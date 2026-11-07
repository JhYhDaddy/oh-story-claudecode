# Agent Note: story-setup 문서별 정밀 교정과 배포 맥락 확인

Status: implemented
Date: 2026-10-14
Related: [호스트별 배포 분리](../../implemented/architecture/2026-09-26-setup-by-host.md)、[조회 유형별 비교 자료 로드](../../implemented/architecture/2026-09-26-explorer-by-query-type.md)、[배포 복사 대상 식별 검사](../../implemented/bug-fix/2026-08-22-deployment-manifest-self-copy-guard.md)

## Problem

story-setup은 배포 절차, Claude 에이전트의 정식 원본, 호스트별 변환 결과, 공유 집필 자료의 복사본을 함께 관리한다. 반복 표현과 불명확한 지시어가 각 자료의 소유 관계를 가렸다. OpenCode 배포 안내는 읽기 전용 에이전트가 3개라고 했지만 chapter-extractor에는 이미 제한된 쓰기 권한이 있었다. Antigravity 생성물은 모두 agent.md라는 이름인데 검증은 name과 파일명이 같아야 한다고 했다. 참고 자료 복사 안내에도 하위 디렉터리를 포함한다는 설명이 일부 빠져 있었다.

## Decision

Markdown·템플릿 132개와 TOML 7개 모두에 문서별 5단계 정밀 교정을 적용했다. story-setup 정식 원본만 직접 수정했다. 공유 복사본은 정식 원본의 5단계 검토 증거를 재사용하고 배포 경로·프로필·호출 맥락을 확인한 뒤 유일 원본에 따라 갱신했다. 호스트별 생성물은 기존 생성기로 다시 만든 뒤 확인했다. 실제 템플릿·생성기·도우미에 맞춰 사실을 보완했으며 전문 용어·인용·명령·필드·번호·스키마·진행 검사·작가 보고 규약은 유지했다. 예산·프레임워크·확인 단계를 추가하지 않았다.

## Alternatives considered

- 배포 복사본을 각각 직접 수정: 해당 파일에서 바로 표현을 고칠 수 있다는 장점이 가장 크다. 하지만 정식 원본과 달라지고 생성기·공유 검사가 수정을 덮어쓰므로 채택하지 않았다.
- 배포 진입 문서만 교정: 범위가 작고 검증이 빠르다는 장점이 가장 크다. 하지만 에이전트 템플릿과 참고 자료도 실행에 직접 영향을 주므로 진입 문서만 명확하게 해서는 내부의 모호함을 없앨 수 없어 채택하지 않았다.

## Consequences

배포 안내와 실제 산출물의 대응 관계가 명확해지고 원본·공유·생성 관계를 추적할 수 있다. 대신 파일마다 검토 증거를 기록하고 템플릿 변경 뒤 생성기와 관련 어댑터 검사를 다시 실행해야 한다. 기존 호스트 기능과 제한은 그대로다.

## 통합 수정 사항

- 관리 파일은 매니페스트에 따라 갱신하고 사용자 설정은 관리 블록 단위로 병합한다. 배포 표식에는 성공한 대상만 기록하며 모든 대상에서 중단되면 이전 표식을 유지한다.
- OpenCode의 읽기 전용 에이전트 설명, Antigravity의 상위 디렉터리 이름 검사, ZCode의 관리 훅 이전, Reasonix 설치 원본 경로와 자리표시자 기본값을 바로잡았다.
- 프로필 목록은 표 안의 색인에서 지정한 장르 카드도 읽을 수 있도록 한다. 감정 기법의 단편 절 예시는 보존하고 long-write 정식 원본과 setup 파생본에 적용 범위를 명시했다.
- 일관성 검사는 작가가 아는 진실과 독자가 현재 아는 내용을 구분한다. 추출기의 수정·자체 검사는 입력 모드에 따라 자료 범위를 제한한다. 이전 산출물의 요약을 보완할 때는 현재 배치의 source_files를 사용하고 원문에서 드러나는 순서대로 항목을 처리한다.
- 집필자는 호출자가 준 제목을 그대로 사용한다. 설계자의 범위는 둘 중 하나를 고르도록 명시했다. 조회자는 검색된 구간과 현재 위치를 확인하며 JSON 이스케이프는 원문을 유지한다. 조사자는 8000자 미리 보기를 전문으로 취급하지 않고 실제 도구 권한에 따라 조회한다.
- 비교 자료 검색은 주요 산출물 중 하나라도 없는 경우, 문체 표본의 가용성, 장 길이 비교를 구분한다. 업그레이드 안내는 과거 버전의 사실과 현재 작업을 구분한다.
- 규칙 4개에서 대화의 기능 판단 방향과 예시 범위를 바로잡았다. 인용·명령·기계 필드·도구 권한·단계 번호는 유지했다.

## 검증

139/139개 문서에 언어·군더더기 제거·모호함 해소·사실 대조·논리의 5단계를 순서대로 적용했다. 원본 62개, 공유본 62개, 생성물 15개다. 공유 자료는 정식 원본의 증거를 재사용하며 배포 맥락을 확인했다. 짧은 명령 래퍼 26개는 규약이 이미 명확해 그대로 두었다.

OpenCode·Codex 생성물을 다시 만들어 제출했고 Antigravity는 임시 프로젝트에 생성해 검증했다. 정적 검사·번호·현재 계약·문서 예산·공유 파일·작가 보고·기록 문서·Python 호출·reference-gates 검사를 통과했다. Claude/Codex/OpenCode/Antigravity/ZCode/OpenClaw/Reasonix 7개 호스트의 어댑터, 전체 배포 회귀, 고정 버전 ClawHub 오프라인 검증도 통과했다. 새로운 실제 모델 창작이나 기본 GUI 집필 테스트는 실행하지 않았다.

## 파일별 범위

| 파일 | 원본 유형 | 5단계 | 결과 |
|---|---|---|---|
| `skills/story-setup/SKILL.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/UPGRADING.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/agent-quality.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/agent-reference-profiles.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/anti-ai-writing.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/banned-words.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/benchmark-style-load.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/character-basics.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/character-design-methods.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/character-relations.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/deslop-gates.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/dialogue-mastery.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/emotion-on-page.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/emotional-arc-design.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/format-and-structure.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/东方仙侠.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/传统玄幻.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/历史古代.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/历史脑洞.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/双男主.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/古言脑洞.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/古风世情.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/女频悬疑.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/女频种田.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/宫斗宅斗.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/年代.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/快穿.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/悬疑灵异.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/悬疑脑洞.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/战神赘婿.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/抗战谍战.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/星光璀璨.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/民国言情.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/游戏体育.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/玄幻脑洞.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/玄幻言情.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/现言脑洞.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/科幻末世.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/职场婚恋.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/西方奇幻.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/豪门总裁.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/都市修真.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/都市日常.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/都市种田.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/都市脑洞.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/都市高武.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards/青春甜宠.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-prose-cards.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/genre-readers.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/long-chapter-hooks.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/long-emotional-methods.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/long-genre-catalog.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/long-genre-mechanics.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/long-quality.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/long-reversal.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/long-suspense.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/opening-design.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/outline-conflict.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/outline-methods.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/outline-rhythm.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/plot-core-methods.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/short-chapter-hooks.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/short-emotional-methods.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/short-genre-formulas.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/short-paragraph-hooks.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/short-quality.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/short-reversal.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/style-combat-face.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/style-genre-modules.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/style-resolution.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/agent-references/writing-craft.md` | 공유본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/antigravity/rules/oh-story.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/codex/AGENTS.md.tmpl` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/codex/agents/chapter-extractor.toml` | 생성물 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/codex/agents/character-designer.toml` | 생성물 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/codex/agents/consistency-checker.toml` | 생성물 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/codex/agents/narrative-writer.toml` | 생성물 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/codex/agents/story-architect.toml` | 생성물 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/codex/agents/story-explorer.toml` | 생성물 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/codex/agents/story-researcher.toml` | 생성물 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/deploy-antigravity.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/deploy-claude-code.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/deploy-codex.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/deploy-generic.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/deploy-openclaw.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/deploy-opencode.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/deploy-reasonix.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/deploy-zcode.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/diagnostics.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/generic/AGENTS.md.tmpl` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/openclaw/AGENTS.md.tmpl` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/opencode/AGENTS.md.tmpl` | 생성물 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/opencode/agents/chapter-extractor.md` | 생성물 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/opencode/agents/character-designer.md` | 생성물 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/opencode/agents/consistency-checker.md` | 생성물 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/opencode/agents/narrative-writer.md` | 생성물 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/opencode/agents/story-architect.md` | 생성물 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/opencode/agents/story-explorer.md` | 생성물 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/opencode/agents/story-researcher.md` | 생성물 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/opencode/commands/browser-cdp.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/opencode/commands/story-cover.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/opencode/commands/story-deslop.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/opencode/commands/story-import.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/opencode/commands/story-long-analyze.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/opencode/commands/story-long-scan.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/opencode/commands/story-long-write.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/opencode/commands/story-review.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/opencode/commands/story-setup.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/opencode/commands/story-short-analyze.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/opencode/commands/story-short-scan.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/opencode/commands/story-short-write.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/opencode/commands/story.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/reasonix/AGENTS.md.tmpl` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/templates/CLAUDE.md.tmpl` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/templates/agents/chapter-extractor.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/templates/agents/character-designer.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/templates/agents/consistency-checker.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/templates/agents/narrative-writer.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/templates/agents/story-architect.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/templates/agents/story-explorer.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/templates/agents/story-researcher.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/templates/rules/story-consistency.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/templates/rules/story-format.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/templates/rules/story-narrative.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/templates/rules/story-outline.md` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/zcode/AGENTS.md.tmpl` | 원본 | 1→5 완료 | 교정본 |
| `skills/story-setup/references/zcode/commands/browser-cdp.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/zcode/commands/story-cover.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/zcode/commands/story-deslop.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/zcode/commands/story-import.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/zcode/commands/story-long-analyze.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/zcode/commands/story-long-scan.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/zcode/commands/story-long-write.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/zcode/commands/story-review.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/zcode/commands/story-setup.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/zcode/commands/story-short-analyze.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/zcode/commands/story-short-scan.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/zcode/commands/story-short-write.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |
| `skills/story-setup/references/zcode/commands/story.md` | 원본 | 1→5 완료 | 규약 명확, 유지 |

## 저장소 전체 범위

이번 13개 스킬은 총 367개 문서로, Markdown 353개·템플릿 7개·TOML 7개다. 341개를 실제 수정했고 명령 래퍼 26개는 5단계 검토 뒤 그대로 두었다. 누락한 경로는 없다. 스킬별로 연결된 PR을 따로 제출하여 아래 표의 순서대로 병합했다. 공유 원본은 한곳에서만 유지하며 복사본과 생성물도 모두 확인했다. 각 PR의 기록에는 파일별 범위 표를 남겼다.

| 스킬 | 문서 수 | PR |
|---|---:|---|
| `story-short-write` | 37 | [#472](https://github.com/zenstory-ai/oh-story-claudecode/pull/472) |
| `story-short-analyze` | 23 | [#473](https://github.com/zenstory-ai/oh-story-claudecode/pull/473) |
| `story-short-scan` | 6 | [#474](https://github.com/zenstory-ai/oh-story-claudecode/pull/474) |
| `story` | 3 | [#475](https://github.com/zenstory-ai/oh-story-claudecode/pull/475) |
| `story-cover` | 2 | [#476](https://github.com/zenstory-ai/oh-story-claudecode/pull/476) |
| `browser-cdp` | 1 | [#477](https://github.com/zenstory-ai/oh-story-claudecode/pull/477) |
| `story-import` | 15 | [#478](https://github.com/zenstory-ai/oh-story-claudecode/pull/478) |
| `story-long-analyze` | 16 | [#479](https://github.com/zenstory-ai/oh-story-claudecode/pull/479) |
| `story-long-scan` | 10 | [#480](https://github.com/zenstory-ai/oh-story-claudecode/pull/480) |
| `story-long-write` | 87 | [#481](https://github.com/zenstory-ai/oh-story-claudecode/pull/481) |
| `story-deslop` | 8 | [#482](https://github.com/zenstory-ai/oh-story-claudecode/pull/482) |
| `story-review` | 20 | [#483](https://github.com/zenstory-ai/oh-story-claudecode/pull/483) |
| `story-setup` | 139 | 이 PR |
