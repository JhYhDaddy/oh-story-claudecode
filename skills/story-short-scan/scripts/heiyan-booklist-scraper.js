#!/usr/bin/env node
/**
 * 헤이옌 단편 서고 목록 수집 스크립트
 *
 * ⚠️ 필수 사전 조건:
 *   1. Chrome CDP 환경 시작
 *   2. Chrome에서 https://manage.zhangwenpindu.cn 에 수동 로그인
 *      로그인하면 백엔드 API 호출에 필요한 Admin-Token 쿠키가 생성된다.
 *      미로그인 → Admin-Token을 감지하지 못했다는 오류 발생
 *
 * 수집 전략: 쿠키에서 Bearer 토큰을 추출해 ms.zhangwenpindu.cn 백엔드 API를 호출한다.
 * 제목, 작가, 글자 수, 분류, 태그 등의 구조화된 JSON 데이터를 얻는다.
 *
 * 사용법:
 *   node heiyan-booklist-scraper.js --pages 5                 # 앞 5페이지(페이지당 20개)
 *   node heiyan-booklist-scraper.js --pages 3 --channel male  # 남성향만
 *   node heiyan-booklist-scraper.js --pages 2 --detail        # 개별 상세 정보(태그 등) 포함
 */

const fs = require("fs");
const path = require("path");
const { ab, sleep, evalJSON, safeStr, getArg, localDateStamp, runCli } = require("./cdp-utils");

const BOOKLIST_URL = "https://manage.zhangwenpindu.cn/books/booklist";
const API_BASE = "https://ms.zhangwenpindu.cn";
const PAGE_SIZE = 20;

// ---------------------------------------------------------------------------
// API 호출
// ---------------------------------------------------------------------------

/** 연결 자체 점검: CDP 미연결과 연결됐으나 미로그인인 경우를 구분한다. */
function probePage(port) {
  return evalJSON(port, "JSON.stringify({host:location.host})");
}

/** 쿠키에서 Admin-Token을 추출한다. */
function getToken(port) {
  const js =
    "JSON.stringify((()=>{" +
    "var m=document.cookie.match(/Admin-Token=([^;]+)/);" +
    "return m?m[1]:''" +
    "})())";
  return evalJSON(port, js) || "";
}

/** 백엔드 API를 호출해 책 목록을 가져온다. */
function fetchBookList(port, token, pageNum) {
  const t = safeStr(token);
  const js =
    "fetch(" + safeStr(API_BASE + "/manage/book/list") + "," +
    "{method:'POST'," +
    "headers:{" +
    "'Content-Type':'application/x-www-form-urlencoded'," +
    "'Authorization':'Bearer '+" + t +
    "}," +
    "body:new URLSearchParams({pageNum:" + safeStr(pageNum) + ",pageSize:" + safeStr(PAGE_SIZE) + ",language:'zh_TW'})" +
    "}).then(function(r){return r.json()})";
  return evalJSON(port, js);
}

/** 백엔드 API를 호출해 책 상세 정보(태그 등)를 가져온다. */
function fetchBookDetail(port, token, bookId) {
  const t = safeStr(token);
  const js =
    "fetch(" + safeStr(API_BASE + "/manage/book/" + encodeURIComponent(bookId)) + "," +
    "{headers:{'Authorization':'Bearer '+" + t + "}}" +
    ").then(function(r){return r.json()})";
  return evalJSON(port, js);
}

// ---------------------------------------------------------------------------
// 주 처리 흐름
// ---------------------------------------------------------------------------

const args = process.argv.slice(2);
const PORT = parseInt(getArg(args, "--port") || "9222", 10);
const OUTDIR = getArg(args, "--outdir") || ".";
const PAGES = parseInt(getArg(args, "--pages") || "5", 10);
const CHANNEL = getArg(args, "--channel") || "all";
const DETAIL = args.includes("--detail");

/**
 * 글자 수 형식: 천 단위 구분을 직접 구현하며 toLocaleString()은 사용하지 않는다.
 * 호스트 ICU 로캘에 따라 de_*는 ‘123.456字’(123자로 오독 가능),
 * fr_*는 U+202F, en-IN은 ‘1,23,456’을 사용해 같은 보고서의 숫자가 기기마다 달라진다.
 * API가 words를 문자열로 반환하는 경우도 지원한다.
 */
function fmtWords(words) {
  const n =
    typeof words === "number"
      ? Math.trunc(words)
      : parseInt(String(words == null ? "" : words).replace(/[^0-9]/g, ""), 10);
  if (!Number.isFinite(n) || n <= 0) return "";
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ",") + "字";
}

function outputFilename(channel, date) {
  if (!["all", "male", "female"].includes(channel)) {
    throw new Error(`未知 --channel: ${channel}（支持 male/female/all）`);
  }
  return `黑岩书库列表_${channel}_${date}.md`;
}

/**
 * 파일 머리말의 데이터 품질: 서고에는 인기 필드가 없어 목록 모드는 책 목록만 제공한다.
 * --detail은 상세 정보 확보 비율에 따라 등급을 정한다.
 * 값이 aggregate-rank.js의 QUALITY_WORDS에 있어야 집계 수집 현황이 쉬운 표현으로 바뀐다.
 */
function dataQuality(books, detail) {
  if (!detail) return "[仅列表-无核心指标]";
  const got = books.filter((b) => b && b.detailOk).length;
  if (got === books.length) return "[OK]";
  return got / books.length < 0.5 ? "[详情解析异常/登录态缺失]" : "[部分详情缺失]";
}

function buildAndSave(allBooks, total, filtered, filepath, detail = DETAIL) {
  const now = new Date().toISOString();
  const maleBooks = filtered.filter((b) => b.classifyStr === "男频");
  const femaleBooks = filtered.filter((b) => b.classifyStr === "女频");
  const otherBooks = filtered.filter(
    (b) => b.classifyStr !== "男频" && b.classifyStr !== "女频"
  );

  const groups = [
    { label: "男频", books: maleBooks },
    { label: "女频", books: femaleBooks },
  ];
  if (otherBooks.length) {
    groups.push({ label: "其他", books: otherBooks });
  }

  const lines = [
    `# 黑岩 · 书库列表`,
    "",
    `- 来源：${BOOKLIST_URL}`,
    `- 抓取时间：${now}`,
    `- 总条目：${total}`,
    `- 已采集：${filtered.length} 条（${Math.ceil(allBooks.length / PAGE_SIZE)} 页）`,
    detail ? "- 含详情（标签、简介）" : "- 列表模式（加 --detail 获取标签和简介）",
    `- 数据质量：${dataQuality(filtered, detail)}`,
    "",
    "---",
    "",
  ];

  for (const g of groups) {
    if (!g.books.length) continue;
    lines.push(`## ${g.label}短篇 — ${g.books.length} 本`, "");

    for (let i = 0; i < g.books.length; i++) {
      try {
        const b = g.books[i];
        lines.push(`### #${i + 1} ${b.name}`);
        // 집계는 위치로 ‘작가 · 소재’를 판별한다. 작가가 없으면 자리표시자를 넣어 소재를 작가로 오인하지 않게 한다.
        const meta = [
          b.userName || "佚名",
          // 각각 배열에 넣은 뒤 합친다. classifyStr + "/" + typeDesc를 먼저 하면 누락 필드가
          // ‘undefined/undefined’ 같은 참인 문자열이 되어 filter(Boolean)을 통과하고 보고서에 그대로 들어간다.
          [b.classifyStr, b.typeDesc].filter(Boolean).join("/"),
          fmtWords(b.words),
          b.price ? b.price + "钻" : "",
          b.open ? "公开" : "未公开",
        ].filter(Boolean).join(" · ");
        if (meta) lines.push(`*${meta}*`);

        if (b.createTime) lines.push(`**创建：** ${b.createTime}`);
        if (b.updateTime) lines.push(`**更新：** ${b.updateTime}`);

        if (b.tags && b.tags.length) {
          lines.push(`**标签：** ${b.tags.join("、")}`);
        }

        if (b.description) {
          lines.push("");
          lines.push(`> ${b.description.substring(0, 200)}${b.description.length > 200 ? "..." : ""}`);
        }

        lines.push("");
      } catch (bookErr) {
        console.error(`[heiyan] ${g.label} 第${i + 1}条处理出错: ${bookErr.message}`);
        lines.push("");
      }
    }

    lines.push("---", "");
  }

  fs.mkdirSync(OUTDIR, { recursive: true });
  fs.writeFileSync(filepath, lines.join("\n"), "utf-8");
  console.log(`  ✓ 已保存: ${filepath}`);
}

function main() {
  console.log("\n→ 采集 黑岩书库列表（API 模式）...");
  console.log(`  计划采集: ${PAGES} 页（每页 ${PAGE_SIZE} 条）`);

  const filename = outputFilename(CHANNEL, localDateStamp());
  const filepath = path.join(OUTDIR, filename);

  // 먼저 관리 화면으로 이동해 토큰을 얻는다.
  let token;
  try {
    ab(PORT, "open", BOOKLIST_URL);
    sleep(3000);

    // 연결 자체 점검: CDP 미실행과 미로그인을 구분해 불필요한 로그인을 안내하지 않는다.
    const probe = probePage(PORT);
    if (!probe) {
      console.error(
        `  ✗ CDP 无响应。请确认已用 browser-cdp 启动 Chrome（端口 ${PORT}），且 agent-browser 可用。`
      );
      return 0;
    }

    token = getToken(PORT);
  } catch (err) {
    console.error(`[heiyan] 页面加载或 token 提取出错: ${err.message}`);
    return 0;
  }

  if (!token) {
    console.log("  ✗ 未检测到 Admin-Token（CDP 已连，但当前未登录）");
    console.log("  → 请先在 Chrome 中打开 https://manage.zhangwenpindu.cn 并登录");
    console.log("  → 登录后重新运行本脚本");
    return 0;
  }
  console.log("  ✓ 获取到认证 token");

  // 페이지별 수집
  const allBooks = [];
  let total = 0;

  for (let p = 1; p <= PAGES; p++) {
    try {
      sleep(800);
      const resp = fetchBookList(PORT, token, p);

      // 실패 구분: API 무응답(시간 초과/CDP) / 401 인증되지 않음
      if (!resp) {
        console.error(`  ✗ 第${p}页接口无响应（请求超时或 CDP 中断），已停止。`);
        break;
      }
      if (resp.code === 401) {
        console.log(`  ⚠ 第${p}页认证失败（401），请重新登录后重试。`);
        break;
      }

      const rows = resp?.data?.rows;
      if (!rows || !rows.length) {
        // 데이터가 없을 때만 code로 서버 오류와 정상적인 끝을 구분한다. 비표준 성공 code를
        // 포함한 유효 응답을 오류로 오인하지 않도록 한다(rows를 포함한 성공 응답은 모두 허용).
        if (resp.code != null && resp.code !== 0 && resp.code !== 200) {
          console.error(`  ✗ 第${p}页接口返回错误 code=${resp.code} ${resp.msg || ""}，已停止。`);
        } else {
          console.log(`  第${p}页无数据，停止`);
        }
        break;
      }

      if (p === 1) {
        total = parseInt(resp.data.total) || 0;
        console.log(`  总条目: ${total}`);
      }

      allBooks.push(...rows);
      console.log(`  第${p}页: ${rows.length} 条 (累计 ${allBooks.length})`);
    } catch (pageErr) {
      console.error(`[heiyan] 第${p}页采集出错，跳过: ${pageErr.message}`);
      if (allBooks.length > 0) {
        console.log(`  已采集 ${allBooks.length} 条，继续处理已有数据`);
      }
      break;
    }
  }

  if (!allBooks.length) {
    console.error("[heiyan] 采集失败：未取到任何书目。多为登录态过期或接口变动，请重新登录后重试。");
    return 0;
  }

  // 품질 검사: 핵심 필드 적중률. API 필드명이 바뀌면 모두 undefined가 되므로 조용히 저장하지 말고 차단해야 한다.
  // classifyStr도 검사한다. 남성향/여성향 분류와 --channel 필터를 결정하므로 필드가 바뀌면 모든 책이
  // 기타로 분류되고 --channel male 결과가 0개가 되어 ‘수집 완료: 0개’라는 거짓 성공 보고서가 생성된다.
  const CORE_FIELDS = [
    { key: "name", label: "书名" },
    { key: "classifyStr", label: "频道(classifyStr)" },
  ];
  for (const f of CORE_FIELDS) {
    const hit = allBooks.filter((b) => b && b[f.key]).length;
    if (hit / allBooks.length < 0.5) {
      console.error(
        `[heiyan] 采集失败：${allBooks.length} 条里仅 ${hit} 条有${f.label}，疑似接口字段变动，已放弃写盘。`
      );
      return 0;
    }
  }

  // 채널 필터
  let filtered = allBooks;
  if (CHANNEL === "male" || CHANNEL === "female") {
    const want = CHANNEL === "male" ? "男频" : "女频";
    filtered = allBooks.filter((b) => b.classifyStr === want);
    if (!filtered.length) {
      // 필터 결과 0개는 성공이 아니다. 실제 classifyStr 분포를 출력해 API 필드 변경과
      // 해당 채널에 작품이 실제로 없는 경우를 구분한다. 둘을 구분할 수 없는 빈 보고서를 쓰지 않는다.
      const seen = {};
      for (const b of allBooks) {
        const k = b && b.classifyStr ? b.classifyStr : "(空)";
        seen[k] = (seen[k] || 0) + 1;
      }
      const dist = Object.keys(seen).map((k) => `${k}×${seen[k]}`).join("、");
      console.error(
        `[heiyan] 采集失败：--channel ${CHANNEL} 筛选后 0 条（${allBooks.length} 条的 classifyStr 取值：${dist}），已放弃写盘。`
      );
      console.error(`  → 若确实没有${want}作品，去掉 --channel 重跑即可拿到全部书目。`);
      return 0;
    }
  }

  // 선택 사항: 책별 상세 정보(태그 등)를 가져온다.
  if (DETAIL && filtered.length) {
    console.log(`  获取 ${filtered.length} 本详情...`);
    for (let i = 0; i < filtered.length; i++) {
      try {
        sleep(500);
        const detail = fetchBookDetail(PORT, token, filtered[i].id);
        if (detail?.data) {
          filtered[i].tags = detail.data.tags || [];
          filtered[i].description = detail.data.description || "";
          filtered[i].chapterCount = detail.data.chapterCount || 0;
          filtered[i].detailOk = true;
        }
        if ((i + 1) % 10 === 0) {
          console.log(`    已获取 ${i + 1}/${filtered.length}`);
        }
      } catch (detailErr) {
        console.error(`[heiyan] 第${i + 1}本详情获取出错，跳过: ${detailErr.message}`);
      }
    }
    console.log("  ✓ 详情获取完成");
  }

  buildAndSave(allBooks, total, filtered, filepath);
  return 1;
}

if (require.main === module) {
  runCli(main, "黑岩采集");
}

module.exports = {
  probePage,
  getToken,
  fetchBookList,
  fetchBookDetail,
  fmtWords,
  outputFilename,
  dataQuality,
  buildAndSave,
};
