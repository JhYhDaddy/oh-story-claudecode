#!/bin/sh
# 구조화된 현재 스킬 계약 검증기의 이식 가능한 실행기.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

PYTHON=
for candidate in python3 python py; do
  if "$candidate" -c "" >/dev/null 2>&1; then
    PYTHON=$candidate
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "Error: Python 3 is required (tried python3, python, and py)" >&2
  exit 127
fi

exec "$PYTHON" "$SCRIPT_DIR/check-current-skill-contracts.py" "$@"
