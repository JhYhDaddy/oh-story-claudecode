# 비교 작품 문체 회수(story-explorer · benchmark_style_load)

`query_type`이 `benchmark_style_load`일 때만 이 파일을 읽는다. 다른 조회 유형에서는 읽지 않는다. 출력은 에이전트 정의의 순수 JSON·문자열 이스케이프 규칙을 따르며 특히 원문 근거 조각을 이스케이프한다.

## 절차

비교 작품의 감정 모듈·리듬 색인·문체를 읽고 이번 장 감정/분위기에 따라 참고 장과 원문 근거 조각을 고른다.

1. **입력 해석**: 프로젝트 디렉터리 + 이번 장 감정/분위기 + 선택적 쾌감 유형 + 선택적 목표 글자 수.
2. **주 비교 작품 선택**:
   - 프로젝트 디렉터리명·`.active-book`·작품 설정으로 현재 작품부터 식별한다. `작품분석실/{当前书}/`는 story-import의 현재 작품 분석이며 비교 후보가 아니다. 과거 잘못 만든 `비교작품/{当前书}/`도 제외하고 `gaps.self_benchmark_ignored: true`를 반환한다.
   - `Read 설정/소재방향.md`로 `主对标书` 필드를 추출한다.
   - 필드가 있고 현재 작품이 아니면 사용한다. 현재 작품을 가리키면 무시하고 `gaps.self_benchmark_ignored: true`.
   - **경로는 필드값 그대로 글자 단위 연결**한다. 《》 같은 장식을 더하거나 한 글자라도 바꾸지 않는다. 틀리면 Glob이 조용히 빈값을 반환하여 작품 없음과 구별할 수 없다.
   - **등록된 주 비교 작품 디렉터리를 3단계에서 찾지 못하면**(안의 파일을 하나도 찾지 못함) `gaps.benchmark_book_missing: true`와 `expected_path`(맞춤법 대조용으로 실제 탐색한 전체 경로 그대로), 빈 `results`를 반환하고 **멈춘다**. 다른 작품으로 바꾸거나 아래 누락 대체를 쓰지 않는다. **작품 디렉터리는 있으나 `문체.md`만 없는 경우는 다르다.** 4-6단계로 진행하고 6단계에서 `profile_missing`으로 분류한다.
   - 필드가 없거나 무시했다면 `Glob 비교작품/*/**/*`로 적중 파일의 작품 디렉터리(`비교작품/` 바로 아래, 현재 작품 제외) 중 사전순 첫 항목을 선택하고 `gaps.main_benchmark_unspecified: true`로 주 비교 작품 미지정을 알린다. **열거 기준은 작품 디렉터리 안의 파일 존재이며 `문체.md` 존재가 아니다.** 문체 파일 없이 다른 자료가 갖춰진 후보도 적중이다.
   - 제외 뒤 없으면 위로 올라가 작업 공간 루트의 `작품분석실/*/**/*`를 찾고 현재 작품을 제외한다. 여전히 없으면 `gaps.no_benchmark: true`, 빈 `results`를 반환한다. **오류로 보고하지 않고 문체 읽기도 계속하지 않는다.**
3. **비교 작품 경로 찾기(디렉터리 유효성만 판단, 문체는 판단 안 함)**: `{项目}/비교작품/{书名}/**/*`를 우선하고 `작품분석실/{书名}/**/*`로 대체한다(위로 작업 공간 루트를 찾고 분석 라이브러리로 내려감). 탐침은 디렉터리의 아무 파일이다. Glob은 순수 디렉터리 패턴을 받지 않아 `{书名}/`는 늘 빈값이다. 한 곳이라도 파일이 적중하면 유효하므로 4단계로 간다. 양쪽 모두 없을 때만 `benchmark_book_missing`. **`문체.md`를 디렉터리 존재 탐침으로 겸용하지 않는다.** 문체 누락은 6단계의 `profile_missing`, 이후 호출자가 `custom_style`로 처리한다.
4. **주 산출물 탐침과 자료 세대**:
   - `{对标书路径}/플롯/감정모듈.md`와 `{对标书路径}/플롯/리듬.md`를 먼저 찾는다. 둘 다 있어야 현재 권위 자료 회수로 간다.
   - 하나라도 없으면 아래 결과를 즉시 반환하고 준비를 멈춘다. `schema_version`으로 신구를 판단하지 않는다. 둘 다 있으면 정상 회수하며 인과·이중 시간선·삼차원 리듬 같은 새 내장 필드 누락은 차단하지 않는다.
   - `플롯/감정모듈.md` 누락 → `gaps.missing_primary_contract: true`·`gaps.module_missing: true`, `repair_action`은 ‘/story-long-analyze Stage 3을 재실행하여 감정 모듈 보충’.
   - `플롯/리듬.md` 누락 → `gaps.missing_primary_contract: true`·`gaps.rhythm_missing: true`, `repair_action`은 ‘/story-long-analyze Stage 3을 재실행하여 리듬 색인 보충’.
5. **현재 권위 자료 회수**:
   - 있는 `{对标书路径}/플롯/감정모듈.md`에서 「读者需求」(독자 욕구)·「情绪引擎」(감정 엔진)·「可复现模块」(재현 가능 모듈) 중 `selected_emotion_module` 1개를 선택하고 `module_source_path`를 쓴다.
   - 있는 `{对标书路径}/플롯/리듬.md`에서 「关键信息推进」(핵심 정보 전진)·「情绪触动点」(감정 자극점)·「爆发」(폭발)/「冷却」(냉각) 중 `rhythm_reference` 1개를 선택하고 `rhythm_source_path`를 쓴다.
   - 두 권위 파일이 모두 있지만 같은 장/모듈의 독자 감정·폭발점 설명이 모순이면 원문 요약 두 개를 유지하고 `gaps.module_rhythm_conflict: true`와 `gaps.conflict: "..."`를 반환한다. 호출자는 두 권위 파일이 `작품분석보고서.md` / `이야기선.md`보다 우선한다는 규칙으로 처리한다. 임의로 다시 쓰지 않는다.
6. **문체 읽기**:
   - `Read {对标书路径}/문체.md`.
   - 없으면 `gaps.profile_missing: true, expected_path: "..."`를 반환하고 **후속 단계를 계속하지 않는다**. 디렉터리 자체는 유효하므로 `benchmark_book_missing`으로 바꾸지 않는다. 호출자가 `custom_style`로 계속/중단을 결정한다.
   - 「生成记录」의 `文风可用：否`를 확인하면 `gaps.profile_degenerate: true`. 이후 문체를 강한 제약으로 쓰지 않는다.
7. **사용 가능성 검사(읽기 전용으로 실행 가능)**:
   - 이 에이전트는 `Read/Glob/Grep`만 있으므로 Bash/stat을 호출할 수 없다.
   - 문체 파일의 「生成记录」만 읽는다. `文风可用：否`·`需重生` 같은 사용 불가 표식이 명시되면 `gaps.profile_stale: true` 또는 `gaps.profile_degenerate: true`, `stale_reason`에 이유를 쓴다.
   - 원문 파일이 없어도 유효한 근거 조각이 있으면 그것만으로 사용 불가라 하지 않는다. 파일 시각을 비교하지 않으며 명시적 만료 설명이 없으면 `profile_stale: false`.
8. **장 분위기 후보 집합**:
   - `Glob {对标书路径}/장별분석/*_요약.md`.
   - Grep 도구로 파일마다 정규식 `Grep -hE '基调：(紧张|轻松|悲伤|热血|爽|甜|温馨|恐怖|压抑|其他)'`를 검색한다. 이는 검색 조건이며 shell 실행이 아니다. **전각 콜론**, 행 시작에 고정하지 않음. 각 장의 모든 플롯 지점 분위기를 얻는다.
   - 장 분위기는 최빈값, 동률이면 grep 출력에서 먼저 나온 것을 취한다.
   - 후보 집합은 장 분위기가 이번 장 감정/분위기와 같은 장 목록이다.
9. **비슷한 분위기 대체(동일 분위기 장이 전혀 없을 때)**:
   - 상세 개요/조회 매개변수에서 ‘긴장·열혈·통쾌함·달콤함·가벼움·따뜻함·슬픔·공포·억압’ 중 가까운 유형을 판단한다. 고정 대응표를 쓰지 않는다.
   - 가장 가까운 분위기 하나로 다시 선별하고 결과에 비슷한 분위기를 대체로 사용했다고 설명한다.
   - 여전히 비면 `gaps.tone_match_failed: true`. 일치 장 읽기는 건너뛰되 작품 전체 문체·`selected_emotion_module`·`rhythm_reference`는 반환한다.
10. **후보가 여러 장일 때 선택**:
   - L1 쾌감 유형 최강 일치. 호출자가 해당 필드를 줬으면 후보 `_요약.md`의 「关键事件」으로 판단한다.
   - L2 제공된 이번 장 목표 글자 수에 원문 장 길이가 가장 가까운 것. Bash로 세지 않고 색인·기존 자료의 원문 길이만 쓴다. 없으면 L2를 건너뛰며 지점 수·요약 글자 수로 대체하지 않는다.
   - L3 가장 작은 장 번호.
11. **일치 장 자료 읽기**:
   - 먼저 `Read {对标书路径}/장별분석/제K장_요약.md`로 분위기 순서·주요 사건·쾌감/감정 지점을 추출한다.
   - 새 경량 요약은 「信息变化」「状态变化」「章尾钩子」「三维节奏」 필드를 직접 읽는다. 구형 요약에 없을 때만 「关键信息与扩写技法」 표를 `matched_chapter_techniques`의 근거/보충으로 읽는다. 어느 쪽도 `플롯/리듬.md`를 덮어쓰지 않는다.
   - `{对标书路径}/장별분석/제K장_심층분석.md`가 있으면 「可借鉴要素」(차용 가능 요소) + 반응층 + 장 끝 후킹 유형을 추가로 읽고 추출한다.
   - 같은 장 심층 분석이 없다고 실패하지 않는다(흔히 도입 세 장에만 있음). `제1장_심층분석.md`·`제2장_심층분석.md`·`제3장_심층분석.md` 중 분위기가 가장 가까운 장으로 대체하거나 문체의 「可借鉴技巧」만 쓴다.
   - 이 대체를 `gaps.matched_deep_dive_missing: true`로 표시한다.
12. **원문 근거 조각 추출(문체 파일)**:
   - `## 原文锚点片段` 절에서 분위기를 붙인 모든 조각을 읽는다.
   - 이번 장 감정/분위기로 1-2개 선택한다. 정확한 일치 우선, 없으면 가까운 분위기.
   - 300-500자 원문을 완전하게 전달하고 자르거나 요약하지 않는다.
13. **구조화 JSON 반환**: `source_files`는 이번에 실제 읽은 파일만 나열하고 예시 경로는 실제 출처로 바꾼다.

## 누락 시 중단과 대체 처리

- 주 산출물 `플롯/감정모듈.md`·`플롯/리듬.md` 중 하나라도 없으면 `missing_primary_contract`·`repair_action`을 반환하고 준비를 멈춘다.
- 등록한 주 비교 작품 디렉터리가 없으면 `benchmark_book_missing`·`expected_path`를 반환하며 작품을 바꾸지 않는다.
- 디렉터리는 있고 `문체.md`만 없으면 `profile_missing`이다. 호출자가 `custom_style`로 계속/중단을 결정한다.

## 출력 구조

```json
{
  "query_type": "benchmark_style_load",
  "results": {
    "style_profile_path": "비교작품/{书名}/문체.md",
    "style_profile_summary": "<≤200자 핵심 추출: 문장부호 습관 + 대화 기법 + 감정 교대 패턴>",
    "selected_emotion_module": "<플롯/감정모듈.md에서 선택한 读者想看什么/情绪链/戏剧单元/可替换项/不可照搬; 없으면 null>",
    "rhythm_reference": "<플롯/리듬.md에서 선택한 关键信息推进/情绪触动点/爆发节奏/冷却参考; 없으면 null>",
    "module_source_path": "비교작품/{书名}/플롯/감정모듈.md",
    "rhythm_source_path": "비교작품/{书名}/플롯/리듬.md",
    "matched_chapter_K": 14,
    "matched_chapter_techniques": "<일치 장 요약 + 심층 분석/도입 세 장 대체 자료의 차용 가능 요소, ≤300자>",
    "anchor_excerpts": [
      {"tone": "悲伤", "source": "제14장 7문단(823-901행)", "demo_point": "대화 이면 의미 기법", "text": "<300-500자 원문>"},
      {"tone": "热血", "source": "제8장 3문단(401-465행)", "demo_point": "쾌감의 준비와 발산 비율", "text": "<300-500자 원문>"}
    ]
  },
  "source_files": ["설정/소재방향.md", "비교작품/{书名}/플롯/감정모듈.md", "비교작품/{书名}/플롯/리듬.md", "비교작품/{书名}/문체.md", "비교작품/{书名}/작품분석보고서.md", "비교작품/{书名}/장별분석/제14장_심층분석.md"],
  "gaps": {
    "no_benchmark": false,
    "module_missing": false,
    "rhythm_missing": false,
    "module_rhythm_conflict": false,
    "conflict": null,
    "missing_primary_contract": false,
    "repair_action": null,
    "profile_missing": false,
    "profile_stale": false,
    "profile_degenerate": false,
    "stale_reason": null,
    "main_benchmark_unspecified": false,
    "benchmark_book_missing": false,
    "self_benchmark_ignored": false,
    "raw_text_unavailable": false,
    "tone_match_failed": false,
    "matched_deep_dive_missing": false
  }
}
```
