"""
Tests for Serenity production entry points (问题 #8).

验证生产入口正确配置：
- 严格配置矩阵（real+two_phase, deterministic+stub, 其他全拒绝）
- conversation_mode 只允许 real/deterministic，其他值立即拒绝
- 禁止注入任意 Mock runner 绕过模式校验
- 通过 TestClient 调用 /run-serenity 验证生产 factory
- 恰好 2 次 LLM 调用
- 至少产生 1 个 raw candidate，验证完整输出结构（verification_id、supporting_source_ids、hard_filter_flags、red-team 字段）
- 验证 factory 生成的 SerenityTools 已连接 DataToolsService
- 验证响应 harness 的 execution_engine 和 llm_provider
"""

import os
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
from fastapi.testclient import TestClient

from backend.db.research import ResearchDB
from backend.api.research import create_research_app
from backend.services.serenity_agent import SerenityAgentRunner
from backend.services.serenity_stub import SerenityStubRunner


class TestConfigurationMatrix(unittest.TestCase):
    """测试：严格配置矩阵."""
    
    def setUp(self):
        os.environ['RESEARCH_LLM_API_KEY'] = 'test-key'
        os.environ['TUSHARE_TOKEN'] = 'test-token'
    
    def tearDown(self):
        for key in ['RESEARCH_LLM_API_KEY', 'TUSHARE_TOKEN']:
            os.environ.pop(key, None)
    
    def test_real_plus_two_phase_allowed(self):
        """real + two_phase 允许."""
        app = create_research_app(
            conversation_mode='real',
            serenity_execution_mode='two_phase'
        )
        self.assertIsNotNone(app)
    
    def test_deterministic_plus_stub_allowed(self):
        """deterministic + stub 允许."""
        app = create_research_app(
            conversation_mode='deterministic',
            serenity_execution_mode='stub'
        )
        self.assertIsNotNone(app)
    
    def test_deterministic_plus_two_phase_rejected(self):
        """deterministic + two_phase 拒绝."""
        with self.assertRaises(ValueError) as cm:
            create_research_app(
                conversation_mode='deterministic',
                serenity_execution_mode='two_phase'
            )
        self.assertIn("deterministic", str(cm.exception).lower())
        self.assertIn("stub", str(cm.exception).lower())
    
    def test_real_plus_stub_rejected(self):
        """real + stub 拒绝."""
        with self.assertRaises(ValueError) as cm:
            create_research_app(
                conversation_mode='real',
                serenity_execution_mode='stub'
            )
        self.assertIn("two_phase", str(cm.exception).lower())
    
    def test_unknown_conversation_mode_rejected(self):
        """未知 conversation_mode 拒绝."""
        with self.assertRaises(ValueError) as cm:
            create_research_app(
                conversation_mode='unknown',
                serenity_execution_mode='stub'
            )
        self.assertIn("conversation_mode", str(cm.exception).lower())
        self.assertIn("unknown", str(cm.exception).lower())


class TestRunnerInjectionValidation(unittest.TestCase):
    """测试：注入 runner 不能绕过模式校验."""
    
    def setUp(self):
        os.environ['RESEARCH_LLM_API_KEY'] = 'test-key'
        os.environ['TUSHARE_TOKEN'] = 'test-token'
    
    def tearDown(self):
        for key in ['RESEARCH_LLM_API_KEY', 'TUSHARE_TOKEN']:
            os.environ.pop(key, None)
    
    def test_real_mode_rejects_injected_stub_runner(self):
        """real 模式拒绝注入的 SerenityStubRunner."""
        stub_runner = SerenityStubRunner()
        
        with self.assertRaises(ValueError) as cm:
            create_research_app(
                conversation_mode='real',
                serenity_execution_mode='two_phase',
                serenity_runner=stub_runner
            )
        self.assertIn("serenityagentrunner", str(cm.exception).lower())
    
    def test_real_mode_rejects_arbitrary_mock_runner(self):
        """real 模式拒绝任意 Mock runner."""
        mock_runner = MagicMock()
        
        with self.assertRaises(ValueError) as cm:
            create_research_app(
                conversation_mode='real',
                serenity_execution_mode='two_phase',
                serenity_runner=mock_runner
            )
        self.assertIn("serenityagentrunner", str(cm.exception).lower())
    
    def test_deterministic_mode_rejects_arbitrary_mock_runner(self):
        """deterministic 模式拒绝任意 Mock runner."""
        mock_runner = MagicMock()
        
        with self.assertRaises(ValueError) as cm:
            create_research_app(
                conversation_mode='deterministic',
                serenity_execution_mode='stub',
                serenity_runner=mock_runner
            )
        self.assertIn("serenitystubrunner", str(cm.exception).lower())


class TestProductionEndToEnd(unittest.TestCase):
    """测试：通过 TestClient 调用 /run-serenity 验证生产 factory."""
    
    def setUp(self):
        os.environ['RESEARCH_LLM_API_KEY'] = 'test-key'
        os.environ['TUSHARE_TOKEN'] = 'test-token'
        self.db = ResearchDB(":memory:")
    
    def tearDown(self):
        for key in ['RESEARCH_LLM_API_KEY', 'TUSHARE_TOKEN']:
            os.environ.pop(key, None)
    
    @patch('backend.services.llm_client.Anthropic')
    @patch('backend.services.research_validation.TushareClient')
    def test_run_serenity_endpoint_with_candidate_pool_verification(self, mock_tushare_cls, mock_anthropic_cls):
        """通过 TestClient 调用 /run-serenity，验证候选池完整性."""
        
        # Track LLM calls
        llm_call_count = [0]
        
        def mock_create_message(**kwargs):
            llm_call_count[0] += 1
            
            # Planner response (first call)
            if llm_call_count[0] == 1:
                return MagicMock(
                    id="msg1",
                    model="claude-sonnet-4",
                    role="assistant",
                    content=[MagicMock(
                        type="text",
                        text='{"keywords": ["电池"], "seed_symbols": ["300750.SZ"], "sectors_to_check": [], "start_date": null, "end_date": null, "falsification_questions": []}'
                    )],
                    stop_reason="end_turn",
                    usage=MagicMock(input_tokens=100, output_tokens=50)
                )
            
            # Synthesizer response (second call)
            return MagicMock(
                id="msg2",
                model="claude-sonnet-4",
                role="assistant",
                content=[MagicMock(
                    type="text",
                    text='{"demand_driver": "电动车需求", "value_chain_layers": [], "suspected_bottleneck_layers": [], "hypothesis_draft": [], "candidate_rationales": {"300750.SZ": {"rationale": "核心供应商", "supporting_source_ids": ["financials:300750.SZ:0"], "falsification_questions": ["产能是否充足"], "counter_evidence": []}}, "evidence_gaps": []}'
                )],
                stop_reason="end_turn",
                usage=MagicMock(input_tokens=200, output_tokens=100)
            )
        
        mock_anthropic_instance = MagicMock()
        mock_anthropic_instance.messages.create = mock_create_message
        mock_anthropic_cls.return_value = mock_anthropic_instance
        
        # Mock Tushare
        import pandas as pd
        mock_tushare_instance = MagicMock()
        
        def mock_query(api_name, **kwargs):
            if api_name == "income":
                return pd.DataFrame([{
                    "ts_code": "300750.SZ",
                    "end_date": "20231231",
                    "ann_date": "20240430",
                    "report_type": "1",
                    "total_revenue": 100000.0,
                    "revenue": 100000.0,
                    "oper_cost": 80000.0,
                    "operate_profit": 15000.0,
                    "total_profit": 14000.0,
                    "n_income": 12000.0,
                    "n_income_attr_p": 11000.0,
                    "basic_eps": 1.2,
                    "diluted_eps": 1.2,
                    "ebit": 15000.0,
                    "ebitda": 16000.0,
                }])
            elif api_name == "stock_basic":
                return pd.DataFrame([{
                    "ts_code": "300750.SZ",
                    "symbol": "300750",
                    "name": "宁德时代",
                    "area": "福建",
                    "industry": "电气设备",
                    "market": "创业板",
                    "list_status": "L",
                    "list_date": "20180612",
                    "delist_date": None,
                }])
            elif api_name == "daily_basic":
                return pd.DataFrame([{
                    "ts_code": "300750.SZ",
                    "trade_date": "20240101",
                    "amount": 5000000.0,
                    "close": 100.0,
                    "turnover_rate": 2.5,
                    "volume_ratio": 1.0,
                    "pe": 30.0,
                    "pb": 5.0,
                }])
            return pd.DataFrame()
        
        mock_tushare_instance.query = mock_query
        mock_tushare_cls.return_value = mock_tushare_instance
        
        # Create app via production factory
        app = create_research_app(
            db=self.db,
            conversation_mode='real',
            serenity_execution_mode='two_phase'
        )
        
        client = TestClient(app)
        
        # Create theme
        theme_response = client.post("/api/research/themes", json={
            "theme_name": "测试主题",
            "background": "测试背景",
            "source_type": "manual_theme"
        })
        self.assertEqual(theme_response.status_code, 200)
        theme_id = theme_response.json()["theme_id"]
        
        # Run Serenity
        serenity_response = client.post(f"/api/research/themes/{theme_id}/run-serenity")
        self.assertEqual(serenity_response.status_code, 200)
        
        # Verify exactly 2 LLM calls (core contract)
        self.assertEqual(llm_call_count[0], 2, "必须恰好 2 次 LLM 调用")
        
        # Get Serenity output to verify structure
        output_response = client.get(f"/api/research/themes/{theme_id}/serenity")
        self.assertEqual(output_response.status_code, 200)
        output = output_response.json()
        
        # Verify harness (proves factory wiring)
        self.assertIn("harness", output)
        harness = output["harness"]
        self.assertEqual(harness["execution_engine"], "two_phase", "execution_engine 必须是 two_phase")
        self.assertIsNotNone(harness.get("llm_provider"), "llm_provider 不能为 None")
        self.assertNotEqual(harness.get("llm_provider"), "unknown", "llm_provider 不能是 unknown")
        
        # Verify output structure (proves complete output contract)
        self.assertIn("candidate_pool_raw", output)
        self.assertIn("candidate_shortlist", output)
        self.assertIn("value_chain_layers", output)
        self.assertIn("evidence_gaps", output)
        
        # A successful production-path run must produce a traceable raw candidate.
        raw_pool = output["candidate_pool_raw"]
        self.assertGreater(len(raw_pool), 0, "生产双阶段链路必须至少产生 1 个 raw candidate")
        first_candidate = raw_pool[0]
        self.assertTrue(first_candidate.get("verification_id"), "候选必须有非空 verification_id")
        self.assertGreater(
            len(first_candidate.get("supporting_source_ids", [])),
            0,
            "候选必须有非空 supporting_source_ids",
        )
        self.assertIsInstance(first_candidate.get("hard_filter_flags"), list, "hard_filter_flags 必须是列表")
        self.assertIsInstance(first_candidate.get("counter_evidence"), list, "counter_evidence 必须是列表")
        self.assertIsInstance(
            first_candidate.get("falsification_questions"),
            list,
            "falsification_questions 必须是列表",
        )
        self.assertIsInstance(first_candidate.get("data_gaps"), list, "data_gaps 必须是列表")
        
        # Verify no trading fields
        self.assertNotIn("buy_signal", output)
        self.assertNotIn("sell_signal", output)
        self.assertNotIn("target_price", output)
        self.assertNotIn("stop_loss", output)


if __name__ == "__main__":
    unittest.main()
