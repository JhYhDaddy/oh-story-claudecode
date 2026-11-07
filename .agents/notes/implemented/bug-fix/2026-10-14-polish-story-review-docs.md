# Agent Note: 원고 검토 자료 교정과 모드·사실 수정·플랫폼 안내 정렬

Status: implemented

## Problem

story-review의 자체 문서 10개에 모드 설명 중복과 단편적인 판단이 있었다. 일부 지시는 기존 계약과 달랐다. 구버전은 안내만 하는데 종합 판단에서는 stale을 추가 검증 금지의 기능 축소 사유로 삼았다. 문장 reviewer는 AI 문체 등급을 category에 넣어 통일된 열거값과 충돌했다. 추적 검사 실패 시 이전 트랜잭션 재실행만 요구해 제출 후 파생 뷰가 변경된 경우의 복구와 구분하지 않았다. 플랫폼 rubric은 표본·계산 근거 없이 본문 단서를 완독·추독·이탈 비율로 환산했다. 옌옌 글자 수, 1인칭, 도시물·성장물 기본 서술법도 보편적인 오답 기준으로 확대됐다.

## Decision

통합 시 진입점의 버전 안내는 누락·예외·도구 불가·재귀 제한·호출 실패를 기존 Phase 0에 맡긴다고 명시한다. 기존 개발 검사는 “파일 누락일 때만 기능 축소” 문구를 그대로 요구해 Phase 0와 모순을 강제했다. 이번에는 story-review의 해당 기준만 바꾸고 양성·음성 사례를 추가하며 다른 spawn 스킬 검사는 유지한다.

전체 문서 20개를 완독하고 파일별로 prose-gap-polish 다섯 단계를 순서대로 수행한다. 자체 문서 10개는 직접 정리하고 공유 복사본 10개는 읽기만 하며 canonical 동기화 사항을 기록한다. 자체 문서는 중복 메타 설명을 줄이고 판단 주체·범위를 명확히 한다. 기존 Phase 0, Findings Schema, 문체 판단, tracking_commit.py에 맞춰 충돌을 고친다. solo 단어별 검토도 책의 문체 판단을 따르며 기본 어휘 목록을 작가가 바꿀 수 없는 절대 적중 규칙으로 만들지 않는다. 플랫폼 매개변수는 근거 있는 경험 안내만 유지하고 본문으로 계산할 수 없는 유지율은 실제 데이터로 검증할 위험으로 바꿔 공식 표준이라 하지 않는다. 전문 용어, 실제 인용, 명령, 번호, 템플릿 필드와 schema를 보존하고 확인 관문을 추가하지 않으며 full/lean/solo 권한과 공유 원본도 바꾸지 않는다.

[작가 보고 규약](../../implemented/feature/2026-09-24-author-facing-reports.md)과 [시점별 원고 검토 읽기](../../implemented/architecture/2026-09-26-per-call-load-ceiling-35k.md)를 따르며 기존 결정을 뒤집지 않는다.

## Alternatives considered

- **공유 복사본 직접 정리**: 모든 파일이 즉시 개선되지만 같은 규칙의 여러 버전을 만든다. 공유 원본은 루트 담당과 장편 작업이 맡았으므로 이번에는 검토·동기화 근거만 기록한다.
- **유지율 예측 숫자를 통일 기준으로 유지**: 빠른 판단에 편리해 보인다. 그러나 출처·계산법이 없어 훅 형태에서 정확한 플랫폼 지표를 추론할 수 없으므로 독서 위험과 실측 검증으로 바꾼다.

## Consequences

검토 모드, 문제 분류, 추적 복구와 플랫폼 판단이 일치하며 작가에게 구체적인 이야기 문제를 제공한다. 대신 플랫폼 rubric은 근거 없는 정밀 효과 예측을 제공하지 않는다. 공유 문서의 최종 개선은 루트 담당의 canonical 동기화에 의존한다. 이번 작업은 런타임 스크립트, manifest, 예산이나 다른 스킬을 바꾸지 않고 커밋·동기화도 하지 않는다.

## 검증

- 20/20 문서를 전문 검토하고 다섯 단계를 순서대로 완료했다. 자체 10개를 수정하고 공유 10개는 읽기만 했다. 언어·중복·모호성·사실·논리의 파일별 증거는 `/tmp/prose-story-review-coverage.json`에 있다.
- 루트 커밋 `84612e5`와 대조한 공유 복사본 10/10은 각 canonical과 바이트가 일치한다. 장편·작가 메모리 원본의 완료된 다섯 단계 증거를 재사용한다. 격리 작업 트리의 예전 복사본은 수정하지 않고 최신본을 덮어쓰도록 돌려보내지도 않는다.
- `tracking_commit.py`의 `check_project`, `draft_transaction`, 트랜잭션 수정 검증과 `commit --help`를 확인했다. 실패한 이전 트랜잭션 재시도와 제출 후 새 revision으로 파생 뷰 재생성을 구분한다. `check-ai-patterns.js`의 blocking/advisory 유형과 Findings Schema는 유지한다.
- 플랫폼 표에 유지율 계산 출처가 없어 훅 형태에서 직접 도출한 비율을 제거했다. 도입·쾌감 포인트·성장·일일 연재의 장르 참조와 4000＝2000×2 예시는 유지했다. 옌옌 글자 수는 이번에 고정한 범위와 확인된 투고 요건을 따르게 하며 기본 범위를 새로 만들지 않았다.
- 자체 문서 10개의 frontmatter, 제목 앵커, 작가 보고 템플릿, 통일 YAML schema, 실제 인용과 전문 용어를 유지했다. 프롬프트에서는 AI 문체 등급의 issue/category를 prose로 적는 점과 열린 훅의 트랜잭션 처리만 수정했으며 실제 필드·자리표시자는 유지했다.
- 정적 검사, 번호, 현재 계약, 작가 보고, 문서 예산, notes, diff-check를 통과했다. 쓰기 실패 재시도·파생 뷰 비교·수정 사전 채움을 다루는 기존 추적 회귀 세 개도 통과했다.
- 이 작업 트리의 공유 검사는 이전 장편 장르 자료의 배포 복사본 34개 불일치만 보고했다. 루트에서 이미 커밋·동기화한 사항이며 이번 story-review에서 새 공유 불일치는 없다.

## 검토 범위

문서 20개를 언어, 군더더기, 모호성, 사실 재확인, 논리의 다섯 단계로 순서대로 검토했다. 공유 복사본은 교정된 원본과 검토 시 사용 상황에 따라 재확인했다.

| 파일 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| `skills/story-review/SKILL.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/agent-prompts.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/anti-ai-writing.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/author-memory-maintenance.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/author-memory.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/banned-words.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/batch-review.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/character-relations.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/dialogue-mastery.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/plot-core-methods.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/quality-rubric.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/review-quality.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/review-tracking.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/rubrics/fanqie.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/rubrics/qidian.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/rubrics/zhihu.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/solo.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/style-resolution.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/tracking-initialization.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-review/references/tracking-transaction.md` | ✓ | ✓ | ✓ | ✓ | ✓ |


통합 후 현재 계약, 버전 사전 검사 양성·음성 사례와 검사 회귀를 통과했다. 검사는 원고 검토의 기존 Phase 0 처리에 맞춘 문구 기준만 바꿨으며 다른 spawn 스킬 검사는 유지한다.
