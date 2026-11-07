#!/usr/bin/env python3
"""build_outline_brief.py — 가져온 장편의 배치별 상세 개요 역산 작업 묶음을 만든다.

사용법:
    python build_outline_brief.py --project <작품디렉터리> --chapters A-B [--analysis <작품분석실/가져온작품명>]

가져오기는 작가의 시간선에 따라 단계별로 나눈다(SKILL.md의 시간표·인계 절). 상세 개요는 배치별 역산하며 읽기 부담이 전체 장 수에 비례해 늘지 않는다.
story-architect가 있으면 주 세션은 이 스크립트만 실행해 묶음 경로를 전달한다. 해당 에이전트에는 명령 실행 권한이 없다. 없으면 주 세션이 묶음을 읽고 이번 배치를 작성한다.
묶음은 작품 내부 `.story/work/개요작성/`에 저장하는 이번 작업의 입력 데이터이며 참조 문서가 아니다.

이번 배치에 필요한 것만 포함하므로 실행자는 장당 약 4K자의 요약 전문을 다시 읽지 않는다.
- 역산 규칙과 상세 개요 템플릿: references/outline-reverse-rules.md 전문.
- 각 장의 본문 경로, visible_chars_v1 기준 과거 길이(집필 시 장 검사와 같은 기준이며 story-architect는 직접 측정 불가),
  분석 라이브러리 요약에서 추출한 필드(핵심 사건·인과·상황 결과·관련 대상·정보 변화·상태 변화·결말 훅; 플롯 포인트는 제목｜유형｜기조만).
- 첫 장에는 도입 훅 작성용으로 앞 장 요약의 결말 훅을 추가한다.
- 장 범위가 이번 배치와 겹치는 권 개요의 플롯 단위 카드. 집필의 `outline_view.py --unit`과 같은 파서를 쓰므로 묶음에서 얻는 단위는 집필 때도 얻을 수 있다.
작품 설정과 작가 확정 사항은 넣지 않는다. 실행자가 규칙에 따라 프로젝트 파일과 `.story/work/가져오기기록.md`의 필요한 부분을 읽는다.

배치 크기는 총량으로 정한다. 요청은 10–20장(마지막 배치는 더 적어도 됨)이지만 묶음과 요약이 없어 읽어야 할 본문 총량이 약 25K자를 넘으면 뒤쪽 장부터 줄인다(10장 미만 가능, 최소 1장).
stdout에는 묶음 경로, 실제 장 범위와 다음 시작점, 실행자가 읽는 공백 제외 chars, 각 장 길이, 요약 없는 장을 한 줄 JSON으로 출력한다.
종료: 0 = 작성 완료, 2 = 인자 오류·본문/권 개요 누락·길이 측정 불가.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from outline_view import parse as parse_volume, unit_chapter_range  # noqa: E402
from wordcount_core import METRIC, WordcountError, find_chapter_file, measure_wordcount  # noqa: E402

RULES = Path(__file__).resolve().parent.parent / "references" / "outline-reverse-rules.md"
WORK_DIR = (".story", "work", "개요작성")
MIN_BATCH, MAX_BATCH = 10, 20
LOAD_LIMIT = 25000  # 실행자가 한 번에 읽는 공백 제외 글자 수. agent 템플릿이나 SKILL 진입점을 더해도 35K 이내다.
# 상세 개요 작성에 필요한 요약 필드(story-long-analyze 요약 투영과 동일한 이름). 이전 요약의 동의 레이블은 별칭에 둔다.
SUMMARY_FIELDS = (
    ("关键事件", ()),
    ("因果", ()),
    ("局面结果", ()),
    ("涉及", ("涉及人物", "出场人物")),
    ("信息变化", ()),
    ("状态变化", ()),
    ("章尾钩子", ("卡点与伏笔",)),
)
FIELD_NAMES = "|".join(name for field in SUMMARY_FIELDS for name in (field[0], *field[1]))
SUMMARY_LABELS = {'关键事件': '핵심 사건', '因果': '인과', '局面结果': '상황 결과', '涉及': '관련 인물', '信息变化': '정보 변화', '状态变化': '상태 변화', '章尾钩子': '장 끝 훅'}

# `**标签**：`(현재 투영과 이전 굵은 표기) 또는 굵게 하지 않은 `- 关键事件：`를 인식한다. 위 필드 이름만 허용한다.
LABEL_RE = re.compile(r"^\s*(?:[-*+]\s*)?(?:\*\*([^*]+?)\*\*|(%s))\s*[：:（(]" % FIELD_NAMES)
POINT_HEADER_RE = re.compile(r"^P(\d+)\s+\*\*(.+?)\*\*\s*[：:]\s*(.+)$")
POINT_TAG_RE = re.compile(r"^主题标签\s*[：:]?\s*[^|｜]*?\s*[|｜]\s*基调\s*[：:]?\s*(.*?)\s*$")


def emit(text: str, stream) -> None:
    """UTF-8로 통일해 출력한다. Windows 콘솔 기본값이 GBK/ASCII이면 중국어 직접 print가 실패한다."""
    stream.buffer.write((text + "\n").encode("utf-8"))
    stream.flush()


def weight(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def parse_range(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", value or "")
    if not match:
        raise SystemExit("ERROR: --chapters는 1-20처럼 A-B 형식으로 지정하세요")
    first = int(match.group(1))
    last = int(match.group(2) or first)
    if first < 1 or last < first:
        raise SystemExit("ERROR: --chapters 범위가 유효하지 않습니다")
    return first, last


def last_body_chapter(project: Path) -> int:
    numbers = [int(m.group(1)) for p in (project / "본문").glob("제*장*.md")
               if "_원본_" not in p.name and (m := re.match(r"^제0*(\d+)장", p.name))]
    return max(numbers, default=0)


def check_batch_size(first: int, last: int, final: int) -> None:
    size = last - first + 1
    if size > MAX_BATCH:
        raise SystemExit(f"ERROR: 상세 개요는 묶음당 최대 {MAX_BATCH}장입니다. 두 묶음으로 나누세요")
    # 작품의 마지막 배치만 10장 미만일 수 있다. 묶음이 너무 커 스크립트가 장 수를 줄이는 경우는 이 제한을 받지 않는다.
    if size < MIN_BATCH and last < final:
        raise SystemExit(f"ERROR: 상세 개요는 묶음당 최소 {MIN_BATCH}장입니다(작품의 마지막 묶음 제외). 범위를 제{first}~{min(final, first + MIN_BATCH - 1)}장으로 넓히세요")


def shown_path(path: Path, base: Path) -> str:
    """프로젝트 루트 내부는 상대 경로(story-architect가 루트 기준으로 해석), 외부는 절대 경로로 쓴다."""
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path)


def measure(project: Path, chapter: int) -> tuple[Path, str, int]:
    try:
        body = find_chapter_file(project / "본문", chapter, outline=False)
        text = body.read_bytes().decode("utf-8")
    except (WordcountError, OSError, UnicodeError) as exc:
        raise SystemExit(f"ERROR: 제{chapter}장 본문을 읽을 수 없습니다({exc}). 본문 이전을 먼저 완료하세요")
    result = measure_wordcount(text, chapter=chapter)
    if result["status"] != "measured":
        raise SystemExit(f"ERROR: 제{chapter}장 분량을 측정할 수 없습니다({result['invalid_reason']})")
    return body, text, result["actual"]


# ---------- 요약 필드 추출 ----------

def label_blocks(text: str) -> dict[str, str]:
    """요약을 `**标签**：` 기준으로 나눈다. 플롯 포인트 뒤 내용은 따로 파싱하며 필드 블록에 넣지 않는다."""
    blocks: dict[str, list[str]] = {}
    current = None
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if POINT_HEADER_RE.match(stripped) or stripped.startswith("#"):
            current = None
            continue
        match = LABEL_RE.match(line)
        if match:
            current = (match.group(1) or match.group(2)).strip()
            rest = re.split(r"[：:]", line, maxsplit=1)
            blocks.setdefault(current, []).append(rest[1] if len(rest) > 1 else "")
            continue
        if current is not None:
            blocks[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in blocks.items()}


def flatten(value: str) -> str:
    """목록·표를 한 줄로 압축한다. 표는 첫 열(인물명)만 취하며 머리글·구분 행은 건너뛴다."""
    rows = [line.strip() for line in value.split("\n") if line.strip()]
    if rows and all(row.startswith("|") for row in rows):
        names = [row.strip("|").split("|")[0].strip() for row in rows[2:]]
        return "、".join(name for name in names if name)
    return " ".join(re.sub(r"^(?:\d+[.、]|[-*+])\s*", "", row) for row in rows)


def summary_points(text: str) -> list[str]:
    lines = text.replace("\r\n", "\n").split("\n")
    points = []
    for index, line in enumerate(lines):
        header = POINT_HEADER_RE.match(line.strip())
        if not header:
            continue
        kind = re.split(r"[|｜]", header.group(3))[0].strip()
        kind = kind[2:].lstrip(" ：:") if kind.startswith("类型") else kind
        tone = "—"
        for follow in lines[index + 1:index + 12]:
            if POINT_HEADER_RE.match(follow.strip()):
                break
            tag = POINT_TAG_RE.match(follow.strip())
            if tag:
                tone = tag.group(1) or "—"
                break
        points.append(f"P{header.group(1)} {header.group(2).strip()}｜{kind}｜{tone}")
    return points


def summary_lines(text: str) -> list[str]:
    blocks = label_blocks(text)
    out = []
    for name, aliases in SUMMARY_FIELDS:
        raw = next((blocks[key] for key in (name, *aliases) if blocks.get(key)), "")
        out.append(f"- {SUMMARY_LABELS[name]}: {flatten(raw) or '(요약에 없음)'}")
    points = summary_points(text)
    out.append("- 사건 지점(제목｜유형｜기조): " + ("；".join(points) if points else "(요약에서 읽을 수 있는 사건 지점이 없음)"))
    return out


def previous_hook(analysis: Path, chapter: int) -> str | None:
    """앞 장 요약의 결말 훅. 앞 장이 묶음에 없으므로 이번 첫 장의 도입 훅 작성에 사용한다."""
    summary = analysis / "장별분석" / f"제{chapter - 1}장_요약.md"
    if chapter <= 1 or not summary.is_file():
        return None
    blocks = label_blocks(summary.read_text(encoding="utf-8-sig"))
    keys = ("章尾钩子", *dict(SUMMARY_FIELDS)["章尾钩子"])
    return next((flatten(blocks[key]) for key in keys if blocks.get(key)), None)


def chapter_block(project: Path, analysis: Path, chapter: int, first: int) -> tuple[str, int, int, bool]:
    """(이번 장 블록, 과거 길이, 실행자가 별도 읽을 본문량, 요약 누락 여부)를 반환한다."""
    body, body_text, actual = measure(project, chapter)
    head = [f"### 제{chapter}장", "",
            f"- 본문: `{shown_path(body, project.parent)}`; 목표 분량 {actual}자({METRIC})"]
    hook = previous_hook(analysis, chapter) if chapter == first else None
    if hook:
        head.append(f"- 앞 장(제{chapter - 1}장)의 끝 훅: {hook}")
    summary = analysis / "장별분석" / f"제{chapter}장_요약.md"
    if summary.is_file():
        lines = [f"- 요약 핵심(`{shown_path(summary, project.parent)}`에서 발췌): "] + [
            "  " + line for line in summary_lines(summary.read_text(encoding="utf-8").lstrip("﻿"))]
        return "\n".join(head + lines), actual, 0, False
    note = "- 요약: 찾지 못함. 해당 장 본문에서 역추론하고 근거가 부족한 부분은 [待补充](보완 필요)로 표시하세요"
    return "\n".join(head + [note]), actual, weight(body_text), True


# ---------- 권 개요 플롯 단위 ----------

def unit_cards(project: Path, first: int, last: int) -> list[str]:
    """각 권 개요에서 이번 배치와 장 범위가 겹치는 플롯 단위 카드를 하위 절과 함께 추출한다."""
    volumes = sorted((project / "개요").glob("권개요_제*권.md"))
    if not volumes:
        raise SystemExit("ERROR: 개요/에 권 개요가 없습니다. 구조 이전 단계에서 권 개요부터 확정하세요")
    out: list[str] = []
    for volume in volumes:
        lines, sections = parse_volume(volume.read_text(encoding="utf-8-sig"))
        for section in sections:
            if section.kind != "单元级" or "剧情单元" not in section.title or section.status == "已退役":
                continue
            span = unit_chapter_range([section], section.unit)
            if span is None or span[0] > last or span[1] < first:
                continue
            end = next((other.start for other in sections
                        if other.start > section.start and other.level <= section.level), len(lines))
            out += [f"출처: `{project.name}/개요/{volume.name}`", "", *lines[section.start:end], ""]
    if not out:
        raise SystemExit(f"ERROR: 권 개요에서 제{first}~{last}장 범위의 플롯 단위 카드를 찾을 수 없습니다(카드 제목 다음 행에 "
                         "‘> 作用域：单元级 {单元ID}’, 카드 안에 ‘- 章节范围：第A-B章’를 작성). 권 개요를 보완한 뒤 "
                         "outline_view.py --check --strict로 확인하세요")
    return out


# ---------- 묶음 구성 ----------

def render(project: Path, first: int, last: int, blocks: list[str]) -> str:
    head = (f"# 작업 묶음: 제{first}~{last}장 상세 개요 역추론(가져오기)\n\n"
            f"`{project.name}/개요/상세개요_제{first:03d}장.md`부터 `상세개요_제{last:03d}장.md`까지 장마다 파일 하나씩 전달하세요(동명 파일은 이 묶음에 따라 덮어씀). "
            f"본문·권 개요·`설정/`을 수정하거나 `추적/`을 만들지 마세요. 근거는 아래 장별 요약 핵심에서 가져오고 분석 자료의 요약 전체는 읽지 마세요. 필요한 필드가 요약 핵심에 없고 "
            f"실제 내용을 반드시 써야 할 때만 해당 장 본문의 관련 문단을 확인하세요. 작가 확정 사항은 `{project.name}/.story/work/가져오기기록.md`에 있습니다. "
            "묶음 밖의 집필 기법 파일은 읽지 마세요. 전달 후에는 작성한 파일 목록, 장마다 한 문장으로 정리한 핵심 사건, "
            "근거가 부족해 [待补充](보완 필요)로 표시한 항목만 보고하세요(없으면 ‘없음’).\n\n"
            "묶음에 나오는 검사는 전달 후 주 세션이 실행하므로 직접 명령을 실행하지 마세요. 필요한 측정 결과는 묶음에 포함되어 있습니다.")
    parts = [head, f"\n## 이번 묶음의 장\n\n경로 기준은 프로젝트 루트(`{project.parent}`)입니다.\n\n" + "\n\n".join(blocks),
             "\n## 이번 묶음에 해당하는 권 개요 플롯 단위\n\n" + "\n".join(unit_cards(project, first, last)).rstrip(),
             "\n---\n\n<!-- 자료: outline-reverse-rules.md -->\n\n" + RULES.read_text(encoding="utf-8").lstrip("﻿").strip()]
    return "\n".join(parts) + "\n"


def build(project: Path, analysis: Path, first: int, last: int) -> dict:
    if not RULES.is_file():
        raise SystemExit(f"ERROR: 참조 파일이 없습니다: {RULES}")
    fixed = weight(render(project, first, last, []))  # 묶음 머리·플롯 단위 카드·규칙은 장 수가 줄면 분량도 줄어든다.
    blocks: list[str] = []
    lengths: dict[int, int] = {}
    missing: list[int] = []
    load, extra_reading = fixed, 0
    for chapter in range(first, last + 1):
        block, actual, extra, absent = chapter_block(project, analysis, chapter, first)
        cost = weight(block) + extra
        if blocks and load + cost > LOAD_LIMIT:
            break  # 묶음이 이미 충분히 크므로 이번 장은 다음 배치로 넘긴다.
        blocks.append(block)
        lengths[chapter] = actual
        load += cost
        extra_reading += extra
        if absent:
            missing.append(chapter)
    end = first + len(blocks) - 1
    text = render(project, first, end, blocks)
    return {"text": text, "end": end, "lengths": lengths, "missing": missing,
            "chars": weight(text) + extra_reading}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="가져온 장편의 상세 개요를 묶음별로 역추론하는 작업 자료 생성")
    parser.add_argument("--project", required=True, type=Path, help="작품 폴더({가져온작품명}/)")
    parser.add_argument("--chapters", required=True, help="장 범위 A-B. 10~20장을 요청하며 묶음이 너무 크면 자동으로 줄임")
    parser.add_argument("--analysis", type=Path, help="분석 자료 폴더. 기본값은 작품 폴더의 상위/작품분석실/{작품폴더명}")
    args = parser.parse_args(argv)
    try:
        project = args.project.resolve()
        if not project.is_dir():
            raise SystemExit(f"ERROR: 작품 폴더가 없습니다: {args.project}")
        first, last = parse_range(args.chapters)
        final = last_body_chapter(project)
        if last > final:
            raise SystemExit(f"ERROR: 본문은 제{final}장까지만 이전되어 요청 범위를 벗어납니다")
        check_batch_size(first, last, final)
        analysis = (args.analysis or project.parent / "작품분석실" / project.name).resolve()
        result = build(project, analysis, first, last)
    except SystemExit as exc:
        emit(str(exc), sys.stderr)
        return 2
    end = result["end"]
    out_dir = project.joinpath(*WORK_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"가져오기상세개요_제{first:03d}-{end:03d}장.md"
    out.write_text(result["text"], encoding="utf-8")
    emit(json.dumps({"brief": str(out), "chapters": f"{first}-{end}",
                     "next": end + 1 if end < final else None, "chars": result["chars"], "limit": LOAD_LIMIT,
                     "metric": METRIC, "lengths": {str(k): v for k, v in result["lengths"].items()},
                     "missing_summaries": result["missing"]},
                    ensure_ascii=False), sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
