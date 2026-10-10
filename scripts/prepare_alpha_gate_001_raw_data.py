"""One-request-at-a-time raw data collection for Alpha Gate 001."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_client import TushareClient


RUN_ID = "snapshot_20261005T002537Z"
SNAPSHOT_DIR = ROOT / "data" / "alpha_gate_001" / RUN_ID
RAW_DIR = SNAPSHOT_DIR / "raw"
MANIFEST_PATH = SNAPSHOT_DIR / "manifest.json"
HOST = "ts.gyzcloud.top"
BASE_PATH = "/api"
MAX_CALLS = 6

DAILY_FIELDS = "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
ADJ_FIELDS = "ts_code,trade_date,adj_factor"
CAL_FIELDS = "exchange,cal_date,is_open,pretrade_date"


def _request_spec(api: str, start: str, end: str) -> dict:
    if api == "fund_daily":
        return {
            "api": api,
            "fields": DAILY_FIELDS,
            "params": {"ts_code": "510880.SH", "start_date": start, "end_date": end},
            "max_rows": 5000,
            "date_field": "trade_date",
            "key_fields": ["ts_code", "trade_date"],
        }
    if api == "fund_adj":
        return {
            "api": api,
            "fields": ADJ_FIELDS,
            "params": {"ts_code": "510880.SH", "start_date": start, "end_date": end},
            "max_rows": 2000,
            "date_field": "trade_date",
            "key_fields": ["ts_code", "trade_date"],
        }
    return {
        "api": "trade_cal",
        "fields": CAL_FIELDS,
        "params": {
            "exchange": "SSE",
            "start_date": start,
            "end_date": end,
            "is_open": "1",
        },
        "max_rows": 2000,
        "date_field": "cal_date",
        "key_fields": ["exchange", "cal_date"],
    }


CALLS = {
    "fund_daily_2009_2014": _request_spec("fund_daily", "20090101", "20141231"),
    "fund_daily_2015_2020": _request_spec("fund_daily", "20150101", "20201231"),
    "fund_adj_2009_2014": _request_spec("fund_adj", "20090101", "20141231"),
    "fund_adj_2015_2020": _request_spec("fund_adj", "20150101", "20201231"),
    "trade_cal_2009_2014": _request_spec("trade_cal", "20090101", "20141231"),
    "trade_cal_2015_2020": _request_spec("trade_cal", "20150101", "20201231"),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _new_manifest() -> dict:
    return {
        "schema": "alpha_gate_001_raw_data_snapshot.v1",
        "snapshot_id": RUN_ID,
        "created_at_utc": _utc_now(),
        "provider": {
            "name": "project-configured Tushare-compatible service",
            "base_url": "https://ts.gyzcloud.top/api",
            "credential_source": ".env.local (values withheld)",
        },
        "scope": {
            "symbol": "510880.SH",
            "preheat_start": "20090101",
            "research_start": "20100101",
            "research_end": "20201231",
            "post_research_numeric_data_requested": False,
            "calendar_mode": "SSE open dates only (is_open=1)",
        },
        "prior_access": {
            "completed_probe_requests": 4,
            "details": [
                "fund_daily/fund_adj/trade_cal: one request each, 20190102-20190104, code/date metadata only",
                "fund_div: one code-filtered request; date fields through ann_date 20260116; no amounts",
                "Prior project activity outside these recorded probes is not asserted to be absent",
            ],
        },
        "request_budget": {"prior_completed": 4, "this_run_limit": MAX_CALLS, "gate_total_limit": 24},
        "requests": {},
        "status": "in_progress",
    }


def _load_manifest() -> dict:
    if not SNAPSHOT_DIR.exists():
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=False)
        RAW_DIR.mkdir()
        manifest = _new_manifest()
        _write_manifest(manifest)
        return manifest
    if not MANIFEST_PATH.is_file():
        raise RuntimeError("snapshot_collision_without_manifest")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("snapshot_id") != RUN_ID or manifest.get("schema") != "alpha_gate_001_raw_data_snapshot.v1":
        raise RuntimeError("snapshot_identity_mismatch")
    return manifest


def _write_manifest(manifest: dict) -> None:
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_config() -> TushareConfig:
    env_path = ROOT / ".env.local"
    values: dict[str, str] = {}
    for raw in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if key in {"TUSHARE_TOKEN", "TUSHARE_API_URL"}:
            values[key] = value.strip()
    if not values.get("TUSHARE_TOKEN") or not values.get("TUSHARE_API_URL"):
        raise RuntimeError("configured_credentials_missing")
    os.environ["TUSHARE_TOKEN"] = values["TUSHARE_TOKEN"]
    os.environ["TUSHARE_API_URL"] = values["TUSHARE_API_URL"]
    config = TushareConfig.from_env()
    parts = urlsplit(config.api_url)
    if (
        not config.token
        or parts.scheme != "https"
        or parts.hostname != HOST
        or parts.path.rstrip("/") != BASE_PATH
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.port
    ):
        raise RuntimeError("configured_endpoint_mismatch")
    config.retry_attempts = 1
    config.request_timeout_seconds = 8
    config.requests_per_minute = 60
    return config


def _json_value(value):
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _validate_frame(frame: pd.DataFrame, spec: dict) -> tuple[list[dict], dict]:
    expected_fields = spec["fields"].split(",")
    if list(frame.columns) != expected_fields:
        raise ValueError("response_fields_mismatch")
    if frame.empty:
        raise ValueError("response_empty")
    if len(frame) >= spec["max_rows"]:
        raise ValueError("response_at_limit")
    params = spec["params"]
    if spec["api"] != "trade_cal" and not frame["ts_code"].astype(str).eq(params["ts_code"]).all():
        raise ValueError("response_code_mismatch")
    if spec["api"] == "trade_cal":
        if not frame["exchange"].astype(str).eq("SSE").all():
            raise ValueError("response_exchange_mismatch")
        if not frame["is_open"].astype(str).eq("1").all():
            raise ValueError("response_calendar_filter_mismatch")
    date_field = spec["date_field"]
    dates = frame[date_field].astype(str)
    if not dates.str.fullmatch(r"\d{8}").all():
        raise ValueError("response_date_format_mismatch")
    if not dates.between(params["start_date"], params["end_date"]).all():
        raise ValueError("response_date_out_of_range")
    duplicate_rows = int(frame.duplicated(spec["key_fields"], keep=False).sum())
    raw_rows = [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]
    summary = {
        "rows": len(frame),
        "columns": list(frame.columns),
        "date_min": min(dates),
        "date_max": max(dates),
        "null_counts": {column: int(frame[column].isna().sum()) for column in frame.columns},
        "duplicate_key_rows": duplicate_rows,
    }
    if duplicate_rows:
        raise ValueError("response_duplicate_keys")
    return raw_rows, summary


def _run_request(call_id: str) -> dict:
    if call_id not in CALLS:
        raise RuntimeError("unknown_request_id")
    manifest = _load_manifest()
    if manifest.get("status") == "incomplete":
        raise RuntimeError("snapshot_already_incomplete")
    if call_id in manifest["requests"]:
        raise RuntimeError("request_already_recorded")
    if sum(bool(item.get("sent")) for item in manifest["requests"].values()) >= MAX_CALLS:
        raise RuntimeError("request_budget_exhausted")

    spec = CALLS[call_id]
    config = _load_config()
    telemetry = {"sent": False, "http_status": None, "api_code": None}
    original_post = requests.post

    def guarded_post(url, *args, **kwargs):
        parts = urlsplit(url)
        body = kwargs.get("json") or {}
        request_params = body.get("params") or {}
        expected_path = f"{BASE_PATH}/{spec['api']}"
        if (
            parts.scheme != "https"
            or parts.hostname != HOST
            or parts.path != expected_path
            or parts.username
            or parts.password
            or parts.query
            or body.get("api_name") != spec["api"]
            or body.get("fields") != spec["fields"]
            or body.get("token") != config.token
            or any(request_params.get(key) != value for key, value in spec["params"].items())
            or set(request_params) - set(spec["params"]) - {"ts_type_name"}
            or request_params.get("ts_type_name") != config.api_url
            or float(kwargs.get("timeout", 0)) != 8.0
        ):
            raise RuntimeError("local_request_guard_rejected")
        kwargs["allow_redirects"] = False
        telemetry["sent"] = True
        response = original_post(url, *args, **kwargs)
        telemetry["http_status"] = response.status_code
        final = urlsplit(response.url)
        if final.scheme != "https" or final.hostname != HOST or final.path != expected_path:
            telemetry["redirect_blocked"] = True
            raise RuntimeError("redirect_or_destination_mismatch")
        try:
            payload = response.json()
            if isinstance(payload, dict) and payload.get("code") is not None:
                telemetry["api_code"] = int(payload["code"])
        except Exception:
            pass
        if 300 <= response.status_code < 400:
            telemetry["redirect_blocked"] = True
            raise RuntimeError("redirect_blocked")
        return response

    requests.post = guarded_post
    started_at = _utc_now()
    started = time.monotonic()
    error_kind = None
    frame = None
    try:
        client = TushareClient(config)
        frame = client.query(spec["api"], fields=spec["fields"], **spec["params"])
        if telemetry["api_code"] != 0 or telemetry["http_status"] != 200:
            raise ValueError("response_status_mismatch")
        raw_rows, quality = _validate_frame(frame, spec)
        data_path = RAW_DIR / f"{call_id}.json"
        data_path.write_text(json.dumps(raw_rows, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        quality["file"] = str(data_path.relative_to(ROOT)).replace("\\", "/")
        quality["sha256"] = _sha256(data_path)
    except Exception as exc:
        if isinstance(exc, ValueError) and str(exc) in {
            "response_fields_mismatch",
            "response_empty",
            "response_at_limit",
            "response_code_mismatch",
            "response_exchange_mismatch",
            "response_calendar_filter_mismatch",
            "response_date_format_mismatch",
            "response_date_out_of_range",
            "response_duplicate_keys",
        }:
            error_kind = str(exc)
        elif telemetry.get("redirect_blocked"):
            error_kind = "redirect_blocked"
        elif telemetry.get("api_code") == 2002:
            error_kind = "permission"
        elif telemetry.get("http_status") not in (None, 200):
            error_kind = "http_error"
        elif telemetry.get("sent") and telemetry.get("http_status") is None:
            error_kind = "transport_or_timeout"
        else:
            error_kind = "client_or_preflight_error"
        quality = None
    finally:
        requests.post = original_post

    request_record = {
        "request_id": call_id,
        "api": spec["api"],
        "fields": spec["fields"],
        "params": spec["params"],
        "started_at_utc": started_at,
        "finished_at_utc": _utc_now(),
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "sent": telemetry["sent"],
        "http_status": telemetry["http_status"],
        "api_code": telemetry["api_code"],
        "status": "success" if error_kind is None else "incomplete",
        "failure_kind": error_kind,
        "quality": quality,
    }
    manifest["requests"][call_id] = request_record
    if error_kind is not None:
        manifest["status"] = "incomplete"
    elif len(manifest["requests"]) == MAX_CALLS:
        manifest["status"] = "downloaded_needs_quality_review"
    _write_manifest(manifest)
    return {
        "request_id": call_id,
        "sent": telemetry["sent"],
        "http_status": telemetry["http_status"],
        "api_code": telemetry["api_code"],
        "status": request_record["status"],
        "failure_kind": error_kind,
        "rows": quality["rows"] if quality else (len(frame) if frame is not None else None),
        "fields": quality["columns"] if quality else None,
    }


def _summarize() -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if len(manifest.get("requests", {})) != MAX_CALLS:
        return {"status": manifest.get("status"), "completed_request_count": len(manifest.get("requests", {})), "quality": "not_ready"}
    loaded: dict[str, list[dict]] = {}
    for call_id, record in manifest["requests"].items():
        if record.get("status") != "success" or not record.get("quality"):
            continue
        rows = json.loads((ROOT / record["quality"]["file"]).read_text(encoding="utf-8"))
        loaded[call_id] = rows
    date_sets: dict[str, set[str]] = {}
    for api in ("fund_daily", "fund_adj", "trade_cal"):
        date_field = "cal_date" if api == "trade_cal" else "trade_date"
        date_sets[api] = {
            str(row[date_field])
            for call_id, rows in loaded.items()
            if call_id.startswith(api)
            for row in rows
        }
    quality = {
        "daily_rows": sum(len(rows) for name, rows in loaded.items() if name.startswith("fund_daily")),
        "factor_rows": sum(len(rows) for name, rows in loaded.items() if name.startswith("fund_adj")),
        "sse_open_days": len(date_sets["trade_cal"]),
        "daily_dates_without_factor": sorted(date_sets["fund_daily"] - date_sets["fund_adj"]),
        "open_days_without_daily_bar": sorted(date_sets["trade_cal"] - date_sets["fund_daily"]),
        "daily_dates_outside_calendar": sorted(date_sets["fund_daily"] - date_sets["trade_cal"]),
        "post_2020_values_requested": False,
        "fill_or_imputation_used": False,
    }
    has_issues = any(
        quality[key]
        for key in ("daily_dates_without_factor", "open_days_without_daily_bar", "daily_dates_outside_calendar")
    )
    manifest["quality_review"] = quality
    manifest["status"] = "downloaded_with_gaps" if has_issues else "downloaded_unverified_for_research_use"
    _write_manifest(manifest)
    return {"status": manifest["status"], **quality}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", choices=CALLS)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    if args.summary:
        print(json.dumps(_summarize(), ensure_ascii=False))
        return 0
    if not args.request:
        parser.error("select one --request or --summary")
    print(json.dumps(_run_request(args.request), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
