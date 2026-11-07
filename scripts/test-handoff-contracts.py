#!/usr/bin/env python3
"""작품 분석·순위 조사 산출물과 하위 단계 소비자 사이의 인계 계약.

생성하는 쪽은 템플릿이나 스크립트가 기준이고, 읽는 쪽은 문서에서 지정한 절·필드·열 이름·값이 기준이다.
읽는 쪽에서 지정한 대상이 생성 템플릿에 실제로 존재하는지 항목별로 검증한다. 검증 범위:

- 장편 분석 보고서: 각 소비자가 `작품분석보고서.md`의 절로 지정한 항목, 문체 생성에서 참조하는 절,
  빠른 미리 보기와 분석 보고서에 이름이 같은 두 절, story-explorer가 도입 세 장 심층 분석에서 읽는 필드.
- 감정 모듈 카드: inspiration_index.py의 EM_REQUIRED_FIELDS를 검사 필드 기준으로 삼는다.
  Stage 3 카드에서 같은 파서로 모든 필드를 읽을 수 있어야 하며 장편 집필 전 회수, 작가 보고서,
  story-explorer가 지정하는 필드도 일치해야 한다.
- 리듬 색인: 장편 집필 전 회수의 rhythm_reference와 story-explorer가 지정한 열/표가 리듬.md 템플릿에 있어야 한다.
- 단편 분석: 사건 지점 템플릿에 집필 단계가 지정한 필드가 있어야 하고 genre_detected의 모든 값이
  집필 장르 매핑 표에 있어야 한다. 단편 가져오기가 읽는 보고서 절이 존재하고 집필/가져오기가 읽는
  `_meta.json` 키가 output-contract의 schema에 있어야 한다.
- 단편 순위 조사: 소재 매칭이 추천하는 목표 플랫폼을 집필 설계 템플릿과 check-phase2-contract.js가
  허용해야 하며 조사에서 지원하는 모든 플랫폼이 대조 표에 있어야 한다. 집필 Phase 1이 읽는 결론 절과
  ‘复扫日期’가 템플릿에 있고, 감정 대조 표와 소재 매칭의 목표 감정은 집필 표의 여섯 종류만 사용하며 난도도 일치해야 한다.
- 장편 순위 조사: 분석 결과 반영과 새 작품 집필이 지정한 소재 결정 절/필드가 템플릿에 있어야 한다.
  ‘待拆文验证’와 ‘能爆的原因’은 같은 행에 있고 파일은 분석 단계가 찾는 `순위조사/{YYYYMMDD}/`에 있어야 한다.
- 보조 에이전트 배정: story-explorer / story-researcher 프롬프트 필드와 조회 유형이 보조 템플릿에 있어야 한다.
  검토에서 단편에 ‘无追踪’을 쓰면 consistency-checker에 단편 분기가 있어야 한다.
- 단편 가져오기 → 단편 집필 구상 검사: 가져오기의 `설정.md` 템플릿에 집필 템플릿의 모든 절과 기본 정보,
  설계 검증 필드가 있어야 한다. 가져오기 템플릿대로 채운 설정/절별 개요를 check-phase2-contract.js로
  검사하면 구상 때 정하도록 남긴 두 항목만 미통과여야 한다.
- 장편 가져오기 → 장편 집필: 가져오기 권별 개요를 그대로 저장하면 outline_view.py의 엄격한 검사를
  통과하고 단위별 카드를 얻을 수 있어야 한다. 카드에는 본문 조립 스크립트가 읽는 단위 필드가 있어야 하고,
  상세 개요 검사기가 보고하는 템플릿 출처가 각 사본의 스킬 안에 실제로 있어야 한다.
- 집필 ‘목표 플랫폼’ → 검토 플랫폼 표: 장편 장르 방향, 단편 설정 템플릿, 가져오기 Phase 1에서 쓸 수 있는
  모든 플랫폼이 분량 유형에 따라 검토 매핑 표에 있고 대상 플랫폼 표 파일이 존재해야 한다.
  검토가 consistency-checker를 호출할 때 템플릿이 요구하는 필드를 전달해야 한다.
- AI 문체 제거 → 집필자: 검사기의 모든 유형이 expression 안내 색인에 있고 blocking 굵은 표기가
  검사기와 일치해야 한다. 모든 호출자의 작업 레이블을 집필자가 인식하며 지정한 deslop-gates 절이 존재해야 한다.

마지막으로 손상한 입력 몇 가지를 사용해 단언이 실제로 오류를 내는지 확인한다.
"""

from __future__ import annotations

import json
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LONG_ANALYZE = "skills/story-long-analyze"
AUTHOR_FACING = f"{LONG_ANALYZE}/references/author-facing.md"
STAGE1 = f"{LONG_ANALYZE}/references/stage1-golden-chapters.md"
STAGE3 = f"{LONG_ANALYZE}/references/stage3-plot-rhythm.md"
STAGE5 = f"{LONG_ANALYZE}/references/stage5-report.md"
STYLE_GENERATOR = f"{LONG_ANALYZE}/references/style-profile-generator.md"
INSPIRATION_INDEX = f"{LONG_ANALYZE}/scripts/inspiration_index.py"
LONG_RECALL = "skills/story-long-write/references/benchmark-recall.md"
EXPLORER_LOAD = "skills/story-setup/references/agent-references/benchmark-style-load.md"
IMPORT_LONG = "skills/story-import/references/structure-mapping-long.md"
IMPORT_SHORT = "skills/story-import/references/structure-mapping-short.md"

SHORT_ANALYZE_SKILL = "skills/story-short-analyze/SKILL.md"
SHORT_GENRES = "skills/story-short-analyze/references/analysis-short-genres.md"
SHORT_STAGE23 = "skills/story-short-analyze/references/stage2-3-structure-emotion.md"
SHORT_STAGE46 = "skills/story-short-analyze/references/stage4-6-reversal-summary.md"
SHORT_CONTRACT = "skills/story-short-analyze/references/output-contract.md"
IMPORT_DEEP = "skills/story-import/references/deep-analysis.md"
SHORT_RECALL = "skills/story-short-write/references/benchmark-recall.md"
SHORT_DESIGN = "skills/story-short-write/references/workflow-design.md"
SHORT_DRAFT = "skills/story-short-write/references/workflow-draft.md"
PHASE2_CHECK = "skills/story-short-write/scripts/check-phase2-contract.js"
SHORT_SCAN_SKILL = "skills/story-short-scan/SKILL.md"
TOPIC_MATCH = "skills/story-short-scan/references/topic-match.md"

# 장편 분석 보고서를 읽는 파일: 장편 집필, 장편 순위 조사, 장편 가져오기, story-setup이 에이전트에 배포하는 자료.
LONG_REPORT_CONSUMER_GLOBS = (
    "skills/story-long-write/**/*.md",
    "skills/story-long-scan/**/*.md",
    "skills/story-setup/references/agent-references/*.md",
    "skills/story-setup/references/templates/agents/*.md",
    "skills/story-review/**/*.md",
    "skills/story-import/SKILL.md",
    IMPORT_LONG,
    STYLE_GENERATOR,
    STAGE5,
)
# 단편 분석 보고서를 읽는 파일.
SHORT_REPORT_CONSUMER_GLOBS = (
    "skills/story-short-write/**/*.md",
    IMPORT_SHORT,
)

# `작품분석보고서.md`의 ‘절’ 또는 ‘절’, 선택적으로 ‘절’의 ‘필드’를 포함한다.
REPORT_REF_RE = re.compile(
    r"(?:拆文报告|작품분석보고서)(?:\.md)?`?(?:의\s+)?((?:「[^」]+」[、与和及]?)+)(?:(?:的|\s*중\s*|의\s*)「([^」]+)」)?"
)
QUOTED_RE = re.compile(r"「([^」]+)」")
# ‘拆文报告·核心发现第 N 条’ 같은 결과 반영 근거 표기.
REPORT_CITE_RE = re.compile(r"拆文报告·([\u4e00-\u9fff]+?)第")
# Stage 3 템플릿 제목: ‘### Stage 3 리듬.md’와 ‘## 5. 리듬.md’를 모두 인정한다.
EM_TEMPLATE_HEADING = r"^#{2,3}\s+(?:Stage 3\s+|\d+\.\s*)?감정모듈\.md"
RHYTHM_TEMPLATE_HEADING = r"^#{2,3}\s+(?:Stage 3\s+|\d+\.\s*)?리듬\.md"


class Repo:
    """저장소 파일을 읽는다. 실패 사례 테스트에서는 overrides로 일부 파일 내용을 대체한다."""

    def __init__(self, overrides: dict[str, str] | None = None) -> None:
        self.overrides = overrides or {}

    def text(self, rel: str) -> str:
        if rel in self.overrides:
            return self.overrides[rel]
        path = ROOT / rel
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    def glob(self, patterns: tuple[str, ...]) -> list[str]:
        found: set[str] = set()
        for pattern in patterns:
            for path in ROOT.glob(pattern):
                if path.is_file():
                    found.add(path.relative_to(ROOT).as_posix())
        found.update(rel for rel in self.overrides if any(Path(rel).match(p) for p in patterns))
        return sorted(found)


# ---------- 공통 파싱 ----------


def fenced_block_after(text: str, heading_re: str) -> str:
    """heading_re가 있는 줄 다음 첫 코드 블록의 내용을 반환한다. 없으면 빈 문자열을 반환한다."""
    match = re.search(heading_re, text, re.M)
    if not match:
        return ""
    rest = text[match.end():]
    opening = re.search(r"^```[^\n]*\n", rest, re.M)
    if not opening:
        return ""
    body = rest[opening.end():]
    closing = re.search(r"^```\s*$", body, re.M)
    return body[: closing.start()] if closing else body


def headings(text: str) -> list[str]:
    return [m.group(2).strip() for m in re.finditer(r"^(#{1,6})\s+(.+?)\s*$", text, re.M)]


def table_header_cells(text: str) -> list[str]:
    """다음 줄이 구분선인 Markdown 표 머리글의 모든 셀을 반환한다."""
    lines = text.splitlines()
    cells: list[str] = []
    for i, line in enumerate(lines[:-1]):
        if line.strip().startswith("|") and re.match(r"^\s*\|?\s*:?-{3,}", lines[i + 1]):
            cells.extend(c.strip() for c in line.strip().strip("|").split("|") if c.strip())
    return cells


def tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    """[(머리글, 행 목록)]을 반환한다."""
    lines = text.splitlines()
    result: list[tuple[list[str], list[list[str]]]] = []
    i = 0
    while i < len(lines) - 1:
        line = lines[i].strip()
        if line.startswith("|") and re.match(r"^\s*\|?\s*:?-{3,}", lines[i + 1]):
            header = [c.strip() for c in line.strip("|").split("|")]
            rows: list[list[str]] = []
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                j += 1
            result.append((header, rows))
            i = j
        else:
            i += 1
    return result


def section_body(text: str, title: str) -> str:
    """제목이 title인 절의 본문을 다음 동급 또는 상위 제목 직전까지 반환한다."""
    match = re.search(rf"^(#{{1,6}})\s+{re.escape(title)}\s*$", text, re.M)
    if not match:
        return ""
    level = len(match.group(1))
    rest = text[match.end():]
    nxt = re.search(rf"^#{{1,{level}}}\s", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def split_terms(raw: str, seps: str) -> list[str]:
    return [t.strip() for t in re.split(f"[{seps}]", raw) if t.strip()]


def line_no(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


# ---------- 장편 분석 보고서 ----------


def long_report_template(repo: Repo) -> tuple[str, str]:
    text = repo.text(AUTHOR_FACING)
    return (
        fenced_block_after(text, r"^## 작품분석보고서\.md\s*$"),
        fenced_block_after(text, r"^## 빠른미리보기\.md\s*$"),
    )


def check_long_report(repo: Repo) -> list[str]:
    failures: list[str] = []
    report, preview = long_report_template(repo)
    if not report:
        return [f"{AUTHOR_FACING}: 找不到「## 작품분석보고서.md」下的报告模板代码块"]
    report_headings = set(headings(report))
    read_sections: dict[str, str] = {}

    for rel in repo.glob(LONG_REPORT_CONSUMER_GLOBS):
        text = repo.text(rel)
        for match in REPORT_REF_RE.finditer(text):
            where = f"{rel}:{line_no(text, match.start())}"
            sections = QUOTED_RE.findall(match.group(1))
            for section in sections:
                read_sections.setdefault(section, where)
            field = match.group(2)
            if field and sections:
                owner = sections[-1]
                body = section_body(report, owner)
                if owner in report_headings and not re.search(rf"(^|[|\s]){re.escape(field)}\s*[：:|]", body, re.M):
                    failures.append(f"{where}: 读拆文报告「{owner}」里的「{field}」，模板该节没写这一项")
        for match in REPORT_CITE_RE.finditer(text):
            read_sections.setdefault(match.group(1), f"{rel}:{line_no(text, match.start())}")
    if not read_sections:
        failures.append("长篇读取方里一处 `작품분석보고서.md`「小节」引用都没找到，检查正则或读取方清单")

    # 문체 생성: 보고서의 ‘文风一句话’를 반영하고 ‘写法技巧 Top 5’와 ‘可借鉴套路 Top 3’를 문체에 발췌한다.
    style = repo.text(STYLE_GENERATOR)
    style_refs = re.findall(r"报告「([^」]+)」", style) + re.findall(r"([\u4e00-\u9fff]+) Top \d+", style)
    if not style_refs:
        failures.append(f"{STYLE_GENERATOR}: 没找到它引用的拆文报告小节，确认读取写法后更新本测试")
    for section in style_refs:
        read_sections.setdefault(section, STYLE_GENERATOR)

    for section, where in sorted(read_sections.items(), key=lambda kv: kv[1]):
        if section not in report_headings:
            failures.append(f"{where}: 读拆文报告「{section}」，报告模板没有这一节")

    # 보고서 템플릿에서 ‘하위 단계가 읽으므로 원래 이름 유지’라고 지정한 절은 실제로 읽는 모든 절을 포함해야 한다.
    note = re.search(r"(?:有下游在读[^：\n]*：|후속 단계가 읽으므로 원래 이름을 유지할 절:)([^\n]+)", repo.text(AUTHOR_FACING))
    if not note:
        failures.append(f"{AUTHOR_FACING}: 拆文报告模板前缺「有下游在读、保留原名」的小节清单")
    else:
        protected = set(QUOTED_RE.findall(note.group(1)))
        for section in protected - report_headings:
            failures.append(f"{AUTHOR_FACING}: 保留清单里的「{section}」在报告模板里不存在")
        for section, where in sorted(read_sections.items(), key=lambda kv: kv[1]):
            if section in report_headings and section not in protected:
                failures.append(f"{AUTHOR_FACING}: 「{section}」被 {where} 读取，没写进「有下游在读、保留原名」清单")

    # 빠른 미리 보기 설명에서 분석 보고서와 이름이 같다고 정한 절은 양쪽 템플릿에 있어야 한다.
    shared = re.search(r"(?:沿用)?((?:「[^」]+」)+)(?:两节的同名同结构| 두 절의 이름·구조를 그대로 사용)", repo.text(AUTHOR_FACING))
    if not shared:
        failures.append(f"{AUTHOR_FACING}: 「빠른미리보기.md」说明里没找到与拆文报告同名的小节约定，确认写法后更新本测试")
    else:
        preview_headings = set(headings(preview))
        for section in QUOTED_RE.findall(shared.group(1)):
            if section not in report_headings or section not in preview_headings:
                failures.append(f"{AUTHOR_FACING}: 约定与拆文报告同名的「{section}」，快速预览和报告模板没有都写")

    # story-explorer가 도입 세 장 심층 분석에서 읽는 필드는 Stage 1 템플릿에 있어야 한다.
    explorer = repo.text(EXPLORER_LOAD)
    match = re.search(r"심층분석\.md`(?: 存在，再读取并提取|가 있으면 )((?:「[^」]+」)+)", explorer)
    if not match:
        failures.append(f"{EXPLORER_LOAD}: 没找到从深度拆解读取的字段，确认读取写法后更新本测试")
    else:
        stage1 = repo.text(STAGE1)
        for field in QUOTED_RE.findall(match.group(1)):
            if not re.search(rf"\*\*{re.escape(field)}\*\*", stage1):
                failures.append(f"{EXPLORER_LOAD}: 从深度拆解读「{field}」，Stage 1 深度拆解模板没有这一项")
    return failures


# ---------- 감정 모듈 카드 ----------


def check_em_cards(repo: Repo) -> list[str]:
    failures: list[str] = []
    module = runpy.run_path(str(ROOT / INSPIRATION_INDEX), run_name="handoff_contracts")
    required = tuple(module["EM_REQUIRED_FIELDS"])
    template = fenced_block_after(repo.text(STAGE3), EM_TEMPLATE_HEADING)
    if not template:
        return [f"{STAGE3}: 找不到「감정모듈.md」模板标题下的模板代码块"]

    cards, _index, problems = module["parse_em_module"](template)
    if not cards:
        failures.append(f"{STAGE3}: inspiration_index 从情绪模块模板里解析不出 EM 卡")
    for card in cards:
        missing = [f for f in required if not card.get(f, "").strip()]
        if missing:
            failures.append(f"{STAGE3}: 模板卡 {card.get('em_id')} 缺门禁字段 {'、'.join(missing)}")
    for problem in problems:
        failures.append(f"{STAGE3}: inspiration_index 解析模板报问题 {problem}")

    vocabulary = set(required) | set(headings(template)) | set(table_header_cells(template))
    for card in cards:
        vocabulary.update(k for k in card if k not in ("em_id", "title"))

    def exact(rel: str, pattern: str, label: str) -> None:
        text = repo.text(rel)
        match = re.search(pattern, text)
        if not match:
            failures.append(f"{rel}: 没找到{label}的字段清单，确认读取写法后更新本测试")
            return
        named = re.findall(r"`([^`]+)`", match.group(1)) if "`" in match.group(1) else split_terms(match.group(1), "、，,")
        where = f"{rel}:{line_no(text, match.start())}"
        extra = [n for n in named if n not in required]
        absent = [f for f in required if f not in named]
        if extra or absent:
            failures.append(
                f"{where}: {label}字段应与 EM_REQUIRED_FIELDS（{'、'.join(required)}）一致；"
                f"多出 {'、'.join(extra) or '无'}，缺 {'、'.join(absent) or '无'}"
            )

    exact(LONG_RECALL, r"`selected_emotion_module`(?:（| 1개를 고른다\. 필드는 )(.+?)(?:）|다\.)", "写前召回 selected_emotion_module ")

    def known(rel: str, pattern: str, label: str, seps: str) -> None:
        text = repo.text(rel)
        match = re.search(pattern, text)
        if not match:
            failures.append(f"{rel}: 没找到{label}，确认读取写法后更新本测试")
            return
        where = f"{rel}:{line_no(text, match.start())}"
        terms = QUOTED_RE.findall(match.group(1)) if "「" in match.group(1) else split_terms(match.group(1), seps)
        for term in terms:
            if not any(term in v for v in vocabulary):
                failures.append(f"{where}: {label}点名「{term}」，감정모듈.md 模板里没有这个字段或小节")

    known(EXPLORER_LOAD, r"(?:从|감정모듈\.md`에서 )([^。\n]+?)(?:中选择 1 条| 중) `selected_emotion_module`", "情绪模块取材范围", "、或")
    known(EXPLORER_LOAD, r'"selected_emotion_module": "<(?:从 플롯/감정모듈\.md 选出的|플롯/감정모듈\.md에서 선택한 )([^；;>"]+)', "selected_emotion_module 字段说明", "/、")
    return failures


# ---------- 전개 리듬 색인 ----------


def check_rhythm(repo: Repo) -> list[str]:
    failures: list[str] = []
    template = fenced_block_after(repo.text(STAGE3), RHYTHM_TEMPLATE_HEADING)
    if not template:
        return [f"{STAGE3}: 找不到「리듬.md」模板标题下的模板代码块"]
    columns = set(table_header_cells(template))
    titles = set(headings(template))

    text = repo.text(LONG_RECALL)
    match = re.search(r"`rhythm_reference`(?:（| 1개를 고른다\. )(.+?)(?:）|의 흐름이다\.)", text)
    if not match:
        failures.append(f"{LONG_RECALL}: 没找到 rhythm_reference 的组成说明，确认读取写法后更新本测试")
    else:
        where = f"{LONG_RECALL}:{line_no(text, match.start())}"
        for step in split_terms(match.group(1), "→"):
            step = {"핵심 정보": "关键信息", "확장 방식": "扩写方式", "감정 자극점": "情绪触动点", "폭발 지점": "爆发点", "여파/냉각": "余波/冷却"}.get(step, step)
            if step not in columns and not any(step in t for t in titles):
                failures.append(f"{where}: rhythm_reference 点名「{step}」，리듬.md 模板里没有这一列或这张表")

    explorer = repo.text(EXPLORER_LOAD)
    match = re.search(r"(?:从|리듬\.md`에서 )([^。\n]+?)(?:中选择 1 条| 중) `rhythm_reference`", explorer)
    if not match:
        failures.append(f"{EXPLORER_LOAD}: 没找到节奏取材范围，确认读取写法后更新本测试")
    else:
        where = f"{EXPLORER_LOAD}:{line_no(explorer, match.start())}"
        vocabulary = columns | titles
        terms = QUOTED_RE.findall(match.group(1)) if "「" in match.group(1) else split_terms(match.group(1), "、/")
        for term in terms:
            if not any(term in v for v in vocabulary):
                failures.append(f"{where}: 节奏取材点名「{term}」，리듬.md 模板里没有对应的列或表")

    # 가져오기에서 장르 방향을 작성할 때 리듬과 감정 모듈 항목을 번호로 참조한다.
    importer = repo.text(IMPORT_LONG)
    em_template = fenced_block_after(repo.text(STAGE3), EM_TEMPLATE_HEADING)
    for prefix_group, source, label in (
        (r"\{(RH/TR) (?:编号|번호)\}", template, "리듬.md"),
        (r"\{(EM)-001 (?:等|등)\}", em_template, "감정모듈.md"),
    ):
        match = re.search(prefix_group, importer)
        if not match:
            failures.append(f"{IMPORT_LONG}: 没找到按编号引用{label}的列，确认读取写法后更新本测试")
            continue
        for prefix in match.group(1).split("/"):
            if not re.search(rf"\b{prefix}-\d{{3}}", source):
                failures.append(f"{IMPORT_LONG}: 引用 {prefix} 编号，{label} 模板里没有 {prefix}-xxx 条目")
    return failures


# ---------- 단편 분석 ----------


def check_short_analyze(repo: Repo) -> list[str]:
    failures: list[str] = []

    # 사건 지점: 집필 단계가 지정하는 지점 필드가 지점 템플릿에 있어야 한다.
    node_template = fenced_block_after(repo.text(SHORT_STAGE23), r"^### (?:节点模板|노드 템플릿)")
    if not node_template:
        failures.append(f"{SHORT_STAGE23}: 找不到「### 节点模板」下的模板代码块")
    else:
        labels = set(re.findall(r"([一-鿿]{2,4})\{", node_template))
        text = repo.text(SHORT_RECALL)
        match = re.search(r"`사건노드\.md`(?: 看每个节点的([^，。\n]+)|에서는 노드별 (.+?)을 보고)", text)
        if not match:
            failures.append(f"{SHORT_RECALL}: 没找到读情节节点的字段说明，确认读取写法后更新本测试")
        else:
            where = f"{SHORT_RECALL}:{line_no(text, match.start())}"
            terms = split_terms(match.group(1), "、和") if match.group(1) is not None else re.findall(r"`([^`]+)`", match.group(2))
            if not terms:
                failures.append(f"{where}: 노드별로 읽을 필드가 없다")
            for term in terms:
                localized_term = {"事件": "사건"}.get(term, term)
                if term in node_template or localized_term in node_template or any(label in term for label in labels):
                    continue
                failures.append(
                    f"{where}: 读情节节点的「{term}」，节点模板里没有这一项（模板字段：{'、'.join(sorted(labels))}）"
                )

    # genre_detected: 분석에서 기록할 수 있는 모든 장르 값을 집필 단계의 매핑 표가 인식해야 한다.
    # 값의 출처: analysis-short-genres.md의 ‘题材路由’ 표 첫 열과 SKILL.md에서 지정한 기본 대체 값.
    skill = repo.text(SHORT_ANALYZE_SKILL)
    produced: list[str] = []
    routing = section_body(repo.text(SHORT_GENRES), "题材路由") or section_body(repo.text(SHORT_GENRES), "소재 분류")
    for header, rows in tables(routing):
        if header and header[0] in ("类型", "유형"):
            produced += [row[0] for row in rows if row and row[0]]
    produced += re.findall(r'扫不到(?:则 genre_detected = |写)[「"]([^」"]+)[」"]', skill)
    if not produced:
        failures.append(f"{SHORT_GENRES}: 没从「题材路由」表解析出 genre_detected 的取值，确认写法后更新本测试")
    recall = repo.text(SHORT_RECALL)
    mapping = next((rows for header, rows in tables(recall) if header and "genre_detected" in header[0]), None)
    if mapping is None:
        failures.append(f"{SHORT_RECALL}: 没找到 genre_detected → 题材包 映射表")
    else:
        accepted: set[str] = set()
        for row in mapping:
            accepted.update(split_terms(re.sub(r"[`]", "", row[0]), "/、（）() "))
        for genre in produced:
            if genre not in accepted:
                failures.append(f"{SHORT_RECALL}: genre_detected 可能取「{genre}」，题材包映射表里没有")

    # 단편 가져오기가 읽는 분석 보고서 절.
    short_titles: set[str] = set()
    for rel in (SHORT_STAGE23, SHORT_STAGE46):
        source = repo.text(rel)
        marker = source.find("## 输出模板")
        short_titles.update(headings(source[marker:] if marker >= 0 else source))
    for rel in repo.glob(SHORT_REPORT_CONSUMER_GLOBS):
        text = repo.text(rel)
        for match in REPORT_REF_RE.finditer(text):
            where = f"{rel}:{line_no(text, match.start())}"
            for section in QUOTED_RE.findall(match.group(1)):
                for part in split_terms(section, "/"):
                    if not any(part in title for title in short_titles):
                        failures.append(f"{where}: 读短篇拆文报告「{section}」，Stage 2-6 输出模板里没有「{part}」这一节")

    # 집필과 가져오기가 읽는 `_meta.json` 키는 output-contract의 schema 템플릿에 있어야 한다.
    schema = fenced_block_after(repo.text(SHORT_CONTRACT), r"^## `_meta\.json` schema")
    keys = set(re.findall(r'"([A-Za-z_]+)"\s*:', schema))
    if not keys:
        failures.append(f"{SHORT_CONTRACT}: 没解析出 `_meta.json` schema 模板的键，确认写法后更新本测试")
    else:
        named = 0
        for rel in (SHORT_RECALL, IMPORT_DEEP):
            text = repo.text(rel)
            for line_match in re.finditer(r"^.*_meta\.json.*$", text, re.M):
                for token in re.findall(r"`([A-Za-z_][A-Za-z0-9_.]*)`", line_match.group(0)):
                    token = (token[len("_meta.json"):] if token.startswith("_meta.json") else token).lstrip(".")
                    if not token or token.endswith(".json"):
                        continue
                    named += 1
                    for part in token.split("."):
                        if part not in keys:
                            where = f"{rel}:{line_no(text, line_match.start())}"
                            failures.append(f"{where}: 读 `_meta.json` 的「{part}」，output-contract 的 schema 里没有这个键")
        if not named:
            failures.append(f"{SHORT_RECALL}: 没找到读取 `_meta.json` 键的写法，确认读取写法后更新本测试")
    return failures


# 번역된 표시 이름을 변경하지 않은 런타임 열거 값으로 대응한다.
# 목록에 없는 값은 그대로 남으므로 잘못된 새 이름을 허용하지 않는다.
LOCALIZED_ENUMS = {
    "미련과 안타까움": "意难平", "풀리지 않는 아쉬움": "意难平",
    "반전의 충격": "反转震撼", "카타르시스": "爽感释放", "통쾌함의 해소": "爽感释放",
    "치유와 온기": "治愈温暖", "치유와 따뜻함": "治愈温暖",
    "곱씹을수록 두려움": "细思极恐", "공감과 감동": "共鸣感动",
    "상": "高", "중": "中", "하": "低",
    "치뎬": "起点", "판치에": "番茄", "진장": "晋江", "기타": "其他",
    "즈후 옌옌": "知乎盐言", "치마오": "七猫", "헤이옌": "黑岩", "훙궈": "红果",
    "뎬중": "点众", "미니프로그램": "小程序", "미정": "未定", "미기재": "未填写",
    "장편": "장편", "단편": "단편",
}


def canonical_enum(value: str) -> str:
    return LOCALIZED_ENUMS.get(value, value)


# ---------- 단편 순위 조사 → 집필 플랫폼 ----------


def phase2_platform_regex(repo: Repo) -> re.Pattern[str] | None:
    source = repo.text(PHASE2_CHECK)
    match = re.search(r"settings\.match\(/目标平台\\s\*\[：:\]\\s\*\((.+?)\)/\)", source)
    if not match:
        return None
    return re.compile(rf"^(?:{match.group(1)})$")


def check_short_platforms(repo: Repo) -> list[str]:
    failures: list[str] = []
    accepted = phase2_platform_regex(repo)
    if accepted is None:
        return [f"{PHASE2_CHECK}: 没解析出目标平台正则，确认写法后更新本测试"]

    design = repo.text(SHORT_DESIGN)
    match = re.search(r"- 目标平台：\{([^}]+)\}", design)
    if not match:
        return failures + [f"{SHORT_DESIGN}: 没找到设定模板的「目标平台」取值，确认写法后更新本测试"]
    choices = split_terms(match.group(1), "/")
    for choice in choices:
        if not accepted.match(choice):
            failures.append(f"{SHORT_DESIGN}: 目标平台可选「{choice}」，check-phase2-contract.js 不认")

    topic = repo.text(TOPIC_MATCH)
    mapping = None
    for header, rows in tables(topic):
        target_cols = [i for i, cell in enumerate(header) if ("目标平台" in cell or "목표 플랫폼" in cell) and i > 0]
        if target_cols:
            mapping = (header, rows, target_cols[0])
            break
    if mapping is None:
        failures.append(f"{TOPIC_MATCH}: 缺少「扫榜平台 → 写作目标平台」对照表（表头含「目标平台」的一列）")
        return failures
    header, rows, col = mapping
    covered: set[str] = set()
    for row in rows:
        if len(row) <= col:
            continue
        covered.update(split_terms(row[0], "/、 "))
        for target in split_terms(row[col], "/、"):
            target = re.sub(r"[（(].*$", "", target).strip()
            if target not in choices:
                failures.append(
                    f"{TOPIC_MATCH}: 对照表把「{row[0]}」推荐到「{target}」，写作端设定模板只认 {' / '.join(choices)}"
                )
            elif not accepted.match(target):
                failures.append(f"{TOPIC_MATCH}: 对照表目标平台「{target}」过不了 check-phase2-contract.js")

    described = re.search(r"조사합니다\. (.+?) 등의 인기 단편 데이터를 분석", repo.text(SHORT_SCAN_SKILL))
    if not described:
        failures.append(f"{SHORT_SCAN_SKILL}: 没从 description 解析出扫榜平台，确认写法后更新本测试")
    else:
        for platform in (canonical_enum(v) for v in split_terms(described.group(1), ",")):
            if not any(platform in name or name in platform for name in covered):
                failures.append(f"{TOPIC_MATCH}: 扫榜支持「{platform}」，对照表里没有这一行")
    return failures


# ---------- 단편 순위 조사 결론 → 집필 Phase 1 ----------

SHORT_WRITE_SKILL = "skills/story-short-write/SKILL.md"


def short_write_emotions(repo: Repo) -> dict[str, str]:
    """집필 Phase 1 감정 표: 감정 → 난도."""
    for header, rows in tables(repo.text(SHORT_WRITE_SKILL)):
        if header and header[0] == "감정 유형" and "난이도" in header:
            col = header.index("난이도")
            return {canonical_enum(row[0]): canonical_enum(row[col]) for row in rows if len(row) > col}
    return {}


def check_short_scan_handoff(repo: Repo) -> list[str]:
    failures: list[str] = []
    topic = repo.text(TOPIC_MATCH)
    template = fenced_block_after(topic, r"^## 단편순위조사결론\.md (?:模板|템플릿)")
    if not template:
        return [f"{TOPIC_MATCH}: 没找到「단편순위조사결론.md 模板」的代码块，确认写法后更新本测试"]

    # 집필 단계는 파일명으로 결론을 찾고 지정한 절과 ‘复扫日期’를 읽는다.
    write = repo.text(SHORT_WRITE_SKILL)
    read_line = re.search(r"^.*`단편순위조사결론\.md`.*$", write, re.M)
    if not read_line:
        failures.append(f"{SHORT_WRITE_SKILL}: 没找到读取 `단편순위조사결론.md` 的写法，确认读取写法后更新本测试")
    else:
        where = f"{SHORT_WRITE_SKILL}:{line_no(write, read_line.start())}"
        for name in re.findall(r"`(选题匹配)`", read_line.group(0)):
            if not re.search(rf"^##\s+{re.escape(name)}\s*$", template, re.M):
                failures.append(f"{where}: 读结论文件的「{name}」，topic-match 模板里没有这一节")
        if "재조사 날짜" in read_line.group(0) and not re.search(r"^- 复扫日期：", template, re.M):
            failures.append(f"{where}: 读结论文件的「复扫日期」，topic-match 模板文件头里没有这个字段")
    if "`단편순위조사결론.md`" not in repo.text(SHORT_SCAN_SKILL):
        failures.append(f"{SHORT_SCAN_SKILL}: 没写结论落到 `단편순위조사결론.md`，写作端按这个文件名找")

    # 소재 선택 시 `투고요건.md`를 읽으므로 이 파일 저장 방법이 SKILL에 있어야 한다. 플랫폼 참조는 선택한 것만 읽기 때문에
    # 특정 플랫폼 참조에만 쓰면 다른 플랫폼을 선택한 작가가 보낸 투고 요건은 저장되지 않는다.
    skill = repo.text(SHORT_SCAN_SKILL)
    if "`투고요건.md`" in skill and not re.search(r"^.*`투고요건\.md`에 저장합니다\..*$", skill, re.M):
        failures.append(f"{SHORT_SCAN_SKILL}: 选题时读 `투고요건.md`，SKILL 里没写把征稿要求存进这个文件")

    # 목표 감정과 난도는 집필 Phase 1 감정 표를 기준으로 한다.
    emotions = short_write_emotions(repo)
    if not emotions:
        return failures + [f"{SHORT_WRITE_SKILL}: 没解析出 Phase 1 情绪表（表头「情绪类型 … 难度」），确认写法后更新本测试"]
    scan_table = None
    for header, rows in tables(repo.text(SHORT_SCAN_SKILL)):
        if header and header[0] == "감정" and "난도" in header:
            scan_table = (rows, header.index("난도"))
            break
    if scan_table is None:
        failures.append(f"{SHORT_SCAN_SKILL}: 缺少情绪对照表（表头「情绪 … 难度」）")
    else:
        rows, col = scan_table
        seen = set()
        for row in rows:
            name = canonical_enum(row[0])
            seen.add(name)
            if name not in emotions:
                failures.append(f"{SHORT_SCAN_SKILL}: 情绪对照表的「{name}」不在写作端情绪表里（{' / '.join(emotions)}）")
            elif len(row) > col and canonical_enum(row[col]) != emotions[name]:
                failures.append(f"{SHORT_SCAN_SKILL}: 「{name}」难度写成「{row[col]}」，写作端是「{emotions[name]}」")
        for name in emotions:
            if name not in seen:
                failures.append(f"{SHORT_SCAN_SKILL}: 情绪对照表缺写作端的「{name}」")
    match = re.search(r"^- 目标情绪：\{([^}]+)\}", template, re.M)
    if not match:
        failures.append(f"{TOPIC_MATCH}: 模板缺「- 目标情绪：{{…}}」，写作端拿它当候选情绪")
    else:
        for choice in split_terms(re.sub(r"[，,].*$", "", match.group(1)), "/"):
            if choice not in emotions:
                failures.append(f"{TOPIC_MATCH}: 目标情绪可选「{choice}」，写作端情绪表里没有")
    return failures



# ---------- 장편 순위 조사 소재 결정 → 분석 결과 반영, 새 작품 집필 시작 ----------

LONG_SCAN_SKILL = "skills/story-long-scan/SKILL.md"
TOPIC_DECISION = "skills/story-long-scan/references/topic-decision.md"
LONG_ANALYZE_SKILL = f"{LONG_ANALYZE}/SKILL.md"
LONG_WRITE_SETUP = "skills/story-long-write/references/workflow-setup.md"

# 읽는 쪽에서 지정한 소재 결정 절이나 필드: (읽는 쪽, 원문의 표기, 템플릿 이름).
# 표기를 못 찾으면 읽는 쪽의 읽기 방식이 바뀐 것이므로 이 표 갱신을 알린다. 이름을 못 찾으면 템플릿 이름이 바뀌어 하위 단계 연결이 조용히 끊어진다.
TOPIC_READS = (
    (LONG_WRITE_SETUP, "「推荐选题」", "推荐选题"),
    (LONG_WRITE_SETUP, "`扫榜日期`", "扫榜日期"),
    (LONG_WRITE_SETUP, "성공 가능성 Y", "能爆的原因"),
    (LONG_WRITE_SETUP, "차별점 Z", "差异化定位"),
    (STAGE5, "「推荐选题」", "推荐选题"),
    (STAGE5, "「能爆的原因」", "能爆的原因"),
    (STAGE5, "「题材组合」", "题材组合"),
    (LONG_ANALYZE_SKILL, "`推荐选题`", "推荐选题"),
)


def check_long_scan_handoff(repo: Repo) -> list[str]:
    failures: list[str] = []
    topic = repo.text(TOPIC_DECISION)
    template = fenced_block_after(topic, r"^## 소재선정\.md (?:模板|템플릿)")
    if not template:
        return [f"{TOPIC_DECISION}: 没找到「소재선정.md 模板」的代码块，确认写法后更新本测试"]
    names = {re.sub(r"[：:].*$", "", h).strip() for h in headings(template)}
    names |= set(re.findall(r"^- ([^：\n]+)：", template, re.M))

    for rel, said, name in TOPIC_READS:
        if said not in repo.text(rel):
            failures.append(f"{rel}: 没找到读选题决策「{name}」的写法 {said}，确认读取写法后更新本测试")
        if name not in names:
            failures.append(f"{TOPIC_DECISION}: {rel} 读选题决策的「{name}」，模板里没有这一节或这个字段")

    # 분석 단계는 ‘能爆的原因’ 행만 바꿔 결과를 반영한다. 표식도 반드시 같은 행에 있어야 한다.
    line = re.search(r"^- 能爆的原因：.*$", template, re.M)
    if not line or "`待拆文验证`" not in line.group(0):
        failures.append(f"{TOPIC_DECISION}: 模板「能爆的原因」那一行要带 `待拆文验证`，拆文端按这一行回填")
    for rel in (STAGE5, LONG_ANALYZE_SKILL):
        if "待拆文验证" not in repo.text(rel):
            failures.append(f"{rel}: 没找到按「待拆文验证」回填的写法，确认读取写法后更新本测试")

    # 분석 단계가 `순위조사/*/소재선정.md`에서 찾으므로 순위 조사 단계는 `순위조사/{YYYYMMDD}/`에 파일을 저장해야 한다.
    if "순위조사/*/소재선정.md" not in repo.text(STAGE5):
        failures.append(f"{STAGE5}: 没找到去 `순위조사/*/소재선정.md` 找文件的写法，确认读取写法后更新本测试")
    elif "순위조사/{YYYYMMDD}/" not in (section_body(topic, "交付") or section_body(topic, "전달")):
        failures.append(f"{TOPIC_DECISION}: 拆文端去 `순위조사/*/소재선정.md` 找文件，交付一节没写落在 `순위조사/{{YYYYMMDD}}/`")

    # 집필 단계는 맨 앞의, 실현 가능성이 가장 높은 추천 소재를 선택하므로 템플릿에 실현 가능성 순 정렬을 명시해야 한다.
    if "실현 가능성이 가장 높은" in repo.text(LONG_WRITE_SETUP) and not any(term in topic for term in ("按可行性排序", "실현 가능성이 높은 순")):
        failures.append(f"{TOPIC_DECISION}: 写作端取排在最前的选题当可行性最高，模板没写按可行性排序")
    return failures


# ---------- 단편 가져오기 → 단편 집필 구상 검사 ----------

# 가져오기는 장르 묶음 선택을 이어쓰기 구상 단계에 남긴다. 이 두 항목은 반드시 미통과이고 나머지는 통과해야 한다.
IMPORT_SHORT_LEFT_FOR_DESIGN = {"phase2.genre-reference-declared", "phase2.genre-moves-declared"}
IMPORT_FIXTURE_VALUES = {
    "- 目标字数：": "- 目标字数：6000 字",
    "- 目标平台：": "- 目标平台：知乎盐言",
    "- 反转类型：": "- 反转类型：身份反转",
    "- 反转位置：": "- 反转位置：第 3 节 ÷ 共 4 节 = 75%",
    "- 付费点：": "- 付费点：第 2 节末",
    "- 反派设计：": "- 反派设计：不适用（家庭矛盾，没有单一反派）",
}


def import_short_fixture(template: str, outline_header: str) -> tuple[str, str]:
    """가져온 설정 템플릿을 완결 단편(4절, 제2절 끝에서 유료 전환)으로 채우고 절별 개요를 덧붙인다."""
    lines = []
    for line in template.splitlines():
        prefix = next((key for key in IMPORT_FIXTURE_VALUES if line.startswith(key)), None)
        lines.append(IMPORT_FIXTURE_VALUES[prefix] if prefix else re.sub(r"\{[^}]*\}", "原文证据", line))
    cells = len(split_terms(outline_header, "|"))
    rows = []
    for section in range(1, 5):
        row = ["开头", "主事件", "她发现账单{发现}", "平静→怀疑"] + ["原文证据"] * (cells - 5) + ["1500"]
        row[7] = "付费点" if section == 2 else "下一节接上"
        rows.append("| " + " | ".join(row) + " |")
    outline = "\n".join([outline_header, "|" + "---|" * cells, *rows]) + "\n"
    return "\n".join(lines) + "\n", outline


def check_import_short(repo: Repo) -> list[str]:
    failures: list[str] = []
    design = fenced_block_after(repo.text(SHORT_DESIGN), r"^#### 설정\.md 模板")
    ours = fenced_block_after(repo.text(IMPORT_SHORT), r"^## 설정\.md 模板")
    if not design or not ours:
        return [f"{IMPORT_SHORT}: 没找到导入或写作端的 설정.md 模板代码块，确认写法后更新本测试"]
    have = set(headings(ours))
    for title in headings(design):
        if "（" not in title and title not in have:  # 괄호가 있는 것은 선택 절이다(작품 전반의 소품, 벤치마크 요약).
            failures.append(f"{IMPORT_SHORT}: 设定模板缺写作端的「{title}」小节，续写构思会当成没写")
    for title in ("基本信息", "Phase 2 设计校验"):
        for label in re.findall(r"^- ([^：{\n]+)：", section_body(design, title), re.M):
            if not re.search(rf"^- {re.escape(label)}：", ours, re.M):
                failures.append(f"{IMPORT_SHORT}: 设定模板缺写作端「{title}」的「{label}」字段")

    node = shutil.which("node")
    header = re.search(r"^\| 结构段/五段功能 .*\|$", repo.text(IMPORT_SHORT), re.M)
    if node is None:
        print("跳过导入短篇构思检查夹具：没有 node")
        return failures
    if not header:
        return failures + [f"{IMPORT_SHORT}: 没找到小节大纲 12 列表头，确认写法后更新本测试"]
    settings, outline = import_short_fixture(ours, header.group(0))
    with tempfile.TemporaryDirectory(prefix="import-short-") as tmp:
        (Path(tmp) / "설정.md").write_text(settings, encoding="utf-8")
        (Path(tmp) / "구간개요.md").write_text(outline, encoding="utf-8")
        run = subprocess.run([node, str(ROOT / PHASE2_CHECK), "--json", tmp],
                             capture_output=True, encoding="utf-8")
    try:
        failed = {item["id"] for item in json.loads(run.stdout)["failures"]}
    except (ValueError, KeyError):
        return failures + [f"{PHASE2_CHECK}: 输出读不出来：{run.stderr.strip()[:200]}"]
    for check_id in sorted(failed - IMPORT_SHORT_LEFT_FOR_DESIGN):
        failures.append(f"{IMPORT_SHORT}: 照导入模板填好的设定过不了构思检查 {check_id}")
    # 가져오기는 이어쓰기 구상에서 누락 항목만 보완한다고 약속한다. 집필 구상은 ‘本书续写基线’을 인식해 [待补充]만 채우고 본문은 다음 절부터 이어 쓴다.
    design_text = repo.text(SHORT_DESIGN)
    if any(term in repo.text(IMPORT_SHORT) for term in ("只补缺项", "빠진 항목만 보충")) and not ("本书续写基线" in design_text and "[待补充]" in design_text):
        failures.append(f"{SHORT_DESIGN}: 导入说续写构思只补缺项，构思步骤没写有「本书续写基线」时只补 [待补充]")
    draft_line = next((line for line in repo.text(SHORT_DRAFT).splitlines() if "**가져온 프로젝트의 이어쓰기 기준**" in line), "")
    if "제 N+1절부터" not in draft_line:
        failures.append(f"{SHORT_DRAFT}: 导入的半成品要从下一节接着写，「导入项目续写基线」没写第 N+1 节")
    return failures


# ---------- 보조 에이전트 배정: 호출자 프롬프트 → 보조 템플릿 ----------

ROUTER = "skills/story/SKILL.md"
REVIEW_PROMPTS = "skills/story-review/references/agent-prompts.md"
AGENT_TEMPLATES = "skills/story-setup/references/templates/agents"
EXPLORER = f"{AGENT_TEMPLATES}/story-explorer.md"
RESEARCHER = f"{AGENT_TEMPLATES}/story-researcher.md"
CHECKER = f"{AGENT_TEMPLATES}/consistency-checker.md"


def prompt_keys(block: str) -> list[str]:
    """`键：{值}` 형식의 프롬프트 줄에 있는 키."""
    return [m.group(1).strip() for m in re.finditer(r"^([^：:\n{]+)[：:]", block, re.M)]


def check_agent_dispatch(repo: Repo) -> list[str]:
    """라우터가 explorer / researcher를, 검토가 consistency-checker를 배정할 때 프롬프트 필드는 템플릿이 인식하는 필드여야 한다."""
    failures: list[str] = []
    router = repo.text(ROUTER)
    explorer = repo.text(EXPLORER)
    researcher = repo.text(RESEARCHER)
    for label, heading, template, rel in (
        ("story-explorer", r"“이야기 자료 조회”는 `story-explorer`에 전달", explorer, EXPLORER),
        ("story-researcher", r"“자료 조사”는 `story-researcher`에 전달", researcher, RESEARCHER),
    ):
        block = fenced_block_after(router, heading)
        keys = prompt_keys(block)
        if not keys:
            failures.append(f"{ROUTER}: 找不到派 {label} 的 prompt 模板")
            continue
        protocol = section_body(template, "被调用协议")
        for key in keys:
            if f"`{key}`" not in protocol:
                failures.append(f"{ROUTER}: 派 {label} 的 prompt 字段「{key}」不在 {rel} 的被调用协议里")
    explorer_types = {
        row[0].strip("`") for header, rows in tables(explorer) if header and header[0] == "query_type" for row in rows
    }
    for header, rows in tables(router):
        if len(header) >= 2 and header[1] == "조회 유형":
            for row in rows:
                # 셀의 첫 백틱 값은 조회 유형이고 괄호 안은 매개변수 값이다.
                for query_type in re.findall(r"^`([a-z_]+)`", row[1]):
                    if query_type not in explorer_types:
                        failures.append(f"{ROUTER}: 查询类型 {query_type} 不在 {EXPLORER} 的 query_type 表里")
    # 검토 시 단편에 ‘无追踪’을 기입하면 검사자가 이 표기를 인식해야 한다. 그렇지 않으면 추적 자료 부재를 증거 부족으로 오판한다.
    if "「无追踪」" in repo.text(REVIEW_PROMPTS) and "「无追踪」" not in repo.text(CHECKER):
        failures.append(f"{CHECKER}: 审稿给短篇写「无追踪」，检查员模板没有对应的短篇分支")
    return failures


# ---------- 장편 가져오기 → 장편 집필 ----------

LONG_OUTLINE_VIEW = "skills/story-long-write/scripts/outline_view.py"
LONG_WRITER_PROMPT = "skills/story-long-write/scripts/build_writer_prompt.py"
OUTLINE_CONTRACT_COPIES = (
    "skills/story-long-write/scripts/check-outline-contract.js",
    "skills/story-import/scripts/check-outline-contract.js",
)


def check_import_long(repo: Repo) -> list[str]:
    """가져오기 권별 개요 템플릿을 그대로 저장해도 집필 단계의 구간 추출기가 엄격한 검사를 통과하고 단위별 카드를 얻을 수 있어야 한다."""
    failures: list[str] = []
    doc = repo.text(IMPORT_LONG)
    marker = "### 권 개요 역추론 템플릿(개요/권개요_제X권.md)"
    if marker not in doc:
        return [f"{IMPORT_LONG}: 没找到卷纲目标格式模板，确认写法后更新本测试"]
    after = doc.split(marker, 1)[1]
    if "```markdown\n" not in after:
        return [f"{IMPORT_LONG}: 卷纲模板不在 markdown 代码块里，确认写法后更新本测试"]
    template = after.split("```markdown\n", 1)[1].split("\n```\n", 1)[0]
    # 본문 조립 스크립트는 단위 카드에서 이 두 필드를 읽는다. 없으면 전체를 회수해야 한다.
    for field in re.findall(r'extract_field\(unit_block or "", "([^"]+)"\)', repo.text(LONG_WRITER_PROMPT)):
        if "／" not in field and f"- {field}：" not in template:
            failures.append(f"{IMPORT_LONG}: 卷纲单元卡缺写正文要读的「{field}」")
    with tempfile.TemporaryDirectory(prefix="import-volume-") as tmp:
        volume = Path(tmp) / "권개요_제1권.md"
        volume.write_text(template + "\n", encoding="utf-8")
        run = lambda *args: subprocess.run(
            [sys.executable, str(ROOT / LONG_OUTLINE_VIEW), *args, str(volume)],
            capture_output=True, encoding="utf-8")
        check = run("--check", "--strict")
        if check.returncode != 0:
            failures.append(f"{IMPORT_LONG}: 导入卷纲模板过不了写作端 outline_view --check --strict："
                            f"{(check.stdout + check.stderr).strip()[-200:]}")
        unit = run("--unit", "L1-01")
        if unit.returncode != 0 or "单元情绪引擎" not in unit.stdout:
            failures.append(f"{IMPORT_LONG}: 写作端按单元取不到导入卷纲的单元卡 L1-01")
    node = shutil.which("node")
    if node is None:
        print("跳过细纲检查回报出处的核对：没有 node")
        return failures
    with tempfile.TemporaryDirectory(prefix="outline-refs-") as tmp:
        stub = Path(tmp) / "상세개요_제001장.md"
        stub.write_text("### 第 1 章：空\n", encoding="utf-8")
        for rel in OUTLINE_CONTRACT_COPIES:
            run = subprocess.run([node, str(ROOT / rel), "--json", str(stub)], capture_output=True, encoding="utf-8")
            try:
                refs = {ref for item in json.loads(run.stdout)["repair_scope"] for ref in item["references"]}
            except (ValueError, KeyError):
                failures.append(f"{rel}: 输出读不出来：{run.stderr.strip()[:200]}")
                continue
            skill = Path(rel).parent.parent
            if not refs:
                failures.append(f"{rel}: 回报里没有可读的模板出处")
            for ref in sorted(refs):
                if not (ROOT / skill / ref).is_file():
                    failures.append(f"{rel}: 回报让读 {ref}，{skill.as_posix()} 里没有这个文件")
    return failures


# ---------- 집필 목표 플랫폼 → 검토 플랫폼 표; 검토 → consistency-checker ----------

REVIEW_SKILL = "skills/story-review/SKILL.md"
LONG_SETUP = "skills/story-long-write/references/workflow-setup.md"
IMPORT_SKILL = "skills/story-import/SKILL.md"


def review_platform_rows(repo: Repo) -> list[tuple[str, set[str], str]]:
    """검토의 ‘篇幅 | 目标平台 | 叠加的平台表’ 매핑 표: [(분량 유형, 플랫폼 값, 플랫폼 표 셀)]."""
    for header, rows in tables(repo.text(REVIEW_SKILL)):
        if header[:2] == ["분량", "목표 플랫폼"]:
            parsed = []
            for row in rows:
                if len(row) < 3:
                    continue
                values = {canonical_enum(re.sub(r"[（(].*?[）)]", "", v).strip()) for v in split_terms(row[1], ",")}
                parsed.append((canonical_enum(row[0]), values, row[2]))
            return parsed
    return []


def check_review_platforms(repo: Repo) -> list[str]:
    """집필/가져오기에서 ‘目标平台’에 쓸 수 있는 모든 값을 검토에서 분량 유형별 플랫폼 표 하나에 매핑하거나 추가 적용하지 않는다고 명시해야 한다."""
    failures: list[str] = []
    rows = review_platform_rows(repo)
    if not rows:
        return [f"{REVIEW_SKILL}: 找不到「篇幅 | 目标平台 | 叠加的平台表」映射表"]
    covered: dict[str, set[str]] = {"장편": set(), "단편": set()}
    for length, values, target in rows:
        if length not in covered:
            failures.append(f"{REVIEW_SKILL}: 平台映射表的篇幅「{length}」不是长篇/단편")
            continue
        covered[length] |= values
        for path in re.findall(r"`(story-review/references/rubrics/[^`]+\.md)`", target):
            if not repo.text(f"skills/{path}"):
                failures.append(f"{REVIEW_SKILL}: 平台映射表指向 {path}，文件不存在")

    producers: list[tuple[str, str, list[str]]] = []
    setup = re.search(r"- 目标平台：\{([^}；;]+)", repo.text(LONG_SETUP))
    if setup:
        producers.append((LONG_SETUP, "장편", split_terms(setup.group(1), "/")))
    else:
        failures.append(f"{LONG_SETUP}: 没找到题材定位模板的「目标平台」取值，确认写法后更新本测试")
    design = re.search(r"- 目标平台：\{([^}]+)\}", repo.text(SHORT_DESIGN))
    if design:
        producers.append((SHORT_DESIGN, "단편", split_terms(design.group(1), "/")))
    else:
        failures.append(f"{SHORT_DESIGN}: 没找到设定模板的「目标平台」取值，确认写法后更新本测试")
    imported = re.search(r"목표 플랫폼\(장편: ([^;]+); 단편: ([^)]+)\)", repo.text(IMPORT_SKILL))
    if imported:
        producers.append((IMPORT_SKILL, "장편", [canonical_enum(v) for v in split_terms(imported.group(1), "/")]))
        producers.append((IMPORT_SKILL, "단편", [canonical_enum(v) for v in split_terms(imported.group(2), "/")]))
    else:
        failures.append(f"{IMPORT_SKILL}: 没找到 Phase 1 的目标平台选项，确认写法后更新本测试")

    for where, length, values in producers:
        for value in values:
            if value not in covered[length]:
                failures.append(f"{where}: {length}目标平台可写「{value}」，{REVIEW_SKILL} 的平台映射表没有这一项")
    return failures


def check_review_checker_fields(repo: Repo) -> list[str]:
    """consistency-checker 템플릿이 호출자에게 요구하는 모든 필드를 검토 프롬프트에서 하나씩 전달해야 한다."""
    template = repo.text(CHECKER)
    match = re.search(r"호출자가 준((?:\s*/?\s*`[a-z_]+`)+)", template)
    if not match:
        return [f"{CHECKER}: 没找到「调用方随 prompt 传入的」字段，确认写法后更新本测试"]
    fields = re.findall(r"`([a-z_]+)`", match.group(1))
    prompts = repo.text(REVIEW_PROMPTS)
    start = re.search(r"^\*\*Agent 4: consistency-checker\*\*", prompts, re.M)
    end = re.search(r"^## ", prompts[start.end():], re.M) if start else None
    block = prompts[start.end(): start.end() + end.start()] if start and end else ""
    if not block:
        return [f"{REVIEW_PROMPTS}: 找不到 consistency-checker 的 prompt 代码块"]
    return [
        f"{REVIEW_PROMPTS}: consistency-checker 模板要求 prompt 带「{field}」，审稿端的 prompt 没写"
        for field in fields
        if not re.search(rf"^\s*{field}：", block, re.M)
    ]


# ---------- AI 문체 제거 → 집필자 ----------

DESLOP_DETECTOR = "skills/story-deslop/scripts/check-ai-patterns.js"
DESLOP_EXPRESSION = "skills/story-deslop/references/expression.md"
DESLOP_GATES = "skills/story-deslop/references/deslop-gates.md"
WRITER_TEMPLATE = f"{AGENT_TEMPLATES}/narrative-writer.md"
# narrative-writer에 AI 문체 제거를 맡기는 호출자. 작업 레이블은 집필자의 호출 규약이 인식하는 값이어야 한다.
DESLOP_WRITER_CALLERS = (
    "skills/story-deslop/references/agent-calls.md",
    "skills/story-long-write/references/agent-calls.md",
    "skills/story-short-write/references/agent-calls.md",
)


def check_deslop_handoff(repo: Repo) -> list[str]:
    failures: list[str] = []
    detector = repo.text(DESLOP_DETECTOR)
    m = re.search(r"blocking by default[^(]*\(([^)]*)\)", detector)
    blocking = {c.strip() for c in m.group(1).split("/")} if m else set()
    if not blocking:
        failures.append(f"{DESLOP_DETECTOR}：读不出 blocking 类别清单")
    node = shutil.which("node")
    if node is None:
        print("跳过检测类别索引核对：没有 node")
    else:
        listed = subprocess.run([node, str(ROOT / DESLOP_DETECTOR), "--list-review-classes"],
                                capture_output=True, encoding="utf-8")
        try:
            classes = json.loads(listed.stdout)
        except ValueError:
            classes = {}
            failures.append(f"{DESLOP_DETECTOR}：--list-review-classes 输出读不出来")
        expression = repo.text(DESLOP_EXPRESSION)
        index = expression[expression.find("## 스크립트 알림을 의미 판단에 연결하기"):]
        for cls in classes:
            bold = f"**`{cls}`**" in index
            if f"`{cls}`" not in index:
                failures.append(f"{DESLOP_EXPRESSION}：检测类别 {cls} 不在提示索引里")
            elif bold != (cls in blocking):
                failures.append(f"{DESLOP_EXPRESSION}：{cls} 的 blocking 加粗与检测器不一致")
    template = repo.text(WRITER_TEMPLATE)
    protocol = template[template.find("## 被调用协议"):]
    known_labels = set(re.findall(r"prompt 标「([^」]+)」", protocol))
    gate_headings = set(re.findall(r"^## (.+)$", repo.text(DESLOP_GATES), re.M))
    for rel in DESLOP_WRITER_CALLERS:
        text = repo.text(rel).replace("\\n", "\n")
        for label in re.findall(r"任务描述：([^\n`{]*去AI味[^\n`{]*)", text):
            if label.strip() not in known_labels:
                failures.append(f"{rel}：任务标签「{label.strip()}」写手不认得（认得：{sorted(known_labels)}）")
        for cited in re.findall(r"deslop-gates(?:\.md)?「([^」]+)」", text):
            if {"按检测类别或问题限定范围": "탐지 분류나 문제로 범위 제한"}.get(cited, cited) not in gate_headings:
                failures.append(f"{rel}：点名的 deslop-gates.md「{cited}」不存在")
    return failures


CHECKS = (
    check_long_report, check_em_cards, check_rhythm, check_short_analyze, check_short_platforms,
    check_short_scan_handoff, check_long_scan_handoff, check_import_short, check_agent_dispatch,
    check_import_long, check_review_platforms, check_review_checker_fields, check_deslop_handoff,
)


def run_all(repo: Repo) -> list[str]:
    failures: list[str] = []
    for check in CHECKS:
        failures.extend(check(repo))
    return failures


# ---------- 실패 사례: 입력을 손상시키면 단언이 반드시 오류를 내야 함 ----------


def mutated(rel: str, old: str, new: str) -> Repo | None:
    """rel의 마지막 old를 new로 바꾼다(보고 템플릿이 빠른 미리 보기 뒤에 있으므로 마지막 항목을 바꿔야 보고서가 수정됨)."""
    text = Repo().text(rel)
    if old not in text:
        return None
    head, _, tail = text.rpartition(old)
    return Repo({rel: head + new + tail})


NEGATIVE_CASES = (
    ("报告删掉「读者在追什么」", AUTHOR_FACING, "## 读者在追什么", "## 读者追读点", "读者在追什么"),
    ("报告「基本信息」不再写题材", AUTHOR_FACING, "题材：{장르}\n", "", "「题材」"),
    ("报告「基本信息」不再写目标平台", AUTHOR_FACING, "目标平台：{원작 플랫폼, 알 수 없으면 빈칸}\n", "", "「目标平台」"),
    ("快速预览改了「黄金三章评分」标题", AUTHOR_FACING, "## 黄金三章评分\n\n| 维度", "## 开篇评分\n\n| 维度", "黄金三章评分"),
    ("深度拆解模板改了「可借鉴要素」", STAGE1, "**可借鉴要素**", "**可学的**", "可借鉴要素"),
    ("短篇报告改了「人物分析」标题", SHORT_STAGE46, "### A. 人物分析", "### A. 人物", "人物分析"),
    ("短篇 schema 改了 reversal_type", SHORT_CONTRACT, '"reversal_type"', '"reversal_kind"', "reversal_type"),
    ("短篇 schema 改了 genre_detected", SHORT_CONTRACT, '"genre_detected"', '"genre"', "genre_detected"),
    ("情节节点模板丢掉位置", SHORT_STAGE23, "位置{N절, 약 X자} | ", "", "位置"),
    ("写前召回把「可替换项」写成别名", LONG_RECALL, "`可替换项`(교체 가능 항목)", "`可替换要素`(교체 가능 항목)", "可替换要素"),
    ("rhythm_reference 点名不存在的列", LONG_RECALL, "확장 방식 →", "확장 기법 →", "확장 기법"),
    ("단편 노드 읽기가 존재하지 않는 필드를 지정", SHORT_RECALL, "`位置`(위치), `功能`(기능)", "`未知字段`(미지 필드), `功能`(기능)", "未知字段"),
    ("情绪模块模板丢掉门禁字段", STAGE3, "| 情绪链 | {결핍", "| 情绪曲线 | {결핍", "情绪链"),
    ("写作端校验不再认黑岩", PHASE2_CHECK, "|黑岩|", "|", "黑岩"),
    ("扫榜结论改了「选题匹配」标题", TOPIC_MATCH, "## 选题匹配", "## 选题方向", "选题匹配"),
    ("扫榜结论文件头丢了复扫日期", TOPIC_MATCH, "- 复扫日期：{YYYYMMDD}\n", "", "复扫日期"),
    ("征稿要求只在平台参考里落盘", SHORT_SCAN_SKILL,
     "5. 작가가 원고 모집 조건을 주면 원문을 출력 디렉터리의 `투고요건.md`에 저장합니다. 소재, 글자 수, 마감일은 필수 조건으로 삼습니다.\n", "", "투고요건.md"),
    ("选题匹配目标情绪写成题材名", TOPIC_MATCH, "{意难平 / 反转震撼", "{虐恋 / 反转震撼", "虐恋"),
    ("扫榜情绪表难度和写作端相反", SHORT_SCAN_SKILL, "| 반전의 충격 | 미스터리, 정체성 뒤바뀜, 반전 | 상 |",
     "| 반전의 충격 | 미스터리, 정체성 뒤바뀜, 반전 | 하 |", "反转震撼"),
    ("选题决策模板丢了题材组合", TOPIC_DECISION, "- 题材组合：", "- 题材：", "题材组合"),
    ("待拆文验证挪出能爆的原因那一行", TOPIC_DECISION,
     "（假设，`待拆文验证`）\n", "\n- 拆文状态：`待拆文验证`\n", "待拆文验证"),
    ("选题决策不再落在扫榜日期目录", TOPIC_DECISION,
     "`순위조사/{YYYYMMDD}/`", "`选题/{YYYYMMDD}/`", "순위조사/*/소재선정.md"),
    ("导入短篇设定还用旧的核心反转小节", IMPORT_SHORT, "### 核心支点", "### 核心反转", "核心支点"),
    ("导入短篇设定丢了付费点字段", IMPORT_SHORT, "- 付费点：第 {N} 节末\n", "", "付费点"),
    ("导入短篇设定没写反派设计", IMPORT_SHORT, "- 反派设计：不适用（{이유}）\n", "", "villain-contract"),
    ("短篇构思不认导入的续写基线", SHORT_DESIGN, "「本书续写基线」가 있으면", "이어쓰기 기준이 있으면", "只补缺项"),
    ("短篇写正文不从导入的下一节接着写", SHORT_DRAFT, "본문은 제 N+1절부터 이어 쓰고", "본문은 이어 쓰고", "第 N+1 节"),
    ("路由派查资料助手用了模板不认的字段", ROUTER, "查询参数：{", "查询内容：{", "查询内容"),
    ("资料研究助手模板丢了 cdp_port", RESEARCHER, "- `cdp_port`: CDP 포트(선택, 기본 9222)\n", "", "cdp_port"),
    ("检查员模板丢了短篇分支", CHECKER, "프롬프트에 「无追踪」 명시", "프롬프트에 추적 없음 명시", "无追踪"),
    ("导入卷纲单元卡丢了作用域行", IMPORT_LONG, "> 作用域：单元级 L1-01\n", "", "outline_view"),
    ("导入卷纲单元卡丢了单元情绪引擎", IMPORT_LONG, "- 单元情绪引擎：", "- 情绪引擎：", "单元情绪引擎"),
    ("审稿平台映射漏了晋江", REVIEW_SKILL, "진장, 기타", "기타", "晋江"),
    ("审稿平台映射漏了黑岩", REVIEW_SKILL, "치마오, 헤이옌, 훙궈", "치마오, 훙궈", "黑岩"),
    ("审稿端不给 consistency-checker 传修订号", REVIEW_PROMPTS, "  state_revision：", "  修订号：", "state_revision"),
    ("去味索引漏了一类 blocking", DESLOP_EXPRESSION, "**`em-dash`**", "**`em_dash`**", "em-dash"),
    ("短篇派写手用了写手不认的去味标签", "skills/story-short-write/references/agent-calls.md",
     "任务描述：审查+去AI味", "任务描述：去AI味+格式检查", "写手不认得"),
    ("调用方点名的 deslop-gates 小节改了名", DESLOP_GATES,
     "## 탐지 분류나 문제로 범위 제한", "## 범위 대응", "按检测类别或问题限定范围"),
)


def run_negative_cases() -> list[str]:
    failures: list[str] = []
    for label, rel, old, new, expect in NEGATIVE_CASES:
        repo = mutated(rel, old, new)
        if repo is None:
            failures.append(f"负例「{label}」：{rel} 里找不到要改的原文「{old}」，更新负例")
            continue
        if not any(expect in f for f in run_all(repo)):
            failures.append(f"负例「{label}」：改坏后没有报出含「{expect}」的问题")
    return failures


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    failures = run_all(Repo())
    failures += run_negative_cases()
    if failures:
        print("交接契约检查失败：")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("交接契约检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
