#!/bin/bash
# session-end.sh — 세션 종료 시 필요한 경우 마지막 상태 기록
# 설계 원칙: 기본은 조용히 파일을 쓰지 않음. 명시적으로 켜도 단편 프로젝트의 추적/을 만들지 않음.
set -euo pipefail

# 공통 함수 라이브러리 로드
source "$(dirname "$0")/lib/common.sh"

# 바이트 안정 로캘: discover_active_book이 중국어 제목/경로를 GBK에서도 올바르게 처리하게 한다(이슈 #164 유형).
export LC_ALL=C

# 작업 트리가 매 세션 종료마다 오염되지 않도록 session-log.txt 쓰기를 기본 비활성화한다.
# STORY_SESSION_LOG=1을 명시해야 켜지며 그래도 기존 장편 추적 디렉터리에만 쓴다.
if [ "${STORY_SESSION_LOG:-0}" != "1" ]; then
  exit 0
fi

BOOK_DIR=$(discover_active_book)

# 기존 추적 디렉터리에만 쓴다. 단편을 장편 구조로 바꾸지 않도록 mkdir하지 않는다.
if [ -n "$BOOK_DIR" ] && [ -d "$BOOK_DIR/추적" ]; then
  echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] session ended" >> "$BOOK_DIR/추적/session-log.txt"
fi
