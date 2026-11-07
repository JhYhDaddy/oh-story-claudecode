#!/bin/bash
# session-start.sh — 프로젝트 상태와 집필 컨텍스트 요약 표시
# 설계 원칙: 정보가 없으면 완전히 조용히 아무것도 출력하지 않아 컨텍스트 오염을 막는다.
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
# 주입 문자열은 리터럴 `\n` 대신 실제 NL로 합친다. 출력은 printf %s여야 한다(끝 주석 참조).
NL=$'\n'
OUTPUT=""
HAS_CONTENT=false

# 최소 사전 검사 후 source한다. 그래야 lib가 없어도 복구 안내를 출력할 수 있다.
if [ ! -f "$HOOK_DIR/lib/common.sh" ] || [ ! -f "$HOOK_DIR/lib/sentinel.sh" ]; then
  printf '%s\n' "[WARN] story hook 函数库缺失。重新运行 /story-setup 恢复 .claude/hooks/lib/。"
  exit 0
fi

# 공통 함수 라이브러리 로드
source "$HOOK_DIR/lib/common.sh"
source "$HOOK_DIR/lib/sentinel.sh"

# 바이트 안정 로캘: discover_active_book으로 중국어 제목/경로를 처리한다. 중국어 Windows에서 GBK 로캘을 내보내면
# 로캘 의존 연산이 UTF-8을 멀티바이트로 잘못 해석하므로 C 로캘 바이트 처리로 강제해야 안정적이다(이슈 #164
# 유형). 이 훅에는 내장 Python이 없어 직접 export할 수 있다.
export LC_ALL=C

ROOT=$(project_root)

# story-setup 배포 후 일회성 재시작 확인. 사용자 지정 에이전트는 세션 시작에만 subagent_type으로
# 등록되며 배포 완료 시 .claude/.agents-pending-restart 마커를 남긴다.
# 여기 도달했다면 새 세션에서 에이전트가 다시 로드됐으므로 확인하고 마커를 한 번만 제거한다.
if [ -f "$ROOT/.claude/.agents-pending-restart" ]; then
  OUTPUT+="[INFO] story-setup 刚部署/更新了 agents，本会话已重新加载——story-architect、narrative-writer 等 custom agent 现已注册可用。${NL}"
  OUTPUT+="  若写作 skill 仍提示 spawn 失败 / 降级 solo，说明你还在部署时的旧会话里，请再新开一个 Claude Code 会话。${NL}${NL}"
  HAS_CONTENT=true
  rm -f "$ROOT/.claude/.agents-pending-restart" 2>/dev/null || true
fi

# 배포 자체 점검: .story-deployed가 있지만 훅 파일이 잘못 삭제됐으면 경고한다.
# story_hook_cli.js/story_hook_core.js는 핵심 node 공유 코어다. 삭제되면 check-prose-after-write/
# validate-story-commit/detect-story-gaps가 모두 조용히 약화되므로 목록에 반드시 포함한다.
if sentinel_exists "$ROOT/.story-deployed"; then
  MISSING_HOOKS=""
  for hook in session-start.sh session-end.sh detect-story-gaps.sh pre-compact.sh post-compact.sh validate-story-commit.sh guard-outline-before-prose.sh check-prose-after-write.sh story_hook_cli.js story_hook_core.js lib/common.sh lib/sentinel.sh; do
    if [ ! -f "$ROOT/.claude/hooks/$hook" ]; then
      MISSING_HOOKS+="$hook "
    fi
  done
  if [ -n "$MISSING_HOOKS" ]; then
    OUTPUT+="[WARN] .story-deployed 存在但缺少 hook：$MISSING_HOOKS${NL}"
    OUTPUT+="  修复：重新运行 /story-setup 恢复缺失的 hook。${NL}${NL}"
    HAS_CONTENT=true
  fi

  # node 런타임 탐지: 본문 보완 검사/커밋 형식 안내/연속성 검사는 node 공유 코어를 쓴다(#243). 공식 권장은
  # 네이티브 바이너리 Claude Code이며 npm 설치에만 Node가 있어 네이티브에는 없을 수 있다. 위 세 기능은
  # 조용히 중단되지만 개요 차단은 순수 bash로 계속 작동한다. 보완 검사가 있다고 오해하지 않도록 시작 시 한 번 알린다.
  if ! node -e "" >/dev/null 2>&1; then
    OUTPUT+="[WARN] 检测不到 node 运行时：正文兜底网/commit 格式提示/连续性检查已停用（大纲拦截仍有纯 bash 兜底）。${NL}"
    OUTPUT+="  修复：安装 Node.js（https://nodejs.org，或 nvm / brew install node）后新开会话即可恢复。${NL}${NL}"
    HAS_CONTENT=true
  fi

  AGENTS_VERSION=$(read_sentinel_field agents_version "$ROOT/.story-deployed")
  case "$AGENTS_VERSION" in
    ''|*[!0-9]*)
      OUTPUT+="[WARN] .story-deployed 缺少数字 agents_version。重新运行 /story-setup。${NL}${NL}"
      HAS_CONTENT=true
      ;;
    *)
      if [ "$AGENTS_VERSION" -lt 38 ]; then
        OUTPUT+="[WARN] story-setup agents_version=$AGENTS_VERSION 低于 v38。重新运行 /story-setup 刷新 hooks、agents 和 references（部署后需新开会话）。${NL}${NL}"
        HAS_CONTENT=true
      elif [ "$AGENTS_VERSION" -gt 38 ]; then
        OUTPUT+="[WARN] story-setup agents_version=$AGENTS_VERSION 高于本 hook 支持的 v38。不要降级覆盖；请先更新 oh-story-claudecode。${NL}${NL}"
        HAS_CONTENT=true
      fi
      ;;
  esac

  # 위 agents_version만 런타임 노후화 판단 기준이며 배포물 동작이 바뀔 때만 올린다.
  # setup_skill_version은 스킬 콘텐츠 기준점으로 내용에 따라 독립적으로 바뀐다. 여기서는 존재만 확인하고
  # 버전 비교에 쓰지 않는다. 그렇지 않으면 콘텐츠 변경마다 재배포 필요를 오탐한다.
  for field in setup_skill_version target_cli resolver_strategy references_dir; do
    if [ -z "$(read_sentinel_field "$field" "$ROOT/.story-deployed")" ]; then
      OUTPUT+="[WARN] .story-deployed 缺少 $field 字段。重新运行 /story-setup 刷新部署元信息。${NL}${NL}"
      HAS_CONTENT=true
    fi
  done

  # 여러 환경 배포의 references_dir는 쉼표 구분 경로이므로 각각 검사한다. 전체를 한 경로로 보면 항상 찾지 못해
  # 매 세션마다 참조 자료 번들 누락을 오탐한다.
  REFERENCES_DIR=$(read_sentinel_field references_dir "$ROOT/.story-deployed")
  if [ -n "$REFERENCES_DIR" ]; then
    MISSING_REFS=""
    OLD_IFS=$IFS
    IFS=','
    for REF_ENTRY in $REFERENCES_DIR; do
      REF_ENTRY=$(printf '%s' "$REF_ENTRY" | LC_ALL=C sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
      [ -n "$REF_ENTRY" ] || continue
      REFERENCES_PATH=$(resolve_project_path "$REF_ENTRY")
      if [ ! -d "$REFERENCES_PATH" ] || ! find "$REFERENCES_PATH" -maxdepth 1 -type f -name "*.md" -print -quit 2>/dev/null | grep -q .; then
        MISSING_REFS="${MISSING_REFS}${MISSING_REFS:+, }${REF_ENTRY}"
      fi
    done
    IFS=$OLD_IFS
    if [ -n "$MISSING_REFS" ]; then
      OUTPUT+="[WARN] story-setup 参考资料包缺失或为空：${MISSING_REFS}。重新运行 /story-setup；若重跑后仍报这条，是 skill 包本身没装全，按你的安装方式重装 oh-story-claudecode（npx skills add 或 marketplace 面板）再部署。${NL}${NL}"
      HAS_CONTENT=true
    fi
  fi
else
  OUTPUT+="[WARN] 写作环境未部署。运行 /story-setup 初始化。${NL}${NL}"
  HAS_CONTENT=true
fi

# git 이력이 있을 때만 브랜치와 최근 커밋 표시
BRANCH=$(git -C "$ROOT" branch --show-current 2>/dev/null || echo "")
if [ -n "$BRANCH" ]; then
  OUTPUT+="=== 写作进度 ===${NL}"
  OUTPUT+="分支：$BRANCH${NL}"
  RECENT=$(git -C "$ROOT" log --oneline -5 2>/dev/null || true)
  if [ -n "$RECENT" ]; then
    OUTPUT+="$RECENT${NL}"
  fi
  OUTPUT+="${NL}"
  HAS_CONTENT=true
fi

# 문맥.md 요약은 현재 위치 부분만 본다. 새 템플릿 앞 7줄은 제목/설명이라 18줄을 읽어 현재 위치 전체(최대 8필드 + 주석)를 포함한다.
BOOK_DIR=$(discover_active_book)
if [ -n "$BOOK_DIR" ] && [ -f "$BOOK_DIR/추적/문맥.md" ]; then
  OUTPUT+="--- 当前位置 ---${NL}"
  # `2>/dev/null || true`는 필수다. 존재하나 읽을 수 없어도 [ -f ]는 참이며 head가 비0으로 종료하면
  # set -e가 즉시 중단한다. OUTPUT은 끝에서만 출력하므로 앞의 [WARN]과 stderr를 모두 잃는다.
  SNAPSHOT=$(head -18 "$BOOK_DIR/추적/문맥.md" 2>/dev/null || true)
  OUTPUT+="${SNAPSHOT}${NL}---${NL}${NL}"
  HAS_CONTENT=true
fi

# 미완료 작품 분석(0보다 클 때만 보고)
if [ -d "$ROOT/작품분석실" ]; then
  # 위와 같이 하위 디렉터리 읽기 불가 시 find 종료 1이 pipefail로 전파되어 set -e가 여기서
  # 아무 바이트도 출력하지 않고 중단한다. `|| true`와 숫자 기본값으로 이 항목만 약화되고 나머지 안내는 전달되게 한다.
  # 최종 상태가 completed가 아닌 것만 센다. _progress.md 개수만 세면 완료 책도 영구 미완료로 오탐한다.
  PROGRESS_COUNT=$(discover_incomplete_analyses "$ROOT" | wc -l | tr -d ' ' || true)
  case "$PROGRESS_COUNT" in ''|*[!0-9]*) PROGRESS_COUNT=0 ;; esac
  if [ "$PROGRESS_COUNT" -gt 0 ]; then
    OUTPUT+="[INFO] 작품분석실/ 中有 $PROGRESS_COUNT 个未完成拆文。运行 /story-long-analyze 或 /story-short-analyze。${NL}"
    HAS_CONTENT=true
  fi
fi

# 버전 갱신 확인: 수동적 안내, 24시간당 최대 한 번, 실패해도 세션에 영향 없음. 끄기: export STORY_NO_UPDATE_CHECK=1
story_update_check() {
  [ -n "${STORY_NO_UPDATE_CHECK:-}" ] && return 0
  command -v curl >/dev/null 2>&1 || return 0
  local vfile=""
  [ -f "$ROOT/.claude/skills/story/VERSION" ] && vfile="$ROOT/.claude/skills/story/VERSION"
  [ -z "$vfile" ] && [ -f "$HOME/.claude/skills/story/VERSION" ] && vfile="$HOME/.claude/skills/story/VERSION"
  [ -n "$vfile" ] || return 0
  local cur; cur=$(tr -dc '0-9.' < "$vfile" 2>/dev/null) || return 0
  [ -n "$cur" ] || return 0
  local cache="${HOME:-$ROOT}/.claude/.story-update-cache"
  local now; now=$(date +%s 2>/dev/null) || return 0
  local last=0 latest=""
  if [ -f "$cache" ]; then
    last=$(sed -n '1p' "$cache" 2>/dev/null || echo 0)
    latest=$(sed -n '2p' "$cache" 2>/dev/null || echo "")
  fi
  case "$last" in ''|*[!0-9]*) last=0;; esac
  local checked=0
  if [ "$((now - last))" -ge 86400 ]; then
    checked=1
    latest=$(curl -fsS --max-time 5 "https://api.github.com/repos/zenstory-ai/oh-story-claudecode/releases/latest" 2>/dev/null \
      | grep -o '"tag_name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | grep -o '[0-9][0-9.]*' | head -1) || latest=""
    # 성공/실패 모두 타임스탬프를 쓴다. 실패 시 latest를 비워 실패 캐시로 삼지 않으면 GitHub 접근 불가 환경은 매 세션마다
    # curl을 5초씩 기다리고도 안내를 받을 수 없다.
    printf '%s\n%s\n' "$now" "$latest" > "$cache" 2>/dev/null || true
  fi
  # 안내 자체도 빈도를 제한한다. 캐시의 latest는 계속 값이 있어 checked를 보지 않으면 같은 버전을 매 세션 알리게 되어
  # 24시간당 최대 한 번 약속을 어긴다(이전 구현은 네트워크 요청만 제한).
  [ "$checked" -eq 1 ] || return 0
  [ -n "$latest" ] || return 0
  if [ "$latest" != "$cur" ] && [ "$(printf '%s\n%s\n' "$cur" "$latest" | sort -t. -k1,1n -k2,2n -k3,3n | tail -1)" = "$latest" ]; then
    OUTPUT+="[INFO] 网文工具箱有新版本 v${latest}（当前 v${cur}）。更新：npx skills add zenstory-ai/oh-story-claudecode -y -g 后重跑 /story-setup；或对 /story 说“检查更新”。关掉提醒：export STORY_NO_UPDATE_CHECK=1${NL}"
    HAS_CONTENT=true
  fi
}
story_update_check || true

# 실제 내용이 있을 때만 출력하고 없으면 완전히 조용히 종료한다.
# 반드시 %s를 쓴다. $OUTPUT에는 추적/문맥.md 원문 요약과 git log 커밋 제목이 들어 있다. %b는
# `\b`, `\n`을 확장해 백업 경로 D:\backup\novel을 존재하지 않는 경로로 바꾸고 컨텍스트에 원시 0x08을 넣는다.
# `\c`(커밋 제목의 C:\code에도 포함)는 printf를 즉시 종료해 뒤의 --- 마무리와
# 작품 분석 [INFO], 새 버전 [INFO]를 모두 조용히 버린다. 구분은 위 ${NL} 실제 줄바꿈으로 한다.
if [ "$HAS_CONTENT" = true ]; then
  printf '%s' "$OUTPUT"
fi
