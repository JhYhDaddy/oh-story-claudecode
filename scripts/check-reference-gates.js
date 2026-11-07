#!/usr/bin/env node
/**
 * check-reference-gates.js — 두 Reference Gate의 정적 검사기.
 *
 * 게이트는 모델이 실행하는 프롬프트 텍스트이므로 호출할 런타임 진입점이나 검증할 반환값이 없다.
 * 따라서 이 검사기는 게이트가 첫 화면에 남아 있고 연결하는 모든 참조를 계속 명시하는지,
 * 즉 소스 정책만 고정한다. 게이트 준수 여부는 실제 집필 실행으로 측정하며 여기서는 측정하지 않는다.
 * 검사 통과를 모델이 게이트를 지켰다는 증거로 해석하면 안 된다.
 */

'use strict'

const assert = require('assert')
const fs = require('fs')
const path = require('path')

const repoRoot = path.resolve(__dirname, '..')

function readSkill(name) {
  return fs.readFileSync(path.join(repoRoot, `skills/${name}/SKILL.md`), 'utf8')
}

const long = readSkill('story-long-write')
const longLines = long.split(/\r?\n/)
const longGateLine = longLines.findIndex((line) => line.includes('## 집필 전 필독')) + 1
assert(longGateLine > 0 && longGateLine <= 20, `long 写前必读 gate must stay in first screen, got line ${longGateLine}`)
for (const reference of [
  'workflow-setup.md', 'workflow-volume.md', 'workflow-outline.md', 'workflow-chapter.md', 'workflow-daily.md', 'workflow-revision.md', 'long-format.md',
  'writing-craft.md', 'long-chapter-quality.md', 'long-chapter-hooks.md', 'long-suspense.md',
  'long-reversal.md',
]) {
  assert(long.includes(reference), `long gate must route ${reference}`)
}
// 집필 전에 이번 요청의 명시적 제약(글자 수, 필수 사건, 금지 사건, 중단 지점)을 그대로 기록하는 동작 앵커.
assert.match(long, /이번 제약을 기록합니다/)

const short = readSkill('story-short-write')
const shortLines = short.split(/\r?\n/)
const shortGateLine = shortLines.findIndex((line) => line.includes('## 집필 전 필독')) + 1
assert(shortGateLine > 0 && shortGateLine <= 20, `short 写前必读 gate must stay in first screen, got line ${shortGateLine}`)

// 단계 참조 자료의 Phase 2 경로와 완료 게이트를 검사한다.
const shortGate = shortLines.slice(shortGateLine - 1, shortGateLine + 11).join('\n')
assert(shortGate.includes('`references/workflow-design.md`'), 'Phase 2 gate must route workflow-design on the first screen')
const shortDesign = fs.readFileSync(path.join(repoRoot, 'skills/story-short-write/references/workflow-design.md'), 'utf8')
assert.match(shortDesign, /check-phase2-contract\.js --json/)

// Phase 3은 독립적으로 실행 가능해야 한다. #418에서는 workflow-draft가 workflow-revision에만 있는 ‘Phase 4
// 명령’을 참조하게 되어 실제 실행에서 사전 검사 없이 본문부터 작성했다.
// 경로, 명령 리터럴, 명령 위치를 고정한다.
function phaseSection(heading) {
  const start = short.indexOf(heading)
  assert(start >= 0, `short SKILL.md must keep ${heading}`)
  const next = short.indexOf('\n### Phase ', start + heading.length)
  return short.slice(start, next < 0 ? undefined : next)
}
assert.match(shortGate, /Phase 3 집필 전 `references\/workflow-draft\.md`/)
assert.match(shortGate, /Phase 4 퇴고 전 `references\/workflow-revision\.md`/)
assert(phaseSection('### Phase 3:').includes('(references/workflow-draft.md)'), 'Phase 3 must route workflow-draft.md')
assert(phaseSection('### Phase 4:').includes('(references/workflow-revision.md)'), 'Phase 4 must route workflow-revision.md')

const shortDraft = fs.readFileSync(path.join(repoRoot, 'skills/story-short-write/references/workflow-draft.md'), 'utf8')
const precheck = shortDraft.match(/`node \{skill 根\}\/scripts\/check-delivery-contract\.js ([^`]*)`/)
assert(precheck, 'workflow-draft must spell out the check-delivery-contract precheck command')
for (const flag of ['--check-contract', '--min-chars {MIN}', '--max-chars {MAX}', '--sections {N}', '--min-section-chars']) {
  assert(precheck[1].includes(flag), `workflow-draft precheck must pass ${flag}`)
}
const draftingStep = shortDraft.indexOf('**집필 전 준비**')
assert(draftingStep > 0 && precheck.index < draftingStep, 'workflow-draft precheck must come before the drafting step')
assert.doesNotMatch(shortDraft, /Phase 4 的交付命令/, 'workflow-draft must not defer the precheck command to Phase 4')
// #445 실제 세션에서 배치 사이에 Python 집계 코드를 약 40번 직접 작성했다. 배치 사이에 ‘--check-contract를 빼고 같은 명령 재실행’ 앵커가 필요하다.
assert.match(shortDraft, /`--check-contract`를 빼고 다시 실행/, 'workflow-draft must tell the writer to re-run the same command between batches')

const shortRevision = fs.readFileSync(path.join(repoRoot, 'skills/story-short-write/references/workflow-revision.md'), 'utf8')
const finalCheck = shortRevision.match(/`node scripts\/check-delivery-contract\.js ([^`]*)`/)
assert(finalCheck && !finalCheck[1].includes('--check-contract'), 'workflow-revision must keep the final delivery check')

// v0.8.2 단편은 작가의 작업 시점별로 로드한다. 본문 작성은 저장된 설계 파일로만 구상과 연결하고 구상 시점의 방법론은 다시 참조하지 않는다.
// (이전에는 본문 작성 중 악역/훅/공식/도입/벤치마크 회수를 다시 찾아 대화가 바뀌면 자료 전체를 다시 읽어야 했다.)
assert.match(short, /\*\*인계는 저장 파일로만\*\*/, 'short SKILL.md must state the design-to-draft handoff')
for (const reference of [
  'workflow-design.md', 'short-reversal.md', 'submission-craft.md', 'villain-and-reveal.md',
  'genre-writing-formulas.md', 'hooks-chapter.md', 'benchmark-recall.md', 'cross-book-recall.md',
]) {
  assert(!shortDraft.includes(reference), `workflow-draft must take ${reference} decisions from 설정.md, not re-read it`)
}
// 본문 작성 시에는 형식 규약과 장르 묶음도 읽는다. 이 자료들도 집필자를 구상 시점의 플랫폼·설계·공개 자료로 돌려보내면 안 된다.
const shortRefs = path.join(repoRoot, 'skills/story-short-write/references')
for (const file of ['short-format.md', ...fs.readdirSync(path.join(shortRefs, 'genre-styles')).map((name) => `genre-styles/${name}`)]) {
  const text = fs.readFileSync(path.join(shortRefs, file), 'utf8')
  for (const reference of ['submission-craft.md', 'workflow-design.md', 'villain-and-reveal.md']) {
    assert(!text.includes(reference), `${file} is loaded while drafting and must not point to ${reference}; use 설정.md instead`)
  }
}
for (const field of ['平台基调', '作者已定']) {
  assert(shortDesign.includes(field), `workflow-design must land ${field} in 설정.md for the draft moment`)
}
// ‘像’은 진입점 완료 기준에서 개별 위치를 재검토하는 단일 기준만 사용하며 전문에 대한 강제 상한은 두지 않는다.
assert.doesNotMatch(shortRevision, /全文不超 10 处/, 'workflow-revision must not reintroduce a hard 像 cap')

process.stdout.write('reference-gates: source policy holds\n')
