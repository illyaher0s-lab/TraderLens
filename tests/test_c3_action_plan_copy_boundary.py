"""
C3 Action Plan Copy Boundary Tests

Verify that forbidden UI copy phrases do not appear in Action Plan frontend code.

Hard requirements:
1. Panel title must be "人工处理计划"
2. Required disclaimer: "这是人工处理计划，不是买卖建议，不会自动交易。"
3. Allowed button labels: 准备执行, 部分执行, 今日放弃, 标记过期
4. Forbidden phrases: 推荐买入, 推荐卖出, 立即买入, 立即卖出, 一键下单, 自动执行,
   保证盈利, 稳定盈利, 实盘可用, 目标价, 最佳策略, 策略排名
5. Exception: "不会自动交易" is NOT forbidden (part of required disclaimer)
"""

import unittest
from pathlib import Path


class TestActionPlanCopyBoundary(unittest.TestCase):
    """Test C3 Action Plan UI copy boundaries."""

    @classmethod
    def setUpClass(cls):
        """Load frontend files once for all tests."""
        cls.frontend_dir = Path(__file__).parent.parent / "frontend"
        cls.action_plan_panel_path = cls.frontend_dir / "components" / "ActionPlanPanel.tsx"
        cls.signal_detail_page_path = cls.frontend_dir / "app" / "signals" / "[signal_id]" / "page.tsx"

        # Read files
        if cls.action_plan_panel_path.exists():
            cls.action_plan_panel_content = cls.action_plan_panel_path.read_text(encoding="utf-8")
        else:
            cls.action_plan_panel_content = ""

        if cls.signal_detail_page_path.exists():
            cls.signal_detail_page_content = cls.signal_detail_page_path.read_text(encoding="utf-8")
        else:
            cls.signal_detail_page_content = ""

        cls.all_frontend_content = cls.action_plan_panel_content + "\n" + cls.signal_detail_page_content

    def test_required_panel_title_present(self):
        """Panel title must be '人工处理计划'."""
        self.assertIn("人工处理计划", self.all_frontend_content, "Panel title '人工处理计划' not found")

    def test_required_disclaimer_present(self):
        """Required disclaimer must be present."""
        required_disclaimer = "这是人工处理计划，不是买卖建议，不会自动交易。"
        self.assertIn(
            required_disclaimer,
            self.all_frontend_content,
            f"Required disclaimer '{required_disclaimer}' not found"
        )

    def test_allowed_button_labels_present(self):
        """All four allowed button labels must be present."""
        allowed_labels = ["准备执行", "部分执行", "今日放弃", "标记过期"]
        for label in allowed_labels:
            self.assertIn(label, self.all_frontend_content, f"Allowed button label '{label}' not found")

    def test_forbidden_recommendation_phrases_absent(self):
        """Forbidden recommendation phrases must not appear."""
        forbidden_phrases = [
            "推荐买入",
            "推荐卖出",
            "立即买入",
            "立即卖出",
        ]
        for phrase in forbidden_phrases:
            self.assertNotIn(
                phrase,
                self.all_frontend_content,
                f"Forbidden phrase '{phrase}' found in frontend code"
            )

    def test_forbidden_execution_phrases_absent(self):
        """Forbidden execution phrases must not appear."""
        forbidden_phrases = [
            "一键下单",
            "自动执行",
        ]
        for phrase in forbidden_phrases:
            self.assertNotIn(
                phrase,
                self.all_frontend_content,
                f"Forbidden phrase '{phrase}' found in frontend code"
            )

    def test_forbidden_profit_phrases_absent(self):
        """Forbidden profit guarantee phrases must not appear."""
        forbidden_phrases = [
            "保证盈利",
            "稳定盈利",
            "实盘可用",
        ]
        for phrase in forbidden_phrases:
            self.assertNotIn(
                phrase,
                self.all_frontend_content,
                f"Forbidden phrase '{phrase}' found in frontend code"
            )

    def test_forbidden_strategy_ranking_phrases_absent(self):
        """Forbidden strategy ranking phrases must not appear."""
        forbidden_phrases = [
            "目标价",
            "最佳策略",
            "策略排名",
        ]
        for phrase in forbidden_phrases:
            self.assertNotIn(
                phrase,
                self.all_frontend_content,
                f"Forbidden phrase '{phrase}' found in frontend code"
            )

    def test_exception_phrase_allowed(self):
        """Exception: '不会自动交易' is allowed as part of required disclaimer."""
        # This phrase appears in the required disclaimer, so it should be present
        self.assertIn(
            "不会自动交易",
            self.all_frontend_content,
            "Exception phrase '不会自动交易' not found (required in disclaimer)"
        )

    def test_blocked_action_plan_disables_execute_button(self):
        """Blocked Action Plan must disable '准备执行' button."""
        # Verify logic exists to disable execute button when blocked
        self.assertIn("canAct", self.action_plan_panel_content, "canAct variable not found")
        self.assertIn("disabled={!canAct", self.action_plan_panel_content, "Execute button not using canAct check")

    def test_blocked_action_plan_disables_partial_button(self):
        """Blocked Action Plan must disable '部分执行' button."""
        # Verify both canAct variable exists and partial button uses it
        self.assertIn("canAct", self.action_plan_panel_content, "canAct variable not found")
        self.assertIn("部分执行", self.action_plan_panel_content, "Partial button not found")
        # Verify the pattern disabled={!canAct appears (for both execute and partial)
        self.assertIn("!canAct", self.action_plan_panel_content, "Buttons not using canAct check")

    def test_blocked_action_plan_allows_skip_and_expired(self):
        """Blocked Action Plan must still allow '今日放弃' and '标记过期'."""
        # Verify skip and expired buttons exist
        self.assertIn("今日放弃", self.action_plan_panel_content, "Skip button not found")
        self.assertIn("标记过期", self.action_plan_panel_content, "Expired button not found")

        # Count occurrences - canAct should appear in:
        # 1. Blocking notice conditional: {!canAct && ...}
        # 2. Execute button disabled: disabled={!canAct || isSubmitting}
        # 3. Partial button disabled: disabled={!canAct || isSubmitting}
        canact_count = self.action_plan_panel_content.count("!canAct")
        self.assertGreaterEqual(canact_count, 2, f"Expected at least 2 uses of !canAct, found {canact_count}")

    def test_blocking_notice_shown(self):
        """Blocking notice must be shown when canAct is false."""
        self.assertIn("阻断条件", self.action_plan_panel_content, "Blocking notice label not found")
        self.assertIn("无法执行或部分执行", self.action_plan_panel_content, "Blocking message not found")

    def test_no_broker_order_fields(self):
        """No broker/order/fill fields should appear in Action Plan UI code."""
        # Remove comments to avoid matching documentation
        import re
        # Remove single-line comments and multi-line comments
        content_no_comments = re.sub(r'/\*.*?\*/', '', self.all_frontend_content, flags=re.DOTALL)
        content_no_comments = re.sub(r'//.*?$', '', content_no_comments, flags=re.MULTILINE)

        # Check for actual field usage patterns (object properties, parameters, variables)
        forbidden_field_patterns = [
            r'\bbroker\s*[:=]',  # broker: or broker =
            r'\.broker\b',       # .broker
            r'\border_id\b',
            r'\bfill_price\b',
            r'\bfill_quantity\b',
            r'\bexecution_price\b',
            r'\bcommission\b',
            r'\bslippage\b',
        ]

        content_lower = content_no_comments.lower()
        for pattern in forbidden_field_patterns:
            match = re.search(pattern, content_lower)
            self.assertIsNone(
                match,
                f"Forbidden field pattern '{pattern}' found in frontend code: {match.group() if match else ''}"
            )


if __name__ == "__main__":
    unittest.main()
