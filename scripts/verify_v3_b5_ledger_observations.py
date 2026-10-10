"""Independent verifier for v3 B5 ledger-replayed observations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.services.v3_b5_ledger_observation import (
    OBSERVATION_SCHEMA,
    authoritative_final_match,
    canonical_bytes,
    replay_ledger,
    sha256_bytes,
    sha256_file,
    validate_observation_rows,
)
from scripts.publish_v3_b5_ledger_observations import (
    B4_ID,
    B4_EVENT_SHA,
    B4_MANIFEST_SHA,
    FORMAL_SNAPSHOT_HASH,
    IS_END,
    IS_START,
    OOS_START,
    OUTPUT_ROOT,
    PROTOCOL_ID,
    REVISION_ID,
    ROOT,
    SUPPLEMENT_ID,
    SUPPLEMENT_MANIFEST_SHA,
    _load_b4,
    _load_formal_manifest,
    _load_immutable_trading_supplement,
    _load_lineage,
    _load_protocol,
    _producer_source_bindings,
    _sidecar_hash,
    _source,
)
from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
from scripts.run_v3_b4_is_once import _ReadBoundDataSource
from strategy_core.v3_relative_strength_executor import V3RelativeStrengthExecutionSpec


def _canonical_final_comparison(value: object) -> dict:
    """Normalize only JSON list/tuple representation without weakening fields."""
    if not isinstance(value, dict):
        raise ValueError("final comparison must be an object")
    required = {"all_equal", "average_cost", "cash", "last_price", "portfolio_value", "positions_symbol_quantity", "snapshot_date"}
    if set(value) != required:
        raise ValueError("final comparison fields mismatch")
    positions = value["positions_symbol_quantity"]
    if not isinstance(positions, dict) or set(positions) != {"actual", "equal", "expected"}:
        raise ValueError("final comparison positions must contain actual/expected/equal")

    def normalize_pairs(raw: object) -> tuple[tuple[str, int], ...]:
        if not isinstance(raw, (list, tuple)):
            raise ValueError("final comparison positions must be ordered pairs")
        normalized_pairs = []
        for pair in raw:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError("final comparison position pair mismatch")
            symbol, quantity = pair
            if not isinstance(symbol, str) or not symbol or isinstance(quantity, bool) or not isinstance(quantity, int):
                raise ValueError("final comparison position field mismatch")
            normalized_pairs.append((symbol, quantity))
        return tuple(normalized_pairs)

    normalized_positions = dict(positions)
    normalized_positions["actual"] = normalize_pairs(positions["actual"])
    normalized_positions["expected"] = normalize_pairs(positions["expected"])
    normalized = dict(value)
    normalized["positions_symbol_quantity"] = normalized_positions
    return normalized


def verify_artifact(artifact_dir: Path, *, repo_root: Path = ROOT) -> dict:
    directory = Path(artifact_dir)
    repo_root = Path(repo_root).resolve()
    manifest_path = directory / "manifest.json"
    observations_path = directory / "observations.json"
    manifest_sha = _sidecar_hash(manifest_path)
    observation_sha = _sidecar_hash(observations_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    observations = json.loads(observations_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != OBSERVATION_SCHEMA or manifest.get("status") != "valid":
        raise ValueError("ledger observation schema/status mismatch")
    if manifest.get("not_authorized_for_b6_oos_gate_promotion_signal") is not True:
        raise ValueError("ledger observation authorization disclosure mismatch")
    if manifest.get("observations", {}).get("sha256") != observation_sha or observation_sha != sha256_bytes(canonical_bytes(observations)):
        raise ValueError("observation content hash mismatch")
    payload = {key: value for key, value in manifest.items() if key != "artifact_id"}
    expected_id = sha256_bytes(canonical_bytes(payload))[:16]
    if manifest.get("artifact_id") != expected_id or directory.name != expected_id:
        raise ValueError("ledger observation artifact identity mismatch")
    protocol, protocol_payload_sha = _load_protocol(repo_root)
    b4_manifest, event, b4_manifest_sha, b4_event_sha = _load_b4(repo_root)
    formal_manifest, formal_payload, formal_manifest_sha = _load_formal_manifest(repo_root)
    supplement = _load_immutable_trading_supplement(repo_root)
    if b4_manifest_sha != B4_MANIFEST_SHA or b4_event_sha != B4_EVENT_SHA or event.backtest_start != IS_START or event.backtest_end != IS_END:
        raise ValueError("B4 predecessor mismatch")
    if protocol.protocol_snapshot_id != PROTOCOL_ID or protocol.strategy_revision_id != REVISION_ID or protocol.data_snapshot_hash != FORMAL_SNAPSHOT_HASH:
        raise ValueError("protocol identity mismatch")
    raw_source = FormalPITPartitionAdapter(repo_root)
    dates = raw_source.common_trading_dates(IS_START, IS_END)
    if len(dates) != 176 or dates[0] != IS_START or dates[-1] != IS_END:
        raise ValueError("calendar date set mismatch")
    audited_source = _ReadBoundDataSource(raw_source, IS_END, enable_batch_endpoints=False)
    spec = V3RelativeStrengthExecutionSpec(
        strategy_revision_id=REVISION_ID,
        protocol_snapshot_id=PROTOCOL_ID,
        data_snapshot_hash=formal_manifest.semantic_hash,
        supplement_id=SUPPLEMENT_ID,
        backtest_start=IS_START,
        backtest_end=IS_END,
    )
    replay = replay_ledger(event, audited_source, dates, initial_capital=spec.initial_capital)
    validate_observation_rows(observations, dates)
    if observations != list(replay.observations):
        raise ValueError("replayed observations differ from artifact")
    final_match = authoritative_final_match(replay.portfolio, event.final_portfolio)
    if not final_match.get("all_equal"):
        raise ValueError("authoritative final fields do not match")
    if _canonical_final_comparison(manifest.get("authoritative_final_match")) != _canonical_final_comparison(final_match):
        raise ValueError("final comparison audit mismatch")
    source_hashes = _producer_source_bindings(repo_root)
    if manifest.get("producer_source_hashes") != source_hashes:
        raise ValueError("producer source hash mismatch")
    audit = audited_source.audit()
    if audit["oos_read_count"] != 0 or audit["max_requested_date"] is None or audit["max_requested_date"] >= OOS_START.isoformat():
        raise ValueError("independent verification read OOS")
    if manifest.get("read_audit", {}).get("oos_read_count") != 0 or manifest.get("read_audit", {}).get("max_requested_date") != audit.get("max_requested_date"):
        raise ValueError("read audit mismatch")
    if manifest.get("fills", {}).get("count") != len(event.fills) or manifest.get("fills", {}).get("consumed_once") is not True:
        raise ValueError("fill ledger audit mismatch")
    if any(replay.operation_counts.get(name, 0) != 0 for name in ("rank_snapshot", "entry_symbols", "exit_symbols", "confirmation", "derive_liquidity", "market_regime", "entry_generation", "exit_generation")):
        raise ValueError("ledger replay invoked strategy decision logic")
    return {"status": "verified", "artifact_id": expected_id, "path": str(directory), "manifest_sha256": manifest_sha, "observations_sha256": observation_sha, "observation_count": len(observations), "fill_count": len(event.fills), "oos_read_count": audit["oos_read_count"], "max_requested_date": audit["max_requested_date"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_artifact(args.artifact_dir), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
