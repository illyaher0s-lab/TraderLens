"""
Rejected Strategy Database

SQLite persistence for rejected strategies. Append-only.

No LLM, no external APIs, no trading logic.
"""

import json
import sqlite3
from datetime import datetime

from contracts.rejected_strategy import (
    RejectedStrategyRecord,
    RejectedStrategyStatus,
    DataQualityStatus,
)


def init_rejected_strategy_db(conn: sqlite3.Connection):
    """Initialize rejected strategy database schema."""
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rejected_strategies (
            registry_id TEXT PRIMARY KEY,
            strategy_revision_id TEXT NOT NULL,
            template_id TEXT NOT NULL,
            template_version TEXT NOT NULL,
            status TEXT NOT NULL,
            failed_gate TEXT NOT NULL,
            rejection_reason TEXT NOT NULL,
            data_quality_status TEXT NOT NULL,
            market_context_snapshot TEXT NOT NULL,
            cost_stress_result_id TEXT,
            future_retest_allowed INTEGER NOT NULL,
            retest_eligibility_reason TEXT NOT NULL,
            artifact_ids TEXT NOT NULL,
            created_at TEXT NOT NULL,
            actor TEXT NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_rejected_strategies_status 
        ON rejected_strategies(status)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_rejected_strategies_revision_id 
        ON rejected_strategies(strategy_revision_id)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_rejected_strategies_template 
        ON rejected_strategies(template_id, template_version)
    """)
    
    conn.commit()


def append_rejected_strategy(conn: sqlite3.Connection, record: RejectedStrategyRecord):
    """
    Append rejected strategy record.
    
    Fails if duplicate registry_id exists.
    """
    cursor = conn.cursor()
    
    # Check for duplicate
    cursor.execute(
        "SELECT registry_id FROM rejected_strategies WHERE registry_id = ?",
        (record.registry_id,)
    )
    if cursor.fetchone():
        raise ValueError(f"Duplicate registry_id: {record.registry_id}")
    
    cursor.execute(
        """
        INSERT INTO rejected_strategies (
            registry_id, strategy_revision_id, template_id, template_version,
            status, failed_gate, rejection_reason, data_quality_status,
            market_context_snapshot, cost_stress_result_id,
            future_retest_allowed, retest_eligibility_reason,
            artifact_ids, created_at, actor
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.registry_id,
            record.strategy_revision_id,
            record.template_id,
            record.template_version,
            record.status.value,
            record.failed_gate,
            record.rejection_reason,
            record.data_quality_status.value,
            json.dumps(record.market_context_snapshot),
            record.cost_stress_result_id,
            1 if record.future_retest_allowed else 0,
            record.retest_eligibility_reason,
            json.dumps(record.artifact_ids),
            record.created_at.isoformat(),
            record.actor,
        ),
    )
    
    conn.commit()


def get_rejected_strategy(conn: sqlite3.Connection, registry_id: str) -> RejectedStrategyRecord:
    """Get rejected strategy by registry_id."""
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT registry_id, strategy_revision_id, template_id, template_version,
               status, failed_gate, rejection_reason, data_quality_status,
               market_context_snapshot, cost_stress_result_id,
               future_retest_allowed, retest_eligibility_reason,
               artifact_ids, created_at, actor
        FROM rejected_strategies
        WHERE registry_id = ?
        """,
        (registry_id,)
    )
    
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Rejected strategy not found: {registry_id}")
    
    return RejectedStrategyRecord(
        registry_id=row[0],
        strategy_revision_id=row[1],
        template_id=row[2],
        template_version=row[3],
        status=RejectedStrategyStatus(row[4]),
        failed_gate=row[5],
        rejection_reason=row[6],
        data_quality_status=DataQualityStatus(row[7]),
        market_context_snapshot=json.loads(row[8]),
        cost_stress_result_id=row[9],
        future_retest_allowed=bool(row[10]),
        retest_eligibility_reason=row[11],
        artifact_ids=json.loads(row[12]),
        created_at=datetime.fromisoformat(row[13]),
        actor=row[14],
    )


def list_rejected_strategies(conn: sqlite3.Connection) -> list[RejectedStrategyRecord]:
    """List all rejected strategies."""
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT registry_id, strategy_revision_id, template_id, template_version,
               status, failed_gate, rejection_reason, data_quality_status,
               market_context_snapshot, cost_stress_result_id,
               future_retest_allowed, retest_eligibility_reason,
               artifact_ids, created_at, actor
        FROM rejected_strategies
        ORDER BY created_at DESC
        """
    )
    
    rows = cursor.fetchall()
    
    return [
        RejectedStrategyRecord(
            registry_id=row[0],
            strategy_revision_id=row[1],
            template_id=row[2],
            template_version=row[3],
            status=RejectedStrategyStatus(row[4]),
            failed_gate=row[5],
            rejection_reason=row[6],
            data_quality_status=DataQualityStatus(row[7]),
            market_context_snapshot=json.loads(row[8]),
            cost_stress_result_id=row[9],
            future_retest_allowed=bool(row[10]),
            retest_eligibility_reason=row[11],
            artifact_ids=json.loads(row[12]),
            created_at=datetime.fromisoformat(row[13]),
            actor=row[14],
        )
        for row in rows
    ]


def list_rejected_strategies_by_status(
    conn: sqlite3.Connection, status: RejectedStrategyStatus
) -> list[RejectedStrategyRecord]:
    """List rejected strategies by status."""
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT registry_id, strategy_revision_id, template_id, template_version,
               status, failed_gate, rejection_reason, data_quality_status,
               market_context_snapshot, cost_stress_result_id,
               future_retest_allowed, retest_eligibility_reason,
               artifact_ids, created_at, actor
        FROM rejected_strategies
        WHERE status = ?
        ORDER BY created_at DESC
        """,
        (status.value,)
    )
    
    rows = cursor.fetchall()
    
    return [
        RejectedStrategyRecord(
            registry_id=row[0],
            strategy_revision_id=row[1],
            template_id=row[2],
            template_version=row[3],
            status=RejectedStrategyStatus(row[4]),
            failed_gate=row[5],
            rejection_reason=row[6],
            data_quality_status=DataQualityStatus(row[7]),
            market_context_snapshot=json.loads(row[8]),
            cost_stress_result_id=row[9],
            future_retest_allowed=bool(row[10]),
            retest_eligibility_reason=row[11],
            artifact_ids=json.loads(row[12]),
            created_at=datetime.fromisoformat(row[13]),
            actor=row[14],
        )
        for row in rows
    ]


def count_by_status(conn: sqlite3.Connection) -> dict[str, int]:
    """Count rejected strategies by status."""
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT status, COUNT(*)
        FROM rejected_strategies
        GROUP BY status
        """
    )
    
    return {row[0]: row[1] for row in cursor.fetchall()}


def count_by_failed_gate(conn: sqlite3.Connection) -> dict[str, int]:
    """Count rejected strategies by failed gate."""
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT failed_gate, COUNT(*)
        FROM rejected_strategies
        GROUP BY failed_gate
        """
    )
    
    return {row[0]: row[1] for row in cursor.fetchall()}


def find_by_strategy_revision_id(
    conn: sqlite3.Connection, strategy_revision_id: str
) -> list[RejectedStrategyRecord]:
    """Find rejected strategies by strategy_revision_id."""
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT registry_id, strategy_revision_id, template_id, template_version,
               status, failed_gate, rejection_reason, data_quality_status,
               market_context_snapshot, cost_stress_result_id,
               future_retest_allowed, retest_eligibility_reason,
               artifact_ids, created_at, actor
        FROM rejected_strategies
        WHERE strategy_revision_id = ?
        ORDER BY created_at DESC
        """,
        (strategy_revision_id,)
    )
    
    rows = cursor.fetchall()
    
    return [
        RejectedStrategyRecord(
            registry_id=row[0],
            strategy_revision_id=row[1],
            template_id=row[2],
            template_version=row[3],
            status=RejectedStrategyStatus(row[4]),
            failed_gate=row[5],
            rejection_reason=row[6],
            data_quality_status=DataQualityStatus(row[7]),
            market_context_snapshot=json.loads(row[8]),
            cost_stress_result_id=row[9],
            future_retest_allowed=bool(row[10]),
            retest_eligibility_reason=row[11],
            artifact_ids=json.loads(row[12]),
            created_at=datetime.fromisoformat(row[13]),
            actor=row[14],
        )
        for row in rows
    ]


def find_by_template(
    conn: sqlite3.Connection,
    template_id: str,
    template_version: str | None = None,
) -> list[RejectedStrategyRecord]:
    """Find rejected strategies by template."""
    cursor = conn.cursor()
    
    if template_version:
        cursor.execute(
            """
            SELECT registry_id, strategy_revision_id, template_id, template_version,
                   status, failed_gate, rejection_reason, data_quality_status,
                   market_context_snapshot, cost_stress_result_id,
                   future_retest_allowed, retest_eligibility_reason,
                   artifact_ids, created_at, actor
            FROM rejected_strategies
            WHERE template_id = ? AND template_version = ?
            ORDER BY created_at DESC
            """,
            (template_id, template_version)
        )
    else:
        cursor.execute(
            """
            SELECT registry_id, strategy_revision_id, template_id, template_version,
                   status, failed_gate, rejection_reason, data_quality_status,
                   market_context_snapshot, cost_stress_result_id,
                   future_retest_allowed, retest_eligibility_reason,
                   artifact_ids, created_at, actor
            FROM rejected_strategies
            WHERE template_id = ?
            ORDER BY created_at DESC
            """,
            (template_id,)
        )
    
    rows = cursor.fetchall()
    
    return [
        RejectedStrategyRecord(
            registry_id=row[0],
            strategy_revision_id=row[1],
            template_id=row[2],
            template_version=row[3],
            status=RejectedStrategyStatus(row[4]),
            failed_gate=row[5],
            rejection_reason=row[6],
            data_quality_status=DataQualityStatus(row[7]),
            market_context_snapshot=json.loads(row[8]),
            cost_stress_result_id=row[9],
            future_retest_allowed=bool(row[10]),
            retest_eligibility_reason=row[11],
            artifact_ids=json.loads(row[12]),
            created_at=datetime.fromisoformat(row[13]),
            actor=row[14],
        )
        for row in rows
    ]
