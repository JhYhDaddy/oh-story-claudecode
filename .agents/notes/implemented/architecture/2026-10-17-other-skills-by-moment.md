# Agent Note: 가져오기·검토·문체 정리·배포·라우팅을 작가 시점별로 재구성하고 스크립트와 정렬

Status: implemented
Date: 2026-10-17
Related: [집필 references 재구성](2026-10-17-write-references-by-moment.md), [가져오기 시점별 파일](2026-09-26-import-by-moment.md), [문체 정리 세 계층](2026-10-15-deslop-three-layer.md), [가져오기 계약](../bug-fix/2026-10-14-import-doc-contract-gaps.md), [검토 교정](../bug-fix/2026-10-14-polish-story-review-docs.md), [문체 정리 계약](../bug-fix/2026-10-14-deslop-doc-contract-gaps.md), [배포 문구·문맥](../simplification/2026-10-14-setup-prose-and-deployment-context.md), [라우팅 교정](../simplification/2026-10-14-polish-story-router.md), [표지 교정](../bug-fix/2026-10-14-polish-story-cover-docs.md), [browser-cdp 교정](../bug-fix/2026-10-14-polish-browser-cdp-docs.md), [인계 계약 테스트](../testing/2026-10-17-handoff-contract-fixtures.md)

## Problem

집필·분석·조사 재구성 후 나머지 스킬의 다섯 감사에서도 같은 문제가 나왔다. 핵심은 스킬 간 인계를 검사하지 않아 생산 템플릿이 소비자의 검사보다 뒤처졌다는 것이다.

- 가져온 권 줄거리의 표는 `outline_view.py --unit`이 못 읽어 축약 회상이 작동하지 않는다. 단편 `设定.md`는 옛 형식이라 구상 검사 다섯 항목이 실패한다. 다음 행동으로 일일 연재를 안내하지만 N+1장 줄거리를 생성하지 않아 첫 장부터 멈춘다. 자체 분석 폴더를 `build_writer_prompt.py`가 비교 작품으로 읽는다. 200장 초과 간소 요약은 생성 단계가 없다.
- 검토 prompt는 story-review 사본을 읽게 하지만 agent는 스킬 간 읽기 금지다. consistency-checker에 개정 번호가 없고 집필 플랫폼 값(옌옌·판체 단편·미니앱·진장)을 검토 표에 대응시키지 못한다. 본문 수정 후 추적을 고치면 `tracking_commit`이 거부하지만 출구가 없다.
- 탐지기 22유형 중 blocking 7유형이 문체 방법 색인에 없다. SKILL·expression의 blocking 설명이 다르고 `去味:跳过` 표시도 없다. Gate A–G는 집필자·호출자·조립기에 각기 다른 목록이다. 과업 태그도 집필자가 인식하지 못하며 여러 장 처리·되돌리기 절차가 없다.
- 배포 관리 블록 병합 분기에 도달하지 못하고 호스트 전용 절은 관리 목록에 없다. 자리표시자 치환이 경로 와일드카드를 바꿀 수 있다. 버전 검사가 세 번, UPGRADING은 v23–v32 계약이 쌓였고 hook 설명은 실제와 다르다. Claude 규칙은 장편 템플릿 복사본이 어긋났다.
- 라우팅은 원문 `Notice:`를 작가에게 읽어 주고 explorer·researcher 필수 필드가 없다. 책 판정은 네 기준, 표지는 저장한 제목·장르를 안 읽고 browser-cdp는 바로 `--yes` Chrome 종료 명령을 준다.
- 아무도 안 읽는 사본: 검토 plot-core-methods·dialogue-mastery·character-relations·review-quality, 가져오기 state-tracking·tracking-transaction, 장편 집필 문체 정리 네 파일이다.

## Decision

**가져오기(story-import)**

- 장편 권 줄거리를 범위 행·`### 剧情单元 L1-01`·`- 单元ID：`·장 범위·단위 박자·감정 엔진이 있는 카드로 바꾸고 `outline_view.py --check --strict`를 실행한다. 장편과 바이트 동일한 `scripts/outline_view.py`를 포함해 shared-assets의 `outline-volume-view`에 등록한다. `build_outline_brief.py`는 카드를 읽고 간소 요약 대체 경로를 없애며 배치 첫 장에 이전 장 끝 훅을 더한다.
- 200장 초과 구분을 없애고 전체를 배치형 chapter-extractor 분석에 통과시킨다. 세부 줄거리는 필요에 따라 전체 역산한다.
- 장·단편 책 폴더는 분석 폴더와 같은 `{导入书名}/`다. 장편 다음 행동은 가져온 다음 장 N에 대해 해당 세부 줄거리를 먼저 만드는 장 N 집필, 단편은 구상 완성이다. 단편 `设定.md`는 집필 구상 템플릿을 쓰되 장르 참조·핵심 기법은 이어쓰기 구상에 맡긴다. 본문은 외형만 정리하고 문단·따옴표는 유지한다.
- 인물 카드는 주인공·조연 카드와 맞추고 관계는 분석의 방향 있는 10열 표를 변환해 겉모습과 실제 절을 더한다. 작가 동의로 자체 문체를 `设定/文风.md`에 저장한다. 비교 작품 등록·자료 동기화 표·충돌 규칙은 `benchmark-sync.md`로 나누어 외부 비교 작품을 가져오기 기록에 연결한 때만 읽는다.
- state-tracking·tracking-transaction 사본을 삭제하고 format-and-structure 원본은 story-setup의 `agent-references/format-and-structure.md`로 옮긴다. 내용은 유지하고 공유 그룹은 없앤다.
- `build_writer_prompt.py`는 분석 라이브러리에서 책 폴더와 같은 이름을 비교 작품에서 제외한다. `check-outline-contract.js` 템플릿 출처는 자체 파일만 쓴다(장편 workflow-outline.md, import outline-reverse-rules.md). 장편의 재 `/story-import` 동기화는 최초 참조 시 동기화로 바꾸고 가져온 프로젝트에 장르 본문 카드가 있을 수 있다는 말은 지운다. README·README_EN·docs/hosts·docs/hosts_EN·docs/ai-long-novel-character-consistency·import 진입부와 특수 상황의 다음 행동을 `写第N章`으로 통일한다.

**검토(story-review)**

- plot-core-methods·dialogue-mastery·character-relations·review-quality와 `character-relations-consumers` 그룹을 삭제한다. 에이전트는 자신의 읽기 표로 보충 자료를 읽는다.
- 공통 rubric은 항상, 플랫폼 표는 추가로 읽는다. SKILL 매핑은 장편 치뎬→qidian, 판체→fanqie, 진장·기타·미정은 추가 없음이다. 단편 전 플랫폼은 제목을 단편 Quality Rubric으로 바꾼 zhihu.md다. 플랫폼은 `设定/题材定位.md` 또는 `设定.md`에서만 읽으며 분석 보고의 목표 플랫폼은 비교 작품 것이므로 쓰지 않는다.
- consistency-checker prompt에 `last_committed_chapter`·`state_revision`을 넣고 배정 전 `tracking_commit.py check`를 한다. tracking-transaction은 제출 오류 때만 읽는다. 본문 변경 거부는 재시도하지 않고 `/story-long-write`로 안내한다. solo는 추적을 고치지 않고 사실 오류·누락을 쉬운 말로 안내한다. hook 문구는 유지한다.
- 5자 이하 규칙을 없애고 문장 길이는 문체에 맡긴다. 출판 기준 표에 보고 전체 판단 열을 더하고 심각도는 쉬운 말로 통일한다. rubric 중복·일일 연재 지원을 없애고 수치는 참고로 바꾼다.

**문체 정리(story-deslop)**

- expression 마지막 절만 22유형 색인이며 굵은 것은 blocking이다. 해당 파일 절만 가리키고 판정은 유지한다. 장편 banned-words 중복 색인은 지워 사용 경계로 바꾼다.
- deslop-gates의 A–G를 없애고 탐지 유형·문제명으로 범위를 정한다. 장·단편 agent-calls, workflow-chapter, style-resolution, `build_writer_prompt.py`, 집필자 템플릿은 탐지 유형·호출자 제한 범위로 통일한다. 단편 태그는 집필자가 아는 검토+AI 문체 제거로, 형식 검사는 분담에 쓴다. 집필자의 포괄성 자가 검사는 장편 집필에만 적용한다.
- SKILL은 단순 AI 문체 제거 요청을 원고 수정으로 처리한다. 장편 사건 변경은 `/story-long-write`의 장 X 수정으로, `/story-review` 결론은 제거 범위로 삼을 수 있다. 여러 장은 하나씩 완료한다. 요청 시 `去味:跳过` 장도 처리하고 해결 후 표시를 지운다. 변경 전 `.story/work/去味原稿/`에 백업하고 복원법을 보고한다. 검색·구두점 쓰기를 나누어 대시를 의미에 맞게 고친 뒤 blocking 없는 재검색 후 구두점 스크립트를 실행한다. 전체 파일 완전 정리는 기본적으로 구두점도 정리한다.
- 장편 집필의 expression·narrative-focus·story-logic·deslop-gates 네 사본을 삭제한다. 직접 집필은 탐지 안내로 고치고 세칙을 읽지 않으며 완전 정리는 `/story-deslop`이다.

**배포(story-setup)**

- 호스트별 프로젝트 관리 블록은 `<!-- oh-story:{宿主} 开始 … -->`부터 `<!-- oh-story:{宿主} 结束 -->`까지다. 새 `scripts/merge-project-instructions.py`는 기존 블록 전체 교체, 무표시 옛 배포의 일회 이전을 한다. 스킬 경로 표·파일 구조·집필 제약은 oh-story 흔적이 있어야 옛 배포로 본다. 재배포는 바이트 동일하다. 자리표시자는 `{项目名}`만, 버전 검사는 Phase 1 한 곳만 남긴다.
- UPGRADING은 작가용 내용만 남기고 hook 설명을 고친다. 업그레이드 절차·도우미 36 재실행 필수·v0.8.5에서 업그레이드 절을 더한다. 옛 import의 표형 권 단위는 본문 집필에서 못 읽지만 새 장 이어쓰기는 영향 없다고 설명한다.
- 집필·설계·인물·일관성·자료 조회·연구 템플릿의 상위 판단 요청은 전달 결과의 주 세션 판정 대기로 바꾼다. 인물 설계 인라인 요약은 과업→파일/절 표, 일관성·조회는 단편 분기를 더한다. 연구는 node로 브라우저 포트를 검사하고 닫혔으면 주 세션에 돌린다. Claude 규칙은 변하지 않는 항목만 남기고 OpenCode·Codex를 재생성, Antigravity는 생성기만 고친다.

**라우팅·표지·browser-cdp**

- 버전·대체 실행은 쉬운 문장으로, 원문은 기술 비고에만 쓴다. 라우팅·import도 `AUTHOR_NOTE_PREFLIGHT_SKILLS`에 넣고 검색 의도→`query_type`, explorer·researcher prompt 필드를 명시한다. 책은 hook 기준과 `设定/题材定位.md`, 또는 `设定.md`·`小节大纲.md`가 함께 있는 폴더로 인정하고 `拆文库/`·`对标/`는 제외한다. 설치 채널별 갱신법을 나누고 배포·갱신 후 새 대화를 안내한다.
- 표지는 `.active-book`·설정을 먼저 읽고 얻은 정보는 묻지 않으며 그 뒤 단어로 장르를 추론한다. 2–3안을 한 문장씩 설명해 고른 하나만 생성한다. 책 폴더가 있으면 `{书目录}/封面/`가 기본이다. API 대체는 시점별 `references/api-fallback.md`로 옮긴다.
- Chrome 종료는 `--dry-run` 먼저, 작가 동의 후 `--yes`로 통일하고 Windows 정리는 CIM을 우선한다.

**검사·예산**

- `test-handoff-contracts.py`는 import 권 카드의 집필 구간 추출, 세부 줄거리 검사 출처 실존, 집필→검토 플랫폼, 검토→consistency-checker 필드, 제거 색인·과업 태그, 단편 import 구상 검사, 라우팅 도우미 필드를 검사한다. [인계 테스트](../testing/2026-10-17-handoff-contract-fixtures.md) 참조. `test-writer-pipeline.py`에는 권 템플릿·자체 분석 폴더 제외 회귀를 더한다.
- doc-budget은 가져오기 장편 이전 14950·단편 10200, 외부 비교 작품 연결 16700, 추적 초기화 tracking-initialization 12050, 출처·범위 7550 / 8700, expression 3800, 검토 제출 오류 규약 분기 28800이다. 배포는 8호스트 중첩 최악 44406을 `path_ceiling.exempt`에 넣는다.

## Alternatives considered

- **200장 초과 간소 요약 생성 단계 추가**: 빠르지만 이미 배치 처리하고 별도 형식은 하위 호환 부담이며 지금까지 생성 단계도 없었다.
- **표형 권 줄거리 파서 추가**: 옛 프로젝트 이전을 피하지만 유일한 집필 파서·엄격 검사까지 두 형식을 받아야 하며 단위 필드가 갈라진다.
- **검토 사본 유지 후 에이전트 읽기**: 집필과 자료가 같지만 스킬 간 읽기 금지이고 자체 표에 이미 같은 파일이 있어 사본은 원본과 어긋날 뿐이다.
- **Gate A–G와 변환 표 유지**: 옛 G 검사 요청은 지원되지만 글자가 의미 없고 이미 세 목록이 불일치한다. 유형·문제명을 직접 쓰면 표가 필요 없다.
- **한 번에 최대 4호스트**: 35K를 지키지만 sentinel의 기존 `target_cli`를 여러 업그레이드 대화로 나눠야 한다. 배포는 본문 집필이 아니고 파일은 기계적 목록이다.

## Consequences

- 이점: import 결과가 집필 추출·구상 검사를 통과하고 첫 집필이 멈추지 않는다. 검토는 자체 플랫폼, 제거는 호출자·집필자·조립기의 같은 범위다. 배포 병합이 작가 문단을 덮지 않고 기술 안내를 직접 읽어 주지 않는다. 인계 이름 변경은 CI가 잡는다.
- 비용: 옛 표형 권 단위는 `outline_view --unit`이 못 읽어 옛 장 수정 전에 카드를 보완해야 한다. 8호스트 배포는 35K 초과다. 새 import 질문(문체·겉/실제 관계), 제거 백업·복원·여러 장, 검토 새 출구, 책 폴더 판정은 검사·픽스처만 통과했고 실제 대화는 미검증이다.
- **본문·검토 A/B 후 퇴보 없을 때 적용할 항목**:
  - 집필자가 short-format 원본의 단편 형식을 읽게 하기(헤이옌 한 문장 한 문단·절 끝 훅과 format-and-structure 충돌), format-and-structure 앞의 장편 설명 삭제.
  - 집필자 같은 유형 점감 규칙.
  - solo에 장·단편별 long-quality / short-quality 추가와 원본을 검토로 이전. review-quality는 장편 도입 세 장·쾌감 간격·연속 무갈등 리듬·다섯 차원 점수·단편 전문 항목까지 삭제했으므로 이 작업 전에는 분량별 목록 없이 공통 rubric·플랫폼 표만 쓴다.
  - expression 색인·유형명은 판정을 바꾸지 않았어도 출시 전 집필자 제거 A/B.
  - SKILL의 기본 수정 처리·장편 사건 변경의 `/story-long-write` 라우팅·사전 백업·장별 처리·`去味:跳过`·blocking만 차단·전체 정리의 기본 구두점 처리도 검사만 통과했으므로 위 A/B 또는 실제 대화에서 검증.
- **이번에 하지 않거나 미정인 항목**:
  - 유지보수자가 하지 않기로 한 작가 취향의 문체/허용 목록 동기화, 검토 보고 파일 저장.
  - 업그레이드 필수 항목을 설치 보고에 적기 전 옛 프로젝트 실제 업그레이드.
  - 검토에 tracking-transaction 개정 절만 동기화하고 tracking-initialization 삭제하기 전 장편 원본 수정.
  - ZCode 호스트 강제 명령, 쓰지 않는 Phase 1 탐지, 일관성 검사 없는 7호스트 수기 경로 표.
  - 시대·농경·무한류·e스포츠 표지와 치뎬·진장·치마오 업로드 크기 사전 확인.
  - 단편 절별 분량 스크립트, 라우팅/hook 책 판정 일치 검사, style-resolution의 `_文风摘要.md`·단편 문체 규약 두 포인터.
