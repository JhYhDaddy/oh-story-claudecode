#!/usr/bin/env python3
"""check-agent-notes.py — .agents/notes/ 결정 기록의 디렉터리 배치와 본문 구조를 검증한다.

규칙은 저장소 루트 AGENTS.md의 중요 변경 기록 지침을 따른다.
  경로   .agents/notes/{proposed,implemented,rejected}/{feature,bug-fix,simplification,architecture,process,testing}/yyyy-mm-dd-topic.md
  첫 줄  "# Agent Note: <제목>"
  상태   "Status: <디렉터리 이름>"이며 실제 디렉터리와 일치해야 한다.
  절     ## Problem; ## Decision(implemented / rejected) 또는 ## Proposal(proposed); ## Alternatives considered; ## Consequences
  금지   INDEX.md 같은 수동 색인(디렉터리 위치가 곧 상태다)

사용법: python3 scripts/check-agent-notes.py [--root <dir>]   종료 코드: 0 통과 / 1 실패
"""
import argparse
import pathlib
import re
import sys

STATUSES = ("proposed", "implemented", "rejected")
CATEGORIES = ("feature", "bug-fix", "simplification", "architecture", "process", "testing")
FILENAME = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*\.md$")
TITLE = re.compile(r"^# Agent Note: \S")
STATUS_LINE = re.compile(r"^Status: (\w+)\s*$", re.M)
HEADING = re.compile(r"^## (.+?)\s*$", re.M)
REQUIRED_COMMON = ("Problem", "Alternatives considered", "Consequences")


def check_note(path: pathlib.Path, root: pathlib.Path) -> list[str]:
    rel = path.relative_to(root)
    errs: list[str] = []
    parts = rel.parts
    if len(parts) != 3:
        return [f"{rel}: 路径必须是 <status>/<category>/<yyyy-mm-dd-topic>.md"]
    status, category, name = parts
    if status not in STATUSES:
        errs.append(f"{rel}: 状态目录 `{status}` 不在 {STATUSES}")
    if category not in CATEGORIES:
        errs.append(f"{rel}: 分类目录 `{category}` 不在 {CATEGORIES}")
    if not FILENAME.match(name):
        errs.append(f"{rel}: 文件名须为 yyyy-mm-dd-topic.md（小写、连字符）")
    text = path.read_text(encoding="utf-8")
    first = text.lstrip("﻿").splitlines()[0] if text.strip() else ""
    if not TITLE.match(first):
        errs.append(f"{rel}: 首行须为 `# Agent Note: <标题>`，实际 `{first[:40]}`")
    m = STATUS_LINE.search(text)
    if not m:
        errs.append(f"{rel}: 缺 `Status: <状态>` 行")
    elif m.group(1) != status:
        errs.append(f"{rel}: `Status: {m.group(1)}` 与所在目录 `{status}` 不一致")
    headings = HEADING.findall(text)
    for h in REQUIRED_COMMON:
        if h not in headings:
            errs.append(f"{rel}: 缺 `## {h}`")
    decision_like = {"Decision", "Proposal"} & set(headings)
    if status == "proposed":
        if "Proposal" not in headings:
            errs.append(f"{rel}: proposed 笔记须有 `## Proposal`")
    elif "Decision" not in headings:
        errs.append(f"{rel}: {status} 笔记须有 `## Decision`")
    if len(decision_like) == 2:
        errs.append(f"{rel}: `## Decision` 与 `## Proposal` 不能同时存在（落地时改名，不并存）")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".agents/notes")
    args = ap.parse_args()
    root = pathlib.Path(args.root)
    if not root.is_dir():
        print(f"check-agent-notes: 目录不存在：{root}")
        return 1
    errs: list[str] = []
    notes = sorted(p for p in root.rglob("*") if p.is_file())
    for p in notes:
        rel = p.relative_to(root)
        if p.name.lower() in ("index.md", "readme.md"):
            errs.append(f"{rel}: 不建索引文件，目录位置就是状态（检索用 rg --hidden）")
            continue
        if p.name == ".gitkeep":
            continue
        if p.suffix != ".md":
            errs.append(f"{rel}: 笔记目录只放 .md")
            continue
        errs.extend(check_note(p, root))
    count = sum(1 for p in notes if p.suffix == ".md")
    if errs:
        print("check-agent-notes: FAIL")
        for e in errs:
            print("  - " + e)
        return 1
    print(f"check-agent-notes: OK ({count} notes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
