#!/usr/bin/env node
/**
 * 츠웨이마오 읽기 순위 수집기. browser-cdp 스킬로 Chrome CDP 환경을 먼저 시작한다.
 * rank-index 한 페이지에 모든 순위가 있으므로 텍스트를 파싱해 구조화한다.
 * 출력 Markdown 형식은 aggregate-rank.js 머리 주석에 있으며 집계도 그 형식으로 파싱한다.
 * 사용법:
 *   node ciweimao-rank-scraper.js --type click       # 조회 순위
 *   node ciweimao-rank-scraper.js --type monthly     # 월표 순위
 *   node ciweimao-rank-scraper.js --type all         # 전체 순위
 * 사전 실행:
 *   node {SKILL_DIR}/browser-cdp/scripts/setup-cdp-chrome.js 9222
 */

const fs = require("fs");
const path = require("path");
const { ab, sleep, evalJSONBase64, scrollLoad, getArg, localDateStamp, runCli } = require("./cdp-utils");

const RANK_URL = "https://www.ciweimao.com/rank-index";

/** 연결·페이지 준비 상태 자체 검사. */
function probePage(port) {
  return evalJSONBase64(
    port,
    "JSON.stringify({host:location.host,len:(document.body&&document.body.innerText||'').length})"
  );
}

const RANK_TYPES = [
  { id: "click", label: "点击榜", header: "点击榜" },
  { id: "favor", label: "收藏榜", header: "收藏榜" },
  { id: "recommend", label: "推荐榜", header: "推荐榜" },
  { id: "subscribe", label: "订阅榜", header: "订阅榜" },
  { id: "monthly", label: "月票榜", header: "月票榜" },
  { id: "tsukkomi", label: "吐槽榜", header: "吐槽榜" },
  { id: "newbook", label: "新书榜", header: "新书榜" },
  { id: "blade", label: "刀片榜", header: "刀片榜" },
  { id: "update", label: "更新榜", header: "更新榜" },
];

// ---------------------------------------------------------------------------
// 페이지 추출
// ---------------------------------------------------------------------------

/**
 * rank-index 한 페이지에서 모든 순위를 파싱한다.
 * 각 순위는 ‘点击榜’ 같은 제목 뒤에 특수 NO.1 항목과 일반 #2-10 항목이 있다.
 * NO.1: 제목 / 작가 / 지표 값의 세 행.
 * #2-10: N[장르]제목 / 지표 값의 두 행.
 */
function extractAllRanks(port) {
  const js =
    "JSON.stringify((()=>{" +
    "var text=document.body.innerText||'';" +
    "var lines=text.split(/\\n/).map(function(l){return l.trim()}).filter(Boolean);" +
    "var headers=['点击榜','收藏榜','推荐榜','订阅榜','月票榜','吐槽榜','新书榜','刀片榜','更新榜'];" +
    "var sections=[];var curName='';var curEntries=[];" +
    "for(var i=0;i<lines.length;i++){" +
    "  var line=lines[i];" +
    // 새 section 탐지
    "  var headerIdx=headers.indexOf(line);" +
    "  if(headerIdx>=0){" +
    "    if(curName&&curEntries.length)sections.push({name:curName,entries:curEntries});" +
    "    curName=headers[headerIdx];curEntries=[];continue" +
    "  }" +
    "  if(!curName)continue;" +
    // 기간 탭·UI 텍스트 건너뛰기
    "  if(/^(周榜|月榜|总榜)$/.test(line))continue;" +
    // NO.1 항목
    "  if(line==='NO.1'&&i+3<lines.length){" +
    "    var t=lines[i+1]||'';var a=lines[i+2]||'';var v=lines[i+3]||'';" +
    "    if(headers.indexOf(v)>=0)continue;" +
    "    curEntries.push({rank:1,title:t,author:a,genre:'',metric:v});" +
    "    i+=2;continue" +
    "  }" +
    // #2-10 항목: N[장르]제목
    "  var rm=line.match(/^(\\d{1,2})\\[(.+?)\\](.+)$/);" +
    "  if(rm){" +
    "    var nextVal=i+1<lines.length?lines[i+1]:'';" +
    "    var metric='';" +
    "    if(/^[\\d.]+(万)?$/.test(nextVal)){metric=nextVal;i++}" +
    "    curEntries.push({rank:parseInt(rm[1]),title:rm[3],author:'',genre:rm[2],metric:metric});" +
    "    continue" +
    "  }" +
    "}" +
    "if(curName&&curEntries.length)sections.push({name:curName,entries:curEntries});" +
    "return sections" +
    "})())";
  return evalJSONBase64(port, js) || [];
}

/**
 * DOM에서 작품 링크를 얻는다. 작품마다 textContent가 빈 표지 anchor와 제목 anchor가 흔히 함께 있다.
 * bookId로 묶어 가장 긴 비어 있지 않은 텍스트를 제목으로 써 빈 표지가 제목을 덮어 보충 전체가 실패하지 않게 한다.
 */
function extractBookUrls(port) {
  const js = `JSON.stringify((function(){
    function clean(t){return t.replace(/^[0-9]+\\[[^\\]]*\\]/,'').replace(/\\s+[0-9.]+(?:万|亿)?$/,'').trim();}
    var byId={};var order=[];
    Array.from(document.querySelectorAll('a[href*="/book/"]')).forEach(function(a){
      var h=a.getAttribute('href')||a.href||'';
      var m=h.match(/\\/book\\/([0-9]+)/);
      if(!m)return; var id=m[1];
      var t=clean((a.innerText||a.textContent||'').replace(/\\s+/g,' ').trim());
      if(!byId[id]){byId[id]='';order.push(id);}
      if(t&&t.length>byId[id].length)byId[id]=t;
    });
    return order.map(function(id){return {bookId:id,title:byId[id],url:'https://www.ciweimao.com/book/'+id};});
  })())`;
  return evalJSONBase64(port, js) || [];
}

// ---------------------------------------------------------------------------
// 렌더링
// ---------------------------------------------------------------------------

/** rank-index는 각 순위의 상위 10개를 표시한다. */
const RANK_SIZE = 10;

/**
 * 순위 하나의 Markdown. 머리의 ‘数据质量’, ‘问题摘要’에 항목 10개 미만 또는 작품 링크 일치율 절반 미만을 표시한다.
 * 1위는 작가만, 나머지는 장르만 있는 것은 실제 페이지 형식이므로 문제가 아니다.
 */
function renderRankFile(rt, entries, urls, now) {
  const norm = (s) => (s || "").replace(/\s+/g, "");
  const linkOf = (entry) => urls.find((u) => norm(u.title) === norm(entry.title));
  const linked = entries.filter((e) => linkOf(e)).length;
  const problems = [];
  if (entries.length < RANK_SIZE) problems.push(`只解析到 ${entries.length} 条（每榜 ${RANK_SIZE} 条）`);
  if (linked * 2 < entries.length) problems.push(`作品页链接只匹配到 ${linked} / ${entries.length} 条`);
  const lines = [
    `# 刺猬猫 · ${rt.label}`,
    "",
    `- 来源：${RANK_URL}`,
    `- 抓取时间：${now}`,
    `- 条目数：${entries.length}`,
    `- 作品页链接：${linked} / ${entries.length}`,
    `- 数据质量：${problems.length ? "[存在问题]" : "[OK]"}`,
    `- 问题摘要：${problems.length ? problems.join("；") : "无"}`,
    "",
    "---",
    "",
  ];

  for (const entry of entries) {
    lines.push(`### #${entry.rank} ${entry.title}`);
    const meta = [entry.author, entry.genre, entry.metric || ""].filter(Boolean).join(" · ");
    if (meta) lines.push(`*${meta}*`);
    const matched = linkOf(entry);
    if (matched) lines.push(`[作品页](${matched.url})`);
    lines.push("", "---", "");
  }
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// 주 처리 흐름
// ---------------------------------------------------------------------------

const args = process.argv.slice(2);
const PORT = parseInt(getArg(args, "--port") || "9222", 10);
const OUTDIR = getArg(args, "--outdir") || ".";
const RANKTYPE = getArg(args, "--type") || "all";

function main() {
  console.log("\n→ 采集 刺猬猫排行榜...");
  console.log(`  URL: ${RANK_URL}`);

  let sections, urls;
  try {
    ab(PORT, "open", RANK_URL);
    sleep(4000);

    // 연결 자체 검사: CDP 미실행·리디렉션은 구조 변경으로 오보하지 않고 대응 가능한 오류를 준다.
    const probe = probePage(PORT);
    if (!probe) {
      console.error(
        `  ✗ CDP 无响应。请确认已用 browser-cdp 启动 Chrome（端口 ${PORT}），且 agent-browser 可用。`
      );
      return 0;
    }
    if (probe.host && probe.host.indexOf("ciweimao") === -1) {
      console.error(`  ✗ 当前页面非刺猬猫（host=${probe.host}），可能被重定向，已跳过。`);
      return 0;
    }

    scrollLoad(PORT, 3);
    sleep(1000);

    sections = extractAllRanks(PORT);
    if (!sections.length) {
      // 지연 로딩이 실행되지 않았을 수 있으므로 스크롤 후 한 번 더 시도한다.
      scrollLoad(PORT, 2);
      sleep(1000);
      sections = extractAllRanks(PORT);
    }
    if (!sections.length) {
      console.error("[ciweimao] 采集失败：未解析到榜单（页面结构可能变动或未加载）。请人工打开榜单页确认。");
      return 0;
    }

    urls = extractBookUrls(PORT);
  } catch (err) {
    console.error(`[ciweimao] 采集失败（页面加载或提取阶段）: ${err.message}`);
    return 0;
  }

  console.log(`  ✓ 提取 ${sections.length} 个榜单，${urls.length} 个书籍链接`);

  // 필요한 순위 유형 선택
  const targetTypes =
    RANKTYPE === "all"
      ? RANK_TYPES
      : RANK_TYPES.filter((r) => r.id === RANKTYPE);

  let written = 0;
  for (const rt of targetTypes) {
    try {
      const section = sections.find((s) => s.name === rt.header);
      if (!section || !section.entries.length) {
        console.log(`  ⚠ ${rt.label} 无数据，跳过`);
        continue;
      }

      const content = renderRankFile(rt, section.entries, urls, new Date().toISOString());

      const filename = `刺猬猫${rt.label}_${localDateStamp()}.md`;
      fs.mkdirSync(OUTDIR, { recursive: true });
      const filepath = path.join(OUTDIR, filename);
      fs.writeFileSync(filepath, content, "utf-8");
      written++;
      console.log(`  ✓ ${rt.label}：${section.entries.length} 条 → ${filepath}`);
    } catch (rankErr) {
      console.error(`[ciweimao] ${rt.label} 处理出错，跳过: ${rankErr.message}`);
    }
  }
  return written;
}

if (require.main === module) {
  runCli(main, "刺猬猫采集");
}

module.exports = { renderRankFile };
