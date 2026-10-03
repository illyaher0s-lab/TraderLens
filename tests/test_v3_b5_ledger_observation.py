from __future__ import annotations

import json
import inspect
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from backend.services.v3_b5_ledger_observation import (
    LedgerObservationError,
    authoritative_final_match,
    canonical_bytes,
    replay_ledger,
    validate_observation_rows,
)
from scripts.publish_v3_b5_ledger_observations import _load_b4, _write_once
from scripts.verify_v3_b5_ledger_observations import _canonical_final_comparison


ROOT = Path(__file__).resolve().parents[1]


class _Status:
    def __init__(self, suspended: bool = False):
        self.is_suspended = suspended


class _Bar:
    def __init__(self, day: date, close: float):
        self.date = day
        self.close = close


class _Source:
    def __init__(self, dates, closes, suspended=()):
        self.dates = tuple(dates)
        self.closes = dict(closes)
        self.suspended = set(suspended)
        self.bar_calls = []

    def get_status(self, symbol, day):
        return _Status((symbol, day) in self.suspended)

    def get_bar(self, symbol, day):
        self.bar_calls.append((symbol, day))
        if (symbol, day) not in self.closes:
            raise KeyError((symbol, day))
        return _Bar(day, self.closes[(symbol, day)])


def _event(*, fill_price=10.0, final_cash=98995.0):
    from backend.services.b4_protocol_types import (
        DailyPortfolioSnapshot,
        EventBacktestResult,
        FillRecord,
        OrderIntentRecord,
    )

    day = date(2025, 6, 27)
    final_day = date(2025, 6, 30)
    return EventBacktestResult(
        result_id="result",
        strategy_revision_id="revision",
        protocol_snapshot_id="protocol",
        evaluation_mode="formal_backtest",
        backtest_start=day,
        backtest_end=final_day,
        order_intents=(OrderIntentRecord(
            order_id="order-1", symbol="AAA.SH", signal_date=day,
            intent="buy", quantity=100,
        ),),
        fills=(FillRecord(
            fill_id="fill-1", order_id="order-1", symbol="AAA.SH",
            fill_date=day, fill_price=fill_price, fill_quantity=100,
            execution_mode="simulated",
        ),),
        rejected_orders=(), future_violations=(),
        final_portfolio=DailyPortfolioSnapshot(
            snapshot_id="final", snapshot_date=final_day, cash=final_cash,
            positions=(("AAA.SH", 100),), portfolio_value=100095.0,
        ),
        frozen_at=day,
    )


def _prepare_temp_b4_inputs(root: Path) -> tuple[Path, Path]:
    from tests.test_v3_execution_semantics import _copy_fixture_repo

    repo_root = _copy_fixture_repo(root / "repo")
    supplement_source = ROOT / "data/pit/v3_execution_semantics_supplements/185a6b8f03915dca"
    supplement_target = repo_root / "data/pit/v3_execution_semantics_supplements/185a6b8f03915dca"
    shutil.copytree(supplement_source, supplement_target)
    b4_source = ROOT / "data/pit/v3_b4_is_results/cfa75e8b2a72bc76"
    b4_target = repo_root / "data/pit/v3_b4_is_results/cfa75e8b2a72bc76"
    b4_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(b4_source, b4_target)
    return repo_root, b4_target


class LedgerObservationTests(unittest.TestCase):
    def test_v3_b5_ledger_rebinds_cfa_predecessor_lineage(self):
        import scripts.publish_v3_b5_ledger_observations as publisher

        with tempfile.TemporaryDirectory() as raw:
            repo_root = Path(raw)
            target = repo_root / "data/pit/v3_b4_is_results" / publisher.B4_ID
            target.parent.mkdir(parents=True)
            shutil.copytree(ROOT / "data/pit/v3_b4_is_results/cfa75e8b2a72bc76", target)
            with patch.object(
                publisher,
                "verify_v3_b4_is_result",
                return_value={"status": "verified"},
            ):
                manifest, event, manifest_sha, event_sha = publisher._load_b4(repo_root)
        self.assertEqual(manifest["artifact_id"], "cfa75e8b2a72bc76")
        self.assertEqual(manifest_sha, "b7db7cd296987ebd85ad199df16841a3a5d8a105892350e5a0bd091e4b5b6f89")
        self.assertEqual(event_sha, "8a8b5955ea6620c97e93914cdfdecd7006967bad0a297affb87a09af064d9a74")
        self.assertEqual(manifest["supplement"]["supplement_id"], "185a6b8f03915dca")
        self.assertEqual(len(event.fills), 124)

    def test_b5_private_loaders_accept_repo_root_and_protocol_loader_is_read_only(self):
        import scripts.publish_v3_b5_ledger_observations as publisher

        for name in (
            "_load_protocol",
            "_load_b4",
            "_load_formal_manifest",
            "_load_immutable_trading_supplement",
            "_load_lineage",
            "_producer_source_bindings",
        ):
            self.assertIn("repo_root", inspect.signature(getattr(publisher, name)).parameters)

        with tempfile.TemporaryDirectory() as raw:
            repo_root = Path(raw)
            (repo_root / "data").mkdir()
            shutil.copy2(ROOT / "data/strategy.db", repo_root / "data/strategy.db")
            calls = []
            real_connect = publisher.sqlite3.connect

            def tracked_connect(database, *args, **kwargs):
                calls.append((str(database), dict(kwargs)))
                return real_connect(database, *args, **kwargs)

            with patch.object(publisher.sqlite3, "connect", tracked_connect):
                protocol, _payload_sha = publisher._load_protocol(repo_root)

            self.assertEqual(protocol.protocol_snapshot_id, publisher.PROTOCOL_ID)
            self.assertEqual(len(calls), 1)
            self.assertTrue(calls[0][0].startswith("file:"))
            self.assertIn("mode=ro", calls[0][0])
            self.assertTrue(calls[0][1].get("uri"))

    def test_v3_b5_ledger_observations_rebinds_new_protocol_lineage(self):
        import scripts.publish_v3_b5_ledger_observations as publisher

        with tempfile.TemporaryDirectory() as raw:
            repo_root = Path(raw)
            target = repo_root / "data/pit/v3_b4_is_results" / publisher.B4_ID
            target.parent.mkdir(parents=True)
            shutil.copytree(ROOT / "data/pit/v3_b4_is_results/cfa75e8b2a72bc76", target)
            with patch.object(publisher, "verify_v3_b4_is_result", return_value={"status": "verified"}):
                manifest, event, manifest_sha, event_sha = publisher._load_b4(repo_root)
        self.assertEqual(manifest["artifact_id"], "cfa75e8b2a72bc76")
        self.assertEqual(manifest_sha, "b7db7cd296987ebd85ad199df16841a3a5d8a105892350e5a0bd091e4b5b6f89")
        self.assertEqual(event_sha, "8a8b5955ea6620c97e93914cdfdecd7006967bad0a297affb87a09af064d9a74")
        self.assertEqual(manifest["supplement"]["supplement_id"], "185a6b8f03915dca")
        self.assertEqual(len(event.fills), 124)

    def test_successor_ledger_publishes_and_verifies_in_temporary_root(self):
        from scripts.publish_v3_b5_ledger_observations import build_and_publish
        from scripts.verify_v3_b5_ledger_observations import verify_artifact

        import scripts.publish_v3_b5_ledger_observations as publisher
        import scripts.run_v3_b4_is_once as b4_runner

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            temp_repo, temp_b4 = _prepare_temp_b4_inputs(root)
            b4_calls = []

            def verify_temp(_path, *, repo_root):
                b4_calls.append((Path(_path), Path(repo_root)))
                return b4_runner.verify_v3_b4_is_result(temp_b4, repo_root=temp_repo)

            connection_targets = []
            real_connect = publisher.sqlite3.connect

            def guarded_connect(database, *args, **kwargs):
                connection_targets.append((str(database), dict(kwargs)))
                if "mode=ro" not in str(database) or kwargs.get("uri") is not True:
                    raise AssertionError(f"non-read-only SQLite connection: {database!r} {kwargs!r}")
                return real_connect(database, *args, **kwargs)

            with patch.object(publisher, "verify_v3_b4_is_result", verify_temp), patch.object(
                publisher.sqlite3, "connect", guarded_connect
            ):
                result = build_and_publish(repo_root=ROOT, output_root=root / "ledger")
                self.assertEqual(result["status"], "published")
                artifact_dir = Path(result["path"])
                verified = verify_artifact(artifact_dir, repo_root=ROOT)
            self.assertEqual(verified["status"], "verified")
            self.assertEqual(len(b4_calls), 2)
            self.assertEqual(len(connection_targets), 4)
            manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["lineage"]["b4"], {
                "artifact_id": "cfa75e8b2a72bc76",
                "manifest_sha256": "b7db7cd296987ebd85ad199df16841a3a5d8a105892350e5a0bd091e4b5b6f89",
                "event_sha256": "8a8b5955ea6620c97e93914cdfdecd7006967bad0a297affb87a09af064d9a74",
            })
            self.assertEqual(manifest["lineage"]["trading_supplement"], {
                "supplement_id": "185a6b8f03915dca",
                "manifest_sha256": "df51e7a9efae3b6e915d8cac8210b431e07f3992fe83fb183e499e512bc9c895",
            })
            self.assertEqual(manifest["observations"]["count"], 176)
            self.assertEqual(manifest["fills"]["count"], 124)
            self.assertTrue(manifest["fills"]["consumed_once"])
            self.assertTrue(manifest["authoritative_final_match"]["all_equal"])
            self.assertEqual(manifest["read_audit"]["max_requested_date"], "2026-03-19")
            self.assertEqual(manifest["read_audit"]["oos_read_count"], 0)
            self.assertEqual(manifest["is_range"]["oos_start"], "2026-03-20")
            for name in ("rank_snapshot", "entry_symbols", "exit_symbols", "confirmation", "derive_liquidity", "market_regime", "entry_generation", "exit_generation"):
                self.assertEqual(manifest["operation_counts"].get(name, 0), 0)
            self.assertEqual(verified["fill_count"], 124)
            self.assertEqual(verified["oos_read_count"], 0)
            observations_path = artifact_dir / "observations.json"
            observations_path.write_bytes(observations_path.read_bytes() + b" ")
            with self.assertRaises(ValueError):
                verify_artifact(artifact_dir, repo_root=ROOT)

    def test_replays_fills_and_matches_authoritative_final_fields(self):
        day = date(2025, 6, 27)
        final_day = date(2025, 6, 30)
        source = _Source((day, final_day), {("AAA.SH", day): 10.0, ("AAA.SH", final_day): 11.0})
        replay = replay_ledger(_event(), source, (day, final_day), initial_capital=100000.0)

        self.assertEqual(replay.consumed_fill_ids, ("fill-1",))
        self.assertTrue(authoritative_final_match(replay.portfolio, _event().final_portfolio)["all_equal"])
        self.assertEqual(replay.observations[0]["daily_return"], 0.0)

    def test_suspended_missing_bar_carries_last_price(self):
        day = date(2025, 6, 27)
        final_day = date(2025, 6, 30)
        source = _Source((day, final_day), {}, suspended={("AAA.SH", day), ("AAA.SH", final_day)})
        replay = replay_ledger(_event(), source, (day, final_day), initial_capital=100000.0)

        self.assertEqual(source.bar_calls, [])
        self.assertEqual(replay.observations[0]["positions_value"], 1000.0)

    def test_non_suspended_missing_bar_fails_loud(self):
        day = date(2025, 6, 27)
        with self.assertRaises(LedgerObservationError):
            replay_ledger(_event(), _Source((day, date(2025, 6, 30)), {}), (day, date(2025, 6, 30)), initial_capital=100000.0)

    def test_validation_rejects_date_gap_and_future(self):
        day = date(2025, 6, 27)
        rows = [{
            "date": (day + timedelta(days=1)).isoformat(),
            "cash": 1.0, "portfolio_value": 1.0,
            "gross_exposure": 0.0, "net_exposure": 0.0,
            "positions_value": 0.0, "daily_return": 0.0,
            "position_values_by_symbol": {},
        }]
        with self.assertRaises(LedgerObservationError):
            validate_observation_rows(rows, (day,), allowed_end=day)

    def test_derived_position_fields_are_not_predecessor_assertions(self):
        result = authoritative_final_match(None, _event().final_portfolio)
        self.assertFalse(result["average_cost"]["comparable"])
        self.assertFalse(result["last_price"]["comparable"])

    def test_fee_cash_mismatch_is_rejected_by_authoritative_match(self):
        day = date(2025, 6, 27)
        final_day = date(2025, 6, 30)
        source = _Source((day, final_day), {("AAA.SH", day): 10.0, ("AAA.SH", final_day): 11.0})
        replay = replay_ledger(_event(), source, (day, final_day), initial_capital=100000.0)
        comparison = authoritative_final_match(replay.portfolio, _event(final_cash=98994.0).final_portfolio)
        self.assertFalse(comparison["all_equal"])

    def test_verified_b4_lineage_is_read_only_and_exact(self):
        import scripts.publish_v3_b5_ledger_observations as publisher

        with tempfile.TemporaryDirectory() as raw:
            repo_root = Path(raw)
            target = repo_root / "data/pit/v3_b4_is_results" / publisher.B4_ID
            target.parent.mkdir(parents=True)
            shutil.copytree(ROOT / "data/pit/v3_b4_is_results/cfa75e8b2a72bc76", target)
            with patch.object(publisher, "verify_v3_b4_is_result", return_value={"status": "verified"}):
                manifest, event, manifest_sha, event_sha = publisher._load_b4(repo_root)
        self.assertEqual(manifest_sha, "b7db7cd296987ebd85ad199df16841a3a5d8a105892350e5a0bd091e4b5b6f89")
        self.assertEqual(event_sha, "8a8b5955ea6620c97e93914cdfdecd7006967bad0a297affb87a09af064d9a74")
        self.assertEqual(manifest["supplement"]["supplement_id"], "185a6b8f03915dca")
        self.assertEqual(len(event.fills), 124)

    def test_write_once_reuses_exact_payload_and_rejects_conflict(self):
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "artifact"
            manifest = {"artifact_id": "fixture", "schema_version": "fixture.v1", "status": "valid"}
            observations = [{"date": "2025-06-27", "cash": 1.0}]
            first = _write_once(target, manifest, observations)
            self.assertEqual(first["status"], "published")
            published_mtime_ns = target.stat().st_mtime_ns
            second = _write_once(target, manifest, observations)
            self.assertEqual(second["status"], "already_published")
            self.assertEqual(target.stat().st_mtime_ns, published_mtime_ns)
            target.joinpath("observations.json").write_text(json.dumps([{"date": "tampered"}]), encoding="utf-8")
            with self.assertRaises(ValueError):
                _write_once(target, manifest, observations)

    def test_write_once_failure_never_exposes_partial_target(self):
        import scripts.publish_v3_b5_ledger_observations as publisher

        with tempfile.TemporaryDirectory() as raw:
            output_root = Path(raw)
            target = output_root / "artifact"
            manifest = {"artifact_id": "fixture", "schema_version": "fixture.v1", "status": "valid"}
            observations = [{"date": "2025-06-27", "cash": 1.0}]
            real_replace = publisher.os.replace

            def fail_final(source, destination):
                if Path(destination) == target:
                    raise OSError("injected final publish failure")
                return real_replace(source, destination)

            with patch.object(publisher.os, "replace", side_effect=fail_final):
                with self.assertRaisesRegex(OSError, "injected final publish failure"):
                    publisher._write_once(target, manifest, observations)

            self.assertFalse(target.exists())
            staging = list(output_root.glob(".artifact.staging-*"))
            self.assertEqual(len(staging), 1)
            self.assertEqual(
                {path.name for path in staging[0].iterdir()},
                {"manifest.json", "manifest.json.sha256", "observations.json", "observations.json.sha256"},
            )

    def test_authoritative_match_is_canonical_json_safe_for_real_dates(self):
        from strategy_core.portfolio import PortfolioState

        comparison = authoritative_final_match(PortfolioState(cash=98995.0), _event().final_portfolio)

        def assert_json_safe(value):
            if isinstance(value, dict):
                for child in value.values():
                    assert_json_safe(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    assert_json_safe(child)
            else:
                self.assertNotIsInstance(value, date)

        assert_json_safe(comparison)
        encoded = canonical_bytes(comparison)
        self.assertIn(b"2025-06-30", encoded)

    def test_final_comparison_normalizes_json_roundtrip_list_tuple_shape(self):
        from strategy_core.portfolio import PortfolioState

        fresh = authoritative_final_match(PortfolioState(cash=98995.0), _event().final_portfolio)
        stored = json.loads(canonical_bytes(fresh))
        self.assertNotEqual(stored, fresh)
        self.assertEqual(_canonical_final_comparison(stored), _canonical_final_comparison(fresh))


if __name__ == "__main__":
    unittest.main()
