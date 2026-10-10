"""
Template Governance V2 Tests

Tests candidate governance record, approved filtering, and B6 guard.
Per Task 1 section 2.3 and L167-171.
"""
import unittest
from datetime import datetime, date
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from backend.services.strategy_template_library import (
    _governance_evidence_hash,
    get_template_by_id,
    list_approved_templates,
    convert_to_frozen_contract,
)
from contracts.strategy import SourceRuleMapping, StrategyTemplateDefinition


class TestV2TemplateGovernanceRecord(unittest.TestCase):
    """Test V2 template candidate governance record."""

    def test_v2_template_exists_and_has_frozen_hash(self):
        """V2 template relative_strength_rotation_shsz_sw2021_v1 exists with frozen hash."""
        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v1")
        
        self.assertIsNotNone(template, "V2 template must exist")
        self.assertEqual(template.template_id, "relative_strength_rotation_shsz_sw2021_v1")
        self.assertEqual(template.version, "v1_shsz_sw2021_pit")
        
        # Frozen hash must be deterministic and non-empty
        hash1 = template.frozen_template_hash
        hash2 = template.frozen_template_hash
        self.assertEqual(hash1, hash2)
        self.assertGreater(len(hash1), 32)
    
    def test_v2_template_converts_to_candidate_with_governance_metadata(self):
        """V2 template converts to StrategyTemplateDefinition with candidate governance."""
        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v1")
        frozen = convert_to_frozen_contract(template, created_at=datetime(2026, 7, 15, 10, 0, 0))
        
        # Must be candidate (not approved, not retired)
        self.assertEqual(frozen.governance_status, "candidate")
        
        # Must have J&T citation (same source as v1)
        self.assertEqual(frozen.source_citation, "10.1111/j.1540-6261.1993.tb04702.x")
        
        # Must have retrieval date
        self.assertIsNotNone(frozen.source_retrieval_date)
        self.assertIsInstance(frozen.source_retrieval_date, date)
        
        # Missing reviewer/review fields (candidate, not approved)
        self.assertIsNone(frozen.reviewer_id)
        self.assertIsNone(frozen.reviewed_at)
        self.assertIsNone(frozen.review_due_date)
        
        # Missing rule mapping (candidate, not complete dossier)
        self.assertIsNone(frozen.rule_mapping)
    
    def test_v2_template_does_not_become_approved_without_complete_dossier(self):
        """V2 template stays candidate when dossier incomplete."""
        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v1")
        frozen = convert_to_frozen_contract(template, created_at=datetime(2026, 7, 15, 10, 0, 0))
        
        # Candidate must not be promoted to approved
        self.assertNotEqual(frozen.governance_status, "approved")
        self.assertEqual(frozen.governance_status, "candidate")

    def test_v2_candidate_binds_existing_requirements_with_stable_governance_hash(self):
        """The V2 candidate binds the existing successor and coverage requirements evidence."""
        root = Path(__file__).resolve().parents[1]
        successor = json.loads(
            (root / "data/pit/qualification_successors/e5100669ed247769/manifest.json").read_text(
                encoding="utf-8"
            )
        )
        coverage = json.loads(
            (root / "data/pit/coverage_packages/695245b51005e50b/coverage_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v1")

        first = convert_to_frozen_contract(template, created_at=datetime(2026, 7, 15, 10, 0, 0))
        second = convert_to_frozen_contract(template, created_at=datetime(2026, 7, 16, 10, 0, 0))

        self.assertEqual(
            first.data_requirements_hash,
            successor["predecessor_data_requirements_hash"],
        )
        self.assertEqual(first.data_requirements_hash, coverage["input_data_requirements_hash"])
        self.assertEqual(first.template_hash, successor["template_hash"])
        self.assertEqual(first.source_rule_mappings, ())
        self.assertIn("SH/SZ", first.market_scope_difference)
        self.assertEqual(first.governance_evidence_hash, second.governance_evidence_hash)
        self.assertEqual(first.governance_status, "candidate")

    def test_source_rule_mapping_is_structured_and_marks_constraints(self):
        """A non-source rule cannot be represented as an ambiguous source claim."""
        mapping = SourceRuleMapping(
            source_claim_id="implementation_constraint:limit_up",
            source_locator=None,
            frozen_rule_id="forbidden_market.limit_up",
            mapping_kind="implementation_constraint",
            rationale="A-share execution constraint, not a J&T result.",
        )

        self.assertEqual(mapping.mapping_kind, "implementation_constraint")

    def test_governance_hash_accepts_structured_mappings(self):
        """A future reviewed mapping remains part of deterministic governance evidence."""
        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v1")
        mapping = SourceRuleMapping(
            source_claim_id="claim-1",
            source_locator="p. 2",
            frozen_rule_id="entry.relative_strength_rank_pct_max",
            mapping_kind="source_claim",
            rationale="Reviewed source-to-rule mapping.",
        )
        governance = {
            "status": "candidate",
            "citation": "10.1111/j.1540-6261.1993.tb04702.x",
            "retrieval": date(2026, 7, 10),
            "source_rule_mappings": (mapping,),
            "market_scope_difference": "A-share implementation differs.",
        }

        first = _governance_evidence_hash(template, governance, "requirements-hash")
        second = _governance_evidence_hash(template, governance, "requirements-hash")

        self.assertEqual(first, second)

    def test_contract_rejects_approved_status_without_complete_dossier(self):
        """Approval cannot be forged by setting only governance_status."""
        template = get_template_by_id("relative_strength_rotation_shsz_sw2021_v1")
        candidate = convert_to_frozen_contract(template, created_at=datetime(2026, 7, 15, 10, 0, 0))

        with self.assertRaises(ValidationError):
            StrategyTemplateDefinition.model_validate(
                {**candidate.model_dump(mode="json"), "governance_status": "approved"}
            )


class TestApprovedTemplateFiltering(unittest.TestCase):
    """Test list_approved_templates() returns only approved, not candidate/retired."""
    
    def test_list_approved_excludes_candidate_templates(self):
        """list_approved_templates() does not return candidate templates."""
        approved = list_approved_templates()
        
        candidate_ids = [
            "relative_strength_rotation_v1",
            "theme_momentum_breakout_v1",
            "volume_breakout_followthrough_v1",
            "relative_strength_rotation_shsz_sw2021_v1",  # V2
        ]
        
        approved_ids = [t.template_id for t in approved]
        
        for cid in candidate_ids:
            self.assertNotIn(cid, approved_ids, 
                           f"Candidate template {cid} must not be in approved list")
    
    def test_list_approved_excludes_retired_templates(self):
        """list_approved_templates() does not return retired templates."""
        approved = list_approved_templates()
        approved_ids = [t.template_id for t in approved]
        
        self.assertNotIn("trend_pullback_watch_v1", approved_ids,
                        "Retired template trend_pullback_watch_v1 must not be in approved list")
    
    def test_list_approved_returns_empty_when_no_approved_exists(self):
        """list_approved_templates() returns empty when all templates are candidate/retired."""
        approved = list_approved_templates()
        
        # After Task 1-E: 1 approved (v2), 6 candidate, 1 retired
        self.assertEqual(len(approved), 1, 
                        "Must return 1 approved template (v2) after owner authorization")


class TestB6GovernanceGuard(unittest.TestCase):
    """Test B6 rejects candidate/retired templates via real run_minimal_validation call."""
    
    def test_b6_rejects_candidate_template_before_any_protected_operation(self):
        """B6 must reject candidate template before ledger reserve, runner, gate, or promotion."""
        from backend.services.b6_validation_flow import B6ValidationFlow
        from backend.db.strategy import StrategyDB
        from contracts.strategy import StrategyDraft
        from contracts.b6_task import B6ValidationTask

        # ponytail: fake ledger tracks protected calls
        class FakeLedger:
            def __init__(self):
                self.reserve_calls = 0
            def reserve_oos_draw(self, **kwargs):
                self.reserve_calls += 1
                raise AssertionError("Governance guard failed: ledger.reserve_oos_draw called")

        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        db = StrategyDB(Path(temp_dir.name) / "strategy.db")
        self.addCleanup(db.close)
        fake_ledger = FakeLedger()
        flow = B6ValidationFlow(oos_budget_ledger=fake_ledger, strategy_db=db)

        db.conn.execute("INSERT INTO backtest_universe_specs (universe_spec_id, payload_json, created_at) VALUES (?, ?, ?)",
                       ("univ_spec_001", "{}", datetime.now().isoformat()))

        # V2 candidate template
        draft = StrategyDraft(
            strategy_revision_id="strat_v2_001",
            theme_id="theme_001",
            hypothesis_id="hyp_001",
            strategy_template_id="relative_strength_rotation_shsz_sw2021_v1",
            strategy_template_version="v1_shsz_sw2021_pit",
            strategy_template_hash="hash_tpl_001",
            hypothesis_source_snapshot_id="hyp_snap_001",
            backtest_universe_spec_id="univ_spec_001",
            strategy_config_json="{}",
            sample_split_rule_id="fixed_ratio_70_30",
            created_at=datetime(2026, 7, 15, 10, 0, 0),
        )
        # ponytail: FK constraint needs draft in DB
        db.conn.execute(
            "INSERT INTO strategy_drafts (strategy_revision_id, theme_id, hypothesis_id, backtest_universe_spec_id, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (draft.strategy_revision_id, draft.theme_id, draft.hypothesis_id, draft.backtest_universe_spec_id, "{}", draft.created_at.isoformat())
        )
        db.conn.execute(
            """
            INSERT INTO research_protocol_snapshots
            (protocol_snapshot_id, strategy_revision_id, payload_json,
             strategy_config_hash, data_snapshot_hash, gate_criteria_hash,
             frozen_at, protocol_profile)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "protocol_001",
                draft.strategy_revision_id,
                "{}",
                "strategy_config_hash",
                "data_snapshot_hash",
                "gate_criteria_hash",
                draft.created_at.isoformat(),
                "legacy_b3",
            ),
        )
        db.conn.commit()

        # ponytail: create running task
        task = B6ValidationTask(
            task_id="test_task_candidate",
            task_key=f"b6_val:{draft.strategy_revision_id}",
            task_type="b6_validation",
            strategy_revision_id=draft.strategy_revision_id,
            protocol_snapshot_id="protocol_001",
            status="running",
            created_at=datetime(2026, 7, 15, 10, 0, 0),
        )
        db.create_b6_task(task)

        # Minimal valid inputs (unused because guard blocks early)
        protocol = self._minimal_protocol()
        manifest = self._minimal_manifest()
        universe = self._minimal_universe()

        result = flow.run_minimal_validation(
            strategy_draft=draft,
            protocol=protocol,
            manifest=manifest,
            universe=universe,
            b4_qualification={"status": "pass"},
            b4_event_result={"status": "pass"},
            task_id=task.task_id,
        )

        self.assertEqual(result.status, "blocked")
        self.assertIn("candidate", result.blocking_reason.lower())
        self.assertEqual(fake_ledger.reserve_calls, 0, 
                        "Ledger reserve must not be called for candidate template")
        self.assertEqual(db.conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_b6_rejects_retired_template_before_any_protected_operation(self):
        """B6 must reject retired template before any protected operation."""
        from backend.services.b6_validation_flow import B6ValidationFlow
        from backend.db.strategy import StrategyDB
        from contracts.strategy import StrategyDraft
        from contracts.b6_task import B6ValidationTask

        class FakeLedger:
            def __init__(self):
                self.reserve_calls = 0
            def reserve_oos_draw(self, **kwargs):
                self.reserve_calls += 1
                raise AssertionError("Guard failed: reserve called on retired template")

        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        db = StrategyDB(Path(temp_dir.name) / "strategy.db")
        self.addCleanup(db.close)
        fake_ledger = FakeLedger()
        flow = B6ValidationFlow(oos_budget_ledger=fake_ledger, strategy_db=db)

        db.conn.execute("INSERT INTO backtest_universe_specs (universe_spec_id, payload_json, created_at) VALUES (?, ?, ?)",
                       ("univ_spec_001", "{}", datetime.now().isoformat()))

        draft = StrategyDraft(
            strategy_revision_id="strat_retired_001",
            theme_id="theme_001",
            hypothesis_id="hyp_001",
            strategy_template_id="trend_pullback_watch_v1",
            strategy_template_version="v1",
            strategy_template_hash="hash_retired",
            hypothesis_source_snapshot_id="hyp_snap_001",
            backtest_universe_spec_id="univ_spec_001",
            strategy_config_json="{}",
            sample_split_rule_id="fixed_ratio_70_30",
            created_at=datetime(2026, 7, 15, 10, 0, 0),
        )
        # ponytail: FK constraint needs draft in DB
        db.conn.execute(
            "INSERT INTO strategy_drafts (strategy_revision_id, theme_id, hypothesis_id, backtest_universe_spec_id, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (draft.strategy_revision_id, draft.theme_id, draft.hypothesis_id, draft.backtest_universe_spec_id, "{}", draft.created_at.isoformat())
        )
        db.conn.execute(
            """
            INSERT INTO research_protocol_snapshots
            (protocol_snapshot_id, strategy_revision_id, payload_json,
             strategy_config_hash, data_snapshot_hash, gate_criteria_hash,
             frozen_at, protocol_profile)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "protocol_001",
                draft.strategy_revision_id,
                "{}",
                "strategy_config_hash",
                "data_snapshot_hash",
                "gate_criteria_hash",
                draft.created_at.isoformat(),
                "legacy_b3",
            ),
        )
        db.conn.commit()

        # ponytail: create running task
        task = B6ValidationTask(
            task_id="test_task_retired",
            task_key=f"b6_val:{draft.strategy_revision_id}",
            task_type="b6_validation",
            strategy_revision_id=draft.strategy_revision_id,
            protocol_snapshot_id="protocol_001",
            status="running",
            created_at=datetime(2026, 7, 15, 10, 0, 0),
        )
        db.create_b6_task(task)

        result = flow.run_minimal_validation(
            strategy_draft=draft,
            protocol=self._minimal_protocol(),
            manifest=self._minimal_manifest(),
            universe=self._minimal_universe(),
            b4_qualification={"status": "pass"},
            b4_event_result={"status": "pass"},
            task_id=task.task_id,
        )

        self.assertEqual(result.status, "blocked")
        self.assertIn("retired", result.blocking_reason.lower())
        self.assertEqual(fake_ledger.reserve_calls, 0)
        self.assertEqual(db.conn.execute("PRAGMA foreign_key_check").fetchall(), [])
    
    def _minimal_protocol(self):
        from contracts.strategy import ResearchProtocolSnapshot
        return ResearchProtocolSnapshot(
            protocol_snapshot_id="proto_001",
            theme_id="theme_001",
            strategy_revision_id="strat_001",
            hypothesis_source_snapshot_id="hyp_001",
            strategy_config_hash="hash_001",
            data_snapshot_hash="hash_002",
            gate_criteria_hash="hash_003",
            shared_oos_window_id="oos_001",
            sample_split_rule_id="fixed_ratio_70_30",
            oos_window_rule_id="rule_001",
            oos_window_rule_params_json="{}",
            oos_window_start=date(2023, 1, 1),
            oos_window_end=date(2024, 12, 31),
            backtest_universe_spec_id="univ_spec_001",
            data_snapshot_id="snap_001",
            kill_criteria_snapshot_id="kill_001",
            prototype_gate_thresholds_json="{}",
            frozen_at=datetime(2026, 7, 15, 10, 0, 0),
            frozen_by="test_user",
        )
    
    def _minimal_manifest(self):
        from backend.services.b3_protocol_types import DataSnapshotManifest
        return DataSnapshotManifest(
            snapshot_id="snap_001",
            provider="tushare",
            semantic_hash="sem_001",
            retrieval_date=date(2026, 7, 1),
            market_data_start=date(2020, 1, 1),
            market_data_end=date(2024, 12, 31),
            universe_snapshot_ids=["univ_001"],
            quality_status="ok",
            gaps=(),
        )
    
    def _minimal_universe(self):
        from backend.services.b3_protocol_types import PointInTimeMembershipSnapshot
        return PointInTimeMembershipSnapshot(
            snapshot_id="univ_001",
            snapshot_date=date(2026, 7, 1),
            universe_rule_type="point_in_time_membership",
            membership_source="test",
            include_delisted=False,
            records=(),
            quality_status="ok",
            gaps=(),
        )


if __name__ == "__main__":
    unittest.main()
