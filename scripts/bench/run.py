#!/usr/bin/env python3
"""벤치마크 사례를 실행한다. fixture로 격리 프로젝트를 만들고 지정 버전 패키지를 배포한 뒤 실제 CLI 세션으로 회차를 수행한다.

사용법:
  run.py --case mid-daily --pkg <pkg디렉터리> --host claude-code --out <runs디렉터리> [--label v0711]

fixture와 호스트 설정은 저장소 밖에 둔다(README.md 참조):
  BENCH_HOME(기본 ~/.oh-story-bench)/fixtures/<fixture>/   고정된 작품
  BENCH_HOME/hosts.json                                 호스트별 실행 파일·모델·자격 증명 파일
산출물(세션 로그, 프로젝트 스냅샷)은 --out에 저장하며 git에 넣지 않는다.
"""
import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import deploy  # noqa: E402

BENCH_HOME = Path(os.environ.get('BENCH_HOME', Path.home() / '.oh-story-bench'))
IDLE_S, HARD_S = 30 * 60, 4 * 60 * 60


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def host_env(cfg, home):
    env = {
        'HOME': str(home), 'USER': os.environ.get('USER', ''), 'LOGNAME': os.environ.get('USER', ''),
        'SHELL': '/bin/zsh', 'TERM': 'xterm-256color', 'LANG': 'zh_CN.UTF-8', 'LC_ALL': 'zh_CN.UTF-8',
        'PATH': cfg.get('path', '/usr/bin:/bin:/usr/sbin:/sbin'), 'TMPDIR': str(home / 'tmp'),
    }
    for k, v in cfg.get('env', {}).items():
        env[k] = v
    for k, f in cfg.get('env_files', {}).items():
        env[k] = Path(os.path.expanduser(f)).read_text(encoding='utf-8').strip()
    (home / 'tmp').mkdir(parents=True, exist_ok=True)
    return env


def claude_env(cfg, home):
    """real_home: 자격 증명은 실제 HOME에 있으므로 그대로 써야 한다(HOME을 바꾸면 Not logged in).
    사용자 설정·플러그인·CLAUDE.md는 --setting-sources로 제외하고 중첩 세션 환경 변수는 제거한다."""
    if not cfg.get('real_home'):
        return host_env(cfg, home)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('CLAUDE', 'OMC_'))}
    env.update(cfg.get('env', {}))
    return env


def keep_transcripts(sid, home):
    """real_home의 세션 기록은 실제 ~/.claude/projects에 저장된다. 실행 디렉터리로 복사해 metrics.py가 기존 방식으로 읽게 한다."""
    for main in (Path.home() / '.claude' / 'projects').glob(f'*/{sid}.jsonl'):
        dest = home / '.claude' / 'projects' / main.parent.name
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(main, dest / main.name)
        if (main.parent / sid).is_dir():
            shutil.copytree(main.parent / sid, dest / sid, dirs_exist_ok=True)


def drive_claude(cfg, proj, home, log, prompt, resume):
    """Claude Code stream-json 세션 한 회차. 백그라운드 하위 agent가 끝날 때까지 프로세스를 유지한다."""
    cmd = [os.path.expanduser(cfg['bin']), '-p', '--input-format', 'stream-json', '--output-format',
           'stream-json', '--verbose', '--permission-mode', 'bypassPermissions']
    if cfg.get('real_home'):
        # story-setup은 settings.local.json에 hooks를 등록하므로 project만 쓰면 훅이 작동하지 않는다.
        cmd += ['--setting-sources', 'project,local', '--strict-mcp-config']
    if cfg.get('model') and cfg['model'] != 'default':
        cmd += ['--model', cfg['model']]
    if resume:
        cmd += ['--resume', resume]
    err = open(str(log).replace('.jsonl', '.err'), 'w')
    p = subprocess.Popen(cmd, cwd=proj, env=claude_env(cfg, home), stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=err, text=True, encoding='utf-8')
    p.stdin.write(json.dumps({'type': 'user', 'message': {'role': 'user', 'content': prompt}},
                             ensure_ascii=False) + '\n')
    p.stdin.flush()
    q = queue.Queue()

    def reader():
        for line in p.stdout:
            q.put(line)
        q.put(None)
    threading.Thread(target=reader, daemon=True).start()
    out = open(log, 'w', encoding='utf-8')
    outstanding, closed, sid = set(), False, None
    start = last = time.time()
    while True:
        try:
            line = q.get(timeout=30)
        except queue.Empty:
            line = ''
        now = time.time()
        if line is None:
            break
        if line:
            last = now
            out.write(line)
            out.flush()
            try:
                d = json.loads(line)
            except ValueError:
                continue
            sid = d.get('session_id', sid)
            st = d.get('subtype')
            if d.get('type') == 'system' and st == 'task_started' and d.get('is_backgrounded'):
                outstanding.add(d['task_id'])
            if d.get('type') == 'system' and st == 'task_notification':
                outstanding.discard(d.get('task_id'))
            if d.get('type') == 'result' and not outstanding and not closed:
                p.stdin.close()
                closed = True
        if (now - last > IDLE_S or now - start > HARD_S) and not closed:
            out.write(json.dumps({'type': 'driver', 'event': 'timeout', 'outstanding': sorted(outstanding)}) + '\n')
            p.stdin.close()
            closed = True
        if closed and now - last > 600:
            p.kill()
            break
    p.wait(timeout=60)
    if cfg.get('real_home') and sid:
        keep_transcripts(sid, home)
    return sid


def drive_codex(cfg, proj, home, log, prompt, resume):
    if prompt.startswith('/story'):
        prompt = '$' + prompt[1:]
    base =[os.path.expanduser(cfg['bin']), 'exec', '-c', f'model="{cfg["model"]}"',
            '-c', f'projects."{proj}".trust_level="trusted"', '--json', '--skip-git-repo-check',
            '--dangerously-bypass-approvals-and-sandbox'] + cfg.get('extra_args', [])
    cmd = base + (['resume', resume, prompt] if resume else ['-C', str(proj), prompt])
    env = dict(os.environ) if cfg.get('inherit_env', True) else host_env(cfg, home)
    # 독립된 CODEX_HOME이 필요하다. 전역 설정의 플러그인(computer-use, 브라우저), notify 훅, 전역 skills를
    # 벤치마크 세션이 상속하면 측정이 오염되고 사용자 컴퓨터를 조작할 수도 있다.
    env.update({k: os.path.expanduser(v) for k, v in cfg.get('env', {}).items()})
    if 'CODEX_HOME' not in env or Path(env['CODEX_HOME']).resolve() == (Path.home() / '.codex').resolve():
        raise SystemExit('codex 主机必须在 hosts.json 里配置独立的 CODEX_HOME（见 README）')
    with open(log, 'w', encoding='utf-8') as out, open(str(log).replace('.jsonl', '.err'), 'w') as err:
        subprocess.run(cmd, cwd=proj, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                       timeout=HARD_S)
    sid = None
    for line in open(log, encoding='utf-8'):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get('type') == 'thread.started':
            sid = d.get('thread_id')
    return sid


DRIVERS = {'claude-code': drive_claude, 'codex': drive_codex}


def committed(book):
    state = book / '추적/_tracking-state.json'
    if not state.is_file():
        return 0
    return int(load_json(state).get('last_committed_chapter') or 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--case', required=True)
    ap.add_argument('--pkg', required=True)
    ap.add_argument('--host', required=True, choices=sorted(DRIVERS))
    ap.add_argument('--out', required=True)
    ap.add_argument('--label', default='')
    a = ap.parse_args()

    case = next(c for c in load_json(HERE / 'cases.json')['cases'] if c['id'] == a.case)
    hosts = load_json(BENCH_HOME / 'hosts.json')
    cfg = hosts[a.host]
    run_dir = Path(a.out).resolve() / '-'.join(x for x in (a.label, a.host, a.case) if x)
    if run_dir.exists():
        subprocess.run(['chmod', '-R', 'u+w', str(run_dir)], check=True)
        shutil.rmtree(run_dir)
    proj, home = run_dir / 'proj', run_dir / 'home'
    book = proj / case['book_dir']
    shutil.copytree(BENCH_HOME / 'fixtures' / case['fixture'], book)
    subprocess.run(['chmod', '-R', 'u+w', str(book)], check=True)  # fixture는 읽기 전용으로 고정되어 있을 수 있다.
    deploy.deploy(a.pkg, a.host, proj)
    subprocess.run(['git', 'init', '-q'], cwd=proj, check=True)
    home.mkdir(parents=True, exist_ok=True)

    start_ch = committed(book)
    goal = start_ch + case['chapters']
    meta = {'case': case, 'host': a.host, 'model': cfg.get('model'), 'pkg': load_json(Path(a.pkg) / 'PACKAGE.json'),
            'start_committed': start_ch, 'turns': []}
    prompts = list(case['turns'])
    sid, n = None, 0
    while prompts or (committed(book) < goal and n < len(case['turns']) + case.get('max_follow_ups', 0)):
        prompt = prompts.pop(0) if prompts else case['follow_up']
        log = run_dir / f't{n}.jsonl'
        t0 = time.time()
        sid = DRIVERS[a.host](cfg, proj, home, log, prompt, sid)
        meta['turns'].append({'prompt': prompt, 'log': log.name, 'session': sid, 'started': t0,
                              'ended': time.time(), 'committed_after': committed(book)})
        (run_dir / 'meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf-8')
        n += 1
    meta['end_committed'] = committed(book)
    (run_dir / 'meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf-8')
    print(run_dir)


if __name__ == '__main__':
    main()
