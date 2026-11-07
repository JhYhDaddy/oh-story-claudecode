# Agent Note: OpenClaw 호환을 위해 SKILL.md frontmatter를 한 줄 키·값 형식으로 유지

Status: implemented

## Problem

스킬 13개를 동일한 `skills/`에서 Claude Code·Codex·OpenCode·OpenClaw·ZCode·Reasonix가 발견해야 한다. OpenClaw / AgentSkills frontmatter 파서는 한 줄 최상위 키만 허용한다. `description: |` 블록 스칼라와 들여쓴 여러 줄 `metadata`는 OpenClaw에서 스킬 자체를 보이지 않게 한다. 그러나 스킬마다 중국어 트리거 문구 십여 개와 영어 별칭으로 구성된 긴 트리거가 있어 자연스럽게 블록 스칼라를 쓰기 쉽다.

## Decision

- 모든 `SKILL.md` frontmatter의 최상위 키는 반드시 한 줄이어야 한다. `name`, `description`은 따옴표 문자열이며 `|` / `>` 블록을 쓰지 않는다. `metadata`는 `metadata.openclaw`를 포함하는 한 줄 JSON 객체다(최소 `source`, 선택적으로 `requires.bins/env/config/anyBins`를 사용해 OpenClaw 로드 시점 조건 검사 가능. 예: `story-cover`의 `GPT_IMAGE_API_KEY`로 표시 여부 제어).
- 트리거는 모두 `description`에 유지하고 형식만 한 줄로 만든다. 한 줄로 만들기 위해 트리거를 삭제하지 않으며 더 긴 트리거 설명은 본문에 둔다.
- 기준 원본은 저장소 루트의 `skills/` 하나뿐이다. OpenClaw 전용 두 번째 스킬이나 미러 패키지를 관리하지 않는다. OpenClaw는 작업 공간 `skills/`를 기본 검색하며 `.agents/skills` symlink에 의존하지 않는다. `story-setup target_cli=openclaw`는 프로젝트 `skills/`와 `references/openclaw/AGENTS.md.tmpl`만 배포하며 agents / hooks / plugin은 배포하지 않는다.
- 검사: CI 필수인 `scripts/check-openclaw-skills.sh`가 들여쓴 행·블록 스칼라·JSON이 아닌 `metadata`를 거부하고 스킬이 정확히 13개인지 확인한다. `OPENCLAW_REAL_CHECK=1`이면 임시 profile·작업 공간으로 격리 에이전트를 만들고 실제 CLI가 스킬 13개를 찾는지 확인한 뒤 정리한다.
- 예외: OpenClaw는 세션 시작 시 조건에 맞는 스킬을 스냅샷하므로 변경 후에는 새 세션을 시작하거나 skills watcher 갱신을 기다려야 한다. 이는 런타임 동작으로 저장소가 통제할 수 없다.

출처: 8d08e23 (#186), 398795d (#189)

## Alternatives considered

- **OpenClaw용 호환 사본을 별도로 생성하거나 plugin 패키지 게시**: 주 `SKILL.md`의 읽기 쉬운 여러 줄 description을 유지하고 OpenClaw 전용 필드가 다른 호스트에 섞이지 않는다는 장점이 있다. 그러나 8d08e23은 ‘plugin 실물 패키지·미러를 도입하지 않고 기준 스킬은 루트 skills/ 하나만 둔다’고 명시했다. 두 번째 사본은 반드시 어긋나며 저장소는 이미 참조 사본 동기화에 `check-shared-files` 비용을 치르고 있다. [스킬 간 사본 기록](../architecture/2026-05-07-cross-skill-copies-not-symlinks.md) 참조.
- **한 줄로 바꾸면서 트리거도 줄이기**: 한 줄이 수백 자면 읽기 어렵다는 장점이 있다. 그러나 트리거는 각 호스트의 호출 적중률을 결정하며 8d08e23은 ‘모든 트리거를 유지하고 형식만 한 줄로 바꾼다’고 명시했다.
- **블록 스칼라 형식**은 대체된 옛 방식이다(8d08e23 이전에는 여러 줄 `description: |`, 들여쓴 YAML `metadata:`).

## Consequences

- **이점**: `skills/` 하나를 여섯 호스트가 발견하고 CI가 PR 단계에서 형식 회귀를 막으므로 실제 장비 검증까지 기다릴 필요가 없다.
- **비용과 알려진 한계**: `description` 한 줄이 매우 길어 읽기 어렵고 한 부분을 고쳐도 diff에서 전체 줄이 바뀐다. 향후 `metadata`가 커져도 한 줄 JSON에 넣어야 한다. OpenClaw 상위 프로젝트가 블록 스칼라 파싱을 허용하면 ‘한 줄’ 제약을 재검토할 수 있지만 ‘기준 원본 하나’ 원칙은 바뀌지 않는다.

## 검증

`bash scripts/check-openclaw-skills.sh`; 로컬에 openclaw가 설치되어 있으면 `OPENCLAW_REAL_CHECK=1 bash scripts/check-openclaw-skills.sh`.
