"""
B6 No Shortcuts Boundary Tests

Tests that B6 does not bypass the original B-module V1 plan boundaries.
"""
import unittest
import ast
from pathlib import Path


class TestB6NoShortcuts(unittest.TestCase):
    def setUp(self):
        self.project_root = Path(__file__).parent.parent
        self.b6_files = [
            "backend/services/b6_validation_flow.py",
            "backend/services/c_admission_gate.py",
            "backend/services/b5_oos_types.py",
        ]

    def _read_file(self, filepath: str) -> str:
        """Read file content."""
        full_path = self.project_root / filepath
        if not full_path.exists():
            return ""
        return full_path.read_text(encoding="utf-8")

    def _parse_imports(self, filepath: str) -> list[str]:
        """Parse all imports from a Python file."""
        content = self._read_file(filepath)
        if not content:
            return []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        return imports

    def test_b6_has_no_ui_dependency(self):
        """B6 has no UI dependency."""
        for filepath in self.b6_files:
            content = self._read_file(filepath).lower()

            forbidden = ["frontend", "react", "page.tsx", "app.tsx"]
            for term in forbidden:
                self.assertNotIn(
                    term,
                    content,
                    f"{filepath} must not reference {term} (B6 is backend-only)",
                )

    def test_b6_has_no_external_broker_or_live_api_dependency(self):
        """B6 has no external broker or live API dependency."""
        for filepath in self.b6_files:
            content = self._read_file(filepath).lower()

            forbidden = [
                "broker",
                "live_trading",
                "order_submission",
                "real_time_feed",
                "execution_venue",
            ]
            for term in forbidden:
                self.assertNotIn(
                    term,
                    content,
                    f"{filepath} must not reference {term} (B6 is offline validation)",
                )

    def test_b6_has_no_llm_gate_dependency(self):
        """B6 has no LLM Gate dependency."""
        for filepath in self.b6_files:
            imports = self._parse_imports(filepath)

            forbidden_imports = ["openai", "anthropic", "langchain"]
            for forbidden_import in forbidden_imports:
                self.assertNotIn(
                    forbidden_import,
                    imports,
                    f"{filepath} must not import {forbidden_import} (Gate must be deterministic)",
                )

    def test_b6_does_not_import_signal_board_action_generation(self):
        """B6 does not import Signal Board action generation."""
        for filepath in self.b6_files:
            imports = self._parse_imports(filepath)

            forbidden = [
                "backend.services.signal_board",
                "backend.services.action_plan",
                "contracts.signal",
            ]
            for forbidden_import in forbidden:
                self.assertNotIn(
                    forbidden_import,
                    imports,
                    f"{filepath} must not import {forbidden_import} (Signal Board is downstream of B6)",
                )

    def test_b6_does_not_modify_b3_or_b4_semantics(self):
        """B6 does not modify B3 or B4 semantics."""
        for filepath in self.b6_files:
            imports = self._parse_imports(filepath)

            # B6 can READ B3/B4 contracts, but cannot MODIFY them
            forbidden = [
                "backend.services.backtest_time_cursor",
                "backend.services.future_data_guard",
            ]
            for forbidden_import in forbidden:
                self.assertNotIn(
                    forbidden_import,
                    imports,
                    f"{filepath} must not import {forbidden_import} (B6 cannot modify B3/B4 semantics)",
                )

    def test_b6_does_not_generate_buy_sell_recommendations(self):
        """B6 does not generate buy/sell recommendations."""
        for filepath in self.b6_files:
            content = self._read_file(filepath).lower()

            forbidden = [
                "buy_signal",
                "sell_signal",
                "trade_recommendation",
                "action_plan",
                "target_price",
                "stop_loss",
            ]
            for term in forbidden:
                self.assertNotIn(
                    term,
                    content,
                    f"{filepath} must not generate {term} (B6 is validation only)",
                )

    def test_b6_validation_flow_rejects_user_technical_parameters(self):
        """B6 validation flow explicitly rejects user technical parameters."""
        flow_file = "backend/services/b6_validation_flow.py"
        content = self._read_file(flow_file)

        # Verify **unexpected_user_parameters pattern exists
        self.assertIn("**unexpected_user_parameters", content)
        self.assertIn("user-supplied technical parameters", content.lower())

    def test_b6_does_not_bypass_oos_controller_validation(self):
        """B6 does not bypass OOS controller validation."""
        flow_file = "backend/services/b6_validation_flow.py"
        content = self._read_file(flow_file)

        # Verify B6 calls OOSEvaluationController.validate_b3_b4_prerequisites
        self.assertIn("OOSEvaluationController", content)
        self.assertIn("validate_b3_b4_prerequisites", content)

    def test_b6_uses_existing_gate_and_explanation_builders(self):
        """B6 uses existing Gate and explanation builders."""
        flow_file = "backend/services/b6_validation_flow.py"
        content = self._read_file(flow_file)

        # Verify B6 imports existing builders
        self.assertIn("PrototypeGateV2", content)
        self.assertIn("GateExplanationBuilder", content)
        self.assertIn("BacktestReportBuilder", content)

    def test_b6_promotion_uses_strategy_promotion_reducer(self):
        """B6 promotion uses StrategyPromotionReducer."""
        flow_file = "backend/services/b6_validation_flow.py"
        content = self._read_file(flow_file)

        # Verify B6 uses StrategyPromotionReducer
        self.assertIn("StrategyPromotionReducer", content)
        self.assertIn("promote_to_prototype_passed", content)


if __name__ == "__main__":
    unittest.main()
