#!/bin/bash
# test-prose-net-parity.sh — 본문 보완용 가벼운 결정론적 검사망의 네 환경 동등성 보호
# 검사망 구현은 Codex `story_codex_hook.py`와 공유 JS 코어 두 개다. Claude/OpenCode/ZCode는
# 각자 바이트가 동일한 코어 복사본을 사용한다. 이 테스트의 보장 네 계층:
#   A. 기능 동등성: Codex Python 검사망과 ZCode 진입점으로 로드한 JS 코어 검사망이 같은 데이터에서
#      문자별로 일치한다. OpenCode/Claude 코어는 동일 바이트 복사본(check-shared-files.sh)이며 plugin.ts가
#      배포 구조로 코어를 로드하고 호출하는지는 test-opencode-plugin.mjs에서 검사하므로 여기서 반복하지 않는다.
#   B. 명령 함수 동등성(CI 필수 보장): 본문 대상 추출/apply-patch 대상/git commit 감지의 순수 함수 3개가
#      Codex Python과 ZCode JS에서 문자별로 일치한다. 보호 없이 수동 복사하다 어긋난 기존 로직을 고정한다.
#   C. 미통합 영역 동등성(CI 필수 보장): 스테이징 Markdown 경고와 개요 차단 판정은 코어에 통합되지 않아 Codex
#      Python과 JS 코어가 각각 구현한다. 데이터로 문자별 비교한다(대소문자 변형 탐지, 경고/차단 문구).
#      의미와 문구는 JS 코어 기준이다. Claude의 두 영역은 별도 순수 bash 구현(validate-story-commit.sh의
#      grep 부분, guard-outline-before-prose.sh 판정 부분)으로 환경 간 문자별 고정은 없으며 동작은
#      check-story-setup-deployment.sh / test-hook-encoding-portable.sh 실행 회귀에서 검사한다.
#   D. Claude bash 본문 쓰기 보호 ↔ JS 코어 동작 동등성(CI 필수 보장): 같은 프로젝트의 같은 쓰기에서
#      bash 차단 여부 == JS 코어 차단 여부를 시나리오별 비교하고 각각 기대 방향도 고정한다(양쪽이 함께 놓쳐도
#      diff가 같을 수 있기 때문). #283에서 다른 세 환경에 추적 조건을 추가할 때 Claude가 한 버전 내내
#      조용히 누락된 공백(이슈 #305)을 메운다. 원인은 bash 영역의 환경 간 단언 부재였다.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
[ -z "$ROOT" ] && { echo "Error: not in a git repository" >&2; exit 1; }

CODEX="$ROOT/skills/story-setup/references/codex/hooks/story_codex_hook.py"
ZCODE="$ROOT/skills/story-setup/references/zcode/hooks/story_zcode_hook.js"
ZCODE_CORE="$ROOT/skills/story-setup/references/zcode/hooks/story_hook_core.js"
CLAUDE_CORE="$ROOT/skills/story-setup/references/templates/hooks/story_hook_core.js"
CLAUDE_COMMIT="$ROOT/skills/story-setup/references/templates/hooks/validate-story-commit.sh"
CLAUDE_GAPS="$ROOT/skills/story-setup/references/templates/hooks/detect-story-gaps.sh"
CLAUDE_GUARD="$ROOT/skills/story-setup/references/templates/hooks/guard-outline-before-prose.sh"
CLAUDE_HOOK_CLI="$ROOT/skills/story-setup/references/templates/hooks/story_hook_cli.js"
STORYCTL="$ROOT/skills/story-long-write/scripts/storyctl.py"
for f in "$CODEX" "$ZCODE" "$ZCODE_CORE" "$CLAUDE_CORE" "$CLAUDE_COMMIT" "$CLAUDE_GAPS" "$CLAUDE_GUARD" "$CLAUDE_HOOK_CLI" "$STORYCTL"; do
  [ -f "$f" ] || { echo "FAIL: missing impl: $f" >&2; exit 1; }
done

fails=0

# ── A. 기능 동등성(Codex Python 검사망 대 JS 코어 검사망) ──
run_functional() {
  command -v node >/dev/null 2>&1 || return 1
  command -v python3 >/dev/null 2>&1 || return 1
  local tmp; tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN

  cat > "$tmp/fixtures.json" <<'EOF'
{
  "clean": "江晨睁开眼天还没亮。\n他要快要狠要赢这是唯一的活路。\n「作为AI管家，我劝你别白费力气。」\n他握紧拳头走向门口。",
  "truncate": "江晨握紧拳头慢慢走向门口。\n江晨冲过去一拳砸在",
  "truncate_astral": "他继续往前走。\n开头😀😀😀😀😀😀😀😀😀😀😀😀😀X",
  "refuse": "夜色压下来。\n作为AI我无法继续创作这部分内容。",
  "refuse_after_quote": "“任务完成。”作为AI，我无法继续创作。",
  "refuse_before_quote": "作为AI，我无法继续创作。“你别怕。”",
  "refuse_after_multiple_quotes": "“甲说完了。”“乙也点头。”我无法继续创作。",
  "refuse_quoted_ok": "“作为AI，我无法继续创作。”",
  "refuse_quoted_with_prefix_ok": "他说：“作为AI，我无法继续创作。”",
  "refuse_english_quoted_ok": "“I cannot continue writing this scene.”",
  "refuse_unclosed_quote": "“任务完成。作为AI，我无法继续创作。",
  "refuse_apostrophe_contractions": "don't 作为AI，我无法继续创作。 John's!",
  "refuse_curly_apostrophe_contractions": "don’t 作为AI，我无法继续创作。 John’s!",
  "refuse_mixed_curly_apostrophe_contractions": "don‘t 作为AI，我无法继续创作。 John’s!",
  "refuse_single_quoted_ok": "他说：'作为AI，我无法继续创作。'然后关了门。",
  "refuse_curly_single_quoted_ok": "他说：‘作为AI，我无法继续创作。’然后关了门。",
  "refuse_name_in_single_quote_ok": "'读完 O'Connor 的信，我无法继续写下去。'她合上笔记本。",
  "refuse_name_in_curly_quote_ok": "‘读完 O’Connor 的信，我无法继续写下去。’她合上笔记本。",
  "refuse_contraction_in_single_quote_ok": "'I can't write. 作为AI，我无法继续创作。'她放下了笔。",
  "refuse_contraction_in_curly_quote_ok": "‘I can’t write. 作为AI，我无法继续创作。’她放下了笔。",
  "refuse_unclosed_apostrophe": "'作为AI，我无法继续创作。 O'Connor 沉默了。",
  "refuse_quote_before_name_ok": "‘我无法继续写下去。’O’Connor 合上了笔记本。",
  "ai_selfref_model": "夜色压下来。\n作为一个AI语言模型，我需要提醒您接下来的情节包含暴力描写。",
  "ai_selfref_assistant": "他推门进来。\n作为一个AI助手，这段内容涉及敏感话题。",
  "ai_selfref_era_ok": "作为一个人工智能时代的产物，他对孤独习以为常。\n他把灯关了。",
  "terminal_banner_ok": "他抬起手按在光屏上。\n【叮！任务完成，奖励已发放】",
  "terminal_ascii_quote_ok": "他站起来推开门。\n他说：\"我回来了。\"",
  "toxic_quote_codename_ok": "他把烟头按进烟灰缸。\n这一战注定是「血屠」的开端，没人料到后来会那样。",
  "engword": "街灯一盏盏亮起。\n按照本章细纲的情节点他该出场了。",
  "repeat": "他握紧拳头一步步走过去缓缓逼近。\n他握紧拳头一步步走过去缓缓逼近。\n他终于停下了。",
  "repeat_seven_ok": "一二三四五六七\n一二三四五六七\n他停下了。",
  "repeat_eight": "一二三四五六七八\n一二三四五六七八\n他停下了。",
  "repeat_astral_seven_ok": "😀😀😀😀😀😀😀\n😀😀😀😀😀😀😀\n他停下了。",
  "repeat_astral_eight": "😀😀😀😀😀😀😀😀\n😀😀😀😀😀😀😀😀\n他停下了。",
  "placeholder": "他打开门。\n（此处省略三百字打斗描写）他赢了。",
  "english_ai": "他说。\nI cannot continue writing this scene for you.",
  "parallel": "要么生，要么死。\n要么战，要么逃。\n要么赢，要么输。\n他做出了选择。",
  "danmaku": "前方高能！\n前方高能！预警。\n这一段我哭了。\n作者加更！",
  "toxic_voice": "他开口了。\n声音不高，第一句却稳稳压住了整个大厅。",
  "toxic_negation": "没有伴奏，没有和声，没有提词器。\n台下静了三秒。",
  "toxic_cross_negation": "不是嚎啕大哭。\n\n也不是扯着嗓子喊不舍。\n\n只是一个人走远了，留在原地的人还站着。",
  "toxic_cross_negation_dialogue_ok": "“不是嚎啕大哭。”\n\n“也不是扯着嗓子喊不舍。”\n\n“只是舍不得。”",
  "toxic_reverse_notis": "是真嗓子，不是修音修出来的。\n他清了清嗓子接着唱。",
  "toxic_forward_notis": "不是没有想过退路，而是根本没有退路。\n他把门关上了。",
  "toxic_trailer": "他放下麦克风朝台下鞠了一躬。\n没人知道，这才刚刚开头。",
  "toxic_trailer_summary": "他放下麦克风朝台下鞠了一躬。\n这一切都结束了。",
  "toxic_trailer_summary_fate": "她把账单折好塞回包里。\n这一夜注定无人入眠。",
  "toxic_trailer_summary_sozhe": "他把钥匙交了出去。\n就这样，一切都结束了。",
  "toxic_trailer_summary_new_chapter": "他收拾好行李。\n新的篇章就此开始。",
  "toxic_trailer_summary_fate_gear": "他握紧了那枚铜钱。\n命运的齿轮开始转动。",
  "toxic_trailer_shubuzhi": "他笑着把门关上。\n殊不知门外早有人等着。",
  "toxic_trailer_imminent": "城门缓缓合拢。\n一场大战即将来临。",
  "toxic_trailer_pressing": "他站在城头往下看。\n黑压压的军阵正朝着城门压过去。",
  "toxic_trailer_alternatives": "他走了。\n谁也不知道他去了哪里。\n谁也没想到会是他。\n这才刚刚开始。\n一场好戏拉开序幕。\n大戏终于拉开帷幕。\n好戏即将开始。\n风暴即将降临。\n潮水正向着堤岸涌来。\n敌军正朝着营地逼了过来。\n骑兵正朝着山口袭过去。\n这一天注定要被记住。\n这一切都说明了问题。\n这一切意味着新生。\n就这样，全部收场。\n就这样，一切都落幕。\n新的旅程就此展开。\n崭新的篇章正在展开。\n新的人生从此开始。",
  "toxic_bare_realize_ok":"那一刻我终于明白，母亲当年为什么总在夜里哭。\n我抓起外套就往门口走。",
  "toxic_summary_subclause_ok": "等这一切结束了，我们就能过上平静幸福的生活了。\n他把门带上了。",
  "toxic_summary_idiom_ok": "世间的这一刻，所有人都接受了命中注定的结局！\n他转身走了。",
  "toxic_dialogue_ok": "「没人知道。」\n他笑了笑接着往前走。",
  "toxic_eitheror_ok": "不是生就是死，他认了。\n他推门走了进去。",
  "toxic_affirm_ok": "是啊，不是他的错。\n他把灯关了。",
  "toxic_shibushi_ok": "他问自己是不是听错了，是不是灯光太晃。\n他揉了揉眼睛。",
  "toxic_question_ok": "是不是他干的，不是我干的。\n他说不清。",
  "toxic_rhetorical_ok": "是挺好的一件事，不是吗。\n他点了点头。",
  "toxic_curtain_ok": "钟声再度响起，比赛正式拉开序幕。\n他站上了台。",
  "toxic_quote_mid_ok": "她的声音不大好听，被人截成“名场面”，但她不在乎。\n台下没有掌声，没有“安可”声，只有此起彼伏的咳嗽。",
  "toxic_multi_tail_ok": "是他的错，不是我的错，不是吗。\n他点了点头。",
  "toxic_exempt_marker_ok": "# 第1章\n<!-- 去味:跳过 -->\n没有伴奏，没有和声，没有提词器。",
  "toxic_exempt_fullwidth_ok": "# 第1章\n<!-- 去味：跳过 -->\n没有伴奏，没有和声，没有提词器。",
  "toxic_exempt_spaced_ok": "# 第1章\n<!--去味 ： 跳过\t-->\n没有伴奏，没有和声，没有提词器。",
  "toxic_exempt_bare_blocked": "# 第1章\n去味:跳过\n没有伴奏，没有和声，没有提词器。",
  "toxic_exempt_other_nets": "# 第1章\n<!-- 去味:跳过 -->\n没有伴奏，没有和声，没有提词器。\n按照本章细纲的情节点他该出场了。",
  "toxic_comment_ok": "他推开门。\n\n<!-- 备注：声音不大，却让人心里一紧 -->\n他走了进去。",
  "toxic_comment_multiline_ok": "他推开门。\n<!-- 备注\n声音不高，却稳稳压住了整个大厅。\n-->\n他走了进去。",
  "toxic_comment_inline": "他推开门。<!-- 备注 -->声音不高，却稳稳压住了整个大厅。",
  "toxic_comment_unclosed": "他推开门。\n<!-- 备注没闭合\n声音不高，却稳稳压住了整个大厅。",
  "toxic_comment_unclosed_after_closed": "<!-- 备注 -->\n他推开门。\n<!-- 没闭合 <!-- 也没闭合\n声音不高，却稳稳压住了整个大厅。",
  "toxic_astral_window_ok": "没人知道他练了多少年。\n“第1排😀😀😀😀😀😀😀😀😀😀”\n“第2排😀😀😀😀😀😀😀😀😀😀”\n“第3排😀😀😀😀😀😀😀😀😀😀”\n“第4排😀😀😀😀😀😀😀😀😀😀”\n“第5排😀😀😀😀😀😀😀😀😀😀”\n“第6排😀😀😀😀😀😀😀😀😀😀”\n“第7排😀😀😀😀😀😀😀😀😀😀”\n“第8排😀😀😀😀😀😀😀😀😀😀”\n“第9排😀😀😀😀😀😀😀😀😀😀”\n“第10排😀😀😀😀😀😀😀😀😀😀”\n“第11排😀😀😀😀😀😀😀😀😀😀”\n“第12排😀😀😀😀😀😀😀😀😀😀”\n“第13排😀😀😀😀😀😀😀😀😀😀”\n“第14排😀😀😀😀😀😀😀😀😀😀”\n“第15排😀😀😀😀😀😀😀😀😀😀”\n“第16排😀😀😀😀😀😀😀😀😀😀”\n“第17排😀😀😀😀😀😀😀😀😀😀”\n“第18排😀😀😀😀😀😀😀😀😀😀”\n“第19排😀😀😀😀😀😀😀😀😀😀”\n“第20排😀😀😀😀😀😀😀😀😀😀”\n“第21排😀😀😀😀😀😀😀😀😀😀”\n“第22排😀😀😀😀😀😀😀😀😀😀”\n“第23排😀😀😀😀😀😀😀😀😀😀”\n“第24排😀😀😀😀😀😀😀😀😀😀”\n“第25排😀😀😀😀😀😀😀😀😀😀”\n“第26排😀😀😀😀😀😀😀😀😀😀”\n“第27排😀😀😀😀😀😀😀😀😀😀”\n“第28排😀😀😀😀😀😀😀😀😀😀”\n“第29排😀😀😀😀😀😀😀😀😀😀”\n“第30排😀😀😀😀😀😀😀😀😀😀”",
  "toxic_trailer_window_ok": "没人知道他练了多少年。\n江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。江晨把这段视频剪了又剪从凌晨剪到天亮每一帧都抠得死死的。\n他把琴盖合上，起了身。"
}
EOF

  python3 - "$CODEX" "$tmp/fixtures.json" > "$tmp/py.txt" <<'PY'
import importlib.util, sys, json
spec = importlib.util.spec_from_file_location("ch", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
fx = json.load(open(sys.argv[2], encoding='utf-8'))
# stdout.buffer로 UTF-8 바이트를 직접 쓴다. Windows의 Python<3.15 텍스트 stdout은 cp1252여서
# 중국어 findings를 print하면 UnicodeEncodeError가 난다(node console.log의 UTF-8 출력과 일치시킴).
for k in sorted(fx):
    line = k + " | " + " ;; ".join(m.prose_net_findings(fx[k]))
    sys.stdout.buffer.write((line + "\n").encode("utf-8"))
PY

  node - "$ZCODE" "$tmp/fixtures.json" > "$tmp/zcode.txt" <<'JS'
const hook = require(process.argv[2])
const fx = require(process.argv[3])
for (const k of Object.keys(fx).sort()) {
  console.log(k, "|", hook.proseNetFindings(fx[k]).join(" ;; "))
}
JS
  if ! diff "$tmp/py.txt" "$tmp/zcode.txt" >/dev/null; then
    echo "FAIL: 功能 parity 不一致（codex python 网 vs zcode JS 网）：" >&2
    diff "$tmp/py.txt" "$tmp/zcode.txt" >&2 || true
    return 3
  fi

  # 기본 규칙은 실제 입력에 기대 결과를 내야 한다. 세 환경이 같은 빈 배열을 냈다는 것만 증명하면 안 된다.
  grep -q '^clean | $' "$tmp/py.txt" || { echo "FAIL: 干净正文被误报" >&2; return 3; }
  grep -q '^refuse | 第2行 메타정보 유출(AI 자기 언급）' "$tmp/py.txt" || { echo "FAIL: 中文 AI 자기 언급未命中" >&2; return 3; }
  grep -q '^refuse_after_quote | 第1行 메타정보 유출(AI 자기 언급）' "$tmp/py.txt" || { echo "FAIL: 对话后的 AI 자기 언급被整行豁免" >&2; return 3; }
  grep -q '^refuse_before_quote | 第1行 메타정보 유출(AI 자기 언급）' "$tmp/py.txt" || { echo "FAIL: 对话前的 AI 자기 언급被整行豁免" >&2; return 3; }
  grep -q '^refuse_after_multiple_quotes | 第1行 메타정보 유출(생성 거부 문구）' "$tmp/py.txt" || { echo "FAIL: 多段对话后的생성 거부 문구被整行豁免" >&2; return 3; }
  grep -q '^refuse_quoted_ok | $' "$tmp/py.txt" || { echo "FAIL: 成对引号内的合法角色台词被误报" >&2; return 3; }
  grep -q '^refuse_quoted_with_prefix_ok | $' "$tmp/py.txt" || { echo "FAIL: 带叙述前缀的成对引号台词被误报" >&2; return 3; }
  grep -q '^refuse_english_quoted_ok | $' "$tmp/py.txt" || { echo "FAIL: 成对引号内的英文角色台词被误报" >&2; return 3; }
  grep -q '^refuse_unclosed_quote | 第1行 메타정보 유출(AI 자기 언급）' "$tmp/py.txt" || { echo "FAIL: 未闭合引号不应跨行/整行豁免" >&2; return 3; }
  grep -q '^refuse_apostrophe_contractions | 第1行 메타정보 유출(AI 자기 언급）' "$tmp/py.txt" || { echo "FAIL: ASCII 缩写撇号被误配成引号跨度，吞掉 AI 자기 언급" >&2; return 3; }
  grep -q '^refuse_curly_apostrophe_contractions | 第1行 메타정보 유출(AI 자기 언급）' "$tmp/py.txt" || { echo "FAIL: 弯撇号缩写吞掉 AI 자기 언급" >&2; return 3; }
  grep -q '^refuse_mixed_curly_apostrophe_contractions | 第1行 메타정보 유출(AI 자기 언급）' "$tmp/py.txt" || { echo "FAIL: 左/右弯撇号被误配成引号跨度，吞掉 AI 자기 언급" >&2; return 3; }
  grep -q '^refuse_single_quoted_ok | $' "$tmp/py.txt" || { echo "FAIL: ASCII 单引号内合法角色台词被误报" >&2; return 3; }
  grep -q '^refuse_curly_single_quoted_ok | $' "$tmp/py.txt" || { echo "FAIL: 弯单引号内合法角色台词被误报" >&2; return 3; }
  grep -q '^refuse_unclosed_apostrophe | 第1行 메타정보 유출(AI 자기 언급）' "$tmp/py.txt" || { echo "FAIL: 词内撇号不应闭合未完成台词" >&2; return 3; }
  for name in refuse_quote_before_name_ok refuse_name_in_single_quote_ok refuse_name_in_curly_quote_ok refuse_contraction_in_single_quote_ok refuse_contraction_in_curly_quote_ok; do
    grep -q "^$name | $" "$tmp/py.txt" || { echo "FAIL: $name 台词内撇号被当成闭引号" >&2; return 3; }
  done
  grep -q '^english_ai | 第2行 메타정보 유출(영문 AI 말투）' "$tmp/py.txt" || { echo "FAIL: 영문 AI 말투未命中" >&2; return 3; }
  grep -q '^engword | 第2行 작업 용어 유출' "$tmp/py.txt" || { echo "FAIL: 작업 용어 유출未命中" >&2; return 3; }
  grep -q '^placeholder | 第2行 자리표시자' "$tmp/py.txt" || { echo "FAIL: 占位符未命中" >&2; return 3; }
  grep -q '^repeat | 第2行 인접 반복' "$tmp/py.txt" || { echo "FAIL: 인접 반복未命中" >&2; return 3; }
  grep -q '^repeat_seven_ok | $' "$tmp/py.txt" || { echo "FAIL: 7 字短行不应触发复读" >&2; return 3; }
  grep -q '^repeat_eight | 第2行 인접 반복' "$tmp/py.txt" || { echo "FAIL: 8 字复读边界未命中" >&2; return 3; }
  grep -q '^repeat_astral_seven_ok | $' "$tmp/py.txt" || { echo "FAIL: 7 个增补面字符不应触发复读" >&2; return 3; }
  grep -q '^repeat_astral_eight | 第2行 인접 반복' "$tmp/py.txt" || { echo "FAIL: 8 个增补面字符的复读边界未命中" >&2; return 3; }

  # 어댑터 본문 검사망은 글자 수를 재지 않는다. 분량 부족 본문은 storyctl 공개 명령만 판정해야 한다.
  # 책임 분리를 고정한다. 이전 90% 알고리즘이 어느 훅에라도 다시 섞이면 외부 출력 회귀가 즉시 실패한다.
  mkdir -p "$tmp/book/개요" "$tmp/book/본문"
  printf '字数目标：1000\n字数口径：visible_chars_v1\n' > "$tmp/book/개요/상세개요_제001장.md"
  python3 - "$tmp/book/본문/제001장_欠账.md" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).write_text("# 第1章\n" + "字" * 800 + "。\n", encoding="utf-8")
PY
  python3 "$STORYCTL" wordcount check \
    --file "$tmp/book/본문/제001장_欠账.md" --target 1000 --chapter 1 \
    > "$tmp/storyctl-wordcount.json"
  python3 - "$tmp/storyctl-wordcount.json" <<'PY'
import json, sys
result = json.load(open(sys.argv[1], encoding="utf-8"))
assert result["schema"] == "story-wordcount-result/v1", result
assert result["metric"] == "visible_chars_v1", result
assert result["actual"] == 801, result
assert result["status"] == "under", result
PY
  [ -z "$(node "$CLAUDE_HOOK_CLI" prose-net "$tmp/book/본문/제001장_欠账.md")" ] || {
    echo "FAIL: Claude Adapter 重新把字数测量混入正文内容网" >&2
    return 3
  }

  git -C "$tmp/book" init -q
  printf '{}\n' | (cd "$tmp/book" && python3 "$CODEX" stop) > "$tmp/codex-stop.json"
  python3 - "$tmp/codex-stop.json" <<'PY'
import json, sys
result = json.load(open(sys.argv[1], encoding="utf-8"))
assert result == {"continue": True}, result
PY

  # 유해 문형 데이터의 무효 검증 방지(양쪽이 같이 틀려도 diff가 통과하므로 기대 출력을 명시적으로 단언):
  # 양성(사용자가 실제 찾은 유해 문장)은 해당 규칙에 걸리고 음성(대사 안/양자택일/확인 표현/是不是/
  # 범위 밖 trailer)은 완전히 조용해야 한다.
  grep -q '^toxic_voice | 第2行 문제 문장 패턴\[voice-contrast\]' "$tmp/py.txt" || { echo "FAIL: 문제 문장 패턴正例 voice-contrast 未命中「声音不高…却」" >&2; return 3; }
  grep -q '^toxic_negation | 第1行 문제 문장 패턴\[negation-parade\]' "$tmp/py.txt" || { echo "FAIL: 문제 문장 패턴正例 negation-parade 未命中「没有…没有…」" >&2; return 3; }
  grep -q '^toxic_cross_negation | $' "$tmp/py.txt" || { echo "FAIL: 跨段「不是/也不是/只是」应由深扫语义复核，不应进轻量 blocking 网" >&2; return 3; }
  grep -q '^toxic_reverse_notis | 第1行 문제 문장 패턴\[reverse-not-is\]' "$tmp/py.txt" || { echo "FAIL: 문제 문장 패턴正例 reverse-not-is 未命中「是真嗓子，不是修音」" >&2; return 3; }
  grep -q '^toxic_forward_notis | 第1行 문제 문장 패턴\[not-is-comparison\]' "$tmp/py.txt" || { echo "FAIL: 문제 문장 패턴正例 not-is-comparison 未命中「不是…，而是…」" >&2; return 3; }
  grep -q '^toxic_trailer | 第2行 문제 문장 패턴\[trailer-ending\]' "$tmp/py.txt" || { echo "FAIL: 문제 문장 패턴正例 trailer-ending 未命中「没人知道，这才刚刚开头」" >&2; return 3; }
  grep -q '^toxic_trailer_summary | 第2行 문제 문장 패턴\[trailer-summary\]' "$tmp/py.txt" || { echo "FAIL: 문제 문장 패턴正例 trailer-summary 未命中「这一切都结束了」" >&2; return 3; }
  grep -q '^toxic_trailer_summary_fate | 第2行 문제 문장 패턴\[trailer-summary\]' "$tmp/py.txt" || { echo "FAIL: 문제 문장 패턴正例 trailer-summary 未命中「这一夜注定无人入眠」" >&2; return 3; }
  # trailer 정규식 두 개의 각 분기마다 양성 하나를 고정한다(이전에는 check-hook-regex-sync의 기준 문자열 grep만 사용).
  for pair in toxic_trailer_summary_sozhe:trailer-summary toxic_trailer_summary_new_chapter:trailer-summary \
      toxic_trailer_summary_fate_gear:trailer-summary toxic_trailer_shubuzhi:trailer-ending \
      toxic_trailer_imminent:trailer-ending toxic_trailer_pressing:trailer-ending; do
    grep -q "^${pair%%:*} | 第2行 문제 문장 패턴\[${pair#*:}\]" "$tmp/py.txt" || { echo "FAIL: 문제 문장 패턴正例 ${pair%%:*} 未命中 ${pair#*:}" >&2; return 3; }
  done
  # 나머지 선택 단어는 각각 한 줄에 한 건씩 탐지되며 수량을 고정한다(예고체 10건 + 상태 요약 8건). 한쪽의 선택 단어를
  # 삭제하거나 바꾸면 문자별 diff 또는 여기의 개수 검사가 실패한다.
  [ "$(grep '^toxic_trailer_alternatives |' "$tmp/py.txt" | grep -o '문제 문장 패턴\[trailer-ending\]' | wc -l | tr -d ' ')" = 10 ] \
    && [ "$(grep '^toxic_trailer_alternatives |' "$tmp/py.txt" | grep -o '문제 문장 패턴\[trailer-summary\]' | wc -l | tr -d ' ')" = 8 ] \
    || { echo "FAIL: trailer 备选词正例未逐行命中（期望 10 条 trailer-ending + 8 条 trailer-summary）" >&2; return 3; }
  grep -q '^toxic_bare_realize_ok | $' "$tmp/py.txt" || { echo "FAIL: 「那一刻…终于明白」审判金句被误报（短篇卖点，本规则不收认知节拍）" >&2; return 3; }
  grep -q '^toxic_summary_subclause_ok | $' "$tmp/py.txt" || { echo "FAIL: 条件从句「等这一切结束了，…」被误报（未落句末断言位）" >&2; return 3; }
  grep -q '^toxic_summary_idiom_ok | $' "$tmp/py.txt" || { echo "FAIL: 成语「命中注定」被跨匹配成 trailer-summary" >&2; return 3; }
  grep -q '^toxic_dialogue_ok | $' "$tmp/py.txt" || { echo "FAIL: 对话内「没人知道」被误报（成对引号应剥除）" >&2; return 3; }
  grep -q '^toxic_cross_negation_dialogue_ok | $' "$tmp/py.txt" || { echo "FAIL: 三段对话内否定被写后 hook 误报（语义审查负责台词 advisory）" >&2; return 3; }
  grep -q '^toxic_eitheror_ok | $' "$tmp/py.txt" || { echo "FAIL: either-or「不是A就是B」被误报" >&2; return 3; }
  grep -q '^toxic_affirm_ok | $' "$tmp/py.txt" || { echo "FAIL: 确认语「是啊，不是…」被误报" >&2; return 3; }
  grep -q '^toxic_shibushi_ok | $' "$tmp/py.txt" || { echo "FAIL: 疑问「是不是」被误报" >&2; return 3; }
  grep -q '^toxic_question_ok | $' "$tmp/py.txt" || { echo "FAIL: 「是不是…」问句起头被误报" >&2; return 3; }
  grep -q '^toxic_rhetorical_ok | $' "$tmp/py.txt" || { echo "FAIL: 反问尾巴「…，不是吗」被误报" >&2; return 3; }
  grep -q '^toxic_curtain_ok | $' "$tmp/py.txt" || { echo "FAIL: 报幕式「正式拉开序幕」被误报" >&2; return 3; }
  grep -q '^toxic_trailer_window_ok | $' "$tmp/py.txt" || { echo "FAIL: 文末 600 字窗口外的「没人知道」被误报" >&2; return 3; }
  grep -q '^toxic_quote_mid_ok | $' "$tmp/py.txt" || { echo "FAIL: 句中引号段未按等长占位截断，规则跨引号拼出假命中" >&2; return 3; }
  grep -q '^toxic_multi_tail_ok | $' "$tmp/py.txt" || { echo "FAIL: 带中间对比项的反问尾巴「…，不是吗」被误报" >&2; return 3; }
  grep -q '^toxic_exempt_marker_ok | $' "$tmp/py.txt" || { echo "FAIL: 标「去味:跳过」的正文문제 문장 패턴未被写后网豁免" >&2; return 3; }
  grep -q '^toxic_exempt_fullwidth_ok | $' "$tmp/py.txt" || { echo "FAIL: 全角冒号豁免标记「去味：跳过」未生效" >&2; return 3; }
  # 제외 마커 구문은 storyctl DESLOP_SKIP와 같다. HTML 주석이어야 하고 안에 공백/탭을 허용한다.
  # 주석 없이 쓴 ‘去味:跳过’는 보이는 본문 텍스트이므로 제외 마커가 아니다.
  grep -q '^toxic_exempt_spaced_ok | $' "$tmp/py.txt" || { echo "FAIL: 带空格的豁免标记 <!--去味 ： 跳过 --> 未生效（与 storyctl 语法不一致）" >&2; return 3; }
  grep -q '^toxic_exempt_bare_blocked | .*문제 문장 패턴' "$tmp/py.txt" || { echo "FAIL: 裸写的「去味:跳过」（不在 HTML 注释里）被当成豁免" >&2; return 3; }
  grep -q '^toxic_exempt_other_nets | 第4行 작업 용어 유출' "$tmp/py.txt" || { echo "FAIL: 豁免标记不应连带关掉문제 문장 패턴以外的网（工程词漏检）" >&2; return 3; }
  grep '^toxic_exempt_other_nets' "$tmp/py.txt" | grep -q '문제 문장 패턴' && { echo "FAIL: 豁免标记在场时문제 문장 패턴仍被推回" >&2; return 3; }
  # HTML 주석(작가 메모/제외 마커)은 본문이 아니다. check-ai-patterns.js와 같은 규칙으로 여러 줄도 가린다. 끝까지
  # 닫히지 않은 `<!--`는 주석이 아니다(`-->` 누락으로 뒤 내용을 숨기면 안 됨). 이전 훅은 가리지 않아 메모의 문형을 차단했지만
  # chapter check 탐지기는 빈 결과를 반환해 두 검사의 기준이 갈렸다.
  for name in toxic_comment_ok toxic_comment_multiline_ok; do
    grep -q "^$name | $" "$tmp/py.txt" || { echo "FAIL: $name HTML 注释里的句式被写后网当문제 문장 패턴（检测器不扫注释）" >&2; return 3; }
  done
  grep -q '^toxic_comment_inline | 第1行 문제 문장 패턴\[voice-contrast\]' "$tmp/py.txt" || { echo "FAIL: 行内注释之后的正文문제 문장 패턴漏检" >&2; return 3; }
  for name in toxic_comment_unclosed toxic_comment_unclosed_after_closed; do
    grep -q "^$name | 第[34]行 문제 문장 패턴\[voice-contrast\]" "$tmp/py.txt" || { echo "FAIL: $name 未闭合的 <!-- 把后文藏起来了" >&2; return 3; }
  done
  # 데이터마다 탐지기와 맞춘다. 훅의 voice-contrast 보고 여부 == check-ai-patterns.js 보고 여부.
  local detector="$ROOT/skills/story-long-write/scripts/check-ai-patterns.js" cname hook_hit det_hit
  for cname in toxic_comment_ok toxic_comment_multiline_ok toxic_comment_inline toxic_comment_unclosed toxic_comment_unclosed_after_closed; do
    node -e 'const fx=require(process.argv[1]);require("fs").writeFileSync(process.argv[2],fx[process.argv[3]])' "$tmp/fixtures.json" "$tmp/$cname.md" "$cname"
    hook_hit=0; grep "^$cname |" "$tmp/py.txt" | grep -q 'voice-contrast' && hook_hit=1
    det_hit=0; node "$detector" --json "$tmp/$cname.md" </dev/null > "$tmp/$cname.json" || true
    grep -q '"voice-contrast"' "$tmp/$cname.json" && det_hit=1
    [ "$hook_hit" = "$det_hit" ] || { echo "FAIL: $cname 写后网（${hook_hit}）与 check-ai-patterns.js（${det_hit}）对 HTML 注释口径不一致" >&2; return 3; }
  done
  grep -q '^toxic_astral_window_ok | $' "$tmp/py.txt" || { echo "FAIL: 引号内 emoji 的占位长度未按 UTF-16 码元对齐，trailer 窗口切点漂移" >&2; return 3; }
  grep -q '^toxic_quote_codename_ok | $' "$tmp/py.txt" || { echo "FAIL: 引号占位替 trailer-summary 的句末 [。！] 伪造终止符（占位字符落进了规则接受位）" >&2; return 3; }

  # AI 자기 지칭(약한 신호)의 무효 검증 방지: 모델명 접미어가 붙은 전형적 퇴화 도입은 거부 표현 없이도 탐지해야 한다.
  # 이전 refuse 데이터는 생성 거부 표현 규칙이 잡아 자기 지칭 규칙을 전혀 검증하지 못했다. 복합명사는 오탐하지 않는다.
  grep -q '^ai_selfref_model | 第2行 메타정보 유출(AI 자기 언급）' "$tmp/py.txt" || { echo "FAIL: AI 자기 언급未命中「作为一个AI语言模型」（无拒绝语）" >&2; return 3; }
  grep -q '^ai_selfref_assistant | 第2行 메타정보 유출(AI 자기 언급）' "$tmp/py.txt" || { echo "FAIL: AI 자기 언급未命中「作为一个AI助手」" >&2; return 3; }
  grep -q '^ai_selfref_era_ok | $' "$tmp/py.txt" || { echo "FAIL: 复合名词「人工智能时代的产物」被 AI 자기 언급误报" >&2; return 3; }

  # 잘림 판정 끝 문장부호: 】(장 끝 시스템 방송 닫기)와 ASCII "(ASCII 인용 닫기) 모두 마무리로 인정한다.
  # 정밀 검사 기준인 check-degeneration.js의 findTruncation과 같으며 실제 잘림은 truncate 데이터가 따로 고정한다.
  grep -q '^terminal_banner_ok | $' "$tmp/py.txt" || { echo "FAIL: 以【…】收尾的章末系统播报被误判잘림 의심" >&2; return 3; }
  grep -q '^terminal_ascii_quote_ok | $' "$tmp/py.txt" || { echo "FAIL: 以 ASCII 收引号收尾的对话被误判잘림 의심" >&2; return 3; }
  grep -q '^truncate | 第2行 잘림 의심' "$tmp/py.txt" || { echo "FAIL: 真截断（结尾无标点）未被检出" >&2; return 3; }
  grep -q '^truncate_astral | 第2行 잘림 의심' "$tmp/py.txt" || { echo "FAIL: 增补面字符结尾的真截断未被检出" >&2; return 3; }
  ! grep '^truncate_astral |' "$tmp/py.txt" | grep -q '�' || { echo "FAIL: 增补面字符摘要被 UTF-16 切坏" >&2; return 3; }
  return 0
}

# ── B. 명령 함수 동등성(Codex Python 대 ZCode JS), CI 필수 보장 ──
# 본문 대상 추출(리디렉션/tee/touch/cp·mv), apply-patch 대상, git commit 감지의 순수 함수 3개는
# (명령 문자열 → 값) 아래 데이터에서 문자별로 같아야 한다. 이전 Python/JS 수동 복사는 보호가 없어 cp·mv 인수 수,
# git 제어어 then/do/else/elif, 서브셸 괄호가 어긋났다. CI 모든 플랫폼에 node+python3가 있어 필수 검사다.
# 참고: 데이터는 양쪽이 합의한 부분집합이다. 인용 안 구분자(echo "a; git commit")와 명령 치환($(git commit))은
# 원래 다르다(Python shlex는 인용을 존중하고 JS는 단순 분할). 이 검사망 범위 밖이며 차단이 아닌 advisory에만 영향이 있다.
run_cmd_parity() {
  command -v node >/dev/null 2>&1 || return 1
  command -v python3 >/dev/null 2>&1 || return 1
  local tmp; tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  cat > "$tmp/cmd.json" <<'EOF'
{
  "redirect": "echo x > book/본문/제1장.md",
  "redirect_clobber": "echo x >| book/본문/제1장.md",
  "redirect_both": "echo x >& book/본문/제1장.md",
  "redirect_fd_dup": "echo book/본문/제1장.md >&2",
  "append": "cat a >> 본문.md",
  "tee": "echo x | tee book/본문/제2장.md",
  "tee_a": "printf y | tee -a 본문.md",
  "tee_double_dash": "printf y | tee -- book/본문/제2장.md",
  "tee_multi": "printf y | tee notes.md book/본문/제2장.md",
  "touch": "touch book/본문/제3장.md",
  "touch_multi": "touch notes.md book/본문/제3장.md",
  "touch_reference": "touch -r book/본문/제1장.md notes.md",
  "cp": "cp src.md book/본문/제4장.md",
  "cp_command_wrapper": "command cp src.md book/본문/제4장.md",
  "cp_command_p_wrapper": "command -p cp src.md book/본문/제4장.md",
  "cp_command_double_dash_wrapper": "command -- cp src.md book/본문/제4장.md",
  "cp_env_unset_short": "env -u FOO cp src.md book/본문/제4장.md",
  "cp_env_unset_long": "env --unset FOO cp src.md book/본문/제4장.md",
  "cp_absolute_binary": "/bin/cp src.md book/본문/제4장.md",
  "cp_destination_directory": "cp draft/제4장.md book/본문/",
  "cp_target_directory": "cp --target-directory=book/본문 draft/제4장.md",
  "install": "install draft.md book/본문/제4장.md",
  "mv2": "mv 본문.md",
  "cp_flag": "cp -f a.md 본문.md",
  "mention": "grep -n book/본문/제1장.md notes.md",
  "redirect_quoted_space": "cat draft.md > \"my book/본문/제1장_x.md\"",
  "redirect_fullwidth_space": "cat draft.md > book/본문/제003장　开局.md",
  "tee_quoted_space": "printf x | tee 'my book/본문/제1장_x.md'",
  "cp_quoted_space": "cp draft.md \"my book/본문/제1장_x.md\"",
  "cp_quoted_operator": "cp draft.md \"book|archive/본문/제11장.md\"",
  "literal_quoted_redirect": "echo '> book/본문/제7장.md'",
  "heredoc_mention": "cat <<EOF\n> book/본문/제7장.md\nEOF",
  "multiple_heredoc_mention": "cat <<A <<B\nfirst\nA\n> book/본문/제7장.md\nB",
  "escaped_heredoc_mention": "cat <<\\EOF\n> book/본문/제7장.md\nEOF",
  "escaped_heredoc_then_redirect": "cat <<\\EOF\nliteral\nEOF\necho x > book/본문/제7장.md",
  "escaped_quote_tee_mention": "printf '%s\\n' \"literal \\\" | tee book/본문/제7장.md\"",
  "nested_shell_redirect": "sh -c 'echo x > book/본문/제7장.md'",
  "nested_shell_combined_flags": "bash -lc 'echo x > book/본문/제7장.md'",
  "quoted_command_substitution_redirect": "echo \"$(echo x > book/본문/제7장.md)\"",
  "quoted_backtick_substitution_redirect": "echo \"`echo x > book/본문/제7장.md`\"",
  "patch_add": "*** Begin Patch\n*** Add File: book/본문/제5장.md\n+본문\n*** End Patch",
  "patch_move": "*** Begin Patch\n*** Update File: draft.md\n*** Move to: book/본문/제6장.md\n+본문\n*** End Patch",
  "patch_move_delete": "*** Begin Patch\n*** Delete File: draft.md\n*** Move to: book/본문/제7장.md\n*** End Patch",
  "patch_move_out": "*** Begin Patch\n*** Update File: book/본문/제8장.md\n*** Move to: draft.md\n+x\n*** End Patch",
  "patch_delete_only": "*** Begin Patch\n*** Delete File: book/본문/제9장.md\n*** End Patch",
  "patch_multi_move": "*** Begin Patch\n*** Add File: notes.md\n+x\n*** Update File: draft.md\n*** Move to: book/본문/제10장.md\n+본문\n*** End Patch",
  "patch_context_move": "*** Begin Patch\n*** Update File: book/본문/제12장.md\n@@\n *** Move to: notes.md\n+본문\n*** End Patch",
  "cd_then_heredoc_redirect": "cd \"/p/书\" && cat > 본문/제022장_x.md <<EOF\nhi\nEOF",
  "cd_chain_tee": "cd /a && cd b && tee 본문/제3장.md",
  "cd_relative_cp": "cd 书 && cp draft.md 본문/제2장.md",
  "cd_clobber_redirect": "cd 书 && cat draft >| 본문/제3장.md",
  "cd_dup_redirect": "cd 书 && echo x >& 본문/제3장.md",
  "cd_amp_redirect": "cd 书 && echo x &> 본문/제3장.md",
  "cd_into_body_redirect": "cd 书/본문 && cat > 제3장.md",
  "cd_into_body_tee": "cd 본문 && tee 제3장.md",
  "cd_redirect_then_pipe": "cd 书 && cat x > 본문/제3장.md 2>&1 | tee log",
  "commit_plain": "git commit -m x",
  "commit_chain": "git add . && git commit -m x",
  "commit_if": "if true; then git commit -m x; fi",
  "commit_for": "for f in *; do git commit -am x; done",
  "commit_subshell": "(cd sub && git commit)",
  "commit_env": "FOO=1 git commit",
  "commit_config": "git -c user.name=x commit",
  "commit_C": "git -C sub commit -m y",
  "noncommit_echo": "echo git commit docs",
  "noncommit_status": "git status && echo done"
}
EOF
  python3 - "$CODEX" "$tmp/cmd.json" > "$tmp/cpy.txt" <<'PY'
import importlib.util, sys, json
spec = importlib.util.spec_from_file_location("ch", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
fx = json.load(open(sys.argv[2], encoding='utf-8'))
for k in sorted(fx):
    c = fx[k]
    line = f"{k} :: pros=[{'|'.join(m.extract_prose_targets_from_command(c))}] patch=[{'|'.join(m.extract_apply_patch_targets(c))}] commit={'1' if m.is_git_commit_command(c) else '0'}"
    sys.stdout.buffer.write((line + "\n").encode("utf-8"))
PY
  node - "$ZCODE" "$tmp/cmd.json" > "$tmp/cjs.txt" <<'JS'
const h = require(process.argv[2])
const fx = require(process.argv[3])
for (const k of Object.keys(fx).sort()) {
  const c = fx[k]
  console.log(`${k} :: pros=[${h.extractProseTargets(c).join("|")}] patch=[${h.extractPatchTargets(c).join("|")}] commit=${h.isGitCommitCommand(c) ? "1" : "0"}`)
}
JS
  if ! diff "$tmp/cpy.txt" "$tmp/cjs.txt" >/dev/null; then
    echo "FAIL: 命令函数 parity 不一致（codex python vs zcode JS）：" >&2
    diff "$tmp/cpy.txt" "$tmp/cjs.txt" >&2 || true
    return 3
  fi
  # 무효 검증 방지: 공백/전각 공백 대상은 온전히 추출해야 한다(양쪽이 같이 틀려도 diff 통과). 문자 집합에서 \s를 제외하면
  # ‘제003장　开局.md’가 ‘제003장’로 잘리고 따옴표를 제외하면 인용 경로 전체를 놓쳐 조용히 허용된다.
  grep -q 'redirect_quoted_space :: pros=\[my book/본문/제1장_x.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: 带空格的引号重定向目标未被整段取出（引号未被尊重）" >&2; return 3; }
  grep -q 'redirect_fullwidth_space :: pros=\[book/본문/제003장　开局.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: 全角空格章名被 \\s 截断（U+3000 不是 shell 分词符）" >&2; return 3; }
  grep -q 'tee_quoted_space :: pros=\[my book/본문/제1장_x.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: 带空格的引号 tee 目标未被整段取出" >&2; return 3; }
  # cd가 있으면 구간별 리디렉션을 검사한다. `>|` `>&` `&>`가 분할로 사라지면 안 되고 본문/로 cd한 뒤 상대 대상도 인식해야 한다.
  for want in 'cd_clobber_redirect :: pros=\[书/본문/제3장.md\]' 'cd_dup_redirect :: pros=\[书/본문/제3장.md\]' \
      'cd_amp_redirect :: pros=\[书/본문/제3장.md\]' 'cd_into_body_redirect :: pros=\[书/본문/제3장.md\]' \
      'cd_into_body_tee :: pros=\[본문/제3장.md\]' 'cd_redirect_then_pipe :: pros=\[书/본문/제3장.md\]'; do
    grep -q "$want" "$tmp/cpy.txt" || { echo "FAIL: cd 后的写正文目标没认出来：$want" >&2; return 3; }
  done
  grep -q 'cp_quoted_space :: pros=\[my book/본문/제1장_x.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: cp 的引号目标被按空白切碎，末位取到了另一本书的路径" >&2; return 3; }
  grep -q 'cp_quoted_operator :: pros=\[book|archive/본문/제11장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: cp 引号目标里的 | 被误当 shell 管道切段，正文守卫会静默放行" >&2; return 3; }
  grep -q 'tee_double_dash :: pros=\[book/본문/제2장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: tee -- 的正文目标未被提取" >&2; return 3; }
  grep -q 'tee_multi :: pros=\[book/본문/제2장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: tee 的第二个正文输出目标未被提取" >&2; return 3; }
  grep -q 'touch_multi :: pros=\[book/본문/제3장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: touch 的第二个正文目标未被提取" >&2; return 3; }
  grep -q 'touch_reference :: pros=\[\]' "$tmp/cpy.txt" \
    || { echo "FAIL: touch -r 的参考源被误判成写入目标" >&2; return 3; }
  grep -q 'literal_quoted_redirect :: pros=\[\]' "$tmp/cpy.txt" \
    || { echo "FAIL: 引号内的重定向示例被误判成真实写入" >&2; return 3; }
  grep -q 'heredoc_mention :: pros=\[\]' "$tmp/cpy.txt" \
    || { echo "FAIL: heredoc 正文中的路径提及被误判成真实写入" >&2; return 3; }
  grep -q 'multiple_heredoc_mention :: pros=\[\]' "$tmp/cpy.txt" \
    || { echo "FAIL: 多 heredoc 的后续正文被误判成真实写入" >&2; return 3; }
  grep -q 'escaped_heredoc_mention :: pros=\[\]' "$tmp/cpy.txt" \
    || { echo "FAIL: 反斜杠引用 heredoc 正文中的路径提及被误判成真实写入" >&2; return 3; }
  grep -q 'escaped_heredoc_then_redirect :: pros=\[book/본문/제7장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: 反斜杠引用 heredoc 吞掉了其后的真实正文写入" >&2; return 3; }
  grep -q 'escaped_quote_tee_mention :: pros=\[\]' "$tmp/cpy.txt" \
    || { echo "FAIL: 转义引号内的 tee 示例被误判成真实写入" >&2; return 3; }
  grep -q 'nested_shell_redirect :: pros=\[book/본문/제7장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: sh -c 内的真实正文重定向绕过了守卫" >&2; return 3; }
  grep -q 'nested_shell_combined_flags :: pros=\[book/본문/제7장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: bash -lc 内的真实正文重定向绕过了守卫" >&2; return 3; }
  grep -q 'quoted_command_substitution_redirect :: pros=\[book/본문/제7장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: 双引号内的 \$(...) 正文写入绕过了守卫" >&2; return 3; }
  grep -q 'quoted_backtick_substitution_redirect :: pros=\[book/본문/제7장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: 双引号内的反引号正文写入绕过了守卫" >&2; return 3; }
  grep -q 'cp_command_wrapper :: pros=\[book/본문/제4장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: command cp 的正文目标未被提取" >&2; return 3; }
  grep -q 'cp_command_p_wrapper :: pros=\[book/본문/제4장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: command -p cp 的正文目标未被提取" >&2; return 3; }
  grep -q 'cp_command_double_dash_wrapper :: pros=\[book/본문/제4장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: command -- cp 的正文目标未被提取" >&2; return 3; }
  grep -q 'cp_env_unset_short :: pros=\[book/본문/제4장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: env -u 包装的 cp 正文目标未被提取" >&2; return 3; }
  grep -q 'cp_env_unset_long :: pros=\[book/본문/제4장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: env --unset 包装的 cp 正文目标未被提取" >&2; return 3; }
  grep -q 'cp_absolute_binary :: pros=\[book/본문/제4장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: 绝对路径 cp 的正文目标未被提取" >&2; return 3; }
  grep -q 'cp_destination_directory :: pros=\[book/본문/제4장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: cp 到正文目录时未按源文件名还原落盘目标" >&2; return 3; }
  grep -q 'cp_target_directory :: pros=\[book/본문/제4장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: cp --target-directory 的正文目标未被提取" >&2; return 3; }
  grep -q 'install :: pros=\[book/본문/제4장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: install 的正文目标未被提取" >&2; return 3; }
  grep -q 'redirect_clobber :: pros=\[book/본문/제1장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: >| 正文重定向绕过了守卫" >&2; return 3; }
  grep -q 'redirect_both :: pros=\[book/본문/제1장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: >& 文件 正文重定向绕过了守卫" >&2; return 3; }
  grep -q 'redirect_fd_dup :: pros=\[\]' "$tmp/cpy.txt" \
    || { echo "FAIL: >&2 文件描述符复制被误判成正文写入" >&2; return 3; }
  # 무효 검증 방지(apply_patch 이동): `*** Move to:`는 Update/Delete File 구간의 하위 명령으로 저장 경로는
  # 목적지다. Add/Update File만 인식하면 ‘Update draft.md + Move to 书/본문/제N장.md’에서 원본
  # draft.md를 추출해 상세 개요 검사를 통째로 건너뛰고 쓰기 후에는 사라진 원본을 검사한다(양쪽 동일 오류는 diff로 못 잡음).
  grep -q 'patch_move :: pros=\[\] patch=\[book/본문/제6장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: apply_patch 的 *** Move to: 目的地未进目标表（源被搬走，只有目的地落盘）" >&2; return 3; }
  grep -q 'patch_move_delete :: pros=\[\] patch=\[book/본문/제7장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: *** Delete File: + *** Move to: 的目的地未进目标表" >&2; return 3; }
  grep -q 'patch_move_out :: pros=\[\] patch=\[draft.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: 搬出 본문/ 时源仍被当写入目标（源已不存在，只有目的地该被判）" >&2; return 3; }
  grep -q 'patch_delete_only :: pros=\[\] patch=\[\]' "$tmp/cpy.txt" \
    || { echo "FAIL: 纯 *** Delete File: 不该进目标表（删除不是写入，认它只会给删稿误报）" >&2; return 3; }
  grep -q 'patch_multi_move :: pros=\[\] patch=\[notes.md|book/본문/제10장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: 一份补丁里 Add 段与 Move 段的目标未同时取全（Move 只该顶替同段的源）" >&2; return 3; }
  grep -q 'patch_context_move :: pros=\[\] patch=\[book/본문/제12장.md\]' "$tmp/cpy.txt" \
    || { echo "FAIL: patch 上下文行里的字面 *** Move to 被误当控制指令，实际正文目标被顶掉" >&2; return 3; }

  # ReDoS 회귀(shellWords): 호출자가 [;&|\n]으로 먼저 나누면 인용 안 |도 분리해 닫히지 않은 "를 남긴다.
  # 이전 정규식의 이스케이프 문자 분기와 따옴표 이외 문자 분기가 모두 역슬래시를 소비해 역슬래시마다 탐색 공간이 두 배가 된다.
  # 이 백여 자 커밋 명령은 실제 CPU를 수십 초 사용해 ZCode hooks.json의 timeoutMs 15000을 넘고 종료됐다.
  # 직접 작성한 선형 토큰화는 밀리초 수준이어야 하므로 2초 예산을 둔다(Python shlex도 선형이며 변화를 막기 위해 함께 측정).
  node - "$ZCODE" > "$tmp/redos.txt" <<'JS' || return 3
const h = require(process.argv[2])
const cmd = 'git commit -m "fix: 正则转义覆盖 ' + Array.from({ length: 18 }, () => "\\\\x").join(" ") + ' covered | see README"'
const t0 = Date.now()
const hit = h.isGitCommitCommand(cmd)
const ms = Date.now() - t0
if (!hit) { console.error("FAIL: git commit 侦测漏判带转义/管道的提交命令"); process.exit(3) }
if (ms > 2000) { console.error(`FAIL: shellWords 回溯爆炸（${ms}ms > 2000ms），宿主 hook 会超时被杀`); process.exit(3) }
console.log(`redos_budget :: ${ms}ms`)
JS
  python3 - "$CODEX" >> "$tmp/redos.txt" <<'PY' || return 3
import importlib.util, sys, time
spec = importlib.util.spec_from_file_location("ch", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
cmd = 'git commit -m "fix: 正则转义覆盖 ' + " ".join([r"\\x"] * 18) + ' covered | see README"'
t0 = time.time()
hit = m.is_git_commit_command(cmd)
ms = int((time.time() - t0) * 1000)
# 실패 문구는 stderr.buffer로 UTF-8을 직접 쓴다. Windows Python 텍스트 stderr는 cp1252라 중국어에서 UnicodeEncodeError가 난다.
if not hit:
    sys.stderr.buffer.write("FAIL: py 侧 git commit 侦测漏判带转义/管道的提交命令\n".encode("utf-8")); sys.exit(3)
if ms > 2000:
    sys.stderr.buffer.write(f"FAIL: py 侧 git commit 侦测退化成非线性（{ms}ms > 2000ms）\n".encode("utf-8")); sys.exit(3)
PY
  return 0
}

# ── C. 미통합 영역 동등성(Codex Python 대 JS 코어), CI 필수 보장 ──
# 스테이징 Markdown 경고와 개요 차단 판정은 코어에 통합되지 않았다. Codex Python의 staged_markdown_warnings /
# prose_block_reason과 JS 코어의 stagedMarkdownWarnings / proseBlockReason이 각각 구현한다.
# 의미/문구는 JS 코어 기준이며 데이터의 문자별 비교로 불일치를 막는다. Claude 순수 bash 구현은 여기서 고정하지 않고
# check-story-setup-deployment.sh / test-hook-encoding-portable.sh 실행 회귀로 검사한다.
# 최소 범위: ① name 필드 대소문자/전각 공백 변형을 동일하게 탐지해 필드가 있으면 경고하지 않음
# ② 필드 누락/하드코딩 속성의 중국어 경고(상하 테두리 포함) 문자별 일치 ③ 장편 상세 개요 없음/있음,
# 단편 절 개요 없음/설정 신호 없음의 4그룹 차단 판정과 문구 일치 ④ 유해 문형 미해결 조건 4그룹:
# 미해결 시 차단, ‘去味:跳过’/전각 콜론 ‘去味：跳过’ 마커면 허용, 이전 장의 잘못된 바이트는 대체 디코딩 후 계속 검사.
run_uncored_parity() {
  command -v node >/dev/null 2>&1 || return 1
  command -v python3 >/dev/null 2>&1 || return 1
  command -v git >/dev/null 2>&1 || return 1
  local tmp; tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN

  # E1: 스테이징 Markdown 경고 — 독립 git 저장소를 만들고 고정 파일 집합을 스테이징한다.
  local repo="$tmp/repo"
  mkdir -p "$repo/book/본문" "$repo/설정"
  git -C "$repo" init -q
  printf '身高: 180\n他推门而入。\n年龄　：18\n' > "$repo/book/본문/제1장.md"
  printf 'NAME：林远\n' > "$repo/설정/주인공.md"            # 대소문자 변형: 필드가 있으므로 경고 없음
  printf '　名字 ：苏离\n' > "$repo/설정/조연.md"          # 전각 공백 패딩: 필드가 있으므로 경고 없음
  printf '简介：没有名字字段\n' > "$repo/설정/악역.md"     # 필드 누락: 경고
  # 인물 카드로 제한: 설정/角色|人物 하위 파일과 설정/ 바로 아래 평면 인물 카드만 name 필드를 검사한다.
  # 프로젝트 설정(관계/문체/소재 포지셔닝 등)과 인물 외 하위 디렉터리는 제외한다. 네 환경(bash/OpenCode/JS/Python)은
  # 같은 기준이다. 여기서 Python↔JS를 고정해 설정/ 전체를 일괄 검사하는 오경고 버전으로 돌아가지 않게 한다.
  mkdir -p "$repo/설정/인물" "$repo/설정/세계관"
  printf '简介：没有名字字段的角色卡\n' > "$repo/설정/인물/新人.md"  # 인물 카드 하위 디렉터리: 필드 누락 시 경고
  printf '# 角色关系图\n' > "$repo/설정/관계.md"                     # 프로젝트 설정: 경고 없음
  printf '# 文风\n' > "$repo/설정/문체.md"                           # 프로젝트 설정: 경고 없음
  printf '# 地理\n' > "$repo/설정/세계관/地理.md"                    # 인물 외 하위 디렉터리: 전체 건너뜀
  git -C "$repo" add -A

  python3 - "$CODEX" "$repo" > "$tmp/spy.txt" <<'PY'
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("ch", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
out = m.staged_markdown_warnings(Path(sys.argv[2]))
sys.stdout.buffer.write((out + "\n").encode("utf-8"))
PY
  node - "$CLAUDE_CORE" "$repo" > "$tmp/sjs.txt" <<'JS'
const core = require(process.argv[2])
console.log(core.stagedMarkdownWarnings(process.argv[3]))
JS
  if ! diff "$tmp/spy.txt" "$tmp/sjs.txt" >/dev/null; then
    echo "FAIL: staged warnings parity 不一致（codex python vs JS core）：" >&2
    diff "$tmp/spy.txt" "$tmp/sjs.txt" >&2 || true
    return 3
  fi
  # 무효 검증 방지(양쪽 빈 문자열도 diff 통과): 탐지/미탐지와 통일된 중국어 문구의 실제 존재를 단언한다.
  grep -q '본문에 인물 속성을 직접 고정했습니다. 설정 파일을 참조하세요' "$tmp/spy.txt" || { echo "FAIL: staged warnings 未按统一文案报硬编码属性" >&2; return 3; }
  grep -q '악역.md: 설정 파일에 필수 이름 필드(name/名字)가 없습니다.' "$tmp/spy.txt" || { echo "FAIL: staged warnings 未按统一文案报缺 name 字段" >&2; return 3; }
  grep -q '주인공.md' "$tmp/spy.txt" && { echo "FAIL: 大写 NAME： 应视为字段已存在（大小写不敏感）" >&2; return 3; }
  grep -q '조연.md' "$tmp/spy.txt" && { echo "FAIL: 全角空格补白的 名字 ： 应视为字段已存在" >&2; return 3; }
  grep -q '설정/인물/新人.md: 설정 파일에 필수 이름 필드(name/名字)가 없습니다.' "$tmp/spy.txt" || { echo "FAIL: 설정/인물 子目录下的角色卡应仍查 name 字段" >&2; return 3; }
  grep -q '관계.md' "$tmp/spy.txt" && { echo "FAIL: 项目级设定件 관계.md 不该被当角色卡查 name" >&2; return 3; }
  grep -q '문체.md' "$tmp/spy.txt" && { echo "FAIL: 项目级设定件 문체.md 不该被当角色卡查 name" >&2; return 3; }
  grep -q '地理.md' "$tmp/spy.txt" && { echo "FAIL: 설정/ 下非角色子目录应整目录跳过" >&2; return 3; }

  # E2: 개요/추적 차단 판정 — 장편 상세 개요 없음(차단)/있음(허용), 단편 절 개요 없음(차단)/설정 신호 없음(허용),
  #     유해 문형 미해결 조건(이전 장 미해결 시 차단 / ‘去味:跳过’ 제외 허용 / 전각 콜론 ‘去味：跳过’ 제외 허용 /
  #     이전 장의 잘못된 바이트를 대체 디코딩한 뒤 계속 검사해 차단), 골격 없는 새 책도 상세 개요를 먼저 요구(차단)
  local blk="$tmp/blk"
  # 상세 개요 내용이 있어야 허용(#과 공백 제외 30자 이상, 제목 문자 포함). v0.8 필드 없는 기존 자유 형식 개요도 인정한다.
  local filled='# 第2章 细纲
江晨在雨夜推开旧书店的门，发现柜台后坐着失踪三年的师父，两人对视良久谁都没先开口。'
  mkdir -p "$blk/long/본문" "$blk/long/개요" "$blk/short" "$blk/short2" \
    "$blk/long2/본문" "$blk/long2/개요" "$blk/long3/본문" "$blk/long3/개요"
  printf '%s\n' "$filled" > "$blk/long/개요/상세개요_제2장.md"
  : > "$blk/short/설정.md"
  : > "$blk/short2/其他.md"
  printf '%s\n' "$filled" > "$blk/long2/개요/상세개요_제2장.md"
  printf '%s\n' '# 제1장 旧' '' '声音不大，却带着一股狠劲。' > "$blk/long2/본문/제1장_旧.md"
  printf '%s\n' "$filled" > "$blk/long3/개요/상세개요_제2장.md"
  printf '%s\n' '# 제1장 旧' '<!-- 去味:跳过 -->' '声音不大，却带着一股狠劲。' > "$blk/long3/본문/제1장_旧.md"
  mkdir -p "$blk/long4/본문" "$blk/long4/개요" "$blk/long5/본문" "$blk/long5/개요"
  printf '%s\n' "$filled" > "$blk/long4/개요/상세개요_제2장.md"
  printf '%s\n' '# 제1장 旧' '<!-- 去味：跳过 -->' '声音不大，却带着一股狠劲。' > "$blk/long4/본문/제1장_旧.md"
  printf '%s\n' "$filled" > "$blk/long5/개요/상세개요_제2장.md"
  { printf '%s\n' '# 제1장 旧' '声音不大，却带着一股狠劲。'; printf '\xff\n'; } > "$blk/long5/본문/제1장_旧.md"
  # 제외 마커: 주석 안 공백/탭 허용(long8), 주석 밖에 쓴 ‘去味:跳过’는 불인정(long9).
  mkdir -p "$blk/long8/본문" "$blk/long8/개요" "$blk/long9/본문" "$blk/long9/개요"
  printf '%s\n' "$filled" > "$blk/long8/개요/상세개요_제2장.md"
  printf '%s\n' '# 제1장 旧' '<!--  去味 : 跳过	-->' '声音不大，却带着一股狠劲。' > "$blk/long8/본문/제1장_旧.md"
  printf '%s\n' "$filled" > "$blk/long9/개요/상세개요_제2장.md"
  printf '%s\n' '# 제1장 旧' '去味:跳过' '声音不大，却带着一股狠劲。' > "$blk/long9/본문/제1장_旧.md"
  for book in long long2 long3 long4 long5 long8 long9; do
    mkdir -p "$blk/$book/추적"
    printf '%s\n' '{"schema_version":4,"state_revision":0,"last_committed_chapter":1}' > "$blk/$book/추적/_tracking-state.json"
    printf '%s\n' '> 状态修订：0' > "$blk/$book/추적/문맥.md"
  done
  # 이전 장 본문은 있지만 state 커밋 진행도가 뒤처지면 다음 장 최초 생성을 차단해야 한다.
  mkdir -p "$blk/long6/본문" "$blk/long6/개요" "$blk/long6/추적"
  printf '%s\n' "$filled" > "$blk/long6/개요/상세개요_제2장.md"
  printf '%s\n' '# 제1장 旧' '他把门关上了。' > "$blk/long6/본문/제1장_旧.md"
  printf '%s\n' '{"schema_version":4,"state_revision":0,"last_committed_chapter":0}' > "$blk/long6/추적/_tracking-state.json"
  printf '%s\n' '> 状态修订：0' > "$blk/long6/추적/문맥.md"
  # 표준 사례: 에이전트가 {书}/본문/제N장.md를 최초 생성할 때 책 디렉터리에 개요/추적/설정 골격이 없어도
  # 차단해야 한다. 상대 대상 cwd 의미는 호스트 어댑터가 각각 책임지며 코어 보호를 약화해 감추면 안 된다.
  mkdir -p "$blk/bare/본문"
  # 파일명만 맞는 빈 상세 개요: 0바이트/제목만/BOM+CRLF+전각 공백/29자(1자 부족)는 모두 차단한다.
  # 정확히 30자는 허용한다. 같은 장의 개요가 둘이고 하나만 채워져도 허용한다. state는 모두 유효해
  # 상세 개요만 유일한 변수다.
  # 제목 문자도 내용에 포함한다(줄 앞 #만 제거). `# 第1章 细纲`은 5자이며 본문 24/25자로 29/30자를 만든다.
  local body29='他推门进屋看见师父坐在柜台后面他推门进屋看见师父'
  local body30='他推门进屋看见师父坐在柜台后面他推门进屋看见师父坐'
  for book in oe_zero oe_heading oe_bomcrlf oe_29 oe_30 oe_dup oe_headcontent oe_gbk; do
    mkdir -p "$blk/$book/본문" "$blk/$book/개요" "$blk/$book/추적"
    printf '%s\n' '{"schema_version":4,"state_revision":0,"last_committed_chapter":0}' > "$blk/$book/추적/_tracking-state.json"
    printf '%s\n' '> 状态修订：0' > "$blk/$book/추적/문맥.md"
  done
  mkdir -p "$blk/long7/본문" "$blk/long7/개요" "$blk/long7/추적"
  printf '%s\n' "$filled" > "$blk/long7/개요/상세개요_제2장.md"
  printf '%s\n' '{"schema_version":4,"state_revision":0,"last_committed_chapter":1}' > "$blk/long7/추적/_tracking-state.json"
  printf '%s\n' '> 状态修订：0' > "$blk/long7/추적/문맥.md"
  { printf '%s\n' '# 제1장 旧'; for i in 1 2 3 4 5 6 7 8; do printf '%s\n' "声音不大，却带着第${i}股狠劲。"; done; printf '%s\n' '他把门关上了。'; } > "$blk/long7/본문/제1장_旧.md"
  : > "$blk/oe_zero/개요/상세개요_제001장.md"
  printf '%s\n' '# 제1장 细纲' '## 目标情绪' '  ## 主角选择' '' > "$blk/oe_heading/개요/상세개요_제001장.md"
  printf '\357\273\277# 제1장 细纲\r\n\r\n\343\200\200\343\200\200\t \r\n' > "$blk/oe_bomcrlf/개요/상세개요_제001장.md"
  printf '%s\n' '# 제1장 细纲' "$body29" > "$blk/oe_29/개요/상세개요_제001장.md"
  printf '%s\n' '# 제1장 细纲' "$body30" > "$blk/oe_30/개요/상세개요_제001장.md"
  : > "$blk/oe_dup/개요/상세개요_제001장.md"
  printf '%s\n' '# 제1장 细纲' "$body30" > "$blk/oe_dup/개요/상세개요_제1장_开端.md"
  # 제목 줄에 내용이 있는 상세 개요(`## 核心事件：…`)를 제목뿐이라고 차단하면 안 된다.
  printf '%s\n' '# 제1장' '## 核心事件：江晨雨夜推门发现失踪三年的师父坐在柜台后' '## 主角选择：留下' > "$blk/oe_headcontent/개요/상세개요_제001장.md"
  # UTF-8이 아닌 상세 개요(이전 GBK 원고)는 bash 보호와 동일하게 비어 있지 않으면 허용한다.
  python3 -c 'import sys;open(sys.argv[1],"wb").write("第二天他就回来了，大家都说他变了，只是没人问".encode("gbk")+b"\n")' "$blk/oe_gbk/개요/상세개요_제001장.md"

  python3 - "$CODEX" "$blk" > "$tmp/bpy.txt" <<'PY'
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("ch", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
root = Path(sys.argv[2])
for rel in ["long/본문/제1장_起.md", "long/본문/제2장_承.md", "short/본문.md", "short2/본문.md", "long2/본문/제2장_新.md", "long3/본문/제2장_新.md", "long4/본문/제2장_新.md", "long5/본문/제2장_新.md", "long6/본문/제2장_新.md", "bare/본문/제1장_起.md", "$PROJ/본문/제001장_x.md", "$(pwd)/book/본문/제001장_y.md", "long7/본문/제2장_新.md", "long8/본문/제2장_新.md", "long9/본문/제2장_新.md", "oe_zero/본문/제001장_a.md", "oe_heading/본문/제001장_a.md", "oe_bomcrlf/본문/제001장_a.md", "oe_29/본문/제001장_a.md", "oe_30/본문/제001장_a.md", "oe_dup/본문/제001장_a.md", "oe_headcontent/본문/제001장_a.md", "oe_gbk/본문/제001장_a.md"]:
    reason = m.prose_block_reason(root, root / rel)
    sys.stdout.buffer.write((f"{rel} :: {reason if reason else '-'}\n").encode("utf-8"))
PY
  node - "$CLAUDE_CORE" "$blk" > "$tmp/bjs.txt" <<'JS'
const path = require("node:path")
const core = require(process.argv[2])
const root = process.argv[3]
for (const rel of ["long/본문/제1장_起.md", "long/본문/제2장_承.md", "short/본문.md", "short2/본문.md", "long2/본문/제2장_新.md", "long3/본문/제2장_新.md", "long4/본문/제2장_新.md", "long5/본문/제2장_新.md", "long6/본문/제2장_新.md", "bare/본문/제1장_起.md", "$PROJ/본문/제001장_x.md", "$(pwd)/book/본문/제001장_y.md", "long7/본문/제2장_新.md", "long8/본문/제2장_新.md", "long9/본문/제2장_新.md", "oe_zero/본문/제001장_a.md", "oe_heading/본문/제001장_a.md", "oe_bomcrlf/본문/제001장_a.md", "oe_29/본문/제001장_a.md", "oe_30/본문/제001장_a.md", "oe_dup/본문/제001장_a.md", "oe_headcontent/본문/제001장_a.md", "oe_gbk/본문/제001장_a.md"]) {
  const reason = core.proseBlockReason(root, path.join(root, rel))
  console.log(`${rel} :: ${reason || "-"}`)
}
JS
  if ! diff "$tmp/bpy.txt" "$tmp/bjs.txt" >/dev/null; then
    echo "FAIL: 大纲阻断 parity 不一致（codex python vs JS core）：" >&2
    diff "$tmp/bpy.txt" "$tmp/bjs.txt" >&2 || true
    return 3
  fi
  grep -q '제1장_起.md :: ⛔' "$tmp/bpy.txt" || { echo "FAIL: 长篇缺细纲未被拦截" >&2; return 3; }
  grep -q '제2장_承.md :: -' "$tmp/bpy.txt" || { echo "FAIL: 长篇有细纲被误拦" >&2; return 3; }
  grep -q 'short/본문.md :: ⛔' "$tmp/bpy.txt" || { echo "FAIL: 短篇缺小节大纲未被拦截" >&2; return 3; }
  grep -q 'short2/본문.md :: -' "$tmp/bpy.txt" || { echo "FAIL: 无设定信号的正文.md 被误拦" >&2; return 3; }
  grep -q '미수정 문제 문장' "$tmp/bpy.txt" || { echo "FAIL: 上一章미수정 문제 문장未被欠账门拦截" >&2; return 3; }
  grep -q 'long3/본문/제2장_新.md :: -' "$tmp/bpy.txt" || { echo "FAIL: 标「去味:跳过」豁免的上一章仍被欠账门误拦" >&2; return 3; }
  grep -q 'long4/본문/제2장_新.md :: -' "$tmp/bpy.txt" || { echo "FAIL: 全角冒号豁免标记「去味：跳过」未被欠账门认可" >&2; return 3; }
  grep -q 'long8/본문/제2장_新.md :: -' "$tmp/bpy.txt" || { echo "FAIL: 注释内带空格的豁免标记 <!--  去味 : 跳过 --> 未被欠账门认可" >&2; return 3; }
  grep -q 'long9/본문/제2장_新.md :: ⛔.*미수정 문제 문장' "$tmp/bpy.txt" || { echo "FAIL: 裸写的「去味:跳过」（不在 HTML 注释里）被欠账门当成豁免" >&2; return 3; }
  grep -q 'long5/본문/제2장_新.md :: ⛔' "$tmp/bpy.txt" || { echo "FAIL: 上一章含坏字节时两端应替换解码继续扫（不得整体放行）" >&2; return 3; }
  grep -q 'long6/본문/제2장_新.md :: ⛔.*먼저 제출할 추적 트랜잭션: 제1장' "$tmp/bpy.txt" || { echo "FAIL: state 的 last_committed_chapter 落后正文时未拦住下一章" >&2; return 3; }
  grep -q 'bare/본문/제1장_起.md :: ⛔' "$tmp/bpy.txt" || { echo "FAIL: 新书无 개요/추적/설정 脚手架时首章守卫 fail open" >&2; return 3; }
  # 상세 개요 누락 안내는 상세개요_제001장.md처럼 앞자리 0을 채운 표준 이름을 제시한다. 상세개요_제1장.md로 잘못 만들게 하면 안 된다.
  grep -q 'long/본문/제1장_起.md :: ⛔.*상세개요_제001장\.md' "$tmp/bpy.txt" || { echo "FAIL: 缺细纲文案未给补零的规范细纲文件名" >&2; return 3; }
  # 대상에 미확장 셸 변수(cat > "$PROJ/본문/...")가 있으면 차단하되 상세 개요 누락 아닌 경로 해석 실패로 안내한다.
  grep -q '\$PROJ/본문/제001장_x.md :: ⛔.*치환되지 않은 셸 변수' "$tmp/bpy.txt" || { echo "FAIL: shell 变量目标未按「路径未解析」拦截" >&2; return 3; }
  grep -q '\$PROJ/본문/제001장_x.md :: .*상세 개요가 없습니다' "$tmp/bpy.txt" && { echo "FAIL: shell 变量目标被误报为상세 개요가 없습니다" >&2; return 3; }
  grep -q '\$(pwd)/book/본문/제001장_y.md :: ⛔.*치환되지 않은 셸 변수' "$tmp/bpy.txt" || { echo "FAIL: \$(...) 命令替换目标未按「路径未解析」拦截" >&2; return 3; }
  for want in oe_zero oe_heading oe_bomcrlf oe_29; do
    grep -q "^$want/본문/제001장_a.md :: ⛔ 본문 쓰기 차단: 제1장의 상세 개요(oe_[a-z0-9]*/개요/상세개요_제001장.md)가 비어 있습니다" "$tmp/bpy.txt" \
      || { echo "FAIL: 空细纲场景 ${want} 未按「细纲가 비어 있습니다」拦截：$(grep "^$want/" "$tmp/bpy.txt")" >&2; return 3; }
  done
  # 미해결 6곳 초과 시 ‘추가 N곳’ 안내: 장편 이전 장은 장 번호를 포함한 storyctl chapter check로 연결한다(양쪽 문자별 동일).
  grep -qF 'long7/본문/제2장_新.md :: ⛔' "$tmp/bpy.txt" \
    && grep -qF '추가 2곳, 전체 검사: {PYTHON} <story-long-write>/scripts/storyctl.py chapter check --project <작품폴더> --chapter 1）' "$tmp/bpy.txt" \
    || { echo "FAIL: 欠账门「另有 N 处」未指向上一章的 chapter check：$(grep -A8 '^long7/' "$tmp/bpy.txt")" >&2; return 3; }
  for want in oe_30 oe_dup oe_headcontent oe_gbk; do
    grep -q "^$want/본문/제001장_a.md :: -" "$tmp/bpy.txt" \
      || { echo "FAIL: 写了内容的细纲场景 ${want} 被误拦：$(grep "^$want/" "$tmp/bpy.txt")" >&2; return 3; }
  done

  # E2b: 유해 문형 재검사 안내 Python↔JS 문자별 일치와 방향 고정: 장편 분할 본문 → 장 번호를 포함한 chapter check,
  #      단편 본문.md / 본문 디렉터리 밖의 제N장 / 경로 없음 → check-ai-patterns.js.
  python3 - "$CODEX" > "$tmp/rpy.txt" <<'PY'
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("ch", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
for rel in ["书/본문/제012장_夜路.md", "书/본문.md", "书/草稿/제3장.md", ""]:
    hint = m.toxic_rescan_hint(Path("/p") / rel if rel else None)
    sys.stdout.buffer.write(f"{rel or '-'} :: {hint}\n".encode("utf-8"))
PY
  node - "$CLAUDE_CORE" > "$tmp/rjs.txt" <<'JS'
const path = require("node:path")
const core = require(process.argv[2])
for (const rel of ["书/본문/제012장_夜路.md", "书/본문.md", "书/草稿/제3장.md", ""]) {
  console.log(`${rel || "-"} :: ${core.toxicRescanHint(rel ? path.join("/p", rel) : "")}`)
}
JS
  if ! diff "$tmp/rpy.txt" "$tmp/rjs.txt" >/dev/null; then
    echo "FAIL: 毒句式复扫指引 parity 不一致（codex python vs JS core）：" >&2
    diff "$tmp/rpy.txt" "$tmp/rjs.txt" >&2 || true
    return 3
  fi
  grep -qxF '书/본문/제012장_夜路.md :: 전체 검사: {PYTHON} <story-long-write>/scripts/storyctl.py chapter check --project <작품폴더> --chapter 12' "$tmp/rpy.txt" \
    || { echo "FAIL: 长篇分章正文的复扫指引未指向 chapter check" >&2; return 3; }
  for want in '书/본문.md' '书/草稿/제3장.md' '-'; do
    grep -qxF -- "$want :: 전체 스캔: node <skill>/scripts/check-ai-patterns.js --check <본문파일>" "$tmp/rpy.txt" \
      || { echo "FAIL: 非长篇分章目标（${want}）的复扫指引应保持 check-ai-patterns.js" >&2; return 3; }
  done

  # E3: 추적 상태 판정 동등성. 누락, 잘못된 JSON, 이전 스키마, 파생 revision 불일치,
  #     리비전/장 번호 누락, 뒤처진 커밋, 유효 state 허용을 검사해 Codex Python과 세 환경 JS 코어의 불일치를 막는다.
  local cp="$tmp/checkpoints"
  mkdir -p "$cp"/{missing,malformed,old,mismatch,norevision,nolast,behind,valid,revised}/추적
  for name in malformed old mismatch norevision nolast behind valid revised; do
    printf '%s\n' '> 状态修订：0' > "$cp/$name/추적/문맥.md"
  done
  printf '%s\n' '{not-json' > "$cp/malformed/추적/_tracking-state.json"
  printf '%s\n' '{"schema_version":3,"state_revision":0,"last_committed_chapter":7}' > "$cp/old/추적/_tracking-state.json"
  printf '%s\n' '{"schema_version":4,"state_revision":1,"last_committed_chapter":7}' > "$cp/mismatch/추적/_tracking-state.json"
  printf '%s\n' '{"schema_version":4,"last_committed_chapter":7}' > "$cp/norevision/추적/_tracking-state.json"
  printf '%s\n' '{"schema_version":4,"state_revision":0}' > "$cp/nolast/추적/_tracking-state.json"
  printf '%s\n' '{"schema_version":4,"state_revision":0,"last_committed_chapter":6}' > "$cp/behind/추적/_tracking-state.json"
  printf '%s\n' '{"schema_version":4,"state_revision":0,"last_committed_chapter":7}' > "$cp/valid/추적/_tracking-state.json"
  # 재작업/이름 변경/원고 백업: 장 번호가 추적 범위 안(expected 7 < last 9)이면 새 파일명이어도 이미 커밋한 장이므로
  # 순서 위반이 아니며 허용해야 한다. 그렇지 않으면 workflow-revision의 원고 백업 단계가 세 환경에서 차단된다.
  printf '%s\n' '{"schema_version":4,"state_revision":0,"last_committed_chapter":9}' > "$cp/revised/추적/_tracking-state.json"
  python3 - "$CODEX" "$cp" > "$tmp/cpy.txt" <<'PY'
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("ch", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
root = Path(sys.argv[2])
# B/C부와 같이 Windows의 Python<3.15 텍스트 stdout은 cp1252여서
# 중국어 issue를 직접 print하면 UnicodeEncodeError가 나므로 stdout.buffer로 UTF-8을 직접 써야 한다.
for name, expected in [("missing", None), ("malformed", None), ("old", None), ("mismatch", None), ("norevision", None), ("nolast", 7), ("behind", 7), ("valid", 7), ("revised", 7)]:
    issue = m.tracking_checkpoint_issue(root / name, require_state=True, expected_last_committed=expected)
    sys.stdout.buffer.write((f"{name} :: {issue or '-'}" + "\n").encode("utf-8"))
PY
  node - "$CLAUDE_CORE" "$cp" > "$tmp/cjs.txt" <<'JS'
const path = require("node:path")
const core = require(process.argv[2])
const root = process.argv[3]
for (const [name, expected] of [["missing", null], ["malformed", null], ["old", null], ["mismatch", null], ["norevision", null], ["nolast", 7], ["behind", 7], ["valid", 7], ["revised", 7]]) {
  const issue = core.trackingCheckpointIssue(path.join(root, name), true, expected)
  console.log(`${name} :: ${issue || "-"}`)
}
JS
  if ! diff "$tmp/cpy.txt" "$tmp/cjs.txt" >/dev/null; then
    echo "FAIL: 追踪检查点 parity 不一致（codex python vs JS core）：" >&2
    diff "$tmp/cpy.txt" "$tmp/cjs.txt" >&2 || true
    return 3
  fi
  grep -q 'missing :: .*_tracking-state.json이 없습니다' "$tmp/cpy.txt" || { echo "FAIL: 缺失 state 未 fail closed" >&2; return 3; }
  grep -q 'malformed :: .*해석할 수 없습니다' "$tmp/cpy.txt" || { echo "FAIL: 坏 JSON 未 fail closed" >&2; return 3; }
  grep -q 'old :: .*schema_version=4' "$tmp/cpy.txt" || { echo "FAIL: 旧 schema 未 fail closed" >&2; return 3; }
  grep -q 'mismatch :: .*상태 리비전.*mode=revision 트랜잭션을 다시 제출해 파생 문서를 재구성' "$tmp/cpy.txt" || { echo "FAIL: 派生 revision 不一致未给 mode=revision 重建动作" >&2; return 3; }
  grep -q 'norevision :: .*정수 state_revision이 없습니다' "$tmp/cpy.txt" || { echo "FAIL: 缺 state_revision 未 fail closed" >&2; return 3; }
  grep -q 'nolast :: .*정수 last_committed_chapter가 없습니다' "$tmp/cpy.txt" || { echo "FAIL: 缺 last_committed 未 fail closed" >&2; return 3; }
  grep -q 'behind :: .*먼저 제출할 추적 트랜잭션: 제7장' "$tmp/cpy.txt" || { echo "FAIL: 落后章号未 fail closed" >&2; return 3; }
  grep -q 'valid :: -' "$tmp/cpy.txt" || { echo "FAIL: 有效 state 被误拦" >&2; return 3; }
  grep -q 'revised :: -' "$tmp/cpy.txt" || { echo "FAIL: 回炉/备份已提交章号被误拦（workflow-revision 备份原稿会卡死）" >&2; return 3; }

  # E4: 이어쓰기 상태 카드 예산 초과는 Python/JS 모두 경고하고 mtime에 우연히 의존하면 안 된다.
  local hot="$tmp/hot-context"
  mkdir -p "$hot/book/본문" "$hot/book/추적"
  printf '%s\n' '# 제1장 开端' '正文。' > "$hot/book/본문/제001장_开端.md"
  printf '%s\n' '{"schema_version":4,"state_revision":0,"last_committed_chapter":1}' > "$hot/book/추적/_tracking-state.json"
  python3 - "$hot/book/추적/문맥.md" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).write_bytes(("> 状态修订：0\n" + "状态" * 7000).encode("utf-8"))
PY
  python3 - "$CODEX" "$hot" > "$tmp/hpy.txt" <<'PY'
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("ch", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
# 실행 중 findings에 중국어가 있다. Windows 텍스트 stdout은 cp1252이므로 buffer로 UTF-8을 직접 쓴다.
for finding in m.continuity_findings(Path(sys.argv[2])):
    sys.stdout.buffer.write((finding + "\n").encode("utf-8"))
PY
  node - "$CLAUDE_CORE" "$hot" > "$tmp/hjs.txt" <<'JS'
const core = require(process.argv[2])
for (const finding of core.continuityFindings(process.argv[3])) console.log(finding)
JS
  if ! diff "$tmp/hpy.txt" "$tmp/hjs.txt" >/dev/null; then
    echo "FAIL: 热上下文超预算 parity 不一致（codex python vs JS core）：" >&2
    diff "$tmp/hpy.txt" "$tmp/hjs.txt" >&2 || true
    return 3
  fi
  grep -q '이어 쓰기 상태 카드의 12288바이트 한도를 초과했습니다' "$tmp/hpy.txt" || { echo "FAIL: 热上下文超预算未告警" >&2; return 3; }
  return 0
}

set +e
run_functional
rc=$?
set -e
case "$rc" in
  0) echo "功能 parity：codex python 网 == JS core 网（扩展 fixtures，含毒句式各分支正反例/AI 自指/截断收尾、豁免标记与 storyctl 字数职责分离）。" ;;
  *) fails=$((fails + 1)) ;;
esac

set +e
run_cmd_parity
rc_cmd=$?
set -e
case "$rc_cmd" in
  0) echo "命令函数 parity：codex python == zcode JS（扩展 fixtures：正文抽取/apply-patch/git commit 侦测逐字相等，含包装器/命令替换/多 heredoc/转义引号、apply_patch 搬家与 ReDoS 预算）。" ;;
  1) echo "命令函数 parity：跳过（无 node/python3 运行时）。" ;;
  *) fails=$((fails + 1)) ;;
esac

# D. Claude bash 본문 쓰기 보호 ↔ JS 코어 proseBlockReason 동작 동등성(CI 필수 보장).
# 개요/상세 개요 차단은 node 없는 런타임에서도 작동해야 하므로 guard-outline-before-prose.sh가 순수 bash로
# 판정한다. 추적 점검은 JSON 파싱이 필요해 story_hook_cli.js로 공유 코어를 호출한다. 한 차단 훅에 두 경로가
# 섞여 있었지만 bash 쪽 환경 간 단언이 없어 #283이 다른 세 환경에 추적 조건을 넣을 때 Claude는 한 버전 내내
# 조용히 누락됐다(이슈 #305). 같은 프로젝트의 같은 쓰기에 bash 차단 여부 == JS 코어 차단 여부를 시나리오별 비교해
# 어느 한쪽만 바뀌어도 실패하게 한다.
run_bash_guard_parity() {
  command -v node >/dev/null 2>&1 || return 1
  command -v python3 >/dev/null 2>&1 || return 1
  local tmp; tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' RETURN

  # scenario|last_committed|ctx_revision|schema|outline_ch|target_ch|target_exists|拆文库|state|prev[|outline_kind]
  # state=none이면 last/ctx/schema는 무의미하다. target_exists=1은 이어쓰기 경로(상세 개요 제외, 추적은 검사).
  # outline_kind 기본은 filled(기존 자유 형식 30자 이상). empty=0바이트, heading=제목만,
  # short29=1자 부족, exact30=정확히 30자, bomcrlf=BOM+CRLF+전각 공백의 빈 껍데기, dup=빈 것과 채운 것 두 개.
  # whitelist 사례: 이전 장 유해 문형이 책별 .deslop-whitelist에 등록됨. Claude의 prose-toxic 하위 명령도
  # JS 코어처럼 허용 목록을 읽어야 bash만 오차단하지 않는다.
  # prev = 이전 장(제001장_旧.md) 내용으로 미해결 검사를 거친다. toxic=유해 문형 있고 제외 없음, marker=첫 6줄에
  # <!-- 去味:跳过 --> 표시, fullwidth=전각 콜론 去味：跳过(양쪽 정규식 모두 ：|: 인식), marker7=마커가 7행에 있음
  # (제외 범위를 벗어나므로 차단). -=이전 장을 만들지 않음.
  local scenarios="
nostate|-|-|-|1|1|0|0|none|-
nooutline|-|-|-|-|1|0|0|none|-
importwindow|-|-|-|-|1|0|1|none|-
importstate|0|0|4|1|3|0|1|yes|-
valid|0|0|4|1|1|0|0|yes|-
skipahead|0|0|4|3|3|0|0|yes|-
existing|1|0|4|1|1|1|0|yes|-
existing_mismatch|1|9|4|1|1|1|0|yes|-
badschema|0|0|3|1|1|0|0|yes|-
revisionbackup|5|0|4|3|3|0|0|yes|-
debt|1|0|4|2|2|0|0|yes|toxic
debt_marker|1|0|4|2|2|0|0|yes|marker
debt_fullwidth|1|0|4|2|2|0|0|yes|fullwidth
debt_marker7|1|0|4|2|2|0|0|yes|marker7
debt_whitelist|1|0|4|2|2|0|0|yes|whitelist
debt_marker_spaced|1|0|4|2|2|0|0|yes|spaced
debt_marker_bare|1|0|4|2|2|0|0|yes|bare
outline_empty|0|0|4|1|1|0|0|yes|-|empty
outline_heading|0|0|4|1|1|0|0|yes|-|heading
outline_short29|0|0|4|1|1|0|0|yes|-|short29
outline_exact30|0|0|4|1|1|0|0|yes|-|exact30
outline_bomcrlf|0|0|4|1|1|0|0|yes|-|bomcrlf
outline_dup|0|0|4|1|1|0|0|yes|-|dup
outline_headcontent|0|0|4|1|1|0|0|yes|-|headcontent
outline_gbk|0|0|4|1|1|0|0|yes|-|gbk
outline_empty_existing|1|0|4|1|1|1|0|yes|-|empty
"
  local out_bash="$tmp/bash.txt" out_js="$tmp/js.txt"
  : > "$out_bash"; : > "$out_js"

  local line
  while IFS='|' read -r name last ctx schema outline target exists lib state prev okind; do
    [ -n "${name:-}" ] || continue
    local proj="$tmp/$name" book="$tmp/$name/书"
    mkdir -p "$book/개요" "$book/본문" "$book/추적"
    [ "$lib" = "1" ] && mkdir -p "$proj/작품분석실/书"
    if [ "$outline" != "-" ]; then
      local ofile="$book/개요/상세개요_제00${outline}장.md"
      # 제목도 내용에 포함한다. `# 细纲` 2자 + 본문 28자로 정확히 30자를 만든다.
      local o30='他推门进屋看见师父坐在柜台后面他推门进屋看见师父坐在柜台'
      case "${okind:-filled}" in
        filled) printf '%s\n' '# 细纲' '江晨在雨夜推开旧书店的门，发现柜台后坐着失踪三年的师父，两人对视良久。' > "$ofile" ;;
        empty) : > "$ofile" ;;
        heading) printf '%s\n' '# 细纲' '## 目标情绪' '## 主角选择' > "$ofile" ;;
        short29) printf '%s\n' '# 细纲' "${o30%台}" > "$ofile" ;;
        exact30) printf '%s\n' '# 细纲' "$o30" > "$ofile" ;;
        bomcrlf) printf '\357\273\277# 细纲\r\n\343\200\200\r\n\t\r\n' > "$ofile" ;;
        dup) : > "$ofile"; printf '%s\n' '# 细纲' "$o30" > "$book/개요/상세개요_제${outline}장_标题.md" ;;
        headcontent) printf '%s\n' '# 第1章' '## 核心事件：江晨雨夜推门发现失踪三年的师父坐在柜台后' '## 主角选择：留下' > "$ofile" ;;
        # 22자 GBK 상세 개요는 유효 UTF-8이 아니어서 계산이 다르다(bash 바이트 계산 27로 차단, JS/Python 대체 문자 계산 35로 허용). 비어 있지 않으면 허용으로 통일한다.
        gbk) python3 -c 'import sys;open(sys.argv[1],"wb").write("第二天他就回来了，大家都说他变了，只是没人问".encode("gbk")+b"\n")' "$ofile" ;;
      esac
    fi
    local toxic='声音不大，却带着一股狠劲。'
    case "$prev" in
      toxic) printf '%s\n' '# 제1장 旧' "$toxic" > "$book/본문/제001장_旧.md" ;;
      marker) printf '%s\n' '# 제1장 旧' '<!-- 去味:跳过 -->' "$toxic" > "$book/본문/제001장_旧.md" ;;
      fullwidth) printf '%s\n' '# 제1장 旧' '<!-- 去味：跳过 -->' "$toxic" > "$book/본문/제001장_旧.md" ;;
      marker7) printf '%s\n' '# 제1장 旧' '他推门。' '她抬头。' '灯亮了。' '雨停了。' '风起了。' '<!-- 去味:跳过 -->' "$toxic" > "$book/본문/제001장_旧.md" ;;
      spaced) printf '%s\n' '# 제1장 旧' '<!--去味 ：	跳过 -->' "$toxic" > "$book/본문/제001장_旧.md" ;;
      bare) printf '%s\n' '# 제1장 旧' '去味:跳过' "$toxic" > "$book/본문/제001장_旧.md" ;;
      whitelist) printf '%s\n' '# 제1장 旧' "$toxic" > "$book/본문/제001장_旧.md"
        printf '%s\n' '# 作者保留的原句' "${toxic%。}" > "$book/.deslop-whitelist" ;;
    esac
    if [ "$state" = "yes" ]; then
      printf '{"schema_version":%s,"state_revision":0,"last_committed_chapter":%s}\n' "$schema" "$last" \
        > "$book/추적/_tracking-state.json"
      printf '> 状态修订：%s。\n' "$ctx" > "$book/추적/문맥.md"
    fi
    local abs="$book/본문/제00${target}장_测试.md"
    [ "$exists" = "1" ] && printf '# 第%s章 测试\n正文。\n' "$target" > "$abs"

    # bash 측: exit 2 = 차단, 0 = 허용
    local payload code
    payload=$(python3 -c 'import json,sys;print(json.dumps({"tool_input":{"file_path":sys.argv[1]}}))' "$abs")
    ( cd "$proj" && CLAUDE_PROJECT_DIR="$proj" CLAUDE_TOOL_INPUT="$payload" bash "$CLAUDE_GUARD" ) >/dev/null 2>"$tmp/$name.bash.err"
    code=$?
    if [ "$code" = 2 ]; then printf '%s :: block\n' "$name" >> "$out_bash"
    else printf '%s :: pass\n' "$name" >> "$out_bash"; fi

    # JS 코어 측(차단 문구를 별도 저장해 미해결 조건 사례에서 같은 수정 안내인지 확인)
    node - "$CLAUDE_CORE" "$proj" "$abs" "$name" "$tmp/$name.js.err" >> "$out_js" <<'JS'
const core = require(process.argv[2])
const reason = core.proseBlockReason(process.argv[3], process.argv[4])
require("node:fs").writeFileSync(process.argv[6], reason || "")
console.log(`${process.argv[5]} :: ${reason ? "block" : "pass"}`)
JS
  done <<< "$scenarios"

  if ! diff "$out_bash" "$out_js" >/dev/null; then
    echo "FAIL: 写正文守卫 parity 不一致（Claude bash guard vs JS core）：" >&2
    diff "$out_bash" "$out_js" >&2 || true
    return 3
  fi
  # 일치만으로 부족하다. 양쪽이 함께 차단을 놓쳐도 diff가 같으므로 각 시나리오 기대 방향을 고정한다.
  local expect="nostate block
nooutline block
importwindow pass
importstate block
valid pass
skipahead block
existing pass
existing_mismatch block
badschema block
revisionbackup pass
debt block
debt_marker pass
debt_fullwidth pass
debt_marker7 block
debt_whitelist pass
debt_marker_spaced pass
debt_marker_bare block
outline_empty block
outline_heading block
outline_short29 block
outline_exact30 pass
outline_bomcrlf block
outline_dup pass
outline_headcontent pass
outline_gbk pass
outline_empty_existing pass"
  while read -r want_name want_verdict; do
    [ -n "$want_name" ] || continue
    grep -qx "$want_name :: $want_verdict" "$out_bash" || {
      echo "FAIL: 场景 ${want_name} 期望 ${want_verdict}，实得：$(grep "^$want_name ::" "$out_bash")" >&2
      return 3
    }
  done <<< "$expect"
  # 빈 상세 개요를 차단할 때 양쪽 모두 어느 장인지 설명해야 한다(Windows bash는 절대 경로이므로 파일명만 비교).
  local side
  for name in outline_empty outline_heading outline_short29 outline_bomcrlf; do
    for side in bash js; do
      grep -q '상세개요_제001장.md)가 비어 있습니다' "$tmp/$name.$side.err" || {
        echo "FAIL: 场景 $name 的 $side 拦截文案未说明细纲是비어 있습니다：$(cat "$tmp/$name.$side.err")" >&2
        return 3
      }
    done
  done
  for name in debt debt_marker7; do
    for side in bash js; do
      grep -q '미수정 문제 문장' "$tmp/$name.$side.err" && grep -qF '<!-- 去味:跳过 -->를 추가하고 다시 시도' "$tmp/$name.$side.err" || {
        echo "FAIL: 场景 $name 的 $side 拦截文案未指明上一章欠账与豁免标记写法：$(cat "$tmp/$name.$side.err")" >&2
        return 3
      }
    done
  done

  # node가 없으면 추적 조건은 허용해야 한다(개요 조건은 순수 bash로 계속 차단).
  local nonode="$tmp/nonode"; mkdir -p "$nonode"
  local proj="$tmp/nostate" abs="$tmp/nostate/书/본문/제001장_测试.md"
  local payload; payload=$(python3 -c 'import json,sys;print(json.dumps({"tool_input":{"file_path":sys.argv[1]}}))' "$abs")
  ( cd "$proj" && PATH="$nonode:/usr/bin:/bin" CLAUDE_PROJECT_DIR="$proj" CLAUDE_TOOL_INPUT="$payload" \
      bash "$CLAUDE_GUARD" ) >/dev/null 2>&1
  [ $? -eq 0 ] || { echo "FAIL: node 缺席时追踪门未 fail-open（BLOCKING 路径不得依赖 node 在场）" >&2; return 3; }
  # 빈 상세 개요 검사는 순수 bash이므로 node 없이도 차단한다(Claude 실제 원본 UTF-8 입력 사용, bash 추출은 \u 이스케이프를 해석하지 않음).
  proj="$tmp/outline_empty"; abs="$tmp/outline_empty/书/본문/제001장_测试.md"
  payload=$(python3 -c 'import json,sys;sys.stdout.buffer.write(json.dumps({"tool_input":{"file_path":sys.argv[1]}},ensure_ascii=False).encode("utf-8"))' "$abs")
  ( cd "$proj" && PATH="$nonode:/usr/bin:/bin" CLAUDE_PROJECT_DIR="$proj" CLAUDE_TOOL_INPUT="$payload" \
      bash "$CLAUDE_GUARD" ) >/dev/null 2>&1
  [ $? -eq 2 ] || { echo "FAIL: node 缺席时空细纲未被纯 bash 门拦下" >&2; return 3; }
  return 0
}

set +e
run_uncored_parity
rc_uncored=$?
set -e
case "$rc_uncored" in
  0) echo "未归核面 parity：codex python == JS core（staged warnings 大小写变体/文案 + 大纲阻断 23 组判定含空细纲各形态（含非 UTF-8）与标题行写内容/复扫指引/毒句式欠账门/无脚手架 fail-closed/文案逐字相等）。" ;;
  1) echo "未归核面 parity：跳过（无 node/python3/git 运行时）。" ;;
  *) fails=$((fails + 1)) ;;
esac

set +e
run_bash_guard_parity
rc_guard=$?
set -e
case "$rc_guard" in
  0) echo "写正文守卫 parity：Claude bash guard == JS core（26 组工程场景：无 state/缺细纲/空细纲各形态（含 GBK 细纲）/导入窗口/跳章/续写/派生修订不一致/坏 schema/回炉备份/上一章毒句式欠账、豁免标记语法与窗口、书级白名单，含 node 缺席时追踪门 fail-open、空细纲门照拦）。" ;;
  1) echo "写正文守卫 parity：跳过（无 node/python3 运行时）。" ;;
  *) fails=$((fails + 1)) ;;
esac

if [ "$fails" -ne 0 ]; then
  echo "Prose net parity tests FAILED ($fails)." >&2
  exit 1
fi
echo "Prose net parity tests passed."
