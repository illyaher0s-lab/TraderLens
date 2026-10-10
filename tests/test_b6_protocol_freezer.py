"""B6 coverage-bound freezer tests against real artifact verifier boundaries."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import unittest
import uuid
from datetime import date, datetime
from pathlib import Path

from backend.db.strategy import StrategyDB
from backend.services.oos_budget_ledger import OOSBudgetLedger
from backend.services.research_protocol_freezer import ResearchProtocolFreezer
from backend.services.strategy_template_library import (
    convert_to_frozen_contract,
    get_template_by_id,
)
from contracts.strategy import (
    BacktestUniverseSpec,
    FrozenCriteriaReference,
    ProtocolFreezePreflightResult,
    ResearchProtocolSnapshot,
    SourceRuleMapping,
    StrategyDraft,
    StrategyTemplateDefinition,
    compute_b6_protocol_id,
)


ROOT = Path(__file__).parent.parent
SUCCESSOR = ROOT / "data/pit/qualification_successors/e5100669ed247769"
PREDECESSOR = ROOT / "data/pit/formal_packages/de3fed9c3819d25c/manifest.json"
COVERAGE = ROOT / "data/pit/coverage_packages/695245b51005e50b"
SNAPSHOT = ROOT / "data/pit/data_snapshot_manifests/ds_traderlens_v2_shsz_pit_001"
SCOPE_FREEZE = ROOT / "docs/verification/V2_HISTORICAL_VALIDATION_SCOPE_FREEZE.md"


class RecordingLedger:
    """Count reads and prove the freezer never reserves."""

    def __init__(self, real: OOSBudgetLedger):
        self.real = real
        self.gets = 0
        self.reserves = 0

    def get_ledger_state(self, theme_id, hypothesis_source_snapshot_id):
        self.gets += 1
        return self.real.get_ledger_state(theme_id, hypothesis_source_snapshot_id)

    def reserve_oos_draw(self, *args, **kwargs):
        self.reserves += 1
        return self.real.reserve_oos_draw(*args, **kwargs)

    @property
    def db(self):
        return self.real.db


def _criteria(raw: str, snapshot_id: str) -> tuple[FrozenCriteriaReference, str]:
    canonical = json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":"))
    content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return (
        FrozenCriteriaReference(
            snapshot_id=snapshot_id,
            criteria_json=raw,
            declared_content_hash=content_hash,
        ),
        content_hash,
    )


def _valid_contracts() -> dict:
    gate, gate_hash = _criteria('{"min_sharpe":1.0}', "g1")
    kill, kill_hash = _criteria('{"max_dd":0.2}', "k1")
    envelope = json.dumps(
        {
            "gate_content_hash": gate_hash,
            "gate_snapshot_id": "g1",
            "kill_content_hash": kill_hash,
            "kill_snapshot_id": "k1",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    template = StrategyTemplateDefinition(
        template_id="relative_strength_rotation_shsz_sw2021_v1",
        version="v1_shsz_sw2021_pit",
        template_hash="17a1be7ea3547e7a3cc85ea25e63b43aa2ddb4e8ced50c699db5a1bdd9cec9f0",
        hypothesis_types=("momentum",),
        core_entry_rule_id="r",
        supported_universe_rule_types=("point_in_time_membership",),
        sample_split_rule_ids=("fixed_70_30",),
        benchmark_rule_id="b",
        created_at=datetime(2024, 1, 1),
        governance_status="approved",
        source_citation="x",
        source_retrieval_date=date(2024, 1, 1),
        market_scope_difference="x",
        data_requirements_hash="e2fff0c75089b88eacc068ce5347d5995ad7cd05b2835906182ac66e5dd709fa",
        governance_evidence_hash="x",
        reviewer_id="a",
        reviewed_at=datetime(2024, 1, 1),
        review_due_date=date(2025, 1, 1),
        review_evidence_path="x",
        review_evidence_sha256="x",
        owner_authorization_hash="x",
        authorized_by="illya",
        authorized_at=datetime(2024, 1, 2),
        source_rule_mappings=(
            SourceRuleMapping(
                source_claim_id="c",
                frozen_rule_id="r",
                mapping_kind="source_claim",
                rationale="x",
            ),
        ),
    )
    draft = StrategyDraft(
        strategy_revision_id="r1",
        theme_id="t1",
        hypothesis_id="h1",
        strategy_template_id=template.template_id,
        strategy_template_version=template.version,
        strategy_template_hash=template.template_hash,
        hypothesis_source_snapshot_id="s1",
        backtest_universe_spec_id="u1",
        strategy_config_json='{"x":1}',
        sample_split_rule_id="fixed_70_30",
        created_at=datetime(2024, 1, 1),
    )
    universe = BacktestUniverseSpec(
        universe_spec_id="u1",
        universe_rule_type="point_in_time_membership",
        membership_source="formal_pit_membership",
        membership_effective_from=date(2020, 1, 1),
        membership_effective_to=date(2025, 1, 1),
        snapshot_date=date(2020, 1, 1),
        membership_snapshot_ids=("pims_traderlens_v2_shsz_sw2021_pit_005",),
        quality_status="ok",
    )
    return {
        "template": template,
        "draft": draft,
        "universe": universe,
        "gate": gate,
        "kill": kill,
        "envelope_hash": hashlib.sha256(envelope.encode("utf-8")).hexdigest(),
    }


class TestB6ProtocolFreezer(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "ledger.db"
        self.db = StrategyDB(str(self.db_path))
        self.ledger = OOSBudgetLedger(self.db)
        self.ledger.get_ledger_state("t1", "s1")
        self.extra_dbs: list[StrategyDB] = []
        self.freezer = ResearchProtocolFreezer()

    def tearDown(self):
        for db in self.extra_dbs:
            db.close()
        self.db.close()
        self.temp.cleanup()

    def _bundle(self) -> dict:
        target = self.root / f"artifacts_{uuid.uuid4().hex[:8]}"
        target.mkdir()
        successor = target / "successor"
        coverage = target / "coverage"
        snapshot = target / "snapshot"
        shutil.copytree(SUCCESSOR, successor)
        shutil.copytree(COVERAGE, coverage)
        shutil.copytree(SNAPSHOT, snapshot)
        predecessor = target / "predecessor.json"
        scope = target / "scope.md"
        shutil.copy2(PREDECESSOR, predecessor)
        shutil.copy2(SCOPE_FREEZE, scope)
        return {
            "successor_dir": successor,
            "predecessor_manifest_path": predecessor,
            "coverage_manifest_path": coverage / "coverage_manifest.json",
            "coverage_sidecar_path": coverage / "coverage_manifest.json.sha256",
            "coverage_by_code_path": coverage / "coverage_by_code.parquet",
            "coverage_by_date_path": coverage / "coverage_by_date.parquet",
            "unavailable_path": coverage / "unavailable_security_dates.parquet",
            "formal_snapshot_dir": snapshot,
            "scope_freeze_path": scope,
        }

    def _call(self, *, bundle=None, **overrides):
        values = _valid_contracts()
        args = {
            **(bundle or self._bundle()),
            "approved_template": values["template"],
            "gate_reference": values["gate"],
            "kill_reference": values["kill"],
            "ledger": self.ledger,
            "strategy_draft": values["draft"],
            "universe": values["universe"],
            "oos_window_rule_id": "latest_252_trading_days",
            "oos_window_start": date(2024, 1, 1),
            "oos_window_end": date(2024, 12, 31),
            "frozen_by": "test",
            "backtest_start": date(2024, 1, 1),
            "gate_criteria_hash": values["envelope_hash"],
        }
        args.update(overrides)
        return self.freezer.freeze_b6_coverage_bound_protocol(**args)

    def _memory_ledger(self):
        db = StrategyDB(":memory:")
        self.extra_dbs.append(db)
        return OOSBudgetLedger(db)

    def _active_ledger(self):
        db = StrategyDB(str(self.root / f"active_{uuid.uuid4().hex}.db"))
        self.extra_dbs.append(db)
        ledger = OOSBudgetLedger(db)
        ledger.reserve_oos_draw("t1", "s1", "cfg", "data", "gate", "w", "idem")
        return ledger

    def _exhausted_ledger(self):
        db = StrategyDB(str(self.root / f"exhausted_{uuid.uuid4().hex}.db"))
        self.extra_dbs.append(db)
        ledger = OOSBudgetLedger(db)
        for index in range(3):
            reservation = ledger.reserve_oos_draw(
                "t1", "s1", f"c{index}", f"d{index}", f"g{index}", "w", f"k{index}"
            )
            ledger.start_execution(reservation.reservation_id)
            ledger.complete_reservation(reservation.reservation_id, "rejected")
        return ledger

    def _row_counts(self):
        connection = sqlite3.connect(self.db_path)
        try:
            tables = (
                "research_protocol_snapshots",
                "oos_budget_state",
                "oos_budget_reservations",
                "oos_evaluation_ledgers",
            )
            return {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
        finally:
            connection.close()

    def test_all_13_reason_codes(self):
        valid = _valid_contracts()
        missing_sidecar = self._bundle()
        missing_sidecar["successor_dir"].joinpath("manifest.json.sha256").unlink()
        cases = (
            ("availability_qualification_unavailable", {"successor_dir": self.root / "missing"}),
            ("availability_successor_binding_invalid", {"bundle": missing_sidecar}),
            ("snapshot_manifest_unavailable", {"formal_snapshot_dir": self.root / "missing_snapshot"}),
            ("template_not_approved", {"approved_template": valid["template"].model_copy(update={"governance_status": "candidate"})}),
            ("template_binding_mismatch", {"approved_template": valid["template"].model_copy(update={"template_hash": "wrong"})}),
            ("artifact_binding_mismatch", {"coverage_manifest_path": self.root / "missing_coverage.json"}),
            ("criteria_reference_unavailable", {"gate_reference": FrozenCriteriaReference(snapshot_id="", criteria_json="{}", declared_content_hash="x")}),
            ("criteria_content_hash_mismatch", {"gate_reference": FrozenCriteriaReference(snapshot_id="g1", criteria_json='{"a":1}', declared_content_hash="wrong")}),
            ("criteria_envelope_hash_mismatch", {"gate_criteria_hash": "wrong"}),
            ("ledger_owner_unavailable", {"ledger": self._memory_ledger()}),
            ("ledger_active_reservation", {"ledger": self._active_ledger()}),
            ("ledger_budget_exhausted", {"ledger": self._exhausted_ledger()}),
            ("split_or_time_consistency_invalid", {"oos_window_rule_id": "unregistered"}),
        )
        for reason_code, overrides in cases:
            with self.subTest(reason_code=reason_code):
                bundle = overrides.pop("bundle", None)
                result = self._call(bundle=bundle, **overrides)
                self.assertIsInstance(result, ProtocolFreezePreflightResult)
                self.assertEqual(result.reason_code, reason_code)

    def test_positive_uses_real_verifiers_and_is_deterministic(self):
        first = self._call()
        second = self._call()
        self.assertIsInstance(first, ResearchProtocolSnapshot)
        self.assertEqual(first.protocol_profile, "b6_coverage_bound")
        self.assertEqual(first.protocol_snapshot_id, compute_b6_protocol_id(first))
        self.assertEqual(first.protocol_snapshot_id, second.protocol_snapshot_id)

    def test_corrupt_artifacts_fail_loud(self):
        mutations = (
            ("successor", "manifest.json"),
            ("snapshot", "manifest.json"),
            ("coverage", "coverage_by_code.parquet"),
        )
        for area, filename in mutations:
            with self.subTest(area=area):
                bundle = self._bundle()
                base = {
                    "successor": bundle["successor_dir"],
                    "snapshot": bundle["formal_snapshot_dir"],
                    "coverage": bundle["coverage_manifest_path"].parent,
                }[area]
                with (base / filename).open("ab") as handle:
                    handle.write(b"tampered")
                with self.assertRaisesRegex(ValueError, "verification failed"):
                    self._call(bundle=bundle)

    def test_exact_draft_template_universe_and_split_bindings(self):
        valid = _valid_contracts()
        cases = (
            ("template_binding_mismatch", {"strategy_draft": valid["draft"].model_copy(update={"strategy_template_version": "wrong"})}),
            ("split_or_time_consistency_invalid", {"strategy_draft": valid["draft"].model_copy(update={"backtest_universe_spec_id": "other"})}),
            ("split_or_time_consistency_invalid", {"strategy_draft": valid["draft"].model_copy(update={"sample_split_rule_id": "unsupported"})}),
        )
        for reason_code, overrides in cases:
            with self.subTest(reason_code=reason_code):
                result = self._call(**overrides)
                self.assertIsInstance(result, ProtocolFreezePreflightResult)
                self.assertEqual(result.reason_code, reason_code)

    def test_criteria_key_order_is_canonical(self):
        gate_a, gate_hash = _criteria('{"z":2,"a":1}', "g1")
        gate_b, _ = _criteria('{ "a" : 1, "z" : 2 }', "g1")
        _, kill_hash = _criteria('{"max_dd":0.2}', "k1")
        envelope = json.dumps(
            {
                "gate_content_hash": gate_hash,
                "gate_snapshot_id": "g1",
                "kill_content_hash": kill_hash,
                "kill_snapshot_id": "k1",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        envelope_hash = hashlib.sha256(envelope.encode("utf-8")).hexdigest()
        first = self._call(gate_reference=gate_a, gate_criteria_hash=envelope_hash)
        second = self._call(gate_reference=gate_b, gate_criteria_hash=envelope_hash)
        self.assertEqual(first.protocol_snapshot_id, second.protocol_snapshot_id)
        self.assertEqual(first.prototype_gate_thresholds_json, '{"a":1,"z":2}')

    def test_zero_writes_and_ledger_call_counts(self):
        before = self._row_counts()
        early = RecordingLedger(self.ledger)
        candidate = _valid_contracts()["template"].model_copy(update={"governance_status": "candidate"})
        unavailable = self._call(approved_template=candidate, ledger=early)
        self.assertIsInstance(unavailable, ProtocolFreezePreflightResult)
        self.assertEqual(early.gets, 0)
        self.assertEqual(early.reserves, 0)
        self.assertEqual(before, self._row_counts())

        success = RecordingLedger(self.ledger)
        protocol = self._call(ledger=success)
        self.assertIsInstance(protocol, ResearchProtocolSnapshot)
        self.assertEqual(success.gets, 1)
        self.assertEqual(success.reserves, 0)
        self.assertEqual(before, self._row_counts())

    def test_current_approved_v2_cannot_inherit_v1_artifacts(self):
        template = convert_to_frozen_contract(
            get_template_by_id("relative_strength_rotation_shsz_sw2021_v2"),
            datetime(2026, 7, 20),
        )
        self.assertEqual(template.governance_status, "approved")
        draft = _valid_contracts()["draft"].model_copy(
            update={
                "strategy_template_id": template.template_id,
                "strategy_template_version": template.version,
                "strategy_template_hash": template.template_hash,
            }
        )
        result = self._call(approved_template=template, strategy_draft=draft)
        self.assertIsInstance(result, ProtocolFreezePreflightResult)
        self.assertEqual(result.reason_code, "template_binding_mismatch")


if __name__ == "__main__":
    unittest.main()
