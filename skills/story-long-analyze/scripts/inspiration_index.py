#!/usr/bin/env python3
"""EM 기법 카드에서 영감 원자를 등록하고 색인을 검증·조회한다.
3층 영감 라이브러리의 기계적 계층. 원자 영감(IA)은 별도 파일을 만들지 않고 `灵感索引.csv`의 한 행으로 등록한다.
기법 전문은 `작품분석실/{书}/플롯/감정모듈.md`의 EM 카드에서만 유지하며 필요할 때 ID로 조회한다.
NM/CBA 카드에는 경로 참조를 금지하고 출처는 `书名/EM-xxx` 형식 ID만 기록한다. 경로 해석은 색인으로 통일한다.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

COLUMNS = (
    "item_id",
    "layer",
    "title",
    "source_book",
    "path",
    "source_ids",
    "novel_count",
    "atom_count",
    "grade",
    "tags",
    "status",
)
LAYERS = {"原子灵感": "IA-", "单小说灵感合并": "NM-", "跨书灵感聚合": "CBA-"}
TAG_AXES = {"题材", "读者需求", "情绪", "关系动作", "剧情功能", "节奏位置", "适用阶段", "风险"}
REQUIRED_CBA_AXES = {"题材", "读者需求", "情绪", "剧情功能", "适用阶段", "风险"}
CORE_QUERY_AXES = {"题材", "读者需求", "情绪", "剧情功能", "适用阶段"}
# 완전한 EM 카드에 필수인 다섯 영감 매핑 필드. 누락은 Stage 3 카드 품질 문제이므로 오류를 보고하고 분석 측에서 수정한다.
EM_REQUIRED_FIELDS = ("读者想看什么", "情绪链", "戏剧单元", "可替换项", "不可照搬")
# 고유명 유출 검사에서 ‘不可照搬’은 제외한다. 이 필드는 원작 고유명을 명시하는 용도다.
EM_LEAK_SCAN_FIELDS = ("读者想看什么", "情绪链", "戏剧单元", "可替换项")
EM_HEADER_RE = re.compile(r"^###\s+[*_]*(EM-[0-9]{2,})(?![0-9])[*_]*\s*(?:[·\-—：:｜|]\s*)?(.*?)[\s*_]*$")
# EM 번호로 시작하지만 `### EM-xxx`가 아닌 제목은 다음 카드가 이전 카드에 조용히 병합되게 한다.
EM_MISPLACED_HEADER_RE = re.compile(r"^#{1,6}\s+[*_【\[]*EM-[0-9]")
EM_TABLE_SEPARATOR_RE = re.compile(r"^:?-+:?$")
EM_INDEX_ID_RE = re.compile(r"(EM-[0-9]{2,})")
# 필드 행은 표 `| 字段 | 值 |`와 굵은 목록 `- **字段**：值` 두 형식을 받는다(선행 `- ` 생략 가능).
EM_BOLD_FIELD_RE = re.compile(r"^[-*]?\s*\*{2,3}([^*]+?)(?:[:：]\*{2,3}|\*{2,3}\s*[:：])\s*(.*)$")
# 동의 필드 이름을 정규화하며 헤더 첫 열 단어는 필드로 보지 않는다.
EM_FIELD_ALIASES = {"不可照搬项": "不可照搬", "可替换项目": "可替换项"}
EM_TABLE_HEADER_KEYS = {"字段", "维度", "---", ""}
CARD_PATH_RE = re.compile(r"\]\(|\.md\)|原子灵感/|单小说灵感合并/|跨书灵感聚合/|작품분석실/")


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def csv_text(rows: list[dict[str, str]]) -> str:
    import io

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return "﻿" + buffer.getvalue()


def normalize_em_field(key: str) -> str:
    """필드명의 굵은 표시·공백을 제거하고 동의어 표로 정규화한다."""
    return EM_FIELD_ALIASES.get(key.strip().strip("*").strip(), key.strip().strip("*").strip())


def parse_em_module(module_text: str) -> tuple[list[dict[str, str]], list[tuple[str, str]], list[str]]:
    """감정모듈.md에서 (완전한 카드, 색인 전용 항목, 구조 문제)를 반환한다.
    완전한 카드는 `### EM-xxx 名称` 절의 필드이며 표 `|字段|内容|`와 목록 `- **字段**：内容`을 모두 받는다.
    굵은 필드와 같은 행에 값이 없으면 다음 필드·제목 전의 목록·문단을 여러 행 값으로 흡수한다.
    색인 항목은 ‘其他机制索引’ 절의 EM-xxx 포함 행(机制ID｜名称｜…)이다.
    인식하지 못한 EM 제목과 카드 내 중복 필드는 다음 카드가 이전 카드에 합쳐졌다는 뜻이므로 문제로 기록한다.
    """
    lines = module_text.split("\n")
    cards: list[dict[str, str]] = []
    index_entries: list[tuple[str, str]] = []
    problems: list[str] = []
    current: dict[str, str] | None = None
    pending_field: str | None = None
    in_index_section = False
    for line in lines:
        stripped = line.strip()
        header = EM_HEADER_RE.match(stripped)
        if header:
            current = {"em_id": header.group(1), "title": header.group(2)}
            cards.append(current)
            in_index_section = False
            pending_field = None
            continue
        if EM_MISPLACED_HEADER_RE.match(stripped):
            problems.append(f"em_header_unrecognized:{stripped[:40]} — EM 카드 제목은 `### EM-xxx 이름` 형식이어야 합니다")
            current = None
            pending_field = None
            continue
        if stripped.startswith("## "):
            in_index_section = "其他机制索引" in stripped
            current = None
            pending_field = None
            continue
        if current is not None and stripped.startswith("|"):
            pending_field = None
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if len(cells) >= 2:
                key = normalize_em_field(cells[0])
                if key not in EM_TABLE_HEADER_KEYS and not EM_TABLE_SEPARATOR_RE.match(key):
                    if key in EM_REQUIRED_FIELDS and key in current:
                        problems.append(f"{current['em_id']}:em_field_duplicate:{key}")
                    current[key] = cells[1]
            continue
        if current is not None:
            # 여러 행 값: 필드명 다음의 들여쓴 목록 행은 굵은 소제목이 있어도 이어지는 값이다.
            if pending_field is not None and stripped and line[:1] in (" ", "\t"):
                appended = stripped.lstrip("-*").strip()
                current[pending_field] = f"{current[pending_field]}；{appended}" if current[pending_field] else appended
                continue
            bold = EM_BOLD_FIELD_RE.match(stripped)
            if bold:
                key = normalize_em_field(bold.group(1))
                value = bold.group(2).strip()
                if key in EM_REQUIRED_FIELDS and key in current:
                    problems.append(f"{current['em_id']}:em_field_duplicate:{key}")
                current[key] = value
                pending_field = None if value else key
                continue
            if pending_field is not None and stripped.startswith("#"):
                pending_field = None
                continue
            if pending_field is not None and stripped:
                appended = stripped.lstrip("-*").strip()
                if appended:
                    current[pending_field] = (
                        f"{current[pending_field]}；{appended}" if current[pending_field] else appended
                    )
                continue
        if in_index_section and stripped:
            match = EM_INDEX_ID_RE.search(stripped)
            if match:
                parts = [part.strip() for part in re.split(r"[|｜]", stripped.strip("|｜ ")) if part.strip()]
                name = parts[1] if len(parts) >= 2 and parts[0] == match.group(1) else (parts[0] if parts else match.group(1))
                if name == match.group(1) and len(parts) >= 2:
                    name = parts[1]
                index_entries.append((match.group(1), name))
    return cards, index_entries, problems


def resolve_workspace(root: Path, explicit: Path | None = None) -> Path:
    """`작품분석실/`를 포함한 작업 공간을 찾는다. 유출 검사 명단과 EM 집합 검증이 여기에 의존한다.
    명시적 `--workspace`를 우선하며 없으면 `--root`부터 최대 5단계 위로 탐색한다.
    실패하면 빈 명단으로 대체하지 않고 오류를 낸다. 빈 집합은 유출 검사를 실행하지 않은 것과 같다.
    """
    if explicit is not None:
        if (explicit / "작품분석실").is_dir():
            return explicit
        raise ValueError(f"workspace_invalid:{explicit} 아래에 작품분석실/이 없습니다")
    candidate = root.resolve()
    for _ in range(6):
        if (candidate / "작품분석실").is_dir():
            return candidate
        if candidate.parent == candidate:
            break
        candidate = candidate.parent
    raise ValueError("workspace_not_located:--root의 상위에서 작품분석실/이 있는 폴더를 찾지 못했습니다. --workspace로 직접 지정하세요")


EM_ARROW_RE = re.compile(r"→|⟶|->")


def replaceable_antipattern_hits(value: str, names: set[str]) -> list[str]:
    """‘고유명→임의 X’ 안티패턴: 화살표 왼쪽이 인물 명단과 맞으면 신뢰도 높은 실제 참조다."""
    hits: set[str] = set()
    for segment in re.split(r"[；;，,、｜|]", value):
        if not EM_ARROW_RE.search(segment):
            continue
        left = EM_ARROW_RE.split(segment)[0]
        hits.update(name for name in names if name in left)
    return sorted(hits)


def character_names(workspace: Path, book: str) -> set[str]:
    role_dir = workspace / "작품분석실" / book / "인물"
    names: set[str] = set()
    if role_dir.is_dir():
        for entry in role_dir.rglob("*.md"):
            stem = re.sub(r"^\d+[-_.、\s]*", "", entry.stem)
            if len(stem) >= 2 and stem not in {"角色关系", "README", "readme", "索引", "目录"}:
                names.add(stem)
    return names


def load_numbered_rows(root: Path) -> tuple[list[tuple[int, dict[str, str]]], list[str]]:
    """파일 행 번호를 포함한 색인 행. 열 수가 틀리면 오류 보고 후 제외하되 실제 행 번호를 유지한다."""
    errors: list[str] = []
    index_path = root / "灵感索引.csv"
    try:
        with index_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows: list[tuple[int, dict[str, str]]] = []
            for row in reader:
                if None in row or None in row.values():
                    errors.append(f"line_{reader.line_num}:column_count_mismatch")
                    continue
                rows.append((reader.line_num, row))
            if tuple(reader.fieldnames or ()) != COLUMNS:
                errors.append("index_header_mismatch")
    except (OSError, UnicodeError, csv.Error) as exc:
        return [], [f"index_unreadable:{exc}"]
    return rows, errors


def load_rows(root: Path) -> tuple[list[dict[str, str]], list[str]]:
    numbered, errors = load_numbered_rows(root)
    return [row for _, row in numbered], errors


class RegisterError(ValueError):
    """문제 전체를 포함한 등록 실패. 반복 시행착오를 피하도록 한 번에 모두 보고한다."""

    def __init__(self, errors: list[str], warnings: list[str] | None = None) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors
        self.warnings = warnings or []


def analyze_module(root: Path, module_path: Path, book: str,
                   workspace: Path | None = None) -> dict[str, Any]:
    """작품의 EM 카드를 파싱·검사해 모든 errors/warnings를 모으고 파일은 쓰지 않는다."""
    errors: list[str] = []
    warnings: list[str] = []
    if not book or book in {".", ".."} or "/" in book or "\\" in book:
        raise RegisterError([f"book_name_invalid:{book!r} — --book에는 작품명만 입력하세요"])
    try:
        ws = resolve_workspace(root, workspace)
    except ValueError as exc:
        raise RegisterError([str(exc)]) from exc
    try:
        module_text = module_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise RegisterError([f"emotion_module_unreadable:{exc}"]) from exc
    cards, index_entries, problems = parse_em_module(module_text)
    if not cards and not index_entries:
        raise RegisterError(["emotion_module_has_no_em_cards"])
    errors.extend(problems)

    book_dir = ws / "작품분석실" / book
    if not book_dir.is_dir():
        errors.append(f"book_dir_not_found:작품분석실/{book} — 작업 공간 {ws}에 이 작품이 없어 고유명 유출 검사에 사용할 인물 목록을 얻을 수 없습니다")
    elif book_dir.resolve() not in module_path.resolve().parents:
        errors.append(f"module_book_mismatch:{module_path}은(는) 작품분석실/{book}/ 아래에 없습니다. --book과 --module은 같은 작품이어야 합니다")
    names = character_names(ws, book)
    if not names and book_dir.is_dir():
        warnings.append(f"character_roster_missing:작품분석실/{book}/인물/이(가) 없거나 비어 있습니다. 이번 고유명 유출 검사에 사용할 목록이 없으므로 카드에 고유명이 없는지 직접 확인하세요")

    seen: set[str] = set()
    atom_rows: list[dict[str, str]] = []
    for card in cards:
        em_id = card["em_id"]
        if em_id in seen:
            errors.append(f"em_id_duplicate:{em_id}")
            continue
        seen.add(em_id)
        card_errors = 0
        if not card["title"].strip():
            errors.append(f"{em_id}:em_title_missing — EM 카드 제목은 `### {em_id} 이름` 형식이어야 합니다")
            card_errors += 1
        absent = [field for field in EM_REQUIRED_FIELDS if field not in card]
        empty = [field for field in EM_REQUIRED_FIELDS if field in card and not card[field].strip()]
        if absent:
            errors.append(f"{em_id}:em_fields_missing:{'|'.join(absent)} — story-long-analyze Stage 3으로 돌아가 해당 모듈 카드를 완성하세요")
            card_errors += 1
        if empty:
            errors.append(f"{em_id}:em_field_value_empty:{'|'.join(empty)} — 필드는 있지만 값이 비어 있습니다. 여러 줄 값은 필드명 바로 다음에 적으세요(목록·문단 지원)")
            card_errors += 1

        field_texts = {"标题": card.get("title", "")}
        field_texts.update({field: card.get(field, "") for field in EM_LEAK_SCAN_FIELDS})
        hit_locations = {
            name: [field for field, text in field_texts.items() if name in text]
            for name in sorted(names)
            if any(name in text for text in field_texts.values())
        }
        antipattern = replaceable_antipattern_hits(card.get("可替换项", ""), names)
        non_portable = card.get("不可照搬", "")
        for name in antipattern:
            errors.append(f"{em_id}:replaceable_antipattern:{name} — ‘고유명→임의의 X’는 추상화 필드에 고유명을 남깁니다. ‘기능 역할→임의의 X’로 고치세요")
            card_errors += 1
        for name, locations in hit_locations.items():
            if name in antipattern:
                continue
            if name in non_portable:
                errors.append(f"{em_id}:source_specific_name_in_mechanism:{name}@{'|'.join(locations)} — 이 카드의 복제 금지 항목「不可照搬」에 적힌 고유명이 추상화 필드에도 남아 있습니다. Stage 3에서 고유명을 제거하고 다시 시도하세요")
                card_errors += 1
            else:
                warnings.append(f"{em_id}:leak_suspect:{name}@{'|'.join(locations)} — 인물 카드 이름과 일반 역할 용어를 자동 구분할 수 없습니다. 직접 확인하고 고유명이면 Stage 3에서 카드를 수정하세요")
        if card_errors == 0:
            atom_rows.append(_ia_row(book, em_id, card["title"], grade="full"))
    for em_id, title in index_entries:
        if em_id in seen:
            continue
        seen.add(em_id)
        for name in sorted(name for name in names if name in title):
            warnings.append(f"{em_id}:leak_suspect:{name}@색인 제목 — 직접 확인하고 고유명이면 Stage 3에서 색인 항목을 수정하세요")
        atom_rows.append(_ia_row(book, em_id, title, grade="index"))
    return {
        "book": book,
        "cards_full": len(cards),
        "cards_index": sum(1 for em_id, _ in index_entries if em_id not in {card["em_id"] for card in cards}),
        "character_roster": len(names),
        "errors": errors,
        "warnings": warnings,
        "atom_rows": atom_rows,
    }


def check_atoms(root: Path, module_path: Path, book: str,
                workspace: Path | None = None) -> dict[str, Any]:
    """읽기 전용 자체 검사. 작품 카드 수·명단 크기·전체 문제를 보고하며 어떤 파일도 쓰지 않는다."""
    try:
        report = analyze_module(root, module_path, book, workspace)
    except RegisterError as exc:
        return {"ok": False, "book": book, "errors": exc.errors, "warnings": exc.warnings}
    report.pop("atom_rows")
    report["ok"] = not report["errors"]
    return report


def register_atoms(root: Path, module_path: Path, book: str,
                   workspace: Path | None = None) -> dict[str, Any]:
    report = analyze_module(root, module_path, book, workspace)
    if report["errors"]:
        raise RegisterError(report["errors"], report["warnings"])
    atom_rows = report["atom_rows"]

    existing, errors = load_rows(root) if (root / "灵感索引.csv").is_file() else ([], [])
    if errors:
        raise RegisterError(errors, report["warnings"])
    preserved = [
        row
        for row in existing
        if not (row.get("layer") == "原子灵感" and row.get("source_book") == book)
    ]
    layer_order = {"原子灵感": 0, "单小说灵感合并": 1, "跨书灵感聚合": 2}
    combined = preserved + atom_rows
    combined.sort(
        key=lambda row: (
            layer_order.get(row.get("layer", ""), 9),
            row.get("source_book", ""),
            row.get("item_id", ""),
        )
    )
    atomic_write_text(root / "灵感索引.csv", csv_text(combined), encoding="utf-8")
    return {
        "ok": True,
        "book": book,
        "atoms_full": sum(1 for row in atom_rows if row["grade"] == "full"),
        "atoms_index": sum(1 for row in atom_rows if row["grade"] == "index"),
        "index_writes": 1,
        "character_roster": report["character_roster"],
        "warnings": report["warnings"],
    }


def _ia_row(book: str, em_id: str, title: str, grade: str) -> dict[str, str]:
    return {
        "item_id": em_id.replace("EM-", "IA-"),
        "layer": "原子灵感",
        "title": title.strip(),
        "source_book": book,
        "path": "",
        "source_ids": em_id,
        "novel_count": "1",
        "atom_count": "1",
        "grade": grade,
        "tags": "",
        "status": "active",
    }


def parse_tags(raw: str) -> tuple[dict[str, set[str]], list[str]]:
    result: dict[str, set[str]] = {}
    errors: list[str] = []
    if not raw.strip():
        return result, errors
    for part in raw.split("；"):
        if not part.strip():
            continue
        if "=" not in part:
            errors.append(f"tag_missing_equals:{part}")
            continue
        axis, values = (piece.strip() for piece in part.split("=", 1))
        if axis not in TAG_AXES:
            errors.append(f"tag_axis_unknown:{axis}")
            continue
        parsed = {value.strip() for value in values.split("|") if value.strip()}
        if not parsed:
            errors.append(f"tag_value_empty:{axis}")
            continue
        result.setdefault(axis, set()).update(parsed)
    return result, errors


def positive_int(raw: str) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 1 else None


def source_ids(raw: str) -> list[str]:
    return [item.strip() for item in re.split(r"[|；]", raw) if item.strip()]


def load_book_em_ids(workspace: Path, source_book: str) -> tuple[set[str], str | None]:
    module_path = workspace / "작품분석실" / source_book / "플롯" / "감정모듈.md"
    try:
        module_text = module_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return set(), "emotion_module_unreadable"
    cards, index_entries, _ = parse_em_module(module_text)
    ids = {card["em_id"] for card in cards} | {em_id for em_id, _ in index_entries}
    return ids, None


def validate(root: Path, workspace: Path | None = None) -> list[str]:
    numbered, errors = load_numbered_rows(root)
    rows = [row for _, row in numbered]
    try:
        ws: Path | None = resolve_workspace(root, workspace)
    except ValueError as exc:
        ws = None
        workspace_error = str(exc)
    vocabulary = load_vocabulary(root)
    if vocabulary is not None:
        errors.extend(vocabulary_errors(vocabulary))
    seen: set[tuple[str, str, str]] = set()
    ia_by_book: dict[str, dict[str, dict[str, str]]] = {}
    nm_by_book: dict[str, dict[str, dict[str, str]]] = {}
    active_single_book_cba: dict[str, int] = {}
    for number, row in numbered:
        item_id = row.get("item_id", "").strip()
        layer = row.get("layer", "").strip()
        book = row.get("source_book", "").strip()
        prefix = LAYERS.get(layer)
        if not prefix:
            errors.append(f"line_{number}:layer_invalid")
            continue
        unique_key = (layer, book if layer != "跨书灵感聚合" else "", item_id)
        if not item_id.startswith(prefix) or unique_key in seen:
            errors.append(f"line_{number}:item_id_invalid_or_duplicate")
        seen.add(unique_key)
        if layer == "原子灵感":
            ia_by_book.setdefault(book, {})[item_id] = row
            if row.get("path", "").strip():
                errors.append(f"line_{number}:ia_must_not_have_card_file")
            if row.get("grade", "").strip() not in {"full", "index"}:
                errors.append(f"line_{number}:ia_grade_invalid")
        else:
            if layer == "单小说灵感合并":
                nm_by_book.setdefault(book, {})[item_id] = row
            relative = row.get("path", "").strip().replace("\\", "/")
            if not relative.startswith(f"{layer}/") or ".." in relative.split("/"):
                errors.append(f"line_{number}:path_outside_layer")
                card_text = ""
            elif not (root / Path(relative)).is_file():
                errors.append(f"line_{number}:path_missing")
                card_text = ""
            else:
                try:
                    card_text = (root / Path(relative)).read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    card_text = ""
            if card_text and CARD_PATH_RE.search(card_text):
                errors.append(f"line_{number}:path_reference_in_card — 카드에는 ID만 허용합니다. 경로는 ID로 灵感索引.csv에서 조회하세요")
            if row.get("grade", "").strip():
                errors.append(f"line_{number}:grade_reserved_for_ia")
        tags, tag_errors = parse_tags(row.get("tags", ""))
        errors.extend(f"line_{number}:{error}" for error in tag_errors)
        if layer == "跨书灵感聚合":
            missing = REQUIRED_CBA_AXES - set(tags)
            if missing:
                errors.append(f"line_{number}:cba_tags_missing:{'|'.join(sorted(missing))}")
            if vocabulary is not None:
                for axis, values in sorted(tags.items()):
                    if axis not in vocabulary:
                        continue
                    for value in sorted(values - set(vocabulary[axis])):
                        errors.append(f"line_{number}:tag_value_not_in_vocabulary:{axis}={value} — 먼저 태그목록.md와 대조하세요. 같은 뜻이면 기존 값을 사용하고 새로운 분류라면 절차에 따라 목록부터 확장하세요")
            novel_count = positive_int(row.get("novel_count", ""))
            if novel_count is None:
                errors.append(f"line_{number}:novel_count_invalid")
            if positive_int(row.get("atom_count", "")) is None:
                errors.append(f"line_{number}:atom_count_invalid")
            if not row.get("source_ids", "").strip():
                errors.append(f"line_{number}:source_ids_missing")
            if novel_count == 1 and "单书假设" not in card_text:
                errors.append(f"line_{number}:single_book_hypothesis_marker_missing")
            if novel_count is not None and novel_count >= 2 and "跨书重复验证" not in card_text:
                errors.append(f"line_{number}:cross_book_validation_marker_missing")
        elif tags:
            errors.append(f"line_{number}:tags_reserved_for_cba")

    for book, atoms in ia_by_book.items():
        if ws is None:
            errors.append(f"book_{book}:{workspace_error}")
            module_error: str | None = "workspace_not_located"
            em_ids = set()
        else:
            em_ids, module_error = load_book_em_ids(ws, book)
            if module_error:
                errors.append(f"book_{book}:{module_error}")
        registered: set[str] = set()
        for item_id, row in atoms.items():
            refs = source_ids(row.get("source_ids", ""))
            if len(refs) != 1 or not refs[0].startswith("EM-"):
                errors.append(f"{book}/{item_id}:ia_source_em_invalid")
                continue
            if refs[0].replace("EM-", "IA-") != item_id:
                errors.append(f"{book}/{item_id}:ia_id_must_mirror_em_id")
            registered.add(refs[0])
            if positive_int(row.get("novel_count", "")) != 1 or positive_int(row.get("atom_count", "")) != 1:
                errors.append(f"{book}/{item_id}:ia_counts_must_equal_one")
        if not module_error and registered != em_ids:
            missing = sorted(em_ids - registered)
            extra = sorted(registered - em_ids)
            errors.append(f"book_{book}:ia_em_set_mismatch:missing={missing}:extra={extra}")

    for book, merges in nm_by_book.items():
        atoms = ia_by_book.get(book, {})
        atom_em = {row.get("source_ids", "").strip() for row in atoms.values()}
        for item_id, row in merges.items():
            refs = source_ids(row.get("source_ids", ""))
            if len(refs) < 2:
                errors.append(f"{book}/{item_id}:nm_requires_at_least_two_sources")
                continue
            unknown = sorted(set(refs) - atom_em)
            if unknown:
                errors.append(f"{book}/{item_id}:nm_source_em_missing:{unknown}")
            if positive_int(row.get("novel_count", "")) != 1:
                errors.append(f"{book}/{item_id}:nm_novel_count_must_equal_one")
            if positive_int(row.get("atom_count", "")) != len(set(refs) & atom_em):
                errors.append(f"{book}/{item_id}:nm_atom_count_mismatch")

    for row in rows:
        if row.get("layer") != "跨书灵感聚合":
            continue
        cba_id = row.get("item_id", "").strip()
        expanded: set[tuple[str, str]] = set()
        unknown_refs: list[str] = []
        for raw_ref in source_ids(row.get("source_ids", "")):
            if "/" not in raw_ref:
                unknown_refs.append(raw_ref)
                continue
            book, ref = raw_ref.rsplit("/", 1)
            if ref.startswith("NM-") and ref in nm_by_book.get(book, {}):
                for em_ref in source_ids(nm_by_book[book][ref].get("source_ids", "")):
                    expanded.add((book, em_ref))
            elif ref.startswith("EM-") and ref.replace("EM-", "IA-") in ia_by_book.get(book, {}):
                expanded.add((book, ref))
            else:
                unknown_refs.append(raw_ref)
        if unknown_refs:
            errors.append(f"{cba_id}:cba_source_missing:{sorted(unknown_refs)}")
        if not expanded:
            errors.append(f"{cba_id}:cba_requires_sources")
            continue
        novels = {book for book, _ in expanded}
        if len(novels) == 1 and row.get("status", "").strip() == "active":
            only = next(iter(novels))
            active_single_book_cba[only] = active_single_book_cba.get(only, 0) + 1
        if positive_int(row.get("novel_count", "")) != len(novels):
            errors.append(f"{cba_id}:cba_novel_count_mismatch")
        if positive_int(row.get("atom_count", "")) != len(expanded):
            errors.append(f"{cba_id}:cba_atom_count_mismatch")
    for book, count in sorted(active_single_book_cba.items()):
        if count > 3:
            errors.append(f"book_{book}:active_single_book_cba_limit_exceeded:{count}")
    return errors


def load_vocabulary(root: Path) -> dict[str, list[str]] | None:
    """`영감자료실/태그목록.md`의 `## 轴` 절 아래 `- 值` 행을 읽는다. 파일이 없으면 None이다."""
    path = root / "태그목록.md"
    if not path.is_file():
        return None
    vocabulary: dict[str, list[str]] = {}
    current_axis: str | None = None
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return None
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## "):
            axis = stripped[3:].strip()
            current_axis = axis if axis in TAG_AXES else None
            if current_axis is not None:
                vocabulary.setdefault(current_axis, [])
            continue
        if current_axis is not None and stripped[:2] in {"- ", "* "}:
            value = stripped[2:].split("（")[0].split("(")[0].strip()
            if value and value not in vocabulary[current_axis]:
                vocabulary[current_axis].append(value)
    return vocabulary


def vocabulary_errors(vocabulary: dict[str, list[str]]) -> list[str]:
    """단어 목록의 필수 축 완전성을 검사한다. 동의어 판정은 목록 확장 시 수동 비교에 맡긴다."""
    return [
        f"vocabulary_axis_missing:{axis}"
        for axis in sorted(REQUIRED_CBA_AXES - set(vocabulary))
    ]


def coverage(root: Path) -> dict[str, Any]:
    """증분 등록을 위한 기계적 안내: 어떤 active CBA 폐포에도 포함되지 않은 원자를 보고한다.
    작품 간 집계 LLM은 uncovered 원자와 기존 단일 작품 가설 카드만 보면 되며 포함된 EM 카드를 다시 읽을 필요가 없다. 읽기 전용이다.
    """
    rows, errors = load_rows(root)
    if errors:
        raise ValueError(";".join(errors))
    ia_by_book: dict[str, set[str]] = {}
    nm_members: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        book = row.get("source_book", "").strip()
        if row.get("layer") == "原子灵感" and row.get("status", "").strip() == "active":
            for ref in source_ids(row.get("source_ids", "")):
                ia_by_book.setdefault(book, set()).add(ref)
        elif row.get("layer") == "单小说灵感合并":
            nm_members[(book, row.get("item_id", "").strip())] = set(source_ids(row.get("source_ids", "")))
    covered: set[tuple[str, str]] = set()
    single_book_hypotheses: list[str] = []
    for row in rows:
        if row.get("layer") != "跨书灵感聚合" or row.get("status", "").strip() != "active":
            continue
        if positive_int(row.get("novel_count", "")) == 1:
            single_book_hypotheses.append(row.get("item_id", "").strip())
        for raw_ref in source_ids(row.get("source_ids", "")):
            if "/" not in raw_ref:
                continue
            book, ref = raw_ref.rsplit("/", 1)
            if ref.startswith("NM-"):
                covered.update((book, em_ref) for em_ref in nm_members.get((book, ref), set()))
            else:
                covered.add((book, ref))
    books: dict[str, dict[str, Any]] = {}
    uncovered_total = 0
    for book in sorted(ia_by_book):
        uncovered = sorted(em for em in ia_by_book[book] if (book, em) not in covered)
        uncovered_total += len(uncovered)
        books[book] = {
            "atoms": len(ia_by_book[book]),
            "covered": len(ia_by_book[book]) - len(uncovered),
            "uncovered": uncovered,
        }
    return {
        "ok": True,
        "books": books,
        "uncovered_total": uncovered_total,
        "single_book_hypotheses": sorted(single_book_hypotheses),
    }


def requested_tags(values: list[str]) -> dict[str, set[str]]:
    tags, errors = parse_tags("；".join(values))
    if errors:
        raise ValueError(";".join(errors))
    return tags


def query(root: Path, values: list[str], limit: int) -> dict[str, Any]:
    """matches와 함께 용어 수정 메타데이터를 반환한다. 요청 값이 라이브러리 전체에 없으면 `unmatched_tags`에 명시하고 조회 축의 기존 값 목록을 준다.
    0건이면 용어를 고쳐 다시 조회하며 단어 목록의 변화를 라이브러리에 없음으로 오인하지 않는다."""
    rows, errors = load_rows(root)
    if errors:
        raise ValueError(";".join(errors))
    wanted = requested_tags(values)
    axis_values: dict[str, set[str]] = {axis: set() for axis in wanted}
    matches: list[dict[str, Any]] = []
    for row in rows:
        if row.get("layer") != "跨书灵感聚合" or row.get("status") != "active":
            continue
        tags, tag_errors = parse_tags(row.get("tags", ""))
        if tag_errors:
            continue
        for axis in axis_values:
            axis_values[axis].update(tags.get(axis, set()))
        score = 0
        matched: list[str] = []
        core_match = False
        for axis, wanted_values in wanted.items():
            overlap = wanted_values & tags.get(axis, set())
            if overlap:
                score += (2 if axis in CORE_QUERY_AXES else 1) * len(overlap)
                matched.extend(f"{axis}={value}" for value in sorted(overlap))
                if axis in CORE_QUERY_AXES:
                    core_match = True
        if score <= 0 or not core_match:
            continue
        matches.append(
            {
                "item_id": row["item_id"],
                "title": row["title"],
                "path": row["path"],
                "score": score,
                "matched_tags": matched,
                "novel_count": positive_int(row.get("novel_count", "")) or 0,
                "atom_count": positive_int(row.get("atom_count", "")) or 0,
            }
        )
    matches.sort(key=lambda item: (-item["score"], -item["novel_count"], -item["atom_count"], item["item_id"]))
    unmatched = [
        f"{axis}={value}"
        for axis in sorted(wanted)
        for value in sorted(wanted[axis] - axis_values[axis])
    ]
    return {
        "matches": matches[: max(3, min(limit, 8))],
        "unmatched_tags": unmatched,
        "axis_inventory": {axis: sorted(found) for axis, found in sorted(axis_values.items())},
        "vocabulary_loaded": load_vocabulary(root) is not None,
    }


def resolve(root: Path, refs: list[str]) -> dict[str, Any]:
    """`书名/EM-xxx`, `书名/NM-xxx`, `CBA-xxx` ID를 읽을 위치로 해석한다. 필요할 때만 조회한다."""
    rows, errors = load_rows(root)
    if errors:
        raise ValueError(";".join(errors))
    by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        book = row.get("source_book", "").strip() if row.get("layer") != "跨书灵感聚合" else ""
        by_key[(book, row.get("item_id", "").strip())] = row
    resolved: list[dict[str, str]] = []
    missing: list[str] = []
    for raw_ref in refs:
        if "/" in raw_ref:
            book, ref = raw_ref.rsplit("/", 1)
        else:
            book, ref = "", raw_ref
        item = ref.replace("EM-", "IA-") if ref.startswith("EM-") else ref
        row = by_key.get((book if not item.startswith("CBA-") else "", item))
        if row is None:
            missing.append(raw_ref)
            continue
        if row.get("layer") == "原子灵感":
            location = f"작품분석실/{book}/플롯/감정모듈.md#{row.get('source_ids', '')}"
        else:
            location = row.get("path", "")
        resolved.append({"ref": raw_ref, "item_id": row.get("item_id", ""), "title": row.get("title", ""), "location": location})
    return {"ok": not missing, "resolved": resolved, "missing": missing}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_parser = subparsers.add_parser("register-atoms")
    register_parser.add_argument("--root", required=True, type=Path)
    register_parser.add_argument("--module", required=True, type=Path)
    register_parser.add_argument("--book", required=True)
    register_parser.add_argument("--workspace", type=Path, default=None)
    check_parser = subparsers.add_parser("check-atoms")
    check_parser.add_argument("--root", required=True, type=Path)
    check_parser.add_argument("--module", required=True, type=Path)
    check_parser.add_argument("--book", required=True)
    check_parser.add_argument("--workspace", type=Path, default=None)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--root", required=True, type=Path)
    validate_parser.add_argument("--workspace", type=Path, default=None)
    coverage_parser = subparsers.add_parser("coverage")
    coverage_parser.add_argument("--root", required=True, type=Path)
    query_parser = subparsers.add_parser("query")
    query_parser.add_argument("--root", required=True, type=Path)
    query_parser.add_argument("--tag", action="append", default=[])
    query_parser.add_argument("--limit", type=int, default=6)
    resolve_parser = subparsers.add_parser("resolve")
    resolve_parser.add_argument("--root", required=True, type=Path)
    resolve_parser.add_argument("--ref", action="append", default=[], required=True)
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    try:
        return run(args)
    except (OSError, UnicodeError) as exc:
        message = f"io_error:{exc}"
        print(json.dumps({"ok": False, "error": message, "errors": [message]}, ensure_ascii=False))
        return 2


def run(args: argparse.Namespace) -> int:
    if args.command == "register-atoms":
        try:
            payload = register_atoms(args.root, args.module, args.book.strip(), args.workspace)
        except ValueError as exc:
            errors = getattr(exc, "errors", None) or [str(exc)]
            warnings = getattr(exc, "warnings", [])
            print(json.dumps({"ok": False, "errors": errors, "warnings": warnings}, ensure_ascii=False))
            return 2
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    if args.command == "check-atoms":
        report = check_atoms(args.root, args.module, args.book.strip(), args.workspace)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["ok"] else 1
    if args.command == "validate":
        errors = validate(args.root, args.workspace)
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False))
        return 0 if not errors else 1
    if args.command == "coverage":
        try:
            payload = coverage(args.root)
        except ValueError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            return 2
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    if args.command == "resolve":
        try:
            payload = resolve(args.root, args.ref)
        except ValueError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            return 2
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if payload["ok"] else 1
    try:
        payload = query(args.root, args.tag, args.limit)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, **payload}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
