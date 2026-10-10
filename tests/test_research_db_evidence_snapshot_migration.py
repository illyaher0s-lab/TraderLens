import json
import sqlite3
from datetime import datetime

from backend.db.research import ResearchDB


def test_legacy_evidence_snapshots_are_migrated_without_losing_rows(tmp_path):
    """A persisted V1 snapshot must survive when V2 adds packet audit fields."""
    db_path = tmp_path / "legacy_research.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE evidence_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            evidence_output TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO evidence_snapshots VALUES (?, ?, ?, ?, ?)",
        (
            "legacy_snapshot",
            "legacy_candidate",
            "600519.SH",
            json.dumps({"legacy": True}),
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    db = ResearchDB(str(db_path))

    columns = {
        row["name"]
        for row in db.conn.execute("PRAGMA table_info(evidence_snapshots)").fetchall()
    }
    assert {"verification_id", "snapshot_date", "packet_input_hash", "tool_result_hash", "packet_data", "audit_id"} <= columns
    assert db.get_evidence_snapshot("legacy_snapshot")["evidence_output"] == {"legacy": True}

    db.store_evidence_snapshot(
        snapshot_id="v2_snapshot",
        candidate_id="candidate_v2",
        verification_id=None,
        snapshot_date="2026-07-10",
        symbol="600519.SH",
        evidence_output={"v2": True},
        packet_data="{}",
    )
    assert db.get_evidence_snapshot("v2_snapshot")["packet_data"] == "{}"
