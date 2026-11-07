# Windows 오류 수정과 검증

2026-11-07, Windows의 Node 24.16.0·Python 3.12.14·Git for Windows 2.37.2에서 확인했다. 셸 검사는 Git Bash를 사용하며 Python의 표준 입출력은 UTF-8로 설정했다.

## 수정 사항

| 항목 | 수정 |
|---|---|
| OpenCode | 경로 변경 과정에서 잘못 바뀐 기대 문구와 Windows 경로 구분자 단언을 수정했다. 본문 쓰기 차단 기능은 유지한다. |
| 문서 예산 | 절 추출기가 LF·CRLF·CR 줄바꿈을 처리한다. CRLF 전용 회귀 사례를 추가했다. |
| 공유 파일 | 오류 메시지의 경로 구분자를 정규화해 비교한다. 실제 파일 내용·복사·오류 검사는 그대로 실행한다. Windows가 지원하지 않는 POSIX 실행 비트 변경 사례만 명시적으로 건너뛴다. |
| Antigravity | 불필요한 중간 디렉터리 이동을 제거했다. Windows의 일시적 EPERM·EACCES·EBUSY에는 최대 750ms 동안 재시도하고, 복원 자체가 실패하면 원본 백업을 보존한다. 오류 주입으로 재시도·복원·백업 보존을 검사한다. 훅 병합 검사는 플랫폼에서 실제로 설정된 파일 모드의 보존을 확인한다. |
| Codex 스킬 발견 | 이 작업 사본에서 일반 파일이던 `.agents/skills`를 원래 Git 계약인 `../skills` 디렉터리 심볼릭 링크로 복구했다. 링크 대상과 14개 스킬 탐색을 검사한다. |
| Chrome 소유권 | 이 환경의 TCP 공급자는 실제 수신 소켓의 State를 0으로 반환해 `-State Listen`과 netstat에서 누락했다. 표준 조회가 비면 로컬 포트·원격 포트 0의 소유 PID를 조회한다. HTTP 응답·인스턴스 식별·프로세스 생존·실행 트리·명령행 포트 검증은 유지한다. |

Chrome 검사는 실제 사용자의 Chrome이나 로그인 프로필 대신 임시 프로필과 모의 CDP 서버를 사용한다. 정상 자식 프로세스 소유뿐 아니라 다른 프로세스의 포트 점유, 죽은 실행기, 오래된 엔드포인트, 식별 불가를 거부하는 사례도 검사한다. 수신 State를 찾지 못하는 경우의 대체 조회는 별도 조건으로 재현한다.

## 새 Windows 체크아웃

이 저장소의 `.agents/skills`는 복사본이 아닌 상대 심볼릭 링크다. Windows에서는 링크 생성 권한을 갖춘 환경에서 `git -c core.symlinks=true clone ...`으로 체크아웃하고 `bash scripts/check-codex-adapter.sh`로 확인한다. 문자열 `../skills`만 들어 있는 일반 파일을 정상 설치로 인정하지 않는다. 이번 작업은 전역 Git 설정을 변경하지 않았다.

## 재검증

필수 검사 목록은 `.github/workflows/cross-platform.yml`을 따른다. 한국어 프로젝트의 생성, 장별 검사·추적 제출, 다음 장 진행, 재수정·파생 상태 검증은 `test-project-path-localization.py`, `test-storyctl.py`, `test-chapter-completion-lifecycle.py`, `test-tracking-commit.py`에서 확인한다. 대시보드는 `node --test tests/dashboard-server.test.mjs`로 확인한다.

이전 완료 기록의 “7개 모두 기존 Windows 환경 제약”이라는 분류는 부정확했다. OpenCode 기대 문구 오류, 플랫폼 차이를 반영하지 않은 테스트, 실제 운영 코드의 호환성 문제, 체크아웃 상태를 구분해 수정했다.

## 최종 결과

전체 검사 명령 61개 모두 통과, 실패 0개. 한국어 경로 전환 10개·추적 51개·장 완성 흐름 8개·문서 예산 18개 통과. 대시보드는 23개 통과·4개 플랫폼 조건 건너뜀이다. 모든 호스트 어댑터와 배포 검사가 통과했다. 변경 파일의 공백 검사도 통과했다.
