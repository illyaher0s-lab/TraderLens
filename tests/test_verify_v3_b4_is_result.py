import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.publish_v3_execution_semantics import publish_v3_execution_semantics
from scripts.run_v3_b4_is_once import run_v3_b4_is_once
from tests.test_run_v3_b4_is_once import _fixture_data


ROOT = Path(__file__).resolve().parents[1]
CLI_MODULE = "scripts.verify_v3_b4_is_result"


def _temp_b4_artifact(tmp_path: Path) -> Path:
    supplement = publish_v3_execution_semantics(output_root=tmp_path / "supplements")
    result = run_v3_b4_is_once(
        repo_root=ROOT,
        output_root=tmp_path / "b4-results",
        audit_path=tmp_path / "audit.json",
        data_source=_fixture_data(),
        supplement_dir=Path(supplement["path"]),
    )
    return Path(result["path"])


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", CLI_MODULE, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_b4_verifier_cli_verifies_real_temp_artifact(tmp_path: Path) -> None:
    artifact_dir = _temp_b4_artifact(tmp_path)
    result = _run_cli(str(artifact_dir))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "verified"
    assert payload["artifact_id"] == artifact_dir.name


def test_b4_verifier_cli_rejects_invalid_invocation_without_side_effects(
    tmp_path: Path,
) -> None:
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    no_args = _run_cli()
    extra_args = _run_cli("one", "two")
    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert no_args.returncode == 2
    assert extra_args.returncode == 2
    assert before == after == []


def test_b4_verifier_cli_returns_invalid_for_missing_or_tampered_temp_artifact(
    tmp_path: Path,
) -> None:
    missing = _run_cli(str(tmp_path / "missing"))
    assert missing.returncode == 1
    assert json.loads(missing.stdout)["status"] == "invalid"

    artifact_dir = _temp_b4_artifact(tmp_path / "valid")
    manifest_path = artifact_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "tampered"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    tampered = _run_cli(str(artifact_dir))
    assert tampered.returncode == 1
    assert json.loads(tampered.stdout)["status"] == "invalid"


def test_b4_verifier_cli_has_only_readonly_single_argument_surface() -> None:
    source = (ROOT / "scripts/verify_v3_b4_is_result.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_from = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "subprocess" not in imported
    assert "sqlite3" not in imported
    assert "backend.db.strategy" not in imported_from
    assert all(
        token not in source
        for token in ("publish_v3", "StrategyDB", "OOSBudgetLedger", "Promotion", "Signal", "git")
    )
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "verify_v3_b4_is_result"
    ]
    assert len(calls) == 1
