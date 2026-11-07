import type { Plugin } from "@opencode/plugin"
import * as fs from "node:fs"
import * as path from "node:path"
import { execSync } from "node:child_process"
import {
  discoverActiveBook,
  resolveTarget,
  extractProseTargets,
  extractPatchTargets,
  proseBlockReason,
  proseAfterWrite,
} from "./lib/story_hook_core.js"

// OpenCode 2.x 플러그인 API(default export `{ id, setup }`)만 지원한다. 1.x 로더는 이 구조를 읽지 못하고
// failed to load plugin을 한 줄 기록한 뒤 계속 실행해 세션 내내 보호가 조용히 무효화되므로 배포 전 버전을 검사한다.
//
// 본문 쓰기 보호 탐지(AI 문체 제거용 가벼운 결정론적 검사망, 개요/상세 개요 보호, 글자 수/저장/제목 중복,
// 본문 쓰기 대상 추출)는 ZCode 훅과 같은 story_hook_core.js를 공유하며 이 플러그인과 함께
// .opencode/plugins/lib/story_hook_core.js에 배포한다. plugins/의 모든 .ts/.js는 플러그인으로 로드되므로 lib/ 하위에 둔다.
// 하위 디렉터리도 server.* / index.* / tui.* / rpc.* 진입점이 있으면 플러그인 패키지이므로 lib/에는 이 파일명을 두지 않는다.
// 여기에는 OpenCode 호스트 관련 부분만 남긴다. 프로젝트 루트 탐색, 도구 execute.before/after와
// 세션 압축 이벤트, 발견 내용을 쓰기 도구 응답에 붙이는 출력 구조를 담당한다.
// 공유 코어는 bash 훅을 기준으로 삼으며 동등성은 test-prose-net-parity.sh가 검증한다.

type ToolInput = Record<string, unknown>
type TextPart = { type: "text"; text: string }

// 2.x 백그라운드 서비스는 한 프로세스로 여러 프로젝트를 제공해 process.cwd()가 사용자 프로젝트가 아니다. 모든 경로는
// 플러그인의 location(ctx.location.directory, 세션 작업 디렉터리)에서 시작하며 프로젝트 루트는 그 git 최상위다.
function projectRoot(directory: string): string {
  try {
    return execSync("git rev-parse --show-toplevel", {
      cwd: directory,
      encoding: "utf-8",
      stdio: ["pipe", "pipe", "pipe"],
      // Windows: 이 설정이 없으면 플러그인 로드 시 git 콘솔 창이 깜박인다.
      windowsHide: true,
    }).trim()
  } catch {
    return directory
  }
}

// 상대 경로 기준: shell 등 도구의 workdir가 있으면 세션 디렉터리 기준으로 해석하고 프로젝트 루트 밖을 금지한다. 없으면 세션 디렉터리다.
function targetBase(root: string, directory: string, input: ToolInput): string {
  const raw = input.workdir
  if (typeof raw !== "string" || !raw.trim()) return directory
  let candidate = path.resolve(directory, raw)
  let canonicalRoot = path.resolve(root)
  try {
    if (!fs.statSync(candidate).isDirectory()) return directory
    candidate = fs.realpathSync(candidate)
    canonicalRoot = fs.realpathSync(root)
  } catch {
    return directory
  }
  const relative = path.relative(canonicalRoot, candidate)
  return relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)
    ? directory
    : candidate
}

function tryGit(root: string, args: string): string {
  try {
    return execSync(`git ${args}`, {
      cwd: root,
      encoding: "utf-8",
      stdio: ["pipe", "pipe", "pipe"],
      // Windows: 이 설정이 없으면 플러그인 로드 시 git 콘솔 창이 깜박인다.
      windowsHide: true,
    }).trim()
  } catch {
    return ""
  }
}

function asInput(value: unknown): ToolInput {
  return value && typeof value === "object" ? (value as ToolInput) : {}
}

function text(input: ToolInput, key: string): string {
  const value = input[key]
  return typeof value === "string" ? value : ""
}

// 파일 변경 도구의 저장 대상. patch는 edit 도구(permission도 write/edit처럼 edit)이며
// 일부 모델은 write/edit 대신 이것만 노출하므로 빠뜨리면 보호 전체가 무효화된다. 대상 추출(*** Add/Update File: 및
// *** Move to: 목적지)은 공유 코어를 재사용해 ZCode/Codex와 같은 기준을 쓴다. Move는 반드시 목적지를 검사해야 한다.
// 그렇지 않으면 이동 패치로 상세 개요 없는 초안을 본문/에 넣을 수 있다.
function mutationTargets(tool: string, input: ToolInput): string[] {
  if (tool === "write" || tool === "edit") {
    const filePath = text(input, "path")
    return filePath ? [filePath] : []
  }
  if (tool === "patch") return extractPatchTargets(text(input, "patchText"))
  return []
}

function preCompactOutput(directory: string): string {
  const root = projectRoot(directory)
  const lines = ["=== Pre-Compact Summary ==="]
  const bookDir = discoverActiveBook(root)
  if (bookDir) {
    const ctxPath = path.join(bookDir, "추적", "문맥.md")
    if (fs.existsSync(ctxPath)) {
      const lineCount = fs.readFileSync(ctxPath, "utf-8").split("\n").length
      const relPath = path.relative(root, ctxPath)
      lines.push(`Writing context: ${relPath} (${lineCount} lines)`)
    } else {
      lines.push("Active state: not found")
    }
  } else {
    lines.push("Active state: not found")
  }

  const changed = tryGit(root, "diff --name-only")
  const staged = tryGit(root, "diff --name-only --cached")
  const changedCount = changed ? changed.split("\n").filter(Boolean).length : 0
  const stagedCount = staged ? staged.split("\n").filter(Boolean).length : 0
  lines.push(`Git: ${changedCount} unstaged, ${stagedCount} staged`)

  lines.push("=== Pre-Compact Complete ===")
  return lines.join("\n")
}

// 모델이 읽는 도구 응답 뒤에 발견 내용을 붙인다. content가 없으면 OpenCode는 output을 텍스트로 직렬화하므로
// 여기서도 같은 방식으로 채운 뒤 추가해 원래 결과를 잃지 않는다.
function appendNote(
  result: { content?: string | ReadonlyArray<unknown>; output?: unknown },
  note: string
): string | ReadonlyArray<unknown> {
  const content = result.content
  if (typeof content === "string") return `${content}\n\n${note}`
  const base: ReadonlyArray<unknown> =
    content && content.length > 0
      ? content
      : [{ type: "text", text: typeof result.output === "string" ? result.output : JSON.stringify(result.output ?? "") }]
  return [...base, { type: "text", text: note } satisfies TextPart]
}

export default {
  id: "oh-story.story-hooks",
  async setup(ctx) {
    const directory = ctx.location.directory

    // 압축 전에 현재 집필 컨텍스트 위치를 요약 요청 system에 넣어 어느 책을 이어 쓰고 상태 파일이 어디인지 요약에 포함하게 한다.
    // OpenCode에는 압축 후 훅이 없어 post-compact 정보를 주입하지 않는다.
    await ctx.session.hook("compaction", (event) => {
      const preMsg = preCompactOutput(directory)
      if (preMsg) event.system.push({ type: "text", text: preMsg })
    })

    await ctx.tool.hook("execute.before", (event) => {
      const input = asInput(event.input)
      const targets =
        event.tool === "shell" ? extractProseTargets(text(input, "command")) : mutationTargets(event.tool, input)

      // 읽기 도구(read/grep/glob/…)는 targets가 비어 바로 반환한다. projectRoot()는 동기 execSync이며
      // 플러그인은 OpenCode 서비스에 상주하므로 검사 대상이 확인된 경우에만 git 프로세스를 만든다.
      if (targets.length === 0) return

      const root = projectRoot(directory)
      const base = targetBase(root, directory, input)
      for (const target of [...new Set(targets)]) {
        const reason = proseBlockReason(root, resolveTarget(root, target, base))
        if (reason) {
          const source = event.tool === "shell" ? "Shell 명령에서 본문 쓰기 대상을 확인했습니다." : "본문 쓰기 대상을 확인했습니다."
          throw new Error(`${reason}（${source}）`)
        }
      }
    })

    // 본문 저장 보완: 쓰기 후 가벼운 결정론적 검사망(잘림/거부 표현/제작 용어/반복 + 저장/글자 수/제목 중복)을 실행하고
    // 발견 내용을 쓰기 도구 응답에 붙여 모델이 읽게 한다. 본문 외 파일이나 발견 없음은 결과를 그대로 둔다(조용히 허용).
    await ctx.tool.hook("execute.after", (event) => {
      if (event.status !== "completed") return
      const input = asInput(event.input)
      const targets = mutationTargets(event.tool, input)
      if (targets.length === 0) return
      const root = projectRoot(directory)
      const base = targetBase(root, directory, input)
      try {
        const notes: string[] = []
        for (const target of [...new Set(targets)]) {
          const note = proseAfterWrite(root, resolveTarget(root, target, base))
          if (note) notes.push(note)
        }
        if (notes.length) {
          event.result = { ...event.result, content: appendNote(event.result, notes.join("\n\n")) }
        }
      } catch {
        // 보완 검사가 절차를 막으면 안 되므로 파싱 실패는 모두 허용한다.
      }
    })
  },
} satisfies Plugin.Plugin
