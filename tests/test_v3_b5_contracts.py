from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_INVENTORY = ROOT / "data/pit/v3_b5_source_inventories/2fe8321a5f644b9b"
RESULT_TYPES = (
    "base_transaction_cost",
    "stress_transaction_cost",
    "benchmark_comparison",
    "same_universe_control_comparison",
)


class V3B5ContractTests(unittest.TestCase):
    def _lineage(self):
        from backend.services.v3_b5_bundle import build_lineage

        return build_lineage(ROOT, source_inventory_dir=SOURCE_INVENTORY)

    def _results(self, lineage=None):
        from backend.services.v3_b5_types import build_result_payload

        lineage = lineage or self._lineage()
        results = {
            "base_transaction_cost": build_result_payload(
                "base_transaction_cost", lineage=lineage,
                result={"gross_traded_notional": 1000.0, "total_cost": 8.0},
                producer_algorithm_hash="1" * 64,
                cost_assumptions_hash="6" * 64,
            ),
            "stress_transaction_cost": build_result_payload(
                "stress_transaction_cost", lineage=lineage,
                result={"gross_traded_notional": 1000.0, "total_cost": 12.0},
                producer_algorithm_hash="2" * 64,
                cost_assumptions_hash="7" * 64,
            ),
            "benchmark_comparison": build_result_payload(
                "benchmark_comparison", lineage=lineage,
                result={"daily_series_hash": "3" * 64},
                producer_algorithm_hash="3" * 64,
                daily_observation_hash="4" * 64,
                cost_assumptions_hash="6" * 64,
            ),
            "same_universe_control_comparison": build_result_payload(
                "same_universe_control_comparison", lineage=lineage,
                result={"daily_series_hash": "5" * 64},
                producer_algorithm_hash="5" * 64,
                daily_observation_hash="4" * 64,
                cost_assumptions_hash="6" * 64,
            ),
        }
        return results

    def test_exact_lineage_and_valid_fixture_bundle(self):
        from backend.services.v3_b5_bundle import publish_b5_bundle, verify_b5_bundle

        lineage = self._lineage()
        results = self._results(lineage)
        self.assertEqual(lineage["template"]["template_id"], "relative_strength_rotation_shsz_sw2021_v3")
        self.assertEqual(lineage["strategy_revision_id"], "6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc")
        self.assertEqual(lineage["source_inventory"]["artifact_id"], "2fe8321a5f644b9b")
        self.assertEqual(lineage["source_inventory"]["manifest_sha256"], "e23b94ac7294003a9b28db28f270bf2f19eaff40da9a03507adda87aad219a2c")
        self.assertEqual(lineage["is_range"], {"start": "2025-06-27", "end": "2026-03-19"})
        self.assertTrue(all(results[key]["canonical_payload_sha256"] for key in RESULT_TYPES))

        with tempfile.TemporaryDirectory() as tmp:
            first = publish_b5_bundle(ROOT, results, Path(tmp))
            self.assertEqual(first["status"], "published")
            bundle_dir = Path(first["path"])
            self.assertFalse(list(bundle_dir.rglob("*.parquet")))
            verified = verify_b5_bundle(ROOT, bundle_dir, source_inventory_dir=SOURCE_INVENTORY)
            self.assertEqual(verified["status"], "verified")
            self.assertEqual(verified["bundle_id"], first["bundle_id"])

    def test_missing_result_is_not_authorized_and_does_not_write(self):
        from backend.services.v3_b5_bundle import publish_b5_bundle

        results = self._results()
        del results["benchmark_comparison"]
        with tempfile.TemporaryDirectory() as tmp:
            result = publish_b5_bundle(ROOT, results, Path(tmp))
            self.assertEqual(result["status"], "not_authorized")
            self.assertIn("benchmark_comparison", result["missing_or_invalid"])
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_invalid_status_and_missing_observation_are_not_authorized(self):
        from backend.services.v3_b5_bundle import publish_b5_bundle

        results = self._results()
        results["stress_transaction_cost"]["status"] = "invalid"
        results["benchmark_comparison"]["daily_observation_hash"] = None
        with tempfile.TemporaryDirectory() as tmp:
            result = publish_b5_bundle(ROOT, results, Path(tmp))
            self.assertEqual(result["status"], "not_authorized")
            self.assertIn("stress_transaction_cost", result["missing_or_invalid"])
            self.assertIn("benchmark_comparison", result["missing_or_invalid"])

    def test_tampered_source_is_not_authorized(self):
        from backend.services.v3_b5_bundle import publish_b5_bundle

        results = self._results()
        with tempfile.TemporaryDirectory() as tmp:
            source_copy = Path(tmp) / "source"
            shutil.copytree(SOURCE_INVENTORY, source_copy)
            manifest = source_copy / "manifest.json"
            manifest.write_bytes(manifest.read_bytes() + b" ")
            output = Path(tmp) / "out"
            result = publish_b5_bundle(ROOT, results, output, source_inventory_dir=source_copy)
            self.assertEqual(result["status"], "not_authorized")
            self.assertTrue(any("source_inventory" in item for item in result["missing_or_invalid"]))
            self.assertFalse(output.exists())

    def test_lineage_tamper_is_rejected(self):
        from backend.services.v3_b5_bundle import publish_b5_bundle

        lineage = self._lineage()
        lineage["b4"]["event_sha256"] = "f" * 64
        results = self._results(lineage)
        with tempfile.TemporaryDirectory() as tmp:
            result = publish_b5_bundle(ROOT, results, Path(tmp))
            self.assertEqual(result["status"], "not_authorized")
            self.assertTrue(any("lineage" in item for item in result["missing_or_invalid"]))

    def test_exact_reuse_sidecar_mismatch_and_same_id_conflict(self):
        from backend.services.v3_b5_bundle import publish_b5_bundle, verify_b5_bundle

        results = self._results()
        with tempfile.TemporaryDirectory() as tmp:
            first = publish_b5_bundle(ROOT, results, Path(tmp))
            second = publish_b5_bundle(ROOT, results, Path(tmp))
            self.assertEqual(second["status"], "already_published")
            bundle_dir = Path(first["path"])
            sidecar = bundle_dir / "manifest.json.sha256"
            sidecar.write_text("0" * 64 + "  manifest.json\n", encoding="utf-8")
            self.assertEqual(verify_b5_bundle(ROOT, bundle_dir, source_inventory_dir=SOURCE_INVENTORY)["status"], "invalid")
            with self.assertRaisesRegex(ValueError, "write-once"):
                publish_b5_bundle(ROOT, results, Path(tmp))

    def test_payload_id_is_deterministic_and_extra_fields_rejected(self):
        from backend.services.v3_b5_types import build_result_payload, validate_result_payload

        lineage = self._lineage()
        first = build_result_payload(
            "base_transaction_cost", lineage=lineage,
            result={"gross_traded_notional": 1000.0, "total_cost": 8.0},
            producer_algorithm_hash="1" * 64,
            cost_assumptions_hash="6" * 64,
        )
        second = build_result_payload(
            "base_transaction_cost", lineage=lineage,
            result={"gross_traded_notional": 1000.0, "total_cost": 8.0},
            producer_algorithm_hash="1" * 64,
            cost_assumptions_hash="6" * 64,
        )
        self.assertEqual(first["payload_id"], second["payload_id"])
        self.assertEqual(first["canonical_payload_sha256"], second["canonical_payload_sha256"])
        tampered = dict(first)
        tampered["unexpected"] = True
        with self.assertRaises(ValueError):
            validate_result_payload(tampered, "base_transaction_cost", lineage)

    def test_cost_assumptions_hash_is_required(self):
        from backend.services.v3_b5_types import build_result_payload

        with self.assertRaises(TypeError):
            build_result_payload(
                "base_transaction_cost", lineage=self._lineage(),
                result={"gross_traded_notional": 1000.0, "total_cost": 8.0},
                producer_algorithm_hash="1" * 64,
            )


if __name__ == "__main__":
    unittest.main()
