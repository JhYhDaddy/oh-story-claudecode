"""출판 준비 문서를 플랫폼 참조와 읽기 전용으로 대조한다.
플랫폼 규칙은 참조 프런트매터(작품 유형당 JSON 한 행)에서 얻으므로 플랫폼 추가는 스크립트 수정 없이 참조를 추가하면 된다.
FAIL: 형식 계약 위반 또는 플랫폼이 제공하지 않는 선택지. WARN: 플랫폼이 거부할 수 있는 확정 값으로 작가가 판단한다.
"""

import argparse
import json
from pathlib import Path
import re
import sys


REFERENCES = Path(__file__).resolve().parents[1] / "references"
FORMAT_VERSION = "1"
HEADER_KEYS = ["格式版本", "目标平台", "作品类型", "核验"]
TAIL = ["作品简介", "待作者确认", "待平台核实", "来源说明"]
COVER_FIELDS = ["模式", "状态", "提示词", "图片"]
COVER_MODES = {"直接生成", "仅提示词", "暂缓"}
BLANK = "（不填）"
PLACEHOLDER = re.compile(r"待(?:作者)?确认|待定|未定|建议|草案|TBD|暂无", re.I)


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    return dict(line.split(": ", 1) for line in match[1].splitlines() if ": " in line) if match else {}


def load_spec(platform, work_type):
    """프런트매터가 플랫폼과 작품 유형을 명시한 참조를 찾는다."""
    for path in sorted(REFERENCES.glob("*.md")):
        meta = frontmatter(path)
        if meta.get("platform") == platform and work_type in meta:
            return json.loads(meta[work_type])
    raise ValueError(f"没有「{platform}」的「{work_type}」适配资料。")


def load_options(name):
    """참조의 ‘## 字段 / 规则 / 候选值’ 블록에서 {field: (candidates, limit)}를 반환한다."""
    options = {}
    for block in re.split(r"^## ", (REFERENCES / name).read_text(encoding="utf-8"), flags=re.M)[1:]:
        field, _, body = block.partition("\n")
        values = re.search(r"^候选值：(.+?)。?\s*$", body, re.M)
        if values:
            limit = re.search(r"^规则：.*?选\s*(\d+)\s*个", body, re.M)
            options[field.strip()] = (set(values[1].split("、")), int(limit[1]) if limit else None)
    if not options:
        raise ValueError(f"{name} 没有可读的候选值。")
    return options


def unfenced(lines, start=0, end=None):
    """코드 블록 밖의 (index, line) 쌍. 긴 표지 프롬프트 안에는 별도 제목이 있을 수 있다."""
    kept, fence = [], None
    for index in range(start, len(lines) if end is None else end):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", lines[index])
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        elif marker:
            fence = marker[1]
        else:
            kept.append((index, lines[index]))
    return kept


def block(lines, headings, position):
    """코드 블록을 제외한 제목 아래의 비어 있지 않은 행."""
    start = headings[position][0] + 1
    end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
    return [line for _, line in unfenced(lines, start, end) if line.strip()]


def parse_fields(lines, where, errors):
    """‘- 字段：值’ 행을 {field: value}로 변환한다. 필드는 각각 한 행에 한 번만 나온다."""
    fields = {}
    for line in lines:
        match = re.fullmatch(r"- ([^：:]+)：(.*)", line)
        if not match:
            errors.append(f"{where}的每个字段必须写成独立的「- 字段：值」行：{line.strip()}")
            continue
        name, value = match[1], match[2].strip()
        if name in fields:
            errors.append(f"{where}的 {name} 出现了不止一次。")
        if re.search(r"[^\s、，,]+\s*[：:]", value):
            errors.append(f"{where}的 {name} 行混入了其他字段，要拆行。")
        fields[name] = value
    return fields


def check_value(where, name, value, errors):
    if value and value != BLANK and PLACEHOLDER.search(value):
        errors.append(f"{where}的 {name} 写了建议或占位词；未定就留空，决定不填写「{BLANK}」。")


def values_of(value):
    return [] if value in ("", BLANK) else [item.strip() for item in value.split("、") if item.strip()]


def title_warnings(title, rule):
    warnings = []
    if any(char.isspace() for char in title):
        warnings.append("书名不能有空格。")
    half = rule.get("half_width")
    length = sum(half if half and ord(char) < 128 else 1 for char in title)
    if length > rule["max"]:
        warnings.append(f"书名计 {length:g} 个字，平台上限 {rule['max']}。")
    if "symbols" in rule:
        invalid = "".join(dict.fromkeys(
            char for char in title if not char.isalnum() and not char.isspace() and char not in rule["symbols"]
        ))
        if invalid:
            warnings.append(f"书名只能用这些符号：{rule['symbols']}，不能用：{invalid}")
    return warnings


def check(text):
    """출판 문서 하나의 (errors, warnings)를 반환한다."""
    if text.lstrip("\ufeff\r\n ").startswith("> 형식:"):
        return check_korean_draft(text)
    lines = text.lstrip("﻿").splitlines()
    headings = [(index, len(match[1]), match[2]) for index, line in unfenced(lines)
                if (match := re.match(r"^(#{1,6})\s+(.*?)\s*$", line))]
    errors, warnings = [], []

    if not headings or headings[0][1] != 1 or not headings[0][2].startswith("书本名称："):
        return ["第一个标题必须是「# 书本名称：<书名>」，前面只放元信息。"], []
    title_line = headings[0][0]
    header = [re.fullmatch(r"> ([^：]+)：(.*)", line) for line in lines[:title_line] if line.strip()]
    if not all(header) or [match[1] for match in header] != HEADER_KEYS:
        return ["元信息必须每行一项，依次为：" + "、".join(HEADER_KEYS) + "。"], []
    meta = {match[1]: match[2].strip() for match in header}
    if meta["格式版本"] != FORMAT_VERSION:
        return [f"格式版本应为 {FORMAT_VERSION}。"], []
    try:
        spec = load_spec(meta["目标平台"], meta["作品类型"])
    except ValueError as error:
        return [str(error)], []

    title = headings[0][2].partition("：")[2].strip()
    check_value("书名", "书本名称", title, errors)
    if title and not errors:
        warnings += title_warnings(title, spec["title"])

    sections = ["封面", *spec["tag_sections"], *TAIL]
    if [(level, name) for _, level, name in headings[1:]] != [(2, name) for name in sections]:
        errors.append("小节必须依次为：" + " → ".join(sections) + "，都用二级标题。")
        return errors, warnings
    basics = parse_fields(block(lines, headings, 0), "基础资料", errors)
    if list(basics) != spec["basics"]:
        errors.append("基础字段必须依次为：" + "、".join(spec["basics"]) + "。")
    for name, value in basics.items():
        check_value("基础资料", name, value, errors)
        choices = spec.get("choices", {}).get(name)
        if choices and value not in ("", BLANK) and value not in choices:
            errors.append(f"{name} 只能是：" + "、".join(choices) + f"，不能是 {value}。")
        limit = spec.get("max_length", {}).get(name)
        if limit and len(value) > limit:
            warnings.append(f"{name} {len(value)} 个字，平台上限 {limit}。")

    cover = parse_fields(block(lines, headings, 1), "封面", errors)
    if list(cover) != COVER_FIELDS:
        errors.append("封面小节字段必须依次为：" + "、".join(COVER_FIELDS) + "。")
    if cover.get("模式") and cover["模式"] not in COVER_MODES:
        errors.append("封面模式只能是：" + "、".join(sorted(COVER_MODES)) + "，未选时留空。")

    for position, (section, rule) in enumerate(spec["tag_sections"].items(), start=2):
        fields = parse_fields(block(lines, headings, position), section, errors)
        file = rule["files"].get("*") or rule["files"].get(basics.get(rule.get("by", ""), ""))
        if file is None:
            options = load_options(next(iter(rule["files"].values())))
            if any(values_of(value) for value in fields.values()):
                errors.append(f"填{section}前先确定{rule['by']}（" + "或".join(rule["files"]) + "）。")
        else:
            options = load_options(file)
        if list(fields) != list(options):
            errors.append(f"{section}字段必须依次为：" + "、".join(options) + "。")
        total = 0
        for name, value in fields.items():
            check_value(section, name, value, errors)
            chosen = values_of(value)
            total += len(chosen)
            if name not in options or file is None:
                continue
            candidates, limit = options[name]
            if len(chosen) != len(set(chosen)):
                errors.append(f"{section}的 {name} 有重复值。")
            if limit and len(chosen) > limit:
                errors.append(f"{section}的 {name} 选了 {len(chosen)} 个，最多 {limit} 个。")
            errors += [f"{section}的 {name} 不在候选里：{item}。" for item in chosen if item not in candidates]
        if rule.get("total") and total > rule["total"]:
            errors.append(f"{section}合计 {total} 个，最多 {rule['total']} 个。")

    synopsis = "\n".join(block(lines, headings, len(spec["tag_sections"]) + 2)).strip()
    if synopsis != BLANK:
        check_value("作品简介", "본문", synopsis, errors)
        limit = spec.get("max_length", {}).get("作品简介")
        if limit and len(synopsis) > limit:
            warnings.append(f"作品简介 {len(synopsis)} 字，平台上限 {limit}。")
    # 준비 문서이므로 빈 필드를 허용한다. 실제 제출 준비 완료를 검사하는 것이 아니다.
    return errors, warnings


KOREAN_PLATFORMS = {"문피아", "네이버 웹소설", "노벨피아", "네이버 시리즈", "카카오페이지", "리디", "포스타입"}
KOREAN_SECTIONS = ["기본 정보", "작품 소개", "표지", "작가 확인 대기", "플랫폼 확인 필요", "출처"]


def check_korean_draft(text):
    """국내 초안의 구조만 검사한다. 플랫폼 공식 양식 검증이 아니다."""
    lines = text.lstrip("\ufeff\r\n ").splitlines()
    visible = unfenced(lines)
    headings = [(i, len(m[1]), m[2]) for i, line in visible
                if (m := re.fullmatch(r"(#{1,6})\s+(.+?)\s*", line))]
    warnings = ["국내 플랫폼의 등록 양식·태그·글자 수·표지 규격은 미검증입니다. 문서 형식 통과는 제출 가능 판정이 아닙니다."]
    expected = [(1, "게시 자료"), *[(2, s) for s in KOREAN_SECTIONS]]
    if [(level, name) for _, level, name in headings] != expected:
        return ["한국어 초안 제목과 절 순서를 확인하세요: 게시 자료 → " + " → ".join(KOREAN_SECTIONS)], warnings
    header = [re.fullmatch(r"> ([^:]+): (.+)", line) for index, line in visible
              if index < headings[0][0] and line.strip()]
    if not all(header) or [m[1] for m in header] != ["형식", "플랫폼", "목적", "상태"]:
        return ["메타정보는 형식·플랫폼·목적·상태 순서로 한 줄씩 작성하세요."], warnings
    meta = {m[1]: m[2].strip() for m in header}
    errors = []
    if meta["형식"] != "ko-draft-v1":
        errors.append("지원하는 국내 형식은 ko-draft-v1입니다.")
    if meta["플랫폼"] not in KOREAN_PLATFORMS:
        errors.append("국내 자료 초안 대상 플랫폼이 아닙니다.")
    if meta["목적"] not in {"직접 연재", "투고 준비", "개인 발행"}:
        errors.append("목적은 직접 연재·투고 준비·개인 발행 중 하나입니다.")
    if meta["상태"] != "자료 초안":
        errors.append("국내 형식 검사는 자료 초안만 지원하며 게시 완료를 판정하지 않습니다.")
    for section in ["플랫폼 확인 필요", "출처"]:
        position = KOREAN_SECTIONS.index(section) + 1
        contents = "\n".join(block(lines, headings, position)).strip()
        if not contents or re.fullmatch(r"[-\s]*(없음|무|无|완료|미정|TBD)[.\s]*", contents, re.I):
            errors.append(f"{section}에 실제 확인 범위·남은 항목 또는 출처를 기록하세요.")
    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        text = args.file.read_text(encoding="utf-8-sig")
        errors, warnings = check(text)
    except (OSError, UnicodeError, ValueError) as error:
        errors, warnings = [str(error)], []
    for warning in warnings:
        print(f"WARN: {warning}")
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    if not errors:
        if text.lstrip().startswith("> 형식:"):
            print("PASS: 한국어 자료 초안 형식 확인 완료(플랫폼 적합성 미검증)")
        else:
            print("PASS: 发布资料符合格式契约与平台候选")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
