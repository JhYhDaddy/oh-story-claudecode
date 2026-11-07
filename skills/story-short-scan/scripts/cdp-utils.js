/**
 * CDP 유틸리티 — 플랫폼별 수집 스크립트의 공통 의존성.
 * 사용법:
 *   const { ab, sleep, evalJSON, evalJSONBase64, scrollLoad, getArg, safeStr, localDateStamp } = require("./cdp-utils");
 * 사전 실행:
 *   node {SKILL_DIR}/browser-cdp/scripts/setup-cdp-chrome.js 9222
 */

const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

/**
 * Windows의 `agent-browser`는 실제 agent-browser-win32-*.exe 또는 포함된 Node CLI로 전달하는 npm shim(.cmd/.ps1)이다.
 * Node는 셸 없는 `.cmd` execFile을 거부한다(CVE-2024-27980). argv 배열을 셸로 보내면 변형된다.
 * `.cmd`의 `%*`는 cmd.exe에서 다시 토큰화되어 공백으로 나뉘고 & | ^에서 깨진다. PowerShell에서 이름만으로 shim을 호출하면
 * 전체 배열이 공백으로 합쳐진 단일 인자가 된다. 문제 지점이 런타임마다 달라 특정 셸 경로를 보강하는 대신 셸을 완전히 우회한다.
 * `.cmd`를 읽어 실제 프로그램과 고정 선행 인자를 복구한 뒤 argv 배열을 그대로 전달해 직접 execFile한다.
 */
function resolveWindowsAgentBrowser(argv) {
  const dirs = String(process.env.PATH || "").split(path.delimiter);
  let cmdPath = null;
  for (const dir of dirs) {
    if (!dir) continue;
    const candidate = path.join(dir, "agent-browser.cmd");
    if (fs.existsSync(candidate)) {
      cmdPath = candidate;
      break;
    }
  }
  if (!cmdPath) return { file: "agent-browser", args: argv };
  const dir = path.dirname(cmdPath);
  const forwardLine =
    fs
      .readFileSync(cmdPath, "utf8")
      .split(/\r?\n/)
      .find((line) => line.includes("%*")) || "";
  const tokens = [...forwardLine.matchAll(/"([^"]*)"/g)]
    .map((m) => m[1])
    .map((t) =>
      t
        .replace(/%~dp0/gi, () => dir + path.sep)
        .replace(/%dp0%/gi, () => dir + path.sep)
    );
  const jsIndex = tokens.findIndex((t) => /\.[cm]?js$/i.test(t));
  if (jsIndex >= 0) {
    return { file: process.execPath, args: [...tokens.slice(jsIndex), ...argv] };
  }
  if (tokens.length > 0) {
    return { file: tokens[0], args: [...tokens.slice(1), ...argv] };
  }
  return { file: "agent-browser", args: argv };
}

/**
 * 셸 없는 호출을 만든다. POSIX는 기본 `agent-browser` 바이너리를 직접 실행하고 Windows는 npm `.cmd`에서 실제 대상을 찾는다.
 * 인자 배열은 그대로 전달하며 cmd.exe/PowerShell을 거치지 않는다.
 */
function buildAgentBrowserInvocation(port, args, platform = process.platform) {
  const argv = ["--cdp", String(port), ...args.map(String)];
  if (platform !== "win32") {
    return { file: "agent-browser", args: argv };
  }
  return resolveWindowsAgentBrowser(argv);
}

// ---------------------------------------------------------------------------
// agent-browser 유틸리티
// ---------------------------------------------------------------------------

/**
 * agent-browser CLI 호출.
 * @param {number} port - CDP 포트
 * @param {...string} args - agent-browser 인자
 * @returns {string} 앞뒤 공백을 제거한 stdout
 */
function ab(port, ...args) {
  const invocation = buildAgentBrowserInvocation(port, args);
  try {
    return execFileSync(
      invocation.file,
      invocation.args,
      {
        encoding: "utf-8",
        timeout: 20000,
        stdio: ["pipe", "pipe", "pipe"],
        windowsHide: true,
      }
    ).trim();
  } catch (error) {
    const stderr = error && error.stderr ? String(error.stderr).trim() : "";
    const stdout = error && error.stdout ? String(error.stdout).trim() : "";
    const detail = stderr || stdout || (error && error.message) || "unknown error";
    throw new Error(`agent-browser failed: ${detail}`, { cause: error });
  }
}

/** ms 밀리초 대기. 크로스 플랫폼이며 시스템 sleep 명령에 의존하지 않는다. */
function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function parseJSONResult(raw) {
  if (!raw || raw === "ERR") {
    throw new Error("agent-browser returned no JSON result");
  }
  try {
    let parsed = JSON.parse(raw);
    if (typeof parsed === "string") {
      try { parsed = JSON.parse(parsed); } catch {}
    }
    return parsed;
  } catch (error) {
    throw new Error(`agent-browser returned invalid JSON: ${String(raw).slice(0, 160)}`, {
      cause: error,
    });
  }
}

/**
 * 브라우저 안에서 JS를 실행하고 JSON 반환값을 파싱한다.
 * 항상 base64(-b)를 쓴다. 본문 추출 JS의 따옴표·역슬래시는 Windows 명령행에서 .cmd %*와 PowerShell의 재파싱으로 그대로 전달되지 않는다.
 * base64는 인자를 [A-Za-z0-9+/=]로 제한하며 수집 스크립트의 evalJSONBase64와 같은 안전한 경로를 사용한다.
 */
function evalJSON(port, js) {
  return evalJSONBase64(port, js);
}

/** agent-browser의 base64 인자로 복잡한 JS를 실행해 명령행 이스케이프·인자 경계 문제를 피한다. */
function evalJSONBase64(port, js) {
  const encoded = Buffer.from(String(js), "utf8").toString("base64");
  return parseJSONResult(ab(port, "eval", "-b", encoded));
}

/**
 * 값을 브라우저 eval 문자열에 안전하게 삽입한다.
 * JSON.stringify로 따옴표·역슬래시 등이 eval 문자열을 깨뜨리지 않게 한다.
 * @param {*} val - 삽입할 값
 * @returns {string} 따옴표를 포함한 JSON 문자열 표현
 */
function safeStr(val) {
  return JSON.stringify(String(val));
}

/**
 * 페이지를 스크롤해 추가 내용을 로드한다.
 * @param {number} port - CDP 포트
 * @param {number} times - 스크롤 횟수
 * @param {number} [interval=1000] - 스크롤 간격(ms)
 */
function scrollLoad(port, times, interval = 1000) {
  for (let i = 0; i < times; i++) {
    ab(port, "eval", "window.scrollBy(0, window.innerHeight)");
    sleep(interval);
  }
}

/** --xxx 인자를 파싱한다. */
function getArg(args, name) {
  const i = args.indexOf(name);
  if (i >= 0) return i + 1 < args.length ? args[i + 1] : null;
  const prefix = `${name}=`;
  const inline = args.find((arg) => String(arg).startsWith(prefix));
  return inline === undefined ? null : String(inline).slice(prefix.length);
}

/**
 * 출력 파일명 날짜(YYYYMMDD)는 항상 현지 달력 날짜를 쓴다.
 * new Date().toISOString().slice(0,10)은 UTC 날짜라 UTC+8보다 8시간 늦으므로 쓰면 안 된다.
 * 파일명은 순위별 하루 한 파일이라는 유일한 중복 키다. 베이징 00:00–08:00 수집에서 UTC를 쓰면 어제 파일명으로 돌아가
 * 전날 밤의 같은 이름 보고서를 덮고 데이터를 전날 것으로 표시한다.
 * @param {Date} [date] - 기본 현재 시각
 * @returns {string} YYYYMMDD
 */
function localDateStamp(date) {
  const d = date instanceof Date ? date : new Date();
  const y = String(d.getFullYear()).padStart(4, "0");
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}${m}${day}`;
}

/**
 * 수집 진입점을 실행해 빈·부분 출력을 기계 판독 가능한 CLI 상태로 바꾼다.
 * 이전 진입점은 정수를, 다중 대상 수집기는 {planned,written,failed,partial,partialReasons}를 반환할 수 있다.
 */
function runCli(main, label) {
  Promise.resolve()
    .then(main)
    .then((result) => {
      const outcome = Number.isInteger(result)
        ? { planned: result, written: result, failed: 0, partial: false, partialReasons: [] }
        : result;
      if (!outcome || !Number.isInteger(outcome.written) || outcome.written < 1) {
        throw new Error("no output was written");
      }
      const failed = Number.isInteger(outcome.failed) ? outcome.failed : 0;
      const planned = Number.isInteger(outcome.planned)
        ? outcome.planned
        : outcome.written + failed;
      const reasons = Array.isArray(outcome.partialReasons)
        ? outcome.partialReasons.filter(Boolean).map(String)
        : [];
      if (outcome.partial || failed > 0) {
        const details = [`wrote ${outcome.written}/${planned}`];
        if (failed > 0) details.push(`failed ${failed}`);
        details.push(...reasons);
        console.error(`${label} partial: ${details.join("; ")}`);
        process.exitCode = 2;
      }
    })
    .catch((error) => {
      const message = error && error.message ? error.message : String(error);
      console.error(`${label} failed: ${message}`);
      process.exitCode = 1;
    });
}

module.exports = {
  ab,
  sleep,
  evalJSON,
  evalJSONBase64,
  buildAgentBrowserInvocation,
  safeStr,
  scrollLoad,
  getArg,
  localDateStamp,
  runCli,
};
