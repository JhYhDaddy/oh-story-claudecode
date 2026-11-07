# Agent Note: story-setup 배포 목록의 두 열은 기준 디렉터리가 다르며 동일 객체 복사는 항상 no-op이다

Status: implemented

## Problem

story-setup 배포 목록에서 `Source path`는 실행 중인 스킬 패키지를, `Target path`는 사용자 프로젝트 루트를 기준으로 하지만 두 기준 디렉터리가 명시되지 않았다. skills-only 환경(OpenClaw / Reasonix / generic)의 프로젝트 사본은 스킬 전체를 복사한 것이므로 재실행 시 프로젝트 안의 사본이 실행되어 양쪽이 같은 디렉터리를 가리킨다. Codex / Reasonix가 `.agents/skills → ../skills` 심볼릭 링크로 로드할 때도 경로 문자열은 다르지만 같은 디렉터리를 가리킨다. OpenCode 행의 기준 없는 상대 소스 경로는 첫 배포 이후 프로젝트에 방금 만든 대상과 일치한다. 문구 그대로 복사하면 `agent-references/`가 자기 자신 안에 중첩되고, 몇 차례 재실행하면 디스크가 가득 찬다(#363).

## Decision

- `skills/story-setup/SKILL.md`에서 목록 앞에 두 열의 기준 디렉터리를 명시한다. 목록의 각 행과 환경별 배포 알고리즘의 모든 재귀 복사 단계 실행 전에 반드시 와일드카드를 개별 소스/대상으로 구체화한 다음 같은 스킬의 `scripts/copy-path-safety.py`로 검사한다. 스크립트는 realpath 의미에 따라 기존 심볼릭 링크를 추적하고, 양쪽이 모두 존재하면 `samefile`로 파일 시스템 객체가 같은지 확인한다.
- 출력 JSON을 읽는다. `status: same`이면 no-op이며 복사를 금지한다. `copy_allowed: true`일 때만 복사할 수 있다. `source_missing`, `unsafe_target_within_source`, `filesystem_identity_error`이면 해당 단계를 중단하고 보고해야 한다. 절대 경로 변환이나 문자열 비교만으로 검사가 끝난 것으로 보지 않는다. 스크립트를 실행할 수 없다면 현재 환경의 파일 시스템 API로 완전히 같은 검사를 해야 한다. 확인할 수 없으면 중단하고 절대로 복사를 시도하지 않는다.
- 배포 전에 자기 중첩 잔여물을 반드시 삭제하고 설치 보고서에 삭제한 경로를 나열한다. 대상은 네 references 루트 아래에 생긴 추가 `agent-references/` 계층(여러 겹일 수 있음)과 `skills/story-setup/skills/`이다.
- skills-only 세 환경의 repository `agent-references/` 행은 no-op으로 명시한다. 스킬 전체 복사에 포함되므로 따로 복사하지 않는다.
- 예외: skills-only 환경의 기존 잔여물에는 자동 정리가 도달하지 못한다. 재실행되는 것은 프로젝트 안의 `SKILL.md`이기 때문이다. README / UPGRADING에서 사용자에게 수동 삭제를 안내한다. 프로젝트의 스킬 문서는 새 패키지로 `skills/` 아래 13개 디렉터리를 덮어써야 갱신된다.
- 검사 장치: `scripts/check-story-setup-deployment.sh`에 자기 복사 탐지기를 넣는다. `Source path` + `Target path` 헤더가 있는 목록 표 안에서만 판정하며, 산문 분기는 두 경로 사이 16자 범위 안에 '到'가 있어야 한다. 탐지기는 먼저 양성·음성 fixture로 자체 검사한 다음 `SKILL.md`를 검사한다.

출처: ef6ff7b (#364)

## Alternatives considered

- **문서 전체에서 같은 경로가 두 번 나오는지 탐지한다** — 범위가 넓고 구현이 가장 간단하다는 장점이 있다. 채택하지 않았다. 저장소 전체 396개 `.md`에서 인물 관계 템플릿과 CHANGELOG 서술을 오탐했다. 목록 표와 인접 범위로 한정하면 오탐 없이 원본 파일의 네 곳을 정확히 탐지한다.
- **문서에 '삭제한 뒤 다시 설치하고 setup을 재실행한다'고만 쓴다** — 한 문장으로 끝난다는 장점이 있다. 채택하지 않았다. skills-only 환경에서는 프로젝트의 이전 스킬을 재실행하므로 새 패키지 내용을 가져오지 못한다. 수동 정리와 새 패키지 덮어쓰기를 나누어 설명한다.
- **문자열이나 절대 경로만 비교한다** — 스크립트에 의존하지 않는다는 장점이 있다. 채택하지 않았다. 심볼릭 링크에서는 경로 문자열이 달라도 같은 객체일 수 있다.

## Consequences

- **이점**: 세 환경에서 재실행이 멱등적이다. CI가 목록 문서 단계에서 동일 Source/Target을 그대로 복사하는 회귀를 차단한다.
- **비용과 알려진 한계**: 복사 단계마다 스크립트 호출이 한 번 추가된다. 탐지기는 목록 헤더와 '到' 표현만 인식하는 휴리스틱이므로 헤더 형식이나 표현을 바꾸면 누락될 수 있다. fixture도 함께 갱신해야 한다. 기존 잔여물은 여전히 사용자가 한 번 수동으로 정리해야 한다.

## 검증

`bash scripts/check-story-setup-deployment.sh`: fixture 자체 검사는 정확히 2, 3, 5, 18행만 탐지해야 하고, 이어지는 `SKILL.md` 검사에서는 탐지 결과가 없어야 한다.
