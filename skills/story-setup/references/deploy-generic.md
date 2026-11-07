# 일반 Web AI / 기타 에이전트 배포

`target_cli`에 `generic`가 있으면 SKILL.md Phase 2에서 이 파일을 전부 읽고 순서대로 실행한다. 경로 검사·멱등 재실행·잔여물 정리·배포 표식·템플릿 자리표시자·프로젝트 지침 병합·보고는 SKILL.md의 공통 규칙을 따른다.

## 배포 목록(기계적 검사 가능)

| Source path | Target path | Owner class | Merge mode | Validation check |
|-------------|-------------|-------------|------------|------------------|
| `skills/story-setup/references/generic/AGENTS.md.tmpl` | `AGENTS.md` | user+managed | 관리 블록 병합 | 일반 story 스킬 라우팅 절 포함 |
| 저장소 `skills/{browser-cdp,story*}/` | `skills/{browser-cdp,story*}/` | 알려진 스킬명을 story-setup이 관리 | 알려진 스킬 디렉터리만 교체 | `SKILL.md` 14개 존재; OpenClaw 호환 frontmatter |
| 저장소 `skills/story-setup/references/agent-references/` | 위 행의 전체 스킬 복사에 포함; 이 행은 no-op | story-setup 관리 | 별도 복사 없음 | 모든 참조 해석 가능 |

## 일반 Web AI / 기타 에이전트 배포 알고리즘

일반 경로는 프로젝트 파일을 읽을 수 있는 NarraFork·Web AI·맞춤 에이전트용이다. `AGENTS.md`와 프로젝트 로컬 `skills/`만 배포한다. 네이티브 훅/에이전트는 배포하지 않는다. 검사는 스킬의 소프트 제약으로, 분업은 solo/direct fallback으로 수행한다.

1. 저장소 현재 `skills/`에서 `SKILL.md`가 있는 모든 story 스킬 디렉터리(14개: `browser-cdp`와 `story*`)를 대상 프로젝트 `skills/{skill-name}/`에 복사한다. story-setup이 관리하는 알려진 스킬 디렉터리만 교체하고 다른 사용자 디렉터리는 보존한다. 프로젝트 사본은 스킬 전체 사본이며 에이전트 참조에는 현재 표준 접두사 `skills/`만 쓴다.
2. `skills/story-setup/references/generic/AGENTS.md.tmpl`로 SKILL.md의 프로젝트 지침 병합에 따라 프로젝트 `AGENTS.md`에 쓴다(`--host generic`).
3. `.story-deployed`의 `target_cli`는 `generic` 또는 여러 호스트 조합으로, generic의 `references_dir`는 `skills/story-setup/references/agent-references`로 쓴다.
4. 설치 보고 항목은 아래 필수 안내를 따른다.

## 검증

- `AGENTS.md`에 일반 story 스킬 라우팅 절이 있는지 확인한다.
- `skills/`에 14개 story 스킬 디렉터리가 있고 각각의 `SKILL.md`를 읽을 수 있는지 확인한다.
- 하위 디렉터리를 포함하여 `skills/story-setup/references/agent-references/`를 소스 상대 경로와 대조한다.

## 설치 보고 필수 안내

generic은 플랫폼 전용 훅/custom agents를 배포하지 않는다. 개요 가드·커밋 알림·session/compact 주입 같은 강제 차단과 다중 에이전트 협업은 스킬의 소프트 제약 또는 solo/direct fallback으로 수행한다.
