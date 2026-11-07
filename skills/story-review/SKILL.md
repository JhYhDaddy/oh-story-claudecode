---
name: story-review
version: 1.1.1
description: "여러 관점의 대립적 검토. reviewer 에이전트가 배포돼 있으면 full/lean 모드에서 병렬 생성합니다. 에이전트가 없거나 비정상 또는 생성에 실패하면 자동으로 solo로 전환하며, 참고 파일을 읽을 수 없으면 내장 평가 기준을 사용합니다. 호출: /story-review, /审查, 검토해 줘, 원고를 검토해 줘."
metadata: {"openclaw":{"source":"https://github.com/zenstory-ai/oh-story-claudecode"}}
---
# story-review: 여러 관점의 대립적 검토

> 생성 버전 안내(생성을 차단하지 않음): 프로젝트 루트 `.story-deployed`의 `agents_version`부터 읽습니다. 현재 `agents_version: 38`과 다르면(표식 없음, 필드 없음·정수 아님, 38보다 작거나 큼) **照常按当前宿主角色来源检查并 spawn** — 평소처럼 현재 호스트의 역할 출처를 확인하고 생성합니다. 동시에 “이번 검토 방법”에서 작가에게 “원고 검토 도우미가 이전 버전입니다. /story-setup을 실행하고(ZCode는 먼저 플러그인 업데이트) 새 대화를 시작하세요”라고 한 문장으로 알립니다. `Notice: agents bundle 版本不匹配（项目 {N}，本版 38）` 원문은 `技术备注`(기술 비고) 줄에 씁니다. **大于 38 时额外提示先更新 oh-story-claudecode** — 38보다 크면 oh-story-claudecode부터 업데이트하라고 추가로 안내하고 로컬의 이전 setup으로 덮어써 다운그레이드하면 안 됩니다. 版本提示本身不触发降级；文件缺失或异常、工具不可用、递归限制或调用失败按 Phase 0 处理 — 버전 안내 자체는 solo 전환 사유가 아닙니다. 파일 누락·이상, 도구 사용 불가, 재귀 제한, 호출 실패는 Phase 0에 따라 처리하고 `技术备注`에 `Fallback: ... -> solo`를 씁니다.

검토를 조율하며 소설의 구조, 인물, 문장, 설정 문제를 찾고 원문 근거가 있는 수정안을 제시합니다.

**실행 원칙: 검토는 문제를 찾는 일이며 올바름을 입증하는 일이 아닙니다.**

**문체 판단**: 먼저 [references/style-resolution.md](references/style-resolution.md)를 읽고 이 책의 문체를 불러옵니다. 호출자가 정한 `style_resolution`과 작가 선호를 재사용합니다. 단독 호출이면 현재 요청과 이 책의 문체로 판단합니다. 같은 판단 결과를 이후 실행자에게 전달합니다.

## 작가 선호의 경계

호출자가 이미 가진 작가 선호만 받으며 작가 기억을 조회하거나 기록하지 않습니다. 독립 호출이면 기억 파일을 불러오지 않습니다. 선호는 의도 해석과 보고 구성에만 활용합니다. 평가 기준의 심각도를 낮추거나 사실 충돌을 문제없다고 판정하거나 플랫폼 통과 조건을 건너뛰는 근거로 삼으면 안 됩니다. 현재 요청이 여전히 우선입니다.

---

## Review Mode 선택

- `/story-review` 또는 `/story-review full` → 에이전트 4개 모두 생성을 우선합니다. 이미 하위 에이전트 안이거나 필수 에이전트가 미배포·비정상이거나 생성에 실패하면 자동으로 solo로 전환합니다.
- `/story-review lean` → `story-architect` + `consistency-checker` 생성을 우선합니다. 이미 하위 에이전트 안이거나 필요한 에이전트 중 하나라도 미배포·비정상이거나 생성에 실패하면 자동으로 solo로 전환합니다.
- `/story-review solo` → 에이전트를 생성하지 않고 현재 세션에서 기본 검토를 수행합니다.

---

## Phase 0: 사전 확인과 대체 모드 전환(반드시 먼저 수행)

1. **요청 모드 확인**: 사용자 입력의 `full`, `lean`, `solo`를 해석합니다. 지정하지 않으면 목표 모드는 `full`입니다.
2. **생성 허용 여부 확인**: 이미 하위 에이전트/Agent 안에서 실행 중이면 재귀적으로 생성하지 않고 바로 `solo`로 전환합니다.
3. **현재 호스트의 역할 출처 확인**: ZCode는 플러그인 하위 에이전트를 지원합니다. 활성 플러그인이 등록한 같은 이름의 역할을 확인하며 `.zcode/agents/`는 필요하지 않습니다. 다른 호스트는 다음 단계에서 해당 호스트의 디렉터리를 확인합니다. 호스트 이름, 배포 표식의 zcode 포함 여부, 다른 호스트 디렉터리의 존재를 이유로 전환하지 않습니다.
4. **필수 에이전트 사용 상태 확인**(현재 호스트 출처만 확인):
   - Claude Code `.claude/agents/`, OpenCode `.opencode/agents/`, Codex `.codex/agents/`, Antigravity `.agents/agents/`를 확인합니다. ZCode는 등록 역할의 정의를 확인하고 프로젝트 파일 존재 여부로 런타임 등록을 대신 판단하지 않습니다.
   - full 필수 에이전트: `story-architect`, `character-designer`, `narrative-writer`, `consistency-checker`
   - lean 필수 에이전트: `story-architect`, `consistency-checker`
   - 각 필수 에이전트의 확인 사항:
     - **Claude Code 에이전트(`.claude/agents/`)**: frontmatter를 읽고 `name:`이 subagent_type과 완전히 같은지 확인합니다. frontmatter가 없거나 파싱할 수 없거나 name이 다르면 malformed agent로 간주합니다.
     - **OpenCode 에이전트(`.opencode/agents/`)**: 파일명이 에이전트 이름입니다(OpenCode는 frontmatter의 `name:`을 요구하지 않음). frontmatter에서 `mode: subagent`와 `permissions:` 규칙 목록이 있고 파싱 가능한지 확인합니다. 2.x는 복수형 `permissions:`를 사용하며 이전 단수형 `permission:`은 재배포 대상으로 봅니다. frontmatter가 없거나 파싱 불가이면 malformed입니다.
     - **Codex 에이전트(`.codex/agents/`)**: 파일명은 `{agent}.toml`입니다. TOML이 파싱 가능하며 `name`, `description`, `developer_instructions`를 포함해야 합니다. `name`은 대상 에이전트와 완전히 같아야 합니다.
     - **Antigravity 에이전트(`.agents/agents/`)**: 경로는 `.agents/agents/agent-name/agent.md`입니다(`agent-name`은 대상 이름). frontmatter가 파싱 가능하며 `name`은 대상 이름과 같고 `mainAgent: false`, `subagent: true`, 비어 있지 않은 `tools`를 갖춰야 합니다. 누락·불일치는 malformed입니다.
     - **ZCode 플러그인 에이전트**: 등록 이름이 대상 역할과 같아야 합니다. 정의를 읽을 수 있으면 파싱 가능한 `name`, `description`, 본문이 필요합니다. 정의를 직접 읽을 수 없으면 런타임 등록을 기준으로 하며 다른 호스트 파일을 검색하지 않습니다.
   - 필요한 역할이 하나라도 없거나 malformed이면 배정을 시도하지 않고 `solo`로 전환합니다. 도우미가 없거나 손상됐다고 쉽게 설명하고 현재 호스트에서 재배포하도록 권장합니다(ZCode는 oh-story 플러그인을 업데이트·활성화한 뒤 새 대화 시작). `missing agents -> solo` / `malformed agents -> solo`와 문제 역할·파일을 기술 비고의 Fallback, Files 두 항목에 기록합니다.
5. **에이전트 도구 사용 가능 여부 확인**: Claude/OpenCode/Codex는 현재 런타임의 하위 Agent/Task 도구, Antigravity는 `invoke_subagent`가 필요합니다. ZCode는 현재 스키마에 맞춰 `Agent`로 등록 역할을 배정합니다. 사용할 수 없으면 `solo`로 전환하고 `技术备注`(기술 비고) 줄에 `Fallback: agent tool unavailable -> solo`를 씁니다.
6. **런타임 실패 시 전환**: 에이전트 생성이 하나라도 실패하거나 `subagent_type` / `agent` / `agent_type` / `TypeName`을 사용할 수 없거나 frontmatter/TOML 런타임 파싱 실패 또는 하위 에이전트 시작 실패가 발생하면 추가 생성을 멈춥니다. `solo`로 다시 검토하고 `技术备注`(기술 비고) 줄에 `Fallback: spawn failed -> solo`와 실패한 이름을 씁니다. 일부 성공한 에이전트의 결과를 full/lean 결론으로 삼지 않습니다.
7. **실제 모드 확정**: 요청 모드와 실제 모드를 모두 보고 끝의 기술 비고 줄에 씁니다.

---

## 검토 기준과 참고 자료 규칙(필수)

참고 파일은 검토 기준을 보충합니다. 읽을 수 없으면 아래 내장 기준 묶음을 사용합니다.

### 작가를 위한 보고(필수)

보고는 작가를 대상으로 합니다. 무엇을 검토했는지, 어디를 고칠지, 이유(독자 경험과 이야기 결과로 설명하고 원문 인용 첨부), 작가가 결정할 일, 다음 단계를 담습니다. reviewer 이름, S1–S4, Gate, 탐지기 범주명, 스크립트 이름, PASS/FAIL, 파일 필드명은 본문에 넣지 않습니다. 위치는 “N장 ‘인용문’” 또는 “N장 M번째 문단”으로 씁니다. 우선순위는 쉬운 말로 바꿉니다(소제목은 템플릿 사용). S1·S2 → **반드시 수정**, S3 → **수정 권장**, S4 → **수정하지 않아도 됨**. 실행 경로는 보고 마지막 줄에만 아래 고정 형식으로 씁니다. `技术备注`는 기술 비고를 뜻하는 계약 표식입니다.

```text
技术备注：Mode {요청}→{실제} · Fallback {none | project custom agents unavailable -> solo | missing agents -> solo | malformed agents -> solo | agent tool unavailable -> solo | spawn failed -> solo | subagent recursion guard -> solo} · Rubric {fanqie | qidian | zhihu | generic} ({file | embedded})[ · Files {누락되거나 비정상인 에이전트 파일}][ · Notice {버전 불일치 원문}]
```

### 참고 자료 탐색 순서

참고 파일을 읽을 수 있으면 다음 순서로 시도하고 처음 찾은 파일을 사용합니다.
1. `{项目根}/.claude/skills/{规范路径}`(Claude Code 프로젝트 설치)
2. `{项目根}/.opencode/skills/{规范路径}`(OpenCode 프로젝트 설치)
3. `{项目根}/.codex/skills/{规范路径}`(Codex 프로젝트 설치)
4. `{项目根}/.zcode/skills/{规范路径}`(ZCode 프로젝트 설치)
5. `{项目根}/skills/{规范路径}`(OpenClaw / Reasonix / generic 배포이며 이 저장소의 개발 환경)
6. `{项目根}/.agents/skills/{规范路径}`(Antigravity 프로젝트의 실제 skill root; Codex / Reasonix도 이 디렉터리나 심볼릭 링크를 탐색할 수 있음)
7. 현재 런타임에서 이 스킬을 불러온 디렉터리 또는 접근 가능한 전역 스킬 검색 경로의 같은 이름 `{skill-name}/...` 디렉터리

> 앞쪽 경로가 없는 것은 정상이며 배포 손상이 아닙니다. `/story-setup`은 Antigravity에서 스킬 14개를 `.agents/skills/`에 실제 복사하고, ZCode에서는 `.zcode/skills/`, OpenClaw / Reasonix / generic에서는 `skills/`에 복사합니다. Codex 프로젝트 배포는 스킬 본체를 복사하지 않습니다. Codex가 skill root에서 이 스킬을 불러오므로 references는 대개 6번째 또는 7번째에서 찾습니다. `references/`를 `.codex/skills/`에 수동 복사하지 마세요. 수동 사본은 story-setup의 관리 대상이 아니므로 업그레이드 후 알림 없이 낡은 상태로 남습니다.

표준 경로는 다음과 같습니다. 파일명만 단독으로 쓰거나 다른 스킬의 references를 잘못 읽어서는 안 됩니다.

| 용도 | 표준 경로 |
|---|---|
| 일반 콘텐츠 평가 기준 | `story-review/references/quality-rubric.md` |
| AI 문체 정리 방법 | `story-review/references/expression.md` · `story-review/references/narrative-focus.md` · `story-review/references/story-logic.md` |
| 어휘·문장 신호 색인 | `story-review/references/banned-words.md` |
| 플랫폼 평가 기준 | `story-review/references/rubrics/{fanqie,qidian,zhihu}.md` |
| 문장부호 사전 검사 스크립트 | `story-review/scripts/normalize-punctuation.js` |
| AI 문형 사전 검사 스크립트 | `story-review/scripts/check-ai-patterns.js` |

### 내장 검토 기준 묶음(경로를 읽을 수 없으면 필수)

현재 프로젝트에서 위 참고 파일을 읽을 수 없더라도 **평가 기준 없는 검토로 낮추거나 보고에서 “구체적인 평가 기준을 불러올 수 없음”이라고 한 뒤 기준 적용을 멈추면 안 됩니다.** 반드시 이 절의 내장 기준 묶음을 사용하고 기술 비고 줄의 Rubric 출처를 `embedded`로 씁니다.

通用网文内容 rubric：

- 核心卖点：핵심 매력: 이번 장이 명확한 매력을 중심으로 전개되는가? 매력이 드러나지 않으면 최소 S2.
- 冲突推进：갈등 전개: 장애물, 선택, 대가 또는 관계 변화가 있는가? 설명·잡담·요약뿐이면 최소 S2.
- 任务卡点：과업의 막힘: 인물이 일을 하다 막힐 때 정보·관계·대가·선택·복선이 달라지는가? 절차 세부 사항만 남고 삭제해도 이야기에 영향이 없으면 최소 S3.
- 情绪曲线：감정 곡선: 밑작업, 고조, 해소 또는 반전이 있는가? 감정이 평평하거나 뜬금없으면 최소 S2/S3.
- 钩子与期待：후킹과 기대: 시작이나 끝이 후속 질문을 만드는가? 서스펜스나 미완의 기대가 없으면 최소 S2.
- 开头新鲜度（仅开篇/前 3 章）：도입의 참신함(도입부/첫 3장만): 구체적인 인물·상황에서 시작하는가, 같은 장르의 기본 전형인가(동종 작품 어디에나 통째로 옮길 수 있는가)? “후킹 있음/날씨로 시작하지 않음”은 획일성을 면제하지 않습니다. 전형적인 도입은 후킹이 있어도 최소 S3이며 장르 템플릿과 전체적으로 겹치면 S2.
- 角色动机：인물 동기: 행동이 목표, 성격, 상황, 관계 압력에 맞는가? 줄거리를 위해 왜곡되면 S1/S2.
- 对话质量：대화 품질: 속뜻, 정보 통제, 인물 차이가 있는가? 설명서식 대화는 최소 S2.
- 设定一致性：설정 일관성: 이미 쓴 규칙, 시간선, 인물 속성을 어기지 않는가? 명확한 사실 충돌은 보통 S1.
- 文字自然度：문장의 자연스러움: 구체적이고 감각적이며 행동이 정보를 전달하는가? AI 말투, 상투어, 요약체는 영향에 따라 S2/S3.
- 句长节奏：문장 길이와 리듬: 이 책의 문체, 의미 연결, 장면 기능으로 판단합니다. 기계적인 짧은 문장, 행동 목록, 비대한 긴 문장은 영향에 따라 S3/S2이며 일률적인 글자 수나 문장 길이 템플릿으로 검수하지 않습니다.
- 标点节奏：문장부호 리듬: 부호가 어조·인물의 목소리에 기여하는가? 전체를 마침표로만 끊거나 물음표·느낌표를 무작위로 쌓거나 `……`/`——`를 남겨 억지로 멈춤을 만들면 영향에 따라 S3/S2.
- 具体字数表达校验：구체적인 글자 수 표현 검증: 본문이 “이 다섯 글자 / 짧은 네 글자 / 세 글자가 떨어지자 / 여덟 글자가 내리꽂혔다”처럼 대사·제자·편지·생각·실시간 댓글을 구체적인 글자 수로 평가하면 집계 기준, 기계 검증 결과, 서사적 필요를 확인할 수 있어야 합니다. 정확한 계산을 보장할 수 없으면 문장 자연스러움 문제로 처리하고 “이 말이 끝나자”, “그 몇 글자”, “말소리가 잦아들자” 등 구체적인 숫자 없는 표현을 권합니다.
- 格式可读性：형식 가독성: 짧은 문단, 독립된 대화, 불필요한 빈 줄 없음. 형식이 읽기를 방해하면 S3, 심각하게 혼란스러우면 S2.
- 剧情循环：줄거리 순환: 목표 → 장애물 → 행동 → 대가/반응 → 새로운 기대. 목표·장애물·반응이 없으면 보통 최소 S2.
- 高潮构建：절정 구성: 힘의 축적, 감정 낙차, 기대 충족을 확인합니다. 강한 반전은 축적 → 거짓 승리 → 붕괴 → 반전/충족을 사용할 수 있습니다. 밑작업이나 충족이 없으면 보통 S2/S3.
- 关系进展：관계 진전: 상호작용의 수위는 현재 관계 단계에 맞아야 합니다. 선을 넘는 친밀감, 갑작스러운 신뢰·적대는 모두 밑작업이 필요하며 없으면 영향에 따라 S1/S2.
- 伏笔状态：복선 상태: 추적 가능해야 합니다. 복선 밀도는 구조 위험 안내로만 사용하며 직접적인 이해 혼란을 일으키지 않는 한 S2+로 올리지 않습니다.

3단계 AI 문체 정리 대체 기준:
- 표현: 상투어, 요약 문장, 정돈된 문형이 기계적으로 되풀이되거나 같은 의미를 반복하는가? 단어 자체는 단서일 뿐이며 감정 직접 서술, 오류 교정 대비, 문체상 허용된 서술은 유지할 수 있습니다.
- 서술 비중: 핵심 대립·결정이 요약되거나 부차적인 절차가 지나치게 상세한가? 압축·확장 모두 인물 경험과 필요한 연결을 지켜야 합니다.
- 이야기: 행동의 이유는 무엇이며 해결 근거는 어디서 왔고 전후에 무엇이 바뀌었는가? 조용한 장면도 관계·인식 변화를 담을 수 있으며 갈등을 강요하지 않습니다.
- 처리 원칙: 원문 근거가 있어야 finding을 내고 읽기 경험의 손실, 최소 제안, 자료의 한계를 밝힙니다. 보고만 하고 수정하지 않습니다. 문장을 짧게 나누거나 행동·새 줄거리를 추가하는 방식을 기본값으로 삼지 않습니다.

플랫폼 대체 기준 요약(일반 기준에 추가):
- 판치에 장편: 강한 도입, 강한 갈등, 잦은 쾌감·감정적 반응, 낮은 이해 장벽.
- 치뎬 장편: 설정의 정합성, 성장 경로, 장기 기대, 세계관의 수용력.
- 단편: 도입 후킹, 밑작업 있는 반전, 감정적 충족, 정보 격차에 따른 전개.

---

## Phase 1: 검토 대상 수집

1. **검토 범위 결정**:
   - 사용자가 장·파일을 지정하면 해당 내용만 검토합니다.
   - 지정하지 않으면 git 저장소에서는 `git diff --name-only`의 본문·설정·개요 파일을 검토합니다. git 저장소가 아니면 장편은 `본문/` 아래 가장 최근 수정한 장, 단편은 `본문.md`를 검토합니다. 보고 첫머리에 검토 범위를 씁니다.
2. **범위 전달 전략**:
   - 파일 경로, 장 이름, 행 번호 범위를 reviewer에게 우선 전달합니다. 책 전체나 많은 장을 매 프롬프트에 통째로 복사하지 않습니다.
   - 단일 파일이나 짧은 구간은 300-1200자 핵심 발췌를 첨부할 수 있습니다.
   - 여러 장·권 전체·책 전체는 반드시 묶음별로 검토합니다. 장 또는 파일 묶음으로 나누어 각각 독립된 findings를 만들고 종합합니다. 나누기 전에 [references/batch-review.md](references/batch-review.md)를 완독합니다(묶음 사이 상태, 연속성, 순서 뒤바뀜 안내).
3. **근거 자료 읽기**: solo와 묶음별 검토에서는 직접 본문, 관련 설정, 인물 기록, 개요, `추적/문맥.md`, 복선 파일을 읽습니다. full/lean에서는 범위·플랫폼 결정과 묶음별 열린 항목에 필요한 파일만 읽고 나머지는 reviewer가 경로를 따라 직접 읽습니다. 자료가 부족하면 보고에 근거 부족으로 표시합니다.
4. **분량과 목표 플랫폼을 확인하고 평가 기준 불러오기**:
   - 일반 기준은 매번 불러옵니다. `story-review/references/quality-rubric.md`를 읽고 불가하면 내장 일반 웹소설 콘텐츠 기준을 사용합니다. 플랫폼 표는 일반 기준을 대체하지 않고 추가합니다.
   - 분량: 책 디렉터리에 `본문/` 또는 `설정/` 하위 디렉터리가 있으면 장편, `본문.md` 또는 `설정.md` 파일이 있으면 단편입니다(`/story`와 같은 라우팅 기준).
   - 플랫폼: 이번에 사용자가 지정한 값을 우선합니다. 다음으로 장편은 `설정/소재방향.md`, 단편은 `설정.md`의 `目标平台`(목표 플랫폼)를 읽습니다. `.active-book`은 책 디렉터리 위치 확인에만 쓰며 플랫폼 출처로 삼지 않습니다.
   - 아래 표대로 플랫폼 기준을 추가합니다. 파일을 읽을 수 없으면 내장 플랫폼 대체 요약을 사용합니다.

     | 분량 | 목표 플랫폼 | 추가할 플랫폼 표 |
     |---|---|---|
     | 장편 | 치뎬 | `story-review/references/rubrics/qidian.md` |
     | 장편 | 판치에 | `story-review/references/rubrics/fanqie.md` |
     | 장편 | 진장, 기타, 미정, 미기재 | 추가 안 함 |
     | 단편 | 즈후 옌옌(옌쉬안으로도 표기), 판치에, 치마오, 헤이옌, 훙궈, 미니프로그램, 미정, 미기재 | `story-review/references/rubrics/zhihu.md` |

   - 단편은 `설정.md`의 `平台基调`(플랫폼 기조)에 따라 형식, 따옴표, 도입문도 확인합니다.
   - 기술 비고 줄의 Rubric에는 추가한 플랫폼 표(`fanqie | qidian | zhihu`)를 쓰고 추가하지 않았으면 `generic`을 씁니다. 괄호 안에는 파일을 읽을 수 있으면 `file`, 내장 요약을 사용했으면 `embedded`를 씁니다.
5. **검토 기준 묶음 요약 작성**: 불러온 파일 내용 또는 내장 대체 요약을 5-12개 기준으로 압축합니다. 이후 solo와 하위 에이전트 모두 이 요약을 사용해야 합니다. 검토 프롬프트에는 줄거리 순환, 절정 구성, 관계 진전 판단을 각각 한 항목씩 유지하고 1-3장 검토에는 도입 참신함을 추가합니다. 문장 길이 기준도 하나 반드시 유지합니다. 서술은 기본적으로 쉼표로 연결한 긴 문장이며 잘게 끊긴 문장과 전보체는 AI 말투와 같은 수준으로 처리합니다. “짧다”는 이유로 통과시키지 않고 이 책의 문체에 별도 규정이 있으면 그 문체를 따릅니다.
6. **결정론적 사전 검사(보고만 하고 수정하지 않음)**: 검토 범위에 로컬 본문 파일 경로가 있으면 이 스킬의 스크립트를 실행합니다.
   ```bash
   node scripts/normalize-punctuation.js --check <正文文件...>
   node scripts/check-ai-patterns.js --check --fail-on=blocking <正文文件...>
   node scripts/check-degeneration.js --check <正文文件...>
   ```
   - `ellipsis`, `double-hyphen`, `markdown-divider` 결과를 `format` findings로 보고에 합칩니다. `em-dash` 대시는 `check-ai-patterns.js`의 의미 기반 수정 제안만 사용합니다(다음 항목 참조). `normalize-punctuation.js`가 같은 위치에 보고한 `em-dash`는 합칠 때 중복으로 버려 같은 곳에 “기계적 치환”과 “기능에 따른 수정”이라는 상충하는 finding이 생기지 않게 합니다. 전체를 마침표로 끊거나 부호를 무작위로 쌓았는지도 사람이 확인합니다. 스크립트는 어조 판단을 대신하지 않습니다.
   - `check-ai-patterns.js`의 blocking / advisory는 모두 우선 `prose` 후보로 삼고 `style_resolution`, 원문의 기능, 3단계 방법으로 하나씩 재검토합니다. 구체적인 읽기 경험 손실을 확인한 뒤 아래 심각도 정의로 분류합니다. 기능적인 오류 교정, 서술, 멈춤은 유지하며 스크립트 등급을 곧바로 필수 수정 finding으로 바꾸지 않습니다. 탐지기 수정안은 참고일 뿐 문체와 사실의 경계를 덮어쓰지 않습니다. 전체 의미 검토는 `expression.md`, `narrative-focus.md`, `story-logic.md`를 참고하고 문제·제안만 보고하며 수정하지 않습니다.
   - `check-degeneration.js`는 모델 퇴화(글자 단위 반복/잘림/플레이스홀더/프로젝트 내부 용어 노출)를 보고하며 각 항목에 `severity: blocking|advisory`가 있습니다. blocking(반복/잘림/tier1 내부 용어)은 S1/S2 `prose` findings로 삼고 수정 제안은 “문장 수정이 아니라 해당 문단 재생성”입니다. advisory(tier2 장/중의적 단어)는 S3입니다.
   - 사전 검사 스크립트 3개는 읽기 전용입니다. `story-review`는 **본문·설정·개요 파일을 수정하지 않습니다.** 본문 자동 수정이 필요하면 `/story-deslop`을 권합니다. full / lean에서 `추적/` 수정은 아래 “추적 파일 관리”에 한해 허용합니다. 묶음별 검토는 모든 모드에서 batch-review.md에 따라 **.story-review/state.md**를 쓸 수 있습니다. solo는 이 상태 파일 외 프로젝트 내용을 쓰지 않습니다.
   - 기본값은 `--quote-mode keep`이며 즈후 옌옌 단편의 `「」`를 문제로 보지 않습니다. 프로젝트가 따옴표 스타일을 명시한 경우에만 해당 변환 제안을 확인합니다.

---

## 통일된 Findings Schema(모든 모드 필수)

solo를 포함한 모든 reviewer는 먼저 공통 구조로 문제를 정리하고 Phase 4 또는 solo 템플릿에 따라 작가용으로 다시 씁니다. 내부 필드는 병합·정렬용이며 작가 보고에 그대로 붙이지 않습니다. `location`은 도구의 읽기 결과에 표시된 원본 파일 행 번호를 사용해야 합니다. 빈 줄을 지운 뒤 다시 번호를 매기지 않습니다.

`consistency` / `factual` / `causal` / `rule_boundary` finding의 `fix`에는 사실을 통일할 방향만 씁니다(예: “왼팔의 오래된 부상으로 통일하고 본문·설정의 충돌 지점도 반영”, “A/B 시간선 중 하나를 근거로 결정해야 함”). 문학적 창작 제안을 쓰지 않습니다.

```yaml
- severity: S1 | S2 | S3 | S4
  category: structure | character | prose | consistency | platform | factual | format | causal | rule_boundary
  location: 파일경로:행번호 또는 장/문단 설명
  evidence: "원문 인용 또는 구체적인 근거"
  issue: "문제 설명"
  fix: "실행 가능한 수정 제안"
```

심각도 정의: S1–S4 등급은 장편 집필·탐지기와 같습니다. 검토 보고의 소제목은 등급에 따라 S1·S2는 “반드시 수정”, S3는 “수정 권장”, S4는 “수정하지 않아도 됨”으로 씁니다.
- **S1**: 중심 줄거리, 인물 동기, 세계 규칙 또는 독자 신뢰를 무너뜨리므로 우선 수정해야 합니다.
- **S2**: 장의 효과, 독자 유지, 리듬, 인물의 설득력에 뚜렷한 영향을 주므로 이번에 수정해야 합니다.
- **S3**: 표현, 가벼운 형식, 국소적인 리듬 등의 부분 품질 문제이며 수정 일정을 잡을 수 있습니다.
- **S4**: 제안 또는 문체 미세 조정이며 게시를 막지 않습니다.

---

## Phase 2: 에이전트 병렬 생성(full/lean 모드)

Phase 0 이후 실제 모드가 여전히 full/lean이면 [references/agent-prompts.md](references/agent-prompts.md)를 읽고 호출 규칙과 프롬프트 4개에 따라 병렬 생성합니다. 종합 판단과 보고 템플릿도 그 파일에 있습니다. 없는 에이전트는 생성하지 않습니다. 각 에이전트는 부모 대화 문맥을 상속하지 않으므로 프롬프트에 경로, 범위, 공통 Findings Schema를 자체적으로 포함합니다.

## Phase 3: 종합 판단(full / lean 모드)

reviewer 결과를 모두 받은 뒤 agent-prompts.md의 “综合裁决”(종합 판단)에 따라 병합하고 중복을 없애며 의견 차이를 제시합니다.

## Phase 4: 보고 출력(full / lean 모드)

실제 모드가 full/lean일 때는 agent-prompts.md의 보고 템플릿을 사용합니다. solo로 전환했다면 solo.md 템플릿을 사용합니다.

---

## solo 모드

전환했거나 solo를 지정했으면 [references/solo.md](references/solo.md)를 읽고 해당 절차와 출력 형식을 따릅니다.

## 추적 파일 관리

`추적/_tracking-state.json`이 있는 장편 프로젝트이며 실제 모드가 full/lean일 때, 마무리 단계에서 [references/review-tracking.md](references/review-tracking.md)를 읽고 추적 자료를 수정합니다. solo는 `추적/`를 바꾸지 않으며 solo.md의 5번째 단계에 따라 보고에 씁니다.

## 다음 절차 연결

**파이프라인:** 공통
**위치:** 검토(집필 후)

| 상황 | 이동할 스킬 | 명령 |
|---|---|---|
| 발견한 문제를 수정하려면 | story-long-write / story-short-write | 해당 집필 스킬로 돌아가 수정 |
| AI 문체 정리가 필요하면 | story-deslop | `/story-deslop` |
