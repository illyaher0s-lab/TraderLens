"""Helper to build positive fixture for verifier tests."""
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.verify_stock_st_reconciled_acceptance import compute_hash


def build_positive_fixture(repo_root: Path) -> Path:
    """
    Build a complete valid artifact fixture in tempdir.
    
    Returns temp artifact root path (caller must keep tempdir alive).
    """
    tmpdir = TemporaryDirectory()
    fake_artifact = Path(tmpdir.name) / "stacc_traderlens_v2_shsz_stock_st_valid_fixture"
    
    # ponytail: copy _003 as base
    base = repo_root / "data/pit/stock_st_reconciled_acceptances/stacc_traderlens_v2_shsz_stock_st_003"
    shutil.copytree(base, fake_artifact)
    
    # ponytail: update artifact_id
    manifest = json.loads((fake_artifact / "manifest.json").read_text())
    manifest["artifact_id"] = "stacc_traderlens_v2_shsz_stock_st_valid_fixture"
    
    # ponytail: add complete cross-bindings (minimal for acceptance)
    manifest["tushare_contract_doc_id"] = 397
    manifest["b3_package_id"] = "b3eip_traderlens_v2_shsz_pit_001"
    manifest["b3_input_index_hash"] = "5053860cd35734d1e0a4435d60653b46cb74f594e365eab5f29da895e9ab30b7"
    
    (fake_artifact / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    
    # ponytail: update sidecar
    manifest_hash = compute_hash(fake_artifact / "manifest.json")
    (fake_artifact / "manifest.json.sha256").write_text(manifest_hash)
    
    return fake_artifact, tmpdir


if __name__ == "__main__":
    repo_root = Path(__file__).parent.parent
    fixture, tmpdir = build_positive_fixture(repo_root)
    print(f"Built fixture: {fixture}")
    
    # ponytail: verify it
    import subprocess
    result = subprocess.run(
        [sys.executable, "scripts/verify_stock_st_reconciled_acceptance.py",
         "--repo-root", str(repo_root), "--artifact-root", str(fixture)],
        capture_output=True, text=True
    )
    print(result.stdout)
    print(f"Exit code: {result.returncode}")
    
    input("Press Enter to cleanup tempdir...")
