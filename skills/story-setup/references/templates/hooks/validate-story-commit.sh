#!/bin/bash
# validate-story-commit.sh — git commit 시 형식 검사(경고만, 차단 없음)
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

HOOK_INPUT="${CLAUDE_TOOL_INPUT:-}"
if [ -z "$HOOK_INPUT" ] && [ ! -t 0 ]; then
  HOOK_INPUT="$(cat)"
fi
# 의도적으로 export하지 않는다. 입력이 git/grep/basename 등 모든 자식 프로세스 envp에 들어가면
# 큰 입력에서 execve E2BIG가 난다(Linux 단일 환경 변수 128 KiB 상한). 실제 읽는 node 호출 한 곳에서만
# 명령별로 할당한다(is-git-commit은 stdin 대신 HOOK_INPUT 환경 변수만 읽음).
# 이 훅은 Bash에 연결돼 입력이 명령 문자열뿐이라 작지만 다른 두 훅과 같은 규칙에 맞춰 제한한다.

is_git_commit_command() {
  # node 공유 코어 isGitCommitCommand 사용: STORY_COMMIT_COMMAND를 우선하고 없으면 HOOK_INPUT의
  # command/cmd/script를 찾는다. JS 토큰화 의미로 OpenCode/ZCode와 같다. 인용 안 구분자 같은 경계는
  # 이전 Python shlex와 문서화된 advisory 차이가 있지만 exit 0 비차단 의미에는 영향이 없다.
  # node가 없으면 커밋 아님으로 보고 조용히 허용한다. 보완 검사가 커밋 절차를 막으면 안 된다. 네이티브 설치에
  # node가 없으면 커밋 형식 안내가 중단되고 session-start.sh가 세션 시작에 한 번 알린다.
  node -e "" >/dev/null 2>&1 || return 1
  local CLI; CLI="$(dirname "$0")/story_hook_cli.js"
  [ -f "$CLI" ] || return 1
  HOOK_INPUT="$HOOK_INPUT" node "$CLI" is-git-commit >/dev/null 2>&1
}

# PreToolUse matcher가 너무 넓거나 CLI가 if를 지원하지 않을 수 있어 스크립트 내부에서 자체 확인해야 한다.
# 명확한 git commit 명령이 없으면 조용히 종료해 echo/grep 등의 오작동을 막는다.
if ! is_git_commit_command; then
  exit 0
fi

# 이후 case + grep은 중국어 경로/본문을 비교한다. 중국어 Windows에서 GBK 로캘을 내보내면
# grep이 UTF-8을 GBK 멀티바이트로 잘못 해석하므로 C 로캘 바이트 일치가 필요하다(이슈 #164 유형).
# 입력 디코딩에 영향이 없도록 is_git_commit_command(node 공유 코어) 뒤에 둔다.
export LC_ALL=C

ROOT=$(project_root)
GIT_ROOT=$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null || printf '%s\n' "$ROOT")
# 경고는 리터럴 `\n` 대신 실제 NL로 합치며 출력은 printf %s를 쓴다(끝 주석 참조).
NL=$'\n'
WARNINGS=""

# 커밋할 파일 목록을 가져온다(공백 경로 문제를 피하려고 -z NUL 구분 사용).
while IFS= read -r -d '' file; do
  # md 아닌 파일 건너뜀
  case "$file" in
    *.md) ;;
    *) continue ;;
  esac

  FULL_PATH="$ROOT/$file"
  if [ ! -f "$FULL_PATH" ]; then
    FULL_PATH="$GIT_ROOT/$file"
  fi

  # 본문 파일의 하드코딩된 플롯 값을 검사한다.
  # 일치 의미와 경고 문구는 여러 CLI의 기준 구현인 JS 코어 story_hook_core.js stagedMarkdownWarnings에 맞춘다.
  # Python↔JS 동등성은 scripts/test-prose-net-parity.sh E부가 고정한다.
  # 콜론/공백은 전각 문자를 대괄호 집합에 넣지 않고 선택식을 쓴다. 전각 집합은 C 로캘에서
  # 단일 바이트로 나뉘어 일치를 놓친다. (：|:)는 전각/반각 콜론을 모두 찾고 ([[:space:]]|　)는 LC_ALL=C에서도
  # 전각 공백 U+3000을 인식해 전각 공백 구분의 누락/오판을 막는다.
  case "$file" in
    본문.md|*/본문.md|본문/*|*/본문/*)
      HARDCODED=$(grep -nE "(身高|体重|年龄)([[:space:]]|　)*(：|:)([[:space:]]|　)*[0-9]+" "$FULL_PATH" 2>/dev/null || true)
      if [ -n "$HARDCODED" ]; then
        WARNINGS="$WARNINGS${NL}⚠ $file: 본문에 인물 속성을 직접 고정했습니다. 설정 파일을 참조하세요: ${NL}$HARDCODED"
      fi
      ;;
  esac

  # 인물 카드 필수 필드를 key:value 구조로 검사한다. grep -i는 JS 코어 /i와 맞춰
  # name/NAME/Name을 대소문자 무관하게 찾는다(LC_ALL=C의 -i는 ASCII만 접어 중국어 바이트에 영향 없음).
  #
  # 인물 카드만 검사한다. 설정/에는 artifact-protocols.md의 관계.md(인물 관계도),
  # 소재방향.md(소재 포지셔닝), 문체.md, 소재본문안내.md,
  # 세계관/*, 세력/* 등 프로젝트 설정도 있으며 원래 名字/姓名 필드가 없다. 설정/ 전체를 일괄 검사하면 설정 변경 커밋마다
  # 거짓 경고가 화면을 채워 실제 본문 인물 속성 하드코딩 경고를 묻는다. 설정/角色|人物 하위 파일과
  # 설정/ 직속 평면 인물 카드(인물.md/주인공.md/조연.md/악역.md 등의 사용자 이름)만 검사한다.
  # 나머지 하위 디렉터리와 알려진 프로젝트 파일은 건너뛴다.
  # 네 환경의 기준은 같다. 이 스크립트(Claude), OpenCode .git/hooks/pre-commit, JS 코어
  # isCharacterSheetPath / stagedMarkdownWarnings, Codex _is_character_sheet_path /
  # staged_markdown_warnings 모두 같은 범위로 제한했다. 어느 하나를 바꾸면 네 곳을 함께 바꿔야
  # 같은 커밋에 CLI마다 다른 경고가 나오지 않는다(동등성 테스트 E부가 Python↔JS를 고정).
  # 기준 구현에 맞춘다는 이유로 되돌리면 거짓 경고까지 되살아나므로 되돌리지 않는다.
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
  if [ "$IS_CHARACTER_SHEET" = true ] \
    && ! grep -qiE "^([[:space:]]|　)*(名字|姓名|名称|name)([[:space:]]|　)*(：|:)" "$FULL_PATH" 2>/dev/null; then
    WARNINGS="$WARNINGS${NL}⚠ $file: 설정 파일에 필수 이름 필드(name/名字)가 없습니다."
  fi
done < <(git -C "$ROOT" -c core.quotepath=false diff --cached --relative --name-only --diff-filter=ACM -z -- . 2>/dev/null || true)

if [ -n "$WARNINGS" ]; then
  echo "=== Story Commit Warnings（advisory only）==="
  # 반드시 %s를 쓴다. $WARNINGS에는 grep -n이 추출한 작가 원문이 있어 %b는 본문의 `\n`, `\b`를
  # 확장하고 `\c`(Windows 경로 C:\code에도 포함)는 printf를 종료해 뒤의 모든 파일 경고와
  # 마무리 테두리를 삼킨다. 구분은 위 ${NL} 실제 줄바꿈으로 한다.
  printf '%s\n' "$WARNINGS"
  echo "=== End Warnings ==="
fi

# 항상 exit 0 — 훅이 집필 절차를 막으면 안 된다.
exit 0
