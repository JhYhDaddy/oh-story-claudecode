# Agent Note: 장편 집필 문서 교정과 기존 계약 정렬

Status: implemented
Date: 2026-10-14
Related: [개념 연결 완결](../../implemented/architecture/2026-09-25-concept-chain-closure.md), [새 책 시작의 구간별 로드](../../implemented/architecture/2026-09-26-opening-by-author-moments.md), [가져오기 문서 보완](../../implemented/bug-fix/2026-10-14-import-doc-contract-gaps.md)

## Problem

장편 핵심 절차·기법 자료에 정보 단절이 남아 있었다. 초기화의 입력 여섯 항목과 파생 뷰 일곱 칸을 혼동하고 도구 불가를 모두 Node 누락으로 설명했다. 형식 설명에는 작가의 명시적 분량 범위 우선순위가 없었다. 일부 기법은 장 개요 비율·예시 분량·구조 모델을 현재 상세 개요 계약보다 우선하는 일반 요구로 썼다. 일부 표의 개수·연결·인과 설명도 앞뒤가 달랐다.

## Decision

52개 문서를 prose-gap-polish 다섯 단계로 완독하고 편집 가능한 49개를 교정했다. `storyctl.py`, `tracking_commit.py`, 상세 개요 검사기와 현재 절차에 맞춰 설명을 보완한다. 전문 용어, 구체적인 역추론 방법, 기계용 필드·명령·번호·관문은 유지한다. 작가 메모리·문체 제거 Gate의 공유 target 세 개는 검토만 하고 제안을 원본 담당자에게 전달한다. 나머지 공유 원본은 source만 수정하고 통합 담당자가 동기화한다. 일일 종료 검사는 아직 개별 검증하지 않은 장을 포함한다. 근거 불명 비율은 제거하고 구체 인과 검사는 유지한다. 예시 개수, 개요 연결과 초기화 필드 수는 실제 내용에 맞춘다.

## Alternatives considered

- **문장만 바꾸고 계약은 확인하지 않음**: 변경은 작지만 문서 실행 시 모호성이 남아 정보·논리 검토를 완료할 수 없다.
- **기법을 모두 일반적인 조언으로 변경**: 표면 충돌은 없애지만 구체 작성법을 잃는다. 이번에는 모델 적용 범위를 밝히고 명백한 오류만 수정한다.

## Consequences

문서가 현재 구현과 일치해 템플릿·기법 모델·기계 검증 관문을 구별할 수 있다. 공유 원본 변경 뒤 통합 시 복사본 동기화가 필요하며 스크립트·예산은 유지한다.

## 검토 범위

이 스킬 문서 87개 모두 다섯 단계를 완료했다. 아래 핵심 자료 52개와 같은 날 polish-long-genre-docs 기록의 장르 자료 35개다. 작가 메모리 두 개는 story 원본에서, deslop-gates는 story-deslop 원본에서 이미 교정·동기화했다.

| 파일 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| `skills/story-long-write/SKILL.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/agent-calls.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/anti-ai-writing.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/artifact-protocols.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/author-memory-maintenance.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/author-memory.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/banned-words.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/benchmark-recall.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/character-basics.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/character-design-methods.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/character-relations.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/commercial-core-methods.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/cross-book-recall.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/deslop-gates.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/dialogue-mastery.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/emotion-on-page.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/emotional-arc-design.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/emotional-methods.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/female-audience-writing.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/long-chapter-hooks.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/long-chapter-quality.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/long-format.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/long-genre-mechanics.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/long-reversal.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/long-suspense.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/opening-design.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/outline-conflict.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/outline-methods.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/outline-rhythm.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/outline-structure-theory.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/plot-core-methods.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/plot-emotion-system.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/plot-frameworks.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/plot-special-topics.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/project-files.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/reader-contract-and-progression.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/reference-index.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/stop-and-fix.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/style-combat-face.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/style-craft.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/style-genre-modules.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/style-resolution.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/tracking-initialization.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/tracking-transaction.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/workflow-chapter.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/workflow-daily.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/workflow-outline.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/workflow-revision.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/workflow-setup.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/workflow-volume.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/writer-prompt-fallback.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-long-write/references/writing-craft.md` | ✓ | ✓ | ✓ | ✓ | ✓ |


통합 때 장르 색인이 단일 장 절차를 부르는 이름을 고쳐 배포 공유 복사본이 미배포 파일을 가리키지 않게 했다. 공유 복사본 71개를 동기화하고 예산은 유지했다.

구성 재검토 보완: 진입점의 장면 목표는 주도 감정으로 표현해 다른 감정의 공존 여지를 남긴다. 일일 집필은 기존 계획 변경의 확인과 이미 승인된 일반 추적 제출을 구분한다. 수정 중 외부 사실이 미확정이면 먼저 검증하고 재작성·검사로 돌아간다. 권별 자체 검사의 저긴장·전환 장 약 15%는 아래 장르별 구분과 같은 균형 참고값으로 통일한다. 한 곳은 상한, 다른 곳은 여성향 관계 용량에 따라 증가 허용으로 쓰지 않는다. 단계·스크립트·문구 예시·예산은 유지한다.

추가 정렬: 권별 템플릿과 구조 자체 검사는 같은 장르별 구분을 쓰고 연결은 workflow-volume의 “장 역할과 긴장·이완”으로 모은다. 템플릿 블록은 이 규칙 문장만 고치며 본문 예시·양성/음성 예시는 바꾸지 않는다. 구조 이론은 선택 모델에 따라 적용하고 5막 모델로 다른 구조를 덮지 않는다. 인물 궤적·숨은 뜻은 장르에 맞추며 곁가지 사건도 주줄거리와 연결한다. 집필 전 조회의 누락 처리는 전체 경로에만 한정하고 성숙 프로젝트의 짧은 경로는 기존 build_writer_prompt.py 판단을 유지하며 새 우회 조건을 넣지 않는다.
