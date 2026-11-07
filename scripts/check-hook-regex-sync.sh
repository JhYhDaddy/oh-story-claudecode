#!/bin/bash
# check-hook-regex-sync.sh — detect-story-gaps.sh의 복선 상태 탐지를 동작 수준에서 검증한다.
#
# 설계 의도: SessionStart 훅은 기한이 지났거나 비정상인 복선만 알린다. 장편에서 유효한 정상 상태를
# (설치됨/회수됨/포기) 문제로 오인해 일일 작업에서 복선 전체 감사를 유발하지 않도록 한다.
# 실제 훅 테스트 데이터를 실행해 정상 상태는 경고하지 않고 기한 경과/비정상 상태는 경고하는지 검증한다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

HOOK_FILE="$REPO_ROOT/skills/story-setup/references/templates/hooks/detect-story-gaps.sh"
COMMON_FILE="$REPO_ROOT/skills/story-setup/references/templates/hooks/lib/common.sh"
PROTOCOL_FILE="$REPO_ROOT/skills/story-long-write/scripts/tracking_commit.py"

for file in "$HOOK_FILE" "$COMMON_FILE" "$PROTOCOL_FILE"; do
  if [ ! -f "$file" ]; then
    echo "FAIL: required file not found: $file"
    exit 1
  fi
done

STATUS_ENUM=$(sed -n 's/^FORESHADOW_STATUSES = (\(.*\))$/\1/p' "$PROTOCOL_FILE" 2>/dev/null | head -1 | tr -d '" ' | tr ',' '/' || true)
if [ -z "$STATUS_ENUM" ]; then
  echo "FAIL: No foreshadow status enum found in protocol file"
  exit 1
fi

echo "Protocol defines status values: $STATUS_ENUM"

TMP_DIR=$(mktemp -d)
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

setup_fixture() {
  local name="$1"
  local foreshadow_body="$2"
  local root="$TMP_DIR/$name"
  mkdir -p "$root/.claude/hooks/lib" "$root/book/추적" "$root/book/본문" "$root/book/설정" "$root/book/개요"
  cp "$HOOK_FILE" "$root/.claude/hooks/detect-story-gaps.sh"
  cp "$COMMON_FILE" "$root/.claude/hooks/lib/common.sh"
  chmod +x "$root/.claude/hooks/detect-story-gaps.sh"
  touch "$root/.story-deployed"
  cat > "$root/book/추적/문맥.md" <<'CTX'
# 写作进度
## 当前位置
- 章: 第1章
CTX
  # 표 머리글의 상태 열거는 $STATUS_ENUM에서 펼치며 별도로 복사하지 않는다. 프로토콜에 상태를 추가하면 테스트 데이터도 바뀐다.
  # 그렇지 않으면 새 상태는 동작 테스트를 거치지 않는다(머리글 자체는 훅의 ^状态\{ 분기에서 건너뛴다).
  cat > "$root/book/추적/복선.md" <<EOF_FORESHADOW
# 伏笔追踪

## 伏笔状态表

| ID | 伏笔内容 | 埋设章节 | 预计回收章节 | 状态{$STATUS_ENUM} | 重要度{高/中/低} |
|----|---------|---------|-------------|-----------------------------|----------------|
$foreshadow_body
EOF_FORESHADOW
  printf '%s' "$root"
}

run_hook() {
  local root="$1"
  (cd "$root" && bash .claude/hooks/detect-story-gaps.sh)
}

assert_no_foreshadow_warn() {
  local case_name="$1"
  local body="$2"
  local root output
  root=$(setup_fixture "$case_name" "$body")
  output=$(run_hook "$root" || true)
  if echo "$output" | grep -q '伏笔'; then
    echo "FAIL: $case_name should not emit foreshadow warning"
    echo "Output:"
    echo "$output"
    exit 1
  fi
  echo "  OK no warn: $case_name"
}

assert_foreshadow_warn() {
  local case_name="$1"
  local body="$2"
  local root output
  root=$(setup_fixture "$case_name" "$body")
  output=$(run_hook "$root" || true)
  if ! echo "$output" | grep -q '检测到过期或异常的伏笔条目'; then
    echo "FAIL: $case_name should emit overdue/abnormal foreshadow warning"
    echo "Output:"
    echo "$output"
    exit 1
  fi
  echo "  OK warn: $case_name"
}

assert_no_foreshadow_warn "header-only" ""

plain_header_root="$TMP_DIR/plain-header"
mkdir -p "$plain_header_root/.claude/hooks/lib" "$plain_header_root/book/추적" "$plain_header_root/book/본문" "$plain_header_root/book/설정" "$plain_header_root/book/개요"
cp "$HOOK_FILE" "$plain_header_root/.claude/hooks/detect-story-gaps.sh"
cp "$COMMON_FILE" "$plain_header_root/.claude/hooks/lib/common.sh"
chmod +x "$plain_header_root/.claude/hooks/detect-story-gaps.sh"
cat > "$plain_header_root/book/추적/복선.md" <<'EOF_PLAIN_HEADER'
# 伏笔追踪

| ID | 名称 | 埋下 | 回收 | 状态 | 备注 |
|----|------|------|------|------|------|
| F001 | 玉佩 | 第1章 | 第20章 | 已埋 | ok |
EOF_PLAIN_HEADER
plain_header_output=$(run_hook "$plain_header_root" || true)
if echo "$plain_header_output" | grep -q '伏笔'; then
  echo "FAIL: plain-header should not emit foreshadow warning"
  echo "Output:"
  echo "$plain_header_output"
  exit 1
fi
echo "  OK no warn: plain-header"

assert_no_foreshadow_warn "normal-open-planted" "| F002 | 正常开放伏笔 | 第1章 | 第20章 | 已埋 | 高 |"
assert_no_foreshadow_warn "closed-recovered" "| F003 | 已回收伏笔 | 第1章 | 第3章 | 已回收 | 低 |"
assert_no_foreshadow_warn "closed-abandoned" "| F006 | 已放弃伏笔 | 第1章 | 第3章 | 放弃 | 低 |"
assert_foreshadow_warn "overdue" "| F004 | 过期伏笔 | 第1章 | 第2章 | 已过期 | 高 |"
assert_foreshadow_warn "retired-unplanted-status" "| F001 | 尚未真正埋设 | 第5章 | 第10章 | 未埋 | 中 |"
assert_foreshadow_warn "unknown-status" "| F005 | 异常状态 | 第1章 | 第2章 | 状态损坏 | 高 |"

# 모든 프로토콜 상태가 훅의 awk 분류기에서 명시적으로 분류되는지 확인한다.
# 명시적인 경고 상태(status == "X") 또는 정상 상태(status != "X")여야 한다.
# 이전 두 번째 조건은 STATUS_ENUM을 추출한 바로 그 PROTOCOL_FILE에서 검색하므로
# 항상 일치해 반복문 전체가 절대 실패할 수 없었다. 프로토콜에만 상태를 추가하고
# 훅에 반영하지 않으면 분류기의 else로 빠져 매 SessionStart마다 비정상으로
# 보고된다. 이런 불일치는 반드시 검사를 실패시켜야 한다.
for state in $(echo "$STATUS_ENUM" | tr '/' ' '); do
  if ! grep -qF "status == \"$state\"" "$HOOK_FILE" \
    && ! grep -qF "status != \"$state\"" "$HOOK_FILE"; then
    echo "FAIL: protocol status not classified by hook: $state"
    echo "  add status == \"$state\" (warn) or status != \"$state\" (normal) to the 伏笔 awk in $HOOK_FILE"
    exit 1
  fi
done

echo ""
echo "OK: hook foreshadow detection warns only on overdue/abnormal states"

# ── 유해 문형 / 보완 검사망의 JS↔Python 정규식 및 상수 동기화 고정 ─────────────
# 작성 후 본문 검사망의 결정론적 규칙은 JS 공유 코어 story_hook_core.js와 codex story_codex_hook.py에 각각
# 같은 구조로 구현된다. 문구는 test-prose-net-parity.sh A부 데이터의 문자별 diff로 고정하지만 일부 문자 집합
# 선택지와 선택 그룹만 다루므로 한쪽에서 문자 하나를 삭제하거나 `|X` 분기/플래그를 바꿔도 모두 통과할 수 있다.
# 따라서 양쪽 상수표를 실제 파싱(JS 정규식/문자열/배열 리터럴 대 Python AST)해 항목별 완전 일치를 비교한다.
#   - 정규식 본문이 문자별로 같아야 한다(분기/문자 추가·삭제 시 실패). 라벨, 수정 안내, 순서도 비교한다.
#   - 모든 플래그 고정: JS 리터럴 플래그는 대조표 등록값과 같고 Python re 플래그는 JS 플래그에서 g를 뺀 값과 같다.
#   - 양쪽 TOXIC_*/SOFT_PATTERNS/HARD_PATTERNS와 _TOXIC_*/_NET_* 상수를 모두 등록해야 하며 한쪽만 추가하면 실패한다.
# 이후 변이 테스트로 한쪽의 불일치를 잡는지 증명한다(이전 버전은 기준 문자열 존재만 검색해 뒤에 분기를 붙여도 통과했다).
JS_CORE="$REPO_ROOT/skills/story-setup/references/templates/hooks/story_hook_core.js"
PY_HOOK="$REPO_ROOT/skills/story-setup/references/codex/hooks/story_codex_hook.py"
for file in "$JS_CORE" "$PY_HOOK"; do
  if [ ! -f "$file" ]; then
    echo "FAIL: required file not found: $file"
    exit 1
  fi
done
PYBIN=""
for cand in python3 python py; do
  if "$cand" -c "" >/dev/null 2>&1; then PYBIN="$cand"; break; fi
done
[ -n "$PYBIN" ] || { echo "FAIL: 需要 Python 解析 js↔py 常量表"; exit 1; }

REGEX_SYNC="$TMP_DIR/regex_sync.py"
cat > "$REGEX_SYNC" <<'PY'
import ast
import json
import re
import sys

# JS 상수명 -> (Python 상수명, JS 정규식 리터럴 필수 flags). 플래그를 완전히 고정해 JS 문자열은 여기 값과
# 문자별로 같고 Python 플래그는 JS에서 g를 뺀 것과 같아야 한다(g는 JS 반복 방식이며 Python finditer/search와 동등).
PAIRS = {
    "TOXIC_QUOTE_SPANS": ("_TOXIC_QUOTE_SPANS", "g"),
    "TOXIC_QUOTE_CHARS": ("_TOXIC_QUOTE_CHARS", None),
    "TOXIC_CLAUSE_BOUNDARY": ("_TOXIC_CLAUSE_BOUNDARY", None),
    "TOXIC_TAG_PARTICLES": ("_TOXIC_TAG_PARTICLES", None),
    "TOXIC_AFFIRM_PARTICLES": ("_TOXIC_AFFIRM_PARTICLES", None),
    "TOXIC_TRAILER_WINDOW": ("_TOXIC_TRAILER_WINDOW", None),
    "TOXIC_SENTENCE_PATTERNS": ("_TOXIC_SENTENCE_PATTERNS", "g"),
    "TOXIC_TRAILER_PATTERN": ("_TOXIC_TRAILER", ""),
    "TOXIC_TRAILER_SUMMARY_PATTERN": ("_TOXIC_TRAILER_SUMMARY", ""),
    "TOXIC_REVERSE_TAIL": ("_TOXIC_REVERSE_TAIL", ""),
    "TERMINAL": ("_NET_TERMINAL", None),
    "SOFT_PATTERNS": ("_NET_SOFT_PATTERNS", ""),
    "HARD_PATTERNS": ("_NET_HARD_PATTERNS", ""),
    "UNEXPANDED_SHELL_VAR": ("UNEXPANDED_SHELL_VAR", ""),
    "OUTLINE_MIN_CHARS": ("_OUTLINE_MIN_CHARS", None),
}
# 두 접두어 그룹의 상수는 모두 PAIRS에 등록해야 한다. 한쪽에만 유해 문형/보완 규칙을 추가해도 불일치다.
JS_FAMILY = re.compile(r"^(TOXIC_[A-Z_]+|SOFT_PATTERNS|HARD_PATTERNS)$")
PY_FAMILY = re.compile(r"^(_TOXIC_[A-Z_]+|_NET_[A-Z_]+)$")
PY_FLAG = {"IGNORECASE": "i", "I": "i", "MULTILINE": "m", "M": "m", "DOTALL": "s", "S": "s",
           "UNICODE": "u", "U": "u", "ASCII": "a", "A": "a", "VERBOSE": "x", "X": "x"}


class JsParser:
    def __init__(self, text: str, pos: int):
        self.s = text
        self.i = pos

    def skip(self) -> None:
        s = self.s
        while self.i < len(s):
            if s[self.i] in " \t\r\n":
                self.i += 1
            elif s.startswith("//", self.i):
                self.i = s.index("\n", self.i)
            elif s.startswith("/*", self.i):
                self.i = s.index("*/", self.i) + 2
            else:
                return

    def value(self):
        self.skip()
        s, c = self.s, self.s[self.i]
        if c == "/":
            return self.regex()
        if c in "\"'":
            return self.string()
        if c == "[":
            self.i += 1
            items = []
            while True:
                self.skip()
                if s[self.i] == "]":
                    self.i += 1
                    return items
                items.append(self.value())
                self.skip()
                if s[self.i] == ",":
                    self.i += 1
        if s.startswith("new Set(", self.i):
            self.i += len("new Set(")
            inner = self.value()
            self.expect(")")
            return inner
        if s.startswith("Array.from(", self.i):
            self.i += len("Array.from(")
            inner = self.value()
            self.expect(")")
            return inner
        m = re.compile(r"\d+").match(s, self.i)
        if m:
            self.i = m.end()
            return int(m.group(0))
        raise SystemExit(f"regex-sync: 无法解析的 JS 常量值: {s[self.i:self.i + 40]!r}")

    def expect(self, ch: str) -> None:
        self.skip()
        if self.s[self.i] != ch:
            raise SystemExit(f"regex-sync: JS 常量期望 {ch!r}: {self.s[self.i:self.i + 40]!r}")
        self.i += 1

    def regex(self):
        s, i = self.s, self.i + 1
        in_class = False
        while True:
            c = s[i]
            if c == "\\":
                i += 2
                continue
            if c == "\n":
                raise SystemExit("regex-sync: JS 正则字面量未闭合")
            if c == "[":
                in_class = True
            elif c == "]":
                in_class = False
            elif c == "/" and not in_class:
                break
            i += 1
        body = s[self.i + 1:i]
        m = re.compile(r"[a-z]*").match(s, i + 1)
        self.i = m.end()
        return ("re", body, m.group(0))

    def string(self):
        s, q, i = self.s, self.s[self.i], self.i + 1
        while s[i] != q:
            i += 2 if s[i] == "\\" else 1
        raw = s[self.i + 1:i]
        self.i = i + 1
        if q == "'":
            raw = raw.replace("\\'", "'").replace('"', '\\"')
        return json.loads('"' + raw + '"')


def js_constants(path: str) -> dict:
    text = open(path, encoding="utf-8").read()
    out = {}
    for m in re.finditer(r"^const ([A-Z_]+) = ", text, re.M):
        name = m.group(1)
        if name in PAIRS or JS_FAMILY.match(name):
            out[name] = JsParser(text, m.end()).value()
    return out


def py_value(node):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        return [py_value(x) for x in node.elts]
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "set" and len(node.args) == 1:
            return py_value(node.args[0])
        if isinstance(func, ast.Attribute) and func.attr == "compile" and isinstance(func.value, ast.Name) and func.value.id == "re":
            flags_node = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == "flags"), None)
            return ("re", py_value(node.args[0]), "".join(sorted(py_flags(flags_node))))
    raise SystemExit(f"regex-sync: 无法解析的 py 常量值: {ast.dump(node)[:80]}")


def py_flags(node) -> set:
    if node is None:
        return set()
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return py_flags(node.left) | py_flags(node.right)
    if isinstance(node, ast.Attribute) and node.attr in PY_FLAG:
        return {PY_FLAG[node.attr]}
    raise SystemExit(f"regex-sync: 无法解析的 py 正则 flags: {ast.dump(node)[:80]}")


def py_constants(path: str) -> dict:
    tree = ast.parse(open(path, encoding="utf-8").read())
    wanted = {py for py, _ in PAIRS.values()}
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name, value = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            name, value = node.target.id, node.value
        else:
            continue
        if name in wanted or PY_FAMILY.match(name):
            out[name] = py_value(value)
    return out


def regexes(value):
    if isinstance(value, tuple) and value and value[0] == "re":
        yield value
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from regexes(item)


def strip_g(value):
    if isinstance(value, tuple) and value and value[0] == "re":
        return ("re", value[1], "".join(sorted(set(value[2]) - {"g"})))
    if isinstance(value, list):
        return [strip_g(v) for v in value]
    return value


def main(js_path: str, py_path: str) -> int:
    js, py = js_constants(js_path), py_constants(py_path)
    errors = []
    for name in sorted(set(js) - set(PAIRS)):
        errors.append(f"JS 常量 {name} 未登记到 js↔py 对照表（单端新增规则）")
    known_py = {p for p, _ in PAIRS.values()}
    for name in sorted(set(py) - known_py):
        errors.append(f"py 常量 {name} 未登记到 js↔py 对照表（单端新增规则）")
    for js_name, (py_name, js_flags) in PAIRS.items():
        if js_name not in js:
            errors.append(f"JS 缺常量 {js_name}")
            continue
        if py_name not in py:
            errors.append(f"py 缺常量 {py_name}")
            continue
        jv, pv = js[js_name], py[py_name]
        if js_flags is not None:
            found = list(regexes(jv))
            if not found:
                errors.append(f"{js_name} 里没抽到正则字面量")
            for _, body, flags in found:
                if flags != js_flags:
                    errors.append(f"{js_name} 的 JS 正则 flags 应为 {js_flags!r}，实为 {flags!r}：/{body[:30]}…/")
        if strip_g(jv) != pv:
            errors.append(f"{js_name} ↔ {py_name} 不一致：\n    js={strip_g(jv)!r}\n    py={pv!r}")
    if errors:
        for e in errors:
            sys.stdout.buffer.write(f"FAIL: 毒句式/兜底网 js↔py 漂移 — {e}\n".encode("utf-8"))
        return 1
    n = sum(len(list(regexes(v))) for v in js.values())
    sys.stdout.buffer.write(f"regex-sync: {len(PAIRS)} 组常量、{n} 条正则 js↔py 逐字相等（含 flags）\n".encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
PY

toxic_fail=0
"$PYBIN" "$REGEX_SYNC" "$JS_CORE" "$PY_HOOK" || toxic_fail=1

# 변이 테스트: 한쪽의 모든 불일치는 위 비교를 실패시켜야 한다. 배열 주석 추가 같은 무관한 변경은 오탐하면 안 된다.
mutate() { # $1 원본 파일 $2 출력 $3 이전 문자열 $4 새 문자열(이전 문자열은 정확히 한 번 있어야 함)
  "$PYBIN" - "$1" "$2" "$3" "$4" <<'PY'
import sys
src, dst, old, new = sys.argv[1:5]
text = open(src, encoding="utf-8").read()
if text.count(old) != 1:
    sys.stderr.buffer.write(f"mutation anchor not unique ({text.count(old)}): {old}\n".encode("utf-8"))
    sys.exit(2)
open(dst, "w", encoding="utf-8", newline="").write(text.replace(old, new))
PY
}
expect_mutation() { # $1 설명 $2 기대값(fail|pass) $3 js|py $4 이전 문자열 $5 새 문자열
  local js="$JS_CORE" py="$PY_HOOK" out="$TMP_DIR/mutant" rc=0
  if [ "$3" = js ]; then mutate "$JS_CORE" "$out.js" "$4" "$5" || { echo "FAIL: 变异锚点失效：$1"; toxic_fail=1; return; }; js="$out.js"
  else mutate "$PY_HOOK" "$out.py" "$4" "$5" || { echo "FAIL: 变异锚点失效：$1"; toxic_fail=1; return; }; py="$out.py"; fi
  "$PYBIN" "$REGEX_SYNC" "$js" "$py" >/dev/null 2>&1 || rc=$?
  if [ "$2" = fail ] && [ "$rc" -eq 0 ]; then echo "FAIL: 同步锁没抓到单端漂移：$1"; toxic_fail=1; fi
  if [ "$2" = pass ] && [ "$rc" -ne 0 ]; then echo "FAIL: 同步锁误报无关改动：$1"; toxic_fail=1; fi
}
expect_mutation "JS 句式正则末尾追加分支" fail js '[却但偏]/g, "voice-contrast"' '[却但偏]|X/g, "voice-contrast"'
expect_mutation "py 预告收尾正则末尾追加分支" fail py '即将(?:开始|来临|降临)")' '即将(?:开始|来临|降临)|X")'
expect_mutation "JS 正则加 i flag" fail js '即将(?:开始|来临|降临)/
' '即将(?:开始|来临|降临)/i
'
expect_mutation "JS 句式正则去掉 g flag" fail js '[却但偏]/g, "voice-contrast"' '[却但偏]/, "voice-contrast"'
expect_mutation "py 正则加 IGNORECASE" fail py '[却但偏]"), "voice-contrast"' '[却但偏]", re.IGNORECASE), "voice-contrast"'
expect_mutation "JS 分句边界集多一个字符" fail js 'const TOXIC_CLAUSE_BOUNDARY = new Set(Array.from("' 'const TOXIC_CLAUSE_BOUNDARY = new Set(Array.from("X'
expect_mutation "JS 单端新增一条문제 문장 패턴常量" fail js 'const TOXIC_REVERSE_TAIL = ' 'const TOXIC_EXTRA_PATTERN = /x/
const TOXIC_REVERSE_TAIL = '
expect_mutation "py 修法文案漂移" fail py '"negation-parade", "‘없다, 없다’식 나열을 하나만 남기거나 모두 지우고' '"negation-parade", "‘없다, 없다’식 나열을 하나만 남기고'
expect_mutation "py 窗口 600→500" fail py '_TOXIC_TRAILER_WINDOW = 600' '_TOXIC_TRAILER_WINDOW = 500'
expect_mutation "JS 兜底网数组里加一行注释（无关改动）" pass js 'const HARD_PATTERNS = [
' 'const HARD_PATTERNS = [
  // 无关注释
'

# 미해결 조건의 제외 마커와 안내 문구는 JS↔Python에서 동기화한다. Claude bash 사전 조건(guard-outline-before-prose.sh)의
# 판정과 문구는 test-prose-net-parity.sh D부가 실제 쓰기 시나리오별로 고정한다.
GATE_SYNC=(
  '<!--[ \t]*去味[ \t]*(：|:)[ \t]*跳过[ \t]*-->'
  '미수정 문제 문장'
  '<!-- 去味:跳过 -->를 추가하고 다시 시도'
)
for needle in "${GATE_SYNC[@]}"; do
  for file in "$JS_CORE" "$PY_HOOK"; do
    if ! grep -Fq -- "$needle" "$file"; then
      echo "FAIL: 欠账门规范串缺失/漂移 — 「${needle}」未出现在 $(basename "$file")"
      toxic_fail=1
    fi
  done
done
# storyctl chapter check의 제외 판정과 훅은 같은 마커 구문을 쓴다(작가가 한 방식으로 표시하면 양쪽 모두 인식).
STORYCTL="$REPO_ROOT/skills/story-long-write/scripts/storyctl.py"
if ! grep -Fq -- "${GATE_SYNC[0]}" "$STORYCTL"; then
  echo "FAIL: 豁免标记语法漂移 — 「${GATE_SYNC[0]}」未出现在 storyctl.py"
  toxic_fail=1
fi
if [ "$toxic_fail" -ne 0 ]; then
  exit 1
fi

echo "OK: 毒句式正则、常量表与欠账门标记/文案 js↔py↔storyctl 逐字同步"
