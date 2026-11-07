# 호스트별 배포와 설치 문제 해결

[영문판의 한국어 번역](hosts_EN.md)

Oh Story는 코딩 에이전트 호스트 7종의 배포 어댑터와 웹 AI·기타 에이전트용 일반 파일 방식을 지원합니다. 이 문서는 배포 조건, 알려진 한계, 설치 문제 해결을 설명합니다. 일상 사용에는 README의 [설치](../README.md#安装) 절만 읽어도 됩니다.

## 설치 문제 해결: Windows 오류, 환경 검사, 마켓플레이스 경로

Windows에서 `ENOENT ... mkdir` 오류가 나도 마지막에 `Done!`이 표시되는 경우가 있습니다. 일부 스킬이 완전히 설치되지 않았다는 뜻입니다. story-setup 참조 묶음의 하위 디렉터리가 통째로 없으면 `/story-setup`이 불완전한 참조 묶음이라고 알리지만 다른 종류의 누락은 알리지 않을 수 있습니다. 오류 표시 여부와 관계없이 같은 설치 명령을 다시 실행하면 복구됩니다.

설치 환경을 진단하려면 에이전트에 “story-setup으로 집필 환경을 검사해줘”라고 요청하거나 스킬에 `check` 인자를 전달합니다. 대상 CLI의 배포 목록을 확인하고 처리 방법을 안내하며 검사만으로 프로젝트를 수정하지 않습니다. 복구는 기존 설정 흐름을 따릅니다.

이 독립 `npx skills` 설치 방식은 Claude Code·ZCode 마켓플레이스를 거치지 않으므로 아래 플러그인 식별자 변경의 영향을 받지 않습니다.

## Claude Code

마켓플레이스 이름은 `oh-story-skills`로 유지하고 이제 단일 `oh-story` 번들만 제공합니다. Claude Code가 저장소 루트에서 14개 스킬을 자동 탐색합니다.

```bash
claude plugin marketplace add https://github.com/zenstory-ai/oh-story-claudecode
claude plugin install oh-story@oh-story-skills
```

설치 후 `/oh-story:story-setup`, `/oh-story:story dashboard` 등을 사용합니다. 기존 사용자는 [이전 안내](../skills/story-setup/UPGRADING.md#插件打包身份迁移v079-同版本修复)를 따릅니다. 식별자 이전은 v0.7.9의 같은 버전 수정에서 시작됐으며, 이전 플러그인 식별자를 사용한다면 직접 마켓플레이스를 새로 고치고 재설치해야 합니다. 명령은 [Claude Code 플러그인 참조](https://code.claude.com/docs/en/plugins-reference)를 확인하세요.

## Antigravity

`/skills`나 자연어로 `story-setup`을 실행하면 현재 호스트(`target_cli=antigravity`)를 자동 판별하고 불명확할 때만 질문합니다. 현재 집필 프로젝트에서 알려진 `.agents/skills/` 디렉터리 14개, `.agents/agents/agent-name/agent.md` 정의 7개(`agent-name`은 실제 이름), `.agents/rules/oh-story.md`, `.agents/hooks/` 실행 파일 2개, `.agents/hooks.json`의 관리 대상 `oh-story` 그룹만 생성·갱신합니다. 그 밖의 사용자 스킬·에이전트·규칙·훅·훅 그룹은 보존하고 배포기는 `~/.gemini/`에 쓰지 않습니다. 프로젝트 스킬은 실제 디렉터리를 사용합니다. `.agents/skills`가 이미 심볼릭 링크라면 Git 변경 영향을 설명하고 명시적인 이전 동의를 받아야 하며, 동의 없이 링크를 따라 쓰지 않습니다. 훅은 PATH의 `node`가 필요합니다. 배포 후 새 대화를 열고 IDE와 대화형 `agy`를 각각 시험합니다. 명령줄 집필은 프로젝트 디렉터리에서 대화형 `agy`를 실행하고 `/skills`, `/agents`, `/hooks`가 oh-story를 발견한 뒤 작업을 요청합니다. **출력 모드 `agy -p`에는 반드시 `--add-dir "$PWD"`를 전달합니다.** agy 1.2.10 실측에서 이 옵션을 주면 작업 공간 `.agents/`의 스킬 14개·에이전트 7개·훅을 읽지만, 빼면 아무것도 읽지 않아 스킬이 대체 경로로 실행되고 일반 모델 출력이 `~/.gemini/antigravity-cli/scratch/`에 저장될 수 있었습니다. 시험 후 임시 디렉터리에 뜻하지 않은 소설 산출물이 없는지 확인하세요.

## Codex

저장소에서 직접 사용할 때 Codex는 `skills/`를 가리키는 심볼릭 링크인 `$REPO_ROOT/.agents/skills`를 탐색해 14개 스킬을 찾습니다. `$story`, `$story-setup`, `/skills`로 호출합니다. Windows에서는 Git의 `core.symlinks=true`가 필요합니다. 심볼릭 링크가 유효하지 않으면 아래 `$story-setup` 배포 방식을 사용합니다.

집필 프로젝트에서 `$story-setup`을 실행하면 `.codex/agents/*.toml`, `.codex/hooks.json`, `.codex/hooks/{story_codex_hook.py,run-story-hook.sh,run-story-hook.cmd}`, `.codex/skills/story-setup/references/agent-references/`를 작성합니다. 프로젝트 `.codex/` 설정 계층을 신뢰하고 `/hooks`에서 훅을 검토·신뢰한 뒤 새 Codex 세션을 열어 사용자 정의 에이전트를 로드합니다. **`/hooks`에서 신뢰하기 전에는 본문 작성 전 개요 보호기를 포함한 훅을 Codex가 조용히 건너뛰며 오류나 알림이 없습니다.** 자동화의 `codex exec`에는 `--dangerously-bypass-hook-trust`를 전달할 수 있습니다.

## ZCode

플러그인 관리에서 이 저장소를 추가하고 `oh-story`를 설치하면 14개 스킬·명령을 사용할 수 있습니다. 마켓플레이스는 루트 카탈로그의 `oh-story-zcode` 또는 Claude 카탈로그의 `oh-story-skills`로 표시될 수 있으며 내용이 같으므로 하나를 선택합니다. 여러 항목을 설치한 구버전은 [이전 안내](../skills/story-setup/UPGRADING.md#插件打包身份迁移v079-同版本修复)를 따릅니다. `$story-setup`에서 `target_cli=zcode`를 선택하면 `.zcode/skills/`, `.zcode/commands/`, `.zcode/hooks/story_zcode_hook.js`를 배포하고 `.zcode/config.json`과 루트 `AGENTS.md`를 안전하게 병합합니다. 훅은 PATH의 `node`가 필요합니다. 현재 ZCode는 플러그인 하위 에이전트를 지원하며 oh-story가 전문 역할 7개를 등록해 현재 `Agent` 도구로 배정합니다. 역할이나 도구를 사용할 수 없을 때만 대체 실행합니다. 스킬만 독립 설치하면 역할이 등록되지 않으므로 플러그인을 활성화해야 합니다. `.zcode/agents/`를 만들거나 사용자 홈에 정의를 쓰지 않습니다. 플러그인 갱신 후 `$story-setup`을 다시 실행해 프로젝트 스냅샷과 이전 AGENTS 지침을 갱신하고 새 세션을 여세요. 현재 훅 어댑터는 `PreCompact`·`SessionEnd`를 등록하지 않으며 압축 후 `SessionStart`로 맥락을 복원합니다. 공식 [플러그인](https://zcode.z.ai/en/docs/plugin)과 [하위 에이전트 문서](https://zcode.z.ai/en/docs/subagents)를 참조하세요.

## OpenCode

**OpenCode 2.x**가 필요합니다(`curl -fsSL https://opencode.ai/v2/install | bash` 또는 `npm i -g @opencode/cli`). 1.x는 본문 보호 플러그인을 읽지 못하므로 story-setup이 중단하고 업그레이드를 안내합니다. 1.x로 배포한 프로젝트는 업그레이드 후 story-setup을 다시 실행합니다. 전역 설치 후 OpenCode가 `~/.claude/skills/`에서 스킬을 자동 탐색합니다. 최초에는 “story-setup으로 웹소설 집필 환경을 배포해줘”처럼 자연어로 호출합니다. 배포 후 슬래시 명령은 자동 로드되며 나타나지 않으면 `opencode reload`를 실행합니다. 세션 시작·종료·압축 등 일부 훅 동작은 Claude Code와 다릅니다. 자세한 내용은 [CONTRIBUTING.md](../CONTRIBUTING.md)의 OpenCode 절에 있습니다.

## OpenClaw

현재는 스킬만 지원합니다. OpenClaw는 작업 공간 `skills/`, `.agents/skills`, `~/.agents/skills`, `~/.openclaw/skills` 등의 스킬 루트에서 14개 스킬을 찾습니다. `SKILL.md`는 한 줄 `name`·`description`, 한 줄 JSON `metadata.openclaw` 형식을 사용합니다. `story-setup`에서 `target_cli=openclaw`를 선택하면 프로젝트 `skills/`로 스킬을 복사하고 OpenClaw용 `AGENTS.md`를 씁니다. 에이전트·훅은 아직 배포하지 않으므로 본문 작성 전 개요 보호는 런타임 강제가 아닌 스킬 지침상의 제약입니다. 새 스킬이 보이지 않으면 OpenClaw 새 세션을 열거나 감시기의 갱신을 기다리세요.

## Reasonix

현재 스킬과 네이티브 플러그인 매니페스트를 지원합니다. Reasonix는 프로젝트 스킬 루트(`.agents/skills` 등, `skills/` 대상 심볼릭 링크)를 기본 탐색해 14개 스킬을 찾습니다. `reasonix doctor capabilities`로 확인하며 루트 `reasonix-plugin.json`을 통한 `reasonix plugin install`도 가능합니다. `story-setup`에서 `target_cli=reasonix`를 선택하면 프로젝트 `skills/`에 복사하고 Reasonix용 `AGENTS.md`를 씁니다. 훅·사용자 정의 에이전트는 아직 배포하지 않아 전문 에이전트가 필요한 스킬은 단독·직접 실행으로 대체합니다. Windows에서 심볼릭 링크가 꺼져 있다면 네이티브 플러그인을 사용합니다.

## 웹 AI와 일반 에이전트

플랫폼이 GitHub 저장소나 프로젝트 파일을 읽을 수 있다면 에이전트에 `skills/*/SKILL.md`와 관련 `references/`를 읽게 합니다. 로컬 복사본이 필요하면 `story-setup`에서 `target_cli=generic`을 선택해 일반 `AGENTS.md`와 `skills/`만 작성합니다. 이 프로젝트의 훅·사용자 정의 에이전트가 없는 환경에서는 스킬 지침상의 제약이나 단독·직접 대체 실행을 사용합니다.

**OpenClaw·Reasonix·일반 배포의 중첩 디렉터리는 수동 정리가 필요합니다.** 이 세 방식은 프로젝트 `skills/`에 스킬 복사본을 두므로 `/story-setup`을 재실행하면 그 복사본이 실행돼 자동 정리가 해당 위치에 도달하지 못합니다. 프로젝트에 `skills/story-setup/references/agent-references/agent-references/`(여러 번 중첩될 수 있음) 또는 `skills/story-setup/skills/`가 있다면 수동으로 삭제합니다. 스킬 텍스트 자체를 갱신하려면 이 프로젝트를 다시 설치하고 새 패키지로 프로젝트 `skills/`의 14개 디렉터리(`browser-cdp`와 `story*`)를 덮어써야 합니다.

업그레이드한 프로젝트에서 이미 `/story-setup`을 실행했다면 루트에서 `/story-setup`을 다시 실행해 훅·에이전트·참조 자료를 동기화하는 것이 좋습니다. 버전별 변경은 [CHANGELOG.md](../CHANGELOG.md)와 [릴리스](https://github.com/zenstory-ai/oh-story-claudecode/releases)에 있습니다.

**여러 에이전트의 협업은 배포 후 새 세션이 필요합니다.** story-architect·narrative-writer·consistency-checker 등 전문 에이전트 7개를 `/story-setup`은 `.claude/agents/`에, `$story-setup`은 `.codex/agents/*.toml`에 씁니다. Antigravity의 `story-setup`은 `.agents/agents/agent-name/agent.md`에 생성합니다(`agent-name`은 실제 이름). Antigravity는 `invoke_subagent`와 같은 이름의 `TypeName`으로 호출하며 런타임에 하위 에이전트가 없으면 스킬이 단독·직접 대체 실행을 명시합니다. 새 세션에서 `/story-review`를 실행해 시작 부분의 “이번 검토 방식”에 여러 관점(전체·간소화 검토)이 표시되면 등록된 것입니다. “혼자 검토함”이면 이전 세션이거나 현재 런타임이 해당 에이전트를 제공하지 않는 상태입니다.

**원고 가져오기와 이어 쓰기 순서:** 먼저 집필 프로젝트 루트에서 `/story-setup`으로 훅·에이전트·AGENTS를 배포합니다. 세션을 새로 시작하거나 갱신한 뒤 `/story-import`로 기존 소설을 가져오고 `/story-long-write 写第N章`으로 이어 씁니다. N은 가져온 범위 다음 장이며 해당 장의 상세 개요부터 보완합니다. `/story-import`를 바로 실행할 수도 있습니다. 배포가 없으면 먼저 setup을 실행할지, 직렬 가져오기를 계속할지 선택하게 합니다.

**작가의 습관은 집필 워크플로가 관리합니다.** `story-long-write`와 `story-short-write`가 작가 메모리를 기록·확인·정리하고 필요할 때 조회합니다. 집필 스킬에 직접 요청하거나 `/story`에 “내 집필 습관을 기억해줘”라고 요청하면 해당 집필 스킬로 전달합니다. 배포된 프로젝트에서 “기억해줘: …”라고 해도 집필 흐름을 따르며 코딩 도구 자체의 메모리에 넣지 않습니다. AI 문체 제거·원고 검토는 집필 흐름이 전달한 문체 요구를 사용합니다.

작가 메모리는 두 계층입니다. 전역·장르·워크플로 선호는 작업 공간 `.story/작가기억/`의 `AP` 항목으로, 특정 책의 선호는 해당 책 `.story/작가기억/`의 `BP` 항목으로 저장해 책과 함께 보관·이동합니다. `Author Memory Receipt`가 반환돼야 기록 성공입니다. 일반 집필은 이번 작업에 관련된 확인된 항목만 조회합니다. 집필자에게 전달하는 습관 원문은 조회마다 최대 2 KB이며 들어가지 못한 내용은 장 끝 보고에서 작가의 원문 그대로 알립니다. 전체 프로필·후보·이력을 본문 프롬프트에 넣지 않습니다. 책별 플롯 추적과는 별개이며 현재 요구, 이 책의 설정, 필수 검증 관문이 항상 우선합니다.
