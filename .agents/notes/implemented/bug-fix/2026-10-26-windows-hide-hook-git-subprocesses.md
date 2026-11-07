# Agent Note: Windows 백그라운드 호스트에서 집필 검사가 실행한 Git 콘솔 숨기기

Status: implemented
Date: 2026-10-26
Related: https://github.com/zenstory-ai/oh-story-claudecode/issues/463

## Problem

Windows 백그라운드 서비스 프로세스에서 OpenCode 데스크톱이 집필 검사를 실행할 때 플러그인의 프로젝트 루트 탐색과 압축 전 통계가 Git을 동기 실행했다. 공유 검사 코어도 제출 검사에서 Git을 실행했다. 세 하위 프로세스에 Windows 콘솔 숨김을 지정하지 않아 본문 쓰기·수정·컨텍스트 압축마다 콘솔 창이 반복해서 깜박이며 집필을 방해했다.

## Decision

- OpenCode 플러그인의 `projectRoot()`와 `tryGit()`에서 Git 호출 시 `windowsHide: true`를 전달한다.
- 공유 `story_hook_core.js`의 `stagedMarkdownWarnings()`도 Git 호출에 `windowsHide: true`를 전달하고 공유 자산 동기화기로 OpenCode·ZCode·Antigravity 배포 사본을 갱신한다.
- PR #464 기여자 SakarPaisen의 원본 커밋과 런타임 옵션 세 곳의 수정을 보존해 현재 main에 병합한다. 기존 패치를 중복 덮어쓰지 않는다.
- 기존 OpenCode 플러그인 동작 테스트에서 실제 `child_process` 호출을 프록시로 감싼 뒤 전달한다. 프로젝트 루트 탐색, 압축 전 Git 통계, staged warning 검사를 각각 실행해 실제 options에 창 숨김 옵션이 있는지 단언한다. 소스 문자열의 존재를 동작 검증으로 오인하지 않는다.

- 현재 main의 잠금 기준에 따라 `story-setup` 패키지를 `1.1.41`로 갱신한다. `story`의 exact companion도 이 버전을 가리키며 생성된 `INSTALL.md` 바이트가 달라져 패키지를 `1.0.26`으로 갱신한다. 저장소 워크플로가 고정한 중앙 컨트롤러 `c584f3caac2f47168781f7165b38200f1bda2350`으로 다이제스트를 재생성하고 기준을 검증한다. 소스 제품 버전은 변경하지 않고 게시도 시작하지 않는다.

## Alternatives considered

- **기여 패치만 병합하고 자동 회귀 테스트는 추가하지 않기**: 불리언 옵션 세 곳만 바뀌고 기여자가 실제 Windows에서 확인했다는 점이 가장 큰 근거다. 그러나 이후 options 리팩터링에서 동작이 조용히 사라져도 macOS/Linux CI는 겉모습으로 회귀를 발견할 수 없다. 얇은 프록시가 플랫폼 공통으로 인자 전달 계약을 고정하므로 채택하지 않는다.
- **모든 저장소 스크립트의 하위 프로세스에 창 숨김 옵션 추가**: 향후 Windows 창 깜박임을 통일적으로 없앨 수 있다는 점이 가장 큰 장점이다. 그러나 이번 문제는 배포 후 GUI 백그라운드 호스트에서 실행되는 집필 검사에 한정된다. 개발 스크립트와 브라우저 도구까지 넓히면 관련 없는 diff가 생기며 그에 대응하는 사용자 증상도 없다.

## Consequences

- **이점**: Windows 데스크톱 호스트의 알려진 Git 실행 경로 세 곳이 보이는 콘솔을 만들지 않고 options 계약도 실행 가능한 회귀 테스트로 보호된다.
- **비용**: 테스트가 잠시 Node 내장 `child_process`의 동기 메서드 두 개를 프록시로 감싸지만 실제 호출을 전달하고 종료 시 복구한다. Windows 외 플랫폼의 운영 코드는 효과가 없는 호환 옵션 하나를 받는다.
- **검증 한계**: 플랫폼 공통 CI는 실제 전달 인자와 기존 반환 동작이 유지됨만 증명한다. 콘솔이 눈에 보이게 깜박이는지는 실제 Windows 데스크톱 재시험이 최종 외관 근거다.
