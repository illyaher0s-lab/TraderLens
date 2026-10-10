from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
COVERAGE_DIR = ROOT / "data/pit/v3_historical_coverage_packages/1e79d26460c0c109"
SCOPE_DIR = ROOT / "data/pit/historical_scope_freezes/acbc49159d989a46"
EVIDENCE_DIR = ROOT / "data/pit/v3_historical_suspension_evidence/4871f6ba56b40e93"
LEGACY_SUCCESSOR_DIR = ROOT / "data/pit/qualification_successors/e5100669ed247769"


def test_v3_verifier_cli_module_entry_help_loads_all_arguments():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.verify_v3_availability_bounded_qualification_successor",
            "--help",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    for option in (
        "--successor-dir",
        "--formal-snapshot-dir",
        "--coverage-dir",
        "--scope-dir",
        "--evidence-dir",
    ):
        assert option in result.stdout


def test_v3_verifier_cli_invalid_result_is_single_json_and_nonzero(tmp_path: Path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.verify_v3_availability_bounded_qualification_successor",
            "--successor-dir",
            str(tmp_path / "missing-successor"),
            "--formal-snapshot-dir",
            str(tmp_path / "missing-formal-snapshot"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1, result.stderr
    assert len(result.stdout.strip().splitlines()) == 1
    assert json.loads(result.stdout) == {
        "reason": "successor manifest or sidecar missing",
        "status": "invalid",
    }


def test_v3_successor_publishes_and_verifies(tmp_path: Path):
    from scripts.build_v3_availability_bounded_qualification_successor import build_successor
    from scripts.publish_v3_formal_snapshot import publish_formal_snapshot
    from scripts.verify_v3_availability_bounded_qualification_successor import verify_successor

    snapshot = publish_formal_snapshot(output_root=tmp_path / "snapshots")
    result = build_successor(
        formal_snapshot_dir=Path(snapshot["path"]),
        coverage_dir=COVERAGE_DIR,
        scope_dir=SCOPE_DIR,
        evidence_dir=EVIDENCE_DIR,
        output_root=tmp_path / "successors",
    )
    successor_dir = Path(result["path"])
    assert result["status"] == "published"
    assert verify_successor(successor_dir, formal_snapshot_dir=Path(snapshot["path"]), coverage_dir=COVERAGE_DIR, scope_dir=SCOPE_DIR, evidence_dir=EVIDENCE_DIR)["status"] == "valid"


def test_v3_successor_rejects_legacy_v2_successor():
    from scripts.verify_v3_availability_bounded_qualification_successor import verify_successor

    result = verify_successor(
        LEGACY_SUCCESSOR_DIR,
        formal_snapshot_dir=LEGACY_SUCCESSOR_DIR,
        coverage_dir=ROOT / "data/pit/coverage_packages/695245b51005e50b",
        scope_dir=SCOPE_DIR,
        evidence_dir=EVIDENCE_DIR,
    )
    assert result["status"] == "invalid"


def test_v3_successor_rejects_missing_exact_binding(tmp_path: Path):
    from scripts.build_v3_availability_bounded_qualification_successor import build_successor
    from scripts.publish_v3_formal_snapshot import publish_formal_snapshot

    snapshot = publish_formal_snapshot(output_root=tmp_path / "snapshots")
    with pytest.raises(ValueError, match="v3|coverage|scope"):
        build_successor(
            formal_snapshot_dir=Path(snapshot["path"]),
            coverage_dir=COVERAGE_DIR,
            scope_dir=tmp_path / "missing-scope",
            evidence_dir=EVIDENCE_DIR,
            output_root=tmp_path / "successors",
        )
