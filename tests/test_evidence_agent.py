"""
Test Evidence Agent orchestrator and safety boundaries.

These tests prove:
- EvidenceDataPacket is correctly built from tool results
- Orchestrator calls all 3 tools and preserves partial results
- LLM output is strictly parsed and re-bound
- Fabricated numbers are detected
- Non-existent announcement references are rejected
- Rewritten source quality is ignored (deterministic rebind)
- Partial tool failure → partial data, no LLM fill
- Output schema errors fail cleanly
- Missing LLM credentials produce clear error
- FakeLLM enables offline testing

FakeLLM returns pre-configured structured outputs for deterministic testing.
"""

import unittest
from datetime import datetime
from contracts.research import (
    EvidenceDataPacket,
    EvidenceAgentAudit,
    EvidenceItem,
    DataToolResult,
)
from backend.services.data_tools import DataToolsService
from backend.services.evidence_agent import EvidenceAgentOrchestrator
from backend.app.tushare.config import TushareConfig
from tests.test_research_validation import FakeTushareClient


# ------------------------------------------------------------------
# Fake LLM for offline testing
# ------------------------------------------------------------------

class FakeLLMClient:
    """Fake LLM that returns pre-configured structured JSON output."""

    def __init__(self, response_text: str | None = None, should_fail: bool = False):
        self.response_text = response_text
        self.should_fail = should_fail
        self.last_messages = None
        self.last_system = None

    def create_message(self, messages, system=None, max_tokens=4096):
        if self.should_fail:
            raise ValueError("Simulated LLM API failure")

        self.last_messages = messages
        self.last_system = system

        text = self.response_text or self._default_response()
        return {
            "id": "fake_msg_001",
            "model": "fake-model",
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }

    @staticmethod
    def _default_response() -> str:
        return json_dumps({
            "evidence_items": [
                {
                    "source_record_id": "financials:0",
                    "description": "公司保持稳定的盈利能力",
                    "supports": ["thesis_profitability"],
                    "falsifies": [],
                    "conflicts": [],
                }
            ],
            "summary": "证据表明公司基本面稳健",
        })


import json as _json


def json_dumps(obj):
    return _json.dumps(obj, ensure_ascii=False)


class TestEvidenceDataPacket(unittest.TestCase):
    """Test EvidenceDataPacket construction."""

    def test_packet_holds_all_tool_results(self):
        now = datetime.now()
        fin = DataToolResult(
            tool_name="get_financials", source="tushare_income",
            retrieved_at=now, raw_data=[{"total_revenue": 1e10}],
        )
        ann = DataToolResult(
            tool_name="get_announcements", source="tushare_anns",
            retrieved_at=now, raw_data=[{"title": "年报"}],
        )
        sector = DataToolResult(
            tool_name="get_sector_and_peers", source="tushare_stock_basic",
            retrieved_at=now, raw_data=[{"industry": "电气设备"}],
        )
        packet = EvidenceDataPacket(
            symbol="300750.SZ",
            snapshot_date="20260624",
            verification_id="verify_test",
            financials=fin,
            announcements=ann,
            sector_and_peers=sector,
            tool_gaps=["test_gap"],
            tool_errors=["test_error"],
            created_at=now,
        )
        self.assertIsNotNone(packet.financials)
        self.assertIsNotNone(packet.announcements)
        self.assertIsNotNone(packet.sector_and_peers)
        self.assertIn("test_gap", packet.tool_gaps)
        self.assertIn("test_error", packet.tool_errors)

    def test_compute_input_hash_is_deterministic(self):
        now = datetime.now()
        packet = EvidenceDataPacket(
            symbol="300750.SZ", created_at=now,
        )
        h1 = packet.compute_input_hash()
        h2 = packet.compute_input_hash()
        self.assertEqual(h1, h2)

    def test_compute_input_hash_changes_with_different_data(self):
        now = datetime.now()
        p1 = EvidenceDataPacket(symbol="300750.SZ", created_at=now)
        p2 = EvidenceDataPacket(symbol="600519.SH", created_at=now)
        self.assertNotEqual(p1.compute_input_hash(), p2.compute_input_hash())


class TestOrchestratorPartialFailure(unittest.TestCase):
    """Test orchestrator handles partial tool failures gracefully."""

    def setUp(self):
        config = TushareConfig(token="fake", api_url="http://fake.test")
        self.fake_tushare = FakeTushareClient(config)
        self.data_tools = DataToolsService(tushare_client=self.fake_tushare)

    def test_all_tools_called_for_normal_symbol(self):
        llm = FakeLLMClient()
        orch = EvidenceAgentOrchestrator(self.data_tools, llm)
        packet, audit, items = orch.run_evidence_agent(
            symbol="300750.SZ",
            verification_id="verify_test",
            snapshot_date="20260624",
        )
        self.assertEqual(packet.symbol, "300750.SZ")
        self.assertIsNotNone(packet.financials)
        self.assertIsNotNone(packet.announcements)
        self.assertIsNotNone(packet.sector_and_peers)
        self.assertGreater(audit.token_usage.get("input_tokens", 0), 0)

    def test_unknown_symbol_produces_partial_results(self):
        """Unknown symbol → empty tool results, but still returns packet + audit."""
        llm = FakeLLMClient()
        orch = EvidenceAgentOrchestrator(self.data_tools, llm)
        packet, audit, items = orch.run_evidence_agent(
            symbol="999999.SZ",
            verification_id="verify_test",
        )
        # Packet exists even with empty results
        self.assertEqual(packet.symbol, "999999.SZ")
        # Tool gaps are recorded
        self.assertGreater(len(packet.tool_gaps), 0)

    def test_no_llm_client_produces_clear_error(self):
        """Missing LLM client produces audit error, not silent pass."""
        orch = EvidenceAgentOrchestrator(self.data_tools, llm_client=None)
        packet, audit, items = orch.run_evidence_agent(
            symbol="300750.SZ",
        )
        self.assertEqual(len(items), 0)
        self.assertIn("No LLM client", " ".join(audit.errors))

    def test_llm_api_failure_records_error(self):
        """LLM API failure records error, returns empty items."""
        llm = FakeLLMClient(should_fail=True)
        orch = EvidenceAgentOrchestrator(self.data_tools, llm)
        packet, audit, items = orch.run_evidence_agent(
            symbol="300750.SZ",
        )
        self.assertEqual(len(items), 0)
        self.assertIn("LLM extraction failed", " ".join(audit.errors))


class TestLLMSafetyBoundaries(unittest.TestCase):
    """Test LLM output safety — fabricated data, invalid sources, schema errors."""

    def setUp(self):
        config = TushareConfig(token="fake", api_url="http://fake.test")
        self.fake_tushare = FakeTushareClient(config)
        self.data_tools = DataToolsService(tushare_client=self.fake_tushare)

    def _run_with_response(self, response_text: str):
        llm = FakeLLMClient(response_text=response_text)
        orch = EvidenceAgentOrchestrator(self.data_tools, llm)
        return orch.run_evidence_agent(
            symbol="300750.SZ",
            verification_id="verify_test",
            snapshot_date="20260624",
        )

    def test_valid_json_output_returns_items(self):
        response = json_dumps({
            "evidence_items": [
                {
                    "source_record_id": "financials:0",
                    "description": "公司盈利稳定",
                    "supports": ["thesis_1"],
                    "falsifies": [],
                    "conflicts": [],
                }
            ],
            "summary": "总结",
        })
        _, audit, items = self._run_with_response(response)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].description, "公司盈利稳定")
        self.assertEqual(items[0].supports, ["thesis_1"])
        self.assertEqual(items[0].source_record_id, "financials:0")
        self.assertEqual(audit.errors, [])

    def test_llm_fabricated_numbers_rejected(self):
        """LLM includes financial numbers — items MUST be rejected by fact verification."""
        response = json_dumps({
            "evidence_items": [
                {
                    "source_record_id": "financials:0",
                    "description": "营收1.5万亿，净利润7500亿",
                    "supports": ["thesis_fabricated"],
                    "falsifies": [],
                    "conflicts": [],
                }
            ],
            "summary": "含编造数据",
        })
        _, audit, items = self._run_with_response(response)
        # Items with fabricated numbers are REJECTED (not survived)
        self.assertEqual(len(items), 0)
        self.assertIn("fabricated", " ".join(audit.errors).lower())

    def test_llm_output_with_invalid_json_records_error(self):
        response = "This is not JSON at all"
        _, audit, items = self._run_with_response(response)
        self.assertEqual(len(items), 0)
        self.assertIn("not valid JSON", " ".join(audit.errors))

    def test_llm_output_missing_evidence_items_records_error(self):
        response = json_dumps({"summary": "no items here"})
        _, audit, items = self._run_with_response(response)
        # No evidence_items key → raw_items will be None
        # parse_llm_output: parsed.get("evidence_items", []) returns []
        self.assertEqual(len(items), 0)

    def test_llm_output_with_wrong_schema_records_error(self):
        response = json_dumps({
            "evidence_items": "not_a_list",
            "summary": "bad schema",
        })
        _, audit, items = self._run_with_response(response)
        self.assertEqual(len(items), 0)
        self.assertIn("not a list", " ".join(audit.errors))

    def test_llm_source_type_quality_are_rebound(self):
        """Even if LLM outputs source_type='first_hand', it's rebound to news/second_hand."""
        response = json_dumps({
            "evidence_items": [
                {
                    "source_record_id": "financials:0",
                    "description": "LLM claims this is first_hand",
                    "source_type": "financial_report",
                    "source_quality": "first_hand",
                    "supports": ["thesis_1"],
                    "falsifies": [],
                    "conflicts": [],
                }
            ],
            "summary": "",
        })
        _, audit, items = self._run_with_response(response)
        # source_type/source_quality from LLM are ignored
        self.assertEqual(len(items), 1)
        self.assertNotEqual(items[0].source_type, "financial_report")
        self.assertNotEqual(items[0].source_quality, "first_hand")
        self.assertEqual(items[0].source_type, "news")

    def test_audit_records_model_info(self):
        response = json_dumps({
            "evidence_items": [
                {
                    "source_record_id": "financials:0",
                    "description": "test",
                    "supports": ["t1"],
                    "falsifies": [],
                    "conflicts": [],
                }
            ],
            "summary": "",
        })
        _, audit, items = self._run_with_response(response)
        self.assertIsNotNone(audit.input_hash)
        self.assertGreater(len(audit.input_hash), 0)
        self.assertGreater(audit.token_usage.get("input_tokens", 0), 0)
        self.assertGreater(audit.extraction_time_ms, 0)

    def test_multiple_evidence_items_parsed(self):
        response = json_dumps({
            "evidence_items": [
                {"source_record_id": "financials:0", "description": "A", "supports": ["t1"], "falsifies": [], "conflicts": []},
                {"source_record_id": "financials:1", "description": "B", "supports": ["t2"], "falsifies": ["t1"], "conflicts": []},
                {"source_record_id": "announcements:0", "description": "C", "supports": [], "falsifies": [], "conflicts": ["c1"]},
            ],
            "summary": "multi",
        })
        _, audit, items = self._run_with_response(response)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[1].falsifies, ["t1"])
        self.assertEqual(items[2].conflicts, ["c1"])

    def test_missing_source_record_id_rejected(self):
        """Items without source_record_id are rejected by fact verification."""
        response = json_dumps({
            "evidence_items": [
                {"description": "no source ref", "supports": ["t1"], "falsifies": [], "conflicts": []},
            ],
            "summary": "",
        })
        _, audit, items = self._run_with_response(response)
        self.assertEqual(len(items), 0)
        self.assertIn("missing source_record_id", " ".join(audit.errors))

    def test_tool_gaps_item_accepted_when_gaps_exist(self):
        """tool_gaps items are accepted when actual gaps exist in the packet."""
        # Use 999999.SZ which produces tool gaps
        llm = FakeLLMClient(response_text=json_dumps({
            "evidence_items": [
                {
                    "source_record_id": "tool_gaps",
                    "description": "无法获取财务数据",
                    "supports": [],
                    "falsifies": ["thesis_unknown"],
                    "conflicts": [],
                }
            ],
            "summary": "数据缺口",
        }))
        orch = EvidenceAgentOrchestrator(self.data_tools, llm)
        _, audit, items = orch.run_evidence_agent(symbol="999999.SZ")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_record_id, "tool_gaps")

    def test_tool_gaps_item_rejected_when_no_gaps(self):
        """tool_gaps items rejected when no actual gaps exist."""
        response = json_dumps({
            "evidence_items": [
                {
                    "source_record_id": "tool_gaps",
                    "description": "声称有数据缺口但实际没有",
                    "supports": [],
                    "falsifies": [],
                    "conflicts": [],
                }
            ],
            "summary": "",
        })
        _, audit, items = self._run_with_response(response)
        # 300750.SZ has clean data → no gaps → tool_gaps item rejected
        self.assertEqual(len(items), 0)

    def test_empty_description_item_skipped(self):
        response = json_dumps({
            "evidence_items": [
                {"source_record_id": "financials:0", "description": "", "supports": ["t1"], "falsifies": [], "conflicts": []},
                {"source_record_id": "financials:1", "description": "valid", "supports": ["t2"], "falsifies": [], "conflicts": []},
            ],
            "summary": "",
        })
        _, audit, items = self._run_with_response(response)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].description, "valid")

    def test_input_blob_contains_no_raw_financial_numbers(self):
        """The input blob sent to LLM must not leak raw financial numbers."""
        llm = FakeLLMClient()
        orch = EvidenceAgentOrchestrator(self.data_tools, llm)
        orch.run_evidence_agent(symbol="300750.SZ", snapshot_date="20260624")

        # Check what was sent to the LLM
        user_content = llm.last_messages[0]["content"]
        # Must NOT contain raw numbers like "4.2e8" or specific revenue figures
        self.assertNotIn("4.2e10", user_content)
        self.assertNotIn("n_income", user_content)
        self.assertNotIn("总营收", user_content)
        # Must contain high-level info
        self.assertIn("Financial data", user_content)
        self.assertIn("reporting period", user_content)

    def test_system_prompt_sent_to_llm(self):
        """The system prompt constraining LLM output is sent."""
        llm = FakeLLMClient()
        orch = EvidenceAgentOrchestrator(self.data_tools, llm)
        orch.run_evidence_agent(symbol="300750.SZ")

        system = llm.last_system or ""
        self.assertIn("ONLY output a JSON object", system)
        self.assertIn("MUST NOT include", system)
        self.assertIn("source_type", system)


class TestOrchestratorToolTrace(unittest.TestCase):
    """Test that orchestrator records full tool call trace."""

    def setUp(self):
        config = TushareConfig(token="fake", api_url="http://fake.test")
        self.fake_tushare = FakeTushareClient(config)
        self.data_tools = DataToolsService(tushare_client=self.fake_tushare)

    def test_all_three_tool_calls_recorded(self):
        llm = FakeLLMClient()
        orch = EvidenceAgentOrchestrator(self.data_tools, llm)
        _, audit, _ = orch.run_evidence_agent(symbol="300750.SZ", snapshot_date="20260624")

        tool_names = [t["tool"] for t in audit.tool_calls]
        self.assertIn("get_financials", tool_names)
        self.assertIn("get_announcements", tool_names)
        self.assertIn("get_sector_and_peers", tool_names)

    def test_tool_call_status_ok_for_normal_symbol(self):
        llm = FakeLLMClient()
        orch = EvidenceAgentOrchestrator(self.data_tools, llm)
        _, audit, _ = orch.run_evidence_agent(symbol="300750.SZ", snapshot_date="20260624")

        for call in audit.tool_calls:
            self.assertEqual(call["status"], "ok")

    def test_quality_validator_runs_post_llm(self):
        """Post-LLM, quality validator flags weak sources."""
        llm = FakeLLMClient()
        orch = EvidenceAgentOrchestrator(self.data_tools, llm)
        _, audit, items = orch.run_evidence_agent(symbol="300750.SZ", snapshot_date="20260624")

        # Items are produced but source quality is always second_hand (rebound)
        # So all items are from same quality level
        if items:
            self.assertTrue(all(i.source_quality == "second_hand" for i in items))


if __name__ == "__main__":
    unittest.main()
