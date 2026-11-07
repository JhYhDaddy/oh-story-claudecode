# scripts/bench — 실제 세션 벤치마크

v0.8 경량화의 모든 변경은 이 벤치마크를 통과해야 합니다. 동일하게 고정한 작품과 같은 테스트 사례로 실제 CLI 세션에서 장 집필을 완료하고, 변경 전후의 소요 시간·토큰·본문 지표를 비교합니다. 결정 배경은 `.agents/notes/implemented/architecture/2026-09-24-v0-8-lean-writing-loop.md`에 있습니다.

저장소에는 도구만 넣습니다. 테스트 자료, 호스트 인증 정보, 실행 산출물은 모두 저장소 밖에 보관하고 커밋하지 않습니다. 기본 위치는 `~/.oh-story-bench`이며 `BENCH_HOME`으로 변경할 수 있습니다.

## 디렉터리 규칙

```
$BENCH_HOME/
  hosts.json              호스트별 실행 파일·모델·인증 파일 경로(비밀키 자체는 제외)
  fixtures/<이름>/        고정한 작품 디렉터리(설정·권별 개요·상세 개요, 기존 본문·추적 정보 포함 가능)
  pkg/<버전>/             deploy.py export로 내보낸 패키지
  runs/<회차>/            run.py 산출물: meta.json, 세션별 로그, 격리된 HOME, 프로젝트 스냅샷
```

`hosts.json` 예시:

```json
{
  "claude-code": {"bin": "<claude 실행 파일>", "model": "<모델 이름>", "path": "<node가 포함된 PATH>",
                  "env": {"ANTHROPIC_BASE_URL": "..."}, "env_files": {"ANTHROPIC_AUTH_TOKEN": "<비밀키 파일>"}},
  "codex": {"bin": "<codex 실행 파일>", "model": "gpt-5.6-sol", "inherit_env": true,
            "env": {"CODEX_HOME": "~/.oh-story-bench/codex-home"}}
}
```

Codex 호스트는 **반드시** 독립된 `CODEX_HOME`을 사용해야 합니다. 이 디렉터리에는 `~/.codex/auth.json`을 가리키는 심볼릭 링크 하나와 모델만 지정한 최소 `config.toml`만 둡니다. `~/.codex`를 직접 사용하면 사용자의 플러그인(컴퓨터 조작·브라우저), `notify` 훅, 전역 스킬을 상속합니다. 측정에 영향을 줄 뿐 아니라 벤치마크 세션이 사용자 컴퓨터를 조작할 수도 있습니다. `run.py`는 설정이 없거나 `~/.codex`를 가리키면 실행을 거부합니다.

## 스크립트

| 스크립트 | 기능 |
|---|---|
| `deploy.py export --ref <git ref> --out <目录>` | Git의 특정 버전에서 `skills/`와 계약 파일을 내보냅니다. |
| `deploy.py deploy --pkg <包> --host claude-code\|codex --proj <项目>` | 모델을 거치지 않고 story-setup 배포 목록에 따라 스킬·에이전트·훅·규칙·진입 문서·배포 표식을 결정적으로 배포합니다. |
| `run.py --case <用例> --pkg <包> --host <主机> --out <runs目录> [--label <标签>]` | 테스트 자료 복사, 배포, `git init` 후 `cases.json`의 순서대로 실제 세션을 실행합니다. 작가에게 질문하면 `follow_up`으로 답하며 목표 장 수를 커밋할 때까지 진행합니다. |
| `judge.py [--judge agy\|claude\|codex] coverage\|pairwise ...` | 기본 평가자는 Antigravity의 Gemini이며 집필 모델과 계열이 달라야 합니다. 플롯 항목의 구현 여부와 범위 밖 추가를 하나씩 확인합니다. 두 버전을 순서를 바꿔 두 번 블라인드 비교하고 결과가 일치할 때만 승패를 판정합니다. 상세 개요가 다르면 각각의 개요를 첨부합니다. |
| `compare.py --base ... --cand ... --coverage ... --pairwise ...` | 두 버전의 효율·품질을 종합하고 비열등성 기준으로 통과 여부를 판정합니다. |
| `metrics.py <run目录>... [--table] [--tell <tell仓库>]` | 장당 평균 실제 경과 시간, 누적 입력·출력 토큰, 주 세션·도구·하위 에이전트 호출 수, 최대 맥락 크기, 압축 횟수, 장별 글자 수, 최초 분량 검사 결과, 탐지기 검출 수를 계산합니다. `--tell`을 주면 사람 글 기준 범위를 벗어난 항목 수도 추가합니다. |

`--tell`은 선택 사항입니다. 지정한다면 `detectors/human_ref_check.py`가 들어 있는 외부 비공개 저장소를 가리켜야 합니다.

Claude Code 호스트는 기본적으로 HOME을 격리합니다. 세션과 하위 에이전트 기록은 `<run>/home/.claude/projects/`에 저장하고 `metrics.py`가 여기서 토큰을 읽습니다. 격리 HOME은 `env_files`로 인증 정보를 전달하는 타사 엔드포인트에 적합합니다. 로컬에 로그인한 Claude를 사용할 때는 hosts.json에 `"real_home": true`를 설정합니다. 실제 HOME에서 인증을 가져오되 `--setting-sources project,local`로 사용자 설정·플러그인·CLAUDE.md를 제외하고, 매 회차가 끝나면 기록을 실행 디렉터리로 복사합니다. Codex는 로그인 정보를 재사용하는 독립 CODEX_HOME을 쓰고 `--json` 출력의 `turn.completed`에서 토큰을 읽습니다.

## 테스트 사례

`cases.json`의 각 사례는 테스트 자료, 작품 디렉터리명, 커밋할 장 수, 첫 요청, 작가의 후속 응답을 지정합니다. 현재 사례는 세 가지입니다.

- `mid-daily`: demo 작품의 21장 다음부터 하루 분량 3장을 집필합니다. 추적 정보와 비교 작품이 있는 성숙한 프로젝트입니다.
- `open-xuanhuan`, `open-nvpin`: 새 작품의 1~3장을 집필합니다. 도입부 작성과 추적 정보 최초 초기화를 포함합니다.

## 품질 판정

효율 지표는 바로 비교할 수 있지만 본문의 개선·악화는 이 디렉터리의 계수만 보고 판단해서는 안 됩니다. 사전 등록한 절차에 따라 먼저 평가 절차와 분석 스크립트를 고정한 뒤 데이터를 생성합니다. 평가 모델은 다른 계열을 사용하고, 개별 블라인드 평가를 수행하며, 주요 지표에는 계수 가능한 값을 사용합니다.
