#!/usr/bin/env python3
"""권 개요 구간 추출기 — 권 개요 전문을 읽지 않고도 작업할 수 있게 한다.

선언된 범위로 권·단위·배치 자료를 선택한다. 범위 없는 이전 절은 보수적으로 포함하고 경고한다.
각 ## / ### / #### 제목의 다음 비어 있지 않은 행에 범위를 적는다:
    > 作用域：卷级常任
    > 作用域：单元级 D1-03
    > 作用域：批次底稿 D1-03｜状态：在用
    > 作用域：批次底稿 D1-02｜状态：已退役
퇴역 행: `⊘`로 시작하는 목록·표 행은 기본적으로 걸러 낸다.
사용법:
    outline_view.py --toc   권개요.md
    outline_view.py --unit D1-03 권개요.md
    outline_view.py --contract 권개요.md
    outline_view.py --check 권개요.md
어느 하위 명령이든 --history를 추가하면 퇴역 행도 출력한다.
"""
import argparse
import io
import re
import sys

HEADING = re.compile(r"^(#{2,4})\s+(.*\S)\s*$")
SCOPE = re.compile(r"^>\s*作用域[：:]\s*(.+?)\s*$")
RETIRED_LINE = re.compile(r"^\s*(?:[-*]\s*)?⊘|^\s*\|\s*⊘")
# 단위 블록 안에 있으면 안 되는 권 전체 표현. 있으면 상시 규칙을 잘못 배치한 것이다.
LEAK = re.compile(r"全卷常任|全程生效|全卷生效|本单元起常任|自 ?[LD]\d+-\d+ ?起生效")
# 권 단위 포인터 행은 유출이 아니다. 단위 블록은 상시 규칙을 참조할 수 있지만 반복 서술하면 안 된다.
POINTER = re.compile(r"全卷常任裁定|已提为卷级|不复读|规则本身见|见「全卷")
UNIT_IN_TITLE = re.compile(r"(?<![\w-])([LD]\d+-\d+|U\d+)(?![\w-])")
# 배치 기초 자료의 여러 장에 걸친 명령은 집필 시에도 유효한 제약이다. 집필 프로필에는 기초 자료가 없으므로 하위 자료로 내려야 한다.
IMPERATIVE = re.compile(r"全程不许|一律不许|往后任何章|此后不再|往后每|从此不|终局前不")
CH_RANGE = re.compile(r"章节范围[：:]\s*第\s*(\d+)\s*[-–—~至]\s*(\d+)\s*章")
# 감정 곡선의 장별 행: 첫 열의 ‘12’와 템플릿의 ‘第12章’을 모두 인식한다.
ARC_ROW = re.compile(r"^\|\s*第?\s*(\d+)\s*章?\s*\|")


def read(path):
    with io.open(path, encoding="utf-8-sig") as handle:
        return handle.read()


class Section:
    __slots__ = ("level", "title", "start", "end", "scope", "kind",
                 "unit", "status", "lines")

    def __init__(self, level, title, start):
        self.level = level
        self.title = title
        self.start = start          # 제목 행 번호(0부터 시작).
        self.end = None
        self.scope = None           # 원래 범위 문자열, None은 미선언.
        self.kind = None            # 권 단위 상시 / 단위별 / 배치 기초 자료
        self.unit = None
        self.status = "在用"
        self.lines = []


def parse(text):
    lines = text.split("\n")
    sections = []
    fence = None
    for index, line in enumerate(lines):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        match = HEADING.match(line)
        if match:
            if sections:
                sections[-1].end = index
            sections.append(Section(len(match.group(1)), match.group(2), index))
    if sections:
        sections[-1].end = len(lines)
    for section in sections:
        section.lines = lines[section.start:section.end]
        for candidate in section.lines[1:]:
            if not candidate.strip():
                continue
            scope_match = SCOPE.match(candidate)
            if scope_match:
                section.scope = scope_match.group(1)
            break
        if section.scope:
            head = section.scope.split("｜")[0].strip()
            if head == "卷级常任":
                section.kind = "卷级常任"
            elif re.fullmatch(r"单元级(?:\s+[A-Za-z][\w-]*)?", head):
                section.kind = "单元级"
            elif re.fullmatch(r"批次底稿(?:\s+[A-Za-z][\w-]*)?", head):
                section.kind = "批次底稿"
            found = re.search(r"^(?:单元级|批次底稿)\s+([A-Za-z][\w-]*)$", head)
            if found:
                section.unit = found.group(1)
            if "已退役" in section.scope:
                section.status = "已退役"
        if section.unit is None:
            found = re.search(r"剧情单元\s+([A-Za-z][\w-]*)", section.title) or UNIT_IN_TITLE.search(section.title)
            if found:
                section.unit = found.group(1)
        if section.unit is None and section.scope is None:
            for line in section.lines[1:]:
                field = re.match(r"^\s*[-*+]\s*单元ID\s*[：:]\s*([A-Za-z][\w-]*)\s*$", line.replace("**", ""))
                if field:
                    section.unit = field.group(1)
                    break
    return lines, sections


def strip_retired(block_lines, keep_history):
    if keep_history:
        return block_lines
    return [line for line in block_lines if not RETIRED_LINE.match(line)]


def unit_chapter_range(sections, unit):
    for section in sections:
        if section.unit == unit and section.kind == "单元级" and "剧情单元" in section.title:
            for line in section.lines:
                found = CH_RANGE.search(line)
                if found:
                    return int(found.group(1)), int(found.group(2))
    return None


def slice_arc(section, span):
    """감정 곡선 같은 장별 표는 현재 단위 장 범위의 행만 남기며 헤더와 설명은 유지한다."""
    if span is None:
        return section.lines
    low, high = span
    kept = []
    for line in section.lines:
        row = ARC_ROW.match(line)
        if row and not (low <= int(row.group(1)) <= high):
            continue
        kept.append(line)
    return kept


def emit(sections, chosen, span, keep_history, note, preamble):
    out = ["\n".join(strip_retired(preamble, keep_history)).rstrip()] if preamble else []
    for section in sections:
        if section not in chosen:
            continue
        body = section.lines
        if "情绪弧线" in section.title or "排班" in section.title:
            body = slice_arc(section, span)
        body = strip_retired(body, keep_history)
        out.append("\n".join(body).rstrip())
    text = "\n\n".join(out)
    sys.stdout.write(text + "\n")
    if note:
        sys.stderr.write(note + "\n")


def cmd_toc(sections):
    print("%-3s %-6s %-9s %-8s %-46s %s" %
          ("#", "行", "作用域", "单元", "段", "字符"))
    for number, section in enumerate(sections, 1):
        size = sum(len(line) + 1 for line in section.lines)
        print("%-3d %-6d %-9s %-8s %-46s %d" %
              (number, section.start + 1, section.kind or "**未声明**",
               (section.unit or "-") + ("(退)" if section.status == "已退役" else ""),
               section.title[:44], size))


def cmd_check(sections, strict=False):
    problems = []
    warnings = []
    for section in sections:
        if section.kind == "批次底稿":
            for offset, line in enumerate(section.lines):
                if IMPERATIVE.search(line):
                    warnings.append(
                        ("W1", "第%d行" % (section.start + offset + 1),
                         "批次底稿里有跨章祈使，写作档不给底稿——确认已下沉到单元级段或细纲：%s"
                         % line.strip()[:52]))
    for section in sections:
        where = "第%d行「%s」" % (section.start + 1, section.title[:36])
        if section.scope is None:
            (problems if strict else warnings).append(("E1" if strict else "W2", where, "缺「> 作用域：」声明行；旧段保守纳入"))
            continue
        if section.kind is None:
            problems.append(("E2", where, "作用域值不认识：%s" % section.scope))
        if section.kind in ("单元级", "批次底稿") and section.unit is None:
            problems.append(("E3", where, "单元级/批次底稿段未标单元ID"))
        if section.kind in ("单元级", "批次底稿"):
            for offset, line in enumerate(section.lines):
                if LEAK.search(line) and not POINTER.search(line):
                    problems.append(
                        ("E4", "第%d行" % (section.start + offset + 1),
                         "单元块内出现全卷字样，常任规则放错了位置：%s"
                         % line.strip()[:56]))
    for code, where, message in problems + warnings:
        print("%s %s %s" % (code, where, message))
    print("---")
    print("段 %d ／ 问题 %d ／ 告警 %d（告警不阻断，逐条人工判断）"
          % (len(sections), len(problems), len(warnings)))
    return 1 if problems else 0


def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("path")
    parser.add_argument("--toc", action="store_true")
    parser.add_argument("--unit")
    parser.add_argument("--contract", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--strict", action="store_true", help="新建卷纲校验：缺作用域也视为错误")
    # 개요 기초 자료는 이제 권 개요 밖 개요/개요초안_{单元ID}.md에 둔다. 기본 출력은 집필에 필요한 폐포다.
    # --stage outline은 공급 자체 점검 등이 아직 권 개요 안의 배치 기초 자료 범위에 있는 구형 형식만을 위해 남긴다.
    parser.add_argument("--stage", choices=["outline", "write"], default="write",
                        help="write（默认）＝卷级常任＋单元级；"
                             "outline＝另带老卷纲里仍在用的批次底稿段")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    try:
        lines, sections = parse(read(args.path))
    except (OSError, UnicodeError) as error:
        sys.stderr.write(f"无法读取卷纲：{error}\n")
        return 2
    if not sections:
        sys.stderr.write("卷纲里没有 ## 段，路径对不对？\n")
        return 2

    if args.toc:
        cmd_toc(sections)
        return 0
    if args.check:
        return cmd_check(sections, args.strict)

    invalid = [s for s in sections if s.scope and
               (s.kind is None or (s.kind != "卷级常任" and s.unit is None))]
    if invalid:
        sys.stderr.write("作用域声明无效，先运行 --check 修正\n")
        return 1
    active = [s for s in sections if args.history or s.status != "已退役"]
    permanent = [s for s in active if s.kind == "卷级常任"]
    undeclared = [s for s in active if s.scope is None]
    note = ("%d 段未声明作用域，已保守纳入；用 --check 查看" % len(undeclared)) if undeclared else None
    preamble = lines[:sections[0].start]
    if args.contract:
        emit(sections, set(permanent + undeclared), None, args.history, note, preamble)
        return 0

    if args.unit:
        unit = args.unit
        owned = [s for s in active if s.unit == unit]
        if not owned:
            sys.stderr.write(
                "找不到单元 %s —— 不静默降级。核对单元ID，或先补卷纲。\n" % unit)
            return 1
        if args.stage == "write":
            # 집필 프로필에는 개요 편성 작업용인 배치 기초 자료를 주지 않는다. 그 안에서 집필에도 구속력 있는 항목은
            # 이미 단위별 절이나 상세 개요로 옮겨져 있어야 한다(artifact-protocols.md의 ‘排纲底稿不进卷纲’ 계약 참조).
            live = [s for s in owned if s.kind == "单元级"]
        else:
            live = [s for s in owned
                    if s.kind == "单元级"
                    or s.kind == "批次底稿"]
        chosen = set(permanent + live + undeclared)
        span = unit_chapter_range(active, unit)
        emit(sections, chosen, span, args.history, note, preamble)
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
