#!/usr/bin/env python3
"""검사 규칙: 작가에게 보여 주는 보고 템플릿에 개발 내부 용어를 쓰지 않는다.

<!-- author-report --> 표식 바로 다음의 코드 블록만 검사한다(오탐을 막기 위해 나머지 스킬 지침은 제외).
코드 블록은 일반 ```md를 쓴다. 언어 표식을 author-report로 쓰면 모델이 울타리까지 그대로 출력하므로 기존 형식은 오류로 처리한다.
검사 대상:
- 알려진 내부 필드/상태명, 검토자 이름, 심각도 코드, Gate 문자, PASS/FAIL
- 스크립트/설정 파일명(.py/.js/.sh/.json/...), 명령행 플래그, snake_case 및 kebab-case 식별자
  (작가가 직접 입력하는 /story-xxx, $story-xxx 명령은 제외)
- 레이블 없는 번호(F003, BP001, REL-001, L1-3). 반드시 ‘설명(ID)’ 또는 ‘ID(설명)’으로 표시한다.
이 파일이 작가 보고 규칙의 유일한 검사기다(static-check.py는 중복 검사하지 않는다).
블록의 마지막 비어 있지 않은 줄이 ‘技术备注：’로 시작하면 실행 경로 같은 기술 세부 사항을 담을 수 있으며 위 검사에서 제외한다.
기술 참고는 반드시 블록 끝의 한 줄이어야 한다.

REQUIRED에 등록된 파일은 최소한 지정된 개수의 author-report 블록을 포함해야 한다. 템플릿 표식의 조용한 삭제를 방지한다.

사용법: python3 scripts/check-author-reports.py [--self-test]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 파일 -> 필요한 author-report 블록의 최소 개수.
# 장편: 기획, 단일 장(완료/글자 수/결정/중단), 일일 집필 배치 종료, 대규모 수정마다 작가 보고 템플릿이 있다.
# 작가 기억 확인 응답은 제외한다. 응답 전체가 템플릿 두 줄이며 코드 블록으로 쓰면 모델이 울타리까지 그대로 출력한다(실측 2/2).
# 따라서 author-memory.md에서는 인라인 예제로 확인 응답을 설명한다.
REQUIRED = {
    # 가져오기 완료 보고는 보고 시점에 맞춰 import-report.md로 이동했다(장편과 단편 각각 한 블록).
    "skills/story-import/references/import-report.md": 2,
    # 검토 보고서는 시점별로 진입점에서 분리했다(v0.8.2). full/lean 템플릿은 하위 에이전트 배정 시 agent-prompts.md에서, 단독 검토 템플릿은 solo.md에서 읽는다.
    "skills/story-review/references/agent-prompts.md": 1,
    "skills/story-review/references/solo.md": 1,
    "skills/story-deslop/SKILL.md": 1,
    "skills/story-short-analyze/SKILL.md": 1,
    "skills/story-long-scan/SKILL.md": 1,
    "skills/story-short-scan/SKILL.md": 1,
    "skills/story-cover/SKILL.md": 1,
    "skills/story-long-write/references/workflow-volume.md": 1,
    "skills/story-long-write/references/workflow-outline.md": 1,
    "skills/story-long-write/references/workflow-chapter.md": 4,
    "skills/story-long-write/references/workflow-daily.md": 1,
    "skills/story-long-write/references/workflow-revision.md": 1,
}

TAIL_PREFIX = "技术备注："

KNOWN_TOKENS = (
    "Requested Mode", "Effective Mode", "Rubric Source", "Severity Counts", "Fallback:",
    "NOT_RUN", "APPROVE", "CONCERNS", "REJECT", "PASS", "FAIL", "SKIP",
    "Author Memory Receipt",
)

CHECKS = (
    ("已知内部名", re.compile(r"(?<![A-Za-z])(?:" + "|".join(re.escape(t) for t in KNOWN_TOKENS) + r")(?![A-Za-z])")),
    ("脚本/配置文件名", re.compile(r"[\w.-]+\.(?:py|js|mjs|cjs|sh|ts|json|jsonl|toml|ya?ml)\b")),
    ("命令行 flag", re.compile(r"(?<![\w-])--[A-Za-z][\w-]*")),
    ("snake_case 字段名", re.compile(r"(?<![\w])[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b")),
    ("kebab-case 标识符", re.compile(r"(?<![\w/$-])[a-z][a-z0-9]*(?:-[a-z0-9]+)+\b")),
    ("英文工程词", re.compile(
        r"(?i)(?<![A-Za-z])(?:state|schema|agents?|reviewers?|rubric|prompt|hooks?|fallback|pipeline|stage|tier|token"
        r"|commit|verdict|severity|discard|borderline|invalid|internal|pass|fail|under|over|tracking|revision"
        r"|checkpoint|segment|delta|Constraint Lock|Notice)(?![A-Za-z])"
    )),
    ("内部清单名", re.compile(r"安全七检|七检|供给自查|供给单|内带|用户带|二档|三档|收编|契约检查器|状态码|追踪事务")),
    ("严重度代号", re.compile(r"(?<![A-Za-z0-9])S[1-4](?![0-9])")),
    ("Gate 名", re.compile(r"\bGate\b|\d\s*Gate")),
)

_ID = r"(?:[A-Z]{1,3}\d?-?\d{2,}|[EFL]\d+(?:-\d+)?)"
RAW_ID = re.compile(r"(?<![A-Za-z0-9])" + _ID + r"(?![A-Za-z0-9])")
# 번호에는 이야기 레이블이 붙어야 한다. ‘설명(ID)’와 ‘ID(설명)’ 두 형식을 모두 인정한다.
LABELED_ID = re.compile(
    r"\S（" + _ID + r"(?:[、，,]\s*" + _ID + r")*）"
    r"|(?<![A-Za-z0-9])" + _ID + r"(?:[、，,]\s*" + _ID + r")*\s*[（(][^）)]*[^\sA-Za-z0-9（(）)][^）)]*[）)]"
)

FENCE_OPEN = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([^\s`]*)")
MARKER = "<!-- author-report -->"
LEGACY_INFO = "author-report"


def author_blocks(text: str):
    """(시작 줄 번호, 블록 내부 줄 목록)을 생성한다."""
    lines = text.splitlines()
    i = 0
    previous = ""
    while i < len(lines):
        m = FENCE_OPEN.match(lines[i])
        if not m:
            if lines[i].strip():
                previous = lines[i].strip()
            i += 1
            continue
        fence = m.group(2)
        marked = previous == MARKER
        start = i
        i += 1
        body = []
        while i < len(lines) and not lines[i].strip().startswith(fence):
            body.append(lines[i])
            i += 1
        i += 1
        previous = ""
        if marked:
            yield start + 2, body


def legacy_fences(text: str) -> list[int]:
    """언어 표식을 author-report로 쓴 기존 코드 블록(줄 번호는 1부터 시작)."""
    return [
        k + 1 for k, line in enumerate(text.splitlines())
        if (m := FENCE_OPEN.match(line)) and m.group(3) == LEGACY_INFO
    ]


def check_block(body: list[str]) -> list[tuple[int, str]]:
    errors: list[tuple[int, str]] = []
    nonempty = [k for k, line in enumerate(body) if line.strip()]
    last = nonempty[-1] if nonempty else -1
    for k, line in enumerate(body):
        stripped = line.strip()
        if stripped.startswith(TAIL_PREFIX):
            if k != last:
                errors.append((k, "技术备注只能是块内最后一行"))
            continue
        for label, pattern in CHECKS:
            hit = pattern.search(line)
            if hit:
                errors.append((k, f"{label}「{hit.group(0)}」"))
        masked = LABELED_ID.sub("", line)
        hit = RAW_ID.search(masked)
        if hit:
            errors.append((k, f"裸编号「{hit.group(0)}」（写成「故事描述（ID）」或「ID（故事描述）」）"))
    return errors


def check_text(text: str) -> list[tuple[int, str]]:
    out = []
    for start, body in author_blocks(text):
        for k, msg in check_block(body):
            out.append((start + k, msg))
    return out


def run() -> int:
    failures = []
    files = sorted((ROOT / "skills").rglob("*.md"))
    marked: dict[str, int] = {}
    for path in files:
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        count = sum(1 for _ in author_blocks(text))
        if count:
            marked[rel] = count
        for lineno, msg in check_text(text):
            failures.append(f"{rel}:{lineno}: {msg}")
        for lineno in legacy_fences(text):
            failures.append(f"{rel}:{lineno}: 围栏信息串不能写 author-report（模型会原样回给作者），改成上一行 {MARKER}、围栏用 ```md")
    for rel, minimum in REQUIRED.items():
        if marked.get(rel, 0) < minimum:
            failures.append(f"{rel}: {MARKER} 标记的报告模板块少于 {minimum} 个（现有 {marked.get(rel, 0)}）")
    if failures:
        print("作者报告模板检查未通过：")
        for f in failures:
            print("  " + f)
        return 1
    print(f"OK: {len(marked)} 个文件的作者报告模板不含工程黑话")
    return 0


def self_test() -> int:
    bad = [
        "字数口径：visible_chars_v1",
        "运行 tracking_commit.py check 通过",
        "要接受当前长度吗？回复 accept-current-length",
        "severity: S2",
        "7 Gate 中 4 个有问题",
        "伏笔 F007 未回收",
        "Fallback: none",
        "加 --book-root",
        "追踪：唯一结构化 state + 派生快照",
        "伏笔 L1-3 待定",
        "按安全七检过了一遍",
        "字数 borderline，要不要 discard",
        "Constraint Lock 已生效",
        "正文已回到内带",
        "这条先收编进追踪",
    ]
    good = [
        "下一步：说「日更」就从第 7 章接着写；也可运行 `/story-long-write`。",
        "还没收的线：玉佩的来历（F003）",
        "伏笔 F057（那封信的去处）已经收回",
        "第一卷第三个单元（L1-3）写完了",
        "## 必须改（2 处）",
        "",
    ]
    ok = True
    for line in bad:
        text = f"{MARKER}\n```md\n{line}\n结尾\n```\n"
        if not check_text(text):
            print(f"self-test: 未拦截 {line!r}")
            ok = False
    for line in good:
        text = f"{MARKER}\n```md\n{line}\n```\n"
        if check_text(text):
            print(f"self-test: 误报 {line!r}: {check_text(text)}")
            ok = False
    tail_ok = MARKER + "\n```md\n正文\n技术备注：Mode full→solo · Fallback missing agents -> solo\n```\n"
    if check_text(tail_ok):
        print(f"self-test: 块尾技术备注被误报 {check_text(tail_ok)}")
        ok = False
    tail_bad = MARKER + "\n```md\n技术备注：S1\n正文\n```\n"
    if not check_text(tail_bad):
        print("self-test: 未拦截非块尾技术备注")
        ok = False
    plain = "```text\ntracking_commit.py check\n```\n"
    if check_text(plain):
        print("self-test: 误检了非 author-report 块")
        ok = False
    unmarked_after_marked = MARKER + "\n```md\n正文\n```\n\n```text\ntracking_commit.py\n```\n"
    if check_text(unmarked_after_marked):
        print("self-test: 标记只该管紧随其后的一个围栏")
        ok = False
    if legacy_fences("```author-report\n正文\n```\n") != [1]:
        print("self-test: 未拦截旧的 author-report 信息串")
        ok = False
    print("self-test OK" if ok else "self-test FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        sys.exit(self_test())
    sys.exit(run())
