from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import json
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch


def _install_unused_execution_imports() -> None:
    """Keep this test focused on preflight; no production executor is imported."""
    executor = types.ModuleType("backend.services.b6_same_draw_executor")
    executor.PreparedSupplementToken = object
    sys.modules.setdefault("backend.services.b6_same_draw_executor", executor)

    flow = types.ModuleType("backend.services.b6_validation_flow")
    flow.B6ValidationFlow = object
    sys.modules.setdefault("backend.services.b6_validation_flow", flow)

    runner = types.ModuleType("scripts.run_v3_task4_once")
    runner.V3_B5_BUNDLE_ROOT = Path("data/pit/v3_b5_validation_bundles")
    runner._discover_verified_b4_artifact = lambda **_: None
    runner._discover_verified_b5_bundle = lambda **_: {"status": "invalid"}
    sys.modules.setdefault("scripts.run_v3_task4_once", runner)

    semantics = types.ModuleType("scripts.verify_v3_execution_semantics")
    semantics.verify_v3_execution_semantics = lambda *_, **__: {"status": "invalid"}
    sys.modules.setdefault("scripts.verify_v3_execution_semantics", semantics)


def _new_task_db(temp_root: Path, bundle_id: str, bundle_sha: str):
    from backend.db.strategy import StrategyDB
    from contracts.b6_task import B6ValidationTask, build_b6_task_id, build_b6_task_key
    from contracts.strategy import (
        BacktestUniverseSpec,
        ResearchProtocolSnapshot,
        StrategyDraft,
        StrategyLifecycleState,
        compute_b6_protocol_id_from_fields,
    )

    db = StrategyDB(str(temp_root / "strategy.db"))
    day = date(2024, 1, 2)
    universe = BacktestUniverseSpec(
        universe_spec_id="formal_preflight_test_universe",
        universe_rule_type="point_in_time_membership",
        membership_source="formal_preflight_test",
        membership_effective_from=day,
        membership_effective_to=day,
        snapshot_date=day,
        membership_snapshot_ids=("membership_test",),
        quality_status="ok",
    )
    fields = {
        "protocol_profile": "b6_coverage_bound",
        "theme_id": "formal_preflight_test_theme",
        "hypothesis_source_snapshot_id": "formal_preflight_test_hypothesis",
        "strategy_revision_id": "formal_preflight_test_revision",
        "sample_split_rule_id": "formal_preflight_test_split",
        "oos_window_rule_id": "formal_preflight_test_window_rule",
        "oos_window_rule_params_json": "{}",
        "oos_window_start": day,
        "oos_window_end": day,
        "shared_oos_window_id": "formal_preflight_test_window",
        "backtest_universe_spec_id": universe.universe_spec_id,
        "data_snapshot_id": "formal_preflight_test_snapshot",
        "data_snapshot_hash": "2" * 64,
        "kill_criteria_snapshot_id": "formal_preflight_test_kill",
        "prototype_gate_thresholds_json": '{"threshold":0.5}',
        "strategy_config_hash": "1" * 64,
        "gate_criteria_hash": "3" * 64,
        "availability_successor_id": "formal_preflight_test_successor",
        "availability_successor_manifest_hash": "a" * 64,
        "availability_successor_algorithm_hash": "successor_algorithm",
        "predecessor_qualification_id": "formal_preflight_test_predecessor",
        "predecessor_qualification_manifest_hash": "b" * 64,
        "predecessor_qualification_status": "availability_bounded_qualified",
        "predecessor_qualification_algorithm_hash": "predecessor_algorithm",
        "coverage_package_id": "formal_preflight_test_coverage",
        "coverage_manifest_hash": "c" * 64,
        "coverage_algorithm_hash": "coverage_algorithm",
        "source_scope_hash": "scope_hash",
        "data_requirements_hash": "requirements_hash",
        "expected_stock_days": 10,
        "complete_stock_days": 9,
        "unavailable_stock_days": 1,
        "gate_snapshot_id": "formal_preflight_test_gate",
        "gate_content_hash": "gate_hash",
        "kill_content_hash": "kill_hash",
    }
    protocol = ResearchProtocolSnapshot(
        protocol_snapshot_id=compute_b6_protocol_id_from_fields(**fields),
        frozen_at=datetime(2026, 8, 21, 12),
        frozen_by="formal_preflight_test",
        **fields,
    )
    db.store_backtest_universe(universe)
    db.create_strategy_draft(
        StrategyDraft(
            strategy_revision_id=protocol.strategy_revision_id,
            theme_id=protocol.theme_id,
            hypothesis_id=protocol.hypothesis_source_snapshot_id,
            strategy_template_id="formal_preflight_test_template",
            strategy_template_version="v1",
            strategy_template_hash="template_hash",
            hypothesis_source_snapshot_id=protocol.hypothesis_source_snapshot_id,
            backtest_universe_spec_id=universe.universe_spec_id,
            strategy_config_json="{}",
            sample_split_rule_id=protocol.sample_split_rule_id,
            created_at=datetime(2026, 8, 21, 12),
        ),
        StrategyLifecycleState(
            lifecycle_state_id="formal_preflight_test_lifecycle",
            strategy_revision_id=protocol.strategy_revision_id,
            state_version=1,
            state="draft",
            source_record_id="formal_preflight_test",
            recorded_at=datetime(2026, 8, 21, 12),
            recorded_by="formal_preflight_test",
        ),
    )
    db.store_protocol_snapshot(protocol)
    task_key = build_b6_task_key(
        strategy_revision_id=protocol.strategy_revision_id,
        protocol_snapshot_id=protocol.protocol_snapshot_id,
        task_contract_version="v2",
        b5_bundle_id=bundle_id,
        b5_bundle_manifest_sha256=bundle_sha,
    )
    task = B6ValidationTask(
        task_id=build_b6_task_id(task_key),
        task_key=task_key,
        task_type="b6_validation",
        task_contract_version="v2",
        strategy_revision_id=protocol.strategy_revision_id,
        protocol_snapshot_id=protocol.protocol_snapshot_id,
        status="queued",
        created_at=datetime(2026, 8, 21, 12),
        b5_bundle_id=bundle_id,
        b5_bundle_manifest_sha256=bundle_sha,
    )
    db.create_or_get_b6_task(task)
    return db, task, protocol


def _strategy_scope_binding(protocol) -> dict:
    return {
        "snapshot_id": "ssu_formal_preflight_test",
        "path": "data/pit/strategy_scoped_universe_snapshots/ssu_formal_preflight_test",
        "manifest_sha256": "d" * 64,
        "scope_identity_sha256": "e" * 64,
        "daily_members_sha256": "f" * 64,
        "market_scope": ["SH", "SZ"],
        "protocol_snapshot_id": protocol.protocol_snapshot_id,
        "oos_window": {
            "start": protocol.oos_window_start.isoformat(),
            "end": protocol.oos_window_end.isoformat(),
        },
    }


def _pass_through_strategy_scope(raw_universe, *, expected_binding, **_kwargs):
    start = date.fromisoformat(expected_binding["oos_window"]["start"])
    end = date.fromisoformat(expected_binding["oos_window"]["end"])
    return SimpleNamespace(
        trading_dates=raw_universe.common_trading_dates(start, end),
        symbols_as_of=raw_universe.symbols_as_of,
    )


class TestB6FormalPreflightAdmission(unittest.TestCase):
    def test_b4_is_verified_from_b5_lineage_without_task4_runner(self) -> None:
        from backend.services.b6_validation_worker import B6ValidationWorker

        temporary_root = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_root.cleanup)
        root = Path(temporary_root.name)
        artifact_id = "verified_b4_artifact"
        artifact_dir = root / "data/pit/v3_b4_is_results" / artifact_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "artifact_id": artifact_id,
            "strategy_revision_id": "verified_revision",
            "protocol_snapshot_id": "verified_protocol",
            "is_range": {"start": "2025-06-27", "end": "2026-03-19"},
        }
        (artifact_dir / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        verification = {
            "status": "verified",
            "artifact_id": artifact_id,
            "manifest_sha256": "1" * 64,
            "event_result_sha256": "2" * 64,
        }
        verifier_module = types.ModuleType("scripts.run_v3_b4_is_once")
        verifier_module.verify_v3_b4_is_result = lambda path, *, repo_root: verification
        b5 = {
            "lineage": {
                "strategy_revision_id": "verified_revision",
                "protocol_snapshot_id": "verified_protocol",
                "b4": {
                    "artifact_id": artifact_id,
                    "manifest_sha256": verification["manifest_sha256"],
                    "event_sha256": verification["event_result_sha256"],
                }
            }
        }

        prior_runner = sys.modules.pop("scripts.run_v3_task4_once", None)
        try:
            with patch.dict(sys.modules, {"scripts.run_v3_b4_is_once": verifier_module}):
                worker = B6ValidationWorker(None, repo_root=root)
                result = worker._discover_b4(b5)
            self.assertEqual(result["artifact_id"], artifact_id)
            self.assertEqual(result["manifest_sha256"], verification["manifest_sha256"])
            self.assertEqual(result["event_result_sha256"], verification["event_result_sha256"])
            self.assertEqual(result["path"], str(artifact_dir.resolve()))
            self.assertEqual(result["strategy_revision_id"], manifest["strategy_revision_id"])
            self.assertEqual(result["protocol_snapshot_id"], manifest["protocol_snapshot_id"])
            self.assertNotIn("scripts.run_v3_task4_once", sys.modules)
        finally:
            sys.modules.pop("scripts.run_v3_task4_once", None)
            if prior_runner is not None:
                sys.modules["scripts.run_v3_task4_once"] = prior_runner

    def test_b4_verification_must_match_every_b5_lineage_hash(self) -> None:
        from backend.services.b6_validation_worker import B6ValidationWorker, _PreflightInvariant

        temporary_root = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_root.cleanup)
        root = Path(temporary_root.name)
        artifact_id = "verified_b4_artifact"
        artifact_dir = root / "data/pit/v3_b4_is_results" / artifact_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "manifest.json").write_text(
            '{"artifact_id":"verified_b4_artifact","strategy_revision_id":"r","protocol_snapshot_id":"p","is_range":{}}',
            encoding="utf-8",
        )
        verification = {
            "status": "verified",
            "artifact_id": artifact_id,
            "manifest_sha256": "1" * 64,
            "event_result_sha256": "2" * 64,
        }
        verifier_module = types.ModuleType("scripts.run_v3_b4_is_once")
        verifier_module.verify_v3_b4_is_result = lambda *_args, **_kwargs: verification
        with patch.dict(sys.modules, {"scripts.run_v3_b4_is_once": verifier_module}):
            worker = B6ValidationWorker(None, repo_root=root)
            for mismatched_field in ("manifest_sha256", "event_sha256"):
                with self.subTest(field=mismatched_field):
                    expected = {
                        "artifact_id": artifact_id,
                        "manifest_sha256": verification["manifest_sha256"],
                        "event_sha256": verification["event_result_sha256"],
                    }
                    expected[mismatched_field] = "3" * 64
                    b5 = {
                        "lineage": {
                            "strategy_revision_id": "r",
                            "protocol_snapshot_id": "p",
                            "b4": expected,
                        }
                    }
                    with self.assertRaises(_PreflightInvariant):
                        worker._discover_b4(b5)

    def test_b4_lineage_rejects_path_escape_and_revision_mismatch(self) -> None:
        from backend.services.b6_validation_worker import B6ValidationWorker, _PreflightInvariant

        temporary_root = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_root.cleanup)
        root = Path(temporary_root.name)
        worker = B6ValidationWorker(None, repo_root=root)
        path_escape = {
            "lineage": {
                "strategy_revision_id": "r",
                "protocol_snapshot_id": "p",
                "b4": {
                    "artifact_id": "../outside",
                    "manifest_sha256": "1" * 64,
                    "event_sha256": "2" * 64,
                },
            }
        }
        with self.assertRaises(_PreflightInvariant):
            worker._discover_b4(path_escape)

        artifact_id = "verified_b4_artifact"
        artifact_dir = root / "data/pit/v3_b4_is_results" / artifact_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "manifest.json").write_text(
            json.dumps({
                "artifact_id": artifact_id,
                "strategy_revision_id": "different_revision",
                "protocol_snapshot_id": "p",
                "is_range": {},
            }),
            encoding="utf-8",
        )
        verifier_module = types.ModuleType("scripts.run_v3_b4_is_once")
        verifier_module.verify_v3_b4_is_result = lambda *_args, **_kwargs: {
            "status": "verified",
            "artifact_id": artifact_id,
            "manifest_sha256": "1" * 64,
            "event_result_sha256": "2" * 64,
        }
        mismatched_revision = {
            "lineage": {
                "strategy_revision_id": "r",
                "protocol_snapshot_id": "p",
                "b4": {
                    "artifact_id": artifact_id,
                    "manifest_sha256": "1" * 64,
                    "event_sha256": "2" * 64,
                },
            }
        }
        with patch.dict(sys.modules, {"scripts.run_v3_b4_is_once": verifier_module}):
            with self.assertRaises(_PreflightInvariant):
                worker._discover_b4(mismatched_revision)

    def test_b5_task_identity_mismatch_stops_before_b4_or_ledger(self) -> None:
        _install_unused_execution_imports()
        from backend.services.b6_validation_worker import B6ValidationWorker
        from backend.services.v3_b5_bundle import independent_verifier_identity

        class CountingLedger:
            def __init__(self):
                self.read_calls = 0
                self.reserve_calls = 0

            def get_ledger_state(self, *_args, **_kwargs):
                self.read_calls += 1
                raise AssertionError("ledger must not be read for a mismatched B5 task")

            def reserve_oos_draw(self, **_kwargs):
                self.reserve_calls += 1
                raise AssertionError("mismatched B5 task must not reserve OOS")

        with tempfile.TemporaryDirectory() as temp_dir:
            for mismatched_field in ("bundle_id", "manifest_sha256"):
                with self.subTest(field=mismatched_field):
                    root = Path(temp_dir) / mismatched_field
                    root.mkdir()
                    db, task, protocol = _new_task_db(
                        root,
                        f"formal-b5-{mismatched_field}",
                        "4" * 64,
                    )
                    try:
                        expected_b4 = {
                            "artifact_id": "b4-test",
                            "manifest_sha256": "5" * 64,
                            "event_sha256": "6" * 64,
                        }
                        b5 = {
                            "status": "verified",
                            "bundle_id": task.b5_bundle_id,
                            "manifest_sha256": task.b5_bundle_manifest_sha256,
                            "authorization_scope": "v3_b5_formal_b6_preflight",
                            "not_authorized_for_b6_oos_gate_promotion_signal": False,
                            "verifier_identity": independent_verifier_identity(),
                            "lineage": {"b4": expected_b4},
                        }
                        bad_b5 = dict(b5)
                        bad_b5[mismatched_field] = "wrong-identity"
                        ledger = CountingLedger()
                        worker = B6ValidationWorker(db, repo_root=root, ledger=ledger)
                        worker._discover_b5 = lambda _task, current=bad_b5: current
                        b4_calls = []
                        worker._discover_b4 = lambda *_args: b4_calls.append(True)

                        result = worker.run_task(task.task_id)

                        self.assertEqual(result.status, "failed")
                        self.assertEqual(result.reason, "invariant_error")
                        self.assertIn(
                            "B5 bundle ID does not match task"
                            if mismatched_field == "bundle_id"
                            else "B5 manifest hash does not match task",
                            db.get_b6_task_by_id(task.task_id).blocking_reason_detail,
                        )
                        self.assertEqual(b4_calls, [])
                        self.assertEqual(ledger.read_calls, 0)
                        self.assertEqual(ledger.reserve_calls, 0)
                    finally:
                        db.close()

    def test_lifecycle_scan_reports_missing_symbol_before_unsupported_symbol_short_circuit(self) -> None:
        _install_unused_execution_imports()
        from backend.services.b6_validation_worker import B6ValidationWorker, _PreflightBlocked

        day = date(2026, 3, 20)

        class MixedUniverseAdapter:
            def __init__(self, *_args, **_kwargs):
                self.formal_binding_verified = True

            def common_trading_dates(self, start, end):
                return (start,) if start == end else ()

            def symbols_as_of(self, _day):
                return ("832317.BJ", "000991.SZ")

            def is_eligible(self, symbol, _day):
                if symbol == "000991.SZ":
                    raise KeyError(f"Unknown stock basic symbol: {symbol}")
                return True

            def get_daily_status(self, _symbol, _day):
                raise AssertionError("lifecycle failures must stop daily reads")

            def get_daily_bar(self, _symbol, _day):
                raise AssertionError("lifecycle failures must stop bar reads")

        binding = {
            "formal_snapshot": {},
            "b3_execution_input": {},
            "stock_basic_lifecycle": {},
            "membership": {},
        }
        protocol = SimpleNamespace(
            protocol_snapshot_id="formal-preflight-test-protocol",
            oos_window_start=day,
            oos_window_end=day,
        )
        binding["strategy_scoped_universe"] = _strategy_scope_binding(protocol)
        worker = B6ValidationWorker(None, repo_root=Path("."))
        with patch(
            "backend.services.b6_validation_worker.FormalPITPartitionAdapter",
            MixedUniverseAdapter,
        ):
            with patch(
                "backend.services.b6_validation_worker.StrategyScopedPITUniverse",
                side_effect=_pass_through_strategy_scope,
            ):
                with self.assertRaises(_PreflightBlocked) as raised:
                    worker._validate_formal_executable_scope(
                        protocol,
                        {"lineage": binding},
                    )

        self.assertIn("000991.SZ", raised.exception.detail)
        self.assertIn("832317.BJ", raised.exception.detail)

    def test_missing_daily_execution_fields_block_before_reservation_and_executor(self) -> None:
        _install_unused_execution_imports()
        from backend.services.b6_validation_worker import B6ValidationWorker
        from backend.services.v3_b5_bundle import independent_verifier_identity

        class MissingExecutionDataAdapter:
            failure_mode = "daily_status"

            def __init__(self, *_args, **_kwargs):
                self.formal_binding_verified = True

            def common_trading_dates(self, start, end):
                return (start,) if start == end else ()

            def symbols_as_of(self, _day):
                return ("000001.SZ",)

            def is_eligible(self, _symbol, _day):
                return True

            def get_daily_status(self, symbol, day):
                if self.failure_mode == "daily_status":
                    raise KeyError(f"{symbol} missing required daily execution status on {day}")
                return SimpleNamespace(is_suspended=False)

            def get_daily_bar(self, symbol, day):
                if self.failure_mode == "daily.close":
                    raise KeyError(f"{symbol} missing daily.close on {day}")
                if self.failure_mode == "adj_factor":
                    raise KeyError(f"{symbol} missing adj_factor on {day}")
                raise AssertionError("status failure must stop before the bar read")

        class CountingLedger:
            def __init__(self):
                self.read_calls = 0
                self.reserve_calls = 0
                self.start_calls = 0

            def get_ledger_state(self, *_args, **_kwargs):
                self.read_calls += 1
                return {"budget_status": "available", "active_reservation_id": None}

            def reserve_oos_draw(self, **_kwargs):
                self.reserve_calls += 1
                return SimpleNamespace(reservation_id="test-reservation", status="reserved", oos_draw_index=1)

            def start_execution(self, _reservation_id):
                self.start_calls += 1

            def fail_reservation_within_tx(self, _conn, _reservation_id, _reason):
                return None

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db, task, protocol = _new_task_db(root, "formal-b5-test", "4" * 64)
            b4 = {
                "artifact_id": "b4-test",
                "manifest_sha256": "5" * 64,
                "event_result_sha256": "6" * 64,
                "strategy_revision_id": protocol.strategy_revision_id,
                "protocol_snapshot_id": protocol.protocol_snapshot_id,
                "is_range": {
                    "start": protocol.oos_window_start.isoformat(),
                    "end": protocol.oos_window_end.isoformat(),
                },
            }
            b5 = {
                "status": "verified",
                "bundle_id": task.b5_bundle_id,
                "manifest_sha256": task.b5_bundle_manifest_sha256,
                "authorization_scope": "v3_b5_formal_b6_preflight",
                "not_authorized_for_b6_oos_gate_promotion_signal": False,
                "verifier_identity": independent_verifier_identity(),
                "lineage": {
                    "b4": {
                        "artifact_id": b4["artifact_id"],
                        "manifest_sha256": b4["manifest_sha256"],
                        "event_sha256": b4["event_result_sha256"],
                    },
                    "protocol_snapshot_id": protocol.protocol_snapshot_id,
                    "strategy_revision_id": protocol.strategy_revision_id,
                    "formal_snapshot": {
                        "id": protocol.data_snapshot_id,
                        "semantic_hash": protocol.data_snapshot_hash,
                        "manifest_sha256": "7" * 64,
                    },
                    "membership": {"id": "membership_test", "manifest_sha256": "8" * 64},
                    "calendar": {"id": "calendar_test", "manifest_sha256": "9" * 64},
                    "b3_execution_input": {
                        "artifact_id": "b3-test",
                        "manifest_sha256": "a" * 64,
                        "formal_input_root_repo_relative": "data/test/inputs",
                    },
                    "stock_basic_lifecycle": {
                        "artifact_id": "lifecycle-test",
                        "manifest_sha256": "b" * 64,
                        "root_repo_relative": "data/test/stock_basic",
                        "stock_basic_files": [],
                    },
                    "strategy_scoped_universe": _strategy_scope_binding(protocol),
                    "is_range": b4["is_range"],
                    "execution_supplement": {"id": "supplement_test", "manifest_sha256": "c" * 64},
                    "gate_criteria_envelope_hash": protocol.gate_criteria_hash,
                },
            }
            ledger = CountingLedger()
            worker = B6ValidationWorker(
                db,
                repo_root=root,
                b5_bundle_root=root / "bundles",
                ledger=ledger,
            )
            worker._discover_b4 = lambda *_args: b4
            worker._prepare_verified_supplement = lambda *_args: SimpleNamespace(
                assert_current=lambda: None
            )
            worker._load_b4_result = lambda _artifact: SimpleNamespace(
                backtest_start=protocol.oos_window_start,
                backtest_end=protocol.oos_window_end,
            )
            worker._build_envelope = lambda *_args: {"identity": {}}
            executor_calls: list[object] = []
            try:
                cases = (
                    ("daily_status", "daily execution status"),
                    ("daily.close", "daily.close"),
                    ("adj_factor", "adj_factor"),
                )
                from contracts.b6_task import B6ValidationTask, build_b6_task_id, build_b6_task_key

                for attempt, (failure_mode, expected_detail) in enumerate(cases):
                    with self.subTest(missing=failure_mode):
                        if attempt == 0:
                            case_task = task
                        else:
                            bundle_id = f"formal-b5-test-{attempt}"
                            bundle_sha = str(4 + attempt) * 64
                            task_key = build_b6_task_key(
                                strategy_revision_id=protocol.strategy_revision_id,
                                protocol_snapshot_id=protocol.protocol_snapshot_id,
                                task_contract_version="v2",
                                b5_bundle_id=bundle_id,
                                b5_bundle_manifest_sha256=bundle_sha,
                            )
                            case_task = B6ValidationTask(
                                task_id=build_b6_task_id(task_key),
                                task_key=task_key,
                                task_type="b6_validation",
                                task_contract_version="v2",
                                strategy_revision_id=protocol.strategy_revision_id,
                                protocol_snapshot_id=protocol.protocol_snapshot_id,
                                status="queued",
                                created_at=datetime(2026, 8, 21, 12 + attempt),
                                b5_bundle_id=bundle_id,
                                b5_bundle_manifest_sha256=bundle_sha,
                            )
                            db.create_or_get_b6_task(case_task)

                        MissingExecutionDataAdapter.failure_mode = failure_mode
                        case_b5 = {
                            **b5,
                            "bundle_id": case_task.b5_bundle_id,
                            "manifest_sha256": case_task.b5_bundle_manifest_sha256,
                        }
                        worker._discover_b5 = lambda _task, current=case_b5: current
                        with patch(
                            "backend.services.b6_validation_worker.FormalPITPartitionAdapter",
                            MissingExecutionDataAdapter,
                        ):
                            with patch(
                                "backend.services.b6_validation_worker.StrategyScopedPITUniverse",
                                side_effect=_pass_through_strategy_scope,
                            ):
                                result = worker.run_task(
                                    case_task.task_id,
                                    execute_same_draw=lambda envelope: executor_calls.append(envelope) or {},
                                )

                        self.assertEqual(result.status, "blocked")
                        self.assertEqual(result.reason, "b6_formal_scope_unavailable")
                        blocked_task = db.get_b6_task_by_id(case_task.task_id)
                        self.assertIn("000001.SZ", blocked_task.blocking_reason_detail)
                        self.assertIn(expected_detail, blocked_task.blocking_reason_detail)

                fixture_bundle_id = "fixture-only-b5-test"
                fixture_bundle_sha = "e" * 64
                fixture_task_key = build_b6_task_key(
                    strategy_revision_id=protocol.strategy_revision_id,
                    protocol_snapshot_id=protocol.protocol_snapshot_id,
                    task_contract_version="v2",
                    b5_bundle_id=fixture_bundle_id,
                    b5_bundle_manifest_sha256=fixture_bundle_sha,
                )
                fixture_task = B6ValidationTask(
                    task_id=build_b6_task_id(fixture_task_key),
                    task_key=fixture_task_key,
                    task_type="b6_validation",
                    task_contract_version="v2",
                    strategy_revision_id=protocol.strategy_revision_id,
                    protocol_snapshot_id=protocol.protocol_snapshot_id,
                    status="queued",
                    created_at=datetime(2026, 8, 21, 16),
                    b5_bundle_id=fixture_bundle_id,
                    b5_bundle_manifest_sha256=fixture_bundle_sha,
                )
                db.create_or_get_b6_task(fixture_task)
                worker._discover_b5 = lambda _task: {
                    **b5,
                    "bundle_id": fixture_bundle_id,
                    "manifest_sha256": fixture_bundle_sha,
                    "authorization_scope": "v3_b5_contract_fixture_only",
                    "not_authorized_for_b6_oos_gate_promotion_signal": True,
                }
                with patch(
                    "backend.services.b6_validation_worker.FormalPITPartitionAdapter",
                    MissingExecutionDataAdapter,
                ):
                    with patch(
                        "backend.services.b6_validation_worker.StrategyScopedPITUniverse",
                        side_effect=_pass_through_strategy_scope,
                    ):
                        fixture_result = worker.run_task(
                            fixture_task.task_id,
                            execute_same_draw=lambda envelope: executor_calls.append(envelope) or {},
                        )
                self.assertEqual(fixture_result.status, "failed")
                self.assertEqual(fixture_result.reason, "invariant_error")
                fixture_blocked_task = db.get_b6_task_by_id(fixture_task.task_id)
                self.assertIn("B5 authorization scope changed", fixture_blocked_task.blocking_reason_detail)

                self.assertEqual(ledger.read_calls, 0)
                self.assertEqual(ledger.reserve_calls, 0)
                self.assertEqual(ledger.start_calls, 0)
                self.assertEqual(executor_calls, [])
            finally:
                db.close()

    def test_worker_accepts_explicit_separate_code_and_artifact_roots(self):
        from backend.services.b6_validation_worker import B6ValidationWorker

        code_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir)
            worker = B6ValidationWorker(
                None,
                code_root=code_root,
                artifact_root=artifact_root,
            )

        self.assertEqual(worker.code_root, code_root.resolve())
        self.assertEqual(worker.repo_root, artifact_root)
        self.assertEqual(
            worker.strategy_scope_root,
            artifact_root / "data/pit/strategy_scoped_universe_snapshots",
        )


if __name__ == "__main__":
    unittest.main()
