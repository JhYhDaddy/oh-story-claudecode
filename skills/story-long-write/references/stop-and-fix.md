# 본문 작성 전 누락 발견: 멈추고 수정

본문 작성 전에 파일 누락이나 추적 불일치를 발견하면 읽는다. 이번에는 본문을 쓰지 않고 수정 후 workflow-chapter의 단계 1부터 다시 시작한다. 작가에게는 workflow-chapter의 ‘더 쓰지 못해 멈춰야 할 때’(원문 표식: `写不下去、要停下时`) 질문 방식을 쓴다.

- **추적 검사 실패**: `tracking_commit.py check` 안내에 따라 수정한다.
- **본문은 있으나 `_tracking-state.json`이 없음**: 집필을 멈추고 작가에게 `/story-import`의 ‘기존 추적 프로젝트 마이그레이션’ 절차를 안내한다. 새 작품에 아직 본문이 없다면 누락이 아니며 workflow-chapter 도입에 따라 초기화한다.
- **파생 뷰와 state 불일치**: [tracking-transaction.md](tracking-transaction.md)에 따라 현재 복구할 이미 커밋된 장에 `mode=revision` 트랜잭션을 커밋하여 파생 뷰를 다시 만든다. 수동 수정하거나 다음 장으로 넘어가지 않는다.
- **비교 작품은 등록했으나 감정 모듈/리듬/문체가 없음**: 작가에게 `/story-long-analyze`로 빠진 분석을 보충하도록 안내한다. 조립 보고서에 `custom_style=true`가 있으면 문체 누락이 아니다. 작가가 비교 작품을 쓰지 않기로 했거나 회수 범위 축소가 성립한 경우도 누락이 아니다.
- **파일 종류별 저장 위치를 찾음**: [project-files.md](project-files.md)를 읽고 따른다.
