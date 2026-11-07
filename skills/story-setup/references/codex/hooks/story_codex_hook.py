#!/usr/bin/env python3
"""oh-story 집필 프로젝트용 Codex 훅 어댑터.
서드파티 의존성 없이 핵심 이야기 보호 규칙을 Codex의 stdin/stdout JSON 계약에 맞춘다.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


HOOK_CWD: Path | None = None


def read_hook_input() -> dict[str, Any]:
    global HOOK_CWD
    # 로캘로 디코딩한 스트림 대신 UTF-8 원시 바이트를 읽는다. Codex/Claude 도구
    # 입력에는 중국어 본문/细纲 경로가 있고 Windows Python stdin 기본값은
    # ANSI(cp1252/cp936)라 문자가 깨져 본문 가드가 일치하지 않고
    # 조용히 허용한다(issue #164 유형, bash 훅과 같은 수정).
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    if not raw.strip():
        return {}
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            return {}
        cwd = obj.get("cwd")
        if isinstance(cwd, str) and Path(cwd).is_dir():
            HOOK_CWD = Path(cwd).resolve()
        return obj
    except Exception:
        return {}


def emit(obj: dict[str, Any] | None) -> None:
    if obj:
        # UTF-8 바이트를 직접 쓴다. Windows stdout 기본 ANSI 코드 페이지는
        # 중국어 거부 사유·additionalContext를 깨뜨리거나 예외를 낼 수 있다.
        sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))


def _deployed_root_from_file() -> Path | None:
    """배포된 스크립트 경로로 프로젝트 루트를 스스로 찾는다.
    story-setup이 <root>/.codex/hooks/story_codex_hook.py에 배포하므로 __file__의 세 번째 상위가 루트다.
    Windows에서 가장 안정적이다. Git Bash launcher의 /c/proj 같은 MSYS 경로는 네이티브 Python 환경 변수·cwd에 그대로 쓸 수 없지만
    __file__은 항상 네이티브 경로다. 따라서 git이 아니거나 중첩 cwd에서 시작해도 루트를 찾는다.
    """
    try:
        here = Path(__file__).resolve()
    except Exception:
        return None
    if here.parent.name == "hooks" and here.parent.parent.name == ".codex":
        root = here.parent.parent.parent
        if root.is_dir():
            return root
    return None


def project_root() -> Path:
    for env_name in ("CODEX_PROJECT_DIR", "CLAUDE_PROJECT_DIR"):
        value = os.environ.get(env_name)
        if not value:
            continue
        try:
            candidate = Path(value)
            if candidate.is_dir():
                return candidate.resolve()
        except Exception:
            pass
    deployed = _deployed_root_from_file()
    if deployed is not None:
        return deployed
    start = HOOK_CWD if HOOK_CWD and HOOK_CWD.is_dir() else Path.cwd()
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if out:
            return Path(out).resolve()
    except Exception:
        pass
    return start.resolve()


def safe_rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(path)


def _walk_project_entries(root: Path, max_depth: int = 4):
    """프로젝트 아래 무시되지 않은 항목을 max_depth까지 반환한다.
    ``find -maxdepth``처럼 루트 직속 깊이는 1이며 4는 보이고 5는 보이지 않는다.
    숨김 디렉터리·node_modules·디렉터리 심볼릭 링크는 내려가기 전에 제외한다.
    """

    def walk(base: Path, remaining: int):
        if remaining <= 0:
            return
        try:
            entries = sorted(base.iterdir(), key=lambda item: item.name)
        except OSError:
            return
        visible = [
            entry
            for entry in entries
            if not entry.name.startswith(".") and entry.name != "node_modules"
        ]
        yield from visible
        if remaining == 1:
            return
        for entry in visible:
            try:
                if entry.is_dir() and not entry.is_symlink():
                    yield from walk(entry, remaining - 1)
            except OSError:
                continue

    yield from walk(root, max_depth)


def read_active_book(root: Path) -> Path | None:
    active_file = root / ".active-book"
    if active_file.exists():
        lines = active_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        # 첫 행이 비었거나 공백뿐이면 root/빈값 == root로 해석하지 않고 자동 탐색으로 넘어간다.
        # 이는 trim 후 비어 있지 않은지 요구하는 bash common.sh discover_active_book과
        # JS 훅의 firstLine()+참 여부 검사와 같다.
        declared = lines[0].strip() if lines else ""
        if declared:
            candidate = (root / declared).resolve()
            try:
                candidate.relative_to(root.resolve())
            except Exception:
                candidate = None  # type: ignore[assignment]
            if candidate and candidate.is_dir():
                return candidate
    entries = list(_walk_project_entries(root))
    for marker in ("추적", "본문"):
        for entry in entries:
            if entry.name == marker and entry.is_dir() and not entry.is_symlink():
                return entry.parent
    for entry in entries:
        if entry.name == "본문.md" and entry.is_file() and not entry.is_symlink():
            return entry.parent
    return None


def hook_context(event: str, text: str) -> dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


# ── 경량 결정적 검사(story_hook_core.js proseNetFindings와 같은 구현으로 일치 유지) ──
# 누락 시 피해가 크고 퇴화 모델이 스스로 못 찾는 강한 신호만 보완한다. 절단·거절문·AI 자기 지칭·
# 본문 작업 용어 유출·인접 행 전체 반복을 검사하며 check-degeneration.js에 의존하지 않는 독립 경량 검사다.
# 종결 문장부호는 깊은 검사 기준 check-degeneration.js findTruncation과 맞춘다([。！？!?…”"』」）)】]).
# 】는 장말 시스템 안내 템플릿의 끝 기호(agent-references/long-chapter-hooks.md 실전 1/4)이며 ASCII 따옴표는
# normalize-punctuation.js --quote-mode ascii의 정상 닫는 기호이므로 둘 다 절단 의심으로 보면 안 된다.
_NET_TERMINAL = set("。！？…”』」）)!?.~—】\"")
_NET_SOFT_PATTERNS = [
    # 종류 접미사(AI语言模型/AI助手/人工智能语言模型/AI模型/AI大模型)는 선택적으로 소비해야 한다. 아니면 전방 탐색이
    # AI 뒤의 ‘语’/‘助’/‘模’를 보아 가장 전형적인 퇴화 도입 전체를 놓친다.
    (re.compile(r'作为(一个)?(AI|人工智能|大?语言模型|智能助手|聊天助手)(?:语言模型|大?模型|助手|机器人)?(?=，|,|。|、|；|;|：|:|！|!|？|\?|\s|）|\)|」|』|"|】|我|无法|不能|没法|$)'), "AI 자기 언급"),
    (re.compile(r"^(Sure|Certainly|Here'?s|As an AI|I (?:cannot|can't|am unable|apologize))"), "영문 AI 말투"),
    (re.compile(r"我(无法|不能)(继续(写|创作|生成|下去|输出)?|生成(内容|文本|正文)?|创作|续写|写作|完成(这个|本)?(章|篇|创作|请求)?)"), "생성 거부 문구"),
]
_NET_HARD_PATTERNS = [
    (re.compile(r"[（(](此处|以下|这里|下文|后续)?[^）)]{0,10}(省略|略去|略过)[^）)]{0,10}[）)]"), "자리표시자(괄호 생략)"),
    (re.compile(r"(TODO|占位符|placeholder|待补充|此处待填|此处待补)"), "자리표시자"),
    (re.compile(r"(细纲|情节点|卷纲|功能标签|目标情绪|字数目标|章首钩子|章尾钩子|任务描述)"), "작업 용어 유출"),
    (re.compile("�"), "깨진 문자(대체 문자)"),
]


def _net_is_skippable(stripped: str) -> bool:
    if not stripped:
        return True
    if stripped[0] == "#":
        return True
    if stripped == "---":
        return True
    if re.match(r"^[-—=*·•\s]+$", stripped):
        return True
    return False


# ── 문제 문장 패턴(JS toxicPhraseFindings와 동형, 안내문은 JS 핵심 모듈 기준) ──
# check-ai-patterns.js의 동명 규칙과 같은 기준으로 결정적·저오탐 패턴만 넣는다. 밀도·
# advisory는 check-ai-patterns.js 깊은 검사에 맡긴다. 모든 정규식은 선형·유한 반복이며 대사·실시간 댓글·
# 시스템 안내는 제외한다. 행별 짝지은 따옴표를 같은 길이 물음표로 가린다(_toxic_mask_quoted의 물음표 사용 이유 참조).
# 가린 뒤에도 따옴표가 남는 다중 행 대사·미종결 행은 통째로 건너뛴다.
# js↔py는 scripts/check-hook-regex-sync.sh의 상수 정확 비교와
# scripts/test-prose-net-parity.sh의 fixture 정확 diff로 일치시킨다.
# 작은따옴표는 짝이 맞아야 한다. don't, O’Connor의 단어 내부 아포스트로피는 여닫는 따옴표가 아니다.
_TOXIC_QUOTE_SPANS = [re.compile(r"「[^」]*」"), re.compile(r"『[^』]*』"), re.compile(r"【[^】]*】"), re.compile(r"“[^”]*”"), re.compile(r"(?<![A-Za-z0-9_])‘(?:[^’]|(?<=[A-Za-z0-9_])’(?=[A-Za-z0-9_]))*(?!(?<=[A-Za-z0-9_])’[A-Za-z0-9_])’"), re.compile(r'"[^"]*"'), re.compile(r"(?<![A-Za-z0-9_])'(?:[^']|(?<=[A-Za-z0-9_])'(?=[A-Za-z0-9_]))*(?!(?<=[A-Za-z0-9_])'[A-Za-z0-9_])'")]
_TOXIC_QUOTE_CHARS = set("「」『』【】“”‘’\"'")
# 절 시작 경계. 앞 문자가 여기에 속해야 ‘是A，不是B’의 첫 ‘是’를 인정하며 확인 표현의 오른쪽 경계로도 쓴다.
_TOXIC_CLAUSE_BOUNDARY = set("，,。.！!？?；;：:、…—~ \t　")
# 의문 끝(是吗/是吧/是嘛)과 확인 표현(是的/是啊/是呀/是呢+경계)의 ‘是’는 대비문의 계사가 아니다.
# 제외 로직은 check-ai-patterns.js TAG_PARTICLES / AFFIRMATION_TAG_PARTICLES에서 가져왔다.
_TOXIC_TAG_PARTICLES = ("吗", "吧", "嘛")
_TOXIC_AFFIRM_PARTICLES = ("的", "啊", "呀", "呢")
_TOXIC_TRAILER_WINDOW = 600
# em-dash 제외는 JS와 같이 의도적이다. 대시는 chapter check --fix-punctuation /
# normalize-punctuation.js가 결정적으로 정리하며 이 검사는 모델이 고쳐야 할 문장만 반송한다.
_TOXIC_SENTENCE_PATTERNS = [
    (re.compile(r"声音(?:并)?不[大高响亮][^。！？!?\n]{0,16}[却但偏]"), "voice-contrast", "‘X하지 않지만 Y하다’식 대비를 빼고 구체적인 효과나 행동을 쓰세요."),
    (re.compile(r"(?:没有[^。！？!?\n，,]{1,12}[，,]){2}"), "negation-parade", "‘없다, 없다’식 나열을 하나만 남기거나 모두 지우고 실제 장면의 세부 묘사로 바꾸세요."),
    (re.compile(r"是[^。！？!?\n，,]{1,12}[，,]\s*(?:而)?不是[^。！？!?\n]{1,20}"), "reverse-not-is", "부정으로 시작하는 설명을 빼고 긍정 항목이나 구체적인 행동을 쓰세요."),
    (re.compile(r"不是[^。！？!?\n]{1,16}[，,]\s*(?:而)?是"), "not-is-comparison", "부정으로 시작하는 설명을 빼고 긍정 항목이나 구체적인 행동을 쓰세요."),
]
# ‘正式拉开序幕/帷幕’는 장면 속 개막 안내이며 서술자 예고가 아니므로 lookbehind로 제외한다(check-ai-patterns.js와 동일).
_TOXIC_TRAILER = re.compile(r"没人知道|谁也不知道|谁也没想到|殊不知|(?:这)?才刚刚开(?:始|头)|正(?:朝着|向着)[^。！？!?\n]{0,24}(?:压|涌|袭|逼)(?:了?过去|了?过来|来)|(?<!正式)拉开(?:序幕|帷幕)|即将(?:开始|来临|降临)")
# 장말 상태 요약체는 trailer-ending과 범위를 공유하지만 미래 예고가 아닌 과거 단정이다(story_hook_core.js와 동일).
# banned-words의 명시적 금지형만 포함한다. ‘(这|那)一刻…终于明白’는 인간 서술의 정상 인식
# 비트이며 단편 1인칭 심판 문장은 매력 요소이므로 제외한다. 문말 단정 위치만 받아 조건절·동사 보어·성어·타동사·부정 인식을 피한다.
_TOXIC_TRAILER_SUMMARY = re.compile(r"这一(?:夜|天|刻|战|年|局|役)[，,]?[^。！？!?，,\n]{0,6}(?<!命中)(?<!是)注定[^。！？!?\n]{0,8}[。！]|就这样[，,][^。！？!?，,\n]{0,8}(?:一切|全部)[^。！？!?，,\n]{0,4}(?:结束了|落幕|收场)[。！]|这一切[，,]?[^。！？!?，,\n]{0,6}(?:都)?(?:说明|意味着|结束了)(?!的)(?:(?!什么)[^。！？!?\n]){0,6}[。！]|(?:新的篇章|新的旅程|崭新的篇章|新的人生)[^。！？!?\n]{0,6}(?:开始|拉开|展开)|命运[^。！？!?\n]{0,6}齿轮")
# ‘是A，不是B’의 반문 끝 ‘…，不是吗/么/吧’는 대비문이 아니다. 적중 구간 마지막 ‘不是’ 다음 첫 글자로 판정한다.
_TOXIC_REVERSE_TAIL = re.compile(r".*[，,]\s*(?:而)?不是([^。！？!?\n]*)$")


def _toxic_mask_quoted(line: str) -> str:
    # 가림 문자는 ‘。’ 대신 ‘？’다. 각 규칙의 [^。！？!?…] 부정 클래스를 끊으면서
    # 어떤 규칙의 허용 위치에도 들어가면 안 된다. 마침표는 trailer-summary 문말 [。！]의 가짜 종결자를 만들어
    # ‘这一战注定是「血屠」的开端，…’처럼 별칭을 인용한 정상 서술을 오탐한다. 보고한
    # ‘这一战注定是。’는 원문에서 grep할 수도 없다.
    # 가림 길이는 UTF-16 코드 단위(이모지 등 보충 평면은 2)로 계산해 JS의 "？".repeat(m.length)와
    # 정확히 맞춘다. 아니면 이모지 대사 행의 양쪽 masked 길이가 달라 trailer 구간 경계가 움직인다.
    out = line
    for rx in _TOXIC_QUOTE_SPANS:
        out = rx.sub(lambda m: "？" * (len(m.group(0).encode("utf-16-le")) // 2), out)
    return out


def _toxic_not_is_excluded(line: str, matched: str, start: int) -> bool:
    """‘是不是’ 의문이나 전환 ‘是’ 뒤의 의문·확인 표현은 ‘不是A，(而)是B’ 대비문이 아니다."""
    if start > 0 and line[start - 1] == "是":
        return True
    end = start + len(matched)
    c1 = line[end] if end < len(line) else ""
    c2 = line[end + 1] if end + 1 < len(line) else ""
    if c1 in _TOXIC_TAG_PARTICLES:
        return True
    if c1 in _TOXIC_AFFIRM_PARTICLES and (c2 == "" or c2 in _TOXIC_CLAUSE_BOUNDARY):
        return True
    return False


def _toxic_reverse_not_is_excluded(line: str, matched: str, start: int) -> bool:
    """절 시작 ‘是A，不是B’만 인정한다. 중간 但是/还是/只是/他是…와 양자택일 不是/就是/也是, 모든 X是 합성어는 제외한다.
    ‘是的，不是…’ 확인 도입·‘是不是…’ 의문 도입·‘…，不是吗/么/吧’ 반문 끝도 제외한다(check-ai-patterns.js와 동일)."""
    prev = line[start - 1] if start > 0 else ""
    if prev != "" and prev not in _TOXIC_CLAUSE_BOUNDARY:
        return True
    if line[start + 1:start + 3] == "不是":
        return True
    c1 = line[start + 1] if start + 1 < len(line) else ""
    c2 = line[start + 2] if start + 2 < len(line) else ""
    if (c1 in _TOXIC_TAG_PARTICLES or c1 in _TOXIC_AFFIRM_PARTICLES) and (c2 == "" or c2 in _TOXIC_CLAUSE_BOUNDARY):
        return True
    tail = _TOXIC_REVERSE_TAIL.search(matched)
    t1 = tail.group(1)[:1] if tail and tail.group(1) else ""
    if t1 in ("吗", "么", "吧"):
        return True
    return False


def _toxic_match_sentence(line: str) -> tuple[str, str, str] | None:
    """행마다 처음 적중한 패턴만 보고한다. 한 곳 수정 뒤 다음을 재검사해 모두 정리한다."""
    for rx, label, fix in _TOXIC_SENTENCE_PATTERNS:
        for m in rx.finditer(line):
            if label == "not-is-comparison" and _toxic_not_is_excluded(line, m.group(0), m.start()):
                continue
            if label == "reverse-not-is" and _toxic_reverse_not_is_excluded(line, m.group(0), m.start()):
                continue
            return (label, fix, m.group(0))
    return None


def load_style_whitelist(file: Path) -> list[str]:
    parent = file.resolve().parent
    book = parent.parent if parent.name == "본문" else parent
    try:
        lines = (book / ".deslop-whitelist").read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    return sorted((line.strip() for line in lines if line.strip() and not line.strip().startswith("#")), key=len, reverse=True)


def mask_style_text(text: str, whitelist: list[str]) -> str:
    chars = list(text)
    for literal in whitelist:
        at = text.find(literal)
        while at != -1:
            chars[at:at + len(literal)] = ["？"] * len(literal)
            at = text.find(literal, at + 1)
    return "".join(chars)


def toxic_rescan_hint(abs_path: Path | None = None) -> str:
    """문제 패턴 끝의 전체 재검사 안내(JS toxicRescanHint와 동일): 장편 분장 본문은 storyctl chapter check,
    단편 본문.md·경로 미제공은 check-ai-patterns.js를 안내한다."""
    if abs_path is not None and abs_path.parent.name == "본문":
        m = re.match(r"^제0*(\d+)장.*\.md$", abs_path.name)
        if m:
            return f"전체 검사: {{PYTHON}} <story-long-write>/scripts/storyctl.py chapter check --project <작품폴더> --chapter {m.group(1)}"
    return "전체 스캔: node <skill>/scripts/check-ai-patterns.js --check <본문파일>"


def _mask_html_comment_lines(lines: list[str]) -> list[str]:
    """HTML 주석은 본문 아닌 메타정보다(JS maskHtmlCommentLines·check-ai-patterns.js scanDocument와 동일).
    주석을 같은 길이 공백으로 바꾸며 여러 행도 허용한다. 문말까지 안 닫힌 `<!--`는 네 문자만 지우고 나머지는 본문으로 본다."""
    unclosed: set[tuple[int, int]] = set()
    while True:
        out: list[str] = []
        is_open = False
        opened_at = None
        for index, line in enumerate(lines):
            text = ""
            cursor = 0
            while cursor < len(line):
                if is_open:
                    close = line.find("-->", cursor)
                    end = len(line) if close == -1 else close + 3
                    text += " " * (end - cursor)
                    cursor = end
                    if close != -1:
                        is_open = False
                    continue
                start = line.find("<!--", cursor)
                if start == -1:
                    text += line[cursor:]
                    break
                text += line[cursor:start] + "    "
                cursor = start + 4
                if (index, start) in unclosed:
                    continue
                is_open = True
                opened_at = (index, start)
            out.append(text)
        if not (is_open and opened_at is not None):
            return out
        unclosed.add(opened_at)


def toxic_phrase_findings(text: str, whitelist=(), rescan: str | None = None) -> list[str]:
    findings: list[str] = []
    content: list[tuple[int, str]] = []
    for i, raw in enumerate(_mask_html_comment_lines(text.split("\n")), 1):
        s = raw.strip()
        if _net_is_skippable(s):
            continue
        masked = _toxic_mask_quoted(mask_style_text(s, whitelist))
        if any(ch in _TOXIC_QUOTE_CHARS for ch in masked):
            continue
        content.append((i, masked))
    for line_no, masked in content:
        hit = _toxic_match_sentence(masked)
        if hit:
            findings.append(f"第{line_no}行 문제 문장 패턴[{hit[0]}]：『{hit[2][:20]}』——{hit[1]}")
    # trailer-ending은 문말 600자만 검사한다. 따옴표 가림 후 행별 누적하며 경계 행은 전체 포함한다.
    acc = 0
    cut = len(content)
    while cut > 0 and acc < _TOXIC_TRAILER_WINDOW:
        cut -= 1
        acc += len(content[cut][1])
    for line_no, masked in content[cut:]:
        m = _TOXIC_TRAILER.search(masked)
        if m:
            findings.append(f"第{line_no}行 문제 문장 패턴[trailer-ending]：『{m.group(0)[:20]}』——장 끝의 예고 문구를 지우고 현재 일어나는 행동이나 장면으로 마무리하세요.")
        ms = _TOXIC_TRAILER_SUMMARY.search(masked)
        if ms:
            findings.append(f"第{line_no}行 문제 문장 패턴[trailer-summary]：『{ms.group(0)[:20]}』——장 끝의 상태 요약을 지우고 상세 개요의 결말을 구체적인 행동·장면·대사로 구현하세요.")
    if findings:
        findings.append("문제 문장 패턴은 확정적인 AI 표현 흔적입니다. 이번 장에서 모두 수정한 뒤 계속하세요. " + (rescan if rescan is not None else toxic_rescan_hint()))
    return findings


# ‘去味:跳过’ 면제 표식: 파일 첫 6행의 `<!-- 去味:跳过 -->`. 전각·반각 콜론과 주석 안
# 공백·Tab을 허용하나 주석 밖 표식은 인정하지 않는다. JS core DESLOP_SKIP_MARKER·bash guard·storyctl DESLOP_SKIP과 같은 문법이다.
_DESLOP_SKIP_MARKER = re.compile(r"<!--[ \t]*去味[ \t]*(：|:)[ \t]*跳过[ \t]*-->")


def _has_deslop_skip_marker(text: str) -> bool:
    return bool(_DESLOP_SKIP_MARKER.search("\n".join(re.split(r"\r?\n", text)[:6])))


def prose_net_findings(text: str, whitelist=(), rescan: str | None = None) -> list[str]:
    findings: list[str] = []
    content: list[tuple[int, str]] = []
    for i, raw in enumerate(text.split("\n"), 1):
        s = raw.strip()
        if _net_is_skippable(s):
            continue
        content.append((i, s))
        hit = False
        # 짝지은 따옴표 안만 면제하고 바깥 서술은 계속 검사한다.
        outside_quotes = _toxic_mask_quoted(s)
        for rx, label in _NET_SOFT_PATTERNS:
            m = rx.search(outside_quotes)
            if m:
                findings.append(f"第{i}行 메타정보 유출({label}）：「{m.group(0)[:20]}」")
                hit = True
                break
        if hit:
            continue
        for rx, label in _NET_HARD_PATTERNS:
            m = rx.search(s)
            if m:
                findings.append(f"第{i}行 {label}：「{m.group(0)[:20]}」")
                break
    for (la, sa), (lb, sb) in zip(content, content[1:]):
        if sa == sb and len(sa) >= 8:
            findings.append(f"第{lb}行 인접 반복: 앞 행과 내용이 같음 「{sa[:20]}」")
    if content:
        ln, last = content[-1]
        if last and last[-1] not in _NET_TERMINAL:
            findings.append(f"第{ln}行 잘림 의심: 끝부분 「…{last[-12:]}」이 문장 부호로 끝나지 않음")
    # ‘去味:跳过’는 미처리 관문과 같은 첫 6행 기준이다. 표식이 있으면 문제 문장 패턴 반송만 건너뛰고
    # 메타정보·자리표시·반복·절단은 계속 검사한다. 그렇지 않으면 안내에 따라 표식을 추가한 Edit가
    # 이미 면제된 패턴을 다시 강제 반송한다.
    if not _has_deslop_skip_marker(text):
        findings.extend(toxic_phrase_findings(text, whitelist, rescan))
    return findings


def _is_prose_path(root: Path, abs_path: Path) -> bool:
    """check-prose-after-write.sh의 과수집 방지와 같은 본문 판정:
    단편 {작품}/본문.md는 같은 위치에 설정.md, 장편 {작품}/본문/제N장*.md는 작품 안에 개요/추적/设定이 있어야 한다."""
    base = abs_path.name
    parent = abs_path.parent.name
    if base == "본문.md":
        return (abs_path.parent / "설정.md").exists()
    if parent == "본문" and re.match(r"^제.*장.*\.md$", base):
        book = abs_path.parent.parent
        return (book / "개요").is_dir() or (book / "추적").is_dir() or (book / "설정").is_dir() or (book / "설정.md").exists()
    return False


def find_changed_prose_files(root: Path) -> list[Path]:
    """이번 회차 git 변경·미추적 본문 파일. PostToolUse가 없는 Codex가 Stop에서 변경 집합을 재검사하는 데 쓴다.
    git 저장소가 아니거나 변경이 없으면 가능한 범위에서 빈 목록을 반환한다."""
    # diff 두 분기는 --relative와 -- .가 필수다. 없으면 저장소 루트 상대 경로를 출력해 프로젝트가 저장소 하위일 때
    # root/rel이 <root>/<proj>/<proj>/…처럼 존재하지 않는 경로가 되어 exists()가 전부 버린다.
    # 그러면 제출된 장의 개고 전체를 놓친다. Codex에는 PostToolUse가 없어 이 Stop 검사가 유일한 본문 검사다.
    # --relative는 범위도 -C 하위 트리로 줄여 원래 cwd 상대인 ls-files와 맞춘다. staged_markdown_warnings와
    # JS stagedMarkdownWarnings도 같은 기준이다.
    out: list[Path] = []
    seen: set[str] = set()
    for args in (
        ["git", "-C", str(root), "-c", "core.quotepath=false", "diff", "--relative", "--name-only", "-z", "--diff-filter=ACM", "--", "."],
        ["git", "-C", str(root), "-c", "core.quotepath=false", "diff", "--relative", "--name-only", "--cached", "-z", "--diff-filter=ACM", "--", "."],
        ["git", "-C", str(root), "-c", "core.quotepath=false", "ls-files", "--others", "--exclude-standard", "-z"],
    ):
        try:
            raw = subprocess.check_output(args, stderr=subprocess.DEVNULL)
        except Exception:
            continue
        for chunk in raw.split(b"\0"):
            if not chunk:
                continue
            rel = chunk.decode("utf-8", errors="ignore")
            if not rel.endswith(".md"):
                continue
            abs_path = (root / rel).resolve()
            key = str(abs_path)
            if key in seen or not abs_path.exists():
                continue
            if _is_prose_path(root, abs_path):
                seen.add(key)
                out.append(abs_path)
    return out


def _discover_all_books(root: Path) -> list[Path]:
    books: list[Path] = []
    seen: set[str] = set()
    for hit in _walk_project_entries(root):
        try:
            is_marker = (
                hit.name in {"추적", "본문"}
                and hit.is_dir()
                and not hit.is_symlink()
            )
            is_body_file = (
                hit.name == "본문.md" and hit.is_file() and not hit.is_symlink()
            )
        except OSError:
            continue
        if not is_marker and not is_body_file:
            continue
        book = hit.parent
        key = str(book.resolve())
        if key not in seen:
            seen.add(key)
            books.append(book)
    return books


def tracking_checkpoint_issue(
    book: Path,
    *,
    require_state: bool = False,
    expected_last_committed: int | None = None,
) -> str | None:
    state = book / "추적" / "_tracking-state.json"
    if not state.exists():
        if require_state:
            return "추적/_tracking-state.json이 없습니다. 본문이 있는 작품은 /story-import의 기존 추적 프로젝트 이전 절차로 추적을 재구성하세요(전체 작품 재분석 불필요). 새 작품은 tracking_commit.py init으로 초기화하세요"
        return None
    try:
        document = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "추적/_tracking-state.json을 해석할 수 없습니다. 본문 쓰기를 멈추고 /story-import를 다시 실행하세요. 상태를 추측하거나 직접 채우지 마세요"
    if not isinstance(document, dict) or document.get("schema_version") != 4:
        return "추적/_tracking-state.json이 현재 schema_version=4 형식이 아닙니다. 본문 쓰기를 멈추고 /story-import를 다시 실행하세요. 이전 구조 호환 경로는 제공하지 않습니다"
    revision = document.get("state_revision")
    if type(revision) is not int:
        return "추적/_tracking-state.json에 정수 state_revision이 없습니다. 본문 쓰기를 멈추고 /story-import를 다시 실행하세요"
    context = book / "추적" / "문맥.md"
    context_revision = None
    try:
        match = re.search(r"状态修订：(\d+)", context.read_text(encoding="utf-8"))
        if match:
            context_revision = int(match.group(1))
    except (OSError, UnicodeError):
        pass
    if context_revision != revision:
        shown = "없음" if context_revision is None else str(context_revision)
        return (
            f"추적/문맥.md의 상태 리비전 {shown}과(와) _tracking-state.json의 {revision}이(가) 다릅니다. "
            "해당 장의 mode=revision 트랜잭션을 다시 제출해 파생 문서를 재구성하세요(expected_state_revision은 추적/_tracking-state.json의 state_revision 값 사용. check 실패 시 JSON은 출력하지 않음)"
        )
    if expected_last_committed is not None:
        last_committed = document.get("last_committed_chapter")
        if type(last_committed) is not int:
            return "추적/_tracking-state.json에 정수 last_committed_chapter가 없습니다. 본문 쓰기를 멈추고 /story-import를 다시 실행하세요"
        # 장 번호가 이미 추적 범위에 있으면 개고·이름 변경·원고 백업이지 새 장 최초 생성이 아니다. 파일명만 새로워도 제출한 장이므로
        # 순서 검증은 항상 실패해 workflow-revision 원고 백업 단계가 막히므로 건너뛴다.
        if expected_last_committed < last_committed:
            return None
        if last_committed != expected_last_committed:
            return (
                f"추적 제출 완료: 제{last_committed}장. 새로 작성할 제{expected_last_committed + 1}장에 앞서 "
                f"먼저 제출할 추적 트랜잭션: 제{expected_last_committed}장"
            )
    return None


def continuity_findings(root: Path) -> list[str]:
    """배치 간 연속성 보완: ① 장을 썼는데 이어쓰기 카드가 뒤처진 추적 노후화 ② 실수 복사 가능성이 큰 동일 장 제목.
    모델과 무관하게 회차·세션 경계에서 안내하고 문제가 없으면 조용히 종료한다. 범위는 누락 검사처럼 저장소 전체이며 비활성 작품도 의도적으로 포함한다.
    .active-book으로 좁히지 않는다. mtime+1초 허용을 쓰는 휴리스틱 안내라 checkout·-p 복사에 오차가 있을 수 있다."""
    msgs: list[str] = []
    for book in _discover_all_books(root):
        body_dir = book / "본문"
        chapters = sorted(body_dir.glob("제*장*.md")) if body_dir.is_dir() else []
        # ① 추적 정보 노후화(추적/문맥.md가 있는 장편만).
        ctx = book / "추적" / "문맥.md"
        checkpoint_issue = tracking_checkpoint_issue(book, require_state=bool(chapters))
        if checkpoint_issue:
            msgs.append(f"[continuity] {safe_rel(root, book)}：{checkpoint_issue}。")
        if chapters and ctx.exists():
            newest = max((c.stat().st_mtime for c in chapters), default=0)
            try:
                ctx_m = ctx.stat().st_mtime
            except Exception:
                ctx_m = 0
            if newest > ctx_m + 1:
                latest = max(chapters, key=lambda c: c.stat().st_mtime).name
                msgs.append(f"[continuity] {safe_rel(root, book)}：본문은 다음 파일까지 갱신됨: 「{latest}」. 이어 쓰기 상태 카드가 더 오래되었습니다. 해당 장의 tracking_commit.py 트랜잭션을 제출하고 check 통과 후 이어 쓰세요. 문맥.md/복선.md를 따로 직접 수정하지 마세요.")
        # ①b 이어쓰기 카드 예산: 트랜잭션 도구가 문맥.md를 통째로 재구축하며 상한은 12288바이트다.
        # 방치하면 장당 읽기량이 장 수에 비례해 늘어 전체 O(N^2)가 된다. 차단하지 않고 안내하며 초과 블록은 추적/장별기록/로 옮겨야 한다.
        if ctx.exists():
            try:
                ctx_size = ctx.stat().st_size
            except Exception:
                ctx_size = 0
            if ctx_size > 12288:
                msgs.append(f"[continuity] {safe_rel(root, book)}：추적/문맥.md가 {ctx_size}바이트로 이어 쓰기 상태 카드의 12288바이트 한도를 초과했습니다. mode=revision 트랜잭션으로 tracking_commit.py가 전체를 재구성하게 하세요. 직접 수정하거나 계속 덧붙이지 마세요.")
        # ② 파일명 第N章_标题의 제목 부분으로 중복 제목을 찾는다.
        titles: dict[str, list[str]] = {}
        for c in chapters:
            mt = re.match(r"^제0*\d+장[_\- 　]+(.+)$", c.stem)
            if not mt:
                continue
            key = mt.group(1).strip()
            if key:
                titles.setdefault(key, []).append(c.name)
        for title, files in titles.items():
            if len(files) > 1:
                msgs.append(f"[continuity] {safe_rel(root, book)}：{len(files)}개 장의 제목 중복: 「{title}」（{('、'.join(files))[:60]}). 제목을 바꾸는 것이 좋습니다.")
    return msgs


def session_start() -> None:
    root = project_root()
    messages: list[str] = []
    sentinel = root / ".story-deployed"
    if sentinel.exists():
        sent_text = sentinel.read_text(encoding="utf-8", errors="ignore")
        if "target_cli:" not in sent_text:
            messages.append("[story-setup] .story-deployed에 target_cli 필드가 없습니다. $story-setup을 다시 실행하세요.")
        elif "codex" not in re.search(r"target_cli:\s*(.*)", sent_text).group(1):  # type: ignore[union-attr]
            messages.append("[story-setup] 현재 배포 표식에 codex가 없습니다. Codex 훅·에이전트가 필요하면 $story-setup을 다시 실행하고 Codex를 선택하세요.")
    book = read_active_book(root)
    if book:
        ctx = book / "추적" / "문맥.md"
        if ctx.exists():
            messages.append(f"[story context] Active book: {safe_rel(root, book)}. Read {safe_rel(root, ctx)} before continuing long-form writing.")
        else:
            messages.append(f"[story context] Active story project detected: {safe_rel(root, book)}.")
    messages.extend(continuity_findings(root))
    if messages:
        emit(hook_context("SessionStart", "\n".join(messages)))


def resolve_target(root: Path, target: str, base: Path | None = None) -> Path:
    normalized = target.replace("\\", "/")
    p = Path(normalized)
    return p if p.is_absolute() else ((base or root) / p).resolve()


def _shell_words(segment: str) -> list[str]:
    """JS shellWords와 같은 따옴표 인식 선형 토큰화. 따옴표 안 문자는 그대로 취하고 짝은 제거하며 미종결이면 구간 끝까지 취한다.
    ASCII 공백·Tab·CR·LF만 나누고 셸 구분자가 아닌 U+3000은 유지한다.
    resolve_target이 Windows 역슬래시를 경로 구분자로 쓰므로 역슬래시 이스케이프를 해석하지 않는다."""
    words: list[str] = []
    current = ""
    started = False
    quote = ""
    escaped = False
    for ch in segment:
        if escaped:
            current += ch
            escaped = False
            started = True
            continue
        if ch == "\\" and quote != "'":
            current += ch
            escaped = True
            started = True
            continue
        if quote:
            if ch == quote:
                quote = ""
            else:
                current += ch
            continue
        if ch in ('"', "'"):
            quote = ch
            started = True
            continue
        if ch in (" ", "\t", "\r", "\n"):
            if started:
                words.append(current)
            current = ""
            started = False
            continue
        started = True
        current += ch
    if started:
        words.append(current)
    return words


def _shell_segments(command: str) -> list[str]:
    """따옴표 밖 셸 제어 기호로만 나누며 따옴표는 _shell_words가 제거하도록 남긴다."""
    segments: list[str] = []
    current = ""
    quote = ""
    escaped = False
    for ch in command:
        if escaped:
            current += ch
            escaped = False
            continue
        if ch == "\\" and quote != "'":
            current += ch
            escaped = True
            continue
        if quote:
            current += ch
            if ch == quote:
                quote = ""
            continue
        if ch in ('"', "'"):
            quote = ch
            current += ch
            continue
        if ch in (";", "&", "|", "\n"):
            if current:
                segments.append(current)
            current = ""
            continue
        current += ch
    if current:
        segments.append(current)
    return segments


def _before_shell_redirection(segment: str) -> str:
    """첫 따옴표 밖 리디렉션과 이후 내용을 제거하며 2>의 fd 숫자도 제거한다."""
    current = ""
    quote = ""
    escaped = False
    for ch in segment:
        if escaped:
            current += ch
            escaped = False
            continue
        if ch == "\\" and quote != "'":
            current += ch
            escaped = True
            continue
        if quote:
            current += ch
            if ch == quote:
                quote = ""
            continue
        if ch in ('"', "'"):
            quote = ch
            current += ch
            continue
        if ch in ("<", ">"):
            return re.sub(r"\d+$", "", current)
        current += ch
    return current


def _read_shell_word(value: str, start: int) -> tuple[str, int]:
    word = ""
    quote = ""
    escaped = False
    started = False
    index = start
    while index < len(value):
        ch = value[index]
        if escaped:
            word += ch
            escaped = False
            started = True
            index += 1
            continue
        if ch == "\\" and quote != "'":
            word += ch
            escaped = True
            started = True
            index += 1
            continue
        if quote:
            if ch == quote:
                quote = ""
            else:
                word += ch
            started = True
            index += 1
            continue
        if ch in ('"', "'"):
            quote = ch
            started = True
            index += 1
            continue
        if ch in (" ", "\t", "\r", "\n", ";", "&", "|", "<", ">", "(", ")"):
            break
        word += ch
        started = True
        index += 1
    return (word if started else "", index)


def _read_heredoc_delimiter(value: str, start: int) -> tuple[str, int]:
    word = ""
    quote = ""
    escaped = False
    started = False
    index = start
    while index < len(value):
        ch = value[index]
        if escaped:
            word += ch
            escaped = False
            started = True
            index += 1
            continue
        if ch == "\\" and quote != "'":
            next_char = value[index + 1:index + 2]
            if quote == '"' and next_char not in ("$", "`", '"', "\\", "\n"):
                word += ch
            else:
                escaped = True
            started = True
            index += 1
            continue
        if quote:
            if ch == quote:
                quote = ""
            else:
                word += ch
            started = True
            index += 1
            continue
        if ch in ('"', "'"):
            quote = ch
            started = True
            index += 1
            continue
        if ch in (" ", "\t", "\r", "\n", ";", "&", "|", "<", ">", "(", ")"):
            break
        word += ch
        started = True
        index += 1
    return (word if started else "", index)


def _heredoc_declarations(line: str) -> list[tuple[str, bool]]:
    declarations: list[tuple[str, bool]] = []
    quote = ""
    escaped = False
    index = 0
    while index < len(line):
        ch = line[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if ch == "\\" and quote != "'":
            escaped = True
            index += 1
            continue
        if quote:
            if ch == quote:
                quote = ""
            index += 1
            continue
        if ch in ('"', "'"):
            quote = ch
            index += 1
            continue
        if not (
            ch == "<"
            and index + 1 < len(line)
            and line[index + 1] == "<"
            and (index == 0 or line[index - 1] != "<")
            and (index + 2 >= len(line) or line[index + 2] != "<")
        ):
            index += 1
            continue
        cursor = index + 2
        strip_tabs = False
        if cursor < len(line) and line[cursor] == "-":
            strip_tabs = True
            cursor += 1
        while cursor < len(line) and line[cursor] in (" ", "\t"):
            cursor += 1
        delimiter, cursor = _read_heredoc_delimiter(line, cursor)
        if delimiter:
            declarations.append((delimiter, strip_tabs))
        index = max(index + 1, cursor)
    return declarations


def _mask_heredoc_bodies(command: str) -> str:
    pending: list[tuple[str, bool]] = []
    output: list[str] = []
    for line in command.split("\n"):
        if pending:
            delimiter, strip_tabs = pending[0]
            comparable = re.sub(r"^\t+", "", line) if strip_tabs else line
            if comparable == delimiter:
                pending.pop(0)
                output.append(line)
            else:
                output.append(" " * len(line))
            continue
        pending.extend(_heredoc_declarations(line))
        output.append(line)
    return "\n".join(output)


def _command_word_index(words: list[str]) -> int:
    index = 0
    while index < len(words):
        while index < len(words) and (
            re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[index])
            or words[index] == "noglob"
        ):
            index += 1
        if index < len(words) and words[index] == "command":
            index += 1
            while index < len(words):
                option = words[index]
                if option == "--":
                    index += 1
                    break
                if option in ("-v", "-V") or re.match(r"^-[p]*[vV]", option):
                    return len(words)
                if option == "-p" or re.match(r"^-p+$", option):
                    index += 1
                    continue
                break
            continue
        if index < len(words) and words[index] == "env":
            index += 1
            while index < len(words):
                option = words[index]
                if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", option) or option in (
                    "-i",
                    "--ignore-environment",
                ):
                    index += 1
                    continue
                if option in ("-u", "--unset"):
                    index += 2
                    continue
                if option.startswith("--unset=") or (re.match(r"^-u.+", option) and option != "-u"):
                    index += 1
                    continue
                if option == "--":
                    index += 1
                break
            continue
        break
    return index


def _nested_shell_command(args: list[str]) -> str:
    value_options = {"-o", "+o", "-O", "+O"}
    index = 0
    while index < len(args):
        option = args[index]
        if option == "--":
            return ""
        if option == "-c" or (re.match(r"^-[^-]+$", option) and "c" in option[1:]):
            return args[index + 1] if index + 1 < len(args) else ""
        if option in value_options:
            index += 2
            continue
        if not option.startswith(("-", "+")):
            break
        index += 1
    return ""


def _command_substitutions(command: str) -> list[str]:
    substitutions: list[str] = []
    quote = ""
    escaped = False
    index = 0
    while index < len(command):
        ch = command[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if ch == "\\" and quote != "'":
            escaped = True
            index += 1
            continue
        if quote == "'":
            if ch == "'":
                quote = ""
            index += 1
            continue
        if ch == '"':
            quote = "" if quote == '"' else '"'
            index += 1
            continue
        if not quote and ch == "'":
            quote = "'"
            index += 1
            continue
        if ch == "$" and command[index + 1:index + 2] == "(" and command[index + 2:index + 3] != "(":
            depth = 1
            inner_quote = ""
            inner_escaped = False
            end = index + 2
            while end < len(command):
                inner = command[end]
                if inner_escaped:
                    inner_escaped = False
                    end += 1
                    continue
                if inner == "\\" and inner_quote != "'":
                    inner_escaped = True
                    end += 1
                    continue
                if inner_quote:
                    if inner == inner_quote:
                        inner_quote = ""
                    end += 1
                    continue
                if inner in ('"', "'"):
                    inner_quote = inner
                elif inner == "(":
                    depth += 1
                elif inner == ")":
                    depth -= 1
                    if depth == 0:
                        break
                end += 1
            if depth == 0:
                substitutions.append(command[index + 2:end])
                index = end + 1
                continue
        if ch == "`":
            end = index + 1
            tick_escaped = False
            while end < len(command):
                inner = command[end]
                if tick_escaped:
                    tick_escaped = False
                elif inner == "\\":
                    tick_escaped = True
                elif inner == "`":
                    break
                end += 1
            if end < len(command):
                substitutions.append(command[index + 1:end])
                index = end + 1
                continue
        index += 1
    return substitutions


def _redirect_targets(command: str, keep_all: bool = False) -> list[str]:
    # keep_all은 JS redirectTargets와 같다. cd가 있으면 대상을 모두 얻고 cd 디렉터리를 붙인 뒤 본문인지 판정한다.
    targets: list[str] = []
    quote = ""
    escaped = False
    index = 0
    while index < len(command):
        ch = command[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if ch == "\\" and quote != "'":
            escaped = True
            index += 1
            continue
        if quote:
            if ch == quote:
                quote = ""
            index += 1
            continue
        if ch in ('"', "'"):
            quote = ch
            index += 1
            continue
        if ch != ">":
            index += 1
            continue
        cursor = index + (2 if command[index + 1:index + 2] == ">" else 1)
        if command[cursor:cursor + 1] in ("|", "&"):
            cursor += 1
        while command[cursor:cursor + 1] in (" ", "\t"):
            cursor += 1
        target, cursor = _read_shell_word(command, cursor)
        if keep_all or "본문" in target:
            targets.append(target)
        index = max(index + 1, cursor)
    return targets


def _write_operands(command: str, args: list[str]) -> list[str]:
    operands: list[str] = []
    value_options = (
        {"-d", "--date", "-r", "--reference", "-t", "--time"}
        if command == "touch"
        else set()
    )
    options = True
    index = 0
    while index < len(args):
        arg = args[index]
        if options and arg == "--":
            options = False
            index += 1
            continue
        if options and arg in value_options:
            index += 2
            continue
        if options and any(
            option.startswith("--") and arg.startswith(option + "=")
            for option in value_options
        ):
            index += 1
            continue
        if options and arg.startswith("-") and arg != "-":
            index += 1
            continue
        operands.append(arg)
        index += 1
    return operands


def _command_basename(value: str) -> str:
    return re.split(r"[\\/]", value or "")[-1]


def _join_posix(directory: str, name: str) -> str:
    """디렉터리 대상은 항상 /로 잇는다. Windows Path의 역슬래시는 세 호스트의 정확 비교를 깨뜨린다."""
    return re.sub(r"[\\/]+$", "", directory) + "/" + name


def _copy_like_targets(command: str, args: list[str]) -> list[str]:
    positionals: list[str] = []
    target_directory = ""
    directory_only = False
    options = True
    index = 0
    while index < len(args):
        arg = args[index]
        if options and arg == "--":
            options = False
            index += 1
            continue
        if options and arg in ("-t", "--target-directory"):
            target_directory = args[index + 1] if index + 1 < len(args) else ""
            index += 2
            continue
        if options and arg.startswith("--target-directory="):
            target_directory = arg[len("--target-directory="):]
            index += 1
            continue
        if options and command == "install" and arg in ("-d", "--directory"):
            directory_only = True
            index += 1
            continue
        if options and arg.startswith("-") and arg != "-":
            index += 1
            continue
        positionals.append(arg)
        index += 1
    if directory_only or not positionals:
        return []
    if target_directory:
        return [_join_posix(target_directory, _command_basename(source)) for source in positionals]
    if len(positionals) < 2:
        return []
    destination = positionals[-1]
    normalized = destination.replace("\\", "/")
    if normalized.endswith("/") or normalized.rsplit("/", 1)[-1] == "본문":
        return [_join_posix(destination, _command_basename(source)) for source in positionals[:-1]]
    return [destination]


def extract_prose_targets_from_command(command: str, depth: int = 0) -> list[str]:
    # 正文 경로는 실제 쓰기 작업의 목적지일 때만 쓰기 대상으로 본다.
    # 리디렉션·tee·touch·cp/mv 목적지가 해당한다. 명령 전체를 검사하면
    # heredoc·문서 문자열·grep 패턴에서 단순히 언급한
    # 본문/제N장.md까지 잡아 편집을 잘못 거부한다.
    targets: list[str] = []
    scannable = _mask_heredoc_bodies(command)
    if depth < 8:
        for nested in _command_substitutions(scannable):
            targets.extend(extract_prose_targets_from_command(nested, depth + 1))
    # JS와 같이 `cd 书目录 && cat > 본문/...`의 상대 쓰기 대상은 cd 이후 디렉터리에 붙인다.
    # cd가 없으면 전체 명령에서 리디렉션을 찾는 기존 동작을 유지한다.
    parsed = []
    # `>|`, `>&file`, `&>`는 파이프·백그라운드가 아닌 리디렉션이다. 먼저 `>`로 통일해 분할 시 대상을 잃지 않는다.
    segment_source = re.sub(r">&(?!\d)", ">", scannable.replace("&>", " >").replace(">|", ">"))
    for raw_segment in _shell_segments(segment_source):
        # JS shellWords처럼 따옴표를 고려한다. str.split()은 U+3000과 따옴표 안 공백으로 대상을 잘라 버린다.
        # 마지막 book/본문/제1장.md만 얻어 다른 작품을 판정하고 거기에 개요가 있으면 잘못 허용한다.
        words = _shell_words(_before_shell_redirection(raw_segment))
        command_index = _command_word_index(words)
        name = _command_basename(words[command_index]) if command_index < len(words) else ""
        parsed.append((raw_segment, name, words[command_index + 1:]))
    has_cd = any(name == "cd" for _, name, _ in parsed)
    if not has_cd:
        targets.extend(_redirect_targets(scannable))
    cwd = ""

    def is_absolute(value: str) -> bool:
        return bool(re.match(r"^([\\/~]|[A-Za-z]:[\\/])", value))

    def under_cwd(value: str) -> str:
        return f"{cwd.rstrip('/')}/{value}" if cwd and not is_absolute(value) else value

    for raw_segment, command_name, command_args in parsed:
        if command_name == "cd":
            directory = next((arg for arg in command_args if not arg.startswith("-")), None)
            if directory:
                cwd = directory if is_absolute(directory) or not cwd else under_cwd(directory)
            continue
        if has_cd:
            targets.extend(
                resolved for resolved in (under_cwd(target) for target in _redirect_targets(raw_segment, True))
                if "본문" in resolved
            )
        if command_name in ("sh", "bash", "dash", "ksh", "zsh"):
            nested = _nested_shell_command(command_args)
            if nested:
                targets.extend(extract_prose_targets_from_command(nested, depth + 1))
        if command_name in ("tee", "touch"):
            targets.extend(
                destination
                for destination in map(under_cwd, _write_operands(command_name, command_args))
                if "본문" in destination
            )
        if command_name in ("cp", "mv", "install"):
            targets.extend(
                destination
                for destination in map(under_cwd, _copy_like_targets(command_name, command_args))
                if "본문" in destination
            )
    return list(dict.fromkeys(target for target in targets if target))


def extract_apply_patch_targets(command: str) -> list[str]:
    # JS extractPatchTargets와 정확히 대응하며 test-prose-net-parity.sh의 명령 함수
    # fixture로 검증한다. Add/Update만 보면 Update File 하위 지시인 `*** Move to:`를 놓친다.
    # apply_patch 이름 변경·이동의 저장 경로는 목적지이며 원본은 없어진다. 예전에는 개요 없는 초안이
    # `Update File: draft.md` + `Move to: 书/본문/제9장.md`로 본문/에 들어갈 수 있었다. 개요 관문을 통과하고
    # 작성 후 검사는 사라진 원본을 보았기 때문이다. 따라서 Move 목적지로 같은 구간의 원본 대상을 대체한다.
    # Delete File은 목록에 넣지 않는다. 삭제는 쓰기가 아니고 prose_block_reason은 기존 본문을 허용하며 삭제 후에는
    # 검사할 파일도 없어 원고 삭제를 오보하기 때문이다. 다만 Delete에도 Move to가 있을 수 있어
    # 그 목적지는 목록에 넣어야 한다. 따라서 Delete는 대체할 원본 칸만 비운다.
    targets: list[str] = []
    source_index = -1
    for line in command.splitlines():
        # 제어 행은 0열부터 시작해야 한다. 선행 공백은 apply_patch 문맥 표식이므로 strip하지 않는다.
        m = re.match(r"^\*\*\* (Add|Update|Delete) File: (.+)$", line)
        if m:
            if m.group(1) == "Delete":
                source_index = -1
                continue
            targets.append(m.group(2).strip())
            source_index = len(targets) - 1
            continue
        m = re.match(r"^\*\*\* Move to: (.+)$", line)
        if m:
            destination = m.group(1).strip()
            if not destination:
                continue
            if source_index >= 0:
                targets[source_index] = destination
            else:
                targets.append(destination)
            source_index = -1
    return targets


def target_paths_from_hook(obj: dict[str, Any]) -> list[Path]:
    root = project_root()
    base = root
    if HOOK_CWD and HOOK_CWD.is_dir():
        try:
            HOOK_CWD.relative_to(root)
            base = HOOK_CWD
        except ValueError:
            pass
    tool_name = str(obj.get("tool_name") or "")
    tool_input = obj.get("tool_input") if isinstance(obj.get("tool_input"), dict) else {}
    assert isinstance(tool_input, dict)
    raw_targets: list[str] = []
    for key in ("file_path", "filePath", "path", "target", "filename"):
        value = tool_input.get(key)
        if isinstance(value, str):
            raw_targets.append(value)
    command = tool_input.get("command")
    if isinstance(command, str):
        if tool_name == "Bash":
            raw_targets.extend(extract_prose_targets_from_command(command))
        else:
            raw_targets.extend(extract_apply_patch_targets(command))
            raw_targets.extend(extract_prose_targets_from_command(command))
    return [resolve_target(root, t, base) for t in raw_targets if t]


# 미확장 셸 변수: $VAR / ${VAR} / $(cmd). JS core UNEXPANDED_SHELL_VAR와 같은 형식이다.
UNEXPANDED_SHELL_VAR = re.compile(r"\$(\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*|\()")

# 사실상 빈 개요는 JS outlineIsEmpty와 같다. BOM·행 앞 제목 기호를 빼고 제목 텍스트는 포함해
# ASCII·전각 공백 외의 문자가 _OUTLINE_MIN_CHARS 코드 포인트 미만이면 빈 것으로 본다. 작성 여부만 재며
# v0.8 필드는 검사하지 않는다. 읽기 실패·비UTF-8은 비어 있지 않다고 허용한다. test-prose-net-parity.sh C절이 일치를 보장한다.
_OUTLINE_MIN_CHARS = 30


def _outline_is_empty(file: Path) -> bool:
    try:
        text = file.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if text.startswith("\ufeff"):
        text = text[1:]
    body = "".join(re.sub(r"^[ \t]*#+", "", line) for line in text.split("\n"))
    return len(re.sub(r"[ \t\r\n\f\v\u3000]", "", body)) < _OUTLINE_MIN_CHARS


def prose_block_reason(root: Path, abs_path: Path) -> str | None:
    base = abs_path.name
    parent = abs_path.parent.name
    if base == "본문.md":
        if abs_path.exists():
            return None
        book_dir = abs_path.parent
        if (root / "작품분석실" / book_dir.name).exists():
            return None
        if not (book_dir / "설정.md").exists():
            return None
        if not (book_dir / "구간개요.md").exists():
            # 문구는 JS proseBlockReason과 맞추며 test-prose-net-parity.sh Part E로 검증한다.
            return f"⛔ 본문 쓰기 차단: {safe_rel(root, abs_path)}와 같은 폴더에 구간개요.md가 없습니다. story-short-write에 따라 구간개요.md를 완성한 뒤 본문을 쓰세요."
        return None
    if parent != "본문":
        return None
    if not re.match(r"^제.*장.*\.md$", base):
        return None
    m = re.match(r"^제0*(\d+)장", base)
    if not m:
        return None
    num = m.group(1)
    book_dir = abs_path.parent.parent
    # 새 작품은 개요·추적·설정 구조 전에 본문을 만들 수 있으므로 핵심 가드는 확인 실패 시 차단해야 한다.
    # 상대 경로는 HOOK_CWD로 해석한다. 이 기본 가드를 약화해 cwd 의미 문제를 숨기면 안 된다.
    state = book_dir / "추적" / "_tracking-state.json"
    # story-import는 기존 본문 복사 후 tracking init 전까지 쓸 수 있다. state가 생기면
    # 현재 추적 프로토콜에 들어가므로 작품분석실/ 자산을 유지한다는 이유로 가드를 영구 우회하지 않는다.
    if (root / "작품분석실" / book_dir.name).exists() and not state.exists():
        return None
    exists = abs_path.exists()
    outline_dir = book_dir / "개요"
    found = False
    if not exists:
        outlines: list[Path] = []
        if outline_dir.is_dir():
            outlines = sorted(
                (c for c in outline_dir.iterdir()
                 if (fm := re.match(r"^상세개요_제0*(\d+)장.*\.md$", c.name)) and fm.group(1) == num),
                key=lambda c: c.name,
            )
        found = bool(outlines)
        # 같은 장의 여러 개요(0 채움·제목 차이) 중 하나라도 내용이 있으면 허용한다. 문구는 JS와 정확히 같다.
        if found and all(_outline_is_empty(c) for c in outlines):
            return (
                f"⛔ 본문 쓰기 차단: 제{num}장의 상세 개요({safe_rel(root, outlines[0])})가 비어 있습니다"
                f"(# 기호와 공백을 제외하고 {_OUTLINE_MIN_CHARS}자 미만). story-long-write의 장별 절차에 따라 상세 개요를 완성하세요"
                "(이번 장의 사건과 주인공의 선택). 그 뒤 본문을 쓰세요."
            )
        if not found:
            # JS와 동일하게 셸 변수를 확장하지 못해도 차단하되 경로 해석 실패라는 정확한 사유를 알린다.
            if UNEXPANDED_SHELL_VAR.search(safe_rel(root, abs_path)) and not book_dir.exists():
                return f"⛔ 본문 쓰기 차단: 쓰기 경로에 치환되지 않은 셸 변수가 있습니다({safe_rel(root, abs_path)}). 보호 검사가 해당 상세 개요를 확인할 수 없습니다. 실제 프로젝트 경로(예: 작품명/본문/제{int(num):03d}장_제목.md)로 다시 작성하세요."
            return f"⛔ 본문 쓰기 차단: 제 {num} 장에 상세 개요가 없습니다({safe_rel(root, outline_dir)}/상세개요_제{int(num):03d}장.md). story-long-write의 장별 절차로 상세 개요를 보완한 뒤 본문을 쓰세요."
    checkpoint_issue = tracking_checkpoint_issue(
        book_dir,
        require_state=True,
        expected_last_committed=None if exists else int(num) - 1,
    )
    if checkpoint_issue:
        return f"⛔ 본문 쓰기 차단: {safe_rel(root, book_dir)}: {checkpoint_issue}."
    if exists:
        return None
    # 미처리 문제 관문(무상태): N장을 최초 생성하기 전에 앞 장에 미수정 문제 문장 패턴이 있고 ‘去味:跳过’가 없으면 먼저 수정한다.
    # 앞 장 파일에서 즉시 판정하며 상태 파일은 쓰지 않는다. 앞 장을 못 찾거나 읽지 못하면 오탐 대신 통과시킨다.
    # js↔py 안내는 check-hook-regex-sync.sh, 판정은 test-prose-net-parity.sh Part E가 일치를 보장한다.
    prev_num = int(num) - 1
    if prev_num >= 1:
        prev_file = None
        try:
            # ext4/overlayfs iterdir는 해시 순서이므로 정렬하지 않으면 같은 장 번호의 원고 백업을 고를 수 있다.
            # 이미 수정된 과거 텍스트를 미처리로 보고할 수 있다(workflow-revision의 원고 백업 산출물).
            # _원본_ 백업을 명시적으로 빼고 정렬해 네 호스트·파일시스템 모두 같은 앞 장을 선택하게 한다.
            candidates = sorted(
                c for c in abs_path.parent.iterdir()
                if re.match(r"^제0*(\d+)장.*\.md$", c.name)
                and int(re.match(r"^제0*(\d+)장", c.name).group(1)) == prev_num
                and "_원본_" not in c.name
            )
            prev_file = candidates[0] if candidates else None
        except OSError:
            prev_file = None
        if prev_file is not None:
            prev_text = None
            try:
                prev_text = prev_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                prev_text = None
            if prev_text is not None and not _has_deslop_skip_marker(prev_text):
                hits = [ln for ln in toxic_phrase_findings(prev_text, load_style_whitelist(prev_file)) if ln.startswith("第")]
                if hits:
                    shown = hits[:6]
                    more = len(hits) - len(shown)
                    reason = (
                        f"⛔ 본문 쓰기 차단: 앞 장({prev_file.name})에 {len(hits)}곳의 미수정 문제 문장이 있습니다. "
                        f"모두 수정한 뒤 다음 장을 쓰세요: 제{num}장. 사용자가 명시적으로 면제하면 앞 장 제목 아래에 <!-- 去味:跳过 -->를 추가하고 다시 시도하세요.\n"
                        + "\n".join(shown)
                    )
                    if more > 0:
                        reason += f"\n(추가 {more}곳, {toxic_rescan_hint(prev_file)}）"
                    return reason
    return None


def pre_tool_prose_guard(obj: dict[str, Any]) -> None:
    root = project_root()
    for path in target_paths_from_hook(obj):
        reason = prose_block_reason(root, path)
        if reason:
            emit({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            })
            return


def find_command(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("command", "cmd", "script"):
            if isinstance(value.get(key), str):
                return value[key]
        for key in ("tool_input", "input", "parameters", "args"):
            found = find_command(value.get(key))
            if found:
                return found
    return ""


def is_git_commit_command(raw: str) -> bool:
    raw = raw.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ; ")
    try:
        lexer = shlex.shlex(raw, posix=True, punctuation_chars="();|&{}")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except TypeError:
        try:
            tokens = shlex.split(raw, posix=True)
        except Exception:
            tokens = raw.split()
    except Exception:
        tokens = raw.split()
    assignment = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
    separators = {";", "&&", "||", "|", "|&", "&"}
    openers = {"(", "{"}
    closers = {")",
        "}",
    }
    control_words = {"then", "do", "else", "elif"}
    wrappers = {"command", "noglob"}
    git_options_with_value = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix", "--config-env"}

    def skip_shell_wrappers(i: int) -> int:
        while i < len(tokens):
            tok = tokens[i]
            if tok in openers or assignment.match(tok) or tok in wrappers:
                i += 1
                continue
            if tok == "env":
                i += 1
                while i < len(tokens):
                    if assignment.match(tokens[i]) or tokens[i] in {"-i", "--ignore-environment"}:
                        i += 1
                        continue
                    break
                continue
            break
        return i

    def is_git_commit_at(i: int) -> bool:
        if i >= len(tokens) or tokens[i] != "git":
            return False
        i += 1
        while i < len(tokens):
            tok = tokens[i]
            if tok in closers or tok in separators:
                return False
            if tok == "commit":
                return True
            if tok == "--":
                i += 1
                continue
            if tok in git_options_with_value:
                i += 2
                continue
            if any(tok.startswith(prefix + "=") for prefix in git_options_with_value if prefix.startswith("--")):
                i += 1
                continue
            if tok.startswith("-c") and tok != "-c":
                i += 1
                continue
            if tok.startswith("-"):
                i += 1
                continue
            return False
        return False

    segment_start = True
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in separators or tok in control_words:
            segment_start = True
            i += 1
            continue
        if segment_start or tok in openers:
            start = skip_shell_wrappers(i)
            if is_git_commit_at(start):
                return True
            segment_start = False
        i += 1
    return False


# 설정/ 직속 프로젝트 설정: artifact-protocols.md의 관계.md(본문 제목 ‘# 角色关系图’),
# 소재방향.md, 문체.md, 소재본문안내.md 등에는 원래 名字/姓名 필드가 없다.
_SETTING_NON_CHARACTER_FILES = {"관계.md", "소재방향.md", "소재본문안내.md", "문체.md", "세계규칙.md", "세계관.md", "특전.md", "배경설정.md"}


def _is_character_sheet_path(rel: str) -> bool:
    """인물 카드만 검사한다. 설정/ 전체를 검사하면 거짓 경고가 본문 인물 속성 하드코딩 경고를 묻어 버린다.
    validate-story-commit.sh / opencode pre-commit.sh case와 일대일 대응한다(bash↔js↔py 네 호스트 동일).
    ① 설정/角色|人物 하위 파일은 인물 카드. ② 다른 하위 디렉터리는 전체 제외(세계관·세력·보고·원리·관계 등).
    ③ 직속 파일은 알려진 프로젝트 설정 외 모두 인물 카드(주인공.md/조연.md/악역.md 등).
    bash `*`는 `/`를 가로지르므로 `설정/인물/*|*/설정/인물/*`는 어느 设定 구간이든 해당할 수 있다.
    전체 경로에서 ①, 다시 ②를 찾으며 첫 设定만으로 결정하면 설정/其他/설정/인물/x.md에서 bash와 달라진다.
    JS isCharacterSheetPath와 같은 구현이며 scripts/test-prose-net-parity.sh Part E로 검증한다."""
    segments = rel.split("/")
    last = len(segments) - 1
    # ① 어느 设定 뒤에 인물/人物이 바로 오고 그 아래 파일 구간이 있다.
    for i in range(last - 1):
        if segments[i] == "설정" and segments[i + 1] in ("인물", "인물"):
            return True
    # ② 어느 设定 뒤에 2구간 이상이 있어 인물이 아닌 하위 디렉터리에 속한다.
    for i in range(last - 1):
        if segments[i] == "설정":
            return False
    # ③ 设定 직속 파일. ②에서 깊은 경로를 제외했으므로 设定은 끝에서 두 번째 구간이다.
    return last >= 1 and segments[last - 1] == "설정" and segments[last] not in _SETTING_NON_CHARACTER_FILES


def staged_markdown_warnings(root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "-c", "core.quotepath=false", "diff", "--cached", "--relative", "--name-only", "--diff-filter=ACM", "-z", "--", "."],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return ""
    warnings: list[str] = []
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        file = raw.decode("utf-8", errors="ignore")
        if not file.endswith(".md"):
            continue
        full = root / file
        if not full.exists():
            continue
        text = full.read_text(encoding="utf-8", errors="ignore")
        # 일치 의미·경고 문구는 CLI 공통 기준인 JS story_hook_core.js stagedMarkdownWarnings에 맞춘다.
        # name은 re.I로 대소문자를 구분하지 않으며 중국어 안내를 사용한다. py↔js는
        # scripts/test-prose-net-parity.sh Part E로 일치시킨다.
        if file == "본문.md" or "/본문.md" in file or file.startswith("본문/") or "/본문/" in file:
            hits = []
            for idx, line in enumerate(text.splitlines(), 1):
                if re.search(r"(身高|体重|年龄)(\s|　)*(：|:)(\s|　)*[0-9]+", line):
                    hits.append(f"{idx}:{line}")
            if hits:
                warnings.append(f"⚠ {file}: 본문에 인물 속성을 직접 고정했습니다. 설정 파일을 참조하세요: \n" + "\n".join(hits))
        if _is_character_sheet_path(file):
            if not re.search(r"^(\s|　)*(名字|姓名|名称|name)(\s|　)*(：|:)", text, re.M | re.I):
                warnings.append(f"⚠ {file}: 설정 파일에 필수 이름 필드(name/名字)가 없습니다.")
    if not warnings:
        return ""
    return "=== Story Commit Warnings（advisory only）===\n" + "\n".join(warnings) + "\n=== End Warnings ==="


def pre_tool_commit_advisory(obj: dict[str, Any]) -> None:
    command = find_command(obj)
    if not command or not is_git_commit_command(command):
        return
    warnings = staged_markdown_warnings(project_root())
    if warnings:
        emit(hook_context("PreToolUse", warnings))


def compact_summary(event: str) -> None:
    root = project_root()
    lines = ["=== Story Compact Summary ==="]
    book = read_active_book(root)
    if book:
        ctx = book / "추적" / "문맥.md"
        if ctx.exists():
            line_count = len(ctx.read_text(encoding="utf-8", errors="ignore").splitlines())
            lines.append(f"Writing context: {safe_rel(root, ctx)} ({line_count} lines)")
        else:
            lines.append(f"Active story project: {safe_rel(root, book)}")
    else:
        lines.append("Active state: not found")
    try:
        # -z + bytes로 전역 core.quotepath=false의 중국어 파일명도 Windows ANSI에서
        # UnicodeDecodeError를 내지 않게 한다. 여기서는 개수만 센다.
        # --relative -- .로 프로젝트 하위 트리만 센다. 프로젝트가 저장소 하위일 때 없으면 상위 저장소 전체의
        # 변경을 세게 된다(find_changed_prose_files / staged_markdown_warnings와 같은 기준).
        changed = subprocess.check_output(["git", "-C", str(root), "-c", "core.quotepath=false", "diff", "--relative", "--name-only", "-z", "--", "."], stderr=subprocess.DEVNULL)
        staged = subprocess.check_output(["git", "-C", str(root), "-c", "core.quotepath=false", "diff", "--relative", "--name-only", "--cached", "-z", "--", "."], stderr=subprocess.DEVNULL)
        n_changed = len([x for x in changed.split(b"\0") if x])
        n_staged = len([x for x in staged.split(b"\0") if x])
        lines.append(f"Git: {n_changed} unstaged, {n_staged} staged")
    except Exception:
        pass
    emit({"systemMessage": "\n".join(lines)})


def stop_event() -> None:
    # Codex에는 PostToolUse가 없어 회차 종료 Stop에서 이번 git 변경 본문을 다시 검사한다.
    # 절단·거절문·작업 용어·반복을 비차단으로 검사하며 없으면 조용히 종료한다. 파싱 실패는 항상 {continue:True}다.
    # Stop 훅은 stdout의 JSON이 필요하다.
    try:
        root = project_root()
        blocks: list[str] = []
        for abs_path in find_changed_prose_files(root):
            try:
                text = abs_path.read_text(encoding="utf-8")
            except Exception:
                continue
            findings = prose_net_findings(text, load_style_whitelist(abs_path), toxic_rescan_hint(abs_path))
            if findings:
                blocks.append(f"=== {safe_rel(root, abs_path)} ===\n" + "\n".join(findings))
        if blocks:
            emit({
                "continue": True,
                "systemMessage": "=== 본문 보완 검사(응답 종료 시 재검사, 모델과 무관）===\n명확한 문제가 감지되면 본문을 수정하고 문제가 없을 때까지 다시 검사하세요:\n"
                + "\n".join(blocks),
            })
            return
    except Exception:
        pass
    emit({"continue": True})


def main() -> int:
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    obj = read_hook_input()
    if event == "session-start":
        session_start()
    elif event == "pre-tool-prose-guard":
        pre_tool_prose_guard(obj)
    elif event == "pre-tool-commit-advisory":
        pre_tool_commit_advisory(obj)
    elif event == "pre-compact":
        compact_summary("PreCompact")
    elif event == "post-compact":
        compact_summary("PostCompact")
    elif event == "stop":
        stop_event()
    else:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
