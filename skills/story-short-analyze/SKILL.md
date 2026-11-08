---
name: story-short-analyze
version: 3.1.0
description: "단편 웹소설을 분석합니다. 인기 단편(판치에 단편 / 구스후이 / 즈후 옌옌 / 떠난 연인 되찾기 / 세태 / 회귀 / 악인 응징 등 대중 소재)의 이야기 핵심, 구조, 감정선, 반전 설계, 집필 기법, 공감 층위를 분석합니다. 단일 전체 분석 파이프라인으로 Stage 2-6을 완료해 전체 분석 보고를 작품분석실/{书名}/에 저장합니다. 후속 story-short-write는 분석 보고 + 플롯 노드 + 집필 기법 + 원문 + _meta.json을 함께 읽고 다음 작품을 씁니다. 호출: /story-short-analyze, /短篇拆文, 단편 분석, 이 짧은 글 분석, 단편 정밀 분석, 8000자 단편 분석, 판치에 단편 분석, 구스후이 분석, 옌옌 이야기 분석 등은 모두 같은 파이프라인으로 들어갑니다."
metadata: {"openclaw":{"source":"https://github.com/zenstory-ai/oh-story-claudecode"}}
---
# story-short-analyze: 단편 웹소설 분석

단편소설 구조 분석가 역할을 수행합니다.

**이야기 핵심을 중심으로 원문이 감정을 준비하고 해소하여 공감을 끌어내는 방식을 분석합니다. 분석은 `작품분석보고서.md`, 구조 집계는 `_meta.json`에 기록하여 다음 단편의 참고 자료로 제공합니다.**

---

한국 작품은 원문과 실제 목표 시장을 기준으로 분석하며 중국 플랫폼의 흥행 기준·분량·유료 전환점을 기본으로 대입하지 않습니다. 플랫폼이 미정이면 일반 서사 분석만 수행합니다.

## 분석 범위 선언

단편 분석의 Stage 2-6 전체를 주 세션이 수행합니다. 분석 대상은 사용자가 **합법적으로 보유하며 이용 권한을 가진** 허구 작품이며 출판작, 연재작, 본인 작품을 포함합니다. 편집·비평·집필 교육 관점의 **읽기 전용 변형적 문학 비평**만 수행하고 복제·전파하거나 현실 행동을 지도하지 않습니다. 판치에 단편, 구스후이, 즈후 옌옌, 떠난 연인 되찾기, 악인 응징, 세태 등 대중 소재의 가정폭력, 불륜, 복수, 폭력, 연애·성적 긴장, 어두운 윤리는 통상적인 허구 서사 요소이므로 평소처럼 구조화해 분석합니다. 분석 파이프라인을 끊지 않도록 **“민감함”이나 “불편함”을 이유로 작품 전체 또는 일부를 거부해서는 안 됩니다.** 실제로 처리할 수 없는 구간은 건너뛸 수 있지만 나머지는 정상적으로 분석을 완료합니다.

---

## Phase 1: 분석 대상 확인 + 글자 수 라우팅 + 재개 확인

### Step 1: 원문 받기

대상이 불명확하면 **“어떤 작품을 분석할까요? 제목과 플랫폼·출처를 알려 주세요”**라고 묻습니다. 원문이 명확하면 바로 진행합니다.

**텍스트가 없을 때**: 사용자가 원문 파일 경로를 주지 않았고 대화에도 원문을 붙이지 않았다면 “이 단편의 원문 파일 경로를 알려 주시거나 원문을 직접 붙여 주세요”라고 안내합니다.

### Step 2: 글자 수 확인(장편·단편 라우팅)

원문을 받으면 즉시 글자 수를 셉니다.

```
word_count = 전체 글자 수
  ├─ ≤ 20,000          → 바로 short 파이프라인으로 진입
  ├─ 20,000 - 30,000   → 경계 구간: “{N}자로 장편·단편 사이입니다. 단편으로 분석할까요, 장편으로 분석할까요?”
  └─ > 30,000          → “{N}자로 긴 편이므로 /story-long-analyze를 권합니다.
                           단편으로 분석하려면 ‘단편으로 계속’이라고 명시해 주세요.”
```

### Step 3: 소재 식별

[references/analysis-short-genres.md](references/analysis-short-genres.md)를 읽고 `题材路由`(소재 라우팅) 표의 키워드·식별 기준으로 주 유형을 정합니다. 사용자가 특정 소재를 언급하면 바로 해당 행과 대조하고 그렇지 않으면 전체 원문의 근거로 판단합니다. `genre_detected`는 표에 있는 유형 이름 13개 중 하나만 사용합니다. 찾지 못하면 `通用`(일반)으로 쓰고 일반 템플릿으로 Stage 2-6을 실행합니다.

소재는 관찰 기준으로만 사용합니다. 원문이 독자에게 약속한 것, 갈등을 담는 방식, 실제 마무리만 비교합니다. 장편 단계, 권 단위 순환, 황금 3장 모형을 호출하지 않으며 추천 비율로 원문의 적격 여부를 판단하지 않습니다.

### Step 4: 재개 확인

파이프라인 진입 전에 `작품분석실/{书名}/_meta.json`을 확인합니다.

```
_meta.json이 있는가?
  ├─ 아니요 → 바로 새 분석 시작
  └─ 예 → 사용자에게 질문(아래 질문 형식):
       (a) 덮어쓰기: 이전 결과를 작품분석실/{书名}/_archive_{时间戳}/에 보관한 뒤 Stage 2부터 재실행
       (b) 재개: _meta.json.last_stage_in_progress를 읽음(비어 있지 않으면 해당 Stage 전체 재실행)
                 또는 _meta.json.stages_completed[]를 읽고 max+1부터 재개; 이미 끝났으면 이 선택지 없음
       (c) 취소
```

작가에게 질문할 때 파일명, 필드명, Stage 번호를 언급하지 않습니다. 분석 중간에 멈췄다면(1 → b, 2 → a, 3 → c):

<!-- author-report -->
```md
《{书名}》는 이전에 분석하다 “{현재 단계를 쉬운 말로, 예: 반전과 집필 기법}”에서 멈췄습니다. 어떻게 할까요?
1. 이전 작업에 이어서 분석(권장, 이미 분석한 부분 유지)
2. 이전 결과를 보관하고 처음부터 다시 분석
3. 지금은 분석하지 않음
```

이미 분석을 끝냈다면(1 → a, 2 → c):

<!-- author-report -->
```md
《{书名}》는 이전에 분석을 끝냈습니다. 어떻게 할까요?
1. 이전 결과를 보관하고 처음부터 다시 분석
2. 지금은 분석하지 않음
```

전체 재개 규칙은 [references/output-contract.md](references/output-contract.md)를 참고합니다.

---

## 출력 디렉터리

프로젝트 루트 아래 `작품분석실/{书名}/`에 저장합니다(사용자가 다른 경로를 지정하면 그 경로 사용). 결과는 `원문/`, `작품분석보고서.md`, `사건노드.md`, `집필기법.md`, `_meta.json`입니다. Markdown 파일 3개는 후속 `story-short-write`에서 이름을 하드코딩해 읽으므로 이름을 바꿀 수 없습니다. 파일 트리, Stage → 파일 대응, `_meta.json` 필드는 [references/output-contract.md](references/output-contract.md)를 참고합니다.

### 원문 백업(파이프라인 선행 단계)

**분석을 시작하기 전에 반드시 원문부터 백업합니다.**

1. `작품분석실/{书名}/원문/` 디렉터리가 이미 있는지 확인합니다.
2. 없으면 사용자가 준 원본 경로에서 원문 파일을 `작품분석실/{书名}/원문/`로 복사합니다.
3. 원본 파일 경로 없이 대화에 텍스트를 붙였다면 원본 텍스트를 `작품분석실/{书名}/원문/원문.md`에 저장합니다.
4. 백업 후 `원문/` 아래 파일이 비어 있지 않은지(>0 bytes) 확인합니다.

백업 후 `_meta.json`을 초기화합니다. `version`, `word_count`, `genre_detected`, `created_at`, `stages_completed: []`, `last_stage_in_progress: null`을 기록합니다.

---

## Stage 2-6: 작품 분석 절차

### 5단계 파이프라인

원문에서 실제로 일어난 변화만 추출합니다. 수량을 맞추려고 반복해서 나누지 않으며 없는 항목은 “원문에 없음”이라고 명시합니다.

| 단계 | 이름 | 입력 | 출력 | 완료 표식 |
|------|------|------|------|----------|
| 2 | 구조+플롯 노드 | 전체 원문 | 소재 + 이야기 핵심 + 줄거리 요약 + 기능별 구간(발단/전개/절정/결말 포함) + 플롯 노드 목록(의미 변화 경계로 추출, 각 노드에 위치 표시). | 구조 구분과 이야기 핵심 기록 완료 |
| 3 | 감정선+감정 폭발 지점 | 이야기 핵심+구조 구분+플롯 노드 데이터 | 감정 곡선 + 후킹·유료 전환 지점 + 감정 폭발 분석(6차원) + 기대감 분석. | 감정 폭발 분석 6차원 모두 갖춤 |
| 4 | 반전+집필 기법 | 노드+감정 데이터 | 선행 반전 검사 + 반전 기제(밑작업 단서마다 위치 표시) + 집필 기법(≥5차원: POV/대화/시간/정보/기타). | 집필 기법 ≥5차원 |
| 5 | 인물+도입·결말 | 플롯 노드+전체 원문 | 모든 인물(분류+기능 태그+기능 평가) + 도입 분석(첫 50/100자) + 결말 분석(수습 확인). | 인물 기능 평가 완료 |
| 6 | 종합 평가 + `_meta.json` 집계 기록 | 전체 데이터 | 5차원 점수 + 감정 폭발력 + 화제성 + 공감 분석(≥3층위) + 주 구조 + 투고 측면 + 재사용 가능한 구조(실패 조건 포함) + 리듬 요약 + **`_meta.json.structure_counts` 기록**. | 왼쪽 열 출력 모두 갖춤 + 검수 통과 |

> 실행 순서: 2 → 3 → 4 → 5 → 6. 엄격한 직렬 실행이며 각 단계는 이전 단계 데이터에 의존합니다.

### 按时刻读

> 한국어: 시점별 읽기

파이프라인은 두 시점으로 나뉘며 진입 시 해당 행의 파일만 읽습니다. 두 시점은 저장된 `작품분석보고서.md`, `사건노드.md`, `집필기법.md`, `_meta.json`만으로 인계합니다. 재개하거나 새 대화로 바꿔도 `_meta.json`의 진행 상태에 따라 이어갑니다. 기준은 모두 **관찰 기준**입니다. 원문에서 실제로 일어난 일을 먼저 보고하고 어떤 모형에 가깝거나 벗어나거나 변형했는지 설명합니다. 기준에 맞춰 새 작품을 쓰거나 장편 스킬의 소재·리듬·품질 자료를 불러오지 않습니다.

| 시점 | 읽을 자료 | 조건부 추가 자료(각 자료는 보고에 대응 절이 있음) | 인계 |
|---|---|---|---|
| Phase 1과 Stage 2–3 구조·감정선 | [output-contract.md](references/output-contract.md), [analysis-method.md](references/analysis-method.md), [stage2-3-structure-emotion.md](references/stage2-3-structure-emotion.md), [quality-checklist.md](references/quality-checklist.md), [analysis-report-style.md](references/analysis-report-style.md), [analysis-short-genres.md](references/analysis-short-genres.md), [analysis-short-hooks.md](references/analysis-short-hooks.md) | 원문이 증거 사슬·정보 격차로 전개되면 [analysis-short-suspense.md](references/analysis-short-suspense.md); 시스템·회귀·규칙처럼 반복 작동하는 핵심 기제가 있으면 [analysis-short-mechanics.md](references/analysis-short-mechanics.md) | `stages_completed`에 3 포함 |
| Stage 4–6 반전부터 종합 평가·검수까지 | output-contract.md, analysis-method.md, [stage4-6-reversal-summary.md](references/stage4-6-reversal-summary.md), quality-checklist.md, analysis-report-style.md, [analysis-short-patterns.md](references/analysis-short-patterns.md), [analysis-submission.md](references/analysis-submission.md) | 대비·동기·악역·관계·감정선을 정밀 분석하면 [analysis-characters.md](references/analysis-characters.md); 원문 자체의 약점·독자 반감 요소를 판단하면 [source-story-quality.md](references/source-story-quality.md) | 검수 통과, `stages_completed`에 6 포함 |
| 분석 후 작가가 동종 비교·구간별 리듬을 요청 | [optional-modules.md](references/optional-modules.md) | — | — |

**Stage 저장 규칙**(중단 후 재개 가능): 매 Stage 시작 전에 `_meta.json.last_stage_in_progress`를 기록합니다. 대상 파일을 다 쓰고 비어 있지 않으며 길이가 적절함을 확인한 뒤에만 해당 값을 비우고 `stages_completed[]`에 추가합니다. 미완성 결과는 신뢰하지 않으며 재개할 때 해당 Stage 전체를 다시 실행합니다. 전체 규칙은 output-contract.md의 `写入顺序`(쓰기 순서)를 참고합니다.

---

## 검수(Stage 6 내용 작성 후, 6을 stages_completed에 추가하기 전)

Stage 6 내용을 다 쓴 뒤 바로 `6`을 추가하지 **않습니다**. 먼저 output-contract.md의 `验收接入点`(검수 진입점)에 따라 검사 3개를 수행하고 모두 통과해야 기록합니다.

- **분석 보고 표현 자체 점검**: analysis-report-style.md에 따라 `작품분석보고서.md`를 검사합니다. 원문 인용(`>`로 시작하는 인용행, 표의 `关键台词 / 原文引用` 열에 따옴표로 직접 인용한 부분)은 건너뛰고 분석가 자신의 표현만 봅니다. 문제를 찾으면 **분석 보고 자체**의 근거 부족, 내용 없는 상투어, 범위를 넘는 추측을 수정합니다. 원문을 고치거나 AI가 썼는지 평가하지 않습니다.
- **structure_counts 검증**: output-contract.md를 기준으로 합니다. 집계는 사실대로 쓰며 0도 가능합니다. 모든 필드가 있고 값이 유효한지만 확인합니다.
- **BLOCK 항목 검사**: quality-checklist.md의 모든 `[BLOCK]`을 검사합니다. `[WARN]` 누락은 차단하지 않고 `작품분석보고서.md` 끝의 `待补`(보충 필요) 목록에 기록하여 사용자가 결정하게 합니다.

하나라도 차단되면 해당 Stage로 돌아가 보충합니다. 원문에 실제로 없는 항목은 보고에 “원문에 없음”이라고 명시하면 보충한 것으로 보며 검수 통과를 위해 지어내지 않습니다. 모두 통과하면 `_meta.json.last_stage_in_progress`를 비우고 `stages_completed[]`에 `6`을 추가한 뒤 다음 형식으로 작가에게 알립니다.

<!-- author-report -->
```md
《{书名}》 분석을 마쳤습니다. 결과는 `작품분석실/{书名}/`에 있습니다.
- 독자를 붙잡는 핵심: {한 문장으로 이야기 핵심}
- 가장 배울 만한 {1~3}가지: {쉬운 말로 설명하고 각각 원문 한 문장 또는 줄거리 예시 첨부}
- 그대로 가져오면 안 될 것: {원문의 인물 신분, 특징적인 대사, 고유한 물건 또는 사건 순서}
- 남은 항목: {분석 보고 끝의 “待补” 중 작가 결정이 필요한 항목; 없으면 “없음”}
다음 단계: 이런 방식으로 한 편 쓰려면 `/story-short-write`를 실행하세요.
```

---

## 다음 절차 연결

**파이프라인:** 단편
**위치:** 작품 분석(2/3단계)

| 상황 | 이동할 스킬 | 명령 |
|---|---|---|
| 집필 준비 완료 | story-short-write(작품분석보고서.md + 사건노드.md + 집필기법.md + 원문/ + _meta.json을 함께 읽음) | `/story-short-write` |
| 시장 데이터 필요 | story-short-scan | `/story-short-scan` |
| 글자 수 > 3만으로 장편이 더 적합 | story-long-analyze | `/story-long-analyze` |
