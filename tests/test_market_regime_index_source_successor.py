from pathlib import Path

import pytest

from scripts.market_regime_bounded_replay import publish_index_source
from scripts.market_regime_index_source_successor import publish_successor, verify_successor


def test_index_successor_binds_predecessor_and_exact_dates(tmp_path: Path) -> None:
    predecessor = publish_index_source(
        [{"ts_code": "000300.SH", "trade_date": "20200117", "close": 100.0, "pre_close": 100.0}],
        [{"api": "index_daily", "ts_code": "000300.SH", "start_date": "20200117", "end_date": "20200117"}],
        tmp_path / "sources",
    )
    rows = [
        {"ts_code": "000300.SH", "trade_date": day, "close": 100.0, "pre_close": 100.0}
        for day in ("20200120", "20200121", "20200122", "20200123", "20200203", "20200204", "20200205", "20200206", "20200207")
    ]
    result = publish_successor(
        rows,
        [{"api": "index_daily", "ts_code": "000300.SH", "start_date": "20200120", "end_date": "20200207"}],
        predecessor_dir=Path(predecessor["path"]),
        output_root=tmp_path / "successors",
        expected_dates=[row["trade_date"] for row in rows],
    )
    assert result["status"] == "published"
    assert verify_successor(
        Path(result["path"]),
        predecessor_dir=Path(predecessor["path"]),
        expected_dates=[row["trade_date"] for row in rows],
    )["status"] == "verified"


def test_index_successor_rejects_extra_date(tmp_path: Path) -> None:
    predecessor = publish_index_source(
        [{"ts_code": "000300.SH", "trade_date": "20200117", "close": 100.0, "pre_close": 100.0}],
        [{"api": "index_daily", "ts_code": "000300.SH", "start_date": "20200117", "end_date": "20200117"}],
        tmp_path / "sources",
    )
    rows = [{"ts_code": "000300.SH", "trade_date": day, "close": 100.0, "pre_close": 100.0} for day in ("20200120", "20200121")]
    with pytest.raises(ValueError, match="exact date set"):
        publish_successor(
            rows,
            [],
            predecessor_dir=Path(predecessor["path"]),
            output_root=tmp_path / "successors",
            expected_dates=["20200120"],
        )
