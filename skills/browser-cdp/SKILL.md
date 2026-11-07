---
name: browser-cdp
description: "기존 로그인 세션을 재사용하며 CDP(Chrome DevTools Protocol)로 Chrome을 제어할 때 사용합니다. 디버그 모드 실행, URL 열기, 페이지 로드 대기, JavaScript 실행, 스냅샷, 인증 토큰 추출을 다룹니다. 호출 표현: browser automation, CDP, agent-browser, 浏览器操作, 操作浏览器, Chrome CDP, 复用登录态, extract token from browser, 브라우저 조작, 로그인 세션 재사용."
metadata: {"openclaw":{"requires":{"bins":["agent-browser"]},"source":"https://github.com/zenstory-ai/oh-story-claudecode"}}
---
# Browser CDP 조작 도구

CDP(Chrome DevTools Protocol)로 Chrome에 연결해 로그인 세션을 재사용하고 브라우저를 조작합니다.

## 사전 조건

- macOS / Linux / Windows(실험적 지원). Google Chrome을 설치하고 사용한 적이 있어 원본 프로필이 존재해야 합니다.
- Node.js 20+
- `agent-browser` 설치: `npm install -g agent-browser`

> 실행 또는 재구성 중 Chrome 프로세스를 종료해야 한다면 아래 절차에 따라 먼저 동의를 받습니다. 저장하지 않은 탭이나 초안이 사라질 수 있습니다.

---

## 실행 절차(매번 이 순서를 따릅니다)

아래의 `{SKILL_DIR}`는 이 스킬(browser-cdp)의 디렉터리입니다.

**첫 번째: 현재 상태 감지(상태 변경 없음)**

```bash
node {SKILL_DIR}/scripts/setup-cdp-chrome.js 9222 --detect-only
```

출력 예:

```
CDP_STATUS=ready                        # 준비 완료, 바로 재사용 가능
CDP_URL=http://127.0.0.1:9222/json/version
BROWSER=Chrome/148.0.7778.168
```

또는:

```
CDP_STATUS=needs-setup
CHROME_RUNNING=yes                      # 사용자의 Chrome이 실행 중이며, 설정 시 종료됨
CHROME_PID_COUNT=3
```

**두 번째: 감지 결과에 따라 분기**

- `CDP_STATUS=needs-setup`이고 `CHROME_INSTALLED=no` → 로컬에서 Chrome을 찾지 못했습니다. 먼저 설치하고 필요한 사이트에 한 번 로그인하도록 안내합니다. setup은 실행하지 않습니다.
- `CDP_STATUS=ready`이고 이번에는 연결만 필요함 → `agent-browser --cdp 9222 ...`를 바로 사용합니다. **setup을 실행하지 않습니다.**
- `--reset` / `--profile`을 명시적으로 요청함 → ready 상태여도 재구성합니다. 아래의 「Chrome 종료가 필요한 경우」를 따릅니다.
- `CDP_STATUS=needs-setup`이고 `CHROME_RUNNING=no` → 안전하게 실행합니다.
  ```bash
  node {SKILL_DIR}/scripts/setup-cdp-chrome.js 9222 --yes
  ```
- `CDP_STATUS=needs-setup`이고 `CHROME_RUNNING=yes` → 아래의 「Chrome 종료가 필요한 경우」를 따릅니다.

**Chrome 종료가 필요한 경우(동의 절차)**: 실행 중인 Chrome을 종료하는 모든 명령(Chrome 실행 중 설정, `--reset`, 명시적 `--profile`)은 다음 세 단계를 따릅니다.

1. 원래 옵션에 `--dry-run`을 추가해 실행하고 종료될 Chrome 프로세스 수를 확인합니다.
2. Chrome 프로세스 N개가 종료되며 저장하지 않은 탭이나 초안이 사라질 수 있음을 설명하고 계속할지 묻습니다.
3. 사용자가 동의하면 `--dry-run`을 제거하고 `--yes`를 추가해 다시 실행합니다. 거부하면 이번 자동화를 취소합니다.

TTY가 아닌 호출에서 Chrome이 실행 중이고 `--yes`가 없으면 스크립트는 종료 코드 3과 `NEEDS_CONSENT: ...`를 반환하고 중단합니다. 동의를 받은 뒤 다시 실행하며, `--yes`를 자동으로 추가하지 않습니다.

**포트 변경**: 다른 프로그램이 9222를 사용 중이면 다른 포트(예: 9333)를 선택할 수 있습니다. 이후 모든 `agent-browser --cdp` 명령에 같은 포트를 사용하고, 순위 조사 스크립트에는 `--port 9333`, 자료 조사 보조 에이전트에는 `cdp_port: 9333`을 전달합니다.

---

## 실행 스크립트 옵션

| 옵션 | 설명 |
|------|------|
| `--detect-only` | 감지만 수행하고 어떤 상태도 변경하지 않음 |
| `--yes` | 동의를 이미 받았으므로 대화형 확인을 생략 |
| `--reset` | 실행 전 `~/chrome-debug-profile`을 비움(로그인이 만료되었을 때 사용) |
| `--profile <name>` | 원본 프로필 지정(기본값 `Default`, 예: `"Profile 1"`). 명시적으로 전달하면 재구성 |
| `--dry-run` | 실행할 단계를 출력하고 실제로 실행하지 않음 |

종료 코드: `0` 성공 / `1` 일반 오류 / `2` 사용자 거부(TTY) / `3` 동의가 필요하지만 `--yes`가 없음.

---

## 자주 사용하는 작업

### 페이지를 열고 로드 대기

```bash
agent-browser --cdp 9222 open "<URL>"
agent-browser --cdp 9222 wait 3000
```

### 페이지 텍스트 추출

```bash
agent-browser --cdp 9222 eval 'document.body.innerText.substring(0, 8000)'
```

### 인증 토큰 추출

다음 예는 localStorage의 `token` 항목 또는 JavaScript에서 읽을 수 있는 쿠키를 읽습니다. 실제 저장 위치는 사이트별로 확인합니다.

```bash
agent-browser --cdp 9222 eval 'localStorage.getItem("token") || document.cookie'
```

### 복잡한 JS(따옴표 / `$` / 백틱 포함)

셸 이스케이프 오류를 피하려면 base64 또는 표준 입력으로 스크립트를 전달합니다.

```bash
# 1) base64로 감싸기
agent-browser --cdp 9222 eval -b "$(echo -n "document.querySelectorAll('a').length" | base64)"

# 2) heredoc + --stdin
cat <<'EOF' | agent-browser --cdp 9222 eval --stdin
const links = document.querySelectorAll('a');
links.length;
EOF
```

### 페이지 상호작용(snapshot으로 요소 참조 얻기)

```bash
agent-browser --cdp 9222 snapshot -i        # 상호작용 가능한 요소만
agent-browser --cdp 9222 click "<CSS or @e1>"
agent-browser --cdp 9222 type "<sel>" "<text>"
```

---

## 중지 / 정리

- 디버그 Chrome 창을 닫으면 됩니다. 창이 응답하지 않으면 `--user-data-dir`로 디버그 인스턴스의 PID를 확인하고 해당 프로세스만 종료합니다.
  - macOS / Linux: `pgrep -af chrome-debug-profile`
  - Windows(PowerShell): `Get-CimInstance Win32_Process | Where-Object CommandLine -like '*chrome-debug-profile*' | Select-Object ProcessId,CommandLine`. PowerShell이 없는 구형 시스템에서만 `wmic process get ProcessId,CommandLine | findstr chrome-debug-profile`을 사용합니다.
  PID를 확인한 뒤 `kill -9 {PID}` / `taskkill /F /PID {PID}`를 사용합니다. 확인할 수 없다면 중단합니다. **수동 정리 시 Chrome 실행 파일 이름으로 프로세스를 일괄 종료하면 안 됩니다.** 실행 스크립트에는 앞서 설명한 동의 절차를 그대로 적용합니다.
- 로그인 만료: `node {SKILL_DIR}/scripts/setup-cdp-chrome.js 9222 --reset`으로 원본 프로필을 다시 복사합니다. 위의 「Chrome 종료가 필요한 경우」에 따라 먼저 dry-run을 실행하고 동의를 받은 후 `--yes`를 추가합니다.

---

## 긴 명령에 제한 시간 적용

오래 걸리는 CDP 명령을 포그라운드에서 실행할 때 페이지 로드와 일괄 수집에 제한 시간을 설정해 한 번의 호출이 세션을 오래 점유하지 않도록 합니다.

### 제한 시간 래퍼

Windows에서는 PowerShell Job으로 제한 시간을 설정합니다.

```powershell
$job = Start-Job { agent-browser --cdp 9222 eval "window.location.replace('https://www.qidian.com/rank/')" }
Wait-Job $job -Timeout 30 | Out-Null
if ($job.State -eq 'Running') { Stop-Job $job; Write-Output "⏱ CDP 操作超时（30s），请重试或手动打断" }
else { Receive-Job $job }
Remove-Job $job -Force
```

macOS / Linux에서 `timeout`을 사용할 수 있는 경우:

```bash
timeout 30 agent-browser --cdp 9222 eval "window.location.replace('https://www.qidian.com/rank/')" || echo "⏱ CDP 操作超时（30s），请重试或手动打断"
```

예시 코드의 중국어 출력은 “CDP 작업 제한 시간(30초)을 초과했습니다. 다시 시도하거나 수동으로 중단하세요”라는 뜻입니다.

### 알려진 제한

| 상황 | 위험 | 대응 |
|------|------|------|
| 페이지 로드 시간 초과 | eval 명령이 계속 기다리며 반환되지 않음 | 30초 제한을 설정하고 시간 초과 후 재시도 |
| 대량 데이터 수집 | 여러 페이지를 넘기며 대기 시간이 누적됨 | 페이지마다 독립적인 제한 시간을 두고 실패 지점부터 재개 |
| Chrome 프로세스가 멈춤 | CDP 연결이 끊겼지만 프로세스는 종료되지 않음 | 디버그 프로필의 PID를 먼저 확인한 후 해당 디버그 인스턴스만 종료하고 재연결. 일반 Chrome까지 종료하면 안 됨 |
| 네트워크 불안정 | 요청이 제한 시간 없이 멈춤 | 시간 초과 후 자동으로 한 번 재시도 |

계속 멈추면 사용자에게 호스트에서 수동으로 중단하도록 요청합니다(예: OpenCode, Claude Code에서 `ESC`).

---

## 자주 묻는 질문

| 문제 | 해결 방법 |
|------|----------|
| `NEEDS_CONSENT` + 종료 코드 3 | 「Chrome 종료가 필요한 경우」에 따라 먼저 dry-run으로 종료될 프로세스 수를 알리고 동의 후 `--yes`를 추가해 재실행 |
| `CHROME_INSTALLED=no` 또는 원본 프로필 없음 | Chrome을 설치하고 한 번 사용. 다른 프로필이 있다면 `--profile`로 지정(재구성되므로 동의 절차 적용) |
| CDP 포트가 수신 대기하지 않음 | `--detect-only`로 재확인. 사용 중이면 포트를 바꾸고 후속 명령도 함께 변경(「포트 변경」 참조) |
| 페이지가 로그인 페이지로 이동 | `snapshot -i`로 로그인 버튼을 찾아 조작 |
| `eval`이 `null` 반환 | localStorage 키 이름 확인. 따옴표가 포함된 JS는 `eval -b` 또는 `--stdin` 사용 |
| 로그인 만료 | `setup-cdp-chrome.js 9222 --reset`. 동의 절차에 따라 먼저 dry-run을 실행하고 동의 후 `--yes` 추가 |
| Chrome 프로필이 여러 개임 | `--profile "Profile 1"`로 지정. `--profile`을 명시하면 재구성되므로 동의 절차 적용 |
| Chrome 실행 실패(30초 시간 초과) | 포트 충돌 확인. `~/chrome-debug-profile/` 손상 여부 확인. 해결되지 않으면 동의 절차에 따라 `--reset` 시도 |
