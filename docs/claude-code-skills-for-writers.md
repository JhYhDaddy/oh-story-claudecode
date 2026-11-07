# 코딩 이외의 Claude Code 스킬: 소설 집필 스킬 묶음으로 살펴보기

에이전트 스킬은 코딩 외의 작업도 조직할 수 있습니다. Oh Story(`zenstory-ai/oh-story-claudecode`)는 MIT 라이선스의 스킬 14개로 Claude Code, Codex CLI, OpenCode, Google Antigravity, OpenClaw, ZCode, Reasonix에서 연재 소설 집필의 전체 흐름을 지원합니다. 인기 순위 조사, 상위 작품 분석, 파일 기반 연속성 추적으로 장 집필, AI 문체 제거, 플랫폼 작품 등록 정보 준비, 표지 제작을 수행합니다. 사용자가 코드를 쓸 필요는 없습니다. 에이전트가 작품 프로젝트의 Markdown 파일을 읽고 씁니다.

## 스킬이란

스킬은 `SKILL.md`와 선택적인 `references/`, `scripts/`가 들어 있는 폴더입니다. `SKILL.md`는 언제 적용하고 무엇을 할지 설명합니다. 작업에 맞을 때만 읽으므로 수십 개의 스킬을 두어도 맥락 창을 모두 채우지 않습니다. 디스크에 저장해 세션 간 재사용한다는 점에서 단일 프롬프트와 다릅니다. 플러그인은 스킬·에이전트·훅을 묶을 수 있는 배포 형식이고, MCP 서버는 프로토콜로 도구를 노출합니다. 스킬은 에이전트가 직접 읽는 지침과 파일입니다. 정식 정의는 Anthropic 문서를 참조하세요. 이 글에서는 작가용으로 만든 실제 형태를 설명합니다.

## 비코딩 스킬 묶음의 구성

Oh Story의 14개 스킬을 집필 작업별로 나누면 다음과 같습니다.

| 작업 | 스킬 | 기능 |
|---|---|---|
| 초기 설정 | `story-setup` | 호스트별 파일 배포. 전문 에이전트와 훅 지원은 호스트에 따라 다름 |
| 요청 전달 | `story` | 자연어 요청·선호 관리를 해당 집필 스킬로 전달하고 로컬 대시보드 실행 |
| 조사 | `story-long-scan`, `story-short-scan` | 치뎬·판체·진장과 단편 순위에서 개별 순위보다 반복되는 패턴을 조사 |
| 작품 분석 | `story-long-analyze`, `story-short-analyze` | 장편 Stage 0~6에서 장 색인, 황금 도입부, 묶음 추출, 리듬, 설정, 보고서, 문체를 다룸. 단편 Stage 2~6은 고유 분석 자료를 생성 |
| 집필 | `story-long-write`, `story-short-write` | 개요에서 본문까지 작성. 장편은 파일 우선 추적(`_tracking-state.json`, 장별 변화분 최대 3072바이트), 단편은 고유 설정·개요·이야기 파일 사용 |
| 수정 | `story-deslop` | 표현, 서사적 강조, 이야기 인과를 진단한 뒤 작가가 정한 범위와 허용에 따라 수정 |
| 검토 | `story-review` | 검토 에이전트의 병렬 다각도 검토. 사용할 수 없으면 단일 실행으로 전환 |
| 가져오기 | `story-import` | 기존 원고를 역분석해 프로젝트 구조로 정리 |
| 출판 준비 | `story-publish` | 확인된 설정·개요를 제목·소개·태그 등 작품 등록 정보로 변환하고 플랫폼 규칙과 대조. 현재 판체 지원 |
| 표지 | `story-cover` | 제목과 장르로 표지 프롬프트 또는 이미지 생성 |
| 브라우저 | `browser-cdp` | 로그인된 Chrome 세션을 재사용해 순위 데이터 수집 |

단순한 프롬프트 모음 이상의 기능을 만드는 요소는 다음과 같습니다.

- **결정적 검사.** `story-deslop`은 문맥 검토와 함께 `node scripts/check-ai-patterns.js`로 로컬 파일의 패턴을 찾습니다. `story-long-write`는 상세 개요에 목표 글자 수가 없으면 추측하지 않고 집필을 거부합니다.
- **필수 자료 검증 관문.** 에이전트가 상세 개요, 권별 개요, 현재 추적 상태를 읽고 이번 글자 수 범위·필수 사건·금지 사건·시간 기준점을 기록한 뒤에만 장을 작성합니다.
- **파일에 저장한 계층별 상태.** 설정·개요·본문·추적 정보를 별도 디렉터리에 둡니다. 추적 상태 카드는 고정 7개 절, 최대 12 KB이며 과거 기록은 전체를 로드하지 않고 필요할 때 조회합니다.
- **실행 환경별 배포기.** `/story-setup` 한 번으로 사용하는 에이전트에 맞는 파일을 `.claude/`, `.codex/`, `.opencode/`, `.agents/` 등에 씁니다.
- **여러 실행 환경용 패키징.** 저장소는 여러 호스트에 필요한 `marketplace.json`, `.claude-plugin`, `.zcode-plugin`, `reasonix-plugin.json`을 제공합니다.

## 작가의 사용 방법

```bash
npx skills add zenstory-ai/oh-story-claudecode -y -g
```

그다음 작품용 빈 폴더에서 에이전트를 열고 실행합니다.

```text
/story-setup
```

새 세션에서 원하는 작업을 자연어로 요청합니다. “책 구상을 도와줘”는 설정·개요 작업을 시작하고 본문은 요청했을 때 씁니다. “내 책을 가져와줘”는 기존 원고를 가져오고, “이 글은 AI 문체가 너무 강해”는 AI 문체 제거를 실행합니다. “선지는 지금 어떤 상태야”라고 물으면 하위 에이전트가 추적 파일에서 인물의 현재 상태를 보고합니다. 위 두 명령 외에 터미널 명령은 필요하지 않습니다.

원래 중국 웹소설 플랫폼(치뎬, 판체, 진장, 치마오, 즈후 옌옌)을 위해 만든 묶음이며 스킬·참조 자료·파일명이 중국어 기반입니다. 이 현지화본에서는 설명을 한국어로 옮기고 실행 경로는 유지합니다. 동작 원리는 언어에 종속되지 않습니다.

## 코딩 이외의 스킬에 주는 의미

소설도 같은 도구를 다른 종류의 상태에 적용합니다. 상태는 크고 매 장 바뀌며, 작가가 플롯 결정을 통제해야 합니다. 올바른 결과는 테스트 통과만이 아니라 독자의 읽기 경험으로 평가합니다. 파일은 상태를 보존하고, 검증 관문은 필수 입력을 확인하며, 스크립트는 기계적인 검증을 맡습니다. 이런 분담은 조사·편집·문서화·제작 작업에도 적용할 수 있습니다.

## 관련 자료

- 저장소: https://github.com/zenstory-ai/oh-story-claudecode (이전 `worldwonderer/oh-story-claudecode` 주소는 자동 이동)
- 영문 README의 한국어 번역: [README_EN.md](../README_EN.md)
- 처음 쓰는 사용자를 위한 안내: https://zenstory.ai/oh-story/agent-skills-for-writers
- Claude Code·Codex에서 설치부터 첫 장까지: https://zenstory.ai/oh-story/claude-code-novel-writing
- 같은 조직의 관련 묶음: 숏드라마(`drama-skills`), 소설의 게임화(`novel-to-game`), 영상 요약(`video-recap-skills`), DeepSeek Harness 플러그인(`oh-story-dsh`)
- 연속성 기능 상세: [keep-ai-novel-consistent-over-100-chapters.md](keep-ai-novel-consistent-over-100-chapters.md)
