"""
V1 Copy Encoding And Boundary Tests

Task 15: Fix User-Facing Chinese Copy And Encoding

Test goals:
1. User-visible production files must not contain mojibake (UTF-8 decoding errors)
2. User-visible production files must not contain over-promise phrases
3. User-visible production files must not expose technical parameters
4. Compliance boundary copy must be present

Scope:
- Frontend components (TypeScript/TSX)
- Backend contracts (Python)
- Backend services that generate user-visible copy (Python)

Exclusions:
- node_modules, .next, tsbuildinfo
- Test files and test fixtures
- Historical docs and reports
"""

import unittest
from pathlib import Path
import re


class TestV1CopyEncoding(unittest.TestCase):
    """Test V1 user-visible copy encoding and boundaries."""

    @classmethod
    def setUpClass(cls):
        """Load production files once for all tests."""
        cls.root = Path(__file__).parent.parent

        # Frontend user-visible files
        cls.frontend_files = [
            cls.root / "frontend" / "app" / "page.tsx",
            cls.root / "frontend" / "app" / "workbench" / "page.tsx",
            cls.root / "frontend" / "app" / "signals" / "page.tsx",
            cls.root / "frontend" / "app" / "signals" / "[signal_id]" / "page.tsx",
            cls.root / "frontend" / "components" / "ActionPlanPanel.tsx",
            cls.root / "frontend" / "components" / "AgentChatPanel.tsx",
            cls.root / "frontend" / "components" / "ApprovalCard.tsx",
            cls.root / "frontend" / "components" / "WorkbenchTimeline.tsx",
            cls.root / "frontend" / "components" / "WorkflowStatusPanel.tsx",
            cls.root / "frontend" / "components" / "LiveLoopPanel.tsx",
        ]

        # Backend contracts (user-visible copy in defaults)
        cls.backend_contract_files = [
            cls.root / "contracts" / "action_plan.py",
            cls.root / "contracts" / "signal_board.py",
        ]

        # Backend services (user-visible copy generation)
        cls.backend_service_files = [
            cls.root / "backend" / "services" / "action_plan_builder.py",
            cls.root / "backend" / "services" / "recommendation_reducer.py",
            cls.root / "backend" / "services" / "execution_card_builder.py",
            cls.root / "backend" / "services" / "observation_pool.py",
            cls.root / "backend" / "services" / "discipline_review.py",
        ]

        # Collect all content
        cls.all_content = {}
        for path in cls.frontend_files + cls.backend_contract_files + cls.backend_service_files:
            if path.exists():
                cls.all_content[str(path)] = path.read_text(encoding="utf-8")

        # Combined content for quick checks
        cls.combined_content = "\n".join(cls.all_content.values())

    def test_no_mojibake_in_user_visible_files(self):
        """Production files must not contain common mojibake fragments."""
        # Common UTF-8/GBK decoding mojibake patterns
        mojibake_fragments = [
            "涓",  # Common in GBK misinterpretation
            "锟",  # U+FFFD replacement character variants
            "�",   # U+FFFD replacement character
            "å",   # UTF-8 byte sequences misread
            "æ",
            "ç",
            "ä¸",  # "中" misread
            "è¯",  # "话" misread
            "äº",  # "了" misread
            "å·",  # Various Chinese chars misread
            "ï¼",  # "！" misread
            "â",   # Various punctuation misread
            "Ã",   # Common UTF-8 double-encoding
            "鐩",  # From existing test
            "鍏",
            "绂",
            "淇",
            "瀹",
            "鈫",
            "鉁",
        ]

        for path_str, content in self.all_content.items():
            for fragment in mojibake_fragments:
                with self.subTest(file=Path(path_str).name, fragment=fragment):
                    self.assertNotIn(
                        fragment,
                        content,
                        f"Mojibake fragment '{fragment}' found in {path_str}"
                    )

    def test_no_profit_guarantee_phrases(self):
        """Production files must not contain profit guarantee phrases."""
        forbidden_phrases = [
            "保证盈利",
            "稳定盈利",
            "稳赚",
            "必赚",
            "确保盈利",
            "盈利保证",
        ]

        for phrase in forbidden_phrases:
            with self.subTest(phrase=phrase):
                self.assertNotIn(
                    phrase,
                    self.combined_content,
                    f"Forbidden profit guarantee phrase '{phrase}' found in production files"
                )

    def test_no_automatic_trading_claims(self):
        """Production files must not claim automatic trading capability."""
        forbidden_phrases = [
            "自动下单",
            "系统已下单",
            "已替你买入",
            "已替你卖出",
            "无需人工",
            "全自动交易",
            "一键自动交易",
            "自动执行交易",
            "系统自动买入",
            "系统自动卖出",
        ]

        # Exception: "不会自动交易" is allowed (part of disclaimer)
        exception_phrase = "不会自动交易"
        
        for phrase in forbidden_phrases:
            with self.subTest(phrase=phrase):
                self.assertNotIn(
                    phrase,
                    self.combined_content,
                    f"Forbidden automatic trading phrase '{phrase}' found in production files"
                )

        # Verify exception phrase is present (required disclaimer)
        self.assertIn(
            exception_phrase,
            self.combined_content,
            f"Required disclaimer phrase '{exception_phrase}' not found"
        )

    def test_no_technical_parameters_exposed_to_user(self):
        """Production files must not expose technical parameters to users."""
        # These terms are forbidden in user-visible UI strings and contract defaults
        # but allowed in code comments and docstrings
        forbidden_terms = [
            # English technical terms
            ("OOS", r'\bOOS\b(?!.*(?:docstring|description|comment))'),
            ("threshold", r'\bthreshold\b(?!.*(?:docstring|description|comment))'),
            ("stop_loss", r'\bstop_loss\b(?!.*(?:docstring|description|comment))'),
            ("liquidity_rule", r'\bliquidity_rule\b(?!.*(?:docstring|description|comment))'),
            ("position_size", r'\bposition_size\b(?!.*(?:docstring|description|comment))'),
            ("backtest_param", r'\bbacktest_param\b(?!.*(?:docstring|description|comment))'),
            # Chinese technical terms
            ("止损比例", r'止损比例(?!.*(?:注释|说明|描述))'),
            ("仓位公式", r'仓位公式(?!.*(?:注释|说明|描述))'),
            ("流动性规则", r'流动性规则(?!.*(?:注释|说明|描述))'),
            ("回测参数", r'回测参数(?!.*(?:注释|说明|描述))'),
            ("策略模板参数", r'策略模板参数(?!.*(?:注释|说明|描述))'),
        ]

        # Only check frontend files (where users see UI strings)
        frontend_content = "\n".join([
            content for path, content in self.all_content.items()
            if "frontend" in path
        ])

        for term_display, pattern in forbidden_terms:
            with self.subTest(term=term_display):
                # Remove comments first to avoid false positives
                content_no_comments = self._remove_comments(frontend_content)
                
                # Search in cleaned content
                match = re.search(pattern, content_no_comments, re.IGNORECASE | re.MULTILINE)
                self.assertIsNone(
                    match,
                    f"Technical parameter term '{term_display}' found exposed to user in frontend files"
                )

    def test_required_compliance_boundary_copy_present(self):
        """Compliance boundary copy must be present in user-facing UI."""
        required_phrases = [
            "不是买卖建议",
            "不会自动交易",
            "需要人工审核",
        ]

        # Check in Workbench page (main entry point)
        workbench_content = self.all_content.get(
            str(self.root / "frontend" / "app" / "workbench" / "page.tsx"),
            ""
        )

        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(
                    phrase,
                    workbench_content,
                    f"Required compliance phrase '{phrase}' not found in Workbench UI"
                )

    def test_action_plan_has_required_disclaimer(self):
        """Action Plan must have required disclaimer."""
        required_disclaimer = "这是人工处理计划，不是买卖建议，不会自动交易。"
        
        action_plan_content = self.all_content.get(
            str(self.root / "frontend" / "components" / "ActionPlanPanel.tsx"),
            ""
        )

        self.assertIn(
            required_disclaimer,
            action_plan_content,
            "Required disclaimer not found in ActionPlanPanel"
        )

    def test_action_plan_contract_has_no_broker_fields(self):
        """Action Plan contract must not contain broker/order/fill fields."""
        action_plan_contract = self.all_content.get(
            str(self.root / "contracts" / "action_plan.py"),
            ""
        )

        # Remove docstrings to avoid matching documentation
        content_no_docstrings = self._remove_python_docstrings(action_plan_contract)

        # Check for field definitions (not just mentions in comments)
        forbidden_field_patterns = [
            r'^\s*broker\s*:',          # Field definition: broker: str
            r'^\s*order_id\s*:',
            r'^\s*fill_price\s*:',
            r'^\s*fill_quantity\s*:',
            r'^\s*execution_price\s*:',
            r'^\s*commission\s*:',
            r'^\s*slippage\s*:',
        ]

        for pattern in forbidden_field_patterns:
            with self.subTest(pattern=pattern):
                match = re.search(pattern, content_no_docstrings, re.MULTILINE)
                self.assertIsNone(
                    match,
                    f"Forbidden field pattern '{pattern}' found in action_plan.py contract"
                )

    def test_approval_card_uses_plain_language(self):
        """Approval Card must use plain Chinese labels, not technical terms."""
        approval_card_content = self.all_content.get(
            str(self.root / "frontend" / "components" / "ApprovalCard.tsx"),
            ""
        )

        # Required plain language labels
        required_labels = [
            "继续",
            "停止",
            "降级观察",
            "进入小资金实盘观察",
            "接受记录解释",
        ]

        for label in required_labels:
            with self.subTest(label=label):
                self.assertIn(
                    label,
                    approval_card_content,
                    f"Required plain language label '{label}' not found in ApprovalCard"
                )

        # Forbidden technical labels
        forbidden_labels = [
            "approve_for_production",
            "reject_validation",
            "force_override",
            "bypass_gate",
        ]

        for label in forbidden_labels:
            with self.subTest(label=label):
                self.assertNotIn(
                    label,
                    approval_card_content,
                    f"Forbidden technical label '{label}' found in ApprovalCard"
                )

    def _remove_comments(self, content: str) -> str:
        """Remove single-line and multi-line comments from TypeScript/JavaScript."""
        # Remove multi-line comments /* ... */
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        # Remove single-line comments //...
        content = re.sub(r'//.*?$', '', content, flags=re.MULTILINE)
        return content

    def _remove_python_docstrings(self, content: str) -> str:
        """Remove Python docstrings (triple-quoted strings)."""
        # Remove triple-quoted docstrings
        content = re.sub(r'""".*?"""', '', content, flags=re.DOTALL)
        content = re.sub(r"'''.*?'''", '', content, flags=re.DOTALL)
        return content


if __name__ == "__main__":
    unittest.main()
