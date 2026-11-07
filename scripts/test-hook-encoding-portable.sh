#!/bin/bash
# test-hook-encoding-portable.sh — 중국어 Windows에서 배포 훅의 인코딩 견고성 회귀 검사.
#
# 중국어 Windows에는 독립적인 인코딩 함정 두 층이 있다(모두 훅을 조용히 무효화, 이슈 #164).
#   1) Python stdout 기본 cp936(로캘과 무관): print(중국어)가 GBK로 인코딩되어 스크립트 UTF-8
#      리터럴 바이트와 달라 비교가 항상 거짓이다. 해결: sys.stdout.buffer.write(...encode("utf-8")).
#   2) 사용자가 GBK 로캘(LANG=zh_CN.GBK)을 내보내면 gawk/GNU sed/GNU grep/bash 와일드카드가
#      UTF-8 내용/경로를 GBK 멀티바이트로 잘못 해석한다. 해결: 훅의 export LC_ALL=C로 바이트 일치.
#
# 함정 1은 #243에서 훅의 내장 Python을 제거해 없어졌다(node는 UTF-8 stdout 사용). 이 테스트의 범위:
#   1a부: 기본 로캘의 장편/단편 상대 경로 차단과 허용(세 플랫폼 모두).
#   1b/1c부: Windows 드라이브 문자 절대 경로 분류(이슈 #184, 1b는 모든 플랫폼, 1c는 Windows/MSYS만).
#   2부: 실제 GBK 로캘에서 모든 훅을 실행해 함정 2 재현(zh_CN.GBK 계열 로캘 필요).
#          macOS에는 기본 제공, CI Ubuntu는 workflow의 localedef로 생성, Windows Git Bash에 없으면 건너뜀.
# 일반 로캘의 장편/단편 상세 개요 허용·차단은 check-story-setup-deployment.sh TS11에서 검사한다.
#
# 사용법: bash scripts/test-hook-encoding-portable.sh
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
  echo "Error: not in a git repository"
  exit 1
fi
HOOKS_DIR="$REPO_ROOT/skills/story-setup/references/templates/hooks"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fail=0
pass() { echo "  PASS $1"; }
bad()  { echo "  FAIL $1"; fail=1; }
# 상세 개요에 내용이 있어야(#과 공백 제외 30자 이상) 본문 쓰기를 허용한다. 빈 파일은 빈 상세 개요로 차단한다.
write_outline() { printf '%s\n' '# 细纲' '江晨在雨夜推开旧书店的门，发现柜台后坐着失踪三年的师父，两人对视良久。' > "$1"; }

deploy() { # $1 = 프로젝트 루트
  mkdir -p "$1/.claude"
  cp -R "$HOOKS_DIR" "$1/.claude/hooks"
  chmod +x "$1/.claude/hooks"/*.sh "$1/.claude/hooks/lib"/*.sh 2>/dev/null || true
}

echo "Hook encoding portability test (issue #164)"
echo "==========================================="

# 1a/1b/1c부 공유 배포 프로젝트(1c는 추적 state가 있는 책 디렉터리를 따로 생성).
P1="$WORK/p1"; deploy "$P1"

# ===== 1a부: 기본 로캘의 장편/단편 상대 경로(세 플랫폼 모두 실행) =====
# 단편 분기는 순수 bash로 중국어 경로를 판정한다([ -f "$BOOK_DIR/설정.md" ]). #164/#184와 같은 유형이다.
# Windows Git Bash와 macOS bash 3.2에서는 여기서만 실제 실행된다(배포 검사 TS11은 Ubuntu만 실행).
echo "--- Part 1a: relative long/short paths in the default locale ---"
mkdir -p "$P1/book/본문" "$P1/book/개요" "$P1/book/추적" "$P1/short"
# 유효한 state를 저장해 상세 개요 조건만 변수가 되게 한다(state가 없으면 추적 점검이 먼저 차단).
printf '{"schema_version":4,"state_revision":0,"last_committed_chapter":0}\n' > "$P1/book/추적/_tracking-state.json"
printf '> 状态修订：0。\n' > "$P1/book/추적/문맥.md"
run_guard_rel() { # $1 file_path -> 종료 코드
  local ec=0
  printf '{"tool_name":"Write","tool_input":{"file_path":"%s","content":"x"}}' "$1" \
    | CLAUDE_PROJECT_DIR="$P1" bash "$P1/.claude/hooks/guard-outline-before-prose.sh" >/dev/null 2>&1 || ec=$?
  printf '%s' "$ec"
}
[ "$(run_guard_rel 'book/본문/제1장_开端.md')" = 2 ] && pass "long blocked, 细纲 missing" || bad "long should block when 细纲 missing"
: > "$P1/book/개요/상세개요_제1장.md"
[ "$(run_guard_rel 'book/본문/제1장_开端.md')" = 2 ] && pass "long blocked, 细纲 empty" || bad "long should block when 细纲 is empty"
write_outline "$P1/book/개요/상세개요_제1장.md"
[ "$(run_guard_rel 'book/본문/제1장_开端.md')" = 0 ] && pass "long allowed, 细纲 present" || bad "long should allow when 细纲 present"
: > "$P1/short/설정.md"
[ "$(run_guard_rel 'short/본문.md')" = 2 ] && pass "short blocked, 小节大纲 missing" || bad "short should block when 小节大纲 missing"
: > "$P1/short/구간개요.md"
[ "$(run_guard_rel 'short/본문.md')" = 0 ] && pass "short allowed, 小节大纲 present" || bad "short should allow when 小节大纲 present"

# ===== 1b부: Windows 드라이브 문자 절대 경로 분류(이슈 #184, 모든 플랫폼 가능) =====
# Windows + Git Bash에서 Claude Code는 드라이브 문자 절대 경로(F:/... 또는 F:\...)를 전달한다. 이전 case는 /*만 인식해
# 상대 경로로 보고 $ROOT/F:/...로 합쳐 잘못된 개요/를 찾고 상세 개요 누락을 오탐했다. 수정 후에는 절대 경로로 처리한다.
# POSIX에는 실제 드라이브 문자가 없어 반증한다. 테스트 데이터는 이전 코드가 만드는 $ROOT/C:/<book> 아래에만 둔다.
#   수정 후: C:/<book>를 절대 경로로 처리(파일시스템 루트 /C:/<book>, 존재하지 않음) → 데이터 없음 → 차단(2)
#   이전 코드: $ROOT/C:/<book>로 합쳐 데이터 발견 → 허용(0)
# 차단(2)으로 드라이브 경로의 절대 경로 처리를 증명한다. 실제 Windows에서는 같은 처리가 실제 드라이브의
# 상세 개요를 찾아 허용하므로 방향이 반대다. 여기서는 절대 경로 분류 수정만 검증한다.
echo "--- Part 1b: Windows drive-letter absolute path classification (issue #184) ---"
if mkdir -p "$P1/C:/book184/개요" 2>/dev/null && write_outline "$P1/C:/book184/개요/상세개요_제2장.md" 2>/dev/null; then
  run_guard_drive() { # $1 file_path(JSON 이스케이프 적용) -> 종료 코드
    local ec=0
    printf '{"tool_name":"Write","tool_input":{"file_path":"%s","content":"x"}}' "$1" \
      | CLAUDE_PROJECT_DIR="$P1" bash "$P1/.claude/hooks/guard-outline-before-prose.sh" >/dev/null 2>&1 || ec=$?
    printf '%s' "$ec"
  }
  [ "$(run_guard_drive 'C:/book184/본문/제2장_x.md')" = 2 ] \
    && pass "[win] forward-slash drive path treated as absolute (not root-joined)" \
    || bad  "[win] forward-slash drive path was root-joined — issue #184 regression"
  # 실제 JSON에서 역슬래시는 이스케이프된다(\\). json.loads가 단일 역슬래시로 풀어 bash에 전달하고 case 분기가 정규화한다.
  [ "$(run_guard_drive 'C:\\book184\\본문\\제2장_x.md')" = 2 ] \
    && pass "[win] backslash drive path treated as absolute (separators normalized)" \
    || bad  "[win] backslash drive path mishandled — issue #184 regression"
  rm -rf "$P1/C:"
else
  echo "  SKIP: 文件系统不支持含 ':' 的目录名（无法构造盘符 fixture）"
fi

# ===== 1c부: 실제 Windows 드라이브 경로(cygpath, Windows/MSYS만 실행) =====
# 1b는 POSIX 반증이다. 여기서는 실제 Windows/MSYS에서 cygpath로 $P1을 C:/... 드라이브 경로로 바꾸고
# 사용자 동작을 직접 검증한다. 상세 개요가 있으면 허용, 없으면 차단한다. POSIX에 cygpath가 없으면 건너뛴다.
echo "--- Part 1c: real Windows drive-letter path via cygpath (issue #184) ---"
if command -v cygpath >/dev/null 2>&1; then
  WINROOT="$(cygpath -m "$P1" 2>/dev/null || true)"
  case "$WINROOT" in
    [A-Za-z]:/*)
      mkdir -p "$P1/winbook/본문" "$P1/winbook/개요" "$P1/winbook/추적"
      # 이 절은 추적 조건이 아닌 드라이브 경로 해석을 검사한다. 유효한 state로 상세 개요 조건만 변수로 둔다.
      # last_committed를 이 절의 장 번호보다 크게 두어 추적 범위 내 장의 순서 검사를 건너뛴다.
      printf '{"schema_version":4,"state_revision":0,"last_committed_chapter":50}\n' > "$P1/winbook/추적/_tracking-state.json"
      printf '> 状态修订：0。\n' > "$P1/winbook/추적/문맥.md"
      run_guard_win() { local ec=0; printf '{"tool_name":"Write","tool_input":{"file_path":"%s","content":"x"}}' "$1" \
        | CLAUDE_PROJECT_DIR="$P1" bash "$P1/.claude/hooks/guard-outline-before-prose.sh" >/dev/null 2>&1 || ec=$?; printf '%s' "$ec"; }
      write_outline "$P1/winbook/개요/상세개요_제3장.md"
      [ "$(run_guard_win "$WINROOT/winbook/본문/제3장_x.md")" = 0 ] \
        && pass "[win] real drive path allowed when 细纲 present" \
        || bad  "[win] real drive path should allow when 细纲 present"
      rm -f "$P1/winbook/개요/상세개요_제3장.md"
      [ "$(run_guard_win "$WINROOT/winbook/본문/제3장_x.md")" = 2 ] \
        && pass "[win] real drive path blocked when 细纲 missing" \
        || bad  "[win] real drive path should block when 细纲 missing"
      rm -rf "$P1/winbook"
      ;;
    *)
      echo "  SKIP: cygpath present but did not yield a drive-letter path ($WINROOT)"
      ;;
  esac
else
  echo "  SKIP: cygpath not available (not a Windows/MSYS runner)"
fi

# ===== 2부: 실제 GBK 로캘에서 모든 훅 실행 =====
echo "--- Part 2: real GBK locale (LANG/LC_ALL=zh_CN.GBK) end-to-end ---"
# 사용 가능한 GBK 계열 로캘을 탐색한다. Cygwin/MSYS2는 필요할 때 합성해 목록에 없으므로 `locale -a` 대신
# 실제 설정 후 `locale charmap`이 GB 계열 인코딩인지 확인한다. Linux(localedef 생성),
# macOS(기본 제공), Windows Git Bash(Cygwin 합성) 모두 실제 GBK로 실행할 수 있다.
detect_gbk_locale() {
  local cand cm
  for cand in zh_CN.GBK zh_CN.gbk zh_CN.GB18030 zh_CN.gb18030 zh_CN.GB2312 zh_CN.gb2312; do
    cm="$(LC_ALL="$cand" locale charmap 2>/dev/null | tr 'a-z' 'A-Z' | tr -d '-')"
    case "$cm" in GBK|GB18030|GB2312) printf '%s' "$cand"; return 0 ;; esac
  done
  return 1
}
GBK_LOCALE="$(detect_gbk_locale || true)"
if [ -z "$GBK_LOCALE" ]; then
  echo "  SKIP: 系统无可用 zh_CN.GBK 类 locale（Part 2 需真实 GBK 区域）"
else
  echo "  using locale: $GBK_LOCALE"
  GBK() { LANG="$GBK_LOCALE" LC_ALL="$GBK_LOCALE" env "$@"; }
  P2="$WORK/p2"; deploy "$P2"
  git -C "$P2" init -q; git -C "$P2" config user.email t@t.t; git -C "$P2" config user.name t
  # 중간 디렉터리로 중국어 책 제목을 사용해 GBK에서 bash 와일드카드가 NOMATCH가 되는 상황을 재현한다.
  BOOK="$P2/让你管账号"; mkdir -p "$BOOK/본문" "$BOOK/개요" "$BOOK/추적" "$BOOK/설정"
  printf '让你管账号\n' > "$P2/.active-book"

  # 2a guard-outline: 중간 중국어 책 제목 디렉터리 + 중국어 glob
  rg() { local ec=0; printf '{"tool_name":"Write","tool_input":{"file_path":"%s","content":"x"}}' "$1" \
    | GBK CLAUDE_PROJECT_DIR="$P2" bash "$P2/.claude/hooks/guard-outline-before-prose.sh" >/dev/null 2>&1 || ec=$?; printf '%s' "$ec"; }
  [ "$(rg '让你管账号/본문/제1장_开端.md')" = 2 ] && pass "[GBK] guard blocks missing 细纲" || bad "[GBK] guard should block missing 细纲"
  write_outline "$BOOK/개요/상세개요_제1장.md"
  # 상세 개요가 있어도 추적 점검이 성립해야 허용한다(이슈 #305부터 Claude에도 적용). 먼저 유효한
  # state를 저장해야 아래 두 검사가 추적 조건 대신 중국어 glob을 검사한다. 중국어 제목 경로는 node를 통해 공유 코어로 전달해
  # GBK에서도 node가 UTF-8로 경로를 받는지 함께 확인한다(bash는 LC_ALL=C 바이트 처리, node는 로캘과 무관).
  printf '{"schema_version":4,"state_revision":0,"last_committed_chapter":0}\n' > "$BOOK/추적/_tracking-state.json"
  printf '> 状态修订：0。\n' > "$BOOK/추적/문맥.md"
  [ "$(rg '让你管账号/본문/제1장_开端.md')" = 0 ] && pass "[GBK] guard allows present 细纲 (Chinese glob)" || bad "[GBK] guard should allow present 细纲 under GBK"
  [ "$(rg '让你管账号/본문/제001장_开端.md')" = 0 ] && pass "[GBK] guard tolerates zero-pad 제001장" || bad "[GBK] guard should tolerate 제001장 under GBK"
  # 빈 상세 개요 검사는 순수 bash 바이트 계산(LC_ALL=C에서 UTF-8 연속 바이트를 제거해 코드 포인트 계산)으로 GBK에서도
  # 29자 차단과 30자 허용을 구분해야 한다. 중국어 바이트 수를 글자 수로 착각하면 안 되며 제목도 센다(`# 细纲`은 2자).
  printf '%s\n' '# 细纲' '他推门进屋看见师父坐在柜台后面他推门进屋看见师父坐在柜' > "$BOOK/개요/상세개요_제1장.md"
  [ "$(rg '让你管账号/본문/제1장_开端.md')" = 2 ] && pass "[GBK] guard blocks 29-char (empty) 细纲" || bad "[GBK] guard should block a 29-char 细纲 under GBK"
  printf '%s\n' '# 细纲' '他推门进屋看见师父坐在柜台后面他推门进屋看见师父坐在柜台' > "$BOOK/개요/상세개요_제1장.md"
  [ "$(rg '让你管账号/본문/제1장_开端.md')" = 0 ] && pass "[GBK] guard allows 30-char 细纲" || bad "[GBK] guard should allow a 30-char 细纲 under GBK"
  # GBK에서도 추적 조건이 차단해야 한다. 중국어 제목을 node로 전달해 state를 파싱하고 차단 안내에 중국어 상대 경로를 포함한다.
  mv "$BOOK/추적/_tracking-state.json" "$BOOK/추적/_state.bak"
  [ "$(rg '让你管账号/본문/제1장_开端.md')" = 2 ] && pass "[GBK] guard blocks missing tracking state (Chinese book path)" || bad "[GBK] guard should block missing tracking state under GBK"
  mv "$BOOK/추적/_state.bak" "$BOOK/추적/_tracking-state.json"

  # 2b detect-story-gaps: 정상 복선 표를 오탐하지 않고 중국어 책 디렉터리를 찾을 수 있음을 증명한다.
  # F001 상태 已埋 양옆에 전각 공백 U+3000을 하나씩 넣어 LC_ALL=C의 trim도 전각 공백을 인식하는지 확인한다.
  cat > "$BOOK/추적/복선.md" <<'EOF'
| ID | 伏笔内容 | 埋设章节 | 预计回收章节 | 状态{已埋/已回收/已过期/放弃} | 重要度{高/中/低} |
|----|---------|---------|-------------|-----------------------------|----------------|
| F001 | 玉佩身世 | 第1章 | 第20章 |　已埋　| 高 |
| F002 | 师门往事 | 第3章 | 第25章 | 已回收 | 中 |
EOF
  out="$(cd "$P2" && GBK CLAUDE_PROJECT_DIR="$P2" bash .claude/hooks/detect-story-gaps.sh 2>&1 || true)"
  echo "$out" | grep -q '伏笔' && bad "[GBK] detect-story-gaps spuriously warns on normal 伏笔" || pass "[GBK] detect-story-gaps silent on normal 伏笔"
  # 실제 누락(본문>10, 설정<3)을 만들어 중국어 책이 실제 순회됐음을 증명한다(그렇지 않으면 위 무응답은 거짓 양성).
  i=1; while [ "$i" -le 11 ]; do : > "$BOOK/본문/제${i}장.md"; i=$((i+1)); done
  out2="$(cd "$P2" && GBK CLAUDE_PROJECT_DIR="$P2" bash .claude/hooks/detect-story-gaps.sh 2>&1 || true)"
  echo "$out2" | grep -q '让你管账号' && pass "[GBK] detect-story-gaps discovers Chinese book + warns on real gap" || bad "[GBK] detect-story-gaps failed to discover Chinese book under GBK"
  rm -f "$BOOK"/본문/제*장.md

  # 2c validate-story-commit: 전각 콜론 + 전각 공백의 하드코딩 속성을 탐지한다. C/GBK에서 대괄호 문자 집합은
  # 전각 콜론을, [[:space:]]는 전각 공백을 놓치므로 선택식으로 해결한다.
  printf '年龄　：18\n' > "$BOOK/본문/제1장_开端.md"
  git -C "$P2" add -A >/dev/null 2>&1
  cout="$(cd "$P2" && GBK CLAUDE_PROJECT_DIR="$P2" STORY_COMMIT_COMMAND='git commit -m x' bash .claude/hooks/validate-story-commit.sh 2>&1 || true)"
  echo "$cout" | grep -q '본문에 인물 속성을 직접 고정' && pass "[GBK] validate-commit catches fullwidth-colon attr" || bad "[GBK] validate-commit missed fullwidth-colon attr under GBK"

  # 2d lib/common.sh discover_active_book: .active-book이 짧은 중국어 제목을 가리키면 GBK의 trim sed가
  # illegal byte sequence를 내 active가 비고 find의 첫 책으로 잘못 대체된다. session-*/
  # pre-compact/post-compact가 재사용하는 공유 경로를 검사한다. 활성 책은 추적/正文이 없어 대체 탐색이 찾지 못하고
  # 미끼 책에는 추적/이 있어 대체 탐색이 미끼만 찾도록 구성한다. 수정 전 decoy, 수정 후 .active-book을 반환한다.
  P2D="$WORK/p2d"; deploy "$P2D"
  mkdir -p "$P2D/让你管账号/설정" "$P2D/decoy小说/추적"
  printf '让你管账号\n' > "$P2D/.active-book"
  active_path="$(cd "$P2D" && GBK CLAUDE_PROJECT_DIR="$P2D" bash -c 'source ".claude/hooks/lib/common.sh"; discover_active_book' 2>/dev/null)"
  # 바이트 안전 단언: 활성 책은 설정/, 미끼는 추적/이 있다. [ -d ]로 바이트 경로를 직접 stat해 일부 실행 환경의
  # GBK에서 basename이 멀티바이트를 바꿔 거짓 실패하는 것을 피한다. 수정 전은 설정 없는 미끼, 수정 후는 활성 책이다.
  if [ -d "$active_path/설정" ]; then
    pass "[GBK] common.sh discover_active_book honors short Chinese .active-book"
  else
    bad "[GBK] common.sh discover_active_book dropped short Chinese .active-book (resolved [$active_path])"
  fi
fi

echo ""
if [ "$fail" -eq 0 ]; then
  echo "PASS: hook 在盘符路径与真实 GBK 区域下都正确"
else
  echo "FAIL: hook 在某个编码/区域模式下行为不符（中文编码回归）"
fi
exit "$fail"
