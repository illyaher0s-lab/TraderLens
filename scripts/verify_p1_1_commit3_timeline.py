"""
P1-1 Commit 3 验证: Session Context + Timeline Activity

验证：
1. context_loaded artifact 存在
2. prescan_result, intent_extraction, stock_identity_resolution, route_decision artifacts 存在
3. workflow_action_started, workflow_action_completed artifacts 存在
4. Timeline 可以读回所有 activity
"""

import sys
import os

# Add project root to path
project_root = r'D:\Codex\TraderLens'
sys.path.insert(0, project_root)
os.chdir(project_root)

from fastapi.testclient import TestClient

from backend.api.research import create_research_app
from backend.db.research import ResearchDB
from backend.db.agent_workbench import get_session_timeline

# Test fixture
test_fixture = {
    '603002.SH': {
        'ticker': '603002.SH',
        'company_name': '宏昌电子',
        'exchange': 'SSE',
        'list_status': 'L'
    },
}

# Create app with deterministic mode
db = ResearchDB(db_path=":memory:")
app = create_research_app(
    db=db,
    conversation_mode="deterministic",
    serenity_execution_mode="stub",
    stock_resolver_fixture=test_fixture,
)

client = TestClient(app)

print("测试 1: friend_stock workflow (帮我看603002)")
print("=" * 80)

response = client.post(
    "/api/agent/workbench/message",
    json={"message": "帮我看603002", "conversation_id": None}
)

assert response.status_code == 200
data = response.json()
session_id = data["conversation_id"]

# Get timeline
timeline = get_session_timeline(db.conn, session_id)

print(f"\nSession ID: {session_id}")
print(f"Timeline 条目数: {len(timeline)}")
print("\nTimeline 内容:")

activity_types = []
for i, item in enumerate(timeline):
    item_type = item["type"]
    if item_type == "artifact_ref":
        artifact_type = item["content"]["artifact_type"]
        artifact_id = item["content"]["artifact_id"]
        activity_types.append(artifact_type)
        print(f"  {i+1}. {artifact_type} -> {artifact_id}")
    elif item_type == "message":
        role = item["content"]["role"]
        content_preview = item["content"]["content"][:30]
        print(f"  {i+1}. message ({role}) -> {content_preview}...")

print("\n活动类型统计:")
print(f"  context_loaded: {activity_types.count('context_loaded')}")
print(f"  prescan_result: {activity_types.count('prescan_result')}")
print(f"  intent_extraction: {activity_types.count('intent_extraction')}")
print(f"  stock_identity_resolution: {activity_types.count('stock_identity_resolution')}")
print(f"  workflow_route_decision: {activity_types.count('workflow_route_decision')}")
print(f"  workflow_action_started: {activity_types.count('workflow_action_started')}")
print(f"  workflow_action_completed: {activity_types.count('workflow_action_completed')}")
print(f"  friend_stock_flow: {activity_types.count('friend_stock_flow')}")

# Verify required activities
required = ['context_loaded', 'prescan_result', 'intent_extraction', 'stock_identity_resolution', 
            'workflow_route_decision', 'workflow_action_started', 'workflow_action_completed']
missing = [r for r in required if r not in activity_types]

if missing:
    print(f"\n[FAIL] 缺少活动: {missing}")
else:
    print(f"\n[PASS] 所有必需活动都已记录")

print("\n" + "=" * 80)
print("测试 2: strategy_idea workflow (刷到策略下午两点半买第二天卖)")
print("=" * 80)

response2 = client.post(
    "/api/agent/workbench/message",
    json={"message": "刷到策略下午两点半买第二天卖", "conversation_id": None}
)

assert response2.status_code == 200
data2 = response2.json()
session_id2 = data2["conversation_id"]

# Get timeline
timeline2 = get_session_timeline(db.conn, session_id2)

print(f"\nSession ID: {session_id2}")
print(f"Timeline 条目数: {len(timeline2)}")

activity_types2 = []
for item in timeline2:
    if item["type"] == "artifact_ref":
        activity_types2.append(item["content"]["artifact_type"])

print("\n活动类型统计:")
print(f"  context_loaded: {activity_types2.count('context_loaded')}")
print(f"  prescan_result: {activity_types2.count('prescan_result')}")
print(f"  intent_extraction: {activity_types2.count('intent_extraction')}")
print(f"  workflow_route_decision: {activity_types2.count('workflow_route_decision')}")
print(f"  workflow_action_started: {activity_types2.count('workflow_action_started')}")
print(f"  workflow_action_completed: {activity_types2.count('workflow_action_completed')}")
print(f"  strategy_idea: {activity_types2.count('strategy_idea')}")
print(f"  strategy_idea_extraction: {activity_types2.count('strategy_idea_extraction')}")

# Verify required activities (no stock_identity_resolution for strategy_idea)
required2 = ['context_loaded', 'prescan_result', 'intent_extraction', 
             'workflow_route_decision', 'workflow_action_started', 'workflow_action_completed']
missing2 = [r for r in required2 if r not in activity_types2]

if missing2:
    print(f"\n[FAIL] 缺少活动: {missing2}")
else:
    print(f"\n[PASS] 所有必需活动都已记录")

print("\n" + "=" * 80)
print("验证完成")
