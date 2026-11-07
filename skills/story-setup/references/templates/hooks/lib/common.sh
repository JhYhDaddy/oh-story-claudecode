#!/bin/bash
# common.sh — 각 훅이 source하는 공통 함수 라이브러리
# source 시 호출자의 셸 옵션을 덮지 않도록 set -euo pipefail을 넣지 않는다.

# project_root — 프로젝트 루트를 안정적으로 해석한다.
# Claude Code가 주입한 CLAUDE_PROJECT_DIR, git 루트, 현재 디렉터리 순으로 사용한다.
# 절대 경로를 출력해 중첩 cwd에서 훅이 잘못 읽거나 쓰지 않게 한다.
project_root() {
  if [ -n "${CLAUDE_PROJECT_DIR:-}" ] && [ -d "$CLAUDE_PROJECT_DIR" ]; then
    (cd "$CLAUDE_PROJECT_DIR" 2>/dev/null && pwd -P) && return
  fi
  local git_root
  git_root=$(git rev-parse --show-toplevel 2>/dev/null || true)
  if [ -n "$git_root" ] && [ -d "$git_root" ]; then
    (cd "$git_root" 2>/dev/null && pwd -P) && return
  fi
  pwd -P
}

# resolve_project_path <path> — 상대 경로를 프로젝트 루트 기준 절대 경로로 해석한다.
resolve_project_path() {
  local path="$1"
  case "$path" in
    /*) printf '%s\n' "$path" ;;
    *) printf '%s/%s\n' "$(project_root)" "$path" ;;
  esac
}

# discover_active_book — 활성 책 한 권 조회
# root/.active-book 우선, 이후 첫 추적/(장편) 또는 본문/ / 본문.md(단편)를 find로 찾는다.
# 용도: session-start / session-end / pre-compact / post-compact. 한 세션은 현재 활성 책만 다룬다.
discover_active_book() {
  local root
  root=$(project_root)

  if [ -f "$root/.active-book" ]; then
    local active
    # LC_ALL=C: 제목은 중국어 UTF-8이다. 중국어 Windows에서 GBK 로캘을 내보내면 trim의
    # s/^[[:space:]]*//가 sed에 전체 줄 GBK 디코딩을 강제한다. 짧은 제목(예: 让你管账号, 修仙传)의
    # UTF-8 바이트가 잘못된 GBK 시퀀스여서 BSD sed가 illegal byte sequence를 내고 active가 비게 된다.
    # 그러면 .active-book을 무시하고 find의 첫 책을 잘못 선택한다. C 로캘 바이트 처리로 강제해야 안정적이다.
    # export 없는 session-*/pre-compact/post-compact도 이 라이브러리를 재사용하므로 여기서 명령별로 보완한다.
    # 호출자에 전역 부작용을 남기지 않도록 라이브러리에서 export하지 않는다(머리말의 호출자 셸 옵션 보존 원칙).
    active=$(LC_ALL=C sed -n '1p' "$root/.active-book" | LC_ALL=C sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || true)
    if [ -n "$active" ]; then
      local active_path active_real
      active_path=$(resolve_project_path "$active")
      # 탈출이 확실할 때만 거부한다. realpath를 실제 해석했고 바이트 비교로 프로젝트 밖임을 확인한 경우만 선언을 버리며
      # 나머지는 기존 순수 문자열 동작을 유지한다. cd+pwd -P는 OS가 중국어 경로 전체를 해석해 Windows 비UTF-8
      # 로캘(cp936/GBK)에서는 실패하거나 중국어 부분을 재인코딩할 수 있다. 이전에는 해석 성공을 반환 조건으로 삼아 유효한
      # 중국어 .active-book을 조용히 버렸고 find -name 追踪도 같은 멀티바이트 약점으로 대체 탐색이 실패했다.
      # 포함 판정은 LC_ALL=C 자식 셸에서 바이트 비교한다. 패턴과 문자열 모두 중국어 UTF-8이라 GBK 디코딩에서는
      # 잘못된 시퀀스로 불일치할 수 있다. 자식 셸 할당은 밖으로 새지 않아 호출자 셸 옵션 보존 원칙을 지킨다.
      active_real=$(cd "$active_path" 2>/dev/null && pwd -P || true)
      if [ -n "$active_real" ] && ! (
        export LC_ALL=C
        case "$active_real" in
          "$root"|"$root"/*) exit 0 ;;
        esac
        exit 1
      ); then
        : # 프로젝트 루트 탈출 확정 → 선언을 버리고 아래 자동 탐색으로 이동
      else
        printf '%s\n' "$active_path"
        return
      fi
    fi
  fi

  # 장편 우선(추적/ 디렉터리 존재)
  local first
  first=$(find "$root" -maxdepth 4 \
    \( -type d ! -path "$root" \( -name '.*' -o -name node_modules \) -prune \) -o \
    \( -type d -name "추적" -print -quit \) 2>/dev/null || true)
  if [ -n "$first" ]; then
    dirname "$first"
    return
  fi

  # 단편 대체 탐색: 본문/ 또는 본문.md를 찾는다(maxdepth 4는 推荐/단편/书名/본문 구조 포함).
  local story_path
  story_path=$(find "$root" -maxdepth 4 \
    \( -type d ! -path "$root" \( -name '.*' -o -name node_modules \) -prune \) -o \
    \( \( -type d -name "본문" -o -type f -name "본문.md" \) -print -quit \) 2>/dev/null || true)
  if [ -n "$story_path" ]; then
    dirname "$story_path"
  fi
}

# analysis_incomplete <_progress.md 경로> — 작품 분석 진행이 미완료인지 판정한다(0이면 미완료).
# 최종 상태 필드의 completed / completed_with_errors는 완료, 나머지 상태
# pending / paused_after_stage1과 필드 누락, 빈 파일, 읽기 실패는 모두 미완료로 처리한다.
# 안내를 한 번 더 하더라도 중간에 끊긴 분석이 조용히 사라지지 않게 한다(빈 파일은 파이프 시작 직후 중단된 형태).
# LC_ALL=C에서 전각 콜론은 바이트로 비교하므로 [：:] 대신 (：|:)를 쓴다. 문자 집합은 전각 문장부호를 바이트로 쪼갠다.
analysis_incomplete() {
  local value
  # 콜론 뒤 상태값 자체만 인식한다. 전체 줄에 *completed* 부분문자열 검사를 하면 템플릿 자리표시자인
  # `{pending/paused_after_stage1/completed/completed_with_errors}`와
  # pending(지난 completed 이후 재실행) 같은 괄호 설명도 완료로 오인해 중단된 분석을 조용히 지운다.
  #
  # 전각 문자는 LC_ALL=C grep의 작은따옴표 패턴 안에만 허용하며 매개변수 확장이나 case 패턴에 넣으면 안 된다.
  # GBK에서 bash는 소스를 2바이트로 디코딩해 전각 콜론 끝 바이트와 바로 뒤 `}`를 한 문자로 묶어
  # 닫는 중괄호를 삼킨다. `${x#*：}`는 common.sh 전체 문법 오류를 일으켜 모든 훅을 멈춘다.
  # 문자 집합도 [：:]가 바이트로 분리되므로 (：|:) 선택식을 쓴다.
  value=$(LC_ALL=C grep -m1 -oE '最终状态(：|:)[[:space:]]*[A-Za-z_]+' "$1" 2>/dev/null \
    | LC_ALL=C grep -oE '[A-Za-z_]+$' || true)
  [ -n "$value" ] || return 0
  case "$value" in
    completed|completed_with_errors) return 1 ;;
    *) return 0 ;;
  esac
}

# discover_incomplete_analyses <프로젝트 루트> — 작품분석실/ 아래 미완료 _progress.md 목록
# 출력: 줄바꿈 구분 절대 경로(discover_all_books와 동일). 분석 라이브러리가 없으면 빈 출력.
discover_incomplete_analyses() {
  local root="$1"
  # 경로 리터럴 끝 `/`를 유지한다. 拆文库의 UTF-8은 홀수 바이트라 GBK에서 닫는 따옴표가 붙으면
  # bash가 마지막 바이트와 따옴표를 같은 멀티바이트 문자로 오인해 이후 함수 정의가 모두 사라진다. 끝 `/`로 바이트를 맞춘다.
  [ -d "$root/작품분석실/" ] || return 0
  { find "$root/작품분석실/" -name "_progress.md" -print 2>/dev/null || true; } | while IFS= read -r progress_file; do
    [ -n "$progress_file" ] || continue
    if analysis_incomplete "$progress_file"; then printf '%s\n' "$progress_file"; fi
  done
  # 명시적으로 0을 반환한다. 마지막 반복이 완료 판정이면 while이 1을 내보내고 호출자가 pipefail을 켠 경우
  # (모든 훅이 사용) set -e로 중단된다. if로 감싸고 return 0도 사용해 이중 보장한다.
  return 0
}

# discover_all_books — 프로젝트의 모든 책 조회
# 출력: 중복 없는 절대 디렉터리 경로 목록, 줄바꿈 구분.
# 용도: detect-story-gaps가 프로젝트의 모든 책을 순회해 누락을 검사할 때 사용한다.
discover_all_books() {
  local root
  root=$(project_root)
  # awk로 삽입 순서를 유지하며 중복 제거(bash 3.2 호환, 연관 배열 없음)
  {
    # 장편: 추적/의 부모 디렉터리
    find "$root" -maxdepth 4 \
      \( -type d ! -path "$root" \( -name '.*' -o -name node_modules \) -prune \) -o \
      \( -type d -name "추적" -print \) 2>/dev/null | while IFS= read -r d; do dirname "$d"; done
    # 단편: 본문/ 또는 본문.md의 부모 디렉터리
    find "$root" -maxdepth 4 \
      \( -type d ! -path "$root" \( -name '.*' -o -name node_modules \) -prune \) -o \
      \( \( -type d -name "본문" -o -type f -name "본문.md" \) -print \) 2>/dev/null | while IFS= read -r d; do dirname "$d"; done
  } | awk 'NF && !seen[$0]++'
}
