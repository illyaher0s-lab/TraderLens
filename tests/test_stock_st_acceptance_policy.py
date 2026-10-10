"""Focused tests for Stock ST Acceptance Policy V1 Corrective 003 freeze."""
from __future__ import annotations
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import freeze_stock_st_acceptance_policy as freezer
import verify_stock_st_acceptance_policy as verifier

FREEZE_SCRIPT = REPO_ROOT / "scripts" / "freeze_stock_st_acceptance_policy.py"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_stock_st_acceptance_policy.py"
CANDIDATE = REPO_ROOT / "data" / "pit" / ".staging" / "stock_st_acceptance_policy_v1_corrective_003"
TRANSPORT = REPO_ROOT / "data" / "pit" / ".staging" / ".freeze_transport_stock_st_acceptance_policy_v1_corrective_003"
RAW_CAPTURE = REPO_ROOT / "data" / "pit" / "stock_st_acceptance_policies" / "stock_st_acceptance_policy_v1" / "tushare_doc_397_raw_capture.html"
RETRIEVED_AT = "2026-07-27T06:32:32.963895Z"
ALLOWED_DESTINATION = "data/pit/.staging/stock_st_acceptance_policy_v1_corrective_003"
CANDIDATE_RELATIVE = Path(ALLOWED_DESTINATION)
FORMAL_ROOT_RELATIVE = Path("data/pit/stock_st_acceptance_policies")
LEGACY_IDENTITIES = (
    "stock_st_acceptance_policy_v1",
    "stock_st_acceptance_policy_v1_corrective_001",
    "stock_st_acceptance_policy_v1_corrective_002",
)

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _run_freeze_cli(destination: Path | str) -> subprocess.CompletedProcess[str]:
    # ponytail: CLI for black-box tests
    return subprocess.run(
        [sys.executable, str(FREEZE_SCRIPT), "--repo-root", str(REPO_ROOT), "--destination", str(destination), "--raw-capture", str(RAW_CAPTURE), "--retrieved-at", RETRIEVED_AT],
        capture_output=True, text=True, check=False
    )

def _freeze_direct(destination: Path | str) -> str:
    # ponytail: direct call for monkeypatch tests
    return freezer.freeze_policy(REPO_ROOT, Path(destination), RAW_CAPTURE, RETRIEVED_AT)

def _run_verify(
    policy_dir: Path,
    mode: str = "candidate",
    repo_root: Path = REPO_ROOT,
) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, str(repo_root / "scripts" / VERIFY_SCRIPT.name), "--repo-root", str(repo_root), "--policy-dir", str(policy_dir)]
    if mode == "candidate":
        args.append("--candidate-mode")
    return subprocess.run(args, capture_output=True, text=True, check=False)

def _setup_temp_verify_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    candidate = repo_root / CANDIDATE_RELATIVE
    candidate.parent.mkdir(parents=True, exist_ok=True)
    for relative in (
        Path("scripts/verify_stock_st_acceptance_policy.py"),
        Path("scripts/reconcile_stock_st_empty_outcomes.py"),
        Path("data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/manifest.json"),
        Path("data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/input_index.json"),
        Path("data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/trade_cal/part.parquet"),
        Path("data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/trade_cal/part.parquet.sha256"),
    ):
        destination = repo_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative, destination)
    candidate.mkdir()
    for relative, raw in freezer.build_desired_artifacts(repo_root, RAW_CAPTURE, RETRIEVED_AT).items():
        (candidate / relative).write_bytes(raw)
    return repo_root, candidate

@pytest.fixture(autouse=True)
def cleanup():
    for path in (CANDIDATE, TRANSPORT):
        if path.exists():
            shutil.rmtree(path)
    yield
    for path in (CANDIDATE, TRANSPORT):
        if path.exists():
            shutil.rmtree(path)

def test_windows_exact_relative_path():
    result = _run_freeze_cli(ALLOWED_DESTINATION)
    assert result.returncode == 0, f"exact relative path rejected: {result.stderr}"
    assert result.stdout.strip() == "frozen"

def test_absolute_path_rejected():
    result = _run_freeze_cli(CANDIDATE.resolve())
    assert result.returncode == 1
    assert "absolute path not allowed" in result.stderr

def test_parent_traversal_rejected():
    result = _run_freeze_cli("data/pit/.staging/../.staging/stock_st_acceptance_policy_v1_corrective_003")
    assert result.returncode == 1
    assert "parent traversal not allowed" in result.stderr

def test_sibling_path_rejected():
    result = _run_freeze_cli("data/pit/.staging/stock_st_acceptance_policy_v1_corrective_004")
    assert result.returncode == 1
    assert "only data/pit/.staging/stock_st_acceptance_policy_v1_corrective_003 allowed" in result.stderr

def test_fresh_freeze():
    result = _run_freeze_cli(ALLOWED_DESTINATION)
    assert result.returncode == 0
    assert result.stdout.strip() == "frozen"
    assert CANDIDATE.exists()
    assert not TRANSPORT.exists()
    assert (CANDIDATE / "policy.json").exists()
    assert (CANDIDATE / "contract_evidence.json").exists()
    assert (CANDIDATE / "tushare_doc_397_raw_capture.html").exists()

def test_already_frozen():
    result1 = _run_freeze_cli(ALLOWED_DESTINATION)
    assert result1.returncode == 0
    result2 = _run_freeze_cli(ALLOWED_DESTINATION)
    assert result2.returncode == 0
    assert result2.stdout.strip() == "already_frozen"

def test_content_conflict():
    _run_freeze_cli(ALLOWED_DESTINATION)
    (CANDIDATE / "policy.json").write_text("tampered")
    result = _run_freeze_cli(ALLOWED_DESTINATION)
    assert result.returncode == 1
    assert "content_conflict" in result.stderr

def test_transport_pre_existing():
    TRANSPORT.mkdir(parents=True)
    result = _run_freeze_cli(ALLOWED_DESTINATION)
    assert result.returncode == 1
    assert "transport already exists" in result.stderr

def test_transport_inventory_mismatch():
    """ponytail: real transport tamper after write, before inventory check"""
    original_existing = freezer._existing_bytes
    tampered = False
    
    def tamper_once(destination: Path):
        nonlocal tampered
        if not tampered and destination == TRANSPORT:
            (destination / "policy.json").unlink()
            tampered = True
        return original_existing(destination)
    
    with patch.object(freezer, '_existing_bytes', side_effect=tamper_once):
        with pytest.raises(freezer.PolicyFreezeError, match="inventory mismatch"):
            _freeze_direct(ALLOWED_DESTINATION)
    
    assert not CANDIDATE.exists(), "candidate created despite transport failure"

def test_rename_failure():
    """ponytail: inject rename failure at atomic boundary"""
    original_rename = Path.rename
    
    def fail_once(self, target):
        if self == TRANSPORT and target == CANDIDATE:
            raise OSError("injected rename failure")
        return original_rename(self, target)
    
    with patch.object(Path, 'rename', fail_once):
        with pytest.raises((OSError, freezer.PolicyFreezeError)):
            _freeze_direct(ALLOWED_DESTINATION)
    
    assert not CANDIDATE.exists(), "candidate exists after rename failure"
    assert TRANSPORT.exists(), "transport deleted after rename failure"

def test_post_rename_verifier_fail():
    """ponytail: verifier fails after successful rename"""
    def fail_verifier(repo_root, policy_dir):
        if policy_dir == CANDIDATE:
            raise freezer.PolicyFreezeError("injected post-rename verifier failure")
    
    with patch.object(freezer, '_verify_staging', side_effect=fail_verifier):
        with pytest.raises(freezer.PolicyFreezeError, match="post-rename verifier"):
            _freeze_direct(ALLOWED_DESTINATION)
    
    assert CANDIDATE.exists(), "candidate deleted after post-rename verifier failure"
    assert not TRANSPORT.exists(), "transport still exists after rename"

def test_fixed_policy_hash():
    _run_freeze_cli(ALLOWED_DESTINATION)
    policy_hash = _sha256(CANDIDATE / "policy.json")
    assert policy_hash == "a0ce6f21b0986cec50bffe8884fdc41de0b1d66036a36c56d13fc31c2c8c947d"

def test_synchronized_policy_contract_raw_capture():
    _run_freeze_cli(ALLOWED_DESTINATION)
    policy_hash = _sha256(CANDIDATE / "policy.json")
    contract_hash = _sha256(CANDIDATE / "contract_evidence.json")
    raw_hash = _sha256(CANDIDATE / "tushare_doc_397_raw_capture.html")
    assert policy_hash == "a0ce6f21b0986cec50bffe8884fdc41de0b1d66036a36c56d13fc31c2c8c947d"
    assert contract_hash == "21a12a21deb03ac818cd1a120a6848d7b199eef1e416ab823d414f101cefe2cf"
    assert raw_hash == "59e27468afb9e71f6e0f812c567e86538da0f1bb4b8bc781318c8e25bb0517e6"

def test_synchronized_tamper_rejected():
    """ponytail: tamper policy+sync sidecars, verifier must reject via fixed hash"""
    _run_freeze_cli(ALLOWED_DESTINATION)
    baseline = _run_verify(CANDIDATE)
    assert baseline.returncode == 0, f"baseline should pass: {baseline.stderr}"
    
    policy_path = CANDIDATE / "policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["legacy_invalid_publications"].append("tampered_entry")
    policy_raw = json.dumps(policy, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
    policy_path.write_bytes(policy_raw)
    (CANDIDATE / "policy.json.sha256").write_text(hashlib.sha256(policy_raw).hexdigest(), encoding="ascii")
    
    result = _run_verify(CANDIDATE)
    assert result.returncode == 1, "synchronized tamper not rejected"
    assert "policy hash mismatch" in result.stdout or "policy hash mismatch" in result.stderr

@pytest.mark.parametrize("identity", LEGACY_IDENTITIES)
def test_legacy_formal_cli_rejected(tmp_path: Path, identity: str):
    repo_root, _ = _setup_temp_verify_repo(tmp_path)
    legacy_path = repo_root / FORMAL_ROOT_RELATIVE / identity
    legacy_path.mkdir(parents=True)

    result = _run_verify(legacy_path, mode="formal", repo_root=repo_root)

    assert result.returncode != 0
    assert result.stdout.strip() == f"REJECTED: unaccepted_invalid_publication: {identity}"

def test_same_basename_outside_formal_root_is_ordinary_path_rejection(tmp_path: Path):
    repo_root, _ = _setup_temp_verify_repo(tmp_path)
    outside_path = tmp_path / "outside" / "stock_st_acceptance_policy_v1"
    outside_path.mkdir(parents=True)

    result = _run_verify(outside_path, mode="formal", repo_root=repo_root)

    assert result.returncode != 0
    assert "unaccepted_invalid_publication" not in result.stdout + result.stderr
    assert "formal mode only accepts" in result.stdout + result.stderr

def test_real_windows_reparse_path_rejected_without_writes(tmp_path: Path):
    repo_root, candidate = _setup_temp_verify_repo(tmp_path)
    baseline = _run_verify(candidate, repo_root=repo_root)
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr

    shutil.rmtree(candidate)
    staging = repo_root / "data" / "pit" / ".staging"
    target_staging = tmp_path / "junction_target"
    target_staging.mkdir()
    shutil.rmtree(staging)
    junction_result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(staging), str(target_staging)],
        capture_output=True,
        text=True,
        check=False,
    )
    if junction_result.returncode != 0:
        try:
            staging.symlink_to(target_staging, target_is_directory=True)
        except OSError as exc:
            pytest.fail(f"could not create real Windows reparse point: {junction_result.stdout}{junction_result.stderr}{exc}")

    try:
        result = _run_verify(repo_root / CANDIDATE_RELATIVE, repo_root=repo_root)
        output = result.stdout + result.stderr
        assert result.returncode != 0
        assert "candidate path is symlink/junction/reparse" in output
        assert not (target_staging / CANDIDATE_RELATIVE.name).exists()
    finally:
        if staging.exists() or staging.is_symlink():
            subprocess.run(["cmd", "/c", "rmdir", str(staging)], check=False)

def test_candidate_mode_verifier():
    _run_freeze_cli(ALLOWED_DESTINATION)
    result = _run_verify(CANDIDATE, mode="candidate")
    assert result.returncode == 0
    assert "ACCEPTED" in result.stdout

def test_formal_mode_verifier():
    _run_freeze_cli(ALLOWED_DESTINATION)
    result = _run_verify(CANDIDATE, mode="formal")
    assert result.returncode == 1
    assert "formal mode only accepts" in result.stdout or "formal mode only accepts" in result.stderr
