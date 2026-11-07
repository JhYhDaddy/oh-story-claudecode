#!/usr/bin/env node
'use strict'

const assert = require('assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const { spawnSync } = require('child_process')

const repoRoot = path.resolve(__dirname, '..')
const verifier = path.join(repoRoot, 'skills/story-long-write/scripts/check-outline-contract.js')
const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'outline-contract-'))

const FIELDS = [
  ['核心事件', '江晨拿到伴奏后决定去老兵家里听故事'],
  ['字数目标', '2300 字'],
  ['字数口径', 'visible_chars_v1'],
  ['阶段位置', '收尾期 · 第2阶段第11章'],
  ['单元ID/位置', 'U03；单元内第 1 拍'],
  ['目标情绪', '踏实的期待 → 被托付的沉重'],
  ['主角目标/关键选择', '要真实素材；在报批与先去听故事之间选一个'],
  ['章节定位', '推进'],
  ['本章结构公式', '接到邀约 + 上门 + 老兵开口 + 立下承诺'],
  ['章首钩子', '悬念前置 — 老人把铁盒推过来'],
  ['爽点', '无显性爽点，功能是把宏大叙事落到具体的人身上'],
  ['本章标价', '铁盒＝老兵一辈子唯一没交出去的东西；尺子在点1立好（他连勋章都捐了）'],
  ['闭环状态', '获得+使用，见效与估值扣住，第22章开奖'],
  ['本章禁止提前释放', '铁盒内容与终局表彰的关系'],
  ['写手自由区', '老兵讲故事的细节、屋内陈设、对话内容由写手自定'],
  ['契约风险', '契约安全'],
]

function outline(overrides = {}) {
  const fields = FIELDS
    .filter(([name]) => overrides.dropField !== name)
    .map(([name, value]) => `- ${name}：${overrides.fieldValues?.[name] ?? value}`)
  const table = overrides.plotTable ?? [
    '| # | 情节点（谁做了什么） | 功能标签 | 分辨率 | 执行边界 |',
    '|---|---|---|---|---|',
    '| 1 | 江晨接到邀约 | 铺垫 | 疏 | 禁：不提铁盒。放：无 |',
    '| 2 | 老人推过铁盒 | 高潮 | 密 | 禁：不评价当下。放：允许老人当场说出这东西他留了几十年 |',
  ].join('\n')
  const acts = ['起因', '发展', '转折', '高潮', '结尾']
    .filter((act) => overrides.dropAct !== act)
    .map((act) => `- ${act}：本章${act}内容`)
  return [
    '## 细纲（第 21 章）',
    '',
    '### 第 21 章：新的伴奏',
    ...fields,
    '',
    '#### 内容概括（五段式）',
    ...acts,
    '',
    '#### 情节安排（多线）',
    '- 主线推进：新作品素材来源确定',
    '- 辅线推进：无',
    '- 逻辑线：拿到伴奏 → 缺素材 → 接受邀约 → 背上承诺',
    '',
    '#### 人物关系和出场顺序',
    '- 出场顺序：江晨、赵大柱',
    '- 人物关系变化：陌生受访者 → 托付关系',
    '',
    '#### 情节细化',
    '- 情节点序列（逐行填下表）：',
    '',
    table,
    '',
  ].join('\n')
}

function writeCase(name, body) {
  const dir = path.join(tmpRoot, name, '개요')
  fs.mkdirSync(dir, { recursive: true })
  if (body !== null) fs.writeFileSync(path.join(dir, '상세개요_제021장.md'), body, 'utf8')
  return path.join(tmpRoot, name)
}

function run(project, chapter = '21') {
  const result = spawnSync(process.execPath, [verifier, '--json', '--project', project, '--chapter', chapter], {
    cwd: repoRoot,
    encoding: 'utf8',
  })
  let report = null
  if (result.stdout.trim()) report = JSON.parse(result.stdout)
  return { ...result, report }
}

const failureIds = (result) => result.report.failures.map((failure) => failure.id)

try {
  // 템플릿 항목이 완전한 상세 개요는 반드시 통과해야 한다. 오탐 방어선이므로 먼저 테스트한다.
  const good = run(writeCase('valid', outline()))
  assert.strictEqual(good.status, 0, good.stdout + good.stderr)
  assert.strictEqual(good.report.ok, true)
  assert.deepStrictEqual(good.report.failures, [])

  // 굵은 필드명과 반각 콜론도 인식해야 올바른 표기를 오탐하지 않는다.
  const boldHalfWidth = outline().replace('- 目标情绪：', '- **目标情绪**: ')
  const bold = run(writeCase('bold-halfwidth', boldHalfWidth))
  assert.strictEqual(bold.status, 0, bold.stdout + bold.stderr)

  // 목표 감정 / 주인공 목표·핵심 선택은 실측상 본문에 직접 영향을 주므로 자리표시자를 허용하지 않는다…
  const hollowIntent = run(writeCase('hollow-intent', outline({
    fieldValues: { 目标情绪: '[待补充]' },
  })))
  assert.strictEqual(hollowIntent.status, 1)
  assert(failureIds(hollowIntent).includes('outline.intent-fields-substantive'))
  assert.match(hollowIntent.report.failures.find((f) => f.id === 'outline.intent-fields-substantive').evidence, /目标情绪/)

  const hollowGoal = run(writeCase('hollow-goal', outline({
    fieldValues: { '主角目标/关键选择': '[待补充]' },
  })))
  assert.strictEqual(hollowGoal.status, 1)
  assert(failureIds(hollowGoal).includes('outline.intent-fields-substantive'))

  // …하지만 나머지 필드는 계약상 [待补充]를 허용하므로 이를 이유로 실패시키면 안 된다.
  const hollowOther = run(writeCase('hollow-other', outline({
    fieldValues: { 契约风险: '[待补充]', 章节定位: '[待补充]', '单元ID/位置': '[待补充]' },
  })))
  assert.strictEqual(hollowOther.status, 0, hollowOther.stdout + hollowOther.stderr)
  assert.strictEqual(hollowOther.report.ok, true)

  const dropped = run(writeCase('missing-field', outline({ dropField: '目标情绪' })))
  assert.strictEqual(dropped.status, 1)
  assert.deepStrictEqual(failureIds(dropped), ['outline.required-fields'])
  assert.match(dropped.report.failures[0].evidence, /目标情绪/)
  assert.strictEqual(dropped.report.repair_scope.length, 1)
  assert.match(dropped.report.repair_scope[0].repair, /\[待补充\]/)

  const noAct = run(writeCase('missing-act', outline({ dropAct: '转折' })))
  assert.strictEqual(noAct.status, 1)
  assert.deepStrictEqual(failureIds(noAct), ['outline.five-act'])

  // 사건 지점을 번호 목록으로 쓴 경우(현재 가장 흔한 이탈 형태)는 반드시 검출해야 한다.
  const listStyle = run(writeCase('plot-as-list', outline({
    plotTable: '1. 江晨接到邀约【铺垫】\n2. 老人推过铁盒【高潮】',
  })))
  assert.strictEqual(listStyle.status, 1)
  assert.deepStrictEqual(failureIds(listStyle), ['outline.plotpoint-table'])

  // 실행 범위가 빠진 3열 표도 규약 이탈이다.
  const threeCol = run(writeCase('plot-three-col', outline({
    plotTable: '| # | 情节点 | 功能标签 |\n|---|---|---|\n| 1 | 江晨接到邀约 | 铺垫 |',
  })))
  assert.strictEqual(threeCol.status, 1)
  assert.deepStrictEqual(failureIds(threeCol), ['outline.plotpoint-table'])

  // ‘分辨率’ 열을 추가하기 전의 기존 4열 표도 계속 허용한다. 템플릿에 열을 추가했다고 기존 상세 개요가 무효화되면 안 된다.
  const legacyFourCol = run(writeCase('plot-legacy-four-col', outline({
    plotTable: [
      '| # | 情节点（谁做了什么） | 功能标签 | 执行边界 |',
      '|---|---|---|---|',
      '| 1 | 江晨接到邀约 | 铺垫 | 只给邀约，不提铁盒 |',
    ].join('\n'),
  })))
  assert.strictEqual(legacyFourCol.status, 0, legacyFourCol.stdout + legacyFourCol.stderr)
  assert.strictEqual(legacyFourCol.report.ok, true)

  // 독서 경험 필드는 선택 사항이다. 핵심 필드만 있는 상세 개요도 통과한다(#383 분리 실험은 목표 감정과 주인공 목표의 이점만 입증).
  const OPTIONAL = ['阶段位置', '章节定位', '本章结构公式', '本章标价', '闭环状态', '写手自由区', '契约风险']
  const coreOnly = outline({ plotTable: [
    '| # | 情节点（谁做了什么） | 功能标签 | 执行边界（禁＋放） |',
    '|---|---|---|---|',
    '| 1 | 江晨接到邀约 | 铺垫 | 禁：不提铁盒。放：无 |',
    '| 2 | 老人推过铁盒 | 高潮 | 禁：不评价当下。放：允许老人当场说出这东西他留了几十年 |',
  ].join('\n') }).split('\n').filter((line) => !OPTIONAL.some((name) => line.startsWith(`- ${name}：`))).join('\n')
  const core = run(writeCase('core-fields-only', coreOnly))
  assert.strictEqual(core.status, 0, core.stdout + core.stderr)

  // 머리글에 ‘禁＋放’을 명시한 4열 표도 최소 한 지점에는 ‘放’이 있어야 한다. 전부 금지 사항이면 실패한다.
  const allBan = run(writeCase('four-col-all-ban', outline({ plotTable: [
    '| # | 情节点（谁做了什么） | 功能标签 | 执行边界（禁＋放） |',
    '|---|---|---|---|',
    '| 1 | 江晨接到邀约 | 铺垫 | 禁：不提铁盒。放：无 |',
  ].join('\n') })))
  assert.strictEqual(allBan.status, 1)
  assert.deepStrictEqual(failureIds(allBan), ['outline.plotpoint-release'])

  // 5열이지만 가운데 열이 分辨率가 아니면 이탈로 판정한다. 아무 열이나 추가해 통과하는 것을 막는다.
  const wrongFifth = run(writeCase('plot-wrong-fifth', outline({
    plotTable: [
      '| # | 情节点（谁做了什么） | 功能标签 | 字数 | 执行边界 |',
      '|---|---|---|---|---|',
      '| 1 | 江晨接到邀约 | 铺垫 | 300 | 只给邀约 |',
    ].join('\n'),
  })))
  assert.strictEqual(wrongFifth.status, 1)
  assert.deepStrictEqual(failureIds(wrongFifth), ['outline.plotpoint-table'])

  const badTarget = run(writeCase('bad-target', outline({ fieldValues: { 字数目标: '很多字' } })))
  assert.strictEqual(badTarget.status, 1)
  assert(failureIds(badTarget).includes('outline.wordcount-target'))

  // 글자 수 목표는 storyctl과 같은 문법이다. 흔한 작가 표기를 허용하고 값을 JSON에 넣는다. 범위를 쓴 경우 더 이상 조용히 하한으로 읽지 않는다.
  assert.deepStrictEqual(good.report.wordcount, { target: 2300, target_status: 'ok', range: null, range_status: 'missing' })
  const approxTarget = run(writeCase('target-approx', outline({ fieldValues: { 字数目标: '约 2,300 字（本章偏短）' } })))
  assert.strictEqual(approxTarget.status, 0, approxTarget.stdout)
  assert.strictEqual(approxTarget.report.wordcount.target, 2300)
  const rangeAsTarget = run(writeCase('target-as-range', outline({ fieldValues: { 字数目标: '2000-2600' } })))
  assert.strictEqual(rangeAsTarget.status, 1)
  assert.deepStrictEqual(failureIds(rangeAsTarget), ['outline.wordcount-target'])
  const authorRange = run(writeCase('author-range', outline() + '\n- 字数范围：2000-2600 字\n'))
  assert.strictEqual(authorRange.status, 0, authorRange.stdout)
  assert.deepStrictEqual(authorRange.report.wordcount.range, { min: 2000, max: 2600 })
  const badRange = run(writeCase('author-range-reversed', outline() + '\n- 字数范围：2600-2000\n'))
  assert.strictEqual(badRange.status, 1)
  assert.deepStrictEqual(failureIds(badRange), ['outline.wordcount-target'])

  // 계약 위험은 선택 사항이다. 기입했다면 세 등급만 허용하고 등급을 JSON에 넣어 검토와 작가 보고에서 사용하게 한다.
  assert.deepStrictEqual(good.report.contract_risk, { level: '契约安全', detail: '', status: 'ok' })
  const reinforce = run(writeCase('risk-reinforce', outline({ fieldValues: { 契约风险: '需补强——补一段交换，让主角付出代价' } })))
  assert.strictEqual(reinforce.status, 0, reinforce.stdout)
  assert.deepStrictEqual(reinforce.report.contract_risk, { level: '需补强', detail: '补一段交换，让主角付出代价', status: 'ok' })
  const badRisk = run(writeCase('risk-invalid', outline({ fieldValues: { 契约风险: '低风险' } })))
  assert.strictEqual(badRisk.status, 1)
  assert.deepStrictEqual(failureIds(badRisk), ['outline.contract-risk'])
  assert.strictEqual(badRisk.report.contract_risk.status, 'invalid')
  // 이전 이름 ‘风险等级’도 같은 필드로 인식한다.
  const legacyRisk = run(writeCase('risk-legacy-name', outline().replace('- 契约风险：契约安全', '- 风险等级：契约破坏')))
  assert.strictEqual(legacyRisk.status, 0, legacyRisk.stdout)
  assert.strictEqual(legacyRisk.report.contract_risk.level, '契约破坏')
  const legacyBad = run(writeCase('risk-legacy-invalid', outline().replace('- 契约风险：契约安全', '- 风险等级：高')))
  assert.deepStrictEqual(failureIds(legacyBad), ['outline.contract-risk'])

  const noCaliber = run(writeCase('no-caliber', outline({ fieldValues: { 字数口径: 'chars' } })))
  assert.strictEqual(noCaliber.status, 1)
  assert.deepStrictEqual(failureIds(noCaliber), ['outline.wordcount-target'])

  // 5열 표 전체가 금지 사항이며 ‘放’이 하나도 없으면 반드시 검출한다. 015장 실제 사고 유형이다.
  const allForbid = run(writeCase('plot-all-forbid', outline({
    plotTable: [
      '| # | 情节点（谁做了什么） | 功能标签 | 分辨率 | 执行边界 |',
      '|---|---|---|---|---|',
      '| 1 | 江晨接到邀约 | 铺垫 | 疏 | 禁：不提铁盒 |',
      '| 2 | 老人推过铁盒 | 高潮 | 密 | 禁：不评价当下 |',
    ].join('\n'),
  })))
  assert.strictEqual(allForbid.status, 1)
  assert(failureIds(allForbid).includes('outline.plotpoint-release'))

  // ‘放’이 있으나 3분의 1 미만이면 blocking은 통과하고 advisory로 알린다.
  const lowRelease = run(writeCase('plot-low-release', outline({
    plotTable: [
      '| # | 情节点（谁做了什么） | 功能标签 | 分辨率 | 执行边界 |',
      '|---|---|---|---|---|',
      '| 1 | 江晨接到邀约 | 铺垫 | 疏 | 禁：不提铁盒。放：允许邻居搭话 |',
      '| 2 | 老人推过铁盒 | 高潮 | 密 | 禁：不评价当下 |',
      '| 3 | 江晨接过铁盒 | 高潮 | 中 | 禁：不开盒 |',
      '| 4 | 告辞出门 | 余波 | 疏 | 禁：不回头 |',
    ].join('\n'),
  })))
  assert.strictEqual(lowRelease.status, 0, lowRelease.stdout + lowRelease.stderr)
  assert(lowRelease.report.advisories.map((a) => a.id).includes('outline.plotpoint-release-ratio'))

  // 조기 공개 금지 항목이 5개를 넘으면 권 단위 상시 규칙 반복을 의심하되 advisory로만 알리고 차단하지 않는다.
  const boilerplate = run(writeCase('release-boilerplate', outline({
    fieldValues: { 本章禁止提前释放: '铁盒内容、终局表彰、幕后资助人、母亲身世、纪念馆改建、旧部队番号' },
  })))
  assert.strictEqual(boilerplate.status, 0, boilerplate.stdout + boilerplate.stderr)
  assert(boilerplate.report.advisories.map((a) => a.id).includes('outline.release-brevity'))

  // 상세 개요가 존재하지 않는 설정 파일을 참조하면 반드시 검출한다. ‘숫자는 X.md 기준’이라고 했지만 X가 없는 개요 구성 사고를 방지한다.
  const ghostRefBody = outline() + '\n#### 结尾设定和钩子\n- 结尾设定：数字口径照 `설정/세계관/经济与用度.md`，收束于关门\n'
  const ghostRef = run(writeCase('ghost-ref', ghostRefBody))
  assert.strictEqual(ghostRef.status, 1)
  assert(failureIds(ghostRef).includes('outline.setting-refs-exist'))

  // 같은 참조의 실제 파일이 존재하면 반드시 통과해야 한다(경로 없는 파일명 참조 포함).
  const realRefProject = writeCase('real-ref', outline() + '\n#### 结尾设定和钩子\n- 结尾设定：数字口径照 `설정/세계관/经济与用度.md`、行市见 `经济与用度.md`\n')
  fs.mkdirSync(path.join(realRefProject, '설정', '세계관'), { recursive: true })
  fs.writeFileSync(path.join(realRefProject, '설정', '세계관', '经济与用度.md'), '# 经济与用度\n', 'utf8')
  const realRef = run(realRefProject)
  assert.strictEqual(realRef.status, 0, realRef.stdout + realRef.stderr)

  // --supply: 단위 카드에 ‘供给自查’ 절이 있으면 통과하고 없으면 실패한다.
  const volumeDir = path.join(tmpRoot, 'supply-case', '개요')
  fs.mkdirSync(volumeDir, { recursive: true })
  const volumeFile = path.join(volumeDir, '권개요_제1권.md')
  fs.writeFileSync(volumeFile, [
    '# 第一卷 卷纲',
    '### 剧情单元 D1-02',
    '- 单元ID：D1-02',
    '- 章节范围：第 11-20 章',
    '#### 供给自查',
    '- 对手供给：贾雄手下（B 级，落 설정/인물/贾雄.md）',
    '### 剧情单元 D1-03',
    '- 单元ID：D1-03',
    '- 章节范围：第 21-34 章',
    '## 核心矛盾',
  ].join('\n'), 'utf8')
  const supplyOk = spawnSync(process.execPath, [verifier, '--json', '--supply', volumeFile, 'D1-02'], { cwd: repoRoot, encoding: 'utf8' })
  assert.strictEqual(supplyOk.status, 0, supplyOk.stdout + supplyOk.stderr)
  const supplyMissing = spawnSync(process.execPath, [verifier, '--json', '--supply', volumeFile, 'D1-03'], { cwd: repoRoot, encoding: 'utf8' })
  assert.strictEqual(supplyMissing.status, 1)
  assert.match(JSON.parse(supplyMissing.stdout).evidence, /供给自查/)
  // 새 작품: 제공 자료 자체 점검은 권별 개요 옆의 개요초안_{单元ID}.md에 작성하며 단위 카드보다 우선한다.
  fs.writeFileSync(path.join(volumeDir, '개요초안_D1-03.md'), '# D1-03 排纲底稿\n\n## 供给自查\n无缺口\n', 'utf8')
  const supplyDraft = spawnSync(process.execPath, [verifier, '--json', '--supply', volumeFile, 'D1-03'], { cwd: repoRoot, encoding: 'utf8' })
  assert.strictEqual(supplyDraft.status, 0, supplyDraft.stdout + supplyDraft.stderr)
  assert.match(JSON.parse(supplyDraft.stdout).evidence, /排纲底稿含「供给自查」/)
  fs.writeFileSync(path.join(volumeDir, '개요초안_D1-03.md'), '# D1-03 排纲底稿\n\n## 建纲追加\n无追加\n', 'utf8')
  assert.strictEqual(spawnSync(process.execPath, [verifier, '--json', '--supply', volumeFile, 'D1-03'], { cwd: repoRoot, encoding: 'utf8' }).status, 1)

  for (const empty of ['无', '无。', '[待补充]', '；禁：不说破', '']) {
    const body = outline().replace('允许老人当场说出这东西他留了几十年', empty)
    const result = run(writeCase(`empty-release-${Buffer.from(empty).toString('hex')}`, body))
    assert(failureIds(result).includes('outline.plotpoint-release'), result.stdout)
  }
  const skillRef = run(writeCase('skill-ref', outline() + '\n见 `writing-craft.md` 与 `references/anti-ai-writing.md`'))
  assert.strictEqual(skillRef.status, 0, skillRef.stdout)
  for (const ref of ['../설정/工钱.md', '설정\\工钱.md', './工钱.md']) {
    const project = writeCase(`relative-${Buffer.from(ref).toString('hex')}`, outline() + `\n见 \`${ref}\``)
    assert(failureIds(run(project)).includes('outline.setting-refs-exist'))
    const target = path.resolve(project, '개요', ref.replace(/\\/g, '/').startsWith('설정/') ? '../' + ref.replace(/\\/g, '/') : ref)
    fs.mkdirSync(path.dirname(target), { recursive: true })
    fs.mkdirSync(target)
    assert(failureIds(run(project)).includes('outline.setting-refs-exist'))
    fs.rmdirSync(target)
    fs.writeFileSync(target, '# 工钱\n一日十文')
    assert.strictEqual(run(project).status, 0)
  }
  const supplyCases = [
    ['### 剧情单元 L1-010\n#### 供给自查', false],
    ['### 剧情单元 L1-01\n尚未执行供给自查', false],
    ['### 剧情单元 L1-01\n### 剧情单元 L1-02\n#### 供给自查', false],
    ['### 剧情单元 L1-01\n```md\n#### 供给自查\n```', false],
    ['### 剧情单元 L1-01\n#### 供给自查', true],
    ['### 剧情单元 L1-01：码头\n#### 供给自查（本批）\n无缺口', true],
    ['### 码头\n- **单元ID**：L1-01\n#### 信息\n##### 供给自查\n无', true],
  ]
  for (const [body, ok] of supplyCases) {
    fs.writeFileSync(volumeFile, body)
    const result = spawnSync(process.execPath, [verifier, '--supply', volumeFile, 'L1-01'], { encoding: 'utf8' })
    assert.strictEqual(result.status, ok ? 0 : 1, result.stdout + body)
  }

  const missingFile = run(writeCase('missing-file', null))
  assert.strictEqual(missingFile.status, 2)
  assert.match(missingFile.stderr, /没有第 21 章细纲/)

  const invalid = spawnSync(process.execPath, [verifier, '--unknown'], { cwd: repoRoot, encoding: 'utf8' })
  assert.strictEqual(invalid.status, 2)
  assert.match(invalid.stderr, /用法/)

  process.stdout.write('outline-contract: all tests passed\n')
} finally {
  fs.rmSync(tmpRoot, { recursive: true, force: true })
}
