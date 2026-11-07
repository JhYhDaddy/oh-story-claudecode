# Agent Note: 정적 검사에서 계약별 담당 검사를 하나로 통일

Status: implemented

## Problem

읽기 전용 테스트 감사에서 정적 문서·구조 검사에 세 종류의 중복이 발견됐다. 첫째, 같은 규칙을 두 번 실행한다. 작가용 보고서의 내부 용어 규칙을 `static-check.py`와 `check-author-reports.py`가 각각 검사했다. 둘째, 더 강한 담당 검사가 있는데도 grep을 반복한다. `check-story-setup-deployment.sh`의 TS10은 session-start 버전 기준, story-review 버전 안내, frontmatter version, story-explorer legacy 분기와 생성된 OpenCode/Codex narrative-writer 복사본을 중복 검사했다. 셋째, 문구나 복사본 개수만 고정해 실제 실행 동작을 보호하지 못한다. Reference Gate의 문장을 글자 그대로 확인하고 데모 상세 개요 21개, references 하위 디렉터리 9개, 배포 목록의 비핵심 열 이름, 더는 내장 Python이 없는 훅의 stdout을 검사했다. 단어 하나를 바꾸거나 디렉터리를 추가해도 실패하여 유지보수 비용에 비해 동작 보호 효과가 없었다.

## Decision

- 작가용 보고서 규칙은 `scripts/check-author-reports.py`만 검사한다. 장편 workflow 네 개의 템플릿 존재와 최소 블록 수를 해당 검사의 `REQUIRED`에 합친다(setup 1, chapter 4, daily 1, revision 1). `static-check.py`는 이 규칙을 더는 로드하지 않고 `test-static-check.py`의 중복 사례 두 개를 삭제한다.
- TS10에는 다른 담당 검사가 다루지 못하는 기준만 남긴다. session-start의 신구 버전 분기는 TS5의 실제 실행으로 검증한다. story-review 사전 검사, setup frontmatter version, legacy 분기는 `check-current-skill-contracts.py`가 다룬다. narrative-writer 글자 수 규칙은 원본 템플릿만 확인하고 생성 복사본은 `check-opencode-adapter.sh` / `check-codex-adapter.sh`의 동기화·결정성 검사로 보장한다.
- references 하위 디렉터리의 “== 9” 검사를 역방향 확인으로 바꾼다. Phase 1 자체 점검 목록의 각 디렉터리가 실제로 존재하는지 검사한다. “각 디렉터리가 목록에 있음”을 확인하는 정방향 검사는 원래 있었다.
- TS2에는 `Source path` / `Target path` 두 표 머리글 단언만 남긴다. 자기 복사 탐지기는 이 이름으로 배포 목록 표를 인식하므로 이름을 바꾸면 행 검사가 아무 작업 없이 끝날 수 있다. 나머지 열 이름 단언은 삭제한다.
- 계약 검사에서 `stage0-toc-block-removal`을 삭제한다. 목차 블록 제거는 `build_chapter_index.py`가 실행하고 `test-long-analyze-runtime-refactor.py`의 목차 포함 원문 사례가 검증한다. `chapter-boundary-table`도 삭제한다(#438 이후 경계는 `chapter_index.csv`에 있다). `expected_demo_outline_count`와 `demo-outline-count`도 삭제한다. `demo-outline-section`은 상세 개요를 하나도 찾지 못하면 즉시 오류를 내어 검사가 헛돌지 않도록 한다. `test_manifest_contract`에서는 CI 단계와 중복인 “manifest와 저장소 일치”를 제거한다.
- `check-reference-gates.js`는 검증 관문의 첫 화면 내 행 위치, reference 라우팅, Constraint Lock과 단편 전달 사전 검사의 명령·매개변수·순서만 확인한다(#418).
- `check-python-invocation.sh`에서 훅 내장 Python stdout 검사를 삭제한다(#243부터 훅은 Node 핵심 구현을 사용한다).

각 검사를 삭제하기 전에 담당 구현을 일부러 망가뜨리는 변이 검사를 수행했고, 남긴 검사가 실패하는 것을 확인한 뒤 복원했다.

## Alternatives considered

- **작가용 보고서 검사를 두 곳에 유지** — 로컬에서 가장 자주 실행하는 `static-check.sh`가 함께 검사하면 일찍 발견할 수 있다. 그러나 같은 규칙으로 같은 계약을 두 번 실행할 뿐이다. CI는 둘 다 실행하며 로컬 점검 목록에도 이미 `check-author-reports.py`가 있다.
- **`stage0-chapter-table-validation`도 삭제** — 이것도 문구 기준에 불과하다는 장점이 있다. 그러나 변이 검사에서 `validate_numbering`을 빈 함수로 만들어도 런타임 테스트가 모두 통과했다. 장 번호 연속성의 런타임 회귀 검사가 없으므로 삭제하면 보호 장치가 사라진다. 런타임 검사에 누락·중복 장 번호 사례를 추가한 뒤 삭제한다.
- **TS2의 열 이름 단언을 전부 삭제** — 앞서 설명했듯 `Source path` / `Target path`는 자기 복사 탐지기의 위치 기준이다. 변이 검사에서 머리글을 바꾸면 자기 복사 행이 있는 목록도 통과함을 확인했으므로 삭제하지 않는다.

## Consequences

- **이점**: 문구 변경, references 디렉터리 추가, 데모 상세 개요 수 변경 때문에 검사가 실패하지 않는다. 동작마다 실패 지점이 하나이며 오류 메시지가 실제 담당 검사를 가리킨다.
- **비용**: `static-check.sh`만 실행하면 작가용 보고서 문제를 알리지 않으므로 `check-author-reports.py`도 실행해야 한다. Reference Gate에서 삭제된 문장 검사(완독, repair 횟수 등)는 더는 CI가 보완하지 않고 실제 집필 평가와 수동 검토에 의존한다. 장 번호 연속성의 런타임 회귀 검사도 아직 부족하며 후속 작업으로 기록했다.

## 검증

`bash scripts/static-check.sh`; `python3 scripts/test-static-check.py`; `python3 scripts/check-author-reports.py --self-test && python3 scripts/check-author-reports.py`; `bash scripts/check-current-skill-contracts.sh`; `python3 scripts/test-current-skill-contracts.py`; `node scripts/check-reference-gates.js`; `bash scripts/check-python-invocation.sh`; `python3 scripts/test-plugin-packaging.py`; `bash scripts/check-story-setup-deployment.sh`.
