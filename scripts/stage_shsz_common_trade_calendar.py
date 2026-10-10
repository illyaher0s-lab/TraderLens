#!/usr/bin/env python3
"""Stage the fixed SH/SZ common trade calendar without publication."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from numbers import Integral
from io import BytesIO

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
EXPECTED_FIELDS = ("exchange", "cal_date", "is_open", "pretrade_date")
REQUEST = {"api_name": "trade_cal", "exchange": "SZSE", "start_date": "20160101", "end_date": "20260710", "fields": "exchange,cal_date,is_open,pretrade_date"}
PROJECT_PYTHON = Path(r"D:\Codex\TraderLens\.venv\Scripts\python.exe")


class StageError(ValueError):
    """Stable stage rejection."""


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
    if _is_reparse(repo_root):
        raise StageError("repo root reparse")
    try:
        relative = path.relative_to(repo_root)
    except ValueError as exc:
        raise StageError("path escape") from exc
    current = repo_root
    for part in relative.parts:
        current /= part
        if current.exists() and _is_reparse(current):
            raise StageError("path reparse")


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StageError("trust JSON") from exc
    if not isinstance(value, dict):
        raise StageError("trust JSON")
    return value


def _read_sidecar(path: Path, expected: str) -> None:
    sidecar = path.with_name(path.name + ".sha256")
    if not path.is_file() or not sidecar.is_file() or _is_reparse(path) or _is_reparse(sidecar) or sidecar.read_text(encoding="ascii") != expected:
        raise StageError("trust sidecar")


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
        raise StageError("policy trust root mismatch")
    _read_sidecar(policy_path, POLICY_SHA256)
    policy = _read_json(policy_path)
    calendar = policy.get("calendar_bindings")
    if policy.get("policy_id") != POLICY_ID or not isinstance(calendar, dict) or calendar.get("exchange") != "SSE" or calendar.get("expected_dates") != 2554 or calendar.get("first_date") != "20160104" or calendar.get("last_date") != "20260710" or calendar.get("canonical_date_set_sha256") != EXPECTED_COMMON_SHA256:
        raise StageError("policy calendar binding")
    for relative, expected in ((B3_MANIFEST_REL, B3_MANIFEST_SHA256), (B3_INDEX_REL, B3_INDEX_SHA256), (B3_TRADE_CAL_REL, B3_TRADE_CAL_SHA256), (B3_TRADE_CAL_SIDECAR_REL, B3_TRADE_CAL_SIDECAR_SHA256)):
        path = repo_root / Path(*relative.split("/"))
        if not path.is_file() or _is_reparse(path) or _sha_file(path) != expected:
            raise StageError("B3 trust root")
    trade_cal = repo_root / Path(*B3_TRADE_CAL_REL.split("/"))
    _read_sidecar(trade_cal, B3_TRADE_CAL_SHA256)
    index = _read_json(repo_root / Path(*B3_INDEX_REL.split("/")))
    entries = index.get("interfaces", {}).get("trade_cal", {}).get("entries", [])
    entry_map = {entry.get("path"): entry for entry in entries if isinstance(entry, dict)}
    if entry_map.get(B3_TRADE_CAL_REL, {}).get("sha256") != B3_TRADE_CAL_SHA256 or entry_map.get(B3_TRADE_CAL_SIDECAR_REL, {}).get("sha256") != B3_TRADE_CAL_SIDECAR_SHA256:
        raise StageError("B3 calendar entry")
    rows = pq.read_table(trade_cal).to_pylist()
    sse_open = {row.get("cal_date") for row in rows if row.get("exchange") == "SSE" and row.get("is_open") == 1}
    if len(sse_open) != 2554 or _sha_bytes(_canonical(sorted(sse_open))) != EXPECTED_COMMON_SHA256:
        raise StageError("SSE calendar binding")
    binding = {"policy": {"path": POLICY_REL, "sha256": POLICY_SHA256, "policy_id": POLICY_ID, "calendar_binding": calendar}, "b3": {"artifact_id": B3_ID, "manifest_path": B3_MANIFEST_REL, "manifest_sha256": B3_MANIFEST_SHA256, "input_index_path": B3_INDEX_REL, "input_index_sha256": B3_INDEX_SHA256, "trade_cal_path": B3_TRADE_CAL_REL, "trade_cal_sha256": B3_TRADE_CAL_SHA256, "trade_cal_sidecar_path": B3_TRADE_CAL_SIDECAR_REL, "trade_cal_sidecar_sha256": B3_TRADE_CAL_SIDECAR_SHA256}}
    return policy, sse_open, binding


def _fetch_szse_rows(repo_root: Path) -> list[dict]:
    child = r'''
import json, os
from pathlib import Path
for line in Path('.env.local').read_text(encoding='utf-8').splitlines():
    line=line.strip()
    if not line or line.startswith('#') or '=' not in line: continue
    key,value=line.split('=',1); key=key.strip(); value=value.strip()
    if key in {'TUSHARE_TOKEN','TUSHARE_API_URL'}:
        if len(value)>=2 and value[0] == value[-1] and value[0] in chr(34)+chr(39): value=value[1:-1]
        os.environ[key]=value
from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_client import TushareClient
config=TushareConfig.from_env(); config.request_timeout_seconds=8.0
client=TushareClient(config)
df=client.pro.query('trade_cal', exchange='SZSE', start_date='20160101', end_date='20260710', fields='exchange,cal_date,is_open,pretrade_date')
rows=[]
for row in df.to_dict('records'):
    rows.append({'exchange': row.get('exchange'), 'cal_date': row.get('cal_date'), 'is_open': int(row.get('is_open')) if row.get('is_open') is not None else None, 'pretrade_date': row.get('pretrade_date')})
print(json.dumps({'rows':rows}, ensure_ascii=False, separators=(',',':')))
'''
    try:
        result = subprocess.run([str(PROJECT_PYTHON), "-c", child], cwd=repo_root, capture_output=True, text=True, timeout=8, check=False)
    except subprocess.TimeoutExpired as exc:
        raise StageError("SZSE provider timeout") from exc
    if result.returncode != 0 or result.stderr.strip() or not result.stdout.strip():
        raise StageError("SZSE provider request failed")
    try:
        payload = json.loads(result.stdout)
        rows = payload["rows"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise StageError("SZSE provider schema") from exc
    if not isinstance(rows, list):
        raise StageError("SZSE provider schema")
    return rows


def _validate_rows(rows: list[dict], sse_open: set[str]) -> tuple[list[dict], dict]:
    if len(rows) != EXPECTED_SZSE_TOTAL_ROWS:
        raise StageError("SZSE row count")
    seen: set[str] = set()
    normalized = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(EXPECTED_FIELDS) or row.get("exchange") != "SZSE":
            raise StageError("SZSE schema")
        if not _valid_date(row.get("cal_date")) or not "20160101" <= row["cal_date"] <= "20260710" or row["cal_date"] in seen:
            raise StageError("SZSE dates")
        seen.add(row["cal_date"])
        if isinstance(row.get("is_open"), bool) or not isinstance(row.get("is_open"), Integral) or int(row["is_open"]) not in (0, 1) or not _valid_date(row.get("pretrade_date")):
            raise StageError("SZSE schema")
        normalized.append({key: row[key] for key in EXPECTED_FIELDS})
    normalized.sort(key=lambda row: row["cal_date"])
    canonical_sha = _sha_bytes(_canonical(normalized))
    if canonical_sha != EXPECTED_SZSE_ROWS_SHA256:
        raise StageError("SZSE canonical rows")
    open_dates = {row["cal_date"] for row in normalized if row["is_open"] == 1}
    common = sorted(open_dates & sse_open)
    sse_only = sorted(sse_open - open_dates)
    szse_only = sorted(open_dates - sse_open)
    if len(open_dates) != EXPECTED_SZSE_OPEN_COUNT or len(common) != EXPECTED_COMMON_OPEN_COUNT or (common[0], common[-1]) != (EXPECTED_COMMON_FIRST, EXPECTED_COMMON_LAST) or _sha_bytes(_canonical(common)) != EXPECTED_COMMON_SHA256 or sse_only or szse_only:
        raise StageError("common calendar mismatch")
    comparison = {"sse_open_count": len(sse_open), "szse_total_rows": len(normalized), "szse_open_count": len(open_dates), "common_open_count": len(common), "sse_only_open_count": len(sse_only), "szse_only_open_count": len(szse_only), "common_first_date": common[0], "common_last_date": common[-1], "common_open_dates_sha256": _sha_bytes(_canonical(common)), "difference_dates_sha256": _sha_bytes(_canonical({"sse_only": sse_only, "szse_only": szse_only}))}
    return normalized, comparison


def _parquet_bytes(rows: list[dict]) -> bytes:
    schema = pa.schema([pa.field("exchange", pa.large_string()), pa.field("cal_date", pa.large_string()), pa.field("is_open", pa.int64()), pa.field("pretrade_date", pa.large_string())])
    table = pa.Table.from_arrays([[row[key] for row in rows] for key in EXPECTED_FIELDS], schema=schema)
    output = BytesIO()
    pq.write_table(table, output)
    return output.getvalue()


def _build_artifact_bytes(repo_root: Path, rows: list[dict]) -> dict[str, bytes]:
    _policy, sse_open, binding = _load_trust(repo_root)
    normalized = sorted(rows, key=lambda row: row["cal_date"])
    parquet_raw = _parquet_bytes(normalized)
    open_dates = {row["cal_date"] for row in normalized if row["is_open"] == 1}
    common = sorted(open_dates & sse_open)
    sse_only = sorted(sse_open - open_dates)
    szse_only = sorted(open_dates - sse_open)
    manifest = {"artifact_id": ARTIFACT_ID, "schema_version": SCHEMA_VERSION, "frozen": True, "request": REQUEST, "parquet": {"path": "szse_trade_cal.parquet", "sha256": _sha_bytes(parquet_raw), "byte_size": len(parquet_raw), "schema": [{"name": "exchange", "type": "large_string"}, {"name": "cal_date", "type": "large_string"}, {"name": "is_open", "type": "int64"}, {"name": "pretrade_date", "type": "large_string"}]}, "canonical_rows": {"algorithm_id": "sha256_sorted_szse_trade_cal_rows_v1", "sort_by": ["cal_date"], "json": {"encoding": "utf-8", "ensure_ascii": False, "separators": [",", ":"], "sort_keys": True}, "sha256": _sha_bytes(_canonical(normalized)), "row_count": len(normalized), "open_count": len(open_dates)}, "trust_bindings": binding, "comparison": {"sse_open_count": len(sse_open), "szse_total_rows": len(normalized), "szse_open_count": len(open_dates), "common_open_count": len(common), "sse_only_open_count": len(sse_only), "szse_only_open_count": len(szse_only), "common_first_date": common[0] if common else None, "common_last_date": common[-1] if common else None, "common_open_dates_sha256": _sha_bytes(_canonical(common)), "difference_dates_sha256": _sha_bytes(_canonical({"sse_only": sse_only, "szse_only": szse_only}))}}
    manifest_raw = _canonical(manifest)
    return {"szse_trade_cal.parquet": parquet_raw, "szse_trade_cal.parquet.sha256": _sha_bytes(parquet_raw).encode("ascii"), "manifest.json": manifest_raw, "manifest.json.sha256": _sha_bytes(manifest_raw).encode("ascii")}


def build_candidate(repo_root: Path) -> Path:
    repo_root = Path(repo_root).resolve(strict=True)
    candidate = repo_root / Path(*CANDIDATE_REL.split("/"))
    formal = repo_root / Path(*FORMAL_REL.split("/"))
    _check_chain(repo_root, candidate)
    _check_chain(repo_root, formal)
    if candidate.exists() or _is_reparse(candidate):
        raise StageError("candidate exists")
    if formal.exists() or _is_reparse(formal):
        raise StageError("formal guard exists")
    _policy, sse_open, _binding = _load_trust(repo_root)
    rows = _fetch_szse_rows(repo_root)
    normalized, _comparison = _validate_rows(rows, sse_open)
    artifacts = _build_artifact_bytes(repo_root, normalized)
    if candidate.exists() or formal.exists():
        raise StageError("path appeared during stage")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.mkdir()
    try:
        for name in ("szse_trade_cal.parquet", "szse_trade_cal.parquet.sha256", "manifest.json", "manifest.json.sha256"):
            with (candidate / name).open("xb") as handle:
                handle.write(artifacts[name])
    except Exception as exc:
        raise StageError("candidate write failed") from exc
    verifier = repo_root / "scripts/verify_shsz_common_trade_calendar.py"
    try:
        result = subprocess.run([str(PROJECT_PYTHON), str(verifier), "--repo-root", str(repo_root), "--artifact-root", CANDIDATE_REL], cwd=repo_root, capture_output=True, text=True, timeout=300, check=False)
    except Exception as exc:
        raise StageError("candidate verifier failed") from exc
    if result.returncode != 0 or result.stderr != "" or result.stdout.strip() != f"ACCEPTED: {ARTIFACT_ID}":
        raise StageError("candidate verifier rejected")
    print(f"STAGED: {CANDIDATE_REL}")
    print(result.stdout.strip())
    return candidate


def _run_verifier(repo_root: Path, artifact_root: str, formal_mode: bool):
    command = [str(PROJECT_PYTHON), str(repo_root / "scripts/verify_shsz_common_trade_calendar.py"), "--repo-root", str(repo_root), "--artifact-root", artifact_root]
    if formal_mode:
        command.append("--formal-mode")
    return subprocess.run(command, cwd=repo_root, capture_output=True, text=True, timeout=300, check=False)


def _verifier_accepted(result) -> bool:
    return result.returncode == 0 and result.stderr == "" and result.stdout.strip() == f"ACCEPTED: {ARTIFACT_ID}"


def publish_formal(repo_root: Path, verifier_runner=None) -> Path:
    repo_root = Path(repo_root).resolve(strict=True)
    candidate = repo_root / Path(*CANDIDATE_REL.split("/"))
    formal = repo_root / Path(*FORMAL_REL.split("/"))
    _check_chain(repo_root, candidate)
    _check_chain(repo_root, formal)
    if not candidate.is_dir() or _is_reparse(candidate):
        raise StageError("candidate missing")
    if formal.exists() or _is_reparse(formal):
        raise StageError("formal exists")
    runner = verifier_runner or _run_verifier
    result = runner(repo_root, CANDIDATE_REL, False)
    if not _verifier_accepted(result):
        raise StageError("candidate verifier rejected")
    formal.parent.mkdir(parents=True, exist_ok=True)
    candidate.rename(formal)
    result = runner(repo_root, FORMAL_REL, True)
    if not _verifier_accepted(result):
        raise StageError("post-publication formal verifier rejected")
    print(f"PUBLISHED: {FORMAL_REL}")
    print(result.stdout.strip())
    return formal


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--publish-formal", action="store_true")
    try:
        args = parser.parse_args(argv)
        if args.publish_formal:
            publish_formal(Path(args.repo_root))
        else:
            build_candidate(Path(args.repo_root))
    except StageError as exc:
        print(f"REJECTED: {exc}")
        return 1
    except BaseException:
        print("REJECTED: stage error")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
