from __future__ import annotations

import math
import inspect
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import backend.services.v3_b5_comparison as comparison
from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
from backend.services.v3_b5_comparison import (
    ComparisonError,
    IS_START,
    OOS_START,
    _FormalComparisonSource,
    ReadBoundAdapter,
    build_weekly_schedule,
    calculate_metrics,
    control_weights,
    industry_weights,
    rebalance_fractional,
    run_fractional_index,
    validate_daily_rows,
)
import scripts.publish_v3_b5_comparisons as publisher
from scripts.publish_v3_b5_comparisons import (
    DEFAULT_LIFECYCLE_MANIFEST,
    LIFECYCLE_ID,
    _load_coverage_binding,
    _load_industry_index,
    _load_lifecycle,
    _load_observation_binding,
)

ROOT = Path(__file__).resolve().parents[1]


class _EligibilityStatus:
    is_st = False
    is_suspended = False


class _LifecycleFilteredAdapter:
    def symbols_as_of(self, _day):
        return ("A.SH", "MISSING.SZ")

    def is_eligible(self, symbol, _day):
        if symbol == "MISSING.SZ":
            raise KeyError(symbol)
        return True

    def get_status(self, _symbol, _day):
        return _EligibilityStatus()

    def derive_liquidity(self, _symbol, _day):
        return {"status": "qualified"}


class _P2Bar:
    def __init__(self, open_price: float, close_price: float, open_sink=None, symbol=None, day=None):
        self._open = open_price
        self.close = close_price
        self._open_sink = open_sink
        self._symbol = symbol
        self._day = day

    @property
    def open(self):
        if self._open_sink is not None:
            self._open_sink.append((self._symbol, self._day))
        return self._open


class _P2Adapter:
    def __init__(self, missing_days=(), suspended_days=(), conflict_days=()):
        self.missing_days = set(missing_days)
        self.suspended_days = set(suspended_days)
        self.conflict_days = set(conflict_days)
        self.open_calls = []
        self.bar_calls = []
        self.status_calls = []

    def symbols_as_of(self, day):
        return ("A.SH", "B.SH") if day >= date(2025, 11, 28) else ("A.SH",)

    def is_eligible(self, _symbol, _day):
        return True

    def derive_liquidity(self, _symbol, _day):
        return {"status": "qualified"}

    def get_status(self, symbol, day):
        self.status_calls.append((symbol, day))
        if (symbol, day) in self.suspended_days:
            return SimpleNamespace(is_st=False, is_suspended=True, is_limit_up=False, is_limit_down=False)
        if (symbol, day) in self.missing_days:
            raise KeyError(f"missing daily: {symbol}/{day}")
        return SimpleNamespace(is_st=False, is_suspended=False, is_limit_up=False, is_limit_down=False)

    def get_bar(self, symbol, day):
        self.bar_calls.append((symbol, day))
        if (symbol, day) in self.missing_days:
            raise KeyError(f"missing daily: {symbol}/{day}")
        if (symbol, day) in self.conflict_days:
            return _P2Bar(10.0, 11.0, self.open_calls, symbol, day)
        close = 10.0 if day < date(2025, 12, 9) else 12.0
        return _P2Bar(10.0, close, self.open_calls, symbol, day)


class _RecordingReadBoundAdapter(ReadBoundAdapter):
    """Transparent production adapter observer used only by the real-slice test."""

    def __init__(self, raw, allowed_end):
        super().__init__(raw, allowed_end)
        self._bar_count = 0

    def _observe(self, operation, symbol=None, day=None):
        if operation == "bar":
            self._bar_count += 1

    def symbols_as_of(self, day):
        self._observe("membership", day=day)
        return super().symbols_as_of(day)

    def common_trading_dates(self, start, end):
        self._observe("calendar", day=end)
        return super().common_trading_dates(start, end)

    def is_eligible(self, symbol, day):
        self._observe("lifecycle", symbol, day)
        return super().is_eligible(symbol, day)

    def derive_liquidity(self, symbol, day):
        self._observe("liquidity", symbol, day)
        return super().derive_liquidity(symbol, day)

    def get_status(self, symbol, day):
        self._observe("status", symbol, day)
        return super().get_status(symbol, day)

    def get_bar(self, symbol, day):
        self._observe("bar", symbol, day)
        return super().get_bar(symbol, day)

    def bar_count(self):
        return self._bar_count


class _ExplodingCalls:
    def __iter__(self):
        raise AssertionError("bar_count scanned retained call history")


class _ObservedComparisonSource(_FormalComparisonSource):
    """Transparent caller observer; production execution/mark remains authoritative."""

    def __init__(self, adapter, industry_index, *, lifecycle, coverage_unavailable):
        super().__init__(adapter, industry_index, lifecycle=lifecycle, coverage_unavailable=coverage_unavailable)
        self.execution_observations = []
        self.mark_observations = []

    def execution(self, symbol, day, *, held=False):
        before = self.adapter.bar_count()
        try:
            result = super().execution(symbol, day, held=held)
        except Exception as exc:
            self.execution_observations.append({"symbol": symbol, "day": day, "bar_delta": self.adapter.bar_count() - before, "exception": type(exc).__name__})
            raise
        self.execution_observations.append({"symbol": symbol, "day": day, "bar_delta": self.adapter.bar_count() - before, "result": result})
        return result

    def mark(self, symbol, day):
        before = self.adapter.bar_count()
        try:
            result = super().mark(symbol, day)
        except Exception as exc:
            self.mark_observations.append({"symbol": symbol, "day": day, "bar_delta": self.adapter.bar_count() - before, "exception": type(exc).__name__})
            raise
        self.mark_observations.append({"symbol": symbol, "day": day, "bar_delta": self.adapter.bar_count() - before, "result": result})
        return result


def _p2_row(day: str, as_of: str, symbol: str = "A.SH", **overrides):
    row = {
        "execution_date": day,
        "as_of_date": as_of,
        "symbol": symbol,
        "status": "unavailable",
        "reason": "required_history_missing",
        "missing_fields": ["daily.close"],
    }
    row.update(overrides)
    return row


def _p2_source(*, rows=None, adapter=None, lifecycle=None):
    adapter = adapter or _P2Adapter(missing_days={("A.SH", date(2025, 11, 27))})
    return _FormalComparisonSource(
        adapter,
        {
            "A.SH": [{"l1_code": "I1", "l1_name": "one", "in_date": date(2016, 1, 1), "out_date": None}],
            "B.SH": [{"l1_code": "I2", "l1_name": "two", "in_date": date(2016, 1, 1), "out_date": None}],
        },
        lifecycle=lifecycle or {"A.SH": ("20160101", None), "B.SH": ("20160101", None)},
        coverage_unavailable=rows or {},
    )


class TestV3B5Comparisons(unittest.TestCase):
    def test_comparison_verifier_exposes_keyword_only_temp_bindings(self):
        from scripts.verify_v3_b5_comparisons import verify_artifact

        parameters = inspect.signature(verify_artifact).parameters
        self.assertEqual(parameters["cost_dir"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(parameters["observation_dir"].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_comparison_source_uses_verified_stock_basic_root(self):
        raw = FormalPITPartitionAdapter(ROOT)
        lifecycle_roots = []

        def capture_lifecycle_root(stock_basic_root, _manifest_path):
            lifecycle_roots.append(Path(stock_basic_root))
            return {}, {"stock_basic_root": Path(stock_basic_root).as_posix()}

        self.assertTrue((raw.stock_basic_root / "list_status=L/part.parquet").is_file())
        self.assertFalse((raw.formal_root / "stock_basic/list_status=L/part.parquet").exists())
        with (
            mock.patch.object(publisher, "FormalPITPartitionAdapter", return_value=raw),
            mock.patch.object(publisher, "_load_lifecycle", side_effect=capture_lifecycle_root),
            mock.patch.object(publisher, "_load_coverage_binding", return_value=({}, {})),
            mock.patch.object(publisher, "_load_industry_index", return_value={}),
        ):
            publisher._load_source(ROOT)

        self.assertEqual(lifecycle_roots, [raw.stock_basic_root])

    def test_v3_b5_comparisons_rebinds_new_b4_and_criteria_lineage(self):
        from backend.services.v3_b5_bundle import build_lineage

        lineage = build_lineage(ROOT)
        self.assertEqual(lineage["b4"], {
            "artifact_id": "cfa75e8b2a72bc76",
            "manifest_sha256": "b7db7cd296987ebd85ad199df16841a3a5d8a105892350e5a0bd091e4b5b6f89",
            "event_sha256": "8a8b5955ea6620c97e93914cdfdecd7006967bad0a297affb87a09af064d9a74",
        })
        self.assertEqual(lineage["execution_supplement"], {
            "id": "185a6b8f03915dca",
            "manifest_sha256": "df51e7a9efae3b6e915d8cac8210b431e07f3992fe83fb183e499e512bc9c895",
        })
        self.assertEqual(
            lineage["protocol_snapshot_id"],
            "8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe",
        )
        self.assertEqual(lineage["gate_criteria_envelope_hash"], "94da0dda30af75d663a7d28deb0a15d64a4e068586a1295f3b4f52203a8c4738")
        self.assertEqual(comparison.BASE_COST_ID, "e405b900f971877f")
        self.assertEqual(comparison.BASE_COST_MANIFEST_SHA, "23159b522d9f2519d05d185031e2a26c2b47cd0b3f22bf983d0d6a89b12396db")
        self.assertEqual(comparison.OBSERVATION_ID, "984864448e8aa4cd")
        self.assertEqual(comparison.OBSERVATION_MANIFEST_SHA, "5c2679300bd9188bc8fbb3cca943805d2161cbacafce1e1a0f6b41b85658e66a")

    def test_successor_comparisons_publish_and_verify_in_temporary_root(self):
        from backend.services.v3_b5_bundle import build_lineage
        from scripts.verify_v3_b5_comparisons import verify_artifact

        cost_dir = ROOT / "data/pit/v3_b5_costs" / "e405b900f971877f"
        observation_dir = ROOT / "data/pit/v3_b5_ledger_observations" / "984864448e8aa4cd"
        with tempfile.TemporaryDirectory() as tmp:
            published = publisher.publish(
                ROOT,
                Path(tmp),
                cost_dir=cost_dir,
                observation_dir=observation_dir,
            )
            self.assertEqual(published["status"], "published")
            artifact = Path(published["path"])
            verified = verify_artifact(
                artifact,
                ROOT,
                cost_dir=cost_dir,
                observation_dir=observation_dir,
            )
            self.assertEqual(verified["status"], "verified")

            manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
            lineage = manifest["lineage"]
            expected = build_lineage(ROOT)
            for key in (
                "b4",
                "execution_supplement",
                "formal_snapshot",
                "gate_criteria_envelope_hash",
                "is_range",
                "protocol_snapshot_id",
                "scope",
                "source_inventory",
                "strategy_revision_id",
            ):
                self.assertEqual(lineage[key], expected[key], key)
            self.assertEqual(lineage["cost_artifact"], {
                "artifact_id": "e405b900f971877f",
                "manifest_sha256": "23159b522d9f2519d05d185031e2a26c2b47cd0b3f22bf983d0d6a89b12396db",
                "cost_assumptions_hash": "69af3a2acdbb5b5c0ed59db5fdc6a4bc3108b19d8f814f0b85363d342522a386",
            })
            self.assertEqual(lineage["ledger_observation"], {
                "artifact_id": "984864448e8aa4cd",
                "manifest_sha256": "5c2679300bd9188bc8fbb3cca943805d2161cbacafce1e1a0f6b41b85658e66a",
                "observations_sha256": "55373c7e7c189663241f48d37b35505f99284d20c7eb07d85b7dec8a0208f842",
            })
            self.assertEqual(manifest["schema_kind"], "theoretical_fractional_comparison_index")
            self.assertTrue(manifest["non_executable"])
            self.assertTrue(manifest["not_authorized_for_b6_oos_gate_promotion_signal"])
            self.assertEqual(manifest["weekly_schedule_count"], 38)

            expected_metrics = {
                "benchmark": {
                    "strategy_cumulative_return": 0.04162010346149536,
                    "comparator_cumulative_return": 0.16638062359212125,
                    "relative_return": -0.12476052013062588,
                    "beta": 0.581813292474396,
                    "correlation": 0.29069318076256223,
                    "stress_cumulative_return": 0.07276060931259298,
                    "gross_cumulative_return": 0.22508921431990414,
                },
                "control": {
                    "strategy_cumulative_return": 0.04162010346149536,
                    "comparator_cumulative_return": 0.20707315091865452,
                    "relative_return": -0.16545304745715916,
                    "beta": 0.6059255722006033,
                    "correlation": 0.34158075137158816,
                    "stress_cumulative_return": 0.11349306328383846,
                    "gross_cumulative_return": 0.26575662930475286,
                },
            }
            for name, filename in (
                ("benchmark", "benchmark_comparison.json"),
                ("control", "same_universe_control.json"),
            ):
                payload = json.loads((artifact / filename).read_text(encoding="utf-8"))
                result = payload["result"]
                self.assertEqual(result["comparison_kind"], "benchmark" if name == "benchmark" else "control")
                self.assertEqual(result["schema_kind"], "theoretical_fractional_comparison_index")
                self.assertEqual(result["initial_nav"], 1.0)
                self.assertEqual(result["is_range"], {
                    "start": "2025-06-27",
                    "end": "2026-03-19",
                    "count": 176,
                    "oos_start": "2026-03-20",
                })
                self.assertEqual(len(result["daily_rows"]), 176)
                self.assertEqual(len(result["rebalances"]), 38)
                self.assertTrue(all(date.fromisoformat(row["date"]) < OOS_START for row in result["daily_rows"]))
                self.assertEqual(result["cost"]["artifact_id"], "e405b900f971877f")
                self.assertEqual(result["cost"]["artifact_manifest_sha256"], "23159b522d9f2519d05d185031e2a26c2b47cd0b3f22bf983d0d6a89b12396db")
                self.assertEqual(result["strategy_observation"]["artifact_id"], "984864448e8aa4cd")
                for metric, expected_value in expected_metrics[name].items():
                    self.assertAlmostEqual(result["metrics"][metric], expected_value, places=14, msg=f"{name}.{metric}")

            before = {
                name: (artifact / name).read_bytes()
                for name in (
                    "manifest.json",
                    "manifest.json.sha256",
                    "benchmark_comparison.json",
                    "benchmark_comparison.json.sha256",
                    "same_universe_control.json",
                    "same_universe_control.json.sha256",
                )
            }
            before_mtime = artifact.stat().st_mtime_ns
            replayed = publisher._write_once(
                artifact,
                {name: raw for name, raw in before.items() if not name.endswith(".sha256")},
            )
            self.assertEqual(replayed, "already_published")
            self.assertEqual({name: (artifact / name).read_bytes() for name in before}, before)
            self.assertEqual(artifact.stat().st_mtime_ns, before_mtime)

            (artifact / "benchmark_comparison.json").write_bytes(b"tampered")
            with self.assertRaises(ComparisonError):
                publisher._write_once(
                    artifact,
                    {name: raw for name, raw in before.items() if not name.endswith(".sha256")},
                )

            (artifact / "benchmark_comparison.json").write_bytes(before["benchmark_comparison.json"])
            (artifact / "extra.txt").write_text("unexpected", encoding="utf-8")
            with self.assertRaises(ComparisonError):
                publisher._write_once(
                    artifact,
                    {name: raw for name, raw in before.items() if not name.endswith(".sha256")},
                )
            with self.assertRaises(ComparisonError):
                verify_artifact(
                    artifact,
                    ROOT,
                    cost_dir=cost_dir,
                    observation_dir=observation_dir,
                )

    def test_publisher_failure_preserves_sibling_staging_without_final_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            target = output_root / "comparison-artifact"
            files = {
                "manifest.json": b"{}",
                "benchmark_comparison.json": b"{}",
                "same_universe_control.json": b"{}",
            }
            real_replace = publisher.os.replace

            def fail_final_rename(source, destination):
                if Path(destination) == target:
                    raise OSError("injected final directory rename failure")
                return real_replace(source, destination)

            with mock.patch.object(publisher.os, "replace", side_effect=fail_final_rename):
                with self.assertRaises(OSError):
                    publisher._write_once(target, files)

            self.assertFalse(target.exists())
            staging = tuple(output_root.glob("comparison-artifact.staging.*"))
            self.assertEqual(len(staging), 1)
            self.assertEqual(
                {path.name for path in staging[0].iterdir()},
                {
                    "manifest.json",
                    "manifest.json.sha256",
                    "benchmark_comparison.json",
                    "benchmark_comparison.json.sha256",
                    "same_universe_control.json",
                    "same_universe_control.json.sha256",
                },
            )

    def test_publisher_lineage_constants_match_comparison_service(self):
        self.assertEqual(
            (publisher.INITIAL_NAV, publisher.BASE_COST_BPS, publisher.STRESS_COST_BPS),
            (comparison.INITIAL_NAV, comparison.BASE_COST_BPS, comparison.STRESS_COST_BPS),
        )

    def test_real_slice_observer_bar_count_does_not_scan_call_history(self):
        adapter = _RecordingReadBoundAdapter(_P2Adapter(), date(2025, 12, 9))
        adapter._observe("liquidity", "A.SH", date(2025, 12, 1))
        adapter._observe("bar", "A.SH", date(2025, 12, 1))
        adapter.calls = _ExplodingCalls()

        self.assertEqual(adapter.bar_count(), 1)

    def test_weekly_schedule_is_first_common_day_and_previous_as_of(self):
        dates = [date(2025, 6, 26), date(2025, 6, 27), date(2025, 6, 30), date(2025, 7, 1), date(2025, 7, 4), date(2025, 7, 7)]
        schedule = build_weekly_schedule(dates, date(2025, 6, 27), date(2025, 7, 7))
        self.assertEqual(
            schedule,
            [
                {"formation_date": "2025-06-27", "as_of_date": "2025-06-26", "execution_date": "2025-06-27"},
                {"formation_date": "2025-06-30", "as_of_date": "2025-06-27", "execution_date": "2025-06-30"},
                {"formation_date": "2025-07-07", "as_of_date": "2025-07-04", "execution_date": "2025-07-07"},
            ],
        )

    def test_fractional_index_reports_completed_rebalances_without_changing_result(self):
        dates = (
            date(2025, 11, 26), date(2025, 11, 27),
            date(2025, 12, 1), date(2025, 12, 9),
        )
        schedule = [
            {"formation_date": "2025-11-26", "as_of_date": "2025-11-25", "execution_date": "2025-11-26"},
            {"formation_date": "2025-12-01", "as_of_date": "2025-11-28", "execution_date": "2025-12-01"},
        ]
        observations = [
            {"date": day.isoformat(), "portfolio_value": value,
             "daily_return": 0.0 if index == 0 else value / (value - 0.01) - 1.0}
            for index, (day, value) in enumerate(zip(dates, (1.0, 1.01, 1.02, 1.04)))
        ]
        coverage_rows = {
            ("20251127", "A.SH"): _p2_row("20251127", "20251126"),
        }
        baseline = run_fractional_index(
            kind="control", source=_p2_source(rows=coverage_rows), dates=dates,
            schedule=schedule, strategy_observations=observations,
        )
        events = []
        observed = run_fractional_index(
            kind="control", source=_p2_source(rows=coverage_rows), dates=dates,
            schedule=schedule, strategy_observations=observations,
            progress=events.append,
        )

        self.assertEqual(observed, baseline)
        self.assertEqual(
            [
                {key: event[key] for key in (
                    "kind", "phase", "completed_rebalances",
                    "total_rebalances", "execution_date",
                )}
                for event in events
            ],
            [
                {"kind": "control", "phase": "rebalance_completed",
                 "completed_rebalances": 1, "total_rebalances": 2,
                 "execution_date": "2025-11-26"},
                {"kind": "control", "phase": "rebalance_completed",
                 "completed_rebalances": 2, "total_rebalances": 2,
                 "execution_date": "2025-12-01"},
            ],
        )
        self.assertTrue(all(event["elapsed_seconds"] >= 0 for event in events))

    def test_benchmark_industry_and_control_weights_are_exact(self):
        members = [
            {"symbol": "A.SH", "l1_code": "I1", "l1_name": "one"},
            {"symbol": "B.SH", "l1_code": "I1", "l1_name": "one"},
            {"symbol": "C.SZ", "l1_code": "I2", "l1_name": "two"},
        ]
        benchmark = industry_weights(members)
        control = control_weights(members)
        self.assertEqual(benchmark, {"A.SH": 0.25, "B.SH": 0.25, "C.SZ": 0.5})
        self.assertEqual(control, {"A.SH": 1 / 3, "B.SH": 1 / 3, "C.SZ": 1 / 3})
        self.assertAlmostEqual(sum(benchmark.values()), 1.0)
        self.assertAlmostEqual(sum(control.values()), 1.0)

    def test_missing_or_ambiguous_industry_is_fail_loud(self):
        with self.assertRaises(ComparisonError):
            industry_weights([{"symbol": "A.SH", "l1_code": None, "l1_name": "one"}])
        with self.assertRaises(ComparisonError):
            industry_weights(
                [
                    {"symbol": "A.SH", "l1_code": "I1", "l1_name": "one"},
                    {"symbol": "A.SH", "l1_code": "I2", "l1_name": "two"},
                ]
            )

    def test_fractional_blocked_entry_keeps_cash_and_blocked_exit_carries(self):
        positions = {"A.SH": 1.0}
        prices = {"A.SH": 10.0, "B.SH": 20.0}
        result = rebalance_fractional(
            positions=positions,
            cash=0.0,
            target_weights={"B.SH": 1.0},
            execution_prices=prices,
            tradable={"A.SH": False, "B.SH": False},
            nav=10.0,
        )
        self.assertEqual(result.positions, {"A.SH": 1.0})
        self.assertEqual(result.cash, 0.0)
        self.assertEqual(result.blocked_entries, 1)
        self.assertEqual(result.blocked_exits, 1)

    def test_turnover_does_not_double_count_cash_and_costs_use_approved_bps(self):
        result = rebalance_fractional(
            positions={},
            cash=1.0,
            target_weights={"A.SH": 0.6, "B.SH": 0.4},
            execution_prices={"A.SH": 10.0, "B.SH": 20.0},
            tradable={"A.SH": True, "B.SH": True},
            nav=1.0,
        )
        self.assertAlmostEqual(result.turnover, 1.0)
        self.assertAlmostEqual(result.base_cost, 1.0 * 8.0431006062 / 10000)
        self.assertAlmostEqual(result.stress_cost, 1.0 * 20.8425059905 / 10000)
        self.assertGreater(result.stress_cost, result.base_cost)
        self.assertAlmostEqual(result.cash, 0.0)
        self.assertAlmostEqual(result.positions["A.SH"] * 10.0 + result.positions["B.SH"] * 20.0, 1.0)

    def test_locked_position_uses_uniform_cash_cap_and_preserves_gross_nav(self):
        result = rebalance_fractional(
            positions={"LOCK.SH": 5.0},
            cash=50.0,
            target_weights={"B.SH": 0.6, "C.SH": 0.4},
            execution_prices={"LOCK.SH": 10.0, "B.SH": 10.0, "C.SH": 20.0},
            tradable={"LOCK.SH": False, "B.SH": True, "C.SH": True},
            nav=100.0,
        )
        self.assertEqual(result.positions["LOCK.SH"], 5.0)
        self.assertAlmostEqual(result.positions["B.SH"] * 10.0, 30.0)
        self.assertAlmostEqual(result.positions["C.SH"] * 20.0, 20.0)
        self.assertAlmostEqual(result.cash, 0.0)
        self.assertAlmostEqual(result.cash + sum(result.positions[s] * p for s, p in {"LOCK.SH": 10.0, "B.SH": 10.0, "C.SH": 20.0}.items()), 100.0)
        self.assertAlmostEqual(result.turnover, 0.5)
        self.assertAlmostEqual(result.base_cost, 0.5 * 8.0431006062 / 10000)
        self.assertAlmostEqual(result.stress_cost, 0.5 * 20.8425059905 / 10000)

    def test_blocked_new_target_keeps_cash_without_renormalizing(self):
        result = rebalance_fractional(
            positions={},
            cash=100.0,
            target_weights={"BLOCKED.SH": 0.6, "BUY.SH": 0.4},
            execution_prices={"BUY.SH": 10.0},
            tradable={"BLOCKED.SH": False, "BUY.SH": True},
            nav=100.0,
        )
        self.assertEqual(result.blocked_entries, 1)
        self.assertNotIn("BLOCKED.SH", result.positions)
        self.assertAlmostEqual(result.positions["BUY.SH"] * 10.0, 40.0)
        self.assertAlmostEqual(result.cash, 60.0)
        self.assertAlmostEqual(result.cash + result.positions["BUY.SH"] * 10.0, 100.0)
        self.assertAlmostEqual(result.turnover, 0.4)

    def test_pretrade_nav_mismatch_or_material_negative_cash_fails_loud(self):
        with self.assertRaises(ComparisonError):
            rebalance_fractional(
                positions={"A.SH": 1.0},
                cash=90.0,
                target_weights={"B.SH": 1.0},
                execution_prices={"A.SH": 10.0, "B.SH": 10.0},
                tradable={"A.SH": True, "B.SH": True},
                nav=101.0,
            )
        with self.assertRaises(ComparisonError):
            rebalance_fractional(
                positions={},
                cash=-0.01,
                target_weights={"B.SH": 1.0},
                execution_prices={"B.SH": 10.0},
                tradable={"B.SH": True},
                nav=1.0,
            )

    def test_daily_rows_and_metrics_are_deterministic(self):
        rows = [
            {"date": "2025-06-27", "gross_nav": 1.0, "base_net_nav": 1.0, "stress_net_nav": 1.0, "daily_return": 0.0},
            {"date": "2025-06-30", "gross_nav": 1.1, "base_net_nav": 1.09, "stress_net_nav": 1.08, "daily_return": 0.09},
        ]
        validate_daily_rows(rows, [date(2025, 6, 27), date(2025, 6, 30)])
        metrics = calculate_metrics([0.0, 0.1], [0.0, 0.05], [1.0, 1.09], [1.0, 1.05])
        self.assertAlmostEqual(metrics["comparator_cumulative_return"], 0.05)
        self.assertIn("beta", metrics)
        self.assertIn("correlation", metrics)

    def test_lifecycle_filters_membership_symbols_before_formal_adapter_lookup(self):
        source = _FormalComparisonSource(
            _LifecycleFilteredAdapter(),
            {
                "A.SH": [{"l1_code": "I1", "l1_name": "one", "in_date": date(2016, 1, 1), "out_date": None}],
                "MISSING.SZ": [{"l1_code": "I1", "l1_name": "one", "in_date": date(2016, 1, 1), "out_date": None}],
            },
            lifecycle={"A.SH": ("20160101", None)},
        )
        members = source.members_for(date(2025, 6, 26), date(2025, 6, 27))
        self.assertEqual([row["symbol"] for row in members], ["A.SH"])

    def test_verified_coverage_unavailable_filters_before_formal_status_lookup(self):
        source = _FormalComparisonSource(
            _LifecycleFilteredAdapter(),
            {
                "A.SH": [{"l1_code": "I1", "l1_name": "one", "in_date": date(2016, 1, 1), "out_date": None}],
                "MISSING.SZ": [{"l1_code": "I1", "l1_name": "one", "in_date": date(2016, 1, 1), "out_date": None}],
            },
            lifecycle={"A.SH": ("20160101", None), "MISSING.SZ": ("20160101", None)},
            coverage_unavailable={("20250627", "MISSING.SZ")},
        )
        members = source.members_for(date(2025, 6, 26), date(2025, 6, 27))
        self.assertEqual([row["symbol"] for row in members], ["A.SH"])

    def test_coverage_unavailable_does_not_override_present_formal_daily_mark(self):
        day = date(2025, 12, 3)
        adapter = _P2Adapter()
        source = _p2_source(
            rows={("20251203", "A.SH"): _p2_row("20251203", "20251202")},
            adapter=adapter,
        )
        self.assertEqual(source.mark("A.SH", day), (10.0, "close"))
        members = source.members_for(date(2025, 12, 2), day)
        self.assertNotIn("A.SH", {row["symbol"] for row in members})

    def test_coverage_unavailable_existing_position_can_exit_at_formal_open(self):
        day = date(2025, 12, 8)
        source = _p2_source(
            rows={("20251208", "A.SH"): _p2_row("20251208", "20251205")},
            adapter=_P2Adapter(),
        )
        self.assertEqual(source.execution("A.SH", day, held=True), (10.0, True, "tradable"))

    def test_present_daily_with_formal_suspension_is_a_source_conflict(self):
        day = date(2025, 11, 27)
        adapter = _P2Adapter(
            suspended_days={("A.SH", day)},
            conflict_days={("A.SH", day)},
        )
        source = _p2_source(adapter=adapter)
        source.mark("A.SH", date(2025, 11, 26))
        with self.assertRaises(ComparisonError):
            source.mark("A.SH", day)

    def test_p2_qualified_held_mark_carries_and_execution_skips_open(self):
        missing_day = date(2025, 11, 27)
        adapter = _P2Adapter(missing_days={("A.SH", missing_day)})
        source = _p2_source(rows={("20251127", "A.SH"): _p2_row("20251127", "20251126")}, adapter=adapter)
        self.assertEqual(source.mark("A.SH", date(2025, 11, 26)), (10.0, "close"))
        self.assertEqual(source.mark("A.SH", missing_day), (10.0, "unavailable_mark_carry"))
        price, tradable, reason = source.execution("A.SH", missing_day, held=True)
        self.assertEqual((price, tradable, reason), (10.0, False, "unavailable_mark_carry_locked"))
        self.assertEqual(adapter.open_calls, [])

    def test_p2_run_locks_position_and_restores_next_valid_mark(self):
        missing_days = {("A.SH", date(2025, 11, 27)), ("A.SH", date(2025, 12, 1))}
        adapter = _P2Adapter(missing_days=missing_days)
        source = _p2_source(
            rows={
                ("20251127", "A.SH"): _p2_row("20251127", "20251126"),
                ("20251201", "A.SH"): _p2_row("20251201", "20251128"),
            },
            adapter=adapter,
        )
        from backend.services.v3_b5_comparison import run_fractional_index

        dates = (date(2025, 11, 26), date(2025, 11, 27), date(2025, 12, 1), date(2025, 12, 9))
        schedule = [
            {"formation_date": "2025-11-26", "as_of_date": "2025-11-25", "execution_date": "2025-11-26"},
            {"formation_date": "2025-12-01", "as_of_date": "2025-11-28", "execution_date": "2025-12-01"},
        ]
        observations = [
            {"date": day.isoformat(), "portfolio_value": value, "daily_return": 0.0 if index == 0 else value / (value - 0.01) - 1.0}
            for index, (day, value) in enumerate(zip(dates, (1.0, 1.01, 1.02, 1.04)))
        ]
        result = run_fractional_index(
            kind="control", source=source, dates=dates, schedule=schedule, strategy_observations=observations
        )
        self.assertEqual(result["daily_rows"][1]["mark_reasons"], {"A.SH": "unavailable_mark_carry"})
        self.assertEqual(result["daily_rows"][2]["mark_reasons"], {"A.SH": "unavailable_mark_carry"})
        self.assertEqual(result["daily_rows"][3]["mark_reasons"], {"A.SH": "close"})
        self.assertEqual(result["rebalances"][1]["turnover"], 0.0)
        self.assertEqual(result["rebalances"][1]["status_reasons"]["A.SH"], "unavailable_mark_carry_locked")
        self.assertEqual(result["daily_rows"][1]["unavailable_count"], 1)
        self.assertEqual(result["daily_rows"][2]["unavailable_count"], 1)
        self.assertEqual([day for symbol, day in adapter.open_calls if symbol == "A.SH"], [date(2025, 11, 26)])
        for row in result["daily_rows"]:
            self.assertAlmostEqual(row["cash"] + row["positions_value"], row["gross_nav"])

    def test_p2_exact_suspension_has_precedence(self):
        suspended_day = date(2025, 11, 27)
        adapter = _P2Adapter(
            missing_days={("A.SH", suspended_day)},
            suspended_days={("A.SH", suspended_day)},
        )
        source = _p2_source(adapter=adapter)
        source.mark("A.SH", date(2025, 11, 26))
        self.assertEqual(source.mark("A.SH", suspended_day), (10.0, "suspended_carry"))

    def test_p2_missing_coverage_prior_or_lifecycle_fails_loud(self):
        missing_day = date(2025, 11, 27)
        cases = [
            _p2_source(adapter=_P2Adapter(missing_days={("A.SH", missing_day)})),
            _p2_source(rows={("20251127", "A.SH"): _p2_row("20251127", "20251125")}),
            _p2_source(rows={("20251127", "A.SH"): _p2_row("20251127", "20251126", reason="other")}),
            _p2_source(
                rows={("20251127", "A.SH"): _p2_row("20251127", "20251126")},
                lifecycle={"A.SH": ("20160101", "20251127"), "B.SH": ("20160101", None)},
            ),
        ]
        for source in cases:
            with self.subTest(source=source):
                with self.assertRaises(ComparisonError):
                    source.mark("A.SH", missing_day)

    def test_p2_daily_conflict_fails_loud(self):
        missing_day = date(2025, 11, 27)
        adapter = _P2Adapter(
            suspended_days={("A.SH", missing_day)},
            conflict_days={("A.SH", missing_day)},
        )
        source = _p2_source(rows={("20251127", "A.SH"): _p2_row("20251127", "20251126")}, adapter=adapter)
        source.mark("A.SH", date(2025, 11, 26))
        with self.assertRaises(ComparisonError):
            source.mark("A.SH", missing_day)

    def test_real_p2_unavailable_mark_slice_20251124_20251209(self):
        repo_root = Path(__file__).resolve().parents[1]
        cutoff = date(2025, 12, 9)
        observation_start = date(2025, 11, 24)
        p2_symbol = "688766.SH"
        p0_symbol = "002348.SZ"
        p2_gap_dates = tuple(
            date.fromisoformat(value)
            for value in (
                "2025-11-27",
                "2025-11-28",
                "2025-12-01",
                "2025-12-02",
                "2025-12-03",
                "2025-12-04",
                "2025-12-05",
            )
        )
        output_root = repo_root / "data/pit/v3_b5_comparisons"
        before_outputs = tuple(sorted(path.name for path in output_root.iterdir())) if output_root.exists() else ()

        raw = FormalPITPartitionAdapter(repo_root)
        guarded = _RecordingReadBoundAdapter(raw, cutoff)
        all_common_dates = tuple(guarded.common_trading_dates(date(1900, 1, 1), cutoff))
        dates = tuple(day for day in all_common_dates if IS_START <= day <= cutoff)
        self.assertTrue(dates)
        self.assertEqual(dates[0], IS_START)
        self.assertEqual(dates[-1], cutoff)
        schedule = build_weekly_schedule(all_common_dates, IS_START, cutoff)

        from scripts.publish_v3_b5_ledger_observations import build_and_publish
        from scripts.verify_v3_b5_ledger_observations import verify_artifact as verify_ledger

        with tempfile.TemporaryDirectory() as observation_root:
            observation_result = build_and_publish(
                repo_root=repo_root,
                output_root=Path(observation_root),
            )
            self.assertEqual(observation_result["status"], "published")
            observation_dir = Path(observation_result["path"])
            self.assertEqual(verify_ledger(observation_dir)["status"], "verified")
            observation_manifest, all_observations = _load_observation_binding(observation_dir)
        observations = [
            row
            for row in all_observations
            if IS_START <= date.fromisoformat(row["date"]) <= cutoff
        ]
        self.assertEqual([row["date"] for row in observations], [day.isoformat() for day in dates])
        self.assertEqual(observation_manifest["is_range"]["start"], IS_START.isoformat())
        self.assertEqual(observation_manifest["is_range"]["end"], "2026-03-19")

        lifecycle, lifecycle_binding = _load_lifecycle(raw.stock_basic_root, DEFAULT_LIFECYCLE_MANIFEST)
        coverage_unavailable, coverage_binding = _load_coverage_binding(repo_root)
        industry_index = _load_industry_index(repo_root)

        benchmark_source = _ObservedComparisonSource(
            guarded,
            industry_index,
            lifecycle=lifecycle,
            coverage_unavailable=coverage_unavailable,
        )
        control_source = _ObservedComparisonSource(
            guarded,
            industry_index,
            lifecycle=lifecycle,
            coverage_unavailable=coverage_unavailable,
        )
        for source in (benchmark_source, control_source):
            source.lifecycle_binding = {"artifact_id": LIFECYCLE_ID, **lifecycle_binding}
            source.coverage_binding = coverage_binding

        self.assertIs(benchmark_source.adapter, control_source.adapter)
        self.assertIs(benchmark_source.adapter._raw, control_source.adapter._raw)
        self.assertIsNot(benchmark_source._last_prices, control_source._last_prices)

        def print_progress(event):
            print(
                f"[{event['kind']}] rebalance "
                f"{event['completed_rebalances']}/{event['total_rebalances']} "
                f"{event['execution_date']} elapsed={event['elapsed_seconds']:.3f}s",
                flush=True,
            )

        def daily_row(result, day):
            day_key = day.isoformat() if isinstance(day, date) else day
            return next(row for row in result["daily_rows"] if row["date"] == day_key)

        def rebalance_row(result, execution_date):
            return next(row for row in result["rebalances"] if row["execution_date"] == execution_date)

        total_p2_events = 0
        for kind, source in (
            ("benchmark", benchmark_source),
            ("control", control_source),
        ):
            result = run_fractional_index(
                kind=kind,
                source=source,
                dates=dates,
                schedule=schedule,
                strategy_observations=observations,
                progress=print_progress,
            )
            self.assertEqual(result["is_range"], {
                "start": IS_START.isoformat(),
                "end": cutoff.isoformat(),
                "count": len(dates),
                "oos_start": OOS_START.isoformat(),
            })
            self.assertTrue(result["non_executable"])
            self.assertEqual(result["availability_mark_carry_event_count"], len(p2_gap_dates))
            total_p2_events += result["availability_mark_carry_event_count"]

            p0_mark = daily_row(result, date(2025, 12, 3))
            self.assertEqual(p0_mark["mark_reasons"].get(p0_symbol), "close")

            p0_exit = rebalance_row(result, "2025-12-08")
            self.assertEqual(p0_exit["status_reasons"].get(p0_symbol), "tradable")
            self.assertNotIn(p0_symbol, p0_exit["target_weights"])
            self.assertNotIn(p0_symbol, p0_exit["executed_weights"])
            self.assertGreater(p0_exit["turnover"], 0.0)
            p0_execution = [
                item
                for item in source.execution_observations
                if item["symbol"] == p0_symbol and item["day"] == date(2025, 12, 8)
            ]
            self.assertEqual(len(p0_execution), 1)
            self.assertGreaterEqual(p0_execution[0]["bar_delta"], 1)
            self.assertEqual(p0_execution[0]["result"][1:], (True, "tradable"))

            for gap_day in p2_gap_dates:
                current = daily_row(result, gap_day)
                self.assertEqual(current["mark_reasons"].get(p2_symbol), "unavailable_mark_carry")
                prior_day = max(day for day in dates if day < gap_day)
                prior = daily_row(result, prior_day)
                self.assertIn(p2_symbol, prior["position_values_by_symbol"])
                self.assertIn(p2_symbol, current["position_values_by_symbol"])
                self.assertAlmostEqual(
                    current["position_values_by_symbol"][p2_symbol],
                    prior["position_values_by_symbol"][p2_symbol],
                    delta=1e-12,
                )
                mark_observations = [
                    item
                    for item in source.mark_observations
                    if item["symbol"] == p2_symbol and item["day"] == gap_day
                ]
                self.assertEqual(len(mark_observations), 1)
                self.assertGreaterEqual(mark_observations[0]["bar_delta"], 1)
                self.assertEqual(mark_observations[0]["result"][1], "unavailable_mark_carry")

            locked_rebalance = rebalance_row(result, "2025-12-01")
            self.assertEqual(locked_rebalance["status_reasons"].get(p2_symbol), "unavailable_mark_carry_locked")
            locked_execution = [
                item
                for item in source.execution_observations
                if item["symbol"] == p2_symbol and item["day"] == date(2025, 12, 1)
            ]
            self.assertEqual(len(locked_execution), 1)
            self.assertEqual(locked_execution[0]["bar_delta"], 0)
            self.assertEqual(locked_execution[0]["result"][1:], (False, "unavailable_mark_carry_locked"))

            suspended_rebalance = daily_row(result, date(2025, 12, 8))
            self.assertEqual(suspended_rebalance["mark_reasons"].get(p2_symbol), "suspended_carry")

            next_valid_mark = daily_row(result, date(2025, 12, 9))
            self.assertEqual(next_valid_mark["mark_reasons"].get(p2_symbol), "close")

            for row in result["daily_rows"]:
                for field in ("gross_nav", "base_net_nav", "stress_net_nav"):
                    self.assertTrue(math.isfinite(float(row[field])))
                    self.assertGreater(float(row[field]), 0.0)
                self.assertGreaterEqual(float(row["cash"]), -1e-12)
                self.assertAlmostEqual(row["cash"] + row["positions_value"], row["gross_nav"], delta=1e-12)

            read_audit = result["source_audit"]["read_audit"]
            self.assertEqual(read_audit["allowed_end"], cutoff.isoformat())
            self.assertLessEqual(date.fromisoformat(read_audit["max_requested_date"]), cutoff)
            self.assertEqual(read_audit["oos_read_count"], 0)

            window_rows = [
                row
                for row in result["daily_rows"]
                if observation_start <= date.fromisoformat(row["date"]) <= cutoff
            ]
            self.assertEqual(window_rows[0]["date"], "2025-11-24")
            self.assertEqual(window_rows[-1]["date"], cutoff.isoformat())
            print(f"[{kind}] verified", flush=True)

        self.assertEqual(total_p2_events, 14)
        after_outputs = tuple(sorted(path.name for path in output_root.iterdir())) if output_root.exists() else ()
        self.assertEqual(after_outputs, before_outputs)


if __name__ == "__main__":
    unittest.main()
