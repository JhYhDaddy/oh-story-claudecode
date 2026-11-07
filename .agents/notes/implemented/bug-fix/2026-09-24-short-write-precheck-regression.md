# Agent Note: 단편 집필 전 매개변수 검수 회귀: Phase 3 파일에 명령을 직접 넣고 전달 보고를 작가 중심으로 변경

Status: implemented

## Problem

v0.7.10(#402)에서는 본문을 생성하기 전에 전체 글자 수, 절 수, 사용자가 정한 절별 최솟값을 동시에 충족할 수 있는지 확인하는 매개변수 검수를 추가했다. #418에서 story-short-write의 Phase 3 / 4를 `workflow-draft.md` / `workflow-revision.md`로 나눈 뒤 `workflow-draft.md`에는 “Phase 4 전달 명령에 `--check-contract`를 추가해 먼저 실행”이라고만 적혔다. 명령 본체는 `workflow-revision.md`에만 있었고 `SKILL.md`는 Phase 4에 가서야 `workflow-revision.md`를 읽도록 했다. 실제 Claude Code 세션에서 모델은 23번째 도구 호출에 본문을 쓰고 29번째에 `workflow-revision.md`를 읽었으며 집필 전 검수는 한 번도 실행하지 않았다. 이후 약 40턴 동안 직접 Python을 작성해 글자 수를 세고 수정한 끝에 4000–5000자 범위에 겨우 들어갔다(4010자).

같은 세션의 전달 보고는 `check-phase2-contract.js` 등 스크립트 다섯 개의 통과 결과와 “고정 12열 절별 개요”를 나열했다. 작가가 본 것은 이야기가 아니라 개발 로그였다.

## Decision

- `workflow-draft.md`의 “집필 전 매개변수 검수”에 전체 명령 `node {skill 根}/scripts/check-delivery-contract.js --json --check-contract --min-chars {MIN} --max-chars {MAX} --sections {N} [--min-section-chars …] {短篇目录}`를 넣는다. 매개변수를 고정한 뒤 `正文.md`를 쓰기 전에 반드시 실행하도록 명시하고 “집필 전 준비” 앞에 둔다. exit 0은 매개변수를 동시에 충족할 수 있다는 뜻일 뿐이다. exit 2는 충돌이므로 집필 전에 멈춰 중국어로 조정할 항목을 선택해 달라고 요청한다.
- 작업 도중 글자 수는 같은 명령에서 `--check-contract`를 빼고 다시 실행한다. 공백 제외 문자 수를 전체 누적값으로 사용하며 미완성 상태의 exit 1은 정상이다. 절별 분포는 계속 `short-format.md`의 “글자 수 집계”를 사용한다. Python 계수기를 직접 작성하지 말라고 명시한다. 이로써 집필 중과 최종 전달에 같은 기준을 쓴다.
- Phase 4의 최종 전달 검수는 기존대로 `workflow-revision.md`에 둔다.
- `workflow-revision.md`에 “전달 설명(작가용)”을 추가한다. 작성한 내용(제목, 핵심 훅 또는 반전, 글자 수, 절 수), 작가 결정이 필요한 사항(추천 기본값을 포함한 한 문장 질문), 선택 가능한 다음 단계를 설명한다. 자체 검사 결과는 쉬운 말 한 문장으로 요약하고 스크립트 이름, 검사 ID, 필드 이름, 매개변수, 개요 표 형식을 쓰지 않는다. 전달 검수가 실패해도 이 형식으로 부족한 점을 알린다. `workflow-design.md`의 Phase 2 관문도 실패하면 설계에 무엇이 부족한지 설명하고 구상 보고에는 이야기와 결정할 질문만 담는다.
- `scripts/check-reference-gates.js`는 첫 화면 관문과 Phase 3 / 4 절이 각각 `workflow-draft.md` / `workflow-revision.md`로 연결되는지 고정한다. `workflow-draft.md`에는 `--check-contract`와 매개변수 세 개를 포함한 실제 명령이 “집필 전 준비” 앞에 있어야 하며 “Phase 4의 전달 명령”이라는 표현은 없어야 한다. `workflow-revision.md`에는 `--check-contract` 없는 최종 검수 명령이 남아야 한다. 이전 `workflow-draft.md`는 이 검사에서 실패한다.
- 예산을 명시적으로 상향한다. `workflow-draft.md` 4600→4750, `workflow-revision.md` 1700→1850, `workflow-design.md` 2350→2400, “단편 실행 지침” 경로 11500→11950. 사유는 `scripts/doc-budget.json`에 등록한다.

## Alternatives considered

- **`workflow-revision.md`를 Phase 3에서 미리 읽음** — 글자를 늘리지 않아도 명령은 이미 그 파일에 있다. 그러나 Phase 3에서 교정 세부 규칙 전체의 컨텍스트 비용을 부담해 분할 의미가 사라진다. “A 파일을 읽어 B 단계 명령을 찾음” 자체가 이번 누락의 원인이기도 하다.
- **`SKILL.md` 첫 화면 관문에 명령 배치** — 진입 파일은 유일하게 읽기를 보장할 수 있다. 그러나 `SKILL.md`에는 라우팅만 남기기로 했으며 명령을 넣으면 구상만 하는 상황까지 모두 비용을 부담한다. Phase 3는 원래 `workflow-draft.md` 완독을 요구하므로 그곳이면 충분하고 실제 집필 시점에도 가깝다.
- **전달 설명에서 스크립트 이름만 제거하고 템플릿은 제공하지 않음** — 변경과 예산이 가장 작다. 그러나 금지만 하면 모델이 검사 ID나 필드 이름 같은 다른 개발 용어로 바꾼다. 세 블록 구조와 한 문장 요약 예시가 있어야 작가 관점을 안정적으로 유지한다.

## Consequences

- 이점: 집필 전 검수에 바로 실행할 명령이 있으며 집필보다 먼저 배치되어 매개변수 충돌을 본문 작성 전에 발견할 수 있다. 집필 중과 최종 전달에서 같은 계수 기준을 사용하므로 직접 만든 스크립트로 반복 측정하지 않는다. 작가는 이야기, 글자 수, 결정할 질문과 다음 단계만 전달받는다.
- 비용: 네 예산을 합해 약 800자 올리고 단편 Phase 3 / 4 세션마다 약 450자를 더 부담한다. 검사는 명령 문자와 상대 위치만 고정하므로 텍스트가 있다는 사실만 입증하며 모델의 실행 여부는 입증하지 않는다. 준수율은 실제 집필 기록 재생으로 검증해야 한다.
- `short-format.md`의 “글자 수 집계” 전체 명령은 여전히 줄바꿈을 포함한 코드 포인트 수를 세며 전달 검수의 공백 제외 문자 수와 다르다. 이 명령은 `scripts/test-charcount-portable.sh` 및 다른 스킬과 문자 단위로 연결되어 있다. 이번에는 `workflow-draft.md`의 전체 누적값만 전달 검수 스크립트를 사용하게 하고 공유 명령은 바꾸지 않았다.
