# Agent Note: 작가용 보고는 개발 세부 대신 이야기를 설명

Status: implemented

## Problem

실제 세션 테스트의 작가 보고에는 이해하기 어렵고 필요도 없는 개발 정보가 가득했다. `check-ai-patterns.js` 같은 스크립트별 통과·실패 목록, `visible_chars_v1`, `last_committed_chapter`, `state_revision` 필드·상태, S1–S4·Gate·“7 Gate” 같은 내부 목록·심각도 코드, 이야기 설명 없는 F057·E015·REL-001 번호, 선택지로 제시한 `accept-current-length` 플래그까지 있었다. story-import 완료 보고는 `visible_chars_v1`, `imported_through_chapter=6`, F001–F007 / E001–E010, “`tracking_commit.py init`과 `check` 모두 통과”를 썼지만 작가는 무엇을 확인하고 다음에 무엇을 말해야 할지 몰랐다.

원인은 두 가지다. 템플릿이 내부 구조를 그대로 노출했다. story-review 머리말은 `Requested Mode` / `Effective Mode` / `Fallback` / `Rubric Source`를 그대로 출력하도록 강제하고 Severity Counts는 S1–S4를 썼다. deslop 표에는 Gate 열, 가져오기 보고에는 “유일한 구조화 state＋파생 스냅샷＋고정 7칸 컨텍스트”가 있었다. 또 쓰면 안 되는 내용을 명시하지 않아 모델이 내부 자체 검사·명령까지 작가에게 읽어 주었다.

## Decision

- **작가를 위한 보고**: 모든 작가용 보고·메시지 템플릿은 한 일(이야기 용어), 발견한 점(쉬운 말＋작가 원문 예시), 작가가 정할 것(질문＋자연어 선택지＋추천 기본값), 다음에 할 말의 네 가지를 다룬다. 스크립트·필드·플래그·상태 코드·내부 목록명은 본문에 넣지 않고 번호는 “이야기 설명(ID)”으로만 쓴다. 검토 축소 사유나 작가 메모리 응답 같은 필요한 실행 내역은 블록 끝의 “기술 비고:” 한 줄에 둔다.
- **템플릿 명시적 표식**: 작가용 템플릿은 일반 ```` ```md ```` 블록에 쓰고 바로 앞줄에 `<!-- author-report -->`를 붙인다. `scripts/check-author-reports.py`는 표식 바로 뒤 블록만 검사해 알려진 내부명, 스크립트·설정 파일명, flag, snake_case / kebab-case 식별자(`/story-*`, `$story-*` 제외), 영어 개발 용어, S1–S4, Gate, 설명 없는 번호를 차단한다. 끝의 기술 비고는 예외지만 한 줄만 허용한다. 번호는 이야기 라벨과 함께 “설명(ID)” 또는 “ID(설명)” 둘 다 허용한다. `REQUIRED`는 필수 템플릿 파일과 최소 블록 수로 표식 삭제를 방지한다. 작가 메모리 응답은 예외다. 전체가 두 줄인 답변을 블록으로 쓰니 모델이 블록까지 그대로 반환했다(출시 전 실측 2/2). 인라인 예시로 바꾸자 2/2가 평문 두 줄이어서 `author-memory.md`는 코드 블록과 `REQUIRED`에서 제외한다. 처음에는 블록 정보 문자열을 `author-report`로 썼는데 실제 원고 검토가 블록까지 통째로 반환했다. 같은 책의 v0.7.10 ```` ```md ```` 템플릿은 그렇지 않았고 “표식 행＋```` ```md ````”로 바꾼 뒤 평문으로 나왔다(각 1회). 이제 검사는 예전 `author-report` 정보 문자열을 거부한다. 검사는 `cross-platform.yml`의 static-check job에 등록하고 `--self-test`에 양성·음성 사례를 둔다. 규칙과 담당 검사는 하나뿐이며 `static-check.py`는 블록을 별도로 훑거나 어휘 목록을 유지하지 않는다. 이전 두 목록은 번호 형식 요구가 반대이고 각각 누락 용어도 있었다. 나중에 같은 규칙을 두 번 실행한 방식도 단순 중복이었다.
- **이번 대상 스킬**:
  - story-review: “작가용 보고” 절을 추가한다. S1은 필수 수정, S2는 수정 권장, S3/S4는 수정 선택으로 옮긴다. reviewer명과 APPROVE/CONCERNS는 “검토 방식”, “종합 판단”으로 바꾸고 “결정해 주세요”, “판단할 수 없는 부분”을 추가한다. Mode / Fallback / Rubric은 끝 기술 비고에 둔다. Findings Schema는 reviewer와 종합 판단 사이의 내부 형식으로 보존한다.
  - story-import: 완료 보고를 “가져온 내용 / 정리한 내용 / 확인할 내용 / 결정할 사항 / 다음: ‘일일 집필’이라고 하면 제N+1장부터 이어쓰기”로 바꾼다. 품질 목록은 작가에게 읽어 주지 않는 자체 검사라고 명시한다. 미배포 환경의 두 선택지와 비교 자료 누락 안내도 쉽게 바꾼다.
  - story-deslop: 문제 표의 Gate 열을 없애고 환산은 내부 집계 설명에 남긴다. 교정 결과는 등급 → 바뀐 내용 → 글자 수 → 전후 비교 → 확인할 사항 순서다.
  - story 라우터·작가 메모리 프로토콜: “작가에게 응답하기”를 추가한다. 먼저 “기억했습니다. 《작품명》의 대화에는 항상 「」를 쓰겠습니다” 같은 문장을 쓰고 기계 응답은 기술 비고에 둔다. 예산 경고를 붙이지 말고 본문 집필 때 챙기지 못할 수 있는 습관을 설명한다. 조회 대체에서 `Fallback: agent unavailable -> direct lookup`을 내세우지 않는다. 프로토콜은 `author-memory-reference` 공유 그룹의 canonical이며 네 복사본은 `shared-references.py sync`로 동기화한다.
  - story-short-analyze: 재개 세 선택지·완료 메시지는 필드·Stage 번호 없이 작가에게 묻는다. 구조 수가 기준 미달이면 먼저 자체 보완하고 불가능할 때만 이야기 용어로 부족한 것을 알린다.
  - story-long-scan / story-short-scan: 조사 보고에 작가 템플릿 표식을 붙이고 수집 실패 순위는 스크립트명·SKIP 대신 한 문장으로 설명하도록 한다. 단편 보고에는 진입부가 요구하는 신뢰도·재조사 시점을 보완한다.
  - story-cover: 전달 메시지 템플릿을 추가하고 출력 디렉터리 질문에 `BOOK_DIR` 변수명을 내세우지 않는다.
- story-long-write, story-long-analyze, story-short-write, story-setup 보고는 병렬 변경에서 같은 원칙으로 다루며 여기서는 세부를 다루지 않는다.

## Alternatives considered

- **모든 스킬 문서의 개발 용어 전수 검사** — 표식 관리 없이 범위가 가장 넓다. 그러나 SKILL.md는 에이전트 작업 지침이므로 스크립트·필드가 필수이며 전수 검사는 오탐과 허용 목록만 늘려 의미가 없다.
- **런타임 모델 출력 후처리 필터** — 템플릿이 아니라 실제 작가 전달문을 차단한다. 그러나 제품은 Markdown 워크플로로 공통 출력 차단 계층이 없고 호스트별 훅 능력도 다르다. 필터는 단어를 삭제할 뿐 F003을 “옥패의 유래”로 바꾸지 못한다.
- **기술 비고 없이 개발 세부 전체 삭제** — 작가 화면은 가장 깔끔하다. 그러나 검토 축소 사유·메모리 응답은 버그 보고와 실제 저장 확인에 유용하다. 끝 한 줄이면 읽기를 방해하지 않고 확인할 수 있다.
- **S1–S4 유지＋중국어 설명** — 내부 schema와 1:1 대응해 정렬이 명확하다. 그러나 작가에게는 수정 여부의 쉬운 세 등급이면 충분하다. 내부 정렬은 S1–S4를 유지하고 종합 판단 후 표현을 바꾼다.

## Consequences

- **이점**: 작가는 보고만 읽고 확인·결정·다음 요청을 알 수 있다. 템플릿 추가·수정 때 흔한 개발 용어는 CI가 차단한다.
- **비용과 한계**: 표식 블록만 검사하므로 모델의 즉흥 답변에는 내부 용어가 섞일 수 있어 원칙 문장에 의존한다. “파생 뷰”, “고정 7칸” 같은 중국어 개발 표현은 검사로 못 잡아 수동 검토가 필요하다. 영어 용어 목록·번호 정규식은 새 용어에 맞춰 늘려야 한다. story-deslop SKILL.md는 순감 약 185자로 예산 안이며 story-review·story-import는 상시 경로 예산 표에 없다.

## 검증

`python3 scripts/check-author-reports.py --self-test`; `python3 scripts/check-author-reports.py`; `bash scripts/check-shared-files.sh`(작가 메모리 복사본 네 개 일치); `bash scripts/check-doc-budget.sh`.
