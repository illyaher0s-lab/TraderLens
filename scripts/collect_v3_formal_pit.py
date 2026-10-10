"""Collect the v3 formal PIT inputs into an unqualified, resumable root.

This module is deliberately narrower than the legacy Gate0 feasibility script.
It has no default production output path and does not publish or qualify any
artifact.  The CLI is an explicit acquisition entry point for a later,
separately authorized Tushare run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_client import TushareClient


SCHEMA_VERSION = "v3_formal_acquisition_manifest.v1"
ACQUISITION_ID_VERSION = "v3_formal_acquisition_identity.v1"
REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = {
    "template_id": "relative_strength_rotation_shsz_sw2021_v3",
    "template_version": "v3_shsz_sw2021_pit_12m_liquidity20d",
    "template_hash": "f7c0fd8123f62f37118cb947e1735861374435f8707e01b06d788a8ec4df39c1",
    "data_requirements_hash": "ef2ab5b1dafe4349f305b52733a7dcb018a2961464dfbc6542a10e34805d041d",
}
STRATEGY_REVISION_ID = "6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc"
BENCHMARKS = ("000300.SH", "000905.SH")
EXCHANGES = ("SSE", "SZSE")

# These roots already contain frozen, published, or production-consumed
# artifacts.  A collector candidate may never be written below them.  A
# caller may use a new run directory under the staging parent, but never the
# existing formal child.
PROTECTED_OUTPUT_ROOTS = tuple(
    REPO_ROOT / Path(*relative.split("/"))
    for relative in (
        "data/pit/v3_formal_data_snapshot_manifests",
        "data/pit/b3_execution_input_packages",
        "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal",
        "data/pit/v3_b4_is_results",
        "data/pit/v3_b5_source_inventories",
        "data/pit/v3_b5_ledger_observations",
        "data/pit/v3_b5_costs",
        "data/pit/v3_b5_comparisons",
        "data/pit/v3_b5_validation_bundles",
        "data/pit/v3_execution_semantics_supplements",
        "data/pit/v3_historical_coverage_packages",
        "data/pit/v3_historical_suspension_evidence",
        "data/pit/v3_availability_bounded_qualification_successors",
        "data/pit/qualification_successors",
        "data/pit/pit_membership_snapshots",
        "data/pit/historical_scope_freezes",
        "data/pit/formal_packages",
        "data/pit/data_snapshot_manifests",
        "data/pit/coverage_packages",
        "data/pit/stock_st_acceptance_policies",
        "data/pit/stock_st_reconciled_acceptances",
    )
)

FIELDS = {
    "trade_cal": "exchange,cal_date,is_open,pretrade_date",
    "stock_basic": "ts_code,symbol,name,market,exchange,list_status,list_date,delist_date",
    "index_classify": "index_code,industry_name,level,is_pub",
    "index_member_all": "ts_code,l1_code,l1_name,in_date,out_date,is_new",
    "daily": "ts_code,trade_date,open,high,low,close,vol,amount",
    "adj_factor": "ts_code,trade_date,adj_factor",
    "stk_limit": "ts_code,trade_date,up_limit,down_limit",
    "stock_st": "ts_code,name,trade_date,type,type_name",
    "suspend_d": "ts_code,trade_date,suspend_timing,suspend_type",
    "index_daily": "ts_code,trade_date,close,vol,amount",
}
REQUIRED_COLUMNS = {
    "trade_cal": ("exchange", "cal_date", "is_open", "pretrade_date"),
    "stock_basic": ("ts_code", "symbol", "name", "market", "exchange", "list_status", "list_date", "delist_date"),
    "index_classify": ("index_code", "industry_name", "level", "is_pub"),
    "index_member_all": ("ts_code", "l1_code", "l1_name", "in_date", "out_date", "is_new"),
    "daily": ("ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"),
    "adj_factor": ("ts_code", "trade_date", "adj_factor"),
    "stk_limit": ("ts_code", "trade_date", "up_limit", "down_limit"),
    "stock_st": ("ts_code", "name", "trade_date", "type", "type_name"),
    "suspend_d": ("ts_code", "trade_date", "suspend_timing", "suspend_type"),
    "index_daily": ("ts_code", "trade_date", "close", "vol", "amount"),
}
OMITTED_INTERFACES = {
    "daily_basic": "not consumed by the current v3 direct contract",
    "namechange": "not consumed by the current v3 direct contract",
}


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sidecar(path: Path) -> Path:
    return path.with_name(path.name + ".sha256")


def _request_metadata(path: Path) -> Path:
    return path.with_name(path.name + ".request.json")


def _request_metadata_sidecar(path: Path) -> Path:
    return _sidecar(_request_metadata(path))


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _acquisition_identity(start_date: str, end_date: str) -> str:
    return _sha_bytes(_canonical({
        "identity_version": ACQUISITION_ID_VERSION,
        "schema_version": SCHEMA_VERSION,
        "template": TEMPLATE,
        "strategy_revision_id": STRATEGY_REVISION_ID,
        "requested_start": start_date,
        "requested_end": end_date,
        "exchanges": list(EXCHANGES),
        "benchmarks": list(BENCHMARKS),
        "fields": FIELDS,
        "omitted_interfaces": OMITTED_INTERFACES,
    }))


def _resolved_output_root(output_root: Path) -> Path:
    candidate = Path(output_root)
    if candidate.exists() and candidate.is_symlink():
        resolved = candidate.resolve(strict=False)
    else:
        resolved = candidate.resolve(strict=False)
    for protected in PROTECTED_OUTPUT_ROOTS:
        protected_resolved = protected.resolve(strict=False)
        if resolved == protected_resolved or protected_resolved in resolved.parents:
            raise ValueError(f"protected output root: {resolved}")
    if candidate.exists() and not candidate.is_dir():
        raise ValueError(f"invalid output root: {resolved}")
    return resolved


def _prepare_output_root(output_root: Path, *, start_date: str, end_date: str) -> Path:
    root = _resolved_output_root(output_root)
    manifest_path = root / "acquisition_manifest.json"
    manifest_sidecar = _sidecar(manifest_path)
    identity = _acquisition_identity(start_date, end_date)
    if root.exists():
        entries = list(root.iterdir())
        if manifest_path.exists() or manifest_sidecar.exists():
            if not manifest_path.exists() or not manifest_sidecar.exists():
                raise ValueError("resume conflict: acquisition manifest is incomplete")
            raw = manifest_path.read_bytes()
            declared = manifest_sidecar.read_text(encoding="ascii").strip().split()[0]
            if _sha_bytes(raw) != declared:
                raise ValueError("resume conflict: acquisition manifest hash mismatch")
            try:
                manifest = json.loads(raw.decode("utf-8"))
            except Exception as error:
                raise ValueError("resume conflict: acquisition manifest is unreadable") from error
            if manifest.get("acquisition_identity") != identity:
                raise ValueError("resume conflict: acquisition identity mismatch")
            if manifest.get("status") != "collected_unqualified" or manifest.get("frozen") is not False:
                raise ValueError("resume conflict: acquisition manifest status mismatch")
        elif entries:
            raise ValueError(
                "resume conflict: output root is non-empty without matching acquisition manifest; "
                "existing partition is not fully bound"
            )
    else:
        root.mkdir(parents=True, exist_ok=True)
    return root


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f"write-once conflict: {path}")
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".partial", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def _land_partition(root: Path, relative_path: str, frame: pd.DataFrame, request: dict) -> dict:
    path = root / Path(*relative_path.split("/"))
    digest_path = _sidecar(path)
    metadata_path = _request_metadata(path)
    metadata_digest_path = _request_metadata_sidecar(path)
    related = (path, digest_path, metadata_path, metadata_digest_path)
    if any(item.exists() for item in related):
        if not all(item.exists() for item in related):
            raise ValueError(f"resume conflict: existing partition is not fully bound: {path}")
        actual_digest = _sha_file(path)
        declared_digest = digest_path.read_text(encoding="ascii").strip().split()[0]
        if actual_digest != declared_digest:
            raise ValueError(f"resume conflict: partition hash mismatch: {path}")
        metadata_raw = metadata_path.read_bytes()
        if _sha_bytes(metadata_raw) != metadata_digest_path.read_text(encoding="ascii").strip().split()[0]:
            raise ValueError(f"resume conflict: request metadata hash mismatch: {path}")
        metadata = json.loads(metadata_raw.decode("utf-8"))
        if metadata.get("request_identity") != request:
            raise ValueError(f"resume conflict: request identity mismatch: {path}")
        if metadata.get("response_sha256") != actual_digest:
            raise ValueError(f"resume conflict: response hash binding mismatch: {path}")
        return {
            "path": relative_path,
            "sha256": actual_digest,
            "byte_size": path.stat().st_size,
            "request_metadata_path": metadata_path.relative_to(root).as_posix(),
            "request_metadata_sha256": _sha_bytes(metadata_raw),
            "acquired_at_utc": metadata["acquired_at_utc"],
        }

    partial = path.with_name(path.name + ".partial")
    if partial.exists():
        raise ValueError(f"resume conflict: unfinished partition exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(partial, index=False, engine="pyarrow")
    os.replace(partial, path)
    response_digest = _sha_file(path)
    acquired_at = _now_utc()
    metadata = {
        "schema_version": "v3_formal_acquisition_partition.v1",
        "provider": "tushare.pro",
        "request_identity": request,
        "response_sha256": response_digest,
        "row_count": int(len(frame)),
        "byte_size": path.stat().st_size,
        "acquired_at_utc": acquired_at,
        "path": relative_path,
    }
    metadata_raw = _canonical(metadata)
    _write_bytes_atomic(digest_path, f"{response_digest}  {path.name}\n".encode("ascii"))
    _write_bytes_atomic(metadata_path, metadata_raw)
    _write_bytes_atomic(metadata_digest_path, f"{_sha_bytes(metadata_raw)}  {metadata_path.name}\n".encode("ascii"))
    return {
        "path": relative_path,
        "sha256": response_digest,
        "byte_size": path.stat().st_size,
        "request_metadata_path": metadata_path.relative_to(root).as_posix(),
        "request_metadata_sha256": _sha_bytes(metadata_raw),
        "acquired_at_utc": acquired_at,
    }


def _call(client: Any, api: str, *, fields: str, allow_empty: bool, **params: Any) -> pd.DataFrame:
    config = getattr(client, "config", None)
    attempts = max(1, int(getattr(config, "retry_attempts", 1)))
    delay = float(getattr(config, "retry_delay_seconds", 0.0))
    request = dict(params)
    request["fields"] = fields
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            enforce = getattr(client, "_enforce_rate_limit", None)
            if enforce is not None:
                enforce()
            frame = getattr(client.pro, api)(**request)
            if frame is None:
                raise ValueError(f"{api} returned None")
            if not isinstance(frame, pd.DataFrame):
                frame = pd.DataFrame(frame)
            if frame.empty and not allow_empty:
                raise ValueError(f"{api} returned an empty required response")
            return frame
        except Exception as error:
            last_error = error
            if attempt < attempts - 1 and delay:
                time.sleep(delay * (2**attempt))
    raise ValueError(f"v3 acquisition API failed: {api}; error={last_error}") from last_error


def _validate_columns(api: str, frame: pd.DataFrame) -> None:
    missing = [field for field in REQUIRED_COLUMNS[api] if field not in frame.columns]
    if missing:
        raise ValueError(f"data_fault: {api} missing required fields: {','.join(missing)}")


def _validate_trade_cal(frame: pd.DataFrame, exchange: str, start_date: str, end_date: str) -> set[str]:
    _validate_columns("trade_cal", frame)
    if frame.empty:
        raise ValueError(f"data_fault: trade_cal empty for {exchange}")
    if set(frame["exchange"].astype(str)) != {exchange}:
        raise ValueError(f"data_fault: trade_cal exchange mismatch for {exchange}")
    dates = set(frame["cal_date"].astype(str))
    if any(len(value) != 8 or not value.isdigit() or value < start_date or value > end_date for value in dates):
        raise ValueError(f"data_fault: trade_cal date outside requested scope for {exchange}")
    if not set(frame["is_open"].astype(int)).issubset({0, 1}):
        raise ValueError(f"data_fault: trade_cal is_open value invalid for {exchange}")
    return {value for value in dates if int(frame.loc[frame["cal_date"].astype(str) == value, "is_open"].iloc[0]) == 1}


def _validate_trade_date(api: str, frame: pd.DataFrame, trade_date: str, *, allow_empty: bool) -> None:
    _validate_columns(api, frame)
    if frame.empty and allow_empty:
        return
    if frame.empty:
        raise ValueError(f"data_fault: {api} empty for {trade_date}")
    if set(frame["trade_date"].astype(str)) != {trade_date}:
        raise ValueError(f"data_fault: {api} date mismatch for {trade_date}")


def _validate_stock_basic(status: str, frame: pd.DataFrame) -> set[str]:
    _validate_columns("stock_basic", frame)
    if status in {"L", "D"} and frame.empty:
        raise ValueError(f"data_fault: stock_basic {status} is empty")
    if frame.empty:
        return set()
    if set(frame["list_status"].astype(str)) != {status}:
        raise ValueError(f"data_fault: stock_basic status mismatch for {status}")
    symbols = frame["ts_code"].astype(str).tolist()
    if len(symbols) != len(set(symbols)):
        raise ValueError(f"data_fault: duplicate stock_basic symbol within {status}")
    return set(symbols)


def _validate_membership_frame(frame: pd.DataFrame) -> set[str]:
    _validate_columns("index_member_all", frame)
    if frame.empty:
        return set()
    identities: set[tuple] = set()
    symbols: set[str] = set()
    for row in frame.to_dict("records"):
        symbol = str(row["ts_code"])
        start = str(row["in_date"])
        end = None if pd.isna(row["out_date"]) or row["out_date"] in (None, "") else str(row["out_date"])
        if len(start) != 8 or not start.isdigit() or (end is not None and (len(end) != 8 or not end.isdigit() or end < start)):
            raise ValueError(f"data_fault: invalid membership interval: {symbol}")
        identity = (symbol, start, end, str(row["l1_code"]), str(row["is_new"]))
        if identity in identities:
            raise ValueError(f"data_fault: duplicate membership identity: {identity}")
        identities.add(identity)
        symbols.add(symbol)
    return symbols


def _manifest_write(root: Path, payload: dict) -> tuple[str, str]:
    manifest_path = root / "acquisition_manifest.json"
    raw = _canonical(payload)
    if manifest_path.exists() or _sidecar(manifest_path).exists():
        if not manifest_path.exists() or not _sidecar(manifest_path).exists():
            raise ValueError("write-once conflict: acquisition manifest is incomplete")
        if manifest_path.read_bytes() != raw or _sidecar(manifest_path).read_text(encoding="ascii").split()[0] != _sha_bytes(raw):
            raise ValueError("write-once conflict: acquisition manifest differs")
        return str(manifest_path), _sha_bytes(raw)
    _write_bytes_atomic(manifest_path, raw)
    _write_bytes_atomic(_sidecar(manifest_path), f"{_sha_bytes(raw)}  {manifest_path.name}\n".encode("ascii"))
    return str(manifest_path), _sha_bytes(raw)


def collect_v3_formal_pit(
    client: Any,
    *,
    output_root: Path,
    start_date: str,
    end_date: str,
) -> dict:
    """Collect exact v3 formal inputs without publishing or qualifying them."""
    if any(len(value) != 8 or not value.isdigit() for value in (start_date, end_date)) or start_date > end_date:
        raise ValueError("invalid acquisition date range")
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    partitions: list[dict] = []

    calendar_frames = []
    open_dates: dict[str, set[str]] = {}
    for exchange in EXCHANGES:
        frame = _call(
            client,
            "trade_cal",
            fields=FIELDS["trade_cal"],
            allow_empty=False,
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
        )
        open_dates[exchange] = _validate_trade_cal(frame, exchange, start_date, end_date)
        calendar_frames.append(frame)
    calendar = pd.concat(calendar_frames, ignore_index=True).sort_values(["cal_date", "exchange"]).reset_index(drop=True)
    common_dates = sorted(open_dates["SSE"] & open_dates["SZSE"])
    if not common_dates:
        raise ValueError("data_fault: no SH/SZ common open trading dates")
    partitions.append(_land_partition(
        root,
        "trade_cal/part.parquet",
        calendar,
        {"api": "trade_cal", "fields": FIELDS["trade_cal"], "params": {"exchanges": list(EXCHANGES), "start_date": start_date, "end_date": end_date}},
    ))

    lifecycle_symbols: set[str] = set()
    for status in ("L", "D", "P"):
        frame = _call(
            client,
            "stock_basic",
            fields=FIELDS["stock_basic"],
            allow_empty=status == "P",
            exchange="",
            list_status=status,
        )
        symbols = _validate_stock_basic(status, frame)
        duplicate = lifecycle_symbols & symbols
        if duplicate:
            raise ValueError(f"data_fault: duplicate stock_basic symbol: {sorted(duplicate)[0]}")
        lifecycle_symbols.update(symbols)
        partitions.append(_land_partition(
            root,
            f"stock_basic/list_status={status}/part.parquet",
            frame,
            {"api": "stock_basic", "fields": FIELDS["stock_basic"], "params": {"exchange": "", "list_status": status}},
        ))

    taxonomy = _call(
        client,
        "index_classify",
        fields=FIELDS["index_classify"],
        allow_empty=False,
        level="L1",
        src="SW2021",
    )
    _validate_columns("index_classify", taxonomy)
    if taxonomy.empty:
        raise ValueError("data_fault: SW2021 index_classify is empty")
    l1_codes = sorted({(str(row["index_code"]), str(row["industry_name"])) for row in taxonomy.to_dict("records")})
    partitions.append(_land_partition(
        root,
        "membership/index_classify/part.parquet",
        taxonomy,
        {"api": "index_classify", "fields": FIELDS["index_classify"], "params": {"level": "L1", "src": "SW2021"}},
    ))
    membership_symbols: set[str] = set()
    for l1_code, _l1_name in l1_codes:
        for is_new in ("Y", "N"):
            frame = _call(
                client,
                "index_member_all",
                fields=FIELDS["index_member_all"],
                allow_empty=True,
                l1_code=l1_code,
                is_new=is_new,
            )
            membership_symbols.update(_validate_membership_frame(frame))
            partitions.append(_land_partition(
                root,
                f"membership/index_member_all/l1_code={l1_code}/is_new={is_new}/part.parquet",
                frame,
                {"api": "index_member_all", "fields": FIELDS["index_member_all"], "params": {"l1_code": l1_code, "is_new": is_new}},
            ))
    if not membership_symbols:
        raise ValueError("data_fault: SW2021 membership is empty")
    missing_lifecycle = sorted(membership_symbols - lifecycle_symbols)
    if missing_lifecycle:
        raise ValueError(f"data_fault: membership symbols missing lifecycle: {','.join(missing_lifecycle)}")

    for trade_date in common_dates:
        for api in ("daily", "adj_factor", "stk_limit", "stock_st", "suspend_d"):
            allow_empty = api in {"stock_st", "suspend_d"}
            frame = _call(client, api, fields=FIELDS[api], allow_empty=allow_empty, trade_date=trade_date)
            _validate_trade_date(api, frame, trade_date, allow_empty=allow_empty)
            partitions.append(_land_partition(
                root,
                f"{api}/trade_date={trade_date}/part.parquet",
                frame,
                {"api": api, "fields": FIELDS[api], "params": {"trade_date": trade_date}},
            ))
        for benchmark in BENCHMARKS:
            frame = _call(
                client,
                "index_daily",
                fields=FIELDS["index_daily"],
                allow_empty=False,
                ts_code=benchmark,
                trade_date=trade_date,
            )
            _validate_trade_date("index_daily", frame, trade_date, allow_empty=False)
            if set(frame["ts_code"].astype(str)) != {benchmark}:
                raise ValueError(f"data_fault: index_daily benchmark mismatch for {benchmark} {trade_date}")
            partitions.append(_land_partition(
                root,
                f"index_daily/ts_code={benchmark}/trade_date={trade_date}/part.parquet",
                frame,
                {"api": "index_daily", "fields": FIELDS["index_daily"], "params": {"ts_code": benchmark, "trade_date": trade_date}},
            ))

    partitions = sorted(partitions, key=lambda item: item["path"])
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "collected_unqualified",
        "frozen": False,
        "provider": "tushare.pro",
        "template": dict(TEMPLATE),
        "strategy_revision_id": STRATEGY_REVISION_ID,
        "scope": {"requested_start": start_date, "requested_end": end_date, "common_open_dates": common_dates},
        "calendar": {"requested_exchanges": list(EXCHANGES), "partition": "trade_cal/part.parquet", "common_rule": "intersection of SSE and SZSE is_open=1"},
        "lifecycle": {"partition_root": "stock_basic", "statuses": ["L", "D", "P"], "symbol_count": len(lifecycle_symbols), "lifecycle_symbols": sorted(lifecycle_symbols)},
        "membership": {"source": "SW2021", "partition_root": "membership", "symbol_count": len(membership_symbols), "membership_symbols": sorted(membership_symbols)},
        "control_group": {"type": "same_sw_l1_industry_excluding_self", "reference": "membership:index_member_all", "pit_rule": "in_date <= as_of_date and (out_date is null or out_date >= as_of_date)"},
        "benchmarks": list(BENCHMARKS),
        "omitted_interfaces": dict(OMITTED_INTERFACES),
        "partitions": partitions,
        "acquisition_timestamps_utc": sorted({item["acquired_at_utc"] for item in partitions}),
        "not_authorized_for_b6_oos_gate_promotion_signal": True,
    }
    manifest_path, manifest_sha256 = _manifest_write(root, payload)
    return {
        "status": "collected_unqualified",
        "root": str(root),
        "manifest_path": manifest_path,
        "manifest_sha256": manifest_sha256,
        "partition_count": len(partitions),
        "common_date_count": len(common_dates),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect v3 formal PIT inputs into an explicit unqualified root")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--start-date", required=True, help="YYYYMMDD")
    parser.add_argument("--end-date", required=True, help="YYYYMMDD")
    args = parser.parse_args(argv)
    config = TushareConfig.from_env()
    config.requests_per_minute = 160
    client = TushareClient(config)
    result = collect_v3_formal_pit(client, output_root=args.output_root, start_date=args.start_date, end_date=args.end_date)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
