#!/usr/bin/env bash
# test-codex-cli-e2e.sh — 저장소 스킬 탐색의 실제 Codex CLI 스모크 테스트.
# `debug prompt-input`은 인증 없는 실험적 진단이다. 안정적인 정적 스키마/생성기/훅
# 보완 검사는 계속 check-codex-adapter.sh가 담당한다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EXPECTED_COUNT=14
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/ohstory-codex-e2e.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

command -v codex >/dev/null 2>&1 \
  || fail "codex CLI not found on PATH. Install with: npm install -g @openai/codex"

mkdir -p "$TMP_ROOT/home/.codex"
WORKSPACE="$TMP_ROOT/workspace"
mkdir -p "$WORKSPACE/.agents" "$WORKSPACE/.codex/agents" "$WORKSPACE/.codex/hooks"
cp -R "$REPO_ROOT/skills" "$WORKSPACE/skills"
ln -s ../skills "$WORKSPACE/.agents/skills"
cp "$REPO_ROOT"/skills/story-setup/references/codex/agents/*.toml \
  "$WORKSPACE/.codex/agents/"
cp "$REPO_ROOT/skills/story-setup/references/codex/hooks/hooks.json" \
  "$WORKSPACE/.codex/hooks.json"
cp "$REPO_ROOT"/skills/story-setup/references/codex/hooks/{story_codex_hook.py,run-story-hook.sh,run-story-hook.cmd} \
  "$WORKSPACE/.codex/hooks/"
cp "$REPO_ROOT/skills/story-setup/references/codex/AGENTS.md.tmpl" \
  "$WORKSPACE/AGENTS.md"
git -C "$WORKSPACE" init -q
python3 - "$TMP_ROOT/home/.codex/config.toml" "$WORKSPACE" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    f"[projects.{json.dumps(sys.argv[2])}]\ntrust_level = \"trusted\"\n",
    encoding="utf-8",
)
PY

echo "Codex CLI E2E"
echo "============="
echo "Repo: $REPO_ROOT"
echo "Codex: $(command -v codex) ($(codex --version))"
echo "  Checking isolated deployed project (skills + agents + hooks)"

HOME="$TMP_ROOT/home" CODEX_HOME="$TMP_ROOT/home/.codex" \
  codex -C "$WORKSPACE" debug prompt-input >"$TMP_ROOT/prompt-input.json"

python3 - "$TMP_ROOT/prompt-input.json" "$WORKSPACE" "$EXPECTED_COUNT" <<'PY'
import json
import re
import sys
try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        from pip._vendor import tomli as tomllib
from pathlib import Path

output_path = Path(sys.argv[1])
repo_root = Path(sys.argv[2]).resolve()
expected_count = int(sys.argv[3])

data = json.loads(output_path.read_text(encoding="utf-8"))

def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)

rendered = "\n".join(strings(data))

# Codex CLI >= 0.151.0은 스킬을 짧은 `rN/<skill>/SKILL.md` 경로와
# Skill roots 별칭 표로 표시한다. 별칭을 절대 경로로 확장해 아래 단언이
# 버전과 무관하게 작동하게 한다. 이전 CLI는 절대 경로만 출력하고 표가 없어
# 이 경우에는 아무것도 바꾸지 않는다.
skill_roots = re.findall(r"^- `(r\d+)` = `([^`]+)`", rendered, re.MULTILINE)
for alias, root in sorted(skill_roots, key=lambda item: -len(item[0])):
    rendered = re.sub(
        r"(?<![0-9A-Za-z_])" + re.escape(alias) + "/",
        str(Path(root).resolve()).replace("\\", "\\\\") + "/",
        rendered,
    )

expected = {
    path.parent.name: str(path.resolve())
    for path in (repo_root / "skills").glob("*/SKILL.md")
}
if len(expected) != expected_count:
    raise SystemExit(
        f"repository fixture error: expected {expected_count} skills, found {len(expected)}"
    )

missing = sorted(name for name, path in expected.items() if path not in rendered)
if missing:
    raise SystemExit(f"Codex prompt input omitted repository skills: {missing}")

repo_pattern = re.compile(
    re.escape(str(repo_root / "skills")) + r"/([^/]+)/SKILL\.md"
)
discovered = set(repo_pattern.findall(rendered))
extra = sorted(discovered - set(expected))
if extra:
    raise SystemExit(f"Codex discovered unexpected repository skills: {extra}")

agents = sorted((repo_root / ".codex/agents").glob("*.toml"))
if len(agents) != 7:
    raise SystemExit(f"deployed fixture error: expected 7 custom agents, found {len(agents)}")
for path in agents:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    for key in ("name", "description", "developer_instructions"):
        if not data.get(key):
            raise SystemExit(f"{path}: missing required custom-agent field {key}")
hooks = json.loads((repo_root / ".codex/hooks.json").read_text(encoding="utf-8"))
if not hooks.get("hooks"):
    raise SystemExit("deployed fixture error: .codex/hooks.json has no hooks")

print(f"    OK Codex discovered all {len(expected)} repository skills")
print(f"    OK isolated fixture includes {len(agents)} custom agents and hook configuration")
PY

echo "OK: Codex CLI E2E passed"
