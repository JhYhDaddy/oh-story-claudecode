#!/bin/bash
# test-story-continuity.sh — detect-story-gaps.sh의 배치 간 연속성 보완 회귀 테스트
# 보장: ① 본문은 N장까지 갱신됐으나 문맥.md가 이전이면 이어쓰기 상태 카드 지연 안내
#       ② 장 제목 중복이면 변경 안내 ③ state 누락/불일치/손상이면 명확한 경고
#       ④ 정상 프로젝트(state/컨텍스트 revision 일치, 컨텍스트가 본문보다 최신, 제목 고유)는 조용함.
# Codex story_codex_hook.py의 continuity_findings와 같은 발동 조건(Codex는 test-codex-hooks.sh에서 검사).
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
[ -z "$REPO_ROOT" ] && { echo "Error: not in a git repository" >&2; exit 1; }
HOOK="$REPO_ROOT/skills/story-setup/references/templates/hooks/detect-story-gaps.sh"
[ -f "$HOOK" ] || { echo "FAIL: hook not found: $HOOK" >&2; exit 1; }
bash -n "$HOOK" || { echo "FAIL: hook has syntax errors" >&2; exit 1; }

# node가 없으면 건너뜀(연속성 검사는 story_hook_cli.js로 공유 코어 호출, node 미탐지 시 조용함, CI 세 플랫폼은 모두 node 설치).
node -e "" >/dev/null 2>&1 || { echo "test-story-continuity: no node runtime, skipped."; exit 0; }

fails=0
run() { CLAUDE_PROJECT_DIR="$1" bash "$HOOK"; }

# 실제 책 구조: 설정 3개로 본문 과다/설정 부족 경고를 피해 연속성만 검사한다.
make_book() {
  local root="$1"
  mkdir -p "$root/某书/본문" "$root/某书/개요" "$root/某书/추적" "$root/某书/설정"
  printf 'a\n' > "$root/某书/설정/인물.md"
  printf 'b\n' > "$root/某书/설정/世界.md"
  printf 'c\n' > "$root/某书/설정/力量.md"
  printf '卷纲\n' > "$root/某书/개요/권개요.md"
  printf '%s\n' '{"schema_version":4,"state_revision":0,"last_committed_chapter":0}' > "$root/某书/추적/_tracking-state.json"
  printf '%s\n' '> 状态修订：0' > "$root/某书/추적/문맥.md"
}

# ① 추적 지연 + ② 제목 중복
T1="$(mktemp -d)"; make_book "$T1"
printf '旧上下文\n' > "$T1/某书/추적/문맥.md"
sleep 1
printf '# 제1장 决战\n正文。\n' > "$T1/某书/본문/제001장_决战.md"
printf '# 제2장 决战\n正文。\n' > "$T1/某书/본문/제002장_决战.md"
out="$(run "$T1")"
printf '%s' "$out" | grep -q '이어 쓰기 상태 카드가 더 오래되었습니다' || { echo "FAIL: 追踪 staleness 未触发"; echo "$out" >&2; fails=$((fails+1)); }
printf '%s' "$out" | grep -q '제목 중복' || { echo "FAIL: 标题去重 未触发"; echo "$out" >&2; fails=$((fails+1)); }
rm -rf "$T1"

# ③ state 불일치/손상/누락 모두 경고해야 함
for kind in mismatch malformed missing; do
  T_META="$(mktemp -d)"; make_book "$T_META"
  printf '# 제1장 开端\n正文。\n' > "$T_META/某书/본문/제001장_开端.md"
  case "$kind" in
    mismatch) printf '%s\n' '{"schema_version":4,"state_revision":1,"last_committed_chapter":0}' > "$T_META/某书/추적/_tracking-state.json" ;;
    malformed) printf '%s\n' '{not-json' > "$T_META/某书/추적/_tracking-state.json" ;;
    missing) rm -f "$T_META/某书/추적/_tracking-state.json" ;;
  esac
  out="$(run "$T_META")"
  case "$kind" in
    mismatch) printf '%s' "$out" | grep -q '상태 리비전' || { echo "FAIL: mismatched state 未触发"; echo "$out" >&2; fails=$((fails+1)); } ;;
    malformed) printf '%s' "$out" | grep -q '해석할 수 없습니다' || { echo "FAIL: malformed state 未触发"; echo "$out" >&2; fails=$((fails+1)); } ;;
    missing) printf '%s' "$out" | grep -q '_tracking-state.json이 없습니다' || { echo "FAIL: missing state 未触发"; echo "$out" >&2; fails=$((fails+1)); } ;;
  esac
  rm -rf "$T_META"
done

# ④ 정상 프로젝트: 컨텍스트가 본문보다 최신, 제목 고유 → 조용함
T2="$(mktemp -d)"; make_book "$T2"
printf '# 제1장 开端\n正文。\n' > "$T2/某书/본문/제001장_开端.md"
printf '# 제2장 转折\n正文。\n' > "$T2/某书/본문/제002장_转折.md"
sleep 1
printf '%s\n' '> 状态修订：0' '新上下文，已更新到제2장' > "$T2/某书/추적/문맥.md"
out="$(run "$T2")"
[ -z "$out" ] || { echo "FAIL: 干净项目应静默，却输出："; echo "$out" >&2; fails=$((fails+1)); }
rm -rf "$T2"

# ⑤ 단편 프로젝트(추적/ 없음): 문맥.md가 없어 지연을 검사하지 않고 오탐도 하지 않음
T3="$(mktemp -d)"
mkdir -p "$T3/단편/본문" "$T3/단편/설정"
printf 'a\n' > "$T3/단편/설정/인물.md"; printf 'b\n' > "$T3/단편/설정/世界.md"; printf 'c\n' > "$T3/단편/설정/力量.md"
printf '# 제1장 起\n正文。\n' > "$T3/단편/본문/제001장_起.md"
mkdir -p "$T3/단편/개요"; printf '개요\n' > "$T3/단편/개요/권개요.md"
out="$(run "$T3")"
printf '%s' "$out" | grep -q '이어 쓰기 상태 카드가 더 오래되었습니다' && { echo "FAIL: 短篇无追踪不应报 staleness"; echo "$out" >&2; fails=$((fails+1)); } || true
rm -rf "$T3"

if [ "$fails" -ne 0 ]; then
  echo "Story continuity tests FAILED ($fails)." >&2
  exit 1
fi
echo "Story continuity regression tests passed."
