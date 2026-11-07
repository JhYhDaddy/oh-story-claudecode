# Agent Note: 탐지기·순위 조사 런타임·Dashboard 테스트는 계약마다 검사 하나를 두고 음성 예제가 검사 분기에 도달하게 한다

Status: implemented

## Problem

읽기 전용 테스트 감사에서 탐지기, 순위 조사 런타임, Dashboard 세 영역에 같은 문제가 발견되었다. 테스트가 '검사하는 것처럼 보이지만' 변이 후에도 실패하지 않았다.

- 밀도 규칙(미세 동작, 상투적 반응, 추상적 요약, 동작 나열, 상투어, 비유, 설명 사슬, 과도한 압축)의 '따옴표 안에서는 탐지하지 않아야 한다'는 음성 예제는 모두 밀도가 낮아서 통과했다. 밀도 함수의 `stripQuoted(trimmed)`를 `trimmed`로 바꿔도 전부 통과했다. 퇴화 탐지기의 순수 대사 반복 예제는 '我不走。'였는데 반복 탐지 길이 기준보다 짧아 역시 따옴표 제거 동작을 검사하지 못했다.
- 같은 것을 여러 곳에서 중복 검사했다. `test-ai-patterns.sh` / `test-outline-copy.sh`의 탐지기 사본 글자별 비교는 `sync-shared-assets.py check`와 중복되었다. `test-scan-runtime.js`는 글자 단위로 동기화하는 short-scan의 `cdp-utils.js`를 다시 실행했다. `dashboard-bundle-contract.test.mjs`의 manifest 검사는 `check-plugin-packaging.py`와 중복되었다. CI의 'Verify cdp-utils loads'에는 검증문이 없었다.
- `testScraperImports`는 scraper가 '테스트 가능한 helper를 반드시 export할 것'을 요구하여 scraper 네 개가 아무도 require하지 않는 export를 남겨 두게 했다.

## Decision

- 사본의 일치는 `scripts/check-shared-files.sh` 안의 `sync-shared-assets.py check`만 담당한다. 테스트 스크립트는 source 사본의 동작만 검사한다.
- `test-ai-patterns.sh`는 표 기반 테스트에서 밀도 규칙 여덟 개의 양성 예제 원문을 대사 따옴표 안에 넣고 모두 탐지되지 않는지 확인한다. 따옴표 제거를 없애는 변이를 적용하면 여덟 개 모두 실패한다. `test-degeneration.sh`의 순수 대사 반복은 길이 ≥12자인 대사로 바꾼다(바로 이어 두 번, 문서 전체에서 세 번). 인접 반복과 긴 문장 반복 분기를 각각 변이시켜도 실패한다.
- scraper는 부작용 없는 import 검사만 유지하고 export를 요구하지 않는다. ciweimao, jjwxc, dz-browse, fanqie의 테스트 전용 export를 삭제한다.
- Claude 패키징 식별은 `check-plugin-packaging.py`만 담당한다. Dashboard 정적 자원은 `dashboard-server.test.mjs`에서 실제 HTTP 경계로 검증한다. `/`를 가져온 뒤 페이지가 참조하는 자원을 하나씩 요청한다.
- CI의 sleep 검사는 `sleep(100)`이 최소 90ms 동안 대기시키는지 확인한다. 검증문 없는 cdp-utils 로드 단계는 삭제한다. 두 환경 모두 이미 `test-scan-runtime.js`를 실행한다.

## Alternatives considered

- **이중 안전장치로 테스트 안에 사본 글자별 비교를 유지한다** — 탐지기 테스트 하나만 실행해도 사본 불일치를 찾을 수 있다는 장점이 있다. 채택하지 않았다. CI는 모든 플랫폼에서 `check-shared-files.sh`를 실행하며 그 오류 메시지가 그룹명과 파일을 알려 주므로 더 정확하다. 두 곳에서 비교하면 한 계약을 바꿀 때 두 곳을 고쳐야 할 뿐이다.
- **밀도 규칙마다 따옴표 음성 예제를 따로 추가한다** — 실패 메시지가 개별 규칙에 더 밀접하다는 장점이 있다. 채택하지 않았다. 거의 같은 shell 틀이 여덟 번 반복된다. 표 기반 테스트는 실패 규칙을 한 번에 보고하면서도 메시지에 규칙별로 나열한다.
- **나중의 단위 테스트를 위해 scraper export를 유지한다** — 순수 함수를 export해야 테스트하기 쉽다는 장점이 있다. 채택하지 않았다. 현재 사용하는 곳이 없으며 순위 조사 동작은 `runScraper`가 CLI를 구동하는 회귀 검사로 이미 검증한다. 실제로 필요해지면 같은 변경에서 테스트와 함께 다시 추가한다.

## Consequences

- **이점**: 유지한 모든 음성 예제는 변이 테스트로 실제 실패할 수 있음을 입증했다. 중복 검사를 없애 같은 계약 변경에 한곳만 고치면 된다. scraper 네 개에서 사용하지 않는 export가 사라졌다.
- **비용**: `test-ai-patterns.sh`만 실행하면 탐지기 사본 불일치를 발견하지 못하므로 `check-shared-files.sh`도 실행해야 한다. Dashboard API job은 `.claude-plugin/marketplace.json` 변경으로 더 이상 실행되지 않는다. 패키징 변경은 cross-platform의 패키징 검사만 담당한다.

## 검증

`bash scripts/test-ai-patterns.sh`; `bash scripts/test-degeneration.sh`; `bash scripts/test-outline-copy.sh`; `node scripts/test-scan-runtime.js`; `bash scripts/check-shared-files.sh`; `npm run test:dashboard`; `python3 scripts/check-plugin-packaging.py`.
