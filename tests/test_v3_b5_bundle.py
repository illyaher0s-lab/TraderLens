from __future__ import annotations

import ast
import inspect
import json
import os
import shutil
import tempfile
import textwrap
import unittest
from unittest.mock import patch
from pathlib import Path

from backend.services.v3_b5_bundle import publish_b5_bundle
from backend.services.v3_b5_types import canonical_json, sha256_bytes


ROOT = Path(os.environ.get("TRADERLENS_SOURCE_ROOT", Path(__file__).resolve().parents[1])).resolve()


def _real_results() -> dict[str, dict]:
    paths = {
        "base_transaction_cost": ROOT / "data/pit/v3_b5_costs/e405b900f971877f/base_transaction_cost.json",
        "stress_transaction_cost": ROOT / "data/pit/v3_b5_costs/e405b900f971877f/stress_transaction_cost.json",
        "benchmark_comparison": ROOT / "data/pit/v3_b5_comparisons/d3a78447920b611a/benchmark_comparison.json",
        "same_universe_control_comparison": ROOT / "data/pit/v3_b5_comparisons/d3a78447920b611a/same_universe_control.json",
    }
    return {result_type: json.loads(path.read_text(encoding="utf-8")) for result_type, path in paths.items()}


def _copy_source_dirs(temp_root: Path) -> tuple[Path, Path]:
    temp_root.mkdir(parents=True, exist_ok=True)
    cost_dir = temp_root / "costs"
    comparison_dir = temp_root / "comparisons"
    shutil.copytree(ROOT / "data/pit/v3_b5_costs/e405b900f971877f", cost_dir)
    shutil.copytree(ROOT / "data/pit/v3_b5_comparisons/d3a78447920b611a", comparison_dir)
    return cost_dir, comparison_dir


def _rewrite_payload(path: Path, mutate) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    draft = {key: value for key, value in payload.items() if key not in {"payload_id", "canonical_payload_sha256"}}
    digest = sha256_bytes(canonical_json(draft))
    payload["payload_id"] = digest[:16]
    payload["canonical_payload_sha256"] = digest
    raw = canonical_json(payload)
    path.write_bytes(raw)
    path.with_name(path.name + ".sha256").write_text(f"{sha256_bytes(raw)}  {path.name}\n", encoding="utf-8")


def _synthetic_bundle_inputs() -> tuple[dict, dict[str, dict]]:
    from backend.services.v3_b5_types import build_result_payload

    lineage = {"synthetic_lineage": {"source": "temporary"}}
    return lineage, {
        "base_transaction_cost": build_result_payload(
            "base_transaction_cost",
            lineage=lineage,
            result={"gross_traded_notional": 1000.0, "total_cost": 8.0},
            producer_algorithm_hash="1" * 64,
            cost_assumptions_hash="6" * 64,
        ),
        "stress_transaction_cost": build_result_payload(
            "stress_transaction_cost",
            lineage=lineage,
            result={"gross_traded_notional": 1000.0, "total_cost": 12.0},
            producer_algorithm_hash="2" * 64,
            cost_assumptions_hash="7" * 64,
        ),
        "benchmark_comparison": build_result_payload(
            "benchmark_comparison",
            lineage=lineage,
            result={"daily_series_hash": "3" * 64},
            producer_algorithm_hash="3" * 64,
            daily_observation_hash="4" * 64,
            cost_assumptions_hash="6" * 64,
        ),
        "same_universe_control_comparison": build_result_payload(
            "same_universe_control_comparison",
            lineage=lineage,
            result={"daily_series_hash": "5" * 64},
            producer_algorithm_hash="5" * 64,
            daily_observation_hash="4" * 64,
            cost_assumptions_hash="6" * 64,
        ),
    }


def _publish_synthetic_bundle(temp_root: Path) -> tuple[Path, dict, dict[str, dict]]:
    lineage, results = _synthetic_bundle_inputs()
    output_root = temp_root / "bundles"
    with patch("backend.services.v3_b5_bundle.build_lineage", return_value=lineage):
        published = publish_b5_bundle(temp_root, results, output_root)
    return Path(published["path"]), published, results


class TestV3B5Bundle(unittest.TestCase):
    def test_cost_public_shapes_and_manifest_fill_count_characterization(self) -> None:
        from backend.services.v3_b5_costs import build_cost_artifact, verify_cost_artifact

        def return_dict_keys(function) -> set[str]:
            tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
            returns = [
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)
            ]
            self.assertEqual(len(returns), 1)
            keys = {key.value for key in returns[0].keys if isinstance(key, ast.Constant)}
            self.assertEqual(len(keys), len(returns[0].keys))
            return keys

        self.assertEqual(
            return_dict_keys(build_cost_artifact),
            {
                "status", "artifact_id", "path", "manifest_sha256",
                "not_authorized_for_b6_oos_gate_promotion_signal", "base", "stress",
            },
        )
        self.assertEqual(
            return_dict_keys(verify_cost_artifact),
            {
                "status", "artifact_id", "path", "manifest_sha256", "base_sha256",
                "stress_sha256", "fill_count", "gross_traded_notional", "base_total_cost",
                "stress_total_cost", "base_total_cost_bps", "stress_total_cost_bps",
            },
        )

        builder_source = inspect.getsource(build_cost_artifact)
        self.assertIn('"fill_count": len(event.fills)', builder_source)

    def _assert_current_ledger_lineage(self, lineage: dict, supplement_manifest: dict) -> None:
        expected_keys = {
            "b4",
            "trading_supplement",
            "protocol",
            "formal_snapshot",
            "scope",
            "source_inventory",
            "membership",
            "calendar",
            "feasibility_design_evidence",
            "b4_manifest_declared",
            "formal_payload_semantic_hash",
            "supplement_status",
            "supplement_declared_source_bindings",
        }
        self.assertEqual(set(lineage), expected_keys)
        self.assertEqual(lineage["protocol"], {
            "snapshot_id": "8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe",
            "strategy_revision_id": "6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc",
            "payload_sha256": "2872d63578d66e6dfc02fd767c4061fd3e291bcb9bbd65f0f2409a4482f6e2a3",
        })
        self.assertEqual(lineage["trading_supplement"], {
            "supplement_id": "185a6b8f03915dca",
            "manifest_sha256": "df51e7a9efae3b6e915d8cac8210b431e07f3992fe83fb183e499e512bc9c895",
        })
        self.assertEqual(lineage["b4"], {
            "artifact_id": "cfa75e8b2a72bc76",
            "manifest_sha256": "b7db7cd296987ebd85ad199df16841a3a5d8a105892350e5a0bd091e4b5b6f89",
            "event_sha256": "8a8b5955ea6620c97e93914cdfdecd7006967bad0a297affb87a09af064d9a74",
        })
        self.assertEqual(lineage["supplement_status"], "immutable_predecessor_manifest_verified")
        self.assertEqual(
            lineage["supplement_declared_source_bindings"],
            supplement_manifest["source_bindings"],
        )
        self.assertEqual(supplement_manifest["criteria"]["envelope_hash"], "94da0dda30af75d663a7d28deb0a15d64a4e068586a1295f3b4f52203a8c4738")

    def _assert_current_flat_lineage(self, lineage: dict, extra_keys: set[str]) -> None:
        from backend.services.v3_b5_bundle import build_lineage

        expected_base = build_lineage(ROOT)
        self.assertEqual(set(lineage), set(expected_base) | extra_keys)
        for key, value in expected_base.items():
            self.assertEqual(lineage[key], value)

    def test_current_lineage_schema_characterization(self) -> None:
        from backend.services.v3_b5_bundle import build_lineage
        from backend.services.v3_b5_costs import _lineage as build_cost_lineage
        from scripts.publish_v3_b5_ledger_observations import (
            _load_b4,
            _load_formal_manifest,
            _load_immutable_trading_supplement,
            _load_lineage,
            _load_protocol,
        )

        protocol, protocol_sha = _load_protocol()
        b4_manifest, _event, b4_sha, event_sha = _load_b4()
        formal_manifest, formal_payload, formal_sha = _load_formal_manifest()
        supplement = _load_immutable_trading_supplement()
        ledger_lineage = _load_lineage(
            protocol,
            protocol_sha,
            b4_manifest,
            b4_sha,
            event_sha,
            supplement,
            formal_payload,
            formal_sha,
        )
        supplement_manifest = supplement["manifest"]
        observation = {
            "artifact_id": "characterization-observation",
            "manifest_sha256": "a" * 64,
            "observations_sha256": "b" * 64,
        }
        cost_lineage = build_cost_lineage(ROOT, observation)
        base_lineage = build_lineage(ROOT)
        comparison_lineage = {
            **base_lineage,
            "cost_artifact": {
                "artifact_id": "characterization-cost",
                "manifest_sha256": "c" * 64,
                "cost_assumptions_hash": "d" * 64,
            },
            "ledger_observation": observation,
            "comparison_contract": {
                "schema_kind": "theoretical_fractional_comparison_index",
                "initial_nav": 100000.0,
                "base_cost_bps": 0.0,
                "stress_cost_bps": 10.0,
            },
            "lifecycle_successor": {},
            "historical_coverage": {},
            "missing_mark_diagnostic": {},
        }

        self._assert_current_ledger_lineage(ledger_lineage, supplement_manifest)
        self._assert_current_flat_lineage(cost_lineage, {"ledger_observation", "daily_observation_hash"})
        self._assert_current_flat_lineage(
            comparison_lineage,
            {
                "cost_artifact",
                "ledger_observation",
                "comparison_contract",
                "lifecycle_successor",
                "historical_coverage",
                "missing_mark_diagnostic",
            },
        )
        self._assert_current_flat_lineage(base_lineage, set())

    def test_production_wrapper_defaults_bind_current_cost_and_comparison(self) -> None:
        from scripts.publish_v3_b5_bundle import load_verified_results
        from scripts import publish_v3_b5_bundle as wrapper

        self.assertEqual(wrapper.COST_ARTIFACT_ID, "e405b900f971877f")
        self.assertEqual(
            wrapper.COST_MANIFEST_SHA256,
            "23159b522d9f2519d05d185031e2a26c2b47cd0b3f22bf983d0d6a89b12396db",
        )
        self.assertEqual(wrapper.COMPARISON_ARTIFACT_ID, "d3a78447920b611a")
        self.assertEqual(
            wrapper.COMPARISON_MANIFEST_SHA256,
            "f6f6af734539a860063f8c30e868c3b96b4b262352998eb17f7bd3e6453ec5cb",
        )

        results = load_verified_results(ROOT)
        self.assertEqual(
            results["base_transaction_cost"]["lineage"]["ledger_observation"]["artifact_id"],
            "984864448e8aa4cd",
        )
        self.assertEqual(
            results["benchmark_comparison"]["lineage"]["cost_artifact"]["artifact_id"],
            "e405b900f971877f",
        )

    def test_current_wrapper_temp_publish_and_official_verify(self) -> None:
        from scripts.publish_v3_b5_bundle import load_verified_results, publish_verified_b5_bundle
        from scripts.verify_v3_b5_bundle import verify_verified_b5_bundle

        results = load_verified_results(ROOT)
        self.assertEqual(set(results), {
            "base_transaction_cost",
            "stress_transaction_cost",
            "benchmark_comparison",
            "same_universe_control_comparison",
        })
        self.assertEqual(
            results["benchmark_comparison"]["lineage"]["cost_artifact"]["artifact_id"],
            "e405b900f971877f",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            published = publish_verified_b5_bundle(ROOT, Path(temp_dir) / "bundles")
            self.assertEqual(published["status"], "published")
            bundle_dir = Path(published["path"])
            verified = verify_verified_b5_bundle(ROOT, bundle_dir)
            self.assertEqual(verified["status"], "verified")
            manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["authorization_scope"], "v3_b5_formal_b6_preflight")
            self.assertFalse(manifest["not_authorized_for_b6_oos_gate_promotion_signal"])
            self.assertEqual(
                set(manifest["results"]),
                set(results),
            )
            self.assertEqual(
                manifest["results"]["benchmark_comparison"]["canonical_payload_sha256"],
                results["benchmark_comparison"]["canonical_payload_sha256"],
            )

    def test_clean_serialized_current_lineage_chain(self) -> None:
        """Run the current B4 -> four B5 boundaries once in one fresh temp root."""
        from backend.services.v3_b5_costs import build_cost_artifact, verify_cost_artifact
        from backend.services.v3_b5_bundle import (
            B4_ID,
            B4_MANIFEST_SHA256,
            B4_EVENT_SHA256,
            GATE_ENVELOPE_HASH,
            PROTOCOL_ID,
            REVISION_ID,
            SUPPLEMENT_ID,
            SUPPLEMENT_MANIFEST_SHA256,
            publish_b5_bundle,
            verify_b5_bundle,
        )
        from scripts.publish_v3_b5_comparisons import publish as publish_comparisons
        from scripts.publish_v3_b5_ledger_observations import build_and_publish
        from scripts.run_v3_b4_is_once import verify_v3_b4_is_result
        from scripts.verify_v3_b5_comparisons import verify_artifact as verify_comparisons
        from scripts.verify_v3_b5_ledger_observations import verify_artifact as verify_ledger

        def read_json(path: Path) -> dict:
            return json.loads(path.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            ledger_root = temp_root / "ledger"
            cost_root = temp_root / "costs"
            comparison_root = temp_root / "comparisons"
            bundle_root = temp_root / "bundles"
            self.assertEqual(tuple(temp_root.iterdir()), ())
            comparison_root.mkdir(parents=True, exist_ok=True)

            b4_dir = ROOT / "data/pit/v3_b4_is_results" / B4_ID
            b4_verified = verify_v3_b4_is_result(b4_dir)
            self.assertEqual(b4_verified["status"], "verified")
            self.assertEqual(b4_verified["artifact_id"], B4_ID)
            supplement_manifest = read_json(
                ROOT / "data/pit/v3_execution_semantics_supplements" / SUPPLEMENT_ID / "manifest.json"
            )
            self.assertEqual(supplement_manifest["criteria"]["envelope_hash"], GATE_ENVELOPE_HASH)

            ledger_result = build_and_publish(repo_root=ROOT, output_root=ledger_root)
            self.assertEqual(ledger_result["status"], "published")
            ledger_dir = Path(ledger_result["path"])
            ledger_verified = verify_ledger(ledger_dir)
            self.assertEqual(ledger_verified["status"], "verified")
            self.assertEqual(ledger_verified["observation_count"], 176)
            self.assertEqual(ledger_verified["fill_count"], 124)
            self.assertEqual(ledger_verified["oos_read_count"], 0)
            ledger_manifest = read_json(ledger_dir / "manifest.json")
            self._assert_current_ledger_lineage(ledger_manifest["lineage"], supplement_manifest)

            cost_result = build_cost_artifact(ROOT, cost_root, observation_dir=ledger_dir)
            self.assertEqual(cost_result["status"], "published")
            cost_dir = Path(cost_result["path"])
            cost_verified = verify_cost_artifact(ROOT, cost_dir, observation_dir=ledger_dir)
            self.assertEqual(cost_verified["status"], "verified")
            self.assertEqual(cost_verified["fill_count"], 124)
            cost_manifest = read_json(cost_dir / "manifest.json")
            self._assert_current_flat_lineage(cost_manifest["lineage"], {"ledger_observation", "daily_observation_hash"})
            self.assertEqual(cost_manifest["lineage"]["ledger_observation"]["artifact_id"], ledger_result["artifact_id"])
            self.assertEqual(
                cost_manifest["lineage"]["ledger_observation"]["manifest_sha256"],
                ledger_result["manifest_sha256"],
            )

            comparison_result = publish_comparisons(
                ROOT,
                comparison_root,
                cost_dir=cost_dir,
                observation_dir=ledger_dir,
            )
            self.assertEqual(comparison_result["status"], "published")
            comparison_dir = Path(comparison_result["path"])
            comparison_verified = verify_comparisons(
                comparison_dir,
                ROOT,
                cost_dir=cost_dir,
                observation_dir=ledger_dir,
            )
            self.assertEqual(comparison_verified["status"], "verified")
            comparison_manifest = read_json(comparison_dir / "manifest.json")
            self._assert_current_flat_lineage(
                comparison_manifest["lineage"],
                {
                    "cost_artifact",
                    "ledger_observation",
                    "comparison_contract",
                    "lifecycle_successor",
                    "historical_coverage",
                    "missing_mark_diagnostic",
                },
            )
            self.assertEqual(comparison_manifest["lineage"]["cost_artifact"]["artifact_id"], cost_result["artifact_id"])
            self.assertEqual(
                comparison_manifest["lineage"]["cost_artifact"]["manifest_sha256"],
                cost_result["manifest_sha256"],
            )
            self.assertEqual(
                comparison_manifest["lineage"]["ledger_observation"]["artifact_id"],
                ledger_result["artifact_id"],
            )

            results = {
                "base_transaction_cost": read_json(cost_dir / "base_transaction_cost.json"),
                "stress_transaction_cost": read_json(cost_dir / "stress_transaction_cost.json"),
                "benchmark_comparison": read_json(comparison_dir / "benchmark_comparison.json"),
                "same_universe_control_comparison": read_json(comparison_dir / "same_universe_control.json"),
            }
            bundle_result = publish_b5_bundle(ROOT, results, bundle_root)
            self.assertEqual(bundle_result["status"], "published")
            bundle_dir = Path(bundle_result["path"])
            bundle_verified = verify_b5_bundle(ROOT, bundle_dir)
            self.assertEqual(bundle_verified["status"], "verified")
            bundle_manifest = read_json(bundle_dir / "manifest.json")
            self._assert_current_flat_lineage(bundle_manifest["lineage"], set())
            self.assertFalse(bundle_manifest["not_authorized_for_b6_oos_gate_promotion_signal"])
            self.assertEqual(set(bundle_manifest["results"]), set(results))
            for result_type, payload in results.items():
                ref = bundle_manifest["results"][result_type]
                self.assertEqual(ref["payload_id"], payload["payload_id"])
                self.assertEqual(ref["canonical_payload_sha256"], payload["canonical_payload_sha256"])

            self.assertEqual(ledger_manifest["observations"]["count"], 176)
            self.assertEqual(ledger_manifest["read_audit"]["oos_read_count"], 0)
            self.assertEqual(cost_manifest["fill_count"], 124)
            self.assertEqual(comparison_manifest["lineage"]["cost_artifact"]["artifact_id"], cost_result["artifact_id"])
            self.assertEqual(bundle_dir.name, bundle_manifest["bundle_id"])
    def test_new_lineage_bundle_references_all_four_results(self) -> None:
        from backend.services.v3_b5_bundle import build_lineage

        lineage = build_lineage(ROOT)
        self.assertEqual(lineage["b4"]["artifact_id"], "cfa75e8b2a72bc76")
        self.assertEqual(lineage["execution_supplement"]["id"], "185a6b8f03915dca")
        self.assertEqual(lineage["gate_criteria_envelope_hash"], "94da0dda30af75d663a7d28deb0a15d64a4e068586a1295f3b4f52203a8c4738")

    def test_verified_inputs_are_admitted_by_bundle_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            response = publish_b5_bundle(ROOT, _real_results(), Path(temp_dir) / "bundles")
        self.assertEqual(response["status"], "published")

    def test_missing_base_source_fails_loud_without_publishing(self) -> None:
        from scripts.publish_v3_b5_bundle import publish_verified_b5_bundle

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            cost_dir, comparison_dir = _copy_source_dirs(temp_root)
            (cost_dir / "base_transaction_cost.json").unlink()
            response = publish_verified_b5_bundle(
                ROOT,
                temp_root / "bundles",
                cost_dir=cost_dir,
                comparison_dir=comparison_dir,
            )
        self.assertEqual(response["status"], "not_authorized")
        self.assertFalse((temp_root / "bundles").exists())

    def test_publisher_writes_verified_inputs_and_exact_reuse_is_idempotent(self) -> None:
        from scripts.publish_v3_b5_bundle import publish_verified_b5_bundle

        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "bundles"
            first = publish_verified_b5_bundle(ROOT, output_root)
            second = publish_verified_b5_bundle(ROOT, output_root)
        self.assertEqual(first["status"], "published")
        self.assertEqual(second["status"], "already_published")
        self.assertEqual(first["bundle_id"], second["bundle_id"])

    def test_each_missing_result_is_not_authorized_without_output(self) -> None:
        for missing in (
            "base_transaction_cost",
            "stress_transaction_cost",
            "benchmark_comparison",
            "same_universe_control_comparison",
        ):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temp_dir:
                results = _real_results()
                results.pop(missing)
                output_root = Path(temp_dir) / "bundles"
                response = publish_b5_bundle(ROOT, results, output_root)
                self.assertEqual(response["status"], "not_authorized")
                self.assertFalse(output_root.exists())

    def test_source_tamper_and_identity_mismatch_are_not_authorized(self) -> None:
        from scripts.publish_v3_b5_bundle import publish_verified_b5_bundle

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            cost_dir, comparison_dir = _copy_source_dirs(temp_root)
            payload_path = comparison_dir / "benchmark_comparison.json"
            payload_path.write_bytes(payload_path.read_bytes() + b" ")
            response = publish_verified_b5_bundle(
                ROOT,
                temp_root / "bundles",
                cost_dir=cost_dir,
                comparison_dir=comparison_dir,
            )
            self.assertEqual(response["status"], "not_authorized")

            cost_dir, comparison_dir = _copy_source_dirs(temp_root / "identity")
            manifest_path = cost_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifact_id"] = "different-artifact"
            raw = canonical_json(manifest)
            manifest_path.write_bytes(raw)
            manifest_path.with_name("manifest.json.sha256").write_text(f"{sha256_bytes(raw)}  manifest.json\n", encoding="utf-8")
            response = publish_verified_b5_bundle(
                ROOT,
                temp_root / "identity-bundles",
                cost_dir=cost_dir,
                comparison_dir=comparison_dir,
            )
            self.assertEqual(response["status"], "not_authorized")

    def test_observation_hash_mismatch_is_not_authorized(self) -> None:
        from scripts.publish_v3_b5_bundle import publish_verified_b5_bundle

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            cost_dir, comparison_dir = _copy_source_dirs(temp_root)
            _rewrite_payload(
                comparison_dir / "benchmark_comparison.json",
                lambda payload: payload.__setitem__("daily_observation_hash", "0" * 64),
            )
            response = publish_verified_b5_bundle(
                ROOT,
                temp_root / "bundles",
                cost_dir=cost_dir,
                comparison_dir=comparison_dir,
            )
        self.assertEqual(response["status"], "not_authorized")

    def test_comparison_future_date_and_daily_gap_fail_loud(self) -> None:
        from scripts.publish_v3_b5_bundle import _validate_comparison_sequence

        comparison_manifest = json.loads(
            (ROOT / "data/pit/v3_b5_comparisons/d3a78447920b611a/manifest.json").read_text(encoding="utf-8")
        )
        payloads = {
            "benchmark_comparison": json.loads(
                (ROOT / "data/pit/v3_b5_comparisons/d3a78447920b611a/benchmark_comparison.json").read_text(encoding="utf-8")
            ),
            "same_universe_control_comparison": json.loads(
                (ROOT / "data/pit/v3_b5_comparisons/d3a78447920b611a/same_universe_control.json").read_text(encoding="utf-8")
            ),
        }
        payloads["benchmark_comparison"]["result"]["daily_rows"][0]["date"] = "2026-03-20"
        with self.assertRaisesRegex(ValueError, "future"):
            _validate_comparison_sequence(comparison_manifest, payloads, ROOT)

        payloads = {
            "benchmark_comparison": json.loads(
                (ROOT / "data/pit/v3_b5_comparisons/d3a78447920b611a/benchmark_comparison.json").read_text(encoding="utf-8")
            ),
            "same_universe_control_comparison": json.loads(
                (ROOT / "data/pit/v3_b5_comparisons/d3a78447920b611a/same_universe_control.json").read_text(encoding="utf-8")
            ),
        }
        payloads["benchmark_comparison"]["result"]["daily_rows"].pop(1)
        with self.assertRaisesRegex(ValueError, "sequence gap"):
            _validate_comparison_sequence(comparison_manifest, payloads, ROOT)

    def test_verifier_rereads_sources_and_rejects_bundle_payload_tamper(self) -> None:
        from scripts.publish_v3_b5_bundle import publish_verified_b5_bundle
        from scripts.verify_v3_b5_bundle import verify_verified_b5_bundle

        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "bundles"
            published = publish_verified_b5_bundle(ROOT, output_root)
            bundle_dir = Path(published["path"])
            verified = verify_verified_b5_bundle(ROOT, bundle_dir)
            self.assertEqual(verified["status"], "verified")
            payload_path = bundle_dir / "base_transaction_cost.json"
            payload_path.write_bytes(payload_path.read_bytes() + b" ")
            invalid = verify_verified_b5_bundle(ROOT, bundle_dir)
        self.assertEqual(invalid["status"], "invalid")

    def test_verifier_rejects_tampered_bundle_disclosure_fields(self) -> None:
        from scripts.publish_v3_b5_bundle import publish_verified_b5_bundle
        from scripts.verify_v3_b5_bundle import verify_verified_b5_bundle

        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "bundles"
            published = publish_verified_b5_bundle(ROOT, output_root)
            bundle_dir = Path(published["path"])
            manifest_path = bundle_dir / "manifest.json"
            original = json.loads(manifest_path.read_text(encoding="utf-8"))
            for field, value in (
                ("not_authorized_for_b6_oos_gate_promotion_signal", True),
                ("authorization_scope", "not_v3_b5_contract_fixture_only"),
            ):
                with self.subTest(field=field):
                    manifest = dict(original)
                    manifest[field] = value
                    raw = canonical_json(manifest)
                    manifest_path.write_bytes(raw)
                    manifest_path.with_name("manifest.json.sha256").write_text(
                        f"{sha256_bytes(raw)}  manifest.json\n", encoding="utf-8"
                    )
                    self.assertEqual(verify_verified_b5_bundle(ROOT, bundle_dir)["status"], "invalid")

    def test_write_once_failure_preserves_staging_without_target(self) -> None:
        from backend.services.v3_b5_bundle import _write_once

        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "bundles"
            output_root.mkdir()
            target = output_root / "bundle-id"
            files = {"first.json": b"first", "second.json": b"second"}
            real_replace = os.replace

            def fail_final(source, destination):
                if Path(destination) == target:
                    raise OSError("injected replace failure")
                return real_replace(source, destination)

            with patch("backend.services.v3_b5_bundle.os.replace", side_effect=fail_final):
                with self.assertRaisesRegex(OSError, "injected replace failure"):
                    _write_once(target, files)

            self.assertFalse(target.exists())
            staging_dirs = list(output_root.glob(".bundle-id.staging-*"))
            self.assertEqual(len(staging_dirs), 1)
            self.assertEqual(
                {path.name for path in staging_dirs[0].iterdir()},
                {"first.json", "second.json"},
            )

    def test_synthetic_bundle_replay_is_exact_and_immutable(self) -> None:
        expected_names = {
            "manifest.json",
            "manifest.json.sha256",
            "base_transaction_cost.json",
            "base_transaction_cost.json.sha256",
            "stress_transaction_cost.json",
            "stress_transaction_cost.json.sha256",
            "benchmark_comparison.json",
            "benchmark_comparison.json.sha256",
            "same_universe_control.json",
            "same_universe_control.json.sha256",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            target, first, _results = _publish_synthetic_bundle(temp_root)
            self.assertEqual(first["status"], "published")
            self.assertEqual(first["authorization_scope"], "v3_b5_contract_fixture_only")
            self.assertTrue(first["not_authorized_for_b6_oos_gate_promotion_signal"])
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["authorization_scope"], "v3_b5_contract_fixture_only")
            self.assertTrue(manifest["not_authorized_for_b6_oos_gate_promotion_signal"])
            self.assertEqual({path.name for path in target.iterdir()}, expected_names)
            before = {
                path.name: (path.read_bytes(), path.stat().st_mtime_ns)
                for path in target.iterdir()
            }
            directory_mtime = target.stat().st_mtime_ns

            _target, second, _results = _publish_synthetic_bundle(temp_root)

            self.assertEqual(second["status"], "already_published")
            self.assertEqual(target.stat().st_mtime_ns, directory_mtime)
            self.assertEqual(
                {
                    path.name: (path.read_bytes(), path.stat().st_mtime_ns)
                    for path in target.iterdir()
                },
                before,
            )

    def test_synthetic_bundle_writer_rejects_extra_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            target, _published, _results = _publish_synthetic_bundle(temp_root)
            (target / "unexpected.json").write_bytes(b"unexpected")
            with self.assertRaisesRegex(ValueError, "write-once conflict"):
                _publish_synthetic_bundle(temp_root)

    def test_synthetic_bundle_writer_rejects_non_directory_target(self) -> None:
        from backend.services.v3_b5_bundle import _write_once

        with tempfile.TemporaryDirectory() as temp_dir:
            non_directory = Path(temp_dir) / "non-directory"
            non_directory.write_bytes(b"not a directory")
            with self.assertRaisesRegex(ValueError, "write-once conflict"):
                _write_once(non_directory, {"manifest.json": b"{}"})

    def test_synthetic_bundle_verifier_rejects_missing_extra_and_noncanonical_sidecar(self) -> None:
        from backend.services.v3_b5_bundle import verify_b5_bundle

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            target, _published, _results = _publish_synthetic_bundle(temp_root)
            (target / "unexpected.json").write_bytes(b"unexpected")
            lineage, _results = _synthetic_bundle_inputs()
            with patch("backend.services.v3_b5_bundle.build_lineage", return_value=lineage):
                self.assertEqual(verify_b5_bundle(temp_root, target)["status"], "invalid")

            (target / "unexpected.json").unlink()
            (target / "base_transaction_cost.json").unlink()
            with patch("backend.services.v3_b5_bundle.build_lineage", return_value=lineage):
                self.assertEqual(verify_b5_bundle(temp_root, target)["status"], "invalid")

            sidecar_root = temp_root / "sidecar"
            target, _published, _results = _publish_synthetic_bundle(sidecar_root)
            sidecar = target / "manifest.json.sha256"
            sidecar.write_bytes(sidecar.read_bytes() + b" trailing")
            with patch("backend.services.v3_b5_bundle.build_lineage", return_value=lineage):
                self.assertEqual(verify_b5_bundle(sidecar_root, target)["status"], "invalid")

    def test_verified_synthetic_payload_tamper_is_rejected_by_verifier_and_replay(self) -> None:
        from scripts.publish_v3_b5_bundle import publish_verified_b5_bundle
        from scripts.verify_v3_b5_bundle import verify_verified_b5_bundle

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            lineage, results = _synthetic_bundle_inputs()
            output_root = temp_root / "bundles"
            with patch("scripts.publish_v3_b5_bundle.load_verified_results", return_value=results):
                with patch("backend.services.v3_b5_bundle.build_lineage", return_value=lineage):
                    published = publish_verified_b5_bundle(temp_root, output_root)
            self.assertEqual(published["status"], "published")
            bundle_dir = Path(published["path"])
            self.assertTrue(bundle_dir.is_dir())

            with patch("scripts.verify_v3_b5_bundle.load_verified_results", return_value=results):
                with patch("backend.services.v3_b5_bundle.build_lineage", return_value=lineage):
                    self.assertEqual(
                        verify_verified_b5_bundle(temp_root, bundle_dir)["status"],
                        "verified",
                    )

            payload_path = bundle_dir / "base_transaction_cost.json"
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            payload["result"]["total_cost"] = 9.0
            raw = canonical_json(payload)
            payload_path.write_bytes(raw)
            payload_path.with_name(payload_path.name + ".sha256").write_bytes(
                f"{sha256_bytes(raw)}  {payload_path.name}\n".encode("utf-8")
            )

            with patch("scripts.verify_v3_b5_bundle.load_verified_results", return_value=results):
                with patch("backend.services.v3_b5_bundle.build_lineage", return_value=lineage):
                    invalid = verify_verified_b5_bundle(temp_root, bundle_dir)
            self.assertEqual(invalid["status"], "invalid")
            self.assertIn("result identity mismatch", invalid["reason"])

            with patch("scripts.publish_v3_b5_bundle.load_verified_results", return_value=results):
                with patch("backend.services.v3_b5_bundle.build_lineage", return_value=lineage):
                    with self.assertRaisesRegex(ValueError, "write-once conflict"):
                        publish_verified_b5_bundle(temp_root, output_root)


if __name__ == "__main__":
    unittest.main()
