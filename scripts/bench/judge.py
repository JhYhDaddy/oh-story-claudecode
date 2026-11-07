#!/usr/bin/env python3
"""벤치마크 본문의 품질 평가: 개별 상세 개요의 실현 여부 대조와 쌍별 블라인드 평가. 기본 평가자는 Antigravity(Gemini)다.
집필자가 Gemini이면 --judge claude 또는 codex로 계열을 바꾼다. 평가자와 집필자는 서로 다른 계열이어야 한다.

사용법:
  judge.py [--judge agy|claude|codex] coverage <run디렉터리>... --out <결과디렉터리>
  judge.py [--judge agy|claude|codex] pairwise --base <run디렉터리>... --cand <run디렉터리>... --out <결과디렉터리>

coverage: 장별 평가. 평가자는 버전을 모른 채 해당 장의 개요와 본문만 보고 플롯 포인트별 실현 여부를 판정한다.
          상세 개요가 허용하지 않은 새로운 플롯 사실도 열거한다. 개수로 검증하며 점수에 의존하지 않는다.
          --strict: ‘장면으로 구현 / 요약 서술 / 누락’으로 구분하고 원문을 인용한다. 기본 기준은 Gemini Flash에 너무 관대해
          양쪽 버전 모두 1.00이 나와 핵심 대립이 요약으로 처리된 문제를 드러내지 못한다.
pairwise: 같은 (호스트, 사례, 장 번호)의 두 버전을 무작위 A/B로 배정하고 순서를 바꿔 한 번씩 평가한다.
          두 결과가 같아야 승패를 인정하고 다르면 무승부다. 평가자는 버전을 모른다. 사례 실행 중 개요를 보충해 두 버전이 다르면
          각각의 개요를 첨부하며 한쪽 개요로 다른 쪽을 평가하지 않는다.
모든 원본 응답은 재검토할 수 있도록 --out에 저장한다. 재실행하면 기존 결과는 건너뛴다.
"""
import argparse
import hashlib
import json
import random
import re
import subprocess
import sys
from pathlib import Path

JUDGE_MODELS = {'agy': 'gemini-3.8-flash-high', 'claude': 'claude-opus-5-5', 'codex': 'gpt-5.6-sol'}
JUDGE = 'agy'

COVERAGE_PROMPT = """你是网文责编，只核对事实，不评文笔。下面是一章的细纲和成稿正文。

任务一：把细纲里的情节点逐条列出（优先用细纲「情节点」表的编号；没有表就按「情节安排」逐条拆），
对每条判定正文是否演出来了：landed（演成了场景）、summarized（只用一两句交代带过）、missing（没有）。
任务二：列出正文里细纲没有授权、且会影响后续章节的新剧情事实（新主线事件、新反转、新能力规则、
改变细纲已定结果、提前写后续章剧情）。现场细节、路人、一次性对话不算。

只输出一个 JSON 对象，不要任何别的文字：
{{"beats": [{{"id": "1", "beat": "情节点一句话", "status": "landed|summarized|missing"}}],
  "unauthorized": [{{"fact": "一句话", "quote": "正文原句片段"}}]}}

===== 细纲 =====
{outline}

===== 正文 =====
{body}
"""

SCENE_PROMPT = """你是网文责编，只核对「演没演」，不评文笔。下面是一章的细纲和成稿正文。

把细纲里的情节点逐条列出（优先用「情节点」表的编号），对每条在正文里找到对应段落，判定呈现方式：
- scene：演成了场景——读者看到逐拍的动作、对话或物件变化，关键交锋用人物的原话呈现；
- summary：叙述者概括转述——例如「他讲了十分钟证据」「两人争了几句」「她把来龙去脉说了一遍」，
  或只给结果不给过程；
- missing：正文里没有。
每条都要摘一句最能说明判定的正文原句（≤40 字）。宁严勿宽：半场景半概括的，关键交锋被概括就判 summary。

只输出一个 JSON 对象，不要任何别的文字：
{{"beats": [{{"id": "1", "beat": "情节点一句话", "render": "scene|summary|missing", "quote": "正文原句"}}]}}

===== 细纲 =====
{outline}

===== 正文 =====
{body}
"""

PAIRWISE_PROMPT = """你是番茄小说的资深编辑。下面是{source}写出的两版第 {chapter} 章正文（A 与 B），
来源未知。请站在追更读者的角度判断哪一版更好看：更想往下读、人物更像活人、场面更具体、
更不像 AI 写的。只看成品，不因长短本身加减分。

只输出一个 JSON 对象，不要任何别的文字：
{{"winner": "A|B|tie", "reason": "两三句具体理由，引用原文片段"}}

{outline}

===== A =====
{a}

===== B =====
{b}
"""


def ask(prompt, cwd):
    model = JUDGE_MODELS[JUDGE]
    if JUDGE == 'claude':
        # 사용자·프로젝트 설정과 CLAUDE.md를 읽지 않는다. 평가자는 프롬프트만 본다.
        cmd, stdin = ['claude', '-p', '--model', model, '--output-format', 'text', '--setting-sources', '',
                      '--disallowedTools', 'Bash,Edit,Write,Read,Glob,Grep,WebFetch,WebSearch,Agent'], prompt
    elif JUDGE == 'codex':
        cmd, stdin = ['codex', 'exec', '-c', f'model="{model}"', '--skip-git-repo-check', '--sandbox', 'read-only',
                      '-'], prompt
    else:
        cmd, stdin = ['agy', '-p', prompt, '--model', model, '--output-format', 'text', '--print-timeout', '10m',
                      '--disable-slash-commands', '--sandbox', '--dangerously-skip-permissions'], None
    completed = subprocess.run(cmd, cwd=cwd, input=stdin, capture_output=True, text=True, encoding='utf-8',
                               **({} if stdin is not None else {'stdin': subprocess.DEVNULL}))
    text = completed.stdout
    match = re.search(r'\{.*\}', text, re.S)
    try:
        return json.loads(match.group(0)) if match else None, text
    except ValueError:
        return None, text


def chapters(run):
    run = Path(run)
    meta = json.loads((run / 'meta.json').read_text(encoding='utf-8'))
    book = run / 'proj' / meta['case']['book_dir']
    for n in range(meta['start_committed'] + 1, meta.get('end_committed', 0) + 1):
        body = sorted((book / '본문').glob(f'제{n:03d}장*.md'))
        outline = sorted((book / '개요').glob(f'상세개요_제{n:03d}장*.md'))
        if body and outline:
            yield meta, n, body[0], outline[0]


def coverage(runs, out, strict=False):
    out.mkdir(parents=True, exist_ok=True)
    for run in runs:
        for meta, n, body, outline in chapters(run):
            dest = out / f'{Path(run).name}-{n:03d}-{JUDGE}.json'
            if dest.exists():
                continue
            prompt = (SCENE_PROMPT if strict else COVERAGE_PROMPT).format(
                outline=outline.read_text(encoding='utf-8'), body=body.read_text(encoding='utf-8'))
            result, raw = ask(prompt, out)
            dest.write_text(json.dumps({'run': Path(run).name, 'host': meta['host'], 'case': meta['case']['id'],
                                        'pkg': meta['pkg'].get('ref'), 'chapter': n, 'judge': JUDGE_MODELS[JUDGE],
                                        'result': result, 'raw': raw},
                                       ensure_ascii=False, indent=1), encoding='utf-8')
            print(dest.name, 'ok' if result else 'PARSE_FAIL', flush=True)


def pairwise(base_runs, cand_runs, out):
    out.mkdir(parents=True, exist_ok=True)
    index = {}
    for label, runs in (('base', base_runs), ('cand', cand_runs)):
        for run in runs:
            for meta, n, body, outline in chapters(run):
                index.setdefault((meta['host'], meta['case']['id'], n), {})[label] = (body, outline)
    for (host, case, n), pair in sorted(index.items()):
        if len(pair) != 2:
            continue
        dest = out / f'{host}-{case}-{n:03d}-{JUDGE}.json'
        if dest.exists():
            continue
        seed = int(hashlib.sha256(f'{host}{case}{n}'.encode()).hexdigest(), 16)
        first = random.Random(seed).choice(['base', 'cand'])
        second = 'cand' if first == 'base' else 'base'
        outlines = {k: v[1].read_text(encoding='utf-8') for k, v in pair.items()}
        texts = {k: v[0].read_text(encoding='utf-8') for k, v in pair.items()}
        rounds = []
        for a, b in ((first, second), (second, first)):
            if outlines['base'] == outlines['cand']:
                source, outline = '同一份细纲', '===== 细纲 =====\n' + outlines['base']
            else:
                source = '各自细纲（同一段剧情、分别补写）'
                outline = '===== A 的细纲 =====\n%s\n\n===== B 的细纲 =====\n%s' % (outlines[a], outlines[b])
            result, raw = ask(PAIRWISE_PROMPT.format(source=source, chapter=n, outline=outline, a=texts[a], b=texts[b]),
                              out)
            w = (result or {}).get('winner')
            rounds.append({'A': a, 'B': b, 'winner': {'A': a, 'B': b}.get(w, 'tie' if w == 'tie' else None),
                           'reason': (result or {}).get('reason'), 'raw': raw})
        votes = [r['winner'] for r in rounds]
        final = votes[0] if votes[0] == votes[1] and votes[0] in ('base', 'cand') else 'tie'
        dest.write_text(json.dumps({'host': host, 'case': case, 'chapter': n, 'judge': JUDGE_MODELS[JUDGE],
                                    'final': final, 'rounds': rounds},
                                   ensure_ascii=False, indent=1), encoding='utf-8')
        print(dest.name, final, flush=True)


def main():
    global JUDGE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--judge', choices=sorted(JUDGE_MODELS), default='agy',
                    help='评委主机；必须与被评正文的写手不同家族')
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('coverage')
    c.add_argument('runs', nargs='+')
    c.add_argument('--out', required=True)
    c.add_argument('--strict', action='store_true', help='逐条判「演成场景 / 概括转述」并摘原句')
    p = sub.add_parser('pairwise')
    p.add_argument('--base', nargs='+', required=True)
    p.add_argument('--cand', nargs='+', required=True)
    p.add_argument('--out', required=True)
    a = ap.parse_args()
    JUDGE = a.judge
    if a.cmd == 'coverage':
        coverage(a.runs, Path(a.out), strict=a.strict)
    else:
        pairwise(a.base, a.cand, Path(a.out))


if __name__ == '__main__':
    sys.exit(main())
