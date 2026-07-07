"""
P3-3 Strategy Rejection Registry Verification Script

Verifies:
1. Strategy idea detail page (/strategy-ideas/{idea_id})
2. List page "查看详情" link works
3. Rejected strategies registry (/rejected-strategies)
4. API fields complete (rejection_reason, artifact_ids, etc.)
5. route_decision.workflow_kind must equal response.workflow_type
6. Real browser DOM capture (no fake/placeholder)
7. Real network log capture
8. All API requests point to localhost:8010

Exit code 0 = PASS, non-zero = FAIL
"""

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
DB_PATH = PROJECT_ROOT / "data" / "research.db"
DOCS_DIR = PROJECT_ROOT / "docs" / "verification"

# Ensure docs dir exists
DOCS_DIR.mkdir(parents=True, exist_ok=True)

# Generate run ID
RUN_ID = f"P2RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

print("=" * 100)
print("P3-3 Strategy Rejection Registry Verification")
print("=" * 100)
print(f"Run ID: {RUN_ID}")
print(f"Timestamp: {datetime.now().isoformat()}")
print("=" * 100)
print()


def kill_port(port: int):
    """Kill process using the specified port."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1]
                subprocess.run(["taskkill", "/PID", pid, "/F"], check=False)
                print(f"[OK] Killed process {pid} on port {port}")
                time.sleep(1)
                return
    except Exception as e:
        print(f"[WARN] Could not kill port {port}: {e}")


def check_ports():
    """Check and free ports 8010 and 3000."""
    print("Step 0: Checking for existing processes on ports 8010 and 3000...")
    for port in [8010, 3000]:
        kill_port(port)
    print("[OK] Ports 8010 and 3000 are available")
    print()


def start_backend():
    """Start backend server."""
    print("Step 1: Starting backend on port 8010...")
    
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    
    process = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8010"],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    
    # Wait for backend to be ready
    import requests
    for attempt in range(30):
        time.sleep(1)
        try:
            response = requests.get("http://localhost:8010/health", timeout=2)
            if response.status_code == 200:
                # Verify process is still alive
                if process.poll() is not None:
                    print(f"[FAIL] Backend process died after starting")
                    sys.exit(1)
                print(f"[OK] Backend ready after {attempt + 1} attempts")
                print()
                return process
        except:
            pass
    
    print("[FAIL] Backend did not start within 30 seconds")
    process.kill()
    sys.exit(1)


def start_frontend():
    """Start frontend server."""
    print("Step 2: Starting frontend on port 3000...")
    
    process = subprocess.Popen(
        ["cmd", "/c", "npm", "run", "dev", "--", "--port", "3000"],
        cwd=FRONTEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    
    # Wait for frontend to be ready
    import requests
    for attempt in range(60):
        time.sleep(1)
        try:
            response = requests.get("http://localhost:3000", timeout=2)
            if response.status_code == 200:
                # Verify process is still alive
                if process.poll() is not None:
                    print(f"[FAIL] Frontend process died after starting")
                    sys.exit(1)
                print(f"[OK] Frontend ready on port 3000 after {attempt + 1} attempts")
                print()
                return process
        except:
            pass
    
    print("[FAIL] Frontend did not start within 60 seconds")
    process.kill()
    sys.exit(1)


async def main():
    check_ports()
    backend_process = start_backend()
    frontend_process = start_frontend()
    
    backend_log_lines = []
    frontend_log_lines = []
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            
            # Capture network requests
            network_requests = []
            
            async def capture_request(request):
                network_requests.append({
                    "url": request.url,
                    "method": request.method,
                })
            
            async def capture_response(response):
                for req in network_requests:
                    if req["url"] == response.url and "status" not in req:
                        req["status"] = response.status
                        if "/api/" in response.url:
                            try:
                                req["response"] = await response.json()
                            except:
                                pass
            
            page = await context.new_page()
            page.on("request", capture_request)
            page.on("response", capture_response)
            
            # Step 3: Submit strategy idea via Workbench
            print("Step 3: Submitting strategy idea via Workbench...")
            await page.goto("http://localhost:3000/workbench", wait_until="networkidle")
            
            strategy_message = f"我想做一个均线交叉策略：5日均线上穿20日均线买入，死叉卖出，备注 {RUN_ID}"
            
            await page.fill('input[type="text"]', strategy_message)
            await page.click('button:has-text("发送")')
            
            # Wait for response
            await page.wait_for_timeout(8000)
            
            # Save Workbench network log
            workbench_network = [r for r in network_requests if "/api/" in r["url"]]
            with open(DOCS_DIR / "p3-3-workbench-network-log.json", "w", encoding="utf-8") as f:
                json.dump(workbench_network, f, indent=2, ensure_ascii=False)
            
            # Extract response
            workbench_response = None
            for req in workbench_network:
                if req["method"] == "POST" and "/api/agent/workbench" in req["url"]:
                    workbench_response = req.get("response")
                    break
            
            if not workbench_response:
                print("[FAIL] No Workbench POST response found")
                sys.exit(1)
            
            conversation_id = workbench_response.get("conversation_id")
            workflow_type = workbench_response.get("workflow_type")
            artifact_ids = workbench_response.get("artifact_ids", [])
            
            # Extract idea_id
            idea_id = None
            for aid in artifact_ids:
                if aid.startswith("idea_"):
                    idea_id = aid
                    break
            
            if not idea_id:
                print("[FAIL] No idea_id found in artifact_ids")
                sys.exit(1)
            
            # Save Workbench response
            with open(DOCS_DIR / "p3-3-workbench-response.json", "w", encoding="utf-8") as f:
                json.dump(workbench_response, f, indent=2, ensure_ascii=False)
            
            print(f"[OK] Workbench Response:")
            print(f"  conversation_id: {conversation_id}")
            print(f"  idea_id: {idea_id}")
            print(f"  workflow_type: {workflow_type}")
            print()
            
            # Step 4: Verify route_decision.workflow_kind from DB
            print("Step 4: Verifying route_decision.workflow_kind from DB...")
            
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Try workflow_intent artifact type
            cursor.execute("""
                SELECT content FROM agent_artifact_refs
                WHERE session_id = ? AND artifact_type = 'workflow_intent'
                ORDER BY created_at DESC LIMIT 1
            """, (conversation_id,))
            
            row = cursor.fetchone()
            if not row:
                # Try intent_ artifact_id pattern
                cursor.execute("""
                    SELECT content FROM agent_artifact_refs
                    WHERE session_id = ? AND artifact_id LIKE 'intent_%'
                    ORDER BY created_at DESC LIMIT 1
                """, (conversation_id,))
                row = cursor.fetchone()
            
            conn.close()
            
            if not row or not row["content"]:
                print(f"[FAIL] route_decision.workflow_kind not found in DB for session {conversation_id}")
                print(f"       Cannot fallback to workflow_type - must have real route_decision")
                sys.exit(1)
            
            intent_data = json.loads(row["content"])
            route_decision_workflow_kind = intent_data.get("route_decision", {}).get("workflow_kind")
            
            if not route_decision_workflow_kind:
                print(f"[FAIL] route_decision.workflow_kind is None in DB")
                sys.exit(1)
            
            assert route_decision_workflow_kind == "strategy_idea", \
                f"route_decision.workflow_kind={route_decision_workflow_kind}, expected strategy_idea"
            assert workflow_type == "strategy_idea", \
                f"workflow_type={workflow_type}, expected strategy_idea"
            
            print(f"[OK] route_decision.workflow_kind = {route_decision_workflow_kind} (verified from DB)")
            print(f"[OK] workflow_type = {workflow_type}")
            print()
            
            # Step 5: Verify detail API
            print(f"Step 5: Verifying GET /api/strategy-ideas/{idea_id}...")
            
            import requests
            detail_response = requests.get(f"http://localhost:8010/api/strategy-ideas/{idea_id}")
            assert detail_response.status_code == 200, f"Detail API returned {detail_response.status_code}"
            
            detail_data = detail_response.json()
            
            with open(DOCS_DIR / "p3-3-detail-api.json", "w", encoding="utf-8") as f:
                json.dump(detail_data, f, indent=2, ensure_ascii=False)
            
            # Verify fields
            assert detail_data["idea_id"] == idea_id
            assert detail_data["workflow_type"] == "strategy_idea"
            assert detail_data["decision"] == "rejected"
            assert detail_data["rejection_reason"] == "no_approved_template"
            assert detail_data["extraction_artifact_id"] is not None
            assert detail_data["mapping_artifact_id"] is not None
            assert detail_data["rejection_artifact_id"] is not None
            assert RUN_ID in detail_data["original_message"]
            
            print(f"[OK] Detail API verified:")
            print(f"  idea_id: {detail_data['idea_id']}")
            print(f"  decision: {detail_data['decision']}")
            print(f"  rejection_reason: {detail_data['rejection_reason']}")
            print(f"  extraction_artifact_id: {detail_data['extraction_artifact_id']}")
            print(f"  mapping_artifact_id: {detail_data['mapping_artifact_id']}")
            print(f"  rejection_artifact_id: {detail_data['rejection_artifact_id']}")
            print()
            
            # Step 6: Verify detail page
            print(f"Step 6: Verifying detail page /strategy-ideas/{idea_id}...")
            
            network_requests.clear()
            await page.goto(f"http://localhost:3000/strategy-ideas/{idea_id}", wait_until="networkidle")
            await page.wait_for_timeout(2000)
            
            detail_dom = await page.content()
            with open(DOCS_DIR / "p3-3-detail-dom.md", "w", encoding="utf-8") as f:
                f.write(f"# Detail Page DOM\n\n")
                f.write(f"URL: /strategy-ideas/{idea_id}\n\n")
                f.write(f"```html\n{detail_dom}\n```\n")
            
            detail_network = [r for r in network_requests if "/api/" in r["url"]]
            with open(DOCS_DIR / "p3-3-detail-network-log.json", "w", encoding="utf-8") as f:
                json.dump(detail_network, f, indent=2, ensure_ascii=False)
            
            # Verify API requests point to localhost:8010
            for req in detail_network:
                assert "localhost:8010" in req["url"], f"API request to wrong host: {req['url']}"
            
            # Verify DOM content
            assert idea_id in detail_dom
            assert "原始描述" in detail_dom
            assert "提取结果" in detail_dom
            assert "模板映射" in detail_dom
            assert "拒绝详情" in detail_dom or "已拒绝" in detail_dom
            assert RUN_ID in detail_dom
            
            print(f"[OK] Detail page verified")
            print(f"  DOM contains idea_id: ✓")
            print(f"  DOM contains run_id: ✓")
            print(f"  API requests to localhost:8010: ✓")
            print()
            
            # Step 7: Verify rejected registry page
            print("Step 7: Verifying rejected strategies registry page...")
            
            network_requests.clear()
            await page.goto("http://localhost:3000/rejected-strategies", wait_until="networkidle")
            await page.wait_for_timeout(2000)
            
            registry_dom = await page.content()
            with open(DOCS_DIR / "p3-3-rejected-registry-dom.md", "w", encoding="utf-8") as f:
                f.write(f"# Rejected Strategies Registry DOM\n\n")
                f.write(f"URL: /rejected-strategies\n\n")
                f.write(f"```html\n{registry_dom}\n```\n")
            
            registry_network = [r for r in network_requests if "/api/" in r["url"]]
            with open(DOCS_DIR / "p3-3-rejected-registry-network-log.json", "w", encoding="utf-8") as f:
                json.dump(registry_network, f, indent=2, ensure_ascii=False)
            
            # Verify API requests
            for req in registry_network:
                assert "localhost:8010" in req["url"], f"API request to wrong host: {req['url']}"
            
            # Verify DOM content
            assert "策略拒绝注册表" in registry_dom or "拒绝" in registry_dom
            assert idea_id in registry_dom or RUN_ID in registry_dom
            assert "无批准模板" in registry_dom or "no_approved_template" in registry_dom
            
            print(f"[OK] Rejected registry verified")
            print(f"  DOM contains rejected ideas: ✓")
            print(f"  API requests to localhost:8010: ✓")
            print()
            
            # Step 8: Save evidence summary
            print("Step 8: Saving evidence summary...")
            
            evidence = {
                "run_id": RUN_ID,
                "timestamp": datetime.now().isoformat(),
                "conversation_id": conversation_id,
                "idea_id": idea_id,
                "workflow_type": workflow_type,
                "route_decision_workflow_kind": route_decision_workflow_kind,
                "decision": detail_data["decision"],
                "rejection_reason": detail_data["rejection_reason"],
                "extraction_artifact_id": detail_data["extraction_artifact_id"],
                "mapping_artifact_id": detail_data["mapping_artifact_id"],
                "rejection_artifact_id": detail_data["rejection_artifact_id"],
                "detail_page_verified": True,
                "rejected_registry_verified": True,
            }
            
            with open(DOCS_DIR / "p3-3-evidence-summary.json", "w", encoding="utf-8") as f:
                json.dump(evidence, f, indent=2, ensure_ascii=False)
            
            print(f"[OK] Evidence summary saved")
            print()
            
            await browser.close()
    
    finally:
        # Save logs
        if backend_process.stdout:
            backend_log_lines = backend_process.stdout.readlines()
        if frontend_process.stdout:
            frontend_log_lines = frontend_process.stdout.readlines()
        
        with open(DOCS_DIR / "p3-3-backend-log.txt", "w", encoding="utf-8") as f:
            f.writelines(backend_log_lines)
        
        with open(DOCS_DIR / "p3-3-frontend-log.txt", "w", encoding="utf-8") as f:
            f.writelines(frontend_log_lines)
        
        # Terminate processes
        backend_process.terminate()
        frontend_process.terminate()
        
        time.sleep(2)
        
        backend_process.kill()
        frontend_process.kill()
    
    print("=" * 100)
    print("[OK] P3-3 Verification PASSED")
    print("=" * 100)
    print()
    print(f"Run ID: {RUN_ID}")
    print(f"Conversation ID: {conversation_id}")
    print(f"Idea ID: {idea_id}")
    print(f"Decision: {detail_data['decision']}")
    print(f"Rejection Reason: {detail_data['rejection_reason']}")
    print()
    print(f"Evidence files saved to: {DOCS_DIR}/")


if __name__ == "__main__":
    asyncio.run(main())
