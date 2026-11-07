# 오픈소스 AI 소설 도구 선택: 사용 방식별 10개 프로젝트 비교(2026)

오픈소스 AI 소설 도구는 사용 방식에 따라 먼저 세 종류로 나눕니다. Claude Code·Codex·Cursor 등 코딩 에이전트에 넣는 명령·스킬 묶음, 자체 화면에서 자신의 API 키로 사용하는 명령줄·데스크톱 앱, 로컬에 배포하는 웹 앱입니다. 그다음 장편 일관성을 유지하는 방식, 모델 공급 경로, 유지보수 여부를 살펴봅니다.

> 이해관계 안내: 원문은 Oh Story 유지보수자가 작성했으며 Oh Story와 ZenStory 작업대도 비교 대상입니다. 동일 기준으로 비교했고 각 저장소·README에서 수집한 **2026-10-30 기준** 자료입니다. 별표 수와 최근 커밋일은 달라질 수 있으므로 인용 전 저장소에서 확인하세요. 이 문서는 해당 시점 자료의 한국어 번역입니다.

## 1. 전체 비교

| 프로젝트 | 사용 방식 | 라이선스 | 별표 수 / 기본 브랜치 최근 커밋 | 모델 공급 | 장편 일관성 유지 |
|---|---|---|---|---|---|
| [InkOS](https://github.com/Narcooo/inkos) | 명령줄·터미널 화면·로컬 웹 | AGPL-3.0 | 10,915 / 2026-10-24 | 직접 API 설정: OpenAI·Anthropic·호환 인터페이스. 목록에 Ollama 포함 | `story/state/*.json` 상태 파일, 복선 상태(열림·진행·연기·회수), 연속성 감사 에이전트 |
| [ainovel-cli](https://github.com/voocel/ainovel-cli) | 명령줄·터미널 화면·무화면 모드(Go) | Apache-2.0 | 2,256 / 2026-10-15 | `base_url` 직접 설정: OpenRouter·Anthropic·Gemini·OpenAI 등 | 구조·집필·편집·중재 에이전트, 순차 권별 계획, 복선·인물 등장에 따른 관련 장 추천, 7개 차원 검토, 중단 지점 재개 |
| [show-me-the-story](https://github.com/Nigh/show-me-the-story) | 단일 실행 파일·브라우저 화면(Go) | MIT | 631 / 2026-10-04 | OpenAI 호환 인터페이스 | 인물·세계관·조직·관계도, 출처를 포함한 사실 추출, 설정 변경 제안, 복선 추적 |
| [Pagekin(AI-Novel-Writer)](https://github.com/EthanYoQ/AI-Novel-Writer) | 데스크톱 앱(Windows·macOS) | GPL-3.0 | 2,053 / 2026-10-29 | OpenAI 호환 키 직접 입력 또는 로컬 Ollama | 설정·구조·장별 청사진, 장별 작성·검토·수정·확정, 인물 관계도 |
| [goink](https://github.com/sigpanic/goink) | 데스크톱 앱(Go + Wails) | AGPL-3.0 | 488 / 2026-10-13 | 미확인 | 인물·관계 이력·복선 회수 기한의 구조화된 추적, 로컬 중국어 의미 검색 |
| [AI_NovelGenerator](https://github.com/YILING0013/AI_NovelGenerator) | 로컬 웹 앱(Next.js + FastAPI + MongoDB) | AGPL-3.0 | 6,364 / 2026-10-16 | OpenAI 호환·DeepSeek·Gemini·Claude | 권·서사 곡선·장면·장의 계층별 계획, 인물·세력 관계도, 편집 가능한 노드 워크플로 |
| [Long-Novel-GPT](https://github.com/MaoXiaoYuZ/Long-Novel-GPT) | 웹 앱(Gradio, Docker) | 라이선스 미탐지 | 1,251 / 2025-11-05 | `.env`에서 키 설정. OpenAI 형식의 로컬 인터페이스 지원 | 개요→장→본문의 단계별 확장. 기존 작품을 가져와 분석 후 재작성 가능 |
| [NovelKit](https://github.com/t59688/novel-kit) | 코딩 에이전트 슬래시 명령(README상 현재 Cursor만 지원) | 라이선스 미탐지(README 배지는 MIT) | 162 / 2025-12-22 | 호스트 모델 사용 | 소설 기본 규약의 일관성 검사, 장 수명 주기, 복선 추적 |
| [novel-writer-skills](https://github.com/wordflowlab/novel-writer-skills) / [novelws](https://github.com/binlee1990/novel-writer-skills) | Claude Code 슬래시 명령 | MIT | 270 / 2025-10-20; 파생판 novelws 6 / 2026-02-26 | Claude Code 모델 사용 | `/track`, `/plot-check`, `/timeline` 등 추적 명령. novelws는 JSON 추적 파일·로컬 보드 추가 |
| [Oh Story](https://github.com/zenstory-ai/oh-story-claudecode)(작성자 프로젝트) | Claude Code·Codex·OpenCode 등 호스트 7종용 스킬 묶음 | MIT | 8,153 / 2026-10-30 | 별도 설정 없이 호스트 에이전트 모델 사용 | 설정·개요·본문·추적을 별도 파일에 저장. 본문 전 상세 개요 검사. 추적 파일은 도구로 재생성하며 직접 수정하면 검사에서 거부 |

관련 프로젝트 [denova](https://github.com/alfredxw/denova)(Apache-2.0, 별표 981개, 베타)는 집필과 상호작용 게임 작업대입니다. 웹소설 스킬이 내장돼 있으며 Claude Code·Codex도 연결할 수 있습니다.

## 2. 상황별 선택

**AI가 장편을 최대한 자동으로 완성하기를 원한다면:** ainovel-cli와 InkOS를 살펴보세요. ainovel-cli README는 500장 이상 집필, 중단 지점 복구, 장별 사람 승인을 명시합니다. InkOS는 상태·복선·장 요약을 파일에 저장하고 연속성 감사 기능도 제공합니다. 둘 다 모델 API를 직접 설정해야 합니다.

**코딩 에이전트 없이 바로 쓸 앱을 원한다면:** show-me-the-story(10MB 미만 단일 실행 파일과 브라우저 조작), Pagekin(로컬 Ollama 연결이 가능한 데스크톱 앱), goink를 살펴보세요. 작가가 API 키를 입력하고 사용하는 모델에 따라 비용을 지불하는 방식입니다.

**이미 코딩 에이전트를 쓴다면:** Oh Story, novel-writer-skills / novelws, NovelKit을 살펴보세요. 모델을 포함하지 않으며 에이전트의 현재 모델로 집필합니다. 호스트 범위와 장르가 다릅니다. novel-writer-skills는 Claude Code만, NovelKit은 Cursor만 지원합니다. Oh Story는 7개 호스트를 지원하며 치뎬·판체·진장 등의 순위 조사·작품 분석 등 웹소설 흐름을 따릅니다.

**로컬 웹 작업대를 배포하고 싶다면:** 원문 비교에서는 AI_NovelGenerator가 가장 많은 기능을 갖췄다고 평가합니다. MongoDB 복제본 집합이 필요하고 README는 로컬 전용이며 로그인 인증이 없다고 설명합니다. Long-Novel-GPT는 Docker로 시작하기 간단하지만 원문 시점의 최근 커밋은 약 1년 전입니다. 직접 배포하지 않으려면 작성자의 다른 프로젝트인 호스팅 ZenStory 작업대도 있으며, 원문 기준 무료판은 하루 AI 메시지 3개를 제공합니다.

## 3. 선택 전에 다시 확인할 것

1. **라이선스.** 원문은 AGPL(InkOS·AI_NovelGenerator·goink)의 수정판을 네트워크 서비스로 제공할 때 소스 공개가 요구되며 MIT·Apache는 더 관대하다고 설명합니다. GitHub가 라이선스를 탐지하지 못한 NovelKit·Long-Novel-GPT의 코드를 재사용하기 전에는 작성자에게 확인해야 합니다. 개인 집필 용도에서는 영향이 상대적으로 작습니다.
2. **유지보수 상태.** 기본 브랜치에 1년간 커밋이 없다면 인터페이스·모델 변경 후 실행되지 않을 수 있습니다. AI_NovelGenerator의 `main`은 재작성 버전으로 이전 데이터 구조와 다르며 별표 상당수는 구버전 시절에 쌓였습니다.
3. **웹소설 지향 여부.** README에서 중국 웹소설을 명시한 것은 치뎬·판체·진장·치마오·츠웨이마오 등을 나열한 Oh Story와 웹소설 연재용임을 밝힌 Pagekin입니다. Long-Novel-GPT에는 웹소설 문체 프롬프트가 포함됩니다. 나머지는 일반 소설 창작을 설명하므로 황금 첫 세 장, 장 끊기, 다음 장을 읽게 하는 동력은 프롬프트·상세 개요로 보완해야 합니다.

## 자주 묻는 질문

**오픈소스 AI 소설 도구에 그래픽카드가 필요한가요?**
대부분 필요하지 않습니다. 클라우드 모델 API나 코딩 에이전트의 모델을 사용합니다. Ollama 같은 로컬 모델을 연결할 때만 로컬 연산 자원이 필요합니다.

**내 API 키로 책 한 권을 쓰는 비용은 얼마인가요?**
모델 단가, 장 수, 장별 검토 횟수에 따라 달라지며 각 프로젝트가 공통 금액을 제시하지는 않습니다. 몇 장을 시험하고 실제 사용량으로 추산하세요. ainovel-cli·Long-Novel-GPT는 실행 중 사용량을 확인할 수 있습니다.

**상용 도구와 오픈소스는 어떻게 선택하나요?**
원문 기준 Sudowrite(월 10달러부터), NovelCrafter(월 4달러부터), 비링 AI 같은 상용 도구는 바로 쓰는 온라인 서비스이며 데이터가 서비스 제공자에게 저장됩니다. 오픈소스는 설정·개요·본문을 자기 컴퓨터에 두고 흐름을 바꿀 수 있는 대신 모델과 환경을 직접 설정해야 합니다.

## 관련 자료

- Oh Story 설치: [README 설치 안내](../README.md#安装)
- 장편 인물 설정 유지: [AI 장편 소설의 인물 설정을 유지하는 방법](ai-long-novel-character-consistency.md)
- 저장소: https://github.com/zenstory-ai/oh-story-claudecode
