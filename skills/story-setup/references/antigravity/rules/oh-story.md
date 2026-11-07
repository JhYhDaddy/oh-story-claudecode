---
trigger: always_on
---

# oh-story 집필 프로젝트 규칙

이 작업 공간은 `.agents/skills/`의 oh-story 웹소설 스킬을 사용한다. 선택한 스킬의 `SKILL.md`를 먼저 읽고 지시에 따라 참조를 읽는다.

## 라우팅

- 장편 집필·이어쓰기: `story-long-write`
- 단편 집필: `story-short-write`
- 장편/단편 분석: `story-long-analyze` / `story-short-analyze`
- 장편/단편 시장 조사: `story-long-scan` / `story-short-scan`
- AI 집필 패턴 제거: `story-deslop`
- 대립 관점 검토: `story-review`
- 기존 작품 가져오기: `story-import`
- 표지 생성: `story-cover`
- 출판 준비(제목·소개·플랫폼 태그): `story-publish`
- 불분명한 집필 의도: `story`
- 프로젝트 배포/갱신: `story-setup`
- 인증된 Chrome 세션 재사용: `browser-cdp`

## 집필 보호 규칙

- 모든 작품 산출물·임시 집필 조각·추적 트랜잭션·생성 프로젝트 디렉터리는 현재 작업 공간 안에 둔다. 사용자가 외부 목적지를 명시하지 않았다면 `~/.gemini/`, Antigravity의 `scratch/` 또는 다른 작업 공간 외부 디렉터리에 oh-story 작품을 만들거나 이어 쓰지 않는다.
- 본문을 쓰기 전에 장편은 해당 `개요/상세개요_제N장*.md`, 단편은 `구간개요.md`가 있어야 한다.
- `추적/_tracking-state.json`을 구조화된 유일 기준으로 취급한다. 파생 Markdown 뷰를 수동 수정하지 않는다.
- 본문을 쓴 뒤 oh-story Antigravity 훅이 주입한 결정적 검사 결과를 모두 해결한 다음 다른 장으로 진행한다.
- 전문 작업에는 `.agents/agents/`에 배포된 일곱 custom agents를 우선한다. 에이전트의 `TypeName`으로 `invoke_subagent`를 호출한다. 실행 환경에서 시작하지 못하면 절차를 실패시키지 말고 스킬에 적힌 solo/direct fallback을 사용한다.

## 작가와 협업

- 답변 본문에는 작품·장·개요·설정 같은 쉬운 집필 용어를 쓴다. 오류 보고 시에는 스크립트명·필드명·상태명을 인용한다.
- `<!-- author-report -->`가 있는 스킬 템플릿은 형식 참고일 뿐이다. 코드 울타리 없이 그 안의 글로 답한다.
- 작가가 집필 습관/취향을 기억·삭제·확인해 달라고 하면 명시한 유형이나 현재 작품에 따라 `story-long-write` 또는 `story-short-write`의 작가 기억 관리를 쓴다. 현재 작품이 없는 일반 습관은 장편 진입점을 사용한다. 작품 한정 취향인데 대상을 식별할 수 없을 때만 어떤 작품인지 묻고 작품을 만들지 않는다. 해당 작업 공간 또는 작품 디렉터리의 `.story/작가기억/`에 쓰며 Antigravity 내장 기억에는 절대로 저장하지 않는다. 일회성 요청은 수행만 하고 기록하지 않는다.
- 이 작업 공간에 설치된 스킬 파일(`SKILL.md`·`references/`·`scripts/`)을 수정하지 않는다. `story-setup` 재배포는 예외다. 스킬 스크립트가 실패하면 멈추고 오류와 실행 명령을 보고하며 임의로 고쳐 우회하지 않는다.

## 맥락 복구

새 대화를 시작하거나 맥락이 압축되었거나 작품 상태가 불확실할 때 현재 작품을 찾고 `추적/문맥.md`를 읽은 뒤 계속한다. Antigravity 외부 훅 API에는 PreCompact/PostCompact 이벤트가 없으므로 이 규칙이 압축 후 필수 복구 경로다.
