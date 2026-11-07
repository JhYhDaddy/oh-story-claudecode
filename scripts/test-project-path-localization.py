#!/usr/bin/env python3
"""한국어 경로와 원본 보존 전환의 독립 회귀 검사."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = load("path_migration", ROOT / "skills/story-setup/scripts/migrate-project-paths.py")
tracking = load("path_tracking", ROOT / "skills/story-long-write/scripts/tracking_commit.py")
core = load("path_wordcount", ROOT / "skills/story-long-write/scripts/wordcount_core.py")


class KoreanPaths(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "original"
        self.dest = self.root / "한국어"
        (self.source / "正文").mkdir(parents=True)
        (self.source / "大纲").mkdir()
        self.body = b"# Original manuscript\r\nExact bytes stay unchanged.\r\n"
        (self.source / "正文/第001章_start.md").write_bytes(self.body)
        (self.source / "大纲/细纲_第001章.md").write_text("outline", encoding="utf-8")
        (self.source / "大纲/卷纲_第一卷.md").write_text("volume", encoding="utf-8")

    def test_architect_work_files_migrate_with_ranges(self):
        work = self.source / ".story/work/排纲"
        work.mkdir(parents=True)
        files = {"核心设定.md": "핵심설정.md", "导入细纲_第001-012章.md": "가져오기상세개요_제001-012장.md",
                 "导入상세개요_제013-024장.md": "가져오기상세개요_제013-024장.md"}
        for name in files:
            (work / name).write_bytes(b"work input\r\n")
        migration.migrate(self.source, self.dest, apply=True)
        for old, new in files.items():
            self.assertEqual((self.dest / ".story/work/개요작성" / new).read_bytes(), b"work input\r\n")
            self.assertEqual((work / old).read_bytes(), b"work input\r\n")

    def test_dry_run_has_no_writes(self):
        result = migration.migrate(self.source, self.dest)
        self.assertFalse(result["applied"])
        self.assertFalse(self.dest.exists())
        self.assertIn({"from": "大纲/卷纲_第一卷.md", "to": "개요/권개요_제1권.md"}, result["renamed"])

    def test_nested_links_change_but_schema_values_do_not(self):
        (self.source / "大纲/links.md").write_text("[volume](卷纲_第一卷.md) [body](../正文/第001章_start.md)", encoding="utf-8")
        (self.source / "state.json").write_text('{"status":"正文"}', encoding="utf-8")
        migration.migrate(self.source, self.dest, apply=True)
        self.assertEqual((self.dest / "개요/links.md").read_text(encoding="utf-8"),
                         "[volume](권개요_제1권.md) [body](../본문/제001장_start.md)")
        self.assertEqual(json.loads((self.dest / "state.json").read_text(encoding="utf-8")), {"status": "正文"})

    def test_raw_manuscript_and_csv_locator(self):
        (self.source / "原文").mkdir()
        raw = "# 원문\r\n[참조](../正文/第001章_start.md)\r\n".encode("utf-8")
        (self.source / "原文/原文.md").write_bytes(raw)
        (self.source / "chapter_index.csv").write_text("chapter,source_locator\n1,原文/原文.md:L1-L2\n", encoding="utf-8")
        migration.migrate(self.source, self.dest, apply=True)
        self.assertEqual((self.dest / "원문/원문.md").read_bytes(), raw)
        self.assertIn("원문/원문.md:L1-L2", (self.dest / "chapter_index.csv").read_text(encoding="utf-8"))

    def test_copy_preserves_body_and_updates_relative_absolute_json_links(self):
        reference = {"schema_version": 4, "relative": "正文/第001章_start.md",
                     "absolute": str(self.source / "正文/第001章_start.md"), "正文": "ordinary text"}
        (self.source / "state.json").write_text(json.dumps(reference), encoding="utf-8")
        (self.source / "README.md").write_text("[chapter](正文/第001章_start.md)", encoding="utf-8")
        migration.migrate(self.source, self.dest, apply=True)
        self.assertEqual((self.dest / "본문/제001장_start.md").read_bytes(), self.body)
        self.assertEqual((self.source / "正文/第001章_start.md").read_bytes(), self.body)
        state = json.loads((self.dest / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["relative"], "본문/제001장_start.md")
        self.assertEqual(Path(state["absolute"]), self.dest / "본문/제001장_start.md")
        self.assertEqual(state["正文"], "ordinary text")
        self.assertIn("(본문/제001장_start.md)", (self.dest / "README.md").read_text(encoding="utf-8"))
        self.assertEqual(core.find_chapter_file(self.dest / "본문", 1, outline=False).name, "제001장_start.md")
        self.assertEqual(core.find_chapter_file(self.dest / "개요", 1, outline=True).name, "상세개요_제001장.md")

    def test_collision_refuses_without_modifying_source_or_destination(self):
        (self.source / "본문").mkdir()
        with self.assertRaisesRegex(ValueError, "충돌"):
            migration.migrate(self.source, self.dest, apply=True)
        self.assertFalse(self.dest.exists())
        self.assertEqual((self.source / "正文/第001章_start.md").read_bytes(), self.body)

    def test_existing_destination_and_nested_destination_refused(self):
        self.dest.mkdir()
        with self.assertRaises(ValueError):
            migration.migrate(self.source, self.dest, apply=True)
        with self.assertRaises(ValueError):
            migration.migrate(self.source, self.source / "nested", apply=True)

    def test_copy_failure_leaves_no_partial_project(self):
        with patch.object(migration.shutil, "copy2", side_effect=OSError("copy failed")):
            with self.assertRaises(OSError):
                migration.migrate(self.source, self.dest, apply=True)
        self.assertFalse(self.dest.exists())
        self.assertEqual(list(self.root.glob(".story-paths-*")), [])

    def test_busy_tracking_project_refused(self):
        (self.source / "追踪").mkdir()
        (self.source / "追踪/.tracking-commit.lock").touch()
        with self.assertRaisesRegex(ValueError, "잠금"):
            migration.migrate(self.source, self.dest, apply=True)

    def test_korean_project_copy_is_idempotent(self):
        migration.migrate(self.source, self.dest, apply=True)
        result = migration.migrate(self.dest, self.root / "second", apply=True)
        self.assertEqual(result["renamed"], [])

    def test_tracking_creation_and_check_use_korean_paths(self):
        seed = {"schema_version": 1, "book_title": "새 작품", "last_chapter": 0,
                "context": {"position": {"volume": "제1권", "volume_start_chapter": 1,
                "story_time": "아침", "scene": "역"}, "long_term_constraints": [],
                "active_character_names": [], "continuity_risks": [], "recent_chapters": [],
                "next_chapter_commitments": []}, "character_snapshots": {}, "foreshadow": [], "timeline_events": []}
        tracking.initialize(self.dest, seed)
        tracking.check_project(self.dest)
        for relative in ["추적/_tracking-state.json", "추적/문맥.md", "추적/복선.md",
                         "추적/시간선/작가용진실.md", "추적/시간선/독자가아는사실.md"]:
            self.assertTrue((self.dest / relative).is_file(), relative)
        self.assertFalse((self.dest / "追踪").exists())
        # 실제 생성된 상태를 이전 파일 배치로 옮긴 뒤 전환해도 파생 뷰 검사를 통과한다.
        legacy = self.root / "legacy-state"
        self.dest.rename(legacy)
        for original, korean in migration.MAP["files"].items():
            for file in list(legacy.rglob(korean)):
                file.rename(file.with_name(original))
        for original, korean in migration.MAP["directories"].items():
            for directory in sorted(legacy.rglob(korean), key=lambda p: len(p.parts), reverse=True):
                if directory.is_dir():
                    directory.rename(directory.with_name(original))
        migration.migrate(legacy, self.dest, apply=True)
        tracking.check_project(self.dest)


if __name__ == "__main__":
    unittest.main()
