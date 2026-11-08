#!/usr/bin/env node
'use strict'

const assert = require('assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const { spawnSync } = require('child_process')

const repoRoot = path.resolve(__dirname, '..')
const verifier = path.join(repoRoot, 'skills/story-short-write/scripts/check-phase2-contract.js')
const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'phase2-contract-'))

// 현재 열 이름. 새 프로젝트는 이 집합을 써야 한다(check-phase2-contract.js의 currentHeader 분기).
const headers = [
  '结构段/五段功能', '主事件', '情节推进', '情绪', '인물/关系变化', '因果/逻辑链',
  '读者新获知什么', '结尾承接/钩子', '伏笔/物件', '场景形态', '对白作用', '目标字数',
]

// v0.7.8 이하 프로젝트에 저장된 이전 열 이름도 변경 후 계속 허용해야 한다(legacyHeader 분기).
const legacyHeaders = headers.map(
  (name, index) => ({ 2: '子事件×3-5', 9: '动静', 10: '对话密度' }[index] || name)
)

const threeUnitProgression = (index) =>
  `主角发现线索${index}{发现}->对手阻拦行动${index}{冲突}->主角留下证据${index}{伏笔}`

function outlineRow(stage, index, hook, { legacy = false, progression = threeUnitProgression } = {}) {
  return [
    stage,
    `主角处理事件${index}`,
    progression(index),
    `疑惑→紧张${index}`,
    `关系压力上升${index}`,
    `发现异常${index} → 调查 → 受阻 → 决定继续`,
    `读者获知线索${index}`,
    hook,
    `旧钥匙${index}`,
    legacy ? (index % 2 ? '动' : '静') : (index % 2 ? '行动' : '证据核验'),
    legacy ? (index % 2 ? '高' : '中') : (index % 2 ? '推动策略' : '无对白，由物件推进'),
    '1000',
  ]
}

function validSettings(overrides = {}) {
  const values = {
    platform: '知乎盐言',
    genre: 'references/genre-styles/悬疑.md',
    moves: '日常违和切入；延迟剥洋葱；证物翻转',
    villain: '反派设计：不适用（冲突来自主角对自我记忆的误判）',
    reversalType: '信息反转',
    reversal: '反转位置：第 6 节 ÷ 共 8 节 = 75%',
    paywall: '付费点：第 4 节末',
    target: '8000',
    ...overrides,
  }
  return [
    '# 设定',
    '## 基本信息',
    `- 目标平台：${values.platform}`,
    `- 目标字数：${values.target} 字`,
    '## Phase 2 设计校验',
    `- 题材参考：\`${values.genre}\``,
    `- 核心招式：${values.moves}`,
    `- ${values.villain}`,
    `- 反转类型：${values.reversalType}`,
    `- ${values.reversal}`,
    `- ${values.paywall}`,
    '',
  ].join('\n')
}

function validOutline({ includePaywall = true, headerRow = headers, ...rowOpts } = {}) {
  const rows = [
    outlineRow('开头', 1, '她决定去查监控', rowOpts),
    outlineRow('铺垫', 2, '她收到没有寄件人的照片', rowOpts),
    outlineRow('铺垫', 3, '照片背后写着她的旧名', rowOpts),
    outlineRow('升级', 4, includePaywall ? '门后传来自己的声音（付费点）' : '门后传来自己的声音', rowOpts),
    outlineRow('升级', 5, '旧照片上的人动了', rowOpts),
    outlineRow('反转', 6, '她发现记忆属于另一个人', rowOpts),
    outlineRow('反转', 7, '真正的主人敲响房门', rowOpts),
    outlineRow('结尾', 8, '她把钥匙留在门外', rowOpts),
  ]
  return [
    '# 小节大纲',
    `| ${headerRow.join(' | ')} |`,
    `| ${headerRow.map(() => '---').join(' | ')} |`,
    ...rows.map((row) => `| ${row.join(' | ')} |`),
    '',
  ].join('\n')
}

function writeCase(name, settings, outline) {
  const dir = path.join(tmpRoot, name)
  fs.mkdirSync(dir, { recursive: true })
  if (settings !== null) fs.writeFileSync(path.join(dir, '설정.md'), settings, 'utf8')
  if (outline !== null) fs.writeFileSync(path.join(dir, '구간개요.md'), outline, 'utf8')
  return dir
}

function run(dir, extraArgs = []) {
  const result = spawnSync(process.execPath, [verifier, '--json', ...extraArgs, dir], {
    cwd: repoRoot,
    encoding: 'utf8',
  })
  let report = null
  if (result.stdout.trim()) report = JSON.parse(result.stdout)
  return { ...result, report }
}

function failureIds(result) {
  return result.report.failures.map((failure) => failure.id)
}

try {
  const good = run(writeCase('valid', validSettings(), validOutline()))
  assert.strictEqual(good.status, 0, good.stdout + good.stderr)
  assert.strictEqual(good.report.ok, true)
  assert.deepStrictEqual(good.report.failures, [])

  // 플랫폼 표의 여섯 플랫폼을 모두 인식해야 한다. 기존 ‘知乎盐选’, ‘盐选’, ‘番茄短篇’도 통과하며 미정인 작가는 ‘未定’을 쓴다.
  for (const platform of ['番茄', '七猫', '黑岩', '红果', '小程序', '点众', '盐言', '知乎盐选', '盐选', '番茄短篇', '未定']) {
    const named = run(writeCase(`platform-${platform}`, validSettings({ platform }), validOutline()))
    assert.strictEqual(named.status, 0, named.stdout + named.stderr)
    assert.strictEqual(
      named.report.checks.find((check) => check.id === 'phase2.platform-declared').evidence,
      `目标平台：${platform}`
    )
  }
  const unknownPlatform = run(writeCase('platform-unknown', validSettings({ platform: '起点' }), validOutline()))
  assert.strictEqual(unknownPlatform.status, 1)
  assert.deepStrictEqual(failureIds(unknownPlatform), ['phase2.platform-declared'])

  // 기존 프로젝트에 저장된 세 이전 열 이름도 계속 통과해야 한다(legacyHeader 호환 분기).
  const legacyHeaderOutline = run(writeCase(
    'legacy-headers',
    validSettings(),
    validOutline({ headerRow: legacyHeaders, legacy: true })
  ))
  assert.strictEqual(legacyHeaderOutline.status, 0, legacyHeaderOutline.stdout + legacyHeaderOutline.stderr)
  assert.strictEqual(legacyHeaderOutline.report.ok, true)
  assert.match(
    legacyHeaderOutline.report.checks.find((check) => check.id === 'phase2.outline-12-columns').evidence,
    /兼容旧项目/
  )

  // 새 열 이름과 이전 열 이름을 섞은 것은 유효한 머리글이 아니다. currentHeader와 legacyHeader 모두 거부해야 한다.
  const mixedHeaderOutline = run(writeCase(
    'mixed-headers',
    validSettings(),
    validOutline({ headerRow: headers.map((name, index) => (index === 2 ? '子事件×3-5' : name)) })
  ))
  assert.strictEqual(mixedHeaderOutline.status, 1)
  assert(failureIds(mixedHeaderOutline).includes('phase2.outline-12-columns'))

  // ‘하위 사건 3-5개’ 할당량을 없앴으므로 절마다 실제 진전이 하나뿐이어도 통과해야 한다.
  const singleUnit = run(writeCase(
    'single-progression-unit',
    validSettings(),
    validOutline({ progression: (index) => `主角当场亮出证据${index}{发现}` })
  ))
  assert.strictEqual(singleUnit.status, 0, singleUnit.stdout + singleUnit.stderr)
  assert.strictEqual(singleUnit.report.ok, true)

  // 개수 하한이 없다는 것이 빈칸이나 기능 레이블 누락을 허용한다는 뜻은 아니다.
  const emptyProgression = run(writeCase(
    'empty-progression',
    validSettings(),
    validOutline({ progression: () => '' })
  ))
  assert.strictEqual(emptyProgression.status, 1)
  assert(failureIds(emptyProgression).includes('phase2.outline-subevents'))

  const untaggedProgression = run(writeCase(
    'untagged-progression',
    validSettings(),
    validOutline({ progression: (index) => `主角当场亮出证据${index}` })
  ))
  assert.strictEqual(untaggedProgression.status, 1)
  assert(failureIds(untaggedProgression).includes('phase2.outline-subevents'))

  const explicitShortTarget = run(writeCase(
    'explicit-short-target',
    validSettings({ target: '6000' }),
    validOutline().replaceAll('| 1000 |', '| 750 |')
  ))
  assert.strictEqual(explicitShortTarget.status, 0, explicitShortTarget.stdout + explicitShortTarget.stderr)

  // 사용자가 글자 수 범위를 주면 개요 합계가 그 안에 들어갈 때 통과한다.
  const rangeTarget = run(writeCase(
    'range-target',
    validSettings({ target: '6000-8000 字' }),
    validOutline().replaceAll('| 1000 |', '| 900 |')
  ))
  assert.strictEqual(rangeTarget.status, 0, rangeTarget.stdout + rangeTarget.stderr)
  assert.strictEqual(rangeTarget.report.ok, true)

  const rangeTargetOutside = run(writeCase(
    'range-target-outside',
    validSettings({ target: '6000-8000 字' }),
    validOutline().replaceAll('| 1000 |', '| 500 |')
  ))
  assert.strictEqual(rangeTargetOutside.status, 1)
  assert.deepStrictEqual(failureIds(rangeTargetOutside), ['phase2.target-word-sum'])
  assert.match(rangeTargetOutside.report.failures[0].evidence, /6000-8000/)

  // ‘万’ 단위로 쓴 목표 글자 수는 정수로 환산한 뒤 비교한다.
  for (const [name, target] of [['wan-range', '约 0.75-0.9 万'], ['wan-single', '0.8万']]) {
    const wan = run(writeCase(name, validSettings({ target }), validOutline()))
    assert.strictEqual(wan.status, 0, wan.stdout + wan.stderr)
  }

  // 채우지 않은 템플릿 자리표시자는 설계 완료로 인정하지 않는다.
  const placeholders = run(writeCase(
    'unfilled-placeholders',
    validSettings({
      moves: '{招式一}；{招式二}；{招式三}',
      reversalType: '{身份/视角/动机/시간선/信息/认知/无反转}',
    }),
    validOutline()
  ))
  assert.strictEqual(placeholders.status, 1)
  assert(failureIds(placeholders).includes('phase2.no-template-placeholders'))

  const missingSettings = run(writeCase('missing-settings', null, validOutline()))
  assert.strictEqual(missingSettings.status, 1)
  assert(failureIds(missingSettings).includes('phase2.settings-readable'))

  const badGenre = run(writeCase(
    'bad-genre-reference',
    validSettings({ genre: 'references/genre-styles/不存在.md' }),
    validOutline()
  ))
  assert.strictEqual(badGenre.status, 1)
  assert.deepStrictEqual(failureIds(badGenre), ['phase2.genre-reference-declared'])
  assert.match(badGenre.report.failures[0].evidence, /不存在\.md/)

  // 기법 설명 안의 모점/쉼표는 기법 내부 설명이며 세미콜론만 기법 사이 구분자다.
  const movesWithInnerPunctuation = run(writeCase(
    'moves-with-inner-punctuation',
    validSettings({ moves: '白月光触发链（旧物、旧地、旧称呼三连触发）；信物翻转，从定情物变成证据；火葬场预告' }),
    validOutline()
  ))
  assert.strictEqual(movesWithInnerPunctuation.status, 0, movesWithInnerPunctuation.stdout + movesWithInnerPunctuation.stderr)
  assert.strictEqual(movesWithInnerPunctuation.report.ok, true)

  const tooFewMoves = run(writeCase(
    'too-few-moves',
    validSettings({ moves: '只有一个招式' }),
    validOutline()
  ))
  assert.strictEqual(tooFewMoves.status, 1)
  assert.deepStrictEqual(failureIds(tooFewMoves), ['phase2.genre-moves-declared'])

  const noReason = run(writeCase(
    'villain-no-reason',
    validSettings({ villain: '反派设计：不适用' }),
    validOutline()
  ))
  assert.strictEqual(noReason.status, 1)
  assert(failureIds(noReason).includes('phase2.villain-contract'))

  const badReversal = run(writeCase(
    'bad-reversal-math',
    validSettings({ reversal: '反转位置：第 6 节 ÷ 共 8 节 = 60%' }),
    validOutline()
  ))
  assert.strictEqual(badReversal.status, 1)
  assert.deepStrictEqual(failureIds(badReversal), ['phase2.reversal-position'])

  const earlyReversalIsDescriptive = run(writeCase(
    'early-reversal-is-descriptive',
    validSettings({ reversal: '反转位置：第 3 节 ÷ 共 8 节 = 37.5%' }),
    validOutline()
  ))
  assert.strictEqual(earlyReversalIsDescriptive.status, 0, earlyReversalIsDescriptive.stdout)
  assert.strictEqual(earlyReversalIsDescriptive.report.ok, true)

  const noReversal = run(writeCase(
    'no-reversal',
    validSettings({
      reversalType: '无反转',
      reversal: '反转位置：不适用（采用报应兑现，不硬塞认知翻转）',
    }),
    validOutline()
  ))
  assert.strictEqual(noReversal.status, 0, noReversal.stdout)
  assert.strictEqual(noReversal.report.ok, true)

  const brokenOutline = validOutline().replace(
    /\| 结尾 \| 主角处理事件8[^\n]+\| 1000 \|/,
    (line) => line.replace(/\| 1000 \|$/, '|')
  )
  const badColumns = run(writeCase('bad-columns', validSettings(), brokenOutline))
  assert.strictEqual(badColumns.status, 1)
  assert(failureIds(badColumns).includes('phase2.outline-data-rows'))

  const badTargetSum = run(writeCase(
    'bad-target-sum',
    validSettings(),
    validOutline().replace('| 1000 |', '| 500 |')
  ))
  assert.strictEqual(badTargetSum.status, 1)
  assert.deepStrictEqual(failureIds(badTargetSum), ['phase2.target-word-sum'])

  // 특정 문제만 고치는 반복: 유료 전환 훅만 실패할 때 그 훅만 바꾸면 이미 유효한
  // 필드를 건드리지 않고 같은 산출물이 통과해야 한다.
  const repairDir = writeCase('targeted-repair', validSettings(), validOutline({ includePaywall: false }))
  const beforeRepair = run(repairDir)
  assert.strictEqual(beforeRepair.status, 1)
  assert.deepStrictEqual(failureIds(beforeRepair), ['phase2.paywall-in-both'])
  assert.strictEqual(beforeRepair.report.repair_scope.length, 1)
  assert.match(beforeRepair.report.repair_scope[0].repair, /只在缺失的文件/)
  const repairedOutline = fs.readFileSync(path.join(repairDir, '구간개요.md'), 'utf8')
    .replace('门后传来自己的声音 |', '门后传来自己的声音（付费点） |')
  fs.writeFileSync(path.join(repairDir, '구간개요.md'), repairedOutline, 'utf8')
  const afterRepair = run(repairDir)
  assert.strictEqual(afterRepair.status, 0, afterRepair.stdout + afterRepair.stderr)
  assert.strictEqual(afterRepair.report.ok, true)

  const mismatchedPaywall = run(writeCase(
    'mismatched-paywall',
    validSettings({ paywall: '付费点：第 3 节末' }),
    validOutline()
  ))
  assert.strictEqual(mismatchedPaywall.status, 1)
  assert.deepStrictEqual(failureIds(mismatchedPaywall), ['phase2.paywall-in-both'])
  assert.match(mismatchedPaywall.report.failures[0].evidence, /声明第 3 节末；大纲标在第 4 节/)

  for (const platform of ['문피아', '네이버 웹소설', '노벨피아', '네이버 시리즈', '카카오페이지', '리디', '포스타입', '기타', '未定']) {
    const settings = validSettings({ platform, paywall: '付费点：없음 (무료 발행)' })
    const free = run(writeCase(`korean-free-${platform}`, settings, validOutline({ includePaywall: false })))
    assert.strictEqual(free.status, 0, free.stdout)
    const conflict = run(writeCase(`korean-conflict-${platform}`, settings, validOutline()))
    assert(failureIds(conflict).includes('phase2.paywall-in-both'))
    const paid = run(writeCase(`korean-paid-${platform}`, validSettings({ platform }), validOutline()))
    assert.strictEqual(paid.status, 0, paid.stdout)
  }

  const invalidInvocation = spawnSync(process.execPath, [verifier, '--unknown'], {
    cwd: repoRoot,
    encoding: 'utf8',
  })
  assert.strictEqual(invalidInvocation.status, 2)
  assert.match(invalidInvocation.stderr, /用法/)

  process.stdout.write('phase2-contract: all tests passed\n')
} finally {
  fs.rmSync(tmpRoot, { recursive: true, force: true })
}
