#!/bin/bash
# test-prose-backstop-hook.sh — check-prose-after-write.sh의 회귀 테스트
# 핵심 보장: ① 본문 아닌 파일(코드/상세 개요/설정/전체 개요/독립 본문)을 과도하게 잡지 않음 ② 실제 본문 보완 검사 실행
# ③ 가벼운 내용 검사망이 강한 신호(잘림/거부 표현/제작 용어/반복)를 정확히 잡고 정상 본문(병렬+대화+서스펜스)은 조용함.
# 과도한 탐지는 인터프리터 없는 경로 조건으로 검증한다. 내용 검사는 동등성 테스트와 같은 node 공유 코어를 사용한다.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
[ -z "$REPO_ROOT" ] && { echo "Error: not in a git repository" >&2; exit 1; }
HOOK="$REPO_ROOT/skills/story-setup/references/templates/hooks/check-prose-after-write.sh"
[ -f "$HOOK" ] || { echo "FAIL: hook not found: $HOOK" >&2; exit 1; }

bash -n "$HOOK" || { echo "FAIL: hook has syntax errors" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# 실제 책 구조: 설정.md + 개요/ + 본문/
mkdir -p "$TMP/某书/본문" "$TMP/某书/개요" "$TMP/docs/본문" "$TMP/游离/본문"
printf '# 설정\n主角江晨。\n' > "$TMP/某书/설정.md"
printf '## 细纲（제1장）\n- 情节点序列：本章细纲，作为AI我无法继续。他握紧拳头。他握紧拳头。\n' > "$TMP/某书/개요/상세개요_제001장.md"
printf '# 개요\n제1장 제2장 细纲 本章 下一章\n' > "$TMP/某书/개요/개요.md"
printf '# 卷纲\n本卷细纲。\n' > "$TMP/某书/개요/권개요_제1권.md"
printf 'const x=1; // 细纲 本章 下一章 作为AI我无法继续 复读复读复读\n' > "$TMP/某书/x.js"
printf '## 본문\n按照细纲，作为AI我无法继续。\n' > "$TMP/docs/본문.md"   # 본문.md는 있지만 형제 설정.md는 없음
printf '## 제5장\n按照细纲，作为AI我无法继续。\n' > "$TMP/游离/본문/제005장.md" # 본문/제N장은 있지만 책 구조는 없음
printf '他' > "$TMP/某书/본문/제001장_截断.md"                            # 실제 본문이 매우 짧음 → 저장 신호 발생

run() { CLAUDE_PROJECT_DIR="$TMP" CLAUDE_TOOL_INPUT="{\"tool_input\":{\"file_path\":\"$1\"}}" bash "$HOOK" 2>/dev/null; }

fails=0
expect_silent() {
  local out; out="$(run "$1")"
  if [ -n "$out" ]; then echo "FAIL: over-capture on non-正文 file: $1" >&2; echo "$out" | head -2 >&2; fails=$((fails+1)); fi
}
expect_fire() {
  local out; out="$(run "$1")"
  if [ -z "$out" ]; then echo "FAIL: backstop did not fire on real 正文: $1" >&2; fails=$((fails+1)); fi
}

# ① 본문 아닌 파일은 절대 탐지하지 않음(제작 용어/반복/거부 표현을 넣어 실제 검사되지 않음을 증명)
expect_silent "$TMP/某书/개요/상세개요_제001장.md"
expect_silent "$TMP/某书/개요/개요.md"
expect_silent "$TMP/某书/개요/권개요_제1권.md"
expect_silent "$TMP/某书/x.js"
expect_silent "$TMP/某书/설정.md"
expect_silent "$TMP/docs/본문.md"
expect_silent "$TMP/游离/본문/제005장.md"
# ② 실제 본문은 매우 짧아도 저장 신호가 반드시 발생해야 함
expect_fire "$TMP/某书/본문/제001장_截断.md"

# ③ 내용 검사망: 실제 본문의 강한 신호와 유형을 정확히 잡고 정상 본문(병렬+AI 인물 대화+서스펜스 마무리)은 조용함.
expect_fire_kw() {
  local out; out="$(run "$1")"
  if ! printf '%s' "$out" | grep -q "$2"; then
    echo "FAIL: 内容网未抓到「$2」: $1" >&2; printf '%s\n' "$out" | head -4 >&2; fails=$((fails+1))
  fi
}
# bash 문자열 반복으로 본문을 채운다. Windows 실행 환경의 Python<3.15 텍스트 stdout은 cp1252여서
# 중국어에 UnicodeEncodeError가 날 수 있다. printf로 스크립트의 UTF-8 바이트 리터럴을 직접 출력하는 것이 안정적이다.
PAD() { local s='江晨握紧拳头慢慢走向门口心里盘算着接下来的每一步棋。'; printf '%s' "$s$s$s$s$s$s$s$s"; }
# 정상: 긴 본문 + 병렬 + AI 인물 대화(따옴표 안 ‘AI로서…’ 제외) + 서스펜스 마무리 문장부호 → 완전히 조용함
{ printf '# 제10장 决战\n\n'; PAD; printf '\n要么生，要么死。\n要么战，要么逃。\n「作为AI管家，我陪你到最后。」\n他终于停下了脚步。\n'; } > "$TMP/某书/본문/제010장_决战.md"
expect_silent "$TMP/某书/본문/제010장_决战.md"
# 잘림: 끝 문장부호 없음
{ printf '# 제11장\n\n'; PAD; printf '\n他猛地冲过去一拳砸在'; } > "$TMP/某书/본문/제011장_截断.md"
expect_fire_kw "$TMP/某书/본문/제011장_截断.md" '잘림 의심'
# 생성 거부 표현 / AI 자기 지칭(대사가 아닌 서술 줄)
{ printf '# 제12장\n\n'; PAD; printf '\n作为AI我无法继续创作这部分内容。\n'; } > "$TMP/某书/본문/제012장_拒绝.md"
expect_fire_kw "$TMP/某书/본문/제012장_拒绝.md" '메타정보 유출'
# 제작 용어가 본문에 누출됨
{ printf '# 제13장\n\n'; PAD; printf '\n按照本章细纲的情节点，他该出场了。\n他出场了。\n'; } > "$TMP/某书/본문/제013장_工程词.md"
expect_fire_kw "$TMP/某书/본문/제013장_工程词.md" '작업 용어 유출'
# 인접한 전체 줄 반복(표시 문자 8개 이상)
{ printf '# 제14장\n\n'; PAD; printf '\n他握紧拳头一步步走过去缓缓逼近。\n他握紧拳头一步步走过去缓缓逼近。\n他停下了。\n'; } > "$TMP/某书/본문/제014장_复读.md"
expect_fire_kw "$TMP/某书/본문/제014장_复读.md" '인접 반복'

# 책별 .deslop-whitelist: 작가가 등록한 원문 리터럴은 유해 문형으로 되돌리지 않는다(OpenCode/ZCode/Antigravity/
# Codex와 같은 기준, 본문 소속 책 디렉터리에서 목록을 찾으며 책 간 상속하지 않음). 실제 bash 훅 → story_hook_cli.js 경로 실행.
expect_no_kw() {
  local out; out="$(run "$1")"
  if printf '%s' "$out" | grep -q "$2"; then
    echo "FAIL: 不该出现「$2」: $1" >&2; printf '%s\n' "$out" | head -4 >&2; fails=$((fails+1))
  fi
}
mkdir -p "$TMP/白名单书/본문" "$TMP/白名单书/개요" "$TMP/对照书/본문" "$TMP/对照书/개요"
printf '# 白名单\n声音不大，却带着一股狠劲\n' > "$TMP/白名单书/.deslop-whitelist"
for book in 白名单书 对照书; do
  { printf '# 제1장 开场\n\n'; PAD; printf '\n声音不大，却带着一股狠劲。\n他把门关上了。\n'; } > "$TMP/$book/본문/제001장_开场.md"
done
expect_fire_kw "$TMP/对照书/본문/제001장_开场.md" 'voice-contrast'
expect_no_kw "$TMP/白名单书/본문/제001장_开场.md" '문제 문장 패턴'
# 허용 목록은 등록한 조각만 가린다. 같은 장 다른 유해 문형은 계속 보고한다.
{ printf '# 제2장 回声\n\n'; PAD; printf '\n声音不大，却带着一股狠劲。\n没有伴奏，没有和声，没有提词器。\n他把门关上了。\n'; } > "$TMP/白名单书/본문/제002장_回声.md"
expect_fire_kw "$TMP/白名单书/본문/제002장_回声.md" 'negation-parade'
expect_no_kw "$TMP/白名单书/본문/제002장_回声.md" 'voice-contrast'
# 재검사 안내: 장편 분할 본문은 장편 흐름의 유일 진입점인 storyctl chapter check로 연결하고 단편 본문.md는
# 계속 check-ai-patterns.js로 연결한다.
expect_fire_kw "$TMP/对照书/본문/제001장_开场.md" 'storyctl.py chapter check --project <작품폴더> --chapter 1$'
expect_no_kw "$TMP/对照书/본문/제001장_开场.md" 'check-ai-patterns.js'
mkdir -p "$TMP/短篇书"
printf '# 설정\n' > "$TMP/短篇书/설정.md"
{ printf '# 본문\n\n'; PAD; printf '\n声音不大，却带着一股狠劲。\n他把门关上了。\n'; } > "$TMP/短篇书/본문.md"
expect_fire_kw "$TMP/短篇书/본문.md" 'check-ai-patterns.js --check <본문파일>$'
expect_no_kw "$TMP/短篇书/본문.md" 'storyctl'
# 강한 신호별 안내: 퇴화 유형은 문단 재작성, 유해 문형은 해당 위치 수정.
expect_fire_kw "$TMP/对照书/본문/제001장_开场.md" '잘림·거부 문구·작업 용어는 해당 문단 재작성, 문제 문장은 해당 위치 수정'

if [ "$fails" -ne 0 ]; then
  echo "Prose backstop hook tests FAILED ($fails)." >&2
  exit 1
fi
echo "Prose backstop hook regression tests passed."
