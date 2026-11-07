#!/bin/bash
# test-outline-copy.sh — 개요 베끼기 탐지기의 회귀 테스트.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
  echo "Error: not in a git repository" >&2
  exit 1
fi

SCRIPT="$REPO_ROOT/skills/story-long-write/scripts/check-outline-copy.js"

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

CASE=""
STATUS=0
OUTPUT=""

fail() {
  echo "FAIL [$CASE]: $1" >&2
  [ -n "$OUTPUT" ] && echo "--- detector output ---" >&2 && echo "$OUTPUT" >&2
  exit 1
}

run() {
  set +e
  OUTPUT="$(node "$SCRIPT" "$@" 2>&1)"
  STATUS=$?
  set -e
}

expect_status() {
  [ "$STATUS" -eq "$1" ] || fail "expected exit $1, got $STATUS"
}

expect_contains() {
  case "$OUTPUT" in
  *"$1"*) ;;
  *) fail "expected output to contain: $1" ;;
  esac
}

# Node로 Git Bash가 변환한 Windows 경로를 얻는다.
expect_path() {
  expect_contains "$(node -p 'process.argv[1]' "$1")"
}

expect_missing() {
  case "$OUTPUT" in
  *"$1"*) fail "expected output NOT to contain: $1" ;;
  *) ;;
  esac
}

# 허용되지 않은 22자 중복은 단독으로 15자 임계값을 넘는다.
COPIED="他握紧那柄旧刀在雨里站了整整一夜没有离开半步"
# 6자 기준 문장은 임계값보다 짧다. 이를 제거한 나머지도 임계값에 도달해야 잘못된 면제를 검증할 수 있다.
OATH="此誓天地可鉴"
VOW="虽死无悔"
# 18자 기준 문장은 자체로 임계값을 넘는다. 과도한 수정으로 허용이 깨지지 않았는지 검증한다.
# demo/长篇 1장의 시스템 보상 문자열에서 가져온 실제 기능적 중복 표본으로 문자별 일치가 정상이다.
PANEL="天王级唱功大师级导演能力中国军魂伴奏"

# --- 1. 기준 문장 앞에 임계값 초과 중복: 앞부분을 보고해야 하며 기준 문장이 포함됐다고 전체를 면제하면 안 됨 ---
CASE="anchor-tail"
cat >"$TMP_DIR/o1.md" <<EOF
#### 情节细化
- 点1：${COPIED}，${OATH}。
- 复沓锚句：
  点1：${OATH}
EOF
printf '%s，%s。\n' "$COPIED" "$OATH" >"$TMP_DIR/p1.md"
run --outline "$TMP_DIR/o1.md" "$TMP_DIR/p1.md"
expect_status 1
expect_contains "22 字「${COPIED}」"
expect_contains "1 处 6 字为复沓锚句"

# --- 2. 기준 문장 뒤에 임계값 초과 중복 ---
CASE="anchor-head"
cat >"$TMP_DIR/o2.md" <<EOF
#### 情节细化
- 点1：${OATH}，${COPIED}。
- 复沓锚句：
  点1：${OATH}
EOF
printf '%s，%s。\n' "$OATH" "$COPIED" >"$TMP_DIR/p2.md"
run --outline "$TMP_DIR/o2.md" "$TMP_DIR/p2.md"
expect_status 1
expect_contains "22 字「${COPIED}」"

# --- 3. 중복 조각에 기준 문장이 여러 개: 중간은 보고하고 양끝을 각각 제외 ---
CASE="multi-anchor"
cat >"$TMP_DIR/o3.md" <<EOF
#### 情节细化
- 点1：${OATH}，${COPIED}，${VOW}。
- 复沓锚句：
  点1：${OATH}
  点1：${VOW}
EOF
printf '%s，%s，%s。\n' "$OATH" "$COPIED" "$VOW" >"$TMP_DIR/p3.md"
run --outline "$TMP_DIR/o3.md" "$TMP_DIR/p3.md"
expect_status 1
expect_contains "22 字「${COPIED}」"
expect_contains "10 字为复沓锚句"

# --- 4. 조각이 기준 문장과 완전히 같음: 면제를 유지하고 조용히 허용하며 제외량 보고 ---
CASE="pure-anchor"
cat >"$TMP_DIR/o4.md" <<EOF
#### 情节细化
- 点1：面板弹出，主角确认奖励到手。
- 复沓锚句：
  点1：${PANEL}
EOF
printf '眼前忽然亮起一行小字。\n%s\n他抬手把那行字抹掉。\n' "$PANEL" >"$TMP_DIR/p4.md"
run --outline "$TMP_DIR/o4.md" "$TMP_DIR/p4.md"
expect_status 0
expect_contains "无未授权誊抄"
expect_contains "1 处 18 字"

# --- 5. 단편 표준 구조: 본문.md + 구간개요.md, 인수 하나로 자동 탐색해야 함 ---
CASE="short-story-autodiscover"
mkdir -p "$TMP_DIR/단편"
cat >"$TMP_DIR/단편/구간개요.md" <<EOF
## 第一节
- 点1：${COPIED}。
EOF
printf '%s。\n' "$COPIED" >"$TMP_DIR/단편/본문.md"
run "$TMP_DIR/단편/본문.md"
expect_status 1
expect_contains "22 字「${COPIED}」"

# --- 6. 장편 표준 구조: 본문/第N章 + 개요/상세개요_第N章, 인수 하나로 자동 탐색해야 함 ---
CASE="long-form-autodiscover"
mkdir -p "$TMP_DIR/장편/본문" "$TMP_DIR/장편/개요"
cat >"$TMP_DIR/장편/개요/상세개요_제001장.md" <<EOF
## 第 1 章
- 点1：${COPIED}。
EOF
printf '# 제001장 雨夜\n\n%s。\n' "$COPIED" >"$TMP_DIR/장편/본문/제001장_雨夜.md"
run "$TMP_DIR/장편/본문/제001장_雨夜.md"
expect_status 1
expect_contains "22 字「${COPIED}」"

# --- 7. 기존 상세 개요에 반복 기준 문장 필드 없음: 기준 문장 없음으로 처리하고 오류 없이 정상 검사 ---
CASE="legacy-no-anchor-field"
cat >"$TMP_DIR/o7.md" <<EOF
#### 情节细化
- 点1：${COPIED}，${OATH}。
EOF
printf '%s，%s。\n' "$COPIED" "$OATH" >"$TMP_DIR/p7.md"
run --outline "$TMP_DIR/o7.md" "$TMP_DIR/p7.md"
expect_status 1
expect_contains "28 字"
expect_missing "为复沓锚句"

# --- 8. 기준 문장 필드의 ‘无’는 기준 문장으로 취급하지 않음 ---
CASE="anchor-field-none"
cat >"$TMP_DIR/o8.md" <<EOF
#### 情节细化
- 点1：${COPIED}。
- 复沓锚句：无
- 结尾设定：主角离开。
EOF
printf '%s。\n' "$COPIED" >"$TMP_DIR/p8.md"
run --outline "$TMP_DIR/o8.md" "$TMP_DIR/p8.md"
expect_status 1
expect_contains "22 字「${COPIED}」"
expect_missing "为复沓锚句"

# --- 9. 본문과 상세 개요 중복 없음: 완전히 조용함 ---
CASE="clean"
cat >"$TMP_DIR/o9.md" <<EOF
#### 情节细化
- 点1：${COPIED}。
EOF
printf '雨停了，他终于肯回头看一眼身后那扇门。\n' >"$TMP_DIR/p9.md"
run --outline "$TMP_DIR/o9.md" "$TMP_DIR/p9.md"
expect_status 0
[ -z "$OUTPUT" ] || fail "expected silent output on a clean chapter"

# --- 10. 상세 개요 자동 탐색 실패: 명시적으로 건너뛰고 일반 독립 본문을 차단하지 않음 ---
CASE="missing-outline"
printf '%s。\n' "$COPIED" >"$TMP_DIR/orphan.md"
run "$TMP_DIR/orphan.md"
expect_status 0
expect_contains "跳过"
expect_path "$TMP_DIR/orphan.md"
expect_contains "未自动发现细纲"

# --- 11. 마무리 재검사에서 와일드카드로 여러 장 전달: 각각 비교하며 두 번째 본문을 상세 개요로 취급하지 않음 ---
CASE="multi-prose-batch"
mkdir -p "$TMP_DIR/批/본문" "$TMP_DIR/批/개요"
cat >"$TMP_DIR/批/개요/상세개요_제005장.md" <<EOF
## 第 5 章
- 点1：${COPIED}。
EOF
cat >"$TMP_DIR/批/개요/상세개요_제006장.md" <<EOF
## 第 6 章
- 点1：${VOW}，主角转身离开。
EOF
printf '# 제005장 雨夜\n\n%s。\n' "$COPIED" >"$TMP_DIR/批/본문/제005장_雨夜.md"
printf '# 제006장 天明\n\n雨停了，他终于肯回头看一眼身后那扇门。\n' >"$TMP_DIR/批/본문/제006장_天明.md"
run "$TMP_DIR/批/본문/제005장_雨夜.md" "$TMP_DIR/批/본문/제006장_天明.md"
expect_status 1
expect_contains "제005장_雨夜.md"
expect_contains "22 字「${COPIED}」"

# --- 12. 뒤쪽 장에만 중복: 첫 장이 정상이라고 전체 허용하지 않음 ---
CASE="multi-prose-later-hit"
run "$TMP_DIR/批/본문/제006장_天明.md" "$TMP_DIR/批/본문/제005장_雨夜.md"
expect_status 1
expect_contains "제005장_雨夜.md"

# --- 13. 명시한 상세 개요 없음: 경로 보고 후 종료 2 ---
CASE="explicit-missing-outline"
run --outline "$TMP_DIR/不存在的细纲.md" "$TMP_DIR/p9.md"
expect_status 2
expect_contains "无法读取显式细纲"
expect_path "$TMP_DIR/不存在的细纲.md"
expect_contains "不存在"

# --- 14. 본문 없음: 경로 보고 후 종료 2 ---
CASE="missing-prose"
run --outline "$TMP_DIR/o9.md" "$TMP_DIR/不存在的正文.md"
expect_status 2
expect_contains "无法读取正文"
expect_path "$TMP_DIR/不存在的正文.md"
expect_contains "不存在"

# --- 15~17. 인수 오류: --outline 값 누락, 알 수 없는 옵션, 본문 없음 모두 종료 2 ---
CASE="outline-option-without-value"
run --outline
expect_status 2
expect_contains "--outline 缺少路径"

CASE="unknown-option"
run --unknown "$TMP_DIR/p9.md"
expect_status 2
expect_contains "未知选项: --unknown"

CASE="no-prose"
run --outline "$TMP_DIR/o9.md"
expect_status 2
expect_contains "缺少正文路径"

# --- 18~19. 디렉터리 입력: 모든 플랫폼에서 일반 파일 아님을 보고 ---
CASE="outline-is-directory"
mkdir -p "$TMP_DIR/目录细纲"
run --outline "$TMP_DIR/目录细纲" "$TMP_DIR/p9.md"
expect_status 2
expect_contains "无法读取显式细纲"
expect_path "$TMP_DIR/目录细纲"
expect_contains "不是普通文件"

CASE="prose-is-directory"
mkdir -p "$TMP_DIR/目录正文"
run --outline "$TMP_DIR/o9.md" "$TMP_DIR/目录正文"
expect_status 2
expect_contains "无法读取正文"
expect_path "$TMP_DIR/目录正文"
expect_contains "不是普通文件"

# --- 20. 예상하지 못한 예외: 오류 보고 후 종료 2 ---
CASE="unexpected-exception"
printf '%s。\n' "$COPIED" >"$TMP_DIR/explode.md"
cat >"$TMP_DIR/throw-on-basename.js" <<'EOF'
const path = require('path')
const originalBasename = path.basename
path.basename = function basename(file, ...args) {
  if (originalBasename.call(this, file, ...args) === 'explode.md') throw new Error('synthetic unexpected failure')
  return originalBasename.call(this, file, ...args)
}
EOF
set +e
OUTPUT="$(node --require "$TMP_DIR/throw-on-basename.js" "$SCRIPT" "$TMP_DIR/explode.md" 2>&1)"
STATUS=$?
set -e
expect_status 2
expect_contains "细纲照搬检测异常"
expect_contains "synthetic unexpected failure"

# --- 21. 자동 탐색 권한 오류를 상세 개요 없음으로 위장하면 안 됨 ---
CASE="auto-outline-permission-error"
cat >"$TMP_DIR/throw-on-readdir.js" <<'JS'
const fs = require('fs')
const original = fs.readdirSync
fs.readdirSync = function (dir, ...args) {
  if (String(dir).endsWith('개요')) {
    const error = new Error(`EACCES: cannot read ${dir}`)
    error.code = 'EACCES'
    throw error
  }
  return original.call(this, dir, ...args)
}
JS
set +e
OUTPUT="$(node --require "$TMP_DIR/throw-on-readdir.js" "$SCRIPT" "$TMP_DIR/批/본문/제005장_雨夜.md" 2>&1)"
STATUS=$?
set -e
expect_status 2
expect_contains "EACCES"
expect_contains "개요"

# --- 22. 경로 발견 후 읽기 실패도 입력 오류이며 건너뛰면 안 됨 ---
CASE="discovered-outline-read-error"
cat >"$TMP_DIR/throw-on-outline-read.js" <<'JS'
const fs = require('fs')
const original = fs.readFileSync
fs.readFileSync = function (file, ...args) {
  if (String(file).endsWith('상세개요_제005장.md')) {
    const error = new Error(`EACCES: cannot read ${file}`)
    error.code = 'EACCES'
    throw error
  }
  return original.call(this, file, ...args)
}
JS
set +e
OUTPUT="$(node --require "$TMP_DIR/throw-on-outline-read.js" "$SCRIPT" "$TMP_DIR/批/본문/제005장_雨夜.md" 2>&1)"
STATUS=$?
set -e
expect_status 2
expect_contains "EACCES"
expect_contains "상세개요_제005장.md"

# --- 23. 자동 발견한 대상이 디렉터리여도 거부 ---
CASE="discovered-outline-is-directory"
mkdir -p "$TMP_DIR/非文件细纲/구간개요.md"
printf '%s。\n' "$COPIED" >"$TMP_DIR/非文件细纲/본문.md"
run "$TMP_DIR/非文件细纲/본문.md"
expect_status 2
expect_contains "不是普通文件"

# --- 24~27. 작성 후 완료 기록은 베끼기 원본이 아님. 일반/굵은 필드와 제목 하위 절 지원 ---
printf '%s。\n' "$COPIED" >"$TMP_DIR/completed-prose.md"
CASE="completion-heading"
printf '#### 实际完成情况\n%s。\n' "$COPIED" >"$TMP_DIR/completion.md"
run --outline "$TMP_DIR/completion.md" "$TMP_DIR/completed-prose.md"
expect_status 0

CASE="completion-field"
printf '%s\n' "- 实际完成情况：${COPIED}。" "- 结尾设定：离开。" >"$TMP_DIR/completion.md"
run --outline "$TMP_DIR/completion.md" "$TMP_DIR/completed-prose.md"
expect_status 0

CASE="completion-bold-field"
printf '%s\n' "- **实际完成情况**：" "  ${COPIED}。" "- 结尾设定：离开。" >"$TMP_DIR/completion.md"
run --outline "$TMP_DIR/completion.md" "$TMP_DIR/completed-prose.md"
expect_status 0

CASE="completion-nested-heading"
printf '#### 实际完成情况\n已完成。\n##### 实际落地\n%s。\n' "$COPIED" >"$TMP_DIR/completion.md"
run --outline "$TMP_DIR/completion.md" "$TMP_DIR/completed-prose.md"
expect_status 0

# --- 28~31. 완료 기록 제외가 기록 앞, 동급/상위 제목 뒤, 다음 필드의 실제 베끼기를 삼키면 안 됨 ---
CASE="copy-before-completion"
printf '#### 情节细化\n%s。\n#### 实际完成情况\n已完成。\n' "$COPIED" >"$TMP_DIR/completion.md"
run --outline "$TMP_DIR/completion.md" "$TMP_DIR/completed-prose.md"
expect_status 1
expect_contains "22 字「${COPIED}」"

CASE="copy-after-completion-peer-heading"
printf '#### 实际完成情况\n##### 实际落地\n已完成。\n#### 后续情节\n%s。\n' "$COPIED" >"$TMP_DIR/completion.md"
run --outline "$TMP_DIR/completion.md" "$TMP_DIR/completed-prose.md"
expect_status 1
expect_contains "22 字「${COPIED}」"

CASE="copy-after-completion-parent-heading"
printf '#### 实际完成情况\n##### 实际落地\n已完成。\n## 下一章\n%s。\n' "$COPIED" >"$TMP_DIR/completion.md"
run --outline "$TMP_DIR/completion.md" "$TMP_DIR/completed-prose.md"
expect_status 1
expect_contains "22 字「${COPIED}」"

CASE="copy-after-completion-field"
printf '%s\n' "- **实际完成情况**：已完成。" "- 结尾设定：${COPIED}。" >"$TMP_DIR/completion.md"
run --outline "$TMP_DIR/completion.md" "$TMP_DIR/completed-prose.md"
expect_status 1
expect_contains "22 字「${COPIED}」"

echo "PASS: check-outline-copy.js (31 cases)"
