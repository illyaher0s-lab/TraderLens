"""Acceptance boundaries for selecting a canonical V2 coverage artifact."""
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).parent.parent
INCOMPLETE_CANDIDATE = "5a50209be277c445"


def test_verifier_rejects_candidate_without_completion_receipt():
    """A manifest and parquet files alone cannot prove the full scan exited normally."""
    from scripts.verify_v2_coverage import verify_coverage_package

    result = verify_coverage_package(INCOMPLETE_CANDIDATE)

    assert result["status"] == "failed"
    assert result["checks"]["build_completed"] is False


def test_builder_uses_bound_manifest_denominator_not_literal():
    """The qualification manifest, not a copied constant, is the acceptance denominator."""
    source = (ROOT / "scripts/build_v2_coverage.py").read_text(encoding="utf-8")

    assert 'manifest.get("expected_stock_days_after_market_scope") != 10659050' not in source


def test_report_contains_frozen_disclosure_verbatim():
    """Downstream work must retain the expected denominator and disclose coverage changes."""
    source = (ROOT / "scripts/build_v2_coverage.py").read_text(encoding="utf-8")
    required = (
        "availability mask 是覆盖诊断产物，不是新的 formal package、tradability mask 或回测 universe。"
        "后续 B6/OOS 若跳过 unavailable observations，必须同时保留原始 expected-universe 分母并披露逐日覆盖率，"
        "不得只报告 supported observations 上的收益而省略覆盖变化。"
    )

    assert required in source


def test_verifier_cli_runs_from_project_root():
    """The artifact-only verifier must be runnable directly after a completed build."""
    completed = subprocess.run(
        [sys.executable, "scripts/verify_v2_coverage.py", INCOMPLETE_CANDIDATE],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert '"status": "failed"' in completed.stdout
