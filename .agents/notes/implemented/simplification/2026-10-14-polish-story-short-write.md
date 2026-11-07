# Agent Note: 전문 용어를 유지하며 단편 집필 자료를 다섯 단계로 교정

Status: implemented

## Problem

단편 집필 진입 문서와 참조 자료 36개 전체에 끊긴 문장, 중복 메타 설명, 예전 경로, 분기 범위 충돌이 있었다. 사용자는 웹소설 전문 용어를 보존하고 각 문서에 prose-gap-polish를 완료하며 스킬별로 PR을 제출하라고 추가 요청했다.

## Decision

전체 문서 37개를 파일별로 언어, 중복 제거, 모호성 해소, 사실 재확인, 논리 수정의 다섯 단계로 순서대로 교정한다. 쾌감 포인트, 훅, 끊는 지점, 마무리, 장면 엔진, 비트 등의 전문 표현은 보존한다. 용어 설명이 필요하면 구체적인 맥락을 추가하며 막연한 대체어로 바꾸지 않는다. 단편 비교 작품 경로, 반전 없는 분기와 악역 없는 분기, Stage 6 완료·재개 설명을 수정한다. 공유 자료는 기준 원본에서 동기화한다. 인용문, 코드 블록, 기계용 필드, 번호와 필요한 검증 관문을 유지하며 예산을 늘리지 않는다.

## Alternatives considered

- 모든 전문 표현을 쉬운 말로 바꾸면 진입 장벽을 줄일 수 있다. 그러나 용어의 정밀도를 잃고 작가 요구에 어긋나므로 임의로 만든 말과 난해한 표현만 정리한다.
- 단편 스킬 세 개를 한 PR에 합치면 검증을 모으고 동기화하기 쉽다. 그러나 사용자가 스킬별 검토를 요구했으므로 순차적으로 연결되는 독립 PR로 나누고 공유 복사본은 원본과 함께 제출한다.

## Consequences

집필 자료가 명확해지고 전문적 의미와 실행 계약이 일치한다. 공유 원본 수정은 다른 소비자에도 영향을 주므로 동기화, 예산, 어댑터를 검증해야 한다. 작품 분석과 순위 조사에만 해당하는 정리는 각각의 후속 PR에서 진행한다.

## 검토 범위

아래 표는 각 파일을 완독하며 진행한 다섯 단계 검토를 기록한다. 결과는 실제 편집과 차이 검토로 확인했으며 자동 검사는 계약만 검증한다.

| 파일 | 다섯 단계 검토 | 결과 |
|---|---|---|
| `SKILL.md` | 1→5 완료 | 수정 완료 |
| `references/agent-calls.md` | 1→5 완료 | 수정 완료 |
| `references/author-memory-maintenance.md` | 1→5 완료 | 수정 완료 |
| `references/author-memory.md` | 1→5 완료 | 수정 완료 |
| `references/banned-words.md` | 1→5 완료 | 수정 완료 |
| `references/benchmark-recall.md` | 1→5 완료 | 수정 완료 |
| `references/cross-book-recall.md` | 1→5 완료 | 수정 완료 |
| `references/dialogue-mastery.md` | 1→5 완료 | 수정 완료 |
| `references/emotional-methods.md` | 1→5 완료 | 수정 완료 |
| `references/genre-styles/世情打脸.md` | 1→5 완료 | 수정 완료 |
| `references/genre-styles/双男主.md` | 1→5 완료 | 수정 완료 |
| `references/genre-styles/复仇打脸.md` | 1→5 완료 | 수정 완료 |
| `references/genre-styles/宅斗宫斗.md` | 1→5 완료 | 수정 완료 |
| `references/genre-styles/总裁豪门.md` | 1→5 완료 | 수정 완료 |
| `references/genre-styles/悬疑.md` | 1→5 완료 | 수정 완료 |
| `references/genre-styles/民俗怪谈.md` | 1→5 완료 | 수정 완료 |
| `references/genre-styles/沙雕脑洞.md` | 1→5 완료 | 수정 완료 |
| `references/genre-styles/甜宠.md` | 1→5 완료 | 수정 완료 |
| `references/genre-styles/追妻火葬场.md` | 1→5 완료 | 수정 완료 |
| `references/genre-writing-formulas.md` | 1→5 완료 | 수정 완료 |
| `references/hooks-chapter.md` | 1→5 완료 | 수정 완료 |
| `references/hooks-paragraph.md` | 1→5 완료 | 수정 완료 |
| `references/output-contract.md` | 1→5 완료 | 수정 완료 |
| `references/reference-index.md` | 1→5 완료 | 수정 완료 |
| `references/scene-craft.md` | 1→5 완료 | 수정 완료 |
| `references/short-craft.md` | 1→5 완료 | 수정 완료 |
| `references/short-deslop.md` | 1→5 완료 | 수정 완료 |
| `references/short-format.md` | 1→5 완료 | 수정 완료 |
| `references/short-prose-quality.md` | 1→5 완료 | 수정 완료 |
| `references/short-reversal.md` | 1→5 완료 | 수정 완료 |
| `references/style-resolution.md` | 1→5 완료 | 수정 완료 |
| `references/submission-craft.md` | 1→5 완료 | 수정 완료 |
| `references/villain-and-reveal.md` | 1→5 완료 | 수정 완료 |
| `references/workflow-design.md` | 1→5 완료 | 수정 완료 |
| `references/workflow-draft.md` | 1→5 완료 | 수정 완료 |
| `references/workflow-revision.md` | 1→5 완료 | 수정 완료 |
| `references/writing-workflow.md` | 1→5 완료 | 수정 완료 |
