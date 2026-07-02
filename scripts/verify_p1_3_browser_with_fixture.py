"""
P1-3 Browser Verification with Test Fixture

Uses stock_resolver_fixture to bypass Tushare and verify frontend state derivation.
Sends three messages and captures timeline + artifact types for screenshot comparison.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from backend.api.research import create_research_app
from backend.db.research import ResearchDB
import json

def main():
    print("P1-3 Browser Verification (with fixture)")
    print("=" * 70)
    
    # Create app with test fixture for stock resolution
    # Key = query input (company name or code), Value = unique identity
    # Don't use same company_name in multiple entries (causes ambiguous match)
    stock_fixture = {
        "宏昌电子": {
            "ticker": "603002.SH",
            "company_name": "宏昌电子",
            "exchange": "SH"
        },
        "603002.SH": {
            "ticker": "603002.SH",
            "company_name": "宏昌电子",
            "exchange": "SH"
        },
        "603002": {
            "ticker": "603002.SH",
            "company_name": "宏昌电子",
            "exchange": "SH"
        }
    }
    
    db = ResearchDB(db_path=":memory:")
    app = create_research_app(
        db=db,
        conversation_mode="deterministic",
        stock_resolver_fixture=stock_fixture
    )
    
    client = TestClient(app)
    
    test_cases = [
        {
            "message": "朋友推荐了宏昌电子",
            "expected_workflow": "friend_stock",
            "description": "Test 1: Friend stock recommendation"
        },
        {
            "message": "刷到策略下午两点半买第二天卖",
            "expected_workflow": "strategy_idea",
            "description": "Test 2: Strategy idea"
        },
        {
            "message": "帮我看看",
            "expected_workflow": "friend_stock",
            "description": "Test 3: Context follow-up"
        }
    ]
    
    conversation_id = None
    output_dir = Path("screenshots")
    output_dir.mkdir(exist_ok=True)
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n{test['description']}")
        print("-" * 70)
        print(f"Input: {test['message']}")
        
        # Send message
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": test["message"], "conversation_id": conversation_id}
        )
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        conversation_id = data["conversation_id"]
        
        print(f"conversation_id: {conversation_id}")
        print(f"workflow_type: {data['workflow_type']}")
        print(f"stage: {data['stage']}")
        
        # Get full timeline
        timeline_response = client.get(f"/api/agent/workbench/{conversation_id}")
        assert timeline_response.status_code == 200
        
        timeline_data = timeline_response.json()
        artifact_types = [
            item["content"]["artifact_type"]
            for item in timeline_data["timeline"]
            if item["type"] == "artifact_ref"
        ]
        
        print(f"\nArtifact types ({len(artifact_types)}):")
        for j, art_type in enumerate(artifact_types, 1):
            print(f"  {j}. {art_type}")
        
        # Save to JSON
        output_file = output_dir / f"test{i}_timeline.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({
                "test_case": test["description"],
                "message": test["message"],
                "expected_workflow": test["expected_workflow"],
                "actual_workflow": data["workflow_type"],
                "conversation_id": conversation_id,
                "stage": data["stage"],
                "agent_reply": data["agent_reply"],
                "artifact_types": artifact_types,
                "full_timeline": timeline_data["timeline"]
            }, f, ensure_ascii=False, indent=2)
        
        print(f"Saved: {output_file}")
        
        # Verification
        if data["workflow_type"] != test["expected_workflow"]:
            print(f"[WARN] workflow_type mismatch: expected {test['expected_workflow']}, got {data['workflow_type']}")
        else:
            print(f"[OK] workflow_type: {data['workflow_type']}")
    
    print("\n" + "=" * 70)
    print("Verification complete!")
    print("\nGenerated files:")
    print("  screenshots/test1_timeline.json - Friend stock")
    print("  screenshots/test2_timeline.json - Strategy idea")
    print("  screenshots/test3_timeline.json - Context follow-up")
    print("\nNext: Compare these artifact_types with your browser screenshots")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
