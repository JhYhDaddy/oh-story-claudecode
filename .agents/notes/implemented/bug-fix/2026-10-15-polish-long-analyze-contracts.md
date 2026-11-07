# Agent Note: 장편 작품 분석 문서를 다섯 단계로 교정

Status: implemented
Date: 2026-10-15

## Problem

문서 16개에는 추출 순서 혼용, 요약 누락 시 잘못된 라우팅, 합성 단계의 원문 재열람 범위 불일치, 문체 세부 항목 예산이 총예산을 초과하는 문제가 있었다. 일부 방법 설명은 경험적 판단을 표본 조건 없는 결론으로 서술했다.

## Decision

문서 16개를 각각 언어, 군더더기, 모호성, 정보 단절, 논리 단절의 다섯 단계로 순서대로 교정한다. 기존 스크립트와 구현된 파이프라인을 근거로 문서를 수정하고 단계 번호, 필드, 원문 예시와 웹소설 전문 용어는 보존한다.

## Alternatives considered

- 문장만 수정하면 차이를 줄일 수 있지만 잘못된 라우팅과 앞뒤 모순을 없애지 못하므로 확인 가능한 계약 설명도 함께 수정한다.

## Consequences

장 추출, 기존 결과 재사용과 문체 생성에서 읽기 범위가 일치한다. 대신 기존 문서의 경험적 수치는 적용 범위를 명시해야 하며 보편적인 품질 결론으로 사용할 수 없다.

## 검증

manage_analysis_run.py의 min_plot_points, stage_required_outputs, mark_stage_command 및 기존 색인·결과 라우팅과 대조했다. 모든 명령, 열거값과 단계 번호를 유지하며 경험적 비율도 재검토 단서로 남긴다. 요약 누락 라우팅, 텍스트 공개 순서, 원문 재열람 범위, 흩어진 사건 보관과 문체 예산(1800+2100+100=4000)을 수정했다. 원문 사례와 전문 용어는 유지하고 표본 근거 없는 보편적인 속도 배수 보장은 제거했다.

문서 구성 재검토의 보완 내용: 작가 질문 규칙에서 추천 선택지와 실제 승인을 구분한다. 확인이 필요한 선택은 답변을 기다리고 이미 승인된 일반 작업은 계속한다. 실행 설명은 `input_file`이 하위 에이전트 출력 경로임을 명시하고 파일 앞부분에 이미 있는 schema 재사용 규칙을 합친다. 단계, 명령과 실행 동작은 유지한다.

같은 검토에서 Stage 2의 예전 요약 두 곳도 수정했다. `existing-results`에 요약 누락이 있으면 압축된 장 블록도 출력하고 제출기는 이를 바탕으로 파생 뷰를 보충한다. 따라서 관찰만 반환한다거나 원문 모드에서만 요약을 보충한다고 요약하면 안 된다. 인물 병합은 기존 nickname 유형으로 동일 인물이라는 명확한 증거가 있는 이름 포함 직함을 수용하며 일반적인 호칭은 병합을 유발하지 않는다. 관계 수는 누락과 오병합 재검토에만 쓰고 원작의 관계를 바꾸도록 요구하지 않는다. 작품 분석 참조 자료의 집필 지시를 관찰 질문으로 바꾸고 한 작품 분석에 먼저 다섯 권을 모으도록 요구하지 않는다. 작품명, 공식과 원문 사례는 보존한다.

집계 소속은 목표와 인과관계로 판단하며 인물·주제의 겹침은 후보를 찾는 데만 쓴다. 흩어진 사건의 보관 위치는 `剧情/散落情节.md`로 명시해 검사기가 사건 전개 단위에서 제외하는 경로와 일치시킨다.

## 검토 범위

문서마다 1 언어, 2 군더더기, 3 모호성, 4 코드·자료 재확인, 5 논리 검토를 순서대로 완료했다.

| 파일 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| `skills/story-long-analyze/SKILL.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-analyze/references/author-facing.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-analyze/references/deconstruction-notes.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-analyze/references/final-checks.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-analyze/references/index-rebuild.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-analyze/references/inspiration-library.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-analyze/references/pipeline-ops.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-analyze/references/semantic-acceptance-fixtures.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-analyze/references/stage1-golden-chapters.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-analyze/references/stage2-extraction.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-analyze/references/stage3-plot-rhythm.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-analyze/references/stage4-characters-settings.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-analyze/references/stage5-report.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-analyze/references/style-profile-generator.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-analyze/references/style-profile-protocol.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-analyze/references/synthesis-inputs.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
