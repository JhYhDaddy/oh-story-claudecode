# Agent Note: story-explorer를 조회 유형별로 로드하고 에이전트 템플릿의 영구 메모리 제거

Status: implemented
Date: 2026-09-26
Related: [35K 로드 상한](2026-09-26-per-call-load-ceiling-35k.md), [작품 분석의 단계별 시점 로드](2026-09-26-analyze-stages-by-moment.md)

## Problem

- **story-explorer는 매 호출 10.7K 전체를 읽음**: 템플릿의 약 절반이 `benchmark_style_load`(집필 전 비교 작품 문체 조회)의 13단계 절차와 출력 예시다. 장 집필 전 비교 조회에만 필요하지만 작가가 “장천의 현재 상태”, “F003 회수 여부”를 묻거나 일일 집필에서 과거 정보를 찾고 원고 검토에서 설정을 찾을 때도 함께 읽는다.
- **`context_load`에 호출자가 없음**: `rg -n context_load skills scripts`는 explorer 템플릿과 생성된 OpenCode / Codex 어댑터 외에 결과가 없다. 일일 집필은 이미 주 세션이 이어쓰기 상태 카드를 읽고 조립 스크립트가 집필 패키지를 구성한다. 문서에만 절차·표 행·출력 예시가 남았고 설명도 “일일 집필 Step 1 컨텍스트 로드”라고 적혀 있다.
- **에이전트 네 개에 `memory: project`가 있음**: character-designer, narrative-writer, story-researcher, story-architect의 frontmatter가 Claude Code 영구 에이전트 메모리(프로젝트 `.claude/agent-memory/`)를 켠다. 작업 공간에 책이 여러 권이면 이전 책·작업의 기억이 이번 호출에 들어가 “시점 간 파일로만 인계” 원칙에 어긋난다. memory는 Write/Edit도 암묵적으로 활성화하여 `disallowedTools: [Edit]`인 story-researcher까지 Edit를 받는다. 이를 추가한 #7, #27, #35에는 이유가 없고 #52에서는 같은 모순으로 읽기 전용 에이전트 두 개에서 제거했지만 나머지 네 개는 남았다.

## Decision

- **비교 조회 절차를 조건부 참조로 이동**: 단계 1–13, 누락 시 중단 규칙과 `benchmark_style_load` 출력 구조 원문을 `skills/story-setup/references/agent-references/benchmark-style-load.md`로 옮긴다. story-setup 자체 파일이며 공유 복사본이 아니므로 `shared-references.json` 등록은 필요 없다. 템플릿에는 다른 에이전트와 같은 “참조 파일 경로 규칙” 문단을 추가한다. `benchmark_style_load` 절에는 “먼저 Read `story-setup/references/agent-references/benchmark-style-load.md`” 한 줄만 남긴다. 단계 5의 중복 충돌 설명 두 문장은 하나로 합친다.
- **`context_load` 삭제**: 표 행, 절차, 고정 읽기량 설명과 출력 예시를 함께 삭제한다. description은 실제 호출 지점(집필 전 비교 조회, 일일 집필 과거 정보 조회, 원고 검토 설정 조회, 질문 라우팅)으로 바꾼다.
- **조회 유형별 예산 분기**: `doc-budget.json`의 story-explorer 경로 이름을 “자료 조회”로 바꾸고 “일반 조회” 5,400(실측 5,349), “집필 전 비교 조회” 10,400(실측 10,326)의 두 분기로 고정한다.
- **템플릿 네 개의 `memory: project` 제거**: 일곱 에이전트 모두 영구 메모리를 사용하지 않는다.
- **검사를 내용 위치에 맞춤**: `check-current-skill-contracts.py`의 주 산출물 누락 시 중단, 자기 작품 비교 제외, 책 디렉터리 탐지, profile_missing 구분의 네 단언은 새 참조 파일을 검사한다. “문체.md를 책 디렉터리 탐지에 사용하지 않음” 금지 규칙에도 새 파일을 포함하고 `test-current-skill-contracts.py` 변이 사례는 새 경로를 사용한다. `check-story-setup-deployment.sh`의 비교 관련 단언 네 개도 새 파일로 바꾸고 세 규칙을 추가한다. 템플릿은 새 파일을 가리켜야 하고 `missing_primary_contract` 또는 `context_load`가 없어야 하며 모든 에이전트 템플릿에 `memory:` 행이 없어야 한다.
- **어댑터**: OpenCode와 Codex의 story-explorer를 다시 생성한다. Antigravity는 배포 때 `generate-antigravity-agents.mjs`가 참조 경로를 바꿔 생성하므로 저장소에 산출물이 없다. `memory`는 원래 OpenCode / Codex 산출물에 들어가지 않아 나머지 네 에이전트 어댑터는 바뀌지 않는다.

## Alternatives considered

- **단일 파일을 유지하고 글자 수만 축소**: explorer는 원래 저렴한 모델(haiku)이므로 Read 하나를 줄이는 편이 안정적이며 참조 읽기를 잊을 위험도 없다. 그러나 비교 조회 절차는 주 산출물 누락 시 중단, 책 디렉터리·문체 별도 판단, 자기 작품 제외 같은 실패 시 차단 계약이다. 글자를 지우면 계약을 지우게 된다. 유형별 분리는 일반 조회를 곧바로 절반 줄이고 비교 조회에 Read 하나를 추가하며 집필자·설계자의 참조 읽기 방식과도 같다.
- **비교 조회를 주 세션에 전부 반환**: benchmark-recall.md에 주 세션 수동 경로 (a)–(g)가 있어 같은 일을 두 번 설명하지 않아도 된다. 그러나 빠른 경로는 장 요약·심층 분석·문체 전문의 많은 중간 읽기를 하위 에이전트 컨텍스트에 두고 주 세션에는 구조화 JSON만 반환한다. 이것이 explorer의 가치이므로 이번에는 로드 시점만 바꾸고 분업은 유지한다.
- **미래를 위해 `context_load` 유지**: 전체 집필 패키지가 다시 필요하면 절차를 다시 쓰지 않아도 된다. 그러나 지금은 조립 스크립트가 결정적으로 패키지를 만들고 예전 문서 절차는 이어쓰기 상태 카드·트랜잭션 draft와 어긋나기 시작했다. 호출되지 않는 분기에 1K자를 쓰게 할 뿐이다.
- **네 에이전트의 memory를 `local` 또는 책별 디렉터리로 변경**: 세션 간 축적한 집필 선호가 유용할 수 있다. 그러나 메모리 디렉터리는 책이 아니라 프로젝트 루트 기준이며 `local`은 위치만 바꾼다. 작가 선호에는 이미 책별 파일에 저장하고 제출 검증하는 작가 메모리와 `设定/文风.md`가 있어 에이전트가 임의로 쓰는 메모리보다 검토하기 쉽다.

## Consequences

- **이점**: explorer 일반 조회는 10,694 → 5,349자(약 −50%), 비교 조회는 10,694 → 10,326자가 된다. 호출자 없는 분기를 삭제한다. 창작 에이전트 네 개는 매 호출 저장 파일만 읽으므로 여러 책의 정보가 섞이지 않는다. researcher 권한은 선언된 `[Read, Glob, Grep, Bash, Write]`로 돌아간다.
- **비용**: 비교 조회에 Read 하나가 추가된다. 기존 배포 프로젝트는 `/story-setup`을 다시 실행해야 새 템플릿·참조를 받는다. 이전 템플릿은 전체 절차를 포함하므로 재실행하지 않아도 계속 동작한다. 기존 `.claude/agent-memory/` 디렉터리는 삭제하지 않으며 재배포 후 읽고 쓰지 않으므로 작가가 직접 정리할 수 있다. 실제 모델 실험은 실행하지 않았다. 이번에는 텍스트 이동과 호출자 없는 분기 삭제만 하며 비교 조회 계약 문구는 바꾸지 않았다.
