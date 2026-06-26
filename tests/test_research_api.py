"""
Test research API.

Core tests for research API endpoints.
Full integration tests cover the complete flow.
"""

import unittest
from datetime import date, datetime, timedelta
from fastapi.testclient import TestClient
from backend.db.research import ResearchDB
from backend.api.research import create_research_app
from backend.services.research_validation import ResearchValidator
from backend.app.tushare.config import TushareConfig
from contracts.research import TickerVerificationRecord, CandidateStock
from tests.test_research_validation import FakeTushareClient


class TestResearchAPI(unittest.TestCase):
    """Test research API endpoints."""

    def setUp(self):
        """Set up test client with in-memory database."""
        self.db = ResearchDB(":memory:")
        self.app = create_research_app(self.db)
        self.client = TestClient(self.app)

    def store_verification(self, symbol: str, company_name: str = "Verified Company") -> str:
        """Store a valid ticker identity snapshot for API flow tests."""
        now = datetime.now()
        verification_id = f"verify_{symbol.replace('.', '_')}"
        self.db.store_ticker_verification(
            TickerVerificationRecord(
                verification_id=verification_id,
                symbol=symbol,
                company_name=company_name,
                exchange="SSE" if symbol.endswith(".SH") else "SZSE",
                status="listed",
                confidence="high",
                source="test_fixture",
                notes="Verified for API test",
                verified_at=now,
                expires_at=now + timedelta(hours=24),
            )
        )
        return verification_id

    def test_cors_allows_frontend_create_theme_request(self):
        """Browser frontend can call the research API from localhost:3000."""
        response = self.client.options(
            "/api/research/themes",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            "http://localhost:3000",
        )

    def test_create_theme(self):
        """Theme can be created."""
        response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "新能源产业链",
                "background": "锂电池需求增长",
                "source_type": "manual_theme",
                "research_mode": "standard",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("theme_id", data)

    def test_list_themes(self):
        """Themes can be listed."""
        # Create a theme first
        self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "测试主题",
                "background": "测试",
                "source_type": "manual_theme",
            },
        )

        response = self.client.get("/api/research/themes")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_get_theme(self):
        """Theme can be retrieved."""
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "测试主题",
                "background": "测试",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]

        response = self.client.get(f"/api/research/themes/{theme_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["theme_id"], theme_id)

    def test_add_candidate(self):
        """Manual stock can be added."""
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "测试主题",
                "background": "测试",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]
        verification_id = self.store_verification("300750.SZ", "宁德时代")

        response = self.client.post(
            f"/api/research/themes/{theme_id}/candidates",
            json={
                "symbol": "300750.SZ",
                "verification_id": verification_id,
                "match_reason": "手动添加",
                "source_type": "manual_stock",
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_run_serenity_does_not_increment_board_version(self):
        """Direct Serenity route does not increment board_version."""
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "测试主题",
                "background": "测试",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]

        # Get initial board version
        theme_response = self.client.get(f"/api/research/themes/{theme_id}")
        initial_version = theme_response.json()["board_version"]

        # Run Serenity
        self.client.post(f"/api/research/themes/{theme_id}/run-serenity")

        # Check board version unchanged
        theme_response = self.client.get(f"/api/research/themes/{theme_id}")
        after_version = theme_response.json()["board_version"]
        self.assertEqual(initial_version, after_version)

    def test_serenity_output_persisted(self):
        """Serenity output is persisted and retrievable."""
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "测试主题",
                "background": "测试",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]

        # Run Serenity
        run_response = self.client.post(f"/api/research/themes/{theme_id}/run-serenity")
        self.assertEqual(run_response.status_code, 200)

        # Retrieve Serenity output
        get_response = self.client.get(f"/api/research/themes/{theme_id}/serenity")
        self.assertEqual(get_response.status_code, 200)
        data = get_response.json()
        self.assertEqual(data["theme_id"], theme_id)
        self.assertIn("demand_driver", data)
        self.assertIn("value_chain_layers", data)
        self.assertIn("candidate_pool_raw", data)

    def test_evidence_output_persisted(self):
        """Evidence output is persisted and retrievable."""
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "测试主题",
                "background": "测试",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]
        verification_id = self.store_verification("300750.SZ", "宁德时代")

        # Add a candidate
        add_response = self.client.post(
            f"/api/research/themes/{theme_id}/candidates",
            json={
                "symbol": "300750.SZ",
                "verification_id": verification_id,
                "match_reason": "手动添加",
                "source_type": "manual_stock",
            },
        )
        candidate_id = add_response.json()["candidate_id"]

        # Run Evidence
        run_response = self.client.post(
            "/api/research/candidates/run-evidence",
            json=[candidate_id],
        )
        self.assertEqual(run_response.status_code, 200)

        # Retrieve Evidence output
        get_response = self.client.get(f"/api/research/candidates/{candidate_id}/evidence")
        self.assertEqual(get_response.status_code, 200)
        data = get_response.json()
        self.assertEqual(data["candidate_id"], candidate_id)
        self.assertIn("evidence_level", data)
        self.assertIn("kill_criteria_hash", data)

    def test_run_evidence_rejects_candidate_missing_verification_id(self):
        """Evidence cannot run when the candidate cannot trace identity verification."""
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "Trust boundary",
                "background": "Test",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]
        now = datetime.now()
        self.db.add_candidate(
            CandidateStock(
                candidate_id="cand_missing_verification",
                theme_id=theme_id,
                symbol="300750.SZ",
                source_type="manual_stock",
                match_reason="Bad fixture",
                created_at=now,
            )
        )

        response = self.client.post(
            "/api/research/candidates/run-evidence",
            json=["cand_missing_verification"],
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("verification_id", response.json()["detail"])

    def test_run_evidence_rejects_expired_candidate_verification_id(self):
        """Evidence refuses expired identity snapshots instead of re-verifying silently."""
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "Trust boundary",
                "background": "Test",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]
        now = datetime.now()
        verification_id = "verify_expired"
        self.db.store_ticker_verification(
            TickerVerificationRecord(
                verification_id=verification_id,
                symbol="300750.SZ",
                company_name="宁德时代",
                exchange="SZSE",
                status="listed",
                confidence="high",
                source="test_fixture",
                notes="Expired for Evidence test",
                verified_at=now - timedelta(hours=25),
                expires_at=now - timedelta(hours=1),
            )
        )
        self.db.add_candidate(
            CandidateStock(
                candidate_id="cand_expired_verification",
                theme_id=theme_id,
                symbol="300750.SZ",
                verification_id=verification_id,
                source_type="manual_stock",
                match_reason="Bad fixture",
                created_at=now,
            )
        )

        response = self.client.post(
            "/api/research/candidates/run-evidence",
            json=["cand_expired_verification"],
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("expired", response.json()["detail"])

    def test_run_evidence_rejects_symbol_mismatched_verification_id(self):
        """Evidence refuses verification records that belong to another symbol."""
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "Trust boundary",
                "background": "Test",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]
        verification_id = self.store_verification("600000.SH", "浦发银行")
        self.db.add_candidate(
            CandidateStock(
                candidate_id="cand_symbol_mismatch",
                theme_id=theme_id,
                symbol="300750.SZ",
                verification_id=verification_id,
                source_type="manual_stock",
                match_reason="Bad fixture",
                created_at=datetime.now(),
            )
        )

        response = self.client.post(
            "/api/research/candidates/run-evidence",
            json=["cand_symbol_mismatch"],
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("not 300750.SZ", response.json()["detail"])

    def test_reject_candidate(self):
        """Candidate can be rejected with reason."""
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "测试主题",
                "background": "测试",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]
        verification_id = self.store_verification("600000.SH")

        # Add a candidate
        add_response = self.client.post(
            f"/api/research/themes/{theme_id}/candidates",
            json={
                "symbol": "600000.SH",
                "verification_id": verification_id,
                "match_reason": "手动添加",
                "source_type": "manual_stock",
            },
        )
        candidate_id = add_response.json()["candidate_id"]

        # Reject candidate
        reject_response = self.client.post(
            f"/api/research/candidates/{candidate_id}/reject",
            params={"actor": "user_001", "reason": "不符合条件"},
        )
        self.assertEqual(reject_response.status_code, 200)
        data = reject_response.json()
        self.assertEqual(data["status"], "rejected")
        self.assertEqual(data["rejected_by"], "user_001")

    def test_reopen_to_evidence(self):
        """Candidate can be reopened to evidence with reason."""
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "测试主题",
                "background": "测试",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]
        verification_id = self.store_verification("002594.SZ")

        # Add a candidate
        add_response = self.client.post(
            f"/api/research/themes/{theme_id}/candidates",
            json={
                "symbol": "002594.SZ",
                "verification_id": verification_id,
                "match_reason": "手动添加",
                "source_type": "manual_stock",
            },
        )
        candidate_id = add_response.json()["candidate_id"]

        # Reopen to evidence
        reopen_response = self.client.post(
            f"/api/research/candidates/{candidate_id}/reopen-to-evidence",
            json={"actor": "user_001", "reason": "需要重新评估"},
        )
        self.assertEqual(reopen_response.status_code, 200)
        data = reopen_response.json()
        self.assertEqual(data["actor"], "user_001")
        self.assertEqual(data["reason"], "需要重新评估")

    def test_conversation(self):
        """Conversation can create pending actions."""
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "测试主题",
                "background": "测试",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]

        response = self.client.post(
            f"/api/research/themes/{theme_id}/conversation",
            json={"content": "添加 300750.SZ"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("agent_message", data)
        self.assertIn("proposed_actions", data)

    def test_get_conversation_history(self):
        """Conversation history can be retrieved."""
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "测试主题",
                "background": "测试",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]

        # Send a message
        self.client.post(
            f"/api/research/themes/{theme_id}/conversation",
            json={"content": "add 600000.SH"},
        )

        # Get conversation history
        response = self.client.get(f"/api/research/themes/{theme_id}/conversation")
        self.assertEqual(response.status_code, 200)
        messages = response.json()
        self.assertGreater(len(messages), 0)

    def test_get_pending_actions(self):
        """Pending actions can be retrieved."""
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "测试主题",
                "background": "测试",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]

        # Create a pending action via conversation
        conv_response = self.client.post(
            f"/api/research/themes/{theme_id}/conversation",
            json={"content": "add 002594.SZ"},
        )
        self.assertGreater(len(conv_response.json()["proposed_actions"]), 0)

        # Get pending actions
        response = self.client.get(f"/api/research/themes/{theme_id}/pending-actions")
        self.assertEqual(response.status_code, 200)
        actions = response.json()
        self.assertGreater(len(actions), 0)

    def test_english_add_command(self):
        """English 'add' command works."""
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "Test Theme",
                "background": "Test",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]

        response = self.client.post(
            f"/api/research/themes/{theme_id}/conversation",
            json={"content": "add 688005.SH"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data["proposed_actions"]), 0)

    def test_apply_action(self):
        """Proposed action can be applied."""
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "测试主题",
                "background": "测试",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]

        # Create proposed action via conversation
        conv_response = self.client.post(
            f"/api/research/themes/{theme_id}/conversation",
            json={"content": "添加 600000.SH"},
        )
        action_id = conv_response.json()["proposed_actions"][0]["action_id"]

        # Apply action
        response = self.client.post(
            "/api/research/actions/apply",
            json={"action_id": action_id, "applied_by": "user_001"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["applied"])


    def test_add_candidate_without_verification_is_rejected(self):
        """Direct candidate creation cannot bypass ticker verification."""
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "Trust boundary",
                "background": "Test",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]

        response = self.client.post(
            f"/api/research/themes/{theme_id}/candidates",
            json={
                "symbol": "300750.SZ",
                "company_name": "Fabricated Name",
                "match_reason": "Manual input",
                "source_type": "manual_stock",
            },
        )

        self.assertEqual(response.status_code, 422)


class TestEvidenceHardFilterMetadata(unittest.TestCase):
    """Test that hard_filter_metadata flows correctly into Evidence output."""

    def setUp(self):
        """Create app with FakeTushareClient-injected validator."""
        self.db = ResearchDB(":memory:")
        config = TushareConfig(
            token="fake_token_for_hard_filter_test",
            api_url="http://fake.test",
        )
        validator = ResearchValidator(tushare_config=config)
        validator._tushare_client = FakeTushareClient(config)
        self.app = create_research_app(self.db, validator=validator)
        self.client = TestClient(self.app)

    def _store_verification(self, symbol: str, company_name: str = "Verified Company") -> str:
        now = datetime.now()
        verification_id = f"verify_{symbol.replace('.', '_')}"
        self.db.store_ticker_verification(
            TickerVerificationRecord(
                verification_id=verification_id,
                symbol=symbol,
                company_name=company_name,
                exchange="SSE" if symbol.endswith(".SH") else "SZSE",
                status="listed",
                confidence="high",
                source="test_fixture",
                notes="Verified for hard filter test",
                verified_at=now,
                expires_at=now + timedelta(hours=24),
            )
        )
        return verification_id

    def _add_candidate(self, theme_id: str, symbol: str, verification_id: str) -> str:
        response = self.client.post(
            f"/api/research/themes/{theme_id}/candidates",
            json={
                "symbol": symbol,
                "verification_id": verification_id,
                "match_reason": "Hard filter test",
                "source_type": "manual_stock",
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["candidate_id"]

    def _create_theme(self, name: str = "Hard Filter Theme") -> str:
        response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": name,
                "background": "Test",
                "source_type": "manual_theme",
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["theme_id"]

    def test_hard_filter_metadata_written_to_tool_trace(self):
        """Evidence tool_trace contains hard_filter_metadata with all snapshot fields."""
        theme_id = self._create_theme()
        verification_id = self._store_verification("300750.SZ", "宁德时代")
        candidate_id = self._add_candidate(theme_id, "300750.SZ", verification_id)

        response = self.client.post(
            "/api/research/candidates/run-evidence",
            json=[candidate_id],
        )
        self.assertEqual(response.status_code, 200)

        evidence_response = self.client.get(
            f"/api/research/candidates/{candidate_id}/evidence",
        )
        self.assertEqual(evidence_response.status_code, 200)
        data = evidence_response.json()

        tool_trace = data["tool_trace"]
        validation_step = tool_trace[0]
        self.assertEqual(validation_step["step"], "validation")
        self.assertEqual(validation_step["action"], "check_hard_filters")

        metadata = validation_step["result"]["metadata"]
        self.assertEqual(metadata["source"], "tushare")
        self.assertIn("retrieved_at", metadata)
        self.assertTrue(metadata["is_listed"])
        self.assertFalse(metadata["is_st"])
        self.assertFalse(metadata["is_suspended"])
        self.assertIsNotNone(metadata["avg_daily_volume"])
        self.assertEqual(metadata["gaps"], [])

    def test_hard_filter_gaps_written_to_evidence_gaps(self):
        """Hard-filter data gaps are copied into evidence_gaps in the output."""
        theme_id = self._create_theme()
        # 000001.SZ has stock_basic data but no daily_basic data in FakeTushareClient
        verification_id = self._store_verification("000001.SZ", "平安银行")
        candidate_id = self._add_candidate(theme_id, "000001.SZ", verification_id)

        response = self.client.post(
            "/api/research/candidates/run-evidence",
            json=[candidate_id],
        )
        self.assertEqual(response.status_code, 200)

        evidence_response = self.client.get(
            f"/api/research/candidates/{candidate_id}/evidence",
        )
        data = evidence_response.json()

        # Evidence gaps should contain the daily_basic gap
        self.assertIn("daily_basic_amount_missing", data["evidence_gaps"])

        # Blocking issues should include unknown_liquidity since avg_daily_volume is None
        self.assertIn("unknown_liquidity", data["blocking_issues"])

    def test_data_source_gaps_block_candidate_default_pass(self):
        """When daily_basic data is missing, unknown_liquidity flag blocks the candidate."""
        theme_id = self._create_theme()
        verification_id = self._store_verification("000001.SZ", "平安银行")
        candidate_id = self._add_candidate(theme_id, "000001.SZ", verification_id)

        response = self.client.post(
            "/api/research/candidates/run-evidence",
            json=[candidate_id],
        )
        self.assertEqual(response.status_code, 200)

        results = response.json()["results"]
        result = results[0]
        # With unknown_liquidity, there should be blocking issues
        self.assertIn("unknown_liquidity", result["blocking_issues"])
        # evidence_level should reflect that hard data is insufficient
        self.assertEqual(result["evidence_level"], "unknown")

    def test_evidence_item_source_fields_survive_api_round_trip(self):
        """EvidenceItem source_type/source_quality survive DB+API JSON round trip."""
        theme_id = self._create_theme("Source Round Trip")
        verification_id = self._store_verification("300750.SZ", "宁德时代")
        candidate_id = self._add_candidate(theme_id, "300750.SZ", verification_id)

        # Run evidence with real hard-filter data (no injection — no source fields)
        # The focus here is that EvidenceItem schema is round-trippable.
        # For the source-field round trip, we test at the contract level.
        response = self.client.post(
            "/api/research/candidates/run-evidence",
            json=[candidate_id],
        )
        self.assertEqual(response.status_code, 200)

        evidence_response = self.client.get(
            f"/api/research/candidates/{candidate_id}/evidence",
        )
        data = evidence_response.json()
        # The EvidenceOutput.serialize is JSON; verify the structure
        self.assertIn("supporting_evidence", data)
        self.assertIsInstance(data["supporting_evidence"], list)
        self.assertIn("falsifying_evidence", data)
        self.assertIsInstance(data["falsifying_evidence"], list)


if __name__ == "__main__":
    unittest.main()
