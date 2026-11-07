#!/bin/bash
# guard-outline-before-prose.sh — PreToolUse(Bash|Write|Edit|MultiEdit) 절차 보호
# 본문 작성 전에 해당 전체/상세 개요가 있어야 하며 없으면 차단한다(exit 2, BLOCKING).
#
# 차단 유형 세 가지:
#   - 장편 본문/제N장_*.md 최초 생성 시 상세 개요 누락/비어 있음: 같은 책 개요/상세개요_제N장.md가 있고 내용이 있어야 함
#     (#과 공백 제외 최소 30자, 상세 개요 필드는 검사하지 않아 이전 책 개요도 허용)
#   - 단편 본문.md 최초 생성 시 개요 누락: 같은 디렉터리 구간개요.md가 있어야 함
#   - 장편 추적 점검 불성립: state 누락/스키마 불일치/이어쓰기 상태 카드 리비전 불일치/새 장 최초 생성 시
#     이전 장 트랜잭션 미커밋(공유 코어 판정, opencode/zcode/codex와 동일, 아래 해당 부분 주석 참조)
# 상세/전체 개요는 최초 생성만 검사하고 추적은 최초 생성과 이어쓰기 모두 검사한다(JS 코어 proseBlockReason과 같은 순서).
# 본문 외 대상과 경로를 파싱하지 못한 경우는 모두 조용히 허용한다.
# 설계 원칙: 차단 누락보다 오차단을 피한다. 불확실하면 exit 0.
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

# 모든 과정에 바이트 안정 로캘을 사용한다. 중국어 경로에서 bash glob(중간 디렉터리가 중국어 책 제목이면
# GBK에서 상세개요_제*장*.md가 NOMATCH), sed 장 번호 추출, case 일치를 사용한다. 중국어 Windows의
# GBK/GB2312 로캘에서는 UTF-8을 멀티바이트로 잘못 디코딩해 실패한다. C 로캘 바이트 일치(UTF-8
# 리터럴과 UTF-8 바이트 비교)로 강제해야 안정적이다(이슈 #164). 경로 추출은 node 공유 코어가 UTF-8로
# 처리해 bash 로캘과 무관하다. 차단 판정은 아래 bash에서 하므로 영향받지 않는다.
export LC_ALL=C

HOOK_INPUT="${CLAUDE_TOOL_INPUT:-}"
if [ -z "$HOOK_INPUT" ] && [ ! -t 0 ]; then
  HOOK_INPUT="$(cat)"
fi
# 의도적으로 export하지 않는다. Write/Edit/MultiEdit 입력에는 장 전체 본문(MultiEdit는 old_string+new_string도)이 있어
# export하면 모든 자식 envp에 들어가 큰 입력에서 execve E2BIG가 난다(Linux 단일 환경 변수 상한
# 128 KiB, macOS 전체 1 MiB). dirname/sed/node가 모두 Argument list too long을 내면 보호가
# exit 2 전에 죽어 비차단 오류로 쓰기를 허용하므로 BLOCKING 계약에 반한다. 입력이 필요한 node 호출에만
# 파이프로 stdin을 전달한다(story_hook_cli.js extract-target은 HOOK_INPUT이 없으면 stdin을 읽음).
# 아래 extract_target_bash는 내장 printf를 쓰므로 export가 필요 없다.

# 직접 쓰기 도구의 대상 경로 추출은 다른 환경과 같은 node 공유 코어를 우선한다. node가 없거나 추출에 실패하면
# 순수 bash로 대체한다. 차단 보호이므로 node 문제 때문에 허용하면 안 된다. 공식 권장은 네이티브 바이너리
# Claude Code이며 npm 설치에만 Node가 있어 네이티브에는 없을 수 있다. 이전 node는 node: 접두어를 모르거나
# 배포 코어 손상 시 탐색은 통과해도 추출 오류가 난다. 경로를 추출할 수 있으면 정상 차단하고 두 경로 모두 실패해야
# 허용한다(오차단 방지를 우선).
CLI="$(dirname "$0")/story_hook_cli.js"

# 순수 bash JSON 대체 추출: dig 우선순위로 첫 file_path/path/filePath 문자열 값을 얻는다. node 앱인 Claude의
# 훅 입력은 JSON.stringify를 써 비ASCII 경로가 원본 UTF-8(\uXXXX 변환 없음)이며 Windows 드라이브
# 경로는 역슬래시 이스케이프다. 둘 다 bash에서 복원할 수 있다(아래 드라이브 분기에서 역슬래시를 /로 정규화). node가 없거나
# 있어도 추출 실패 시 사용한다.
extract_target_bash() {
  local key val
  for key in file_path path filePath; do
    val="$(printf '%s' "$HOOK_INPUT" \
      | grep -oE "\"$key\"[[:space:]]*:[[:space:]]*\"([^\"\\\\]|\\\\.)*\"" \
      | head -n1 \
      | sed -E "s/^\"$key\"[[:space:]]*:[[:space:]]*\"//; s/\"\$//")"
    if [ -n "$val" ]; then
      val="${val//\\\"/\"}"   # \" -> "
      val="${val//\\\\/\\}"   # \\ -> \
      printf '%s' "$val"
      return 0
    fi
  done
  return 1
}

# 실질적으로 빈 상세 개요: 파일 앞 BOM과 각 줄의 Markdown 제목 마커(공백/탭 다음 #)를 제거하고 제목 문자는
# 세어 비공백 코드 포인트가 30개 미만이면 비었다고 본다(공백 = ASCII 공백 + 전각 공백). JS core outlineIsEmpty / Codex Python
# _outline_is_empty와 같은 기준(test-prose-net-parity.sh D부로 고정). 순수 bash 바이트 연산으로 LC_ALL=C에서
# UTF-8 연속 바이트(0x80~0xBF)를 제거한 바이트 수가 코드 포인트 수다. UTF-8 로캘이나 node에 의존하지 않는다.
# 일반 파일 아님/읽기 불가/유효 UTF-8 아님(GBK 등 이전 인코딩)은 비어 있지 않은 것으로 허용해 오차단을 피한다.
OUTLINE_MIN_CHARS=30
# 한 줄의 유효 UTF-8 바이트 시퀀스(Unicode 표 3-7, 과도하게 긴 인코딩과 서로게이트 거부)를 LC_ALL=C에서 바이트별 비교한다.
UTF8_LINE=$'^([^\x80-\xff]|[\xc2-\xdf][\x80-\xbf]|\xe0[\xa0-\xbf][\x80-\xbf]|[\xe1-\xec\xee\xef][\x80-\xbf][\x80-\xbf]|\xed[\x80-\x9f][\x80-\xbf]|\xf0[\x90-\xbf][\x80-\xbf][\x80-\xbf]|[\xf1-\xf3][\x80-\xbf][\x80-\xbf][\x80-\xbf]|\xf4[\x80-\x8f][\x80-\xbf][\x80-\xbf])*$'
outline_is_empty() {
  local f="$1" n bom fws tab
  [ -f "$f" ] && [ -r "$f" ] || return 1
  if grep -qvaE "$UTF8_LINE" "$f"; then return 1; fi
  bom="$(printf '\357\273\277')"
  fws="$(printf '\343\200\200')"
  tab="$(printf '\t')"
  n="$( { sed -e "1s/^${bom}//" -e "s/^[ ${tab}]*#*//" "$f" || true; } \
    | sed "s/${fws}//g" | tr -d ' \t\r\n\f\v' | tr -d '\200-\277' | wc -c | tr -d ' ')"
  case "$n" in ''|*[!0-9]*) return 1 ;; esac
  [ "$n" -lt "$OUTLINE_MIN_CHARS" ]
}

TARGET=""
if node -e "" >/dev/null 2>&1 && [ -f "$CLI" ]; then
  TARGET="$(printf '%s' "$HOOK_INPUT" | node "$CLI" extract-target 2>/dev/null || true)"
fi
# node가 있어도 추출이 비면(이전 node의 node: 미지원/손상 코어의 탐색 통과 후 오류) 순수 bash로 대체한다.
# Bash 입력에는 file_path가 없다. 직접 대상 추출 실패 시 공유 코어가 리디렉션/tee/touch/cp/mv의 쓰기 대상만 찾게 하여
# grep/cat 같은 읽기 명령의 본문 경로 언급을 쓰기로 오인하지 않는다. 이 경로는 node에 의존하므로 없으면 Bash 명령은
# 오차단 방지 원칙으로 허용하고 Write/Edit/MultiEdit는 위 순수 bash 대체 경로를 따른다.
[ -z "$TARGET" ] && TARGET="$(extract_target_bash 2>/dev/null || true)"

ROOT=$(project_root)
if [ -z "$TARGET" ]; then
  if node -e "" >/dev/null 2>&1 && [ -f "$CLI" ]; then
    set +e
    COMMAND_BLOCK="$(printf '%s' "$HOOK_INPUT" | node "$CLI" prose-command-guard "$ROOT" 2>&1)"
    COMMAND_STATUS=$?
    set -e
    if [ "$COMMAND_STATUS" -ne 0 ]; then
      printf '%s\n' "⚠ Bash 본문 쓰기 보호 검사에서 해석에 실패했습니다. 이번에는 fail-open으로 허용합니다. Write/Edit를 사용하거나 훅을 복구하세요: ${COMMAND_BLOCK:-未知错误}" >&2
      exit 0
    fi
    if [ -n "$COMMAND_BLOCK" ]; then
      printf '%s\n' "$COMMAND_BLOCK" >&2
      exit 2
    fi
  elif printf '%s' "$HOOK_INPUT" | grep -q '본문'; then
    printf '%s\n' "⚠ 사용 가능한 Node/story_hook_cli.js가 없어 Bash의 본문 쓰기 여부를 판단할 수 없습니다. 이번에는 fail-open으로 허용합니다. 개요 보호 검사를 사용하려면 Write/Edit로 작성하세요." >&2
  fi
  exit 0
fi

# 절대 경로는 그대로 사용하고 상대 경로만 프로젝트 루트와 합친다.
# Windows + Git Bash에서 Claude Code는 드라이브 문자 절대 경로(F:/work/... 또는 F:\work\...)를 전달할 수 있다.
# /*만 인식하면 상대 경로로 보고 $ROOT/F:/work/...로 합쳐 잘못된 개요/를 찾고 상세 개요 누락을 오탐한다(이슈 #184).
# [A-Za-z]:[/\\]*로 드라이브 절대 경로를 찾고 역슬래시를 /로 통일한다(plugin.ts의 isAbsolute + 역슬래시 정규화와 일치).
case "$TARGET" in
  /*) ABS="$TARGET" ;;
  [A-Za-z]:[/\\]*) ABS="${TARGET//\\//}" ;;
  *)  ABS="$ROOT/$TARGET" ;;
esac

BASE="$(basename "$ABS")"
PARENT="$(basename "$(dirname "$ABS")")"

case "$BASE" in
  본문.md)
    # 단편 단일 본문 파일이 이미 있으면 허용한다(이어쓰기/수정).
    [ -f "$ABS" ] && exit 0
    BOOK_DIR="$(dirname "$ABS")"
    # story-import 이전: 작품분석실/{书名}/ 분석 원본이 있으면 본문을 절 개요보다 먼저 옮기는 것이 정상이므로 허용한다(절 개요는 분석으로 역추론).
    [ -d "$ROOT/작품분석실/$(basename "$BOOK_DIR")" ] && exit 0
    # 실제 단편 프로젝트만 차단한다(설정.md 신호, story-short-write/import 모두 이를 먼저 생성).
    # docs/본문.md 같은 작품 외 파일의 오차단을 피한다.
    [ -f "$BOOK_DIR/설정.md" ] || exit 0
    if [ ! -f "$BOOK_DIR/구간개요.md" ]; then
      printf '%s\n' "⛔ 본문 쓰기 차단: ${TARGET}와 같은 폴더에 구간개요.md가 없습니다. " >&2
      printf '%s\n' "   story-short-write에 따라 구간개요.md를 완성한 뒤 본문을 쓰세요(개요 생략 불가)." >&2
      printf '%s\n' "   초안을 쓰려면 먼저 구간개요.md를 만드세요." >&2
      exit 2
    fi
    ;;
  *)
    # 장편 분할 본문: 부모 디렉터리가 正文이고 파일명은 第N章... 형식이어야 한다.
    [ "$PARENT" = "본문" ] || exit 0
    case "$BASE" in
      제*장*.md) ;;
      *) exit 0 ;;
    esac
    # 장 번호(앞자리 0 제거)
    NUM="$(printf '%s' "$BASE" | sed -n 's/^제0*\([0-9][0-9]*\)장.*/\1/p')"
    [ -z "$NUM" ] && exit 0
    BOOK_DIR="$(dirname "$(dirname "$ABS")")"
    # story-import 이전: 작품분석실/{书名}/ 분석 원본이 있으면 허용한다(상세 개요는 장 요약에서 역추론해 본문보다 늦게 이전).
    # 추적/_tracking-state.json이 생기면 현재 추적 프로토콜로 진입한다. 작품분석실/ 분석 자산을 남겨 두었다고
    # 보호를 영구 우회하지 않는다(story_hook_core.js와 같은 판정).
    if [ -d "$ROOT/작품분석실/$(basename "$BOOK_DIR")" ] && [ ! -f "$BOOK_DIR/추적/_tracking-state.json" ]; then
      exit 0
    fi
    # 기존 본문(이어쓰기/수정/재작업)은 상세 개요 검사를 건너뛰지만 추적 점검은 적용한다. JS 코어
    # proseBlockReason과 같이 개요는 최초 생성만, 추적은 두 경우 모두 검사한다.
    EXISTS=""
    [ -f "$ABS" ] && EXISTS=1
    if [ -z "$EXISTS" ]; then
      OUTLINE_DIR="$BOOK_DIR/개요"
      FOUND=""
      FILLED=""
      if [ -d "$OUTLINE_DIR" ]; then
        # 앞자리 0과 제목 접미어 차이를 허용해 정수 장 번호로 개요/상세개요_제*장*.md를 찾는다. 같은 장에 여러 상세 개요가 있으면
        # 하나라도 내용이 있으면 허용한다(JS 코어와 동일). FOUND는 빈 개요 안내에 쓸 사전순 첫 파일이다.
        for f in "$OUTLINE_DIR"/상세개요_제*장*.md; do
          [ -e "$f" ] || continue
          fnum="$(basename "$f" | sed -n 's/^상세개요_제0*\([0-9][0-9]*\)장.*/\1/p')"
          [ "$fnum" = "$NUM" ] || continue
          [ -n "$FOUND" ] || FOUND="$f"
          if ! outline_is_empty "$f"; then FILLED=1; break; fi
        done
      fi
      if [ -n "$FOUND" ] && [ -z "$FILLED" ]; then
        # ROOT는 pwd -P 물리 경로이고 대상은 논리 경로일 수 있어(macOS /var → /private/var) 두 접두어 모두 제거한다.
        OUTLINE_REL="${FOUND#"$ROOT"/}"
        [ -n "${CLAUDE_PROJECT_DIR:-}" ] && OUTLINE_REL="${OUTLINE_REL#"${CLAUDE_PROJECT_DIR%/}"/}"
        printf '%s\n' "⛔ 본문 쓰기 차단: 제${NUM}장의 상세 개요(${OUTLINE_REL})가 비어 있습니다(# 기호와 공백을 제외하고 ${OUTLINE_MIN_CHARS}자 미만). story-long-write의 장별 절차에 따라 상세 개요를 완성하세요(이번 장의 사건과 주인공의 선택). 그 뒤 본문을 쓰세요." >&2
        exit 2
      fi
      if [ -z "$FOUND" ]; then
        printf '%s\n' "⛔ 본문 쓰기 차단: 제 ${NUM} 장에 상세 개요가 없습니다(${OUTLINE_DIR#$ROOT/}/상세개요_제$(printf '%03d' "$NUM")장.md）。" >&2
        printf '%s\n' "   story-long-write의 장별 절차로 상세 개요를 보완한 뒤 본문을 쓰세요(상세 개요 생략 불가)." >&2
        printf '%s\n' "   초안을 쓰려면 먼저 해당 상세 개요 파일을 만드세요." >&2
        exit 2
      fi
    fi
    # 추적 점검: state 없음 / schema가 4 아님 / 이어쓰기 상태 카드 리비전 불일치 / 새 장 최초 생성 시
    # 이전 장 트랜잭션 미커밋을 모두 차단한다. 공유 코어(story_hook_cli.js tracking-checkpoint)로 판정하며
    # opencode/zcode/codex와 같은 구현이다. 이슈 #305 전에는 JS 코어와 Codex Python에만 있어
    # Claude만 빠진 채 추적 없는 본문 여러 장을 조용히 작성할 수 있었다.
    # JSON 파싱이 필요해 node에 의존한다. node/코어 없음 또는 하위 명령 미인식이면 오차단 방지 원칙으로 허용한다.
    # 이 파일의 다른 기능 저하와 동일하며 SessionStart 연속성 안내와 배치 끝 check가 보완한다.
    if node -e "" >/dev/null 2>&1 && [ -f "$CLI" ]; then
      # 새 장 최초 생성만 이전 장 커밋 순서를 검사한다. 기존 본문은 `-`를 전달해 state 자체만 검사한다.
      EXPECT="-"
      [ -z "$EXISTS" ] && EXPECT=$((NUM - 1))
      CHECKPOINT="$(node "$CLI" tracking-checkpoint "$ROOT" "$BOOK_DIR" "$EXPECT" 2>/dev/null || true)"
      if [ -n "$CHECKPOINT" ]; then
        printf '%s\n' "$CHECKPOINT" >&2
        exit 2
      fi
    fi
    # 기존 본문은 여기까지다. 미해결 검사 조건은 새 장 최초 생성에만 적용한다.
    [ -n "$EXISTS" ] && exit 0
    # 미처리 문제 관문(무상태): N장을 최초 생성하기 전에 앞 장에 미수정 문제 문장 패턴이 있고 ‘去味:跳过’가 없으면 먼저 수정한다.
    # 유해 문형 검사는 공유 코어 prose-toxic 하위 명령을 사용한다(쓰기 후 검사와 같은 규칙). node/코어 없음 또는 검사 실패는
    # 오차단 방지 원칙으로 허용한다. 쓰기 후 검사와 SKILL의 같은 턴 필수 규칙이 보완한다. 이전 장 파일에서 즉시 계산하며 상태를 저장하지 않는다.
    PREV=$((NUM - 1))
    if [ "$PREV" -ge 1 ] && node -e "" >/dev/null 2>&1 && [ -f "$CLI" ]; then
      PROSE_DIR="$(dirname "$ABS")"
      PREV_FILE=""
      # glob은 이미 사전순이지만 같은 장의 원고 백업(workflow-revision의 원고 백업 산출물)도
      # 일치하므로 _원본_를 명시적으로 건너뛰어 JS 코어/Codex Python과 같은 이전 장을 선택한다.
      for f in "$PROSE_DIR"/제*장*.md; do
        [ -e "$f" ] || continue
        case "$(basename "$f")" in *_원본_*) continue ;; esac
        pnum="$(basename "$f" | sed -n 's/^제0*\([0-9][0-9]*\)장.*/\1/p')"
        if [ "$pnum" = "$PREV" ]; then PREV_FILE="$f"; break; fi
      done
      if [ -n "$PREV_FILE" ] && ! head -n 6 "$PREV_FILE" | grep -qE '<!--[[:blank:]]*去味[[:blank:]]*(：|:)[[:blank:]]*跳过[[:blank:]]*-->'; then
        TOXIC="$(node "$CLI" prose-toxic "$PREV_FILE" 2>/dev/null || true)"
        if [ -n "$TOXIC" ]; then
          printf '%s\n' "⛔ 본문 쓰기 차단: 앞 장($(basename "$PREV_FILE")）에 미수정 문제 문장이 있습니다. 모두 수정한 뒤 다음 장을 쓰세요: 제${NUM}장. 사용자가 명시적으로 면제하면 앞 장 제목 아래에 <!-- 去味:跳过 -->를 추가하고 다시 시도하세요." >&2
          # 처음 8개만 나열한다. `printf … | head -n 8`은 금지한다. 항목이 많으면 head가 먼저 종료해 printf가 SIGPIPE를 받고,
          # pipefail이면 파이프 전체가 141을 반환해 set -e가 즉시 종료한다. 아래 exit 2에 도달하지 못하고 차단이
          # 비차단 오류로 바뀌어 쓰기를 허용한다. here-string으로 head에 직접 전달해 파이프와 SIGPIPE를 없애고
          # || true도 덧붙여 반드시 exit 2에 도달하게 한다.
          head -n 8 <<< "$TOXIC" >&2 || true
          exit 2
        fi
      fi
    fi
    ;;
esac

exit 0
