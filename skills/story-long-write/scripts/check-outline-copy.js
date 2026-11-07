#!/usr/bin/env node
/**
 * check-outline-copy.js — 상세 개요 베끼기 탐지.
 * 개요의 플롯 포인트를 완성된 산문으로 써 본문이 필사만 하게 되면 품질이 개요 수준에 고정된다.
 * 실측에서 연속 중복은 최대 13.5%, 가장 긴 구간은 40자였고 대부분 대사가 아닌 서술이었다. 장의 좋은 문장을 개요 단계에서 이미 써 버린 것이다.
 * 본문과 같은 장 개요의 연속 중복이 기준(기본 15자)을 넘으면 보고한다. 개요는 기능·결과만 확정하고 문장은 본문 작성 때 만든다.
 * 같은 표현이 모두 나쁜 복사는 아니다. 시스템 패널·과제·고유명은 같아야 하므로 스크립트는 위치·구간 증거만 주고 agent가 문맥으로 수정 여부를 판단한다.
 * check-ai-patterns.js advisory처럼 모든 항목에 결론이 필요하며 보고만 하거나 0건을 만들기 위해 기계적으로 고치면 안 된다.
 * 유지할 문장은 주 세션만 개요의 반복 기준 문장에 추가한다. 하위 에이전트는 개요를 고치지 않는다(narrative-writer의 자체 개요 수정 금지).
 * 스스로 허용 목록에 넣으면 오판한 중복이 주 세션 재검사에서 사라져 두 번째 검토가 무력화되기 때문이다.
 * 면제: 개요 ‘复沓锚句’에 행당 하나로 적힌 맹세·시스템 패널·과거 사건 원문 등은 그대로 쓸 수 있다.
 * 기준 문장 자체의 정확한 구간만 빼며 앞뒤 중복은 계속 판정한다. 면제량을 따로 집계해 보고서 끝에 표시하여 남용을 드러낸다.
 * narrative-writer 저장 후 자체 검사와 주 세션 마무리 재검사에서 같은 구현을 호출한다. 네 호스트 공유 핵심 훅을 이 검사 하나 때문에 확장하지 않는다.
 * 사용법:
 *   node check-outline-copy.js <본문경로...>                    # 같은 장 개요 자동 검색, 단편은 같은 디렉터리 소절 개요
 *   node check-outline-copy.js --outline <상세개요경로> <본문경로...> # 개요 지정
 * 위치 인자는 check-ai-patterns.js의 `<file...>`처럼 모두 본문이다. `본문/제XXX장_*.md`로 여러 장을 넘길 때 추가 본문을 개요로 삼으면
 * 첫 파일은 잘못 비교하고 나머지는 검사하지 않은 채 0으로 종료해 깨끗하다고 오보하므로 허용하지 않는다.
 * 종료: 0=깨끗함 또는 개요 자동 검색 실패로 건너뜀, 1=검토할 중복, 2=인자 오류·입력(찾은 개요 포함) 읽기 실패·예상 밖 예외.
 * 깨끗하면 조용히 종료하며 개요를 못 찾으면 검사를 건너뛰었다고 명시해 실제 검사 완료와 구분한다.
 */

'use strict'
const fs = require('fs')
const path = require('path')

const MIN_RUN = 16 // 판정 기준: 연속 중복 >15자, 즉 >=16자.
const REPORT_TOP = 8 // 나열할 최대 구간 수.

function readTextFile(p) {
  try {
    const stat = fs.statSync(p)
    if (!stat.isFile()) return { ok: false, reason: '不是普通文件' }
    return { ok: true, text: fs.readFileSync(p, 'utf8').replace(/^﻿/, '') }
  } catch (error) {
    if (error && error.code === 'ENOENT') return { ok: false, reason: '不存在' }
    if (error && error.code) return { ok: false, reason: `无法读取（${error.code}）` }
    return { ok: false, reason: `无法读取：${error instanceof Error ? error.message : String(error)}` }
  }
}

function reportInputError(kind, file, reason) {
  process.stderr.write(`错误: 无法读取${kind} "${file}"：${reason}。\n`)
}

function reportUsageError(message) {
  process.stderr.write(`错误: ${message}。\n`)
  process.stderr.write('用法: node check-outline-copy.js [--outline <细纲路径>] <正文路径...>\n')
  return 2
}

/** 한자만 남긴다. 문장부호·강조·【】를 제거해 개요 표기 때문에 거짓 음성이 생기지 않게 한다. */
function hanOnly(s) {
  return s.replace(/[^一-鿿]/g, '')
}

// 작성 후 채운 완료 기록은 필사 출처가 아니다. 제목 블록은 하위 제목을 포함하고 필드 블록은 다음 필드·제목에서 끝난다.
function stripCompletionRecord(outline) {
  let headingLevel = 0
  let inField = false
  return outline.split('\n').filter((line) => {
    const heading = line.match(/^ {0,3}(#{1,6})[\t ]+(.*)$/)
    if (headingLevel) {
      if (!heading || heading[1].length > headingLevel) return false
      headingLevel = 0
    }
    if (inField) {
      if (!heading && !/^[-*+][\t ]+/.test(line)) return false
      inField = false
    }
    if (heading && heading[2].includes('实际完成情况')) {
      headingLevel = heading[1].length
      return false
    }
    if (/^[-*+][\t ]+(?:\*\*|__)?实际完成情况[^：:]*[：:]/.test(line)) {
      inField = true
      return false
    }
    return true
  }).join('\n')
}

/**
 * 개요 ‘复沓锚句’ 아래 원문을 행당 하나씩 추출한다. 이 필드만 인식하고 플롯 포인트 배열은 검사하지 않는다.
 * 기준 문장을 고정 블록에 모아 플롯 포인트는 일어날 일만 쓰게 한다.
 * 블록은 들여쓰지 않은 다음 필드(`- xxx`) 또는 다음 소제목에서 끝나므로 `1.` 번호·들여쓴 `-` 목록·일반 텍스트를 별도 표식 없이 추출한다.
 */
function extractAnchors(outline) {
  const m = outline.match(/复沓锚句[^：:\n]*[：:]([\s\S]*?)(?=\n[-*+]\s|\n#{1,6}\s|$)/)
  if (!m) return []
  return m[1]
    .split("\n")
    // 목록 기호와 ‘点N：’ 같은 위치 접두사를 제거해 원문만 남긴다.
    .map((line) => line.replace(/^\s*[-*+]?\s*(?:\d+[.、)]\s*)?(?:点\s*\d+\s*[：:])?/, ""))
    .map((line) => hanOnly(line))
    .filter((a) => a.length >= 2)
}

/**
 * 구간에서 기준 문장의 정확한 위치를 제거하고 남은 하위 구간·면제 글자 수를 반환한다.
 * 기준 문장을 포함한다는 이유로 전체를 허용하면 안 된다. 탐욕 검사는 최장 구간을 찾으므로 중간 기준 문장에 붙은 비허용 중복까지 면제할 수 있다.
 */
function splitByAnchors(frag, anchors) {
  // 구간이 기준 문장 안에 완전히 포함되면 전체 면제다. 일부 복사도 허용 범위다.
  if (anchors.some((a) => a.includes(frag))) return { rest: [], anchoredLen: frag.length }

  const spans = []
  for (const a of anchors) {
    for (let from = 0; from + a.length <= frag.length; ) {
      const at = frag.indexOf(a, from)
      if (at < 0) break
      spans.push([at, at + a.length])
      from = at + 1 // 같은 기준 문장 반복도 매번 기록한다.
    }
  }
  if (!spans.length) return { rest: [frag], anchoredLen: 0 }

  spans.sort((x, y) => x[0] - y[0])
  const merged = [spans[0]] // 여러 기준 문장이 겹치거나 붙으면 하나로 합쳐 중복 계산을 피한다.
  for (const [s, e] of spans.slice(1)) {
    const last = merged[merged.length - 1]
    if (s <= last[1]) last[1] = Math.max(last[1], e)
    else merged.push([s, e])
  }

  const rest = []
  let cursor = 0
  let anchoredLen = 0
  for (const [s, e] of merged) {
    if (s > cursor) rest.push(frag.slice(cursor, s))
    anchoredLen += e - s
    cursor = e
  }
  if (cursor < frag.length) rest.push(frag.slice(cursor))
  return { rest, anchoredLen }
}

/** 개요/를 순회해 장 번호 정규식으로 같은 장 개요를 찾으며 접미사 파일명도 지원한다. */
function findOutline(proseFile) {
  const base = path.basename(proseFile)
  // 단편에는 장 번호가 없으며 본문.md와 구간개요.md가 같은 디렉터리에 있다.
  if (base === '본문.md') {
    const sibling = path.join(path.dirname(proseFile), '구간개요.md')
    return fs.existsSync(sibling) ? sibling : null
  }
  const m = base.match(/^제\s*0*(\d+)\s*장/)
  if (!m) return null
  const chapter = m[1]
  const dir = path.join(path.dirname(path.dirname(proseFile)), '개요')
  try {
    for (const file of fs.readdirSync(dir)) {
      const fm = file.match(/^상세개요_제0*(\d+)장.*\.md$/)
      if (fm && fm[1] === chapter) return path.join(dir, file)
    }
  } catch (error) {
    if (error.code !== 'ENOENT') throw error
  }
  return null
}

function main() {
  const proseFiles = []
  let explicitOutline = null
  const argv = process.argv.slice(2)
  let positionalOnly = false
  for (let k = 0; k < argv.length; k++) {
    const arg = argv[k]
    if (!positionalOnly && arg === '--') {
      positionalOnly = true
    } else if (!positionalOnly && arg === '--outline') {
      if (explicitOutline !== null) return reportUsageError('--outline 不能重复指定')
      const value = argv[k + 1]
      if (!value || value.startsWith('--')) return reportUsageError('--outline 缺少路径')
      explicitOutline = value
      k++
    } else if (!positionalOnly && arg.startsWith('--')) {
      return reportUsageError(`未知选项: ${arg}`)
    } else {
      proseFiles.push(arg)
    }
  }
  if (!proseFiles.length) return reportUsageError('缺少正文路径')

  // 파일별 독립 판정. 입력 오류를 중복 발견보다 우선한다.
  let status = 0
  for (const proseFile of proseFiles) {
    status = Math.max(status, checkOne(proseFile, explicitOutline))
  }
  return status
}

function checkOne(proseFile, explicitOutline) {
  const proseResult = readTextFile(proseFile)
  if (!proseResult.ok) {
    reportInputError('正文', proseFile, proseResult.reason)
    return 2
  }
  const prose = proseResult.text

  const outlineFile = explicitOutline || findOutline(proseFile)
  if (!outlineFile) {
    process.stdout.write(`细纲照搬检测：跳过 "${proseFile}"（未自动发现细纲）。\n`)
    return 0
  }
  const outlineResult = readTextFile(outlineFile)
  if (!outlineResult.ok) {
    reportInputError(explicitOutline ? '显式细纲' : '自动发现的细纲', outlineFile, outlineResult.reason)
    return 2
  }
  const outline = outlineResult.text

  // 본문 제목 행을 제거한 뒤 비교한다.
  const P = hanOnly(prose.replace(/^#.*$/gm, ''))
  const O = hanOnly(stripCompletionRecord(outline))
  if (P.length < MIN_RUN || O.length < MIN_RUN) return 0

  // 반복 기준 문장의 원문은 그대로 써도 되므로 적중하면 면제로 세고 필사로 보지 않는다.
  const anchors = extractAnchors(outline)

  // 탐욕 검사: 시작점마다 개요의 부분 문자열인 최장 구간을 이진 탐색한다. 적중 구간은 겹치지 않는다.
  const hits = []
  let copied = 0
  let anchored = 0
  let anchoredCount = 0
  let i = 0
  while (i < P.length) {
    let best = 0
    if (i + MIN_RUN <= P.length && O.includes(P.substr(i, MIN_RUN))) {
      best = MIN_RUN
      let lo = MIN_RUN
      let hi = Math.min(P.length - i, 200)
      while (lo <= hi) {
        const mid = (lo + hi) >> 1
        if (O.includes(P.substr(i, mid))) {
          best = mid
          lo = mid + 1
        } else hi = mid - 1
      }
    }
    if (best) {
      const frag = P.substr(i, best)
      const { rest, anchoredLen } = splitByAnchors(frag, anchors)
      if (anchoredLen) {
        anchored += anchoredLen
        anchoredCount++
      }
      // 기준 문장 제거 후 남은 부분도 개요 부분 문자열이므로 기준 길이만 다시 판정한다.
      for (const seg of rest) {
        if (seg.length >= MIN_RUN) {
          hits.push({ frag: seg, len: seg.length })
          copied += seg.length
        }
      }
      i += best
    } else i++
  }
  if (!hits.length) {
    // 전부 기준 문장 면제이면 조용히 통과시키되 남용 검토를 위해 면제량은 보고한다.
    if (anchoredCount) {
      process.stdout.write(
        `细纲照搬检测（${path.basename(proseFile)}）：无未授权誊抄；` +
          `另有 ${anchoredCount} 处 ${anchored} 字为复沓锚句的逐字落地。\n`
      )
    }
    return 0
  }

  const rate = ((copied * 100) / P.length).toFixed(1)
  // 단편은 상세 개요가 없어 구간개요.md 끝에 기준 문장을 등록한다. 안내는 단편에 맞추고 장편 원문은 유지한다.
  const isShort = path.basename(outlineFile) === '구간개요.md'
  const guidance = isShort
    ? `逐条对照原文判断：确属把小节大纲叙述搬进正文就重写——大纲只锁功能与结果，句子在正文现场写；誓词、关键原话、固定专名等功能性重合可保留。每条都要有结论，不为归零机械改写。保留项由主会话登记进小节大纲.md 末尾「复沓锚句：」行下（每行一条原话，缩进写）再复检——子代理只重写正文或标 \`[需复核]\` 交回，不改小节大纲。`
    : `逐条对照原文判断：确属把细纲叙述搬进正文就重写——细纲只锁功能与结果，句子在正文现场写；系统面板、誓词、案卷原话、固定专名等功能性重合可保留。每条都要有结论，不为归零机械改写。保留项由主会话补进细纲「复沓锚句」——子代理只重写正文或标 \`[需复核]\` 交回，不改大纲细纲。`
  const out = [
    `=== ${isShort ? '小节大纲' : '细纲'}照搬检测（${path.basename(proseFile)}）===`,
    `正文 ${P.length} 字，与 ${path.basename(outlineFile)} 连续重合 >${MIN_RUN - 1} 字的片段 ${hits.length} 处，共 ${copied} 字（${rate}%）。`,
    guidance,
  ]
  hits
    .sort((a, b) => b.len - a.len)
    .slice(0, REPORT_TOP)
    .forEach((h) => out.push(`  · ${h.len} 字「${h.frag}」`))
  if (hits.length > REPORT_TOP) out.push(`  · …另有 ${hits.length - REPORT_TOP} 处`)
  if (anchoredCount) out.push(`（另有 ${anchoredCount} 处 ${anchored} 字为复沓锚句的逐字落地，不计入誊抄）`)
  process.stdout.write(out.join('\n') + '\n')
  return 1
}

try {
  process.exit(main())
} catch (error) {
  const message = error instanceof Error ? error.message : String(error)
  process.stderr.write(`错误: 细纲照搬检测异常：${message}。\n`)
  process.exit(2)
}
