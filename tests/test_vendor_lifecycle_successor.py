from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.qualify_vendor_lifecycle_successor import qualify
from scripts.verify_vendor_lifecycle_successor import verify


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> dict[str, Path]:
    formal = tmp_path / "formal"
    daily = formal / "daily"
    daily.mkdir(parents=True)
    rows = []
    for date in ("20200102", "20200103", "20200106"):
        part = daily / f"trade_date={date}" / "part.parquet"
        part.parent.mkdir()
        pd.DataFrame({"ts_code": ["000001.SZ", "000043.SZ"], "trade_date": [int(date), int(date)]}).to_parquet(part)
        rows.append(date)

    vendor_csv = tmp_path / "source" / "nested" / "vendor.csv"
    vendor_csv.parent.mkdir(parents=True)
    with vendor_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["日期", "代码", *[f"f{i}" for i in range(2, 35)], "上市时间", "退市时间"])
        for date in rows:
            writer.writerow([f"{date[:4]}-{date[4:6]}-{date[6:]}", "000043", *([""] * 33), "1994-01-01", "20200106"])

    vendor_manifest = tmp_path / "artifact" / "vendor_manifest.json"
    vendor_manifest.parent.mkdir()
    vendor_manifest.write_text(json.dumps({"snapshot_id": "vendor_test", "package_sha256": _sha(vendor_csv), "files": [{"path": "source\\nested\\vendor.csv"}]}), encoding="utf-8")
    candidate = tmp_path / "security_lifecycle_candidate.json"
    candidate.write_text(json.dumps({
        "status": "candidate_verified",
        "vendor_snapshot_id": "vendor_test",
        "vendor_package_sha256": _sha(vendor_csv),
        "codes": [{
            "ts_code": "000043.SZ",
            "list_date": "19940101",
            "delist_date": "20200106",
            "vendor_observed_dates": 3,
            "formal_daily_gap_dates": 3,
            "uncovered_formal_daily_dates": 0,
        }],
        "uncovered_formal_daily_dates": 0,
        "errors": [],
        "formal_qualification_run": False,
    }, indent=2), encoding="utf-8")
    gap_audit = tmp_path / "gap_audit.json"
    gap_audit.write_text(json.dumps({
        "status": "lifecycle_source_incomplete",
        "checked_trade_days": 3,
        "gap_codes": [{
            "ts_code": "000043.SZ",
            "total_days": 3,
            "first_date": "20200102",
            "last_date": "20200106",
            "intervals": [{"start": "20200102", "end": "20200106", "trading_days": 3}],
        }],
    }), encoding="utf-8")
    return {"formal": formal, "vendor": tmp_path, "vendor_manifest": vendor_manifest, "candidate": candidate, "gap_audit": gap_audit}


def test_qualifies_bounded_vendor_lifecycle_and_verifies(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    out = tmp_path / "successors"
    result = qualify(**paths, output_root=out)
    assert result["status"] == "published"
    assert result["qualification_status"] == "bounded_qualified_vendor_lifecycle"
    artifact = out / result["successor_id"]
    assert verify(artifact) == {"status": "verified", "successor_id": result["successor_id"]}


def test_qualifier_rejects_extra_code(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    candidate = json.loads(paths["candidate"].read_text())
    candidate["codes"].append({"ts_code": "999999.SZ", "list_date": "19940101", "delist_date": "20200106", "vendor_observed_dates": 3, "formal_daily_gap_dates": 3, "uncovered_formal_daily_dates": 0})
    paths["candidate"].write_text(json.dumps(candidate), encoding="utf-8")
    with pytest.raises(ValueError, match="code set"):
        qualify(**paths, output_root=tmp_path / "successors")


def test_qualifier_rejects_wrong_column_count(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    source = paths["vendor"] / "source" / "nested" / "vendor.csv"
    lines = source.read_text(encoding="utf-8").splitlines()
    source.write_text(lines[0] + "\n" + lines[1].rsplit(",", 1)[0] + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="37 columns"):
        qualify(**paths, output_root=tmp_path / "successors")


def test_qualifier_rejects_key_column_mismatch(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    source = paths["vendor"] / "source" / "nested" / "vendor.csv"
    lines = source.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace("代码", "证券代码")
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="header"):
        qualify(**paths, output_root=tmp_path / "successors")


def test_verifier_rejects_tampered_candidate_hash(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    result = qualify(**paths, output_root=tmp_path / "successors")
    artifact = tmp_path / "successors" / result["successor_id"]
    manifest = json.loads((artifact / "manifest.json").read_text())
    manifest["candidate_sha256"] = "0" * 64
    semantic = {key: value for key, value in manifest.items() if key != "successor_id"}
    manifest["successor_id"] = hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()[:16]
    (artifact / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (artifact / "manifest.json.sha256").write_text(_sha(artifact / "manifest.json"), encoding="utf-8")
    with pytest.raises(ValueError, match="candidate hash"):
        verify(artifact, candidate=paths["candidate"])
