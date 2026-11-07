#!/bin/bash
# detect-story-gaps.sh — 집필 프로젝트의 누락 항목 5개 탐지
# 설계 원칙: 누락이 없으면 아무것도 출력하지 않아 컨텍스트 오염을 막는다.
set -euo pipefail

# 공통 함수 라이브러리 로드(project_root + discover_all_books)
source "$(dirname "$0")/lib/common.sh"

# 이후 awk로 중국어 복선 표를 파싱하고 find/grep으로 중국어 경로를 찾는다. 중국어 Windows에서 GBK 로캘을 내보내면
# gawk가 UTF-8 상태값의 GBK 디코딩에 실패해 trim과 == 비교가 어긋나 모든 행을 오탐한다. C 로캘로 강제해
# UTF-8 리터럴과 내용 바이트를 비교해야 안정적이다(이슈 #164 유형). 끝의 연속성 검사는
# node 공유 코어(story_hook_cli.js)를 사용하며 node는 UTF-8로 파일을 읽고 stdout을 쓰므로
# LC_ALL=C의 영향을 받지 않아 위에서 export해도 된다.
export LC_ALL=C

ROOT=$(project_root)
# 보고서는 리터럴 `\n` 대신 실제 NL로 합친다. 출력은 반드시 printf %s를 쓴다(끝 주석 참조).
NL=$'\n'
OUTPUT=""
HAS_WARNINGS=false

# 1. 새 프로젝트 탐지: 책 제목 디렉터리 없음(장편과 단편 모두 지원)
# bash 3.2 호환: 연관 배열 없이 discover_all_books 안에서 순서대로 중복을 제거한다.
declare -a BOOK_DIRS=()
while IFS= read -r dir; do
  [ -n "$dir" ] && BOOK_DIRS+=("$dir")
done < <(discover_all_books)

if [ "${#BOOK_DIRS[@]}" -eq 0 ]; then
  # 디렉터리 구조가 전혀 없는 완전 새 프로젝트는 조용히 종료한다.
  exit 0
fi

for BOOK_DIR in "${BOOK_DIRS[@]}"; do
  BOOK_NAME=$(basename "$BOOK_DIR")
  BOOK_OUTPUT=""

  # 2. 본문은 많지만 설정은 적음
  CHAPTER_COUNT=0
  SETTING_COUNT=0
  # `|| true`와 숫자 기본값은 필수다. 하위 디렉터리를 읽지 못하면 find가 종료 1, pipefail이 파이프 전체에 적용되어
  # set -e가 여기서 종료한다. OUTPUT은 끝에서만 출력하므로 모든 경고와 stderr를 잃는다.
  if [ -d "$BOOK_DIR/본문" ]; then
    CHAPTER_COUNT=$(find "$BOOK_DIR/본문" -name "*.md" 2>/dev/null | wc -l | tr -d ' ' || true)
    case "$CHAPTER_COUNT" in ''|*[!0-9]*) CHAPTER_COUNT=0 ;; esac
  elif [ -f "$BOOK_DIR/본문.md" ]; then
    CHAPTER_COUNT=1
  fi
  if [ -d "$BOOK_DIR/설정" ]; then
    SETTING_COUNT=$(find "$BOOK_DIR/설정" -name "*.md" 2>/dev/null | wc -l | tr -d ' ' || true)
    case "$SETTING_COUNT" in ''|*[!0-9]*) SETTING_COUNT=0 ;; esac
  fi
  if [ "$CHAPTER_COUNT" -gt 10 ] && [ "$SETTING_COUNT" -lt 3 ]; then
    BOOK_OUTPUT+="[WARN] ${BOOK_NAME}：正文 ${CHAPTER_COUNT} 章，但设定文件只有 ${SETTING_COUNT} 个，建议补充设定。${NL}"
  fi

  # 4. 기한이 지났거나 비정상인 복선 단서
  if [ -f "$BOOK_DIR/추적/복선.md" ]; then
    # 표 데이터 행의 상태 열만 검사한다. 현재 프로토콜의 정상 상태(설치됨/회수됨/포기)는 경고하지 않아
    # 장편 프로젝트가 매 SessionStart마다 복선 전체 감사를 실행하지 않게 한다.
    # 동작 회귀: scripts/check-hook-regex-sync.sh(로캘 견고성은 export LC_ALL=C가 보장)
    ABNORMAL_FORESHADOW=$(awk -F'|' '
      # 전각 공백 U+3000 포함: LC_ALL=C의 [[:space:]]는 ASCII만 인식하므로 셀의 전각 공백 패딩이
      # status에 남아 비정상으로 오탐된다. 선택식으로 전각 공백을 보완한다(문자 집합에 넣으면 로캘 간 버그 발생).
      function trim(s) { gsub(/^([[:space:]]|　)+|([[:space:]]|　)+$/, "", s); return s }
      # 구분 줄 문자 집합에는 `:`가 필요하다. Markdown 정렬 |:---|:---:|---:|도 구분 줄이며 누락하면
      # 데이터 줄로 오인해 ":---"를 상태값으로 보고 매 SessionStart에 복선 이상을 하나씩 오탐한다.
      # `:`는 ASCII라 문자 집합에 넣을 수 있다(전각 문자만 금지, 위 주석 참조).
      /^\|/ && $0 !~ /^\|[-:[:space:]|]+$/ {
        status=trim($6)
        if (status == "" || status == "状态" || status ~ /^状态\{/) next
        if (status == "已过期" || (status != "已埋" && status != "已回收" && status != "放弃")) print
      }
    ' "$BOOK_DIR/추적/복선.md" 2>/dev/null || true)
    if [ -n "$ABNORMAL_FORESHADOW" ]; then
      BOOK_OUTPUT+="[WARN] ${BOOK_NAME}：복선.md 中检测到过期或异常的伏笔条目，建议跑 /story-review lean 或做一次伏笔审计。${NL}"
    fi
  fi

  # 5. 개요 누락(프로젝트 유형별 판정)
  if [ -d "$BOOK_DIR/본문" ] || [ -f "$BOOK_DIR/본문.md" ]; then
    # 장편: 추적/이 있으면 장편으로 보고 개요/ 디렉터리를 요구한다.
    if [ -d "$BOOK_DIR/추적" ] && [ ! -d "$BOOK_DIR/개요" ]; then
      BOOK_OUTPUT+="[WARN] ${BOOK_NAME}：已有 본문/ 但缺少 개요/，建议先搭大纲。${NL}"
    # 단편: 추적/이 없으면 단편으로 보고 구간개요.md 파일을 요구한다.
    elif [ ! -d "$BOOK_DIR/추적" ] && [ ! -f "$BOOK_DIR/구간개요.md" ]; then
      BOOK_OUTPUT+="[WARN] ${BOOK_NAME}：已有正文但缺少 구간개요.md，建议先搭大纲。${NL}"
    fi
  fi

  # 문제가 있을 때만 해당 책 정보를 출력한다.
  if [ -n "$BOOK_OUTPUT" ]; then
    OUTPUT+="检查：$BOOK_NAME${NL}$BOOK_OUTPUT"
    HAS_WARNINGS=true
  fi
done

# 3. 전체 작품 분석 미완료 탐지(책이 아닌 프로젝트 수준)
GLOBAL_PROGRESS_OUTPUT=""
if [ -d "$ROOT/작품분석실" ]; then
  # session-start처럼 최종 상태로 필터링해 완료한 책은 보고하지 않는다(파일 개수만 세면 영구 오탐).
  while IFS= read -r progress_file; do
    [ -n "$progress_file" ] || continue
    GLOBAL_PROGRESS_OUTPUT+="[WARN] 拆文未完成：${progress_file#$ROOT/}，运行 /story-long-analyze 继续。${NL}"
  done < <(discover_incomplete_analyses "$ROOT")
fi
if [ -n "$GLOBAL_PROGRESS_OUTPUT" ]; then
  OUTPUT+="$GLOBAL_PROGRESS_OUTPUT"
  HAS_WARNINGS=true
fi

# 6. 배치 간 연속성 보완(추적 지연 + 장 제목 중복): node 공유 코어 continuityFindings를 사용해
# Codex/OpenCode/ZCode와 구현을 공유한다. 세션 시작에 본문 작성 후 문맥.md가 뒤처졌거나
# 두 장의 제목이 겹쳤는지 알린다. 메시지는 공유 코어와 같고 여러 책/동률 중복 정렬은 JS 의미를 따른다.
# 이는 문서화되어 있으며 안내 순서만 바꾸고 보고 여부는 바꾸지 않는다. 위 누락 탐지처럼 저장소 전체를 검사해
# 비활성 책도 알린다(책을 바꾸기 전에 단절을 알기 위한 의도). .active-book으로 좁히지 않는다. 지연은 mtime 비교와
# 같은 초 오탐 방지용 +1초 허용을 쓰는 휴리스틱 안내다. git checkout/복사 -p로 mtime이 바뀌면 오차가 있을 수 있으나
# 안내만 하고 차단하지 않는다. node가 없으면 조용히 건너뛴다(네이티브 설치에는 없을 수 있으며 session-start.sh가 시작 시 한 번
# 안내한다. core.js는 bash 훅 디렉터리의 story_hook_cli.js가 로드한다).
if node -e "" >/dev/null 2>&1; then
  CONT_CLI="$(dirname "$0")/story_hook_cli.js"
  if [ -f "$CONT_CLI" ]; then
    CONTINUITY_OUTPUT="$(node "$CONT_CLI" continuity "$ROOT" 2>/dev/null || true)"
    if [ -n "$CONTINUITY_OUTPUT" ]; then
      OUTPUT+="$CONTINUITY_OUTPUT"
      HAS_WARNINGS=true
    fi
  fi
fi

# 경고가 있을 때만 출력한다.
# 반드시 %s를 쓴다. $OUTPUT에는 책 디렉터리명과 파일에서 읽은 장 제목을 포함한 node 연속성 출력이 들어 있다.
# %b는 `\n`, `\b`를 확장하고 `\c`는 printf를 즉시 종료해 뒤의 [WARN]을 모두 삼킨다.
# 구분 줄바꿈은 위에서 합칠 때 사용한 ${NL} 실제 줄바꿈이 담당한다.
if [ "$HAS_WARNINGS" = true ]; then
  printf '%s\n' "=== 写作缺口检测 ===" "$OUTPUT"
fi
