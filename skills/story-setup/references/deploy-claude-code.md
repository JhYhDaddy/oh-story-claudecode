# Claude Code 배포

`target_cli`에 `claude-code`가 있으면 SKILL.md Phase 2에서 이 파일을 전부 읽고 순서대로 실행한다. 경로 검사·멱등 재실행·잔여물 정리·배포 표식·템플릿 자리표시자·보고는 SKILL.md의 공통 규칙을 따른다.

## 배포 목록(기계적 검사 가능)

| Source path | Target path | Owner class | Merge mode | Validation check |
|-------------|-------------|-------------|------------|------------------|
| `skills/story-setup/references/templates/CLAUDE.md.tmpl` | `CLAUDE.md` | user+managed | 관리 블록 병합 | story 스킬 라우팅 절 포함 |
| `skills/story-setup/references/templates/hooks/` | `.claude/hooks/` | story-setup 관리 | recursive replace | `session-*.sh`, `detect-story-gaps.sh`, `validate-story-commit.sh`, `guard-outline-before-prose.sh`, `check-prose-after-write.sh`, `story_hook_core.js`, `story_hook_cli.js`, `lib/common.sh`, `lib/sentinel.sh` 존재; `story_hook_core.js`가 OpenCode/ZCode/Antigravity 사본과 바이트 단위로 동일 |
| `skills/story-setup/references/templates/rules/*.md` | `.claude/rules/*.md` | story-setup 관리 | 교체 | 모든 규칙에 `paths` frontmatter 포함 |
| `skills/story-setup/references/templates/agents/*.md` | `.claude/agents/*.md` | story-setup 관리 | 교체 | 에이전트 파일 7개 존재 |
| `skills/story-setup/references/agent-references/*.md` | `.claude/skills/story-setup/references/agent-references/*.md` | story-setup 관리 | 교체 | 모든 `story-setup/references/agent-references/*.md` 참조 해석 가능 |
| `skills/story-setup/references/templates/settings-hooks.json` | `.claude/settings.local.json` | user+managed | 고정 훅 식별자로 관리 등록 교체 | JSON 유효, 이전 matcher 등록 이전 완료, 현재 템플릿 명령 각각 하나, 사용자 훅 보존 |
| `skills/story-setup/scripts/merge-claude-settings.py` | 배포 시 실행, 프로젝트에 복사 안 함 | story-setup helper | 실행 | 알려진 story 훅 등록 교체, 사용자 훅/최상위 필드 보존, v24→v25 이전 및 재실행 멱등 |
| `skills/story-setup/scripts/copy-path-safety.py` | 재귀 복사 전마다 실행, 프로젝트 전용 디렉터리에 복사 안 함 | story-setup helper | 실행 | JSON `copy_allowed: true`일 때만 복사, symlink 같은 객체는 no-op, target이 source 안이면 중단 |
| 생성 sentinel | `.story-deployed` | story-setup 관리 | 교체 | `agents_version`, `setup_skill_version`, `target_cli`, `resolver_strategy`, `references_dir` 포함 |

`references/templates/hooks/` 내용: 훅 스크립트 템플릿 8개 + `story_hook_core.js`(본문 검사망·개요 가드·연속성·커밋 탐지의 공유 구현, OpenCode/ZCode/Antigravity와 동일) + `story_hook_cli.js`(bash 훅이 코어를 호출하는 node 연결부) + `lib/common.sh`/`lib/sentinel.sh`. 본문 보완 검사 `check-prose-after-write.sh`는 PostToolUse Write/Edit에 한정한다. `cat>`/`tee` 등 Bash 본문 쓰기는 Claude에서 쓰기 전 가드만 실행한다.

## CLAUDE.md 배포

SKILL.md의 프로젝트 지침 병합에 따라 프로젝트 루트 `CLAUDE.md`에 쓴다. `--host claude-code`, 템플릿은 `references/templates/CLAUDE.md.tmpl`.

## Hooks 배포

- **전체 디렉터리 트리 재귀 복사**: `skills/story-setup/references/templates/hooks/`를 사용자 프로젝트 `.claude/hooks/`로 복사한다.
- `lib/` 하위 디렉터리를 반드시 유지한다.
  - `lib/common.sh`: `project_root`·`discover_active_book`·`discover_all_books` 제공.
  - `lib/sentinel.sh`: `.story-deployed` 필드 읽기 제공.
- `.claude/hooks/*.sh`만 실행 권한(`chmod +x`)을 주면 된다. `lib/*.sh`는 훅이 `source`하므로 실행 비트가 필요 없다.

## Rules 배포

- `skills/story-setup/references/templates/rules/`의 모든 `.md`를 읽는다.
- 사용자 프로젝트 `.claude/rules/`로 복사한다.

## Agents 배포

- `skills/story-setup/references/templates/agents/`의 모든 `.md`를 읽는다.
- 사용자 프로젝트 `.claude/agents/`로 복사한다.
- 에이전트 파일은 story-setup 관리 대상이며 덮어써도 된다. oh-story 에이전트 7개만 덮어쓰고 작가의 자체 에이전트는 보존한다.
- 여기의 Claude Code Markdown이 에이전트 본문의 원본이며 다른 호스트 에이전트는 모두 이를 변환한다.
- **배포 뒤 새 세션을 열어야 한다.** 에이전트는 세션 시작에만 등록된다. 아래 설치 보고 필수 안내를 따른다.

### Agent References 배포

- `skills/story-setup/references/agent-references/`의 모든 `.md`를 하위 디렉터리와 함께 프로젝트 `.claude/skills/story-setup/references/agent-references/`로 재귀 복사한다.
- 에이전트나 참조에 `story-setup/references/agent-references/<file>.md`가 나오면 소스·대상 패키지 모두에 `<file>.md`가 있어야 한다.
- 배포 뒤 에이전트 참조는 이 스킬 안의 복사 경로 `story-setup/references/agent-references/*.md`를 사용한다. 다른 스킬의 references로 직접 연결하지 않는다. Claude Code는 현재 표준 접두사 `.claude/skills/`만 쓰고 실행 중 과거 대체 경로를 순회하지 않는다.

## settings.local.json에 Hooks 등록 병합

`.claude/settings.local.json`이 있으면 기존 설정을 읽어 병합하고 없으면 helper가 새 파일을 만든다.

1. 기존 플랫폼 공통 규칙으로 Python을 탐색한다: `for PYBIN in python3 python py; do "$PYBIN" -c "" 2>/dev/null && break; done`. 없으면 멈추며 병합을 직접 작성하거나 간소화하지 않는다.
2. `"$PYBIN" "{story-setup skill目录}/scripts/merge-claude-settings.py" --existing "{项目}/.claude/settings.local.json" --template "{story-setup skill目录}/references/templates/settings-hooks.json" --output "{项目}/.claude/settings.local.json"`을 호출한다.
3. helper는 알려진 모든 story-setup 훅의 과거 등록을 제거하고 현재 템플릿을 추가한다. matcher/timeout/if를 버전에 맞게 갱신하면서 이전 블록에 섞인 사용자 훅과 알 수 없는 최상위 필드를 원형 보존한다. 저장 후 JSON을 해석하여 템플릿 명령이 각각 하나이고 사용자 설정이 남았는지 확인한다. helper를 재실행하고 파일 바이트를 비교해 멱등성을 확인한다.

## 배포 표식 보충

- `references_dir`는 `.claude/skills/story-setup/references/agent-references`로 쓴다. 여러 호스트는 쉼표로 연결한다.
- 일회성 표식 `.claude/.agents-pending-restart`도 만든다(빈 파일이면 충분). session-start.sh가 다음 세션 시작 시 이를 보고 에이전트 등록을 확인한 뒤 자동 삭제하여 사용자에게 재시작 적용을 알려 준다.

## 검증

1. 훅 등록:
   - `.claude/settings.local.json`의 hooks 필드 확인.
   - `.claude/hooks/` 스크립트 존재와 실행 권한 확인.
   - `.claude/hooks/lib/common.sh`와 `.claude/hooks/lib/sentinel.sh` 존재 확인.
2. 규칙 경로:
   - `.claude/rules/` 규칙 파일 존재와 `paths` frontmatter 확인.
3. 에이전트:
   - `.claude/agents/`의 정의 파일 7개 확인.
4. 에이전트 참조 묶음:
   - 하위 디렉터리를 포함해 `.claude/skills/story-setup/references/agent-references/`를 소스 상대 경로와 대조.
   - 모든 `story-setup/references/agent-references/<file>.md`가 배포 묶음에서 해석되는지 확인.

## 설치 보고 필수 안내

- **재시작 안내는 눈에 띄게 ‘남은 할 일’ 첫 항목에 둔다.** 이번 배포가 `.claude/agents/`에 썼지만 Claude Code는 세션 시작 시에만 custom agent를 `subagent_type`으로 등록한다. **새 Claude Code 세션을 열고 집필을 시작한다.** 그렇지 않으면 현재 세션의 story-review / story-long-write 등이 `story-architect`·`narrative-writer`를 spawn할 때 ‘subagent_type 사용 불가’로 solo 전환하여 단일 관점이 되고 다중 에이전트 협업을 잃는다. 적용 여부는 새 세션에서 `/story-review`를 실행하여 보고서 첫머리 ‘이번 검토 방식’이 여러 관점(전체/간소 검토)이면 등록 성공이다. ‘혼자 검토’라면 이전 세션이거나 미등록이다.
- 재시작 뒤 `/story-long-write` 또는 `/story-short-write`를 사용할 수 있다.
