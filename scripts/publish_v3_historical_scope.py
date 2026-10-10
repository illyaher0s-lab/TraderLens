"""Publish and independently verify the approved v3 historical scope."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from backend.services.strategy_template_library import (
    convert_to_frozen_contract,
    get_template_by_id,
    get_template_data_requirements_hash,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CALENDAR_DIR = ROOT / "data/pit/shsz_common_trade_calendars/shsz_common_trade_calendar_v1"
DEFAULT_OUTPUT_ROOT = ROOT / "data/pit/historical_scope_freezes"
DEFAULT_CALENDAR_REPO_PATH = "data/pit/shsz_common_trade_calendars/shsz_common_trade_calendar_v1"
TEMPLATE_ID = "relative_strength_rotation_shsz_sw2021_v3"
TEMPLATE_VERSION = "v3_shsz_sw2021_pit_12m_liquidity20d"
TEMPLATE_HASH = "f7c0fd8123f62f37118cb947e1735861374435f8707e01b06d788a8ec4df39c1"
DATA_REQUIREMENTS_HASH = "ef2ab5b1dafe4349f305b52733a7dcb018a2961464dfbc6542a10e34805d041d"
CALENDAR_ARTIFACT_ID = "shsz_common_trade_calendar_v1"
CALENDAR_DATES_HASH = "62b6880c9acc381d273ceee40c900a486c3f83488600c042c43ce1d8f9cbb194"
CALENDAR_MANIFEST_HASH = "ae019cf45072d8274f915837a03d1824c02a69159df473512dbce2e925586785"
CALENDAR_PARQUET_HASH = "8b41168bcd1c39d52ed00f9717ba6fa5330e5b4e15de78068446abe8647f2364"


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _read_sidecar(path: Path) -> str:
    parts = path.read_text(encoding="utf-8").strip().split()
    if len(parts) not in (1, 2) or len(parts[0]) != 64:
        raise ValueError(f"invalid SHA-256 sidecar: {path}")
    int(parts[0], 16)
    return parts[0]


def _load_calendar(calendar_dir: Path) -> tuple[dict, list[str], Path, Path]:
    manifest_path = calendar_dir / "manifest.json"
    parquet_path = calendar_dir / "szse_trade_cal.parquet"
    manifest_sidecar = calendar_dir / "manifest.json.sha256"
    parquet_sidecar = calendar_dir / "szse_trade_cal.parquet.sha256"
    if not all(path.exists() for path in (manifest_path, parquet_path, manifest_sidecar, parquet_sidecar)):
        raise ValueError("calendar manifest, parquet, or sidecar is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("artifact_id") != CALENDAR_ARTIFACT_ID:
        raise ValueError("calendar artifact identity mismatch")
    if _read_sidecar(manifest_sidecar) != _sha256_file(manifest_path):
        raise ValueError("calendar manifest sidecar mismatch")
    if _read_sidecar(parquet_sidecar) != _sha256_file(parquet_path):
        raise ValueError("calendar parquet sidecar mismatch")
    frame = pd.read_parquet(parquet_path)
    if not {"cal_date", "is_open"}.issubset(frame.columns):
        raise ValueError("calendar schema missing cal_date/is_open")
    dates = sorted(frame.loc[frame["is_open"].astype(int) == 1, "cal_date"].astype(str).str.replace("-", "", regex=False).tolist())
    if len(dates) != len(set(dates)):
        raise ValueError("calendar has duplicate open dates")
    dates_hash = _sha256_bytes(_canonical(dates))
    if manifest.get("comparison", {}).get("common_open_dates_sha256") != dates_hash:
        raise ValueError("calendar open-date hash mismatch")
    if manifest.get("comparison", {}).get("common_open_count") != len(dates):
        raise ValueError("calendar open-date count mismatch")
    return manifest, dates, manifest_path, parquet_path


def _validate_template(template_id: str, template_version: str, template_hash: str, requirements_hash: str) -> None:
    template = get_template_by_id(template_id)
    if template is None:
        raise ValueError("v3 template is not approved")
    actual_requirements_hash = get_template_data_requirements_hash(template)
    frozen_contract = convert_to_frozen_contract(template, datetime(2026, 8, 4))
    if (
        template.template_id != TEMPLATE_ID
        or template.version != TEMPLATE_VERSION
        or template.frozen_template_hash != TEMPLATE_HASH
        or actual_requirements_hash != DATA_REQUIREMENTS_HASH
        or frozen_contract.governance_status != "approved"
    ):
        raise ValueError("repository v3 template identity is not the approved frozen contract")
    if (template_id, template_version, template_hash, requirements_hash) != (
        TEMPLATE_ID,
        TEMPLATE_VERSION,
        TEMPLATE_HASH,
        DATA_REQUIREMENTS_HASH,
    ):
        raise ValueError("requested v3 template identity mismatch")


def _scope_payload(
    *,
    calendar_dir: Path,
    calendar_repo_path: str,
    template_id: str = TEMPLATE_ID,
    template_version: str = TEMPLATE_VERSION,
    template_hash: str = TEMPLATE_HASH,
    requirements_hash: str = DATA_REQUIREMENTS_HASH,
) -> dict:
    _validate_template(template_id, template_version, template_hash, requirements_hash)
    calendar_manifest, common_dates, manifest_path, parquet_path = _load_calendar(calendar_dir)
    if _sha256_file(manifest_path) != CALENDAR_MANIFEST_HASH or _sha256_file(parquet_path) != CALENDAR_PARQUET_HASH:
        raise ValueError("calendar source inventory is not the frozen registered artifact")
    if calendar_manifest["comparison"]["common_open_dates_sha256"] != CALENDAR_DATES_HASH:
        raise ValueError("calendar source date set is not the frozen registered artifact")

    execution_dates = common_dates[-252:]
    first_execution_index = common_dates.index(execution_dates[0])
    as_of_dates = [common_dates[common_dates.index(day) - 1] for day in execution_dates]
    confirmation_dates = [common_dates[common_dates.index(execution_dates[0]) - offset] for offset in (1, 2, 3)]
    earliest_confirmation_as_of = min(confirmation_dates)
    source_warmup_start = common_dates[common_dates.index(earliest_confirmation_as_of) - 252]
    source_dates = common_dates[common_dates.index(source_warmup_start) :]
    is_count = int(len(execution_dates) * 0.7)
    is_dates = execution_dates[:is_count]
    oos_dates = execution_dates[is_count:]
    if (
        len(execution_dates) != 252
        or execution_dates[0] != "20250627"
        or execution_dates[-1] != "20260710"
        or as_of_dates[0] != "20250626"
        or earliest_confirmation_as_of != "20250624"
        or source_warmup_start != "20240607"
        or len(source_dates) != 507
        or len(is_dates) != 176
        or len(oos_dates) != 76
    ):
        raise ValueError("frozen v3 historical scope derivation mismatch")

    return {
        "schema_version": "v3_historical_scope_freeze.v1",
        "status": "published",
        "frozen": True,
        "authorization": {
            "decision": "A",
            "authorized_by": "illya",
            "authorization_reference": "user_approved_product_scope_A",
        },
        "template": {
            "template_id": template_id,
            "template_version": template_version,
            "template_hash": template_hash,
            "data_requirements_hash": requirements_hash,
        },
        "calendar": {
            "artifact_id": CALENDAR_ARTIFACT_ID,
            "repo_relative_path": calendar_repo_path,
            "manifest_sha256": _sha256_file(manifest_path),
            "parquet_sha256": _sha256_file(parquet_path),
            "common_open_dates_sha256": CALENDAR_DATES_HASH,
            "common_open_count": len(common_dates),
            "cutoff": "20260710",
        },
        "derivation": {
            "execution_rule_id": "latest_252_trading_days",
            "execution_rule_input": "bound calendar open dates through cutoff inclusive",
            "as_of_rule": "execution date's immediately preceding common open date",
            "confirmation_rule": "three independent as_of dates immediately preceding execution",
            "momentum_rule": "d_minus_252_common_trading_days",
            "source_warmup_rule": "252 trading days before earliest confirmation as_of, inclusive through cutoff",
            "split_rule_id": "fixed_ratio_70_30",
        },
        "execution": {
            "count": len(execution_dates),
            "start": execution_dates[0],
            "end": execution_dates[-1],
            "ordered_date_set_sha256": _sha256_bytes(_canonical(execution_dates)),
            "dates": execution_dates,
            "as_of_dates": as_of_dates,
            "confirmation_earliest_as_of": earliest_confirmation_as_of,
        },
        "source": {
            "start": source_dates[0],
            "end": source_dates[-1],
            "count": len(source_dates),
            "ordered_date_set_sha256": _sha256_bytes(_canonical(source_dates)),
            "dates": source_dates,
        },
        "split": {
            "rule_id": "fixed_ratio_70_30",
            "is_count": len(is_dates),
            "is_start": is_dates[0],
            "is_end": is_dates[-1],
            "oos_count": len(oos_dates),
            "oos_start": oos_dates[0],
            "oos_end": oos_dates[-1],
            "oos_consumed": False,
        },
    }


def publish_scope(
    *,
    calendar_dir: Path = DEFAULT_CALENDAR_DIR,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    calendar_repo_path: str = DEFAULT_CALENDAR_REPO_PATH,
    template_id: str = TEMPLATE_ID,
    template_version: str = TEMPLATE_VERSION,
    template_hash: str = TEMPLATE_HASH,
    requirements_hash: str = DATA_REQUIREMENTS_HASH,
) -> dict:
    payload = _scope_payload(
        calendar_dir=Path(calendar_dir),
        calendar_repo_path=calendar_repo_path,
        template_id=template_id,
        template_version=template_version,
        template_hash=template_hash,
        requirements_hash=requirements_hash,
    )
    artifact_id = _sha256_bytes(_canonical(payload))[:16]
    target = Path(output_root) / artifact_id
    raw = _canonical({**payload, "artifact_id": artifact_id})
    if target.exists():
        manifest_path = target / "manifest.json"
        sidecar_path = target / "manifest.json.sha256"
        if not manifest_path.exists() or not sidecar_path.exists():
            raise ValueError("scope write-once conflict: incomplete existing artifact")
        if manifest_path.read_bytes() != raw or _read_sidecar(sidecar_path) != _sha256_bytes(raw):
            raise ValueError("scope write-once conflict: existing artifact differs")
        return {"status": "already_published", "artifact_id": artifact_id, "path": str(target)}
    target.mkdir(parents=True, exist_ok=False)
    manifest_path = target / "manifest.json"
    manifest_path.write_bytes(raw)
    (target / "manifest.json.sha256").write_text(_sha256_bytes(raw) + "  manifest.json\n", encoding="utf-8")
    return {
        "status": "published",
        "artifact_id": artifact_id,
        "path": str(target),
        "execution_count": payload["execution"]["count"],
        "execution_start": payload["execution"]["start"],
        "execution_end": payload["execution"]["end"],
        "source_count": payload["source"]["count"],
        "source_start": payload["source"]["start"],
        "source_end": payload["source"]["end"],
        "is_count": payload["split"]["is_count"],
        "oos_count": payload["split"]["oos_count"],
    }


def verify_scope(
    scope_dir: Path,
    *,
    calendar_dir: Path = DEFAULT_CALENDAR_DIR,
    calendar_repo_path: str = DEFAULT_CALENDAR_REPO_PATH,
) -> dict:
    scope_dir = Path(scope_dir)
    manifest_path = scope_dir / "manifest.json"
    sidecar_path = scope_dir / "manifest.json.sha256"
    if not manifest_path.exists() or not sidecar_path.exists():
        raise ValueError("scope manifest or sidecar is missing")
    raw = manifest_path.read_bytes()
    if _read_sidecar(sidecar_path) != _sha256_bytes(raw):
        raise ValueError("scope manifest sidecar mismatch")
    manifest = json.loads(raw.decode("utf-8"))
    artifact_id = manifest.pop("artifact_id", None)
    if not artifact_id or _sha256_bytes(_canonical(manifest))[:16] != artifact_id:
        raise ValueError("scope artifact ID mismatch")
    expected = _scope_payload(calendar_dir=Path(calendar_dir), calendar_repo_path=calendar_repo_path)
    if manifest != expected:
        raise ValueError("scope manifest does not match independently derived contract")
    return {"status": "valid", "artifact_id": artifact_id}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calendar-dir", type=Path, default=DEFAULT_CALENDAR_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    print(json.dumps(publish_scope(calendar_dir=args.calendar_dir, output_root=args.output_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
