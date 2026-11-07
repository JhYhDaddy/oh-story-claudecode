#!/usr/bin/env bash
# test-codex-hooks.sh — 합성 입력을 사용한 Codex 훅 계약 테스트.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
# 상세 개요에 내용이 있어야(#과 공백 제외 30자 이상) 본문 쓰기를 허용한다. 빈 파일은 빈 상세 개요로 차단한다.
write_outline() { printf '%s\n' '# 细纲' '江晨在雨夜推开旧书店的门，发现柜台后坐着失踪三年的师父，两人对视良久。' > "$1"; }

HOOKS_SRC="$REPO_ROOT/skills/story-setup/references/codex/hooks"
HOOK_SRC="$HOOKS_SRC/story_codex_hook.py"
ROOT="$TMP_DIR/story-project"
HOOK="$ROOT/.codex/hooks/story_codex_hook.py"
mkdir -p "$ROOT/.codex/hooks"
cp "$HOOK_SRC" "$HOOK"
cp "$HOOKS_SRC/run-story-hook.sh" "$HOOKS_SRC/run-story-hook.cmd" "$ROOT/.codex/hooks/"
chmod +x "$HOOK"

git -C "$ROOT" init -q
git -C "$ROOT" config user.email codex-hook@example.invalid
git -C "$ROOT" config user.name codex-hook-test

run_hook() {
  local event="$1" payload="$2"
  (cd "$ROOT" && printf '%s' "$payload" | CODEX_PROJECT_DIR="$ROOT" python3 "$HOOK" "$event")
}

# 훅 stdout은 로캘로 디코딩하지 말고 UTF-8 바이트로 읽는다. 훅은 UTF-8 중국어 거부 사유를 출력하지만
# Windows Python의 stdin 기본값은 ANSI 코드 페이지라
# 올바른 출력이어도 여기서 UnicodeDecodeError가 발생할 수 있다.
assert_json() {
  python3 -c 'import json,sys; json.loads(sys.stdin.buffer.read().decode("utf-8"))' >/dev/null
}

assert_denied() {
  local out="$1" label="$2"
  printf '%s' "$out" | assert_json || fail "$label did not emit valid JSON: $out"
  printf '%s' "$out" | python3 -c 'import json,sys; o=json.loads(sys.stdin.buffer.read().decode("utf-8")); h=o.get("hookSpecificOutput",{}); assert h.get("hookEventName")=="PreToolUse" and h.get("permissionDecision")=="deny" and h.get("permissionDecisionReason")' || fail "$label was not denied: $out"
}

assert_additional_context() {
  local out="$1" label="$2"
  printf '%s' "$out" | assert_json || fail "$label did not emit valid JSON: $out"
  printf '%s' "$out" | python3 -c 'import json,sys; o=json.loads(sys.stdin.buffer.read().decode("utf-8")); h=o.get("hookSpecificOutput",{}); assert h.get("additionalContext")' || fail "$label missing additionalContext: $out"
}

assert_empty() {
  local out="$1" label="$2"
  [ -z "$out" ] || fail "$label expected empty allow output, got: $out"
}

write_clean_state() {
  mkdir -p "$1/추적"
  printf '{"schema_version":4,"state_revision":0,"last_committed_chapter":%s}\n' "${2:-0}" > "$1/추적/_tracking-state.json"
  printf '%s\n' '> 状态修订：0' > "$1/추적/문맥.md"
}

echo "Codex hook synthetic tests"
echo "=========================="
echo "Fixture: $ROOT"

mkdir -p "$ROOT/book/본문" "$ROOT/book/개요" "$ROOT/book/설정"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Bash","tool_input":{"command":"cat > book/본문/제001장_开端.md <<EOF\n正文\nEOF"}}')"
assert_denied "$out" "long prose without outline"
printf '%s' "$out" | grep -q '상세개요_제001장\.md' || fail "missing-outline denial must name the zero-padded outline file: $out"
# 보호 로직이 대상 경로의 셸 변수를 확장하지 못하면 차단하되 상세 개요 누락이 아닌 경로 해석 실패로 안내한다.
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Bash","tool_input":{"command":"PROJ=$PWD/book; cat > \"$PROJ/본문/제001장_开端.md\" <<EOF\n正文\nEOF"}}')"
assert_denied "$out" "prose target behind an unexpanded shell variable"
printf '%s' "$out" | grep -q '치환되지 않은 셸 변수' || fail "shell-variable target denial must say the path was not resolved: $out"
if printf '%s' "$out" | grep -q '상세 개요가 없습니다'; then fail "shell-variable target must not be reported as a missing outline: $out"; fi
write_outline "$ROOT/book/개요/상세개요_제1장.md"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Bash","tool_input":{"command":"cat > book/본문/제001장_开端.md <<EOF\n正文\nEOF"}}')"
assert_denied "$out" "long prose without tracking metadata"
printf '%s' "$out" | grep -q '_tracking-state.json이 없습니다' || fail "missing tracking denial did not explain re-import/init: $out"
write_clean_state "$ROOT/book"
# 상세 개요 파일은 있으나 제목뿐으로 비어 있으면 차단하고 비어 있다는 점과 채울 내용을 설명한다.
printf '%s\n' '# 제1장 细纲' '## 目标情绪' > "$ROOT/book/개요/상세개요_제1장.md"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Bash","tool_input":{"command":"cat > book/본문/제001장_开端.md <<EOF\n正文\nEOF"}}')"
assert_denied "$out" "long prose with an empty outline"
printf '%s' "$out" | grep -q '상세 개요(book/개요/상세개요_제1장.md)가 비어 있습니다' || fail "empty-outline denial must say the outline is empty: $out"
write_outline "$ROOT/book/개요/상세개요_제1장.md"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Bash","tool_input":{"command":"cat > book/본문/제001장_开端.md <<EOF\n正文\nEOF"}}')"
assert_empty "$out" "long prose with outline"

mkdir -p "$ROOT/bare/본문" "$ROOT/cwd-book/본문" "$ROOT/cwd-book/개요"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Write","tool_input":{"file_path":"bare/본문/제1장_首章.md"}}')"
assert_denied "$out" "bare long project without scaffolding"
relative_payload="$(python3 - "$ROOT/cwd-book" <<'PY'
import json, sys
from pathlib import Path
payload = {"cwd": str(Path(sys.argv[1]).resolve()), "tool_name": "Write", "tool_input": {"file_path": "본문/제8장_相对.md"}}
sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
PY
)"
out="$(run_hook pre-tool-prose-guard "$relative_payload")"
assert_denied "$out" "relative prose target from hook cwd"
printf '%s' "$out" | grep -q 'cwd-book/개요' || fail "relative target was not resolved from hook cwd: $out"
write_outline "$ROOT/cwd-book/개요/상세개요_제8장.md"
out="$(run_hook pre-tool-prose-guard "$relative_payload")"
assert_denied "$out" "relative prose target without tracking metadata"
write_clean_state "$ROOT/cwd-book" 7
out="$(run_hook pre-tool-prose-guard "$relative_payload")"
assert_empty "$out" "relative prose target with cwd-local outline"

out="$(run_hook pre-tool-prose-guard '{"tool_name":"apply_patch","tool_input":{"command":"*** Begin Patch\n*** Add File: book/본문/제002장_新局.md\n+본문\n*** End Patch\n"}}')"
assert_denied "$out" "apply_patch long prose without outline"
: > "$ROOT/book/본문/제009장_已存在.md"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Write","tool_input":{"file_path":"book/본문/제009장_已存在.md","content":"改稿"}}')"
assert_empty "$out" "existing prose rewrite"
printf '%s\n' '{"schema_version":4,"state_revision":1,"last_committed_chapter":0}' > "$ROOT/book/추적/_tracking-state.json"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Write","tool_input":{"file_path":"book/본문/제009장_已存在.md","content":"改稿"}}')"
assert_denied "$out" "existing prose rewrite with mismatched derived state"
printf '%s' "$out" | grep -q 'mode=revision 트랜잭션을 다시 제출해 파생 문서를 재구성' || fail "state mismatch denial missed retry action: $out"
write_clean_state "$ROOT/book"

mkdir -p "$ROOT/short"
: > "$ROOT/short/설정.md"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Write","tool_input":{"file_path":"short/본문.md","content":"본문"}}')"
assert_denied "$out" "short prose without outline"
: > "$ROOT/short/구간개요.md"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Write","tool_input":{"file_path":"short/본문.md","content":"본문"}}')"
assert_empty "$out" "short prose with outline"

mkdir -p "$ROOT/impbook/본문" "$ROOT/작품분석실/impbook"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Write","tool_input":{"file_path":"impbook/본문/제1장_导入.md","content":"본문"}}')"
assert_empty "$out" "story-import long migration"
mkdir -p "$ROOT/impbook/개요" "$ROOT/impbook/추적"
write_outline "$ROOT/impbook/개요/상세개요_제2장.md"
printf '%s\n' '{"schema_version":4,"state_revision":1,"last_committed_chapter":1}' > "$ROOT/impbook/추적/_tracking-state.json"
printf '%s\n' '> 状态修订：0' > "$ROOT/impbook/추적/문맥.md"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Write","tool_input":{"file_path":"impbook/본문/제2장_导入后续.md","content":"본문"}}')"
assert_denied "$out" "imported project must not permanently bypass invalid tracking guard"

echo "  OK outline-before-prose guard"

# 공유 파서의 전체 구문 행렬은 test-prose-net-parity.sh에 있다. 여기서는 Codex 어댑터가
# 쓰기 하나와 읽기 전용 언급 하나를 올바르게 전달하는지만 검증한다.
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Bash","tool_input":{"command":"grep -n book/본문/제7장.md notes.md"}}')"
assert_empty "$out" "command merely mentioning prose path is not denied"
out="$(run_hook pre-tool-prose-guard '{"tool_name":"Bash","tool_input":{"command":"cat draft.md > book/본문/제7장_x.md"}}')"
assert_denied "$out" "write to prose without outline is denied"

echo "  OK prose command-scan precision"

cat > "$ROOT/book/본문/제1장.md" <<'TXT'
年龄：18
TXT
cat > "$ROOT/short/본문.md" <<'TXT'
身高: 180
TXT
git -C "$ROOT" add book/본문/제1장.md short/본문.md
out="$(run_hook pre-tool-commit-advisory '{"tool_name":"Bash","tool_input":{"command":"git commit -m test"}}')"
assert_additional_context "$out" "commit advisory"
echo "$out" | grep -q '본문에 인물 속성을 직접 고정' || fail "commit advisory did not inspect staged markdown"
echo "$out" | grep -q 'short/본문.md' || fail "commit advisory missed short prose"
out="$(run_hook pre-tool-commit-advisory '{"tool_name":"Bash","tool_input":{"command":"echo git commit docs"}}')"
assert_empty "$out" "non-commit bash command"

echo "  OK commit advisory"

mkdir -p "$ROOT/book/추적"
cat > "$ROOT/.story-deployed" <<'TXT'
deployed_at: 2026-06-25T00:00:00Z
agents_version: 19
setup_skill_version: 1.2.9
target_cli: codex
resolver_strategy: project-local-skill-reference
references_dir: .codex/skills/story-setup/references/agent-references
TXT
printf 'book\n' > "$ROOT/.active-book"
printf '%s\n' '> 状态修订：0' > "$ROOT/book/추적/문맥.md"
out="$(run_hook session-start '{"hook_event_name":"SessionStart"}')"
assert_additional_context "$out" "session-start context"
echo "$out" | grep -q 'Active book' || fail "session-start did not mention active book"
printf '%s\n' '{"schema_version":4,"state_revision":1,"last_committed_chapter":0}' > "$ROOT/book/추적/_tracking-state.json"
out="$(run_hook session-start '{"hook_event_name":"SessionStart"}')"
assert_additional_context "$out" "session-start tracking mismatch warning"
echo "$out" | grep -q '상태 리비전' || fail "session-start missed tracking revision mismatch: $out"
write_clean_state "$ROOT/book"
out="$(run_hook pre-compact '{"hook_event_name":"PreCompact"}')"
printf '%s' "$out" | assert_json || fail "pre-compact invalid JSON: $out"
echo "$out" | grep -q 'Story Compact Summary' || fail "pre-compact missing summary"
out="$(run_hook post-compact '{"hook_event_name":"PostCompact"}')"
printf '%s' "$out" | assert_json || fail "post-compact invalid JSON: $out"
out="$(run_hook stop '{"hook_event_name":"Stop"}')"
printf '%s' "$out" | assert_json || fail "stop invalid JSON: $out"

echo "  OK session/compact/stop JSON"

# ── Stop 콘텐츠 검사: Codex에는 PostToolUse가 없어 턴 종료 시 git 변경 본문의 강한 신호를 재검사(가벼운 검사망) ──
# 잘린 새 장을 git 변경(untracked)으로 남기면 stop이 파일을 지목하고 잘림을 보고해야 한다. 변경 없는 파일은 재검사하지 않는다.
PAD6='江晨握紧拳头慢慢走向门口盘算着每一步。'  # Windows Python 텍스트 stdout의 cp1252 오류를 피하려고 bash로 반복 채운다.
printf '# 제6장\n\n%s\n他冲过去一拳砸在' "$PAD6$PAD6$PAD6$PAD6$PAD6$PAD6" > "$ROOT/book/본문/제006장_截断.md"
out="$(run_hook stop '{"hook_event_name":"Stop"}')"
printf '%s' "$out" | assert_json || fail "stop content-sweep invalid JSON: $out"
echo "$out" | grep -q '截断' || fail "stop did not flag truncated git-changed prose: $out"
echo "$out" | grep -q '제006장_截断.md' || fail "stop did not name the changed prose file: $out"
# 커밋 완료되어 git 변경이 없는 장은 재검사하지 않는다. 이번 턴 변경 집합만 다룬다.
git -C "$ROOT" add -A && git -C "$ROOT" commit -qm wip >/dev/null 2>&1
out="$(run_hook stop '{"hook_event_name":"Stop"}')"
printf '%s' "$out" | python3 -c 'import json,sys; o=json.loads(sys.stdin.buffer.read().decode("utf-8")); assert "截断" not in o.get("systemMessage","")' || fail "stop re-flagged already-committed prose: $out"
echo "  OK stop content sweep (git-changed only)"

# ── SessionStart 연속성: 추적 노후화(장을 썼으나 문맥.md가 뒤처짐) + 장 제목 중복 ──
mkdir -p "$ROOT/contbook/본문" "$ROOT/contbook/추적"
write_clean_state "$ROOT/contbook"
printf '旧上下文\n' > "$ROOT/contbook/추적/문맥.md"
sleep 1
printf '# 제1장 决战\n正文。\n' > "$ROOT/contbook/본문/제001장_决战.md"
printf '# 제2장 决战\n正文。\n' > "$ROOT/contbook/본문/제002장_决战.md"
out="$(run_hook session-start '{"hook_event_name":"SessionStart"}')"
assert_additional_context "$out" "session-start continuity"
echo "$out" | grep -q '이어 쓰기 상태 카드가 더 오래되었습니다' || fail "session-start missed 追踪 staleness: $out"
echo "$out" | grep -q '제목 중복' || fail "session-start missed dup-title: $out"
echo "  OK session-start continuity (追踪 staleness + dup-title)"

# 디렉터리 탐색은 권장 구조 깊이만 보고 node_modules/숨김 디렉터리에 들어가지 않는다. Bash/Python/공유 JS 코어가 같아야 한다.
DISCOVERY_ROOT="$TMP_DIR/discovery-root"
mkdir -p "$DISCOVERY_ROOT/shallow/추적" \
  "$DISCOVERY_ROOT/node_modules/fake/추적" \
  "$DISCOVERY_ROOT/.hidden/fake/추적" \
  "$DISCOVERY_ROOT/a/b/c/d/e/deep/추적"
python_discovered="$(python3 - "$HOOK_SRC" "$DISCOVERY_ROOT" <<'PY'
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("story_codex_hook", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = Path(sys.argv[2])
active = module.read_active_book(root)
all_books = "|".join(sorted(p.relative_to(root).as_posix() for p in module._discover_all_books(root)))
print(f"{active.relative_to(root).as_posix() if active else ''};{all_books}")
PY
)"
[ "$python_discovered" = "shallow;shallow" ] || fail "Codex discovery crossed depth/ignored dirs: $python_discovered"
node_discovered="$(node - "$HOOKS_SRC/../../templates/hooks/story_hook_core.js" "$DISCOVERY_ROOT" <<'JS'
const core = require(process.argv[2]);
const path = require("node:path");
const root = process.argv[3];
const active = core.discoverActiveBook(root);
const allBooks = core.discoverAllBooks(root).map((p) => path.relative(root, p).split(path.sep).join("/")).sort().join("|");
process.stdout.write(`${active ? path.relative(root, active).split(path.sep).join("/") : ""};${allBooks}`);
JS
)"
[ "$node_discovered" = "shallow;shallow" ] || fail "JS discovery crossed depth/ignored dirs: $node_discovered"
bash_discovered="$(CLAUDE_PROJECT_DIR="$DISCOVERY_ROOT" bash -s -- "$HOOKS_SRC/../../templates/hooks/lib/common.sh" "$DISCOVERY_ROOT" <<'SH'
source "$1"
root="$(project_root)"
active="$(discover_active_book)"
all_books="$(discover_all_books | while IFS= read -r p; do printf '%s\n' "${p#$root/}"; done | sort | paste -sd '|' -)"
printf '%s;%s' "${active#$root/}" "$all_books"
SH
)"
[ "$bash_discovered" = "shallow;shallow" ] || fail "Bash discovery crossed depth/ignored dirs: $bash_discovered"

# `.active-book`이 디렉터리 심볼릭 링크로 프로젝트 루트 밖을 가리킬 수 없다. 잘못된 선언은 모두 자동 탐색으로 대체한다.
OUTSIDE_BOOK="$TMP_DIR/outside-book"
mkdir -p "$OUTSIDE_BOOK/추적"
# Windows/MSYS에서 심볼릭 링크 권한이 없으면 ln -s가 조용히 디렉터리 복사로 바뀌어 탈출 상황을 재현하지 못하며
# 복사된 escape/追踪이 뒤쪽 깊이 단언에서 책으로 인식될 수 있다. 실제 심볼릭 링크를 얻었을 때만 실행한다.
if ln -s "$OUTSIDE_BOOK" "$DISCOVERY_ROOT/escape" 2>/dev/null && [ -L "$DISCOVERY_ROOT/escape" ]; then
  printf '%s\n' 'escape' > "$DISCOVERY_ROOT/.active-book"
  python_active="$(python3 - "$HOOK_SRC" "$DISCOVERY_ROOT" <<'PY'
import importlib.util, sys
from pathlib import Path
spec=importlib.util.spec_from_file_location("h",sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
r=Path(sys.argv[2]); p=m.read_active_book(r); print(p.relative_to(r).as_posix() if p else "")
PY
)"
  node_active="$(node - "$HOOKS_SRC/../../templates/hooks/story_hook_core.js" "$DISCOVERY_ROOT" <<'JS'
const c=require(process.argv[2]),p=require('node:path'),r=process.argv[3],v=c.discoverActiveBook(r);process.stdout.write(v?p.relative(r,v).split(p.sep).join('/'):"");
JS
)"
  bash_active="$(CLAUDE_PROJECT_DIR="$DISCOVERY_ROOT" bash -s -- "$HOOKS_SRC/../../templates/hooks/lib/common.sh" <<'SH'
source "$1"; discover_active_book
SH
)"
  [ "$python_active" = "shallow" ] || fail "Python accepted out-of-root .active-book symlink: $python_active"
  [ "$node_active" = "shallow" ] || fail "JS accepted out-of-root .active-book symlink: $node_active"
  DISCOVERY_REAL="$(cd "$DISCOVERY_ROOT" && pwd -P)"
  [ "$bash_active" = "$DISCOVERY_REAL/shallow" ] || fail "Bash accepted out-of-root .active-book symlink: $bash_active"
  rm -f "$DISCOVERY_ROOT/.active-book"
  rm -f "$DISCOVERY_ROOT/escape"
else
  # ln -s 실패 또는 복사로 대체된 경우 잔여물을 정리해 아래 maxdepth 4 탐색 단언을 오염시키지 않는다.
  rm -rf "$DISCOVERY_ROOT/escape"
fi

# `find -maxdepth 4` 경계: 마커 자체가 깊이 4이면 보이고 5이면 안 보인다. 세 구현에 한 단계 오차가 없어야 한다.
mkdir -p "$DISCOVERY_ROOT/a/b/book/추적" "$DISCOVERY_ROOT/a/b/c/book/추적"
python_books="$(python3 - "$HOOK_SRC" "$DISCOVERY_ROOT" <<'PY'
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("story_codex_hook", sys.argv[1])
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
root = Path(sys.argv[2])
print("|".join(sorted(p.relative_to(root).as_posix() for p in module._discover_all_books(root))))
PY
)"
node_books="$(node - "$HOOKS_SRC/../../templates/hooks/story_hook_core.js" "$DISCOVERY_ROOT" <<'JS'
const core = require(process.argv[2]); const path = require("node:path"); const root = process.argv[3];
process.stdout.write(core.discoverAllBooks(root).map((p) => path.relative(root,p).split(path.sep).join("/")).sort().join("|"));
JS
)"
bash_books="$(CLAUDE_PROJECT_DIR="$DISCOVERY_ROOT" bash -s -- "$HOOKS_SRC/../../templates/hooks/lib/common.sh" "$DISCOVERY_ROOT" <<'SH'
source "$1"; root="$(project_root)"
discover_all_books | while IFS= read -r p; do printf '%s\n' "${p#$root/}"; done | sort | paste -sd '|' -
SH
)"
[ "$python_books" = "a/b/book|shallow" ] || fail "Python depth-4 discovery mismatch: $python_books"
[ "$node_books" = "a/b/book|shallow" ] || fail "JS depth-4 discovery mismatch: $node_books"
[ "$bash_books" = "a/b/book|shallow" ] || fail "Bash depth-4 discovery mismatch: $bash_books"
echo "  OK bounded directory discovery (depth 4, hidden/node_modules pruned, Bash/JS/Python parity)"

nested="$ROOT/nested/a/b"
mkdir -p "$nested"
out="$(cd "$TMP_DIR" && printf '{"cwd":"%s","tool_name":"Write","tool_input":{"file_path":"book/본문/제003장_嵌套.md","content":"본문"}}' "$nested" | python3 "$HOOK" pre-tool-prose-guard)"
assert_denied "$out" "cwd-based root resolution"

echo "  OK cwd-based root resolution"

# 모든 플랫폼에서 __file__ 자체 위치 탐색(Windows 핵심 해석기)을 검사한다. 잘못된
# CODEX_PROJECT_DIR(환경 변수 무시)와 무관한 cwd에서도 훅은 자기 .codex/hooks/ 위치로부터
# 루트를 찾아야 한다. 실제 루트에는 상세 개요가 있어 잘못된 루트는 거부하고
# __file__ 기반 루트만 허용한다(위 유효 환경 변수 검사는 환경 변수가 우선해 이 경로를 거치지 않음).
write_outline "$ROOT/book/개요/상세개요_제8장.md"
write_clean_state "$ROOT/book" 7
out="$(cd "$TMP_DIR" && CODEX_PROJECT_DIR="$TMP_DIR/does-not-exist" python3 "$HOOK" pre-tool-prose-guard <<'JSON'
{"tool_name":"Write","tool_input":{"file_path":"book/본문/제8장_x.md","content":"x"}}
JSON
)"
assert_empty "$out" "__file__ self-location resolves root when env is bogus and cwd unrelated"
rm -f "$ROOT/book/개요/상세개요_제8장.md"

echo "  OK __file__ self-location (all platforms)"

NON_GIT="$TMP_DIR/non-git-story-project"
NON_GIT_HOOK="$NON_GIT/.codex/hooks/story_codex_hook.py"
mkdir -p "$NON_GIT/.codex/hooks" "$NON_GIT/book/본문" "$NON_GIT/book/개요" "$NON_GIT/nested/a/b"
cp "$HOOK_SRC" "$NON_GIT_HOOK"
cp "$HOOKS_SRC/run-story-hook.sh" "$HOOKS_SRC/run-story-hook.cmd" "$NON_GIT/.codex/hooks/"
cp "$REPO_ROOT/skills/story-setup/references/codex/hooks/hooks.json" "$NON_GIT/.codex/hooks.json"
launcher_cmd="$(
  NON_GIT="$NON_GIT" python3 - <<'PY'
import json, os
from pathlib import Path
hooks = json.loads((Path(os.environ["NON_GIT"]) / ".codex/hooks.json").read_text(encoding="utf-8"))
print(hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"])
PY
)"
out="$(
  cd "$NON_GIT/nested/a/b"
  printf '{"tool_name":"Write","tool_input":{"file_path":"book/본문/제004장_非Git.md","content":"본문"}}' | eval "$launcher_cmd"
)"
assert_denied "$out" "non-git deployment launcher root search"

echo "  OK non-git deployment launcher root search"

# 루트 전달: git 없는 프로젝트의 실제 루트에 개요가 있고 중첩 cwd에서 실행하면
# 허용해야 한다. 실행기가 셸에서 찾은 루트가 Python 훅에 전달되어야 하며
# (CODEX_PROJECT_DIR 또는 __file__ 자체 위치 탐색) Python이 중첩 cwd로 돌아가
# 잘못 거부하면 안 된다. Windows에서도 검사한다(Git Bash MSYS 경로를 네이티브 Python에 전달).
# 단순 환경 변수/cwd 전달이 실패하는 바로 그 상황이다.
write_outline "$NON_GIT/book/개요/상세개요_제4장.md"
write_clean_state "$NON_GIT/book" 3
out="$(cd "$NON_GIT/nested/a/b"; unset CODEX_PROJECT_DIR CLAUDE_PROJECT_DIR; printf '{"tool_name":"Write","tool_input":{"file_path":"book/본문/제004장_非Git.md","content":"본문"}}' | eval "$launcher_cmd")"
assert_empty "$out" "non-git nested cwd + outline present allows (root reaches Python hook)"
rm -f "$NON_GIT/book/개요/상세개요_제4장.md"

echo "  OK non-git nested root propagation"

case "$(uname -s 2>/dev/null || true)" in
  MINGW*|MSYS*|CYGWIN*)
    NON_GIT="$NON_GIT" python3 - <<'PY'
import json
import os
import subprocess
from pathlib import Path

root = Path(os.environ["NON_GIT"])
hooks = json.loads((root / ".codex/hooks.json").read_text(encoding="utf-8"))["hooks"]
command = hooks["PreToolUse"][0]["hooks"][0]["commandWindows"]
# bytes 리터럴은 ASCII여야 한다(중국어 바이트 리터럴은 SyntaxError). str을 만든 뒤 UTF-8로 인코딩한다.
payload = '{"tool_name":"Write","tool_input":{"file_path":"book/본문/제004장_非Git.md","content":"본문"}}'.encode("utf-8")
completed = subprocess.run(
    command,
    cwd=root / "nested/a/b",
    input=payload,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    shell=True,
    timeout=20,
)
assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
output = completed.stdout.decode("utf-8")
data = json.loads(output)
specific = data.get("hookSpecificOutput", {})
assert specific.get("permissionDecision") == "deny", output
PY
    echo "  OK commandWindows nested root + interpreter launcher"
    ;;
esac

# 배포 없음: cwd 조상에 .codex/hooks/story_codex_hook.py가 없으면 실행기는
# 조용히 아무 작업 없이 종료 0이어야 한다. "//.codex/hooks/story_codex_hook.py"를 실행하면 안 된다.
# (상위 탐색을 끝낸 뒤 "/"를 프로젝트 루트로 간주하면 이런 일이 발생한다.)
NO_DEPLOY="$TMP_DIR/no-deploy/x/y"
mkdir -p "$NO_DEPLOY"
out="$(cd "$NO_DEPLOY"; unset CODEX_PROJECT_DIR CLAUDE_PROJECT_DIR; printf '{"tool_name":"Write","tool_input":{"file_path":"book/본문/제1장.md","content":"본문"}}' | eval "$launcher_cmd" 2>&1)"
assert_empty "$out" "missing deployment launcher no-ops silently"
case "$out" in *//.codex*) fail "launcher executed //.codex/... on missing deployment: $out";; esac

echo "  OK missing-deployment launcher no-op"
echo ""
echo "OK: Codex hook synthetic tests passed"
