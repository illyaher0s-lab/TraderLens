"""
Rejected Strategy Registry Service

Deterministic wrapper around rejected strategy DB.

No LLM, no external APIs, no random, no trading logic.
"""

import sqlite3

from contracts.rejected_strategy import RejectedStrategyRecord, RejectedStrategyStatus
from backend.db.rejected_strategy import (
    init_rejected_strategy_db,
    append_rejected_strategy,
    get_rejected_strategy,
    list_rejected_strategies,
    list_rejected_strategies_by_status,
    count_by_status,
    count_by_failed_gate,
    find_by_strategy_revision_id,
    find_by_template,
)


class RejectedStrategyRegistry:
    """
    Rejected strategy registry service.
    
    Deterministic wrapper. No LLM, no external APIs.
    """
    
    def __init__(self, conn: sqlite3.Connection):
        """Initialize registry with database connection."""
        self.conn = conn
        init_rejected_strategy_db(conn)
    
    def append(self, record: RejectedStrategyRecord):
        """Append rejected strategy record."""
        append_rejected_strategy(self.conn, record)
    
    def get(self, registry_id: str) -> RejectedStrategyRecord:
        """Get rejected strategy by ID."""
        return get_rejected_strategy(self.conn, registry_id)
    
    def list_all(self) -> list[RejectedStrategyRecord]:
        """List all rejected strategies."""
        return list_rejected_strategies(self.conn)
    
    def list_by_status(self, status: RejectedStrategyStatus) -> list[RejectedStrategyRecord]:
        """List rejected strategies by status."""
        return list_rejected_strategies_by_status(self.conn, status)
    
    def count_by_status(self) -> dict[str, int]:
        """Count rejected strategies by status."""
        return count_by_status(self.conn)
    
    def count_by_failed_gate(self) -> dict[str, int]:
        """Count rejected strategies by failed gate."""
        return count_by_failed_gate(self.conn)
    
    def find_by_revision(self, strategy_revision_id: str) -> list[RejectedStrategyRecord]:
        """Find rejected strategies by revision ID."""
        return find_by_strategy_revision_id(self.conn, strategy_revision_id)
    
    def find_by_template(
        self, template_id: str, template_version: str | None = None
    ) -> list[RejectedStrategyRecord]:
        """Find rejected strategies by template."""
        return find_by_template(self.conn, template_id, template_version)
