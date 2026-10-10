# ponytail: fake minimal fixtures for B6 tests, avoid copy-paste
import sqlite3
from datetime import date, datetime
from pathlib import Path

from backend.db.strategy import StrategyDB
from backend.services.oos_budget_ledger import OOSBudgetLedger
from contracts.strategy import (
    StrategyDraft, StrategyLifecycleState, ResearchProtocolSnapshot,
    BacktestUniverseSpec,
)
from contracts.b6_task import B6ValidationTask


def setup_minimal_b6_db(path):
    """Setup DB + draft + protocol + universe + task. Returns (db, ledger, draft, protocol, task_id)."""
    db = StrategyDB(str(path))
    ledger = OOSBudgetLedger(db)
    
    db.store_backtest_universe(BacktestUniverseSpec(
        universe_spec_id="u", universe_rule_type="point_in_time_membership",
        membership_source="t", membership_effective_from=date(2024,1,1),
        membership_effective_to=date(2024,12,31), snapshot_date=date(2024,1,1),
        membership_snapshot_ids=("s",), quality_status="ok"
    ))
    
    draft = StrategyDraft(
        strategy_revision_id="r", theme_id="t", hypothesis_id="h",
        strategy_template_id="tpl", strategy_template_version="v1",
        strategy_template_hash="hash", hypothesis_source_snapshot_id="hs",
        backtest_universe_spec_id="u", strategy_config_json="{}",
        sample_split_rule_id="split", created_at=datetime.now()
    )
    
    protocol = ResearchProtocolSnapshot(
        protocol_snapshot_id="p", theme_id="t", hypothesis_source_snapshot_id="hs",
        strategy_revision_id="r", sample_split_rule_id="split",
        oos_window_rule_id="w", oos_window_rule_params_json="{}",
        oos_window_start=date(2024,1,1), oos_window_end=date(2024,12,31),
        shared_oos_window_id="w", backtest_universe_spec_id="u",
        strategy_config_hash="ch", data_snapshot_id="d", data_snapshot_hash="dh",
        kill_criteria_snapshot_id="k", prototype_gate_thresholds_json="{}",
        gate_criteria_hash="gh", frozen_at=datetime.now(), frozen_by="test"
    )
    
    db.create_strategy_draft(draft, StrategyLifecycleState(
        lifecycle_state_id="ls", strategy_revision_id="r", state_version=1,
        state="draft", source_record_id="init", recorded_at=datetime.now(), recorded_by="test"
    ))
    db.store_protocol_snapshot(protocol)
    
    return db, ledger, draft, protocol


def fake_manifest():
    """Minimal DataSnapshotManifest."""
    from backend.services.b3_protocol_types import DataSnapshotManifest
    return DataSnapshotManifest(
        snapshot_id="d", provider="t", retrieval_date=date(2024,1,1),
        market_data_start=date(2024,1,1), market_data_end=date(2024,12,31),
        adjustment_factor_fingerprint="fp", universe_snapshot_ids=("s",),
        semantic_hash="sh", quality_status="ok", gaps=()
    )


def fake_universe():
    """Minimal PointInTimeMembershipSnapshot (matches BacktestUniverseSpec)."""
    from backend.services.b3_protocol_types import PointInTimeMembershipSnapshot
    return PointInTimeMembershipSnapshot(
        snapshot_id="s", snapshot_date=date(2024,1,1),
        universe_rule_type="point_in_time_membership", membership_source="t",
        include_delisted=False, records=(), quality_status="ok", gaps=()
    )


def fake_b4_qualification():
    """Minimal B4 qualification dict."""
    return {"status": "passed"}


def fake_b4_event():
    """Minimal B4 event result."""
    return {"status": "completed"}
