import json
import sqlite3

import pytest

from scripts.verify_p3_2_strategy_result_visibility import read_route_decision_workflow_kind


def _create_artifact_table(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE agent_artifact_refs (
            artifact_ref_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            artifact_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            content TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def test_p3_2_verification_reads_real_workflow_route_decision(tmp_path):
    """
    P3-2 acceptance must verify the router's persisted route decision, not infer
    workflow_kind from response.workflow_type or any later summary artifact.
    """
    db_path = tmp_path / "research.db"
    conn = _create_artifact_table(db_path)
    conn.execute(
        """
        INSERT INTO agent_artifact_refs (
            artifact_ref_id, session_id, artifact_id, artifact_type, content, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "artref_route",
            "sess_test",
            "route_sess_test",
            "workflow_route_decision",
            json.dumps({"workflow_kind": "strategy_idea", "workflow_state": "created"}),
            "2026-07-07T12:00:00",
        ),
    )
    conn.commit()
    conn.close()

    assert read_route_decision_workflow_kind(db_path, "sess_test") == "strategy_idea"


def test_p3_2_verification_fails_without_real_route_decision(tmp_path):
    """
    An empty workflow_intent artifact is not proof of route_decision.workflow_kind.
    The verification script must fail loud instead of falling back to workflow_type.
    """
    db_path = tmp_path / "research.db"
    conn = _create_artifact_table(db_path)
    conn.execute(
        """
        INSERT INTO agent_artifact_refs (
            artifact_ref_id, session_id, artifact_id, artifact_type, content, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "artref_intent",
            "sess_test",
            "intent_sess_test",
            "workflow_intent",
            "{}",
            "2026-07-07T12:00:00",
        ),
    )
    conn.commit()
    conn.close()

    with pytest.raises(AssertionError, match="workflow_route_decision"):
        read_route_decision_workflow_kind(db_path, "sess_test")
