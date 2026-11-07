---
name: story-long-analyze
version: 1.0.0
description: "장편 웹소설을 분석합니다. 황금 3장, 장별 요약, 줄거리, 감정, 리듬, 인물, 설정, 문체 인터페이스를 유지하며 연속된 장 묶음으로 인과관계, 이중 시간선, 관계, 3차원 리듬을 분석합니다. 기존 결과 직접 사용, 필요에 따른 보강, 중단 지점 재개를 지원합니다. 선택형 3층 영감 라이브러리 파이프라인(영감 라이브러리, 여러 책의 영감 통합, 영감 라이브러리 업데이트)을 포함합니다. 호출: /story-long-analyze, /长篇拆文, 이 책 분석해 줘, 황금 3장 분석, 심층 분석, 전체 분석 또는 소설 텍스트 파일 경로 제공."
metadata: {"openclaw":{"source":"https://github.com/zenstory-ai/oh-story-claudecode"}}
---
# story-long-analyze: 장편 웹소설 분석

웹소설 구조 분석가 역할을 수행합니다.

**핵심 원칙: 기계적 색인은 한 번 만들고 재사용합니다. 정상 추출에서는 각 원문 묶음을 한 번만 읽어 장별 사실과 장 사이 관찰을 함께 만듭니다. 실패 재시도는 계획에 따라 다시 읽으며 종합 단계에서는 저장된 결과를 재사용합니다.**

> 에이전트 호환성: 현재 호스트의 에이전트만 확인합니다. ZCode는 플러그인이 등록한 같은 이름의 역할을 확인하고 실제 스키마에 따라 `Agent`로 배정하며 `.zcode/agents`는 필요하지 않습니다. 역할·도구가 없거나 호출이 실패할 때만 solo/direct로 전환하고 `Fallback: project custom agents unavailable -> solo`를 보고합니다. 다른 CLI의 디렉터리를 검색하거나 호스트 이름만으로 일률적으로 전환하지 않습니다.
>
> 생성 버전 안내(생성을 차단하지 않음): 프로젝트 루트 `.story-deployed`의 `agents_version`부터 읽습니다. 현재 `agents_version: 38`과 다르면(표식 없음, 필드 없음·정수 아님, 38보다 작거나 큼) 照常按当前宿主角色来源检查并 spawn — 평소처럼 현재 호스트의 역할 출처를 확인하고 생성합니다. 동시에 `Notice: agents bundle 版本不匹配（项目 {N}，本版 38）`를 보고하고 `/story-setup`을 다시 실행한 뒤 새 대화를 시작하도록 안내합니다. 大于 38 时额外提示先更新 oh-story-claudecode — 38보다 크면 oh-story-claudecode부터 업데이트하라고 추가로 안내하며 로컬의 이전 setup으로 덮어써 다운그레이드하면 안 됩니다. 只有当前宿主角色缺失或不暴露调用能力时才降级 solo/direct — 현재 호스트 역할이 없거나 호출 기능을 제공하지 않을 때만 solo/direct로 전환합니다.

## 분석 경계

1. 읽을 수 있는 원문과 기존 자료로만 결론을 내립니다. 없는 내용은 “알 수 없음” 또는 “텍스트에 명시되지 않음”으로 씁니다.
2. 명확한 사실에는 장, `source_locator` 또는 5–15자의 위치 확인 어구를 붙이고 추론에는 근거 수준을 표시합니다.
3. 객관적인 발생 순서, 텍스트의 공개 순서, 독자가 아는 내용, 인물이 아는 내용을 구분합니다.
4. 사건 전개, 독자 감정, 분량 배치를 따로 분석하며 점수로 설명을 대신하지 않습니다.
5. 추상적인 기제만 옮기며 고유 설정, 인물 조합, 핵심 사건 사슬, 특징적 장면, 원문 문장을 복제하지 않습니다.
6. 필드를 채우려고 사실을 지어내거나 결과를 거꾸로 추론해 인물에게 처음부터 계획이 있었다고 만들지 않습니다.

## 작가에게 설명하기

대화 답변, `빠른미리보기.md`, `작품분석보고서.md`, 인물 관계도는 [references/author-facing.md](references/author-facing.md)에 따라 작성합니다. 작품 속 사건, 읽기 경험, 참고할 집필 방식을 명확히 설명합니다. 내부 필드, 명령, 품질 지표는 실행 자료에만 두고 번호에는 이름을 붙입니다. 스크립트가 `author_message`를 반환하면 설명과 선택지를 전달합니다.

## 실행 규약

- `{PYTHON}`: `python3`, `python`, `py -3` 순으로 시도해 처음 실행되는 것을 사용합니다. `{story-long-analyze skill 根}`은 이 파일의 디렉터리이며 `{拆文目录}`는 `작품분석실/{书名}/`입니다.
- 처음 분석하는 책은 작가가 준 TXT를 `{拆文目录}/원문/원문.txt`로 저장합니다. UTF-8이 아니면(흔히 GBK) 먼저 UTF-8로 변환합니다. 그렇지 않으면 하위 에이전트가 행 번호로 읽을 때 글자가 깨집니다.
- 전체가 2만 자 미만이거나 장 제목을 인식하지 못하면 대개 단편이므로 `/story-short-analyze`를 권합니다. 작가가 장편을 고집하거나 가져오기에서 호출했다면(분량을 이미 확정함) 정상적으로 장편 분석을 진행합니다.

## 按时刻读

> 한국어: 시점별 읽기

각 단계에 진입할 때 아래 표의 해당 설명만 불러옵니다. 재개·새 세션은 저장된 결과물과 `_progress.md`의 단계 상태로 연결합니다. [references/author-facing.md](references/author-facing.md)는 매 시점 필요에 따라 사용합니다.

| 시점 | 읽을 자료 | 인계 |
|---|---|---|
| Phase 1–2, Stage 0–1 첫 3장 | 이 파일 + [stage1-golden-chapters.md](references/stage1-golden-chapters.md); 원문이 바뀌거나 장 번호가 맞지 않으면 [index-rebuild.md](references/index-rebuild.md) 추가 | 황금 3장·빠른 미리보기를 저장하고 `stage1` 표시 |
| Stage 2 묶음별 추출 | [pipeline-ops.md](references/pipeline-ops.md); 하위 에이전트를 사용할 수 없어 직접 묶음을 쓰면 [stage2-extraction.md](references/stage2-extraction.md) 추가 | 모든 요약을 저장하고 `stage2` 표시 |
| 누락 보충 / 보강(검사기가 `repair_stages`, `enhance_existing`을 주거나 집필 쪽에서 작가에게 분석 보충을 요청) | 이 파일 Phase 2의 표 2개를 읽고 누락 Stage에 해당하는 아래 행을 읽음 | 누락 결과물만 보충하고 각각 단계 표시 |
| Stage 3 줄거리·리듬 | [synthesis-inputs.md](references/synthesis-inputs.md) + [stage3-plot-rhythm.md](references/stage3-plot-rhythm.md) | 리듬·감정 모듈 저장, `stage3` 표시 |
| Stage 4 인물·설정 | [synthesis-inputs.md](references/synthesis-inputs.md) + [stage4-characters-settings.md](references/stage4-characters-settings.md) | 인물·설정 저장, `stage4` 표시 |
| Stage 5 주 보고 | [synthesis-inputs.md](references/synthesis-inputs.md) + [stage5-report.md](references/stage5-report.md) | 보고 저장, `stage5` 표시 |
| Stage 6 문체 | [style-profile-generator.md](references/style-profile-generator.md) | `문체.md` 저장, `stage6` 표시 |
| 전체 분석 완료 | [final-checks.md](references/final-checks.md) | author-facing의 “전체 분석 완료”에 따라 보고 |
| 영감 라이브러리(작가가 “영감 라이브러리 / 영감 추출 / 여러 책의 영감 통합 / 영감 라이브러리 업데이트”를 요청할 때) | [references/inspiration-library.md](references/inspiration-library.md) | `영감자료실/`만 쓰고 분석 결과물은 변경하지 않음 |

## Phase 1: 대상 확인과 디렉터리 검사

제목·원문이 없으면 제목, 플랫폼, 원문 경로를 묻습니다. 이미 완성된 결과를 직접 사용한다면 원문을 강제로 요구하지 않습니다. 기존 디렉터리에는 먼저 읽기 전용 검사기를 실행합니다.

```text
"{PYTHON}" "{story-long-analyze skill 根}/scripts/inspect_existing_assets.py" --root "작품분석실/{书名}" --compact
```

경로 오류는 반드시 중단합니다. 기존 요약은 일절 덮어쓰지 않습니다. 특정 장을 다시 분석하려면 해당 `장별분석/제N장_요약.md`와 그 장을 포함하는 `_analysis_cache/批次-*.md`를 삭제합니다(요약만 삭제하면 캐시에서 그대로 복원됨). 책 전체를 다시 분석하려면 새 디렉터리를 사용합니다. `schema_version`은 보고만 하며 신·구 버전 통과 조건으로 삼거나 재사용 시 수정해서는 안 됩니다. 신·구 투영 자료가 섞여 있으면 출처를 보고하되 재분석을 요구하지 않습니다.

## Phase 2: 검사 결과에 따른 경로 선택

| `recommended_path` | 수행 작업 |
|---|---|
| `new_analysis` | 새 소설: Stage 0 색인 생성 → Stage 1 → 멈추고 질문 → Stage 2–6 |
| `continue_partial` | 일부 완료: 색인이 없으면 생성. Stage 1 결과(첫 3장 심층 분석, `빠른미리보기.md`) 중 없는 것만 보충하고 기존 것은 덮어쓰지 않음. 모두 갖추면 `stage1` 표시. 이후 `plan --intent continue`로 누락 장만 보충하고 Stage 3–6을 완성 |
| `direct_use` | 완성된 기존 결과: 색인을 만들거나 원문을 읽지 않고 바로 사용. 작가가 보강을 명시적으로 요청할 때만 `plan --intent enhance` |
| `repair_stages` | 장별 결과는 모두 있고 후속 결과만 누락: 아래 표에 따라 항목별 보충 |
| `enhance_existing` | 장별 결과가 있으나 완전하지 않음: 총 장 수를 모르면 색인 생성 후 재검사. 요약이 없으면 `plan --intent continue`로 기존 결과에서 보충(원문을 읽지 않음). 작가가 보강을 요청하면 `--intent enhance` |

| `stage_repairs` 코드 | 보충할 단계 |
|---|---|
| `stage3_emotion`, `stage3_rhythm` | Stage 3: 누락된 감정 모듈 또는 리듬만 보충 |
| `stage6_style` | Stage 6: 문체 |
| `stage3`, `stage4`, `stage5`, `stage6` | 완료 표시 누락: 결과가 모두 있고 적격이면 `mark-stage`만 실행하며 다시 쓰지 않음. 없을 때만 재작성 |

여러 항목이면 Stage 순서로 하나씩 보충하고 표시합니다. 감정 모듈 카드의 필드 누락(영감 라이브러리 등록 오류)은 검사기가 누락으로 보고하지 않습니다. 작가 동의를 받은 뒤 기존 `플롯/감정모듈.md`를 `_analysis_cache/legacy/`에 복사하고 Stage 3에 따라 오류 카드만 수정한 뒤 `stage3`을 표시합니다. Stage 3–5는 기존 결과와 묶음 캐시만 사용하며 원문을 읽지 않습니다. 묶음 캐시가 없는 이전 프로젝트는 `digest`로 장별 필드를 얻고 기존 줄거리·관계 자료를 더합니다. 집필 쪽의 “벤치마크 책에 감정/리듬 분석이 부족함”, “문체가 없음”은 각각 여기의 Stage 3, Stage 6에 대응합니다.

### 고정 결과물 인터페이스

- `작품분석보고서.md`, `개요요약.md`, `빠른미리보기.md`
- `장별분석/제1장_심층분석.md`, `장별분석/제2장_심층분석.md`, `장별분석/제3장_심층분석.md`, `장별분석/제N장_요약.md`
- `플롯/README.md`, `플롯/이야기선.md`, 줄거리 단위, `플롯/리듬.md`, `플롯/감정모듈.md`, `플롯/분산사건.md`
- `인물/`, `설정/`, `인물관계도/`, `문체.md`
- `chapter_index.csv`, `_progress.md`, `_analysis_cache/`

`작품분석보고서.md`가 읽기 진입점입니다. 줄거리 단위는 인과적 사실, `플롯/리듬.md`는 정보 전개·3차원 리듬, `플롯/감정모듈.md`는 독자 요구·재현 기제, `인물/인물관계.md`는 관계 사실, `문체.md`는 표현 층위를 담당합니다.

## 단계별 핵심

- **Stage 0 기계적 색인**: 새 프로젝트 또는 일부 완료 프로젝트에서 원문을 읽어야 할 때 `chapter_index.csv`를 만듭니다(명령은 stage1-golden-chapters.md 참조). LF만으로 실제 행을 세고 목차·본문 제목이 겹치면 목차 블록부터 제외합니다. 落表前校验章号连续 — 표에 저장하기 전에 장 번호의 연속성, 중복 없음, 경계 유효성을 검증합니다. 원문 변화·장 번호 불일치로 스크립트가 멈추면 index-rebuild.md를 읽고 설명과 선택지를 작가에게 전달합니다(기본 권장은 기존 장 번호로 계속).
- **Stage 1 황금 3장**: 색인으로 첫 3장을 읽으며 같은 읽기에서 장별 심층 분석 3개, 선택형 `_style-sample.txt`, `빠른미리보기.md`를 씁니다. 이후 `manage_analysis_run.py mark-stage --stage stage1`을 실행합니다. 작가가 한 번에 완료하라고 하지 않았다면 author-facing의 “첫 3장 분석 후 멈추고 질문”에 따라 묻습니다. 한 번에 완료, 여러 책 동시 분석, 가져오기에서 자동 재개를 요청했다면 멈추지 않습니다.
- **Stage 2 묶음별 추출**: `plan`으로 읽기 전용 계획을 만들고 묶음마다 `chapter-extractor` 하나를 배정합니다. 기본값은 제한된 병렬 실행(회차당 3묶음)이며 작가가 물을 때만 설명하고 분석 방식을 전환합니다. 하위 에이전트가 직접 원문을 읽고 묶음 입력을 씁니다. 주 세션은 이를 다시 붙여 넣거나 읽지 않고 바로 `commit`합니다. 세부 사항은 pipeline-ops.md를 참고합니다.
- **Stage 3–5**: `digest`로 자료를 얻고 원문을 다시 읽지 않습니다. 단계 표시는 synthesis-inputs.md의 `阶段标记`(단계 표시)를 참고합니다. Stage 5의 새 보고를 쓰기 전에 `mark-stage --stage stage5 --prepare`로 기존 보고부터 백업합니다.
- **소재 결정에 결과 반영**: Stage 5 보고 저장 후 `소재선정.md`를 찾아 여전히 “待拆文验证”(작품 분석 검증 대기)로 표시되고 소재가 맞는 항목만 갱신합니다(찾을 위치·작성법은 stage5-report.md). `推荐选题`(추천 소재) 절이 없으면 순위만 조사한 것이므로 건너뛰고 무효로 보지 않습니다. 추천 소재가 있지만 현재 계약의 필수 필드인 `能爆的原因`(흥행할 이유) 등이 없으면 `invalid_topic_decision_contract`를 반환하고 `story-long-scan` Phase 5를 다시 실행하도록 안내합니다. 파일이 없어도 작품 분석에는 영향이 없습니다.
- **Stage 6 문체**: 기존 `문체.md`와 유효한 `_style-sample.txt`를 우선 사용합니다. 표본이 부족하면 색인으로 원문 4–6개 구간을 지정해 읽고 책 전체를 재탐색하지 않습니다. 문체만 없으면 바로 이 단계만 실행하고 Stage 1–5를 재실행하지 않습니다. 검증 가능한 원문 문장을 얻을 수 없으면 실패를 명시합니다.

## 상태와 이전 프로젝트

실행 상태는 `_progress.md`의 관리 구역만 담당합니다. 기존 `schema_version: 2`는 원래 값을 유지합니다. `chapter_index.csv`는 기계적 색인이며 캐시는 복구 근거입니다. 단계 기록이 있으면 `最终状态`(최종 상태)는 스크립트가 씁니다. Stage 3–6이 모두 끝나면 `completed`, 그렇지 않으면 새 프로젝트는 `pending`, 이전 프로젝트는 원래 값을 유지합니다(기존 해당 행만 수정). 세션 hooks가 이 값으로 분석 완료를 판단하므로 직접 수정하지 않습니다.

전체 완료 후 [references/final-checks.md](references/final-checks.md)에 따라 마무리 검사를 하고 author-facing.md의 “전체 분석 완료”에 따라 작가에게 보고합니다.
