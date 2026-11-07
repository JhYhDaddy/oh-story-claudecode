# Agent Note: 장별 임시 파일을 책 내부 .story/work/에 모으고 제출 성공 후 자동 정리

Status: implemented
Date: 2026-09-24

## Problem

workflow-chapter는 집필자에게 “먼저 앞 묶음 임시 segment 작성”, `build_writer_prompt.py … --out {留档文件}`, 장별 트랜잭션 JSON 구성을 요구하지만 파일을 어디에 저장할지는 정하지 않았다. 실제 세션에서 다음 문제가 발생했다.

- 모델이 전역 `/tmp/ch22_seg1.md`, `/tmp/ch1_front.md`, `/tmp/ch1_writer_prompt.md`에 작성했다. 여러 책이나 세션이 같은 장 번호를 쓰면 서로 덮어쓰며 Windows에는 `/tmp`도 없다.
- 다른 세션에서는 `_seg_001_a.md`를 `正文/`에 넣어 본문 디렉터리를 오염시켰다. 파일명이 `第001章_前组.md` 형태이면 `wordcount_core.find_chapter_file`이 “같은 장의 본문이 둘 이상”이라고 판단하여 `chapter check/commit`이 실패하며 `detect-story-gaps.sh`도 이를 한 장으로 센다.
- 또 다른 세션에서는 제출 후 `大纲/_tx_ch1.json`, `大纲/_writer_prompt_ch1.md`를 남겼다. 정리 규칙은 “세 장마다 중간 스냅샷”인 단계 13에 있어 단일 장이나 1–2장 묶음은 도달하지 못했다.

## Decision

1. 저장 위치는 책 디렉터리 아래 `.story/work/第NNN章/`로 통일한다. 장 번호는 장별 기록과 같은 세 자리로 0을 채운다. 파일명은 `前组.md`, `后组.md`, `writer_prompt.md`, `tracking.json`으로 고정한다. workflow-chapter 상단 “작업 디렉터리”, workflow-daily 트랜잭션 단계, tracking-transaction(story-import / story-review 복사본 동기화), project-files 디렉터리 트리, narrative-writer 템플릿(OpenCode / Codex 어댑터 재생성)에 같은 기준을 적용한다.
2. `build_writer_prompt.py`에서 `--out`에 값을 주지 않으면 `.story/work/第NNN章/writer_prompt.md`에 기록하고 상위 디렉터리를 자동 생성한다. 실행 배치 칸에 앞 묶음·뒤 묶음의 절대 경로를 직접 적어 집필자가 경로를 임의로 만들지 않게 한다.
3. `storyctl.py chapter commit` / `accept-current-length`는 트랜잭션 제출 성공 후 `.story/work/第NNN章/`를 삭제한다. 이어 `.story/work`, `.story`가 비었으면 함께 삭제하고 `work_dir_removed`를 반환한다. `.story/作者记忆/`가 있으면 건드리지 않는다. 범위 이탈, blocking, 무효 트랜잭션으로 제출이 거부되면 재실행을 위해 디렉터리를 그대로 남긴다. 정리 실패는 반환값의 `work_dir_cleanup_error`로만 알리고 이미 저장한 제출을 실패로 보고하지 않는다.
3a. 트랜잭션 명령 예시에서 추상적인 자리표시자를 없앤다. tracking-transaction(복사본 세 개)과 story-import의 `--input`에는 `{书项目根}/.story/work/init.json`, `{书项目根}/.story/work/第{NNN}章/tracking.json`을 직접 쓴다. 출시 전 새 책 최초 초기화 실측에서 모델이 `{初始化事务.json}` 자리표시자를 따라 `/tmp/claude-story-init/init.json`에 트랜잭션을 썼기 때문이다.
4. 문서의 “제출 성공 후 정리”를 단계 13에서 단계 12로 옮긴다. 작가가 “이 장은 버림”을 선택하면 본문과 작업 디렉터리를 삭제한다.
5. 회귀 검사: `test-chapter-completion-lifecycle.py`는 “거부 시 보존 → 성공 시 삭제 → 작가 메모리 영향 없음 → 본문 디렉터리에 한 장만 남음”을 검증한다. `test-writer-pipeline.py`는 값 없는 `--out`의 기록과 실행 배치의 경로를 검증한다.

## Alternatives considered

- **`追踪/.work/`**: 트랜잭션 JSON과 가장 가깝고 dashboard가 점 디렉터리를 기본적으로 숨긴다. 그러나 `追踪/`는 모두 `_tracking-state.json`에서 파생되어 수동 수정을 금지하는 파일이다. 직접 작성하는 초안을 섞으면 규칙이 흐려진다. `init`이 이전 구조를 옮길 때도 이 디렉터리에서 파일을 이동하므로 경계가 명확해야 한다.
- **시스템 임시 디렉터리(`tempfile`)**: 여러 플랫폼에서 사용할 수 있고 책 디렉터리를 오염시키지 않는다. 그러나 매번 경로가 달라 트랜잭션 실패 후 같은 JSON을 그대로 재실행하려면 파일을 다시 찾을 수 있어야 한다. 세션 사이에도 경로를 합의할 수 없어 모델이 계속 임의로 만든다.
- **책마다 평평한 `.story/work/` 디렉터리를 두고 파일명에 장 번호 포함**: 디렉터리 한 단계를 줄인다. 그러나 정리할 때 파일명 패턴을 맞춰야 하고 `第001章_前组.md` 같은 이름은 본문 명명 방식과 충돌한다. 장별 디렉터리는 파일을 추측하지 않고 전체 디렉터리를 삭제할 수 있다.
- **문서만 수정하고 스크립트 유지**: 변경이 가장 작다. 그러나 원래 문제 자체가 정리 단계를 실행하지 않은 것이므로 제출 스크립트가 성공 때 결정적으로 삭제해야 모델이 기억하는 데 의존하지 않는다.

## Consequences

- 이점: 여러 책·세션이 동시에 실행되어도 파일이 충돌하지 않고 Windows에서도 동작한다. 본문 디렉터리에는 장만 있으므로 장 파싱과 훅이 오판하지 않는다. 제출 성공 후 잔여물이 없고 실패하면 실행 상태가 그대로 남아 재실행할 수 있다.
- 이점: 훅 수정이 필요 없다. 집필 전 검사와 집필 후 보완 검사는 상위 디렉터리명이 `正文`인 `第N章*.md`만 인식한다. 작업 디렉터리는 상세 개요 관문을 유발하지 않는다. `story_hook_core`도 `正文`/`追踪`이라는 디렉터리만으로 책을 찾는다.
- 비용: 책 디렉터리의 `.story/`에는 원래 책별 작가 메모리만 있었지만 이제 `work/`도 일시적으로 나타난다. story 대시보드는 `.story`를 숨기지 않아 집필 중 임시 파일이 보인다.
- 비용: `mode=revision` 트랜잭션은 여전히 `tracking_commit.py commit`을 거치고 storyctl을 거치지 않으므로 자동 정리하지 않고 문서의 삭제 요구에 의존한다. 대규모 수정의 원고 백업은 계속 `正文/`의 `第X章_章名_原稿_日期.md`에 저장하며 이번에는 바꾸지 않았다.
