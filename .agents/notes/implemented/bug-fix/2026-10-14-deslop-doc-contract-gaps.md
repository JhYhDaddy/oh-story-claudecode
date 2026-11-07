# Agent Note: AI 문체 제거 Gate와 검출 스크립트 설명 일치

Status: implemented
Date: 2026-10-14
Related: [AI 문체 제거의 단일 등급](../../implemented/bug-fix/2026-09-27-deslop-one-grading.md), [개념 연결 완결](../../implemented/architecture/2026-09-25-concept-chain-closure.md), [장편 핵심 문서 다듬기](../../implemented/bug-fix/2026-10-14-long-write-doc-contract-gaps.md), [나머지 스킬의 시점별 재구성](../architecture/2026-10-17-other-skills-by-moment.md)(이후 Gate A–G 문자를 없애고 검출 범주로 범위를 제한하여 이 기록의 ‘Gate 범위 유지’를 대체)

## Problem

Gate A는 기본적으로 금지어를 행동으로 바꾸라고 하여 정확한 직접 서술을 허용하고 미세 행동을 억지로 넣지 말라는 Gate C와 충돌했다. 진입점은 스캐너가 따옴표 밖만 본다고 했지만 대시와 일부 정형 병렬 규칙은 실제 대사도 검사한다. 퇴화 검출 스크립트는 기본적으로 finding이 하나라도 있으면 1로 종료하므로 종료 코드 1을 전부 blocking으로 볼 수 없다. 진입점은 여섯 등급 지표와 스크립트 findings의 관계를 설명하지 않았고 상대 경로 스크립트 명령을 어느 디렉터리에서 실행하는지도 누락했다.

## Decision

이 스킬의 로컬 또는 기준 원본 문서 세 개(진입점·Gate 세부 규칙·에이전트 프롬프트)를 다듬었다. 공유 대상 다섯 개는 전체 검토 후 원본 동기화를 기다린다. 현재 스크립트에 맞춰 스캔 범위·종료 코드·읽기 전용/쓰기 역할을 설명한다. 기존 보호 프로토콜에 따라 Gate A/E/G의 수정 조건을 명확히 하고 중복 예외 설명을 제거한다. 여섯 등급 임계값·Gate 범위·비율 상한·라운드 수·명령·기계 필드는 유지한다.

## Alternatives considered

- **스캔 스크립트를 옛 설명에 맞게 변경**: ‘따옴표 밖만 검사’가 맞게 된다. 그러나 기존 대사 문장부호·정형 병렬 검사를 잃으므로 문서만 수정한다.
- **등급 기준 재설계**: 더 많은 경계를 처리할 수 있다. 그러나 기존 단일 등급 결정을 뒤집어 이번 다듬기 범위를 벗어난다.

## Consequences

실행자가 실제 검출 결과에 따라 분기하고 상투적 표현을 없앨 때 미세 행동을 자동으로 추가하지 않게 된다. 대신 Gate 원본 변경 후 long-write·setup 사본을 동기화해야 한다. 공유 대상과 스크립트는 원문을 유지한다.

## 검토 범위

문서 8개를 각각 언어·군더더기·모호함·사실 대조·논리의 다섯 단계로 순서대로 검토했다. 공유 사본은 장편 원본과 이 스킬의 사용 맥락에 맞춰 확인했다.

| 파일 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| `skills/story-deslop/SKILL.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-deslop/references/agent-calls.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-deslop/references/anti-ai-writing.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-deslop/references/author-memory-maintenance.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-deslop/references/author-memory.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-deslop/references/banned-words.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-deslop/references/deslop-gates.md` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `skills/story-deslop/references/style-resolution.md` | ✓ | ✓ | ✓ | ✓ | ✓ |

통합 후 long-write·setup의 AI 문체 제거 Gate 사본 두 개를 동기화하고 모든 동기화 대기 상태를 해소했다.
