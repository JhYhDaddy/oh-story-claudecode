#!/bin/bash
# pre-compact.sh — 압축 전 집필 상태 요약 기록(내용 전체 출력 안 함)
set -euo pipefail

# 공통 함수 라이브러리 로드
source "$(dirname "$0")/lib/common.sh"

# 바이트 안정 로캘: discover_active_book이 중국어 제목/경로를 GBK에서도 올바르게 처리하게 한다(이슈 #164 유형).
export LC_ALL=C

ROOT=$(project_root)

echo "=== Pre-Compact Summary ==="

BOOK_DIR=$(discover_active_book)

# 문맥.md 상태 요약(경로 + 줄 수, 내용은 출력하지 않음)
if [ -n "$BOOK_DIR" ] && [ -f "$BOOK_DIR/추적/문맥.md" ]; then
  LINE_COUNT=$(wc -l < "$BOOK_DIR/추적/문맥.md" | tr -d ' ')
  echo "Writing context: ${BOOK_DIR#$ROOT/}/추적/문맥.md ($LINE_COUNT lines)"
else
  echo "Active state: not found"
fi

# Git 미커밋 변경 수
CHANGED=$(git -C "$ROOT" diff --name-only 2>/dev/null | wc -l | tr -d ' ') || CHANGED=0
STAGED=$(git -C "$ROOT" diff --name-only --cached 2>/dev/null | wc -l | tr -d ' ') || STAGED=0
echo "Git: ${CHANGED} unstaged, ${STAGED} staged"

echo "=== Pre-Compact Complete ==="
