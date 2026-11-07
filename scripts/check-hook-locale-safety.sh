#!/bin/bash
# check-hook-locale-safety.sh — Windows 중국어 GBK 로캘에서 배포 훅의 바이트 안전성을 보호한다.
#
# 배경(이슈 #164 유형): 배포 훅은 사용자 Windows Git Bash에서 실행된다. GBK/GB2312 로캘을 내보내면
# gawk/GNU sed/GNU grep과 bash 와일드카드가 UTF-8 중국어 내용/경로의 멀티바이트를 잘못 디코딩해
# 보호가 조용히 실패한다(오차단 또는 누락). 훅에서 `export LC_ALL=C`로 바이트 일치를 사용해 해결한다.
#
# 이 검사는 로캘과 무관한 정적 검사(모든 CI에서 실행 가능)이며 동작 회귀 검사인
# scripts/test-hook-encoding-portable.sh(실제 GBK 로캘에서 훅을 처음부터 끝까지 실행)를 보완한다.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
  echo "Error: not in a git repository"
  exit 1
fi
HOOKS_DIR="$REPO_ROOT/skills/story-setup/references/templates/hooks"

echo "Hook locale-safety Guard"
echo "========================"

fail=0

# 검사 1: 중국어 내용/경로를 처리하는 모든 배포 훅은 export LC_ALL=C로 GBK에서 바이트 일치를 사용해야 한다.
# node 공유 코어를 호출하는 훅(guard-outline/validate-story-commit)은 export 위치에도 조건이 있다(각 파일 주석 참조).
# 하지만 모두 해당 export를 포함해야 한다.
# 목록을 수동 복사하지 않고 hooks 최상위 *.sh를 열거한다(lib/는 검사 3의 명령별 LC_ALL=C로 관리). 새 훅도
# 자동 검사한다. 이전 수동 목록은 check-prose-after-write.sh를 누락했는데, 그 안의 `case "$BASE" in 본문.md)`는
# export LC_ALL=C의 바이트 비교에 전적으로 의존하므로 누락은 해당 훅을 전혀 검사하지 못한다는 뜻이다.
# 최소 목록은 필수 존재 여부만 확인한다. 훅이 잘못 삭제됐을 때 열거되지 않았다고 거짓 통과하면 안 된다.
REQUIRED_LOCALE_HOOKS="check-prose-after-write detect-story-gaps guard-outline-before-prose validate-story-commit session-start session-end pre-compact post-compact"
for h in $REQUIRED_LOCALE_HOOKS; do
  if [ ! -f "$HOOKS_DIR/$h.sh" ]; then
    echo "FAIL: 预期的 locale 敏感 hook 不存在：$h.sh"
    fail=1
  fi
done
while IFS= read -r f; do
  [ -n "$f" ] || continue
  if ! grep -qE '^[[:space:]]*export[[:space:]]+LC_(ALL|CTYPE)=C\b' "$f"; then
    echo "FAIL: $(basename "$f") 缺少 export LC_ALL=C（GBK 区域下中文匹配会乱，issue #164 同类）"
    fail=1
  fi
done < <(find "$HOOKS_DIR" -maxdepth 1 -name '*.sh' -type f | sort)
[ "$fail" -eq 0 ] && echo "OK: locale 敏感 hook 均已 export LC_ALL=C"

# 검사 2: 배포 훅 정규식에서 전각 문자가 포함된 대괄호 문자 집합(예: [：:])을 금지한다.
# UTF-8 로캘에서만 올바르며 C/GBK에서는 단일 바이트로 분리돼 일치를 놓친다. 반드시 (：|:) 같은 선택식으로 바꾼다.
# `[` 바로 뒤의 전각 콜론/세미콜론/쉼표/마침표 등 일반 전각 문장부호를 바이트로 찾는다. 전체 줄 주석은 건너뛴다.
# -r에는 --include와 함께 디렉터리를 전달한다. "$HOOKS_DIR"/*.sh는 최상위 파일만 펼쳐 -r이 무의미해지고
# lib/common.sh와 lib/sentinel.sh의 문자 집합은 하나도 검사하지 못한다.
BRACKET_HITS="$(LC_ALL=C grep -rnE '\[[^]]*(：|；|，|。|！|？|、)' "$HOOKS_DIR" --include='*.sh' 2>/dev/null \
  | grep -vE ':[0-9]+:[[:space:]]*#' || true)"
if [ -n "$BRACKET_HITS" ]; then
  echo "FAIL: 部署 hook 正则里出现含全角字符的方括号字符组（C/GBK 区域会漏匹配，改用交替 (A|B)）："
  echo "$BRACKET_HITS"
  fail=1
else
  echo "OK: 未发现含全角字符的方括号字符组"
fi

# 검사 3: hooks/lib/ 함수 라이브러리는 LC_ALL=C를 직접 export하지 않는다(호출자가 로캘 결정). 중국어 제목/경로를
# 처리하는 sed/grep에 명령별 LC_ALL=C가 필요하다. 없으면 GBK에서 trim이 illegal byte sequence를 내고
# .active-book 내용이 비어 find의 첫 번째 책으로 잘못 해석된다.
# common.sh만 고정하지 말고 lib/ 전체를 검사한다. sentinel.sh도 session-start에서 재사용하므로 파일명을 고정하면
# 새 함수 라이브러리가 자동으로 검사를 면제받는다.
if [ -d "$HOOKS_DIR/lib" ]; then
  # grep -n에 파일명 접두어(-H)를 붙이고 :[0-9]+:[[:space:]]*#으로 주석 줄을 제외한다.
  BARE_TEXT_TOOL="$(grep -HnE '(^|[^=[:alnum:]_])(sed|grep)[[:space:]]' "$HOOKS_DIR/lib"/*.sh 2>/dev/null \
    | grep -vE 'LC_ALL=C' | grep -vE ':[0-9]+:[[:space:]]*#' || true)"
  if [ -n "$BARE_TEXT_TOOL" ]; then
    echo "FAIL: hooks/lib 有未加 LC_ALL=C 的 sed/grep（GBK 下处理中文书名会乱）："
    echo "$BARE_TEXT_TOOL"
    fail=1
  else
    echo "OK: hooks/lib 的 sed/grep 均已 LC_ALL=C"
  fi
fi

exit "$fail"
