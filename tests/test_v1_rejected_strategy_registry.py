"""
V1 Rejected Strategy Registry Tests

Verify append-only rejected strategy persistence.
"""

import unittest
import tempfile
import os
import sqlite3
from datetime import datetime, timezone

from contracts.rejected_strategy import (
    RejectedStrategyRecord,
    RejectedStrategyStatus,
    DataQualityStatus,
)
from backend.services.rejected_strategy_registry import RejectedStrategyRegistry


class TestRejectedStrategyRegistry(unittest.TestCase):
    """Test rejected strategy registry."""

    def setUp(self):
        """Set up test database."""
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.conn = sqlite3.connect(self.db_path)
        self.registry = RejectedStrategyRegistry(self.conn)

    def tearDown(self):
        """Clean up test database."""
        self.conn.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_append_rejected_strategy(self):
        """Can append rejected strategy with failed gate and reason."""
        now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)
        record = RejectedStrategyRecord(
            registry_id="reject_001",
            strategy_revision_id="rev_001",
            template_id="template_001",
            template_version="v1",
            status=RejectedStrategyStatus.REJECTED,
            failed_gate="oos_performance",
            rejection_reason="OOS Sharpe < 0.5",
            data_quality_status=DataQualityStatus.OK,
            artifact_ids=["validation_report_001"],
            created_at=now,
            actor="validation_gate",
        )

        self.registry.append(record)
        retrieved = self.registry.get("reject_001")

        self.assertEqual(retrieved.registry_id, "reject_001")
        self.assertEqual(retrieved.status, RejectedStrategyStatus.REJECTED)
        self.assertEqual(retrieved.failed_gate, "oos_performance")

    def test_append_blocked_strategy(self):
        """Can append blocked strategy."""
        now = datetime.now(timezone.utc)
        record = RejectedStrategyRecord(
            registry_id="block_001",
            strategy_revision_id="rev_002",
            template_id="template_001",
            template_version="v1",
            status=RejectedStrategyStatus.BLOCKED,
            failed_gate="data_quality",
            rejection_reason="Missing price data",
            data_quality_status=DataQualityStatus.UNAVAILABLE,
            artifact_ids=["data_check_001"],
            created_at=now,
            actor="system",
        )

        self.registry.append(record)
        retrieved = self.registry.get("block_001")

        self.assertEqual(retrieved.status, RejectedStrategyStatus.BLOCKED)

    def test_append_needs_review_strategy(self):
        """Can append needs_review strategy."""
        now = datetime.now(timezone.utc)
        record = RejectedStrategyRecord(
            registry_id="review_001",
            strategy_revision_id="rev_003",
            template_id="template_001",
            template_version="v1",
            status=RejectedStrategyStatus.NEEDS_REVIEW,
            failed_gate="edge_case",
            rejection_reason="Unusual market condition",
            data_quality_status=DataQualityStatus.OK,
            artifact_ids=["review_note_001"],
            created_at=now,
            actor="system",
        )

        self.registry.append(record)
        retrieved = self.registry.get("review_001")

        self.assertEqual(retrieved.status, RejectedStrategyStatus.NEEDS_REVIEW)

    def test_artifact_ids_required(self):
        """Artifact IDs are required."""
        now = datetime.now(timezone.utc)

        with self.assertRaises(ValueError):
            RejectedStrategyRecord(
                registry_id="bad_001",
                strategy_revision_id="rev_004",
                template_id="template_001",
                template_version="v1",
                status=RejectedStrategyStatus.REJECTED,
                failed_gate="gate",
                rejection_reason="Reason",
                data_quality_status=DataQualityStatus.OK,
                artifact_ids=[],  # Empty - should fail
                created_at=now,
                actor="system",
            )

    def test_rejection_reason_required(self):
        """Rejection reason is required."""
        now = datetime.now(timezone.utc)

        with self.assertRaises(ValueError):
            RejectedStrategyRecord(
                registry_id="bad_002",
                strategy_revision_id="rev_005",
                template_id="template_001",
                template_version="v1",
                status=RejectedStrategyStatus.REJECTED,
                failed_gate="gate",
                rejection_reason="",  # Empty - should fail
                data_quality_status=DataQualityStatus.OK,
                artifact_ids=["artifact_001"],
                created_at=now,
                actor="system",
            )

    def test_data_quality_status_stored(self):
        """Data quality status is stored."""
        now = datetime.now(timezone.utc)
        record = RejectedStrategyRecord(
            registry_id="dq_001",
            strategy_revision_id="rev_006",
            template_id="template_001",
            template_version="v1",
            status=RejectedStrategyStatus.BLOCKED,
            failed_gate="data_quality",
            rejection_reason="Stale data",
            data_quality_status=DataQualityStatus.STALE,
            artifact_ids=["dq_report_001"],
            created_at=now,
            actor="system",
        )

        self.registry.append(record)
        retrieved = self.registry.get("dq_001")

        self.assertEqual(retrieved.data_quality_status, DataQualityStatus.STALE)

    def test_retest_eligibility_stored(self):
        """Retest eligibility is stored."""
        now = datetime.now(timezone.utc)
        record = RejectedStrategyRecord(
            registry_id="retest_001",
            strategy_revision_id="rev_007",
            template_id="template_001",
            template_version="v1",
            status=RejectedStrategyStatus.REJECTED,
            failed_gate="oos_performance",
            rejection_reason="Low Sharpe",
            data_quality_status=DataQualityStatus.OK,
            future_retest_allowed=True,
            retest_eligibility_reason="Can retest with more data",
            artifact_ids=["validation_001"],
            created_at=now,
            actor="gate",
        )

        self.registry.append(record)
        retrieved = self.registry.get("retest_001")

        self.assertTrue(retrieved.future_retest_allowed)
        self.assertEqual(retrieved.retest_eligibility_reason, "Can retest with more data")

    def test_duplicate_registry_id_fails(self):
        """Duplicate registry_id fails."""
        now = datetime.now(timezone.utc)
        record1 = RejectedStrategyRecord(
            registry_id="dup_001",
            strategy_revision_id="rev_008",
            template_id="template_001",
            template_version="v1",
            status=RejectedStrategyStatus.REJECTED,
            failed_gate="gate",
            rejection_reason="Reason",
            data_quality_status=DataQualityStatus.OK,
            artifact_ids=["artifact_001"],
            created_at=now,
            actor="system",
        )

        self.registry.append(record1)

        record2 = RejectedStrategyRecord(
            registry_id="dup_001",  # Same ID
            strategy_revision_id="rev_009",
            template_id="template_001",
            template_version="v1",
            status=RejectedStrategyStatus.REJECTED,
            failed_gate="gate",
            rejection_reason="Different reason",
            data_quality_status=DataQualityStatus.OK,
            artifact_ids=["artifact_002"],
            created_at=now,
            actor="system",
        )

        with self.assertRaises(ValueError) as ctx:
            self.registry.append(record2)

        self.assertIn("duplicate", str(ctx.exception).lower())

    def test_count_by_status(self):
        """count_by_status works."""
        now = datetime.now(timezone.utc)
        
        # Add rejected
        self.registry.append(RejectedStrategyRecord(
            registry_id="count_001",
            strategy_revision_id="rev_010",
            template_id="template_001",
            template_version="v1",
            status=RejectedStrategyStatus.REJECTED,
            failed_gate="gate",
            rejection_reason="Reason",
            data_quality_status=DataQualityStatus.OK,
            artifact_ids=["art_001"],
            created_at=now,
            actor="system",
        ))
        
        # Add blocked
        self.registry.append(RejectedStrategyRecord(
            registry_id="count_002",
            strategy_revision_id="rev_011",
            template_id="template_001",
            template_version="v1",
            status=RejectedStrategyStatus.BLOCKED,
            failed_gate="gate",
            rejection_reason="Reason",
            data_quality_status=DataQualityStatus.OK,
            artifact_ids=["art_002"],
            created_at=now,
            actor="system",
        ))

        counts = self.registry.count_by_status()
        self.assertEqual(counts.get("rejected"), 1)
        self.assertEqual(counts.get("blocked"), 1)

    def test_count_by_failed_gate(self):
        """count_by_failed_gate works."""
        now = datetime.now(timezone.utc)
        
        self.registry.append(RejectedStrategyRecord(
            registry_id="gate_001",
            strategy_revision_id="rev_012",
            template_id="template_001",
            template_version="v1",
            status=RejectedStrategyStatus.REJECTED,
            failed_gate="oos_performance",
            rejection_reason="Reason",
            data_quality_status=DataQualityStatus.OK,
            artifact_ids=["art_001"],
            created_at=now,
            actor="system",
        ))
        
        self.registry.append(RejectedStrategyRecord(
            registry_id="gate_002",
            strategy_revision_id="rev_013",
            template_id="template_001",
            template_version="v1",
            status=RejectedStrategyStatus.REJECTED,
            failed_gate="oos_performance",
            rejection_reason="Reason",
            data_quality_status=DataQualityStatus.OK,
            artifact_ids=["art_002"],
            created_at=now,
            actor="system",
        ))

        counts = self.registry.count_by_failed_gate()
        self.assertEqual(counts.get("oos_performance"), 2)

    def test_find_by_strategy_revision_id(self):
        """find_by_revision works."""
        now = datetime.now(timezone.utc)
        
        self.registry.append(RejectedStrategyRecord(
            registry_id="find_001",
            strategy_revision_id="rev_target",
            template_id="template_001",
            template_version="v1",
            status=RejectedStrategyStatus.REJECTED,
            failed_gate="gate",
            rejection_reason="Reason",
            data_quality_status=DataQualityStatus.OK,
            artifact_ids=["art_001"],
            created_at=now,
            actor="system",
        ))

        results = self.registry.find_by_revision("rev_target")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].strategy_revision_id, "rev_target")

    def test_find_by_template(self):
        """find_by_template works."""
        now = datetime.now(timezone.utc)
        
        self.registry.append(RejectedStrategyRecord(
            registry_id="tmpl_001",
            strategy_revision_id="rev_014",
            template_id="template_target",
            template_version="v1",
            status=RejectedStrategyStatus.REJECTED,
            failed_gate="gate",
            rejection_reason="Reason",
            data_quality_status=DataQualityStatus.OK,
            artifact_ids=["art_001"],
            created_at=now,
            actor="system",
        ))

        results = self.registry.find_by_template("template_target")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].template_id, "template_target")

    def test_no_live_execution_fields(self):
        """Record does not contain live execution fields."""
        now = datetime.now(timezone.utc)
        record = RejectedStrategyRecord(
            registry_id="noexec_001",
            strategy_revision_id="rev_015",
            template_id="template_001",
            template_version="v1",
            status=RejectedStrategyStatus.REJECTED,
            failed_gate="gate",
            rejection_reason="Reason",
            data_quality_status=DataQualityStatus.OK,
            artifact_ids=["art_001"],
            created_at=now,
            actor="system",
        )

        self.assertFalse(hasattr(record, "execution_price"))
        self.assertFalse(hasattr(record, "fill_quantity"))
        self.assertFalse(hasattr(record, "broker"))

    def test_no_pnl_fields(self):
        """Record does not contain P&L fields."""
        now = datetime.now(timezone.utc)
        record = RejectedStrategyRecord(
            registry_id="nopnl_001",
            strategy_revision_id="rev_016",
            template_id="template_001",
            template_version="v1",
            status=RejectedStrategyStatus.REJECTED,
            failed_gate="gate",
            rejection_reason="Reason",
            data_quality_status=DataQualityStatus.OK,
            artifact_ids=["art_001"],
            created_at=now,
            actor="system",
        )

        self.assertFalse(hasattr(record, "realized_pnl"))
        self.assertFalse(hasattr(record, "unrealized_pnl"))

    def test_db_does_not_import_llm(self):
        """DB does not import LLM clients."""
        import backend.db.rejected_strategy as db_module
        import inspect

        source = inspect.getsource(db_module)
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("anthropic", source.lower())

    def test_service_does_not_import_llm(self):
        """Service does not import LLM clients."""
        import backend.services.rejected_strategy_registry as svc_module
        import inspect

        source = inspect.getsource(svc_module)
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("anthropic", source.lower())


if __name__ == "__main__":
    unittest.main()


class TestRejectedStrategyExtraFieldsRejection(unittest.TestCase):
    """Test rejected strategy rejects extra execution/P&L fields."""

    def test_rejects_pnl_field(self):
        """Constructing with pnl field raises validation error."""
        now = datetime.now(timezone.utc)
        
        with self.assertRaises(Exception):  # Pydantic ValidationError
            RejectedStrategyRecord(
                registry_id="bad_pnl",
                strategy_revision_id="rev_001",
                template_id="template_001",
                template_version="v1",
                status=RejectedStrategyStatus.REJECTED,
                failed_gate="gate",
                rejection_reason="Reason",
                data_quality_status=DataQualityStatus.OK,
                artifact_ids=["art_001"],
                created_at=now,
                actor="system",
                pnl=123.45,  # Extra field - should fail
            )

    def test_rejects_recommendation_level_field(self):
        """Constructing with recommendation_level raises validation error."""
        now = datetime.now(timezone.utc)
        
        with self.assertRaises(Exception):
            RejectedStrategyRecord(
                registry_id="bad_rec",
                strategy_revision_id="rev_001",
                template_id="template_001",
                template_version="v1",
                status=RejectedStrategyStatus.REJECTED,
                failed_gate="gate",
                rejection_reason="Reason",
                data_quality_status=DataQualityStatus.OK,
                artifact_ids=["art_001"],
                created_at=now,
                actor="system",
                recommendation_level="strongly_execute",  # Extra field
            )

    def test_rejects_execution_price_field(self):
        """Constructing with execution_price raises validation error."""
        now = datetime.now(timezone.utc)
        
        with self.assertRaises(Exception):
            RejectedStrategyRecord(
                registry_id="bad_exec",
                strategy_revision_id="rev_001",
                template_id="template_001",
                template_version="v1",
                status=RejectedStrategyStatus.REJECTED,
                failed_gate="gate",
                rejection_reason="Reason",
                data_quality_status=DataQualityStatus.OK,
                artifact_ids=["art_001"],
                created_at=now,
                actor="system",
                execution_price=10.5,  # Extra field
            )
