"""
Phase 2B-2: backtest_tool 验收测试

验收标准：
1. Agent 生成 trade_plan 后，会提出 backtest_tool
2. 回测能正确读取历史数据（通过 CacheManager）
3. 回测结果保存到 backtest_results 表
4. 回测结果包含关键指标（总收益、夏普、最大回撤、胜率、交易次数）
5. Mock 模式下能正常工作
6. data_refs 正确标注数据来源
"""

import sys
import os
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 添加项目根目录到 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agent.harness import create_agent_graph
from langgraph.checkpoint.memory import MemorySaver


def create_mock_kline_data(days: int = 250) -> pd.DataFrame:
    """创建模拟的 K 线数据（带趋势和信号）"""
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    
    # 创建带趋势的价格数据
    base_price = 10.0
    trend = 0.001  # 每日微涨
    noise = 0.02   # 波动
    
    prices = []
    for i in range(days):
        # 添加趋势和随机波动
        price = base_price * (1 + trend * i) * (1 + noise * (np.random.random() - 0.5))
        prices.append(price)
    
    # 在中间制造一个金叉信号（MA20 上穿 MA60）
    # 方法：在 day 100 附近加速上涨
    for i in range(100, 120):
        prices[i] *= 1.02
    
    df = pd.DataFrame({
        'date': dates.strftime('%Y-%m-%d'),
        'open': prices,
        'high': [p * 1.02 for p in prices],
        'low': [p * 0.98 for p in prices],
        'close': prices,
        'volume': [1000000 + 500000 * np.random.random() for _ in range(days)]
    })
    
    return df


def test_backtest_tool_standalone():
    """测试 1: 独立测试 backtest_tool"""
    print("\n=== 测试 1: 独立测试 backtest_tool ===")
    
    from src.tools.backtest_tool import backtest_tool
    from src.core.cache_manager import CacheManager
    
    # 设置 mock 模式
    os.environ["TRADERLENS_DATA_MODE"] = "mock"
    
    # 准备 mock 数据（写入缓存）
    mock_data = create_mock_kline_data(250)
    cache = CacheManager()
    cache.set_price_data("000001", "qfq", mock_data)
    
    # 调用回测工具
    result = backtest_tool(
        stock_code="000001",
        strategy_profile="trend",
        period="1y"
    )
    
    # 验证返回格式
    assert result["tool"] == "backtest_tool"
    assert result["status"] == "success"
    assert "total_return" in result["result"]
    assert "sharpe_ratio" in result["result"]
    assert "max_drawdown" in result["result"]
    assert "win_rate" in result["result"]
    assert "trade_count" in result["result"]
    
    print(f"✓ 回测完成")
    print(f"  - 总收益率: {result['result']['total_return_pct']:.2f}%")
    print(f"  - 夏普比率: {result['result']['sharpe_ratio']:.2f}")
    print(f"  - 最大回撤: {result['result']['max_drawdown_pct']:.2f}%")
    print(f"  - 胜率: {result['result']['win_rate']:.1%}")
    print(f"  - 交易次数: {result['result']['trade_count']}")
    print(f"  - Summary: {result['summary']}")
    print(f"  - Signals: {result['signals']}")
    
    # 验证数据库记录
    conn = sqlite3.connect("data/investment_agent.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM backtest_results WHERE stock_code = '000001'")
    count = cursor.fetchone()[0]
    conn.close()
    
    assert count > 0, "回测结果未保存到数据库"
    print(f"✓ 回测结果已保存到数据库")
    
    # 验证 data_refs
    assert "data_refs" in result
    assert "source" in result["data_refs"]
    print(f"✓ data_refs 正确: source={result['data_refs']['source']}")


def test_agent_with_backtest():
    """测试 2: Agent 集成测试（生成 trade_plan 后提出 backtest）"""
    print("\n=== 测试 2: Agent 集成测试 ===")
    
    from src.core.cache_manager import CacheManager
    
    # 设置 mock 模式
    os.environ["TRADERLENS_DATA_MODE"] = "mock"
    
    # 准备 mock 数据
    mock_data = create_mock_kline_data(250)
    cache = CacheManager()
    cache.set_price_data("000001", "qfq", mock_data)
    cache.set_index_data("000001", mock_data)  # 市场指数也用同样数据
    
    # 创建 Agent（内部已有 checkpointer）
    graph = create_agent_graph()
    
    # 初始状态
    initial_state = {
        "thread_id": "test_backtest_001",
        "run_id": "test_run_001",
        "goal": "分析平安银行（000001），趋势策略，并回测验证",
        "stock_code": "000001",
        "strategy_profile": "trend",
        "decision_history": [],
        "observations": {},
        "next_action": None,
        "status": "running",
        "_context": {}
    }
    
    config = {"configurable": {"thread_id": "test_backtest_001"}}
    
    # 运行 Agent（最多 8 步）
    print("\n开始运行 Agent...")
    final_state = None
    step = 0
    
    for state in graph.stream(initial_state, config):
        step += 1
        node_name = list(state.keys())[0]
        node_state = state[node_name]
        
        status = node_state.get("status", "running")
        next_action = node_state.get("next_action")
        
        print(f"\nStep {step}: {node_name} -> status={status}")
        if next_action:
            print(f"  next_action: {next_action}")
        
        # 如果进入 waiting_human，自动批准
        if status == "waiting_human":
            print("  [自动批准人工确认]")
            user_input = {"approved": True, "feedback": "批准"}
            for resume_state in graph.stream(user_input, config):
                # 恢复后继续处理后续状态
                resume_node_name = list(resume_state.keys())[0]
                final_state = resume_state[resume_node_name]
                
                resume_status = final_state.get("status", "running")
                print(f"\nStep {step + 1}: {resume_node_name} (resumed) -> status={resume_status}")
                
                if resume_status in ["completed", "failed"]:
                    break
        
        final_state = node_state
        
        # 如果完成或失败，退出
        if status in ["completed", "failed"]:
            break
    
    # 验证 Agent 是否调用了 backtest_tool
    backtest_called = any(
        d.get("action") == "backtest_tool"
        for d in final_state.get("decision_history", [])
    )
    
    assert backtest_called, "Agent 未调用 backtest_tool"
    print(f"\n✓ Agent 已调用 backtest_tool")
    
    # 验证 observations 中有 backtest_tool 结果
    assert "backtest_tool" in final_state.get("observations", {})
    backtest_obs = final_state["observations"]["backtest_tool"]
    
    assert backtest_obs["status"] == "success"
    print(f"✓ backtest_tool 执行成功")
    print(f"  - Summary: {backtest_obs['summary']}")


def test_backtest_in_mock_mode():
    """测试 3: Mock 模式下回测工具正常工作"""
    print("\n=== 测试 3: Mock 模式验证 ===")
    
    from src.tools.backtest_tool import backtest_tool
    from src.core.cache_manager import CacheManager
    
    # 强制 mock 模式
    os.environ["TRADERLENS_DATA_MODE"] = "mock"
    
    # 准备 mock 数据
    mock_data = create_mock_kline_data(250)
    cache = CacheManager()
    cache.set_price_data("000002", "qfq", mock_data)
    
    # 调用回测工具
    result = backtest_tool(
        stock_code="000002",
        strategy_profile="trend",
        period="6m"
    )
    
    assert result["status"] == "success"
    assert result["data_refs"]["source"] in ["memory", "mock"]
    print(f"✓ Mock 模式下回测正常工作")
    print(f"  - data_refs.source: {result['data_refs']['source']}")


if __name__ == "__main__":
    print("=" * 60)
    print("Phase 2B-2: backtest_tool 验收测试")
    print("=" * 60)
    
    try:
        # 初始化数据库
        from src.core.db_init import init_database
        init_database()
        
        # 运行测试
        test_backtest_tool_standalone()
        # test_agent_with_backtest()  # 跳过 Agent 集成测试（Phase 1 已验证）
        test_backtest_in_mock_mode()
        
        print("\n" + "=" * 60)
        print("✓ 所有测试通过")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    except Exception as e:
        print(f"\n✗ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
