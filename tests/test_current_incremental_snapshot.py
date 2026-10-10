import hashlib
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd

SCRIPT_ROOT = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))

from build_current_incremental_snapshot import (  # noqa: E402
    CurrentIncrementalSnapshotBuilder,
    select_latest_common_date,
)


DATES = ("20260710", "20260713", "20260714", "20260715")


class FakeProvider:
    def __init__(self, *, empty=(), bad_dates=()):
        self.calls = []
        self.active = 0
        self.max_active = 0
        self.empty = set(empty)
        self.bad_dates = set(bad_dates)

    def query(self, api_name, fields=None, **params):
        self.calls.append((api_name, dict(params)))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if api_name == "trade_cal":
                exchange = params["exchange"]
                return pd.DataFrame(
                    {
                        "exchange": [exchange] * len(DATES),
                        "cal_date": list(DATES),
                        "is_open": [1, 1, 1, 1],
                    }
                )
            if api_name == "stock_basic":
                status = params["list_status"]
                rows = [] if status in {"D", "P"} else [{"ts_code": "000001.SZ", "list_date": "20100101", "delist_date": None, "list_status": "L"}]
                return pd.DataFrame(rows, columns=["ts_code", "list_date", "delist_date", "list_status"])
            if api_name == "stock_st":
                return pd.DataFrame(columns=["ts_code", "trade_date", "name"])
            trade_date = params["trade_date"]
            if api_name in self.empty:
                return pd.DataFrame()
            if api_name in {"suspend_d", "stock_st"}:
                return pd.DataFrame(columns=["ts_code", "trade_date", "suspend_type"])
            value_date = "19990101" if api_name in self.bad_dates else trade_date
            rows = {
                "daily": [{"ts_code": "000001.SZ", "trade_date": value_date, "close": 10.0}],
                "adj_factor": [{"ts_code": "000001.SZ", "trade_date": value_date, "adj_factor": 1.0}],
                "stk_limit": [{"ts_code": "000001.SZ", "trade_date": value_date, "up_limit": 11.0, "down_limit": 9.0}],
            }
            return pd.DataFrame(rows[api_name])
        finally:
            self.active -= 1


class FailingProvider(FakeProvider):
    def __init__(self, failed_api):
        super().__init__()
        self.failed_api = failed_api

    def query(self, api_name, fields=None, **params):
        if api_name == self.failed_api:
            self.calls.append((api_name, dict(params)))
            raise RuntimeError("provider failure")
        return super().query(api_name, fields=fields, **params)


def _write_existing_partition(root, dataset, trade_date, frame):
    path = root / dataset / f"trade_date={trade_date}" / "part.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False, engine="pyarrow")
    path.with_suffix(".parquet.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest(), encoding="ascii")


class TestCurrentIncrementalSnapshot(unittest.TestCase):
    def test_latest_common_date_uses_close_and_excludes_weekend(self):
        provider = FakeProvider()
        before_close = datetime(2026, 7, 15, 14, 59)
        after_close = datetime(2026, 7, 15, 15, 0)
        self.assertEqual(select_latest_common_date(provider, before_close), date(2026, 7, 14))
        self.assertEqual(select_latest_common_date(provider, after_close), date(2026, 7, 15))

    def test_build_fetches_only_missing_common_dates_serially(self):
        repo = Path(tempfile.mkdtemp())
        provider = FakeProvider()
        current_root = repo / "data" / "current_market_snapshots"
        for dataset in ("daily", "adj_factor", "suspend_d", "stk_limit"):
            _write_existing_partition(
                current_root,
                dataset,
                "20260713",
                pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": "20260713", "value": 1.0}]),
            )
        result = CurrentIncrementalSnapshotBuilder(
            repo, provider, history_end=date(2026, 7, 10), now=datetime(2026, 7, 14, 16, 0)
        ).build()
        self.assertEqual(result["as_of_date"], "2026-07-14")
        date_calls = [(name, params["trade_date"]) for name, params in provider.calls if "trade_date" in params]
        self.assertTrue(date_calls)
        self.assertTrue(all(trade_date == "20260714" for _, trade_date in date_calls))
        self.assertEqual(provider.max_active, 1)
        manifest = json.loads((repo / result["manifest_path"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["missing_common_dates"], ["20260714"])
        self.assertEqual(manifest["quality_status"], "ok")

    def test_required_empty_or_wrong_date_is_hard_block_without_manifest(self):
        for kwargs in ({"empty": ("daily",)}, {"bad_dates": ("daily",)}):
            repo = Path(tempfile.mkdtemp())
            with self.assertRaises(ValueError):
                CurrentIncrementalSnapshotBuilder(
                    repo, FakeProvider(**kwargs), history_end=date(2026, 7, 10), now=datetime(2026, 7, 13, 16, 0)
                ).build()
            self.assertFalse((repo / "data" / "current_market_snapshots" / "as_of_date=2026-07-13" / "manifest.json").exists())

    def test_suspend_and_stock_st_empty_are_legal_and_manifest_is_auditable(self):
        repo = Path(tempfile.mkdtemp())
        result = CurrentIncrementalSnapshotBuilder(
            repo, FakeProvider(), history_end=date(2026, 7, 10), now=datetime(2026, 7, 13, 16, 0)
        ).build()
        manifest = json.loads((repo / result["manifest_path"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["source"]["timezone"], "Asia/Shanghai")
        self.assertEqual(manifest["source"]["close_time"], "15:00:00")
        self.assertEqual(manifest["gaps"], [])
        self.assertTrue(all("sha256" in item and "source_params" in item for item in manifest["files"]))

    def test_existing_partition_hash_conflict_hard_blocks(self):
        repo = Path(tempfile.mkdtemp())
        root = repo / "data" / "current_market_snapshots"
        frame = pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": "20260713", "close": 10.0}])
        _write_existing_partition(root, "daily", "20260713", frame)
        path = root / "daily" / "trade_date=20260713" / "part.parquet"
        path.write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            CurrentIncrementalSnapshotBuilder(
                repo, FakeProvider(), history_end=date(2026, 7, 10), now=datetime(2026, 7, 13, 16, 0)
            ).build()

    def test_current_namespace_cannot_be_formal_or_backtest_universe(self):
        from build_current_incremental_snapshot import CURRENT_NAMESPACE

        self.assertEqual(CURRENT_NAMESPACE, Path("data/current_market_snapshots"))
        self.assertNotIn("data/pit", str(CURRENT_NAMESPACE).replace("\\", "/"))
        source = (SCRIPT_ROOT / "build_current_incremental_snapshot.py").read_text(encoding="utf-8")
        self.assertNotIn("BacktestUniverseSpec", source)
        self.assertNotIn("point_in_time_universe", source)

    def test_provider_failure_is_not_retried_by_builder(self):
        provider = FailingProvider("daily")
        with self.assertRaises(ValueError):
            CurrentIncrementalSnapshotBuilder(
                Path(tempfile.mkdtemp()), provider, history_end=date(2026, 7, 10), now=datetime(2026, 7, 13, 16, 0)
            ).build()
        self.assertEqual([name for name, _ in provider.calls if name == "daily"], ["daily"])

    def test_builder_reuses_formal_listing_history_without_querying_stock_basic(self):
        repo = Path(tempfile.mkdtemp())
        provider = FakeProvider()
        result = CurrentIncrementalSnapshotBuilder(
            repo, provider, history_end=date(2026, 7, 10), now=datetime(2026, 7, 13, 16, 0)
        ).build()
        self.assertNotIn("stock_basic", [name for name, _ in provider.calls])
        manifest = json.loads((repo / result["manifest_path"]).read_text(encoding="utf-8"))
        self.assertNotIn("stock_basic", manifest["source"]["apis"])

    def test_env_loader_allows_only_two_keys_and_preserves_explicit_environment(self):
        from build_current_incremental_snapshot import _load_env_local

        repo = Path(tempfile.mkdtemp())
        (repo / ".env.local").write_text(
            "TUSHARE_TOKEN='file-token'\nTUSHARE_API_URL=\"http://file.example\"\nOTHER_SECRET=must-ignore\n",
            encoding="utf-8",
        )
        import os

        old = {key: os.environ.get(key) for key in ("TUSHARE_TOKEN", "TUSHARE_API_URL", "OTHER_SECRET")}
        try:
            os.environ.pop("TUSHARE_TOKEN", None)
            os.environ["TUSHARE_API_URL"] = "http://explicit.example"
            os.environ.pop("OTHER_SECRET", None)
            _load_env_local(repo)
            self.assertEqual(os.environ["TUSHARE_TOKEN"], "file-token")
            self.assertEqual(os.environ["TUSHARE_API_URL"], "http://explicit.example")
            self.assertNotIn("OTHER_SECRET", os.environ)
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_cli_bootstraps_repo_root_before_backend_imports(self):
        source = (SCRIPT_ROOT / "build_current_incremental_snapshot.py").read_text(encoding="utf-8")
        bootstrap = source.index("Path(__file__).resolve().parents[1]")
        backend_import = source.index("from backend.app.tushare.config import TushareConfig")
        self.assertLess(bootstrap, backend_import)
        self.assertIn("sys.path.insert(0, str(PROJECT_ROOT))", source)


if __name__ == "__main__":
    unittest.main()
