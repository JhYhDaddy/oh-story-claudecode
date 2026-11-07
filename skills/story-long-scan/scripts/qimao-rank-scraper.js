#!/usr/bin/env node
/**
 * 치마오 소설 순위 수집기. 순위 경로는 browser-cdp로 Chrome CDP를 먼저 시작한다.
 * 탭으로 남성·여성 및 순위 유형을 바꾸고 스크롤 로딩 후 페이지 텍스트에서 구조화 데이터를 파싱한다.
 * 출력 Markdown 형식은 aggregate-rank.js 머리 주석을 따른다.
 * 사용법:
 *   node qimao-rank-scraper.js --channel male --type hot --period day   # 남성 인기 일간
 *   node qimao-rank-scraper.js --channel male --type hot --period month # 남성 인기 월간
 *   node qimao-rank-scraper.js --channel male --type hot --period all   # 일간+월간
 *   node qimao-rank-scraper.js --channel female --type new             # 여성 신작
 *   node qimao-rank-scraper.js --channel all --type all                # 전체
 *   node qimao-rank-scraper.js --source library --pages 3              # 조회순 신작 첫 3페이지
 * 순위 수집 전 실행:
 *   node {SKILL_DIR}/browser-cdp/scripts/setup-cdp-chrome.js 9222
 * 라이브러리 필터는 서버 렌더링이므로 직접 HTTPS를 사용하며 Chrome이 필요 없다.
 */

const fs = require("fs");
const https = require("https");
const path = require("path");
const { ab, sleep, evalJSONBase64, scrollLoad, getArg, localDateStamp, runCli } = require("./cdp-utils");

const RANK_URL = "https://www.qimao.com/paihang";

/** 연결·페이지 준비 상태 자체 검사. */
function probePage(port) {
  return evalJSONBase64(
    port,
    "JSON.stringify({host:location.host,path:location.pathname,len:(document.body&&document.body.innerText||'').length})"
  );
}

const CHANNELS = [
  { id: "male", label: "男频", tab: "男生榜", path: "boy" },
  { id: "female", label: "女频", tab: "女生榜", path: "girl" },
];

const RANK_TYPES = [
  { id: "hot", label: "大热榜", path: "hot" },
  { id: "new", label: "新书榜", path: "new" },
  { id: "finish", label: "完结榜", path: "over" },
  { id: "collect", label: "收藏榜", path: "collect" },
  { id: "update", label: "更新榜", path: "update" },
];

const PERIODS = [
  { id: "day", label: "日榜", path: "date" },
  { id: "month", label: "月榜", path: "month" },
];

// ---------------------------------------------------------------------------
// 페이지 조작
// ---------------------------------------------------------------------------

function rankUrl(channelId, rankTypeId, periodId) {
  const channel = CHANNELS.find((item) => item.id === channelId);
  const rankType = RANK_TYPES.find((item) => item.id === rankTypeId);
  const period = PERIODS.find((item) => item.id === (periodId || "day"));
  if (!channel || !rankType || !period) return "";
  return `${RANK_URL}/${channel.path}/${rankType.path}/${period.path}/`;
}

/** 페이지의 실제 active 상태를 읽고 검증한 뒤에만 출력 파일 레이블로 사용한다. */
function extractObservedSelection(port) {
  const js = `JSON.stringify((function(){
    function text(selector){var e=document.querySelector(selector);return e?(e.textContent||'').replace(/\\s+/g,'').trim():'';}
    return {path:location.pathname,channel:text('.qm-switch-tab .item.active'),rankType:text('.child-tabs-item.menu-tab.active'),period:text('.date-type-tabs .tab.active')};
  })())`;
  return evalJSONBase64(port, js) || {};
}

function selectionMatches(observed, channelId, rankTypeId, periodId) {
  const channel = CHANNELS.find((item) => item.id === channelId);
  const rankType = RANK_TYPES.find((item) => item.id === rankTypeId);
  const period = periodId ? PERIODS.find((item) => item.id === periodId) : null;
  if (!channel || !rankType) return false;
  const expectedUrl = rankUrl(channelId, rankTypeId, periodId);
  if (!expectedUrl) return false;
  const expectedPath = new URL(expectedUrl).pathname;
  const actualPath = String(observed && observed.path || "").replace(/\/+$/, "/");
  return !!(
    actualPath === expectedPath &&
    String(observed.channel || "").includes(channel.tab) &&
    observed.rankType === rankType.label &&
    (!period || observed.period === period.label)
  );
}

/**
 * DOM에서 작품 링크를 얻는다. 작품에는 순위 숫자·제목·최신 갱신 등 여러 anchor가 있다.
 * bookId로 묶어 숫자 전용·최근 갱신 접두사를 제외한 가장 긴 텍스트를 제목으로 선택한다.
 * 그렇지 않으면 숫자 anchor가 제목을 덮어 제목별 링크 보충이 모두 실패한다.
 */
function extractBookUrls(port) {
  const js = `JSON.stringify((function(){
    var byId={};var order=[];
    Array.from(document.querySelectorAll('a')).forEach(function(a){
      var h=a.getAttribute('href')||a.href||'';
      var m=h.match(/\\/(?:shuku|book)\\/([0-9]+)/);
      if(!m)return; var id=m[1];
      var t=(a.innerText||a.textContent||'').replace(/\\s+/g,' ').trim();
      if(!byId[id]){byId[id]='';order.push(id);}
      if(t&&!/^[0-9]+$/.test(t)&&!/^(最近更新|最新章节|最新)/.test(t)){
        if(t.length>byId[id].length)byId[id]=t;
      }
    });
    return order.map(function(id){return {bookId:id,title:byId[id],url:'https://www.qimao.com/shuku/'+id+'/'};});
  })())`;
  return evalJSONBase64(port, js) || [];
}

/** 페이지 innerText를 구조화 작품 데이터로 파싱한다. 고정 순서는 순위→제목→작가→장르→하위 분류→상태→글자 수→소개→갱신→인기도다. */
function extractBooksFromText(port) {
  const js =
    "JSON.stringify((()=>{" +
    "var text=document.body.innerText||'';" +
    // 순위 데이터 시작 위치를 찾는다.
    "var start=-1;" +
    "['日榜','月榜'].forEach(function(m){if(start<0)start=text.indexOf(m)});" +
    "if(start<0)return[];" +
    "var lines=text.substring(start).split(/\\n/);" +
    "var books=[];var cur=null;var fieldIdx=0;" +
    "for(var i=0;i<lines.length;i++){" +
    "  var line=lines[i].trim();" +
    "  if(!line)continue;" +
    // 순위 뒤 페이지 탐색기·푸터는 즉시 잘라야 한다. 아니면 ‘5 / 下一页 / 跳转 / 友情链接’가
    // 모든 필드를 갖춘 가짜 작품으로 이어진다.
    "  if(/^(上一页|下一页|跳转|友情链接[:：]?)$/.test(line)){if(cur&&cur.title)books.push(cur);cur=null;break}" +
    // 순위 표식: 독립 숫자 1–99.
    "  if(/^\\d{1,2}$/.test(line)&&parseInt(line)<100){" +
    "    if(cur&&cur.title)books.push(cur);" +
    "    cur={rank:parseInt(line),title:'',author:'',genre:'',subGenre:'',status:'',words:'',heat:'',update:'',desc:''};" +
    "    fieldIdx=0;continue" +
    "  }" +
    "  if(!cur)continue;" +
    // UI 텍스트 건너뛰기
    "  if(/^(加入书架|立即阅读|蝉联|榜首)/.test(line))continue;" +
    // 인기도
    "  var hm=line.match(/([\\d.]+)\\s*万\\s*热度/);" +
    "  if(hm){cur.heat=hm[1]+'万';continue}" +
    // 최신 갱신
    "  if(line.indexOf('最近更新')===0){cur.update=line.replace(/^最近更新\\s*/,'');continue}" +
    // 상태
    "  if(/^(连载中|已完结)$/.test(line)){cur.status=line;continue}" +
    // 글자 수
    "  if(/^[\\d.]+万字$/.test(line)){cur.words=line;continue}" +
    // 제목→작가→장르→하위 분류 순서로 채운다.
    "  if(fieldIdx===0){cur.title=line;fieldIdx=1;continue}" +
    "  if(fieldIdx===1){cur.author=line;fieldIdx=2;continue}" +
    "  if(fieldIdx===2){cur.genre=line;fieldIdx=3;continue}" +
    "  if(fieldIdx===3){cur.subGenre=line;fieldIdx=4;continue}" +
    // 나머지는 소개다.
    "  cur.desc+=(cur.desc?' ':'')+line" +
    "}" +
    "if(cur&&cur.title)books.push(cur);" +
    "return books" +
    "})())";
  return evalJSONBase64(port, js) || [];
}

/**
 * 본문 파서가 작품으로 오인한 페이지 탐색기 등을 제외한다.
 * 순위 끝에 ‘5 / 下一页’ 같은 UI가 있으므로 유효 항목에는 양수 순위·제목·작가가 모두 필요하다.
 */
function isUsableBook(book) {
  return !!(
    book &&
    Number.isInteger(book.rank) &&
    book.rank > 0 &&
    book.title &&
    book.author &&
    !/^(上一页|下一页|跳转)$/.test(book.title) &&
    !/^(上一页|下一页|跳转|友情链接[:：]?)$/.test(book.author)
  );
}

function cleanDesc(value) {
  const text = String(value || "")
    .replace(/\s*(?:飙升|上升|下降)\s*\d+\s*名\s*$/g, "")
    .replace(/\s*(?:上一页|下一页)\s*$/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (text.length <= 100) return text;
  const cut = text.slice(0, 100);
  const sentence = cut.match(/^[\s\S]*[。！？]/);
  return (sentence ? sentence[0] : cut) + "...";
}

function summarizeQuality(books, rawCount) {
  const linked = books.filter((book) => book.url).length;
  const heated = books.filter((book) => book.heat).length;
  const fieldCounts = [
    ["题材", "genre"],
    ["子分类", "subGenre"],
    ["状态", "status"],
    ["字数", "words"],
    ["热度", "heat"],
  ].map(([label, field]) => ({
    label,
    missing: books.filter((book) => !book[field]).length,
  }));
  const problems = [];
  if (rawCount > books.length) problems.push(`移除无效/UI条目 ${rawCount - books.length} 条`);
  if (linked < books.length) problems.push(`作品页链接缺失 ${books.length - linked} 条`);
  for (const field of fieldCounts) {
    if (field.missing) problems.push(`${field.label}缺失 ${field.missing} 条`);
  }
  if (books.length < 15) problems.push(`[数据稀疏] 实际采集 ${books.length} 条`);
  return {
    linked,
    heated,
    problems,
    quality: problems.length ? "[存在问题]" : "[OK]",
  };
}

function renderMarkdown(ch, rt, period, url, books, rawCount, now = new Date().toISOString()) {
  const periodLabel = period ? period.label : "";
  const summary = summarizeQuality(books, rawCount);
  const lines = [
    `# 七猫 · ${ch.label} · ${rt.label}${periodLabel}`,
    "",
    `- 数据质量：${summary.quality}`,
    `- 有效条目：${books.length} / ${rawCount}`,
    `- 问题摘要：${summary.problems.length ? summary.problems.join("；") : "无"}`,
    `- 作品页链接：${summary.linked} / ${books.length}`,
    `- 热度命中：${summary.heated} / ${books.length}`,
    `- 来源：${url}`,
    `- 抓取时间：${now}`,
    `- 条目数：${books.length}`,
    "",
    "---",
    "",
  ];

  for (const b of books) {
    try {
      lines.push(`### #${b.rank} ${b.title}`);
      const meta = [
        b.author || "[待补]",
        b.genre || "[待补]",
        b.subGenre || "[待补]",
        b.status || "[待补]",
        b.words || "[待补]",
        b.heat ? b.heat + "热度" : "[待补]",
      ].join(" · ");
      lines.push(`*${meta}*`);
      if (b.update) lines.push(`**最新更新：** ${b.update}`);
      if (b.url) lines.push(`[作品页](${b.url})`);
      const desc = cleanDesc(b.desc);
      if (desc) {
        lines.push("");
        lines.push("**简介**");
        lines.push("");
        lines.push(desc);
      }
      lines.push("", "---", "");
    } catch (bookErr) {
      console.error(`[qimao] ${ch.label}${rt.label} 第${b.rank}条处理出错: ${bookErr.message}`);
      lines.push("", "---", "");
    }
  }

  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// 라이브러리 필터 페이지(--source library).
// 전체 채널·30만 자 미만·3일 내 갱신·연재·조회순. 서버 렌더링 HTML을 Node가 직접 읽어
// Chrome을 열지 않는다. 인기도 숫자 없이 조회순 페이지 순서를 쓰며 하위 분류만 있어 주분류는 분류 페이지 제목에서 얻는다.
// ---------------------------------------------------------------------------

const LIBRARY_ID = "library";
const LIBRARY_LIST = "全站书库点击新书"; // ‘新书’를 포함해 집계의 신작 순위 열에 넣는다.
const LIBRARY_HOST = "www.qimao.com";
const LIBRARY_TITLE_MARKS = ["3天内更新", "30万以下", "连载中"];
const LIBRARY_SORT = "按点击量";
const LIBRARY_SORT_OPTIONS = ["按点击量", "按总字数", "最近更新", "按收藏数"];
const LIBRARY_FILTER_NOTE = "全部频道·30万字以下·3天内更新·连载中";
const LIBRARY_DEFAULT_PAGES = 3;
const LIBRARY_MAX_PAGES = 10;
const LIBRARY_REQUEST_GAP_MS = 800;
const LIBRARY_SPARSE_BELOW = 15;
const DESKTOP_HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
  Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
  "Accept-Language": "zh-CN,zh;q=0.9",
  "Accept-Encoding": "identity",
};
const MAX_HTML_BYTES = 5 * 1024 * 1024;

/** 라이브러리 page 페이지. 경로 구간은 채널-주분류-하위분류-글자수-갱신-?-상태-정렬-페이지이며 a는 제한 없음이다. */
function libraryPageUrl(page) {
  return `https://${LIBRARY_HOST}/shuku/a-a-a-1-1-a-0-click-${page}/`;
}

/** 주분류만 필터링한 라이브러리 페이지. <title>은 ‘{주분류}小说-’로 시작한다. */
function categoryUrl(mainId) {
  return `https://${LIBRARY_HOST}/shuku/a-${mainId}-a-a-a-a-a-click-1/`;
}

/** --pages 검증: 1–10 정수, 기본 3. */
function parseLibraryPages(raw) {
  if (raw === null || raw === undefined) return LIBRARY_DEFAULT_PAGES;
  const text = String(raw).trim();
  const pages = /^\d+$/.test(text) ? Number(text) : NaN;
  if (!Number.isInteger(pages) || pages < 1 || pages > LIBRARY_MAX_PAGES) {
    throw new Error(`未知 --pages: ${raw}（书库翻页取 1-${LIBRARY_MAX_PAGES} 的整数）`);
  }
  return pages;
}

/**
 * HTML 한 페이지: 데스크톱 UA·무압축·15초 제한·사이트 내부 리디렉션 최대 3회.
 * www.qimao.com/shuku/를 벗어나거나 상태가 200이 아니면 해당 페이지 실패다.
 * 응답 헤더에는 앞 공백이 있는 content-security-policy 등 접힌 행이 있어 Node의 엄격한 파서가 Parse Error를 낸다.
 * 이 요청만 헤더 파싱을 완화한다. 공개 페이지 읽기 전용이며 다른 요청에 영향은 없다.
 */
function fetchQimaoHtml(url, redirects = 3) {
  return new Promise((resolve, reject) => {
    const options = { headers: DESKTOP_HEADERS, timeout: 15000, insecureHTTPParser: true };
    const req = https.get(url, options, (res) => {
      const status = res.statusCode;
      if (status >= 300 && status < 400 && res.headers.location) {
        res.resume();
        if (redirects <= 0) {
          reject(new Error("重定向超过 3 次"));
          return;
        }
        let next;
        try {
          next = new URL(res.headers.location, url);
        } catch {
          reject(new Error(`重定向地址无效：${res.headers.location}`));
          return;
        }
        if (next.protocol !== "https:" || next.host !== LIBRARY_HOST || !next.pathname.startsWith("/shuku/")) {
          reject(new Error(`被重定向到 ${next.host}${next.pathname}，不是七猫书库页（可能被风控或登录页拦住）`));
          return;
        }
        fetchQimaoHtml(next.toString(), redirects - 1).then(resolve, reject);
        return;
      }
      if (status !== 200) {
        res.resume();
        reject(new Error(`HTTP ${status}`));
        return;
      }
      let body = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        body += chunk;
        if (body.length > MAX_HTML_BYTES) req.destroy(new Error("页面大小异常"));
      });
      res.on("end", () => resolve(body));
      res.on("error", reject);
    });
    req.on("timeout", () => req.destroy(new Error("请求超时（15 秒）")));
    req.on("error", reject);
  });
}

const HTML_ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };

function decodeEntities(text) {
  return String(text || "").replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (whole, name) => {
    if (name[0] === "#") {
      const code = /^#x/i.test(name) ? parseInt(name.slice(2), 16) : parseInt(name.slice(1), 10);
      return Number.isInteger(code) && code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : whole;
    }
    const decoded = HTML_ENTITIES[name.toLowerCase()];
    return decoded === undefined ? whole : decoded;
  });
}

/** 태그 제거→엔티티 해석→공백 압축 순서로 &lt;b&gt; 같은 제목을 보존한다.
 * 주석·태그를 변화가 없을 때까지 제거한 뒤 남은 꺾쇠를 없앤다. ‘<!<!---->--’ 같은 중첩·미종결 형태는 한 번 제거하면 새 ‘<!--’가 된다.
 * 실제 본문 꺾쇠는 소스에서 엔티티이므로 마지막 해석 때 복원되어 잘못 삭제되지 않는다. */
function htmlText(html) {
  let stripped = String(html || "");
  for (let previous = null; stripped !== previous; ) {
    previous = stripped;
    // 닫히지 않은 주석은 HTML 규칙대로 끝까지 주석 처리한다.
    stripped = stripped.replace(/<!--[\s\S]*?(?:-->|$)/g, "").replace(/<[^>]*>/g, " ");
  }
  return decodeEntities(stripped.replace(/[<>]/g, "")).replace(/\s+/g, " ").trim();
}

function attrValue(attrs, name) {
  const m = String(attrs || "").match(
    new RegExp(`(?:^|\\s)${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)'|([^\\s>]+))`, "i")
  );
  if (!m) return null;
  return decodeEntities(m[1] !== undefined ? m[1] : m[2] !== undefined ? m[2] : m[3]);
}

/** classNames를 모두 포함한 요소. Vue의 data-v-xxx 속성도 허용한다. */
function findByClass(html, classNames, limit = Infinity) {
  const wanted = [].concat(classNames);
  const found = [];
  const re = /<([a-zA-Z][\w-]*)\b([^>]*)>/g;
  let m;
  while ((m = re.exec(html)) && found.length < limit) {
    const cls = attrValue(m[2], "class");
    if (cls === null) continue;
    const tokens = cls.split(/\s+/);
    if (!wanted.every((name) => tokens.includes(name))) continue;
    const tag = m[1].toLowerCase();
    const closeRe = new RegExp(`</${tag}\\s*>`, "ig");
    closeRe.lastIndex = re.lastIndex;
    const close = closeRe.exec(html);
    found.push({ attrs: m[2], inner: html.slice(re.lastIndex, close ? close.index : html.length) });
  }
  return found;
}

function firstByClass(html, classNames) {
  return findByClass(html, classNames, 1)[0] || null;
}

function normalizeWords(text) {
  const t = String(text || "").replace(/\s+/g, "");
  if (/^[\d.]+万?字$/.test(t)) return t;
  if (/^[\d.]+万?$/.test(t)) return `${t}字`;
  return "";
}

/**
 * 라이브러리 HTML 한 페이지 파싱. li.qm-cover-text-item 하나가 작품 하나다.
 * .s-tit a(제목, /shuku/{bookId}/), .s-category(하위 분류, 링크에 주분류 id),
 * .s-status, .s-words-num, .s-desc, .s-author, .s-update-time.
 */
function parseShukuPage(html) {
  const source = String(html || "");
  const titleMatch = source.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  const sortTabs = findByClass(source, ["tab-inner", "active"])
    .map((el) => htmlText(el.inner))
    .filter((label) => LIBRARY_SORT_OPTIONS.includes(label));
  const pagerNumbers = findByClass(source, ["page-btn", "num"]).map((el) => ({
    n: /^\d+$/.test(htmlText(el.inner)) ? Number(htmlText(el.inner)) : null,
    active: (attrValue(el.attrs, "class") || "").split(/\s+/).includes("active"),
  }));
  const numbered = pagerNumbers.filter((p) => p.n !== null);
  const activePager = numbered.find((p) => p.active);

  const starts = [];
  const liRe = /<li\b([^>]*)>/gi;
  let m;
  while ((m = liRe.exec(source))) {
    const cls = attrValue(m[1], "class") || "";
    if (cls.split(/\s+/).includes("qm-cover-text-item")) starts.push(m.index);
  }
  const items = starts.map((start, i) => {
    const nextStart = i + 1 < starts.length ? starts[i + 1] : source.length;
    const end = source.indexOf("</li>", start);
    const chunk = source.slice(start, end > start && end < nextStart ? end : nextStart);
    const titleEl = firstByClass(chunk, "s-tit");
    const anchor = titleEl && titleEl.inner.match(/<a\b([^>]*)>([\s\S]*?)<\/a\s*>/i);
    const href = anchor ? attrValue(anchor[1], "href") || "" : "";
    const idMatch = href.match(/\/shuku\/(\d+)\/?(?:[?#]|$)/);
    const categoryEl = firstByClass(chunk, "s-category");
    const categoryHref = categoryEl ? attrValue(categoryEl.attrs, "href") || "" : "";
    const categoryIds = categoryHref.match(/\/shuku\/a-(\d+)-(\d+)-/);
    const text = (cls) => {
      const el = firstByClass(chunk, cls);
      return el ? htmlText(el.inner) : "";
    };
    const bookId = idMatch ? idMatch[1] : "";
    return {
      bookId,
      title: anchor ? htmlText(anchor[2]) : "",
      url: bookId ? `https://${LIBRARY_HOST}/shuku/${bookId}/` : "",
      author: text("s-author"),
      genre: "",
      subGenre: categoryEl ? htmlText(categoryEl.inner) : "",
      mainId: categoryIds ? categoryIds[1] : "",
      status: text("s-status"),
      words: normalizeWords(text("s-words-num")),
      update: text("s-update-time"),
      desc: text("s-desc"),
    };
  });

  return {
    title: titleMatch ? htmlText(titleMatch[1]) : "",
    sort: sortTabs.length === 1 ? sortTabs[0] : "",
    activePage: activePager ? activePager.n : null,
    maxPage: numbered.length ? Math.max(...numbered.map((p) => p.n)) : null,
    items,
  };
}

/** 실제 유효 필터는 파일 머리와 같아야 한다(#340). 제목 세 항목이 완전해야 하며 정렬을 읽을 수 있으면 조회순이어야 한다. */
function libraryPageProblems(page, requestedPage) {
  const problems = [];
  const missing = LIBRARY_TITLE_MARKS.filter((mark) => !page.title.includes(mark));
  if (missing.length) {
    problems.push(`页面标题「${page.title || "空"}」缺少「${missing.join("」「")}」，筛选没生效（可能被风控页拦住）`);
  }
  if (page.sort && page.sort !== LIBRARY_SORT) {
    problems.push(`页面排序是「${page.sort}」，不是「${LIBRARY_SORT}」`);
  }
  if (page.activePage !== null && page.activePage !== requestedPage) {
    problems.push(`请求第 ${requestedPage} 页，页面停在第 ${page.activePage} 页`);
  }
  return problems;
}

/** 주분류 페이지 <title> ‘都市小说-好看的都市小说-…’ → ‘都市’. 맞지 않으면 빈 문자열. */
function parseCategoryTitle(html) {
  const m = String(html || "").match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  const title = m ? htmlText(m[1]) : "";
  const name = title.match(/^([^\s\-—|]+?)小说-/);
  return name ? name[1] : "";
}

function metaPart(value) {
  return String(value || "").replace(/\*/g, "").replace(/\s*·\s*/g, "·").trim();
}

function summarizeLibraryQuality(books, rawCount, pageProblems) {
  const count = (pred) => books.filter(pred).length;
  const linked = count((book) => book.url);
  const problems = [...pageProblems];
  if (rawCount > books.length) problems.push(`移除无效条目 ${rawCount - books.length} 条`);
  if (linked < books.length) problems.push(`作品页链接缺失 ${books.length - linked} 条`);
  const missing = [
    ["主类未解析", (book) => !book.genre],
    ["子分类缺失", (book) => !book.subGenre],
    ["状态缺失", (book) => !book.status],
    ["字数缺失", (book) => !book.words],
  ];
  for (const [label, pred] of missing) {
    const n = count(pred);
    if (n) problems.push(`${label} ${n} 条`);
  }
  // 라이브러리는 원래 인기도 숫자가 없으므로 누락이 문제가 아니며 순위는 조회순 페이지 순서다.
  if (books.length < LIBRARY_SPARSE_BELOW) problems.push(`[数据稀疏] 实际采集 ${books.length} 条`);
  return { linked, problems, quality: problems.length ? "[存在问题]" : "[OK]" };
}

function renderLibraryMarkdown({ books, rawCount, pages, pagesRead, pageProblems = [], now = new Date().toISOString() }) {
  const summary = summarizeLibraryQuality(books, rawCount, pageProblems);
  const range = pagesRead < pages ? `取前 ${pages} 页（实取 ${pagesRead} 页）` : `取前 ${pages} 页`;
  const lines = [
    `# 七猫 · ${LIBRARY_LIST}`,
    "",
    `- 数据质量：${summary.quality}`,
    `- 有效条目：${books.length} / ${rawCount}`,
    `- 问题摘要：${summary.problems.length ? summary.problems.join("；") : "无"}`,
    `- 作品页链接：${summary.linked} / ${books.length}`,
    `- 来源：${libraryPageUrl(1)}`,
    `- 筛选：${LIBRARY_FILTER_NOTE}；${LIBRARY_SORT}排序，${range}；名次即页序，书库页没有热度数字`,
    `- 抓取时间：${now}`,
    `- 条目数：${books.length}`,
    "",
    "---",
    "",
  ];
  for (const b of books) {
    lines.push(`### #${b.rank} ${b.title}`);
    // 위치별 메타정보 집계: 작가, 장르(주분류가 없으면 하위 분류), 하위 분류 태그, 상태, 글자 수.
    const meta = [
      metaPart(b.author),
      metaPart(b.genre || b.subGenre),
      b.genre ? metaPart(b.subGenre) : "",
      metaPart(b.status) || "[待补]",
      b.words || "[待补]",
    ].filter(Boolean);
    lines.push(`*${meta.join(" · ")}*`);
    if (b.update) lines.push(`**最新更新：** ${b.update}`);
    if (b.url) lines.push(`[作品页](${b.url})`);
    const desc = cleanDesc(b.desc);
    if (desc) lines.push("", "**简介**", "", desc);
    lines.push("", "---", "");
  }
  return { content: lines.join("\n"), summary };
}

/**
 * 페이지를 넘기며 bookId 중복을 제거하고 첫 등장 순으로 연속 번호를 붙인다. 새 작품이 없는 페이지에서 멈춘다.
 * 첫 페이지 실패나 수집 0권이면 예외이며 파일을 쓰지 않는다. 이후 페이지 실패면 기존 페이지를 partial로 보존한다.
 */
async function scrapeLibrary(pages) {
  console.log(`\n→ 采集 七猫${LIBRARY_LIST}（${LIBRARY_FILTER_NOTE}，${LIBRARY_SORT}，前 ${pages} 页）...`);
  const books = [];
  const seen = new Set();
  const pageProblems = [];
  let invalid = 0;
  let pagesRead = 0;
  let maxPage = null;
  let requested = 0;
  const politeGet = async (url) => {
    if (requested++ > 0) sleep(LIBRARY_REQUEST_GAP_MS);
    return fetchQimaoHtml(url);
  };

  for (let page = 1; page <= pages; page++) {
    if (maxPage !== null && page > maxPage) {
      console.log(`  书库只有 ${maxPage} 页，停止翻页`);
      break;
    }
    let parsed;
    try {
      parsed = parseShukuPage(await politeGet(libraryPageUrl(page)));
      const problems = libraryPageProblems(parsed, page);
      if (problems.length) throw new Error(problems.join("；"));
    } catch (err) {
      const reason = `第 ${page} 页没取到：${err && err.message ? err.message : err}`;
      if (!books.length) throw new Error(reason);
      console.error(`  ✗ ${reason}，保留前 ${pagesRead} 页`);
      pageProblems.push(reason);
      break;
    }
    pagesRead++;
    if (page === 1) maxPage = parsed.maxPage;
    let fresh = 0;
    let duplicate = 0;
    for (const item of parsed.items) {
      if (!item.title || !item.author) {
        invalid++;
        continue;
      }
      const key = item.bookId || `${item.title}|${item.author}`;
      if (seen.has(key)) {
        duplicate++;
        continue;
      }
      seen.add(key);
      books.push({ ...item, rank: books.length + 1 });
      fresh++;
    }
    console.log(`  第 ${page} 页：新书 ${fresh} 本${duplicate ? `，跨页重复 ${duplicate} 本` : ""}`);
    if (!fresh) break;
  }

  if (!books.length) {
    throw new Error(`书库第 1 页一本书都没解析出来（页面条目 ${invalid} 个），页面可能改版`);
  }

  // 라이브러리는 하위 분류만 있다. 주분류는 분류 페이지 제목으로 조회하며 ID당 실행 중 한 번만 요청한다.
  const mainNames = new Map();
  for (const id of new Set(books.map((book) => book.mainId).filter(Boolean))) {
    try {
      mainNames.set(id, parseCategoryTitle(await politeGet(categoryUrl(id))));
    } catch (err) {
      console.error(`  ⚠ 主类 ${id} 没查到：${err && err.message ? err.message : err}`);
      mainNames.set(id, "");
    }
  }
  for (const book of books) book.genre = mainNames.get(book.mainId) || "";

  const { content, summary } = renderLibraryMarkdown({
    books,
    rawCount: books.length + invalid,
    pages,
    pagesRead,
    pageProblems,
  });
  console.log(`  ✓ 提取 ${books.length} 本（链接 ${summary.linked}/${books.length}，${summary.quality}）`);
  return { content, partialReasons: pageProblems };
}

// ---------------------------------------------------------------------------
// 주 처리 흐름
// ---------------------------------------------------------------------------

const args = process.argv.slice(2);
const PORT = parseInt(getArg(args, "--port") || "9222", 10);
const OUTDIR = getArg(args, "--outdir") || ".";
const CHANNEL = getArg(args, "--channel") || "male";
const RANKTYPE = getArg(args, "--type") || "hot";
const PERIOD = getArg(args, "--period") || "day";
const SOURCE = getArg(args, "--source") || "rank";
const PAGES_ARG = getArg(args, "--pages");

/** --x=value를 포함한 인자 명시 여부. 라이브러리 모드에서 순위 전용 인자를 거부하는 데 쓴다. */
function hasArg(argv, name) {
  return argv.some((arg) => arg === name || String(arg).startsWith(`${name}=`));
}

function scrapeRank(port, channelId, rankTypeId, periodId) {
  const ch = CHANNELS.find((c) => c.id === channelId);
  const rt = RANK_TYPES.find((r) => r.id === rankTypeId);
  const period = periodId ? PERIODS.find((p) => p.id === periodId) : null;
  if (!ch || !rt) {
    console.log("  ⚠ 未知频道或榜单类型");
    return null;
  }

  const periodLabel = period ? period.label : "";
  const url = rankUrl(channelId, rankTypeId, periodId);
  console.log(`\n→ 采集 七猫${ch.label}${rt.label}${periodLabel}...`);

  let books, urls, rawCount;
  try {
    ab(port, "open", url);
    sleep(3000);

    // 연결 자체 검사: CDP 미실행·리디렉션 시 빈 출력을 조용히 만들지 않고 대응 가능한 오류를 준다.
    const probe = probePage(port);
    if (!probe) {
      console.error(
        `  ✗ CDP 无响应。请确认已用 browser-cdp 启动 Chrome（端口 ${port}），且 agent-browser 可用。`
      );
      return null;
    }
    if (probe.host && probe.host.indexOf("qimao") === -1) {
      console.error(`  ✗ 当前页面非七猫（host=${probe.host}），可能被重定向，已跳过。`);
      return null;
    }
    const observed = extractObservedSelection(port);
    if (!selectionMatches(observed, channelId, rankTypeId, periodId)) {
      console.error(
        `  ✗ 页面实际榜单与请求不一致（请求 ${ch.tab}/${rt.label}/${periodLabel || "日榜"}，` +
        `实际 ${observed.channel || "?"}/${observed.rankType || "?"}/${observed.period || "?"}，path=${observed.path || probe.path || "?"}），已跳过。`
      );
      return null;
    }
    console.log(`  ✓ 已验证页面实际榜单：${observed.channel}/${observed.rankType}${observed.period ? "/" + observed.period : ""}`);

    // 스크롤해 더 로드한다.
    scrollLoad(port, 5);
    sleep(1000);

    // 텍스트로 작품 데이터를 파싱하고 DOM에서 링크를 얻는다.
    const rawBooks = extractBooksFromText(port);
    rawCount = rawBooks.length;
    books = rawBooks.filter(isUsableBook);
    urls = extractBookUrls(port);
  } catch (err) {
    console.error(`[qimao] ${ch.label}${rt.label}${periodLabel} 页面加载或提取出错: ${err.message}`);
    return null;
  }

  if (!books.length) {
    console.error(`[qimao] 采集失败：页面结构可能已变（选择器没匹配到数据），请检查榜单URL或更新选择器 (${RANK_URL} ${ch.label}${rt.label}${periodLabel})`);
    return null;
  }

  // 제목을 정규화해 공백 차이를 흡수한 뒤 URL과 맞춘다.
  const norm = (s) => (s || "").replace(/\s+/g, "");
  for (const b of books) {
    try {
      const matched = urls.find((u) => norm(u.title) === norm(b.title));
      if (matched) b.url = matched.url;
    } catch (matchErr) {
      console.error(`[qimao] URL匹配出错（#${b.rank} ${b.title}）: ${matchErr.message}`);
    }
  }

  const summary = summarizeQuality(books, rawCount);
  console.log(
    `  ✓ 提取 ${books.length} 本（链接 ${summary.linked}/${books.length}，热度 ${summary.heated}/${books.length}）`
  );
  return renderMarkdown(ch, rt, period, url, books, rawCount);
}

function buildTargets(channel, rankType, period, source = "rank") {
  // 라이브러리는 사이트 전체 하나가 유일한 대상이며 --type all에 넣지 않는다. Chrome 불필요, 순위와 무관한 필터를 사용한다.
  if (source === LIBRARY_ID) return [{ channel: "all", rankType: LIBRARY_ID, period: null }];
  const channels = channel === "all" ? CHANNELS.map((item) => item.id) : [channel];
  const rankTypes = rankType === "all" ? RANK_TYPES.map((item) => item.id) : [rankType];
  const targets = [];
  for (const channelId of channels) {
    for (const rankTypeId of rankTypes) {
      if (rankTypeId === "hot") {
        const periods = period === "all" ? PERIODS.map((item) => item.id) : [period];
        for (const periodId of periods) {
          targets.push({ channel: channelId, rankType: rankTypeId, period: periodId });
        }
      } else {
        targets.push({ channel: channelId, rankType: rankTypeId, period: null });
      }
    }
  }
  return targets;
}

function outputFilename(channelId, rankTypeId, periodId, date) {
  if (rankTypeId === LIBRARY_ID) return `七猫${LIBRARY_LIST}_${date}.md`;
  const channel = CHANNELS.find((item) => item.id === channelId);
  const rankType = RANK_TYPES.find((item) => item.id === rankTypeId);
  const period = periodId ? PERIODS.find((item) => item.id === periodId) : null;
  return `七猫${channel.label}${rankType.label}${period ? period.label : ""}_${date}.md`;
}

/** 네트워크·브라우저 실행 전에 모든 인자를 검증하고 대상·라이브러리 페이지 수를 반환한다. */
function resolvePlan() {
  if (SOURCE !== "rank" && SOURCE !== LIBRARY_ID) {
    throw new Error(`未知 --source: ${SOURCE}（rank / ${LIBRARY_ID}）`);
  }
  if (SOURCE === LIBRARY_ID) {
    const rankOnly = ["--channel", "--type", "--period"].filter((name) => hasArg(args, name));
    if (rankOnly.length) {
      throw new Error(
        `--source library 不能配 ${rankOnly.join("、")}：书库筛选固定为${LIBRARY_FILTER_NOTE}、${LIBRARY_SORT}`
      );
    }
    return { targets: buildTargets(null, null, null, LIBRARY_ID), pages: parseLibraryPages(PAGES_ARG) };
  }
  if (hasArg(args, "--pages")) {
    throw new Error("--pages 只用于 --source library");
  }
  if (CHANNEL !== "all" && !CHANNELS.some((channel) => channel.id === CHANNEL)) {
    throw new Error(`未知 --channel: ${CHANNEL}`);
  }
  if (RANKTYPE !== "all" && !RANK_TYPES.some((rank) => rank.id === RANKTYPE)) {
    throw new Error(`未知 --type: ${RANKTYPE}`);
  }
  if (PERIOD !== "all" && !PERIODS.some((period) => period.id === PERIOD)) {
    throw new Error(`未知 --period: ${PERIOD}`);
  }
  return { targets: buildTargets(CHANNEL, RANKTYPE, PERIOD), pages: 0 };
}

async function main() {
  const { targets, pages } = resolvePlan();
  let written = 0;
  let failed = 0;
  const partialReasons = [];

  for (const target of targets) {
    let content;
    if (target.rankType === LIBRARY_ID) {
      // 라이브러리는 대상 하나다. 전체 실패는 예외(exit 1, 파일 미작성), 페이지별 실패는 partialReasons에 담는다.
      const library = await scrapeLibrary(pages);
      content = library.content;
      partialReasons.push(...library.partialReasons);
    } else {
      content = scrapeRank(PORT, target.channel, target.rankType, target.period);
    }
    if (!content) {
      failed++;
      continue;
    }

    const filename = outputFilename(target.channel, target.rankType, target.period, localDateStamp());
    fs.mkdirSync(OUTDIR, { recursive: true });
    const filepath = path.join(OUTDIR, filename);
    fs.writeFileSync(filepath, content, "utf-8");
    written++;
    console.log(`  ✓ 已保存: ${filepath}`);
  }
  return {
    planned: targets.length,
    written,
    failed,
    partial: failed > 0 || partialReasons.length > 0,
    partialReasons,
  };
}

if (require.main === module) {
  runCli(main, "七猫采集");
}

module.exports = {
  extractBooksFromText,
  isUsableBook,
  cleanDesc,
  renderMarkdown,
  rankUrl,
  selectionMatches,
  buildTargets,
  outputFilename,
};
