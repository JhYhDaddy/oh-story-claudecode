# Agent Note: 공유 런타임을 단일 배포 패키지로 묶지 않고 스킬별 실제 사본 유지

Status: rejected

## Problem

v0.8 경량화 제안([v0.8 제안](../../implemented/architecture/2026-09-24-v0-8-lean-writing-loop.md) 2절)에 ‘공유 런타임을 하나의 패키지로 묶기’ 항목이 있었다. 작가 기억·추적·검출기·글자 수 스크립트가 스킬 다섯 곳에 복사되어 저장소 중복이 약 1.76MB(스크립트 약 0.94MB)이고 한 곳을 수정하면 모든 사본을 동기화해야 한다. 제안은 이를 하나의 런타임 묶음으로 만들어 story-setup이 사용자 프로젝트에 배포하고 각 스킬이 그 사본을 호출하는 방식이었다.

## Decision

- 단일 런타임 패키지를 만들지 않는다. 공유 스크립트는 이를 쓰는 각 스킬에 실제 사본을 계속 둔다. `scripts/shared-assets.json`에 유일한 source를 등록하고 `sync-shared-assets.py sync`로 동기화하며 `check-shared-files.sh`가 CI에서 불일치를 막는다.
- v0.8 제안 2절의 이 항목은 이 기록으로 종결한다.

## Alternatives considered

- **제안대로 구현**(`story-runtime/`을 만들어 작가 기억·추적·글자 수·검출기 스크립트를 모으고 story-setup으로 프로젝트의 고정 위치에 배포한 뒤 각 스킬이 이를 호출하게 하고 사본 삭제): 단일 원본, 약 0.94MB의 중복 스크립트 감소, 작은 PR diff, 유지 관리자의 동기화 작업 제거가 가장 큰 장점이다. 다음 세 이유로 채택하지 않는다.
  - [스킬 간 복사 기록](../../implemented/architecture/2026-05-07-cross-skill-copies-not-symlinks.md)의 전제인 스킬별 독립 설치·배포를 뒤집는다. OpenClaw·Reasonix·generic 대상은 skills-only여서 story-setup의 런타임 배포 단계가 없다. `npx skills add`나 marketplace에서 스킬 하나만 설치해도 런타임 패키지를 받지 못한다. 이 사용자들의 본문 쓰기 검사·추적 제출·검출기는 바로 작동하지 않게 된다.
  - 조사에서 확인한 네 문제(토큰·시간·AI 문체·개념 복잡도)는 모두 사용자 측 문제다. 중복 사본은 유지 관리자 작업만 늘린다. 사용자는 세션마다 자기 사본만 로드하므로 토큰을 더 쓰거나 개념을 하나 더 배우지 않는다. 필요하지 않은 곳에서 이득이 생기고 사용자가 비용을 부담한다.
  - 기존 `shared-assets.json` + `check-shared-files.sh`가 이미 불일치 위험을 CI에서 통제한다. 사본이 다르면 즉시 실패하고 담당 원본은 하나다.

## Consequences

- **이점**: skills-only 플랫폼과 단일 스킬 설치를 포함한 모든 대상이 계속 작동하며 새로운 배포 전제 조건을 추가하지 않는다.
- **비용**: 저장소에 약 1.76MB의 중복 내용이 남고 공유 스크립트를 수정하면 `sync-shared-assets.py sync`와 모든 사본의 커밋이 계속 필요하다.
- **재검토 조건**: 모든 대상에 신뢰할 수 있는 런타임 배포 단계가 생기거나 스킬 설치가 스킬 간 의존성을 기본 지원하면 다시 논의한다. 그때 새 기록을 만들고 이 기록과 서로 링크한다.
