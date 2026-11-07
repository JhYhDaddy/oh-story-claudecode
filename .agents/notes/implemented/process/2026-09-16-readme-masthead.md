# Agent Note: README 머리말을 중앙 정렬 형식으로 통일

Status: implemented

## Problem

저장소 여섯 곳의 README 머리말이 제각각이었다. 일부 제목은 저장소 슬러그였고 배지는 0~4개로 개수도 다르며 Actions·social·flat 스타일이 섞여 있었다. 커뮤니티 진입점은 대표 저장소에만 Telegram 하나가 있었고 그것도 본문 끝에 묻혀 있었다. 어느 저장소를 열어도 첫 화면만으로는 누구의 프로젝트인지, 활동 중인지, 어디서 질문해야 하는지 알기 어려웠다.

## Decision

여섯 저장소의 두 언어 README는 동일한 중앙 정렬 머리말을 사용하며 순서를 고정한다. 브랜드 마크(76px, `https://raw.githubusercontent.com/zenstory-ai/zenstory/main/apps/web/public/brand/zenstory-ai-mark.svg` 참조; 2026-10-29부터 zenstory.ai 사본을 참조하지 않는다. GitHub 이미지 프록시가 README 조회마다 원본을 요청하여 Vercel CDN 요청의 약 16%를 차지했기 때문이다), `<h1>` 제품명, 굵은 한 문장, 탐색 링크 한 줄(프로젝트 홈페이지 · 본문 앵커 두 개 · 다른 언어), flat-square 배지 한 줄, for-the-badge 커뮤니티 버튼 한 줄 순이다. 배지는 flat-square와 브랜드 색상으로 통일한다. 별 수는 `#22D3EE`, Release와 개수는 `#081431`, License는 `#1F6FEB`이다. 핵심 네 항목은 Stars·Release·프로젝트 규모(Skills N 또는 Workbenches N)·License이며 저장소별 실행 정보(Python 버전·CI·Validate·MiMo)는 그 뒤에 놓는다. 제품명은 저장소 슬러그가 아니라 사이트의 이름을 사용한다.

## Alternatives considered

- **hypit처럼 제품마다 글자가 포함된 로고 이미지를 제목으로 사용**. 가장 큰 장점은 이미지 워드마크의 시각적 밀도가 글자보다 훨씬 높아 브랜드를 한눈에 알아볼 수 있다는 점이다. 그러나 제품 여섯 개의 워드마크 여섯 개를 만드는 것은 별도 디자인 작업으로 이번 범위를 벗어난다. 텍스트 `<h1>`은 검색·목차·스크린 리더에서도 읽을 수 있다.
- **로고 파일을 각 저장소에 복사**. 외부 사이트에 의존하지 않아 포크와 오프라인 렌더링도 정상 작동한다는 점이 가장 큰 장점이다. 그러나 로고를 바꿀 때 사본 여섯 곳을 수정해야 한다. GitHub camo 프록시가 zenstory.ai의 이 SVG를 정상 반환하는 것도 실제로 확인했다.

## Consequences

- 이점: 여섯 저장소의 첫 화면이 같아지고 별 수·버전·규모·라이선스·질문 진입점이 고정 위치에 놓인다. 브랜드 마크 변경 시 온라인 파일 하나만 바꾸면 된다.
- 비용: 로고는 zenstory.ai 접근 가능 여부에 의존한다. GitHub가 `<h1>`에 붙이는 하단 테두리는 없앨 수 없어 제목과 부제 사이에 가로선이 남는다.
- 이 저장소에서 추가로 한 선택: 없음.

## 검증

배지 URL 27개를 하나씩 요청해 모두 200을 반환하고 라벨도 올바른지 확인했다(별 수·Release 태그·CI/Validate 상태 포함). 머리말은 GitHub 공식 Markdown 인터페이스로 렌더링하고 밝은·어두운 테마에서 육안으로 확인했다.
