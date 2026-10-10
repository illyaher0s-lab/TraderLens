#!/usr/bin/env python3
"""Freeze Stock ST Acceptance Policy V1 Corrective 003."""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import pyarrow.parquet as pq

POLICY_ID = "stock_st_acceptance_policy_v1_corrective_003"
ALLOWED_DESTINATION = "data/pit/.staging/stock_st_acceptance_policy_v1_corrective_003"
TRANSPORT_NAME = ".freeze_transport_stock_st_acceptance_policy_v1_corrective_003"
EXPECTED_RETRIEVED_AT = "2026-07-27T06:32:32.963895Z"
EXPECTED_RAW_CAPTURE_SHA256 = "59e27468afb9e71f6e0f812c567e86538da0f1bb4b8bc781318c8e25bb0517e6"
EXPECTED_B3_MANIFEST_SHA256 = "ee21303e17b60f81947f40e172031421b88e53d3d79b0fdb95ba6c474a327786"
EXPECTED_B3_INPUT_INDEX_SHA256 = "3b7ca54e7cfad3443f0442215ca38328cfe92dcf1f780d3a85ac65710cacc787"
EXPECTED_STOCK_ST_INTERFACE_HASH = "b9db559909524a484d75d8cad9b8acf26d93acd9142edf92786f5215e48e00bb"
EXPECTED_TRADE_CAL_INTERFACE_HASH = "859484d6e1d0bfa06921b1b9c43334aa64c11569bae46a775df3bd713910b05c"
EXPECTED_TRADE_CAL_PARQUET_SHA256 = "28a8587f1962ab268736c41de3e8d8442fbf0f54325475f1cf0b302125575860"
EXPECTED_TRADE_CAL_SIDECAR_SHA256 = "7600cd540366a4e5dfd97e6b5df5154fd3507338c3db12f1cff4cb16ed898aa6"
EXPECTED_DATE_SET_SHA256 = "62b6880c9acc381d273ceee40c900a486c3f83488600c042c43ce1d8f9cbb194"
LEGACY_RECONCILER_SHA256 = "c06c494ebca3c6682b2d048147e82294c9ef55c9abc6edd1b850103454fc6ce5"

B3_MANIFEST_PATH = Path("data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/manifest.json")
B3_INPUT_INDEX_PATH = Path("data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/input_index.json")
TRADE_CAL_PATH = Path("data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/trade_cal/part.parquet")
TRADE_CAL_SIDECAR_PATH = Path(f"{TRADE_CAL_PATH}.sha256")
REGISTERED_STOCK_ST_ROOT = "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/stock_st"

class PolicyFreezeError(RuntimeError):
    pass

def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())

def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def canonical_json_hash(value: object) -> str:
    return sha256_bytes(canonical_json_bytes(value))

def pretty_json_bytes(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")

def _validate_destination_boundary(repo_root: Path, destination: Path) -> None:
    # ponytail: parent thread verified Windows guard, inline here
    if destination.is_absolute():
        raise PolicyFreezeError("destination_boundary_violation: absolute path not allowed")
    if ".." in destination.parts:
        raise PolicyFreezeError("destination_boundary_violation: parent traversal not allowed")
    if destination.as_posix() != ALLOWED_DESTINATION:
        raise PolicyFreezeError(f"destination_boundary_violation: only {ALLOWED_DESTINATION} allowed")
    resolved = (repo_root.resolve() / destination).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        raise PolicyFreezeError(f"destination_boundary_violation: escapes repo")
    # ponytail: check symlink/junction per component
    cursor = repo_root.resolve()
    for part in destination.parts:
        cursor /= part
        if cursor.exists():
            if cursor.is_symlink():
                raise PolicyFreezeError(f"destination_boundary_violation: symlink")
            try:
                import stat as stat_mod
                attrs = getattr(cursor.lstat(), 'st_file_attributes', 0)
                if attrs & getattr(stat_mod, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
                    raise PolicyFreezeError(f"destination_boundary_violation: junction/reparse")
            except (AttributeError, OSError):
                pass

def _require_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise PolicyFreezeError(f"missing {label}")
    if sha256_file(path) != expected:
        raise PolicyFreezeError(f"{label} hash mismatch")

def _validate_raw_capture(raw: bytes) -> None:
    if sha256_bytes(raw) != EXPECTED_RAW_CAPTURE_SHA256:
        raise PolicyFreezeError("raw capture hash mismatch")
    for token in (b"stock_st", b"trade_date", b"ts_code", b"type_name", b"20160101", b"9:20"):
        if token not in raw:
            raise PolicyFreezeError(f"raw capture missing token")

def _registered_bindings(repo_root: Path) -> tuple[dict, list[str]]:
    manifest_path = repo_root / B3_MANIFEST_PATH
    index_path = repo_root / B3_INPUT_INDEX_PATH
    calendar_path = repo_root / TRADE_CAL_PATH
    sidecar_path = repo_root / TRADE_CAL_SIDECAR_PATH
    
    _require_hash(manifest_path, EXPECTED_B3_MANIFEST_SHA256, "B3 manifest")
    _require_hash(index_path, EXPECTED_B3_INPUT_INDEX_SHA256, "B3 input index")
    _require_hash(calendar_path, EXPECTED_TRADE_CAL_PARQUET_SHA256, "trade calendar")
    _require_hash(sidecar_path, EXPECTED_TRADE_CAL_SIDECAR_SHA256, "trade calendar sidecar")
    
    if sidecar_path.read_text(encoding="utf-8").strip() != EXPECTED_TRADE_CAL_PARQUET_SHA256:
        raise PolicyFreezeError("trade calendar sidecar content mismatch")
    
    index = json.loads(index_path.read_text(encoding="utf-8"))
    stock_st_entries = index["interfaces"]["stock_st"]["entries"]
    trade_cal_entries = index["interfaces"]["trade_cal"]["entries"]
    
    if len(stock_st_entries) != 5108:
        raise PolicyFreezeError("stock_st entry count mismatch")
    if len(trade_cal_entries) != 2:
        raise PolicyFreezeError("trade_cal entry count mismatch")
    if canonical_json_hash(stock_st_entries) != EXPECTED_STOCK_ST_INTERFACE_HASH:
        raise PolicyFreezeError("stock_st interface hash mismatch")
    if canonical_json_hash(trade_cal_entries) != EXPECTED_TRADE_CAL_INTERFACE_HASH:
        raise PolicyFreezeError("trade_cal interface hash mismatch")
    
    calendar = pq.read_table(calendar_path)
    if calendar.num_rows != 3841 or calendar.column_names != ["exchange", "cal_date", "is_open", "pretrade_date"]:
        raise PolicyFreezeError("trade calendar schema mismatch")
    
    values = calendar.to_pydict()
    exchanges = sorted(set(str(v) for v in values["exchange"]))
    if exchanges != ["SSE"]:
        raise PolicyFreezeError("trade calendar exchange mismatch")
    
    # ponytail: compute canonical date set in-place
    dates = sorted(
        str(date)
        for date, exchange, is_open in zip(values["cal_date"], values["exchange"], values["is_open"])
        if exchange == "SSE" and int(is_open) == 1
    )
    if len(dates) != 2554 or dates[0] != "20160104" or dates[-1] != "20260710":
        raise PolicyFreezeError("trade calendar date set mismatch")
    if canonical_json_hash(dates) != EXPECTED_DATE_SET_SHA256:
        raise PolicyFreezeError("trade calendar date set canonical hash mismatch")
    
    return index, dates

def _authorized_request_profile() -> dict:
    return {
        "algorithm_id": "stock_st_authorized_request.v1",
        "canonical_form": {"endpoint": "stock_st", "params": {"trade_date": "D"}},
        "disclosure": "Only the canonical stock_st(trade_date=D) request is authorized. D represents a single YYYYMMDD date variable.",
    }

def _algorithm_specs() -> dict:
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
            "columns": ["ts_code", "name", "trade_date", "type", "type_name"],
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

def build_desired_artifacts(repo_root: Path, raw_capture_path: Path, retrieved_at: str) -> dict[str, bytes]:
    if retrieved_at != EXPECTED_RETRIEVED_AT:
        raise PolicyFreezeError("retrieved_at mismatch")
    
    raw_capture = raw_capture_path.resolve().read_bytes()
    _validate_raw_capture(raw_capture)
    _, dates = _registered_bindings(repo_root.resolve())
    
    claims = {
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
    
    contract_evidence = {
        "claims": claims,
        "claims_canonical_sha256": canonical_json_hash(claims),
        "legacy_disclosure": {
            "note": "The legacy reconciler is historical execution provenance, not the V1 canonicalization trust root.",
            "reconciler_path": "scripts/reconcile_stock_st_empty_outcomes.py",
            "reconciler_sha256": LEGACY_RECONCILER_SHA256,
        },
        "schema_version": "stock_st_contract_evidence.v1",
        "source": {
            "doc_id": 397,
            "raw_capture_artifact": "tushare_doc_397_raw_capture.html",
            "raw_capture_sha256": EXPECTED_RAW_CAPTURE_SHA256,
            "retrieved_at": retrieved_at,
            "url": "https://tushare.pro/document/2?doc_id=397",
        },
    }
    contract_raw = pretty_json_bytes(contract_evidence)
    algorithms = _algorithm_specs()
    
    policy = {
        "authorized_request_profile": _authorized_request_profile(),
        "b3_package_bindings": {
            "input_index_path": B3_INPUT_INDEX_PATH.as_posix(),
            "input_index_sha256": EXPECTED_B3_INPUT_INDEX_SHA256,
            "manifest_path": B3_MANIFEST_PATH.as_posix(),
            "manifest_sha256": EXPECTED_B3_MANIFEST_SHA256,
            "package_id": "b3eip_traderlens_v2_shsz_pit_001",
            "stock_st_entry_count": 5108,
            "stock_st_interface_sha256": EXPECTED_STOCK_ST_INTERFACE_HASH,
            "trade_cal_entry_count": 2,
            "trade_cal_interface_sha256": EXPECTED_TRADE_CAL_INTERFACE_HASH,
            "trade_cal_path": TRADE_CAL_PATH.as_posix(),
            "trade_cal_sha256": EXPECTED_TRADE_CAL_PARQUET_SHA256,
            "trade_cal_sidecar_path": TRADE_CAL_SIDECAR_PATH.as_posix(),
            "trade_cal_sidecar_sha256": EXPECTED_TRADE_CAL_SIDECAR_SHA256,
        },
        "calendar_bindings": {
            "canonical_date_set_sha256": canonical_json_hash(dates),
            "disclosure": "Registered B3 _001 contains SSE only; no SZSE calendar.",
            "exchange": "SSE",
            "expected_dates": 2554,
            "first_date": "20160104",
            "is_open": 1,
            "last_date": "20260710",
            "source_rows": 3841,
        },
        "canonical_algorithms": algorithms,
        "contract_bindings": {
            "claims_canonical_sha256": canonical_json_hash(claims),
            "contract_evidence_artifact": "contract_evidence.json",
            "contract_evidence_raw_sha256": sha256_bytes(contract_raw),
            "raw_capture_artifact": "tushare_doc_397_raw_capture.html",
            "raw_capture_sha256": EXPECTED_RAW_CAPTURE_SHA256,
        },
        "legacy_invalid_publications": [
            "stacc_traderlens_v2_shsz_stock_st_001",
            "stacc_traderlens_v2_shsz_stock_st_002",
            "stacc_traderlens_v2_shsz_stock_st_003",
            "stock_st_acceptance_policy_v1",
            "stock_st_acceptance_policy_v1_corrective_001",
            "stock_st_acceptance_policy_v1_corrective_002",
        ],
        "path_safety": {
            "reject_absolute": True,
            "reject_junction_or_reparse": True,
            "reject_parent_traversal": True,
            "reject_symlink_escape": True,
        },
        "policy_id": POLICY_ID,
        "registered_stock_st_root": REGISTERED_STOCK_ST_ROOT,
        "schema_requirements": {
            "empty_allowed_types": ["null", "large_string"],
            "nonempty_types": ["large_string"] * 5,
            "required_columns": ["ts_code", "name", "trade_date", "type", "type_name"],
        },
        "schema_version": "stock_st_acceptance_policy.v1",
    }
    policy_raw = pretty_json_bytes(policy)
    
    return {
        "contract_evidence.json": contract_raw,
        "contract_evidence.json.sha256": sha256_bytes(contract_raw).encode("ascii"),
        "policy.json": policy_raw,
        "policy.json.sha256": sha256_bytes(policy_raw).encode("ascii"),
        "tushare_doc_397_raw_capture.html": raw_capture,
        "tushare_doc_397_raw_capture.html.sha256": EXPECTED_RAW_CAPTURE_SHA256.encode("ascii"),
    }

def _existing_bytes(destination: Path) -> dict[str, bytes]:
    if not destination.is_dir():
        raise PolicyFreezeError("content_conflict: destination is not a directory")
    return {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in sorted(destination.rglob("*"))
        if path.is_file()
    }

def _verify_staging(repo_root: Path, policy_dir: Path) -> None:
    verifier = repo_root.resolve() / "scripts" / "verify_stock_st_acceptance_policy.py"
    result = subprocess.run(
        [sys.executable, str(verifier), "--repo-root", str(repo_root.resolve()), "--policy-dir", str(policy_dir), "--candidate-mode"],
        capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise PolicyFreezeError(f"post-rename verifier rejected: {(result.stdout + result.stderr).strip()}")

def freeze_policy(repo_root: Path, destination: Path, raw_capture_path: Path, retrieved_at: str) -> str:
    _validate_destination_boundary(repo_root, destination)
    desired = build_desired_artifacts(repo_root, raw_capture_path, retrieved_at)
    
    resolved_dest = (repo_root.resolve() / destination).resolve()
    resolved_transport = resolved_dest.parent / TRANSPORT_NAME
    
    # ponytail: exact match before verifier
    if resolved_dest.exists():
        if _existing_bytes(resolved_dest) == desired:
            _verify_staging(repo_root, resolved_dest)
            return "already_frozen"
        raise PolicyFreezeError("content_conflict: existing policy differs")
    
    if resolved_transport.exists():
        raise PolicyFreezeError("transport already exists")
    
    resolved_transport.parent.mkdir(parents=True, exist_ok=True)
    resolved_transport.mkdir()
    for relative, raw in desired.items():
        (resolved_transport / relative).write_bytes(raw)
    
    if _existing_bytes(resolved_transport) != desired:
        raise PolicyFreezeError("transport inventory mismatch")
    
    resolved_transport.rename(resolved_dest)
    _verify_staging(repo_root, resolved_dest)
    return "frozen"

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--raw-capture", type=Path, required=True)
    parser.add_argument("--retrieved-at", required=True)
    args = parser.parse_args(argv)
    try:
        status = freeze_policy(args.repo_root, args.destination, args.raw_capture, args.retrieved_at)
    except (OSError, KeyError, ValueError, PolicyFreezeError) as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 1
    print(status)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
