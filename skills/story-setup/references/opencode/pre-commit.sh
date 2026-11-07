#!/bin/sh
### story-hooks: BEGIN ###
# story 프로젝트 커밋 검증
# story-setup 관리 블록 — 수동 편집 금지
# 이야기 파일의 하드코딩된 인물 속성을 검사한다(안내만 하며 절대 차단하지 않음).
#
# 이 블록은 SKILL.md 배포 규칙에 따라 사용자의 기존 .git/hooks/pre-commit에 그대로 삽입된다. 자체
# shebang 없이 호스트 인터프리터를 따른다. 호스트는 흔히 #!/bin/sh(git 기본 예제/lefthook/husky)이며
# Debian/Ubuntu의 /bin/sh는 dash다. 따라서 블록 전체는 POSIX sh 구문만 사용하고 set -o pipefail,
# read -r -d 빈 문자열, 프로세스 치환 `< <(...)`, 달러 따옴표 줄바꿈 구문은 쓰지 않는다. dash에서 첫 항목은 오류, 뒤 구문들은 문법 오류를 내어
# 이후 모든 git commit이 종료 1로 실패해 커밋을 만들지 못한다. 이는 안내만 하고 절대 차단하지 않는다는
# 계약에 반한다. create 모드에서는 파일 전체를 훅으로 복사하므로 파일 자체 shebang도 /bin/sh를 쓴다.
# /bin/bash 없는 호스트(Alpine/busybox, NixOS)에서는 git이 건너뛰지 않고 치명적 오류를 내기 때문이다.
# 마지막 `|| true`는 호스트가 set -e여도 이 블록 때문에 커밋을 막지 않는 최종 안전장치다.
(
set -eu
# LC_ALL=C: 패턴의 전각 ‘　’ ‘：’는 멀티바이트 UTF-8이다. GBK에서 grep은 잘못된 시퀀스로 판단해
# 종료 2를 내고 !로 뒤집으면 모든 설정 파일의 필드 누락을 오탐한다. C 로캘로 강제해 바이트 일치한다.
# validate-story-commit.sh와 동일하며 이슈 #164 규칙은 LC_ALL=C + 문자 집합 대신 선택식이다.
export LC_ALL=C
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
WARNINGS=""
# POSIX sh에는 달러 따옴표 줄바꿈 구문이 없어 줄바꿈 상수는 이렇게 작성한다.
NL='
'

# 스테이징 md 목록을 한 번에 가져온다. POSIX sh는 read -d가 없어 -z NUL 스트림을 받지 못하므로 줄바꿈으로 구분한다.
# 파일명 자체에 줄바꿈이 있는 매우 드문 경우만 어긋나며 안내 문구에만 영향이 있다. 다음 방식도 안 된다.
# `git … | while`은 while을 자식 셸에서 실행해 모은 WARNINGS를 꺼낼 수 없다. 변수에 먼저 저장하고
# here-doc으로 while에 전달해 현재 셸에서 반복한다.
STAGED=$(git -c core.quotepath=false diff --cached --relative --name-only --diff-filter=ACM -- . 2>/dev/null || true)

while IFS= read -r file; do
  [ -n "$file" ] || continue
  case "$file" in
    *.md) ;;
    *) continue ;;
  esac

  FULL_PATH="$ROOT/$file"
  [ -f "$FULL_PATH" ] || continue

  # 일치 의미와 경고 문구는 JS 코어(story_hook_core.js stagedMarkdownWarnings)에 맞춘다. 콜론/공백은
  # 전각 문자를 넣은 대괄호 집합 대신 선택식을 쓴다(C/GBK에서는 집합이 단일 바이트로 나뉘어 누락). name 필드는
  # grep -i로 대소문자를 구분하지 않는다.
  case "$file" in
    본문.md|*/본문.md|본문/*|*/본문/*)
      HARDCODED=$(grep -nE "(身高|体重|年龄)([[:space:]]|　)*(：|:)([[:space:]]|　)*[0-9]+" "$FULL_PATH" 2>/dev/null || true)
      if [ -n "$HARDCODED" ]; then
        WARNINGS="$WARNINGS$NL⚠ $file: 正文硬编码角色属性，应引用设定文件：$NL$HARDCODED"
      fi
      ;;
  esac

  # 인물 카드만 검사한다. 설정/에는 관계.md、소재방향.md、문체.md、세계관/*、세력/* 같은 프로젝트 설정도 있으며
  # 원래 名字/姓名 필드가 없어 전체를 검사하면 매 커밋마다 거짓 경고가 화면을 채우고 위의
  # 실제 하드코딩 경고를 묻어 버린다(validate-story-commit.sh와 같은 판정 기준).
  IS_CHARACTER_SHEET=false
  case "$file" in
    설정/인물/*|*/설정/인물/*|설정/인물/*|*/설정/인물/*)
      IS_CHARACTER_SHEET=true
      ;;
    설정/*/*|*/설정/*/*)
      # 세계관/세력/보고서/원리/인물 관계 등 인물 카드 외 하위 디렉터리는 통째로 건너뛴다.
      ;;
    설정/*|*/설정/*)
      case "${file##*/}" in
        관계.md|소재방향.md|소재본문안내.md|문체.md|세계규칙.md|세계관.md|특전.md|배경설정.md) ;;
        *) IS_CHARACTER_SHEET=true ;;
      esac
      ;;
  esac
  if [ "$IS_CHARACTER_SHEET" = true ] &&
    ! grep -qiE "^([[:space:]]|　)*(名字|姓名|名称|name)([[:space:]]|　)*(：|:)" "$FULL_PATH" 2>/dev/null; then
    WARNINGS="$WARNINGS$NL⚠ $file: 设定文件缺少 name/名字 必填字段。"
  fi
done <<STORY_STAGED_EOF
$STAGED
STORY_STAGED_EOF

if [ -n "$WARNINGS" ]; then
  echo "=== Story Commit Warnings（advisory only）==="
  # printf의 %s를 쓴다(%b나 echo -e 금지). $WARNINGS에는 grep -n이 추출한 작가 원문이 들어 있으며
  # 그 안의 `\c`(Windows 경로 C:\code에도 포함)가 출력을 종료해 이후 경고를 모두 삼킬 수 있다.
  printf '%s\n' "$WARNINGS"
  echo "=== End Warnings ==="
fi

) || true
### story-hooks: END ###
