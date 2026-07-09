"""
P1-3 浏览器验收测试脚本
发送三条测试消息并记录 timeline artifacts
"""

import requests
import json
import sys

API_BASE = "http://localhost:8000"

def send_message(message, conversation_id=None):
    """发送消息到 workbench"""
    url = f"{API_BASE}/api/agent/workbench/message"
    payload = {"message": message}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    
    response = requests.post(url, json=payload)
    response.raise_for_status()
    return response.json()

def get_session(conversation_id):
    """获取会话 timeline"""
    url = f"{API_BASE}/api/agent/workbench/{conversation_id}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def print_timeline_artifacts(timeline):
    """打印 timeline 中的 artifact 类型"""
    artifacts = [item for item in timeline if item['type'] == 'artifact_ref']
    print(f"\n=== Timeline Artifact Types ({len(artifacts)} artifacts) ===")
    for i, artifact in enumerate(artifacts, 1):
        artifact_type = artifact['content']['artifact_type']
        artifact_id = artifact['content']['artifact_id']
        print(f"{i}. {artifact_type} (id: {artifact_id})")

def main():
    print("=" * 80)
    print("P1-3 Workbench 浏览器验收测试")
    print("=" * 80)
    
    # Test 1: 朋友推荐了宏昌电子
    print("\n\n【测试 1】朋友推荐了宏昌电子")
    print("-" * 80)
    
    response1 = send_message("朋友推荐了宏昌电子")
    conversation_id = response1['conversation_id']
    
    print(f"Conversation ID: {conversation_id}")
    print(f"Agent Reply: {response1['agent_reply']}")
    
    session1 = get_session(conversation_id)
    print_timeline_artifacts(session1['timeline'])
    
    # Save to file
    with open('test1_timeline.json', 'w', encoding='utf-8') as f:
        json.dump(session1['timeline'], f, ensure_ascii=False, indent=2)
    print("\n完整 timeline 已保存到: test1_timeline.json")
    
    # Test 2: 刷到策略下午两点半买第二天卖
    print("\n\n【测试 2】刷到策略下午两点半买第二天卖")
    print("-" * 80)
    
    response2 = send_message("刷到策略下午两点半买第二天卖")
    conversation_id2 = response2['conversation_id']
    
    print(f"Conversation ID: {conversation_id2}")
    print(f"Agent Reply: {response2['agent_reply']}")
    
    session2 = get_session(conversation_id2)
    print_timeline_artifacts(session2['timeline'])
    
    with open('test2_timeline.json', 'w', encoding='utf-8') as f:
        json.dump(session2['timeline'], f, ensure_ascii=False, indent=2)
    print("\n完整 timeline 已保存到: test2_timeline.json")
    
    # Test 3: 帮我看看（承接测试 1）
    print("\n\n【测试 3】帮我看看（承接上一轮宏昌电子）")
    print("-" * 80)
    
    response3 = send_message("帮我看看", conversation_id=conversation_id)
    
    print(f"Conversation ID: {conversation_id}")
    print(f"Agent Reply: {response3['agent_reply']}")
    
    session3 = get_session(conversation_id)
    print_timeline_artifacts(session3['timeline'])
    
    # Check context_loaded
    artifacts = [item for item in session3['timeline'] if item['type'] == 'artifact_ref']
    context_loaded_artifacts = [a for a in artifacts if a['content']['artifact_type'] == 'context_loaded']
    
    if context_loaded_artifacts:
        last_context = context_loaded_artifacts[-1]
        if last_context['content'].get('artifact_content'):
            try:
                context_data = json.loads(last_context['content']['artifact_content'])
                print(f"\n【验证】context_loaded 内容:")
                print(f"  claimed_stock: {context_data.get('claimed_stock')}")
            except:
                print("\n【验证】无法解析 context_loaded 内容")
    
    with open('test3_timeline.json', 'w', encoding='utf-8') as f:
        json.dump(session3['timeline'], f, ensure_ascii=False, indent=2)
    print("\n完整 timeline 已保存到: test3_timeline.json")
    
    print("\n\n" + "=" * 80)
    print("测试完成！")
    print("=" * 80)
    print("\n请访问 http://localhost:3010/workbench 查看前端界面")
    print("对照上述 artifact 列表验证活动流显示")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n错误: {e}", file=sys.stderr)
        sys.exit(1)
