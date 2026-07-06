#!/usr/bin/env python3
"""
P3-1 Strategy Idea API-only Verification (Simplified)

Tests strategy_idea workflow through direct API calls.
"""

import json
import sys
import time
import requests
from datetime import datetime
from pathlib import Path

# Fix Windows encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.runtime_test_helpers import generate_run_id

print("=" * 100)
print("P3-1 Strategy Idea API-only Verification")
print("=" * 100)
print()

run_id = generate_run_id()
print(f"Run ID: {run_id}")
print()

def main():
    # Check if backend is running
    print("[1/3] Checking backend...")
    try:
        response = requests.get("http://localhost:8010/api/health/runtime", timeout=5)
        if response.status_code == 200:
            print("✅ Backend is running")
        else:
            print(f"FAIL: Backend returned {response.status_code}")
            return 1
    except requests.exceptions.ConnectionError:
        print("FAIL: Backend not running on port 8010")
        print("Please start backend: python -m uvicorn backend.main:app --host 127.0.0.1 --port 8010")
        return 1
    print()
    
    # Submit strategy idea
    print("[2/3] Submitting strategy idea...")
    strategy_message = f"我想做一个A股放量突破策略：股票突破20日高点且成交量超过20日均量2倍时买入，跌破10日均线卖出，备注 {run_id}"
    print(f"Message: {strategy_message}")
    
    try:
        response = requests.post(
            "http://localhost:8010/api/agent/workbench/message",
            json={"message": strategy_message},
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"FAIL: POST returned {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return 1
        
        response_data = response.json()
        print("✅ POST successful")
        
        # Save response
        response_path = PROJECT_ROOT / "docs/verification/p3-1-api-response.json"
        response_path.parent.mkdir(parents=True, exist_ok=True)
        with open(response_path, "w", encoding="utf-8") as f:
            json.dump(response_data, f, indent=2, ensure_ascii=False)
        print(f"Saved response to {response_path.relative_to(PROJECT_ROOT)}")
        
    except Exception as e:
        print(f"FAIL: Exception during POST: {e}")
        return 1
    print()
    
    # Verify response
    print("[3/3] Verifying response...")
    
    workflow_type = response_data.get("workflow_type")
    artifact_ids = response_data.get("artifact_ids", [])
    agent_reply = response_data.get("agent_reply", "")
    
    print(f"workflow_type: {workflow_type}")
    print(f"artifact_ids: {artifact_ids}")
    print(f"agent_reply length: {len(agent_reply)} chars")
    print()
    
    # Check workflow_type
    if workflow_type != "strategy_idea":
        print(f"FAIL: Expected workflow_type='strategy_idea', got '{workflow_type}'")
        return 1
    print("✅ workflow_type is strategy_idea")
    
    # Check artifact_ids
    if not artifact_ids:
        print("FAIL: No artifact_ids returned")
        return 1
    print(f"✅ {len(artifact_ids)} artifacts returned")
    
    # Check not clarification
    if any("clarify" in aid.lower() for aid in artifact_ids):
        print("FAIL: Response is clarification")
        return 1
    print("✅ Not a clarification")
    
    # Check for reject/accept
    has_reject = "reject" in agent_reply.lower() or "拒绝" in agent_reply
    has_accept = "accept" in agent_reply.lower() or "接受" in agent_reply or "通过" in agent_reply
    
    if has_reject:
        print("✅ Strategy REJECTED (expected, no template library)")
    elif has_accept:
        print("⚠️  Strategy ACCEPTED (unexpected)")
    else:
        print("⚠️  No clear accept/reject in reply")
    
    # Save summary
    summary = {
        "run_id": run_id,
        "strategy_message": strategy_message,
        "timestamp": datetime.now().isoformat(),
        "workflow_type": workflow_type,
        "artifact_ids": artifact_ids,
        "has_reject": has_reject,
        "has_accept": has_accept,
        "agent_reply_preview": agent_reply[:300],
    }
    
    summary_path = PROJECT_ROOT / "docs/verification/p3-1-api-summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"Saved summary to {summary_path.relative_to(PROJECT_ROOT)}")
    print()
    
    print("=" * 100)
    print("✅ P3-1 API VERIFICATION PASSED")
    print("=" * 100)
    print()
    print("Summary:")
    print(f"  Run ID: {run_id}")
    print(f"  Workflow Type: {workflow_type}")
    print(f"  Artifacts: {len(artifact_ids)}")
    print(f"  Result: {'REJECTED' if has_reject else 'ACCEPTED' if has_accept else 'UNCLEAR'}")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
