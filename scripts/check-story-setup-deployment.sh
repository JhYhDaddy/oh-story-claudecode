#!/bin/bash
# check-story-setup-deployment.sh — story-setup 배포/런타임 회귀 검사
# 훅 라이브러리 배포, 참조 번들 무결성, 루트 인식 훅, 단편 프로젝트 무변경,
# 커밋 훅 자체 실행 조건, 배포 동작의 기준점을 검사한다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL_DIR="$REPO_ROOT/skills/story-setup"
HOOKS_DIR="$SKILL_DIR/references/templates/hooks"
AGENT_REFS_DIR="$SKILL_DIR/references/agent-references"
SKILL_FILE="$SKILL_DIR/SKILL.md"
# 진입점에는 공통 절차만 둔다. 호스트별 배포 목록/알고리즘/검증은 references/deploy-<target_cli>.md에 두고 하나만 읽는다.
DEPLOY_HOSTS="claude-code opencode codex antigravity zcode openclaw reasonix generic"
deploy_file() { printf '%s/references/deploy-%s.md' "$SKILL_DIR" "$1"; }
DEPLOY_CLAUDE="$(deploy_file claude-code)"
DEPLOY_OPENCODE="$(deploy_file opencode)"
DEPLOY_ZCODE="$(deploy_file zcode)"
DEPLOY_OPENCLAW="$(deploy_file openclaw)"
DEPLOY_REASONIX="$(deploy_file reasonix)"
DEPLOY_GENERIC="$(deploy_file generic)"
SETTINGS_FILE="$SKILL_DIR/references/templates/settings-hooks.json"
CLAUDE_MERGE="$SKILL_DIR/scripts/merge-claude-settings.py"
COPY_PATH_SAFETY="$SKILL_DIR/scripts/copy-path-safety.py"
TMP_DIR="$(mktemp -d)"
CURRENT_AGENTS_VERSION="$(node -e 'process.stdout.write(String(require(process.argv[1]).agents_version))' "$SCRIPT_DIR/current-contract.json")"
CURRENT_SETUP_VERSION="$(node -e 'process.stdout.write(String(require(process.argv[1]).setup_skill_version))' "$SCRIPT_DIR/current-contract.json")"
PREVIOUS_AGENTS_VERSION=$((CURRENT_AGENTS_VERSION - 1))
NEXT_AGENTS_VERSION=$((CURRENT_AGENTS_VERSION + 1))

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

# 상세 개요에 내용이 있어야(#과 공백 제외 30자 이상) 본문 쓰기를 허용한다. 빈 파일은 빈 상세 개요로 차단한다.
write_outline() { printf '%s\n' '# 细纲' '江晨在雨夜推开旧书店的门，发现柜台后坐着失踪三年的师父，两人对视良久。' > "$1"; }

assert_file() {
  [ -f "$1" ] || fail "required file missing: $1"
}

assert_grep() {
  local pattern="$1"
  local file="$2"
  local message="$3"
  grep -Eq "$pattern" "$file" || fail "$message ($file)"
}

assert_no_grep() {
  local pattern="$1"
  local file="$2"
  local message="$3"
  if grep -Eq "$pattern" "$file"; then
    fail "$message ($file)"
  fi
}

copy_hooks() {
  local root="$1"
  mkdir -p "$root/.claude"
  cp -R "$HOOKS_DIR" "$root/.claude/hooks"
  chmod +x "$root/.claude/hooks"/*.sh
}

copy_agent_refs() {
  local root="$1"
  mkdir -p "$root/.claude/skills/story-setup/references"
  cp -R "$AGENT_REFS_DIR" "$root/.claude/skills/story-setup/references/agent-references"
}

write_sentinel() {
  local root="$1"
  cat > "$root/.story-deployed" <<SENTINEL
deployed_at: 2026-05-24T00:00:00Z
agents_version: $CURRENT_AGENTS_VERSION
setup_skill_version: $CURRENT_SETUP_VERSION
target_cli: claude-code
resolver_strategy: project-local-skill-reference
references_dir: .claude/skills/story-setup/references/agent-references
SENTINEL
}

run_from_nested() {
  local root="$1"
  local script="$2"
  local nested="$root/nested/a/b"
  mkdir -p "$nested"
  (cd "$nested" && CLAUDE_PROJECT_DIR="$root" bash "$root/.claude/hooks/$script")
}

run_from_nested_no_project_dir() {
  local root="$1"
  local script="$2"
  local nested="$root/nested/a/b"
  mkdir -p "$nested"
  (cd "$nested" && unset CLAUDE_PROJECT_DIR && bash "$root/.claude/hooks/$script")
}

setup_git_repo() {
  local root="$1"
  git -C "$root" init -q
  git -C "$root" config user.email story-setup@example.invalid
  git -C "$root" config user.name story-setup-test
}

run_commit_hook_command() {
  local root="$1"
  local command_text="$2"
  (cd "$root" && CLAUDE_PROJECT_DIR="$root" STORY_COMMIT_COMMAND="$command_text" bash .claude/hooks/validate-story-commit.sh 2>&1 || true)
}

assert_commit_warns() {
  local root="$1"
  local command_text="$2"
  local label="$3"
  local out
  out="$(run_commit_hook_command "$root" "$command_text")"
  echo "$out" | grep -q 'Story Commit Warnings' || fail "validate-story-commit did not warn for $label: $command_text"
  echo "$out" | grep -q '본문에 인물 속성을 직접 고정' || fail "validate-story-commit did not inspect staged markdown for $label"
}

echo "Story setup deployment check"
echo "============================"
echo "Repo: $REPO_ROOT"

# TS1 — 훅 의존성 완전성
assert_file "$HOOKS_DIR/lib/common.sh"
assert_file "$HOOKS_DIR/lib/sentinel.sh"
runtime_artifacts="$(find "$HOOKS_DIR" -maxdepth 4 \( -path '*/.omc*' -o -name '.DS_Store' -o -name '*.tmp' -o -name '*.log' \) -print 2>/dev/null || true)"
[ -z "$runtime_artifacts" ] || fail "hook templates contain runtime artifacts that would be recursively deployed: $runtime_artifacts"
while IFS= read -r src; do
  [ -n "$src" ] || continue
  case "$src" in
    '$(dirname "$0")/'*)
      rel="${src#'$(dirname "$0")/'}"
      assert_file "$HOOKS_DIR/$rel"
      ;;
    "\$(dirname \"\$0\")/"*)
      rel="${src#"\$(dirname \"\$0\")/"}"
      assert_file "$HOOKS_DIR/$rel"
      ;;
  esac
done < <(grep -RhoE '^source[[:space:]]+"[^"]+"' "$HOOKS_DIR"/*.sh | sed -E 's/^source[[:space:]]+"//;s/"$//' | sort -u)
# node 공유 코어 + CLI 연결: 본문 검사망/경로 추출/git commit 감지/연속성의 단일 구현을 bash 훅이
# `node "$(dirname "$0")/story_hook_cli.js"`로 호출한다. 개요 차단 판정과 스테이징된 Markdown 경고는 아직 코어에 통합하지 않아
# 각 환경이 별도로 구현한다(Claude는 순수 bash, codex↔core 동등성은 test-prose-net-parity.sh C부에서 고정).
# 이 두 항목은 source 의존성이 아니어서 위 grep이 찾지 못한다. 존재와 문법 유효성을 명시적으로 단언해야 조용한 기능 저하를 막는다.
# (node가 없으면 훅은 exit 0, session-start.sh는 세션 시작에 한 번 안내한다. 여기서는 개발 기기에 node가 있다고 보고 검증한다.)
assert_file "$HOOKS_DIR/story_hook_core.js"
assert_file "$HOOKS_DIR/story_hook_cli.js"
if command -v node >/dev/null 2>&1; then
  node --check "$HOOKS_DIR/story_hook_core.js" || fail "story_hook_core.js node syntax invalid"
  node --check "$HOOKS_DIR/story_hook_cli.js" || fail "story_hook_cli.js node syntax invalid"
fi
# 이는 의존성 방향의 정적 정책이며 동작 테스트가 아니다. bash 훅 4개는 CLI 연결을 통해 공유 코어를 재사용해야 하며
# 다섯 번째 Python 구현을 다시 내장하면 안 된다. 실행 동작은 test-prose-net-parity와 훅 회귀 검사에서 다룬다.
for hook in check-prose-after-write guard-outline-before-prose validate-story-commit detect-story-gaps; do
  if grep -q "<<'PY'" "$HOOKS_DIR/$hook.sh"; then
    fail "$hook.sh must not embed a duplicate Python implementation"
  fi
  assert_grep 'story_hook_cli\.js' "$HOOKS_DIR/$hook.sh" "$hook.sh must delegate to story_hook_cli.js"
done
assert_grep '递归复制完整目录树|recursive' "$DEPLOY_CLAUDE" "Claude deploy file must require recursive hook deployment"
assert_grep 'lib/common\.sh' "$DEPLOY_CLAUDE" "Claude deploy file must mention hooks/lib/common.sh"
assert_grep 'lib/sentinel\.sh' "$DEPLOY_CLAUDE" "Claude deploy file must mention hooks/lib/sentinel.sh"
echo "  OK TS1 hook dependency completeness"

# TS1b — SessionStart 배포 자체 점검 목록은 모든 훅 스크립트를 포함해야 한다(새 훅 누락 방지, #195 검토).
# *.js도 열거한다. story_hook_cli.js/story_hook_core.js는 핵심 공유 코어로 삭제되면 본문 보완 검사/커밋 감지/
# 연속성 검사가 모두 조용히 약화되므로 자체 점검 목록에 반드시 등록해야 한다.
selfcheck_line="$(grep -E 'for hook in .*; do' "$HOOKS_DIR/session-start.sh" | head -1)"
[ -n "$selfcheck_line" ] || fail "session-start.sh 缺少 hook 自检 for 循环"
# 목록의 마지막 훅 뒤는 공백이 아닌 `;`이다(grep 패턴상 줄은 `; do`로 끝난다).
# 원래 줄에서 *" $base "*를 찾으면 실제 등록된 마지막 훅도 누락으로 오인한다. 먼저 세미콜론을
# 공백으로 바꾸고 양끝에 공백을 넣어 정렬을 강요하지 않고 첫 항목과 마지막 항목을 같은 case로 찾는다.
selfcheck_tokens=" ${selfcheck_line//;/ } "
while IFS= read -r hookfile; do
  base="$(basename "$hookfile")"
  case "$selfcheck_tokens" in
    *" $base "*) : ;;
    # ${base}의 중괄호는 필수다. macOS bash 3.2는 UTF-8 로캘에서 전각 ‘（’의 첫 바이트를 변수명에 포함해
    # set -u가 base?: unbound variable을 내므로 실제 누락된 훅 이름을 알 수 없게 된다.
    *) fail "session-start.sh 部署自检名单漏列 hook：${base}（新增 hook 须同步加入该名单）" ;;
  esac
done < <(find "$HOOKS_DIR" -maxdepth 1 \( -name '*.sh' -o -name '*.js' \) -type f)
echo "  OK TS1b session-start self-check lists all hook scripts and node cores"

# TS2a — 호스트별 분리: 진입점은 각 호스트 배포 파일로 연결하고 각 파일은 전체 목록/검증/보고 안내를 갖춘다.
# 파일 또는 진입점 경로가 하나라도 없으면 해당 호스트 작가는 배포 절차를 받지 못한다. 절 누락은 동작 누락이다.
for host in $DEPLOY_HOSTS; do
  host_file="$(deploy_file "$host")"
  assert_file "$host_file"
  assert_grep "references/deploy-$host\.md" "$SKILL_FILE" "story-setup entry must route target_cli $host to its deploy file"
  assert_grep "^# " "$host_file" "deploy file must have a title: $host"
  assert_grep "\`target_cli\`( 含 |에 )\`$host\`" "$host_file" "deploy file must state which target_cli reads it: $host"
  for section in '^## (部署清单|배포 목록)' '^## (验证|검증)' '^## (安装报告必须提示|설치 보고 필수 안내)'; do
    assert_grep "$section" "$host_file" "deploy file $host missing section: $section"
  done
  # 아래 자체 복사 탐지기는 이 두 머리글로 배포 목록 표를 식별하므로 이름을 바꾸면 행 검사가 조용히 무효화된다.
  for header in 'Source path' 'Target path'; do
    assert_grep "$header" "$host_file" "deployment manifest header the self-copy detector keys on is missing in $host: $header"
  done
done
extra_deploy_files="$(find "$SKILL_DIR/references" -maxdepth 1 -name 'deploy-*.md' | wc -l | tr -d ' ')"
[ "$extra_deploy_files" = "8" ] || fail "story-setup must ship exactly 8 host deploy files, found $extra_deploy_files"
# 실행 환경으로 호스트를 판단할 수 있으면 작가에게 묻지 않는다. 물어도 쉬운 표현을 쓰며 배포 위치를 다시 묻지 않는다.
assert_grep '能判断就不问作者|판별 가능하면 작가에게 묻지 않음' "$SKILL_FILE" "story-setup must detect the current host before asking the author"
assert_no_grep '让用户选择目标环境|사용자에게 대상 환경을 선택하게' "$SKILL_FILE" "story-setup must not ask first-time authors to pick among all hosts when the host is detectable"
assert_no_grep 'AskUserQuestion 确认部署位置|AskUserQuestion으로 배포 위치를 확인' "$SKILL_FILE" "story-setup must not ask for the deploy location by default"
echo "  OK TS2a host deploy files"

# TS2 — 배포 점검 목록/매니페스트 파싱 가능 여부
for group in 'templates/hooks/' 'templates/rules' 'templates/agents' 'agent-references' 'settings-hooks\.json' 'CLAUDE\.md' '\.story-deployed'; do
  assert_grep "$group" "$DEPLOY_CLAUDE" "deployment manifest missing asset group: $group"
done
assert_grep '\.agents-pending-restart' "$DEPLOY_CLAUDE" "Claude deploy must create the one-shot restart marker"
assert_file "$SKILL_DIR/references/openclaw/AGENTS.md.tmpl"
assert_file "$SKILL_DIR/references/generic/AGENTS.md.tmpl"
assert_file "$SKILL_DIR/references/reasonix/AGENTS.md.tmpl"
assert_file "$SKILL_DIR/references/zcode/AGENTS.md.tmpl"
assert_file "$SKILL_DIR/references/zcode/config.json.patch"
assert_file "$SKILL_DIR/references/zcode/hooks/hooks.json"
assert_file "$SKILL_DIR/references/zcode/hooks/story_zcode_hook.js"
assert_file "$SKILL_DIR/references/zcode/hooks/story_hook_core.js"
assert_file "$SKILL_DIR/references/antigravity/rules/oh-story.md"
assert_file "$SKILL_DIR/references/antigravity/hooks/hooks.json"
assert_file "$SKILL_DIR/references/antigravity/hooks/story_antigravity_hook.js"
assert_file "$SKILL_DIR/references/antigravity/hooks/story_hook_core.js"
assert_file "$SKILL_DIR/scripts/generate-antigravity-agents.mjs"
assert_file "$SKILL_DIR/scripts/deploy-antigravity-skills.py"
assert_file "$SKILL_DIR/scripts/merge-antigravity-hooks.py"
# OpenCode는 동일한 본문 보호 코어를 공유한다(바이트 일치는 check-opencode-adapter.sh가 검증).
# plugin.ts와 함께 .opencode/plugins/lib/story_hook_core.js로 배포한다(lib/ 하위 디렉터리로 두어
# OpenCode의 단일 수준 .opencode/plugins/*.js 플러그인 자동 탐색을 피한다).
assert_file "$SKILL_DIR/references/opencode/story_hook_core.js"
assert_grep 'opencode/story_hook_core\.js' "$DEPLOY_OPENCODE" "deployment manifest missing OpenCode shared prose-guard core"
assert_grep 'references/openclaw/AGENTS\.md\.tmpl' "$DEPLOY_OPENCLAW" "deployment manifest missing OpenClaw AGENTS template"
assert_grep 'OpenClaw skills-only' "$DEPLOY_OPENCLAW" "story-setup must document OpenClaw skills-only deployment"
assert_grep 'references/generic/AGENTS\.md\.tmpl' "$DEPLOY_GENERIC" "deployment manifest missing generic AGENTS template"
assert_grep '通用 Web AI / 其他 Agent|일반 Web AI / 기타 에이전트' "$DEPLOY_GENERIC" "story-setup must document generic Web AI deployment"
assert_grep 'references/reasonix/AGENTS\.md\.tmpl' "$DEPLOY_REASONIX" "deployment manifest missing Reasonix AGENTS template"
assert_grep 'Reasonix skills-only' "$DEPLOY_REASONIX" "story-setup must document Reasonix skills-only deployment"
assert_grep '\.agents/skills → \.\./skills' "$DEPLOY_REASONIX" "Reasonix deploy must link .agents/skills to skills/"
assert_grep 'references/zcode/AGENTS\.md\.tmpl' "$DEPLOY_ZCODE" "deployment manifest missing ZCode AGENTS template"
assert_grep 'target_cli = zcode' "$SKILL_FILE" "story-setup must detect ZCode projects"
assert_grep '\.zcode/config\.json' "$DEPLOY_ZCODE" "story-setup must document ZCode config merge"
assert_grep '不部署.*\.zcode/agents|不创建.*\.zcode/agents|\.zcode/agents.*만들거나.*수정하지 않는다|\.zcode/agents.*배포하지 않' "$DEPLOY_ZCODE" "story-setup must document ZCode agent boundary"
# 스킬 전용 경로 세 곳의 AGENTS 템플릿은 각자 배포 파일에 있으며 서로 섞어 쓰면 안 된다.
for pair in "openclaw:$DEPLOY_OPENCLAW" "reasonix:$DEPLOY_REASONIX" "generic:$DEPLOY_GENERIC"; do
  host="${pair%%:*}"; file="${pair#*:}"
  for other in openclaw reasonix generic zcode opencode codex; do
    [ "$other" = "$host" ] && continue
    assert_no_grep "references/$other/AGENTS\.md\.tmpl" "$file" "deploy-$host.md must not deploy the $other AGENTS template"
  done
done
assert_grep 'references_dir' "$SKILL_FILE" "sentinel references_dir must be documented"
assert_grep 'resolver_strategy' "$SKILL_FILE" "sentinel resolver_strategy must be documented"
assert_grep 'target_cli' "$SKILL_FILE" "sentinel target_cli must be documented"

# 배포 목록 Source는 스킬 패키지 기준, Target은 프로젝트 루트 기준이다. 스킬 전용 환경에서는 두 기준이 같을 수 있다.
# 어느 행이든 같은 경로를 그대로 쓰면 실행자가 디렉터리를 자기 안으로 복사하게 된다.
assert_grep 'copy-path-safety\.py' "$SKILL_FILE" "deployment must invoke the recursive-copy path safety helper"
assert_grep 'Path\.resolve.*realpath' "$SKILL_FILE" "deployment must canonicalize copy paths through symlinks"
assert_grep 'samefile' "$SKILL_FILE" "deployment must compare existing source/target filesystem identity"
assert_grep 'target-descendant|目标位于源目录内' "$SKILL_FILE" "deployment must reject recursive-copy targets inside their source"
assert_grep '清理自嵌套残留|자기 중첩 잔여물 정리' "$SKILL_FILE" "story-setup must clean self-nested copies before deploying"
assert_file "$COPY_PATH_SAFETY"

# 실제 도우미를 실행해 심볼릭 링크 별칭, 동일 디렉터리, 하위 디렉터리, 안전한 형제 경로를 검증한다. SKILL.md 문구만 고정하면 안 된다.
path_fixture="$TMP_DIR/copy-path-safety"
mkdir -p "$path_fixture/project/skills/story-setup/references/agent-references" \
  "$path_fixture/project/.agents" "$path_fixture/source" "$path_fixture/sibling"

python3 - "$COPY_PATH_SAFETY" "$path_fixture" <<'PY' || fail "copy path safety helper behavior regressed"
import json
import importlib.util
import subprocess
import sys
from unittest import mock
from pathlib import Path

helper = sys.argv[1]
root = Path(sys.argv[2])


def run(source, target):
    proc = subprocess.run(
        [sys.executable, helper, str(source), str(target)],
        text=True,
        capture_output=True,
    )
    payload = json.loads(proc.stdout)
    return proc.returncode, payload


project = root / "project"
alias = project / ".agents/skills/story-setup/references/agent-references"
direct = project / "skills/story-setup/references/agent-references"
try:
    (project / ".agents/skills").symlink_to("../skills", target_is_directory=True)
except OSError as exc:
    # 심볼릭 링크 권한 없는 Windows 실행 환경도 다른 실제 도우미 경로는 검사한다.
    print("SKIP: symlink alias fixture unavailable: {}".format(exc))
else:
    code, payload = run(alias, direct)
    assert code == 0
    assert payload["status"] == "same"
    assert payload["copy_allowed"] is False
    assert payload["source_realpath"] == payload["target_realpath"]

source = root / "source"
code, payload = run(source, source / "nested/target")
assert code != 0
assert payload["status"] == "unsafe_target_within_source"
assert payload["copy_allowed"] is False
assert not (source / "nested").exists()

code, payload = run(source, root / "sibling/target")
assert code == 0
assert payload["status"] == "safe"
assert payload["copy_allowed"] is True
assert not (root / "sibling/target").exists()

code, payload = run(root / "missing", root / "sibling/target")
assert code != 0
assert payload["status"] == "source_missing"
assert payload["copy_allowed"] is False

spec = importlib.util.spec_from_file_location("copy_path_safety", helper)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with mock.patch.object(module.os.path, "samefile", side_effect=OSError("identity unavailable")):
    payload = module.classify_copy(source, root / "sibling")
assert payload["status"] == "filesystem_identity_error"
assert payload["copy_allowed"] is False
assert module.status_exit_code(payload["status"]) != 0
PY
# 탐지기는 하나만 작성하고 양성/음성 데이터로 자체 점검한 뒤 실제 SKILL.md를 검사한다.
cat > "$TMP_DIR/detect-self-copy.py" <<'PY'
import re
import sys

path = sys.argv[1]
lines = open(path, encoding='utf-8').read().splitlines()
bad = []
in_manifest = False
# 「复制 A 到 B」里两个路径之间只隔几个字；隔得远的是叙述句，不是复制指令。
MAX_GAP = 16


def norm(cell):
    return cell.strip().strip('`').rstrip('/')


for idx, line in enumerate(lines, 1):
    stripped = line.strip()
    is_row = stripped.startswith('|') and stripped.endswith('|')
    if is_row and 'Source path' in stripped and 'Target path' in stripped:
        in_manifest = True
        continue
    if not is_row:
        in_manifest = False
    elif in_manifest:
        if set(stripped) <= set('|-: '):
            continue
        cells = [c.strip() for c in stripped.strip('|').split('|')]
        # 源写成 `repository ...` 时显式声明了它在仓库/skill 包一侧，与项目根一侧的
        # 目标不同名，自然不会相等；裸写成同一个字符串的才是复制进自身。
        if len(cells) >= 2 and norm(cells[0]) == norm(cells[1]):
            bad.append((idx, f'manifest row copies {cells[0]} onto itself'))
        continue
    if '复制' not in stripped and '拷贝' not in stripped and '복사' not in stripped:
        continue
    # 只看紧邻的一对反引号路径：中间只隔一个「到」而两侧同路径，就是复制进自身。
    # 两次出现之间夹着别的路径或大段叙述时不算——那是「从 A 复制到 B，A 是唯一来源」这类正常句子。
    spans = [(m.start(), m.end(), m.group(1)) for m in re.finditer(r'`([^`]+)`', stripped)]
    for (_, left_end, left), (right_start, right_end, right) in zip(spans, spans[1:]):
        gap = stripped[left_end:right_start]
        if '/' not in left or norm(left) != norm(right):
            continue
        ko_copy = re.fullmatch(r'(?:를|을)\s*', gap.strip()) and re.match(r'(?:으)?로\s+(?:재귀\s+|동기화\s+)?복사', stripped[right_end:])
        if ('到' in gap or ko_copy) and len(gap) <= MAX_GAP:
            bad.append((idx, f'copy instruction names `{left}` as both source and target'))

for idx, msg in bad:
    print(f'{path}:{idx}: {msg}', file=sys.stderr)
sys.exit(1 if bad else 0)
PY

cat > "$TMP_DIR/self-copy-fixtures.md" <<'FIXTURE'
- 将 `references/opencode/agents/` 下所有文件复制到 `.opencode/agents/`；`references/opencode/agents/` 是唯一来源。
- 复制 `a/b/` 到 `a/b/`。
- 将 `a/b/` 同步复制到 `a/b/`。
- 复制 `x/y/` 到 `.codex/x/y/`。
- 复制 `a/b/` 到 `a/b`。
- 将 `skills/story-setup/references/agent-references/` 下所有 `.md` 复制到项目内 `.claude/skills/story-setup/references/agent-references/`。
- `a/b/` 与 `a/b/` 都要存在；提到复制但两者之间没有「到」。
- 拆文结果被复制进 `비교작품/`，用户看到的就是对标内容和自己设定一样；只有外部作品才进 `비교작품/`。
- 复制 `p/q/` 到 `r/s/`，`p/q/` 保留。
- 复制章节时 `第N章` 到 `第N章` 的编号不变。

| 角色 A | 角色 B | 关系类型 | 情感倾向 | 当前状态 | 起始章节 |
|--------|--------|---------|---------|---------|---------|
| {名} | {名} | {类型} | {倾向} | {描述} | 第{N}章 |

| Source path | Target path | Owner class | Merge mode | Validation check |
|-------------|-------------|-------------|------------|------------------|
| `a/b/` | `a/b` | story-setup managed | replace | resolves | 条件 |
| repository `a/b/` | `a/b/` | story-setup managed | replace | resolves | 条件 |
| `a/b/` | `.codex/a/b/` | story-setup managed | replace | resolves | 条件 |
- `a/b/`를 `a/b/`로 복사한다.
- `a/b/`를 `a/b`로 재귀 복사한다.
- `a/b/`를 `c/d/`로 복사한다.
- `a/b/`와 `a/b/`가 있어야 한다. 복사 전에 확인한다.
FIXTURE

# 탐지 결과가 있으면 종료 코드는 1이다. `|| true`는 파이프 안에 있어야 한다. 그렇지 않으면 pipefail로 할당 시 스크립트가 중단돼
# 아래 fail 메시지조차 출력하지 못한다.
fixture_hits="$({ python3 "$TMP_DIR/detect-self-copy.py" "$TMP_DIR/self-copy-fixtures.md" 2>&1 >/dev/null || true; } | sed 's/.*fixtures\.md:\([0-9]*\):.*/\1/' | tr '\n' ',')"
[ "$fixture_hits" = "2,3,5,18,21,22," ] \
  || fail "self-copy detector fixtures regressed: expected lines 2,3,5,18,21,22 got [$fixture_hits]"

for setup_doc in "$SKILL_FILE" "$SKILL_DIR"/references/deploy-*.md; do
  python3 "$TMP_DIR/detect-self-copy.py" "$setup_doc" \
    || fail "story-setup declares a copy whose source and target are the same path ($setup_doc)"
done

# Claude Code의 Bash 본문 쓰기도 같은 사전 보호를 거쳐야 한다. Write/Edit만 등록하면 cat>/tee/cp로 우회할 수 있다.
python3 - "$SKILL_DIR/references/templates/settings-hooks.json" <<'PY' || fail "Claude Bash prose pre-guard is not registered"
import json, sys
from pathlib import Path
hooks = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
assert any(
    "Bash" in block.get("matcher", "").split("|")
    and any("guard-outline-before-prose.sh" in hook.get("command", "") for hook in block.get("hooks", []))
    for block in hooks
)
PY
# v24 → v25 실제 이전: 같은 command라도 이전 matcher를 남기면 안 된다. 이전 블록의 사용자 훅은 보존하고 재실행은 멱등적이어야 한다.
assert_file "$CLAUDE_MERGE"
cat > "$TMP_DIR/claude-v24.json" <<'JSON'
{
  "permissions": {"allow": ["Read"]},
  "customTop": "keep",
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {"type": "command", "command": "bash \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/guard-outline-before-prose.sh", "timeout": 7},
          {"type": "command", "command": "bash ./user-pre-hook.sh", "timeout": 99}
        ]
      }
    ],
    "PostToolUse": [
      {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/guard-outline-before-prose.sh", "timeout": 3}]}
    ]
  }
}
JSON
python3 "$CLAUDE_MERGE" --existing "$TMP_DIR/claude-v24.json" --template "$SETTINGS_FILE" --output "$TMP_DIR/claude-v25.json"
python3 - "$TMP_DIR/claude-v25.json" <<'PY' || fail "Claude v24→v25 hook migration failed"
import json, sys
doc=json.load(open(sys.argv[1],encoding="utf-8"))
assert doc["permissions"] == {"allow":["Read"]} and doc["customTop"] == "keep"
hits=[]; user=[]
for event, blocks in doc["hooks"].items():
    if not isinstance(blocks,list): continue
    for block in blocks:
        for hook in block.get("hooks",[]):
            cmd=hook.get("command","")
            if "guard-outline-before-prose.sh" in cmd: hits.append((event,block.get("matcher"),hook))
            if "user-pre-hook.sh" in cmd: user.append((event,block.get("matcher"),hook))
assert len(hits)==1, hits
assert hits[0][0]=="PreToolUse" and hits[0][1]=="Bash|Write|Edit|MultiEdit", hits
assert hits[0][2].get("timeout")==10, hits
assert len(user)==1 and user[0][0]=="PreToolUse" and user[0][1]=="Write|Edit|MultiEdit", user
PY
python3 "$CLAUDE_MERGE" --existing "$TMP_DIR/claude-v25.json" --template "$SETTINGS_FILE" --output "$TMP_DIR/claude-v25-again.json"
cmp -s "$TMP_DIR/claude-v25.json" "$TMP_DIR/claude-v25-again.json" \
  || fail "Claude settings merge is not idempotent"

# 프로젝트 지침 병합: 호스트마다 관리 블록 하나. 마커 없는 이전 파일은 한 번 이전하고 작가의 절은 블록 밖에 남긴다.
# 재실행은 블록 전체를 교체하며 바이트 단위로 멱등적이다. 흔한 이름이어도 oh-story 흔적 없는 작가의 절은 이전 배포로 삭제하면 안 된다.
INSTR_MERGE="$SKILL_DIR/scripts/merge-project-instructions.py"
assert_file "$INSTR_MERGE"
python3 - "$INSTR_MERGE" "$SKILL_DIR/references" "$TMP_DIR/instr-merge" <<'PY' || fail "project instruction managed-block merge regressed"
import json, subprocess, sys
from pathlib import Path
helper, refs, root = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
root.mkdir(parents=True)
templates = {
    "claude-code": refs / "templates/CLAUDE.md.tmpl",
    "opencode": refs / "opencode/AGENTS.md.tmpl",
    **{h: refs / h / "AGENTS.md.tmpl" for h in ("codex", "zcode", "openclaw", "reasonix", "generic")},
}
def run(host, path, name="我的书"):
    proc = subprocess.run([sys.executable, helper, "--host", host, "--template", str(templates[host]),
                           "--existing", str(path), "--output", str(path), "--project-name", name],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)
# 새 파일: 모든 호스트가 닫힌 블록을 렌더링하고 {项目名}만 바꾸며 {书名} 와일드카드는 유지한다.
for host in templates:
    target = root / f"new-{host}.md"
    assert run(host, target)["status"] == "created"
    text = target.read_text(encoding="utf-8")
    assert text.startswith(f"<!-- oh-story:{host} 开始") and f"<!-- oh-story:{host} 结束 -->" in text, host
    assert "{项目名}" not in text and "我的书" in text and "{书名}" in text, host
# 마커 없는 이전 다중 호스트 파일: Codex + ZCode를 한 번씩 이전하고 작가 절은 보존하며 폐기된 협업 규칙 절은 제거한다.
legacy = root / "AGENTS.md"
legacy.write_text("""# 我的书 — 网文写作工具集（Codex）

## Skill 路由表

| `$story-long-write` | story-long-write |

## Codex 项目约定

- Codex custom agents 在 `.codex/agents/*.toml`

## 我的约定

- 每天写两章。

## ZCode 项目约定

- 写正文前必须先有对应大纲

## 协作规则

Agent 分工与升级路径见 `.codex/agents/*.toml` 的职责边界。
""", encoding="utf-8")
assert run("codex", legacy)["status"] == "migrated"
assert run("zcode", legacy)["status"] == "migrated"
first = legacy.read_bytes()
text = first.decode("utf-8")
assert text.count("## 我的约定") == 1 and "每天写两章" in text
assert "## 协作规则" not in text
assert text.count("<!-- oh-story:codex 开始") == 1 and text.count("<!-- oh-story:zcode 开始") == 1
for host in ("zcode", "codex", "zcode"):
    assert run(host, legacy)["status"] == "replaced"
assert legacy.read_bytes() == first, "redeploy must be byte-idempotent"
# oh-story 흔적 없는 작가의 흔한 동명 절은 이전 배포가 아니다. 블록만 추가하고 원문은 그대로 둔다.
user = root / "user-AGENTS.md"
original = "# 我的项目\n\n## 文件结构\n\n- docs/ 放说明\n"
user.write_text(original, encoding="utf-8")
assert run("generic", user)["status"] == "appended"
merged = user.read_text(encoding="utf-8")
assert merged.startswith(original.rstrip("\n")) and "网文写作工具集（通用 Agent / Web AI）" in merged
# oh-story 제목 줄 없는 작가 파일은 절 이름이 템플릿과 같고 본문에 작품분석실/细纲이 있어도 이전 배포가 아니다.
own = root / "own-CLAUDE.md"
original = "# 我的小说项目\n\n## 文件结构\n\n- 작품분석실/ 放我自己的拆书笔记\n- 细纲写在 notes/\n\n## 与作者协作\n\n- 先讨论再动笔\n"
own.write_text(original, encoding="utf-8")
report = run("claude-code", own)
assert report["status"] == "appended" and report["removed_legacy_sections"] == [], report
assert own.read_text(encoding="utf-8").startswith(original.rstrip("\n"))
# 다른 호스트 블록이 있으면 블록 밖 작가의 공통 절 이름(작가와 협업 등)은 이 호스트 이전 배포로 보지 않는다.
shared = root / "shared-AGENTS.md"
assert run("codex", shared)["status"] == "created"
shared.write_text(shared.read_text(encoding="utf-8") + "\n## 与作者协作\n\n- 先讨论再动笔\n", encoding="utf-8")
report = run("zcode", shared)
assert report["status"] == "appended" and report["removed_legacy_sections"] == [], report
assert "先讨论再动笔" in shared.read_text(encoding="utf-8")
PY

# 재배포 시 sentinel의 target_cli가 기준이다. 이를 무시하면 매번 다시 묻게 되고 스킬 전용 환경 세 곳은 탐지할 방법도 없다.
assert_grep '已部署项目以 sentinel 里的值为准|기존 배포 프로젝트는 sentinel의 값을 기준으로 합니다' "$SKILL_FILE" "story-setup must reuse the deployed target_cli on redeploy"
# 다만 sentinel을 재사용해도 현재 호스트 판정은 생략하지 않는다. 작가가 프로그램을 바꿨다면 새 호스트에 설치할 기회가 있어야 한다.
assert_no_grep '跳过下面第 4-6 步的宿主判断|4-6번째 단계의 호스트 판단을 건너뜁니다' "$SKILL_FILE" "story-setup must still detect the current host when the sentinel already lists targets"
assert_grep '第 4 步仍判断当前宿主|4번째 단계에서 현재 호스트는 계속 판단합니다' "$SKILL_FILE" "story-setup must detect the current host on redeploy"
assert_grep '你现在用的是.*要一起装上吗|지금 사용 중인.*함께 설치할까요' "$SKILL_FILE" "story-setup must offer to add a new current host missing from the sentinel"
# 호스트를 판단할 수 없을 때 프로젝트의 호스트 마커는 지난 설치 대상일 뿐 현재 프로그램을 뜻하지 않는다.
assert_no_grep '恰好只有一个宿主的标记就用它|호스트 표식이 정확히 하나면 그대로 사용' "$SKILL_FILE" "story-setup must not silently treat a lone project marker as the current host"
assert_grep '这次还是它吗|이번에도 같은가요' "$SKILL_FILE" "story-setup must confirm a lone project marker with the author"
# metadata.openclaw는 스킬 14개 모두에 있어 이것으로 판정하면 reasonix/generic 프로젝트를 OpenClaw로 오인한다.
assert_no_grep '中的 `metadata\.openclaw`' "$SKILL_FILE" "story-setup must not detect OpenClaw from the skills bundle it deploys itself"
assert_grep '不作 OpenClaw 信号|OpenClaw 신호가 아닙니다' "$SKILL_FILE" "story-setup must explain why metadata.openclaw is not a detection signal"
# 스킬 전용 환경 세 곳은 AGENTS.md 제목 줄로만 구분한다. SKILL.md가 참조하는 마커는 템플릿에 실제 존재해야 한다.
assert_grep '网文写作工具集（Reasonix）' "$SKILL_FILE" "story-setup must detect a deployed Reasonix project from AGENTS.md"
assert_grep '网文写作工具集（通用 Agent / Web AI）' "$SKILL_FILE" "story-setup must detect a deployed generic project from AGENTS.md"
assert_grep '网文写作工具集（Reasonix）' "$SKILL_DIR/references/reasonix/AGENTS.md.tmpl" "Reasonix AGENTS template must carry the marker story-setup detects"
assert_grep '网文写作工具集（通用 Agent / Web AI）' "$SKILL_DIR/references/generic/AGENTS.md.tmpl" "generic AGENTS template must carry the marker story-setup detects"
assert_grep '网文写作工具集（OpenClaw）' "$SKILL_DIR/references/openclaw/AGENTS.md.tmpl" "OpenClaw AGENTS template must carry the marker story-setup detects"
echo "  OK TS2 deployment manifest"

# TS3 — 에이전트 참조 번들 무결성
refs_tmp="$TMP_DIR/deployed-reference-bundle"
copy_agent_refs "$refs_tmp"
while IFS= read -r ref; do
  [ -n "$ref" ] || continue
  assert_file "$AGENT_REFS_DIR/$ref"
  assert_file "$refs_tmp/.claude/skills/story-setup/references/agent-references/$ref"
done < <(grep -RhoE 'story-setup/references/agent-references/[A-Za-z0-9_-]+\.md' \
  "$SKILL_DIR/references/templates/agents" "$AGENT_REFS_DIR" "$SKILL_DIR/references/templates/rules" 2>/dev/null \
  | sed 's|.*/||' | sort -u)
echo "  OK TS3 agent reference integrity"

# TS4 — 중첩 cwd에서 훅 루트 해석
root="$TMP_DIR/root-aware"
mkdir -p "$root/book/추적" "$root/book/본문" "$root/book/설정" "$root/book/개요" "$root/작품분석실/sample"
setup_git_repo "$root"
copy_hooks "$root"
copy_agent_refs "$root"
write_sentinel "$root"
printf 'book\n' > "$root/.active-book"
cat > "$root/book/추적/문맥.md" <<'CTX'
# 写作进度
## 当前位置
- 章: 第1章
CTX
touch "$root/작품분석실/sample/_progress.md"
# 음성 테스트 데이터: 분석 완료된 책을 미완료로 보고하면 안 된다(_progress.md 개수만 세면 영구 오탐).
mkdir -p "$root/작품분석실/done"
printf '# 深度拆解进度：done\n\n- 最终状态：completed\n- schema_version: 2\n' > "$root/작품분석실/done/_progress.md"

out_start="$(run_from_nested "$root" session-start.sh || true)"
echo "$out_start" | grep -q '当前位置' || fail "session-start did not resolve active book from project root"
echo "$out_start" | grep -q '未完成拆文' || fail "session-start did not resolve 拆文库 from project root"
echo "$out_start" | grep -q '有 1 个未完成拆文' || fail "session-start counted completed 拆文 as unfinished"
if echo "$out_start" | grep -q '参考资料包缺失'; then
  fail "session-start reported missing reference bundle after deployed refs were copied"
fi

out_pre="$(run_from_nested "$root" pre-compact.sh || true)"
echo "$out_pre" | grep -q 'Writing context: book/추적/문맥.md' || fail "pre-compact did not resolve context from project root"

out_post="$(run_from_nested "$root" post-compact.sh || true)"
echo "$out_post" | grep -q 'Read book/추적/문맥.md' || fail "post-compact did not resolve context from project root"

out_gaps="$(run_from_nested "$root" detect-story-gaps.sh || true)"
if [ -n "$out_gaps" ] && echo "$out_gaps" | grep -q "$root/nested"; then
  fail "detect-story-gaps leaked nested cwd paths"
fi
# session-start와 같은 기준으로 미완료는 보고하고 완료는 보고하지 않는다(양쪽이 작품분석실/를 각각 읽으므로 각각 고정).
echo "$out_gaps" | grep -q '拆文未完成：작품분석실/sample/_progress.md' || fail "detect-story-gaps missed unfinished 拆文"
if echo "$out_gaps" | grep -q '작품분석실/done/_progress.md'; then
  fail "detect-story-gaps counted completed 拆文 as unfinished"
fi

fallback_root="$TMP_DIR/git-fallback"
mkdir -p "$fallback_root/book/추적" "$fallback_root/book/본문" "$fallback_root/book/개요"
setup_git_repo "$fallback_root"
copy_hooks "$fallback_root"
copy_agent_refs "$fallback_root"
write_sentinel "$fallback_root"
printf 'book\n' > "$fallback_root/.active-book"
printf '# 写作进度\n' > "$fallback_root/book/추적/문맥.md"
out_fallback="$(run_from_nested_no_project_dir "$fallback_root" pre-compact.sh || true)"
echo "$out_fallback" | grep -q 'Writing context: book/추적/문맥.md' || fail "pre-compact did not resolve context via git root fallback without CLAUDE_PROJECT_DIR"

echo "  OK TS4 hook root resolution"

# TS5 — Sentinel / 불완전한 배포 진단
broken_root="$TMP_DIR/broken-libs"
mkdir -p "$broken_root"
setup_git_repo "$broken_root"
copy_hooks "$broken_root"
write_sentinel "$broken_root"
rm -f "$broken_root/.claude/hooks/lib/sentinel.sh"
broken_out="$(run_from_nested "$broken_root" session-start.sh 2>&1 || true)"
echo "$broken_out" | grep -q 'hook 函数库缺失' || fail "session-start did not explain missing hook libraries before sourcing"

bad_sentinel_root="$TMP_DIR/bad-sentinel"
mkdir -p "$bad_sentinel_root"
setup_git_repo "$bad_sentinel_root"
copy_hooks "$bad_sentinel_root"
cat > "$bad_sentinel_root/.story-deployed" <<SENTINEL
deployed_at: 2026-05-24T00:00:00Z
agents_version: $CURRENT_AGENTS_VERSION
setup_skill_version: $CURRENT_SETUP_VERSION
resolver_strategy: project-local-skill-reference
references_dir: .claude/skills/story-setup/references/agent-references
SENTINEL
bad_sentinel_out="$(run_from_nested "$bad_sentinel_root" session-start.sh 2>&1 || true)"
echo "$bad_sentinel_out" | grep -q '缺少 target_cli' || fail "session-start did not warn for missing sentinel target_cli"
echo "$bad_sentinel_out" | grep -q '参考资料包缺失或为空' || fail "session-start did not warn for missing deployed reference bundle"

stale_previous_root="$TMP_DIR/stale-previous"
mkdir -p "$stale_previous_root/.claude/skills/story-setup/references/agent-references"
setup_git_repo "$stale_previous_root"
copy_hooks "$stale_previous_root"
cat > "$stale_previous_root/.story-deployed" <<SENTINEL
deployed_at: 2026-05-24T00:00:00Z
agents_version: $PREVIOUS_AGENTS_VERSION
setup_skill_version: $CURRENT_SETUP_VERSION
target_cli: claude-code
resolver_strategy: project-local-skill-reference
references_dir: .claude/skills/story-setup/references/agent-references
SENTINEL
stale_previous_out="$(run_from_nested "$stale_previous_root" session-start.sh 2>&1 || true)"
echo "$stale_previous_out" | grep -q "低于 v$CURRENT_AGENTS_VERSION" || fail "session-start did not warn for agents_version $PREVIOUS_AGENTS_VERSION stale v$CURRENT_AGENTS_VERSION deployment"

newer_project_root="$TMP_DIR/newer-project"
mkdir -p "$newer_project_root/.claude/skills/story-setup/references/agent-references"
setup_git_repo "$newer_project_root"
copy_hooks "$newer_project_root"
cat > "$newer_project_root/.story-deployed" <<SENTINEL
deployed_at: 2026-05-24T00:00:00Z
agents_version: $NEXT_AGENTS_VERSION
setup_skill_version: 1.3.0
target_cli: claude-code
resolver_strategy: project-local-skill-reference
references_dir: .claude/skills/story-setup/references/agent-references
SENTINEL
newer_project_out="$(run_from_nested "$newer_project_root" session-start.sh 2>&1 || true)"
echo "$newer_project_out" | grep -q "高于本 hook 支持的 v$CURRENT_AGENTS_VERSION" || fail "session-start did not reject agents_version $NEXT_AGENTS_VERSION downgrade"
echo "$newer_project_out" | grep -q '不要降级覆盖' || fail "session-start did not explain future-version safety"

mixed_version_root="$TMP_DIR/mixed-version"
mkdir -p "$mixed_version_root/.claude/skills/story-setup/references/agent-references"
setup_git_repo "$mixed_version_root"
copy_hooks "$mixed_version_root"
touch "$mixed_version_root/.claude/skills/story-setup/references/agent-references/dummy.md"
cat > "$mixed_version_root/.story-deployed" <<SENTINEL
deployed_at: 2026-05-24T00:00:00Z
agents_version: $CURRENT_AGENTS_VERSION
setup_skill_version: 1.2.6
target_cli: claude-code
resolver_strategy: project-local-skill-reference
references_dir: .claude/skills/story-setup/references/agent-references
SENTINEL
mixed_version_out="$(run_from_nested "$mixed_version_root" session-start.sh 2>&1 || true)"
# agents_version만 런타임 노후화 판단의 기준이다. setup_skill_version이 뒤처져도 재배포하지 않는다(의도된 설계).
if echo "$mixed_version_out" | grep -q "低于 v$CURRENT_AGENTS_VERSION"; then
  fail "session-start incorrectly nagged '低于 v$CURRENT_AGENTS_VERSION' for current agents_version=$CURRENT_AGENTS_VERSION just because setup_skill_version lags"
fi
if echo "$mixed_version_out" | grep -q '高于本 hook'; then
  fail "session-start incorrectly nagged '高于本 hook' for current agents_version=$CURRENT_AGENTS_VERSION just because setup_skill_version lags"
fi

# 여러 환경 배포의 references_dir는 쉼표로 구분한 여러 경로다. 전체를 한 경로로 검사하면 매 세션 누락을 오탐하고
# 반대로 실제 빠진 경로는 놓치므로 두 방향 모두 검증해야 한다.
multi_end_root="$TMP_DIR/multi-end-refs"
mkdir -p "$multi_end_root/.claude/skills/story-setup/references/agent-references"
mkdir -p "$multi_end_root/.codex/skills/story-setup/references/agent-references"
setup_git_repo "$multi_end_root"
copy_hooks "$multi_end_root"
touch "$multi_end_root/.claude/skills/story-setup/references/agent-references/dummy.md"
touch "$multi_end_root/.codex/skills/story-setup/references/agent-references/dummy.md"
cat > "$multi_end_root/.story-deployed" <<SENTINEL
deployed_at: 2026-05-24T00:00:00Z
agents_version: $CURRENT_AGENTS_VERSION
setup_skill_version: $CURRENT_SETUP_VERSION
target_cli: claude-code,codex
resolver_strategy: project-local-skill-reference
references_dir: .claude/skills/story-setup/references/agent-references,.codex/skills/story-setup/references/agent-references
SENTINEL
multi_end_out="$(run_from_nested "$multi_end_root" session-start.sh 2>&1 || true)"
if echo "$multi_end_out" | grep -q '参考资料包缺失或为空'; then
  fail "session-start falsely reported missing references for a complete multi-end deployment"
fi

rm -rf "$multi_end_root/.codex"
multi_end_partial_out="$(run_from_nested "$multi_end_root" session-start.sh 2>&1 || true)"
echo "$multi_end_partial_out" | grep -q '参考资料包缺失或为空' \
  || fail "session-start did not warn when one end of a multi-end references_dir is missing"
echo "$multi_end_partial_out" | grep -q '\.codex/skills/story-setup/references/agent-references' \
  || fail "session-start did not name the missing end in a multi-end references_dir"
if echo "$multi_end_partial_out" | grep -q '\.claude/skills/story-setup/references/agent-references,'; then
  fail "session-start reported the whole comma-joined references_dir instead of only the missing end"
fi

echo "  OK TS5 sentinel diagnostics"

# TS6 — 단편 프로젝트 무변경
short_root="$TMP_DIR/short-project"
mkdir -p "$short_root/story"
setup_git_repo "$short_root"
copy_hooks "$short_root"
write_sentinel "$short_root"
printf 'story\n' > "$short_root/.active-book"
cat > "$short_root/story/본문.md" <<'TXT'
正文
TXT
run_from_nested "$short_root" session-end.sh >"$TMP_DIR/story-session-end.out" 2>&1 || true
[ ! -d "$short_root/story/추적" ] || fail "session-end created 추적/ for short project without opt-in"
(cd "$short_root/nested/a/b" && CLAUDE_PROJECT_DIR="$short_root" STORY_SESSION_LOG=1 bash "$short_root/.claude/hooks/session-end.sh") >"$TMP_DIR/story-session-end-opt.out" 2>&1 || true
[ ! -d "$short_root/story/추적" ] || fail "session-end created 추적/ for short project even with STORY_SESSION_LOG=1"
echo "  OK TS6 short project non-mutation"

# TS7 — 커밋 훅 자체 실행 조건
commit_root="$TMP_DIR/commit-hook"
mkdir -p "$commit_root/book/본문" "$commit_root/book/설정" "$commit_root/short"
setup_git_repo "$commit_root"
copy_hooks "$commit_root"
cat > "$commit_root/book/본문/제1장.md" <<'TXT'
年龄 ：18
TXT
cat > "$commit_root/short/본문.md" <<'TXT'
身高: 180
TXT
cat > "$commit_root/book/설정/인물.md" <<'TXT'
角色设定
TXT
git -C "$commit_root" add "book/본문/제1장.md" "short/본문.md" "book/설정/인물.md"
for cmd in \
  'git commit -m test' \
  'git -c user.name=x commit -m test' \
  "git -C $commit_root commit -m test" \
  'command git commit -m test' \
  'env X=1 git commit -m test' \
  'git add .; git commit -m test' \
  $'git add .\ngit commit -m test' \
  '(git commit -m test)' \
  'if true; then git commit -m test; fi' \
  'noglob git commit -m test'; do
  assert_commit_warns "$commit_root" "$cmd" "$cmd"
done
for cmd in 'echo git commit docs' 'grep "git commit" file'; do
  non_commit_out="$(run_commit_hook_command "$commit_root" "$cmd")"
  [ -z "$non_commit_out" ] || fail "validate-story-commit warned for non-commit command '$cmd': $non_commit_out"
done
stdin_out="$(cd "$commit_root" && unset STORY_COMMIT_COMMAND CLAUDE_TOOL_INPUT && printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git commit -m test"}}' | CLAUDE_PROJECT_DIR="$commit_root" bash .claude/hooks/validate-story-commit.sh 2>&1 || true)"
echo "$stdin_out" | grep -q 'Story Commit Warnings' || fail "validate-story-commit did not read stdin hook payload"
echo "$stdin_out" | grep -q 'short/본문.md' || fail "validate-story-commit did not inspect short-story 본문.md"
echo "$stdin_out" | grep -q 'book/설정/인물.md' || fail "validate-story-commit did not inspect staged setting markdown"

mono_root="$TMP_DIR/mono-root"
project_root="$mono_root/story-project"
mkdir -p "$project_root/book/본문"
setup_git_repo "$mono_root"
copy_hooks "$project_root"
cat > "$project_root/book/본문/제1장.md" <<'TXT'
身高:181
TXT
git -C "$mono_root" add "story-project/book/본문/제1장.md"
mono_out="$(cd "$project_root" && CLAUDE_PROJECT_DIR="$project_root" STORY_COMMIT_COMMAND='git commit -m test' bash .claude/hooks/validate-story-commit.sh 2>&1 || true)"
echo "$mono_out" | grep -q '본문에 인물 속성을 직접 고정' || fail "validate-story-commit missed staged files when CLAUDE_PROJECT_DIR differs from git root"
echo "  OK TS7 commit hook self-gating"

# TS8 — detect-story-gaps의 여러 책 순회
multi_root="$TMP_DIR/multi-book"
mkdir -p "$multi_root/long/추적" "$multi_root/long/본문" "$multi_root/short"
setup_git_repo "$multi_root"
copy_hooks "$multi_root"
printf 'long\n' > "$multi_root/.active-book"
printf '长篇正文\n' > "$multi_root/long/본문/제1장.md"
printf '短篇正文\n' > "$multi_root/short/본문.md"
multi_out="$(run_from_nested "$multi_root" detect-story-gaps.sh || true)"
echo "$multi_out" | grep -q '^检查：long$' || fail "detect-story-gaps did not inspect long project when .active-book is set"
echo "$multi_out" | grep -q '^检查：short$' || fail "detect-story-gaps did not inspect short project alongside long project"
long_count="$(printf '%s\n' "$multi_out" | grep -c '^检查：long$' || true)"
[ "$long_count" -eq 1 ] || fail "detect-story-gaps reported long project $long_count times; expected exactly once"
echo "  OK TS8 multi-book gap detection"

# TS10 — 버전 임계값 + 배포 동작 기준점
# 실행 시 실제로 고장 나는 항목만 고정한다. agents_version 임계값은 파일 간 일치하고 사용자에게 배포되는
# 에이전트 템플릿에는 핵심 동작 규칙이 있어야 한다. 이전에는 UPGRADING.md/README에 특정 문구가 있어야 한다는
# 문서 완전성 단언도 있었지만 단어 하나만 바꿔도 실패하고 동작이 아닌 표현을 검사하므로 check-story-long-write-contract.sh와
# 함께 제거했다. 릴리스 시 UPGRADING 보완 여부는 릴리스 목록과 사람이 판단하며 CI로 문구를 고정하지 않는다.
# session-start의 신구 버전 분기는 TS5 실제 실행에서, story-review 사전 검사와 프런트매터 version은
# check-current-skill-contracts.py에서 검증하므로 여기서 grep을 반복하지 않는다.
assert_grep "agents_version.*小于 \`$CURRENT_AGENTS_VERSION\`|版本 < $CURRENT_AGENTS_VERSION|agents_version.*\`$CURRENT_AGENTS_VERSION\` 미만" "$SKILL_DIR/SKILL.md" "story-setup redeploy branch must treat agents_version $PREVIOUS_AGENTS_VERSION as stale"
assert_grep "agents_version.*大于 \`$CURRENT_AGENTS_VERSION\`|agents_version.*\`$CURRENT_AGENTS_VERSION\`보다 큼" "$SKILL_DIR/SKILL.md" "story-setup must stop before downgrading a newer deployment"

# 1단계 자체 점검 디렉터리 목록은 하드코딩되어 실제 references/ 하위 디렉터리 집합과 일치해야 한다.
# 하나 빠지면 불완전 설치를 놓치고, 삭제된 디렉터리가 남으면 정상 패키지를 불완전하다고 판단해 모든 배포를 차단한다.
selfcheck_line="$(grep -nE '先自检参考目录|참고 디렉터리부터 자체 확인' "$SKILL_FILE" | head -1 | cut -d: -f1)"
[ -n "$selfcheck_line" ] || fail "story-setup Phase 1 reference self-check paragraph not found"
selfcheck_text="$(sed -n "${selfcheck_line}p" "$SKILL_FILE")"
for ref_dir in "$SKILL_DIR"/references/*/; do
  ref_name="$(basename "$ref_dir")"
  case "$selfcheck_text" in
    *"\`$ref_name\`"*) ;;
    *) fail "story-setup Phase 1 self-check list is missing reference dir: $ref_name" ;;
  esac
done
case "$selfcheck_text" in
  *'`references/deploy-*.md`'*) ;;
  *) fail "story-setup Phase 1 self-check must also require the host deploy files" ;;
esac
listed_ref_dirs="$(printf '%s\n' "$selfcheck_text" | grep -oE '`[a-z][a-z-]*`' | tr -d '`')"
[ -n "$listed_ref_dirs" ] || fail "story-setup Phase 1 self-check list names no reference dirs"
for ref_name in $listed_ref_dirs; do
  [ -d "$SKILL_DIR/references/$ref_name" ] || fail "story-setup Phase 1 self-check lists a reference dir that does not exist: $ref_name"
done
assert_grep '플롯/감정모듈\.md.*missing_primary_contract|missing_primary_contract.*플롯/감정모듈\.md' "$AGENT_REFS_DIR/benchmark-style-load.md" "story-explorer must require the current emotion-module artifact"
assert_grep '플롯/리듬\.md.*missing_primary_contract|missing_primary_contract.*플롯/리듬\.md' "$AGENT_REFS_DIR/benchmark-style-load.md" "story-explorer must require the current rhythm artifact"
assert_grep 'missing_primary_contract: true|missing_primary_contract": true' "$AGENT_REFS_DIR/benchmark-style-load.md" "story-explorer must emit missing_primary_contract for broken canonical artifacts"
assert_grep 'repair_action.*Stage 3|Stage 3.*repair_action|重跑 /story-long-analyze Stage 3' "$AGENT_REFS_DIR/benchmark-style-load.md" "story-explorer must provide a repair action instead of silent fallback"
# 비교 기준 검색 절차는 benchmark_style_load에서만 읽으며 템플릿에는 참조만 둔다. context_load는 호출자가 없어 삭제했다.
assert_grep 'agent-references/benchmark-style-load\.md' "$SKILL_DIR/references/templates/agents/story-explorer.md" "story-explorer must route benchmark_style_load to its agent reference"
assert_no_grep 'missing_primary_contract|context_load' "$SKILL_DIR/references/templates/agents/story-explorer.md" "story-explorer template must not inline the benchmark recall flow or the removed context_load"
# 인계는 저장된 파일로만 한다. 에이전트는 작업 간 영구 기억을 갖지 않는다(memory는 Write/Edit를 암묵적으로 열기도 한다).
for agent_template in "$SKILL_DIR"/references/templates/agents/*.md; do
  assert_no_grep '^memory:' "$agent_template" "agent templates must not enable persistent agent memory"
done
assert_grep 'missing_primary_contract' "$REPO_ROOT/skills/story-long-write/references/project-files.md" "story-long-write must not silently fallback for missing primary artifacts"
assert_grep '内容概括（五段式）|情节安排（多线）|人物关系和出场顺序|结尾设定和钩子' "$SKILL_DIR/references/templates/agents/story-architect.md" "story-architect must output v13 chapter blueprint fields"
assert_grep '逻辑线|人物关系变化|行动成本（可无）/收益归属|结尾设定' "$SKILL_DIR/references/templates/agents/consistency-checker.md" "consistency-checker must consume current outline blueprint fields"
assert_grep '语气标点谱系|말투별 문장부호 체계' "$SKILL_DIR/references/templates/agents/narrative-writer.md" "narrative-writer must enforce v13 tone punctuation"
assert_grep '不用.*……|不使用.*……|不保留.*……|不残留.*……|…….*쓰지 않|…….*억지 멈춤을 만들지 않' "$SKILL_DIR/references/templates/agents/narrative-writer.md" "narrative-writer must reject ellipsis pause punctuation"
assert_grep '不用.*——|不使用.*——|不保留.*——|不残留.*——|——.*쓰지 않' "$SKILL_DIR/references/templates/agents/narrative-writer.md" "narrative-writer must reject dialogue dash exception"
assert_grep '语气标点谱系|말투별 문장부호 체계' "$AGENT_REFS_DIR/format-and-structure.md" "agent references must include v13 tone punctuation format rules"
assert_grep '不用.*……|不使用.*……|不保留.*……|不残留.*……|…….*쓰지 않|…….*억지 멈춤을 만들지 않' "$AGENT_REFS_DIR/format-and-structure.md" "agent references must forbid ellipsis pause punctuation"
assert_grep '不用.*——|不使用.*——|不保留.*——|不残留.*——|正文和对话都禁止.*——|——.*억지 멈춤을 만들지 않' "$AGENT_REFS_DIR/format-and-structure.md" "agent references must forbid dialogue dash exception"
# AI 문체 제거 방법은 세 계층에서 같은 원본으로 배포한다. 동작 기준은 방법과 실제 수정 평가에서 검증하고 배포 검사는 읽기 가능한 인터페이스만 확인한다.
for deslop_method in expression narrative-focus story-logic; do
  assert_grep "agent-references/$deslop_method\\.md" "$SKILL_DIR/references/templates/agents/narrative-writer.md" "narrative-writer must load the $deslop_method method"
  assert_grep "$deslop_method\\.md" "$AGENT_REFS_DIR/deslop-gates.md" "deslop scope interface must route to $deslop_method"
  cmp -s "$AGENT_REFS_DIR/$deslop_method.md" "$REPO_ROOT/skills/story-deslop/references/$deslop_method.md" || fail "deployed deslop method is stale: $deslop_method"
done
assert_no_grep 'anti-ai-writing\.md' "$SKILL_DIR/references/templates/agents/narrative-writer.md" "narrative-writer must not load the removed deslop guide"
assert_grep 'check-ai-patterns\.js --check' "$SKILL_DIR/references/templates/agents/narrative-writer.md" "narrative-writer must require detector rescan handoff"
assert_grep '裸调用.*不得自动进入正文写作|不得自动进入正文写作.*裸调用|인수 없이 호출.*본문 집필에 자동 진입.*안 됩니다' "$REPO_ROOT/skills/story-long-write/SKILL.md" "story-long-write bare invocation must not auto-write prose"
assert_grep '不得把已有项目默认为日更 3 章|默认为日更 3 章|기존 프로젝트를 기본 일일 연재 3장으로 간주하면 안 됩니다' "$REPO_ROOT/skills/story-long-write/SKILL.md" "story-long-write must not default existing projects to daily 3 chapters on bare invocation"
assert_grep '默认停在细纲交付|最远停在细纲交付|默认停靠.*Phase 1→3|상세 개요 전달까지만 진행하며 본문을 자동 작성하지 않음' "$REPO_ROOT/skills/story-long-write/SKILL.md" "story-long-write opening flow must stop after outline by default"
assert_grep '本轮 K（最多 3 章）后必须进入 Step 3/4 收尾并停止|最多 3 章.*收尾并停止|최대 3장.*반드시 Step 3/4로 마무리하고 멈추' "$REPO_ROOT/skills/story-long-write/references/workflow-daily.md" "daily workflow must stop after bounded batch"
assert_grep '细纲边界|不得自造剧情|상세 개요가 유일한 줄거리 설계도' "$SKILL_DIR/references/templates/agents/narrative-writer.md" "narrative-writer must enforce the outline boundary"
# 원본 템플릿을 기준으로 한다. OpenCode/Codex 생성본은 sync-opencode.py --check와 Codex 생성기 결정론적 검사로 일치시킨다.
assert_grep '`under` 不补.*`over`.*`compress-once`|`under`는 보충하지 않고.*`over`.*`compress-once`' "$SKILL_DIR/references/templates/agents/narrative-writer.md" "narrative-writer must keep asymmetric wordcount handling"
assert_grep 'over 单次压缩.*净删.*不增语义|`over`.*한 차례 압축.*의미를 늘리지 않고 순수 삭제' "$SKILL_DIR/references/templates/agents/narrative-writer.md" "narrative-writer must keep one-pass semantic-preserving compression"
assert_grep '导入续写入口顺序|推荐顺序.*story-setup|가져온 뒤 이어 쓰는 순서.*story-setup' "$REPO_ROOT/skills/story-import/SKILL.md" "story-import must answer setup-vs-import order before asking for source"
# 가져오기는 작가의 작업 시점별로 파일을 나눈다. 절차 질의응답과 이전 추적 재구축은 import-special-cases.md로 옮기고 작가 결정은 가져오기 기록에 저장한다.
assert_grep '推荐顺序.*story-setup|권장 순서.*story-setup' "$REPO_ROOT/skills/story-import/references/import-special-cases.md" "story-import special cases must keep the setup-vs-import answer"
assert_grep '只需重建 `추적/`|`추적/`만 재구축' "$REPO_ROOT/skills/story-import/references/import-special-cases.md" "story-import must rebuild legacy tracking without re-analyzing the book"
assert_grep '\.story/work/가져오기기록\.md' "$REPO_ROOT/skills/story-import/SKILL.md" "story-import must persist author decisions to the import record"
assert_grep '超过约 25K 字时脚本自动少排几章|약 25K자를 넘으면 장 수를 자동으로 줄이며' "$REPO_ROOT/skills/story-import/references/outline-reverse.md" "story-import must reverse outlines in bounded batches"
echo "  OK TS10 version + behavior anchors"

# TS11 — 본문 전에 개요를 요구하는 쓰기 보호(차단형 PreToolUse 훅)
guard_root="$TMP_DIR/outline-guard"
mkdir -p "$guard_root/book/본문" "$guard_root/book/개요" "$guard_root/book/설정" \
         "$guard_root/short" "$guard_root/docs" \
         "$guard_root/impbook/본문" "$guard_root/작품분석실/impbook" \
         "$guard_root/impshort" "$guard_root/작품분석실/impshort"
setup_git_repo "$guard_root"
copy_hooks "$guard_root"
assert_file "$guard_root/.claude/hooks/guard-outline-before-prose.sh"

run_guard() {
  # $1 = file_path; 훅 종료 코드를 출력한다(0 허용, 2 차단).
  local fp="$1" ec=0
  printf '{"tool_name":"Write","tool_input":{"file_path":"%s","content":"x"}}' "$fp" \
    | CLAUDE_PROJECT_DIR="$guard_root" bash "$guard_root/.claude/hooks/guard-outline-before-prose.sh" >/dev/null 2>&1 || ec=$?
  printf '%s' "$ec"
}

run_bash_guard() {
  # $1 = Bash 명령; 훅 종료 코드를 출력한다(0 허용, 2 차단).
  local command_text="$1" ec=0 payload
  payload="$(python3 - "$command_text" <<'PY'
import json, sys
print(json.dumps({"tool_name": "Bash", "tool_input": {"command": sys.argv[1]}}, ensure_ascii=False))
PY
)"
  printf '%s' "$payload" \
    | CLAUDE_PROJECT_DIR="$guard_root" bash "$guard_root/.claude/hooks/guard-outline-before-prose.sh" >/dev/null 2>&1 || ec=$?
  printf '%s' "$ec"
}

# 장편 허용 흐름: 상세 개요 없음 → 차단 / 있음 → 허용 / 장 번호 앞자리 0 허용
[ "$(run_guard 'book/본문/제1장_开端.md')" = "2" ] || fail "guard did not BLOCK long prose when 细纲 missing"
write_outline "$guard_root/book/개요/상세개요_제1장.md"
# 상세 개요가 갖춰져도 추적 점검을 통과해야 한다(이슈 #305부터 Claude에도 다른 세 환경과 같은 순서로 적용).
# 이 절은 상세 개요와 경로 분류를 검사하므로 유효한 state를 먼저 저장해 추적 조건을 고정한다.
# last_committed는 이 절의 모든 사례 장 번호보다 큰 값으로 둔다. 추적 범위 안의 장은 순서 검사를 건너뛰므로
# 1/7/123/124장은 상세 개요 조건으로만 판정된다. 순서 검사 자체는 test-prose-net-parity.sh D부의
# 시나리오 행렬에서 다루며 여기서 반복하지 않는다.
mkdir -p "$guard_root/book/추적"
printf '{"schema_version":4,"state_revision":0,"last_committed_chapter":200}\n' > "$guard_root/book/추적/_tracking-state.json"
printf '> 状态修订：0。\n' > "$guard_root/book/추적/문맥.md"
[ "$(run_guard 'book/본문/제1장_开端.md')" = "0" ] || fail "guard wrongly blocked long prose when 细纲 present"
# 추적 조건 자체: state를 옮기면 차단한다(이전 Claude는 조용히 허용해 추적 없는 본문을 작성했다).
mv "$guard_root/book/추적/_tracking-state.json" "$guard_root/book/추적/_state.bak"
[ "$(run_guard 'book/본문/제1장_开端.md')" = "2" ] || fail "guard did not BLOCK long prose when tracking state missing"
mv "$guard_root/book/추적/_state.bak" "$guard_root/book/추적/_tracking-state.json"
[ "$(run_guard 'book/본문/제001장_开端.md')" = "0" ] || fail "guard did not tolerate chapter-number zero padding (제001장 vs 상세개요_제1장)"
write_outline "$guard_root/book/개요/상세개요_제7장_惊变.md"
[ "$(run_guard 'book/본문/제7장_x.md')" = "0" ] || fail "guard did not tolerate title-suffixed 细纲 (상세개요_제7장_惊变.md)"
# 단편 허용 흐름: 설정.md 신호 + 절 개요 없음 → 차단; 절 개요 추가 → 허용
: > "$guard_root/short/설정.md"
[ "$(run_guard 'short/본문.md')" = "2" ] || fail "guard did not BLOCK short prose when 구간개요.md missing"
: > "$guard_root/short/구간개요.md"
[ "$(run_guard 'short/본문.md')" = "0" ] || fail "guard wrongly blocked short prose when 구간개요.md present"
# 작품 외 파일 / 단편 프로젝트 신호 없음 → 허용(오차단보다 차단 누락을 택함)
[ "$(run_guard 'book/설정/인물.md')" = "0" ] || fail "guard wrongly blocked a non-prose file"
[ "$(run_guard 'docs/본문.md')" = "0" ] || fail "guard wrongly blocked a non-story 본문.md (no 설정.md signal)"
# 기존 본문 있음 → 허용(이어 쓰기/수정/AI 문체 제거)
: > "$guard_root/book/본문/제9장_x.md"
[ "$(run_guard 'book/본문/제9장_x.md')" = "0" ] || fail "guard wrongly blocked rewrite of an existing prose file"
# story-import 이전 흐름: 작품분석실/{书名}/ 원본이 있으면 본문을 전체/절 개요보다 먼저 이전하도록 허용한다.
[ "$(run_guard 'impbook/본문/제1장_x.md')" = "0" ] || fail "guard wrongly blocked story-import LONG prose migration (拆文库 source present)"
: > "$guard_root/impshort/설정.md"
[ "$(run_guard 'impshort/본문.md')" = "0" ] || fail "guard wrongly blocked story-import SHORT prose migration (拆文库 source present)"
# Bash 명령: 실제 본문 쓰기만 차단하며 경로 언급만으로 오차단하지 않는다. 8장은 상세 개요가 없어 쓰기를 차단해야 한다.
if command -v node >/dev/null 2>&1; then
  [ "$(run_bash_guard 'cat draft.md > book/본문/제8장_x.md')" = "2" ] \
    || fail "Claude Bash write bypassed prose pre-guard"
  [ "$(run_bash_guard 'grep -n book/본문/제8장_x.md notes.md')" = "0" ] \
    || fail "Claude Bash read-only mention was wrongly blocked"
  # 상세 개요 누락 안내는 앞자리 0을 채운 표준 이름을 쓴다. 대상에 미확장 셸 변수가 있어도 차단하되 경로 해석 실패라고 설명한다.
  pad_err="$(printf '{"tool_name":"Write","tool_input":{"file_path":"book/본문/제8장_x.md","content":"x"}}' \
    | CLAUDE_PROJECT_DIR="$guard_root" bash "$guard_root/.claude/hooks/guard-outline-before-prose.sh" 2>&1 >/dev/null || true)"
  printf '%s' "$pad_err" | grep -q '상세개요_제008장\.md' || fail "missing-outline block must name the zero-padded outline file: $pad_err"
  var_payload="$(python3 - <<'PY'
import json
print(json.dumps({"tool_name": "Bash", "tool_input": {"command": 'PROJ=$PWD/book; cat draft.md > "$PROJ/본문/제8장_x.md"'}}, ensure_ascii=False))
PY
)"
  var_ec=0
  var_err="$(printf '%s' "$var_payload" \
    | CLAUDE_PROJECT_DIR="$guard_root" bash "$guard_root/.claude/hooks/guard-outline-before-prose.sh" 2>&1 >/dev/null)" || var_ec=$?
  [ "$var_ec" = "2" ] || fail "Claude Bash write behind an unexpanded shell variable must stay blocked"
  printf '%s' "$var_err" | grep -q '치환되지 않은 셸 변수' || fail "shell-variable target block must say the path was not resolved: $var_err"

  # Bash 상대 대상은 항상 프로젝트 루트가 아닌 훅 cwd 기준으로 해석한다. 루트 book에는 8장 상세 개요가 있고 nested/book에는 없다.
  write_outline "$guard_root/book/개요/상세개요_제8장.md"
  mkdir -p "$guard_root/nested/book/본문"
  cwd_payload="$(python3 - "$guard_root/nested" <<'PY'
import json, sys
print(json.dumps({"cwd": sys.argv[1], "tool_name": "Bash", "tool_input": {"command": "cat > book/본문/제8장_x.md"}}, ensure_ascii=False))
PY
)"
  cwd_ec=0
  printf '%s' "$cwd_payload" \
    | CLAUDE_PROJECT_DIR="$guard_root" bash "$guard_root/.claude/hooks/guard-outline-before-prose.sh" >/dev/null 2>&1 || cwd_ec=$?
  [ "$cwd_ec" = "2" ] || fail "Claude Bash relative target ignored hook cwd"

  # 공유 코어가 손상되면 허용 상태를 유지하되 명시적으로 경고한다. 런타임 오류를 쓰기 대상 없음으로 위장하면 안 된다.
  cp "$guard_root/.claude/hooks/story_hook_core.js" "$guard_root/.claude/hooks/story_hook_core.js.bak"
  printf '%s\n' 'throw new Error("broken core fixture")' > "$guard_root/.claude/hooks/story_hook_core.js"
  broken_payload="$(python3 - <<'PY'
import json
print(json.dumps({"tool_name": "Bash", "tool_input": {"command": "cat > book/본문/제8장_x.md"}}, ensure_ascii=False))
PY
)"
  broken_ec=0
  broken_err="$(printf '%s' "$broken_payload" \
    | CLAUDE_PROJECT_DIR="$guard_root" bash "$guard_root/.claude/hooks/guard-outline-before-prose.sh" 2>&1 >/dev/null)" || broken_ec=$?
  mv "$guard_root/.claude/hooks/story_hook_core.js.bak" "$guard_root/.claude/hooks/story_hook_core.js"
  [ "$broken_ec" = "0" ] || fail "broken Bash guard core must preserve documented fail-open behavior"
  printf '%s' "$broken_err" | grep -q '보호 검사에서 해석에 실패했습니다' \
    || fail "broken Bash guard core was silently ignored: $broken_err"
fi
echo "  OK TS11 outline-before-prose guard"

# TS11b — node가 없으면 차단 보호는 순수 bash 추출로 대체해 여전히 exit 2여야 한다(실패 시 허용 금지).
# 공식 권장은 Node 없는 네이티브 바이너리 Claude Code 설치이며 npm 설치에만 node가 있다. 이전 구현은 node만 탐지해
# 없으면 허용하므로 상세 개요 없는 본문 쓰기가 조용히 통과했다(#243 회귀). 항상 0이 아닌 값을 반환하는 가짜 node로
# node 사용 불가를 재현하고 나머지 도구(sed/grep/bash)는 PATH에 둔다. 일부 Windows에서 가짜 도구가 실제 node를 가리지 못하면
# 환경 때문에 거짓 실패하지 않도록 건너뛴다.
nonode_shim="$TMP_DIR/nonode-shim"
mkdir -p "$nonode_shim"
printf '#!/bin/sh\nexit 1\n' > "$nonode_shim/node"
chmod +x "$nonode_shim/node"
run_guard_nonode() {
  local fp="$1" ec=0
  printf '{"tool_name":"Write","tool_input":{"file_path":"%s","content":"x"}}' "$fp" \
    | CLAUDE_PROJECT_DIR="$guard_root" PATH="$nonode_shim:$PATH" \
      bash "$guard_root/.claude/hooks/guard-outline-before-prose.sh" >/dev/null 2>&1 || ec=$?
  printf '%s' "$ec"
}
if ! PATH="$nonode_shim:$PATH" node -e "" >/dev/null 2>&1; then
  # 상세 개요 없음 → 여전히 차단(bash 대체 경로가 대상 경로를 추출하고 정상적으로 exit 2)
  [ "$(run_guard_nonode 'book/본문/제123장_无纲.md')" = "2" ] \
    || fail "guard fail-OPEN without node (regression #243): 缺细纲写正文必须仍拦截（bash 兜底）"
  # 빈 상세 개요 → 여전히 차단(빈 개요 검사는 순수 bash 바이트 수 계산으로 node에 의존하지 않음)
  : > "$guard_root/book/개요/상세개요_제123장.md"
  [ "$(run_guard_nonode 'book/본문/제123장_无纲.md')" = "2" ] \
    || fail "guard(no-node) must block long prose when 细纲 is empty (纯 bash 空细纲门)"
  write_outline "$guard_root/book/개요/상세개요_제123장.md"
  # 상세 개요 있음 → 허용(bash 대체 경로가 오차단하지 않음)
  [ "$(run_guard_nonode 'book/본문/제123장_无纲.md')" = "0" ] \
    || fail "guard(no-node) wrongly blocked long prose when 细纲 present (bash 兜底)"
  # 본문이 아닌 대상 → 허용
  [ "$(run_guard_nonode 'book/설정/인물.md')" = "0" ] \
    || fail "guard(no-node) wrongly blocked a non-prose file (bash 兜底)"
  echo "  OK TS11b outline guard fail-closed without node"
else
  echo "  SKIP TS11b (假 node 垫片未能遮蔽真 node，跳过 no-node 回归)"
fi

# TS11c — node가 있어도 추출에 실패하면(이전 node가 node: 접두어를 모르거나 배포 코어 손상으로 탐색 통과 후 실행 오류)
# 차단 보호는 순수 bash로 대체해 exit 2여야 한다. 이전 if/else는 node 탐색만 통과하면 node 분기로만 가서 추출이 비면 허용했다.
# #243 재검토에서 발견한 두 번째 실패 시 허용 경로다. 가짜 도구가 node -e 빈 문자열에는 0, 실제 스크립트에는 비0을 반환하게 한다.
# 해석된 node가 실제로 가짜 도구임을 확인한 경우만 실행한다(실제 node라면 잘못된 이유로 단언이 통과할 수 있음).
brokennode_shim="$TMP_DIR/brokennode-shim"
mkdir -p "$brokennode_shim"
printf '#!/bin/sh\n[ "$1" = "-e" ] && exit 0\nexit 1\n' > "$brokennode_shim/node"
chmod +x "$brokennode_shim/node"
run_guard_brokennode() {
  local fp="$1" ec=0
  printf '{"tool_name":"Write","tool_input":{"file_path":"%s","content":"x"}}' "$fp" \
    | CLAUDE_PROJECT_DIR="$guard_root" PATH="$brokennode_shim:$PATH" \
      bash "$guard_root/.claude/hooks/guard-outline-before-prose.sh" >/dev/null 2>&1 || ec=$?
  printf '%s' "$ec"
}
resolved_node="$(PATH="$brokennode_shim:$PATH" bash -c 'command -v node' 2>/dev/null || true)"
if [ "$resolved_node" = "$brokennode_shim/node" ]; then
  # node 탐색 통과 후 CLI 추출 오류 → 상세 개요가 없으면 여전히 차단(bash 대체 경로로 대상 해석)
  [ "$(run_guard_brokennode 'book/본문/제124장_坏node.md')" = "2" ] \
    || fail "guard fail-OPEN with broken node (regression #243): node 在但抽取失败时必须回落 bash 仍拦截"
  write_outline "$guard_root/book/개요/상세개요_제124장.md"
  # 상세 개요 있음 → 허용(bash 대체 경로가 오차단하지 않음)
  [ "$(run_guard_brokennode 'book/본문/제124장_坏node.md')" = "0" ] \
    || fail "guard(broken-node) wrongly blocked long prose when 细纲 present (bash 兜底)"
  echo "  OK TS11c outline guard fail-closed when node present-but-broken"
else
  echo "  SKIP TS11c (假 node 垫片未能遮蔽真 node，跳过 broken-node 回归)"
fi

# TS12 — 에이전트 재시작 대기 상태의 일회성 확인
restart_root="$TMP_DIR/restart-flag"
mkdir -p "$restart_root/.claude"
setup_git_repo "$restart_root"
copy_hooks "$restart_root"
copy_agent_refs "$restart_root"
write_sentinel "$restart_root"
touch "$restart_root/.claude/.agents-pending-restart"
restart_out="$(run_from_nested "$restart_root" session-start.sh || true)"
echo "$restart_out" | grep -q '现已注册可用' || fail "session-start did not confirm agents registered after restart flag"
[ ! -f "$restart_root/.claude/.agents-pending-restart" ] || fail "session-start did not clear the one-shot .agents-pending-restart flag"
echo "  OK TS12 restart-flag confirmation"

echo ""
echo "OK: story-setup deployment checks passed"
