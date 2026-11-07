# Agent Note: 장·단편 집필 references를 작가의 시점과 읽는 주체에 따라 재구성

Status: implemented
Date: 2026-10-17
Related: [새 책 시작을 확인 지점별로 로드](2026-09-26-opening-by-author-moments.md), [단편 시점별 로드](2026-09-26-short-write-by-moment.md), [장편 집필 문서 교정](../bug-fix/2026-10-14-long-write-doc-contract-gaps.md), [단편 집필 자료 교정](../simplification/2026-10-14-polish-story-short-write.md), [줄거리 계획 방법 계층](2026-10-17-planning-method-layer.md), [집필 핵심 경로와 AI 문체 제거 정렬](../simplification/2026-10-17-writer-hot-path-align-deslop.md), [분석 자료 재구성](2026-10-17-analyze-docs-by-moment.md), [순위 조사 자료 재구성](2026-10-17-scan-docs-by-moment.md), [나머지 스킬 재구성](2026-10-17-other-skills-by-moment.md), [인계 계약 테스트](../testing/2026-10-17-handoff-contract-fixtures.md)

## Problem

10월 14일 두 집필 스킬의 모든 references를 문장별로 교정했지만 유지보수자는 여전히 혼란스럽다고 느꼈다. 10월 17일 다중 에이전트 감사(5개 묶음별 정독, 검사 제약 조사, 웹소설 작업 흐름 관점, 종합·재검토)는 구조적 원인을 찾았다.

- 흐름 파일은 작가의 시점별, 방법 파일은 집필 강좌 출처별, 참조 색인은 Phase 1–5별이다. plot-frameworks·commercial-core-methods·style-craft는 저장소 전체에서 reference-index만 가리키는데 진입부는 본문 집필 때 색인으로 추가 읽기를 금지하여 주 흐름에서 방법을 읽지 못한다.
- 집필의 오래된 규칙은 AI 문체 제거 세 자료와 반대다. writing-craft는 “첫 번째는 충분히, 두 번째는 절반”, “가장 무거운 문장은 가장 짧게”를 요구한다. narrative-focus는 감소 횟수를 정하지 않으며 deslop-gates는 고정 문장 길이·상세 묘사 비율·가장 짧은 강박자로 검수하지 않는다. 집필자가 옛 규칙대로 쓰면 문체 정리에서 다시 되돌린다.
- 템플릿·검사기, 작업 묶음·흐름이 불일치한다. artifact-protocols 권 줄거리 템플릿을 그대로 저장하면 `outline_view.py --check --strict`가 범위 행 누락 14건을 보고한다. workflow-volume은 비교 작품이 없으면 outline-methods의 여덟 노드를 읽게 하지만 volume 묶음에는 그 파일이 없다. workflow-outline은 workflow-daily에 없는 보충 생성 흐름을 가리킨다. 단편 agent-calls는 short-craft를 따르라고 하지만 집필자의 agent-references에는 없다.
- 장·단편 공유 사본을 옮기며 불필요한 내용을 줄이지 않았다. 단편 훅 파일에 시스템 활성화·인스턴스 보상 같은 남성향 장편 예시, 장편 감정 곡선에 단편 분량 배분, 장편 도입 예시에 단편의 아내 되찾기 자료가 남았다.
- 같은 사항의 기준이 여러 곳에서 충돌한다. 감사에서 20개 넘는 묶음을 찾았다. 사건 단위 규모 세 기준, 연애 단계 표 다섯 개·이름 네 묶음, 단편 도입문을 느리게 재현하거나 반복 없이 이어가는 두 방식, 단편 플랫폼 네 목록 등이 있다.

## Decision

내용을 작가의 시점 × 읽는 주체로 배치한다. 시점마다 주 세션용 흐름 파일 하나와 방법 파일 최대 하나를 두고 작업 묶음·집필자 prompt의 원본으로도 쓴다. 검사가 고정한 파일명은 보존하고 내용을 옮긴다. 묶음마다 검사를 통과한 뒤 다음을 진행하며 agents_version은 이번 작업에서 한 번만 올린다(35 → 36).

1. **계약 연결 복구**: 권 줄거리 템플릿에 범위 행을 더해 그대로 `outline_view.py --check --strict`를 통과하도록 회귀 테스트한다. 세부 줄거리 누락·추적 설명 읽기 시점·작가 기억 검색 종류를 각각 통일한다. volume 묶음에 여덟 노드, outline 묶음에 장 시작·끝 훅 유형의 이름·공식 두 열만 넣는다. 단편 집필자 배정 때 주 세션이 장르 묶음 요점을 prompt에 쓴다. 지정 장 집필에 세부 줄거리가 없으면 그 장을 먼저 만들고 집필하며 보고에 알린다. 일일 연재 묶음에서는 그 장 직전에 멈춰 작가에게 묻는다. 기존 세부 줄거리에 필드만 없으면 기존 필드로 쓰고 되쓰지 않는다. 조립 스크립트의 장르 카드 선택은 가장 긴 일치부터 한다.
2. **사용되지 않는 방법 파일 정리와 계획 시점 계층화**: style-craft, plot-frameworks, commercial-core-methods, outline-structure-theory, plot-emotion-system, plot-special-topics, outline-conflict, outline-rhythm, character-design-methods의 고유 내용을 기준 파일로 옮긴 뒤 삭제한다. revision-diagnosis를 만들고 색인은 시점·증상별로 찾게 한다. workflow-volume·workflow-outline 내부를 주 세션/계획 방법 두 절로 나누고 묶음은 방법 절만 가져간다. 계획 척도는 한 곳만 정의한다. outline-methods는 권 구조·리듬, plot-core-methods는 세부 줄거리·장 단위 방법, long-genre-mechanics는 핵심 소재·특수 능력, character-relations는 연애선, genre-readers는 독자·플랫폼을 담당한다. 세부 줄거리의 다섯 부분은 유지한다. [계획 방법 계층](2026-10-17-planning-method-layer.md) 참조.
3. **본문 집필 핵심 경로와 문체 제거 정렬**: writing-craft, style-combat-face, long-suspense, emotion-on-page, dialogue-mastery의 상충하는 할당량을 판단 기준으로 바꾸고 파일별 A/B에서 퇴보하지 않아야 반영한다. 훅·감정 방법 예시는 장편 자료 원문으로 바꾼다. [집필 핵심 경로 정렬](../simplification/2026-10-17-writer-hot-path-align-deslop.md) 참조.
4. **단편 재구성**: writing-workflow→workflow-design, hooks-paragraph→hooks-chapter, short-prose-quality→workflow-revision으로 합치고 집필 측 output-contract는 삭제한다. submission-craft가 플랫폼·도입문·분량·유료 전환점의 유일한 원본이며 훅·반전 파일에서 장편 내용을 뺀다. 치마오 인기 단편 자료에 따라 도입문은 본문 시작인 약 150–300자로 정한다. 진행 중인 순간에서 멈추면 제1절이 이어지고 결말·결과까지 쓰면 제1절에서 과정을 회상할 수 있으며 장르로 나누지 않는다. 이로써 [9월 26일 결정](2026-09-26-short-write-by-moment.md)의 150–220자를 바꾼다. 장르 묶음은 도입문에서 무엇을 미리 밝힐지만 남긴다. 여섯 플랫폼 분량은 아라비아 숫자(자료 없는 판체·훙궈는 8000–12000)로 쓴다. 미선택 목표 플랫폼은 `未定`이며 구상 검사는 `未定`과 이전 명칭 “盐选”, “番茄短篇”도 받아들이고 “약 1–1.3만” 같은 표기를 정수로 환산한다. 본문 절 표시·따옴표는 `设定.md`의 플랫폼 기조만 보고, 없으면 `正文.md` 기존 방식, 그것도 없으면 `###1.`과 `""`를 쓴다. `check-reference-gates.js`는 형식 규약·장르 묶음이 submission-craft를 다시 가리키지 않도록 검사한다. hooks-chapter는 구상 중 유료 전환 위치가 불확실할 때 “2. 절 끝”만 조회하며 본문 집필에서는 읽지 않는다.
5. **분석·순위 조사·다른 스킬도 같은 방식으로 재구성**: 분석·조사는 각 노트, 가져오기·검토·문체 정리·배포·라우팅·표지·browser-cdp는 [나머지 스킬 재구성](2026-10-17-other-skills-by-moment.md)을 본다. 스킬 간 인계는 `scripts/test-handoff-contracts.py` 픽스처가 검사한다. [인계 계약 테스트](../testing/2026-10-17-handoff-contract-fixtures.md) 참조.

이번에 하지 않은 항목:

- short-craft를 장르 묶음으로 분할하지 않았다. 장르 묶음이 설명하지 않은 본문 기법을 보완하며 분할하면 열 장르의 집필법이 바뀌므로 장르별 짝지은 블라인드 평가가 먼저다. 이번에는 장편 내용만 뺐고 기본 집필법 역할은 유지하며 장르의 어조·도입·감정 강도가 우선한다.
- 집필자 템플릿의 같은 유형을 점차 줄이는 규칙은 본문 A/B가 필요해 유지했다.
- 제목·소개·플랫폼 우선 질문·데이터 기반 재작업 등 새로운 작가 상호작용은 추가하지 않았다.
- 문체 정리·검토·배포에서 집필자나 검토 출력을 바꾸는 항목(short-format을 원본으로 한 단편 형식 읽기, solo 검토의 장르 품질 목록 추가, Claude 규칙 추가 축소 등)은 A/B 이후로 남겼다. 목록은 [나머지 스킬 재구성](2026-10-17-other-skills-by-moment.md)의 Consequences에 있다.

## Alternatives considered

- **문장별 교정 반복**: 변경 범위가 작고 검사를 건드리지 않는다. 그러나 10월 14일에 이미 했고 문제는 파일 소유·로드 시점·규칙 충돌이다. 문장이 좋아져도 흐름에서 방법을 못 읽고 충돌은 남는다.
- **주 세션과 방법을 별도 파일로 분리**: 주체 구분이 가장 명확하다. 그러나 workflow-volume·workflow-outline 이름은 작가 보고 검사·계약 목록·참조 검사·story-import 사본이 고정하며 생성기가 이미 절 단위 추출을 지원해 내부 분리로 같은 효과를 얻는다.
- **옛 방법 파일을 보관 디렉터리로 이동하고 경로만 제거**: 원문을 참고할 수 있다. 그러나 스킬은 현재 상태만 설명하며 최상위 디렉터리를 추가하지 않는다. 남은 파일은 검색되어 충돌 규칙이 다시 읽힐 수 있다.
- **세부 줄거리 다섯 부분을 연결·전개·도착점 셋으로 변경**: 긴장이 낮은 장에 더 맞는다. 그러나 제거 실험에서 본문 품질을 좌우한 것은 목표 감정과 주인공 선택 두 필드다. 다섯 부분 변경 이득은 거의 없고 검사기·story-import·기존 줄거리 호환 비용이 든다.

## Consequences

- 이점: 각 시점의 방법과 템플릿 필드가 대응하고 집필·문체 정리가 되돌리기를 반복하지 않는다. 템플릿이 자체 검사를 통과하고 장·단편은 각자 자료만 보며 스킬 인계 이름이 바뀌면 CI가 즉시 실패한다.
- 비용: 삭제·병합에 맞춰 doc-budget·공유 자료 목록·agent-references·에이전트 템플릿·어댑터를 동기화했다. 사용자는 story-setup으로 도우미 버전 36을 다시 배포해야 적용되며 스킬만 설치하는 호스트는 업그레이드 전까지 옛 사본이다. 핵심 경로 밖은 보호 검사·픽스처만 통과했고 가져오기·문체 정리·검토·라우팅의 새 주 흐름은 실제 대화에서 더 실행해야 한다.
- 10월 14일 두 교정 노트와 9월 26일 두 시점별 로드 노트의 사실(작업 묶음에 전체 흐름 포함, 권 계획 시점에 전작 규모 기록 등)은 새 계획 방법 계층 노트에 별도로 썼다. 옛 노트의 결정을 반대로 고치지 않는다.
