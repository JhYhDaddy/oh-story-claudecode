#!/usr/bin/env node
// setup-cdp-chrome.js
// CDP(Chrome DevTools Protocol) 디버깅을 지원하는 Chrome 환경을 준비한다(크로스 플랫폼).
// agent-browser가 이 스크립트를 통해 사용자의 Chrome 로그인 상태를 재사용할 수 있다.
//
// 사용법:
//   node setup-cdp-chrome.js [port] [options]
//
// 옵션:
//   --detect-only            현재 상태만 구조화해 탐지하며 변경하지 않는다.
//   --yes                    기존 Chrome 종료에 동의하고 대화형 질문을 건너뛴다.
//   --reset                  ~/chrome-debug-profile을 비운 뒤 다시 복사한다.
//   --profile <name>         지정 Chrome 프로필을 사용한다(기본: Default).
//   --dry-run                실행 예정 작업만 출력하며 실제 실행하지 않는다.
//
// 설명: CDP 포트가 수신 중이면 기본적으로 기존 Chrome을 재사용하고 0으로 종료한다. --reset 또는 명시적
//       --profile을 지정하면 재사용하지 않는다. 두 옵션은 디버그 프로필 재생성을 뜻하며 로그인 만료 시 이 경로를 쓴다.
//       먼저 기존 Chrome을 종료한다. 비 TTY에서는 --yes가 필요하며 없으면 NEEDS_CONSENT를 알리고 exit 3으로 종료한다.
//       재생성 경로에는 두 필수 관문이 있다. 프로세스 종료 후 포트 응답이 실제로 없어야 하며 그렇지 않으면 프로필 변경 전에
//       exit 1로 중단한다. 실행 중인 Chrome의 프로필은 삭제하지 않는다. 실행 후에는 포트의 응답자가 이번에 시작한
//       인스턴스임을 입증해야 한다. 식별 정보가 있고 재생성 전과 다르며, spawn한 프로세스가 살아 있고, LISTEN 소유자가
//       모두 해당 프로세스 트리에 속하며, 그중 이번 --remote-debugging-port를 가진 소유자가 실제로 있어야 한다.
//       어느 조건이든 확인 불가를 포함해 입증하지 못하면 성공을 보고하지 않는다. 다른 세션을 새 브라우저로 전달하지 않기 위해서다.
//
// 종료 코드:
//   0  성공 / detect-only 완료
//   1  일반 오류(환경 누락, 시간 초과 등)
//   2  사용자 거부(TTY 모드에서 N 응답)
//   3  동의가 필요하지만 비 TTY이며 --yes가 없음
//
// detect-only 구조화 출력(stdout, 행마다 KEY=value):
//   CDP_STATUS=ready|needs-setup
//   CDP_URL=...                    (ready일 때만)
//   BROWSER=...                    (ready일 때만)
//   CHROME_RUNNING=yes|no
//   CHROME_PID_COUNT=N             (CHROME_RUNNING=yes일 때만)

"use strict";

const { execSync, spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const net = require("net");
const os = require("os");
const path = require("path");
const readline = require("readline");

// ---------------------------------------------------------------------------
// 인자 파싱
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const flags = { dryRun: false, yes: false, detectOnly: false, reset: false };
  let profile = "Default";
  // --profile 명시 여부: 기본값 Default로는 미지정과 Default 명시를 구분할 수 없다.
  // 두 경우는 CDP 준비 완료 분기에서 의미가 다르다(재사용 또는 지정 프로필로 재생성).
  let profileExplicit = false;
  let port = null;

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    switch (a) {
      case "--dry-run": flags.dryRun = true; break;
      case "--yes": case "-y": flags.yes = true; break;
      case "--detect-only": flags.detectOnly = true; break;
      case "--reset": flags.reset = true; break;
      case "--profile":
        profile = argv[++i];
        if (!profile) {
          console.error("❌ --profile에는 값이 필요합니다(예: --profile \"Profile 1\")");
          process.exit(1);
        }
        profileExplicit = true;
        break;
      default:
        if (/^\d+$/.test(a)) {
          port = parseInt(a, 10);
        } else if (a.startsWith("--")) {
          console.error(`⚠️  알 수 없는 인수: ${a}`);
        } else {
          console.error(`⚠️  무시한 인수: ${a}`);
        }
    }
  }

  if (port === null) port = 9222;
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    console.error(`❌ 잘못된 포트: ${port}. 1~65535의 정수여야 합니다.`);
    process.exit(1);
  }

  return { flags, profile, profileExplicit, port };
}

const ARGS = parseArgs(process.argv.slice(2));
const CDP_PORT = ARGS.port;
const PLATFORM = os.platform();

// ---------------------------------------------------------------------------
// 플랫폼 설정 매핑
// ---------------------------------------------------------------------------

const PLATFORM_CONFIG = {
  darwin: {
    chromePaths: [
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ],
    profileDir: path.join(
      os.homedir(),
      "Library",
      "Application Support",
      "Google",
      "Chrome"
    ),
    findChrome() {
      for (const p of this.chromePaths) if (fs.existsSync(p)) return p;
      return null;
    },
    listChromePids() {
      try {
        const out = execSync("pgrep -x 'Google Chrome'", { encoding: "utf-8" }).trim();
        return out.split("\n").map(Number).filter((n) => n > 0);
      } catch { return []; }
    },
    killChrome() {
      try { execSync("pkill -9 -x 'Google Chrome'", { stdio: "ignore" }); } catch {}
    },
  },
  win32: {
    chromePaths: [
      path.join(process.env["PROGRAMFILES(X86)"] || "", "Google", "Chrome", "Application", "chrome.exe"),
      path.join(process.env.PROGRAMFILES || "", "Google", "Chrome", "Application", "chrome.exe"),
      path.join(process.env.LOCALAPPDATA || "", "Google", "Chrome", "Application", "chrome.exe"),
    ],
    profileDir: path.join(
      process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local"),
      "Google", "Chrome", "User Data"
    ),
    findChrome() {
      for (const p of this.chromePaths) if (p && fs.existsSync(p)) return p;
      return null;
    },
    listChromePids() {
      try {
        const out = execSync('tasklist /FI "IMAGENAME eq chrome.exe" /NH /FO CSV', { encoding: "utf-8" }).trim();
        return out.split("\n").map((line) => {
          const m = line.match(/"chrome.exe","(\d+)"/i);
          return m ? parseInt(m[1], 10) : 0;
        }).filter((n) => n > 0);
      } catch { return []; }
    },
    killChrome() {
      try { execSync("taskkill /F /IM chrome.exe", { stdio: "ignore" }); } catch {}
    },
  },
  linux: {
    chromePaths: [
      "/usr/bin/google-chrome-stable",
      "/usr/bin/google-chrome",
      "/opt/google/chrome/google-chrome",
    ],
    profileDir: path.join(os.homedir(), ".config", "google-chrome"),
    findChrome() {
      for (const p of this.chromePaths) if (fs.existsSync(p)) return p;
      return null;
    },
    listChromePids() {
      // 일반적인 Chrome 프로세스 이름을 포함한다.
      const patterns = ["google-chrome-stable", "google-chrome", "chrome"];
      const pids = new Set();
      for (const pat of patterns) {
        try {
          const out = execSync(`pgrep -x ${pat}`, { encoding: "utf-8" }).trim();
          out.split("\n").map(Number).filter((n) => n > 0).forEach((n) => pids.add(n));
        } catch {}
      }
      return [...pids];
    },
    killChrome() {
      for (const pat of ["google-chrome-stable", "google-chrome", "chrome"]) {
        try { execSync(`pkill -9 -x ${pat}`, { stdio: "ignore" }); } catch {}
      }
    },
  },
};

// ---------------------------------------------------------------------------
// 유틸리티 함수
// ---------------------------------------------------------------------------

function log(msg) { console.log(msg); }
function warn(msg) { console.warn("⚠️  " + msg); }
function ok(msg) { console.log("✅ " + msg); }
function err(msg) { console.error("❌ " + msg); }

function getConfig() {
  const config = PLATFORM_CONFIG[PLATFORM];
  if (!config) {
    err(`지원하지 않는 플랫폼: ${PLATFORM}. darwin/win32/linux를 지원합니다.`);
    process.exit(1);
  }
  return config;
}

/** ms 밀리초 동안 동기 대기한다(setTimeout이나 시스템 sleep에 의존하지 않음). */
function sleepSync(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

/**
 * HTTP GET으로 CDP 엔드포인트를 검사한다. 4xx/5xx를 거부하고 응답 본문을 비운다.
 * agent:false가 필수다. Node 19+의 http.globalAgent는 기본 keepAlive여서 탐지 소켓이 풀에 남는다.
 * sleepSync가 이벤트 루프를 막고 종료·시작을 기다리는 동안 서버가 5초 유휴 연결을 닫아도 클라이언트는 FIN을 처리하지 못한다.
 * 다음 탐지에서 죽은 소켓을 재사용하면 ECONNRESET이 발생해 살아 있는 포트를 응답 없음으로 오판한다.
 * 이 거짓 음성은 아래 포트 관문을 통과시킬 수 있으므로 매번 새 연결을 사용해야 한다.
 */
function httpGet(url) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, { timeout: 3000, agent: false }, (res) => {
      let body = "";
      res.on("data", (chunk) => (body += chunk));
      res.on("end", () => {
        if (res.statusCode >= 400) {
          reject(new Error(`HTTP ${res.statusCode}`));
        } else {
          resolve(body);
        }
      });
    });
    req.on("error", reject);
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("timeout"));
    });
  });
}

async function probeCDP(port) {
  try {
    const version = await httpGet(`http://127.0.0.1:${port}/json/version`);
    return version;
  } catch {
    return null;
  }
}

/** 원시 TCP 탐지: HTTP 500이나 잘못된 JSON도 포트 점유를 뜻하므로 프로필 파괴 작업을 허용하는 근거가 될 수 없다. */
function probeTcp(port, timeoutMs = 1000) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: "127.0.0.1", port });
    let settled = false;
    const done = (listening) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(listening);
    };
    socket.setTimeout(timeoutMs);
    socket.once("connect", () => done(true));
    socket.once("error", () => done(false));
    socket.once("timeout", () => done(false));
  });
}

/**
 * /json/version 응답에서 브라우저 인스턴스를 구분할 식별자를 가져온다.
 * Chrome은 실행할 때마다 새로운 browser GUID(webSocketDebuggerUrl의 마지막 부분)를 사용하므로 이 목적에 가장 적합하다.
 * 가져오지 못하면 null을 반환한다. 호출자는 null을 반드시 “비교 불가”로 처리해야 하며, 절대로 “같음”이나 “다름”으로 처리해서는 안 된다.
 */
function cdpIdentity(version) {
  if (!version) return null;
  try {
    const obj = JSON.parse(version);
    if (obj.webSocketDebuggerUrl) return String(obj.webSocketDebuggerUrl);
  } catch {}
  return null;
}

/**
 * TCP 포트가 실제로 수신을 멈출 때까지 기다린다. true는 비어 있음, false는 시간 초과 후에도 수신 중임을 뜻한다.
 * HTTP 500이나 잘못된 응답은 CDP가 비정상이라는 뜻일 뿐 포트가 비었다는 뜻이 아니므로 probeCDP를 쓰면 안 된다.
 */
async function waitForPortFree(port, maxMs = 8000, stepMs = 500, needQuiet = 2) {
  const start = Date.now();
  let quiet = 0;
  for (;;) {
    if (await probeTcp(port)) {
      quiet = 0;
    } else if (++quiet >= needQuiet) {
      return true;
    }
    if (Date.now() - start >= maxMs) return false;
    sleepSync(stepMs);
  }
}

/** 진단용으로 포트 점유 프로세스를 가능한 범위에서 조회한다. 실패하면 null이며 판정에는 영향을 주지 않는다. */
function describePortHolder(port) {
  const cmd =
    PLATFORM === "win32"
      ? `netstat -ano -p tcp | findstr LISTENING | findstr :${port}`
      : `lsof -nP -iTCP:${port} -sTCP:LISTEN`;
  try {
    const out = execSync(cmd, {
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    const line = out
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l && !/^COMMAND\s/.test(l))[0];
    return line ? line.slice(0, 200) : null;
  } catch {
    return null;
  }
}

/** 읽기 전용 조회 명령으로 stdout을 얻는다. 명령 부재·0이 아닌 종료·시간 초과는 모두 null이다. */
function queryStdout(cmd) {
  try {
    const out = execSync(cmd, {
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "ignore"],
      timeout: 5000,
      maxBuffer: 8 * 1024 * 1024,
    });
    return typeof out === "string" ? out : String(out);
  } catch {
    return null;
  }
}

/**
 * 지정 포트의 LISTEN 프로세스 PID 목록을 얻는다.
 * CDP 응답을 확인한 뒤에만 호출하므로 이 시점에는 반드시 수신자가 있다. 빈 결과는 도구 누락이나 조회 불가를 뜻한다.
 * 항상 판정 불가를 나타내는 null을 반환하며, 점유자가 없다는 뜻으로 받아들여 허용하면 안 된다.
 */
function listPortListenerPids(port) {
  const queries =
    PLATFORM === "win32"
      ? [
          {
            kind: "pid",
            cmd: `powershell -NoProfile -NonInteractive -Command "Get-NetTCPConnection -State Listen -LocalPort ${port} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"`,
          },
          {
            kind: "pid",
            cmd: `pwsh -NoProfile -NonInteractive -Command "Get-NetTCPConnection -State Listen -LocalPort ${port} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"`,
          },
          // 일부 Windows TCP 공급자는 수신 State를 0으로 반환해 -State Listen과
          // netstat에서 누락된다. 아래는 netstat 대체 경로와 같은 로컬 포트 + 원격 포트 0 조건이다.
          // HTTP 응답 확인 후에만 조회하며 소유 PID의 실행 트리·명령행 검증은 그대로 적용한다.
          ...["powershell", "pwsh"].map((shell) => ({
            kind: "pid",
            cmd: `${shell} -NoProfile -NonInteractive -Command "Get-NetTCPConnection -LocalPort ${port} -ErrorAction SilentlyContinue | Where-Object RemotePort -eq 0 | Select-Object -ExpandProperty OwningProcess"`,
          })),
          { kind: "netstat", cmd: "netstat -ano -p tcp" },
        ]
      : [
          { kind: "pid", cmd: `lsof -nP -iTCP:${port} -sTCP:LISTEN -t` },
          // Linux에는 lsof가 없는 경우가 많으므로 ss / fuser를 대안으로 사용한다.
          { kind: "ss", cmd: `ss -H -ltnp "sport = :${port}"` },
          { kind: "pid", cmd: `fuser -n tcp ${port}` },
        ];
  for (const { kind, cmd } of queries) {
    const out = queryStdout(cmd);
    if (out === null) continue;
    const pids = new Set();
    if (kind === "netstat") {
      // 현지화된 상태 문자열을 읽지 않는다. 수신 행의 안정된 형식은 TCP + 로컬 대상 포트 +
      // foreign port 0 + 마지막 Owning PID 열이다. 연결된 세션의 foreign port는 0이 아니다.
      for (const line of out.split("\n")) {
        const fields = line.trim().split(/\s+/);
        if (fields.length < 5 || fields[0].toUpperCase() !== "TCP") continue;
        const localPort = Number((fields[1].match(/:(\d+)$/) || [])[1]);
        const foreignPort = Number((fields[2].match(/:(\d+)$/) || [])[1]);
        const pid = Number(fields[fields.length - 1]);
        if (localPort === port && foreignPort === 0 && Number.isInteger(pid) && pid > 0) {
          pids.add(pid);
        }
      }
    } else if (kind === "ss") {
      for (const m of out.matchAll(/pid=(\d+)/g)) pids.add(Number(m[1]));
    } else {
      // PowerShell OwningProcess / lsof -t / fuser: 숫자로만 된 PID 목록.
      for (const tok of out.split(/\s+/)) {
        const n = Number(tok);
        if (Number.isInteger(n) && n > 0) pids.add(n);
      }
    }
    const list = [...pids].filter((n) => n > 0);
    if (list.length > 0) return list;
  }
  return null;
}

/** 시스템 전체 pid -> ppid 표. 조회 불가는 null이며 부모 프로세스가 없다는 뜻은 아니다. */
function listProcessParents() {
  const cmds =
    PLATFORM === "win32"
      ? [
          // 최신 Windows에서는 wmic가 제거되어 PowerShell CIM으로 대체한다(5.1 / 7 모두 시도).
          "wmic process get ProcessId,ParentProcessId /format:csv",
          'powershell -NoProfile -NonInteractive -Command "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId | ConvertTo-Csv -NoTypeInformation"',
          'pwsh -NoProfile -NonInteractive -Command "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId | ConvertTo-Csv -NoTypeInformation"',
        ]
      : ["ps -A -o pid=,ppid="]; // macOS(BSD)와 Linux(procps) 모두 이 명령을 지원한다.
  for (const cmd of cmds) {
    const out = queryStdout(cmd);
    if (out === null) continue;
    const map = new Map();
    if (PLATFORM === "win32") {
      // wmic는 알파벳순, PowerShell은 Select 순이므로 헤더로 열 위치를 찾는다.
      const lines = out.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
      const head = lines.findIndex(
        (l) => /processid/i.test(l) && /parentprocessid/i.test(l)
      );
      if (head < 0) continue;
      const cols = lines[head]
        .split(",")
        .map((c) => c.replace(/"/g, "").trim().toLowerCase());
      const pidCol = cols.indexOf("processid");
      const ppidCol = cols.indexOf("parentprocessid");
      if (pidCol < 0 || ppidCol < 0) continue;
      for (const line of lines.slice(head + 1)) {
        const cells = line.split(",").map((c) => c.replace(/"/g, "").trim());
        const pid = Number(cells[pidCol]);
        const ppid = Number(cells[ppidCol]);
        if (pid > 0 && Number.isInteger(ppid)) map.set(pid, ppid);
      }
    } else {
      for (const line of out.split("\n")) {
        const m = line.trim().match(/^(\d+)\s+(\d+)$/);
        if (m) map.set(Number(m[1]), Number(m[2]));
      }
    }
    if (map.size > 0) return map;
  }
  return null;
}

/** 특정 PID의 전체 명령행을 얻으며 실패하면 null이다. */
function processCommandLine(pid) {
  const cmds =
    PLATFORM === "win32"
      ? [
          `wmic process where "ProcessId=${pid}" get CommandLine /value`,
          `powershell -NoProfile -NonInteractive -Command "(Get-CimInstance Win32_Process -Filter 'ProcessId=${pid}').CommandLine"`,
          `pwsh -NoProfile -NonInteractive -Command "(Get-CimInstance Win32_Process -Filter 'ProcessId=${pid}').CommandLine"`,
        ]
      : [`ps -ww -o command= -p ${pid}`]; // -ww: 긴 Chrome 명령행이 터미널 너비로 잘리지 않게 한다.
  for (const cmd of cmds) {
    const out = queryStdout(cmd);
    if (out === null) continue;
    const text =
      PLATFORM === "win32" ? out.replace(/^\s*CommandLine=/im, "") : out;
    const trimmed = text.trim();
    if (trimmed) return trimmed;
  }
  return null;
}

/** ppid를 거슬러 올라가 PID가 rootPid 자체를 포함한 프로세스 트리에 속하는지 확인한다. */
function isInProcessTree(pid, rootPid, parents) {
  let cur = pid;
  for (let hops = 0; hops < 64; hops++) {
    if (cur === rootPid) return true;
    if (!Number.isInteger(cur) || cur <= 1) return false;
    const next = parents.get(cur);
    if (next === undefined || next === cur) return false;
    cur = next;
  }
  return false;
}

function commandLineHasArgument(commandLine, argument) {
  const escaped = argument.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(?:^|[\\s"'])${escaped}(?=$|[\\s"'])`).test(commandLine);
}

/**
 * 포트에서 응답하는 엔드포인트가 이번 spawn 프로세스 소유임을 입증한다. 두 조건이 모두 필요하다.
 *   ① 모든 LISTEN 소유자가 rootPid의 트리에 속한다. Chrome은 별도 browser 프로세스를 만들고
 *      macOS에서는 re-exec할 수 있으므로 직접 PID가 아니라 전체 트리를 비교한다. 자식이 수신 fd를 상속해
 *      lsof에 표시될 수도 있으므로 하나가 아니라 모든 소유자가 트리에 있어야 한다.
 *   ② 트리 안에 이번 --remote-debugging-port=<port>를 가진 소유자가 실제로 있어야 한다.
 *      트리의 다른 프로세스가 우연히 포트를 점유한 것이 아니라 우리가 설정한 인스턴스임을 입증한다.
 * 어느 단계든 확인할 수 없으면 unverifiable이다. 입증 불가를 입증 완료로 취급하지 않고 실패한다.
 */
function verifyPortOwnedByLaunch(port, rootPid) {
  const fail = (code, lines) => ({ ok: false, code, lines: [`${code}: ${lines[0]}`, ...lines.slice(1)] });
  const unverifiable = (why) =>
    fail("CDP_OWNER_UNVERIFIABLE", [
      `포트 ${port}의 LISTEN 프로세스 소유 관계를 확인할 수 없습니다(${why}).`,
      "시작 성공으로 처리하지 않습니다. 이번에 실행한 인스턴스의 엔드포인트인지 확인할 수 없어 후속 수집에 사용할 수 없습니다.",
      PLATFORM === "win32"
        ? "프로세스 소유 관계를 확인하려면 netstat과 wmic 또는 PowerShell이 필요합니다."
        : "프로세스 소유 관계를 확인하려면 lsof(또는 ss / fuser)와 ps가 필요합니다.",
      `해결 방법: 위 도구를 설치하고 다시 실행하거나, 포트 ${port}에서 방금 실행한 Chrome이 작동하는지 직접 확인하세요.`,
    ]);

  if (!rootPid) return unverifiable("spawn에서 pid를 받지 못함");
  const listeners = listPortListenerPids(port);
  if (!listeners) return unverifiable("이 포트를 수신하는 프로세스를 찾을 수 없음");

  // 소유자가 spawn한 PID 자체라면 프로세스 표를 읽지 않는다. 가장 흔한 형태인 Chrome browser가
  // 직접 시작한 프로세스인 경우 wmic/ps 이외의 추가 요소에 의존하지 않는다.
  let outside = listeners.filter((pid) => pid !== rootPid);
  if (outside.length > 0) {
    const parents = listProcessParents();
    if (!parents) return unverifiable("프로세스 목록(pid/ppid)을 읽을 수 없음");
    outside = outside.filter((pid) => !isInProcessTree(pid, rootPid, parents));
  }
  if (outside.length > 0) {
    const holder = describePortHolder(port);
    return fail("CDP_PORT_NOT_OURS", [
      `포트 ${port}의 LISTEN 프로세스(pid ${outside.join(", ")})가 이번 실행의 프로세스 트리(루트 pid ${rootPid})에 속하지 않습니다.`,
      "시작 성공으로 처리하지 않습니다. 다른 프로세스가 포트를 점유하고 있어 수집을 계속하면 다른 세션을 읽게 됩니다.",
      ...(holder ? [`점유 프로세스: ${holder}`] : []),
      `해결 방법: 포트 ${port}를 점유한 프로세스를 종료하고 다시 실행하거나 다른 포트를 사용하세요.`,
    ]);
  }

  const marker = `--remote-debugging-port=${port}`;
  let sawCommandLine = false;
  for (const pid of listeners) {
    const cmdline = processCommandLine(pid);
    if (cmdline === null) continue;
    sawCommandLine = true;
    if (commandLineHasArgument(cmdline, marker)) return { ok: true, pids: listeners, pid };
  }
  if (!sawCommandLine) return unverifiable("점유 프로세스의 명령행을 읽을 수 없음");
  return fail("CDP_OWNER_NOT_LAUNCHED_INSTANCE", [
    `포트 ${port}의 LISTEN 프로세스(pid ${listeners.join(", ")})는 이번 실행의 프로세스 트리에 있지만 ${marker} 인수를 가진 프로세스가 없습니다.`,
    "시작 성공으로 처리하지 않습니다. 이번에 실행한 Chrome이 아니라 같은 트리에서 이 포트를 점유한 다른 프로세스가 응답했습니다.",
    `해결 방법: 다른 프로세스가 포트 ${port}를 점유하지 않는지 확인하거나 다른 포트로 다시 실행하세요.`,
  ]);
}

/** spawn한 Chrome의 생존 여부. exitCode/signalCode를 우선하고 kill(pid,0)을 대안으로 쓴다. */
function isChildAlive(child) {
  if (!child || !child.pid) return false;
  if (child.exitCode !== null || child.signalCode !== null) return false;
  try {
    process.kill(child.pid, 0);
    return true;
  } catch {
    return false;
  }
}

function isPidAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

/** 이번 spawn으로 시작한 트리만 정리한다. 전역 killChrome으로 사용자의 다른 창까지 종료하지 않는다. */
function terminateLaunchTree(rootPid) {
  if (!Number.isInteger(rootPid) || rootPid <= 0) return;
  if (PLATFORM === "win32") {
    try {
      execSync(`taskkill /F /T /PID ${rootPid}`, { stdio: "ignore" });
    } catch {}
    return;
  }

  const parents = listProcessParents();
  const tree = [];
  if (parents) {
    for (const pid of parents.keys()) {
      if (pid !== process.pid && isInProcessTree(pid, rootPid, parents)) tree.push(pid);
    }
  }
  if (!tree.includes(rootPid)) tree.push(rootPid);

  // 자손을 먼저, launcher를 마지막에 종료한다. 부모가 먼저 죽어 분리된 수신자의 부모가 바뀌면 소유권을 놓칠 수 있다.
  const depth = (pid) => {
    let current = pid;
    for (let hops = 0; hops < 64; hops++) {
      if (current === rootPid) return hops;
      const next = parents?.get(current);
      if (!next || next === current) return -1;
      current = next;
    }
    return -1;
  };
  tree.sort((left, right) => depth(right) - depth(left));
  for (const pid of tree) {
    try { process.kill(pid, "SIGTERM"); } catch {}
  }
  sleepSync(200);
  for (const pid of tree) {
    if (!isPidAlive(pid)) continue;
    try { process.kill(pid, "SIGKILL"); } catch {}
  }
}

/** 파일 복사. ENOENT는 무시하고 다른 오류는 사용자 진단을 위해 경고를 한 번 출력한다. */
function copyFileSafe(src, dest) {
  try {
    fs.copyFileSync(src, dest);
    return true;
  } catch (e) {
    if (e.code !== "ENOENT") {
      warn(`복사 실패: ${src} -> ${dest} (${e.code || e.message})`);
    }
    return false;
  }
}

/** 디렉터리를 재귀 복사한다. */
function copyDirRecursive(src, dest) {
  fs.cpSync(src, dest, { recursive: true, force: true });
}

/** 디렉터리를 재귀 삭제한다. */
function rmDirSafe(dir) {
  fs.rmSync(dir, { recursive: true, force: true });
}

/**
 * 기존 debugProfile에 증분 반영할 때 로그인 상태 관련 파일을 갱신한다.
 * Chrome의 Default/Cookies와 Default/Network/Cookies를 모두 시도하며
 * -journal / -wal / -shm 보조 파일과 Google 계정 로그인 데이터도 포함한다.
 */
function refreshAuthFiles(srcDefault, destDefault) {
  const targets = [
    "Cookies", "Cookies-journal",
    "Login Data", "Login Data-journal",
    "Login Data For Account", "Login Data For Account-journal",
    "Web Data", "Web Data-journal",
    path.join("Network", "Cookies"),
    path.join("Network", "Cookies-journal"),
  ];
  let copied = 0;
  for (const rel of targets) {
    const src = path.join(srcDefault, rel);
    if (!fs.existsSync(src)) continue;
    const dest = path.join(destDefault, rel);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    if (copyFileSafe(src, dest)) copied++;
  }
  return copied;
}

/** 이전 충돌로 다음 실행이 실패하지 않도록 Chrome singleton 잠금을 정리한다. */
function clearSingletonLocks(profileDir) {
  const names = ["SingletonLock", "SingletonCookie", "SingletonSocket"];
  for (const n of names) {
    try { fs.unlinkSync(path.join(profileDir, n)); } catch {}
  }
}

/** Chrome PID 목록이 빌 때까지 기다린다. */
function waitForChromeExit(config, maxMs = 8000, stepMs = 500) {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    if (config.listChromePids().length === 0) return true;
    sleepSync(stepMs);
  }
  return false;
}

/** TTY 대화형 확인 질문. */
function promptYesNo(question) {
  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(question, (answer) => {
      rl.close();
      resolve(/^y(es)?$/i.test((answer || "").trim()));
    });
  });
}

// ---------------------------------------------------------------------------
// detect-only 모드
// ---------------------------------------------------------------------------

async function runDetectOnly(config) {
  const version = await probeCDP(CDP_PORT);
  if (version) {
    log("CDP_STATUS=ready");
    log(`CDP_URL=http://127.0.0.1:${CDP_PORT}/json/version`);
    // JSON에서 브라우저 버전 추출을 시도하며 오류를 허용한다.
    try {
      const obj = JSON.parse(version);
      if (obj.Browser) log(`BROWSER=${obj.Browser}`);
    } catch {}
    process.exit(0);
  }
  log("CDP_STATUS=needs-setup");
  const pids = config.listChromePids();
  if (pids.length > 0) {
    log("CHROME_RUNNING=yes");
    log(`CHROME_PID_COUNT=${pids.length}`);
  } else {
    log("CHROME_RUNNING=no");
  }
  process.exit(0);
}

// ---------------------------------------------------------------------------
// 동의 절차: true는 계속, false는 사용자 거부.
// ---------------------------------------------------------------------------

async function ensureConsentToKill(pids) {
  if (pids.length === 0) return true;
  if (ARGS.flags.yes) return true;

  // 비 TTY: 알리지 않은 프로세스 종료를 거부하고 호출자(Claude / 상위 스크립트)에 명확한 신호를 준다.
  if (!process.stdin.isTTY) {
    err(`NEEDS_CONSENT: ${pids.length} running Chrome process(es) will be killed.`);
    err(`Pass --yes to confirm (after asking the user), or stop Chrome manually first.`);
    process.exit(3);
  }

  // TTY: 대화형으로 확인한다.
  warn(`실행 중인 Chrome 프로세스 ${pids.length}개를 찾았습니다.`);
  warn("계속하면 이 프로세스들을 종료합니다. 일반 Chrome에서 저장하지 않은 작업이 사라질 수 있습니다.");
  return promptYesNo("계속하시겠습니까? [y/N] ");
}

// ---------------------------------------------------------------------------
// 주 처리 흐름
// ---------------------------------------------------------------------------

async function main() {
  const config = getConfig();
  const debugProfile = path.join(os.homedir(), "chrome-debug-profile");

  // 1) Chrome 실행 경로 탐지(detect-only에도 profileDir이 필요함).
  const chromePath = config.findChrome();

  // detect-only: 어떤 상태도 변경하지 않는다.
  if (ARGS.flags.detectOnly) {
    if (!chromePath) {
      log("CDP_STATUS=needs-setup");
      log("CHROME_INSTALLED=no");
      process.exit(0);
    }
    return runDetectOnly(config);
  }

  log("=== CDP Chrome 환경 준비 ===");
  log(`플랫폼: ${PLATFORM} | CDP 포트: ${CDP_PORT} | profile: ${ARGS.profile}`);

  if (!chromePath) {
    err("Google Chrome을 찾을 수 없습니다. 설치 여부를 확인하세요.");
    err(`검색 경로: ${JSON.stringify(config.chromePaths, null, 2)}`);
    process.exit(1);
  }
  log(`Chrome 경로: ${chromePath}`);

  // 2) dry-run: 기존 CDP 재사용을 포함한 모든 부수 효과보다 먼저 계획을 출력해 실제 실행 단계를 보여 준다.
  const defaultProfile = path.join(config.profileDir, ARGS.profile);
  const hasProfile = fs.existsSync(defaultProfile);

  if (ARGS.flags.dryRun) {
    const cdpAlive = !!(await probeCDP(CDP_PORT));
    const tcpOccupied = await probeTcp(CDP_PORT);
    // --reset / 명시적 --profile은 재사용을 건너뛰므로(아래 3단계) dry-run도 이를 정확히 알린다.
    const willReuse = cdpAlive && !ARGS.flags.reset && !ARGS.profileExplicit;
    const cdpNote = !tcpOccupied
      ? "수신 중이 아님"
      : !cdpAlive
        ? "TCP 수신 중이지만 정상 CDP가 아님(실행 시 프로필을 변경하기 전에 중단)"
      : willReuse
        ? "준비됨(실행 시 바로 재사용)"
        : "준비됨(--reset/--profile이 지정되어 실행 시 재사용하지 않고 다시 생성)";
    log(`Chrome profile: ${defaultProfile} (${hasProfile ? "있음" : "없음"})`);
    log(`CDP 포트 ${CDP_PORT}: ${cdpNote}`);
    const runningPids = config.listChromePids();
    log(`Chrome 프로세스 ${runningPids.length}개 감지`);
    log("\n--- dry-run 모드: 실행 없이 작업 내용만 출력 ---");
    if (willReuse) {
      log("0. CDP 준비 완료. 실행 시 바로 재사용하고 코드 0으로 종료(아래 단계는 참고용)");
    } else if (cdpAlive) {
      log("0. CDP 준비 완료. --reset/--profile이 지정되어 아래 단계에 따라 다시 생성");
    }
    // 실제 실행 순서대로 동적 번호를 부여한다. 프로세스 종료, 빈 포트 확인, 프로필 디렉터리 변경 순이다.
    let stepNo = 0;
    const step = (msg) => log(`${++stepNo}. ${msg}`);
    if (runningPids.length > 0) {
      step(`${ARGS.flags.yes ? "(동의함)" : "동의를 받은 뒤 "}Chrome 프로세스 ${runningPids.length}개 종료`);
    } else {
      step("Chrome 프로세스가 없어 종료할 필요 없음");
    }
    step(`TCP로 포트 ${CDP_PORT} 해제 확인(수신 중인 프로세스가 있으면 프로필 삭제와 실행을 하지 않고 중단)`);
    if (ARGS.flags.reset) step(`삭제: ${debugProfile}`);
    if (hasProfile) {
      step(`프로필 복사: ${defaultProfile} -> ${debugProfile}/Default`);
    } else {
      step("⚠️ 사용자 프로필이 없어 빈 프로필로 실행");
    }
    step("SingletonLock / SingletonCookie / SingletonSocket 정리");
    step("Chrome 실행(--remote-allow-origins=*, --no-first-run 등 포함)");
    step(
      `검증: http://127.0.0.1:${CDP_PORT}/json/version 응답이 이번에 실행한 인스턴스에서 왔는지 확인` +
        "(인스턴스 식별값 조회·변경 확인 + 프로세스 실행 중 + 포트의 LISTEN 프로세스가 이 트리에 포함)"
    );
    ok("dry-run 완료.");
    process.exit(0);
  }

  // 3) CDP가 준비되었으면 재사용하고 바로 종료한다.
  //    다만 --reset / 명시적 --profile은 디버그 프로필 재생성을 뜻한다. 문서는 로그인 만료 시
  //    --reset을 실행하게 하며 그때도 CDP는 살아 있다(해당 세션에서 만료를 발견함). 기존처럼 재사용하면
  //    두 인자를 조용히 무시하면서 exit 0으로 성공을 보고하므로 이 경우 재사용하지 않고 재생성을 진행한다.
  const existing = await probeCDP(CDP_PORT);
  const portWasListening = await probeTcp(CDP_PORT);
  if (existing) {
    if (!ARGS.flags.reset && !ARGS.profileExplicit) {
      ok("CDP 준비 완료. 기존 Chrome을 재사용합니다.");
      log(existing.split("\n").slice(0, 5).join("\n"));
      process.exit(0);
    }
    const requested = ARGS.flags.reset ? "--reset" : `--profile ${ARGS.profile}`;
    warn(`CDP 포트 ${CDP_PORT} 수신 중이지만 ${requested} 인수가 지정되어 재사용하지 않습니다. 기존 Chrome을 종료하고 디버그 프로필을 다시 생성합니다.`);
  }
  // 재생성 전 인스턴스 식별 정보: 10단계에서 단순 응답이 아니라 새 인스턴스의 응답임을 입증하는 데 사용한다.
  const staleIdentity = cdpIdentity(existing);

  if (!hasProfile) {
    err(`Chrome 프로필을 찾을 수 없음: ${defaultProfile}`);
    err("Google Chrome을 설치해 한 번 이상 사용했는지 확인하거나 --profile <name>으로 다른 프로필을 지정하세요.");
    process.exit(1);
  }

  // 4) 동의 절차: 종료할 Chrome 프로세스가 있으면 먼저 동의를 구한다.
  const runningPids = config.listChromePids();
  const consented = await ensureConsentToKill(runningPids);
  if (!consented) {
    err("사용자가 거부하여 중단했습니다.");
    process.exit(2);
  }

  // 5) 기존 Chrome 프로세스를 종료하고 종료를 기다린다.
  if (runningPids.length > 0) {
    log(`Chrome 프로세스 ${runningPids.length}개 종료 중...`);
    config.killChrome();
    if (!waitForChromeExit(config, 6000)) {
      warn("첫 종료 요청 후에도 Chrome 프로세스가 남아 있어 다시 시도합니다...");
      config.killChrome();
      waitForChromeExit(config, 4000);
    }
    const remain = config.listChromePids();
    if (remain.length > 0) {
      err(`Chrome 프로세스 ${remain.length}개가 종료되지 않아 중단했습니다.`);
      err("디버그 프로필을 삭제하거나 변경하지 않았고 새 Chrome도 실행하지 않았습니다. 기존 상태를 유지합니다.");
      process.exit(1);
    } else {
      ok("Chrome이 종료되었습니다.");
    }
  }

  // 5.5) 필수 관문: 포트가 실제로 비어야 프로필 디렉터리 변경과 새 인스턴스 실행을 허용한다.
  //      프로필 삭제 전에 관문을 두는 순서는 의도적이다. 이전 인스턴스가 살아 있는데 진행하면 최악의 경우
  //      실행 중인 Chrome 프로필을 삭제하고, 새 프로세스는 점유된 포트 때문에 실행하지 못하며,
  //      10단계 probeCDP에 이전 엔드포인트가 응답해 exit 0으로 재생성 성공을 보고한다. 호출자는 새 브라우저를 얻었다고
  //      새 브라우저를 열면 이후 수집은 매번 이전 세션이나 다른 사람의 세션을 읽게 된다. 여기서는 반드시 오류로 중단해야 한다.
  //      /json/version의 정상 여부와 무관하게 실행한다. HTTP 500도 포트를 점유할 수 있다.
  // 프로세스를 종료한 경우만 유예 시간을 준다. 식별된 Chrome이 없으면 점유자가 저절로 종료하지 않으므로 빠르게 확인 후 실패한다.
  const graceMs = runningPids.length > 0 ? 8000 : 1000;
  if (!(await waitForPortFree(CDP_PORT, graceMs))) {
    const remain = config.listChromePids();
    err(
      existing
        ? `CDP 포트 ${CDP_PORT} 의 기존 인스턴스가 계속 응답하여 중단했습니다.`
        : `CDP 포트 ${CDP_PORT} 가 여전히 점유되어 해제되지 않았으므로 중단했습니다.`
    );
    if (remain.length > 0) {
      err(`원인: Chrome 프로세스 ${remain.length}개가 종료되지 않았습니다(종료 요청 무효. 권한 부족 또는 프로세스 응답 정지 가능).`);
    } else if (runningPids.length === 0) {
      err("원인: 식별할 수 없는 프로세스가 포트를 점유했습니다. Chrome 프로세스를 찾지 못해 스크립트에서 종료할 수 없습니다.");
    } else {
      err("원인: Chrome은 종료되었지만 다른 프로세스가 이 포트를 점유하고 있습니다.");
    }
    const holder = describePortHolder(CDP_PORT);
    if (holder) err(`점유 프로세스: ${holder}`);
    err("디버그 프로필을 삭제하거나 변경하지 않았고 새 Chrome도 실행하지 않았습니다. 기존 상태를 유지합니다.");
    err(`해결 방법: 포트 ${CDP_PORT}를 점유한 프로세스를 직접 종료하고 다시 실행하거나 다른 포트를 사용하세요(node setup-cdp-chrome.js <다른 포트> ...).`);
    process.exit(1);
  }
  if (portWasListening) {
    ok(`CDP 포트 ${CDP_PORT} 해제 완료.`);
  }

  // 6) --reset: 디버그 프로필을 비운다.
  if (ARGS.flags.reset) {
    log(`디버그 프로필 삭제 중: ${debugProfile}`);
    rmDirSafe(debugProfile);
  }

  // 7) 프로필 복사 / 갱신(Chrome이 종료되어 SQLite 일관성이 유지됨).
  const debugDefault = path.join(debugProfile, "Default");
  if (!fs.existsSync(debugDefault)) {
    log("Chrome 프로필을 디버그 폴더로 복사하는 중...");
    fs.mkdirSync(debugProfile, { recursive: true });
    try { fs.chmodSync(debugProfile, 0o700); } catch {}
    copyDirRecursive(defaultProfile, debugDefault);
    ok(`프로필 복사 완료: ${debugProfile}`);
  } else {
    log("디버그 프로필이 있어 로그인 상태 관련 파일을 갱신합니다...");
    try { fs.chmodSync(debugProfile, 0o700); } catch {}
    const n = refreshAuthFiles(defaultProfile, debugDefault);
    ok(`로그인 상태 파일 ${n}개 갱신 완료`);
  }

  // 8) singleton 잠금을 정리한다.
  clearSingletonLocks(debugProfile);

  // 9) CDP 모드로 Chrome을 시작한다.
  log(`CDP 모드로 Chrome 실행 중(포트 ${CDP_PORT})...`);
  const chromeArgs = [
    `--remote-debugging-port=${CDP_PORT}`,
    `--user-data-dir=${debugProfile}`,
    "--remote-allow-origins=*",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-features=ChromeWhatsNewUI",
  ];
  const child = spawn(chromePath, chromeArgs, { detached: true, stdio: "ignore" });
  const childPid = child.pid;
  let spawnError = null;
  child.on("error", (e) => { spawnError = e; });
  child.unref();

  /** 시작 후 검증 실패: 방금 시작한 프로세스만 정리한다. 포트 소유자가 우리 것이 아니라면 다른 Chrome까지 종료하면 안 된다. */
  function abortAfterLaunch(reasons) {
    for (const line of reasons) err(line);
    err("방금 실행한 Chrome 프로세스를 정리하는 중...");
    terminateLaunchTree(childPid);
    process.exit(1);
  }

  // 10) 실행을 기다리고 검증한다. 응답만으로 성공은 아니다. 종료되지 않은 이전 인스턴스이거나 다른 프로세스가
  //     우연히 포트를 점유했을 수 있다. 다음 네 조건을 모두 충족해야 한다.
  //     ① 새 엔드포인트의 browser GUID를 얻는다. 얻지 못하면 비교 불가이며 계약상 같음이나 다름으로 취급할 수 없다.
  //     ② GUID가 재생성 전과 다르다(5.5단계에서 이전 엔드포인트 소멸도 확인함).
  //     ③ 방금 spawn한 프로세스가 살아 있다. 죽었다면 포트 응답자는 이번 인스턴스가 아니다.
  //     ④ LISTEN 소유자가 spawn한 프로세스 트리에 실제로 있으며 이번 실행의
  //        --remote-debugging-port를 갖는다. 앞의 세 조건은 간접 증거다. 이전 엔드포인트 소멸, 식별 정보 변경,
  //        launcher 생존만으로 포트 소유권을 입증할 수 없다. ④만이 포트와 프로세스의 관계를 실제로 확인한다.
  log("Chrome 시작 대기 중...");
  let identityMisses = 0;
  for (let i = 1; i <= 15; i++) {
    sleepSync(2000);
    if (spawnError) {
      abortAfterLaunch([`Chrome 시작 실패: ${spawnError.message}`]);
    }
    const version = await probeCDP(CDP_PORT);
    if (version) {
      const identity = cdpIdentity(version);
      if (identity === null) {
        // 시작 직후에는 HTTP만 먼저 응답할 수 있어 두 차례 유예한다. 이후에도 얻지 못하면 실패한다.
        if (++identityMisses < 3) {
          log(`   포트에서 응답했지만 인스턴스 식별값을 조회할 수 없어 재시도 ${identityMisses}/3...`);
          continue;
        }
        abortAfterLaunch([
          `CDP_IDENTITY_UNVERIFIABLE: 포트 ${CDP_PORT}가 HTTP로 응답했지만 /json/version에서 인스턴스 식별값(webSocketDebuggerUrl)을 조회할 수 없습니다.`,
          "시작 성공으로 처리하지 않습니다. 식별값이 없어 새 인스턴스인지 확인할 수 없습니다. 규약에 따라 동일·상이 여부가 아닌 미확인 상태로 처리합니다.",
          `해결 방법: 포트 ${CDP_PORT}의 서비스가 Chrome CDP 엔드포인트인지 확인하거나 다른 포트로 다시 실행하세요.`,
        ]);
      }
      if (staleIdentity && identity === staleIdentity) {
        abortAfterLaunch([
          `포트 ${CDP_PORT}에서 새 Chrome이 아닌 재생성 전 인스턴스(${identity})가 응답했습니다.`,
          "시작 성공으로 처리하지 않습니다. 계속 수집하면 이전 세션을 읽게 됩니다.",
        ]);
      }
      if (!isChildAlive(child)) {
        const holder = describePortHolder(CDP_PORT);
        abortAfterLaunch([
          `포트 ${CDP_PORT}에서 CDP 응답이 왔지만 방금 실행한 Chrome(pid ${childPid})이 이미 종료되었습니다.`,
          "시작 성공으로 처리하지 않습니다. 이 엔드포인트는 이번에 실행한 인스턴스에 속하지 않습니다.",
          ...(holder ? [`점유 프로세스: ${holder}`] : []),
          `해결 방법: 다른 프로세스가 포트 ${CDP_PORT}를 점유하지 않는지 확인하거나 다른 포트로 다시 실행하세요.`,
        ]);
      }
      const owner = verifyPortOwnedByLaunch(CDP_PORT, childPid);
      if (!owner.ok) abortAfterLaunch(owner.lines);
      ok(`Chrome CDP 모드 시작 성공(포트 ${CDP_PORT})`);
      log(version.split("\n").slice(0, 5).join("\n"));
      process.exit(0);
    }
    log(`   시도 ${i}/15...`);
  }

  // 11) 실패 정리: 방금 시작한 고아 Chrome을 종료한다.
  err("30초 안에 Chrome CDP 환경을 시작하지 못했습니다.");
  err("방금 실행한 Chrome 프로세스를 정리하는 중...");
  terminateLaunchTree(childPid);
  err("가능한 원인:");
  err("  - Chrome이 --remote-debugging-port를 지원하지 않음");
  err(`  - 다른 프로세스가 포트 ${CDP_PORT}를 점유 중`);
  err("  - 디버그 프로필 폴더 손상(--reset 시도)");
  process.exit(1);
}

main().catch((e) => {
  err(`시작 실패: ${e.message}`);
  process.exit(1);
});
