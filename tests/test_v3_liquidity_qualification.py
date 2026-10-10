from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.qualify_v3_liquidity import ALGORITHM, _load_scope, _source_inventory, _stock_basic_inventory
from scripts.qualify_v3_liquidity import qualify
from scripts.verify_v3_liquidity import verify


def _fixture(tmp_path: Path) -> dict[str, Path]:
    daily = tmp_path / "daily"
    suspend = tmp_path / "suspend_d"
    for offset in range(21):
        day = (date(2020, 1, 2) + pd.Timedelta(days=offset)).strftime("%Y%m%d")
        (daily / f"trade_date={day}").mkdir(parents=True)
        (suspend / f"trade_date={day}").mkdir(parents=True)
        pd.DataFrame({"ts_code": ["000001.SZ"], "amount": [1000.0], "trade_date": [int(day)]}).to_parquet(daily / f"trade_date={day}" / "part.parquet")
        pd.DataFrame({"ts_code": [], "trade_date": []}).to_parquet(suspend / f"trade_date={day}" / "part.parquet")
    calendar_data = tmp_path / "calendar.parquet"
    pd.DataFrame({"cal_date": [int((date(2020, 1, 2) + pd.Timedelta(days=i)).strftime("%Y%m%d")) for i in range(21)], "is_open": [1] * 21}).to_parquet(calendar_data)
    import hashlib
    calendar = tmp_path / "calendar.json"
    calendar.write_text(json.dumps({"artifact_id": "cal", "comparison": {"common_first_date": "20200102", "common_last_date": "20200122", "common_open_count": 21}, "parquet": {"path": "calendar.parquet", "sha256": hashlib.sha256(calendar_data.read_bytes()).hexdigest()}}), encoding="utf-8")
    lifecycle = tmp_path / "lifecycle.json"
    lifecycle.write_text(json.dumps({"successor_id": "49b09326f35936c6", "qualification_status": "bounded_qualified_vendor_lifecycle", "codes": [{"ts_code": "000001.SZ", "list_date": "19900101", "delist_date": "99991231", "gap_dates": []}]}), encoding="utf-8")
    daily_index = tmp_path / "daily-index.json"
    daily_index.write_text(json.dumps({"interfaces": {"daily": {"interface_content_hash": "dailyhash"}}}), encoding="utf-8")
    suspend_index = tmp_path / "suspend-index.json"
    suspend_index.write_text(json.dumps({"interfaces": {"suspend_d": {"interface_content_hash": "suspendhash"}}}), encoding="utf-8")
    records = tmp_path / "records.parquet"
    pd.DataFrame({"symbol": ["000001.SZ"], "effective_from": [date(1990, 1, 1)], "effective_to": [None]}).to_parquet(records)
    stock = tmp_path / "stock_basic"
    for status in ("L", "D", "P"):
        (stock / f"list_status={status}").mkdir(parents=True)
        pd.DataFrame({"ts_code": ["000001.SZ"] if status == "L" else [], "list_date": ["19900101"] if status == "L" else [], "delist_date": [None] if status == "L" else []}).to_parquet(stock / f"list_status={status}" / "part.parquet")
    return {"daily_root": daily, "suspend_root": suspend, "calendar": calendar, "lifecycle": lifecycle, "daily_index": daily_index, "suspend_index": suspend_index, "membership_records": records, "stock_basic_root": stock}


def test_qualifies_and_verifies_liquidity_metadata(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    result = qualify(**paths, output_root=tmp_path / "out", template_hash="t", data_requirements_hash="r", source_range=(date(2020, 1, 22), date(2020, 1, 22)))
    assert result["status"] == "published"
    assert result["data_fault_count"] == 0
    assert verify(tmp_path / "out" / result["artifact_id"], **paths)["status"] == "verified"


def test_data_fault_blocks_publication(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    bad = paths["daily_root"] / "trade_date=20200121" / "part.parquet"
    pd.DataFrame({"ts_code": ["000001.SZ"], "amount": [None], "trade_date": [20200121]}).to_parquet(bad)
    with pytest.raises(ValueError, match="data_fault"):
        qualify(**paths, output_root=tmp_path / "out", template_hash="t", data_requirements_hash="r", source_range=(date(2020, 1, 22), date(2020, 1, 22)))


def test_current_qualifier_uses_valid_daily_amount_before_r(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    day = "20200121"
    pd.DataFrame({"ts_code": ["000001.SZ"], "amount": [1_000_000.0], "trade_date": [int(day)]}).to_parquet(paths["daily_root"] / f"trade_date={day}" / "part.parquet")
    pd.DataFrame({"ts_code": ["000001.SZ"], "trade_date": [int(day)], "suspend_type": ["R"]}).to_parquet(paths["suspend_root"] / f"trade_date={day}" / "part.parquet")

    result = qualify(**paths, output_root=tmp_path / "out", template_hash="t", data_requirements_hash="r", source_range=(date(2020, 1, 22), date(2020, 1, 22)))

    assert result["data_fault_count"] == 0
    assert result["scope"]["stats"]["complete_count"] == 1


def test_current_qualifier_does_not_mask_invalid_daily_with_s(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    day = "20200121"
    pd.DataFrame({"ts_code": ["000001.SZ"], "amount": [None], "trade_date": [int(day)]}).to_parquet(paths["daily_root"] / f"trade_date={day}" / "part.parquet")
    pd.DataFrame({"ts_code": ["000001.SZ"], "trade_date": [int(day)], "suspend_type": ["S"]}).to_parquet(paths["suspend_root"] / f"trade_date={day}" / "part.parquet")

    with pytest.raises(ValueError, match="data_fault"):
        qualify(**paths, output_root=tmp_path / "out", template_hash="t", data_requirements_hash="r", source_range=(date(2020, 1, 22), date(2020, 1, 22)))


def test_insufficient_window_is_unavailable_not_fault(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    result = qualify(**paths, output_root=tmp_path / "out", template_hash="t", data_requirements_hash="r", source_range=(date(2020, 1, 2), date(2020, 1, 2)))
    assert result["status"] == "published"
    assert result["unavailable_ineligible_count"] == 1
    assert result["data_fault_count"] == 0


def test_tampered_source_is_rejected_by_verifier(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    result = qualify(**paths, output_root=tmp_path / "out", template_hash="t", data_requirements_hash="r", source_range=(date(2020, 1, 22), date(2020, 1, 22)))
    bad = paths["daily_root"] / "trade_date=20200121" / "part.parquet"
    bad.write_bytes(b"tampered")
    assert verify(tmp_path / "out" / result["artifact_id"], **paths)["status"] == "invalid"


def test_algorithm_is_complete_frozen_contract() -> None:
    assert set(ALGORITHM) == {"algorithm_id", "window_trading_days", "execution_day_excluded", "source_field", "source_unit", "yuan_multiplier", "threshold_yuan", "suspended_day_amount_yuan", "minimum_history_trading_days", "insufficient_history", "suspension_evidence_source", "other_missing", "partial_mean_allowed", "window_extension_allowed"}


def test_stock_basic_inventory_is_repo_relative_rglob(tmp_path: Path) -> None:
    root = tmp_path / "nested" / "list_status=L"
    root.mkdir(parents=True)
    (root / "part.parquet").write_bytes(b"x")
    assert _stock_basic_inventory(tmp_path / "nested")["files"][0]["path"].endswith("list_status=L/part.parquet")


def test_scope_shared_and_source_inventory_is_window_only(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    scope, common, _ = _load_scope(paths["membership_records"], paths["stock_basic_root"], paths["calendar"], paths["lifecycle"], date(2020, 1, 22), date(2020, 1, 22))
    assert scope == [("000001.SZ", date(2020, 1, 22))]
    assert _source_inventory(paths["daily_root"], common[-20], common[-1])["entry_count"] == 20


def test_partition_reader_is_cached_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _fixture(tmp_path)
    calls = {"daily": 0, "suspend_d": 0}
    from scripts import qualify_v3_liquidity as mod
    original = mod._rows
    def counted(root, day):
        calls[root.name] += 1
        return original(root, day)
    monkeypatch.setattr(mod, "_rows", counted)
    mod.qualify(**paths, output_root=tmp_path / "out", template_hash="t", data_requirements_hash="r", source_range=(date(2020, 1, 22), date(2020, 1, 22)))
    assert calls["daily"] <= 20
    assert calls["suspend_d"] <= 20


def test_corrective_overlay_supplies_only_authorized_suspend_rows(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    from scripts.publish_v3_liquidity_corrective import publish_suspend_corrective
    fault = {"symbol": "000001.SZ", "missing_date": "20200121", "execution_date": "20200122"}
    overlay = tmp_path / "overlay"
    publish_suspend_corrective(overlay, faults=[fault], rows=[{"ts_code": "000001.SZ", "trade_date": "20200121", "suspend_type": "S"}], original_partition_hashes={"20200121": "orig"}, response_hash="resp")
    overlay = overlay / next(overlay.iterdir()).name
    result = qualify(**paths, output_root=tmp_path / "out", template_hash="t", data_requirements_hash="r", source_range=(date(2020, 1, 22), date(2020, 1, 22)), corrective_overlay=overlay)
    assert result["status"] == "published"
