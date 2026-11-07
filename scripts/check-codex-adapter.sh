#!/usr/bin/env bash
# check-codex-adapter.sh — Codex 어댑터 인터페이스의 결정론적 검사.
#
# 여기서 Codex 지원은 저장소 스킬 탐색(.agents/skills 심볼릭 링크)과
# `$story-setup` 프로젝트 배포(.codex/agents + .codex/hooks)로 구성된다.
# 실제 플러그인 패키지는 없다. 에이전트 TOML은 Claude 에이전트 템플릿으로부터
# scripts/generate-codex-agents.py가 생성한다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
assert_file() { [ -f "$1" ] || fail "required file missing: $1"; }
assert_path() { [ -e "$1" ] || fail "required path missing: $1"; }
assert_grep() { grep -Eq "$1" "$2" || fail "$3 ($2)"; }

cd "$REPO_ROOT"

echo "Codex adapter check"
echo "==================="
echo "Repo: $REPO_ROOT"

CODEX_DIR="skills/story-setup/references/codex"
assert_path ".agents/skills"
assert_file "$CODEX_DIR/AGENTS.md.tmpl"
assert_file "$CODEX_DIR/hooks/hooks.json"
assert_file "$CODEX_DIR/hooks/story_codex_hook.py"
assert_file "$CODEX_DIR/hooks/run-story-hook.sh"
assert_file "$CODEX_DIR/hooks/run-story-hook.cmd"
assert_path "$CODEX_DIR/agents"
assert_file "scripts/generate-codex-agents.py"
assert_file "scripts/generate-codex-hooks.py"
assert_file "scripts/test-codex-hook-merge.py"
assert_file "skills/story-setup/scripts/merge-codex-hooks.py"

python3 -m json.tool "$CODEX_DIR/hooks/hooks.json" >/dev/null
python3 - <<'PY'
from pathlib import Path
for name in (
    'scripts/generate-codex-agents.py',
    'scripts/generate-codex-hooks.py',
    'skills/story-setup/references/codex/hooks/story_codex_hook.py',
):
    compile(Path(name).read_text(encoding='utf-8'), name, 'exec')
PY
python3 scripts/generate-codex-hooks.py --check
python3 scripts/test-codex-hook-merge.py

echo "  OK JSON/Python syntax"

# Windows 인코딩 안전성(이슈 #164 유형): 훅은 중국어 본문/细纲을 표준 입출력으로 전달하므로
# Windows ANSI 코드 페이지 텍스트 스트림 대신 UTF-8 바이트를 사용해야 한다.
HOOK_PY="$CODEX_DIR/hooks/story_codex_hook.py"
# 줄 검색 대신 AST를 순회한다. 줄 단위 read_text(/encoding= 쌍 검사는 양방향으로 잘못된다.
# 두 줄로 나뉜 올바른 호출이나 .read_text()를 언급한 주석을 회귀 오류로 보고하며,
# `p.read_text() + p.read_text(encoding="utf-8")[:0]`는 줄 어딘가에 encoding 토큰이 있다는 이유로
# 허용한다. AST는 주석을 보지 않고 호출을 확인한다.
python3 - "$HOOK_PY" <<'PY'
import ast
import sys
from pathlib import Path

path = Path(sys.argv[1])
tree = ast.parse(path.read_text(encoding="utf-8"), str(path))


def dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


required = {"sys.stdin.buffer.read", "sys.stdout.buffer.write"}
seen = set()
problems = []
for node in ast.walk(tree):
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        continue
    name = dotted(node.func)
    if name in required:
        seen.add(name)
    if name in ("sys.stdin.read", "sys.stdout.write"):
        problems.append(f"line {node.lineno}: text-mode {name}() (Windows ANSI hazard)")
    if node.func.attr == "read_text" and not any(kw.arg == "encoding" for kw in node.keywords):
        problems.append(f"line {node.lineno}: read_text() without encoding='utf-8' (Windows ANSI hazard)")
for name in sorted(required - seen):
    problems.append(f"missing UTF-8 byte stdio call: {name}()")
if problems:
    raise SystemExit("FAIL: Codex hook Windows encoding safety (issue #164):\n  " + "\n  ".join(problems))
PY

echo "  OK Windows encoding safety (UTF-8 stdio + file reads)"

# .agents/skills는 skills/에 대한 상대 심볼릭 링크(Codex가 스캔하는 agentskills.io 경로)이므로
# 스킬 복사본은 따로 없다. 유효한 상대 링크여야 한다. 잘못된 링크나 절대 링크
# (openai/codex#11314), Windows의 링크 대신 텍스트 스텁은 탐색을 조용히 망가뜨린다.
[ -L ".agents/skills" ] || fail ".agents/skills must be a symlink (got a regular file/dir; on Windows enable git core.symlinks)"
target="$(readlink .agents/skills)"
[ "$target" = "../skills" ] || fail ".agents/skills symlink target must be relative '../skills', got '$target'"
skill_count="$(find skills -maxdepth 2 -name SKILL.md | wc -l | tr -d ' ')"
[ "$skill_count" = "14" ] || fail "expected 14 skills, found $skill_count"
for skill in skills/*/SKILL.md; do
  name="$(basename "$(dirname "$skill")")"
  assert_file ".agents/skills/$name/SKILL.md"
done

echo "  OK .agents/skills discovery symlink ($skill_count skills)"

# 사용자 지정 에이전트 TOML은 Claude 템플릿으로부터 결정론적으로 생성한다.
python3 scripts/generate-codex-agents.py --dest "$TMP_DIR/agents" >/dev/null
diff -qr "$TMP_DIR/agents" "$CODEX_DIR/agents" >/dev/null \
  || fail "generated Codex agents are stale; run scripts/generate-codex-agents.py"
if grep -RInE '当前 Claude 部署|(^|[^[:alnum:]_])/story(-[a-z0-9-]+)?' "$CODEX_DIR/agents"; then
  fail "generated Codex agents must use Codex platform wording and \$story* invocations"
fi

# 원본이 없거나 비어 있으면 대상을 건드리기 전에 실패해야 한다. 그렇지 않으면
# --source 오타가 모든 생성 TOML을 조용히 삭제하고도 성공을 반환한다.
mkdir -p "$TMP_DIR/empty-source" "$TMP_DIR/safe-dest"
printf 'keep\n' > "$TMP_DIR/safe-dest/sentinel.toml"
if python3 scripts/generate-codex-agents.py \
  --source "$TMP_DIR/empty-source" --dest "$TMP_DIR/safe-dest" >/dev/null 2>&1; then
  fail "Codex generator must reject an empty source directory"
fi
assert_file "$TMP_DIR/safe-dest/sentinel.toml"

# 뒤쪽 원본이 잘못된 경우에도 앞쪽의 유효한 원본을 쓰기 전에 실패해야 한다.
# 이를 통해 전체 검증 후 쓰기라는 생성기 동작을 고정한다.
mkdir -p "$TMP_DIR/malformed-source" "$TMP_DIR/transactional-dest"
cat >"$TMP_DIR/malformed-source/a.md" <<'EOF'
---
name: a
description: valid first fixture
---
body
EOF
printf 'missing frontmatter\n' >"$TMP_DIR/malformed-source/b.md"
printf 'keep old a\n' >"$TMP_DIR/transactional-dest/a.toml"
printf 'keep sentinel\n' >"$TMP_DIR/transactional-dest/sentinel.toml"
cp -R "$TMP_DIR/transactional-dest" "$TMP_DIR/transactional-before"
if python3 scripts/generate-codex-agents.py \
  --source "$TMP_DIR/malformed-source" \
  --dest "$TMP_DIR/transactional-dest" >/dev/null 2>&1; then
  fail "Codex generator must reject malformed agent source"
fi
diff -qr "$TMP_DIR/transactional-before" "$TMP_DIR/transactional-dest" >/dev/null \
  || fail "Codex generator modified destination before validating all sources"

# 뒤쪽 렌더링 파일을 게시할 때 파일시스템 오류가 발생해도 앞쪽 갱신이 노출되면 안 된다.
# b.toml을 디렉터리로 두어 a.toml이 준비된 뒤 두 번째 쓰기가
# 실패하도록 한다.
mkdir -p "$TMP_DIR/write-failure-source" "$TMP_DIR/write-failure-dest/b.toml"
cat >"$TMP_DIR/write-failure-source/a.md" <<'EOF'
---
name: a
description: valid first fixture
---
new a body
EOF
cat >"$TMP_DIR/write-failure-source/b.md" <<'EOF'
---
name: b
description: valid second fixture
---
new b body
EOF
printf 'keep old a\n' > "$TMP_DIR/write-failure-dest/a.toml"
printf 'keep manual asset\n' > "$TMP_DIR/write-failure-dest/manual.txt"
cp -R "$TMP_DIR/write-failure-dest" "$TMP_DIR/write-failure-before"
if python3 scripts/generate-codex-agents.py \
  --source "$TMP_DIR/write-failure-source" \
  --dest "$TMP_DIR/write-failure-dest" >/dev/null 2>&1; then
  fail "Codex generator must fail when a generated target is a directory"
fi
diff -qr "$TMP_DIR/write-failure-before" "$TMP_DIR/write-failure-dest" >/dev/null \
  || fail "Codex generator exposed a partial update after a destination write failure"

# 두 번째 원자적 커밋(a.toml 교체 이후)에도 실패를 주입하여 롤백이
# 생성된 모든 바이트를 복원하는지 확인하고, 다음 항목도 보존하는지 확인한다.
# 대상 디렉터리의 관련 없는 파일도 유지해야 한다.
python3 - "scripts/generate-codex-agents.py" "$TMP_DIR" <<'PY'
import importlib.util
import sys
from pathlib import Path

script = Path(sys.argv[1]).resolve()
dest = Path(sys.argv[2]) / "codex-commit-failure"
dest.mkdir()
(dest / "a.toml").write_text("old a\n", encoding="utf-8")
(dest / "b.toml").write_text("old b\n", encoding="utf-8")
(dest / "manual.txt").write_text("manual\n", encoding="utf-8")
before = {path.name: path.read_bytes() for path in dest.iterdir()}
spec = importlib.util.spec_from_file_location("generate_codex_atomic", script)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
real_replace = module.os.replace
calls = 0

def fail_second(src, dst):
    global calls
    calls += 1
    if calls == 2:
        raise OSError("injected second-commit failure")
    return real_replace(src, dst)

module.os.replace = fail_second
try:
    module.publish_rendered({"a.toml": "new a\n", "b.toml": "new b\n"}, dest)
except OSError:
    pass
else:
    raise SystemExit("Codex publisher did not surface injected commit failure")
after = {path.name: path.read_bytes() for path in dest.iterdir()}
if after != before:
    raise SystemExit("Codex publisher failed to roll back an interrupted commit")
PY

# 이전 생성 파일을 제거할 수 없어도(불변 플래그, 잠금, 읽기 전용 마운트)
# 롤백이 중단되면 안 된다. 복원 가능한 파일은 모두 이전 바이트로 돌아가고
# 제거할 수 없는 파일은 원래 내용을 유지해야 한다.
python3 - "scripts/generate-codex-agents.py" "$TMP_DIR" <<'PY'
import importlib.util
import sys
from pathlib import Path

script = Path(sys.argv[1]).resolve()
dest = Path(sys.argv[2]) / "codex-immutable-stale"
dest.mkdir()
(dest / "a.toml").write_text("old a\n", encoding="utf-8")
(dest / "stale.toml").write_text("old stale\n", encoding="utf-8")
(dest / "manual.txt").write_text("manual\n", encoding="utf-8")
before = {path.name: path.read_bytes() for path in dest.iterdir()}
spec = importlib.util.spec_from_file_location("generate_codex_immutable", script)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

real_unlink = Path.unlink
real_copy2 = module.shutil.copy2
# 이름이 아닌 파일 자체 경로를 기준으로 장애를 주입한다. 실제 불변 파일도
# 읽기와 백업 디렉터리 복사는 허용하므로 stale.toml 자체를 대상으로 하는 쓰기/삭제만
# 실패해야 한다. 이름을 기준으로 하면 백업 복사도 막아
# 롤백 경로를 검사하기 전에 중단된다.
victim = (dest / "stale.toml").resolve()


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
    module.publish_rendered({"a.toml": "new a\n"}, dest)
except PermissionError:
    pass
else:
    raise SystemExit("Codex publisher did not surface the un-removable stale file")
finally:
    Path.unlink = real_unlink
    module.shutil.copy2 = real_copy2
after = {path.name: path.read_bytes() for path in dest.iterdir()}
if after != before:
    raise SystemExit(
        f"Codex rollback left a partial update past an un-removable file: {before} -> {after}"
    )
PY

# 에이전트 이름은 출력 파일명이 된다. 경로처럼 생기거나 파일명과 불일치하는 이름은
# 준비 단계 전에 거부해 악의적이거나 오타가 있는 프런트매터가 --dest 밖으로 벗어나지 못하게 한다.
mkdir -p "$TMP_DIR/escape-source" "$TMP_DIR/escape-dest"
cat >"$TMP_DIR/escape-source/safe.md" <<'EOF'
---
name: ../victim
description: must be rejected
---
body
EOF
printf 'outside sentinel\n' > "$TMP_DIR/victim.toml"
if python3 scripts/generate-codex-agents.py \
  --source "$TMP_DIR/escape-source" \
  --dest "$TMP_DIR/escape-dest" >/dev/null 2>&1; then
  fail "Codex generator must reject path-like agent names"
fi
[ "$(cat "$TMP_DIR/victim.toml")" = "outside sentinel" ] \
  || fail "Codex generator let an agent name escape the destination"
[ -z "$(find "$TMP_DIR/escape-dest" -mindepth 1 -print -quit)" ] \
  || fail "Codex generator touched the destination for an invalid agent name"

python3 - <<'PY'
try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        from pip._vendor import tomli as tomllib
from pathlib import Path
expected = {
    'chapter-extractor', 'character-designer', 'consistency-checker',
    'narrative-writer', 'story-architect', 'story-explorer', 'story-researcher',
}
read_only = {'consistency-checker', 'story-explorer'}  # chapter-extractor는 배치 입력 파일을 쓰므로 더 이상 읽기 전용이 아니다.
found = set()
for path in sorted(Path('skills/story-setup/references/codex/agents').glob('*.toml')):
    data = tomllib.loads(path.read_text(encoding='utf-8'))
    for key in ('name', 'description', 'developer_instructions'):
        assert data.get(key), f'{path}: missing {key}'
    name = data['name']
    instructions = data['developer_instructions']
    assert path.name == f'{name}.toml', f'{path}: filename/name mismatch'
    assert '.codex/skills/story-setup/references/agent-references/' in instructions
    for stale in ('.claude/skills/', '.opencode/skills/', '{项目根}/skills/story-setup/references/agent-references/'):
        assert stale not in instructions, f'{path}: stale cross-CLI reference fallback {stale}'
    assert 'agent_type' in instructions, f'{path}: missing Codex agent_type guidance'
    assert 'subagent_type' not in instructions, f'{path}: leaked Claude subagent_type wording'
    assert 'unknown agent_type' in instructions, f'{path}: missing runtime fallback guidance'
    if name in read_only:
        assert data.get('sandbox_mode') == 'read-only', f'{path}: expected read-only sandbox'
    found.add(name)
assert found == expected, found
PY

echo "  OK Codex custom-agent TOML (schema + generator determinism)"

# 생성 등록은 루트 탐색과 이벤트 라우팅만 담당한다. 인터프리터 탐색과 훅 분배는
# JSON 명령 6개에 복사하지 않고 플랫폼별 실행기 하나에 둔다.
assert_grep 'for candidate in python3 python py' "$CODEX_DIR/hooks/run-story-hook.sh" "POSIX launcher must probe Python interpreters"
assert_grep 'for %%P in \(python3 python py\) do' "$CODEX_DIR/hooks/run-story-hook.cmd" "Windows launcher must probe the current interpreter list"
assert_grep 'set "PYBIN=%%P"' "$CODEX_DIR/hooks/run-story-hook.cmd" "Windows launcher must retain the first working interpreter"
if grep -q 'git rev-parse' "$CODEX_DIR/hooks/hooks.json" "$CODEX_DIR/hooks/run-story-hook.sh" "$CODEX_DIR/hooks/run-story-hook.cmd"; then
  fail "deployment hooks must not require git to launch story_codex_hook.py"
fi

# 모든 실행기는 (a) 확인된 루트를 Python에 전달하고(CODEX_PROJECT_DIR=$PROJECT_ROOT)
# (b) 훅 파일이 없으면 아무 작업도 하지 않아야 한다. root="/"일 때 "//.codex/..."를 실행하면 안 된다.
# Python 훅도 __file__ 기준으로 자기 위치를 찾아 Git Bash MSYS 루트가 Windows에서 해석되도록 한다.
#
# 각 등록의 이벤트 토큰은 소비자 세 곳의 허용 목록과 각각 일치해야 한다. run-story-hook.sh의 case,
# run-story-hook.cmd의 if /I 연결, story_codex_hook.py main()의 분배 중 하나라도 빠지면 훅이 영구히 작동하지 않는다.
# (실행기 case가 *) exit 2로 빠지고 표준 출력/오류가 비게 된다.) command↔commandWindows 일치 단언만으로는
# 같은 오타를 복사했음을 증명할 뿐이다. 다섯 번째 목록을 복사하지 말고 소비자 세 곳에서 목록을 파싱해 비교한다.
python3 - "$CODEX_DIR/hooks/hooks.json" "$CODEX_DIR/hooks/story_codex_hook.py" \
  "$CODEX_DIR/hooks/run-story-hook.sh" "$CODEX_DIR/hooks/run-story-hook.cmd" <<'PY'
import json, re, sys
from pathlib import Path
hooks = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["hooks"]
all_hooks = [h for arr in hooks.values() for blk in arr for h in blk["hooks"]]
assert all_hooks, "no launcher commands found"
registered = []
for h in all_hooks:
    c = h["command"]
    assert '.codex/hooks/run-story-hook.sh' in c, f"POSIX command must route through the shared launcher: {c}"
    assert 'python3 python py' not in c and 'story_codex_hook.py' not in c, f"registration duplicated launcher logic: {c}"
    w = h.get("commandWindows")
    assert w, f"hook missing commandWindows (Windows = cmd.exe /C): {c[:60]}"
    assert "run-story-hook.cmd" in w and "powershell -NoProfile" in w, f"Windows command must locate the shared launcher: {w}"
    assert "story_codex_hook.py" not in w and "python3" not in w, f"Windows registration duplicated launcher logic: {w}"
    posix_event = c.rsplit(" ", 1)[-1]
    assert f"'{posix_event}'" in w, f"command/commandWindows event mismatch: {posix_event} vs {w}"
    registered.append(posix_event)

# 같은 handler가 두 번 등록되면 블록 복사 후 이벤트 토큰 수정을 잊어 다른 이벤트 등록이 빠진 것이다.
dupes = sorted({e for e in registered if registered.count(e) > 1})
assert not dupes, f"hooks.json registers the same event token more than once: {dupes}"

launcher_sh = Path(sys.argv[3]).read_text(encoding="utf-8")
launcher_cmd = Path(sys.argv[4]).read_text(encoding="utf-8")
hook_py = Path(sys.argv[2]).read_text(encoding="utf-8")

# case "$EVENT" in ... esac 구간의 분기만 모으고 각 a|b|c를 모두 펼친다.
# PYBIN 탐색 등 다른 case는 목록을 오염시키지 않으며 분기를 한 줄씩 쓴 목록도 파싱한다.
case_block = re.search(r'case[ \t]+"\$EVENT"[ \t]+in(.*?)esac', launcher_sh, re.S)
assert case_block, 'run-story-hook.sh must gate "$EVENT" with a case allowlist'
sh_tokens = set()
for arm in re.findall(r'^[ \t]*([a-z0-9|-]+)\)', case_block.group(1), re.M):
    sh_tokens.update(arm.split("|"))
allowed = {
    "run-story-hook.sh": sh_tokens,
    "run-story-hook.cmd": set(re.findall(r'"%EVENT%"=="([a-z0-9-]+)"', launcher_cmd)),
    "story_codex_hook.py": set(re.findall(r'event == "([a-z0-9-]+)"', hook_py)),
}
for name, tokens in allowed.items():
    assert tokens, f"{name}: no event allowlist found (the parser or the file shape changed)"
    assert tokens == set(registered), (
        f"event token drift between hooks.json and {name}: "
        f"registered-only={sorted(set(registered) - tokens)}, {name}-only={sorted(tokens - set(registered))}"
    )
PY

echo "  OK generated launcher routing + cmd.exe commandWindows"

# 참조 경로 계약: 생성된 Codex 에이전트는 story-setup이 배포하는 번들만 사용한다.
python3 - "$CODEX_DIR/agents" <<'PY'
import sys
from pathlib import Path
for path in sorted(Path(sys.argv[1]).glob("*.toml")):
    text = path.read_text(encoding="utf-8")
    if "1. `{项目根}/" not in text:
        continue  # 이 에이전트에는 번호가 붙은 참조 목록이 없다.
    assert text.count("1. `{项目根}/.codex/skills/story-setup/references/agent-references/") == 1, \
        f"{path.name}: numbered reference list must contain the canonical Codex path once"
    for stale in (".claude/skills/", ".opencode/skills/", "{项目根}/skills/story-setup/references/agent-references/"):
        assert stale not in text, f"{path.name}: stale cross-CLI reference fallback {stale}"
PY

echo "  OK Codex agent canonical reference path"

assert_grep '\$story-setup|\$story-long-write|/skills' "$CODEX_DIR/AGENTS.md.tmpl" "Codex AGENTS template must mention skill invocation"
assert_grep '\.codex/agents/\*\.toml' "$CODEX_DIR/AGENTS.md.tmpl" "Codex AGENTS template must mention custom agent location"
assert_grep '\.codex/hooks\.json' "$CODEX_DIR/AGENTS.md.tmpl" "Codex AGENTS template must mention hooks location"
assert_grep 'target_cli:.*codex|codex.*target_cli' skills/story-setup/SKILL.md "story-setup must document codex target_cli"
# 진입점은 호스트별 배포 파일 하나만 읽는다. Codex 목록, 훅 병합, 신뢰 안내는 모두 deploy-codex.md에 있다.
assert_grep 'references/deploy-codex\.md' skills/story-setup/SKILL.md "story-setup entry must route codex to its deploy file"
assert_grep 'references/codex' skills/story-setup/references/deploy-codex.md "story-setup must document Codex references"
assert_grep 'target_cli`( 写入 |는 )`codex`' skills/story-setup/references/deploy-codex.md "Codex deploy file must write codex into target_cli"
assert_grep 'merge-codex-hooks\.py' skills/story-setup/references/deploy-codex.md "Codex deploy file must merge hooks through the helper"
assert_grep 'dangerously-bypass-hook-trust' skills/story-setup/references/deploy-codex.md "Codex deploy file must keep the hook trust install-report prompt"
assert_grep '\.codex/agents|\.codex/hooks\.json' skills/story-review/SKILL.md "story-review must check Codex agents"

echo "  OK Codex docs/instruction anchors"
echo ""
echo "OK: Codex adapter checks passed"
