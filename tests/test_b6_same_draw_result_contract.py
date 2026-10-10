"""Synthetic same-draw B6 result contract tests."""

import unittest
from datetime import date
import hashlib
import json


def _identity_kwargs() -> dict:
    return {
        "task_id": "task_synthetic_001",
        "task_key": "a" * 64,
        "strategy_revision_id": "revision_synthetic_001",
        "protocol_snapshot_id": "protocol_synthetic_001",
        "b5_bundle_id": "bundle_synthetic_001",
        "b5_bundle_manifest_sha256": "b" * 64,
        "b4_artifact_id": "b4_synthetic_001",
        "b4_manifest_sha256": "c" * 64,
        "b4_event_result_sha256": "d" * 64,
        "formal_snapshot_id": "formal_synthetic_001",
        "formal_snapshot_manifest_sha256": "e" * 64,
        "membership_snapshot_id": "membership_synthetic_001",
        "membership_manifest_sha256": "f" * 64,
        "calendar_id": "calendar_synthetic_001",
        "calendar_manifest_sha256": "1" * 64,
        "data_snapshot_hash": "2" * 64,
        "execution_input_hash": "3" * 64,
        "shared_oos_window_id": "oos_window_synthetic_001",
        "oos_start": date(2026, 4, 1),
        "oos_end": date(2026, 6, 30),
        "result_schema_version": "b6_same_draw_oos_result.v1",
    }


def _same_draw_result_payload() -> dict:
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
    ).model_dump(mode="json")


class TestB6SameDrawResultContract(unittest.TestCase):
    def test_same_draw_alpha_is_recomputed_from_six_returns(self):
        from backend.services.b5_oos_types import (
            B6SameDrawOOSResult,
            BaseCostResult,
            SameDrawExecutionIdentity,
            StressCostResult,
        )

        result = B6SameDrawOOSResult(
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

        self.assertAlmostEqual(result.alpha_vs_benchmark_base, 0.06)
        self.assertAlmostEqual(result.alpha_vs_benchmark_stress, 0.03)
        self.assertAlmostEqual(result.alpha_vs_control_base, 0.07)
        self.assertAlmostEqual(result.alpha_vs_control_stress, 0.04)

    def test_missing_return_series_is_rejected(self):
        from backend.services.b5_oos_types import B6SameDrawOOSResult

        payload = _same_draw_result_payload()
        payload.pop("benchmark_net_return_stress")

        with self.assertRaises(ValueError):
            B6SameDrawOOSResult.model_validate(payload)

    def test_nonfinite_or_nonpositive_nav_is_rejected(self):
        from backend.services.b5_oos_types import (
            B6SameDrawOOSResult,
            BaseCostResult,
            SameDrawExecutionIdentity,
            StressCostResult,
        )

        with self.assertRaises(ValueError):
            B6SameDrawOOSResult(
                identity=SameDrawExecutionIdentity(**_identity_kwargs()),
                starting_nav=float("nan"),
                ending_nav_base=100000.0,
                ending_nav_stress=100000.0,
                strategy_net_return_base=0.1,
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

    def test_stress_cost_must_not_be_weaker_than_base(self):
        from backend.services.b5_oos_types import (
            B6SameDrawOOSResult,
            BaseCostResult,
            SameDrawExecutionIdentity,
            StressCostResult,
        )

        with self.assertRaises(ValueError):
            B6SameDrawOOSResult(
                identity=SameDrawExecutionIdentity(**_identity_kwargs()),
                starting_nav=100000.0,
                ending_nav_base=100000.0,
                ending_nav_stress=99000.0,
                strategy_net_return_base=0.1,
                strategy_net_return_stress=0.05,
                benchmark_net_return_base=0.04,
                benchmark_net_return_stress=0.02,
                same_universe_control_return_base=0.03,
                same_universe_control_return_stress=0.01,
                base_cost_result=BaseCostResult(
                    result_id="base_cost_synthetic_001",
                    slippage_bps=2.0,
                    commission_bps=2.0,
                    impact_bps=2.0,
                    total_cost_bps=6.0,
                    assumptions_hash="4" * 64,
                ),
                stress_cost_result=StressCostResult(
                    result_id="stress_cost_synthetic_001",
                    slippage_bps=1.0,
                    commission_bps=1.0,
                    impact_bps=1.0,
                    total_cost_bps=3.0,
                    stress_multiplier=2.0,
                    assumptions_hash="5" * 64,
                ),
            )

    def test_alpha_values_are_not_caller_supplied_fields(self):
        from backend.services.b5_oos_types import B6SameDrawOOSResult

        payload = {
            "identity": _identity_kwargs(),
            "starting_nav": 100000.0,
            "ending_nav_base": 100000.0,
            "ending_nav_stress": 99000.0,
            "strategy_net_return_base": 0.1,
            "strategy_net_return_stress": 0.05,
            "benchmark_net_return_base": 0.04,
            "benchmark_net_return_stress": 0.02,
            "same_universe_control_return_base": 0.03,
            "same_universe_control_return_stress": 0.01,
            "base_cost_result": {
                "result_id": "base_cost_synthetic_001",
                "slippage_bps": 1.0,
                "commission_bps": 2.0,
                "impact_bps": 1.0,
                "total_cost_bps": 4.0,
                "assumptions_hash": "4" * 64,
            },
            "stress_cost_result": {
                "result_id": "stress_cost_synthetic_001",
                "slippage_bps": 2.0,
                "commission_bps": 3.0,
                "impact_bps": 2.0,
                "total_cost_bps": 7.0,
                "stress_multiplier": 2.0,
                "assumptions_hash": "5" * 64,
            },
            "alpha_vs_benchmark_base": 999.0,
        }

        with self.assertRaises(ValueError):
            B6SameDrawOOSResult.model_validate(payload)

    def test_result_payload_contains_derived_alpha_and_identity(self):
        from backend.services.b5_oos_types import (
            B6SameDrawOOSResult,
            BaseCostResult,
            SameDrawExecutionIdentity,
            StressCostResult,
        )

        result = B6SameDrawOOSResult(
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

        payload = result.to_payload()
        self.assertEqual(payload["schema_version"], "b6_same_draw_oos_result.v1")
        self.assertEqual(payload["identity"]["b5_bundle_id"], "bundle_synthetic_001")
        self.assertAlmostEqual(payload["alpha_vs_benchmark_base"], 0.06)
        self.assertAlmostEqual(payload["alpha_vs_control_stress"], 0.04)


class TestB6SameDrawResultV2(unittest.TestCase):
    @staticmethod
    def _audit_payload():
        from backend.services.b5_oos_types import B6SameDrawReadAudit

        return B6SameDrawReadAudit.from_trace(
            allowed_end=date(2026, 6, 30),
            trace=(
                {"operation": "get_bar", "requested_date": "2026-06-01"},
                {"operation": "get_status", "requested_date": "2026-06-01"},
            ),
        ).model_dump(mode="json")

    def _v2_payload(self):
        payload = _same_draw_result_payload()
        payload["identity"]["result_schema_version"] = "b6_same_draw_oos_result.v2"
        payload["read_audit"] = self._audit_payload()
        return payload

    def test_v2_requires_verified_read_audit(self):
        from backend.services.b5_oos_types import B6SameDrawOOSResult

        payload = _same_draw_result_payload()
        payload["identity"]["result_schema_version"] = "b6_same_draw_oos_result.v2"
        with self.assertRaises(ValueError):
            B6SameDrawOOSResult.model_validate(payload)

        result = B6SameDrawOOSResult.model_validate(self._v2_payload())
        self.assertEqual(result.identity.result_schema_version, "b6_same_draw_oos_result.v2")
        self.assertEqual(result.read_audit.schema_version, "b6_same_draw_read_audit.v1")
        result.assert_production_terminal_eligible()

        bad_cost = self._v2_payload()
        bad_cost["base_cost_result"]["assumptions_hash"] = "not-a-sha"
        with self.assertRaises(ValueError):
            B6SameDrawOOSResult.model_validate(bad_cost)

    def test_audit_bounds_owner_counts_and_trace_hash_are_strict(self):
        from backend.services.b5_oos_types import B6SameDrawReadAudit

        valid = self._audit_payload()
        self.assertEqual(valid["read_count"], 2)
        self.assertEqual(valid["operation_counts"], {"get_bar": 1, "get_status": 1})
        expected_trace_hash = hashlib.sha256(
            json.dumps(
                [
                    {"operation": "get_bar", "requested_date": "2026-06-01"},
                    {"operation": "get_status", "requested_date": "2026-06-01"},
                ],
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(valid["canonical_trace_sha256"], expected_trace_hash)
        audit = B6SameDrawReadAudit.model_validate(valid)
        with self.assertRaises(ValueError):
            audit.owner = "untrusted_caller"
        for field, value in (
            ("owner", "untrusted_caller"),
            ("future_violation_count", 1),
            ("canonical_trace_sha256", "A" * 64),
            ("read_count", 1),
        ):
            with self.subTest(field=field):
                tampered = dict(valid)
                tampered[field] = value
                with self.assertRaises(ValueError):
                    B6SameDrawReadAudit.model_validate(tampered)

        future = dict(valid)
        future["max_requested_date"] = "2026-07-01"
        with self.assertRaises(ValueError):
            B6SameDrawReadAudit.model_validate(future)

        negative = dict(valid)
        negative["operation_counts"] = {"get_bar": -1, "get_status": 3}
        with self.assertRaises(ValueError):
            B6SameDrawReadAudit.model_validate(negative)

        extra = dict(valid)
        extra["raw_trace"] = []
        with self.assertRaises(ValueError):
            B6SameDrawReadAudit.model_validate(extra)

    def test_v1_fixture_remains_readable_but_not_production_terminal(self):
        from backend.services.b5_oos_types import B6SameDrawOOSResult

        legacy = B6SameDrawOOSResult.model_validate(_same_draw_result_payload())
        payload = legacy.to_payload()
        self.assertEqual(payload["schema_version"], "b6_same_draw_oos_result.v1")
        self.assertNotIn("read_audit", payload)
        self.assertIsNone(legacy.read_audit)
        with self.assertRaises(ValueError):
            legacy.assert_production_terminal_eligible()


if __name__ == "__main__":
    unittest.main()
