#!/usr/bin/env bash
# Reasonix 네이티브 플러그인 매니페스트의 결정론적 검사(이슈 #204/#252).
# Reasonix(DeepSeek-Reasonix CLI)는 루트 reasonix-plugin.json을 읽고 프로젝트 스킬 루트를
# 스캔한다. 이 검사는 전역 매니페스트를 다룬다. 프로젝트 수준 `story-setup` 배포는
# 스킬만 제공한다(target_cli=reasonix, skills + AGENTS.md, 훅/사용자 지정 에이전트 없음
# → 단독/직접 실행 대체 경로). check-story-setup-deployment.sh가 이를 검증한다.
# Reasonix 훅과 사용자 지정 에이전트는 후속 단계다. 실제 `reasonix doctor
# capabilities`는 CLI가 필요하므로 CI에 포함하지 않는다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

fail() { echo "FAIL: $*" >&2; exit 1; }

echo "Reasonix adapter check"
echo "======================"
echo "Repo: $REPO_ROOT"

[ -f reasonix-plugin.json ] || fail "reasonix-plugin.json missing"
python3 -m json.tool reasonix-plugin.json >/dev/null || fail "reasonix-plugin.json is not valid JSON"

python3 - <<'PY'
import json, re
from pathlib import Path

manifest = json.loads(Path('reasonix-plugin.json').read_text())
assert re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,127}', manifest.get('name', '')), f"bad name: {manifest.get('name')!r}"
assert manifest['name'] == 'oh-story', manifest['name']
assert manifest['skills'] == 'skills', manifest.get('skills')
assert isinstance(manifest.get('description'), str) and manifest['description'], 'description required'
version = Path('skills/story/VERSION').read_text().strip()
assert manifest['version'] == version, f"version {manifest['version']!r} must match skills/story/VERSION {version!r}"
# 매니페스트가 `skills` 아래 스킬을 제공한다는 약속을 확인한다.
skills = sorted(Path('skills').glob('*/SKILL.md'))
assert len(skills) == 14, f'expected 14 skills, got {len(skills)}'
PY
echo "  OK reasonix-plugin.json (schema + version pin + 14 Skills)"
echo ""
echo "OK: Reasonix adapter checks passed"
