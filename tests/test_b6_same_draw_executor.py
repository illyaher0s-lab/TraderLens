"""Synthetic/temp-boundary tests for the Phase 5D2 same-draw executor."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq


SYMBOLS = ("000001.SZ", "000002.SZ", "000003.SZ")
FORMAL_REL = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal")
MEMBERSHIP_ID = "pims_traderlens_v2_shsz_sw2021_pit_005"
SOURCE_INVENTORY_ID = "2fe8321a5f644b9b"


def _write_table(path: Path, rows: list[dict], schema: pa.Schema | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sidecar(path: Path) -> None:
    path.with_name(path.name + ".sha256").write_text(
        f"{_sha(path)}  {path.name}\n", encoding="utf-8"
    )


def _build_synthetic_repo(root: Path) -> tuple[Path, date, date]:
    days = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(280))
    formal = root / FORMAL_REL

    calendar_schema = pa.schema([
        pa.field("exchange", pa.string()),
        pa.field("cal_date", pa.string()),
        pa.field("is_open", pa.int64()),
    ])
    _write_table(
        formal / "trade_cal/part.parquet",
        [
            {"exchange": exchange, "cal_date": day.strftime("%Y%m%d"), "is_open": 1}
            for day in days
            for exchange in ("SSE", "SZSE")
        ],
        calendar_schema,
    )

    stock_schema = pa.schema([
        pa.field("ts_code", pa.string()),
        pa.field("list_date", pa.string()),
        pa.field("delist_date", pa.string()),
    ])
    _write_table(
        formal / "stock_basic/list_status=L/part.parquet",
        [{"ts_code": symbol, "list_date": "20240101", "delist_date": None} for symbol in SYMBOLS],
        stock_schema,
    )
    for status in ("D", "P"):
        _write_table(formal / f"stock_basic/list_status={status}/part.parquet", [], stock_schema)

    membership_dir = root / "data/pit/pit_membership_snapshots" / MEMBERSHIP_ID
    membership_rows = [
        {
            "symbol": symbol,
            "effective_from": date(2024, 1, 1),
            "effective_to": None,
            "source": "synthetic_formal_fixture",
            "snapshot_id": MEMBERSHIP_ID,
        }
        for symbol in SYMBOLS
    ]
    records_path = membership_dir / "records.parquet"
    _write_table(records_path, membership_rows)
    _sidecar(records_path)
    membership_manifest = {"snapshot_id": MEMBERSHIP_ID, "records_parquet_sha256": _sha(records_path), "frozen": True}
    manifest_path = membership_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(membership_manifest), encoding="utf-8")
    _sidecar(manifest_path)

    daily_schema = pa.schema([
        pa.field("ts_code", pa.string()), pa.field("trade_date", pa.string()),
        pa.field("open", pa.float64()), pa.field("high", pa.float64()),
        pa.field("low", pa.float64()), pa.field("close", pa.float64()),
        pa.field("amount", pa.float64()), pa.field("vol", pa.float64()),
    ])
    adj_schema = pa.schema([pa.field("ts_code", pa.string()), pa.field("adj_factor", pa.float64())])
    suspend_schema = pa.schema([
        pa.field("ts_code", pa.string()), pa.field("trade_date", pa.string()),
        pa.field("suspend_type", pa.string()), pa.field("suspend_timing", pa.string()),
    ])
    st_schema = pa.schema([
        pa.field("ts_code", pa.string()), pa.field("trade_date", pa.string()),
        pa.field("type_name", pa.string()), pa.field("name", pa.string()),
    ])
    limit_schema = pa.schema([
        pa.field("ts_code", pa.string()), pa.field("up_limit", pa.float64()),
        pa.field("down_limit", pa.float64()),
    ])
    for index, day in enumerate(days):
        daily_rows = []
        for symbol_index, symbol in enumerate(SYMBOLS):
            close = 20.0 + index * (symbol_index + 1)
            daily_rows.append({
                "ts_code": symbol,
                "trade_date": day.strftime("%Y%m%d"),
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "amount": 100_000.0,
                "vol": 10_000.0,
            })
        _write_table(formal / f"daily/trade_date={day:%Y%m%d}/part.parquet", daily_rows, daily_schema)
        _write_table(
            formal / f"adj_factor/trade_date={day:%Y%m%d}/part.parquet",
            [{"ts_code": symbol, "adj_factor": 1.0} for symbol in SYMBOLS],
            adj_schema,
        )
        _write_table(
            formal / f"suspend_d/trade_date={day:%Y%m%d}/part.parquet",
            [], suspend_schema,
        )
        _write_table(formal / f"stock_st/trade_date={day:%Y%m%d}/part.parquet", [], st_schema)
        _write_table(
            formal / f"stk_limit/trade_date={day:%Y%m%d}/part.parquet",
            [{"ts_code": symbol, "up_limit": 1000.0, "down_limit": 0.1} for symbol in SYMBOLS],
            limit_schema,
        )

    source_dir = formal / "sw_l1_membership"
    source_partition = source_dir / "SW2021_synthetic.parquet"
    source_rows = [
        {
            "ts_code": symbol,
            "l1_code": "801010.SI" if symbol != "000003.SZ" else "801030.SI",
            "l1_name": "synthetic_a" if symbol != "000003.SZ" else "synthetic_b",
            "in_date": "20240101",
            "out_date": None,
            "is_new": "Y",
        }
        for symbol in SYMBOLS
    ]
    source_schema = pa.schema([
        pa.field("ts_code", pa.string()), pa.field("l1_code", pa.string()),
        pa.field("l1_name", pa.string()), pa.field("in_date", pa.string()),
        pa.field("out_date", pa.string()), pa.field("is_new", pa.string()),
    ])
    _write_table(source_partition, source_rows, source_schema)
    source_manifest_path = source_dir / "manifest.json"
    source_manifest_path.write_text(
        json.dumps({"status": "collected_verified", "partitions": [{"name": source_partition.name}]}),
        encoding="utf-8",
    )
    _sidecar(source_manifest_path)
    inventory_dir = root / "data/pit/v3_b5_source_inventories" / SOURCE_INVENTORY_ID
    inventory_manifest = {
        "artifact_id": SOURCE_INVENTORY_ID,
        "status": "published",
        "authorization_scope": "v3_b5_source_inventory_only",
        "not_authorized_for_b6_oos_gate_promotion_signal": True,
        "source_manifest_path": str(source_manifest_path.relative_to(root)).replace("\\", "/"),
        "source_manifest_sha256": _sha(source_manifest_path),
        "partitions": [{"name": source_partition.name, "sha256": _sha(source_partition)}],
    }
    inventory_path = inventory_dir / "manifest.json"
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    inventory_path.write_text(json.dumps(inventory_manifest), encoding="utf-8")
    _sidecar(inventory_path)
    return root, days[-10], days[-1]


@contextmanager
def _synthetic_envelope():
    with tempfile.TemporaryDirectory(prefix="b6-same-draw-") as directory:
        root, oos_start, oos_end = _build_synthetic_repo(Path(directory))
        from strategy_core.v3_relative_strength_executor import STRATEGY_REVISION_ID

        supplement_id = "supplement_synthetic_same_draw_001"
        supplement_dir = root / "data/pit/v3_execution_semantics_supplements" / supplement_id
        supplement_dir.mkdir(parents=True, exist_ok=True)
        source_path = root / "synthetic_sources/runtime.py"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text("SYNTHETIC_SOURCE = True\n", encoding="utf-8")
        supplement = {
            "schema_version": "v3_execution_semantics_supplement.v2",
            "supplement_id": supplement_id,
            "status": "published",
            "authorization_scope": "v3_manual_trading_execution",
            "not_authorized_for_b6_oos_gate_promotion_signal": False,
            "strategy_revision_id": STRATEGY_REVISION_ID,
            "strategy": {"strategy_revision_id": STRATEGY_REVISION_ID},
            "protocol": {
                "protocol_snapshot_id": "protocol_synthetic_same_draw_001",
            },
            "data_chain": {
                "formal_snapshot": {
                    "semantic_hash": "2" * 64,
                },
            },
            "criteria": {"envelope_hash": "3" * 64},
            "source_bindings": {
                "synthetic_runtime": {
                    "path": "synthetic_sources/runtime.py",
                    "sha256": _sha(source_path),
                },
            },
        }
        supplement_manifest_path = supplement_dir / "manifest.json"
        supplement_manifest_path.write_text(
            json.dumps(supplement, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        _sidecar(supplement_manifest_path)
        manifest_sha = _sha(supplement_manifest_path)
        identity = {
            "task_id": "task_synthetic_same_draw_001",
            "task_key": "a" * 64,
            "strategy_revision_id": supplement["strategy_revision_id"],
            "protocol_snapshot_id": supplement["protocol"]["protocol_snapshot_id"],
            "b5_bundle_id": "bundle_synthetic_same_draw_001",
            "b5_bundle_manifest_sha256": "b" * 64,
            "b4_artifact_id": "b4_synthetic_same_draw_001",
            "b4_manifest_sha256": "c" * 64,
            "b4_event_result_sha256": "d" * 64,
            "formal_snapshot_id": "formal_synthetic_same_draw_001",
            "formal_snapshot_manifest_sha256": "e" * 64,
            "membership_snapshot_id": MEMBERSHIP_ID,
            "membership_manifest_sha256": "f" * 64,
            "calendar_id": "calendar_synthetic_same_draw_001",
            "calendar_manifest_sha256": "1" * 64,
            "data_snapshot_hash": supplement["data_chain"]["formal_snapshot"]["semantic_hash"],
            "execution_input_hash": manifest_sha,
            "shared_oos_window_id": "oos_window_synthetic_same_draw_001",
            "oos_start": oos_start.isoformat(),
            "oos_end": oos_end.isoformat(),
            "result_schema_version": "b6_same_draw_oos_result.v2",
        }
        envelope = {
            "task_id": identity["task_id"],
            "task_key": identity["task_key"],
            "protocol_snapshot_id": identity["protocol_snapshot_id"],
            "strategy_revision_id": identity["strategy_revision_id"],
            "reservation_id": "reservation_synthetic_001",
            "oos_draw_index": 1,
            "identity": identity,
        }
        yield root, envelope


@contextmanager
def _verified_synthetic_supplement():
    from unittest.mock import patch

    from backend.services.b6_same_draw_executor import (
        PreparedSupplementToken,
        _find_verified_supplement,
    )

    with _synthetic_envelope() as (root, envelope):
        supplement_dir = root / "data/pit/v3_execution_semantics_supplements" / "supplement_synthetic_same_draw_001"
        supplement = json.loads((supplement_dir / "manifest.json").read_text(encoding="utf-8"))
        verified = {
            "status": "verified",
            "supplement_id": supplement["supplement_id"],
            "path": str(supplement_dir),
            "manifest_sha256": _sha(supplement_dir / "manifest.json"),
            "strategy_revision_id": supplement["strategy_revision_id"],
            "protocol_snapshot_id": supplement["protocol"]["protocol_snapshot_id"],
            "data_snapshot_hash": supplement["data_chain"]["formal_snapshot"]["semantic_hash"],
        }
        envelope["prepared_supplement"] = PreparedSupplementToken.from_verified(
            supplement_dir,
            verified,
            repo_root=root,
            b5_bundle_id=envelope["identity"]["b5_bundle_id"],
            b5_bundle_manifest_sha256=envelope["identity"]["b5_bundle_manifest_sha256"],
            criteria_envelope_hash=supplement["criteria"]["envelope_hash"],
        )
        with patch(
            "backend.services.b6_same_draw_executor._find_verified_supplement",
            autospec=True,
            return_value=(supplement_dir, supplement),
        ) as loader:
            with patch(
                "scripts.verify_v3_execution_semantics.verify_v3_execution_semantics",
                return_value=verified,
            ):
                yield root, envelope, loader


class TestB6SameDrawExecutor(unittest.TestCase):
    def test_production_callable_is_missing_or_not_bound_to_real_b4(self):
        from backend.services.b6_same_draw_executor import execute_production_same_draw

        self.assertTrue(callable(execute_production_same_draw))

    def test_formal_source_inventory_does_not_require_unpublished_source_sidecar(self):
        from backend.services.b6_same_draw_executor import _load_industry_index

        industry_index = _load_industry_index(Path(__file__).resolve().parents[1])

        self.assertTrue(industry_index)
        self.assertIn("000001.SZ", industry_index)
        self.assertTrue(all(item["l1_code"] for item in industry_index["000001.SZ"]))

    def _execute(self):
        from backend.services.b6_same_draw_executor import execute_production_same_draw

        with _verified_synthetic_supplement() as (root, envelope, loader):
            result = execute_production_same_draw(envelope, repo_root=root)
            self.assertFalse(loader.called)
            self.assertTrue(envelope["prepared_supplement"].consumed)
            return result

    def test_prepared_token_has_exact_contract_and_canonical_identity(self):
        from backend.services.b6_same_draw_executor import _canonical_bytes

        with _verified_synthetic_supplement() as (_root, envelope, _loader):
            token = envelope["prepared_supplement"]
            payload = token.to_dict()
            self.assertEqual(set(payload), {
                "token_schema_version",
                "supplement_id",
                "manifest_sha256",
                "repo_relative_path",
                "protocol_snapshot_id",
                "strategy_revision_id",
                "b5_bundle_id",
                "b5_bundle_manifest_sha256",
                "criteria_envelope_hash",
                "source_bindings",
                "verified_manifest_bytes_sha256",
                "prepared_identity_sha256",
            })
            self.assertEqual(payload["token_schema_version"], "prepared_supplement_token.v1")
            identity_payload = {
                key: value
                for key, value in payload.items()
                if key != "prepared_identity_sha256"
            }
            self.assertEqual(
                payload["prepared_identity_sha256"],
                hashlib.sha256(_canonical_bytes(identity_payload)).hexdigest(),
            )

    def test_real_b6_v3_caller_uses_frozen_verified_supplement_without_discovery_or_verifier_after_start(self):
        from unittest.mock import patch

        from backend.services.b6_same_draw_executor import execute_production_same_draw
        from strategy_core.backtest_engine import run_event_backtest as real_run_event_backtest

        with _verified_synthetic_supplement() as (root, envelope, loader):
            calls = []
            events = []

            def observe_call(*args, **kwargs):
                calls.append((args, kwargs))
                event = real_run_event_backtest(*args, **kwargs)
                events.append(event)
                return event

            with patch(
                "backend.services.b6_same_draw_executor.run_event_backtest",
                side_effect=observe_call,
            ):
                result = execute_production_same_draw(envelope, repo_root=root)
        self.assertFalse(loader.called)
        self.assertTrue(envelope["prepared_supplement"].consumed)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(events), 1)
        self.assertIsNone(calls[0][1].get("supplement_path"))
        frozen = calls[0][1]["verified_supplement"]
        self.assertNotIn("path", frozen)
        self.assertNotIn("repo_relative_path", frozen)
        self.assertEqual(events[0].order_intents, ())
        self.assertEqual(events[0].fills, ())
        self.assertEqual(result.identity.result_schema_version, "b6_same_draw_oos_result.v2")
        result.assert_production_terminal_eligible()
        self.assertEqual(result.base_cost_result.total_cost_bps, 0.0)
        self.assertEqual(result.stress_cost_result.total_cost_bps, 0.0)
        self.assertEqual(result.ending_nav_base, result.ending_nav_stress)
        self.assertEqual(result.strategy_net_return_base, result.strategy_net_return_stress)
        for field in (
            "strategy_net_return_base", "strategy_net_return_stress",
            "benchmark_net_return_base", "benchmark_net_return_stress",
            "same_universe_control_return_base", "same_universe_control_return_stress",
        ):
            self.assertTrue(math.isfinite(getattr(result, field)))
        self.assertEqual(
            result.alpha_vs_benchmark_base,
            result.strategy_net_return_base - result.benchmark_net_return_base,
        )

    def test_real_execute_production_same_draw_prices_filled_event_and_reports_business_costs(self):
        from unittest.mock import patch

        from backend.services.b4_protocol_types import (
            DailyPortfolioSnapshot,
            EventBacktestResult,
            FillRecord,
            OrderIntentRecord,
        )
        from backend.services.b6_same_draw_executor import execute_production_same_draw
        from strategy_core.v3_relative_strength_executor import V3DailyPortfolioObservation

        with _verified_synthetic_supplement() as (root, envelope, loader):
            def filled_backtest(
                spec,
                _data_source,
                _benchmark_source,
                _protocol_snapshot_id,
                _data_snapshot_hash,
                *,
                initial_capital,
                verified_supplement,
                observation_sink,
            ):
                self.assertEqual(initial_capital, 100000.0)
                self.assertNotIn("path", verified_supplement)
                for offset in range((spec.backtest_end - spec.backtest_start).days + 1):
                    observation_sink(
                        V3DailyPortfolioObservation(
                            date=spec.backtest_start + timedelta(days=offset),
                            cash=99000.0,
                            portfolio_value=100000.0,
                            positions=(("000001.SZ", 100, 10.0),),
                        )
                    )
                return EventBacktestResult(
                    result_id="event_synthetic_filled_001",
                    strategy_revision_id=spec.strategy_revision_id,
                    protocol_snapshot_id=spec.protocol_snapshot_id,
                    evaluation_mode="formal_backtest",
                    backtest_start=spec.backtest_start,
                    backtest_end=spec.backtest_end,
                    order_intents=(OrderIntentRecord(
                        order_id="order_synthetic_filled_001",
                        symbol="000001.SZ",
                        signal_date=spec.backtest_start,
                        intent="buy",
                        quantity=100,
                    ),),
                    fills=(FillRecord(
                        fill_id="fill_synthetic_filled_001",
                        order_id="order_synthetic_filled_001",
                        symbol="000001.SZ",
                        fill_date=spec.backtest_start,
                        fill_price=10.0,
                        fill_quantity=100,
                        execution_mode="simulated",
                    ),),
                    rejected_orders=(),
                    future_violations=(),
                    final_portfolio=DailyPortfolioSnapshot(
                        snapshot_id="snapshot_synthetic_filled_001",
                        snapshot_date=spec.backtest_end,
                        cash=99000.0,
                        positions=(("000001.SZ", 100),),
                        portfolio_value=100000.0,
                    ),
                    frozen_at=spec.backtest_end,
                )

            with patch(
                "backend.services.b6_same_draw_executor.run_event_backtest",
                side_effect=filled_backtest,
            ):
                result = execute_production_same_draw(envelope, repo_root=root)

        self.assertFalse(loader.called)
        self.assertTrue(envelope["prepared_supplement"].consumed)
        self.assertAlmostEqual(result.base_cost_result.commission_bps, 50.0)
        self.assertAlmostEqual(result.base_cost_result.total_cost_bps, 50.0)
        self.assertAlmostEqual(result.stress_cost_result.commission_bps, 50.0)
        self.assertAlmostEqual(result.stress_cost_result.slippage_bps, 10.0)
        self.assertAlmostEqual(result.stress_cost_result.total_cost_bps, 60.0)
        self.assertAlmostEqual(result.ending_nav_base, 100000.0)
        self.assertAlmostEqual(result.ending_nav_stress, 99999.0)
        self.assertAlmostEqual(result.strategy_net_return_base, 0.0)
        self.assertAlmostEqual(result.strategy_net_return_stress, -0.00001)

    def test_prepared_token_rejects_b5_criteria_and_prepared_identity_mismatch(self):
        from backend.services.b6_same_draw_executor import PreparedSupplementToken

        with _verified_synthetic_supplement() as (root, envelope, _loader):
            token = envelope["prepared_supplement"]
            bad_identity = dict(envelope["identity"])
            bad_identity["b5_bundle_id"] = "different_bundle"
            with self.assertRaisesRegex(ValueError, "B5"):
                token.consume(bad_identity)

            supplement_dir = root / "data/pit/v3_execution_semantics_supplements/supplement_synthetic_same_draw_001"
            verified = token.verified_representation
            with self.assertRaisesRegex(ValueError, "criteria"):
                PreparedSupplementToken.from_verified(
                    supplement_dir,
                    verified,
                    repo_root=root,
                    b5_bundle_id=envelope["identity"]["b5_bundle_id"],
                    b5_bundle_manifest_sha256=envelope["identity"]["b5_bundle_manifest_sha256"],
                    criteria_envelope_hash="9" * 64,
                )

            object.__setattr__(token, "_prepared_identity_sha256", "0" * 64)
            with self.assertRaisesRegex(ValueError, "prepared identity"):
                token.assert_current()

    def test_strategy_stress_does_not_double_charge_base_cost(self):
        from backend.services.b4_protocol_types import EventBacktestResult, FillRecord, OrderIntentRecord, DailyPortfolioSnapshot
        from backend.services.b6_same_draw_executor import _strategy_costs

        event = EventBacktestResult(
            result_id="event_synthetic_cost_001",
            strategy_revision_id="revision_synthetic_cost_001",
            protocol_snapshot_id="protocol_synthetic_cost_001",
            evaluation_mode="formal_backtest",
            backtest_start=date(2025, 1, 1),
            backtest_end=date(2025, 1, 2),
            order_intents=(OrderIntentRecord(
                order_id="order_synthetic_cost_001", symbol="000001.SZ",
                signal_date=date(2025, 1, 1), intent="buy", quantity=100,
            ),),
            fills=(FillRecord(
                fill_id="fill_synthetic_cost_001", order_id="order_synthetic_cost_001",
                symbol="000001.SZ", fill_date=date(2025, 1, 2), fill_price=10.0,
                fill_quantity=100, execution_mode="simulated",
            ),),
            rejected_orders=(), future_violations=(),
            final_portfolio=DailyPortfolioSnapshot(
                snapshot_id="snapshot_synthetic_cost_001", snapshot_date=date(2025, 1, 2),
                cash=99_000.0, positions=(("000001.SZ", 100),), portfolio_value=100_000.0,
            ),
            frozen_at=date(2025, 1, 3),
        )
        base, stress, _ = _strategy_costs(event)
        base_nav = 100_000.0
        stress_nav = base_nav - (stress["total"] - base["total"])
        expected_base_total = max(100 * 10.0 * 0.0003, 5.0)
        stress_price = 10.0 * 1.001
        expected_stress_total = max(100 * stress_price * 0.0006, 5.0) + abs(stress_price - 10.0) * 100
        self.assertAlmostEqual(base["total"], expected_base_total)
        self.assertAlmostEqual(stress["total"], expected_stress_total)
        self.assertGreater(stress["total"], base["total"])
        self.assertAlmostEqual(stress_nav, base_nav - (stress["total"] - base["total"]))
        self.assertNotAlmostEqual(stress_nav, base_nav - stress["total"])

    def test_strategy_costs_rejects_duplicate_or_malformed_ledger(self):
        from backend.services.b4_protocol_types import DailyPortfolioSnapshot, EventBacktestResult, FillRecord, OrderIntentRecord
        from backend.services.b6_same_draw_executor import _strategy_costs

        intent = OrderIntentRecord(
            order_id="order_synthetic_invalid_001", symbol="000001.SZ",
            signal_date=date(2025, 1, 1), intent="buy", quantity=100,
        )
        duplicate_fill = FillRecord(
            fill_id="fill_synthetic_invalid_001", order_id=intent.order_id,
            symbol=intent.symbol, fill_date=date(2025, 1, 2), fill_price=10.0,
            fill_quantity=100, execution_mode="simulated",
        )
        duplicate_event = EventBacktestResult(
            result_id="event_synthetic_invalid_duplicate",
            strategy_revision_id="revision_synthetic_invalid",
            protocol_snapshot_id="protocol_synthetic_invalid",
            evaluation_mode="formal_backtest",
            backtest_start=date(2025, 1, 1), backtest_end=date(2025, 1, 2),
            order_intents=(intent,), fills=(duplicate_fill, duplicate_fill),
            rejected_orders=(), future_violations=(),
            final_portfolio=DailyPortfolioSnapshot(
                snapshot_id="snapshot_synthetic_invalid_duplicate", snapshot_date=date(2025, 1, 2),
                cash=100_000.0, positions=(), portfolio_value=100_000.0,
            ),
            frozen_at=date(2025, 1, 3),
        )
        with self.assertRaises(ValueError):
            _strategy_costs(duplicate_event)

        malformed_fill = duplicate_fill.model_copy(update={"order_id": "missing-order"})
        malformed_event = duplicate_event.model_copy(
            update={
                "result_id": "event_synthetic_invalid_reference",
                "fills": (malformed_fill,),
            }
        )
        with self.assertRaises(ValueError):
            _strategy_costs(malformed_event)

    def test_shared_read_audit_and_independent_portfolios(self):
        result = self._execute()

        self.assertEqual(result.read_audit.owner, "b6_same_draw_executor")
        self.assertEqual(result.read_audit.future_violation_count, 0)
        self.assertLessEqual(result.read_audit.max_requested_date, result.identity.oos_end)
        self.assertGreater(result.read_audit.read_count, 0)
        self.assertGreaterEqual(len(result.read_audit.operation_counts), 1)
        self.assertNotEqual(
            result.benchmark_net_return_base,
            result.same_universe_control_return_base,
        )

    def test_future_identity_cost_and_missing_series_fail_loud(self):
        from backend.services.b6_same_draw_executor import execute_production_same_draw
        from unittest.mock import patch

        with _synthetic_envelope() as (root, envelope):
            bad_identity = dict(envelope["identity"])
            bad_identity["execution_input_hash"] = "f" * 64
            bad_envelope = {**envelope, "identity": bad_identity}
            with patch("backend.services.b6_same_draw_executor.run_event_backtest") as engine:
                with self.assertRaises((FileNotFoundError, ValueError)):
                    execute_production_same_draw(bad_envelope, repo_root=root)
                engine.assert_not_called()

        with _synthetic_envelope() as (root, envelope):
            bad_identity = dict(envelope["identity"])
            bad_identity["oos_end"] = (date.fromisoformat(bad_identity["oos_end"]) + timedelta(days=1)).isoformat()
            bad_envelope = {**envelope, "identity": bad_identity}
            with self.assertRaises(ValueError):
                execute_production_same_draw(bad_envelope, repo_root=root)

        with _synthetic_envelope() as (root, envelope):
            end = date.fromisoformat(envelope["identity"]["oos_end"])
            daily_path = root / FORMAL_REL / f"daily/trade_date={end:%Y%m%d}/part.parquet"
            daily_path.unlink()
            with patch("backend.services.b6_same_draw_executor.run_event_backtest") as engine:
                with self.assertRaises((FileNotFoundError, ValueError, KeyError)):
                    execute_production_same_draw(envelope, repo_root=root)
                engine.assert_not_called()

    def test_unpatched_tampered_supplement_fails_before_engine(self):
        from backend.services.b6_same_draw_executor import execute_production_same_draw
        from unittest.mock import patch

        with _synthetic_envelope() as (root, envelope):
            manifest_path = root / (
                "data/pit/v3_execution_semantics_supplements/"
                "supplement_synthetic_same_draw_001/manifest.json"
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["protocol_snapshot_id"] = "tampered_protocol"
            manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8")
            with patch("backend.services.b6_same_draw_executor.run_event_backtest") as engine:
                with self.assertRaises(ValueError):
                    execute_production_same_draw(envelope, repo_root=root)
                engine.assert_not_called()


if __name__ == "__main__":
    unittest.main()
