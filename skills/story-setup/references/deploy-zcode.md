# ZCode 배포

`target_cli`에 `zcode`가 있으면 SKILL.md Phase 2에서 이 파일을 전부 읽고 순서대로 실행한다. 경로 검사·멱등 재실행·잔여물 정리·배포 표식·템플릿 자리표시자·프로젝트 지침 병합·보고는 SKILL.md의 공통 규칙을 따른다. `references/zcode/`는 AGENTS·Commands 14개·플러그인 역할·workspace config patch·엄격한 JSON Hook runner를 제공한다.

## 배포 목록(기계적 검사 가능)

| Source path | Target path | Owner class | Merge mode | Validation check |
|-------------|-------------|-------------|------------|------------------|
| `skills/story-setup/references/zcode/AGENTS.md.tmpl` | `AGENTS.md` | user+managed | 관리 블록 병합 | ZCode `$story-*` 라우팅·기능 기반 fallback 포함 |
| `skills/story-setup/references/zcode/agents/*.md` | 플러그인 manifest의 `agents` 등록(workspace에 복사하지 않음) | plugin managed | 플러그인 갱신 | 같은 이름의 전문 역할 7개 등록. 파일 존재만으로 호출 가능하지 않음 |
| 저장소 `skills/{browser-cdp,story*}/` | `.zcode/skills/{browser-cdp,story*}/` | 알려진 스킬명은 story-setup 관리 | 알려진 디렉터리만 교체 | `SKILL.md` 14개 존재, ZCode frontmatter 제한 충족 |
| `skills/story-setup/references/zcode/commands/` | `.zcode/commands/` | 알려진 명령명은 story-setup 관리 | 알려진 명령 파일만 교체 | 명령 14개의 이름/frontmatter 유효 |
| `skills/story-setup/references/zcode/hooks/story_zcode_hook.js` | `.zcode/hooks/story_zcode_hook.js` | story-setup 관리 | 교체 | Node 구문·훅 계약 테스트 통과 |
| `skills/story-setup/references/zcode/hooks/story_hook_core.js` | `.zcode/hooks/story_hook_core.js` | story-setup 관리 | 교체 | Node 구문·훅 계약 테스트 통과 |
| `skills/story-setup/references/zcode/config.json.patch` | `.zcode/config.json`에 병합 | user+managed | event+matcher+process args로 병합 | JSON 유효. 아래 알고리즘 4단계 상호 배타 분기에 따라 미설치 시 `hooks.enabled=true`·지원 이벤트만, 설치 시 이번 oh-story 훅 등록 없음/제거됨 확인 |

## 에이전트 경계

**ZCode는 하위 에이전트와 플러그인 역할을 지원한다.** oh-story 플러그인이 manifest의 `agents`로 전문 역할 7개를 등록한다. 현재 실행 환경의 `Agent` 도구와 실제 schema를 사용한다. `.zcode/agents/`를 만들거나 사용자 home을 수정하지 않는다. 공식 사용자 수준 정의·플러그인 등록은 workspace 디렉터리 탐색과 다르다. 독립 Skills 설치는 플러그인 역할을 자동 등록하지 않으므로 역할이 없으면 oh-story 플러그인 활성화/갱신을 안내하고 그래도 사용할 수 없을 때 solo/direct로 전환한다. 근거: [플러그인](https://zcode.z.ai/en/docs/plugin), [하위 에이전트](https://zcode.z.ai/en/docs/subagents).

## ZCode 배포 알고리즘

프로젝트에는 Skills·Commands·AGENTS.md·Hooks를 배포한다. `.zcode/agents`나 `.zcode/rules`는 배포하지 않으며 플러그인 역할은 플러그인 설치/갱신으로 등록한다.

1. 저장소 현재 `skills/`에서 `SKILL.md`가 있는 디렉터리 14개를 `.zcode/skills/{skill-name}/`로 복사한다. 알려진 디렉터리만 교체하고 다른 사용자 Skills는 보존한다. 에이전트 참조는 현재 표준 접두사 `.zcode/skills/`에서만 찾고 실행 중 과거 대체 경로를 순회하지 않는다.
2. `references/zcode/commands/*.md`를 `.zcode/commands/`에 복사한다. 같은 이름 명령 14개만 교체하고 다른 사용자 Commands는 보존한다.
3. `references/zcode/hooks/story_zcode_hook.js`와 `references/zcode/hooks/story_hook_core.js`를 `.zcode/hooks/`에 복사한다.
4. `references/zcode/config.json.patch`와 기존 `.zcode/config.json`을 읽는다. 루트 `zcode.json`만 있더라도 oh-story 프로젝트 훅용 `.zcode/config.json`을 만들며 루트 파일은 바꾸지 않는다.
   - 사용자 미지 필드·MCP·plugins·skills/commands disable overrides를 모두 유지한다.
   - **훅 상호 배타(이중 실행 방지)**: 설치된 oh-story 플러그인으로 실행하는 프로젝트라면(marketplace 설치, 루트 `.zcode-plugin/plugin.json`의 `hooks.json`이 SessionStart/PreToolUse/PostToolUse를 전역 등록) `.zcode/config.json`에서 이번 알려진 oh-story 훅 등록을 제거하고 사용자 훅을 유지한 뒤 아래 `config.json.patch` 훅 병합을 **건너뛴다**. manifest가 이미 등록했으므로 다시 병합하면 같은 이벤트가 두 번 실행된다(PreToolUse 이중 차단·PostToolUse 이중 주입). 플러그인 미설치(직접 clone/수동 references 가져오기)일 때만 병합한다. 불확실하면 ‘ZCode가 이 플러그인을 통해 이 훅 묶음을 이미 등록했는가’로 판단한다. 두 경로 모두 스킬·명령·훅 파일·AGENTS·config의 훅 외 필드는 정상 배포한다.
   - 훅 병합(미설치 때만): `hooks.enabled: true`. 사용자의 기존 `timeoutMs`가 더 크면 유지하고 아니면 템플릿값을 쓴다. `hooks.events`의 SessionStart·PreToolUse·PostToolUse를 `event + matcher + process command + args`로 중복 제거하여 추가한다. 지원하지 않는 PreCompact·PostCompact·SessionEnd·SubagentStop·Notification은 복사하지 않는다.
5. `references/zcode/AGENTS.md.tmpl`을 SKILL.md의 프로젝트 지침 병합에 따라 루트 `AGENTS.md`에 쓴다(`--host zcode`).
6. `.story-deployed`의 `target_cli`는 `zcode` 또는 여러 호스트 조합, `references_dir`는 `.zcode/skills/story-setup/references/agent-references`로 쓴다. Claude의 `.claude/.agents-pending-restart`는 만들지 않는다.
7. 실제 플러그인 등록 역할을 확인하고 사실대로 보고한다. 사용할 수 있으면 같은 이름 역할로 배정하고, 없으면 플러그인 활성화/갱신 후 새 세션을 안내한다. workspace 재배포로 대신하지 않는다. 훅은 PATH의 실행 가능한 `node`가 필요하다.

플러그인 설치는 이 알고리즘을 거치지 않는다. `.zcode-plugin/plugin.json`이 Skills·Commands·Hooks·역할 7개를 노출한다. 플러그인 Skills는 workspace `.zcode/skills`보다 우선순위가 낮다. 업그레이드 뒤 **갱신된 플러그인 사본**에서 story-setup을 실행하여 오래된 프로젝트 스냅샷과 AGENTS 관리 블록을 덮어써야 한다. 이전 setup이 플러그인을 가리면 [업그레이드 가이드](../UPGRADING.md)에 따라 백업 후 밖으로 옮기고 다시 배포한다. **훅 등록은 하나뿐이어야 한다.** 플러그인이 있으면 manifest가 등록 기준이며 workspace의 같은 등록은 4단계로 정리한다.

## 검증

- 루트 `AGENTS.md`에 ZCode `$story-*` 라우팅·개요 가드·기능 기반 fallback이 있고 고정 solo 지시가 없는지 확인한다.
- 플러그인이 있으면 전문 역할 7개의 실제 등록을 확인한다. 독립 Skills만 있으면 역할 누락을 허용하되 명시한다. 역할 자료는 workspace `.zcode/skills/story-setup/references/agent-references/`에서 읽으며 프로젝트 에이전트 디렉터리나 사용자 수준 정의를 만들지 않는다.
- `.zcode/skills/`의 Skills 14개·`.zcode/commands/`의 Commands 14개, frontmatter와 명명을 확인한다.
- `.zcode/hooks/story_zcode_hook.js`·`.zcode/hooks/story_hook_core.js`가 있고 `node --check`가 통과하는지 확인한다.
- `.zcode/config.json` JSON과 4단계 분기를 확인한다. 미설치 시 enabled·이벤트·process 경로가 템플릿과 맞아야 하며 설치 시 해당 workspace 등록 없이 사용자 훅을 유지해야 한다. 검증 통과를 위해 템플릿 훅을 다시 병합하지 않는다.
- `.zcode/skills/story-setup/references/agent-references/`가 완전하고 모든 참조 경로를 해석할 수 있는지 확인한다.
- fixture로 SessionStart·PreToolUse deny/allow·PostToolUse를 호출한다. 발견 사항이 없으면 stdout이 비고, 출력이 있으면 ZCode의 엄격한 JSON 형식인지 확인한다.

## 설치 보고 필수 안내

실제 역할 등록을 설명한다. 사용 가능하면 full/lean에서 필요한 역할로 배정하고 역할·도구가 없을 때만 전환한다. 훅은 PATH의 `node`에 의존한다. 배포 뒤 새 세션으로 프로젝트 자료를 새로 읽는다. 플러그인 역할의 모델은 주 세션을 상속하며 Claude의 역할별 inline hooks를 이식하지 않는다. 분석 보조자의 단일 파일 쓰기 범위는 역할 본문이 제약하며 강제 경로 격리를 보장하지 않는다.
