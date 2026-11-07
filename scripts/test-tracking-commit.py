#!/usr/bin/env python3
"""단일 기준 원본을 사용하는 추적 상태 도구의 동작 회귀 테스트."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills/story-long-write/scripts/tracking_commit.py"
STORYCTL = ROOT / "skills/story-long-write/scripts/storyctl.py"
STORYCTL_SPEC = importlib.util.spec_from_file_location("storyctl_tracking_tests", STORYCTL)
assert STORYCTL_SPEC and STORYCTL_SPEC.loader
storyctl = importlib.util.module_from_spec(STORYCTL_SPEC)
STORYCTL_SPEC.loader.exec_module(storyctl)


def position(*, volume: str = "第一卷·军宣整顿", start: int = 1) -> dict[str, object]:
    return {
        "volume": volume,
        "volume_start_chapter": start,
        "story_time": "实弹训练两天后",
        "scene": "火箭军文工团高层看片会",
    }


def initial_document(
    *,
    last_chapter: int = 0,
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": 1,
        "book_title": "让你管账号，你高燃混剪炸全网",
        "last_chapter": last_chapter,
        "context": {
            "position": position(),
            "long_term_constraints": ["军方培养江晨的后续安排尚未向读者揭示。"],
            "active_character_names": [],
            "continuity_risks": [],
            "recent_chapters": [
                {"chapter": chapter, "summary": f"第{chapter}章军宣账号继续扩大影响。"}
                for chapter in range(max(1, last_chapter - 2), last_chapter + 1)
            ],
            "next_chapter_commitments": ["推进五天百万粉任务。"] if last_chapter else [],
        },
        "character_snapshots": {},
        "foreshadow": [],
        "timeline_events": [],
    }
    return document


def snapshot(*, state: str = "军内认可继续抬升", items: int = 1, repeat: int = 1) -> dict[str, object]:
    phrases = {
        "abilities_resources": "老兵采访授权与军宣制作资源仍需继续使用",
        "relationships": "与钟嘉嘉及文工团的协作关系影响下一阶段决策",
        "knowledge": "已经确认军宣流程和作品传播结果",
        "open_threads": "尚未回收的培养安排与作品计划仍需推进",
    }
    return {
        "identity": "火箭军文工团宣传兵",
        "location": "火箭军文工团高层看片会",
        "goal": "完成五天百万粉任务",
        "state": state,
        **{
            field: [f"第{index + 1}项：{phrase * repeat}" for index in range(items)]
            for field, phrase in phrases.items()
        },
    }


def transaction(
    chapter: int,
    *,
    mode: str = "append",
    character: bool = False,
    foreshadow: bool = False,
    timeline: bool = False,
    next_commitment: str = "结算百万粉任务并承接老兵主题。",
) -> dict[str, object]:
    character_changes = [{"name": "江晨", "change": "作品价值获军内高层确认"}] if character else []
    foreshadow_changes = (
        [
            {
                "action": "upsert",
                "id": "F027",
                "summary": "专业团队仍拍不出江晨原版的灵魂。",
                "planted_chapter": chapter,
                "planned_resolution_chapter": chapter + 8,
                "status": "已埋",
                "importance": "高",
            }
        ]
        if foreshadow
        else []
    )
    timeline_events = (
        [
            {
                "action": "upsert",
                "id": "E010",
                "story_time": "实弹训练两天后",
                "objective_fact": "军方培养江晨另有尚未公开的后续安排。",
                "reader_knowledge": "读者只知道专业重拍版被否决，不知道后续培养安排。",
                "reveal_status": "未揭示",
                "reveal_chapter": None,
                "characters": ["江晨", "钟嘉嘉"],
            }
        ]
        if timeline
        else []
    )
    return {
        "schema_version": 1,
        "mode": mode,
        "chapter": chapter,
        "chapter_title": f"军宣爆款·{chapter}",
        "delta": {
            "result": f"江晨在第{chapter}章继续扩大军宣作品影响力。",
            "character_changes": character_changes,
            "foreshadow_changes": foreshadow_changes,
            "timeline_events": timeline_events,
            "constraints": [],
            "next_chapter_commitments": [next_commitment],
        },
        "context": {
            "position": position(),
            "long_term_constraints": ["军方培养江晨的后续安排尚未向读者揭示。"],
            "active_character_names": ["江晨"] if character else [],
            "continuity_risks": [],
        },
        "character_snapshots": {"江晨": snapshot()} if character else {},
    }


def load_tool_module():
    spec = importlib.util.spec_from_file_location("tracking_commit_under_test", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TrackingCommitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name) / "让你管账号，你高燃混剪炸全网"
        self.project.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_tool(
        self,
        command: str,
        document: dict[str, object] | None = None,
        *,
        expect: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        args = [sys.executable, str(TOOL), command, "--project", str(self.project)]
        if document is not None:
            document = json.loads(json.dumps(document, ensure_ascii=False))
            if command == "commit" and "expected_state_revision" not in document:
                document["expected_state_revision"] = self.read_state()["state_revision"]
            input_path = Path(self.temporary.name) / f"{command}-{os.urandom(4).hex()}.json"
            input_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            args.extend(["--input", str(input_path)])
        # 도구는 UTF-8 바이트를 직접 쓴다. text=True는 기본적으로 로캘로 디코딩하므로 Windows의 cp1252에서는
        # 중국어 안내를 읽을 때 UnicodeDecodeError가 발생한다. 반드시 UTF-8을 명시한다.
        completed = subprocess.run(
            args, text=True, capture_output=True, check=False, encoding="utf-8"
        )
        self.assertEqual(
            completed.returncode,
            expect,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        return completed

    def init(self, *, last_chapter: int = 0) -> None:
        self.run_tool(
            "init",
            initial_document(last_chapter=last_chapter),
        )

    def write_chapter_contract(self, chapter: int, *, actual: int = 800, target: int = 1000) -> bytes:
        (self.project / "개요").mkdir(exist_ok=True)
        (self.project / "본문").mkdir(exist_ok=True)
        width = max(3, len(str(chapter)))
        (self.project / "개요" / f"상세개요_제{chapter:0{width}d}장.md").write_text(
            f"- 字数目标：{target} 字\n- 字数口径：visible_chars_v1\n",
            encoding="utf-8",
        )
        body = ("# 标题\n" + "字" * actual + "。\n").encode("utf-8")
        (self.project / "본문" / f"제{chapter:0{width}d}장_测试.md").write_bytes(body)
        return body

    def bind_wordcount(
        self,
        document: dict[str, object],
        *,
        resolution: str = "accepted_current_length",
    ) -> dict[str, object]:
        chapter = int(document["chapter"])
        if "expected_state_revision" not in document:
            document["expected_state_revision"] = self.read_state()["state_revision"]
        document["wordcount"] = storyctl.build_project_wordcount_record(
            self.project,
            chapter,
            resolution=resolution,
        )
        return document

    def read_state(self) -> dict[str, object]:
        return json.loads((self.project / "추적/_tracking-state.json").read_text(encoding="utf-8"))

    def test_init_creates_one_structured_authority_and_only_derived_views(self) -> None:
        self.init()
        tracking = self.project / "추적"
        state = self.read_state()

        self.assertEqual(state["schema_version"], 4)
        self.assertEqual(state["state_revision"], 0)
        self.assertEqual(state["characters"], {})
        self.assertEqual(state["foreshadow"], {})
        self.assertEqual(state["timeline"], {})
        self.assertEqual(state["wordcount_records"], {})
        self.assertNotIn("wordcount_policy", state)
        self.assertNotIn("wordcount_events", state)
        self.assertFalse((tracking / "_tracking-meta.json").exists())
        self.assertFalse((tracking / "시간선/사건목록.json").exists())
        self.assertIn("状态修订：0", (tracking / "문맥.md").read_text(encoding="utf-8"))
        self.run_tool("check")

    def test_commit_updates_state_and_all_demo_derived_views(self) -> None:
        self.init()
        self.run_tool("commit", transaction(1, character=True, foreshadow=True, timeline=True))
        tracking = self.project / "추적"
        state = self.read_state()

        self.assertEqual(state["last_committed_chapter"], 1)
        self.assertEqual(state["state_revision"], 1)
        self.assertIn("江晨", state["characters"])
        self.assertIn("F027", state["foreshadow"])
        self.assertIn("E010", state["timeline"])
        self.assertIn("状态修订：1", (tracking / "문맥.md").read_text(encoding="utf-8"))
        self.assertIn("F027｜专业团队仍拍不出江晨原版的灵魂", (tracking / "문맥.md").read_text(encoding="utf-8"))
        self.assertIn("军方培养江晨另有尚未公开的后续安排", (tracking / "시간선/작가용진실.md").read_text(encoding="utf-8"))
        self.assertNotIn("军方培养江晨另有尚未公开的后续安排", (tracking / "시간선/독자가아는사실.md").read_text(encoding="utf-8"))
        self.assertTrue((tracking / "장별기록/제001장.md").exists())
        self.run_tool("check")

    def test_simple_wordcount_record_commits_the_exact_current_body(self) -> None:
        self.init()
        original = self.write_chapter_contract(1, actual=800, target=1000)
        document = self.bind_wordcount(transaction(1))

        self.run_tool("commit", document)

        state = self.read_state()
        self.assertEqual(state["last_committed_chapter"], 1)
        self.assertEqual(state["state_revision"], 1)
        record = state["wordcount_records"]["1"]
        self.assertEqual(
            set(record),
            {"metric", "target", "actual", "status", "resolution", "body_sha256"},
        )
        self.assertEqual(record["status"], "under")
        self.assertEqual(record["resolution"], "accepted_current_length")
        self.assertEqual((self.project / "본문/제001장_测试.md").read_bytes(), original)
        self.run_tool("check")

    def test_body_or_target_change_rejects_a_prepared_record_without_writes(self) -> None:
        self.init()
        original_body = self.write_chapter_contract(1, actual=800, target=1000)
        document = self.bind_wordcount(transaction(1))
        before = self.read_state()

        body_path = self.project / "본문/제001장_测试.md"
        body_path.write_bytes(original_body + "变".encode("utf-8"))
        changed_body = self.run_tool("commit", document, expect=2)
        self.assertIn("wordcount record is stale", changed_body.stderr)
        self.assertEqual(self.read_state(), before)

        body_path.write_bytes(original_body)
        (self.project / "개요/상세개요_제001장.md").write_text(
            "- 字数目标：1100 字\n- 字数口径：visible_chars_v1\n", encoding="utf-8"
        )
        changed_target = self.run_tool("commit", document, expect=2)
        self.assertIn("wordcount record is stale", changed_target.stderr)
        self.assertEqual(self.read_state(), before)

    def test_two_concurrent_different_commits_advance_only_one_revision(self) -> None:
        self.init()
        self.write_chapter_contract(1, actual=800, target=1000)
        first = self.bind_wordcount(transaction(1, next_commitment="A"))
        second = self.bind_wordcount(transaction(1, next_commitment="B"))

        paths = []
        for index, document in enumerate((first, second), start=1):
            path = Path(self.temporary.name) / f"concurrent-{index}.json"
            path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            paths.append(path)
        processes = [
            subprocess.Popen(
                [sys.executable, str(TOOL), "commit", "--project", str(self.project), "--input", str(path)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
            )
            for path in paths
        ]
        results = [process.communicate(timeout=20) + (process.returncode,) for process in processes]

        self.assertEqual(sorted(result[2] for result in results), [0, 2], results)
        state = self.read_state()
        self.assertEqual(state["state_revision"], 1)
        self.assertEqual(set(state["wordcount_records"]), {"1"})
        self.assertEqual(len(list((self.project / "추적/장별기록").glob("제001장.md"))), 1)

    def test_character_snapshot_lists_are_not_limited_to_eight_items(self) -> None:
        self.init()
        document = transaction(1, character=True)
        document["character_snapshots"]["江晨"] = snapshot(items=12)

        completed = self.run_tool("commit", document)

        self.assertNotIn("at most 8 items", completed.stderr)
        self.assertEqual(len(self.read_state()["characters"]["江晨"]["relationships"]), 12)
        self.run_tool("check")

    def test_snapshot_target_warns_and_hard_cap_rejects_before_any_write(self) -> None:
        self.init()
        warning = transaction(1, character=True)
        warning["character_snapshots"]["江晨"] = snapshot(items=12, repeat=2)
        completed = self.run_tool("commit", warning)
        self.assertIn("WARNING: character snapshot 江晨", completed.stderr)
        self.assertEqual(self.read_state()["state_revision"], 1)

        rejected = transaction(2, character=True)
        rejected["character_snapshots"]["江晨"] = snapshot(items=24, repeat=4)
        before = json.loads(json.dumps(self.read_state(), ensure_ascii=False))
        completed = self.run_tool("commit", rejected, expect=2)
        self.assertIn("hard cap of 8192 bytes", completed.stderr)
        self.assertEqual(self.read_state(), before)
        self.assertFalse((self.project / "추적/장별기록/제002장.md").exists())

    def test_missing_active_snapshot_is_rejected_before_any_write(self) -> None:
        self.init()
        document = transaction(1)
        document["context"]["active_character_names"] = ["不存在的核心角色"]
        before = self.read_state()

        result = self.run_tool("commit", document, expect=2)

        self.assertIn("has no current snapshot", result.stderr)
        self.assertEqual(self.read_state(), before)
        self.assertFalse((self.project / "추적/장별기록/제001장.md").exists())

    def test_partial_view_write_keeps_old_authority_and_same_transaction_can_retry(self) -> None:
        self.init()
        module = load_tool_module()
        document = transaction(1, character=True, foreshadow=True, timeline=True)
        document["expected_state_revision"] = 0
        original = module.atomic_write_text

        def fail_on_foreshadow(path: Path, payload: str) -> None:
            if path.name == "복선.md":
                raise OSError("injected derived-view failure")
            original(path, payload)

        module.atomic_write_text = fail_on_foreshadow
        with self.assertRaises(OSError):
            module.apply_transaction(self.project, document)

        self.assertEqual(self.read_state()["state_revision"], 0)
        self.assertIn("状态修订：1", (self.project / "추적/문맥.md").read_text(encoding="utf-8"))
        self.run_tool("check", expect=2)

        module.atomic_write_text = original
        module.apply_transaction(self.project, document)
        self.assertEqual(self.read_state()["state_revision"], 1)
        self.run_tool("check")

    def test_stale_revision_cannot_overwrite_newer_state(self) -> None:
        self.init()
        self.run_tool("commit", transaction(1, foreshadow=True, timeline=True))
        stale = transaction(1, mode="revision", foreshadow=True, timeline=True)
        stale["expected_state_revision"] = 1
        self.run_tool("commit", transaction(2))

        result = self.run_tool("commit", stale, expect=2)

        self.assertIn("tracking state changed", result.stderr)
        self.assertEqual(self.read_state()["last_committed_chapter"], 2)
        self.assertEqual(self.read_state()["state_revision"], 2)

    def test_old_revision_preserves_current_next_chapter_commitment(self) -> None:
        self.init()
        self.run_tool("commit", transaction(1, next_commitment="让专业团队进场重拍。"))
        self.run_tool("commit", transaction(2, next_commitment="等待高层看片结论。"))
        self.run_tool("commit", transaction(3, next_commitment="结算五天百万粉任务。"))
        self.run_tool("commit", transaction(1, mode="revision", next_commitment="修订章当时的旧承诺。"))

        context = (self.project / "추적/문맥.md").read_text(encoding="utf-8")
        self.assertIn("结算五天百万粉任务", context)
        self.assertNotIn("修订章当时的旧承诺", context)

    def test_old_revision_applies_current_rows_without_moving_update_chapter_back(self) -> None:
        self.init()
        self.run_tool("commit", transaction(1, foreshadow=True, timeline=True))
        chapter_two = transaction(2, foreshadow=True, timeline=True)
        chapter_two["delta"]["foreshadow_changes"][0].update(
            planted_chapter=1,
            planned_resolution_chapter=2,
            status="已回收",
            summary="专业版缺少灵魂的判断已经由高层拍板兑现。",
        )
        chapter_two["delta"]["timeline_events"][0]["reader_knowledge"] = "读者已经看到张耀祖采用江晨原版。"
        self.run_tool("commit", chapter_two)

        revision = transaction(1, mode="revision", foreshadow=True, timeline=True)
        revision["delta"]["foreshadow_changes"][0].update(
            planted_chapter=1,
            planned_resolution_chapter=2,
            status="已回收",
            summary="专业版缺少灵魂的判断已经由高层拍板兑现。",
        )
        revision["delta"]["timeline_events"][0]["reader_knowledge"] = "读者已经看到张耀祖采用江晨原版。"
        self.run_tool("commit", revision)

        state = self.read_state()
        self.assertEqual(state["foreshadow"]["F027"]["updated_chapter"], 2)
        self.assertEqual(state["timeline"]["E010"]["updated_chapter"], 2)
        self.run_tool("check")

    def test_imported_cutoff_requires_only_new_daily_records(self) -> None:
        self.init(last_chapter=27)
        self.run_tool("commit", transaction(28, character=True))
        tracking = self.project / "추적"

        self.assertFalse((tracking / "장별기록/제027장.md").exists())
        self.assertTrue((tracking / "장별기록/제028장.md").exists())
        self.assertEqual(self.read_state()["imported_through_chapter"], 27)
        self.run_tool("check")

    def test_imported_chapter_revision_creates_an_overlay_record(self) -> None:
        self.init(last_chapter=20)
        self.run_tool("commit", transaction(10, mode="revision"))
        self.assertTrue((self.project / "추적/장별기록/제010장.md").exists())
        self.assertEqual(self.read_state()["imported_through_chapter"], 20)
        self.run_tool("check")

    def test_check_compares_derived_views_to_state_without_parsing_markdown(self) -> None:
        self.init()
        self.run_tool("commit", transaction(1, character=True, foreshadow=True, timeline=True))
        tracking = self.project / "추적"

        path = tracking / "인물상태/江晨.md"
        path.write_text("# 任意手改格式\n", encoding="utf-8")
        result = self.run_tool("check", expect=2)
        self.assertIn("derived view differs from _tracking-state.json", result.stderr)

        self.run_tool("commit", transaction(2))
        self.run_tool("check")

    def test_check_rejects_orphan_character_file(self) -> None:
        self.init()
        orphan = self.project / "추적/인물상태/CONFLICT.md"
        orphan.write_text("# orphan\n", encoding="utf-8")
        result = self.run_tool("check", expect=2)
        self.assertIn("character snapshot files differ", result.stderr)

    def test_draft_prefills_current_context_so_only_the_delta_is_written(self) -> None:
        self.init()
        (self.project / "개요").mkdir(exist_ok=True)
        (self.project / "개요" / "상세개요_제001장.md").write_text("### 제 1 장：看片会\n", encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(TOOL), "draft", "--project", str(self.project), "--chapter", "1"],
            text=True, capture_output=True, check=False, encoding="utf-8")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        guide = json.loads(completed.stdout)
        draft_path = Path(guide["draft"])
        self.assertEqual(draft_path, self.project / ".story/work/제001장/tracking.json")
        self.assertEqual(guide["mode"], "append")
        self.assertEqual(guide["limits_chars"]["delta.result"], 160)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        self.assertEqual(draft["chapter_title"], "看片会")
        self.assertEqual(draft["expected_state_revision"], self.read_state()["state_revision"])
        self.assertEqual(draft["context"]["long_term_constraints"],
                         self.read_state()["context"]["long_term_constraints"])
        # 새 장의 이야기 시간과 장면은 이전 장에서 가져오지 않고 비워 둔다. 이번 장의 끝을 기준으로 작성하게 하며 이전 값은 별도 참고로 제공한다.
        previous = self.read_state()["context"]["position"]
        self.assertEqual((draft["context"]["position"]["story_time"], draft["context"]["position"]["scene"]), ("", ""))
        self.assertEqual(guide["previous_position"], {"story_time": previous["story_time"], "scene": previous["scene"]})
        self.assertEqual(draft["context"]["position"]["volume"], previous["volume"])
        draft["delta"]["result"] = "江晨在看片会上保住了原版。"
        self.run_tool("commit", draft, expect=2)
        self.assertEqual(self.read_state()["last_committed_chapter"], 0)
        draft["context"]["position"].update({"story_time": "看片会当晚", "scene": "剪辑室"})
        draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
        # draft 재실행은 리비전만 갱신하고 이미 입력한 내용을 지우지 않는다.
        again = subprocess.run(
            [sys.executable, str(TOOL), "draft", "--project", str(self.project), "--chapter", "1"],
            text=True, capture_output=True, check=False, encoding="utf-8")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("그대로 유지했습니다", json.loads(again.stdout)["fill"])
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        self.assertEqual(draft["delta"]["result"], "江晨在看片会上保住了原版。")
        self.run_tool("commit", draft)
        self.assertEqual(self.read_state()["last_committed_chapter"], 1)
        self.assertEqual(self.read_state()["context"]["position"]["scene"], "剪辑室")

    def test_common_model_spellings_commit_on_first_try(self) -> None:
        # 실측(v0.8.1 solo A/B, 10장)에서는 장 번호를 문자열로 쓰거나 planned_chapter를 임의로 만들어 첫 제출이 모두 반려되었다.
        # action을 add로 쓰고 새 작품 스냅샷의 identity를 목록으로 쓴 경우도 있었다. 의미가 명확한 표기는 받아들인 뒤 정식 형식으로 정규화한다.
        self.init()
        document = transaction(1, character=True, foreshadow=True, timeline=True)
        row = document["delta"]["foreshadow_changes"][0]
        row["action"] = "add"
        row["planted_chapter"] = "1"
        row["planned_chapter"] = row.pop("planned_resolution_chapter")
        event = document["delta"]["timeline_events"][0]
        event["action"] = "新增"
        document["character_snapshots"]["江晨"]["identity"] = ["火箭军文工团宣传兵", "军宣爆款创作者"]
        document["character_snapshots"]["江晨"]["relationships"] = "与钟嘉嘉协作"
        self.run_tool("commit", document)
        state = self.read_state()
        self.assertEqual(state["foreshadow"]["F027"]["planted_chapter"], 1)
        self.assertEqual(state["foreshadow"]["F027"]["planned_resolution_chapter"], 9)
        self.assertEqual(state["characters"]["江晨"]["identity"], "火箭军文工团宣传兵；军宣爆款创作者")
        self.assertEqual(state["characters"]["江晨"]["relationships"], ["与钟嘉嘉协作"])

    def test_status_verbs_fill_a_missing_status_and_reject_a_contradicting_one(self) -> None:
        # resolve/回收를 upsert로 매핑할 때 동작어 자체에 ‘회수 완료’ 의도가 있다. status가 없으면 보충하고 충돌하면 반려하며 올바른 표기를 안내한다.
        self.init()
        document = transaction(1, foreshadow=True)
        row = document["delta"]["foreshadow_changes"][0]
        row["action"] = "回收"
        row.pop("status")
        self.run_tool("commit", document)
        self.assertEqual(self.read_state()["foreshadow"]["F027"]["status"], "已回收")

        for verb, status, hint in (("resolve", "已埋", "status=已回收"), ("回收", "已埋", "status=已回收"),
                                   ("advance", "已回收", "status=已埋"), ("推进", "放弃", "status=已埋")):
            document = transaction(2, foreshadow=True)
            document["delta"]["foreshadow_changes"][0].update({"action": verb, "status": status})
            stderr = self.run_tool("commit", document, expect=2).stderr
            self.assertIn(f"action={verb}과(와) status={status}가 모순됩니다", stderr)
            self.assertIn(hint, stderr)
        self.assertEqual(self.read_state()["last_committed_chapter"], 1)

        document = transaction(2, foreshadow=True)
        document["delta"]["foreshadow_changes"][0].update({"action": "推进", "status": "已埋",
                                                           "planted_chapter": "１"})
        self.run_tool("commit", document)
        self.assertEqual(self.read_state()["foreshadow"]["F027"]["status"], "已埋")

    def test_superscript_chapter_is_a_clean_rejection_not_a_traceback(self) -> None:
        self.init()
        document = transaction(1, foreshadow=True)
        document["delta"]["foreshadow_changes"][0]["planted_chapter"] = "²"
        completed = self.run_tool("commit", document, expect=2)
        self.assertIn("planted_chapter must be an integer", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

    def test_rejections_name_the_fix(self) -> None:
        self.init()
        document = transaction(1, foreshadow=True)
        document["delta"]["foreshadow_changes"][0]["payoff_note"] = "看片会后"
        completed = self.run_tool("commit", document, expect=2)
        self.assertIn("contains unsupported fields: payoff_note", completed.stderr)
        self.assertIn("허용 값: action, id, importance, planned_resolution_chapter, planted_chapter, status, summary",
                      completed.stderr)
        document = transaction(1, foreshadow=True)
        document["delta"]["foreshadow_changes"][0]["action"] = "merge"
        self.assertIn("action is invalid: use upsert or delete", self.run_tool("commit", document, expect=2).stderr)
        self.run_tool("commit", transaction(1, character=True))
        document = transaction(2, character=True)
        document["character_snapshots"] = {}
        self.assertIn("current_snapshots", self.run_tool("commit", document, expect=2).stderr)

    def test_draft_shows_entry_shapes_from_the_validator_constants(self) -> None:
        self.init()
        completed = subprocess.run(
            [sys.executable, str(TOOL), "draft", "--project", str(self.project), "--chapter", "1"],
            text=True, capture_output=True, check=False, encoding="utf-8")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        shapes = json.loads(completed.stdout)["shapes"]
        foreshadow = shapes["delta.foreshadow_changes[]"]
        self.assertEqual(foreshadow["planted_chapter"], 1)
        self.assertEqual(foreshadow["status"], "已埋|已回收|已过期|放弃")
        self.assertEqual(set(foreshadow), {"action", "id", "summary", "planted_chapter",
                                           "planned_resolution_chapter", "status", "importance"})
        self.assertEqual(shapes["delta.timeline_events[]"]["reveal_status"], "未揭示|部分揭示|已揭示")
        snapshot_shape = shapes["character_snapshots.{인물명}"]
        self.assertEqual(snapshot_shape["identity"], "한 문장")
        self.assertEqual(snapshot_shape["open_threads"], ["항목당 한 문장"])

    def test_redraft_with_stale_revision_rebuilds_context_and_keeps_filled_parts(self) -> None:
        self.init()
        (self.project / "개요").mkdir(exist_ok=True)
        (self.project / "개요" / "상세개요_제001장.md").write_text("### 제 1 장：看片会\n", encoding="utf-8")
        draft_cmd = [sys.executable, str(TOOL), "draft", "--project", str(self.project), "--chapter", "1"]
        first = subprocess.run(draft_cmd, text=True, capture_output=True, check=False, encoding="utf-8")
        draft_path = Path(json.loads(first.stdout)["draft"])
        state = self.read_state()
        # 만료된 초안: 다른 트랜잭션이 state를 변경하면 이전 초안의 리비전과 context는 모두 오래된 값이다.
        stale = json.loads(draft_path.read_text(encoding="utf-8"))
        stale["expected_state_revision"] = state["state_revision"] + 7
        stale["context"]["position"]["volume"] = "旧卷名"
        stale["delta"]["result"] = "江晨保住了原版。"
        stale["context"]["position"].update({"story_time": "当晚", "scene": "剪辑室"})
        draft_path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")
        again = subprocess.run(draft_cmd, text=True, capture_output=True, check=False, encoding="utf-8")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("현재 상태로 context를 재구성", json.loads(again.stdout)["fill"])
        rebuilt = json.loads(draft_path.read_text(encoding="utf-8"))
        self.assertEqual(rebuilt["expected_state_revision"], state["state_revision"])
        self.assertEqual(rebuilt["context"]["position"]["volume"], state["context"]["position"]["volume"])
        self.assertEqual(rebuilt["delta"]["result"], "江晨保住了原版。")
        self.assertEqual((rebuilt["context"]["position"]["story_time"], rebuilt["context"]["position"]["scene"]),
                         ("当晚", "剪辑室"))
        self.run_tool("commit", rebuilt)
        self.assertEqual(self.read_state()["last_committed_chapter"], 1)

    def test_redraft_merge_keeps_the_drafts_own_additions_and_retirements(self) -> None:
        self.init()
        (self.project / "개요").mkdir(exist_ok=True)
        (self.project / "개요" / "상세개요_제001장.md").write_text("### 제 1 장：看片会\n", encoding="utf-8")
        draft_cmd = [sys.executable, str(TOOL), "draft", "--project", str(self.project), "--chapter", "1"]
        first = subprocess.run(draft_cmd, text=True, capture_output=True, check=False, encoding="utf-8")
        draft_path = Path(json.loads(first.stdout)["draft"])
        state = self.read_state()
        old = state["context"]["long_term_constraints"][0]
        stale = json.loads(draft_path.read_text(encoding="utf-8"))
        stale["expected_state_revision"] = state["state_revision"] + 7
        stale["context"]["long_term_constraints"] = ["本章新立的约束。"]  # 이전 항목을 삭제하고 새 항목을 추가한다.
        stale["delta"]["retired_context_items"] = [old]
        stale["delta"]["result"] = "江晨保住了原版。"
        stale["context"]["position"].update({"story_time": "当晚", "scene": "剪辑室", "volume": "旧卷名"})
        draft_path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")
        again = subprocess.run(draft_cmd, text=True, capture_output=True, check=False, encoding="utf-8")
        guide = json.loads(again.stdout)
        self.assertIn("권 정보가 달라 현재 상태를 적용했습니다", guide["fill"])
        rebuilt = json.loads(draft_path.read_text(encoding="utf-8"))
        # 이번 장의 새 항목은 남기고 퇴역한 항목은 되살리지 않는다.
        self.assertEqual(rebuilt["context"]["long_term_constraints"], ["本章新立的约束。"])
        self.run_tool("commit", rebuilt)
        self.assertEqual(self.read_state()["context"]["long_term_constraints"], ["本章新立的约束。"])

    def test_redraft_revision_and_names_are_not_merged_back_silently(self) -> None:
        self.init()
        self.run_tool("commit", transaction(1))
        # 수정 초안: 중간에 새 장이 추가되고 항목이 퇴역할 수 있으므로 이전 초안에만 남은 항목을 자동 복원하지 않는다.
        draft_cmd = [sys.executable, str(TOOL), "draft", "--project", str(self.project), "--chapter", "1"]
        first = subprocess.run(draft_cmd, text=True, capture_output=True, check=False, encoding="utf-8")
        self.assertEqual(json.loads(first.stdout)["mode"], "revision")
        draft_path = Path(json.loads(first.stdout)["draft"])
        state = self.read_state()
        stale = json.loads(draft_path.read_text(encoding="utf-8"))
        stale["expected_state_revision"] = state["state_revision"] + 7
        stale["context"]["long_term_constraints"].append("已被后续章节退役的条目。")
        stale["context"]["active_character_names"].append("路人乙")
        stale["character_snapshots"] = {"路人乙": {"name": "路人乙"}}  # 이후 장에서 퇴역한 인물의 이전 스냅샷.
        draft_path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")
        again = subprocess.run(draft_cmd, text=True, capture_output=True, check=False, encoding="utf-8")
        fill = json.loads(again.stdout)["fill"]
        rebuilt = json.loads(draft_path.read_text(encoding="utf-8"))
        self.assertEqual(rebuilt["context"]["long_term_constraints"], state["context"]["long_term_constraints"])
        self.assertNotIn("路人乙", rebuilt["context"]["active_character_names"])
        self.assertIn("자동 복원하지 않았습니다", fill)
        self.assertIn("已被后续章节退役的条目。", fill)
        self.assertIn("등장 인물 路人乙", fill)
        self.assertIn("인물 스냅샷 路人乙", fill)
        self.assertEqual(rebuilt["character_snapshots"], {})

    def draft(self, chapter: int) -> tuple[dict[str, object], Path]:
        completed = subprocess.run(
            [sys.executable, str(TOOL), "draft", "--project", str(self.project), "--chapter", str(chapter)],
            text=True, capture_output=True, check=False, encoding="utf-8")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        guide = json.loads(completed.stdout)
        return guide, Path(guide["draft"])

    def test_revision_draft_keeps_commitments_that_contain_the_separator(self) -> None:
        # 약속 원문에 ‘；’가 포함된 경우: 최신 장이 아닌 장의 수정 초안은 장별 기록에서 약속을 읽으며 한 항목을 둘로 나누면 안 된다.
        self.init()
        commitment = "江晨答应交片；但只交原版，不交删改版。"
        self.run_tool("commit", transaction(1, next_commitment=commitment))
        self.run_tool("commit", transaction(2))
        _, draft_path = self.draft(1)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        self.assertEqual(draft["delta"]["next_chapter_commitments"], [commitment])
        # 미리 채운 값으로 제출하고 다시 읽어도 같은 한 항목이어야 한다. 렌더링과 다시 읽기는 서로 역연산이다.
        self.run_tool("commit", draft)
        (self.project / ".story/work/제001장/tracking.json").unlink()
        _, draft_path = self.draft(1)
        again = json.loads(draft_path.read_text(encoding="utf-8"))
        self.assertEqual(again["delta"]["next_chapter_commitments"], [commitment])

    def test_revision_draft_without_a_record_does_not_claim_it_prefilled(self) -> None:
        self.init()
        self.run_tool("commit", transaction(1))
        self.run_tool("commit", transaction(2))
        (self.project / "추적/장별기록/제001장.md").unlink()
        guide, _ = self.draft(1)
        self.assertEqual(guide["mode"], "revision")
        self.assertNotIn("기존 장별 기록으로 미리 채웠습니다", guide["fill"])
        self.assertIn("장별 기록이 없거나", guide["fill"])

    def test_revision_draft_prefills_the_committed_record_so_nothing_is_wiped(self) -> None:
        self.init()
        first = transaction(1, character=True, foreshadow=True, timeline=True)
        first["delta"]["constraints"] = ["原版视频不能再被替换。"]
        self.run_tool("commit", first)
        self.run_tool("commit", transaction(2, character=True))
        record_path = self.project / "추적/장별기록/제001장.md"
        before = record_path.read_text(encoding="utf-8")

        guide, draft_path = self.draft(1)
        self.assertEqual(guide["mode"], "revision")
        # 수정 delta는 변경 부분만 입력하는 것이 아니라 수정 후 해당 장의 전체 기록이다.
        self.assertNotIn("只填 delta 里本章的变化", guide["fill"])
        self.assertIn("전체 기록", guide["fill"])
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        delta = draft["delta"]
        self.assertEqual(delta["result"], first["delta"]["result"])
        self.assertEqual(delta["character_changes"], first["delta"]["character_changes"])
        self.assertEqual([item["id"] for item in delta["foreshadow_changes"]], ["F027"])
        self.assertEqual([item["id"] for item in delta["timeline_events"]], ["E010"])
        self.assertEqual(delta["constraints"], ["原版视频不能再被替换。"])
        self.assertEqual(delta["next_chapter_commitments"], first["delta"]["next_chapter_commitments"])
        self.assertIn("江晨", draft["character_snapshots"])

        # 실제 수정한 한 항목만 바꾸고 나머지는 미리 채운 값으로 제출한다. 장별 기록은 결과 외에는 그대로이며 check를 통과한다.
        delta["result"] = "江晨在看片会上保住原版，并当场剪出新预告。"
        self.run_tool("commit", draft)
        after = record_path.read_text(encoding="utf-8")
        self.assertEqual(after, before.replace(first["delta"]["result"], delta["result"]))
        self.run_tool("check")

    def test_revision_keeps_the_chapter_retirement_log(self) -> None:
        self.init()
        constraint = "军方培养江晨的后续安排尚未向读者揭示。"
        declared = transaction(1)
        declared["context"]["long_term_constraints"] = []
        declared["delta"]["retired_context_items"] = [constraint]
        self.run_tool("commit", declared)
        _, draft_path = self.draft(1)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        self.run_tool("commit", draft)
        record = (self.project / "추적/장별기록/제001장.md").read_text(encoding="utf-8")
        self.assertIn("## 本章退役登记", record)
        self.assertIn(constraint, record)
        self.run_tool("check")

    def test_revision_without_remeasuring_a_changed_body_is_rejected(self) -> None:
        self.init()
        body = self.write_chapter_contract(1, actual=1000, target=1000)
        self.run_tool("commit", self.bind_wordcount(transaction(1), resolution="within_user_band"))
        (self.project / "본문/제001장_测试.md").write_bytes(body.replace("字".encode("utf-8"), "改".encode("utf-8"), 50))
        before = self.read_state()
        result = self.run_tool("commit", transaction(1, mode="revision"), expect=2)
        self.assertIn("storyctl.py chapter commit", result.stderr)
        self.assertEqual(self.read_state(), before)
        # 오류는 변경된 항목을 명시하고 storyctl이 포함된 집필 스킬을 안내한다. story-review / story-import에는 storyctl이 없다.
        self.assertIn("제1장의 본문이(가) 변경되었습니다", result.stderr)
        self.assertIn("story-long-write의 storyctl.py chapter commit", result.stderr)
        # 본문을 건드리지 않는 추적 정보만의 수정(예: 파생 뷰 수정)도 정상적으로 제출할 수 있다.
        (self.project / "본문/제001장_测试.md").write_bytes(body)
        self.run_tool("commit", transaction(1, mode="revision"))
        # 글자 수 목표만 바뀌면 목표가 바뀌었다고 알리고 본문이 바뀌었다고 잘못 알리지 않는다.
        outline = self.project / "개요/상세개요_제001장.md"
        original_outline = outline.read_text(encoding="utf-8")
        outline.write_text(original_outline.replace("1000 字", "1200 字"), encoding="utf-8")
        result = self.run_tool("commit", transaction(1, mode="revision"), expect=2)
        self.assertIn("제1장의 목표 분량이(가) 변경되었습니다", result.stderr)
        self.assertNotIn("正文已改", result.stderr)

    def test_tracking_only_revision_survives_a_later_author_range_line(self) -> None:
        # 제출 시 상세 개요에 ‘字数范围’가 없어 author_range가 기록되지 않았고, 작가가 나중에 범위를 추가했다. 본문과 목표가 그대로라면
        # 추적 정보만의 수정을 본문이나 글자 수 목표가 바뀌었다는 이유로 거부하면 안 된다.
        self.init()
        self.write_chapter_contract(1, actual=1000, target=1000)
        self.run_tool("commit", self.bind_wordcount(transaction(1), resolution="within_user_band"))
        outline = self.project / "개요/상세개요_제001장.md"
        outline.write_text(outline.read_text(encoding="utf-8") + "- 字数范围：1500-2000 字\n", encoding="utf-8")
        self.run_tool("commit", transaction(1, mode="revision"))
        self.run_tool("check")

    def test_tracking_only_revision_survives_a_non_numeric_target_note(self) -> None:
        # 이전 상세 개요에서 숫자 목표 옆에 ‘字数目标：按卷规划’ 같은 설명 행을 둔 경우, 숫자 없는 행은 설명문으로 취급한다.
        # 이미 제출한 장의 추적 정보만 수정할 때도 정상 대조하여 통과한다. 두 숫자 값이 충돌하면 여전히 거부한다.
        self.init()
        self.write_chapter_contract(1, actual=1000, target=1000)
        self.run_tool("commit", self.bind_wordcount(transaction(1), resolution="within_user_band"))
        outline = self.project / "개요/상세개요_제001장.md"
        original = outline.read_text(encoding="utf-8")
        outline.write_text(original + "- 字数目标：按卷规划\n", encoding="utf-8")
        self.run_tool("commit", transaction(1, mode="revision"))
        outline.write_text(original + "- 字数目标：1200 字\n", encoding="utf-8")
        result = self.run_tool("commit", transaction(1, mode="revision"), expect=2)
        self.assertIn("분량 기록을 대조할 수 없습니다", result.stderr)

    def test_retired_item_still_in_context_is_rejected(self) -> None:
        self.init()
        document = transaction(1)
        document["delta"]["retired_context_items"] = list(document["context"]["long_term_constraints"])
        result = self.run_tool("commit", document, expect=2)
        self.assertIn("lists items that are still in context", result.stderr)

    def test_all_over_length_fields_are_reported_at_once_in_characters(self) -> None:
        self.init()
        document = transaction(1, foreshadow=True)
        document["delta"]["result"] = "江晨" * 100
        document["delta"]["foreshadow_changes"][0]["summary"] = "老兵" * 70
        result = self.run_tool("commit", document, expect=2)
        self.assertIn("2개 필드가 길이 한도를 초과했습니다", result.stderr)
        self.assertIn("delta.result exceeds 480 bytes(현재 200자, 상한 약 160자, 최소 40자 삭제 필요)", result.stderr)
        self.assertIn("summary exceeds 360 bytes(현재 140자, 상한 약 120자, 최소 20자 삭제 필요)", result.stderr)
        self.assertEqual(self.read_state()["last_committed_chapter"], 0)

    def test_unknown_fields_are_rejected(self) -> None:
        invalid_init = initial_document()
        invalid_init["baseline"] = {}
        self.run_tool("init", invalid_init, expect=2)

        self.init()
        state = self.read_state()
        state["status"] = "clean"
        (self.project / "추적/_tracking-state.json").write_text(
            json.dumps(state, ensure_ascii=False), encoding="utf-8"
        )
        result = self.run_tool("check", expect=2)
        self.assertIn("unsupported fields", result.stderr)

    def test_init_archives_a_pre_transaction_tracking_directory(self) -> None:
        tracking = self.project / "추적"
        tracking.mkdir()
        (tracking / "인물상태.md").write_text("# 旧角色状态\n", encoding="utf-8")
        (tracking / "시간선.md").write_text("# 旧时间线\n", encoding="utf-8")
        (tracking / "_tracking-meta.json").write_text("{}\n", encoding="utf-8")

        result = self.run_tool("init", initial_document())
        self.assertIn("_이전추적보관", result.stderr)
        archive = tracking / "_이전추적보관"
        self.assertEqual((archive / "인물상태.md").read_text(encoding="utf-8"), "# 旧角色状态\n")
        self.assertEqual((archive / "시간선.md").read_text(encoding="utf-8"), "# 旧时间线\n")
        self.assertFalse((tracking / "인물상태.md").exists())
        self.assertTrue((tracking / "인물상태").is_dir())
        self.run_tool("check")

    def test_failed_init_leaves_the_old_tracking_directory_untouched(self) -> None:
        tracking = self.project / "추적"
        tracking.mkdir()
        (tracking / "인물상태.md").write_text("# 旧角色状态\n", encoding="utf-8")
        invalid = initial_document()
        invalid["baseline"] = {}

        self.run_tool("init", invalid, expect=2)
        self.assertTrue((tracking / "인물상태.md").exists())
        self.assertFalse((tracking / "_이전추적보관").exists())

    def test_commit_and_check_still_refuse_a_retired_layout(self) -> None:
        self.init()
        (self.project / "추적/시간선.md").write_text("# 旧时间线\n", encoding="utf-8")
        result = self.run_tool("check", expect=2)
        self.assertIn("retired tracking files", result.stderr)
        result = self.run_tool("commit", transaction(1), expect=2)
        self.assertIn("retired tracking files", result.stderr)

    def test_dropping_a_context_item_without_declaring_it_is_rejected(self) -> None:
        self.init()
        silent = transaction(1)
        silent["context"]["long_term_constraints"] = []
        result = self.run_tool("commit", silent, expect=2)
        self.assertIn("retired_context_items", result.stderr)
        self.assertEqual(self.read_state()["state_revision"], 0)
        self.assertFalse((self.project / "추적/장별기록/제001장.md").exists())

    def test_declared_context_retirement_is_recorded_in_the_chapter_delta(self) -> None:
        self.init()
        declared = transaction(1)
        constraint = "军方培养江晨的后续安排尚未向读者揭示。"
        declared["context"]["long_term_constraints"] = []
        declared["delta"]["retired_context_items"] = [constraint]
        self.run_tool("commit", declared)

        self.assertEqual(self.read_state()["context"]["long_term_constraints"], [])
        delta_text = (self.project / "추적/장별기록/제001장.md").read_text(encoding="utf-8")
        self.assertIn("## 本章退役登记", delta_text)
        self.assertIn(constraint, delta_text)
        self.run_tool("check")

    def test_retiring_a_core_character_removes_its_derived_view(self) -> None:
        self.init()
        self.run_tool("commit", transaction(1, character=True))
        self.assertTrue((self.project / "추적/인물상태/江晨.md").exists())

        retire = transaction(2)
        retire["delta"]["retired_characters"] = ["江晨"]
        self.run_tool("commit", retire)

        self.assertNotIn("江晨", self.read_state()["characters"])
        self.assertFalse((self.project / "추적/인물상태/江晨.md").exists())
        self.assertIn("角色状态：江晨", (self.project / "추적/장별기록/제002장.md").read_text(encoding="utf-8"))
        self.run_tool("check")

    def test_an_interrupted_archive_can_be_resumed(self) -> None:
        tracking = self.project / "추적"
        (tracking / "_이전추적보관").mkdir(parents=True)
        (tracking / "인물상태.md").write_text("# 未搬完\n", encoding="utf-8")
        (tracking / "_이전추적보관/시간선.md").write_text("# 上次已搬\n", encoding="utf-8")

        self.run_tool("init", initial_document())
        archive = tracking / "_이전추적보관"
        self.assertEqual((archive / "인물상태.md").read_text(encoding="utf-8"), "# 未搬完\n")
        self.assertEqual((archive / "시간선.md").read_text(encoding="utf-8"), "# 上次已搬\n")
        self.run_tool("check")

    def test_archive_never_clobbers_an_already_archived_file(self) -> None:
        tracking = self.project / "추적"
        (tracking / "_이전추적보관").mkdir(parents=True)
        (tracking / "인물상태.md").write_text("现役\n", encoding="utf-8")
        (tracking / "_이전추적보관/인물상태.md").write_text("存档\n", encoding="utf-8")

        result = self.run_tool("init", initial_document(), expect=2)
        self.assertIn("already exists", result.stderr)
        self.assertEqual((tracking / "인물상태.md").read_text(encoding="utf-8"), "现役\n")
        self.assertEqual((tracking / "_이전추적보관/인물상태.md").read_text(encoding="utf-8"), "存档\n")

    def test_a_character_can_die_and_retire_in_one_transaction(self) -> None:
        self.init()
        self.run_tool("commit", transaction(1, character=True))
        farewell = transaction(2)
        farewell["delta"]["character_changes"] = [{"name": "江晨", "change": "在最终一战中阵亡，彻底退场"}]
        farewell["delta"]["retired_characters"] = ["江晨"]
        self.run_tool("commit", farewell)

        record = (self.project / "추적/장별기록/제002장.md").read_text(encoding="utf-8")
        self.assertIn("江晨｜核心｜在最终一战中阵亡，彻底退场", record)
        self.assertIn("角色状态：江晨", record)
        self.assertNotIn("江晨", self.read_state()["characters"])
        self.run_tool("check")

    def test_retirement_is_rejected_in_a_revision(self) -> None:
        self.init(last_chapter=20)
        retire = transaction(10, mode="revision")
        retire["delta"]["retired_characters"] = ["江晨"]
        result = self.run_tool("commit", retire, expect=2)
        self.assertIn("append transaction", result.stderr)

        drop = transaction(10, mode="revision")
        drop["context"]["long_term_constraints"] = []
        drop["delta"]["retired_context_items"] = ["军方培养江晨的后续安排尚未向读者揭示。"]
        result = self.run_tool("commit", drop, expect=2)
        self.assertIn("append transaction", result.stderr)
        self.assertEqual(self.read_state()["state_revision"], 0)

    def test_retiring_a_still_active_character_is_rejected(self) -> None:
        self.init()
        self.run_tool("commit", transaction(1, character=True))
        still_listed = transaction(2)
        still_listed["delta"]["retired_characters"] = ["江晨"]
        still_listed["context"]["active_character_names"] = ["江晨"]
        result = self.run_tool("commit", still_listed, expect=2)
        self.assertIn("retired character 江晨 is still listed in context.active_character_names", result.stderr)
        self.assertEqual(self.read_state()["state_revision"], 1)

    def test_retiring_and_updating_a_character_in_one_transaction_is_rejected(self) -> None:
        self.init()
        self.run_tool("commit", transaction(1, character=True))
        updated = transaction(2, character=True)
        updated["delta"]["retired_characters"] = ["江晨"]
        updated["context"]["active_character_names"] = []
        result = self.run_tool("commit", updated, expect=2)
        self.assertIn("character 江晨 cannot be retired and updated in the same transaction", result.stderr)
        self.assertEqual(self.read_state()["state_revision"], 1)

    def test_windows_reserved_character_name_is_rejected(self) -> None:
        self.init()
        invalid = transaction(1, character=True)
        invalid["delta"]["character_changes"][0]["name"] = "CON"
        invalid["context"]["active_character_names"] = ["CON"]
        invalid["character_snapshots"] = {"CON": invalid["character_snapshots"]["江晨"]}
        result = self.run_tool("commit", invalid, expect=2)
        self.assertIn("is reserved on Windows", result.stderr)
        self.assertEqual(self.read_state()["state_revision"], 0)

    def cast_document(self, count: int, *, long_fields: bool = False) -> dict[str, object]:
        document = initial_document()
        names = [f"女主{index:02d}" for index in range(1, count + 1)]
        document["context"]["active_character_names"] = names
        for name in names:
            entry = snapshot()
            if long_fields:
                entry.update(identity="身" * 80, state="状" * 100, goal="目" * 100)
            document["character_snapshots"][name] = entry
        return document

    def test_twenty_active_characters_pass_and_the_twenty_first_is_rejected_before_any_write(self) -> None:
        result = self.run_tool("init", self.cast_document(21), expect=2)
        self.assertIn("at most 20 names", result.stderr)
        # 잠금을 만들 때 생성한 빈 추적/ 디렉터리만 남길 수 있다.
        self.assertFalse((self.project / "추적/_tracking-state.json").exists())
        self.assertFalse((self.project / "추적/문맥.md").exists())
        self.assertFalse((self.project / "추적/인물상태").exists())

        self.run_tool("init", self.cast_document(20))
        context = (self.project / "추적/문맥.md").read_text(encoding="utf-8")
        self.assertIn("女主20｜", context)
        self.run_tool("check")

        overflow = transaction(1, character=True)
        overflow["context"]["active_character_names"] = self.read_state()["context"]["active_character_names"] + ["江晨"]
        before = self.read_state()
        result = self.run_tool("commit", overflow, expect=2)
        self.assertIn("at most 20 names", result.stderr)
        self.assertEqual(self.read_state(), before)
        self.assertFalse((self.project / "추적/장별기록/제001장.md").exists())

    def test_existing_state_with_six_to_twenty_active_characters_still_checks_drafts_and_commits(self) -> None:
        # 이전 버전은 6명만 허용했다. 작가가 스크립트의 state를 7–20명으로 수정했어도 업그레이드 후 check / draft / commit이 정상 동작해야 한다.
        for count in (6, 7, 20):
            with self.subTest(count=count):
                self.project = Path(self.temporary.name) / f"群像{count}"
                self.project.mkdir()
                self.run_tool("init", self.cast_document(count))
                self.run_tool("check")
                (self.project / "개요").mkdir()
                (self.project / "개요" / "상세개요_제001장.md").write_text("### 제 1 장：家宴\n", encoding="utf-8")
                drafted = subprocess.run(
                    [sys.executable, str(TOOL), "draft", "--project", str(self.project), "--chapter", "1"],
                    text=True, capture_output=True, check=False, encoding="utf-8")
                self.assertEqual(drafted.returncode, 0, drafted.stderr)
                draft_path = Path(json.loads(drafted.stdout)["draft"])
                draft = json.loads(draft_path.read_text(encoding="utf-8"))
                self.assertEqual(len(draft["context"]["active_character_names"]), count)
                draft["delta"]["result"] = "众人在家宴上各怀心思。"
                draft["context"]["position"].update({"story_time": "家宴当晚", "scene": "正厅"})
                self.run_tool("commit", draft)
                state = self.read_state()
                self.assertEqual(state["last_committed_chapter"], 1)
                self.assertEqual(len(state["context"]["active_character_names"]), count)
                self.run_tool("check")

    def test_hot_context_byte_cap_still_rejects_a_full_cast_before_any_write(self) -> None:
        result = self.run_tool("init", self.cast_document(20, long_fields=True), expect=2)
        self.assertIn("hot context exceeds 12288 bytes", result.stderr)
        self.assertFalse((self.project / "추적/_tracking-state.json").exists())
        self.assertFalse((self.project / "추적/문맥.md").exists())
        self.assertFalse((self.project / "추적/인물상태").exists())

        self.run_tool("init", self.cast_document(20))
        grown = transaction(1)
        names = self.read_state()["context"]["active_character_names"]
        grown["context"]["active_character_names"] = names
        grown["delta"]["character_changes"] = [{"name": name, "change": "心思写满"} for name in names]
        grown["character_snapshots"] = {
            name: {**snapshot(), "identity": "身" * 80, "state": "状" * 100, "goal": "目" * 100} for name in names
        }
        before = self.read_state()
        context_before = (self.project / "추적/문맥.md").read_bytes()
        result = self.run_tool("commit", grown, expect=2)
        self.assertIn("hot context exceeds 12288 bytes", result.stderr)
        self.assertEqual(self.read_state(), before)
        self.assertEqual((self.project / "추적/문맥.md").read_bytes(), context_before)
        self.assertFalse((self.project / "추적/장별기록/제001장.md").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
