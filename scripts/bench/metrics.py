#!/usr/bin/env python3
"""한 번 이상의 벤치마크 실행에서 효율과 본문 지표를 계산해 JSON으로 출력한다(--table은 별도 비교 표도 출력).

사용법:
  metrics.py <run目录>... [--table] [--tell <tell仓库>]

효율(커밋한 장 수로 평균): 실제 경과 시간, 주 세션 회차, 도구 호출, 하위 에이전트 횟수, 누적 입력/출력 토큰,
주 세션의 단일 문맥 최대 크기, 자동 압축 횟수, 각 장의 커밋 시각.
본문: 장별 가시 글자 수와 목표, 첫 chapter check의 분량 판정, 현재 분량 수락 여부,
check-ai-patterns의 blocking/advisory 개수. --tell을 주면 사람 기준 구간을 벗어난 항목 수도 추가한다.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

CHECK_RE = re.compile(r'storyctl\.py\S*\s+chapter\s+check\b.*?--chapter\s+(\d+)', re.S)
COMMIT_RE = re.compile(r'storyctl\.py\S*\s+chapter\s+(commit|accept-current-length)\b.*?--chapter\s+(\d+)', re.S)


def jl(path):
    for line in open(path, encoding='utf-8', errors='replace'):
        try:
            yield json.loads(line)
        except ValueError:
            continue


def ts(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()


def usage_add(tot, u):
    for k in ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens', 'output_tokens'):
        tot[k] = tot.get(k, 0) + int(u.get(k) or 0)


def check_status(text):
    """chapter check는 한 줄 JSON을 출력한다. story-chapter-check 행을 찾아 length.status를 얻는다."""
    for line in (text or '').splitlines():
        line = line.strip()
        if 'story-chapter-check' in line and line.startswith('{'):
            try:
                return json.loads(line)['length']['status']
            except (ValueError, KeyError, TypeError):
                pass
    return None


def tool_text(block):
    c = block.get('content')
    if isinstance(c, list):
        return ''.join(x.get('text', '') for x in c if isinstance(x, dict))
    return c or ''


def claude_efficiency(run, meta):
    projects = run / 'home/.claude/projects'
    sessions = {t['session'] for t in meta['turns'] if t.get('session')}
    main_files = [f for f in projects.glob('*/*.jsonl') if f.stem in sessions]
    sub_files = [f for s in sessions for f in projects.glob(f'*/{s}/subagents/*.jsonl')]
    eff = {'main': {}, 'sub': {}, 'tools': Counter(), 'spawns': 0, 'compactions': 0,
           'main_calls': 0, 'max_context': 0, 'checks': [], 'commits': []}
    seen = set()
    pending = {}
    for f in main_files:
        for d in jl(f):
            if d.get('type') == 'system' and d.get('subtype') == 'compact_boundary':
                eff['compactions'] += 1
            msg = d.get('message') or {}
            if d.get('type') == 'assistant' and msg.get('id') and msg['id'] not in seen:
                seen.add(msg['id'])
                u = msg.get('usage') or {}
                usage_add(eff['main'], u)
                eff['main_calls'] += 1
                ctx = sum(int(u.get(k) or 0) for k in ('input_tokens', 'cache_read_input_tokens',
                                                        'cache_creation_input_tokens'))
                eff['max_context'] = max(eff['max_context'], ctx)
            if d.get('type') == 'assistant':
                for b in msg.get('content') or []:
                    if b.get('type') != 'tool_use':
                        continue
                    eff['tools'][b['name']] += 1
                    if b['name'] in ('Agent', 'Task'):
                        eff['spawns'] += 1
                    cmd = (b.get('input') or {}).get('command') or ''
                    for rx, kind in ((CHECK_RE, 'check'), (COMMIT_RE, 'commit')):
                        m = rx.search(cmd)
                        if m:
                            pending[b['id']] = (kind, m.groups(), d.get('timestamp'))
            if d.get('type') == 'user' and isinstance(msg.get('content'), list):
                for b in msg['content']:
                    if b.get('type') == 'tool_result' and b.get('tool_use_id') in pending:
                        kind, groups, t = pending.pop(b['tool_use_id'])
                        text = tool_text(b)
                        if kind == 'check':
                            eff['checks'].append({'chapter': int(groups[0]), 'status': check_status(text)})
                        elif not b.get('is_error') and '"ok": false' not in text:
                            eff['commits'].append({'chapter': int(groups[1]), 'action': groups[0],
                                                   'at': ts(d['timestamp']) if d.get('timestamp') else None})
    seen_sub = set()
    for f in sub_files:
        for d in jl(f):
            msg = d.get('message') or {}
            if d.get('type') == 'assistant' and msg.get('id') and msg['id'] not in seen_sub:
                seen_sub.add(msg['id'])
                usage_add(eff['sub'], msg.get('usage') or {})
    # 일부 호환 엔드포인트의 기록에는 output_tokens가 없다. 매 회차 result 이벤트 집계와 비교해 큰 값을 사용한다.
    res = {}
    for t in meta['turns']:
        for d in jl(run / t['log']):
            if d.get('type') == 'result':
                usage_add(res, d.get('usage') or {})
    eff['result_output_tokens'] = res.get('output_tokens', 0)
    eff['tools'] = dict(eff['tools'])
    return eff


def codex_efficiency(run, meta):
    eff = {'main': {}, 'sub': {}, 'tools': Counter(), 'spawns': 0, 'compactions': 0,
           'main_calls': 0, 'max_context': 0, 'checks': [], 'commits': []}
    for t in meta['turns']:
        for d in jl(run / t['log']):
            if d.get('type') == 'turn.completed':
                u = d.get('usage') or {}
                eff['main']['input_tokens'] = eff['main'].get('input_tokens', 0) + int(u.get('input_tokens') or 0)
                eff['main']['cache_read_input_tokens'] = (eff['main'].get('cache_read_input_tokens', 0)
                                                          + int(u.get('cached_input_tokens') or 0))
                eff['main']['output_tokens'] = eff['main'].get('output_tokens', 0) + int(u.get('output_tokens') or 0)
            item = d.get('item') or {}
            if d.get('type') == 'item.completed':
                kind = item.get('type')
                eff['tools'][kind] += 1
                cmd = item.get('command') or ''
                m = CHECK_RE.search(cmd)
                if m:
                    eff['checks'].append({'chapter': int(m.group(1)), 'status': check_status(item.get('aggregated_output'))})
                m = COMMIT_RE.search(cmd)
                if m and item.get('exit_code') == 0:
                    eff['commits'].append({'chapter': int(m.group(2)), 'action': m.group(1), 'at': None})
    # codex의 input_tokens에는 cached 부분이 이미 포함된다.
    eff['main']['input_tokens'] = eff['main'].get('input_tokens', 0) - eff['main'].get('cache_read_input_tokens', 0)
    # --json에는 주 스레드만 있다. 하위 agent의 토큰·횟수는 CODEX_HOME/sessions의 rollout에서 cwd로 이번 실행에 귀속시킨다.
    eff['spawns'], eff['agents'] = 0, Counter()
    for rollout in codex_rollouts(run):
        first, last = None, None
        for d in jl(rollout):
            if first is None:
                first = d
            if (d.get('payload') or {}).get('type') == 'token_count':
                last = (d['payload'].get('info') or {}).get('total_token_usage') or last
        source = ((first or {}).get('payload') or {}).get('source')
        if not (isinstance(source, dict) and 'subagent' in source) or not last:
            continue
        spawn = source['subagent'].get('thread_spawn') or {}
        eff['spawns'] += 1
        eff['agents'][spawn.get('agent_path', '?').rsplit('/', 1)[-1]] += 1
        cached = int(last.get('cached_input_tokens') or 0)
        usage_add(eff['sub'], {'input_tokens': int(last.get('input_tokens') or 0) - cached,
                               'cache_read_input_tokens': cached, 'output_tokens': last.get('output_tokens')})
    eff['agents'] = dict(eff['agents'])
    eff['tools'] = dict(eff['tools'])
    return eff


def codex_rollouts(run):
    try:
        hosts = json.loads((Path(os.environ.get('BENCH_HOME', Path.home() / '.oh-story-bench')) / 'hosts.json')
                           .read_text(encoding='utf-8'))
        home = Path(os.path.expanduser(hosts['codex']['env']['CODEX_HOME']))
    except (OSError, KeyError, ValueError):
        return []
    proj = str((Path(run) / 'proj').resolve())
    found = []
    for f in (home / 'sessions').rglob('rollout-*.jsonl'):
        with open(f, encoding='utf-8', errors='replace') as handle:
            try:
                meta = json.loads(handle.readline()).get('payload') or {}
            except ValueError:
                continue
        cwd = meta.get('cwd') or ''
        if cwd and str(Path(cwd).resolve()) == proj:
            found.append(f)
    return found


def prose(run, meta, tell):
    book = run / 'proj' / meta['case']['book_dir']
    scripts = run / 'proj' / ('.claude/skills' if meta['host'] == 'claude-code' else '.agents/skills') / 'story-long-write/scripts'
    state_path = book / '추적/_tracking-state.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.is_file() else {}
    records = state.get('wordcount_records') or {}
    out = []
    for n in range(meta['start_committed'] + 1, meta.get('end_committed', meta['start_committed']) + 1):
        files = sorted((book / '본문').glob(f'제{n:03d}장*.md'))
        if not files:
            out.append({'chapter': n, 'missing': True})
            continue
        f = files[0]
        rec = records.get(str(n)) or {}
        r = subprocess.run(['node', str(scripts / 'check-ai-patterns.js'), '--json', str(f)],
                           capture_output=True, text=True)
        sev = Counter()
        try:
            data = json.loads(r.stdout or '{}')
            for finding in (data.get('findings') if isinstance(data, dict) else data) or []:
                sev[finding.get('severity', 'unknown')] += 1
        except (ValueError, AttributeError):
            sev['parse_error'] += 1
        row = {'chapter': n, 'file': f.name, 'actual': rec.get('actual'), 'target': rec.get('target'),
               'final_status': rec.get('status'), 'resolution': rec.get('resolution'),
               'detector': dict(sev)}
        if tell:
            r = subprocess.run([sys.executable, str(Path(tell) / 'detectors/human_ref_check.py'), str(f)],
                               capture_output=True, text=True)
            m = re.search(r'(\d+) 项越界', r.stdout)
            row['human_ref_out_of_range'] = int(m.group(1)) if m else None
        out.append(row)
    return out


def summarize(run, tell):
    run = Path(run)
    meta = json.loads((run / 'meta.json').read_text(encoding='utf-8'))
    eff = (claude_efficiency if meta['host'] == 'claude-code' else codex_efficiency)(run, meta)
    chapters = max(1, meta.get('end_committed', 0) - meta['start_committed'])
    wall = sum(t['ended'] - t['started'] for t in meta['turns'])
    tot = {}
    usage_add(tot, eff['main'])
    usage_add(tot, eff['sub'])
    all_in = tot.get('input_tokens', 0) + tot.get('cache_read_input_tokens', 0) + tot.get('cache_creation_input_tokens', 0)
    first = {}
    for c in eff['checks']:
        first.setdefault(c['chapter'], c['status'])
    return {
        'run': run.name, 'host': meta['host'], 'model': meta.get('model'), 'pkg': meta['pkg'].get('ref'),
        'case': meta['case']['id'], 'chapters_committed': meta.get('end_committed', 0) - meta['start_committed'],
        'chapters_goal': meta['case']['chapters'], 'user_turns': len(meta['turns']),
        'per_chapter': {
            'wall_min': round(wall / 60 / chapters, 1),
            'input_tokens_total_M': round(all_in / chapters / 1e6, 2),
            'input_uncached_K': round(tot.get('input_tokens', 0) / chapters / 1e3, 1),
            'output_tokens_K': round(max(tot.get('output_tokens', 0), eff.get('result_output_tokens', 0))
                                     / chapters / 1e3, 1),
            'main_calls': round(eff['main_calls'] / chapters, 1),
            'tool_calls': round(sum(eff['tools'].values()) / chapters, 1),
            'spawns': round(eff['spawns'] / chapters, 2),
        },
        'max_main_context_K': round(eff['max_context'] / 1e3, 1), 'compactions': eff['compactions'],
        'first_check_status': first, 'commits': eff['commits'], 'tools': eff['tools'],
        'prose': prose(run, meta, tell),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('runs', nargs='+')
    ap.add_argument('--table', action='store_true')
    ap.add_argument('--tell')
    a = ap.parse_args()
    rows = [summarize(r, a.tell) for r in a.runs]
    if not a.table:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return
    keys = ['wall_min', 'input_tokens_total_M', 'input_uncached_K', 'output_tokens_K', 'main_calls', 'tool_calls', 'spawns']
    print('| run | 章 | ' + ' | '.join(keys) + ' | ctx峰值K | 压缩 | 首检带内 | blocking/advisory |')
    print('|' + '---|' * (len(keys) + 6))
    for r in rows:
        inband = sum(1 for s in r['first_check_status'].values() if s in ('internal_pass', 'borderline'))
        blk = sum(p.get('detector', {}).get('blocking', 0) for p in r['prose'])
        adv = sum(p.get('detector', {}).get('advisory', 0) for p in r['prose'])
        print(f"| {r['run']} | {r['chapters_committed']}/{r['chapters_goal']} | "
              + ' | '.join(str(r['per_chapter'][k]) for k in keys)
              + f" | {r['max_main_context_K']} | {r['compactions']} | {inband}/{len(r['first_check_status'])} | {blk}/{adv} |")


if __name__ == '__main__':
    main()
