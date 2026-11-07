#!/usr/bin/env bash
# check-opencode-adapter.sh — OpenCode 어댑터 인터페이스의 결정론적 검사.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT="$REPO_ROOT/skills/story-setup/references/opencode"
TMP_DIR="$(mktemp -d)"
SYNC_LOG="$TMP_DIR/sync.log"
trap 'rm -rf "$TMP_DIR"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
assert_file() { [ -f "$1" ] || fail "required file missing: $1"; }
assert_dir() { [ -d "$1" ] || fail "required directory missing: $1"; }
assert_grep() { grep -Eq "$1" "$2" || fail "$3 ($2)"; }

cd "$REPO_ROOT"

echo "OpenCode adapter check"
echo "======================"
echo "Repo: $REPO_ROOT"

assert_dir "$ROOT"
assert_file "$ROOT/AGENTS.md.tmpl"
assert_file "$ROOT/plugin.ts"
assert_file "$ROOT/story_hook_core.js"
assert_dir "$ROOT/agents"
assert_dir "$ROOT/commands"
assert_file "scripts/sync-opencode.py"

# 생성 영역의 스냅샷으로 --check 자체의 읽기 전용 계약도 검증한다.
# 개발자의 작업 트리에 관련 없는 변경이 이미 있는 경우도 포함한다.
cp -R "$ROOT" "$TMP_DIR/opencode-before"
if ! python3 scripts/sync-opencode.py --check >"$SYNC_LOG" 2>&1; then
  cat "$SYNC_LOG" >&2 || true
  echo "::error::OpenCode templates are out of sync with Claude Code templates." >&2
  echo "::error::Run 'python3 scripts/sync-opencode.py' locally and commit the changes." >&2
  exit 1
fi
diff -qr "$TMP_DIR/opencode-before" "$ROOT" >/dev/null \
  || fail "sync-opencode.py --check modified generated files"

echo "  OK generated OpenCode templates are in sync (--check stayed read-only)"

python3 - "scripts/sync-opencode.py" "$TMP_DIR" <<'PY'
import importlib.util
import sys
from pathlib import Path

script_path = Path(sys.argv[1]).resolve()
tmp = Path(sys.argv[2]) / "opencode-transaction"
spec = importlib.util.spec_from_file_location("sync_opencode", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

src = tmp / "skills/story-setup/references/templates/agents"
templates = src.parent
dst_root = tmp / "skills/story-setup/references/opencode"
dst = dst_root / "agents"
src.mkdir(parents=True)
dst.mkdir(parents=True)
(templates / "CLAUDE.md.tmpl").write_text("valid instructions\n", encoding="utf-8")
(src / "a.md").write_text(
    "---\nname: a\ndescription: valid first fixture\ntools: [Read]\n---\nbody\n",
    encoding="utf-8",
)
(src / "b.md").write_text("missing frontmatter\n", encoding="utf-8")
(dst / "a.md").write_text("keep old a\n", encoding="utf-8")
(dst / "sentinel.md").write_text("keep sentinel\n", encoding="utf-8")
before = {path.name: path.read_bytes() for path in dst.iterdir()}
module.ROOT = tmp
old_argv = sys.argv
sys.argv = [str(script_path)]
try:
    module.main()
except ValueError:
    pass
else:
    raise SystemExit("sync-opencode must reject malformed agent source")
finally:
    sys.argv = old_argv
after = {path.name: path.read_bytes() for path in dst.iterdir()}
if after != before:
    raise SystemExit("sync-opencode modified destination before validating all sources")
PY

echo "  OK malformed source cannot partially update generated agents"

python3 - "scripts/sync-opencode.py" "$TMP_DIR" <<'PY'
import importlib.util
import sys
from pathlib import Path

script_path = Path(sys.argv[1]).resolve()
tmp = Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("sync_opencode_atomic", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def snapshot(root: Path) -> dict[str, tuple[str, bytes]]:
    result = {}
    if not root.exists():
        return result
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[rel] = ("symlink", str(path.readlink()).encode())
        elif path.is_dir():
            result[rel] = ("dir", b"")
        else:
            result[rel] = ("file", path.read_bytes())
    return result


def write_agent(path: Path, name: str) -> None:
    path.write_text(
        f"---\nname: {name}\ndescription: valid {name} fixture\ntools: [Read]\n---\n{name} body\n",
        encoding="utf-8",
    )


def run_normal(root: Path) -> None:
    old_root, old_argv = module.ROOT, sys.argv
    module.ROOT = root
    sys.argv = [str(script_path)]
    try:
        module.main()
    finally:
        module.ROOT = old_root
        sys.argv = old_argv


# 단계 간 실패: 유효한 에이전트 뒤에 CLAUDE.md.tmpl 누락이 발견돼도 OpenCode 어댑터 트리 전체는
# 바이트 단위로 변경되지 않아야 한다.
missing_root = tmp / "opencode-missing-agents-template"
missing_src = missing_root / "skills/story-setup/references/templates/agents"
missing_dst = missing_root / "skills/story-setup/references/opencode"
missing_src.mkdir(parents=True)
(missing_dst / "agents").mkdir(parents=True)
write_agent(missing_src / "a.md", "a")
(missing_dst / "agents/a.md").write_text("keep old a\n", encoding="utf-8")
(missing_dst / "plugin.ts").write_text("keep manual plugin\n", encoding="utf-8")
before = snapshot(missing_dst)
try:
    run_normal(missing_root)
except RuntimeError:
    pass
else:
    raise SystemExit("sync-opencode must reject a missing CLAUDE.md.tmpl")
if snapshot(missing_dst) != before:
    raise SystemExit("sync-opencode partially updated agents before CLAUDE.md.tmpl validation")


# 게시 실패: 대상의 b.md를 의도적으로 디렉터리로 둔다.
# 두 번째 에이전트 출력 실패가 앞의 a.md 갱신을 노출하거나
# AGENTS.md.tmpl/수동 OpenCode 자산을 변경하면 안 된다.
write_root = tmp / "opencode-write-failure"
write_src_root = write_root / "skills/story-setup/references/templates"
write_src = write_src_root / "agents"
write_dst = write_root / "skills/story-setup/references/opencode"
write_src.mkdir(parents=True)
(write_dst / "agents/b.md").mkdir(parents=True)
write_agent(write_src / "a.md", "a")
write_agent(write_src / "b.md", "b")
(write_src_root / "CLAUDE.md.tmpl").write_text("new instructions\n", encoding="utf-8")
(write_dst / "agents/a.md").write_text("keep old a\n", encoding="utf-8")
(write_dst / "AGENTS.md.tmpl").write_text("keep old instructions\n", encoding="utf-8")
(write_dst / "plugin.ts").write_text("keep manual plugin\n", encoding="utf-8")
before = snapshot(write_dst)
try:
    run_normal(write_root)
except (IsADirectoryError, OSError):
    pass
else:
    raise SystemExit("sync-opencode must fail when a generated target is a directory")
if snapshot(write_dst) != before:
    raise SystemExit("sync-opencode exposed a partial adapter update after a write failure")


# 첫 에이전트 커밋 뒤 두 번째 os.replace를 실패시킨다. 일반 예외 경로가
# 에이전트, AGENTS.md.tmpl, 수동 자산을 복원해야 한다.
commit_dst = tmp / "opencode-commit-failure"
(commit_dst / "agents").mkdir(parents=True)
(commit_dst / "agents/a.md").write_text("old a\n", encoding="utf-8")
(commit_dst / "agents/b.md").write_text("old b\n", encoding="utf-8")
(commit_dst / "AGENTS.md.tmpl").write_text("old instructions\n", encoding="utf-8")
(commit_dst / "plugin.ts").write_text("manual plugin\n", encoding="utf-8")
before = snapshot(commit_dst)
real_replace = module.os.replace
calls = 0

def fail_second_replace(src, dst):
    global calls
    calls += 1
    if calls == 2:
        raise OSError("injected second-commit failure")
    return real_replace(src, dst)

module.os.replace = fail_second_replace
try:
    module.publish_tree(
        {"a.md": "new a\n", "b.md": "new b\n"},
        "new instructions\n",
        commit_dst,
    )
except OSError:
    pass
else:
    raise SystemExit("sync-opencode did not surface injected commit failure")
finally:
    module.os.replace = real_replace
if snapshot(commit_dst) != before:
    raise SystemExit("sync-opencode failed to roll back an interrupted commit")


# opencode/agents에 복사된 심볼릭 링크가 준비 단계 쓰기를 외부/사용자 디렉터리로
# 돌리면 안 된다.
link_root = tmp / "opencode-symlink-parent"
link_src_root = link_root / "skills/story-setup/references/templates"
link_src = link_src_root / "agents"
link_dst = link_root / "skills/story-setup/references/opencode"
external = tmp / "opencode-external"
link_src.mkdir(parents=True)
link_dst.mkdir(parents=True)
external.mkdir()
write_agent(link_src / "a.md", "a")
(link_src_root / "CLAUDE.md.tmpl").write_text("instructions\n", encoding="utf-8")
(external / "a.md").write_text("external sentinel\n", encoding="utf-8")
(link_dst / "agents").symlink_to(external, target_is_directory=True)
before_external = snapshot(external)
try:
    run_normal(link_root)
except ValueError:
    pass
else:
    raise SystemExit("sync-opencode must reject a symlinked agents directory")
if snapshot(external) != before_external:
    raise SystemExit("sync-opencode followed agents symlink and modified external files")
PY

echo "  OK OpenCode generated-file failures roll back without replacing the adapter root"

# 오래된 생성 에이전트를 제거할 수 없어도(불변 플래그, 잠금, 읽기 전용 마운트)
# 롤백이 중단되면 안 된다. 복원 가능한 파일은 이전 바이트로 돌아가고
# 제거할 수 없는 파일은 내용을 유지하며 수동 자산도 그대로 남아야 한다.
python3 - "scripts/sync-opencode.py" "$TMP_DIR" <<'PY'
import importlib.util
import sys
from pathlib import Path

script_path = Path(sys.argv[1]).resolve()
root = Path(sys.argv[2]) / "opencode-immutable-stale"
agents = root / "agents"
agents.mkdir(parents=True)
(agents / "a.md").write_text("old a\n", encoding="utf-8")
(agents / "stale.md").write_text("old stale\n", encoding="utf-8")
(root / "AGENTS.md.tmpl").write_text("old instructions\n", encoding="utf-8")
(root / "plugin.ts").write_text("manual plugin\n", encoding="utf-8")


def snap() -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


before = snap()
spec = importlib.util.spec_from_file_location("sync_opencode_immutable", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

real_unlink = Path.unlink
real_copy2 = module.shutil.copy2
# 이름이 아닌 파일 자체 경로를 기준으로 장애를 주입한다. 실제 불변 파일도
# 읽기와 백업 디렉터리 복사는 허용하므로 stale.toml 자체를 대상으로 하는 쓰기/삭제만
# stale.md 자체를 대상으로 할 때만 실패해야 한다. 이름을 기준으로 하면
# 롤백 경로를 검사하기 전에 중단된다.
victim = (agents / "stale.md").resolve()


def blocked_unlink(self, *args, **kwargs):
    if self.resolve() == victim:
        raise PermissionError("simulated immutable stale file")
    return real_unlink(self, *args, **kwargs)


def blocked_copy2(src, dst, *args, **kwargs):
    if Path(dst).resolve() == victim:
        raise PermissionError("simulated immutable stale file")
    return real_copy2(src, dst, *args, **kwargs)


Path.unlink = blocked_unlink
module.shutil.copy2 = blocked_copy2
try:
    module.publish_tree({"a.md": "new a\n"}, "new instructions\n", root)
except PermissionError:
    pass
else:
    raise SystemExit("sync-opencode did not surface the un-removable stale file")
finally:
    Path.unlink = real_unlink
    module.shutil.copy2 = real_copy2
after = snap()
if after != before:
    raise SystemExit(
        f"sync-opencode rollback left a partial update past an un-removable file: {before} -> {after}"
    )
PY

echo "  OK OpenCode rollback survives an un-removable stale agent file"

python3 - <<'PY'
from pathlib import Path
expected = {
    'chapter-extractor', 'character-designer', 'consistency-checker',
    'narrative-writer', 'story-architect', 'story-explorer', 'story-researcher',
}
base = Path('skills/story-setup/references/opencode/agents')
found = {p.stem for p in base.glob('*.md')}
assert found == expected, found

# 각 에이전트 도구 사용 가능 여부(목록에 없는 도구 모두 제거 포함)는 아래 whollyDisabled 판정 행렬로 고정한다.
for p in sorted(base.glob('*.md')):
    text = p.read_text()
    assert text.startswith('---\n'), f'{p}: missing frontmatter'
    try:
        fm = text.split('---', 2)[1]
    except IndexError:
        raise AssertionError(f'{p}: malformed frontmatter')
    assert 'mode: subagent' in fm, f'{p}: missing mode: subagent'
    assert 'description:' in fm, f'{p}: missing description'
    assert '\npermission:' not in fm, f'{p}: legacy 1.x permission map'
    assert 'steps:' in fm, f'{p}: missing steps limit'
    assert '.claude/skills/story-setup/references/agent-references/' not in text, f'{p}: leaked Claude reference path'
    assert '.opencode/skills/story-setup/references/agent-references/' not in text, f'{p}: stale hidden OpenCode reference fallback'
    if p.stem in {'character-designer', 'consistency-checker', 'narrative-writer', 'story-architect'}:
        assert '{项目根}/skills/story-setup/references/agent-references/' in text, f'{p}: missing canonical OpenCode reference path'
PY

echo "  OK agent templates"

# 프런트매터 파싱은 한 줄을 단독 차지하는 `---`에 고정한다(값 안의 하이픈 3개로 permissions/steps가 잘리면 안 됨).
# disallowedTools의 Bash는 shell 전체 거부로 변환한다. OpenCode는 shell 권한을 명시하지 않으면 기본 허용하므로
# edit만 거부한 읽기 전용 에이전트도 shell 리디렉션으로 본문을 쓸 수 있다. 읽기 전용 명령 예외도 두지 않는다.
# 명령 허용 목록은 `( allowlisted-command ) > 본문.md` 같은 외부 리디렉션을 막지 못한다. 전체 거부만이 런타임에서
# shell 도구를 목록에서 제거할 수 있다.
python3 - "scripts/sync-opencode.py" <<'PY'
import importlib.util
import sys
from pathlib import Path

script_path = Path(sys.argv[1]).resolve()
spec = importlib.util.spec_from_file_location("sync_opencode_permissions", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

source = (
    "---\nname: a\ndescription: |\n  只读 agent --- 7 Gate。\n"
    "tools: [Read, Glob, Grep]\ndisallowedTools: [Write, Edit, Bash]\nmaxTurns: 9\n"
    "# 备注 --- 与主 skill 平级\n---\nbody\n"
)
fm, body = module.parse_frontmatter(source)
missing = {'name', 'description', 'tools', 'disallowedTools', 'maxTurns'} - set(fm)
assert not missing, f'frontmatter truncated at an inline ---: missing {missing}'
assert body.strip() == 'body', body

# 본문만 권한 근거이므로 body는 필수 인수다. 기본값을 주면 전달 누락이 조용한 권한 변경이 된다.
try:
    module.convert_claude_to_opencode(fm)
except TypeError:
    pass
else:
    raise AssertionError('convert_claude_to_opencode must require the agent body (no default)')

# 읽기 전용 에이전트 본문이 명령 실행을 요구하면 생성기는 명확히 실패해야 하며 shell 예외를 몰래 열면 안 된다.
try:
    module.convert_claude_to_opencode(
        fm, '**确定项目根目录：** 执行 `git rev-parse --show-toplevel`，失败则用当前工作目录。\n'
    )
except ValueError as error:
    assert 'git rev-parse --show-toplevel' in str(error), error
else:
    raise AssertionError('restricted agent instructions must not require Bash')

# 본문에 명령 언급 없음 → 아무것도 허용하지 않음(전체 deny가 런타임에서 shell 도구를 제거)
plain = module.convert_claude_to_opencode(fm, '只读 agent，正文没有任何 shell 步骤\n')
assert plain['permissions']['shell'] == 'deny', (
    f'read-only agent whose body never asks for a command must get a plain shell deny: {plain}'
)

# 생성기는 실행 불가 또는 권한이 뚫린 에이전트를 조용히 만들지 말고 **명확히 실패**해야 한다.
# 본문이 어떤 shell 명령이든 요구하면 생성을 중단하고 해당 명령을 지목해야 한다.
try:
    module.convert_claude_to_opencode(fm, '**准备环境：** 执行 `npm install`，然后开始检查。\n')
except ValueError as error:
    assert 'npm install' in str(error), error
else:
    raise AssertionError('generator must fail loudly when the body needs an ungranted command')


def rules_in_file_order(fm_text: str):
    """파일에 쓰인 순서대로 permissions 규칙을 가져온다. 순서가 우선순위이므로 dict/set을 쓰면 안 된다."""
    import re
    return re.findall(r'^  - action: "?([^"\n]+)"?\n    resource: "?([^"\n]+)"?\n    effect: (\S+)$', fm_text, re.M)


# format_frontmatter는 규칙을 정렬하면 안 된다. 넓은 deny가 먼저, 좁은 allow가 나중이라는 순서가
# 조용히 지워지기 때문이다. 역알파벳 삽입 순서로 검사한다.
probe = {'permissions': {'zzz': 'deny', '*': 'deny', 'aaa': 'allow'}}
probe_rules = rules_in_file_order(module.format_frontmatter(probe))
assert probe_rules == [('zzz', '*', 'deny'), ('*', '*', 'deny'), ('aaa', '*', 'allow')], (
    f'format_frontmatter reordered permission rules (must preserve dict order): {probe_rules}'
)

# 생성기 자체 출력: 읽기 전용 에이전트의 shell은 전체 deny여야 한다.
generated_rules = rules_in_file_order(module.format_frontmatter(plain))
assert ('shell', '*', 'deny') in generated_rules, generated_rules
PY

echo "  OK generator makes read-only Bash unavailable and rejects contradictory instructions"

# 생성 산출물의 **판정 행렬**. 상위 OpenCode 2.x 판정을 독립적으로 재현하며 sync-opencode.py의 파싱은
# 의도적으로 재사용하지 않는다. 재사용하면 재현 자체가 틀렸을 때 테스트도 함께 틀리기 때문이다.
#   core/src/tool.ts   whollyDisabled(): action이 일치하는 마지막 규칙에서 resource가 *이고 deny이면
#                      모델에 전달하는 목록에서 도구 전체를 뺀다. write/edit/patch는 action edit를 공유한다.
#   util/wildcard.ts   match()
# 실제 런타임 판정은 test-agent-permissions.py --opencode가 실제 CLI로 검사한다. 여기는 CLI 없는 정적 안전망이다.
python3 - <<'PY'
import re
from pathlib import Path


def wildcard_match(value: str, pattern: str) -> bool:
    escaped = re.sub(r'[.+^${}()|\[\]\\]', r'\\\g<0>', pattern)
    escaped = escaped.replace('*', '.*').replace('?', '.')
    return re.match('^' + escaped + '$', value, flags=re.DOTALL) is not None


def wholly_disabled(action: str, rules) -> bool:
    matched = [rule for rule in rules if wildcard_match(action, rule[0])]
    return bool(matched) and matched[-1][1] == '*' and matched[-1][2] == 'deny'


def rules_in_file_order(fm_text: str):
    return re.findall(r'^  - action: "?([^"\n]+)"?\n    resource: "?([^"\n]+)"?\n    effect: (\S+)$', fm_text, re.M)


# 도구 → 권한에서 대응하는 action(도구 options.permission, 기본값은 도구명)
TOOL_ACTION = {
    'read': 'read', 'glob': 'glob', 'grep': 'grep',
    'write': 'edit', 'edit': 'edit', 'patch': 'edit',
    'shell': 'shell', 'subagent': 'subagent', 'webfetch': 'webfetch', 'websearch': 'websearch',
    'skill': 'skill', 'question': 'question', 'execute': 'execute',
    # 표에 없는 도구(향후 추가 포함)는 첫 전체 deny만 제거할 수 있다.
    'unlisted-future-tool': 'unlisted-future-tool',
}
READ_LIKE = {'read', 'glob', 'grep'}
read_only = {'consistency-checker', 'story-explorer'}  # chapter-extractor는 배치 입력 파일을 쓰므로 더 이상 읽기 전용이 아니다.
shell_agents = {'narrative-writer', 'story-researcher'}
base = Path('skills/story-setup/references/opencode/agents')
for path in sorted(base.glob('*.md')):
    name = path.stem
    rules = rules_in_file_order(path.read_text(encoding='utf-8').split('\n---\n', 1)[0])
    available = {tool for tool, action in TOOL_ACTION.items() if not wholly_disabled(action, rules)}
    expected = set(READ_LIKE)
    if name not in read_only:
        expected |= {'write', 'edit', 'patch'}
    if name in shell_agents:
        expected |= {'shell'}
    assert available == expected, (
        f'{name}: tools left for the model {sorted(available)} != {sorted(expected)}'
        f'（rules in file order: {rules}）'
    )
PY

echo "  OK generated permissions leave each agent exactly its capability tools (2.x whollyDisabled)"

# Claude의 chapter-extractor는 인라인 훅(analysis-input-guard)으로 배치 입력 파일만 쓴다. OpenCode에는
# 에이전트별 훅이 없어 edit 경로 규칙으로 제한한다. 2.x permission.ts evaluate()를 독립 재현한다. action과
# resource가 모두 일치하는 마지막 규칙을 사용하며 resource는 세션 디렉터리 기준 경로다(file-access.ts resolve).
python3 - <<'PY'
import re
from pathlib import Path


def wildcard_match(value: str, pattern: str) -> bool:
    escaped = re.sub(r'[.+^${}()|\[\]\\]', r'\\\g<0>', pattern)
    escaped = escaped.replace('*', '.*').replace('?', '.')
    return re.match('^' + escaped + '$', value, flags=re.DOTALL) is not None


def evaluate(action: str, resource: str, rules) -> str:
    matched = [rule for rule in rules if wildcard_match(action, rule[0]) and wildcard_match(resource, rule[1])]
    return matched[-1][2] if matched else 'ask'


def rules_of(name: str):
    text = Path(f'skills/story-setup/references/opencode/agents/{name}.md').read_text(encoding='utf-8')
    return re.findall(r'^  - action: "?([^"\n]+)"?\n    resource: "?([^"\n]+)"?\n    effect: (\S+)$',
                      text.split('\n---\n', 1)[0], re.M)


extractor = rules_of('chapter-extractor')
# 2.x Wildcard.match는 *를 .*와 s 플래그로 컴파일해 여러 디렉터리 계층을 넘는다(로컬 opencode 바이너리에서 확인).
for path in ('작품분석실/书/_analysis_cache/输入-RAW-4-6.md', '작품분석실/书/_analysis_cache/输入-REUSE-1-3.md',
             '_analysis_cache/输入-RAW-1-3.md', '作品/작품분석실/书/_analysis_cache/输入-RAW-7-9.md'):
    assert evaluate('edit', path, extractor) == 'allow', (path, extractor)
for path in ('작품분석실/书/장별분석/제4장_요약.md', '작품분석실/书/_analysis_cache/批次-RAW-4-6.md',
             '작품분석실/书/_progress.md', 'book/본문/제1장.md', '작품분석실/书/_analysis_cache/输入.md'):
    assert evaluate('edit', path, extractor) == 'deny', (path, extractor)
for name in ('character-designer', 'narrative-writer', 'story-architect'):
    assert evaluate('edit', 'book/본문/제1장.md', rules_of(name)) == 'allow', name
PY

echo "  OK chapter-extractor may only edit _analysis_cache/输入-{RAW|REUSE}-*.md (2.x evaluate)"

# 보호 훅 이름을 파싱할 수 없으면 차단한다. 프런트매터에 Write/Edit PreToolUse 훅이 있는데 명령 형식 변경으로
# 이름을 인식하지 못하면 생성 오류를 내야 한다. 보호가 없다고 간주해 작업 공간 전체 edit를 허용하면 안 된다.
python3 - "scripts/sync-opencode.py" <<'PY'
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("sync_opencode_guard", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def frontmatter(command: str, matcher: str = "Write|Edit") -> str:
    return ("---\nname: x\ntools: [Read, Write, Edit]\nhooks:\n  PreToolUse:\n"
            f"    - matcher: \"{matcher}\"\n      hooks:\n        - type: command\n"
            f"          command: {command}\n---\n\n正文\n")

known = 'node "$CLAUDE_PROJECT_DIR"/.claude/hooks/story_hook_cli.js analysis-input-guard'
assert module.frontmatter_write_guard(frontmatter(known)) == "analysis-input-guard"
for command in ('node "$CLAUDE_PROJECT_DIR/.claude/hooks/story_hook_cli.js" analysis-input-guard',
                'bash "$CLAUDE_PROJECT_DIR"/.claude/hooks/guard-analysis-input.sh'):
    for matcher in ("Write|Edit", "Edit", "Write"):
        try:
            module.frontmatter_write_guard(frontmatter(command, matcher))
        except ValueError:
            continue
        raise AssertionError(f"unrecognized write-guard hook must fail closed: {matcher} / {command}")
# CRLF 템플릿도 보호 이름을 인식해야 한다. 인식 불가 시 차단하며 `\n---\n`을 못 찾았다고 훅 없음으로 간주하지 않는다.
assert module.frontmatter_write_guard(frontmatter(known).replace("\n", "\r\n")) == "analysis-input-guard"
unknown = 'bash "$CLAUDE_PROJECT_DIR"/.claude/hooks/guard-analysis-input.sh'
# matcher의 `*`, 빈 값, 전체 생략 모두 Write/Edit를 포함하며 CRLF에서도 같다.
cases = [frontmatter(unknown, "*"), frontmatter(unknown, ""), frontmatter(unknown).replace("\r\n", "\n").replace("\n", "\r\n"),
         frontmatter(unknown, "*").replace("\n", "\r\n"),
         frontmatter(unknown).replace('    - matcher: "Write|Edit"\n', "    -\n")]
for text in cases:
    try:
        module.frontmatter_write_guard(text)
    except ValueError:
        continue
    raise AssertionError(f"write hook with wildcard/CRLF matcher must fail closed: {text!r}")
# Bash 등 비쓰기 matcher만 있는 훅과 훅 없는 에이전트는 영향받지 않는다.
assert module.frontmatter_write_guard(frontmatter('bash x.sh', "Bash")) is None
assert module.frontmatter_write_guard("---\nname: x\ntools: [Read]\n---\n\n正文\n") is None
PY

echo "  OK unrecognized Write/Edit hook in agent frontmatter fails generation (no silent edit allow)"

# 생성은 멱등적이어야 한다. 두 번 실행한 결과가 같아야 템플릿 변경 없이 --check가 무작위 동기화 오류를 내지 않는다.
python3 - "scripts/sync-opencode.py" "$TMP_DIR" <<'PY'
import contextlib
import importlib.util
import io
import shutil
import sys
from pathlib import Path

script_path = Path(sys.argv[1]).resolve()
root = Path(sys.argv[2]) / "opencode-idempotent"
spec = importlib.util.spec_from_file_location("sync_opencode_idempotent", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

src = Path("skills/story-setup/references")
dst = root / "skills/story-setup/references"
dst.mkdir(parents=True)
shutil.copytree(src / "templates", dst / "templates")
shutil.copytree(src / "opencode", dst / "opencode")


def snapshot() -> dict[str, bytes]:
    base = dst / "opencode"
    return {
        path.relative_to(base).as_posix(): path.read_bytes()
        for path in sorted(base.rglob("*"))
        if path.is_file()
    }


def run() -> None:
    old_root, old_argv = module.ROOT, sys.argv
    module.ROOT = root
    sys.argv = [str(script_path)]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            module.main()
    finally:
        module.ROOT, sys.argv = old_root, old_argv


run()
first = snapshot()
run()
second = snapshot()
if first != second:
    drift = sorted(key for key in set(first) | set(second) if first.get(key) != second.get(key))
    raise SystemExit(f"sync-opencode.py is not idempotent; drifting files: {drift}")
PY

echo "  OK generation is idempotent (second run is byte-identical)"

python3 - <<'PY'
from pathlib import Path
skill_names = {p.parent.name for p in Path('skills').glob('*/SKILL.md')}
command_names = {p.stem for p in Path('skills/story-setup/references/opencode/commands').glob('*.md')}
assert skill_names == command_names, f'missing={skill_names-command_names}, extra={command_names-skill_names}'
for p in sorted(Path('skills/story-setup/references/opencode/commands').glob('*.md')):
    text = p.read_text()
    assert text.startswith('---\n'), f'{p}: missing frontmatter'
    fm = text.split('---', 2)[1]
    assert 'description:' in fm, f'{p}: missing description'
    assert any(s in text for s in (f'请使用 {p.stem} skill', f'{p.stem} 스킬로')), f'{p}: command body must route to same skill'
    # OpenCode는 템플릿에 $ARGUMENTS와 $1..$N이 모두 없을 때만 사용자 인수를 끝에 붙인다.
    # 이 대체 동작은 공식 문서에 없다(opencode.ai/docs/commands는 자리표시자만 설명).
    # 1.14.32 실측에서는 일반 텍스트 한 줄로 추가된다. 자리표시자를 명시해야 ZCode와 같고 미문서화 동작에 의존하지 않는다.
    assert '$ARGUMENTS' in text, f'{p}: command template must place $ARGUMENTS explicitly'

# command 인터페이스가 있는 두 어댑터를 일치시키고 어느 쪽이든 누락하면 차단한다.
zcode_dir = Path('skills/story-setup/references/zcode/commands')
if zcode_dir.is_dir():
    zcode_names = {p.stem for p in zcode_dir.glob('*.md')}
    assert zcode_names == command_names, f'opencode/zcode command sets differ: only_zcode={zcode_names-command_names}, only_opencode={command_names-zcode_names}'
    for p in sorted(zcode_dir.glob('*.md')):
        assert '$ARGUMENTS' in p.read_text(), f'{p}: command template must place $ARGUMENTS explicitly'
PY

echo "  OK slash command templates (含 \$ARGUMENTS 占位符与 ZCode 对齐)"

# 이 작업에는 opencode CLI가 없다(실제 로드는 test-opencode-cli-e2e.sh에서 단언). 따라서 구조로 대신 검사한다.
# 배포 매니페스트는 코어를 반드시 .opencode/plugins/lib/에 두고 .opencode/plugins/ 바로 아래에는 두지 않는다.
# (바로 아래 *.js는 OpenCode가 고장 난 두 번째 플러그인으로 자동 로드한다.)
assert_grep '\.opencode/plugins/lib/story_hook_core\.js' "$REPO_ROOT/skills/story-setup/references/deploy-opencode.md" "OpenCode deploy manifest must target .opencode/plugins/lib/story_hook_core.js, not a flat .opencode/plugins/story_hook_core.js"
# 버전 검사는 불확실하면 차단한다. 1.x에서는 플러그인이 로드되지 않고 에이전트의 `permissions:` 규칙도
# 무시돼 읽기 전용 에이전트에 write/shell이 허용된다. 따라서 알 수 없는 버전에서는 중단해야 하며
# 차단된 OpenCode 단독 배포는 `.story-deployed`를 건드리지 않아야 한다.
# story-setup 진입점은 호스트별 배포 파일 하나만 읽는다. deploy-opencode.md로 연결하며 버전 검사와 모델 설정도 그 파일에 둔다.
assert_grep 'references/deploy-opencode\.md' "$REPO_ROOT/skills/story-setup/SKILL.md" "story-setup entry must route opencode to its deploy file"
SETUP_MD="$REPO_ROOT/skills/story-setup/references/deploy-opencode.md"
assert_grep '命令不可用或解析不出版本 → 同样停止 OpenCode 部署|명령을 사용할 수 없거나 버전을 해석하지 못해도 OpenCode 배포를 중단한다' "$SETUP_MD" "OpenCode version gate must stop when the version cannot be determined"
assert_grep 'target 只有 opencode 则不写、不更新 `\.story-deployed`|target이 opencode뿐이면 `\.story-deployed`를 만들거나 갱신하지 않고' "$SETUP_MD" "blocked OpenCode-only deploy must not write or bump .story-deployed"
if grep -Eq '解析不出版本 → 继续部署|버전을 해석하지 못해도 OpenCode 배포를 계속한다' "$SETUP_MD"; then fail "OpenCode version gate must not continue on an unknown version"; fi
# 모델 캐시는 .opencode/agents/ 교체 전에 저장해야 한다. 그렇지 않으면 사용자의 model:이 덮인 뒤 빈 값이 캐시된다.
assert_grep '先缓存已有模型配置|기존 모델 설정부터 캐시한다' "$SETUP_MD" "OpenCode deploy must cache existing agent models before replacing .opencode/agents/"
# 작가에게 모델을 물을 때는 역할명(작품 분석 도우미/집필자/총괄)을 사용하고 내부 에이전트 이름은 기술 비고 열에만 둔다.
assert_grep '拆书助手|분석 보조' "$SETUP_MD" "OpenCode model questions must name roles the author understands"
# Python으로 문자 단위 일치를 확인한다. C 로캘의 grep [^」]는 바이트 집합이라 같은 바이트를 가진 한자도 잘못 제외해 누락된다.
python3 - "$SETUP_MD" <<'PY' || fail "OpenCode model questions must not show internal agent names to the author"
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
internal = r"chapter-extractor|consistency-checker|story-explorer|story-researcher|character-designer|narrative-writer|story-architect"
hits = [q for q in re.findall(r"「[^」]*」|‘[^’]*’", text) if re.search(internal, q)]
if hits:
    print("internal agent names inside author-facing quotes: {}".format(hits), file=sys.stderr)
    sys.exit(1)
PY
assert_grep 'permissions:` (规则列表|규칙 목록)' "$REPO_ROOT/skills/story-review/SKILL.md" "story-review must validate OpenCode 2.x agents by their permissions: list"
# #242: 런타임 동작 테스트. 배포된 코어 구조(lib/)에 맞춰 plugin.ts를 로드하고
# ctx.location, execute.before/after, 압축 훅을 실행한다. 코어의 바이트 일치는
# check-shared-files.sh가, 검사망/보호 의미는 test-prose-net-parity.sh가 검증한다.
node --experimental-strip-types scripts/test-opencode-plugin.mjs
assert_grep 'AGENTS\.md|OpenCode' "$ROOT/AGENTS.md.tmpl" "OpenCode AGENTS template must be present"
assert_grep 'story-long-write|story-short-write|story-review' "$ROOT/AGENTS.md.tmpl" "OpenCode AGENTS template must mention story skill routing"

echo "  OK plugin behavior and instruction anchors"
echo ""
echo "OK: OpenCode adapter checks passed"
