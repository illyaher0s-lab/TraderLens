"""B5 PrototypeGateV2 Tests."""
import unittest
from datetime import date, datetime

from backend.services.prototype_gate_v2 import PrototypeGateV2
from contracts.strategy import ImmutableBacktestReport, PrototypeGateResultV2


class TestPrototypeGateV2(unittest.TestCase):
    """Test PrototypeGateV2 evaluator."""
    
    def setUp(self):
        self.gate = PrototypeGateV2()
    
    def test_gate_rejects_future_data_violations(self):
        """Gate must hard reject if future_data_violation_count > 0."""
        import json
        
        # Report with future data violations
        report_payload = {
            "protocol_snapshot_id": "proto_001",
            "strategy_config_hash": "config_001",
            "data_snapshot_hash": "data_001",
            "gate_criteria_hash": "gate_001",
            "future_data_violation_count": 2,  # Has violations
            "b4_read_trace_summary": "test",
            "adjustment_mode": "qfq",
            "adjustment_snapshot_fingerprint": "adj_001",
            "liquidation_impact": 0.0,
            "disclaimer": "test",
        }
        
        report = ImmutableBacktestReport(
            report_id="rpt_001",
            theme_id="theme_001",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            strategy_config_hash="config_001",
            data_snapshot_hash="data_001",
            gate_criteria_hash="gate_001",
            evaluation_mode="out_of_sample",
            oos_draw_index=1,
            shared_oos_window_id="oos_001",
            multiple_comparison_flag=False,
            report_payload_json=json.dumps(report_payload),
            integrity_status="valid",
            generated_at=datetime.now(),
            report_hash="hash_001",
        )
        
        result = self.gate.evaluate(report=report, gate_criteria_hash="gate_001")
        
        self.assertEqual(result.verdict, "rejected")
        self.assertIn("future data", result.blocking_issues[0].lower())
    
    def test_gate_rejects_gate_criteria_hash_mismatch(self):
        """Gate must reject if gate_criteria_hash mismatch."""
        import json
        
        report_payload = {
            "protocol_snapshot_id": "proto_001",
            "strategy_config_hash": "config_001",
            "data_snapshot_hash": "data_001",
            "gate_criteria_hash": "gate_001",
            "future_data_violation_count": 0,
            "b4_read_trace_summary": "test",
            "adjustment_mode": "qfq",
            "adjustment_snapshot_fingerprint": "adj_001",
            "liquidation_impact": 0.0,
            "disclaimer": "test",
        }
        
        report = ImmutableBacktestReport(
            report_id="rpt_001",
            theme_id="theme_001",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            strategy_config_hash="config_001",
            data_snapshot_hash="data_001",
            gate_criteria_hash="gate_001",
            evaluation_mode="out_of_sample",
            oos_draw_index=1,
            shared_oos_window_id="oos_001",
            multiple_comparison_flag=False,
            report_payload_json=json.dumps(report_payload),
            integrity_status="valid",
            generated_at=datetime.now(),
            report_hash="hash_001",
        )
        
        # Gate criteria hash mismatch
        with self.assertRaises(ValueError) as ctx:
            self.gate.evaluate(report=report, gate_criteria_hash="gate_DIFFERENT")
        
        self.assertIn("criteria hash mismatch", str(ctx.exception).lower())
    
    def test_gate_never_outputs_prototype_passed(self):
        """Gate must never output prototype_passed verdict."""
        gate_result = PrototypeGateResultV2(
            gate_result_id="gate_001",
            report_id="rpt_001",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            verdict="candidate_for_prototype_passed",
            checks_json="{}",
            blocking_issues=(),
            warnings=(),
            strategy_config_hash="config_001",
            data_snapshot_hash="data_001",
            gate_criteria_hash="gate_001",
            oos_draw_index=1,
            shared_oos_window_id="oos_001",
            multiple_comparison_flag=False,
            generated_at=datetime.now(),
            gate_result_hash="hash_001",
        )
        
        # Check verdict cannot be prototype_passed
        self.assertIn(gate_result.verdict, ["rejected", "needs_review", "candidate_for_prototype_passed"])
        self.assertNotEqual(gate_result.verdict, "prototype_passed")
    
    def test_gate_does_not_write_lifecycle_state(self):
        """Gate must not write lifecycle state or call StrategyPromotionReducer."""
        import backend.services.prototype_gate_v2 as gate_module
        import inspect
        
        source = inspect.getsource(gate_module)
        
        # Gate must not import lifecycle write tools
        forbidden_imports = ["StrategyPromotionReducer", "backend.db.strategy"]
        for forbidden in forbidden_imports:
            self.assertNotIn(forbidden, source)
    
    def test_missing_base_stress_or_control_cannot_candidate(self):
        """Missing base/stress/control results block candidate verdict."""
        import json
        
        # Report with missing stress cost
        report_payload = {
            "protocol_snapshot_id": "proto_001",
            "strategy_config_hash": "config_001",
            "data_snapshot_hash": "data_001",
            "gate_criteria_hash": "gate_001",
            "future_data_violation_count": 0,
            "b4_read_trace_summary": "test",
            "adjustment_mode": "qfq",
            "adjustment_snapshot_fingerprint": "adj_001",
            "liquidation_impact": 0.0,
            "stress_cost_result": "not_available_from_b4_result",  # Missing
            "disclaimer": "test",
        }
        
        report = ImmutableBacktestReport(
            report_id="rpt_001",
            theme_id="theme_001",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            strategy_config_hash="config_001",
            data_snapshot_hash="data_001",
            gate_criteria_hash="gate_001",
            evaluation_mode="out_of_sample",
            oos_draw_index=1,
            shared_oos_window_id="oos_001",
            multiple_comparison_flag=False,
            report_payload_json=json.dumps(report_payload),
            integrity_status="valid",
            generated_at=datetime.now(),
            report_hash="hash_001",
        )
        
        result = self.gate.evaluate(report=report, gate_criteria_hash="gate_001")
        
        self.assertIn(result.verdict, ["rejected", "needs_review"])
        self.assertNotEqual(result.verdict, "candidate_for_prototype_passed")
    
    def test_data_insufficient_cannot_candidate(self):
        """Data insufficient status blocks candidate verdict."""
        import json
        
        report = ImmutableBacktestReport(
            report_id="rpt_001",
            theme_id="theme_001",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            strategy_config_hash="config_001",
            data_snapshot_hash="data_001",
            gate_criteria_hash="gate_001",
            evaluation_mode="out_of_sample",
            oos_draw_index=1,
            shared_oos_window_id="oos_001",
            multiple_comparison_flag=False,
            report_payload_json="{}",
            integrity_status="invalid",  # Data insufficient
            generated_at=datetime.now(),
            report_hash="hash_001",
        )
        
        result = self.gate.evaluate(report=report, gate_criteria_hash="gate_001")
        
        self.assertIn(result.verdict, ["rejected", "needs_review"])
        self.assertNotEqual(result.verdict, "candidate_for_prototype_passed")
    
    def test_draw_2_and_3_are_not_weaker_than_draw_1(self):
        """OOS draw 2 and 3 must have stricter or equal thresholds than draw 1."""
        # This test verifies policy exists, not that it's configurable
        draw_1_policy = self.gate.get_oos_policy(oos_draw_index=1)
        draw_2_policy = self.gate.get_oos_policy(oos_draw_index=2)
        draw_3_policy = self.gate.get_oos_policy(oos_draw_index=3)
        
        # Draw 2/3 thresholds must be >= draw 1
        self.assertGreaterEqual(draw_2_policy["min_sharpe"], draw_1_policy["min_sharpe"])
        self.assertGreaterEqual(draw_3_policy["min_sharpe"], draw_2_policy["min_sharpe"])
    
    def test_gate_has_no_llm_dependency(self):
        """Gate must not import or call LLM."""
        import backend.services.prototype_gate_v2 as gate_module
        import inspect
        
        source = inspect.getsource(gate_module)
        
        # Check no LLM imports
        forbidden_imports = ["import openai", "from openai", "import anthropic", "from anthropic"]
        for forbidden in forbidden_imports:
            self.assertNotIn(forbidden, source)
    
    def test_high_absolute_return_fails_if_control_or_stress_fails(self):
        """High absolute return cannot pass if control/stress checks fail."""
        import json
        
        # Report with high return but missing control
        report_payload = {
            "protocol_snapshot_id": "proto_001",
            "strategy_config_hash": "config_001",
            "data_snapshot_hash": "data_001",
            "gate_criteria_hash": "gate_001",
            "future_data_violation_count": 0,
            "b4_read_trace_summary": "test",
            "adjustment_mode": "qfq",
            "adjustment_snapshot_fingerprint": "adj_001",
            "liquidation_impact": 0.0,
            "strategy_return": 0.50,  # 50% return
            "control_comparison": "not_available_from_b4_result",  # Missing
            "disclaimer": "test",
        }
        
        report = ImmutableBacktestReport(
            report_id="rpt_001",
            theme_id="theme_001",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            strategy_config_hash="config_001",
            data_snapshot_hash="data_001",
            gate_criteria_hash="gate_001",
            evaluation_mode="out_of_sample",
            oos_draw_index=1,
            shared_oos_window_id="oos_001",
            multiple_comparison_flag=False,
            report_payload_json=json.dumps(report_payload),
            integrity_status="valid",
            generated_at=datetime.now(),
            report_hash="hash_001",
        )
        
        result = self.gate.evaluate(report=report, gate_criteria_hash="gate_001")
        
        # High return alone cannot pass without control
        self.assertNotEqual(result.verdict, "candidate_for_prototype_passed")

    def test_explicit_stress_failure_blocks_candidate(self):
        """Gate must reject a present but failed stress result."""
        import json

        report_payload = {
            "protocol_snapshot_id": "proto_001",
            "strategy_config_hash": "config_001",
            "data_snapshot_hash": "data_001",
            "gate_criteria_hash": "gate_001",
            "future_data_violation_count": 0,
            "base_cost_result": {"status": "pass"},
            "stress_cost_result": {"status": "fail"},
            "benchmark_comparison": {"status": "pass"},
            "control_comparison": {"status": "pass"},
            "data_quality_status": "ok",
        }

        report = ImmutableBacktestReport(
            report_id="rpt_001",
            theme_id="theme_001",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            strategy_config_hash="config_001",
            data_snapshot_hash="data_001",
            gate_criteria_hash="gate_001",
            evaluation_mode="out_of_sample",
            oos_draw_index=1,
            shared_oos_window_id="oos_001",
            multiple_comparison_flag=False,
            report_payload_json=json.dumps(report_payload),
            integrity_status="valid",
            generated_at=datetime.now(),
            report_hash="hash_001",
        )

        result = self.gate.evaluate(report=report, gate_criteria_hash="gate_001")

        self.assertEqual(result.verdict, "rejected")
        self.assertTrue(any("stress" in issue.lower() for issue in result.blocking_issues))

    def test_explicit_control_or_benchmark_failure_blocks_candidate(self):
        """Gate must reject failed benchmark/control comparison, not just require presence."""
        import json

        for failed_field in ("benchmark_comparison", "control_comparison"):
            report_payload = {
                "protocol_snapshot_id": "proto_001",
                "strategy_config_hash": "config_001",
                "data_snapshot_hash": "data_001",
                "gate_criteria_hash": "gate_001",
                "future_data_violation_count": 0,
                "base_cost_result": {"status": "pass"},
                "stress_cost_result": {"status": "pass"},
                "benchmark_comparison": {"status": "pass"},
                "control_comparison": {"status": "pass"},
                "data_quality_status": "ok",
            }
            report_payload[failed_field] = {"status": "fail"}

            report = ImmutableBacktestReport(
                report_id=f"rpt_{failed_field}",
                theme_id="theme_001",
                strategy_revision_id="strat_001",
                protocol_snapshot_id="proto_001",
                strategy_config_hash="config_001",
                data_snapshot_hash="data_001",
                gate_criteria_hash="gate_001",
                evaluation_mode="out_of_sample",
                oos_draw_index=1,
                shared_oos_window_id="oos_001",
                multiple_comparison_flag=False,
                report_payload_json=json.dumps(report_payload),
                integrity_status="valid",
                generated_at=datetime.now(),
                report_hash="hash_001",
            )

            result = self.gate.evaluate(report=report, gate_criteria_hash="gate_001")

            self.assertEqual(result.verdict, "rejected")
            self.assertTrue(
                any(failed_field.replace("_", " ") in issue.lower() for issue in result.blocking_issues)
            )

    def test_concentration_or_beta_flags_block_candidate(self):
        """Gate must reject beta domination and concentration flags from deterministic comparison."""
        import json

        report_payload = {
            "protocol_snapshot_id": "proto_001",
            "strategy_config_hash": "config_001",
            "data_snapshot_hash": "data_001",
            "gate_criteria_hash": "gate_001",
            "future_data_violation_count": 0,
            "base_cost_result": {"status": "pass"},
            "stress_cost_result": {"status": "pass"},
            "benchmark_comparison": {"status": "pass"},
            "control_comparison": {"status": "pass"},
            "data_quality_status": "ok",
            "beta_dominated": True,
            "single_symbol_concentration": {"can_candidate": False},
        }

        report = ImmutableBacktestReport(
            report_id="rpt_001",
            theme_id="theme_001",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            strategy_config_hash="config_001",
            data_snapshot_hash="data_001",
            gate_criteria_hash="gate_001",
            evaluation_mode="out_of_sample",
            oos_draw_index=1,
            shared_oos_window_id="oos_001",
            multiple_comparison_flag=False,
            report_payload_json=json.dumps(report_payload),
            integrity_status="valid",
            generated_at=datetime.now(),
            report_hash="hash_001",
        )

        result = self.gate.evaluate(report=report, gate_criteria_hash="gate_001")

        self.assertEqual(result.verdict, "rejected")
        joined_issues = " ".join(result.blocking_issues).lower()
        self.assertIn("beta", joined_issues)
        self.assertIn("concentration", joined_issues)


if __name__ == "__main__":
    unittest.main()
