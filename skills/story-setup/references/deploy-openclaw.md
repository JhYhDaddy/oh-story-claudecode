# OpenClaw 배포

`target_cli`에 `openclaw`가 있으면 SKILL.md Phase 2에서 이 파일을 전부 읽고 순서대로 실행한다. 경로 검사·멱등 재실행·잔여물 정리·배포 표식·템플릿 자리표시자·프로젝트 지침 병합·보고는 SKILL.md의 공통 규칙을 따른다.

## 배포 목록(기계적 검사 가능)

| Source path | Target path | Owner class | Merge mode | Validation check |
|-------------|-------------|-------------|------------|------------------|
| `skills/story-setup/references/openclaw/AGENTS.md.tmpl` | `AGENTS.md` | user+managed | 관리 블록 병합 | OpenClaw story 스킬 라우팅 절 포함 |
| 저장소 `skills/{browser-cdp,story*}/` | `skills/{browser-cdp,story*}/` | 알려진 스킬명을 story-setup이 관리 | 알려진 스킬 디렉터리만 교체 | `SKILL.md` 14개 존재; OpenClaw 호환 frontmatter |
| 저장소 `skills/story-setup/references/agent-references/` | 위 행의 전체 스킬 복사에 포함; 이 행은 no-op | story-setup 관리 | 별도 복사 없음 | 모든 참조 해석 가능 |

## 에이전트 경계

**OpenClaw 첫 버전은 에이전트를 배포하지 않는다.** 스킬만 배포하며 에이전트 협업 스킬은 기존 fallback에 따라 solo/direct로 낮춰 실행한다. Claude/OpenCode 에이전트 frontmatter를 OpenClaw 에이전트로 그대로 복사하지 않는다.

## OpenClaw skills-only 배포 알고리즘

다음 순서로 프로젝트 스킬을 배포한다.

1. 저장소 현재 `skills/`에서 `SKILL.md`가 있는 모든 story 스킬 디렉터리를 읽는다(14개: `browser-cdp`와 `story*`).
2. 대상 프로젝트 `skills/{skill-name}/`에 쓴다. story-setup이 관리하는 알려진 디렉터리만 교체하고 `skills/`의 다른 사용자 디렉터리는 보존한다. 프로젝트 사본은 스킬 전체 사본이며 에이전트 참조에는 현재 표준 접두사 `skills/`만 쓴다.
3. 각 `SKILL.md`는 OpenClaw frontmatter 조건을 만족해야 한다. `name` / `description`은 한 줄 키-값, `metadata`는 `metadata.openclaw`를 포함한 한 줄 JSON 객체다.
4. `skills/story-setup/references/openclaw/AGENTS.md.tmpl`로 SKILL.md의 프로젝트 지침 병합에 따라 프로젝트 `AGENTS.md`에 쓴다(`--host openclaw`).
5. `.story-deployed`의 `target_cli`는 `openclaw` 또는 여러 호스트 조합으로, OpenClaw의 `references_dir`는 `skills/story-setup/references/agent-references`로 쓴다.
6. 설치 보고 항목은 아래 필수 안내를 따른다.

## 검증

- `AGENTS.md`에 OpenClaw story 스킬 라우팅 절이 있는지 확인한다.
- `skills/`에 14개 story 스킬 디렉터리가 있으며 각각의 `SKILL.md`에 한 줄 `name`·`description`·JSON `metadata.openclaw`가 있는지 확인한다.
- 하위 디렉터리를 포함하여 `skills/story-setup/references/agent-references/`를 소스 상대 경로와 대조한다.

## 설치 보고 필수 안내

OpenClaw 첫 버전은 skills-only다. OpenClaw 에이전트/훅을 배포하지 않으며 실행 중 강제 차단도 없다. 본문 전 개요 가드·커밋 알림·session/compact 자동 주입은 스킬 내부 소프트 제약이다. OpenClaw는 세션 시작 시 사용 가능한 스킬의 스냅샷을 만든다. 배포 후 명령/스킬이 안 보이면 새 OpenClaw 세션을 열거나 skills watcher 갱신을 기다려야 한다.
