"""
测试 counter_evidence source_record_id 的严格格式校验。

要求：
1. 格式必须为 tool:symbol:index
2. tool 必须属于已注册的数据工具白名单
3. symbol 必须严格等于当前候选 symbol
4. index 必须是非负整数
5. 仍需检查 ID 存在于 context，且来源不是 weak
6. description 去除空格后不能为空
"""

import unittest
from datetime import datetime

from contracts.research import (
    ResearchSource,
    CounterEvidence,
)
from backend.services.serenity_agent import (
    VerifiedResearchCandidate,
    SerenityRunContext,
    SerenityAgentAudit,
)
from backend.services.serenity_synthesizer import ResearchSynthesizer


class TestCounterEvidenceStrictValidation(unittest.TestCase):
    """测试 counter_evidence source_record_id 严格格式校验。"""

    def setUp(self):
        """设置测试环境。"""
        self.synthesizer = ResearchSynthesizer(llm_client=None)
        self.now = datetime.now()

    def _make_context(
        self,
        symbol: str,
        company_name: str,
        sources: list[ResearchSource]
    ) -> SerenityRunContext:
        """构造测试用 SerenityRunContext。"""
        candidate = VerifiedResearchCandidate(
            symbol=symbol,
            company_name=company_name,
            confidence="high",
            verification_id="test",
            exchange="SZ",
            listing_status="active",
            supporting_source_ids=[],
            falsification_questions=[],
            counter_evidence=[],
            data_gaps=[],
        )

        sources_by_id = {s.source_record_id: s for s in sources}

        context = SerenityRunContext()
        context.theme_keywords = ["锂电池", "电池"]
        context.verified_candidates_by_symbol = {symbol: candidate}
        context.sources_by_id = sources_by_id

        return context

    def test_invalid_tool_name_rejected(self):
        """测试：fake:300750.SZ:0 → 拒绝（工具名不在白名单）"""
        sources = [
            ResearchSource(
                source_record_id="fake:300750.SZ:0",
                source_type="financial_report",
                source_quality="first_hand",
                title="假数据",
                summary="测试",
                retrieved_at=self.now,
            )
        ]
        context = self._make_context("300750.SZ", "宁德时代", sources)
        audit = SerenityAgentAudit()

        synthesis_dict = {
            "candidate_rationales": {
                "300750.SZ": {
                    "counter_evidence": [
                        {
                            "description": "反证内容",
                            "source_record_id": "fake:300750.SZ:0"
                        }
                    ]
                }
            }
        }

        self.synthesizer._bind_red_team_results(synthesis_dict, context, audit)

        candidate = context.verified_candidates_by_symbol["300750.SZ"]
        self.assertEqual(len(candidate.counter_evidence), 0)
        self.assertIn("invalid tool 'fake'", "\n".join(audit.errors))

    def test_malformed_format_two_parts_rejected(self):
        """测试：fake:300750.SZ → 拒绝（格式不是三部分）"""
        sources = []
        context = self._make_context("300750.SZ", "宁德时代", sources)
        audit = SerenityAgentAudit()

        synthesis_dict = {
            "candidate_rationales": {
                "300750.SZ": {
                    "counter_evidence": [
                        {
                            "description": "反证内容",
                            "source_record_id": "fake:300750.SZ"
                        }
                    ]
                }
            }
        }

        self.synthesizer._bind_red_team_results(synthesis_dict, context, audit)

        candidate = context.verified_candidates_by_symbol["300750.SZ"]
        self.assertEqual(len(candidate.counter_evidence), 0)
        self.assertIn("malformed (expected format: tool:symbol:index)", "\n".join(audit.errors))

    def test_non_integer_index_rejected(self):
        """测试：financials:300750.SZ:x → 拒绝（index 不是整数）"""
        sources = [
            ResearchSource(
                source_record_id="financials:300750.SZ:x",
                source_type="financial_report",
                source_quality="first_hand",
                title="财报",
                summary="测试",
                retrieved_at=self.now,
            )
        ]
        context = self._make_context("300750.SZ", "宁德时代", sources)
        audit = SerenityAgentAudit()

        synthesis_dict = {
            "candidate_rationales": {
                "300750.SZ": {
                    "counter_evidence": [
                        {
                            "description": "反证内容",
                            "source_record_id": "financials:300750.SZ:x"
                        }
                    ]
                }
            }
        }

        self.synthesizer._bind_red_team_results(synthesis_dict, context, audit)

        candidate = context.verified_candidates_by_symbol["300750.SZ"]
        self.assertEqual(len(candidate.counter_evidence), 0)
        self.assertIn("invalid index 'x'", "\n".join(audit.errors))

    def test_wrong_symbol_rejected(self):
        """测试：financials:002594.SZ:0 → 拒绝（symbol 不匹配当前候选）"""
        sources = [
            ResearchSource(
                source_record_id="financials:002594.SZ:0",
                source_type="financial_report",
                source_quality="first_hand",
                title="比亚迪财报",
                summary="测试",
                retrieved_at=self.now,
            )
        ]
        context = self._make_context("300750.SZ", "宁德时代", sources)
        audit = SerenityAgentAudit()

        synthesis_dict = {
            "candidate_rationales": {
                "300750.SZ": {
                    "counter_evidence": [
                        {
                            "description": "反证内容",
                            "source_record_id": "financials:002594.SZ:0"
                        }
                    ]
                }
            }
        }

        self.synthesizer._bind_red_team_results(synthesis_dict, context, audit)

        candidate = context.verified_candidates_by_symbol["300750.SZ"]
        self.assertEqual(len(candidate.counter_evidence), 0)
        self.assertIn("belongs to 002594.SZ, not 300750.SZ", "\n".join(audit.errors))

    def test_empty_description_rejected(self):
        """测试：空 description → 拒绝"""
        sources = [
            ResearchSource(
                source_record_id="financials:300750.SZ:0",
                source_type="financial_report",
                source_quality="first_hand",
                title="财报",
                summary="测试",
                retrieved_at=self.now,
            )
        ]
        context = self._make_context("300750.SZ", "宁德时代", sources)
        audit = SerenityAgentAudit()

        synthesis_dict = {
            "candidate_rationales": {
                "300750.SZ": {
                    "counter_evidence": [
                        {
                            "description": "   ",  # 只有空格
                            "source_record_id": "financials:300750.SZ:0"
                        }
                    ]
                }
            }
        }

        self.synthesizer._bind_red_team_results(synthesis_dict, context, audit)

        candidate = context.verified_candidates_by_symbol["300750.SZ"]
        self.assertEqual(len(candidate.counter_evidence), 0)
        self.assertIn("missing description", "\n".join(audit.errors))

    def test_valid_counter_evidence_json_roundtrip(self):
        """测试：合法 CounterEvidence JSON 往返保持两个字段"""
        sources = [
            ResearchSource(
                source_record_id="financials:300750.SZ:0",
                source_type="financial_report",
                source_quality="first_hand",
                title="财报",
                summary="测试",
                retrieved_at=self.now,
            )
        ]
        context = self._make_context("300750.SZ", "宁德时代", sources)
        audit = SerenityAgentAudit()

        synthesis_dict = {
            "candidate_rationales": {
                "300750.SZ": {
                    "counter_evidence": [
                        {
                            "description": "产能利用率低于预期",
                            "source_record_id": "financials:300750.SZ:0"
                        }
                    ]
                }
            }
        }

        self.synthesizer._bind_red_team_results(synthesis_dict, context, audit)

        candidate = context.verified_candidates_by_symbol["300750.SZ"]
        self.assertEqual(len(candidate.counter_evidence), 1)
        self.assertEqual(len(audit.errors), 0)

        ce = candidate.counter_evidence[0]
        self.assertIsInstance(ce, CounterEvidence)
        self.assertEqual(ce.description, "产能利用率低于预期")
        self.assertEqual(ce.source_record_id, "financials:300750.SZ:0")

        # JSON 往返测试
        import json
        ce_json = ce.model_dump()
        self.assertEqual(set(ce_json.keys()), {"description", "source_record_id"})
        ce_restored = CounterEvidence(**ce_json)
        self.assertEqual(ce_restored.description, "产能利用率低于预期")
        self.assertEqual(ce_restored.source_record_id, "financials:300750.SZ:0")

    def test_valid_counter_evidence_passes(self):
        """测试：合法来源正常通过"""
        sources = [
            ResearchSource(
                source_record_id="announcements:300750.SZ:1",
                source_type="announcement",
                source_quality="first_hand",
                title="公告",
                summary="扩产计划延期",
                retrieved_at=self.now,
            )
        ]
        context = self._make_context("300750.SZ", "宁德时代", sources)
        audit = SerenityAgentAudit()

        synthesis_dict = {
            "candidate_rationales": {
                "300750.SZ": {
                    "counter_evidence": [
                        {
                            "description": "扩产计划延期至明年",
                            "source_record_id": "announcements:300750.SZ:1"
                        }
                    ]
                }
            }
        }

        self.synthesizer._bind_red_team_results(synthesis_dict, context, audit)

        candidate = context.verified_candidates_by_symbol["300750.SZ"]
        self.assertEqual(len(candidate.counter_evidence), 1)
        self.assertEqual(len(audit.errors), 0)

        ce = candidate.counter_evidence[0]
        self.assertEqual(ce.description, "扩产计划延期至明年")
        self.assertEqual(ce.source_record_id, "announcements:300750.SZ:1")

    def test_source_not_in_context_rejected(self):
        """测试：source_record_id 不存在于 context → 拒绝"""
        sources = []  # 空来源列表
        context = self._make_context("300750.SZ", "宁德时代", sources)
        audit = SerenityAgentAudit()

        synthesis_dict = {
            "candidate_rationales": {
                "300750.SZ": {
                    "counter_evidence": [
                        {
                            "description": "反证内容",
                            "source_record_id": "financials:300750.SZ:0"
                        }
                    ]
                }
            }
        }

        self.synthesizer._bind_red_team_results(synthesis_dict, context, audit)

        candidate = context.verified_candidates_by_symbol["300750.SZ"]
        self.assertEqual(len(candidate.counter_evidence), 0)
        self.assertIn("not found in context", "\n".join(audit.errors))

    def test_weak_source_rejected(self):
        """测试：source_quality == weak → 拒绝"""
        sources = [
            ResearchSource(
                source_record_id="financials:300750.SZ:0",
                source_type="financial_report",
                source_quality="weak",
                title="低质量财报",
                summary="测试",
                retrieved_at=self.now,
            )
        ]
        context = self._make_context("300750.SZ", "宁德时代", sources)
        audit = SerenityAgentAudit()

        synthesis_dict = {
            "candidate_rationales": {
                "300750.SZ": {
                    "counter_evidence": [
                        {
                            "description": "反证内容",
                            "source_record_id": "financials:300750.SZ:0"
                        }
                    ]
                }
            }
        }

        self.synthesizer._bind_red_team_results(synthesis_dict, context, audit)

        candidate = context.verified_candidates_by_symbol["300750.SZ"]
        self.assertEqual(len(candidate.counter_evidence), 0)
        self.assertIn("is weak", "\n".join(audit.errors))


if __name__ == "__main__":
    unittest.main()
