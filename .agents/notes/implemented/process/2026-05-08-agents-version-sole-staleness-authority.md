# Agent Note: agents_version을 배포물 갱신 필요 여부의 유일한 런타임 기준으로 사용

Status: implemented

## Problem

story-setup은 사용자 프로젝트에 hooks·agents·rules·agent-references를 배포한다. 스킬 패키지를 갱신하면 이미 배포한 프로젝트가 조용히 뒤처진다. session-start가 ‘/story-setup을 다시 실행해야 한다’고 판단할 방법이 필요하다. 동시에 배포물에 영향 없는 스킬 텍스트 변경으로 사용자를 방해하거나 옛 스킬 패키지가 더 최신 배포물을 낮춰 덮어써서는 안 된다.

## Decision

- `.story-deployed` sentinel은 `agents_version`(정수), `setup_skill_version`, `target_cli`, `resolver_strategy`, `references_dir`를 포함한다. 현재 값의 단일 원본은 `scripts/current-contract.json`이다.
- `agents_version`만 런타임에서 갱신 필요 여부를 결정한다. `session-start.sh`와 story-setup Phase 1은 이것만 비교한다. 누락·비정수·현재보다 작음이면 갱신 대상으로 보아 story-setup을 다시 실행해 agents/hooks/rules/reference bundle을 덮어쓴다. 같으면 배포 완료 상태이며 AskUserQuestion으로 재배포 여부를 확인한다. 더 크면 로컬 스킬이 프로젝트보다 오래된 것이므로 반드시 중단하고 배포 파일을 전혀 쓰지 않으며 다운그레이드 덮어쓰기를 하지 않는다.
- `setup_skill_version`은 존재만 검사하며 뒤처져도 재배포를 유발하지 않는다(의도된 설계). 런타임에서 과거 템플릿을 단계별로 호환하지 않는다. 업그레이드는 재실행이다.
- 버전 증가 규칙: 배포물 동작이 바뀔 때만 올린다. 단순 텍스트 경량화나 spawn prompt에만 인라인되는 변경은 올리지 않는다. 증가는 출시 주기에 따른다. 개발 중 PR이 에이전트 템플릿을 바꿔도 미출시 버전은 유지하고 출시 PR에서 일괄 증가시키며 UPGRADING의 ‘현재 버전’을 갱신한다.
- 검사: `check-story-setup-deployment.sh`가 `current-contract.json`에서 현재 값을 읽고 N-1 / N / N+1 sentinel로 session-start의 경고 / 무응답 / 다운그레이드 거부를 각각 단언한다. `setup_skill_version`이 뒤처져도 잘못 경고하지 않는지도 확인한다.

출처: 3442428 (#7), 12a9655 (#240), 6af0529 (#359), 1e2488b (#395), abe9663 (#416)

## Alternatives considered

- **`setup_skill_version`도 비교에 포함**: 버전 하나면 되고 의미가 직관적이라는 장점이 있다. 그러나 내용 변경도 ‘재배포 필요’로 오판하게 된다. session-start 주석과 배포 검사는 이를 사용하지 않는 것이 설계 의도임을 고정한다.
- **에이전트 템플릿을 바꾸는 PR마다 버전 증가**: 배포물이 바뀌자마자 사용자가 받게 할 수 있다. 그러나 한 출시 주기 안에 재실행을 여러 번 강요한다. 6af0529의 ‘keep agent version release-gated’와 590d10e의 ‘미출시 agent 계약 버전 유지’는 모두 출시 시 일괄 증가를 선택했다.
- **CI grep으로 UPGRADING에 특정 버전이 반드시 있어야 한다고 고정**: 과거에 있었으나 12a9655에서 제거했다. 동작이 아닌 문구를 검사하므로 출시 때 UPGRADING 보완 여부는 출시 목록과 사람이 확인한다.
- **런타임에서 옛 템플릿을 단계별 호환**: UPGRADING에서 명시적으로 하지 않기로 했다. 배포기는 소유 유형에 따라 관리 파일을 교체하고 사용자 파일을 병합하면 된다.

## Consequences

- **이점**: 배포물이 실제로 바뀔 때만 사용자에게 알리며 옛 패키지가 최신 배포물을 덮어쓰지 않는다. `agents_version` 한 곳을 바꾸면 모든 호스트의 갱신 알림을 유발할 수 있다.
- **비용과 알려진 한계**: 출시 전 main의 템플릿 변경은 출시 시 버전을 올릴 때까지 기존 배포 프로젝트에 보이지 않는다(v0.7.10 UPGRADING은 개발 중 main v30을 사용한 프로젝트도 재실행해야 한다고 명시). 기준값을 `session-start.sh`, story-setup `SKILL.md`, UPGRADING, `current-contract.json`에 맞춰야 하며 단일 참조가 아닌 CI 검증 지점에 의존한다.

## 검증

`bash scripts/check-story-setup-deployment.sh`(TS10 버전 임계값 + N±1 sentinel 상황); `bash scripts/check-current-skill-contracts.sh`가 manifest와 SKILL.md의 버전 일치를 검증한다.
