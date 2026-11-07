# AGENTS.md

이 파일은 oh-story-claudecode 저장소 자체의 개발 지침으로, 이 스킬 묶음을 유지보수하는 코딩 에이전트를 위한 문서입니다. 사용자 집필 프로젝트에 배포하는 AGENTS.md와는 다릅니다. 사용자 프로젝트의 AGENTS.md / CLAUDE.md는 story-setup이 `skills/story-setup/references/*/AGENTS.md.tmpl`을 바탕으로 생성하며, 이 파일과는 관계없습니다.

## 저장소 소개

웹소설 집필용 스킬 묶음입니다. 14개 스킬(`skills/<name>/SKILL.md` + `references/`)과 Claude Code, Codex, OpenCode, OpenClaw, Antigravity, ZCode, Reasonix 등 7개 코딩 에이전트(호스트)를 위한 어댑터로 구성됩니다. 제품의 핵심은 Markdown에 작성된 집필 방법과 워크플로 계약이며, 런타임 프로그램이 아닙니다. `scripts/`에는 저장소 자체의 검사, 테스트, 코드 생성 스크립트가 들어 있습니다([scripts/README.md](scripts/README.md) 참조). 스킬 런타임 스크립트와 구분합니다.

## 수정 전 필수 규칙

- **프런트매터는 한 줄 키-값 형식**: `description`에 `|`/`>` 블록을 사용하지 않으며, `metadata`는 한 줄 JSON입니다. OpenClaw가 이 형식에 의존합니다.
- **스킬 간 파일 참조 금지**: 공통 기반 구성 요소인 `browser-cdp`를 제외하면, 스킬의 SKILL.md / references에서 다른 스킬의 파일을 참조하면 안 됩니다. 공유 콘텐츠는 `scripts/shared-references.json` / `scripts/shared-assets.json`에 등록합니다.
- **자주 읽는 문서의 글자 수 예산**: SKILL.md, references, 에이전트 템플릿에는 `scripts/doc-budget.json`의 제한이 적용됩니다. 본문을 추가할 때는 같은 분량의 기존 내용을 줄이거나 예산을 명시적으로 늘리고 이유를 설명합니다. 각 역할의 호출당 로드량은 조건 분기와 동시 로드 조합을 포함해 공백 제외 35K자(`path_ceiling`)가 절대 상한입니다. 예외는 `path_ceiling.exempt`에 사유와 함께 등록해야 합니다. 조건부 읽기는 기본적으로 상호 배타적이며, 함께 읽는 경우는 `stacking`에 등록합니다. 분량을 줄일 때는 드물게 필요한 규칙부터 해당 시점에만 읽는 참조 문서로 옮깁니다.
- **워크플로 번호는 계약**: Step / Phase / Stage 번호와 참조 연결은 `skill-numbering.py`가 검사합니다. 순서를 바꿀 때는 직접 번호를 고치지 말고 스크립트의 연쇄 갱신을 실행합니다.
- **에이전트 템플릿이나 CLAUDE.md.tmpl을 수정하면 어댑터를 다시 생성**: OpenCode, Codex, Antigravity 등의 생성 결과도 함께 커밋해야 합니다. 누락하면 어댑터 CI가 실패합니다.
- **스킬 문서에서 `python3` 직접 호출 금지**: python3 → python → py 순서로 실행 가능한 인터프리터를 탐색합니다.
- **`scripts/` 스크립트의 이름이나 위치 변경**: `.github/workflows/*.yml`, CONTRIBUTING.md, scripts/README.md와 해당 스크립트를 호출하는 다른 스크립트도 함께 갱신합니다.
- 이 파일에는 story-setup이 배포된 프로젝트를 식별하는 표식(각 호스트 AGENTS.md.tmpl의 제목 줄)을 넣으면 안 됩니다. 넣으면 저장소 루트에서 story-setup을 실행할 때 이 저장소를 이미 배포된 프로젝트로 오인합니다.

전체 규칙, 호스트별 어댑터 유지보수 절차와 기여 절차는 [CONTRIBUTING.md](CONTRIBUTING.md)를 참조합니다.

## 검증

필수 검사는 `.github/workflows/cross-platform.yml`을 기준으로 합니다. 커밋 전에 [CONTRIBUTING.md](CONTRIBUTING.md)의 CI 검사 절에 있는 로컬 명령으로 변경 사항과 관련된 검사를 실행합니다. 최소한 `bash scripts/static-check.sh`, `python3 scripts/skill-numbering.py check`, `bash scripts/check-doc-budget.sh`, `bash scripts/check-shared-files.sh`를 실행해야 합니다.

## 주요 변경의 결정 기록

결정 기록은 `.agents/notes/{proposed,implemented,rejected}/{feature,bug-fix,simplification,architecture,process,testing}/yyyy-mm-dd-topic.md`에 저장합니다. DeepSeek Harness의 agent-notes 규약을 따릅니다(방법: https://github.com/czm15053/write-notes-like-deepseek). 한국어 현지화본에서는 본문은 한국어로 작성하고 필수 소제목은 영어로 유지합니다.

1. 단순하지 않은 변경(에이전트가 관찰하는 워크플로 단계, 스킬 간 계약, 주요 산출물이나 저장 형식, 어댑터 구조, 검사 스크립트와 CI, 테스트 전략)을 시작하기 전에 `.agents/notes/`에서 같은 주제의 기존 기록을 검색합니다. 해당 기록이 있으면 사실을 그 자리에서 갱신합니다. 없으면 먼저 `proposed/`에 작성하고, 구현이 완료되면 코드와 같은 커밋에서 `implemented/`로 옮깁니다. 서식, 이름, 버전 번호, 동작을 바꾸지 않는 패치 같은 기계적 변경은 기록 없이 바로 커밋합니다.
2. 모든 기록에는 `## Problem`, `## Decision`(현재 시제로 구현된 사실만 작성) 또는 `## Proposal`, `## Alternatives considered`, `## Consequences`가 필요합니다. 검토 후 제외한 대안은 가장 강한 장점을 먼저 쓰고 제외한 이유를 설명합니다. 검토하지 않은 대안은 지어내지 않습니다. 결과에는 이점과 비용을 모두 적습니다.
3. 기존 기록을 정반대 결정으로 바꿔 쓰지 않습니다. 경로·이름·기본값 같은 사실은 기존 기록에서 수정하되, 결정이 뒤집히면 새 기록을 만들고 서로 연결합니다.
4. `INDEX.md`를 만들지 않습니다. 디렉터리 위치가 상태를 나타내며, 검색에는 `rg --hidden .agents/notes/`를 사용합니다.
