# Agent Note: 본문 차단 안내에 0으로 채운 상세 개요 파일명 표시, shell 변수 경로는 파싱 실패로 정확히 안내

Status: implemented
Date: 2026-09-24
Related: [2026-07-15-hook-guard-failure-semantics](../architecture/2026-07-15-hook-guard-failure-semantics.md)

## Problem

본문 쓰기 전 개요 검사가 차단하면 모델은 안내에 따라 파일을 보완한다. 안내 두 곳이 모델을 잘못 이끌었다.

- 상세 개요가 없을 때 `细纲_第{章号}章.md`(예: `细纲_第1章.md`)를 안내했지만 표준 이름과 demo는 0을 채운 `细纲_第001章.md`였다. 검사는 0 채움 차이를 허용하지만 안내대로 생성한 파일명은 다른 상세 개요와 달라진다.
- 공유 코어 `extractProseTargets`는 shell 명령에서 쓰기 대상을 추출할 때 경로를 리터럴로 읽는다. `PROJ=...; cat > "$PROJ/正文/第001章_x.md"`는 `{项目根}/$PROJ/正文/...`로 합쳐져 작품 디렉터리를 찾지 못한다. 그 결과 ‘상세 개요 누락($PROJ/大纲/细纲_第1章.md)’으로 보고하지만 실제 개요는 존재한다. 모델은 불필요한 개요를 추가하거나 잘못된 위치에 `$PROJ` 디렉터리를 만든다.

## Decision

- JS 공유 코어 `story_hook_core.js`의 `proseBlockReason`, Codex `story_codex_hook.py`의 `prose_block_reason`, Claude `guard-outline-before-prose.sh`의 개요 누락 안내 모두 세 자리 0 채움 파일명을 제시한다(장 번호 1000 이상은 그대로). JS 코어 배포 사본 세 개는 `sync-shared-assets.py`로 동기화한다.
- 장편 본문 대상의 프로젝트 루트 아래 상대 경로에 확장되지 않은 shell 변수나 명령 치환(`$VAR` / `${VAR}` / `$(cmd)`)이 있고 리터럴로 합친 작품 디렉터리가 없으면 계속 차단한다(fail closed). 안내는 ‘쓰기 경로에 확장되지 않은 shell 변수가 있어 검사가 해당 상세 개요를 확인할 수 없다. 리터럴 프로젝트 경로로 다시 쓰라’는 내용으로 바꾼다. JS와 Python 문구는 글자 단위로 같다. Claude bash 검사는 Bash 명령에 원래 공유 코어를 호출하며 Write/Edit의 직접 파일 경로에는 shell 변수가 없으므로 따로 수정하지 않는다.
- 테스트: `test-prose-net-parity.sh` Part E에 `$PROJ/正文/第001章_x.md`, `$(pwd)/book/正文/第001章_y.md`, 0 채움 파일명 단언을 추가해 Python과 JS를 비교한다. `test-codex-hooks.sh`, `test-opencode-plugin.mjs`, `check-story-setup-deployment.sh`에 명령 단위 사례를 각각 하나씩 추가한다.

## Alternatives considered

- **검사에서 같은 명령 안의 변수 대입(`PROJ=...;`)을 파싱해 확장**: 상세 개요의 실제 존재 여부를 정확히 판단해 정상 쓰기 명령을 다시 작성하지 않아도 된다는 점이 가장 큰 장점이다. 그러나 대입은 `export`, `$(...)`, 이전 명령, 환경에서 올 수 있어 정적 확장은 일부만 다루고 잘못된 값으로 허용할 위험도 있다. 모델이 리터럴 경로를 쓰게 하는 것이 더 단순하고 신뢰할 수 있다.
- **shell 변수가 있으면 바로 허용**: 정상 쓰기를 잘못 차단하지 않는다는 장점이 있다. 그러나 판단할 수 없는 본문 쓰기는 일관되게 fail closed로 처리해 왔다(Related 참조). 허용하면 검사 우회를 위한 고정된 표현이 생기므로 채택하지 않는다.

## Consequences

- **이점**: 모델이 차단 안내에 따라 생성하는 개요 이름이 표준과 일치한다. shell 변수 경로 차단이 존재하지 않는 누락을 보완하라고 잘못 안내하지 않는다.
- **비용**: 변수가 포함된 정상 쓰기도 계속 차단되어 모델이 리터럴 경로로 바꾸고 다시 실행해야 한다.
- **알려진 한계**: 장편 `正文/第N章*.md` 대상만 처리한다. 파일명 자체에 변수(예: `第${N}章.md`)가 있으면 장 번호를 파싱할 수 없으며 기존 동작을 유지한다.
