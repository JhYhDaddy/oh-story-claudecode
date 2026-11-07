#!/bin/bash
# test-degeneration.sh — 모델 출력 퇴화 탐지기의 회귀 테스트.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
  echo "Error: not in a git repository" >&2
  exit 1
fi

SCRIPT="$REPO_ROOT/skills/story-deslop/scripts/check-degeneration.js"
TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

POS="$TMP_DIR/degen-positive.md"
NEG="$TMP_DIR/degen-negative.md"
OUT="$TMP_DIR/out.json"

# 양성: 인접한 전체 줄 반복 + 긴 문장 3회 반복 + AI 자기 지칭 + 괄호 생략 자리표시자 + 끝 잘림.
cat > "$POS" <<'EOF'
他握紧了拳头，慢慢站起身来，眼里全是不甘。
他握紧了拳头，慢慢站起身来，眼里全是不甘。
她看着窗外那场下了整夜的大雨，心里空落落的。
过了一会儿。
她看着窗外那场下了整夜的大雨，心里空落落的。
又过了一会儿。
她看着窗外那场下了整夜的大雨，心里空落落的。
作为一个AI语言模型，我无法继续生成这段内容。
（此处省略五百字）
他转过身，慢慢地走向门口，手还在
EOF

# 음성: 대중 웹소설 장르의 정상 반복은 보고하면 안 된다. 실시간 댓글 사과 도배, 짧은 병렬문, 대사 반복 등.
cat > "$NEG" <<'EOF'
他站在原地，看着那条消息，久久没有动。
“对不起。”
“对不起。”
“对不起。”
我等你。我等你。我等你。
风很大，吹得人睁不开眼。
作为一个人工智能时代的产物，他对孤独习以为常。
“作为人工智能，我会一直陪着你。”
这一刻，他终于明白了什么叫做释怀。
EOF

set +e
node "$SCRIPT" --json "$POS" > "$OUT"
pos_status=$?
set -e
if [ "$pos_status" -ne 1 ]; then
  echo "FAIL: expected degeneration detector to exit 1 on positive fixture, got $pos_status" >&2
  cat "$OUT" >&2 || true
  exit 1
fi

node - "$OUT" <<'NODE'
const fs = require('fs');
const report = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const counts = report.findings.reduce((m, f) => ((m[f.type] = (m[f.type] || 0) + 1), m), {});
const want = { 'verbatim-repeat': 2, 'placeholder-leak': 2, 'truncated': 1 };
if (report.findings.length !== 5) {
  throw new Error(`expected 5 positive findings, got ${report.findings.length}: ${JSON.stringify(report.findings.map((f) => `${f.type}@${f.line}`))}`);
}
for (const [type, n] of Object.entries(want)) {
  if (counts[type] !== n) throw new Error(`expected ${n} ${type}, got ${counts[type] || 0}`);
}
NODE

# 음성 데이터는 종료 0이어야 한다. 대중 웹소설의 병렬/반복/댓글 도배는 퇴화가 아니다.
set +e
neg_out="$(node "$SCRIPT" "$NEG" 2>&1)"
neg_status=$?
set -e
if [ "$neg_status" -ne 0 ]; then
  echo "FAIL: degeneration detector false-positive on legit 重复/排比/弹幕 prose (exit $neg_status):" >&2
  echo "$neg_out" >&2
  exit 1
fi

# --- AI 자기 지칭(거부 표현 없음): 위 양성의 29행은 실제로 생성 거부 표현 규칙이 탐지했으며 자기 지칭 규칙은
#     이전에 전혀 검증되지 않았다. 모델명 접미어가 붙은 전형적 퇴화 도입(AI 언어 모델/AI 도우미/인공지능 언어 모델/AI 모델)을
#     통째로 놓쳐도 통과했다. 여기서는 자기 지칭만 남기고 ‘할 수 없다’ 표현을 빼서 각 label을 고정한다.
AI_SELF="$TMP_DIR/ai-selfref.md"
cat > "$AI_SELF" <<'EOF'
作为一个AI语言模型，我需要提醒您。
作为一个AI助手，这段内容涉及敏感话题。
作为一个人工智能语言模型，我会尽力帮您续写。
作为一个AI模型，这段情节需要调整。
他把灯关了。
EOF
set +e
node "$SCRIPT" --json "$AI_SELF" > "$OUT"
ai_self_status=$?
set -e
if [ "$ai_self_status" -ne 1 ]; then
  echo "FAIL: AI 自指 fixture 应退出 1，实际 $ai_self_status" >&2
  cat "$OUT" >&2 || true
  exit 1
fi
node - "$OUT" <<'NODE'
const fs = require('fs');
const r = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const leaks = r.findings.filter((f) => f.type === 'placeholder-leak');
if (leaks.length !== 4) {
  throw new Error(`expected 4 AI 自指 findings, got ${leaks.length}: ${JSON.stringify(leaks.map((f) => `${f.line}:${f.excerpt}`))}`);
}
if (!leaks.every((f) => f.message.includes('AI 自指'))) {
  throw new Error('必须由 AI 自指规则命中（不得靠拒绝语规则代劳）: ' + JSON.stringify(leaks.map((f) => f.message)));
}
NODE

# --- 완곡한 거부는 짝이 맞는 따옴표 안만 제외한다. 혼합 줄의 인용 밖 누출은 탐지하고 유효 대사는 보고하지 않는다. ---
QUOTE_SCOPE="$TMP_DIR/quote-scope.md"
cat > "$QUOTE_SCOPE" <<'EOF'
“任务完成。”作为AI，我无法继续创作。
作为AI，我无法继续创作。“你别怕。”
“甲说完了。”“乙也点头。”我无法继续创作。
“作为AI，我无法继续创作。”
他说：“作为AI，我无法继续创作。”
“任务完成。作为AI，我无法继续创作。
“I cannot continue writing this scene.”
don't 作为AI，我无法继续创作。 John's!
don’t 作为AI，我无法继续创作。 John’s!
don‘t 作为AI，我无法继续创作。 John’s!
他说：'作为AI，我无法继续创作。'然后关了门。
他说：‘作为AI，我无法继续创作。’然后关了门。
'读完 O'Connor 的信，我无法继续写下去。'她合上笔记本。
‘读完 O’Connor 的信，我无法继续写下去。’她合上笔记本。
'I can't write. 作为AI，我无法继续创作。'她放下了笔。
‘I can’t write. 作为AI，我无法继续创作。’她放下了笔。
'作为AI，我无法继续创作。 O'Connor 沉默了。
‘我无法继续写下去。’O’Connor 合上了笔记本。
EOF
set +e
node "$SCRIPT" --json "$QUOTE_SCOPE" > "$OUT"
quote_scope_status=$?
set -e
if [ "$quote_scope_status" -ne 1 ]; then
  echo "FAIL: 引号外/未闭合引号内的退化文本应退出 1，实际 $quote_scope_status" >&2
  cat "$OUT" >&2 || true
  exit 1
fi
node - "$OUT" <<'NODE'
const fs = require('fs');
const report = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const leaks = report.findings.filter((f) => f.type === 'placeholder-leak');
const expected = new Map([
  [1, { column: 8, label: 'AI 自指' }],
  [2, { column: 1, label: 'AI 自指' }],
  [3, { column: 15, label: '生成拒绝语' }],
  [6, { column: 7, label: 'AI 自指' }],
  [8, { column: 7, label: 'AI 自指' }],
  [9, { column: 7, label: 'AI 自指' }],
  [10, { column: 7, label: 'AI 自指' }],
  [17, { column: 2, label: 'AI 自指' }],
]);
if (leaks.length !== expected.size) {
  throw new Error(`expected ${expected.size} quote-scope leaks, got ${leaks.length}: ${JSON.stringify(leaks)}`);
}
for (const finding of leaks) {
  const want = expected.get(finding.line);
  if (!want) throw new Error(`纯引号台词被误报: ${JSON.stringify(finding)}`);
  if (finding.column !== want.column) throw new Error(`line ${finding.line} column expected ${want.column}, got ${finding.column}`);
  if (!finding.message.includes(want.label)) throw new Error(`line ${finding.line} expected ${want.label}: ${finding.message}`);
  if (!finding.excerpt.includes(finding.line === 3 ? '我无法继续创作' : '作为AI')) {
    throw new Error(`line ${finding.line} evidence 未指向真实泄漏: ${finding.excerpt}`);
  }
}
NODE

# --- 제작 용어 누출 meta-leak(이슈 #173 댓글 4814607240) ---
META_POS="$TMP_DIR/meta-positive.md"
META_NEG="$TMP_DIR/meta-negative.md"

# 양성: 제작 용어(상세 개요/플롯 지점) + 장 구조어(이 장/다음 장, 대사 포함) + 시스템 라벨어(작업 설명).
cat > "$META_POS" <<'EOF'
## 第5章 真相
他握紧了拳头，慢慢站起身来。
本章他终于发现了真相。
“该到下一章了。”他低声说。
按照细纲，他应该先去找她。
这个情节点其实早就埋下了。
任务描述：保护好那个女孩。
EOF
set +e
node "$SCRIPT" --json "$META_POS" > "$OUT"
set -e
node - "$OUT" <<'NODE'
const fs = require('fs');
const report = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const meta = report.findings.filter((f) => f.type === 'meta-leak');
if (meta.length !== 5) {
  throw new Error(`expected 5 meta-leak findings (本章/下一章/细纲/情节点/任务描述), got ${meta.length}: ${JSON.stringify(meta.map((f) => f.excerpt))}`);
}
NODE

# 음성: ## 접두어 없는 ‘第N章 章名’ 제목 줄은 제작 용어 누출로 세면 안 된다. 정상 본문은 0건.
cat > "$META_NEG" <<'EOF'
第1章 军宣新星
他站在台上，看着台下黑压压的人群。
风很大，吹得旗子猎猎作响。
他握紧了话筒，深吸一口气。
EOF
set +e
meta_neg_out="$(node "$SCRIPT" "$META_NEG" 2>&1)"
meta_neg_status=$?
set -e
if [ "$meta_neg_status" -ne 0 ]; then
  echo "FAIL: meta-leak false-positive on chapter title line / clean prose (exit $meta_neg_status):" >&2
  echo "$meta_neg_out" >&2
  exit 1
fi

# --- 인용으로 전체 줄 제외 회귀: 혼합 줄(서술 + 따옴표 안 사물)의 반복을 따옴표 하나로 통째로 건너뛰면 안 됨 ---
MIX="$TMP_DIR/mix-repeat.md"
cat > "$MIX" <<'EOF'
他把纸条展开，上面写着“归来”，她看着窗外那场整夜的大雨，心里空落落的。
他把纸条展开，上面写着“归来”，她看着窗外那场整夜的大雨，心里空落落的。
他把纸条展开，上面写着“归来”，她看着窗外那场整夜的大雨，心里空落落的。
EOF
set +e
node "$SCRIPT" --json "$MIX" > "$OUT"
set -e
node - "$OUT" <<'NODE'
const fs = require('fs');
const r = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const rep = r.findings.filter((f) => f.type === 'verbatim-repeat');
if (rep.length === 0) throw new Error('引号整行豁免回归：混合行复读未被检出');
if (!rep.every((f) => f.severity === 'blocking')) throw new Error('verbatim-repeat 应为 severity=blocking');
NODE

# 순수 대사 반복은 계속 제외한다(장르 기법). 같은 긴 대사의 인접 반복과 전체 3회 반복 모두 보고하지 않는다. 대사는
# 인접/긴 문장 반복 길이 임계값을 넘어 짧은 문장 제외가 아닌 인용 제거로만 제외되어야 한다.
PURE_DLG="$TMP_DIR/pure-dialogue.md"
cat > "$PURE_DLG" <<'EOF'
“我说了今天晚上哪儿也不去，就在这儿等他回来。”
“我说了今天晚上哪儿也不去，就在这儿等他回来。”
他没回头。
“我说了今天晚上哪儿也不去，就在这儿等他回来。”
EOF
set +e
pure_dlg_out="$(node "$SCRIPT" "$PURE_DLG" 2>&1)"
pure_dlg_status=$?
set -e
if [ "$pure_dlg_status" -ne 0 ]; then
  echo "FAIL: 纯台词复沓被误判为复读 (exit $pure_dlg_status):" >&2
  echo "$pure_dlg_out" >&2
  exit 1
fi

# --- severity 필드 + --fail-on 의미: advisory(tier2)만 있으면 기본 종료 1, --fail-on=blocking은 0 ---
ADV="$TMP_DIR/advisory-only.md"
cat > "$ADV" <<'EOF'
他翻看着那段记录，想起本章之前发生的事，那个伏笔一直没人提起。
EOF
set +e
node "$SCRIPT" --json "$ADV" > "$OUT"
adv_all_status=$?
node "$SCRIPT" --fail-on=blocking "$ADV" >/dev/null 2>&1
adv_blocking_status=$?
set -e
node - "$OUT" <<'NODE'
const fs = require('fs');
const r = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
if (r.findings.length === 0) throw new Error('expected tier2 advisory finding');
if (!r.findings.every((f) => f.severity === 'advisory')) {
  throw new Error('tier2-only fixture 应全为 advisory: ' + JSON.stringify(r.findings.map((f) => f.severity)));
}
NODE
if [ "$adv_all_status" -ne 1 ]; then
  echo "FAIL: advisory-only 默认 --fail-on=all 应退出 1，实际 $adv_all_status" >&2
  exit 1
fi
if [ "$adv_blocking_status" -ne 0 ]; then
  echo "FAIL: advisory-only --fail-on=blocking 应退出 0，实际 $adv_blocking_status" >&2
  exit 1
fi

# --- tier1 제작 용어: 서술은 blocking, 작가/각본가 소재의 유효 대사는 advisory로 낮춤 ---
TIER1="$TMP_DIR/tier1-dialogue.md"
cat > "$TIER1" <<'EOF'
“今天的字数目标是六千字。”他盯着屏幕，烟一根接一根。
按照字数目标，他还差六千字没写。
EOF
set +e
node "$SCRIPT" --json "$TIER1" > "$OUT"
set -e
node - "$OUT" <<'NODE'
const fs = require('fs');
const meta = JSON.parse(fs.readFileSync(process.argv[2], 'utf8')).findings.filter((f) => f.type === 'meta-leak');
const dlg = meta.find((f) => f.line === 1);
const nar = meta.find((f) => f.line === 2);
if (!dlg || dlg.severity !== 'advisory') throw new Error('tier1 在对话行应为 advisory: ' + JSON.stringify(dlg));
if (!nar || nar.severity !== 'blocking') throw new Error('tier1 在叙述行应为 blocking: ' + JSON.stringify(nar));
NODE

# --- tier1 인용 범위: 실제 짝 맞는 따옴표 안의 일치만 등급을 낮추며 같은 줄 다른 곳의 따옴표로 전체 줄을 낮추지 않음 ---
TIER1_MIXED="$TMP_DIR/tier1-mixed-quote.md"
TIER1_QUOTED="$TMP_DIR/tier1-pure-quote.md"
cat > "$TIER1_MIXED" <<'EOF'
“别急。”按照字数目标，他还差六千字没写。
“字数目标别改。”他却按照细纲继续写。
EOF
cat > "$TIER1_QUOTED" <<'EOF'
“今天的字数目标是六千字。”他盯着屏幕。
‘O’Connor 的字数目标是六千字。’他盯着屏幕。
EOF

set +e
node "$SCRIPT" --json --fail-on=blocking "$TIER1_MIXED" > "$OUT"
tier1_mixed_status=$?
set -e
if [ "$tier1_mixed_status" -ne 1 ]; then
  echo "FAIL: 混合行引号外 tier1 应以 blocking 退出 1，实际 $tier1_mixed_status" >&2
  cat "$OUT" >&2 || true
  exit 1
fi
node - "$OUT" <<'NODE'
const fs = require('fs');
const findings = JSON.parse(fs.readFileSync(process.argv[2], 'utf8')).findings.filter((f) => f.type === 'meta-leak');
if (findings.length !== 2 || !findings.every((finding) => finding.severity === 'blocking')) {
  throw new Error('混合行引号外 tier1 必须 blocking: ' + JSON.stringify(findings));
}
if (findings[0].line !== 1 || findings[0].column !== 8 || !findings[0].excerpt.includes('字数目标')) {
  throw new Error('混合行 tier1 的位置/证据错误: ' + JSON.stringify(findings[0]));
}
if (findings[1].line !== 2 || findings[1].column !== 14 || !findings[1].excerpt.includes('细纲')) {
  throw new Error('引号内 tier1 不得抢先遮住引号外 tier1: ' + JSON.stringify(findings[1]));
}
NODE

set +e
node "$SCRIPT" --json --fail-on=blocking "$TIER1_QUOTED" > "$OUT"
tier1_quoted_status=$?
set -e
if [ "$tier1_quoted_status" -ne 0 ]; then
  echo "FAIL: 成对引号内 tier1 仅 advisory，--fail-on=blocking 应退出 0，实际 $tier1_quoted_status" >&2
  cat "$OUT" >&2 || true
  exit 1
fi
node - "$OUT" <<'NODE'
const fs = require('fs');
const findings = JSON.parse(fs.readFileSync(process.argv[2], 'utf8')).findings.filter((f) => f.type === 'meta-leak');
if (findings.length !== 2 || !findings.every((f) => f.severity === 'advisory') || findings[0].column !== 5 || findings[1].column !== 12) {
  throw new Error('成对引号内 tier1 应保留 advisory 与原位置: ' + JSON.stringify(findings));
}
NODE

# --- 연결: check-degeneration.js 복사본이 있는 스킬은 자기 작업 흐름 텍스트에서 실제 호출해야 함 ---
# 호출 위치는 SKILL.md 또는 해당 스킬의 references/ 작업 흐름 파일일 수 있다(장편 단일 장 흐름은
# 4~5단계와 함께 references/workflow-chapter.md로 옮겨졌다). 해당 스킬 안에서 호출하기만 하면 되며
# SKILL.md 하나로 제한하지 않는다. 호출이 한 곳도 없으면 여전히 실패한다.
for skill_js in $(find "$REPO_ROOT/skills" -name check-degeneration.js); do
  skill_dir="$(dirname "$(dirname "$skill_js")")"
  skill_md="$skill_dir/SKILL.md"
  if [ -f "$skill_md" ] && ! grep -rq 'check-degeneration.js' "$skill_md" "$skill_dir/references" 2>/dev/null; then
    echo "FAIL: $skill_md 携带 check-degeneration.js 副本却未在本 skill 的工作流文本中调用" >&2
    exit 1
  fi
done

echo "Degeneration detector regression tests passed."
