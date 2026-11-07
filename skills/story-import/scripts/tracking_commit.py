#!/usr/bin/env python3
"""단일 구조화된 이야기 상태와 결정적 Markdown 뷰를 관리한다.

언어 모델이 간결한 의미 JSON을 공급하면 메모리에서 검증·병합하고 모든 파생 뷰를 렌더링한다.
마지막으로 유일한 커밋 지점인 ``_tracking-state.json``을 원자적으로 쓴다.
프로젝트별 잠금으로 리비전·글자 수 검사 전에 동시 작성자를 직렬화한다.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import re
import stat
import sys
import tempfile
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Any


_WORDCOUNT_CORE_PATH = Path(__file__).with_name("wordcount_core.py")
if not _WORDCOUNT_CORE_PATH.is_file():  # pragma: no cover - 배포 손상
    raise RuntimeError("TOOL_UNAVAILABLE: wordcount_core.py")
_WORDCOUNT_CORE_SPEC = importlib.util.spec_from_file_location(
    "story_wordcount_core", _WORDCOUNT_CORE_PATH
)
if _WORDCOUNT_CORE_SPEC is None or _WORDCOUNT_CORE_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("unable to load wordcount core")
wordcount_core = importlib.util.module_from_spec(_WORDCOUNT_CORE_SPEC)
_WORDCOUNT_CORE_SPEC.loader.exec_module(wordcount_core)


INPUT_SCHEMA_VERSION = 1
TRACKING_SCHEMA_VERSION = 4
DELTA_TARGET_BYTES = 1536
DELTA_MAX_BYTES = 3072
CONTEXT_TARGET_BYTES = 8192
CONTEXT_MAX_BYTES = 12288
SNAPSHOT_TARGET_BYTES = 4096
SNAPSHOT_MAX_BYTES = 8192
# 다음 장의 즉시 참조 컨텍스트에 열거하는 활성 인물 수이며 핵심 인물 총수가 아니다. 크기는 CONTEXT_MAX_BYTES가 제한한다.
ACTIVE_CHARACTER_MAX = 20

CONTEXT_HEADINGS = (
    "## 当前位置",
    "## 长期约束",
    "## 核心角色状态",
    "## 活跃伏笔",
    "## 近三章速记",
    "## 下一章承诺",
    "## 连贯性风险",
)
FORESHADOW_STATUSES = ("已埋", "已回收", "已过期", "放弃")
FORESHADOW_IMPORTANCE = ("高", "中", "低")
REVEAL_STATUSES = ("未揭示", "部分揭示", "已揭示")
# 모델이 복선·시간선 항목에 자주 쓰는 명확한 동의어는 정식 이름으로 바꿔 표현 때문에 제출이 실패하지 않게 한다.
ACTION_ALIASES = {
    "add": "upsert", "new": "upsert", "create": "upsert", "update": "upsert", "plant": "upsert",
    "advance": "upsert", "resolve": "upsert", "insert": "upsert",
    "新增": "upsert", "埋设": "upsert", "更新": "upsert", "推进": "upsert", "回收": "upsert",
    "remove": "delete", "删除": "delete",
}
# 상태 의미를 가진 복선 동작어도 upsert로 매핑하지만 단어 자체가 복선의 진행 단계를 나타낸다.
# status가 없으면 유일한 의도 출처인 동작어로 보충한다. status와 동작어가 충돌하면 반려한다.
# 어느 쪽이 잘못됐는지 판단할 수 없으며 조용히 고치면 미회수 복선을 회수 완료로 기록할 수 있기 때문이다.
FORESHADOW_ACTION_STATUS = {
    "resolve": "已回收", "回收": "已回收",
    "advance": "已埋", "推进": "已埋",
}
FORESHADOW_KEY_ALIASES = {
    "planned_chapter": "planned_resolution_chapter", "planned_payoff_chapter": "planned_resolution_chapter",
    "payoff_chapter": "planned_resolution_chapter", "resolution_chapter": "planned_resolution_chapter",
    "resolve_chapter": "planned_resolution_chapter", "plant_chapter": "planted_chapter",
    "planted": "planted_chapter", "description": "summary", "content": "summary",
}
TIMELINE_KEY_ALIASES = {"time": "story_time", "fact": "objective_fact", "reveal": "reveal_status"}
INVALID_FILE_CHARS = re.compile(r"[<>:\"/\\|?*\x00-\x1f]")
FORESHADOW_ID = re.compile(r"^F\d{3,}$")
SNAPSHOT_TEXT_FIELDS = ("identity", "location", "goal", "state")
SNAPSHOT_LIST_FIELDS = ("abilities_resources", "relationships", "knowledge", "open_threads")
EVENT_ID = re.compile(r"^E\d{3,}$")
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
RETIRED_TRACKING_PATHS = (
    "_tracking-meta.json",
    "단계요약.md",
    "인물상태.md",
    "시간선.md",
    "요약",
    "시간선/사건목록.json",
)
RETIRED_ARCHIVE_DIR = "_이전추적보관"


class TrackingError(ValueError):
    """예상 가능한 검증 오류 또는 추적 상태 오류."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TrackingError(message)


def wordcount_value(function: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return function(*args, **kwargs)
    except wordcount_core.WordcountError as exc:
        raise TrackingError(str(exc)) from exc


def as_mapping(value: object, label: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def as_list(value: object, label: str) -> list[Any]:
    require(isinstance(value, list), f"{label} must be a JSON array")
    return value


def as_int(value: object, label: str, *, minimum: int = 0) -> int:
    require(isinstance(value, int) and not isinstance(value, bool), f"{label} must be an integer")
    require(value >= minimum, f"{label} must be >= {minimum}")
    return value


def as_chapter(value: object, label: str, *, minimum: int = 1) -> int:
    """장 번호: 모델이 자주 쓰는 숫자 문자열 "22"는 의미를 유지하며 정수로 받고 나머지는 기존처럼 오류로 처리한다."""
    if isinstance(value, str) and value.strip().isdecimal():
        value = int(value.strip())
    return as_int(value, label, minimum=minimum)


def with_aliases(row: dict[str, Any], aliases: dict[str, str]) -> dict[str, Any]:
    """뜻이 명확한 동의 필드를 정식 이름으로 바꾼다. 정식 필드가 이미 있으면 그대로 두어 알 수 없는 필드 오류로 처리한다."""
    row = dict(row)
    for alias, canonical in aliases.items():
        if alias in row and canonical not in row:
            row[canonical] = row.pop(alias)
    return row


def normalize_action(value: object, label: str, *, allow_delete: bool) -> str:
    action = clean_text(value, label, max_bytes=24)
    action = ACTION_ALIASES.get(action.lower(), action.lower())
    allowed = ("upsert", "delete") if allow_delete else ("upsert",)
    require(action in allowed, f"{label} is invalid: use {' or '.join(allowed)}")
    return action


def require_known_keys(mapping: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(mapping) - allowed
    require(not unknown, f"{label} contains unsupported fields: {', '.join(sorted(unknown))}"
                         f"(허용 값: {', '.join(sorted(allowed))})")


# 트랜잭션 검증 중 길이 초과 필드를 모아 한꺼번에 보고한다. None은 초기화·상태 읽기 등에서 즉시 개별 오류를 보고한다.
_LENGTH_ISSUES: list[str] | None = None


def length_hint(label: str, text: str, max_bytes: int) -> str:
    """바이트 상한을 글자 수로 바꾼다. 중국어를 쓰는 모델에는 몇 글자를 줄여야 하는지 알려줘야 한다."""
    size = len(text.encode("utf-8"))
    allowed = max(1, max_bytes * len(text) // size)
    return (f"{label} exceeds {max_bytes} bytes(현재 {len(text)}자, 상한 약 {allowed}자, "
            f"최소 {len(text) - allowed}자 삭제 필요)")


def clean_text(value: object, label: str, *, allow_empty: bool = False, max_bytes: int = 768) -> str:
    require(isinstance(value, str), f"{label} must be a string")
    cleaned = " ".join(value.replace("|", "｜").split())
    require(allow_empty or bool(cleaned), f"{label} must not be empty")
    if len(cleaned.encode("utf-8")) > max_bytes:
        if _LENGTH_ISSUES is None:
            raise TrackingError(length_hint(label, cleaned, max_bytes))
        _LENGTH_ISSUES.append(length_hint(label, cleaned, max_bytes))
    return cleaned


def clean_string_list(
    value: object,
    label: str,
    *,
    maximum: int | None = None,
    item_max_bytes: int = 384,
) -> list[str]:
    values = as_list(value, label)
    if maximum is not None:
        require(len(values) <= maximum, f"{label} may contain at most {maximum} items")
    return [clean_text(item, f"{label}[{index}]", max_bytes=item_max_bytes) for index, item in enumerate(values)]


def safe_file_component(value: object, label: str) -> str:
    name = unicodedata.normalize("NFC", clean_text(value, label, max_bytes=180))
    require(not INVALID_FILE_CHARS.search(name), f"{label} contains an invalid filename character")
    require(name not in {".", ".."} and not name.endswith((".", " ")), f"{label} is not a safe filename")
    require(name.split(".", 1)[0].upper() not in WINDOWS_RESERVED_NAMES, f"{label} is reserved on Windows")
    return name


def portable_name_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def byte_size(text: str) -> int:
    return len(text.encode("utf-8"))


def emit(text: str, *, error: bool = False) -> None:
    """UTF-8 바이트를 직접 쓴다.
    Windows 텍스트 stdout은 cp1252라 중국어에서 UnicodeEncodeError가 나고 stderr 기본 backslashreplace는 중국어를 읽기 어려운 코드 포인트로 바꾼다. 둘 다 우회한다.
    """
    stream = sys.stderr if error else sys.stdout
    stream.flush()
    stream.buffer.write((text + "\n").encode("utf-8"))
    stream.buffer.flush()


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrackingError(f"unable to read JSON {path}: {exc}") from exc


def json_payload(document: object) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def atomic_write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_if_changed(path: Path, payload: str) -> None:
    try:
        if path.read_text(encoding="utf-8") == payload:
            return
    except FileNotFoundError:
        pass
    atomic_write_text(path, payload)


def tracking_root(project: Path) -> Path:
    return project.resolve() / "추적"


def state_path(project: Path) -> Path:
    return tracking_root(project) / "_tracking-state.json"


@contextmanager
def project_write_lock(project: Path, *, timeout_seconds: float = 10.0):
    tracking = tracking_root(project)
    tracking.mkdir(parents=True, exist_ok=True)
    path = tracking / ".tracking-commit.lock"
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TrackingError(
                    "tracking commit lock is busy or stale; retry, or remove 추적/.tracking-commit.lock after confirming no commit is running"
                )
            time.sleep(0.05)
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def delta_path(tracking: Path, chapter: int) -> Path:
    width = max(3, len(str(chapter)))
    return tracking / "장별기록" / f"제{chapter:0{width}d}장.md"


def find_retired_tracking_paths(tracking: Path) -> list[str]:
    found = [relative for relative in RETIRED_TRACKING_PATHS if (tracking / relative).exists()]
    found.extend(sorted(path.name for path in tracking.glob("기준_종료제*장.md")))
    return found


def require_no_retired_tracking_paths(tracking: Path) -> None:
    found = find_retired_tracking_paths(tracking)
    require(not found, f"retired tracking files are not supported: {', '.join(found)}")


def archive_retired_tracking_paths(tracking: Path) -> list[str]:
    """트랜잭션 도입 전 추적/을 옆으로 옮겨 init이 현재 프로토콜을 그 자리에 만들게 한다.
    이전 파일은 파싱·변환 없이 작가 참고용으로 그대로 보존한다. 새 상태는 init 문서만으로 재구성한다.
    """
    retired = find_retired_tracking_paths(tracking)
    if not retired:
        return []
    archive = tracking / RETIRED_ARCHIVE_DIR
    for relative in retired:
        require(
            not (archive / relative).exists(),
            f"추적/{RETIRED_ARCHIVE_DIR}/{relative} already exists; move it away before initializing",
        )
    # 전체 검증 후 이동한다. 중단 후 재실행하면 이미 옮긴 항목은 대기 목록에서 빠져 바로 이어갈 수 있다.
    for relative in retired:
        target = archive / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tracking / relative, target)
    return retired


def _both_blank(position: dict[str, Any]) -> bool:
    return all(isinstance(position.get(key), str) and not position[key].strip() for key in ("story_time", "scene"))


def validate_position(value: object, label: str = "context.position") -> dict[str, Any]:
    position = as_mapping(value, label)
    require_known_keys(position, {"volume", "volume_start_chapter", "story_time", "scene"}, label)
    require(not _both_blank(position),
            f"{label}.story_time and {label}.scene must not be empty: fill where this chapter ends")
    return {
        "volume": safe_file_component(position.get("volume"), f"{label}.volume"),
        "volume_start_chapter": as_int(
            position.get("volume_start_chapter"), f"{label}.volume_start_chapter", minimum=1
        ),
        "story_time": clean_text(position.get("story_time"), f"{label}.story_time", max_bytes=240),
        "scene": clean_text(position.get("scene"), f"{label}.scene", max_bytes=240),
    }


def joined_text(value: object) -> object:
    """단문 필드가 문자열 목록이면 ‘；’로 이어 내용을 잃지 않고 한 문장으로 만든다."""
    if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
        return "；".join(value)
    return value


def as_text_list(value: object) -> object:
    """목록 필드에 한 문장만 있으면 항목 하나로 취급한다."""
    return [value] if isinstance(value, str) and value.strip() else value


def normalize_snapshot(value: object, label: str) -> dict[str, Any]:
    snapshot = as_mapping(value, label)
    snapshot = {key: joined_text(item) if key in SNAPSHOT_TEXT_FIELDS else as_text_list(item)
                if key in SNAPSHOT_LIST_FIELDS else item for key, item in snapshot.items()}
    require_known_keys(
        snapshot,
        {"identity", "location", "goal", "state", "abilities_resources", "relationships", "knowledge", "open_threads"},
        label,
    )
    return {
        "identity": clean_text(snapshot.get("identity"), f"{label}.identity", max_bytes=240),
        "location": clean_text(snapshot.get("location"), f"{label}.location", max_bytes=240),
        "goal": clean_text(snapshot.get("goal"), f"{label}.goal", max_bytes=300),
        "state": clean_text(snapshot.get("state"), f"{label}.state", max_bytes=300),
        "abilities_resources": clean_string_list(
            snapshot.get("abilities_resources", []), f"{label}.abilities_resources"
        ),
        "relationships": clean_string_list(snapshot.get("relationships", []), f"{label}.relationships"),
        "knowledge": clean_string_list(snapshot.get("knowledge", []), f"{label}.knowledge"),
        "open_threads": clean_string_list(snapshot.get("open_threads", []), f"{label}.open_threads"),
    }


def normalize_snapshots(value: object, label: str = "character_snapshots") -> dict[str, dict[str, Any]]:
    snapshots = as_mapping(value, label)
    normalized: dict[str, dict[str, Any]] = {}
    portable_names: set[str] = set()
    for raw_name, raw_snapshot in snapshots.items():
        name = safe_file_component(raw_name, f"{label} character name")
        key = portable_name_key(name)
        require(key not in portable_names, f"{label} contains a cross-platform duplicate character {name}")
        portable_names.add(key)
        normalized[name] = normalize_snapshot(raw_snapshot, f"{label}.{name}")
    return normalized


def render_snapshot(name: str, snapshot: dict[str, Any], through_chapter: int, revision: int) -> str:
    def section(title: str, values: list[str]) -> list[str]:
        return [f"## {title}", *(f"- {item}" for item in values or ["无"]), ""]

    lines = [
        f"# {name}｜当前状态",
        "",
        f"- 状态修订：{revision}",
        f"- 截至章节：第{through_chapter}章",
        f"- 身份：{snapshot['identity']}",
        f"- 位置：{snapshot['location']}",
        f"- 当前目标：{snapshot['goal']}",
        f"- 身心状态：{snapshot['state']}",
        "",
    ]
    lines.extend(section("能力与资源", snapshot["abilities_resources"]))
    lines.extend(section("关键关系", snapshot["relationships"]))
    lines.extend(section("已知信息", snapshot["knowledge"]))
    lines.extend(section("未结事项", snapshot["open_threads"]))
    payload = "\n".join(lines).rstrip() + "\n"
    require(
        byte_size(payload) <= SNAPSHOT_MAX_BYTES,
        f"character snapshot {name} exceeds hard cap of {SNAPSHOT_MAX_BYTES} bytes",
    )
    return payload


def normalize_foreshadow_change(
    value: object,
    label: str,
    *,
    allow_delete: bool,
    through_chapter: int,
) -> dict[str, Any]:
    row = with_aliases(as_mapping(value, label), FORESHADOW_KEY_ALIASES)
    require_known_keys(
        row,
        {"action", "id", "summary", "planted_chapter", "planned_resolution_chapter", "status", "importance"},
        label,
    )
    raw_action = row.get("action", "upsert")
    action = normalize_action(raw_action, f"{label}.action", allow_delete=allow_delete)
    identifier = clean_text(row.get("id"), f"{label}.id", max_bytes=24)
    require(FORESHADOW_ID.fullmatch(identifier) is not None, f"{label}.id must look like F001")
    if action == "delete":
        return {"action": action, "id": identifier}
    implied = FORESHADOW_ACTION_STATUS.get(" ".join(str(raw_action).split()).lower())
    if implied is not None:
        if row.get("status") in (None, ""):
            row["status"] = implied
        right = "회수했다면 status=已回收로 적으세요" if implied == "已回收" else "진전만 있고 아직 회수하지 않았다면 status=已埋로 적으세요"
        require(
            row["status"] == implied,
            f"{label}.action={raw_action}과(와) status={row['status']}가 모순됩니다: {right}. "
            "그 뜻이 아니라면 action을 upsert로 바꾸고 실제 상태를 적으세요",
        )
    planted_chapter = as_chapter(row.get("planted_chapter"), f"{label}.planted_chapter")
    require(planted_chapter <= through_chapter, f"{label}.planted_chapter cannot be in the future")
    planned_raw = row.get("planned_resolution_chapter")
    planned_chapter = (
        None if planned_raw in (None, "") else as_chapter(planned_raw, f"{label}.planned_resolution_chapter")
    )
    require(
        planned_chapter is None or planned_chapter >= planted_chapter,
        f"{label}.planned_resolution_chapter cannot precede planted_chapter",
    )
    status = clean_text(row.get("status"), f"{label}.status", max_bytes=24)
    importance = clean_text(row.get("importance"), f"{label}.importance", max_bytes=12)
    require(status in FORESHADOW_STATUSES, f"{label}.status must be one of {FORESHADOW_STATUSES}")
    require(importance in FORESHADOW_IMPORTANCE, f"{label}.importance must be one of {FORESHADOW_IMPORTANCE}")
    return {
        "action": action,
        "id": identifier,
        "summary": clean_text(row.get("summary"), f"{label}.summary", max_bytes=360),
        "planted_chapter": planted_chapter,
        "planned_resolution_chapter": planned_chapter,
        "status": status,
        "importance": importance,
    }


def normalize_foreshadow_state(value: object, last_chapter: int) -> dict[str, dict[str, Any]]:
    rows = as_mapping(value, "tracking state.foreshadow")
    normalized: dict[str, dict[str, Any]] = {}
    for raw_identifier, raw_row in rows.items():
        identifier = clean_text(raw_identifier, "tracking state.foreshadow ID", max_bytes=24)
        row = as_mapping(raw_row, f"tracking state.foreshadow.{identifier}")
        require_known_keys(
            row,
            {"id", "summary", "planted_chapter", "planned_resolution_chapter", "status", "importance", "updated_chapter"},
            f"tracking state.foreshadow.{identifier}",
        )
        require(row.get("id") == identifier, f"tracking state.foreshadow.{identifier}.id does not match its key")
        change = normalize_foreshadow_change(
            {
                "action": "upsert",
                **{key: value for key, value in row.items() if key != "updated_chapter"},
            },
            f"tracking state.foreshadow.{identifier}",
            allow_delete=False,
            through_chapter=last_chapter,
        )
        change.pop("action")
        updated = as_int(row.get("updated_chapter"), f"tracking state.foreshadow.{identifier}.updated_chapter", minimum=1)
        require(updated <= last_chapter, f"foreshadow {identifier} updates after current chapter")
        change["updated_chapter"] = updated
        normalized[identifier] = change
    return normalized


def render_foreshadow(rows: dict[str, dict[str, Any]], revision: int) -> str:
    lines = [
        "# 伏笔当前状态",
        "",
        f"> 状态修订：{revision}。每个 ID 只保留一行当前状态；历史变化见 `장별기록/`。",
        "",
        "| ID | 内容 | 埋设章 | 计划回收章 | 状态 | 重要度 | 最近变更章 |",
        "|---|---|---:|---:|---|---|---:|",
    ]
    for identifier in sorted(rows):
        row = rows[identifier]
        planned = f"第{row['planned_resolution_chapter']}章" if row["planned_resolution_chapter"] else "—"
        lines.append(
            f"| {identifier} | {row['summary']} | 第{row['planted_chapter']}章 | {planned} | "
            f"{row['status']} | {row['importance']} | 第{row['updated_chapter']}章 |"
        )
    return "\n".join(lines) + "\n"


def normalize_timeline_change(
    value: object,
    label: str,
    *,
    allow_delete: bool,
    through_chapter: int,
) -> dict[str, Any]:
    event = with_aliases(as_mapping(value, label), TIMELINE_KEY_ALIASES)
    require_known_keys(
        event,
        {"action", "id", "story_time", "objective_fact", "reader_knowledge", "reveal_status", "reveal_chapter", "characters"},
        label,
    )
    action = normalize_action(event.get("action", "upsert"), f"{label}.action", allow_delete=allow_delete)
    identifier = clean_text(event.get("id"), f"{label}.id", max_bytes=24)
    require(EVENT_ID.fullmatch(identifier) is not None, f"{label}.id must look like E001")
    if action == "delete":
        return {"action": action, "id": identifier}
    reveal_status = clean_text(event.get("reveal_status"), f"{label}.reveal_status", max_bytes=24)
    require(reveal_status in REVEAL_STATUSES, f"{label}.reveal_status must be one of {REVEAL_STATUSES}")
    reveal_raw = event.get("reveal_chapter")
    reveal_chapter = None if reveal_raw in (None, "") else as_chapter(reveal_raw, f"{label}.reveal_chapter")
    if reveal_status == "未揭示":
        require(reveal_chapter is None, f"{label} must not put a future reveal chapter in established timeline facts")
    else:
        require(reveal_chapter is not None, f"{label}.reveal_chapter is required once revealed")
        require(reveal_chapter <= through_chapter, f"{label}.reveal_chapter cannot be in the future")
    return {
        "action": action,
        "id": identifier,
        "story_time": clean_text(event.get("story_time"), f"{label}.story_time", max_bytes=240),
        "objective_fact": clean_text(event.get("objective_fact"), f"{label}.objective_fact", max_bytes=480),
        "reader_knowledge": clean_text(event.get("reader_knowledge"), f"{label}.reader_knowledge", max_bytes=480),
        "reveal_status": reveal_status,
        "reveal_chapter": reveal_chapter,
        "characters": clean_string_list(event.get("characters", []), f"{label}.characters", maximum=12, item_max_bytes=120),
    }


def normalize_timeline_state(value: object, last_chapter: int) -> dict[str, dict[str, Any]]:
    events = as_mapping(value, "tracking state.timeline")
    normalized: dict[str, dict[str, Any]] = {}
    for raw_identifier, raw_event in events.items():
        identifier = clean_text(raw_identifier, "tracking state.timeline ID", max_bytes=24)
        event = as_mapping(raw_event, f"tracking state.timeline.{identifier}")
        require_known_keys(
            event,
            {
                "id", "story_time", "objective_fact", "reader_knowledge", "reveal_status", "reveal_chapter",
                "characters", "first_recorded_chapter", "updated_chapter",
            },
            f"tracking state.timeline.{identifier}",
        )
        require(event.get("id") == identifier, f"tracking state.timeline.{identifier}.id does not match its key")
        change = normalize_timeline_change(
            {
                "action": "upsert",
                **{
                    key: value
                    for key, value in event.items()
                    if key not in {"first_recorded_chapter", "updated_chapter"}
                },
            },
            f"tracking state.timeline.{identifier}",
            allow_delete=False,
            through_chapter=last_chapter,
        )
        change.pop("action")
        first = as_int(event.get("first_recorded_chapter"), f"tracking state.timeline.{identifier}.first_recorded_chapter", minimum=1)
        updated = as_int(event.get("updated_chapter"), f"tracking state.timeline.{identifier}.updated_chapter", minimum=1)
        require(first <= last_chapter, f"timeline event {identifier} starts after current chapter")
        require(updated <= last_chapter, f"timeline event {identifier} updates after current chapter")
        change["first_recorded_chapter"] = first
        change["updated_chapter"] = updated
        normalized[identifier] = change
    return normalized


def render_timeline_views(events: dict[str, dict[str, Any]], revision: int) -> tuple[str, str]:
    author_lines = [
        "# 作者真相时间线",
        "",
        f"> 状态修订：{revision}。客观事实与读者认知的权威对照；未来揭示计划仍留在大纲。",
        "",
        "| ID | 首次登记章 | 故事时间 | 客观事实 | 读者当前认知 | 揭示状态 | 实际揭示章 |",
        "|---|---:|---|---|---|---|---:|",
    ]
    reader_lines = [
        "# 读者已知时间线",
        "",
        f"> 状态修订：{revision}。只呈现读者截至当前章节已经知道或相信的内容，不泄露作者侧客观真相。",
        "",
        "| ID | 读者当前认知 | 认知截至章 |",
        "|---|---|---:|",
    ]
    for identifier in sorted(events):
        event = events[identifier]
        reveal = f"第{event['reveal_chapter']}章" if event.get("reveal_chapter") else "—"
        characters = "、".join(event.get("characters", []))
        objective = event["objective_fact"] + (f"（涉及：{characters}）" if characters else "")
        author_lines.append(
            f"| {identifier} | 第{event['first_recorded_chapter']}章 | {event['story_time']} | {objective} | "
            f"{event['reader_knowledge']} | {event['reveal_status']} | {reveal} |"
        )
        reader_lines.append(f"| {identifier} | {event['reader_knowledge']} | 第{event['updated_chapter']}章 |")
    return "\n".join(author_lines) + "\n", "\n".join(reader_lines) + "\n"


def validate_context_input(value: object, *, include_initial_fields: bool) -> dict[str, Any]:
    context = as_mapping(value, "context")
    allowed = {"position", "long_term_constraints", "active_character_names", "continuity_risks"}
    if include_initial_fields:
        allowed.update({"recent_chapters", "next_chapter_commitments"})
    require_known_keys(context, allowed, "context")
    normalized: dict[str, Any] = {
        "position": validate_position(context.get("position")),
        "long_term_constraints": clean_string_list(
            context.get("long_term_constraints", []), "context.long_term_constraints", maximum=6
        ),
        "active_character_names": [
            safe_file_component(name, f"context.active_character_names[{index}]")
            for index, name in enumerate(as_list(context.get("active_character_names", []), "context.active_character_names"))
        ],
        "continuity_risks": clean_string_list(
            context.get("continuity_risks", []), "context.continuity_risks", maximum=5
        ),
    }
    require(
        len(normalized["active_character_names"]) <= ACTIVE_CHARACTER_MAX,
        f"context.active_character_names may contain at most {ACTIVE_CHARACTER_MAX} names",
    )
    require(
        len({portable_name_key(name) for name in normalized["active_character_names"]})
        == len(normalized["active_character_names"]),
        "context.active_character_names contains cross-platform duplicates",
    )
    if include_initial_fields:
        recent: list[dict[str, Any]] = []
        for index, raw_item in enumerate(as_list(context.get("recent_chapters", []), "context.recent_chapters")):
            item = as_mapping(raw_item, f"context.recent_chapters[{index}]")
            require_known_keys(item, {"chapter", "summary"}, f"context.recent_chapters[{index}]")
            recent.append(
                {
                    "chapter": as_int(item.get("chapter"), f"context.recent_chapters[{index}].chapter", minimum=1),
                    "summary": clean_text(item.get("summary"), f"context.recent_chapters[{index}].summary", max_bytes=360),
                }
            )
        require(len(recent) <= 3, "context.recent_chapters may contain at most 3 items")
        normalized["recent_chapters"] = recent
        normalized["next_chapter_commitments"] = clean_string_list(
            context.get("next_chapter_commitments", []), "context.next_chapter_commitments", maximum=5
        )
    return normalized


def active_foreshadow_lines(rows: dict[str, dict[str, Any]]) -> list[str]:
    importance = {value: index for index, value in enumerate(FORESHADOW_IMPORTANCE)}
    candidates = [row for row in rows.values() if row["status"] == "已埋"]
    candidates.sort(
        key=lambda row: (importance[row["importance"]], row["planned_resolution_chapter"] or 10**12, row["id"])
    )
    result = []
    for row in candidates[:8]:
        planned = f"第{row['planned_resolution_chapter']}章" if row["planned_resolution_chapter"] else "回收章未定"
        result.append(f"{row['id']}｜{row['summary']}｜埋第{row['planted_chapter']}章｜{planned}｜{row['importance']}")
    return result


def render_context(state: dict[str, Any]) -> str:
    context = state["context"]
    position = context["position"]
    current_chapter = (
        "尚未开篇" if state["last_committed_chapter"] == 0 else f"第{state['last_committed_chapter']}章"
    )
    character_lines = [
        f"{name}｜{state['characters'][name]['identity']}｜{state['characters'][name]['state']}｜"
        f"目标：{state['characters'][name]['goal']}"
        for name in context["active_character_names"]
    ]
    sections: list[tuple[str, list[str]]] = [
        (
            "## 当前位置",
            [
                f"当前章：{current_chapter}",
                f"卷：{position['volume']}（始于第{position['volume_start_chapter']}章）",
                f"故事时间：{position['story_time']}",
                f"场景：{position['scene']}",
            ],
        ),
        ("## 长期约束", context["long_term_constraints"]),
        ("## 核心角色状态", character_lines),
        ("## 活跃伏笔", active_foreshadow_lines(state["foreshadow"])),
        ("## 近三章速记", [f"第{item['chapter']}章｜{item['summary']}" for item in context["recent_chapters"]]),
        ("## 下一章承诺", context["next_chapter_commitments"]),
        ("## 连贯性风险", context["continuity_risks"]),
    ]
    lines = [
        f"# 写作连续性上下文 — {state['book_title']}",
        "",
        f"> 状态修订：{state['state_revision']}。截至当前章的续写状态卡，只放下一章真正需要的连续性状态。",
        "",
    ]
    for heading, values in sections:
        lines.append(heading)
        lines.extend(f"- {value}" for value in values or ["无"])
        lines.append("")
    payload = "\n".join(lines).rstrip() + "\n"
    headings = tuple(line for line in payload.splitlines() if line.startswith("## "))
    require(headings == CONTEXT_HEADINGS, "generated context headings do not match the seven-section schema")
    require(byte_size(payload) <= CONTEXT_MAX_BYTES, f"hot context exceeds {CONTEXT_MAX_BYTES} bytes")
    return payload


def normalize_delta(
    value: object,
    *,
    through_chapter: int,
    snapshots: dict[str, dict[str, Any]],
    existing_core_names: dict[str, str],
) -> dict[str, Any]:
    delta = as_mapping(value, "delta")
    require_known_keys(
        delta,
        {
            "result", "character_changes", "foreshadow_changes", "timeline_events", "constraints",
            "next_chapter_commitments", "retired_context_items", "retired_characters",
        },
        "delta",
    )
    retired_characters = [
        safe_file_component(name, f"delta.retired_characters[{index}]")
        for index, name in enumerate(as_list(delta.get("retired_characters", []), "delta.retired_characters"))
    ]
    retired_keys = [portable_name_key(name) for name in retired_characters]
    require(len(retired_keys) == len(set(retired_keys)), "delta.retired_characters contains duplicate characters")
    retiring = set(retired_keys)
    character_changes: list[dict[str, Any]] = []
    for index, raw_change in enumerate(as_list(delta.get("character_changes", []), "delta.character_changes")):
        change = as_mapping(raw_change, f"delta.character_changes[{index}]")
        require_known_keys(change, {"name", "change"}, f"delta.character_changes[{index}]")
        name = safe_file_component(change.get("name"), f"delta.character_changes[{index}].name")
        existing = existing_core_names.get(portable_name_key(name))
        is_core = name in snapshots or existing is not None
        # 이번 장에 퇴역한 인물은 마지막 변화만 기록하며 곧 삭제할 스냅샷을 추가 제출할 필요가 없다.
        require(
            not is_core or name in snapshots or portable_name_key(name) in retiring,
            f"core character {name} changed but has no current snapshot:  draft 출력의 current_snapshots에서 "
            f"‘{name}’의 스냅샷 전체를 이번 장 종료 시점의 상태로 수정해 character_snapshots에 넣으세요",
        )
        character_changes.append(
            {"name": name, "change": clean_text(change.get("change"), f"delta.character_changes[{index}].change", max_bytes=360)}
        )
    character_keys = [portable_name_key(item["name"]) for item in character_changes]
    require(len(character_keys) == len(set(character_keys)), "delta.character_changes contains duplicate characters")
    foreshadow_changes = [
        normalize_foreshadow_change(
            raw, f"delta.foreshadow_changes[{index}]", allow_delete=True, through_chapter=through_chapter
        )
        for index, raw in enumerate(as_list(delta.get("foreshadow_changes", []), "delta.foreshadow_changes"))
    ]
    timeline_events = [
        normalize_timeline_change(
            raw, f"delta.timeline_events[{index}]", allow_delete=True, through_chapter=through_chapter
        )
        for index, raw in enumerate(as_list(delta.get("timeline_events", []), "delta.timeline_events"))
    ]
    require(
        len({item["id"] for item in foreshadow_changes}) == len(foreshadow_changes),
        "delta.foreshadow_changes contains duplicate IDs",
    )
    require(
        len({item["id"] for item in timeline_events}) == len(timeline_events),
        "delta.timeline_events contains duplicate IDs",
    )
    require(
        set(snapshots).issubset({item["name"] for item in character_changes}),
        "character_snapshots must contain exactly the core characters changed by this transaction",
    )
    return {
        "result": clean_text(delta.get("result"), "delta.result", max_bytes=480),
        "character_changes": character_changes,
        "foreshadow_changes": foreshadow_changes,
        "timeline_events": timeline_events,
        "constraints": clean_string_list(delta.get("constraints", []), "delta.constraints", maximum=6),
        "next_chapter_commitments": clean_string_list(
            delta.get("next_chapter_commitments", []), "delta.next_chapter_commitments", maximum=5
        ),
        "retired_context_items": clean_string_list(
            delta.get("retired_context_items", []), "delta.retired_context_items", maximum=11
        ),
        "retired_characters": retired_characters,
    }


def render_commitments(commitments: list[str]) -> list[str]:
    # 일반적으로 ‘；’로 한 줄에 잇지만 약속 원문에도 이 기호가 있으면 되돌릴 수 없으므로 항목별 들여쓰기 형식을 쓴다.
    if any("；" in item for item in commitments):
        return ["- 下一章承诺："] + [f"  - {item}" for item in commitments]
    return ["- 下一章承诺：" + ("；".join(commitments) or "无")]


def render_delta(chapter: int, title: str, delta: dict[str, Any], core_names: set[str]) -> str:
    lines = [
        f"# 第{chapter:03d}章 · {title}",
        f"- 结果：{delta['result']}",
        *render_commitments(delta["next_chapter_commitments"]),
        "",
        "## 角色变化",
    ]
    lines.extend(
        f"- {item['name']}｜{'核心' if item['name'] in core_names else '临时'}｜{item['change']}"
        for item in delta["character_changes"]
    )
    if not delta["character_changes"]:
        lines.append("- 无")
    lines.extend(["", "## 伏笔变化"])
    for item in delta["foreshadow_changes"]:
        if item["action"] == "delete":
            lines.append(f"- {item['id']}｜删除当前登记")
        else:
            planned = f"第{item['planned_resolution_chapter']}章" if item["planned_resolution_chapter"] else "未定"
            lines.append(f"- {item['id']}｜{item['status']}｜{item['summary']}｜回收{planned}")
    if not delta["foreshadow_changes"]:
        lines.append("- 无")
    lines.extend(["", "## 时间与揭示"])
    for item in delta["timeline_events"]:
        if item["action"] == "delete":
            lines.append(f"- {item['id']}｜删除当前登记")
        else:
            lines.append(
                f"- {item['id']}｜{item['story_time']}｜事实：{item['objective_fact']}｜"
                f"读者：{item['reader_knowledge']}｜{item['reveal_status']}"
            )
    if not delta["timeline_events"]:
        lines.append("- 无")
    lines.extend(["", "## 连贯性约束"])
    lines.extend(f"- {item}" for item in delta["constraints"])
    if not delta["constraints"]:
        lines.append("- 无")
    retired = delta.get("retired_context_items", []) + [
        f"角色状态：{name}" for name in delta.get("retired_characters", [])
    ]
    if retired:
        # 퇴역 항목을 여기 보관해 이어쓰기 상태 카드가 축소된 뒤에도 무엇을 내렸는지 조회할 수 있다.
        lines.extend(["", "## 本章退役登记"])
        lines.extend(f"- {item}" for item in retired)
    payload = "\n".join(lines) + "\n"
    size = byte_size(payload)
    if size > DELTA_MAX_BYTES:
        longest = sorted((line for line in lines if line.startswith("- ")), key=len, reverse=True)[:3]
        allowed = DELTA_MAX_BYTES * len(payload) // size
        raise TrackingError(
            f"chapter delta is {size} bytes; hard cap is {DELTA_MAX_BYTES}(장별 기록 현재 {len(payload)}자, "
            f"상한 약 {allowed}자, 최소 {len(payload) - allowed}자 축약 필요. 가장 긴 항목: "
            + "；".join(f"{line[2:18]}…({len(line) - 2}자)" for line in longest) + "）")
    return payload


def normalize_wordcount_records(value: object, last_chapter: int) -> dict[str, dict[str, Any]]:
    records = as_mapping(value, "tracking state.wordcount_records")
    normalized: dict[str, dict[str, Any]] = {}
    for raw_chapter, raw_record in records.items():
        require(isinstance(raw_chapter, str) and re.fullmatch(r"[1-9]\d*", raw_chapter) is not None,
                "wordcount record chapter key is invalid")
        chapter = int(raw_chapter)
        require(chapter <= last_chapter, "wordcount record exceeds last committed chapter")
        normalized[raw_chapter] = wordcount_value(wordcount_core.normalize_wordcount_record, raw_record)
    return normalized


def normalize_state(document: object) -> dict[str, Any]:
    root = as_mapping(document, "tracking state")
    require_known_keys(
        root,
        {
            "schema_version", "book_title", "last_committed_chapter", "imported_through_chapter",
            "state_revision", "context", "characters", "foreshadow", "timeline",
            "wordcount_records",
        },
        "tracking state",
    )
    require(root.get("schema_version") == TRACKING_SCHEMA_VERSION, "tracking state schema is unsupported")
    last_chapter = as_int(root.get("last_committed_chapter"), "tracking state.last_committed_chapter")
    imported_through = as_int(root.get("imported_through_chapter"), "tracking state.imported_through_chapter")
    require(imported_through <= last_chapter, "imported chapter cutoff exceeds current chapter")
    context = validate_context_input(root.get("context"), include_initial_fields=True)
    require(
        context["position"]["volume_start_chapter"] <= max(1, last_chapter),
        "context.position.volume_start_chapter is after the current writing position",
    )
    recent_numbers = [item["chapter"] for item in context["recent_chapters"]]
    require(recent_numbers == sorted(recent_numbers), "context.recent_chapters must be ordered")
    require(len(recent_numbers) == len(set(recent_numbers)), "context.recent_chapters contains duplicates")
    require(all(chapter <= last_chapter for chapter in recent_numbers), "context.recent_chapters cannot include future chapters")
    characters = normalize_snapshots(root.get("characters", {}), "tracking state.characters")
    for name in context["active_character_names"]:
        require(name in characters, f"active core character {name} has no current snapshot")
    foreshadow = normalize_foreshadow_state(root.get("foreshadow", {}), last_chapter)
    timeline = normalize_timeline_state(root.get("timeline", {}), last_chapter)
    if last_chapter == 0:
        require(not foreshadow, "a chapter-0 project cannot have planted foreshadow facts")
        require(not timeline, "a chapter-0 project cannot have established timeline facts")
    state_revision = as_int(root.get("state_revision"), "tracking state.state_revision")
    wordcount_records = normalize_wordcount_records(root.get("wordcount_records", {}), last_chapter)
    return {
        "schema_version": TRACKING_SCHEMA_VERSION,
        "book_title": clean_text(root.get("book_title"), "tracking state.book_title", max_bytes=240),
        "last_committed_chapter": last_chapter,
        "imported_through_chapter": imported_through,
        "state_revision": state_revision,
        "context": context,
        "characters": characters,
        "foreshadow": foreshadow,
        "timeline": timeline,
        "wordcount_records": wordcount_records,
    }


def load_state(project: Path) -> dict[str, Any]:
    path = state_path(project)
    require(path.exists(), "tracking state is missing; run init first")
    return normalize_state(read_json(path))


def normalize_initial_document(document: object) -> dict[str, Any]:
    root = as_mapping(document, "init input")
    require_known_keys(
        root,
        {
            "schema_version", "book_title", "last_chapter", "context", "character_snapshots",
            "foreshadow", "timeline_events",
        },
        "init input",
    )
    require(root.get("schema_version") == INPUT_SCHEMA_VERSION, "init input schema_version is unsupported")
    last_chapter = as_int(root.get("last_chapter"), "last_chapter")
    context = validate_context_input(root.get("context"), include_initial_fields=True)
    snapshots = normalize_snapshots(root.get("character_snapshots", {}))
    foreshadow: dict[str, dict[str, Any]] = {}
    for index, raw_row in enumerate(as_list(root.get("foreshadow", []), "foreshadow")):
        row = normalize_foreshadow_change(
            raw_row, f"foreshadow[{index}]", allow_delete=False, through_chapter=last_chapter
        )
        require(row["id"] not in foreshadow, f"duplicate foreshadow ID {row['id']}")
        row.pop("action")
        row["updated_chapter"] = max(1, last_chapter)
        foreshadow[row["id"]] = row
    timeline: dict[str, dict[str, Any]] = {}
    for index, raw_event in enumerate(as_list(root.get("timeline_events", []), "timeline_events")):
        event = normalize_timeline_change(
            raw_event, f"timeline_events[{index}]", allow_delete=False, through_chapter=last_chapter
        )
        require(event["id"] not in timeline, f"duplicate timeline event ID {event['id']}")
        event.pop("action")
        event["first_recorded_chapter"] = max(1, last_chapter)
        event["updated_chapter"] = max(1, last_chapter)
        timeline[event["id"]] = event
    return normalize_state(
        {
            "schema_version": TRACKING_SCHEMA_VERSION,
            "book_title": clean_text(root.get("book_title"), "book_title", max_bytes=240),
            "last_committed_chapter": last_chapter,
            "imported_through_chapter": last_chapter,
            "state_revision": 0,
            "context": context,
            "characters": snapshots,
            "foreshadow": foreshadow,
            "timeline": timeline,
            "wordcount_records": {},
        }
    )


def normalize_transaction(project: Path, state: dict[str, Any], document: object) -> dict[str, Any]:
    global _LENGTH_ISSUES
    _LENGTH_ISSUES = []
    try:
        transaction = _normalize_transaction(project, state, document)
    finally:
        issues, _LENGTH_ISSUES = _LENGTH_ISSUES, None
    require(not issues, f"{len(issues)}개 필드가 길이 한도를 초과했습니다. 모두 수정한 뒤 제출하세요: " + "；".join(issues))
    return transaction


# 이 파일은 story-long-write / story-review / story-import에서 동일하다. storyctl.py는 story-long-write에만 있다.
RECOUNT_HINT = ("수정본은 story-long-write의 storyctl.py chapter commit으로 "
                "같은 트랜잭션을 제출하세요(분량 범위 밖이면 chapter accept-current-length 사용). 글자 수를 다시 계산하고 이번 장 작업 폴더를 정리합니다")


def _normalize_transaction(project: Path, state: dict[str, Any], document: object) -> dict[str, Any]:
    root = as_mapping(document, "transaction")
    require_known_keys(
        root,
        {
            "schema_version", "mode", "chapter", "chapter_title", "expected_state_revision",
            "delta", "context", "character_snapshots", "wordcount",
        },
        "transaction",
    )
    require(root.get("schema_version") == INPUT_SCHEMA_VERSION, "transaction schema_version is unsupported")
    mode = clean_text(root.get("mode"), "mode", max_bytes=24)
    require(mode in {"append", "revision"}, "mode must be append or revision")
    chapter = as_int(root.get("chapter"), "chapter", minimum=1)
    expected_revision = as_int(root.get("expected_state_revision"), "expected_state_revision")
    wordcount_input = root.get("wordcount")
    require(expected_revision == state["state_revision"], "tracking state changed since this transaction was prepared")
    last = state["last_committed_chapter"]
    if mode == "append":
        require(chapter == last + 1, f"append chapter must be {last + 1}, got {chapter}")
    else:
        require(chapter <= last, f"cannot revise unwritten chapter {chapter}; last committed chapter is {last}")
    context = validate_context_input(root.get("context"), include_initial_fields=False)
    snapshots = normalize_snapshots(root.get("character_snapshots", {}))
    existing_names = {portable_name_key(name): name for name in state["characters"]}
    for name in snapshots:
        existing = existing_names.get(portable_name_key(name))
        require(existing is None or existing == name, f"character {name} conflicts with existing character {existing}")
    through_chapter = chapter if mode == "append" else last
    delta = normalize_delta(
        root.get("delta"),
        through_chapter=through_chapter,
        snapshots=snapshots,
        existing_core_names=existing_names,
    )
    wordcount = None
    if wordcount_input is not None:
        wordcount = wordcount_value(
            wordcount_core.validate_current_wordcount_record, project, chapter, wordcount_input
        )
    elif mode == "revision" and str(chapter) in state["wordcount_records"]:
        # 글자 수 기록을 제출한 장에서 본문·목표 변경 후 storyctl을 우회해 수정 제출하면 actual/body_sha256이 오래된 값으로 남는다.
        # 기록에 고정된 본문과 목표만 대조한다. 나중에 상세 개요에 추가한 ‘字数范围’는 만료로 보지 않는다.
        try:
            drift = wordcount_core.wordcount_record_drift(project, chapter, state["wordcount_records"][str(chapter)])
        except wordcount_core.WordcountError as exc:
            raise TrackingError(f"제{chapter}장의 분량 기록을 대조할 수 없습니다({exc}). {RECOUNT_HINT}") from exc
        if drift:
            raise TrackingError(f"제{chapter}장의 {', '.join({'正文': '본문', '字数目标': '목표 분량'}.get(item, item) for item in drift)}이(가) 변경되었습니다. {RECOUNT_HINT}")
    return {
        "mode": mode,
        "chapter": chapter,
        "title": clean_text(root.get("chapter_title"), "chapter_title", max_bytes=240),
        "delta": delta,
        "context": context,
        "snapshots": snapshots,
        "wordcount": wordcount,
    }


def checkpoint_record(
    change: dict[str, Any], chapter: int, previous: dict[str, Any] | None, *, keep_first_chapter: bool = False
) -> dict[str, Any]:
    current = {key: value for key, value in change.items() if key != "action"}
    current["updated_chapter"] = max(previous["updated_chapter"] if previous else chapter, chapter)
    if keep_first_chapter:
        current["first_recorded_chapter"] = previous["first_recorded_chapter"] if previous else chapter
    return current


def merge_transaction(state: dict[str, Any], transaction: dict[str, Any]) -> dict[str, Any]:
    next_state = copy.deepcopy(state)
    chapter = transaction["chapter"]
    if transaction["mode"] == "append":
        next_state["last_committed_chapter"] = chapter
    next_state["state_revision"] += 1
    next_state["characters"].update(transaction["snapshots"])
    if transaction["wordcount"] is not None:
        next_state["wordcount_records"][str(chapter)] = transaction["wordcount"]

    next_context = transaction["context"]
    # 퇴역은 지금부터 현재 상태에서 빠진다는 뜻이다. append의 장별 기록만 현재 시점을 나타내며
    # 수정 기록은 과거 장에 속하므로 거기에 넣으면 퇴역 발생 장을 잘못 보고하게 된다.
    is_revision = transaction["mode"] == "revision"
    require(
        not (is_revision and transaction["delta"]["retired_characters"]),
        "retired_characters must be committed in an append transaction, not a revision",
    )
    for name in transaction["delta"]["retired_characters"]:
        require(name in next_state["characters"], f"retired character {name} has no current snapshot")
        require(
            name not in transaction["snapshots"],
            f"character {name} cannot be retired and updated in the same transaction",
        )
        require(
            name not in next_context["active_character_names"],
            f"retired character {name} is still listed in context.active_character_names",
        )
        next_state["characters"].pop(name)

    # 컨텍스트 항목은 통째로 제출한다. 누락하면 과거 판정이 조용히 사라지므로 제거를 명시해야 한다.
    previous_items = set(state["context"]["long_term_constraints"]) | set(state["context"]["continuity_risks"])
    dropped = previous_items - (set(next_context["long_term_constraints"]) | set(next_context["continuity_risks"]))
    require(
        not (is_revision and dropped),
        "a revision must resubmit every current context item; retire them in an append transaction instead: "
        + "；".join(sorted(dropped)),
    )
    kept = set(next_context["long_term_constraints"]) | set(next_context["continuity_risks"])
    still_listed = sorted(set(transaction["delta"]["retired_context_items"]) & kept)
    require(
        not still_listed,
        "delta.retired_context_items lists items that are still in context; remove them from context: "
        + "；".join(still_listed),
    )
    undeclared = sorted(dropped - set(transaction["delta"]["retired_context_items"]))
    require(
        not undeclared,
        "context items were dropped without being declared in delta.retired_context_items: "
        + "；".join(undeclared),
    )
    transaction["delta"]["retired_context_items"] = sorted(dropped)

    for change in transaction["delta"]["foreshadow_changes"]:
        if change["action"] == "delete":
            next_state["foreshadow"].pop(change["id"], None)
        else:
            next_state["foreshadow"][change["id"]] = checkpoint_record(
                change, chapter, next_state["foreshadow"].get(change["id"])
            )
    for change in transaction["delta"]["timeline_events"]:
        if change["action"] == "delete":
            next_state["timeline"].pop(change["id"], None)
        else:
            next_state["timeline"][change["id"]] = checkpoint_record(
                change, chapter, next_state["timeline"].get(change["id"]), keep_first_chapter=True
            )

    recent_by_chapter = {item["chapter"]: item for item in state["context"]["recent_chapters"]}
    if chapter in recent_by_chapter or transaction["mode"] == "append":
        recent_by_chapter[chapter] = {"chapter": chapter, "summary": transaction["delta"]["result"]}
    recent = sorted(recent_by_chapter.values(), key=lambda item: item["chapter"])[-3:]
    current_last = next_state["last_committed_chapter"]
    next_commitments = (
        transaction["delta"]["next_chapter_commitments"]
        if transaction["mode"] == "append" or chapter == current_last
        else state["context"]["next_chapter_commitments"]
    )
    next_state["context"] = {
        **next_context,
        "recent_chapters": recent,
        "next_chapter_commitments": next_commitments,
    }
    return normalize_state(next_state)


def render_views(state: dict[str, Any]) -> dict[str, str]:
    revision = state["state_revision"]
    views = {
        "문맥.md": render_context(state),
        "복선.md": render_foreshadow(state["foreshadow"], revision),
    }
    author, reader = render_timeline_views(state["timeline"], revision)
    views["시간선/작가용진실.md"] = author
    views["시간선/독자가아는사실.md"] = reader
    for name, snapshot in state["characters"].items():
        views[f"인물상태/{name}.md"] = render_snapshot(
            name, snapshot, state["last_committed_chapter"], revision
        )
    return views


def write_views(tracking: Path, views: dict[str, str]) -> None:
    # 컨텍스트는 다음 리비전을 담으므로 먼저 쓴다. 이후 실패하면 hook/check가
    # 컨텍스트 리비전과 마지막 제출 _tracking-state.json의 불일치를 감지한다.
    write_if_changed(tracking / "문맥.md", views["문맥.md"])
    for relative in sorted(path for path in views if path != "문맥.md"):
        write_if_changed(tracking / relative, views[relative])
    expected_character_files = {
        Path(relative).name for relative in views if relative.startswith("인물상태/")
    }
    character_dir = tracking / "인물상태"
    character_dir.mkdir(parents=True, exist_ok=True)
    for path in character_dir.glob("*.md"):
        if path.name not in expected_character_files:
            path.unlink()


def warn_sizes(views: dict[str, str], delta_payload: str | None = None) -> None:
    if delta_payload is not None and byte_size(delta_payload) > DELTA_TARGET_BYTES:
        emit(
            f"WARNING: chapter delta is {byte_size(delta_payload)} bytes; target is <= {DELTA_TARGET_BYTES}",
            error=True,
        )
    context_size = byte_size(views["문맥.md"])
    if context_size > CONTEXT_TARGET_BYTES:
        emit(f"WARNING: hot context is {context_size} bytes; target is <= {CONTEXT_TARGET_BYTES}", error=True)
    for relative, payload in views.items():
        if not relative.startswith("인물상태/"):
            continue
        size = byte_size(payload)
        if size > SNAPSHOT_TARGET_BYTES:
            emit(
                f"WARNING: character snapshot {Path(relative).stem} is {size} bytes; target is <= {SNAPSHOT_TARGET_BYTES}",
                error=True,
            )


def _initialize_locked(project: Path, document: object) -> dict[str, Any]:
    tracking = tracking_root(project)
    require(not state_path(project).exists(), "tracking state already exists; init never overwrites project state")
    state = normalize_initial_document(document)
    views = render_views(state)
    state_payload = json_payload(state)

    # 입력 검증을 모두 통과한 후 사용자 파일을 건드린다. 실패한 init은 어떤 파일도 옮기지 않는다.
    archived = archive_retired_tracking_paths(tracking)
    for directory in (tracking / "장별기록", tracking / "인물상태", tracking / "시간선"):
        directory.mkdir(parents=True, exist_ok=True)
    write_views(tracking, views)
    atomic_write_text(state_path(project), state_payload)
    warn_sizes(views)
    if archived:
        emit(
            f"NOTE: 이전 추적 구조를 그대로 추적/{RETIRED_ARCHIVE_DIR}/에 옮겼습니다: {', '.join(archived)}. "
            "현재 상태는 이번 init 입력을 기준으로 하며 이전 파일은 해석에 사용하지 않습니다.",
            error=True,
        )
    return state


def initialize(project: Path, document: object) -> dict[str, Any]:
    with project_write_lock(project):
        return _initialize_locked(project, document)


def _apply_transaction_locked(project: Path, document: object) -> dict[str, Any]:
    tracking = tracking_root(project)
    require_no_retired_tracking_paths(tracking)
    state = load_state(project)
    transaction = normalize_transaction(project, state, document)
    next_state = merge_transaction(state, transaction)
    path = delta_path(tracking, transaction["chapter"])
    previous_record = parse_chapter_record(path) if transaction["mode"] == "revision" else None
    if previous_record is not None:
        # 퇴역은 append에서만 발생한다. 수정 시 과거 퇴역 등록을 그대로 가져와 사라지지 않게 한다.
        transaction["delta"]["retired_context_items"] = previous_record["retired"]

    delta_payload = render_delta(
        transaction["chapter"],
        transaction["title"],
        transaction["delta"],
        # 이번 장에 퇴역한 인물은 next_state에서 삭제되었어도 이번 장 기록에서는 여전히 핵심 인물로 표시해야 한다.
        set(next_state["characters"]) | set(transaction["delta"]["retired_characters"]),
    )
    views = render_views(next_state)
    next_state_payload = json_payload(next_state)
    if transaction["mode"] == "append" and path.exists():
        require(
            path.read_text(encoding="utf-8") == delta_payload,
            f"chapter delta {transaction['chapter']} already exists with different content",
        )

    write_if_changed(path, delta_payload)
    write_views(tracking, views)
    # 유일한 기준 파일은 마지막에 저장한다. 그전 실패는 같은 트랜잭션으로 바로 재시도할 수 있다.
    atomic_write_text(state_path(project), next_state_payload)
    warn_sizes(views, delta_payload)
    if previous_record is not None:
        warn_emptied_record(transaction["chapter"], previous_record, transaction["delta"])
    return next_state


def warn_emptied_record(chapter: int, previous: dict[str, Any], delta: dict[str, Any]) -> None:
    labels = {"character_changes": "角色变化", "foreshadow_changes": "伏笔变化", "timeline_events": "时间与揭示",
              "constraints": "连贯性约束", "next_chapter_commitments": "下一章承诺"}
    emptied = [f"{label}(기존 {len(previous[key])}개 항목)" for key, label in labels.items()
               if previous[key] and not delta[key]]
    if emptied:
        emit(f"WARNING: 제{chapter}장 수정으로 장별 기록에서 다음 항목을 비웠습니다: " + "、".join(emptied)
             + ". 수정의 delta에는 이번 장의 전체 기록이 필요합니다. 의도한 삭제가 아니라면 draft로 다시 미리 채운 뒤 제출하세요.", error=True)


def apply_transaction(project: Path, document: object) -> dict[str, Any]:
    with project_write_lock(project):
        return _apply_transaction_locked(project, document)


def check_project(project: Path) -> dict[str, Any]:
    tracking = tracking_root(project)
    require_no_retired_tracking_paths(tracking)
    state = load_state(project)
    last_chapter = state["last_committed_chapter"]
    required_delta_start = state["imported_through_chapter"] + 1
    for chapter in range(required_delta_start, last_chapter + 1):
        require(delta_path(tracking, chapter).exists(), f"chapter delta {chapter} is missing")
    for path in (tracking / "장별기록").glob("제*장.md"):
        match = re.fullmatch(r"제(\d+)장\.md", path.name)
        require(match is not None, f"chapter delta has an invalid filename: {path.name}")
        chapter = as_int(int(match.group(1)), f"chapter delta {path.name}", minimum=1)
        require(path == delta_path(tracking, chapter), f"chapter delta {chapter} filename is not canonical")
        require(chapter <= last_chapter, f"chapter delta {chapter} exceeds last_committed_chapter")
        require(path.stat().st_size <= DELTA_MAX_BYTES, f"chapter delta {chapter} exceeds {DELTA_MAX_BYTES} bytes")

    expected_views = render_views(state)
    for relative, expected in expected_views.items():
        path = tracking / relative
        require(path.exists(), f"derived view is missing: {relative}")
        require(
            path.read_text(encoding="utf-8") == expected,
            f"derived view differs from _tracking-state.json: {relative}",
        )
    expected_character_files = {
        Path(relative).name for relative in expected_views if relative.startswith("인물상태/")
    }
    actual_character_files = {path.name for path in (tracking / "인물상태").glob("*.md")}
    require(actual_character_files == expected_character_files, "character snapshot files differ from tracking state")
    return state


# 트랜잭션 초안의 텍스트별 글자 수 상한(전부 중국어라 가정해 UTF-8 글자당 3바이트)을 안내에 써 모델의 반복 시행착오를 줄인다.
DRAFT_LIMITS = {
    "delta.result": 160, "character_changes[].change": 120, "foreshadow_changes[].summary": 120,
    "timeline_events[].objective_fact / reader_knowledge": 160, "context.position.story_time / scene": 80,
    "character_snapshots.*.goal / state": 100, "逐章记录总量": 1024,
}


RECORD_SECTIONS = {"角色变化": "character_changes", "伏笔变化": "foreshadow_changes",
                   "时间与揭示": "timeline_events", "连贯性约束": "constraints", "本章退役登记": "retired"}


def parse_chapter_record(path: Path) -> dict[str, Any] | None:
    """도구가 생성한 장별 기록(render_delta의 고정 형식)을 다시 읽어 수정 초안 채우기와 제출 대조에 사용한다.
    수기 Markdown 파싱이 아닌 자체 결정적 출력의 역연산이며 읽지 못하면 None이다."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    record: dict[str, Any] = {"title": "", "result": "", "next_chapter_commitments": [],
                              **{key: [] for key in RECORD_SECTIONS.values()}}
    section = None
    in_commitments = False
    for line in text.splitlines():
        heading = re.match(r"^# 第\d+章 · (.+)$", line)
        if heading and not record["title"]:
            record["title"] = heading.group(1).strip()
            continue
        if line.startswith("## "):
            section = RECORD_SECTIONS.get(line[3:].strip())
            in_commitments = False
            continue
        if in_commitments and line.startswith("  - "):
            record["next_chapter_commitments"].append(line[4:])
            continue
        in_commitments = False
        if not line.startswith("- "):
            continue
        item = line[2:]
        if section is None:
            if item.startswith("结果："):
                record["result"] = item[len("结果："):]
            elif item.startswith("下一章承诺："):
                value = item[len("下一章承诺："):]
                # 빈 값은 항목별 하위 목록 형식(render_commitments)이며 뒤의 들여쓴 행을 개별 항목으로 읽는다.
                in_commitments = value == ""
                record["next_chapter_commitments"] = [] if value in ("无", "") else value.split("；")
            continue
        if item == "无" and section != "retired":
            continue
        record[section].append(item)
    return record


def record_prefill(state: dict[str, Any], record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """제출된 장별 기록을 수정 delta로 복원한다. 결과·약속·제약·인물 변화는 원문을 사용하고 복선·시간선은 영향받은 ID의 현재 값을 쓴다.
    수정 제출은 최신 장까지의 현재 값이다. 기록 속 핵심 인물의 현재 스냅샷도 반환한다."""
    notes: list[str] = []
    changes = []
    for line in record["character_changes"]:
        parts = line.split("｜", 2)
        if len(parts) == 3:
            changes.append({"name": parts[0], "change": parts[2]})
    snapshots = {item["name"]: copy.deepcopy(state["characters"][item["name"]])
                 for item in changes if item["name"] in state["characters"]}

    def rows(lines: list[str], current: dict[str, Any], label: str) -> list[dict[str, Any]]:
        prefilled = []
        for line in lines:
            parts = line.split("｜")
            identifier = parts[0]
            if len(parts) > 1 and parts[1] == "删除当前登记":
                if identifier in current:
                    notes.append(f"{label} {identifier}은(는) 이번 장에서 삭제한 뒤 다시 등록되어 삭제를 미리 채우지 않았습니다. 삭제가 필요하면 직접 추가하세요")
                else:
                    prefilled.append({"action": "delete", "id": identifier})
            elif identifier in current:
                prefilled.append({"action": "upsert", **{key: copy.deepcopy(value) for key, value in current[identifier].items()
                                                         if key not in ("updated_chapter", "first_recorded_chapter")}})
            else:
                notes.append(f"{label} {identifier}은(는) 이후 장에서 삭제되어 미리 채우지 않았습니다")
        return prefilled

    delta = {
        "result": record["result"],
        "character_changes": changes,
        "foreshadow_changes": rows(record["foreshadow_changes"], state["foreshadow"], "伏笔"),
        "timeline_events": rows(record["timeline_events"], state["timeline"], "时间线事件"),
        "constraints": list(record["constraints"]),
        "next_chapter_commitments": list(record["next_chapter_commitments"]),
    }
    return delta, snapshots, notes


def entry_shapes(chapter: int) -> dict[str, Any]:
    """draft에서 항목별 형식을 즉시 제공한다. 빈 배열만 있으면 모델이 필드 이름·정수·열거형을 추측해 첫 제출이 거의 모두 반려된다.
    값은 검증과 같은 상수에서 생성하며 별도 체계를 만들지 않는다."""
    return {
        "delta.character_changes[]": {"name": "인물명", "change": "이번 장에서 일어난 변화를 한 문장으로 작성"},
        "delta.foreshadow_changes[]": {
            "action": "upsert(전체 항목을 없애려면 delete로 적고 id만 포함)", "id": "F007", "summary": "복선을 한 문장으로 작성",
            "planted_chapter": chapter, "planned_resolution_chapter": "계획된 회수 장 번호를 정수로 작성. 미정이면 null",
            "status": "|".join(FORESHADOW_STATUSES), "importance": "|".join(FORESHADOW_IMPORTANCE),
        },
        "delta.timeline_events[]": {
            "action": "upsert(전체 항목을 없애려면 delete로 적고 id만 포함)", "id": "E012", "story_time": "작품 속 시간",
            "objective_fact": "객관적으로 일어난 사건", "reader_knowledge": "독자가 현재 알고 있거나 믿는 내용",
            "reveal_status": "|".join(REVEAL_STATUSES),
            "reveal_chapter": f"공개 또는 일부 공개라면 공개 장 번호를 정수로 작성({chapter}장 이하). 미공개면 null",
            "characters": ["인물명"],
        },
        "character_snapshots.{인물명}": {
            **{key: "한 문장" for key in SNAPSHOT_TEXT_FIELDS},
            **{key: ["항목당 한 문장"] for key in SNAPSHOT_LIST_FIELDS},
        },
    }


def draft_transaction(project: Path, chapter: int) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """현재 state로 장별 트랜잭션의 리비전·모드·장 제목·전체 제출 컨텍스트를 미리 채운다.
    새 장(append)은 호출자가 이번 변화만 쓴다. 현장 핵심 인물의 현재 스냅샷도 반환해 변화가 있으면 전체를 고쳐 넣게 한다.
    새 장의 시간·장면은 장 끝 위치여야 하므로 비운다. 이전 값을 그대로 제출하는 실수를 막고 이전 값은 별도 참고로 반환한다.
    수정(revision)의 delta는 수정 후 장 전체 기록이므로 제출된 장별 기록으로 채워 호출자가 수정한다.
    세 번째 반환값 {"notes": [...], "prefilled": bool}은 채우지 못한 항목과 장별 기록 읽기 성공 여부다."""
    state = load_state(project)
    last = state["last_committed_chapter"]
    require(1 <= chapter <= last + 1, f"draft chapter must be between 1 and {last + 1}")
    mode = "append" if chapter == last + 1 else "revision"
    title = ""
    for outline in sorted((project / "개요").glob(f"상세개요_제{chapter:03d}장*.md")):
        match = re.search(rf"^#{{1,4}}\s*(?:第|제)\s*0*{chapter}\s*(?:章|장)\s*[：:]\s*(.+?)\s*$",
                          outline.read_text(encoding="utf-8"), re.M)
        if match:
            title = match.group(1).strip()
            break
    context = json.loads(json.dumps(state["context"], ensure_ascii=False))
    previous_position = {key: context["position"][key] for key in ("story_time", "scene")}
    delta: dict[str, Any] = {
        "result": "", "character_changes": [], "foreshadow_changes": [], "timeline_events": [],
        "constraints": [], "next_chapter_commitments": [],
    }
    snapshots_prefill: dict[str, Any] = {}
    notes: list[str] = []
    prefilled = False
    if mode == "append":
        delta.update({"retired_context_items": [], "retired_characters": []})
        context["position"].update({"story_time": "", "scene": ""})
    else:
        record = parse_chapter_record(delta_path(tracking_root(project), chapter))
        if record is not None:
            prefilled = True
            delta, snapshots_prefill, notes = record_prefill(state, record)
            title = title or record["title"]
            if chapter == last:
                # 최신 장의 약속은 state에 그대로 있어 기록 행을 ‘；’로 나누는 것보다 정확하다.
                delta["next_chapter_commitments"] = list(state["context"]["next_chapter_commitments"])
    document = {
        "schema_version": INPUT_SCHEMA_VERSION,
        "mode": mode,
        "chapter": chapter,
        "chapter_title": title,
        "expected_state_revision": state["state_revision"],
        "delta": delta,
        "context": {key: context[key] for key in
                    ("position", "long_term_constraints", "active_character_names", "continuity_risks")},
        "character_snapshots": snapshots_prefill,
    }
    snapshots = {name: state["characters"][name] for name in context["active_character_names"]
                 if name in state["characters"]}
    if mode == "revision":
        return document, snapshots, {"notes": notes, "prefilled": prefilled}
    return document, snapshots, previous_position


def rebuild_stale_draft(document: dict[str, Any], existing: dict[str, Any], append: bool,
                        current_characters: Any = ()) -> str:
    """리비전 변경은 다른 트랜잭션 제출을 뜻한다. 현재 상태를 바탕으로 안전한 부분만 자동 병합하고 나머지는 호출자에게 대조 목록을 준다.

    새 장 초안 사이에는 수정만 끼어들 수 있고 수정은 제약·위험을 삭제하지 못한다. 따라서 현재 제약·위험으로 이전 바탕을 덮는다.
    이전 초안에만 있는 항목은 이번 추가이며 delta의 퇴역 선언은 이번 삭제이므로 정확히 병합할 수 있다.
    수정 초안 사이에는 퇴역 가능한 새 장이 들어오거나 현장 인물명이 수정으로 삭제될 수 있어 어느 것이 최신인지 판단할 수 없다.
    현재 상태를 취하고 차이를 열거한다. 이번 장에 스냅샷이 있는 새 인물명만 자동으로 되살린다."""
    def items(value: object) -> list[str]:
        return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []

    def norm(item: str) -> str:
        return " ".join(item.replace("|", "｜").split())

    notes = ["리비전이 변경되었습니다. 현재 상태로 context를 재구성하고 이번 장에 작성한 delta" + (", 추가·종료한 제약, 종료 위치" if append else "")
             + "를 병합했습니다"]
    for key in ("delta", "character_snapshots"):
        if isinstance(existing.get(key), dict):
            document[key] = existing[key]
    if existing.get("chapter_title"):
        document["chapter_title"] = existing["chapter_title"]
    old_context = existing.get("context") if isinstance(existing.get("context"), dict) else {}
    delta = document["delta"] if isinstance(document["delta"], dict) else {}
    context = document["context"]
    retired = {norm(item) for item in items(delta.get("retired_context_items"))}
    left_out: list[str] = []
    for key in ("long_term_constraints", "continuity_risks"):
        current = {norm(item) for item in context[key]}
        extra = []
        for item in items(old_context.get(key)):
            if norm(item) not in current:
                current.add(norm(item))
                extra.append(item)
        if append:
            context[key] = [item for item in context[key] if norm(item) not in retired] + extra
        else:
            left_out += extra
    snapshots = document["character_snapshots"] if isinstance(document["character_snapshots"], dict) else {}
    names = context["active_character_names"]
    for name in items(old_context.get("active_character_names")):
        if name in names:
            continue
        if append and name in snapshots:
            names.append(name)
        else:
            left_out.append(f"등장 인물 {name}")
    names[:] = [name for name in names if name not in set(items(delta.get("retired_characters")))]
    known = set(current_characters)
    for name in list(snapshots):
        if name not in known and name not in names:
            snapshots.pop(name)
            left_out.append(f"인물 스냅샷 {name}")
    if left_out:
        notes.append("초안에만 있고 현재 상태에는 없는 항목은 자동 복원하지 않았습니다(다른 제출에서 종료했을 수 있음). 이번 장에 필요하면 직접 복원하세요: "
                     + "；".join(left_out))
    old_position = old_context.get("position") if isinstance(old_context.get("position"), dict) else {}
    position = context["position"]
    if append:
        for key in ("story_time", "scene"):
            if isinstance(old_position.get(key), str) and old_position[key].strip():
                position[key] = old_position[key]
    differs = [f"{key}: 초안은 ‘{old_position[key]}’, 현재 상태는 ‘{position[key]}’"
               for key in ("volume", "volume_start_chapter")
               if key in old_position and old_position[key] != position[key]]
    if differs:
        notes.append("권 정보가 달라 현재 상태를 적용했습니다. 이번 장에서 실제로 권이 바뀐다면 수정하세요(" + "；".join(differs) + "）")
    if snapshots:
        notes.append("가져온 인물 스냅샷(" + "、".join(snapshots) + ")은 중간 제출로 바뀌었을 수 있습니다. current_snapshots와 하나씩 대조하세요")
    return "；".join(notes)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "commit"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--project", type=Path, required=True, help="book project root containing 추적/")
        subparser.add_argument("--input", type=Path, required=True, help="UTF-8 JSON input document")
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--project", type=Path, required=True, help="book project root containing 추적/")
    draft_parser = subparsers.add_parser("draft", help="write a pre-filled chapter transaction to fill in")
    draft_parser.add_argument("--project", type=Path, required=True, help="book project root containing 추적/")
    draft_parser.add_argument("--chapter", type=int, required=True)
    draft_parser.add_argument("--out", type=Path, help="default: <project>/.story/work/제NNN장/tracking.json")
    draft_parser.add_argument("--force", action="store_true",
                              help="discard an existing draft instead of only refreshing its revision")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "draft":
            document, snapshots, extra = draft_transaction(args.project, args.chapter)
            previous_position = extra if document["mode"] == "append" else {}
            prefill_notes = extra.get("notes", []) if document["mode"] == "revision" else []
            record_prefilled = bool(extra.get("prefilled")) if document["mode"] == "revision" else False
            out = args.out or args.project / ".story" / "work" / f"제{args.chapter:03d}장" / "tracking.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            refreshed = ""
            if out.exists() and not args.force:
                # draft 재실행은 이미 입력한 변화를 지우지 않는다. 리비전이 바뀌었으면 다른 트랜잭션이 제출된 것이므로 context는 현재
                # 상태로 재구성한다. 이전 context를 쓰면 그 변경 전체를 덮어쓰므로 이번 장에서 직접 입력한 부분만 가져온다.
                existing = read_json(out)
                require(isinstance(existing, dict) and existing.get("chapter") == document["chapter"]
                        and existing.get("mode") == document["mode"],
                        f"{out} already holds a draft for a different chapter or mode; pass --force to replace it")
                if existing.get("expected_state_revision") == document["expected_state_revision"]:
                    document, refreshed = existing, "기존 초안이 있고 리비전이 같아 그대로 유지했습니다"
                else:
                    refreshed = rebuild_stale_draft(document, existing, bool(previous_position),
                                                    load_state(args.project)["characters"])
            out.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            if document["mode"] == "revision" and not record_prefilled:
                fill = (f"수정 작업이지만 이번 장의 장별 기록이 없거나 읽을 수 없어({delta_path(Path('추적'), args.chapter).as_posix()}) delta를 미리 채우지 못했습니다: "
                        "수정한 본문에 따라 이번 장의 전체 기록(결과·약속·인물 변화·복선·시간선·제약)을 작성하세요. 적지 않은 항목은 기록되지 않습니다. "
                        "인물 스냅샷·복선·시간선은 최신 집필 장까지 반영한 현재 값을 쓰세요. context의 현재 항목은 모두 그대로 유지하세요(수정 시 종료 처리 불가). "
                        "본문을 수정했다면 story-long-write의 storyctl.py chapter commit으로 제출하세요(재계산 후 이번 장 작업 폴더 정리). "
                        "형식을 찾으려고 스크립트 소스나 state 파일을 따로 읽지 마세요.")
            elif document["mode"] == "revision":
                fill = ("수정 작업입니다. delta는 수정 후 이번 장의 전체 기록이며 기존 장별 기록으로 미리 채웠습니다(복선·시간선은 현재 값 사용, "
                        "기록의 핵심 인물 스냅샷은 character_snapshots에 포함). 수정 본문과 항목별로 대조해 여전히 유효한 것은 유지하고, "
                        "뒤집힌 것은 삭제·수정하며 새 항목은 보완하세요. 모두 비운 뒤 변경분만 적으면 빠진 항목이 이번 장 기록에서 사라집니다. "
                        "인물 스냅샷·복선·시간선은 최신 집필 장까지 반영한 현재 값으로 수정하세요. context의 현재 항목은 모두 유지하세요(수정 시 종료 처리 불가). "
                        "본문을 수정했다면 story-long-write의 storyctl.py chapter commit으로 제출하세요(재계산 후 이번 장 작업 폴더 정리). "
                        "형식을 찾으려고 스크립트 소스나 state 파일을 따로 읽지 마세요.")
                if prefill_notes:
                    fill += "미리 채우지 못한 항목: " + "；".join(prefill_notes) + "。"
            else:
                fill = ("delta에는 이번 장의 변화만 작성하세요. context의 나머지 필드는 현재 값입니다. 종료할 장기 제약·연속성 위험은 context에서 삭제하고 원문을 "
                        "delta.retired_context_items에 넣으세요(append만 가능). 이번 장에 변화한 핵심 인물은 아래 현재 스냅샷 전체를 수정해 character_snapshots에 넣고, "
                        "character_changes에 변화를 한 문장으로 적으세요. 항목별 형식은 shapes를 따르며 소스나 state 파일에서 따로 찾지 마세요.")
            blank = not (document["context"]["position"].get("story_time") or document["context"]["position"].get("scene"))
            if previous_position and blank:
                fill = ("context.position의 story_time과 scene은 비워 두었습니다. 이번 장 종료 시점의 시간과 장면을 입력하세요(앞 장 종료 시점은 "
                        "previous_position 참조. 권을 바꾸면 volume과 volume_start_chapter도 함께 수정). ") + fill
            payload = {
                "draft": str(out),
                "mode": document["mode"],
                "expected_state_revision": document["expected_state_revision"],
                "fill": (f"{refreshed}. 처음부터 다시 생성하려면 --force를 추가하세요." if refreshed else "") + fill,
                "limits_chars": DRAFT_LIMITS,
                "shapes": entry_shapes(args.chapter),
                "current_snapshots": snapshots,
            }
            if previous_position:
                payload["previous_position"] = previous_position
            emit(json.dumps(payload, ensure_ascii=False))
            return 0
        if args.command == "init":
            result = initialize(args.project, read_json(args.input))
        elif args.command == "commit":
            result = apply_transaction(args.project, read_json(args.input))
        else:
            result = check_project(args.project)
    except (TrackingError, OSError, UnicodeError) as exc:
        emit(f"ERROR: {exc}", error=True)
        return 2
    emit(
        json.dumps(
            {
                "last_committed_chapter": result["last_committed_chapter"],
                "state_revision": result["state_revision"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
