<a id="贡献指南"></a>
# 기여 가이드라인

웹소설 작성 스킬에 대해 관심을 보여주셔서 감사합니다. 기여해 주시기를 환영합니다.

<a id="仓库结构"></a>
## 저장소 구조

```
skills/
├── story/                   # 툴박스 라우팅
├── story-setup/             # 환경 배포
├── story-import/            # 역방향 가져오기
├── story-long-write/        # 장편 글쓰기
├── story-long-analyze/      # 장편 작품 분석
├── story-long-scan/         # 장편 순위 조사
├── story-short-write/       # 단편 글쓰기
├── story-short-analyze/     # 단편 작품 분석
├── story-short-scan/        # 단편 소설 순위 조사
├── story-deslop/            # AI 문체 제거
├── story-review/            # 다양한 관점에서의 검토
├── story-cover/             # 표지 제작
└── browser-cdp/             # 브라우저 조작
scripts/                       # 개발 검사기 / 테스트 / 코드 생성 (전체 목록은 scripts/README.md을 참조하십시오)
```

각 스킬은 `SKILL.md`(입구)과 `references/` 디렉터리(지식베이스)로 구성되어 있습니다.

<a id="反馈与需求"></a>
## 피드백 및 요구사항

- 안정적으로 재현 가능한 명령어, 파일, 상태 또는 런타임 오류가 발생하는 경우에는 **버그 리포트**를 제출해 주십시오.
- 문체, 등장인물, 리듬, 논리적 구조 또는 AI 특유의 스타일이 기대에 부합하지 않는 경우: **출력 품질 관련 사례**를 제출하시고, 최소한 필요한 맥락 정보, 연속적인 출력 내용의 일부, 구체적인 문제점이 발생한 위치, 그리고 원하는 개선 방향을 명시해 주시기 바랍니다.
- 새로운 기능 또는 런타임/IDE와의 호환성 개선을 원하는 경우에는 **기능 요청**을 제출하면서 실제 사용 중에 발생하는 문제점과 수용 가능한 결과를 명시해 주셔야 합니다. 또한 호환성 개선을 요청할 때는 공식 확장 기능 관련 문서나 스킬 관련 자료도 함께 제공해 주시기 바랍니다.
- 사용 방법, 절차 선택 및 일반적인 질의응답: [GitHub Discussions](https://github.com/zenstory-ai/oh-story-claudecode/discussions)를 방문하십시오.

이슈란 조치를 취할 수 있는 작업 관련 정보를 말합니다. 재현 단계, 실제 결과, 문제가 발생한 구체적인 위치 또는 검수 결과가 누락되어 있을 경우, 유지보수 담당자는 해당 정보의 추가 제공을 요청할 것입니다. 장기간에 걸쳐 해당 정보가 제공되지 않을 경우, 그 정보는 개발 일정에 포함되지 않습니다. API 키, 토큰, 개인 정보, 공개될 수 없거나 공개하기를 원하지 않는 문서는 절대 제출하지 마십시오.

<a id="skill-格式"></a>
## 스킬 형식

`SKILL.md`의 시작 부분에는 반드시 frontmatter가 있어야 합니다.

```yaml
---
name: skill-name
description: "한 문장 설명. 호출 방법: /skill-name, 호출어1, 호출어2"
metadata: {"openclaw":{"source":"https://github.com/zenstory-ai/oh-story-claudecode"}}
---
```

OpenClaw과의 호환성을 위해, frontmatter는 반드시 한 줄로 된 키-값 형식으로 작성되어야 합니다. `description`의 경우 `|`/`>` 블록은 사용하지 않아야 하며, `metadata`는 반드시 한 줄로 된 JSON 객체여야 합니다. 보다 긴 설명은 본문에 기재해 주십시오.

`references/` 내의 파일들은 필요에 따라 스킬에 의해 로드되며, 모두 컨텍스트에 포함되지는 않습니다.

<a id="维护者指引与决策笔记"></a>
## 유지보수자를 위한 안내 및 의사결정 관련 메모

- 저장소 루트의 [AGENTS.md](AGENTS.md)는 이 저장소를 유지보수하는 코딩 에이전트용 개발 지침입니다. 변경 전 필수 규칙, 검증 진입점, 기록 규칙을 담습니다. `CLAUDE.md`에는 `@AGENTS.md` 한 줄만 두며 별도 본문을 관리하지 않습니다. story-setup이 사용자 집필 프로젝트에 배포하는 `AGENTS.md` / `CLAUDE.md`와는 관계없습니다.
- 단순하지 않은 변경은 `.agents/notes/{proposed,implemented,rejected}/{feature,bug-fix,simplification,architecture,process,testing}/yyyy-mm-dd-topic.md`에 결정 기록을 남깁니다. Problem / Decision 또는 Proposal / Alternatives considered / Consequences 절을 포함합니다. 전체 규칙은 AGENTS.md의 주요 변경 결정 기록 절을 확인하세요. `scripts/check-agent-notes.py`가 CI에서 서식을 검사합니다. 검색: `rg --hidden <关键词> .agents/notes/`.

<a id="如何贡献"></a>
## 어떻게 기여할 수 있을까요?

<a id="改进现有-skill"></a>
### 기존의 스킬을 개선하기

1. 포크 저장소
2. `main`에서 분기를 생성합니다: `git checkout -b feat/your-feature main`
3. 해당 `SKILL.md` 또는 `references/` 파일을 수정하십시오.
4. PR을 제출할 때는 무엇을 어떻게 변경했는지, 왜 그런 변경을 했는지를 명확히 설명해 주세요.

<a id="新增-skill"></a>
### 새로운 스킬 추가

1. `skills/` 아래에 디렉터리를 생성하고, 그 안에 `SKILL.md`과 `references/`를 포함시킵니다.
2. 저장소 루트 디렉터리에서 `npx skills validate`를 실행할 때 오류가 발생하지 않도록 확인하십시오.
3. PR을 제출합니다.

<a id="ci-检查"></a>
## CI 검사

PR는 자동으로 `.github/workflows/cross-platform.yml`을 실행합니다. static-check 작업은 다음과 같은 검사를 수행합니다(모두 필수):

- `scripts/static-check.sh` — frontmatter의 구조화된 파싱, 정확한 Markdown 경로/앵커 포인트의 처리, 에이전트를 통한 참조 기능 및 참고 자료의 접근성을 보장합니다. 기본 구성 요소인 `browser-cdp`을 제외하고는 다른 스킬 파일 간의 참조가 금지됩니다(작가 보고서 템플릿과 관련된 전문 용어들은 아래의 `check-author-reports.py`에서 별도로 검사기를 통해 관리됩니다).
- `python3 scripts/skill-numbering.py check` — 워크플로우 번호의 연속성, 참조 항목의 바인딩 가능성, 그리고 소수점 표기와 관련된 검사기 규칙
- `python3 scripts/check-agent-notes.py` — `.agents/notes/`의 디렉터리 배치, `Status`와 소속 디렉터리의 일치, 필수 절을 검사합니다. `python3 scripts/test-agent-notes.py`는 동작 회귀 테스트입니다.
- `python3 scripts/check-author-reports.py` — `<!-- author-report -->`로 표시한 작가 보고서 템플릿에 스크립트명, 필드명, 플래그, 심각도 코드 등 엔지니어링 용어가 없는지 검사합니다. `--self-test`는 허용·거부 사례의 회귀 테스트입니다.
- `scripts/check-current-skill-contracts.sh` — `scripts/current-contract.json`에 따라 현재 버전, Phase, 스키마, 주요 산출물, 상세 개요 계약을 확인하고, 과거 경로와 알리지 않는 호환 분기를 차단합니다.
- `python3 scripts/test-current-skill-contracts.py` — 현재 계약 매니페스트와 주요 산출물의 즉시 실패 동작을 검증합니다.
- `python3 scripts/test-handoff-contracts.py` — 스킬 간 전달 계약을 검증합니다. 작품 분석·순위 조사·가져오기 산출물에서 집필로, 집필 플랫폼에서 원고 검토로, 조수·집필자에게 AI 문체 제거를 위임할 때 전달하는 절·필드·열 이름·플랫폼 값·태그를 검사하며 반대 사례 자체 검사도 포함합니다.
- `scripts/check-doc-budget.sh` — `scripts/doc-budget.json`에 따라 자주 읽는 SKILL/references/에이전트 템플릿의 글자 수를 검사해 매 세션 로드하는 규칙이 모르는 사이 늘어나는 것을 방지합니다.
- `scripts/check-hook-regex-sync.sh` — 훅 복선 상태 검출 동작
- `scripts/check-shared-files.sh` — 공유 런타임 자산 목록 + 다양한 스킬 간의 참조 일관성 보장
- `scripts/check-scan-runtime-policy.sh` — 스크레이퍼의 로컬 날짜 설정 및 CDP 소스 코드 관련 검사기 기능
- `python3 scripts/test-scan-runtime-policy.py` — 관련이 없거나 무용한 코드에 대한 키워드 검사는 스캔/브라우저의 보안 전략을 속일 수 없습니다.
- `python3 scripts/test-scan-aggregate.py` — 순위 조사를 위한 집계 스크립트의 파싱, 중복 제거, 분포 분석 및 샘플링 과정에 대한 회귀 테스트
- `scripts/check-story-setup-deployment.sh` — story-setup 배포 완전성
- `python3 scripts/test-plugin-packaging.py` — 공개된 CLI를 통해 catalog/manifest에 대해 블랙박스 변이 회귀 테스트을 수행함
- `scripts/check-claude-adapter.sh` — Claude 마켓플레이스, 기본 플러그인 매니페스트 및 14개의 스킬에 대한 자동 검사 기능; 실제 CLI 라이프사이클 사용도 가능
- `scripts/check-opencode-adapter.sh` — OpenCode 어댑터 동기화, commands/agents 구조와 플러그인의 실제 동작을 검사합니다.
- `scripts/check-openclaw-skills.sh` — OpenClaw 한 줄 프런트매터, `metadata.openclaw`, 선택적 실제 CLI 스킬 탐색을 검사합니다.
- `scripts/check-codex-adapter.sh` — Codex 저장소 스킬 심볼릭 링크, 사용자 정의 에이전트 TOML, 훅 생성의 결정성, 실행기 계약을 검사합니다.
- `scripts/test-codex-hooks.sh` — Codex 훅 합성 이벤트 테스트
- `scripts/check-antigravity-adapter.sh` — Antigravity 프로젝트의 스킬들: 물리적 구현, Markdown 에이전트, 항상 활성화된 규칙, named-group 훅 및 병합/행동 회귀 기능
- `node scripts/test-antigravity-hooks.mjs` — Antigravity 공식 훅 입출력, 산출물 연결, Stop 후 한 번만 이어서 실행하는 동작을 검사합니다.
- `scripts/check-zcode-adapter.sh` — ZCode 플러그인/마켓플레이스, 14개의 스킬/명령어, 지원되는 Hook 이벤트 및 배포 앵커 포인트 검사
- `scripts/test-zcode-hooks.sh` — ZCode: 엄격한 JSON Hook 계약, 본문 검사기, 연속성 및 크로스플랫폼 Node runner 테스트
- `python3 scripts/test-storyctl.py` — `visible_chars_v1` 계수, 이중 구간, 구조화된 CLI, 같은 기준의 demo 증거에 대한 런타임 동작 회귀 테스트입니다.
- 수집 스크립트의 `node --check` 구문 검사

위 목록은 대표적인 예시입니다. **필수 검사 목록은 `.github/workflows/cross-platform.yml`을 기준으로 합니다.** 각 스크립트의 용도와 실행 시점은 [scripts/README.md](scripts/README.md)를 참조하세요. `.github/workflows/cli-compat.yml`은 관련 PR, 주간 일정, 수동 실행 시 공식 최신 버전을 설치하고 Claude Code·Codex·OpenCode·OpenClaw의 인증 없는 실제 CLI 스모크 테스트를 실행합니다.

또한 Windows/MacOS용 작업에서는 `python3 scripts/check-plugin-packaging.py`(Claude/ZCode 카탈로그, 네이티브 매니페스트, 통합 번들 신원 정보, 버전 정보 및 14개의 기본 스킬 검사)의 실행과 크로스플랫폼 테스트가 이루어지며, cdp-utils의 로딩 과정과 setup 스크립트인 dry-run도 검증됩니다.

제출하기 전에 Linux CI의 필수 점검 항목들을 로컬 환경에서 먼저 실행해 보는 것을 권장합니다.

```bash
bash scripts/static-check.sh
python3 scripts/test-static-check.py
python3 scripts/check-agent-notes.py
python3 scripts/check-author-reports.py --self-test
python3 scripts/check-author-reports.py
python3 scripts/skill-numbering.py check
bash scripts/test-skill-numbering.sh
bash scripts/check-current-skill-contracts.sh
python3 scripts/test-current-skill-contracts.py
python3 scripts/test-handoff-contracts.py
bash scripts/check-doc-budget.sh
bash scripts/check-hook-regex-sync.sh
bash scripts/check-shared-files.sh
python3 scripts/test-shared-assets.py
python3 scripts/test-shared-references.py
node scripts/test-normalize-punctuation.js
python3 scripts/test-style-precedence.py
node scripts/test-scan-runtime.js
bash scripts/check-scan-runtime-policy.sh
python3 scripts/test-scan-runtime-policy.py
python3 scripts/test-scan-aggregate.py
bash scripts/test-ai-patterns.sh
node scripts/test-phase2-contract.js
node scripts/test-delivery-contract.js
node scripts/check-reference-gates.js
node scripts/test-outline-contract.js
bash scripts/test-degeneration.sh
bash scripts/test-prose-backstop-hook.sh
bash scripts/test-prose-net-parity.sh
bash scripts/test-story-continuity.sh
python3 scripts/test-storyctl.py
python3 scripts/test-author-memory-commit.py
bash scripts/check-story-setup-deployment.sh
python3 scripts/test-plugin-packaging.py
bash scripts/check-claude-adapter.sh
bash scripts/check-codex-adapter.sh
bash scripts/check-opencode-adapter.sh
bash scripts/check-openclaw-skills.sh
bash scripts/test-codex-hooks.sh
bash scripts/check-python-invocation.sh
bash scripts/check-hook-locale-safety.sh
bash scripts/test-hook-encoding-portable.sh
bash scripts/test-charcount-portable.sh
bash scripts/test-charcount-portable.sh --stub

# 선택 사항: 실제 CLI 스모크 테스트(해당 CLI를 각각 설치해야 함)
CLAUDE_REAL_CHECK=1 bash scripts/check-claude-adapter.sh
bash scripts/test-codex-cli-e2e.sh
bash scripts/test-opencode-cli-e2e.sh
OPENCLAW_REAL_CHECK=1 bash scripts/check-openclaw-skills.sh
```

<a id="工作流编号规范"></a>
## 워크플로우 번호 규격

프로세스 단계를 새로 추가하거나 조정할 때는 `Step 1`, `Step 2`과 같은 연속적인 숫자를 명시적인 제목으로 사용해야 합니다. 단계를 추가하기 위해 `Step 1.5`, `Phase 2.1`, `Stage 0.5`와 같은 번호를 만들지 말아야 하며, `SKILL.md`에서 명확한 워크플로우 제목을 `### 2.1`이나 `- 2.1`으로 대체해서도 안 됩니다. `references/` 매뉴얼 자체의 `3.1` 장/목록 번호는 이 규칙의 적용을 받지 않습니다.

번호를 수정하기 전에 먼저 미리 보고, 그 다음에 저장한 후 다시 한 번 확인하세요.

```bash
python3 scripts/skill-numbering.py audit
python3 scripts/skill-numbering.py fix --dry-run
python3 scripts/skill-numbering.py fix --write
python3 scripts/skill-numbering.py check
```

자동 복구 기능은 명시적으로 지정된 Step 제목과 오해의 소지가 없이 바인딩할 수 있는 참조만을 재정렬합니다. 바인딩할 수 없는 fractional Step 참조나 일대다 매핑의 경우, 파일에 저장되기 전에 전체 작업이 실패하게 됩니다. Phase, 숫자로 표시된 제목, 그리고 bullet 형식의 하위 Step들은 의미에 따라 수동으로 명명해야 합니다. 전체 알고리즘과 부분 경로의 사용 방법은 [scripts/README.md](scripts/README.md#工作流编号维护)을 참조하십시오.

에이전트/스킬/플러그인/훅 프로토콜과 관련된 주장들은 반드시 해당 프로젝트의 공식 문서를 먼저 확인한 후, 실제 CLI 출력 결과를 통해 다시 검증해야 합니다. 다른 에이전트의 유사한 필드를 근거로 추론해서는 안 됩니다.

<a id="共享文件规范"></a>
## 공유 파일 규격

일부 파일은 여러 스킬 간에 공유되므로(banned-words.md, expression.md 등), 수정할 때는 모든 복사본을 동기화해야 합니다.

- runtime 스크립트의 유일한 소스/대상은 `scripts/shared-assets.json`에 정의되어 있습니다. 먼저 `source`을 수정한 다음 `python3 scripts/sync-shared-assets.py sync`를 실행하십시오.
- 동일한 이름의 런타임 스크립트는 하나의 표준 그룹에만 속할 수 있으며, 각 타겟은 반드시 소스 파일의 기본 이름을 그대로 유지해야 합니다. 타겟의 이름을 바꾸어서 단일 소유자의 규칙을 우회하는 것은 금지됩니다.
- 참조 문서의 정규 소스, 배포 복사본 및 디렉터리 미러는 `scripts/shared-references.json`에 명시적으로 정의되어 있습니다. 먼저 소스를 수정한 다음 `python3 scripts/shared-references.py sync`을 실행하십시오. ‘reference target’은 의미상의 별명을 사용할 수 있지만, 반드시 manifest 파일 내에서 각 경로별로 등록되어야 합니다.
- `check-shared-files.sh`은 두 개의 manifest의 관리 경로가 중복되지 않는지 동시에 확인하며, reference 문서는 `shared-references.json`에만 등록됩니다.
- `shared-references.py check`는 콘텐츠 해시로 등록되지 않은 스킬 간 완전 동일 복사본도 검색합니다. 디렉터리 미러의 `files`는 원본 트리 전체를 빠짐없이 포함해야 하며, 새 파일이 매니페스트를 우회해서는 안 됩니다.
- `check-reference-similarity.py`은 다른 스킬과 유사한 복제본을 스캔합니다. 여전히 독립적으로 진화해야 하는 역사적 파생 파일은 `derived_groups`에서 구성원과 그 분화 사유를 등록해야 합니다. 새로 생성된 복제본의 경우 “등록 동기화” 또는 “진정으로 독립적인 콘텐츠로 생성”을 선택해야 하며, 파일 이름을 변경하는 방법으로는 소유자를 우회할 수 없습니다.
- `story-short-analyze`의 `analysis-short-*`은 원문을 관찰하는 데 사용되는 기준 도구일 뿐, 작성 지침서가 아닙니다. 장문으로 이루어진 요소나 볼륨 단위의 반복 구조, 추천되는 구조 비율, 또는 “모든 장에 반드시 포함되어야 할 내용”과 같은 규칙은 다시 도입하는 것이 금지됩니다. 이러한 규칙들은 `check-short-analysis-scope.py`에 의해 검사기로 관리됩니다.
- 제출하기 전에 반드시 `bash scripts/check-shared-files.sh`를 실행해 주십시오. manifest에 등록되어 있지 않은 동일한 이름의 runtime 스크립트는 바로 실패하게 됩니다.

<a id="知识库贡献"></a>
### 지식베이스 기여

가장 가치 있는 기여 유형:

- **실전 데이터**: 각 플랫폼의 최신 순위 분석, 주제별 추세 변화
- **새로운 주제 구조**: 새로운 주제를 다루는 글쓰기 공식, 구조적 템플릿
- **AI 문체 제거 규칙**: 새로운 AI 흔적 패턴, 재작성 예시
- **플랫폼 규칙 업데이트**: 투고 요구 사항 및 추천 메커니즘의 변경 사항

<a id="质量要求"></a>
## 품질 요구 사항

- **운용성**: 콘텐츠는 AI 에이전트가 바로 실행할 수 있어야 하며, 강의식 설명은 피합니다.
- **간결함**: 표와 템플릿을 사용하고, 장문으로 설명하지 마세요.
- **자체 완결성**: 런타임 시 스킬들은 서로 다른 스킬 경로를 통해 참조하는 것이 금지됩니다. 반드시 공유해야 하는 참조 자료는 ‘표준 소스 파일’과 ‘매니페스트 파일’을 사용하여 로컬에 배포된 복사본의 형태로 제공되어야 하며, 이를 통해 각 스킬이 독립적으로 설치될 수 있도록 해야 합니다.
- **한국어**: 이 현지화본의 주석과 문서는 한국어로 작성합니다. 실행에 필요한 식별자·경로·계약 표식은 유지합니다.
- **패치 교체**: 문제를 해결하려고 자주 읽는 경로(`scripts/doc-budget.json` 등록 파일)에 규칙을 추가할 때는 같은 커밋에서 기존 규칙을 같은 분량만큼 삭제하거나 병합합니다. 줄일 수 없을 때만 예산을 늘리고 해당 `why`에 문제의 출처와 모든 사용자가 매 장마다 읽을 가치가 있는 이유를 적습니다. 주요 버전 출시 전마다 재검토하여 스크립트나 훅으로 이미 결정적으로 처리하는 규칙은 삭제합니다.
- **역할별 로딩량 계산 방식**: 에이전트가 실제로 매번 호출할 때 읽어야 하는 파일들은 `agent` 필드가 포함된 예산 경로로 등록됩니다. 템플릿의 frontmatter 부분에 있는 `skills:`은 검사기에 의해 자동으로 계산되며, 미리 로딩되었지만 경로가 등록되어 있지 않은 템플릿은 즉시 검사에 실패합니다. 모든 호출(각 분기 및 중첩된 경우 모두 포함)은 `path_ceiling.limit`(35K, 공백 문자 제외)를 초과하지 않아야 하며, 이를 초과하는 경우는 `path_ceiling.exempt`에만 기재하고 그 이유를 명시해야 합니다. 등록 규칙은 다음과 같습니다: `files`에 `文件#小节标题`가 포함된 경우 해당 섹션만 계산됩니다; `generated`은 패키징 스크립트가 실행된 후에 측정됩니다; `branches`은 기본적으로 상호 배타적이므로, 동일한 호출 내에서 동시에 발생하는 경우는 모두 `stacking.slots`에 포함됩니다(각 슬롯당 최대 1개만 가능하며, 슬롯 간에는 중첩이 가능하고, 검사기는 최악의 경우를 고려하여 계산합니다).
- **작가에게 보내는 보고서**: 작가용 보고서·메시지 템플릿은 일반 ```` ```md ```` 코드 블록에 넣고 바로 위 줄에 `<!-- author-report -->`를 표시합니다. 블록 언어를 `author-report`로 쓰면 모델이 블록을 그대로 작가에게 반환하므로 검사기가 거부합니다. 수행한 일, 발견한 점(원문 포함), 작가가 결정할 일, 다음 단계만 설명합니다. 스크립트명, 필드명, 플래그, 심각도 코드, 맥락 없는 번호는 넣지 않습니다. 꼭 필요한 실행 세부 정보는 블록 마지막에 “기술 참고:” 한 줄로 적습니다. `check-author-reports.py`가 검사합니다.

<a id="提交流程"></a>
## 제출 절차

```
포크 → 브랜치 → 커밋 → PR → 리뷰 → 병합
```

- 한 개의 PR은 하나의 변경 사항에만 초점을 맞춥니다.
- 커밋 메시지는 한국어로 작성하며, 형식은 `유형: 짧은 설명`입니다.
- 유형: `feat`(신규 추가)/`fix`(수정)/`docs`(문서 작성)/`refactor`(구조 재설계)

<a id="plugin-打包与版本锚点"></a>
## 플러그인 패키징 및 버전 고정점

Claude Code과 ZCode 모두 단일한 `oh-story` 번들을 배포하며, 이 번들은 저장소의 루트 디렉터리에서 총 14개의 스킬을 모두 노출합니다. 이전에 스킬별로 13개의 카탈로그 항목으로 나뉘어 있던 구조로 복원하지 않아야 합니다. 두 마켓플레이스의 이름은 각 플랫폼에 맞게 다르게 지정되어 있습니다: Claude는 `oh-story-skills`이며, ZCode의 기본 카탈로그는 `oh-story-zcode`입니다. 양쪽 카탈로그 모두 `name: oh-story`과 `source: ./` 항목은 각각 하나만 존재할 수 있으며, 그 버전은 해당 네이티브 매니페스트와 일치해야 합니다.

`agents_version`은 릴리스 시 이전 릴리스 태그의 값에 1을 더한 수로 설정됩니다. 개발 분기에서 이미 이 목표 값이 사용되고 있는 경우에는 그 값이 변경되지 않으며, PR이 합쳐지는 횟수에 따라 증가하지도 않습니다. 릴리스 전에는 `scripts/current-contract.json`과 배포 안내 내용, 그리고 생성된 템플릿이 일치하는지 확인해야 합니다.

배포 버전에는 총 6개의 JSON/VERSION 파일 앵커 포인트가 있으며, 이들은 반드시 동기화되어야 합니다.

1. `.claude-plugin/marketplace.json`(`metadata.version` 및 유일한 항목인 `version`)
2. `.claude-plugin/plugin.json`
3. `marketplace.json`(`plugins[0].version`; 최상위 레벨의 `version: 1`는 스키마 버전으로, 배포 과정에서 변경되지 않습니다)
4. `.zcode-plugin/plugin.json`
5. `reasonix-plugin.json`
6. `skills/story/VERSION`

Claude는 매니페스트에 명시된 기본 디렉터리를 기반으로 `skills/`을 찾아냅니다. 따라서 catalog 항목이나 `.claude-plugin/plugin.json`에 `skills`, `agents`, `hooks`, `commands`와 같은 필터를 작성해서는 안 됩니다. ZCode의 경우 네이티브 매니페스트에 있는 `skills: "skills"`을 그대로 유지하며, 해당 파일의 Commands/Hooks는 기존의 ZCode을 통해 검증됩니다. 동일한 버전으로 패키징하여 문제를 해결하는 방법에 대한 자세한 내용은 [업그레이드 가이드](skills/story-setup/UPGRADING.md#插件打包身份迁移v079-同版本修复)를 참조하십시오.

검사 단계:

```bash
python3 scripts/check-plugin-packaging.py
python3 scripts/test-plugin-packaging.py
bash scripts/check-claude-adapter.sh
CLAUDE_REAL_CHECK=1 bash scripts/check-claude-adapter.sh  # 옵션: HOME의 실제 CLI 라이프사이클을 분리합니다.
bash scripts/check-zcode-adapter.sh
```

형식 및 명령어는 [Claude Code 플러그인 참조](https://code.claude.com/docs/en/plugins-reference)와 [ZCode 플러그인 문서](https://zcode.z.ai/en/docs/plugin)를 기준으로 합니다. 라이프사이클 스크립트는 Claude CLI를 적용하며, ZCode 데스크톱 버전으로의 마이그레이션은 해당 데스크톱 버전에서 확인해야 합니다.

<a id="opencode-模板同步"></a>
## OpenCode 템플릿 동기화

이 프로젝트는 Claude Code, Google Antigravity, OpenCode, Codex, ZCode, OpenClaw, Reasonix(Phase 1)를 지원합니다. OpenCode는 2.x만 지원합니다(npm 패키지 `@opencode/cli`). 1.x에 머문 `opencode-ai`는 지원하지 않으며 story-setup이 배포 전에 버전을 검사해 차단합니다. OpenCode 에이전트와 프로젝트 지침 템플릿은 `scripts/sync-opencode.py`가 Claude Code 템플릿에서 자동 생성합니다.

<a id="何时需要同步"></a>
### 언제 동기화가 필요한가요?

다음 파일들을 수정한 후에는 동기화 스크립트를 실행해야 합니다:

- `skills/story-setup/references/templates/agents/*.md`(에이전트 정의)
- `skills/story-setup/references/templates/CLAUDE.md.tmpl`(프로젝트 지시서 템플릿)

<a id="同步步骤"></a>
### 동기화 단계

```bash
python3 scripts/sync-opencode.py
python3 scripts/sync-opencode.py --check  # 옵션: 검증만 수행하고 파일은 변경하지 않음
bash scripts/check-opencode-adapter.sh
bash scripts/test-opencode-cli-e2e.sh  # 옵션: 사용자 컴퓨터에 OpenCode 2.x가 이미 설치되어 있어야 합니다(npm i -g @opencode/cli).
```

권한은 Claude 원본의 `tools`/`disallowedTools`에서 유추되며, 금지되는 항목들은 먼저 선언 도구에서 제거되어야 하며, 에이전트 이름에 따라 개별적으로 판단되어서는 안 됩니다. 크로스플랫폼 매핑에는 다음과 같은 제한 사항들이 있습니다:

- 세 개의 생성기는 인라인 배열을 지원합니다(예: `[Read, Glob, Grep]`의 경우, 항목들은 따옴표로 묶일 수 있습니다). Claude 공식 버전 역시 쉼표로 구분된 문자열을 지원하지만, 이 프로젝트에서 사용하는 생성기는 해당 형식을 지원하지 않습니다. 알려지지 않았거나 지원되지 않는 도구들은 생성 파일이 배포되기 전에 오류를 발생시킵니다.
- OpenCode 2.x는 Read, Glob, Grep, Write, Edit, Bash를 지원하며, 네이티브 `permissions:` 규칙 목록을 생성합니다(`action`/`resource`/`effect`의 경우 Bash에 해당하는 action은 `shell`입니다). 명시적으로 `tools`을 사용할 경우 먼저 `*`의 deny 규칙을 적용한 후에만 특정 기능을 허용하며, 명시되지 않은 shell, 위임된 권한, MCP 등은 계속해서 금지 상태를 유지합니다. `tools`가 생략된 경우에만 상위 권한을 상속합니다. OpenCode는 마지막으로 적용된 규칙을 사용하며, 규칙의 순서가 바로 우선순위를 의미합니다. Read/Glob/Grep는 각각 독립적으로 매핑되며, 빈 목록일 경우 모든 기능이 금지됩니다. Write 또는 Edit 중 하나라도 유효하면 `edit` 권한(write/edit/patch)이 전체적으로 허용되며, 이러한 편집 도구들 간의 제한은 적용되지 않습니다. Write는 파일을 덮어쓸 수도 있으며, “단순히 생성만 가능”한 것은 아닙니다.
- Codex는 위에서 언급한 여섯 가지 도구뿐만 아니라 NotebookEdit, PowerShell의 쓰기 기능도 지원합니다. 이 시스템은 파일 시스템 `sandbox_mode`만을 추론할 수 있으며, Claude의 전체 도구 허용 목록을 완전하게 표현할 수는 없습니다. 명시적으로 Read/Glob/Grep만 유효하다고 지정된 경우에만 read-only을 설정합니다; 쓰기 기능이 있는 경우에는 상위 세션의 샌드박스 설정을 상속합니다. `tools`가 생략된 경우에도 상속하며, 일부 금지 사항만을 고려하여 모든 상속된 도구가 읽기 전용이라고 가정하지는 않습니다. 유효한 도구가 하나도 없는 경우에는 이 필드를 사용하여 해당 정보를 표현할 수 없으므로, 그러한 경우에는 정보 생성을 거부합니다.
- Antigravity는 위에 언급된 6가지 도구만 매핑할 수 있으며, 명시적으로 지정된 비어 있지 않은 유효 도구 목록이 필요합니다. 매핑할 수 없는 항목은 오류 메시지를 표시하며, 조용히 삭제되지 않습니다.

회귀 명령: `python3 scripts/test-agent-permissions.py`. `--opencode /path/to/opencode`를 전달하면 실제 OpenCode 2.x CLI와 로컬 모의 모델(`scripts/opencode-mock-llm.mjs`)로 각 에이전트의 실제 도구 목록과 허용·거부 도구의 실행을 검증합니다. 모델 계정은 필요하지 않습니다.

스크립트는 다음과 같이 작동합니다:
1. `templates/agents/` 하위의 Claude Code 에이전트를 opencode 형식으로 변환하여 `opencode/agents/`에 저장합니다.
2. `CLAUDE.md.tmpl`을 `opencode/AGENTS.md.tmpl`에 복사하고, `.claude/` 경로 참조를 대체합니다.
3. 출력된 동기화 결과 요약
4. 선택 사항으로, 실제 CLI를 사용하여 임시 프로젝트에서 14개의 스킬 및 커맨드, 7개의 에이전트를 테스트하고, `story-hooks.ts` 플러그인이 active 상태인지 확인할 수 있습니다. 또한, 모의 모델을 사용하여 실제 운영 환경에서 본문 검사기 기능, 작성 후 보완 처리 과정, 압축 전 데이터 삽입 과정을 테스트할 수도 있습니다.

<a id="ci-检测"></a>
### CI 검사

PR 과정에서 Claude Code 템플릿 파일이 수정되면, CI는 자동으로 opencode 템플릿이 동기화되었는지를 확인하고, 14개의 커맨드, 7개의 에이전트 구조, 그리고 `plugin.ts`의 실제 검사기 동작 및 마무리 과정도 추가로 검사합니다. `cli-compat.yml`는 `@opencode/cli@latest`를 설치하여 실제 CLI 기반의 e2e 테스트와 런타임 권한 테스트를 수행합니다. 만약 CI에서 오류가 발생하면, 로컬에서 동기화 스크립트와 `bash scripts/check-opencode-adapter.sh`를 실행한 후 결과를 다시 제출해 주십시오.

<a id="手动维护的部分"></a>
### 수동으로 유지보수해야 하는 부분

다음 파일들은 자동으로 생성되지 않으므로 수동으로 관리해야 합니다:

- `skills/story-setup/references/opencode/plugin.ts` — 훅 논리
- `skills/story-setup/references/opencode/commands/` — 슬래시 명령어

<a id="sync-opencodepy-已知局限"></a>
### sync-opencode.py의 알려진 한계점들

동기화 스크립트를 실행한 후에는 다음과 같은 수동 검사를 진행해야 합니다:

- **경로 해석 부분**: `fix_path_rules_section()`에 의해 자동으로 처리되었으므로 수동으로 수정할 필요가 없습니다.
- **에이전트 수**: `opencode/agents/`의 경우 항상 7개의 파일로 구성되어 있는지 확인하십시오.

<a id="opencode-关键兼容性问题"></a>
### OpenCode의 주요 호환성 문제

**Glob은 숨겨진 디렉터리를 검색하지 않습니다**: opencode의 Glob 도구는 `.opencode/` 디렉터리를 검색하지 않으므로, 다음과 같은 설계 결정이 내려졌습니다:

- **agent-references**는 `.opencode/skills/`가 아닌 `skills/story-setup/references/agent-references/`에 배포됩니다(숨김 상태가 아님).
- **에이전트 파일**의 이중 배포 방식: `.opencode/agents/`(opencode 시스템에서 사용) + `agents/`(Glob에서 확인 가능한 복사본)
- **하위 에이전트 탐지**: 에이전트를 생성하는 모든 스킬(story, story-review, story-long-write, story-deslop, story-import, story-long-analyze, story-short-write)은 현재 호스트의 정식 디렉터리만 검사합니다. Claude는 `.claude/agents/`, OpenCode는 `.opencode/agents/`, Codex는 `.codex/agents/`, Antigravity는 `.agents/agents/`입니다. 다른 호스트의 파일이 있다는 이유로 사용 가능하다고 판단하지 않습니다. ZCode는 활성화된 플러그인의 런타임 등록에서 같은 이름의 역할을 확인하며 `.zcode/agents/`를 요구하지 않습니다. 역할이나 도구를 사용할 수 없을 때만 대체 방식으로 전환합니다. OpenClaw Phase 1은 프로젝트 에이전트를 배포하지 않고 단독·직접 실행으로 대체합니다.

**플러그인은 백그라운드 서비스에서 실행됩니다**: 2.x에서는 하나의 백그라운드 서비스가 여러 프로젝트를 처리하므로 플러그인의 `process.cwd()`는 사용자 프로젝트가 아닙니다. 프로젝트 루트와 상대 경로 기준점은 항상 `ctx.location.directory`(Git 최상위 디렉터리)를 사용합니다. 압축 전에 `ctx.session.hook("compaction")`으로 요약 요청의 `system`에 집필 맥락 위치를 추가합니다.

**세션 시작 시스템 지침 주입은 미연결 상태입니다**: 2.x의 `ctx.session.hook("context")`는 각 모델 요청 전에 시스템 지침을 수정할 수 있지만, 이 어댑터에는 세션 시작 시 배포 상태·집필 진척 알림을 아직 연결하지 않았습니다. 사용자는 `/story-setup`을 직접 실행해 상태를 확인할 수 있습니다.

**기타 훅의 차이점**: `detect-gaps`(빈틈 감지) 플러그인은 이식되지 않았으며, 세션 시작 시 알림 메시지가 표시되지 않습니다(단, compact 요약 및 본문 작성 전의 개요 검사기 기능은 그대로 유지됩니다); `session-end` opencode에는 해당하는 이벤트가 없어 현재로서는 지원되지 않습니다; `validate-commit`는 git의 원본 `pre-commit` 훅으로 대체되었으며, 이는 모든 CLI에서 사용할 수 있습니다.

<a id="opencode-使用注意事项"></a>
### OpenCode 사용 시 주의 사항

- **배포 후 실행하는 슬래시 커맨드**: 2.x 버전에서는 `.opencode/commands/`, 에이전트, 플러그인 및 설정 내용이 자동으로 재로드됩니다. 만약 이러한 과정이 수행되지 않는다면 `opencode reload`을 실행하거나, 프로그램을 종료한 후 `opencode -c`를 실행하여 다시 진입하십시오.
- **첫 번째 배포 시에는 자연어를 사용하여 실행:** 새로운 프로젝트에서는 슬래시 커맨드가 없으므로, story-setup을 자연어로 실행해야 합니다(예: “story-setup 스킬을 사용하여 웹소설 작성 환경을 설정해 주세요”).
- **browser-cdp의 장시간 작업이 멈출 수 있습니다**: OpenCode에는 백그라운드 작업 기능이 없어 오래 걸리는 브라우저 작업은 사용자가 `ESC`로 중단해야 합니다. SKILL.md에 시간제한 래퍼 사용 안내가 포함돼 있습니다.

<a id="openclaw-适配维护"></a>
## OpenClaw의 어댑터 유지보수

OpenClaw 현재는 **Phase 1 skills-only**를 사용하여 적용하고 있습니다.

- 표준 소스는 여전히 저장소의 루트 `skills/`입니다. OpenClaw을 위해 별도의 스킬을 유지보수하지 마십시오.
- 모든 `SKILL.md` 프론트마터는 OpenClaw/AgentSkills의 규칙을 준수해야 합니다. 즉, 한 줄에 `name`를, 한 줄에 `description`을, 한 줄에 JSON 형식의 `metadata`를 작성해야 하며, `metadata.openclaw`도 반드시 존재해야 합니다.
- `metadata.openclaw.requires.bins/env/config/anyBins`은 OpenClaw 및 load-time의 게이팅에 사용됩니다. 예를 들어, `story-cover`의 가시성은 `GPT_IMAGE_API_KEY`를 통해 제어됩니다.
- `story-setup target_cli=openclaw`은 프로젝트 `skills/`과 `references/openclaw/AGENTS.md.tmpl`만 배포하며, OpenClaw의 에이전트/훅/플러그인은 배포하지 않습니다.
- OpenClaw는 세션을 시작할 때 로드 조건을 충족하는 스킬의 스냅샷을 만듭니다. 변경 후에는 새 세션을 시작하거나 스킬 감시기의 갱신을 기다려야 합니다.

<a id="openclaw-检查步骤"></a>
### OpenClaw 검사 단계

```bash
bash scripts/check-openclaw-skills.sh
OPENCLAW_REAL_CHECK=1 bash scripts/check-openclaw-skills.sh  # 이 장치에 openclaw를 설치할 때 선택적으로 사용할 수 있습니다.
```

`OPENCLAW_REAL_CHECK=1`은 임시 프로필과 임시 작업 공간을 사용하여 격리된 에이전트를 생성하며, OpenClaw CLI가 작업 공간 `skills/`에서 14개의 스킬을 정상적으로 인식할 수 있는지를 확인합니다. 스크립트가 끝나면 임시 프로필은 삭제됩니다.

<a id="openclaw-已知边界"></a>
### OpenClaw의 알려진 한계

- **에이전트 기능의 일시 중단**: OpenClaw의 에이전트/세션 모델이 Claude/Codex 프로젝트 내의 에이전트 파일과 다르기 때문에, OpenClaw 게이트웨이용 에이전트는 일시적으로 생성되지 않습니다. 에이전트 간의 협력이 필요한 스킬들은 반드시 솔로/직접 모드로 전환되어야 합니다.
- **훅의 일시적인 보류**: 본문을 작성하기 전에 개요 검사기, 커밋 알림, session-start/compact의 삽입 내용이 OpenClaw 훅/플러그인으로 마이그레이트되지 않았으므로, OpenClaw는 스킬 프로세스에서만 부드러운 제약 조건으로 사용됩니다.
- **package 발행 일정 연기**: OpenClaw은 workspace/personal/managed 스킬 루트를 인식할 수 있으나, 현재 단계에서는 OpenClaw 네이티브 플러그인 package를 발표하지 않을 예정입니다.

<a id="google-antigravity-适配维护"></a>
## Google Antigravity의 어댑터 유지보수

Antigravity 2.0과 `agy` CLI는 모두 `.agents/` 워크스페이스 커스터마이징 기능을 공유하지만, 릴리스 전에는 각각 별도로 실제 환경에서 테스트를 수행하는 것이 권장됩니다. 모든 지원 기능은 `story-setup`를 통해 프로젝트에 배포되며, 배포 도구에는 `~/.gemini/`가 사용되지 않습니다.

- 14개의 스킬이 실제 `.agents/skills/{name}/` 형태로 구현되었습니다. `deploy-antigravity-skills.py`은 기존에 알려진 이름만을 대체하며, 사용자의 스킬은 그대로 유지됩니다. 기존의 심볼릭 링크는 기본적으로 fail-closed를 사용하며, 사용자가 명시적으로 동의한 경우에만 해당 스킬들이 이전되며, 링크를 통해 대상 디렉터리로 파일이 복사되어서는 안 됩니다.
- 7개의 커스텀 에이전트는 Claude Markdown 원본을 배포할 때 `.agents/agents/agent-name/agent.md`에 생성됩니다(`agent-name`은 실제 이름으로 대체해야 합니다). 도구명은 반드시 공식 목록에 있는 이름을 사용해야 하며, 호출 시에는 `invoke_subagent`와 동일한 이름의 `TypeName`을 함께 사용해야 합니다. 이 생성기는 이미 정의된 7개의 에이전트만을 대체하며, 다른 사용자들이 정의한 에이전트들은 그대로 유지됩니다.
- Always-On Rule은 `.agents/rules/oh-story.md`로 고정되어 있으며, 파일 크기는 12,000자 미만이어야 합니다. 이 규칙은 스킬 라우팅 및 compact 처리 후에 `추적/문맥.md`을 다시 읽어오는 역할을 수행합니다. Antigravity에 Claude의 PreCompact/PostCompact 기능이 있다고 가정하지 마십시오.
- `.agents/hooks.json`은 최상위 레벨의 named-group 매핑입니다. 병합기는 `oh-story` 그룹만을 대체하며, 모든 사용자 그룹은 그대로 유지됩니다. 현재 `PreToolUse`, `PostToolUse`, `PreInvocation`, `Stop`가 등록되어 있는 경우, PreToolUse에서는 반드시 `decision`을 출력해야 하며, PostToolUse에서는 정확하게 `{}`을 출력해야 합니다. 작업 결과는 해당 세션의 `artifactDirectoryPath`에 저장되며, 다음 번 PreInvocation 시에 이 데이터가 사용됩니다. Stop은 이어서 실행하도록 강제하는 동작을 최대 한 번만 수행합니다.
- `.agents/hooks/`에서는 `story_antigravity_hook.js`와 공유 `story_hook_core.js`만 관리합니다. 후자는 `scripts/shared-assets.json`이 바이트 단위 일치를 강제하므로 복사본을 직접 수정하지 않습니다. 훅은 PATH의 Node에 의존합니다.

검사 단계:

```bash
bash scripts/check-antigravity-adapter.sh
python3 scripts/test-antigravity-skills-deploy.py
python3 scripts/test-antigravity-hook-merge.py
node scripts/test-antigravity-hooks.mjs
```

현재 Antigravity 2.0 / `agy`가 설치돼 있다면 임시 집필 프로젝트에서 `story-setup`을 실행하고 새 대화를 연 뒤 `/skills`, `/agents`, `/hooks`로 탐색 여부를 확인합니다. IDE와 대화형 CLI를 각각 검증합니다. 출력 모드 `agy -p`에는 반드시 `--add-dir "$PWD"`를 전달합니다. agy 1.2.10 실측에서는 이 옵션을 넣으면 작업 공간 `.agents/`의 스킬 14개, 에이전트 7개, 훅을 로드하고, 빼면 모두 로드하지 않아 일반 모델 출력을 `~/.gemini/antigravity-cli/scratch/`에 쓸 수 있었습니다. 테스트 후 뜻하지 않은 임시 산출물을 확인하고 정리합니다. 자동 검사는 사용자 전역 설정을 읽거나 쓰지 않으며 이 실환경 검증을 대체하지 않습니다.

<a id="zcode-适配维护"></a>
## ZCode의 어댑터 유지보수

ZCode는 “네이티브 플러그인 + `story-setup` 워크스페이스 배포”라는 두 가지 방식을 사용합니다.

- `.zcode-plugin/plugin.json`과 기본 `marketplace.json`은 동일한 이름과 버전을 가진 단일 `oh-story` 번들로 제공되며, 이 번들에는 14개의 스킬, 14개의 커맨드, 7개의 플러그인 역할, 그리고 ZCode 후크가 포함되어 있습니다. 카탈로그 자체의 이름은 `oh-story-zcode`로 유지되며, 각 항목에 포함된 플러그인의 버전은 반드시 `skills/story/VERSION`와 동기화되어 있어야 합니다.
- `skills/story-setup/references/zcode/`은 워크스페이스 배포 템플릿으로, `AGENTS.md.tmpl`, Commands, 생성된 플러그인 에이전트들, `config.json.patch`, 그리고 제3자 의존성이 없는 Node Hook 러너를 포함하고 있습니다.
- ZCode 3.3.4는 `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PermissionRequest`, `PostToolUse`, `PostToolUseFailure`, `Stop`만을 지원합니다. Claude의 `PreCompact`, `PostCompact`, `SessionEnd`, `SubagentStop` 또는 `Notification`를 복사하지 마십시오.
- stdout Hook가 비어 있으면 통과됩니다. 비어 있지 않은 경우에는 반드시 엄격한 JSON 스키마를 준수해야 합니다. 진단 정보는 stderr에만 기록되며, 이상 발생 시 fail-open이 사용됩니다. `process`과 `node`를 우선적으로 사용하십시오. shell/Python 런처의 크로스플랫폼 버전을 도입하지 마십시오.
- ZCode는 플러그인 하위 에이전트를 지원합니다. `.zcode-plugin/plugin.json`의 `agents`는 `references/zcode/agents/`를 가리킵니다. `python3 scripts/generate-zcode-agents.py`로 Claude 원본에서 생성해 커밋합니다. 검사 스크립트는 생성 결과 일치와 권한 회귀를 확인합니다. 모델은 현재 세션을 상속하며 도구 허용·금지 목록을 유지합니다. Claude 인라인 훅을 그대로 옮기지 않습니다. 작품 분석 역할의 경로 범위는 여전히 프롬프트 제약이며 강한 격리를 보장하지 않습니다. 공식 근거: [플러그인](https://zcode.z.ai/en/docs/plugin), [하위 에이전트](https://zcode.z.ai/en/docs/subagents).
- `.zcode/agents/`/`.zcode/rules/`을 생성하거나 사용자의 홈 디렉터리에 파일을 저장하지 않습니다. 스킬 전용 설치 방식에서는 플러그인 역할을 등록하지 않으며, 플러그인을 활성화하거나 업데이트하라는 메시지가 표시됩니다. 단, 고정된 설정을 사용하거나 프로젝트를 반복적으로 배포하는 방식은 적용되지 않습니다.

<a id="zcode-检查步骤"></a>
### ZCode 검사 단계

```bash
python3 scripts/generate-zcode-agents.py --check
bash scripts/check-zcode-adapter.sh
bash scripts/test-zcode-hooks.sh
bash scripts/test-prose-net-parity.sh
```

본문의 경량 결정적 검사망를 업데이트할 때는 Claude, OpenCode, Codex, Antigravity, ZCode의 다섯 가지 구성 요소를 동기화해야 하며, shared-assets / parity / Antigravity의 훅 테스트가 통과되어야 합니다.

<a id="reasonix-适配维护"></a>
## Reasonix의 어댑터 유지보수

Reasonix(DeepSeek-Reasonix CLI)은 현재 스킬, 원본 플러그인 매니페스트, 그리고 skills-only를 활용한 프로젝트 수준의 `story-setup` 배포를 지원합니다. 훅과 커스텀 에이전트에 대해서는 후속 단계에서 구현될 예정입니다(전문 에이전트가 관련된 스킬의 경우 솔로 모드로 작동하거나 직접적인 대체 방안이 적용될 것입니다).

- `reasonix-plugin.json`은 플러그인 매니페스트이며, `version`은 반드시 `skills/story/VERSION`와 동기화되어야 합니다(`check-reasonix-adapter.sh`는 검사기의 역할을 합니다).
- Reasonix는 프로젝트 스킬 루트(`.agents/skills` 등, Codex와 공유하는 `skills/` 대상 심볼릭 링크)를 기본 탐색하여 14개 스킬을 발견합니다.
- `story-setup`의 `target_cli=reasonix`을 skills-only에 배포하는 방법: 14개의 스킬을 프로젝트 `skills/`에 복사한 후 `references/reasonix/AGENTS.md.tmpl`에 저장하되, 훅이나 에이전트는 배포하지 않습니다(OpenClaw 및 generic과 동일한 구조이며, `check-story-setup-deployment.sh`이 이를 검사기로 보호합니다). Reasonix의 배포 경로나 템플릿을 변경할 경우에는 해당 검사기 설정도 동기화되어야 합니다.
- 실제 CLI를 사용해 확인해 보면 `reasonix doctor capabilities`이 CI 내에 포함되어 있지 않은 것을 알 수 있으며, 배포 전에 수동으로 실행해 볼 수 있습니다.

<a id="reasonix-检查步骤"></a>
### Reasonix 검사 단계

```bash
bash scripts/check-reasonix-adapter.sh
```

<a id="codex-适配维护"></a>
## 코덱스의 어댑터 유지보수

이 프로젝트는 Codex CLI(repo skills를 통한 스킬 발견)과 `$story-setup`(프로젝트 배포) 두 가지 방식을 모두 지원합니다.

- repo-local 스킬: `.agents/skills`은 `skills/`를 가리키는 상대적인 심볼릭 링크입니다(`../skills`, agentskills.io 표준 경로). Codex가 이를 스캔하면 해당 스킬을 발견할 수 있지만, 두 번째 복사본을 만들어서는 안 됩니다. 이 심볼릭 링크는 반드시 유효한 상대적인 링크여야 합니다(`check-codex-adapter.sh`의 검사기 설정에서 target가 `../skills`인 경우만 유효합니다; 무효하거나 절대 경로인 경우에는 스킬을 발견할 수 없습니다. 자세한 내용은 openai/codex#11314를 참조하십시오). Windows 환경에서는 git `core.symlinks=true`을 사용해야 합니다. OpenClaw는 작업 공간의 `skills/`를 직접 탐색하므로 해당 심볼릭 링크에 의존하지 않습니다.
- 프로젝트 배포 훅: `skills/story-setup/references/codex/hooks/hooks.json`은 `$story-setup`이 집필 프로젝트에 배포합니다. POSIX `command`와 Windows `commandWindows` 모두 현재 디렉터리에서 위로 올라가며 `.codex/hooks/run-story-hook.*`를 찾고 Git 저장소에 의존하지 않습니다. 찾으면 공유 실행기가 이벤트 허용 목록, 인터프리터 탐색, `CODEX_PROJECT_DIR` 주입, Python 훅 실행을 일괄 처리합니다.
- Windows 훅: Codex는 Windows에서 `%COMSPEC% /C`(cmd.exe)를 사용하여 `commandWindows`을 실행합니다. 현재 등록된 명령들은 PowerShell을 이용하여 단계적으로 상위 항목을 확인한 후에 `run-story-hook.cmd`를 호출하므로, 중첩된 작업 디렉터리도 POSIX 행동 규칙에 따라 동작하며, 프로젝트 루트 디렉터리만을 지원하는 것은 아닙니다. 이벤트 목록이나 런처를 변경한 후에는 반드시 생성기를 다시 실행하고 적합성을 확인해야 하며, 6개의 등록 항목 내에서 수동으로 탐지 로직을 복사하는 것은 금지됩니다.
- 커스텀 에이전트: `skills/story-setup/references/codex/agents/*.toml`은 `scripts/generate-codex-agents.py`이 `references/templates/agents/*.md`에서 생성합니다. Claude 에이전트 템플릿을 수정한 후에는 반드시 다시 생성하여 제출해야 합니다.

<a id="codex-同步步骤"></a>
### 코덱스 동기화 단계

```bash
python3 scripts/generate-codex-agents.py
python3 scripts/generate-codex-hooks.py
bash scripts/check-codex-adapter.sh
bash scripts/test-codex-hooks.sh
```

<a id="codex-关键兼容性问题"></a>
### 코덱스의 주요 호환성 문제

- **훅의 신뢰 장벽**: Codex 프로젝트 `.codex/`의 설정 계층은 반드시 신뢰를 받아야 하며, 관리되지 않는 명령 훅의 경우 사용자가 `/hooks`에서 검토 및 신뢰를 부여한 후에만 실행됩니다. 신뢰를 받기 전에는 Codex가 이러한 훅들(본문을 작성하기 전의 개요 검사기를 포함하여)을 자동으로 건너뛰며 오류를 보고하지 않습니다. 자동화 과정에서는 `codex exec`에 `--dangerously-bypass-hook-trust`을 추가할 수 있습니다.
- **훅 JSON 계약**: `PreToolUse`, `PreCompact`, `PostCompact`의 일반적인 stdout은 무시됩니다. JSON 형식으로 데이터를 출력해야 하는 경우에는 `hookSpecificOutput.permissionDecision = "deny"`이나 `hookSpecificOutput.additionalContext`를 사용해야 합니다.
- **PreToolUse 불완전한 차단 기능**: Codex 공식 설명에 따르면, 현재의 셸/편집 기능을 통한 차단 메커니즘은 완벽한 보안 장치가 아닙니다. 스토리 훅은 단지 글쓰기 과정에서의 안전 장치 역할을 할 뿐이며, 버전 관리나 수동 검토를 대체할 수는 없습니다.
- **에이전트 파일 형식**: Codex 커스텀 에이전트의 경우 `.codex/agents/{name}.toml`을 사용해야 하며, `name`, `description`, `developer_instructions`도 반드시 필요합니다. 읽기 전용 에이전트는 `sandbox_mode = "read-only"`를 사용합니다.
- **사용자 정의 에이전트의 런타임 등록**: `$story-setup`이 `.codex/agents/*.toml`을 작성한 뒤 프로젝트 `.codex/` 설정 계층을 신뢰하고 새 Codex 세션을 시작해야 합니다. 현재 런타임이 여전히 `unknown agent_type`을 반환한다면(로컬 `codex exec 0.141.0` 임시 프로젝트 스모크 테스트에서 재현됨), 스킬은 단독·직접 실행으로 전환하고 그 사실을 보고해야 합니다. 자동 검사의 필수 통과 조건은 TOML 스키마와 파일 배포 검사입니다.

한국 플랫폼 기본 분기·게시 자료 초안 검사는 `python scripts/test-korean-platforms.py`로 실행합니다. 국내 형식 검사의 통과는 플랫폼 공식 요건 검증이 아니며 기존 판체 검사는 `python scripts/test-publish-format.py`로 함께 확인합니다.
