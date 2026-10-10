"""Fetch preserved 510880 fund_div rows for known 2009-2020 announcement dates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_client import TushareClient


RUN_ID = "fund_div_announcements_20261005T004106Z"
OUTPUT_DIR = ROOT / "data" / "alpha_gate_001" / RUN_ID
RAW_DIR = OUTPUT_DIR / "raw"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"
HOST = "ts.gyzcloud.top"
ANN_DATES = [
    "20090318", "20091016", "20100709", "20101018", "20111018",
    "20121212", "20140115", "20150114", "20160114", "20170117",
    "20180117", "20190110", "20200113",
]
FIELDS = (
    "ts_code,ann_date,imp_anndate,base_date,record_date,ex_date,pay_date,"
    "earpay_date,net_ex_date,account_date,div_cash,base_unit,ear_distr,ear_amount"
)
FIELD_LIST = FIELDS.split(",")
ROW_LIMIT = 2000


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_config() -> TushareConfig:
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
    url = urlsplit(config.api_url)
    if (
        not config.token or url.scheme != "https" or url.hostname != HOST
        or url.path.rstrip("/") != "/api" or url.username or url.password
        or url.query or url.fragment or url.port
    ):
        raise RuntimeError("configured_endpoint_mismatch")
    config.retry_attempts = 1
    config.request_timeout_seconds = 8
    config.requests_per_minute = 60
    return config


def new_manifest() -> dict:
    return {
        "schema": "alpha_gate_001_fund_div_raw.v1",
        "snapshot_id": RUN_ID,
        "created_at_utc": now_utc(),
        "provider": {
            "name": "project-configured Tushare-compatible service",
            "base_url": "https://ts.gyzcloud.top/api",
            "credentials": ".env.local (values withheld)",
        },
        "scope": {
            "ts_code": "510880.SH",
            "ann_date_min": "20090101",
            "ann_date_max": "20201231",
            "unique_announcement_dates_from_prior_probe": ANN_DATES,
            "dates_deduplicated_for_request_list_only": True,
            "response_rows_preserved_without_merge": True,
        },
        "documented_field_units": {
            "div_cash": "每股派息(元)",
            "base_unit": "基准基金份额(万份)",
            "ear_distr": "可分配收益(元)",
            "ear_amount": "收益分配金额(元)",
            "source": "previously read Tushare fund_div interface contract",
        },
        "request_budget": {
            "previous_gate_requests": 10,
            "this_run_cap": 14,
            "gate_total_cap": 24,
        },
        "requests": {},
        "status": "raw_in_progress",
    }


def read_or_create_manifest() -> dict:
    if OUTPUT_DIR.exists():
        if not MANIFEST_PATH.is_file():
            raise RuntimeError("snapshot_collision_without_manifest")
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if manifest.get("snapshot_id") != RUN_ID:
            raise RuntimeError("snapshot_identity_mismatch")
        return manifest
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    RAW_DIR.mkdir()
    manifest = new_manifest()
    write_manifest(manifest)
    return manifest


def write_manifest(manifest: dict) -> None:
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def to_json_value(value):
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not (float("-inf") < value < float("inf")):
        return None
    return value


def collect(ann_date: str) -> dict:
    if ann_date not in ANN_DATES:
        raise RuntimeError("announcement_date_not_in_recovered_list")
    manifest = read_or_create_manifest()
    if manifest.get("status") == "incomplete":
        raise RuntimeError("collection_already_incomplete")
    if ann_date in manifest["requests"]:
        raise RuntimeError("announcement_date_already_requested")
    if len(manifest["requests"]) >= 14:
        raise RuntimeError("request_budget_exhausted")

    config = load_config()
    telemetry = {"sent": False, "http_status": None, "api_code": None}
    original_post = requests.post

    def guarded_post(url, *args, **kwargs):
        parts = urlsplit(url)
        body = kwargs.get("json") or {}
        params = body.get("params") or {}
        if (
            parts.scheme != "https" or parts.hostname != HOST
            or parts.path != "/api/fund_div" or parts.username or parts.password
            or parts.query or body.get("api_name") != "fund_div"
            or body.get("fields") != FIELDS or body.get("token") != config.token
            or params.get("ann_date") != ann_date
            or params.get("ts_type_name") != config.api_url
            or set(params) - {"ann_date", "ts_type_name"}
            or float(kwargs.get("timeout", 0)) != 8.0
        ):
            raise RuntimeError("local_request_guard_rejected")
        kwargs["allow_redirects"] = False
        telemetry["sent"] = True
        response = original_post(url, *args, **kwargs)
        telemetry["http_status"] = response.status_code
        final = urlsplit(response.url)
        if final.scheme != "https" or final.hostname != HOST or final.path != "/api/fund_div":
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

    started_at = now_utc()
    clock_start = time.monotonic()
    failure = None
    target_rows: list[dict] = []
    provider_rows = None
    raw_path = RAW_DIR / f"ann_date_{ann_date}.json"
    requests.post = guarded_post
    try:
        client = TushareClient(config)
        frame = client.query("fund_div", fields=FIELDS, ann_date=ann_date)
        provider_rows = len(frame)
        if telemetry["http_status"] != 200 or telemetry["api_code"] != 0:
            raise RuntimeError("response_status_mismatch")
        if list(frame.columns) != FIELD_LIST:
            raise RuntimeError("response_fields_mismatch")
        if len(frame) >= ROW_LIMIT:
            failure = "response_at_conservative_2000_row_ceiling"
        if not frame["ann_date"].astype(str).eq(ann_date).all():
            raise RuntimeError("response_announcement_date_mismatch")
        selected = frame.loc[frame["ts_code"].astype(str).eq("510880.SH")]
        target_rows = [
            {str(key): to_json_value(value) for key, value in row.items()}
            for row in selected.to_dict(orient="records")
        ]
        raw_path.write_text(
            json.dumps(target_rows, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        if not target_rows and failure is None:
            failure = "target_event_missing_from_response"
    except Exception as exc:
        if failure is None:
            message = str(exc)
            if message in {
                "response_status_mismatch", "response_fields_mismatch",
                "response_announcement_date_mismatch",
            }:
                failure = message
            elif telemetry.get("redirect_blocked"):
                failure = "redirect_blocked"
            elif telemetry.get("api_code") == 2002:
                failure = "permission"
            elif telemetry.get("http_status") not in (None, 200):
                failure = "http_error"
            elif telemetry.get("sent") and telemetry.get("http_status") is None:
                failure = "transport_or_timeout"
            else:
                failure = "client_or_preflight_error"
    finally:
        requests.post = original_post

    record = {
        "ann_date": ann_date,
        "api": "fund_div",
        "fields": FIELDS,
        "params": {"ann_date": ann_date},
        "started_at_utc": started_at,
        "finished_at_utc": now_utc(),
        "elapsed_ms": round((time.monotonic() - clock_start) * 1000),
        "sent": telemetry["sent"],
        "http_status": telemetry["http_status"],
        "api_code": telemetry["api_code"],
        "provider_rows_received": provider_rows,
        "target_rows_saved": len(target_rows),
        "status": "raw" if failure is None else "incomplete",
        "failure_kind": failure,
        "file": str(raw_path.relative_to(ROOT)).replace("\\", "/") if raw_path.exists() else None,
        "sha256": sha256(raw_path) if raw_path.exists() else None,
        "duplicates_merged": 0,
    }
    manifest["requests"][ann_date] = record
    if failure is not None:
        manifest["status"] = "incomplete"
    elif len(manifest["requests"]) == len(ANN_DATES):
        manifest["status"] = "raw_unverified"
    write_manifest(manifest)
    return {
        "ann_date": ann_date,
        "sent": telemetry["sent"],
        "http_status": telemetry["http_status"],
        "api_code": telemetry["api_code"],
        "provider_rows_received": provider_rows,
        "target_rows_saved": len(target_rows),
        "status": record["status"],
        "failure_kind": failure,
        "sha256": record["sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ann-date", choices=ANN_DATES)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    if args.summary:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        sent = sum(bool(r.get("sent")) for r in manifest["requests"].values())
        target_rows = sum(int(r.get("target_rows_saved") or 0) for r in manifest["requests"].values())
        print(json.dumps({
            "snapshot_id": manifest["snapshot_id"],
            "status": manifest["status"],
            "requested_dates": len(manifest["requests"]),
            "requests_sent": sent,
            "target_rows_saved": target_rows,
            "duplicates_merged": 0,
            "failure_kinds": [r["failure_kind"] for r in manifest["requests"].values() if r.get("failure_kind")],
        }, ensure_ascii=False))
        return 0
    if not args.ann_date:
        parser.error("select one --ann-date or --summary")
    print(json.dumps(collect(args.ann_date), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
