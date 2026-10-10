"""V2 formal snapshot manifest publication - metadata only."""
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from backend.services.b3_protocol_types import CoverageDisclosure, DataSnapshotManifest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _content_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _existing_matches(manifest_path: Path, payload: dict) -> bool:
    sidecar_path = manifest_path.with_suffix(".json.sha256")
    if not manifest_path.is_file() or not sidecar_path.is_file():
        raise ValueError(f"Incomplete existing artifact: {manifest_path.parent}")
    if sidecar_path.read_text(encoding="utf-8").strip() != _sha256(manifest_path):
        raise ValueError(f"Existing artifact sidecar mismatch: {manifest_path}")
    existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = dict(payload)
    expected["manifest_content_hash"] = _content_hash(payload)
    return existing == expected


def publish_universe_reference(
    universe_reference_id: str,
    sw2021_membership_manifest_sha256: str,
    sw2021_universe_candidate_sha256: str,
    universe_definition_hash: str,
    source_taxonomy: str,
    output_dir: Path,
) -> dict:
    """Publish metadata-only universe reference."""
    ref_dir = output_dir / universe_reference_id
    manifest_path = ref_dir / "manifest.json"
    
    candidate = {
        "universe_reference_id": universe_reference_id,
        "sw2021_membership_manifest_sha256": sw2021_membership_manifest_sha256,
        "sw2021_universe_candidate_sha256": sw2021_universe_candidate_sha256,
        "universe_definition_hash": universe_definition_hash,
        "source_taxonomy": source_taxonomy,
        "provenance_only": True,
        "not_authorized_for_b6_oos_gate_promotion_signal": True,
    }
    if ref_dir.exists():
        if _existing_matches(manifest_path, candidate):
            return {"status": "already_published", "universe_reference_id": universe_reference_id}
        raise ValueError(f"Universe reference {universe_reference_id} exists with different content")
    
    ref_dir.mkdir(parents=True)
    manifest = dict(candidate)
    manifest["manifest_content_hash"] = _content_hash(candidate)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (ref_dir / "manifest.json.sha256").write_text(_sha256(manifest_path), encoding="utf-8")
    
    return {"status": "published", "universe_reference_id": universe_reference_id}


def publish_data_snapshot_manifest(
    snapshot_id: str,
    provider: str,
    market_data_start,
    market_data_end,
    semantic_hash: str,
    universe_reference_ids: tuple[str, ...],
    coverage_package_id: str,
    coverage_manifest_sha256: str,
    expected_stock_days: int,
    complete_stock_days: int,
    unavailable_stock_days: int,
    field_missing_counts: dict,
    source_manifest_hashes: dict[str, str],
    output_dir: Path,
) -> dict:
    """Publish formal data snapshot manifest."""
    from datetime import date
    
    snap_dir = output_dir / snapshot_id
    manifest_path = snap_dir / "manifest.json"
    
    if not source_manifest_hashes:
        raise ValueError("source_manifest_hashes is required")
    # ponytail: sort deterministic metadata once
    sorted_counts = tuple(sorted(field_missing_counts.items()))
    sorted_source_hashes = tuple(sorted(source_manifest_hashes.items()))
    
    disclosure = CoverageDisclosure(
        coverage_package_id=coverage_package_id,
        coverage_manifest_sha256=coverage_manifest_sha256,
        expected_stock_days=expected_stock_days,
        complete_stock_days=complete_stock_days,
        unavailable_stock_days=unavailable_stock_days,
        field_missing_counts=sorted_counts,
    )
    DataSnapshotManifest(
        snapshot_id=snapshot_id,
        provider=provider,
        retrieval_date=None,
        retrieval_date_status="unknown",
        market_data_start=market_data_start,
        market_data_end=market_data_end,
        universe_snapshot_ids=(),
        universe_reference_ids=universe_reference_ids,
        semantic_hash=semantic_hash,
        quality_status="ok",
        gaps=("availability_limited",),
        coverage_disclosure=disclosure,
        source_manifest_hashes=sorted_source_hashes,
    )
    
    # ponytail: reuse existing timestamp if idempotent
    if snap_dir.exists():
        existing_manifest = json.loads(manifest_path.read_text())
        published_at = datetime.fromisoformat(existing_manifest["manifest_published_at"])
        
        # Build candidate manifest
        candidate_dict = {
            "snapshot_id": snapshot_id,
            "provider": provider,
            "retrieval_date": None,
            "market_data_start": market_data_start.isoformat() if isinstance(market_data_start, date) else market_data_start,
            "market_data_end": market_data_end.isoformat() if isinstance(market_data_end, date) else market_data_end,
            "universe_snapshot_ids": [],
            "semantic_hash": semantic_hash,
            "quality_status": "ok",
            "gaps": ["availability_limited"],
            "frozen": True,
            "retrieval_date_status": "unknown",
            "manifest_published_at": published_at.isoformat(),
            "universe_reference_ids": list(universe_reference_ids),
            "coverage_disclosure": {
                "coverage_package_id": disclosure.coverage_package_id,
                "coverage_manifest_sha256": disclosure.coverage_manifest_sha256,
                "expected_stock_days": disclosure.expected_stock_days,
                "complete_stock_days": disclosure.complete_stock_days,
                "unavailable_stock_days": disclosure.unavailable_stock_days,
                "field_missing_counts": list(disclosure.field_missing_counts),
            },
            "source_manifest_hashes": list(sorted_source_hashes),
            "not_authorized_for_b6_oos_gate_promotion_signal": True,
        }
        candidate_content_hash = _content_hash(candidate_dict)
        candidate_dict["manifest_content_hash"] = candidate_content_hash
        
        # ponytail: compare canonical JSON
        existing_canonical = json.dumps(existing_manifest, sort_keys=True)
        candidate_canonical = json.dumps(candidate_dict, sort_keys=True)
        if existing_canonical == candidate_canonical:
            return {"status": "already_published", "snapshot_id": snapshot_id}
        raise ValueError(f"Snapshot {snapshot_id} exists with different content")
    else:
        published_at = datetime.utcnow()
    
    # Build manifest without content hash
    manifest_dict = {
        "snapshot_id": snapshot_id,
        "provider": provider,
        "retrieval_date": None,
        "market_data_start": market_data_start.isoformat() if isinstance(market_data_start, date) else market_data_start,
        "market_data_end": market_data_end.isoformat() if isinstance(market_data_end, date) else market_data_end,
        "universe_snapshot_ids": [],
        "semantic_hash": semantic_hash,
        "quality_status": "ok",
        "gaps": ["availability_limited"],
        "frozen": True,
        "retrieval_date_status": "unknown",
        "manifest_published_at": published_at.isoformat(),
        "universe_reference_ids": list(universe_reference_ids),
        "coverage_disclosure": {
            "coverage_package_id": disclosure.coverage_package_id,
            "coverage_manifest_sha256": disclosure.coverage_manifest_sha256,
            "expected_stock_days": disclosure.expected_stock_days,
            "complete_stock_days": disclosure.complete_stock_days,
            "unavailable_stock_days": disclosure.unavailable_stock_days,
            "field_missing_counts": list(disclosure.field_missing_counts),
        },
        "source_manifest_hashes": list(sorted_source_hashes),
        "not_authorized_for_b6_oos_gate_promotion_signal": True,
    }
    
    # Compute content hash
    content_hash = _content_hash(manifest_dict)
    manifest_dict["manifest_content_hash"] = content_hash
    
    if snap_dir.exists():
        if _sha256(manifest_path) == hashlib.sha256(json.dumps(manifest_dict, indent=2).encode()).hexdigest():
            return {"status": "already_published", "snapshot_id": snapshot_id}
        raise ValueError(f"Snapshot {snapshot_id} exists with different content")
    
    snap_dir.mkdir(parents=True)
    manifest_path.write_text(json.dumps(manifest_dict, indent=2))
    (snap_dir / "manifest.json.sha256").write_text(_sha256(manifest_path))
    
    return {"status": "published", "snapshot_id": snapshot_id, "manifest_content_hash": content_hash}
