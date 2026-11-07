#!/usr/bin/env python3
"""check, commit, accept-current-length의 런타임 종단 간 테스트."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STORYCTL = ROOT / "skills/story-long-write/scripts/storyctl.py"
TRACKING = ROOT / "skills/story-long-write/scripts/tracking_commit.py"


def position() -> dict[str, object]:
    return {"volume": "第一卷", "volume_start_chapter": 1, "story_time": "当日", "scene": "剪辑室"}


def initial_document() -> dict[str, object]:
    return {
        "schema_version": 1,
        "book_title": "最终闭环测试",
        "last_chapter": 0,
        "context": {
            "position": position(),
            "long_term_constraints": ["只写批准内容。"],
            "active_character_names": [],
            "continuity_risks": [],
            "recent_chapters": [],
            "next_chapter_commitments": [],
        },
        "character_snapshots": {},
        "foreshadow": [],
        "timeline_events": [],
    }


def transaction(chapter: int, revision: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "append",
        "chapter": chapter,
        "chapter_title": f"闭环测试·{chapter}",
        "expected_state_revision": revision,
        "delta": {
            "result": f"第{chapter}章完成。",
            "character_changes": [],
            "foreshadow_changes": [],
            "timeline_events": [],
            "constraints": [],
            "next_chapter_commitments": ["继续批准剧情。"],
        },
        "context": {
            "position": position(),
            "long_term_constraints": ["只写批准内容。"],
            "active_character_names": [],
            "continuity_risks": [],
        },
        "character_snapshots": {},
    }


class FinalChapterFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="final-wordcount-flow-")
        self.root = Path(self.temporary.name)
        self.project = self.root / "book"
        self.project.mkdir()
        self.run_tracking("init", initial_document())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_input(self, label: str, document: dict[str, object]) -> Path:
        path = self.root / f"{label}-{os.urandom(4).hex()}.json"
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        return path

    def run_process(
        self, args: list[str], *, expect: int = 0, env: dict[str, str] | None = None
    ) -> dict[str, object]:
        completed = subprocess.run(
            args, cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False, env=env
        )
        self.assertEqual(completed.returncode, expect, f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}")
        lines = completed.stdout.strip().splitlines()
        self.assertTrue(lines, completed.stderr)
        return json.loads(lines[-1])

    def run_tracking(self, command: str, document: dict[str, object]) -> dict[str, object]:
        path = self.write_input(command, document)
        return self.run_process(
            [sys.executable, str(TRACKING), command, "--project", str(self.project), "--input", str(path)]
        )

    def run_chapter(
        self, command: str, chapter: int, *, document: dict[str, object] | None = None, expect: int = 0,
        extra: list[str] | None = None, env: dict[str, str] | None = None,
    ) -> dict[str, object]:
        args = [
            sys.executable, str(STORYCTL), "chapter", command,
            "--project", str(self.project), "--chapter", str(chapter), *(extra or []),
        ]
        if document is not None:
            args.extend(["--input", str(self.write_input(f"chapter-{chapter}", document))])
        return self.run_process(args, expect=expect, env=env)

    def state(self) -> dict[str, object]:
        return json.loads((self.project / "추적/_tracking-state.json").read_text(encoding="utf-8"))

    def write_contract(
        self, chapter: int, actual: int, *, target: int = 1000, blocking: bool = False, extra: str = ""
    ) -> None:
        (self.project / "개요").mkdir(exist_ok=True)
        (self.project / "본문").mkdir(exist_ok=True)
        (self.project / "개요" / f"상세개요_제{chapter:03d}장.md").write_text(
            f"- 字数目标：{target} 字\n- 字数口径：visible_chars_v1\n{extra}\n"
            "| # | 情节点（谁做了什么） | 功能标签 | 执行边界 |\n|---|---|---|---|\n"
            "| 1 | 江晨完成一次审核 | 推进 | 不新增支线 |\n",
            encoding="utf-8",
        )
        prefix = "这不是夸奖，而是命令。" if blocking else ""
        fill = max(0, actual - len(prefix) - 1)
        (self.project / "본문" / f"제{chapter:03d}장_测试.md").write_text(
            f"# 第{chapter}章\n{prefix}" + "字" * fill + "。",
            encoding="utf-8",
        )

    def test_fix_punctuation_normalizes_body_before_the_single_check(self) -> None:
        self.write_contract(1, 1000)
        body = self.project / "본문" / "제001장_测试.md"
        body.write_text(body.read_text(encoding="utf-8").replace("字字字字", "字……字", 1), encoding="utf-8")
        plain = self.run_chapter("check", 1, expect=1)
        self.assertEqual(plain["status"], "blocked")
        self.assertEqual(plain["quality"]["status"], "fail")
        self.assertNotIn("punctuation_fixed", plain)
        args = [sys.executable, str(STORYCTL), "chapter", "check", "--project", str(self.project),
                "--chapter", "1", "--fix-punctuation"]
        fixed = self.run_process(args)
        self.assertTrue(fixed["punctuation_fixed"])
        self.assertEqual(fixed["quality"]["status"], "pass")
        self.assertNotIn("……", body.read_text(encoding="utf-8"))
        self.assertFalse(self.run_process(args)["punctuation_fixed"])

    def test_complete_user_flow_without_persisted_approval_state(self) -> None:
        # 체크포인트는 순수하다. 한 번 호출해도 추적 상태나 본문은 바뀌지 않는다.
        segment = self.root / "segment.md"
        segment.write_text("# 前半段\n" + "字" * 500, encoding="utf-8")
        before = self.state()
        checkpoint = self.run_process(
            [sys.executable, str(STORYCTL), "wordcount", "checkpoint", "--file", str(segment), "--target", "1000"]
        )
        self.assertEqual(checkpoint["remaining_user_range"], {"min": 350, "max": 650})
        self.assertEqual(self.state(), before)

        # 1: 분량과 차단 수준 품질 검사를 통과하면 정상 커밋한다.
        self.write_contract(1, 1000)
        checked = self.run_chapter("check", 1)
        self.assertEqual(checked["quality"]["status"], "pass")
        self.assertEqual(checked["available_actions"], ["commit"])
        committed = self.run_chapter("commit", 1, document=transaction(1, self.state()["state_revision"]))
        self.assertTrue(committed["tracking_committed"])

        # 2: 분량 미달(under)은 자동 커밋하지 않는다. accept가 바뀐 본문과 목표를 다시 읽은 뒤 한 번 커밋한다.
        self.write_contract(2, 800)
        checked = self.run_chapter("check", 2)
        self.assertEqual(
            checked["available_actions"],
            ["accept-current-length", "revise-outline-or-target", "discard"],
        )
        self.assertIsNone(checked["compression"])
        self.assertEqual(checked["state_revision"], self.state()["state_revision"])
        rejected = self.run_chapter(
            "commit", 2, document=transaction(2, self.state()["state_revision"]), expect=2
        )
        self.assertIn("outside the user band", rejected["message"])
        self.assertEqual(rejected["error_code"], "LENGTH_OUT_OF_BAND")
        self.assertEqual(self.state()["last_committed_chapter"], 1)
        self.write_contract(2, 801, target=1100)
        accepted = self.run_chapter(
            "accept-current-length", 2, document=transaction(2, self.state()["state_revision"])
        )
        self.assertTrue(accepted["tracking_committed"])
        record = self.state()["wordcount_records"]["2"]
        self.assertEqual((record["target"], record["actual"], record["status"]), (1100, 801, "under"))
        self.assertEqual(record["resolution"], "accepted_current_length")

        # 3: 분량 초과(over)는 결정론적으로 정한 삭제 범위에 따라 순수 삭제만 하는 축약을 정확히 한 번 제안한다.
        self.write_contract(3, 1200)
        checked = self.run_chapter("check", 3)
        self.assertEqual(checked["length"]["status"], "over")
        self.assertEqual(
            checked["available_actions"],
            ["compress-once", "accept-current-length", "revise-outline-or-target", "discard"],
        )
        self.assertEqual(
            checked["compression"],
            {
                "mode": "single_pass_remove_only",
                "remove_to_internal_band": {"min": 80, "max": 320},
                "remove_to_user_band": {"min": 50, "max": 350},
            },
        )
        rejected = self.run_chapter(
            "commit", 3, document=transaction(3, self.state()["state_revision"]), expect=2
        )
        self.assertIn("outside the user band", rejected["message"])
        self.assertEqual(self.state()["last_committed_chapter"], 2)

        # 허용된 한 번의 축약을 재현한다. 새 검사에서 허용 구간에 들어오면 커밋한다.
        self.write_contract(3, 1100)
        checked = self.run_chapter("check", 3)
        self.assertEqual(checked["length"]["status"], "internal_pass")
        self.assertEqual(checked["available_actions"], ["commit"])
        self.assertIsNone(checked["compression"])
        self.run_chapter("commit", 3, document=transaction(3, self.state()["state_revision"]))

        # 4: 차단 수준 품질 검사가 실패하면 커밋할 수 없다. 명시적으로 품질을 수정한 뒤 다음 장을 진행한다.
        self.write_contract(4, 1200, blocking=True)
        failed = self.run_chapter("check", 4, expect=1)
        self.assertEqual(failed["status"], "blocked")
        self.assertEqual(failed["quality"]["status"], "fail")
        self.assertEqual(failed["available_actions"], [])
        self.assertIsNone(failed["compression"])
        blocked = self.run_chapter(
            "commit", 4, document=transaction(4, self.state()["state_revision"]), expect=2
        )
        self.assertIn("blocking quality", blocked["message"])
        self.assertEqual((blocked["status"], blocked["error_code"]), ("error", "QUALITY_BLOCKED"))
        self.assertEqual(self.state()["last_committed_chapter"], 3)
        self.write_contract(4, 1000)
        self.run_chapter("commit", 4, document=transaction(4, self.state()["state_revision"]))

        state = self.state()
        self.assertEqual(state["last_committed_chapter"], 4)
        self.assertEqual(set(state["wordcount_records"]), {"1", "2", "3", "4"})
        self.assertNotIn("wordcount_events", state)
        self.assertNotIn("wordcount_policy", state)

    def test_author_range_from_outline_or_flags_replaces_the_default_band(self) -> None:
        # 목표 1200자에 1080자: 기본 내부 허용 구간 ±12%(1056자부터)에서는 internal_pass지만 작가 지정 범위가 1100-1300이면 분량 미달이다.
        self.write_contract(1, 1080, target=1200, extra="- 字数范围：1100-1300\n")
        checked = self.run_chapter("check", 1)
        self.assertEqual(checked["length"]["status"], "under")
        self.assertEqual(checked["length"]["band_source"], "author")
        self.assertEqual(checked["status"], "needs_decision")
        # 명령행에서 준 범위가 상세 개요보다 우선한다. 작가 범위 안에서 커밋하며 기록에 author_range를 포함하고 state 검증도 통과한다.
        widened = ["--min-chars", "1000", "--max-chars", "1300"]
        self.assertEqual(self.run_chapter("check", 1, extra=widened)["status"], "ready")
        self.run_chapter("commit", 1, document=transaction(1, self.state()["state_revision"]), extra=widened)
        record = self.state()["wordcount_records"]["1"]
        self.assertEqual(record["author_range"], {"min": 1000, "max": 1300})
        self.assertEqual(record["status"], "internal_pass")
        self.run_process([sys.executable, str(TRACKING), "check", "--project", str(self.project)])
        # 분량 초과 시 삭제할 글자 수도 작가 지정 범위로 계산한다.
        self.write_contract(2, 1400, target=1200, extra="- 字数范围：1100-1300\n")
        over = self.run_chapter("check", 2)
        self.assertEqual(over["compression"]["remove_to_user_band"], {"min": 100, "max": 300})
        self.assertEqual(over["compression"]["remove_to_internal_band"], {"min": 100, "max": 300})

    def test_accept_current_length_has_a_floor_and_needs_one_compression_first(self) -> None:
        self.write_contract(1, 289, target=1000)
        refused = self.run_chapter(
            "accept-current-length", 1, document=transaction(1, self.state()["state_revision"]), expect=2
        )
        self.assertEqual((refused["status"], refused["error_code"]), ("error", "BELOW_ACCEPT_FLOOR"))
        self.assertEqual(self.state()["last_committed_chapter"], 0)
        self.run_chapter(
            "accept-current-length", 1, document=transaction(1, self.state()["state_revision"]), extra=["--force"]
        )
        self.assertEqual(self.state()["wordcount_records"]["1"]["actual"], 289)

        self.write_contract(2, 1400)
        refused = self.run_chapter(
            "accept-current-length", 2, document=transaction(2, self.state()["state_revision"]), expect=2
        )
        self.assertEqual(refused["error_code"], "COMPRESSION_REQUIRED")
        self.assertEqual(self.run_chapter("check", 2)["available_actions"][0], "compress-once")
        # 한 글자 삭제는 축약으로 인정하지 않는다. 기준 1400자, 작가 상한 1150자라면 차이 250자의 절반 이상을 삭제해 ≤1275자가 되어야 한다.
        for token_cut in (1399, 1276):
            self.write_contract(2, token_cut)
            refused = self.run_chapter(
                "accept-current-length", 2, document=transaction(2, self.state()["state_revision"]), expect=2
            )
            self.assertEqual(refused["error_code"], "COMPRESSION_REQUIRED", token_cut)
            self.assertIn("1275", refused["message"])
        self.write_contract(2, 1270)  # 실제로 한 번 축약했는데도 초과한다면 이제 현재 분량을 수락할 수 있다.
        accepted = self.run_chapter(
            "accept-current-length", 2, document=transaction(2, self.state()["state_revision"])
        )
        self.assertTrue(accepted["tracking_committed"])
        self.assertEqual(accepted["work_dir_removed"], ".story/work/제002장")

    def test_missing_node_is_a_tool_error_not_a_prose_finding(self) -> None:
        self.write_contract(1, 1000)
        empty_bin = self.root / "empty-bin"
        empty_bin.mkdir()
        env = {**os.environ, "PATH": str(empty_bin)}
        checked = self.run_chapter("check", 1, expect=3, env=env)
        self.assertEqual(checked["status"], "tool_unavailable")
        self.assertEqual(checked["quality"]["status"], "unavailable")
        self.assertEqual(checked["quality"]["blocking_findings"], [])
        self.assertIn("Node.js", checked["quality"]["tool_errors"][0]["message"])
        self.assertEqual(checked["length"]["status"], "internal_pass")
        refused = self.run_chapter(
            "commit", 1, document=transaction(1, self.state()["state_revision"]), expect=3, env=env
        )
        self.assertEqual((refused["schema"], refused["error_code"]), ("story-chapter-error/v1", "TOOL_UNAVAILABLE"))

    def test_findings_pass_through_and_semantic_advisories_are_counted(self) -> None:
        # 대체 검사기 스텁으로 실제 storyctl을 실행한다. finding은 그대로 전달하고 review는 기본적으로 의미 유형별로 센다.
        runtime = self.root / "runtime"
        runtime.mkdir()
        for name in ("storyctl.py", "wordcount_core.py", "tracking_commit.py"):
            shutil.copy2(STORYCTL.parent / name, runtime / name)
        findings = [
            {"type": "voice", "severity": "advisory", "review": "semantic", "line": 1},
            {"type": "space", "severity": "advisory", "review": "mechanical", "line": 2},
            {"type": "legacy", "severity": "advisory", "line": 3},
        ]
        (runtime / "check-ai-patterns.js").write_text(
            f"process.stdout.write(JSON.stringify({{findings: {json.dumps(findings)}}}))\n", encoding="utf-8"
        )
        # 퇴화 검사기의 advisory(개발 용어 유출 의심)는 review를 붙이지 않는다. AI 문체 문제가 아니므로 AI 문체 검토를 유발하는 의미 항목 수에 포함하지 않는다.
        degeneration = [{"type": "meta-leak", "severity": "advisory", "line": 4}]
        (runtime / "check-degeneration.js").write_text(
            f"process.stdout.write(JSON.stringify({{findings: {json.dumps(degeneration)}}}))\n", encoding="utf-8"
        )
        for name in ("normalize-punctuation.js", "check-outline-copy.js"):
            (runtime / name).write_text("process.exit(0)\n", encoding="utf-8")
        self.write_contract(1, 1000)
        checked = self.run_process([
            sys.executable, str(runtime / "storyctl.py"), "chapter", "check",
            "--project", str(self.project), "--chapter", "1",
        ])
        self.assertEqual(
            checked["quality"]["advisories"],
            [{"source": "ai-pattern", **row} for row in findings]
            + [{"source": "degeneration", **row, "review": "mechanical"} for row in degeneration],
        )
        self.assertEqual(checked["quality"]["semantic_advisories"], 2)
        self.assertEqual(checked["status"], "ready")

    def test_revision_goes_through_storyctl_and_remeasures_the_body(self) -> None:
        self.write_contract(1, 1000)
        self.run_chapter("commit", 1, document=transaction(1, self.state()["state_revision"]))
        self.write_contract(1, 950)
        draft = self.run_process([
            sys.executable, str(TRACKING), "draft", "--project", str(self.project), "--chapter", "1",
        ])
        self.assertEqual(draft["mode"], "revision")
        committed = self.run_process([
            sys.executable, str(STORYCTL), "chapter", "commit", "--project", str(self.project),
            "--chapter", "1", "--input", draft["draft"],
        ])
        self.assertEqual(committed["mode"], "revision")
        self.assertEqual(committed["work_dir_removed"], ".story/work/제001장")
        self.assertEqual(self.state()["wordcount_records"]["1"]["actual"], 950)
        self.assertIn("第1章完成。", (self.project / "추적/장별기록/제001장.md").read_text(encoding="utf-8"))

    def test_chapter_work_dir_survives_failure_and_is_removed_after_commit(self) -> None:
        work = self.project / ".story/work/제001장"
        work.mkdir(parents=True)
        memory = self.project / ".story/작가기억"
        memory.mkdir(parents=True)
        (work / "전반.md").write_text("# 前组\n" + "字" * 400, encoding="utf-8")
        (work / "writer_prompt.md").write_text("prompt", encoding="utf-8")
        tracking_input = work / "tracking.json"

        def commit(expect: int) -> dict[str, object]:
            tracking_input.write_text(
                json.dumps(transaction(1, self.state()["state_revision"]), ensure_ascii=False), encoding="utf-8"
            )
            return self.run_process([
                sys.executable, str(STORYCTL), "chapter", "commit", "--project", str(self.project),
                "--chapter", "1", "--input", str(tracking_input),
            ], expect=expect)

        # 거부된 커밋은 모든 임시 파일을 보존해 같은 트랜잭션을 재실행할 수 있게 한다.
        self.write_contract(1, 800)
        rejected = commit(2)
        self.assertIn("outside the user band", rejected["message"])
        self.assertTrue(tracking_input.is_file())
        self.assertTrue((work / "전반.md").is_file())

        self.write_contract(1, 1000)
        committed = commit(0)
        self.assertTrue(committed["tracking_committed"])
        self.assertEqual(committed["work_dir_removed"], ".story/work/제001장")
        self.assertFalse(work.exists())
        self.assertFalse((self.project / ".story/work").exists())
        # 책 수준 작가 기억도 .story/를 공유하며 절대 건드리면 안 된다.
        self.assertTrue(memory.is_dir())
        self.assertEqual(sorted(path.name for path in (self.project / "본문").iterdir()), ["제001장_测试.md"])

        # 다음 장의 작업 디렉터리가 없으면 삭제할 것이 없다고만 보고한다.
        self.write_contract(2, 1000)
        second = self.run_chapter("commit", 2, document=transaction(2, self.state()["state_revision"]))
        self.assertIsNone(second["work_dir_removed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
