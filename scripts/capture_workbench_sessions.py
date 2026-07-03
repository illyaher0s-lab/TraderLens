"""
Capture workbench sessions for P1-3 browser verification.

Sends three messages and captures:
1. conversation_id
2. timeline artifacts
3. Saves to JSON files for manual screenshot comparison
"""

import requests
import json
import sys
from pathlib import Path

API_BASE = "http://localhost:8000"

def send_message(message: str, conversation_id: str | None = None) -> dict:
    """Send a message to workbench and return response."""
    response = requests.post(
        f"{API_BASE}/api/agent/workbench/message",
        json={"message": message, "conversation_id": conversation_id}
    )
    response.raise_for_status()
    return response.json()

def get_session_timeline(conversation_id: str) -> dict:
    """Get full session timeline."""
    response = requests.get(f"{API_BASE}/api/agent/workbench/{conversation_id}")
    response.raise_for_status()
    return response.json()

def extract_artifact_types(timeline: list) -> list[str]:
    """Extract artifact types from timeline in order."""
    return [
        item["content"]["artifact_type"]
        for item in timeline
        if item["type"] == "artifact_ref"
    ]

def main():
    output_dir = Path("screenshots")
    output_dir.mkdir(exist_ok=True)
    
    test_cases = [
        {
            "message": "朋友推荐了宏昌电子",
            "output_file": "test1_friend_stock_data.json",
            "description": "Test 1: Friend stock recommendation"
        },
        {
            "message": "刷到策略下午两点半买第二天卖",
            "output_file": "test2_strategy_idea_data.json",
            "description": "Test 2: Strategy idea"
        },
        {
            "message": "帮我看看",
            "output_file": "test3_context_loaded_data.json",
            "description": "Test 3: Context follow-up"
        }
    ]
    
    conversation_id = None
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n{'='*60}")
        print(f"{test['description']}")
        print(f"{'='*60}")
        print(f"Sending: {test['message']}")
        
        # Send message
        response = send_message(test["message"], conversation_id)
        conversation_id = response["conversation_id"]
        
        print(f"conversation_id: {conversation_id}")
        print(f"workflow_type: {response['workflow_type']}")
        print(f"stage: {response['stage']}")
        
        # Get full timeline
        session_data = get_session_timeline(conversation_id)
        artifact_types = extract_artifact_types(session_data["timeline"])
        
        print(f"\nArtifact types ({len(artifact_types)}):")
        for j, art_type in enumerate(artifact_types, 1):
            print(f"  {j}. {art_type}")
        
        # Save to file
        output_path = output_dir / test["output_file"]
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "test_case": test["description"],
                "message": test["message"],
                "conversation_id": conversation_id,
                "workflow_type": response["workflow_type"],
                "stage": response["stage"],
                "agent_reply": response["agent_reply"],
                "artifact_types": artifact_types,
                "full_timeline": session_data["timeline"]
            }, f, ensure_ascii=False, indent=2)
        
        print(f"Saved to: {output_path}")
    
    print(f"\n{'='*60}")
    print("All test cases completed!")
    print(f"{'='*60}")
    print("\nNext steps:")
    print("1. Compare screenshot content with artifact_types in each JSON file")
    print("2. Verify status panel text matches timeline state")
    print("3. Verify activity flow items match artifact_types order")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
