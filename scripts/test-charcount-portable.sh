#!/bin/bash
# test-charcount-portable.sh — 크로스 플랫폼 문자 수 명령이 주요 세 플랫폼과 Windows
# Microsoft Store 자리표시자 상황에서도 중국어 문자 수를 정확히 세는지 검증한다.
#
# 배경: 스킬 문서는 아래 탐색 명령으로 글자 수를 세도록 요구한다. Windows에서 python.org 설치 후에도
# `python3`가 Microsoft Store 자리표시자를 실행해 종료 49로 조용히 실패할 수 있으므로
# python3 -> python -> py 순으로 실제 인터프리터를 찾아야 한다. GitHub windows-latest에는 사용 가능한
# python3가 있어 --stub 모드가 종료 49의 가짜 python3를 삽입해 실제 장애를 재현한다.
#
# 사용법:
#   bash scripts/test-charcount-portable.sh           # 실제 인터프리터 사용
#   bash scripts/test-charcount-portable.sh --stub     # Store 자리표시자 재현(종료 49)
#
# story-short-write/references/short-format.md의 글자 수 통계 절 첫 bash 블록에서 명령을 직접
# 추출해 실행한다. 복사하지 않아 문서가 바뀌면 새 명령을 검사한다. check-python-invocation.sh는
# 문서의 python3 직접 호출 회귀를 막고 이 스크립트는 명령이 실제로 정확한 결과를 내는지 검사한다.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOC="$REPO_ROOT/skills/story-short-write/references/short-format.md"
COUNT_BLOCK="$(awk '/^## (字数统计|글자 수 계산)/{s=1;next} s&&/^```bash$/{b=1;next} b&&/^```$/{exit} b' "$DOC")"
case "$COUNT_BLOCK" in
  *PYBIN*) ;;
  *) echo "FAIL: 未能从 $DOC 的「字数统计」节抽到探测 + 统计命令" >&2; exit 1 ;;
esac

STUB=0
[ "${1:-}" = "--stub" ] && STUB=1

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# 중국어 디렉터리와 파일명으로 이슈 #121의 경로 상황을 재현한다.
BOOK_DIR="$WORK/小说项目/第一卷"
mkdir -p "$BOOK_DIR"
# 코드 포인트 12개: 中文字数测试(6) + ABC(3) + 123(3), 끝 줄바꿈 없음
printf '%s' '中文字数测试ABC123' > "$BOOK_DIR/본문.md"
EXPECT=12

# 실제 사용 가능한 인터프리터를 먼저 기록한다. 스텁은 자체 완결적이어야 하며 현재 기기에
# python3와 python/py가 함께 있다고 가정하지 않는다(일부 macOS는 python3만 있음).
REAL_PYTHON=""
for candidate in python3 python py; do
  if "$candidate" -c "" >/dev/null 2>&1; then
    REAL_PYTHON="$(command -v "$candidate")"
    break
  fi
done
[ -n "$REAL_PYTHON" ] || { echo "FAIL: no working Python interpreter" >&2; exit 1; }

if [ "$STUB" -eq 1 ]; then
  # 항상 exit 49인 가짜 python3를 PATH 맨 앞에 넣어 Windows Store 자리표시자를 재현한다.
  FAKEBIN="$WORK/fakebin"
  mkdir -p "$FAKEBIN"
  printf '#!/bin/sh\nexit 49\n' > "$FAKEBIN/python3"
  printf '#!/bin/sh\nexec "%s" "$@"\n' "$REAL_PYTHON" > "$FAKEBIN/python"
  chmod +x "$FAKEBIN/python3"
  chmod +x "$FAKEBIN/python"
  PATH="$FAKEBIN:$PATH"
  export PATH
  echo "[stub] python3 现在固定 exit 49（模拟 Microsoft Store 占位程序）"
fi

# 책 디렉터리에서 문서 명령을 그대로 실행한다(상대 경로 본문.md). 스킬에서 모델이 쓰는 방식과 같다.
# 먼저 프로젝트/본문 디렉터리로 cd한 뒤 상대 경로를 쓴다. Windows Git Bash에서 절대 POSIX 경로를
# (/tmp/...、/c/...) 네이티브 Windows Python에 바로 넘기면 C:\tmp\...로 해석해 파일을 찾지 못한다.
# 상대 경로는 자식 프로세스의 실제 cwd로 해석해 세 플랫폼이 같다. 마지막 줄은 선택한 인터프리터를 보고해 스텁 단언에 쓴다.
OUT="$(cd "$BOOK_DIR" && eval "$COUNT_BLOCK"; printf '\n__PYBIN=%s\n' "${PYBIN:-}")"
PYBIN="$(printf '%s\n' "$OUT" | sed -n 's/^__PYBIN=//p')"
GOT="$(printf '%s\n' "$OUT" | sed '/^__PYBIN=/d;/^$/d')"

echo "selected interpreter: $PYBIN"
echo "char count: $GOT (expect $EXPECT)"

fail=0
if [ "$GOT" != "$EXPECT" ]; then
  echo "FAIL: 字符数不符（中文路径或解释器问题）"
  fail=1
fi
if [ "$STUB" -eq 1 ] && [ "$PYBIN" = "python3" ]; then
  echo "FAIL: stub 模式下仍选中了坏掉的 python3，回退链没生效"
  fail=1
fi
if [ "$fail" -eq 0 ]; then
  echo "PASS"
fi
exit "$fail"
