# Agent Note: 의사결정 기록의 디렉터리·구조를 육안 검토 대신 스크립트로 검사

Status: implemented

## Problem

`.agents/notes/` 규약(상태 디렉터리·분류 디렉터리·날짜 파일명·`Status` 행·필수 절 네 개)은 AGENTS.md에 적혀 있었지만 CI 검증이 전혀 없었다. 첫 골격을 병합하기 전 main에 기록 세 개(#429·#432·#433)가 먼저 들어왔고 그중 하나는 첫 줄의 `# Agent Note:` 접두사가 빠졌으나 검토에서 발견하지 못했다. 규약을 읽는 사람에게만 맡기면 첫 묶음부터 첫 불일치가 발생한다.

## Decision

- `scripts/check-agent-notes.py`가 `.agents/notes/`를 순회하며 검사한다. 경로는 `<status>/<category>/<yyyy-mm-dd-topic>.md`이고 두 디렉터리 이름은 허용 목록에 있어야 한다. 첫 줄은 `# Agent Note: <标题>`(제목 자리표시자)이며 `Status:`는 디렉터리와 일치해야 한다. `## Problem`, `## Alternatives considered`, `## Consequences`는 필수다. `implemented` / `rejected`에는 `## Decision`, `proposed`에는 `## Proposal`이 있어야 하며 둘을 함께 쓸 수 없다. `INDEX.md` / `README.md` 같은 수동 색인을 금지한다. 하나라도 위반하면 종료 코드 1을 반환한다.
- `scripts/test-agent-notes.py`가 임시 디렉터리에 유형별 위반 기록을 만들고 각 유형이 차단되며 정상 기록이 통과하는지 단언한다.
- 두 검사를 `.github/workflows/cross-platform.yml`의 `static-check` 작업에서 `test-static-check.py` 바로 뒤에 연결한다. `scripts/README.md`와 `CONTRIBUTING.md`의 CI 검사 목록도 함께 갱신한다.
- 검증은 형식만 담당하며 내용은 판단하지 않는다. 출처(`来源`) 행, 대안의 실제 존재 여부, Decision과 main의 일치는 검사하지 않는다. 이는 여전히 검토의 역할이다.

출처: 이 PR (#431)

## Alternatives considered

- **AGENTS.md의 글 지침과 검토에만 의존**: 스크립트·관리 비용이 없고 기록은 사람과 에이전트가 읽는 설명이므로 형식이 중요하지 않다는 점이 가장 큰 근거다. 그러나 main의 첫 묶음부터 한 기록이 어긋났으며 에이전트는 기록을 쓸 때 규약을 자동으로 다시 읽지 않는다. 기계적 형식은 스크립트가 가장 잘하고 사람이 가장 쉽게 놓치는 영역이다.
- **`static-check.py`의 Markdown 파서를 재사용해 규칙 추가**: 새 스크립트가 필요 없다는 장점이 있다. 그러나 static-check는 스킬 문서(frontmatter·참조 도달성)를 다루며 기록은 `skills/` 아래에 있지도 않고 frontmatter도 없다. 억지로 넣으면 목표 두 개를 하나의 검사기에 섞게 된다. 독립 스크립트는 80줄이고 경계가 분명하다.
- **출처(`来源`) 행이 실제 커밋을 가리키는지도 검증**: 꾸며낸 기각 대안을 막을 수 있다는 점이 가장 큰 장점이다. 그러나 전체 git 이력이 필요해 얕은 clone에서 오탐이 생기고 proposed 단계에는 출처가 원래 없으므로 검토에 맡긴다.

## Consequences

- **이점**: 형식 불일치는 PR에서 바로 실패하므로 검토자는 내용만 읽으면 된다. 새 상태·분류는 스크립트 허용 목록만 바꾸면 된다.
- **비용과 알려진 한계**: CI 단계 하나가 추가된다(1초 미만). 스크립트는 내용을 이해하지 못해 `Decision`이 희망 사항이거나 `Alternatives`에 허수아비 대안 하나뿐이어도 통과한다. 앞으로 기록이 많아져 색인이 필요해지면 `INDEX.md` 금지와 AGENTS.md 4항을 함께 재판정해야 한다.

## 검증

이 브랜치에서 `python3 scripts/check-agent-notes.py`는 `OK (13 notes)`를 출력하며 `python3 scripts/test-agent-notes.py`의 열 개 사례가 모두 통과한다.
