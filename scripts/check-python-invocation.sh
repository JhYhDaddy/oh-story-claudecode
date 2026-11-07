#!/bin/bash
# check-python-invocation.sh — 스킬 문서에서 `python3` 직접 호출을 금지하는 보호 검사.
#
# Windows에서 python.org로 설치해도 `python3`가 Microsoft Store 자리표시자 프로그램을 실행해 종료 코드 49로
# 조용히 실패할 수 있다(이슈 #121). 모든 호출은 먼저 python3 -> python -> py 순으로 사용 가능한 인터프리터를 탐색해야 한다.
#   for PYBIN in python3 python py; do "$PYBIN" -c "" 2>/dev/null && break; done
#   "$PYBIN" -c "..."
#
# python3 다음 공백과 임의의 인수(-c / -m / << / 스크립트 경로 / 따옴표 등)가 오는 모든 직접 호출과
# 공백 없는 리디렉션(python3<<'PY' / python3<스크립트)도 차단한다.
# 후자도 유효한 셸 구문이며 Store 자리표시자를 실행한다. 탐색 목록 `python3 python py`와
# 설명 문구(python3 뒤에 공백 없이 역슬래시 따옴표, 대시, 화살표 등이 오는 경우)는 영향받지 않는다.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
  echo "Error: not in a git repository"
  exit 1
fi

# 직접 호출 형식: python3 + 공백 + 비공백 인수(-c / -m / << / 스크립트 경로 / 따옴표 포함),
# 또는 python3 바로 뒤의 `<`(heredoc `python3<<'PY'`나 입력 리디렉션 `python3<스크립트`는 공백 없이도 실행됨).
# `<` 이외에 바로 붙는 형태(역슬래시 따옴표/대시/화살표/슬래시)는 설명 문구이므로 계속 제외한다.
PATTERN='python3([[:space:]]+[^[:space:]]|<)'
# 탐색 목록 `... in python3 python py ...`는 허용하므로 검색 결과에서 제외한다(PYBIN/c 등 변수명 지원).
ALLOW='python3 python py'

echo "Python Invocation Guard"
echo "======================="

# skills/ 문서와 배포 템플릿 훅을 검사한다(CI scripts 자체는 어떤 호출 형식도 허용하므로 제외).
hits="$(grep -rnE "$PATTERN" "$REPO_ROOT/skills" 2>/dev/null | grep -vF "$ALLOW" || true)"

if [ -n "$hits" ]; then
  echo "FAIL: 发现裸调 python3（Windows 上会 exit 49）："
  echo "$hits"
  echo
  echo "改用解释器探测形态："
  echo '  for PYBIN in python3 python py; do "$PYBIN" -c "" 2>/dev/null && break; done'
  echo '  "$PYBIN" -c "..."'
  exit 1
fi

echo "OK: 未发现裸调 python3"
