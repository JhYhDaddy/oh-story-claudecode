# Agent Note: 단편 작품 분석 자료를 문서별로 다듬기

Status: implemented

## Problem

단편 작품 분석 자료에는 집필 명령과 관찰 기준의 혼용, 출처 없는 정밀 통계, 주관 평가와 점수의 충돌, 노드 순서·완료 배열의 모호함이 있었다. 지난 차례에는 짧은 기준 문서 여섯 개를 읽기만 하고 수정하지 않았다. 사용자는 전문 용어를 유지하면서 모든 파일에 다섯 단계 다듬기를 적용하라고 요청했다.

## Decision

진입점과 reference 22개를 파일별로 다섯 단계에 따라 다듬었다. 후킹·핵심 아이디어·특수 능력·구조 패턴·주인공의 주도권 등의 용어는 유지한다. 기존 변경의 전문적 의미를 다시 확인하고 기준 문서 여섯 개의 지시 대상, 후킹 판정 범위, 서스펜스 대상, 관찰자형 주인공의 관찰 방식을 보완했다. 인용·코드 블록 템플릿·번호·기계 필드·검증 조건은 유지하고 시장 자료 공유 원본을 순위 조사 사본에 동기화한다.

## Alternatives considered

- 짧은 기준 문서 여섯 개를 읽은 것으로만 기록하면 변경을 줄일 수 있다. 그러나 중복된 편집 과정 설명과 판정 범위 누락이 남아 있어 다섯 단계에 따라 수정까지 진행한다.
- 모든 주인공에게 결말을 결정하는 행동권을 주면 주도성을 비교하기 쉽다. 그러나 영혼으로 지켜보는 단편 등은 개입할 수 없다는 무력함 자체가 독서 경험이므로 실제 역할과 독자에게 한 약속을 기록하고 단일 패턴을 합격 조건으로 삼지 않는다.

## Consequences

작품 분석이 검증 가능한 텍스트 관찰에 가까워지고 장르 모델을 원문에 강요할 위험이 줄어든다. 일부 절대 판단을 완화하여 분석자가 텍스트에 근거해 효과를 설명해야 한다. 기계적 검수와 글자 수 예산은 유지한다.

아래 표의 인물·독자·기법·문단 후킹·분석 사례·즈후 스타일·시장 데이터 파일은 이후 병합하거나 삭제했고 차단 기준도 필요한 내용을 모두 썼는지만 확인하도록 바뀌었다. [작품 분석 자료의 시점별 재구성](../architecture/2026-10-17-analyze-docs-by-moment.md)을 참조한다.

## 검토 범위

파일별 다섯 단계 전체 읽기를 완료했다. output-contract.md는 앞선 집필 원본 처리와 함께 동기화했고 이 PR에서 완료·재개 규약을 다시 확인했다.

| 파일 | 다섯 단계 검토 | 결과 |
|---|---|---|
| `SKILL.md` | 1→5 완료 | 수정 완료 |
| `references/analysis-character-basics.md` | 1→5 완료 | 수정 완료 |
| `references/analysis-character-design.md` | 1→5 완료 | 수정 완료 |
| `references/analysis-character-relations.md` | 1→5 완료 | 수정 완료 |
| `references/analysis-method.md` | 1→5 완료 | 수정 완료 |
| `references/analysis-paragraph-hooks.md` | 1→5 완료 | 수정 완료 |
| `references/analysis-reader-profile.md` | 1→5 완료 | 수정 완료 |
| `references/analysis-report-style.md` | 1→5 완료 | 수정 완료 |
| `references/analysis-short-genres.md` | 1→5 완료 | 수정 완료 |
| `references/analysis-short-hooks.md` | 1→5 완료 | 수정 완료 |
| `references/analysis-short-mechanics.md` | 1→5 완료 | 수정 완료 |
| `references/analysis-short-patterns.md` | 1→5 완료 | 수정 완료 |
| `references/analysis-short-suspense.md` | 1→5 완료 | 수정 완료 |
| `references/analysis-writing-techniques.md` | 1→5 완료 | 수정 완료 |
| `references/deconstruction-examples.md` | 1→5 완료 | 수정 완료 |
| `references/optional-modules.md` | 1→5 완료 | 수정 완료 |
| `references/output-contract.md` | 1→5 완료 | 앞선 공유 원본 수정·재검토 완료 |
| `references/quality-checklist.md` | 1→5 완료 | 수정 완료 |
| `references/real-market-data.md` | 1→5 완료 | 수정 완료 |
| `references/source-story-quality.md` | 1→5 완료 | 수정 완료 |
| `references/stage2-3-structure-emotion.md` | 1→5 완료 | 수정 완료 |
| `references/stage4-6-reversal-summary.md` | 1→5 완료 | 수정 완료 |
| `references/zhihu-style.md` | 1→5 완료 | 수정 완료 |
