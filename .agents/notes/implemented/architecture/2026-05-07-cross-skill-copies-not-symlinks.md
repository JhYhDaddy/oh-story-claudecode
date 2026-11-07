# Agent Note: 스킬 간 공유 파일은 symlink 대신 실제 사본과 명시적 목록으로 관리

Status: implemented

## Problem

여러 스킬이 같은 참조 자료(banned-words·anti-ai-writing)와 런타임 스크립트(check-ai-patterns.js·cdp-utils.js)를 필요로 한다. 각 스킬은 `npx skills add`, marketplace, story-setup의 사용자 프로젝트 복사 등을 통해 독립적으로 설치·배포할 수 있어야 한다. symlink나 `../` 스킬 간 경로는 따로 설치하거나 Windows에 symlink 권한이 없으면 끊어진다.

## Decision

- 각 스킬 디렉터리는 자체 완결적이어야 하며 스킬 간 공유 내용은 실제 사본으로 둔다. 스킬 사이에서 symlink나 `../` 참조를 절대 쓰지 않는다. `static-check.py`가 스킬 간 파일 참조를 막는다. 유일한 예외는 기반 구성 요소 `browser-cdp`이며 업무 스킬은 그 실행기를 참조할 수 있다.
- 두 명시적 목록으로 사본 일치를 관리하고 CI의 `check-shared-files.sh`가 차례로 검사한다.
  - `scripts/shared-assets.json`: 런타임 스크립트의 그룹별 유일한 `source`와 `targets`를 지정한다. source 변경 후 `sync-shared-assets.py sync`를 실행한다. 같은 이름의 런타임은 그룹 하나에만 속할 수 있으며 target은 source basename을 유지해야 한다. 이름 변경으로 단일 담당 원본 규칙을 우회할 수 없다.
  - `scripts/shared-references.json`: 참조 문서의 source / targets를 지정한다. 매우 비슷하지만 의도적으로 달라진 파생 관계는 `derived_groups`에 출처와 차별화 이유를 설명하고 근사 스캔(행 단위 Jaccard / containment)으로 확인한다.
  - 런타임·참조 목록은 파일 유형별로 배타적이며 같은 경로를 두 목록에 등록할 수 없다.
- 목록에 등록되지 않은 동명·유사 사본은 즉시 실패한다.
- 저장소 수준 예외: `.agents/skills`는 `../skills`를 가리키는 상대 symlink(agentskills.io 표준 경로)로 Codex / Reasonix 검색용이며 두 번째 스킬 사본이 아니다. `check-codex-adapter.sh`는 유효한 상대 symlink인지 검사한다(무효·절대 링크는 검색이 조용히 실패하게 함). Windows에는 `git core.symlinks=true`가 필요하다.

출처: 89ff2c8 (#5), 4e8a2c8 (#17), 398795d (#189), 3f2a890

## Alternatives considered

- **`skills/shared/` + symlink**: 단일 원본이라 불일치가 없다는 장점이 있다. 145a635는 취약한 `../` 참조를 symlink 16개로 바꿨다. 그러나 독립 설치와 Windows에서 symlink가 작동하지 않아 89ff2c8이 `skills/shared/`를 삭제하고 4e8a2c8이 symlink 16개를 모두 실제 사본으로 바꿨다.
- **스킬 간 `../` 경로 참조**: 복사하지 않고 한 곳만 바꾸면 적용된다는 장점이 있다. 그러나 역시 독립 배포를 깨므로 ce8216b에서 잔여 참조를 제거한 뒤 static-check로 차단한다.
- **담당 원본 등록 없이 ‘동명 파일의 바이트 일치’만 스캔**: 초기 `check-shared-files.sh`의 방식이다. 그러나 어느 파일이 원본인지 불분명하고 의도적으로 다른 파일(각 스킬의 output-templates.md)은 IGNORE 목록에 의존해야 하며 유사하게 고쳐 쓴 사본도 찾을 수 없다. 명시적 목록으로 대체한다.

## Consequences

- **이점**: 어느 스킬이든 단독 복사로 실행할 수 있고 모든 사본의 담당 원본이 명확하며 의도적 차별화는 이유를 적어야 한다.
- **비용과 알려진 한계**: 같은 내용이 저장소에 여러 번 존재한다(agent-references에도 추가 사본). 한 곳을 수정하면 동기화하고 모든 사본을 커밋해야 해서 PR diff가 커진다. 차별화 설명도 관리 부담이다. 모든 대상 호스트가 symlink를 안정적으로 해석하고 배포기가 디렉터리 단위 복사를 하지 않게 되면 재검토할 수 있다.

## 검증

`bash scripts/check-shared-files.sh`, `python3 scripts/test-shared-assets.py`, `bash scripts/check-codex-adapter.sh`의 `.agents/skills` 단언.
