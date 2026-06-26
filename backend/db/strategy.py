from __future__ import annotations

import sqlite3
from datetime import datetime

from contracts.strategy import (
    BacktestUniverseSpec,
    ForwardWatchlistSnapshot,
    HumanConfirmationConsumption,
    HumanPromotionConfirmation,
    ImmutableBacktestReport,
    OOSEvaluationLedger,
    PrototypeGateResultV2,
    ResearchProtocolSnapshot,
    StrategyDraft,
    StrategyLifecycleState,
    StrategyPromotionRecord,
    StrategyTemplateDefinition,
)


IMMUTABLE_TABLES = (
    "strategy_template_definitions",
    "backtest_universe_specs",
    "forward_watchlist_snapshots",
    "strategy_drafts",
    "strategy_lifecycle_states",
    "research_protocol_snapshots",
    "oos_evaluation_ledgers",
    "immutable_backtest_reports",
    "prototype_gate_results_v2",
    "human_promotion_confirmations",
    "human_confirmation_consumptions",
    "strategy_promotions",
)


class StrategyDB:
    def __init__(self, db_path: str = "data/strategy.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()

    def close(self) -> None:
        self.conn.close()

    def _create_tables(self) -> None:
        cursor = self.conn.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS strategy_template_definitions (
                template_id TEXT NOT NULL,
                version TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                template_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (template_id, version)
            );

            CREATE TABLE IF NOT EXISTS backtest_universe_specs (
                universe_spec_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS forward_watchlist_snapshots (
                watchlist_snapshot_id TEXT PRIMARY KEY,
                theme_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS strategy_drafts (
                strategy_revision_id TEXT PRIMARY KEY,
                theme_id TEXT NOT NULL,
                hypothesis_id TEXT NOT NULL,
                backtest_universe_spec_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (backtest_universe_spec_id)
                    REFERENCES backtest_universe_specs(universe_spec_id)
            );

            CREATE TABLE IF NOT EXISTS strategy_lifecycle_states (
                lifecycle_state_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                state_version INTEGER NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('draft', 'prototype_passed')),
                source_record_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                UNIQUE (strategy_revision_id, state_version),
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS
                uq_strategy_one_prototype_passed
            ON strategy_lifecycle_states(strategy_revision_id)
            WHERE state = 'prototype_passed';

            CREATE TABLE IF NOT EXISTS research_protocol_snapshots (
                protocol_snapshot_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                strategy_config_hash TEXT NOT NULL,
                data_snapshot_hash TEXT NOT NULL,
                gate_criteria_hash TEXT NOT NULL,
                frozen_at TEXT NOT NULL,
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id)
            );

            CREATE TABLE IF NOT EXISTS oos_evaluation_ledgers (
                ledger_snapshot_id TEXT PRIMARY KEY,
                theme_id TEXT NOT NULL,
                ledger_version INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                UNIQUE (theme_id, ledger_version)
            );

            CREATE TABLE IF NOT EXISTS immutable_backtest_reports (
                report_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                protocol_snapshot_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                report_hash TEXT NOT NULL UNIQUE,
                integrity_status TEXT NOT NULL CHECK (integrity_status IN ('valid', 'invalid')),
                generated_at TEXT NOT NULL,
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id),
                FOREIGN KEY (protocol_snapshot_id)
                    REFERENCES research_protocol_snapshots(protocol_snapshot_id)
            );

            CREATE TABLE IF NOT EXISTS prototype_gate_results_v2 (
                gate_result_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                report_id TEXT NOT NULL,
                protocol_snapshot_id TEXT NOT NULL,
                verdict TEXT NOT NULL CHECK (
                    verdict IN (
                        'rejected',
                        'needs_review',
                        'candidate_for_prototype_passed'
                    )
                ),
                payload_json TEXT NOT NULL,
                gate_result_hash TEXT NOT NULL UNIQUE,
                generated_at TEXT NOT NULL,
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id),
                FOREIGN KEY (report_id)
                    REFERENCES immutable_backtest_reports(report_id),
                FOREIGN KEY (protocol_snapshot_id)
                    REFERENCES research_protocol_snapshots(protocol_snapshot_id)
            );

            CREATE TABLE IF NOT EXISTS human_promotion_confirmations (
                human_confirmation_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                gate_result_id TEXT NOT NULL,
                decision TEXT NOT NULL CHECK (decision IN ('approve', 'reject')),
                payload_json TEXT NOT NULL,
                confirmed_at TEXT NOT NULL,
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id),
                FOREIGN KEY (gate_result_id)
                    REFERENCES prototype_gate_results_v2(gate_result_id)
            );

            CREATE TABLE IF NOT EXISTS strategy_promotions (
                promotion_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL UNIQUE,
                gate_result_id TEXT NOT NULL,
                report_id TEXT NOT NULL,
                protocol_snapshot_id TEXT NOT NULL,
                human_confirmation_id TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                promoted_at TEXT NOT NULL,
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id),
                FOREIGN KEY (gate_result_id)
                    REFERENCES prototype_gate_results_v2(gate_result_id),
                FOREIGN KEY (report_id)
                    REFERENCES immutable_backtest_reports(report_id),
                FOREIGN KEY (protocol_snapshot_id)
                    REFERENCES research_protocol_snapshots(protocol_snapshot_id),
                FOREIGN KEY (human_confirmation_id)
                    REFERENCES human_promotion_confirmations(human_confirmation_id)
            );

            CREATE TABLE IF NOT EXISTS human_confirmation_consumptions (
                consumption_id TEXT PRIMARY KEY,
                human_confirmation_id TEXT NOT NULL UNIQUE,
                strategy_revision_id TEXT NOT NULL,
                gate_result_id TEXT NOT NULL,
                promotion_id TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                consumed_at TEXT NOT NULL,
                FOREIGN KEY (human_confirmation_id)
                    REFERENCES human_promotion_confirmations(human_confirmation_id),
                FOREIGN KEY (promotion_id)
                    REFERENCES strategy_promotions(promotion_id)
            );

            CREATE TRIGGER IF NOT EXISTS
                guard_prototype_passed_lifecycle_insert
            BEFORE INSERT ON strategy_lifecycle_states
            WHEN NEW.state = 'prototype_passed'
            BEGIN
                SELECT CASE WHEN NOT EXISTS (
                    SELECT 1
                    FROM strategy_promotions p
                    JOIN human_confirmation_consumptions c
                      ON c.promotion_id = p.promotion_id
                    WHERE p.strategy_revision_id = NEW.strategy_revision_id
                      AND p.promotion_id = NEW.source_record_id
                ) THEN RAISE(
                    ABORT,
                    'prototype_passed requires promotion and consumed confirmation'
                ) END;
            END;
            """
        )
        for table_name in IMMUTABLE_TABLES:
            cursor.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS prevent_{table_name}_update
                BEFORE UPDATE ON {table_name}
                BEGIN
                    SELECT RAISE(ABORT, '{table_name} is append-only');
                END
                """
            )
            cursor.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS prevent_{table_name}_delete
                BEFORE DELETE ON {table_name}
                BEGIN
                    SELECT RAISE(ABORT, '{table_name} is append-only');
                END
                """
            )
        self.conn.commit()

    def list_table_names(self) -> set[str]:
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        return {row["name"] for row in rows}

    @staticmethod
    def _json(model) -> str:
        return model.model_dump_json()

    def store_strategy_template(self, item: StrategyTemplateDefinition) -> None:
        self.conn.execute(
            """
            INSERT INTO strategy_template_definitions
            (template_id, version, payload_json, template_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                item.template_id,
                item.version,
                self._json(item),
                item.template_hash,
                item.created_at.isoformat(),
            ),
        )
        self.conn.commit()

    def store_backtest_universe(self, item: BacktestUniverseSpec) -> None:
        self.conn.execute(
            """
            INSERT INTO backtest_universe_specs
            (universe_spec_id, payload_json, created_at)
            VALUES (?, ?, ?)
            """,
            (
                item.universe_spec_id,
                self._json(item),
                datetime.now().isoformat(),
            ),
        )
        self.conn.commit()

    def store_forward_watchlist(self, item: ForwardWatchlistSnapshot) -> None:
        self.conn.execute(
            """
            INSERT INTO forward_watchlist_snapshots
            (watchlist_snapshot_id, theme_id, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                item.watchlist_snapshot_id,
                item.theme_id,
                self._json(item),
                item.created_at.isoformat(),
            ),
        )
        self.conn.commit()

    def create_strategy_draft(
        self,
        draft: StrategyDraft,
        initial_state: StrategyLifecycleState,
    ) -> None:
        if initial_state.strategy_revision_id != draft.strategy_revision_id:
            raise ValueError("initial lifecycle state must match draft")
        if initial_state.state != "draft" or initial_state.state_version != 1:
            raise ValueError("initial lifecycle state must be draft version 1")
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute(
                """
                INSERT INTO strategy_drafts
                (strategy_revision_id, theme_id, hypothesis_id,
                 backtest_universe_spec_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    draft.strategy_revision_id,
                    draft.theme_id,
                    draft.hypothesis_id,
                    draft.backtest_universe_spec_id,
                    self._json(draft),
                    draft.created_at.isoformat(),
                ),
            )
            self.conn.execute(
                """
                INSERT INTO strategy_lifecycle_states
                (lifecycle_state_id, strategy_revision_id, state_version,
                 state, source_record_id, payload_json, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    initial_state.lifecycle_state_id,
                    initial_state.strategy_revision_id,
                    initial_state.state_version,
                    initial_state.state,
                    initial_state.source_record_id,
                    self._json(initial_state),
                    initial_state.recorded_at.isoformat(),
                ),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def store_protocol_snapshot(self, item: ResearchProtocolSnapshot) -> None:
        self.conn.execute(
            """
            INSERT INTO research_protocol_snapshots
            (protocol_snapshot_id, strategy_revision_id, payload_json,
             strategy_config_hash, data_snapshot_hash, gate_criteria_hash, frozen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.protocol_snapshot_id,
                item.strategy_revision_id,
                self._json(item),
                item.strategy_config_hash,
                item.data_snapshot_hash,
                item.gate_criteria_hash,
                item.frozen_at.isoformat(),
            ),
        )
        self.conn.commit()

    def store_oos_ledger(self, item: OOSEvaluationLedger) -> None:
        self.conn.execute(
            """
            INSERT INTO oos_evaluation_ledgers
            (ledger_snapshot_id, theme_id, ledger_version, payload_json, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                item.ledger_snapshot_id,
                item.theme_id,
                item.ledger_version,
                self._json(item),
                item.recorded_at.isoformat(),
            ),
        )
        self.conn.commit()

    def store_backtest_report(self, item: ImmutableBacktestReport) -> None:
        self.conn.execute(
            """
            INSERT INTO immutable_backtest_reports
            (report_id, strategy_revision_id, protocol_snapshot_id, payload_json,
             report_hash, integrity_status, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.report_id,
                item.strategy_revision_id,
                item.protocol_snapshot_id,
                self._json(item),
                item.report_hash,
                item.integrity_status,
                item.generated_at.isoformat(),
            ),
        )
        self.conn.commit()

    def store_gate_result(self, item: PrototypeGateResultV2) -> None:
        self.conn.execute(
            """
            INSERT INTO prototype_gate_results_v2
            (gate_result_id, strategy_revision_id, report_id,
             protocol_snapshot_id, verdict, payload_json,
             gate_result_hash, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.gate_result_id,
                item.strategy_revision_id,
                item.report_id,
                item.protocol_snapshot_id,
                item.verdict,
                self._json(item),
                item.gate_result_hash,
                item.generated_at.isoformat(),
            ),
        )
        self.conn.commit()

    def store_human_confirmation(self, item: HumanPromotionConfirmation) -> None:
        self.conn.execute(
            """
            INSERT INTO human_promotion_confirmations
            (human_confirmation_id, strategy_revision_id, gate_result_id,
             decision, payload_json, confirmed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item.human_confirmation_id,
                item.strategy_revision_id,
                item.gate_result_id,
                item.decision,
                self._json(item),
                item.confirmed_at.isoformat(),
            ),
        )
        self.conn.commit()

    @staticmethod
    def _load(model_type, row):
        if row is None:
            return None
        return model_type.model_validate_json(row["payload_json"])

    def get_strategy_draft(self, strategy_revision_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM strategy_drafts
            WHERE strategy_revision_id = ?
            """,
            (strategy_revision_id,),
        ).fetchone()
        return self._load(StrategyDraft, row)

    def get_protocol_snapshot(self, protocol_snapshot_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM research_protocol_snapshots
            WHERE protocol_snapshot_id = ?
            """,
            (protocol_snapshot_id,),
        ).fetchone()
        return self._load(ResearchProtocolSnapshot, row)

    def get_backtest_report(self, report_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM immutable_backtest_reports
            WHERE report_id = ?
            """,
            (report_id,),
        ).fetchone()
        return self._load(ImmutableBacktestReport, row)

    def get_gate_result(self, gate_result_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM prototype_gate_results_v2
            WHERE gate_result_id = ?
            """,
            (gate_result_id,),
        ).fetchone()
        return self._load(PrototypeGateResultV2, row)

    def get_human_confirmation(self, human_confirmation_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM human_promotion_confirmations
            WHERE human_confirmation_id = ?
            """,
            (human_confirmation_id,),
        ).fetchone()
        return self._load(HumanPromotionConfirmation, row)

    def get_latest_lifecycle_state(self, strategy_revision_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json
            FROM strategy_lifecycle_states
            WHERE strategy_revision_id = ?
            ORDER BY state_version DESC
            LIMIT 1
            """,
            (strategy_revision_id,),
        ).fetchone()
        return self._load(StrategyLifecycleState, row)

    def _get_promotion_by_strategy(self, strategy_revision_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM strategy_promotions
            WHERE strategy_revision_id = ?
            """,
            (strategy_revision_id,),
        ).fetchone()
        return self._load(StrategyPromotionRecord, row)

    def _confirmation_is_consumed(self, human_confirmation_id: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1 FROM human_confirmation_consumptions
            WHERE human_confirmation_id = ?
            """,
            (human_confirmation_id,),
        ).fetchone()
        return row is not None

    def _commit_validated_promotion(
        self,
        promotion: StrategyPromotionRecord,
        consumption: HumanConfirmationConsumption,
        lifecycle_state: StrategyLifecycleState,
    ) -> None:
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute(
                """
                INSERT INTO strategy_promotions
                (promotion_id, strategy_revision_id, gate_result_id, report_id,
                 protocol_snapshot_id, human_confirmation_id, payload_json,
                 promoted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    promotion.promotion_id,
                    promotion.strategy_revision_id,
                    promotion.gate_result_id,
                    promotion.report_id,
                    promotion.protocol_snapshot_id,
                    promotion.human_confirmation_id,
                    self._json(promotion),
                    promotion.promoted_at.isoformat(),
                ),
            )
            self.conn.execute(
                """
                INSERT INTO human_confirmation_consumptions
                (consumption_id, human_confirmation_id, strategy_revision_id,
                 gate_result_id, promotion_id, payload_json, consumed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    consumption.consumption_id,
                    consumption.human_confirmation_id,
                    consumption.strategy_revision_id,
                    consumption.gate_result_id,
                    consumption.promotion_id,
                    self._json(consumption),
                    consumption.consumed_at.isoformat(),
                ),
            )
            self.conn.execute(
                """
                INSERT INTO strategy_lifecycle_states
                (lifecycle_state_id, strategy_revision_id, state_version,
                 state, source_record_id, payload_json, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lifecycle_state.lifecycle_state_id,
                    lifecycle_state.strategy_revision_id,
                    lifecycle_state.state_version,
                    lifecycle_state.state,
                    lifecycle_state.source_record_id,
                    self._json(lifecycle_state),
                    lifecycle_state.recorded_at.isoformat(),
                ),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
