# Agent Note: OpenCode 어댑터는 2.x만 지원하고 배포 전에 버전 검사로 차단

Status: implemented

Related: [2026-09-24-opencode-version-gate-fail-closed](../bug-fix/2026-09-24-opencode-version-gate-fail-closed.md)(‘버전을 확정할 수 없어도 배포 계속’은 이후 배포 중단으로 뒤집힘), [2026-10-29-opencode-2-2-call-gated-tools](../testing/2026-10-29-opencode-2-2-call-gated-tools.md)(2.2부터 `skill`·Code Mode 도구는 실제 호출로 검증)

## Problem

OpenCode 2.0(2026-09-11부터, npm 패키지 `@opencode/cli`로 1.18.x에 머문 `opencode-ai`와 별도 배포)은 서버를 다시 구현했다. 우리 OpenCode 어댑터는 1.x 기준이며 2.0.15에서 다음을 확인했다.

- 본문 쓰기 검사 플러그인의 default export는 1.x hook-map 함수지만 2.x loader는 `{ id, setup }` / `{ id, effect }`만 받는다. `PluginModule.LoadError` 후 WARN 한 줄만 기록하고 서비스는 계속 실행되어 개요 검사와 집필 후 보완 검사가 세션 내내 조용히 작동하지 않는다(#440/#441).
- `opencode.json`의 `plugin` 배열은 단일 파일 경로였으나 2.x는 디렉터리만 허용하여 항목을 버린다(`configured plugin path must be a directory`).
- 도구명·인자가 바뀌었다. `bash`→`shell`, `apply_patch`→`patch`, `write`/`edit`의 `filePath`→`path`.
- 2.x는 기본적으로 백그라운드 서비스 프로세스 하나가 여러 프로젝트를 담당하여 플러그인의 `process.cwd()`가 더 이상 사용자 프로젝트가 아니다. 1.x의 프로젝트 루트 탐색을 그대로 쓰면 상세 개요가 있는 정상 본문 쓰기를 잘못 차단하고 집필 후 검사도 다른 위치를 스캔한다.
- `opencode debug skill`과 `debug agent --tool`이 삭제되어 CI의 e2e·런타임 권한 테스트가 2.x에서 실행되지 않는다. `opencode models --verbose`도 사라졌는데 story-setup의 에이전트 모델 등급 분류는 이 명령으로 비용을 조회했다.

CI가 계속 통과한 이유는 `cli-compat`가 늘 1.x인 `opencode-ai@latest`를 설치했기 때문이다. e2e도 설정에 플러그인 항목이 있는지만 확인하고 실제 로드·훅 작동 여부는 검사하지 않았다.

## Decision

- OpenCode 2.x만 지원하며 저장소에 1.x 분기 코드를 남기지 않는다.
- `skills/story-setup/references/opencode/plugin.ts`의 기본 내보내기는 `{ id: "oh-story.story-hooks", setup(ctx) }`다. `ctx.tool.hook("execute.before")`는 `write`/`edit`의 `path`, `patch`의 `patchText`, `shell`의 `command` + `workdir`에서 본문 대상을 추출하고 차단되면 예외를 던진다. 런타임이 이를 도구 결과로 모델에 돌려준다. `ctx.tool.hook("execute.after")`는 `status: completed`일 때 보완 검사 결과를 `result.content`에 덧붙인다. `ctx.session.hook("compaction")`은 요약 요청의 `system`에 집필 컨텍스트 위치를 추가한다. 프로젝트 루트는 `ctx.location.directory`의 git toplevel이며 상대 경로는 세션 디렉터리 또는 shell의 `workdir`를 기준으로 한다. 공유 코어 `story_hook_core.js`는 변경하지 않았다.
- 플러그인은 2.x의 `.opencode/plugins/*.ts` 자동 검색으로 로드하며 `opencode.json.patch`는 삭제한다. story-setup의 ‘OpenCode 배포 전제’에서는 기존 `opencode.json(c)`의 `plugin`/`plugins` 배열에서 story-hooks.ts를 가리키는 옛 항목을 제거한다. `lib/` 하위 디렉터리는 `index.*` / `server.*` / `tui.*` / `rpc.*`를 넣지 않으면 플러그인 패키지로 취급되지 않는다.
- `scripts/sync-opencode.py`는 기본 `permissions:` 규칙 목록을 생성한다(`action`/`resource`/`effect`, Bash→`shell`, 목록 순서가 우선순위).
- story-setup은 OpenCode 배포 전 `opencode --version`을 실행한다. 주 버전이 2 미만이면 배포를 중단하고 2.x 설치 명령을 안내한다. 명령을 사용할 수 없으면 계속하되 설치 보고서 첫 줄에 버전 미확인을 알린다. 모델 등급 분류는 `opencode api model.list`(`cost[]`/`limit.context`가 있는 JSON)를 사용하고 실패하면 `opencode models`로 대체한다. `plugin.list`에서 `oh-story.story-hooks`가 `active`인지 검증하는 항목을 추가한다.
- CI `cli-compat.yml`은 `@opencode/cli@latest`를 설치한다. `scripts/test-opencode-cli-e2e.sh`는 먼저 프로젝트 밖에서 백그라운드 서비스를 시작하고 스킬 13개(`GET /api/skill`의 `path`), command 13개, 기본 권한 에이전트 7개, `plugin.list`의 플러그인 `active` 상태를 단언한다. 이어 `scripts/opencode-mock-llm.mjs`로 실제 `opencode run`을 구동한다. 상세 개요 없는 write/shell/patch가 차단되고 모델이 이유를 받는지, 개요가 있는 write는 저장되고 모델이 보완 검사 결과를 받는지, `session.compact` 요약 요청에 `Writing context: book/追踪/上下文.md`가 포함되는지 확인한다.
- `scripts/test-agent-permissions.py --opencode`는 백그라운드 서비스를 예열한 뒤 에이전트마다 `opencode run --agent`를 실행하고 모의 모델이 받은 도구 목록을 런타임 판정으로 삼는다(2.x는 도구 전체를 deny하면 목록에서 제거). 허용한 write/shell이 실제 실행되고 거부한 write가 `No tool named "write"`를 받는지도 검증한다. `check-opencode-adapter.sh`의 정적 판정 행렬은 2.x `whollyDisabled()`를 독립적으로 재현하도록 바꾼다.
- `scripts/test-opencode-plugin.mjs`는 `setup(ctx)`로 훅을 등록하고 프로젝트 밖 cwd에서 `setup`과 훅을 호출하여 `ctx.location` 기준 탐색을 고정한다.
- 2.x 백그라운드 서비스는 기본 고정 포트를 사용한다. 개발 장비에 OpenCode 서비스가 이미 있으면 격리 HOME의 서비스가 시작되지 않고 요청이 계속 재시도된다. e2e·런타임 권한 테스트는 먼저 `opencode service set port`로 격리 HOME에 빈 포트를 지정한다.

출처: #443(#440·#441 수정)

## Alternatives considered

- **한 파일에서 1.x `server()`와 2.x `setup()` 동시 내보내기**: 공식 이전 문서가 이중 내보내기를 안내하므로 현재 기본 설치 경로가 여전히 1.x인 사용자에게 영향이 없다는 장점이 있다. 그러나 유지 관리자가 구코드를 남기지 않겠다고 명시했다. 1.x도 1.18.29부터 객체 형식을 인식하므로 이중 내보내기로 모든 1.x를 지원할 수 없고, 두 훅·도구명·인자 체계를 장기간 병렬 테스트해야 해 채택하지 않는다.
- **에이전트는 1.x `permission:`을 유지하고 2.x legacy 이전에 의존**: 파일 하나를 두 세대가 읽어 변경이 최소다. 그러나 2.x만 지원하면 이는 옛 형식의 잔재이며 상위 프로젝트가 legacy 경로를 계속 유지해야 한다. 기본 `permissions:`는 공식 문서와 같고 생성기에서 한 번 매핑하면 되므로 그 방식을 사용한다.
- **`opencode.json`의 플러그인 등록 유지**: 명시적 선언이 자동 검색보다 눈에 잘 보인다는 장점이 있다. 그러나 2.x는 단일 파일 경로를 버리고 경고한다. 등록하려면 디렉터리형 플러그인 패키지로 바꿔야 하는데 자동 검색보다 구조만 늘고 이점이 없어 채택하지 않는다.
- **버전이 달라도 정상 배포하고 보고서에만 안내**: 다중 호스트 배포를 멈추지 않는다는 장점이 있다. 그러나 1.x의 플러그인 로드 실패는 조용히 발생하고 한 줄 안내는 쉽게 지나치며 본문 검사 부재가 산출물에 직접 영향을 준다. `opencode` 명령을 사용할 수 없어 판정 자체가 불가능할 때만 안내로 대체한다.
- **e2e에 `--standalone` 전용 서버 사용**: 호출마다 독립적이며 백그라운드 서비스 수명 주기를 관리할 필요가 없다. 그러나 콜드 스타트에서는 location의 에이전트·플러그인이 비동기 로드되어 `--standalone` 조회가 빈 목록을 반환하고 `run --agent`는 Agent not found를 보고한다. standalone 서비스의 cwd도 마침 프로젝트이므로 `process.cwd()` 회귀를 검출할 수 없다.

## Consequences

- **이점**: 2.x 사용자는 개요 검사·집필 후 보완 검사·압축 전 컨텍스트 주입을 다시 사용할 수 있다. CI가 처음으로 실제 OpenCode 런타임의 훅·권한을 검증하며 ‘플러그인이 조용히 로드되지 않음’과 ‘서비스 cwd가 프로젝트가 아님’ 두 회귀 모두 실패 대조군으로 검출됨을 확인했다.
- **비용**: 여전히 1.x인 사용자(`curl opencode.ai/install`, `npm i -g opencode-ai` 모두 당시 1.x 설치)는 2.x로 업그레이드해야 이 어댑터를 쓸 수 있으며 story-setup이 차단·안내한다. 기존 배포 프로젝트는 플러그인·에이전트 교체를 위해 story-setup을 다시 실행해야 한다. `agents_version`은 출시 주기에 따라 다음 출시에서 올리므로 그 전에는 session-start가 안내하지 않는다. cli-compat OpenCode 작업에는 모의 모델과 `opencode run` 십여 회가 추가된다.
- **알려진 한계**: 모의 모델은 훅·권한의 런타임 동작만 검증하고 실제 모델이 올바른 도구를 고르는지는 검증하지 않는다. 훅 예외의 모델 반환, `opencode run`이 `$PWD`로 세션 디렉터리를 정하는 동작, location 리소스의 비동기 준비는 문서 보장이 아니라 2.0.15 실측 동작이며 e2e 단언으로 보호한다.

## 검증

- OpenCode 2.0.15의 `bash scripts/test-opencode-cli-e2e.sh`가 통과했다. 플러그인을 main의 1.x판으로 되돌리면 `story-hooks plugin missing from plugin.list`, `ctx.location.directory`를 `process.cwd()`로 바꾸면 `outlined write was blocked or not written`이 발생했다.
- `python3 scripts/test-agent-permissions.py --opencode <opencode 2.0.15>`가 통과하고 에이전트 7개의 도구 목록이 능력 선언과 일치했다.
- `node scripts/test-opencode-plugin.mjs`가 통과했으며 `process.cwd()` 변형은 실패했다.
- `bash scripts/check-opencode-adapter.sh`가 통과했다.
- 다른 OpenCode 서비스가 기본 포트를 사용 중이면 포트 지정 전에는 e2e가 멈췄고 지정 후에는 e2e·권한 테스트가 모두 통과했다.
- 실제 모델(MiMo `xiaomi/mimo-v2.6-pro`, OpenCode 2.0.15, `opencode run --auto`)로 상황별 시험을 수행해 모두 기대와 일치했다. 새 프로젝트의 story-setup 배포는 `opencode.json`을 쓰지 않고 플러그인이 `active`였다. 1.x 시절 배포를 다시 실행하면 플러그인이 `failed`에서 `active`로 바뀌고 `opencode.json`에서는 story-hooks 등록만 삭제하며 사용자 필드와 에이전트 사용자 지정 `model:`은 유지했다. 개요 없는 본문 쓰기가 차단되면 모델이 상세 개요·추적을 보완한 뒤 저장하고 집필 후 검사가 지적한 AI 문장을 수정했다. shell heredoc 본문 쓰기가 차단되었고 `book/` 하위 디렉터리에서 세션을 시작해도 상대 경로 쓰기를 프로젝트 루트 기준으로 판정했다. narrative-writer 하위 에이전트에서도 훅이 작동했으며 단편의 소절 개요 누락도 차단했다. `/story` 명령은 정상 라우팅되었고 실제 compaction 요약은 `book/追踪/上下文.md`를 이어쓰기 진입점으로 제시했다.
