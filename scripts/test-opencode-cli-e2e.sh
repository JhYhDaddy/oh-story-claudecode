#!/usr/bin/env bash
# test-opencode-cli-e2e.sh — 프로젝트 로컬 story 설정 자산의 실제 OpenCode 2.x CLI 종단 간 검사.
#
# 파일 존재뿐 아니라 플러그인의 실제 런타임 로드(plugin.list 상태 active)와 훅의 실제 효과를
# OpenCode 런타임에서 검증한다. opencode-mock-llm.mjs가 정해진 도구 호출을 내는 모의 모델로 훅을 구동하고
# 저장 결과와 모델이 실제 받은 도구 응답을 단언한다. 모든 쿼리는 백그라운드 서비스로 보내며 서비스를 프로젝트 밖에서
# 시작한다(서비스 cwd != 프로젝트). 플러그인이 process.cwd() 대신 ctx.location으로 프로젝트를 찾는 회귀를 검사한다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT="$REPO_ROOT/skills/story-setup/references/opencode"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/ohstory-opencode-e2e.XXXXXX")"
TMP_ROOT="$(cd "$TMP_ROOT" && pwd -P)"
CLI_HOME="$TMP_ROOT/home"
PROJECT="$TMP_ROOT/project"
MOCK_LOG="$TMP_ROOT/mock-requests.jsonl"
MOCK_SCRIPT="$TMP_ROOT/mock-script.json"
MOCK_PID=""

fail() { echo "FAIL: $*" >&2; exit 1; }

if ! command -v opencode >/dev/null 2>&1; then
  fail "opencode CLI not found on PATH. Install OpenCode 2.x with: npm install -g @opencode/cli"
fi

run_opencode() {
  HOME="$CLI_HOME" \
    XDG_CONFIG_HOME="$CLI_HOME/.config" \
    XDG_DATA_HOME="$CLI_HOME/.local/share" \
    XDG_CACHE_HOME="$CLI_HOME/.cache" \
    XDG_STATE_HOME="$CLI_HOME/.local/state" \
    command opencode "$@"
}

cleanup() {
  run_opencode service stop >/dev/null 2>&1 || true
  if [ -n "$MOCK_PID" ]; then kill "$MOCK_PID" 2>/dev/null || true; wait "$MOCK_PID" 2>/dev/null || true; fi
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

mkdir -p "$CLI_HOME/.config/opencode"

VERSION="$(run_opencode --version 2>&1 | head -1)"
MAJOR="$(printf '%s\n' "$VERSION" | sed -nE 's/^[^0-9]*([0-9]+)\.[0-9]+\.[0-9]+.*/\1/p')"
[ -n "$MAJOR" ] && [ "$MAJOR" -ge 2 ] || fail "OpenCode 2.x required, got: $VERSION"

echo "OpenCode CLI E2E"
echo "================"
echo "Repo: $REPO_ROOT"
echo "OpenCode: $(command -v opencode) ($VERSION)"

# 백그라운드 서비스는 기본 고정 포트를 사용한다. 개발 기기의 기존 OpenCode가 점유하면 격리 HOME 서비스가 시작되지 않아
# 요청이 계속 재시도된다. 먼저 격리 HOME에 빈 포트를 고정하고 프로젝트 밖에서 시작한 뒤 모든 요청이 재사용한다.
SERVICE_PORT="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
run_opencode service set port "$SERVICE_PORT" >/dev/null
(cd "$CLI_HOME" && run_opencode api GET /api/info >/dev/null)

# location 범위 목록 API를 GET해 data가 비지 않을 때까지 기다린다(location 플러그인 비동기 준비로 첫 응답은 빌 수 있음).
# OpenCode 2.x는 스킬/플러그인/명령을 비동기 로드한다. 첫 비어 있지 않은 응답도 내장 항목뿐일 수 있다.
# 같은 버전 CI에서도 간헐적으로 실패하므로 $3의 쉼표 구분 id/name이 모두 나타날 때까지 기다린다.
# 30초 뒤에도 다 없으면 마지막 결과를 후속 검증에 넘겨 구체적인 누락을 보고하게 한다.
api_list() {
  local directory="$1" out="$2" require="$3"; shift 3
  local attempt
  for attempt in $(seq 1 30); do
    if run_opencode api "$@" -H "x-opencode-directory:$directory" >"$out" 2>"$out.err" &&
      python3 -c '
import json, sys
data = json.load(open(sys.argv[1])).get("data")
items = [item for item in data or [] if isinstance(item, dict)]
have = {item.get("id") for item in items} | {item.get("name") for item in items}
need = {name for name in sys.argv[2].split(",") if name}
sys.exit(0 if items and need <= have else 1)
' "$out" "$require" 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  if python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("data") else 1)' "$out" 2>/dev/null; then
    return 0
  fi
  cat "$out" "$out.err" >&2 || true
  fail "OpenCode API returned no data: $*"
}

STORY_SKILLS="browser-cdp,story,story-cover,story-deslop,story-import,story-long-analyze,story-long-scan,story-long-write,story-publish,story-review,story-setup,story-short-analyze,story-short-scan,story-short-write"

echo "  Checking repo-local skill discovery"
api_list "$REPO_ROOT" "$TMP_ROOT/repo-skills.json" "$STORY_SKILLS" GET /api/skill
python3 - "$TMP_ROOT/repo-skills.json" "$REPO_ROOT" <<'PY'
import json
import sys
from pathlib import Path

expected = {
    "browser-cdp",
    "story",
    "story-cover",
    "story-deslop",
    "story-import",
    "story-long-analyze",
    "story-long-scan",
    "story-long-write",
    "story-publish",
    "story-review",
    "story-setup",
    "story-short-analyze",
    "story-short-scan",
    "story-short-write",
}

data = json.loads(Path(sys.argv[1]).read_text())["data"]
repo_root = Path(sys.argv[2]).resolve()
items = {item.get("name") or item.get("id"): item for item in data if isinstance(item, dict)}
missing = sorted(expected - set(items))
if missing:
    raise SystemExit(f"missing OpenCode-discovered story skills: {missing}")
for name in expected:
    location = items[name].get("path")
    if not isinstance(location, str):
        raise SystemExit(f"{name}: OpenCode output omitted skill path")
    actual = Path(location).resolve()
    wanted = (repo_root / "skills" / name / "SKILL.md").resolve()
    if actual != wanted:
        raise SystemExit(f"{name}: expected location {wanted}, got {actual}")
print(f"    OK {len(expected)} story skills discovered")
PY

# story-setup 배포 목록과 동일하게 opencode.json을 쓰지 않고 .opencode/plugins/ 자동 탐색을 사용한다.
mkdir -p \
  "$PROJECT/.opencode/agents" \
  "$PROJECT/.opencode/commands" \
  "$PROJECT/.opencode/plugins/lib" \
  "$PROJECT/skills/story-setup/references"
cp -R "$ROOT/agents/." "$PROJECT/.opencode/agents/"
cp -R "$ROOT/commands/." "$PROJECT/.opencode/commands/"
cp "$ROOT/plugin.ts" "$PROJECT/.opencode/plugins/story-hooks.ts"
cp "$ROOT/story_hook_core.js" "$PROJECT/.opencode/plugins/lib/story_hook_core.js"
cp "$ROOT/AGENTS.md.tmpl" "$PROJECT/AGENTS.md"
cp -R "$REPO_ROOT/skills/story-setup/references/agent-references" \
  "$PROJECT/skills/story-setup/references/agent-references"
git -C "$PROJECT" init -q

echo "  Checking deployed project plugin/commands/agents"
api_list "$PROJECT" "$TMP_ROOT/plugins.json" "oh-story.story-hooks" plugin.list
api_list "$PROJECT" "$TMP_ROOT/commands.json" "$STORY_SKILLS" GET /api/command
(cd "$PROJECT" && run_opencode debug agents >"$TMP_ROOT/agents.json")
python3 - "$TMP_ROOT" <<'PY'
import json
import sys
from pathlib import Path

tmp = Path(sys.argv[1])
plugins = json.loads((tmp / "plugins.json").read_text())["data"]
commands = json.loads((tmp / "commands.json").read_text())["data"]
agents = json.loads((tmp / "agents.json").read_text())

story = [item for item in plugins if item.get("id") == "oh-story.story-hooks"]
if not story:
    raise SystemExit("story-hooks plugin missing from plugin.list")
status = (story[0].get("state") or {}).get("status")
if status != "active":
    raise SystemExit(f"story-hooks plugin not active: {json.dumps(story[0], ensure_ascii=False)}")
if not str((story[0].get("source") or {}).get("path", "")).endswith("/.opencode/plugins/story-hooks.ts"):
    raise SystemExit(f"story-hooks loaded from unexpected source: {story[0].get('source')}")

expected_commands = {
    "browser-cdp",
    "story",
    "story-cover",
    "story-deslop",
    "story-import",
    "story-long-analyze",
    "story-long-scan",
    "story-long-write",
    "story-review",
    "story-setup",
    "story-short-analyze",
    "story-short-scan",
    "story-short-write",
}
expected_agents = {
    "chapter-extractor",
    "character-designer",
    "consistency-checker",
    "narrative-writer",
    "story-architect",
    "story-explorer",
    "story-researcher",
}
command_ids = {item.get("id") or item.get("name") for item in commands}
missing_commands = sorted(expected_commands - command_ids)
if missing_commands:
    raise SystemExit(f"missing OpenCode commands: {missing_commands}")
by_id = {item.get("id"): item for item in agents}
missing_agents = sorted(expected_agents - set(by_id))
if missing_agents:
    raise SystemExit(f"missing OpenCode agents: {missing_agents}")
for name in expected_agents:
    agent = by_id[name]
    if agent.get("mode") != "subagent":
        raise SystemExit(f"{name}: mode should be subagent, got {agent.get('mode')!r}")
    rules = agent.get("permissions") or []
    if {"action": "*", "resource": "*", "effect": "deny"} not in rules:
        raise SystemExit(f"{name}: native permissions did not load: {rules}")
if "只读" not in by_id["story-explorer"].get("description", ""):
    raise SystemExit("story-explorer description did not load story content")

print(f"    OK story-hooks active, {len(expected_commands)} commands, {len(expected_agents)} agents")
PY

echo "  Checking plugin hooks on the real runtime (mock model)"
MOCK_LOG="$MOCK_LOG" MOCK_SCRIPT="$MOCK_SCRIPT" node "$SCRIPT_DIR/opencode-mock-llm.mjs" >"$TMP_ROOT/mock-port" &
MOCK_PID=$!
MOCK_PORT=""
for _ in $(seq 1 100); do
  MOCK_PORT="$(tr -d '[:space:]' <"$TMP_ROOT/mock-port")"
  [ -n "$MOCK_PORT" ] && break
  sleep 0.1
done
[ -n "$MOCK_PORT" ] || fail "mock model did not start"
cat >"$CLI_HOME/.config/opencode/opencode.json" <<JSON
{
  "\$schema": "https://opencode.ai/config.json",
  "providers": {
    "mock": {
      "name": "Mock",
      "package": "@opencode/ai/providers/openai-compatible",
      "settings": { "baseURL": "http://127.0.0.1:$MOCK_PORT/v1", "apiKey": "fixture" },
      "models": { "probe": { "name": "probe" } }
    }
  }
}
JSON
# 전역 설정 변경으로 실행 중 서비스를 다시 로드해 시작 시의 빈 provider 목록이 남지 않도록 한다.
run_opencode reload >/dev/null 2>&1 || true

mkdir -p "$PROJECT/book/본문" "$PROJECT/book/개요" "$PROJECT/book/추적"
printf '# 上下文\n当前位置\n' >"$PROJECT/book/추적/문맥.md"
printf 'book\n' >"$PROJECT/.active-book"

# 모의 모델이 정해진 도구 호출 한 차례로 `opencode run`을 마치게 한다. 로그는 이번 요청만 남긴다.
run_case() {
  local label="$1" calls="$2" pid
  printf '%s\n' "$calls" >"$MOCK_SCRIPT"
  : >"$MOCK_LOG"
  (cd "$PROJECT" && run_opencode run --model mock/probe "$label" >"$TMP_ROOT/run.out" 2>"$TMP_ROOT/run.err") &
  pid=$!
  for _ in $(seq 1 120); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    fail "$label: opencode run timed out"
  fi
  wait "$pid" || { cat "$TMP_ROOT/run.err" >&2; fail "$label: opencode run failed"; }
}

# 모델이 받은 마지막 도구 응답이 지정 정규식과 일치하는지 단언한다.
assert_tool_result() {
  python3 - "$MOCK_LOG" "$1" "$2" <<'PY'
import json
import re
import sys

log, label, pattern = sys.argv[1:]
rows = [json.loads(line) for line in open(log, encoding="utf-8") if line.strip()]
results = [m for row in rows for m in row["body"].get("messages", []) if m.get("role") == "tool"]
if not results:
    raise SystemExit(f"{label}: model never received a tool result ({len(rows)} requests)")
content = results[-1].get("content")
text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
if not re.search(pattern, text):
    raise SystemExit(f"{label}: tool result did not match {pattern!r}: {text[:600]}")
PY
}

run_case block-write '[{"name":"write","arguments":{"path":"book/본문/제001장_开局.md","content":"正文。"}}]'
[ ! -e "$PROJECT/book/본문/제001장_开局.md" ] || fail "write without outline reached disk"
assert_tool_result block-write '본문 쓰기 차단: 第 1 章상세 개요가 없습니다'

run_case block-shell '[{"name":"shell","arguments":{"command":"printf x > book/본문/제002장_绕过.md","description":"fixture"}}]'
[ ! -e "$PROJECT/book/본문/제002장_绕过.md" ] || fail "shell redirect without outline reached disk"
assert_tool_result block-shell '본문 쓰기 차단[\s\S]*已从 Shell 命令识别到正文写入目标'

run_case block-patch '[{"name":"patch","arguments":{"patchText":"*** Begin Patch\n*** Add File: book/본문/제003장_补丁.md\n+正文。\n*** End Patch\n"}}]'
[ ! -e "$PROJECT/book/본문/제003장_补丁.md" ] || fail "patch without outline reached disk"
assert_tool_result block-patch '본문 쓰기 차단: 第 3 章상세 개요가 없습니다'

# 상세 개요에 내용이 있어야(#과 공백 제외 30자 이상) 본문 쓰기를 허용한다.
printf '%s\n' '# 细纲' '江晨在雨夜推开旧书店的门，发现柜台后坐着失踪三年的师父，两人对视良久。' >"$PROJECT/book/개요/상세개요_제1장.md"
printf '{"schema_version": 4, "state_revision": 0, "last_committed_chapter": 0}\n' >"$PROJECT/book/추적/_tracking-state.json"
printf '> 状态修订：0\n' >"$PROJECT/book/추적/문맥.md"
CALLS="$(python3 -c 'import json; print(json.dumps([{"name": "write", "arguments": {"path": "book/본문/제001장_开局.md", "content": "街灯一盏盏亮起。" * 30 + "\nTODO 此处待补"}}], ensure_ascii=False))')"
run_case after-write "$CALLS"
[ -s "$PROJECT/book/본문/제001장_开局.md" ] || fail "outlined write was blocked or not written"
assert_tool_result after-write '본문 보완 검사（book/본문/제001장_开局\.md）[\s\S]*占位符'
echo "    OK write/shell/patch blocked without outline; outlined write passes with after-write findings"

SESSION_ID="$(cd "$PROJECT" && run_opencode session list --format json | python3 -c '
import json, sys
data = json.load(sys.stdin)
items = data.get("data", data) if isinstance(data, dict) else data
print(items[0]["id"])')"
: >"$MOCK_LOG"
run_opencode api session.compact --param "sessionID=$SESSION_ID" -d '{}' -H "x-opencode-directory:$PROJECT" >/dev/null
compacted=""
for _ in $(seq 1 60); do
  if grep -q 'Pre-Compact Summary' "$MOCK_LOG" 2>/dev/null; then compacted=1; break; fi
  sleep 1
done
[ -n "$compacted" ] || fail "compaction request never reached the model"
grep -q 'Writing context: book/추적/문맥.md' "$MOCK_LOG" ||
  fail "compaction hook did not resolve the project from ctx.location"
echo "    OK compaction request carries the writing-context pointer"

echo ""
echo "OK: OpenCode CLI E2E passed"
