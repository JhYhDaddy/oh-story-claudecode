#!/usr/bin/env bash
# ZCode 플러그인과 story-setup 배포 인터페이스의 결정론적 검사.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

fail() { echo "FAIL: $*" >&2; exit 1; }
assert_file() { [ -f "$1" ] || fail "required file missing: $1"; }
assert_dir() { [ -d "$1" ] || fail "required directory missing: $1"; }
assert_grep() { grep -Eq "$1" "$2" || fail "$3 ($2)"; }

ROOT="skills/story-setup/references/zcode"
HOOK="$ROOT/hooks/story_zcode_hook.js"
HOOK_CORE="$ROOT/hooks/story_hook_core.js"

echo "ZCode adapter check"
echo "==================="
echo "Repo: $REPO_ROOT"

for file in \
  .zcode-plugin/plugin.json \
  marketplace.json \
  "$ROOT/AGENTS.md.tmpl" \
  "$ROOT/config.json.patch" \
  "$ROOT/hooks/hooks.json" \
  "$HOOK" \
  "$HOOK_CORE" \
  scripts/generate-zcode-agents.py \
  scripts/test-zcode-agents.py; do
  assert_file "$file"
done
assert_dir "$ROOT/agents"

for file in .zcode-plugin/plugin.json marketplace.json "$ROOT/config.json.patch" "$ROOT/hooks/hooks.json"; do
  python3 -m json.tool "$file" >/dev/null
done
node --check "$HOOK"
node --check "$HOOK_CORE"
echo "  OK JSON/JavaScript syntax"

python3 - <<'PY'
import json
from pathlib import Path

plugin = json.loads(Path('.zcode-plugin/plugin.json').read_text())
assert plugin['commands'] == 'skills/story-setup/references/zcode/commands'
assert plugin['agents'] == 'skills/story-setup/references/zcode/agents'
assert plugin['hooks'] == 'skills/story-setup/references/zcode/hooks/hooks.json'
for key in ('channels', 'lspServers', 'outputStyles', 'settings'):
    assert key not in plugin, f'non-runnable ZCode component declared: {key}'

market = json.loads(Path('marketplace.json').read_text())
assert market['version'] == 1
PY
# 두 카탈로그 경로와 두 네이티브 매니페스트(#390), 정확한 루트 스킬 집합은
# 같은 CI 작업에서 check-claude-adapter.sh가 실행하는 check-plugin-packaging.py가 검사한다.
echo "  OK native plugin/marketplace manifest"

python3 - <<'PY'
import re
from pathlib import Path

skills = sorted(Path('skills').glob('*/SKILL.md'))
commands = sorted(Path('skills/story-setup/references/zcode/commands').glob('*.md'))
expected = {p.parent.name for p in skills}
assert {p.stem for p in commands} == expected

for skill in skills:
    text = skill.read_text(encoding='utf-8')
    front = text.split('---', 2)[1]
    name = re.search(r'^name:\s*["\']?([^"\'\n]+)', front, re.M)
    desc = re.search(r'^description:\s*(.+)$', front, re.M)
    assert name and name.group(1).strip() == skill.parent.name, skill
    assert desc, f'{skill}: missing description'
    value = desc.group(1).strip().strip('"\'')
    assert len(value) <= 1024, f'{skill}: description too long'

allowed = {'description', 'argument-hint', 'allowed-tools', 'model', 'skills', 'disable-noninteractive'}
for command in commands:
    assert re.fullmatch(r'[a-z0-9][a-z0-9_:-]{0,63}', command.stem), command
    text = command.read_text(encoding='utf-8')
    assert text.startswith('---\n'), command
    front, body = text.split('---', 2)[1:]
    keys = {line.split(':', 1)[0] for line in front.splitlines() if ':' in line}
    assert keys <= allowed, f'{command}: unsupported keys {keys - allowed}'
    assert 'description' in keys and 'skills' in keys
    assert '$ARGUMENTS' in body
PY
echo "  OK Skills + Commands (schema and one-to-one names; skill set pinned by check-plugin-packaging.py)"

python3 scripts/generate-zcode-agents.py --check
python3 scripts/test-zcode-agents.py
python3 - <<'PY'
import importlib.util
from pathlib import Path

root = Path('skills/story-setup/references/zcode/agents')
expected = {
    'chapter-extractor', 'character-designer', 'consistency-checker',
    'narrative-writer', 'story-architect', 'story-explorer', 'story-researcher',
}
files = sorted(root.glob('*.md'))
assert {path.stem for path in files} == expected

generator_path = Path('scripts/generate-zcode-agents.py')
spec = importlib.util.spec_from_file_location('zcode_agent_generator_check', generator_path)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

allowed = {'name', 'description', 'model', 'tools', 'disallowedTools', 'maxTurns'}
for path in files:
    meta, body = module.parse_frontmatter(path.read_text(encoding='utf-8'))
    assert set(meta) <= allowed, (path, set(meta) - allowed)
    assert {'name', 'description', 'model', 'tools', 'maxTurns'} <= set(meta), path
    assert meta['name'] == path.stem
    assert meta['model'] == 'inherit'
    assert module.parse_tool_list(meta['tools'], 'tools'), path
    assert 'hooks' not in meta
    assert '.claude/skills/' not in body and '当前 Claude 部署' not in body
    assert 'Agent(subagent_type' not in body

for name in ('consistency-checker', 'story-explorer'):
    meta, _ = module.parse_frontmatter((root / f'{name}.md').read_text(encoding='utf-8'))
    assert module.parse_tool_list(meta['tools'], 'tools') == {'Read', 'Glob', 'Grep'}
    assert module.parse_tool_list(meta['disallowedTools'], 'disallowedTools') == {'Write', 'Edit', 'Bash'}

chapter = (root / 'chapter-extractor.md').read_text(encoding='utf-8')
assert any(s in chapter for s in ('不提供 Claude inline hook 的 per-agent 写入强隔离', 'Claude 인라인 훅의 에이전트별 강한 쓰기 격리를 제공하지 않습니다'))
assert any(s in chapter for s in ('只能 Write/Edit 调用方指定的单个', '호출자가 지정한 단일 `_analysis_cache/输入-{批次ID}.md`에만 Write/Edit할 수 있으며'))
PY
echo "  OK plugin Agents (7 generated roles; bounded tools; no Claude-only inline hooks)"

python3 - <<'PY'
import json
from pathlib import Path

supported = {'SessionStart', 'UserPromptSubmit', 'PreToolUse', 'PermissionRequest', 'PostToolUse', 'PostToolUseFailure', 'Stop'}
# 이벤트 → 허용 handler. 이름이 허용 집합에 있는지만 검사하면 블록 복사 뒤 args[1] 수정을 잊어
# SessionStart에 post-tool-prose-check를 연결한 오류도 통과한다.
# story_zcode_hook.js는 process.argv[2]로만 분배하고 hook_event_name을 비교하지 않는다. 그러면
# 세션 시작 컨텍스트 주입이 사라지거나 쓰기 후 검사가 잘못된 입력으로 아무것도 보고하지 않으므로 이벤트별 고정이 필수다.
EVENT_HANDLERS = {
    'SessionStart': {'session-start'},
    'PreToolUse': {'pre-tool-prose-guard', 'pre-tool-commit-advisory'},
    'PostToolUse': {'post-tool-prose-check'},
}
plugin = json.loads(Path('skills/story-setup/references/zcode/hooks/hooks.json').read_text())['hooks']
config = json.loads(Path('skills/story-setup/references/zcode/config.json.patch').read_text())['hooks']
assert config['enabled'] is True
assert set(plugin) == set(EVENT_HANDLERS)
assert set(config['events']) == set(plugin)
assert set(plugin) <= supported

def flatten(events):
    # 이벤트 이름도 추출해야 한다. 이벤트 키를 버리면 handler를 담당 이벤트에 다시 연결할 수 없다.
    return [(event, hook) for event, groups in events.items() for group in groups for hook in group['hooks']]

plugin_hooks = flatten(plugin)
workspace_hooks = flatten(config['events'])
assert len(plugin_hooks) == len(workspace_hooks) == 4
expected_routes = {(event, handler) for event, handlers in EVENT_HANDLERS.items() for handler in handlers}
# 등록 두 개를 각각 독립 대조한다. hooks.json만 바꾸고 config.json.patch를 안 바꾸거나 그 반대도 실패해야 한다.
# 둘은 별도 수동 관리하며 check-shared-files.sh는 의도적으로 hooks.json을 바이트 동등성에서 제외한다.
for source, pairs in (('hooks.json', plugin_hooks), ('config.json.patch', workspace_hooks)):
    for event, hook in pairs:
        assert set(hook) <= {'type', 'command', 'args', 'timeoutMs'}
        assert hook['type'] == 'process' and hook['command'] == 'node'
        assert hook['args'][1] in EVENT_HANDLERS[event], (
            f'{source}: {event} 路由到了错误的 handler', hook['args'][1], sorted(EVENT_HANDLERS[event]))
    routes = {(event, hook['args'][1]) for event, hook in pairs}
    assert routes == expected_routes, (
        f'{source}: event→handler 注册漂移', sorted(expected_routes - routes), sorted(routes - expected_routes))
post_groups = plugin['PostToolUse']
assert len(post_groups) == 1 and post_groups[0]['matcher'] == 'Bash|Write|Edit|ApplyPatch'
# 라우팅 테스트(runner 직접 호출로 matcher를 우회한 거짓 통과 방지): pre-tool-prose-guard matcher는 플러그인과
# 작업 공간 설정에서 같아야 하며 test-zcode-hooks가 전달할 모든 도구를 라우팅해야 한다. 여기에는
# ApplyPatch도 포함한다(본문 apply-patch 대상이 실제 matcher를 거쳐 handler에 전달돼야 하며 직접 호출 차단만으로 부족).
import re
def prose_guard_matcher(events):
    for group in events['PreToolUse']:
        if any(h['args'][1] == 'pre-tool-prose-guard' for h in group['hooks']):
            return group['matcher']
    return None
mc = prose_guard_matcher(config['events'])
mp = prose_guard_matcher(plugin)
assert mc is not None and mc == mp, ('pre-tool-prose-guard matcher drift between config and plugin', mc, mp)
for tool in ('Bash', 'Write', 'Edit', 'ApplyPatch'):
    assert re.search(mc, tool), ('pre-tool-prose-guard matcher does not route tool', tool, mc)
for _event, hook in plugin_hooks:
    assert hook['args'][0].startswith('${ZCODE_PLUGIN_ROOT}/')
for _event, hook in workspace_hooks:
    assert hook['args'][0] == '${ZCODE_PROJECT_DIR}/.zcode/hooks/story_zcode_hook.js'
PY
echo "  OK supported events + strict process-hook shape"

if grep -RqsE 'PreCompact|PostCompact|SessionEnd|SubagentStop|Notification' "$ROOT/hooks" "$ROOT/config.json.patch"; then
  fail "ZCode adapter contains unsupported hook events"
fi
[ ! -e "$ROOT/rules" ] || fail "ZCode has no .zcode/rules discovery surface"

assert_grep '\$story-long-write|\$story-setup' "$ROOT/AGENTS.md.tmpl" 'ZCode AGENTS template must document $skill invocation'
assert_grep 'target_cli = zcode|target_cli.*zcode' skills/story-setup/SKILL.md "story-setup must document zcode target_cli"
assert_grep 'references/deploy-zcode\.md' skills/story-setup/SKILL.md "story-setup entry must route zcode to its deploy file"
assert_grep 'references/zcode/config\.json\.patch' skills/story-setup/references/deploy-zcode.md "story-setup manifest missing ZCode config patch"
# 조합 설치 대리 검증(CI에 ZCode 런타임 없음): 플러그인 매니페스트와 작업 공간 설정이 같은 훅을 등록하므로
# 배포 알고리즘은 상호 배타성을 명시해야 한다(플러그인이 있으면 config 훅 병합 생략). 그렇지 않으면 PreToolUse/PostToolUse가 두 번 실행된다.
assert_grep 'hooks 互斥|훅 상호 배타' skills/story-setup/references/deploy-zcode.md "story-setup must document the plugin/workspace hooks mutex (skip config hooks merge when plugin installed, avoid double-firing)"
assert_grep '\.zcode/skills/story-setup/references/agent-references' skills/story-setup/references/deploy-zcode.md "story-setup missing ZCode reference path"
assert_grep '更新后的插件副本|갱신된 플러그인 사본' skills/story-setup/references/deploy-zcode.md "ZCode upgrade must choose the updated plugin setup, not its workspace snapshot"
assert_grep '更新后的插件副本|갱신된 플러그인 사본' skills/story-setup/UPGRADING.md "ZCode upgrade guide must explain the setup source priority"

python3 - <<'PY'
from pathlib import Path

# Markdown이 실행 계약이다. 이전 호스트 버전 판정이 실제 플러그인 등록 상태를 다시 우회하지 않도록 한다.
for skill in ('story', 'story-long-write', 'story-short-write', 'story-long-analyze', 'story-import', 'story-deslop', 'story-review'):
    path = Path('skills') / skill / 'SKILL.md'
    text = path.read_text(encoding='utf-8')
    assert 'ZCode' in text and any(s in text for s in ('插件', '플러그인')) and any(s in text for s in ('注册', '등록')), path
    assert 'ZCode 3.3.4' not in text, f'{path}: stale fixed-version solo routing'
deep = Path('skills/story-import/references/deep-analysis.md').read_text(encoding='utf-8')
assert '（或 ZCode）' not in deep, 'import must not override capability detection with host-based solo'
PY

echo "  OK deployment instructions + explicit capability boundaries"
echo ""
echo "OK: ZCode adapter checks passed"
