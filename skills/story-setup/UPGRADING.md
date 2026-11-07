# 업그레이드 안내

## 当前版本

현재 도우미 버전은 38(v0.9.2)이다. 기존 프로젝트는 스킬 묶음을 갱신한 후 프로젝트 루트에서 `/story-setup`을 다시 실행한다(Codex는 `$story-setup`, Antigravity는 `/skills` 또는 직접 이름 지정). 이후 새 세션을 연다. 위 절명과 아래 버전 키는 검사 계약 원형이다.

- `setup_skill_version: 1.3.6`
- `agents_version: 38`

`.story-deployed` 필드가 불완전하거나 `agents_version`이 정수가 아니거나 38 미만이면 갱신 대상이다. story-setup을 다시 실행하면 된다. 프로젝트의 `agents_version`이 38보다 크면 로컬 스킬 묶음이 더 오래된 것이다. oh-story-claudecode부터 갱신하고 옛 묶음으로 덮어쓰지 않는다. 버전별 변경은 저장소 루트 `CHANGELOG.md`를 본다.

## 업그레이드 순서

1. 스킬 묶음을 갱신한다. 명령행 설치는 `npx skills add zenstory-ai/oh-story-claudecode -y -g`를 다시 실행하고, 플러그인 마켓이나 Plugin Management 설치는 패널에서 갱신한다.
2. 집필 프로젝트 루트에서 `/story-setup`을 다시 실행한다(Codex는 `$story-setup`).
3. 새 세션을 열어 새 도우미와 hook을 적용한다. Codex가 hook 신뢰를 요구하면 `/hooks`에서 신뢰한다.
4. 집필 중인 장편은 각 책에 `추적/_tracking-state.json`이 있는지 확인한다. 없으면 아래 ‘추적 모델 이관’에 따라 재구축한다. 그렇지 않으면 다음 장 집필이 차단된다.
5. 분석 산출물이나 상세 개요가 현재 형식에 맞지 않으면 검사 안내에 따라 해당 부분을 보충한다. 한 항목의 누락 때문에 전체 작품을 재분석하지 않는다.

## 이번 갱신은 story-setup 재실행 필수(v0.9.2, 도우미 버전 38)

- 출판 자료 스킬 `story-publish`가 추가됐다. story-setup을 다시 실행해야 프로젝트에 스킬(OpenClaw·Reasonix·일반 모드는 프로젝트 `skills/`로 복사), 프로젝트 지침의 출판 자료 진입점, OpenCode·ZCode의 `/story-publish` 명령이 생긴다.
- 원고·설정·추적·작가 기억은 이관할 필요가 없다.

## v0.9.1 업그레이드 설명(도우미 버전 37)

- 스킬 묶음 갱신 후 story-setup을 다시 실행하고 새 세션을 열어 새 도우미와 hook을 적용한다.
- ZCode는 `oh-story` 플러그인을 먼저 갱신하고 활성화한다. **갱신된 플러그인 사본**에서 story-setup을 실행해 프로젝트 `.zcode/skills` 스냅샷을 덮어쓴다. 프로젝트의 옛 story-setup으로 재배포하지 않는다. 독립 설치한 Skills는 플러그인 역할을 등록하지 않는다.
- ZCode가 여전히 프로젝트의 옛 스냅샷을 찾으면 관리 디렉터리 `.zcode/skills/story-setup`을 `.zcode/skills` 밖으로 옮겨 백업한 뒤 새 플러그인에서 story-setup을 실행한다. 배포 완료 후 새 버전이 이 디렉터리를 다시 만든다. 다른 프로젝트 Skills를 지울 필요는 없다.
- Windows는 재실행 시 프로젝트 hook을 갱신해 옛 진입점을 계속 쓰지 않게 한다.

## v0.9.0 업그레이드 설명(도우미 버전 36)

- 집필자·구조 설계자·인물 설계자·일관성 검사자·자료 조회자·연구자 템플릿이 모두 바뀌었다. 개요·도입·인물·장르·감정 방법을 사용 시점별로 재정리하고 중복되거나 오래된 자료를 삭제했다. 집필 기법과 AI 느낌 제거 방법도 맞췄다. 재실행하지 않으면 옛 도우미가 삭제된 자료를 찾는다.
- 프로젝트 지침(`CLAUDE.md`·`AGENTS.md`)은 도구마다 `<!-- oh-story:{工具} 开始`부터 `<!-- oh-story:{工具} 结束 -->`까지의 관리 블록을 쓴다. 첫 재실행은 옛 oh-story 문단을 관리 블록으로 바꾸고 직접 작성한 문단은 밖에 둔다. 이후에는 블록 안만 교체한다. 여러 도구가 `AGENTS.md`를 공유해도 각자 블록을 써 서로 덮어쓰지 않는다.
- Claude Code의 `.claude/rules/`에서 집필 흐름과 충돌하는 고정 항목(장 시작/끝 훅의 고정 유형, 매 장 감정 변화 필수, 고정 문단/글자 수 경계)을 없앴다. 권 개요·상세 개요 필드는 집필 워크플로 템플릿을 기준으로 하며 옛 상세 개요의 필드 누락은 계속 차단하지 않는다.
- 일관성 검사자와 자료 조회자도 단편 프로젝트(`설정.md`·`구간개요.md`·`본문.md`)를 처리한다. 연구자는 브라우저 디버깅 포트가 닫혀 있으면 주 세션에 돌려보내고 주 세션이 사용자에게 브라우저 실행 여부를 묻는다.
- 원고·설정·개요·추적·작가 기억의 데이터 형식은 같으므로 이관하지 않는다.
- 이전에 가져온 장편의 권 개요는 줄거리 단위가 표여서 본문 집필 시 단위별로 읽을 수 없다. 새 장 이어쓰기는 영향이 없다. 제N장 집필 전에 새 단위를 카드 형식으로 보충한다. 가져온 옛 장을 다시 쓰려면 `/story-long-write`로 해당 권의 옛 단위를 먼저 단위 카드로 바꾼다.

## v0.8.5 및 이전 버전에서 갱신

story-setup 한 번으로 현재 버전을 설치하며 중간 버전을 차례로 거칠 필요는 없다. 집필 중 만날 변화는 다음과 같다.

- 장편 집필 후 검사는 Node.js 18+가 필요하다. 없으면 장을 제출할 수 없으므로 설치 후 다시 검사한다. 장편 분석은 Python 3이 필요하다.
- 이미 제출한 장의 수정은 먼저 해당 장의 수정 초안을 만들고 제출한다. 추적 파일을 직접 고치지 않는다.
- 상세 개요에 ‘字数范围：2000-2600’ 한 줄로 지정 범위를 넣을 수 있다. 없으면 기본값을 중심으로 조정한다. 옛 상세 개요·권 개요도 계속 쓰며 개요 작성 시 새 형식을 보충한다.
- 본문 집필 전 상세 개요가 빈 껍데기여서는 안 된다. `#`와 공백을 제외하고 30자 미만이면 차단한다. `<!-- 去味:跳过 -->`가 있는 장은 그 표식 때문에 문제로 보지 않는다.
- 순위 조사는 매번 새 `순위조사/{日期}/` 디렉터리에 쓰며 옛 디렉터리는 그대로 둔다.
- 코딩 도구를 바꾸고 story-setup을 다시 실행하면 현재 도구도 함께 설치할지 묻는다.
- 프로젝트의 옛 `.claude/agent-memory/`는 더 이상 쓰지 않으므로 삭제할 수 있다.

## OpenCode는 2.x만 지원(v0.7.11)

OpenCode 2.0부터 npm 패키지는 `@opencode/cli`이며 `opencode-ai`는 1.x에 머물렀다. 이 어댑터는 2.x만 지원한다. 1.x 플러그인 loader는 새 `story-hooks.ts`를 읽지 못해 본문 집필 전 보호와 집필 후 보완 검사가 없다. 1.x는 agents의 `permissions:` 규칙도 인식하지 못해 읽기 전용 agent의 권한 제한이 사라진다. story-setup은 1.x이거나 버전을 확인할 수 없으면 배포를 멈춘다.

1. OpenCode 갱신: `npm rm -g opencode-ai`로 옛 패키지를 먼저 제거하고 `npm i -g @opencode/cli`(또는 `curl -fsSL https://opencode.ai/v2/install | bash`)를 실행한다. `opencode --version`이 2.x인지 확인한다. 두 패키지 모두 `opencode` 명령을 제공하므로 먼저 제거하지 않으면 PATH에 1.x가 남을 수 있다.
2. 스킬 묶음 갱신 후 프로젝트 루트에서 story-setup을 다시 실행한다. `.opencode/plugins/story-hooks.ts`와 `.opencode/agents/`를 교체한다(2.x 네이티브 `permissions:` 규칙 목록으로 전환하며 기존 `model:`은 보존). `opencode.json` / `opencode.jsonc`의 옛 story-hooks 플러그인 등록도 제거한다.

## 플러그인 패키지 식별자 이관(v0.7.9 동일 버전 수정)

Claude Code / ZCode 마켓은 단일 `oh-story` 플러그인으로 바뀌며 당시의 13개 Skills를 모두 포함한다. v0.7.9의 동일 버전 수정에서 시작한 이관으로, 옛 식별자를 쓰는 사용자는 수동 이관이 필요하다. `npx skills` 설치는 필요 없다. 제거 전 보존할 플러그인 데이터를 백업한다. 아래 작업은 옛 플러그인 기록에만 적용하며 집필 프로젝트와 story-setup 배포 파일은 보존한다.

### Claude Code

1. 영향받는 집필 프로젝트에서 설치 플러그인을 나열하고 기록의 `id`와 `scope`로 실제 옛 식별자를 확인한다. `project` / `local`은 각각의 프로젝트 기록이므로 여러 프로젝트면 따로 확인한다.

   ```bash
   claude plugin list --json
   ```

   목록에 실제 존재하고 marketplace가 `oh-story-skills`인 다음 옛 ID만 처리한다.

   ```text
   browser-cdp@oh-story-skills
   story@oh-story-skills
   story-cover@oh-story-skills
   story-deslop@oh-story-skills
   story-import@oh-story-skills
   story-long-analyze@oh-story-skills
   story-long-scan@oh-story-skills
   story-long-write@oh-story-skills
   story-review@oh-story-skills
   story-setup@oh-story-skills
   story-short-analyze@oh-story-skills
   story-short-scan@oh-story-skills
   story-short-write@oh-story-skills
   ```

2. **catalog 갱신 전**, 실제 존재하는 옛 ID를 하나씩 제거한다. 목록의 원래 `user`·`project`·`local` scope를 쓴다. 아래는 user scope의 `story` 예다.

   ```bash
   claude plugin uninstall story@oh-story-skills --scope user --keep-data
   ```

   `--keep-data`는 옛 식별자의 데이터를 보존하지만 새 `oh-story` 식별자로 이관하지는 않는다. 같은 옛 ID가 여러 scope에 있으면 각각 실행한다.

3. 실제 옛 식별자를 모두 제거한 뒤 기존 catalog를 갱신한다. 로컬에 아직 없다면 저장소를 추가한다.

   ```bash
   claude plugin marketplace update oh-story-skills
   # catalog가 아직 없을 때만:
   claude plugin marketplace add https://github.com/zenstory-ai/oh-story-claudecode
   ```

4. 원래 scope에 통합 bundle을 설치한다. scope가 여러 개면 각각 설치한다.

   ```bash
   claude plugin install oh-story@oh-story-skills --scope user
   ```

5. 새 Claude Code 세션에서 `/oh-story:story-setup` 또는 `/oh-story:story dashboard`를 쓴다. 명령과 manifest 형식은 [Claude Code 플러그인 참조](https://code.claude.com/docs/en/plugins-reference)를 본다.

### ZCode

Plugin Management에서 영향받는 옛 항목을 제거하고 마켓을 새로 고친다. 필요하면 저장소를 다시 추가하고 `oh-story` 하나를 설치한다. 중복 설치를 피하도록 화면의 마켓 이름(`oh-story-skills` 또는 `oh-story-zcode`)을 그대로 쓴다. 제거할 수 없으면 데이터 백업을 보존하고 ZCode 버전과 화면 증상을 첨부해 공식 지원에 문의한다. 전체 캐시를 비우거나 캐시 JSON을 손으로 고치지 않는다. [ZCode 플러그인 문서](https://zcode.z.ai/en/docs/plugin)를 참고한다.

## 프로젝트에 생긴 중첩 디렉터리

옛 배포는 `agent-references/agent-references/`(여러 겹일 수 있음) 또는 `skills/story-setup/skills/`를 남길 수 있으며 심하면 디스크를 채운다. 새 배포는 이런 복사를 거부하고 잔여 디렉터리를 자동 제거한다.

OpenClaw·Reasonix·일반 모드는 프로젝트 `skills/`에 스킬을 두므로 재실행해도 옛 스킬이 실행되어 자동 정리할 수 없다. 위 두 종류를 수동 삭제한 뒤 갱신한 스킬 묶음으로 프로젝트 `skills/`의 14개 디렉터리를 덮어쓴다.

## 추적 모델 이관(v0.7.2 및 이전 장편 프로젝트 필독)

장편 추적은 `추적/_tracking-state.json`을 기준으로 집필 워크플로의 제출 도구가 통일해 쓴다. 이어쓰기 상태 카드·장별 기록·인물 스냅샷·복선표·두 시간선 모두 도구가 통째로 생성하며 손으로 고치지 않는다.

판단과 결과:

| 상황 | 결과 |
|------|------|
| `추적/_tracking-state.json`이 있고 `check` 통과 | 정상, 처리 불필요 |
| `_tracking-state.json`은 없으나 본문이 있음 | 일일 집필 중단. Claude Code·Codex·OpenCode·ZCode·Antigravity는 hook이 본문 쓰기를 직접 차단하고 다른 도구는 집필 워크플로가 멈춘다 |
| 존재하나 파생 뷰를 수동 수정함 | `check`가 `derived view differs from _tracking-state.json` 보고 |

이관에 **전체 작품 재분석은 필요 없다**. 본문·`설정/`·`개요/`·`작품분석실/`는 영향받지 않고 `추적/`만 재구축한다. `/story-import`의 옛 추적 프로젝트 이관을 실행한다. 마지막 완결 장 번호 `N`을 세고 옛 추적 파일과 최근 몇 장 본문으로 현재 상태를 재구축한다. `last_chapter=N` 초기화 트랜잭션을 만들어 `tracking_commit.py init`을 실행한다. 옛 추적 구조는 원형 그대로 `추적/_이전추적보관/`에 통째로 옮기며 삭제하거나 파싱하지 않는다.

퇴역 구조: `_tracking-meta.json`·`시간선/사건목록.json` 및 더 오래된 추적 파일은 더 이상 파싱하지 않는다. `commit`·`check`는 발견 즉시 거부한다.

이후 추적은 집필 워크플로로만 제출한다. 생성 파일을 수동 수정했다면 해당 장의 수정 제출로 통째로 재구축한다.

## 작가 기억의 두 단계 저장 이관(v0.7.11 이전 프로젝트)

작가 기억은 작업 공간당 하나에서 두 단계로 바뀐다. 작업 공간 `.story/작가기억/`에는 전역·장르·절차 항목(번호 `AP`)만 두고, 각 책의 `.story/작가기억/`에는 해당 책 항목(번호 `BP`)을 둬 책과 함께 보관·이관한다. 반복 수정이나 완성 원고에서 취향을 추정하지도 않는다. `record`는 `repeated_correction` / `inferred_pattern` 출처를 거부하지만 기존 항목은 계속 읽기·확인·퇴역 처리할 수 있다.

아래 명령의 `{所用写作 skill 根}`은 `story-long-write` 또는 `story-short-write` 설치 디렉터리다.

1. 새 작품별 취향은 `--book-root {书目录}`를 전달해야 쓸 수 있다. 옛 스킬 사본에 이 인자가 없으면 오류가 나므로 `/story-setup`을 다시 실행해 스크립트와 문서의 버전을 맞춘다.
2. 갱신 전 작업 공간에 쓴 작품별 항목은 책 디렉터리로 옮길 때까지 **`query`가 반환하지 않는다**. 전역·장르·절차 항목은 영향 없다. 해당 항목은 작업 공간의 `작가프로필.md`에서 여전히 볼 수 있다.
3. 책마다 한 번 실행하면 일괄 이동한다. 멱등적이며 중간 실패 시 그대로 다시 실행한다.

   ```text
   {PYTHON} {所用写作 skill 根}/scripts/author_memory_commit.py migrate --workspace {工作区} --book-root {工作区}/장편/{书名}
   ```

   단정 내용·발언 원문 증거·확인 횟수·중요도는 그대로 보존한다. 전역 항목과 충돌하는 후보는 이관 후 확인 대기로 돌린다. 에이전트에게 ‘작가 기억 정리’를 요청해도 이관이 기본 제안 항목에 포함된다.

**단일 책 배치**(`본문/`·`추적/`이 작업 공간 루트 바로 아래): 책별 데이터는 `{工作区}/.story/작가기억/书级/`에 저장한다. 이관 시 `--book-root`에 작업 공간 자체를 전달한다.

   ```text
   {PYTHON} {所用写作 skill 根}/scripts/author_memory_commit.py migrate --workspace {工作区} --book-root {工作区}
   ```

책 이름은 기본적으로 기존 작품별 항목에서 가져온다. 여러 책의 항목이 있으면 `--book {书名}`으로 지정한다. main의 사전 배포판을 써서 조회 시 `project-level state must not carry state.book`이 나는 작업 공간은 아무 명령에 `--book-root {工作区}`를 붙여 실행하면 항목 손실 없이 자동 복구된다.

## 장편 분석의 옛 산출물(v0.7.10 및 이전 분석 작품)

- v0.7.10 이전 분석 라이브러리는 원문이 서문/프롤로그로 시작하면 재개 전에 멈추고 묻는다. 옛 버전은 프롤로그를 인식하지 못해 바로 재개하면 장 번호가 하나 어긋난다. 앞 3장까지만 분석한 라이브러리는 ‘프롤로그를 별도 장으로 재분석’이 가장 저렴하다. 장별 요약이 있으면 ‘프롤로그를 첫 장에 합쳐 옛 장 번호로 계속’을 권한다.
- `작품분석보고서.md` 절 구조가 바뀌었다. ‘质量评估’(품질 평가)는 삭제되고 ‘证据边界与待核事项’(증거 경계와 확인 대기)은 ‘还不确定的地方’(아직 불확실한 곳)로 바뀐다. 옛 보고서는 자동 재작성하지 않으며 Stage 5 재실행 시 적용된다.
- 인물 관계도는 `인물관계도/인물관계도.md`로 바뀐다. 텍스트 목록은 중국어를 보존하고 Mermaid 지원 뷰어는 관계도를 표시한다. 중국어 글꼴이 있으면 PNG도 출력한다. 이전 병음판 PNG는 자동 삭제하지 않으며 수동 삭제 가능하다.
- 분석 진행 파일 `_progress.md`는 `schema_version: 2`만 인식한다. 더 오래된 진행 파일로는 재개할 수 없으며 안내대로 처음부터 분석한다.

## 가져온 프로젝트의 자기 작품 비교 등록 정리

옛 `story-import`는 작가 자신의 가져온 책을 `비교작품/{当前书名}/`로 잘못 만들거나 해당 책 설정을 ‘주 비교 작품’으로 등록했을 수 있다. 갱신은 사용자 파일을 자동 삭제하지 않는다. 다음 경계에 따라 수동 확인한다.

1. `작품분석실/{导入书名}/`는 보존한다. 해당 책의 가져오기 분석·프로젝트 재구축 데이터 소스이며 잘못된 디렉터리가 아니다.
2. 프로젝트 루트 `설정/`를 정식 설정으로 삼는다. `비교작품/{当前书名}/`가 해당 책의 `설정/`나 `작품분석실/{导入书名}/`에서 복사됐을 뿐이고 수동 보충이 없음을 확인한 경우에만 잘못 만든 디렉터리를 삭제한다.
3. `설정/소재방향.md`에서 현재 책을 주/보조 비교 작품으로 등록한 필드를 정리한다. 실제 외부 비교 작품 등록은 그대로 둔다.
4. `비교작품/{外部书名}/` 이름은 외부 작품처럼 보여도 내용이 현재 책에서 왔다면 잘못된 뷰를 삭제하고 진짜 `작품분석실/{对标书名}/`에서 다시 동기화한다. 이름만 바꿔 수리한 척하지 않는다.
5. `/story-setup`(Codex는 `$story-setup`)을 다시 실행하고 새 세션을 열어 현재 도우미 템플릿을 적용한다.
