#!/usr/bin/env python3
"""Verify Stock ST Acceptance Policy V1 Corrective 003."""
from __future__ import annotations
import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path, PurePosixPath
import pyarrow.parquet as pq

EXPECTED_POLICY_SHA256 = "a0ce6f21b0986cec50bffe8884fdc41de0b1d66036a36c56d13fc31c2c8c947d"
EXPECTED_RAW_CAPTURE_SHA256 = "59e27468afb9e71f6e0f812c567e86538da0f1bb4b8bc781318c8e25bb0517e6"
EXPECTED_B3_MANIFEST_SHA256 = "ee21303e17b60f81947f40e172031421b88e53d3d79b0fdb95ba6c474a327786"
EXPECTED_B3_INPUT_INDEX_SHA256 = "3b7ca54e7cfad3443f0442215ca38328cfe92dcf1f780d3a85ac65710cacc787"
EXPECTED_STOCK_ST_INTERFACE_HASH = "b9db559909524a484d75d8cad9b8acf26d93acd9142edf92786f5215e48e00bb"
EXPECTED_TRADE_CAL_INTERFACE_HASH = "859484d6e1d0bfa06921b1b9c43334aa64c11569bae46a775df3bd713910b05c"
EXPECTED_TRADE_CAL_PARQUET_SHA256 = "28a8587f1962ab268736c41de3e8d8442fbf0f54325475f1cf0b302125575860"
EXPECTED_TRADE_CAL_SIDECAR_SHA256 = "7600cd540366a4e5dfd97e6b5df5154fd3507338c3db12f1cff4cb16ed898aa6"
EXPECTED_DATE_SET_SHA256 = "62b6880c9acc381d273ceee40c900a486c3f83488600c042c43ce1d8f9cbb194"
EXPECTED_LEGACY_RECONCILER_SHA256 = "c06c494ebca3c6682b2d048147e82294c9ef55c9abc6edd1b850103454fc6ce5"
EXPECTED_FILES = {
    "contract_evidence.json",
    "contract_evidence.json.sha256",
    "policy.json",
    "policy.json.sha256",
    "tushare_doc_397_raw_capture.html",
    "tushare_doc_397_raw_capture.html.sha256",
}
EXPECTED_LEGACY_IDS = [
    "stacc_traderlens_v2_shsz_stock_st_001",
    "stacc_traderlens_v2_shsz_stock_st_002",
    "stacc_traderlens_v2_shsz_stock_st_003",
    "stock_st_acceptance_policy_v1",
    "stock_st_acceptance_policy_v1_corrective_001",
    "stock_st_acceptance_policy_v1_corrective_002",
]
IMMUTABLE_LEGACY_FORMAL_PUBLICATION_REGISTRY = frozenset(
    {
        "stock_st_acceptance_policy_v1",
        "stock_st_acceptance_policy_v1_corrective_001",
        "stock_st_acceptance_policy_v1_corrective_002",
    }
)
EXPECTED_COLUMNS = ["ts_code", "name", "trade_date", "type", "type_name"]
EXPECTED_B3_PATHS = {
    "manifest_path": "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/manifest.json",
    "input_index_path": "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/input_index.json",
    "trade_cal_path": "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/trade_cal/part.parquet",
    "trade_cal_sidecar_path": "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/trade_cal/part.parquet.sha256",
}
EXPECTED_STOCK_ST_ROOT = "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/stock_st"

class PolicyVerificationError(RuntimeError):
    pass

def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())

def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def canonical_json_hash(value: object) -> str:
    return sha256_bytes(canonical_json_bytes(value))

def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def _fail(message: str) -> None:
    raise PolicyVerificationError(message)

def _is_reparse(path: Path) -> bool:
    # ponytail: Windows reparse check
    metadata = path.lstat()
    return bool(getattr(metadata, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))

def _require_plain_path(path: Path, label: str) -> None:
    if path.is_symlink() or _is_reparse(path):
        _fail(f"{label} is symlink/junction/reparse")

def _registered_path(repo_root: Path, registered: str, label: str) -> Path:
    logical = PurePosixPath(registered)
    if logical.is_absolute() or ".." in logical.parts or ".staging" in logical.parts:
        _fail(f"{label} path escape")
    physical = repo_root.joinpath(*logical.parts)
    cursor = repo_root
    for part in logical.parts:
        cursor /= part
        if not cursor.exists():
            _fail(f"missing {label}: {registered}")
        _require_plain_path(cursor, label)
    try:
        physical.resolve(strict=True).relative_to(repo_root)
    except ValueError:
        _fail(f"{label} path escape")
    return physical

def _require_plain_path_components(repo_root: Path, path: Path, label: str) -> None:
    lexical = path.absolute()
    try:
        relative = lexical.relative_to(repo_root)
    except ValueError:
        return
    cursor = repo_root
    for part in relative.parts:
        cursor /= part
        if cursor.exists() or cursor.is_symlink():
            _require_plain_path(cursor, label)

def _reject_legacy_formal_publication(repo_root: Path, policy_dir: Path) -> None:
    formal_root = (repo_root / "data" / "pit" / "stock_st_acceptance_policies").absolute()
    lexical = policy_dir.absolute()
    if lexical.parent == formal_root and lexical.name in IMMUTABLE_LEGACY_FORMAL_PUBLICATION_REGISTRY:
        _fail(f"unaccepted_invalid_publication: {lexical.name}")

def _verify_file_set(policy_dir: Path) -> None:
    _require_plain_path(policy_dir, "policy directory")
    actual = {path.relative_to(policy_dir).as_posix() for path in policy_dir.rglob("*") if path.is_file()}
    if actual != EXPECTED_FILES:
        _fail(f"policy file inventory mismatch: missing={sorted(EXPECTED_FILES - actual)}, extra={sorted(actual - EXPECTED_FILES)}")
    for relative in sorted(EXPECTED_FILES):
        _require_plain_path(policy_dir / relative, relative)

def _verify_sidecar(path: Path) -> str:
    sidecar = Path(f"{path}.sha256")
    expected = sidecar.read_text(encoding="ascii").strip()
    actual = sha256_file(path)
    if expected != actual:
        _fail(f"{path.name} sidecar mismatch")
    return actual

def _expected_claims() -> dict:
    return {
        "data_start": "20160101",
        "description": "historical daily ST/*ST list by trade_date",
        "endpoint": "stock_st",
        "request": {
            "params": {
                "ts_code": {"format": "stock code with exchange suffix (e.g., 000001.SZ)", "required": False, "type": "str"},
                "trade_date": {"format": "YYYYMMDD", "required": False, "type": "str"},
                "start_date": {"format": "YYYYMMDD", "required": False, "type": "str"},
                "end_date": {"format": "YYYYMMDD", "required": False, "type": "str"},
            }
        },
        "response": {
            "columns": [
                {"name": "ts_code", "type": "str"},
                {"name": "name", "type": "str"},
                {"name": "trade_date", "type": "str"},
                {"name": "type", "type": "str"},
                {"name": "type_name", "type": "str"},
            ],
            "column_order_semantics": "output order fixed as specified",
            "historical_state_semantics": "each row represents ST status on a specific trade_date",
            "max_rows": 1000,
        },
        "update_time": "09:20 daily",
    }

def _expected_authorized_request_profile() -> dict:
    return {
        "algorithm_id": "stock_st_authorized_request.v1",
        "canonical_form": {"endpoint": "stock_st", "params": {"trade_date": "D"}},
        "disclosure": "Only the canonical stock_st(trade_date=D) request is authorized. D represents a single YYYYMMDD date variable.",
    }

def _expected_algorithm_specs() -> dict:
    canonical_json = {
        "algorithm_id": "canonical_json_sha256.v1",
        "encoding": "UTF-8",
        "ensure_ascii": False,
        "separators": [",", ":"],
        "sort_keys": True,
    }
    request = {
        "algorithm_id": "stock_st_request.v1",
        "canonical_json": canonical_json,
        "template": {"endpoint": "stock_st", "params": {"trade_date": "D"}},
    }
    empty_response = {
        "algorithm_id": "stock_st_empty_response.v1",
        "canonical_json": canonical_json,
        "template": {
            "columns": EXPECTED_COLUMNS,
            "endpoint": "stock_st",
            "outcome": "success_empty",
            "request_trade_date": "D",
            "rows": [],
        },
    }
    aggregate = {
        "algorithm_id": "stock_st_empty_outcomes_aggregate.v1",
        "canonical_json": canonical_json,
        "item_fields": ["request_trade_date", "request_sha256", "response_sha256", "outcome", "row_count"],
        "sort_by": ["request_trade_date"],
    }
    reconciliation = {
        "algorithm_id": "stock_st_empty_reconciliation.v2",
        "aggregate_algorithm_sha256": canonical_json_hash(aggregate),
        "empty_response_algorithm_sha256": canonical_json_hash(empty_response),
        "request_algorithm_sha256": canonical_json_hash(request),
    }
    return {
        "aggregate": {"content": aggregate, "sha256": canonical_json_hash(aggregate)},
        "empty_response": {"content": empty_response, "sha256": canonical_json_hash(empty_response)},
        "reconciliation": {"content": reconciliation, "sha256": canonical_json_hash(reconciliation)},
        "request": {"content": request, "sha256": canonical_json_hash(request)},
    }

def _verify_contract(policy_dir: Path, policy: dict) -> None:
    raw_path = policy_dir / "tushare_doc_397_raw_capture.html"
    contract_path = policy_dir / "contract_evidence.json"
    raw_hash = _verify_sidecar(raw_path)
    contract_hash = _verify_sidecar(contract_path)
    if raw_hash != EXPECTED_RAW_CAPTURE_SHA256:
        _fail("raw capture hash mismatch")
    if policy["contract_bindings"] != {
        "claims_canonical_sha256": canonical_json_hash(_expected_claims()),
        "contract_evidence_artifact": "contract_evidence.json",
        "contract_evidence_raw_sha256": contract_hash,
        "raw_capture_artifact": "tushare_doc_397_raw_capture.html",
        "raw_capture_sha256": EXPECTED_RAW_CAPTURE_SHA256,
    }:
        _fail("contract policy binding mismatch")
    
    contract = _load_json(contract_path)
    if contract.get("schema_version") != "stock_st_contract_evidence.v1":
        _fail("contract evidence schema mismatch")
    if contract.get("claims") != _expected_claims():
        _fail("contract claims mismatch")
    if contract.get("claims_canonical_sha256") != canonical_json_hash(contract["claims"]):
        _fail("contract claims hash mismatch")
    if contract.get("source") != {
        "doc_id": 397,
        "raw_capture_artifact": "tushare_doc_397_raw_capture.html",
        "raw_capture_sha256": EXPECTED_RAW_CAPTURE_SHA256,
        "retrieved_at": "2026-07-27T06:32:32.963895Z",
        "url": "https://tushare.pro/document/2?doc_id=397",
    }:
        _fail("contract source binding mismatch")
    if contract.get("legacy_disclosure") != {
        "note": "The legacy reconciler is historical execution provenance, not the V1 canonicalization trust root.",
        "reconciler_path": "scripts/reconcile_stock_st_empty_outcomes.py",
        "reconciler_sha256": EXPECTED_LEGACY_RECONCILER_SHA256,
    }:
        _fail("legacy reconciler disclosure mismatch")
    for token in (b"stock_st", b"trade_date", b"ts_code", b"type_name", b"20160101", b"9:20"):
        if token not in raw_path.read_bytes():
            _fail(f"raw capture missing contract token")

def _verify_stock_st_entries(entries: list[dict]) -> None:
    # ponytail: only validate structure, not physical files
    if len(entries) != 5108:
        _fail("stock_st entry count mismatch")
    root = PurePosixPath(EXPECTED_STOCK_ST_ROOT)
    parquet_dates, sidecar_dates, seen_paths = set(), set(), set()
    for entry in entries:
        registered = entry.get("path")
        if not isinstance(registered, str) or registered in seen_paths:
            _fail("invalid or duplicate stock_st entry path")
        seen_paths.add(registered)
        path = PurePosixPath(registered)
        if path.is_absolute() or ".." in path.parts:
            _fail("stock_st entry path escape")
        try:
            relative = path.relative_to(root)
        except ValueError:
            _fail("stock_st entry outside registered root")
        if len(relative.parts) != 2 or not relative.parts[0].startswith("trade_date="):
            _fail("stock_st entry partition path mismatch")
        date = relative.parts[0].removeprefix("trade_date=")
        if len(date) != 8 or not date.isdigit():
            _fail("stock_st entry date mismatch")
        if relative.parts[1] == "part.parquet":
            parquet_dates.add(date)
        elif relative.parts[1] == "part.parquet.sha256":
            sidecar_dates.add(date)
        else:
            _fail("unexpected stock_st entry filename")
        if not isinstance(entry.get("sha256"), str) or len(entry["sha256"]) != 64 or not isinstance(entry.get("byte_size"), int) or entry["byte_size"] < 0:
            _fail("invalid stock_st entry metadata")
    if parquet_dates != sidecar_dates or len(parquet_dates) != 2554:
        _fail("stock_st parquet/sidecar inventory mismatch")

def _verify_b3(repo_root: Path, policy: dict) -> None:
    bindings = policy["b3_package_bindings"]
    for key, expected in EXPECTED_B3_PATHS.items():
        if bindings.get(key) != expected:
            _fail(f"{key} policy mismatch")
    if bindings != {
        "input_index_path": EXPECTED_B3_PATHS["input_index_path"],
        "input_index_sha256": EXPECTED_B3_INPUT_INDEX_SHA256,
        "manifest_path": EXPECTED_B3_PATHS["manifest_path"],
        "manifest_sha256": EXPECTED_B3_MANIFEST_SHA256,
        "package_id": "b3eip_traderlens_v2_shsz_pit_001",
        "stock_st_entry_count": 5108,
        "stock_st_interface_sha256": EXPECTED_STOCK_ST_INTERFACE_HASH,
        "trade_cal_entry_count": 2,
        "trade_cal_interface_sha256": EXPECTED_TRADE_CAL_INTERFACE_HASH,
        "trade_cal_path": EXPECTED_B3_PATHS["trade_cal_path"],
        "trade_cal_sha256": EXPECTED_TRADE_CAL_PARQUET_SHA256,
        "trade_cal_sidecar_path": EXPECTED_B3_PATHS["trade_cal_sidecar_path"],
        "trade_cal_sidecar_sha256": EXPECTED_TRADE_CAL_SIDECAR_SHA256,
    }:
        _fail("B3 policy binding mismatch")
    
    manifest_path = _registered_path(repo_root, bindings["manifest_path"], "B3 manifest")
    index_path = _registered_path(repo_root, bindings["input_index_path"], "B3 input index")
    calendar_path = _registered_path(repo_root, bindings["trade_cal_path"], "trade calendar")
    calendar_sidecar_path = _registered_path(repo_root, bindings["trade_cal_sidecar_path"], "trade calendar sidecar")
    
    if sha256_file(manifest_path) != EXPECTED_B3_MANIFEST_SHA256:
        _fail("B3 manifest hash mismatch")
    if sha256_file(index_path) != EXPECTED_B3_INPUT_INDEX_SHA256:
        _fail("B3 input index hash mismatch")
    if sha256_file(calendar_path) != EXPECTED_TRADE_CAL_PARQUET_SHA256:
        _fail("trade calendar hash mismatch")
    if sha256_file(calendar_sidecar_path) != EXPECTED_TRADE_CAL_SIDECAR_SHA256:
        _fail("trade calendar sidecar hash mismatch")
    if calendar_sidecar_path.read_text(encoding="ascii").strip() != EXPECTED_TRADE_CAL_PARQUET_SHA256:
        _fail("trade calendar sidecar content mismatch")
    
    manifest = _load_json(manifest_path)
    index = _load_json(index_path)
    stock_st_entries = index["interfaces"]["stock_st"]["entries"]
    trade_cal_entries = index["interfaces"]["trade_cal"]["entries"]
    _verify_stock_st_entries(stock_st_entries)
    if canonical_json_hash(stock_st_entries) != EXPECTED_STOCK_ST_INTERFACE_HASH:
        _fail("stock_st interface hash mismatch")
    if len(trade_cal_entries) != 2:
        _fail("trade_cal entry count mismatch")
    if canonical_json_hash(trade_cal_entries) != EXPECTED_TRADE_CAL_INTERFACE_HASH:
        _fail("trade_cal interface hash mismatch")
    if manifest.get("input_index_sha256") != EXPECTED_B3_INPUT_INDEX_SHA256:
        _fail("B3 manifest input-index binding mismatch")
    for interface, expected_hash in (("stock_st", EXPECTED_STOCK_ST_INTERFACE_HASH), ("trade_cal", EXPECTED_TRADE_CAL_INTERFACE_HASH)):
        if manifest.get("interfaces", {}).get(interface, {}).get("interface_content_hash") != expected_hash:
            _fail(f"B3 manifest {interface} binding mismatch")
    
    try:
        calendar = pq.read_table(calendar_path)
    except Exception as exc:
        raise PolicyVerificationError(f"invalid trade calendar parquet: {exc}") from exc
    if calendar.num_rows != 3841:
        _fail("trade calendar row count mismatch")
    if calendar.column_names != ["exchange", "cal_date", "is_open", "pretrade_date"]:
        _fail("trade calendar schema mismatch")
    values = calendar.to_pydict()
    exchanges = sorted({str(value) for value in values["exchange"]})
    if exchanges != ["SSE"]:
        _fail("trade calendar exchange set mismatch")
    dates = sorted(
        str(date)
        for date, exchange, is_open in zip(values["cal_date"], values["exchange"], values["is_open"])
        if exchange == "SSE" and int(is_open) == 1
    )
    if len(dates) != 2554 or dates[0] != "20160104" or dates[-1] != "20260710" or canonical_json_hash(dates) != EXPECTED_DATE_SET_SHA256:
        _fail("trade calendar date set mismatch")

def _verify_policy_semantics(repo_root: Path, policy: dict) -> None:
    if policy.get("policy_id") != "stock_st_acceptance_policy_v1_corrective_003":
        _fail("policy_id mismatch")
    if policy.get("schema_version") != "stock_st_acceptance_policy.v1":
        _fail("policy schema mismatch")
    if policy.get("authorized_request_profile") != _expected_authorized_request_profile():
        _fail("authorized request profile mismatch")
    if policy.get("legacy_invalid_publications") != EXPECTED_LEGACY_IDS:
        _fail("legacy rejection registry mismatch")
    if policy.get("registered_stock_st_root") != EXPECTED_STOCK_ST_ROOT:
        _fail("registered stock_st root mismatch")
    if policy.get("schema_requirements") != {
        "empty_allowed_types": ["null", "large_string"],
        "nonempty_types": ["large_string"] * 5,
        "required_columns": EXPECTED_COLUMNS,
    }:
        _fail("stock_st schema policy mismatch")
    if policy.get("path_safety") != {
        "reject_absolute": True,
        "reject_junction_or_reparse": True,
        "reject_parent_traversal": True,
        "reject_symlink_escape": True,
    }:
        _fail("path-safety policy mismatch")
    if policy.get("canonical_algorithms") != _expected_algorithm_specs():
        _fail("canonical algorithm policy mismatch")
    if policy.get("calendar_bindings") != {
        "canonical_date_set_sha256": EXPECTED_DATE_SET_SHA256,
        "disclosure": "Registered B3 _001 contains SSE only; no SZSE calendar.",
        "exchange": "SSE",
        "expected_dates": 2554,
        "first_date": "20160104",
        "is_open": 1,
        "last_date": "20260710",
        "source_rows": 3841,
    }:
        _fail("calendar policy mismatch")
    reconciler = _registered_path(repo_root, "scripts/reconcile_stock_st_empty_outcomes.py", "legacy reconciler")
    if sha256_file(reconciler) != EXPECTED_LEGACY_RECONCILER_SHA256:
        _fail("legacy reconciler hash mismatch")

def _verify(policy_dir: Path, repo_root: Path, *, candidate_mode: bool = False) -> None:
    repo_root = repo_root.resolve(strict=True)
    _reject_legacy_formal_publication(repo_root, policy_dir)
    _require_plain_path_components(repo_root, policy_dir, "candidate path")
    policy_dir = policy_dir.resolve(strict=True)
    
    # ponytail: exact-path enforcement
    expected_candidate = repo_root / "data" / "pit" / ".staging" / "stock_st_acceptance_policy_v1_corrective_003"
    expected_formal = repo_root / "data" / "pit" / "stock_st_acceptance_policies" / "stock_st_acceptance_policy_v1_corrective_003"
    
    if candidate_mode:
        if policy_dir != expected_candidate.resolve():
            _fail(f"candidate mode only accepts {expected_candidate.relative_to(repo_root)}")
    else:
        if policy_dir != expected_formal.resolve():
            _fail(f"formal mode only accepts {expected_formal.relative_to(repo_root)}")
    
    _verify_file_set(policy_dir)
    policy_path = policy_dir / "policy.json"
    actual_policy_hash = sha256_file(policy_path)
    if actual_policy_hash != EXPECTED_POLICY_SHA256:
        _fail(f"policy hash mismatch: expected {EXPECTED_POLICY_SHA256}, got {actual_policy_hash}")
    sidecar_hash = _verify_sidecar(policy_path)
    if sidecar_hash != actual_policy_hash:
        _fail("policy sidecar mismatch")
    policy = _load_json(policy_path)
    _verify_contract(policy_dir, policy)
    _verify_policy_semantics(repo_root, policy)
    _verify_b3(repo_root, policy)

def verify_policy(repo_root: Path, policy_dir: Path, *, candidate_mode: bool = False) -> int:
    try:
        _verify(policy_dir, repo_root, candidate_mode=candidate_mode)
    except (json.JSONDecodeError, KeyError, OSError, PolicyVerificationError, TypeError, ValueError) as exc:
        print(f"REJECTED: {exc}")
        return 1
    print("ACCEPTED: stock_st_acceptance_policy_v1_corrective_003")
    return 0

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--policy-dir", type=Path, required=True)
    parser.add_argument("--candidate-mode", action="store_true")
    args = parser.parse_args(argv)
    return verify_policy(args.repo_root, args.policy_dir, candidate_mode=args.candidate_mode)

if __name__ == "__main__":
    raise SystemExit(main())
