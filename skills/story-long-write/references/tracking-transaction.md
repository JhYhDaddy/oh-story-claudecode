# 추적 상태 프로토콜

`추적/`는 구조화 state를 권위 자료로 삼고 스크립트가 Markdown 뷰를 생성한다. 모델은 의미를 담은 JSON 하나만 제출하며 여러 추적 파일을 각각 `Write/Edit/echo >>`하지 않는다.

## 권위 계층과 파생 계층

| 계층 | 파일 | 의미 |
|---|---|---|
| 유일한 권위 | `_tracking-state.json` | schema·최종 커밋 장·가져오기 종료 장·상태 수정 번호·컨텍스트 구조·인물/복선/시간선·커밋된 장의 짧은 글자 수 기록 |
| 장 기록 | `장별기록/제NNN장.md` | 이번 장에서 향후 연속성에 유용한 압축 변화. 목표 ≤1536바이트, 하드 상한 3072바이트. 가져온 범위의 수정은 덮어쓴 기록으로 저장 |
| 파생 뷰 | `문맥.md`, `인물상태/{角色名}.md`, `복선.md`, `시간선/작가용진실.md`, `시간선/독자가아는사실.md` | 전부 `_tracking-state.json`에서 생성. 직접 수정 금지, 프로그램 입력으로 사용하지 않음 |

Markdown은 작가와 에이전트가 읽는 용도이며 도구가 역으로 해석하지 않는다. `check`는 `_tracking-state.json`에서 다시 렌더링해 파일별로 비교한다. 미래의 어느 장에서 공개할지에 관한 계획은 권 개요/상세 개요에 쓰고 시간선의 기정사실로 쓰지 않는다. 장별 기록은 사람이 읽기 편한 압축 변화 기록일 뿐, 이것만으로 전체 현재 상태를 손실 없이 복원한다고 보장하지 않는다. 완전한 현재 의미는 `_tracking-state.json`을 따른다.

## 도구 실행

환경에 맞는 Python 3을 `python3`, `python`, `py -3` 순서로 찾는다. 추적 트랜잭션 스크립트는 현재 skill 루트를, 글자 수와 장 마무리 절차는 모두 `story-long-write` skill 루트를 사용한다.

```text
{PYTHON} {当前 skill 根}/scripts/tracking_commit.py init   --project {书项目根} --input {书项目根}/.story/work/init.json
{PYTHON} {当前 skill 根}/scripts/tracking_commit.py check  --project {书项目根}
{PYTHON} {当前 skill 根}/scripts/tracking_commit.py draft  --project {书项目根} --chapter {N}
{PYTHON} {story-long-write skill 根}/scripts/storyctl.py chapter check   --project {书项目根} --chapter {N} [--min-chars {下限} --max-chars {上限}]
{PYTHON} {story-long-write skill 根}/scripts/storyctl.py chapter commit  --project {书项目根} --chapter {N} --input {书项目根}/.story/work/제{NNN}장/tracking.json
{PYTHON} {story-long-write skill 根}/scripts/storyctl.py chapter accept-current-length --project {书项目根} --chapter {N} --input {书项目根}/.story/work/제{NNN}장/tracking.json
```

- `init`: `_tracking-state.json`이 없을 때만 실행하고 초기화된 프로젝트는 절대 덮어쓰지 않는다.
- `draft`: 현재 state로 장 트랜잭션을 `.story/work/제NNN장/tracking.json`에 미리 채운다. 수정 번호·모드·장 제목·현재 `context` 4개 값을 채우고 각 텍스트 필드의 길이 상한과 현장 핵심 인물의 현재 스냅샷을 출력한다. 새 장(append)은 호출자가 `delta`와 변화한 인물 스냅샷만 채운다. 커밋된 장(revision)은 기존 장 기록에서 `delta`와 관련 인물 스냅샷을 미리 채우되 복선·시간선은 현재 값을 쓴다. 호출자는 이를 수정 후의 완전한 기록으로 고치며 비우고 다시 쓰지 않는다.
- 작가의 글자 수 범위: 작가가 상하한을 명시하면 상세 개요에 `字数范围：2000-2600` 같은 행을 쓸 수 있다. 이번 작업에만 준 범위는 `--min-chars` / `--max-chars`를 함께 주며 상세 개요보다 우선한다. `wordcount check` / `checkpoint`, `chapter check` / `commit` / `accept-current-length` 모두 인식한다. 지정하면 기본 내부 범위 ±12%와 사용자 범위 ±15%를 동시에 대체한다. 결과의 `band_source`는 `author`이고 커밋 글자 수 기록에 `author_range`가 추가된다.
- `wordcount measure` / `wordcount checkpoint`: 순수 측정 진입점이다. 본문·tracking을 쓰거나 의미 판단을 하지 않는다. 장편 본문은 앞 묶음 완성 후 주 세션이 `--project`를 붙여 `checkpoint`를 한 번만 호출한다. 목표·범위는 상세 개요에서 읽으며 workflow-chapter의 6단계를 참조한다. 전체 장 길이는 `chapter check`로 확정한다. `remaining_user_range`는 유효 범위, 즉 작가 범위 또는 기본 사용자 범위로 계산한다.
- `chapter check`: 현재 본문·상세 개요 목표를 다시 읽고 결정적 길이 상태·기존 blocking quality·`state_revision`·현재 가능한 행동을 반환하며 approval은 저장하지 않는다. 최상위 `status`는 `ready`(커밋 가능, exit 0), `needs_decision`(길이 범위 밖, `available_actions`를 작가에게 제시, exit 0), `blocked`(차단 본문 문제, exit 1), `invalid`(빈 본문 등, exit 1), `tool_unavailable`(node 또는 검사 스크립트 없음, `quality.tool_errors` 참조, 본문 문제가 아니며 exit 3)이다. 인수 오류·파일 누락은 `story-chapter-error/v1`(`status: error`, exit 2)을 출력한다. `under`에는 자동 보충 집필을 제공하지 않는다. `over`에는 한 번의 순삭제 `compress-once`와 유효 범위 복귀에 필요한 삭제 글자 수를 추가 반환한다. `quality.semantic_advisories`는 의미 관련 advisory 수이며 검사기가 `review: mechanical`로 표시한 것은 세지 않는다.
- `chapter commit`: 현재 파일을 다시 읽고 다시 세며 blocking quality를 다시 검사한다. 유효 범위 안의 장만 받아 짧은 글자 수 기록과 장 트랜잭션을 원자적으로 함께 커밋한다. 새 장·수정 모두 이 명령을 쓴다.
- `chapter accept-current-length`: 범위 밖이지만 quality pass인 장만 받는다. 수락 시점에 다시 읽고 다시 세며 즉시 원자적으로 커밋한다. 오래되어 무효가 될 수 있는 과거 결정을 저장하지 않는다. 목표의 절반 미만(`BELOW_ACCEPT_FLOOR`)이거나 초과인데 한 번의 압축을 아직 하지 않았으면(`COMPRESSION_REQUIRED`) 거부한다. 작가가 명시적으로 결정했을 때 `--force`를 붙인다.
- `check`: state schema·장별 기록 연속성/정규명/크기·고정 7칸·인물 스냅샷 하드 상한·파생 파일 집합·모든 파생 뷰와 state의 글자 단위 일치를 엄격히 검증한다.

작품마다 `추적/.tracking-commit.lock`으로 트랜잭션 쓰기를 직렬화하고 `expected_state_revision`으로 옛 상태에서 만든 stale transaction을 거부한다. 다른 트랜잭션 둘이 동시에 실행되어도 최대 하나만 수정에 성공한다. 글자 수 기록도 잠금 안에서 현재 본문·목표를 다시 검사하므로 둘 중 하나가 바뀌면 미리 만든 기록은 실패한다.

트랜잭션 JSON은 임시 입력이며 프로젝트 산출물이 아니다. 작품 디렉터리의 `.story/work/` 아래에만 쓰고 장 트랜잭션은 `.story/work/제NNN장/tracking.json`에 둔다. 시스템 `/tmp`·작품 루트·`개요/`·`본문/`에는 쓰지 않는다. 성공 전에는 보존하고 커밋 성공 후 삭제한다. `storyctl.py chapter commit` / `accept-current-length`는 성공 시 해당 장 디렉터리를 자동 삭제하고 `tracking_commit.py commit` 직접 호출은 호출자가 지운다. 글자 수 기록이 있는 장의 본문·목표가 바뀌면 `tracking_commit.py commit`은 수정 트랜잭션을 거부하므로 `storyctl.py chapter commit`을 사용해야 한다. 이후 `check` 실패는 아래 방식으로 새 `mode=revision` 트랜잭션을 제출해 고치며 원래 트랜잭션은 필요 없다. 파일 쓰기가 실패하면 `_tracking-state.json`은 아직 전진하지 않았다. 환경을 바로잡고 **같은** `commit`을 다시 실행한다. append 재실행은 기존 장별 기록의 내용이 완전히 같은 경우만 받으며 `dirty/pending/repair` 상태 머신을 유지하지 않는다.

검증 실패와 쓰기 실패의 처리는 다르다. 필드 오류·폐기된 구조·용량 초과 같은 검증 실패는 오류에 따라 트랜잭션 자체를 고쳐야 하며 같은 것을 다시 실행해도 결과는 같다. 파생 뷰를 직접 또는 외부에서 바꿔 `check`가 `derived view differs from _tracking-state.json`을 보고하면 **해당 장**의 `mode=revision` 트랜잭션을 다시 제출해 전체를 재구축한다. `expected_state_revision`은 `추적/_tracking-state.json`의 `state_revision`에서 가져온다. `check` 실패 시 stderr에 ERROR만 쓰며 JSON은 출력하지 않는다. 파생 파일을 직접 고치거나 `_tracking-state.json`을 삭제해 다시 시작하지 않는다. 수동으로 쓴 장별 기록은 같은 장의 append에서 계속 `chapter delta N already exists with different content`를 발생시킨다. 그 수동 파일을 삭제하고 원래 트랜잭션을 재실행하면 된다.

도구는 옛 `_tracking-meta.json`, `시간선/사건목록.json`, 더 오래된 추적 구조를 해석하지 않으며 의미 호환 계층도 제공하지 않는다. `init`이 이를 만나면 먼저 원형 그대로 `추적/_이전추적보관/`에 통째로 옮기고 원래 위치에 현재 프로토콜을 만든다. 옛 자료는 작가 열람용으로 남고 해석에는 참여하지 않는다. 현재 상태는 init 입력을 전적으로 따른다. 검증에 실패한 init은 아무 파일도 옮기지 않는다. `commit`과 `check`는 여전히 옛 구조를 즉시 거부하며 현재 프로토콜이 구축된 프로젝트에서만 실행한다.

## 초기화 트랜잭션

새 작품 또는 가져오기 초기화에서만 init 전에 [tracking-initialization.md](tracking-initialization.md)를 끝까지 읽고 원래 JSON·가져오기 경계에 맞춰 트랜잭션을 만든다. 기존 프로젝트 이어쓰기는 아래 장별 트랜잭션을 바로 사용하고 초기화 예시를 다시 읽지 않는다.

호출자의 장별 JSON에는 `wordcount`를 쓰지 않는다. 정식 진입점인 `chapter commit` 또는 `chapter accept-current-length`가 커밋 시점에 만들어 주입한다. 최종 state는 커밋된 장의 `metric / target / actual / status / resolution / body_sha256`만 보존하고 작가 글자 수 범위가 유효하면 `author_range`를 추가한다. MEASURE/RESOLVE 이벤트·ID 사슬·policy fingerprint·독립 chapter state는 저장하지 않는다.

## 장별 트랜잭션

예시의 인물 식별자와 상태 열거값은 데이터 계약을 위해 유지하며 설명 내용은 한국어로 적었다.

```json
{
  "schema_version": 1,
  "mode": "append",
  "chapter": 10,
  "chapter_title": "전문 팀이 찍은 영상이 그보다 못하다고?",
  "expected_state_revision": 9,
  "delta": {
    "result": "간부 시사회에서 전문 팀의 고화질 재촬영본에 영혼이 없다는 평가가 나오고, 장야오쭈는 장천의 휴대전화 원본을 계속 쓰기로 결정했다.",
    "character_changes": [
      {"name": "江晨", "change": "군 간부에게 작품 가치를 인정받아 인기 신인에서 대체 불가능한 군 홍보 창작자로 올라섰다"}
    ],
    "foreshadow_changes": [
      {
        "action": "upsert",
        "id": "F027",
        "summary": "전문 팀도 장천 원본의 영혼을 재현하지 못해 그의 창작 능력이 복제 불가능함을 다시 입증한다",
        "planted_chapter": 10,
        "planned_resolution_chapter": null,
        "status": "已埋",
        "importance": "中"
      }
    ],
    "timeline_events": [
      {
        "action": "upsert",
        "id": "E010",
        "story_time": "실탄 훈련 이틀 후",
        "objective_fact": "문예단 간부들이 전문 재촬영본을 기각하고 장천의 휴대전화 원본을 계속 사용하기로 했다",
        "reader_knowledge": "독자는 저우보썬이 전문 촬영본의 영혼 부재를 지적하고 장야오쭈가 현장에서 원본 사용을 결정하는 것을 보았다",
        "reveal_status": "已揭示",
        "reveal_chapter": 10,
        "characters": ["江晨", "周薄森", "张耀祖"]
      }
    ],
    "constraints": ["이후에도 작품의 실제 효과와 주변 반응으로 장천의 활약을 확대하며 시스템 보상 숫자만 쓰지 않는다"],
    "next_chapter_commitments": ["5일 안에 팔로워 100만 명 임무를 결산하고 참전 용사 주제의 새 임무로 잇는다"]
  },
  "context": {
    "position": {
      "volume": "제1권·군 홍보 개편",
      "volume_start_chapter": 1,
      "story_time": "실탄 훈련 이틀 후",
      "scene": "로켓군 문예단 간부 시사회"
    },
    "long_term_constraints": ["군 홍보의 쾌감은 작품 효과와 주변 반응 사슬로 실현하며 시스템 알림에만 의존하지 않는다"],
    "active_character_names": ["江晨"],
    "continuity_risks": ["중자자가 장천이 절반만 맞혔다고 말했으므로 공개되지 않은 육성 계획을 독자가 아는 사실로 취급하면 안 된다"]
  },
  "character_snapshots": {
    "江晨": {
      "identity": "로켓군 문예단 홍보병, 인기 군 홍보 창작자",
      "location": "로켓군 문예단 간부 시사회",
      "goal": "5일 안에 팔로워 100만 명 임무를 완수하고 실제 경쟁력 있는 군 홍보 콘텐츠를 계속 만든다",
      "state": "전문 팀이 역으로 원본 가치를 입증하며 군 내부의 인정이 높아진다",
      "abilities_resources": ["전생의 MCN 인기 콘텐츠 운영 경험", "《중국군혼》 반주", "거장급 연출 능력"],
      "relationships": ["중자자가 군보 자원을 계속 제공한다", "저우보썬과 장야오쭈가 창작 능력을 명확히 인정했다"],
      "knowledge": ["《군보》 인터뷰 원고가 심사를 통과했다", "원본 영상을 정식 군 홍보 콘텐츠로 계속 사용한다"],
      "open_threads": ["5일 안에 팔로워 100만 명 임무가 아직 결산되지 않았다", "중자자가 말한 절반만 맞혔다는 뜻은 아직 밝혀지지 않았다"]
    }
  }
}
```

제약:

- 트랜잭션 구성 전 `check`를 실행하고 현재 `state_revision`을 `expected_state_revision`에 그대로 넣는다. 상태가 바뀌었으면 state를 다시 읽고 트랜잭션을 다시 만든다.
- 허용 `context` 필드는 하위 명령마다 다르다. `init`은 `position`, `long_term_constraints`, `active_character_names`, `continuity_risks`, `recent_chapters`, `next_chapter_commitments` 6개를 받으며 `commit`은 앞의 4개만 받는다. 나머지 두 필드는 commit 때 현재 뷰와 이번 장 `delta`에서 도구가 파생한다. 직접 채우면 쓰기 전에 `context contains unsupported fields: ...`, exit 2로 거부한다. commit은 자체 허용 필드를 사용하며 init 예시를 그대로 복사하지 않는다.
- `character_snapshots`에 있는 인물은 핵심 재사용 인물로 간주하며 `character_changes`에도 있어야 한다. 이미 스냅샷이 있는 핵심 인물이 다시 변하면 새 스냅샷을 제출한다.
- 인물 스냅샷의 목록 4개는 항목 수를 제한하지 않고 개별 길이와 최종 파일 바이트 수만 제한한다. 목표 ≤4096바이트를 넘으면 경고, 하드 상한 8192바이트를 넘으면 쓰기 전에 거부한다.
- 스냅샷 없는 인물 변화는 임시 인물로 보아 상태 파일을 만들지 않는다. `context.active_character_names`는 다음 장의 활동 인물이지 핵심 인물 총수나 주인공 수가 아니다. 최대 20명이며 현재 스냅샷이 있어야 한다. 다음 장에 등장하거나 직접 영향을 받는 핵심 인물만 넣는다. 나머지도 스냅샷은 유지하며 필요할 때 `추적/인물상태/{名}.md`를 읽는다.
- `context.long_term_constraints`는 최대 6개다. 7번째를 넣기 전에 의미가 겹치는 항목을 합치거나 작가에게 선택을 요청하며 옛 제약을 자동 삭제하지 않는다. 영구 설정 판정은 여기에, 단기의 강한 약속은 `next_chapter_commitments`에 넣고 과정상의 결정은 이어쓰기 상태 카드에 넣지 않는다.
- `context.long_term_constraints`와 `context.continuity_risks`는 현재 값 전체를 제출한다. 이전 판에는 있고 이번에는 없는 항목은 각각 `delta.retired_context_items`에 나열해야 하며 그렇지 않으면 쓰기 전에 거부한다. 누락을 삭제로 보지 않는다. 실제 폐기 항목은 도구가 이번 장 기록의 `## 本章退役登记`에 써 두어 나중에 조회할 수 있다.
- 재사용하지 않을 핵심 인물은 `delta.retired_characters`에 쓴다. 도구는 현재 스냅샷·`인물상태/{角色名}.md`를 삭제하고 장 기록에 보관한다. 같은 트랜잭션에서 폐기와 스냅샷 제출을 동시에 하거나 `context.active_character_names`에 남은 인물을 폐기할 수 없다. 인물이 사망·퇴장하는 장에는 변화를 `character_changes`에 그대로 쓰면 되며 곧 삭제할 스냅샷을 다시 낼 필요는 없다. 장 기록은 계속 핵심 인물로 표시한다. 폐기는 현재 활성 컨텍스트에서 빠진다는 뜻일 뿐 본문·장 기록에는 영향이 없다.
- 두 종류의 폐기는 모두 `mode=append`에서만 제출한다. 폐기는 현재 시점부터 현재 상태에서 빠진다는 뜻이다. revision의 장 기록은 고친 옛 장에 속하므로 거기에 쓰면 폐기 발생 장을 잘못 보고하게 된다. `mode=revision`은 현재 컨텍스트 항목 전체를 그대로 다시 제출하고 폐기는 다음 append에서 한다.
- `복선.md`는 이미 심은 복선의 현재 상태만 표시하며 미래 계획은 개요에 남긴다.
- `timeline_events.action`은 `upsert/delete`다. `未揭示`(미공개)의 `reveal_chapter`는 반드시 `null`이고 부분/완전 공개에는 이미 발생한 실제 장만 쓴다.
- `mode=revision`에서는 수정 후 그 장에 여전히 성립하는 완전한 연속성 기록으로 장별 기록을 다시 계산한다. `draft`가 미리 채운 초안을 고치며 빠뜨린 항목은 기록에서 사라지고 도구가 비워진 칸을 stderr에 경고한다. 기존 폐기 등록은 그대로 보존한다. 현재 인물·복선·시간선·컨텍스트에는 영향을 받은 대상의 최신 집필 장까지의 현재 값을 제출한다.
- 가져오기 종료 장 이내의 본문을 고치면 해당 장의 기록이 추가되거나 덮어써지며 `imported_through_chapter`는 바뀌지 않는다.

## 이어쓰기 상태 카드의 고정 형식

`문맥.md`는 ≤12288바이트이며 state에서 전체 생성한다. 최상위 구역은 아래 7개뿐이다. 제목은 생성 계약이므로 원형을 유지한다.

1. `## 当前位置`: 현재 위치
2. `## 长期约束`: 장기 제약
3. `## 核心角色状态`: 핵심 인물 상태
4. `## 活跃伏笔`: 활성 복선
5. `## 近三章速记`: 최근 3장 간단 기록
6. `## 下一章承诺`: 다음 장 약속
7. `## 连贯性风险`: 연속성 위험

활동 인물은 최대 20명, 활성 복선은 결정적으로 최대 8개를 고르며 최근 장은 3개만 남긴다. 이는 다음 장의 활성 컨텍스트 용량이며 전체 인물 상태의 용량 제한이 아니다. 인물이 많고 상태 행이 길면 바이트 상한에 먼저 닿을 수 있다. 초과하면 상태 행을 먼저 줄이고 그다음 인원 수를 줄인다.
