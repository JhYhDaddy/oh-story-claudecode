#!/usr/bin/env bash
# check-claude-adapter.sh — Claude Code 마켓플레이스/플러그인 호환성 검사.
# 기본은 정적 검사다. CLAUDE_REAL_CHECK=1이면 설치된 Claude CLI를 호출한다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

fail() { echo "FAIL: $*" >&2; exit 1; }

echo "Claude Code adapter check"
echo "========================="
echo "Repo: $REPO_ROOT"
python3 "$SCRIPT_DIR/check-plugin-packaging.py" --root "$REPO_ROOT"

if [ "${CLAUDE_REAL_CHECK:-0}" = "1" ]; then
  command -v claude >/dev/null 2>&1 \
    || fail "CLAUDE_REAL_CHECK=1 but claude is not on PATH"
  TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ohstory-claude-check.XXXXXX")"
  trap 'rm -rf "$TMP_DIR"' EXIT
  mkdir -p "$TMP_DIR/home" "$TMP_DIR/config" "$TMP_DIR/plugin/.claude-plugin"
  export HOME="$TMP_DIR/home" USERPROFILE="$TMP_DIR/home" CLAUDE_CONFIG_DIR="$TMP_DIR/config"
  echo "  Claude: $(claude --version)"

  # 매니페스트가 둘 다 있는 디렉터리는 Claude에서 마켓플레이스로 검증한다.
  # 실제 플러그인을 별도로 검증해 기본 탐색으로 발견되는 SKILL.md 파일 14개를
  # 파싱하게 한다. 합성한 구성 요소 매니페스트로 대체하지 않는다.
  cp "$REPO_ROOT/.claude-plugin/plugin.json" "$TMP_DIR/plugin/.claude-plugin/plugin.json"
  cp -R "$REPO_ROOT/skills" "$TMP_DIR/plugin/skills"
  claude plugin validate --strict "$TMP_DIR/plugin"
  claude plugin validate --strict "$REPO_ROOT/.claude-plugin/marketplace.json"
  echo "  OK Claude CLI strict component and marketplace validation"

  # 세 범위 모두 별도 홈/설정과 임시 git 작업 공간을 사용한다.
  python3 "$SCRIPT_DIR/test-claude-plugin-lifecycle.py"
fi

echo "OK: Claude Code adapter checks passed"
