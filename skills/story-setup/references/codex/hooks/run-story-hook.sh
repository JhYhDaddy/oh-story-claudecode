#!/bin/sh
# 프로젝트 로컬 Codex 훅 실행기. hooks.json이 이 파일을 찾으며 이 스크립트가
# 인터프리터 탐색과 이벤트 분배를 담당해 훅 등록 6개에 중복하지 않게 한다.
set -eu

EVENT="${1:-}"
case "$EVENT" in
  session-start|pre-tool-prose-guard|pre-tool-commit-advisory|pre-compact|post-compact|stop) ;;
  *) exit 2 ;;
esac

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
HOOK="$SCRIPT_DIR/story_codex_hook.py"
[ -f "$HOOK" ] || exit 0

PYBIN=
for candidate in python3 python py; do
  if "$candidate" -c "" >/dev/null 2>&1; then
    PYBIN=$candidate
    break
  fi
done
[ -n "$PYBIN" ] || exit 0

CODEX_PROJECT_DIR="$PROJECT_ROOT"; export CODEX_PROJECT_DIR
exec "$PYBIN" "$HOOK" "$EVENT"
