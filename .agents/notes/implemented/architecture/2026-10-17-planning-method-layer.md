# Agent Note: 기획 시점에 방법 계층을 분리하고 작업 패키지는 개요 작성법만 추출

Status: implemented
Date: 2026-10-17
Related: [작가 확인 지점별 새 책 시작](2026-09-26-opening-by-author-moments.md), [작가 시점과 독자별 장단편 references 재구성](2026-10-17-write-references-by-moment.md), [35K 로드 상한](2026-09-26-per-call-load-ceiling-35k.md)

## Problem

장편 권별·상세 개요 작성법은 주 절차가 읽지 않는 9개 파일에 흩어져 있었다. style-craft, plot-frameworks, commercial-core-methods, outline-structure-theory, plot-emotion-system, plot-special-topics, outline-conflict, outline-rhythm, character-design-methods다. 사건 단위 분량 기준 세 종류, 감정선 단계 표 다섯 개처럼 같은 내용을 여러 곳에서 다르게 설명했고 권 구조 작성법도 네 파일에 나뉘어 상호 참조했다.

9월 26일 작가 확인 지점별 분리 때 정한 방식 중 일부가 이번 재구성에서 문제가 됐다.

- 작업 패키지가 workflow-volume·workflow-outline 전체를 담아 주 세션 읽기 목록·역할 분담·작가 보고 템플릿까지 story-architect 컨텍스트에 들어갔다. 독자가 둘인 내용을 한 패키지에 섞었다.
- workflow-volume은 권별 개요 단계에서 전권 장 번호·단계 비율·단계별 리듬 공식의 “전권 분량·단계 개요”를 채우게 했다. 현재 권만 정밀 설계하는데 첫 권 단계에서 믿을 만한 전권 수치를 낼 수 없다.
- 권별 패키지는 항상 outline-methods의 여덟 지점과 emotional-methods의 “장편 단위 감정 엔진”을 포함해 주 비교 작품이 있어도 여덟 지점을 추가로 읽었다. 감정 엔진과 권 구조 방법도 두 파일에 갈라져 있었다.
- 작업 패키지 없는 story-architect 템플릿은 항목마다 “실행 시 profile에 따라 읽기”라고 해 문구대로라면 장르 목록·훅·서스펜스·반전·인물 궤적 전체 약 55K를 읽게 됐다.

## Decision

- **시점별 방법의 출처를 하나로 지정**: outline-methods는 권 구조·리듬을 담당한다. “권별 개요 작성법”은 매번 읽고 여덟 지점·감정 모듈 공식·무대 변경 세 절은 조건부로 읽는다. plot-core-methods는 상세 개요·장 수준 방법(목표 감정·주인공 선택, 쾌감 포인트 여섯 유형, 절정 구성, 전환 장, 도입 장치)을 담당한다. long-genre-mechanics는 핵심 소재·특수 능력, character-relations의 “감정선 단계”는 유일한 전권 감정선 표, genre-readers는 독자·플랫폼·작품명·소개·비교 작품을 담당한다. opening-design은 상세 개요 시점의 “도입 기획”과 제1–3장 집필의 “도입 집필”만 남긴다. 작가가 “늘어짐, 답답함, 성격 변화, 추독 하락” 같은 증상만 말할 때 원인을 찾는 revision-diagnosis를 새로 만든다. 기존 9개 파일의 고유 내용을 옮긴 뒤 파일과 agent-references 복사본 3개를 삭제한다.
- **절차 파일 내부를 두 절로 분리**: workflow-volume·workflow-outline을 “주 세션”(읽기 목록, 분업, 작가 보고)과 “개요 작성법”으로 나눈다. build_architect_brief의 권별 패키지는 workflow-volume의 작성법, artifact-protocols, outline-methods의 권별 작성법, reader-contract만 담는다. 상세 개요 패키지는 workflow-outline의 작성법과 plot-core-methods(첫 묶음은 전체, 이후 도입 장치 절 제외), 첫 묶음의 opening-design “도입 기획”을 담는다. 여덟 지점·감정 모듈 공식·무대 변경·감정선 단계는 끝의 조건부 읽기에 나열한다.
- **권별 개요 때 전권 장 번호를 정하지 않음**: `大纲/大纲.md`는 전권 개요와 권별 표로 바꾼다. 권마다 글자 수 범위·단계·기능·핵심 사건·시작/종료 상태·권 계약·결말 비축을 한 행에 쓴다. 목표 글자 수는 권 수×권별 글자 수로 추정하고 전권 장 번호·단계 비율은 미리 정하지 않는다. 척도는 workflow-volume의 “개요 척도” 한 곳에서 정의하며 artifact-protocols·배포 규칙 story-outline은 이를 가리킨다. story-import가 역추론한 大纲.md도 같은 형태다.
- **감정 엔진을 권별 개요 작성법에 통합**: emotional-methods에서 “장편 단위 감정 엔진”을 없애고 다섯 질문·강도 원칙을 outline-methods의 “사건 단위 설계”로 옮긴다. 인과 사슬은 권별 사건 단위 카드 필드에 남긴다. emotional-arc-design은 기대 관리·위험 부담·단편 글자 수 배분을 제거하고 “여섯 궤적 빠른 참조”만 남긴다. 단편 곡선·전환 위치는 단편 emotional-methods로 돌린다.
- **작업 패키지 없으면 profile 표만 따라 읽기**: story-architect 템플릿의 항목별 읽기 문장을 없애고 agent-reference-profiles를 행별로 판단해 작업 유형에 맞는 행만 읽으며 지정 절이 있으면 그 절만 읽는다. profile의 emotional-arc-design은 Common에서 Long으로 옮기고 female-audience-writing의 agent-references 복사본을 추가한다(장르 목록·핵심 소재 모두 연결). outline-conflict·outline-rhythm 행은 삭제한다. agents_version은 35 → 36이다.
- **실측 예산 등록**: 권별 패키지 24024 → 23228, 최악 중첩 31944 → 31557. 권별 주 세션 최악 중첩은 권별 작성법·조건부 세 절 추가로 32141 → 33701. 첫 상세 개요 패키지 19273 → 15532. 설정 확정 주 세션 최악은 특수 능력·감정선 단계 추가로 31827 → 32743. 단일 장·일일 집필 direct/solo에 “첫 세 장: 도입 집필” 중첩을 추가해 최악 34519, 34512다. 대규모 수정 direct/solo의 “작가가 증상만 말함”은 최악 34026이다. 패키지 없는 story-architect는 장르 포지셔닝(남성향/여성향), 권 구조, 새 책 도입, 구조 검토의 상호 배타적 다섯 분기로 등록하며 최대 19187이다. 모두 ≤35000이며 예외는 없다.

## Alternatives considered

- **패키지에 절차 전체 유지**: story-architect가 주 세션의 검수·보고 방식을 보면 전달이 더 잘 맞을 수 있다. 그러나 머리말에 반환할 항목을 이미 명시했고 작가 보고 템플릿은 하위 에이전트가 그 형식으로 답하게 할 뿐이다. 읽기 목록·보고 설명 약 1.3K도 추가된다.
- **주 세션 계층·방법 계층을 새 파일로 분리**: 독자가 가장 깔끔히 나뉜다. 그러나 workflow-volume·workflow-outline 이름은 작가 보고 검사, 계약 목록, 참조 관문, story-import 복사본에 고정돼 있다. 파일 내부 절과 절별 추출로 같은 효과를 낼 수 있다.
- **전권 분량·단계 개요를 유지하고 비율만 삭제**: 작가는 시작 때 전체 길이·단계 수를 보고 싶다. 그러나 첫 권에서 전권 장 번호를 정확히 정할 수 없고 적어 놓으면 후속 권을 제약한다. 권별 표의 글자 수 범위·단계가 이미 길이와 구성을 답한다.
- **예전 파일을 연결하지 않는 보관소로 유지**: 원문을 참조할 수 있다. 그러나 검색으로 발견돼 충돌하는 기준을 모델이 다시 읽을 수 있다. 원문은 git 이력에서 확인할 수 있으므로 남기지 않는다.

## Consequences

- 이점: 시점별로 읽는 권별·상세 개요 방법이 채울 템플릿 필드와 맞고 같은 일은 한 곳에서 설명한다. 패키지에는 방법만 들어가 작가 보고 템플릿이 하위 에이전트 컨텍스트에 들어가지 않는다. 주 비교 작품이 있으면 여덟 지점을 추가로 읽지 않는다. 패키지 없는 story-architect의 문자상 약 55K 로드는 최대 약 19K로 줄었다.
- 비용: 권별 주 세션 최악 중첩은 32141→33701로 늘고 단일 장·일일 집필 direct/solo는 약 34.5K에 가까워 후속 규칙 추가 전 공간을 확보해야 한다. 축소 과정에서 길게 쓰는 세 방법, 구원물 여덟 방법, 절정 분류 등 낮은 가치 항목을 제거했으며 git 이력을 기준으로 한다. agents_version 36의 새 템플릿·자료를 받으려면 기존 프로젝트에서 story-setup을 다시 실행해야 한다. skills-only 호스트는 업그레이드 전까지 프로젝트의 구복사본을 실행한다. 구조 변경 후 권별·첫 10장 상세 개요 블라인드 평가는 다시 실행하지 않았다. 병합 전에 2026-09-26 프로토콜로 현환·여성향 각 한 권을 추가 실행한다.
