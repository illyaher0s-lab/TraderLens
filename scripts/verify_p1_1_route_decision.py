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

test_cases = []

def add_test(name, input_text, expected, conversation_id=None, check_artifact=None):
    test_cases.append((name, input_text, expected, conversation_id, check_artifact))

def create_position_context():
    seed = client.post(
        '/api/agent/workbench/message',
        json={'message': '帮我看603002', 'conversation_id': None},
    )
    assert seed.status_code == 200
    session_id = seed.json()['conversation_id']
    position_id = 'pos_route_test_001'
    db.conn.execute(
        """
        INSERT INTO observation_positions (
            position_id, source_log_id, execution_card_id, signal_id,
            action_plan_id, capital_context_id, symbol, name, entry_price,
            quantity, template_id, template_version, entry_thesis,
            lifecycle_state, opened_at, closed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            position_id,
            'log_route_test_001',
            'card_route_test_001',
            'signal_route_test_001',
            'plan_route_test_001',
            'capital_route_test_001',
            '603002.SH',
            '宏昌电子',
            12.34,
            100,
            'template_route_test',
            '1.0',
            'route decision verification',
            'open',
            '2026-07-02T09:30:00',
            None,
        ),
    )
    db.conn.commit()
    return session_id, position_id


def create_stock_context():
    seed = client.post(
        '/api/agent/workbench/message',
        json={'message': '帮我看603002', 'conversation_id': None},
    )
    assert seed.status_code == 200
    return seed.json()['conversation_id']


position_session_id, expected_position_id = create_position_context()
stock_context_session_id = create_stock_context()

add_test('execution_feedback', "已买入100股成交价12.34", "execution_feedback", check_artifact="no_flow")
add_test('hypothetical_buy_clarification', "我在想要不要买100股", ["clarification", "unknown"], check_artifact="no_position")
add_test('position_followup_no_position', "今天要不要继续拿", ["clarification", "unknown"])
add_test('position_followup_with_open_position', "今天要不要继续拿", "position_followup", conversation_id=position_session_id, check_artifact="open_position")
add_test('stock_code_friend_stock', "帮我看603002", "friend_stock", check_artifact="flow_id")
add_test('company_friend_stock', "朋友推荐了宏昌电子", "friend_stock", check_artifact="flow_id")
add_test('strategy_idea', "刷到策略下午两点半买第二天卖", "strategy_idea", check_artifact="idea_id")
add_test('followup_no_context', "帮我看看", ["clarification", "unknown"])
add_test('followup_with_stock_context', "帮我看看", "friend_stock", conversation_id=stock_context_session_id, check_artifact="flow_id")
add_test('greeting', "你好", ["clarification", "unknown"])
add_test('buy_stock_research', "买入宏昌电子可以吗", "friend_stock", check_artifact="flow_id")

print("=" * 140)
print("P1-1 Route Decision Verification")
print("=" * 140)
print()
print(f"{'Input':<40} | {'route_decision':<20} | {'response.type':<20} | {'Match':<5} | {'Expected':<20} | {'Pass'}")
print("-" * 140)

failures = []

for name, message, expected_workflow, conversation_id, check_artifact in test_cases:
    response = client.post(
        '/api/agent/workbench/message',
        json={'message': message, 'conversation_id': conversation_id}
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
            failures.append((name, "Missing flow_id evidence"))
    elif check_artifact == "no_flow":
        # execution_feedback should not create flow
        cursor = db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM friend_stock_flows WHERE source_note LIKE ?", (f"%{message}%",))
        count = cursor.fetchone()[0]
        if count > 0:
            print(f"  WARNING: Unexpected flow created for execution_feedback")
            failures.append((name, "Should not create flow"))
    elif check_artifact == "idea_id":
        if not any(str(artifact_id).startswith("idea_") for artifact_id in data.get("artifact_ids", [])):
            failures.append((name, "Missing idea_id evidence"))
    elif check_artifact == "no_position":
        cursor = db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM observation_positions WHERE symbol = '603002.SH'")
        # Only the explicit position context is allowed to exist.
        count = cursor.fetchone()[0]
        if count != 1:
            failures.append((name, f"Unexpected position count {count}"))
    elif check_artifact == "open_position":
        if expected_position_id not in data.get("agent_reply", "") and expected_position_id not in str(data.get("artifact_ids", [])):
            failures.append((name, f"Missing open_position_id evidence {expected_position_id}"))

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
    print(f"Position follow-up open_position_id: {expected_position_id}")
    sys.exit(0)
