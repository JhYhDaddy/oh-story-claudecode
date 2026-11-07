"use strict"

const fs = require("node:fs")
const path = require("node:path")
const { spawnSync } = require("node:child_process")

function existingDir(value) {
  if (typeof value !== "string" || !value.trim()) return null
  try {
    const resolved = fs.realpathSync(path.resolve(value))
    return fs.statSync(resolved).isDirectory() ? resolved : null
  } catch {
    return null
  }
}

function safeRelative(root, target) {
  try {
    const rel = path.relative(path.resolve(root), path.resolve(target))
    return rel && !rel.startsWith("..") ? rel.split(path.sep).join("/") : String(target)
  } catch {
    return String(target)
  }
}

function resolveTarget(root, target, base = root) {
  const normalized = String(target || "").replace(/\\/g, "/")
  return path.isAbsolute(normalized) ? path.resolve(normalized) : path.resolve(base || root, normalized)
}

function firstLine(file) {
  try {
    return fs.readFileSync(file, "utf8").split(/\r?\n/, 1)[0].trim()
  } catch {
    return ""
  }
}

function findFirst(base, maxDepth, predicate) {
  // maxDepth는 `find -maxdepth N`과 같다. root 직속 깊이는 1, 깊이 N은 보이고 N+1은 보이지 않는다.
  if (maxDepth <= 0) return null
  let entries = []
  try {
    entries = fs.readdirSync(base, { withFileTypes: true })
  } catch {
    return null
  }
  for (const entry of entries) {
    if (entry.name.startsWith(".") || entry.name === "node_modules") continue
    const full = path.join(base, entry.name)
    if (predicate(full, entry)) return full
  }
  if (maxDepth === 1) return null
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name.startsWith(".") || entry.name === "node_modules") continue
    const found = findFirst(path.join(base, entry.name), maxDepth - 1, predicate)
    if (found) return found
  }
  return null
}

function discoverActiveBook(root) {
  const declared = firstLine(path.join(root, ".active-book"))
  if (declared) {
    const candidate = existingDir(resolveTarget(root, declared))
    if (candidate) {
      // root도 realpath로 비교한다. existingDir가 candidate를 실제 경로로 풀었는데 root를 그대로 쓰면
      // 프로젝트가 심볼릭 링크 아래(macOS /tmp·/var, 링크된 홈·작업 디렉터리)에 있을 때 rel이
      // 잘못 ‘..’로 시작해 유효한 .active-book이 조용히 버려진다. bash의 pwd -P, Python의
      // root.resolve()와 맞춘다.
      const rel = path.relative(existingDir(root) || path.resolve(root), candidate)
      if (!rel.startsWith("..") && !path.isAbsolute(rel)) return candidate
    }
  }
  const tracking = findFirst(root, 4, (_full, entry) => entry.isDirectory() && entry.name === "추적")
  if (tracking) return path.dirname(tracking)
  const body = findFirst(root, 4, (_full, entry) => entry.isDirectory() && entry.name === "본문")
  if (body) return path.dirname(body)
  const bodyFile = findFirst(root, 4, (_full, entry) => entry.isFile() && entry.name === "본문.md")
  return bodyFile ? path.dirname(bodyFile) : null
}

function discoverAllBooks(root) {
  const books = new Map()
  function walk(base, depth) {
    if (depth <= 0) return
    let entries = []
    try { entries = fs.readdirSync(base, { withFileTypes: true }) } catch { return }
    for (const entry of entries) {
      if (entry.name.startsWith(".") || entry.name === "node_modules") continue
      const full = path.join(base, entry.name)
      if (entry.isDirectory() && (entry.name === "추적" || entry.name === "본문")) {
        books.set(path.dirname(full), path.dirname(full))
      } else if (entry.isFile() && entry.name === "본문.md") {
        books.set(path.dirname(full), path.dirname(full))
      }
    }
    if (depth === 1) return
    for (const entry of entries) {
      if (!entry.isDirectory() || entry.name.startsWith(".") || entry.name === "node_modules") continue
      walk(path.join(base, entry.name), depth - 1)
    }
  }
  walk(root, 4)
  return [...books.values()]
}

function trackingCheckpointIssue(book, requireState = false, expectedLastCommitted = null) {
  const state = path.join(book, "추적", "_tracking-state.json")
  if (!fs.existsSync(state)) {
    return requireState
      ? `추적/_tracking-state.json이 없습니다. 본문이 있는 작품은 /story-import의 기존 추적 프로젝트 이전 절차로 추적을 재구성하세요(전체 작품 재분석 불필요). 새 작품은 tracking_commit.py init으로 초기화하세요`
      : null
  }
  let document
  try {
    document = JSON.parse(fs.readFileSync(state, "utf8"))
  } catch {
    return `추적/_tracking-state.json을 해석할 수 없습니다. 본문 쓰기를 멈추고 /story-import를 다시 실행하세요. 상태를 추측하거나 직접 채우지 마세요`
  }
  if (!document || typeof document !== "object" || Array.isArray(document) || document.schema_version !== 4) {
    return `추적/_tracking-state.json이 현재 schema_version=4 형식이 아닙니다. 본문 쓰기를 멈추고 /story-import를 다시 실행하세요. 이전 구조 호환 경로는 제공하지 않습니다`
  }
  if (!Number.isInteger(document.state_revision)) {
    return `추적/_tracking-state.json에 정수 state_revision이 없습니다. 본문 쓰기를 멈추고 /story-import를 다시 실행하세요`
  }
  const context = path.join(book, "추적", "문맥.md")
  let contextRevision = null
  try {
    const match = fs.readFileSync(context, "utf8").match(/状态修订：(\d+)/)
    if (match) contextRevision = Number(match[1])
  } catch {}
  if (contextRevision !== document.state_revision) {
    const shown = contextRevision === null ? "없음" : contextRevision
    return `추적/문맥.md의 상태 리비전 ${shown}과(와) _tracking-state.json의 ${document.state_revision}이(가) 다릅니다. 해당 장의 mode=revision 트랜잭션을 다시 제출해 파생 문서를 재구성하세요(expected_state_revision은 추적/_tracking-state.json의 state_revision 값 사용. check 실패 시 JSON은 출력하지 않음)`
  }
  if (expectedLastCommitted !== null) {
    if (!Number.isInteger(document.last_committed_chapter)) {
      return `추적/_tracking-state.json에 정수 last_committed_chapter가 없습니다. 본문 쓰기를 멈추고 /story-import를 다시 실행하세요`
    }
    // 장 번호가 이미 추적 범위에 있으면 개고·이름 변경·원고 백업이지 새 장 최초 생성이 아니다. 파일명만 새로워도 제출한 장이므로
    // 순서 검증은 항상 실패해 workflow-revision 원고 백업 단계가 막히므로 건너뛴다.
    if (expectedLastCommitted < document.last_committed_chapter) return null
    if (document.last_committed_chapter !== expectedLastCommitted) {
      return `추적 제출 완료: 제${document.last_committed_chapter}장. 새로 작성할 제${expectedLastCommitted + 1}장에 앞서 먼저 제출할 추적 트랜잭션: 제${expectedLastCommitted}장`
    }
  }
  return null
}

function continuityFindings(root) {
  const messages = []
  for (const book of discoverAllBooks(root)) {
    const bodyDir = path.join(book, "본문")
    let chapters = []
    try {
      chapters = fs.readdirSync(bodyDir)
        .filter((file) => /^제.*장.*\.md$/.test(file))
        .map((file) => path.join(bodyDir, file))
    } catch {}

    const context = path.join(book, "추적", "문맥.md")
    const checkpointIssue = trackingCheckpointIssue(book, chapters.length > 0)
    if (checkpointIssue) {
      messages.push(`[continuity] ${safeRelative(root, book)}：${checkpointIssue}。`)
    }
    if (chapters.length && fs.existsSync(context)) {
      try {
        const newest = Math.max(...chapters.map((file) => fs.statSync(file).mtimeMs))
        const contextTime = fs.statSync(context).mtimeMs
        if (newest > contextTime + 1000) {
          const latest = chapters.reduce((left, right) => fs.statSync(left).mtimeMs > fs.statSync(right).mtimeMs ? left : right)
          messages.push(`[continuity] ${safeRelative(root, book)}：본문은 다음 파일까지 갱신됨: 「${path.basename(latest)}」. 이어 쓰기 상태 카드가 더 오래되었습니다. 해당 장의 tracking_commit.py 트랜잭션을 제출하고 check 통과 후 이어 쓰세요. 문맥.md/복선.md를 따로 직접 수정하지 마세요.`)
        }
      } catch {}
    }

    // 이어쓰기 상태 카드 예산: 문맥.md는 트랜잭션 도구가 전체 재구축하며 절대 상한은 12288바이트다.
    if (fs.existsSync(context)) {
      try {
        const contextSize = fs.statSync(context).size
        if (contextSize > 12288) {
          messages.push(`[continuity] ${safeRelative(root, book)}：추적/문맥.md가 ${contextSize}바이트로 이어 쓰기 상태 카드의 12288바이트 한도를 초과했습니다. mode=revision 트랜잭션으로 tracking_commit.py가 전체를 재구성하게 하세요. 직접 수정하거나 계속 덧붙이지 마세요.`)
        }
      } catch {}
    }

    const titles = new Map()
    for (const chapter of chapters) {
      const match = path.basename(chapter, ".md").match(/^제0*\d+장[_\- 　]+(.+)$/)
      if (!match) continue
      const title = match[1].trim()
      if (title) titles.set(title, [...(titles.get(title) || []), path.basename(chapter)])
    }
    for (const [title, files] of titles.entries()) {
      if (files.length > 1) {
        messages.push(`[continuity] ${safeRelative(root, book)}：${files.length}개 장의 제목 중복: 「${title}」（${files.join("、").slice(0, 60)}). 제목을 바꾸는 것이 좋습니다.`)
      }
    }
  }
  return messages
}

function readShellWord(value, start) {
  let word = ""
  let quote = ""
  let escaped = false
  let started = false
  let index = start
  for (; index < value.length; index++) {
    const ch = value[index]
    if (escaped) {
      word += ch
      escaped = false
      started = true
      continue
    }
    if (ch === "\\" && quote !== "'") {
      word += ch
      escaped = true
      started = true
      continue
    }
    if (quote) {
      if (ch === quote) quote = ""
      else word += ch
      started = true
      continue
    }
    if (ch === '"' || ch === "'") {
      quote = ch
      started = true
      continue
    }
    if ([" ", "\t", "\r", "\n", ";", "&", "|", "<", ">", "(", ")"].includes(ch)) break
    word += ch
    started = true
  }
  return { word: started ? word : "", next: index }
}

function readHeredocDelimiter(value, start) {
  let word = ""
  let quote = ""
  let escaped = false
  let started = false
  let index = start
  for (; index < value.length; index++) {
    const ch = value[index]
    if (escaped) {
      word += ch
      escaped = false
      started = true
      continue
    }
    if (ch === "\\" && quote !== "'") {
      const next = value[index + 1] || ""
      if (quote === '"' && !["$", "`", '"', "\\", "\n"].includes(next)) {
        word += ch
      } else {
        escaped = true
      }
      started = true
      continue
    }
    if (quote) {
      if (ch === quote) quote = ""
      else word += ch
      started = true
      continue
    }
    if (ch === '"' || ch === "'") {
      quote = ch
      started = true
      continue
    }
    if ([" ", "\t", "\r", "\n", ";", "&", "|", "<", ">", "(", ")"].includes(ch)) break
    word += ch
    started = true
  }
  return { word: started ? word : "", next: index }
}

function heredocDeclarations(line) {
  const declarations = []
  let quote = ""
  let escaped = false
  for (let index = 0; index < line.length; index++) {
    const ch = line[index]
    if (escaped) {
      escaped = false
      continue
    }
    if (ch === "\\" && quote !== "'") {
      escaped = true
      continue
    }
    if (quote) {
      if (ch === quote) quote = ""
      continue
    }
    if (ch === '"' || ch === "'") {
      quote = ch
      continue
    }
    if (ch !== "<" || line[index + 1] !== "<" || line[index - 1] === "<" || line[index + 2] === "<") continue
    let cursor = index + 2
    let stripTabs = false
    if (line[cursor] === "-") {
      stripTabs = true
      cursor++
    }
    while (line[cursor] === " " || line[cursor] === "\t") cursor++
    const parsed = readHeredocDelimiter(line, cursor)
    if (parsed.word) declarations.push({ delimiter: parsed.word, stripTabs })
    index = Math.max(index, parsed.next - 1)
  }
  return declarations
}

function maskHeredocBodies(command) {
  const pending = []
  return String(command).split("\n").map((line) => {
    if (pending.length) {
      const current = pending[0]
      const comparable = current.stripTabs ? line.replace(/^\t+/, "") : line
      if (comparable === current.delimiter) {
        pending.shift()
        return line
      }
      return " ".repeat(line.length)
    }
    pending.push(...heredocDeclarations(line))
    return line
  }).join("\n")
}

function commandWordIndex(words) {
  let index = 0
  while (index < words.length) {
    while (index < words.length && (/^[A-Za-z_][A-Za-z0-9_]*=/.test(words[index]) || words[index] === "noglob")) index++
    if (words[index] === "command") {
      index++
      while (index < words.length) {
        const option = words[index]
        if (option === "--") { index++; break }
        if (option === "-v" || option === "-V" || /^-[p]*[vV]/.test(option)) return words.length
        if (option === "-p" || /^-p+$/.test(option)) { index++; continue }
        break
      }
      continue
    }
    if (words[index] === "env") {
      index++
      while (index < words.length) {
        const option = words[index]
        if (/^[A-Za-z_][A-Za-z0-9_]*=/.test(option) || ["-i", "--ignore-environment"].includes(option)) {
          index++
          continue
        }
        if (option === "-u" || option === "--unset") {
          index += 2
          continue
        }
        if (option.startsWith("--unset=") || (/^-u.+/.test(option) && option !== "-u")) {
          index++
          continue
        }
        if (option === "--") index++
        break
      }
      continue
    }
    break
  }
  return index
}

function nestedShellCommand(args) {
  const valueOptions = new Set(["-o", "+o", "-O", "+O"])
  for (let index = 0; index < args.length; index++) {
    const option = args[index]
    if (option === "--") return ""
    if (option === "-c" || (/^-[^-]+$/.test(option) && option.slice(1).includes("c"))) {
      return args[index + 1] || ""
    }
    if (valueOptions.has(option)) {
      index++
      continue
    }
    if (!option.startsWith("-") && !option.startsWith("+")) break
  }
  return ""
}

function commandSubstitutions(command) {
  const value = String(command)
  const substitutions = []
  let quote = ""
  let escaped = false
  for (let index = 0; index < value.length; index++) {
    const ch = value[index]
    if (escaped) {
      escaped = false
      continue
    }
    if (ch === "\\" && quote !== "'") {
      escaped = true
      continue
    }
    if (quote === "'") {
      if (ch === "'") quote = ""
      continue
    }
    if (ch === '"') {
      quote = quote === '"' ? "" : '"'
      continue
    }
    if (!quote && ch === "'") {
      quote = "'"
      continue
    }
    if (ch === "$" && value[index + 1] === "(" && value[index + 2] !== "(") {
      let depth = 1
      let innerQuote = ""
      let innerEscaped = false
      let end = index + 2
      for (; end < value.length; end++) {
        const inner = value[end]
        if (innerEscaped) { innerEscaped = false; continue }
        if (inner === "\\" && innerQuote !== "'") { innerEscaped = true; continue }
        if (innerQuote) {
          if (inner === innerQuote) innerQuote = ""
          continue
        }
        if (inner === '"' || inner === "'") { innerQuote = inner; continue }
        if (inner === "(") depth++
        else if (inner === ")" && --depth === 0) break
      }
      if (depth === 0) {
        substitutions.push(value.slice(index + 2, end))
        index = end
      }
      continue
    }
    if (ch === "`") {
      let end = index + 1
      let tickEscaped = false
      for (; end < value.length; end++) {
        const inner = value[end]
        if (tickEscaped) { tickEscaped = false; continue }
        if (inner === "\\") { tickEscaped = true; continue }
        if (inner === "`") break
      }
      if (end < value.length) {
        substitutions.push(value.slice(index + 1, end))
        index = end
      }
    }
  }
  return substitutions
}

// keepAll: 명령에 cd가 있으면 상대 대상에 cd 디렉터리를 먼저 붙여 본문인지 판정한다(`cd 正文 && cat > 제3장.md`).
// 따라서 일단 모두 추출하고 호출자가 디렉터리를 붙인 뒤 필터링한다.
function redirectTargets(command, keepAll = false) {
  const value = String(command)
  const targets = []
  let quote = ""
  let escaped = false
  for (let index = 0; index < value.length; index++) {
    const ch = value[index]
    if (escaped) { escaped = false; continue }
    if (ch === "\\" && quote !== "'") { escaped = true; continue }
    if (quote) {
      if (ch === quote) quote = ""
      continue
    }
    if (ch === '"' || ch === "'") { quote = ch; continue }
    if (ch !== ">") continue
    let cursor = index + (value[index + 1] === ">" ? 2 : 1)
    if (value[cursor] === "|" || value[cursor] === "&") cursor++
    while (value[cursor] === " " || value[cursor] === "\t") cursor++
    const parsed = readShellWord(value, cursor)
    if (keepAll || parsed.word.includes("본문")) targets.push(parsed.word)
    index = Math.max(index, parsed.next - 1)
  }
  return targets
}

function writeOperands(command, args) {
  const operands = []
  const valueOptions = command === "touch"
    ? new Set(["-d", "--date", "-r", "--reference", "-t", "--time"])
    : new Set()
  let options = true
  for (let i = 0; i < args.length; i++) {
    const arg = args[i]
    if (options && arg === "--") {
      options = false
      continue
    }
    if (options && valueOptions.has(arg)) {
      i++
      continue
    }
    if (options && [...valueOptions].some((option) => option.startsWith("--") && arg.startsWith(`${option}=`))) continue
    if (options && arg.startsWith("-") && arg !== "-") continue
    operands.push(arg)
  }
  return operands
}

function commandBasename(value) {
  const parts = String(value || "").split(/[\\/]/)
  return parts[parts.length - 1]
}

// 디렉터리형 저장 대상은 항상 ‘/’로 연결한다. Windows path.join의 역슬래시는 세 호스트 parity의
// 정확 비교를 어긋나게 한다. resolveTarget도 나중에 역슬래시를 /로 바꾸므로 여기서 미리 통일한다.
function joinPosix(directory, name) {
  return `${String(directory).replace(/[\\/]+$/, "")}/${name}`
}

function copyLikeTargets(command, args) {
  const positionals = []
  let targetDirectory = ""
  let directoryOnly = false
  let options = true
  for (let i = 0; i < args.length; i++) {
    const arg = args[i]
    if (options && arg === "--") {
      options = false
      continue
    }
    if (options && (arg === "-t" || arg === "--target-directory")) {
      targetDirectory = args[++i] || ""
      continue
    }
    if (options && arg.startsWith("--target-directory=")) {
      targetDirectory = arg.slice("--target-directory=".length)
      continue
    }
    if (options && command === "install" && (arg === "-d" || arg === "--directory")) {
      directoryOnly = true
      continue
    }
    if (options && arg.startsWith("-") && arg !== "-") continue
    positionals.push(arg)
  }
  if (directoryOnly || !positionals.length) return []
  if (targetDirectory) {
    return positionals.map((source) => joinPosix(targetDirectory, commandBasename(source)))
  }
  if (positionals.length < 2) return []
  const destination = positionals[positionals.length - 1]
  const normalized = destination.replace(/\\/g, "/")
  if (normalized.endsWith("/") || normalized.split("/").pop() === "본문") {
    return positionals.slice(0, -1).map((source) => joinPosix(destination, commandBasename(source)))
  }
  return [destination]
}

function extractProseTargets(command, depth = 0) {
  const targets = []
  const scannable = maskHeredocBodies(command)
  if (depth < 8) {
    for (const nested of commandSubstitutions(scannable)) {
      targets.push(...extractProseTargets(nested, depth + 1))
    }
  }
  // `cd 书目录 && cat > 본문/...`는 cd 이후 디렉터리에 상대 대상을 붙여야 한다. 아니면 세션 디렉터리에서 개요를 찾아
  // 있는 개요를 없다고 오판한다. cd가 없으면 명령 전체의 리디렉션을 검사하는 기존 동작을 유지한다.
  // `>|`, `>&file`, `&>`는 파이프·백그라운드가 아닌 리디렉션이다. 먼저 `>`로 통일해 분할 시 대상을 잃지 않는다.
  const segments = shellSegments(scannable.replace(/&>/g, " >").replace(/>\|/g, ">").replace(/>&(?!\d)/g, ">"))
  const parsed = segments.map((raw) => {
    const words = shellWords(beforeShellRedirection(raw))
    const commandIndex = commandWordIndex(words)
    return { raw, name: commandBasename(words[commandIndex]), args: words.slice(commandIndex + 1) }
  })
  const hasCd = parsed.some((item) => item.name === "cd")
  if (!hasCd) targets.push(...redirectTargets(scannable))
  let cwd = ""
  const isAbsolute = (value) => /^([\\/~]|[A-Za-z]:[\\/])/.test(value)
  const underCwd = (value) => (cwd && !isAbsolute(value) ? joinPosix(cwd, value) : value)
  for (const { raw, name: commandName, args: commandArgs } of parsed) {
    // shellWords처럼 따옴표를 고려해 토큰화한다. /\s+/는 cp draft.md "my book/본문/제1장.md"의 대상을 잘라
    // 마지막 book/본문/제1장.md만 얻어 다른 작품을 판정하고 거기에 개요가 있으면 잘못 허용한다.
    if (commandName === "cd") {
      const directory = commandArgs.find((arg) => !arg.startsWith("-"))
      if (directory) cwd = isAbsolute(directory) || !cwd ? directory : joinPosix(cwd, directory)
      continue
    }
    if (hasCd) targets.push(...redirectTargets(raw, true).map(underCwd).filter((target) => target.includes("본문")))
    if (["sh", "bash", "dash", "ksh", "zsh"].includes(commandName)) {
      const nested = nestedShellCommand(commandArgs)
      if (nested) targets.push(...extractProseTargets(nested, depth + 1))
    }
    if (commandName === "tee" || commandName === "touch") {
      for (const destination of writeOperands(commandName, commandArgs).map(underCwd)) {
        if (destination.includes("본문")) targets.push(destination)
      }
    }
    if (commandName === "cp" || commandName === "mv" || commandName === "install") {
      for (const destination of copyLikeTargets(commandName, commandArgs).map(underCwd)) {
        if (destination.includes("본문")) targets.push(destination)
      }
    }
  }
  return [...new Set(targets.filter(Boolean))]
}

// apply_patch 대상 추출. Add/Update만 보면 Update File의 하위 지시인 `*** Move to:`를 놓친다.
// 이름 변경·이동의 저장 경로는 목적지이며 원본은 이동 후 없어진다. 이전에는
// `*** Update File: draft.md` + `*** Move to: 书/본문/제9장.md`에서 draft.md만 추출해 본문이 아니라 개요 관문을 통과했고
// 작성 후 검사도 사라진 원본을 검사하여 개요 없는 초안이 본문/으로 들어갈 수 있었다.
// 따라서 Move 목적지로 같은 구간의 원본 대상을 대체한다. 추가가 아니다. 없어진 원본 검사는 오탐·빈 검사를 만든다.
// Delete File은 양쪽 모두 목록에 넣지 않는다. 삭제는 쓰기가 아니며 proseBlockReason은 기존 본문을 원래 허용한다.
// 삭제 후 파일이 없어 검사할 대상도 없으므로 인식하면 원고 삭제를 오보한다. 다만 Delete 구간도 Move to(이동 후 원본 삭제)를 가질 수 있어
// 그 목적지는 목록에 넣어야 한다. 따라서 Delete는 대체할 원본 칸만 비운다.
function extractPatchTargets(patchText) {
  const targets = []
  let sourceIndex = -1
  for (const line of String(patchText).split(/\r?\n/)) {
    // apply_patch 제어 행은 0열에서 시작해야 하며 diff 문맥 행은 공백으로 시작한다.
    // 먼저 trim하면 본문의 ` *** Move to: notes.md`가 이동 지시로 위장해 실제 검사 대상을 덮는다.
    const file = line.match(/^\*\*\* (Add|Update|Delete) File: (.+)$/)
    if (file) {
      if (file[1] === "Delete") {
        sourceIndex = -1
        continue
      }
      targets.push(file[2].trim())
      sourceIndex = targets.length - 1
      continue
    }
    const move = line.match(/^\*\*\* Move to: (.+)$/)
    if (move) {
      const destination = move[1].trim()
      if (!destination) continue
      if (sourceIndex >= 0) targets[sourceIndex] = destination
      else targets.push(destination)
      sourceIndex = -1
    }
  }
  return targets
}

// 미확장 셸 변수: $VAR / ${VAR} / $(cmd). codex UNEXPANDED_SHELL_VAR와 같은 형식이다.
const UNEXPANDED_SHELL_VAR = /\$(\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*|\()/

// ‘去味:跳过’ 면제 표식: 파일 첫 6행의 `<!-- 去味:跳过 -->`. 전각·반각 콜론과 주석 안
// 공백·Tab을 허용하나 주석 밖 표식은 인정하지 않는다. codex py _DESLOP_SKIP_MARKER·bash guard·storyctl DESLOP_SKIP과 같은 문법이다.
const DESLOP_SKIP_MARKER = /<!--[ \t]*去味[ \t]*(：|:)[ \t]*跳过[ \t]*-->/
function hasDeslopSkipMarker(text) {
  return DESLOP_SKIP_MARKER.test(text.split(/\r?\n/).slice(0, 6).join("\n"))
}

// 사실상 빈 개요: 파일 시작 BOM과 행 시작 Markdown 제목 기호(공백·Tab 뒤 #)를 제거한 뒤
// ASCII 공백·전각 공백을 제외한 나머지가 OUTLINE_MIN_CHARS 코드 포인트 미만인 경우다. 제목 텍스트는 센다.
// `## 核心事件：…`처럼 제목에 내용을 쓴 개요도 내용이 있다. 작성 여부만 재며
// v0.8 개요 필드는 검사하지 않아 다른 형식의 기존 개요도 허용한다. 권한·디렉터리 문제로 읽지 못하거나 유효 UTF-8이 아니면
// GBK 등에서 호스트별 해석·계수가 다를 수 있으므로 비어 있지 않다고 보고 통과시킨다(누락 차단을 감수).
// codex py _outline_is_empty, guard-outline-before-prose.sh outline_is_empty와 같은 기준이다.
// test-prose-net-parity.sh C/D 절이 일치를 보장한다.
const OUTLINE_MIN_CHARS = 30
function outlineIsEmpty(file) {
  let text
  try {
    const bytes = fs.readFileSync(file)
    text = bytes.toString("utf8")
    if (!Buffer.from(text, "utf8").equals(bytes)) return false
  } catch {
    return false
  }
  if (text.startsWith("\uFEFF")) text = text.slice(1)
  const body = text.split("\n").map((line) => line.replace(/^[ \t]*#+/, "")).join("")
  return Array.from(body.replace(/[ \t\r\n\f\v\u3000]/g, "")).length < OUTLINE_MIN_CHARS
}

function proseBlockReason(root, absolute) {
  const base = path.basename(absolute)
  const parent = path.basename(path.dirname(absolute))
  if (base === "본문.md") {
    if (fs.existsSync(absolute)) return null
    const book = path.dirname(absolute)
    if (fs.existsSync(path.join(root, "작품분석실", path.basename(book)))) return null
    if (!fs.existsSync(path.join(book, "설정.md"))) return null
    if (!fs.existsSync(path.join(book, "구간개요.md"))) {
      return `⛔ 본문 쓰기 차단: ${safeRelative(root, absolute)}와 같은 폴더에 구간개요.md가 없습니다. story-short-write에 따라 구간개요.md를 완성한 뒤 본문을 쓰세요.`
    }
    return null
  }
  if (parent !== "본문" || !/^제.*장.*\.md$/.test(base)) return null
  const match = base.match(/^제0*(\d+)장/)
  if (!match) return null
  const chapter = match[1]
  const book = path.dirname(path.dirname(absolute))
  const state = path.join(book, "추적", "_tracking-state.json")
  // 가드의 기준 사례: agent는 어떤 기본 구조도 생기기 전에 {작품}/본문/제N장.md를 처음 만들 수 있다.
  // 작품처럼 보이는지를 허용 조건으로 삼으면 안 된다. 상대 경로 오판은 호스트 어댑터가 cwd 기준으로 해결해야 하며
  // 핵심 가드가 확인 실패 시 허용하도록 해서는 안 된다.
  // story-import는 기존 본문 복사 후 tracking init 전까지 쓸 수 있다. state가 생기면
  // 현재 추적 프로토콜에 들어가므로 작품분석실/ 자산을 유지한다는 이유로 가드를 영구 우회하지 않는다.
  if (fs.existsSync(path.join(root, "작품분석실", path.basename(book))) && !fs.existsSync(state)) return null
  const exists = fs.existsSync(absolute)
  const outlineDir = path.join(book, "개요")
  let found = false
  if (!exists) {
    let outlines = []
    try {
      outlines = fs.readdirSync(outlineDir).filter((file) => {
        const candidate = file.match(/^상세개요_제0*(\d+)장.*\.md$/)
        return candidate && candidate[1] === chapter
      }).sort()
    } catch {}
    found = outlines.length > 0
    // 0 채움·제목 차이로 같은 장 개요가 여러 개면 하나라도 내용이 있으면 허용한다.
    if (found && outlines.every((file) => outlineIsEmpty(path.join(outlineDir, file)))) {
      return `⛔ 본문 쓰기 차단: 제${chapter}장의 상세 개요(${safeRelative(root, path.join(outlineDir, outlines[0]))})가 비어 있습니다(# 기호와 공백을 제외하고 ${OUTLINE_MIN_CHARS}자 미만). story-long-write의 장별 절차에 따라 상세 개요를 완성하세요(이번 장의 사건과 주인공의 선택). 그 뒤 본문을 쓰세요.`
    }
    if (!found) {
      // `cat > "$PROJ/본문/제001장.md"`의 셸 변수는 가드가 확장하지 못하므로 리터럴로 작품 경로를 만들면
      // 개요를 찾을 수 없다. 계속 차단하되 개요 누락으로 오보하지 않고 경로 해석 실패라고 알린다.
      if (UNEXPANDED_SHELL_VAR.test(safeRelative(root, absolute)) && !fs.existsSync(book)) {
        return `⛔ 본문 쓰기 차단: 쓰기 경로에 치환되지 않은 셸 변수가 있습니다(${safeRelative(root, absolute)}). 보호 검사가 해당 상세 개요를 확인할 수 없습니다. 실제 프로젝트 경로(예: 작품명/본문/제${chapter.padStart(3, "0")}장_제목.md)로 다시 작성하세요.`
      }
      return `⛔ 본문 쓰기 차단: 제 ${chapter} 장에 상세 개요가 없습니다(${safeRelative(root, outlineDir)}/상세개요_제${chapter.padStart(3, "0")}장.md). story-long-write의 장별 절차로 상세 개요를 보완한 뒤 본문을 쓰세요.`
    }
  }
  const checkpointIssue = trackingCheckpointIssue(book, true, exists ? null : Number(chapter) - 1)
  if (checkpointIssue) {
    return `⛔ 본문 쓰기 차단: ${safeRelative(root, book)}: ${checkpointIssue}.`
  }
  if (exists) return null
  // 미처리 문제 관문(무상태): N장을 최초 생성하기 전에 앞 장에 미수정 문제 문장 패턴이 있고 ‘去味:跳过’가 없으면 먼저 수정한다.
  // 앞 장 파일에서 즉시 판정하며 상태 파일은 쓰지 않는다. 앞 장을 못 찾거나 읽지 못하면 오탐 대신 통과시킨다.
  // js↔py 안내는 check-hook-regex-sync.sh, 판정은 test-prose-net-parity.sh Part E가 일치를 보장한다.
  const prevNum = Number(chapter) - 1
  if (prevNum >= 1) {
    let prevFile = null
    try {
      // ext4/overlayfs의 readdir는 해시 순서라 정렬하지 않으면 같은 번호의 원고 백업을 선택해
      // 이미 수정된 과거 텍스트를 미처리로 보고할 수 있다(workflow-revision의 원고 백업 산출물).
      // _원본_ 백업을 명시적으로 빼고 정렬해 네 호스트·파일시스템 모두 같은 앞 장을 선택하게 한다.
      const candidates = fs.readdirSync(path.dirname(absolute))
        .filter((file) => {
          const pm = file.match(/^제0*(\d+)장.*\.md$/)
          return pm && Number(pm[1]) === prevNum && !file.includes("_원본_")
        })
        .sort()
      if (candidates.length) prevFile = path.join(path.dirname(absolute), candidates[0])
    } catch {}
    if (prevFile) {
      let prevText = null
      try { prevText = fs.readFileSync(prevFile, "utf8") } catch {}
      if (prevText !== null && !hasDeslopSkipMarker(prevText)) {
        const hits = toxicPhraseFindings(prevText, loadStyleWhitelist(prevFile)).filter((line) => line.startsWith("第"))
        if (hits.length) {
          const shown = hits.slice(0, 6)
          const more = hits.length - shown.length
          let reason = `⛔ 본문 쓰기 차단: 앞 장(${path.basename(prevFile)})에 ${hits.length}곳의 미수정 문제 문장이 있습니다. 모두 수정한 뒤 다음 장을 쓰세요: 제${chapter}장. 사용자가 명시적으로 면제하면 앞 장 제목 아래에 <!-- 去味:跳过 -->를 추가하고 다시 시도하세요.\n${shown.join("\n")}`
          if (more > 0) reason += `\n(추가 ${more}곳, ${toxicRescanHint(prevFile)}）`
          return reason
        }
      }
    }
  }
  return null
}

// 종결 문장부호는 깊은 검사 기준 check-degeneration.js findTruncation과 맞춘다([。！？!?…”"』」）)】]).
// 】는 장말 시스템 안내 템플릿의 끝 기호(agent-references/long-chapter-hooks.md 실전 1/4)이며 ASCII 따옴표는
// normalize-punctuation.js --quote-mode ascii의 정상 닫는 기호이므로 둘 다 절단 의심으로 보면 안 된다.
const TERMINAL = new Set(Array.from("。！？…”』」）)!?.~—】\""))
// 어댑터 호환을 위해 export를 유지한다.
const QUOTE_OPENERS = new Set(["「", "“", "‘", "『", '"'])
const SOFT_PATTERNS = [
  // 종류 접미사(AI语言模型/AI助手/人工智能语言模型/AI模型/AI大模型)는 선택적으로 소비해야 한다. 아니면 전방 탐색이
  // AI 뒤의 ‘语’/‘助’/‘模’를 보아 가장 전형적인 퇴화 도입 전체를 놓친다.
  [/作为(一个)?(AI|人工智能|大?语言模型|智能助手|聊天助手)(?:语言模型|大?模型|助手|机器人)?(?=，|,|。|、|；|;|：|:|！|!|？|\?|\s|）|\)|」|』|"|】|我|无法|不能|没法|$)/, "AI 자기 언급"],
  [/^(Sure|Certainly|Here'?s|As an AI|I (?:cannot|can't|am unable|apologize))/, "영문 AI 말투"],
  [/我(无法|不能)(继续(写|创作|生成|下去|输出)?|生成(内容|文本|正文)?|创作|续写|写作|完成(这个|本)?(章|篇|创作|请求)?)/, "생성 거부 문구"],
]
const HARD_PATTERNS = [
  [/[（(](此处|以下|这里|下文|后续)?[^）)]{0,10}(省略|略去|略过)[^）)]{0,10}[）)]/, "자리표시자(괄호 생략)"],
  [/(TODO|占位符|placeholder|待补充|此处待填|此处待补)/, "자리표시자"],
  [/(细纲|情节点|卷纲|功能标签|目标情绪|字数目标|章首钩子|章尾钩子|任务描述)/, "작업 용어 유출"],
  [/�/, "깨진 문자(대체 문자)"],
]

function skippableLine(line) {
  return !line || line.startsWith("#") || line === "---" || /^[-—=*·•\s]+$/.test(line)
}

// ── 문제 문장 패턴(결정적 AI 문장 흔적, 작성 후 본문 검사의 빈번한 경로) ──
// check-ai-patterns.js의 동명 규칙과 같은 기준으로 결정적·저오탐 패턴만 넣는다. 밀도·
// advisory는 check-ai-patterns.js의 깊은 검사에 맡기며 매번 본문 작성 때 도는 이 검사에는 넣지 않는다. 모든 정규식은
// 선형 검사·유한 반복으로 재귀 탐색 폭발이 없다. 대사·댓글·시스템 안내는 제외해 행별 짝지은 따옴표 구간을 같은 길이
// 물음표로 가린다. 이 문자가 각 문자 클래스를 끊어 따옴표를 가로지르는 가짜 적중을 막는다.
// maskQuotedSpans의 마침표 대신 물음표 사용 이유를 참조한다. 가린 뒤에도 다중 행 대사·미종결 때문에 따옴표가 남은
// 행은 통째로 건너뛴다. JS와 동형 Python 구현(codex
// story_codex_hook.py)은 scripts/check-hook-regex-sync.sh의 상수 정확 비교와
// scripts/test-prose-net-parity.sh의 fixture 정확 diff로 일치시키며 안내문은 이 핵심 모듈이 기준이다.
// 작은따옴표는 짝이 맞아야 한다. don't, O’Connor의 단어 내부 아포스트로피는 여닫는 따옴표가 아니다.
const TOXIC_QUOTE_SPANS = [/「[^」]*」/g, /『[^』]*』/g, /【[^】]*】/g, /“[^”]*”/g, /(?<![A-Za-z0-9_])‘(?:[^’]|(?<=[A-Za-z0-9_])’(?=[A-Za-z0-9_]))*(?!(?<=[A-Za-z0-9_])’[A-Za-z0-9_])’/g, /"[^"]*"/g, /(?<![A-Za-z0-9_])'(?:[^']|(?<=[A-Za-z0-9_])'(?=[A-Za-z0-9_]))*(?!(?<=[A-Za-z0-9_])'[A-Za-z0-9_])'/g]
const TOXIC_QUOTE_CHARS = new Set(Array.from("「」『』【】“”‘’\"'"))
// 절 시작 경계. 앞 문자가 여기에 속해야 ‘是A，不是B’의 첫 ‘是’를 인정하며 확인 표현의 오른쪽 경계로도 쓴다.
const TOXIC_CLAUSE_BOUNDARY = new Set(Array.from("，,。.！!？?；;：:、…—~ \t　"))
// 의문 끝(是吗/是吧/是嘛)과 확인 표현(是的/是啊/是呀/是呢+경계)의 ‘是’는 대비문의 계사가 아니다.
// 제외 로직은 check-ai-patterns.js TAG_PARTICLES / AFFIRMATION_TAG_PARTICLES에서 가져왔다.
const TOXIC_TAG_PARTICLES = new Set(["吗", "吧", "嘛"])
const TOXIC_AFFIRM_PARTICLES = new Set(["的", "啊", "呀", "呢"])
const TOXIC_TRAILER_WINDOW = 600
// em-dash를 넣지 않는 것은 의도적이다(check-ai-patterns.js에서는 blocking). 대시는 문장부호이므로 장편 chapter check
// --fix-punctuation / normalize-punctuation.js가 결정적으로 정리하고 단편도 마무리 때 먼저 정리한다. 이 검사는
// 모델이 다시 써야 하는 문장만 돌려보낸다. 매 쓰기마다 대시로 차단하면 잡음만 늘고 누락도 제출 전 chapter check가 막는다.
const TOXIC_SENTENCE_PATTERNS = [
  [/声音(?:并)?不[大高响亮][^。！？!?\n]{0,16}[却但偏]/g, "voice-contrast", "‘X하지 않지만 Y하다’식 대비를 빼고 구체적인 효과나 행동을 쓰세요."],
  [/(?:没有[^。！？!?\n，,]{1,12}[，,]){2}/g, "negation-parade", "‘없다, 없다’식 나열을 하나만 남기거나 모두 지우고 실제 장면의 세부 묘사로 바꾸세요."],
  [/是[^。！？!?\n，,]{1,12}[，,]\s*(?:而)?不是[^。！？!?\n]{1,20}/g, "reverse-not-is", "부정으로 시작하는 설명을 빼고 긍정 항목이나 구체적인 행동을 쓰세요."],
  [/不是[^。！？!?\n]{1,16}[，,]\s*(?:而)?是/g, "not-is-comparison", "부정으로 시작하는 설명을 빼고 긍정 항목이나 구체적인 행동을 쓰세요."],
]
// ‘正式拉开序幕/帷幕’는 장면 속 개막 안내이며 서술자 예고가 아니므로 lookbehind로 제외한다(check-ai-patterns.js와 동일).
const TOXIC_TRAILER_PATTERN = /没人知道|谁也不知道|谁也没想到|殊不知|(?:这)?才刚刚开(?:始|头)|正(?:朝着|向着)[^。！？!?\n]{0,24}(?:压|涌|袭|逼)(?:了?过去|了?过来|来)|(?<!正式)拉开(?:序幕|帷幕)|即将(?:开始|来临|降临)/
// 장말 상태 요약체: trailer-ending과 문말 범위를 공유하지만 미래 예고 대신 과거를 단정한다(check-ai-patterns.js와 동일).
// banned-words의 명시적 금지형만 포함한다. ‘(这|那)一刻…终于明白’는 인간 서술의 정상 인식
// 비트이며 단편 1인칭 심판 문장은 매력 요소이므로 제외한다. 문말 단정 위치만 받아 조건절·동사 보어·성어·타동사·부정 인식을 피한다.
const TOXIC_TRAILER_SUMMARY_PATTERN = /这一(?:夜|天|刻|战|年|局|役)[，,]?[^。！？!?，,\n]{0,6}(?<!命中)(?<!是)注定[^。！？!?\n]{0,8}[。！]|就这样[，,][^。！？!?，,\n]{0,8}(?:一切|全部)[^。！？!?，,\n]{0,4}(?:结束了|落幕|收场)[。！]|这一切[，,]?[^。！？!?，,\n]{0,6}(?:都)?(?:说明|意味着|结束了)(?!的)(?:(?!什么)[^。！？!?\n]){0,6}[。！]|(?:新的篇章|新的旅程|崭新的篇章|新的人生)[^。！？!?\n]{0,6}(?:开始|拉开|展开)|命运[^。！？!?\n]{0,6}齿轮/
// ‘是A，不是B’의 반문 끝 ‘…，不是吗/么/吧’는 대비문이 아니다. 적중 구간 마지막 ‘不是’ 다음 첫 글자로 판정한다.
const TOXIC_REVERSE_TAIL = /.*[，,]\s*(?:而)?不是([^。！？!?\n]*)$/

// 가림 문자는 ‘。’ 대신 ‘？’다. 각 규칙의 [^。！？!?…] 부정 클래스를 끊으면서
// 어떤 규칙의 허용 위치에도 들어가면 안 된다. 마침표는 trailer-summary 문말 [。！]의 가짜 종결자를 만들어
// ‘这一战注定是「血屠」的开端，…’처럼 별칭을 인용한 정상 서술을 오탐한다. 보고한
// ‘这一战注定是。’는 원문에서 grep할 수도 없다. 가림 길이를 유지하므로 trailer 구간 경계는 움직이지 않는다.
function maskQuotedSpans(line) {
  let out = line
  for (const spans of TOXIC_QUOTE_SPANS) out = out.replace(spans, (m) => "？".repeat(m.length))
  return out
}

// ‘是不是’ 질문이나 전환 ‘是’ 뒤의 의문·확인 표현은 ‘不是A，(而)是B’ 대비문이 아니다.
function toxicNotIsExcluded(line, matched, start) {
  if (start > 0 && line[start - 1] === "是") return true
  const end = start + matched.length
  const c1 = line[end] || ""
  const c2 = line[end + 1] || ""
  if (TOXIC_TAG_PARTICLES.has(c1)) return true
  if (TOXIC_AFFIRM_PARTICLES.has(c1) && (c2 === "" || TOXIC_CLAUSE_BOUNDARY.has(c2))) return true
  return false
}

// 절 첫머리 ‘是A，不是B’만 인식한다. 중간의 但是/还是/只是/他是…는 제외하며 양자택일
// 不是/就是/也是 및 모든 X是 접속사·부사 합성어도 절 시작 조건으로 제외한다. ‘是的，不是…’
// 확인 도입, ‘是不是…’ 의문 도입, ‘…，不是吗/么/吧’ 반문 끝도 제외한다(check-ai-patterns.js와 동일).
function toxicReverseNotIsExcluded(line, matched, start) {
  const prev = start > 0 ? line[start - 1] : ""
  if (prev !== "" && !TOXIC_CLAUSE_BOUNDARY.has(prev)) return true
  if (line.slice(start + 1, start + 3) === "不是") return true
  const c1 = line[start + 1] || ""
  const c2 = line[start + 2] || ""
  if ((TOXIC_TAG_PARTICLES.has(c1) || TOXIC_AFFIRM_PARTICLES.has(c1)) && (c2 === "" || TOXIC_CLAUSE_BOUNDARY.has(c2))) return true
  const tail = matched.match(TOXIC_REVERSE_TAIL)
  const t1 = tail && tail[1] ? tail[1][0] : ""
  if (t1 === "吗" || t1 === "么" || t1 === "吧") return true
  return false
}

// 행마다 처음 적중한 패턴만 보고한다. 한 곳 수정 후 다음 곳을 재검사해 모두 정리하는 방식이다.
function matchToxicSentence(line) {
  for (const [regex, label, fix] of TOXIC_SENTENCE_PATTERNS) {
    regex.lastIndex = 0
    let match
    while ((match = regex.exec(line)) !== null) {
      if (label === "not-is-comparison" && toxicNotIsExcluded(line, match[0], match.index)) continue
      if (label === "reverse-not-is" && toxicReverseNotIsExcluded(line, match[0], match.index)) continue
      return [label, fix, match[0]]
    }
  }
  return null
}

function codePointSlice(value, start, end) {
  return Array.from(value).slice(start, end).join("")
}

// 현재 작품에만 적용한다. 무관한 작업 공간이나 다른 작품의 선택을 상속하지 않는다.
function loadStyleWhitelist(file) {
  const parent = path.dirname(path.resolve(file));
  const book = path.basename(parent) === '본문' ? path.dirname(parent) : parent;
  try {
    return fs.readFileSync(path.join(book, '.deslop-whitelist'), 'utf8')
      .split(/\r?\n/).map(line => line.trim())
      .filter(line => line && !line.startsWith('#'))
      .sort((a, b) => b.length - a.length);
  } catch (error) {
    if (error.code === 'ENOENT') return [];
    throw error;
  }
}

function styleSpans(text, whitelist) {
  const spans = [];
  for (const literal of whitelist) {
    for (let at = text.indexOf(literal); at !== -1; at = text.indexOf(literal, at + 1)) {
      spans.push([at, at + literal.length]);
    }
  }
  return spans;
}

function maskStyleText(text, whitelist) {
  const chars = text.split('');
  for (const [start, end] of styleSpans(text, whitelist)) {
    chars.fill('？', start, end);
  }
  return chars.join('');
}


// 문제 패턴 마지막 행의 전체 재검사 안내: 장편 분장 본문({작품}/본문/제N장*.md)은 장편 절차의 유일한 검사 진입점
// storyctl chapter check를 가리킨다. 단편 본문.md나 경로가 없는 호출은 check-ai-patterns.js를 안내한다.
// codex py toxic_rescan_hint도 같은 문구이며 test-prose-net-parity.sh C절이 일치를 보장한다.
function toxicRescanHint(absolute) {
  const match = absolute ? path.basename(absolute).match(/^제0*(\d+)장.*\.md$/) : null
  if (match && path.basename(path.dirname(absolute)) === "본문") {
    return `전체 검사: {PYTHON} <story-long-write>/scripts/storyctl.py chapter check --project <작품폴더> --chapter ${match[1]}`
  }
  return "전체 스캔: node <skill>/scripts/check-ai-patterns.js --check <본문파일>"
}

// HTML 주석(예: `<!-- 去味:跳过 -->`, 작가 메모)은 본문이 아닌 메타정보다. check-ai-patterns.js scanDocument와 같이
// `<!--`, `-->` 포함 구간을 코드 포인트 기준 같은 길이 공백으로 가리며 여러 행도 허용한다. 문말까지 안 닫힌 `<!--`는 주석이 아니므로
// 그 네 문자만 지우고 뒤는 본문으로 본다. `-->` 누락으로 장 전체를 숨길 수 없다. codex py _mask_html_comment_lines도 동형이다.
function maskHtmlCommentLines(lines) {
  const unclosed = new Set()
  for (;;) {
    const out = []
    let open = false
    let openedAt = null
    lines.forEach((line, index) => {
      let text = ""
      let cursor = 0
      while (cursor < line.length) {
        if (open) {
          const close = line.indexOf("-->", cursor)
          const end = close === -1 ? line.length : close + 3
          text += " ".repeat(Array.from(line.slice(cursor, end)).length)
          cursor = end
          if (close !== -1) open = false
          continue
        }
        const start = line.indexOf("<!--", cursor)
        if (start === -1) {
          text += line.slice(cursor)
          break
        }
        text += line.slice(cursor, start) + "    "
        cursor = start + 4
        const key = `${index}:${start}`
        if (unclosed.has(key)) continue
        open = true
        openedAt = key
      }
      out.push(text)
    })
    if (!(open && openedAt !== null)) return out
    unclosed.add(openedAt)
  }
}

function toxicPhraseFindings(text, whitelist = [], rescan = toxicRescanHint("")) {
  const findings = []
  const content = []
  maskHtmlCommentLines(text.split("\n")).forEach((raw, index) => {
    const line = raw.trim()
    if (skippableLine(line)) return
    const masked = maskQuotedSpans(maskStyleText(line, whitelist))
    for (const ch of masked) {
      if (TOXIC_QUOTE_CHARS.has(ch)) return
    }
    content.push([index + 1, masked])
  })
  for (const [lineNo, masked] of content) {
    const hit = matchToxicSentence(masked)
    if (hit) findings.push(`第${lineNo}行 문제 문장 패턴[${hit[0]}]：『${codePointSlice(hit[2], 0, 20)}』——${hit[1]}`)
  }
  // trailer-ending은 문말 600자만 검사한다. 따옴표 가림 후 행별 누적하며 경계 행은 전체 포함한다.
  let acc = 0
  let cut = content.length
  while (cut > 0 && acc < TOXIC_TRAILER_WINDOW) {
    cut -= 1
    acc += Array.from(content[cut][1]).length
  }
  for (let i = cut; i < content.length; i++) {
    const [lineNo, masked] = content[i]
    const match = masked.match(TOXIC_TRAILER_PATTERN)
    if (match) findings.push(`第${lineNo}行 문제 문장 패턴[trailer-ending]：『${codePointSlice(match[0], 0, 20)}』——장 끝의 예고 문구를 지우고 현재 일어나는 행동이나 장면으로 마무리하세요.`)
    const summary = masked.match(TOXIC_TRAILER_SUMMARY_PATTERN)
    if (summary) findings.push(`第${lineNo}行 문제 문장 패턴[trailer-summary]：『${codePointSlice(summary[0], 0, 20)}』——장 끝의 상태 요약을 지우고 상세 개요의 결말을 구체적인 행동·장면·대사로 구현하세요.`)
  }
  if (findings.length) findings.push(`문제 문장 패턴은 확정적인 AI 표현 흔적입니다. 이번 장에서 모두 수정한 뒤 계속하세요. ${rescan}`)
  return findings
}

function proseNetFindings(text, whitelist = [], rescan = toxicRescanHint("")) {
  const findings = []
  const content = []
  text.split("\n").forEach((raw, index) => {
    const line = raw.trim()
    if (skippableLine(line)) return
    const lineNo = index + 1
    content.push([lineNo, line])
    let hit = false
    // 짝지은 따옴표 안만 면제하고 바깥 서술은 계속 검사한다.
    const outsideQuotes = maskQuotedSpans(line)
    for (const [regex, label] of SOFT_PATTERNS) {
      const match = outsideQuotes.match(regex)
      if (match) {
        findings.push(`第${lineNo}行 메타정보 유출(${label}）：「${codePointSlice(match[0], 0, 20)}」`)
        hit = true
        break
      }
    }
    if (hit) return
    for (const [regex, label] of HARD_PATTERNS) {
      const match = line.match(regex)
      if (match) {
        findings.push(`第${lineNo}行 ${label}：「${codePointSlice(match[0], 0, 20)}」`)
        break
      }
    }
  })
  for (let i = 1; i < content.length; i++) {
    const previous = content[i - 1][1]
    const [lineNo, current] = content[i]
    const characters = Array.from(current)
    if (previous === current && characters.length >= 8) findings.push(`第${lineNo}行 인접 반복: 앞 행과 내용이 같음 「${characters.slice(0, 20).join("")}」`)
  }
  if (content.length) {
    const [lineNo, last] = content[content.length - 1]
    if (!TERMINAL.has(Array.from(last).pop())) findings.push(`第${lineNo}行 잘림 의심: 끝부분 「…${codePointSlice(last, -12)}」이 문장 부호로 끝나지 않음`)
  }
  // ‘去味:跳过’는 미처리 관문과 같은 첫 6행 기준이다. 표식이 있으면 문제 문장 패턴 반송만 건너뛰고
  // 메타정보·자리표시·반복·절단은 계속 검사한다. 그렇지 않으면 안내에 따라 표식을 추가한 Edit가
  // 이미 면제된 패턴을 다시 강제 반송한다.
  if (!hasDeslopSkipMarker(text)) {
    findings.push(...toxicPhraseFindings(text, whitelist, rescan))
  }
  return findings
}

function isProsePath(absolute) {
  const base = path.basename(absolute)
  const parent = path.basename(path.dirname(absolute))
  if (base === "본문.md") return fs.existsSync(path.join(path.dirname(absolute), "설정.md"))
  if (parent !== "본문" || !/^제.*장.*\.md$/.test(base)) return false
  const book = path.dirname(path.dirname(absolute))
  // 개요/추적/设定은 디렉터리, 설정.md는 파일이어야 한다. bash 기준 검사
  // check-prose-after-write.sh의 `[ -d 大纲 ] || … || [ -f 설정.md ]`와 같다.
  return ["개요", "추적", "설정"].some((name) => existingDir(path.join(book, name))) || fs.existsSync(path.join(book, "설정.md"))
}

function duplicateTitleFindings(absolute) {
  const bodyDir = path.dirname(absolute)
  if (path.basename(bodyDir) !== "본문") return []
  const titles = new Map()
  try {
    for (const file of fs.readdirSync(bodyDir)) {
      const match = file.replace(/\.md$/, "").match(/^제0*\d+장[_\- 　]+(.+)$/)
      if (!match) continue
      const title = match[1].trim()
      if (title) titles.set(title, [...(titles.get(title) || []), file])
    }
  } catch {}
  const findings = []
  for (const [title, files] of titles.entries()) {
    if (files.length > 1) findings.push(`${files.length}개 장의 제목 중복: 「${title}」（${files.join("、").slice(0, 60)}). 제목을 바꾸는 것이 좋습니다.`)
  }
  return findings
}

function proseAfterWrite(root, absolute) {
  if (!fs.existsSync(absolute) || !isProsePath(absolute)) return ""
  const findings = []
  try {
    const bytes = fs.statSync(absolute).size
    if (bytes < 200) findings.push(`【파일 저장】본문이 ${bytes}바이트뿐입니다. 미완성이나 저장 실패(용량 한도·시간 초과)가 의심되므로 확인하고 보완하세요.`)
    const text = fs.readFileSync(absolute, "utf8")
    findings.push(...proseNetFindings(text, loadStyleWhitelist(absolute), toxicRescanHint(absolute)))
  } catch {
    return ""
  }
  findings.push(...duplicateTitleFindings(absolute))
  if (!findings.length) return ""
  return `=== 본문 보완 검사(${safeRelative(root, absolute)}）===\n주 세션이 마무리 검사를 놓치지 않도록 모델과 무관한 규칙으로 자동 재검사합니다. 유형별로 수정한 뒤 문제가 없을 때까지 다시 검사하세요:\n${findings.join("\n")}`
}

// 모호한 선택 정규식 대신 선형 수동 토큰화를 쓴다. 이전 /"(?:\\.|[^"])*"|'[^']*'|[^\s]+/에서 \\.와 [^"]가 모두
// 역슬래시를 소비하며 호출자가 [;&|\n]으로 나누면 따옴표 안 구분자도 잘라 미종결 따옴표를 남긴다. 그러면 역슬래시마다
// 탐색 공간이 두 배가 되어 `git commit -m "fix: 转义覆盖 \\n \\r … | see README"` 같은 130자 명령이 실측
// CPU 27초를 써 호스트 timeoutMs(zcode 15000ms)를 넘는다. 문자별 검사로 따옴표 안 문자를 그대로 취하고
// 짝 따옴표를 제거하며 미종결이면 구간 끝까지 취한다. ASCII 공백·Tab·CR·LF로 나누며 셸 구분자가 아닌 U+3000은
// 나누지 않는다. resolveTarget이 역슬래시를 Windows 경로 구분자로 쓰므로 이스케이프 해석도 하지 않는다.
function shellWords(segment) {
  const words = []
  let current = ""
  let started = false
  let quote = ""
  let escaped = false
  for (const ch of String(segment)) {
    if (escaped) {
      current += ch
      escaped = false
      started = true
      continue
    }
    if (ch === "\\" && quote !== "'") {
      current += ch
      escaped = true
      started = true
      continue
    }
    if (quote) {
      if (ch === quote) quote = ""
      else current += ch
      continue
    }
    if (ch === '"' || ch === "'") {
      quote = ch
      started = true
      continue
    }
    if (ch === " " || ch === "\t" || ch === "\r" || ch === "\n") {
      if (started) words.push(current)
      current = ""
      started = false
      continue
    }
    started = true
    current += ch
  }
  if (started) words.push(current)
  return words
}

function shellSegments(command) {
  const segments = []
  let current = ""
  let quote = ""
  let escaped = false
  for (const ch of String(command)) {
    if (escaped) {
      current += ch
      escaped = false
      continue
    }
    if (ch === "\\" && quote !== "'") {
      current += ch
      escaped = true
      continue
    }
    if (quote) {
      current += ch
      if (ch === quote) quote = ""
      continue
    }
    if (ch === '"' || ch === "'") {
      quote = ch
      current += ch
      continue
    }
    if (ch === ";" || ch === "&" || ch === "|" || ch === "\n") {
      if (current) segments.push(current)
      current = ""
      continue
    }
    current += ch
  }
  if (current) segments.push(current)
  return segments
}

function beforeShellRedirection(segment) {
  let current = ""
  let quote = ""
  let escaped = false
  for (const ch of String(segment)) {
    if (escaped) {
      current += ch
      escaped = false
      continue
    }
    if (ch === "\\" && quote !== "'") {
      current += ch
      escaped = true
      continue
    }
    if (quote) {
      current += ch
      if (ch === quote) quote = ""
      continue
    }
    if (ch === '"' || ch === "'") {
      quote = ch
      current += ch
      continue
    }
    if (ch === "<" || ch === ">") {
      return current.replace(/\d+$/, "")
    }
    current += ch
  }
  return current
}

function isGitCommitCommand(command) {
  const valueOptions = new Set(["-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix", "--config-env"])
  // 하위 셸·중괄호 그룹을 공백으로 펴 `(git commit)` / `{ git commit; }`의 git 동사를 드러내고
  // 구분자로 나눈 뒤 앞쪽 셸 래퍼·제어어를 건너뛴다.
  // then/do/else/elif를 건너뛰어 if/for/while 안 커밋도 탐지한다. Claude bash의
  // validate-story-commit.sh와 codex is_git_commit_command를 따른다.
  for (const rawSegment of String(command).replace(/\r/g, "").replace(/[(){}]/g, " ").split(/[;&|\n]+/)) {
    const words = shellWords(rawSegment)
    let i = 0
    while (i < words.length && (/^[A-Za-z_][A-Za-z0-9_]*=/.test(words[i]) || ["command", "noglob", "then", "do", "else", "elif"].includes(words[i]))) i++
    if (words[i] === "env") {
      i++
      while (i < words.length && (/^[A-Za-z_][A-Za-z0-9_]*=/.test(words[i]) || ["-i", "--ignore-environment"].includes(words[i]))) i++
    }
    if (words[i] !== "git") continue
    i++
    while (i < words.length) {
      const token = words[i]
      if (token === "commit") return true
      if (valueOptions.has(token)) { i += 2; continue }
      if ([...valueOptions].some((option) => option.startsWith("--") && token.startsWith(`${option}=`))) { i++; continue }
      if (token.startsWith("-")) { i++; continue }
      break
    }
  }
  return false
}

// 설정/ 직속 프로젝트 설정: artifact-protocols.md의 관계.md(본문 제목 ‘# 角色关系图’),
// 소재방향.md, 문체.md, 소재본문안내.md 등에는 원래 名字/姓名 필드가 없다.
const SETTING_NON_CHARACTER_FILES = new Set(["관계.md", "소재방향.md", "소재본문안내.md", "문체.md", "세계규칙.md", "세계관.md", "특전.md", "배경설정.md"])

// 인물 카드만 검사한다. 설정/ 전체를 일괄 검사하면 매 설정 커밋마다 거짓 경고가 쏟아져
// 본문 인물 속성 하드코딩의 실제 경고를 묻어 버린다. validate-story-commit.sh / opencode
// pre-commit.sh의 case와 일대일로 맞춘다(bash↔js↔py 네 호스트 동일, 한쪽만 일괄 검사로 되돌리지 않음).
// ① 설정/角色|人物 하위 파일은 인물 카드다.
// ② 다른 설정/<하위디렉터리>/는 전체 건너뛴다(세계관·세력·보고·원리·인물 관계 등).
// ③ 설정/ 직속 파일은 알려진 프로젝트 설정 외에 모두 인물 카드로 본다(주인공.md/조연.md/악역.md 등 맞춤 이름).
// bash의 `*`는 `/`를 가로지르므로 `설정/인물/*|*/설정/인물/*`는 경로 내 어느 设定 구간이든 해당 분기를
// 만족하면 된다. 따라서 전체 경로에서 ①을 찾고 다시 ②를 찾으며 첫 设定 구간만으로 결정하지 않는다.
// 그렇게 하면 설정/其他/설정/인물/x.md 같은 중첩 경로에서 bash와 결과가 갈라진다.
function isCharacterSheetPath(relative) {
  const segments = relative.split("/")
  const last = segments.length - 1
  // ① 어느 设定 뒤에 인물/人物이 바로 오고 그 아래 파일 구간이 있다.
  for (let i = 0; i + 1 < last; i++) {
    if (segments[i] === "설정" && (segments[i + 1] === "인물" || segments[i + 1] === "인물")) return true
  }
  // ② 어느 设定 뒤에 2구간 이상이 있어 인물이 아닌 하위 디렉터리에 속한다.
  for (let i = 0; i + 1 < last; i++) {
    if (segments[i] === "설정") return false
  }
  // ③ 设定 직속 파일. ②에서 깊은 경로를 제외했으므로 设定은 끝에서 두 번째 구간이다.
  return last >= 1 && segments[last - 1] === "설정" && !SETTING_NON_CHARACTER_FILES.has(segments[last])
}

function stagedMarkdownWarnings(root) {
  let output
  try {
    output = spawnSync("git", ["-C", root, "-c", "core.quotepath=false", "diff", "--cached", "--relative", "--name-only", "--diff-filter=ACM", "-z", "--", "."], {
      encoding: "buffer",
      stdio: ["ignore", "pipe", "ignore"],
      // Windows에서 이 옵션이 없으면 훅 실행마다 git 콘솔 창이 깜박인다.
      windowsHide: true,
    })
    if (output.status !== 0 || !output.stdout) return ""
  } catch {
    return ""
  }
  const warnings = []
  for (const relative of output.stdout.toString("utf8").split("\0").filter(Boolean)) {
    if (!relative.endsWith(".md")) continue
    const full = path.join(root, relative)
    let text = ""
    try { text = fs.readFileSync(full, "utf8") } catch { continue }
    if (relative === "본문.md" || relative.includes("/본문.md") || relative.startsWith("본문/") || relative.includes("/본문/")) {
      const hits = []
      text.split(/\r?\n/).forEach((line, index) => {
        if (/(身高|体重|年龄)[\s　]*(：|:)[\s　]*[0-9]+/.test(line)) hits.push(`${index + 1}:${line}`)
      })
      if (hits.length) warnings.push(`⚠ ${relative}: 본문에 인물 속성을 직접 고정했습니다. 설정 파일을 참조하세요: \n${hits.join("\n")}`)
    }
    if (isCharacterSheetPath(relative) && !/^[\s　]*(名字|姓名|名称|name)[\s　]*(：|:)/im.test(text)) {
      warnings.push(`⚠ ${relative}: 설정 파일에 필수 이름 필드(name/名字)가 없습니다.`)
    }
  }
  return warnings.length ? `=== Story Commit Warnings（advisory only）===\n${warnings.join("\n")}\n=== End Warnings ===` : ""
}

module.exports = {
  existingDir,
  safeRelative,
  resolveTarget,
  firstLine,
  findFirst,
  discoverActiveBook,
  discoverAllBooks,
  trackingCheckpointIssue,
  continuityFindings,
  extractProseTargets,
  extractPatchTargets,
  proseBlockReason,
  isProsePath,
  duplicateTitleFindings,
  proseAfterWrite,
  shellWords,
  isGitCommitCommand,
  stagedMarkdownWarnings,
  TERMINAL,
  QUOTE_OPENERS,
  SOFT_PATTERNS,
  HARD_PATTERNS,
  skippableLine,
  proseNetFindings,
  maskQuotedSpans,
  toxicPhraseFindings,
  toxicRescanHint,
  loadStyleWhitelist,
}
