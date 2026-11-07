#!/usr/bin/env node

import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import childProcess, { execFileSync } from "node:child_process";
import { createRequire, syncBuiltinESMExports } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const srcDir = path.join(repoRoot, "skills/story-setup/references/opencode");
const tmp = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "story-opencode-plugin-")));
const originalCwd = process.cwd();
const originalExecSync = childProcess.execSync;
const originalSpawnSync = childProcess.spawnSync;
const childProcessCalls = [];

// 실제 child_process 호출을 감싸는 얇은 프록시로 options를 기록한다. 플러그인과 공유 코어가 실제 구조 분해로 얻는
// execSync/spawnSync를 다루므로 소스에 windowsHide라는 글자가 있는지만 보는 것이 아니라 런타임 인자를 검증한다.
childProcess.execSync = (command, options) => {
  childProcessCalls.push({ method: "execSync", command, options });
  return originalExecSync(command, options);
};
childProcess.spawnSync = (command, args, options) => {
  childProcessCalls.push({ method: "spawnSync", command, args, options });
  return originalSpawnSync(command, args, options);
};
syncBuiltinESMExports();

// plugin.ts는 "./lib/story_hook_core.js"를 가져온다(ZCode와 공유하는 본문 검사 코어이며
// .opencode/plugins/lib/에 배포됨). 저장소 코어는 같은 디렉터리에 있고 배포 배치에만 lib/가 있으므로 임시 디렉터리에서
// 배포 배치를 재현해야 import가 코어를 찾을 수 있다.
const deployDir = path.join(tmp, "plugins");
fs.mkdirSync(path.join(deployDir, "lib"), { recursive: true });
fs.copyFileSync(path.join(srcDir, "plugin.ts"), path.join(deployDir, "plugin.ts"));
fs.copyFileSync(
  path.join(srcDir, "story_hook_core.js"),
  path.join(deployDir, "lib", "story_hook_core.js")
);
const pluginPath = path.join(deployDir, "plugin.ts");

async function expectBlocked(action, label) {
  await assert.rejects(action, /본문 쓰기 차단/, label);
}

function writeCleanState(book, lastCommitted = 0) {
  fs.mkdirSync(path.join(book, "추적"), { recursive: true });
  fs.writeFileSync(
    path.join(book, "추적", "_tracking-state.json"),
    JSON.stringify({ schema_version: 4, state_revision: 0, last_committed_chapter: lastCommitted }) + "\n",
    "utf8"
  );
  fs.writeFileSync(path.join(book, "추적", "문맥.md"), "> 状态修订：0\n", "utf8");
}

try {
  execFileSync("git", ["init", "-q", tmp]);
  process.chdir(tmp);
  const imported = await import(`${pathToFileURL(pluginPath).href}?test=${Date.now()}`);
  const plugin = imported.default;
  assert.equal(plugin.id, "oh-story.story-hooks");
  assert.equal(typeof plugin.setup, "function");

  // OpenCode 2.x 플러그인 문맥의 최소 대역: 플러그인이 사용하는 location / tool.hook / session.hook만 제공한다.
  const hooks = { tool: {}, session: {} };
  const register = (domain) => async (name, callback) => {
    hooks[domain][name] = callback;
    return { dispose: async () => {} };
  };
  // setup을 프로젝트 밖의 cwd에서 실행한다. 실제 백그라운드 서비스가 플러그인을 로드할 때도 process.cwd()는 사용자 프로젝트가 아니다.
  process.chdir(os.tmpdir());
  try {
    await plugin.setup({
      location: { directory: tmp },
      tool: { hook: register("tool") },
      session: { hook: register("session") },
    });
  } finally {
    process.chdir(tmp);
  }
  assert.equal(typeof hooks.tool["execute.before"], "function");
  assert.equal(typeof hooks.tool["execute.after"], "function");
  assert.equal(typeof hooks.session.compaction, "function");

  // async로 감싸 동기 throw도 거부된 promise로 나타나게 한다. 런타임의 Promise 래핑과 같다.
  const before = async (tool, input) => hooks.tool["execute.before"]({ tool, input });
  const after = async (tool, input, content) => {
    const event = { tool, input, status: "completed", result: { content } };
    await hooks.tool["execute.after"](event);
    return event.result.content;
  };

  fs.mkdirSync("book/본문", { recursive: true });
  fs.mkdirSync("book/개요", { recursive: true });
  fs.mkdirSync("book/추적", { recursive: true });
  fs.writeFileSync("book/추적/문맥.md", "# 上下文\n当前位置\n", "utf8");
  fs.writeFileSync(".active-book", "book\n", "utf8");

  await expectBlocked(
    () => before("write", { path: "book/본문/제001장_开局.md" }),
    "new long prose without an outline"
  );

  fs.writeFileSync("book/개요/상세개요_제1장.md", "# 细纲\n江晨在雨夜推开旧书店的门，发现柜台后坐着失踪三年的师父，两人对视良久。\n", "utf8");
  await assert.rejects(
    () => before("write", { path: "book/본문/제001장_开局.md" }),
    /_tracking-state\.json이 없습니다/,
    "long prose with outline but no tracking checkpoint must fail closed"
  );
  writeCleanState("book");
  // 상세 개요 파일은 있지만 제목뿐이면 계속 차단하며 상세 개요가 비었다고 명확히 안내한다.
  fs.writeFileSync("book/개요/상세개요_제1장.md", "# 细纲\n## 目标情绪\n", "utf8");
  await assert.rejects(
    () => before("write", { path: "book/본문/제001장_开局.md" }),
    /제1장의 상세 개요\(book\/개요\/상세개요_제1장\.md\)가 비어 있습니다/,
    "long prose with an empty outline must be blocked"
  );
  fs.writeFileSync("book/개요/상세개요_제1장.md", "# 细纲\n江晨在雨夜推开旧书店的门，发现柜台后坐着失踪三年的师父，两人对视良久。\n", "utf8");
  await before("write", { path: "book/본문/제001장_开局.md" });

  // 2.x 백그라운드 서비스의 한 프로세스가 여러 프로젝트를 담당하므로 process.cwd()는 사용자 프로젝트가 아니다. 검사기는 ctx.location만 따른다.
  // cwd를 프로젝트 밖으로 옮겨도 상세 개요가 있는 장은 허용하고 없는 장은 프로젝트 내부 경로를 기준으로 차단한다.
  process.chdir(os.tmpdir());
  try {
    await before("write", { path: "book/본문/제001장_开局.md" });
    await assert.rejects(
      () => before("write", { path: "book/본문/제005장_外部.md" }),
      /제 5 장에 상세 개요가 없습니다\(book\/개요\/상세개요_제005장\.md\)/,
      "project root must come from ctx.location, not process.cwd()"
    );
  } finally {
    process.chdir(tmp);
  }

  // 셸 변수를 확장할 수 없으면 여전히 차단하되 경로 해석 실패를 사실대로 알리고 상세 개요가 없다고 잘못 보고하지 않는다.
  await assert.rejects(
    () => before("shell", { command: 'PROJ=$PWD/book; cat draft.md > "$PROJ/본문/제001장_开局.md"' }),
    (error) => /치환되지 않은 셸 변수/.test(error.message) && !/상세 개요가 없습니다/.test(error.message),
    "shell-variable prose target must be blocked as unresolved, not as a missing outline"
  );

  fs.mkdirSync("bare/본문", { recursive: true });
  await expectBlocked(
    () => before("write", { path: "bare/본문/제1장_首章.md" }),
    "bare long project without scaffolding must fail closed"
  );

  fs.mkdirSync("cwd-book/본문", { recursive: true });
  fs.mkdirSync("cwd-book/개요", { recursive: true });
  await assert.rejects(
    () =>
      before("shell", {
        command: "cat draft.md > 본문/제8장_相对.md",
        workdir: path.join(tmp, "cwd-book"),
      }),
    /cwd-book\/개요/,
    "relative Shell target must resolve from the tool workdir"
  );
  await assert.rejects(
    () => before("shell", { command: "cat draft.md > 본문/제8장_相对.md", workdir: "cwd-book" }),
    /cwd-book\/개요/,
    "relative workdir must resolve from the session directory"
  );
  fs.writeFileSync("cwd-book/개요/상세개요_제8장.md", "# 细纲\n江晨在雨夜推开旧书店的门，发现柜台后坐着失踪三年的师父，两人对视良久。\n", "utf8");
  writeCleanState("cwd-book", 7);
  await before("shell", {
    command: "cat draft.md > 본문/제8장_相对.md",
    workdir: path.join(tmp, "cwd-book"),
  });

  fs.writeFileSync("book/본문/제002장_续写.md", "已有正文。\n", "utf8");
  await before("edit", { path: "book/본문/제002장_续写.md" });
  fs.writeFileSync(
    "book/추적/_tracking-state.json",
    JSON.stringify({ schema_version: 4, state_revision: 1, last_committed_chapter: 0 }) + "\n",
    "utf8"
  );
  await assert.rejects(
    () => before("edit", { path: "book/본문/제002장_续写.md" }),
    /mode=revision 트랜잭션을 다시 제출해 파생 문서를 재구성/,
    "existing prose revision must be blocked while derived state is inconsistent"
  );
  writeCleanState("book", 3);

  await assert.rejects(
    () => before("shell", { command: "cat draft.md > book/본문/제003장_绕过.md" }),
    /본문 쓰기 차단[\s\S]*Shell 명령에서 본문 쓰기 대상을 확인했습니다/,
    "shell redirect must be blocked without claiming the static parser is unbypassable"
  );
  await before("shell", { command: "grep 'book/본문/제003장_绕过.md' notes.md" });

  // patch는 OpenCode의 edit 계열 도구다. 일부 모델은 patch만 노출하고 write/edit는 숨긴다.
  // 사전 검사와 저장 후 보완 검사 모두 이를 인식해야 한다. 그렇지 않으면 그 모델의 전체 실행에서 개요 검사와 본문 보완 검사가 사라진다.
  const addPatch = (target) =>
    `*** Begin Patch\n*** Add File: ${target}\n+正文第一句。\n*** End Patch\n`;
  await expectBlocked(
    () => before("patch", { patchText: addPatch("book/본문/제004장_补丁.md") }),
    "patch must not bypass the outline guard"
  );
  fs.writeFileSync("book/개요/상세개요_제4장.md", "# 细纲\n江晨在雨夜推开旧书店的门，发现柜台后坐着失踪三年的师父，两人对视良久。\n", "utf8");
  await before("patch", { patchText: addPatch("book/본문/제004장_补丁.md") });

  // *** Move to:는 patch의 이동/이름 변경 형식이며 저장 경로는 목적지다. 대상 추출의 각 형태(Delete+Move,
  // 본문/ 밖으로 이동, 순수 Delete)는 test-prose-net-parity.sh B절에서 검사한다. 여기서는 플러그인이 patchText를 코어에 넘기고
  // 목적지 장 번호로 차단하는지만 확인한다(원본 draft.md는 본문이 아니므로 검사 대상으로 판단하면 안 됨).
  const movePatch = (source, destination) =>
    `*** Begin Patch\n*** Update File: ${source}\n*** Move to: ${destination}\n+正文第一句。\n*** End Patch\n`;
  await assert.rejects(
    () => before("patch", { patchText: movePatch("draft.md", "book/본문/제009장_搬家.md") }),
    /본문 쓰기 차단[\s\S]*제 9 장에 상세 개요가 없습니다/,
    "patch *** Move to: 的拦截判据必须算在目的地章号上"
  );

  fs.mkdirSync("short", { recursive: true });
  fs.writeFileSync("short/설정.md", "# 설정\n", "utf8");
  await expectBlocked(
    () => before("write", { path: "short/본문.md" }),
    "new short prose without section outline"
  );
  fs.writeFileSync("short/구간개요.md", "# 小节大纲\n", "utf8");
  await before("write", { path: "short/본문.md" });

  fs.writeFileSync(
    "book/본문/제001장_开局.md",
    `${"街灯一盏盏亮起。".repeat(30)}\nTODO 此处待补`,
    "utf8"
  );
  const afterOutput = await after("write", { path: "book/본문/제001장_开局.md" }, "write complete");
  assert.match(afterOutput, /^write complete\n\n/);
  assert.match(afterOutput, /본문 보완 검사/);
  assert.match(afterOutput, /자리표시자/);

  // content가 구조화 배열이면 기존 항목을 다시 쓰지 않고 text 항목 하나를 추가한다.
  const structured = await after("write", { path: "book/본문/제001장_开局.md" }, [
    { type: "text", text: "write complete" },
  ]);
  assert.equal(structured[0].text, "write complete");
  assert.match(structured.at(-1).text, /본문 보완 검사/);

  fs.writeFileSync("notes.md", "TODO\n", "utf8");
  assert.equal(await after("write", { path: "notes.md" }, "unchanged"), "unchanged");

  fs.writeFileSync(
    "book/본문/제004장_补丁.md",
    `${"街灯一盏盏亮起。".repeat(30)}\nTODO 此处待补`,
    "utf8"
  );
  const patchAfterOutput = await after(
    "patch",
    { patchText: addPatch("book/본문/제004장_补丁.md") },
    "patch applied"
  );
  assert.match(patchAfterOutput, /본문 보완 검사/);
  assert.match(patchAfterOutput, /자리표시자/);

  assert.equal(await after("patch", { patchText: addPatch("notes.md") }, "unchanged"), "unchanged");

  // 이동 패치의 쓰기 후 보완 검사: **목적지**의 장을 검사해야 한다. Add/Update File만 인식하면 여기서 draft.md를 추출해
  // 검사 전체가 빈 상태로 통과하므로 본문/로 옮긴 장에 TODO가 있어도 아무 알림이 없다.
  fs.writeFileSync(
    "book/본문/제009장_搬家.md",
    `${"街灯一盏盏亮起。".repeat(30)}\nTODO 此处待补`,
    "utf8"
  );
  const moveAfterOutput = await after(
    "patch",
    { patchText: movePatch("draft.md", "book/본문/제009장_搬家.md") },
    "patch applied"
  );
  assert.match(moveAfterOutput, /본문 보완 검사\(book\/본문\/제009장_搬家\.md）/);
  assert.match(moveAfterOutput, /자리표시자/);

  // 실패한 도구 호출에는 쓰기 후 보완 검사를 하지 않고 결과를 그대로 유지한다.
  const failed = { tool: "write", input: { path: "book/본문/제001장_开局.md" }, status: "error", error: { message: "x" } };
  await hooks.tool["execute.after"](failed);
  assert.equal(failed.result, undefined);

  // 쓰기 계열이 아닌 도구는 dispatch 전에 반환하며 read/grep/... 때문에 git rev-parse를 매번 fork하면 안 된다.
  // 플러그인은 OpenCode 서비스 프로세스에 상주하므로 동기 execSync 호출이 이벤트 루프를 막는다.
  // 기록만 하는 git shim으로 PATH를 대체한다. 읽기 도구 후에는 기록이 비고 쓰기 도구 후에는 기록이 있어야 한다.
  // 두 번째 조건은 이 단언이 항상 참이 되는 것을 방지한다.
  if (process.platform !== "win32") {
    const shimDir = path.join(tmp, "bin");
    const gitLog = path.join(tmp, "git-calls.log");
    fs.mkdirSync(shimDir, { recursive: true });
    fs.writeFileSync(
      path.join(shimDir, "git"),
      `#!/bin/sh\nprintf '%s\\n' "$*" >> ${JSON.stringify(gitLog)}\nprintf '%s\\n' ${JSON.stringify(tmp)}\n`,
      { mode: 0o755 }
    );
    const realPath = process.env.PATH;
    process.env.PATH = shimDir;
    try {
      for (const tool of ["read", "grep", "glob", "question", "subagent", "webfetch"]) {
        await before(tool, {});
      }
      assert.equal(
        fs.existsSync(gitLog),
        false,
        "non-write tools must not fork git rev-parse"
      );
      await before("write", { path: "book/본문/제002장_续写.md" });
      assert.match(
        fs.readFileSync(gitLog, "utf8"),
        /rev-parse/,
        "git shim must actually intercept projectRoot()"
      );
    } finally {
      process.env.PATH = realPath;
    }
  }

  const compact = { system: [] };
  await hooks.session.compaction(compact);
  assert(compact.system.some((part) => part.type === "text" && part.text.includes(`Writing context: ${path.join("book", "추적", "문맥.md")}`)));

  // 공유 코어의 staged commit 검사도 git을 호출한다. 실제 배포 배치의 모듈을 직접 호출하고 프록시는 기록과 전달만 수행해
  // stagedMarkdownWarnings()가 실제로 spawnSync에 넘기는 options를 검증한다.
  const require = createRequire(import.meta.url);
  const core = require(path.join(deployDir, "lib", "story_hook_core.js"));
  core.stagedMarkdownWarnings(tmp);

  const projectRootCalls = childProcessCalls.filter(
    (call) => call.method === "execSync" && call.command === "git rev-parse --show-toplevel"
  );
  assert(projectRootCalls.length > 0, "projectRoot() must exercise execSync");
  assert(
    projectRootCalls.every((call) => call.options?.windowsHide === true),
    "projectRoot() must hide the git console window on Windows"
  );

  const tryGitCalls = childProcessCalls.filter(
    (call) => call.method === "execSync" && /^git diff --name-only(?: --cached)?$/.test(call.command)
  );
  assert.equal(tryGitCalls.length, 2, "preCompactOutput() must exercise both tryGit() calls");
  assert(
    tryGitCalls.every((call) => call.options?.windowsHide === true),
    "tryGit() must hide the git console window on Windows"
  );

  const stagedWarningCalls = childProcessCalls.filter(
    (call) => call.method === "spawnSync" && call.command === "git" && call.args?.includes("--cached")
  );
  assert.equal(stagedWarningCalls.length, 1, "stagedMarkdownWarnings() must exercise spawnSync once");
  assert.equal(
    stagedWarningCalls[0].options?.windowsHide,
    true,
    "stagedMarkdownWarnings() must hide the git console window on Windows"
  );

  console.log("OK: OpenCode plugin guards outlines and reports after-write findings behaviorally");
} finally {
  childProcess.execSync = originalExecSync;
  childProcess.spawnSync = originalSpawnSync;
  syncBuiltinESMExports();
  process.chdir(originalCwd);
  fs.rmSync(tmp, { recursive: true, force: true });
}
