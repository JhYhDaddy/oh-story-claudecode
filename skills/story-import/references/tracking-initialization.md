# 추적 초기화 트랜잭션

## 초기화 트랜잭션

추적 상태가 아직 없을 때만 초기화한다. 새 작품은 0장에서 시작한다. 아래 JSON을 `{书目录}/.story/work/init.json`에 쓰고 `{PYTHON} {skill 根}/scripts/tracking_commit.py init --project {书目录} --input {书目录}/.story/work/init.json`을 실행한 뒤 성공하면 임시 파일을 삭제한다. `story-import`로 기존 소설을 가져올 때는 마지막 완결 장을 `last_chapter=N`에 기록한다. 1..N장의 일일 집필 기록을 꾸며 만들지 않으며 일반적인 이어쓰기는 N+1장에서 시작한다.

```json
{
  "schema_version": 1,
  "book_title": "계정 관리 맡겼더니 열혈 편집 영상으로 인터넷을 뒤집다",
  "last_chapter": 0,
  "context": {
    "position": {
      "volume": "제1권·군 홍보 개편",
      "volume_start_chapter": 1,
      "story_time": "장천이 로켓군 문예단에 부임하기 전",
      "scene": "로켓군 문예단"
    },
    "long_term_constraints": ["군 홍보의 쾌감은 작품 효과와 구경하는 이들의 반응 사슬로 실현하며 시스템 알림에만 의존하지 않는다"],
    "active_character_names": [],
    "continuity_risks": [],
    "recent_chapters": [],
    "next_chapter_commitments": ["장천을 부임시키고 5일 안에 팔로워 100만 명을 모으는 초보 임무를 부여한다"]
  },
  "character_snapshots": {},
  "foreshadow": [],
  "timeline_events": []
}
```

가져오기 예시는 읽은 본문에 맞춰 현재 상태로 바꿔야 하며 0장 내용을 그대로 사용하면 안 된다. 모든 가져오기 묶음이 끝난 뒤 한 번만 초기화하고 기존 state를 초기화하지 않는다. 현재 핵심 인물 스냅샷·현재 복선 행·시간선 사건·JSON의 context 입력 6개를 전달하면 스크립트가 7칸의 `추적/문맥.md`를 만든다. 단계·권 단위 회고는 필요에 따라 본문을 조회하며 매 장의 강한 일관성 추적 산출물로 취급하지 않는다.
