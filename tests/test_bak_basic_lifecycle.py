"""Checks for the bounded bak_basic lifecycle supplement candidate."""
import json
from pathlib import Path


MANIFEST = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/bak_basic_lifecycle/manifest.json")


def test_bak_basic_manifest_binds_each_lifecycle_gap_code():
    """Every code absent from stock_basic must be explicitly covered or block."""
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["status"] == "candidate_verified"
    assert {item["ts_code"] for item in manifest["partitions"]} == {"000022.SZ", "000043.SZ", "300114.SZ"}


def test_bak_basic_candidate_covers_every_observed_daily_gap_date():
    """The supplement is valid only when its dated history covers each daily observation."""
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["uncovered_daily_gap_dates"] == 0
    assert manifest["formal_qualification_run"] is False
