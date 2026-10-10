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
from decimal import Decimal
from datetime import date, datetime
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
    TradeType,
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
                    draft_id TEXT,
                    execution_card_id TEXT,
                    signal_id TEXT,
                    action_plan_id TEXT,
                    capital_context_id TEXT,
                    market_snapshot_id TEXT,
                    confirmed_action TEXT NOT NULL,
                    confirmed_execution_status TEXT NOT NULL,
                    confirmed_price REAL,
                    confirmed_quantity INTEGER,
                    reason TEXT,
                    confirmed_by_user INTEGER NOT NULL CHECK(confirmed_by_user = 1),
                    broker_verified INTEGER NOT NULL CHECK(broker_verified = 0),
                    confirmed_at TEXT NOT NULL,
                    execution_date TEXT,
                    confirmed_fees REAL,
                    symbol TEXT,
                    name TEXT,
                    record_source TEXT NOT NULL DEFAULT 'strategy_plan',
                    trade_type TEXT NOT NULL DEFAULT 'unknown'
                        CHECK(trade_type IN ('actual', 'simulated', 'unknown')),
                    operation_id TEXT,
                    operation_fingerprint TEXT,
                    operation_response TEXT,
                    voided_at TEXT,
                    void_reason TEXT,
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
                    execution_card_id TEXT,
                    signal_id TEXT,
                    action_plan_id TEXT,
                    capital_context_id TEXT,
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
                    record_source TEXT NOT NULL DEFAULT 'strategy_plan',
                    trade_type TEXT NOT NULL DEFAULT 'unknown'
                        CHECK(trade_type IN ('actual', 'simulated', 'unknown')),
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
                    position_id TEXT,
                    execution_card_id TEXT,
                    signal_id TEXT,
                    review_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    sell_log_id TEXT
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
            self._migrate_manual_ledger_schema(conn)
            self._migrate_discipline_review_schema(conn)
            self._migrate_structured_execution_fields(conn)
            self._migrate_manual_void_fields(conn)
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_logs_operation_id ON execution_observation_logs(operation_id) WHERE operation_id IS NOT NULL"
            )

    @staticmethod
    def _migrate_structured_execution_fields(conn: sqlite3.Connection) -> None:
        """Add structured manual execution facts without changing historical rows."""
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(execution_observation_logs)")
        }
        definitions = {
            "confirmed_trade_amount": "TEXT",
            "security_type": "TEXT NOT NULL DEFAULT 'unknown'",
            "quantity_unit": "TEXT NOT NULL DEFAULT 'unknown'",
            "trade_source": "TEXT",
            "sell_reason": "TEXT",
            "exit_plan_target_price": "REAL",
            "exit_plan_stop_price": "REAL",
            "exit_plan_conditions": "TEXT",
            "exit_plan_entered_at": "TEXT",
            "exit_plan_is_retrospective": "INTEGER",
        }
        for name, definition in definitions.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE execution_observation_logs ADD COLUMN {name} {definition}")

    @staticmethod
    def _migrate_manual_void_fields(conn: sqlite3.Connection) -> None:
        """Add audit-only void metadata without changing existing trade facts."""
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(execution_observation_logs)")
        }
        if "voided_at" not in columns:
            conn.execute("ALTER TABLE execution_observation_logs ADD COLUMN voided_at TEXT")
        if "void_reason" not in columns:
            conn.execute("ALTER TABLE execution_observation_logs ADD COLUMN void_reason TEXT")

    @staticmethod
    def _migrate_manual_ledger_schema(conn: sqlite3.Connection) -> None:
        """Make plan provenance optional only for explicitly autonomous manual records."""
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN IMMEDIATE")
        try:
            log_info = {row[1]: row for row in conn.execute("PRAGMA table_info(execution_observation_logs)")}
            log_needs_rebuild = (
                any(log_info[name][3] for name in (
                    "draft_id", "execution_card_id", "signal_id", "action_plan_id",
                    "capital_context_id", "market_snapshot_id",
                ))
                or not {"execution_date", "confirmed_fees", "symbol", "name", "record_source", "operation_id",
                        "operation_fingerprint", "operation_response", "trade_type"}.issubset(log_info)
            )
            position_info = {row[1]: row for row in conn.execute("PRAGMA table_info(observation_positions)")}
            position_needs_rebuild = (
                any(position_info[name][3] for name in (
                    "execution_card_id", "signal_id", "action_plan_id", "capital_context_id",
                ))
                or "record_source" not in position_info
                or "trade_type" not in position_info
            )
            review_info = {row[1]: row for row in conn.execute("PRAGMA table_info(discipline_reviews)")}
            review_needs_rebuild = any(review_info[name][3] for name in ("execution_card_id", "signal_id"))

            if log_needs_rebuild:
                conn.execute("""
                    CREATE TABLE execution_observation_logs_manual (
                        log_id TEXT PRIMARY KEY, draft_id TEXT, execution_card_id TEXT, signal_id TEXT,
                        action_plan_id TEXT, capital_context_id TEXT, market_snapshot_id TEXT,
                        confirmed_action TEXT NOT NULL, confirmed_execution_status TEXT NOT NULL,
                        confirmed_price REAL, confirmed_quantity INTEGER, reason TEXT,
                        confirmed_by_user INTEGER NOT NULL CHECK(confirmed_by_user = 1),
                        broker_verified INTEGER NOT NULL CHECK(broker_verified = 0), confirmed_at TEXT NOT NULL,
                        execution_date TEXT,
                        confirmed_fees REAL, symbol TEXT, name TEXT,
                        record_source TEXT NOT NULL DEFAULT 'strategy_plan', operation_id TEXT,
                        trade_type TEXT NOT NULL DEFAULT 'unknown'
                            CHECK(trade_type IN ('actual', 'simulated', 'unknown')),
                        operation_fingerprint TEXT, operation_response TEXT,
                        confirmed_trade_amount TEXT,
                        security_type TEXT NOT NULL DEFAULT 'unknown',
                        quantity_unit TEXT NOT NULL DEFAULT 'unknown',
                        trade_source TEXT, sell_reason TEXT,
                        exit_plan_target_price REAL, exit_plan_stop_price REAL,
                        exit_plan_conditions TEXT, exit_plan_entered_at TEXT,
                        exit_plan_is_retrospective INTEGER,
                        FOREIGN KEY (draft_id) REFERENCES execution_observation_drafts(draft_id)
                    )
                """)
                old_cols = set(log_info)
                old_fields = [
                    "log_id", "draft_id", "execution_card_id", "signal_id", "action_plan_id",
                    "capital_context_id", "market_snapshot_id", "confirmed_action",
                    "confirmed_execution_status", "confirmed_price", "confirmed_quantity", "reason",
                    "confirmed_by_user", "broker_verified", "confirmed_at",
                ]
                new_fields = [
                    "execution_date", "confirmed_fees", "symbol", "name", "record_source", "operation_id",
                    "trade_type", "operation_fingerprint", "operation_response", "confirmed_trade_amount",
                    "security_type", "quantity_unit", "trade_source", "sell_reason",
                    "exit_plan_target_price", "exit_plan_stop_price", "exit_plan_conditions",
                    "exit_plan_entered_at", "exit_plan_is_retrospective",
                ]
                defaults = {
                    "record_source": "'strategy_plan'",
                    "trade_type": "'unknown'",
                    "security_type": "'unknown'",
                    "quantity_unit": "'unknown'",
                }
                expressions = [
                    name if name in old_cols else defaults.get(name, "NULL")
                    for name in old_fields + new_fields
                ]
                fields = ", ".join(old_fields + new_fields)
                conn.execute(
                    f"INSERT INTO execution_observation_logs_manual ({fields}) "
                    f"SELECT {', '.join(expressions)} FROM execution_observation_logs"
                )
                conn.execute("DROP TABLE execution_observation_logs")
                conn.execute("ALTER TABLE execution_observation_logs_manual RENAME TO execution_observation_logs")

            if position_needs_rebuild:
                conn.execute("""
                    CREATE TABLE observation_positions_manual (
                        position_id TEXT PRIMARY KEY, source_log_id TEXT NOT NULL,
                        execution_card_id TEXT, signal_id TEXT, action_plan_id TEXT, capital_context_id TEXT,
                        symbol TEXT NOT NULL, name TEXT NOT NULL, entry_price REAL NOT NULL, quantity INTEGER NOT NULL,
                        template_id TEXT NOT NULL, template_version TEXT NOT NULL, entry_thesis TEXT NOT NULL,
                        lifecycle_state TEXT NOT NULL, opened_at TEXT NOT NULL, closed_at TEXT,
                        record_source TEXT NOT NULL DEFAULT 'strategy_plan',
                        trade_type TEXT NOT NULL DEFAULT 'unknown'
                            CHECK(trade_type IN ('actual', 'simulated', 'unknown')),
                        FOREIGN KEY (source_log_id) REFERENCES execution_observation_logs(log_id)
                    )
                """)
                old_cols = set(position_info)
                old_fields = [
                    "position_id", "source_log_id", "execution_card_id", "signal_id", "action_plan_id",
                    "capital_context_id", "symbol", "name", "entry_price", "quantity", "template_id",
                    "template_version", "entry_thesis", "lifecycle_state", "opened_at", "closed_at",
                ]
                fields_with_source = old_fields + ["record_source", "trade_type"]
                expressions = [name if name in old_cols else "NULL" for name in old_fields]
                expressions += ["record_source" if "record_source" in old_cols else "'strategy_plan'"]
                expressions += ["trade_type" if "trade_type" in old_cols else "'unknown'"]
                conn.execute(
                    f"INSERT INTO observation_positions_manual ({', '.join(fields_with_source)}) "
                    f"SELECT {', '.join(expressions)} FROM observation_positions"
                )
                conn.execute("DROP TABLE observation_positions")
                conn.execute("ALTER TABLE observation_positions_manual RENAME TO observation_positions")

            if review_needs_rebuild:
                conn.execute("""
                    CREATE TABLE discipline_reviews_manual (
                        review_id TEXT PRIMARY KEY, position_id TEXT NOT NULL, execution_card_id TEXT,
                        signal_id TEXT, review_json TEXT NOT NULL, created_at TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    INSERT INTO discipline_reviews_manual (
                        review_id, position_id, execution_card_id, signal_id, review_json, created_at
                    ) SELECT review_id, position_id, execution_card_id, signal_id, review_json, created_at
                    FROM discipline_reviews
                """)
                conn.execute("DROP TABLE discipline_reviews")
                conn.execute("ALTER TABLE discipline_reviews_manual RENAME TO discipline_reviews")

            conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_execution_card ON execution_observation_logs(execution_card_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_draft ON execution_observation_logs(draft_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_lifecycle ON observation_positions(lifecycle_state)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_position ON discipline_reviews(position_id)")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute("PRAGMA foreign_keys = ON")

    @staticmethod
    def _migrate_discipline_review_schema(conn: sqlite3.Connection) -> None:
        """Allow sale reviews without a position and index their source sell log."""
        review_info = {row[1]: row for row in conn.execute("PRAGMA table_info(discipline_reviews)")}
        needs_rebuild = review_info["position_id"][3] != 0 or "sell_log_id" not in review_info
        if needs_rebuild:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "CREATE TABLE discipline_reviews_manual ("
                    "review_id TEXT PRIMARY KEY, position_id TEXT, execution_card_id TEXT, "
                    "signal_id TEXT, review_json TEXT NOT NULL, created_at TEXT NOT NULL, sell_log_id TEXT)"
                )
                old_columns = set(review_info)
                for row in conn.execute("SELECT * FROM discipline_reviews").fetchall():
                    review_json = row["review_json"]
                    try:
                        review_payload = json.loads(review_json)
                    except (TypeError, json.JSONDecodeError):
                        review_payload = {}
                    sell_log_id = (
                        row["sell_log_id"] if "sell_log_id" in old_columns
                        else review_payload.get("sell_log_id")
                    )
                    conn.execute(
                        "INSERT INTO discipline_reviews_manual "
                        "(review_id, position_id, execution_card_id, signal_id, review_json, created_at, sell_log_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            row["review_id"], row["position_id"], row["execution_card_id"],
                            row["signal_id"], review_json, row["created_at"], sell_log_id or None,
                        ),
                    )
                conn.execute("DROP TABLE discipline_reviews")
                conn.execute("ALTER TABLE discipline_reviews_manual RENAME TO discipline_reviews")
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_position ON discipline_reviews(position_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_sell_log ON discipline_reviews(sell_log_id)")

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
                    confirmed_by_user, broker_verified, confirmed_at, trade_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    log.trade_type.value,
                ),
            )

    def get_manual_operation(self, operation_id: str) -> Optional[dict]:
        """Return a previously committed manual trade operation for idempotent retry."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT operation_fingerprint, operation_response FROM execution_observation_logs "
                "WHERE operation_id = ? AND record_source = 'autonomous_manual'",
                (operation_id,),
            ).fetchone()
            return dict(row) if row else None

    @staticmethod
    def _sellable_quantity_in_connection(
        conn: sqlite3.Connection,
        *,
        symbol: str,
        trade_type: TradeType,
        record_source: str,
        execution_date: date,
    ) -> int:
        if trade_type not in {TradeType.actual, TradeType.simulated}:
            return 0
        row = conn.execute(
            """
            SELECT COALESCE(SUM(
                CASE
                    WHEN confirmed_action = 'buy' AND execution_date < ?
                        THEN COALESCE(confirmed_quantity, 0)
                    WHEN confirmed_action = 'sell' AND execution_date <= ?
                        THEN -COALESCE(confirmed_quantity, 0)
                    ELSE 0
                END
            ), 0) AS available
            FROM execution_observation_logs
            WHERE symbol = ? AND trade_type = ? AND record_source = ?
              AND confirmed_execution_status IN ('executed_full', 'executed_partial')
              AND voided_at IS NULL
            """,
            (execution_date.isoformat(), execution_date.isoformat(), symbol, trade_type.value, record_source),
        ).fetchone()
        return max(0, int(row["available"] or 0))

    @staticmethod
    def _position_quantity_in_connection(
        conn: sqlite3.Connection,
        *,
        symbol: str,
        trade_type: TradeType,
        record_source: str,
        execution_date: date,
    ) -> int:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(
                CASE
                    WHEN confirmed_action = 'buy' AND execution_date <= ?
                        THEN COALESCE(confirmed_quantity, 0)
                    WHEN confirmed_action = 'sell' AND execution_date <= ?
                        THEN -COALESCE(confirmed_quantity, 0)
                    ELSE 0
                END
            ), 0) AS held
            FROM execution_observation_logs
            WHERE symbol = ? AND trade_type = ? AND record_source = ?
              AND confirmed_execution_status IN ('executed_full', 'executed_partial')
              AND voided_at IS NULL
            """,
            (execution_date.isoformat(), execution_date.isoformat(), symbol, trade_type.value, record_source),
        ).fetchone()
        return max(0, int(row["held"] or 0))

    def get_sellable_quantity(
        self,
        *,
        symbol: str,
        trade_type: TradeType,
        record_source: str,
        execution_date: date,
    ) -> int:
        """Return prior-day buys less effective sells through the sell date."""
        with self._get_conn() as conn:
            return self._sellable_quantity_in_connection(
                conn,
                symbol=symbol,
                trade_type=trade_type,
                record_source=record_source,
                execution_date=execution_date,
            )

    def get_position_quantity(
        self,
        *,
        symbol: str,
        trade_type: TradeType,
        record_source: str,
        execution_date: date,
    ) -> int:
        """Return total held shares, including buys made on the execution date."""
        with self._get_conn() as conn:
            return self._position_quantity_in_connection(
                conn,
                symbol=symbol,
                trade_type=trade_type,
                record_source=record_source,
                execution_date=execution_date,
            )

    def list_manual_position_logs(
        self,
        *,
        symbol: str,
        trade_type: TradeType,
        record_source: str,
        execution_date: date,
    ) -> list[ExecutionObservationLog]:
        """Read the active known-type ledger events needed for one position calculation."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT log_id FROM execution_observation_logs
                WHERE symbol = ? AND trade_type = ? AND record_source = ?
                  AND execution_date <= ?
                  AND confirmed_execution_status IN ('executed_full', 'executed_partial')
                  AND voided_at IS NULL
                ORDER BY execution_date, confirmed_at, log_id
                """,
                (symbol, trade_type.value, record_source, execution_date.isoformat()),
            ).fetchall()
        return [log for row in rows if (log := self.get_log(row["log_id"])) is not None]

    @staticmethod
    def _validate_voided_manual_scope(conn: sqlite3.Connection, target: sqlite3.Row) -> None:
        if (
            target["record_source"] != "autonomous_manual"
            or target["trade_type"] not in {TradeType.actual.value, TradeType.simulated.value}
            or not target["symbol"]
        ):
            return
        if target["confirmed_action"] == "buy" and target["execution_date"]:
            dependent_sale = conn.execute(
                """
                SELECT log_id FROM execution_observation_logs
                WHERE symbol = ? AND trade_type = ? AND record_source = ?
                  AND confirmed_action = 'sell'
                  AND confirmed_execution_status IN ('executed_full', 'executed_partial')
                  AND voided_at IS NULL
                  AND (
                    execution_date > ?
                    OR (execution_date = ? AND (
                      confirmed_at > ? OR (confirmed_at = ? AND log_id > ?)
                    ))
                  )
                LIMIT 1
                """,
                (
                    target["symbol"], target["trade_type"], target["record_source"],
                    target["execution_date"], target["execution_date"],
                    target["confirmed_at"], target["confirmed_at"], target["log_id"],
                ),
            ).fetchone()
            if dependent_sale:
                raise ValueError("该买入已参与后续卖出的成本计算；请先作废依赖的卖出记录。")
        rows = conn.execute(
            """
            SELECT log_id, confirmed_action, confirmed_quantity, execution_date
            FROM execution_observation_logs
            WHERE symbol = ? AND trade_type = ? AND record_source = ?
              AND confirmed_execution_status IN ('executed_full', 'executed_partial')
              AND voided_at IS NULL AND log_id != ?
            ORDER BY execution_date, confirmed_at, log_id
            """,
            (target["symbol"], target["trade_type"], target["record_source"], target["log_id"]),
        ).fetchall()
        if any(row["confirmed_action"] == "sell" and not row["execution_date"] for row in rows):
            raise ValueError("存在成交日期未知的有效卖出，先核对依赖记录后再作废。")
        available = 0
        dates = sorted({row["execution_date"] for row in rows if row["execution_date"]})
        for event_date in dates:
            day_rows = [row for row in rows if row["execution_date"] == event_date]
            sold = sum(
                int(row["confirmed_quantity"] or 0)
                for row in day_rows if row["confirmed_action"] == "sell"
            )
            if sold > available:
                raise ValueError("仍有依赖该买入的有效卖出；请先作废依赖的卖出记录。")
            available -= sold
            available += sum(
                int(row["confirmed_quantity"] or 0)
                for row in day_rows if row["confirmed_action"] == "buy"
            )

    @staticmethod
    def _validate_legacy_void_dependencies(conn: sqlite3.Connection, target: sqlite3.Row) -> None:
        if target["confirmed_action"] != "buy":
            return
        positions = conn.execute(
            "SELECT position_id FROM observation_positions WHERE source_log_id = ?",
            (target["log_id"],),
        ).fetchall()
        for position in positions:
            active_sale = conn.execute(
                """
                SELECT el.log_id
                FROM discipline_reviews dr
                JOIN execution_observation_logs el ON el.log_id = dr.sell_log_id
                WHERE dr.position_id = ? AND el.confirmed_action = 'sell'
                  AND el.voided_at IS NULL
                LIMIT 1
                """,
                (position["position_id"],),
            ).fetchone()
            if active_sale:
                raise ValueError("该买入仍有依赖的有效卖出；请先作废依赖的卖出记录。")

    @staticmethod
    def _rebuild_manual_position_scope(
        conn: sqlite3.Connection,
        *,
        symbol: str,
        trade_type: str,
        record_source: str,
        changed_at: datetime,
    ) -> int:
        rows = conn.execute(
            """
            SELECT log_id, confirmed_action, confirmed_quantity, confirmed_price,
                   confirmed_at, execution_date, name
            FROM execution_observation_logs
            WHERE symbol = ? AND trade_type = ? AND record_source = ?
              AND confirmed_execution_status IN ('executed_full', 'executed_partial')
              AND voided_at IS NULL
            ORDER BY execution_date, confirmed_at, log_id
            """,
            (symbol, trade_type, record_source),
        ).fetchall()
        held = 0
        gross_basis = Decimal("0")
        active_buys = [row for row in rows if row["confirmed_action"] == "buy"]
        latest_sell_at = None
        dates = sorted({row["execution_date"] for row in rows if row["execution_date"]})
        for event_date in dates:
            day_rows = [row for row in rows if row["execution_date"] == event_date]
            sellable_held = held
            for row in sorted(day_rows, key=lambda item: (item["confirmed_at"], item["log_id"])):
                if row["confirmed_action"] == "buy" and row["confirmed_quantity"] and row["confirmed_price"] is not None:
                    qty = int(row["confirmed_quantity"])
                    held += qty
                    gross_basis += Decimal(str(row["confirmed_price"])) * qty
                elif row["confirmed_action"] == "sell" and row["confirmed_quantity"]:
                    qty = int(row["confirmed_quantity"])
                    if held <= 0 or qty > held or qty > sellable_held:
                        continue
                    gross_basis -= (gross_basis / held) * qty
                    held -= qty
                    sellable_held -= qty
                    latest_sell_at = row["confirmed_at"]
        positions = conn.execute(
            """
            SELECT position_id, quantity, entry_price FROM observation_positions
            WHERE symbol = ? AND trade_type = ? AND record_source = ?
            ORDER BY opened_at, position_id
            """,
            (symbol, trade_type, record_source),
        ).fetchall()
        if not positions:
            return held
        canonical_id = positions[0]["position_id"]
        first_buy = active_buys[0] if active_buys else None
        if held > 0:
            average_price = float(gross_basis / held)
            conn.execute(
                """
                UPDATE observation_positions
                SET source_log_id = COALESCE(?, source_log_id),
                    name = COALESCE(?, name), entry_price = ?, quantity = ?,
                    lifecycle_state = 'open', opened_at = COALESCE(?, opened_at),
                    closed_at = NULL
                WHERE position_id = ?
                """,
                (
                    first_buy["log_id"] if first_buy else None,
                    first_buy["name"] if first_buy else None,
                    average_price,
                    held,
                    first_buy["confirmed_at"] if first_buy else None,
                    canonical_id,
                ),
            )
        else:
            # Closed rows retain their last valid positive quantity and basis for history;
            # lifecycle_state, not a fabricated zero-quantity position, removes inventory.
            conn.execute(
                "UPDATE observation_positions SET lifecycle_state = 'closed', closed_at = ? WHERE position_id = ?",
                (latest_sell_at or changed_at.isoformat(), canonical_id),
            )
        for row in positions[1:]:
            conn.execute(
                "UPDATE observation_positions SET lifecycle_state = 'closed', closed_at = ? WHERE position_id = ?",
                (changed_at.isoformat(), row["position_id"]),
            )
        return held

    @staticmethod
    def _invalidate_reviews_for_void(conn: sqlite3.Connection, log_id: str) -> None:
        rows = conn.execute(
            "SELECT review_id, review_json FROM discipline_reviews WHERE sell_log_id = ?",
            (log_id,),
        ).fetchall()
        for row in rows:
            try:
                payload = json.loads(row["review_json"])
                payload["ai_review_text"] = None
                payload["ai_review_status"] = "not_requested"
                payload["deterministic_summary"] = "关联成交记录已作废；该复盘不再计入当前盈亏。"
                pnl = payload.get("pnl_record") or {}
                pnl.update({
                    "gross_pnl_amount": None,
                    "gross_pnl_pct": None,
                    "pnl_amount": None,
                    "pnl_pct": None,
                    "fees": None,
                    "pnl_source": "incomplete",
                    "missing_fields": list(dict.fromkeys([*(pnl.get("missing_fields") or []), "voided_trade"])),
                })
                fee = pnl.get("fee_calculation") or {}
                fee.update({"source": "unknown", "amount": None, "note": "关联成交记录已作废。"})
                pnl["fee_calculation"] = fee
                payload["pnl_record"] = pnl
                plan = payload.get("plan_comparison") or {}
                plan["message"] = "关联成交记录已作废，计划对照不再适用"
                payload["plan_comparison"] = plan
                conn.execute(
                    "UPDATE discipline_reviews SET review_json = ? WHERE review_id = ?",
                    (json.dumps(payload, ensure_ascii=False), row["review_id"]),
                )
            except (TypeError, ValueError, KeyError):
                # Preserve an unparseable historical review; the API hides it with its voided sell.
                continue

    @staticmethod
    def _invalidate_scope_ai_reviews(
        conn: sqlite3.Connection,
        *,
        symbol: str,
        trade_type: str,
        record_source: str,
    ) -> None:
        positions = conn.execute(
            "SELECT position_id FROM observation_positions WHERE symbol = ? AND trade_type = ? AND record_source = ?",
            (symbol, trade_type, record_source),
        ).fetchall()
        position_ids = {row["position_id"] for row in positions}
        for position_id in position_ids:
            reviews = conn.execute(
                "SELECT review_id, review_json FROM discipline_reviews WHERE position_id = ?",
                (position_id,),
            ).fetchall()
            for row in reviews:
                try:
                    payload = json.loads(row["review_json"])
                except (TypeError, ValueError):
                    continue
                payload["ai_review_text"] = None
                payload["ai_review_status"] = "not_requested"
                conn.execute(
                    "UPDATE discipline_reviews SET review_json = ? WHERE review_id = ?",
                    (json.dumps(payload, ensure_ascii=False), row["review_id"]),
                )

    def _rebuild_legacy_position_for_void(
        self,
        conn: sqlite3.Connection,
        *,
        target: sqlite3.Row,
        changed_at: datetime,
    ) -> None:
        position_ids = set()
        if target["confirmed_action"] == "buy":
            rows = conn.execute(
                "SELECT position_id FROM observation_positions WHERE source_log_id = ?",
                (target["log_id"],),
            ).fetchall()
            position_ids.update(row["position_id"] for row in rows)
        review_rows = conn.execute(
            "SELECT review_json FROM discipline_reviews WHERE sell_log_id = ?",
            (target["log_id"],),
        ).fetchall()
        for row in review_rows:
            try:
                position_id = json.loads(row["review_json"]).get("position_id")
                if position_id:
                    position_ids.add(position_id)
            except (TypeError, ValueError):
                continue
        for position_id in position_ids:
            position = conn.execute(
                "SELECT * FROM observation_positions WHERE position_id = ?", (position_id,)
            ).fetchone()
            if not position:
                continue
            buy = conn.execute(
                "SELECT confirmed_quantity, confirmed_price FROM execution_observation_logs WHERE log_id = ?",
                (position["source_log_id"],),
            ).fetchone()
            if not buy:
                continue
            sells = conn.execute(
                """
                SELECT el.confirmed_quantity, el.confirmed_at
                FROM discipline_reviews dr
                JOIN execution_observation_logs el ON el.log_id = dr.sell_log_id
                WHERE dr.position_id = ? AND el.confirmed_action = 'sell' AND el.voided_at IS NULL
                  AND el.confirmed_execution_status IN ('executed_full', 'executed_partial', 'filled')
                """,
                (position_id,),
            ).fetchall()
            buy_quantity = 0 if target["log_id"] == position["source_log_id"] else int(buy["confirmed_quantity"] or 0)
            sold = sum(int(row["confirmed_quantity"] or 0) for row in sells)
            remaining = max(0, buy_quantity - sold)
            closed_at = max((row["confirmed_at"] for row in sells), default=changed_at.isoformat()) if remaining == 0 else None
            if remaining > 0:
                conn.execute(
                    "UPDATE observation_positions SET quantity = ?, lifecycle_state = 'open', closed_at = NULL WHERE position_id = ?",
                    (remaining, position_id),
                )
            else:
                conn.execute(
                    "UPDATE observation_positions SET lifecycle_state = 'closed', closed_at = ? WHERE position_id = ?",
                    (closed_at, position_id),
                )

    def void_execution_log(self, log_id: str, reason: str, voided_at: Optional[datetime] = None) -> dict:
        """Append an auditable void state and atomically rebuild its derived position."""
        reason = reason.strip()
        if not reason:
            raise ValueError("作废原因必填。")
        if len(reason) > 160:
            raise ValueError("作废原因不能超过160个字符。")
        now = voided_at or datetime.now()
        with self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            target = conn.execute(
                "SELECT * FROM execution_observation_logs WHERE log_id = ?", (log_id,)
            ).fetchone()
            if not target:
                raise KeyError(log_id)
            if target["voided_at"]:
                if target["void_reason"] == reason:
                    return {
                        "status": "already_voided",
                        "log_id": log_id,
                        "voided_at": target["voided_at"],
                        "void_reason": target["void_reason"],
                    }
                raise ValueError("该记录已作废；请使用原作废原因重试。")
            self._validate_voided_manual_scope(conn, target)
            self._validate_legacy_void_dependencies(conn, target)
            conn.execute(
                "UPDATE execution_observation_logs SET voided_at = ?, void_reason = ? "
                "WHERE log_id = ? AND voided_at IS NULL",
                (now.isoformat(), reason, log_id),
            )
            self._invalidate_reviews_for_void(conn, log_id)
            if (
                target["record_source"] == "autonomous_manual"
                and target["trade_type"] in {TradeType.actual.value, TradeType.simulated.value}
                and target["symbol"]
            ):
                remaining = self._rebuild_manual_position_scope(
                    conn,
                    symbol=target["symbol"],
                    trade_type=target["trade_type"],
                    record_source=target["record_source"],
                    changed_at=now,
                )
                self._invalidate_scope_ai_reviews(
                    conn,
                    symbol=target["symbol"],
                    trade_type=target["trade_type"],
                    record_source=target["record_source"],
                )
            else:
                self._rebuild_legacy_position_for_void(conn, target=target, changed_at=now)
                remaining = None
            return {
                "status": "voided",
                "log_id": log_id,
                "voided_at": now.isoformat(),
                "void_reason": reason,
                "remaining_quantity": remaining,
            }

    def save_manual_operation(
        self,
        log: ExecutionObservationLog,
        response: dict,
        *,
        position: Optional[ObservationPosition] = None,
        close_position_id: Optional[str] = None,
        remaining_quantity: Optional[int] = None,
        review: Optional[DisciplineReview] = None,
    ) -> None:
        """Atomically persist one confirmed manual event and its direct ledger effects."""
        if log.record_source != "autonomous_manual" or not log.operation_id or not log.operation_fingerprint:
            raise ValueError("manual operation requires autonomous provenance and an idempotency key")
        if log.trade_type.value not in {"actual", "simulated"}:
            raise ValueError("manual operation requires an explicit actual or simulated trade type")
        if position and position.trade_type != log.trade_type:
            raise ValueError("position trade type must match its source log")
        if review and review.trade_type != log.trade_type:
            raise ValueError("review trade type must match the execution")
        with self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if position:
                open_rows = conn.execute(
                    """
                    SELECT position_id, entry_price, quantity FROM observation_positions
                    WHERE symbol = ? AND trade_type = ? AND record_source = ?
                      AND lifecycle_state = 'open'
                    ORDER BY opened_at, position_id
                    """,
                    (position.symbol, position.trade_type.value, position.record_source),
                ).fetchall()
                if open_rows:
                    existing_quantity = sum(int(row["quantity"]) for row in open_rows)
                    incoming_quantity = int(log.confirmed_quantity or 0)
                    combined_quantity = existing_quantity + incoming_quantity
                    weighted_cost = sum(
                        Decimal(str(row["entry_price"])) * int(row["quantity"])
                        for row in open_rows
                    ) + Decimal(str(log.confirmed_price)) * incoming_quantity
                    average_price = weighted_cost / combined_quantity
                    position_id = open_rows[0]["position_id"]
                    conn.execute(
                        "UPDATE observation_positions SET quantity = ?, entry_price = ? WHERE position_id = ?",
                        (combined_quantity, float(average_price), position_id),
                    )
                    for duplicate in open_rows[1:]:
                        conn.execute(
                            "UPDATE observation_positions SET lifecycle_state = 'closed', "
                            "closed_at = ? WHERE position_id = ?",
                            (log.confirmed_at.isoformat(), duplicate["position_id"]),
                        )
                    response["position_id"] = position_id
                    position = None
            if log.confirmed_action == "sell":
                if log.execution_date is None or not close_position_id:
                    raise ValueError("a sell must be bound to an open position and execution date")
                matched_position = conn.execute(
                    "SELECT symbol, trade_type, record_source, lifecycle_state FROM observation_positions "
                    "WHERE position_id = ?",
                    (close_position_id,),
                ).fetchone()
                if (
                    not matched_position
                    or matched_position["symbol"] != log.symbol
                    or matched_position["trade_type"] != log.trade_type.value
                    or matched_position["record_source"] != log.record_source
                    or matched_position["lifecycle_state"] != "open"
                ):
                    raise ValueError("cannot sell against a closed or mismatched position")
                open_rows = conn.execute(
                    """
                    SELECT position_id FROM observation_positions
                    WHERE symbol = ? AND trade_type = ? AND record_source = ?
                      AND lifecycle_state = 'open'
                    ORDER BY opened_at, position_id
                    """,
                    (log.symbol, log.trade_type.value, log.record_source),
                ).fetchall()
                if not open_rows or close_position_id != open_rows[0]["position_id"]:
                    raise ValueError("refresh the position page and choose the current aggregated position")
                available = self._sellable_quantity_in_connection(
                    conn,
                    symbol=log.symbol,
                    trade_type=log.trade_type,
                    record_source=log.record_source,
                    execution_date=log.execution_date,
                )
                if log.confirmed_quantity is None or log.confirmed_quantity > available:
                    raise ValueError(
                        f"卖出数量超过可卖数量（当前最多 {available}）。若这是实际成交，请先补录遗漏的买入记录，再登记卖出。"
                    )
            conn.execute(
                """
                INSERT INTO execution_observation_logs (
                    log_id, draft_id, execution_card_id, signal_id, action_plan_id,
                    capital_context_id, market_snapshot_id, confirmed_action,
                    confirmed_execution_status, confirmed_price, confirmed_quantity,
                    reason, confirmed_by_user, broker_verified, confirmed_at, execution_date,
                    confirmed_fees, symbol, name, record_source, operation_id,
                    trade_type, operation_fingerprint, operation_response, confirmed_trade_amount,
                    security_type, quantity_unit, trade_source, sell_reason,
                    exit_plan_target_price, exit_plan_stop_price, exit_plan_conditions,
                    exit_plan_entered_at, exit_plan_is_retrospective
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log.log_id, log.draft_id, log.execution_card_id, log.signal_id,
                    log.action_plan_id, log.capital_context_id, log.market_snapshot_id,
                    log.confirmed_action, log.confirmed_execution_status, log.confirmed_price,
                    log.confirmed_quantity, log.reason, 1, 0, log.confirmed_at.isoformat(),
                    log.execution_date.isoformat() if log.execution_date else None,
                    log.confirmed_fees, log.symbol, log.name, log.record_source,
                    log.operation_id, log.trade_type.value, log.operation_fingerprint,
                    json.dumps(response, ensure_ascii=False),
                    log.confirmed_trade_amount, log.security_type, log.quantity_unit,
                    log.trade_source, log.sell_reason, log.exit_plan_target_price,
                    log.exit_plan_stop_price, log.exit_plan_conditions,
                    log.exit_plan_entered_at.isoformat() if log.exit_plan_entered_at else None,
                    None if log.exit_plan_is_retrospective is None else int(log.exit_plan_is_retrospective),
                ),
            )
            if position:
                conn.execute(
                    """
                    INSERT INTO observation_positions (
                        position_id, source_log_id, execution_card_id, signal_id,
                        action_plan_id, capital_context_id, symbol, name, entry_price,
                        quantity, template_id, template_version, entry_thesis,
                        lifecycle_state, opened_at, closed_at, record_source, trade_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        position.position_id, position.source_log_id, position.execution_card_id,
                        position.signal_id, position.action_plan_id, position.capital_context_id,
                        position.symbol, position.name, position.entry_price, position.quantity,
                        position.template_id, position.template_version, position.entry_thesis,
                        position.lifecycle_state.value, position.opened_at.isoformat(), None,
                        position.record_source, position.trade_type.value,
                    ),
                )
            if close_position_id:
                held_after_sell = self._position_quantity_in_connection(
                    conn,
                    symbol=log.symbol,
                    trade_type=log.trade_type,
                    record_source=log.record_source,
                    execution_date=log.execution_date,
                )
                if held_after_sell > 0:
                    conn.execute(
                        "UPDATE observation_positions SET quantity = ? WHERE position_id = ?",
                        (held_after_sell, close_position_id),
                    )
                else:
                    conn.execute(
                        "UPDATE observation_positions SET lifecycle_state = 'closed', closed_at = ? "
                        "WHERE position_id = ?",
                        (log.confirmed_at.isoformat(), close_position_id),
                    )
                for duplicate in open_rows[1:]:
                    conn.execute(
                        "UPDATE observation_positions SET quantity = 0, lifecycle_state = 'closed', "
                        "closed_at = ? WHERE position_id = ?",
                        (log.confirmed_at.isoformat(), duplicate["position_id"]),
                    )
            if review:
                conn.execute(
                    """
                    INSERT INTO discipline_reviews (
                        review_id, position_id, execution_card_id, signal_id, review_json, created_at
                        , sell_log_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review.review_id, review.position_id, review.execution_card_id,
                        review.signal_id, json.dumps(review.model_dump(), ensure_ascii=False, default=str),
                        review.created_at.isoformat(), review.sell_log_id,
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
                execution_date=date.fromisoformat(row["execution_date"]) if row["execution_date"] else None,
                confirmed_fees=row["confirmed_fees"],
                confirmed_trade_amount=row["confirmed_trade_amount"],
                symbol=row["symbol"],
                name=row["name"],
                security_type=row["security_type"],
                quantity_unit=row["quantity_unit"],
                trade_source=row["trade_source"],
                sell_reason=row["sell_reason"],
                exit_plan_target_price=row["exit_plan_target_price"],
                exit_plan_stop_price=row["exit_plan_stop_price"],
                exit_plan_conditions=row["exit_plan_conditions"],
                exit_plan_entered_at=datetime.fromisoformat(row["exit_plan_entered_at"])
                if row["exit_plan_entered_at"] else None,
                exit_plan_is_retrospective=bool(row["exit_plan_is_retrospective"])
                if row["exit_plan_is_retrospective"] is not None else None,
                trade_type=TradeType(row["trade_type"]),
                record_source=row["record_source"],
                operation_id=row["operation_id"],
                operation_fingerprint=row["operation_fingerprint"],
                operation_response=row["operation_response"],
                voided_at=datetime.fromisoformat(row["voided_at"]) if row["voided_at"] else None,
                void_reason=row["void_reason"],
            )

    def list_execution_logs(self) -> list[dict]:
        """Read confirmed execution history from the canonical live-trade ledger."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT log_id, execution_date, confirmed_at, confirmed_action,
                       confirmed_price, confirmed_quantity, confirmed_fees, reason,
                       symbol, name, record_source, action_plan_id,
                       confirmed_trade_amount, security_type, quantity_unit,
                       trade_source, sell_reason, exit_plan_target_price,
                       exit_plan_stop_price, exit_plan_conditions,
                       exit_plan_entered_at, exit_plan_is_retrospective, trade_type,
                       voided_at, void_reason
                FROM execution_observation_logs
                ORDER BY execution_date DESC, confirmed_at DESC, log_id DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]

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
                    execution_date=date.fromisoformat(row["execution_date"]) if row["execution_date"] else None,
                    confirmed_fees=row["confirmed_fees"],
                    confirmed_trade_amount=row["confirmed_trade_amount"],
                    symbol=row["symbol"],
                    name=row["name"],
                    security_type=row["security_type"],
                    quantity_unit=row["quantity_unit"],
                    trade_source=row["trade_source"],
                    sell_reason=row["sell_reason"],
                    exit_plan_target_price=row["exit_plan_target_price"],
                    exit_plan_stop_price=row["exit_plan_stop_price"],
                    exit_plan_conditions=row["exit_plan_conditions"],
                    exit_plan_entered_at=datetime.fromisoformat(row["exit_plan_entered_at"])
                    if row["exit_plan_entered_at"] else None,
                    exit_plan_is_retrospective=bool(row["exit_plan_is_retrospective"])
                    if row["exit_plan_is_retrospective"] is not None else None,
                    trade_type=TradeType(row["trade_type"]),
                    record_source=row["record_source"],
                    operation_id=row["operation_id"],
                    operation_fingerprint=row["operation_fingerprint"],
                    operation_response=row["operation_response"],
                    voided_at=datetime.fromisoformat(row["voided_at"]) if row["voided_at"] else None,
                    void_reason=row["void_reason"],
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
                    entry_thesis, lifecycle_state, opened_at, closed_at, record_source
                    , trade_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    position.record_source,
                    position.trade_type.value,
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
                trade_type=TradeType(row["trade_type"]),
                record_source=row["record_source"],
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
                    review_json, created_at, sell_log_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review.review_id,
                    review.position_id,
                    review.execution_card_id,
                    review.signal_id,
                    review.model_dump_json(),
                    review.created_at.isoformat(),
                    review.sell_log_id,
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
                    trade_type=TradeType(row["trade_type"]),
                    record_source=row["record_source"],
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
                    trade_type=TradeType(row["trade_type"]),
                    record_source=row["record_source"],
                )
                for row in rows
            ]

    def close_position(self, position_id: str, closed_at: datetime) -> None:
        """Close an observation position."""
        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE observation_positions
                SET lifecycle_state = 'closed', closed_at = ?
                WHERE position_id = ?
                """,
                (closed_at.isoformat(), position_id),
            )

    def find_open_position_by_symbol(
        self,
        symbol: str,
        record_source: Optional[str] = None,
        trade_type: TradeType = TradeType.unknown,
    ) -> Optional[ObservationPosition]:
        """Find open position by symbol and explicit ledger scope."""
        with self._get_conn() as conn:
            source_clause = " AND record_source = ?" if record_source else ""
            row = conn.execute(
                f"""
                SELECT * FROM observation_positions
                WHERE symbol = ? AND lifecycle_state = 'open'
                  AND trade_type = ?
                {source_clause}
                ORDER BY opened_at DESC
                LIMIT 1
                """,
                (symbol, trade_type.value, record_source) if record_source else (symbol, trade_type.value),
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
                trade_type=TradeType(row["trade_type"]),
                record_source=row["record_source"],
            )

    def save_discipline_review(self, review: DisciplineReview) -> None:
        """Save discipline review as JSON."""
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
                    json.dumps(review.model_dump(), ensure_ascii=False, default=str),
                    review.created_at.isoformat(),
                ),
            )

    def get_discipline_review(self, review_id: str) -> Optional[DisciplineReview]:
        """Retrieve discipline review by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT review_json FROM discipline_reviews WHERE review_id = ?",
                (review_id,),
            ).fetchone()

            if not row:
                return None

            review_data = json.loads(row["review_json"])
            return DisciplineReview(**review_data)

    def update_discipline_review_ai_text(self, review_id: str, ai_review_text: str) -> None:
        """Update only the generated text and availability of an existing review."""
        value = ai_review_text.strip() if isinstance(ai_review_text, str) else ""
        if not value:
            raise ValueError("AI review text must not be empty.")
        if any(character.isdigit() for character in value):
            raise ValueError("AI review text must not contain digits.")
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT review_json FROM discipline_reviews WHERE review_id = ?",
                (review_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Discipline review not found: {review_id}")
            try:
                payload = json.loads(row["review_json"])
            except (TypeError, ValueError) as exc:
                raise ValueError("Existing discipline review JSON is invalid.") from exc
            if not isinstance(payload, dict):
                raise ValueError("Existing discipline review JSON is invalid.")
            payload["ai_review_text"] = value
            payload["ai_review_status"] = "available"
            cursor = conn.execute(
                "UPDATE discipline_reviews SET review_json = ? WHERE review_id = ?",
                (json.dumps(payload, ensure_ascii=False), review_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Discipline review not found: {review_id}")

    def list_discipline_reviews(self) -> list[DisciplineReview]:
        """Read persisted sale reviews in newest-first order."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT review_json FROM discipline_reviews ORDER BY created_at DESC, review_id DESC"
            ).fetchall()
            return [DisciplineReview.model_validate_json(row["review_json"]) for row in rows]

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
