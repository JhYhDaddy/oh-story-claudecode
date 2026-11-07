#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const USAGE = `Usage: node check-degeneration.js [--check] [--json] [--fail-on=blocking|all] <file...>

Detect model-degeneration fingerprints that a degrading model cannot self-report:
  - verbatim repetition (复读/打转): a long sentence repeated, or back-to-back identical lines
  - mid-sentence truncation (截断): file ends without terminal/closing punctuation
  - placeholder / refusal / meta leakage (元信息泄漏): 作为AI / 我无法继续 / 此处省略 / 乱码
  - engineering-word leakage (工程词泄漏): 细纲 / 情节点 / 本章 / 下一章 / 任务描述 漏进正文

Each finding carries severity: blocking (复读/截断/占位拒绝语/tier1 纯工程词，正文里永不合法，
命中即重写) 或 advisory (tier2 장별분석/歧义词、对话行里的工程词，只提示、交人/LLM 判)。
--fail-on=blocking 只在出现 blocking finding 时退出 1；默认 --fail-on=all 有任何 finding 即退出 1。

Report-only. The script never rewrites — the safe response is to regenerate the
affected unit (chapter / 摘要) with the finding fed back as a constraint, cap retries,
then surface the evidence to the user. Conservative by design: 通俗网文 deliberately
uses 排比/复沓/弹幕刷屏/重复台词 for rhythm, so short and dialogue repetition is exempt.`;

// 반복: 가시 글자 수가 REPEAT_MIN_LEN 이상인 긴 문장이 REPEAT_MIN_COUNT회 이상 나오면 제자리 반복으로 판정한다.
// 인접한 행 전체의 반복(가시 글자 수 ≥ ADJACENT_MIN_LEN)은 즉시 반복이다. 짧은 문장·댓글·대화의 연속은 면제한다.
const REPEAT_MIN_LEN = 12;
const REPEAT_MIN_COUNT = 3;
const ADJACENT_MIN_LEN = 8;

// hard는 모든 행에 적용한다(본문에서 항상 부적절). soft는 대화가 아닌 서술 행에만 적용한다. 인물 대사에서는
// ‘对不起，我无法答应你’가 모델 거절문이 아닌 정상 대화일 수 있다.
const PLACEHOLDER_PATTERNS = [
  // ‘作为AI’는 뒤에 문장 구분·我·无法…가 오거나 문말인 자기 지칭 위치여야 한다. ‘人工智能时代的产物’ 같은
  // 복합 명사의 오탐을 피하며 대화는 면제한다. 시스템물·AI 동반자물의 ‘作为AI，我会保护你’는 정상 대사다.
  // 모델 종류 접미사(AI语言模型/AI助手/人工智能语言模型/AI模型/AI大模型)는 선택적으로 소비해야 한다. 아니면 전방 탐색이
  // AI 바로 뒤의 ‘语’/‘助’/‘模’를 보아 가장 전형적인 퇴화 도입 전체를 놓친다. 작성 후 검사 story_hook_core.js의
  // SOFT_PATTERNS / story_codex_hook.py의 _NET_SOFT_PATTERNS와 의미가 같다.
  { re: /作为(一个)?(AI|人工智能|大?语言模型|智能助手|聊天助手)(?:语言模型|大?模型|助手|机器人)?(?=[，,。、；;：:！!？?\s）)」』"】]|我|无法|不能|没法|$)/, label: '元信息泄漏（AI 自指）', hard: false },
  { re: /�/, label: '乱码（替换字符 �）', hard: true },
  { re: /^(Sure|Certainly|Here'?s|As an AI|I (?:cannot|can't|am unable|apologize))/, label: '元信息泄漏（英文 AI 腔）', hard: true },
  { re: /[（(](此处|以下|这里|下文|后续)?\s*(省略|略)(去|过)?[^）)]{0,10}[）)]/, label: '占位符（括号省略）', hard: true },
  { re: /(未完待续|TODO|占位符|placeholder)/, label: '占位符', hard: true },
  { re: /我(无法|不能)(继续(写|创作|生成|下去)|生成(内容|文本|正文)?|创作|续写|完成(这个|本)?(章|篇|创作|请求))/, label: '元信息泄漏（生成拒绝语）', hard: false },
];

const QUOTED_SPAN_PATTERNS = [
  /「[^」]*」/g,
  /『[^』]*』/g,
  /【[^】]*】/g,
  /“[^”]*”/g,
  // 작은따옴표는 짝이 맞아야 한다. don't, O’Connor의 단어 내부 아포스트로피는 여닫는 따옴표가 아니다.
  /(?<![A-Za-z0-9_])‘(?:[^’]|(?<=[A-Za-z0-9_])’(?=[A-Za-z0-9_]))*(?!(?<=[A-Za-z0-9_])’[A-Za-z0-9_])’/g,
  /"[^"]*"/g,
  /(?<![A-Za-z0-9_])'(?:[^']|(?<=[A-Za-z0-9_])'(?=[A-Za-z0-9_]))*(?!(?<=[A-Za-z0-9_])'[A-Za-z0-9_])'/g,
];

// 작업 용어 유출(본문 메타정보 검사의 결정적 버전): 약한 모델이 집필 작업 용어를 본문에 흘려 몰입을 깨뜨린다.
// DeepSeek-v4 같은 모델은 대사에 ‘该到下一章了’를 넣기도 한다. 모델이 스스로 찾지 못하므로 스크립트로 보완한다.
// tier1은 순수 집필 절차 용어로 본문에서 거의 항상 부적절하다. tier2는 장 구조·다의어이며 인물이 이야기 안에서
// 실제로 ‘第X章’을 읽거나 논의하는 경우, 이야기 속 시스템·인터페이스 용어는 예외다(report-only로 사람/LLM이 판정).
const META_TIER1_RE = /细纲|情节点|卷纲|功能标签|目标情绪|字数目标|章首钩子|章尾钩子/;
const META_TIER2_RE = /第[一二三四五六七八九十百千万两0-9]+章|本章|这一章|上一章|下一章|上章|下章|前一章|后一章|前文|后文|伏笔|读者|任务描述/;

const options = { json: false, files: [], failOn: 'all' };

for (let i = 2; i < process.argv.length; i += 1) {
  const arg = process.argv[i];
  if (arg === '--check') {
    // 다른 검사기와의 대칭성을 위해 허용하지만 탐지는 항상 검사 전용이다.
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
  const findings = scanDocument(input).map((finding) => ({ file, ...finding }));
  allFindings.push(...findings);
}

if (options.json) {
  process.stdout.write(`${JSON.stringify({ findings: allFindings }, null, 2)}\n`);
} else {
  for (const f of allFindings) {
    console.log(`${f.file}:${f.line}:${f.column}: [${f.severity}] ${f.type}: ${f.message} (${f.excerpt})`);
  }
}

if (failed) process.exit(2);
// --fail-on=blocking은 blocking finding이 있을 때만 종료 코드 1을 반환한다(advisory는 보고만 함). 기본값 all은 기존처럼 finding이 하나라도 있으면 1을 반환한다.
const hasBlocking = allFindings.some((f) => f.severity === 'blocking');
if (options.failOn === 'blocking' ? hasBlocking : allFindings.length > 0) process.exit(1);

function die(message) {
  console.error(message);
  console.error(USAGE.trimEnd());
  process.exit(2);
}

function scanDocument(input) {
  const lines = input.split(/\r?\n/);
  const content = []; // 프런트매터·코드 블록 밖 본문 행의 { text, trimmed, lineNo }.
  let fence = null;
  let inFrontMatter = hasYamlFrontMatter(lines);

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    if (inFrontMatter) {
      if (index > 0 && trimmed === '---') inFrontMatter = false;
      continue;
    }
    const fenceMarker = /^(?:`{3,}|~{3,})/.exec(trimmed);
    if (fence) {
      if (fenceMarker && trimmed[0] === fence) fence = null;
      continue;
    }
    if (fenceMarker) {
      fence = trimmed[0];
      continue;
    }
    content.push({ text: line, trimmed, lineNo: index + 1 });
  }

  const findings = [];
  findings.push(...findRepetition(content));
  findings.push(...findTruncation(content));
  findings.push(...findPlaceholders(content));
  findings.push(...findMetaLeak(content));
  findings.sort((a, b) => a.line - b.line || a.column - b.column);
  return findings;
}

function isContent(trimmed) {
  return trimmed && !trimmed.startsWith('#') && !/^-{3,}$/.test(trimmed);
}

// 열 번호를 유지하도록 짝지은 따옴표 내용을 같은 길이로 가린다. 닫히지 않은 따옴표는 면제하지 않는다.
function maskQuotedSpans(text) {
  let masked = text;
  for (const pattern of QUOTED_SPAN_PATTERNS) {
    masked = masked.replace(pattern, (match) => ' '.repeat(match.length));
  }
  return masked;
}

// 짝지은 따옴표 구간(대사·시스템 용어·인용 물건)을 제거해 바깥 서술만 남긴다. 반복 대사는 장르 기법이므로 면제하지만
// 서술과 따옴표 속 물건·짧은 대사가 섞인 행에서는 바깥 서술의 반복도 퇴화이므로 행 전체를 면제하면 안 된다.
function stripQuoted(text) {
  let stripped = text;
  for (const pattern of QUOTED_SPAN_PATTERNS) {
    stripped = stripped.replace(pattern, '');
  }
  return stripped;
}

function visibleLength(text) {
  const m = text.match(/[一-鿿Ａ-ｚA-Za-z0-9]/g);
  return m ? m.length : 0;
}

function findRepetition(content) {
  const findings = [];
  const body = content.filter((c) => isContent(c.trimmed));

  // (1) 바로 이어지는 동일 행(즉시 반복). 바깥 서술이 짧은 순수 대사·실시간 댓글 반복은 면제한다.
  // 서술과 따옴표 속 물건이 섞인 행은 따옴표 제거 후 서술이 충분히 길면 행 전체 반복을 여전히 판정한다.
  for (let i = 1; i < body.length; i += 1) {
    if (
      body[i].trimmed === body[i - 1].trimmed &&
      visibleLength(stripQuoted(body[i].trimmed)) >= ADJACENT_MIN_LEN
    ) {
      findings.push({
        line: body[i].lineNo,
        column: 1,
        type: 'verbatim-repeat',
        severity: 'blocking',
        message: '逐行复读（紧邻整行重复）：疑似模型打转，重写本段、删掉重复。',
        excerpt: compact(body[i].trimmed),
      });
    }
  }

  // (2) 파일 전체에서 긴 문장이 REPEAT_MIN_COUNT회 이상 반복되는 경우.
  // 장르 기법인 따옴표 내부 대사만 면제한다. 바깥 서술은 혼합 행을 포함해 반복 횟수에 반영한다.
  const counts = new Map();
  for (const { trimmed } of body) {
    for (const sentence of stripQuoted(trimmed).split(/[。！？!?]/)) {
      const s = sentence.trim();
      if (visibleLength(s) < REPEAT_MIN_LEN) continue;
      const entry = counts.get(s) || { count: 0, firstLine: null };
      entry.count += 1;
      counts.set(s, entry);
    }
  }
  // 반복 문장의 첫 행을 기록한다.
  const flagged = new Set();
  for (const [s, entry] of counts) {
    if (entry.count >= REPEAT_MIN_COUNT) flagged.add(s);
  }
  if (flagged.size) {
    for (const { trimmed, lineNo } of body) {
      for (const sentence of stripQuoted(trimmed).split(/[。！？!?]/)) {
        const s = sentence.trim();
        if (flagged.has(s)) {
          findings.push({
            line: lineNo,
            column: 1,
            type: 'verbatim-repeat',
            severity: 'blocking',
            message: `长句复读（同句出现 ${counts.get(s).count} 次）：疑似模型打转，重写、保留一处。`,
            excerpt: compact(s),
          });
          flagged.delete(s); // 각 반복 문장은 처음 나온 위치에서 한 번만 보고한다.
        }
      }
    }
  }

  return findings;
}

function findTruncation(content) {
  const body = content.filter((c) => isContent(c.trimmed));
  if (body.length === 0) return [];
  const last = body[body.length - 1];
  // 완성된 장은 종결·닫는 문장부호로 끝나며 그렇지 않으면 잘린 것으로 본다.
  if (/[。！？!?…”"』」）)】]$/.test(last.trimmed)) return [];
  return [{
    line: last.lineNo,
    column: last.trimmed.length,
    type: 'truncated',
    severity: 'blocking',
    message: '疑似截断：正文末尾未以句末/收尾标点结束，可能被模型中途切断；补完结尾或重写收尾。',
    excerpt: compact(last.trimmed.slice(-24)),
  }];
}

function findPlaceholders(content) {
  const findings = [];
  for (const { trimmed, lineNo } of content) {
    if (!isContent(trimmed)) continue;
    const outsideQuotes = maskQuotedSpans(trimmed);
    for (const { re, label, hard } of PLACEHOLDER_PATTERNS) {
      // hard 신호는 행 전체를 검사한다. soft 자기 지칭·거절문은 짝지은 따옴표 밖만 검사하고 같은 길이로 가려 열 번호를 유지한다.
      const m = re.exec(hard ? trimmed : outsideQuotes);
      if (m) {
        const index = m.index || 0;
        findings.push({
          line: lineNo,
          column: index + 1,
          type: 'placeholder-leak',
          severity: 'blocking',
          message: `${label}：正文混入元信息/拒绝语/占位符，重写本段干净落地。`,
          excerpt: compact(trimmed.slice(Math.max(0, index - 4), index + 20)),
        });
        break; // 행당 발견 사항 하나면 충분하다.
      }
    }
  }
  return findings;
}

function findMetaLeak(content) {
  const findings = [];
  let firstContentSeen = false;
  for (const { trimmed, lineNo } of content) {
    if (!isContent(trimmed)) continue;
    if (!firstContentSeen) {
      firstContentSeen = true;
      // 제목 행(第N章 章名, ## 접두사가 없어도 해당)은 제목 이외 본문이 아니므로 제외한다.
      if (/^第[一二三四五六七八九十百千万两0-9]+章/.test(trimmed)) continue;
    }
    const outsideQuotes = maskQuotedSpans(trimmed);
    let m = META_TIER1_RE.exec(outsideQuotes);
    let quotedTier1 = false;
    if (!m) {
      m = META_TIER1_RE.exec(trimmed);
      quotedTier1 = Boolean(m);
    }
    if (m) {
      // tier1 순수 작업 용어는 본문에서 거의 항상 부적절하므로 blocking이다. 다만 작가·시나리오 작가물에서 인물이 실제 창작을 논하며
      // 적중 위치가 짝지은 따옴표 안이면 정상일 수 있어 advisory로 낮춘다. 같은 행 다른 위치의 따옴표는 영향을 주지 않는다.
      findings.push({
        line: lineNo,
        column: m.index + 1,
        type: 'meta-leak',
        severity: quotedTier1 ? 'advisory' : 'blocking',
        message: `工程词泄漏：「${m[0]}」是写作流水线术语，正文里不该出现；改成角色/场景内表达。${quotedTier1 ? '例外：角色为作者/编剧、在故事内真实讨论创作时，台词里可能合法。' : ''}`,
        excerpt: compact(trimmed.slice(Math.max(0, m.index - 6), m.index + 18)),
      });
      continue; // tier1이 적중하면 충분하며 tier2를 중복 적용하지 않는다.
    }
    m = META_TIER2_RE.exec(trimmed);
    if (m) {
      findings.push({
        line: lineNo,
        column: m.index + 1,
        type: 'meta-leak',
        severity: 'advisory',
        message: `元信息泄漏：「${m[0]}」疑似工程/章节结构词混入正文；改成角色当下可感知的事件锚点或相对时间。例外：角色在故事内真实阅读/讨论「第X章」、真身为作者/读者、或故事内系统/界面用语。`,
        excerpt: compact(trimmed.slice(Math.max(0, m.index - 6), m.index + 18)),
      });
    }
  }
  return findings;
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

function compact(text) {
  const normalized = text.replace(/\s+/g, ' ').trim();
  return normalized.length > 80 ? `${normalized.slice(0, 77)}...` : normalized;
}
