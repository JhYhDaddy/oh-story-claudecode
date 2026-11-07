# Codex 배포

`target_cli`에 `codex`가 있으면 SKILL.md Phase 2에서 이 파일을 전부 읽고 순서대로 실행한다. 경로 검사·멱등 재실행·잔여물 정리·배포 표식·템플릿 자리표시자·프로젝트 지침 병합·보고는 SKILL.md의 공통 규칙을 따른다.

## 배포 목록(기계적 검사 가능)

| Source path | Target path | Owner class | Merge mode | Validation check |
|-------------|-------------|-------------|------------|------------------|
| `skills/story-setup/references/codex/AGENTS.md.tmpl` | `AGENTS.md` | user+managed | 관리 블록 병합 | Codex story 스킬 라우팅 절 포함 |
| `skills/story-setup/references/codex/agents/` | `.codex/agents/` | story-setup 관리 | 교체 | TOML 7개 해석 가능, `name`/`description`/`developer_instructions` 포함 |
| `skills/story-setup/references/codex/hooks/hooks.json` | `.codex/hooks.json` | user+managed | 고정 훅 식별자로 관리 등록 교체 | JSON 유효, 오래된 직접/launcher 등록 전부 제거, 현재 등록 6개가 각각 정확히 한 번 존재 |
| `skills/story-setup/references/codex/hooks/{story_codex_hook.py,run-story-hook.sh,run-story-hook.cmd}` | `.codex/hooks/`의 같은 이름 파일 | story-setup 관리 | 교체 | Python/shell/cmd launcher 파일 모두 존재 |
| `skills/story-setup/scripts/merge-codex-hooks.py` | 배포 시 실행, 프로젝트에는 복사 안 함 | story-setup helper | 실행 | 알려진 관리 등록 교체, 사용자 훅·알 수 없는 최상위 필드 보존, 멱등 결과 |
| `skills/story-setup/references/agent-references/` | `.codex/skills/story-setup/references/agent-references/` | story-setup 관리 | 교체 | 모든 참조 해석 가능 |

## Codex 에이전트 배포

- `skills/story-setup/references/codex/agents/`의 모든 `.toml`을 읽어 사용자 프로젝트 `.codex/agents/`에 복사한다.
- 에이전트 파일은 story-setup 관리 대상이며 덮어쓸 수 있다. Claude Code Markdown이 본문 원본이다. 저장소 루트 `scripts/generate-codex-agents.py`가 `references/codex/agents/` TOML을 결정적으로 생성하며 배포는 이 산출물만 복사한다.
- 각 TOML이 해석 가능하고 Codex 필수 필드 `name`·`description`·`developer_instructions`를 포함하는지 확인한다.
- 읽기 전용 역할(`consistency-checker`·`story-explorer`)은 `sandbox_mode = "read-only"`를 유지한다. `chapter-extractor`는 배치 입력 파일을 쓰므로 읽기 전용 샌드박스를 설정하지 않는다.
- **배포 뒤 trust + 새 Codex 세션이 필수다.** 보고와 fallback 규칙은 아래 필수 안내를 따른다. `/hooks`에서 신뢰하기 전에는 Codex가 본문 전 개요 가드를 포함한 훅을 조용히 건너뛴다. 실행 중 `unknown agent_type`이면 호출자는 solo/direct로 전환하고 fallback을 보고한다.
- `skills/story-setup/references/agent-references/`를 `.codex/skills/story-setup/references/agent-references/`로 동기화 복사하여 Codex 에이전트의 프로젝트 내부 주 참조 경로로 삼는다. 현재 표준 접두사 `.codex/skills/`만 쓰고 실행 중 과거 대체 경로를 순회하지 않는다.

## Codex hooks.json 병합 알고리즘

프로젝트 훅은 `.codex/hooks.json`, 실행 스크립트는 `.codex/hooks/story_codex_hook.py`·`run-story-hook.sh`·`run-story-hook.cmd`에 배포한다. JSON은 프로젝트 루트 탐색과 event 전달만 맡고 인터프리터 탐색은 플랫폼 launcher가 통합 처리한다.

1. 현재 story-setup 스킬 디렉터리를 찾고 `references/codex/hooks/hooks.json`을 유일한 현재 템플릿으로 읽는다. 프로젝트 `.codex/hooks.json`도 읽으며 없으면 빈 객체로 본다.
2. 기존 플랫폼 공통 규칙으로 Python을 탐색한다: `for PYBIN in python3 python py; do "$PYBIN" -c "" 2>/dev/null && break; done`. 없으면 멈추고 JSON 병합을 직접 작성하거나 간소화하지 않는다.
3. `"$PYBIN" "{story-setup skill目录}/scripts/merge-codex-hooks.py" --existing "{项目}/.codex/hooks.json" --template "{story-setup skill目录}/references/codex/hooks/hooks.json" --output "{项目}/.codex/hooks.json"`을 호출한다. helper는 과거 직접 호출 `story_codex_hook.py`와 현재 `run-story-hook.sh`·`run-story-hook.cmd`의 세 관리 식별자를 인식한다. 알려진 관리 등록을 모두 제거한 뒤 현재 템플릿을 추가한다.
4. 기존 사용자 훅, matcher 블록, 알 수 없는 최상위 필드를 보존한다. 반복 실행은 멱등이어야 한다. 원래 `command` 문자열 기준으로 추가·중복 제거하지 않는다. 그러면 v17 직접 명령과 v18 launcher가 이중 등록된다.
5. 저장 후 JSON을 해석하여 이전 `story_codex_hook.py` 직접 명령은 0개, 현재 템플릿의 등록 6개는 각각 정확히 한 번, 사용자 훅·알 수 없는 최상위 필드는 유지됨을 확인한다. 이어 사용자에게 프로젝트 `.codex/` 계층의 Codex trust와 non-managed command hooks의 `/hooks` review/trust가 필요하다고 알린다. Windows에서는 `commandWindows`를 쓰며 launcher는 현재 디렉터리에서 위로 `.codex/hooks/`를 찾으므로 POSIX와 중첩 디렉터리 동작이 같다.

## AGENTS.md와 배포 표식

- `references/codex/AGENTS.md.tmpl`을 SKILL.md의 프로젝트 지침 병합에 따라 루트 `AGENTS.md`에 쓴다(`--host codex`).
- `.story-deployed`의 `target_cli`는 `codex` 또는 여러 호스트 조합, `references_dir`는 `.codex/skills/story-setup/references/agent-references`로 쓴다.

## 검증

- `AGENTS.md`에 Codex story 스킬 라우팅 절이 있는지 확인한다.
- `.codex/agents/`의 `.toml` 에이전트 정의 7개가 존재하고 해석 가능한지 확인한다.
- `.codex/hooks.json`이 존재하고 유효하며 Unix `command`는 `run-story-hook.sh`, Windows `commandWindows`는 `run-story-hook.cmd`로만 시작하는지 확인한다. `story_codex_hook.py` 직접 호출 등록은 없어야 한다.
- `.codex/hooks/story_codex_hook.py`·`run-story-hook.sh`·`run-story-hook.cmd`가 있고 Python 구문이 유효하며 POSIX/Windows launcher가 중첩 cwd에서 프로젝트 루트를 찾는지 확인한다.
- 하위 디렉터리를 포함하여 `.codex/skills/story-setup/references/agent-references/`를 소스 상대 경로와 대조한다.

## 설치 보고 필수 안내

Codex는 프로젝트 `.codex/` 설정 계층 trust와 `/hooks`에서 non-managed 훅 review/trust가 필요하다. **신뢰 전에는 오류 없이 훅을 조용히 건너뛰므로 본문 전 개요 가드도 작동하지 않는다.** 자동화의 `codex exec`에는 `--dangerously-bypass-hook-trust`를 추가할 수 있다. 배포 뒤 새 Codex 세션을 열어 custom agents를 활성화한다. 그래도 실행 환경이 `unknown agent_type`을 반환하면 각 스킬의 fallback 규칙으로 solo/direct 전환한다.
