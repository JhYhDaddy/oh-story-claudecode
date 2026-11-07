# Agent Note: 장·단편 분석을 단계별 시점으로 나누어 해당 시점의 규칙만 읽기

Status: implemented
Date: 2026-09-26
Related: [35K 로드 상한](2026-09-26-per-call-load-ceiling-35k.md), [작가 확인 지점별 새 책 시작](2026-09-26-opening-by-author-moments.md), [주 세션에서 내용 중계 금지](../simplification/2026-09-24-long-analyze-no-relay-and-digest.md)

## Problem

두 분석 스킬의 진입부가 단계별 읽을 자료를 지정하지 않아 모델이 방법과 템플릿을 통째로 읽었다.

- **장편**: SKILL.md 8.4K의 마지막 문장이 pipeline-ops(7.6K), output-templates(15.1K), material-decomposition(13.0K)를 함께 지정한다. Stage 3–5는 author-facing(4.3K)까지 약 48K이며 digest로 가져올 자료는 제외한 값이다. Stage 1은 자체 절이 없고 템플릿은 output-templates 중간에 숨었다. Stage 3 절에는 집계 방법 링크가 없다. 드문 분기(장 번호 불일치의 세 선택지, 약 700자), pipeline-ops와 중복인 계획·제출·분할 설명, 유지보수자만 쓰는 회귀·의미 검증 예시가 상주한다. Stage 1 질문에서는 작가에게 순차·제한 병렬·순서 무제한 중 배분 방법을 고르게 하는데 이는 기술적 선택이다.
- **단편**: Stage 2–6을 한꺼번에 처리하며 필수 다섯 파일(output-contract, output-templates, material-decomposition, source-story-quality, analysis-report-style)과 SKILL은 약 42.5K, 본문까지 약 60K다. output-contract의 집필 측 활용법·유지보수자 스모크 테스트도 계속 읽고, SKILL.md의 검수 네 단계는 output-contract의 검수 접점과 중복된다.

단계 사이에 필요한 것은 저장된 산출물과 진행 정보(장편 `_progress.md`의 단계 상태와 `mark-stage`, 단편 `_meta.json`의 `stages_completed`)뿐이며 이전 단계의 작업 설명은 필요 없다.

## Decision

- **장편 Stage별 분리**: SKILL.md에 시점별 읽기 표를 추가한다. 도입 세 장(Phase 1–2, Stage 0–1)은 `stage1-golden-chapters.md`, Stage 2는 `pipeline-ops.md`와 하위 에이전트 불가 시 `stage2-extraction.md`, Stage 3/4/5는 `synthesis-inputs.md`(digest 자료 조회·단계 표시·종합 단계 사실 보존)와 해당 `stage3-plot-rhythm.md` / `stage4-characters-settings.md` / `stage5-report.md`, Stage 6은 `style-profile-generator.md`(Stage 6 필드 요약 통합), 전체 완료 시 `final-checks.md`를 읽는다. output-templates.md와 material-decomposition.md는 내용을 단계별로 옮긴 뒤 삭제한다. Stage 1은 진입부 자체 절을 갖는다.
- **장편 진입부 축소**: 장 번호 불일치 세 선택지와 원문 변경 세칙은 `index-rebuild.md`로 옮겨 스크립트가 멈출 때만 읽는다. Stage 2는 pipeline-ops 링크 문단만 남긴다. 유지보수자 회귀·의미 검증 예시는 `final-checks.md`의 유지보수자 회귀 절로 옮긴다.
- **배분 방식 기본 결정**: Stage 2는 제한 병렬(회당 3배치)을 기본으로 하며 질문 템플릿에서 세 방식을 나열하지 않는다. 작가가 속도·안정성을 물으면 author-facing의 새 설명으로 안내하고 전환한다. 세 방식 자체와 story-import의 제한 병렬 자동 재개는 유지한다.
- **단편 두 시점**: Stage 2–3은 output-contract, `analysis-method.md`(두 시점 공통 분석법), `stage2-3-structure-emotion.md`, `quality-checklist.md`(단계별 목록·품질 기준, BLOCK 검색 근거), analysis-report-style을 읽는다. Stage 4–6은 단계 파일을 `stage4-6-reversal-summary.md`로 바꾸며 Stage 6 원문 품질 평가 때 source-story-quality를 더한다. 같은 유형 비교·플랫폼 적합성·상세 리듬은 `optional-modules.md`로 옮긴다.
- **단편 기준 통일**: 반전 복선은 단일 기준인 output-contract에 따라 ≥3개이며 무반전/응보형은 검사하지 않는다. 진입부 흐름 표, Stage→파일 표, stage4-6 방법·품질 목록을 같은 문구로 맞춘다(검사 스크립트는 없다). `character_archetypes`에 세는 대비 인물의 최소 조건은 세 층 라벨 중 하나 이상이 다른 둘과 반대이고 원문 행동 대비가 있는 것이다. Stage 5에서 대비 기법을 세분할 때만 analysis-character-design의 해당 제목 절을 읽는다.
- **단편 중복 제거**: SKILL.md 검수는 이 스킬 고유 사항(표현 검사에서 원문 인용 제외, 무반전 허용, quality-checklist에서 BLOCK 검색, 보완 불가 시 이야기 언어로 설명)과 완료 보고만 남긴다. 절차는 output-contract의 검수 접점을 따른다. 출력 트리·Stage→파일 표·저장 규약도 output-contract를 가리킨다.
- **output-contract 축소**: 공유 원본(story-short-write)에서 하위 소비 규약·집필 절차 제안·유지보수자 로컬 스모크 테스트와 유지보수자용 sync-policy·버전 세칙을 삭제한다. 구상에 필요한 활용법(`_meta.json` 선택 사항, 반전 유형별 뼈대 선택, 사건 노드로 리듬 배열, 기법·원문에서는 쓰는 방법만 학습)은 benchmark-recall의 한 문단으로 합치고 별도 파일을 만들지 않는다. shared-references로 두 사본을 동기화한다. 검수 접점 세 단계는 진입부와 같다. 표현 검사 적중 시 분석자가 보고서 자체를 수정하고, 로컬 품질 목록의 BLOCK을 검색하고, 통과 후 SKILL의 완료 보고로 작가에게 알린다.
- **보호 검사**: check-current-skill-contracts에 `analyze-moment-routing`(두 진입부 표가 각 시점 파일을 링크)과 `analyze-dispatch-default`(질문 템플릿에서 작가에게 배분 방식 선택 금지)를 추가하고 test-current-skill-contracts에 정상·실패 회귀 사례를 둔다. 기존 기준점(pipeline-ops 배분 목록·schema_version, SKILL 장 번호 연속 검사, 소재 결정 Phase, author-facing 템플릿 기술 용어, 단편 관찰 척도 경로)은 원래 파일 또는 옮긴 내용에 유지한다.

| 시점(주 세션 규칙, 공백 제외 문자 수) | 변경 전 | 변경 후 |
|---|---|---|
| 장편 도입 세 장(Stage 0 포함) | 27.8K | 14.4K(장 번호 불일치 15.8K) |
| 장편 Stage 2 | 20.3K(직접 배치 작성 48.4K) | 17.0K(직접 배치 작성 22.6K) |
| 장편 Stage 3 | 48.4K | 25.4K(클리셰 어휘표 조회 29.5K) |
| 장편 Stage 4 / 5 | 48.4K | 18.3K / 15.0K |
| 장편 Stage 6 | 32.2K | 16.6K |
| 단편 Stage 2–3 | 42.5K | 20.1K |
| 단편 Stage 4–6 | 42.5K | 26.9K(원문 평가 31.1K, 인물 척도 각 하나 32.7–33.2K, 가장 큰 집필 기법 표 분기 34.9K) |

변경 전은 진입부가 실제 지정한 파일 기준이며 Stage 3–5와 단편은 각각 같은 전체 자료를 읽었다.

## Alternatives considered

- **파일을 나누지 않고 절만 정확히 지정**: 파일 수·변경 범위·git 이력을 유지한다. 그러나 모델은 파일 전체를 Read하므로 절 지정으로 실제 로드를 제한하지 못한다. 두 큰 파일이 모든 단계를 포괄해 매 시점 15K+13K를 지불한다.
- **단편도 Stage마다 한 시점**: 매번 읽는 양은 최소다. 그러나 본문 5000–15000자이며 Stage 2–3(감정 곡선과 노드), Stage 4–6(인물·종합 평가와 반전·기법)은 내부 의존성이 강하다. 다섯 시점의 인계 비용이 절약량보다 크며 두 시점으로도 35K 이하다.
- **쉽게 설명하고 배분 방식은 작가가 선택**: 속도·안정성 취향은 다를 수 있다. 그러나 동시성과 이어가기의 기술적 절충을 작가가 판단할 근거가 없다. 미선택 기본값도 이미 제한 병렬이며 질문하면 전환할 수 있다.
- **output-contract의 하위 활용법을 유지하고 분석에서 해당 절 생략**: 공유 계약을 그대로 둔다. 그러나 생략은 모델의 자율에 기대고 파일 전체는 여전히 문맥에 들어온다. 집필 활용법은 집필 측에 두는 것이 맞다.

## Consequences

- 이점: 장편 시점별 ≤25.4K(분기 포함 ≤29.5K), 단편 두 시점 ≤27K(분기 ≤35K)다. Stage 1 진입 절이 생기고 드문 분기·유지보수 자료가 상주하지 않으며 작가에게 기술적 선택을 요구하지 않는다. 저장 파일만으로 인계하므로 재개와 새 대화가 같은 경로다.
- 비용: 장편 참조는 9→14개, 단편 핵심은 5→6개이며 단계에 따라 찾아야 한다. 시점별 표가 경로 계약이 되어 단계 파일 추가 시 진입부도 갱신해야 한다(새 검사가 감시). 단편 Stage 4–6에서 analysis-writing-techniques 전체를 읽으면 정확히 35.0K여서 제목으로 표 하나만 찾도록 한다. 해당 단계 파일에 추가하려면 같은 분량을 먼저 빼야 한다. 모든 시점·인물 척도 분기는 doc-budget에 등록했고 Stage 5 인물 척도는 한 번에 하나만 읽는다.
- 동작: 단계 번호·스크립트 명령·검수·인계는 같다. 관찰 가능한 유일한 변화는 Stage 1 질문에서 세 방식을 나열하지 않고 회당 세 구간씩 계속한다는 것이다. 실제 모델 대조 평가는 하지 않았다.
