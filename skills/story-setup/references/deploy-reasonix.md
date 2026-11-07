# Reasonix 배포

`target_cli`에 `reasonix`가 있으면 SKILL.md Phase 2에서 이 파일을 전부 읽고 순서대로 실행한다. 경로 검사·멱등 재실행·잔여물 정리·배포 표식·템플릿 자리표시자·프로젝트 지침 병합·보고는 SKILL.md의 공통 규칙을 따른다.

## 배포 목록(기계적 검사 가능)

| Source path | Target path | Owner class | Merge mode | Validation check |
|-------------|-------------|-------------|------------|------------------|
| `skills/story-setup/references/reasonix/AGENTS.md.tmpl` | `AGENTS.md` | user+managed | 관리 블록 병합 | Reasonix story 스킬 라우팅 절과 solo/direct fallback 포함 |
| 저장소 `skills/{browser-cdp,story*}/` | `skills/{browser-cdp,story*}/` | 알려진 스킬명을 story-setup이 관리 | 알려진 스킬 디렉터리만 교체 | `SKILL.md` 14개 존재; OpenClaw 호환 frontmatter |
| 저장소 `skills/story-setup/references/agent-references/` | 위 행의 전체 스킬 복사에 포함; 이 행은 no-op | story-setup 관리 | 별도 복사 없음 | 모든 참조 해석 가능 |

## Reasonix skills-only 배포 알고리즘

Reasonix(DeepSeek-Reasonix CLI)는 현재 스킬과 `AGENTS.md`만 배포한다. Reasonix 훅/custom agents는 배포하지 않는다. 훅 I/O 계약과 하위 에이전트 동작을 검증할 실제 CLI가 없어 후속 단계로 남겼다.

1. 저장소 현재 `skills/`에서 `SKILL.md`가 있는 모든 story 스킬 디렉터리(14개: `browser-cdp`와 `story*`)를 대상 프로젝트 `skills/{skill-name}/`에 복사한다. story-setup이 관리하는 알려진 디렉터리만 교체하고 다른 사용자 디렉터리는 보존한다. 프로젝트 사본은 스킬 전체 사본이며 에이전트 참조에는 현재 표준 접두사 `skills/`만 쓴다.
2. 프로젝트 루트에 `.agents/skills → ../skills` 상대 심볼릭 링크(Codex와 공유하는 스킬 루트)를 만들어 Reasonix의 네이티브 `.agents/skills` 탐색이 스킬을 찾게 한다. 이미 `skills/`를 가리키면 유지한다. 일반 디렉터리가 차지하고 있으면 덮어쓰지 않고 설치 보고에 알린다. Windows에서 심볼릭 링크를 사용할 수 없으면 건너뛰고 설치 소스 저장소 루트의 `reasonix-plugin.json`으로 `reasonix plugin install`을 실행한다.
3. `skills/story-setup/references/reasonix/AGENTS.md.tmpl`로 SKILL.md의 프로젝트 지침 병합에 따라 프로젝트 `AGENTS.md`에 쓴다(`--host reasonix`).
4. `.story-deployed`의 `target_cli`는 `reasonix` 또는 여러 호스트 조합으로, Reasonix의 `references_dir`는 `skills/story-setup/references/agent-references`로 쓴다.
5. 설치 보고 항목은 아래 필수 안내를 따른다.

## 검증

- `AGENTS.md`에 Reasonix story 스킬 라우팅 절과 solo/direct fallback 설명이 있는지 확인한다.
- `skills/`에 14개 story 스킬 디렉터리가 있고 각 `SKILL.md`를 읽을 수 있는지 확인한다.
- 프로젝트 `.agents/skills`가 `skills/`를 가리키는 심볼릭 링크인지 확인한다(POSIX, Reasonix 네이티브 스킬 발견용). Windows에서 링크를 만들지 않았으면 설치 소스 저장소에서 루트 `reasonix-plugin.json`을 사용한 `reasonix plugin install`이 가능한지 확인한다.
- 하위 디렉터리를 포함하여 `skills/story-setup/references/agent-references/`를 소스 상대 경로와 대조한다.

## 설치 보고 필수 안내

Reasonix는 현재 skills-only이며 Reasonix 훅/custom agents를 배포하지 않는다. 본문 전 개요 가드·커밋 알림·session/compact 자동 주입은 스킬 내부 소프트 제약이고 전문 에이전트 관련 스킬은 solo/direct fallback으로 수행한다. `reasonix doctor capabilities`로 스킬 발견을 확인할 수 있다. 배포 뒤 새 스킬이 보이지 않으면 새 Reasonix 세션을 열거나 설치 소스 저장소 루트 `reasonix-plugin.json`으로 네이티브 플러그인 설치를 수행한다.
