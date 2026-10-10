"""Synthetic report/Gate/explanation tests for same-draw Alpha evidence."""

import json
import unittest
from datetime import date
from unittest.mock import patch

from backend.services.b4_protocol_types import DailyPortfolioSnapshot, EventBacktestResult
from tests.test_b6_same_draw_result_contract import _identity_kwargs


def _same_draw_result():
    from backend.services.b5_oos_types import (
        B6SameDrawOOSResult,
        BaseCostResult,
        SameDrawExecutionIdentity,
        StressCostResult,
    )

    return B6SameDrawOOSResult(
        identity=SameDrawExecutionIdentity(**_identity_kwargs()),
        starting_nav=100000.0,
        ending_nav_base=101000.0,
        ending_nav_stress=100500.0,
        strategy_net_return_base=0.10,
        strategy_net_return_stress=0.05,
        benchmark_net_return_base=0.04,
        benchmark_net_return_stress=0.02,
        same_universe_control_return_base=0.03,
        same_universe_control_return_stress=0.01,
        base_cost_result=BaseCostResult(
            result_id="base_cost_synthetic_001",
            slippage_bps=1.0,
            commission_bps=2.0,
            impact_bps=1.0,
            total_cost_bps=4.0,
            assumptions_hash="4" * 64,
        ),
        stress_cost_result=StressCostResult(
            result_id="stress_cost_synthetic_001",
            slippage_bps=2.0,
            commission_bps=3.0,
            impact_bps=2.0,
            total_cost_bps=7.0,
            stress_multiplier=2.0,
            assumptions_hash="5" * 64,
        ),
    )


def _same_draw_v2_result(trace_suffix=()):
    from backend.services.b5_oos_types import B6SameDrawReadAudit

    result = _same_draw_result()
    audit = B6SameDrawReadAudit.from_trace(
        allowed_end=date(2026, 6, 30),
        trace=(
            {"operation": "get_bar", "requested_date": "2026-06-01"},
            {"operation": "get_status", "requested_date": "2026-06-01"},
        ) + tuple(trace_suffix),
    )
    identity = result.identity.model_copy(
        update={"result_schema_version": "b6_same_draw_oos_result.v2"}
    )
    return result.model_copy(update={"identity": identity, "read_audit": audit})


def _b4_result():
    return EventBacktestResult(
        result_id="b4_result_synthetic_001",
        strategy_revision_id="revision_synthetic_001",
        protocol_snapshot_id="protocol_synthetic_001",
        evaluation_mode="formal_backtest",
        backtest_start=date(2026, 4, 1),
        backtest_end=date(2026, 6, 30),
        order_intents=(),
        fills=(),
        rejected_orders=(),
        future_violations=(),
        final_portfolio=DailyPortfolioSnapshot(
            snapshot_id="portfolio_synthetic_001",
            snapshot_date=date(2026, 6, 30),
            cash=100000.0,
            positions=(),
            portfolio_value=100000.0,
        ),
        frozen_at=date(2026, 7, 1),
    )


def test_same_draw_revalidation_remains_in_prototype_gate():
    from backend.services.backtest_report_builder import BacktestReportBuilder
    from backend.services.prototype_gate_v2 import PrototypeGateV2
    from backend.services.prototype_gate_criteria_surface import (
        evaluate_effective_criteria,
    )

    report = BacktestReportBuilder().build_report(
        report_id="report_synthetic_001",
        strategy_revision_id="revision_synthetic_001",
        protocol_snapshot_id="protocol_synthetic_001",
        strategy_config_hash="strategy_config_synthetic_001",
        data_snapshot_hash="2" * 64,
        gate_criteria_hash="gate_criteria_synthetic_001",
        oos_draw_index=1,
        shared_oos_window_id="oos_window_synthetic_001",
        b4_result=_b4_result(),
        adjustment_mode="qfq",
        adjustment_snapshot_fingerprint="adjustment_synthetic_001",
        same_draw_result=_same_draw_v2_result(),
    )

    with patch(
        "backend.services.prototype_gate_v2.evaluate_effective_criteria",
        wraps=evaluate_effective_criteria,
    ) as delegated:
        gate_result = PrototypeGateV2().evaluate(
            report=report,
            gate_criteria_hash="gate_criteria_synthetic_001",
        )

    assert delegated.call_count == 1
    assert gate_result.verdict == "candidate_for_prototype_passed"

    payload = json.loads(report.report_payload_json)
    payload["same_draw_result"]["alpha_vs_benchmark_base"] = 0.99
    tampered_report = report.model_copy(
        update={"report_payload_json": json.dumps(payload, sort_keys=True)}
    )
    tampered_gate = PrototypeGateV2().evaluate(
        report=tampered_report,
        gate_criteria_hash="gate_criteria_synthetic_001",
    )
    assert tampered_gate.verdict == "rejected"
    assert any(
        "same-draw result invalid" in issue.lower()
        for issue in tampered_gate.blocking_issues
    )


class TestB6AlphaReportGateContract(unittest.TestCase):
    def test_same_draw_report_contains_identity_metrics_and_no_placeholders(self):
        from backend.services.backtest_report_builder import BacktestReportBuilder

        report = BacktestReportBuilder().build_report(
            report_id="report_synthetic_001",
            strategy_revision_id="revision_synthetic_001",
            protocol_snapshot_id="protocol_synthetic_001",
            strategy_config_hash="strategy_config_synthetic_001",
            data_snapshot_hash="2" * 64,
            gate_criteria_hash="gate_criteria_synthetic_001",
            oos_draw_index=1,
            shared_oos_window_id="oos_window_synthetic_001",
            b4_result=_b4_result(),
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adjustment_synthetic_001",
            same_draw_result=_same_draw_result(),
        )

        payload = json.loads(report.report_payload_json)
        self.assertEqual(payload["schema_version"], "b6_same_draw_oos_report.v1")
        self.assertEqual(payload["task_id"], "task_synthetic_001")
        self.assertEqual(payload["task_key"], "a" * 64)
        self.assertEqual(payload["b5_bundle_id"], "bundle_synthetic_001")
        self.assertEqual(payload["b5_bundle_manifest_sha256"], "b" * 64)
        self.assertEqual(
            payload["b4_lineage"]["event_result_sha256"],
            "d" * 64,
        )
        for field in (
            "strategy_net_return_base",
            "strategy_net_return_stress",
            "benchmark_net_return_base",
            "benchmark_net_return_stress",
            "same_universe_control_return_base",
            "same_universe_control_return_stress",
            "alpha_vs_benchmark_base",
            "alpha_vs_benchmark_stress",
            "alpha_vs_control_base",
            "alpha_vs_control_stress",
            "base_cost_result",
            "stress_cost_result",
        ):
            self.assertIn(field, payload["same_draw_result"])
        for field in (
            "formal_snapshot_id",
            "formal_snapshot_manifest_sha256",
            "membership_snapshot_id",
            "membership_manifest_sha256",
            "calendar_id",
            "calendar_manifest_sha256",
            "execution_input_hash",
        ):
            self.assertIn(field, payload["same_draw_result"]["identity"])
        self.assertAlmostEqual(
            payload["same_draw_result"]["alpha_vs_benchmark_base"],
            0.06,
        )
        self.assertNotIn("not_available_from_b4_result", json.dumps(payload))

    def test_same_draw_report_hash_changes_for_metric_or_lineage_change(self):
        from backend.services.backtest_report_builder import BacktestReportBuilder

        builder = BacktestReportBuilder()
        result = _same_draw_result()
        report = builder.build_report(
            report_id="report_synthetic_001",
            strategy_revision_id="revision_synthetic_001",
            protocol_snapshot_id="protocol_synthetic_001",
            strategy_config_hash="strategy_config_synthetic_001",
            data_snapshot_hash="2" * 64,
            gate_criteria_hash="gate_criteria_synthetic_001",
            oos_draw_index=1,
            shared_oos_window_id="oos_window_synthetic_001",
            b4_result=_b4_result(),
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adjustment_synthetic_001",
            same_draw_result=result,
        )
        metric_changed = result.model_copy(update={"strategy_net_return_base": 0.11})
        metric_report = builder.build_report(
            report_id="report_synthetic_001",
            strategy_revision_id="revision_synthetic_001",
            protocol_snapshot_id="protocol_synthetic_001",
            strategy_config_hash="strategy_config_synthetic_001",
            data_snapshot_hash="2" * 64,
            gate_criteria_hash="gate_criteria_synthetic_001",
            oos_draw_index=1,
            shared_oos_window_id="oos_window_synthetic_001",
            b4_result=_b4_result(),
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adjustment_synthetic_001",
            same_draw_result=metric_changed,
        )
        lineage_changed = result.identity.model_copy(update={"b4_manifest_sha256": "6" * 64})
        lineage_result = result.model_copy(update={"identity": lineage_changed})
        lineage_report = builder.build_report(
            report_id="report_synthetic_001",
            strategy_revision_id="revision_synthetic_001",
            protocol_snapshot_id="protocol_synthetic_001",
            strategy_config_hash="strategy_config_synthetic_001",
            data_snapshot_hash="2" * 64,
            gate_criteria_hash="gate_criteria_synthetic_001",
            oos_draw_index=1,
            shared_oos_window_id="oos_window_synthetic_001",
            b4_result=_b4_result(),
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adjustment_synthetic_001",
            same_draw_result=lineage_result,
        )

        self.assertNotEqual(report.report_hash, metric_report.report_hash)
        self.assertNotEqual(report.report_hash, lineage_report.report_hash)

    def test_report_hash_covers_read_audit_and_metrics(self):
        from backend.services.backtest_report_builder import BacktestReportBuilder

        builder = BacktestReportBuilder()
        result = _same_draw_v2_result()
        report = builder.build_report(
            report_id="report_synthetic_001",
            strategy_revision_id="revision_synthetic_001",
            protocol_snapshot_id="protocol_synthetic_001",
            strategy_config_hash="strategy_config_synthetic_001",
            data_snapshot_hash="2" * 64,
            gate_criteria_hash="gate_criteria_synthetic_001",
            oos_draw_index=1,
            shared_oos_window_id="oos_window_synthetic_001",
            b4_result=_b4_result(),
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adjustment_synthetic_001",
            same_draw_result=result,
        )
        payload = json.loads(report.report_payload_json)
        self.assertEqual(payload["schema_version"], "b6_same_draw_oos_report.v2")
        self.assertIn("read_audit", payload["same_draw_result"])

        changed_audit = _same_draw_v2_result(
            ({"operation": "get_liquidity", "requested_date": "2026-06-02"},)
        )
        changed_report = builder.build_report(
            report_id="report_synthetic_001",
            strategy_revision_id="revision_synthetic_001",
            protocol_snapshot_id="protocol_synthetic_001",
            strategy_config_hash="strategy_config_synthetic_001",
            data_snapshot_hash="2" * 64,
            gate_criteria_hash="gate_criteria_synthetic_001",
            oos_draw_index=1,
            shared_oos_window_id="oos_window_synthetic_001",
            b4_result=_b4_result(),
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adjustment_synthetic_001",
            same_draw_result=changed_audit,
        )
        self.assertNotEqual(report.report_hash, changed_report.report_hash)

    def test_v1_fixture_remains_readable_but_not_production_terminal(self):
        from backend.services.backtest_report_builder import BacktestReportBuilder

        report = BacktestReportBuilder().build_report(
            report_id="report_synthetic_001",
            strategy_revision_id="revision_synthetic_001",
            protocol_snapshot_id="protocol_synthetic_001",
            strategy_config_hash="strategy_config_synthetic_001",
            data_snapshot_hash="2" * 64,
            gate_criteria_hash="gate_criteria_synthetic_001",
            oos_draw_index=1,
            shared_oos_window_id="oos_window_synthetic_001",
            b4_result=_b4_result(),
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adjustment_synthetic_001",
            same_draw_result=_same_draw_result(),
        )
        payload = json.loads(report.report_payload_json)
        self.assertEqual(payload["schema_version"], "b6_same_draw_oos_report.v1")
        self.assertEqual(payload["result_schema_version"], "b6_same_draw_oos_result.v1")
        self.assertNotIn("read_audit", payload["same_draw_result"])
        with self.assertRaises(ValueError):
            _same_draw_result().assert_production_terminal_eligible()

    def test_report_rejects_mismatched_same_draw_window(self):
        from backend.services.backtest_report_builder import BacktestReportBuilder

        result = _same_draw_v2_result()
        mismatched_identity = result.identity.model_copy(update={"oos_end": date(2026, 7, 1)})
        mismatched_result = result.model_copy(update={"identity": mismatched_identity})

        with self.assertRaises(ValueError):
            BacktestReportBuilder().build_report(
                report_id="report_synthetic_001",
                strategy_revision_id="revision_synthetic_001",
                protocol_snapshot_id="protocol_synthetic_001",
                strategy_config_hash="strategy_config_synthetic_001",
                data_snapshot_hash="2" * 64,
                gate_criteria_hash="gate_criteria_synthetic_001",
                oos_draw_index=1,
                shared_oos_window_id="oos_window_synthetic_001",
                b4_result=_b4_result(),
                adjustment_mode="qfq",
                adjustment_snapshot_fingerprint="adjustment_synthetic_001",
                same_draw_result=mismatched_result,
            )

    def test_gate_reuses_same_draw_evidence_without_alpha_threshold(self):
        from backend.services.backtest_report_builder import BacktestReportBuilder
        from backend.services.prototype_gate_v2 import PrototypeGateV2

        report = BacktestReportBuilder().build_report(
            report_id="report_synthetic_001",
            strategy_revision_id="revision_synthetic_001",
            protocol_snapshot_id="protocol_synthetic_001",
            strategy_config_hash="strategy_config_synthetic_001",
            data_snapshot_hash="2" * 64,
            gate_criteria_hash="gate_criteria_synthetic_001",
            oos_draw_index=1,
            shared_oos_window_id="oos_window_synthetic_001",
            b4_result=_b4_result(),
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adjustment_synthetic_001",
            same_draw_result=_same_draw_result(),
        )

        gate_result = PrototypeGateV2().evaluate(
            report=report,
            gate_criteria_hash="gate_criteria_synthetic_001",
        )

        self.assertEqual(gate_result.verdict, "candidate_for_prototype_passed")
        checks = json.loads(gate_result.checks_json)
        self.assertAlmostEqual(
            checks["same_draw_result"]["alpha_vs_benchmark_base"], 0.06, places=12
        )
        self.assertEqual(checks["same_draw_result"]["alpha_vs_control_stress"], 0.04)
        self.assertNotIn("alpha_threshold", json.dumps(checks))
        self.assertNotIn("promotion", json.dumps(checks).lower())

    def test_gate_rejects_tampered_derived_alpha(self):
        from backend.services.backtest_report_builder import BacktestReportBuilder
        from backend.services.prototype_gate_v2 import PrototypeGateV2

        report = BacktestReportBuilder().build_report(
            report_id="report_synthetic_001",
            strategy_revision_id="revision_synthetic_001",
            protocol_snapshot_id="protocol_synthetic_001",
            strategy_config_hash="strategy_config_synthetic_001",
            data_snapshot_hash="2" * 64,
            gate_criteria_hash="gate_criteria_synthetic_001",
            oos_draw_index=1,
            shared_oos_window_id="oos_window_synthetic_001",
            b4_result=_b4_result(),
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adjustment_synthetic_001",
            same_draw_result=_same_draw_result(),
        )
        payload = json.loads(report.report_payload_json)
        payload["same_draw_result"]["alpha_vs_benchmark_base"] = 0.99
        tampered_report = report.model_copy(
            update={"report_payload_json": json.dumps(payload, sort_keys=True)}
        )

        gate_result = PrototypeGateV2().evaluate(
            report=tampered_report,
            gate_criteria_hash="gate_criteria_synthetic_001",
        )

        self.assertEqual(gate_result.verdict, "rejected")
        self.assertTrue(
            any(
                "same-draw result invalid" in issue.lower()
                for issue in gate_result.blocking_issues
            )
        )

    def test_gate_revalidates_v2_read_audit_and_rejects_tamper(self):
        from backend.services.backtest_report_builder import BacktestReportBuilder
        from backend.services.prototype_gate_v2 import PrototypeGateV2

        report = BacktestReportBuilder().build_report(
            report_id="report_synthetic_001",
            strategy_revision_id="revision_synthetic_001",
            protocol_snapshot_id="protocol_synthetic_001",
            strategy_config_hash="strategy_config_synthetic_001",
            data_snapshot_hash="2" * 64,
            gate_criteria_hash="gate_criteria_synthetic_001",
            oos_draw_index=1,
            shared_oos_window_id="oos_window_synthetic_001",
            b4_result=_b4_result(),
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adjustment_synthetic_001",
            same_draw_result=_same_draw_v2_result(),
        )
        self.assertEqual(
            json.loads(report.report_payload_json)["schema_version"],
            "b6_same_draw_oos_report.v2",
        )
        gate_result = PrototypeGateV2().evaluate(
            report=report,
            gate_criteria_hash="gate_criteria_synthetic_001",
        )
        self.assertEqual(gate_result.verdict, "candidate_for_prototype_passed")
        checks = json.loads(gate_result.checks_json)
        self.assertEqual(
            checks["same_draw_result"]["read_audit"]["owner"],
            "b6_same_draw_executor",
        )

        payload = json.loads(report.report_payload_json)
        payload["same_draw_result"]["read_audit"]["future_violation_count"] = 1
        tampered_report = report.model_copy(
            update={"report_payload_json": json.dumps(payload, sort_keys=True)}
        )
        tampered_gate = PrototypeGateV2().evaluate(
            report=tampered_report,
            gate_criteria_hash="gate_criteria_synthetic_001",
        )
        self.assertEqual(tampered_gate.verdict, "rejected")
        self.assertTrue(
            any("same-draw result invalid" in issue.lower() for issue in tampered_gate.blocking_issues)
        )

    def test_explanation_shows_market_control_strategy_and_arithmetic_alpha(self):
        from backend.services.backtest_report_builder import BacktestReportBuilder
        from backend.services.gate_explanation_builder import GateExplanationBuilder
        from backend.services.prototype_gate_v2 import PrototypeGateV2

        report = BacktestReportBuilder().build_report(
            report_id="report_synthetic_001",
            strategy_revision_id="revision_synthetic_001",
            protocol_snapshot_id="protocol_synthetic_001",
            strategy_config_hash="strategy_config_synthetic_001",
            data_snapshot_hash="2" * 64,
            gate_criteria_hash="gate_criteria_synthetic_001",
            oos_draw_index=1,
            shared_oos_window_id="oos_window_synthetic_001",
            b4_result=_b4_result(),
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adjustment_synthetic_001",
            same_draw_result=_same_draw_result(),
        )
        gate_result = PrototypeGateV2().evaluate(
            report=report,
            gate_criteria_hash="gate_criteria_synthetic_001",
        )

        explanation = GateExplanationBuilder().build_explanation(
            report_id=report.report_id,
            gate_result=gate_result,
        )
        summary = explanation.plain_summary.lower()
        for phrase in (
            "strategy",
            "market benchmark",
            "same-universe control",
            "arithmetic",
            "not causal",
        ):
            self.assertIn(phrase, summary)

    def test_explanation_shows_read_audit_verified_for_v2(self):
        from backend.services.backtest_report_builder import BacktestReportBuilder
        from backend.services.gate_explanation_builder import GateExplanationBuilder
        from backend.services.prototype_gate_v2 import PrototypeGateV2

        report = BacktestReportBuilder().build_report(
            report_id="report_synthetic_001",
            strategy_revision_id="revision_synthetic_001",
            protocol_snapshot_id="protocol_synthetic_001",
            strategy_config_hash="strategy_config_synthetic_001",
            data_snapshot_hash="2" * 64,
            gate_criteria_hash="gate_criteria_synthetic_001",
            oos_draw_index=1,
            shared_oos_window_id="oos_window_synthetic_001",
            b4_result=_b4_result(),
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="adjustment_synthetic_001",
            same_draw_result=_same_draw_v2_result(),
        )
        gate_result = PrototypeGateV2().evaluate(
            report=report,
            gate_criteria_hash="gate_criteria_synthetic_001",
        )
        explanation = GateExplanationBuilder().build_explanation(
            report_id=report.report_id,
            gate_result=gate_result,
        )
        self.assertIn("read audit verified", explanation.plain_summary.lower())


if __name__ == "__main__":
    unittest.main()
