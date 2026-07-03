"""
Live Trade Database Layer

Manages execution observation drafts and logs.

Red lines enforced at DB layer:
1. Logs table is append-only from confirm/correct actions — no auto-promotion.
2. broker_verified is always False in both tables.
3. Evidence chain (5 IDs) must be non-empty for both draft and log.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from contracts.live_trade import (
    DailyObservationSignal,
    DisciplineReview,
    ExecutionInterpretationStatus,
    ExecutionObservationDraft,
    ExecutionObservationLog,
    ExplanationSource,
    InvalidationTrigger,
    ObservationPosition,
    PositionLifecycleState,
    DailySignalType,
)
from contracts.market_data_fault import MarketDataFaultState


class LiveTradeDB:
    """SQLite database for live trade execution observations."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _get_conn(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self):
        """Initialize database schema."""
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_observation_drafts (
                    draft_id TEXT PRIMARY KEY,
                    execution_card_id TEXT NOT NULL,
                    signal_id TEXT NOT NULL,
                    action_plan_id TEXT NOT NULL,
                    capital_context_id TEXT NOT NULL,
                    market_snapshot_id TEXT NOT NULL,
                    raw_user_text TEXT NOT NULL,
                    parsed_action TEXT NOT NULL,
                    parsed_execution_status TEXT NOT NULL,
                    parsed_price REAL,
                    parsed_quantity INTEGER,
                    parsed_reason TEXT,
                    missing_fields TEXT NOT NULL,
                    follow_up_question TEXT,
                    interpretation_source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    broker_verified INTEGER NOT NULL CHECK(broker_verified = 0),
                    created_at TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_observation_logs (
                    log_id TEXT PRIMARY KEY,
                    draft_id TEXT NOT NULL,
                    execution_card_id TEXT NOT NULL,
                    signal_id TEXT NOT NULL,
                    action_plan_id TEXT NOT NULL,
                    capital_context_id TEXT NOT NULL,
                    market_snapshot_id TEXT NOT NULL,
                    confirmed_action TEXT NOT NULL,
                    confirmed_execution_status TEXT NOT NULL,
                    confirmed_price REAL,
                    confirmed_quantity INTEGER,
                    reason TEXT,
                    confirmed_by_user INTEGER NOT NULL CHECK(confirmed_by_user = 1),
                    broker_verified INTEGER NOT NULL CHECK(broker_verified = 0),
                    confirmed_at TEXT NOT NULL,
                    FOREIGN KEY (draft_id) REFERENCES execution_observation_drafts(draft_id)
                )
                """
            )

            # Task 9: Observation positions and daily signals
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS observation_positions (
                    position_id TEXT PRIMARY KEY,
                    source_log_id TEXT NOT NULL,
                    execution_card_id TEXT NOT NULL,
                    signal_id TEXT NOT NULL,
                    action_plan_id TEXT NOT NULL,
                    capital_context_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    name TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    quantity INTEGER NOT NULL,
                    template_id TEXT NOT NULL,
                    template_version TEXT NOT NULL,
                    entry_thesis TEXT NOT NULL,
                    lifecycle_state TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    FOREIGN KEY (source_log_id) REFERENCES execution_observation_logs(log_id)
                )
                """
            )
            
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_observation_signals (
                    signal_record_id TEXT PRIMARY KEY,
                    position_id TEXT NOT NULL,
                    signal_type TEXT,
                    triggered_invalidations TEXT NOT NULL,
                    as_of_date TEXT NOT NULL,
                    market_data_state TEXT NOT NULL,
                    rule_trace TEXT NOT NULL,
                    plain_explanation TEXT,
                    explanation_source TEXT NOT NULL,
                    FOREIGN KEY (position_id) REFERENCES observation_positions(position_id)
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS discipline_reviews (
                    review_id TEXT PRIMARY KEY,
                    position_id TEXT NOT NULL,
                    execution_card_id TEXT NOT NULL,
                    signal_id TEXT NOT NULL,
                    review_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

            # Indexes for common queries
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_drafts_execution_card ON execution_observation_drafts(execution_card_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_logs_execution_card ON execution_observation_logs(execution_card_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_logs_draft ON execution_observation_logs(draft_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_positions_lifecycle ON observation_positions(lifecycle_state)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_signals_position_date ON daily_observation_signals(position_id, as_of_date)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reviews_position ON discipline_reviews(position_id)"
            )

    def save_draft(self, draft: ExecutionObservationDraft) -> None:
        """
        Save execution observation draft.
        
        Red line enforcement:
        - broker_verified must be False (DB CHECK constraint)
        - Evidence chain IDs must be non-empty (contract validator already checked)
        """
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO execution_observation_drafts (
                    draft_id, execution_card_id, signal_id, action_plan_id,
                    capital_context_id, market_snapshot_id, raw_user_text,
                    parsed_action, parsed_execution_status, parsed_price,
                    parsed_quantity, parsed_reason, missing_fields,
                    follow_up_question, interpretation_source, status,
                    broker_verified, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft.draft_id,
                    draft.execution_card_id,
                    draft.signal_id,
                    draft.action_plan_id,
                    draft.capital_context_id,
                    draft.market_snapshot_id,
                    draft.raw_user_text,
                    draft.parsed_action,
                    draft.parsed_execution_status,
                    draft.parsed_price,
                    draft.parsed_quantity,
                    draft.parsed_reason,
                    ",".join(draft.missing_fields),
                    draft.follow_up_question,
                    draft.interpretation_source,
                    draft.status.value,
                    0,  # broker_verified must be 0 (False)
                    draft.created_at.isoformat(),
                ),
            )

    def save_log(self, log: ExecutionObservationLog) -> None:
        """
        Save confirmed execution observation log.
        
        Red line enforcement:
        - Only callable after user confirm/correct (contract validates confirmed_by_user=True)
        - broker_verified must be False (DB CHECK constraint)
        """
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO execution_observation_logs (
                    log_id, draft_id, execution_card_id, signal_id,
                    action_plan_id, capital_context_id, market_snapshot_id,
                    confirmed_action, confirmed_execution_status,
                    confirmed_price, confirmed_quantity, reason,
                    confirmed_by_user, broker_verified, confirmed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log.log_id,
                    log.draft_id,
                    log.execution_card_id,
                    log.signal_id,
                    log.action_plan_id,
                    log.capital_context_id,
                    log.market_snapshot_id,
                    log.confirmed_action,
                    log.confirmed_execution_status,
                    log.confirmed_price,
                    log.confirmed_quantity,
                    log.reason,
                    1,  # confirmed_by_user must be 1 (True)
                    0,  # broker_verified must be 0 (False)
                    log.confirmed_at.isoformat(),
                ),
            )

    def get_draft(self, draft_id: str) -> Optional[ExecutionObservationDraft]:
        """Retrieve draft by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM execution_observation_drafts WHERE draft_id = ?",
                (draft_id,),
            ).fetchone()

            if not row:
                return None

            return ExecutionObservationDraft(
                draft_id=row["draft_id"],
                execution_card_id=row["execution_card_id"],
                signal_id=row["signal_id"],
                action_plan_id=row["action_plan_id"],
                capital_context_id=row["capital_context_id"],
                market_snapshot_id=row["market_snapshot_id"],
                raw_user_text=row["raw_user_text"],
                parsed_action=row["parsed_action"],
                parsed_execution_status=row["parsed_execution_status"],
                parsed_price=row["parsed_price"],
                parsed_quantity=row["parsed_quantity"],
                parsed_reason=row["parsed_reason"],
                missing_fields=row["missing_fields"].split(",") if row["missing_fields"] else [],
                follow_up_question=row["follow_up_question"],
                interpretation_source=row["interpretation_source"],
                status=ExecutionInterpretationStatus(row["status"]),
                broker_verified=False,  # Always False from DB
                created_at=datetime.fromisoformat(row["created_at"]),
            )

    def get_log(self, log_id: str) -> Optional[ExecutionObservationLog]:
        """Retrieve log by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM execution_observation_logs WHERE log_id = ?",
                (log_id,),
            ).fetchone()

            if not row:
                return None

            return ExecutionObservationLog(
                log_id=row["log_id"],
                draft_id=row["draft_id"],
                execution_card_id=row["execution_card_id"],
                signal_id=row["signal_id"],
                action_plan_id=row["action_plan_id"],
                capital_context_id=row["capital_context_id"],
                market_snapshot_id=row["market_snapshot_id"],
                confirmed_action=row["confirmed_action"],
                confirmed_execution_status=row["confirmed_execution_status"],
                confirmed_price=row["confirmed_price"],
                confirmed_quantity=row["confirmed_quantity"],
                reason=row["reason"],
                confirmed_by_user=True,  # Always True from DB
                broker_verified=False,  # Always False from DB
                confirmed_at=datetime.fromisoformat(row["confirmed_at"]),
            )

    def list_drafts_by_execution_card(self, execution_card_id: str) -> list[ExecutionObservationDraft]:
        """List all drafts for a given execution card."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM execution_observation_drafts WHERE execution_card_id = ? ORDER BY created_at DESC",
                (execution_card_id,),
            ).fetchall()

            return [
                ExecutionObservationDraft(
                    draft_id=row["draft_id"],
                    execution_card_id=row["execution_card_id"],
                    signal_id=row["signal_id"],
                    action_plan_id=row["action_plan_id"],
                    capital_context_id=row["capital_context_id"],
                    market_snapshot_id=row["market_snapshot_id"],
                    raw_user_text=row["raw_user_text"],
                    parsed_action=row["parsed_action"],
                    parsed_execution_status=row["parsed_execution_status"],
                    parsed_price=row["parsed_price"],
                    parsed_quantity=row["parsed_quantity"],
                    parsed_reason=row["parsed_reason"],
                    missing_fields=row["missing_fields"].split(",") if row["missing_fields"] else [],
                    follow_up_question=row["follow_up_question"],
                    interpretation_source=row["interpretation_source"],
                    status=ExecutionInterpretationStatus(row["status"]),
                    broker_verified=False,
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]

    def list_logs_by_execution_card(self, execution_card_id: str) -> list[ExecutionObservationLog]:
        """List all confirmed logs for a given execution card."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM execution_observation_logs WHERE execution_card_id = ? ORDER BY confirmed_at DESC",
                (execution_card_id,),
            ).fetchall()

            return [
                ExecutionObservationLog(
                    log_id=row["log_id"],
                    draft_id=row["draft_id"],
                    execution_card_id=row["execution_card_id"],
                    signal_id=row["signal_id"],
                    action_plan_id=row["action_plan_id"],
                    capital_context_id=row["capital_context_id"],
                    market_snapshot_id=row["market_snapshot_id"],
                    confirmed_action=row["confirmed_action"],
                    confirmed_execution_status=row["confirmed_execution_status"],
                    confirmed_price=row["confirmed_price"],
                    confirmed_quantity=row["confirmed_quantity"],
                    reason=row["reason"],
                    confirmed_by_user=True,
                    broker_verified=False,
                    confirmed_at=datetime.fromisoformat(row["confirmed_at"]),
                )
                for row in rows
            ]

    def save_position(self, position: ObservationPosition) -> None:
        """Insert or replace an observation position snapshot."""
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO observation_positions (
                    position_id, source_log_id, execution_card_id, signal_id,
                    action_plan_id, capital_context_id, symbol, name,
                    entry_price, quantity, template_id, template_version,
                    entry_thesis, lifecycle_state, opened_at, closed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position.position_id,
                    position.source_log_id,
                    position.execution_card_id,
                    position.signal_id,
                    position.action_plan_id,
                    position.capital_context_id,
                    position.symbol,
                    position.name,
                    position.entry_price,
                    position.quantity,
                    position.template_id,
                    position.template_version,
                    position.entry_thesis,
                    position.lifecycle_state.value,
                    position.opened_at.isoformat(),
                    position.closed_at.isoformat() if position.closed_at else None,
                ),
            )

    def get_position(self, position_id: str) -> Optional[ObservationPosition]:
        """Retrieve an observation position by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM observation_positions WHERE position_id = ?",
                (position_id,),
            ).fetchone()

            if not row:
                return None

            return ObservationPosition(
                position_id=row["position_id"],
                source_log_id=row["source_log_id"],
                execution_card_id=row["execution_card_id"],
                signal_id=row["signal_id"],
                action_plan_id=row["action_plan_id"],
                capital_context_id=row["capital_context_id"],
                symbol=row["symbol"],
                name=row["name"],
                entry_price=row["entry_price"],
                quantity=row["quantity"],
                template_id=row["template_id"],
                template_version=row["template_version"],
                entry_thesis=row["entry_thesis"],
                lifecycle_state=PositionLifecycleState(row["lifecycle_state"]),
                opened_at=datetime.fromisoformat(row["opened_at"]),
                closed_at=datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None,
            )

    def save_daily_signal(self, signal: DailyObservationSignal) -> None:
        """Save a deterministic daily observation signal."""
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO daily_observation_signals (
                    signal_record_id, position_id, signal_type,
                    triggered_invalidations, as_of_date, market_data_state,
                    rule_trace, plain_explanation, explanation_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.signal_record_id,
                    signal.position_id,
                    signal.signal_type.value if signal.signal_type else None,
                    json.dumps([trigger.value for trigger in signal.triggered_invalidations], ensure_ascii=False),
                    signal.as_of_date.isoformat(),
                    signal.market_data_state.value,
                    json.dumps(signal.rule_trace, ensure_ascii=False),
                    signal.plain_explanation,
                    signal.explanation_source.value,
                ),
            )

    def list_daily_signals(self, position_id: str) -> list[DailyObservationSignal]:
        """List daily signals for a position ordered by signal date."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM daily_observation_signals
                WHERE position_id = ?
                ORDER BY as_of_date ASC
                """,
                (position_id,),
            ).fetchall()

            signals = []
            for row in rows:
                triggered = [
                    InvalidationTrigger(value)
                    for value in json.loads(row["triggered_invalidations"])
                ]
                signals.append(
                    DailyObservationSignal(
                        signal_record_id=row["signal_record_id"],
                        position_id=row["position_id"],
                        signal_type=DailySignalType(row["signal_type"]) if row["signal_type"] else None,
                        triggered_invalidations=triggered,
                        as_of_date=datetime.fromisoformat(row["as_of_date"]),
                        market_data_state=MarketDataFaultState(row["market_data_state"]),
                        rule_trace=json.loads(row["rule_trace"]),
                        plain_explanation=row["plain_explanation"],
                        explanation_source=ExplanationSource(row["explanation_source"]),
                    )
                )

            return signals

    def save_discipline_review(self, review: DisciplineReview) -> None:
        """Save a discipline review and nested P&L record as immutable JSON."""
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO discipline_reviews (
                    review_id, position_id, execution_card_id, signal_id,
                    review_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    review.review_id,
                    review.position_id,
                    review.execution_card_id,
                    review.signal_id,
                    review.model_dump_json(),
                    review.created_at.isoformat(),
                ),
            )

    def get_discipline_review(self, review_id: str) -> Optional[DisciplineReview]:
        """Retrieve a discipline review by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT review_json FROM discipline_reviews WHERE review_id = ?",
                (review_id,),
            ).fetchone()

            if not row:
                return None

            return DisciplineReview.model_validate_json(row["review_json"])

    def list_open_positions(self) -> list[ObservationPosition]:
        """List all open observation positions."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM observation_positions
                WHERE lifecycle_state = 'open'
                ORDER BY opened_at DESC
                """,
            ).fetchall()

            return [
                ObservationPosition(
                    position_id=row["position_id"],
                    source_log_id=row["source_log_id"],
                    execution_card_id=row["execution_card_id"],
                    signal_id=row["signal_id"],
                    action_plan_id=row["action_plan_id"],
                    capital_context_id=row["capital_context_id"],
                    symbol=row["symbol"],
                    name=row["name"],
                    entry_price=row["entry_price"],
                    quantity=row["quantity"],
                    template_id=row["template_id"],
                    template_version=row["template_version"],
                    entry_thesis=row["entry_thesis"],
                    lifecycle_state=PositionLifecycleState(row["lifecycle_state"]),
                    opened_at=datetime.fromisoformat(row["opened_at"]),
                    closed_at=datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None,
                )
                for row in rows
            ]

    def list_all_positions(self) -> list[ObservationPosition]:
        """List all observation positions (both open and closed)."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM observation_positions
                ORDER BY opened_at DESC
                """,
            ).fetchall()

            return [
                ObservationPosition(
                    position_id=row["position_id"],
                    source_log_id=row["source_log_id"],
                    execution_card_id=row["execution_card_id"],
                    signal_id=row["signal_id"],
                    action_plan_id=row["action_plan_id"],
                    capital_context_id=row["capital_context_id"],
                    symbol=row["symbol"],
                    name=row["name"],
                    entry_price=row["entry_price"],
                    quantity=row["quantity"],
                    template_id=row["template_id"],
                    template_version=row["template_version"],
                    entry_thesis=row["entry_thesis"],
                    lifecycle_state=PositionLifecycleState(row["lifecycle_state"]),
                    opened_at=datetime.fromisoformat(row["opened_at"]),
                    closed_at=datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None,
                )
                for row in rows
            ]

    def get_latest_daily_signal(self, position_id: str) -> Optional[DailyObservationSignal]:
        """Get the latest daily signal for a position."""
        with self._get_conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM daily_observation_signals
                WHERE position_id = ?
                ORDER BY as_of_date DESC
                LIMIT 1
                """,
                (position_id,),
            ).fetchone()

            if not row:
                return None

            triggered = [
                InvalidationTrigger(value)
                for value in json.loads(row["triggered_invalidations"])
            ]

            return DailyObservationSignal(
                signal_record_id=row["signal_record_id"],
                position_id=row["position_id"],
                signal_type=DailySignalType(row["signal_type"]) if row["signal_type"] else None,
                triggered_invalidations=triggered,
                as_of_date=datetime.fromisoformat(row["as_of_date"]),
                market_data_state=MarketDataFaultState(row["market_data_state"]),
                rule_trace=json.loads(row["rule_trace"]),
                plain_explanation=row["plain_explanation"],
                explanation_source=ExplanationSource(row["explanation_source"]),
            )
