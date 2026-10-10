"""Synthetic file-backed tests for the explicit-task B6 worker boundary."""

from __future__ import annotations

from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
import hashlib
import json
import shutil
import sqlite3
import tempfile
import unittest
import inspect

from backend.db.strategy import StrategyDB
from backend.services.oos_budget_ledger import OOSBudgetLedger
from tests.test_run_v3_task4_once import (
    B5_BUNDLE_DIR,
    B5_BUNDLE_ID,
    RESULT_ID,
    RESULT_ROOT,
    CURRENT_B4_ID,
    CURRENT_B4_EVENT_SHA256,
    CURRENT_B4_MANIFEST_SHA256,
    CURRENT_B5_BUNDLE_ID,
    CURRENT_B5_BUNDLE_MANIFEST_SHA256,
    CURRENT_B5_SUPPLEMENT_ID,
    CURRENT_B5_SUPPLEMENT_MANIFEST_SHA256,
    CURRENT_PROTOCOL_ID,
    CURRENT_STRATEGY_REVISION_ID,
)


REPO_ROOT = Path("D:/Codex/TraderLens")


def _prepare_isolated_worker_fixture(
    tmp_path: Path,
    *,
    b4_window: tuple[date, date] | None = None,
    membership_snapshot_id: str = "pims_traderlens_v2_shsz_sw2021_pit_005",
) -> dict:
    """Build a queued B5-bound task through public APIs in a temporary DB."""
    from contracts.b6_task import B6ValidationTask, build_b6_task_id, build_b6_task_key
    from contracts.strategy import (
        BacktestUniverseSpec,
        ResearchProtocolSnapshot,
        StrategyDraft,
        StrategyLifecycleState,
        compute_b6_protocol_id_from_fields,
    )

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    b4_results_root = tmp_path / "b4_results"
    b4_results_root.mkdir()
    bundle_id = "b5_phase5e6_synthetic"
    bundle_dir = tmp_path / "verified" / bundle_id
    bundle_dir.mkdir(parents=True)
    db_path = tmp_path / "strategy.db"

    universe = BacktestUniverseSpec(
        universe_spec_id="universe_phase5e6_synthetic",
        universe_rule_type="point_in_time_membership",
        membership_source="synthetic_e6_worker_fixture",
        membership_effective_from=date(2024, 1, 1),
        membership_effective_to=date(2024, 12, 31),
        snapshot_date=date(2024, 1, 1),
        membership_snapshot_ids=(membership_snapshot_id,),
        quality_status="ok",
    )
    protocol_fields = {
        "protocol_profile": "b6_coverage_bound",
        "theme_id": "theme_phase5e6_synthetic",
        "hypothesis_source_snapshot_id": "hypothesis_phase5e6_synthetic",
        "strategy_revision_id": "revision_phase5e6_synthetic",
        "sample_split_rule_id": "split_phase5e6_synthetic",
        "oos_window_rule_id": "window_phase5e6_synthetic",
        "oos_window_rule_params_json": "{}",
        "oos_window_start": date(2024, 1, 1),
        "oos_window_end": date(2024, 12, 31),
        "shared_oos_window_id": "window_phase5e6_synthetic",
        "backtest_universe_spec_id": universe.universe_spec_id,
        "data_snapshot_id": "data_phase5e6_synthetic",
        "data_snapshot_hash": "2" * 64,
        "kill_criteria_snapshot_id": "kill_phase5e6_synthetic",
        "prototype_gate_thresholds_json": '{"threshold": 0.5}',
        "strategy_config_hash": "1" * 64,
        "gate_criteria_hash": "3" * 64,
        "availability_successor_id": "successor_phase5e6_synthetic",
        "availability_successor_manifest_hash": "a" * 64,
        "availability_successor_algorithm_hash": "successor_algorithm_phase5e6_synthetic",
        "predecessor_qualification_id": "predecessor_phase5e6_synthetic",
        "predecessor_qualification_manifest_hash": "b" * 64,
        "predecessor_qualification_status": "availability_bounded_qualified",
        "predecessor_qualification_algorithm_hash": "predecessor_algorithm_phase5e6_synthetic",
        "coverage_package_id": "coverage_phase5e6_synthetic",
        "coverage_manifest_hash": "c" * 64,
        "coverage_algorithm_hash": "coverage_algorithm_phase5e6_synthetic",
        "source_scope_hash": "scope_hash_phase5e6_synthetic",
        "data_requirements_hash": "requirements_hash_phase5e6_synthetic",
        "expected_stock_days": 1000,
        "complete_stock_days": 900,
        "unavailable_stock_days": 100,
        "gate_snapshot_id": "gate_snapshot_phase5e6_synthetic",
        "gate_content_hash": "gate_content_hash_phase5e6_synthetic",
        "kill_content_hash": "kill_content_hash_phase5e6_synthetic",
    }
    protocol = ResearchProtocolSnapshot(
        protocol_snapshot_id=compute_b6_protocol_id_from_fields(**protocol_fields),
        frozen_at=datetime(2026, 8, 21, 12, 0, 0),
        frozen_by="e6_test",
        **protocol_fields,
    )
    b4_is_start, b4_is_end = b4_window or (
        protocol.oos_window_start,
        protocol.oos_window_end,
    )

    source_path = repo_root / "synthetic_sources" / "worker_runtime.py"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("SYNTHETIC_WORKER_SOURCE = True\n", encoding="utf-8")
    supplement_id = "supplement_phase5e6_worker_fixture"
    supplement_dir = repo_root / "data/pit/v3_execution_semantics_supplements" / supplement_id
    supplement_dir.mkdir(parents=True, exist_ok=True)
    supplement_manifest = {
        "schema_version": "v3_execution_semantics_supplement.v2",
        "supplement_id": supplement_id,
        "status": "published",
        "authorization_scope": "v3_manual_trading_execution",
        "not_authorized_for_b6_oos_gate_promotion_signal": False,
        "strategy": {"strategy_revision_id": protocol.strategy_revision_id},
        "protocol": {"protocol_snapshot_id": protocol.protocol_snapshot_id},
        "data_chain": {"formal_snapshot": {"semantic_hash": protocol.data_snapshot_hash}},
        "criteria": {"envelope_hash": protocol.gate_criteria_hash},
        "source_bindings": {
            "worker_runtime": {
                "path": "synthetic_sources/worker_runtime.py",
                "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            },
        },
    }
    supplement_manifest_path = supplement_dir / "manifest.json"
    supplement_manifest_path.write_bytes(
        json.dumps(supplement_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    supplement_manifest_sha256 = hashlib.sha256(supplement_manifest_path.read_bytes()).hexdigest()
    supplement_manifest_path.with_name("manifest.json.sha256").write_text(
        f"{supplement_manifest_sha256}  manifest.json\n", encoding="utf-8"
    )

    b4_artifact = {
        "artifact_id": "b4_phase5e6_synthetic",
        "manifest_sha256": "a" * 64,
        "event_result_sha256": "b" * 64,
        "strategy_revision_id": protocol.strategy_revision_id,
        "protocol_snapshot_id": protocol.protocol_snapshot_id,
        "is_range": {
            "start": b4_is_start.isoformat(),
            "end": b4_is_end.isoformat(),
        },
    }
    b5_bundle = {
        "status": "verified",
        "bundle_id": bundle_id,
        "manifest_sha256": None,
        "authorization_scope": "v3_b5_contract_fixture_only",
        "not_authorized_for_b6_oos_gate_promotion_signal": True,
        "lineage": {
            "b4": {
                "artifact_id": b4_artifact["artifact_id"],
                "manifest_sha256": b4_artifact["manifest_sha256"],
                "event_sha256": b4_artifact["event_result_sha256"],
            },
            "protocol_snapshot_id": protocol.protocol_snapshot_id,
            "strategy_revision_id": protocol.strategy_revision_id,
            "formal_snapshot": {
                "id": protocol.data_snapshot_id,
                "semantic_hash": protocol.data_snapshot_hash,
                "manifest_sha256": "d" * 64,
            },
            "membership": {
                "id": universe.membership_snapshot_ids[0],
                "manifest_sha256": "e" * 64,
            },
            "calendar": {
                "id": "calendar_phase5e6_synthetic",
                "manifest_sha256": "f" * 64,
            },
            "is_range": {
                "start": b4_is_start.isoformat(),
                "end": b4_is_end.isoformat(),
            },
            "execution_supplement": {
                "id": supplement_id,
                "manifest_sha256": supplement_manifest_sha256,
            },
            "gate_criteria_envelope_hash": protocol.gate_criteria_hash,
            "source_inventory": {},
        },
    }
    bundle_manifest = dict(b5_bundle)
    bundle_manifest.pop("manifest_sha256")
    bundle_manifest_path = bundle_dir / "manifest.json"
    bundle_manifest_path.write_bytes(
        json.dumps(bundle_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    bundle_manifest_sha256 = hashlib.sha256(bundle_manifest_path.read_bytes()).hexdigest()
    bundle_manifest_path.with_name("manifest.json.sha256").write_text(
        f"{bundle_manifest_sha256}  manifest.json\n",
        encoding="utf-8",
    )
    b5_bundle["manifest_sha256"] = bundle_manifest_sha256

    verified = {
        "status": "verified",
        "supplement_id": supplement_id,
        "path": str(supplement_dir),
        "manifest_sha256": supplement_manifest_sha256,
        "strategy_revision_id": protocol.strategy_revision_id,
        "protocol_snapshot_id": protocol.protocol_snapshot_id,
        "data_snapshot_hash": protocol.data_snapshot_hash,
        "criteria_envelope_hash": protocol.gate_criteria_hash,
    }

    db = StrategyDB(str(db_path))
    try:
        db.store_backtest_universe(universe)
        draft = StrategyDraft(
            strategy_revision_id=protocol.strategy_revision_id,
            theme_id=protocol.theme_id,
            hypothesis_id=protocol.hypothesis_source_snapshot_id,
            strategy_template_id="template_phase5e6_synthetic",
            strategy_template_version="v1",
            strategy_template_hash="template_hash_phase5e6_synthetic",
            hypothesis_source_snapshot_id=protocol.hypothesis_source_snapshot_id,
            backtest_universe_spec_id=universe.universe_spec_id,
            strategy_config_json="{}",
            sample_split_rule_id=protocol.sample_split_rule_id,
            created_at=datetime(2026, 8, 21, 12, 0, 0),
        )
        db.create_strategy_draft(
            draft,
            StrategyLifecycleState(
                lifecycle_state_id="lifecycle_phase5e6_synthetic",
                strategy_revision_id=protocol.strategy_revision_id,
                state_version=1,
                state="draft",
                source_record_id="initial",
                recorded_at=datetime(2026, 8, 21, 12, 0, 0),
                recorded_by="e6_test",
            ),
        )
        db.store_protocol_snapshot(protocol)
        task_key = build_b6_task_key(
            strategy_revision_id=protocol.strategy_revision_id,
            protocol_snapshot_id=protocol.protocol_snapshot_id,
            task_contract_version="v2",
            b5_bundle_id=bundle_id,
            b5_bundle_manifest_sha256=bundle_manifest_sha256,
        )
        task = B6ValidationTask(
            task_id=build_b6_task_id(task_key),
            task_key=task_key,
            task_type="b6_validation",
            task_contract_version="v2",
            strategy_revision_id=protocol.strategy_revision_id,
            protocol_snapshot_id=protocol.protocol_snapshot_id,
            status="queued",
            created_at=datetime(2026, 8, 21, 12, 0, 0),
            b5_bundle_id=bundle_id,
            b5_bundle_manifest_sha256=bundle_manifest_sha256,
        )
        winner, created = db.create_or_get_b6_task(task)
        if not created or winner.task_id != task.task_id:
            raise AssertionError("synthetic E6 task admission did not create the expected task")
    finally:
        db.close()

    _write_formal_scope_guard_fixture(
        repo_root,
        protocol.oos_window_start,
        membership_snapshot_id=membership_snapshot_id,
    )

    return {
        "repo_root": repo_root,
        "db_path": db_path,
        "protocol": protocol,
        "source_path": source_path,
        "b4_results_root": b4_results_root,
        "bundle_dir": bundle_dir,
        "task_id": task.task_id,
        "b4_artifact": b4_artifact,
        "b5_bundle": b5_bundle,
        "verified": verified,
        "supplement_dir": supplement_dir,
        "b4_is_window": (b4_is_start, b4_is_end),
    }


def _write_formal_scope_guard_fixture(
    repo_root: Path,
    effective_from: date,
    *,
    membership_snapshot_id: str,
    include_unknown_member: bool = False,
) -> None:
    """Write only synthetic formal inputs used by the executable-scope guard."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    formal_root = (
        repo_root
        / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
    )
    calendar_schema = pa.schema([
        pa.field("exchange", pa.string()),
        pa.field("cal_date", pa.string()),
        pa.field("is_open", pa.int64()),
    ])
    calendar_path = formal_root / "trade_cal/part.parquet"
    calendar_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pylist(
            [
                {"exchange": "SSE", "cal_date": effective_from.strftime("%Y%m%d"), "is_open": 1},
                {"exchange": "SZSE", "cal_date": effective_from.strftime("%Y%m%d"), "is_open": 1},
            ],
            schema=calendar_schema,
        ),
        calendar_path,
    )

    stock_schema = pa.schema([
        pa.field("ts_code", pa.string()),
        pa.field("list_date", pa.string()),
        pa.field("delist_date", pa.string()),
    ])
    listed_path = formal_root / "stock_basic/list_status=L/part.parquet"
    listed_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pylist(
            [{"ts_code": "000001.SZ", "list_date": "20200101", "delist_date": None}],
            schema=stock_schema,
        ),
        listed_path,
    )
    for status in ("D", "P"):
        path = formal_root / f"stock_basic/list_status={status}/part.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist([], schema=stock_schema), path)

    membership_root = repo_root / "data/pit/pit_membership_snapshots" / membership_snapshot_id
    membership_root.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "symbol": "000001.SZ",
            "effective_from": effective_from,
            "effective_to": None,
            "source": "synthetic_formal_scope_fixture",
            "snapshot_id": membership_snapshot_id,
        },
    ]
    if include_unknown_member:
        records.append(
            {
                "symbol": "UNKNOWN.SZ",
                "effective_from": effective_from,
                "effective_to": None,
                "source": "synthetic_formal_scope_fixture",
                "snapshot_id": membership_snapshot_id,
            }
        )
    records_schema = pa.schema([
        pa.field("symbol", pa.string()),
        pa.field("effective_from", pa.date32()),
        pa.field("effective_to", pa.date32()),
        pa.field("source", pa.string()),
        pa.field("snapshot_id", pa.string()),
    ])
    records_path = membership_root / "records.parquet"
    pq.write_table(pa.Table.from_pylist(records, schema=records_schema), records_path)
    records_sha256 = hashlib.sha256(records_path.read_bytes()).hexdigest()
    manifest_path = membership_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "snapshot_id": membership_snapshot_id,
                "records_parquet_sha256": records_sha256,
                "frozen": True,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    (records_path.with_name("records.parquet.sha256")).write_text(
        f"{records_sha256}  records.parquet\n",
        encoding="utf-8",
    )
    (manifest_path.with_name("manifest.json.sha256")).write_text(
        f"{manifest_sha256}  manifest.json\n",
        encoding="utf-8",
    )


def _prepare_phase5c_fixture(tmp_path: Path) -> dict:
    return _prepare_isolated_worker_fixture(tmp_path)


def _configure_isolated_worker(worker, fixture: dict):
    """Inject only synthetic discovery/verification at the worker boundary."""
    from unittest.mock import patch

    from backend.services.b6_validation_worker import B6ValidationWorker

    worker._discover_b4 = lambda: dict(fixture["b4_artifact"])

    def discover_b5(task):
        bundle_dir = worker.b5_bundle_root / str(task.b5_bundle_id)
        manifest_path = bundle_dir / "manifest.json"
        sidecar_path = bundle_dir / "manifest.json.sha256"
        if not manifest_path.is_file() or not sidecar_path.is_file():
            return {"status": "invalid", "reason": "v3 B5 bundle directory missing"}
        actual = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        if sidecar_path.read_text(encoding="utf-8").split()[0] != actual:
            return {"status": "invalid", "reason": "v3 B5 bundle manifest hash mismatch"}
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"status": "invalid", "reason": str(exc)}
        return {
            **fixture["b5_bundle"],
            **manifest,
            "status": "verified",
            "manifest_sha256": actual,
        }

    worker._discover_b5 = discover_b5

    def prepare_verified_supplement(b5_bundle, protocol):
        with patch(
            "backend.services.b6_validation_worker.verify_v3_execution_semantics",
            return_value=fixture["verified"],
        ):
            return B6ValidationWorker._prepare_verified_supplement(worker, b5_bundle, protocol)

    worker._prepare_verified_supplement = prepare_verified_supplement
    return worker


def _same_draw_from_envelope(envelope: dict):
    from backend.services.b5_oos_types import (
        B6SameDrawOOSResult,
        B6SameDrawReadAudit,
        BaseCostResult,
        SameDrawExecutionIdentity,
        StressCostResult,
    )

    identity = SameDrawExecutionIdentity(**envelope["identity"])
    return B6SameDrawOOSResult(
        identity=identity,
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
            result_id="base_cost_phase5c_synthetic",
            slippage_bps=1.0,
            commission_bps=2.0,
            impact_bps=1.0,
            total_cost_bps=4.0,
            assumptions_hash="4" * 64,
        ),
        stress_cost_result=StressCostResult(
            result_id="stress_cost_phase5c_synthetic",
            slippage_bps=2.0,
            commission_bps=3.0,
            impact_bps=2.0,
            total_cost_bps=7.0,
            stress_multiplier=2.0,
            assumptions_hash="5" * 64,
        ),
        read_audit=B6SameDrawReadAudit.from_trace(
            allowed_end=date.fromisoformat(envelope["identity"]["oos_end"]),
            trace=(),
        ),
    )


class CountingLedger:
    """Transparent read counter; protected writes fail if reached in Phase 5B."""

    def __init__(self, db: StrategyDB):
        self.real = OOSBudgetLedger(db)
        self.read_calls = 0
        self.reserve_calls = 0

    def get_ledger_state(self, *args, **kwargs):
        self.read_calls += 1
        return self.real.get_ledger_state(*args, **kwargs)

    def reserve_oos_draw(self, *args, **kwargs):
        self.reserve_calls += 1
        raise AssertionError("Phase 5B must stop before reserve_oos_draw")


def _prepare_e6_boundary_fixture(raw_tmp: Path) -> dict:
    """Build a fresh temp DB and temp supplement for prepared-token tests."""
    from contracts.b6_task import B6ValidationTask, build_b6_task_id, build_b6_task_key

    case = _prepare_isolated_worker_fixture(raw_tmp)
    db = StrategyDB(str(case["db_path"]))
    protocol = case["protocol"]
    task_key = build_b6_task_key(
        strategy_revision_id=protocol.strategy_revision_id,
        protocol_snapshot_id=protocol.protocol_snapshot_id,
        task_contract_version="v2",
        b5_bundle_id=CURRENT_B5_BUNDLE_ID,
        b5_bundle_manifest_sha256=CURRENT_B5_BUNDLE_MANIFEST_SHA256,
    )
    task = B6ValidationTask(
        task_id=build_b6_task_id(task_key),
        task_key=task_key,
        task_type="b6_validation",
        task_contract_version="v2",
        strategy_revision_id=protocol.strategy_revision_id,
        protocol_snapshot_id=protocol.protocol_snapshot_id,
        status="queued",
        created_at=datetime(2026, 8, 21, 12, 0, 0),
        b5_bundle_id=CURRENT_B5_BUNDLE_ID,
        b5_bundle_manifest_sha256=CURRENT_B5_BUNDLE_MANIFEST_SHA256,
    )
    winner, created = db.create_or_get_b6_task(task)
    if not created or winner.task_id != task.task_id:
        db.close()
        raise AssertionError("synthetic E6 current-bundle task admission did not create the expected task")

    b5_bundle = dict(case["b5_bundle"])
    b5_bundle["bundle_id"] = CURRENT_B5_BUNDLE_ID
    b5_bundle["manifest_sha256"] = CURRENT_B5_BUNDLE_MANIFEST_SHA256
    return {
        **case,
        "db": db,
        "task": winner,
        "b5_bundle": b5_bundle,
    }


class _RecordingOOSLedger(OOSBudgetLedger):
    def __init__(self, db: StrategyDB, events: list[str] | None = None):
        super().__init__(db)
        self.events = events if events is not None else []
        self.read_calls = 0
        self.reserve_calls = 0
        self.start_calls = 0

    def get_ledger_state(self, *args, **kwargs):
        self.read_calls += 1
        self.events.append("ledger_state")
        return super().get_ledger_state(*args, **kwargs)

    def reserve_oos_draw(self, *args, **kwargs):
        self.reserve_calls += 1
        self.events.append("reserve")
        return super().reserve_oos_draw(*args, **kwargs)

    def start_execution(self, reservation_id):
        self.start_calls += 1
        self.events.append("start")
        return super().start_execution(reservation_id)


def _make_e6_worker(case: dict, ledger: Any):
    from backend.services.b4_protocol_types import DailyPortfolioSnapshot, EventBacktestResult
    from backend.services.b6_validation_worker import B6ValidationWorker

    protocol = case["protocol"]
    b4_is_start, b4_is_end = case.get(
        "b4_is_window",
        (protocol.oos_window_start, protocol.oos_window_end),
    )

    def b4_result_loader(artifact):
        return EventBacktestResult(
            result_id="b4_phase5e6_synthetic",
            strategy_revision_id=artifact["strategy_revision_id"],
            protocol_snapshot_id=artifact["protocol_snapshot_id"],
            evaluation_mode="formal_backtest",
            backtest_start=b4_is_start,
            backtest_end=b4_is_end,
            order_intents=(),
            fills=(),
            rejected_orders=(),
            future_violations=(),
            final_portfolio=DailyPortfolioSnapshot(
                snapshot_id="snapshot_phase5e6_synthetic",
                snapshot_date=b4_is_end,
                cash=100000.0,
                positions=(),
                portfolio_value=100000.0,
            ),
            frozen_at=b4_is_end,
        )

    return B6ValidationWorker(
        case["db"],
        repo_root=case["repo_root"],
        b5_bundle_root=case["bundle_dir"].parent,
        b4_result_loader=b4_result_loader,
        ledger=ledger,
    )


def _prepare_v3_successor_worker_fixture(tmp_path: Path) -> dict:
    """Create a failed v2 predecessor and its queued v3 successor in temp DB."""
    case = _prepare_isolated_worker_fixture(tmp_path)
    db = StrategyDB(str(case["db_path"]))
    try:
        claimed = db.claim_b6_task(case["task_id"])
        if claimed is None:
            raise AssertionError("C1b fixture did not claim its v2 predecessor")
        db.update_b6_task_status(
            claimed.task_id,
            "failed",
            completed_at=datetime(2026, 8, 21, 12, 1, 0),
            blocking_reason_code="invariant_error",
            blocking_reason_detail="synthetic predecessor failure",
        )
        db.conn.commit()
        predecessor = db.get_b6_task_by_id(claimed.task_id)
        successor, created = db.create_or_get_b6_successor_attempt(predecessor.task_id)
        if not created or successor.status != "queued":
            raise AssertionError("C1b fixture did not create its queued v3 successor")
    finally:
        db.close()
    return {
        **case,
        "predecessor": predecessor,
        "task": successor,
        "task_id": successor.task_id,
    }


class TestPreparedSupplementBoundary(unittest.TestCase):
    def _preflight_patches(self, worker, case, events=None):
        from unittest.mock import patch

        def verify(*args, **kwargs):
            if events is not None:
                events.append("supplement_verify")
            return case["verified"]

        return (
            patch.object(worker, "_discover_b4", return_value=case["b4_artifact"]),
            patch.object(worker, "_discover_b5", return_value=case["b5_bundle"]),
            patch(
                "backend.services.b6_validation_worker.verify_v3_execution_semantics",
                side_effect=verify,
                create=True,
            ),
        )

    def test_second_preflight_verifies_v2_supplement_before_ledger_read_and_returns_prepared_token(self):
        with tempfile.TemporaryDirectory(prefix="b6-e6-preflight-") as raw_tmp:
            case = _prepare_e6_boundary_fixture(Path(raw_tmp))
            try:
                worker = _make_e6_worker(case, CountingLedger(case["db"]))
                claimed = case["db"].claim_b6_task(case["task"].task_id)
                self.assertIsNotNone(claimed)
                patches = self._preflight_patches(worker, case)
                with patches[0], patches[1], patches[2] as verifier:
                    prepared = worker._second_preflight(claimed)
                self.assertEqual(len(prepared), 4)
                self.assertEqual(verifier.call_count, 1)
                token = prepared[3]
                self.assertEqual(token.supplement_id, case["verified"]["supplement_id"])
                self.assertEqual(token.manifest_sha256, case["verified"]["manifest_sha256"])
                frozen = token.verified_representation
                self.assertNotIn("path", frozen)
                self.assertEqual(frozen["supplement_id"], case["verified"]["supplement_id"])
                self.assertEqual(frozen["manifest_sha256"], case["verified"]["manifest_sha256"])
            finally:
                case["db"].close()

    def test_prepared_token_is_consumed_once_after_start_without_reverification(self):
        with tempfile.TemporaryDirectory(prefix="b6-e6-consume-") as raw_tmp:
            case = _prepare_e6_boundary_fixture(Path(raw_tmp))
            try:
                events = []
                ledger = _RecordingOOSLedger(case["db"], events)
                worker = _make_e6_worker(case, ledger)
                calls = []

                def execute(envelope):
                    token = envelope["prepared_supplement"]
                    token.consume(envelope["identity"])
                    calls.append(envelope)
                    return _same_draw_from_envelope(envelope)

                patches = self._preflight_patches(worker, case, events)
                with patches[0], patches[1], patches[2] as verifier:
                    result = worker.run_task(case["task"].task_id, execute_same_draw=execute)
                self.assertEqual(result.status, "completed")
                self.assertEqual(verifier.call_count, 1)
                self.assertEqual(len(calls), 1)
                token = calls[0]["prepared_supplement"]
                self.assertTrue(token.consumed)
                with self.assertRaises(ValueError):
                    token.consume(calls[0]["identity"])
                self.assertEqual(ledger.read_calls, 1)
                self.assertEqual(ledger.reserve_calls, 1)
                self.assertEqual(ledger.start_calls, 1)
            finally:
                case["db"].close()

    def test_source_binding_drift_before_start_blocks_without_reservation(self):
        with tempfile.TemporaryDirectory(prefix="b6-e6-before-start-") as raw_tmp:
            case = _prepare_e6_boundary_fixture(Path(raw_tmp))
            try:
                class MutatingLedger(_RecordingOOSLedger):
                    def get_ledger_state(self, *args, **kwargs):
                        state = super().get_ledger_state(*args, **kwargs)
                        case["source_path"].write_bytes(case["source_path"].read_bytes() + b"# drift\n")
                        return state

                ledger = MutatingLedger(case["db"])
                worker = _make_e6_worker(case, ledger)
                patches = self._preflight_patches(worker, case)
                with patches[0], patches[1], patches[2] as verifier:
                    result = worker.run_task(case["task"].task_id, execute_same_draw=lambda _: self.fail("executor called"))
                self.assertEqual(result.status, "blocked")
                self.assertEqual(result.task_status, "blocked")
                self.assertEqual(result.reason, "b6_prepared_supplement_changed")
                self.assertEqual(verifier.call_count, 1)
                self.assertEqual(ledger.read_calls, 1)
                self.assertEqual(ledger.reserve_calls, 0)
            finally:
                case["db"].close()

    def test_source_binding_drift_after_reserve_before_start_releases_and_blocks(self):
        with tempfile.TemporaryDirectory(prefix="b6-e6-after-reserve-") as raw_tmp:
            case = _prepare_e6_boundary_fixture(Path(raw_tmp))
            try:
                class MutatingLedger(_RecordingOOSLedger):
                    def reserve_oos_draw(self, *args, **kwargs):
                        reservation = super().reserve_oos_draw(*args, **kwargs)
                        case["source_path"].write_bytes(
                            case["source_path"].read_bytes() + b"# drift after reserve\n"
                        )
                        return reservation

                ledger = MutatingLedger(case["db"])
                worker = _make_e6_worker(case, ledger)
                executor_calls = []
                patches = self._preflight_patches(worker, case)
                with patches[0], patches[1], patches[2] as verifier:
                    result = worker.run_task(
                        case["task"].task_id,
                        execute_same_draw=lambda _: executor_calls.append(True),
                    )

                self.assertEqual(result.status, "blocked")
                self.assertEqual(result.task_status, "blocked")
                self.assertEqual(result.reason, "b6_prepared_supplement_changed")
                self.assertTrue(result.task_id)
                self.assertEqual(verifier.call_count, 1)
                self.assertEqual(ledger.read_calls, 1)
                self.assertEqual(ledger.reserve_calls, 1)
                self.assertEqual(ledger.start_calls, 0)
                self.assertEqual(executor_calls, [])
                with closing(sqlite3.connect(case["db_path"])) as conn:
                    conn.row_factory = sqlite3.Row
                    task_row = conn.execute(
                        "select status, blocking_reason_code from b6_validation_tasks where task_id = ?",
                        (case["task"].task_id,),
                    ).fetchone()
                    reservation_row = conn.execute(
                        "select status, terminal_reason from oos_budget_reservations"
                    ).fetchone()
                    state_row = conn.execute(
                        "select consumed_draw_count, next_oos_draw_index, active_reservation_id, budget_status "
                        "from oos_budget_state"
                    ).fetchone()
                    ledger_rows = conn.execute(
                        "select count(*) from oos_evaluation_ledgers"
                    ).fetchone()[0]
                    report_rows = conn.execute(
                        "select count(*) from immutable_backtest_reports"
                    ).fetchone()[0]
                    gate_rows = conn.execute(
                        "select count(*) from prototype_gate_results_v2"
                    ).fetchone()[0]
                self.assertEqual(dict(task_row), {
                    "status": "blocked",
                    "blocking_reason_code": "b6_prepared_supplement_changed",
                })
                self.assertEqual(reservation_row["status"], "released")
                self.assertIn("prepared_supplement_changed", reservation_row["terminal_reason"])
                self.assertEqual(dict(state_row), {
                    "consumed_draw_count": 0,
                    "next_oos_draw_index": 1,
                    "active_reservation_id": None,
                    "budget_status": "available",
                })
                self.assertEqual(ledger_rows, 2)
                self.assertEqual(report_rows, 0)
                self.assertEqual(gate_rows, 0)
            finally:
                case["db"].close()

    def test_source_binding_drift_after_start_fails_after_start_without_executor_rerun(self):
        with tempfile.TemporaryDirectory(prefix="b6-e6-after-start-") as raw_tmp:
            case = _prepare_e6_boundary_fixture(Path(raw_tmp))
            try:
                class MutatingLedger(_RecordingOOSLedger):
                    def start_execution(self, reservation_id):
                        result = super().start_execution(reservation_id)
                        case["source_path"].write_bytes(case["source_path"].read_bytes() + b"# drift\n")
                        return result

                ledger = MutatingLedger(case["db"])
                worker = _make_e6_worker(case, ledger)
                executor_calls = []
                patches = self._preflight_patches(worker, case)
                with patches[0], patches[1], patches[2] as verifier:
                    result = worker.run_task(
                        case["task"].task_id,
                        execute_same_draw=lambda _: executor_calls.append(True),
                    )
                self.assertEqual(result.status, "failed")
                self.assertEqual(result.reason, "b6_fail_after_start")
                self.assertEqual(verifier.call_count, 1)
                self.assertEqual(ledger.reserve_calls, 1)
                self.assertEqual(ledger.start_calls, 1)
                self.assertEqual(executor_calls, [])
                with closing(sqlite3.connect(case["db_path"])) as conn:
                    self.assertEqual(conn.execute("select status from oos_budget_reservations").fetchone()[0], "failed")
            finally:
                case["db"].close()

    def test_worker_progress_order_claim_preflight_token_ledger_reserve_start(self):
        from backend.services.b6_validation_worker import B6ValidationWorker

        events = []

        class RecordingDB(StrategyDB):
            def claim_b6_task(self, task_id):
                events.append("claim")
                return super().claim_b6_task(task_id)

        with tempfile.TemporaryDirectory(prefix="b6-e6-order-") as raw_tmp:
            case = _prepare_e6_boundary_fixture(Path(raw_tmp))
            case["db"].close()
            db = RecordingDB(str(case["db_path"]))
            case["db"] = db
            try:
                ledger = _RecordingOOSLedger(db, events)
                worker = _make_e6_worker(case, ledger)
                patches = self._preflight_patches(worker, case, events)
                with patches[0], patches[1], patches[2] as verifier:
                    result = worker.run_task(case["task"].task_id, execute_same_draw=lambda envelope: events.append("executor") or _same_draw_from_envelope(envelope))
                self.assertEqual(result.status, "completed")
                self.assertEqual(verifier.call_count, 1)
                self.assertEqual(events, ["claim", "supplement_verify", "ledger_state", "reserve", "start", "executor"])
            finally:
                db.close()


class TestB6SuccessorWorker(unittest.TestCase):
    def test_v3_successor_reaches_existing_second_preflight_boundary(self):
        from unittest.mock import patch

        from backend.services.b6_validation_worker import B6ValidationWorker

        with tempfile.TemporaryDirectory(prefix="b6-c1b-worker-") as raw_tmp:
            case = _prepare_v3_successor_worker_fixture(Path(raw_tmp))
            db = StrategyDB(str(case["db_path"]))
            try:
                ledger = CountingLedger(db)
                case["db"] = db
                worker = _make_e6_worker(case, ledger)
                with patch.object(worker, "_discover_b4", return_value=case["b4_artifact"]), patch.object(
                    worker, "_discover_b5", return_value=case["b5_bundle"]
                ), patch(
                    "backend.services.b6_validation_worker.verify_v3_execution_semantics",
                    return_value=case["verified"],
                ) as verifier:
                    result = worker.run_task(case["task_id"])
                self.assertEqual(result.status, "ready_for_reservation")
                self.assertEqual(result.task_status, "running")
                self.assertTrue(result.ready_for_reservation)
                self.assertEqual(ledger.read_calls, 1)
                self.assertEqual(ledger.reserve_calls, 0)
                self.assertEqual(verifier.call_count, 1)
                with closing(sqlite3.connect(case["db_path"])) as conn:
                    conn.row_factory = sqlite3.Row
                    predecessor = conn.execute(
                        "SELECT task_contract_version,status,claimed_at FROM b6_validation_tasks WHERE task_id=?",
                        (case["predecessor"].task_id,),
                    ).fetchone()
                    successor = conn.execute(
                        "SELECT task_contract_version,status,predecessor_task_id,predecessor_task_key,successor_attempt_number "
                        "FROM b6_validation_tasks WHERE task_id=?",
                        (case["task_id"],),
                    ).fetchone()
                    oos = {
                        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                        for table in (
                            "oos_budget_state",
                            "oos_budget_reservations",
                            "oos_evaluation_ledgers",
                            "immutable_backtest_reports",
                            "prototype_gate_results_v2",
                        )
                    }
                self.assertEqual(dict(predecessor)["task_contract_version"], "v2")
                self.assertEqual(dict(predecessor)["status"], "failed")
                self.assertIsNotNone(predecessor["claimed_at"])
                self.assertEqual(dict(successor), {
                    "task_contract_version": "v3",
                    "status": "running",
                    "predecessor_task_id": case["predecessor"].task_id,
                    "predecessor_task_key": case["predecessor"].task_key,
                    "successor_attempt_number": 1,
                })
                self.assertEqual(oos, {
                    "oos_budget_state": 0,
                    "oos_budget_reservations": 0,
                    "oos_evaluation_ledgers": 0,
                    "immutable_backtest_reports": 0,
                    "prototype_gate_results_v2": 0,
                })
            finally:
                db.close()

    def test_v3_successor_completes_existing_terminal_chain_once(self):
        from unittest.mock import patch

        events: list[str] = []
        with tempfile.TemporaryDirectory(prefix="b6-c1b-worker-terminal-") as raw_tmp:
            case = _prepare_v3_successor_worker_fixture(Path(raw_tmp))
            db = StrategyDB(str(case["db_path"]))
            try:
                ledger = _RecordingOOSLedger(db, events)
                case["db"] = db
                worker = _make_e6_worker(case, ledger)
                executor_calls: list[dict] = []

                def execute(envelope):
                    envelope["prepared_supplement"].consume(envelope["identity"])
                    executor_calls.append(envelope)
                    return _same_draw_from_envelope(envelope)

                with patch.object(worker, "_discover_b4", return_value=case["b4_artifact"]), patch.object(
                    worker, "_discover_b5", return_value=case["b5_bundle"]
                ), patch(
                    "backend.services.b6_validation_worker.verify_v3_execution_semantics",
                    return_value=case["verified"],
                ) as verifier:
                    result = worker.run_task(case["task_id"], execute_same_draw=execute)
                self.assertEqual(result.status, "completed")
                self.assertEqual(result.task_status, "completed")
                self.assertEqual(result.reason, "completed")
                self.assertTrue(result.oos_authorized)
                self.assertTrue(result.oos_consumed)
                self.assertEqual(verifier.call_count, 1)
                self.assertEqual(len(executor_calls), 1)
                self.assertEqual(ledger.read_calls, 1)
                self.assertEqual(ledger.reserve_calls, 1)
                self.assertEqual(ledger.start_calls, 1)
                self.assertIsNotNone(result.report_id)
                self.assertIsNotNone(result.gate_result_id)
                self.assertIsNone(result.promotion_id)
                with closing(sqlite3.connect(case["db_path"])) as conn:
                    conn.row_factory = sqlite3.Row
                    self.assertEqual(
                        conn.execute(
                            "SELECT status FROM b6_validation_tasks WHERE task_id=?",
                            (case["task_id"],),
                        ).fetchone()[0],
                        "completed",
                    )
                    self.assertEqual(
                        conn.execute(
                            "SELECT status FROM oos_budget_reservations WHERE task_key=?",
                            (case["task"].task_key,),
                        ).fetchone()[0],
                        "completed",
                    )
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM oos_evaluation_ledgers").fetchone()[0], 3)
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM immutable_backtest_reports").fetchone()[0], 1)
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM prototype_gate_results_v2").fetchone()[0], 1)
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM strategy_promotions").fetchone()[0], 0)
            finally:
                db.close()


class TestWorkerClaimAndPreflight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._fixture_root = Path(tempfile.mkdtemp(prefix="b6-worker-fixture-"))
        cls._baseline = cls._prepare_task(cls._fixture_root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._fixture_root, ignore_errors=True)
        super().tearDownClass()

    @staticmethod
    def _prepare_task(tmp_path: Path) -> dict:
        return _prepare_isolated_worker_fixture(tmp_path)

    @staticmethod
    def _worker(fixture: dict):
        from backend.services.b6_validation_worker import B6ValidationWorker

        db = StrategyDB(str(fixture["db_path"]))
        ledger = CountingLedger(db)
        worker = B6ValidationWorker(
            db,
            repo_root=fixture["repo_root"],
            b4_results_root=fixture["b4_results_root"],
            b5_bundle_root=fixture["bundle_dir"].parent,
            ledger=ledger,
        )
        return db, ledger, _configure_isolated_worker(worker, fixture)

    @classmethod
    def _clone_fixture(cls, tmp_path: Path) -> dict:
        db_path = tmp_path / "strategy.db"
        shutil.copy2(cls._baseline["db_path"], db_path)
        bundle_parent = tmp_path / "verified"
        bundle_parent.mkdir()
        bundle_dir = bundle_parent / cls._baseline["b5_bundle"]["bundle_id"]
        shutil.copytree(cls._baseline["bundle_dir"], bundle_dir)
        return {
            "repo_root": cls._baseline["repo_root"],
            "db_path": db_path,
            "b4_results_root": cls._baseline["b4_results_root"],
            "bundle_dir": bundle_dir,
            "task_id": cls._baseline["task_id"],
            "b4_artifact": cls._baseline["b4_artifact"],
            "b5_bundle": cls._baseline["b5_bundle"],
            "verified": cls._baseline["verified"],
            "supplement_dir": cls._baseline["supplement_dir"],
        }

    @staticmethod
    def _oos_counts(db_path: Path) -> dict[str, int]:
        with closing(sqlite3.connect(db_path)) as conn:
            return {
                table: conn.execute(f"select count(*) from {table}").fetchone()[0]
                for table in (
                    "oos_budget_state",
                    "oos_budget_reservations",
                    "oos_evaluation_ledgers",
                    "immutable_backtest_reports",
                    "prototype_gate_results_v2",
                )
            }

    def test_valid_explicit_task_claim_reaches_second_preflight_ready(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            fixture = self._clone_fixture(Path(raw_tmp))
            db, ledger, worker = self._worker(fixture)
            try:
                result = worker.run_task(fixture["task_id"])
                self.assertEqual(result.status, "ready_for_reservation")
                self.assertEqual(result.task_status, "running")
                self.assertTrue(result.ready_for_reservation)
                self.assertEqual(result.task_id, fixture["task_id"])
                self.assertEqual(ledger.read_calls, 1)
                self.assertEqual(ledger.reserve_calls, 0)
                self.assertEqual(self._oos_counts(fixture["db_path"]), {
                    "oos_budget_state": 0,
                    "oos_budget_reservations": 0,
                    "oos_evaluation_ledgers": 0,
                    "immutable_backtest_reports": 0,
                    "prototype_gate_results_v2": 0,
                })
            finally:
                db.close()

    def test_membership_only_formal_symbol_blocks_before_ledger_or_executor(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            fixture = _prepare_isolated_worker_fixture(
                Path(raw_tmp),
                membership_snapshot_id="pims_traderlens_v2_shsz_sw2021_pit_005",
            )
            _write_formal_scope_guard_fixture(
                fixture["repo_root"],
                fixture["protocol"].oos_window_start,
                membership_snapshot_id="pims_traderlens_v2_shsz_sw2021_pit_005",
                include_unknown_member=True,
            )
            db = StrategyDB(str(fixture["db_path"]))
            ledger = CountingLedger(db)
            from backend.services.b6_validation_worker import B6ValidationWorker

            worker = B6ValidationWorker(
                db,
                repo_root=fixture["repo_root"],
                b4_results_root=fixture["b4_results_root"],
                b5_bundle_root=fixture["bundle_dir"].parent,
                ledger=ledger,
            )
            _configure_isolated_worker(worker, fixture)
            try:
                result = worker.run_task(fixture["task_id"])
                self.assertEqual(result.status, "blocked")
                self.assertEqual(result.task_status, "blocked")
                self.assertEqual(result.reason, "b6_formal_scope_unavailable")
                self.assertEqual(ledger.read_calls, 0)
                self.assertEqual(ledger.reserve_calls, 0)
                with closing(sqlite3.connect(fixture["db_path"])) as verify_conn:
                    row = verify_conn.execute(
                        "SELECT status, blocking_reason_code, blocking_reason_detail "
                        "FROM b6_validation_tasks WHERE task_id = ?",
                        (fixture["task_id"],),
                    ).fetchone()
                    self.assertEqual(row[0], "blocked")
                    self.assertEqual(row[1], "b6_formal_scope_unavailable")
                    self.assertIn("formal stock_basic lifecycle", row[2])
                    self.assertEqual(
                        verify_conn.execute("SELECT COUNT(*) FROM oos_budget_state").fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        verify_conn.execute("SELECT COUNT(*) FROM oos_budget_reservations").fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        verify_conn.execute("SELECT COUNT(*) FROM oos_evaluation_ledgers").fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        verify_conn.execute("SELECT COUNT(*) FROM immutable_backtest_reports").fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        verify_conn.execute("SELECT COUNT(*) FROM prototype_gate_results_v2").fetchone()[0],
                        0,
                    )
            finally:
                db.close()

    def test_missing_b5_blocks_before_ledger_and_leaves_oos_empty(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            fixture = self._clone_fixture(Path(raw_tmp))
            db, ledger, worker = self._worker(fixture)
            worker.b5_bundle_root = Path(raw_tmp) / "missing-bundles"
            try:
                result = worker.run_task(fixture["task_id"])
                self.assertEqual(result.status, "blocked")
                self.assertEqual(result.task_status, "blocked")
                self.assertIn("b5_validation_inputs_missing", result.reason)
                self.assertEqual(ledger.read_calls, 0)
                self.assertEqual(ledger.reserve_calls, 0)
                self.assertEqual(self._oos_counts(fixture["db_path"])["oos_budget_reservations"], 0)
            finally:
                db.close()

    def test_tampered_b5_lineage_fails_invariant_before_ledger(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            fixture = self._clone_fixture(Path(raw_tmp))
            manifest_path = fixture["bundle_dir"] / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["lineage"]["strategy_revision_id"] = "tampered-revision"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            manifest_path.with_name("manifest.json.sha256").write_text(
                f"{hashlib.sha256(manifest_path.read_bytes()).hexdigest()}  manifest.json\n",
                encoding="utf-8",
            )
            db, ledger, worker = self._worker(fixture)
            try:
                result = worker.run_task(fixture["task_id"])
                self.assertEqual(result.status, "failed")
                self.assertEqual(result.task_status, "failed")
                self.assertEqual(result.reason, "invariant_error")
                self.assertEqual(ledger.read_calls, 0)
                self.assertEqual(ledger.reserve_calls, 0)
                self.assertEqual(self._oos_counts(fixture["db_path"])["oos_budget_reservations"], 0)
            finally:
                db.close()

    def test_ledger_unavailable_or_exhausted_blocks_after_one_read(self):
        from backend.services.b6_validation_worker import B6ValidationWorker

        class UnavailableLedger(CountingLedger):
            def get_ledger_state(self, *args, **kwargs):
                self.read_calls += 1
                raise OSError("ledger temporarily unavailable")

        class ExhaustedLedger(CountingLedger):
            def get_ledger_state(self, *args, **kwargs):
                self.read_calls += 1
                return {
                    "completed_draw_count": 3,
                    "next_oos_draw_index": 4,
                    "budget_status": "oos_budget_exhausted",
                    "active_reservation_id": None,
                }

        for ledger_type, expected_reason in (
            (UnavailableLedger, "b6_ledger_unavailable"),
            (ExhaustedLedger, "b6_oos_budget_unavailable"),
        ):
            with self.subTest(ledger=ledger_type.__name__), tempfile.TemporaryDirectory() as raw_tmp:
                fixture = self._clone_fixture(Path(raw_tmp))
                db = StrategyDB(str(fixture["db_path"]))
                ledger = ledger_type(db)
                worker = B6ValidationWorker(
                    db,
                    repo_root=fixture["repo_root"],
                    b4_results_root=fixture["b4_results_root"],
                    b5_bundle_root=fixture["bundle_dir"].parent,
                    ledger=ledger,
                )
                _configure_isolated_worker(worker, fixture)
                try:
                    result = worker.run_task(fixture["task_id"])
                    self.assertEqual(result.status, "blocked")
                    self.assertEqual(result.task_status, "blocked")
                    self.assertEqual(result.reason, expected_reason)
                    self.assertEqual(ledger.read_calls, 1)
                    self.assertEqual(ledger.reserve_calls, 0)
                finally:
                    db.close()

    def test_task_identity_mismatch_fails_before_ledger(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            fixture = self._clone_fixture(Path(raw_tmp))
            bad_key = "f" * 64
            with closing(sqlite3.connect(fixture["db_path"])) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "select payload_json from b6_validation_tasks where task_id = ?",
                    (fixture["task_id"],),
                ).fetchone()
                payload = json.loads(row["payload_json"])
                payload["task_key"] = bad_key
                conn.execute(
                    "update b6_validation_tasks set task_key = ?, payload_json = ? where task_id = ?",
                    (bad_key, json.dumps(payload, sort_keys=True), fixture["task_id"]),
                )
                conn.commit()
            db, ledger, worker = self._worker(fixture)
            try:
                result = worker.run_task(fixture["task_id"])
                self.assertEqual(result.status, "failed")
                self.assertEqual(result.task_status, "failed")
                self.assertEqual(result.reason, "invariant_error")
                self.assertEqual(ledger.read_calls, 0)
            finally:
                db.close()

    def test_missing_id_latest_and_nonexecutable_states_do_not_claim(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            fixture = self._clone_fixture(Path(raw_tmp))
            db, ledger, worker = self._worker(fixture)
            try:
                with self.assertRaises(ValueError):
                    worker.run_task("")
                not_found = worker.run_task("latest")
                self.assertEqual(not_found.status, "not_found")
                self.assertEqual(ledger.read_calls, 0)

                with closing(sqlite3.connect(fixture["db_path"])) as conn:
                    conn.execute(
                        "update b6_validation_tasks set status = 'blocked' where task_id = ?",
                        (fixture["task_id"],),
                    )
                    conn.commit()
                blocked = worker.run_task(fixture["task_id"])
                self.assertEqual(blocked.status, "blocked")
                self.assertEqual(blocked.reason, "task_not_executable")
                self.assertEqual(ledger.read_calls, 0)
            finally:
                db.close()

    def test_running_reentry_returns_recovery_without_new_attempt(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            fixture = self._clone_fixture(Path(raw_tmp))
            db, ledger, worker = self._worker(fixture)
            try:
                first = worker.run_task(fixture["task_id"])
                second = worker.run_task(fixture["task_id"])
                self.assertEqual(first.status, "ready_for_reservation")
                self.assertEqual(second.status, "recovery_required")
                self.assertEqual(second.task_status, "running")
                self.assertEqual(ledger.read_calls, 1)
            finally:
                db.close()

    def test_two_file_backed_connections_have_one_claim_winner(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            fixture = self._clone_fixture(Path(raw_tmp))
            db1, ledger1, worker1 = self._worker(fixture)
            db2, ledger2, worker2 = self._worker(fixture)
            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(
                        lambda worker: worker.run_task(fixture["task_id"]),
                        (worker1, worker2),
                    ))
                self.assertEqual(sum(result.status == "ready_for_reservation" for result in results), 1)
                self.assertEqual(sum(result.status in {"not_claimed", "recovery_required"} for result in results), 1)
                self.assertEqual(ledger1.read_calls + ledger2.read_calls, 1)
                with closing(sqlite3.connect(fixture["db_path"])) as conn:
                    self.assertEqual(
                        conn.execute("select count(*) from b6_validation_tasks").fetchone()[0],
                        1,
                    )
            finally:
                db1.close()
                db2.close()

    def test_worker_source_has_no_production_engine_or_promotion_shortcut(self):
        import backend.services.b6_validation_worker as worker_module

        source = inspect.getsource(worker_module)
        for forbidden in (
            "run_event_backtest",
            "PrototypeGateV2",
            "StrategyPromotionReducer",
            "promote_to_prototype_passed(",
            "SignalBoard",
        ):
            self.assertNotIn(forbidden, source)

    def test_transition_write_failure_rolls_back_and_fails_loud(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            fixture = self._clone_fixture(Path(raw_tmp))

            class FailingStrategyDB(StrategyDB):
                def update_b6_task_status(self, *args, **kwargs):
                    raise OSError("injected transition write failure")

            db = FailingStrategyDB(str(fixture["db_path"]))
            ledger = CountingLedger(db)
            from backend.services.b6_validation_worker import B6ValidationWorker

            worker = B6ValidationWorker(
                db,
                repo_root=fixture["repo_root"],
                b4_results_root=fixture["b4_results_root"],
                b5_bundle_root=Path(raw_tmp) / "missing-bundles",
                ledger=ledger,
            )
            _configure_isolated_worker(worker, fixture)
            try:
                with self.assertRaises(OSError):
                    worker.run_task(fixture["task_id"])
                task = db.get_b6_task_by_id(fixture["task_id"])
                self.assertEqual(task.status, "running")
                self.assertEqual(ledger.read_calls, 0)
            finally:
                db.close()

    def test_production_envelope_is_v2_and_real_executor_accepts_it(self):
        from copy import deepcopy
        from types import SimpleNamespace

        from backend.services.b6_same_draw_executor import (
            _validate_envelope,
            execute_production_same_draw,
        )
        from backend.services.b5_oos_types import B6SameDrawOOSResult
        from backend.services.b6_validation_worker import B6ValidationWorker
        from tests.test_b6_same_draw_executor import _verified_synthetic_supplement
        from tests.test_b6_same_draw_result_contract import _same_draw_result_payload

        with _verified_synthetic_supplement() as (root, source_envelope, _loader):
            prepared_supplement = source_envelope["prepared_supplement"]
            source_identity = source_envelope["identity"]
            task = SimpleNamespace(
                task_id=source_identity["task_id"],
                task_key=source_identity["task_key"],
                protocol_snapshot_id=source_identity["protocol_snapshot_id"],
                strategy_revision_id=source_identity["strategy_revision_id"],
                b5_bundle_id=source_identity["b5_bundle_id"],
                b5_bundle_manifest_sha256=source_identity["b5_bundle_manifest_sha256"],
            )
            protocol = SimpleNamespace(
                protocol_snapshot_id=source_identity["protocol_snapshot_id"],
                strategy_revision_id=source_identity["strategy_revision_id"],
                data_snapshot_hash=source_identity["data_snapshot_hash"],
                shared_oos_window_id=source_identity["shared_oos_window_id"],
                oos_window_start=date.fromisoformat(source_identity["oos_start"]),
                oos_window_end=date.fromisoformat(source_identity["oos_end"]),
            )
            b4_artifact = {
                "artifact_id": source_identity["b4_artifact_id"],
                "manifest_sha256": source_identity["b4_manifest_sha256"],
                "event_result_sha256": source_identity["b4_event_result_sha256"],
            }
            b5_bundle = {
                "lineage": {
                    "formal_snapshot": {
                        "id": source_identity["formal_snapshot_id"],
                        "manifest_sha256": source_identity["formal_snapshot_manifest_sha256"],
                    },
                    "membership": {
                        "id": source_identity["membership_snapshot_id"],
                        "manifest_sha256": source_identity["membership_manifest_sha256"],
                    },
                    "calendar": {
                        "id": source_identity["calendar_id"],
                        "manifest_sha256": source_identity["calendar_manifest_sha256"],
                    },
                    "execution_supplement": {
                        "manifest_sha256": source_identity["execution_input_hash"],
                    },
                },
            }
            reservation = SimpleNamespace(
                reservation_id=source_envelope["reservation_id"],
                oos_draw_index=source_envelope["oos_draw_index"],
            )
            worker = B6ValidationWorker(None, repo_root=root)
            envelope = worker._build_envelope(
                task,
                protocol,
                b4_artifact,
                b5_bundle,
                reservation,
                prepared_supplement,
            )

            self.assertEqual(
                envelope["identity"]["result_schema_version"],
                "b6_same_draw_oos_result.v2",
            )
            _validate_envelope(envelope)
            result = execute_production_same_draw(envelope, repo_root=root)
            self.assertEqual(result.identity.result_schema_version, "b6_same_draw_oos_result.v2")
            self.assertIsNotNone(result.read_audit)
            self.assertRegex(result.base_cost_result.assumptions_hash, r"^[0-9a-f]{64}$")
            self.assertRegex(result.stress_cost_result.assumptions_hash, r"^[0-9a-f]{64}$")
            result.assert_production_terminal_eligible()

            legacy_envelope = deepcopy(envelope)
            legacy_envelope["identity"]["result_schema_version"] = "b6_same_draw_oos_result.v1"
            with self.assertRaises(ValueError):
                _validate_envelope(legacy_envelope)
            legacy = B6SameDrawOOSResult.model_validate(_same_draw_result_payload())
            self.assertEqual(legacy.identity.result_schema_version, "b6_same_draw_oos_result.v1")
            with self.assertRaises(ValueError):
                legacy.assert_production_terminal_eligible()


class TestWorkerReservationAndRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._fixture_root = Path(tempfile.mkdtemp(prefix="b6-worker-phase5c-"))
        cls._baseline = _prepare_phase5c_fixture(cls._fixture_root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._fixture_root, ignore_errors=True)
        super().tearDownClass()

    @classmethod
    def _clone_fixture(cls, tmp_path: Path) -> dict:
        db_path = tmp_path / "strategy.db"
        shutil.copy2(cls._baseline["db_path"], db_path)
        bundle_parent = tmp_path / "verified"
        bundle_parent.mkdir()
        bundle_dir = bundle_parent / cls._baseline["b5_bundle"]["bundle_id"]
        shutil.copytree(cls._baseline["bundle_dir"], bundle_dir)
        return {
            "repo_root": cls._baseline["repo_root"],
            "db_path": db_path,
            "b4_results_root": cls._baseline["b4_results_root"],
            "bundle_dir": bundle_dir,
            "task_id": cls._baseline["task_id"],
            "b4_artifact": cls._baseline["b4_artifact"],
            "b5_bundle": cls._baseline["b5_bundle"],
            "verified": cls._baseline["verified"],
            "supplement_dir": cls._baseline["supplement_dir"],
        }

    @staticmethod
    def _worker(fixture, *, ledger=None, ledger_class=None, db_class=StrategyDB):
        from backend.services.b6_validation_worker import B6ValidationWorker
        from backend.services.b4_protocol_types import DailyPortfolioSnapshot, EventBacktestResult

        db = db_class(str(fixture["db_path"]))
        protocol = db.get_protocol_snapshot(
            db.get_b6_task_by_id(fixture["task_id"]).protocol_snapshot_id
        )

        def b4_result_loader(artifact):
            return EventBacktestResult(
                result_id="b4_phase5c_oos_synthetic",
                strategy_revision_id=artifact["strategy_revision_id"],
                protocol_snapshot_id=artifact["protocol_snapshot_id"],
                evaluation_mode="formal_backtest",
                backtest_start=protocol.oos_window_start,
                backtest_end=protocol.oos_window_end,
                order_intents=(),
                fills=(),
                rejected_orders=(),
                future_violations=(),
                final_portfolio=DailyPortfolioSnapshot(
                    snapshot_id="portfolio_phase5c_oos_synthetic",
                    snapshot_date=protocol.oos_window_end,
                    cash=100000.0,
                    positions=(),
                    portfolio_value=100000.0,
                ),
                frozen_at=protocol.oos_window_end,
            )

        if ledger is None and ledger_class is not None:
            ledger = ledger_class(db)
        worker = B6ValidationWorker(
            db,
            repo_root=fixture["repo_root"],
            b4_results_root=fixture["b4_results_root"],
            b5_bundle_root=fixture["bundle_dir"].parent,
            b4_result_loader=b4_result_loader,
            ledger=ledger,
        )
        return db, _configure_isolated_worker(worker, fixture)

    @staticmethod
    def _oos_counts(db_path: Path) -> dict[str, int]:
        with closing(sqlite3.connect(db_path)) as conn:
            return {
                table: conn.execute(f"select count(*) from {table}").fetchone()[0]
                for table in (
                    "oos_budget_state",
                    "oos_budget_reservations",
                    "oos_evaluation_ledgers",
                    "immutable_backtest_reports",
                    "prototype_gate_results_v2",
                )
            }

    def test_fake_same_draw_reserves_starts_and_completes_once(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            fixture = self._clone_fixture(Path(raw_tmp))
            db, worker = self._worker(fixture)
            calls = []

            def execute_same_draw(envelope):
                calls.append(envelope)
                return _same_draw_from_envelope(envelope)

            try:
                result = worker.run_task(
                    fixture["task_id"],
                    execute_same_draw=execute_same_draw,
                )
                self.assertEqual(result.status, "completed")
                self.assertEqual(result.task_status, "completed")
                self.assertEqual(len(calls), 1)
                self.assertEqual(result.oos_authorized, True)
                self.assertEqual(result.oos_consumed, True)
                self.assertIsNotNone(result.report_id)
                self.assertIsNotNone(result.gate_result_id)
            finally:
                db.close()

    def test_same_draw_execution_uses_protocol_oos_while_b4_result_remains_is(self):
        with tempfile.TemporaryDirectory(prefix="b6-e6-is-oos-separation-") as raw_tmp:
            case = _prepare_isolated_worker_fixture(
                Path(raw_tmp),
                b4_window=(date(2023, 1, 1), date(2023, 12, 31)),
            )
            db = StrategyDB(str(case["db_path"]))
            case["db"] = db
            events: list[str] = []
            ledger = _RecordingOOSLedger(db, events)
            worker = _configure_isolated_worker(_make_e6_worker(case, ledger), case)
            calls: list[dict] = []

            def execute_same_draw(envelope):
                calls.append(envelope)
                self.assertEqual(
                    envelope["identity"]["oos_start"],
                    case["protocol"].oos_window_start.isoformat(),
                )
                self.assertEqual(
                    envelope["identity"]["oos_end"],
                    case["protocol"].oos_window_end.isoformat(),
                )
                self.assertNotEqual(
                    envelope["identity"]["oos_start"],
                    case["b4_is_window"][0].isoformat(),
                )
                events.append("executor")
                return _same_draw_from_envelope(envelope)

            try:
                result = worker.run_task(
                    case["task_id"],
                    execute_same_draw=execute_same_draw,
                )
                self.assertEqual(result.status, "completed")
                self.assertEqual(result.task_status, "completed")
                self.assertIsNone(result.promotion_id)
                self.assertEqual(len(calls), 1)
                self.assertEqual(ledger.read_calls, 1)
                self.assertEqual(ledger.reserve_calls, 1)
                self.assertEqual(ledger.start_calls, 1)
                self.assertEqual(events, ["ledger_state", "reserve", "start", "executor"])
                with closing(sqlite3.connect(case["db_path"])) as verify_conn:
                    verify_conn.row_factory = sqlite3.Row
                    task_row = verify_conn.execute(
                        "SELECT status FROM b6_validation_tasks WHERE task_id = ?",
                        (case["task_id"],),
                    ).fetchone()
                    self.assertEqual(task_row["status"], "completed")
                    reservation_row = verify_conn.execute(
                        """
                        SELECT status, task_key, protocol_snapshot_id FROM oos_budget_reservations
                        WHERE task_key = (
                            SELECT task_key FROM b6_validation_tasks WHERE task_id = ?
                        )
                        """,
                        (case["task_id"],),
                    ).fetchone()
                    self.assertEqual(reservation_row["status"], "completed")
                    task_key = verify_conn.execute(
                        "SELECT task_key FROM b6_validation_tasks WHERE task_id = ?",
                        (case["task_id"],),
                    ).fetchone()[0]
                    self.assertEqual(reservation_row["task_key"], task_key)
                    self.assertEqual(
                        reservation_row["protocol_snapshot_id"],
                        case["protocol"].protocol_snapshot_id,
                    )
                    ledger_rows = verify_conn.execute(
                        """
                        SELECT ledger_version, payload_json
                        FROM oos_evaluation_ledgers
                        ORDER BY ledger_version
                        """
                    ).fetchall()
                    self.assertEqual([row[0] for row in ledger_rows], [1, 2, 3])
                    ledger_payloads = [json.loads(row[1]) for row in ledger_rows]
                    self.assertEqual(
                        [payload["oos_evaluation_count"] for payload in ledger_payloads],
                        [0, 0, 1],
                    )
                    self.assertEqual(
                        [payload["budget_status"] for payload in ledger_payloads],
                        ["reserved", "reserved", "available"],
                    )
                    state_row = verify_conn.execute(
                        """
                        SELECT consumed_draw_count, next_oos_draw_index, active_reservation_id
                        FROM oos_budget_state
                        """
                    ).fetchone()
                    self.assertEqual(tuple(state_row), (1, 2, None))
                    self.assertEqual(
                        verify_conn.execute("SELECT COUNT(*) FROM oos_evaluation_ledgers").fetchone()[0],
                        3,
                    )
                    report_row = verify_conn.execute(
                        "SELECT payload_json FROM immutable_backtest_reports"
                    ).fetchone()
                    self.assertIsNotNone(report_row)
                    stored_report = json.loads(report_row["payload_json"])
                    report_payload = json.loads(stored_report["report_payload_json"])
                    self.assertEqual(
                        report_payload["b4_lineage"]["artifact_id"],
                        case["b4_artifact"]["artifact_id"],
                    )
                    self.assertEqual(
                        report_payload["oos_window"]["start"],
                        case["protocol"].oos_window_start.isoformat(),
                    )
                    self.assertEqual(
                        verify_conn.execute("SELECT COUNT(*) FROM prototype_gate_results_v2").fetchone()[0],
                        1,
                    )
                    self.assertEqual(
                        verify_conn.execute("SELECT COUNT(*) FROM strategy_promotions").fetchone()[0],
                        0,
                    )
            finally:
                db.close()

    def test_wrong_verified_b4_is_range_fails_before_ledger(self):
        with tempfile.TemporaryDirectory(prefix="b6-e6-b4-range-") as raw_tmp:
            case = _prepare_isolated_worker_fixture(
                Path(raw_tmp),
                b4_window=(date(2023, 1, 1), date(2023, 12, 31)),
            )
            case["b4_artifact"]["is_range"] = {
                "start": date(2022, 1, 1).isoformat(),
                "end": date(2022, 12, 31).isoformat(),
            }
            db = StrategyDB(str(case["db_path"]))
            case["db"] = db
            events: list[str] = []
            ledger = _RecordingOOSLedger(db, events)
            worker = _configure_isolated_worker(_make_e6_worker(case, ledger), case)
            calls: list[dict] = []
            try:
                result = worker.run_task(
                    case["task_id"],
                    execute_same_draw=lambda envelope: calls.append(envelope),
                )
                self.assertEqual(result.status, "failed")
                self.assertEqual(result.task_status, "failed")
                self.assertEqual(result.reason, "invariant_error")
                self.assertEqual(ledger.read_calls, 1)
                self.assertEqual(ledger.reserve_calls, 0)
                self.assertEqual(ledger.start_calls, 0)
                self.assertEqual(calls, [])
                with closing(sqlite3.connect(case["db_path"])) as verify_conn:
                    row = verify_conn.execute(
                        "SELECT status, blocking_reason_code, blocking_reason_detail FROM b6_validation_tasks WHERE task_id = ?",
                        (case["task_id"],),
                    ).fetchone()
                    self.assertEqual(tuple(row), (
                        "failed",
                        "invariant_error",
                        "B4 event result window does not match verified B4 IS window",
                    ))
                    self.assertEqual(
                        verify_conn.execute("SELECT COUNT(*) FROM oos_budget_reservations").fetchone()[0],
                        0,
                    )
            finally:
                db.close()

    def test_reserve_rejection_blocks_without_reservation_or_consumption(self):
        from backend.services.oos_budget_ledger import OOSBudgetLedger

        class RejectingLedger(OOSBudgetLedger):
            reserve_calls = 0

            def reserve_oos_draw(self, *args, **kwargs):
                self.reserve_calls += 1
                raise ValueError("budget became unavailable")

        with tempfile.TemporaryDirectory() as raw_tmp:
            fixture = self._clone_fixture(Path(raw_tmp))
            db, worker = self._worker(fixture, ledger_class=RejectingLedger)
            try:
                result = worker.run_task(fixture["task_id"], execute_same_draw=lambda _: self.fail("executor called"))
                self.assertEqual(result.status, "blocked")
                self.assertEqual(result.reason, "b6_oos_budget_unavailable")
                self.assertEqual(worker.ledger.reserve_calls, 1)
                self.assertEqual(self._oos_counts(fixture["db_path"]), {
                    "oos_budget_state": 0,
                    "oos_budget_reservations": 0,
                    "oos_evaluation_ledgers": 0,
                    "immutable_backtest_reports": 0,
                    "prototype_gate_results_v2": 0,
                })
            finally:
                db.close()

    def test_start_failure_releases_without_consumption(self):
        from backend.services.oos_budget_ledger import OOSBudgetLedger

        class StartFailLedger(OOSBudgetLedger):
            def start_execution(self, reservation_id):
                raise OSError("injected start failure")

        with tempfile.TemporaryDirectory() as raw_tmp:
            fixture = self._clone_fixture(Path(raw_tmp))
            db, worker = self._worker(fixture, ledger_class=StartFailLedger)
            try:
                result = worker.run_task(fixture["task_id"], execute_same_draw=lambda _: self.fail("executor called"))
                self.assertEqual(result.status, "blocked")
                self.assertEqual(result.reason, "b6_start_failed")
                with closing(sqlite3.connect(fixture["db_path"])) as conn:
                    self.assertEqual(conn.execute("select status from oos_budget_reservations").fetchone()[0], "released")
                    self.assertEqual(conn.execute("select consumed_draw_count from oos_budget_state").fetchone()[0], 0)
            finally:
                db.close()

    def test_reserved_recovery_releases_without_second_reserve(self):
        from backend.services.oos_budget_ledger import OOSBudgetLedger

        class CountingReserveLedger(OOSBudgetLedger):
            def __init__(self, db):
                super().__init__(db)
                self.reserve_calls = 0

            def reserve_oos_draw(self, *args, **kwargs):
                self.reserve_calls += 1
                return super().reserve_oos_draw(*args, **kwargs)

        with tempfile.TemporaryDirectory() as raw_tmp:
            fixture = self._clone_fixture(Path(raw_tmp))
            db, worker = self._worker(fixture, ledger_class=CountingReserveLedger)
            task = db.get_b6_task_by_id(fixture["task_id"])
            protocol = db.get_protocol_snapshot(task.protocol_snapshot_id)
            db.claim_b6_task(task.task_id)
            reservation = worker.ledger.reserve_oos_draw(
                theme_id=protocol.theme_id,
                hypothesis_source_snapshot_id=protocol.hypothesis_source_snapshot_id,
                strategy_config_hash=protocol.strategy_config_hash,
                data_snapshot_hash=protocol.data_snapshot_hash,
                gate_criteria_hash=protocol.gate_criteria_hash,
                shared_oos_window_id=protocol.shared_oos_window_id,
                idempotency_key=task.task_key,
                task_key=task.task_key,
                protocol_snapshot_id=protocol.protocol_snapshot_id,
            )
            calls = []
            try:
                result = worker.run_task(
                    task.task_id,
                    execute_same_draw=lambda _: calls.append(True),
                )
                self.assertEqual(result.status, "queued")
                self.assertEqual(result.reason, "requeued_after_release")
                self.assertEqual(worker.ledger.reserve_calls, 1)
                self.assertEqual(calls, [])
                with closing(sqlite3.connect(fixture["db_path"])) as conn:
                    self.assertEqual(
                        conn.execute(
                            "SELECT status FROM oos_budget_reservations WHERE reservation_id = ?",
                            (reservation.reservation_id,),
                        ).fetchone()[0],
                        "released",
                    )
                    self.assertEqual(
                        conn.execute("SELECT consumed_draw_count FROM oos_budget_state").fetchone()[0],
                        0,
                    )
            finally:
                db.close()

    def test_executor_exception_fails_after_start_without_rerun(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            fixture = self._clone_fixture(Path(raw_tmp))
            db, worker = self._worker(fixture)
            calls = []

            def execute_and_fail(_):
                calls.append(True)
                raise RuntimeError("synthetic executor failure")

            try:
                result = worker.run_task(
                    fixture["task_id"],
                    execute_same_draw=execute_and_fail,
                )
                self.assertEqual(result.status, "failed")
                self.assertEqual(result.reason, "b6_fail_after_start")
                self.assertEqual(len(calls), 1)
                with closing(sqlite3.connect(fixture["db_path"])) as conn:
                    self.assertEqual(
                        conn.execute("SELECT status FROM oos_budget_reservations").fetchone()[0],
                        "failed",
                    )
                    self.assertEqual(
                        conn.execute("SELECT consumed_draw_count FROM oos_budget_state").fetchone()[0],
                        1,
                    )
                    self.assertEqual(
                        conn.execute("SELECT COUNT(*) FROM immutable_backtest_reports").fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        conn.execute("SELECT COUNT(*) FROM prototype_gate_results_v2").fetchone()[0],
                        0,
                    )
            finally:
                db.close()

    def test_terminal_write_failure_consumes_once_without_success_rows(self):
        class FailingTerminalDB(StrategyDB):
            def store_b6_terminal_result_tx(self, *args, **kwargs):
                raise OSError("synthetic terminal write failure")

        with tempfile.TemporaryDirectory() as raw_tmp:
            fixture = self._clone_fixture(Path(raw_tmp))
            db, worker = self._worker(fixture, db_class=FailingTerminalDB)
            calls = []

            def execute(envelope):
                calls.append(envelope)
                return _same_draw_from_envelope(envelope)

            try:
                result = worker.run_task(
                    fixture["task_id"],
                    execute_same_draw=execute,
                )
                self.assertEqual(result.status, "failed")
                self.assertEqual(result.reason, "b6_fail_after_start")
                self.assertEqual(len(calls), 1)
                with closing(sqlite3.connect(fixture["db_path"])) as conn:
                    conn.row_factory = sqlite3.Row
                    task = conn.execute(
                        "SELECT task_key, protocol_snapshot_id, status "
                        "FROM b6_validation_tasks WHERE task_id = ?",
                        (fixture["task_id"],),
                    ).fetchone()
                    self.assertEqual(task["status"], "failed")
                    reservation = conn.execute(
                        "SELECT reservation_id, status, terminal_reason, task_key, "
                        "protocol_snapshot_id, oos_draw_index "
                        "FROM oos_budget_reservations WHERE task_key = ?",
                        (task["task_key"],),
                    ).fetchone()
                    self.assertIsNotNone(reservation)
                    self.assertEqual(reservation["status"], "failed")
                    self.assertIn(
                        "execution_or_terminal_failed:",
                        reservation["terminal_reason"],
                    )
                    self.assertEqual(reservation["task_key"], task["task_key"])
                    self.assertEqual(
                        reservation["protocol_snapshot_id"],
                        task["protocol_snapshot_id"],
                    )
                    self.assertEqual(reservation["oos_draw_index"], 1)

                    protocol = db.get_protocol_snapshot(task["protocol_snapshot_id"])
                    audit_rows = conn.execute(
                        "SELECT ledger_snapshot_id, theme_id, "
                        "hypothesis_source_snapshot_id, ledger_version, payload_json "
                        "FROM oos_evaluation_ledgers "
                        "WHERE theme_id = ? AND hypothesis_source_snapshot_id = ? "
                        "ORDER BY ledger_version",
                        (protocol.theme_id, protocol.hypothesis_source_snapshot_id),
                    ).fetchall()
                    self.assertEqual(len(audit_rows), 3)

                    # OOSEvaluationLedger stores immutable snapshots rather than an
                    # event_type column.  The reserve/start/fail_after_start order
                    # is therefore asserted from the exact snapshot transitions
                    # emitted by those three ledger methods.
                    audit_phases = []
                    for row in audit_rows:
                        payload = json.loads(row["payload_json"])
                        self.assertEqual(
                            payload["ledger_snapshot_id"],
                            row["ledger_snapshot_id"],
                        )
                        self.assertEqual(payload["theme_id"], row["theme_id"])
                        self.assertEqual(
                            payload["hypothesis_source_snapshot_id"],
                            row["hypothesis_source_snapshot_id"],
                        )
                        self.assertEqual(payload["ledger_version"], row["ledger_version"])
                        self.assertEqual(payload["theme_id"], protocol.theme_id)
                        self.assertEqual(
                            payload["hypothesis_source_snapshot_id"],
                            protocol.hypothesis_source_snapshot_id,
                        )
                        self.assertEqual(payload["oos_budget_limit"], 3)
                        self.assertEqual(payload["active_reservation_ids"], [])
                        self.assertEqual(payload["completed_evaluation_ids"], [])
                        self.assertEqual(payload["report_ids"], [])
                        if payload["ledger_version"] in (1, 2):
                            audit_phases.append((
                                payload["ledger_version"],
                                "reserve" if payload["ledger_version"] == 1 else "start",
                                payload["budget_status"],
                                payload["oos_evaluation_count"],
                                payload["next_oos_draw_index"],
                            ))
                        else:
                            audit_phases.append((
                                payload["ledger_version"],
                                "fail_after_start",
                                payload["budget_status"],
                                payload["oos_evaluation_count"],
                                payload["next_oos_draw_index"],
                            ))
                    self.assertEqual(audit_phases, [
                        (1, "reserve", "reserved", 0, 1),
                        (2, "start", "reserved", 0, 1),
                        (3, "fail_after_start", "available", 1, 1),
                    ])

                    state = conn.execute(
                        "SELECT consumed_draw_count, next_oos_draw_index, "
                        "budget_status, active_reservation_id "
                        "FROM oos_budget_state"
                    ).fetchone()
                    self.assertEqual(state["consumed_draw_count"], 1)
                    self.assertEqual(state["next_oos_draw_index"], 2)
                    self.assertEqual(state["budget_status"], "available")
                    self.assertIsNone(state["active_reservation_id"])
                    self.assertEqual(
                        conn.execute(
                            "SELECT COUNT(*) FROM immutable_backtest_reports"
                        ).fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        conn.execute(
                            "SELECT COUNT(*) FROM prototype_gate_results_v2"
                        ).fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        self._oos_counts(fixture["db_path"]),
                        {
                            "oos_budget_state": 1,
                            "oos_budget_reservations": 1,
                            "oos_evaluation_ledgers": 3,
                            "immutable_backtest_reports": 0,
                            "prototype_gate_results_v2": 0,
                        },
                    )
            finally:
                db.close()

    def test_started_failure_consumes_once_and_retry_does_not_execute(self):
        from backend.services.oos_budget_ledger import OOSBudgetLedger

        with tempfile.TemporaryDirectory() as raw_tmp:
            fixture = self._clone_fixture(Path(raw_tmp))
            db = StrategyDB(str(fixture["db_path"]))
            task = db.get_b6_task_by_id(fixture["task_id"])
            protocol = db.get_protocol_snapshot(task.protocol_snapshot_id)
            ledger = OOSBudgetLedger(db)
            db.claim_b6_task(task.task_id)
            reservation = ledger.reserve_oos_draw(
                theme_id=protocol.theme_id,
                hypothesis_source_snapshot_id=protocol.hypothesis_source_snapshot_id,
                strategy_config_hash=protocol.strategy_config_hash,
                data_snapshot_hash=protocol.data_snapshot_hash,
                gate_criteria_hash=protocol.gate_criteria_hash,
                shared_oos_window_id=protocol.shared_oos_window_id,
                idempotency_key=task.task_key,
                task_key=task.task_key,
                protocol_snapshot_id=protocol.protocol_snapshot_id,
            )
            ledger.start_execution(reservation.reservation_id)
            db.close()
            db, worker = self._worker(fixture, ledger_class=OOSBudgetLedger)
            calls = []

            def should_not_run(_):
                calls.append(True)
                raise AssertionError("started recovery must not rerun executor")

            try:
                result = worker.run_task(task.task_id, execute_same_draw=should_not_run)
                self.assertEqual(result.status, "failed")
                self.assertEqual(result.reason, "b6_fail_after_start")
                self.assertEqual(calls, [])
                with closing(sqlite3.connect(fixture["db_path"])) as conn:
                    self.assertEqual(conn.execute("select status from oos_budget_reservations").fetchone()[0], "failed")
                    self.assertEqual(conn.execute("select consumed_draw_count from oos_budget_state").fetchone()[0], 1)
            finally:
                db.close()

    def test_completed_retry_returns_durable_chain_without_second_execution(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            fixture = self._clone_fixture(Path(raw_tmp))
            db, worker = self._worker(fixture)
            calls = []

            def execute(envelope):
                calls.append(envelope)
                return _same_draw_from_envelope(envelope)

            try:
                first = worker.run_task(fixture["task_id"], execute_same_draw=execute)
                second = worker.run_task(fixture["task_id"], execute_same_draw=lambda _: self.fail("completed retry executed"))
                self.assertEqual(first.status, "completed")
                self.assertEqual(second.status, "completed")
                self.assertEqual(second.report_id, first.report_id)
                self.assertEqual(second.gate_result_id, first.gate_result_id)
                self.assertEqual(len(calls), 1)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
