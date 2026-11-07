#!/bin/bash
# post-compact.sh — 압축 후 컨텍스트 복원 안내
set -euo pipefail

# 공통 함수 라이브러리 로드
source "$(dirname "$0")/lib/common.sh"

# 바이트 안정 로캘: discover_active_book이 중국어 제목/경로를 GBK에서도 올바르게 처리하게 한다(이슈 #164 유형).
export LC_ALL=C

ROOT=$(project_root)
BOOK_DIR=$(discover_active_book)

if [ -n "$BOOK_DIR" ] && [ -f "$BOOK_DIR/추적/문맥.md" ]; then
  LINE_COUNT=$(wc -l < "$BOOK_DIR/추적/문맥.md" | tr -d ' ')
  echo "Context was compacted. Read ${BOOK_DIR#$ROOT/}/추적/문맥.md ($LINE_COUNT lines) to restore writing context."
else
  echo "Context was compacted. Check 추적/문맥.md to restore context."
fi
