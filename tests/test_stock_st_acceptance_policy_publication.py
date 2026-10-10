"""Publication matrix for Stock ST Acceptance Policy V1 Corrective 003."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FREEZE_SCRIPT_NAME = "freeze_stock_st_acceptance_policy.py"
VERIFY_SCRIPT_NAME = "verify_stock_st_acceptance_policy.py"
PUBLISH_SCRIPT_NAME = "publish_stock_st_acceptance_policy.py"
RETRIEVED_AT = "2026-07-27T06:32:32.963895Z"
EXPECTED_POLICY_SHA256 = "a0ce6f21b0986cec50bffe8884fdc41de0b1d66036a36c56d13fc31c2c8c947d"
EXPECTED_FILES = (
    "contract_evidence.json",
    "contract_evidence.json.sha256",
    "policy.json",
    "policy.json.sha256",
    "tushare_doc_397_raw_capture.html",
    "tushare_doc_397_raw_capture.html.sha256",
)

CANDIDATE_RELATIVE = Path("data/pit/.staging/stock_st_acceptance_policy_v1_corrective_003")
FORMAL_RELATIVE = Path("data/pit/stock_st_acceptance_policies/stock_st_acceptance_policy_v1_corrective_003")
TRANSPORT_RELATIVE = Path("data/pit/stock_st_acceptance_policies/.staging_stock_st_acceptance_policy_v1_corrective_003")
RAW_CAPTURE_RELATIVE = Path("data/pit/stock_st_acceptance_policies/stock_st_acceptance_policy_v1/tushare_doc_397_raw_capture.html")
ST004_FORMAL_GUARD = Path("data/pit/stock_st_reconciled_acceptances/stacc_traderlens_v2_shsz_stock_st_004")
ST004_STAGING_GUARD = Path("data/pit/.staging/stacc_traderlens_v2_shsz_stock_st_004")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_bytes(path: Path) -> dict[str, bytes] | None:
    if not path.exists():
        return None
    return {
        file.relative_to(path).as_posix(): file.read_bytes()
        for file in sorted(path.rglob("*"))
        if file.is_file()
    }


def _publisher_module():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import publish_stock_st_acceptance_policy as publisher

    return publisher


def _setup_temp_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    source_files = (
        Path("scripts/freeze_stock_st_acceptance_policy.py"),
        Path("scripts/verify_stock_st_acceptance_policy.py"),
        Path("scripts/publish_stock_st_acceptance_policy.py"),
        Path("scripts/reconcile_stock_st_empty_outcomes.py"),
        Path("data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/manifest.json"),
        Path("data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/input_index.json"),
        Path("data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/trade_cal/part.parquet"),
        Path("data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/trade_cal/part.parquet.sha256"),
        RAW_CAPTURE_RELATIVE,
    )
    for relative in source_files:
        destination = repo_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative, destination)
    return repo_root


def _run_freeze(repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / FREEZE_SCRIPT_NAME),
            "--repo-root",
            str(repo_root),
            "--destination",
            CANDIDATE_RELATIVE.as_posix(),
            "--raw-capture",
            str(repo_root / RAW_CAPTURE_RELATIVE),
            "--retrieved-at",
            RETRIEVED_AT,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _run_publish(repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(repo_root / "scripts" / PUBLISH_SCRIPT_NAME), "--repo-root", str(repo_root)],
        capture_output=True,
        text=True,
        check=False,
    )


def _run_verify(repo_root: Path, policy_dir: Path, *, candidate_mode: bool) -> subprocess.CompletedProcess[str]:
    args = [
        sys.executable,
        str(repo_root / "scripts" / VERIFY_SCRIPT_NAME),
        "--repo-root",
        str(repo_root),
        "--policy-dir",
        str(policy_dir),
    ]
    if candidate_mode:
        args.append("--candidate-mode")
    return subprocess.run(args, capture_output=True, text=True, check=False)


def _prepare_candidate(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    repo_root = _setup_temp_repo(tmp_path)
    freeze = _run_freeze(repo_root)
    assert freeze.returncode == 0, freeze.stdout + freeze.stderr
    candidate = repo_root / CANDIDATE_RELATIVE
    formal = repo_root / FORMAL_RELATIVE
    transport = repo_root / TRANSPORT_RELATIVE
    return repo_root, candidate, formal, transport


def test_fresh_publish_is_verified_and_byte_identical(tmp_path: Path):
    repo_root, candidate, formal, transport = _prepare_candidate(tmp_path)

    result = _run_publish(repo_root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "published"
    formal_result = _run_verify(repo_root, formal, candidate_mode=False)
    assert formal_result.returncode == 0, formal_result.stdout + formal_result.stderr
    assert _tree_bytes(formal) == _tree_bytes(candidate)
    assert not transport.exists()


def test_already_published_is_typed_and_idempotent(tmp_path: Path):
    repo_root, _, _, _ = _prepare_candidate(tmp_path)
    first = _run_publish(repo_root)
    assert first.returncode == 0

    second = _run_publish(repo_root)

    assert second.returncode == 0
    assert second.stdout.strip() == "already_published"


def test_different_formal_content_conflicts_without_overwrite(tmp_path: Path):
    repo_root, candidate, formal, _ = _prepare_candidate(tmp_path)
    assert _run_publish(repo_root).returncode == 0
    formal_policy = formal / "policy.json"
    formal_policy.write_bytes(b"different formal content")
    formal_before = _tree_bytes(formal)
    candidate_before = _tree_bytes(candidate)

    result = _run_publish(repo_root)

    assert result.returncode != 0
    assert "formal content conflict" in result.stdout + result.stderr
    assert _tree_bytes(formal) == formal_before
    assert _tree_bytes(candidate) == candidate_before


def test_synchronized_candidate_tamper_rejected_before_publication(tmp_path: Path):
    repo_root, candidate, formal, transport = _prepare_candidate(tmp_path)
    baseline = _run_verify(repo_root, candidate, candidate_mode=True)
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr
    policy_path = candidate / "policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["legacy_invalid_publications"].append("tampered")
    raw = json.dumps(policy, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
    policy_path.write_bytes(raw)
    (candidate / "policy.json.sha256").write_text(hashlib.sha256(raw).hexdigest(), encoding="ascii")

    result = _run_publish(repo_root)

    assert result.returncode != 0
    assert "candidate verifier rejected" in result.stdout + result.stderr
    assert not formal.exists()
    assert not transport.exists()


def test_preexisting_exact_transport_fails_loud_and_preserves_transport(tmp_path: Path):
    repo_root, _, formal, transport = _prepare_candidate(tmp_path)
    transport.mkdir()
    (transport / "sentinel").write_bytes(b"keep")
    before = _tree_bytes(transport)

    result = _run_publish(repo_root)

    assert result.returncode != 0
    assert "transport already exists" in result.stdout + result.stderr
    assert _tree_bytes(transport) == before
    assert not formal.exists()


def test_transport_inventory_mismatch_preserves_transport(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo_root, _, formal, transport = _prepare_candidate(tmp_path)
    publisher = _publisher_module()
    original_copy = publisher._copy_artifact
    tampered = False

    def copy_then_tamper(source: Path, destination: Path):
        nonlocal tampered
        original_copy(source, destination)
        if not tampered:
            destination.write_bytes(b"tampered transport")
            tampered = True

    monkeypatch.setattr(publisher, "_copy_artifact", copy_then_tamper)

    with pytest.raises(publisher.PolicyPublicationError, match="transport inventory mismatch"):
        publisher.publish_policy(repo_root)

    assert transport.exists()
    assert not formal.exists()


def test_atomic_rename_failure_preserves_transport_without_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo_root, _, formal, transport = _prepare_candidate(tmp_path)
    publisher = _publisher_module()
    original_rename = publisher.Path.rename

    def fail_transport_rename(self: Path, target: Path):
        if self == transport and target == formal:
            raise OSError("injected atomic rename failure")
        return original_rename(self, target)

    monkeypatch.setattr(publisher.Path, "rename", fail_transport_rename)

    with pytest.raises(publisher.PolicyPublicationError, match="atomic rename failed"):
        publisher.publish_policy(repo_root)

    assert transport.exists()
    assert not formal.exists()


def test_post_rename_formal_verifier_failure_keeps_formal_and_second_call_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo_root, _, formal, transport = _prepare_candidate(tmp_path)
    publisher = _publisher_module()
    original_run_verifier = publisher._run_verifier

    def fail_formal_verifier(repo: Path, policy_dir: Path, *, candidate_mode: bool):
        if not candidate_mode:
            return subprocess.CompletedProcess(
                args=[], returncode=1, stdout="REJECTED: injected formal verifier failure", stderr=""
            )
        return original_run_verifier(repo, policy_dir, candidate_mode=candidate_mode)

    monkeypatch.setattr(publisher, "_run_verifier", fail_formal_verifier)

    with pytest.raises(publisher.PolicyPublicationError, match="post-rename formal verifier rejected"):
        publisher.publish_policy(repo_root)
    assert formal.exists()
    assert not transport.exists()

    with pytest.raises(publisher.PolicyPublicationError, match="formal verifier rejected"):
        publisher.publish_policy(repo_root)
    assert formal.exists()
    assert not transport.exists()


def test_verifier_candidate_and_formal_exact_path_boundaries_remain_real(tmp_path: Path):
    repo_root, candidate, formal, _ = _prepare_candidate(tmp_path)
    wrong_candidate_mode = _run_verify(repo_root, candidate, candidate_mode=False)
    wrong_formal_mode = _run_verify(repo_root, candidate, candidate_mode=True)

    assert wrong_candidate_mode.returncode != 0
    assert "formal mode only accepts" in wrong_candidate_mode.stdout + wrong_candidate_mode.stderr
    assert wrong_formal_mode.returncode == 0
    assert not formal.exists()


def test_stock_st_004_absence_positive_guard_allows_publish(tmp_path: Path):
    repo_root, _, _, _ = _prepare_candidate(tmp_path)

    assert not (repo_root / ST004_FORMAL_GUARD).exists()
    assert not (repo_root / ST004_STAGING_GUARD).exists()
    result = _run_publish(repo_root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "published"


@pytest.mark.parametrize("guard_relative", [ST004_FORMAL_GUARD, ST004_STAGING_GUARD])
def test_stock_st_004_guard_rejects_before_any_policy_write(tmp_path: Path, guard_relative: Path):
    repo_root, candidate, formal, transport = _prepare_candidate(tmp_path)
    guard = repo_root / guard_relative
    guard.mkdir(parents=True)
    candidate_before = _tree_bytes(candidate)

    result = _run_publish(repo_root)

    assert result.returncode != 0
    assert "stock_st_004_guard_present" in result.stdout + result.stderr
    assert _tree_bytes(candidate) == candidate_before
    assert not formal.exists()
    assert not transport.exists()
