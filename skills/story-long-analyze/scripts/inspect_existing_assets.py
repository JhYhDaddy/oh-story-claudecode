#!/usr/bin/env python3
"""사용자 파일을 변경하지 않고 재사용 가능한 장편 분석 자산을 검사한다.
``장별분석/제N장_요약.md``, 황금 3장 분석, 집계 파일이라는 원래 디렉터리 계약만 인식한다.
누락 장을 정확히 보고해 빠진 부분만 채우게 한다.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable


SUMMARY_RE = re.compile(r"^제0*(\d+)장_요약\.md$")
GOLDEN_RE = re.compile(r"^제0*(\d+)장_심층분석\.md$")
SCHEMA_RE = re.compile(r"schema_version\s*[：:]\s*v?(\d+)", re.IGNORECASE)
TOTAL_RE = re.compile(r"总章数\s*(?:[：:]|\|)\s*(\d+)")
TOTAL_FALLBACK_RE = re.compile(r"总章数\s+(\d+)\s*章?")
TABLE_CHAPTER_TOTAL_RE = re.compile(r"\|\s*章节数\s*\|\s*(\d+)\s*(?:章)?\s*\|")
COVERAGE_TOTAL_RE = re.compile(
    r"(?:输入覆盖\s*[：:]\s*全文|精读覆盖\s*[：:]\s*第\s*1\s*[—–-]\s*)(\d+)\s*章"
)
FINAL_RE = re.compile(r"(?:最终状态|当前状态)\s*[：:]\s*([a-z0-9_]+)", re.IGNORECASE)
SOURCE_HASH_RE = re.compile(
    r"(?:输入版本|SHA-256|source_sha256)\s*(?:[：:]|\|)\s*([0-9a-f]{64})", re.IGNORECASE
)
PROJECTION_RE = re.compile(
    r"<!--\s*story-long-analyze:projection\s+runtime=(?P<runtime>[^\s]+)\s+"
    r"source=(?P<source>[^\s]+)(?:\s+[^>]*?)?\s*-->"
)
STATE_START = "<!-- story-long-analyze:runtime-state:start -->"
STATE_END = "<!-- story-long-analyze:runtime-state:end -->"
# v0.7.x는 _progress.md에 ‘章节边界’ 표(章号 | 标题 | 起始行 | 字数)를 기록했다.
BOUNDARY_HEADING_RE = re.compile(r"^#{1,6}\s*章节边界")
TITLE_LABEL_RE = re.compile(
    r"^\s*(?:第(?P<number>[〇零一二三四五六七八九十百千万两0-9]+)章|第[〇零一二三四五六七八九十百千万两0-9]+[卷回节]"
    r"|卷[〇零一二三四五六七八九十百千万两0-9]+|Chapter\s*(?P<english>[0-9]+)|(?P<numeric>[0-9]+)[.、](?![0-9])"
    r"|(?P<special>楔子|序章|引子|前言|后记|尾声|番外[〇零一二三四五六七八九十百千万两0-9]*))",
    re.IGNORECASE,
)
# 제목에 붙인 작가 메모. 예: ‘（求收藏）’, ‘【二合一】’.
TITLE_NOTE_RE = re.compile(r"[(\[【〔〖][^()\[\]【】〔〕〖〗]*[)\]】〕〗]\s*$")
TITLE_NOISE_RE = re.compile(r"[\s\-—:：、.,;!?\"“”'‘’《》「」『』()\[\]【】〔〕〖〗]+")


def nonempty(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def any_nonempty(paths: Iterable[Path]) -> bool:
    return any(nonempty(path) for path in paths)


def read_text(path: Path) -> str | None:
    if not nonempty(path):
        return None
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return None


def read_progress(path: Path) -> tuple[int | None, int | None, str | None]:
    text = read_text(path)
    if text is None:
        return None, None, "unreadable" if path.exists() else None
    schema_match = SCHEMA_RE.search(text)
    total_match = TOTAL_RE.search(text) or COVERAGE_TOTAL_RE.search(text)
    final_match = FINAL_RE.search(text)
    return (
        int(schema_match.group(1)) if schema_match else None,
        int(total_match.group(1)) if total_match else None,
        final_match.group(1).lower() if final_match else None,
    )


def read_declared_total(paths: Iterable[Path]) -> tuple[int | None, str | None]:
    for path in paths:
        text = read_text(path)
        if text is None:
            continue
        match = TOTAL_RE.search(text) or TOTAL_FALLBACK_RE.search(text) or TABLE_CHAPTER_TOTAL_RE.search(text)
        if match and int(match.group(1)) > 0:
            return int(match.group(1)), path.as_posix()
    return None, None


def read_source_hash(paths: Iterable[Path]) -> tuple[str | None, str | None]:
    for path in paths:
        text = read_text(path)
        if text is None:
            continue
        match = SOURCE_HASH_RE.search(text)
        if match:
            return match.group(1).lower(), path.as_posix()
    return None, None


def read_index_chapters(path: Path) -> tuple[list[int], list[str]]:
    if not nonempty(path):
        return [], []
    errors: list[str] = []
    chapters: list[int] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"chapter", "char_count", "source_locator", "status", "source_sha256"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                return [], ["chapter_index.csv에 필요한 열이 없습니다: " + ", ".join(sorted(missing))]
            for row_number, row in enumerate(reader, start=2):
                try:
                    chapters.append(int(row["chapter"]))
                except (TypeError, ValueError):
                    errors.append(f"chapter_index.csv의 {row_number}행 장 번호가 유효하지 않습니다")
    except (OSError, UnicodeError, csv.Error) as exc:
        return [], [f"chapter_index.csv를 읽을 수 없습니다: {exc}"]
    if len(chapters) != len(set(chapters)):
        errors.append("chapter_index.csv에 중복 장 번호가 있습니다")
    unique = sorted(set(chapters))
    if unique and unique != list(range(1, max(unique) + 1)):
        errors.append("chapter_index.csv의 장 번호가 연속적이지 않습니다")
    return unique, errors


def read_index_identities(path: Path) -> list[dict[str, str]]:
    if not nonempty(path):
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except (OSError, UnicodeError, csv.Error):
        return []


def read_managed_stages(text: str | None) -> tuple[bool, dict[str, dict[str, str]]]:
    if not text or text.count(STATE_START) != 1 or text.count(STATE_END) != 1:
        return False, {}
    match = re.search(re.escape(STATE_START) + r"(.*?)" + re.escape(STATE_END), text, re.DOTALL)
    if not match:
        return False, {}
    stages: dict[str, dict[str, str]] = {}
    section = None
    for line in match.group(1).splitlines():
        if line.strip() == "### 阶段状态":
            section = "stages"
            continue
        if line.startswith("### "):
            section = None
            continue
        if section != "stages" or not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0] not in {"阶段", "---"}:
            stages[cells[0].lower()] = {"status": cells[1].lower(), "output": cells[2]}
    return True, stages


def collect_numbered_files(
    directory: Path, pattern: re.Pattern[str]
) -> tuple[list[int], dict[int, Path], list[str]]:
    chapters: list[int] = []
    sources: dict[int, Path] = {}
    duplicates: list[str] = []
    if not directory.is_dir():
        return chapters, sources, duplicates
    for path in sorted(directory.iterdir()):
        match = pattern.match(path.name)
        if not match or not nonempty(path):
            continue
        chapter = int(match.group(1))
        if chapter in sources:
            duplicates.append(f"제{chapter}장: {sources[chapter].as_posix()} / {path.as_posix()}")
            continue
        chapters.append(chapter)
        sources[chapter] = path
    return sorted(chapters), sources, duplicates


def compact_ranges(chapters: Iterable[int]) -> list[str]:
    values = sorted(set(chapters))
    if not values:
        return []
    ranges: list[str] = []
    start = previous = values[0]
    for chapter in values[1:]:
        if chapter == previous + 1:
            previous = chapter
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = chapter
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ranges


def relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def summary_kind(path: Path) -> str:
    text = read_text(path) or ""
    return "three_script_projection" if PROJECTION_RE.search(text[:1000]) else "upstream_summary"


def read_legacy_boundaries(text: str | None) -> list[dict[str, object]]:
    """v0.7.x ‘章节边界’ 표 행: 이전 장 번호, 제목, 시작 행."""
    if not text:
        return []
    rows: list[dict[str, object]] = []
    in_section = False
    header: list[str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if in_section and rows:
                break
            in_section = bool(BOUNDARY_HEADING_RE.match(stripped))
            header = None
            continue
        if not in_section or not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if header is None:
            if "章号" in cells:
                header = cells
            continue
        if not "".join(cells).strip("-: "):
            continue
        record = dict(zip(header, cells))
        number = re.search(r"\d+", record.get("章号", ""))
        start = re.search(r"\d+", record.get("起始行", ""))
        if not number:
            continue
        rows.append({
            "chapter": int(number.group(0)),
            "title": record.get("标题", ""),
            "start_line": int(start.group(0)) if start else None,
        })
    return rows


def title_parts(title: str) -> tuple[str, str, str]:
    """제목의 (레이블, 엄격한 키, 느슨한 키). 느슨한 키는 뒤쪽 작가 메모를 제외한다."""
    text = unicodedata.normalize("NFKC", str(title or "")).strip()
    label = ""
    for _ in range(3):
        match = TITLE_LABEL_RE.match(text)
        if not match or not match.group(0).strip():
            break
        for group in ("number", "english", "numeric", "special"):
            if match.group(group):
                label = match.group(group)
        text = text[match.end():]
    strict = TITLE_NOISE_RE.sub("", text)
    loose = text
    while TITLE_NOTE_RE.search(loose):
        loose = TITLE_NOTE_RE.sub("", loose)
    return label, strict, TITLE_NOISE_RE.sub("", loose) or strict


def label_matches(label: str, row: dict[str, object]) -> bool:
    source = str(row.get("source_chapter", "")).strip()
    if not label or not source:
        return False
    if label == source:
        return True
    try:
        from build_chapter_index import parse_number
        return source.isdigit() and parse_number(label) == int(source)
    except ValueError:
        return False


def title_candidates(title: str, index_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """이전 표 제목과 일치하는 색인 행을 가장 적합한 단계부터 반환한다."""
    label, strict, loose = title_parts(title)
    if strict:
        keys = [(row, title_parts(str(row.get("title", "")))) for row in index_rows]
        for tier in (
            [row for row, (_, row_strict, _) in keys if row_strict == strict],
            [row for row, (_, _, row_loose) in keys
             if row_loose and (row_loose == loose or row_loose in loose or loose in row_loose)],
        ):
            if tier:
                return tier
    # 제목이 바뀌거나 없어도 장 번호는 남아 있다.
    return [row for row in index_rows if label_matches(label, row)]


def map_legacy_row(old: dict[str, object], index_rows: list[dict[str, object]]) -> int | None:
    """이전 경계 행이 가리키는 색인 장.
    시작 행이 정확히 장 제목 행이면 그것만으로 결정한다. 아니면 제목으로 고르며 여럿이면 이전 시작 행에 가장 가까운 장을 택한다.
    제목 없는 행은 해당 행을 포함하는 장으로 돌아간다.
    """
    start = old.get("start_line")
    if isinstance(start, int):
        for row in index_rows:
            if int(row["start_line"]) == start:
                return int(row["chapter"])
    matches = title_candidates(str(old.get("title", "")), index_rows)
    if not isinstance(start, int):
        return int(matches[0]["chapter"]) if len(matches) == 1 else None
    if not matches and not any(title_parts(str(old.get("title", "")))[:2]):
        matches = [row for row in index_rows if int(row["start_line"]) <= start <= int(row["end_line"])]

    def distance(row: dict[str, object]) -> int:
        first, last = int(row["start_line"]), int(row["end_line"])
        return 0 if first <= start <= last else min(abs(start - first), abs(start - last))

    ranked = sorted(matches, key=distance)
    if not ranked or (len(ranked) > 1 and distance(ranked[0]) == distance(ranked[1])):
        return None
    return int(ranked[0]["chapter"])


def leading_special_labels(index_rows: list[dict[str, object]]) -> list[str]:
    """첫 번호 장 앞의 프롤로그형 장(楔子、序章、第0章 등)."""
    labels: list[str] = []
    for row in index_rows:
        source = str(row.get("source_chapter", "")).strip()
        if source.isdigit() and int(source) >= 1:
            break
        labels.append("第0章" if source == "0" else source)
    return labels


def mapping_author_message(detail: str, labels: list[str], done: str) -> str:
    """필드 이름 없이 작가의 선택지를 포함한 쉬운 중단 메시지 하나."""
    if labels:
        prologue = "、".join("「%s」" % label for label in labels)
        return (
            "잠시 멈춰야 합니다: %s. 이번 장 구분에서는 도입부의 %s를 별도 장으로 계산했습니다. "
            "이대로 분석을 계속하면 기존 파일의 장 번호가 한 장씩 어긋나 %s의 분석이 빠지거나 중복됩니다. 다음 중 하나를 선택하세요: "
            "① 기존 장 번호로 계속(권장. 기존 분석에서 %s를 별도 장으로 세지 않았다면 선택): %s를 첫 장에 합치고, "
            "이미 분석한 %s는 그대로 재사용하며 %s를 따로 분석하지 않습니다. "
            "② %s를 별도 장으로 계산: 기존 분석 결과를 모두 백업 폴더로 옮기고(삭제하지 않음) 새 장 번호로 다시 분석합니다. "
            "③ 새 폴더에서 작품 전체를 다시 분석합니다."
            % (detail, prologue, prologue, prologue, prologue, done, prologue, prologue)
        )
    return (
        "잠시 멈춰야 합니다: %s. 기존 분석 %s가 어느 장에 해당하는지 확인할 수 없습니다. 다음 중 하나를 선택하세요: "
        "① 새 폴더에서 작품 전체를 다시 분석(권장). ② 원문 버전이 바뀌었거나 수정됐다면 기존 분석에 사용한 원문으로 되돌린 뒤 계속합니다."
        % (detail, done)
    )


def legacy_mapping_check(root: Path, index_rows: list[dict[str, object]]) -> dict[str, object] | None:
    """이전 실행의 번호 파일이 장 색인과 맞지 않으면 중단한다.
    이전 요약은 항상 색인보다 먼저 만들어졌다. _progress.md가 v0.7.x의 경계 표를 갖거나 런타임 블록이 없으면 황금 3장 분석도 이전 결과다.
    이번 Stage 1은 색인 기준으로 이를 쓴다. 이전 경계 표가 있으면 그것으로 결정하며, 없는데 원문이 1장부터 시작하지 않으면 모호하다.
    """
    if not index_rows:
        return None
    progress_text = read_text(root / "_progress.md")
    boundaries = read_legacy_boundaries(progress_text)
    legacy_progress = progress_text is not None and (bool(boundaries) or STATE_START not in progress_text)
    _, summary_sources, _ = collect_numbered_files(root / "장별분석", SUMMARY_RE)
    old_chapters = {chapter for chapter, path in summary_sources.items() if summary_kind(path) == "upstream_summary"}
    old_kinds = ["장별 요약"] if old_chapters else []
    if legacy_progress:
        golden, _, _ = collect_numbered_files(root / "장별분석", GOLDEN_RE)
        if golden:
            old_chapters.update(golden)
            old_kinds.insert(0, "도입부 세 장 분석")
    if not old_chapters:
        return None
    rows = sorted(index_rows, key=lambda row: int(row["chapter"]))
    labels = leading_special_labels(rows)
    done = "、".join(old_kinds)
    if boundaries:
        by_old = {int(row["chapter"]): row for row in boundaries}
        # 이전 실행이 표 이후에 추가한 장도 표가 포함하는 모든 장이 일치한다면
        # 같은 번호 체계를 유지한다.
        checked = sorted(chapter for chapter in old_chapters if chapter <= max(by_old)) or sorted(old_chapters)
        shifted = []
        unknown = []
        for chapter in checked:
            old = by_old.get(chapter)
            mapped = map_legacy_row(old, rows) if old else None
            if mapped is None:
                unknown.append(chapter)
            elif mapped != chapter:
                shifted.append((chapter, mapped))
        if not shifted and not unknown:
            return None
        if shifted:
            old_number, new_number = shifted[0]
            title = next((str(row.get("title", "")) for row in rows if int(row["chapter"]) == new_number), "")
            detail = "기존 분석의 제%s장 ‘%s’가 이번 장 목록에서는 제%s장입니다" % (old_number, title, new_number)
        else:
            detail = "기존 진행 기록의 장 목록이 원문과 맞지 않습니다(제%s장을 찾을 수 없음)" % compact_ranges(unknown)[0]
        code = "legacy_boundary_shift" if shifted else "legacy_boundary_unmatched"
    else:
        first_source = str(rows[0].get("source_chapter", "")).strip()
        if first_source.isdigit() and int(first_source) == 1:
            return None
        detail = "원문은 ‘%s’로 시작하지만 기존 분석에 장 번호를 대조할 목록이 없습니다" % (first_source or "알 수 없음")
        code = "legacy_identity_unverifiable"
    return {
        "code": code,
        "conflict": "기존 분석의 장 번호가 현재 색인과 다릅니다: " + detail,
        "author_message": mapping_author_message(detail, labels, done),
        "fold_prologue_available": bool(labels),
        "legacy_chapters": sorted(old_chapters),
    }


def inspect(root: Path, expected_override: int | None) -> dict[str, object]:
    root = root.resolve()
    schema, progress_total, final_state = read_progress(root / "_progress.md")
    progress_text = read_text(root / "_progress.md")
    index_chapters, index_errors = read_index_chapters(root / "chapter_index.csv")
    index_identities = read_index_identities(root / "chapter_index.csv")
    managed_state_present, managed_stages = read_managed_stages(progress_text)

    summaries, summary_sources, duplicate_summaries = collect_numbered_files(root / "장별분석", SUMMARY_RE)
    golden, golden_sources, duplicate_golden = collect_numbered_files(root / "장별분석", GOLDEN_RE)

    preferred_paths: dict[int, str] = {}
    preferred_kinds: dict[int, str] = {}
    for chapter, path in summary_sources.items():
        preferred_paths[chapter] = relative(root, path)
        preferred_kinds[chapter] = summary_kind(path)
    for chapter, path in golden_sources.items():
        if chapter not in preferred_paths:
            preferred_paths[chapter] = relative(root, path)
            preferred_kinds[chapter] = "golden_analysis"

    expected = expected_override
    expected_source = "argument" if expected is not None else None
    if expected is None and index_chapters and not index_errors:
        expected = max(index_chapters)
        expected_source = "chapter_index.csv"
    if expected is None and progress_total is not None and final_state in {"completed", "completed_with_errors"}:
        expected = progress_total
        expected_source = "_progress.md"
    if expected is None:
        expected, source = read_declared_total((root / "작품분석보고서.md", root / "개요요약.md", root / "빠른미리보기.md"))
        expected_source = Path(source).name if source else None
    if expected is None and progress_total is not None:
        expected = progress_total
        expected_source = "_progress.md"

    expected_set = set(range(1, expected + 1)) if expected else set()
    union_semantic_set = set(preferred_paths)
    missing_semantic = sorted(expected_set - union_semantic_set)
    out_of_range_semantic = sorted(union_semantic_set - expected_set) if expected else []
    missing_summaries = sorted(expected_set - set(summaries))
    out_of_range_summaries = sorted(set(summaries) - expected_set) if expected else []

    primary = {
        "emotion_module": nonempty(root / "플롯" / "감정모듈.md"),
        "rhythm": nonempty(root / "플롯" / "리듬.md"),
    }
    plot_dir = root / "플롯"
    assets = {
        "report": nonempty(root / "작품분석보고서.md"),
        "style": nonempty(root / "문체.md"),
        "storyline": nonempty(plot_dir / "이야기선.md"),
        "plot_units": any_nonempty(
            path
            for path in plot_dir.glob("*.md")
            if path.name not in {"README.md", "이야기선.md", "리듬.md", "감정모듈.md", "분산사건.md"}
        )
        if plot_dir.is_dir()
        else False,
        "characters": any_nonempty(path for path in (root / "인물").glob("*.md") if path.name != "인물관계.md")
        if (root / "인물").is_dir()
        else False,
        "settings": any_nonempty((root / "설정").rglob("*.md")) if (root / "설정").is_dir() else False,
        "batch_cache": any_nonempty((root / "_analysis_cache").glob("批次-*.md"))
        if (root / "_analysis_cache").is_dir()
        else False,
        "chapter_index": nonempty(root / "chapter_index.csv"),
    }

    has_any = bool(union_semantic_set) or any(assets.values()) or any(primary.values()) or nonempty(root / "_progress.md")
    semantic_coverage_complete = bool(union_semantic_set) and (
        (expected is not None and not missing_semantic and not out_of_range_semantic)
        or (expected is None and final_state in {"completed", "completed_with_errors"})
    )
    summary_coverage_complete = (
        bool(summaries) and expected is not None and not missing_summaries and not out_of_range_summaries
    )
    standard_coverage_complete = bool(union_semantic_set) and expected is not None and union_semantic_set == expected_set
    legacy_core = assets["report"] and summary_coverage_complete and (assets["storyline"] or assets["plot_units"])
    managed_pipeline_complete = all(
        managed_stages.get(stage, {}).get("status") == "completed"
        for stage in ("stage1", "stage2", "stage3", "stage4", "stage5", "stage6")
    )
    usable_upstream_complete = (
        all(primary.values())
        and assets["report"]
        and standard_coverage_complete
        and (
            managed_pipeline_complete
            or (
                final_state in {"completed", "completed_with_errors"}
                and (assets["storyline"] or assets["plot_units"])
            )
        )
    )

    if expected:
        preferred_paths = {chapter: path for chapter, path in preferred_paths.items() if chapter in expected_set}
        preferred_kinds = {chapter: kind for chapter, kind in preferred_kinds.items() if chapter in expected_set}
    semantic_set = set(preferred_paths)

    full_result_available = usable_upstream_complete or legacy_core
    mixed_sources = len(set(preferred_kinds.values())) > 1

    # 이전 실행에서 번호를 붙인 파일은 색인과 어긋날 수 있지만 이번 실행의 황금 3장
    # 분석과 투영은 색인을 기준으로 작성한다.
    mapping_conflicts: list[str] = []
    mapping_blocked_chapters: list[int] = []
    mapping = legacy_mapping_check(root, index_identities) if index_identities else None
    if mapping:
        mapping_blocked_chapters = sorted(expected_set or set(index_chapters))
        mapping_conflicts.append(str(mapping["conflict"]))

    stage_repairs: list[str] = []
    if semantic_coverage_complete:
        legacy_completed = final_state in {"completed", "completed_with_errors"}
        if not primary["emotion_module"]:
            stage_repairs.append("stage3_emotion")
        if not primary["rhythm"]:
            stage_repairs.append("stage3_rhythm")
        if not legacy_completed and (not assets["characters"] or not assets["settings"]):
            stage_repairs.append("stage4")
        if not assets["report"]:
            stage_repairs.append("stage5")
        if not assets["style"]:
            stage_repairs.append("stage6_style")
        for stage in ("stage3", "stage4", "stage5", "stage6"):
            row = managed_stages.get(stage)
            if row and row.get("status") != "completed" and stage not in stage_repairs:
                stage_repairs.append(stage)
            elif managed_state_present and not legacy_completed and row is None:
                # 새 3스크립트 실행에서는 중단 전에 파일을 수동으로 놓았더라도
                # 완료된 단계 행이 필요하다.
                if stage not in stage_repairs and not any(item.startswith(stage + "_") for item in stage_repairs):
                    stage_repairs.append(stage)

    if not has_any:
        classification = "empty"
        recommended_path = "new_analysis"
    elif usable_upstream_complete:
        classification = "current_complete"
        recommended_path = "repair_stages" if stage_repairs else "direct_use"
    elif legacy_core:
        classification = "legacy_complete"
        recommended_path = "repair_stages" if stage_repairs else "direct_use"
    elif semantic_coverage_complete:
        classification = "partial_or_mixed"
        recommended_path = "repair_stages" if stage_repairs else "enhance_existing"
    else:
        classification = "partial_or_mixed"
        recommended_path = "continue_partial" if expected and missing_semantic else "enhance_existing"

    conflicts = list(index_errors)
    conflicts.extend(f"중복 요약: {item}" for item in duplicate_summaries)
    conflicts.extend(f"중복 도입부 세 장 분석: {item}" for item in duplicate_golden)
    conflicts.extend(mapping_conflicts)
    if final_state == "completed" and not usable_upstream_complete:
        conflicts.append("진행 상태는 completed지만 현재 주요 산출물 또는 선행 장별 분석이 불완전합니다")
    if final_state == "completed_with_errors" and not semantic_coverage_complete:
        conflicts.append("진행 상태가 completed_with_errors입니다. 실패·확인 대기 기록으로 사용 가능한 범위를 확인하세요")
    if index_chapters and expected and max(index_chapters) != expected:
        conflicts.append("자동 색인의 장 수가 예상 장 수와 다릅니다")

    source_hash, source_hash_path = read_source_hash((root / "_progress.md",))

    return {
        "root": str(root),
        "classification": classification,
        "recommended_path": recommended_path,
        "schema_version": schema,
        "final_state": final_state,
        "expected_chapters": expected,
        "expected_chapters_source": expected_source,
        # 원래 인터페이스가 필요한 호출자를 위해 원래 키를 남긴다.
        "completed_summary_chapters": summaries,
        "missing_summary_chapters": missing_summaries,
        "out_of_range_summary_chapters": out_of_range_summaries,
        # 런타임 라우팅은 요약 파일명만 쓰지 않고 아래에서 선택한 의미 계열을 사용해야 한다.
        "completed_semantic_chapters": sorted(semantic_set),
        "missing_semantic_chapters": missing_semantic,
        "out_of_range_semantic_chapters": out_of_range_semantic,
        "semantic_coverage_complete": semantic_coverage_complete,
        "full_result_available": full_result_available,
        "chapter_sources": {
            "priority": ["upstream_summary", "three_script_projection", "golden_analysis"],
            "upstream_summary": {"chapters": summaries, "ranges": compact_ranges(summaries)},
            "golden_analysis": {"chapters": golden, "ranges": compact_ranges(golden)},
            "preferred_by_chapter": {str(chapter): preferred_kinds[chapter] for chapter in sorted(preferred_kinds)},
            "preferred_paths": {str(chapter): preferred_paths[chapter] for chapter in sorted(preferred_paths)},
        },
        "source_hash": source_hash,
        "source_hash_source": source_hash_path,
        "primary_artifacts": primary,
        "reusable_assets": assets,
        "legacy_capabilities": {
            "benchmark_reference": full_result_available or assets["report"] or assets["plot_units"] or bool(semantic_set),
            "import_facts": bool(semantic_set),
            "writing_style_reference": assets["style"],
        },
        "current_capabilities": {
            "emotion_module_recall": primary["emotion_module"],
            "rhythm_reference_recall": primary["rhythm"],
            "source_location": assets["chapter_index"],
        },
        "mixed_sources": mixed_sources,
        "stage_repairs": stage_repairs,
        "managed_stage_status": managed_stages,
        "chapter_mapping_conflicts": mapping_conflicts,
        "chapter_mapping_blocked_chapters": mapping_blocked_chapters,
        "chapter_mapping_author_message": mapping["author_message"] if mapping else None,
        "provenance_requires_review": mixed_sources or (has_any and schema is None),
        "conflicts": conflicts,
        "notes": [
            "이 검사는 지정한 작품 폴더의 선행 산출물 표준 경로만 조사합니다. 다른 프로젝트나 디스크는 검색하지 않습니다.",
            "실행 경로를 결정할 때는 completed_semantic_chapters를 사용해야 합니다. 장별 요약 파일이 없다고 분석 결과도 없는 것은 아닙니다.",
            "direct_use는 기본적으로 바로 재사용한다는 뜻입니다. 사용자가 보강을 명시적으로 요청한 경우에만 기존 결과에서 다시 추출합니다.",
            "작품 전체를 다시 분석하려면 새 폴더를 사용하세요. 이 검사는 현재 폴더를 덮어쓰는 재분석을 제공하지 않습니다.",
        ],
    }


def compact_payload(payload: dict[str, object]) -> dict[str, object]:
    """사람·모델용 검사 뷰에서 장별 배열을 제거한다."""
    result = dict(payload)
    semantic = result.pop("completed_semantic_chapters")
    missing = result.pop("missing_semantic_chapters")
    result["semantic_coverage"] = {
        "completed_count": len(semantic),
        "completed_ranges": compact_ranges(semantic),
        "missing_count": len(missing),
        "missing_ranges": compact_ranges(missing),
    }
    result.pop("completed_summary_chapters", None)
    result.pop("missing_summary_chapters", None)
    result.pop("out_of_range_summary_chapters", None)
    result.pop("out_of_range_semantic_chapters", None)
    source_info = dict(result["chapter_sources"])
    source_info.pop("preferred_by_chapter", None)
    source_info.pop("preferred_paths", None)
    for key in ("upstream_summary", "golden_analysis"):
        entry = dict(source_info[key])
        entry["count"] = len(entry.pop("chapters"))
        source_info[key] = entry
    result["chapter_sources"] = source_info
    return result


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="작품분석실/{작품명} 폴더")
    parser.add_argument("--expected-chapters", type=int, help="알고 있는 전체 장 수. 생략하면 표준 경로를 우선해 추정")
    parser.add_argument("--compact", action="store_true", help="장별 배열을 생략하고 실행 경로 판단에 필요한 범위 요약을 출력")
    args = parser.parse_args()
    if args.expected_chapters is not None and args.expected_chapters < 1:
        parser.error("--expected-chapters는 0보다 커야 합니다")
    try:
        if not args.root.exists():
            raise ValueError("root_not_found:%s" % args.root)
        if not args.root.is_dir():
            raise ValueError("root_is_not_directory:%s" % args.root)
        # 여기서 디렉터리를 실제로 읽어 읽을 수 없는 경로를 빈 신규 분석 프로젝트로
        # 오인하기 전에 실패하게 한다.
        next(args.root.iterdir(), None)
        payload = inspect(args.root, args.expected_chapters)
        if args.compact:
            payload = compact_payload(payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
