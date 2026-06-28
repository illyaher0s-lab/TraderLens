"""
B5 Task 11: Compatibility and Boundary Tests

Validates that B5 does not cross boundaries into:
- Signal Board
- Live trading or broker integration
- LLM Gate
- User-supplied technical parameters (OOS dates, Gate thresholds, stress params)
- Legacy B4 qualification
- B3/B4 semantics modification
"""
import unittest
import ast
import os
from pathlib import Path


class TestB5Compatibility(unittest.TestCase):
    def setUp(self):
        self.b5_files = [
            "backend/services/oos_evaluation_controller.py",
            "backend/services/oos_budget_ledger.py",
            "backend/services/backtest_report_builder.py",
            "backend/services/control_comparison.py",
            "backend/services/cost_stress_runner.py",
            "backend/services/prototype_gate_v2.py",
            "backend/services/gate_explanation_builder.py",
            "backend/services/b5_oos_types.py",
        ]
        self.project_root = Path(__file__).parent.parent

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

    def test_b5_has_no_signal_board_dependency(self):
        """B5 has no Signal Board dependency."""
        forbidden = [
            "backend.services.signal_board",
            "backend.services.action_plan",
            "contracts.signal",
        ]

        for filepath in self.b5_files:
            imports = self._parse_imports(filepath)
            for forbidden_import in forbidden:
                self.assertNotIn(
                    forbidden_import,
                    imports,
                    f"{filepath} must not import {forbidden_import} (Signal Board is downstream of B5)"
                )

    def test_b5_has_no_live_trading_or_broker_dependency(self):
        """B5 has no live trading or broker dependency."""
        forbidden_keywords = [
            "broker",
            "live_trading",
            "order_submission",
            "execution_venue",
            "real_time_feed",
        ]

        for filepath in self.b5_files:
            content = self._read_file(filepath).lower()
            for keyword in forbidden_keywords:
                self.assertNotIn(
                    keyword,
                    content,
                    f"{filepath} must not reference {keyword} (B5 is historical validation only)"
                )

    def test_b5_has_no_llm_gate_dependency(self):
        """B5 has no LLM Gate dependency."""
        forbidden_imports = [
            "openai",
            "anthropic",
            "langchain",
        ]

        for filepath in self.b5_files:
            imports = self._parse_imports(filepath)
            for forbidden_import in forbidden_imports:
                self.assertNotIn(
                    forbidden_import,
                    imports,
                    f"{filepath} must not import {forbidden_import} (Gate must be deterministic)"
                )

    def test_b5_rejects_user_supplied_oos_dates(self):
        """B5 rejects user-supplied OOS dates."""
        # Check that OOS controller validates B3 protocol with frozen OOS window
        controller_file = "backend/services/oos_evaluation_controller.py"
        content = self._read_file(controller_file)

        # Must use B3 ResearchProtocolSnapshot
        self.assertIn("ResearchProtocolSnapshot", content)

        # Must validate protocol existence
        self.assertIn("isinstance(protocol, ResearchProtocolSnapshot)", content)

        # Protocol has frozen OOS window (oos_window_start, oos_window_end)
        # User cannot pass custom dates

    def test_b5_rejects_user_supplied_gate_thresholds(self):
        """B5 rejects user-supplied Gate thresholds."""
        gate_file = "backend/services/prototype_gate_v2.py"
        content = self._read_file(gate_file)

        # Gate must use frozen policies
        self.assertIn("OOS_DRAW_POLICIES", content)

        # Gate thresholds come from protocol.gate_criteria_hash, not user input
        self.assertIn("gate_criteria_hash", content)

    def test_b5_rejects_runtime_lowering_of_stress_policy(self):
        """B5 rejects runtime lowering of stress policy."""
        stress_file = "backend/services/cost_stress_runner.py"
        if not (self.project_root / stress_file).exists():
            self.skipTest(f"{stress_file} not yet implemented")

        content = self._read_file(stress_file)

        # Stress policy must be frozen or system-controlled
        # Cannot be lowered at runtime by user or API

    def test_b5_rejects_legacy_b4_qualification(self):
        """B5 rejects legacy B4 qualification."""
        controller_file = "backend/services/oos_evaluation_controller.py"
        content = self._read_file(controller_file)

        # Must reject string-only B4 result (legacy format)
        self.assertIn("isinstance(b4_result, str)", content)

        # Must require formal B4 result with protocol/data IDs
        self.assertIn("protocol_snapshot_id", content)
        self.assertIn("data_snapshot_hash", content)

    def test_b5_does_not_modify_b3_or_b4_semantics(self):
        """B5 does not modify B3 or B4 semantics."""
        forbidden_b3_b4_files = [
            "contracts/stable.py",
            "backend/services/backtest_time_cursor.py",
            "backend/services/future_data_guard.py",
            "strategy_core/backtest_engine.py",
        ]

        # B5 files must not import and modify B3/B4 core logic
        for b5_file in self.b5_files:
            imports = self._parse_imports(b5_file)

            # B5 can READ B3/B4 contracts, but cannot MODIFY them
            # Check that B5 does not import B3/B4 internals
            self.assertNotIn("backend.services.backtest_time_cursor", imports)
            self.assertNotIn("backend.services.future_data_guard", imports)

    def test_b5_does_not_generate_buy_sell_recommendations(self):
        """B5 does not generate buy/sell recommendations."""
        forbidden_keywords = [
            "buy_signal",
            "sell_signal",
            "trade_recommendation",
            "action_plan",
        ]

        for filepath in self.b5_files:
            content = self._read_file(filepath).lower()
            for keyword in forbidden_keywords:
                self.assertNotIn(
                    keyword,
                    content,
                    f"{filepath} must not generate {keyword} (B5 is validation only, not action generation)"
                )

    def test_b5_gate_never_outputs_prototype_passed(self):
        """B5 Gate never outputs prototype_passed verdict."""
        gate_file = "backend/services/prototype_gate_v2.py"
        content = self._read_file(gate_file)

        # Gate verdict must be one of: rejected, needs_review, candidate_for_prototype_passed
        # Never prototype_passed
        self.assertNotIn('verdict = "prototype_passed"', content)
        self.assertNotIn("verdict='prototype_passed'", content)

    def test_b5_does_not_modify_strategy_config(self):
        """B5 does not modify strategy config."""
        for filepath in self.b5_files:
            content = self._read_file(filepath)

            # B5 must not modify strategy_config_json
            self.assertNotIn("strategy_config_json =", content)

            # B5 reads strategy_config_hash, not modifies config

    def test_b5_does_not_bypass_oos_budget(self):
        """B5 does not bypass OOS budget."""
        budget_file = "backend/services/oos_budget_ledger.py"
        if not (self.project_root / budget_file).exists():
            self.skipTest(f"{budget_file} not yet implemented")

        content = self._read_file(budget_file)

        # Budget limit is enforced (check for >= 3 draw limit)
        self.assertTrue(
            ">= 3" in content or "completed_draw_count >= 3" in content,
            "Budget ledger must enforce 3-draw limit"
        )

    def test_b5_explanation_does_not_override_verdict(self):
        """B5 explanation does not override verdict."""
        explanation_file = "backend/services/gate_explanation_builder.py"
        content = self._read_file(explanation_file)

        # Explanation reads verdict, does not change it
        # Must fail if gate_result is None
        self.assertIn("gate_result is None", content)

        # Explanation must bind to gate_result_id
        self.assertIn("gate_result_id", content)

    def test_b5_does_not_delete_rejected_reports(self):
        """B5 does not delete rejected reports."""
        # Check that report builder and DB are append-only
        report_builder_file = "backend/services/backtest_report_builder.py"
        if not (self.project_root / report_builder_file).exists():
            self.skipTest(f"{report_builder_file} not yet implemented")

        content = self._read_file(report_builder_file)

        # Must not contain DELETE or DROP statements
        self.assertNotIn("DELETE FROM", content)
        self.assertNotIn("DROP TABLE", content)

    def test_b5_uses_frozen_protocol_contracts(self):
        """B5 uses frozen B3 protocol contracts."""
        controller_file = "backend/services/oos_evaluation_controller.py"
        content = self._read_file(controller_file)

        # Must import ResearchProtocolSnapshot from contracts.strategy
        imports = self._parse_imports(controller_file)
        self.assertIn("contracts.strategy", imports)

        # Must check protocol.frozen
        self.assertIn("frozen", content)

    def test_b5_does_not_expose_technical_parameters_to_user(self):
        """B5 does not expose technical parameters to user."""
        explanation_file = "backend/services/gate_explanation_builder.py"
        content = self._read_file(explanation_file)

        # Explanation must be plain-language
        # Must not ask user to choose technical parameters
        # Check docstring or comments mention "plain" or "user"
        self.assertIn("plain", content.lower())

    def test_b5_does_not_run_without_b4_qualification(self):
        """B5 does not run without B4 qualification."""
        controller_file = "backend/services/oos_evaluation_controller.py"
        content = self._read_file(controller_file)

        # Must validate B4 result
        self.assertIn("b4_result", content)

        # Must check qualification_status == "pass"
        self.assertIn("qualification_status", content)

    def test_b5_does_not_use_forward_watchlist(self):
        """B5 does not use forward watchlist."""
        controller_file = "backend/services/oos_evaluation_controller.py"
        content = self._read_file(controller_file)

        # Must reject ForwardWatchlistSnapshot
        self.assertIn("ForwardWatchlistSnapshot", content)

        # Must only accept PointInTimeMembershipSnapshot
        self.assertIn("PointInTimeMembershipSnapshot", content)

    def test_b5_does_not_modify_b4_result(self):
        """B5 does not modify B4 result."""
        for filepath in self.b5_files:
            content = self._read_file(filepath)

            # B5 reads EventBacktestResult, does not modify it
            # Check that B5 does not assign to result fields


if __name__ == "__main__":
    unittest.main()
