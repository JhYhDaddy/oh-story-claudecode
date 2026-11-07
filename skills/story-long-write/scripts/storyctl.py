#!/usr/bin/env python3
"""장편의 장을 측정·체크포인트 생성·검사·커밋한다."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


def _load_local_module(name: str, filename: str) -> Any:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"TOOL_UNAVAILABLE: {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = _load_local_module("story_wordcount_core", "wordcount_core.py")
for _name in dir(core):
    if not _name.startswith("_"):
        globals()[_name] = getattr(core, _name)

CHAPTER_CHECK_SCHEMA = "story-chapter-check/v1"
CHAPTER_ERROR_SCHEMA = "story-chapter-error/v1"
# 작품 내부 작업 디렉터리: segment·집필 프롬프트 기록·장별 트랜잭션 JSON의 유일한 위치.
# build_writer_prompt.py와 같다. 제출 성공 후 전체 디렉터리를 삭제하며 실패하면 재실행용으로 보존한다.
WORK_ROOT = (".story", "work")


class CliArgumentError(ValueError):
    pass


class StructuredArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliArgumentError(message)


def _tracking_module() -> Any:
    return _load_local_module("story_tracking_for_storyctl", "tracking_commit.py")


def _tracking_call(function: Any, *args: Any) -> Any:
    try:
        return function(*args)
    except Exception as exc:
        if exc.__class__.__name__ == "TrackingError":
            raise WordcountError(str(exc)) from exc
        raise


def _json_line(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    # 호출자가 UTF-8을 명시해도 Windows 실행 환경의 콘솔은 cp1252일 수 있다.
    # 프로토콜 출력을 바이트로 써 JSON이 호스트 콘솔 코드 페이지에
    # 의존하지 않게 한다.
    sys.stdout.buffer.write(rendered.encode("utf-8"))
    sys.stdout.buffer.flush()


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WordcountError(f"unable to read {label}: {exc}") from exc
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def chapter_work_dir(project: Path, chapter: int) -> Path:
    width = max(3, len(str(chapter)))
    return project.resolve().joinpath(*WORK_ROOT, f"제{chapter:0{width}d}장")


def _remove_chapter_work_dir(project: Path, chapter: int) -> str | None:
    """커밋 성공 후 해당 장의 작업 디렉터리를 삭제한다.
    장별 디렉터리만 삭제하고 `.story/work`, `.story`는 비었을 때만 제거해 `.story/` 아래 작품 기억을 보존한다.
    """
    path = chapter_work_dir(project, chapter)
    if path.is_symlink():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    else:
        return None
    for parent in (path.parent, path.parent.parent):
        try:
            parent.rmdir()
        except OSError:
            break
    return "/".join((*WORK_ROOT, path.name))


def _project_files(
    project: Path, chapter: int, author_range: Any = None,
) -> tuple[Path, Path, int, dict[str, int] | None]:
    return read_project_chapter(project, chapter, author_range)


def _json_findings(output: str) -> list[dict[str, Any]] | None:
    """검사기 --json의 findings. 예상 JSON이 아니면 문제 없음 대신 도구 고장으로 처리하도록 None을 반환한다."""
    try:
        value = json.loads(output)
    except json.JSONDecodeError:
        return None
    findings = value.get("findings") if isinstance(value, dict) else None
    if not isinstance(findings, list) or not all(isinstance(row, dict) for row in findings):
        return None
    return findings


NODE_REQUIRED = (
    "품질 검사(AI 문장 패턴, 품질 저하, 문장 부호, 상세 개요 복사)에는 Node.js가 필요하지만 현재 node를 찾을 수 없습니다. "
    "Node.js 18 이상을 설치하고 `node --version`이 작동하는지 확인한 뒤 다시 실행하세요. 설치 전에는 이 장을 제출할 수 없습니다."
)


def _semantic_advisories(advisories: list[dict[str, Any]]) -> int:
    # check-ai-patterns는 finding마다 review=semantic|mechanical을 붙인다. 퇴화 검사기는 진입점에서 모두 mechanical로 표시한다.
    # 다른 출처의 미표시 항목은 누락을 피하도록 의미 검토 대상으로 센다.
    return sum(1 for row in advisories if row.get("review") != "mechanical")


# 훅(JS core DESLOP_SKIP_MARKER / codex py / bash guard)과 같은 문법. 주석 안 ASCII 공백·Tab만 인식하고
# 전각·반각 콜론을 모두 받는다. 주석 밖에 그대로 쓴 표식은 인정하지 않는다.
DESLOP_SKIP = re.compile(r"<!--[ \t]*去味[ \t]*(：|:)[ \t]*跳过[ \t]*-->")


def deslop_skipped(body: Path) -> bool:
    """작가가 해당 장의 AI 문체 제거를 거부하면 제목 아래 <!-- 去味:跳过 -->로 문장 패턴을 면제한다. 훅과 같은 첫 6행 범위다."""
    head = re.split(r"\r?\n", body.read_text(encoding="utf-8-sig"))[:6]
    return bool(DESLOP_SKIP.search("\n".join(head)))


def check_blocking_quality(outline: Path, body: Path) -> dict[str, Any]:
    """결정적 본문 검사를 실행한다.
    status: pass=blocking 없음, fail=차단할 본문 문제 있음, unavailable=검사 도구 누락·충돌(본문 문제가 아님, tool_errors 참조).
    """
    node = shutil.which("node")
    if node is None:
        return {
            "status": "unavailable",
            "blocking_findings": [],
            "advisories": [],
            "semantic_advisories": 0,
            "tool_errors": [{"type": "TOOL_UNAVAILABLE", "tool": "node", "message": NODE_REQUIRED}],
        }
    root = Path(__file__).parent
    exempt = deslop_skipped(body)
    blocking: list[dict[str, Any]] = []
    advisories: list[dict[str, Any]] = []
    tool_errors: list[dict[str, Any]] = []
    for name, script in (
        ("ai-pattern", "check-ai-patterns.js"),
        ("degeneration", "check-degeneration.js"),
    ):
        path = root / script
        if not path.is_file():
            tool_errors.append({"type": "TOOL_UNAVAILABLE", "tool": script, "message": f"missing {script}"})
            continue
        completed = subprocess.run(
            [node, str(path), "--check", "--json", "--fail-on=blocking", str(body)],
            text=True, encoding="utf-8", capture_output=True, check=False,
        )
        findings = _json_findings(completed.stdout)
        if findings is None or completed.returncode not in {0, 1}:
            tool_errors.append({"type": "TOOL_ERROR", "tool": script, "source": name,
                                "message": completed.stderr.strip() or f"{script} exited {completed.returncode} without JSON findings"})
            continue
        for finding in findings:
            row = {"source": name, **finding}
            if name == "degeneration":
                # 반복·절단·거절문·작업 용어 같은 퇴화는 AI 문체가 아니므로 문체 검토 발동용 의미 항목 수에 넣지 않는다.
                row.setdefault("review", "mechanical")
            if exempt and name == "ai-pattern" and finding.get("severity") == "blocking":
                # 면제는 AI 문장 패턴에만 적용한다. 반복·절단·거절문·작업 용어는 여전히 고쳐야 한다.
                advisories.append({**row, "severity": "advisory", "exempted": "去味:跳过"})
                continue
            (blocking if finding.get("severity") == "blocking" else advisories).append(row)

    punctuation = root / "normalize-punctuation.js"
    if not punctuation.is_file():
        tool_errors.append({"type": "TOOL_UNAVAILABLE", "tool": punctuation.name,
                            "message": "missing normalize-punctuation.js"})
    else:
        completed = subprocess.run(
            [node, str(punctuation), "--check", str(body)],
            text=True, encoding="utf-8", capture_output=True, check=False,
        )
        if completed.returncode == 1:
            blocking.append(
                {"type": "PUNCTUATION_NOT_NORMALIZED", "message": (completed.stdout or completed.stderr).strip()}
            )
        elif completed.returncode != 0:
            tool_errors.append({"type": "TOOL_ERROR", "tool": punctuation.name,
                                "message": completed.stderr.strip() or f"exited {completed.returncode}"})

    outline_copy = root / "check-outline-copy.js"
    if not outline_copy.is_file():
        tool_errors.append({"type": "TOOL_UNAVAILABLE", "tool": outline_copy.name,
                            "message": "missing check-outline-copy.js"})
    else:
        completed = subprocess.run(
            [node, str(outline_copy), "--outline", str(outline), str(body)],
            text=True, encoding="utf-8", capture_output=True, check=False,
        )
        if completed.returncode != 0:
            advisories.append(
                {"source": "outline-copy", "type": "OUTLINE_COPY_REVIEW", "review": "semantic",
                 "message": completed.stdout.strip()}
            )
    return {
        "status": "unavailable" if tool_errors else ("fail" if blocking else "pass"),
        "blocking_findings": blocking,
        "advisories": advisories,
        "semantic_advisories": _semantic_advisories(advisories),
        "tool_errors": tool_errors,
    }


# chapter check의 최상위 status·종료 코드로 제출 가능·작가 결정 필요·본문 수정 필요·도구 고장을 구분한다.
CHECK_EXIT_CODES = {"ready": 0, "needs_decision": 0, "blocked": 1, "invalid": 1, "tool_unavailable": 3}
ERROR_EXIT_CODES = {"TOOL_UNAVAILABLE": 3}
ACCEPT_FLOOR_RATIO = 0.5
BASELINE_FILE = "over_length_baseline.json"


class ChapterRefused(WordcountError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _check_status(length: dict[str, Any], quality: dict[str, Any]) -> str:
    if quality["status"] == "unavailable":
        return "tool_unavailable"
    if quality["status"] != "pass":
        return "blocked"
    if length["status"] == "invalid":
        return "invalid"
    return "ready" if length["status"] in {"internal_pass", "borderline"} else "needs_decision"


def _body_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_over_baseline(project: Path, chapter: int, body_path: Path, actual: int) -> None:
    """처음 over를 보면 원고 지문을 기록해 초과 분량 수용 전에 한 차례 순삭제 압축을 실제 했는지 입증한다."""
    path = chapter_work_dir(project, chapter) / BASELINE_FILE
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        previous = None
    # 기준 원고보다 짧으면 압축 재검사이므로 기준을 유지한다. 길면 새로 쓴 원고로 보아 다시 기록한다.
    if isinstance(previous, dict) and isinstance(previous.get("actual"), int) and actual <= previous["actual"]:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"body_sha256": _body_digest(body_path), "actual": actual}), encoding="utf-8")


def chapter_check(project: Path, chapter: int, author_range: Any = None) -> dict[str, Any]:
    outline, body_path, target, effective_range = _project_files(project, chapter, author_range)
    try:
        body = body_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise WordcountError(f"unable to read body: {exc}") from exc
    length = evaluate_wordcount(body, target, chapter=chapter, author_range=effective_range)
    quality = check_blocking_quality(outline, body_path)
    status = _check_status(length, quality)
    if status == "ready":
        actions = ["commit"]
    elif status != "needs_decision":
        actions: list[str] = []
    elif length["status"] == "over":
        actions = ["compress-once", "accept-current-length", "revise-outline-or-target", "discard"]
    else:
        actions = ["accept-current-length", "revise-outline-or-target", "discard"]
    tracking = _tracking_module()
    state = _tracking_call(tracking.load_state, project)
    compression = None
    if length["status"] == "over" and quality["status"] == "pass":
        actual = length["actual"]
        compression = {
            "mode": "single_pass_remove_only",
            "remove_to_internal_band": {
                "min": actual - length["internal_band"]["max"],
                "max": actual - length["internal_band"]["min"],
            },
            "remove_to_user_band": {
                "min": actual - length["user_band"]["max"],
                "max": actual - length["user_band"]["min"],
            },
        }
        _record_over_baseline(project, chapter, body_path, actual)
    return {
        "schema": CHAPTER_CHECK_SCHEMA,
        "status": status,
        "chapter": chapter,
        "length": length,
        "quality": quality,
        "compression": compression,
        "state_revision": state["state_revision"],
        "tracking_committed": state["last_committed_chapter"] >= chapter,
        "next_chapter_started": state["last_committed_chapter"] > chapter,
        "available_actions": actions,
    }


def fix_punctuation(project: Path, chapter: int, author_range: Any = None) -> bool:
    """장 본문에 결정적 문장부호 정규화를 직접 적용한다.
    `chapter check --fix-punctuation`에 통합해 상위 절차가 정리 스크립트를 따로 실행하지 않고 한 번에 장을 마무리하게 한다.
    """
    _, body, _, _ = _project_files(project, chapter, author_range)
    node = shutil.which("node")
    script = Path(__file__).with_name("normalize-punctuation.js")
    if node is None or not script.is_file():
        return False  # chapter check는 누락 도구를 quality.tool_errors에 보고한다.
    before = body.read_bytes()
    subprocess.run([node, str(script), str(body)], text=True, encoding="utf-8",
                   capture_output=True, check=False)
    return body.read_bytes() != before


def _require_acceptable_length(
    project: Path, chapter: int, checked: dict[str, Any], *, force: bool, author_range: Any = None,
) -> None:
    """현재 길이 수용의 최소 조건 두 가지: 짧으면 목표 절반 이상, 길면 원고와 작가 상한 차이의 절반 이상을 순삭제하는 압축을 한 번 수행.
    작가가 명시적으로 결정하면 --force로 넘을 수 있다."""
    if force:
        return
    length = checked["length"]
    if length["status"] == "under" and length["actual"] < length["target"] * ACCEPT_FLOOR_RATIO:
        raise ChapterRefused(
            "BELOW_ACCEPT_FLOOR",
            f"이번 장은 {length['actual']}자로 목표 {length['target']}자의 절반에 못 미쳐 현재 분량을 바로 승인할 수 없습니다. "
            "상세 개요를 보완하거나 목표 분량을 수정하세요. 작가가 현재 분량을 명시적으로 원하면 --force를 추가하세요.",
        )
    if length["status"] == "over":
        path = chapter_work_dir(project, chapter) / BASELINE_FILE
        try:
            baseline = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            baseline = None
        _, body_path, _, _ = _project_files(project, chapter, author_range)
        valid = isinstance(baseline, dict) and isinstance(baseline.get("actual"), int)
        # 압축은 실제 삭제해야 한다. 원고와 작가 범위 상한 차이의 최소 절반(최소 1자)을 줄여야 하며 한두 글자만 지우면 수행으로 인정하지 않는다.
        ceiling = None
        if valid:
            gap = baseline["actual"] - length["user_band"]["max"]
            ceiling = baseline["actual"] - max(1, (gap + 1) // 2)
        compressed = (
            valid
            and baseline.get("body_sha256") != _body_digest(body_path)
            and length["actual"] <= ceiling
        )
        if not compressed:
            detail = (f"(원고 {baseline['actual']}자, 압축 후 상한 {ceiling}자, 현재 {length['actual']}자)"
                      if valid else "")
            raise ChapterRefused(
                "COMPRESSION_REQUIRED",
                f"분량을 초과한 장은 먼저 compress-once로 한 번 압축하고 chapter check를 다시 실행하세요{detail}. 그래도 초과하면 현재 분량을 승인할 수 있습니다. "
                "작가가 압축하지 않겠다고 명시하면 --force를 추가하세요.",
            )


def chapter_commit(
    project: Path, chapter: int, input_path: Path, *, accept_current_length: bool,
    author_range: Any = None, force: bool = False,
) -> dict[str, Any]:
    checked = chapter_check(project, chapter, author_range)
    if checked["status"] == "tool_unavailable":
        raise ChapterRefused(
            "TOOL_UNAVAILABLE",
            "；".join(item["message"] for item in checked["quality"]["tool_errors"]) or NODE_REQUIRED,
        )
    if checked["quality"]["status"] != "pass":
        raise ChapterRefused("QUALITY_BLOCKED", "blocking quality findings must be fixed before commit")
    length_status = checked["length"]["status"]
    in_user_band = length_status in {"internal_pass", "borderline"}
    if accept_current_length:
        require(length_status in {"under", "over"}, "accept-current-length requires a valid out-of-band chapter")
        _require_acceptable_length(project, chapter, checked, force=force, author_range=author_range)
        resolution = "accepted_current_length"
    else:
        if not in_user_band:
            raise ChapterRefused(
                "LENGTH_OUT_OF_BAND",
                "chapter length is outside the user band; use accept-current-length or revise it",
            )
        resolution = "within_user_band"
    document = _read_json_object(input_path, "tracking transaction")
    require(document.get("chapter") == chapter, "tracking transaction chapter does not match command")
    require("wordcount" not in document, "tracking transaction must not provide wordcount")
    document["wordcount"] = build_project_wordcount_record(
        project, chapter, resolution=resolution, author_range=author_range,
    )
    tracking = _tracking_module()
    state = _tracking_call(tracking.apply_transaction, project, document)
    checked["tracking_committed"] = state["last_committed_chapter"] >= chapter
    checked["next_chapter_started"] = state["last_committed_chapter"] > chapter
    checked["wordcount"] = state["wordcount_records"].get(str(chapter))
    checked["mode"] = document.get("mode")
    # 커밋은 이미 영구 저장되었다. 정리 실패는 보고하되 커밋 실패로 바꾸지 않는다.
    try:
        checked["work_dir_removed"] = _remove_chapter_work_dir(project, chapter)
    except OSError as exc:
        checked["work_dir_removed"] = None
        checked["work_dir_cleanup_error"] = str(exc)
    return checked


def _build_parser() -> StructuredArgumentParser:
    parser = StructuredArgumentParser(prog="storyctl.py")
    commands = parser.add_subparsers(dest="command", required=True)
    wordcount = commands.add_parser("wordcount")
    wordcount_commands = wordcount.add_subparsers(dest="wordcount_command", required=True)
    for command in ("measure", "check", "checkpoint"):
        subparser = wordcount_commands.add_parser(command)
        subparser.add_argument("--file", required=True)
        subparser.add_argument("--chapter")
        subparser.add_argument("--case-id")
        if command != "measure":
            subparser.add_argument("--target", required=command == "check")
            _add_range_arguments(subparser)
        if command == "checkpoint":
            subparser.add_argument("--project", type=Path,
                                   help="작품 폴더: --chapter와 함께 상세 개요에서 목표 분량(--target 미지정 시)과 분량 범위를 읽음")
    chapter = commands.add_parser("chapter")
    chapter_commands = chapter.add_subparsers(dest="chapter_command", required=True)
    for command in ("check", "commit", "accept-current-length"):
        subparser = chapter_commands.add_parser(command)
        subparser.add_argument("--project", type=Path, required=True)
        subparser.add_argument("--chapter", type=int, required=True)
        _add_range_arguments(subparser)
        if command != "check":
            subparser.add_argument("--input", type=Path, required=True)
        else:
            subparser.add_argument("--fix-punctuation", action="store_true",
                                   help="본문 파일의 문장 부호를 먼저 정리한 뒤 검사")
        if command == "accept-current-length":
            subparser.add_argument("--force", action="store_true",
                                   help="작가의 명시적 결정에 따라 목표 절반 미달 제한과 초과 시 1회 압축 요구를 건너뜀")
    return parser


def _add_range_arguments(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--min-chars", type=int, help="이번 요청의 최소 글자 수(--max-chars와 함께 지정). 상세 개요의 범위와 기본 ±15%%보다 우선")
    subparser.add_argument("--max-chars", type=int, help="이번 요청의 최대 글자 수")


def _cli_author_range(args: argparse.Namespace) -> dict[str, int] | None:
    low, high = getattr(args, "min_chars", None), getattr(args, "max_chars", None)
    if low is None and high is None:
        return None
    if low is None or high is None:
        raise CliArgumentError("--min-chars and --max-chars must be given together")
    try:
        return normalize_author_range({"min": low, "max": high})
    except WordcountError as exc:
        raise CliArgumentError(str(exc)) from exc


def _wordcount_command(args: argparse.Namespace, author_range: dict[str, int] | None) -> int:
    try:
        body = Path(args.file).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        result = (
            {"schema": MEASUREMENT_SCHEMA, "metric": METRIC, "chapter": args.chapter, "case_id": args.case_id,
             "actual": None, "status": "invalid", "invalid_reason": "INVALID_FILE"}
            if args.wordcount_command == "measure"
            else invalid_wordcount_result("INVALID_FILE", chapter=args.chapter, case_id=args.case_id)
        )
        _json_line(result)
        return 2
    if args.wordcount_command == "measure":
        result = measure_wordcount(body, chapter=args.chapter, case_id=args.case_id)
    elif args.wordcount_command == "checkpoint":
        target = args.target
        if args.project is not None:
            # chapter check와 같은 우선순위: 명령행 상·하한 > 개요 ‘字数范围’ > 기본 범위.
            try:
                chapter = int(args.chapter or "")
                _, outline = read_chapter_outline(args.project, chapter)
                if target is None:
                    target = target_from_outline(outline)
                author_range = effective_author_range(outline, author_range)
            except (ValueError, WordcountError):
                _json_line(invalid_wordcount_result("INVALID_OUTLINE", chapter=args.chapter, case_id=args.case_id))
                return 2
        if target is None:
            _json_line(invalid_wordcount_result("INVALID_ARGUMENT", chapter=args.chapter, case_id="--target or --project is required"))
            return 2
        try:
            result = checkpoint_wordcount(
                body, target, chapter=args.chapter, case_id=args.case_id, author_range=author_range,
            )
        except WordcountError:
            result = invalid_wordcount_result("INVALID_TARGET", chapter=args.chapter, case_id=args.case_id)
    else:
        result = evaluate_wordcount(
            body, args.target, chapter=args.chapter, case_id=args.case_id, author_range=author_range,
        )
    _json_line(result)
    return 2 if result.get("status") == "invalid" else 0


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(argv) if argv is not None else sys.argv[1:]
    try:
        args = _build_parser().parse_args(raw)
        author_range = _cli_author_range(args)
    except CliArgumentError as exc:
        payload = (
            {"schema": CHAPTER_ERROR_SCHEMA, "status": "error", "error_code": "INVALID_ARGUMENT", "message": str(exc)}
            if raw[:1] == ["chapter"] else invalid_wordcount_result("INVALID_ARGUMENT", case_id=str(exc))
        )
        _json_line(payload)
        return 2
    if args.command == "wordcount":
        return _wordcount_command(args, author_range)
    try:
        if args.chapter_command == "check":
            fixed = fix_punctuation(args.project, args.chapter, author_range) if args.fix_punctuation else None
            result = chapter_check(args.project, args.chapter, author_range)
            if fixed is not None:
                result["punctuation_fixed"] = fixed
        else:
            result = chapter_commit(
                args.project, args.chapter, args.input,
                accept_current_length=args.chapter_command == "accept-current-length",
                author_range=author_range, force=getattr(args, "force", False),
            )
    except (WordcountError, OSError, UnicodeError) as exc:
        code = exc.code if isinstance(exc, ChapterRefused) else "CHECK_FAILED"
        _json_line({"schema": CHAPTER_ERROR_SCHEMA, "status": "error", "error_code": code, "message": str(exc)})
        return ERROR_EXIT_CODES.get(code, 2)
    _json_line(result)
    if args.chapter_command != "check":
        return 0
    return CHECK_EXIT_CODES[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
