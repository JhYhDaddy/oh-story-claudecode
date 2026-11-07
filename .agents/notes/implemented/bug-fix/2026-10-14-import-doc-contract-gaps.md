# Agent Note: 가져오기 문서를 기존 스크립트·작품 분석 산출물에 맞추기

Status: implemented
Related: [가져오기 자료를 시점별로 로드](../../implemented/architecture/2026-09-26-import-by-moment.md)

## Problem

가져오기 흐름의 시점별 설계는 구현되었지만 일부 설명이 현재 구현과 충돌했다. 마무리 자체 검사는 아직 실행하지 않은 활성화 항목도 완료되어야 한다고 요구했다. 인물 스냅샷 목록을 최대 8개로 잘못 설명했고 범위를 확대하면 기존 상태를 재초기화하도록 요구했다. 단편의 구조 분할·밑작업·감정 강도 출처가 잘못되었고 장편 이전의 후반부는 앞에서 재사용을 허용한 기존 결과까지 무조건 차단했다.

## Decision

`tracking_commit.py`, `build_outline_brief.py`, 기존 장편·단편 분석 출력 계약에 따라 마무리 자체 검사는 이전까지의 진행만 확인하고 스냅샷 목록은 바이트로 제한하며 배치 분석 완료 후 한 번만 초기화한다고 명확히 한다. 단편 구조 분할은 분석 보고서, 밑작업은 반전 분석에서 가져오고 감정 강도는 두 척도를 구분한다. 장편 이전에서는 기존 결과의 호환 범위를 통일한다. 분량 경로는 작가가 선언하면 바로 확정한다. 선언이 없을 때의 신호 충돌은 기존 Phase 1 확인에서 처리하고 5장 미만일 때의 글자 수 대체 기준을 보완한다. 명령·필드·번호·기계적 검사와 스크립트는 유지한다.

단편 이전은 기존 내용과 이어쓰기 기준을 보존하지만 집필 측 구상 검사를 바로 통과한다고 보장하지 않는다. 이후 설계는 집필 스킬의 기존 흐름으로 보완한다. 형식 참조는 근거 있는 감정 기복을 허용하고 문장부호는 기본적으로 기존 작품별 문체 우선 규칙을 따른다. 공유 추적 참조 두 개에는 제안만 기록하고 원본 처리 차례를 기다린다.

## Alternatives considered

- 문장만 다듬으면 변경이 가장 적다. 그러나 실행자가 스스로 막히거나 데이터를 얻지 못하는 지침이 남으므로 확인 가능한 설명 오류도 함께 고친다.
- 스크립트를 옛 설명에 맞추면 기존 문서를 유지할 수 있다. 그러나 현재 스크립트와 상하위 계약이 이미 일치하므로 구현 범위를 넓힐 필요가 없다.

## Consequences

가져오기 설명을 기존 구현대로 실행할 수 있고 이어쓰기에 필요한 자료 출처가 더 명확해진다. 대신 유지보수 시 상위 산출물과 이 스킬의 이전 설명을 함께 대조해야 한다. 공유 추적 참조 두 개는 long-write 원본 처리에서 정리·동기화되었으며 앞으로도 유일한 원본을 따라야 한다.

## 검토 범위

문서 15개를 모두 읽고 다섯 단계를 순서대로 완료했다. 공유 추적 자료 두 개는 long-write 원본 처리에서 수정·동기화했으며 현재 기록은 재검토와 동기화를 완료한 결과다.

| 파일 | 다섯 단계 검토 | 결과 |
|---|---|---|
| `SKILL.md` | 1→5 완료 | 수정 완료 |
| `references/character-state-reverse.md` | 1→5 완료 | 수정 완료 |
| `references/deep-analysis.md` | 1→5 완료 | 수정 완료 |
| `references/format-and-structure.md` | 1→5 완료 | 수정 완료 |
| `references/import-report.md` | 1→5 완료 | 수정 완료 |
| `references/import-special-cases.md` | 1→5 완료 | 수정 완료 |
| `references/import-tracking.md` | 1→5 완료 | 수정 완료 |
| `references/length-routing.md` | 1→5 완료 | 수정 완료 |
| `references/outline-reverse-rules.md` | 1→5 완료 | 수정 완료 |
| `references/outline-reverse.md` | 1→5 완료 | 수정 완료 |
| `references/state-tracking.md` | 1→5 완료 | 수정 완료 |
| `references/structure-mapping-long.md` | 1→5 완료 | 수정 완료 |
| `references/structure-mapping-short.md` | 1→5 완료 | 수정 완료 |
| `references/tracking-initialization.md` | 1→5 완료 | 공유 원본 처리에서 완료 |
| `references/tracking-transaction.md` | 1→5 완료 | 공유 원본 처리에서 완료 |
