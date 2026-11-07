#!/usr/bin/env python3
"""storyctl과 추적 기능이 공유하는 작은 결정적 글자 수 핵심 모듈."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any


WORDCOUNT_SCHEMA = "story-wordcount-result/v1"
MEASUREMENT_SCHEMA = "story-wordcount-measurement/v1"
CHECKPOINT_SCHEMA = "story-wordcount-checkpoint/v1"
METRIC = "visible_chars_v1"
RESOLUTIONS = frozenset({"within_user_band", "accepted_current_length"})

_WHITE_SPACE_CODEPOINTS = frozenset(
    [*range(0x0009, 0x000E)]
    + [
        0x0020, 0x0085, 0x00A0, 0x1680, *range(0x2000, 0x200B),
        0x2028, 0x2029, 0x202F, 0x205F, 0x3000,
    ]
)
_FRONTMATTER_KEY_RE = re.compile(r"^[A-Za-z_\u3400-\u9FFF][^:\n]{0,80}:[ \t]*(?:.*)$")
_LEADING_BLANK_RE = re.compile(r"^[\u0009\u0020\u3000]*$")
_ATX_HEADING_RE = re.compile(r"^[\u0009\u0020]{0,3}#{1,6}[\u0009\u0020]+\S")
_POSITIVE_INTEGER_RE = re.compile(r"^[1-9]\d*$")
# 상세 개요 ‘字数目标’, ‘字数范围’, ‘字数口径’의 유일한 표기 문법. check-outline-contract.js가 같은 정규식을 정확히 복제하며
# scripts/test-storyctl.py가 같은 표기를 양쪽에서 실행해 개요 검증 통과 후 장 검사에서 거부하지 않도록 보장한다.
# 숫자가 없는 목표·범위 행(‘字数目标：按卷规划’)은 설명문이며 값을 추출하지 않는다.
_NUMBER = r"([1-9][0-9]{0,2}(?:[,，][0-9]{3})+|[1-9][0-9]*)"
_NOTE = r"(?:[（(][^（）()]*[）)])?"
_TARGET_VALUE_RE = re.compile(rf"^(?:约|大约)?[ \t]*{_NUMBER}[ \t]*字?(?:左右)?[ \t]*{_NOTE}$")
_RANGE_VALUE_RE = re.compile(
    rf"^{_NUMBER}[ \t]*字?[ \t]*(?:-|~|～|—|–|－|至|到)[ \t]*{_NUMBER}[ \t]*字?[ \t]*{_NOTE}$"
)
_METRIC_VALUE_RE = re.compile(rf"^([A-Za-z0-9_-]+)[ \t]*{_NOTE}$")
_HAS_DIGIT_RE = re.compile(r"[0-9０-９]")


def _field_values(text: str, label: str) -> list[str]:
    pattern = re.compile(
        rf"^[ \t>]*(?:[-*+][ \t]*)?(?:\*\*)?{label}(?:\*\*)?[ \t]*[:：][ \t]*(.*?)[ \t]*$", re.MULTILINE
    )
    return [value.replace("**", "").strip() for value in pattern.findall(text)]


def _numeric_field_values(text: str, label: str) -> list[str]:
    return [raw for raw in _field_values(text, label) if _HAS_DIGIT_RE.search(raw)]


def _number(raw: str) -> int:
    return int(re.sub(r"[,，]", "", raw))


def parse_target_field(text: str) -> dict[str, Any]:
    """{"status": ok|missing|invalid|conflict, "value": int|None, "raw": [...]}를 반환한다."""
    raws = _numeric_field_values(normalize_newlines(text).lstrip("\ufeff"), "字数目标")
    if not raws:
        return {"status": "missing", "value": None, "raw": raws}
    matches = [_TARGET_VALUE_RE.fullmatch(raw) for raw in raws]
    if not all(matches):
        return {"status": "invalid", "value": None, "raw": raws}
    values = sorted({_number(match.group(1)) for match in matches if match})
    if len(values) != 1:
        return {"status": "conflict", "value": None, "raw": raws}
    return {"status": "ok", "value": values[0], "raw": raws}


def parse_range_field(text: str) -> dict[str, Any]:
    """선택적 작가 범위 행 ‘字数范围：2000-2600’. 상태 이름은 parse_target_field와 같다."""
    raws = _numeric_field_values(normalize_newlines(text).lstrip("\ufeff"), "字数范围")
    if not raws:
        return {"status": "missing", "value": None, "raw": raws}
    matches = [_RANGE_VALUE_RE.fullmatch(raw) for raw in raws]
    if not all(matches):
        return {"status": "invalid", "value": None, "raw": raws}
    values = sorted({(_number(match.group(1)), _number(match.group(2))) for match in matches if match})
    if len(values) != 1:
        return {"status": "invalid", "value": None, "raw": raws}
    low, high = values[0]
    if low > high:
        return {"status": "invalid", "value": None, "raw": raws}
    return {"status": "ok", "value": {"min": low, "max": high}, "raw": raws}


def parse_metric_field(text: str) -> dict[str, Any]:
    """‘字数口径：visible_chars_v1（按可见字符）’. 각 행은 기준 이름(괄호 메모 선택)이어야 하며 METRIC만 허용한다."""
    raws = _field_values(normalize_newlines(text).lstrip("\ufeff"), "字数口径")
    matches = [_METRIC_VALUE_RE.fullmatch(raw) for raw in raws]
    ok = bool(raws) and all(matches) and {match.group(1) for match in matches if match} == {METRIC}
    return {"ok": ok, "raw": raws}


class WordcountError(ValueError):
    """예상 가능한 결정적 글자 수 계약 위반."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WordcountError(message)


def normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def strip_recognizable_frontmatter(value: str) -> str:
    lines = value.split("\n")
    if not lines or lines[0] != "---":
        return value
    closing = next((index for index in range(1, min(len(lines), 201)) if lines[index] in {"---", "..."}), -1)
    if closing < 2 or not any(_FRONTMATTER_KEY_RE.match(line) for line in lines[1:closing]):
        return value
    return "\n".join(lines[closing + 1 :])


def visible_body(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("body must be a string")
    text = normalize_newlines(value)
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = strip_recognizable_frontmatter(text).split("\n")
    while lines and _LEADING_BLANK_RE.match(lines[0]):
        lines.pop(0)
    if lines and _ATX_HEADING_RE.match(lines[0]):
        lines.pop(0)
    return "\n".join(lines)


def count_visible_chars(value: str) -> int:
    return sum(ord(character) not in _WHITE_SPACE_CODEPOINTS for character in visible_body(value))


def parse_target(value: Any) -> int:
    raw = str(value if value is not None else "")
    if not _POSITIVE_INTEGER_RE.fullmatch(raw):
        raise WordcountError("target must be a positive integer")
    target = int(raw)
    require(target <= 9_007_199_254_740_991, "target exceeds Number.MAX_SAFE_INTEGER")
    return target


def normalize_author_range(value: Any) -> dict[str, int] | None:
    """작가가 명시한 상한·하한. None은 기본 ±12% / ±15% 이중 범위 유지다."""
    if value is None:
        return None
    require(isinstance(value, dict) and set(value) == {"min", "max"}, "author range must be {min, max}")
    low, high = value["min"], value["max"]
    require(
        all(isinstance(item, int) and not isinstance(item, bool) and item >= 1 for item in (low, high)),
        "author range bounds must be positive integers",
    )
    require(low <= high, "author range min must not exceed max")
    return {"min": low, "max": high}


def compute_wordcount_bands(value: Any, author_range: Any = None) -> dict[str, dict[str, int]]:
    target = parse_target(value)
    author = normalize_author_range(author_range)
    if author is not None:
        # 작가 지정 범위를 그대로 우선한다. 내부·사용자 범위 모두 이 값을 사용하며 borderline은 없다.
        return {"internal": dict(author), "user": dict(author)}
    return {
        "internal": {"min": (target * 88 + 99) // 100, "max": target * 112 // 100},
        "user": {"min": (target * 85 + 99) // 100, "max": target * 115 // 100},
    }


def invalid_wordcount_result(
    reason: str, *, chapter: Any = None, case_id: Any = None,
    target: int | None = None, actual: int | None = None,
) -> dict[str, Any]:
    return {
        "schema": WORDCOUNT_SCHEMA, "metric": METRIC, "chapter": chapter, "case_id": case_id,
        "target": target, "actual": actual, "internal_band": None, "user_band": None,
        "signed_error_pct": None, "absolute_error_pct": None, "band_source": None,
        "status": "invalid", "invalid_reason": reason,
    }


def measure_wordcount(value: str, *, chapter: Any = None, case_id: Any = None) -> dict[str, Any]:
    try:
        actual = count_visible_chars(value)
    except (TypeError, ValueError):
        return {
            "schema": MEASUREMENT_SCHEMA, "metric": METRIC, "chapter": chapter,
            "case_id": case_id, "actual": None, "status": "invalid", "invalid_reason": "INVALID_BODY",
        }
    return {
        "schema": MEASUREMENT_SCHEMA, "metric": METRIC, "chapter": chapter,
        "case_id": case_id, "actual": actual, "status": "measured", "invalid_reason": None,
    }


def evaluate_wordcount(
    value: str, target_value: Any, *, chapter: Any = None, case_id: Any = None, author_range: Any = None,
) -> dict[str, Any]:
    try:
        target = parse_target(target_value)
    except (TypeError, ValueError):
        return invalid_wordcount_result("INVALID_TARGET", chapter=chapter, case_id=case_id)
    try:
        author = normalize_author_range(author_range)
    except WordcountError:
        return invalid_wordcount_result("INVALID_RANGE", chapter=chapter, case_id=case_id, target=target)
    try:
        actual = count_visible_chars(value)
    except (TypeError, ValueError):
        return invalid_wordcount_result("INVALID_BODY", chapter=chapter, case_id=case_id, target=target)
    if actual == 0:
        return invalid_wordcount_result("EMPTY_BODY", chapter=chapter, case_id=case_id, target=target, actual=actual)
    bands = compute_wordcount_bands(target, author)
    internal_pass = bands["internal"]["min"] <= actual <= bands["internal"]["max"]
    user_pass = bands["user"]["min"] <= actual <= bands["user"]["max"]
    status = "internal_pass" if internal_pass else (
        "borderline" if user_pass else ("under" if actual < bands["user"]["min"] else "over")
    )
    signed_error = (actual - target) / target
    return {
        "schema": WORDCOUNT_SCHEMA, "metric": METRIC, "chapter": chapter, "case_id": case_id,
        "target": target, "actual": actual,
        "internal_band": {**bands["internal"], "status": "pass" if internal_pass else "fail"},
        "user_band": {**bands["user"], "status": "pass" if user_pass else "fail"},
        "signed_error_pct": signed_error, "absolute_error_pct": abs(signed_error),
        "band_source": "author" if author else "default",
        "status": status, "invalid_reason": None,
    }


def checkpoint_wordcount(
    value: str, target_value: Any, *, chapter: Any = None, case_id: Any = None, author_range: Any = None,
) -> dict[str, Any]:
    target = parse_target(target_value)
    actual = count_visible_chars(value)
    author = normalize_author_range(author_range)
    user = compute_wordcount_bands(target, author)["user"]
    return {
        "schema": CHECKPOINT_SCHEMA, "metric": METRIC, "chapter": chapter, "case_id": case_id,
        "target": target, "actual": actual, "user_band": user,
        "band_source": "author" if author else "default",
        "remaining_user_range": {
            "min": max(0, user["min"] - actual),
            "max": max(0, user["max"] - actual),
        },
    }


_FIELD_ERRORS = {
    "missing": "is missing",
    "invalid": "is not a recognizable number (write e.g. 2300 字 / 约 2300 / 2,300)",
    "conflict": "has conflicting values",
}


def target_from_outline(value: str) -> int:
    text = normalize_newlines(value)
    if text.startswith("\ufeff"):
        text = text[1:]
    parsed = parse_target_field(text)
    require(parsed["status"] == "ok", f"字数目标 {_FIELD_ERRORS.get(parsed['status'], '')}: {parsed['raw']}")
    require(parse_metric_field(text)["ok"], f"字数口径 must be {METRIC}")
    return parse_target(parsed["value"])


def range_from_outline(value: str) -> dict[str, int] | None:
    """선택 행 ‘字数范围：2000-2600’. 없으면 None, 잘못 쓰면 기본 범위로 조용히 돌아가지 않고 오류를 낸다."""
    parsed = parse_range_field(value)
    if parsed["status"] == "missing":
        return None
    require(parsed["status"] == "ok", f"字数范围 must be one min-max pair with min <= max: {parsed['raw']}")
    return parsed["value"]


def _chapter_number_from_name(name: str, *, outline: bool) -> int | None:
    # 개고에서 원문을 제N장_장제목_원본_{日期}.md로 백업하며 훅처럼 이를 해당 장의 본문으로 보지 않는다.
    if not outline and "_원본_" in name:
        return None
    pattern = r"^상세개요_제0*(\d+)장.*\.md$" if outline else r"^제0*(\d+)장(?:[_\- 　].*)?\.md$"
    match = re.match(pattern, name)
    return int(match.group(1)) if match else None


def find_chapter_file(directory: Path, chapter: int, *, outline: bool) -> Path:
    require(isinstance(chapter, int) and not isinstance(chapter, bool) and chapter >= 1, "chapter must be >= 1")
    require(directory.is_dir(), f"chapter directory is missing: {directory}")
    matches = sorted(
        path for path in directory.iterdir()
        if path.is_file() and _chapter_number_from_name(path.name, outline=outline) == chapter
    )
    label = "outline" if outline else "body"
    require(len(matches) == 1, f"chapter {chapter} must have exactly one {label} file")
    return matches[0]


def read_chapter_outline(project: Path, chapter: int) -> tuple[Path, str]:
    outline_path = find_chapter_file(project.resolve() / "개요", chapter, outline=True)
    try:
        return outline_path, outline_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise WordcountError(f"unable to read outline: {exc}") from exc


def effective_author_range(outline: str, author_range: Any = None) -> dict[str, int] | None:
    """명령행 상한·하한이 있으면 상세 개요의 잘못된 범위에도 차단하지 않고 우선 적용한다. 없으면 개요를 읽는다."""
    return normalize_author_range(author_range) if author_range is not None else range_from_outline(outline)


def read_project_chapter(
    project: Path, chapter: int, author_range: Any = None,
) -> tuple[Path, Path, int, dict[str, int] | None]:
    """이번 장의 개요·본문을 찾아 목표 글자 수와 유효한 작가 범위를 읽는다."""
    outline_path, outline = read_chapter_outline(project, chapter)
    body_path = find_chapter_file(project.resolve() / "본문", chapter, outline=False)
    return outline_path, body_path, target_from_outline(outline), effective_author_range(outline, author_range)


def build_project_wordcount_record(
    project: Path, chapter: int, *, resolution: str, author_range: Any = None,
) -> dict[str, Any]:
    """author_range=None이면 개요의 ‘字数范围’를 읽고 명시적 --min-chars/--max-chars가 있으면 우선 적용한다."""
    require(resolution in RESOLUTIONS, f"unsupported wordcount resolution: {resolution}")
    _, body_path, target, author = read_project_chapter(project, chapter, author_range)
    try:
        body_bytes = body_path.read_bytes()
        body = body_bytes.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise WordcountError(f"unable to read chapter files: {exc}") from exc
    result = evaluate_wordcount(body, target, chapter=chapter, author_range=author)
    require(result["status"] != "invalid", f"invalid chapter wordcount: {result['invalid_reason']}")
    in_user_band = result["status"] in {"internal_pass", "borderline"}
    require(
        (resolution == "within_user_band" and in_user_band)
        or (resolution == "accepted_current_length" and not in_user_band),
        "wordcount resolution does not match the current length",
    )
    record = {
        "metric": METRIC,
        "target": result["target"],
        "actual": result["actual"],
        "status": result["status"],
        "resolution": resolution,
        "body_sha256": hashlib.sha256(body_bytes).hexdigest(),
    }
    if author is not None:
        record["author_range"] = dict(author)
    return record


_RECORD_FIELDS = {"metric", "target", "actual", "status", "resolution", "body_sha256"}


def normalize_wordcount_record(value: object) -> dict[str, Any]:
    require(isinstance(value, dict), "wordcount record must be an object")
    require(
        set(value) in (_RECORD_FIELDS, _RECORD_FIELDS | {"author_range"}),
        "wordcount record fields are invalid",
    )
    require(value.get("metric") == METRIC, "wordcount metric is unsupported")
    target = parse_target(value.get("target"))
    author = normalize_author_range(value.get("author_range"))
    actual = value.get("actual")
    require(isinstance(actual, int) and not isinstance(actual, bool) and actual >= 1, "wordcount actual is invalid")
    expected = evaluate_wordcount("字" * actual, target, author_range=author)
    require(value.get("status") == expected["status"], "wordcount status does not match target and actual")
    resolution = value.get("resolution")
    require(resolution in RESOLUTIONS, "wordcount resolution is unsupported")
    in_user_band = expected["status"] in {"internal_pass", "borderline"}
    require((resolution == "within_user_band") == in_user_band, "wordcount resolution does not match status")
    digest = value.get("body_sha256")
    require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None, "body_sha256 is invalid")
    return dict(value)


def wordcount_record_drift(project: Path, chapter: int, value: object) -> list[str]:
    """제출된 글자 수 기록 중 현재 파일 대비 만료된 항목. 고정된 본문 바이트와 목표만 대조한다.
    작가가 나중에 개요의 ‘字数范围’를 추가·수정하면 다음 계산의 판정 범위만 바뀌며 기존 기록은 만료되지 않는다.
    """
    record = normalize_wordcount_record(value)
    root = project.resolve()
    outline_path = find_chapter_file(root / "개요", chapter, outline=True)
    body_path = find_chapter_file(root / "본문", chapter, outline=False)
    try:
        outline = outline_path.read_text(encoding="utf-8")
        body_bytes = body_path.read_bytes()
    except (OSError, UnicodeError) as exc:
        raise WordcountError(f"unable to read chapter files: {exc}") from exc
    drift = []
    if hashlib.sha256(body_bytes).hexdigest() != record["body_sha256"]:
        drift.append("正文")
    if target_from_outline(outline) != record["target"]:
        drift.append("字数目标")
    return drift


def validate_current_wordcount_record(project: Path, chapter: int, value: object) -> dict[str, Any]:
    record = normalize_wordcount_record(value)
    current = build_project_wordcount_record(
        project, chapter, resolution=record["resolution"], author_range=record.get("author_range"),
    )
    require(record == current, "wordcount record is stale for the current body or target")
    return record
