"""Phase 2B-5 验收测试 - research_memory_tool

测试目标：
1. 验证占位实现能正常返回
2. 验证输出格式符合统一标准
3. 验证可以安全集成到 Agent
"""

import os
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.tools.research_memory_tool import search_research_memory


def test_research_memory_tool():
    """测试 1: 独立测试 research_memory_tool"""
    print("\n" + "="*60)
    print("测试 1: 独立测试 research_memory_tool")
    print("="*60)
    
    # 测试查询
    query = "平安银行"
    
    print(f"\n检索关键词: {query}")
    print("-" * 60)
    
    # 调用工具
    result = search_research_memory(query=query, limit=5)
    
    # 验证返回格式
    assert result["tool"] == "search_research_memory", "工具名称错误"
    assert result["status"] in ["success", "error"], "状态字段错误"
    assert "result" in result, "缺少 result 字段"
    assert "summary" in result, "缺少 summary 字段"
    assert "signals" in result, "缺少 signals 字段"
    assert "data_refs" in result, "缺少 data_refs 字段"
    assert "created_at" in result, "缺少 created_at 字段"
    
    # 打印结果
    print(f"\n✓ 检索完成")
    print(f"  - 状态: {result['status']}")
    print(f"  - 查询: {result['result'].get('query', 'N/A')}")
    print(f"  - 找到记录数: {result['result'].get('found_count', 0)}")
    print(f"  - 记录列表: {result['result'].get('records', [])}")
    print(f"  - Summary: {result['summary']}")
    print(f"  - Signals: {result['signals']}")
    print(f"  - Ref ID: {result['data_refs'].get('ref_id', 'N/A')}")
    print(f"  - Source: {result['data_refs'].get('source', 'N/A')}")
    
    # 验证 result 包含必需字段
    assert "query" in result["result"], "result 缺少 query"
    assert "found_count" in result["result"], "result 缺少 found_count"
    assert "records" in result["result"], "result 缺少 records"
    
    # 验证占位实现返回空结果
    assert result["result"]["found_count"] == 0, "占位实现应该返回 0 条记录"
    assert len(result["result"]["records"]) == 0, "占位实现应该返回空列表"
    
    print("\n✓ 所有断言通过")
    
    return result


def test_different_queries():
    """测试 2: 测试不同查询"""
    print("\n" + "="*60)
    print("测试 2: 测试不同查询")
    print("="*60)
    
    queries = [
        "平安银行",
        "银行板块",
        "趋势策略",
        ""
    ]
    
    for query in queries:
        result = search_research_memory(query=query, limit=3)
        print(f"\n查询: '{query}'")
        print(f"  - 状态: {result['status']}")
        print(f"  - 找到记录数: {result['result']['found_count']}")
        print(f"  - Ref ID: {result['data_refs']['ref_id']}")
        
        # 验证每次调用都能正常返回
        assert result["status"] == "success", f"查询 '{query}' 失败"
        assert result["result"]["found_count"] == 0, "占位实现应该返回 0"
    
    print("\n✓ 不同查询测试通过")


def test_agent_integration():
    """测试 3: 验证 Agent 集成"""
    print("\n" + "="*60)
    print("测试 3: 验证 Agent 集成")
    print("="*60)
    
    # 模拟 Agent 调用
    from src.agent.executor import _execute_tool
    from src.agent.state import AgentState
    
    # 创建最小 state
    state: AgentState = {
        "thread_id": "test_thread",
        "run_id": "test_run",
        "goal": "测试 research_memory_tool",
        "observations": {},
        "decision_history": [],
        "next_action": None,
        "next_action_input": None,
        "is_goal_complete": False,
        "status": "running",
        "thought_summary": None,
        "_tool_call_counts": {}
    }
    
    # 调用 executor
    tool_input = {
        "query": "平安银行",
        "limit": 5
    }
    
    result = _execute_tool("search_research_memory", tool_input, state)
    
    print(f"\n✓ Agent 集成测试")
    print(f"  - 工具名称: {result['tool']}")
    print(f"  - 状态: {result['status']}")
    print(f"  - 可以安全放入 observations: {isinstance(result, dict)}")
    
    # 验证可以安全放入 observations
    assert isinstance(result, dict), "返回值应该是 dict"
    assert "tool" in result, "返回值应该包含 tool 字段"
    assert "status" in result, "返回值应该包含 status 字段"
    
    print("\n✓ Agent 集成正常")


def test_output_format_consistency():
    """测试 4: 验证输出格式一致性"""
    print("\n" + "="*60)
    print("测试 4: 验证输出格式一致性")
    print("="*60)
    
    result = search_research_memory(query="测试", limit=5)
    
    # 验证与其他工具的输出格式一致
    required_fields = [
        "tool",
        "status",
        "result",
        "summary",
        "signals",
        "data_refs",
        "error",
        "created_at"
    ]
    
    print(f"\n验证输出字段:")
    for field in required_fields:
        assert field in result, f"缺少字段: {field}"
        print(f"  ✓ {field}: {type(result[field]).__name__}")
    
    # 验证 data_refs 结构
    data_refs_fields = ["ref_id", "source", "is_stale", "last_updated"]
    print(f"\n验证 data_refs 字段:")
    for field in data_refs_fields:
        assert field in result["data_refs"], f"data_refs 缺少字段: {field}"
        print(f"  ✓ {field}: {result['data_refs'][field]}")
    
    print("\n✓ 输出格式一致性验证通过")


def main():
    """主测试入口"""
    print("\n" + "="*60)
    print("Phase 2B-5 验收测试 - research_memory_tool")
    print("="*60)
    
    try:
        # 测试 1: 独立测试工具
        result = test_research_memory_tool()
        
        # 测试 2: 不同查询
        test_different_queries()
        
        # 测试 3: Agent 集成
        test_agent_integration()
        
        # 测试 4: 输出格式一致性
        test_output_format_consistency()
        
        print("\n" + "="*60)
        print("✅ Phase 2B-5 所有测试通过")
        print("="*60)
        print("\n说明:")
        print("  - research_memory_tool 占位实现完成")
        print("  - 返回空结果，可以安全集成到 Agent")
        print("  - Phase 3+ 接入 SQLite / RAG 只需替换 result['records']")
        print("\n下一步: Phase 3 (Streamlit UI)")
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
