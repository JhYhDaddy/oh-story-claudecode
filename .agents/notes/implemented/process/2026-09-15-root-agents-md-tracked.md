# Agent Note: 저장소 루트 AGENTS.md와 CLAUDE.md를 버전 관리에 포함

Status: implemented

## Problem

저장소 초기화 때부터 `.gitignore`는 루트의 `AGENTS.md`, `CLAUDE.md`, `.agents/*`를 무시했다(`.agents/skills`만 허용). 루트가 한때 story-setup의 배포·테스트 디렉터리를 겸했기 때문이다. 이 두 파일은 story-setup이 호스트별 템플릿(`references/*/AGENTS.md.tmpl`, `templates/CLAUDE.md.tmpl`)으로 사용자 집필 프로젝트에 생성하는 파일이었고 저장소 자체 개발 지침이 아니었다. 그 결과 코딩 에이전트가 저장소에 들어와도 자동으로 읽는 유지 관리자 지침이 없었다. 규칙은 `CONTRIBUTING.md`와 `scripts/README.md`의 설명 속에 흩어져 있어 에이전트에게는 사실상 규칙이 없는 것과 같았다.

## Decision

- 루트 `AGENTS.md`를 유지 관리자 개발 지침의 유일한 원본으로 삼고 git에 포함한다.
- 루트 `CLAUDE.md`는 `@AGENTS.md` 가져오기 한 줄만 담으며 두 번째 본문을 절대 따로 관리하지 않는다.
- `.gitignore`에서 `AGENTS.md`, `CLAUDE.md` 두 줄을 삭제하고 `!.agents/notes`를 추가해 에이전트 기록 트리를 버전 관리한다. `.agents/*`의 다른 무시 규칙은 유지한다.
- 루트 `AGENTS.md`에는 story-setup이 배포 완료 프로젝트를 식별하는 표시 문구를 절대 넣지 않는다. 예를 들어 ‘网文写作工具集（OpenClaw）’, ‘网文写作工具集（Reasonix）’, ‘网文写作工具集（通用 Agent / Web AI）’ 같은 제목이다(story-setup `SKILL.md` Phase 1이 이 문구로 배포 여부를 판단). 이런 표시가 있으면 story-setup이 저장소를 이미 배포된 프로젝트로 오인한다.
- 사용자 집필 프로젝트의 `AGENTS.md` / `CLAUDE.md`는 여전히 story-setup이 템플릿에서 생성·병합하며 이 결정과 무관하다.

출처: 유지 관리자 결정, 2026-09-15

## Alternatives considered

- **두 파일을 계속 무시하고 개발 지침을 `CONTRIBUTING.md`에만 두기**: 위험이 없고 story-setup이 사용자 프로젝트에 생성하는 동명 파일과 혼동하지 않는다는 점이 가장 큰 장점이다. 그러나 코딩 에이전트는 `CONTRIBUTING.md`를 자동으로 읽지 않으므로 설명 속 규칙은 사실상 없는 것과 같아 채택하지 않는다.
- **`AGENTS.md`와 `CLAUDE.md`의 본문을 각각 관리**: 호스트별로 강조점을 달리할 수 있다는 점이 가장 큰 장점이다. 그러나 내용이 반드시 어긋나며 저장소 이력의 문서 불일치 수정(예: 5498710, 7a3a12c)이 이를 보여 준다. 본문 하나와 가져오기 하나를 사용한다.

## Consequences

- **이점**: 저장소에 진입한 에이전트가 세션 시작부터 유지 관리자 규칙과 기록 진입점을 받는다. 기록 트리를 코드와 함께 커밋·검토한다.
- **비용과 알려진 한계**: 유지 관리자가 저장소 루트에서 story-setup을 실행하면 `AGENTS.md`가 수정된 것으로 표시되어 `git checkout -- AGENTS.md`로 복구해야 한다. 이를 받아들인다. 향후 story-setup이 제목 표시로 배포 상태를 판단하지 않게 되면 ‘표시 문구 금지’ 규칙도 함께 좁혀야 한다.

## 검증

`git check-ignore -v AGENTS.md CLAUDE.md .agents/notes`는 일치 항목이 없어야 하며 `grep -n '网文写作工具集（' AGENTS.md`는 출력이 없어야 한다.
