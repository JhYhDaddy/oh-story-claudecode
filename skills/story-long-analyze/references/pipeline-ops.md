# 장편 분석 실행·반영·복구

## 단일 상태 원본과 세 스크립트

1. `build_chapter_index.py`: 기계적 장 경계·장별 원문 hash 생성.
2. `inspect_existing_assets.py`: 옛 결과·현 결과·누락 장·복구 단계를 읽기 전용으로 식별.
3. `manage_analysis_run.py`: 읽기 전용 계획, 묶음 반영·분할·복구·단계 표시.

Stage 4는 별도로 `render_relation_chart.py`가 `인물/인물관계.md`에서 관계도를 생성하며 실행 상태에는 관여하지 않습니다.

스크립트 출력은 내부용입니다. 실패·작가 결정이 필요하면 쉬운 설명·선택지를 담은 `author_message`를 [author-facing.md](author-facing.md)에 따라 전달합니다. JSON·오류 코드·아래 분류·경로명을 그대로 붙이지 않습니다.

기계적 장 경계의 유일한 기준은 `chapter_index.csv`입니다. 묶음·단계 상태는 `_progress.md`의 `story-long-analyze:runtime-state` 관리 영역에만 씁니다. `_analysis_cache/`는 전체 결과·복구 근거를 보관하며 상태 저장소가 아닙니다.

기존 프로젝트의 `schema_version: 2`는 유지하며 수정하지 않습니다. 보고용 값일 뿐 옛 결과를 무효화하는 기준이 아닙니다.

계획은 표준 출력으로만 내보내 현재 실행이 직접 사용합니다. 별도 계획·체크포인트·묶음별 수신증 파일은 만들지 않습니다. `{PYTHON}`·경로 자리표시자는 SKILL.md의 실행 규칙 참조.

## 1. 디렉터리부터 확인

```text
"{PYTHON}" "{story-long-analyze skill 根}/scripts/inspect_existing_assets.py" --root "{拆文目录}" --compact
```

- 경로 없음·디렉터리 아님·읽기 불가: 0이 아닌 종료값. 경로부터 수정합니다.
- 기존 빈 디렉터리: `empty / new_analysis`.
- 완전한 옛 프로젝트: `direct_use`. 색인을 만들거나 원문을 읽지 않습니다.
- 부분 프로젝트: `--compact`면 `semantic_coverage.missing_ranges`, 없으면 장별 `missing_semantic_chapters`·`missing_summary_chapters`도 있습니다.
- 신·구 투영 혼재: `mixed_sources: true`와 장별 출처. 완전한 프로젝트라면 여전히 직접 사용할 수 있습니다.
- `stage_repairs`는 SKILL.md Phase 2의 두 번째 표대로 해당 Stage만 보완하며 Stage 2 누락 장과 따로 처리합니다.

## 2. 원문이 필요할 때 색인 생성·검증

완전한 옛 결과는 기본적으로 직접 사용하고 단순 보강도 색인이 필요 없습니다. 신규·부분 완료 상태에서 원문을 더 읽어야 할 때 실행합니다. 문체만 보충하면 style-profile-generator.md대로 별도 색인을 만듭니다.

```text
"{PYTHON}" "{story-long-analyze skill 根}/scripts/build_chapter_index.py" \
  --source "{拆文目录}/원문/원문.txt" \
  --output "{拆文目录}/chapter_index.csv" \
  --locator-path "원문/원문.txt"
```

스크립트는 LF만으로 물리 행 번호를 계산합니다. 서장·프롤로그·제0장·임의 시작 장·외전·후기·여러 권·중국어 큰 수를 지원합니다. CSV에는 내부 연속 번호·원본 장 번호·권·제목·행 경계·문자 수·`chapter_sha256`·전체 원본 hash·파서 버전을 저장합니다.

같은 원본 색인은 재사용하고 다시 쓰지 않습니다. 원문 변경·재구축 후 번호 불일치·옛 결과 번호 불일치는 [index-rebuild.md](index-rebuild.md)를 따릅니다.

## 3. 읽기 전용 계획 생성

```text
"{PYTHON}" "{story-long-analyze skill 根}/scripts/manage_analysis_run.py" plan \
  --root "{拆文目录}" \
  --intent continue
```

- `continue`: 누락된 의미 분석 장·캐시가 무효화된 등록 묶음 보완. 의미 결과는 있지만 요약만 없으면 옛 결과에서 투영합니다.
- `enhance`: 완전한 묶음 캐시가 없는 분석 완료 장을 `REUSE-{起章}-{止章}`로 묶어 장간 관찰을 추출합니다. 장별 결과가 전 작품을 포함하면 원문 읽기 수는 0입니다. 누락 장이 있으면 그 장들의 `RAW`도 계획에 나옵니다. 계획대로 처리하거나 작가에게 완료 범위만 보강할지 먼저 묻고 `--chapters`로 제한합니다.

‘전 작품 재분석’ 의도는 없습니다. 기존 요약은 절대 덮어쓰지 않습니다. 전체 재분석은 새 디렉터리에서 합니다.

묶음 배정은 `--next 1`로 다음 것만 가져옵니다. 진도 확인은 `--next 0`으로 `remaining_batches`·구간 압축된 `summary_gaps`만 봅니다. 전체 계획은 묶음당 약 500자로 반복 출력하면 주 세션 맥락을 소모합니다. `--next`를 생략하면 전 묶음을 출력합니다.

특정 구간만 요청받으면 `--chapters 起-止`를 추가합니다(`--next`와 함께 가능). 해당 범위만 계획·`remaining_batches` 집계하며 `summary_gaps`는 여전히 전 작품 기준입니다. 구간 완료 후 멈추고 `stage2`를 표시하지 않습니다. author-facing의 전체 완료 문안으로 이 구간만 보고한 뒤 나머지도 분석할지 묻습니다.

계획은 메모리·표준 출력에만 있고 `state_written`은 반드시 `false`입니다. 블록당 최대 3장·25,000문자이며 초장편 단일 장은 독점 블록을 허용합니다. 한 장이 원문 블록 두 개에 들어가면 안 됩니다. 계획 원문 읽기 수가 0이면 원문 과제를 배정하지 않습니다. 묶음 ID는 장 범위를 그대로 씁니다. `RAW`는 누락 장·캐시 무효 묶음만, `REUSE`는 계획의 옛 결과만 읽습니다. 도입 3장 심층 분석은 기존 의미 결과이므로 원문을 다시 읽지 않고 빠진 요약을 생성할 수 있습니다.

## 4. 묶음 하나 실행·반영

`chapter-extractor`는 계획의 묶음 하나만 처리합니다. **주 세션은 내용을 중계하지 않습니다.** 원문·결과 모두 주 세션 맥락을 거치지 않습니다. 아래 필드를 계획 그대로 복사하고 경로 앞에 `{拆文目录}/`를 붙입니다. 임의 선택·계산하지 않습니다.

- `batch_id`, `input_kind`.
- `source_files`: 원문 블록은 장별 `source_locator`이며 하위 에이전트가 행 번호로 직접 읽습니다. `chapter_chars`: 장별 글자 수. `min_plot_points`: 글자 수 기준으로 계산한 장별 최소 사건 수.
- `input_file`: `_analysis_cache/输入-{批次ID}.md` 출력 경로. 작품마다 자신의 분석 디렉터리에 저장합니다.
- `handoff_cache`: 계획이 정한 ‘이번 시작 장 이전의 가장 최근 반영 묶음’ 인계 캐시. 비면 주지 않습니다. 하위 에이전트는 그 안의 `### 跨批状态`만 읽습니다.

하위 에이전트는 전체 출력을 파일에 쓰고 `BATCH_WRITTEN` 한 줄만 반환합니다. 주 세션은 **그 입력 파일을 Read하지 않고** 바로 반영합니다. 거부되면 같은 묶음을 다시 배정하며 필드를 그대로 주고 오류 코드를 덧붙입니다. 하위 에이전트는 `source_locator`로 원문을 확인하고 `min_plot_points`에 맞춰 사건을 보완합니다. Edit으로 오류 부분만 고친 뒤 다시 반영하며 전체 구조가 망가진 경우만 파일을 다시 씁니다. 성공하면 입력 파일을 삭제합니다. 어느 배정 방식이든 `commit`은 주 세션이 하나씩 실행하고 병렬 실행하지 않습니다.

**배정 방식**: 기본은 2번 제한 병렬이며 작가에게 세 가지 중 고르라고 하지 않습니다. 더 빠르거나 안정적으로 가능한지 묻거나 변경을 명시하면 author-facing의 방식 설명대로 안내·전환합니다. 세 방식 모두 계획의 `handoff_cache`를 사용하며 반영 진도에 따라 해당 묶음이 자동 선택됩니다.

1. **직렬**: 앞 묶음 반영 성공 뒤 다음을 배정합니다. 캐시는 바로 앞 묶음입니다. 사건·미결 궁금증·확정 별명을 완전히 이어받아 Stage 3 병합이 가장 쉽지만 가장 느리고 시간은 묶음 수에 비례합니다.
2. **제한 병렬**: 라운드당 3묶음을 동시에 배정합니다. 같은 라운드는 시작 전 가장 최근 반영 묶음을 공유하고 라운드 전체 반영 후 다음을 배정합니다. 대기 시간이 줄고 인계 지연은 최대 한 라운드입니다. 다만 같은 라운드끼리 새 사건·별명을 볼 수 없어 경계에서 ID를 중복 생성할 수 있으므로 Stage 3 장간 병합에 의존합니다.
3. **묶음 순서 제한 없음**: 앞 묶음을 기다리지 않고 최대 12개 하위 에이전트를 실행합니다(호스트·계정 상한이 더 낮으면 그에 따름). 실행 수가 상한의 절반보다 적으면 상한까지 추가 배정합니다. `plan --next {在跑数＋补派数}`로 가져오고 실행 중 ID는 건너뜁니다(계획은 반영된 것만 인식). 속도 제한·시간 초과·하위 에이전트 오류면 상한을 절반으로 줄인 뒤 보충합니다. 더 많은 묶음을 처리하지만 인계가 가장 약해 Stage 3·4 병합에 가장 의존합니다. 동시성이 높을수록 제한·전체 묶음 재실행 위험이 커집니다.

작가 언급 없음·한 번에 전체 분석·여러 작품 동시 분석·story-import 자동 재개는 모두 2번입니다. 1·3번은 작가가 명시 선택한 경우만 사용합니다. 여러 작품이면 작품별로 번갈아 배정하고 3번 총 동시성도 같은 상한을 넘지 않습니다. 1·2번은 `plan --next 1` / `--next 3`을 씁니다. 하위 에이전트가 없으면 주 세션이 [stage2-extraction.md](stage2-extraction.md)를 먼저 읽고 그 묶음 반영 형식의 추출 규칙·래핑 표식대로 작성합니다.

```text
"{PYTHON}" "{story-long-analyze skill 根}/scripts/manage_analysis_run.py" commit \
  --root "{拆文目录}" \
  --input "{拆文目录}/_analysis_cache/输入-RAW-4-6.md" \
  --batch-id "RAW-4-6" \
  --range-sha256 "{plan 输出值}" \
  --source-file "{plan 列出的来源}"
```

`REUSE`는 `--range-sha256`을 전달하지 않습니다. 완전한 보강이면 `REUSED_CHAPTERS`·장간 관찰만 출력해도 됩니다. 요약이 필요하면 같은 압축 장 블록을 출력합니다. 반영 입구에서 최대 3장·25,000문자를 다시 확인하며 초장편 단일 장 독점은 여전히 허용합니다.

반영 순서:

1. 쓰기 전에 전체 범위·표식·압축 필드·사건을 검증합니다. 원문 블록의 장별 사건은 `min_plot_points` 이상·30개 이하여야 하며 어기면 묶음 전체 거부. 번호는 연속, 각 항목에 주제 태그·기조 행 필수.
2. `RAW`의 현재 범위 hash를 재계산해 계획과 다르면 거부합니다.
3. 전체 모델 출력·최종 종료 표식이 있는 묶음 캐시를 원자적으로 씁니다.
4. 빠진 `장별분석/제N장_요약.md`만 생성합니다. 기존 요약은 모두 보존하고 `kept_existing_summary_chapters`에 나열합니다. 사건의 주제·기조·유형을 고정 열거값으로 투영하며 주제·기조 대응 불가면 「其他」. 옛 소비자가 쓰는 「关键事件」「情节点」「涉及」「基调」 필드를 유지합니다.
5. 마지막에 `_progress.md` 관리 묶음 표를 `completed`로 바꿉니다. 단계 기록이 있으면 Stage 3–6 상태에 따라 관리 영역 「最终状态」를 다시 씁니다. 옛 프로젝트는 기존 행을 바꾸고 두 번째 행을 추가하지 않습니다.

성공 행에는 범위·입력 유형·원문 범위 hash·상태·캐시 경로를 기록합니다. 관리 영역 밖의 BOM·줄바꿈·작가 메모·기존 `schema_version`은 바이트 단위로 보존해야 합니다.

## 5. 실패·분할·재시도

모델 출력이 불완전하면 반영하지 않습니다. 묶음이 너무 크거나 연속 실패하면:

```text
"{PYTHON}" "{story-long-analyze skill 根}/scripts/manage_analysis_run.py" split \
  --root "{拆文目录}" --batch-id "RAW-4-6"
```

`--at 4`로 분할 경계를 지정할 수도 있습니다. 같은 `_progress.md` 관리 영역에 부모 블록을 `superseded`로 표시하고 이웃한 자식 둘을 씁니다. `plan` 재실행 후 자식을 사용하며 위치 번호로 옛 기록을 덮거나 자식을 부모로 재결합하지 않습니다.

## 6. 중단 복구

먼저 `plan`을 다시 실행합니다. 아래 세 조건을 만족한 성공 묶음은 나오지 않습니다.

1. 범위의 모든 요약 존재.
2. 캐시가 완전하고 마지막 비어 있지 않은 표식이 cache end.
3. `RAW` 상태 행의 범위 hash = 현 색인 계산값.

캐시는 완전하지만 요약·진도의 마지막 저장이 안 됐다면:

```text
"{PYTHON}" "{story-long-analyze skill 根}/scripts/manage_analysis_run.py" repair-progress --root "{拆文目录}"
```

완전하고 범위 hash가 유효한 캐시에서만 빠진 요약·상태를 보완하며 사용자 수정 파일은 덮어쓰지 않습니다. 종료 표식 없음·범위 hash 무효면 오류를 알리고 해당 묶음을 다시 실행합니다.

## 7. 단계 표시·후속 단계

Stage 1 도입 세 장·빠른 미리보기 저장 후 `stage1`, 계획의 묶음이 없어지고 모든 요약 저장 후 `stage2`를 표시합니다.

```text
"{PYTHON}" "{story-long-analyze skill 根}/scripts/manage_analysis_run.py" mark-stage --root "{拆文目录}" --stage stage2
```

Stage 3–5의 자료 추출(`digest`)·표시는 [synthesis-inputs.md](synthesis-inputs.md), Stage 6는 [style-profile-generator.md](style-profile-generator.md), 마무리는 [final-checks.md](final-checks.md) 참조.
