#!/usr/bin/env python3
"""프로젝트 지침 파일에 호스트 하나의 oh-story 블록을 병합한다.

CLAUDE.md와 공유 루트 AGENTS.md에는 호스트별 관리 블록이 하나씩 있다.

    <!-- oh-story:codex 开始：重新部署时整块替换，自己的内容写在块外 -->
    ...렌더링한 템플릿...
    <!-- oh-story:codex 结束 -->

재배포는 이 호스트 블록만 교체한다. 모든 블록 밖의 텍스트와 다른 호스트
블록은 바이트 단위로 보존한다. 블록 도입 전 파일은 한 번 이전한다.
oh-story 제목 줄, 소개, 현재 템플릿이 소유한 제목의 절을 제거하고 블록으로
대체한다. 모든 블록 밖에 oh-story 제목 줄이 있을 때만 이전 배포로 간주한다.
다른 호스트 블록이 이미 있으면 이 호스트 고유 제목만 이전 잔여물로 취급한다.
그 밖의 파일은 작가 소유이므로 블록을 뒤에 추가한다.
위 중국어 마커 예시는 실제 인식 구문이므로 원형을 유지한다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path


HOSTS = ("claude-code", "opencode", "codex", "zcode", "openclaw", "reasonix", "generic")
# 이전 템플릿에는 있었지만 현재 템플릿에서 삭제된 관리 대상 절도 이전 파일 이전 시 함께 제거한다.
RETIRED_HEADINGS = frozenset({"协作规则"})
# 흔한 이름의 절은 oh-story 흔적이 있을 때만 관리 대상으로 간주해 작가의 동명 절을 잘못 삭제하지 않는다.
GENERIC_HEADINGS = frozenset({"Skill 路由表", "文件结构", "写作约束"})
LEGACY_SIGNALS = ("story-", "작품분석실", "추적/", "细纲", "작가기억", "oh-story")
# 호스트 템플릿 공통 절: 다른 호스트 블록이 있고 블록 밖에 이전 제목이 없으면 작가 소유다.
SHARED_HEADINGS = frozenset({"Skill 路由表", "文件结构", "写作约束", "与作者协作", "Compact 后恢复上下文"})
TITLE_SIGNAL = "网文写作工具集"
LEGACY_MARKER = "<!-- managed-by: story-setup -->"
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")


class MergeError(ValueError):
    pass


def begin_marker(host: str) -> str:
    return f"<!-- oh-story:{host} 开始：重新部署时整块替换，自己的内容写在块外 -->"


def end_marker(host: str) -> str:
    return f"<!-- oh-story:{host} 结束 -->"


def block_re(host: str) -> re.Pattern[str]:
    return re.compile(
        r"^<!-- oh-story:" + re.escape(host) + r" 开始[^\n]*-->\n.*?^<!-- oh-story:"
        + re.escape(host) + r" 结束 -->[ \t]*$",
        re.S | re.M,
    )


ANY_BEGIN_RE = re.compile(r"^<!-- oh-story:([a-z-]+) 开始[^\n]*-->$", re.M)


def render_block(template: str, host: str, project_name: str) -> str:
    body = template.replace("\r\n", "\n").replace("{项目名}", project_name).strip("\n")
    if "<!-- oh-story:" in body:
        raise MergeError("template must not carry its own oh-story markers")
    return f"{begin_marker(host)}\n{body}\n{end_marker(host)}"


def managed_headings(template: str) -> set[str]:
    headings = {m.group(1) for m in map(HEADING_RE.match, template.splitlines()) if m}
    return headings | set(RETIRED_HEADINGS)


def protected_spans(text: str) -> list[tuple[int, int]]:
    """모든 기존 oh-story 블록(호스트 무관)의 문자 범위."""
    spans = []
    for match in ANY_BEGIN_RE.finditer(text):
        host = match.group(1)
        end = re.compile(r"^<!-- oh-story:" + re.escape(host) + r" 结束 -->[ \t]*$", re.M).search(text, match.end())
        if end is None:
            raise MergeError(f"unterminated oh-story:{host} block")
        spans.append((match.start(), end.end()))
    return spans


def title_re(template: str) -> re.Pattern[str] | None:
    """프로젝트 이름을 와일드카드로 처리한 템플릿 자체 H1."""
    first = next((line for line in template.splitlines() if line.startswith("# ")), "")
    if TITLE_SIGNAL not in first:
        return None
    parts = [re.escape(part) for part in first.strip().split("{项目名}")]
    return re.compile("^" + ".*".join(parts) + r"\s*$")


def strip_legacy(text: str, template: str) -> tuple[str, int | None, list[str]]:
    """이 템플릿이 소유한 마커 없는 oh-story 콘텐츠를 제거한다.

    새 텍스트, 블록 삽입 오프셋(이전 콘텐츠가 없으면 None), 제거한 절 제목을 반환한다.
    """
    headings = managed_headings(template)
    own_title = title_re(template)
    spans = protected_spans(text)
    lines = text.split("\n")
    offsets = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1

    def inside_block(index: int) -> bool:
        return any(start <= offsets[index] < end for start, end in spans)

    # 이전 배포의 증거: 블록 밖의 oh-story 제목 줄(어느 호스트든) 또는 이전 관리 마커.
    outside = [line for i, line in enumerate(lines) if not inside_block(i)]
    legacy_deploy = any(
        (line.startswith("# ") and TITLE_SIGNAL in line) or line.strip() == LEGACY_MARKER for line in outside
    )
    if not legacy_deploy:
        if not spans:
            return text, None, []
        # 다른 호스트 블록이 이미 있으면 공통 절은 먼저 이전한 호스트가 정리했으므로 이 호스트 고유 절만 남는다.
        headings = headings - SHARED_HEADINGS - RETIRED_HEADINGS

    # 블록 밖의 줄을 ‘이 호스트의 제목 줄 + 소개’와 ‘## 절’ 두 종류 조각으로 나눈다.
    pieces: list[tuple[str, int, int]] = []  # (제목, 시작 줄, 끝 줄[미포함])
    index = 0
    while index < len(lines):
        if inside_block(index):
            index += 1
            continue
        line = lines[index]
        if own_title is not None and own_title.match(line):
            end = index + 1
            while end < len(lines) and not lines[end].startswith("#") and not inside_block(end):
                end += 1
            pieces.append(("#title", index, end))
            index = end
            continue
        heading = HEADING_RE.match(line)
        if heading:
            end = index + 1
            while end < len(lines) and not lines[end].startswith("# ") and not HEADING_RE.match(lines[end]) and not inside_block(end):
                end += 1
            pieces.append((heading.group(1), index, end))
            index = end
            continue
        index += 1

    removed_ranges: list[tuple[int, int]] = []
    removed_titles: list[str] = []
    for title, start, end in pieces:
        body = "\n".join(lines[start:end])
        if title == "#title":
            removed_ranges.append((start, end))
            removed_titles.append(lines[start].lstrip("# ").strip())
        elif title in headings and (
            title not in GENERIC_HEADINGS or any(signal in body for signal in LEGACY_SIGNALS)
        ):
            removed_ranges.append((start, end))
            removed_titles.append(title)
    if not removed_ranges:
        return text, None, []
    drop = set()
    for start, end in removed_ranges:
        drop.update(range(start, end))
    first = min(start for start, _ in removed_ranges)
    kept_before = [line for i, line in enumerate(lines[:first]) if i not in drop]
    kept_after = [line for i, line in enumerate(lines) if i >= first and i not in drop]
    head = "\n".join(kept_before)
    insert_at = len(head) + (1 if kept_before else 0)
    new_text = head + ("\n" if kept_before else "") + "\n".join(kept_after)
    return new_text, insert_at, removed_titles


def tidy(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n") + "\n"


def merge(existing: str, template: str, host: str, project_name: str) -> tuple[str, dict]:
    block = render_block(template, host, project_name)
    crlf = existing.count("\r\n") > existing.count("\n") / 2 if existing else False
    text = existing.replace("\r\n", "\n")
    report: dict = {"host": host, "removed_legacy_sections": []}
    if not text.strip():
        report["status"] = "created"
        merged = block + "\n"
    else:
        protected_spans(text)  # 먼저 기존 블록이 모두 닫혔는지 검증한다.
        pattern = block_re(host)
        matches = list(pattern.finditer(text))
        if len(matches) > 1:
            raise MergeError(f"more than one oh-story:{host} block")
        if matches:
            report["status"] = "replaced"
            merged = tidy(text[: matches[0].start()] + block + text[matches[0].end():])
        else:
            stripped, insert_at, removed = strip_legacy(text, template)
            if insert_at is None:
                report["status"] = "appended"
                merged = tidy(text.rstrip("\n") + "\n\n" + block)
            else:
                report["status"] = "migrated"
                report["removed_legacy_sections"] = removed
                before, after = stripped[:insert_at], stripped[insert_at:]
                merged = tidy(
                    (before.rstrip("\n") + "\n\n" if before.strip() else "")
                    + block
                    + ("\n\n" + after.lstrip("\n") if after.strip() else "")
                )
    if crlf:
        merged = merged.replace("\n", "\r\n")
    return merged, report


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", required=True, choices=HOSTS)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--existing", required=True, type=Path, help="project CLAUDE.md / AGENTS.md (may be absent)")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--project-name", required=True)
    args = parser.parse_args(argv)
    try:
        template = args.template.read_text(encoding="utf-8")
        existing = args.existing.read_text(encoding="utf-8") if args.existing.is_file() else ""
        merged, report = merge(existing, template, args.host, args.project_name)
        unchanged = merged == existing and args.output.resolve() == args.existing.resolve()
        if not unchanged:
            atomic_write(args.output, merged)
    except (OSError, UnicodeDecodeError, MergeError) as error:
        print(json.dumps({"status": "error", "error": str(error)}))
        return 1
    # Windows 콘솔 인코딩으로 보고서가 깨지지 않도록 ASCII만 출력한다(중국어는 이스케이프).
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
