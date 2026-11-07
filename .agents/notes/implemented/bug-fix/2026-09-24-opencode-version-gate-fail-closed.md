# Agent Note: OpenCode 버전 검사를 fail-closed로 변경하여 버전을 모르면 배포 중단

Status: implemented
Date: 2026-09-24
Related: [2026-09-23-opencode-v2-only](../architecture/2026-09-23-opencode-v2-only.md)(이 기록은 ‘명령을 사용할 수 없어도 배포를 계속한다’는 기존 결정을 뒤집음)

## Problem

#443은 OpenCode 2.x만 지원한다. story-setup은 배포 전 `opencode --version`을 실행할 수 없거나 버전을 파싱하지 못해도 배포를 계속하고 설치 보고서 첫 줄에 ‘버전을 확인하지 못했다’고만 안내했다. 출시 전 재검토에서 이 분기가 안전하지 않음을 확인했다.

- 1.x는 에이전트의 2.x 기본 `permissions:` 규칙 목록을 인식하지 못하고 알 수 없는 필드를 무시한다. 읽기 전용 에이전트 세 개(`chapter-extractor`, `consistency-checker`, `story-explorer`)가 전체 파일 쓰기와 shell 권한을 받게 된다. 플러그인 로드 실패는 검사기가 없는 문제지만 권한 실패는 읽기 전용 에이전트가 프로젝트를 실제로 고칠 수 있게 한다.
- 1.x를 차단할 때 `.story-deployed`를 어떻게 처리하는지 문서가 설명하지 않았다. OpenCode만 배포하는 프로젝트에서 이 파일을 평소처럼 쓰거나 `agents_version`을 올리면 session-start와 스킬 버전 알림이 이미 현재 배포라고 판단하여 재실행 안내가 나오지 않는다.
- story-review는 `permission` 필드로 OpenCode 에이전트의 정상 여부를 판단했다. #443 이후에는 복수형 `permissions:`만 있어 모델이 정상 에이전트를 malformed로 판단하고 solo로 대체할 수 있었다.
- 여러 스킬이 ‘Claude/OpenCode는 `subagent_type` 사용’이라고 설명했다. OpenCode 2.x 위임 도구는 `subagent`이고 인자는 `agent`다(2.0.16 바이너리 내장 설명도 `subagent_type`이 아닌 `agent` 사용을 명시).

## Decision

- `skills/story-setup/references/deploy-opencode.md`의 배포 전제(2026-09-26부터 SKILL.md에서 분리, [호스트별 배포 분리](../architecture/2026-09-26-setup-by-host.md) 참조): 주 버전이 2 미만이거나 버전을 확정할 수 없으면 OpenCode 배포를 중단한다. 버전을 모르면 사용자 터미널에서 `opencode --version`을 실행해 달라고 요청하고 대화에서 2.x임을 확인한 뒤에만 계속한다.
- OpenCode 배포 중단 시 대상이 opencode뿐이면 `.story-deployed`를 쓰거나 갱신하지 않는다(기존 파일은 그대로 두고 `agents_version`을 올리지 않음). OpenCode 파일도 전혀 쓰지 않는다. 대상이 여러 개면 다른 호스트는 정상 배포하되 기록하는 `target_cli`에서 opencode를 제외한다. 보고서 첫 줄에 OpenCode 미배포와 이유를 알리고 업그레이드 후 재실행하여 OpenCode를 다시 추가하도록 안내한다.
- 이미 배포한 프로젝트에서 재실행할 때 `target_cli`에 opencode가 없지만 `.opencode/plugins/story-hooks.ts` 또는 `.opencode/agents/`가 있으면 AskUserQuestion으로 OpenCode를 다시 추가할지 묻는다. 추가를 선택하면 먼저 버전 검사를 통과한 뒤 `target_cli`에 기록한다. 그렇지 않으면 sentinel의 `agents_version`은 이미 현재 버전이고 `target_cli`에 따라 감지도 건너뛰어 업그레이드한 OpenCode가 영원히 다시 배포되지 않으며 예전 플러그인이 2.x에서 조용히 실패한다.
- 업그레이드 명령은 먼저 `npm rm -g opencode-ai`를 실행하고 `@opencode/cli`를 설치한다. 두 패키지 모두 `opencode` 명령을 제공하므로 구패키지를 제거하지 않으면 PATH에 1.x가 남을 수 있다.
- story-review는 `mode: subagent`와 `permissions:` 규칙 목록을 검사한다. 구버전 단수형 `permission:`은 재배포가 필요한 것으로 본다.
- story-short-write·story-deslop·story-import·story-review의 위임 설명을 ‘OpenCode는 `subagent`의 `agent` 인자 사용’으로 바꾼다.
- `scripts/check-opencode-adapter.sh`는 버전 불명 시 중단, OpenCode-only 차단 시 `.story-deployed`를 쓰지 않는다는 문구를 단언하고 예전 ‘버전 파싱 실패 → 계속 배포’를 거부한다. story-review가 `permissions:`로 검증하는지도 단언한다.

## Alternatives considered

- **‘버전 불명이어도 계속 배포하고 보고서 첫 줄에 안내’ 유지**: 샌드박스에서 `opencode`를 실행할 수 없는 환경(PATH에 없음, OpenCode 자체 세션의 제한)에서도 사용자를 멈추지 않고 배포를 끝낼 수 있다는 장점이 있다. 그러나 최악의 경우는 1.x이며 이때 읽기 전용 에이전트가 쓰기·shell 권한을 받는다. 이는 편의성 저하가 아니라 프로젝트를 망가뜨릴 위험이고 첫 줄 안내는 쉽게 지나칠 수 있다. 사용자 버전 확인 후 계속하는 방식은 샌드박스에서 대화 한 번이 추가되지만 여전히 완료할 수 있다.
- **1.x에서 단수형 `permission:`으로 대체 에이전트 생성**: 1.x 사용자도 읽기 전용 제약을 받을 수 있다. 그러나 유지 관리자는 1.x 분기 코드를 남기지 않기로 결정했다(Related 참조). 1.x에서는 본문 검사 플러그인도 로드할 수 없어 배포가 불완전하다.
- **차단되어도 `.story-deployed`를 쓰고 `target_cli`만 비우기**: 배포 시도 흔적을 남길 수 있다. 그러나 session-start와 스킬 버전 알림은 `agents_version`으로 오래되었는지 판단하므로 현재 버전을 기록하면 미배포 프로젝트가 최신처럼 보이고 재실행 안내를 받지 못한다.

## Consequences

- **이점**: 1.x나 버전 불명일 때 권한이 무효인 읽기 전용 에이전트를 배포하지 않는다. OpenCode-only 프로젝트가 차단되면 다음 세션에서도 story-setup 재실행 안내가 나온다. 다중 호스트 프로젝트는 업그레이드 후 재실행 시 OpenCode 재추가 질문을 받는다. story-review가 정상 2.x 에이전트를 malformed로 오인하지 않는다.
- **비용**: 배포 환경에서 `opencode --version`을 실행할 수 없는 사용자는 확인 단계가 하나 늘어난다. 다중 대상 배포에서 OpenCode가 차단되면 `target_cli` 한 항목이 빠져 재실행 때 질문으로 추가해야 한다. 작가가 `.opencode/`를 직접 삭제한 프로젝트에는 질문하지 않는다.
- **알려진 한계**: 버전 검사는 여전히 스킬 텍스트가 모델 실행을 제약하는 방식이며 스크립트로 강제하지 않는다. `check-opencode-adapter.sh`는 문구 존재만 검사하고 실제 1.x에서 배포를 실행하지 않는다.
