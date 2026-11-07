# API 대체 경로로 이미지 생성

세션에 내장 이미지 생성 도구가 없거나 작가가 API 사용을 명시적으로 요청했을 때만 사용합니다. `gpt-image-2`는 base64를 반환하며 요청 본문에 `response_format`을 넣지 않습니다. 참고 이미지가 없으면 텍스트로 이미지를 생성하고, 있으면 이미지 기반 생성을 사용합니다.

## 환경 변수

| 변수 | 필수 | 기본값 | 설명 |
|:-----|:----:|:-----|:-----|
| `GPT_IMAGE_API_KEY` | 예 | — | OpenAI 또는 호환 프록시의 API 키 |
| `GPT_IMAGE_BASE_URL` | | `https://api.openai.com/v1` | 호환 프록시 사용 시 변경 |
| `GPT_IMAGE_MODEL` | | `gpt-image-2` | 새 모델을 시험할 때만 재정의 |
| `GPT_IMAGE_SIZE` | | `1024x1536` | 요청 크기: 판체 3:4는 `768x1024`, 기본 2:3은 `1024x1536`. 실제 크기는 생성 결과를 기준으로 하며 업로드 픽셀 크기는 진입 문서의 내보내기 단계에서 보장 |
| `BOOK_DIR` | 예 | — | `封面/`의 상위 디렉터리. 진입 문서의 「정보 수집」에서 정한 저장 위치 |
| `PROMPT` | 예 | — | 진입 문서에서 템플릿에 따라 구성한 전체 프롬프트 |
| `REF_IMAGE` | | — | 참고 이미지의 로컬 경로 또는 URL. 설정하면 이미지 기반 생성 사용 |

## 텍스트로 이미지 생성(참고 이미지 없음)

```bash
set -euo pipefail
: "${GPT_IMAGE_API_KEY:?请设置 export GPT_IMAGE_API_KEY=你的key}"
: "${PROMPT:?请先 export PROMPT=构建提示词步骤拼好的完整提示词}"
BASE_URL="${GPT_IMAGE_BASE_URL:-https://api.openai.com/v1}"
MODEL="${GPT_IMAGE_MODEL:-gpt-image-2}"
SIZE="${GPT_IMAGE_SIZE:-1024x1536}"
BOOK_DIR="${BOOK_DIR:?请先 export BOOK_DIR=书目录或 ./covers/<书名>}"

mkdir -p "$BOOK_DIR/封面"

# 버전 번호를 증가시켜 이전에 생성한 표지를 덮어쓰지 않음
i=1
while [ -f "$BOOK_DIR/封面/封面_v${i}.png" ]; do i=$((i+1)); done
OUT="$BOOK_DIR/封面/封面_v${i}.png"
RESP=$(mktemp)
trap 'rm -f "$RESP"' EXIT

# jq로 JSON 본문을 구성해 PROMPT의 따옴표·줄바꿈·중국어로 셸 문자열이 손상되지 않게 함
BODY=$(jq -n \
  --arg m "$MODEL" \
  --arg p "$PROMPT" \
  --arg s "$SIZE" \
  '{model:$m, prompt:$p, size:$s}')

curl -fsS --max-time 180 --retry 2 --retry-delay 5 \
  "$BASE_URL/images/generations" \
  -H "Authorization: Bearer $GPT_IMAGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d "$BODY" > "$RESP"

# API 오류 시 즉시 종료해 오류 JSON을 base64로 취급하여 손상된 PNG를 쓰지 않게 함
if jq -e '.error' "$RESP" >/dev/null 2>&1; then
  echo "API error:" >&2
  jq '.error' "$RESP" >&2
  exit 1
fi

# `// empty`는 누락 필드에 "null" 대신 빈 문자열을 출력하며, 아래 -s 검사와 함께 3바이트짜리 가짜 PNG 생성을 방지
jq -er '.data[0].b64_json // empty' "$RESP" | base64 --decode > "$OUT"
[ -s "$OUT" ] || { echo "empty or malformed output: $OUT" >&2; head -c 300 "$RESP" >&2; exit 1; }

# 이전 버전을 바탕으로 세부 조정할 수 있도록 프롬프트 사본 저장
printf '%s\n' "$PROMPT" > "${OUT%.png}.prompt.txt"

file "$OUT"
ls -lt "$BOOK_DIR/封面/"
```

## 이미지 기반 생성(참고 이미지 있음)

아래 `/v1/images/edits` 명령은 `multipart/form-data`로 로컬 이미지를 업로드하며 `Content-Type: application/json`을 추가하지 않습니다. 텍스트 필드는 `--form-string`, 이미지 필드는 `-F image=@path`를 사용합니다.

```bash
set -euo pipefail
: "${GPT_IMAGE_API_KEY:?请设置 export GPT_IMAGE_API_KEY=你的key}"
: "${PROMPT:?请先 export PROMPT=构建提示词步骤拼好的完整提示词}"
BASE_URL="${GPT_IMAGE_BASE_URL:-https://api.openai.com/v1}"
MODEL="${GPT_IMAGE_MODEL:-gpt-image-2}"
SIZE="${GPT_IMAGE_SIZE:-1024x1536}"
BOOK_DIR="${BOOK_DIR:?请先 export BOOK_DIR=书目录或 ./covers/<书名>}"
REF_IMAGE="${REF_IMAGE:?请先 export REF_IMAGE=本地路径或 URL}"

mkdir -p "$BOOK_DIR/封面"

# 버전 번호 자동 증가
i=1
while [ -f "$BOOK_DIR/封面/封面_v${i}.png" ]; do i=$((i+1)); done
OUT="$BOOK_DIR/封面/封面_v${i}.png"
RESP=$(mktemp)
REF_TMP=""
trap '[ -n "$REF_TMP" ] && rm -f "$REF_TMP"; rm -f "$RESP"' EXIT

# URL은 먼저 임시 파일로 다운로드하고 로컬 경로는 바로 사용. 인수 없는 mktemp로 macOS/Linux 동작을 일치시킴.
case "$REF_IMAGE" in
  http://*|https://*)
    REF_TMP=$(mktemp)
    curl -fsSL --max-time 60 -o "$REF_TMP" "$REF_IMAGE"
    REF_LOCAL="$REF_TMP"
    ;;
  *)
    [ -f "$REF_IMAGE" ] || { echo "参考图不存在: $REF_IMAGE" >&2; exit 1; }
    REF_LOCAL="$REF_IMAGE"
    ;;
esac

curl -fsS --max-time 240 --retry 2 --retry-delay 5 \
  "$BASE_URL/images/edits" \
  -H "Authorization: Bearer $GPT_IMAGE_API_KEY" \
  --form-string "model=$MODEL" \
  --form-string "size=$SIZE" \
  --form-string "prompt=$PROMPT" \
  -F "image=@$REF_LOCAL" > "$RESP"

if jq -e '.error' "$RESP" >/dev/null 2>&1; then
  echo "API error:" >&2
  jq '.error' "$RESP" >&2
  exit 1
fi

# `// empty`는 누락 필드에 "null" 대신 빈 문자열을 출력하며, -s 검사와 함께 3바이트짜리 가짜 PNG 생성을 방지
jq -er '.data[0].b64_json // empty' "$RESP" | base64 --decode > "$OUT"
[ -s "$OUT" ] || { echo "empty or malformed output: $OUT" >&2; head -c 300 "$RESP" >&2; exit 1; }

printf '%s\n' "$PROMPT"    > "${OUT%.png}.prompt.txt"
printf '%s\n' "$REF_IMAGE" > "${OUT%.png}.ref.txt"

file "$OUT"
ls -lt "$BOOK_DIR/封面/"
```
