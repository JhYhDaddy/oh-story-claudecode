#!/bin/bash
# check-prose-after-write.sh — PostToolUse(Write|Edit|MultiEdit) 본문 보완 검사
# 본문 저장 후 가벼운 결정론적 검사망을 자동 실행해 발견 내용을 알린다. 모델과 무관한 보완 계층이다.
# 주 세션이 압축/낮은 모델 성능/주의 분산으로 결정론적 마무리를 놓쳐도 강한 신호는 반드시 잡는다.
#
# 누락 피해가 크고 퇴화한 모델이 스스로 찾기 어려운 강한 신호만 다룬다. 잘림, 생성 거부/AI 자기 지칭,
# 본문의 제작 용어 누출, 인접한 전체 줄 반복, 유해 문형(결정론적 AI 문형 특징), 저장 실패/잘림.
# 지나친 단문/긴 문단/대시 같은 advisory와 전체 반복/tier2 모호한 단어는 작업 흐름의 마무리 단계에서
# check-ai-patterns / check-degeneration으로 전체 검사한다. 이 훅은 두 탐지기를 배포하거나 의존하지 않으며
# 독립된 가벼운 검사망이다(유해 문형은 check-ai-patterns.js의 동명 규칙과 같은 규격).
#
# 범위: PostToolUse의 Write|Edit|MultiEdit에서만 실행한다. cat>/tee/cp/mv 등 Bash로
# 본문을 쓰는 경로는 이 훅을 우회한다(Claude/OpenCode Bash는 사전 보호만 있고 쓰기 후 보완은 없음).
# 이러한 경로는 Codex Stop의 턴 종료 git 변경 집합 검사가 보완한다. 알려진 범위 제한이며 결함이 아니다.
#
# 내용 검사는 OpenCode/ZCode와 같은 node 공유 코어 story_hook_core.js를 사용하고 bash는
# 이벤트 라우팅과 파일 유형 판정만 맡는다. node stdout은 기본 UTF-8이라 이전 내장 Python의 cp936 처리가 필요 없다.
#
# 비차단(exit 0, 안내만 하며 집필을 막지 않음). 발견이 없으면 컨텍스트를 오염시키지 않도록 완전히 조용하다.
# node를 사용할 수 없으면 조용히 허용한다(보완 검사가 흐름을 막으면 안 됨).
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

# 중국어 경로에서 bash glob/basename/case를 쓴다. 중국어 Windows의 GBK 로캘은 UTF-8 리터럴을
# 멀티바이트로 잘못 디코딩해 비교가 항상 거짓이 된다(이슈 #164). C 로캘 바이트 일치로 강제해야 안정적이다.
# node는 별도 프로세스에서 UTF-8로 처리하므로 LC_ALL=C의 영향을 받지 않는다.
export LC_ALL=C

HOOK_INPUT="${CLAUDE_TOOL_INPUT:-}"
if [ -z "$HOOK_INPUT" ] && [ ! -t 0 ]; then
  HOOK_INPUT="$(cat)"
fi
# 의도적으로 export하지 않는다. Write/Edit 입력은 장 전체 본문을 포함해 export하면 모든 자식 프로세스 envp에 들어간다.
# 입력이 커지면 execve가 E2BIG를 낸다(Linux 단일 환경 변수 128 KiB, macOS 전체 1 MiB 상한).
# dirname/basename/node가 모두 Argument list too long을 내어 보완 검사망이 조용히 중단된다. 필요한 node 호출에만
# 파이프로 stdin을 전달한다(story_hook_cli.js extract-target은 HOOK_INPUT이 없으면 stdin을 읽음).

# node 탐색: 공식 권장 네이티브 바이너리 Claude Code에는 node가 없을 수 있고 npm 설치에만 포함된다.
# 찾지 못하면 조용히 허용하고 보완 검사망을 중단한다. session-start.sh가 세션 시작에 한 번 안내한다.
node -e "" >/dev/null 2>&1 || exit 0
CLI="$(dirname "$0")/story_hook_cli.js"
[ -f "$CLI" ] || exit 0

# 대상 파일 경로 추출: 입력을 파이프로 node stdin에 전달하고 UTF-8 경로를 돌려받는다.
TARGET="$(printf '%s' "$HOOK_INPUT" | node "$CLI" extract-target 2>/dev/null || true)"
[ -z "$TARGET" ] && exit 0

ROOT=$(project_root)
# 드라이브 문자 절대 경로 정규화(guard-outline-before-prose.sh / plugin.ts와 일치, 이슈 #184).
case "$TARGET" in
  /*) ABS="$TARGET" ;;
  [A-Za-z]:[/\\]*) ABS="${TARGET//\\//}" ;;
  *)  ABS="$ROOT/$TARGET" ;;
esac

BASE="$(basename "$ABS")"
PARENT="$(basename "$(dirname "$ABS")")"

# 본문 파일만 보완 검사하며 코드/상세 개요/설정/전체 개요 등은 절대 건드리지 않는다.
#   - 단편: {书}/본문.md이며 같은 디렉터리에 설정.md가 있음(실제 단편 신호, docs/본문.md 등 제외)
#   - 장편: {书}/본문/제N장*.md(부모는 반드시 正文), {书}에 개요/추적/设定이 있음(실제 책 구조)
# case 패턴은 첫 문자에 고정한다. 상세개요_제N장.md(첫 글자 细), 권개요_제1권.md, check-ai-patterns.js,
# 설정.md, 개요.md 등은 `본문.md`/`제*장*.md`와 일치하지 않아 탐지되지 않는다.
IS_PROSE=false
case "$BASE" in
  본문.md)
    [ -f "$(dirname "$ABS")/설정.md" ] && IS_PROSE=true
    ;;
  제*장*.md)
    if [ "$PARENT" = "본문" ]; then
      BOOK="$(dirname "$(dirname "$ABS")")"
      if [ -d "$BOOK/개요" ] || [ -d "$BOOK/추적" ] || [ -d "$BOOK/설정" ] || [ -f "$BOOK/설정.md" ]; then
        IS_PROSE=true
      fi
    fi
    ;;
esac
[ "$IS_PROSE" = true ] || exit 0
[ -f "$ABS" ] || exit 0

# 보고서는 리터럴 `\n` 대신 실제 줄바꿈 NL로 합친다. 마지막 출력은 printf %s여야 한다(끝 주석 참조).
NL=$'\n'
OUT=""

# 저장 검사: 본문이 200바이트 미만이면 미완성 또는 quota/timeout 중단에 따른 저장 실패일 가능성이 크다.
# LC_ALL=C에서는 중국어 코드 포인트를 셀 수 없어 글자 수 대신 wc -c 바이트를 쓴다. 거의 비었는지 판단하기에 충분하다.
BYTES=$(wc -c < "$ABS" 2>/dev/null | tr -d ' ' || echo 0)
case "$BYTES" in ''|*[!0-9]*) BYTES=0 ;; esac
if [ "$BYTES" -lt 200 ]; then
  OUT+="【파일 저장】본문이 ${BYTES}바이트뿐입니다. 미완성이나 저장 실패(용량 한도·시간 초과)가 의심되므로 확인하고 보완하세요.${NL}"
fi

# node 공유 코어가 잘림/거부 표현/AI 자기 지칭/tier1 제작 용어/인접 반복/유해 문형을 탐지한다.
# 글자 수는 storyctl 공개 명령만 측정한다. 어댑터에 복제하지 않고 Node 기능 저하에도 영향받지 않는다.
NET_MSG="$(node "$CLI" prose-net "$ABS" 2>/dev/null || true)"
[ -n "$NET_MSG" ] && OUT+="【품질 저하/작업 용어/문제 문장】(잘림·거부 문구·작업 용어는 해당 문단 재작성, 문제 문장은 해당 위치 수정. 다음 장으로 미루지 말고 즉시 처리)${NL}${NET_MSG}${NL}"

[ -z "$OUT" ] && exit 0

# 반드시 %s를 쓰고 %b는 금지한다. ${OUT}에는 작가 원문 일부(잘림/반복/제작 용어 발췌)가 들어 있다. %b는 본문의
# `\n`, `\b`, `\t`를 확장해 파일에 없는 내용으로 바꾸며 `\c`(Windows 경로 C:\code에도 포함)는
# printf 전체를 즉시 끝내 이후 강한 신호를 조용히 버린다(종료 0, stderr 없음).
# 훅 자체 구분 줄바꿈은 위 ${NL} 실제 줄바꿈이 담당하며 %b 확장에 의존하지 않는다.
printf '%s\n' "=== 본문 보완 검사(${BASE}）===" "주 세션이 마무리 검사를 놓치지 않도록 모델과 무관한 규칙으로 자동 재검사합니다. 유형별로 수정한 뒤 문제가 없을 때까지 다시 검사하세요:"
printf '%s' "$OUT"
exit 0
