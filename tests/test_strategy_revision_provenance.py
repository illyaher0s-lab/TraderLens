"""Task 2/4 Phase B: Strategy Revision Approval Provenance validator tests.

Real file-backed DBs, real StrategyDB.create_strategy_draft(), Phase A fixtures.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest

from backend.db.research import ResearchDB
from backend.db.strategy import StrategyDB
from backend.db.agent_workbench import init_agent_workbench_db
from contracts.research import CandidateStock, ThemeInput
from contracts.strategy import StrategyDraft, StrategyLifecycleState
from tests.approval_context_fixtures import attach_continued_approval


@pytest.fixture
def research_db(tmp_path):
    db = ResearchDB(str(tmp_path / "research.db"))
    init_agent_workbench_db(db.conn)
    yield db
    db.conn.close()


@pytest.fixture
def strategy_db(tmp_path):
    db = StrategyDB(str(tmp_path / "strategy.db"))
    yield db
    db.conn.close()


def _theme_candidate_evidence(db: ResearchDB, theme_id: str, candidate_id: str):
    """ponytail: shared fixture setup"""
    now = datetime.now()
    db.create_theme(
        ThemeInput(
            theme_id=theme_id,
            theme_name="Test",
            background="Test",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
    )
    db.add_candidate(
        CandidateStock(
            candidate_id=candidate_id,
            theme_id=theme_id,
            symbol="600000.SH",
            source_type="manual_theme",
            match_reason="Test",
            status="raw",
            created_at=now,
        )
    )
    # evidence snapshot
    snap_id = f"snap_{candidate_id}"
    db.conn.execute(
        "INSERT INTO evidence_snapshots (snapshot_id, candidate_id, symbol, evidence_output, created_at) VALUES (?, ?, ?, ?, ?)",
        (snap_id, candidate_id, "600000.SH", "{}", now.isoformat()),
    )
    db.conn.commit()
    return snap_id


def _dual_db_snapshot(research_db: ResearchDB, strategy_db) -> tuple[str, str]:
    """Canonical snapshot of both databases. ponytail: deterministic dump."""
    # Get DB file paths
    research_path = research_db.conn.execute("PRAGMA database_list").fetchone()[2]
    strategy_path = strategy_db.conn.execute("PRAGMA database_list").fetchone()[2]
    
    # Independent connections for snapshot
    r_conn = sqlite3.connect(research_path)
    s_conn = sqlite3.connect(strategy_path)
    
    # Dump to sorted strings
    r_dump = "\n".join(sorted(line for line in r_conn.iterdump() if not line.startswith("-- ")))
    s_dump = "\n".join(sorted(line for line in s_conn.iterdump() if not line.startswith("-- ")))
    
    r_conn.close()
    s_conn.close()
    
    return (r_dump, s_dump)


def test_complete_chain_valid(research_db, strategy_db):
    """Complete provenance chain validates successfully."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    # ponytail: real create_strategy_draft with FK-valid prerequisites
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_1",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id,
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_1",
            strategy_revision_id="rev_1",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    # ponytail: validator call → should pass
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_1")
    assert result.is_valid
    
    # Dual-DB zero-write verification
    before_r, before_s = _dual_db_snapshot(research_db, strategy_db)
    result2 = validate_strategy_revision_provenance(strategy_db, research_db, "rev_1")
    after_r, after_s = _dual_db_snapshot(research_db, strategy_db)
    
    assert before_r == after_r, "ResearchDB modified by validator"
    assert before_s == after_s, "StrategyDB modified by validator"


def test_revision_not_found(research_db, strategy_db):
    """Nonexistent revision_id rejected (no latest fallback)."""
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "nonexistent")
    assert not result.is_valid
    assert result.reason_code == "strategy_revision_provenance_unavailable"


def test_missing_source_fields(research_db, strategy_db):
    """Draft without source_approval_card_id/source_confirmed_candidate_id rejected."""
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="legacy_1",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id="snap_1",
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        # ponytail: no source fields
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_legacy",
            strategy_revision_id="legacy_1",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "legacy_1")
    assert not result.is_valid
    assert result.reason_code == "strategy_revision_provenance_unavailable"


def test_empty_source_fields(research_db, strategy_db):
    """Empty/whitespace source IDs rejected."""
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="empty_1",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id="snap_1",
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id="  ",  # ponytail: whitespace
        source_confirmed_candidate_id="",
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_empty",
            strategy_revision_id="empty_1",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "empty_1")
    assert not result.is_valid
    assert result.reason_code == "strategy_revision_provenance_unavailable"


def test_confirmed_not_found(research_db, strategy_db):
    """Confirmed candidate doesn't exist."""
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_2",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id="snap_1",
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id="card_1",
        source_confirmed_candidate_id="nonexistent",
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_2",
            strategy_revision_id="rev_2",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_2")
    assert not result.is_valid
    assert result.reason_code == "source_confirmed_candidate_unavailable"


def test_approval_card_not_found(research_db, strategy_db):
    """Approval card doesn't exist."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_3",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id="nonexistent_card",
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_3",
            strategy_revision_id="rev_3",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_3")
    assert not result.is_valid
    assert result.reason_code == "source_approval_card_unavailable"


def test_workflow_id_not_equal_session_id(research_db, strategy_db):
    """card.workflow_id != session_id rejected."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    # ponytail: corrupt workflow_id after confirmation
    cursor = research_db.conn.cursor()
    cursor.execute("SELECT card_data FROM agent_approval_cards WHERE approval_card_id = ?", (card_id,))
    card_json = cursor.fetchone()[0]
    card_dict = json.loads(card_json)
    card_dict["workflow_id"] = "wrong_workflow"
    research_db.conn.execute(
        "UPDATE agent_approval_cards SET card_data = ? WHERE approval_card_id = ?",
        (json.dumps(card_dict), card_id)
    )
    research_db.conn.commit()
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_workflow",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id,
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_workflow",
            strategy_revision_id="rev_workflow",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_workflow")
    assert not result.is_valid
    assert result.reason_code == "approval_candidate_binding_mismatch"


def test_card_confirmed_id_mismatch(research_db, strategy_db):
    """confirmed.approval_card_id != draft.source_approval_card_id."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1")
    card_id_2 = attach_continued_approval(research_db, "theme_1", session_id="session_2", approval_card_id="card_2")  # ponytail: different session
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_4",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id_2,  # ponytail: wrong card
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_4",
            strategy_revision_id="rev_4",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_4")
    assert not result.is_valid
    assert result.reason_code == "approval_candidate_binding_mismatch"


def test_theme_mismatch(research_db, strategy_db):
    """confirmed.theme_id != draft.theme_id."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_5",
        theme_id="theme_wrong",  # ponytail: mismatch
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id,
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_5",
            strategy_revision_id="rev_5",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_5")
    assert not result.is_valid
    assert result.reason_code == "approval_candidate_binding_mismatch"


def test_corrupt_card_json_fail_loud(research_db, strategy_db):
    """Corrupt card_data JSON fails loudly (not typed unavailable)."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    # ponytail: corrupt card_data
    research_db.conn.execute(
        "UPDATE agent_approval_cards SET card_data = ? WHERE approval_card_id = ?",
        ("{corrupt", card_id)
    )
    research_db.conn.commit()
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_6",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id,
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_6",
            strategy_revision_id="rev_6",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        validate_strategy_revision_provenance(strategy_db, research_db, "rev_6")


def test_contract_invalid_card_fail_loud(research_db, strategy_db):
    """Contract-invalid ApprovalCard (valid JSON, invalid contract) fails with pydantic.ValidationError."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    # ponytail: valid JSON but missing required contract fields
    research_db.conn.execute(
        "UPDATE agent_approval_cards SET card_data = ? WHERE approval_card_id = ?",
        ('{"approval_card_id": "card_theme_1", "workflow_id": "session_theme_1"}', card_id)
    )
    research_db.conn.commit()
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_contract",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id,
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_contract",
            strategy_revision_id="rev_contract",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        validate_strategy_revision_provenance(strategy_db, research_db, "rev_contract")


def test_card_decision_not_continue(research_db, strategy_db):
    """Card decision != 'continue' is rejected."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1", approval_card_id="card_stopped")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    # ponytail: modify decision to 'stop' AFTER confirmation to create invalid state
    cursor = research_db.conn.cursor()
    cursor.execute(
        "SELECT card_data FROM agent_approval_cards WHERE approval_card_id = ?",
        (card_id,)
    )
    card_json = cursor.fetchone()[0]
    card_dict = json.loads(card_json)
    card_dict["decision"] = "stop"
    research_db.conn.execute(
        "UPDATE agent_approval_cards SET card_data = ? WHERE approval_card_id = ?",
        (json.dumps(card_dict), card_id)
    )
    research_db.conn.commit()
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_decision",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id,
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_decision",
            strategy_revision_id="rev_decision",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_decision")
    assert not result.is_valid
    assert result.reason_code == "approval_candidate_binding_mismatch"


def test_session_artifact_ref_missing(research_db, strategy_db):
    """Session has no artifact_ref for the theme."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    # ponytail: delete session artifact_ref after confirmation to create invalid state
    research_db.conn.execute(
        "DELETE FROM agent_artifact_refs WHERE session_id = ? AND artifact_id = ?",
        ("session_theme_1", "theme_1")
    )
    research_db.conn.commit()
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_artifact_ref",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id,
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_artifact_ref",
            strategy_revision_id="rev_artifact_ref",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_artifact_ref")
    assert not result.is_valid
    assert result.reason_code == "approval_candidate_binding_mismatch"


def test_theme_in_session_but_not_in_card_artifact_ids(research_db, strategy_db):
    """Theme exists in session artifacts but NOT in card.artifact_ids."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    # ponytail: modify card.artifact_ids after confirmation to create invalid state
    cursor = research_db.conn.cursor()
    cursor.execute(
        "SELECT card_data FROM agent_approval_cards WHERE approval_card_id = ?",
        (card_id,)
    )
    card_json = cursor.fetchone()[0]
    card_dict = json.loads(card_json)
    card_dict["artifact_ids"] = ["theme_other"]  # remove theme_1
    research_db.conn.execute(
        "UPDATE agent_approval_cards SET card_data = ? WHERE approval_card_id = ?",
        (json.dumps(card_dict), card_id)
    )
    research_db.conn.commit()
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_card_artifact",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id,
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_card_artifact",
            strategy_revision_id="rev_card_artifact",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_card_artifact")
    assert not result.is_valid
    assert result.reason_code == "approval_candidate_binding_mismatch"


def test_original_candidate_not_exists(research_db, strategy_db):
    """Original candidate row deleted after confirmation."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    # ponytail: delete original candidate
    research_db.conn.execute("DELETE FROM research_candidates WHERE candidate_id = ?", ("cand_1",))
    research_db.conn.commit()
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_cand_missing",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id,
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_cand_missing",
            strategy_revision_id="rev_cand_missing",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_cand_missing")
    assert not result.is_valid
    assert result.reason_code == "approval_candidate_binding_mismatch"


def test_original_candidate_symbol_mismatch(research_db, strategy_db):
    """Original candidate symbol != confirmed.symbol."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    # ponytail: corrupt candidate symbol
    research_db.conn.execute(
        "UPDATE research_candidates SET symbol = ? WHERE candidate_id = ?",
        ("601999.SH", "cand_1")
    )
    research_db.conn.commit()
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_cand_symbol",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id,
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_cand_symbol",
            strategy_revision_id="rev_cand_symbol",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_cand_symbol")
    assert not result.is_valid
    assert result.reason_code == "approval_candidate_binding_mismatch"


def test_primary_evidence_not_in_evidence_ids(research_db, strategy_db):
    """primary_evidence_snapshot_id not in evidence_snapshot_ids."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    snap_id_other = f"snap_other"
    research_db.conn.execute(
        "INSERT INTO evidence_snapshots (snapshot_id, candidate_id, symbol, evidence_output, created_at) VALUES (?, ?, ?, ?, ?)",
        (snap_id_other, "cand_1", "600000.SH", "{}", datetime.now().isoformat()),
    )
    research_db.conn.commit()
    
    card_id = attach_continued_approval(research_db, "theme_1")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id_other],  # ponytail: primary not in list
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_primary_not_in",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id,
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_primary_not_in",
            strategy_revision_id="rev_primary_not_in",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_primary_not_in")
    assert not result.is_valid
    assert result.reason_code == "approval_candidate_binding_mismatch"


def test_evidence_snapshot_truly_missing(research_db, strategy_db):
    """Evidence snapshot row truly doesn't exist."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    # ponytail: delete evidence snapshot after confirmation
    research_db.conn.execute("DELETE FROM evidence_snapshots WHERE snapshot_id = ?", (snap_id,))
    research_db.conn.commit()
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_snap_missing",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id,
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_snap_missing",
            strategy_revision_id="rev_snap_missing",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_snap_missing")
    assert not result.is_valid
    assert result.reason_code == "approval_candidate_binding_mismatch"


def test_evidence_snapshot_fetch_candidate_mismatch(research_db, strategy_db):
    """Evidence snapshot exists but candidate_id doesn't match."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1")
    
    # ponytail: create second candidate with different ID
    now = datetime.now()
    research_db.add_candidate(
        CandidateStock(
            candidate_id="cand_wrong",
            theme_id="theme_1",
            symbol="600000.SH",
            source_type="manual_theme",
            match_reason="Test",
            status="raw",
            created_at=now,
        )
    )
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_wrong",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],  # ponytail: snap_id is for cand_1, not cand_wrong
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_snap_fetch",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id,
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_snap_fetch",
            strategy_revision_id="rev_snap_fetch",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_snap_fetch")
    assert not result.is_valid
    assert result.reason_code == "approval_candidate_binding_mismatch"


def test_evidence_snapshot_symbol_mismatch(research_db, strategy_db):
    """Evidence snapshot symbol != confirmed.symbol."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    # ponytail: corrupt evidence symbol
    research_db.conn.execute(
        "UPDATE evidence_snapshots SET symbol = ? WHERE snapshot_id = ?",
        ("601999.SH", snap_id)
    )
    research_db.conn.commit()
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_snap_symbol",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id,
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_snap_symbol",
            strategy_revision_id="rev_snap_symbol",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_snap_symbol")
    assert not result.is_valid
    assert result.reason_code == "approval_candidate_binding_mismatch"


def test_session_has_other_theme_only(research_db, strategy_db):
    """Session has research_case for theme_other, not theme_1."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    # ponytail: swap session artifact to theme_other after confirmation
    now = datetime.now()
    research_db.create_theme(
        ThemeInput(
            theme_id="theme_other",
            theme_name="Other",
            background="Other",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
    )
    research_db.conn.execute(
        "UPDATE agent_artifact_refs SET artifact_id = ? WHERE session_id = ? AND artifact_id = ?",
        ("theme_other", "session_theme_1", "theme_1")
    )
    research_db.conn.commit()
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_other_theme",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id,
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_other_theme",
            strategy_revision_id="rev_other_theme",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_other_theme")
    assert not result.is_valid
    assert result.reason_code == "approval_candidate_binding_mismatch"


def test_original_candidate_theme_mismatch(research_db, strategy_db):
    """Original candidate.theme_id != confirmed.theme_id."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    # ponytail: corrupt candidate theme
    research_db.conn.execute(
        "UPDATE research_candidates SET theme_id = ? WHERE candidate_id = ?",
        ("theme_wrong", "cand_1")
    )
    research_db.conn.commit()
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_cand_theme",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id,
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_cand_theme",
            strategy_revision_id="rev_cand_theme",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_cand_theme")
    assert not result.is_valid
    assert result.reason_code == "approval_candidate_binding_mismatch"


def test_primary_evidence_id_missing(research_db, strategy_db):
    """confirmed.primary_evidence_snapshot_id is None."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    # ponytail: remove primary
    research_db.conn.execute(
        "UPDATE confirmed_candidates SET primary_evidence_snapshot_id = NULL WHERE confirmed_id = ?",
        (confirmed.confirmed_id,)
    )
    research_db.conn.commit()
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    draft = StrategyDraft(
        strategy_revision_id="rev_pri_missing",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_id,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id,
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_pri_missing",
            strategy_revision_id="rev_pri_missing",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_pri_missing")
    assert not result.is_valid
    assert result.reason_code == "approval_candidate_binding_mismatch"


def test_draft_hypothesis_source_mismatch_primary(research_db, strategy_db):
    """draft.hypothesis_source_snapshot_id != confirmed.primary_evidence_snapshot_id."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    snap_other = "snap_other"
    research_db.conn.execute(
        "INSERT INTO evidence_snapshots (snapshot_id, candidate_id, symbol, evidence_output, created_at) VALUES (?, ?, ?, ?, ?)",
        (snap_other, "cand_1", "600000.SH", "{}", datetime.now().isoformat()),
    )
    research_db.conn.commit()
    
    card_id = attach_continued_approval(research_db, "theme_1")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    # ponytail: draft uses wrong hypothesis source
    draft = StrategyDraft(
        strategy_revision_id="rev_hyp_mismatch",
        theme_id="theme_1",
        hypothesis_id="hyp_1",
        strategy_template_id="tmpl_1",
        strategy_template_version="v1",
        strategy_template_hash="hash1",
        hypothesis_source_snapshot_id=snap_other,
        backtest_universe_spec_id="spec_1",
        strategy_config_json="{}",
        sample_split_rule_id="rule_1",
        created_at=datetime.now(),
        source_approval_card_id=card_id,
        source_confirmed_candidate_id=confirmed.confirmed_id,
    )
    strategy_db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="state_hyp_mismatch",
            strategy_revision_id="rev_hyp_mismatch",
            state_version=1,
            state="draft",
            source_record_id="draft",
            recorded_at=datetime.now(),
            recorded_by="test",
        ),
    )
    
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    result = validate_strategy_revision_provenance(strategy_db, research_db, "rev_hyp_mismatch")
    assert not result.is_valid
    assert result.reason_code == "approval_candidate_binding_mismatch"


@pytest.mark.parametrize("test_case", [
    "revision_not_found",
    "missing_source_fields",
    "empty_source_fields",
    "confirmed_not_found",
    "card_not_found",
    "card_confirmed_mismatch",
    "card_decision_stop",
    "theme_mismatch",
    "workflow_mismatch",
    "artifact_ref_missing",
    "card_artifact_mismatch",
    "candidate_missing",
    "candidate_theme_mismatch",
    "candidate_symbol_mismatch",
    "primary_missing",
    "primary_not_in_list",
    "hypothesis_source_mismatch",
    "evidence_snap_missing",
    "evidence_candidate_mismatch",
    "evidence_symbol_mismatch",
    "corrupt_json",
    "contract_invalid",
])
def test_all_branches_zero_write(research_db, strategy_db, test_case):
    """All validator branches (typed + fail-loud) leave both DBs unchanged."""
    snap_id = _theme_candidate_evidence(research_db, "theme_1", "cand_1")
    card_id = attach_continued_approval(research_db, "theme_1")
    
    confirmed = research_db.confirm_candidate(
        candidate_id="cand_1",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        evidence_snapshot_ids=[snap_id],
        primary_evidence_snapshot_id=snap_id,
        approval_card_id=card_id,
    )
    
    strategy_db.conn.execute(
        "INSERT INTO strategy_template_definitions VALUES (?, ?, ?, ?, ?)",
        ("tmpl_1", "v1", "{}", "hash1", datetime.now().isoformat())
    )
    strategy_db.conn.execute(
        "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
        ("spec_1", "{}", datetime.now().isoformat())
    )
    strategy_db.conn.commit()
    
    # Setup per test case - ponytail: minimal setup for each branch
    if test_case == "revision_not_found":
        rev_id = "nonexistent"
    elif test_case == "empty_source_fields":
        draft = StrategyDraft(
            strategy_revision_id="rev_empty",
            theme_id="theme_1",
            hypothesis_id="hyp_1",
            strategy_template_id="tmpl_1",
            strategy_template_version="v1",
            strategy_template_hash="hash1",
            hypothesis_source_snapshot_id=snap_id,
            backtest_universe_spec_id="spec_1",
            strategy_config_json="{}",
            sample_split_rule_id="rule_1",
            created_at=datetime.now(),
            source_approval_card_id="  ",
            source_confirmed_candidate_id="",
        )
        strategy_db.create_strategy_draft(
            draft,
            StrategyLifecycleState(
                lifecycle_state_id="state_empty",
                strategy_revision_id="rev_empty",
                state_version=1,
                state="draft",
                source_record_id="draft",
                recorded_at=datetime.now(),
                recorded_by="test",
            ),
        )
        rev_id = "rev_empty"
    elif test_case == "card_confirmed_mismatch":
        card_id_2 = attach_continued_approval(research_db, "theme_1", session_id="session_2", approval_card_id="card_2")
        draft = StrategyDraft(
            strategy_revision_id="rev_ccm",
            theme_id="theme_1",
            hypothesis_id="hyp_1",
            strategy_template_id="tmpl_1",
            strategy_template_version="v1",
            strategy_template_hash="hash1",
            hypothesis_source_snapshot_id=snap_id,
            backtest_universe_spec_id="spec_1",
            strategy_config_json="{}",
            sample_split_rule_id="rule_1",
            created_at=datetime.now(),
            source_approval_card_id=card_id_2,
            source_confirmed_candidate_id=confirmed.confirmed_id,
        )
        strategy_db.create_strategy_draft(
            draft,
            StrategyLifecycleState(
                lifecycle_state_id="state_ccm",
                strategy_revision_id="rev_ccm",
                state_version=1,
                state="draft",
                source_record_id="draft",
                recorded_at=datetime.now(),
                recorded_by="test",
            ),
        )
        rev_id = "rev_ccm"
    elif test_case in ("corrupt_json", "contract_invalid", "workflow_mismatch", "artifact_ref_missing", 
                       "card_artifact_mismatch", "candidate_missing", "candidate_theme_mismatch",
                       "candidate_symbol_mismatch", "primary_missing", "primary_not_in_list",
                       "hypothesis_source_mismatch", "evidence_snap_missing", "evidence_candidate_mismatch",
                       "evidence_symbol_mismatch", "card_decision_stop", "theme_mismatch",
                       "missing_source_fields", "confirmed_not_found", "card_not_found"):
        # ponytail: create draft, then corrupt state to trigger specific branch
        draft = StrategyDraft(
            strategy_revision_id=f"rev_{test_case[:4]}",
            theme_id="theme_wrong" if test_case == "theme_mismatch" else "theme_1",
            hypothesis_id="hyp_1",
            strategy_template_id="tmpl_1",
            strategy_template_version="v1",
            strategy_template_hash="hash1",
            hypothesis_source_snapshot_id="snap_other" if test_case == "hypothesis_source_mismatch" else snap_id,
            backtest_universe_spec_id="spec_1",
            strategy_config_json="{}",
            sample_split_rule_id="rule_1",
            created_at=datetime.now(),
            source_approval_card_id="nonexistent_card" if test_case == "card_not_found" else card_id,
            source_confirmed_candidate_id="nonexistent_confirmed" if test_case == "confirmed_not_found" else (
                confirmed.confirmed_id if test_case != "missing_source_fields" else None
            ),
        )
        strategy_db.create_strategy_draft(
            draft,
            StrategyLifecycleState(
                lifecycle_state_id=f"state_{test_case[:4]}",
                strategy_revision_id=f"rev_{test_case[:4]}",
                state_version=1,
                state="draft",
                source_record_id="draft",
                recorded_at=datetime.now(),
                recorded_by="test",
            ),
        )
        rev_id = f"rev_{test_case[:4]}"
        
        # ponytail: post-creation corruption for branches requiring it
        if test_case == "corrupt_json":
            research_db.conn.execute(
                "UPDATE agent_approval_cards SET card_data = ? WHERE approval_card_id = ?",
                ("{corrupt", card_id)
            )
            research_db.conn.commit()
        elif test_case == "contract_invalid":
            research_db.conn.execute(
                "UPDATE agent_approval_cards SET card_data = ? WHERE approval_card_id = ?",
                ('{"approval_card_id": "card_theme_1"}', card_id)
            )
            research_db.conn.commit()
        elif test_case == "workflow_mismatch":
            cursor = research_db.conn.cursor()
            cursor.execute("SELECT card_data FROM agent_approval_cards WHERE approval_card_id = ?", (card_id,))
            card_json = cursor.fetchone()[0]
            card_dict = json.loads(card_json)
            card_dict["workflow_id"] = "wrong"
            research_db.conn.execute(
                "UPDATE agent_approval_cards SET card_data = ? WHERE approval_card_id = ?",
                (json.dumps(card_dict), card_id)
            )
            research_db.conn.commit()
        elif test_case == "artifact_ref_missing":
            research_db.conn.execute(
                "DELETE FROM agent_artifact_refs WHERE session_id = ? AND artifact_id = ?",
                ("session_theme_1", "theme_1")
            )
            research_db.conn.commit()
        elif test_case == "card_artifact_mismatch":
            cursor = research_db.conn.cursor()
            cursor.execute("SELECT card_data FROM agent_approval_cards WHERE approval_card_id = ?", (card_id,))
            card_json = cursor.fetchone()[0]
            card_dict = json.loads(card_json)
            card_dict["artifact_ids"] = ["theme_other"]
            research_db.conn.execute(
                "UPDATE agent_approval_cards SET card_data = ? WHERE approval_card_id = ?",
                (json.dumps(card_dict), card_id)
            )
            research_db.conn.commit()
        elif test_case == "candidate_missing":
            research_db.conn.execute("DELETE FROM research_candidates WHERE candidate_id = ?", ("cand_1",))
            research_db.conn.commit()
        elif test_case == "candidate_theme_mismatch":
            research_db.conn.execute(
                "UPDATE research_candidates SET theme_id = ? WHERE candidate_id = ?",
                ("theme_wrong", "cand_1")
            )
            research_db.conn.commit()
        elif test_case == "candidate_symbol_mismatch":
            research_db.conn.execute(
                "UPDATE research_candidates SET symbol = ? WHERE candidate_id = ?",
                ("601999.SH", "cand_1")
            )
            research_db.conn.commit()
        elif test_case == "primary_missing":
            research_db.conn.execute(
                "UPDATE confirmed_candidates SET primary_evidence_snapshot_id = NULL WHERE confirmed_id = ?",
                (confirmed.confirmed_id,)
            )
            research_db.conn.commit()
        elif test_case == "primary_not_in_list":
            snap_other = "snap_other"
            research_db.conn.execute(
                "INSERT INTO evidence_snapshots (snapshot_id, candidate_id, symbol, evidence_output, created_at) VALUES (?, ?, ?, ?, ?)",
                (snap_other, "cand_1", "600000.SH", "{}", datetime.now().isoformat()),
            )
            research_db.conn.execute(
                "UPDATE confirmed_candidates SET evidence_snapshot_ids = ? WHERE confirmed_id = ?",
                (json.dumps([snap_other]), confirmed.confirmed_id)
            )
            research_db.conn.commit()
        elif test_case == "hypothesis_source_mismatch":
            snap_other = "snap_other"
            research_db.conn.execute(
                "INSERT INTO evidence_snapshots (snapshot_id, candidate_id, symbol, evidence_output, created_at) VALUES (?, ?, ?, ?, ?)",
                (snap_other, "cand_1", "600000.SH", "{}", datetime.now().isoformat()),
            )
            research_db.conn.commit()
        elif test_case == "evidence_snap_missing":
            research_db.conn.execute("DELETE FROM evidence_snapshots WHERE snapshot_id = ?", (snap_id,))
            research_db.conn.commit()
        elif test_case == "evidence_candidate_mismatch":
            research_db.conn.execute(
                "UPDATE evidence_snapshots SET candidate_id = ? WHERE snapshot_id = ?",
                ("cand_other", snap_id)
            )
            research_db.conn.commit()
        elif test_case == "evidence_symbol_mismatch":
            research_db.conn.execute(
                "UPDATE evidence_snapshots SET symbol = ? WHERE snapshot_id = ?",
                ("601999.SH", snap_id)
            )
            research_db.conn.commit()
        elif test_case == "card_decision_stop":
            cursor = research_db.conn.cursor()
            cursor.execute("SELECT card_data FROM agent_approval_cards WHERE approval_card_id = ?", (card_id,))
            card_json = cursor.fetchone()[0]
            card_dict = json.loads(card_json)
            card_dict["decision"] = "stop"
            research_db.conn.execute(
                "UPDATE agent_approval_cards SET card_data = ? WHERE approval_card_id = ?",
                (json.dumps(card_dict), card_id)
            )
            research_db.conn.commit()
    
    # Dual-DB snapshot before
    before_r, before_s = _dual_db_snapshot(research_db, strategy_db)
    
    # Call validator - ponytail: must throw for fail-loud, must return invalid for typed
    from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
    from pydantic import ValidationError
    
    if test_case in ("corrupt_json", "contract_invalid"):
        with pytest.raises(ValidationError):
            validate_strategy_revision_provenance(strategy_db, research_db, rev_id)
    else:
        result = validate_strategy_revision_provenance(strategy_db, research_db, rev_id)
        assert not result.is_valid
    
    # Dual-DB snapshot after
    after_r, after_s = _dual_db_snapshot(research_db, strategy_db)
    
    # Assert zero write
    assert before_r == after_r, f"{test_case}: ResearchDB modified"
    assert before_s == after_s, f"{test_case}: StrategyDB modified"
    