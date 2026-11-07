---
name: story-setup
version: 1.3.6
description: "웹소설 집필 도구 모음의 기반 환경을 배포하고 검사합니다. Claude Code / OpenCode / Codex / Google Antigravity / ZCode / OpenClaw / Reasonix용 내장 어댑터를 제공하며 Web AI / 일반 Agent는 skills + AGENTS.md 파일 모드를 사용할 수 있습니다. 호출: /story-setup, $story-setup, 집필 준비, 환경 구성해 줘, 집필 프로젝트 설정, 집필 환경 검사."
metadata: {"openclaw":{"source":"https://github.com/zenstory-ai/oh-story-claudecode"}}
---
# story-setup: 웹소설 집필 도구 모음 기반 환경 배포

사용자 프로젝트 디렉터리에 웹소설 집필 도구 모음을 배포합니다. 지원 CLI는 전용 hooks/agents/config를 사용하고 NarraFork, Web AI, 사용자 정의 Agent 등은 일반 파일 모드를 사용합니다.

**사용자 설정을 보존합니다. 관리 대상 파일은 목록에 따라 갱신하고 공동 관리 파일은 관리 블록으로 병합합니다.**

최초 배포 순서는 현재 호스트 판단 → 프로젝트 루트 확인 → 호스트별 배포 → 검수 → 다음 단계 안내입니다. 이 파일은 공통 절차를 다룹니다. 호스트별 배포 목록, 알고리즘, 검증, 보고 안내는 Phase 2의 해당 파일에 있으며 **이번 대상 호스트의 파일만 읽습니다.**

## 모드 선택

- 인수가 `check`이거나 사용자가 배포 검사, 환경 진단, 에이전트 사용 불가 원인 조사만 요청하면 [references/diagnostics.md](references/diagnostics.md)를 완독하고 해당 절차로 검사·보고만 합니다. 아래 배포 절차로 들어가지 않습니다.
- 설치·업데이트·복구 요청이면 아래 배포 절차를 수행합니다. 검사 후 이미 명시적으로 허가받은 복구는 이 파일과 호스트 배포 파일의 배포·병합 규칙을 따릅니다.

---

## Phase 1: 호스트와 프로젝트 판단

기존 작품에 `设定/`, `大纲/`, `正文/`, `追踪/`가 있으면 한국어 폴더를 나란히 만들지 않습니다. 먼저 [한국어 경로 전환](references/korean-project-paths.md)을 읽고 새 목적지로 변환한 뒤 그 폴더에서 배포·집필을 계속합니다.

**참고 디렉터리부터 자체 확인**: 실행 중인 이 `SKILL.md`의 디렉터리를 기준으로 같은 위치의 `references/` 하위 디렉터리를 나열합니다. 다음 9개가 **모두 있으며 비어 있지 않은지** 확인합니다: `agent-references`, `templates`, `opencode`, `codex`, `antigravity`, `zcode`, `openclaw`, `reasonix`, `generic`. 같은 위치의 `references/deploy-*.md`(호스트 배포 파일 8개), `scripts/merge-claude-settings.py`, `scripts/merge-codex-hooks.py`, `scripts/merge-antigravity-hooks.py`, `scripts/generate-antigravity-agents.mjs`, `scripts/deploy-antigravity-skills.py`, `scripts/merge-project-instructions.py`, `scripts/copy-path-safety.py`도 있어야 합니다. 호스트 배포 단계, Claude/Codex/Antigravity hooks 병합, Antigravity Skills 실제 복사·에이전트 생성, 프로젝트 지침 병합, 재귀 복사 안전 검사가 이 파일들에 의존합니다. 하나라도 없으면 스킬 패키지가 불완전한 것이므로 **즉시 중단하고 어떤 배포 파일도 쓰지 않습니다.** 보고에 “디렉터리 누락”, “빈 디렉터리”, “스크립트·배포 파일 누락”을 구분하고 다음 복구 지침을 줍니다. “story-setup 참고 자료 패키지가 불완전하며 {경로}가 없습니다. 설치 방법에 맞춰 oh-story-claudecode를 다시 설치하세요. 명령줄로 설치했다면 `npx skills add zenstory-ai/oh-story-claudecode -y -g`를 다시 실행하고 marketplace / Plugin Management에서 설치했다면 해당 패널에서 재설치한 뒤 /story-setup을 실행하세요.”

> 판단 기준은 `SKILL.md`의 유무입니다. 실행 중인 `SKILL.md`와 같은 위치의 `references/`만 봅니다. 프로젝트의 `.claude/skills/story-setup/`, `.codex/skills/story-setup/`, OpenCode의 `skills/story-setup/`에는 `references/agent-references/`만 있고 `SKILL.md`는 없으므로 실행 디렉터리가 아니며 검사 대상으로 삼지 않습니다. Antigravity / ZCode / OpenClaw / Reasonix / generic 프로젝트 사본은 `SKILL.md`를 포함한 전체 스킬 복사본이므로 하위 디렉터리 9개가 원래 모두 있어야 하며 정상적으로 검사합니다.

1. 현재 디렉터리가 이미 배포됐는지 확인합니다(`.story-deployed` 존재).
   - `agents_version` 누락·정수 아님·`38` 미만 → 업데이트 필요로 표시하고 이번 배포를 계속합니다.
   - `agents_version: 38` → AskUserQuestion으로 재배포 여부를 확인합니다. 재배포는 **현재 로컬 스킬 패키지**로 프로젝트 파일만 갱신한다고 안내합니다. 스킬 자체의 새 버전을 받으려면 먼저 oh-story-claudecode를 업데이트(`npx skills add` 또는 marketplace)하고 돌아와 재실행해야 합니다.
   - `agents_version`이 `38`보다 큼 → 현재 story-setup이 프로젝트 배포보다 이전 버전입니다. 다운그레이드 덮어쓰기를 막기 위해 중단하고 oh-story-claudecode부터 업데이트하라고 안내합니다. 배포 파일을 쓰지 않습니다.
   - `target_cli`도 읽습니다. **기존 배포 프로젝트는 sentinel의 값을 기준으로 합니다.** 비어 있지 않으면 해당 호스트들을 그대로 재배포하고 작가에게 다시 선택시키지 않습니다(쉼표로 구분한 여러 호스트 조합 유지). 4번째 단계에서 현재 호스트는 계속 판단합니다. 현재 호스트가 판별됐는데 목록에 없으면(작가가 소프트웨어를 바꿈) AskUserQuestion으로 “이 폴더는 전에 {배포된 호스트}용으로 설치했습니다. 지금 사용 중인 {현재 호스트}도 함께 설치할까요?”라고 묻습니다. 선택지는 “함께 설치(권장)”, “기존 것만 업데이트”이며 전자면 `target_cli`에 추가합니다. 판별 불가이면 묻지 않습니다. 필드가 없거나 비었을 때만 4-6번째 단계를 따릅니다. 사용자가 대상 추가·삭제를 명시적으로 요청하면 AskUserQuestion으로 기존 값을 바탕으로 바꾸고 sentinel에 기록합니다.
   - `target_cli`에 opencode는 없지만 `.opencode/plugins/story-hooks.ts` 또는 `.opencode/agents/`가 있으면(다중 호스트 배포 때 OpenCode가 버전 조건으로 차단된 경우) AskUserQuestion으로 OpenCode를 다시 추가할지 묻습니다. 추가를 선택하면 [references/deploy-opencode.md](references/deploy-opencode.md)의 “배포 선행 조건”부터 통과한 뒤 `target_cli`에 기록합니다.
2. 책 제목 디렉터리가 있는지 확인합니다(`추적/` 하위 디렉터리 포함 또는 사용자 정의 구조).
   - 있으면 장편 프로젝트로 인식하고 현재 프로젝트 정보를 표시합니다.
   - 없으면 새 프로젝트 또는 단편 프로젝트로 인식합니다.
3. `.active-book`이 있으면 현재 활성 책을 표시하고 없으면 건너뜁니다.
4. **현재 호스트 판단(판별 가능하면 작가에게 묻지 않음)**. 다음 순서에서 처음 확정 가능한 근거를 사용합니다.
   - 자신의 실행 환경: 시스템 프롬프트, 사용 가능한 도구 이름, 스킬 호출 문법이 Claude Code, Codex, OpenCode, Google Antigravity(명령줄 `agy` 포함), ZCode, OpenClaw, Reasonix 중 어디인지 드러냄.
   - 실행 중인 `SKILL.md`의 설치 위치에 호스트 전용 디렉터리가 있음(예: `.claude/`, `.codex/`, `.zcode/`, `.gemini/`, `.openclaw/`, `.opencode/`).
   - 판별 불가(웹 AI, 자체 Agent, 위 신호가 서로 충돌 등) → 5번째 단계의 프로젝트 표식은 후보로만 보고 6번째 단계에서 작가에게 질문합니다.
5. 프로젝트에 이미 있는 호스트 표식을 확인합니다.
   - `.claude/` 또는 `CLAUDE.md` → `target_cli = claude-code`
   - `opencode.json`, `opencode.jsonc`, `.opencode/` → `target_cli = opencode`
   - `.codex/`, `.codex/config.toml`, `.codex/agents/`, `.codex/hooks.json`, `AGENTS.md`의 Codex 절 → `target_cli = codex`
   - `.agents/hooks.json`, `.agents/agents/`, `.agents/rules/oh-story.md`의 Antigravity 표식 → `target_cli = antigravity`
   - `.zcode/`, `.zcode/config.json`, `zcode.json`, `.zcode/skills/`, `.zcode/commands/`, `AGENTS.md`의 ZCode 절 → `target_cli = zcode`
   - `openclaw.json`, `.openclaw/`, `AGENTS.md`의 OpenClaw 절(제목에 `网文写作工具集（OpenClaw）` 포함) → `target_cli = openclaw`
   - `.reasonix/`, `reasonix-plugin.json`, `REASONIX.md`, `AGENTS.md`의 Reasonix 절(제목에 `网文写作工具集（Reasonix）` 포함) → `target_cli = reasonix`
   - `AGENTS.md`의 일반 절(제목에 `网文写作工具集（通用 Agent / Web AI）` 포함) → `target_cli = generic`
   - `CLAUDE.md` / `AGENTS.md`의 `<!-- oh-story:{宿主} 开始` 관리 블록 → `target_cli`에 해당 호스트 포함

   > 마지막 세 종류는 호스트별로 **서로 배타적인** 표식만 인정합니다. `skills/*/SKILL.md`의 `metadata.openclaw`는 OpenClaw 신호가 아닙니다(스킬 14개 모두 포함하며 skills-only 배포 경로 3개가 만든 `skills/`도 같음). `.agents/skills/`도 Antigravity, Codex, Reasonix가 공유하므로 단독 근거로 삼지 않습니다.
6. `target_cli`를 결정합니다.
   - 4번째 단계에서 현재 호스트를 확정했으면 그 호스트가 `target_cli`입니다. 프로젝트에 다른 호스트 표식도 있으면 AskUserQuestion으로 “이 폴더에는 전에 {다른 호스트}용 집필 도구도 설치했습니다. 이번에 함께 업데이트할까요?”라고 쉽게 묻습니다. 선택지는 “{현재 호스트}만 설치(권장)”, “함께 업데이트”입니다. 작가가 처음부터 여러 호스트 설치를 요청했다면 그대로 따릅니다.
   - 판별할 수 없고 프로젝트 표식이 정확히 한 호스트이면 AskUserQuestion으로 “지난번에는 {호스트}용으로 설치했습니다. 이번에도 같은가요?”라고 묻습니다. 맞으면 사용하고 아니면 다음 항목처럼 묻습니다.
   - 판별 불가인 나머지 경우는 AskUserQuestion으로 “지금 어떤 소프트웨어에서 저와 대화하고 있나요?”라고 묻습니다. 제품명과 짧은 설명을 선택지로 줍니다: Claude Code(Anthropic 명령줄/데스크톱), Codex(OpenAI 명령줄), OpenCode, Google Antigravity(명령줄 agy 포함), ZCode, OpenClaw, Reasonix(DeepSeek 명령줄), 웹 AI 또는 기타 도구(NarraFork, 자체 Agent 등), 여러 도구. 질문 도구에 모두 넣을 수 없으면 프로젝트 표식에 있던 제품을 앞에 두고 나머지는 “기타”에 이름을 직접 쓰도록 합니다.
   - 답을 `target_cli`로 변환합니다. Claude Code → `claude-code`, 웹 AI·기타 → `generic`, 나머지는 소문자 제품명입니다. 여러 호스트는 `claude-code,opencode,codex,antigravity,zcode,openclaw,reasonix,generic` 중 선택한 값들입니다.
7. **프로젝트 루트 확인(대개 질문 불필요)**: 프로젝트 루트는 현재 작업 디렉터리입니다. 현재 위치가 사용자 홈, 디스크 루트, 시스템 디렉터리 또는 이 스킬 패키지 자체의 설치·소스 디렉터리일 때만 “집필 도구를 어느 폴더에 설치할까요? 보통 원고가 있는 폴더입니다”라고 쉽게 묻습니다. 그 외에는 바로 배포하고 설치 보고의 “배포 내역”에 위치를 씁니다.

## Phase 2: 기반 환경 배포

Phase 2는 멱등적입니다. 복사·쓰기·호스트별 병합을 반복해도 결과가 같습니다. 관리 디렉터리에서는 oh-story 자체 스킬 14개, 도우미 7개, hook·규칙 파일만 덮어쓰고 같은 디렉터리의 작가 파일은 보존합니다. 원고, 설정, 개요, 추적 자료, `.active-book`을 덮어쓰지 않습니다. 도구·권한·네트워크 문제로 중단되면 처음부터 다시 실행하면 되며 미완성 결과를 별도로 정리하지 않습니다. `create only if absent`인 사용자 상태 파일(목록의 Owner class 참조)은 덮어쓰지 않습니다.

**두 열의 기준 디렉터리는 다릅니다.** `Source path`는 패키지 내부 출처이며 story-setup 안의 경로는 현재 `SKILL.md`의 디렉터리로 찾습니다. `Target path`는 사용자 프로젝트 루트 기준입니다. 각 행을 실행하기 전과 각 호스트 배포 알고리즘의 재귀 복사 단계 전에 와일드카드를 개별 원본·대상으로 구체화하고 이 `SKILL.md`와 같은 위치의 `scripts/copy-path-safety.py`로 검사합니다. 이 스크립트는 `Path.resolve` / `realpath` 의미에 따라 기존 symlink를 따라가며 양쪽이 모두 있으면 `samefile`로 파일 시스템 객체를 확인합니다. **절대 경로 변환이나 문자열 비교만으로는 검사가 완료되지 않습니다.** JSON 결과에서 `status: same`이면 no-op이며 복사를 금지합니다. `copy_allowed: true`일 때만 복사할 수 있습니다. `source_missing`, `unsafe_target_within_source`, `filesystem_identity_error`이면 해당 단계를 반드시 중단하고 보고합니다. 스크립트를 실행할 수 없으면 현재 환경의 파일 시스템 API로 완전히 같은 canonical realpath, same-object, target-descendant 검사를 수행해야 합니다. 확인할 수 없으면 중단하며 복사를 시도해서는 안 됩니다. OpenClaw / Reasonix / generic 프로젝트 사본은 전체 스킬 복사본이므로 재실행할 때 프로젝트 안의 사본을 실행합니다. Reasonix / Codex는 `.agents/skills → ../skills` symlink로 불러올 수도 있습니다. 경로 문자열이 달라도 같은 디렉터리일 수 있으며 문자 그대로 복사하면 자기 안에 디렉터리를 중첩하여 디스크를 가득 채울 수 있습니다.

**배포 전 자기 중첩 잔여물 정리**: `{.claude,.codex,.zcode}/skills/story-setup/references/agent-references/` 및 프로젝트 루트 `skills/story-setup/references/agent-references/` 안에 불필요한 `agent-references/` 층이 더 있으면(여러 층일 수 있음) 그 부분 전체를 삭제합니다. `skills/story-setup/skills/`도 삭제한 뒤 배포하며 설치 보고에 삭제 경로를 나열합니다.

### Step 1: 호스트별 배포

`target_cli`의 각 호스트에 대해 해당 배포 파일을 **완독**하고 기계적으로 검사 가능한 배포 목록과 알고리즘을 순서대로 수행합니다. 다른 호스트의 파일은 읽지 않습니다.

| `target_cli` | 배포 파일 |
|---|---|
| `claude-code` | [references/deploy-claude-code.md](references/deploy-claude-code.md) |
| `opencode` | [references/deploy-opencode.md](references/deploy-opencode.md)(“배포 선행 조건”의 버전 조건부터 통과) |
| `codex` | [references/deploy-codex.md](references/deploy-codex.md) |
| `antigravity` | [references/deploy-antigravity.md](references/deploy-antigravity.md) |
| `zcode` | [references/deploy-zcode.md](references/deploy-zcode.md) |
| `openclaw` | [references/deploy-openclaw.md](references/deploy-openclaw.md) |
| `reasonix` | [references/deploy-reasonix.md](references/deploy-reasonix.md) |
| `generic` | [references/deploy-generic.md](references/deploy-generic.md) |

여러 호스트가 루트 `AGENTS.md`를 공유하되 각각 관리 블록 하나를 차지합니다(아래 “프로젝트 지침 병합” 참조). 어느 호스트가 자체 선행 조건으로 차단되면(OpenCode 버전 조건, Antigravity의 Node 없음 등) 해당 배포 파일대로 처리하고 나머지 호스트는 정상 배포합니다.

### Step 2：创建部署标记

> **한국어 안내:** 배포 표식 생성. 이 제목은 배포 계약 검사에서 참조합니다.

- 이번에 성공한 대상만 `.story-deployed`(sentinel file)를 생성·갱신합니다. 모든 대상이 중단되면 기존 표식을 보존하고 새 표식을 만들지 않습니다.
- 写入以下字段 — 다음 필드를 씁니다(YAML `key: value` 형식, hook은 `references/templates/hooks/lib/sentinel.sh`로 읽음).
  ```
  deployed_at: <date -u +"%Y-%m-%dT%H:%M:%SZ">
  agents_version: 38
  setup_skill_version: 1.3.6
  target_cli: claude-code（또는 opencode, codex, antigravity, zcode, openclaw, reasonix, generic 및 임의 조합）
  resolver_strategy: project-local-skill-reference
  references_dir: .claude/skills/story-setup/references/agent-references（Codex는 .codex/skills/...; Antigravity는 .agents/skills/...; ZCode는 .zcode/skills/...; OpenCode / OpenClaw / Reasonix / generic은 skills/...; 여러 호스트는 쉼표로 구분）
  ```
- session-start.sh와 집필 스킬이 이 파일로 배포 상태를 확인하여 반복 안내를 방지합니다.
- 호스트 배포 파일의 “배포 표식 보충”에서 요구하는 추가 표식도 만듭니다(예: Claude Code 재시작 확인 표식).

## Phase 3: 설치 검증

검사 전용 모드는 1–2번만 재사용하고 3번은 건너뜁니다. 그 안에서 hook 실제 실행이나 fixture 쓰기를 요구하는 하위 항목은 정적 검사(파일 존재, 문법 유효성, 등록 항목 완비)로만 바꿉니다. 프로젝트에 쓰는 hook을 실행하거나 배포 표식을 만들지 않습니다.

1. `target_cli` 각 호스트의 배포 파일에서 “검증” 절을 수행합니다.
2. 배포 표식을 검증합니다.
   - `.story-deployed`가 있고 필드가 완비됐으며 버전이 Step 2 필드 블록과 같은지 확인합니다.
3. 설치 보고를 출력합니다. 프로그래밍을 모르는 작가를 대상으로 다음 순서로 씁니다.
   - **“지금 할 수 있는 일”부터 작성**: 이번 배포 후 실제 가능한 일을 집필 언어로 나열합니다(예: “새 책 시작·이어 쓰기: /story-long-write”, “벤치마크 작품 분석 가능”). 호스트 제약도 사실대로 풀어 설명합니다(예: “이 도구에서는 분업 도우미 없이 제가 혼자 원고를 검토합니다”).
   - **다음은 “추가로 필요한 일”**: “새 대화 시작”, “Codex에서 /hooks를 열어 oh-story 항목 신뢰”, “Node 먼저 설치”처럼 따라 할 수 있게 씁니다. 없으면 “추가 조치 없음”이라고 씁니다. 이 두 부분에는 스크립트명, 필드명, 상태명, 파일 경로를 넣지 않습니다. 호스트 배포 파일의 “설치 보고 필수 안내”를 먼저 쉬운 말로 이 두 부분에 반영합니다.
   - **끝에 짧은 “배포 내역”**: 설치 폴더, 배포 파일, 병합 설정, 삭제한 잔여 경로, 호스트 배포 파일에서 요구하는 요약(OpenCode 모델 설정 등), 기술적 이유를 보고 마지막에 둡니다.

---

## 템플릿 플레이스홀더

`{项目名}`만 치환합니다. 작가가 준 책 제목·프로젝트명을 사용하고 없으면 현재 디렉터리명을 쓰며 중괄호를 제거합니다. 나머지 중괄호 표기(예: `{书名}/본문/`)는 “임의의 책 디렉터리”를 의미하므로 그대로 유지합니다.

## 프로젝트 지침 병합(CLAUDE.md / AGENTS.md)

각 호스트는 프로젝트 지침 파일에서 `<!-- oh-story:{宿主} 开始 … -->`부터 `<!-- oh-story:{宿主} 结束 -->`까지 관리 블록 하나를 차지합니다. 블록 안에는 렌더링한 템플릿을 둡니다. Claude Code는 `CLAUDE.md`에 쓰고 나머지는 루트 `AGENTS.md`를 공유합니다. `python3` → `python` → `py` 순으로 사용 가능한 Python을 찾아 `PYBIN`으로 두고 실행합니다.

```text
"$PYBIN" "{story-setup skill目录}/scripts/merge-project-instructions.py" --host {宿主} --template {该宿主模板} --existing {项目指令文件} --output {项目指令文件} --project-name {项目名}
```

규칙(스크립트 실행 불가 시 같은 규칙으로 수동 병합):
1. 파일이 없거나 비었으면 이 블록만 씁니다.
2. 이 호스트의 블록이 있으면 전체 블록을 교체합니다. 블록 밖 텍스트와 다른 호스트 블록은 한 글자도 바꾸지 않습니다.
3. 이 호스트 블록은 없지만 블록 밖에 이전 버전 `网文写作工具集` 제목이 있으면(이전 배포), 이 호스트의 이전 제목·소개와 템플릿과 이름이 같은 절을 삭제합니다. 폐기된 `协作规则`도 포함합니다. `Skill 路由表`, `文件结构`, `写作约束`는 내용에 oh-story 흔적이 있을 때만 삭제합니다. 원래 위치에 이 블록을 넣고 작가 자신의 절은 블록 밖에 유지합니다. 다른 호스트 블록이 이미 있고 블록 밖에 이전 제목이 없으면 이 호스트 고유 절(예: `Codex 项目约定`)만 삭제합니다.
4. 위 경우에 해당하지 않으면 파일 끝에 이 블록을 추가합니다.

스크립트가 출력한 이전 절 이름을 설치 보고의 “배포 내역”에 씁니다.

---

## 참고 자료

| 파일 | 용도 |
|------|------|
| references/deploy-*.md | 호스트 배포 파일 8개: 배포 목록, 알고리즘, 검증, 설치 보고 안내. Phase 2 Step 1에 따라 대상 호스트만 읽음 |
| [references/diagnostics.md](references/diagnostics.md) | 검사 전용 모드 |
| UPGRADING.md | 작가용 안내: 버전별 재실행 필요 여부와 이전 데이터 이전 대상 |

---

## 다음 절차 연결

**파이프라인:** 배포
**위치:** 초기화(맨 먼저)

| 상황 | 이동할 스킬 | 명령 |
|---|---|---|
| 배포 후 집필 시작 | story-long-write / story-short-write | `/story-long-write` 또는 `/story-short-write` |
| 기존 소설을 가져와 분석 | story-import | `/story-import` |
| 브라우저 로그인 상태 필요(순위 조사/분석 원문 확보) | browser-cdp | `/browser-cdp`; generic은 플랫폼의 로컬 스크립트·브라우저 제어 허용 필요 |

호스트별 호출 문법: Claude `/이름`, Codex/ZCode `$이름`, Antigravity는 `/skills`로 탐색하거나 이름 직접 지정, OpenClaw `/skill 이름`, Reasonix / generic은 스킬 이름 직접 지정.
