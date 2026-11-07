#!/usr/bin/env node
/**
 * 치디안 중국어 사이트 순위 수집기. browser-cdp와 함께 사용하며 CDP 경로에서는 Chrome을 먼저 시작한다.
 * 기본은 CDP 없이 m.qidian.com SSR pageContext JSON을 읽어 PC 보안 차단을 피한다. 모바일이 안 되면 Chrome CDP의 PC 페이지로 대체한다.
 * 출력 Markdown은 aggregate-rank.js 머리 주석 형식이다.
 * 사용법:
 *   node qidian-rank-scraper.js --type hotsales               # 베스트셀러
 *   node qidian-rank-scraper.js --type yuepiao                # 월표
 *   node qidian-rank-scraper.js --type signnewbook            # 계약 작가 신작
 *   node qidian-rank-scraper.js --type pubnewbook             # 일반 작가 신작
 *   node qidian-rank-scraper.js --type newauthor              # 신인 작가 신작
 *   node qidian-rank-scraper.js --type newsign                # 신인 계약 신작
 *   node qidian-rank-scraper.js --type recom                  # 창작 추천
 *   node qidian-rank-scraper.js --type sanjiang               # 삼강 추천(/sanjiang/, /rank/ 아님)
 *   node qidian-rank-scraper.js --type all                    # 전체
 *   node qidian-rank-scraper.js --type hotsales --mode mobile # 모바일 SSR만
 *   node qidian-rank-scraper.js --type hotsales --mode cdp    # 대체 CDP/PC만
 *   node qidian-rank-scraper.js --type library [--pages 3]    # 라이브러리 인기 신작, CDP 전용·all 제외
 * 라이브러리 인기 신작은 남성·연재·30만 자 미만·3일 내 갱신을 인기순으로 정렬한 전체 작품 필터다.
 * 앞 N페이지를 읽는다(--pages 1–10, 기본 3; library에만 유효하며 다른 순위에 주면 오류).
 * PC 직접 HTTPS는 보안 차단되므로 CDP로만 연다. 글자 수는 보호 글꼴 해석으로, 총 추천·계약·유료 정보는 m.qidian.com 작품 페이지로 보충한다.
 * 사전 조건: 기본 mobile/auto에는 library 외에 Chrome이 필요 없다.
 * cdp와 library는 다음을 먼저 실행한다: node {SKILL_DIR}/browser-cdp/scripts/setup-cdp-chrome.js 9222
 */

const fs = require("fs");
const https = require("https");
const path = require("path");
const { ab, sleep, evalJSON, scrollLoad, getArg, localDateStamp, runCli } = require("./cdp-utils");

const PC_BASE_URL = "https://www.qidian.com/rank";
const MOBILE_BASE_URL = "https://m.qidian.com";

/** CAPTCHA 자동 재시도 최대 횟수. */
const MAX_CAPTCHA_RETRIES = 3;
/** 사용자 CAPTCHA 수동 해결을 기다리는 최대 초. */
const MAX_CAPTCHA_WAIT_SEC = 120;
/** CAPTCHA 해제 확인 간격(밀리초). */
const CAPTCHA_POLL_INTERVAL = 5000;

const MOBILE_HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) " +
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
  Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
  "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
  "Accept-Encoding": "identity",
};

const RANK_TYPES = [
  { id: "hotsales", label: "畅销榜", mobilePath: "/rank/hotsales/" },
  { id: "yuepiao", label: "月票榜", mobilePath: "/rank/yuepiao/" },
  {
    id: "signnewbook",
    label: "签约作者新书榜",
    mobilePath: "/rank/sign/",
    mobileLabel: "签约榜",
  },
  {
    id: "pubnewbook",
    label: "公众作者新书榜",
    mobilePath: "/rank/newbook/",
    mobileLabel: "新书榜",
  },
  { id: "newauthor", label: "新人作者新书榜", mobilePath: "/rank/newauthor/", mobileLabel: "新人榜" },
  {
    id: "newsign",
    label: "新人签约新书榜",
    mobilePath: "/rank/sign/",
    mobileLabel: "签约榜",
  },
  { id: "recom", label: "原创推荐榜", mobilePath: "/rank/rec/", mobileLabel: "推荐榜" },
  { id: "readindex", label: "阅读指数榜", mobilePath: "/rank/readindex/" },
  {
    id: "collect",
    label: "收藏榜",
    mobilePath: "/rank/newfans/",
    mobileLabel: "书友榜（移动端替代）",
  },
  {
    id: "sanjiang",
    label: "三江推荐",
    baseUrl: "https://www.qidian.com/sanjiang/",
    mobilePath: "/sanjiang/",
  },
  // 가상 순위: 전체 작품 필터의 페이지 넘김. CDP 전용이며 Chrome이 필요 없는 기본 --type all에는 넣지 않는다.
  // 목록명에 ‘新书’를 넣어 집계 시 신작 순위 열로 보낸다.
  {
    id: "library",
    label: "男频书库人气新书",
    baseUrl: "https://www.qidian.com/all/action0-size1-update1/",
    library: true,
  },
];

// ---------------------------------------------------------------------------
// 페이지 추출
// ---------------------------------------------------------------------------

/**
 * 치디안 SSR 순위의 작품 목록을 추출한다. .book-img-text ul > li 안의 구조:
 *   h2 > a           → 제목+링크
 *   p.author         → 작가 | 장르·하위 장르 | 상태
 *   p.intro          → 소개
 *   p.update > a+span → 최신 장+날짜
 */
function extractBookList(port) {
  const js =
    "JSON.stringify((()=>{" +
    "var items=[];" +
    "function metrics(text){" +
    "  var flat=String(text||'').replace(/\\s+/g,' ').trim();" +
    "  var words=flat.match(/([\\d.]+\\s*万?字)/);" +
    "  var total=flat.match(/([\\d.,]+\\s*万?)\\s*总推荐/);" +
    "  var signing=flat.match(/(?:^|\\s|·)(已签约|未签约|签约)(?=\\s|·|$)/);" +
    "  var pricing=flat.match(/(?:^|\\s|·)(VIP|免费)(?=\\s|·|$)/i);" +
    "  return {words:words?words[1].replace(/\\s+/g,''):'',totalRecommendations:total?total[1]:'',signing:signing?signing[1]:'',pricing:pricing?pricing[1].toUpperCase()==='VIP'?'VIP':pricing[1]:''};" +
    "}" +
    "var lis=document.querySelectorAll('.book-img-text ul li');" +
    "if(!lis.length){" +
    // 대안: H2 링크로 찾는다.
    "  var h2s=document.querySelectorAll('h2 a[href*=\"/book/\"]');" +
    "  h2s.forEach(function(a,idx){" +
    "    var c=a.parentElement;" +
    "    for(var j=0;j<3;j++){if(c.parentElement)c=c.parentElement}" +
    "    var text=c.innerText||'';" +
    "    var metric=metrics(text);" +
    "    var href=a.getAttribute('href')||a.href||'';" +
    "    var url=href?(href.indexOf('http')===0?href:'https:'+href):'';" +
    "    items.push({rank:idx+1,title:a.textContent.trim(),url:url,author:'',genre:'',status:'',words:metric.words,rankValue:'',totalRecommendations:metric.totalRecommendations,signing:metric.signing,pricing:metric.pricing,descText:'',updateText:text.replace(/\\s+/g,' ').trim().substring(0,300)})" +
    "  });" +
    "  return items" +
    "}" +
    "lis.forEach(function(li,idx){" +
    "  var titleEl=li.querySelector('h2 a');" +
    "  if(!titleEl)return;" +
    "  var title=titleEl.textContent.trim();" +
    "  var href=titleEl.getAttribute('href')||titleEl.href||'';" +
    "  var url=href?(href.indexOf('http')===0?href:'https:'+href):'';" +
    // 작가: p.author > a.name
    "  var authorEl=li.querySelector('p.author a.name');" +
    "  var author=authorEl?authorEl.textContent.trim():'';" +
    // 장르: p.author > a(.name과 .go-sub-type 제외).
    "  var genreEls=li.querySelectorAll('p.author a');" +
    "  var genre='';var subGenre='';" +
    "  genreEls.forEach(function(a){" +
    "    if(a.classList.contains('name'))return;" +
    "    if(!genre){genre=a.textContent.trim()}else if(!subGenre){subGenre=a.textContent.trim()}" +
    "  });" +
    // 상태: p.author > span:last-child
    "  var statusEl=li.querySelector('p.author span');" +
    "  var status=statusEl?statusEl.textContent.trim():'';" +
    // 소개: p.intro
    "  var introEl=li.querySelector('p.intro');" +
    "  var descText=introEl?introEl.textContent.trim():'';" +
    // 갱신: p.update
    "  var updateEl=li.querySelector('p.update');" +
    "  var updateText=updateEl?updateEl.textContent.replace(/\\s+/g,' ').trim():'';" +
    "  var metric=metrics(li.innerText||'');" +
    "  if(title){" +
    "    items.push({rank:idx+1,title:title,url:url,author:author,genre:genre+(subGenre?'·'+subGenre:''),status:status,words:metric.words,rankValue:'',totalRecommendations:metric.totalRecommendations,signing:metric.signing,pricing:metric.pricing,descText:descText,updateText:updateText})" +
    "  }" +
    "});" +
    "return items" +
    "})())";
  return evalJSON(port, js) || [];
}

/** 상세 페이지에서 태그·소개를 추출한다. */
function extractDetail(port) {
  const js =
    "JSON.stringify((()=>{" +
    "var tags=Array.from(document.querySelectorAll('[class*=\"tag\"] a,[class*=\"label\"] a')).map(function(a){return a.textContent.trim()});" +
    "var intro=document.querySelector('[class*=\"intro\"],[class*=\"summary\"],[class*=\"desc\"]');" +
    "var introText=intro?intro.textContent.trim():'';" +
    "var update=document.querySelector('[class*=\"update\"],[class*=\"latest\"]');" +
    "var updateText=update?update.textContent.trim():'';" +
    "var info=document.querySelector('.book-info,[class*=\"book-info\"],[class*=\"bookInfo\"]');" +
    "var infoText=info?(info.innerText||info.textContent||''):(document.body?document.body.innerText||'':'');" +
    "var words=infoText.match(/([\\d.]+\\s*万?字)/);" +
    "var total=infoText.match(/([\\d.,]+\\s*万?)\\s*总推荐/);" +
    "var signing=infoText.match(/(?:^|\\s|·)(已签约|未签约|签约)(?=\\s|·|$)/);" +
    "var pricing=infoText.match(/(?:^|\\s|·)(VIP|免费)(?=\\s|·|$)/i);" +
    "return {tags:tags,intro:introText,update:updateText,words:words?words[1].replace(/\\s+/g,''):'',totalRecommendations:total?total[1]:'',signing:signing?signing[1]:'',pricing:pricing?pricing[1].toUpperCase()==='VIP'?'VIP':pricing[1]:''}" +
    "})())";
  return evalJSON(port, js);
}

/**
 * 현재 페이지의 CAPTCHA·보안 검증 차단 여부를 확인한다.
 * 일반적인 특징은 CAPTCHA 키워드가 있거나 순위 DOM 요소가 없는 것이다.
 * @returns {{ blocked: boolean, reason: string } | null} 차단 시 사유 객체, 아니면 null
 */
function captchaCheckJS() {
  return (
    "JSON.stringify((()=>{" +
    // 작품 링크가 무더기로 있으면 정상 목록이다. 라이브러리 첫 3000자에는 소개 전문과 장 제목이 있어
    // 작품 속 ‘验证’, ‘拖动’ 같은 단어를 차단으로 보면 불필요한 재시도·120초 수동 검증 대기가 발생한다.
    "if(document.querySelectorAll('a[href*=\"/book/\"]').length>=5)return {blocked:false,reason:''};" +
    "var bodyText=document.body?(document.body.innerText||'').substring(0,3000):'';" +
    "var lower=bodyText.toLowerCase();" +
    "var keywords=['验证','captcha','verify','安全验证','滑块','拖动','请完成验证'," +
    "'混元','人机验证','异常请求','访问验证','操作频繁','请求过于频繁','waf','请稍后再试'];" +
    "for(var i=0;i<keywords.length;i++){" +
    "  if(lower.indexOf(keywords[i])>-1){" +
    "    return {blocked:true,reason:keywords[i]};" +
    "  }" +
    "}" +
    // li[data-rid]는 전체 작품 필터 항목이다. 현재 .book-img-text 안에 있지만
    // 개편 후 차단으로 오판해 3회 재시도와 120초 수동 대기를 낭비하지 않도록 명시한다.
    "var hasContent=document.querySelector('.book-img-text ul li,.rank-body,.rank-list,.book-img-text,li[data-rid]');" +
    "if(!hasContent){" +
    "  return {blocked:true,reason:'页面无榜单内容(可能被拦截)'};" +
    "}" +
    "return {blocked:false,reason:''};" +
    "})())"
  );
}

function isCaptchaPage(port) {
  const result = evalJSON(port, captchaCheckJS());
  return result && result.blocked === true ? result : null;
}

/**
 * URL을 열고 로딩을 기다리며 CAPTCHA 차단에 대응한다.
 * 1. 페이지를 정상 로드한다.
 * 2. CAPTCHA가 감지되면 점증 대기 후 새로고침한다(최대 MAX_CAPTCHA_RETRIES회).
 * 3. 계속 차단되면 Chrome CDP 창에서 사용자가 수동 검증하도록 안내하고 해제·시간 초과까지 확인한다.
 * @returns {boolean} true=준비 완료, false=CAPTCHA 통과 불가
 */
function openWithCaptchaHandling(port, url) {
  for (let attempt = 1; attempt <= MAX_CAPTCHA_RETRIES; attempt++) {
    ab(port, "open", url);
    // 처음 3초, 이후 매번 2초씩 더 기다린다.
    sleep(3000 + (attempt - 1) * 2000);

    const captcha = isCaptchaPage(port);
    if (!captcha) {
      return true;
    }
    console.log(`  ⚠ 检测到安全拦截 (${captcha.reason})，第 ${attempt}/${MAX_CAPTCHA_RETRIES} 次重试...`);
    // 늘어난 시간만큼 기다린 후 재시도한다.
    sleep(attempt * 5000);
  }

  // 자동 재시도가 모두 실패하면 사용자 수동 처리를 기다린다.
  console.log(`  ⚠ 自动重试未通过验证码，请在 Chrome CDP 窗口手动完成验证`);
  console.log(`  ⏳ 等待手动验证（最长 ${MAX_CAPTCHA_WAIT_SEC} 秒）...`);

  const startTime = Date.now();
  while (Date.now() - startTime < MAX_CAPTCHA_WAIT_SEC * 1000) {
    sleep(CAPTCHA_POLL_INTERVAL);
    // 새로고침해 CAPTCHA 해제 여부를 확인한다.
    ab(port, "open", url);
    sleep(3000);
    const captcha = isCaptchaPage(port);
    if (!captcha) {
      console.log(`  ✓ 验证码已解除，继续采集`);
      return true;
    }
    const elapsed = Math.round((Date.now() - startTime) / 1000);
    process.stdout.write(`  等待中... (${elapsed}s)\r`);
  }
  console.log(`  ✗ 等待超时，验证码仍未解除`);
  return false;
}

// ---------------------------------------------------------------------------
// 모바일 SSR 추출(기본 경로).
// ---------------------------------------------------------------------------

function mobileUrl(pathname) {
  if (!pathname) return "";
  return pathname.startsWith("http") ? pathname : `${MOBILE_BASE_URL}${pathname}`;
}

function fetchText(url, redirects = 3) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: MOBILE_HEADERS, timeout: 15000 }, (res) => {
      if (
        redirects > 0 &&
        res.statusCode >= 300 &&
        res.statusCode < 400 &&
        res.headers.location
      ) {
        res.resume();
        const nextUrl = new URL(res.headers.location, url).toString();
        fetchText(nextUrl, redirects - 1).then(resolve, reject);
        return;
      }

      let body = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        body += chunk;
      });
      res.on("end", () => {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(`HTTP ${res.statusCode}`));
          return;
        }
        resolve(body);
      });
    });

    req.on("timeout", () => {
      req.destroy(new Error("request timeout"));
    });
    req.on("error", reject);
  });
}

function extractMobilePageContext(html) {
  const m = html.match(
    /<script[^>]+id=["']vite-plugin-ssr_pageContext["'][^>]*>([\s\S]*?)<\/script>/i
  );
  if (!m) return null;
  try {
    return JSON.parse(m[1]);
  } catch (e) {
    console.log(`  ⚠ 移动端 pageContext JSON 解析失败: ${e.message}`);
    return null;
  }
}

function normalizeMobileBook(record, idx) {
  const title = record.bName || record.bookName || "";
  const bid = record.bid || record.bookId || "";
  const genre = [record.cat, record.subCat].filter(Boolean).join("·");
  const first = (...keys) => {
    for (const key of keys) {
      const value = record[key];
      if (value !== undefined && value !== null && value !== "") return String(value);
    }
    return "";
  };

  return {
    rank: record.rankNum || idx + 1,
    title,
    url: bid ? `${MOBILE_BASE_URL}/book/${bid}/` : "",
    author: record.bAuth || record.author || "",
    genre,
    status: first("status", "bookStatus", "serializationStatus"),
    words: first("cnt", "wordCount", "words", "wordCnt"),
    rankValue: first("rankCnt", "rankValue"),
    totalRecommendations: first(
      "totalRecommend",
      "totalRecommendations",
      "recommendCount",
      "totalRec"
    ),
    signing: first("signStatus", "signing", "contractStatus"),
    pricing: first("vipStatus", "pricing", "chargeStatus"),
    descText: record.desc || "",
    updateText: "",
  };
}

/** 소개 공백을 압축하고 100자 초과 시 문장 끝에서 자르는 것을 우선한다. */
function cleanDesc(raw) {
  const desc = String(raw || "").replace(/\s+/g, " ").trim();
  if (desc.length <= 100) return desc;
  const cut = desc.slice(0, 100);
  const sentence = cut.match(/^[\s\S]*[。！？]/);
  return (sentence ? sentence[0] : cut) + "...";
}

/** 순위 항목의 장르·글자 수 누락 비율이 이 값을 넘으면 数据质量를 문제 있음으로 표시한다(대개 페이지 개편). */
const RANK_FIELD_MISSING_RATIO = 0.5;

/** 순위의 ‘数据质量’, ‘问题摘要’ 두 행. 라이브러리 신작은 별도 계산 후 extraLines로 전달한다. */
function rankQualityLines(books) {
  const problems = [];
  for (const [field, label] of [["genre", "题材"], ["words", "字数"]]) {
    const missing = books.filter((b) => !b[field]).length;
    if (missing > books.length * RANK_FIELD_MISSING_RATIO) problems.push(`${label}缺失 ${missing} / ${books.length} 条`);
  }
  return [
    `- 数据质量：${problems.length ? "[存在问题]" : "[OK]"}`,
    `- 问题摘要：${problems.length ? problems.join("；") : "无"}`,
  ];
}

function renderMarkdown(rt, books, url, sourceMode, extraLines = []) {
  const now = new Date().toISOString();
  const quality = extraLines.some((line) => /^- 数据质量：/.test(line)) ? [] : rankQualityLines(books);
  const lines = [
    `# 起点 · ${rt.label}`,
    "",
    `- 来源：${url}`,
    `- 抓取方式：${sourceMode}`,
    `- 抓取时间：${now}`,
    `- 条目数：${books.length}`,
    ...extraLines,
    ...quality,
    "",
    "---",
    "",
  ];

  for (let i = 0; i < books.length; i++) {
    const b = books[i];
    lines.push(`## #${b.rank || i + 1} ${b.title}`);
    const meta = [b.author, b.genre, b.status].filter(Boolean).join(" · ");
    if (meta) lines.push(`*${meta}*`);
    const required = (value) =>
      value === undefined || value === null || value === "" ? "[待补]" : String(value);
    lines.push(`**字数：${required(b.words)}**`);
    if (b.rankValue) lines.push(`**榜单值：${b.rankValue}**`);
    // 라이브러리 신작의 총 추천은 수천~수만이라 월표·베스트셀러의 기존 작품과 섞으면 장르 인기도 중앙값이 두 자릿수 규모로 낮아진다.
    // 다른 행 이름으로 별도 표시해 인기도 기준으로 집계하지 않는다. 라이브러리 순서는 인기 순위이며 숫자는 원시 항목에 남겨 표본 검토에 쓴다.
    if (b.library) lines.push(`**新书总推荐：${required(b.newBookRecom)}**`);
    else lines.push(`**总推荐：${required(b.totalRecommendations)}**`);
    lines.push(`**签约：${required(b.signing)}**`);
    lines.push(`**收费模式：${required(b.pricing)}**`);
    if (b.updateText) lines.push(`**最新更新：** ${b.updateText}`);
    if (b.tags?.length) lines.push(`**标签：** ${b.tags.join("、")}`);
    if (b.url) lines.push(`[作品页](${b.url})`);
    const desc = cleanDesc(b.descText);
    if (desc) {
      lines.push("");
      lines.push("**简介**");
      lines.push("");
      lines.push(desc);
    }
    lines.push("", "---", "");
  }

  return lines.join("\n");
}

async function scrapeRankMobile(rankTypeId) {
  const rt = RANK_TYPES.find((r) => r.id === rankTypeId);
  if (!rt) {
    console.log(`  ⚠ 未知榜单类型: ${rankTypeId}`);
    return null;
  }
  if (!rt.mobilePath) {
    console.log(`  ⚠ 榜单 ${rankTypeId} 暂无移动端 SSR 路径`);
    return null;
  }

  const url = mobileUrl(rt.mobilePath);
  console.log(`\n→ 采集 起点${rt.label}（移动端 SSR）...`);
  console.log(`  URL: ${url}`);

  const html = await fetchText(url);
  const pageContext = extractMobilePageContext(html);
  const pageData = pageContext?.pageContext?.pageProps?.pageData;
  const records = pageData?.records || [];
  const books = records.map(normalizeMobileBook).filter((b) => b.title);

  if (!books.length) {
    console.log("  ⚠ 移动端 SSR 未提取到书籍");
    return null;
  }

  console.log(`  ✓ 提取 ${books.length} 本`);

  const extraLines = [];
  if (rt.mobileLabel && rt.mobileLabel !== rt.label) {
    extraLines.push(`- 移动端实际榜单：${rt.mobileLabel}`);
  }
  if (FETCH_DETAIL) {
    extraLines.push("- 说明：移动端 SSR 已包含简介；--detail 在 mobile/auto 模式下不会额外打开详情页。");
  }

  return renderMarkdown(rt, books, url, "mobile-ssr", extraLines);
}

// ---------------------------------------------------------------------------
// 라이브러리 인기 신작(--type library): 전체 작품 필터 페이지 넘김 + 보호 글꼴 해석 + 모바일 상세 필드 보충.
// ---------------------------------------------------------------------------

const LIBRARY_DEFAULT_PAGES = 3;
const LIBRARY_MAX_PAGES = 10;
/** 실제 페이지에서 선택되어 있어야 할 필터. 맞지 않으면 인기 신작 페이지로 저장하지 않는다. */
const LIBRARY_SITE = "男生";
const LIBRARY_FILTERS = ["连载", "30万字以下", "三日内"];
const LIBRARY_SORT = "人气排序";
/** 작품별 모바일 상세 요청 간격(밀리초). */
const LIBRARY_DETAIL_GAP_MS = 400;
/** 상세 실패 비율이 이 값을 넘으면 문제 요약에 명시한다. */
const LIBRARY_DETAIL_FAIL_RATIO = 0.5;

const FONT_HOST = "qdfepccdn.qidian.com";
const FONT_PATH_RE = /^\/gtimg\/qd_anti_spider\/([A-Za-z0-9]+)\.ttf$/;
const FONT_MAX_BYTES = 2 * 1024 * 1024;
const FONT_HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  Accept: "*/*",
  "Accept-Encoding": "identity",
  Referer: "https://www.qidian.com/",
};

/** 글리프 이름 → 문자. zero..nine과 period만 인식하며 나머지는 해석 불가다. */
const GLYPH_CHARS = {
  zero: "0",
  one: "1",
  two: "2",
  three: "3",
  four: "4",
  five: "5",
  six: "6",
  seven: "7",
  eight: "8",
  nine: "9",
  period: ".",
};
/** post 2.0에서 인덱스 < 258은 Mac 표준 글리프 순서다. 필요한 것만 나열한다. */
const MAC_STANDARD_GLYPHS = {
  17: "period",
  19: "zero",
  20: "one",
  21: "two",
  22: "three",
  23: "four",
  24: "five",
  25: "six",
  26: "seven",
  27: "eight",
  28: "nine",
};
/** 잘못된 글꼴이 Unicode 전체를 범위로 주지 못하도록 cmap당 펼칠 코드 포인트 수를 제한한다. */
const CMAP_MAX_ENTRIES = 70000;

/**
 * 보호된 글자 수의 코드 포인트(탕구트 문자·사용자 정의 영역). 출력에 이 문자를 남기지 않는다.
 * 해석하지 못하면 깨진 문자를 보고서에 쓰지 않고 [待补]로 표시한다.
 */
const CIPHER_CHARS_RE = /[\uE000-\uF8FF\u{17000}-\u{18D8F}\u{F0000}-\u{10FFFF}]/gu;

function stripCipherChars(value) {
  return String(value === undefined || value === null ? "" : value)
    .replace(CIPHER_CHARS_RE, "")
    .replace(/\s+/g, " ")
    .trim();
}

function libraryPageUrl(page) {
  const base = RANK_TYPES.find((r) => r.library).baseUrl;
  return page === 1 ? base : base.replace(/\/$/, `-page${page}/`);
}

/** --pages 검증: 1..LIBRARY_MAX_PAGES 정수만 허용하고 미지정이면 기본값이다. */
function parseLibraryPages(raw, given) {
  if (!given) return LIBRARY_DEFAULT_PAGES;
  const text = raw === null || raw === undefined ? "" : String(raw).trim();
  const n = /^\d+$/.test(text) ? Number(text) : NaN;
  if (!Number.isInteger(n) || n < 1 || n > LIBRARY_MAX_PAGES) {
    throw new Error(`未知 --pages: ${text || "（空）"}（取 1-${LIBRARY_MAX_PAGES} 的整数）`);
  }
  return n;
}

/** 브라우저 실행·네트워크 전에 라이브러리 인자를 빠르게 검증한다. 넘길 페이지 수를 반환하며 다른 순위는 null이다. */
function validateLibraryArgs(rankType, mode, pagesRaw, pagesGiven) {
  const rt = RANK_TYPES.find((r) => r.id === rankType);
  if (!rt || !rt.library) {
    if (pagesGiven) {
      throw new Error(`--pages 只用于 --type library（当前 --type ${rankType}）`);
    }
    return null;
  }
  if (mode === "mobile") {
    throw new Error("--type library 不支持 --mode mobile：书库筛选页只能用 Chrome（CDP）打开");
  }
  return parseLibraryPages(pagesRaw, pagesGiven);
}

// ---- 보호 글꼴(qd_anti_spider): 순수 Node로 TrueType cmap + post 파싱 ----

function readCmapTable(cmap) {
  const numTables = cmap.readUInt16BE(2);
  const result = new Map();
  const put = (cp, gid) => {
    if (gid && !result.has(cp)) result.set(cp, gid);
    if (result.size > CMAP_MAX_ENTRIES) throw new Error("cmap 码点过多");
  };
  for (let i = 0; i < numTables; i++) {
    const rec = 4 + i * 8;
    const offset = cmap.readUInt32BE(rec + 4);
    const format = cmap.readUInt16BE(offset);
    if (format === 12) {
      const groups = cmap.readUInt32BE(offset + 12);
      for (let g = 0; g < groups; g++) {
        const at = offset + 16 + g * 12;
        const start = cmap.readUInt32BE(at);
        const end = cmap.readUInt32BE(at + 4);
        const startGid = cmap.readUInt32BE(at + 8);
        if (end < start || end - start > CMAP_MAX_ENTRIES) throw new Error("cmap 区间异常");
        for (let cp = start; cp <= end; cp++) put(cp, startGid + (cp - start));
      }
    } else if (format === 4) {
      const segX2 = cmap.readUInt16BE(offset + 6);
      const seg = segX2 / 2;
      const endAt = offset + 14;
      const startAt = endAt + segX2 + 2;
      const deltaAt = startAt + segX2;
      const rangeAt = deltaAt + segX2;
      for (let s = 0; s < seg; s++) {
        const end = cmap.readUInt16BE(endAt + s * 2);
        const start = cmap.readUInt16BE(startAt + s * 2);
        const delta = cmap.readInt16BE(deltaAt + s * 2);
        const rangeOffset = cmap.readUInt16BE(rangeAt + s * 2);
        if (start === 0xffff || end < start) continue;
        for (let cp = start; cp <= end; cp++) {
          let gid;
          if (rangeOffset === 0) {
            gid = (cp + delta) & 0xffff;
          } else {
            gid = cmap.readUInt16BE(rangeAt + s * 2 + rangeOffset + (cp - start) * 2);
            if (gid) gid = (gid + delta) & 0xffff;
          }
          put(cp, gid);
        }
      }
    }
  }
  return result;
}

function readPostGlyphNames(post) {
  const version = post.readUInt32BE(0);
  if (version !== 0x00020000) {
    throw new Error(`post 表版本 0x${version.toString(16)} 不带字形名`);
  }
  const numGlyphs = post.readUInt16BE(32);
  const indices = [];
  for (let i = 0; i < numGlyphs; i++) indices.push(post.readUInt16BE(34 + i * 2));
  const extra = [];
  let at = 34 + numGlyphs * 2;
  while (at < post.length) {
    const len = post.readUInt8(at);
    if (at + 1 + len > post.length) break;
    extra.push(post.toString("latin1", at + 1, at + 1 + len));
    at += 1 + len;
  }
  return indices.map((idx) => (idx < 258 ? MAC_STANDARD_GLYPHS[idx] || "" : extra[idx - 258] || ""));
}

/**
 * 보호 글꼴을 파싱해 Map<코드포인트, "0".."9"|".">를 반환한다.
 * magic·표 범위·cmap/post 누락·post 2.0 불일치 등 구조 오류는 모두 예외로 처리해 호출자가 [待补]를 쓰게 한다.
 */
function parseAntiSpiderFont(buf) {
  if (!Buffer.isBuffer(buf) || buf.length < 12) throw new Error("字体文件太短");
  const magic = buf.readUInt32BE(0);
  if (magic !== 0x00010000 && magic !== 0x74727565 && magic !== 0x4f54544f) {
    throw new Error("不是 TrueType/OpenType 字体");
  }
  const numTables = buf.readUInt16BE(4);
  if (12 + numTables * 16 > buf.length) throw new Error("字体表目录越界");
  const tables = {};
  for (let i = 0; i < numTables; i++) {
    const rec = 12 + i * 16;
    const tag = buf.toString("latin1", rec, rec + 4);
    const offset = buf.readUInt32BE(rec + 8);
    const length = buf.readUInt32BE(rec + 12);
    if (offset + length > buf.length) throw new Error(`字体表 ${tag.trim()} 越界`);
    // subarray 뷰는 표 길이를 벗어나 읽으면 Buffer 자체가 RangeError를 던진다.
    tables[tag] = buf.subarray(offset, offset + length);
  }
  if (!tables.cmap || !tables.post) throw new Error("字体缺 cmap 或 post 表");
  const names = readPostGlyphNames(tables.post);
  const map = new Map();
  for (const [cp, gid] of readCmapTable(tables.cmap)) {
    const name = names[gid];
    if (name && Object.prototype.hasOwnProperty.call(GLYPH_CHARS, name)) {
      map.set(cp, GLYPH_CHARS[name]);
    }
  }
  if (!map.size) throw new Error("字体里没有可识别的数字字形");
  return map;
}

/**
 * 글꼴 매핑으로 암호화 코드 포인트를 글자 수로 바꾼다. 예: [0x187B9, ...] + 万字 → 26.14万字.
 * 하나라도 매핑이 없거나 결과가 숫자가 아니거나 단위가 불명확하면 빈 문자열을 반환하고 호출자가 [待补]를 쓴다.
 */
function decodeLibraryWords(codes, unit, fontMap) {
  if (!(fontMap instanceof Map) || !Array.isArray(codes) || !codes.length) return "";
  if (unit !== "万字" && unit !== "字") return "";
  let digits = "";
  for (const code of codes) {
    const ch = fontMap.get(Number(code));
    if (ch === undefined) return "";
    digits += ch;
  }
  if (!/^\d+(\.\d+)?$/.test(digits)) return "";
  return `${digits}${unit}`;
}

function fontUrlAllowed(url) {
  try {
    const u = new URL(url);
    return u.protocol === "https:" && u.hostname === FONT_HOST && FONT_PATH_RE.test(u.pathname);
  } catch {
    return false;
  }
}

/** qdfepccdn.qidian.com에서만 글꼴을 받는다. 제한 15초, 리디렉션 없음, 크기 제한. */
function fetchFontBuffer(url) {
  return new Promise((resolve, reject) => {
    if (!fontUrlAllowed(url)) {
      reject(new Error(`字体地址不在白名单：${url}`));
      return;
    }
    const req = https.get(url, { headers: FONT_HEADERS, timeout: 15000 }, (res) => {
      if (res.statusCode < 200 || res.statusCode >= 300) {
        res.resume();
        reject(new Error(`字体下载 HTTP ${res.statusCode}`));
        return;
      }
      const chunks = [];
      let size = 0;
      res.on("data", (chunk) => {
        size += chunk.length;
        if (size > FONT_MAX_BYTES) {
          req.destroy(new Error("字体文件过大"));
          return;
        }
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
      });
      res.on("end", () => resolve(Buffer.concat(chunks)));
      res.on("error", reject);
    });
    req.on("timeout", () => {
      req.destroy(new Error("字体下载超时"));
    });
    req.on("error", reject);
  });
}

/** 같은 글꼴은 실행당 한 번만 다운로드·파싱한다. 실패도 캐시해 반복 요청을 피한다. */
const libraryFontCache = new Map();

function loadLibraryFont(name, url) {
  if (!libraryFontCache.has(name)) {
    const task = (async () => {
      const m = fontUrlAllowed(url) ? new URL(url).pathname.match(FONT_PATH_RE) : null;
      if (!m || m[1] !== name) throw new Error(`字体 ${name} 没有可用的下载地址`);
      return parseAntiSpiderFont(await fetchFontBuffer(url));
    })().then(
      (map) => ({ map, error: "" }),
      (err) => ({ map: null, error: err && err.message ? err.message : String(err) })
    );
    libraryFontCache.set(name, task);
  }
  return libraryFontCache.get(name);
}

// ---- 목록 페이지: 브라우저 추출 + Node 검증·정리 ----

/**
 * 라이브러리 페이지 추출 함수를 toString()으로 eval에 넣는다. 모듈 범위를 참조하거나 백틱을 포함하면 안 된다.
 * 글자 수는 해당 p.update의 클래스 있는 암호화 span에서만 코드 포인트를 얻고 최신 장은 링크 title에서 얻는다.
 * @font-face와 암호문이 섞인 p.update 전체 텍스트는 읽지 않는다.
 */
function qdLibraryPageSnapshot(qdLibraryPage) {
  function txt(el) {
    return el ? String(el.textContent || "").replace(/\s+/g, " ").trim() : "";
  }
  var panels = Array.prototype.filter.call(document.querySelectorAll(".select-list"), function (el) {
    return el.offsetParent !== null;
  });
  var filters = panels.length ? Array.prototype.map.call(panels[0].querySelectorAll(".act"), txt) : [];
  var fontUrls = {};
  Array.prototype.forEach.call(document.querySelectorAll("style"), function (st) {
    var re = /https:\/\/qdfepccdn\.qidian\.com\/gtimg\/qd_anti_spider\/([A-Za-z0-9]+)\.ttf/g;
    var m;
    while ((m = re.exec(st.textContent || ""))) fontUrls[m[1]] = m[0];
  });
  var pagerMax = 0;
  Array.prototype.forEach.call(document.querySelectorAll(".lbf-pagination-item-list a[data-page]"), function (a) {
    var n = parseInt(a.getAttribute("data-page"), 10);
    if (n > pagerMax) pagerMax = n;
  });
  var items = Array.prototype.map.call(document.querySelectorAll("li[data-rid]"), function (li) {
    var titleEl = li.querySelector("h2 a");
    var href = titleEl ? titleEl.getAttribute("href") || "" : "";
    var idMatch = href.match(/\/book\/(\d+)/);
    var genre = "";
    var links = li.querySelectorAll("p.author a");
    for (var i = 0; i < links.length; i++) {
      if (links[i].classList.contains("name") || links[i].classList.contains("go-sub-type")) continue;
      genre = txt(links[i]);
      break;
    }
    var update = li.querySelector("p.update");
    var secret = null;
    if (update) {
      var spans = update.querySelectorAll("span[class]");
      for (var j = 0; j < spans.length; j++) {
        if (/^[A-Za-z0-9]+$/.test(spans[j].className)) {
          secret = spans[j];
          break;
        }
      }
    }
    var unit = "";
    if (secret && secret.nextSibling) {
      var unitMatch = String(secret.nextSibling.textContent || "").match(/^\s*(万字|字)/);
      unit = unitMatch ? unitMatch[1] : "";
    }
    var chapter = update ? update.querySelector("a[title]") || update.querySelector("a") : null;
    return {
      rid: li.getAttribute("data-rid") || "",
      bookId: idMatch ? idMatch[1] : "",
      title: titleEl ? titleEl.getAttribute("title") || txt(titleEl) : "",
      author: txt(li.querySelector("p.author a.name")),
      genre: genre,
      subGenre: txt(li.querySelector("p.author a.go-sub-type")),
      status: txt(li.querySelector("p.author span")),
      intro: txt(li.querySelector("p.intro")),
      wordsFont: secret ? secret.className : "",
      wordsCodes: secret
        ? Array.from(secret.textContent || "").map(function (c) {
            return c.codePointAt(0);
          })
        : [],
      wordsUnit: unit,
      latestChapter: chapter ? chapter.getAttribute("title") || txt(chapter) : "",
    };
  });
  return {
    qdLibraryPage: qdLibraryPage,
    path: location.pathname,
    site: txt(document.querySelector(".site .site-item.act")),
    filters: filters,
    sort: txt(document.querySelector(".select-wrap a.act")),
    pager: txt(document.querySelector(".lbf-pagination-current")),
    pagerMax: pagerMax,
    fontUrls: fontUrls,
    items: items,
  };
}

/** 라이브러리 page 페이지용 eval 내용을 만든다. */
function buildLibraryPageJS(page) {
  return `JSON.stringify((${qdLibraryPageSnapshot.toString()})(${Number(page)}))`;
}

/**
 * 실제 선택된 필터·정렬·페이지 번호를 대조한다. 보이는 필터 패널만 인정한다.
 * 불일치 목록을 반환하며 빈 배열은 남성·연재·30만 자 미만·3일 내·인기순·page 페이지가 맞다는 뜻이다.
 */
function checkLibraryPage(snapshot, page) {
  if (!snapshot || typeof snapshot !== "object" || !Array.isArray(snapshot.items)) {
    return ["页面没有返回列表数据"];
  }
  const problems = [];
  if (snapshot.site !== LIBRARY_SITE) problems.push(`频道是「${snapshot.site || "无"}」`);
  const filters = Array.isArray(snapshot.filters) ? snapshot.filters : [];
  for (const want of LIBRARY_FILTERS) {
    if (!filters.includes(want)) problems.push(`没选中「${want}」`);
  }
  if (snapshot.sort !== LIBRARY_SORT) problems.push(`排序是「${snapshot.sort || "无"}」`);
  if (String(snapshot.pager) !== String(page)) {
    problems.push(`分页停在第「${snapshot.pager || "?"}」页`);
  }
  return problems;
}

/** 브라우저 항목 → book. 제목·작가·장르가 없으면 잘못 맞추지 않고 수집을 포기해 null을 반환한다. */
function normalizeLibraryItem(item) {
  if (!item || typeof item !== "object") return null;
  const bookId = /^\d+$/.test(String(item.bookId || "")) ? String(item.bookId) : "";
  const title = stripCipherChars(item.title);
  const author = stripCipherChars(item.author);
  const mainGenre = stripCipherChars(item.genre);
  const subGenre = stripCipherChars(item.subGenre);
  if (!bookId || !title || !author || !mainGenre) return null;
  const codes = Array.isArray(item.wordsCodes)
    ? item.wordsCodes.map(Number).filter((n) => Number.isInteger(n) && n > 0)
    : [];
  return {
    bookId,
    title,
    url: `https://www.qidian.com/book/${bookId}/`,
    author,
    genre: subGenre ? `${mainGenre}·${subGenre}` : mainGenre,
    status: stripCipherChars(item.status),
    words: "",
    wordsFont: /^[A-Za-z0-9]+$/.test(String(item.wordsFont || "")) ? String(item.wordsFont) : "",
    wordsCodes: codes,
    wordsUnit: item.wordsUnit === "万字" || item.wordsUnit === "字" ? item.wordsUnit : "",
    latestChapter: stripCipherChars(item.latestChapter),
    totalRecommendations: "",
    signing: "",
    pricing: "",
    descText: stripCipherChars(item.intro),
    updateText: "",
  };
}

/** 모바일 bookInfo의 정수 글자 수 → ‘26.14万字’/‘8000字’. */
function formatWordsCount(count) {
  const n = Number(count);
  if (!Number.isFinite(n) || n <= 0) return "";
  return n >= 10000 ? `${(n / 10000).toFixed(2)}万字` : `${Math.round(n)}字`;
}

/** m.qidian.com/book/{id}/의 bookInfo로 총 추천·계약·유료·갱신 시각·대체 글자 수를 book에 보충한다. */
function applyMobileBookInfo(book, info) {
  if (!info || typeof info !== "object") return false;
  if (Number.isFinite(Number(info.recomAll)) && Number(info.recomAll) >= 0 && info.recomAll !== "") {
    book.totalRecommendations = String(info.recomAll);
  }
  const sign = stripCipherChars(info.signStatus);
  if (sign) book.signing = sign;
  else if (info.isSign === 1) book.signing = "签约";
  else if (info.isSign === 0) book.signing = "未签约";
  if (info.isVip === 1) book.pricing = "VIP";
  else if (info.isVip === 0) book.pricing = "免费";
  if (!book.words) {
    book.words = formatWordsCount(info.wordsCnt);
    if (book.words) book.wordsFromDetail = true;
  }
  const updated = stripCipherChars(info.updTime);
  if (updated) book.updateTime = updated;
  return true;
}

async function fetchMobileBookInfo(bookId) {
  const html = await fetchText(`${MOBILE_BASE_URL}/book/${bookId}/`);
  const info = extractMobilePageContext(html)?.pageContext?.pageProps?.pageData?.bookInfo;
  if (!info || String(info.bookId) !== String(bookId)) throw new Error("详情页没有这本书的 bookInfo");
  return info;
}

/**
 * 페이지를 넘겨 라이브러리를 수집해 { content, partialReasons }를 반환한다. 한 권도 없으면 예외이며 빈 파일은 쓰지 않는다.
 * 페이지 실패 시 그 지점에서 멈추고 앞 페이지를 partial로 보존한다. 순위가 어긋나지 않게 뒤 페이지는 넘기지 않는다.
 */
async function scrapeLibrary(port, pages) {
  const rt = RANK_TYPES.find((r) => r.library);
  console.log(`\n→ 采集 起点${rt.label}（CDP/PC，前 ${pages} 页）...`);
  const books = [];
  const seen = new Set();
  const fontUrls = {};
  const pageFailures = [];
  const notes = [];
  let skipped = 0;
  let pagerMax = 0;
  let lastPage = 0;

  for (let page = 1; page <= pages; page++) {
    if (pagerMax && page > pagerMax) {
      notes.push(`站点只有 ${pagerMax} 页`);
      break;
    }
    const url = libraryPageUrl(page);
    console.log(`  第 ${page} 页：${url}`);
    let snapshot;
    try {
      if (!openWithCaptchaHandling(port, url)) throw new Error("页面无法通过验证码拦截");
      snapshot = evalJSON(port, buildLibraryPageJS(page));
      const problems = checkLibraryPage(snapshot, page);
      if (problems.length) throw new Error(`筛选状态不符（${problems.join("，")}）`);
    } catch (err) {
      const reason = `第 ${page} 页没取到：${err && err.message ? err.message : err}`;
      console.error(`[qidian] 书库${reason}`);
      pageFailures.push(reason);
      break;
    }
    lastPage = page;
    pagerMax = Number(snapshot.pagerMax) || pagerMax;
    for (const [name, fontUrl] of Object.entries(snapshot.fontUrls || {})) fontUrls[name] = fontUrl;
    const normalized = [];
    for (const item of snapshot.items) {
      const book = normalizeLibraryItem(item);
      if (book) normalized.push(book);
      else skipped++;
    }
    const fresh = normalized.filter((b) => !seen.has(b.bookId));
    console.log(`  第 ${page} 页：${snapshot.items.length} 条，新书 ${fresh.length} 本`);
    if (!fresh.length) {
      notes.push(`第 ${page} 页没有新书，停止翻页`);
      break;
    }
    for (const book of fresh) {
      seen.add(book.bookId);
      book.rank = books.length + 1;
      books.push(book);
    }
  }

  if (!books.length) {
    throw new Error(pageFailures[0] || "书库列表页一本都没抓到（可能被验证页拦住，或页面改版）");
  }

  // 글자 수는 보호 글꼴을 먼저 해석한다.
  let decoded = 0;
  const fontErrors = new Set();
  for (const book of books) {
    if (!book.wordsFont) continue;
    const font = await loadLibraryFont(book.wordsFont, fontUrls[book.wordsFont] || "");
    if (!font.map) {
      fontErrors.add(font.error);
      continue;
    }
    book.words = decodeLibraryWords(book.wordsCodes, book.wordsUnit, font.map);
    if (book.words) decoded++;
  }
  console.log(`  字数解码：${decoded} / ${books.length}`);
  for (const message of fontErrors) console.log(`  ⚠ 字体解码失败：${message}`);

  // 총 추천·계약·유료 정보와 글자 수 해석 실패 시 대체값은 작품별 모바일 페이지에서 얻는다.
  let detailOk = 0;
  for (let i = 0; i < books.length; i++) {
    if (i > 0) sleep(LIBRARY_DETAIL_GAP_MS);
    try {
      if (applyMobileBookInfo(books[i], await fetchMobileBookInfo(books[i].bookId))) detailOk++;
    } catch (err) {
      console.log(`    详情失败 ${books[i].title}：${err && err.message ? err.message : err}`);
    }
  }
  console.log(`  详情补全：${detailOk} / ${books.length}`);

  for (const book of books) {
    book.updateText = [book.latestChapter, book.updateTime].filter(Boolean).join(" · ");
  }

  const problems = [...pageFailures.map((r) => `${r}（已保留前 ${lastPage} 页）`)];
  const missingWords = books.filter((b) => !b.words).length;
  if (missingWords) problems.push(`字数缺失 ${missingWords} 条（字体解码与详情页都没拿到）`);
  const detailFailed = books.length - detailOk;
  if (detailFailed > books.length * LIBRARY_DETAIL_FAIL_RATIO) {
    problems.push(`超过一半的书没取到详情（${detailFailed} / ${books.length}），总推荐、签约、收费多为 [待补]`);
  }
  if (skipped) problems.push(`缺书名/作者/题材的条目 ${skipped} 条，已跳过`);
  if (books.length < 15) problems.push(`[数据稀疏] 实际采集 ${books.length} 条`);

  for (const b of books) {
    b.library = true;
    b.newBookRecom = b.totalRecommendations;
  }
  const extraLines = [
    `- 筛选：${LIBRARY_SITE}·${LIBRARY_FILTERS.slice(0, 2).join("·")}·${LIBRARY_FILTERS[2]}更新；${LIBRARY_SORT}，取前 ${pages} 页`,
    `- 实际翻页：${lastPage} 页${notes.length ? `（${notes.join("；")}）` : ""}`,
    `- 字数来源：反爬字体解码 ${decoded} 条，详情页兜底 ${books.filter((b) => b.wordsFromDetail).length} 条，缺失 ${missingWords} 条`,
    `- 详情补全：成功 ${detailOk} / 共 ${books.length}`,
    "- 热度：名次即人气排名；作品页的总推荐单列为「新书总推荐」，不进聚合的热度口径",
    `- 数据质量：${problems.length ? "[存在问题]" : "[OK]"}`,
    `- 问题摘要：${problems.length ? problems.join("；") : "无"}`,
  ];
  return {
    content: renderMarkdown(rt, books, libraryPageUrl(1), "cdp-pc", extraLines),
    partialReasons: pageFailures,
  };
}

// ---------------------------------------------------------------------------
// 주 처리 흐름
// ---------------------------------------------------------------------------

const args = process.argv.slice(2);
const PORT = parseInt(getArg(args, "--port") || "9222", 10);
const OUTDIR = getArg(args, "--outdir") || ".";
const RANKTYPE = getArg(args, "--type") || "hotsales";
const SCRAPE_MODE = getArg(args, "--mode") || "auto"; // auto | mobile | cdp
const FETCH_DETAIL = (getArg(args, "--detail") || "no") === "yes";
// --pages는 --type library 전용이다. 지정 여부를 기억해 다른 순위에서 주면 무시하지 않고 오류를 낸다.
const PAGES_RAW = getArg(args, "--pages");
const PAGES_GIVEN = args.some((arg) => arg === "--pages" || String(arg).startsWith("--pages="));

function scrapeRankCDP(port, rankTypeId) {
  const rt = RANK_TYPES.find((r) => r.id === rankTypeId);
  if (!rt) {
    console.log(`  ⚠ 未知榜单类型: ${rankTypeId}`);
    return null;
  }

  const url = rt.baseUrl || `${PC_BASE_URL}/${rankTypeId}/`;
  console.log(`\n→ 采集 起点${rt.label}（CDP/PC）...`);
  console.log(`  URL: ${url}`);

  const pageReady = openWithCaptchaHandling(port, url);
  if (!pageReady) {
    console.log("  ✗ 起点采集失败：页面无法通过验证码拦截");
    return null;
  }

  scrollLoad(port, 3);
  sleep(1000);

  const books = extractBookList(port);
  if (!books.length) {
    console.log("  ⚠ 未提取到书籍");
    return null;
  }
  console.log(`  ✓ 提取 ${books.length} 本`);

  // 선택 사항: 항목별 상세 페이지에서 데이터를 보충한다.
  if (FETCH_DETAIL) {
    console.log("  正在获取详情页补充数据...");
    for (let i = 0; i < Math.min(books.length, 20); i++) {
      const b = books[i];
      if (!b.url) continue;
      ab(port, "open", b.url);
      sleep(1500);
      const detail = extractDetail(port);
      if (detail) {
        if (detail.tags?.length) b.tags = detail.tags;
        if (detail.intro) b.descText = detail.intro;
        if (detail.update) b.updateText = detail.update;
        for (const field of ["words", "totalRecommendations", "signing", "pricing"]) {
          if (detail[field]) b[field] = detail[field];
        }
      }
      console.log(`    [${i + 1}/${books.length}] ${b.title}`);
    }
    // 순위 페이지로 돌아간다.
    ab(port, "open", url);
    sleep(2000);
  }

  return renderMarkdown(rt, books, url, "cdp-pc");
}

async function scrapeRank(rankTypeId) {
  if (!["auto", "mobile", "cdp"].includes(SCRAPE_MODE)) {
    throw new Error(`未知 --mode: ${SCRAPE_MODE}（可选 auto/mobile/cdp）`);
  }

  if (SCRAPE_MODE !== "cdp") {
    try {
      const content = await scrapeRankMobile(rankTypeId);
      if (content || SCRAPE_MODE === "mobile") return content;
    } catch (e) {
      console.log(`  ⚠ 移动端 SSR 采集失败: ${e.message}`);
      if (SCRAPE_MODE === "mobile") return null;
    }
  }

  if (SCRAPE_MODE !== "mobile") {
    console.log("  → 回退到 CDP/PC 页面采集");
    return scrapeRankCDP(PORT, rankTypeId);
  }

  return null;
}

async function main() {
  // 인자 오류는 개별 순위의 일시 실패가 아닌 설정 문제이므로 순위별 격리 전에 빠르게 실패한다.
  if (RANKTYPE !== "all" && !RANK_TYPES.some((rank) => rank.id === RANKTYPE)) {
    throw new Error(`未知 --type: ${RANKTYPE}`);
  }
  if (!["auto", "mobile", "cdp"].includes(SCRAPE_MODE)) {
    throw new Error(`未知 --mode: ${SCRAPE_MODE}（可选 auto/mobile/cdp）`);
  }
  const libraryPages = validateLibraryArgs(RANKTYPE, SCRAPE_MODE, PAGES_RAW, PAGES_GIVEN);

  // 라이브러리는 CDP 전용이며 Chrome이 필요 없는 기본 --type all에서 제외한다.
  const rankTypes =
    RANKTYPE === "all" ? RANK_TYPES.filter((r) => !r.library).map((r) => r.id) : [RANKTYPE];
  let written = 0;
  let failed = 0;
  let partial = false;
  const partialReasons = [];

  for (const rt of rankTypes) {
    // 순위별 격리: 모바일 SSR 실패 후 CDP 대체는 예외를 그대로 던진다(ab()가 삼키지 않음).
    // 한 순위의 일시 실패가 --type all의 나머지를 끊으면 안 된다(판체·츠웨이마오와 동일).
    try {
      const rtInfo = RANK_TYPES.find((r) => r.id === rt);
      let content;
      if (rtInfo.library) {
        const library = await scrapeLibrary(PORT, libraryPages);
        content = library.content;
        if (library.partialReasons.length) {
          partial = true;
          partialReasons.push(...library.partialReasons.map((reason) => `${rtInfo.label}: ${reason}`));
        }
      } else {
        content = await scrapeRank(rt);
      }
      if (!content) {
        failed++;
        partialReasons.push(`${rtInfo ? rtInfo.label : rt}: no usable data`);
        continue;
      }

      const filename = `起点${rtInfo.label}_${localDateStamp()}.md`;
      fs.mkdirSync(OUTDIR, { recursive: true });
      const filepath = path.join(OUTDIR, filename);
      fs.writeFileSync(filepath, content, "utf-8");
      written++;
      console.log(`  ✓ 已保存: ${filepath}`);
    } catch (rankErr) {
      failed++;
      const rtInfo = RANK_TYPES.find((r) => r.id === rt);
      const message = rankErr && rankErr.message ? rankErr.message : String(rankErr);
      partialReasons.push(`${rtInfo ? rtInfo.label : rt}: ${message}`);
      console.error(
        `[qidian] ${rtInfo ? rtInfo.label : rt} 采集失败，跳过: ${message}`
      );
    }
  }
  return {
    planned: rankTypes.length,
    written,
    failed,
    partial: partial || failed > 0,
    partialReasons,
  };
}

if (require.main === module) {
  runCli(main, "起点采集");
}

module.exports = {
  extractBookList,
  mobileUrl,
  extractMobilePageContext,
  normalizeMobileBook,
  cleanDesc,
  renderMarkdown,
  rankQualityLines,
  parseAntiSpiderFont,
  decodeLibraryWords,
  captchaCheckJS,
};
