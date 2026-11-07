# Agent Note: 자주 읽는 경로에는 라우팅과 필수 규칙만 남기고 기법과 단계별 절차를 references로 이동

Status: implemented

## Problem

narrative-writer 템플릿은 장마다 에이전트를 생성할 때마다 비용이 발생하며, 약 300줄에 필수 규칙과 기법이 섞여 있다. story-short-write의 `SKILL.md`는 모든 단편 작업에서 무조건 로드되지만, 구상 단계의 틀과 설계 검증은 Phase 2에서만 필요하다. 장편에서는 이미 상황별로 절차를 `workflow-*.md`로 옮겼다(새 책 시작 -30%, 재작업 -41%). 그러나 당시 `agents_version`을 올리지 않으려고 에이전트 템플릿은 의도적으로 건드리지 않아 부채가 누적되었다.

## Decision

- **narrative-writer 기준 템플릿**(`skills/story-setup/references/templates/agents/narrative-writer.md`, OpenCode / Codex 복사본은 생성기가 동기화)은 약 110줄로 구성하고 필수 규칙을 앞에 둔다. 상세 개요를 유일한 사건 전개 설계도로 삼기, 본문 형태의 자율성, 새 요소의 세 단계 분류, 글자 수 자체 측정 금지, 메타정보 격리, 형식 규약, 추적 정보 작성 금지가 해당한다. 집필 기법은 agent-references(`writing-craft.md` 등)로 옮긴다. 참조 파일 표는 “행별로 조건을 판단하고 해당하면 읽으며 해당하지 않으면 미리 로드하지 않는다”로 구성한다. 참조 경로 규칙은 세 호스트 동기화기가 인식하는 표준 문단 형태를 유지한다. spawn prompt 뼈대는 `build_writer_prompt.py`가 결정적으로 조립하고 주 세션은 일곱 칸만 채운다.
- **story-short-write `SKILL.md`**에는 진입 Reference Gate, 상황별 라우팅과 산출물 계약만 남긴다. Phase 2 구상 절차는 `references/workflow-design.md`, Phase 3 / 4는 `workflow-draft.md` / `workflow-revision.md`에 두고 단계별로 읽는다. 진입 검증 관문은 반드시 `SKILL.md`에 남긴다.
- **장편도 같은 구조**를 사용한다. `SKILL.md`는 상황별 라우팅만 담당하고 `workflow-setup` / `daily` / `chapter` / `revision`을 상황에 따라 로드한다.
- 이동만 하고 삭제하지 않는다. 기법 규칙을 하나도 줄이지 않는다. 이동한 파일은 doc-budget에서 보수적으로 전액 산입하며 분할을 같은 단계의 총량 절감으로 계산하지 않는다. 조건부 참조는 `branches`에 등록한다.

출처: 1e2488b (#395), 9c40276 (#401), fde1754 (#418), 1eae178 (#352)

## Alternatives considered

- **단일 파일 전체 로드를 유지하고 예산만으로 글자 수 축소** — 한 파일을 한 번에 읽으면 누락을 막을 수 있다. 그러나 1eae178 실측에서 새 책 시작과 재작업은 본문을 쓰지도 않으면서 11k자의 단일 장 절차 비용을 부담했다. 예산은 수량만 줄일 뿐 상황 불일치를 없애지 못한다.
- **템플릿 간소화와 `agents_version` 상향을 동시에 진행** — 배포 산출물이 바뀌면 즉시 갱신해야 한다는 장점이 있다. 그러나 1e2488b에서는 템플릿 변경을 먼저 반영하고 관련 PR 확정 후 버전을 일괄 상향하기로 했다. [agents_version 기록](../process/2026-05-08-agents-version-sole-staleness-authority.md)을 참조한다.
- **중복 기법 규칙도 함께 삭제** — 실제 중복이라는 장점이 있다. 그러나 PR #228 블라인드 평가에서 이를 삭제하면 퇴보했으므로 이동만 하고 삭제하지 않는다.

## Consequences

- **이점**: 단편 `SKILL.md`는 39.6k → 11.4k바이트, 집필자 정의는 293 → 110줄로 줄었다. 참조를 필요할 때 읽으며 집필 전에는 현재 단계의 텍스트 비용만 부담한다.
- **비용과 알려진 한계**: 한 작업에서 여러 파일을 읽어야 한다. “다 읽은 뒤 작성”은 Reference Gate의 문구에만 의존한다(`rg`로 일부만 읽는 것은 완독이 아니다). 성능이 낮은 모델은 건너뛸 수 있어 #415에서 “preserve reference reads”를 보완했다. 라우팅 문구도 예산을 차지한다(paths의 `why`에 +900 등록). 분할은 파일 간 참조를 끊기도 한다. #418 이후 단편 `workflow-draft.md`의 집필 전 매개변수 검수에는 “Phase 4 전달 명령에 `--check-contract`를 추가”라고만 쓰였고 명령 본체는 `workflow-revision.md`에 남았다. 실측에서 모델은 먼저 본문을 쓰고 집필 전 검수를 하지 않았다. 수정과 방어 검사는 [단편 집필 전 검수 회귀](../bug-fix/2026-09-24-short-write-precheck-regression.md)를 참조한다. 분리할 때 각 단계 파일에는 그 단계에서 실행할 명령이 자체적으로 포함되어야 한다. 재검토 신호: 하위 에이전트가 외부로 옮긴 기법을 누락하는 비율이 다시 높아지면 해당 규칙을 더 옮기지 말고 템플릿으로 되돌린다. narrative-writer 예산의 `why`에는 같은 장을 여섯 번 실행하는 동안 모두 `writing-craft.md`를 누락한 이력이 있다.

## 검증

`bash scripts/check-doc-budget.sh`의 “본문 에이전트 기본 규칙”과 “장편 일일 집필 주 세션” 경로 합계, `python3 scripts/test-writer-pipeline.py`, `bash scripts/check-story-setup-deployment.sh`의 템플릿 동작 기준을 확인한다.
