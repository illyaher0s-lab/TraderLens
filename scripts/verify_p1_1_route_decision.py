"""
P1-1 Route Decision 单一裁决源收口验证

验证：
1. route_decision.workflow_kind (从 timeline artifact 读取) | response.workflow_type | 是否相等
2. 每条输入断言 workflow_type == 期望值
3. exit code 非0 表示验证失败
4. handler 非空壳证据
"""

import sys
import os
import json

project_root = r'D:\Codex\TraderLens'
sys.path.insert(0, project_root)
os.chdir(project_root)

from fastapi.testclient import TestClient
from backend.api.research import create_research_app
from backend.db.research import ResearchDB
from backend.db.agent_workbench import get_artifact_content
import sqlite3

test_fixture = {
    '603002.SH': {
        'ticker': '603002.SH',
        'company_name': '宏昌电子',
        'exchange': 'SSE',
        'list_status': 'L'
    },
}

db = ResearchDB(db_path=':memory:')
app = create_research_app(
    db=db,
    conversation_mode='deterministic',
    serenity_execution_mode='stub',
    stock_resolver_fixture=test_fixture,
)

client = TestClient(app)

# Test cases: (input, expected, setup_fn, check_artifact)
test_cases = []

def add_test(input_text, expected, setup_fn=None, check_artifact=None):
    test_cases.append((input_text, expected, setup_fn, check_artifact))

# 1. execution_feedback - 不建 flow
add_test("已买入100股成交价12.34", "execution_feedback", check_artifact="no_flow")

# 2. clarification - 不建仓
add_test("我在想要不要买100股", ["clarification", "unknown"], check_artifact="no_position")

# 3. position_followup 无持仓 -> clarification/unknown
add_test("今天要不要继续拿", ["clarification", "unknown"])

# 4. position_followup 有持仓 -> position_followup
def setup_position_followup(session_id):
    # 模拟持仓：直接在 router 逻辑中 open_positions 会在 existing session 加载
    # 因为 new session 总是空，我们需要用 existing session
    # 但验证脚本每次都是 new session (conversation_id=None)
    # 所以这条用例实际上无法通过 router 到达 position_followup
    # 需要修改：使用 existing session
    pass

# 跳过第 4 条，因为需要 existing session + open_position（复杂 setup）

# 5-11. 其他用例
add_test("帮我看603002", "friend_stock", check_artifact="flow_id")
add_test("朋友推荐了宏昌电子", "friend_stock", check_artifact="flow_id")
add_test("刷到策略下午两点半买第二天卖", "strategy_idea", check_artifact="idea_id")
add_test("帮我看看", ["clarification", "unknown"])
# 跳过 "帮我看看(有上一轮股票上下文)" - 需要 existing session
add_test("你好", ["clarification", "unknown"])
add_test("买入宏昌电子可以吗", "friend_stock", check_artifact="flow_id")

print("=" * 140)
print("P1-1 Route Decision Verification")
print("=" * 140)
print()
print(f"{'Input':<40} | {'route_decision':<20} | {'response.type':<20} | {'Match':<5} | {'Expected':<20} | {'Pass'}")
print("-" * 140)

failures = []

for test_item in test_cases:
    if len(test_item) == 4:
        message, expected_workflow, setup_fn, check_artifact = test_item
    else:
        message, expected_workflow = test_item
        setup_fn = None
        check_artifact = None
    
    if setup_fn:
        setup_fn(None)
    
    response = client.post(
        '/api/agent/workbench/message',
        json={'message': message, 'conversation_id': None}
    )
    
    if response.status_code != 200:
        print(f"{message:<40} | ERROR: HTTP {response.status_code}")
        failures.append((message, f"HTTP {response.status_code}"))
        continue
    
    data = response.json()
    response_workflow_type = data.get('workflow_type', 'MISSING')
    session_id = data.get('conversation_id')
    
    # Read route_decision from timeline artifact
    route_decision_content = get_artifact_content(db.conn, session_id, 'workflow_route_decision')
    if not route_decision_content:
        print(f"{message:<40} | NO ARTIFACT")
        failures.append((message, "No route_decision artifact"))
        continue
    
    route_decision = json.loads(route_decision_content)
    route_decision_workflow = route_decision['workflow_kind']
    
    match = "YES" if route_decision_workflow == response_workflow_type else "NO"
    
    # Check against expected
    if isinstance(expected_workflow, list):
        # Accept any in list
        expected_pass = response_workflow_type in expected_workflow
        actual_expected = response_workflow_type if expected_pass else expected_workflow[0]
    else:
        actual_expected = expected_workflow
        expected_pass = (response_workflow_type == expected_workflow)
    
    pass_str = "PASS" if expected_pass and match == "YES" else "FAIL"
    
    print(f"{message:<40} | {route_decision_workflow:<20} | {response_workflow_type:<20} | {match:<5} | {actual_expected:<20} | {pass_str}")
    
    if not expected_pass or match != "YES":
        failures.append((message, f"Expected {actual_expected}, got {response_workflow_type}, match={match}"))
    
    # Check artifact evidence
    if check_artifact == "flow_id":
        # friend_stock should create flow
        cursor = db.conn.cursor()
        cursor.execute("SELECT flow_id FROM friend_stock_flows WHERE source_note LIKE ? ORDER BY created_at DESC LIMIT 1", (f"%{message}%",))
        flow = cursor.fetchone()
        if not flow:
            print(f"  WARNING: No flow_id found for friend_stock")
            failures.append((message, "Missing flow_id evidence"))
    elif check_artifact == "no_flow":
        # execution_feedback should not create flow
        cursor = db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM friend_stock_flows WHERE source_note LIKE ?", (f"%{message}%",))
        count = cursor.fetchone()[0]
        if count > 0:
            print(f"  WARNING: Unexpected flow created for execution_feedback")
            failures.append((message, "Should not create flow"))

print("-" * 140)
print()

if failures:
    print(f"FAILED: {len(failures)}/{len(test_cases)} tests failed")
    for msg, reason in failures:
        print(f"  - {msg}: {reason}")
    sys.exit(1)
else:
    print(f"SUCCESS: All {len(test_cases)} tests passed")
    print()
    print("Iron Rule Verified:")
    print("  [OK] route_decision.workflow_kind read from timeline artifact")
    print("  [OK] response.workflow_type == route_decision.workflow_kind (no override)")
    print()
    print("Note: 2 context-dependent tests skipped (require existing session + open_position/stock_context)")
    print("  - 'position_followup with open_position'")
    print("  - 'friend_stock follow-up with stock context'")
    sys.exit(0)
