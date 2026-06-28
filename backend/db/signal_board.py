"""
Signal Board Database Layer

SQLite-based storage for PlannedSignal entities.
Provides ORM-style interface for CRUD operations.

Design Principles:
- Embedded SQLite (no external DB server)
- ACID guarantees (no data loss)
- Simple schema (no JOINs, denormalized for fast reads)
- Indexed for common queries (date, status, snapshot_hash)
"""

import sqlite3
import json
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Iterator, Union
from contextlib import contextmanager

from contracts.signal_board import PlannedSignal, SignalSummary


class SignalListResult:
    """Paginated signal list with backwards-compatible list behavior."""

    def __init__(self, items: List[PlannedSignal], total: int, limit: int, offset: int):
        self.items = items
        self.total = total
        self.limit = limit
        self.offset = offset
        self.has_more = offset + len(items) < total

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator[PlannedSignal]:
        return iter(self.items)

    def __getitem__(self, key: Union[int, slice, str]):
        if isinstance(key, str):
            return self.to_dict()[key]
        return self.items[key]

    def __eq__(self, other) -> bool:
        if isinstance(other, list):
            return self.items == other
        return super().__eq__(other)

    def to_dict(self) -> dict:
        return {
            "items": self.items,
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
            "has_more": self.has_more,
        }


class SignalBoardDB:
    """
    SQLite database for Signal Board.
    
    Schema:
        planned_signals table with all PlannedSignal fields.
        Indexes on: signal_date, review_status, snapshot_hash
    
    Thread Safety:
        Each operation opens a new connection (check_same_thread=False).
        Safe for concurrent reads, serialized writes.
    """
    
    def __init__(self, db_path: str | Path):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file.
                     Creates file and schema if doesn't exist.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
    
    @contextmanager
    def _get_conn(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        conn.row_factory = sqlite3.Row  # Access columns by name
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_schema(self):
        """Create tables and indexes if not exist."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS planned_signals (
                    signal_id TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    strategy_revision_id TEXT,
                    lifecycle_state_at_generation TEXT,
                    admission_source TEXT,
                    snapshot_hash TEXT NOT NULL,
                    signal_date TEXT NOT NULL,
                    intended_execution_date TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    planned_action TEXT NOT NULL,
                    quantity INTEGER,
                    trigger_reason TEXT NOT NULL,
                    review_status TEXT NOT NULL DEFAULT 'pending',
                    reviewed_at TEXT,
                    reviewed_by TEXT,
                    rejection_reason TEXT,
                    current_price REAL,
                    position_before INTEGER,
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    risk_flags TEXT NOT NULL DEFAULT '[]',
                    evidence_status TEXT NOT NULL DEFAULT 'clean',
                    evidence_checked_at TEXT
                )
            """)
            
            # Indexes for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signal_date 
                ON planned_signals(signal_date)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_review_status 
                ON planned_signals(review_status)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_snapshot_hash 
                ON planned_signals(snapshot_hash)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_intended_execution_date 
                ON planned_signals(intended_execution_date)
            """)
    
    def create_signal(self, signal: PlannedSignal) -> None:
        """
        Insert a new signal into database.
        
        Args:
            signal: PlannedSignal to insert
        
        Raises:
            sqlite3.IntegrityError: If signal_id already exists
        """
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO planned_signals (
                    signal_id, strategy_id, strategy_version, strategy_revision_id,
                    lifecycle_state_at_generation, admission_source,
                    snapshot_hash,
                    signal_date, intended_execution_date, symbol, direction,
                    planned_action, quantity, trigger_reason, review_status, reviewed_at,
                    reviewed_by, rejection_reason, current_price, position_before,
                    created_at, metadata, risk_flags, evidence_status, evidence_checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal.signal_id,
                signal.strategy_id,
                signal.strategy_version,
                signal.strategy_revision_id,
                signal.lifecycle_state_at_generation,
                signal.admission_source,
                signal.snapshot_hash,
                signal.signal_date.isoformat(),
                signal.intended_execution_date.isoformat(),
                signal.symbol,
                signal.direction,
                signal.planned_action,
                signal.quantity,
                signal.trigger_reason,
                signal.review_status,
                signal.reviewed_at.isoformat() if signal.reviewed_at else None,
                signal.reviewed_by,
                signal.rejection_reason,
                signal.current_price,
                signal.position_before,
                signal.created_at.isoformat(),
                json.dumps(signal.metadata),
                json.dumps(signal.risk_flags),
                signal.evidence_status,
                signal.evidence_checked_at.isoformat() if signal.evidence_checked_at else None
            ))
    
    def get_signal(self, signal_id: str) -> Optional[PlannedSignal]:
        """
        Retrieve a single signal by ID.

        Args:
            signal_id: Signal UUID

        Returns:
            PlannedSignal if found, None otherwise
        """
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM planned_signals WHERE signal_id = ?",
                (signal_id,)
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_signal(row)

    def get_admitted_signal(self, signal_id: str) -> Optional[PlannedSignal]:
        """
        Return signal only if it has valid C admission metadata.

        Args:
            signal_id: Signal UUID

        Returns:
            PlannedSignal if found and admitted (prototype_passed), None otherwise
        """
        signal = self.get_signal(signal_id)
        if signal is None:
            return None
        if signal.lifecycle_state_at_generation != "prototype_passed":
            return None
        return signal

    def list_signals(
        self,
        signal_date: Optional[date] = None,
        intended_execution_date: Optional[date] = None,
        review_status: Optional[str] = None,
        direction: Optional[str] = None,
        snapshot_hash: Optional[str] = None,
        strategy_id: Optional[str] = None,
        strategy_version: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        include_missing_admission: bool = False,
    ) -> SignalListResult:
        """
        Query signals with filters.
        
        Args:
            signal_date: Filter by signal generation date
            intended_execution_date: Filter by intended execution date
            review_status: Filter by review status (pending/reviewed/ignored/approved_for_watch)
            direction: Filter by direction (buy/sell)
            snapshot_hash: Filter by snapshot hash
            strategy_id: Filter by strategy ID (M4.1 Phase 3)
            strategy_version: Filter by strategy version (M4.1 Phase 3)
            limit: Max results to return
            offset: Pagination offset
            include_missing_admission: If False (default), only return signals with valid
                admission metadata (lifecycle_state_at_generation='prototype_passed').
                If True, include all signals (for audit/internal use).
        
        Returns:
            Paginated result. It can still be iterated/indexed like a list for
            older callers, while also exposing total/limit/offset/has_more.
        """
        if limit <= 0:
            raise ValueError("limit must be greater than 0")
        if limit > 500:
            raise ValueError("limit must be less than or equal to 500")
        if offset < 0:
            raise ValueError("offset must be greater than or equal to 0")

        where = " WHERE 1=1"
        params = []
        
        # C1 Task 3: Default filter - only return signals with valid admission
        if not include_missing_admission:
            where += " AND lifecycle_state_at_generation = ?"
            params.append("prototype_passed")
        
        if signal_date is not None:
            where += " AND signal_date = ?"
            params.append(signal_date.isoformat())
        
        if intended_execution_date is not None:
            where += " AND intended_execution_date = ?"
            params.append(intended_execution_date.isoformat())
        
        if review_status is not None:
            where += " AND review_status = ?"
            params.append(review_status)
        
        if direction is not None:
            where += " AND direction = ?"
            params.append(direction)
        
        if snapshot_hash is not None:
            where += " AND snapshot_hash = ?"
            params.append(snapshot_hash)
        
        if strategy_id is not None:
            where += " AND strategy_id = ?"
            params.append(strategy_id)
        
        if strategy_version is not None:
            where += " AND strategy_version = ?"
            params.append(strategy_version)
        
        order_by = """
            ORDER BY signal_date DESC,
                     intended_execution_date DESC,
                     strategy_id ASC,
                     strategy_version ASC,
                     symbol ASC,
                     signal_id ASC
        """
        count_query = "SELECT COUNT(*) FROM planned_signals" + where
        page_query = "SELECT * FROM planned_signals" + where + order_by + " LIMIT ? OFFSET ?"
        
        with self._get_conn() as conn:
            total = conn.execute(count_query, params).fetchone()[0]
            cursor = conn.execute(page_query, [*params, limit, offset])
            rows = cursor.fetchall()
            items = [self._row_to_signal(row) for row in rows]
            return SignalListResult(items=items, total=total, limit=limit, offset=offset)
    
    def update_review_status(
        self,
        signal_id: str,
        review_status: str,
        reviewed_by: str,
        rejection_reason: Optional[str] = None
    ) -> bool:
        """
        Update review status of a signal.
        
        Args:
            signal_id: Signal UUID
            review_status: New review status (reviewed/ignored/approved_for_watch)
            reviewed_by: Username who reviewed
            rejection_reason: Why signal was ignored (if status is 'ignored')
        
        Returns:
            True if signal was updated, False if signal not found
        """
        with self._get_conn() as conn:
            cursor = conn.execute("""
                UPDATE planned_signals
                SET review_status = ?,
                    reviewed_at = ?,
                    reviewed_by = ?,
                    rejection_reason = ?
                WHERE signal_id = ?
            """, (
                review_status,
                datetime.utcnow().isoformat(),
                reviewed_by,
                rejection_reason,
                signal_id
            ))
            return cursor.rowcount > 0
    
    def batch_update_review_status(
        self,
        signal_ids: List[str],
        review_status: str,
        reviewed_by: str,
        rejection_reason: Optional[str] = None
    ) -> int:
        """
        Batch update review status of multiple signals.
        
        Args:
            signal_ids: List of signal UUIDs
            review_status: New review status
            reviewed_by: Username who reviewed
            rejection_reason: Why signals were ignored
        
        Returns:
            Number of signals updated
        """
        if not signal_ids:
            return 0
        
        placeholders = ",".join("?" * len(signal_ids))
        query = f"""
            UPDATE planned_signals
            SET review_status = ?,
                reviewed_at = ?,
                reviewed_by = ?,
                rejection_reason = ?
            WHERE signal_id IN ({placeholders})
        """
        
        with self._get_conn() as conn:
            cursor = conn.execute(
                query,
                (review_status, datetime.utcnow().isoformat(), reviewed_by, rejection_reason, *signal_ids)
            )
            return cursor.rowcount
    
    def update_evidence(
        self,
        signal_id: str,
        risk_flags: list[str],
        evidence_status: str,
        evidence_checked_at: datetime
    ) -> bool:
        """
        Update evidence check results for a signal.
        
        Args:
            signal_id: Signal UUID
            risk_flags: List of detected risk flags
            evidence_status: Evidence status (clean/warning/blocked)
            evidence_checked_at: Timestamp of evidence check
        
        Returns:
            True if signal was updated, False if signal not found
        """
        with self._get_conn() as conn:
            cursor = conn.execute("""
                UPDATE planned_signals
                SET risk_flags = ?,
                    evidence_status = ?,
                    evidence_checked_at = ?
                WHERE signal_id = ?
            """, (
                json.dumps(risk_flags),
                evidence_status,
                evidence_checked_at.isoformat(),
                signal_id
            ))
            return cursor.rowcount > 0
    
    def expire_pending_signals(
        self,
        as_of_date: date,
        reviewed_by: str = "system_expiration"
    ) -> int:
        """
        Expire pending signals whose intended_execution_date has passed.
        
        Only updates signals with:
        - review_status = 'pending'
        - intended_execution_date < as_of_date
        
        Does NOT update:
        - watching / ignored / expired signals
        - signals with intended_execution_date >= as_of_date
        
        Args:
            as_of_date: Current date to compare against intended_execution_date
            reviewed_by: Username to record (default: "system_expiration")
        
        Returns:
            Number of signals expired
        """
        with self._get_conn() as conn:
            cursor = conn.execute("""
                UPDATE planned_signals
                SET review_status = 'expired',
                    reviewed_at = ?,
                    reviewed_by = ?
                WHERE review_status = 'pending'
                  AND intended_execution_date < ?
            """, (
                datetime.utcnow().isoformat(),
                reviewed_by,
                as_of_date.isoformat()
            ))
            return cursor.rowcount
    
    def get_summary(self, signal_date: date) -> SignalSummary:
        """
        Get summary statistics for signals on a given date.
        
        Args:
            signal_date: Date when signals were generated
        
        Returns:
            SignalSummary with counts by status and direction
        """
        with self._get_conn() as conn:
            # Total count
            cursor = conn.execute(
                "SELECT COUNT(*) FROM planned_signals WHERE signal_date = ?",
                (signal_date.isoformat(),)
            )
            total_count = cursor.fetchone()[0]
            
            # Count by status
            cursor = conn.execute("""
                SELECT review_status, COUNT(*) 
                FROM planned_signals 
                WHERE signal_date = ?
                GROUP BY review_status
            """, (signal_date.isoformat(),))
            by_status = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Count by direction
            cursor = conn.execute("""
                SELECT direction, COUNT(*) 
                FROM planned_signals 
                WHERE signal_date = ?
                GROUP BY direction
            """, (signal_date.isoformat(),))
            by_direction = {row[0]: row[1] for row in cursor.fetchall()}
            
            pending_count = by_status.get("pending", 0)
            
            return SignalSummary(
                signal_date=signal_date,
                total_count=total_count,
                by_status=by_status,
                by_direction=by_direction,
                pending_count=pending_count
            )
    
    def list_strategies(self, include_missing_admission: bool = False) -> List[dict]:
        """
        List all strategy_id + strategy_version combinations in the database.
        
        Args:
            include_missing_admission: If False (default), only count signals with valid
                admission metadata (lifecycle_state_at_generation='prototype_passed').
                If True, include all signals (for audit/internal use).
        
        Returns:
            List of dicts with:
            - strategy_id: str
            - strategy_version: str
            - signal_count: int
            - latest_signal_date: str (ISO format)
        
        Example:
            [
                {
                    "strategy_id": "momentum_v2",
                    "strategy_version": "v2.1.0",
                    "signal_count": 15,
                    "latest_signal_date": "2023-12-29"
                }
            ]
        """
        where_clause = ""
        if not include_missing_admission:
            where_clause = "WHERE lifecycle_state_at_generation = 'prototype_passed'"
        
        with self._get_conn() as conn:
            cursor = conn.execute(f"""
                SELECT 
                    strategy_id,
                    strategy_version,
                    COUNT(*) as signal_count,
                    MAX(signal_date) as latest_signal_date
                FROM planned_signals
                {where_clause}
                GROUP BY strategy_id, strategy_version
                ORDER BY strategy_id ASC, strategy_version ASC
            """)
            
            rows = cursor.fetchall()
            
            return [
                {
                    "strategy_id": row["strategy_id"],
                    "strategy_version": row["strategy_version"],
                    "signal_count": row["signal_count"],
                    "latest_signal_date": row["latest_signal_date"]
                }
                for row in rows
            ]
    
    def _row_to_signal(self, row: sqlite3.Row) -> PlannedSignal:
        """Convert SQLite row to PlannedSignal."""
        return PlannedSignal(
            signal_id=row["signal_id"],
            strategy_id=row["strategy_id"],
            strategy_version=row["strategy_version"],
            strategy_revision_id=row["strategy_revision_id"],
            lifecycle_state_at_generation=row["lifecycle_state_at_generation"],
            admission_source=row["admission_source"],
            snapshot_hash=row["snapshot_hash"],
            signal_date=date.fromisoformat(row["signal_date"]),
            intended_execution_date=date.fromisoformat(row["intended_execution_date"]),
            symbol=row["symbol"],
            direction=row["direction"],
            planned_action=row["planned_action"],
            quantity=row["quantity"],
            trigger_reason=row["trigger_reason"],
            review_status=row["review_status"],
            reviewed_at=datetime.fromisoformat(row["reviewed_at"]) if row["reviewed_at"] else None,
            reviewed_by=row["reviewed_by"],
            rejection_reason=row["rejection_reason"],
            current_price=row["current_price"],
            position_before=row["position_before"],
            created_at=datetime.fromisoformat(row["created_at"]),
            metadata=json.loads(row["metadata"]),
            risk_flags=json.loads(row["risk_flags"]) if row["risk_flags"] else [],
            evidence_status=row["evidence_status"],
            evidence_checked_at=datetime.fromisoformat(row["evidence_checked_at"]) if row["evidence_checked_at"] else None
        )
