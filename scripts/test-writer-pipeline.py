#!/usr/bin/env python3
"""공개 CLI 회귀: 구간 폐포, 기존 권 개요, 조립 및 참조 불러오기 단계 축소."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / 'skills/story-long-write/scripts'


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='writer-pipeline-')
        self.addCleanup(self.tmp.cleanup)
        self.book = Path(self.tmp.name) / '雾港 来信'
        self.outline = self.put('개요/상세개요_제001장.md', '### 제 1 장：一封信\n- 单元ID/位置：L1-01；第1拍\n- 目标情绪：犹疑→决定替朋友保管信件\n')
        self.volume = self.put('개요/권개요_제1권.md', self.volume_text())
        headings = ['当前位置', '长期约束', '核心角色状态', '活跃伏笔', '近三章速记', '下一章承诺', '连贯性风险']
        self.put('추적/문맥.md', '\n'.join('## ' + h + '\n无\n' for h in headings))
        self.put('설정/문체.md', '# 文风\n' + '以对话与选择推进，保留必要的直接心理描述。\n' * 15)
        self.put('설정/소재본문안내.md', '# 关系\n保留人物各自的诉求，以具体选择推进关系。')

    def put(self, name, body):
        file = self.book / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(body, encoding='utf-8')
        return file

    def call(self, script, *args, env=None):
        return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                              cwd=self.tmp.name, capture_output=True, encoding='utf-8',
                              env={**os.environ, 'PYTHONIOENCODING': 'ascii', **(env or {})})

    def view(self, *args):
        return self.call('outline_view.py', *args, self.volume)

    def build(self):
        return self.call('build_writer_prompt.py', '--project', self.book, '--chapter', 1)

    def volume_text(self, unit='L1-01'):
        return f'''# 第一卷
卷首约束：不能打开信。
## 卷契约
> 作用域：卷级常任
信件内容本卷不揭示。
### 剧情单元 {unit}
> 作用域：单元级 {unit}
- 章节范围：第1-3章
- 单元情绪引擎：犹疑→朋友托付→决定保管
- 单元节拍/章功能分配：第1章接信，第2章质疑，第3章保管
#### 供给自查
> 作用域：批次底稿 {unit}｜状态：在用
供给材料
### 剧情单元 L1-010
> 作用域：单元级 L1-010
不能串卡
'''

    def test_arc_rows_sliced_in_template_form(self):
        # 권 개요 템플릿의 감정 곡선 첫 열은 ‘第{N}章’이다. 단위별 구간 추출에서도 해당 단위의 행만 남긴다.
        text = self.volume_text() + ('## 情绪弧线\n> 作用域：卷级常任\n| 章 | 定位 |\n|---|---|\n'
                                     '| 第1章 | 高压 |\n| 第3章 | 推进 |\n| 第5章 | 低压 |\n| 7 | 关系 |\n')
        self.volume.write_text(text, encoding='utf-8')
        out = self.view('--unit', 'L1-01').stdout
        self.assertIn('| 第1章 | 高压 |', out)
        self.assertIn('| 第3章 | 推进 |', out)
        self.assertNotIn('第5章', out)
        self.assertNotIn('| 7 |', out)

    def test_declared_ids_and_closure(self):
        for unit in ['L1-01', 'D2-03', 'U03']:
            with self.subTest(unit=unit):
                self.volume.write_text(self.volume_text(unit), encoding='utf-8')
                result = self.view('--unit', unit, '--stage', 'write')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('卷首约束', result.stdout)
                self.assertIn('本卷不揭示', result.stdout)
                self.assertNotIn('供给材料', result.stdout)
                self.assertNotIn('不能串卡', result.stdout)
                self.assertEqual(self.view('--check', '--strict').returncode, 0)

    def test_default_view_is_the_writing_closure(self):
        result = self.view('--unit', 'L1-01')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('本卷不揭示', result.stdout)
        self.assertNotIn('供给材料', result.stdout)
        self.assertIn('供给材料', self.view('--unit', 'L1-01', '--stage', 'outline').stdout)

    def test_legacy_unit_field(self):
        self.volume.write_text('## 第一单元\n- **单元ID**：L1-01\n旧约束', encoding='utf-8')
        result = self.view('--unit', 'L1-01')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('旧约束', result.stdout)

    def test_missing_unit_is_error(self):
        self.assertEqual(self.view('--unit', 'L1-02').returncode, 1)

    def test_legacy_contract_is_conservative(self):
        self.volume.write_text('# 卷纲\n## 卷契约\n终局真相不能揭示\n### 剧情单元 L1-01\n旧卡', encoding='utf-8')
        for mode in [('--contract',), ('--unit', 'L1-01')]:
            result = self.view(*mode)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('终局真相不能揭示', result.stdout)
            self.assertIn('未声明', result.stderr)
        self.assertEqual(self.view('--check').returncode, 0)
        self.assertEqual(self.view('--check', '--strict').returncode, 1)

    def test_invalid_scope_does_not_silently_drop(self):
        self.volume.write_text('## 卷契约\n> 作用域：卷级常任错误\n不能丢失', encoding='utf-8')
        self.assertEqual(self.view('--contract').returncode, 1)

    def test_history_for_sections_and_rows(self):
        text = self.volume_text() + '\n#### 老底稿\n> 作用域：批次底稿 L1-01｜状态：已退役\n旧方案\n'
        text += '\n#### 老裁定\n> 作用域：单元级 L1-01｜状态：已退役\n旧口径\n'
        text += '\n## 常任补充\n> 作用域：卷级常任\n- ⊘ 旧行\n'
        self.volume.write_text(text, encoding='utf-8')
        for stage in ['outline', 'write']:
            current = self.view('--unit', 'L1-01', '--stage', stage).stdout
            for old in ['旧方案', '旧口径', '旧行']:
                self.assertNotIn(old, current)
        history = self.view('--unit', 'L1-01', '--history').stdout
        for old in ['旧口径', '旧行']:
            self.assertIn(old, history)
        # 이전 권 개요의 배치 기초 자료는 개요 편성 프로필에서만 나타나고 기본 집필 프로필에는 포함되지 않는다.
        self.assertNotIn('旧方案', history)
        self.assertIn('旧方案', self.view('--unit', 'L1-01', '--history', '--stage', 'outline').stdout)

    def test_fenced_example_not_a_section_and_blank_scope(self):
        text = self.volume_text().replace('## 卷契约\n', '## 卷契约\n\n\n\n')
        text += '\n```md\n## 假章节\n> 作用域：单元级 L9-99\n```\n'
        self.volume.write_text(text, encoding='utf-8')
        self.assertEqual(self.view('--check', '--strict').returncode, 0)
        self.assertEqual(self.view('--unit', 'L9-99').returncode, 1)

    def test_builder_native_path_and_downgrade(self):
        out = self.book / 'prompt.txt'
        result = self.call('build_writer_prompt.py', '--project', self.book, '--chapter', 1, '--out', out)
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = out.read_text(encoding='utf-8')
        self.assertIn(str((self.book / '본문/제001장_一封信.md').resolve()), prompt)
        self.assertIn('第1章接信', prompt)
        self.assertNotIn('不能串卡', prompt)
        self.assertIn('참조 축소: 가능', result.stdout)
        self.assertNotIn('위 내용이 프롬프트 본문입니다', prompt)

    def test_builder_injects_author_memory_query(self):
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('author_preferences(작가 기억', result.stdout)
        self.assertIn('작가 기억: 관련 active 항목 없음', result.stdout)
        (self.book / '.story-deployed').write_text('agents_version: 34\n', encoding='utf-8')
        event = {'schema_version': 1, 'event_id': 'e1', 'operation': {'action': 'remember', 'preference': {
            'kind': 'prose_style', 'scope': {'level': 'global', 'value': None}, 'assertion': '对话一律用直角引号',
            'quote': '对话一律用「」', 'source_ref': 'test', 'source': 'explicit_user', 'confidence': 'high',
            'importance': 'high', 'status': 'active', 'reason': '作者明确要求', 'conflicts_with': [],
            }}}
        memory_input = Path(self.tmp.name) / 'memory.json'
        memory_input.write_text(json.dumps(event, ensure_ascii=False), encoding='utf-8')
        recorded = self.call('author_memory_commit.py', 'record', '--workspace', self.book, '--input', memory_input)
        self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)
        result = self.build()
        self.assertIn('- 对话一律用直角引号（AP001）', result.stdout)
        self.assertIn('작가 기억: 1개 반영', result.stdout)

    def test_builder_reports_missed_author_memory_in_author_words(self):
        # 한도를 넘어서 넣지 못한 항목을 조용히 생략하지 않는다. 주입 블록에는 집필자가 읽는 행만 넣고 2KB 한도를 온전히 계산한다.
        # 대조 보고서는 누락 항목을 모두 명시하며 처음 20개 번호로 제한하지 않는다. 장 끝에 작가에게 전달할 문장도 구성한다.
        (self.book / '.story-deployed').write_text('agents_version: 34\n', encoding='utf-8')
        self.assertEqual(self.call('author_memory_commit.py', 'init', '--workspace', self.book).returncode, 0)
        operations = [{'action': 'remember', 'preference': {
            'kind': 'prose_style', 'scope': {'level': 'global', 'value': None},
            'assertion': f'习惯{n:02d}：' + '写' * 36, 'quote': f'第{n}条习惯', 'source_ref': 'test',
            'source': 'explicit_user', 'confidence': 'high', 'importance': 'medium', 'status': 'active',
            'reason': '作者明确要求', 'conflicts_with': [],
        }} for n in range(1, 41)]
        memory_input = Path(self.tmp.name) / 'memory.json'
        for revision, batch in enumerate((operations[:32], operations[32:])):  # 트랜잭션 하나에는 최대 32개 항목을 넣는다.
            memory_input.write_text(json.dumps({'schema_version': 1, 'transaction_id': f'flood-{revision}',
                                                'expected_state_revision': revision, 'operations': batch},
                                               ensure_ascii=False), encoding='utf-8')
            committed = self.call('author_memory_commit.py', 'commit', '--workspace', self.book, '--input', memory_input)
            self.assertEqual(committed.returncode, 0, committed.stdout + committed.stderr)
        out = self.book / 'prompt.txt'
        result = self.call('build_writer_prompt.py', '--project', self.book, '--chapter', 1, '--out', out)
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = out.read_text(encoding='utf-8')
        injected = [line for line in prompt.splitlines() if line.startswith('- 习惯')]
        self.assertEqual(len(injected), 15)  # 행당 133바이트이므로 2048바이트에 15개가 들어간다. 이전 JSON 외곽 구조 기준으로는 8개뿐이었다.
        self.assertEqual(sum(len((line + '\n').encode('utf-8')) for line in injected) <= 2048, True)
        # 중요도가 같으면 최근 갱신 순으로 정렬한다. 두 번째 묶음(AP033-040)을 먼저 넣고 첫 번째 묶음은 AP007까지만 넣는다.
        self.assertNotIn('习惯08：', prompt)
        self.assertNotIn('넣지 못함', prompt)  # 작가에게 전달할 말은 대조 보고서에만 넣고 집필자 프롬프트에는 넣지 않는다.
        report = result.stdout.split('아래 내용은 프롬프트에 넣지 않습니다', 1)[1]
        self.assertIn('이번 장에 25개를 넣지 못함(AP008, ', report)
        self.assertIn('AP032)', report)
        self.assertIn('기록한 집필 습관 중 이번 장에 포함하지 못한 항목이 25개입니다: 「习惯08：写写写写写写写写写…」', report)
        self.assertIn('「习惯15：写写写写写写写写写…」 등. ‘작가 기억 정리’를 요청하면 비슷한 항목을 합치거나 잘 쓰지 않는 항목의 우선순위를 낮출 수 있습니다.', report)

    def test_builder_merges_multi_genre_misses_by_importance(self):
        # 작품의 두 장르를 각각 조회한 뒤 합친다. 한 조회에서 빠져도 다른 조회에 포함되면 누락이 아니며 양쪽에 포함돼도 한 번만 주입한다.
        # 합친 누락 항목은 중요도순이다. 뒤 조회에서 빠진 high 습관은 앞 조회에서 빠진 low 습관보다 먼저 나오며 8개 미만이면 ‘等’을 붙이지 않는다.
        (self.book / '.story-deployed').write_text('agents_version: 34\n', encoding='utf-8')
        self.put('설정/소재방향.md', '# 题材定位\n- 题材类型：都市 · 悬疑\n')
        self.assertEqual(self.call('author_memory_commit.py', 'init', '--workspace', self.book).returncode, 0)

        def op(assertion, importance, level='global', value=None):
            return {'action': 'remember', 'preference': {
                'kind': 'prose_style', 'scope': {'level': level, 'value': value}, 'assertion': assertion,
                'quote': assertion, 'source_ref': 'test', 'source': 'explicit_user', 'confidence': 'high',
                'importance': importance, 'status': 'active', 'reason': '作者明确要求', 'conflicts_with': [],
            }}

        first = ([op(f'全局低{n:02d}：' + '写' * 35, 'low') for n in range(1, 11)]  # AP001-010
                 + [op('全局高：短句推进', 'high')]  # AP011
                 + [op(f'悬疑高{n:02d}：' + '写' * 35, 'high', 'genre', '悬疑') for n in range(1, 9)])  # AP012-019
        second = [op(f'都市高{n:02d}：' + '写' * 35, 'high', 'genre', '都市') for n in range(1, 17)]  # AP020-035
        memory_input = Path(self.tmp.name) / 'memory.json'
        for revision, batch in enumerate((first, second)):
            memory_input.write_text(json.dumps({'schema_version': 1, 'transaction_id': f'genres-{revision}',
                                                'expected_state_revision': revision, 'operations': batch},
                                               ensure_ascii=False), encoding='utf-8')
            committed = self.call('author_memory_commit.py', 'commit', '--workspace', self.book, '--input', memory_input)
            self.assertEqual(committed.returncode, 0, committed.stdout + committed.stderr)
        out = self.book / 'prompt.txt'
        result = self.call('build_writer_prompt.py', '--project', self.book, '--chapter', 1, '--out', out)
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = out.read_text(encoding='utf-8')
        self.assertEqual(prompt.count('- 全局高：短句推进（AP011）'), 1)  # 두 조회에 모두 포함되더라도 한 번만 주입한다.
        self.assertIn('- 全局低07：', prompt)  # 미스터리 조회에 포함되고 도시물 조회에서 빠졌으면 포함된 것으로 본다.
        report = result.stdout.split('아래 내용은 프롬프트에 넣지 않습니다', 1)[1]
        self.assertIn('이번 장에 4개를 넣지 못함(AP035, AP008, AP009, AP010)', report)
        self.assertIn('기록한 집필 습관 중 이번 장에 포함하지 못한 항목이 4개입니다: 「都市高16：写写写写写写写写…」「全局低08：', report)
        self.assertIn('「全局低10：写写写写写写写写…」. ‘작가 기억 정리’', report)  # 8개 미만이면 ‘等’을 붙이지 않는다.

    def test_builder_keeps_misses_from_earlier_genre_query(self):
        # 앞 조회에서만 누락된 해당 장르 습관은 합칠 때 뒤 조회 결과로 덮어 지우면 안 된다.
        # 앞 조회에서 밀려났지만 뒤 조회에 포함된 전역 습관은 누락으로 보지 않는다.
        (self.book / '.story-deployed').write_text('agents_version: 34\n', encoding='utf-8')
        self.put('설정/소재방향.md', '# 题材定位\n- 题材类型：都市 · 悬疑\n')
        self.assertEqual(self.call('author_memory_commit.py', 'init', '--workspace', self.book).returncode, 0)

        def op(assertion, importance, level='global', value=None):
            return {'action': 'remember', 'preference': {
                'kind': 'prose_style', 'scope': {'level': level, 'value': value}, 'assertion': assertion,
                'quote': assertion, 'source_ref': 'test', 'source': 'explicit_user', 'confidence': 'high',
                'importance': importance, 'status': 'active', 'reason': '作者明确要求', 'conflicts_with': [],
            }}

        first = ([op(f'全局低{n:02d}', 'low') for n in range(1, 5)]  # AP001-004, 행당 25바이트
                 + [op('全局高', 'high')]  # AP005
                 + [op(f'悬疑高{n:02d}：' + '写' * 35, 'high', 'genre', '悬疑') for n in range(1, 17)])  # AP006-021
        second = [op(f'都市高{n:02d}：' + '写' * 35, 'high', 'genre', '都市') for n in range(1, 6)]  # AP022-026
        memory_input = Path(self.tmp.name) / 'memory.json'
        for revision, batch in enumerate((first, second)):
            memory_input.write_text(json.dumps({'schema_version': 1, 'transaction_id': f'early-{revision}',
                                                'expected_state_revision': revision, 'operations': batch},
                                               ensure_ascii=False), encoding='utf-8')
            committed = self.call('author_memory_commit.py', 'commit', '--workspace', self.book, '--input', memory_input)
            self.assertEqual(committed.returncode, 0, committed.stdout + committed.stderr)
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = result.stdout.split('아래 내용은 프롬프트에 넣지 않습니다', 1)[1]
        # 미스터리 조회에서는 AP021과 AP002-004가 빠지고 도시물 조회에서는 모두 들어간다. AP002-004는 포함된 것으로 본다.
        self.assertIn('이번 장에 1개를 넣지 못함(AP021)', report)
        self.assertIn('- 全局低04（AP004）', result.stdout)

    def remember(self, workspace, assertion, *, book_root=None, level='global', value=None):
        event = {'schema_version': 1, 'event_id': f'm-{assertion}', 'operation': {'action': 'remember', 'preference': {
            'kind': 'prose_style', 'scope': {'level': level, 'value': value}, 'assertion': assertion,
            'quote': assertion, 'source_ref': 'test', 'source': 'explicit_user', 'confidence': 'high',
            'importance': 'high', 'status': 'active', 'reason': '作者明确要求', 'conflicts_with': [],
        }}}
        memory_input = Path(self.tmp.name) / 'memory.json'
        memory_input.write_text(json.dumps(event, ensure_ascii=False), encoding='utf-8')
        args = ['record', '--workspace', workspace, '--input', memory_input]
        if book_root is not None:
            args += ['--book-root', book_root]
        recorded = self.call('author_memory_commit.py', *args)
        self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)

    def move_book(self, *parts):
        target = Path(self.tmp.name).joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(self.book), str(target))
        self.book = target
        return target

    def memory_files(self, root):
        return sorted(str(p.relative_to(root)) for p in root.rglob('*') if '작가기억' in str(p))

    def test_builder_finds_workspace_without_deploy_marker(self):
        # DSH 등은 .story-deployed를 쓰지 않는다. 장편/의 부모, .active-book, 작품분석실/ 또는 프로젝트 기억으로 작업 공간을 식별한다.
        # 전역(프로젝트) 항목과 작품 항목을 모두 대신 조회하며 주 세션의 수동 조회로 되돌리지 않는다.
        cases = [
            ('长篇下的书', ('多书甲', '장편', '雾港 来信'), None),
            ('有 .active-book', ('多书乙', '雾港 来信'), '.active-book'),
            ('有拆文库', ('多书丙', '雾港 来信'), '작품분석실'),
        ]
        for name, parts, marker in cases:
            with self.subTest(layout=name):
                book = self.move_book(*parts)
                workspace = Path(self.tmp.name) / parts[0]
                if marker == '.active-book':
                    (workspace / marker).write_text('雾港 来信\n', encoding='utf-8')
                elif marker:
                    (workspace / marker).mkdir()
                # 처음에 작품 항목만 있고 루트에 프로젝트 기억이 없으면 장편/, .active-book, 작품분석실/로만 식별한다.
                self.remember(workspace, f'{name}：本书条目', book_root=book, level='book', value='雾港 来信')
                result = self.build()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'- {name}：本书条目（BP', result.stdout)
                self.assertNotIn('스크립트 조회 실패', result.stdout)
                self.remember(workspace, f'{name}：全局条目')
                result = self.build()
                self.assertIn(f'- {name}：全局条目（AP', result.stdout)
                self.assertIn(f'- {name}：本书条目（BP', result.stdout)

    def test_builder_single_book_layout_without_deploy_marker(self):
        # DSH의 일반적인 단일 작품 구조: 작품 루트가 작업 공간이며 프로젝트 기억과 작품 기억(书级/)이 모두 작품 디렉터리에 있다.
        # 바깥 디렉터리에 작품분석실/가 있어도 판정을 바꾸지 않는다. 프로젝트 기억이 있는 가장 가까운 상위 디렉터리가 작업 공간이다.
        self.move_book('外层', '雾港 来信')
        (Path(self.tmp.name) / '外层' / '작품분석실').mkdir()
        # 书级/의 작품 기억만 있어도 작품 디렉터리를 식별한다. 그렇지 않으면 작품 항목을 바깥에서 찾아 누락한다.
        self.remember(self.book, '单书：本书条目', book_root=self.book, level='book', value='雾港 来信')
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('- 单书：本书条目（BP001）', result.stdout)
        self.remember(self.book, '单书：全局条目')
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('- 单书：全局条目（AP001）', result.stdout)
        self.assertIn('- 单书：本书条目（BP001）', result.stdout)

    def test_builder_never_takes_book_under_long_dir_as_workspace(self):
        # 장편/ 아래의 작품 디렉터리는 작업 공간으로 보지 않는다. 기억 디렉터리에 예전 오이동으로 생긴 빈 书级/가 있어도
        # 부모 이름이 长篇인 것을 우선해 작업 공간을 식별한다. 단일 작품 구조로 조회하면 작가 기억 도구가 오류를 낸다.
        book = self.move_book('多书丁', '장편', '雾港 来信')
        workspace = book.parent.parent
        self.remember(workspace, '长篇优先：本书条目', book_root=book, level='book', value='雾港 来信')
        (book / '.story' / '작가기억' / '书级').mkdir()
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('- 长篇优先：本书条目（BP001）', result.stdout)
        self.assertNotIn('스크립트 조회 실패', result.stdout)

    def test_builder_never_takes_home_as_workspace(self):
        # 홈 디렉터리 자체는 작업 공간으로 보지 않는다. 홈에 잘못 놓인 .active-book으로 작품을 홈에 귀속시키면 안 된다.
        book = self.move_book('假主目录', '雾港 来信')
        home = book.parent
        (home / '.active-book').write_text('雾港 来信\n', encoding='utf-8')
        self.remember(home, '主目录：本书条目', book_root=book, level='book', value='雾港 来信')
        result = self.call('build_writer_prompt.py', '--project', self.book, '--chapter', 1,
                           env={'HOME': str(home), 'USERPROFILE': str(home)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('집필 작업 공간을 찾지 못했습니다', result.stdout)

    def test_builder_does_not_guess_workspace_over_book_memory(self):
        # 식별 단서가 없는 작업 공간 바로 아래에 작품과 작품 기억만 있으면 작품 디렉터리를 작업 공간으로 조회할 때 단일 작품 구조의 구형 기억으로 간주해
        # 书级/로 이동시켜 이후 올바른 작업 공간 조회가 모두 실패한다. 식별하지 못하면 조회·쓰기를 하지 않고 주 세션이 작업 공간을 정하도록 한다.
        book = self.move_book('无迹象工作区', '雾港 来信')
        workspace = book.parent
        self.remember(workspace, '无迹象：本书条目', book_root=book, level='book', value='雾港 来信')
        before = self.memory_files(workspace)
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('집필 작업 공간을 찾지 못했습니다', result.stdout)
        self.assertEqual(self.memory_files(workspace), before, '代查不得挪动书级记忆')
        query = self.call('author_memory_commit.py', 'query', '--workspace', workspace, '--book-root', book,
                          '--kind', 'prose_style')
        self.assertEqual(query.returncode, 0, query.stdout + query.stderr)
        self.assertEqual(json.loads(query.stdout)['lines'], ['- 无迹象：本书条目（BP001）'])

    def test_builder_queries_scoped_author_memory(self):
        (self.book / '.story-deployed').write_text('agents_version: 34\n', encoding='utf-8')
        self.put('설정/소재방향.md', '# 题材定位\n- 题材类型：都市 · 悬疑（无言情线）\n')
        memory_input = Path(self.tmp.name) / 'memory.json'
        for n, (level, value, assertion) in enumerate([
                ('genre', '悬疑', '悬疑线索先埋后揭'), ('workflow', '장편', '长篇每章结尾留钩子'),
                ('genre', '仙侠', '仙侠用古风称谓'), ('workflow', '交稿', '交稿前先报字数'),
                ('genre', '言情', '言情线慢热')], 1):
            event = {'schema_version': 1, 'event_id': f's{n}', 'operation': {'action': 'remember', 'preference': {
                'kind': 'prose_style', 'scope': {'level': level, 'value': value}, 'assertion': assertion,
                'quote': assertion, 'source_ref': 'test', 'source': 'explicit_user', 'confidence': 'high',
                'importance': 'high', 'status': 'active', 'reason': '作者明确要求', 'conflicts_with': [],
                }}}
            memory_input.write_text(json.dumps(event, ensure_ascii=False), encoding='utf-8')
            recorded = self.call('author_memory_commit.py', 'record', '--workspace', self.book, '--input', memory_input)
            self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        # 작품 장르와 장편 워크플로에 한정된 항목도 조회해야 하며 전역·작품 항목만 남기면 안 된다.
        self.assertIn('悬疑线索先埋后揭', result.stdout)
        self.assertIn('长篇每章结尾留钩子', result.stdout)
        self.assertNotIn('仙侠用古风称谓', result.stdout)
        # 판단할 수 없는 범위 값은 조용히 버리지 않고 주 세션에 맡긴다.
        self.assertNotIn('言情线慢热', result.stdout)  # ‘无言情线’(로맨스 서사 없음)은 로맨스 장르가 아니다.
        self.assertIn('범위 한정 항목은 조회하지 않음(장르: 仙侠, 言情；절차: 交稿)', result.stdout)

    def test_builder_injects_author_decided_with_a_cap(self):
        # 방향 설정 때 저장한 작품별 결정(선호·금지선)을 집필 시 볼 수 있어야 한다. 스크립트가 ‘作者已定’을 주입하고 길면 잘라 원문을 안내한다.
        self.put('설정/소재방향.md', '# 题材定位\n## 基本信息\n- 题材类型：都市\n## 作者已定\n'
                 '- {作者在对话里定下的方向}\n- 不写感情线，主角全程单身\n- 否掉：重生开局（作者嫌老套）\n'
                 '## 读者契约\n- 核心读者承诺：不注入这一节\n')
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('——— 작가가 확정한 사항(작품의 결정', result.stdout)
        self.assertIn('- 不写感情线，主角全程单身', result.stdout)
        self.assertNotIn('{作者在对话里定下的方向}', result.stdout)
        self.assertNotIn('不注入这一节', result.stdout)
        self.assertIn('작가 확정 사항: 반영함', result.stdout)
        self.put('설정/소재방향.md', '## 作者已定\n' + ''.join(f'- 第{i}条红线：' + '禁' * 40 + '\n' for i in range(30)))
        long = self.build()
        self.assertIn('600자 초과로 잘랐습니다', long.stdout)
        self.assertIn('第0条红线', long.stdout)
        self.assertNotIn('第29条红线', long.stdout)
        self.put('설정/소재방향.md', '# 题材定位\n- 题材类型：都市\n')
        self.assertIn('작가 확정 사항: 소재 방향 파일에 없거나 비어 있어 넣지 않음', self.build().stdout)

    def test_builder_matches_genre_cards_when_the_book_has_none(self):
        # 새 작품 1장에는 장르별 본문 안내 카드가 없다. 스크립트가 ‘题材类型’으로 카드를 찾아 주 세션이 3K 색인을 전부 읽지 않게 한다.
        (self.book / '설정/소재본문안내.md').unlink()
        self.put('설정/소재방향.md', '# 题材定位\n- 题材类型：都市日常 · 豪门总裁\n')
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        cards = SCRIPTS.parent / 'references' / 'genre-prose-cards'
        self.assertIn(f"주 장르 {cards / '都市日常.md'}(확신도 high)；보조 장르 {cards / '豪门总裁.md'}", result.stdout)
        self.assertIn('참조 축소: 불가(장르 본문 안내 카드에 유효한 내용이 없음)', result.stdout)
        # 최장 일치 우선: ‘玄幻言情’, ‘仙侠言情’의 ‘玄幻’, ‘仙侠’는 다른 카드의 짧은 별칭이므로 주 카드보다 먼저 선택되면 안 된다.
        for line, main, loser in [('玄幻言情', '玄幻言情.md', '传统玄幻.md'),
                                  ('仙侠言情', '玄幻言情.md', '东方仙侠.md'),
                                  ('传统玄幻 · 玄幻言情', '传统玄幻.md', None)]:
            with self.subTest(genre=line):
                self.put('설정/소재방향.md', f'# 题材定位\n- 题材类型：{line}\n')
                out = self.build().stdout
                self.assertIn(f"주 장르 {cards / main}", out)
                if loser:
                    self.assertNotIn(str(cards / loser), out)
                else:
                    self.assertIn(f"보조 장르 {cards / '玄幻言情.md'}", out)
        self.put('설정/소재방향.md', '# 题材定位\n- 题材类型：蒸汽朋克考古\n')
        self.assertIn('일치하는 카드도 없습니다', self.build().stdout)

    def test_bare_out_archives_into_book_work_dir(self):
        result = self.call('build_writer_prompt.py', '--project', self.book, '--chapter', 1, '--out')
        self.assertEqual(result.returncode, 0, result.stderr)
        work = (self.book / '.story/work/제001장').resolve()
        archived = work / 'writer_prompt.md'
        self.assertTrue(archived.is_file())
        self.assertIn(f'보관 파일: {archived}', result.stdout)
        prompt = archived.read_text(encoding='utf-8')
        # 구간 경로는 작품 내부의 구체적 경로이며 본문/이나 /tmp 아래에 두지 않는다.
        self.assertIn(str(work / '전반.md'), prompt)
        self.assertIn(str(work / '후반.md'), prompt)
        self.assertFalse((self.book / '본문').exists() and any((self.book / '본문').iterdir()))

    def test_incomplete_replacements_keep_full_recall(self):
        original = self.volume.read_text(encoding='utf-8')
        for broken in ['missing-card', 'empty-card', 'placeholder-emotion', 'missing-unit', 'missing-engine', 'missing-tempo']:
            with self.subTest(broken=broken):
                self.set_inputs_for_downgrade(original)
                card = self.book / '설정/소재본문안내.md'
                if broken == 'missing-card': card.unlink()
                if broken == 'empty-card': card.write_text('# 题材卡\n[待补充]', encoding='utf-8')
                if broken == 'placeholder-emotion':
                    self.outline.write_text(self.outline.read_text(encoding='utf-8').replace('犹疑→决定替朋友保管信件', '[待补充][待补充][待补充]'), encoding='utf-8')
                if broken == 'missing-unit': self.volume.unlink()
                if broken in ['missing-engine', 'missing-tempo']:
                    word = '单元情绪引擎' if broken == 'missing-engine' else '单元节拍/章功能分配'
                    self.volume.write_text('\n'.join(line for line in original.splitlines() if word not in line), encoding='utf-8')
                result = self.build()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('참조 축소: 불가', result.stdout)
                self.assertIn('전체 참조', result.stdout)

    def set_inputs_for_downgrade(self, volume):
        self.volume.write_text(volume, encoding='utf-8')
        self.put('설정/소재본문안내.md', '关系通过保管信件的具体选择推进。')
        self.outline.write_text('### 第 1 章：一封信\n- 单元ID/位置：L1-01\n- 目标情绪：犹疑→决定替朋友保管信件', encoding='utf-8')

    def test_required_state_and_title(self):
        state = self.book / '추적/문맥.md'
        original = state.read_text(encoding='utf-8')
        for heading in ['活跃伏笔', '长期约束', '下一章承诺']:
            state.write_text(original.replace('## ' + heading, '## 改名'), encoding='utf-8')
            self.assertEqual(self.build().returncode, 2)
        state.write_text(original, encoding='utf-8')
        self.outline.write_text('章名缺失', encoding='utf-8')
        self.assertEqual(self.build().returncode, 2)

    def test_previous_tail_and_nearest_heading(self):
        self.put('개요/상세개요_제011장.md', '### 제 11 장：回信\n')
        self.put('본문/제9장_旧.md', '### 제9장 旧\n九')
        self.put('본문/제10장_最近.md', '# 제010장 最近\n十')
        self.put('본문/제99장_未来.md', '#### 제99장 未来\n后续秘密')
        result = self.call('build_writer_prompt.py', '--project', self.book, '--chapter', 11)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(': # 제011장 回信', result.stdout)
        self.assertNotIn('后续秘密', result.stdout)
        (self.book / '본문/제10장_最近.md').unlink()
        self.assertEqual(self.call('build_writer_prompt.py', '--project', self.book, '--chapter', 11).returncode, 2)

    def test_multiline_unit_fields_and_short_style(self):
        self.put('설정/문체.md', '## 对话\n优先用短问句推进分歧，保留必要的直接心理。')
        text = self.volume_text().replace('单元节拍/章功能分配：第1章接信，第2章质疑，第3章保管', '单元节拍/章功能分配：\n  - 第1章接信\n  - 第2章质疑')
        self.volume.write_text(text, encoding='utf-8')
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('참조 축소: 가능', result.stdout)
        self.assertIn('第2章质疑', result.stdout)

    def test_no_benchmark_book_downgrades_without_style(self):
        # 작가가 비교 작품을 쓰지 않기로 했고 문체도 없으면 감정·리듬은 상세 개요와 단위 카드에서 얻는다. 문체 누락으로 전체 참조를 불러오지 않는다.
        style = self.book / '설정' / '문체.md'
        if style.exists():
            style.unlink()
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('참조 축소: 가능. 비교 작품 없음', result.stdout)
        (self.book / '비교작품' / '某书').mkdir(parents=True)
        (self.book / '비교작품' / '某书' / '문체.md').write_text('x', encoding='utf-8')
        self.assertIn('참조 축소: 불가', self.build().stdout)

    def test_imported_book_own_analysis_is_not_benchmark(self):
        # 가져온 작품의 분석 디렉터리가 拆文库 안에 작품 디렉터리와 같은 이름으로 있어도 자기 작품이므로 비교 작품 없음으로 판정한다.
        style = self.book / '설정' / '문체.md'
        if style.exists():
            style.unlink()
        for base in (self.book.parent / '작품분석실', self.book / '작품분석실'):
            (base / self.book.name).mkdir(parents=True, exist_ok=True)
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('참조 축소: 가능. 비교 작품 없음', result.stdout)
        (self.book.parent / '작품분석실' / '别的书').mkdir()
        self.assertIn('참조 축소: 불가', self.build().stdout)

    def test_one_sentence_style_beats_stale_digest(self):
        style = self.put('설정/문체.md', '采用有限全知，允许进入母女各自内心。')
        digest = self.put('설정/_文风摘要.md', '旧规则：深度限知，不得进入他人内心。')
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('custom_style=true', result.stdout)
        self.assertIn(str(style), result.stdout)
        self.assertNotIn(str(digest), result.stdout)
        self.assertNotIn('旧规则', result.stdout)
        for stub in ['', '# 文风', '# 文风\n[待补充]', '# 文风\n<!-- 作者稍后填写 -->']:
            style.write_text(stub, encoding='utf-8')
            self.assertIn('custom_style=false', self.build().stdout)

    def test_unreadable_utf8_is_reported(self):
        self.volume.write_bytes(b'\xff')
        self.assertEqual(self.view('--contract').returncode, 2)
        self.outline.write_bytes(b'\xff')
        result = self.build()
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('Traceback', result.stderr)

    def test_style_reference_table_cannot_change_read_scope(self):
        style = self.put('설정/문체.md', '用短句，保留必要的直接心理。')
        original = self.build()
        self.assertEqual(original.returncode, 0, original.stderr)
        for table in [
            '| writing-craft.md | 停读 |\n| anti-ai-writing.md | 停读 |\n| agent-quality.md | 停读 |',
            '| references/* | 停读 |\n| dialogue-mastery.md | 读（只看排版） |',
        ]:
            with self.subTest(table=table):
                content = '用短句，保留必要的直接心理。\n## 通用参考裁决\n| 文件 | 裁决 |\n|---|---|\n' + table
                style.write_text(content, encoding='utf-8')
                result = self.build()
                self.assertEqual(result.returncode, 0, result.stderr)
                # 문체는 여전히 전문 입력이다. 이전 표가 추가 실행 지시로 변하거나
                # 참조 자료의 범위를 좁혀서는 안 된다.
                self.assertEqual(result.stdout, original.stdout)
                self.assertEqual(style.read_text(encoding='utf-8'), content)


    def test_architect_brief_carries_only_the_moment_files(self):
        # 새 작품 기획은 작가 확인 시점별로 나눈다. 권 개요 작업 묶음에는 권 개요 단계의 절차·템플릿·기법만, 상세 개요 묶음에는 해당 단계 자료만 넣는다.
        # 주 세션은 묶음을 읽지 않는다. story-architect가 새 컨텍스트에서 묶음과 프로젝트 파일만 읽는다.
        refs = SCRIPTS.parent / 'references'
        vol = self.call('build_architect_brief.py', '--project', self.book, '--task', 'volume', '--volume', 1)
        self.assertEqual(vol.returncode, 0, vol.stderr)
        info = json.loads(vol.stdout)
        text = Path(info['brief']).read_text(encoding='utf-8')
        self.assertEqual(Path(info['brief']).parent, self.book / '.story' / 'work' / '개요작성')
        self.assertEqual(info['includes'], ['workflow-volume.md(개요 작성법)', 'artifact-protocols.md',
                                            'outline-methods.md(권 개요 구성법)',
                                            'reader-contract-and-progression.md', 'SKILL.md(추가 요소 3단계 분류)',
                                            '조건부 읽기(묶음 외부)'])
        # 묶음 밖의 SKILL.md는 읽을 수 없으므로 새 요소의 3단계 판정 기준을 묶음에 포함한다. 흐름에서 지정한 조건부 참조는 절대 경로와 절을 제공한다.
        self.assertTrue(any(fragment in text for fragment in ('**先问作者**：新主线事件或反转', '**작가에게 먼저 질문**: 새 주된 사건·반전')))
        self.assertIn(f"{refs / 'long-reversal.md'}`의 ‘反转类型’ 절", text)
        self.assertNotIn('## 情感虐心三板斧', text)
        # 권별 개요 구성법은 항상 묶음에 포함한다. 여덟 지점, 감정 모듈 공식, 무대 전환은 조건에 따라 묶음 밖에서 읽는다.
        self.assertTrue(any(s in text for s in ('### 剧情单元设计', '### 플롯 단위 설계')))
        self.assertNotIn('## 八节点故事结构', text)
        self.assertNotIn('## 情绪模块公式', text)
        self.assertIn(f"{refs / 'outline-methods.md'}`의 ‘八节点故事结构’ 절", text)
        self.assertIn(f"{refs / 'character-relations.md'}`의 ‘感情线阶段’ 절", text)
        # 절차 파일에서는 ‘排纲方法’만 추출하며 주 세션의 읽기 목록과 작가 보고 템플릿은 묶음에 넣지 않는다.
        self.assertIn('## 排纲方法', text)
        self.assertTrue(any(s in text for s in ('### 排纲刻度', '### 개요의 규모')))
        self.assertNotIn('<!-- author-report -->', text)
        self.assertNotIn('## 主会话', text)
        self.assertNotIn('## 细纲（第 N 章）', text)
        self.assertLess(info['chars'], 30000)
        # story-architect는 명령을 실행할 수 없으므로 이번 장들을 포괄하는 단위 폐포를 스크립트가 추출해 묶음에 넣는다.
        self.volume.write_text(self.volume_text() + '### 剧情单元 L1-02\n> 作用域：单元级 L1-02\n'
                               '- 章节范围：第4-12章\n- 单元情绪引擎：保管→被追查→反将一军\n', encoding='utf-8')
        first = json.loads(self.call('build_architect_brief.py', '--project', self.book, '--task', 'outline',
                                     '--chapters', '1-3').stdout)
        later = json.loads(self.call('build_architect_brief.py', '--project', self.book, '--task', 'outline',
                                     '--chapters', '4-10').stdout)
        self.assertIn('opening-design.md(도입부 계획)', first['includes'])
        self.assertFalse(any(name.startswith('opening-design.md') for name in later['includes']))
        self.assertIn('plot-core-methods.md', first['includes'])
        self.assertIn('plot-core-methods.md(도입부 흡인 요소 제외)', later['includes'])
        self.assertTrue(any('단위 L1-01' in name for name in first['includes']))
        self.assertTrue(any('단위 L1-02' in name for name in later['includes']))
        self.assertFalse(any('단위 L1-01' in name for name in later['includes']))
        outline_text = Path(first['brief']).read_text(encoding='utf-8')
        self.assertIn('卷首约束', outline_text)  # 권 단위 상시 항목도 폐포와 함께 묶음에 넣는다.
        self.assertIn('직접 명령을 실행하지 마세요', outline_text)
        both = json.loads(self.call('build_architect_brief.py', '--project', self.book, '--task', 'outline',
                                    '--chapters', '2-5').stdout)
        both_text = Path(both['brief']).read_text(encoding='utf-8')
        self.assertIn('保管→被追查', both_text)
        self.assertEqual(both_text.count('信件内容本卷不揭示'), 1)  # 두 단위에 걸쳐도 권 단위 상시 항목은 한 번만 제공한다.
        uncovered = self.call('build_architect_brief.py', '--project', self.book, '--task', 'outline', '--chapters', '30-31')
        self.assertEqual(uncovered.returncode, 2)
        self.assertIn('해당 범위의 플롯 단위가 없음: 제30-31장', uncovered.stderr)
        # 단위가 요청의 일부만 포괄하면 일부만 조용히 제공하지 말고 빠진 장을 명시한다.
        partial = self.call('build_architect_brief.py', '--project', self.book, '--task', 'outline', '--chapters', '10-14')
        self.assertEqual(partial.returncode, 2, partial.stdout)
        self.assertIn('플롯 단위가 일부 범위만 포함함. 누락: 제13-14장', partial.stderr)
        rules = json.loads(self.call('build_architect_brief.py', '--project', self.book, '--task', 'outline',
                                     '--chapters', '30-31', '--rules-only').stdout)
        self.assertFalse(any('권 개요 발췌' in name for name in rules['includes']))
        self.assertIn('## 细纲（第 N 章）', outline_text)
        self.assertIn('## 开篇规划', outline_text)
        self.assertNotIn('## 开篇落笔', outline_text)
        self.assertTrue(any(s in outline_text for s in ('## 高潮构建公式', '## 절정 구성')))
        self.assertIn('## 噱头分类与开篇流程', outline_text)
        self.assertNotIn('<!-- author-report -->', outline_text)
        later_text = Path(later['brief']).read_text(encoding='utf-8')
        self.assertTrue(any(s in later_text for s in ('## 高潮构建公式', '## 절정 구성')))
        self.assertNotIn('## 噱头分类与开篇流程', later_text)
        # 상세 개요 템플릿은 도입부 7형식과 결말부 13형식에서 고르게 한다. 두 표는 포함하되 실전 템플릿은 넣지 않는다.
        self.assertIn('## 章尾钩子 13 式', outline_text)
        self.assertIn('## 章首钩子 7 式', outline_text)
        self.assertNotIn('## 章尾实战模板', outline_text)
        # 이름과 공식 열만 넣고 예문은 넣지 않는다. 상세 개요가 예문 문장 구조를 그대로 따를 수 있기 때문이다.
        self.assertTrue(any(s in outline_text for s in ('| 13 | 留白钩子 | 只展示反应，不揭示发生了什么 |\n', '| 13 | 여백 | 반응만 공개 |\n')))
        self.assertNotIn('他看了信', outline_text)
        self.assertNotIn('아버지가 추궁한 뒤에도 예량천은 차분한 얼굴로', outline_text)
        self.assertIn('long-chapter-hooks.md(장 끝 훅 13종, 장 시작 훅 7종)', later['includes'])
        self.assertIn('第1节：主角卡', outline_text)
        self.assertNotIn('第3节：反派设计', outline_text)
        world = json.loads(self.call('build_architect_brief.py', '--project', self.book, '--task', 'world').stdout)
        world_text = Path(world['brief']).read_text(encoding='utf-8')
        self.assertIn('## 作者已定', world_text)  # 설정 템플릿을 묶음에 포함해 방향 설정 때 저장한 작가 결정을 읽을 수 있게 한다.
        self.assertIn('核心梗三层递进设计', world_text)
        self.assertTrue(any(s in world_text for s in ('## 金手指', '## 특전')))
        self.assertIn(f"{refs / 'character-relations.md'}`의 ‘感情线阶段’ 절", world_text)
        self.assertNotIn('## 微创新与差异化设计', world_text)
        self.assertNotIn('## 感情流人设核心法', world_text)
        self.assertNotIn('全书体量与阶段总览', world_text)
        self.assertNotIn('主会话自己定设定时读', world_text)  # 주 세션의 읽기 목록은 묶음에 넣지 않는다.
        self.assertNotIn('주 세션이 직접 설정을 정한다면', world_text)
        self.assertIn(f"{refs / 'female-audience-writing.md'}`의 전문", world_text)
        self.assertIn('추가 요소 분류「新增物三级」에 따라 작가에게 먼저 물어야', world_text)
        too_many = self.call('build_architect_brief.py', '--project', self.book, '--task', 'outline', '--chapters', '1-11')
        self.assertEqual(too_many.returncode, 2)
        self.assertIn('상세 개요는 묶음당 최대 10장', too_many.stderr)


    def test_architect_brief_names_unit_cards_missing_scope_lines(self):
        # 단위 카드에 ‘> 作用域：’ 행이 없으면 추출기가 식별하지 못한다. 오류에는 해당 카드를 명시하고 장 범위가 필요하다는 일반 설명만 하지 않는다.
        self.volume.write_text('# 第一卷\n### 剧情单元 L1-01\n- 章节范围：第1-3章\n', encoding='utf-8')
        result = self.call('build_architect_brief.py', '--project', self.book, '--task', 'outline', '--chapters', '1-3')
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn('‘> 作用域：单元级 {单元ID}’ 선언 행이 없습니다: 권개요_제1권.md「剧情单元 L1-01」', result.stderr)
        self.assertIn('--check --strict', result.stderr)


class ImportOutlineBriefTests(unittest.TestCase):
    """가져오기 시 배치별 상세 개요 역산: 이번 배치 규칙, 추출한 요약 핵심, 측정한 길이, 겹치는 플롯 단위 카드만 묶음에 포함한다."""

    SCRIPT = ROOT / 'skills/story-import/scripts/build_outline_brief.py'
    SUMMARY = ('## 第{n}章\n\n**概要**：概要不进包{n}\n\n**关键事件**：\n1. 江晨推门{n}\n2. 看见雨\n\n'
               '**因果**：雨夜来信\n\n**局面结果**：信被收下\n\n**涉及**：江晨，老周\n\n**信息变化**：读者知道信是假的\n\n'
               '**状态变化**：江晨 犹疑→决定\n\n**三维节奏**：三维节奏不进包\n\n**章尾钩子**：悬念：信里写了谁\n\n'
               '**证据**：证据不进包\n\n**情节点**：\n\n'
               'P1 **雨夜推门**：类型行动 | 白描不进包 | 涉及江晨 | 地点无 | 物品无 | 时间无\n\n'
               '主题标签悬念 | 基调：紧张\n\n---\n\n'
               'P2 **收下来信**：类型转折点 | 白描不进包 | 涉及江晨 | 地点无 | 物品信 | 时间无\n\n'
               '主题标签悬念 | 基调：压抑\n')

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='import-brief-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.book = self.root / '旧书'
        for chapter in range(1, 26):
            self.put(f'본문/제{chapter:03d}장_雨夜.md', f'# 제{chapter}장 雨夜\n\n他推开门，看见雨。' + '字' * chapter + '\n')
            if chapter != 7:
                self.summary(chapter, self.SUMMARY.format(n=chapter))
        self.volume(('L1-01', '第1-12章', '接信'), ('L1-02', '第13-25章', '反击'))

    def put(self, name, body):
        file = self.book / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(body, encoding='utf-8')

    def summary(self, chapter, body):
        file = self.root / '작품분석실' / '旧书' / '장별분석' / f'제{chapter}장_요약.md'
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(body, encoding='utf-8')

    def volume(self, *cards):
        """cards: (단위 ID, 장 범위, 비트). 가져오기 권 개요 템플릿에 따라 단위 카드를 작성한다."""
        body = ''.join(f'### 剧情单元 {uid}\n> 作用域：单元级 {uid}\n\n- 单元ID：{uid}\n- 章节范围：{span}\n'
                       f'- 单元节拍/章功能分配：{beat}\n- 下一单元因果钩子：第1-2章的回响\n\n' for uid, span, beat in cards)
        self.put('개요/권개요_제1권.md', '# 제1권 卷纲\n\n## 剧情单元卡（反推）\n> 作用域：卷级常任\n\n' + body +
                 '## 人物弧线\n> 作用域：卷级常任\n\n| 角色 | 本卷起点 |\n|---|---|\n| 甲 | 第1-99章 |\n')

    def call(self, chapters):
        return subprocess.run([sys.executable, str(self.SCRIPT), '--project', str(self.book), '--chapters', chapters],
                              cwd=self.root, capture_output=True, encoding='utf-8',
                              env={**os.environ, 'PYTHONIOENCODING': 'ascii'})

    def brief(self, chapters):
        result = self.call(chapters)
        self.assertEqual(result.returncode, 0, result.stderr)
        info = json.loads(result.stdout)
        return info, Path(info['brief']).read_text(encoding='utf-8')

    def test_brief_carries_batch_evidence_and_rules(self):
        info, text = self.brief('1-12')
        self.assertEqual(Path(info['brief']).parent, (self.book / '.story' / 'work' / '개요작성').resolve())
        # story-architect는 명령을 실행할 수 없으므로 스크립트가 visible_chars_v1 기준으로 길이를 측정한다.
        self.assertEqual(info['metric'], 'visible_chars_v1')
        self.assertEqual(info['lengths']['3'], len('他推开门，看见雨。') + 3)
        self.assertEqual(info['missing_summaries'], [7])
        self.assertEqual((info['chapters'], info['next']), ('1-12', 13))
        self.assertIn('### 剧情单元 L1-01', text)
        self.assertIn('- 单元节拍/章功能分配：接信', text)
        self.assertNotIn('L1-02', text)
        self.assertNotIn('| 甲 |', text)  # 다른 표가 섞여 들어오지 않는다.
        self.assertIn('## 细纲（第 N 章）', text)
        self.assertIn('직접 명령을 실행하지 마세요', text)
        self.assertIn('가져오기기록.md', text)

    def test_brief_extracts_summary_fields_instead_of_paths_only(self):
        info, text = self.brief('1-12')
        # 상세 개요에 필요한 필드를 묶음에 추출해 실행자가 요약 전체를 다시 읽지 않도록 한다.
        for want in ('핵심 사건: 江晨推门3 看见雨', '인과: 雨夜来信', '상황 결과: 信被收下', '관련 인물: 江晨，老周',
                     '정보 변화: 读者知道信是假的', '상태 변화: 江晨 犹疑→决定', '장 끝 훅: 悬念：信里写了谁',
                     'P1 雨夜推门｜行动｜紧张；P2 收下来信｜转折点｜压抑'):
            self.assertIn(want, text)
        for skip in ('概要不进包', '三维节奏不进包', '证据不进包', '白描不进包'):
            self.assertNotIn(skip, text)
        # 요약이 없는 장은 본문을 읽어야 한다. chars에는 실행자가 실제 읽어야 할 전체 분량을 계산한다.
        body7 = (self.book / '본문' / '제007장_雨夜.md').read_text(encoding='utf-8')
        self.assertIn('요약: 찾지 못함', text)
        self.assertEqual(info['chars'], len(''.join(text.split())) + len(''.join(body7.split())))

    def test_first_chapter_carries_previous_hook(self):
        # 도입 훅은 앞 장의 결말 훅에서 얻는다. 배치 내부 각 장의 앞 장 요약은 이미 묶음에 있으므로 첫 장만 별도로 가져온다.
        _, text = self.brief('11-20')
        self.assertIn('- 앞 장(제10장)의 끝 훅: 悬念：信里写了谁', text)
        self.assertEqual(text.count('훅: 悬念'), 11)  # 10개 장 각각의 장 끝 훅 + 첫 장에 함께 제공되는 직전 장.
        _, first = self.brief('1-12')
        self.assertNotIn('- 앞 장(', first)

    def test_legacy_summary_labels_still_extracted(self):
        self.summary(2, '- 关键事件：推门\n\n**出场人物**：\n\n| 角色 | 本章重要性 |\n|---|---|\n| 林雷 | major |\n| 希尔曼 | minor |\n\n'
                        '- **卡点与伏笔**：结尾卡点：信没拆\n')
        _, text = self.brief('1-12')
        self.assertIn('핵심 사건: 推门', text)
        self.assertIn('관련 인물: 林雷、希尔曼', text)
        self.assertIn('장 끝 훅: 结尾卡点：信没拆', text)
        self.assertIn('상황 결과: (요약에 없음)', text)

    def test_batch_shrinks_when_brief_too_big(self):
        for chapter in range(1, 26):
            if chapter != 7:
                self.summary(chapter, self.SUMMARY.format(n=chapter).replace('看见雨', '雨' * 3000))
        info, text = self.brief('1-12')
        first, last = map(int, info['chapters'].split('-'))
        self.assertEqual(first, 1)
        self.assertLess(last, 10)  # 묶음은 총분량에 따라 나누므로 10장보다 적을 수 있다.
        self.assertEqual(info['next'], last + 1)
        self.assertLessEqual(info['chars'], info['limit'])
        self.assertTrue(Path(info['brief']).name.endswith(f'제001-{last:03d}장.md'))
        self.assertNotIn(f'### 第{last + 1}章', text)

    def test_unit_cards_selected_by_chapter_range_field(self):
        self.volume(('L1-01', '第1-5章', '接信'), ('L1-02', '第6-9章', '反击'), ('L1-03', '第10-10章', '余波'),
                    ('L1-04', '第15-15章', '单元编号不当章号'), ('L1-05', '第13-25章', '远处'))
        _, text = self.brief('1-12')
        for card in ('### 剧情单元 L1-01', '### 剧情单元 L1-02', '### 剧情单元 L1-03'):
            self.assertIn(card, text)
        self.assertNotIn('L1-04', text)  # ‘章节范围’ 필드만 인식하며 다른 필드의 ‘第1-2章’은 인정하지 않는다.
        self.assertNotIn('L1-05', text)

    def test_cards_the_writer_cannot_read_stop_the_brief(self):
        # 본문 작성 시 outline_view.py --unit이 인식하지 못하는 권 개요(범위 행 누락, 구형 표 형식 단위)는 작업 묶음에도 포함하지 않는다.
        self.put('개요/권개요_제1권.md', '# 제1권\n\n### 剧情单元 L1-01\n- 章节范围：제1-12장\n')
        missing_scope = self.call('1-12')
        self.assertEqual(missing_scope.returncode, 2)
        self.assertIn('作用域：单元级', missing_scope.stderr)
        self.put('개요/권개요_제1권.md', '# 제1권\n\n## 剧情单元（反推）\n| 单元ID | 章节范围 |\n|---|---|\n| L1-1 | 제1-12장 |\n')
        table = self.call('1-12')
        self.assertEqual(table.returncode, 2)
        self.assertIn('--check --strict', table.stderr)

    def test_import_volume_template_passes_writer_gates(self):
        # 가져오기 권 개요 템플릿은 그대로 저장해도 엄격한 추출 검증을 통과해 집필 시 단위별 카드를 얻어야 한다. 장 범위를 채우면 작업 묶음도 인식한다.
        doc = (ROOT / 'skills/story-import/references/structure-mapping-long.md').read_text(encoding='utf-8')
        marker = next(marker for marker in ('#### 目标格式模板（개요/권개요_제X권.md）', '### 권 개요 역추론 템플릿(개요/권개요_제X권.md)') if marker in doc)
        after = doc.split(marker, 1)[1]
        template = after.split('```markdown\n', 1)[1].split('\n```\n', 1)[0]
        self.put('개요/권개요_제1권.md', template.replace('第{A}-{B}章', '第1-25章') + '\n')
        volume = self.book / '개요' / '권개요_제1권.md'
        view = lambda *args: subprocess.run(
            [sys.executable, str(SCRIPTS / 'outline_view.py'), *args, str(volume)],
            capture_output=True, encoding='utf-8', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
        check = view('--check', '--strict')
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertIn('问题 0 ／ 告警 0', check.stdout)
        unit = view('--unit', 'L1-01')
        self.assertEqual(unit.returncode, 0, unit.stderr)
        self.assertIn('单元情绪引擎', unit.stdout)
        _, text = self.brief('1-12')
        self.assertIn('### 剧情单元 L1-01', text)
        # 가져오기에 포함된 추출기 사본은 집필 측과 같으므로 양쪽 파싱이 달라지지 않는다.
        self.assertEqual((ROOT / 'skills/story-import/scripts/outline_view.py').read_bytes(),
                         (SCRIPTS / 'outline_view.py').read_bytes())

    def test_batch_bounds(self):
        too_many = self.call('1-21')
        self.assertEqual(too_many.returncode, 2)
        self.assertIn('최대 20장', too_many.stderr)
        too_few = self.call('1-5')
        self.assertEqual(too_few.returncode, 2)
        self.assertIn('최소 10장', too_few.stderr)
        info, text = self.brief('21-25')  # 작품의 마지막 배치는 10장 미만일 수 있다.
        self.assertIn('L1-02', text)
        self.assertIsNone(info['next'])
        beyond = self.call('20-30')
        self.assertEqual(beyond.returncode, 2)
        self.assertIn('본문은 제25장까지만 이전', beyond.stderr)

    def test_missing_volume_outline_stops(self):
        (self.book / '개요' / '권개요_제1권.md').unlink()
        result = self.call('1-12')
        self.assertEqual(result.returncode, 2)
        self.assertIn('권 개요가 없습니다', result.stderr)


class VolumeTemplateContractTests(unittest.TestCase):
    """artifact-protocols.md의 권 개요 템플릿은 그대로 저장해도 추출기의 엄격한 검증을 통과해야 한다."""

    def test_template_passes_strict_check(self):
        doc = (ROOT / 'skills/story-long-write/references/artifact-protocols.md').read_text(encoding='utf-8')
        after = doc.split('\n## 개요/권개요_제X권.md\n', 1)[1]
        template = after.split('```markdown\n', 1)[1].split('\n```\n', 1)[0]
        with tempfile.TemporaryDirectory(prefix='volume-template-') as tmp:
            volume = Path(tmp) / '개요' / '권개요_제1권.md'
            volume.parent.mkdir()
            volume.write_text(template + '\n', encoding='utf-8')
            run = lambda *args: subprocess.run(
                [sys.executable, str(SCRIPTS / 'outline_view.py'), *args, str(volume)],
                capture_output=True, encoding='utf-8', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
            check = run('--check', '--strict')
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            self.assertIn('问题 0 ／ 告警 0', check.stdout)
            unit = run('--unit', 'L1-01')
            self.assertEqual(unit.returncode, 0, unit.stderr)
            self.assertIn('### 剧情单元 L1-01', unit.stdout)
            self.assertEqual(unit.stderr, '')


if __name__ == '__main__':
    unittest.main()
