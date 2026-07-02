"""
P1-1 第二批验证脚本 - Commit 1

使用 FastAPI TestClient 调用真实 API：
POST /api/agent/workbench/message

输出 9 条输入的真实 {intent, route, workflow_state}
"""

import os
import sys
from pathlib import Path

# Add backend to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set environment
os.environ["PYTHONIOENCODING"] = "utf-8"

# Tushare config (not used in deterministic mode, but set for completeness)
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "32821f0804f7800a20eb6f6702fe6cb1")
TUSHARE_API_URL = os.getenv("TUSHARE_API_URL", "http://8.163.90.143:8686/")

os.environ["TUSHARE_TOKEN"] = TUSHARE_TOKEN
os.environ["TUSHARE_API_URL"] = TUSHARE_API_URL

# Clear proxy
for key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]:
    os.environ.pop(key, None)


def test_workbench_9_inputs():
    """Test 9 input cases with real API calls."""
    from fastapi.testclient import TestClient
    from backend.api.research import create_research_app
    from backend.db.research import ResearchDB
    
    # Build test fixture for deterministic mode
    test_fixture = {
        "600000.SH": {
            "ticker": "600000.SH",
            "company_name": "浦发银行",
            "exchange": "SSE",
            "list_status": "L"
        },
        "603002.SH": {
            "ticker": "603002.SH",
            "company_name": "宏昌电子",
            "exchange": "SSE",
            "list_status": "L"
        },
        "000001.SZ": {
            "ticker": "000001.SZ",
            "company_name": "平安银行",
            "exchange": "SZSE",
            "list_status": "L"
        },
        "300750.SZ": {
            "ticker": "300750.SZ",
            "company_name": "宁德时代",
            "exchange": "SZSE",
            "list_status": "L"
        },
    }
    
    # Create app with deterministic mode + injected fixture
    db = ResearchDB(db_path=":memory:")
    app = create_research_app(
        db=db,
        conversation_mode="deterministic",
        serenity_execution_mode="stub",
        stock_resolver_fixture=test_fixture,
    )
    
    client = TestClient(app)
    
    # Test cases
    test_cases = [
        "帮我看宏昌电子是否值得买入",
        "帮我看603002",
        "朋友推荐了宏昌电子",
        "买入宏昌电子可以吗",
        "刷到策略下午两点半买第二天卖",
        "已买入100股成交价12.34",
        "今天要不要继续拿",
        "帮我看看",
        "你好",
    ]
    
    print("=" * 80)
    print("P1-1 第二批验证 - Commit 1: 真实 API 调用（deterministic + fixture）")
    print("=" * 80)
    print()
    
    results = []
    friend_stock_ids = []
    strategy_idea_ids = []
    
    for i, message in enumerate(test_cases, 1):
        print(f"测试 {i}/{len(test_cases)}: {message}")
        print("-" * 80)
        
        # Call real API endpoint
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": message, "conversation_id": None}
        )
        
        print(f"  HTTP Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract fields (use correct field names from response)
            workflow_type = data.get("workflow_type", "unknown")
            stage = data.get("stage", "unknown")
            agent_reply = data.get("agent_reply", "")  # Correct field name
            artifact_ids = data.get("artifact_ids", [])  # Correct field name
            
            # Check artifacts for DB record IDs
            for artifact_id in artifact_ids:
                if artifact_id.startswith("flow_"):
                    friend_stock_ids.append(artifact_id)
                elif artifact_id.startswith("idea_"):
                    strategy_idea_ids.append(artifact_id)
            
            results.append({
                "message": message,
                "workflow_type": workflow_type,
                "stage": stage,
                "status": "OK",
            })
            
            print(f"  Workflow Type: {workflow_type}")
            print(f"  Stage: {stage}")
            print(f"  Artifact IDs: {artifact_ids}")
            print(f"  Reply: {agent_reply[:100]}...")
        else:
            print(f"  ❌ API Error: {response.text[:200]}")
            results.append({
                "message": message,
                "workflow_type": "error",
                "stage": "error",
                "status": "FAIL",
            })
        
        print()
    
    # Summary table
    print("=" * 80)
    print("验证结果汇总")
    print("=" * 80)
    print()
    
    print(f"{'输入':<35} | {'Workflow Type':<20} | {'Stage':<20} | {'Status':<10}")
    print("-" * 95)
    for result in results:
        msg = result['message'][:33]
        print(f"{msg:<35} | {result['workflow_type']:<20} | {result['stage']:<20} | {result['status']:<10}")
    
    print()
    print(f"Friend Stock DB Records: {len(friend_stock_ids)}")
    if friend_stock_ids:
        for fid in friend_stock_ids[:3]:  # Show up to 3
            print(f"  - {fid}")
    
    print()
    print(f"Strategy Idea DB Records: {len(strategy_idea_ids)}")
    if strategy_idea_ids:
        for sid in strategy_idea_ids[:3]:
            print(f"  - {sid}")
    
    print()
    print("说明:")
    print("- 身份解析: deterministic_fixture（编排测试）")
    print("- 真实 Tushare: 第一批已独立验收")
    print()
    
    # Return results for potential automation
    return results, friend_stock_ids, strategy_idea_ids


if __name__ == "__main__":
    test_workbench_9_inputs()
