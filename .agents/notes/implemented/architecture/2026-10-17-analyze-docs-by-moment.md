# Agent Note: 장·단편 분석 자료를 작가 시점과 읽는 주체별로 재구성하고 스크립트와 정렬

Status: implemented
Date: 2026-10-17
Related: [분석 단계별 로드](2026-09-26-analyze-stages-by-moment.md), [집필 references 재구성](2026-10-17-write-references-by-moment.md), [장편 분석 계약 교정](../bug-fix/2026-10-15-polish-long-analyze-contracts.md), [단편 분석 교정](../simplification/2026-10-14-polish-story-short-analyze.md), [인계 계약 테스트](../testing/2026-10-17-handoff-contract-fixtures.md)

## Problem

집필 측 재구성 뒤 두 분석 스킬 감사에서도 같은 구조 문제가 나왔다.

- `manage_analysis_run.py`는 enhance에서도 누락 장을 `RAW` 배치로 계산하지만 pipeline-ops는 원문 읽기 0을 요구한다. `chunk_range`는 3장·2.5만 자 상한만 보는데 stage2-extraction·chapter-extractor는 긴 장·권 경계로 자유 분할하라고 한다. 문체 규약은 문장 길이 비율·`confidence: high`를 요구하지만 통계 스크립트가 없다. `--compact`는 문서가 보라는 장별 `missing_*` 키를 없앤다.
- 집필에서 Stage 3+ 보완·문체 누락으로 보내지만 장편 시점 표에는 보완/강화가 없고 영감 라이브러리 경로도 예산에 없다.
- deconstruction-notes는 클리셰 표만 유용하다. style-profile-protocol·generator가 반씩 설명하고 하위 활용법은 사라진 Gate D를 가리킨다. semantic-acceptance-fixtures는 final-checks만 참조하며 테스트가 쓰지 않는다. 단편이 장편 집필에서 가져온 인물·독자·기법 다섯 파일 약 33K 중 실제 필요한 것은 관계 네 유형·동기 사슬·반대 인물 네 요소·세 층 대비·연애 단계뿐이다. zhihu-style·deconstruction-examples는 어떤 단계에도 연결되지 않는다.
- 인계가 조용히 끊긴다. import는 보고서에 없는 세 절을 읽는다. 집필 전 회상은 감정 모듈 카드의 옛 이름 “读者需求、触发器、可替换要素、反抄袭提醒”을 읽지만 `inspiration_index.py` 필수 필드는 “读者想看什么、情绪链、戏剧单元、可替换项、不可照搬”이다. 节奏.md에는 “扩写技法” 열이 없고 단편 사건 노드는 위치가 없으며 장르 태그는 두 묶음이고 조사 추천 플랫폼을 집필이 인식하지 못한다.
- 단편 훅 개수 등 최소 차단 기준은 소비자가 없고 보충 불가 시 출구도 없어 import가 Stage 6을 요구하면 반복 실행할 수 있다. Stage 4–6 인물 척도 중첩은 35K를 넘지만 중첩 등록도 없다.

## Decision

**장편 분석(story-long-analyze)**

- SKILL.md 실행 규칙에 `{PYTHON}` 탐지 순서 python3·python·py -3, UTF-8 원문 `原文/原文.txt` 저장, 2만 자 미만이면 단편 권장(가져오기 호출은 안내 생략)을 넣는다. Stage 0–6 절은 단계별 요점으로 합친다. Phase 2를 표 둘로 바꾼다. `inspect_existing_assets.py`의 `recommended_path` 다섯 값별 처리(`continue_partial`은 누락 Stage 1 산출물 보완 후 `stage1` 표시)와 `stage_repairs` 코드별 복구다. `stage3_emotion`·`stage3_rhythm`·`stage6_style`은 파일 누락이라 다시 쓰고 접미사 없는 `stageN`은 완료 표시만 없어 파일이 유효하면 `mark-stage`만 한다. 감정 카드 필드 미비는 검사기가 누락으로 보고하지 않으므로 옛 파일 백업·문제 카드만 수정·`stage3` 표시를 Phase 2 끝에 쓰고 영감·마무리 검사에서 연결한다. 시점 표에 보완/강화·영감 라이브러리를 더한다.
- pipeline-ops의 enhance를 `manage_analysis_run.py` 실제 동작과 맞춘다. 장별 결과가 전부 있으면 원문을 안 읽고 누락 장은 여전히 `RAW` 배치다. `--compact`에서는 `semantic_coverage.missing_ranges`로 누락을 본다.
- Stage 2 분할은 계획을 따른다. stage2-extraction·chapter-extractor에서 자유 분할을 지우고 같은 순서·항목을 쓴다. 증거 A/B/C 정의는 Stage 3–5용 synthesis-inputs, 하위 에이전트용 chapter-extractor, 직접 배치 작성용 stage2-extraction 세 곳에 각 독자별로 둔다.
- style-profile-protocol을 generator에 합치고 삭제한다. 문체를 기계적 통계라고 하지 않는다. 결론마다 기존 자료/원문 근거/표본 부족 중 근거 한 줄을 쓴다. 문장 길이·구두점·문단 리듬은 최대 원문 근거 수준이며 영어 신뢰도 코드를 출력하지 않는다. 모방 불가 절을 모방 비권장으로 바꿔 보고서와 맞춘다. benchmark-style-load·style-resolution은 사용 가능한 문체·원문 근거·참고 기법만 읽고 `confidence: high`로 우선 채택하지 않는다.
- deconstruction-notes 클리셰 표를 stage3-plot-rhythm으로 옮기고 삭제한다. stage3 사건 필드·유형·검사는 각각 하나만 두고 포괄률은 사건 노드 기준이다. stage4 두 등급 표를 합치고 archetype·특수 능력 유형을 중국어로 바꾸며 가짜 수치 신뢰도를 없앤다. semantic-acceptance-fixtures와 final-checks 유지보수자 절을 삭제한다.
- author-facing 심층 분석 파일명을 고친다. 기본 정보는 검사 정규식이 “总章数：1200”을 인식하도록 필드：값의 행별 형식으로 바꾸며 하위 소비자가 읽어 원명을 유지할 절 목록을 명시한다. stage5는 `选题决策.md` 탐색 위치·되쓰기 형식을 설명한다.

**단편 분석(story-short-analyze)**

- 장르 척도는 SKILL의 13태그로 재배열하며 `genre_detected`는 그 값 또는 “通用”만 허용한다. 노드 템플릿에 `位置{第N节，约X字}`를 추가하고 유형을 기능으로 바꿔 집필 회상과 맞춘다.
- 차단은 작성 완전성만 본다. 필드 완비, `beats`에 시작/전개/절정/결말 포함, 유효 값이다. 개수는 0도 허용하고 실제대로 쓰며 원문에 없다고 명시해도 작성한 것으로 본다.
- 인물 다섯 파일은 analysis-characters로 합친다. 제목·소개·도입·유료 전환·플랫폼 형식은 새 analysis-submission에 두고 플랫폼을 submission-craft와 맞춘다. analysis-character-{basics,design,relations}, analysis-reader-profile, analysis-writing-techniques, analysis-paragraph-hooks, deconstruction-examples, zhihu-style을 삭제한다. 대화 다섯 등급은 stage4-6, 부당한 피해는 analysis-characters, 구경꾼은 훅 척도로 옮긴다. real-market-data는 short-scan만 남기고 공유 그룹을 없앤다.

**스킬 간 연결·검사**

- 장편 import는 실제 보고서 절을 읽는다. 집필 전 회상·benchmark-style-load는 감정 카드 필수 다섯 필드, 리듬은 “扩写方式” 등 실제 열, 단편 집필은 노드 위치·기능·사건을 읽는다. short-scan topic-match에 조사→집필 플랫폼 표를 더하며 뎬중은 “小程序”로 쓴다. 단편 import의 재사용 구조는 있는 만큼만, 없으면 원문에 없다고 쓴다. 단편 보고서 절 이름은 모두 「」로 묶어 인계 테스트가 다루게 한다.
- doc-budget에 장편 보완/강화·장편 영감·단편 완료 후 동종 비교/절별 리듬 세 경로를 추가한다. 단편 Stage 2–3·4–6 조건부 읽기에 stacking을 등록한다(최악 24.5K·29.4K). 삭제 파일 분기를 없애고 나머지는 실측에서 약 100자 여유로 조인다. `check-short-analysis-scope.py` 관찰 척도에 새 두 파일을 넣고 옛 인물·독자·기법 파일 재유입을 금지한다.
- 새 `scripts/test-handoff-contracts.py`를 static-check job에 연결한다.

## Alternatives considered

- **문장 길이 통계 스크립트로 `high` 유지**: 실제 근거가 생긴다. 그러나 `confidence: high`를 보고 채택하는 하위 소비자가 없어 아무도 안 쓰는 라벨을 위해 플랫폼별 계산·픽스처를 관리해야 한다. 가짜 설명을 지우고 표본량에 따라 med/low로 정하면 오해가 사라진다.
- **semantic-acceptance-fixtures를 scripts/bench로 보관**: 수동 예시를 남긴다. 그러나 아무 스크립트도 안 읽어 여전히 실행되지 않는 글이며 git 이력으로 충분하다.
- **인물·독자·기법 각 원명에 축약본 유지**: 예산·공유 목록 변경이 작다. 그러나 대부분 장편·집필 내용(대형 서사 Boss·남성향 연애 공략·빈칸 템플릿)이고 단편은 개념 다섯 개만 써 같은 시점에 두 파일을 더 읽게 한다.
- **analysis-paragraph-hooks 세 절을 모두 훅 척도로 이동**: 목적지가 단순하다. 그러나 대화 등급·부당한 피해는 훅이 아니며 같은 개념이 두 시점에 중복된다. 실제 사용 단계에 둔다.
- **최소 개수는 유지하고 보완 불가 출구 추가**: 증거를 더 찾게 한다. 그러나 집필은 `reversal_type`만 쓰고 나머지 개수는 비교용이다. 최소치는 척도의 고정 수 없음과 충돌하고 억지 훅이 비교를 오염시킨다.

## Consequences

- 이점: enhance·분할·누락 검사 설명이 스크립트와 같고 집필에서 보완 요청으로 보내도 대응 시점이 있다. 단편 자료 약 80.8K→42.5K, Stage 4–6 최악 중첩은 35K 초과→29.4K다. 인계 이름 변경은 테스트가 즉시 잡는다.
- 비용: `文风.md`의 `high`가 사라져 옛 프로젝트 설명이 달라지지만 하위는 이 필드를 안 읽어 동작은 같다. 단편 차단 완화·보고 구조 변경은 실제 전체 파이프라인 미검증이다. 아내 되찾기·달콤한 연애·서스펜스 각 한 편으로 보고 완전성·장르 묶음 대응·import 재실행 방지를 확인해야 한다. 장편 stage1 여성향 관계 경로·연애/가문 다툼 쾌감 형태는 자료 검증 없이 추가했다. chapter-extractor는 agents_version 36과 함께 배포하며 사용자가 재배포해야 적용된다.
