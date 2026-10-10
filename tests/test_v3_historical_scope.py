import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
CALENDAR_DIR = ROOT / "data/pit/shsz_common_trade_calendars/shsz_common_trade_calendar_v1"


def test_scope_cli_publishes_the_approved_v3_window(tmp_path: Path):
    output_root = tmp_path / "scope_freezes"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.publish_v3_historical_scope",
            "--calendar-dir",
            str(CALENDAR_DIR),
            "--output-root",
            str(output_root),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    publication = json.loads(result.stdout)
    assert publication["status"] == "published"
    assert publication["execution_count"] == 252
    assert publication["execution_start"] == "20250627"
    assert publication["execution_end"] == "20260710"
    assert publication["source_count"] == 507
    assert publication["source_start"] == "20240607"
    assert publication["source_end"] == "20260710"
    assert publication["is_count"] == 176
    assert publication["oos_count"] == 76
    manifest_path = Path(publication["path"]) / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "v3_historical_scope_freeze.v1"
    assert manifest["template"]["template_id"] == "relative_strength_rotation_shsz_sw2021_v3"
    assert manifest["template"]["template_version"] == "v3_shsz_sw2021_pit_12m_liquidity20d"
    assert manifest["execution"]["count"] == 252
    assert manifest["source"]["count"] == 507


def test_scope_rejects_template_identity_mismatch(tmp_path: Path):
    from scripts.publish_v3_historical_scope import publish_scope

    with pytest.raises(ValueError, match="template identity mismatch"):
        publish_scope(
            calendar_dir=CALENDAR_DIR,
            output_root=tmp_path,
            template_version="v3_wrong_scope",
        )


def test_scope_verifier_rejects_calendar_manifest_tamper(tmp_path: Path):
    from scripts.publish_v3_historical_scope import publish_scope, verify_scope

    calendar_dir = tmp_path / "calendar"
    shutil.copytree(CALENDAR_DIR, calendar_dir)
    publication = publish_scope(calendar_dir=calendar_dir, output_root=tmp_path / "out")
    manifest_path = calendar_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["comparison"]["common_open_dates_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="calendar manifest sidecar mismatch"):
        verify_scope(Path(publication["path"]), calendar_dir=calendar_dir)


def test_scope_verifier_rejects_old_scope_schema(tmp_path: Path):
    from scripts.publish_v3_historical_scope import verify_scope

    old_scope = tmp_path / "old"
    old_scope.mkdir()
    raw = b'{"schema_version":"v2_historical_scope_freeze"}'
    (old_scope / "manifest.json").write_bytes(raw)
    import hashlib

    (old_scope / "manifest.json.sha256").write_text(hashlib.sha256(raw).hexdigest() + "  manifest.json\n")

    with pytest.raises(ValueError, match="artifact ID mismatch"):
        verify_scope(old_scope, calendar_dir=CALENDAR_DIR)


def test_scope_publication_is_write_once(tmp_path: Path):
    from scripts.publish_v3_historical_scope import publish_scope

    output_root = tmp_path / "out"
    first = publish_scope(calendar_dir=CALENDAR_DIR, output_root=output_root)
    second = publish_scope(calendar_dir=CALENDAR_DIR, output_root=output_root)
    assert second["status"] == "already_published"
    assert second["artifact_id"] == first["artifact_id"]
    manifest_path = Path(first["path"]) / "manifest.json"
    original = manifest_path.read_bytes()
    manifest_path.write_bytes(original + b"\n")
    with pytest.raises(ValueError, match="write-once conflict"):
        publish_scope(calendar_dir=CALENDAR_DIR, output_root=output_root)
    assert manifest_path.read_bytes() == original + b"\n"


def test_scope_verifier_cli_recomputes_from_calendar_source(tmp_path: Path):
    from scripts.publish_v3_historical_scope import publish_scope

    publication = publish_scope(calendar_dir=CALENDAR_DIR, output_root=tmp_path / "out")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.verify_v3_historical_scope",
            "--scope-dir",
            publication["path"],
            "--calendar-dir",
            str(CALENDAR_DIR),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"artifact_id": publication["artifact_id"], "status": "valid"}
