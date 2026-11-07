#!/bin/bash
# check-doc-budget.sh — 자주 읽는 문서의 예산 보호(스킬/에이전트 템플릿의 조용한 팽창 방지)
#
# 배경: 스킬 텍스트는 모든 사용자가 매 세션 지불하는 토큰이다. 규칙 하나의 비용 증가는 작아도
# 누적되면 일일 작업 경로의 비용이 두 배가 된다. 매 세션 또는 매 장 컨텍스트에 들어가는 파일에 상한을 둔다.
# 초과하면 실패해 같은 양의 기존 텍스트를 삭제하거나 scripts/doc-budget.json에서 예산을 명시적으로 늘리게 한다.
#
# 측정: 모든 공백을 제거한 문자 수. 중국어와 영어 모두 세며 문장부호/줄바꿈/들여쓰기 변경은 수치에 영향을 주지 않는다.
# 드물게 읽는 경로(story-setup 배포, UPGRADING, 작품 분석 라이브러리 템플릿)는 등록하거나 제한하지 않는다.
#
# paths는 역할 하나의 호출 한 번 단위로 등록하며 의미는 다음과 같다.
#   files      무조건 읽는다. `파일#절 제목`은 해당 절만 센다(동급 이상 다음 제목까지, 코드 펜스의 #은 제외).
#   generated  스크립트 생성 작업 묶음. `--project <임시 디렉터리> <args>`로 실행하고 출력 JSON의 brief 파일에서 저장소 루트 경로를 뺀 뒤 센다(절대 경로 때문에 기기별 측정치가 달라지지 않도록).
#   branches   조건부 읽기. 기본적으로 상호 배타적이며 각 분기 = 기본 + 분기 파일을 각자 budget과 비교한다.
#   stacking   같은 호출에서 중첩되는 분기. slots의 슬롯마다 분기를 최대 하나 선택하며 여러 슬롯은 동시에 발생할 수 있다.
#              모든 조합을 열거해 최악의 경우를 stacking.budget과 비교한다(동일 파일은 한 번만, 전체 파일을 읽었으면 하위 절 중복 제외).
#   path_ceiling.limit는 호출당 엄격한 상한(v0.8.2부터 35000)이다. 예외는 path_ceiling.exempt에만 사유와 함께 기록한다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="$SCRIPT_DIR/doc-budget.json"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --root)
      [ "$#" -ge 2 ] || { echo "FAIL: --root 缺少路径"; exit 2; }
      REPO_ROOT="$2"
      shift 2
      ;;
    --manifest)
      [ "$#" -ge 2 ] || { echo "FAIL: --manifest 缺少路径"; exit 2; }
      MANIFEST="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: bash scripts/check-doc-budget.sh [--root DIR] [--manifest FILE]"
      exit 0
      ;;
    *)
      echo "FAIL: 未知参数：$1"
      exit 2
      ;;
  esac
done

if [ ! -f "$MANIFEST" ]; then
  echo "FAIL: 预算清单缺失：$MANIFEST"
  exit 1
fi

node -e '
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const [manifestPath, repoRoot] = process.argv.slice(1);
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));

const fail = [];
const note = [];
const strip = (text) => text.replace(/\s/g, "").length;

// 파일#절 추출: 제목 줄부터 다음 동급/상위 제목까지(코드 펜스 안 줄 제외).
const sectionOf = (text, anchor) => {
  const lines = text.split(/\r\n?|\n/);
  let fence = false;
  let start = -1;
  let level = 0;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^\s*(```|~~~)/.test(line)) { fence = !fence; continue; }
    if (fence) continue;
    const m = line.match(/^(#{1,6})\s+(.*)$/);
    if (!m) continue;
    if (start >= 0 && m[1].length <= level) return lines.slice(start, i).join("\n");
    if (start < 0 && m[2].trim().startsWith(anchor)) { start = i; level = m[1].length; }
  }
  return start >= 0 ? lines.slice(start).join("\n") : null;
};

// 측정값: null = 파일 없음, undefined = 절 없음. 둘 다 오류이며 조용히 0으로 처리하지 않는다.
const cache = new Map();
const weigh = (entry) => {
  if (cache.has(entry)) return cache.get(entry);
  const hash = entry.indexOf("#");
  const rel = hash >= 0 ? entry.slice(0, hash) : entry;
  const abs = path.join(repoRoot, rel);
  let value = null;
  if (fs.existsSync(abs)) {
    const text = fs.readFileSync(abs, "utf8");
    if (hash < 0) value = strip(text);
    else {
      const body = sectionOf(text, entry.slice(hash + 1));
      value = body === null ? undefined : strip(body);
    }
  }
  cache.set(entry, value);
  return value;
};

let python = null;
const findPython = () => {
  if (python) return python;
  for (const [cmd, pre] of [["python3", []], ["python", []], ["py", ["-3"]]]) {
    const probe = spawnSync(cmd, [...pre, "--version"], { encoding: "utf8" });
    if (probe.status === 0) { python = [cmd, pre]; return python; }
  }
  return null;
};
// 스크립트 생성 작업 묶음: 한 번 실행해 chars를 얻는다. 생성 실패나 알 수 없는 출력은 오류다.
const generatedWeight = (gen) => {
  const key = `gen:${gen.script} ${(gen.args || []).join(" ")}`;
  if (cache.has(key)) return cache.get(key);
  let value;
  const py = findPython();
  const script = path.join(repoRoot, gen.script);
  if (!py) value = { error: "找不到 Python 3（依次试 python3、python、py -3）" };
  else if (!fs.existsSync(script)) value = { error: `拼包脚本不存在：${gen.script}` };
  else {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "doc-budget-"));
    const run = spawnSync(py[0], [...py[1], script, "--project", tmp, ...(gen.args || [])], { encoding: "utf8" });
    const last = (run.stdout || "").trim().split("\n").pop() || "";
    let chars = null;
    try {
      const out = JSON.parse(last);
      chars = out.chars;
      // 묶음의 절대 참조 경로 길이는 기기별 저장소 위치에 따라 달라 루트 경로를 제거한 텍스트로 측정한다.
      if (Number.isInteger(chars) && out.brief && fs.existsSync(out.brief)) {
        chars = strip(fs.readFileSync(out.brief, "utf8").split(repoRoot + path.sep).join(""));
      }
    } catch (e) { chars = null; }
    fs.rmSync(tmp, { recursive: true, force: true });
    value = run.status === 0 && Number.isInteger(chars) ? chars
      : { error: `拼包脚本 ${gen.script} ${(gen.args || []).join(" ")} 没给出 chars（退出码 ${run.status}）：${(run.stderr || last).trim().slice(0, 200)}` };
  }
  cache.set(key, value);
  return value;
};

console.log("热路径文档预算");
console.log("".padEnd(78, "-"));
console.log("  用量 /   预算  余量  文件");

for (const entry of manifest.files) {
  const used = weigh(entry.path);
  if (used === null || used === undefined) {
    fail.push(`预算登记的文件不存在：${entry.path}（改名/删除后请同步 doc-budget.json）`);
    continue;
  }
  const left = entry.budget - used;
  const mark = left < 0 ? "OVER" : "ok";
  console.log(`  ${String(used).padStart(6)} / ${String(entry.budget).padStart(6)} ${String(left).padStart(6)}  ${entry.path}  [${mark}]`);
  if (left < 0) {
    fail.push(`${entry.path} 超预算 ${-left} 字（${used} > ${entry.budget}）：${entry.why}`);
  } else if (left >= Math.ceil(entry.budget * 0.05)) {
    note.push(`${entry.path} 比预算低 ${left} 字，可把 budget 降到 ${Math.ceil(used / 100) * 100} 锁住这次精简`);
  }
}

console.log("");
console.log("已登记路径合计（不含项目资料与未登记条件项）");
console.log("".padEnd(78, "-"));
// 경로 상한: 역할별 호출(각 조건 분기와 중첩 조합 포함)의 로드량은 path_ceiling.limit를 넘으면 안 된다.
// 예외는 path_ceiling.exempt에 사유와 함께만 기록하며 예산 자체도 상한 위로 올릴 수 없다.
const ceiling = manifest.path_ceiling || null;
if (ceiling && !(Number.isFinite(ceiling.limit) && ceiling.limit > 0)) {
  fail.push(`path_ceiling.limit 缺失或不是正数（现为 ${JSON.stringify(ceiling.limit)}）——拼错会让硬上限静默失效`);
}
const ceilingOn = ceiling && Number.isFinite(ceiling.limit) && ceiling.limit > 0;
const exemptGroups = new Set((ceiling && ceiling.exempt) || []);

// 한 호출에서 읽는 내용은 동일 파일을 한 번만 세며 전체를 읽었으면 하위 절을 별도로 세지 않는다.
const total = (entries, generated, label) => {
  const set = [...new Set(entries)];
  const whole = new Set(set.filter((e) => !e.includes("#")));
  let sum = 0;
  let broken = false;
  for (const entry of set) {
    const hash = entry.indexOf("#");
    if (hash >= 0 && whole.has(entry.slice(0, hash))) continue;
    const used = weigh(entry);
    if (used === null) { fail.push(`路径「${label}」登记的文件不存在：${entry.split("#")[0]}`); broken = true; continue; }
    if (used === undefined) { fail.push(`路径「${label}」登记的小节找不到：${entry}`); broken = true; continue; }
    sum += used;
  }
  for (const gen of generated) {
    const used = generatedWeight(gen);
    if (typeof used !== "number") { fail.push(`路径「${label}」：${used.error}`); broken = true; continue; }
    sum += used;
  }
  return broken ? null : sum;
};
const checkPath = (label, budget, entries, generated, group) => {
  const sum = total(entries, generated, label);
  if (sum === null) return;
  const left = budget - sum;
  const exempt = ceilingOn && exemptGroups.has(group);
  console.log(`  ${String(sum).padStart(6)} / ${String(budget).padStart(6)} ${String(left).padStart(6)}  ${label}  [${left < 0 ? "OVER" : "ok"}${exempt ? "，上限豁免" : ""}]`);
  if (left < 0) {
    fail.push(`路径「${label}」超预算 ${-left} 字（${sum} > ${budget}）`);
  }
  if (ceilingOn && !exempt && (sum > ceiling.limit || budget > ceiling.limit)) {
    fail.push(`路径「${label}」超过硬上限 ${ceiling.limit} 字（实际 ${sum}，预算 ${budget}）：${ceiling.why}`);
  }
};
// 에이전트 프런트매터 `skills: [...]`는 매 호출마다 SKILL.md 전체를 미리 로드한다.
// 이전에는 예산에 포함되지 않아 집필자가 매번 story-deslop 전체 비용을 추가 지불했다. 등록된 에이전트 경로는 자동 포함하며
// 사전 로드 템플릿은 최소 하나의 agent 경로가 있어야 비용이 다시 숨지 않는다.
const AGENT_DIR = "skills/story-setup/references/templates/agents";
const preloads = (rel) => {
  const abs = path.join(repoRoot, rel);
  if (!fs.existsSync(abs)) return null;
  const head = fs.readFileSync(abs, "utf8").split(/^---\s*$/m)[1] || "";
  const inline = head.match(/^skills:[ \t]*\[([^\]]*)\]/m);
  if (inline) return inline[1].split(",").map((s) => s.trim()).filter(Boolean);
  const block = head.match(/^skills:[ \t]*\r?\n((?:[ \t]+-[^\n]*\n?)+)/m);
  if (block) return block[1].split("\n").map((s) => s.replace(/^[ \t]+-[ \t]*/, "").trim()).filter(Boolean);
  // 해석 불가능한 skills 표기를 사전 로드 없음으로 간주해 통과시키면 안 된다.
  if (/^skills:/m.test(head)) fail.push(`${rel} 的 skills 预加载写法认不出，改成 skills: [a, b] 或逐行 - a`);
  return [];
};
const MAX_COMBOS = 4096;
const agentPaths = new Set();
for (const group of manifest.paths || []) {
  let files = group.files || [];
  const generated = group.generated || [];
  if (group.agent) {
    agentPaths.add(group.agent);
    const skills = preloads(group.agent);
    if (skills === null) { fail.push(`路径「${group.label}」登记的 agent 不存在：${group.agent}`); continue; }
    files = [group.agent, ...files, ...skills.map((name) => `skills/${name}/SKILL.md`)];
  }
  if (group.branches) {
    for (const branch of group.branches) {
      checkPath(`${group.label}（${branch.label}）`, branch.budget, [...files, ...branch.files], generated, group.label);
    }
  } else {
    checkPath(group.label, group.budget, files, generated, group.label);
  }
  if (!group.stacking) continue;
  // 중첩: 슬롯별 분기를 최대 하나 선택하고 슬롯 간 동시 발생을 허용한다. 모든 조합 중 최악을 택한다.
  const byLabel = new Map((group.branches || []).map((b) => [b.label, b]));
  const slots = group.stacking.slots || [];
  const seen = new Set();
  let bad = false;
  for (const slot of slots) {
    for (const name of slot) {
      if (!byLabel.has(name)) { fail.push(`路径「${group.label}」stacking 列了不存在的分支：${name}`); bad = true; }
      if (seen.has(name)) { fail.push(`路径「${group.label}」stacking 里分支「${name}」出现在两个槽里（一个槽内互斥，同一分支只能属于一个槽）`); bad = true; }
      seen.add(name);
    }
  }
  if (!Number.isFinite(group.stacking.budget)) { fail.push(`路径「${group.label}」stacking 缺 budget`); bad = true; }
  const combos = slots.reduce((n, slot) => n * (slot.length + 1), 1);
  if (combos > MAX_COMBOS) { fail.push(`路径「${group.label}」stacking 组合数 ${combos} 超过 ${MAX_COMBOS}，拆小槽位`); bad = true; }
  if (bad || slots.length === 0) continue;
  let worst = null;
  const walk = (i, chosen) => {
    if (i === slots.length) {
      const sum = total([...files, ...chosen.flatMap((name) => byLabel.get(name).files)], generated, group.label);
      if (sum !== null && (worst === null || sum > worst.sum || (sum === worst.sum && chosen.length > worst.chosen.length))) worst = { sum, chosen: [...chosen] };
      return;
    }
    walk(i + 1, chosen);
    for (const name of slots[i]) walk(i + 1, [...chosen, name]);
  };
  walk(0, []);
  if (worst === null) continue;
  const label = `${group.label}（最坏叠加：${worst.chosen.join("＋") || "无"}）`;
  const left = group.stacking.budget - worst.sum;
  const exempt = ceilingOn && exemptGroups.has(group.label);
  console.log(`  ${String(worst.sum).padStart(6)} / ${String(group.stacking.budget).padStart(6)} ${String(left).padStart(6)}  ${label}  [${left < 0 ? "OVER" : "ok"}${exempt ? "，上限豁免" : ""}]`);
  if (left < 0) fail.push(`路径「${label}」超预算 ${-left} 字（${worst.sum} > ${group.stacking.budget}）`);
  if (ceilingOn && !exempt && (worst.sum > ceiling.limit || group.stacking.budget > ceiling.limit)) {
    fail.push(`路径「${label}」超过硬上限 ${ceiling.limit} 字（实际 ${worst.sum}，预算 ${group.stacking.budget}）：${ceiling.why}`);
  }
}
const agentDir = path.join(repoRoot, AGENT_DIR);
if (ceiling) {
  const labels = new Set((manifest.paths || []).map((g) => g.label));
  for (const name of exemptGroups) {
    if (!labels.has(name)) fail.push(`path_ceiling.exempt 列了不存在的路径：${name}`);
  }
}
if (fs.existsSync(agentDir)) {
  for (const name of fs.readdirSync(agentDir).filter((n) => n.endsWith(".md")).sort()) {
    const rel = `${AGENT_DIR}/${name}`;
    const skills = preloads(rel) || [];
    if (skills.length && !agentPaths.has(rel)) {
      fail.push(`${rel} 预加载了 ${skills.join("、")}，但没有登记 agent 路径——预加载内容进该 agent 每次调用，须计入预算`);
    }
  }
}

if (note.length) {
  console.log("");
  console.log("提示（不阻断）：");
  for (const n of note) console.log(`  - ${n}`);
}

if (fail.length) {
  console.log("");
  console.log("FAIL: 热路径文档超预算");
  for (const f of fail) console.log(`  - ${f}`);
  console.log("");
  console.log("处理顺序：① 先找同一文件里能删的旧文本（重复指令、已被脚本确定性拦住的规则、");
  console.log("设计理由旁白、只在极少数场景才用得上的分支），删等量再提交；");
  console.log("② 路径超了先看是不是本不该同时发生的读取挤在一次调用里：少见时刻的规则搬进按时刻读的 reference，");
  console.log("或调整流程让它们不再同时发生；会叠加的条件读取登记进 stacking，别当成互斥分支；");
  console.log("③ 确实是必须加的新规则，就在 scripts/doc-budget.json 调高 budget，并在 PR 里写清为什么这段值得每个用户每次会话都付。");
  if (ceilingOn) {
    console.log(`每次调用的硬上限是 ${ceiling.limit} 字（path_ceiling.limit），预算不能调过它；`);
    console.log("确需超限的路径只能列进 path_ceiling.exempt，并在 why 里写明原因。");
  }
  process.exit(1);
}

console.log("");
console.log("Result: 热路径文档预算检查通过");
' "$MANIFEST" "$REPO_ROOT"
