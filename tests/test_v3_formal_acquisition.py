from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest


class _FakePro:
    def __init__(
        self,
        owner: "_FakeClient",
        *,
        missing_lifecycle: bool = False,
        duplicate_status: bool = False,
        duplicate_calendar: bool = False,
        invalid_pretrade: bool = False,
        invalid_taxonomy_level: bool = False,
        invalid_membership_binding: bool = False,
        duplicate_membership: bool = False,
        duplicate_daily: bool = False,
        invalid_daily_numeric: bool = False,
    ):
        self.owner = owner
        self.missing_lifecycle = missing_lifecycle
        self.duplicate_status = duplicate_status
        self.duplicate_calendar = duplicate_calendar
        self.invalid_pretrade = invalid_pretrade
        self.invalid_taxonomy_level = invalid_taxonomy_level
        self.invalid_membership_binding = invalid_membership_binding
        self.duplicate_membership = duplicate_membership
        self.duplicate_daily = duplicate_daily
        self.invalid_daily_numeric = invalid_daily_numeric

    def _record(self, api: str, params: dict) -> None:
        self.owner.calls.append({"api": api, "params": dict(params)})
        if self.owner.transient_failures:
            self.owner.transient_failures -= 1
            raise TimeoutError("transient provider timeout")
        if self.owner.provider_error is not None:
            raise self.owner.provider_error

    def trade_cal(self, **params):
        self._record("trade_cal", params)
        exchange = params["exchange"]
        row = {
            "exchange": exchange,
            "cal_date": "20240102",
            "is_open": 1,
            "pretrade_date": "20240101",
        }
        if self.invalid_pretrade:
            row["pretrade_date"] = "20240102"
        rows = [row]
        if self.duplicate_calendar:
            rows.append(dict(row))
        return pd.DataFrame(rows)

    def stock_basic(self, **params):
        self._record("stock_basic", params)
        status = params["list_status"]
        rows = {
            "L": [{
                "ts_code": "000001.SZ", "symbol": "000001", "name": "A",
                "market": "主板", "exchange": "SZ", "list_status": "L",
                "list_date": "20200101", "delist_date": None,
            }],
            "D": [{
                "ts_code": "000002.SZ", "symbol": "000002", "name": "B",
                "market": "主板", "exchange": "SZ", "list_status": "D",
                "list_date": "20200101", "delist_date": "20250101",
            }],
            "P": [],
        }[status]
        if self.duplicate_status and status == "D":
            rows = [{**rows[0], "ts_code": "000001.SZ"}]
        return pd.DataFrame(rows, columns=[
            "ts_code", "symbol", "name", "market", "exchange", "list_status", "list_date", "delist_date",
        ])

    def index_classify(self, **params):
        self._record("index_classify", params)
        return pd.DataFrame([{
            "index_code": "801010.SI", "industry_name": "农林牧渔",
            "level": "L2" if self.invalid_taxonomy_level else "L1", "is_pub": "Y",
        }])

    def index_member_all(self, **params):
        self._record("index_member_all", params)
        if params["is_new"] == "N":
            return pd.DataFrame(columns=["ts_code", "l1_code", "l1_name", "in_date", "out_date", "is_new"])
        rows = [
            {"ts_code": "000001.SZ", "l1_code": "801010.SI", "l1_name": "农林牧渔", "in_date": "20200101", "out_date": None, "is_new": "Y"},
            {"ts_code": "000002.SZ", "l1_code": "801010.SI", "l1_name": "农林牧渔", "in_date": "20200101", "out_date": "20250101", "is_new": "Y"},
        ]
        if params["is_new"] == "N" and self.duplicate_membership:
            rows = [{**rows[0], "is_new": "N"}]
        if self.invalid_membership_binding:
            rows[0]["l1_code"] = "801020.SI"
        if self.missing_lifecycle:
            rows.append({"ts_code": "000991.SZ", "l1_code": "801010.SI", "l1_name": "农林牧渔", "in_date": "20160823", "out_date": None, "is_new": "Y"})
        return pd.DataFrame(rows)

    def daily(self, **params):
        self._record("daily", params)
        rows = [
            {"ts_code": symbol, "trade_date": "20240102", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5, "vol": 1000.0, "amount": 100000.0}
            for symbol in ("000001.SZ", "000002.SZ")
        ]
        if self.duplicate_daily:
            rows.append(dict(rows[0]))
        if self.invalid_daily_numeric:
            rows[0]["close"] = float("nan")
        return pd.DataFrame(rows)

    def adj_factor(self, **params):
        self._record("adj_factor", params)
        return pd.DataFrame([
            {"ts_code": symbol, "trade_date": "20240102", "adj_factor": 1.0}
            for symbol in ("000001.SZ", "000002.SZ")
        ])

    def stk_limit(self, **params):
        self._record("stk_limit", params)
        return pd.DataFrame([
            {"ts_code": symbol, "trade_date": "20240102", "up_limit": 20.0, "down_limit": 5.0}
            for symbol in ("000001.SZ", "000002.SZ")
        ])

    def stock_st(self, **params):
        self._record("stock_st", params)
        return pd.DataFrame(columns=["ts_code", "name", "trade_date", "type", "type_name"])

    def suspend_d(self, **params):
        self._record("suspend_d", params)
        return pd.DataFrame(columns=["ts_code", "trade_date", "suspend_timing", "suspend_type"])

    def index_daily(self, **params):
        self._record("index_daily", params)
        return pd.DataFrame([{
            "ts_code": params["ts_code"], "trade_date": "20240102", "close": 100.0, "vol": 1000.0, "amount": 100000.0,
        }])


class _FakeClient:
    def __init__(
        self,
        *,
        missing_lifecycle: bool = False,
        duplicate_status: bool = False,
        duplicate_calendar: bool = False,
        invalid_pretrade: bool = False,
        invalid_taxonomy_level: bool = False,
        invalid_membership_binding: bool = False,
        duplicate_membership: bool = False,
        duplicate_daily: bool = False,
        invalid_daily_numeric: bool = False,
        transient_failures: int = 0,
        provider_error: Exception | None = None,
    ):
        self.calls: list[dict] = []
        self.transient_failures = transient_failures
        self.provider_error = provider_error
        self.config = SimpleNamespace(retry_attempts=3, retry_delay_seconds=0.0)
        self.pro = _FakePro(
            self,
            missing_lifecycle=missing_lifecycle,
            duplicate_status=duplicate_status,
            duplicate_calendar=duplicate_calendar,
            invalid_pretrade=invalid_pretrade,
            invalid_taxonomy_level=invalid_taxonomy_level,
            invalid_membership_binding=invalid_membership_binding,
            duplicate_membership=duplicate_membership,
            duplicate_daily=duplicate_daily,
            invalid_daily_numeric=invalid_daily_numeric,
        )

    def _enforce_rate_limit(self):
        return None


def test_v3_acquisition_plan_writes_bound_partitions_and_omits_noncontract_interfaces(tmp_path: Path):
    from scripts.collect_v3_formal_pit import collect_v3_formal_pit

    client = _FakeClient()
    result = collect_v3_formal_pit(client, output_root=tmp_path / "formal", start_date="20240102", end_date="20240102")

    assert result["status"] == "collected_unqualified"
    root = Path(result["root"])
    manifest = json.loads((root / "acquisition_manifest.json").read_text(encoding="utf-8"))
    assert manifest["template"]["template_id"] == "relative_strength_rotation_shsz_sw2021_v3"
    assert manifest["calendar"]["requested_exchanges"] == ["SSE", "SZSE"]
    assert manifest["membership"]["source"] == "SW2021"
    assert manifest["control_group"]["reference"] == "membership:index_member_all"
    assert manifest["omitted_interfaces"] == {
        "daily_basic": "not consumed by the current v3 direct contract",
        "namechange": "not consumed by the current v3 direct contract",
    }
    assert (root / "stock_basic/list_status=L/part.parquet").exists()
    assert (root / "stock_basic/list_status=D/part.parquet").exists()
    assert (root / "stock_basic/list_status=P/part.parquet").exists()
    assert (root / "membership/index_member_all/l1_code=801010.SI/is_new=Y/part.parquet").exists()
    assert (root / "daily/trade_date=20240102/part.parquet").exists()
    assert (root / "index_daily/ts_code=000300.SH/trade_date=20240102/part.parquet").exists()
    assert (root / "index_daily/ts_code=000905.SH/trade_date=20240102/part.parquet").exists()
    for entry in manifest["partitions"]:
        path = root / entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        metadata_path = root / entry["request_metadata_path"]
        metadata_raw = metadata_path.read_bytes()
        assert metadata_path.exists()
        assert hashlib.sha256(metadata_raw).hexdigest() == entry["request_metadata_sha256"]
        metadata_sidecar = metadata_path.with_name(metadata_path.name + ".sha256")
        assert hashlib.sha256(metadata_raw).hexdigest() == metadata_sidecar.read_text().split()[0]
        metadata = json.loads(metadata_raw)
        assert metadata["provider"] == "tushare.pro"
        assert metadata["request_identity"]["api"]
        assert metadata["request_identity"]["params"]
        assert entry["acquired_at_utc"]

    apis = {call["api"] for call in client.calls}
    assert "daily_basic" not in apis
    assert "namechange" not in apis
    stock_calls = [call for call in client.calls if call["api"] == "stock_basic"]
    assert [call["params"]["list_status"] for call in stock_calls] == ["L", "D", "P"]
    assert {call["params"]["exchange"] for call in stock_calls} == {""}
    calendar_calls = [call for call in client.calls if call["api"] == "trade_cal"]
    assert [call["params"]["exchange"] for call in calendar_calls] == ["SSE", "SZSE"]
    assert all(call["params"]["fields"] == "exchange,cal_date,is_open,pretrade_date" for call in calendar_calls)
    manifest_by_path = {entry["path"]: entry for entry in manifest["partitions"]}
    for status in ("L", "D", "P"):
        entry = manifest_by_path[f"stock_basic/list_status={status}/part.parquet"]
        assert entry["provider"] == "tushare.pro"
        assert entry["request_identity"]["params"]["list_status"] == status
        assert entry["response_status"] == ("success_empty" if status == "P" else "success")


def test_v3_acquisition_rejects_membership_not_closed_by_lifecycle_without_manifest(tmp_path: Path):
    from scripts.collect_v3_formal_pit import collect_v3_formal_pit

    root = tmp_path / "formal"
    with pytest.raises(ValueError, match=r"data_fault: membership symbols missing lifecycle: 000991\.SZ"):
        collect_v3_formal_pit(
            _FakeClient(missing_lifecycle=True),
            output_root=root,
            start_date="20240102",
            end_date="20240102",
        )
    assert not (root / "acquisition_manifest.json").exists()


def test_v3_acquisition_rejects_duplicate_stock_basic_identity_across_statuses(tmp_path: Path):
    from scripts.collect_v3_formal_pit import collect_v3_formal_pit

    with pytest.raises(ValueError, match=r"data_fault: duplicate stock_basic symbol: 000001\.SZ"):
        collect_v3_formal_pit(
            _FakeClient(duplicate_status=True),
            output_root=tmp_path / "formal",
            start_date="20240102",
            end_date="20240102",
        )


def test_v3_acquisition_resume_never_overwrites_existing_partition_without_bound_sidecars(tmp_path: Path):
    from scripts.collect_v3_formal_pit import collect_v3_formal_pit

    root = tmp_path / "formal"
    path = root / "daily/trade_date=20240102/part.parquet"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"pre-existing content")

    client = _FakeClient()
    with pytest.raises(ValueError, match=r"resume conflict: existing partition is not fully bound"):
        collect_v3_formal_pit(
            client,
            output_root=root,
            start_date="20240102",
            end_date="20240102",
        )
    assert path.read_bytes() == b"pre-existing content"
    assert client.calls == []


def test_v3_acquisition_resume_keeps_manifest_identity_stable(tmp_path: Path):
    from scripts.collect_v3_formal_pit import collect_v3_formal_pit

    root = tmp_path / "formal"
    collect_v3_formal_pit(_FakeClient(), output_root=root, start_date="20240102", end_date="20240102")
    before = (root / "acquisition_manifest.json").read_bytes()

    result = collect_v3_formal_pit(_FakeClient(), output_root=root, start_date="20240102", end_date="20240102")

    assert result["manifest_sha256"] == hashlib.sha256(before).hexdigest()
    assert (root / "acquisition_manifest.json").read_bytes() == before


def test_v3_acquisition_rejects_bound_partition_request_identity_drift(tmp_path: Path):
    from scripts.collect_v3_formal_pit import collect_v3_formal_pit

    root = tmp_path / "formal"
    collect_v3_formal_pit(_FakeClient(), output_root=root, start_date="20240102", end_date="20240102")
    metadata_path = root / "daily/trade_date=20240102/part.parquet.request.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["request_identity"]["params"]["trade_date"] = "20240103"
    metadata_raw = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
    metadata_path.write_bytes(metadata_raw)
    metadata_path.with_name(metadata_path.name + ".sha256").write_text(hashlib.sha256(metadata_raw).hexdigest() + "  " + metadata_path.name + "\n")
    partition = root / "daily/trade_date=20240102/part.parquet"
    before = partition.read_bytes()

    with pytest.raises(ValueError, match=r"resume conflict: request identity mismatch"):
        collect_v3_formal_pit(_FakeClient(), output_root=root, start_date="20240102", end_date="20240102")
    assert partition.read_bytes() == before


def test_v3_acquisition_rejects_protected_output_root_before_provider_call(tmp_path: Path):
    from scripts.collect_v3_formal_pit import collect_v3_formal_pit

    repo_root = Path(__file__).parents[1]
    root = repo_root / "data/pit/v3_formal_data_snapshot_manifests" / "candidate-must-not-write"
    client = _FakeClient()

    with pytest.raises(ValueError, match=r"protected output root"):
        collect_v3_formal_pit(client, output_root=root, start_date="20240102", end_date="20240102")

    assert client.calls == []
    assert not root.exists()


def test_v3_acquisition_rejects_link_resolving_into_protected_root(tmp_path: Path):
    from scripts.collect_v3_formal_pit import collect_v3_formal_pit

    repo_root = Path(__file__).parents[1]
    protected = repo_root / "data/pit/v3_formal_data_snapshot_manifests"
    link = tmp_path / "formal-link"
    try:
        os.symlink(protected, link, target_is_directory=True)
    except OSError as error:
        pytest.fail(f"symlink contract could not be exercised: {error}")

    client = _FakeClient()
    with pytest.raises(ValueError, match=r"protected output root"):
        collect_v3_formal_pit(client, output_root=link / "candidate", start_date="20240102", end_date="20240102")
    assert client.calls == []


def test_v3_acquisition_rejects_nonempty_root_without_matching_identity_before_provider_call(tmp_path: Path):
    from scripts.collect_v3_formal_pit import collect_v3_formal_pit

    root = tmp_path / "existing"
    root.mkdir()
    old = root / "old-bytes.bin"
    old.write_bytes(b"preserve me")
    client = _FakeClient()

    with pytest.raises(ValueError, match=r"non-empty.*matching acquisition manifest"):
        collect_v3_formal_pit(client, output_root=root, start_date="20240102", end_date="20240102")
    assert old.read_bytes() == b"preserve me"
    assert client.calls == []


def test_v3_acquisition_resume_reuses_valid_partitions_without_provider_calls(tmp_path: Path):
    from scripts.collect_v3_formal_pit import collect_v3_formal_pit

    root = tmp_path / "resume"
    first_client = _FakeClient()
    first = collect_v3_formal_pit(first_client, output_root=root, start_date="20240102", end_date="20240102")
    manifest_before = (root / "acquisition_manifest.json").read_bytes()

    second_client = _FakeClient()
    second = collect_v3_formal_pit(second_client, output_root=root, start_date="20240102", end_date="20240102")

    assert first_client.calls
    assert second_client.calls == []
    assert second["manifest_sha256"] == first["manifest_sha256"]
    assert (root / "acquisition_manifest.json").read_bytes() == manifest_before


def test_v3_acquisition_rejects_resume_identity_drift_before_provider_call(tmp_path: Path):
    from scripts.collect_v3_formal_pit import collect_v3_formal_pit

    root = tmp_path / "resume-conflict"
    first_client = _FakeClient()
    collect_v3_formal_pit(first_client, output_root=root, start_date="20240102", end_date="20240102")
    manifest_before = (root / "acquisition_manifest.json").read_bytes()
    second_client = _FakeClient()

    with pytest.raises(ValueError, match=r"acquisition identity mismatch"):
        collect_v3_formal_pit(second_client, output_root=root, start_date="20240103", end_date="20240103")
    assert second_client.calls == []
    assert (root / "acquisition_manifest.json").read_bytes() == manifest_before


def test_v3_acquisition_rejects_duplicate_calendar_identity(tmp_path: Path):
    from scripts.collect_v3_formal_pit import collect_v3_formal_pit

    with pytest.raises(ValueError, match=r"data_fault: trade_cal duplicate"):
        collect_v3_formal_pit(_FakeClient(duplicate_calendar=True), output_root=tmp_path / "formal", start_date="20240102", end_date="20240102")


def test_v3_acquisition_rejects_inconsistent_calendar_pretrade_date(tmp_path: Path):
    from scripts.collect_v3_formal_pit import collect_v3_formal_pit

    with pytest.raises(ValueError, match=r"data_fault: trade_cal pretrade_date"):
        collect_v3_formal_pit(_FakeClient(invalid_pretrade=True), output_root=tmp_path / "formal", start_date="20240102", end_date="20240102")


def test_v3_acquisition_rejects_taxonomy_level_mismatch(tmp_path: Path):
    from scripts.collect_v3_formal_pit import collect_v3_formal_pit

    with pytest.raises(ValueError, match=r"data_fault: index_classify level mismatch"):
        collect_v3_formal_pit(_FakeClient(invalid_taxonomy_level=True), output_root=tmp_path / "formal", start_date="20240102", end_date="20240102")


def test_v3_acquisition_rejects_membership_partition_binding_mismatch(tmp_path: Path):
    from scripts.collect_v3_formal_pit import collect_v3_formal_pit

    with pytest.raises(ValueError, match=r"data_fault: membership request binding mismatch"):
        collect_v3_formal_pit(_FakeClient(invalid_membership_binding=True), output_root=tmp_path / "formal", start_date="20240102", end_date="20240102")


def test_v3_acquisition_rejects_cross_partition_membership_duplicate(tmp_path: Path):
    from scripts.collect_v3_formal_pit import collect_v3_formal_pit

    with pytest.raises(ValueError, match=r"data_fault: duplicate membership identity"):
        collect_v3_formal_pit(_FakeClient(duplicate_membership=True), output_root=tmp_path / "formal", start_date="20240102", end_date="20240102")


def test_v3_acquisition_rejects_duplicate_daily_symbol(tmp_path: Path):
    from scripts.collect_v3_formal_pit import collect_v3_formal_pit

    with pytest.raises(ValueError, match=r"data_fault: daily duplicate ts_code"):
        collect_v3_formal_pit(_FakeClient(duplicate_daily=True), output_root=tmp_path / "formal", start_date="20240102", end_date="20240102")


def test_v3_acquisition_rejects_invalid_daily_numeric(tmp_path: Path):
    from scripts.collect_v3_formal_pit import collect_v3_formal_pit

    with pytest.raises(ValueError, match=r"data_fault: daily invalid numeric"):
        collect_v3_formal_pit(_FakeClient(invalid_daily_numeric=True), output_root=tmp_path / "formal", start_date="20240102", end_date="20240102")


def test_v3_provider_retries_only_explicit_transient_failures(tmp_path: Path):
    from scripts.collect_v3_formal_pit import _call

    client = _FakeClient(transient_failures=2)
    frame = _call(client, "trade_cal", fields="exchange,cal_date,is_open,pretrade_date", allow_empty=False, exchange="SSE")

    assert not frame.empty
    assert len(client.calls) == 3


def test_v3_provider_permission_or_parameter_error_fails_fast_as_unverified(tmp_path: Path):
    from scripts.collect_v3_formal_pit import _call

    client = _FakeClient(provider_error=RuntimeError("points or parameter rejected"))
    with pytest.raises(ValueError, match=r"UNVERIFIED_PROVIDER_CODE"):
        _call(client, "trade_cal", fields="exchange,cal_date,is_open,pretrade_date", allow_empty=False, exchange="SSE")
    assert len(client.calls) == 1
