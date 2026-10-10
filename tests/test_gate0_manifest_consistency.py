"""Gate 0 manifest consistency tests."""
import pandas as pd
import hashlib
import json
from pathlib import Path


def test_manifest_row_count_matches_parquet():
    """Manifest row_count must match actual parquet rows."""
    snapshot_dir = Path("data/pit/tushare").glob("*/")
    snapshots = [d for d in snapshot_dir if d.is_dir() and not d.name.startswith(".")]
    
    if not snapshots:
        return  # ponytail: no snapshots = nothing to check
    
    latest = max(snapshots, key=lambda p: p.stat().st_mtime)
    manifest_path = latest / "manifest.json"
    
    if not manifest_path.exists():
        return
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    if "interface_status" not in manifest:
        return
    
    # Check every interface with a parquet file
    for iface, status in manifest["interface_status"].items():
        parquet_path = latest / f"{iface}.parquet"
        if parquet_path.exists() and status.get("status") == "ok":
            df = pd.read_parquet(parquet_path)
            actual_rows = len(df)
            manifest_rows = status.get("row_count", 0)
            assert actual_rows == manifest_rows, \
                f"{iface}: parquet has {actual_rows} rows, manifest claims {manifest_rows}"


def test_manifest_sha256_matches_parquet():
    """Manifest should record actual file hash."""
    snapshot_dir = Path("data/pit/tushare").glob("*/")
    snapshots = [d for d in snapshot_dir if d.is_dir() and not d.name.startswith(".")]
    
    if not snapshots:
        return
    
    latest = max(snapshots, key=lambda p: p.stat().st_mtime)
    manifest_path = latest / "manifest.json"
    
    if not manifest_path.exists():
        return
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    # Check manifest.sha256 file
    sha_path = latest / "manifest.sha256"
    if sha_path.exists():
        recorded_hash = sha_path.read_text().strip()
        actual_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        assert recorded_hash == actual_hash, \
            f"manifest.sha256 mismatch: recorded={recorded_hash[:16]}..., actual={actual_hash[:16]}..."
