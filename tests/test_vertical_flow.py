"""
A 模块完整纵向流程测试

Tests the complete flow:
  Theme creation → verify_ticker → ProposedAction → reducer add candidate
  → real hard filter → data tools → Evidence Agent → source quality + fact check
  → EvidenceSnapshot → human confirmation → confirmed_candidate_pool

Key assertions:
- verification_id 一致性追踪每一步
- 数据缺失不能默认通过
- LLM 编造事实不能进入快照
- 有 blocking issue 不能确认
- 确认池完整冻结 Evidence、thesis、失效规则、价格和基准快照
- A 模块输出不包含买卖、止损、仓位或次日行动
"""

import unittest
from datetime import date, datetime, timedelta
from fastapi.testclient import TestClient
from backend.db.research import ResearchDB
from backend.api.research import create_research_app
from backend.services.research_validation import ResearchValidator
from backend.app.tushare.config import TushareConfig
from contracts.research import TickerVerificationRecord
from tests.test_research_validation import FakeTushareClient
from tests.approval_context_fixtures import attach_continued_approval
import hashlib


def _store_verification(db: ResearchDB, symbol: str, company_name: str = "Verified Company") -> str:
    now = datetime.now()
    vid = f"verify_{symbol.replace('.', '_')}"
    db.store_ticker_verification(
        TickerVerificationRecord(
            verification_id=vid,
            symbol=symbol,
            company_name=company_name,
            exchange="SSE" if symbol.endswith(".SH") else "SZSE",
            status="listed",
            confidence="high",
            source="test_fixture",
            notes="Verified for vertical flow",
            verified_at=now,
            expires_at=now + timedelta(hours=24),
        )
    )
    return vid


class TestAVerticalFlow(unittest.TestCase):
    """A 模块完整纵向流程：从主题到确认候选池."""

    def setUp(self):
        self.db = ResearchDB(":memory:")
        config = TushareConfig(token="fake", api_url="http://fake.test")
        validator = ResearchValidator(tushare_config=config)
        validator._tushare_client = FakeTushareClient(config)
        self.app = create_research_app(self.db, validator=validator)
        self.client = TestClient(self.app)
        self.approval_cards = {}

    def _approval_for(self, theme_id: str) -> str:
        if theme_id not in self.approval_cards:
            self.approval_cards[theme_id] = attach_continued_approval(self.db, theme_id)
        return self.approval_cards[theme_id]

    # ------------------------------------------------------------------
    # Helper: add a verified candidate with full setup
    # ------------------------------------------------------------------

    def _create_theme(self, name="纵向流程测试主题") -> str:
        r = self.client.post("/api/research/themes", json={
            "theme_name": name, "background": "端到端测试",
            "source_type": "manual_theme",
        })
        self.assertEqual(r.status_code, 200)
        return r.json()["theme_id"]

    def _add_candidate(self, theme_id: str, symbol: str, company_name: str) -> tuple:
        """Add candidate → returns (candidate_id, verification_id)."""
        vid = _store_verification(self.db, symbol, company_name)
        r = self.client.post(
            f"/api/research/themes/{theme_id}/candidates",
            json={
                "symbol": symbol,
                "verification_id": vid,
                "match_reason": "产业链核心环节",
                "source_type": "manual_stock",
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["candidate_id"], vid

    def _store_snapshot(self, candidate_id: str, verification_id: str,
                        symbol: str, evidence_output: dict,
                        snap_id: str | None = None) -> str:
        sid = snap_id or f"snap_vflow_{candidate_id}"
        packet_data = '{"symbol": "' + symbol + '", "candidate_id": "' + candidate_id + '"}'
        packet_hash = hashlib.sha256(packet_data.encode("utf-8")).hexdigest()
        self.db.store_evidence_snapshot(
            snapshot_id=sid,
            candidate_id=candidate_id,
            verification_id=verification_id,
            snapshot_date="20260624",
            symbol=symbol,
            evidence_output=evidence_output,
            packet_input_hash=packet_hash,
            tool_result_hash="def456",
            packet_data=packet_data,
        )
        return sid

    # ------------------------------------------------------------------
    # Test 1: Full happy-path vertical flow
    # ------------------------------------------------------------------

    def test_full_vertical_flow_theme_to_confirmed_pool(self):
        """Complete A module flow: theme → verify → add → hard filter → evidence → snapshot → confirm."""
        # Step 1: Create theme
        theme_id = self._create_theme()

        # Step 2: Add candidate with verified ticker
        symbol = "300750.SZ"
        candidate_id, verification_id = self._add_candidate(theme_id, symbol, "宁德时代")

        # Step 3: Verify candidate has verification_id set by reducer
        candidate = self.db.get_candidate(candidate_id)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.verification_id, verification_id)
        self.assertEqual(candidate.symbol, symbol)
        self.assertEqual(candidate.company_name, "宁德时代")

        # Step 4: Run evidence (hard filter + evidence light check)
        ev_response = self.client.post(
            "/api/research/candidates/run-evidence",
            json=[candidate_id],
        )
        self.assertEqual(ev_response.status_code, 200)
        ev_results = ev_response.json()["results"]
        self.assertEqual(len(ev_results), 1)
        # With FakeTushareClient, 300750.SZ has clean hard filter data
        self.assertEqual(ev_results[0]["blocking_issues"], [])
        self.assertEqual(ev_results[0]["evidence_level"], "unknown")

        # Step 5: Retrieve evidence output and verify it includes hard_filter_metadata
        evidence = self.client.get(
            f"/api/research/candidates/{candidate_id}/evidence",
        )
        self.assertEqual(evidence.status_code, 200)
        ev_data = evidence.json()
        self.assertIn("tool_trace", ev_data)
        # The tool_trace must start with validation step
        self.assertGreater(len(ev_data["tool_trace"]), 0)
        self.assertEqual(ev_data["tool_trace"][0]["step"], "validation")

        # Step 6: Create EvidenceSnapshot with evidence output
        snap_id = self._store_snapshot(
            candidate_id, verification_id, symbol,
            evidence_output=ev_data,
        )
        snap = self.db.get_evidence_snapshot(snap_id)
        self.assertIsNotNone(snap)
        self.assertEqual(snap["candidate_id"], candidate_id)
        self.assertEqual(snap["verification_id"], verification_id)
        self.assertEqual(snap["symbol"], symbol)

        # Step 7: Confirm candidate with snapshot
        today = date.today().isoformat()
        confirm_response = self.client.post(
            f"/api/research/candidates/{candidate_id}/confirm",
            json={
                "approval_card_id": self._approval_for(theme_id),
                "confirmation_reason": "产业链核心环节，证据充分",
                "evidence_level": "medium",
                "confirmed_by": "user_vflow",
                "pool_snapshot_date": today,
                "thesis_snapshot": "锂电池产业链关键环节",
                "invalidation_rules": [
                    {"type": "demand_shift", "note": "海外需求大幅下降"},
                ],
                "price_snapshot": {
                    "close": 500.0, "volume": 10000000,
                    "is_limit_up": False, "is_limit_down": False,
                    "is_suspended": False,
                },
                "benchmark_snapshot": {
                    "benchmark_type": "index",
                    "benchmark_code": "399006.SZ",
                    "snapshot_value": 3000.0,
                },
                "evidence_snapshot_ids": [snap_id],
                "primary_evidence_snapshot_id": snap_id,
            },
        )
        self.assertEqual(confirm_response.status_code, 200, confirm_response.text)
        confirmed_data = confirm_response.json()
        self.assertEqual(confirmed_data["status"], "confirmed")

        # Step 8: Verify confirmed candidate pool
        pool = self.client.get(
            f"/api/research/themes/{theme_id}/confirmed-candidates",
        )
        self.assertEqual(pool.status_code, 200)
        pool_list = pool.json()
        self.assertEqual(len(pool_list), 1)

        conf = pool_list[0]
        # Frozen fields
        self.assertEqual(conf["thesis_snapshot"], "锂电池产业链关键环节")
        self.assertEqual(len(conf["invalidation_rules"]), 1)
        self.assertEqual(conf["price_snapshot"]["close"], 500.0)
        self.assertEqual(conf["benchmark_snapshot"]["benchmark_type"], "index")
        self.assertEqual(conf["confirmation_reason"], "产业链核心环节，证据充分")
        self.assertEqual(conf["evidence_level"], "medium")
        self.assertEqual(conf["pool_snapshot_date"], today)
        self.assertTrue(conf["forward_only"])
        self.assertEqual(conf["symbol"], symbol)
        self.assertEqual(conf["verification_id"], verification_id)
        # Evidence snapshots frozen
        self.assertIn(snap_id, conf["evidence_snapshot_ids"])
        self.assertEqual(conf["primary_evidence_snapshot_id"], snap_id)

        # Step 9: A 模块输出 MUST NOT contain B/C fields
        self.assertNotIn("entry_price", conf)
        self.assertNotIn("stop_loss", conf)
        self.assertNotIn("position_pct", conf)
        self.assertNotIn("buy_tomorrow", conf)
        self.assertNotIn("target_price", conf)
        self.assertNotIn("order_type", conf)

    # ------------------------------------------------------------------
    # Test 2: verification_id consistency across entire flow
    # ------------------------------------------------------------------

    def test_verification_id_consistent_throughout_flow(self):
        """verification_id is the same from ticker verify through confirmation."""
        theme_id = self._create_theme()
        candidate_id, verification_id = self._add_candidate(theme_id, "600519.SH", "贵州茅台")

        # Candidate stores the original verification_id
        cand = self.db.get_candidate(candidate_id)
        self.assertEqual(cand.verification_id, verification_id)

        # Evidence run uses candidate's verification_id (not re-verified)
        ev_response = self.client.post(
            "/api/research/candidates/run-evidence",
            json=[candidate_id],
        )
        self.assertEqual(ev_response.status_code, 200)

        # Snapshot stores verification_id
        snap_id = self._store_snapshot(candidate_id, verification_id, "600519.SH",
                                        {"evidence_level": "medium", "blocking_issues": []})
        snap = self.db.get_evidence_snapshot(snap_id)
        self.assertEqual(snap["verification_id"], verification_id)

        # Confirmation stores verification_id
        self.client.post(
            f"/api/research/candidates/{candidate_id}/confirm",
            json={
                "approval_card_id": self._approval_for(theme_id),
                "confirmation_reason": "test", "evidence_level": "medium",
                "confirmed_by": "user", "pool_snapshot_date": date.today().isoformat(),
                "thesis_snapshot": "test", "invalidation_rules": [],
                "price_snapshot": {}, "benchmark_snapshot": {},
                "evidence_snapshot_ids": [snap_id],
            },
        )
        conf = self.db.list_confirmed_candidates(theme_id)[0]
        self.assertEqual(conf.verification_id, verification_id)

    # ------------------------------------------------------------------
    # Test 3: Data missing does NOT default pass
    # ------------------------------------------------------------------

    def test_data_gaps_block_default_pass(self):
        """When data source returns empty, unknown flags block the candidate."""
        theme_id = self._create_theme("Gap Test Theme")
        # 000001.SZ has stock_basic data but no daily_basic data in FakeTushareClient
        vid = _store_verification(self.db, "000001.SZ", "平安银行")
        r = self.client.post(
            f"/api/research/themes/{theme_id}/candidates",
            json={
                "symbol": "000001.SZ", "verification_id": vid,
                "match_reason": "test", "source_type": "manual_stock",
            },
        )
        candidate_id = r.json()["candidate_id"]

        ev_response = self.client.post(
            "/api/research/candidates/run-evidence",
            json=[candidate_id],
        )
        results = ev_response.json()["results"]
        # unknown_liquidity should be in blocking_issues
        self.assertIn("unknown_liquidity", results[0]["blocking_issues"])
        self.assertEqual(results[0]["evidence_level"], "unknown")

    # ------------------------------------------------------------------
    # Test 4: Blocking issues prevent confirmation
    # ------------------------------------------------------------------

    def test_blocking_issues_prevent_confirmation(self):
        """Evidence snapshot with blocking_issues cannot be used to confirm."""
        theme_id = self._create_theme()
        candidate_id, verification_id = self._add_candidate(theme_id, "300750.SZ", "宁德时代")

        snap_id = self._store_snapshot(
            candidate_id, verification_id, "300750.SZ",
            evidence_output={
                "evidence_level": "falsified",
                "blocking_issues": ["unknown_listing_status", "is_st"],
                "evidence_gaps": [],
                "tool_trace": [],
            },
        )

        r = self.client.post(
            f"/api/research/candidates/{candidate_id}/confirm",
            json={
                "approval_card_id": self._approval_for(theme_id),
                "confirmation_reason": "test", "evidence_level": "medium",
                "confirmed_by": "user", "pool_snapshot_date": date.today().isoformat(),
                "thesis_snapshot": "test", "invalidation_rules": [],
                "price_snapshot": {}, "benchmark_snapshot": {},
                "evidence_snapshot_ids": [snap_id],
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("blocking", r.json()["detail"].lower())

    # ------------------------------------------------------------------
    # Test 5: LLM-fabricated facts cannot enter snapshot
    # ------------------------------------------------------------------

    def test_fabricated_data_rejected_by_fact_check(self):
        """Evidence with source_record_id pointing to non-existent row is rejected."""
        # This tests that the _verify_facts mechanism works at the orchestrator level
        # We test via the FakeLLM's output containing a fabricated source_record_id
        from backend.services.data_tools import DataToolsService
        from backend.services.evidence_agent import EvidenceAgentOrchestrator
        from tests.test_evidence_agent import FakeLLMClient, json_dumps

        dt = DataToolsService(tushare_client=FakeTushareClient(
            TushareConfig(token="fake", api_url="http://fake.test")
        ))

        # LLM fabricates a reference to a non-existent row
        fake_response = json_dumps({
            "evidence_items": [
                {
                    "source_record_id": "financials:999",
                    "description": "营收持续增长",
                    "supports": ["t1"], "falsifies": [], "conflicts": [],
                }
            ],
            "summary": "fake",
        })

        llm = FakeLLMClient(response_text=fake_response)
        orch = EvidenceAgentOrchestrator(dt, llm)
        _, audit, items = orch.run_evidence_agent(
            symbol="300750.SZ", verification_id="v", snapshot_date="20260624",
        )
        self.assertEqual(len(items), 0)
        self.assertTrue(
            any("row index 999 out of range" in e for e in audit.errors),
            f"Expected fact rejection, got: {audit.errors}",
        )

    # ------------------------------------------------------------------
    # Test 6: Snapshot verification_id mismatch rejected
    # ------------------------------------------------------------------

    def test_snapshot_verification_id_mismatch_rejected(self):
        """Snapshot with mismatched verification_id cannot confirm."""
        theme_id = self._create_theme()
        candidate_id, verification_id = self._add_candidate(theme_id, "300750.SZ", "宁德时代")

        # Store snapshot with different verification_id
        wrong_vid = "verify_wrong_symbol"
        snap_id = "snap_mismatch_verification"
        self._store_snapshot(
            candidate_id, wrong_vid, "300750.SZ",
            evidence_output={"evidence_level": "medium", "blocking_issues": []},
            snap_id=snap_id,
        )

        r = self.client.post(
            f"/api/research/candidates/{candidate_id}/confirm",
            json={
                "approval_card_id": self._approval_for(theme_id),
                "confirmation_reason": "test", "evidence_level": "medium",
                "confirmed_by": "user", "pool_snapshot_date": date.today().isoformat(),
                "thesis_snapshot": "test", "invalidation_rules": [],
                "price_snapshot": {}, "benchmark_snapshot": {},
                "evidence_snapshot_ids": [snap_id],
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("verification_id", r.json()["detail"].lower())

    # ------------------------------------------------------------------
    # Test 7: Snapshot hash integrity check
    # ------------------------------------------------------------------

    def test_snapshot_hash_integrity_check(self):
        """Tampered snapshot hash triggers integrity failure."""
        theme_id = self._create_theme()
        candidate_id, verification_id = self._add_candidate(theme_id, "300750.SZ", "宁德时代")

        snap_id = "snap_tampered_hash"
        self.db.store_evidence_snapshot(
            snapshot_id=snap_id,
            candidate_id=candidate_id,
            verification_id=verification_id,
            snapshot_date="20260624",
            symbol="300750.SZ",
            evidence_output={"evidence_level": "medium", "blocking_issues": []},
            packet_input_hash="tampered_hash_value",  # wrong hash
            tool_result_hash="",
            packet_data='{"symbol": "300750.SZ"}',  # correct data → hash mismatch
        )

        r = self.client.post(
            f"/api/research/candidates/{candidate_id}/confirm",
            json={
                "approval_card_id": self._approval_for(theme_id),
                "confirmation_reason": "test", "evidence_level": "medium",
                "confirmed_by": "user", "pool_snapshot_date": date.today().isoformat(),
                "thesis_snapshot": "test", "invalidation_rules": [],
                "price_snapshot": {}, "benchmark_snapshot": {},
                "evidence_snapshot_ids": [snap_id],
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("hash", r.json()["detail"].lower())

    # ------------------------------------------------------------------
    # Test 8: Confirmed pool frozen — thesis/evidence/etc. immutable
    # ------------------------------------------------------------------

    def test_confirmed_pool_fields_frozen_after_confirmation(self):
        """After confirmation, thesis, invalidation_rules, evidence_snapshot_ids are stored."""
        theme_id = self._create_theme("Frozen Pool")
        candidate_id, verification_id = self._add_candidate(theme_id, "600519.SH", "贵州茅台")

        snap_id = self._store_snapshot(
            candidate_id, verification_id, "600519.SH",
            evidence_output={"evidence_level": "strong", "blocking_issues": []},
        )

        self.client.post(
            f"/api/research/candidates/{candidate_id}/confirm",
            json={
                "approval_card_id": self._approval_for(theme_id),
                "confirmation_reason": "长期基本面优良", "evidence_level": "strong",
                "confirmed_by": "user_vflow", "pool_snapshot_date": "2026-06-24",
                "thesis_snapshot": "高端白酒龙头，品牌壁垒深厚",
                "invalidation_rules": [
                    {"type": "policy_risk", "note": "消费税大幅调整"},
                ],
                "price_snapshot": {"close": 2000.0, "volume": 5000000},
                "benchmark_snapshot": {
                    "benchmark_type": "index", "benchmark_code": "000001.SH",
                    "snapshot_value": 3300.0,
                },
                "evidence_snapshot_ids": [snap_id],
                "primary_evidence_snapshot_id": snap_id,
            },
        )

        confirmations = self.client.get(
            f"/api/research/themes/{theme_id}/confirmed-candidates",
        ).json()
        self.assertEqual(len(confirmations), 1)

        c = confirmations[0]
        self.assertEqual(c["thesis_snapshot"], "高端白酒龙头，品牌壁垒深厚")
        self.assertEqual(len(c["invalidation_rules"]), 1)
        self.assertEqual(c["invalidation_rules"][0]["type"], "policy_risk")
        self.assertEqual(c["price_snapshot"]["close"], 2000.0)
        self.assertEqual(c["benchmark_snapshot"]["benchmark_code"], "000001.SH")
        self.assertEqual(c["benchmark_snapshot"]["snapshot_value"], 3300.0)
        self.assertEqual(c["pool_snapshot_date"], "2026-06-24")
        self.assertIn(snap_id, c["evidence_snapshot_ids"])
        self.assertEqual(c["primary_evidence_snapshot_id"], snap_id)
        self.assertTrue(c["forward_only"])

    # ------------------------------------------------------------------
    # Test 9: Multi-version snapshots retained
    # ------------------------------------------------------------------

    def test_multiple_snapshots_retained(self):
        """Multiple evidence snapshots can exist for a candidate."""
        theme_id = self._create_theme("Multi Snap")
        candidate_id, verification_id = self._add_candidate(theme_id, "300750.SZ", "宁德时代")

        snap1 = self._store_snapshot(
            candidate_id, verification_id, "300750.SZ",
            evidence_output={"evidence_level": "weak", "blocking_issues": ["unknown_liquidity"]},
            snap_id="snap_v1",
        )
        snap2 = self._store_snapshot(
            candidate_id, verification_id, "300750.SZ",
            evidence_output={"evidence_level": "medium", "blocking_issues": []},
            snap_id="snap_v2",
        )

        snaps = self.db.get_evidence_snapshots_for_candidate(candidate_id)
        self.assertGreaterEqual(len(snaps), 2)
        snap_ids = [s["snapshot_id"] for s in snaps]
        self.assertIn(snap1, snap_ids)
        self.assertIn(snap2, snap_ids)

        # Confirm with v2 (clean)
        self.client.post(
            f"/api/research/candidates/{candidate_id}/confirm",
            json={
                "approval_card_id": self._approval_for(theme_id),
                "confirmation_reason": "updated evidence", "evidence_level": "medium",
                "confirmed_by": "user", "pool_snapshot_date": date.today().isoformat(),
                "thesis_snapshot": "test", "invalidation_rules": [],
                "price_snapshot": {}, "benchmark_snapshot": {},
                "evidence_snapshot_ids": [snap2],
            },
        )
        conf = self.db.list_confirmed_candidates(theme_id)[0]
        self.assertIn(snap2, conf.evidence_snapshot_ids)


if __name__ == "__main__":
    unittest.main()
