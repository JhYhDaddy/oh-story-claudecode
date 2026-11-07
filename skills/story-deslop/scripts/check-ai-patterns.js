#!/usr/bin/env node
'use strict';

const fs = require('fs');
const { loadStyleWhitelist, maskStyleText } = require('./style-whitelist.js');
const path = require('path');

const USAGE = `Usage: node check-ai-patterns.js [--check] [--json] [--fail-on=blocking|all] <file...>
       node check-ai-patterns.js --list-review-classes

Detect high-risk AI-flavor prose patterns that need human rewrite:
  - negative setup followed by positive flip in the same sentence
  - comma/semicolon/colon + positive flip
  - sentence break + positive flip
  - repeated negative setup followed by positive flip
  - em-dash (按功能改写), 碎句号 (连续短叙述句), 长段落 (按镜头断段)
  - 微动作复读 (「了下/了一下」式轻量补语高密度，电报体指纹)
  - 套式反应细节 (指尖/指节/目光等无功能微动作与「平静得像在念」式语气比喻成片)
  - 抽象总结复读 (命运/棋局/这一刻终于明白/才刚刚开始，AI 结尾腔)
  - 套词密度过高 (仿佛/一丝/深吸一口气/平静无波等禁用词聚集)
  - 比喻密度过高 (像/好像/仿佛/如同等比喻标记成片复现)
  - 解释链密度过高 (知道/明白/这意味着/必须/需要等判断链聚集)
  - 系统公告公文腔过密 (方括号系统/规则行里硬规则词聚集)
  - 过度精炼短段 (长文本里短叙述段过密且自然连接偏少)
  - 低连接密度 (引号外叙述功能词/白话连接偏少且中长句不足，像提纲/电报体)
  - 监控摄像头式动作清单 (同段连续摆放动作动词，缺少视角温度/情绪缓冲)
  - 音量反差腔 (声音不高/不大…却…, 实战漏网句式)
  - 否定排比 (没有X，没有Y…连排 / 没X…只是Y 先否定后肯定, 实战漏网句式)
  - 工整并列 (至于X不X，怎么X / 同动词「不V A，不V B」，含台词，advisory)
  - 反序对比 (是A，不是B — not-is 的反序变种, 实战漏网句式)
  - 预告式总结收尾 (文末窗口 没人知道/才刚刚开始/正朝着…压了过去, 实战漏网句式)
  - 章尾状态总结体 (文末窗口 这一夜注定/这一切都结束了/新的人生才刚刚开始/命运的齿轮)
  - 引号强调滥用 (叙述里 1-4 字短词加引号强调，密度型)

Book-local .deslop-whitelist literal spans are excluded from style scanning (no regex or ancestor inheritance).
Each finding carries severity: blocking by default for generation/deslop cleanup (not-is-comparison / em-dash / voice-contrast / negation-parade / reverse-not-is / trailer-ending / trailer-summary). This is a local style/readability gate, not an AIGC detector score; functional human text can be marked for review instead of hard-edited for a detector.
或 advisory (period-stutter / long-paragraph / micro-action-tic / negation-pair-tic / stock-reaction-tic / action-list-tic / abstract-summary-tic / cliche-density-tic / metaphor-density-tic / reasoning-chain-tic / system-notice-formality-tic / overcompressed-prose-tic / low-connective-density-tic / quote-emphasis-tic / formulaic-parallelism，是提示，justified 的长推理/氛围段可保留)。
--fail-on=blocking 只在出现 blocking finding 时退出 1；默认 --fail-on=all 有任何 finding 即退出 1。
Each finding also carries review: mechanical（表面形态确定、就地改写即可）或 semantic（可能承担叙事功能，需读上下文判断是否保留）；blocking 一律 mechanical。--list-review-classes 输出完整分类表（JSON）。
HTML comments (<!-- ... -->, e.g. the 去味:跳过 exemption marker) are metadata, not prose, and are never scanned.

The script reports findings only. It never rewrites text, because the safe fix is
contextual: usually delete the negative setup, write the positive term directly,
or show it via action/detail.`;

const STOP_CHARS = new Set(['。', '！', '？', '!', '?', '\n']);
const SOFT_SEPARATORS = new Set(['，', ',', '、', '；', ';', '：', ':']);
const HARD_SEPARATORS = new Set(['。', '.', '！', '!', '？', '?']);
const MAX_NEGATIVE_SPAN = 80;
const MAX_POSITIVE_SPAN = 80;

// 잘게 끊긴 문장: 가시 글자 수가 STUTTER_MAX_SENTENCE 이하인 서술 단문이 STUTTER_MIN_RUN개 연속 이어져 호흡이 없는 경우.
// 서술문만 센다. 대화·실시간 댓글·시스템 안내는 짧은 문장 묶음이 자연스러운 형식이므로 제외한다.
const STUTTER_MIN_RUN = 6;
const STUTTER_MAX_SENTENCE = 5;
// 긴 문단: 원시 문자 수가 기준을 넘으면 장면별 분리를 안내한다. 모바일 읽기의 보수적 기준이며 정상 문단은 훨씬 짧다.
const LONG_PARAGRAPH_CHARS = 200;

// 미세 동작 반복: ‘V了下 / V了一下 / 拍了两下 / 松了半圈’ 같은 가벼운 보어가 서술에 고밀도로 반복되면
// 과도하게 줄인 전보체의 흔적이 되기 쉽다. 따옴표 밖 서술만 검사하며 밀도와 횟수 기준을 모두 충족해야 보고한다.
// 한 번 나오는 것은 정상적인 중국어 표현이다.
const MICRO_TIC_PATTERN = /了(?:[一两三几半])?[下阵圈道声眼口气会]/g;
const MICRO_TIC_MIN_HITS = 5;
// ‘没A，也没B’, ‘不A，也不B’ 부정 대구: 치마오 인간 장편은 약 0.07곳/천 자, 모델 원고는 0.4–1.5곳/천 자다.
// 인물이 하지 않은 행동을 나열하는 것은 영어식 리듬이다. 한 장에 3곳 이상이면 안내 하나를 보고한다.
const NEGATION_PAIR_PATTERN = /(?:没有|没|不)[^，。！？；,!?\n]{1,10}[，,；]\s*[^，。！？；,!?\n]{0,6}?也(?:没有|没|不)/g;
const NEGATION_PAIR_MIN_HITS = 3;
const MICRO_TIC_PER_KILO = 6;

// 상투적 반응 세부: 신체 묘사 자체를 금지하지 않고 ‘부위 + 미세 동작/상태’가 무더기로 나타나는 경우를 안내한다.
// ‘胸口像被撞了一下’, 목울대·눈가·낮아지는 목소리 같은 범용 감정 꼬리와 ‘차분한 말투 +
// 낭독/선고하는 듯함’ 템플릿을 포함한다. 어휘 변화가 커서 단어별 blocking은 하지 않고 한 장에 4곳 모일 때
// advisory로 각 위치의 삭제 테스트를 요구한다. 물리적 결과를 전달하는 정상 부상·싸움·생리 반응은 유지할 수 있다.
const STOCK_REACTION_PATTERNS = [
  /(?:指尖|手指|指节|手背|掌心|拳头|袖口|衣角|裙角|下唇|嘴唇|唇角|嘴角|眉头|眼底|眸光|目光|视线|肩膀|呼吸)[^。！？!?\n]{0,16}(?:轻轻|微微|缓缓|悄然|不自觉|无意识|下意识|攥紧|握紧|收紧|绞紧|泛白|发白|叩|敲|摩挲|抿紧|抿成|移开|垂下|躲开|一颤|颤了?一下|停了?一下|顿了?一下)/g,
  /(?:语气|声音)[^。！？!?\n]{0,12}(?:平静|冷静|平淡|冷淡|淡漠|平直)[^。！？!?\n]{0,12}(?:像|仿佛|如同|好像)[^。！？!?\n]{0,16}(?:念|读|报|说|陈述|宣判|背诵)/g,
  /(?:胸口|心口)[^。！？!?\n]{0,16}(?:像|仿佛|如同|好像)[^。！？!?\n]{0,16}(?:撞|锤|压|攥|堵)[^。！？!?\n]{0,8}(?:一下|一记|一拳)?/g,
  /(?:声音|嗓音|语气)[^。！？!?\n]{0,12}(?:放轻|压低|发紧|发颤|很轻|轻了些)/g,
  /(?:喉结|喉头|喉咙)[^。！？!?\n]{0,10}(?:滚|动|紧|堵|发涩|发干)/g,
  /(?:眼眶|眼圈|鼻子)[^。！？!?\n]{0,8}(?:发红|红了|发热|发酸|一酸)/g,
  /(?:抿了?下唇|抿了?抿唇|抿了?下嘴|抿着笑)/g,
];
const STOCK_REACTION_MIN_HITS = 4;
// 보정 자료(사람이 쓴 원문, <br>은 줄바꿈으로 복원): qimao 장편 5584개 장 + heiyan 단편 전체 3983편.
// 장편의 장 단위(중앙값 약 2100자)에서는 per-kilo를 1.0→1.5로 바꿔도 오탐률이 0.43%→0.39%로 거의 변하지 않는다.
// 단편 전체 8000~20000자에서는 MIN_HITS가 사실상 무의미해져 밀도 기준만 남으며, 1.0일 때 오탐률은 5.57%다.
// 1.5에서는 1.46%로 낮아진다. 따라서 1.5를 택해 두 모집단을 같은 규모로 맞춘다(네 사본이 같은 기준을 공유).
const STOCK_REACTION_PER_KILO = 1.5;

// 감시 카메라식 행동 목록: 같은 문단에 범용 동작 동사(伸手/拿起/取过/挑开/放下/转身 등)를 연속 쌓고
// 쉼표·모점으로 연결해 절차표처럼 만들면 시점의 온기가 없는 감시 기록처럼 읽힌다. advisory만 적용한다.
// 싸움·추격 등의 기능적 동작 설계는 유지하거나 사람이 재검토할 수 있다.
const ACTION_LIST_VERB_PATTERN = /伸手|抬手|探手|拿起|拿过|取出|取过|掏出|摸出|抓起|攥住|握住|捏住|按住|推开|拉开|打开|关上|放下|递给|挑开|掀开|扯开|拧开|倒出|端起|转身|回头|抬头|低头|弯腰|俯身|走到|走向|坐下|站起|看向|看着|盯着|扫过/g;
const ACTION_LIST_MIN_HITS = 5;
const ACTION_LIST_MIN_SEPARATORS = 4;

// 추상적 요약 반복: 템플릿 문단은 인물의 현재 경험을 ‘命运/棋局/
// 这一刻终于明白/才刚刚开始’ 같은 작가 요약으로 끌어올리곤 한다. 개별 단어는 장르에 기여할 수 있으므로 고밀도 집중만 보고한다.
const ABSTRACT_SUMMARY_PATTERNS = [
  /这一刻[，,]?[^\n。！？!?]{0,24}(?:终于|才)(?:明白|意识到)/g,
  /从这一刻开始/g,
  /(?:命运|宿命)[^\n。！？!?]{0,28}(?:齿轮|棋局|獠牙|改写|推向|安排)/g,
  /早已[^\n。！？!?]{0,8}(?:布好|安排好)[^\n。！？!?]{0,8}(?:棋局|局)/g,
  /前所未有的(?:决意|清醒|勇气|力量|恐惧|平静|信念)/g,
  /(?:反击|复仇|战争|较量|故事|命运)[^\n。！？!?]{0,12}才刚刚开始/g,
  /(?:新的开始|全新的开始)/g,
];
const ABSTRACT_SUMMARY_MIN_HITS = 3;
const ABSTRACT_SUMMARY_PER_KILO = 4;

// 상투어 밀도: ‘仿佛/一丝’ 한 번은 정상 중국어일 수 있으나 고밀도로 모이면 템플릿 어조가 된다.
// 단어 목록에는 저장소 banned-words에서 고위험으로 명시한 형태만 넣어 일반 기능어까지 일괄 포착하지 않는다.
const CLICHE_PATTERNS = [
  /仿佛|犹如|宛若|如同/g,
  /一丝|一抹|些许|几分|隐约/g,
  /深吸一口气|缓缓|微微|轻轻|淡淡/g,
  /眼中闪过|嘴角勾起|眸光微微一闪|指节泛白|目光锐利|眼神锐利/g,
  /心中涌起一股|心头一震|心中一动|心下了然|心中暗道|心中一凛/g,
  /不容置疑|不容置喙|不易察觉|显而易见|毫无疑问|不可否认/g,
  /声音不大[，,]?却带着|语气平静无波|平静无波|声音平直|听不出情绪/g,
  /不知何时|唾手可得|无声翻涌|沉默(?:在[^。！？!?\n]{0,16})?蔓延|难以言说/g,
  /散发着一股|冰冷的光|格外刺眼|深邃而冰冷/g,
];
const CLICHE_DENSITY_MIN_HITS = 8;
const CLICHE_DENSITY_PER_KILO = 12;

// 비유 밀도: 생활 속 비유 하나는 장면에 기여할 수 있지만 ‘像/好像/仿佛/如同’이 무더기로 반복되면
// AI식 수사 쌓기가 되기 쉽다. advisory만 적용하며 필요한 수만 남기고 구체적 장면으로 돌아가게 한다.
// ‘像’을 다른 비유 단어로 바꾸라는 뜻이 아니다.
const METAPHOR_MARKER_PATTERN = /好像|像是|仿佛|宛如|如同|犹如|(?<![不头图画影录摄肖])像(?![头像素])/g;
const METAPHOR_LIKE_PHRASE_PATTERN = /(?:死|水|冰|火|潮水|石头|木头|机器|纸|铁|鬼|死人|刀|针|网|墙)一样/g;
const METAPHOR_DENSITY_MIN_HITS = 7;
const METAPHOR_DENSITY_PER_KILO = 3;

// 설명 연쇄 밀도: ‘他知道/他明白/这意味着/必须需要’처럼
// 독자 대신 계속 추론하면 보고서처럼 읽힌다. 개별 판단어는 추리에 기여할 수 있어 고밀도일 때만 현재 인물의 증거로 돌아가도록 안내한다.
const REASONING_CHAIN_PATTERNS = [
  { key: 'mental', core: true, pattern: /(?<![不没未无])(?:他|她|我)?(?:知道|明白|意识到|清楚|判断|确认|分析)/g },
  { key: 'connector', core: true, pattern: /这意味着|也就是说|换句话说|真正的问题(?:在于)?|问题在于|关键在于|在这种情况下|按照这个逻辑|只有这样|想到这里/g },
  { key: 'modal', core: true, pattern: /(?:(?<!不)(?:必须|需要|应该|只要|就会|可能|可以|能够|无法)|不能)[^。！？!?\n]{0,16}(?:判断|确认|承担|维持|稳住|控制|扩大|失控|带来|造成|理解|默认|回家|进门|核对|筛选|减少|建立|风险|结果|秩序|责任)/g },
  { key: 'abstract', core: false, pattern: /(?:任务|条件|风险|来源|逻辑|局面|结果|责任|秩序|规则|信息不足|决策能力)/g },
];
const REASONING_CHAIN_MIN_HITS = 8;
const REASONING_CHAIN_CORE_MIN_HITS = 4;
const REASONING_CHAIN_MIN_BUCKETS = 2;
const REASONING_CHAIN_PER_KILO = 18;

// 시스템 공지의 공문체: 대괄호 규칙·패널 행이 모인 곳의 강제 규칙 단어만 검사한다.
// 특정 장르의 단어 목록이 아니다. 단독의 엄격한 규칙, 일상 서술, 일반 대화는 발동하지 않는다.
const NOTICE_FORMAL_PATTERNS = [
  /不得|必须|不可|禁止|严禁|应当|须|需|务必/g,
  /当前|本公告|本规则|本系统|提示|任务失败|临时权限|权限|状态|等级/g,
  /维持|公共区域|秩序|优先|惩罚|处罚|违规|指令|执行/g,
  /被视为|同样计入|计入|承担|责任|单位|撤回|转发|截图/g,
];
const NOTICE_FORMAL_CORE_PATTERN = /不得|必须|不可|禁止|严禁|应当|须|需|务必|被视为|同样计入|计入/g;
const NOTICE_FORMAL_MIN_LINES = 4;
const NOTICE_FORMAL_MIN_HITS = 12;
const NOTICE_FORMAL_CORE_MIN_HITS = 5;
const NOTICE_FORMAL_PER_KILO = 60;

// 과도하게 압축한 짧은 문단: 과처리 표본에는 15자 이내 서술 문단이 많고 ‘的/了/就/着/过/呢/吧/啊’ 같은
// 자연스러운 연결이 적다. 대조 텍스트는 보통 이를 더 많이 유지한다. advisory만 적용하며 기계적인 분량 늘리기는 금지한다.
const OVERCOMPRESSED_PROSE_PARTICLE_PATTERN = /[的了就着过呢吧啊呀嘛]/g;
const OVERCOMPRESSED_PROSE_MIN_CHARS = 1200;
const OVERCOMPRESSED_PROSE_MIN_PARAS = 45;
const OVERCOMPRESSED_PROSE_SHORT_MAX_CHARS = 15;
const OVERCOMPRESSED_PROSE_SHORT_RATIO = 0.58;
const OVERCOMPRESSED_PROSE_PARTICLE_PER_KILO = 85;

// 낮은 연결 밀도: 기능어가 적다는 이유만으로는 중·장문이 많은 텍스트까지 잘못 포착한다.
// 따라서 “중장문 부족” 조건을 함께 적용하고 따옴표 밖의 서술만 살펴야 한다. overcompressed를 짧은 구간에서 보완하는 검사이며 권고만 제공한다.
const LOW_CONNECTIVE_FUNCTION_TERMS = ['的', '了', '就', '在', '是', '也', '都', '还', '又', '把', '被', '给', '这个', '那个', '里面', '以后', '时候', '现在', '因为', '所以', '但是', '不过', '然后', '已经', '还是', '起来', '出来', '下去'];
const LOW_CONNECTIVE_PLAIN_TERMS = ['的', '了', '就', '也', '还', '又', '这个', '那个', '东西', '事情', '时候', '里面', '以后', '一下', '一点', '有点', '还是'];
const LOW_CONNECTIVE_MIN_CHARS = 800;
const LOW_CONNECTIVE_FUNCTION_PER_KILO = 100;
const LOW_CONNECTIVE_PLAIN_PER_KILO = 65;
const LOW_CONNECTIVE_LONG_SENTENCE_CHARS = 30;
const LOW_CONNECTIVE_LONG_SENTENCE_RATIO = 0.08;

// 양자택일 ‘不是A就是B / 不是A也是B’에서 붙어 있는 ‘是’는 접속사 일부이며 긍정절의 계사가 아니다.
// ‘不是A，也不是B’의 두 번째 부정절을 전환으로 보지 않던 기존 예외를 유지하도록 ‘不’를 포함한다.
const COMPACT_EITHER_OR_PREV = new Set(['不', '就', '也']);
// 문장 끝 어기·반문 조사: ‘…，是吗 / 是吧 / 是嘛’는 반문 꼬리이며 부정 뒤의 긍정 전환이 아니다.
const TAG_PARTICLES = new Set(['吗', '吧', '嘛']);
// 문단 시작의 확인 표현: ‘不是第一次来。是的，他还记得……’의 ‘是的/是啊’는
// 앞 내용을 이어 확인하는 말이며 ‘不是 A，是 B’의 긍정 전환이 아니다.
const AFFIRMATION_TAG_PARTICLES = new Set(['的', '啊', '呀', '呢']);
const AFFIRMATION_TAG_BOUNDARY = new Set(['', '，', ',', '。', '.', '！', '!', '？', '?', '、', '；', ';', '：', ':', '\n', '\r', '\t', ' ']);

// 대사·시스템 안내·실시간 댓글의 따옴표 문자 쌍. stripQuoted와 quotedRanges가 같은 정의를 공유한다.
// 따옴표 구간은 줄을 넘지 않는다(문자 클래스에서 \n 제외). 여러 문단 대사의 마지막에만 닫거나 전각·반각 혼용으로
// 닫는 따옴표가 빠지는 일은 흔하다. 줄을 넘겨 짝지으면 닫히지 않은 따옴표 뒤 수백·수천 자를 모두
// 따옴표 안으로 보아 quotedRanges 소비자(not-is 다중 행 검사)가 서술 전체를 조용히 면제하게 된다.
const QUOTE_PAIRS = [['「', '」'], ['『', '』'], ['【', '】'], ['“', '”'], ['‘', '’'], ['"', '"'], ["'", "'"]];
const QUOTE_SOURCES = QUOTE_PAIRS.map(([open, close]) => `${escapeRegExp(open)}[^${escapeRegExpCharClass(close)}\\n]*${escapeRegExp(close)}`);

// ---- 실전 테스트에서 누락된 문장 패턴(실제 집필의 누락 예문에서 추출, 2026-07 보정) ----
// 보정 기준: 인간 집필 《万疆》 본문 20장(1/10/20/…/190장) + demo 첫 20장.
// blocking 규칙은 인간 말뭉치 적중이 거의 0이어야 한다(20장당 1곳 이하이며 사람이 해당 패턴임을 확인). 자료는 규칙별 주석 참조.

// 음량 대비 어조(실전 누락 A): ‘声音不高，第一句却稳稳压住了整个大厅。’
// 기존 검사에는 상투어 밀도의 ‘声音不大，却带着’만 있어 음량·전환 단어가 바뀌면 놓쳤다.
// 따옴표 밖 서술은 위치마다 blocking 처리한다. 음량 도입을 삭제하고 목소리가 현장에 미친 구체적 효과를 바로 쓴다.
// 보정: 《万疆》 20장 0건, demo 첫 20장 0건.
const VOICE_CONTRAST_PATTERN = /声音(?:并)?不[大高响亮][^。！？!?\n]{0,16}[却但偏]/g;

// 부정 병렬(실전 누락 B): ‘没有伴奏，没有和声，没有提词器。’ 같은 문장에 ‘没有X，’가 2개 이상 연속됨.
// 변형 ‘他没炫技，没有那种…架势。他只是唱’은 부정으로 도입한 뒤 ‘只是/只会/只有’로 긍정 마무리한다.
// ‘没/没有’ 절만 수집하며 ‘不X’는 제외한다. 인간 서술의 ‘不哭不闹’ 등이 너무 흔해 오탐 비용에 비해 이득이 없다.
// 단독 ‘没’는 두 가지 비부정 용법도 제외해야 정상 서술을 병렬로 오판하지 않는다.
//   1) 결합 형태소(沉没/淹没/埋没/出没/隐没 등): 앞 글자로 제외한다. “船沉没在雾里，没人回头，…只有…”는 세지 않는다.
//   2) 시간 관용구(没多久/没过多久/没等X): 뒤 글자로 제외한다. “没多久，没等她撑伞，…只有…”는 세지 않는다.
// ‘没有X’에는 두 모호성이 없다. 결합 형태소 뒤에는 ‘有’가 붙지 않으며 시간 관용어는 다음 글자 제외 규칙으로 이미 처리한다.
// 첫 번째 연속 나열 패턴에는 기존처럼 보호 조건을 추가하지 않는다.
// 보정: 《万疆》 20장 0건, demo 첫 20장 0건.
const NEGATION_PARADE_PATTERNS = [
  /(?:没有[^。！？!?\n，,]{1,12}[，,]){2}/g,
  /(?<![沉淹埋出隐湮吞覆漫泯])没(?!有?过?多久)(?:有)?[^。！？!?\n，,]{1,12}[，,]\s*没(?!有?过?多久)(?:有)?[^。！？!?\n，,]{1,16}[，,。.][^。！？!?\n，,]{0,6}只(?:是|会|有)/g,
];
const CROSS_NEGATION_START = /^不是[^。！？!?\n]{1,24}[。！？!?]?$/;
const CROSS_NEGATION_MIDDLE = /^(?:也|还)不是[^。！？!?\n]{1,24}[。！？!?]?$/;
const CROSS_NEGATION_END = /^只是[^。！？!?\n]{1,32}[。！？!?]?$/;

// 흔하지만 바로 오류로 판정할 수 없는 두 종류의 정형적 문장 구조는 권고만 제공한다. 차단 규칙과 달리 여기서는 의도적으로 검색한다.
// 대사: 자연스러운 주문 ‘不放辣，不放葱’은 목적어 최소 길이로 제외한다. 더 긴 동일 동사 목록의 기능은 의미 검토에 맡긴다.
const DECISION_FRAME_PATTERN = /至于([\u3400-\u9fff]{1,3})不\1[，,]\s*怎么\1/g;
const REPEATED_NEGATIVE_VERB_PATTERN = /不([\u3400-\u9fff]{1,2})([\u3400-\u9fff]{2,8})[，,]\s*不\1([\u3400-\u9fff]{2,8})/g;

// 역순 대비(실전 누락 C): ‘是真嗓子，不是修音修出来的’는 not-is-comparison의 역순 변형이다.
// not-is의 제외 기반을 재사용한다. 따옴표 내부 제거(maskQuoted), ‘是的/是啊’ 확인 표현(isAffirmationTagAt).
// 앞 글자 제외를 양자택일의 不/就/也에서 모든 ‘X是’ 접속사·부사 합성어로 확장한다(还是/只是/可是/但是/
// 于是/倒是/像是/若是/要是/正是/便是/总是/老是/更是/最是/算是/怕是/凡是/或是/即是/自是/
// 竟是/原是/本是/仍是/许是/净是/光是/单是/尽是). ‘是不是’ 의문 시작과 ‘不是吗/不是么/
// 不是吧’ 반문 꼬리는 별도로 제외한다.
// 보정: 《万疆》 20장 0건, demo 첫 20장 0건이므로 blocking으로 구현한다.
const REVERSE_NOT_IS_PATTERN = /是([^。！？!?\n，,]{1,12})[，,]\s*(?:而)?不是([^。！？!?\n]{1,20})/g;
const REVERSE_NOT_IS_PREV_EXCLUDE = new Set([...COMPACT_EITHER_OR_PREV, '还', '只', '可', '但', '于', '倒', '像', '若', '要', '正', '便', '总', '老', '更', '最', '算', '怕', '凡', '或', '即', '自', '竟', '原', '本', '仍', '许', '净', '光', '单', '尽']);

// 예고형 요약 마무리(실전 누락 D): ‘没人知道，这才刚刚开头。’, ‘一场…震惊接力，正朝着…缓缓压了过去。’
// 장 끝에서 독자 대신 다음 전개를 예고하는 것은 AI식 마무리다. 따옴표 제거 후 가시 글자 수로 정한 문말 구간만 행 단위로 검사한다.
// 본문 중간의 ‘没人知道’는 보통 일반 서술이므로 오탐하지 않는다. 따옴표 속 대사 ‘没人知道…’도 세지 않는다.
// ‘正式拉开序幕/帷幕’는 장면 속 사건의 개막 안내다(인간 예문: ‘钟声再度响起，比赛正式拉开序幕’).
// 서술자의 예고가 아니므로 앞쪽 lookbehind로 제외한다.
// 보정: 《万疆》 20장에서 ‘正式拉开序幕’ 개막 안내 2곳을 제외하면 0건, demo 첫 20장도 0건.
const TRAILER_ENDING_PATTERN = /没人知道|谁也不知道|谁也没想到|殊不知|(?:这)?才刚刚开(?:始|头)|正(?:朝着|向着)[^。！？!?\n]{0,24}(?:压|涌|袭|逼)(?:了?过去|了?过来|来)|(?<!正式)拉开(?:序幕|帷幕)|即将(?:开始|来临|降临)/g;
const TRAILER_ENDING_WINDOW_CHARS = 600;

// 장 끝 상태 요약체: 상세 개요의 결말 설정을 요약문 그대로 써서 마무리한다(‘这一夜注定无人入眠’,
// ‘这一切都结束了’, ‘新的人生才刚刚开始’, ‘命运的齿轮’). trailer-ending과 문말 구간을 공유하지만
// 이 규칙은 과거를 단정하고 trailer-ending은 미래를 예고한다. banned-words에서 명시적으로 금지한 형태만 수집한다.
// “(这|那)一刻…终于明白”는 포함하지 않는다. 실제 작가의 글에서는 정상적인 인식의 흐름이며, 단편의 1인칭 판단 문장은 오히려 매력 요소다.
// (short-craft의 ‘审判金句 / 心死余韵’). 밀도 유형은 advisory인 abstract-summary-tic이 담당한다.
// 각 분기는 문장 끝 단정 위치여야 한다. 아니면 조건절(等这一切结束了，我们就…), 동사 보어
// (这一切都说明得非常清楚), 성어를 가로지르는 일치(这一刻…命中注定), 계사 서술(这一战的结果是注定的),
// 타동사 용법(就这样…才结束了这个话题), 장면 내 안내(就这样…宣布…圆满落幕), 부정 인식
// (他不知道这一切意味着什么)까지 잡는다. 마지막 유형은 (?!什么)로 간접 의문을 제외하며 이는 단정과 반대다.
// 보정 자료(글 끝 600자 구간, 일치 항목을 하나씩 수동 검토): qimao 장 중간 구간 20000개 장에서 1곳 일치(0.005%),
// heiyan 단편 전체 3999편에서 22곳 일치(0.550%, 모두 위에 나열한 금지 형태). 같은 자료에서 기존 trailer-ending
// 각각 1.345% / 6.602%가 적중하므로 이 규칙의 오탐 범위는 같은 구간의 기존 규칙보다 훨씬 작다. 단편 전체가 마무리 구간이므로
// 기준 발생률이 장편의 장 중간 구간보다 본래 높으므로 두 모집단의 수치를 따로 보고한다.
const TRAILER_SUMMARY_PATTERN = /这一(?:夜|天|刻|战|年|局|役)[，,]?[^。！？!?，,\n]{0,6}(?<!命中)(?<!是)注定[^。！？!?\n]{0,8}[。！]|就这样[，,][^。！？!?，,\n]{0,8}(?:一切|全部)[^。！？!?，,\n]{0,4}(?:结束了|落幕|收场)[。！]|这一切[，,]?[^。！？!?，,\n]{0,6}(?:都)?(?:说明|意味着|结束了)(?!的)(?:(?!什么)[^。！？!?\n]){0,6}[。！]|(?:新的篇章|新的旅程|崭新的篇章|新的人生)[^。！？!?\n]{0,6}(?:开始|拉开|展开)|命运[^。！？!?\n]{0,6}齿轮/g;

// 따옴표 강조 남용(실사용에서 누락된 유형 E, 밀도 기반 권고, metaphor-density-tic 방식):
// 서술 속 짧은 단어를 따옴표로 강조하는 경우(他是被请来"把关"的). 서술 층위에서 1~4자를 감싼 따옴표 쌍만 센다.
// 제외 항목: 【】 시스템 패널, 인용 동사(说|道|问|喊|答|念|叫|回|吼|嘀咕 및 추가한 骂|写|读|唱)의
// 앞 6자/뒤 3자 안에 붙어 있는 아주 짧은 대사, 따옴표 안에 문장부호가 있는 대사, 따옴표 밖 서술이 없는 행(독립 대사/
// 실시간 댓글/연속 의성어), 중첩 따옴표(대사 안의 강조). 전체 글에서 3곳 이상이면 한 건 보고한다. 한 곳의 강조는
// 정상적인 수사이며, 밀도가 높아야 상투적인 문체가 된다.
// 보정: demo 첫 20개 장은 임계값 초과 0개, 《万疆》 20개 장은 2개(포스터 문구 “我在番城” 계열,
// “邀战书” 등 전달 문구로, 실제 작가도 이렇게 쓴다). 따라서 이 규칙은 권고만 제공하며 차단으로 격상하지 않는다.
const QUOTE_EMPHASIS_MIN_HITS = 3;
const QUOTE_EMPHASIS_MAX_VISIBLE = 4;
const QUOTE_EMPHASIS_SPEECH_VERB_PATTERN = /[说道问喊答念叫回吼骂写读唱嘀咕]/;

// review 분류: 후속 처리를 나누는 기준. mechanical = 일치한 표면 형태 자체가 문제이므로 집필 단계에서 바로 고치면 된다.
// semantic = 같은 형태가 서사 기능을 할 수 있으므로 문맥을 읽고 유지/수정을 판단한다(의미 검토에 위임). blocking은 반드시
// mechanical이어야 한다(blocking은 별도 판단 없이 모두 제거해야 한다는 뜻). 새 finding type은 여기에 등록해야 하며, 누락되면 실행 중
// 즉시 오류를 내고 종료한다(scripts/test-ai-patterns.sh도 소스에서 type을 추출해 이 표와 양방향 대조한다).
//   type                         review      이유
//   not-is-comparison            mechanical  고정 문형 “不是A，而是B”, 차단
//   voice-contrast               mechanical  고정 대비 문형 “声音不大…却”, 차단
//   negation-parade              mechanical  고정 부정 병렬 문형, 차단
//   reverse-not-is               mechanical  역순 대비 문형 “是A，不是B”, 차단
//   trailer-ending               mechanical  글 끝 구간의 고정 예고 문구, 차단
//   trailer-summary              mechanical  글 끝 구간의 고정 요약 문구, 차단
//   em-dash                      mechanical  문장부호, 차단
//   long-paragraph               mechanical  문단 길이 임계값, 문단을 나누면 해결
//   period-stutter               mechanical  연속된 짧은 문장 수, 문장을 합치면 해결
//   micro-action-tic             mechanical  고정 보어 “了下/了一下”의 밀도
//   negation-pair-tic            semantic    “没A，也没B” 부정 대구, 실제로 강조해야 하는 부분은 유지
//   cliche-density-tic           mechanical  고정 금지 어휘 목록의 밀도
//   stock-reaction-tic           semantic    신체 반응은 물리적 결과나 감정을 표현할 수 있으므로 각 부분을 삭제해 보며 판단
//   action-list-tic              semantic    전투/추격 등 기능적인 동작 구성은 유지 가능
//   abstract-summary-tic         semantic    작가의 요약/전지적 시점이 부적절한지는 문맥에 따라 판단
//   metaphor-density-tic         semantic    비유가 장면에 기여하는지, 무엇을 삭제할지는 문맥을 읽고 판단
//   reasoning-chain-tic          semantic    독자 대신 추론하는 설명의 연쇄이며, 긴 추론 문단도 정당할 수 있음
//   system-notice-formality-tic  semantic    시스템/규칙 텍스트는 본래 공문체가 가능하므로 장르와 기능을 확인
//   overcompressed-prose-tic     semantic    짧은 문단의 높은 밀도는 리듬 선택일 수 있으므로 기계적인 분량 늘리기 금지
//   low-connective-density-tic   semantic    위와 같으며, 접속어 추가 여부는 읽는 느낌에 따라 판단
//   quote-emphasis-tic           semantic    표어/전달 문구의 따옴표는 정상적인 표현
//   formulaic-parallelism        semantic    정형적인 병렬 구조는 해명이나 의문 해소 기능을 할 수 있음
const REVIEW_CLASSES = Object.freeze({
  'not-is-comparison': 'mechanical',
  'voice-contrast': 'mechanical',
  'negation-parade': 'mechanical',
  'reverse-not-is': 'mechanical',
  'trailer-ending': 'mechanical',
  'trailer-summary': 'mechanical',
  'em-dash': 'mechanical',
  'long-paragraph': 'mechanical',
  'period-stutter': 'mechanical',
  'micro-action-tic': 'mechanical',
  'negation-pair-tic': 'semantic',
  'cliche-density-tic': 'mechanical',
  'stock-reaction-tic': 'semantic',
  'action-list-tic': 'semantic',
  'abstract-summary-tic': 'semantic',
  'metaphor-density-tic': 'semantic',
  'reasoning-chain-tic': 'semantic',
  'system-notice-formality-tic': 'semantic',
  'overcompressed-prose-tic': 'semantic',
  'low-connective-density-tic': 'semantic',
  'quote-emphasis-tic': 'semantic',
  'formulaic-parallelism': 'semantic',
});

const options = {
  json: false,
  files: [],
  failOn: 'all',
};

for (let i = 2; i < process.argv.length; i += 1) {
  const arg = process.argv[i];
  if (arg === '--check') {
    // normalize-punctuation.js와의 인터페이스 대칭성을 위해 허용한다. 탐지는 항상 검사만 수행한다.
  } else if (arg === '--list-review-classes') {
    process.stdout.write(`${JSON.stringify(REVIEW_CLASSES, null, 2)}\n`);
    process.exit(0);
  } else if (arg === '--json') {
    options.json = true;
  } else if (arg.startsWith('--fail-on=')) {
    const v = arg.slice('--fail-on='.length);
    if (v !== 'blocking' && v !== 'all') die(`--fail-on must be 'blocking' or 'all'`);
    options.failOn = v;
  } else if (arg === '-h' || arg === '--help') {
    process.stdout.write(`${USAGE}\n`);
    process.exit(0);
  } else if (arg.startsWith('-')) {
    die(`Unknown option: ${arg}`);
  } else {
    options.files.push(arg);
  }
}

if (options.files.length === 0) {
  die('No files provided');
}

let failed = false;
const allFindings = [];

for (const file of options.files) {
  const fullPath = path.resolve(file);
  let input;
  try {
    input = fs.readFileSync(fullPath, 'utf8');
  } catch (error) {
    failed = true;
    if (!options.json) console.error(`${file}: unable to read (${error.message})`);
    continue;
  }

  let whitelist;
  try { whitelist = loadStyleWhitelist(fullPath); }
  catch (error) { die(`${file}: unable to read .deslop-whitelist (${error.message})`); }
  const findings = scanDocument(maskStyleText(input, whitelist)).map((finding) => ({ file, ...finding, review: reviewClass(finding.type) }));
  allFindings.push(...findings);
}

if (options.json) {
  process.stdout.write(`${JSON.stringify({ findings: allFindings }, null, 2)}\n`);
} else {
  for (const finding of allFindings) {
    console.log(`${finding.file}:${finding.line}:${finding.column}: [${finding.severity}] ${finding.type}: ${finding.message} (${finding.excerpt})`);
  }
}

if (failed) process.exit(2);
// --fail-on=blocking은 blocking finding이 있을 때만 종료 코드 1을 반환한다(advisory는 보고만 함). 기본값 all은 기존처럼 finding이 하나라도 있으면 1을 반환한다.
const hasBlocking = allFindings.some((f) => f.severity === 'blocking');
if (options.failOn === 'blocking' ? hasBlocking : allFindings.length > 0) process.exit(1);

function reviewClass(type) {
  const review = REVIEW_CLASSES[type];
  if (!review) {
    console.error(`internal error: finding type '${type}' has no review class (add it to REVIEW_CLASSES)`);
    process.exit(2);
  }
  return review;
}

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function escapeRegExpCharClass(text) {
  return text.replace(/[\\\]^-]/g, '\\$&');
}

function die(message) {
  console.error(message);
  console.error(USAGE.trimEnd());
  process.exit(2);
}

// unclosedOpenings: 글 끝까지 닫히지 않은 `<!--`의 위치("행:열"). 닫히지 않은 주석은 주석으로 취급하지 않는다.
// 그렇지 않으면 `-->` 하나를 빠뜨렸을 때 뒤의 장 전체가 숨겨진다. 해당 위치는 본문으로 검사하되 `<!--` 자체만 지운다.
function scanDocument(input, unclosedOpenings = new Set()) {
  const lines = input.split(/\r?\n/);
  const findings = [];
  let fence = null;
  let inFrontMatter = hasYamlFrontMatter(lines);
  let commentOpen = false;
  let commentStart = null;
  let block = [];
  const proseLines = [];

  const flushBlock = () => {
    if (block.length === 0) return;
    findings.push(...scanBlock(block));
    block = [];
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();

    if (inFrontMatter) {
      if (index > 0 && trimmed === '---') inFrontMatter = false;
      continue;
    }

    const fenceMarker = parseFenceMarker(trimmed);
    if (fence) {
      if (fenceMarker && fenceMarker.char === fence.char && fenceMarker.length >= fence.length) {
        fence = null;
      }
      continue;
    }

    if (fenceMarker && !commentOpen) {
      flushBlock();
      fence = fenceMarker;
      continue;
    }

    // HTML 주석(예: `<!-- 去味:跳过 -->` 예외 표식)은 본문이 아닌 메타정보이므로 같은 길이의 공백으로 바꿔
    // 열 번호를 유지한다. 행 전체가 주석이면 건너뛰며, 주석은 여러 행에 걸칠 수 있다.
    const masked = maskHtmlComments(line, commentOpen, index, unclosedOpenings);
    commentOpen = masked.open;
    if (masked.openedAt !== null) commentStart = masked.openedAt;
    if (masked.text !== line && !masked.text.trim()) continue;

    block.push({ text: masked.text, lineNo: index + 1 });
    proseLines.push({ text: masked.text, lineNo: index + 1 });
  }

  if (commentOpen && commentStart !== null) {
    return scanDocument(input, new Set([...unclosedOpenings, commentStart]));
  }

  flushBlock();
  findings.push(...scanProsePatterns(proseLines));
  findings.sort((a, b) => a.line - b.line || a.column - b.column);
  return findings;
}

// 문단 단위 검사: 지나친 마침표 분할(연속된 짧은 서술문), 긴 문단, 줄표(기계적으로 치환하지 않고 기능에 맞게 수정).
function scanProsePatterns(proseLines) {
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;

    const dashPattern = /——|—|--+/g;
    let dash;
    while ((dash = dashPattern.exec(text)) !== null) {
      findings.push({
        line: lineNo,
        column: dash.index + 1,
        type: 'em-dash',
        severity: 'blocking',
        message: '破折号按功能改写：打断→动作 beat/短句，拖长音→省略或动作，插入说明→逗号/冒号；勿一律改句号。',
        excerpt: compact(text.slice(Math.max(0, dash.index - 8), dash.index + dash[0].length + 8)),
      });
    }

    if (trimmed.length > LONG_PARAGRAPH_CHARS) {
      findings.push({
        line: lineNo,
        column: 1,
        type: 'long-paragraph',
        severity: 'advisory',
        message: `段落过长（${trimmed.length} 字）：按镜头/新动作/新线索/视线切换断段，别一段到底。`,
        excerpt: compact(trimmed.slice(0, 40)),
      });
    }
  }

  findings.push(...findVoiceContrast(proseLines));
  findings.push(...findNegationParade(proseLines));
  findings.push(...findFormulaicParallelism(proseLines));
  findings.push(...findReverseNotIs(proseLines));
  findings.push(...findTrailerEnding(proseLines));
  findings.push(...findQuoteEmphasisTic(proseLines));
  findings.push(...findPeriodStutter(proseLines));
  findings.push(...findMicroActionTic(proseLines));
  findings.push(...findNegationPairTic(proseLines));
  findings.push(...findStockReactionTic(proseLines));
  findings.push(...findActionListTic(proseLines));
  findings.push(...findAbstractSummaryTic(proseLines));
  findings.push(...findClicheDensityTic(proseLines));
  findings.push(...findMetaphorDensityTic(proseLines));
  findings.push(...findReasoningChainTic(proseLines));
  findings.push(...findNoticeFormalityTic(proseLines));
  findings.push(...findOvercompressedProseTic(proseLines));
  findings.push(...findLowConnectiveDensityTic(proseLines));
  return findings;
}

// 음량 대비 문체(실사용에서 누락된 유형 A): 따옴표 밖 서술의 각 일치를 차단하고 위치와 발췌는 원문에서 가져온다.
// (maskQuoted가 같은 길이의 자리표시자로 오프셋을 보존한다. 일치 조각에는 물음표 자리표시자가 없어 치환 영역에 들어가지 않는다.)
function findVoiceContrast(proseLines) {
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const masked = maskQuoted(text);
    VOICE_CONTRAST_PATTERN.lastIndex = 0;
    let match;
    while ((match = VOICE_CONTRAST_PATTERN.exec(masked)) !== null) {
      findings.push({
        line: lineNo,
        column: match.index + 1,
        type: 'voice-contrast',
        severity: 'blocking',
        message: '音量反差腔：「声音不大/不高…却/但…」是 AI 高频反差模板；删掉音量铺垫，直接写声音落进场子的具体效果（谁停了手、哪排安静了）。',
        excerpt: compact(text.slice(match.index, match.index + match[0].length)),
      });
    }
  }

  return findings;
}

// 부정 병렬(실사용에서 누락된 유형 B): 한 문장에서 “没有X，”를 연속 나열하거나 먼저 부정한 뒤 “只是”로 긍정 결론을 맺는 형태.
// 같은 텍스트에 겹쳐 일치할 수 있으므로 구간 기준으로 중복을 제거해 한 번만 보고한다.
function findNegationParade(proseLines) {
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const masked = maskQuoted(text);

    const spans = [];
    for (const pattern of NEGATION_PARADE_PATTERNS) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(masked)) !== null) {
        spans.push([match.index, match.index + match[0].length]);
      }
    }
    spans.sort((a, b) => a[0] - b[0]);

    let lastEnd = -1;
    for (const [start, end] of spans) {
      if (start < lastEnd) {
        lastEnd = Math.max(lastEnd, end);
        continue;
      }
      lastEnd = end;
      findings.push({
        line: lineNo,
        column: start + 1,
        type: 'negation-parade',
        severity: 'blocking',
        message: '否定排比：「没有X，没有Y…」/「没X，没有Y，只是Z」是 AI 高频排比模板；删掉否定清单，直接写现场实际有什么，最多留一个最有信息量的否定。',
        excerpt: compact(text.slice(start, end)),
      });
    }
  }

  return findings;
}

function findFormulaicParallelism(proseLines) {
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    for (const [pattern, message] of [
      [DECISION_FRAME_PATTERN, '「至于X不X，怎么X」把同一决定拆成工整栏目；若只是复述细纲，压成角色当下的一次判断或直接动作。'],
      [REPEATED_NEGATIVE_VERB_PATTERN, '同动词「不V A，不V B」容易写成否定清单；含台词也要按语境复核，保留真正有功能的一项即可。'],
    ]) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(text)) !== null) {
        findings.push({
          line: lineNo,
          column: match.index + 1,
          type: 'formulaic-parallelism',
          severity: 'advisory',
          message,
          excerpt: compact(match[0]),
        });
      }
    }
  }

  // 여러 문단에 걸친 “不是A / 也不是B / 只是C”는 상세 개요를 되풀이한 것일 수도 있고 정상적인
  // 해명, 의문 해소 또는 감정의 점층일 수도 있다. 구문만으로는 안정적으로 구분할 수 없어 권고만 제공하고 의미 검토에 넘긴다.
  const window = [];
  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed) continue;
    if (isDivider(trimmed) || isStructural(trimmed)) {
      window.length = 0;
      continue;
    }
    if (window.length && lineNo - window[window.length - 1].lineNo > 2) window.length = 0;
    window.push({ text: maskQuoted(trimmed), original: trimmed, lineNo });
    if (window.length > 3) window.shift();
    if (window.length !== 3) continue;
    if (!CROSS_NEGATION_START.test(window[0].text)
      || !CROSS_NEGATION_MIDDLE.test(window[1].text)
      || !CROSS_NEGATION_END.test(window[2].text)) continue;
    findings.push({
      line: window[0].lineNo,
      column: 1,
      type: 'formulaic-parallelism',
      severity: 'advisory',
      message: '跨段「不是… / 也不是… / 只是…」可能是工整否定铺排，也可能承担辩解或悬念排除；通读语境，只在重复细纲或拖慢画面时改写。',
      excerpt: compact(window.map((entry) => entry.original).join(' / ')),
    });
  }

  return findings;
}

// 역순 대비 문체(실사용에서 누락된 유형 C): “是A，不是B”. 제외 처리는 not-is-comparison의 기반 기능을 재사용한다.
// 따옴표 안을 제외하고 “是的/是啊” 확인 표현을 제외한다. 앞 글자와의 합성어 및 반문 어미는 REVERSE_NOT_IS_PREV_EXCLUDE 주석 참조.
function findReverseNotIs(proseLines) {
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const masked = maskQuoted(text);
    REVERSE_NOT_IS_PATTERN.lastIndex = 0;
    let match;
    while ((match = REVERSE_NOT_IS_PATTERN.exec(masked)) !== null) {
      const start = match.index;
      // “就是/也是/还是/只是/可是…”의 “是”는 합성어의 일부이며 긍정 항목을 연결하는 계사가 아니다.
      if (REVERSE_NOT_IS_PREV_EXCLUDE.has(masked[start - 1])) continue;
      // “是不是…”로 시작하는 의문문.
      if (masked[start + 1] === '不') continue;
      // “是的，…不是…”의 확인 연결 표현(not-is 판정 재사용).
      if (isAffirmationTagAt(masked, start)) continue;
      // “…，不是吗/不是么/不是吧”의 반문 어미.
      if (/^[吗么吧]/.test(match[2])) continue;
      findings.push({
        line: lineNo,
        column: start + 1,
        type: 'reverse-not-is',
        severity: 'blocking',
        message: '反序对比腔：「是A，不是B」与「不是A，是B」同族；删掉后置否定，直接写 A 的具体表现，或用细节让读者自己对比。',
        excerpt: compact(text.slice(start, start + match[0].length)),
      });
    }
  }

  return findings;
}

// 예고/요약형 마무리(실사용에서 누락된 유형 D): 글 끝 구간만 검사한다. 끝에서 역방향으로 서술 행을 수집하며,
// 따옴표 내용을 제거한 가시 문자 수가 구간 크기에 도달하면 멈춘다(행 단위로 올림하며 경계 행도 전체를 포함).
function findTrailerEnding(proseLines) {
  const windowLines = [];
  let accumulated = 0;

  for (let i = proseLines.length - 1; i >= 0 && accumulated < TRAILER_ENDING_WINDOW_CHARS; i -= 1) {
    const { text } = proseLines[i];
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    windowLines.unshift(proseLines[i]);
    accumulated += visibleLength(stripQuoted(trimmed));
  }

  const findings = [];
  for (const { text, lineNo } of windowLines) {
    const masked = maskQuoted(text);
    TRAILER_ENDING_PATTERN.lastIndex = 0;
    let match;
    while ((match = TRAILER_ENDING_PATTERN.exec(masked)) !== null) {
      findings.push({
        line: lineNo,
        column: match.index + 1,
        type: 'trailer-ending',
        severity: 'blocking',
        message: '预告式总结收尾：「没人知道/才刚刚开始/正朝着…压了过去」是 AI 章尾预告腔；结尾停在具体动作、画面或一句台词上，悬念让事件自己挂住，别替读者预告下一章。',
        excerpt: compact(text.slice(match.index, match.index + match[0].length)),
      });
    }
    TRAILER_SUMMARY_PATTERN.lastIndex = 0;
    let summaryMatch;
    while ((summaryMatch = TRAILER_SUMMARY_PATTERN.exec(masked)) !== null) {
      findings.push({
        line: lineNo,
        column: summaryMatch.index + 1,
        type: 'trailer-summary',
        severity: 'blocking',
        message: '章尾状态总结体：「这一夜注定…/这一切都结束了/新的人生才刚刚开始/命运的齿轮」是把细纲的结尾设定原样写成了总结句；结尾设定要落成最后一个具体动作、画面或台词，别替读者盖章。',
        excerpt: compact(text.slice(summaryMatch.index, summaryMatch.index + summaryMatch[0].length)),
      });
    }
  }

  return findings;
}

// 따옴표 강조 남용(실사용에서 누락된 유형 E): 서술 층위에서 1~4자를 따옴표 쌍으로 강조한 조각을 세며 전체 글에서 한 건만 보고한다.
// (밀도 기반 분포 특성). 대사 제외 조건은 QUOTE_EMPHASIS_* 상수 주석 참조.
function findQuoteEmphasisTic(proseLines) {
  let hits = 0;
  let firstLine = null;
  const samples = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    // 따옴표 밖에 서술이 없는 행(독립 대사/실시간 댓글/연속 의성어 ““叮咚~”“叮咚~””)은 전체를 건너뛴다.
    // 강조 남용은 서술 층위의 특성이므로 서술이 없으면 강조 여부를 따질 필요가 없다.
    if (visibleLength(stripQuoted(trimmed)) === 0) continue;
    const ranges = quotedRanges(text);

    for (const [start, end] of ranges) {
      if (text[start] === '【') continue; // 시스템 패널/공지의 표기로, 강조 따옴표가 아니다.
      // 중첩 따옴표: 대사 안의 강조는 인물의 말이므로 서술 층위의 강조 남용으로 세지 않는다.
      if (ranges.some(([s2, e2]) => s2 <= start && end <= e2 && (s2 !== start || e2 !== end))) continue;
      const inner = text.slice(start + 1, end - 1);
      const visible = visibleLength(inner);
      if (visible < 1 || visible > QUOTE_EMPHASIS_MAX_VISIBLE) continue;
      if (/[。！？!?…，,；;：:]/.test(inner)) continue; // 문장부호를 포함하면 대사/안내 방송이며 강조가 아니다.
      const before = text.slice(Math.max(0, start - 6), start);
      const after = text.slice(end, end + 3);
      if (QUOTE_EMPHASIS_SPEECH_VERB_PATTERN.test(before) || QUOTE_EMPHASIS_SPEECH_VERB_PATTERN.test(after)) continue; // 인용 동사에 인접하면 아주 짧은 대사다.
      hits += 1;
      if (firstLine === null) firstLine = lineNo;
      if (samples.length < 6 && !samples.includes(inner)) samples.push(inner);
    }
  }

  if (hits < QUOTE_EMPHASIS_MIN_HITS) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'quote-emphasis-tic',
    severity: 'advisory',
    message: `引号强调滥用：叙述里 1-4 字短词加引号强调 ${hits} 处；只留真正反讽/转述必要的一两处，其余去掉引号直接写，或换成具体动作让读者自己品。`,
    excerpt: compact(samples.join(' ')),
  }];
}

// 부정 대구: 따옴표 밖 서술의 “没A，也没B” 문장을 세며 전체 글에서 한 건만 보고한다.
function findNegationPairTic(proseLines) {
  let hits = 0;
  let firstLine = null;
  const samples = [];
  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    NEGATION_PAIR_PATTERN.lastIndex = 0;
    let match;
    while ((match = NEGATION_PAIR_PATTERN.exec(narrative)) !== null) {
      hits += 1;
      if (firstLine === null) firstLine = lineNo;
      if (samples.length < 4) samples.push(match[0]);
    }
  }
  if (hits < NEGATION_PAIR_MIN_HITS) return [];
  return [{
    line: firstLine,
    column: 1,
    type: 'negation-pair-tic',
    severity: 'advisory',
    message: `否定对偶偏多：「没A，也没B」式叙述 ${hits} 处；写人物没做什么是英文式节奏，改成他做了什么（留一两处真正要强调的）。`,
    excerpt: compact(samples.join(' | ')),
  }];
}

// 미세 동작 반복: 따옴표 밖 서술에서 “了X量词”라는 짧은 보어의 밀도를 센다. 횟수와 천 자당 밀도 두 기준을 적용하며,
// 전체 글에서 한 건만 보고한다(개별 위치의 문제가 아니라 분포 수준의 특성이다).
function findMicroActionTic(proseLines) {
  let hits = 0;
  let narrativeChars = 0;
  let firstLine = null;
  const samples = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    narrativeChars += visibleLength(narrative);
    MICRO_TIC_PATTERN.lastIndex = 0;
    let match;
    while ((match = MICRO_TIC_PATTERN.exec(narrative)) !== null) {
      hits += 1;
      if (firstLine === null) firstLine = lineNo;
      if (samples.length < 6 && !samples.includes(match[0])) samples.push(match[0]);
    }
  }

  if (narrativeChars === 0 || hits < MICRO_TIC_MIN_HITS) return [];
  const perKilo = (hits / narrativeChars) * 1000;
  if (perKilo < MICRO_TIC_PER_KILO) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'micro-action-tic',
    severity: 'advisory',
    message: `微动作复读：「了下/了一下」式轻量补语 ${hits} 处（${perKilo.toFixed(1)}/千字）；同一反应模板高密度复现是机械指纹，合并动作 beat、换具体细节，别每个动作都补一个轻反应尾巴。`,
    excerpt: compact(samples.join(' ')),
  }];
}

// 상투적 반응 묘사: 따옴표 밖 서술의 일반적인 신체 부위/목소리 반응과 고정된 어조 비유를 센다.
// 삭제 테스트 후보이며 신체 묘사 금지 목록이 아니다. 전체 글에서 한 건만 보고하고, 행동의 결과,
// 부상, 인물의 습관 또는 플롯 기능을 가진 세부 묘사는 유지한다.
function findStockReactionTic(proseLines) {
  let hits = 0;
  let narrativeChars = 0;
  let firstLine = null;
  const samples = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    narrativeChars += visibleLength(narrative);

    for (const pattern of STOCK_REACTION_PATTERNS) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(narrative)) !== null) {
        hits += 1;
        if (firstLine === null) firstLine = lineNo;
        const sample = sentenceAround(narrative, match.index);
        if (samples.length < 6 && sample && !samples.includes(sample)) samples.push(sample);
      }
    }
  }

  if (narrativeChars === 0 || hits < STOCK_REACTION_MIN_HITS) return [];
  const perKilo = (hits / narrativeChars) * 1000;
  if (perKilo < STOCK_REACTION_PER_KILO) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'stock-reaction-tic',
    severity: 'advisory',
    message: `套式反应细节：指尖/指节/喉结/眼圈/声音放轻等通用反应或“平静得像在念”式语气比喻 ${hits} 处（${perKilo.toFixed(1)}/千字）；逐处做删除测试，只标注情绪、不改变选择、关系、物件或动作结果的删掉，不要换部位或同义动作。`,
    excerpt: compact(samples.join(' | ')),
  }];
}

function findActionListTic(proseLines) {
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed).trim();
    if (!narrative) continue;

    ACTION_LIST_VERB_PATTERN.lastIndex = 0;
    const verbs = [];
    let match;
    while ((match = ACTION_LIST_VERB_PATTERN.exec(narrative)) !== null) {
      verbs.push(match[0]);
    }

    if (verbs.length < ACTION_LIST_MIN_HITS) continue;
    const separators = (narrative.match(/[，、；;]/g) || []).length;
    if (separators < ACTION_LIST_MIN_SEPARATORS) continue;

    findings.push({
      line: lineNo,
      column: 1,
      type: 'action-list-tic',
      severity: 'advisory',
      message: `监控摄像头式动作清单：同段连续动作动词 ${verbs.length} 个、分隔符 ${separators} 个；合并琐碎步骤，只保留有情绪/情节功能的动作，必要时用角色犹豫、误判或环境反馈做缓冲。`,
      excerpt: compact(verbs.slice(0, 8).join(' ')),
    });
  }

  return findings;
}

// 상투어 밀도: 따옴표 밖 서술에 고위험 금지 어휘가 몰리는지 센다. 단어별 치환기가 아니며, 밀도가 높아
// 상투적인 문체가 될 때만 알린다. 요약을 삭제하고 구체적인 행동/물건/대화로 바꿔야 하며, 동의어를 돌려 쓰는 방식은 아니다.
function findClicheDensityTic(proseLines) {
  let hits = 0;
  let narrativeChars = 0;
  let firstLine = null;
  const samples = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    narrativeChars += visibleLength(narrative);

    for (const pattern of CLICHE_PATTERNS) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(narrative)) !== null) {
        hits += 1;
        if (firstLine === null) firstLine = lineNo;
        if (samples.length < 8 && !samples.includes(match[0])) samples.push(match[0]);
      }
    }
  }

  if (narrativeChars === 0 || hits < CLICHE_DENSITY_MIN_HITS) return [];
  const perKilo = (hits / narrativeChars) * 1000;
  if (perKilo < CLICHE_DENSITY_PER_KILO) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'cliche-density-tic',
    severity: 'advisory',
    message: `套词密度过高：高危 AI 套词 ${hits} 处（${perKilo.toFixed(1)}/千字）；不要同义词轮换，改成角色当下可见的动作、物件、对话和具体后果。`,
    excerpt: compact(samples.join(' ')),
  }];
}

// 비유 밀도: 따옴표 밖 서술의 “像/好像/仿佛/如同” 등 비유 표지를 센다.
// 비유 하나는 문제가 아니다. 높은 밀도로 몰릴 때만 알려 글을 또 다른 수사적 틀로 바꾸는 일을 막는다.
function findMetaphorDensityTic(proseLines) {
  let hits = 0;
  let narrativeChars = 0;
  let firstLine = null;
  const samples = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    narrativeChars += visibleLength(narrative);

    METAPHOR_MARKER_PATTERN.lastIndex = 0;
    let match;
    while ((match = METAPHOR_MARKER_PATTERN.exec(narrative)) !== null) {
      hits += 1;
      if (firstLine === null) firstLine = lineNo;
      const sample = sentenceAround(narrative, match.index);
      if (samples.length < 6 && sample && !samples.includes(sample)) samples.push(sample);
    }

    METAPHOR_LIKE_PHRASE_PATTERN.lastIndex = 0;
    while ((match = METAPHOR_LIKE_PHRASE_PATTERN.exec(narrative)) !== null) {
      const prefix = narrative.slice(Math.max(0, match.index - 8), match.index);
      if (/好像|像是|像|仿佛|宛如|如同|犹如/.test(prefix)) continue;
      hits += 1;
      if (firstLine === null) firstLine = lineNo;
      const sample = sentenceAround(narrative, match.index);
      if (samples.length < 6 && sample && !samples.includes(sample)) samples.push(sample);
    }
  }

  if (narrativeChars === 0 || hits < METAPHOR_DENSITY_MIN_HITS) return [];
  const perKilo = (hits / narrativeChars) * 1000;
  if (perKilo < METAPHOR_DENSITY_PER_KILO) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'metaphor-density-tic',
    severity: 'advisory',
    message: `比喻密度过高：像/好像/仿佛/如同等比喻标记 ${hits} 处（${perKilo.toFixed(1)}/千字）；保留最有叙事功能的少数比喻，其余回到具体动作、物件、声音或后果，不要换成新比喻。`,
    excerpt: compact(samples.join(' | ')),
  }];
}

// 설명 연쇄 밀도: 따옴표 밖 서술의 “知道/明白/这意味着/必须需要” 등 판단의 연쇄를 센다.
// 전체 글에서 한 건만 보고한다. 구조적 기능어를 보충하는 대신 판단을 행동, 물건, 대화와 현장의 반응으로 표현해야 한다.
function findReasoningChainTic(proseLines) {
  let hits = 0;
  let coreHits = 0;
  let narrativeChars = 0;
  let firstLine = null;
  const samples = [];
  const buckets = new Set();

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    narrativeChars += visibleLength(narrative);

    for (const { pattern, key, core } of REASONING_CHAIN_PATTERNS) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(narrative)) !== null) {
        hits += 1;
        if (core) coreHits += 1;
        buckets.add(key);
        if (firstLine === null) firstLine = lineNo;
        const sample = compact(match[0]);
        if (samples.length < 8 && !samples.includes(sample)) samples.push(sample);
      }
    }
  }

  if (narrativeChars === 0 || hits < REASONING_CHAIN_MIN_HITS) return [];
  if (coreHits < REASONING_CHAIN_CORE_MIN_HITS || buckets.size < REASONING_CHAIN_MIN_BUCKETS) return [];
  const perKilo = (hits / narrativeChars) * 1000;
  if (perKilo < REASONING_CHAIN_PER_KILO) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'reasoning-chain-tic',
    severity: 'advisory',
    message: `解释链密度过高：知道/明白/这意味着/必须/需要等判断链 ${hits} 处（${perKilo.toFixed(1)}/千字）；像逻辑报告时，把判断落到角色当下可见的动作、物件、对话和现场反馈。`,
    excerpt: compact(samples.join(' | ')),
  }];
}

// 시스템/규칙 행이 계속 API 문서나 정부 공문처럼 보이면 독자는 기계적인 문체를 쉽게 느낀다.
// 규칙을 삭제하는 대신 기능을 유지하면서 일부 딱딱한 말을 일상적인 표현이나 구체적인 결과로 바꾼다.
function findNoticeFormalityTic(proseLines) {
  let hits = 0;
  let noticeChars = 0;
  let noticeLines = 0;
  let coreHits = 0;
  let firstLine = null;
  const samples = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!/^【[^】]+】$/.test(trimmed)) continue;
    noticeLines += 1;
    noticeChars += visibleLength(trimmed);

    NOTICE_FORMAL_CORE_PATTERN.lastIndex = 0;
    while (NOTICE_FORMAL_CORE_PATTERN.exec(trimmed) !== null) coreHits += 1;

    for (const pattern of NOTICE_FORMAL_PATTERNS) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(trimmed)) !== null) {
        hits += 1;
        if (firstLine === null) firstLine = lineNo;
        const sample = compact(match[0]);
        if (samples.length < 8 && !samples.includes(sample)) samples.push(sample);
      }
    }
  }

  if (noticeLines < NOTICE_FORMAL_MIN_LINES || noticeChars === 0 || hits < NOTICE_FORMAL_MIN_HITS || coreHits < NOTICE_FORMAL_CORE_MIN_HITS) return [];
  const perKilo = (hits / noticeChars) * 1000;
  if (perKilo < NOTICE_FORMAL_PER_KILO) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'system-notice-formality-tic',
    severity: 'advisory',
    message: `系统公告公文腔过密：方括号规则行中硬规则词 ${hits} 处（${perKilo.toFixed(1)}/千字）；保留为角色看见的屏幕/公告/规则载体，只在载体内部白话化部分硬词，或补角色当场看懂的具体后果，不改成叙述者解释。`,
    excerpt: compact(samples.join(' | ')),
  }];
}

// 긴 글 전체가 지나치게 “정제”된 경우: 짧은 문단은 많고 자연스러운 연결은 부족해 가공한 줄거리/스토리보드처럼 읽힌다.
// 전체를 읽고 끊긴 곳을 보완해야 하며, 임계값을 맞추려고 전역에 “的/了/就”를 넣어서는 안 된다.
function findOvercompressedProseTic(proseLines) {
  let narrativeChars = 0;
  let narrativeParas = 0;
  let shortParas = 0;
  let particles = 0;
  let firstLine = null;
  const samples = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed) || /^【[^】]+】$/.test(trimmed)) continue;
    const narrative = stripQuoted(trimmed).trim();
    const len = visibleLength(narrative);
    if (len === 0) continue;

    if (firstLine === null) firstLine = lineNo;
    narrativeParas += 1;
    narrativeChars += len;
    if (len <= OVERCOMPRESSED_PROSE_SHORT_MAX_CHARS) {
      shortParas += 1;
      if (samples.length < 6) samples.push(narrative);
    }

    OVERCOMPRESSED_PROSE_PARTICLE_PATTERN.lastIndex = 0;
    while (OVERCOMPRESSED_PROSE_PARTICLE_PATTERN.exec(narrative) !== null) particles += 1;
  }

  if (narrativeChars < OVERCOMPRESSED_PROSE_MIN_CHARS || narrativeParas < OVERCOMPRESSED_PROSE_MIN_PARAS) return [];
  const shortRatio = shortParas / narrativeParas;
  if (shortRatio < OVERCOMPRESSED_PROSE_SHORT_RATIO) return [];
  const particlePerKilo = (particles / narrativeChars) * 1000;
  if (particlePerKilo >= OVERCOMPRESSED_PROSE_PARTICLE_PER_KILO) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'overcompressed-prose-tic',
    severity: 'advisory',
    message: `过度精炼短段：叙述段 ${narrativeParas} 个，其中 ${shortParas} 个≤${OVERCOMPRESSED_PROSE_SHORT_MAX_CHARS}字（${(shortRatio * 100).toFixed(0)}%），自然连接 ${particlePerKilo.toFixed(1)}/千字偏少；先通读判断，确有提纲感再补断裂处和必要结构虚词，有意短镜头可留，别机械注水。`,
    excerpt: compact(samples.join(' | ')),
  }];

}

// 낮은 연결 밀도: 긴 글이나 중단기 구간의 따옴표 밖 서술에서 기능어와 일상적 연결이 모두 적고 중장문 연결도 부족하면,
// “개요/전보체” 분포가 나타난다. 필요한 연결과 문장 묶음을 복원해야 하며, 전역에 단어를 보충하는 방식은 아니다.
function findLowConnectiveDensityTic(proseLines) {
  let bodyChars = 0;
  let functionHits = 0;
  let plainHits = 0;
  let firstLine = null;
  const sentences = [];
  const samples = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;

    // 따옴표 밖 서술만 본다. 대사/실시간 댓글/시스템 안내는 본래 짧을 수 있으며, 함께 집계하면 장르 특성을 전보체로 오인하게 된다.
    const narrative = stripQuoted(trimmed).trim();
    const narrativeLen = visibleLength(narrative);
    if (narrativeLen === 0) continue;

    if (firstLine === null) firstLine = lineNo;
    bodyChars += narrativeLen;
    functionHits += countTerms(narrative, LOW_CONNECTIVE_FUNCTION_TERMS);
    plainHits += countTerms(narrative, LOW_CONNECTIVE_PLAIN_TERMS);

    for (const sentence of splitSentences(narrative)) {
      const len = visibleLength(sentence);
      if (len === 0) continue;
      sentences.push(len);
      if (len <= 12 && samples.length < 6) samples.push(sentence);
    }
  }

  if (bodyChars < LOW_CONNECTIVE_MIN_CHARS || sentences.length === 0) return [];
  const functionPerKilo = (functionHits / bodyChars) * 1000;
  if (functionPerKilo >= LOW_CONNECTIVE_FUNCTION_PER_KILO) return [];
  const plainPerKilo = (plainHits / bodyChars) * 1000;
  if (plainPerKilo >= LOW_CONNECTIVE_PLAIN_PER_KILO) return [];
  const longSentenceRatio = sentences.filter((len) => len >= LOW_CONNECTIVE_LONG_SENTENCE_CHARS).length / sentences.length;
  if (longSentenceRatio >= LOW_CONNECTIVE_LONG_SENTENCE_RATIO) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'low-connective-density-tic',
    severity: 'advisory',
    message: `低连接密度：引号外叙述功能词 ${functionPerKilo.toFixed(1)}/千字、白话连接 ${plainPerKilo.toFixed(1)}/千字，且≥${LOW_CONNECTIVE_LONG_SENTENCE_CHARS}字承接句仅 ${(longSentenceRatio * 100).toFixed(0)}%；容易像提纲/电报体。通读后补必要连接和中长句群，别机械注水。`,
    excerpt: compact(samples.join(' | ')),
  }];
}

// 추상적 요약 반복: 따옴표 밖 서술에서 추상도가 높은 마무리 문형을 센다. 전체 글에서 한 건만 보고하며, 인물이
// 현재 볼 수 있는 문서, 행동, 대화 또는 물리적 결과로 돌아가도록 알린다. 운명 같은 거창한 말로 독자 대신 요약하지 않는다.
function findAbstractSummaryTic(proseLines) {
  let hits = 0;
  let narrativeChars = 0;
  let firstLine = null;
  const samples = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    narrativeChars += visibleLength(narrative);

    for (const pattern of ABSTRACT_SUMMARY_PATTERNS) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(narrative)) !== null) {
        hits += 1;
        if (firstLine === null) firstLine = lineNo;
        const sample = compact(match[0]);
        if (samples.length < 6 && !samples.includes(sample)) samples.push(sample);
      }
    }
  }

  if (narrativeChars === 0 || hits < ABSTRACT_SUMMARY_MIN_HITS) return [];
  const perKilo = (hits / narrativeChars) * 1000;
  if (perKilo < ABSTRACT_SUMMARY_PER_KILO) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'abstract-summary-tic',
    severity: 'advisory',
    message: `抽象总结复读：命运/棋局/这一刻终于明白/才刚刚开始等作者总结 ${hits} 处（${perKilo.toFixed(1)}/千字）；回到角色当下可见的文件、动作、对话或物理后果，别替读者盖章。`,
    excerpt: compact(samples.join(' | ')),
  }];
}

function findPeriodStutter(proseLines) {
  const findings = [];
  let runLen = 0;
  let runStartLine = null;
  let runSample = [];

  const flush = () => {
    if (runLen >= STUTTER_MIN_RUN) {
      findings.push({
        line: runStartLine,
        column: 1,
        type: 'period-stutter',
        severity: 'advisory',
        message: `碎句号：连续 ${runLen} 个短句无呼吸；按目标句长把碎句合并成中长句、补回画面与连接（见本 skill 句长/疏密节奏规则）。`,
        excerpt: compact(runSample.join(' ')),
      });
    }
    runLen = 0;
    runStartLine = null;
    runSample = [];
  };

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed) continue; // 빈 행은 한 문장씩 문단을 나누는 편집 형식이며 서술의 연속성을 끊지 않는다.
    if (isDivider(trimmed) || isStructural(trimmed)) {
      flush(); // 구분선/Markdown 구조 행: 짧은 문장 카운트를 초기화한다.
      continue;
    }
    const narrative = stripQuoted(trimmed);
    if (visibleLength(narrative) === 0) {
      flush(); // 순수 대화/실시간 댓글/시스템 안내: 연속된 짧은 문장이 정상적이므로 짧은 문장 카운트를 초기화한다.
      continue;
    }
    // 따옴표 밖 서술문만 센다. 혼합 행(서술+따옴표 안의 물건/짧은 대사)도 따옴표 밖 부분은 짧은 문장 집계에 포함한다.
    for (const sentence of splitSentences(narrative)) {
      if (visibleLength(sentence) <= STUTTER_MAX_SENTENCE) {
        if (runLen === 0) runStartLine = lineNo;
        runLen += 1;
        if (runSample.length < 6) runSample.push(sentence);
      } else {
        flush();
      }
    }
  }
  flush();
  return findings;
}

function isDivider(trimmed) {
  return /^-{3,}$/.test(trimmed) || /^[*_]{3,}$/.test(trimmed);
}

// Markdown 구조 행(제목/목록/인용/표)은 서술 본문이 아니므로 긴 문단/지나친 마침표 분할/줄표 검사에서 모두 건너뛴다.
function isStructural(trimmed) {
  return /^(#{1,6}\s|>\s?|[-*+]\s|\d+[.)]\s|\|)/.test(trimmed)
    || /^第[零一二三四五六七八九十百千万\d]+章(?:\s|_|$)/.test(trimmed);
}

// 따옴표 쌍 안의 조각(대사/시스템 안내)을 제거하고 밖의 서술만 남긴다. 짧은 문장 판정용: 순수 대화/실시간 댓글의 연속된 짧은 문장은
// 장르상 정상적이므로 제외하지만 “서술+따옴표 안의 물건/짧은 대사” 혼합 행은 따옴표 밖 서술을 짧은 문장 집계에 포함한다.
function stripQuoted(text) {
  let out = text;
  for (const src of QUOTE_SOURCES) out = out.replace(new RegExp(src, 'g'), '');
  return out;
}

// 따옴표 쌍으로 둘러싼 조각(따옴표 포함)을 같은 길이의 물음표로 바꾼다. 따옴표 안 대사/안내를 제외하면서 원문의
// 오프셋을 보존해 개별 blocking 규칙이 위치와 원문 발췌를 구할 수 있게 한다(stripQuoted는 위치를 이동시켜 부적합하다).
// 자리표시자는 “。” 대신 “？”를 쓴다. 각 규칙의 [^。！？!?…] 부정 문자 클래스를 끊어야 하며(？와 마침표는 각
// 규칙의 부정 문자 클래스에서 같은 역할), 어떤 규칙에도 일치하는 문자로 들어가면 안 된다. 마침표를 쓰면 trailer-summary의 문장 끝
// [。！] 종료 문자가 가짜로 생겨 “这一战注定是「血屠」的开端，…”처럼 따옴표 안에 암호명/별명을 넣은 서술 행을
// 오탐한다. 보고된 “这一战注定是。”는 원문에서 grep으로 찾을 수도 없다. 자리표시자 길이가 같으므로 오프셋과 발췌 구간은 이동하지 않는다.
function maskQuoted(text) {
  let out = text;
  for (const src of QUOTE_SOURCES) {
    out = out.replace(new RegExp(src, 'g'), (m) => '？'.repeat(m.length));
  }
  return out;
}

// 따옴표 안 조각(따옴표 자체 포함)의 [start, end) 구간을 반환해 not-is 대비 문장에서 대사를 제외하는 데 쓴다.
function quotedRanges(text) {
  const ranges = [];
  for (const src of QUOTE_SOURCES) {
    const re = new RegExp(src, 'g');
    let match;
    while ((match = re.exec(text)) !== null) ranges.push([match.index, match.index + match[0].length]);
  }
  return ranges;
}

function insideRanges(pos, ranges) {
  return ranges.some(([start, end]) => pos >= start && pos < end);
}

function splitSentences(trimmed) {
  return trimmed
    .split(/[。！？!?]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function sentenceAround(text, index) {
  let start = index;
  while (start > 0 && !STOP_CHARS.has(text[start - 1])) start -= 1;
  let end = index;
  while (end < text.length && !STOP_CHARS.has(text[end])) end += 1;
  return compact(text.slice(start, end).trim());
}

function visibleLength(sentence) {
  const matched = sentence.match(/[一-鿿Ａ-ｚA-Za-z0-9]/g);
  return matched ? matched.length : 0;
}

function countTerms(text, terms) {
  let count = 0;
  for (const term of terms) {
    let index = text.indexOf(term);
    while (index !== -1) {
      count += 1;
      index = text.indexOf(term, index + term.length);
    }
  }
  return count;
}

// 행 안의 HTML 주석(`<!--`, `-->` 포함)을 같은 길이의 공백으로 바꾼다. openBefore는 이전 행에서 닫히지 않은 주석이 남았음을 나타낸다.
// unclosedOpenings의 `<!--`는 글 끝까지 닫히지 않는다. 네 글자만 지우고 뒤는 그대로 본문으로 취급한다.
// openedAt은 이 행에서 마지막으로 주석을 연 `<!--`의 위치("행:열")이며, 없으면 null이다.
function maskHtmlComments(line, openBefore, lineIndex = 0, unclosedOpenings = new Set()) {
  let out = '';
  let open = openBefore;
  let cursor = 0;
  let openedAt = null;
  while (cursor < line.length) {
    if (open) {
      const close = line.indexOf('-->', cursor);
      const end = close === -1 ? line.length : close + 3;
      out += ' '.repeat(end - cursor);
      cursor = end;
      if (close !== -1) open = false;
      continue;
    }
    const start = line.indexOf('<!--', cursor);
    if (start === -1) {
      out += line.slice(cursor);
      break;
    }
    out += line.slice(cursor, start) + '    ';
    cursor = start + 4;
    const key = `${lineIndex}:${start}`;
    if (unclosedOpenings.has(key)) continue;
    open = true;
    openedAt = key;
  }
  return { text: out, open, openedAt };
}

function parseFenceMarker(trimmedLine) {
  const match = /^(?:`{3,}|~{3,})/.exec(trimmedLine);
  if (!match) return null;
  return { char: match[0][0], length: match[0].length };
}

function hasYamlFrontMatter(lines) {
  if (!lines[0] || lines[0].trim() !== '---') return false;
  let sawYamlField = false;
  for (let i = 1; i < Math.min(lines.length, 40); i += 1) {
    const trimmed = lines[i].trim();
    if (trimmed === '---') return sawYamlField;
    if (/^[A-Za-z0-9_-]+:\s*/.test(trimmed)) sawYamlField = true;
  }
  return false;
}

function scanBlock(block) {
  const text = block.map((entry) => entry.text).join('\n');
  const lineStarts = [];
  let cursor = 0;

  for (const entry of block) {
    lineStarts.push({ offset: cursor, lineNo: entry.lineNo });
    cursor += entry.text.length + 1;
  }

  return findNotIsComparisons(text, (offset) => positionForOffset(lineStarts, offset));
}

function positionForOffset(lineStarts, offset) {
  let low = 0;
  let high = lineStarts.length - 1;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const current = lineStarts[mid];
    const next = lineStarts[mid + 1];

    if (offset < current.offset) {
      high = mid - 1;
    } else if (next && offset >= next.offset) {
      low = mid + 1;
    } else {
      return {
        line: current.lineNo,
        column: offset - current.offset + 1,
      };
    }
  }

  return { line: lineStarts[0].lineNo, column: 1 };
}

function findNotIsComparisons(text, getPosition) {
  const findings = [];
  const quoted = quotedRanges(text);
  let offset = 0;

  while (offset < text.length) {
    const start = text.indexOf('不是', offset);
    if (start === -1) break;

    // 따옴표 안은 대사/시스템 안내다. 구어의 “不是A，是B”는 자연스러운 해명/반문이므로 서술 층위의 AI 대비 문형으로 세지 않는다.
    // (지나친 마침표 분할 검사와 마찬가지로 따옴표 내용을 제외한다.)
    if (insideRanges(start, quoted)) {
      offset = start + 2;
      continue;
    }

    // 흔한 예/아니요 의문문 조각 “是不是”를 피한다.
    if (start > 0 && text[start - 1] === '是') {
      offset = start + 2;
      continue;
    }

    const candidate = text.slice(start);
    const markerEnd = findPositiveFlipEnd(candidate);

    if (markerEnd === -1) {
      offset = start + 2;
      continue;
    }

    const raw = trimTrailingNoise(extractFinding(candidate, markerEnd));
    if (raw.length >= 4) {
      const position = getPosition(start);
      findings.push({
        line: position.line,
        column: position.column,
        type: 'not-is-comparison',
        severity: 'blocking',
        message: '高频 AI 对比句式；删掉否定铺垫，直接写后项，或改成动作/细节呈现。',
        excerpt: compact(raw),
      });
    }

    offset = start + Math.max(raw.length, 2);
  }

  return findings;
}

function findPositiveFlipEnd(candidate) {
  let index = 2; // “不是” 다음
  let scanned = 0;
  let crossedSeparator = false;

  while (index < candidate.length && scanned <= MAX_NEGATIVE_SPAN) {
    const char = candidate[index];

    if (startsWithAt(candidate, index, '而是')) return index + 2;

    if (SOFT_SEPARATORS.has(char)) {
      const next = skipGap(candidate, index + 1);
      if (startsWithAt(candidate, next, '而是')) return next + 2;
      if (candidate[next] === '是' && !TAG_PARTICLES.has(candidate[next + 1]) && !isAffirmationTagAt(candidate, next)) return next + 1;
      crossedSeparator = true;
    }

    if (HARD_SEPARATORS.has(char)) {
      const next = skipGap(candidate, index + 1);
      if (candidate[next] === '是' && !TAG_PARTICLES.has(candidate[next + 1]) && !isAffirmationTagAt(candidate, next)) return next + 1;
      if (char !== '.') break;
      crossedSeparator = true;
    }

    if (STOP_CHARS.has(char)) break;

    // “不是A是B”처럼 붙어 있는 형태도 잡지만 첫 절 안으로 한정한다.
    // 즉, 어떤 구분자도 나오기 전이어야 한다. 구분자 뒤의 접속사 끝에 붙은 “是”는
    // (只是/可是/但是/还是/于是/倒是/总是…) 해당 단어의 일부이며 긍정 항목이 아니다.
    // 계사로 오인한다(issue #166의 오탐 유형). 구분자 뒤 전환은 여전히
    // 구분자에 붙은 ‘，是’/‘，而是’를 위의 구분자 분기로 포착한다.
    // ‘，他是’/‘，那是’처럼 주어가 있는 전환은 여기서 의도적으로 잡지 않는다.
    // 단어 목록 없이는 구분자 주변만 보고 이를 접속사와 구별할 수 없으며,
    // 재검사 0건을 요구하는 필수 관문에서는 오탐으로 좋은 문장을 고치게 하는 비용이
    // 이 드문 형태를 놓치는 비용보다 더 크기 때문이다.
    // 양자택일 관용구 ‘不是A就是B / 也是B’의 ‘是’는
    // 就是/也是 접속사 일부이지 계사가 아니므로 就/也도 제외한다. 또한
    // ‘不是A，也不是B’의 두 번째 부정절 안 ‘是’를 전환으로 취급하지 않는다.
    if (char === '是' && !COMPACT_EITHER_OR_PREV.has(candidate[index - 1]) && !crossedSeparator) {
      return index + 1;
    }

    index += 1;
    scanned += 1;
  }

  return -1;
}

function extractFinding(candidate, markerEnd) {
  let end = markerEnd;
  const limit = Math.min(candidate.length, markerEnd + MAX_POSITIVE_SPAN);

  while (end < limit) {
    if (STOP_CHARS.has(candidate[end])) break;
    end += 1;
  }

  return candidate.slice(0, end);
}

function startsWithAt(text, index, needle) {
  return text.slice(index, index + needle.length) === needle;
}

function isAffirmationTagAt(text, index) {
  if (text[index] !== '是') return false;
  const particle = text[index + 1];
  if (!AFFIRMATION_TAG_PARTICLES.has(particle)) return false;
  const boundary = text[index + 2] || '';
  return AFFIRMATION_TAG_BOUNDARY.has(boundary);
}

// 행 내부 공백과 줄바꿈(빈 행·문단 간격 포함)을 건너뛰고 다음 의미 있는 문자에서 멈춘다. 기존 구현은 줄바꿈 하나만 건너뛰어
// ‘不是A。(빈 행)是B’처럼 빈 행을 가로지르는 분할 공개 문장을 놓쳤다.
function skipGap(text, index) {
  while (index < text.length && (isInlineSpace(text[index]) || text[index] === '\n')) index += 1;
  return index;
}

function isInlineSpace(char) {
  return char === ' ' || char === '\t' || char === '\r';
}

function trimTrailingNoise(text) {
  return text.replace(/[\s|）)】\]]+$/u, '');
}

function compact(text) {
  const normalized = text.replace(/\s+/g, ' ').trim();
  return normalized.length > 80 ? `${normalized.slice(0, 77)}...` : normalized;
}
