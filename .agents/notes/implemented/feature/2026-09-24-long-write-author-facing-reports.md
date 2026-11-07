# Agent Note: 장편 집필 보고를 쉬운 말로 바꾸고 템플릿 정적 검사 추가

Status: implemented
Date: 2026-09-24

## Problem

훅을 배포한 실제 Claude Code 전체 세션에서 story-long-write의 보고·질문에 작가가 이해하거나 선택하기 어려운 개발 용어가 많았다.

- 분량 이탈 시 storyctl 동작명 `accept-current-length / revise-outline-or-target / discard`와 `visible_chars_v1`, `borderline`, `within_user_band`, “내부 범위 ±12%”를 직접 제시했다.
- 일관성 결과는 “S3×3＋S4×5”였고 기획 보고에 Constraint Lock, 안전 일곱 검사 ⑥⑦, 공급 자체 검사, required-fields plotpoint-table 계약 검사기가 등장했다.
- 상태 설명에는 `context.long_term_constraints`, `last_committed_chapter`, `state_revision`, “두 번째 등급 편입”, 뜻 없는 F0xx/E0xx/L1-03이 나왔다.

원인은 workflow의 보고 형식 자체가 내부 이름을 쓰도록 했다는 것이다. 예를 들어 단계 8은 `accept-current-length / revise-outline-or-target / discard`를 보여 주고 일일 종료는 장 수·글자 수·드리프트·공급 피드백을 보고하며 대규모 수정은 `internal_pass / borderline / …`를 보고하게 했다. 기획·개요 수정·장 완료·중단에는 템플릿이 아예 없어 모델이 내부 확인 과정을 그대로 작가에게 쏟았다.

같은 세션에서 두 규칙 모순도 드러났다.

- “계속 써”: SKILL.md 상황 표·workflow-daily는 일일 집필 트리거로 보지만 기획 이어가기에서는 “계속/계속 써/이대로”가 범위를 넓히지 않는다고 했다. 권 하나를 기획한 작가가 계속 쓰라고 하자 여섯 선택지 표를 받았다.
- 추적 초기화: workflow-setup은 본문·state가 없으면 어떤 상세 개요 묶음 저장 후에도 초기화한다고 했지만 project-files는 기획만 하면 추적을 만들지 않는다고 했다. 실제로 개요 하나를 수정해도 초기화하지 않았다.

## Decision

1. SKILL.md에 “작가용 보고” 공통 규칙을 둔다. 보고·질문·중단 설명은 쓴/바꾼 것(장 이름·사건), 작가가 정할 것(쉬운 질문＋선택지＋추천 기본값), 다음 단계만 다룬다. 스크립트·필드·인수·상태 코드·내부 목록명을 금지하고 번호는 “복선 F057(그 편지의 행방)”처럼 이야기 라벨을 붙인다. 검사 결과는 쉬운 말 한 문장, 응답·Notice·Fallback 기계 행은 맨 끝 한 줄로 제한한다. 주 세션이 하위 에이전트 용어를 바꿔 전달한다. 모든 절차에 적용하고 SKILL.md만 매번 로드되므로 진입부에 둔다.
2. 각 절차가 원래 완독하는 workflow 파일에 `<!-- author-report -->` 표식과 ```` ```md ```` 블록으로 보고 템플릿을 둔다.
   - workflow-setup: 새 책·전권/권별/상세 개요·개요 보충/수정의 기획 전달 후 C급 누락과 설정 충돌을 “결정할 사항”으로 묻는다. 비교 작품의 감정·리듬 분석 누락도 쉽게 설명한다.
   - workflow-chapter “작가에게 보고”: 한 장 완료, 분량 이탈, 새 요소 세 단계 중 ③ 결정, 중단을 다룬다. 분량 선택은 “현재 길이로 수락(추천)”, “개요나 목표 분량을 바꾼 뒤 재작성”, “이 장 폐기”로 바꾼다. 블록 밖 한 줄에서 각각 `chapter accept-current-length`, 단계 8 복귀, 제출 없이 본문·작업 디렉터리 삭제에 대응함을 밝힌다. 일관성 수정은 “앞뒤가 맞지 않는 …를 발견해 앞 내용에 맞췄습니다” 한 문장으로 알린다.
   - workflow-daily: 장 수·글자 수·드리프트·공급 피드백 대신 묶음 종료 보고 템플릿을 사용하고 분기·드리프트·재고 확인은 내부 검사라고 표시한다.
   - workflow-revision: 수정 완료 템플릿에서 “약 X자, 기존보다 Y자 증가/감소”라고 설명하고 상태 코드를 보고하지 않는다.
3. `scripts/check-author-reports.py`는 모든 스킬의 `author-report` 블록을 행별 검사한다. snake_case, kebab-case, 스크립트·데이터 파일명, 명령 인수, S1-S4, 이야기 설명 없는 번호, commit/state/revision/Fallback 같은 영어 용어, 안전 일곱 검사·공급 자체 검사·내부 범위·사용자 범위·편입·2등급·3등급 같은 내부 목록명을 발견하면 FAIL이다. `--self-test`는 블록 안에서는 실패하고 밖의 같은 말은 실패하지 않음을 입증한다. `REQUIRED`에 setup 1, chapter 4, daily 1, revision 1의 최소 블록 수를 등록해 검사가 헛돌지 않게 한다.
4. 계속 쓰기 규칙을 통일한다. “계속”, “이대로”, “계획 확인”은 현재 범위만 잇는다. “계속 써”, “이어서 써”는 본문이며 다음 장 개요가 있으면 집필한다. 단, 바로 전 작업이 기획이면 “제N장 본문을 이어 쓸까요?” 한 문장만 기본값 예로 묻고 선택지 표를 내지 않는다. 개요가 없으면 먼저 해당 장 개요를 보충할지 묻는다. workflow-daily 적용 조건도 맞춘다.
5. 추적은 첫 본문 진입 때만 초기화한다. 새 책·개요·상세 개요·보충 같은 기획 단계는 `追踪/`를 만들지 않는다. workflow-setup의 “개요 후 초기화” 두 곳과 project-files 산출물 표를 “첫 본문 작성 전 초기화”로 바꾼다. workflow-chapter는 이미 state 누락을 처리하므로 유지한다.
6. 끊긴 참조 두 곳도 수정한다. SKILL.md가 workflow-chapter의 실제 “글자 수 측정 기준”, “품질 검사” 절을 가리키게 하고 workflow-daily의 개요 보충은 SKILL.md 대신 workflow-setup의 Phase 3을 가리킨다.

narrative-writer와 consistency-checker 템플릿은 주 세션에 반환하므로 내부 용어를 유지한다.

## Alternatives considered

- **SKILL.md에 공통 규칙만 추가**: 예산·변경이 가장 작다. 그러나 구체적인 workflow 형식 지침 자체가 개발 용어를 요구하면 일반 규칙보다 우선한다. 템플릿 없는 기획·장 완료에서는 내부 검사를 그대로 전달하기 쉬우므로 둘 다 필요하다.
- **모든 템플릿을 새 참조 하나에 집중**(예: author-reports.md): 한 곳에서 관리하고 중복이 없다. 그러나 Reference Gate에 필수 파일이 늘고 절차 끝에 일어나는 보고 때문에 새 파일을 건너뛸 가능성이 크다. 템플릿 내용도 각기 달라 이미 읽은 workflow 안에 두는 편이 안정적이다.
- **블록 대신 workflow 전문 검사**: 범위가 넓다. 그러나 본문은 모델 내부 지침이므로 스크립트·필드가 필요해 예외만 많아진다. 작가용 부분을 표시하는 것이 최소 검증 범위다.
- **“계속 써”는 항상 확인 없이 본문 작성**: 방해가 가장 적다. 그러나 기획 직후에는 다음 기획 구간을 원할 수도 있다. 기본값 있는 한 문장 질문은 비용이 작고 잘못 한 장을 쓰면 추적을 롤백해야 한다.
- **첫 상세 개요 후 추적 초기화 유지**: 제1장 집필에서 한 단계를 줄인다. 그러나 기획기에 사실 상태를 만들면 project-files·실제 동작과 모순된다. workflow-chapter가 이미 진입 시 state 누락을 처리하므로 그 한 곳으로 통일한다.

## Consequences

- 이점: 작가는 이야기 차원의 설명과 바로 답할 질문을 받는다. 분량·결정·중단에 고정 질문과 추천 기본값이 있으며 새 템플릿에 개발 용어가 들어가면 정적 검사가 실패한다.
- 이점: 기획 후 계속 쓰기에 선택지 표가 뜨지 않고 추적 초기화 규칙이 하나가 된다.
- 비용: 예산을 명시적으로 올린다. SKILL.md 6900→7350, workflow-chapter 12300→13400, workflow-daily 11890→12250, workflow-setup 14700→14850, workflow-revision 2990→3100, project-files 4700→4800. 관련 경로도 `scripts/doc-budget.json`의 why에 따라 올린다. 사용자마다 매 세션 수백 자를 더 부담하는 대신 보고를 읽기 쉬워진다. 템플릿은 뼈대만 두고 긴 예시는 넣지 않는다.
- 비용: `author-report` 블록만 검사하므로 템플릿 밖 즉흥 보고는 일반 규칙에 의존한다. 금지 목록 방식이어서 새 개발 용어는 `AUTHOR_REPORT_JARGON`에 추가해야 한다.
