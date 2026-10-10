#!/usr/bin/env python3
"""Independent verifier for the fixed SH/SZ common trade-calendar candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

import pyarrow as pa
import pyarrow.parquet as pq

ARTIFACT_ID = "shsz_common_trade_calendar_v1"
SCHEMA_VERSION = "shsz_common_trade_calendar.v1"
CANDIDATE_REL = "data/pit/.staging/shsz_common_trade_calendar_v1"
FORMAL_REL = "data/pit/shsz_common_trade_calendars/shsz_common_trade_calendar_v1"
POLICY_ID = "stock_st_acceptance_policy_v1_corrective_003"
POLICY_REL = f"data/pit/stock_st_acceptance_policies/{POLICY_ID}/policy.json"
POLICY_SHA256 = "a0ce6f21b0986cec50bffe8884fdc41de0b1d66036a36c56d13fc31c2c8c947d"
B3_ID = "b3eip_traderlens_v2_shsz_pit_001"
B3_ROOT = f"data/pit/b3_execution_input_packages/{B3_ID}"
B3_MANIFEST_REL = f"{B3_ROOT}/manifest.json"
B3_INDEX_REL = f"{B3_ROOT}/input_index.json"
B3_TRADE_CAL_REL = f"{B3_ROOT}/inputs/trade_cal/part.parquet"
B3_TRADE_CAL_SIDECAR_REL = f"{B3_TRADE_CAL_REL}.sha256"
B3_MANIFEST_SHA256 = "ee21303e17b60f81947f40e172031421b88e53d3d79b0fdb95ba6c474a327786"
B3_INDEX_SHA256 = "3b7ca54e7cfad3443f0442215ca38328cfe92dcf1f780d3a85ac65710cacc787"
B3_TRADE_CAL_SHA256 = "28a8587f1962ab268736c41de3e8d8442fbf0f54325475f1cf0b302125575860"
B3_TRADE_CAL_SIDECAR_SHA256 = "7600cd540366a4e5dfd97e6b5df5154fd3507338c3db12f1cff4cb16ed898aa6"
EXPECTED_SZSE_ROWS_SHA256 = "7f7e39de351a69ec640a58c2da0607e50c303492278beec608f2fd535e58f84a"
EXPECTED_SZSE_TOTAL_ROWS = 3844
EXPECTED_SZSE_OPEN_COUNT = 2554
EXPECTED_COMMON_OPEN_COUNT = 2554
EXPECTED_COMMON_FIRST = "20160104"
EXPECTED_COMMON_LAST = "20260710"
EXPECTED_COMMON_SHA256 = "62b6880c9acc381d273ceee40c900a486c3f83488600c042c43ce1d8f9cbb194"
EXPECTED_DIFFERENCE_SHA256 = "4f53cda18c2baa0c0354bb5f4f1f2f6a6f8f3d2f4a1cbbd99f0f3f6a8e1f4c5f"
EXPECTED_FIELDS = ("exchange", "cal_date", "is_open", "pretrade_date")
EXPECTED_SCHEMA = (
    {"name": "exchange", "type": "large_string"},
    {"name": "cal_date", "type": "large_string"},
    {"name": "is_open", "type": "int64"},
    {"name": "pretrade_date", "type": "large_string"},
)
REQUEST = {
    "api_name": "trade_cal",
    "exchange": "SZSE",
    "start_date": "20160101",
    "end_date": "20260710",
    "fields": "exchange,cal_date,is_open,pretrade_date",
}


class VerificationError(ValueError):
    """Stable candidate rejection."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _check_chain(repo_root: Path, path: Path) -> None:
    current = repo_root
    if _is_reparse(current):
        raise VerificationError("repo root reparse")
    try:
        relative = path.relative_to(repo_root)
    except ValueError as exc:
        raise VerificationError("path escape") from exc
    for part in relative.parts:
        current = current / part
        if current.exists() and _is_reparse(current):
            raise VerificationError("candidate path is symlink/junction/reparse")


def _exact_path(repo_root: Path, value: str, formal_mode: bool) -> Path:
    expected = FORMAL_REL if formal_mode else CANDIDATE_REL
    if not isinstance(value, str) or value != expected:
        raise VerificationError("formal path must be exact fixed relative path" if formal_mode else "candidate path must be exact fixed relative path")
    if PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute() or ".." in PurePosixPath(value).parts or "\\" in value:
        raise VerificationError("unsafe candidate path")
    path = repo_root / Path(*value.split("/"))
    _check_chain(repo_root, path)
    return path


def _read_sidecar(path: Path, expected: str) -> None:
    sidecar = path.with_name(path.name + ".sha256")
    if not path.is_file() or _is_reparse(path) or not sidecar.is_file() or _is_reparse(sidecar):
        raise VerificationError("missing or unsafe sidecar")
    if sidecar.read_text(encoding="ascii") != expected:
        raise VerificationError("sidecar content mismatch")


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError("invalid trust JSON") from exc
    if not isinstance(value, dict):
        raise VerificationError("trust JSON must be object")
    return value


def _valid_date(value: object) -> bool:
    if not isinstance(value, str) or re.fullmatch(r"\d{8}", value) is None:
        return False
    try:
        datetime.strptime(value, "%Y%m%d")
        return True
    except ValueError:
        return False


def _load_trust(repo_root: Path) -> tuple[dict, set[str], dict]:
    policy_path = repo_root / Path(*POLICY_REL.split("/"))
    if not policy_path.is_file() or _is_reparse(policy_path) or _sha_file(policy_path) != POLICY_SHA256:
        raise VerificationError("policy trust root mismatch")
    _read_sidecar(policy_path, POLICY_SHA256)
    policy = _read_json(policy_path)
    if policy.get("policy_id") != POLICY_ID:
        raise VerificationError("policy identity mismatch")
    calendar = policy.get("calendar_bindings")
    if not isinstance(calendar, dict) or calendar.get("exchange") != "SSE" or calendar.get("expected_dates") != 2554 or calendar.get("first_date") != "20160104" or calendar.get("last_date") != "20260710" or calendar.get("canonical_date_set_sha256") != EXPECTED_COMMON_SHA256:
        raise VerificationError("policy calendar binding mismatch")
    for relative, expected in ((B3_MANIFEST_REL, B3_MANIFEST_SHA256), (B3_INDEX_REL, B3_INDEX_SHA256), (B3_TRADE_CAL_REL, B3_TRADE_CAL_SHA256), (B3_TRADE_CAL_SIDECAR_REL, B3_TRADE_CAL_SIDECAR_SHA256)):
        path = repo_root / Path(*relative.split("/"))
        if not path.is_file() or _is_reparse(path) or _sha_file(path) != expected:
            raise VerificationError("B3 trust root mismatch")
    trade_cal = repo_root / Path(*B3_TRADE_CAL_REL.split("/"))
    _read_sidecar(trade_cal, B3_TRADE_CAL_SHA256)
    index = _read_json(repo_root / Path(*B3_INDEX_REL.split("/")))
    entries = index.get("interfaces", {}).get("trade_cal", {}).get("entries", [])
    entry_map = {entry.get("path"): entry for entry in entries if isinstance(entry, dict)}
    for relative, expected in ((B3_TRADE_CAL_REL, B3_TRADE_CAL_SHA256), (B3_TRADE_CAL_SIDECAR_REL, B3_TRADE_CAL_SIDECAR_SHA256)):
        if entry_map.get(relative, {}).get("sha256") != expected:
            raise VerificationError("B3 calendar entry mismatch")
    table = pq.read_table(trade_cal)
    rows = table.to_pylist()
    sse_open = {row.get("cal_date") for row in rows if row.get("exchange") == "SSE" and row.get("is_open") == 1}
    if len(sse_open) != 2554 or _sha_bytes(_canonical(sorted(sse_open))) != EXPECTED_COMMON_SHA256:
        raise VerificationError("SSE calendar binding mismatch")
    binding = {
        "policy": {"path": POLICY_REL, "sha256": POLICY_SHA256, "policy_id": POLICY_ID, "calendar_binding": calendar},
        "b3": {"artifact_id": B3_ID, "manifest_path": B3_MANIFEST_REL, "manifest_sha256": B3_MANIFEST_SHA256, "input_index_path": B3_INDEX_REL, "input_index_sha256": B3_INDEX_SHA256, "trade_cal_path": B3_TRADE_CAL_REL, "trade_cal_sha256": B3_TRADE_CAL_SHA256, "trade_cal_sidecar_path": B3_TRADE_CAL_SIDECAR_REL, "trade_cal_sidecar_sha256": B3_TRADE_CAL_SIDECAR_SHA256},
    }
    return policy, sse_open, binding


def _rows_from_table(table: pa.Table) -> list[dict]:
    expected_schema = pa.schema([pa.field("exchange", pa.large_string()), pa.field("cal_date", pa.large_string()), pa.field("is_open", pa.int64()), pa.field("pretrade_date", pa.large_string())])
    if not table.schema.remove_metadata().equals(expected_schema):
        raise VerificationError("parquet schema")
    rows = table.to_pylist()
    seen: set[str] = set()
    normalized = []
    for row in rows:
        if set(row) != set(EXPECTED_FIELDS):
            raise VerificationError("parquet columns")
        if row["exchange"] != "SZSE":
            raise VerificationError("exchange")
        if not _valid_date(row["cal_date"]) or not ("20160101" <= row["cal_date"] <= "20260710"):
            raise VerificationError("cal_date")
        if row["cal_date"] in seen:
            raise VerificationError("duplicate cal_date")
        seen.add(row["cal_date"])
        if isinstance(row["is_open"], bool) or type(row["is_open"]) is not int or row["is_open"] not in (0, 1):
            raise VerificationError("is_open")
        if not _valid_date(row["pretrade_date"]):
            raise VerificationError("pretrade_date")
        normalized.append({key: row[key] for key in EXPECTED_FIELDS})
    return sorted(normalized, key=lambda row: row["cal_date"])


def verify_candidate(repo_root: Path, artifact_root: str = CANDIDATE_REL, formal_mode: bool = False) -> dict:
    repo_root = Path(repo_root).resolve(strict=True)
    candidate = _exact_path(repo_root, artifact_root, formal_mode)
    formal = repo_root / Path(*FORMAL_REL.split("/"))
    if not formal_mode and (formal.exists() or _is_reparse(formal)):
        raise VerificationError("formal guard exists")
    if not candidate.is_dir() or _is_reparse(candidate):
        raise VerificationError("candidate missing or unsafe")
    actual = {entry.name for entry in candidate.iterdir()}
    expected_files = {"szse_trade_cal.parquet", "szse_trade_cal.parquet.sha256", "manifest.json", "manifest.json.sha256"}
    if actual != expected_files:
        raise VerificationError("candidate inventory mismatch")
    for entry in candidate.iterdir():
        if _is_reparse(entry) or not entry.is_file():
            raise VerificationError("candidate inventory unsafe")
    parquet_path = candidate / "szse_trade_cal.parquet"
    manifest_path = candidate / "manifest.json"
    parquet_sha = _sha_file(parquet_path)
    manifest_sha = _sha_file(manifest_path)
    _read_sidecar(parquet_path, parquet_sha)
    _read_sidecar(manifest_path, manifest_sha)
    manifest = _read_json(manifest_path)
    expected_manifest_keys = {"artifact_id", "schema_version", "frozen", "request", "parquet", "canonical_rows", "trust_bindings", "comparison"}
    if set(manifest) != expected_manifest_keys:
        raise VerificationError("manifest schema")
    if manifest["artifact_id"] != ARTIFACT_ID or manifest["schema_version"] != SCHEMA_VERSION or manifest["frozen"] is not True or manifest["request"] != REQUEST:
        raise VerificationError("manifest identity")
    _policy, sse_open, binding = _load_trust(repo_root)
    if manifest["trust_bindings"] != binding:
        raise VerificationError("manifest trust binding")
    rows = _rows_from_table(pq.read_table(parquet_path))
    canonical_sha = _sha_bytes(_canonical(rows))
    if canonical_sha != EXPECTED_SZSE_ROWS_SHA256:
        raise VerificationError("canonical rows hash mismatch")
    open_dates = {row["cal_date"] for row in rows if row["is_open"] == 1}
    common = sorted(open_dates & sse_open)
    sse_only = sorted(sse_open - open_dates)
    szse_only = sorted(open_dates - sse_open)
    differences_sha = _sha_bytes(_canonical({"sse_only": sse_only, "szse_only": szse_only}))
    parquet_decl = manifest["parquet"]
    if set(parquet_decl) != {"path", "sha256", "byte_size", "schema"} or parquet_decl["path"] != "szse_trade_cal.parquet" or parquet_decl["sha256"] != parquet_sha or type(parquet_decl["byte_size"]) is not int or parquet_decl["byte_size"] != parquet_path.stat().st_size or parquet_decl["schema"] != list(EXPECTED_SCHEMA):
        raise VerificationError("manifest parquet binding")
    canonical_decl = manifest["canonical_rows"]
    if set(canonical_decl) != {"algorithm_id", "sort_by", "json", "sha256", "row_count", "open_count"} or canonical_decl["algorithm_id"] != "sha256_sorted_szse_trade_cal_rows_v1" or canonical_decl["sort_by"] != ["cal_date"] or canonical_decl["json"] != {"encoding": "utf-8", "ensure_ascii": False, "separators": [",", ":"], "sort_keys": True} or canonical_decl["sha256"] != canonical_sha or type(canonical_decl["row_count"]) is not int or type(canonical_decl["open_count"]) is not int or canonical_decl["row_count"] != len(rows) or canonical_decl["open_count"] != len(open_dates):
        raise VerificationError("manifest canonical binding")
    comparison = manifest["comparison"]
    expected_comparison_keys = {"sse_open_count", "szse_total_rows", "szse_open_count", "common_open_count", "sse_only_open_count", "szse_only_open_count", "common_first_date", "common_last_date", "common_open_dates_sha256", "difference_dates_sha256"}
    if set(comparison) != expected_comparison_keys:
        raise VerificationError("manifest comparison schema")
    expected_comparison = {"sse_open_count": len(sse_open), "szse_total_rows": len(rows), "szse_open_count": len(open_dates), "common_open_count": len(common), "sse_only_open_count": len(sse_only), "szse_only_open_count": len(szse_only), "common_first_date": common[0] if common else None, "common_last_date": common[-1] if common else None, "common_open_dates_sha256": _sha_bytes(_canonical(common)), "difference_dates_sha256": differences_sha}
    if comparison != expected_comparison:
        raise VerificationError("manifest comparison binding")
    if len(rows) != EXPECTED_SZSE_TOTAL_ROWS or len(open_dates) != EXPECTED_SZSE_OPEN_COUNT or len(common) != EXPECTED_COMMON_OPEN_COUNT or (common[0], common[-1]) != (EXPECTED_COMMON_FIRST, EXPECTED_COMMON_LAST) or _sha_bytes(_canonical(common)) != EXPECTED_COMMON_SHA256 or sse_only or szse_only:
        raise VerificationError("common calendar mismatch")
    return manifest


class _RejectingParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise VerificationError("verification error")


def main(argv: list[str] | None = None) -> int:
    parser = _RejectingParser(add_help=False)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--artifact-root", default=CANDIDATE_REL)
    parser.add_argument("--formal-mode", action="store_true")
    try:
        args = parser.parse_args(argv)
        verify_candidate(Path(args.repo_root), args.artifact_root, args.formal_mode)
    except VerificationError as exc:
        print(f"REJECTED: {exc}")
        return 1
    except BaseException:
        print("REJECTED: verification error")
        return 1
    print(f"ACCEPTED: {ARTIFACT_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
