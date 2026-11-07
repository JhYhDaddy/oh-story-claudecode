# OpenCode 배포

`target_cli`에 `opencode`가 있으면 SKILL.md Phase 2에서 이 파일을 전부 읽고 순서대로 실행한다. 경로 검사·멱등 재실행·잔여물 정리·배포 표식·템플릿 자리표시자·프로젝트 지침 병합·보고는 SKILL.md의 공통 규칙을 따른다.

## 배포 선행 조건(아래 OpenCode 행보다 먼저 실행)

OpenCode 2.x만 지원한다. 1.x 플러그인 loader는 `story-hooks.ts`를 읽지 못해 로그 한 줄만 남기고 계속 실행하므로 본문 가드가 내내 없다. 1.x는 에이전트 `permissions:`도 인식하지 못해 읽기 전용 `consistency-checker`·`story-explorer`에 파일 쓰기·shell 권한을 준다. 버전 관문은 확인 실패 시 차단한다.

1. `opencode --version`을 실행하고 첫 `주.부.수정` 버전 번호를 취한다.
   - 주 버전 ≥ 2이면 계속한다.
   - 주 버전 < 2이면 OpenCode 배포만 중단하고 다른 target은 계속한다. 먼저 2.x로 갱신하도록 알린다. `npm rm -g opencode-ai` 뒤 `npm i -g @opencode/cli` 또는 `curl -fsSL https://opencode.ai/v2/install | bash`로 설치하고 story-setup을 재실행한다.
   - 명령을 사용할 수 없거나 버전을 해석하지 못해도 OpenCode 배포를 중단한다. 사용자 터미널에서 `opencode --version`을 실행하게 하고 대화에서 2.x 표시를 확인한 뒤에만 계속한다. 1.x이면 위와 같이 처리한다.
   - 중단 시 target이 opencode뿐이면 `.story-deployed`를 만들거나 갱신하지 않고 기존 값을 유지하며 `agents_version`도 높이지 않는다. OpenCode 파일도 쓰지 않는다. 여러 target이면 다른 호스트만 배포하고 저장할 `target_cli`에서 opencode를 뺀다. 설치 보고의 ‘지금 할 수 있는 것’에는 설치된 호스트만, ‘남은 할 일’에는 OpenCode 미설치와 이유(예: 구버전)를 쉬운 말로 쓴다. 업그레이드 후 재배포 때 다시 추가한다.
2. OpenCode가 `.opencode/plugins/*.ts`를 자동 발견하여 읽으므로 `opencode.json`에 등록하지 않는다. 루트 `opencode.json` / `opencode.jsonc`가 있으면 `plugin`·`plugins` 배열에서 `.opencode/plugins/story-hooks.ts`를 가리키는 과거 항목을 제거한다(2.x는 단일 파일 경로를 버리고 경고함). 빈 배열이 되면 키를 지우고 나머지는 원형 보존한다.

## 배포 목록(기계적 검사 가능)

| Source path | Target path | Owner class | Merge mode | Validation check |
|-------------|-------------|-------------|------------|------------------|
| `skills/story-setup/references/opencode/AGENTS.md.tmpl` | `AGENTS.md` | user+managed | 관리 블록 병합 | story 스킬 라우팅 절 포함 |
| `skills/story-setup/references/opencode/agents/` | `.opencode/agents/` | story-setup 관리 | replace | 에이전트 파일 7개 존재. replace 전에 아래 기존 모델 보존 절로 `model:`을 캐시하여 사용자 모델 보호 |
| `skills/story-setup/references/opencode/plugin.ts` | `.opencode/plugins/story-hooks.ts` | story-setup 관리 | replace | TypeScript 플러그인 존재 |
| `skills/story-setup/references/opencode/story_hook_core.js` | `.opencode/plugins/lib/story_hook_core.js` | story-setup 관리 | replace | Node 구문 유효, ZCode 사본과 바이트 동일, story-hooks.ts에서 import |
| `skills/story-setup/references/opencode/commands/` | `.opencode/commands/` | story-setup 관리 | replace | 명령 파일 14개 존재 |
| 저장소 `skills/story-setup/references/agent-references/` | `skills/story-setup/references/agent-references/` | story-setup 관리 | replace | 모든 참조 해석 가능 |
| `skills/story-setup/references/opencode/pre-commit.sh` | `.git/hooks/pre-commit` | user+managed | 추가 또는 생성 | 파일 존재·실행 가능. marker 블록이 있으면 내용 교체, 없으면 exit 0 위치를 감지하여 삽입 |

## 배포 단계

1. **기존 모델 설정부터 캐시한다.** 아래 모델 설정의 ‘기존 모델 설정 보존’을 먼저 수행한 뒤 2단계 replace를 한다. 먼저 덮어쓰면 사용자 모델을 잃는다.
2. `references/opencode/agents/`를 `.opencode/agents/`로 복사한다. Claude Code Markdown이 본문 원본이며 이곳은 저장소에서 미리 생성한 산출물이므로 배포는 복사만 한다.
3. `plugin.ts`를 `.opencode/plugins/story-hooks.ts`, `story_hook_core.js`를 `.opencode/plugins/lib/`, `commands/`를 `.opencode/commands/`로 복사한다. `pre-commit.sh`는 목록의 규칙대로 `.git/hooks/pre-commit`에 병합한다.
4. 에이전트 참조를 `skills/story-setup/references/agent-references/`에 복사한다. OpenCode는 현재 표준 접두사 `skills/`만 사용하고 실행 중 과거 대체 경로를 순회하지 않는다.
5. `references/opencode/AGENTS.md.tmpl`을 SKILL.md의 프로젝트 지침 병합에 따라 루트 `AGENTS.md`에 쓴다(`--host opencode`).
6. 에이전트 모델 설정의 나머지 단계를 실행한다.
7. `.story-deployed`의 `references_dir`는 `skills/story-setup/references/agent-references`로 쓴다. 여러 호스트는 쉼표로 연결한다.

## 에이전트 모델 설정

> 하위 에이전트가 모델을 지정하지 않으면 주 모델을 상속하므로 저비용 역할도 주 모델 한도를 쓴다. 이 단계는 사용자 모델을 자동 탐지하여 `model:`에 쓴다.

### 기존 모델 설정 보존(`.opencode/agents/` replace 전에 필수)

배포는 `replace`라 이전 `model:`을 덮어쓴다. **그 전에** `.opencode/agents/*.md`를 탐색하고 에이전트별 `model:`을 캐시한다(에이전트명 → 모델 ID). 후속 탐지 실패/시간 초과 또는 사용자의 특정 등급 건너뛰기에는 캐시를 복원하여 기존 저비용 모델이 주 모델로 지워지지 않게 한다. 이미 replace했고 캐시가 비었다면 새 설치로 취급하고 보고에 ‘이전 모델 설정을 보존하지 못함’을 알린다.

### 모델 목록 얻기

프로젝트 루트에서 `opencode api model.list -H "x-opencode-directory:<项目根绝对路径>"`를 우선 실행한다. JSON의 `data[]` 항목 `providerID/id`가 모델 ID, `cost[]`는 백만 token당 input/output 단가(빈 배열이면 비용 자료 없음), `limit.context`는 맥락 길이다. 실행/해석 실패 시 줄마다 `provider/model`인 일반 텍스트 `opencode models`로 전환한다. 최초 models.dev 캐시 로딩 때문에 둘 다 제한 시간 60000ms(60초)를 쓴다.

- 성공하면 모델 등급 구분으로 진행한다.
- 시간 초과면 캐시가 준비되지 않았을 수 있으므로 한 번 재시도한다. 계속 초과하면 기존 모델 캐시를 `model:`에 복원하고 자동 설정을 건너뛴 뒤 수동 설정 안내를 보고한다.
- 명령 없음·빈 출력 등 실패도 캐시 복원·자동 설정 생략·수동 설정 안내로 처리한다.

### 모델 등급 구분

**비용 우선(`model.list` 비용 자료가 있을 때)**: 실제 cost 순서로 나눈다. 저급은 최저가/무료, 중급은 중간 가격, 고급은 최고가 또는 맥락/역량이 가장 강한 모델이다. 무료 모델은 실제 cost=0으로 저급이며 **이름의 마케팅 단어로 판단하지 않는다.** 예를 들어 `nemotron-3-ultra-free`는 이름에 `ultra`가 있어도 cost=0이므로 저급이다. 비용 자료가 없는 모델도 후보에 포함하고 버리지 않는다.

**키워드 대체(`opencode models`만 있거나 cost가 없을 때)**: ID의 마지막 `/` 뒤 모델명을 `-`·`.`·`_`로 나누어 조각마다 대소문자 무시 완전 일치로 비교한다. `minimax-m3`는 `[minimax, m3]`라 `mini`·`max`에 맞지 않는다. `claude-haiku-4.5`는 `[claude, haiku, 4, 5]`로 `haiku`에 맞는다. 휴리스틱이므로 설치 보고에 `분류 근거: 키워드(heuristic)`를 표시한다.

| 등급 | 일치 키워드 | 에이전트 |
|------|-----------|-----------|
| 저급 | `haiku`, `flash`, `mini`, `nano`, `lite` | chapter-extractor, consistency-checker, story-explorer |
| 중급 | `sonnet`, `plus` | story-researcher, character-designer |
| 고급 | `opus`, `pro`, `ultra`, `max` | story-architect, narrative-writer |

- 여러 등급과 맞으면 가장 높은 등급을 취한다.
- 키워드와 하나도 맞지 않는 모델도 추가 추천 후보로 남긴다(비용 분류에서는 모두 포함). 설치 보고에 목록과 ‘직접 입력으로 사용 가능’을 알린다.
- 같은 등급에 여러 제공자가 있으면 anthropic·openai·google·deepseek 등 알려진 제공자의 모델을 먼저 제시한다.

### 등급별 대화 선택

저급 → 중급 → 고급 순으로 각 등급마다 AskUserQuestion으로 선택을 받는다. 질문에는 작가가 이해하는 역할명만 쓰고 내부 에이전트명은 기술 비고에만 둔다.

| 등급 | 작가에게 할 질문 | 기술 비고: 에이전트 |
|------|-----------|---------------------|
| 저급 | ‘분석 보조·자료 검색·교정은 찾고 대조하는 작업입니다. 어떤 모델을 쓸까요? 저렴한 모델이면 충분합니다.’ | chapter-extractor(분석 보조), story-explorer(자료 검색), consistency-checker(교정) |
| 중급 | ‘인물 설계자와 자료 연구자는 설정·자료를 정리합니다. 어떤 모델을 쓸까요?’ | character-designer(인물 설계), story-researcher(자료 연구) |
| 고급 | ‘본문 작가와 개요·작품 전체를 총괄하는 지휘자는 본문 품질을 직접 결정합니다. 어떤 모델을 쓸까요?’ | narrative-writer(본문 작가), story-architect(총괄 지휘) |

등급별 선택지 구조:

```
선택지:
  - provider/model-id
  - provider/model-id
  - 직접 입력(전체 모델 ID. 오타는 실행 때 드러남. 고급은 저급 모델 사용 시 본문 품질 저하 안내)
  - 기존 모델 유지(캐시가 있을 때만 표시)
  - 건너뛰고 주 모델 사용(저급/고급: 비용이 높을 수 있음. 중급: 주 모델 품질은 보통 충분함)
```

규칙:

- 후보는 최대 5개이며 초과하면 잘라 내고 추가 모델은 직접 입력하도록 알린다. **후보가 0개여도 모든 등급에서 AskUserQuestion을 띄운다.** 후보(있으면)·직접 입력·기존 모델 유지(그 에이전트의 model 캐시가 있을 때만)·건너뛰고 주 모델 사용을 포함한다. 0개이면 해당 경고와 미분류/등급 밖 모델을 참고 목록으로 보여 준다. 대화를 조용히 건너뛰어 직접 입력 기회를 없애지 않는다.
- `직접 입력`: 전체 `provider/model-id`를 받는다. 저장 전에 한 줄·제어 문자 없음·`^[A-Za-z0-9._-]+/[A-Za-z0-9._:+-]+$` 일치를 확인하고 아니면 재입력 또는 건너뛰기를 안내한다.
- `기존 모델 유지`: 캐시된 해당 에이전트 model을 복원한다. 건너뛰기와 다르다. 본문 작가의 캐시 모델이 이번 분류에서 저급/중급이면(구버전에서 중급 배정) 고급 질문에 ‘지난번 본문 작가는 중급 모델이었습니다. 본문에는 고급 모델을 권합니다’라고 덧붙이고 다시 선택하도록 권한다.
- `건너뛰고 주 모델 사용`: 명시적 삭제다. 해당 `model:`을 쓰지 않아 주 모델을 상속한다. 이전 설정을 유지하려면 기존 모델 유지를 선택해야 한다.
- 등급별 후보가 0개이면 질문 설명에 다음을 알린다.
  - 저급: ‘저렴한 모델을 찾지 못했습니다. 분석 보조·자료 검색·교정은 주 모델을 사용하므로 비용이 높을 수 있습니다.’
  - 중급: ‘적절한 중급 모델을 찾지 못했습니다. 인물 설계·자료 연구는 주 모델을 씁니다. 품질이 충분하면 괜찮습니다. 비용을 줄이려면 주 모델보다 못하지 않은 중급 모델을 직접 입력하거나 아래 미분류 모델에서 고르세요.’
  - 고급: ‘고급 모델을 찾지 못했습니다. 본문 작가와 총괄 지휘는 주 모델을 사용합니다.’

### model 필드 쓰기

사용자가 고른 에이전트 파일(`.opencode/agents/*.md`, 앞의 배포 2단계에서 배포함)에서 frontmatter 끝의 닫는 `---` 앞에 **들여쓰기 없는 최상위 필드** `model:`을 넣는다. `permissions:` 규칙 목록 같은 여러 줄 블록 안에 넣지 않는다. YAML 특수 문자가 있는 값은 따옴표로 감싸 frontmatter를 보존한다.

```yaml
---
description: ...
mode: subagent
permissions:
  - action: "*"
    resource: "*"
    effect: deny
  - action: read
    resource: "*"
    effect: allow
steps: 12
model: provider/model-id
---
```

- 이미 `model:`이 있으면 최상위 값을 바꾸고 중복 키를 추가하지 않는다.
- 기존 모델 유지는 캐시된 model을 복원한다.
- 건너뛰고 주 모델 사용은 `model:`을 쓰지 않는다.
- 탐지 실패/시간 초과로 이 단계에 오지 못한 등급은 캐시를 복원하여 replace가 기존 설정을 지우지 않게 한다. 복원한 본문 작가 모델이 키워드상 저급/중급이면 ‘남은 할 일’에서 고급 모델로 바꾸도록 안내한다.

## 검증

- `.opencode/agents/`에 정의 7개가 있고 frontmatter에 `mode: subagent`와 `permissions` 규칙 목록이 있는지 확인한다.
- `.opencode/plugins/story-hooks.ts` 존재를 확인한다.
- `.opencode/plugins/lib/story_hook_core.js` 존재와 `node --check` 통과를 확인한다. story-hooks.ts가 import하는 공유 본문 가드 코어이며 `.zcode` 사본과 바이트가 같다. `.opencode/plugins/*.js` 자동 발견을 피하려고 `lib/` 안에 둔다. `lib/`에 `index.*` / `server.*`는 두지 않는다.
- `.opencode/commands/`에 명령 14개가 있는지 확인한다.
- 하위 디렉터리를 포함하여 `skills/story-setup/references/agent-references/`를 소스 상대 경로와 대조한다.
- `opencode.json` / `opencode.jsonc`가 있으면 `plugin`·`plugins` 배열에 story-hooks.ts 항목이 없는지 확인한다.
- `opencode` 사용 가능 시 프로젝트 루트에서 `opencode api plugin.list -H "x-opencode-directory:<项目根绝对路径>"`를 실행하여 `id`가 `oh-story.story-hooks`인 항목의 `state.status`가 `active`인지 확인한다. 첫 요청이 빈 목록이면 몇 초 뒤 재시도한다.
- `.git/hooks/pre-commit` 존재와 실행 권한을 확인한다. Windows에서는 권한 검사를 생략한다.
- 에이전트 frontmatter를 YAML로 해석하고 설정한 `model:`이 유효한 최상위 스칼라인지 확인한다. `model:` 부분 문자열 grep만으로 대신하지 않는다.

## 설치 보고 필수 안내

- 배포 뒤 새 OpenCode 세션을 열어 에이전트·명령·플러그인을 활성화한다.
- 모델 설정을 수행했다면 배포 상세에 역할명 먼저, 내부명은 괄호로 모델 요약을 쓴다.
  ```
  에이전트 모델 설정:
    총괄 지휘(story-architect)         → <고급 모델>(provider/model-id)
    본문 작가(narrative-writer)         → <고급 모델>(provider/model-id)
    인물 설계(character-designer)       → <중급 모델>(provider/model-id)
    자료 연구(story-researcher)         → <중급 모델>(provider/model-id)
    분석 보조(chapter-extractor)        → <저급 모델>(provider/model-id)
    교정(consistency-checker)          → <저급 모델>(provider/model-id)
    자료 검색(story-explorer)           → <저급 모델>(provider/model-id)
  ```
- 자동 탐지 실패로 목록을 읽지 못했다면 ‘남은 할 일’에 쉽게 쓴다.
  <!-- author-report -->
  ```md
  이번에는 사용 가능한 모델 목록을 읽지 못했습니다. 이미 설정한 보조자는 이전 모델을 유지하고, 미설정 보조자는 주 모델을 써 비용이 높을 수 있습니다. 비용을 줄이고 싶으면 저렴한 모델명을 알려 주세요. 본문 작가와 총괄 지휘에는 가장 좋은 모델을 권합니다.
  ```
  배포 상세에는 한 줄만 남긴다. 모델은 `.opencode/agents/{agent名}.md` frontmatter의 `model:`에 있으며 사용 가능한 모델은 `opencode models`, 가격은 https://models.dev/ 참조.
