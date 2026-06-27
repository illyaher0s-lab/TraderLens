"""Backtest Report Builder Tests."""
import unittest
from datetime import date, datetime

from backend.services.backtest_report_builder import BacktestReportBuilder
from backend.services.b4_protocol_types import (
    EventBacktestResult,
    DailyPortfolioSnapshot,
)


class TestBacktestReportBuilder(unittest.TestCase):
    """Test backtest report builder."""
    
    def setUp(self):
        self.builder = BacktestReportBuilder()
        
        # Valid B4 event backtest result
        self.b4_result = EventBacktestResult(
            result_id="result_001",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            evaluation_mode="formal_backtest",
            backtest_start=date(2023, 1, 1),
            backtest_end=date(2023, 12, 31),
            order_intents=(),
            fills=(),
            rejected_orders=(),
            future_violations=(),
            final_portfolio=DailyPortfolioSnapshot(
                snapshot_id="final_001",
                snapshot_date=date(2023, 12, 31),
                cash=100000.0,
                positions=(),
                portfolio_value=100000.0,
            ),
            frozen_at=date(2024, 1, 1),
        )
    
    def test_report_records_protocol_and_three_hashes(self):
        """Report must include protocol_snapshot_id and three hashes."""
        report = self.builder.build_report(
            report_id="rpt_001",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            strategy_config_hash="config_hash_001",
            data_snapshot_hash="data_hash_001",
            gate_criteria_hash="gate_hash_001",
            oos_draw_index=1,
            shared_oos_window_id="shared_oos_001",
            b4_result=self.b4_result,
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adj_fp_001",
        )
        
        self.assertEqual(report.protocol_snapshot_id, "proto_001")
        self.assertEqual(report.strategy_config_hash, "config_hash_001")
        self.assertEqual(report.data_snapshot_hash, "data_hash_001")
        self.assertEqual(report.gate_criteria_hash, "gate_hash_001")
    
    def test_report_records_oos_draw_and_window(self):
        """Report must include oos_draw_index and shared_oos_window_id."""
        report = self.builder.build_report(
            report_id="rpt_test",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            strategy_config_hash="config_hash_001",
            data_snapshot_hash="data_hash_001",
            gate_criteria_hash="gate_hash_001",
            oos_draw_index=2,
            shared_oos_window_id="shared_oos_002",
            b4_result=self.b4_result,
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adj_fp_001",
        )
        
        self.assertEqual(report.oos_draw_index, 2)
        self.assertEqual(report.shared_oos_window_id, "shared_oos_002")
    
    def test_report_records_b4_read_trace_summary(self):
        """Report must include B4 read trace summary."""
        report = self.builder.build_report(
            report_id="rpt_test",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            strategy_config_hash="config_hash_001",
            data_snapshot_hash="data_hash_001",
            gate_criteria_hash="gate_hash_001",
            oos_draw_index=1,
            shared_oos_window_id="shared_oos_001",
            b4_result=self.b4_result,
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adj_fp_001",
        )
        
        import json
        payload = json.loads(report.report_payload_json)
        self.assertIsNotNone(payload["b4_read_trace_summary"])
        self.assertGreater(len(payload["b4_read_trace_summary"]), 0)
        self.assertIn("Orders:", payload["b4_read_trace_summary"])
    
    def test_report_records_future_data_violation_count(self):
        """Report must record future data violation count."""
        from backend.services.b4_protocol_types import FutureDataViolation
        
        # B4 result with violations
        b4_with_violations = EventBacktestResult(
            result_id="result_002",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            evaluation_mode="formal_backtest",
            backtest_start=date(2023, 1, 1),
            backtest_end=date(2023, 12, 31),
            order_intents=(),
            fills=(),
            rejected_orders=(),
            future_violations=(
                FutureDataViolation(
                    requested_date=date(2023, 1, 2),
                    allowed_max_date=date(2023, 1, 1),
                    source="test_bar_read",
                    reason="Attempted T+1 read",
                    evaluation_mode="signal_phase",
                ),
                FutureDataViolation(
                    requested_date=date(2023, 1, 3),
                    allowed_max_date=date(2023, 1, 1),
                    source="test_status_read",
                    reason="Attempted T+2 read",
                    evaluation_mode="signal_phase",
                ),
            ),
            final_portfolio=DailyPortfolioSnapshot(
                snapshot_id="final_002",
                snapshot_date=date(2023, 12, 31),
                cash=100000.0,
                positions=(),
                portfolio_value=100000.0,
            ),
            frozen_at=date(2024, 1, 1),
        )
        
        report = self.builder.build_report(
            report_id="rpt_test",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            strategy_config_hash="config_hash_001",
            data_snapshot_hash="data_hash_001",
            gate_criteria_hash="gate_hash_001",
            oos_draw_index=1,
            shared_oos_window_id="shared_oos_001",
            b4_result=b4_with_violations,
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adj_fp_001",
        )
        
        import json
        payload = json.loads(report.report_payload_json)
        self.assertEqual(payload["future_data_violation_count"], 2)
    
    def test_report_records_adjustment_snapshot_metadata(self):
        """Report must record adjustment mode and fingerprint."""
        report = self.builder.build_report(
            report_id="rpt_test",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            strategy_config_hash="config_hash_001",
            data_snapshot_hash="data_hash_001",
            gate_criteria_hash="gate_hash_001",
            oos_draw_index=1,
            shared_oos_window_id="shared_oos_001",
            b4_result=self.b4_result,
            adjustment_mode="hfq",
            adjustment_snapshot_fingerprint="adj_fp_hfq_001",
        )
        
        import json
        payload = json.loads(report.report_payload_json)
        self.assertEqual(payload["adjustment_mode"], "hfq")
        self.assertEqual(payload["adjustment_snapshot_fingerprint"], "adj_fp_hfq_001")
    
    def test_report_records_liquidation_impact(self):
        """Report must record liquidation impact (non-negative)."""
        report = self.builder.build_report(
            report_id="rpt_test",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            strategy_config_hash="config_hash_001",
            data_snapshot_hash="data_hash_001",
            gate_criteria_hash="gate_hash_001",
            oos_draw_index=1,
            shared_oos_window_id="shared_oos_001",
            b4_result=self.b4_result,
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adj_fp_001",
        )
        
        import json
        payload = json.loads(report.report_payload_json)
        self.assertGreaterEqual(payload["liquidation_impact"], 0.0)
    
    def test_missing_required_b4_metadata_rejected(self):
        """Missing required B4 metadata is hard rejected."""
        # Use model_construct to bypass Pydantic validation and test builder's validation
        from pydantic import BaseModel
        
        invalid_b4 = EventBacktestResult.model_construct(
            result_id="result_003",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="",  # Empty string
            evaluation_mode="formal_backtest",
            backtest_start=date(2023, 1, 1),
            backtest_end=date(2023, 12, 31),
            order_intents=(),
            fills=(),
            rejected_orders=(),
            future_violations=(),
            final_portfolio=DailyPortfolioSnapshot(
                snapshot_id="final_003",
                snapshot_date=date(2023, 12, 31),
                cash=100000.0,
                positions=(),
                portfolio_value=100000.0,
            ),
            frozen_at=date(2024, 1, 1),
        )
        
        with self.assertRaises(ValueError) as ctx:
            self.builder.build_report(
            report_id="rpt_test",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
                strategy_config_hash="config_hash_001",
                data_snapshot_hash="data_hash_001",
                gate_criteria_hash="gate_hash_001",
                oos_draw_index=1,
                shared_oos_window_id="shared_oos_001",
                b4_result=invalid_b4,
                adjustment_mode="qfq",
                adjustment_snapshot_fingerprint="adj_fp_001",
            )
        self.assertIn("protocol_snapshot_id", str(ctx.exception))
    
    def test_report_hash_is_deterministic(self):
        """Same report payload generates same hash."""
        report1 = self.builder.build_report(
            report_id="rpt_test",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            strategy_config_hash="config_hash_001",
            data_snapshot_hash="data_hash_001",
            gate_criteria_hash="gate_hash_001",
            oos_draw_index=1,
            shared_oos_window_id="shared_oos_001",
            b4_result=self.b4_result,
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adj_fp_001",
        )
        
        report2 = self.builder.build_report(
            report_id="rpt_test",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            strategy_config_hash="config_hash_001",
            data_snapshot_hash="data_hash_001",
            gate_criteria_hash="gate_hash_001",
            oos_draw_index=1,
            shared_oos_window_id="shared_oos_001",
            b4_result=self.b4_result,
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adj_fp_001",
        )
        
        hash1 = self.builder.compute_report_hash(report1)
        hash2 = self.builder.compute_report_hash(report2)
        
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)  # SHA256 hex
    
    def test_report_disclaimer_blocks_profit_and_live_trading_claims(self):
        """Report disclaimer must block profit guarantee and live trading claims."""
        report = self.builder.build_report(
            report_id="rpt_test",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            strategy_config_hash="config_hash_001",
            data_snapshot_hash="data_hash_001",
            gate_criteria_hash="gate_hash_001",
            oos_draw_index=1,
            shared_oos_window_id="shared_oos_001",
            b4_result=self.b4_result,
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adj_fp_001",
        )
        
        import json
        payload = json.loads(report.report_payload_json)
        disclaimer_lower = payload["disclaimer"].lower()
        self.assertIn("not", disclaimer_lower)
        self.assertIn("profit", disclaimer_lower)
        self.assertIn("live trading", disclaimer_lower)
        self.assertIn("promotion", disclaimer_lower)
    
    def test_report_builder_creates_no_gate_or_promotion(self):
        """Report builder must not create Gate or promotion."""
        report = self.builder.build_report(
            report_id="rpt_test",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            strategy_config_hash="config_hash_001",
            data_snapshot_hash="data_hash_001",
            gate_criteria_hash="gate_hash_001",
            oos_draw_index=1,
            shared_oos_window_id="shared_oos_001",
            b4_result=self.b4_result,
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adj_fp_001",
        )
        
        # Report payload has no Gate fields
        import json
        payload = json.loads(report.report_payload_json)
        self.assertNotIn("gate_verdict", payload)
        self.assertNotIn("prototype_passed", payload)
        self.assertNotIn("promotion_id", payload)
    
    def test_report_records_missing_fields_explicitly(self):
        """Report must record missing base/stress/control results explicitly."""
        report = self.builder.build_report(
            report_id="rpt_test",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            strategy_config_hash="config_hash_001",
            data_snapshot_hash="data_hash_001",
            gate_criteria_hash="gate_hash_001",
            oos_draw_index=1,
            shared_oos_window_id="shared_oos_001",
            b4_result=self.b4_result,
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adj_fp_001",
        )
        
        import json
        payload = json.loads(report.report_payload_json)
        
        # Missing fields must be explicitly marked as not available
        self.assertEqual(payload["base_cost_result"], "not_available_from_b4_result")
        self.assertEqual(payload["stress_cost_result"], "not_available_from_b4_result")
        self.assertEqual(payload["control_comparison"], "not_available_from_b4_result")
        
        # B4 read trace summary must acknowledge source limitation
        self.assertIn("Orders:", payload["b4_read_trace_summary"])
        
        # Liquidation impact is 0.0 when B4 doesn't provide liquidation events
        self.assertEqual(payload["liquidation_impact"], 0.0)


if __name__ == "__main__":
    unittest.main()
