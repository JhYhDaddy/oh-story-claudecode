# Agent Note: Windows 최종 검증 실패 수정

Status: implemented

## Problem

한국어 경로 변경 후 남은 7개 검사 실패를 모두 환경 제약으로 분류했지만 최신 OpenCode 실패에는 잘못 치환한 테스트 기대 문구도 포함됐다. Windows의 줄바꿈·권한·링크와 폴더 교체, CDP 프로세스 소유 검사를 개별 재현해 판단해야 한다.

## Decision

OpenCode 기대 문구·경로 단언, CRLF 절 추출, 플랫폼 모드·경로 검사를 수정했다. Antigravity는 중간 rename을 제거하고 일시적 Windows 잠금 오류를 제한 재시도하며 복원 실패 시 백업을 남긴다. 오류 주입으로 세 실패 경로를 검증한다. `.agents/skills`는 원래 상대 심볼릭 링크로 복구했다.

이 Windows TCP 공급자의 수신 State=0 반환을 .NET과 Node 임시 소켓으로 확인했다. 표준 Listen 조회가 비면 로컬 포트·원격 포트 0의 PID를 읽고 기존 HTTP 식별·생존·실행 트리·명령행 검증을 그대로 적용한다. 성공·실패 사례를 모두 유지한다. 무관했던 생존 신호 검사 변경은 채택하지 않았다.

## Alternatives considered

- 실패를 제외하면 빠르게 녹색 결과를 만들 수 있지만 실제 Windows 배포 문제를 숨기므로 사용하지 않는다.
- 모든 플랫폼을 Unix처럼 처리하면 구현이 단순하지만 Windows의 실제 파일 시스템 동작을 검증하지 못한다.

## Consequences

지원 플랫폼의 검증 결과를 신뢰할 수 있게 한다. Windows에서 재현되지 않는 플랫폼 고유 기능과 실제 브라우저를 사용하지 않는 모의 검사의 범위는 명시한다.

## Verification

Windows 전체 검사 명령 61/61 통과. 경로 전환 10개, 추적 51개, 장 완성 흐름 8개, 문서 예산 18개 통과. 대시보드 23개 통과·4개 플랫폼 조건 제외. POSIX 실행 비트 변경만 Windows에서 명시적으로 제외한다. 상세는 [Windows 검증](../../../../docs/WINDOWS_VALIDATION.md)에 기록했다.
