#!/bin/bash
# sentinel.sh — .story-deployed 표식 필드를 읽는 유틸리티 함수
# .story-deployed는 YAML key: value 형식(yq 없이 awk 단일 프로세스로 파싱)
# source 시 호출자의 셸 옵션을 덮지 않도록 set -euo pipefail을 넣지 않는다.

sentinel_file() {
  if [ -n "${SENTINEL_FILE:-}" ]; then
    printf '%s\n' "$SENTINEL_FILE"
  elif command -v project_root >/dev/null 2>&1; then
    printf '%s/.story-deployed\n' "$(project_root)"
  else
    printf '%s\n' ".story-deployed"
  fi
}

# read_sentinel_field <field_name> [file]
# 앞뒤 공백과 짝 맞는 따옴표를 제거한 필드값을 출력한다. 파일/필드가 없으면 빈 문자열.
# 항상 return 0으로 pipefail / set -e가 호출자를 종료시키지 않게 한다.
read_sentinel_field() {
  local field="$1"
  local file="${2:-$(sentinel_file)}"
  [ -f "$file" ] || return 0
  awk -v key="${field}:" '
    { sub(/\r$/, "") }
    substr($0, 1, length(key)) == key {
      v = substr($0, length(key) + 1)
      sub(/^[[:space:]]+/, "", v)
      n = length(v)
      if (n >= 2 && substr(v, 1, 1) == "\"" && substr(v, n, 1) == "\"") {
        v = substr(v, 2, n - 2)
      } else if (n >= 2) {
        q = sprintf("%c", 39)
        if (substr(v, 1, 1) == q && substr(v, n, 1) == q) {
          v = substr(v, 2, n - 2)
        }
      }
      sub(/[[:space:]]+$/, "", v)
      print v
      exit
    }
  ' "$file" 2>/dev/null
  return 0
}

# sentinel_exists [file] — 종료 0 / 1
sentinel_exists() {
  [ -f "${1:-$(sentinel_file)}" ]
}
