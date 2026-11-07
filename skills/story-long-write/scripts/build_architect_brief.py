#!/usr/bin/env python3
"""build_architect_brief.py — 권 개요·배치 상세 개요 작성 시점에 필요한 절차·템플릿을 묶는다.
사용법:
    python build_architect_brief.py --project <작품디렉터리> --task world
    python build_architect_brief.py --project <작품디렉터리> --task volume [--volume N]
    python build_architect_brief.py --project <작품디렉터리> --task outline --chapters A-B
    python build_architect_brief.py --project <임시디렉터리> --task <작업> --rules-only   # 저장소 예산 측정

기획은 작가 확인 시점별로 나눈다(workflow-setup.md). 가장 무거운 권 개요·상세 개요는 story-architect가 새 컨텍스트에서 처리한다.
주 세션은 이 스크립트를 실행해 경로만 넘기고 묶음 내용을 읽지 않는다. 작품의 `.story/work/개요작성/`에 저장하며 참조 문서가 아닌 작업 입력이다.
세 작업 모두 외부에서 읽지 못하는 SKILL.md의 ‘新增物三级’ 판정 기준을 포함한다.
- world: workflow-setup.md Phase 2·설정 템플릿, character-basics.md, long-genre-mechanics.md의 핵심 소재 3단계·특전, character-relations.md 관계 유형, reader-contract-and-progression.md.
- volume: workflow-volume.md의 개요 편성법(척도·제출·자체 점검·핵심점법·비교 작품 이전·장 위치), artifact-protocols.md의 대강·권 개요 템플릿, outline-methods.md의 권 개요 편성법, reader-contract-and-progression.md(자체 점검 4번 계약 네 질문).
- outline: workflow-outline.md 편성법(배치 절차·상세 템플릿/검증·설정 보완·기초 자료), long-chapter-hooks.md의 결말 13형식·도입 7형식(이름·공식만, 예문 제외),
  character-basics.md의 주인공·조연 템플릿, plot-core-methods.md(첫 배치는 전문, 이후 도입 화제성 절 제외). 첫 장 포함 시 opening-design.md의 도입 계획도 넣는다.
주 세션용 읽기 목록·분업·작가 보고 절은 제외한다. 특정 작품에만 필요한 다중 비교 작품 참조·여성향·8노드·감정 모듈 공식·무대 전환·감정선 단계·곡선/반전·영감 라이브러리는
묶음 끝 조건부 읽기에 절대 경로와 소절로만 나열하며 조건 충족 시 읽는다. 작품 방향·설정·작가 구두 결정은 `설정/`에서 실행자가 필요한 부분을 읽는다.
`--rules-only`는 작품 권 개요 없이 규칙만 묶어 호출별 로드 예산을 잰다.
stdout 한 줄 JSON: 묶음 경로, 공백 제외 글자 수, 포함 자료. 종료 0=작성됨, 2=인자·자료 누락(권 단위가 요청 장 일부만 포괄하는 경우 포함).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from outline_view import parse as parse_volume, slice_arc, strip_retired, unit_chapter_range  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parent.parent
REFERENCES = SKILL_ROOT / "references"
WORK_DIR = (".story", "work", "개요작성")
# 묶음 밖 조건부 읽기: (파일, 소절 또는 None=전문, 조건). 실행자가 `설정/`을 읽고 조건을 판단한다.
CROSS_BOOK = ("cross-book-recall.md", None, "`설정/소재방향.md`의 비교 작품 등록「对标登记」에 작품이 2개 이상 있음")
INSPIRATION = ("cross-book-recall.md", "公共灵感标签召回", "작업 공간에 `영감자료실/`이 있음(일치 항목이 없어도 진행)")
ROMANCE = ("character-relations.md", "感情线阶段", "작품에 감정 서사가 있음")
CONDITIONAL = {
    "world": [("female-audience-writing.md", None, "여성 독자 대상 작품임"), ROMANCE, CROSS_BOOK, INSPIRATION],
    "volume": [CROSS_BOOK, ("outline-methods.md", "八节点故事结构", "주 비교 작품이 없음"),
               ("outline-methods.md", "情绪模块公式", "권 개요에 독자적으로 만든 단위가 있음"),
               ("outline-methods.md", "换地图", "이번 권에서 주요 무대를 바꾸거나 새 무대를 엶"),
               ("emotional-arc-design.md", "六种弧线速查", "감정 곡선 유형을 선택하기 어려움"),
               ("long-reversal.md", "反转类型", "이번 권에 반전을 계획함"), ROMANCE, INSPIRATION],
    "outline": [ROMANCE, CROSS_BOOK, INSPIRATION],
}


def read_reference(name: str) -> str:
    path = REFERENCES / name
    if not path.is_file():
        raise SystemExit(f"ERROR: 참조 파일이 없습니다: {path}")
    return path.read_text(encoding="utf-8").lstrip("﻿")


def section(text: str, start: str, end: str | None = None) -> str:
    """start 제목부터 end 제목 전까지 추출한다. end가 없으면 문말까지, start가 없으면 빈 값 대신 오류다."""
    match = re.search(rf"^#+\s*{re.escape(start)}.*$", text, re.M)
    if match is None:
        raise SystemExit(f"ERROR: 참조 파일에서 ‘{start}’ 절을 찾을 수 없습니다")
    stop = re.search(rf"^#+\s*{re.escape(end)}.*$", text[match.end():], re.M) if end else None
    return text[match.start(): match.end() + stop.start() if stop else len(text)].rstrip()


def drop_last_column(text: str) -> str:
    """표의 마지막 예문 열을 제외해 상세 개요가 훅 예문의 문장 모양을 그대로 베끼지 않게 한다."""
    return "\n".join("|".join(line.split("|")[:-2]) + "|" if line.startswith("|") else line
                     for line in text.splitlines())


def new_addition_tiers() -> str:
    """기획·설정에 필요한 SKILL.md ‘新增物三级’ 기준. 묶음 밖 SKILL.md는 읽을 수 없으므로 포함한다."""
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r"^> \*\*新增物三级\*\*.*?(?=^(?!>))", text, re.M | re.S)
    if match is None:
        raise SystemExit("ERROR: SKILL.md에서 추가 요소 3단계 분류「新增物三级」를 찾을 수 없습니다")
    return "\n".join(line[2:] if line.startswith("> ") else line.lstrip(">") for line in match.group(0).rstrip().splitlines())


def conditional_reads(task: str) -> str:
    lines = ["다음은 묶음 밖 자료입니다. 조건에 해당할 때 지정된 절만 읽고, 절을 지정하지 않았다면 전문을 읽으세요. 조건에 해당하지 않으면 읽지 마세요:"]
    for name, part, when in CONDITIONAL[task]:
        where = f"‘{part}’ 절" if part else "전문"
        lines.append(f"- {when}: `{REFERENCES / name}`의 {where} 읽기")
    return "\n".join(lines)


def emit(text: str, stream) -> None:
    """UTF-8로 통일해 출력한다. Windows 콘솔 기본값이 GBK/ASCII이면 중국어 직접 print가 실패한다."""
    stream.buffer.write((text + "\n").encode("utf-8"))
    stream.flush()


def render(sections, chosen, span, preamble) -> str:
    """outline_view.emit처럼 퇴역 항목을 빼고 감정 곡선을 단위별로 자르되 텍스트로 반환한다."""
    out = ["\n".join(strip_retired(preamble, False)).rstrip()] if preamble else []
    for sec in sections:
        if sec not in chosen:
            continue
        body = slice_arc(sec, span) if ("情绪弧线" in sec.title or "排班" in sec.title) else sec.lines
        out.append("\n".join(strip_retired(body, False)).rstrip())
    return "\n\n".join(out) + "\n"


def unit_closures(project: Path, first: int, last: int) -> list[tuple[str, str]]:
    """story-architect는 명령을 못 실행하므로 스크립트가 이번 장들을 포괄하는 플롯 단위 폐포를 미리 묶는다.
    `outline_view.py --unit U --stage outline`과 같으며 같은 권의 여러 단위 중 첫 단위에만 권 계약·상시 항목을 한 번 붙인다."""
    found: list[tuple[str, str]] = []
    covered: set[int] = set()
    undeclared: list[str] = []
    for volume in sorted((project / "개요").glob("권개요_제*권.md")):
        lines, sections = parse_volume(volume.read_text(encoding="utf-8"))
        # 단위 카드에 제목만 있고 범위 행이 없으면 추출기가 인식하지 못한다. 단위를 못 찾았다고만 하지 말고 빠진 행을 명시한다.
        undeclared += [f"{volume.name}「{s.title.strip()}」" for s in sections
                       if s.scope is None and s.unit and "剧情单元" in s.title]
        if any(s.scope and (s.kind is None or (s.kind != "卷级常任" and s.unit is None)) for s in sections):
            raise SystemExit(f"ERROR: {volume.name}의 적용 범위 선언이 유효하지 않습니다. 먼저 outline_view.py --check로 확인하고 수정하세요")
        active = [s for s in sections if s.status != "已退役"]
        shared = [s for s in active if s.kind == "卷级常任" or s.scope is None]
        units = sorted({s.unit for s in active if s.unit and s.kind == "单元级"})
        given = False
        for unit in units:
            span = unit_chapter_range(active, unit)
            if not (span and span[0] <= last and span[1] >= first):
                continue
            covered.update(range(span[0], span[1] + 1))
            live = [s for s in active if s.unit == unit and s.kind in ("单元级", "批次底稿")]
            if given:
                text = "(권 단위 계약과 상시 항목은 앞 구간과 같으므로 반복하지 않습니다.)\n\n" + render(sections, set(live), span, None)
            else:
                text = render(sections, set(shared + live), span, lines[:sections[0].start] if sections else None)
            given = True
            found.append((f"{volume.name} · 단위 {unit}(제{span[0]}~{span[1]}장)", text))
    missing = [n for n in range(first, last + 1) if n not in covered]
    if missing:
        hint = (f". 다음 단위 카드에 ‘> 作用域：单元级 {{单元ID}}’ 선언 행이 없습니다: {'、'.join(undeclared)}"
                if undeclared else "(단위 카드에 ‘> 作用域：单元级 {单元ID}’와 ‘章节范围：第A-B章’를 적으세요)")
        where = "해당 범위의 플롯 단위가 없음: " if not found else "플롯 단위가 일부 범위만 포함함. 누락: "
        raise SystemExit(f"ERROR: 권 개요에 {where}제{compress(missing)}장{hint}. 먼저 권 개요를 보완하세요"
                         "(`outline_view.py --check --strict`로 전체 문제를 확인)")
    return found


def compress(numbers: list[int]) -> str:
    """[4, 5, 6, 9] → 4-6、9"""
    spans, start = [], numbers[0]
    for prev, cur in zip(numbers, numbers[1:] + [None]):
        if cur != prev + 1:
            spans.append(f"{start}-{prev}" if start != prev else f"{start}")
            start = cur
    return "、".join(spans)


def weight(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def build(task: str, volume: int | None, chapters: tuple[int, int] | None,
          project: Path | None = None, rules_only: bool = False) -> tuple[str, list[str]]:
    outside = "집필 기법은 이 묶음과 맨 끝의 ‘조건부 읽기’ 중 해당하는 절만 읽으세요. "
    if task == "world":
        head = ("# 작업 묶음: 핵심 설정 제안\n\n"
                "아래 Phase 2에 따라 핵심 설정을 파일로 작성하세요: `설정/소재방향.md`(방향 설정 때 작성한 내용을 보완하며 작가가 확정한 내용은 삭제하지 않음), "
                "`설정/관계.md`, 주인공과 핵심 인물의 `설정/인물/{이름}.md`, 작품 전체에 영향을 주는 `설정/세계관/{주제}.md`. "
                "작가가 방향 설정 때 말한 내용은 `설정/소재방향.md`에 있으므로 먼저 읽으세요. 불확실한 것은 두 가지 후보로 제시해 작가가 결정하도록 하세요. "
                "물가·소득·능력 단계 같은 작품 전체 기준은 아래 추가 요소 분류「新增物三级」에 따라 작가에게 먼저 물어야 하므로 후보만 제시하세요. "
                f"권 개요와 본문은 작성하지 마세요. {outside}전달 후에는 작성한 파일 목록, 주인공과 핵심 갈등 각 한 문장, "
                "작가가 결정할 사항만 보고하세요(없으면 ‘없음’).")
        setup = read_reference("workflow-setup.md")
        parts = [("workflow-setup.md(Phase 2와 설정 템플릿)",
                  section(setup, "Phase 2：核心设定", "Agent 调用：story-architect + character-designer") + "\n\n"
                  + section(setup, "定设定时建的文件模板")),
                 ("character-basics.md", read_reference("character-basics.md")),
                 ("long-genre-mechanics.md(핵심 소재 3단계 발전, 특전)",
                  section(read_reference("long-genre-mechanics.md"), "核心梗三层递进设计", "微创新与差异化设计")),
                 ("character-relations.md(인물 관계 유형)",
                  section(read_reference("character-relations.md"), "人物关系类型", "感情流人设核心法")),
                 ("reader-contract-and-progression.md", read_reference("reader-contract-and-progression.md"))]
    elif task == "volume":
        label = f"제{volume}권" if volume else "이번 권"
        head = (f"# 작업 묶음: {label} 권 개요 작성\n\n"
                f"`개요/개요.md`의 권별 표(이미 있으면 이번 권 행만 보완)와 `개요/권개요_제{volume or 'X'}권.md`만 전달하세요. "
                "상세 개요와 본문을 쓰거나 `추적/`을 만들지 마세요. 작품 방향·설정·비교 작품 등록·작가 확정 사항은 `설정/`에서 읽으세요(먼저 "
                f"`설정/소재방향.md` 읽기). {outside}전달 후에는 작성한 파일 목록, 개요 자체 점검 1~4의 "
                "결론 각 한 문장, 작가가 결정할 사항만 보고하세요(없으면 ‘없음’).")
        parts = [("workflow-volume.md(개요 작성법)", section(read_reference("workflow-volume.md"), "排纲方法")),
                 ("artifact-protocols.md", read_reference("artifact-protocols.md")),
                 ("outline-methods.md(권 개요 구성법)", section(read_reference("outline-methods.md"), "卷纲排法", "换地图")),
                 ("reader-contract-and-progression.md", read_reference("reader-contract-and-progression.md"))]
    else:
        first, last = chapters
        head = (f"# 작업 묶음: 제{first}~{last}장 상세 개요 작성\n\n"
                f"`개요/상세개요_제{first:03d}장`부터 제{last:03d}장까지의 상세 개요, 개요 초안, 필요한 설정 보완만 전달하세요. 본문을 쓰거나 "
                "`추적/`을 만들지 마세요. 이번 묶음에 해당하는 권 개요 단위 구간은 맨 끝에 발췌했으므로 권 개요 전체는 읽지 마세요. 설정은 `설정/`에서 필요한 부분만 읽으세요. "
                f"{outside}전달 후에는 작성한 파일 목록, "
                "장마다 한 문장으로 정리한 핵심 사건, 작가가 결정할 사항만 보고하세요(없으면 ‘없음’).")
        basics = read_reference("character-basics.md")
        plot = read_reference("plot-core-methods.md")
        parts = [("workflow-outline.md(개요 작성법)", section(read_reference("workflow-outline.md"), "排纲方法")),
                 ("long-chapter-hooks.md(장 끝 훅 13종, 장 시작 훅 7종)",
                  drop_last_column(section(read_reference("long-chapter-hooks.md"), "章尾钩子 13 式", "章尾实战模板"))),
                 ("character-basics.md(주인공·조연 카드)", section(basics, "第1节：主角卡", "第3节"))]
        if first <= 3:
            parts += [("plot-core-methods.md", plot),
                      ("opening-design.md(도입부 계획)",
                       section(read_reference("opening-design.md"), "开篇规划", "开篇落笔"))]
        else:
            parts.append(("plot-core-methods.md(도입부 흡인 요소 제외)",
                          section(plot, "目标情绪与主角选择", "噱头分类与开篇流程")))
        if not rules_only:
            parts += [(f"권 개요 발췌: {name}", text) for name, text in unit_closures(project, first, last)]
    parts.append(("SKILL.md(추가 요소 3단계 분류)", new_addition_tiers()))
    parts.append(("조건부 읽기(묶음 외부)", conditional_reads(task)))
    body = [head + ("\n\n묶음의 절차에 나오는 명령(구간 추출, `--check`, `check-outline-contract.js`)은 전달 후 주 세션이 실행합니다. "
                    "직접 명령을 실행하지 마세요. 필요한 구간 추출 결과는 묶음에 포함되어 있습니다.")]
    for name, text in parts:
        body.append(f"\n---\n\n<!-- 자료: {name} -->\n\n{text.strip()}\n")
    return "\n".join(body), [name for name, _ in parts]


def parse_range(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", value or "")
    if not match:
        raise SystemExit("ERROR: --chapters는 1-10처럼 A-B 형식으로 지정하세요")
    first = int(match.group(1))
    last = int(match.group(2) or first)
    if first < 1 or last < first:
        raise SystemExit("ERROR: --chapters 범위가 유효하지 않습니다")
    return first, last


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="story-architect의 권·상세 개요 작업 묶음 생성")
    parser.add_argument("--project", required=True, type=Path, help="작품 폴더")
    parser.add_argument("--task", required=True, choices=("world", "volume", "outline"))
    parser.add_argument("--volume", type=int, help="권 번호(volume 작업)")
    parser.add_argument("--chapters", help="장 범위 A-B(outline 작업)")
    parser.add_argument("--rules-only", action="store_true", help="규칙만 묶고 작품의 권 개요는 제외(예산 검사 측정용)")
    args = parser.parse_args(argv)
    try:
        if not args.project.is_dir():
            raise SystemExit(f"ERROR: 작품 폴더가 없습니다: {args.project}")
        chapters = parse_range(args.chapters) if args.task == "outline" else None
        if args.task == "outline" and chapters[1] - chapters[0] >= 10:
            raise SystemExit("ERROR: 상세 개요는 묶음당 최대 10장입니다. 두 묶음으로 나누세요")
        text, included = build(args.task, args.volume, chapters, args.project, args.rules_only)
    except SystemExit as exc:
        emit(str(exc), sys.stderr)
        return 2
    out_dir = args.project.joinpath(*WORK_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.task == "world":
        name = "핵심설정.md"
    elif args.task == "volume":
        name = f"권개요_제{args.volume}권.md" if args.volume else "권개요.md"
    else:
        name = f"상세개요_제{chapters[0]:03d}-{chapters[1]:03d}장.md"
    out = out_dir / name
    out.write_text(text, encoding="utf-8")
    emit(json.dumps({"brief": str(out), "chars": weight(text), "includes": included}, ensure_ascii=False), sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
