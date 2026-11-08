<a id="scripts--仓库开发脚本索引"></a>
# scripts/ —— 저장소 개발 스크립트 인덱스

이 파일들은 스킬 묶음 자체를 개발하는 **검사·테스트·코드 생성** 스크립트입니다. 스킬 실행용 스크립트는 각 스킬의 `scripts/` 아래(예: `story-deslop/scripts/check-ai-patterns.js`)에 있으며 스킬 간 바이트 단위로 동기화합니다.

- 대부분의 경우 CI가 자동으로 해당 작업을 수행합니다(`.github/workflows/cross-platform.yml`). 제출하기 전에 완전한 로컬 검증 절차는 [CONTRIBUTING.md](../CONTRIBUTING.md)의 “CI 검사” 항목을 참조하십시오.
- **이름을 변경하거나 스크립트의 위치를 옮길 경우**, `.github/workflows/*.yml`, `CONTRIBUTING.md`, 이 파일 자체뿐만 아니라 이를 호출하는 관련 스크립트들도 모두 동기화하여 수정해야 합니다(아래 ‘언제 실행할 것인가’에서 설명된 호출 관계를 참조하십시오).

`python scripts/test-writer-pipeline.py`는 장편 구간 추출기와 프롬프트 조립기의 공개 CLI를 검증합니다. 기존 권별 개요, 적용 범위, 해제된 이력, 기본 경로, 필수 자료, 참조 회상 축소 단계를 포함하며 세 플랫폼 CI에서 실행합니다.

`python scripts/test-long-analyze-runtime.py`는 장편 분석의 단일 상태 실행을 검증합니다. 기계적 장 색인·장별 해시, 기존 산출물 식별, 읽기 전용 계획, 범위별 배치, 호환 요약 뷰, 인접 분리, 원자적 커밋, 캐시 복구를 포함합니다. 실제 실행은 `skills/story-long-analyze/scripts/`의 `build_chapter_index.py`, `inspect_existing_assets.py`, `manage_analysis_run.py` 세 스크립트만 사용합니다. 이전 장 경계 표를 가진 자료에서 서장을 만났을 때의 장 번호 대조·병합 경로, Windows/GBK 콘솔의 UTF-8 출력, 중국어 글꼴이 없을 때 `render_relation_chart.py`가 병음 이미지 대신 Markdown 관계도만 쓰는 동작도 검사합니다.

`scripts/bench/`는 v0.8부터 사용하는 실제 세션 벤치마크입니다. 특정 버전 패키지를 결정적으로 배포하고 고정한 작품을 실제 CLI로 집필하여 장별 시간·토큰·본문 지표를 계산합니다. 실제 모델·인증 정보가 필요해 CI에서는 실행하지 않습니다. [bench/README.md](bench/README.md)를 참조하세요.

<a id="静态守卫check-"></a>
## 정적 검사기(check-*)

| 스크립트 | 검사 대상 | 실행 시점 |
|---|---|---|
| `static-check.sh` + `static-check.py` | 프런트매터·Markdown 경로와 앵커·에이전트 참조·참고 자료 도달 경로를 구조적으로 검증. 기본 구성 요소 `browser-cdp` 외에는 스킬 간 파일 참조 금지 | CI |
| `skill-numbering.py check` | 워크플로 Step/Phase/Stage 번호 정책, 참조 연결, SKILL.md의 이름 없는 번호·소수점 하위 단계 검사 | CI; 워크플로우 구조를 변경한 후 |
| `check-current-skill-contracts.sh` + `.py` + `current-contract.json` | 구조화된 매니페스트로 현재 버전·Phase·스키마·주요 산출물·상세 개요 계약 검증. 과거 경로 검사를 유지하고 주요 산출물 누락 뒤 알리지 않는 대체를 차단. 단편 집필·AI 문체 제거의 대체 실행·버전 안내 원문은 기술 참고 줄에만 허용 | CI |
| `check-shared-files.sh` | 두 매니페스트로 런타임·참조 복사본을 검증하고 미등록 완전·유사 복제본을 차단하며 초기 설정 프로필 계약·소비 경로 확인 | CI |
| `check-reference-similarity.py` | 스킬 간 Markdown의 행 단위 Jaccard/포함 유사도 검사. 유사도가 높은 파생 관계는 `shared-references.json`의 `derived_groups`에 원본과 분화 이유를 명시해야 함 | CI(check-shared-files에 의해 호출됨) |
| `check-agent-reference-consumers.py` | 배포 자료 참조의 전체 접두사와 파일·줄 번호, 참조 도달 경로, 단일 프로필 목록, 장편·단편 소유권, story-architect의 중복 목록 부재를 검사. 실제 읽기 행동을 입증하지는 않음 | CI(check-shared-files에 의해 호출됨) |
| `check-short-analysis-scope.py` | 단편 분석이 원문 관찰 기준만 연결하도록 보장. 과거 혼합 매뉴얼, 장편 구조 명령, 권장 비율의 재유입 차단 | CI(check-shared-files에 의해 호출됨) |
| `check-scan-runtime-policy.sh` | 수집 파일명의 로컬 날짜 도우미 의존과 CDP 탐지·Windows 수신 포트 해석의 소스 정책 검사 | CI; 이러한 의존 관계는 격리 도구를 사용한 테스트로는 확인할 수 없습니다. |
| `check-story-setup-deployment.sh` | story-setup 배포·런타임 회귀 테스트. 느리며 2분 이상 소요 | CI |
| `check-doc-budget.sh` + `doc-budget.json` | 자주 읽는 SKILL/references/에이전트 템플릿의 공백 제외 글자 수와 경로별 총량 검사. 호출당 절대 상한 35K(`path_ceiling`, 예외는 `exempt`에 사유 기록). `agent` 경로는 역할별 실제 로드량을 계산하며 템플릿이 미리 읽는 스킬도 자동 합산. `文件#小节`은 해당 절만, `generated`는 묶음 생성 스크립트의 결과를 계수. `branches`는 기본적으로 상호 배타적이며 동시 발생 조합은 `stacking`에 등록해 최악의 합계 계산. 초과하면 같은 분량의 기존 글을 줄이거나 절차를 조정하거나 예산을 명시적으로 증액 | CI; 자주 로드되는 경로 본문 뒤에 추가/삭제하기 |
| `check-hook-regex-sync.sh` | `detect-story-gaps.sh`의 복선 상태 탐지. 유해 구문·보완 검사망의 정규식과 상수 표를 JS↔Python 파싱 후 항목별 비교(플래그·한쪽에 추가된 상수 포함). 내장 변이 검사로 한쪽 분기 추가·플래그 변경이 실패하는지 확인 | CI |
| `check-hook-locale-safety.sh` | Windows 중국어 GBK 로캘에 배포한 훅의 바이트 안전성 | CI |
| `check-python-invocation.sh` | 스킬 문서의 `python3` 직접 호출 금지. python3→python→py 순서로 탐색해야 함 | CI |
| `check-agent-notes.py` + `test-agent-notes.py` | `.agents/notes/`: 결정 내용을 기록하는 노트의 디렉터리 구조(상태/분류/날짜 및 파일명); `Status`: 디렉터리 구조와 일치하며 반드시 포함되어야 할 항목들(문제점/결정 사항 또는 제안 사항/고려된 대안들/그에 따른 결과들); 수동으로 인덱스를 생성하는 것은 금지됨; ‘test’ 모드에서는 임시 디렉터리를 사용하여 각 카테고리별로 위반 사항을 확인함. | CI; 노트를 추가하거나 이동시킨 후 |
| `check-author-reports.py` | `<!-- author-report -->`로 표시된 작가의 보고서 템플릿에는 엔지니어링 전문 용어들, 즉 내부 필드명/상태명, 스크립트 이름, flag, snake/kebab 식별자, S1–S4, Gate, 숫자만으로 이루어진 명칭 등이 포함되어서는 안 됩니다. 블록의 마지막 줄에 기재된 “기술적 참고 사항:”은 이 규칙의 예외입니다. 등록된 파일(장문 계획서, 개별 챕터, 매일 업데이트되는 내용, 대대적인 수정이 필요한 템플릿 포함)의 보고 블록은 등록된 내용의 수보다 적어서는 안 됩니다. `--self-test`은 예시와 반예시를 함께 제공합니다. | CI; 보고서 템플릿을 수정한 후 |
| `check-plugin-packaging.py` | Claude/ZCode 카탈로그 2개와 기본 매니페스트 2개의 단일 번들 식별 정보·버전·기본 구성 요소 탐색·루트 스킬 14개 검사 | CI; 플러그인 패키징 방식을 변경한 후 |
| `check-claude-adapter.sh` | Claude 마켓플레이스·루트 플러그인 매니페스트·스킬 14개 자동 탐색 검사. 실제 CLI 생명주기 검사는 선택 사항 | CI(정적); `CLAUDE_REAL_CHECK=1`(실제 CLI) |
| `check-opencode-adapter.sh` | OpenCode 2.x 어댑터 동기화·명령과 에이전트 구조·생성된 권한의 2.x 판정 행렬·플러그인 동작 회귀 | CI + 동기화 CI(sync-opencode.py 조정) |
| `check-openclaw-skills.sh` | OpenClaw 에이전트스킬/프런트매터의 호환성 | CI |
| `check-codex-adapter.sh` | Codex 어댑터: repo 스킬 심볼릭 링크, 에이전트 TOML, 훅 및 크로스플랫폼 런처 | CI에서 generate-codex-agents.py의 결정적 생성 확인 |
| `test-agent-permissions.py` | 도구 허용 목록, 금지 우선, 빈 목록·상속, 지원하지 않는 선언의 회귀 검사. `--opencode`로 실제 OpenCode 2.x와 모의 모델을 사용해 에이전트별 실제 도구와 실행 허용·거부 검증 | CI; CLI 호환성을 사용하여 실제 OpenCode를 실행합니다. |
| `check-antigravity-adapter.sh` | Antigravity 2.0 어댑터: 프로젝트 스킬, 에이전트 생성, Always-On Rule, named-group Hooks 및 행동 회귀 테스트 | CI（제너레이터 실행, 병합 작업 및 훅 테스트 수행） |
| `check-zcode-adapter.sh` | ZCode 플러그인/마켓플레이스, 스킬/명령어/에이전트/훅, 캐릭터 생성의 일관성 및 배포 앵커 포인트 | CI |
| `check-reasonix-adapter.sh` | Reasonix 플러그인 매니페스트 검사(스키마·스킬 14개·skills/story/VERSION과 버전 일치) | CI |

`python scripts/test-style-precedence.py`는 작품별 표현 예외가 심층 검사·문장 부호 정리·집필 후 검사·다음 장 진행 검사에 일관되게 적용되는지 확인합니다. 다른 작품으로 예외가 번지거나 같은 줄의 다른 문제·구조 오류까지 면제되어서는 안 됩니다.

<a id="测试回归test-"></a>
## 테스트 회귀(test-*)

`python3 scripts/test-publish-format.py`이 story-publish의 배포 자료를 검사하는 과정: 메타정보 및 형식 버전, 세 가지 필드의 값, 플랫폼에 따른 메타정보 선택 규칙, 태그 및 분류 후보 항목과 그 최대 수량, 제목과 길이에 대한 확인만 이루어지며 실패하지 않으며, 참조 파일의 후보 수와 중문 경로 하에서의 읽기 전용 기능에 대해서도 검사가 이루어집니다. 호스트 CLI나 네트워크가 필요하지 않으며, 이미 세 개의 플랫폼 CI에 연동되어 있습니다.

| 스크립트 | 무엇을 측정하는 건가요? | 실행 시점 |
|---|---|---|
| `test-ai-patterns.sh` | 결정적 AI 문장 구조 검출기 `check-ai-patterns.js` 회귀 테스트 | CI |
| `test-phase2-contract.js` | 단편 Phase 2 검증기의 설계 필드, 12열 개요, 분량 구간, 이름 있는 실패와 repair_scope 동작 | Linux / Windows / macOS CI |
| `test-doc-budget.py` | 임시 문서 프로젝트의 경로 합산, 초과, 파일 누락, 절별 계수, 묶음 계수, 최악의 중첩 조합(변이 비교 포함), 절대 상한 설정 실패 | CI |
| `test-delivery-contract.js` | 단편 최종 글자 수·절 수·표식·빈 줄 전달 계약 | Linux / Windows / macOS CI |
| `check-reference-gates.js` | 장편·단편 집필 전 필수 자료의 첫 화면 위치·핵심 연결, 장편의 이번 제약 기록 표식, 단편 전달 사전 검사 명령과 설계 파일만을 통한 본문 전달 검사. 구상 방법을 다시 읽지 않고 “像” 사용에 고정 상한을 두지 않음. 검증 관문은 프롬프트이므로 단언할 런타임 진입점이 없음 | Linux / Windows / macOS CI |
| `test-outline-contract.js` | 장편 상세 개요의 필드·절·5단 구성·4열 플롯 표·계수 기준·계약 위험 값에 대한 정상·오류 사례 | Linux / Windows / macOS CI |
| `test-degeneration.sh` | 모델 퇴화 감지기 `check-degeneration.js` 회귀 | CI |
| `test-prose-net-parity.sh` | 본문 보완용 경량 결정적 검사망, 본문 보호, 명령 대상 추출의 JS 코어·Codex Python·Claude Bash 동등성 | CI |
| `test-prose-backstop-hook.sh` | `check-prose-after-write.sh` 회귀 테스트 | CI |
| `test-story-continuity.sh` | `detect-story-gaps.sh` 다중 배치에 걸친 연속적인 보완 처리 회귀 테스트 | CI |
| `test-tracking-commit.py` | 단일 기준 추적의 원자적 상태, 분량 이벤트 사슬, 해시 무효화, 활성화 경계, 멱등성, 동시 커밋 | CI |
| `test-storyctl.py` | `visible_chars_v1`, 이중 구간과 작가 범위, 목표 글자 수의 양쪽 파싱 일치, 장 검사 상태·AI 문체 예외, 커밋 기록과 동일 기준 demo 증거 | Linux / Windows / macOS CI |
| `test-chapter-completion-lifecycle.py` | 공개 CLI 체크포인트, 정상 커밋, 분량 부족 수락, 초과 시 1회 압축 구간, 품질 차단, 다음 장 진행 | Linux / Windows / macOS CI |
| `test-author-memory-commit.py` | 작업 공간 작가 메모리: 단일 이벤트 응답, 집필자 전달 줄 최대 2 KB와 누락 전체 목록, 증거 후보, 충돌 대체, 철회, 실패 시 쓰기 없음, 오래된 개정, 멱등 재실행, 파생 데이터 복구 | CI |
| `test-codex-hooks.sh` | 생성된 Codex 훅의 표준 입력·출력 계약 회귀 검사 | CI |
| `test-static-check.py` | 실제 프런트매터 블록, 정확한 경로·앵커, 스킬 간 참조, 코드 블록, 사용되지 않는 참조, 에이전트·장 링크 테스트 자료 | CI |
| `test-current-skill-contracts.py` | 현재 계약 매니페스트의 형식·고정값, 주요 산출물 즉시 실패 의미 테스트 자료 | CI |
| `test-handoff-contracts.py` | 분석·순위 산출물과 소비자의 전달 계약: 보고서 절, 첫 세 장 심층 필드, 감정 모듈 검증 필드, 리듬 표 열, 단편 노드, 장르 값·`_meta.json` 키, 대상 플랫폼. 가져온 권별 개요·단편 설정의 추출·구상 검사, 집필 플랫폼과 검토 표, 조수 프롬프트 필드, AI 문체 검사 범주·집필자 태그. 고의로 망가뜨린 입력의 실패 자체 검사 포함 | CI |
| `test-plugin-packaging.py` | 공개 패키징 CLI로 임시 저장소의 카탈로그·매니페스트·버전·구성 필터를 변이하여 구조화된 실패 확인 | CI |
| `test-zcode-agents.py` | ZCode 역할 도구 허용·금지 우선·모델 상속·자료 경로·잘못된 입력의 쓰기 없음·생성 불일치·7개 호출자의 드물게 실행되는 경로 계약 | CI(check-zcode-adapter에 의해 호출됨) |
| `test-claude-plugin-lifecycle.py` | HOME 격리 후 실제 Claude CLI에서 이전 식별자 13개를 단일 번들로 이전하고 갱신·제거·무관한 플러그인 보존 확인 | `CLAUDE_REAL_CHECK=1`는 `check-claude-adapter.sh`에 의해 호출됩니다. |
| `test-shared-assets.py` | 공유 에셋 매니페스트의 불일치·동기화·경로 이탈·기본 파일명 단일 소유권·미등록 중복 탐지 | CI |
| `test-shared-references.py` | 참조 매니페스트 별칭·디렉터리 그룹·불일치·동기화·미등록 복사본·에이전트 소비 연결 | CI |
| `test-normalize-punctuation.js` | 문장 부호 정규화의 읽기 전용 검사·프런트매터·코드 블록·CRLF·따옴표 모드·멱등성 | CI |
| `test-scan-runtime.js` | CDP 인자 경계·오류·JSON 계약과 수집기 7개의 부작용 없는 가져오기. 치마오·치뎬 서재 페이지 이동(페이지 간 순위·중복 제거·빈 페이지 중지·부분 실패·인자 검사), 치뎬 수집 방지 글꼴 해독 | CI |
| `test-scan-aggregate.py` | `aggregate-rank.js`가 7개 플랫폼 형식과 수동 목록의 장르·인기 기준·분량 구간·태그를 해석하는지 검사. 동일 작품의 순위 간 중복 제거, 수집 문제 표시, 표본 부족 표시, 원문 표본 조회, 순위 외 파일 제외, 약 700항목 입력을 1/5 미만으로 축소, 인기 값 없는 신작이 플랫폼 인기 기준을 지우지 않는지 확인 | Linux / Windows / macOS CI |
| `test-scan-runtime-policy.py` | 무관하거나 실행되지 않는 코드의 키워드로 수집·브라우저 정적 정책을 속일 수 없는지 변이 검사 | CI; `check-scan-runtime-policy.sh`을 수정한 후 |
| `test-opencode-plugin.mjs` | 2.x `setup(ctx)`로 TypeScript 플러그인을 직접 실행해 개요 보호·셸 우회·집필 후 검사·압축 주입·`ctx.location` 위치 판별 확인 | `check-opencode-adapter.sh`에 의해 호출됨 |
| `test-codex-cli-e2e.sh` | HOME 격리 후 실제 Codex CLI에서 저장소 스킬 14개 탐색 확인 | CLI 호환성 CI; `codex`가 이미 설치되어 있어야 합니다. |
| `test-zcode-hooks.sh` | ZCode: 엄격한 JSON Hook, 본문 검사기 및 연속성 회귀 테스트 | CI |
| `test-antigravity-hooks.mjs` | 실제 등록 명령의 셸·리터럴 인자 호환(공백·중국어 프로젝트 경로), 훅 입출력, 본문 보호, 산출물 연결, Stop 후 1회 이어 실행 | CI(Linux/Windows/macOS) |
| `test-antigravity-hook-merge.py` | `.agents/hooks.json` 최상위 `oh-story` 관리 그룹 교체, 사용자 그룹 보존, 멱등성 | `check-antigravity-adapter.sh`에 의해 호출됨 |
| `test-antigravity-skills-deploy.py` | 알려진 스킬 14개의 원자적 실제 파일 배포, 알 수 없는 사용자 스킬 보존, 심볼릭 링크 기본 차단·명시적 이전·링크를 통한 쓰기 방지 | `check-antigravity-adapter.sh`에 의해 호출됨 |
| `test-charcount-portable.sh` | 세 플랫폼과 Windows에서 글자 수 계산 명령의 정확성 | CI(check-python-invocation 조정) |
| `test-hook-encoding-portable.sh` | Windows 중국어 환경에서 배포 훅의 인코딩 견고성 | CI |
| `test-long-analyze-runtime.py` | 장편 분석 색인, 기존 산출물 직접 사용·보강·재개 연결, 이전 장 번호와 서장 정렬, 겹치지 않는 원문 묶음, 배치 커밋·복구, 중국어 글꼴 없는 관계도 대체 처리 | CI; story-long-analyze을 실행 모드로 변경한 후 |
| `test-inspiration-index.py` | 3계층 영감 자료 색인: EM 카드 등록 멱등성, 고유명사 유출 차단, NM/CBA 완결성과 계수, 카드 내 경로 참조 거부, 태그 검색 | CI; inspiration_index.py을 수정하거나 영감 라이브러리 계약을 변경한 후에 |
| `test-opencode-cli-e2e.sh` | 실제 OpenCode 2.x CLI에서 스킬 14개·명령 14개·에이전트 7개 탐색·플러그인 활성 확인. 모의 모델로 백그라운드 서비스의 본문 차단·집필 후 보완 검사·압축 주입 검증 | CLI 호환성 CI; OpenCode 2.x(`@opencode/cli`)가 이미 설치되어 있어야 합니다. |
| `opencode-mock-llm.mjs` | OpenAI 호환 모의 모델. 시나리오 파일에 따라 도구 호출을 보내고 요청을 기록하여 실제 OpenCode 테스트 두 개의 런타임 구동에 사용 | `test-opencode-cli-e2e.sh` 및 `test-agent-permissions.py --opencode`에 의해 호출됨 |
| `test-skill-numbering.sh` | Step 재배치의 연쇄 변경 안전성, 앵커 문제 시 차단, 코드 블록 참조, 검증 실패 시 쓰기 없음·커밋 롤백, 모의 실행·기록·멱등성 | Linux / Windows용 Git Bash / macOS용 CI |

<a id="代码生成--同步"></a>
## 코드 생성 / 동기화

| 스크립트 | 기능 | 실행 시점 |
|---|---|---|
| `sync-opencode.py` | Claude 에이전트 템플릿과 `CLAUDE.md.tmpl`에서 `opencode/agents/`와 `AGENTS.md.tmpl` 생성. `--check`는 파일 수정 없이 동기화 상태만 검사 | 에이전트 템플릿 수정 후 수동 실행. 동기화 CI와 check-opencode-adapter에서 호출 |
| `generate-codex-agents.py` | Claude 에이전트 템플릿을 사용하여 Codex `.toml` 에이전트를 생성합니다. | 에이전트 템플릿 수정 후 수동 실행. check-codex-adapter에서 생성 결정성 확인 |
| `generate-zcode-agents.py` | Claude 템플릿에서 ZCode Markdown 역할 생성. 모델 상속·도구 허용 목록 유지·인라인 훅 미이전. `--check`는 읽기 전용 일치 검사 | 에이전트 템플릿 수정 후 실행. check-zcode-adapter에서 호출 |
| `generate-codex-hooks.py` | 6개의 이벤트 목록을 기반으로 `hooks.json`를 생성하며, POSIX/Windows 공용 런처가 인터프리터의 탐지 작업을 담당합니다. | Codex 훅 등록 변경 후 실행. check-codex-adapter에서 생성 결정성 확인 |
| `skills/story-setup/scripts/generate-antigravity-agents.mjs` | Claude 원본에서 Antigravity `.agents/agents/agent-name/agent.md` 생성(`agent-name`은 실제 이름). 공식 도구명·모델 프로필·참조 루트·호출 용어 변환 | story-setup을 배포할 때 check-antigravity-adapter에 의해 검증됨 |
| `skills/story-setup/scripts/merge-antigravity-hooks.py` | `.agents/hooks.json`의 `oh-story` 이름 그룹을 원자적으로 교체하고 모든 사용자 그룹 보존 | story-setup 배포 시 + 병합을 통한 회귀 테스트 |
| `skills/story-setup/scripts/deploy-antigravity-skills.py` | oh-story 스킬 14개를 프로젝트 `.agents/skills`의 실제 디렉터리로 배포. 알려진 스킬만 교체하고 사용자 스킬 보존. 심볼릭 링크는 명시적 이전이 필요하며 대상에 링크를 따라 쓰지 않음 | story-setup 배포 시 + materialization 회귀 테스트 |
| `shared-assets.json` + `sync-shared-assets.py` | 독립 배포가 필요한 중복 실행 스크립트의 유일 원본·대상 지정 | 공유 런타임을 변경한 후에는 `sync`를 실행하고, CI에서는 `check`을 실행합니다. |
| `shared-references.json` + `shared-references.py` | 독립 설치 가능한 스킬의 중복 참조에 정식 원본·의미 별칭 대상·완전한 디렉터리 미러 지정. `derived_groups`에는 독립적으로 발전하는 유사 파생 파일 등록 | 공유 reference를 변경한 후에는 `sync`을 실행하고, CI의 경우에는 `check`을 실행합니다. |

> `skills/story-setup/references/templates/agents/*.md`이나 `CLAUDE.md.tmpl`을 변경한 경우, 해당 호스트에 대한 생성 스크립트를 다시 실행하고 결과를 제출해야 합니다. 그렇지 않으면 어댑터의 CI 과정에서 오류가 발생합니다. 자세한 내용은 [CONTRIBUTING.md](../CONTRIBUTING.md)의 “OpenCode 템플릿 동기화”, “Codex 어댑터 유지보수”, “ZCode 어댑터 유지보수” 항목을 참조하십시오.

<a id="工作流编号维护"></a>
## 워크플로우 번호 관리

`skill-numbering.py`는 기본적으로 정식 원본인 `skills/**/*.md`를 검사합니다. 단계를 반복 삽입하면서 `Step 1.3`, `Phase 2.5`처럼 소수점 번호가 누적되는 것을 막습니다.

```bash
python3 scripts/skill-numbering.py audit          # 읽기 전용 목록 조사. 문제가 있어도 종료 코드 0
python3 scripts/skill-numbering.py check          # CI 검사. 문제가 있으면 0이 아닌 코드로 종료
python3 scripts/skill-numbering.py fix --dry-run  # 전체 차이를 확인하며 파일에는 쓰지 않음
python3 scripts/skill-numbering.py fix --write    # 검증 통과 후 한 번에 파일에 반영
bash scripts/test-skill-numbering.sh              # 격리된 테스트 자료로 회귀 검사
```

유지보수 원칙:

- `### Step N` 형태의 **명시적인 Step 제목**만 자동 재정렬합니다. ‘파일 + 제목 계층 + 가장 가까운 상위 제목’으로 묶고 각 묶음에 1부터 연속 번호를 부여합니다.
- 제목과 연결 대상을 유일하게 식별할 수 있는 `Step N` 참조는 원래 텍스트를 기준으로 동시에 바꿉니다. 코드 블록의 명령·예제 참조도 포함합니다. `1.5 → 2` 뒤에 `2 → 3`이 연쇄 적용되는 이중 치환을 막습니다.
- 소수점 Step 참조에 대응하는 제목이 해당 파일에 없거나 이전 번호 하나가 여러 새 번호에 대응하면 `fix`는 아무 파일도 쓰기 전에 실패합니다. 여러 파일을 쓸 때는 먼저 전체 검증과 임시 저장을 수행하고 실패 시 되돌리므로 일부만 반영된 결과를 남기지 않습니다.
- 제목 번호를 바꾸면 GitHub Markdown 앵커도 바뀝니다. 저장소에 이전 앵커를 가리키는 동일 파일·다른 파일의 링크가 하나라도 있으면 `fix`는 쓰기 전에 중지하고 해당 프래그먼트를 모두 보고합니다. 링크를 명시적으로 갱신한 뒤 다시 실행해야 합니다. 특정 경로만 검사해도 저장소의 유입 링크는 모두 확인합니다.
- `Step N.M` / `Phase N.M` / `Stage N.M`, 바로 아래의 `skills/*/SKILL.md`에 있는 단계 이름 없는 소수점 제목, 글머리표의 소수점 하위 단계는 `check`에서 오류로 보고하되 추측으로 자동 수정하지 않습니다.
- `references/` 매뉴얼의 `3.1` 같은 절·목록 번호는 워크플로 번호가 아니므로 검사하거나 수정하지 않습니다. 파이프라인 중간 단계를 삽입할 때는 의미 있는 이름이나 `Stage 2A`를 사용하고 소수점을 쓰지 않습니다.
- 명령 끝에 파일·디렉터리를 지정해 일부만 조사할 수 있습니다(예: `... audit skills/story-cover/SKILL.md`). 병합 전에는 기본 전체 범위의 `check`를 실행해야 합니다.

한국어 프로젝트 경로: `test-project-path-localization.py`는 실제 경로 생성, 원고 보존 복사, 참조 변환, 충돌·중첩·잠금 거부와 실패 정리를 검사합니다. 변환 도구는 `skills/story-setup/scripts/migrate-project-paths.py`, 대응표는 같은 폴더의 `project-paths-ko.json`입니다.

Windows에서 확인한 줄바꿈·권한·심볼릭 링크·폴더 교체·Chrome 소유권 검사와 수정 범위는 [Windows 검증 기록](../docs/WINDOWS_VALIDATION.md)을 참고합니다. POSIX 실행 비트 변경 사례는 Windows에서만 명시적으로 제외하며 내용 드리프트·원본 보존·오류 거부 검사는 계속 실행합니다.

한국 플랫폼 기본 분기·게시 자료 초안 검사는 `python scripts/test-korean-platforms.py`로 실행합니다. 국내 형식 검사의 통과는 플랫폼 공식 요건 검증이 아니며 기존 판체 검사는 `python scripts/test-publish-format.py`로 함께 확인합니다.
