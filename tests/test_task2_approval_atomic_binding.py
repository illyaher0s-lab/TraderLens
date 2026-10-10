from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api.research import create_research_app
from backend.db.agent_workbench import attach_artifact_ref, init_agent_workbench_db
from backend.db.research import ResearchDB
from contracts.agent_workbench import ArtifactRef
from contracts.research import CandidateStock, ThemeInput
from tests.approval_context_fixtures import attach_continued_approval


def _open_db(tmp_path) -> ResearchDB:
    db = ResearchDB(str(tmp_path / "research.db"))
    init_agent_workbench_db(db.conn)
    return db


def _add_theme_candidate(
    db: ResearchDB,
    *,
    theme_id: str = "theme_1",
    candidate_id: str = "cand_1",
) -> None:
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


def _confirm(db: ResearchDB, *, card_id: str | None, candidate_id: str = "cand_1"):
    return db.confirm_candidate(
        candidate_id=candidate_id,
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="user",
        pool_snapshot_date=date.today(),
        thesis_snapshot="Test",
        invalidation_rules=[],
        price_snapshot={},
        benchmark_snapshot={},
        approval_card_id=card_id,
    )


def _assert_no_confirmation_writes(db: ResearchDB, theme_id: str, candidate_id: str) -> None:
    assert db.conn.execute("SELECT COUNT(*) FROM confirmed_candidates").fetchone()[0] == 0
    assert db.get_candidate(candidate_id).status == "raw"
    assert db.get_theme(theme_id).board_version == 0


def test_production_db_accepts_only_the_exact_card_and_session_theme_chain(tmp_path):
    db = _open_db(tmp_path)
    try:
        _add_theme_candidate(db)
        card_id = attach_continued_approval(db, "theme_1")

        confirmed = _confirm(db, card_id=card_id)

        assert confirmed.approval_card_id == card_id
        assert db.get_candidate("cand_1").status == "confirmed"
        assert db.get_theme("theme_1").board_version == 1
    finally:
        db.close()


def test_workflow_id_equal_to_theme_id_is_rejected(tmp_path):
    db = _open_db(tmp_path)
    try:
        _add_theme_candidate(db)
        now = datetime.now().isoformat()
        db.conn.execute(
            "INSERT INTO agent_sessions VALUES (?, ?, ?, ?, ?, ?)",
            ("session_1", "friend_stock", "waiting_for_approval", "Test", now, now),
        )
        db.conn.execute(
            "INSERT INTO agent_artifact_refs VALUES (?, ?, ?, ?, ?, ?)",
            ("ref_1", "session_1", "theme_1", "research_case", None, now),
        )
        db.conn.execute(
            "INSERT INTO agent_approval_cards VALUES (?, ?, ?, ?)",
            (
                "card_wrong",
                "session_1",
                json.dumps(
                    {
                        "approval_card_id": "card_wrong",
                        "workflow_id": "theme_1",
                        "stage": "research_confirmation",
                        "title": "Wrong",
                        "plain_language_summary": "Wrong",
                        "allowed_decisions": ["continue"],
                        "artifact_ids": ["theme_1"],
                        "created_at": now,
                        "decision": "continue",
                        "decided_at": now,
                        "decided_by": "user",
                    }
                ),
                now,
            ),
        )
        db.conn.commit()

        with pytest.raises(ValueError, match="approval_card_session_mismatch"):
            _confirm(db, card_id="card_wrong")
        _assert_no_confirmation_writes(db, "theme_1", "cand_1")
    finally:
        db.close()


def test_same_session_other_research_case_cannot_borrow_card(tmp_path):
    db = _open_db(tmp_path)
    try:
        _add_theme_candidate(db, theme_id="theme_1", candidate_id="cand_1")
        _add_theme_candidate(db, theme_id="theme_2", candidate_id="cand_2")
        card_id = attach_continued_approval(
            db,
            "theme_1",
            session_id="session_shared",
            artifact_theme_ids=["theme_1", "theme_2"],
            card_artifact_ids=["theme_1"],
        )

        with pytest.raises(ValueError, match="approval_card_research_case_binding_mismatch"):
            _confirm(db, card_id=card_id, candidate_id="cand_2")
        _assert_no_confirmation_writes(db, "theme_2", "cand_2")
    finally:
        db.close()


@pytest.mark.parametrize("card_id", [None, "", "   "])
def test_new_confirmation_requires_real_card(card_id, tmp_path):
    db = _open_db(tmp_path)
    try:
        _add_theme_candidate(db)
        with pytest.raises(ValueError, match="approval_provenance_required"):
            _confirm(db, card_id=card_id)
        _assert_no_confirmation_writes(db, "theme_1", "cand_1")
    finally:
        db.close()


@pytest.mark.parametrize(
    ("trigger_name", "trigger_sql"),
    [
        (
            "fail_confirmed_insert",
            """CREATE TRIGGER fail_confirmed_insert BEFORE INSERT ON confirmed_candidates
            BEGIN SELECT RAISE(ABORT, 'forced confirmed insert failure'); END""",
        ),
        (
            "fail_candidate_status",
            """CREATE TRIGGER fail_candidate_status BEFORE UPDATE OF status ON research_candidates
            WHEN NEW.status = 'confirmed'
            BEGIN SELECT RAISE(ABORT, 'forced candidate status failure'); END""",
        ),
        (
            "fail_board_version",
            """CREATE TRIGGER fail_board_version BEFORE UPDATE OF board_version ON research_themes
            WHEN NEW.board_version <> OLD.board_version
            BEGIN SELECT RAISE(ABORT, 'forced board version failure'); END""",
        ),
    ],
)
def test_confirmation_state_transition_rolls_back_as_one_transaction(
    trigger_name, trigger_sql, tmp_path
):
    db = _open_db(tmp_path)
    try:
        _add_theme_candidate(db)
        card_id = attach_continued_approval(db, "theme_1")
        db.conn.execute(trigger_sql)
        db.conn.commit()

        with pytest.raises(sqlite3.IntegrityError, match="forced"):
            _confirm(db, card_id=card_id)
        _assert_no_confirmation_writes(db, "theme_1", "cand_1")
    finally:
        db.close()


def test_corrupt_card_json_fails_loud_without_business_writes(tmp_path):
    db = _open_db(tmp_path)
    try:
        _add_theme_candidate(db)
        now = datetime.now().isoformat()
        db.conn.execute(
            "INSERT INTO agent_sessions VALUES (?, ?, ?, ?, ?, ?)",
            ("session_1", "friend_stock", "waiting_for_approval", "Test", now, now),
        )
        attach_artifact_ref(
            db.conn,
            ArtifactRef(
                artifact_ref_id="ref_1",
                session_id="session_1",
                artifact_id="theme_1",
                artifact_type="research_case",
                created_at=datetime.now(),
            ),
        )
        db.conn.execute(
            "INSERT INTO agent_approval_cards VALUES (?, ?, ?, ?)",
            ("card_corrupt", "session_1", "{", now),
        )
        db.conn.commit()

        with pytest.raises(ValidationError):
            _confirm(db, card_id="card_corrupt")
        _assert_no_confirmation_writes(db, "theme_1", "cand_1")
    finally:
        db.close()


def test_production_api_passes_card_through_reducer_to_atomic_db_boundary(tmp_path):
    db = _open_db(tmp_path)
    try:
        _add_theme_candidate(db)
        card_id = attach_continued_approval(db, "theme_1")
        db.store_evidence_snapshot(
            snapshot_id="snap_1",
            candidate_id="cand_1",
            verification_id=None,
            snapshot_date=date.today().isoformat(),
            symbol="600000.SH",
            evidence_output={"evidence_level": "medium", "blocking_issues": []},
        )
        client = TestClient(create_research_app(db))

        response = client.post(
            "/api/research/candidates/cand_1/confirm",
            json={
                "approval_card_id": card_id,
                "confirmation_reason": "Test",
                "evidence_level": "medium",
                "confirmed_by": "user",
                "pool_snapshot_date": date.today().isoformat(),
                "thesis_snapshot": "Test",
                "invalidation_rules": [],
                "price_snapshot": {},
                "benchmark_snapshot": {},
                "evidence_snapshot_ids": ["snap_1"],
                "primary_evidence_snapshot_id": "snap_1",
            },
        )

        assert response.status_code == 200, response.text
        stored = db.list_confirmed_candidates("theme_1")
        assert [item.approval_card_id for item in stored] == [card_id]
        assert db.get_theme("theme_1").board_version == 1
    finally:
        db.close()


def test_production_api_rejects_missing_card_without_fallback(tmp_path):
    db = _open_db(tmp_path)
    try:
        _add_theme_candidate(db)
        db.store_evidence_snapshot(
            snapshot_id="snap_1",
            candidate_id="cand_1",
            verification_id=None,
            snapshot_date=date.today().isoformat(),
            symbol="600000.SH",
            evidence_output={"evidence_level": "medium", "blocking_issues": []},
        )
        client = TestClient(create_research_app(db))
        response = client.post(
            "/api/research/candidates/cand_1/confirm",
            json={
                "confirmation_reason": "Test",
                "evidence_level": "medium",
                "confirmed_by": "user",
                "pool_snapshot_date": date.today().isoformat(),
                "thesis_snapshot": "Test",
                "invalidation_rules": [],
                "price_snapshot": {},
                "benchmark_snapshot": {},
                "evidence_snapshot_ids": ["snap_1"],
            },
        )

        assert response.status_code == 400
        assert "approval_provenance_required" in response.json()["detail"]
        _assert_no_confirmation_writes(db, "theme_1", "cand_1")
    finally:
        db.close()


def test_legacy_null_provenance_remains_readable(tmp_path):
    db = _open_db(tmp_path)
    try:
        db.conn.execute(
            """INSERT INTO confirmed_candidates (
                confirmed_id, theme_id, candidate_id, symbol, company_name,
                thesis_snapshot, invalidation_rules, price_snapshot, benchmark_snapshot,
                confirmation_reason, evidence_level, evidence_snapshot_ids,
                confirmed_by, confirmed_at, pool_snapshot_date, forward_only,
                approval_card_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL)""",
            (
                "legacy_1",
                "theme_1",
                "cand_1",
                "600000.SH",
                "Legacy",
                "Test",
                "[]",
                "{}",
                "{}",
                "Test",
                "medium",
                "[]",
                "user",
                datetime.now().isoformat(),
                date.today().isoformat(),
            ),
        )
        db.conn.commit()

        stored = db.get_confirmed_candidate("legacy_1")
        assert stored is not None
        assert stored.approval_card_id is None
    finally:
        db.close()
