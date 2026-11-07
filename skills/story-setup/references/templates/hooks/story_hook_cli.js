#!/usr/bin/env node
"use strict"

// story_hook_cli.js — Claude Code bash 훅의 Node 연결부.
// Claude 훅은 settings.json에 등록한 bash 스크립트이며 핵심 로직은 여기서 require한
// story_hook_core.js를 사용한다. OpenCode/ZCode와 동일하며 check-shared-files가
// 바이트 일치를 보장한다. 핵심에 통합된 기능은 본문 검사(prose-net), 경로 추출
// extract-target, Bash 본문 쓰기 전 관문(prose-command-guard), git commit 탐지
// is-git-commit, 연속성 continuity, 추적 체크포인트 tracking-checkpoint다.
// 아직 핵심에 통합하지 않고 호스트별로 구현하는 기능:
//   - Write/Edit/MultiEdit 개요·상세 개요 차단: Claude는 guard-outline-before-prose.sh의
//     순수 bash를 쓴다. 권장 네이티브 설치에 Node가 없어도 차단해야 하므로
//     bash 판정을 유지한다. Bash 명령은 실제 쓰기와 읽기용 언급을 구분해야 해 이 CLI로 공통 핵심을 쓰며
//     Node가 없으면 허용으로 낮춘다. 추적 체크포인트도 JSON 파싱 때문에 tracking-checkpoint로
//     실행하고 Node가 없으면 허용한다.
//     codex prose_block_reason ↔ core proseBlockReason은
//     scripts/test-prose-net-parity.sh Part E로 일치시킨다.
//   - staged Markdown 경고: Claude는 validate-story-commit.sh의 bash grep을 쓰며 codex의
//     staged_markdown_warnings ↔ core stagedMarkdownWarnings도 Part E로 검증한다.
//     일치 의미와 문구는 JS 핵심을 기준으로 한다.
// 각 호스트에는 훅 I/O 형식만 처리하는 얇은 연결부를 남긴다. Node가 stdout을 UTF-8로 써서
// 이전 내장 Python의 cp936/LC_ALL 인코딩 처리도 필요 없어진다.

const fs = require("node:fs")
const path = require("node:path")
const core = require("./story_hook_core.js")

function readStdin() {
  try {
    return fs.readFileSync(0, "utf8")
  } catch {
    return ""
  }
}

const NESTED_INPUT_KEYS = ["tool_input", "input", "parameters", "args"]

function digString(value, keys, allowEmpty = false) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    for (const key of keys) {
      const found = value[key]
      if (typeof found === "string" && (allowEmpty || found)) return found
    }
    for (const key of NESTED_INPUT_KEYS) {
      const found = digString(value[key], keys, allowEmpty)
      if (found) return found
    }
  }
  return ""
}

const digTargetPath = (value) => digString(value, ["file_path", "path", "filePath"])
const digCommand = (value) => digString(value, ["command", "cmd", "script"], true)
const digWorkingDirectory = (value) =>
  digString(value, ["cwd", "working_directory", "workingDirectory"])

const [command, ...args] = process.argv.slice(2)

if (command === "extract-target") {
  // PostToolUse 입력 JSON → 대상 경로. 입력 없음·파싱 실패·경로 없음은 0이 아닌 종료로
  // bash가 조용히 허용하게 한다(이전 Python sys.exit(1)과 동일).
  const raw = process.env.HOOK_INPUT || readStdin()
  if (!raw) process.exit(1)
  let obj
  try {
    obj = JSON.parse(raw)
  } catch {
    process.exit(1)
  }
  const target = digTargetPath(obj)
  if (!target) process.exit(1)
  process.stdout.write(target)
} else if (command === "prose-command-guard") {
  // Claude Bash PreToolUse JSON → 실제 본문 쓰기 대상 → 공통 핵심 차단 사유. 핵심이 지원하는
  // 리디렉션/tee/touch/cp/mv/install만 인식하고 grep 같은 읽기 언급은 대상을 만들지 않는다. 대상 없으면 정상
  // 허용하며 파싱·핵심 예외는 별도 종료 코드로 bash에 보내 명시적 경고 후 허용한다. 대상 없음으로 위장하면 안 된다.
  const root = args[0]
  const raw = process.env.HOOK_INPUT || readStdin()
  try {
    if (!root || !raw) process.exit(0)
    const obj = JSON.parse(raw)
    const shellCommand = digCommand(obj)
    if (!shellCommand) process.exit(0)
    let base = root
    const requestedBase = core.existingDir(digWorkingDirectory(obj))
    if (requestedBase) {
      const relative = path.relative(path.resolve(root), requestedBase)
      if (!relative.startsWith("..") && !path.isAbsolute(relative)) base = requestedBase
    }
    const seen = new Set()
    for (const target of core.extractProseTargets(shellCommand)) {
      const absolute = core.resolveTarget(root, target, base)
      if (seen.has(absolute)) continue
      seen.add(absolute)
      const reason = core.proseBlockReason(root, absolute)
      if (reason) {
        process.stdout.write(`${reason}（已从 Bash 命令识别到正文写入目标。）`)
        break
      }
    }
  } catch (error) {
    const detail = error && error.message ? error.message : String(error)
    process.stderr.write(`[story-guard] Bash 正文目标解析失败，已降级放行：${detail}`)
    process.exit(3)
  }
} else if (command === "prose-net") {
  // 문제 문장 패턴을 포함한 경량 결정적 검사. 글자 수는 storyctl 공개 명령만 측정하며 어댑터에서 복제하지 않는다.
  // 작품 .deslop-whitelist는 다른 네 호스트와 같이 core.loadStyleWhitelist가 본문 작품 디렉터리에서 찾는다.
  // 파일·허용 목록 읽기 실패는 조용히 종료해 보완 검사가 절차를 해치지 않게 한다(core.proseAfterWrite와 동일).
  const absolute = args[0]
  let text
  let whitelist
  try {
    text = fs.readFileSync(absolute, "utf8")
    whitelist = core.loadStyleWhitelist(absolute)
  } catch {
    process.exit(0)
  }
  const out = core.proseNetFindings(text, whitelist, core.toxicRescanHint(absolute))
  if (out.length) process.stdout.write(out.join("\n"))
} else if (command === "prose-toxic") {
  // 문제 문장 패턴만 독립 검사한다. 가드 사전 관문·수동 재검사용이며 prose-net에도 같은 결과가 포함된다.
  // 계약: 빈 stdout은 깨끗함, 그 외는 행당 finding이며 마지막은 0건 요구와 전체 검사 안내다.
  // 파일 읽기 실패·내부 예외는 항상 exit 0으로 조용히 허용한다. 이 CLI의 보완 검사가 본 절차를 해치지 않는 원칙이다.
  const absolute = args[0]
  try {
    const text = fs.readFileSync(absolute, "utf8")
    const out = core.toxicPhraseFindings(text, core.loadStyleWhitelist(absolute), core.toxicRescanHint(absolute))
    if (out.length) process.stdout.write(out.join("\n"))
  } catch {
    process.exit(0)
  }
} else if (command === "tracking-checkpoint") {
  // 추적 체크포인트 차단 관문. guard-outline-before-prose.sh가 이 하위 명령으로 공통 핵심
  // trackingCheckpointIssue를 사용해 codex py/opencode/zcode와 같은 판정을 한다. issue #305 전에는
  // Claude에만 이 관문이 없어 같은 프로젝트·쓰기를 주 호스트는 허용하고 다른 셋은 차단했다.
  // 사용법: tracking-checkpoint <root> <bookDir> <앞장번호|->
  //   새 장 최초 생성은 앞 장 번호로 앞 장 트랜잭션 제출 순서를 검사한다.
  //   기존 본문 이어쓰기·개고는 `-`를 넘겨 state 존재·schema·리비전 일치만 검사한다.
  // 계약: 빈 stdout은 허용, 그 외는 core.proseBlockReason과 정확히 같은 전체 차단 안내다.
  // Node가 없으면 bash가 호출하지 않아 허용하므로 내부 예외도 exit 0으로 조용히 허용한다.
  // 이 CLI의 다른 하위 명령처럼 보완 검사가 본 절차를 해치지 않게 한다.
  const [root, book, expectedRaw] = args
  try {
    // Number(expectedRaw)로 바로 정수 판정하면 빈 문자열이 0이 되어 이어쓰기를
    // 1장 최초 생성으로 오인한다. 빈값·미지정·자리표시자 `-`를 먼저 제외한다.
    const expected =
      expectedRaw && expectedRaw !== "-" && Number.isInteger(Number(expectedRaw))
        ? Number(expectedRaw)
        : null
    const issue = core.trackingCheckpointIssue(book, true, expected)
    if (issue) process.stdout.write(`⛔ 写正文被拦截：${core.safeRelative(root, book)} 的${issue}。`)
  } catch {
    process.exit(0)
  }
} else if (command === "is-git-commit") {
  // git commit 탐지. STORY_COMMIT_COMMAND를 우선하고 없으면 HOOK_INPUT의 command/cmd/script를 찾는다.
  // OpenCode/ZCode와 같은 JS 토큰화의 isGitCommitCommand를 쓴다. 따옴표 안 구분자 등의 경계는
  // 기존 Python shlex와 문서화된 안내 수준 차이가 있다. git commit이면 exit 0, 아니면 exit 1이다.
  let raw = process.env.STORY_COMMIT_COMMAND || ""
  if (!raw) {
    const hookInput = process.env.HOOK_INPUT || ""
    if (!hookInput) process.exit(1)
    let obj
    try {
      obj = JSON.parse(hookInput)
    } catch {
      obj = {}
    }
    raw = digCommand(obj)
  }
  if (!raw) process.exit(1)
  process.exit(core.isGitCommitCommand(raw) ? 0 : 1)
} else if (command === "continuity") {
  // 배치 간 연속성: 추적 노후화+장 제목 중복. 공통 continuityFindings의 문구는 이전
  // Python과 정확히 같고 다중 작품·동순위 중복 정렬은 JS 기준이라 안내 순서만 달라진다.
  const root = args[0]
  const out = core.continuityFindings(root)
  if (out.length) process.stdout.write(out.join("\n") + "\n")
} else if (command === "analysis-input-guard") {
  // chapter-extractor의 PreToolUse(Write) 인라인 가드. 배치 결과는 다음 경로만 허용한다.
  // {분석디렉터리}/_analysis_cache/输入-{RAW|REUSE}-{시작장}-{끝장}.md. 분석 디렉터리는
  // chapter_index.csv 또는 _progress.md 존재로 판단하며 프로젝트 루트 안이어야 한다. exit 2로 차단하고 사유를 하위 agent에 보낸다.
  // 입력을 못 읽으면 판정 불가로 허용한다. 제출 스크립트가 여전히 내용 전체를 검증한다.
  const raw = process.env.HOOK_INPUT || readStdin()
  let obj
  try {
    obj = JSON.parse(raw)
  } catch {
    process.exit(0)
  }
  const target = digTargetPath(obj)
  if (!target) process.exit(0)
  const root = path.resolve(process.env.CLAUDE_PROJECT_DIR || digString(obj, ["cwd"]) || process.cwd())
  const absolute = path.resolve(root, target)
  const reasons = []
  const match = /^输入-(RAW|REUSE)-(\d+)-(\d+)\.md$/.exec(path.basename(absolute))
  if (!match) reasons.push("文件名必须是 输入-{RAW|REUSE}-{起章}-{止章}.md")
  else if (Number(match[2]) < 1 || Number(match[3]) < Number(match[2])) reasons.push("批次章号范围无效")
  const cacheDir = path.dirname(absolute)
  const bookDir = path.dirname(cacheDir)
  if (path.basename(cacheDir) !== "_analysis_cache") reasons.push("只能写在拆文目录的 _analysis_cache/ 下")
  else if (!["chapter_index.csv", "_progress.md"].some((name) => fs.existsSync(path.join(bookDir, name)))) {
    reasons.push("上级目录不是拆文目录（缺 chapter_index.csv 与 _progress.md）")
  }
  const relative = path.relative(root, absolute)
  if (relative.startsWith("..") || path.isAbsolute(relative)) reasons.push("路径在项目目录之外")
  if (reasons.length) {
    process.stderr.write(
      `⛔ chapter-extractor 写入被拦截：${target}\n${reasons.join("；")}。\n` +
        "只允许写调用方给的 {拆文目录}/_analysis_cache/输入-{批次ID}.md（批次 ID 如 RAW-4-6），不写其他文件。"
    )
    process.exit(2)
  }
} else {
  process.exit(2)
}
