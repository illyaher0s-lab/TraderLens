"""Phase 2B-1 验收测试：watchlist_tool + 人工确认流程

验收标准：
[x] Agent 生成 trade_plan 后，会提出 add_to_watchlist
[x] QualityGate 正确拦截并进入 waiting_human
[x] 用户批准后写入 SQLite
[x] decision_history 记录"人工批准"
[x] observations["watchlist_tool"] 保存工具结果
[x] list_watchlist 能读出刚保存的记录
[x] 拒绝时不会写入数据库
"""

import os
import sys
import logging
from pathlib import Path

# 设置 Python 路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

# 设置环境变量：使用 mock 模式
os.environ["TRADERLENS_DATA_MODE"] = "mock"

from agent.harness import create_agent_graph
from langgraph.types import Command

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)


def test_watchlist_approval_flow():
    """测试完整的观察池添加 + 人工确认流程"""
    logger.info("=" * 60)
    logger.info("Phase 2B-1 验收测试：watchlist_tool + 人工确认")
    logger.info("=" * 60)
    
    # 创建图
    graph = create_agent_graph()
    
    # 初始化状态
    initial_state = {
        "thread_id": "test-phase2b1-watchlist-approval",
        "goal": "分析 000001 平安银行，给出交易计划并加入观察池",
        "stock_code": "000001",
        "strategy_profile": "trend",
        "observations": {},
        "decision_history": [],
        "status": "running",
        "is_goal_complete": False,
        "run_id": "test-phase2b1-001"
    }
    
    config = {
        "configurable": {
            "thread_id": "test-phase2b1-watchlist-approval"
        }
    }
    
    logger.info("\n[Test 1] Agent 运行到 interrupt（等待人工确认）")
    logger.info("=" * 60)
    
    # 第一次执行：运行到 interrupt
    result = None
    for event in graph.stream(initial_state, config, stream_mode="values"):
        result = event
        status = result.get("status", "unknown")
        next_action = result.get("next_action", "none")
        logger.info(f"Step {len(result.get('decision_history', []))}: status={status}, next_action={next_action}")
        
        # 当遇到 interrupt 时，stream 会自动停止
        if status == "waiting_human":
            logger.info("✓ 检测到 waiting_human 状态，Agent 已暂停等待人工确认")
            break
    
    # 验证状态
    assert result is not None, "Agent 应该至少执行了一步"
    assert result["status"] == "waiting_human", f"状态应为 waiting_human，实际为 {result['status']}"
    assert result["next_action"] == "watchlist_tool", f"next_action 应为 watchlist_tool，实际为 {result['next_action']}"
    logger.info("✓ 验证通过：QualityGate 正确拦截了 watchlist_tool")
    
    # 检查 decision_history
    logger.info(f"\n当前 decision_history 有 {len(result['decision_history'])} 条记录：")
    for i, decision in enumerate(result["decision_history"], 1):
        logger.info(f"  {i}. {decision['action']}: {decision.get('result_summary', 'N/A')}")
    
    # 验证：应该已经执行了 market_regime, technicals, trade_plan
    actions = [d["action"] for d in result["decision_history"]]
    assert "market_regime_tool" in actions, "应该已执行 market_regime_tool"
    assert "technicals_tool" in actions, "应该已执行 technicals_tool"
    assert "trade_plan_tool" in actions, "应该已执行 trade_plan_tool"
    logger.info("✓ 验证通过：Agent 在请求添加观察池前，已完成必要的分析步骤")
    
    logger.info("\n[Test 2] 用户批准，Agent 继续执行并写入数据库")
    logger.info("=" * 60)
    
    # 恢复执行：批准操作
    approval_command = Command(resume={"approved": True})
    result = None
    for event in graph.stream(approval_command, config, stream_mode="values"):
        result = event
        status = result.get("status", "unknown")
        next_action = result.get("next_action", "none")
        is_complete = result.get("is_goal_complete", False)
        logger.info(f"Step {len(result.get('decision_history', []))}: status={status}, next_action={next_action}, complete={is_complete}")
    
    # 验证最终状态
    assert result is not None, "Agent 应该继续执行"
    assert result.get("is_goal_complete", False), "目标应该已完成"
    
    # 验证 decision_history 包含人工审批记录
    actions = [d["action"] for d in result["decision_history"]]
    logger.info(f"\n最终 decision_history 有 {len(result['decision_history'])} 条记录：")
    for i, decision in enumerate(result["decision_history"], 1):
        logger.info(f"  {i}. {decision['action']}: {decision.get('result_summary', 'N/A')}")
    
    assert any("human_review" in action for action in actions), "decision_history 应包含人工审批记录"
    logger.info("✓ 验证通过：decision_history 记录了人工批准")
    
    # 验证 observations 包含 watchlist_tool 结果
    assert "watchlist_tool" in result["observations"], "observations 应包含 watchlist_tool 结果"
    watchlist_result = result["observations"]["watchlist_tool"]
    assert watchlist_result["status"] == "success", f"watchlist_tool 应成功，实际状态: {watchlist_result['status']}"
    assert "watchlist_id" in watchlist_result["result"], "结果应包含 watchlist_id"
    watchlist_id = watchlist_result["result"]["watchlist_id"]
    logger.info(f"✓ 验证通过：观察池记录已写入，ID = {watchlist_id}")
    
    logger.info("\n[Test 3] 验证数据库记录")
    logger.info("=" * 60)
    
    # 使用 list_watchlist 读取
    from tools.watchlist_tool import list_watchlist, get_watchlist_item
    
    list_result = list_watchlist(status="watching")
    assert list_result["status"] == "success", f"list_watchlist 应成功，实际: {list_result['status']}"
    assert list_result["result"]["count"] > 0, "观察池应至少有 1 条记录"
    logger.info(f"✓ 验证通过：list_watchlist 返回 {list_result['result']['count']} 条记录")
    
    # 获取详细记录
    item_result = get_watchlist_item(watchlist_id)
    assert item_result["status"] == "success", f"get_watchlist_item 应成功，实际: {item_result['status']}"
    item = item_result["result"]
    assert item["stock_code"] == "000001", f"股票代码应为 000001，实际: {item['stock_code']}"
    assert item["status"] == "watching", f"状态应为 watching，实际: {item['status']}"
    logger.info(f"✓ 验证通过：数据库记录正确")
    logger.info(f"  股票代码: {item['stock_code']}")
    logger.info(f"  入场触发: {item['entry_trigger']}")
    logger.info(f"  止损位: {item['stop_loss']}")
    logger.info(f"  止盈位: {item['take_profit']}")
    
    logger.info("\n[Test 4] 测试用户拒绝场景")
    logger.info("=" * 60)
    
    # 新的 thread，测试拒绝
    initial_state_reject = {
        "thread_id": "test-phase2b1-watchlist-reject",
        "goal": "分析 000002 万科A，给出交易计划并加入观察池",
        "stock_code": "000002",
        "strategy_profile": "trend",
        "observations": {},
        "decision_history": [],
        "status": "running",
        "is_goal_complete": False,
        "run_id": "test-phase2b1-002"
    }
    
    config_reject = {
        "configurable": {
            "thread_id": "test-phase2b1-watchlist-reject"
        }
    }
    
    # 运行到 interrupt
    result_reject = None
    for event in graph.stream(initial_state_reject, config_reject, stream_mode="values"):
        result_reject = event
        if result_reject.get("status") == "waiting_human":
            logger.info("✓ 检测到 waiting_human 状态")
            break
    
    assert result_reject["status"] == "waiting_human", "应进入 waiting_human 状态"
    
    # 记录当前观察池数量
    list_before = list_watchlist(status="watching")
    count_before = list_before["result"]["count"]
    logger.info(f"拒绝前观察池数量: {count_before}")
    
    # 拒绝操作
    reject_command = Command(resume={"approved": False})
    result_reject_final = None
    for event in graph.stream(reject_command, config_reject, stream_mode="values"):
        result_reject_final = event
    
    # 验证：应该失败
    assert result_reject_final["status"] == "failed", f"状态应为 failed，实际: {result_reject_final['status']}"
    assert result_reject_final["error_message"] == "用户拒绝了操作", "错误信息应为'用户拒绝了操作'"
    logger.info("✓ 验证通过：拒绝后 Agent 状态为 failed")
    
    # 验证：观察池数量不变
    list_after = list_watchlist(status="watching")
    count_after = list_after["result"]["count"]
    assert count_after == count_before, f"拒绝后观察池数量应不变，之前: {count_before}，之后: {count_after}"
    logger.info(f"✓ 验证通过：拒绝后观察池数量未增加（仍为 {count_after}）")
    
    logger.info("\n" + "=" * 60)
    logger.info("Phase 2B-1 验收测试全部通过 ✓")
    logger.info("=" * 60)


if __name__ == "__main__":
    # 初始化数据库
    from core.db_init import init_database
    init_database()
    logger.info("Database initialized\n")
    
    # 运行测试
    test_watchlist_approval_flow()
