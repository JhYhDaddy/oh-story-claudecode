#!/usr/bin/env node
// opencode-mock-llm.mjs — 실제 OpenCode 2.x 런타임 테스트용 OpenAI 호환 모의 모델.
//
// 동작: tools가 있는 첫 요청에는 MOCK_SCRIPT 파일의 JSON 배열 [{name, arguments}]에 따라 도구 호출을 한 번에 반환한다.
// (요청마다 파일을 다시 읽으므로 mock을 재시작하지 않고 두 `opencode run` 사이에 시나리오를 바꿀 수 있다. 파일이 없으면 도구를 호출하지 않는다.)
// 메시지에 이미 도구 결과가 있으면 'done'으로 종료하고, tools가 없는 요청(제목 생성 등)에는 제목을 반환한다.
// 각 요청 본문을 MOCK_LOG(JSONL)에 추가한다. 테스트는 이를 통해 모델이 실제로 받은 도구 목록과 반환 내용을 확인한다.
// 시작 후 수신 포트를 stdout 첫 줄에 출력한다. MOCK_PORT 기본값은 0(임의 포트)이다.
import fs from "node:fs"
import http from "node:http"

const log = process.env.MOCK_LOG
const script = process.env.MOCK_SCRIPT
const usage = { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 }

function scriptedToolCalls() {
  let calls = []
  try {
    calls = JSON.parse(fs.readFileSync(script, "utf8"))
  } catch {}
  return calls.map((call, index) => ({
    id: `call_${index}`,
    type: "function",
    function: { name: call.name, arguments: JSON.stringify(call.arguments ?? {}) },
  }))
}

function chunk(delta, finish = null) {
  return {
    id: "chatcmpl-mock",
    object: "chat.completion.chunk",
    created: Math.floor(Date.now() / 1000),
    model: "probe",
    choices: [{ index: 0, delta, finish_reason: finish }],
  }
}

function reply(res, stream, message, finish) {
  if (stream === false) {
    res.writeHead(200, { "content-type": "application/json" })
    res.end(JSON.stringify({
      id: "chatcmpl-mock",
      object: "chat.completion",
      model: "probe",
      usage,
      choices: [{ index: 0, finish_reason: finish, message: { role: "assistant", ...message } }],
    }))
    return
  }
  const chunks = [chunk({ role: "assistant", content: message.content ?? "" })]
  for (const [index, call] of (message.tool_calls ?? []).entries()) chunks.push(chunk({ tool_calls: [{ index, ...call }] }))
  chunks.push({ ...chunk({}, finish), usage })
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" })
  for (const item of chunks) res.write(`data: ${JSON.stringify(item)}\n\n`)
  res.end("data: [DONE]\n\n")
}

const server = http.createServer((req, res) => {
  let raw = ""
  req.on("data", (data) => (raw += data))
  req.on("end", () => {
    let body = {}
    try {
      body = JSON.parse(raw || "{}")
    } catch {}
    if (log) fs.appendFileSync(log, JSON.stringify({ path: req.url, body }) + "\n")
    if (!req.url.includes("/chat/completions")) {
      res.writeHead(404, { "content-type": "application/json" })
      res.end("{}")
      return
    }
    const messages = Array.isArray(body.messages) ? body.messages : []
    const hasTools = Array.isArray(body.tools) && body.tools.length > 0
    const answered = messages.some((message) => message.role === "tool")
    const toolCalls = hasTools && !answered ? scriptedToolCalls() : []
    if (toolCalls.length) {
      reply(res, body.stream, { content: null, tool_calls: toolCalls }, "tool_calls")
    } else {
      reply(res, body.stream, { content: hasTools ? "done" : "Mock title" }, "stop")
    }
  })
})

server.listen(Number(process.env.MOCK_PORT || 0), "127.0.0.1", () => {
  process.stdout.write(`${server.address().port}\n`)
})
