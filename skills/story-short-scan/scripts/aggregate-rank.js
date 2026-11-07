#!/usr/bin/env node
/**
 * aggregate-rank.js — 순위 Markdown을 짧은 표로 집계해 주 세션이 이 표만 읽게 한다.
 * 입력은 플랫폼 수집 스크립트가 만든 순위 파일 또는 같은 형식의 수동 정리 파일이다.
 * 첫 행 `# {平台} · {榜单名}`, 항목 `### #{排名} {书名}`(치디안은 `## #`),
 * 다음 행 `*作者 · 题材 · ... *`. 선택적으로 `## {题材/频道} — N 本` 그룹,
 * `**标签：** a、b`, `**字数：X**`, `**总推荐：X**`, `**简介**` 절 또는 `> 简介`를 쓴다.
 * 사용법:
 *   node aggregate-rank.js <순위파일또는디렉터리>... [--out 순위조사집계.md] [--top 3]
 *        [--desc 30] [--sparse 15] [--scale long|short] [--json]
 *   node aggregate-rank.js <순위파일또는디렉터리>... --sample <장르/태그/제목단어> [--n 5]
 * 플랫폼별 장르의 권수·비중·인기도 중앙값·글자 수 중앙값·빈번한 태그·표본 충분성을 제공한다.
 * 전역으로 태그 인기어·글자 수 분포·흔한 제목 단어·여러 순위 중복·장르 대표작을 제공한다.
 * 같은 플랫폼의 제목+작가가 같으면 한 작품으로 한 번만 센다. 기본 표본 기준은 15권, 순위당 10위만 있는 츠웨이마오는 10권이다.
 * --sparse를 주면 모든 플랫폼에 적용한다. 항목이 모두 같은 동일 플랫폼 순위(예: 같은 페이지인 치디안 모바일의 두 계약 순위)는
 * 하나로 계산해 중복을 부풀리지 않는다. 인기도 숫자가 전혀 없는 순위(예: 페이지순 라이브러리)는 순서만 계산하고 인기도 기준 선택에는 참여하지 않는다.
 * 머리에 ‘每题材上限’이 있는 순위(판체의 장르별 상위 N권)는 권수가 표본 상한임을 출력한다. 입력은 읽기 전용이며 --out 외에는 파일을 쓰지 않는다.
 */

"use strict";

const fs = require("fs");
const path = require("path");

const OWN_OUTPUT_PREFIXES = ["순위조사집계", "소재선정", "단편순위조사결론", "扫榜聚合", "选题决策", "短篇扫榜结论"];
const SHORT_PLATFORMS = new Set(["点众", "黑岩", "知乎盐言", "盐言", "番茄短篇", "七猫短篇"]);
const METRIC_PRIORITY = ["在读", "热度", "收藏", "赞同", "点赞", "阅读", "月票", "总推荐", "榜单值", "营养液", "积分", "评分"];
// 항목이 적은 소규모 플랫폼의 표본 기준은 여기의 권수, 나머지는 DEFAULT_SPARSE가 기본이다.
const SMALL_PLATFORM_SPARSE = { "刺猬猫": 10 };
const DEFAULT_SPARSE = 15;
const UNRESOLVED_TITLES = new Set(["（标题待解析）", "（书名待解析）", ""]);

// ---------------------------------------------------------------------------
// 인자
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const opts = {
    inputs: [],
    out: "",
    top: 3,
    desc: 30,
    sparse: null,
    scale: "",
    json: false,
    sample: "",
    n: 5,
  };
  const valued = new Set(["--out", "--top", "--desc", "--sparse", "--scale", "--sample", "--n"]);
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--json") {
      opts.json = true;
    } else if (arg === "-h" || arg === "--help") {
      opts.help = true;
    } else if (valued.has(arg)) {
      const value = argv[i + 1];
      if (value === undefined || value.startsWith("--")) {
        throw new Error(`${arg} 需要一个值`);
      }
      i++;
      const key = arg.slice(2);
      if (["top", "desc", "sparse", "n"].includes(key)) {
        const num = parseInt(value, 10);
        if (!Number.isFinite(num) || num < 0) throw new Error(`${arg} 需要非负整数，收到 ${value}`);
        opts[key] = num;
      } else {
        opts[key] = value;
      }
    } else if (arg.startsWith("--")) {
      throw new Error(`未知参数：${arg}`);
    } else {
      opts.inputs.push(arg);
    }
  }
  if (opts.scale && !["long", "short"].includes(opts.scale)) {
    throw new Error(`--scale 只接受 long 或 short，收到 ${opts.scale}`);
  }
  return opts;
}

const USAGE = [
  "用法：node aggregate-rank.js <榜单文件或目录>... [--out 순위조사집계.md] [--top 3] [--desc 30]",
  "                            [--sparse 15，刺猬猫默认 10] [--scale long|short] [--json]",
  "      node aggregate-rank.js <榜单文件或目录>... --sample <题材/标签/书名词> [--n 5]",
].join("\n");

// ---------------------------------------------------------------------------
// 숫자·필드 파싱
// ---------------------------------------------------------------------------

/** ‘12.3万’, ‘1,234’, ‘45’는 숫자로, [待补]·미상·빈 값은 null로 변환한다. */
function parseNumber(raw) {
  if (raw === undefined || raw === null) return null;
  const text = String(raw).replace(/[,，\s]/g, "");
  const m = text.match(/(\d+(?:\.\d+)?)(万|亿)?/);
  if (!m) return null;
  let n = parseFloat(m[1]);
  if (m[2] === "万") n *= 10000;
  if (m[2] === "亿") n *= 100000000;
  return Math.round(n);
}

const STATUS_RE = /^(连载中?|已?完结|完本|暂停|断更|已完本)$/;
const WORDS_RE = /^(?:字数\s*)?([\d.,]+)\s*(万)?\s*字$/;
const READS_RE = /^([\d.,]+)\s*(万)?\s*(在读|热度|月票|收藏|赞同|点赞|阅读)$/;
const LABELED_RE = /^(收藏|营养液|积分|月票|在读|热度)\s*([\d.,]+)\s*(万)?$/;
const SCORE_RE = /^(\d+(?:\.\d+)?)\s*分$/;
const BARE_NUM_RE = /^[\d.,]+\s*万?$/;
const IGNORED_RE = /^(?:[\d.,]+\s*钻|公开|未公开|未知(?:\s*在读|字)?|\[待补\]|VIP|免费|签约|A签|B签|已签约|未签约)$/;

function classifySegments(segments) {
  const result = { status: "", words: null, metrics: {}, rest: [] };
  for (const seg of segments) {
    const s = seg.trim();
    if (!s) continue;
    let m;
    if (STATUS_RE.test(s)) {
      result.status = s;
    } else if ((m = s.match(WORDS_RE))) {
      result.words = parseNumber(m[1] + (m[2] || ""));
    } else if ((m = s.match(READS_RE))) {
      result.metrics[m[3]] = parseNumber(m[1] + (m[2] || ""));
    } else if ((m = s.match(LABELED_RE))) {
      result.metrics[m[1]] = parseNumber(m[2] + (m[3] || ""));
    } else if ((m = s.match(SCORE_RE))) {
      result.metrics["评分"] = parseFloat(m[1]);
    } else if (IGNORED_RE.test(s)) {
      continue;
    } else if (BARE_NUM_RE.test(s)) {
      result.metrics["榜单值"] = parseNumber(s);
    } else {
      result.rest.push(s);
    }
  }
  return result;
}

function splitTags(text) {
  return String(text || "")
    .split(/[、,，+/／|｜\s]+/)
    .map((t) => t.trim())
    .filter((t) => t && t !== "[待补]" && t !== "未知");
}

// ---------------------------------------------------------------------------
// 파일 파싱
// ---------------------------------------------------------------------------

const TITLE_RE = /^#\s+(.+?)\s*·\s*(.+?)\s*$/;
const ENTRY_RE = /^#{2,3}\s+#(\d+)\s+(.*)$/;
const SECTION_RE = /^##\s+(.+?)\s+—\s+(.+)$/;
const HEADER_RE = /^-\s*([^：:]+)[：:]\s*(.*)$/;
// 판체 머리의 ‘- 每题材上限 ≈ 20’은 콜론이 없어 따로 인식한다.
const CAP_RE = /^-\s*每题材上限\s*[≈约：:]?\s*(\d+)/;

function parseRankFile(filePath) {
  const text = fs.readFileSync(filePath, "utf8").replace(/^﻿/, "");
  const lines = text.split(/\r?\n/);
  const firstHeading = lines.find((line) => /^#\s/.test(line));
  const tm = firstHeading ? firstHeading.match(TITLE_RE) : null;
  if (!tm) return null;
  // 첫 행은 순위처럼 보이지만 항목이 없으면 수집 실패 가능성이 높다. 반환은 하되 수집 상황의 ‘没采到’에 넣고
  // 장르 통계에는 포함하지 않는다.

  const file = {
    path: filePath,
    name: path.basename(filePath),
    platform: tm[1].trim(),
    list: tm[2].trim(),
    header: {},
    sections: [],
    entries: [],
  };

  let inHeader = true;
  let section = "";
  let current = null;

  const finish = () => {
    if (!current) return;
    while (current.raw.length && /^(---|\s*)$/.test(current.raw[current.raw.length - 1])) {
      current.raw.pop();
    }
    file.entries.push(parseEntry(current, file));
    current = null;
  };

  for (const line of lines) {
    if (inHeader) {
      const cm = line.match(CAP_RE);
      if (cm) {
        file.header["每题材上限"] = cm[1];
        continue;
      }
      const hm = line.match(HEADER_RE);
      if (hm) {
        file.header[hm[1].trim()] = hm[2].trim();
        continue;
      }
      if (line.trim() === "---" || ENTRY_RE.test(line) || SECTION_RE.test(line)) {
        inHeader = false;
      }
      if (line.trim() === "---") continue;
    }
    const em = line.match(ENTRY_RE);
    if (em) {
      finish();
      current = { rank: parseInt(em[1], 10), title: em[2].trim(), section, raw: [line] };
      continue;
    }
    const sm = line.match(SECTION_RE);
    if (sm) {
      finish();
      section = sm[1].trim();
      const status = sm[2].trim();
      const count = parseNumber(status);
      file.sections.push({ name: section, status, count: /本$/.test(status) ? count : null });
      continue;
    }
    if (current) current.raw.push(line);
  }
  finish();
  return file;
}

function parseEntry(entry, file) {
  const body = entry.raw.slice(1);
  let metaLine = "";
  const tags = [];
  const metrics = {};
  let words = null;
  const descLines = [];
  let inDesc = false;

  for (const line of body) {
    const t = line.trim();
    if (!t) continue;
    if (!metaLine && /^\*[^*].*\*$/.test(t)) {
      metaLine = t.slice(1, -1);
      continue;
    }
    let m;
    if ((m = t.match(/^\*\*标签[：:]\*\*\s*(.*)$/))) {
      tags.push(...splitTags(m[1]));
      inDesc = false;
    } else if ((m = t.match(/^\*\*字数[：:]\s*(.*?)\*\*$/))) {
      words = parseNumber(m[1]);
    } else if ((m = t.match(/^\*\*(总推荐|榜单值|月票|收藏|在读|热度)[：:]\s*(.*?)\*\*$/))) {
      const value = parseNumber(m[2]);
      if (value !== null) metrics[m[1]] = value;
    } else if (t === "**简介**") {
      inDesc = true;
    } else if (/^\*\*[^*]+[：:]/.test(t) || /^\[作品页\]/.test(t)) {
      inDesc = false;
    } else if (t.startsWith(">")) {
      descLines.push(t.replace(/^>\s*/, ""));
    } else if (inDesc) {
      descLines.push(t);
    }
  }

  const segments = metaLine ? metaLine.split(/\s+·\s+/) : [];
  const cls = classifySegments(segments);
  Object.assign(metrics, Object.fromEntries(
    Object.entries(cls.metrics).filter(([, v]) => v !== null && v !== undefined)
  ));
  if (words === null) words = cls.words;

  let author = "";
  let metaGenre = "";
  const rest = cls.rest;
  if (file.platform === "刺猬猫" && rest.length < 2) {
    // 수집한 츠웨이마오 항목의 텍스트 필드는 하나뿐이다. 1위는 작가, 나머지는 장르다.
    // 수동 정리한 ‘作者 · 题材’가 모두 있으면 일반 위치로 읽는다.
    if (entry.rank === 1) author = rest[0] || "";
    else metaGenre = rest[0] || "";
  } else {
    author = rest[0] || "";
    metaGenre = rest[1] || "";
    for (const extra of rest.slice(2)) tags.push(...splitTags(extra));
  }
  // 헤이옌 ‘男频/现言’: 슬래시 뒤가 장르다.
  if (metaGenre.includes("/")) {
    const parts = metaGenre.split("/").filter(Boolean);
    metaGenre = parts[parts.length - 1] || metaGenre;
  }
  // 치디안 ‘玄幻·东方玄幻’: 주분류를 장르로, 하위 분류를 태그로 넣어 장르 표가 쪼개지지 않게 한다.
  if (metaGenre.includes("·")) {
    const [main, ...subs] = metaGenre.split("·").map((x) => x.trim()).filter(Boolean);
    metaGenre = main || metaGenre;
    for (const sub of subs) tags.push(sub);
  }
  const sectionGenre = entry.section && !/^全部/.test(entry.section) ? entry.section : "";
  const genre = metaGenre || sectionGenre || "未分类";

  return {
    platform: file.platform,
    list: file.list,
    file: file.name,
    rank: entry.rank,
    title: entry.title,
    resolved: !UNRESOLVED_TITLES.has(entry.title) && !/^bookId:/.test(entry.title),
    author,
    genre,
    status: cls.status,
    words,
    metrics,
    tags: Array.from(new Set(tags)),
    desc: descLines.join(" ").replace(/\s+/g, " ").trim(),
    raw: entry.raw.join("\n"),
  };
}

function collectFiles(inputs) {
  const files = [];
  for (const input of inputs) {
    if (!fs.existsSync(input)) throw new Error(`找不到输入：${input}`);
    const stat = fs.statSync(input);
    if (stat.isDirectory()) {
      const names = fs.readdirSync(input).filter((n) => n.endsWith(".md")).sort();
      for (const name of names) files.push(path.join(input, name));
    } else {
      files.push(input);
    }
  }
  return files.filter((f) => !OWN_OUTPUT_PREFIXES.some((p) => path.basename(f).startsWith(p)));
}

// ---------------------------------------------------------------------------
// 집계
// ---------------------------------------------------------------------------

function median(values) {
  const nums = values.filter((v) => typeof v === "number" && Number.isFinite(v)).sort((a, b) => a - b);
  if (!nums.length) return null;
  const mid = Math.floor(nums.length / 2);
  return nums.length % 2 ? nums[mid] : Math.round((nums[mid - 1] + nums[mid]) / 2);
}

function countBy(items) {
  const map = new Map();
  for (const item of items) map.set(item, (map.get(item) || 0) + 1);
  return Array.from(map.entries()).sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0]), "zh"));
}

function normKey(s) {
  return String(s || "").replace(/[\s《》「」“”"']/g, "").toLowerCase();
}

function wordBuckets(scale) {
  if (scale === "short") {
    return [
      ["5千字以下", 0, 5000],
      ["5千-1万字", 5000, 10000],
      ["1-2万字", 10000, 20000],
      ["2-4万字", 20000, 40000],
      ["4万字以上", 40000, Infinity],
    ];
  }
  return [
    ["10万字以下", 0, 100000],
    ["10-30万字", 100000, 300000],
    ["30-50万字", 300000, 500000],
    ["50-100万字", 500000, 1000000],
    ["100-200万字", 1000000, 2000000],
    ["200万字以上", 2000000, Infinity],
  ];
}

function isNewList(list) {
  return /新书|新人|新手|新作|潜力/.test(list);
}

// 기준의 분모는 인기도 숫자가 있는 순위에 오른 작품(inMetricList)만 센다. 순서만 있는 페이지순 라이브러리는
// 원래 인기도가 없으므로 포함하면 페이지를 많이 수집할수록 실제 인기 순위의 기준이 ‘순위 순서’로 밀려난다.
function pickMetric(books) {
  const counts = new Map();
  for (const b of books) for (const k of Object.keys(b.metrics)) counts.set(k, (counts.get(k) || 0) + 1);
  const threshold = Math.max(1, Math.ceil(books.filter((b) => b.inMetricList).length * 0.3));
  for (const k of METRIC_PRIORITY) if ((counts.get(k) || 0) >= threshold) return k;
  return "";
}

// 장르 안 일부 작품만 인기도가 있으면 그 수가 이 기준보다 적을 때 중앙값을 보고하지 않는다. 한두 작품이 장르 전체를 대표할 수 없다.
const MIN_HEAT_KNOWN = 3;

function titleGrams(titles, minCount) {
  const counter = new Map();
  for (const title of titles) {
    const clean = title.replace(/[^一-龥A-Za-z0-9]/g, "");
    const seen = new Set();
    for (let i = 0; i < clean.length - 1; i++) seen.add(clean.slice(i, i + 2));
    for (const g of seen) counter.set(g, (counter.get(g) || 0) + 1);
  }
  return Array.from(counter.entries())
    .filter(([, c]) => c >= minCount)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "zh"))
    .slice(0, 20);
}

// 순위·제목·작가가 항목별로 같은 두 목록은 같은 데이터다. 제목을 해석하지 못한 항목은 비교하지 않아
// 모두 ‘（标题待解析）· 未知’인 두 목록을 같다고 오판하지 않는다.
function entrySignature(file) {
  if (!file.entries.length || file.entries.some((e) => !e.resolved)) return "";
  return file.platform + "\n" + file.entries.map((e) => `${e.rank}|${normKey(e.title)}|${normKey(e.author)}`).join("\n");
}

// 뒤에 읽은 중복 목록에 duplicateOf를 붙인다(재호출에도 결과 동일). 집계·표본 추출은 이를 건너뛴다.
function markDuplicateLists(parsedFiles) {
  const firstBySignature = new Map();
  for (const file of parsedFiles) {
    const signature = entrySignature(file);
    if (!signature) continue;
    if (firstBySignature.has(signature)) file.duplicateOf = firstBySignature.get(signature).list;
    else firstBySignature.set(signature, file);
  }
}

function sparseFor(platform, opts) {
  if (opts.sparse !== null && opts.sparse !== undefined) return opts.sparse;
  return SMALL_PLATFORM_SPARSE[platform] || DEFAULT_SPARSE;
}

function aggregate(parsedFiles, opts) {
  markDuplicateLists(parsedFiles);

  const byPlatform = new Map();
  for (const file of parsedFiles) {
    if (!file.entries.length || file.duplicateOf) continue;
    if (!byPlatform.has(file.platform)) byPlatform.set(file.platform, []);
    byPlatform.get(file.platform).push(file);
  }

  const platforms = [];
  for (const [platform, files] of byPlatform) {
    const entries = files.flatMap((f) => f.entries);
    const scale = opts.scale || (SHORT_PLATFORMS.has(platform) ? "short" : "long");
    const sparse = sparseFor(platform, opts);
    // 인기도 숫자가 전혀 없는 목록은 순서 목록으로만 보며 인기도 기준의 분모에 넣지 않는다(pickMetric 참조).
    const rankOnlyFiles = files.filter((f) => !f.entries.some((e) => Object.keys(e.metrics).length));
    const rankOnlyEntries = new Set(rankOnlyFiles.flatMap((f) => f.entries));

    // 동일 플랫폼의 제목+작가가 같은 작품은 한 권으로 세고 등장한 순위 목록을 기록한다.
    const books = new Map();
    for (const e of entries) {
      const key = e.resolved ? `${normKey(e.title)}|${normKey(e.author)}` : `${e.file}|${e.list}|${e.rank}`;
      let book = books.get(key);
      if (!book) {
        book = { ...e, lists: [], bestRank: e.rank, metrics: { ...e.metrics }, tags: [...e.tags] };
        books.set(key, book);
      } else {
        for (const [k, v] of Object.entries(e.metrics)) {
          if (book.metrics[k] === undefined || v > book.metrics[k]) book.metrics[k] = v;
        }
        for (const t of e.tags) if (!book.tags.includes(t)) book.tags.push(t);
        if (book.words === null && e.words !== null) book.words = e.words;
        if (!book.desc && e.desc) book.desc = e.desc;
        if (book.genre === "未分类" && e.genre !== "未分类") book.genre = e.genre;
        book.bestRank = Math.min(book.bestRank, e.rank);
      }
      const label = e.list;
      if (!book.lists.includes(label)) book.lists.push(label);
      if (isNewList(e.list)) book.inNewList = true;
      else book.inOtherList = true;
      if (!rankOnlyEntries.has(e)) book.inMetricList = true;
    }
    const uniq = Array.from(books.values());
    const metric = pickMetric(uniq);
    const hasNew = entries.some((e) => isNewList(e.list));
    const hasOther = entries.some((e) => !isNewList(e.list));
    const sortKey = (b) => (metric && typeof b.metrics[metric] === "number" ? -b.metrics[metric] : 0);
    const byHeat = (a, b) => sortKey(a) - sortKey(b) || a.bestRank - b.bestRank;

    const genreMap = new Map();
    for (const b of uniq) {
      if (!genreMap.has(b.genre)) genreMap.set(b.genre, []);
      genreMap.get(b.genre).push(b);
    }
    const genres = Array.from(genreMap.entries())
      .map(([name, list]) => {
        const sorted = [...list].sort(byHeat);
        const heatKnown = metric ? list.filter((b) => typeof b.metrics[metric] === "number").length : 0;
        const heatShown = heatKnown === list.length || heatKnown >= MIN_HEAT_KNOWN;
        return {
          name,
          count: list.length,
          share: uniq.length ? list.length / uniq.length : 0,
          heatMedian: metric && heatShown ? median(list.map((b) => b.metrics[metric])) : null,
          heatKnown,
          wordsMedian: median(list.map((b) => b.words)),
          newCount: list.filter((b) => b.inNewList).length,
          topTags: countBy(list.flatMap((b) => b.tags)).slice(0, 3).map(([t]) => t),
          sparse: list.length < sparse,
          reps: sorted.filter((b) => b.resolved).slice(0, opts.top).map((b) => ({
            title: b.title,
            author: b.author,
            heat: metric ? b.metrics[metric] ?? null : null,
            words: b.words,
            tags: b.tags.slice(0, 4),
            desc: opts.desc > 0 ? truncate(b.desc, opts.desc) : "",
            lists: b.lists.length,
          })),
        };
      })
      .sort((a, b) => b.count - a.count || (b.heatMedian || 0) - (a.heatMedian || 0) || a.name.localeCompare(b.name, "zh"));

    const buckets = wordBuckets(scale).map(([label, lo, hi]) => ({
      label,
      count: uniq.filter((b) => typeof b.words === "number" && b.words >= lo && b.words < hi).length,
    }));
    const withMetric = metric ? uniq.filter((b) => typeof b.metrics[metric] === "number").map((b) => b.metrics[metric]).sort((a, b) => a - b) : [];
    const quantile = (q) => (withMetric.length ? withMetric[Math.min(withMetric.length - 1, Math.floor(q * (withMetric.length - 1) + 0.5))] : null);
    const cappedFiles = files.filter((f) => parseInt(f.header["每题材上限"], 10) > 0);

    platforms.push({
      platform,
      scale,
      sparse,
      metric,
      rankOnlyLists: metric ? Array.from(new Set(rankOnlyFiles.map((f) => f.list))) : [],
      perGenreCap: cappedFiles.length
        ? { top: Math.max(...cappedFiles.map((f) => parseInt(f.header["每题材上限"], 10))), lists: cappedFiles.map((f) => f.list) }
        : null,
      entryCount: entries.length,
      bookCount: uniq.length,
      unresolved: entries.filter((e) => !e.resolved).length,
      compareNew: hasNew && hasOther,
      genres,
      tags: countBy(uniq.flatMap((b) => b.tags)).slice(0, 30),
      words: { median: median(uniq.map((b) => b.words)), known: uniq.filter((b) => typeof b.words === "number").length, buckets },
      heat: metric ? { p25: quantile(0.25), p50: quantile(0.5), p75: quantile(0.75), max: quantile(1), known: withMetric.length } : null,
      status: countBy(uniq.map((b) => b.status || "未标")),
      titleGrams: titleGrams(uniq.filter((b) => b.resolved).map((b) => b.title), 3),
      overlap: uniq
        .filter((b) => b.lists.length >= 2)
        .sort((a, b) => b.lists.length - a.lists.length || byHeat(a, b))
        .slice(0, 15)
        .map((b) => ({ title: b.title, genre: b.genre, lists: b.lists })),
    });
  }

  const files = parsedFiles.map((f) => {
    const problems = [];
    const quality = f.header["数据质量"] || "";
    if (f.header["问题摘要"] && f.header["问题摘要"] !== "无") problems.push(f.header["问题摘要"]);
    const unresolved = f.entries.filter((e) => !e.resolved).length;
    if (unresolved) problems.push(`书名待解析 ${unresolved} 条`);
    const failed = f.sections.filter((s) => /失败/.test(s.status) || s.count === 0).map((s) => s.name);
    if (!f.entries.length) problems.push("没采到：整份榜单一本都没有");
    else if (failed.length) problems.push(`没采到：${failed.join("、")}`);
    if (f.duplicateOf) problems.push(`和「${f.duplicateOf}」条目完全相同，是同一份数据，只按一份计`);
    return {
      name: f.name,
      platform: f.platform,
      list: f.list,
      duplicateOf: f.duplicateOf || "",
      time: (f.header["抓取时间"] || "").slice(0, 10),
      entries: f.entries.length,
      quality: quality || "未标注",
      problems,
    };
  });

  platforms.sort((a, b) => b.bookCount - a.bookCount || a.platform.localeCompare(b.platform, "zh"));
  const explicitSparse = opts.sparse !== null && opts.sparse !== undefined;
  return { files, platforms, options: { top: opts.top, sparse: explicitSparse ? opts.sparse : DEFAULT_SPARSE, sparseExplicit: explicitSparse } };
}

function truncate(text, n) {
  const s = String(text || "");
  return s.length > n ? s.slice(0, n) + "…" : s;
}

// ---------------------------------------------------------------------------
// 출력
// ---------------------------------------------------------------------------

function fmtNum(n) {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  if (Math.abs(n) >= 100000000) return (n / 100000000).toFixed(1).replace(/\.0$/, "") + "亿";
  if (Math.abs(n) >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, "") + "万";
  return String(Math.round(n * 10) / 10);
}

function pct(x) {
  return `${Math.round(x * 100)}%`;
}

// 장르 인기도 중앙값: 모두 값이 있으면 숫자만, 일부만 있으면 유효 권수도 쓴다. MIN_HEAT_KNOWN보다 적으면 숫자를 쓰지 않는다.
function fmtHeatMedian(g) {
  if (!g.heatKnown || g.heatKnown === g.count) return fmtNum(g.heatMedian);
  if (g.heatMedian === null) return `—（只有 ${g.heatKnown} 本有值）`;
  return `${fmtNum(g.heatMedian)}（${g.heatKnown} 本有值）`;
}

// 머리의 ‘数据质量’는 스크립트·유지보수자용 표식이다. 작가 폴더에 저장하는 ‘순위조사집계.md’에서는 쉬운 말로 바꾼다.
const QUALITY_WORDS = {
  "[OK]": "正常",
  "[标题解析异常]": "书名大多没解出来",
  "[书名解析异常]": "书名大多没解出来",
  "[无数据]": "没有数据",
  "[存在问题]": "有问题",
  "[仅列表-无核心指标]": "只有书单，缺热度等关键数字",
  "[详情解析异常/登录态缺失]": "详情大多没取到，可能没登录",
  "[部分详情缺失]": "部分详情没取到",
  "未标注": "质量未标",
};

function qualityWords(quality) {
  if (Object.prototype.hasOwnProperty.call(QUALITY_WORDS, quality)) return QUALITY_WORDS[quality];
  return String(quality || "").replace(/^\[(.*)\]$/, "$1") || "质量未标";
}

function renderMarkdown(result) {
  const out = ["# 扫榜聚合", ""];
  out.push(`- 来源：${result.files.length} 个榜单文件，${result.platforms.map((p) => `${p.platform} ${p.bookCount} 本`).join("，")}`);
  const smallOnes = result.options.sparseExplicit
    ? []
    : result.platforms.filter((p) => p.sparse !== result.options.sparse).map((p) => `${p.platform} ${p.sparse} 本`);
  const smallNote = smallOnes.length ? `（${smallOnes.join("、")}）` : "";
  out.push(`- 样本门槛：同题材少于 ${result.options.sparse} 本${smallNote}标「少」，不能单独撑起高可行性`);
  out.push("");
  out.push("## 采集情况", "");
  for (const f of result.files) {
    const note = f.problems.length ? `；${f.problems.join("；")}` : "";
    out.push(`- ${f.platform} · ${f.list}：${f.entries} 条，${f.time || "日期未标"}，${qualityWords(f.quality)}${note}`);
  }
  out.push("");

  for (const p of result.platforms) {
    const metricLabel = p.metric || "无热度字段，按榜单名次";
    out.push(`## ${p.platform}（${p.bookCount} 本，热度口径：${metricLabel}）`, "");
    const newCol = p.compareNew;
    const head = ["题材", "本数", "占比", "热度中位", "字数中位", "高频标签", "样本"];
    if (newCol) head.splice(3, 0, "新书榜");
    out.push(`| ${head.join(" | ")} |`);
    out.push(`|${head.map(() => "---").join("|")}|`);
    for (const g of p.genres) {
      const row = [
        g.name,
        String(g.count),
        pct(g.share),
        fmtHeatMedian(g),
        fmtNum(g.wordsMedian),
        g.topTags.join("、") || "—",
        g.sparse ? "少" : p.perGenreCap ? "采样" : "够",
      ];
      if (newCol) row.splice(3, 0, String(g.newCount));
      out.push(`| ${row.join(" | ")} |`);
    }
    out.push("");

    if (p.heat) {
      out.push(`- 热度分布（${p.metric}，${p.heat.known} 本有值）：P25 ${fmtNum(p.heat.p25)} / 中位 ${fmtNum(p.heat.p50)} / P75 ${fmtNum(p.heat.p75)} / 最高 ${fmtNum(p.heat.max)}`);
    }
    if (p.perGenreCap) {
      out.push(`- 每题材按上限取前 ${p.perGenreCap.top} 本（${p.perGenreCap.lists.join("、")}）：本数和占比是采样结果，不代表题材大小，样本列标「采样」不算够；同方向够不够数细分梗或标签的本数，题材冷热看热度中位`);
    }
    if (p.rankOnlyLists.length) {
      out.push(`- 没有热度数字的榜（只按名次）：${p.rankOnlyLists.join("、")}；热度中位和热度分布只算有热度的书`);
    }
    if (p.words.known) out.push(`- 字数分布（${p.words.known} 本有值，中位 ${fmtNum(p.words.median)}字）：${p.words.buckets.map((b) => `${b.label} ${b.count}`).join("，")}`);
    out.push(`- 状态：${p.status.map(([s, c]) => `${s} ${c}`).join("，")}`);
    if (p.tags.length) out.push(`- 标签热词：${p.tags.map(([t, c]) => `${t}(${c})`).join("、")}`);
    if (p.titleGrams.length) out.push(`- 书名常见词：${p.titleGrams.map(([t, c]) => `${t}(${c})`).join("、")}`);
    if (p.overlap.length) {
      out.push(`- 多榜重合：${p.overlap.map((o) => `《${o.title}》(${o.genre}，${o.lists.length} 榜)`).join("、")}`);
    }
    out.push("");

    out.push(`### ${p.platform}各题材代表作（每题材前 ${result.options.top} 本）`, "");
    for (const g of p.genres) {
      if (!g.reps.length) continue;
      out.push(`**${g.name}**`);
      for (const r of g.reps) {
        const parts = [`《${r.title}》`];
        if (r.author) parts.push(r.author);
        if (p.metric && typeof r.heat === "number") parts.push(`${fmtNum(r.heat)}${p.metric}`);
        if (r.words !== null && r.words !== undefined) parts.push(`${fmtNum(r.words)}字`);
        if (r.tags.length) parts.push(r.tags.join("、"));
        if (r.lists >= 2) parts.push(`${r.lists} 榜`);
        let line = `- ${parts.join(" · ")}`;
        if (r.desc) line += `｜${r.desc}`;
        out.push(line);
      }
      out.push("");
    }
  }
  return out.join("\n") + "\n";
}

function renderSample(parsedFiles, query, n) {
  const q = query.trim();
  markDuplicateLists(parsedFiles);
  const hits = parsedFiles
    .filter((f) => !f.duplicateOf)
    .flatMap((f) => f.entries)
    .filter((e) => e.genre === q || e.tags.includes(q) || e.title.includes(q) || (e.section && e.section === q));
  const metricOf = (e) => {
    for (const k of METRIC_PRIORITY) if (typeof e.metrics[k] === "number") return e.metrics[k];
    return null;
  };
  hits.sort((a, b) => (metricOf(b) ?? -1) - (metricOf(a) ?? -1) || a.rank - b.rank);
  const out = [`# 抽样：${q}（命中 ${hits.length} 条，显示 ${Math.min(n, hits.length)} 条）`, ""];
  for (const e of hits.slice(0, n)) {
    out.push(`<!-- ${e.platform} · ${e.list} · ${e.file} -->`);
    out.push(e.raw, "");
  }
  return out.join("\n") + "\n";
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function main(argv) {
  const opts = parseArgs(argv);
  if (opts.help) {
    process.stdout.write(USAGE + "\n");
    return 0;
  }
  if (!opts.inputs.length) {
    process.stderr.write(USAGE + "\n");
    return 2;
  }
  const parsed = collectFiles(opts.inputs).map(parseRankFile).filter(Boolean);
  if (!parsed.some((f) => f.entries.length)) {
    const empty = parsed.map((f) => f.name);
    process.stderr.write(
      "没有找到可聚合的榜单文件（首行须是「# 平台 · 榜单名」，且含「### #排名 书名」条目）。" +
        (empty.length ? `这些榜单一本都没有：${empty.join("、")}。` : "") + "\n"
    );
    return 1;
  }
  if (opts.sample) {
    process.stdout.write(renderSample(parsed, opts.sample, opts.n));
    return 0;
  }
  const result = aggregate(parsed, opts);
  const text = opts.json ? JSON.stringify(result, null, 2) + "\n" : renderMarkdown(result);
  if (opts.out) {
    fs.mkdirSync(path.dirname(path.resolve(opts.out)), { recursive: true });
    fs.writeFileSync(opts.out, text, "utf8");
  }
  process.stdout.write(text);
  return 0;
}

if (require.main === module) {
  try {
    process.exitCode = main(process.argv.slice(2));
  } catch (err) {
    process.stderr.write(`aggregate-rank：${err && err.message ? err.message : err}\n`);
    process.exitCode = 2;
  }
}

module.exports = { parseRankFile, aggregate, renderMarkdown, parseNumber, classifySegments };
