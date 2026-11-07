#!/usr/bin/env node
"use strict"

import assert from "node:assert/strict"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import process from "node:process"
import { spawnSync } from "node:child_process"
import { fileURLToPath } from "node:url"

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const source = path.join(repo, "skills/story-setup/references/antigravity/hooks")
const fixture = fs.mkdtempSync(path.join(os.tmpdir(), "oh story 中文 hook-"))
const hookDir = path.join(fixture, ".agents/hooks")
const artifact = path.join(fixture, ".antigravity-artifacts")
const hook = path.join(hookDir, "story_antigravity_hook.js")

function write(relative, content) {
  const file = path.join(fixture, relative)
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, content, "utf8")
  return file
}

const events = {
  "pre-tool-use": "PreToolUse",
  "post-tool-use": "PostToolUse",
  "pre-invocation": "PreInvocation",
  stop: "Stop",
}

function invoke(event, input, shell = false) {
  const registered = JSON.parse(fs.readFileSync(path.join(fixture, ".agents/hooks.json"), "utf8"))
  const entries = registered["oh-story"][events[event]]
  assert.equal(entries.length, 1, `${event}: expected one registered entry`)
  const entry = entries[0]
  if (entry.matcher && input.toolCall?.name) {
    assert.ok(new RegExp(entry.matcher).test(input.toolCall.name), `${event}: tool is not routed`)
  }
  const handlers = entry.hooks || [entry]
  assert.equal(handlers.length, 1, `${event}: expected one registered handler`)
  const { command } = handlers[0]
  // 셸을 통한 실행과 argv에 따옴표를 보존한 실행으로 등록 명령을 테스트한다.
  // 리터럴 분할은 호환성을 시험하며 IDE 파서를 모델링하지는 않는다.
  const [program, ...args] = command.trim().split(/\s+/)
  const result = spawnSync(shell ? command : program, shell ? [] : args, {
    shell,
    cwd: path.join(fixture, ".agents"),
    input: JSON.stringify({
      conversationId: "fixture-conversation",
      workspacePaths: [fixture],
      artifactDirectoryPath: artifact,
      ...input,
    }),
    encoding: "utf8",
  })
  assert.equal(result.status, 0, `${event} failed: ${result.stderr}`)
  assert.doesNotThrow(() => JSON.parse(result.stdout), `${event} emitted invalid JSON: ${result.stdout}`)
  return { raw: result.stdout, value: JSON.parse(result.stdout) }
}

try {
  fs.mkdirSync(hookDir, { recursive: true })
  fs.mkdirSync(artifact, { recursive: true })
  fs.copyFileSync(path.join(source, "story_antigravity_hook.js"), hook)
  fs.copyFileSync(path.join(source, "story_hook_core.js"), path.join(hookDir, "story_hook_core.js"))
  fs.copyFileSync(path.join(source, "hooks.json"), path.join(fixture, ".agents/hooks.json"))

  // 등록한 네 명령 모두 공백과 중국어 문자가 있는 프로젝트 경로에서
  // OS 셸과 리터럴 argv 전달 방식으로 실행되어야 한다.
  for (const shell of [false, true]) {
    assert.deepEqual(invoke("pre-tool-use", {
      toolCall: { name: "write_to_file", args: { TargetFile: "普通笔记.md" } },
    }, shell).value, { decision: "allow" })
    assert.equal(invoke("post-tool-use", {}, shell).raw, "{}")
    assert.deepEqual(invoke("pre-invocation", { invocationNum: 1 }, shell).value, {})
    assert.deepEqual(invoke("stop", { fullyIdle: true, terminationReason: "model_stop" }, shell).value,
      { decision: "stop" })
  }

  write("단편/설정.md", "# 설정\n")
  const shortProse = path.join(fixture, "단편/본문.md")
  let response = invoke("pre-tool-use", {
    toolCall: { name: "write_to_file", args: { TargetFile: shortProse } },
  }).value
  assert.equal(response.decision, "deny")
  assert.match(response.reason, /구간개요/)

  write("단편/구간개요.md", "# 小节大纲\n")
  response = invoke("pre-tool-use", {
    toolCall: { name: "write_to_file", args: { TargetFile: "단편/본문.md" } },
  }).value
  assert.deepEqual(response, { decision: "allow" })

  write("另一短篇/설정.md", "# 설정\n")
  response = invoke("pre-tool-use", {
    toolCall: {
      name: "run_command",
      args: { CommandLine: "printf draft > \"另一短篇/본문.md\"", Cwd: fixture },
    },
  }).value
  assert.equal(response.decision, "deny")
  assert.match(response.reason, /另一短篇.*구간개요/s)

  write("普通笔记.md", "hello\n")
  response = invoke("pre-tool-use", {
    toolCall: { name: "replace_file_content", args: { TargetFile: "普通笔记.md" } },
  }).value
  assert.deepEqual(response, { decision: "allow" })

  write("단편/본문.md", "# 标题\n\n本章将在下一章继续展开")
  let post = invoke("post-tool-use", {
    toolCall: { name: "write_to_file", args: { TargetFile: "단편/본문.md" } },
  })
  assert.equal(post.raw, "{}", "PostToolUse must emit exactly {}")
  const pending = path.join(artifact, "oh-story-pending.json")
  assert.ok(fs.existsSync(pending), "PostToolUse must persist pending findings")
  post = invoke("post-tool-use", {
    toolCall: { name: "run_command", args: { CommandLine: "printf draft > \"단편/본문.md\"", Cwd: fixture } },
  })
  assert.equal(post.raw, "{}", "run_command PostToolUse must also emit exactly {}")

  response = invoke("pre-invocation", { invocationNum: 1 }).value
  assert.ok(Array.isArray(response.injectSteps) && response.injectSteps.length === 1)
  assert.match(response.injectSteps[0].ephemeralMessage, /본문 보완 검사/)
  assert.match(response.injectSteps[0].ephemeralMessage, /잘림 의심|메타정보 유출|문제 문장 패턴/)

  response = invoke("stop", { fullyIdle: false, terminationReason: "model_stop" }).value
  assert.equal(response.decision, "stop", "Stop must not continue while background work is active")
  response = invoke("stop", { fullyIdle: true, terminationReason: "error" }).value
  assert.equal(response.decision, "stop", "Stop must not continue an error termination")
  response = invoke("stop", { fullyIdle: true, terminationReason: "model_stop" }).value
  assert.equal(response.decision, "continue")
  response = invoke("stop", { fullyIdle: true, terminationReason: "model_stop" }).value
  assert.equal(response.decision, "stop", "Stop may force at most one continuation")

  const clean = "雨落在旧瓦上，檐角的水沿着石阶往下淌，院门外传来车轮碾过碎石的轻响。".repeat(4)
  write("단편/본문.md", `# 标题\n\n${clean}\n`)
  post = invoke("post-tool-use", {
    toolCall: { name: "multi_replace_file_content", args: { TargetFile: "단편/본문.md" } },
  })
  assert.equal(post.raw, "{}")
  assert.ok(!fs.existsSync(pending), "clean rewrite must clear pending findings")
  assert.deepEqual(invoke("pre-invocation", { invocationNum: 1 }).value, {})

  write(".story-deployed", "agents_version: 26\ntarget_cli: antigravity\n")
  write(".active-book", "长书\n")
  write("长书/설정/세계관.md", "# 세계관\n")
  write("长书/추적/문맥.md", "# 上下文\n")
  response = invoke("pre-invocation", { invocationNum: 0 }).value
  assert.ok(Array.isArray(response.injectSteps))
  assert.match(response.injectSteps.map((item) => item.ephemeralMessage).join("\n"), /Active book: 长书/)

  const git = (args) => spawnSync("git", args, { cwd: fixture, encoding: "utf8" })
  assert.equal(git(["init", "-q"]).status, 0)
  write("长书/설정/인물/甲.md", "# 角色甲\n\n年龄：20\n")
  assert.equal(git(["add", "."]).status, 0)
  response = invoke("pre-tool-use", {
    toolCall: { name: "run_command", args: { CommandLine: "git commit -m fixture", Cwd: fixture } },
  }).value
  assert.equal(response.decision, "allow")
  assert.match(response.reason, /Story Commit Warnings/)

  post = invoke("post-tool-use", { error: "fixture failure" })
  assert.equal(post.raw, "{}")
  process.stdout.write("Antigravity hook contract tests passed.\n")
} finally {
  fs.rmSync(fixture, { recursive: true, force: true })
}
