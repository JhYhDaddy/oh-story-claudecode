#!/usr/bin/env node
/**
 * 판체 소설 순위 수집기. browser-cdp로 Chrome CDP 환경을 먼저 시작한다.
 * 순위 페이지의 __INITIAL_STATE__에서 구조화 목록을 얻고 작품별 상세 페이지에서 실제 제목·작가·소개·장르·태그를 해석한다.
 * 목록은 글꼴 기반 수집 방지를 사용하지만 상세 HTML은 평문이다. 출력 형식은 aggregate-rank.js 머리 주석을 따른다.
 * 사용법:
 *   node fanqie-rank-scraper.js --channel 1 --type 2              # 남성향 읽기 순위
 *   node fanqie-rank-scraper.js --channel 0 --type 1              # 여성향 신작 순위
 *   node fanqie-rank-scraper.js --channel 1 --type 2 --outdir ./   # 출력 디렉터리
 *   node fanqie-rank-scraper.js --channel all                    # 전체 수집
 *   node fanqie-rank-scraper.js --channel 1 --top 15              # 장르별 상위 15권
 *   node fanqie-rank-scraper.js --source library --channel all    # 라이브러리 인기순: 연재 중, 30만 자 미만
 *   node fanqie-rank-scraper.js --source library --channel mix --pages 5 # 성별 구분 없이 5페이지
 * 사전 실행:
 *   node {SKILL_DIR}/browser-cdp/scripts/setup-cdp-chrome.js 9222
 */

const fs = require("fs");
const path = require("path");
const { ab, sleep, evalJSONBase64, scrollLoad, getArg, localDateStamp, runCli } = require("./cdp-utils");

// 상세 요청 한 번의 동시 배치 크기. 동기 XHR을 쓰므로 너무 크면
// cdp-utils ab()의 20초 제한에 걸려 명시적으로 실패한다. 배치 분할은 장르 전체 중단을 피하기 위한 것이다.
const DETAIL_CHUNK = 5;

// ---------------------------------------------------------------------------
// 페이지 추출
// ---------------------------------------------------------------------------

/** 연결·페이지 준비 상태 자체 검사. */
function probePage(port) {
  return evalJSONBase64(
    port,
    "JSON.stringify({host:location.host,hasState:!!window.__INITIAL_STATE__})"
  );
}

/** 사이드 메뉴 분류 링크를 추출하는 브라우저 JS를 만든다. */
function buildCategoriesJS(prefix) {
  return `JSON.stringify((function(){
    var prefix=${JSON.stringify(prefix)};
    var out=[];var seen={};
    Array.from(document.querySelectorAll('a')).forEach(function(a){
      var href=a.getAttribute('href')||'';
      if(href.indexOf(prefix)===-1)return;
      var name=(a.innerText||a.textContent||'').trim();
      if(!name)return;
      if(seen[href])return;seen[href]=1;
      out.push({name:name,href:href});
    });
    return out;
  })())`;
}

/** 사이드 메뉴 분류 링크를 추출한다. */
function extractCategories(port, channel, type) {
  const prefix = `/rank/${channel}_${type}_`;
  return evalJSONBase64(port, buildCategoriesJS(prefix)) || [];
}

/**
 * __INITIAL_STATE__에서 현재 분류의 작품 목록을 얻는다.
 * 여러 경로와 심층 대체 탐색을 시도하고 필드 이름을 정규화해 state 구조 변경으로 전체가 실패하지 않게 한다.
 */
function buildBookListJS() {
  return `JSON.stringify((function(){
    var s=window.__INITIAL_STATE__||{};
    var cands=[
      s.rank&&s.rank.book_list, s.rank&&s.rank.bookList, s.rank&&s.rank.rankList,
      s.rankData&&s.rankData.book_list, s.page&&s.page.book_list
    ];
    var list=null;
    for(var i=0;i<cands.length;i++){ if(Array.isArray(cands[i])&&cands[i].length){list=cands[i];break;} }
    if(!list){
      var found=null;
      (function walk(o,d){
        if(found||!o||d>6)return;
        if(Array.isArray(o)){
          if(o.length&&o[0]&&typeof o[0]==='object'&&(o[0].bookId||o[0].book_id)){found=o;return;}
          for(var j=0;j<o.length&&!found;j++)walk(o[j],d+1);return;
        }
        if(typeof o==='object'){ for(var k in o){ if(found)break; try{walk(o[k],d+1)}catch(e){} } }
      })(s,0);
      list=found||[];
    }
    return list.map(function(b){return {
      bookId:String(b.bookId||b.book_id||''),
      read_count:b.read_count||b.readCount||b.read||'',
      wordNumber:b.wordNumber||b.word_number||b.wordCount||'',
      creationStatus:(b.creationStatus!=null?b.creationStatus:(b.creation_status!=null?b.creation_status:b.status)),
      lastChapterTitle:b.lastChapterTitle||b.last_chapter_title||b.lastChapter||'',
      category:b.category||b.categoryName||b.category_name||''
    };}).filter(function(b){return b.bookId;});
  })())`;
}

function extractBookList(port) {
  const list = evalJSONBase64(port, buildBookListJS());
  return Array.isArray(list) ? list : [];
}

/**
 * 작품 상세 HTML을 파싱한다. buildDetailJS가 toString으로 브라우저 스크립트에 넣으므로 모듈 범위를 참조하거나 백틱을 포함하면 안 된다.
 * 목록의 제목·작가는 글꼴로 보호되지만 상세 HTML의 JSON과 <title>은 평문이다.
 * 실제 SSR(__INITIAL_STATE__)의 bookName/author/abstract를 쓰며 장르는 categoryV2(이스케이프된 JSON 배열 첫 Name)에 있다.
 * readCount/wordNumber는 숫자 또는 문자열이다. 추천 작품 객체도 bookName/readCount/lastChapterTitle을 포함해 먼저 나올 수 있으므로
 * 제목·작가·숫자·최신 장은 현재 작품 객체에서만 얻는다. bookId로 먼저 찾고 실패하면 <title> 제목으로 찾는다.
 * 둘 다 실패하면 제목·작가는 <title>/meta로 대체하고 숫자는 비운다. 추천 작품의 수치를 잘못 기록하는 대신 미상으로 둔다.
 */
function parseDetailHtml(h, id) {
  function pick(src, res) {
    for (var i = 0; i < res.length; i++) {
      var m = src.match(res[i]);
      if (m && m[1]) return m[1].trim();
    }
    return "";
  }
  function jsonString(src, key) {
    var m = src.match(new RegExp('"' + key + '"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)"'));
    if (!m) return "";
    try {
      return String(JSON.parse('"' + m[1] + '"')).trim();
    } catch (e) {
      return m[1].replace(/\\"/g, '"').trim();
    }
  }
  function jsonNumber(src, key) {
    var m = src.match(new RegExp('"' + key + '"\\s*:\\s*"?([0-9]+)'));
    return m ? m[1] : "";
  }
  // JSON 시작부터 문자열을 구분해 탐색하고 pos를 포함한 가장 안쪽 객체 텍스트를 반환한다.
  function enclosingObject(src, pos) {
    var start = src.lastIndexOf("__INITIAL_STATE__", pos);
    if (start >= 0) {
      start = src.indexOf("{", start);
    } else {
      start = src.lastIndexOf("<script", pos);
      start = start >= 0 ? src.indexOf(">", start) + 1 : 0;
    }
    if (start < 0 || start > pos) return "";
    var stack = [];
    var inStr = false;
    var esc = false;
    for (var i = start; i < src.length; i++) {
      var c = src.charAt(i);
      if (inStr) {
        if (esc) esc = false;
        else if (c === "\\") esc = true;
        else if (c === '"') inStr = false;
        continue;
      }
      if (c === '"') inStr = true;
      else if (c === "{") stack.push(i);
      else if (c === "}") {
        var open = stack.pop();
        if (open === undefined) return "";
        if (open <= pos && i >= pos) return src.slice(open, i + 1);
      }
    }
    return "";
  }
  function regionAt(re) {
    var m;
    re.lastIndex = 0;
    while ((m = re.exec(h))) {
      var obj = enclosingObject(h, m.index);
      if (obj.indexOf('"bookName"') >= 0) return obj;
    }
    return "";
  }

  var titleTag = pick(h, [
    /<title>([^<]*?)(?:完整版|最新章节|在线阅读|_番茄小说|-番茄小说|_番茄|-番茄)/,
    /<meta[^>]+property="og:title"[^>]+content="([^"]+)"/,
    /<title>([^<|_]{1,40})/,
  ]);
  var safeId = String(id).replace(/[^0-9A-Za-z_]/g, "");
  var region = safeId
    ? regionAt(new RegExp('"(?:bookId|book_id)"\\s*:\\s*"?' + safeId + '(?![0-9A-Za-z_])', "g"))
    : "";
  if (!region && titleTag) {
    var escTitle = titleTag.replace(/[.*+?^$()|[\]\\{}]/g, "\\$&");
    region = regionAt(new RegExp('"bookName"\\s*:\\s*"' + escTitle + '"', "g"));
  }

  var title = (region && jsonString(region, "bookName")) || titleTag;
  var author = (region && (jsonString(region, "author") || jsonString(region, "authorName"))) ||
    pick(h, [/<meta[^>]+property="og:novel:author"[^>]+content="([^"]+)"/]);
  // 실제 소개인 abstract를 우선한다. meta description은 플랫폼 템플릿(‘番茄小说提供...’)이며
  // data-rh 속성이 흔히 있으므로 느슨한 속성 일치를 대안으로 쓴다.
  var abs = region ? jsonString(region, "abstract") : "";
  if (abs.length < 6) abs = "";
  var desc = abs || pick(h, [
    /<meta[^>]+name="description"[^>]+content="([^"]+)"/,
    /<meta[^>]+property="og:description"[^>]+content="([^"]+)"/,
  ]);
  // 장르: category는 빈 문자열인 경우가 많으며 실제 값은 categoryV2의 이스케이프 JSON 첫 Name이다.
  var category = (region && pick(region, [
    /"categoryV2":"\[\{[\s\S]*?\\"Name\\":\\"([^"\\]+)/,
    /"category"\s*:\s*"([^"]{1,20})"/,
  ])) || pick(h, [/<meta[^>]+property="og:novel:category"[^>]+content="([^"]+)"/]);
  // 태그: 판체 소개 시작의 【tag+tag+...】는 장르 세분화의 실제 신호다.
  var tags = "";
  var bm = (abs || desc || "").match(/[【\[]([^】\]]{2,40})[】\]]/);
  if (bm) tags = bm[1].split(/[+、,\/\s]+/).filter(Boolean).slice(0, 6).join("、");
  // 라이브러리 목록의 읽는 중 수·글자 수도 글꼴로 보호되며 상세 SSR 숫자는 평문이다.
  return {
    title: title,
    author: author,
    desc: desc,
    category: category,
    tags: tags,
    readCount: region ? jsonNumber(region, "readCount") : "",
    wordNumber: region ? jsonNumber(region, "wordNumber") : "",
    creationStatus: region ? jsonNumber(region, "creationStatus") : "",
    lastChapterTitle: region ? jsonString(region, "lastChapterTitle") : "",
  };
}

/**
 * 상세 정보 일괄 해석: 작품별 동기 XHR로 /page/{id}를 요청하고 parseDetailHtml에 전달한다.
 * { id: {title, author, desc, category, tags, readCount, wordNumber, creationStatus, lastChapterTitle} } 반환.
 */
function buildDetailJS(ids) {
  return `JSON.stringify((function(){
    var ids=${JSON.stringify(ids)};
    var parseDetailHtml=${parseDetailHtml.toString()};
    var map={};
    for(var k=0;k<ids.length;k++){
      var id=ids[k];
      try{
        var x=new XMLHttpRequest();
        x.open('GET','/page/'+id,false);
        x.send();
        map[id]=parseDetailHtml(x.responseText||'',id);
      }catch(e){
        map[id]={title:'',author:'',desc:'',category:'',tags:'',err:String(e&&e.message||e)};
      }
    }
    return map;
  })())`;
}

function fetchDetailsChunk(port, ids) {
  return evalJSONBase64(port, buildDetailJS(ids)) || {};
}

/** 한 번의 eval 시간 초과를 피하도록 나누어 해석하고 합친 map을 반환한다. */
function fetchDetails(port, bookIds) {
  const map = {};
  for (let i = 0; i < bookIds.length; i += DETAIL_CHUNK) {
    const chunk = bookIds.slice(i, i + DETAIL_CHUNK);
    const part = fetchDetailsChunk(port, chunk);
    Object.assign(map, part);
    sleep(300);
  }
  return map;
}

// ---------------------------------------------------------------------------
// 형식화
// ---------------------------------------------------------------------------

function fmtReads(count) {
  if (!count || count === "0") return "未知";
  const n = parseInt(count, 10);
  if (isNaN(n)) return "未知";
  if (n >= 10000) return (n / 10000).toFixed(1) + "万";
  return String(n);
}

function fmtWords(count) {
  if (!count) return "未知";
  const n = parseInt(count, 10);
  if (isNaN(n)) return "未知";
  if (n >= 10000) return (n / 10000).toFixed(1) + "万";
  return String(n);
}

function fmtStatus(s) {
  const v = String(s);
  if (v === "1") return "连载中";
  if (v === "0" || v === "2") return "已完结";
  return s ? String(s) : "未知";
}

/** 소개 정리: 플랫폼 템플릿 제거 → 공백 압축 → 문장 끝 기준 100자 절단. */
function cleanDesc(raw) {
  if (!raw) return "";
  let d = String(raw)
    // 소개는 원본 JSON 문자열이므로 일반 이스케이프(\n \uXXXX \" 등)를 먼저 복원한다.
    .replace(/\\u([0-9a-fA-F]{4})/g, (_, h) => String.fromCharCode(parseInt(h, 16)))
    .replace(/\\[nrt]/g, " ")
    .replace(/\\"/g, '"')
    .replace(/番茄小说[^。！？]*?(?:免费阅读|完整版|在线阅读)[^。！？]*[。！？]/g, "")
    .replace(/番茄小说[^。！？]*?(?:免费阅读|完整版|在线阅读)[^。！？]*$/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (d.length <= 100) return d;
  const cut = d.slice(0, 100);
  const m = cut.match(/^[\s\S]*[。！？]/);
  return (m ? m[0] : cut) + "...";
}

// ---------------------------------------------------------------------------
// 주 처리 흐름
// ---------------------------------------------------------------------------

const args = process.argv.slice(2);
const PORT = parseInt(getArg(args, "--port") || "9222", 10);
const OUTDIR = getArg(args, "--outdir") || ".";
const CHANNEL = getArg(args, "--channel") || "1";
const TYPE = getArg(args, "--type") || "2";
const TOP = parseInt(getArg(args, "--top") || "20", 10);
const SOURCE = getArg(args, "--source") || "rank";
const PAGES = parseInt(getArg(args, "--pages") || "3", 10);
const STAT = getArg(args, "--stat") || "1";
const COUNT = getArg(args, "--count") || "0";

function channelLabel(ch) {
  return ch === "1" ? "男频" : "女频";
}

function typeLabel(t) {
  return t === "2" ? "阅读榜" : "新书榜";
}

function scrapeChannel(ch, type) {
  const chLabel = channelLabel(ch);
  const tyLabel = typeLabel(type);
  console.log(`\n→ 采集 ${chLabel}${tyLabel}...`);

  // 알려진 분류 ID로 진입해 메뉴가 현재 채널·유형의 분류만 표시하게 한다.
  const initCatId = ch === "1" ? "1141" : "1139"; // 남성향: 서양 판타지 / 여성향: 고풍 세태물
  const initUrl = `https://fanqienovel.com/rank/${ch}_${type}_${initCatId}`;
  ab(PORT, "open", initUrl);
  sleep(3000);

  // 연결 자체 검사: bookId만 조용히 나열하는 대신 대응 가능한 오류를 준다.
  const probe = probePage(PORT);
  if (!probe) {
    throw new Error(`CDP 无响应。请确认已用 browser-cdp 启动 Chrome（端口 ${PORT}），且 agent-browser 可用`);
  }
  if (probe.host && probe.host.indexOf("fanqie") === -1) {
    throw new Error(`当前页面非番茄（host=${probe.host}），可能被重定向到登录/验证页`);
  }
  if (!probe.hasState) {
    console.error(`  ⚠ 页面未挂载 __INITIAL_STATE__，将尝试兜底扫描，结果可能不完整。`);
  }

  let categories = extractCategories(PORT, ch, type);
  if (!categories.length) {
    // 메뉴가 지연 로딩될 수 있어 스크롤 후 한 번 재시도한다.
    scrollLoad(PORT, 2);
    sleep(1000);
    categories = extractCategories(PORT, ch, type);
  }
  if (!categories.length) {
    // 계속 실패하면 현재 진입 페이지만 수집해 빈 실행 대신 최소한의 데이터를 얻는다.
    console.log(`  ⚠ 未提取到品类菜单，降级为单题材采集（入口页）`);
    categories = [{ name: "全部（入口页）", href: `/rank/${ch}_${type}_${initCatId}` }];
  } else {
    console.log(`  发现 ${categories.length} 个品类`);
  }

  const now = new Date().toISOString();
  const lines = [
    `# 番茄 · ${chLabel}${tyLabel} · 全 ${categories.length} 题材`,
    "",
    `- 频道参数：channel=${ch}，type=${type}`,
    `- 抓取时间：${now}`,
    `- 每题材上限 ≈ ${TOP}`,
    "",
    "---",
    "",
  ];

  let totalBooks = 0;
  let resolvedTitles = 0;
  const bodyLines = [];

  for (let ci = 0; ci < categories.length; ci++) {
    const cat = categories[ci];
    console.log(`  [${ci + 1}/${categories.length}] ${cat.name}`);

    try {
      ab(PORT, "open", `https://fanqienovel.com${cat.href}`);
      sleep(2500);
      scrollLoad(PORT, 2);

      let books = extractBookList(PORT);
      if (!Array.isArray(books) || !books.length) {
        bodyLines.push(`## ${cat.name} — 0 本`, "", "---", "");
        continue;
      }
      if (books.length > TOP) books = books.slice(0, TOP);

      // 실제 제목·작가·소개·장르·평점·태그를 나누어 해석한다.
      const bookIds = books.map((b) => String(b.bookId));
      const details = fetchDetails(PORT, bookIds);

      bodyLines.push(`## ${cat.name} — ${books.length} 本`, "");

      for (let i = 0; i < books.length; i++) {
        const b = books[i];
        const info = details[String(b.bookId)] || {};
        totalBooks++;
        const resolved = !!info.title;
        if (resolved) resolvedTitles++;

        const title = info.title || "（标题待解析）";
        const author = info.author || "未知";
        const category = info.category || b.category || "";
        const catSeg = category ? ` · ${category}` : "";

        bodyLines.push(`### #${i + 1} ${title}`);
        bodyLines.push(
          `*${author}${catSeg} · ${fmtStatus(b.creationStatus)} · ${fmtReads(b.read_count)} 在读 · ${fmtWords(b.wordNumber)}字*`
        );
        if (info.tags) bodyLines.push(`**标签：** ${info.tags}`);
        bodyLines.push(`**最新更新：** ${b.lastChapterTitle || "未知"}`);
        bodyLines.push(`**bookId：** ${b.bookId}`);
        bodyLines.push(`[作品页](https://fanqienovel.com/page/${b.bookId})`);
        const desc = cleanDesc(info.desc);
        if (desc) {
          bodyLines.push("");
          bodyLines.push("**简介**");
          bodyLines.push("");
          bodyLines.push(desc);
        }
        bodyLines.push("");
      }

      bodyLines.push("---", "");
    } catch (catErr) {
      console.error(
        `  [fanqie] 品类 ${cat.name} 处理出错，跳过: ${catErr && catErr.message ? catErr.message : catErr}`
      );
      bodyLines.push(`## ${cat.name} — 采集失败`, "", "---", "");
    }
  }

  // 한 권도 수집하지 못하면 파일을 쓰지 않고 실패로 센다. 빈 순위가 집계에 들어가면 결론 일부가 조용히 빠진다.
  if (totalBooks === 0) {
    throw new Error("所有题材一本都没采到（页面结构可能变了，或被登录/验证页拦住）");
  }

  // 품질 상태: 제목 해석 비율이 판체 수집 성공 여부의 핵심 신호다.
  const ratio = resolvedTitles / totalBooks;
  const quality = ratio < 0.5 ? "[标题解析异常]" : "[OK]";
  lines.splice(5, 0,
    `- 标题解析：成功 ${resolvedTitles} / 共 ${totalBooks}`,
    `- 数据质量：${quality}`
  );

  if (resolvedTitles === 0) {
    console.error(
      `  ✗ ${chLabel}${tyLabel}：${totalBooks} 本全部标题解析失败。多为详情页结构变动或登录/验证拦截，` +
      `请在 Chrome 内手动打开任一 https://fanqienovel.com/page/{bookId} 确认页面正常。`
    );
  } else if (ratio < 0.5) {
    console.error(
      `  ⚠ ${chLabel}${tyLabel}：标题解析率偏低（${resolvedTitles}/${totalBooks}），结果质量已标注。`
    );
  }

  return lines.concat(bodyLines).join("\n");
}


// ---------------------------------------------------------------------------
// 라이브러리 인기순: /library/{필터}/page_{n}?sort=hottes, 페이지당 18권, 인기도순.
// ---------------------------------------------------------------------------

const LIB_STAT = { "1": "连载中", "0": "已完结", any: "" };
const LIB_COUNT = { "0": "30万字以下", "1": "30-50万字", "2": "50-100万字", "3": "100-200万字", "4": "200万字以上", any: "" };

/** 라이브러리 필터: audience1=남성, audience0=여성, stat1=연재 중, count0=30만 자 미만. 모두 미선택이면 all. */
function libraryPath(ch) {
  const segs = [];
  if (ch !== "mix") segs.push(`audience${ch}`);
  if (STAT !== "any") segs.push(`stat${STAT}`);
  if (COUNT !== "any") segs.push(`count${COUNT}`);
  return segs.length ? segs.join("-") : "all";
}

function libraryLabel(ch) {
  const who = ch === "mix" ? "全站" : channelLabel(ch);
  const filters = [LIB_STAT[STAT], LIB_COUNT[COUNT]].filter(Boolean).join("·");
  return { who, filters };
}

/** 목록 제목·읽는 중 수는 글꼴 보호 대상이다. 페이지순 bookId만 얻고 나머지는 상세 페이지에서 해석한다. */
function buildLibraryIdsJS() {
  return `JSON.stringify((function(){
    var seen={},out=[];
    Array.from(document.querySelectorAll('a[href*="/page/"]')).forEach(function(a){
      var m=(a.getAttribute('href')||'').match(/\\/page\\/(\\d+)/);
      if(m&&!seen[m[1]]){seen[m[1]]=1;out.push(m[1]);}
    });
    return out;
  })())`;
}

function scrapeLibrary(ch) {
  const { who, filters } = libraryLabel(ch);
  const seg = libraryPath(ch);
  console.log(`\n→ 采集 番茄书库最热 · ${who}${filters ? "（" + filters + "）" : ""}...`);
  const ids = [];
  for (let page = 1; page <= PAGES; page++) {
    const url = `https://fanqienovel.com/library/${seg}/page_${page}?sort=hottes`;
    ab(PORT, "open", url);
    sleep(3000);
    if (page === 1) {
      const probe = probePage(PORT);
      if (!probe) {
        throw new Error(`CDP 无响应。请确认已用 browser-cdp 启动 Chrome（端口 ${PORT}），且 agent-browser 可用`);
      }
      if (probe.host && probe.host.indexOf("fanqie") === -1) {
        throw new Error(`当前页面非番茄（host=${probe.host}），可能被重定向到登录/验证页`);
      }
    }
    const readIds = () => {
      const got = evalJSONBase64(PORT, buildLibraryIdsJS());
      return Array.isArray(got) ? got : [];
    };
    let pageIds = readIds();
    if (!pageIds.length) {
      sleep(2000);
      pageIds = readIds();
    }
    const fresh = pageIds.filter((id) => !ids.includes(id));
    console.log(`  第 ${page} 页：${fresh.length} 本`);
    if (!fresh.length) break;
    ids.push(...fresh);
  }

  if (!ids.length) {
    // 한 권도 못 얻으면 빈 파일을 쓰지 않는다. 빈 파일을 집계하면 결론 일부가 조용히 빠진다.
    throw new Error("书库列表页一本都没抓到（可能被登录/验证页拦住，或页面改版）");
  }
  const details = fetchDetails(PORT, ids);
  const now = new Date().toISOString();
  let resolved = 0;
  const body = [`## 全部（书库最热） — ${ids.length} 本`, ""];
  ids.forEach((id, i) => {
    const info = details[id] || {};
    if (info.title) resolved++;
    const catSeg = info.category ? ` · ${info.category}` : "";
    body.push(`### #${i + 1} ${info.title || "（标题待解析）"}`);
    body.push(`*${info.author || "未知"}${catSeg} · ${fmtStatus(info.creationStatus)} · ${fmtReads(info.readCount)} 在读 · ${fmtWords(info.wordNumber)}字*`);
    if (info.tags) body.push(`**标签：** ${info.tags}`);
    body.push(`**最新更新：** ${info.lastChapterTitle || "未知"}`);
    body.push(`**bookId：** ${id}`);
    body.push(`[作品页](https://fanqienovel.com/page/${id})`);
    const desc = cleanDesc(info.desc);
    if (desc) body.push("", "**简介**", "", desc);
    body.push("");
  });
  const quality = resolved / ids.length < 0.5 ? "[标题解析异常]" : "[OK]";
  if (resolved / ids.length < 0.5) {
    console.error(`  ⚠ 标题解析率偏低（${resolved}/${ids.length}），请在 Chrome 内手动打开任一作品页确认不是验证页。`);
  }
  // 목록명에 ‘新书’를 넣는다. 연재 중·30만 자 미만의 인기순은 사실상 신작 인기도이므로 집계의 신작 순위 열로 들어간다.
  const listName = `${who}书库最热${COUNT === "0" && STAT === "1" ? "新书" : ""}`;
  const head = [
    `# 番茄 · ${listName}`,
    "",
    `- 来源：https://fanqienovel.com/library/${seg}/page_1?sort=hottes`,
    `- 筛选：${filters || "不限"}；按「最热」排序，取前 ${PAGES} 页`,
    `- 抓取时间：${now}`,
    `- 标题解析：成功 ${resolved} / 共 ${ids.length}`,
    `- 数据质量：${quality}`,
    "",
    "---",
    "",
  ];
  return { content: head.concat(body).join("\n"), name: `番茄${who}${listName.replace(who, "")}_${libraryPath(ch)}_${localDateStamp()}.md` };
}

function mainLibrary() {
  if (!["0", "1", "all", "mix"].includes(CHANNEL)) throw new Error(`未知 --channel: ${CHANNEL}（书库用 1 / 0 / all / mix）`);
  if (!(STAT in LIB_STAT)) throw new Error(`未知 --stat: ${STAT}（1 连载中 / 0 已完结 / any）`);
  if (!(COUNT in LIB_COUNT)) throw new Error(`未知 --count: ${COUNT}（0-4 或 any）`);
  const channels = CHANNEL === "all" ? ["1", "0"] : [CHANNEL];
  const failures = [];
  let written = 0;
  for (const ch of channels) {
    try {
      const out = scrapeLibrary(ch);
      fs.mkdirSync(OUTDIR, { recursive: true });
      const filepath = path.join(OUTDIR, out.name);
      fs.writeFileSync(filepath, out.content, "utf-8");
      written++;
      console.log(`  ✓ 已保存: ${filepath}`);
    } catch (err) {
      const reason = `书库${libraryLabel(ch).who}：${err && err.message ? err.message : err}`;
      console.error(`[fanqie] ${reason}，跳过`);
      failures.push(reason);
    }
  }
  return outcome(channels.length, written, failures);
}

/** runCli 형식으로 보고한다. 아무 파일도 못 쓰면 전체 실패, 일부 실패는 exit 2와 사유 목록이다. */
function outcome(planned, written, failures) {
  if (!written) throw new Error(failures.join("；") || "no output was written");
  return { planned, written, failed: failures.length, partialReasons: failures };
}

function main() {
  if (SOURCE === "library") return mainLibrary();
  if (SOURCE !== "rank") throw new Error(`未知 --source: ${SOURCE}（rank / library）`);
  if (!["0", "1", "all"].includes(CHANNEL)) {
    throw new Error(`未知 --channel: ${CHANNEL}`);
  }
  if (!["1", "2", "all"].includes(TYPE)) {
    throw new Error(`未知 --type: ${TYPE}`);
  }
  const channels = CHANNEL === "all" ? ["1", "0"] : [CHANNEL];
  const types = TYPE === "all" ? ["2", "1"] : [TYPE];
  const failures = [];
  let written = 0;

  for (const ch of channels) {
    for (const ty of types) {
      try {
        const content = scrapeChannel(ch, ty);

        const filename = `番茄${channelLabel(ch)}${typeLabel(ty)}_全题材_${localDateStamp()}.md`;
        fs.mkdirSync(OUTDIR, { recursive: true });
        const filepath = path.join(OUTDIR, filename);
        fs.writeFileSync(filepath, content, "utf-8");
        written++;
        console.log(`  ✓ 已保存: ${filepath}`);
      } catch (chErr) {
        const reason = `${channelLabel(ch)}${typeLabel(ty)}：${chErr && chErr.message ? chErr.message : chErr}`;
        console.error(`[fanqie] ${reason}，跳过`);
        failures.push(reason);
      }
    }
  }
  return outcome(channels.length * types.length, written, failures);
}

if (require.main === module) {
  runCli(main, "番茄采集");
}

module.exports = { parseDetailHtml, buildDetailJS, cleanDesc };
