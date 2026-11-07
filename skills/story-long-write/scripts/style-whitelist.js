'use strict';

const fs = require('fs');
const path = require('path');

// 현재 작품에만 적용한다. 무관한 작업 공간이나 다른 작품의 선택을 상속하지 않는다.
function loadStyleWhitelist(file) {
  const parent = path.dirname(path.resolve(file));
  const book = path.basename(parent) === '본문' ? path.dirname(parent) : parent;
  try {
    return fs.readFileSync(path.join(book, '.deslop-whitelist'), 'utf8')
      .split(/\r?\n/).map(line => line.trim())
      .filter(line => line && !line.startsWith('#'))
      .sort((a, b) => b.length - a.length);
  } catch (error) {
    if (error.code === 'ENOENT') return [];
    throw error;
  }
}

function styleSpans(text, whitelist) {
  const spans = [];
  for (const literal of whitelist) {
    for (let at = text.indexOf(literal); at !== -1; at = text.indexOf(literal, at + 1)) {
      spans.push([at, at + literal.length]);
    }
  }
  return spans;
}

function maskStyleText(text, whitelist) {
  const chars = text.split('');
  for (const [start, end] of styleSpans(text, whitelist)) {
    chars.fill('？', start, end);
  }
  return chars.join('');
}

module.exports = { loadStyleWhitelist, styleSpans, maskStyleText };
