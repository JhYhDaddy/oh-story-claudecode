# 에이전트 참고 자료 Profile 계약

> 이 파일은 story-architect의 유일한 자료 목록이며 에이전트 템플릿에 중복 나열하지 않는다. 작업 묶음에서 다루지 않은 문제는 `long` 또는 `short`를 선택한 뒤 `Common + 현재 profile`만 읽는다. 표 밖 파일을 임의로 추가하지 않고 표의 색인이 지정한 장르 카드는 해당 색인에 따라 읽는다. 다른 에이전트는 자신의 템플릿을 따르되 여기의 long / short 선택 규칙과 품질 보완을 사용한다.

## 선택 규칙

1. 매개변수에 장편/연재/장 개요/일일 연재(长篇 / 连载 / 章纲 / 日更)가 명시되면 `long`.
2. 단편/한 편/절 개요/옌옌/미니 프로그램 단편(短篇 / 单篇 / 小节大纲 / 盐言 / 小程序短故事)이 명시되면 `short`.
3. 명시되지 않으면 산출물로 판단한다. `개요/상세개요_제XXX장.md`·`추적/`는 long, `구간개요.md`·단일 파일 `본문.md`는 short다.
4. 새 프로젝트에 산출물이 없으면 호출자로 판단한다. story-long-write의 장르 방향·핵심 설정·개요 작업은 `long`, story-short-write의 구상 작업은 `short`.
5. 여전히 판단할 수 없으면 `Reference Profile: unresolved`를 반환한다. 대비책으로 두 자료 묶음을 동시에 읽지 않는다.
6. 출력 첫머리에 `Reference Profile: long|short`를 표시한다. 검토 작업은 검토 대상 작품으로 고른다.

## Common

| 파일 | 읽기 조건 |
|---|---|
| [agent-quality.md](agent-quality.md) | 검토·평가·전달 전 확인. 장르 공통 품질 핵심만 제공하므로 현재 profile의 품질 보완도 반드시 읽음 |
| [genre-readers.md](genre-readers.md) | 목표 독자·플랫폼·기대 판단 |
| [plot-core-methods.md](plot-core-methods.md) | 상세 개요·절 개요 작성/검토: 목표 감정과 주인공 선택·쾌감 여섯 유형·절정 구성·전환 장·도입 매력. short는 전체 분량과 맞는 방법만 사용 |

## Long profile

| 파일 | 읽기 조건 |
|---|---|
| [long-genre-catalog.md](long-genre-catalog.md) | 장편 남성향 장르 방향 또는 틀 빠른 참조 |
| [female-audience-writing.md](female-audience-writing.md) | 여성향 장편 장르 틀·독자 욕구·소개. 여성향은 이 파일만 읽고 장르 목록은 읽지 않음 |
| [long-genre-mechanics.md](long-genre-mechanics.md) | 장편 핵심 아이디어·특수 능력·작은 혁신 설계 |
| [genre-prose-cards.md](genre-prose-cards.md) | 장편 장르의 목소리와 장기 제약 결정 |
| [character-relations.md](character-relations.md) | 감정선이 있으면 ‘감정선 단계’만 읽음 |
| [outline-methods.md](outline-methods.md) | 권 구조 논의/검토: ‘권 개요 배치’. 주 비교 작품이 없으면 ‘여덟 지점 이야기 구조’, 자체 단위가 있으면 ‘감정 모듈 공식’, 무대 변경 시 ‘무대 이동’을 추가 |
| [opening-design.md](opening-design.md) | 신작 도입·첫 3장 상세 개요: ‘도입부 계획’만 읽음 |
| [emotional-arc-design.md](emotional-arc-design.md) | 권·플롯 단위 감정 곡선 설계/검토: ‘곡선 여섯 유형’만 읽음 |
| [long-emotional-methods.md](long-emotional-methods.md) | 감정 장면 설계: 세 기법·밀고 당기는 리듬·실패 유형 |
| [long-chapter-hooks.md](long-chapter-hooks.md) | 장 첫머리/끝·장 사이 기대 설계. 고정된 100자 할당량을 적용하지 않음 |
| [long-suspense.md](long-suspense.md) | 단기·중기·장기 의문과 회수 주기 배치 |
| [long-reversal.md](long-reversal.md) | 단위·권·전체 반전 설계. 전체 비율을 절대 규칙으로 적용하지 않음 |
| [long-quality.md](long-quality.md) | 도입 세 장·연재 리듬·독자 계약·결말 비축 검토 |

Long profile은 `short-*` 파일을 읽지 않는다. ‘6장’·‘절마다 500–800자’·‘두 절마다 후킹’·‘전체 70–85%에서 반드시 절정’ 같은 단편 기본 기준을 적용하지 않는다.

## Short profile

| 파일 | 읽기 조건 |
|---|---|
| [short-genre-formulas.md](short-genre-formulas.md) | 단편 장르의 구조 뼈대가 필요할 때 |
| [short-chapter-hooks.md](short-chapter-hooks.md) | 절 끝·첫머리·문단 후킹·유료 전환점·전체 의문 설계 |
| [short-emotional-methods.md](short-emotional-methods.md) | 한 편의 유대·파열·밀고 당기기·여운 설계, 전체 곡선·전환 위치 선택 |
| [short-reversal.md](short-reversal.md) | 단편 단서·오도·공개 설계. 두 겹 반전은 선택한 방안에 따라 사용 |
| [short-quality.md](short-quality.md) | 전체 밀도·유료 전환점·반전 증거 사슬·결말 충족 검토 |

Short profile은 `long-*`·`outline-*`·`opening-design.md`·`emotional-arc-design.md`·`female-audience-writing.md`·`genre-prose-cards.md`를 읽지 않는다. 권 단위·일일 연재·십여 장에 걸친 지표를 필수 관문으로 삼지 않는다.
