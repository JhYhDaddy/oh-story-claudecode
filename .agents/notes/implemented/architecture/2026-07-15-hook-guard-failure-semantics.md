# Agent Note: 차단 검사는 fail-closed, Bash 명령 검사는 best-effort fail-open

Status: implemented

## Problem

`guard-outline-before-prose.sh`는 사용자 프로젝트에 배포되는 유일한 차단 hook이다(상세 개요 없이 본문을 쓰면 exit 2). 네 호스트의 hook 논리를 공유 node 코어 `story_hook_core.js`로 모은 뒤 Claude의 bash hook은 node를 감지해 코어 사용 여부를 결정했다. 그러나 Claude Code 공식 권장 설치는 node를 포함하지 않는 네이티브 바이너리 방식이다. node를 찾지 못했다고 조용히 허용하면 차단 검사가 없는 것처럼 된다. 코어 통합 당시 실제로 이 회귀가 발생해 두 번 수정했다(node 부재, node는 있지만 추출이 예외를 던지는 경우). 한편 Bash 명령이 쓰는 본문 대상은 정적으로만 식별할 수 있어 shell 샌드박스가 될 수 없으므로 실패 시 의미를 명확히 해야 한다.

## Decision

- **Write/Edit/MultiEdit 경로(차단)**: 대상 경로 추출은 node 공유 코어를 우선 사용한다. node가 없거나 추출 결과가 비면 항상 순수 bash JSON 추출로 대체한다(`file_path` / `path` / `filePath` 우선순위로 값을 선택하고 `\\` 이스케이프와 UTF-8 복원). 두 경로 모두 대상을 추출하지 못할 때만 허용한다. 차단 판정(장 번호·상세 개요 glob·exit 2)은 모두 bash에서 수행하며 node에 의존하지 않는다. python heredoc을 대체 경로로 쓰지 않는다. `test-prose-net-parity.sh`는 Claude hook의 heredoc python을 금지하여 다섯 번째 수동 복제 로직이 생기지 않게 한다.
- **Bash 명령 경로(best-effort)**: `settings-hooks.json`은 검사를 `Bash|Write|Edit|MultiEdit`에 등록한다. 공유 코어는 리다이렉션, `tee`, `touch`, `cp`, `mv`, `install`의 쓰기 대상만 식별한다. 읽기 전용 명령의 따옴표 예시와 heredoc 본문 언급은 막지 않으며 상대 경로는 hook cwd 기준으로 해석한다. 이는 정적 best-effort 식별이며 shell 샌드박스가 아니다. 환경 변수를 통한 간접 경로, 실행 중 결합되는 명령, 목록에 없는 파일 쓰기 프로그램은 신뢰할 수 있게 판정할 수 없으므로 Write/Edit로 써야 한다. node나 코어에 오류가 생기면 반드시 stderr에 명시적으로 경고한 뒤 fail-open한다.
- 총원칙은 ‘막지 못하는 한이 있어도 잘못 차단하지 않는다’이다. 판정 자체가 불확실하면 exit 0을 반환한다. 그러나 기반 요소의 부재(node 없음)가 조용한 허용으로 바뀌어서는 안 된다.
- 같은 작업에서 확정한 발견 경계: 작품 디렉터리는 프로젝트 아래 4단계까지만 찾고 숨김 디렉터리와 `node_modules`는 가지치기한다. `.active-book`은 realpath로 포함 관계를 비교하며 symlink로 프로젝트 루트 밖을 가리킬 수 없다.

출처: 739a427 (#243), 3174916 (#348), 603de4a (#239)

## Alternatives considered

- **코어 통합 후 node에 전적으로 의존하고 없으면 허용**: 구현이 하나라 불일치가 없다는 장점이 있으며 advisory hook 세 개는 실제로 이런 대체 방식을 쓴다. 그러나 네이티브 바이너리 설치에는 node가 없어 ‘상세 개요 없이 본문 쓰기’를 조용히 허용하게 된다. 실제로 발생해 수정한 회귀이므로 채택하지 않는다.
- **python heredoc 대체 경로**: 코어 통합 전 방식으로 node에 전혀 의존하지 않는다는 장점이 있다. 그러나 수동 복제 로직을 다시 만들어 이번에 세운 코어 통합 회귀 검사 경계를 깨므로 채택하지 않는다.
- 저장소 이력에는 ‘Bash 경로도 fail-closed로 처리’하는 대안을 검토한 기록이 없다. ‘샌드박스가 아니다’라는 역할 정의만 확인된다.

## Consequences

- **이점**: Python은 있고 node는 없는 환경과 고장 난 node 환경 모두에서 차단 검사가 fail-closed를 유지한다. Bash를 통한 본문 쓰기도 검사 범위에 포함된다.
- **비용과 알려진 한계**: 순수 bash 추출은 코어 밖의 두 번째 구현이다. parity 테스트가 ‘같은 쓰기를 bash가 막는가 == JS 코어가 막는가’를 상황별로 고정한다. Bash의 간접 쓰기는 필연적으로 일부 놓치며 사용자에게는 경고만 보인다. Claude Code가 node 존재를 보장하거나 hook이 구조화된 쓰기 대상을 받을 수 있게 되면 bash 대체 경로의 필요성을 재검토해야 한다.

## 검증

`bash scripts/check-story-setup-deployment.sh`의 TS11b(항상 0이 아닌 값으로 종료하는 가짜 node)와 TS11c(`node -e ''`는 0, 스크립트 실행은 0이 아닌 값으로 종료하는 고장 난 node)는 상세 개요가 없으면 여전히 exit 2인지 단언한다. `bash scripts/test-prose-net-parity.sh`는 heredoc python이 없고 `story_hook_cli.js`를 통해 코어를 호출하는지 단언한다.
