from __future__ import annotations

import pytest

from scripts.publish_v3_liquidity_corrective import publish_suspend_corrective, verify_suspend_corrective


def test_only_authorized_faults_can_be_published(tmp_path):
    faults = [{"symbol": "000524.SZ", "missing_date": "20260624", "execution_date": "20260710"}]
    rows = [{"ts_code": "000524.SZ", "trade_date": "20260624", "suspend_type": "S"}]
    result = publish_suspend_corrective(tmp_path, faults=faults, rows=rows, original_partition_hashes={"20260624": "orig"}, response_hash="resp", authorized_faults=faults)
    assert result["status"] == "published"
    assert verify_suspend_corrective(tmp_path / result["artifact_id"], faults=faults, response_hash="resp")["status"] == "verified"


def test_daily_suspend_conflict_is_rejected(tmp_path):
    faults = [{"symbol": "000524.SZ", "missing_date": "20260624", "execution_date": "20260710"}]
    with pytest.raises(ValueError, match="conflict"):
        publish_suspend_corrective(tmp_path, faults=faults, rows=[{"ts_code": "000524.SZ", "trade_date": "20260624", "suspend_type": "S", "daily_amount": 1.0}], original_partition_hashes={"20260624": "orig"}, response_hash="resp")


def test_unauthorized_fault_is_rejected(tmp_path):
    faults = [{"symbol": "OTHER.SZ", "missing_date": "20260624", "execution_date": "20260710"}]
    with pytest.raises(ValueError, match="authorized"):
        publish_suspend_corrective(tmp_path, faults=faults, rows=[{"ts_code": "OTHER.SZ", "trade_date": "20260624", "suspend_type": "S"}], original_partition_hashes={"20260624": "orig"}, response_hash="resp", authorized_faults=[{"symbol": "000524.SZ", "missing_date": "20260624", "execution_date": "20260710"}])


def test_missing_source_remains_data_fault(tmp_path):
    faults = [{"symbol": "000524.SZ", "missing_date": "20260624", "execution_date": "20260710"}]
    with pytest.raises(ValueError, match="data_fault"):
        publish_suspend_corrective(tmp_path, faults=faults, rows=[], original_partition_hashes={"20260624": "orig"}, response_hash="resp")
