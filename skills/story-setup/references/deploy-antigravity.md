# Google Antigravity 배포

`target_cli`에 `antigravity`가 있으면 SKILL.md Phase 2에서 이 파일을 전부 읽고 순서대로 실행한다. 경로 검사·멱등 재실행·잔여물 정리·배포 표식·템플릿 자리표시자·보고는 SKILL.md의 공통 규칙을 따른다. `references/antigravity/`는 Always-On Rule·named-group 훅·I/O 어댑터를 제공한다. 쓰기 후 발견 사항은 세션 산출물로 PreInvocation/Stop에 전달한다.

## 배포 목록(기계적 검사 가능)

| Source path | Target path | Owner class | Merge mode | Validation check |
|-------------|-------------|-------------|------------|------------------|
| 현재 패키지 스킬 루트 + `scripts/deploy-antigravity-skills.py` | `.agents/skills/{browser-cdp,story*}/` | 알려진 스킬명 14개는 story-setup 관리 | 알려진 디렉터리 원자 교체, 미지 스킬 보존, symlink를 따라 쓰지 않음 | 유효한 `SKILL.md`가 있는 실제 디렉터리 14개 |
| `skills/story-setup/scripts/generate-antigravity-agents.mjs` + Claude 에이전트 원본 | `.agents/agents/agent-name/agent.md`(`agent-name`은 실제 이름) | 알려진 정의 7개는 story-setup 관리 | 생성 후 알려진 정의 원자 교체, 미지 사용자 에이전트 보존 | Markdown 에이전트 7개 해석 가능, 정확한 Antigravity 도구명, `mainAgent: false`, `subagent: true` |
| `skills/story-setup/references/antigravity/rules/oh-story.md` | `.agents/rules/oh-story.md` | story-setup 관리 | 교체 | `trigger: always_on`, 12,000자 미만 |
| `skills/story-setup/references/antigravity/hooks/hooks.json` | `.agents/hooks.json` | user+managed | 최상위 `oh-story` 그룹만 교체 | Antigravity named-group schema 유효, 사용자 그룹 보존, 멱등 |
| `skills/story-setup/references/antigravity/hooks/{story_antigravity_hook.js,story_hook_core.js}` | `.agents/hooks/`의 같은 이름 파일 | story-setup 관리 | 교체 | Node 구문 유효, core가 공유 원본과 바이트 동일, 훅 계약 테스트 통과 |
| `skills/story-setup/scripts/merge-antigravity-hooks.py` | 배포 helper 전용 | story-setup helper | 실행 | `oh-story`만 원자 교체, 사용자 그룹 보존, 멱등 |

## Antigravity 에이전트 배포

- PATH에서 `node`를 먼저 확인한다. 에이전트 생성과 프로젝트 훅이 모두 Node에 의존한다. 없으면 Antigravity 대상 배포를 멈추고 반제품을 남기지 않으며 Node 설치 후 재실행을 안내한다.
- Claude Code Markdown이 에이전트 본문 원본이다. 배포 시 story-setup의 `scripts/generate-antigravity-agents.mjs`가 `.agents/agents/agent-name/agent.md`(`agent-name`은 실제 이름)를 만든다. Claude 도구명·모델 등급·참조 루트·호출 용어를 Antigravity 2.0 계약으로 결정적으로 변환한다. Claude frontmatter를 그대로 복사하지 않는다.
- `node "{story-setup skill目录}/scripts/generate-antigravity-agents.mjs" --source "{story-setup skill目录}/references/templates/agents" --dest "{项目}/.agents/agents"`를 실행한다. 생성기는 7개를 모두 렌더링한 뒤 알려진 `.agents/agents/agent-name/agent.md` 7개를 원자 교체하고 구형 동명 평면 `.md`를 정리한다. 다른 사용자 에이전트는 보존한다. 어떤 원본의 frontmatter라도 잘못되면 일부만 갱신한 디렉터리를 남기지 않으며 관리 에이전트 symlink를 따라 프로젝트 밖에 쓰지 않는다.
- `.md` 7개를 검증한다. `name`이 부모 `agent-name`과 일치하고 `mainAgent: false`·`subagent: true`여야 한다. 모델은 `flash` / `pro`만, 도구는 공식 `view_file`·`find_by_name`·`grep_search`·`write_to_file`·`replace_file_content`·`multi_replace_file_content`·`run_command`만 사용한다. Claude의 `Read/Glob/Grep/Write/Edit/Bash`나 `.claude/skills/` 접두사가 남으면 안 된다. Antigravity는 현재 표준 `.agents/skills/`만 쓴다.
- 읽기 전용 `consistency-checker`·`story-explorer`에는 쓰기·명령 도구가 없어야 한다. `chapter-extractor`는 읽기·파일 쓰기만 있고 명령 도구가 없다. 나머지는 Claude 원본의 기능 경계에 따라 대응한다.
- Antigravity는 `invoke_subagent`의 `TypeName`으로 호출한다. 배포 뒤 새 Antigravity 대화를 열고 `story-review`로 full/lean을 확인한다. 실행 중 custom agent를 찾지 못하면 스킬의 solo/direct fallback으로 수행한다.

## Antigravity 배포 알고리즘

Antigravity 2.0은 프로젝트 `.agents/`를 customization 루트로 쓴다. `.agents/skills`·`.agents/agents`·`.agents/rules`·`.agents/hooks`를 만들고 `.agents/hooks.json`을 병합한다. Skills·Always-On Rule·custom subagents 7개·workspace Hooks를 배포하며 사용자 home의 `~/.gemini/`는 수정하지 않는다.

1. 현재 패키지의 알려진 스킬 14개(`browser-cdp`와 `story*`)를 찾아 `deploy-antigravity-skills.py --source "{当前 skill 包根}" --dest "{项目}/.agents/skills"`로 원자적으로 실제 파일을 만든다. helper는 14개 이름만 교체하고 다른 사용자 스킬은 보존하며 소스/대상 realpath가 같으면 no-op다. 대상은 **실제 디렉터리**여야 한다. 최상위 `.agents/skills → ../skills` symlink를 새로 만들지 않는다. Antigravity 2.0 프로젝트 배포는 실제 디렉터리를 지원 경로로 삼는다.
   - 기존 `.agents/skills`가 symlink면 helper는 먼저 멈추고 링크를 따라 쓰지 않아야 한다. AskUserQuestion으로 다음을 설명한다. 이전 과정은 링크로 보이는 모든 스킬을 프로젝트 안의 새 실제 디렉터리로 복사하고 oh-story 이름 14개만 갱신하며 링크 대상은 원형 보존하지만 symlink 자체는 디렉터리로 바꾼다. 큰 git diff가 생길 수 있다. 사용자가 명시적으로 동의한 뒤에만 `--migrate-symlink`를 추가해 재실행한다. 거부하면 Antigravity 배포를 멈추고 완전한 지원을 확보하지 못했다고 보고한다. 다중 호스트 배포나 기존 Codex symlink를 이유로 이 확인을 생략하지 않는다.
2. 위 에이전트 배포 절의 생성기로 `.agents/agents/`의 알려진 `.agents/agents/agent-name/agent.md` 7개를 원자 갱신하고 다른 사용자 에이전트를 보존한다. 사용자 home에서 에이전트를 옮겨 오지 않는다.
3. `references/antigravity/rules/oh-story.md`를 `.agents/rules/oh-story.md`로 복사하고 `trigger: always_on`·12,000자 미만을 확인한다. 이 규칙이 스킬 라우팅·집필 강제 제약·compact 후 복구를 맡는다. Antigravity IDE는 루트 `AGENTS.md`를 workspace 규칙으로 보지 않으므로 AGENTS 템플릿으로 대체하지 않는다.
4. `references/antigravity/hooks/story_antigravity_hook.js`와 같은 디렉터리의 `story_hook_core.js`를 `.agents/hooks/`에 복사하고 `node --check`를 검증한다. 훅 명령은 `.agents/`(`hooks.json` 위치)를 작업 디렉터리로 하므로 `hooks/story_antigravity_hook.js`를 써야 하며 `.agents/hooks/...`로 쓰지 않는다. 공유 core는 Claude/OpenCode/ZCode 원본과 바이트가 같아야 한다.
5. `references/antigravity/hooks/hooks.json`을 `.agents/hooks.json`에 병합한다. 플랫폼 공통 규칙으로 Python 3를 찾고 `merge-antigravity-hooks.py {项目}/.agents/hooks.json {skill目录}/references/antigravity/hooks/hooks.json`을 호출한다. helper는 최상위 `oh-story` named group만 교체하고 다른 사용자 훅 그룹을 보존한다. 저장 뒤 재실행하고 바이트 비교로 멱등성을 확인한다. Claude/Codex의 바깥 `{ "hooks": ... }` schema를 Antigravity에 쓰지 않는다.
6. 이벤트 경계를 검증한다. `PreToolUse`·`PostToolUse`·`PreInvocation`·`Stop`만 등록한다. PreToolUse는 호출마다 `decision`, PostToolUse는 `{}`만 출력해야 한다. 본문 발견 사항은 세션 `artifactDirectoryPath`에 임시 저장했다가 다음 PreInvocation에서 주입한다. 모델이 바로 종료하려 하면 Stop은 무한 루프를 막기 위해 최대 한 번만 계속하도록 강제한다. 외부 훅에는 SessionStart/PreCompact/PostCompact가 없다. 첫 맥락은 `invocationNum=0`의 PreInvocation이 주입하고 compact 뒤에는 Always-On Rule이 `추적/문맥.md` 읽기를 강제한다.
7. `.story-deployed`의 `target_cli`는 `antigravity` 또는 여러 호스트 조합, `references_dir`는 `.agents/skills/story-setup/references/agent-references`로 쓴다. 설치 보고에 새 대화를 열어 Skills/Rules/Agents/Hooks를 다시 탐색하도록 안내하고 Node가 훅 실행 의존성임을 명시한다.

Antigravity IDE와 대화형 `agy`는 이 workspace `.agents/` 산출물을 공유하지만 각각 실제 환경 smoke test가 필요하다. `npx skills add -g`가 현재 어느 `~/.gemini/*`에 전역 스킬을 쓰는지에 의존하지 않는다. story-setup의 지원 범위는 위 프로젝트 내부 실제 디렉터리 배포다.

## 검증

- `.agents/skills/`의 story 스킬 14개가 실제 디렉터리이며 `SKILL.md`를 읽을 수 있고 `.agents/skills/story-setup/references/agent-references/`가 완전한지 확인한다.
- `.agents/agents/`의 Markdown 에이전트 7개가 해석 가능하고 이름·모델 등급·공식 도구 허용 목록·읽기 전용 경계·`.agents/skills/` 참조 접두사가 맞는지 확인한다.
- `.agents/rules/oh-story.md`의 `trigger: always_on`과 12,000자 미만을 확인한다.
- `.agents/hooks.json`이 유효하며 최상위 `oh-story`에 정확히 PreToolUse/PostToolUse/PreInvocation/Stop이 있고 사용자 그룹이 보존되었는지 확인한다. `.agents/hooks/story_antigravity_hook.js`와 `story_hook_core.js` 구문도 확인한다.
- fixture 검증: 개요/추적 누락 PreToolUse는 deny, 일반 쓰기는 allow, 커밋은 advisory. PostToolUse stdout은 항상 `{}`이며 본문 발견 사항을 세션 산출물에 쓴다. 다음 PreInvocation이 이를 주입한다. 미처리 발견 사항의 Stop continue는 최대 한 번이다. 깨끗한 본문은 pending state를 지운다.

## 설치 보고 필수 안내

새 Antigravity 대화로 customization을 새로 읽는다. Hooks는 PATH의 `node`에 의존한다. 외부 훅 API에 PreCompact/PostCompact가 없으므로 Always-On Rule이 `추적/문맥.md`를 읽어 compact에서 복구한다. IDE와 대화형 `agy`는 각각 실제 환경 smoke test를 권한다. 명령줄 집필은 프로젝트 디렉터리에서 대화형 `agy`로 들어가 `/skills`·`/agents`·`/hooks`가 oh-story를 찾았는지 확인한 뒤 요청한다. print 모드 `agy -p`는 `--add-dir "$PWD"`가 필수다(agy 1.2.10 실측에서 있어야 workspace `.agents/`의 스킬 14개·에이전트 7개·훅을 읽었으며 없으면 모두 읽지 못해 `~/.gemini/antigravity-cli/scratch/`로 쓰기가 돌아갈 수 있음). 테스트 뒤 scratch에 예상 밖 소설 산출물이 없는지 확인한다.
