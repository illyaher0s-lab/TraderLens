"""
API-free checks for Signal Board UX polish guardrails.

These tests protect user-facing copy and styling boundaries that are easy to
regress during frontend edits.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SIGNALS_PAGE = ROOT / "frontend" / "app" / "signals" / "page.tsx"
GLOBALS_CSS = ROOT / "frontend" / "app" / "globals.css"


class TestSignalBoardUxPolish(unittest.TestCase):
    def test_signal_list_has_no_debug_version_marker(self):
        source = SIGNALS_PAGE.read_text(encoding="utf-8")

        self.assertNotIn("UI_VERSION_SIGNAL_BOARD", source)

    def test_globals_css_has_no_test_background_override(self):
        source = GLOBALS_CSS.read_text(encoding="utf-8")

        self.assertNotIn("Test: If this changes background", source)
        self.assertNotIn("background: #f3f4f6 !important", source)

    def test_signal_list_avoids_prohibited_visible_copy(self):
        source = SIGNALS_PAGE.read_text(encoding="utf-8")
        prohibited_terms = ["买入", "卖出", "推荐", "建议操作", "最佳策略", "策略排名"]

        for term in prohibited_terms:
            with self.subTest(term=term):
                self.assertNotIn(term, source)


if __name__ == "__main__":
    unittest.main()
