"""
Research database operations.

Provides SQLite persistence for:
- research_themes
- research_candidates
- serenity_outputs
- evidence_outputs
- research_actions (proposed and applied)
- conversation_messages
- confirmed_candidates

Key behaviors:
- create/list/get theme
- add/list candidates by theme
- store latest Serenity output per theme
- store Evidence output per candidate
- store proposed and applied actions
- store conversation messages linked to proposed actions
- confirm/reject candidate
- reopen candidate to evidence with reason
- reopen theme to Serenity with reason
- list confirmed candidates by theme
- increment theme board_version on successful state mutation
"""

import json
import sqlite3
from datetime import date, datetime
from typing import Optional
from contracts.research import (
    ThemeInput,
    CandidateStock,
    SerenityOutput,
    EvidenceOutput,
    ProposedAction,
    ConversationMessage,
    AppliedAction,
    ConfirmedCandidate,
    AgentHarnessConfig,
    EvidenceItem,
    ConflictItem,
)
from contracts.approval_card import ApprovalCard


class ResearchDB:
    """SQLite database for research module."""

    def __init__(self, db_path_or_conn="data/research.db", *, db_path=None):
        """Initialize database connection and create tables.

        Args:
            db_path_or_conn: Either a path string (default: "data/research.db")
                            or an existing sqlite3.Connection
        """
        if db_path is not None:
            if db_path_or_conn != "data/research.db":
                raise TypeError("Specify either db_path_or_conn or db_path, not both")
            db_path_or_conn = db_path
        if isinstance(db_path_or_conn, str):
            self.conn = sqlite3.connect(db_path_or_conn, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self._owns_connection = True
        else:
            # Reuse existing connection
            self.conn = db_path_or_conn
            self._owns_connection = False
        self._create_tables()

    def _create_tables(self):
        """Create all research tables."""
        cursor = self.conn.cursor()

        # research_themes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_themes (
                theme_id TEXT PRIMARY KEY,
                theme_name TEXT NOT NULL,
                background TEXT NOT NULL,
                source_type TEXT NOT NULL,
                research_mode TEXT NOT NULL DEFAULT 'standard',
                urgency TEXT NOT NULL DEFAULT 'normal',
                notes TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                board_version INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        # V2 (2026-07-10): user-proposed industry-chain hypothesis, pending-only.
        self._ensure_column(
            "research_themes", "user_industry_chain_hypothesis", "TEXT"
        )
        # V2 (2026-07-10): research synthesis result + explicit decision trust boundary.
        self._ensure_column("research_themes", "research_output", "TEXT")
        self._ensure_column("research_themes", "approval_decision", "TEXT")
        self._ensure_column("research_themes", "confirmed_by", "TEXT")
        self._ensure_column("research_themes", "confirmed_at", "TEXT")
        self._ensure_column("research_themes", "decision_loop_id", "TEXT")

        # research_candidates
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_candidates (
                candidate_id TEXT PRIMARY KEY,
                theme_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                company_name TEXT,
                verification_id TEXT,
                source_type TEXT NOT NULL,
                chain_layer TEXT,
                match_reason TEXT NOT NULL,
                match_confidence TEXT DEFAULT 'unknown',
                status TEXT NOT NULL DEFAULT 'raw',
                hard_filter_flags TEXT DEFAULT '[]',
                override_reason TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (theme_id) REFERENCES research_themes(theme_id),
                FOREIGN KEY (verification_id) REFERENCES ticker_verification_records(verification_id)
            )
        """)
        self._ensure_column("research_candidates", "verification_id", "TEXT")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_candidates_theme ON research_candidates(theme_id)")

        # serenity_outputs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS serenity_outputs (
                theme_id TEXT PRIMARY KEY,
                demand_driver TEXT NOT NULL,
                value_chain_layers TEXT NOT NULL,
                suspected_bottleneck_layers TEXT NOT NULL,
                candidate_pool_raw TEXT NOT NULL,
                candidate_shortlist TEXT NOT NULL,
                hypothesis_draft TEXT NOT NULL,
                evidence_gaps TEXT NOT NULL,
                harness TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (theme_id) REFERENCES research_themes(theme_id)
            )
        """)

        # evidence_outputs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS evidence_outputs (
                candidate_id TEXT PRIMARY KEY,
                kill_criteria_hash TEXT NOT NULL,
                evidence_level TEXT NOT NULL,
                supporting_evidence TEXT DEFAULT '[]',
                falsifying_evidence TEXT DEFAULT '[]',
                conflict_items TEXT DEFAULT '[]',
                blocking_issues TEXT DEFAULT '[]',
                evidence_gaps TEXT DEFAULT '[]',
                tool_trace TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                FOREIGN KEY (candidate_id) REFERENCES research_candidates(candidate_id)
            )
        """)

        # research_actions (proposed)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_actions_proposed (
                action_id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                target_id TEXT NOT NULL,
                args TEXT NOT NULL,
                rationale TEXT NOT NULL,
                proposed_by TEXT NOT NULL,
                proposed_at TEXT NOT NULL,
                expires_at TEXT,
                board_version INTEGER
            )
        """)

        # research_actions (applied)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_actions_applied (
                action_id TEXT PRIMARY KEY,
                proposed_action TEXT NOT NULL,
                applied INTEGER NOT NULL,
                actor_reason TEXT,
                rejection_reason TEXT,
                applied_by TEXT,
                applied_at TEXT NOT NULL
            )
        """)

        # conversation_messages
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_messages (
                message_id TEXT PRIMARY KEY,
                theme_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                linked_proposed_action_ids TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                FOREIGN KEY (theme_id) REFERENCES research_themes(theme_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_theme ON conversation_messages(theme_id)")

        # confirmed_candidates
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS confirmed_candidates (
                confirmed_id TEXT PRIMARY KEY,
                theme_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL,
                source_serenity_run_id TEXT,
                source_evidence_run_id TEXT,
                symbol TEXT NOT NULL,
                company_name TEXT NOT NULL,
                verification_id TEXT,
                chain_layer TEXT,
                thesis_snapshot TEXT NOT NULL,
                invalidation_rules TEXT NOT NULL,
                price_snapshot TEXT NOT NULL,
                benchmark_snapshot TEXT NOT NULL,
                confirmation_reason TEXT NOT NULL,
                evidence_level TEXT NOT NULL,
                evidence_snapshot_ids TEXT DEFAULT '[]',
                primary_evidence_snapshot_id TEXT,
                confirmed_by TEXT NOT NULL,
                confirmed_at TEXT NOT NULL,
                pool_snapshot_date TEXT NOT NULL,
                forward_only INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (theme_id) REFERENCES research_themes(theme_id),
                FOREIGN KEY (candidate_id) REFERENCES research_candidates(candidate_id),
                FOREIGN KEY (verification_id) REFERENCES ticker_verification_records(verification_id)
            )
        """)
        self._ensure_column("confirmed_candidates", "verification_id", "TEXT")
        self._ensure_column("confirmed_candidates", "evidence_snapshot_ids", "TEXT DEFAULT '[]'")
        self._ensure_column("confirmed_candidates", "primary_evidence_snapshot_id", "TEXT")
        self._ensure_column("confirmed_candidates", "approval_card_id", "TEXT")

        # evidence_snapshots (immutable, append-only)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS evidence_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                verification_id TEXT,
                snapshot_date TEXT,
                symbol TEXT NOT NULL,
                evidence_output TEXT NOT NULL,
                packet_input_hash TEXT DEFAULT '',
                tool_result_hash TEXT DEFAULT '',
                packet_data TEXT DEFAULT '',
                audit_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (candidate_id) REFERENCES research_candidates(candidate_id)
            )
        """)
        self._ensure_column("evidence_snapshots", "verification_id", "TEXT")
        self._ensure_column("evidence_snapshots", "snapshot_date", "TEXT")
        self._ensure_column("evidence_snapshots", "packet_input_hash", "TEXT DEFAULT ''")
        self._ensure_column("evidence_snapshots", "tool_result_hash", "TEXT DEFAULT ''")
        self._ensure_column("evidence_snapshots", "packet_data", "TEXT DEFAULT ''")
        self._ensure_column("evidence_snapshots", "audit_id", "TEXT")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_snapshots_candidate ON evidence_snapshots(candidate_id)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_confirmed_theme ON confirmed_candidates(theme_id)")

        # ticker_verification_records
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ticker_verification_records (
                verification_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                company_name TEXT NOT NULL,
                exchange TEXT NOT NULL,
                status TEXT NOT NULL,
                confidence TEXT NOT NULL,
                source TEXT NOT NULL,
                notes TEXT NOT NULL,
                verified_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_verification_symbol ON ticker_verification_records(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_verification_expires ON ticker_verification_records(expires_at)")

        # friend_stock_flows (flow state persistence)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friend_stock_flows (
                flow_id TEXT PRIMARY KEY,
                raw_company_input TEXT,
                raw_code_input TEXT,
                source_note TEXT,
                ticker_verification_result TEXT,
                research_output TEXT,
                status TEXT NOT NULL DEFAULT 'waiting',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Schema migration: add status column to friend_stock_flows if not exists
        self._ensure_column("friend_stock_flows", "status", "TEXT NOT NULL DEFAULT 'waiting'")

        self.conn.commit()

    def _ensure_column(self, table_name: str, column_name: str, column_definition: str):
        """Add a column for existing SQLite databases when schema evolves."""
        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing_columns = {row["name"] for row in cursor.fetchall()}
        if column_name not in existing_columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")

    def create_theme(self, theme: ThemeInput, *, commit: bool = True):
        """Create a new research theme."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO research_themes 
            (theme_id, theme_name, background, source_type, research_mode, urgency, notes, status, board_version, user_industry_chain_hypothesis, research_output, approval_decision, confirmed_by, confirmed_at, decision_loop_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                theme.theme_id,
                theme.theme_name,
                theme.background,
                theme.source_type,
                theme.research_mode,
                theme.urgency,
                theme.notes,
                theme.status,
                theme.board_version,
                json.dumps(theme.user_industry_chain_hypothesis) if theme.user_industry_chain_hypothesis else None,
                json.dumps(theme.research_output) if theme.research_output else None,
                theme.approval_decision,
                theme.confirmed_by,
                theme.confirmed_at.isoformat() if theme.confirmed_at else None,
                theme.decision_loop_id,
                theme.created_at.isoformat(),
                theme.updated_at.isoformat(),
            ),
        )
        if commit:
            self.conn.commit()

    def get_theme(self, theme_id: str) -> Optional[ThemeInput]:
        """Get a theme by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM research_themes WHERE theme_id = ?", (theme_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return ThemeInput(
            theme_id=row["theme_id"],
            theme_name=row["theme_name"],
            background=row["background"],
            source_type=row["source_type"],
            research_mode=row["research_mode"],
            urgency=row["urgency"],
            notes=row["notes"],
            status=row["status"],
            board_version=row["board_version"],
            user_industry_chain_hypothesis=(
                json.loads(row["user_industry_chain_hypothesis"])
                if row["user_industry_chain_hypothesis"] else None
            ),
            research_output=(
                json.loads(row["research_output"])
                if row["research_output"] else None
            ),
            approval_decision=row["approval_decision"],
            confirmed_by=row["confirmed_by"],
            confirmed_at=(
                datetime.fromisoformat(row["confirmed_at"])
                if row["confirmed_at"] else None
            ),
            decision_loop_id=row["decision_loop_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def list_themes(self) -> list[ThemeInput]:
        """List all themes."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM research_themes ORDER BY created_at DESC")
        return [
            ThemeInput(
                theme_id=row["theme_id"],
                theme_name=row["theme_name"],
                background=row["background"],
                source_type=row["source_type"],
                research_mode=row["research_mode"],
                urgency=row["urgency"],
                notes=row["notes"],
                status=row["status"],
                board_version=row["board_version"],
                user_industry_chain_hypothesis=(
                    json.loads(row["user_industry_chain_hypothesis"])
                    if row["user_industry_chain_hypothesis"] else None
                ),
                research_output=(
                    json.loads(row["research_output"])
                    if row["research_output"] else None
                ),
                approval_decision=row["approval_decision"],
                confirmed_by=row["confirmed_by"],
                confirmed_at=(
                    datetime.fromisoformat(row["confirmed_at"])
                    if row["confirmed_at"] else None
                ),
                decision_loop_id=row["decision_loop_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in cursor.fetchall()
        ]

    def store_research_output(
        self, theme_id: str, research_output: dict, *, commit: bool = True
    ) -> None:
        """Persist real Serenity+Tushare synthesis result on the ResearchCase."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE research_themes SET research_output = ?, updated_at = ? WHERE theme_id = ?",
            (json.dumps(research_output), datetime.now().isoformat(), theme_id),
        )
        if commit:
            self.conn.commit()

    def store_hypothesis(self, theme_id: str, hypothesis: dict) -> None:
        """Persist user-proposed industry-chain hypothesis VERBATIM as pending-only."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE research_themes SET user_industry_chain_hypothesis = ?, updated_at = ? "
            "WHERE theme_id = ?",
            (json.dumps(hypothesis), datetime.now().isoformat(), theme_id),
        )
        self.conn.commit()

    def record_decision(
        self,
        theme_id: str,
        decision: str,
        confirmed_by: str,
        decision_loop_id: str | None,
    ) -> None:
        """Persist the explicit user decision (continue/observe/stop) + approver.

        Only a real, explicit decision reaches here. Default/LLM-text/stub/
        data-error/LLM-error never count as approval (enforced by the caller).
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE research_themes SET approval_decision = ?, confirmed_by = ?, "
            "confirmed_at = ?, decision_loop_id = ?, updated_at = ? WHERE theme_id = ?",
            (
                decision,
                confirmed_by,
                datetime.now().isoformat(),
                decision_loop_id,
                datetime.now().isoformat(),
                theme_id,
            ),
        )
        self.conn.commit()

    def add_candidate(self, candidate: CandidateStock):
        """Add a candidate to a theme."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO research_candidates
            (candidate_id, theme_id, symbol, company_name, verification_id, source_type, chain_layer, match_reason, match_confidence, status, hard_filter_flags, override_reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate.candidate_id,
                candidate.theme_id,
                candidate.symbol,
                candidate.company_name,
                candidate.verification_id,
                candidate.source_type,
                candidate.chain_layer,
                candidate.match_reason,
                candidate.match_confidence,
                candidate.status,
                json.dumps(candidate.hard_filter_flags),
                candidate.override_reason,
                candidate.created_at.isoformat(),
            ),
        )
        self.conn.commit()

    def list_candidates(self, theme_id: str) -> list[CandidateStock]:
        """List all candidates for a theme."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM research_candidates WHERE theme_id = ?", (theme_id,))
        return [
            CandidateStock(
                candidate_id=row["candidate_id"],
                theme_id=row["theme_id"],
                symbol=row["symbol"],
                company_name=row["company_name"],
                verification_id=row["verification_id"],
                source_type=row["source_type"],
                chain_layer=row["chain_layer"],
                match_reason=row["match_reason"],
                match_confidence=row["match_confidence"],
                status=row["status"],
                hard_filter_flags=json.loads(row["hard_filter_flags"]),
                override_reason=row["override_reason"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in cursor.fetchall()
        ]

    def get_candidate(self, candidate_id: str) -> Optional[CandidateStock]:
        """Get a candidate by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM research_candidates WHERE candidate_id = ?", (candidate_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return CandidateStock(
            candidate_id=row["candidate_id"],
            theme_id=row["theme_id"],
            symbol=row["symbol"],
            company_name=row["company_name"],
            verification_id=row["verification_id"],
            source_type=row["source_type"],
            chain_layer=row["chain_layer"],
            match_reason=row["match_reason"],
            match_confidence=row["match_confidence"],
            status=row["status"],
            hard_filter_flags=json.loads(row["hard_filter_flags"]),
            override_reason=row["override_reason"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def confirm_candidate(
        self,
        candidate_id: str,
        confirmation_reason: str,
        evidence_level: str,
        confirmed_by: str,
        pool_snapshot_date: date,
        thesis_snapshot: str,
        invalidation_rules: list[dict],
        price_snapshot: dict,
        benchmark_snapshot: dict,
        approval_card_id: Optional[str] = None,
        override_reason: Optional[str] = None,
        source_serenity_run_id: Optional[str] = None,
        source_evidence_run_id: Optional[str] = None,
        evidence_snapshot_ids: Optional[list[str]] = None,
        primary_evidence_snapshot_id: Optional[str] = None,
    ) -> ConfirmedCandidate:
        """Atomically bind a real continued Approval Card to a confirmation."""
        if not approval_card_id or not approval_card_id.strip():
            raise ValueError("approval_provenance_required")
        if self.conn.in_transaction:
            raise RuntimeError("confirmation_transaction_already_active")

        cursor = self.conn.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            candidate = self.get_candidate(candidate_id)
            if not candidate:
                raise ValueError(f"Candidate {candidate_id} not found")
            if candidate.status == "blocked" and candidate.hard_filter_flags and not override_reason:
                raise ValueError("Blocked candidate requires override reason")

            card_row = cursor.execute(
                """SELECT session_id, card_data
                FROM agent_approval_cards WHERE approval_card_id = ?""",
                (approval_card_id,),
            ).fetchone()
            if not card_row:
                raise ValueError("approval_card_unavailable")

            # Invalid JSON or invalid contract is an invariant failure, not typed unavailable.
            card = ApprovalCard.model_validate_json(card_row["card_data"])
            if card.approval_card_id != approval_card_id:
                raise RuntimeError("approval_card_primary_key_invariant")
            if card.workflow_id != card_row["session_id"]:
                raise ValueError("approval_card_session_mismatch")
            if card.decision != "continue":
                raise ValueError("approval_card_not_continued")

            has_session_research_case = cursor.execute(
                """SELECT 1 FROM agent_artifact_refs
                WHERE session_id = ? AND artifact_type = 'research_case'
                  AND artifact_id = ? LIMIT 1""",
                (card_row["session_id"], candidate.theme_id),
            ).fetchone()
            if not has_session_research_case or candidate.theme_id not in card.artifact_ids:
                raise ValueError("approval_card_research_case_binding_mismatch")

            now = datetime.now()
            confirmed = ConfirmedCandidate(
                confirmed_id=f"confirmed_{candidate_id}_{now.timestamp()}",
                theme_id=candidate.theme_id,
                candidate_id=candidate_id,
                source_serenity_run_id=source_serenity_run_id,
                source_evidence_run_id=source_evidence_run_id,
                symbol=candidate.symbol,
                company_name=candidate.company_name or "",
                verification_id=candidate.verification_id,
                chain_layer=candidate.chain_layer,
                thesis_snapshot=thesis_snapshot,
                invalidation_rules=invalidation_rules,
                price_snapshot=price_snapshot,
                benchmark_snapshot=benchmark_snapshot,
                confirmation_reason=confirmation_reason,
                evidence_level=evidence_level,
                evidence_snapshot_ids=evidence_snapshot_ids or [],
                primary_evidence_snapshot_id=primary_evidence_snapshot_id,
                confirmed_by=confirmed_by,
                confirmed_at=now,
                pool_snapshot_date=pool_snapshot_date,
                approval_card_id=approval_card_id,
            )

            cursor.execute(
                """INSERT INTO confirmed_candidates (
                    confirmed_id, theme_id, candidate_id, source_serenity_run_id,
                    source_evidence_run_id, symbol, company_name, verification_id,
                    chain_layer, thesis_snapshot, invalidation_rules, price_snapshot,
                    benchmark_snapshot, confirmation_reason, evidence_level,
                    evidence_snapshot_ids, primary_evidence_snapshot_id, confirmed_by,
                    confirmed_at, pool_snapshot_date, forward_only, approval_card_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (
                    confirmed.confirmed_id,
                    confirmed.theme_id,
                    confirmed.candidate_id,
                    confirmed.source_serenity_run_id,
                    confirmed.source_evidence_run_id,
                    confirmed.symbol,
                    confirmed.company_name,
                    confirmed.verification_id,
                    confirmed.chain_layer,
                    confirmed.thesis_snapshot,
                    json.dumps(confirmed.invalidation_rules),
                    json.dumps(confirmed.price_snapshot),
                    json.dumps(confirmed.benchmark_snapshot),
                    confirmed.confirmation_reason,
                    confirmed.evidence_level,
                    json.dumps(confirmed.evidence_snapshot_ids),
                    confirmed.primary_evidence_snapshot_id,
                    confirmed.confirmed_by,
                    confirmed.confirmed_at.isoformat(),
                    confirmed.pool_snapshot_date.isoformat(),
                    confirmed.approval_card_id,
                ),
            )
            updated_candidate = cursor.execute(
                "UPDATE research_candidates SET status = 'confirmed' WHERE candidate_id = ?",
                (candidate_id,),
            )
            if updated_candidate.rowcount != 1:
                raise RuntimeError("candidate_status_update_invariant")
            updated_theme = cursor.execute(
                """UPDATE research_themes
                SET board_version = board_version + 1, updated_at = ?
                WHERE theme_id = ?""",
                (now.isoformat(), candidate.theme_id),
            )
            if updated_theme.rowcount != 1:
                raise RuntimeError("theme_board_version_update_invariant")
            self.conn.commit()
            return confirmed
        except Exception:
            self.conn.rollback()
            raise

    def list_confirmed_candidates(self, theme_id: str) -> list[ConfirmedCandidate]:
        """List all confirmed candidates for a theme."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM confirmed_candidates WHERE theme_id = ?", (theme_id,))
        return [
            ConfirmedCandidate(
                confirmed_id=row["confirmed_id"],
                theme_id=row["theme_id"],
                candidate_id=row["candidate_id"],
                source_serenity_run_id=row["source_serenity_run_id"],
                source_evidence_run_id=row["source_evidence_run_id"],
                symbol=row["symbol"],
                company_name=row["company_name"],
                verification_id=row["verification_id"],
                chain_layer=row["chain_layer"],
                thesis_snapshot=row["thesis_snapshot"],
                invalidation_rules=json.loads(row["invalidation_rules"]),
                price_snapshot=json.loads(row["price_snapshot"]),
                benchmark_snapshot=json.loads(row["benchmark_snapshot"]),
                confirmation_reason=row["confirmation_reason"],
                evidence_level=row["evidence_level"],
                evidence_snapshot_ids=json.loads(row["evidence_snapshot_ids"]),
                primary_evidence_snapshot_id=row["primary_evidence_snapshot_id"],
                confirmed_by=row["confirmed_by"],
                confirmed_at=datetime.fromisoformat(row["confirmed_at"]),
                pool_snapshot_date=date.fromisoformat(row["pool_snapshot_date"]),
                approval_card_id=(
                    row["approval_card_id"] if "approval_card_id" in row.keys() else None
                ),
            )
            for row in cursor.fetchall()
        ]

    def get_confirmed_candidate(self, confirmed_id: str) -> Optional[ConfirmedCandidate]:
        """Get a confirmed candidate by pool_id (confirmed_id)."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM confirmed_candidates WHERE confirmed_id = ?", (confirmed_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return ConfirmedCandidate(
            confirmed_id=row["confirmed_id"],
            theme_id=row["theme_id"],
            candidate_id=row["candidate_id"],
            source_serenity_run_id=row["source_serenity_run_id"],
            source_evidence_run_id=row["source_evidence_run_id"],
            symbol=row["symbol"],
            company_name=row["company_name"],
            verification_id=row["verification_id"],
            chain_layer=row["chain_layer"],
            thesis_snapshot=row["thesis_snapshot"],
            invalidation_rules=json.loads(row["invalidation_rules"]),
            price_snapshot=json.loads(row["price_snapshot"]),
            benchmark_snapshot=json.loads(row["benchmark_snapshot"]),
            confirmation_reason=row["confirmation_reason"],
            evidence_level=row["evidence_level"],
            evidence_snapshot_ids=json.loads(row["evidence_snapshot_ids"]),
            primary_evidence_snapshot_id=row["primary_evidence_snapshot_id"],
            confirmed_by=row["confirmed_by"],
            confirmed_at=datetime.fromisoformat(row["confirmed_at"]),
            pool_snapshot_date=date.fromisoformat(row["pool_snapshot_date"]),
            approval_card_id=(
                row["approval_card_id"] if "approval_card_id" in row.keys() else None
            ),
        )

    def store_conversation_message(self, message: ConversationMessage):
        """Store a conversation message."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO conversation_messages
            (message_id, theme_id, role, content, linked_proposed_action_ids, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                message.message_id,
                message.theme_id,
                message.role,
                message.content,
                json.dumps(message.linked_proposed_action_ids),
                message.created_at.isoformat(),
            ),
        )
        self.conn.commit()

    def get_conversation_message(self, message_id: str) -> Optional[ConversationMessage]:
        """Get a conversation message by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM conversation_messages WHERE message_id = ?", (message_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return ConversationMessage(
            message_id=row["message_id"],
            theme_id=row["theme_id"],
            role=row["role"],
            content=row["content"],
            linked_proposed_action_ids=json.loads(row["linked_proposed_action_ids"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def store_proposed_action(self, action: ProposedAction):
        """Store a proposed action."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO research_actions_proposed
            (action_id, action, target_id, args, rationale, proposed_by, proposed_at, expires_at, board_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action.action_id,
                action.action,
                action.target_id,
                json.dumps(action.args),
                action.rationale,
                action.proposed_by,
                action.proposed_at.isoformat(),
                action.expires_at.isoformat() if action.expires_at else None,
                action.board_version,
            ),
        )
        self.conn.commit()

    def get_proposed_action(self, action_id: str) -> Optional[ProposedAction]:
        """Get a proposed action by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM research_actions_proposed WHERE action_id = ?", (action_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return ProposedAction(
            action_id=row["action_id"],
            action=row["action"],
            target_id=row["target_id"],
            args=json.loads(row["args"]),
            rationale=row["rationale"],
            proposed_by=row["proposed_by"],
            proposed_at=datetime.fromisoformat(row["proposed_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            board_version=row["board_version"],
        )

    def store_applied_action(self, applied: AppliedAction):
        """Store an applied or rejected action."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO research_actions_applied
            (action_id, proposed_action, applied, actor_reason, rejection_reason, applied_by, applied_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                applied.action_id,
                applied.proposed_action.model_dump_json(),
                1 if applied.applied else 0,
                applied.actor_reason,
                applied.rejection_reason,
                applied.applied_by,
                applied.applied_at.isoformat(),
            ),
        )
        self.conn.commit()

    def get_applied_action(self, action_id: str) -> Optional[AppliedAction]:
        """Get an applied action by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM research_actions_applied WHERE action_id = ?", (action_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return AppliedAction(
            action_id=row["action_id"],
            proposed_action=ProposedAction.model_validate_json(row["proposed_action"]),
            applied=bool(row["applied"]),
            actor_reason=row["actor_reason"],
            rejection_reason=row["rejection_reason"],
            applied_by=row["applied_by"],
            applied_at=datetime.fromisoformat(row["applied_at"]),
        )

    def increment_board_version(self, theme_id: str):
        """Increment theme board_version by 1."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE research_themes SET board_version = board_version + 1, updated_at = ? WHERE theme_id = ?",
            (datetime.now().isoformat(), theme_id),
        )
        self.conn.commit()

    def reopen_candidate_to_evidence(
        self, candidate_id: str, actor: str, reason: str, timestamp: datetime
    ) -> dict:
        """Reopen a candidate to evidence with audit trail."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE research_candidates SET status = 'needs_evidence' WHERE candidate_id = ?",
            (candidate_id,),
        )
        self.conn.commit()

        return {
            "candidate_id": candidate_id,
            "actor": actor,
            "reason": reason,
            "timestamp": timestamp.isoformat(),
        }

    def reopen_theme_to_serenity(self, theme_id: str, actor: str, reason: str, timestamp: datetime) -> dict:
        """Reopen a theme to Serenity with audit trail."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE research_themes SET status = 'serenity_done' WHERE theme_id = ?",
            (theme_id,),
        )
        self.conn.commit()

        return {
            "theme_id": theme_id,
            "actor": actor,
            "reason": reason,
            "timestamp": timestamp.isoformat(),
        }

    def close(self):
        """Close database connection."""
        self.conn.close()

    def list_pending_actions_by_theme(self, theme_id: str) -> list[ProposedAction]:
        """List pending proposed actions for a theme (not yet applied)."""
        cursor = self.conn.cursor()
        
        # Get all proposed actions for this theme or its candidates
        cursor.execute("""
            SELECT p.* FROM research_actions_proposed p
            WHERE p.action_id NOT IN (SELECT action_id FROM research_actions_applied)
            AND (p.target_id = ? OR p.target_id IN (
                SELECT candidate_id FROM research_candidates WHERE theme_id = ?
            ))
            ORDER BY p.proposed_at DESC
        """, (theme_id, theme_id))
        
        actions = []
        for row in cursor.fetchall():
            action = ProposedAction(
                action_id=row["action_id"],
                action=row["action"],
                target_id=row["target_id"],
                args=json.loads(row["args"]),
                rationale=row["rationale"],
                proposed_by=row["proposed_by"],
                proposed_at=datetime.fromisoformat(row["proposed_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
                board_version=row["board_version"],
            )
            actions.append(action)
        return actions

    def list_conversation_by_theme(self, theme_id: str) -> list[ConversationMessage]:
        """List conversation messages for a theme."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM conversation_messages WHERE theme_id = ? ORDER BY created_at ASC",
            (theme_id,)
        )
        return [
            ConversationMessage(
                message_id=row["message_id"],
                theme_id=row["theme_id"],
                role=row["role"],
                content=row["content"],
                linked_proposed_action_ids=json.loads(row["linked_proposed_action_ids"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in cursor.fetchall()
        ]

    def store_serenity_output(self, output: SerenityOutput):
        """Store Serenity analysis output."""
        cursor = self.conn.cursor()
        
        # Upsert: replace existing output for this theme
        cursor.execute("""
            INSERT OR REPLACE INTO serenity_outputs
            (theme_id, demand_driver, value_chain_layers, suspected_bottleneck_layers, 
             candidate_pool_raw, candidate_shortlist, hypothesis_draft, evidence_gaps, harness, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            output.theme_id,
            output.demand_driver,
            json.dumps([layer for layer in output.value_chain_layers]),
            json.dumps([layer for layer in output.suspected_bottleneck_layers]),
            json.dumps([c.model_dump(mode='json') for c in output.candidate_pool_raw]),
            json.dumps([c.model_dump(mode='json') for c in output.candidate_shortlist]),
            json.dumps(output.hypothesis_draft),
            json.dumps(output.evidence_gaps),
            output.harness.model_dump_json(),
            output.created_at.isoformat(),
        ))
        self.conn.commit()

    def get_serenity_output(self, theme_id: str) -> SerenityOutput | None:
        """Get Serenity output for a theme."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM serenity_outputs WHERE theme_id = ?", (theme_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        from contracts.research import SerenityOutput, AgentHarnessConfig, CandidateStock
        
        return SerenityOutput(
            theme_id=row["theme_id"],
            demand_driver=row["demand_driver"],
            value_chain_layers=json.loads(row["value_chain_layers"]),
            suspected_bottleneck_layers=json.loads(row["suspected_bottleneck_layers"]),
            candidate_pool_raw=[CandidateStock(**c) for c in json.loads(row["candidate_pool_raw"])],
            candidate_shortlist=[CandidateStock(**c) for c in json.loads(row["candidate_shortlist"])],
            hypothesis_draft=json.loads(row["hypothesis_draft"]),
            evidence_gaps=json.loads(row["evidence_gaps"]),
            harness=AgentHarnessConfig.model_validate_json(row["harness"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def store_evidence_output(self, output: EvidenceOutput):
        """Store Evidence analysis output."""
        cursor = self.conn.cursor()
        
        # Upsert: replace existing output for this candidate
        cursor.execute("""
            INSERT OR REPLACE INTO evidence_outputs
            (candidate_id, kill_criteria_hash, evidence_level, supporting_evidence, 
             falsifying_evidence, conflict_items, blocking_issues, evidence_gaps, tool_trace, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            output.candidate_id,
            output.kill_criteria_hash,
            output.evidence_level,
            json.dumps([e.model_dump(mode='json') for e in output.supporting_evidence]),
            json.dumps([e.model_dump(mode='json') for e in output.falsifying_evidence]),
            json.dumps([c.model_dump(mode='json') for c in output.conflict_items]),
            json.dumps(output.blocking_issues),
            json.dumps(output.evidence_gaps),
            json.dumps(output.tool_trace),
            output.created_at.isoformat(),
        ))
        self.conn.commit()

    def get_evidence_output(self, candidate_id: str) -> EvidenceOutput | None:
        """Get Evidence output for a candidate."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM evidence_outputs WHERE candidate_id = ?", (candidate_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        from contracts.research import EvidenceOutput, EvidenceItem, ConflictItem
        
        return EvidenceOutput(
            candidate_id=row["candidate_id"],
            kill_criteria_hash=row["kill_criteria_hash"],
            evidence_level=row["evidence_level"],
            supporting_evidence=[EvidenceItem(**e) for e in json.loads(row["supporting_evidence"])],
            falsifying_evidence=[EvidenceItem(**e) for e in json.loads(row["falsifying_evidence"])],
            conflict_items=[ConflictItem(**c) for c in json.loads(row["conflict_items"])],
            blocking_issues=json.loads(row["blocking_issues"]),
            evidence_gaps=json.loads(row["evidence_gaps"]),
            tool_trace=json.loads(row["tool_trace"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def store_evidence_snapshot(
        self,
        snapshot_id: str,
        candidate_id: str,
        verification_id: str | None,
        snapshot_date: str | None,
        symbol: str,
        evidence_output: dict,
        packet_input_hash: str = "",
        tool_result_hash: str = "",
        packet_data: str = "",
        audit_id: str | None = None,
    ) -> None:
        """Store an immutable Evidence snapshot (append-only)."""
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO evidence_snapshots
            (snapshot_id, candidate_id, verification_id, snapshot_date, symbol,
             evidence_output, packet_input_hash, tool_result_hash, packet_data, audit_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            snapshot_id, candidate_id, verification_id, snapshot_date, symbol,
            json.dumps(evidence_output), packet_input_hash, tool_result_hash,
            packet_data, audit_id, now,
        ))
        self.conn.commit()

    def get_evidence_snapshot(self, snapshot_id: str) -> dict | None:
        """Get an Evidence snapshot by ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM evidence_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "snapshot_id": row["snapshot_id"],
            "candidate_id": row["candidate_id"],
            "verification_id": row["verification_id"],
            "snapshot_date": row["snapshot_date"],
            "symbol": row["symbol"],
            "evidence_output": json.loads(row["evidence_output"]),
            "packet_input_hash": row["packet_input_hash"],
            "tool_result_hash": row["tool_result_hash"],
            "packet_data": row["packet_data"],
            "audit_id": row["audit_id"],
            "created_at": row["created_at"],
        }

    def get_evidence_snapshots_for_candidate(self, candidate_id: str) -> list[dict]:
        """Get all Evidence snapshots for a candidate."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM evidence_snapshots WHERE candidate_id = ? ORDER BY created_at DESC",
            (candidate_id,),
        )
        results = []
        for row in cursor.fetchall():
            results.append({
                "snapshot_id": row["snapshot_id"],
                "candidate_id": row["candidate_id"],
                "verification_id": row["verification_id"],
                "snapshot_date": row["snapshot_date"],
                "symbol": row["symbol"],
                "evidence_output": json.loads(row["evidence_output"]),
                "packet_input_hash": row["packet_input_hash"],
                "tool_result_hash": row["tool_result_hash"],
                "packet_data": row["packet_data"],
                "audit_id": row["audit_id"],
                "created_at": row["created_at"],
            })
        return results

    def store_ticker_verification(self, record: "TickerVerificationRecord"):
        """Store ticker verification record."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO ticker_verification_records
            (verification_id, symbol, company_name, exchange, status, confidence, 
             source, notes, verified_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.verification_id,
            record.symbol,
            record.company_name,
            record.exchange,
            record.status,
            record.confidence,
            record.source,
            record.notes,
            record.verified_at.isoformat(),
            record.expires_at.isoformat(),
        ))
        self.conn.commit()

    def get_ticker_verification(self, verification_id: str) -> "TickerVerificationRecord | None":
        """Get ticker verification record by verification_id."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM ticker_verification_records WHERE verification_id = ?",
            (verification_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        
        from contracts.research import TickerVerificationRecord
        
        return TickerVerificationRecord(
            verification_id=row["verification_id"],
            symbol=row["symbol"],
            company_name=row["company_name"],
            exchange=row["exchange"],
            status=row["status"],
            confidence=row["confidence"],
            source=row["source"],
            notes=row["notes"],
            verified_at=datetime.fromisoformat(row["verified_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
        )

    def is_verification_valid(self, verification_id: str) -> bool:
        """Check if verification_id exists and has not expired."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 1 FROM ticker_verification_records
            WHERE verification_id = ? AND expires_at > ?
        """, (verification_id, datetime.now().isoformat()))
        return cursor.fetchone() is not None

    def store_friend_stock_flow(
        self,
        flow_id: str,
        raw_company_input: str,
        raw_code_input: Optional[str],
        source_note: str,
        ticker_verification_result: Optional[dict] = None,
        research_output: Optional[dict] = None,
    ):
        """Store or update friend stock flow state."""
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        
        # Check if exists
        cursor.execute("SELECT 1 FROM friend_stock_flows WHERE flow_id = ?", (flow_id,))
        exists = cursor.fetchone() is not None
        
        if exists:
            # Update
            cursor.execute("""
                UPDATE friend_stock_flows
                SET ticker_verification_result = ?,
                    research_output = ?,
                    updated_at = ?
                WHERE flow_id = ?
            """, (
                json.dumps(ticker_verification_result) if ticker_verification_result else None,
                json.dumps(research_output) if research_output else None,
                now,
                flow_id,
            ))
        else:
            # Insert
            cursor.execute("""
                INSERT INTO friend_stock_flows
                (flow_id, raw_company_input, raw_code_input, source_note,
                 ticker_verification_result, research_output, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                flow_id,
                raw_company_input,
                raw_code_input,
                source_note,
                json.dumps(ticker_verification_result) if ticker_verification_result else None,
                json.dumps(research_output) if research_output else None,
                now,
                now,
            ))
        
        self.conn.commit()

    def get_friend_stock_flow(self, flow_id: str) -> Optional[dict]:
        """Get friend stock flow state by flow_id."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM friend_stock_flows WHERE flow_id = ?", (flow_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        return {
            "flow_id": row["flow_id"],
            "raw_company_input": row["raw_company_input"],
            "raw_code_input": row["raw_code_input"],
            "source_note": row["source_note"],
            "ticker_verification_result": json.loads(row["ticker_verification_result"]) if row["ticker_verification_result"] else None,
            "research_output": json.loads(row["research_output"]) if row["research_output"] else None,
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
