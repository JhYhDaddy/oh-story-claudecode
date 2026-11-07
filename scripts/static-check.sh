#!/bin/bash
# 구조화된 스킬 Markdown 검사의 크로스 플랫폼 실행기.

set -euo pipefail

# `set -e`에서 단순 할당은 명령 치환의 종료 코드를 상속한다. git 실패(저장소 아님/git 없음) 시 즉시 중단되어
# 아래 진단 분기에 도달하지 못한다. `|| true`로 감싸고 판단을 -z 검사에 맡긴다.
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$REPO_ROOT" ]; then
  echo "Error: not in a git repository" >&2
  exit 1
fi

PYBIN=""
for candidate in python3 python py; do
  if "$candidate" -c "" >/dev/null 2>&1; then
    PYBIN="$candidate"
    break
  fi
done
if [ -z "$PYBIN" ]; then
  echo "Error: Python 3 is required for scripts/static-check.py" >&2
  exit 1
fi

exec "$PYBIN" "$REPO_ROOT/scripts/static-check.py" --root "$REPO_ROOT"
