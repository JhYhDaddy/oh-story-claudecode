# Agent Note: OpenCode 2.2부터 skill·Code Mode 도구 권한을 실제 호출로 검증

Status: implemented

Related: [2026-09-23-opencode-v2-only](../architecture/2026-09-23-opencode-v2-only.md)(런타임 권한 테스트에서 ‘도구 목록으로 판정’하던 전제)

## Problem

CI의 `cli-compat`는 `@opencode/cli@latest`를 설치한다. OpenCode 2.2.0(2026-10-27) 출시 후 main의 `scripts/test-agent-permissions.py --opencode`가 실패했다. 읽기 전용 chapter-extractor 등의 하위 에이전트 목록에 `skill`과 `opencode_worktree_remove`가 추가되었다. 같은 main은 2.1.4에서 통과한다.

2.2.1 소스(`Tool.snapshot`)를 확인한 결과 두 변화가 있었다.

- `execute`가 거부되면 원래 Code Mode에 숨겨져 있던 도구가 직접 노출된다(상위 프로젝트 #59315). 우리 하위 에이전트는 모두 `execute`를 거부한다.
- 2.2는 모든 에이전트에 브라우저 스킬 대상 `action: skill` deny 규칙 하나를 덧붙인다. 리소스가 특정 스킬이므로 `skill`의 마지막 일치 규칙이 더 이상 전역 deny가 아니게 되어 목록에서 제거되지 않는다. 실제 호출 시 `skill`은 로드할 스킬별로 권한을 판단하므로 우리의 `"*"` deny는 그대로 차단한다.

따라서 ‘모델이 받은 도구 목록이 곧 런타임 판정’이라는 전제가 이 두 종류의 도구에는 더 이상 성립하지 않는다.

## Decision

- `test_opencode_runtime`이 목록을 판정하기 전에 `skill`과 `opencode_worktree_remove`를 제외하고 나머지 단언은 유지한다.
- `skill`은 실제 호출로 검증한다. 테스트 프로젝트에 `.opencode/skills/probe/SKILL.md`를 두고 목록에 `skill`이 있는 각 하위 에이전트가 호출하게 해 `SKILL_CANARY`를 얻지 못함을 단언한다. 전체 도구를 상속한 대조 fixture는 같은 스킬을 호출해 반드시 해당 값을 얻어야 한다. 스킬을 찾지 못한 것이 아니라 권한 때문에 거부됨을 증명한다.
- `opencode_worktree_remove`는 에이전트에 `edit`가 있을 때만 나타난다고 단언한다(이 도구의 권한 키가 `edit`).
- 에이전트 템플릿은 바꾸지 않는다. 템플릿 끝에 명시적 `action: skill` deny를 넣어도 목록 노출을 막지 못한다(2.2의 추가 규칙이 뒤에 놓임). 실제 호출은 원래부터 거부된다.

## Alternatives considered

- **CI를 `@opencode/cli@2.1.x`에 고정**: 테스트를 건드리지 않고 바로 통과한다는 장점이 있다. 그러나 사용자는 최신 버전을 설치하므로 버전 고정은 실제 사용자 런타임 검사를 중단하고 문제를 미룰 뿐이다.
- **에이전트 템플릿에 명시적 skill deny 추가**: 설정 원본에서 제한을 강화한다는 장점이 있다. 그러나 2.2.1 실측에서 효과가 없고 목록에 여전히 `skill`이 나타나므로 채택하지 않는다.

## Consequences

이점: 테스트가 2.1.4와 2.2.1 모두에서 통과한다. `skill` 거부를 실제 호출과 대조군으로 증명하므로 목록 확인보다 직접적이다.

비용과 남은 위험: `opencode_worktree_remove`는 `edit` 권한으로 판정한다. `edit *`가 허용된 narrative-writer·story-architect·character-designer·story-researcher는 2.2에서 이를 호출해 git worktree를 삭제할 수 있다. 2.1에서는 거부된 Code Mode 안에 숨겨져 있어 하위 에이전트가 접근하지 못했다. 현행 권한 형식은 작업·리소스 경로로만 규칙을 작성할 수 있으므로 이를 거부하면 파일 편집까지 거부해야 한다. 따라서 이번에는 ‘edit와 함께 노출’로만 제한하고 여기에 기록한다. 상위 프로젝트에 알리거나 다른 방법을 찾을지는 유지 관리자가 결정한다.

## 검증

- `python3.12 scripts/test-agent-permissions.py --opencode <@opencode/cli 2.2.1>`와 `<2.1.4>`가 모두 통과했다.
- 수정 전 main은 2.2.1에서 `AssertionError: ('chapter-extractor', {..., 'skill', ...})`를 보고했다.
