"""국내 기본 분기와 초안 검사, 기존 중국 출력 호환성 회귀 검사."""
import importlib.util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("publish", ROOT / "skills/story-publish/scripts/check-publish-format.py")
publish = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish)


class KoreanPlatforms(unittest.TestCase):
    def draft(self):
        text = (ROOT / "skills/story-publish/references/korean-platforms.md").read_text(encoding="utf-8")
        return re.search(r"```markdown\n(.*?)\n```", text, re.S)[1]

    def test_all_platforms_accept_drafts_with_explicit_limitations(self):
        for platform in publish.KOREAN_PLATFORMS:
            with self.subTest(platform=platform):
                errors, warnings = publish.check(self.draft().replace("플랫폼: 문피아", "플랫폼: " + platform))
                self.assertEqual(errors, [])
                self.assertTrue(any("미검증" in w for w in warnings))

    def test_no_fanqie_title_limit_for_korean_draft(self):
        draft = self.draft().replace("- 제목 [제안]:", "- 제목 [제안]: 회귀한 마법사는 오늘도 평화로운 일상을 꿈꾼다")
        errors, warnings = publish.check(draft)
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)

    def test_reject_false_completion_and_unknown_platform(self):
        for before, after in [("자료 초안", "게시 완료"), ("플랫폼: 문피아", "플랫폼: 알수없음"),
                              ("ko-draft-v1", "ko-draft-v2"), ("목적: 직접 연재", "목적: 자동 게시")]:
            with self.subTest(after=after):
                self.assertTrue(publish.check(self.draft().replace(before, after))[0])

    def test_missing_scope_and_source_rejected(self):
        for section in ["플랫폼 확인 필요", "출처"]:
            pattern = r"(## " + section + r"\n).*?(?=\n## |\Z)"
            draft = re.sub(pattern, r"\1없음\n", self.draft(), flags=re.S)
            self.assertTrue(publish.check(draft)[0])

    def test_legacy_fanqie_still_uses_platform_rules(self):
        self.assertEqual(publish.load_spec("番茄小说", "长篇")["title"]["max"], 15)
        self.assertTrue(publish.title_warnings("has spaces", {"max": 15}))

    def test_manual_scan_does_not_feed_chinese_parser(self):
        for kind in ["long", "short"]:
            text = (ROOT / f"skills/story-{kind}-scan/references/korean-platforms.md").read_text(encoding="utf-8")
            self.assertIn("중국어 형식 전용 `aggregate-rank.js`에 넣지 않는다", text)
            self.assertIn("자동 수집기와 API 연동은 미검증", text)

    def test_unspecified_short_review_is_generic(self):
        text = (ROOT / "skills/story-review/SKILL.md").read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if line.startswith("     | 단편 | 즈후"))
        self.assertNotIn("미정", row)
        self.assertIn("미기재는 장단편 모두 `generic`", text)


if __name__ == "__main__":
    unittest.main()
