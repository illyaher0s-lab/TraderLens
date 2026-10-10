from pathlib import Path
from contextlib import closing
import hashlib
import json
import shutil
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.db.strategy import ProtocolSnapshotLookupError, StrategyDB
from scripts.run_v3_task4_once import (
    _discover_verified_b4_artifact,
    _discover_verified_b5_bundle,
    _materialize_and_preflight,
    run_once,
)


REPO_ROOT = Path(__file__).resolve().parents[1]

RESULT_ID = "20960e9fd15cdb44"
RESULT_ROOT = REPO_ROOT / "data/pit/v3_b4_is_results"
B5_BUNDLE_DIR = REPO_ROOT / "data/pit/v3_b5_validation_bundles/9d388459df4d591e"
B5_BUNDLE_ID = "9d388459df4d591e"
TASK7_B5_SUPPLEMENT_ID = "680cd55c91254667"
TASK7_B5_SUPPLEMENT_MANIFEST_SHA256 = "c7bff428da948b54389c6c7415072de6ca5df4ebe777d251d1a06d08e6e8fb39"

CURRENT_B4_ID = "958bb9717edd08a9"
CURRENT_B4_MANIFEST_SHA256 = "af9ebfbcda0eff795efc4ef26688f57286886206e1e6dfe1699a90a197f8b7c2"
CURRENT_B4_EVENT_SHA256 = "374479e9df35c80c680adfe34fe95d10a78eb4d049a24fc6bc43cfb3aa0bf1cc"
CURRENT_B5_BUNDLE_ID = "e4b03db805ebbdee"
CURRENT_B5_BUNDLE_MANIFEST_SHA256 = "fb5b0c3e2cea118f33257a0cc338fe768df7fce237bf8fdf1b8b93dbcc1416a5"
CURRENT_B5_SUPPLEMENT_ID = "d1134e96d6b2ec1b"
CURRENT_B5_SUPPLEMENT_MANIFEST_SHA256 = "18e7fd2fb48c089019c9343512641de7ef4f90fd50415c868919ddcabd24c16b"
CURRENT_PROTOCOL_ID = "8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe"
CURRENT_STRATEGY_REVISION_ID = "6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc"
CURRENT_CRITERIA_ROOT = REPO_ROOT / "data/pit/prototype_gate_v2_criteria"


def _copy_current_criteria(tmp_path: Path) -> Path:
    criteria_root = tmp_path / "criteria"
    shutil.copytree(CURRENT_CRITERIA_ROOT, criteria_root)
    return criteria_root


def _snapshot_b6_task_rows(db_path: Path) -> dict[str, dict[str, object]]:
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return {
            row["task_id"]: dict(row)
            for row in conn.execute(
                "select * from b6_validation_tasks order by task_id"
            ).fetchall()
        }


class TestTask7B5Admission(unittest.TestCase):
    def _run_v3_gate_1_4_preflight(self, tmp_path: Path, successor_specs):
        import scripts.run_v3_task4_once as task4_runner

        repo_root = tmp_path / "repo"
        formal_root = repo_root / task4_runner.V3_FORMAL_SNAPSHOT_ROOT
        formal_dir = formal_root / task4_runner.FORMAL_SNAPSHOT_ID
        formal_dir.mkdir(parents=True)
        formal_manifest = {
            "snapshot_id": task4_runner.FORMAL_SNAPSHOT_ID,
            "semantic_hash": task4_runner.FORMAL_SNAPSHOT_HASH,
        }
        formal_raw = json.dumps(formal_manifest, sort_keys=True, separators=(",", ":")).encode()
        (formal_dir / "manifest.json").write_bytes(formal_raw)
        (formal_dir / "manifest.json.sha256").write_text(
            hashlib.sha256(formal_raw).hexdigest() + "  manifest.json\n",
            encoding="utf-8",
        )

        # This protected acquisition root is deliberately not a formal snapshot.
        decoy = formal_root / "candidate-must-not-write"
        decoy.mkdir()
        (decoy / "acquisition_manifest.json").write_text("{}", encoding="utf-8")

        successor_root = repo_root / task4_runner.V3_SUCCESSOR_ROOT
        successor_root.mkdir(parents=True)
        b3_manifest_sha256 = "a" * 64
        membership_manifest_sha256 = "b" * 64
        membership_records_sha256 = "c" * 64
        expected_template = {
            "data_requirements_hash": task4_runner.DATA_REQUIREMENTS_HASH,
            "template_hash": task4_runner.TEMPLATE_HASH,
            "template_id": task4_runner.TEMPLATE_ID,
            "template_version": task4_runner.TEMPLATE_VERSION,
        }
        for directory_name, successor_id, variant in successor_specs:
            successor_dir = successor_root / directory_name
            successor_dir.mkdir()
            successor_manifest = {
                "successor_id": successor_id,
                "successor_schema_version": "v3_availability_bounded_qualification_successor.v1",
                "authorization_scope": "b6_coverage_bound",
                "not_authorized_for_b6_oos_gate_promotion_signal_or_data_collection": False,
                "status": "availability_bounded_qualified",
                "template": expected_template,
                "formal_snapshot": {
                    "manifest_sha256": hashlib.sha256(formal_raw).hexdigest(),
                    "semantic_hash": task4_runner.FORMAL_SNAPSHOT_HASH,
                    "snapshot_id": task4_runner.FORMAL_SNAPSHOT_ID,
                },
                "lineage": {
                    "b3": {
                        "artifact_id": task4_runner.B3_ID,
                        "manifest_sha256": b3_manifest_sha256,
                    },
                    "membership": {
                        "manifest_sha256": membership_manifest_sha256,
                        "records_sha256": membership_records_sha256,
                        "snapshot_id": task4_runner.MEMBERSHIP_ID,
                    },
                },
                "test_variant": variant,
            }
            successor_raw = json.dumps(
                successor_manifest, sort_keys=True, separators=(",", ":")
            ).encode()
            (successor_dir / "manifest.json").write_bytes(successor_raw)
            (successor_dir / "manifest.json.sha256").write_text(
                hashlib.sha256(successor_raw).hexdigest() + "  manifest.json\n",
                encoding="utf-8",
            )

        calls = []

        class FakeStrategyDB:
            def __init__(self, _path):
                pass

            def materialize_strategy_provenance(self, *_args):
                return {"created_ids": {}, "reused_ids": {}}

            def close(self):
                pass

        frozen_template = SimpleNamespace(
            template_id=task4_runner.TEMPLATE_ID,
            version=task4_runner.TEMPLATE_VERSION,
            template_hash=task4_runner.TEMPLATE_HASH,
            data_requirements_hash=task4_runner.DATA_REQUIREMENTS_HASH,
        )
        draft = SimpleNamespace(
            strategy_revision_id=CURRENT_STRATEGY_REVISION_ID,
            strategy_template_id=task4_runner.TEMPLATE_ID,
            strategy_template_version=task4_runner.TEMPLATE_VERSION,
            strategy_template_hash=task4_runner.TEMPLATE_HASH,
        )

        def validate_candidate(**kwargs):
            successor_dir = Path(kwargs["successor_dir"])
            formal_snapshot_dir = Path(kwargs["formal_snapshot_dir"])
            calls.append((successor_dir, formal_snapshot_dir, draft.strategy_revision_id))
            manifest = json.loads((successor_dir / "manifest.json").read_text(encoding="utf-8"))
            return {
                "status": "valid",
                "successor_id": manifest["successor_id"],
                "successor_manifest_sha256": hashlib.sha256(
                    (successor_dir / "manifest.json").read_bytes()
                ).hexdigest(),
                "snapshot_id": task4_runner.FORMAL_SNAPSHOT_ID,
                "snapshot_manifest_sha256": hashlib.sha256(formal_raw).hexdigest(),
                "snapshot_semantic_hash": task4_runner.FORMAL_SNAPSHOT_HASH,
                "scope_id": "acbc49159d989a46",
                "coverage_id": "1e79d26460c0c109",
            }

        with (
            patch.object(task4_runner, "StrategyDB", FakeStrategyDB),
            patch.object(
                task4_runner,
                "_verify_membership_artifact",
                return_value=(
                    {"snapshot_id": task4_runner.MEMBERSHIP_ID},
                    membership_manifest_sha256,
                    membership_records_sha256,
                ),
            ),
            patch.object(
                task4_runner,
                "_build_provenance_records",
                return_value=(frozen_template, object(), draft, object()),
            ),
            patch.object(
                task4_runner,
                "TASK7_FORMAL_SNAPSHOT_MANIFEST_SHA256",
                hashlib.sha256(formal_raw).hexdigest(),
            ),
            patch.object(
                task4_runner,
                "validate_strategy_revision_provenance",
                return_value=SimpleNamespace(is_valid=True, reason_code=None, detail=None),
            ),
            patch.object(
                task4_runner,
                "verify_v3_snapshot",
                return_value={"status": "valid"},
            ),
            patch.object(task4_runner, "validate_v3_gate_1_4", side_effect=validate_candidate),
        ):
            result = _materialize_and_preflight(
                repo_root=repo_root,
                db_path=tmp_path / "unused.db",
                b3_manifest={},
                b3_manifest_hash=b3_manifest_sha256,
                criteria_root=tmp_path / "missing-criteria",
            )
        return result, calls, formal_dir

    def test_v3_admission_ignores_directories_without_formal_manifests(self):
        with tempfile.TemporaryDirectory(prefix="task7-v3-admission-decoy-") as raw_tmp:
            result, calls, formal_dir = self._run_v3_gate_1_4_preflight(
                Path(raw_tmp),
                [("12f1b9aac73dfcd4", "12f1b9aac73dfcd4", "current")],
            )

        self.assertEqual(result["first_missing_prerequisite"], "b6_criteria")
        self.assertEqual(result["v3_formal_snapshot"]["id"], "v3ds_d73256081de82e8a")
        self.assertEqual(result["v3_availability_successor"]["id"], "12f1b9aac73dfcd4")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0].name, "12f1b9aac73dfcd4")
        self.assertEqual(calls[0][1], formal_dir)
        self.assertEqual(calls[0][2], CURRENT_STRATEGY_REVISION_ID)

    def test_v3_admission_rejects_multiple_verified_current_lineage_successors(self):
        with tempfile.TemporaryDirectory(prefix="task7-v3-admission-multiple-") as raw_tmp:
            result, calls, _ = self._run_v3_gate_1_4_preflight(
                Path(raw_tmp),
                [
                    ("successor-a", "successor-a", "a"),
                    ("successor-b", "successor-b", "b"),
                ],
            )

        self.assertEqual(result["first_missing_prerequisite"], "b6_v3_admission")
        self.assertEqual(result["reason"], "hard_block:b6_v3_admission_ambiguous")
        self.assertIn("multiple verified successors", result["gate1_4_validation"]["reason"])
        self.assertEqual({call[0].name for call in calls}, {"successor-a", "successor-b"})

    def test_v3_admission_rejects_duplicate_successor_id_with_different_manifest_hash(self):
        with tempfile.TemporaryDirectory(prefix="task7-v3-admission-id-conflict-") as raw_tmp:
            result, calls, _ = self._run_v3_gate_1_4_preflight(
                Path(raw_tmp),
                [
                    ("12f1b9aac73dfcd4", "12f1b9aac73dfcd4", "first-bytes"),
                    ("duplicate-copy", "12f1b9aac73dfcd4", "different-bytes"),
                ],
            )

        self.assertEqual(result["first_missing_prerequisite"], "b6_v3_admission")
        self.assertEqual(result["reason"], "hard_block:b6_v3_admission_ambiguous")
        self.assertIn("successor ID has conflicting manifest hashes", result["gate1_4_validation"]["reason"])
        self.assertEqual(calls, [])

    def test_current_lineage_pin_defaults_match_accepted_bundle(self):
        import scripts.run_v3_task4_once as task4_runner

        self.assertEqual(task4_runner.TASK7_B4_ARTIFACT_ID, CURRENT_B4_ID)
        self.assertEqual(task4_runner.TASK7_B4_MANIFEST_SHA256, CURRENT_B4_MANIFEST_SHA256)
        self.assertEqual(task4_runner.TASK7_B4_EVENT_RESULT_SHA256, CURRENT_B4_EVENT_SHA256)
        self.assertEqual(
            task4_runner.TASK7_FORMAL_SNAPSHOT_MANIFEST_SHA256,
            "57067e15e6ad1a92b23b42b48173b6cf1af2e7e23f3357320288fb7e109c2680",
        )
        self.assertEqual(task4_runner.TASK7_B5_SUPPLEMENT_ID, CURRENT_B5_SUPPLEMENT_ID)
        self.assertEqual(
            task4_runner.TASK7_B5_SUPPLEMENT_MANIFEST_SHA256,
            CURRENT_B5_SUPPLEMENT_MANIFEST_SHA256,
        )
        self.assertEqual(task4_runner.TASK7_B5_BUNDLE_ID, CURRENT_B5_BUNDLE_ID)
        self.assertEqual(
            task4_runner.TASK7_B5_BUNDLE_MANIFEST_SHA256,
            CURRENT_B5_BUNDLE_MANIFEST_SHA256,
        )

        source_root = REPO_ROOT
        with tempfile.TemporaryDirectory(prefix="task7-current-pin-") as raw_tmp:
            fixture_root = Path(raw_tmp) / "repo"
            shutil.copytree(
                source_root / "data/pit/v3_b4_is_results" / CURRENT_B4_ID,
                fixture_root / "data/pit/v3_b4_is_results" / CURRENT_B4_ID,
            )
            shutil.copytree(
                source_root / "data/pit/v3_execution_semantics_supplements" / CURRENT_B5_SUPPLEMENT_ID,
                fixture_root / "data/pit/v3_execution_semantics_supplements" / CURRENT_B5_SUPPLEMENT_ID,
            )
            shutil.copytree(
                source_root / "data/pit/v3_b5_validation_bundles" / CURRENT_B5_BUNDLE_ID,
                fixture_root / "data/pit/v3_b5_validation_bundles" / CURRENT_B5_BUNDLE_ID,
            )

            with patch.object(
                task4_runner,
                "verify_v3_b4_is_result",
                return_value={
                    "status": "verified",
                    "manifest_sha256": CURRENT_B4_MANIFEST_SHA256,
                    "event_result_sha256": CURRENT_B4_EVENT_SHA256,
                },
            ), patch.object(
                task4_runner,
                "verify_verified_b5_bundle",
                return_value={
                    "status": "verified",
                    "bundle_id": CURRENT_B5_BUNDLE_ID,
                    "manifest_sha256": CURRENT_B5_BUNDLE_MANIFEST_SHA256,
                    "result_count": 4,
                },
            ):
                b4 = _discover_verified_b4_artifact(repo_root=fixture_root)
                b5 = _discover_verified_b5_bundle(repo_root=fixture_root)

        self.assertEqual(b4["artifact_id"], CURRENT_B4_ID)
        self.assertEqual(b4["manifest_sha256"], CURRENT_B4_MANIFEST_SHA256)
        self.assertEqual(b4["event_result_sha256"], CURRENT_B4_EVENT_SHA256)
        self.assertEqual(b4["supplement_id"], CURRENT_B5_SUPPLEMENT_ID)
        self.assertEqual(b5["status"], "verified")
        self.assertEqual(b5["bundle_id"], CURRENT_B5_BUNDLE_ID)
        self.assertEqual(b5["manifest_sha256"], CURRENT_B5_BUNDLE_MANIFEST_SHA256)

    def test_valid_b5_inputs_are_source_isolated(self):
        with tempfile.TemporaryDirectory(prefix="task7-source-isolation-") as raw_tmp:
            temp_root = Path(raw_tmp).resolve()
            repo_root, criteria_root, bundle_dir = self._prepare_valid_b5_inputs(temp_root)
            repo_root = repo_root.resolve()

            self.assertIn(temp_root, repo_root.parents)
            self.assertNotEqual(repo_root, REPO_ROOT.resolve())
            self.assertFalse((repo_root / "data/strategy.db").exists())
            self.assertEqual(
                criteria_root.resolve(),
                repo_root / "data/pit/prototype_gate_v2_criteria",
            )
            self.assertEqual(
                bundle_dir.resolve(),
                repo_root / "data/pit/v3_b5_validation_bundles" / CURRENT_B5_BUNDLE_ID,
            )

            required_relative_paths = (
                "data/pit/b3_execution_input_packages/05f38a2884dc7e47/manifest.json",
                "data/pit/b3_execution_input_packages/05f38a2884dc7e47/manifest.json.sha256",
                "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/manifest.json",
                "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/input_index.json",
                "data/pit/qualification_successors/49b09326f35936c6/manifest.json",
                "data/pit/liquidity_qualification_successors/7c05ece4d3f01086/manifest.json",
                "data/pit/v3_historical_coverage_packages/1e79d26460c0c109/manifest.json",
                "data/pit/v3_historical_coverage_packages/1e79d26460c0c109/manifest.json.sha256",
                "data/pit/v3_historical_coverage_packages/1e79d26460c0c109/coverage_by_code.parquet",
                "data/pit/v3_historical_coverage_packages/1e79d26460c0c109/coverage_by_date.parquet",
                "data/pit/v3_historical_coverage_packages/1e79d26460c0c109/unavailable_security_dates.parquet",
                "data/pit/v3_formal_data_snapshot_manifests/v3ds_d73256081de82e8a/manifest.json",
                "data/pit/v3_availability_bounded_qualification_successors/12f1b9aac73dfcd4/manifest.json",
                "data/pit/historical_scope_freezes/acbc49159d989a46/manifest.json",
                "data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_005/manifest.json",
                "data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_005/records.parquet",
                "data/pit/shsz_common_trade_calendars/shsz_common_trade_calendar_v1/manifest.json",
                "data/pit/shsz_common_trade_calendars/shsz_common_trade_calendar_v1/szse_trade_cal.parquet",
                f"data/pit/v3_execution_semantics_supplements/{CURRENT_B5_SUPPLEMENT_ID}/manifest.json",
                f"data/pit/v3_b4_is_results/{CURRENT_B4_ID}/manifest.json",
                f"data/pit/v3_b4_is_results/{CURRENT_B4_ID}/event_result.json",
                f"data/pit/v3_b5_source_inventories/2fe8321a5f644b9b/manifest.json",
                f"data/pit/v3_b5_costs/e405b900f971877f/manifest.json",
                f"data/pit/v3_b5_comparisons/d3a78447920b611a/manifest.json",
                f"data/pit/v3_b5_validation_bundles/{CURRENT_B5_BUNDLE_ID}/manifest.json",
                "data/pit/prototype_gate_v2_criteria/prototype_gate_v2_gate_v2_2bd8670c2e0fe084/manifest.json",
                "data/pit/prototype_gate_v2_criteria/prototype_gate_v2_kill_v2_ea47b0c73ed2476e/manifest.json",
                "backend/services/prototype_gate_criteria_surface.py",
                "backend/services/formal_pit_partition_adapter.py",
                "strategy_core/v3_relative_strength_executor.py",
                "strategy_core/backtest_engine.py",
                "strategy_core/fill_simulator.py",
                "strategy_core/orders.py",
                "strategy_core/transaction_costs.py",
                "strategy_core/portfolio.py",
            )
            for relative in required_relative_paths:
                self.assertTrue((repo_root / relative).is_file(), relative)

    def test_b4_discovery_forwards_temp_repo_root_to_verifier(self):
        import scripts.run_v3_task4_once as task4_runner

        captured = {}

        def verify(artifact_dir, *, repo_root):
            captured["artifact_dir"] = Path(artifact_dir).resolve()
            captured["repo_root"] = Path(repo_root).resolve()
            return {
                "status": "verified",
                "artifact_id": captured["artifact_dir"].name,
                "manifest_sha256": hashlib.sha256(
                    (captured["artifact_dir"] / "manifest.json").read_bytes()
                ).hexdigest(),
                "event_result_sha256": hashlib.sha256(
                    (captured["artifact_dir"] / "event_result.json").read_bytes()
                ).hexdigest(),
            }

        with tempfile.TemporaryDirectory(prefix="task7-b4-root-forward-") as raw_tmp:
            repo_root, _, _ = self._prepare_valid_b5_inputs(Path(raw_tmp))
            with patch.object(task4_runner, "verify_v3_b4_is_result", verify):
                try:
                    result = _discover_verified_b4_artifact(repo_root=repo_root)
                except TypeError as exc:
                    self.fail(f"B4 discovery omitted repo_root: {exc}")

        self.assertIsNotNone(result)
        self.assertEqual(captured["repo_root"], repo_root.resolve())
        self.assertEqual(captured["artifact_dir"].name, CURRENT_B4_ID)
        self.assertEqual(result["artifact_id"], CURRENT_B4_ID)
        self.assertEqual(result["manifest_sha256"], CURRENT_B4_MANIFEST_SHA256)
        self.assertEqual(result["event_result_sha256"], CURRENT_B4_EVENT_SHA256)

    def test_successor_b5_bundle_discovery_uses_exact_current_identity(self):
        repo_root = REPO_ROOT
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            bundle_dir = tmp_path / "verified" / CURRENT_B5_BUNDLE_ID
            shutil.copytree(
                repo_root / "data/pit/v3_b5_validation_bundles" / CURRENT_B5_BUNDLE_ID,
                bundle_dir,
            )
            result = _discover_verified_b5_bundle(
                repo_root=repo_root,
                bundle_dir=bundle_dir,
            )

        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["bundle_id"], CURRENT_B5_BUNDLE_ID)
        self.assertEqual(result["manifest_sha256"], CURRENT_B5_BUNDLE_MANIFEST_SHA256)

    def test_current_lineage_defaults_are_explicit_and_verified(self):
        repo_root = REPO_ROOT

        b4 = _discover_verified_b4_artifact(repo_root=repo_root)
        self.assertIsNotNone(b4)
        self.assertEqual(b4["artifact_id"], CURRENT_B4_ID)
        self.assertEqual(b4["manifest_sha256"], CURRENT_B4_MANIFEST_SHA256)
        self.assertEqual(b4["event_result_sha256"], CURRENT_B4_EVENT_SHA256)
        self.assertEqual(b4["supplement_id"], CURRENT_B5_SUPPLEMENT_ID)
        self.assertEqual(b4["supplement_manifest_sha256"], CURRENT_B5_SUPPLEMENT_MANIFEST_SHA256)

        b5 = _discover_verified_b5_bundle(repo_root=repo_root)
        self.assertEqual(b5["status"], "verified")
        self.assertEqual(b5["bundle_id"], CURRENT_B5_BUNDLE_ID)
        self.assertEqual(b5["manifest_sha256"], CURRENT_B5_BUNDLE_MANIFEST_SHA256)

    @staticmethod
    def _prepare_current_lineage_with_existing_task(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
        repo_root = REPO_ROOT
        db_path = tmp_path / "strategy.db"
        shutil.copy2(repo_root / "data/strategy.db", db_path)
        criteria_root = _copy_current_criteria(tmp_path)
        b4_root = tmp_path / "b4-results"
        shutil.copytree(
            repo_root / "data/pit/v3_b4_is_results" / CURRENT_B4_ID,
            b4_root / CURRENT_B4_ID,
        )
        bundle_dir = tmp_path / "verified" / CURRENT_B5_BUNDLE_ID
        shutil.copytree(
            repo_root / "data/pit/v3_b5_validation_bundles" / CURRENT_B5_BUNDLE_ID,
            bundle_dir,
        )
        return repo_root, db_path, criteria_root, b4_root, bundle_dir

    def _assert_b6_task_snapshot(
        self,
        before: dict[str, dict[str, object]],
        after: dict[str, dict[str, object]],
        *,
        added_task_id: str | None = None,
    ) -> None:
        statuses = {row["status"] for row in before.values()}
        self.assertIn("queued", statuses)
        self.assertIn("failed", statuses)
        expected_ids = set(before)
        if added_task_id is not None:
            self.assertNotIn(added_task_id, before)
            expected_ids.add(added_task_id)
        self.assertEqual(set(after), expected_ids)
        self.assertEqual(
            len(after),
            len(before) + (1 if added_task_id is not None else 0),
        )
        for task_id, old_row in before.items():
            self.assertEqual(after[task_id], old_row)
            if old_row["status"] == "queued":
                self.assertEqual(after[task_id]["status"], "queued")
            if old_row["status"] == "failed":
                self.assertEqual(after[task_id]["status"], "failed")

    def test_new_v2_b5_bundle_creates_new_task_identity_without_mutating_old_task(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            repo_root, db_path, criteria_root, b4_root, bundle_dir = (
                self._prepare_current_lineage_with_existing_task(tmp_path)
            )
            old_rows = _snapshot_b6_task_rows(db_path)

            events = []

            class RecordingOOSBudgetLedger:
                def __init__(self, *args, **kwargs):
                    events.append("init")

            with patch("scripts.run_v3_task4_once.OOSBudgetLedger", RecordingOOSBudgetLedger):
                result = run_once(
                    repo_root=repo_root,
                    db_path=db_path,
                    audit_path=tmp_path / "audit.json",
                    criteria_root=criteria_root,
                    b4_results_root=b4_root,
                    b5_bundle_dir=bundle_dir,
                    current_snapshot_required=False,
                )

            failed_rows = [
                row for row in old_rows.values()
                if row["task_contract_version"] == "v2" and row["status"] == "failed"
            ]
            self.assertEqual(len(failed_rows), 1)
            failed_row = failed_rows[0]
            self.assertEqual(result["status"], "failed")
            self.assertFalse(result["b6_task_created"])
            self.assertTrue(result["b6_task_reused"])
            self.assertEqual(result["task_id"], failed_row["task_id"])
            self.assertEqual(result["task_key"], failed_row["task_key"])
            self.assertEqual(result["task_contract_version"], "v2")
            self.assertEqual(result["b5_bundle"]["bundle_id"], CURRENT_B5_BUNDLE_ID)
            self.assertEqual(result["b5_bundle"]["manifest_sha256"], CURRENT_B5_BUNDLE_MANIFEST_SHA256)
            self.assertEqual(events, [])

            after_rows = _snapshot_b6_task_rows(db_path)
            self._assert_b6_task_snapshot(old_rows, after_rows)
            successor_rows = [
                row for row in after_rows.values()
                if row["task_contract_version"] == "v3"
            ]
            self.assertEqual(len(successor_rows), 1)
            successor = successor_rows[0]
            self.assertEqual(successor["status"], "queued")
            self.assertIsNone(successor["claimed_at"])
            self.assertEqual(successor["predecessor_task_id"], failed_row["task_id"])
            self.assertEqual(successor["predecessor_task_key"], failed_row["task_key"])
            self.assertEqual(successor["successor_attempt_number"], 1)
            with closing(sqlite3.connect(db_path)) as conn:
                for table in (
                    "oos_budget_state",
                    "oos_budget_reservations",
                    "oos_evaluation_ledgers",
                    "immutable_backtest_reports",
                    "prototype_gate_results_v2",
                ):
                    self.assertEqual(conn.execute(f"select count(*) from {table}").fetchone()[0], 0)

    def test_old_queued_task_is_not_selected_by_new_admission(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            repo_root, db_path, criteria_root, b4_root, bundle_dir = (
                self._prepare_current_lineage_with_existing_task(tmp_path)
            )
            old_rows = _snapshot_b6_task_rows(db_path)

            result = run_once(
                repo_root=repo_root,
                db_path=db_path,
                audit_path=tmp_path / "audit.json",
                criteria_root=criteria_root,
                b4_results_root=b4_root,
                b5_bundle_dir=bundle_dir,
                current_snapshot_required=False,
            )

            failed_rows = [
                row for row in old_rows.values()
                if row["task_contract_version"] == "v2" and row["status"] == "failed"
            ]
            self.assertEqual(len(failed_rows), 1)
            failed_row = failed_rows[0]
            self.assertEqual(result["status"], "failed")
            self.assertFalse(result["b6_task_created"])
            self.assertTrue(result["b6_task_reused"])
            self.assertEqual(result["task_id"], failed_row["task_id"])
            self.assertEqual(result["task_key"], failed_row["task_key"])
            self.assertEqual(result["b5_bundle"]["bundle_id"], CURRENT_B5_BUNDLE_ID)
            self.assertEqual(result["b5_bundle"]["manifest_sha256"], CURRENT_B5_BUNDLE_MANIFEST_SHA256)
            self.assertNotIn("results", result["b5_bundle"])

            after_rows = _snapshot_b6_task_rows(db_path)
            self._assert_b6_task_snapshot(old_rows, after_rows)
            successor_rows = [
                row for row in after_rows.values()
                if row["task_contract_version"] == "v3"
            ]
            self.assertEqual(len(successor_rows), 1)
            successor = successor_rows[0]
            self.assertEqual(successor["status"], "queued")
            self.assertIsNone(successor["claimed_at"])
            self.assertEqual(successor["predecessor_task_id"], failed_row["task_id"])
            self.assertEqual(successor["predecessor_task_key"], failed_row["task_key"])
            self.assertEqual(successor["successor_attempt_number"], 1)
            with closing(sqlite3.connect(db_path)) as conn:
                for table in (
                    "oos_budget_state",
                    "oos_budget_reservations",
                    "oos_evaluation_ledgers",
                    "immutable_backtest_reports",
                    "prototype_gate_results_v2",
                ):
                    self.assertEqual(conn.execute(f"select count(*) from {table}").fetchone()[0], 0)

    def test_explicit_reserialized_bundle_cannot_bypass_pinned_current_identity(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            repo_root, db_path, criteria_root, b4_root, _ = (
                self._prepare_current_lineage_with_existing_task(tmp_path)
            )
            old_rows = _snapshot_b6_task_rows(db_path)
            tampered_parent = tmp_path / "reserialized"
            tampered_parent.mkdir()
            bundle_dir = tampered_parent / CURRENT_B5_BUNDLE_ID
            shutil.copytree(
                REPO_ROOT / "data/pit/v3_b5_validation_bundles" / CURRENT_B5_BUNDLE_ID,
                bundle_dir,
            )
            manifest_path = bundle_dir / "manifest.json"
            parsed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_path.write_text(
                json.dumps(parsed_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            reserialized_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            self.assertNotEqual(reserialized_sha256, CURRENT_B5_BUNDLE_MANIFEST_SHA256)
            (bundle_dir / "manifest.json.sha256").write_text(
                f"{reserialized_sha256}  manifest.json\n",
                encoding="utf-8",
            )

            result = run_once(
                repo_root=repo_root,
                db_path=db_path,
                audit_path=tmp_path / "audit.json",
                criteria_root=criteria_root,
                b4_results_root=b4_root,
                b5_bundle_dir=bundle_dir,
                current_snapshot_required=False,
            )

            self.assertEqual(result["status"], "hard_block:b5_validation_inputs_missing")
            self.assertEqual(result["first_missing_prerequisite"], "b5_validation_inputs")
            self.assertEqual(result["b5_bundle"]["status"], "invalid")
            self.assertFalse(result["b6_task_created"])
            self.assertFalse(result["oos_consumed"])
            after_rows = _snapshot_b6_task_rows(db_path)
            self._assert_b6_task_snapshot(old_rows, after_rows)
            with closing(sqlite3.connect(db_path)) as conn:
                for table in (
                    "oos_budget_state",
                    "oos_budget_reservations",
                    "oos_evaluation_ledgers",
                    "immutable_backtest_reports",
                    "prototype_gate_results_v2",
                ):
                    self.assertEqual(conn.execute(f"select count(*) from {table}").fetchone()[0], 0)

    def test_progressed_current_task_is_reused_without_execution(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            repo_root, criteria_root, bundle_dir = self._prepare_valid_b5_inputs(tmp_path)
            db_path = tmp_path / "strategy.db"
            run_kwargs = {
                "repo_root": repo_root,
                "db_path": db_path,
                "audit_path": tmp_path / "audit.json",
                "criteria_root": criteria_root,
                "b5_bundle_dir": bundle_dir,
                "current_snapshot_required": False,
            }
            protocol_result = run_once(**run_kwargs)
            self.assertEqual(protocol_result["status"], "hard_block:b6_protocol_missing")
            created = run_once(**run_kwargs)
            self.assertEqual(created["status"], "queued")
            self.assertTrue(created["b6_task_created"])

            with closing(StrategyDB(str(db_path))) as strategy_db:
                claimed = strategy_db.claim_b6_task(created["task_id"])
            self.assertIsNotNone(claimed)
            self.assertEqual(claimed.status, "running")

            resumed = run_once(**run_kwargs)

            self.assertEqual(resumed["status"], "running")
            self.assertEqual(resumed["task_status"], claimed.status)
            self.assertEqual(resumed["task_id"], claimed.task_id)
            self.assertEqual(resumed["task_key"], claimed.task_key)
            self.assertFalse(resumed["b6_task_created"])
            self.assertTrue(resumed["b6_task_reused"])
            self.assertEqual(resumed["reason"], "running:b6_validation_task")
            self.assertFalse(resumed["oos_authorized"])
            self.assertFalse(resumed["oos_consumed"])
            with closing(sqlite3.connect(db_path)) as conn:
                for table in (
                    "oos_budget_state",
                    "oos_budget_reservations",
                    "oos_evaluation_ledgers",
                    "immutable_backtest_reports",
                    "prototype_gate_results_v2",
                ):
                    self.assertEqual(conn.execute(f"select count(*) from {table}").fetchone()[0], 0)

    def test_new_task_admission_has_zero_oos_side_effects(self):
        from backend.services.oos_budget_ledger import OOSBudgetLedger as RealOOSBudgetLedger
        from contracts.b6_task import build_b6_task_id, build_b6_task_key

        events = []

        class RecordingOOSBudgetLedger(RealOOSBudgetLedger):
            def __init__(self, db):
                events.append("init")
                super().__init__(db)

            def get_ledger_state(self, *args, **kwargs):
                events.append("get_ledger_state")
                return super().get_ledger_state(*args, **kwargs)

        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            repo_root, criteria_root, bundle_dir = self._prepare_valid_b5_inputs(tmp_path)
            db_path = tmp_path / "strategy.db"
            run_kwargs = {
                "repo_root": repo_root,
                "db_path": db_path,
                "audit_path": tmp_path / "audit.json",
                "criteria_root": criteria_root,
                "b5_bundle_dir": bundle_dir,
                "current_snapshot_required": False,
            }
            self.assertEqual(run_once(**run_kwargs)["status"], "hard_block:b6_protocol_missing")
            events.clear()

            with patch("scripts.run_v3_task4_once.OOSBudgetLedger", RecordingOOSBudgetLedger):
                result = run_once(**run_kwargs)

            self.assertEqual(result["status"], "queued")
            self.assertTrue(result["b6_task_created"])
            self.assertEqual(result["task_status"], "queued")
            self.assertEqual(result["b5_bundle"]["bundle_id"], CURRENT_B5_BUNDLE_ID)
            self.assertEqual(result["b5_bundle"]["manifest_sha256"], CURRENT_B5_BUNDLE_MANIFEST_SHA256)
            self.assertTrue(result["b5_bundle"]["not_authorized_for_b6_oos_gate_promotion_signal"])
            self.assertNotIn("results", result["b5_bundle"])
            self.assertEqual(events, [])

            with closing(sqlite3.connect(db_path)) as conn:
                row = conn.execute(
                    """
                    select task_id, task_key, status, protocol_snapshot_id,
                           b5_bundle_id, b5_bundle_manifest_sha256
                    from b6_validation_tasks
                    """
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(
                    row[2:],
                    ("queued", CURRENT_PROTOCOL_ID, CURRENT_B5_BUNDLE_ID, CURRENT_B5_BUNDLE_MANIFEST_SHA256),
                )
                expected_key = build_b6_task_key(
                    strategy_revision_id=CURRENT_STRATEGY_REVISION_ID,
                    protocol_snapshot_id=CURRENT_PROTOCOL_ID,
                    task_contract_version="v2",
                    b5_bundle_id=CURRENT_B5_BUNDLE_ID,
                    b5_bundle_manifest_sha256=CURRENT_B5_BUNDLE_MANIFEST_SHA256,
                )
                self.assertEqual(row[1], expected_key)
                self.assertEqual(row[0], build_b6_task_id(expected_key))
                counts = {
                    table: conn.execute(f"select count(*) from {table}").fetchone()[0]
                    for table in (
                        "oos_budget_state",
                        "oos_budget_reservations",
                        "oos_evaluation_ledgers",
                        "immutable_backtest_reports",
                        "prototype_gate_results_v2",
                    )
                }
                self.assertEqual(
                    counts,
                    {
                        "oos_budget_state": 0,
                        "oos_budget_reservations": 0,
                        "oos_evaluation_ledgers": 0,
                        "immutable_backtest_reports": 0,
                        "prototype_gate_results_v2": 0,
                    },
                )

    @staticmethod
    def _prepare_valid_b5_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
        source_root = Path(__file__).resolve().parents[1]
        repo_root = (Path(tmp_path) / "repo").resolve()
        directories = (
            "data/pit/b3_execution_input_packages/05f38a2884dc7e47",
            "data/pit/qualification_successors/49b09326f35936c6",
            "data/pit/liquidity_qualification_successors/7c05ece4d3f01086",
            "data/pit/v3_historical_coverage_packages/1e79d26460c0c109",
            "data/pit/v3_formal_data_snapshot_manifests/v3ds_d73256081de82e8a",
            "data/pit/v3_availability_bounded_qualification_successors/12f1b9aac73dfcd4",
            "data/pit/historical_scope_freezes/acbc49159d989a46",
            "data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_005",
            "data/pit/shsz_common_trade_calendars/shsz_common_trade_calendar_v1",
            "data/pit/prototype_gate_v2_criteria",
            f"data/pit/v3_execution_semantics_supplements/{CURRENT_B5_SUPPLEMENT_ID}",
            f"data/pit/v3_b4_is_results/{CURRENT_B4_ID}",
            "data/pit/v3_b5_source_inventories/2fe8321a5f644b9b",
            "data/pit/v3_b5_costs/e405b900f971877f",
            "data/pit/v3_b5_comparisons/d3a78447920b611a",
            f"data/pit/v3_b5_validation_bundles/{CURRENT_B5_BUNDLE_ID}",
            "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership",
        )
        for relative in directories:
            target = repo_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_root / relative, target)

        files = (
            "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/manifest.json",
            "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/manifest.json.sha256",
            "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/input_index.json",
            "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/input_index.json.sha256",
            "docs/verification/TASK4_V3_AI_TECHNICAL_REVIEW.md",
            "backend/services/prototype_gate_criteria_surface.py",
            "backend/services/formal_pit_partition_adapter.py",
            "strategy_core/v3_relative_strength_executor.py",
            "strategy_core/backtest_engine.py",
            "strategy_core/fill_simulator.py",
            "strategy_core/orders.py",
            "strategy_core/transaction_costs.py",
            "strategy_core/portfolio.py",
        )
        for relative in files:
            target = repo_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_root / relative, target)

        criteria_root = repo_root / "data/pit/prototype_gate_v2_criteria"
        bundle_dir = repo_root / "data/pit/v3_b5_validation_bundles" / CURRENT_B5_BUNDLE_ID
        return repo_root, criteria_root, bundle_dir

    @staticmethod
    def _assert_one_b6_task_and_no_oos(db_path: Path) -> None:
        with closing(sqlite3.connect(db_path)) as conn:
            counts = {
                table: conn.execute(f"select count(*) from {table}").fetchone()[0]
                for table in (
                    "b6_validation_tasks",
                    "oos_budget_state",
                    "oos_budget_reservations",
                    "oos_evaluation_ledgers",
                    "immutable_backtest_reports",
                    "prototype_gate_results_v2",
                )
            }
        assert counts == {
            "b6_validation_tasks": 1,
            "oos_budget_state": 0,
            "oos_budget_reservations": 0,
            "oos_evaluation_ledgers": 0,
            "immutable_backtest_reports": 0,
            "prototype_gate_results_v2": 0,
        }

    def test_b5_admission_creates_queued_v2_task_without_oos(self):
        from contracts.b6_task import build_b6_task_id, build_b6_task_key

        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            repo_root, criteria_root, bundle_dir = self._prepare_valid_b5_inputs(tmp_path)
            db_path = tmp_path / "strategy.db"
            audit_path = tmp_path / "audit.json"

            protocol_result = run_once(
                repo_root=repo_root,
                db_path=db_path,
                audit_path=audit_path,
                criteria_root=criteria_root,
                b5_bundle_dir=bundle_dir,
                current_snapshot_required=False,
            )
            self.assertEqual(protocol_result["status"], "hard_block:b6_protocol_missing")

            result = run_once(
                repo_root=repo_root,
                db_path=db_path,
                audit_path=audit_path,
                criteria_root=criteria_root,
                b5_bundle_dir=bundle_dir,
                current_snapshot_required=False,
            )

            self.assertEqual(result["status"], "queued")
            self.assertEqual(result["reason"], "queued:b6_validation_task")
            self.assertIsNone(result["first_missing_prerequisite"])
            self.assertTrue(result["b6_task_created"])
            self.assertFalse(result["b6_task_reused"])
            self.assertEqual(result["task_contract_version"], "v2")
            self.assertEqual(result["task_status"], "queued")
            self.assertFalse(result["oos_authorized"])
            self.assertFalse(result["oos_consumed"])
            self.assertEqual(result["b5_bundle"]["bundle_id"], CURRENT_B5_BUNDLE_ID)
            self.assertNotIn("results", result["b5_bundle"])
            self.assertTrue(result["b5_bundle"]["not_authorized_for_b6_oos_gate_promotion_signal"])

            with closing(sqlite3.connect(db_path)) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "select * from b6_validation_tasks"
                ).fetchone()
                self.assertIsNotNone(row)
                payload = json.loads(row["payload_json"])
                expected_key = build_b6_task_key(
                    strategy_revision_id=payload["strategy_revision_id"],
                    protocol_snapshot_id=payload["protocol_snapshot_id"],
                    task_contract_version="v2",
                    b5_bundle_id=CURRENT_B5_BUNDLE_ID,
                    b5_bundle_manifest_sha256=result["b5_bundle"]["manifest_sha256"],
                )
                self.assertEqual(payload["task_key"], expected_key)
                self.assertEqual(payload["task_id"], build_b6_task_id(expected_key))
            self._assert_one_b6_task_and_no_oos(db_path)

    def test_exact_b5_task_retry_reuses_queued_task(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            repo_root, criteria_root, bundle_dir = self._prepare_valid_b5_inputs(tmp_path)
            db_path = tmp_path / "strategy.db"
            audit_path = tmp_path / "audit.json"
            run_kwargs = {
                "repo_root": repo_root,
                "db_path": db_path,
                "audit_path": audit_path,
                "criteria_root": criteria_root,
                "b5_bundle_dir": bundle_dir,
                "current_snapshot_required": False,
            }

            self.assertEqual(run_once(**run_kwargs)["status"], "hard_block:b6_protocol_missing")
            created = run_once(**run_kwargs)
            reused = run_once(**run_kwargs)

            self.assertTrue(created["b6_task_created"])
            self.assertFalse(created["b6_task_reused"])
            self.assertFalse(reused["b6_task_created"])
            self.assertTrue(reused["b6_task_reused"])
            self.assertEqual(created["status"], "queued")
            self.assertEqual(reused["status"], "queued")
            self.assertEqual(created["task_id"], reused["task_id"])
            self.assertEqual(created["task_key"], reused["task_key"])
            self.assertEqual(created["b5_bundle"], reused["b5_bundle"])
            self.assertFalse(reused["oos_consumed"])
            self._assert_one_b6_task_and_no_oos(db_path)

    def test_task_admission_does_not_instantiate_or_read_oos_ledger(self):
        from backend.services.oos_budget_ledger import OOSBudgetLedger as RealOOSBudgetLedger

        events = []

        class RecordingOOSBudgetLedger(RealOOSBudgetLedger):
            def __init__(self, db):
                events.append("init")
                super().__init__(db)

            def get_ledger_state(self, *args, **kwargs):
                events.append("get_ledger_state")
                return super().get_ledger_state(*args, **kwargs)

        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            repo_root, criteria_root, bundle_dir = self._prepare_valid_b5_inputs(tmp_path)
            db_path = tmp_path / "strategy.db"
            audit_path = tmp_path / "audit.json"
            run_kwargs = {
                "repo_root": repo_root,
                "db_path": db_path,
                "audit_path": audit_path,
                "criteria_root": criteria_root,
                "b5_bundle_dir": bundle_dir,
                "current_snapshot_required": False,
            }

            self.assertEqual(run_once(**run_kwargs)["status"], "hard_block:b6_protocol_missing")
            events.clear()
            with patch("scripts.run_v3_task4_once.OOSBudgetLedger", RecordingOOSBudgetLedger):
                result = run_once(**run_kwargs)

            self.assertEqual(result["status"], "queued")
            self.assertEqual(events, [])
            self._assert_one_b6_task_and_no_oos(db_path)

    def test_revision_profile_ambiguity_blocks_real_caller_without_silent_selection(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            db_path = tmp_path / "strategy.db"
            audit_path = tmp_path / "audit.json"
            criteria_root = tmp_path / "missing-criteria"
            ambiguous = ProtocolSnapshotLookupError("protocol_snapshot_ambiguous")
            with patch.object(
                StrategyDB,
                "get_protocol_snapshot_by_revision_profile",
                side_effect=ambiguous,
            ), patch("scripts.run_v3_task4_once.validate_v3_gate_1_4", return_value=None):
                result = run_once(
                    repo_root=REPO_ROOT,
                    db_path=db_path,
                    audit_path=audit_path,
                    criteria_root=criteria_root,
                    current_snapshot_required=False,
                )
            self.assertEqual(result["status"], "hard_block:b6_protocol_ambiguous")
            self.assertEqual(result["first_missing_prerequisite"], "b6_protocol")
            with closing(sqlite3.connect(db_path)) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM b6_validation_tasks").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM research_protocol_snapshots").fetchone()[0], 0)

    def test_task7_b4_discovery_rejects_frozen_old_b5_lineage(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            old_root = Path(raw_tmp) / "old-results"
            shutil.copytree(RESULT_ROOT / RESULT_ID, old_root / RESULT_ID)
            self.assertIsNone(
                _discover_verified_b4_artifact(
                    repo_root=REPO_ROOT,
                    result_root=old_root,
                )
            )

    def test_b5_admission_precedes_protocol_freezer_for_missing_or_invalid_bundle(self):
        from scripts.publish_v3_execution_semantics import publish_v3_execution_semantics
        import scripts.run_v3_b4_is_once as b4_runner
        import scripts.run_v3_task4_once as task4_runner
        from tests.test_run_v3_b4_is_once import _fixture_data

        repo_root = REPO_ROOT
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            criteria_root = _copy_current_criteria(tmp_path)
            supplement = publish_v3_execution_semantics(
                output_root=tmp_path / "supplements"
            )
            current_b4 = b4_runner.run_v3_b4_is_once(
                repo_root=repo_root,
                output_root=tmp_path / "generated-b4",
                audit_path=tmp_path / "b4-audit.json",
                data_source=_fixture_data(),
                supplement_dir=Path(supplement["path"]),
            )
            self.assertIn(current_b4["status"], {"published", "already_published"})
            self.assertEqual(
                b4_runner.verify_v3_b4_is_result(Path(current_b4["path"]))["status"],
                "verified",
            )
            results_root = tmp_path / "results"
            shutil.copytree(
                Path(current_b4["path"]),
                results_root / current_b4["artifact_id"],
            )

            tampered_parent = tmp_path / "tampered"
            tampered_parent.mkdir()
            tampered_dir = tampered_parent / CURRENT_B5_BUNDLE_ID
            shutil.copytree(
                REPO_ROOT / "data/pit/v3_b5_validation_bundles" / CURRENT_B5_BUNDLE_ID,
                tampered_dir,
            )
            manifest_path = tampered_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["status"] = "tampered"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            for label, bundle_dir in (
                ("missing", tmp_path / "missing-bundle"),
                ("tampered", tampered_dir),
            ):
                with self.subTest(bundle=label):
                    db_path = tmp_path / f"{label}.db"
                    with patch(
                        "scripts.run_v3_task4_once.ResearchProtocolFreezer.freeze_b6_coverage_bound_protocol",
                        side_effect=AssertionError("B5 admission occurred after the protocol freezer"),
                    ), patch.object(
                        task4_runner,
                        "TASK7_B5_SUPPLEMENT_ID",
                        b4_runner.SUPPLEMENT_ID,
                    ), patch.object(
                        task4_runner,
                        "TASK7_B5_SUPPLEMENT_DIR",
                        Path("data/pit/v3_execution_semantics_supplements") / b4_runner.SUPPLEMENT_ID,
                    ), patch.object(
                        task4_runner,
                        "TASK7_B5_SUPPLEMENT_MANIFEST_SHA256",
                        b4_runner.SUPPLEMENT_MANIFEST_SHA256,
                    ):
                        result = run_once(
                            repo_root=repo_root,
                            db_path=db_path,
                            audit_path=tmp_path / f"{label}-audit.json",
                            criteria_root=criteria_root,
                            b4_results_root=results_root,
                            b5_bundle_dir=bundle_dir,
                            current_snapshot_required=False,
                        )

                    self.assertEqual(result["status"], "hard_block:b5_validation_inputs_missing")
                    self.assertEqual(result["first_missing_prerequisite"], "b5_validation_inputs")
                    self.assertEqual(result["b5_bundle"]["status"], "invalid")
                    with closing(sqlite3.connect(db_path)) as conn:
                        self.assertEqual(
                            conn.execute("select count(*) from research_protocol_snapshots").fetchone()[0],
                            0,
                        )
                    self._assert_no_b6_or_oos_rows(db_path)

    def test_existing_protocol_preserves_b4_and_b5_discovery_evidence(self):
        repo_root = REPO_ROOT
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            criteria_root = _copy_current_criteria(tmp_path)
            verified_parent = tmp_path / "verified"
            verified_parent.mkdir()
            bundle_dir = verified_parent / CURRENT_B5_BUNDLE_ID
            shutil.copytree(
                REPO_ROOT / "data/pit/v3_b5_validation_bundles" / CURRENT_B5_BUNDLE_ID,
                bundle_dir,
            )

            db_path = tmp_path / "strategy.db"
            first = run_once(
                repo_root=repo_root,
                db_path=db_path,
                audit_path=tmp_path / "audit.json",
                criteria_root=criteria_root,
                b5_bundle_dir=bundle_dir,
                current_snapshot_required=False,
            )
            self.assertEqual(first["status"], "hard_block:b6_protocol_missing")
            self.assertEqual(first["first_missing_prerequisite"], "b6_protocol")

            second = run_once(
                repo_root=repo_root,
                db_path=db_path,
                audit_path=tmp_path / "audit.json",
                criteria_root=criteria_root,
                b5_bundle_dir=bundle_dir,
                current_snapshot_required=False,
            )
            self.assertEqual(second["status"], "queued")
            self.assertEqual(second["reason"], "queued:b6_validation_task")
            self.assertIsNone(second["first_missing_prerequisite"])
            self.assertTrue(second["b6_task_created"])
            self.assertFalse(second["b6_task_reused"])
            self.assertEqual(second["task_contract_version"], "v2")
            self.assertEqual(second["task_status"], "queued")
            self.assertFalse(second["oos_authorized"])
            self.assertFalse(second["oos_consumed"])

            bundle_manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
            b4_manifest_path = repo_root / "data/pit/v3_b4_is_results" / CURRENT_B4_ID / "manifest.json"
            b4_event_path = b4_manifest_path.with_name("event_result.json")
            expected_b4 = {
                "artifact_id": CURRENT_B4_ID,
                "manifest_sha256": hashlib.sha256(b4_manifest_path.read_bytes()).hexdigest(),
                "event_result_sha256": hashlib.sha256(b4_event_path.read_bytes()).hexdigest(),
            }
            for observed in (first, second):
                self.assertEqual(observed["b4_artifact"]["artifact_id"], expected_b4["artifact_id"])
                self.assertEqual(observed["b4_artifact"]["manifest_sha256"], expected_b4["manifest_sha256"])
                self.assertEqual(observed["b4_artifact"]["event_result_sha256"], expected_b4["event_result_sha256"])
                bound = observed["b5_bundle"]
                self.assertEqual(bound["status"], "verified")
                self.assertEqual(bound["bundle_id"], CURRENT_B5_BUNDLE_ID)
                self.assertEqual(bound["manifest_sha256"], hashlib.sha256((bundle_dir / "manifest.json").read_bytes()).hexdigest())
                self.assertEqual(bound["authorization_scope"], bundle_manifest["authorization_scope"])
                self.assertTrue(bound["not_authorized_for_b6_oos_gate_promotion_signal"])
                self.assertEqual(bound["lineage"], bundle_manifest["lineage"])
                self.assertEqual(bound["is_range"], bundle_manifest["lineage"]["is_range"])
                self.assertEqual(bound["source_inventory"], bundle_manifest["lineage"]["source_inventory"])
                self.assertEqual(bound["result_count"], len(bundle_manifest["results"]))
                self.assertNotIn("results", bound)

            with closing(sqlite3.connect(db_path)) as conn:
                self.assertEqual(
                    conn.execute("select count(*) from research_protocol_snapshots").fetchone()[0],
                    1,
                )
            self._assert_one_b6_task_and_no_oos(db_path)

    def test_b4_b5_lineage_mismatch_blocks_before_protocol_freezer(self):
        from backend.services.research_protocol_freezer import ResearchProtocolFreezer
        from scripts.publish_v3_execution_semantics import publish_v3_execution_semantics
        import scripts.run_v3_b4_is_once as b4_runner
        import scripts.run_v3_task4_once as task4_runner
        from tests.test_run_v3_b4_is_once import _fixture_data

        repo_root = REPO_ROOT
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            supplement = publish_v3_execution_semantics(
                output_root=tmp_path / "supplements"
            )
            current_b4 = b4_runner.run_v3_b4_is_once(
                repo_root=repo_root,
                output_root=tmp_path / "generated-b4",
                audit_path=tmp_path / "b4-audit.json",
                data_source=_fixture_data(),
                supplement_dir=Path(supplement["path"]),
            )
            self.assertIn(current_b4["status"], {"published", "already_published"})
            self.assertEqual(
                b4_runner.verify_v3_b4_is_result(Path(current_b4["path"]))["status"],
                "verified",
            )
            results_root = tmp_path / "results"
            shutil.copytree(
                Path(current_b4["path"]),
                results_root / current_b4["artifact_id"],
            )

            criteria_root = _copy_current_criteria(tmp_path)
            verified_parent = tmp_path / "verified"
            verified_parent.mkdir()
            bundle_dir = verified_parent / B5_BUNDLE_ID
            shutil.copytree(B5_BUNDLE_DIR, bundle_dir)

            freezer_calls = []
            real_freeze = ResearchProtocolFreezer.freeze_b6_coverage_bound_protocol

            def observed_freeze(self, *args, **kwargs):
                freezer_calls.append(True)
                return real_freeze(self, *args, **kwargs)

            with patch.object(
                ResearchProtocolFreezer,
                "freeze_b6_coverage_bound_protocol",
                new=observed_freeze,
            ), patch.object(
                task4_runner,
                "TASK7_B5_SUPPLEMENT_ID",
                b4_runner.SUPPLEMENT_ID,
            ), patch.object(
                task4_runner,
                "TASK7_B5_SUPPLEMENT_DIR",
                Path("data/pit/v3_execution_semantics_supplements") / b4_runner.SUPPLEMENT_ID,
            ), patch.object(
                task4_runner,
                "TASK7_B5_SUPPLEMENT_MANIFEST_SHA256",
                b4_runner.SUPPLEMENT_MANIFEST_SHA256,
            ):
                result = run_once(
                    repo_root=repo_root,
                    db_path=tmp_path / "strategy.db",
                    audit_path=tmp_path / "audit.json",
                    criteria_root=criteria_root,
                    b4_results_root=results_root,
                    b5_bundle_dir=bundle_dir,
                    current_snapshot_required=False,
                )

            self.assertEqual(freezer_calls, [], "lineage mismatch reached the protocol freezer")
            self.assertEqual(result["status"], "hard_block:b5_validation_inputs_missing")
            self.assertEqual(result["first_missing_prerequisite"], "b5_validation_inputs")
            self.assertEqual(result["b5_bundle"]["status"], "invalid")
            self.assertEqual(result["b5_bundle"]["reason"], "bundle lineage mismatch")
            with closing(sqlite3.connect(tmp_path / "strategy.db")) as conn:
                self.assertEqual(
                    conn.execute("select count(*) from research_protocol_snapshots").fetchone()[0],
                    0,
                )
            self._assert_no_b6_or_oos_rows(tmp_path / "strategy.db")

    @staticmethod
    def _assert_no_b6_or_oos_rows(db_path: Path) -> None:
        with closing(sqlite3.connect(db_path)) as conn:
            counts = {
                table: conn.execute(f"select count(*) from {table}").fetchone()[0]
                for table in (
                    "b6_validation_tasks",
                    "oos_budget_state",
                    "oos_budget_reservations",
                    "oos_evaluation_ledgers",
                    "immutable_backtest_reports",
                    "prototype_gate_results_v2",
                )
            }
        assert counts == {
            "b6_validation_tasks": 0,
            "oos_budget_state": 0,
            "oos_budget_reservations": 0,
            "oos_evaluation_ledgers": 0,
            "immutable_backtest_reports": 0,
            "prototype_gate_results_v2": 0,
        }

    def test_missing_and_tampered_b5_bundle_hard_block_before_b6(self):
        repo_root = REPO_ROOT
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            criteria_root = _copy_current_criteria(tmp_path)
            production_audit = repo_root / "docs/verification/task4_v3_one_shot_audit.json"
            production_audit_before = production_audit.read_bytes()

            tampered_parent = tmp_path / "tampered"
            tampered_parent.mkdir()
            tampered_dir = tampered_parent / CURRENT_B5_BUNDLE_ID
            shutil.copytree(
                REPO_ROOT / "data/pit/v3_b5_validation_bundles" / CURRENT_B5_BUNDLE_ID,
                tampered_dir,
            )
            manifest_path = tampered_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["status"] = "tampered"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            for label, bundle_dir in (
                ("missing", tmp_path / "missing-bundle"),
                ("tampered", tampered_dir),
            ):
                with self.subTest(bundle=label):
                    db_path = tmp_path / f"{label}.db"
                    audit_path = tmp_path / f"{label}-audit.json"
                    result = run_once(
                        repo_root=repo_root,
                        db_path=db_path,
                        audit_path=audit_path,
                        criteria_root=criteria_root,
                        b5_bundle_dir=bundle_dir,
                        current_snapshot_required=False,
                    )
                    assert result["status"] == "hard_block:b5_validation_inputs_missing"
                    assert result["first_missing_prerequisite"] == "b5_validation_inputs"
                    assert result["b5_bundle"]["status"] == "invalid"
                    assert result["oos_consumed"] is False
                    assert result["b6_task_created"] is False
                    assert audit_path.is_file()
                    self._assert_no_b6_or_oos_rows(db_path)

            assert production_audit.read_bytes() == production_audit_before

    def test_verified_b5_bundle_binds_all_results_before_next_prerequisite(self):
        repo_root = REPO_ROOT
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            criteria_root = _copy_current_criteria(tmp_path)
            verified_parent = tmp_path / "verified"
            verified_parent.mkdir()
            bundle_dir = verified_parent / CURRENT_B5_BUNDLE_ID
            shutil.copytree(
                REPO_ROOT / "data/pit/v3_b5_validation_bundles" / CURRENT_B5_BUNDLE_ID,
                bundle_dir,
            )
            result = run_once(
                repo_root=repo_root,
                db_path=tmp_path / "strategy.db",
                audit_path=tmp_path / "audit.json",
                criteria_root=criteria_root,
                b5_bundle_dir=bundle_dir,
                current_snapshot_required=False,
            )

            manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
            bound = result["b5_bundle"]
            assert result["status"] == "hard_block:b6_protocol_missing"
            assert result["first_missing_prerequisite"] == "b6_protocol"
            assert bound["status"] == "verified"
            assert bound["bundle_id"] == manifest["bundle_id"]
            assert bound["manifest_sha256"] == hashlib.sha256(
                (bundle_dir / "manifest.json").read_bytes()
            ).hexdigest()
            assert bound["is_range"] == manifest["lineage"]["is_range"]
            assert bound["source_inventory"] == manifest["lineage"]["source_inventory"]
            assert set(manifest["results"]) == {
                "base_transaction_cost",
                "stress_transaction_cost",
                "benchmark_comparison",
                "same_universe_control_comparison",
            }
            assert bound["result_count"] == len(manifest["results"])
            assert "results" not in bound
            assert result["oos_consumed"] is False
            assert result["b6_task_created"] is False
            self._assert_no_b6_or_oos_rows(tmp_path / "strategy.db")


def test_empty_db_materializes_provenance_without_oos(tmp_path: Path):
    result = run_once(repo_root=REPO_ROOT, db_path=tmp_path / "empty.db", audit_path=tmp_path / "audit.json", criteria_root=tmp_path / "missing-criteria", current_snapshot_required=False)
    assert result["status"] == "hard_block:b6_criteria_missing"
    assert result["reason"] == "hard_block:b6_criteria_missing"
    assert result["oos_consumed"] is False
    assert set(result["created_ids"]) == {"template", "universe", "strategy_revision", "lifecycle"}


def test_materialization_requires_real_criteria_and_b3_freezer_contract(tmp_path: Path):
    result = run_once(repo_root=REPO_ROOT, db_path=tmp_path / "empty.db", audit_path=tmp_path / "audit.json", criteria_root=tmp_path / "missing-criteria", current_snapshot_required=False)
    assert result["first_missing_prerequisite"] == "b6_criteria"
    assert result["gate1_4_validation"]["status"] == "valid"


def test_one_shot_materializes_real_provenance_once_and_stops_before_b6(tmp_path: Path):
    repo_root = REPO_ROOT
    db_path = tmp_path / "strategy.db"
    with sqlite3.connect(repo_root / "data/research.db") as research_conn:
        approval_before = research_conn.execute(
            "select approval_card_id, card_data from agent_approval_cards order by approval_card_id"
        ).fetchall()

    first = run_once(repo_root=repo_root, db_path=db_path, audit_path=tmp_path / "audit.json", criteria_root=tmp_path / "missing-criteria", current_snapshot_required=False)

    assert first["first_missing_prerequisite"] == "b6_criteria"
    assert set(first["created_ids"]) == {"template", "universe", "strategy_revision", "lifecycle"}
    assert first["reused_ids"] == {}
    assert first["oos_consumed"] is False
    assert first["b6_task_created"] is False
    assert first["provenance_validation"]["is_valid"] is True

    with sqlite3.connect(db_path) as conn:
        counts = {
            table: conn.execute(f"select count(*) from {table}").fetchone()[0]
            for table in (
                "strategy_template_definitions",
                "backtest_universe_specs",
                "strategy_drafts",
                "strategy_lifecycle_states",
                "b6_validation_tasks",
                "oos_budget_reservations",
            )
        }
        universe_payload = json.loads(
            conn.execute("select payload_json from backtest_universe_specs").fetchone()[0]
        )
    assert counts == {
        "strategy_template_definitions": 1,
        "backtest_universe_specs": 1,
        "strategy_drafts": 1,
        "strategy_lifecycle_states": 1,
        "b6_validation_tasks": 0,
        "oos_budget_reservations": 0,
    }
    assert universe_payload["membership_source"] == "B3:05f38a2884dc7e47:sw2021_tushare_l1_partitions"
    assert universe_payload["membership_snapshot_ids"] == [
        "pims_traderlens_v2_shsz_sw2021_pit_005"
    ]
    assert universe_payload["membership_effective_from"] == "1984-05-09"
    assert universe_payload["membership_effective_to"] == "2026-06-05"
    assert universe_payload["snapshot_date"] == "2026-07-17"
    assert universe_payload["quality_status"] == "ok"

    second = run_once(repo_root=repo_root, db_path=db_path, audit_path=tmp_path / "audit.json", criteria_root=tmp_path / "missing-criteria", current_snapshot_required=False)

    assert second["first_missing_prerequisite"] == "b6_criteria"
    assert second["gate1_4_validation"]["status"] == "valid"
    assert second["created_ids"] == {}
    assert set(second["reused_ids"]) == {"template", "universe", "strategy_revision", "lifecycle"}
    assert second["oos_consumed"] is False
    with sqlite3.connect(repo_root / "data/research.db") as research_conn:
        approval_after = research_conn.execute(
            "select approval_card_id, card_data from agent_approval_cards order by approval_card_id"
        ).fetchall()
    assert approval_after == approval_before


def test_one_shot_rejects_existing_conflicting_provenance_without_overwrite(tmp_path: Path):
    repo_root = REPO_ROOT
    db_path = tmp_path / "strategy.db"
    first = run_once(repo_root=repo_root, db_path=db_path, audit_path=tmp_path / "audit.json", current_snapshot_required=False)
    template_id = first["created_ids"]["template"]

    with sqlite3.connect(db_path) as conn:
        conn.execute("drop trigger prevent_strategy_template_definitions_update")
        conn.execute(
            "update strategy_template_definitions set payload_json = ? where template_id = ?",
            ('{"tampered":true}', template_id),
        )
        conn.commit()

    second = run_once(repo_root=repo_root, db_path=db_path, audit_path=tmp_path / "audit.json", current_snapshot_required=False)

    assert second["status"] == "hard_block:strategy_provenance_conflict"
    assert second["oos_consumed"] is False
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "select payload_json from strategy_template_definitions where template_id = ?",
            (template_id,),
        ).fetchone()[0] == '{"tampered":true}'


def test_one_shot_test_audit_is_isolated_from_production_audit(tmp_path: Path):
    repo_root = REPO_ROOT
    production_audit = repo_root / "docs/verification/task4_v3_one_shot_audit.json"
    audit_path = tmp_path / "audit.json"
    before = production_audit.read_bytes()

    result = run_once(
        repo_root=repo_root,
        db_path=tmp_path / "strategy.db",
        audit_path=audit_path,
        criteria_root=tmp_path / "missing-criteria",
        current_snapshot_required=False,
    )

    assert result["status"] == "hard_block:b6_criteria_missing"
    assert audit_path.is_file()
    assert json.loads(audit_path.read_text(encoding="utf-8"))["status"] == result["status"]
    assert production_audit.read_bytes() == before


def test_one_shot_discovers_gate5_criteria_and_blocks_b5_before_protocol(tmp_path: Path):
    from scripts.publish_v3_gate_criteria import publish_criteria_pair

    criteria_root = tmp_path / "criteria"
    publish_criteria_pair(output_root=criteria_root)
    result = run_once(
        repo_root=REPO_ROOT,
        db_path=tmp_path / "strategy.db",
        audit_path=tmp_path / "audit.json",
        criteria_root=criteria_root,
        b5_bundle_dir=tmp_path / "missing-bundle",
        current_snapshot_required=False,
    )
    assert result["status"] == "hard_block:b5_validation_inputs_missing"
    assert result["first_missing_prerequisite"] == "b5_validation_inputs"
    assert result["gate5_validation"]["status"] == "valid"
    assert "protocol" not in result["created_ids"]
    assert "protocol" not in result["reused_ids"]
    assert result["b4_artifact"]["artifact_id"] == CURRENT_B4_ID
    assert result["b4_artifact"]["supplement_id"] == CURRENT_B5_SUPPLEMENT_ID
    assert result["b4_artifact"]["manifest_sha256"]
    assert result["b4_artifact"]["event_result_sha256"]
    assert result["b4_artifact"]["is_range"] == {"start": "2025-06-27", "end": "2026-03-19"}
    assert result["b4_artifact"]["qualification_status"] == "pass"
    assert result["b4_artifact"]["canary_blocked_count"] == 6
    assert result["b4_artifact"]["future_violations"] == 0
    assert result["b4_artifact"]["oos_read_count"] == 0
    assert result["missing_b5_validation_inputs"] == ["verified_b5_bundle"]
    assert result["b5_bundle"]["status"] == "invalid"
    assert result["oos_consumed"] is False
    assert result["b6_task_created"] is False

    with closing(sqlite3.connect(tmp_path / "strategy.db")) as conn:
        assert conn.execute("select count(*) from research_protocol_snapshots").fetchone()[0] == 0
        for table in (
            "b6_validation_tasks",
            "oos_budget_state",
            "oos_budget_reservations",
            "oos_evaluation_ledgers",
            "immutable_backtest_reports",
            "prototype_gate_results_v2",
        ):
            assert conn.execute(f"select count(*) from {table}").fetchone()[0] == 0

    second = run_once(
        repo_root=REPO_ROOT,
        db_path=tmp_path / "strategy.db",
        audit_path=tmp_path / "audit.json",
        criteria_root=criteria_root,
        b5_bundle_dir=tmp_path / "missing-bundle",
        current_snapshot_required=False,
    )
    assert second["status"] == "hard_block:b5_validation_inputs_missing"
    assert "protocol" not in second["created_ids"]
    assert "protocol" not in second["reused_ids"]
    assert second["b4_artifact"] == result["b4_artifact"]
    assert second["b5_bundle"]["status"] == "invalid"
    with closing(sqlite3.connect(tmp_path / "strategy.db")) as conn:
        assert conn.execute("select count(*) from research_protocol_snapshots").fetchone()[0] == 0
        for table in (
            "b6_validation_tasks",
            "oos_budget_state",
            "oos_budget_reservations",
            "oos_evaluation_ledgers",
            "immutable_backtest_reports",
            "prototype_gate_results_v2",
        ):
            assert conn.execute(f"select count(*) from {table}").fetchone()[0] == 0


def test_one_shot_ignores_old_b4_lineage_artifacts(tmp_path: Path):
    from scripts.publish_v3_gate_criteria import publish_criteria_pair

    results_root = tmp_path / "results"
    shutil.copytree(RESULT_ROOT / "2fa4edb45e567104", results_root / "2fa4edb45e567104")
    criteria_root = tmp_path / "criteria"
    publish_criteria_pair(output_root=criteria_root)
    result = run_once(
        repo_root=REPO_ROOT,
        db_path=tmp_path / "strategy.db",
        audit_path=tmp_path / "audit.json",
        criteria_root=criteria_root,
        b4_results_root=results_root,
        current_snapshot_required=False,
    )
    assert result["status"] == "hard_block:b4_event_backtest_missing"
    assert "b4_artifact" not in result


def test_one_shot_rejects_tampered_latest_b4_artifact(tmp_path: Path):
    from scripts.publish_v3_gate_criteria import publish_criteria_pair

    results_root = tmp_path / "results"
    shutil.copytree(RESULT_ROOT / CURRENT_B4_ID, results_root / CURRENT_B4_ID)
    manifest_path = results_root / CURRENT_B4_ID / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["supplement"]["manifest_sha256"] = "tampered"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    criteria_root = tmp_path / "criteria"
    publish_criteria_pair(output_root=criteria_root)
    result = run_once(
        repo_root=REPO_ROOT,
        db_path=tmp_path / "strategy.db",
        audit_path=tmp_path / "audit.json",
        criteria_root=criteria_root,
        b4_results_root=results_root,
        current_snapshot_required=False,
    )
    assert result["status"] == "hard_block:b4_event_backtest_invalid"
    assert "sidecar" in result["detail"] or "binding" in result["detail"]


def test_one_shot_rejects_conflicting_latest_b4_artifacts(tmp_path: Path):
    from scripts.publish_v3_gate_criteria import publish_criteria_pair

    results_root = tmp_path / "results"
    shutil.copytree(RESULT_ROOT / CURRENT_B4_ID, results_root / CURRENT_B4_ID)
    conflict_dir = results_root / "staging"
    shutil.copytree(RESULT_ROOT / CURRENT_B4_ID, conflict_dir)
    conflict_manifest_path = conflict_dir / "manifest.json"
    conflict_manifest = json.loads(conflict_manifest_path.read_text(encoding="utf-8"))
    conflict_manifest["universe"]["record_count"] = 0
    conflict_payload = {key: value for key, value in conflict_manifest.items() if key != "artifact_id"}
    canonical = json.dumps(conflict_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    conflict_manifest["artifact_id"] = hashlib.sha256(canonical).hexdigest()[:16]
    conflict_manifest_path.write_bytes(json.dumps(conflict_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    conflict_manifest_path.with_name("manifest.json.sha256").write_text(
        f"{hashlib.sha256(conflict_manifest_path.read_bytes()).hexdigest()}  manifest.json\n",
        encoding="utf-8",
    )
    conflict_dir.rename(results_root / conflict_manifest["artifact_id"])
    criteria_root = tmp_path / "criteria"
    publish_criteria_pair(output_root=criteria_root)
    result = run_once(
        repo_root=REPO_ROOT,
        db_path=tmp_path / "strategy.db",
        audit_path=tmp_path / "audit.json",
        criteria_root=criteria_root,
        b4_results_root=results_root,
        current_snapshot_required=False,
    )
    assert result["status"] == "hard_block:b4_event_backtest_invalid"
    assert "multiple" in result["detail"]
