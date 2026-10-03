from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from backend.services.b4_protocol_types import (
    EventBacktestResult,
    FillRecord,
    DailyPortfolioSnapshot,
    OrderIntentRecord,
)


ROOT = Path(__file__).resolve().parents[1]


def _event(*, conflicting: bool = False, fills: tuple[FillRecord, ...] | None = None) -> EventBacktestResult:
    day = date(2025, 6, 27)
    intents = (
        OrderIntentRecord(
            order_id="o-buy",
            symbol="000001.SZ",
            signal_date=date(2025, 6, 26),
            intent="buy",
            quantity=100,
        ),
        OrderIntentRecord(
            order_id="o-sell",
            symbol="600000.SH",
            signal_date=date(2025, 6, 26),
            intent="sell",
            quantity=100,
        ),
    )
    records = fills if fills is not None else (
        FillRecord(
            fill_id="f-buy",
            order_id="o-buy",
            symbol="000001.SZ",
            fill_date=day,
            fill_price=10.0,
            fill_quantity=100,
            execution_mode="simulated",
        ),
        FillRecord(
            fill_id="f-sell",
            order_id="o-sell",
            symbol="600000.SH",
            fill_date=day,
            fill_price=20.0,
            fill_quantity=100,
            execution_mode="simulated",
        ),
    )
    if conflicting:
        intents = (
            intents[0],
            OrderIntentRecord(
                order_id="o-sell",
                symbol="600000.SH",
                signal_date=day,
                intent="buy",
                quantity=100,
            ),
        )
    return EventBacktestResult(
        result_id="result-fixture",
        strategy_revision_id="revision-fixture",
        protocol_snapshot_id="protocol-fixture",
        evaluation_mode="formal_backtest",
        backtest_start=day,
        backtest_end=day,
        order_intents=intents,
        fills=records,
        rejected_orders=(),
        future_violations=(),
        final_portfolio=DailyPortfolioSnapshot(
            snapshot_id="snapshot-fixture",
            snapshot_date=day,
            cash=100000.0,
            positions=(),
            portfolio_value=100000.0,
        ),
        frozen_at=day,
    )


class V3B5CostTests(unittest.TestCase):
    def test_v3_b5_costs_rebinds_new_protocol_and_supplement_lineage(self):
        from backend.services.v3_b5_bundle import build_lineage

        lineage = build_lineage(ROOT)
        self.assertEqual(
            lineage["protocol_snapshot_id"],
            "8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe",
        )
        self.assertEqual(lineage["execution_supplement"]["id"], "185a6b8f03915dca")
        self.assertEqual(
            lineage["b4"]["artifact_id"], "cfa75e8b2a72bc76"
        )

    def test_successor_costs_publishes_and_verifies_in_temporary_root(self):
        from backend.services.v3_b5_costs import _load_b4, build_cost_artifact, verify_cost_artifact

        observation_dir = ROOT / "data/pit/v3_b5_ledger_observations" / "984864448e8aa4cd"
        _manifest, source_event = _load_b4(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            result = build_cost_artifact(ROOT, Path(tmp), observation_dir=observation_dir)
            self.assertEqual(result["status"], "published")
            artifact = Path(result["path"])
            verified = verify_cost_artifact(ROOT, artifact, observation_dir=observation_dir)
            self.assertEqual(verified["status"], "verified")
            manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["lineage"]["ledger_observation"], {
                "artifact_id": "984864448e8aa4cd",
                "manifest_sha256": "5c2679300bd9188bc8fbb3cca943805d2161cbacafce1e1a0f6b41b85658e66a",
                "observations_sha256": "55373c7e7c189663241f48d37b35505f99284d20c7eb07d85b7dec8a0208f842",
                "observation_count": 176,
            })
            self.assertEqual(manifest["lineage"]["execution_supplement"], {
                "id": "185a6b8f03915dca",
                "manifest_sha256": "df51e7a9efae3b6e915d8cac8210b431e07f3992fe83fb183e499e512bc9c895",
            })
            self.assertEqual(manifest["lineage"]["b4"], {
                "artifact_id": "cfa75e8b2a72bc76",
                "manifest_sha256": "b7db7cd296987ebd85ad199df16841a3a5d8a105892350e5a0bd091e4b5b6f89",
                "event_sha256": "8a8b5955ea6620c97e93914cdfdecd7006967bad0a297affb87a09af064d9a74",
            })
            self.assertEqual(manifest["fill_count"], 124)
            self.assertAlmostEqual(result["base"]["gross_traded_notional"], 2153566.0)
            self.assertAlmostEqual(result["base"]["commission"], 688.2647999999999, places=10)
            self.assertAlmostEqual(result["base"]["stamp"], 1043.8700000000003, places=10)
            self.assertEqual(result["base"]["transfer"], 0.0)
            self.assertEqual(result["base"]["slippage_amount"], 0.0)
            self.assertEqual(result["base"]["impact_amount"], 0.0)
            self.assertAlmostEqual(result["base"]["total_cost"], 1732.1348000000003, places=10)
            self.assertAlmostEqual(result["base"]["total_cost_bps"], 8.0431006062, places=9)
            self.assertAlmostEqual(result["stress"]["commission"], 1292.1790956000004, places=10)
            self.assertAlmostEqual(result["stress"]["stamp"], 1042.8261300000004, places=10)
            self.assertAlmostEqual(result["stress"]["slippage_amount"], 2153.5659999998907, places=9)
            self.assertEqual(result["stress"]["impact_amount"], 0.0)
            self.assertAlmostEqual(result["stress"]["total_cost"], 4488.5712255998915, places=9)
            self.assertAlmostEqual(result["stress"]["total_cost_bps"], 20.8425059905, places=9)
            self.assertGreater(result["stress"]["total_cost"], result["base"]["total_cost"])
            self.assertEqual(result["base"]["fill_ids"], result["stress"]["fill_ids"])
            self.assertEqual(result["base"]["fill_ids"], [fill.fill_id for fill in source_event.fills])
            self.assertEqual(len(result["base"]["fill_ids"]), 124)
            self.assertEqual(manifest["cost_assumptions_hash"], "69af3a2acdbb5b5c0ed59db5fdc6a4bc3108b19d8f814f0b85363d342522a386")
            self.assertEqual(manifest["producer_algorithm_hash"], manifest["producer_source_hashes"]["cost_service"]["sha256"])
            self.assertEqual(manifest["authorization_scope"], "v3_is_transaction_cost_only")
            self.assertTrue(manifest["not_authorized_for_b6_oos_gate_promotion_signal"])
            self.assertEqual(
                {path.name for path in artifact.iterdir()},
                {
                    "manifest.json", "manifest.json.sha256",
                    "base_transaction_cost.json", "base_transaction_cost.json.sha256",
                    "stress_transaction_cost.json", "stress_transaction_cost.json.sha256",
                },
            )

    def test_red_boundary_exists_and_computes_base_and_stress(self):
        from backend.services.v3_b5_costs import calculate_cost_results

        result = calculate_cost_results(_event())
        base = result["base"]
        stress = result["stress"]
        self.assertEqual(base["fill_ids"], ["f-buy", "f-sell"])
        self.assertEqual(stress["fill_ids"], base["fill_ids"])
        self.assertEqual(base["gross_traded_notional"], 3000.0)
        self.assertEqual(base["commission"], 10.0)
        self.assertEqual(base["stamp"], 2.0)
        self.assertEqual(base["transfer"], 0.0)
        self.assertEqual(base["slippage_amount"], 0.0)
        self.assertEqual(base["impact_amount"], 0.0)
        self.assertEqual(base["total_cost"], 12.0)
        self.assertAlmostEqual(stress["slippage_amount"], 3.0)
        self.assertGreater(stress["total_cost"], base["total_cost"])
        self.assertGreater(stress["total_cost_bps"], base["total_cost_bps"])
        self.assertEqual(stress["stress_slippage_bps"], 10.0)
        self.assertEqual(stress["impact_model"], "none")

    def test_minimum_commission_and_sell_stamp_are_explicit(self):
        from backend.services.v3_b5_costs import calculate_cost_results

        result = calculate_cost_results(_event())
        fills = result["base"]["per_fill"]
        self.assertEqual(fills[0]["commission"], 5.0)
        self.assertEqual(fills[0]["stamp"], 0.0)
        self.assertEqual(fills[1]["commission"], 5.0)
        self.assertEqual(fills[1]["stamp"], 2.0)

    def test_invalid_or_conflicting_fill_identity_fails_loud(self):
        from backend.services.v3_b5_costs import CostCalculationError, calculate_cost_results

        with self.assertRaises(CostCalculationError):
            calculate_cost_results(
                _event(
                    fills=(
                        FillRecord(
                            fill_id="f-buy",
                            order_id="o-buy",
                            symbol="600000.SH",
                            fill_date=date(2025, 6, 27),
                            fill_price=10.0,
                            fill_quantity=100,
                            execution_mode="simulated",
                        ),
                    )
                )
            )
        duplicate = _event(fills=(_event().fills[0], _event().fills[0]))
        with self.assertRaises(CostCalculationError):
            calculate_cost_results(duplicate)
        with self.assertRaises(CostCalculationError):
            calculate_cost_results(_event(fills=()))

        bad_price = FillRecord.model_construct(
            fill_id="f-bad", order_id="o-buy", symbol="000001.SZ",
            fill_date=date(2025, 6, 27), fill_price=float("nan"),
            fill_quantity=100, execution_mode="simulated",
        )
        with self.assertRaises(CostCalculationError):
            calculate_cost_results(_event(fills=(bad_price,)))

        hold_intent = OrderIntentRecord.model_construct(
            order_id="o-buy", symbol="000001.SZ", signal_date=date(2025, 6, 26),
            intent="hold", quantity=100,
        )
        hold_event = _event(fills=(_event().fills[0],))
        hold_event = hold_event.model_copy(update={"order_intents": (hold_intent,)})
        with self.assertRaises(CostCalculationError):
            calculate_cost_results(hold_event)

    def test_lineage_and_write_once_boundary_is_present(self):
        from backend.services.v3_b5_costs import build_cost_artifact, verify_cost_artifact

        with tempfile.TemporaryDirectory() as tmp:
            result = build_cost_artifact(ROOT, Path(tmp))
            self.assertIn(result["status"], {"published", "already_published"})
            artifact = Path(result["path"])
            self.assertTrue((artifact / "manifest.json").exists())
            self.assertTrue((artifact / "base_transaction_cost.json").exists())
            self.assertTrue((artifact / "stress_transaction_cost.json").exists())
            self.assertTrue((artifact / "manifest.json.sha256").exists())
            self.assertTrue((artifact / "base_transaction_cost.json.sha256").exists())
            self.assertTrue((artifact / "stress_transaction_cost.json.sha256").exists())
            self.assertTrue(result["not_authorized_for_b6_oos_gate_promotion_signal"])
            verified = verify_cost_artifact(ROOT, artifact)
            self.assertEqual(verified["status"], "verified")
            before = {
                path.name: (path.read_bytes(), path.stat().st_mtime_ns)
                for path in artifact.iterdir()
            }
            artifact_mtime = artifact.stat().st_mtime_ns
            reused = build_cost_artifact(ROOT, Path(tmp))
            self.assertEqual(reused["status"], "already_published")
            self.assertEqual(artifact.stat().st_mtime_ns, artifact_mtime)
            self.assertEqual(
                {
                    path.name: (path.read_bytes(), path.stat().st_mtime_ns)
                    for path in artifact.iterdir()
                },
                before,
            )
            base = artifact / "base_transaction_cost.json"
            original_base = base.read_bytes()
            base.write_bytes(base.read_bytes() + b" ")
            with self.assertRaises(ValueError):
                verify_cost_artifact(ROOT, artifact)
            with self.assertRaises(ValueError):
                build_cost_artifact(ROOT, Path(tmp))
            base.write_bytes(original_base)
            base_sidecar = artifact / "base_transaction_cost.json.sha256"
            original_sidecar = base_sidecar.read_bytes()
            base_sidecar.write_bytes(b"0" * 64 + b"  base_transaction_cost.json\n")
            with self.assertRaises(ValueError):
                verify_cost_artifact(ROOT, artifact)
            base_sidecar.write_bytes(original_sidecar)

    def test_atomic_write_failure_leaves_no_final_target_and_preserves_staging(self):
        from backend.services.v3_b5_costs import _write_once

        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            target = output_root / "artifact-id"
            files = {"one": b"one", "two": b"two"}
            real_replace = os.replace

            def fail_on_second_file(source, destination):
                if Path(destination).name == "two":
                    raise OSError("injected atomic rename failure")
                return real_replace(source, destination)

            with patch("backend.services.v3_b5_costs.os.replace", side_effect=fail_on_second_file):
                with self.assertRaises(OSError):
                    _write_once(target, files)

            self.assertFalse(target.exists())
            staging_dirs = list(output_root.glob(".artifact-id.staging-*"))
            self.assertEqual(len(staging_dirs), 1)
            self.assertTrue((staging_dirs[0] / "one").exists())
            self.assertTrue(any(staging_dirs[0].iterdir()))

    def test_non_root_source_is_rejected_before_any_output_write(self):
        from backend.services.v3_b5_costs import build_cost_artifact

        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "costs"
            with self.assertRaises(ValueError):
                build_cost_artifact(Path(tmp) / "not-the-repository", output_root)
            self.assertFalse(output_root.exists())


if __name__ == "__main__":
    unittest.main()
