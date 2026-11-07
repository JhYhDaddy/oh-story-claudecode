#!/usr/bin/env python3
"""두 버전의 벤치마크 결과를 비교한다. 효율 개선 폭과 품질 비열등성 기준을 사용한다.

사용법:
  compare.py --base <run디렉터리>... --cand <run디렉터리>... --coverage <judge coverage 디렉터리>
             --pairwise <judge pairwise 디렉터리> [--tell <tell저장소>] [--json]

기준(비열등성, 모두 충족해야 통과; 사전 등록 프로토콜의 고정값이며 아래는 기본값):
  Q1 플롯 포인트 실현율(landed=1, summarized=0.5, missing=0; 미제출 장은 0): 후보 − 기준 ≥ −0.05
  Q2 장당 허용 범위 밖 추가: 후보 − 기준 ≤ +0.3
  Q3 쌍별 블라인드 평가: 승패가 있는 쌍 중 후보 승률 ≥ 0.35; 승패가 있는 쌍이 6개 미만이면 ‘근거 부족’
  Q4 장당 검사기 advisory: 후보 − 기준 ≤ +1.0; --tell 지정 시 인간 범위를 벗어난 항목의 중앙값 차이 ≤ +1
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import metrics  # noqa: E402

SCORE = {'landed': 1.0, 'summarized': 0.5, 'missing': 0.0}


def coverage_rows(cov_dir, runs):
    names = {Path(r).name for r in runs}
    rows = {}
    for f in Path(cov_dir).glob('*.json'):
        d = json.loads(f.read_text(encoding='utf-8'))
        if d['run'] not in names or not d.get('result'):
            continue
        beats = d['result'].get('beats') or []
        rate = sum(SCORE.get(b.get('status'), 0) for b in beats) / len(beats) if beats else 0.0
        rows[(d['host'], d['case'], d['chapter'])] = (rate, len(d['result'].get('unauthorized') or []))
    return rows


def side(runs, cov_dir, tell):
    summaries = [metrics.summarize(r, tell) for r in runs]
    cov = coverage_rows(cov_dir, runs)
    rates, unauth, adv, tells = [], [], [], []
    for s in summaries:
        goal_chapters = s['chapters_goal']
        committed = {p['chapter']: p for p in s['prose'] if not p.get('missing')}
        keys = [k for k in cov if k[0] == s['host'] and k[1] == s['case']]
        for k in keys:
            rates.append(cov[k][0])
            unauth.append(cov[k][1])
        rates.extend([0.0] * max(0, goal_chapters - len(keys)))  # 작성되지 않은 장은 전부 누락으로 계산한다.
        for p in committed.values():
            adv.append(p.get('detector', {}).get('advisory', 0))
            if p.get('human_ref_out_of_range') is not None:
                tells.append(p['human_ref_out_of_range'])
    eff = {}
    for key in ('wall_min', 'input_tokens_total_M', 'main_calls', 'spawns'):
        eff[key] = round(statistics.mean(s['per_chapter'][key] for s in summaries), 2)
    eff['compactions'] = sum(s['compactions'] for s in summaries)
    eff['chapters'] = f"{sum(s['chapters_committed'] for s in summaries)}/{sum(s['chapters_goal'] for s in summaries)}"
    return {
        'efficiency': eff,
        'coverage': round(statistics.mean(rates), 3) if rates else None,
        'unauthorized_per_chapter': round(statistics.mean(unauth), 2) if unauth else None,
        'advisory_per_chapter': round(statistics.mean(adv), 2) if adv else None,
        'tell_median': statistics.median(tells) if tells else None,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', nargs='+', required=True)
    ap.add_argument('--cand', nargs='+', required=True)
    ap.add_argument('--coverage', required=True)
    ap.add_argument('--pairwise', required=True)
    ap.add_argument('--tell')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    base, cand = side(a.base, a.coverage, a.tell), side(a.cand, a.coverage, a.tell)
    finals = [json.loads(f.read_text(encoding='utf-8'))['final'] for f in Path(a.pairwise).glob('*.json')]
    decisive = [f for f in finals if f in ('base', 'cand')]
    win = sum(f == 'cand' for f in decisive) / len(decisive) if decisive else None
    gates = {
        'Q1_coverage': (cand['coverage'] - base['coverage']) >= -0.05,
        'Q2_unauthorized': (cand['unauthorized_per_chapter'] - base['unauthorized_per_chapter']) <= 0.3,
        'Q3_pairwise': ('证据不足' if len(decisive) < 6 else win >= 0.35),
        'Q4_advisory': (cand['advisory_per_chapter'] - base['advisory_per_chapter']) <= 1.0,
    }
    if base['tell_median'] is not None and cand['tell_median'] is not None:
        gates['Q4_tell'] = (cand['tell_median'] - base['tell_median']) <= 1
    report = {'base': base, 'cand': cand,
              'pairwise': {'pairs': len(finals), 'decisive': len(decisive), 'cand_win_rate': win,
                           'tally': {k: finals.count(k) for k in ('cand', 'base', 'tie')}},
              'gates': gates}
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return
    print('| 指标 | 基线 | 候选 |\n|---|---|---|')
    for k in base['efficiency']:
        print(f"| {k} | {base['efficiency'][k]} | {cand['efficiency'][k]} |")
    for k in ('coverage', 'unauthorized_per_chapter', 'advisory_per_chapter', 'tell_median'):
        print(f'| {k} | {base[k]} | {cand[k]} |')
    print(f"\n配对盲评：{report['pairwise']}")
    print('门槛：' + '，'.join(f'{k}={v}' for k, v in gates.items()))


if __name__ == '__main__':
    main()
