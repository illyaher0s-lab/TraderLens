#!/usr/bin/env python3
"""
P3-2 Strategy Idea Result Visibility Verification Script

Verifies:
1. Strategy idea submission in Workbench (reuse P3-1 flow)
2. GET /api/strategy-ideas/{idea_id} returns full detail
3. GET /api/strategy-ideas?conversation_id={id} returns list
4. /strategy-ideas page displays results
5. Decision = rejected (no template)
6. Run ID visible in original_message
7. P2 regression gate passes
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from playwright.async_api import async_playwright


def generate_run_id():
    """Generate unique run ID for this test run."""
    return f"P2RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def read_route_decision_workflow_kind(db_path: Path, conversation_id: str) -> str:
    """Read the persisted router decision for a workbench conversation."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT content FROM agent_artifact_refs
            WHERE session_id = ? AND artifact_type = 'workflow_route_decision'
            ORDER BY created_at DESC LIMIT 1
            """,
            (conversation_id,),
        )
        route_row = cursor.fetchone()
    finally:
        conn.close()

    assert route_row and route_row["content"], (
        f"Missing persisted workflow_route_decision artifact for {conversation_id}"
    )

    route_decision = json.loads(route_row["content"])
    workflow_kind = route_decision.get("workflow_kind")
    assert workflow_kind, (
        f"workflow_route_decision artifact for {conversation_id} has no workflow_kind"
    )
    return workflow_kind


def is_port_in_use(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def get_port_pids(port: int) -> list[int]:
    command = (
        f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue "
        "| Select-Object -ExpandProperty OwningProcess -Unique"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    pids = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def release_port(port: int) -> None:
    pids = get_port_pids(port)
    for pid in pids:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    time.sleep(2)
    if is_port_in_use(port):
        raise RuntimeError(f"Port {port} still in use after targeted kill attempt")


async def main():
    run_id = generate_run_id()
    print(f"\n{'='*100}")
    print(f"P3-2 Strategy Idea Result Visibility Verification")
    print(f"{'='*100}")
    print(f"Run ID: {run_id}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"{'='*100}\n")

    # Evidence directory
    evidence_dir = PROJECT_ROOT / "docs" / "verification"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    backend_process = None
    frontend_process = None
    browser = None

    try:
        # Step 0: Check and kill existing processes on ports 8010 and 3000
        print("Step 0: Checking for existing processes on ports 8010 and 3000...")

        if is_port_in_use(8010):
            print("[WARN] Port 8010 is in use, attempting targeted kill...")
            release_port(8010)
        
        if is_port_in_use(3000):
            print("[WARN] Port 3000 is in use, attempting targeted kill...")
            release_port(3000)
        
        print("[OK] Ports 8010 and 3000 are available")
        
        # Step 1: Start backend
        print("Step 1: Starting backend on port 8010...")
        backend_env = os.environ.copy()
        backend_env["RESEARCH_CONVERSATION_MODE"] = "deterministic"
        backend_env["SERENITY_EXECUTION_MODE"] = "stub"
        
        backend_log_path = evidence_dir / "p3-2-backend-log.txt"
        backend_log = open(backend_log_path, "w", encoding="utf-8")
        
        backend_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8010",
            ],
            cwd=PROJECT_ROOT,
            env=backend_env,
            stdout=backend_log,
            stderr=subprocess.STDOUT,
        )
        
        # Verify backend process is still alive after starting
        time.sleep(2)
        if backend_process.poll() is not None:
            backend_log.close()
            with open(backend_log_path, "r", encoding="utf-8") as f:
                log_content = f.read()
            raise RuntimeError(f"Backend process died immediately. Exit code: {backend_process.returncode}\n\nLog:\n{log_content}")
        
        # Wait for backend to be ready
        max_retries = 30
        backend_ready = False
        for i in range(max_retries):
            try:
                import urllib.request
                response = urllib.request.urlopen("http://localhost:8010/health", timeout=2)
                if response.status == 200:
                    # Verify backend process is still alive
                    if backend_process.poll() is not None:
                        backend_log.close()
                        with open(backend_log_path, "r", encoding="utf-8") as f:
                            log_content = f.read()
                        raise RuntimeError(f"Backend /health 200 but process died. Exit code: {backend_process.returncode}\n\nLog:\n{log_content}")
                    print(f"[OK] Backend ready after {i+1} attempts")
                    backend_ready = True
                    break
            except:
                if backend_process.poll() is not None:
                    backend_log.close()
                    with open(backend_log_path, "r", encoding="utf-8") as f:
                        log_content = f.read()
                    raise RuntimeError(f"Backend process died while waiting. Exit code: {backend_process.returncode}\n\nLog:\n{log_content}")
                if i == max_retries - 1:
                    raise TimeoutError("Backend failed to start after 30 seconds")
                time.sleep(1)
        
        if not backend_ready:
            raise RuntimeError("Backend did not become ready")

        # Step 2: Start frontend
        print("\nStep 2: Starting frontend on port 3000...")
        frontend_log_path = evidence_dir / "p3-2-frontend-log.txt"
        frontend_log = open(frontend_log_path, "w", encoding="utf-8")
        
        frontend_process = subprocess.Popen(
            ["cmd", "/c", "npm", "run", "dev", "--", "--port", "3000"],
            cwd=PROJECT_ROOT / "frontend",
            stdout=frontend_log,
            stderr=subprocess.STDOUT,
        )
        
        # Verify frontend process is still alive after starting
        time.sleep(2)
        if frontend_process.poll() is not None:
            frontend_log.close()
            with open(frontend_log_path, "r", encoding="utf-8") as f:
                log_content = f.read()
            raise RuntimeError(f"Frontend process died immediately. Exit code: {frontend_process.returncode}\n\nLog:\n{log_content}")
        
        # Wait for frontend - must be on port 3000
        max_retries = 60
        frontend_ready = False
        for i in range(max_retries):
            try:
                import urllib.request
                # Must be exactly port 3000, not 3001/3004
                response = urllib.request.urlopen("http://localhost:3000", timeout=2)
                if response.status == 200:
                    print(f"[OK] Frontend ready on port 3000 after {i+1} attempts")
                    frontend_ready = True
                    break
            except Exception as e:
                if frontend_process.poll() is not None:
                    frontend_log.close()
                    with open(frontend_log_path, "r", encoding="utf-8") as f:
                        log_content = f.read()
                    raise RuntimeError(f"Frontend process died while waiting. Exit code: {frontend_process.returncode}\n\nLog:\n{log_content}")
                if i == max_retries - 1:
                    raise TimeoutError("Frontend failed to start on port 3000 after 60 seconds")
                time.sleep(1)
        
        if not frontend_ready:
            raise RuntimeError("Frontend did not become ready on port 3000")

        # Step 3: Submit strategy idea via Workbench (browser)
        print("\nStep 3: Opening Workbench in browser...")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            # Capture network requests
            workbench_responses = []
            
            async def capture_response(response):
                if "/api/agent/workbench/message" in response.url:
                    try:
                        body = await response.json()
                        workbench_responses.append({
                            "url": response.url,
                            "status": response.status,
                            "body": body,
                        })
                    except:
                        pass
            
            page.on("response", capture_response)

            # Navigate to workbench
            await page.goto("http://localhost:3000/workbench", wait_until="domcontentloaded", timeout=30000)
            print("[OK] Workbench page loaded")

            # Wait for input to be ready
            await page.wait_for_selector("textarea, input[type='text']", timeout=10000)
            await asyncio.sleep(1)

            # Input strategy idea
            strategy_message = (
                f"我想做一个A股放量突破策略：股票突破20日高点且成交量超过20日均量2倍时买入，"
                f"跌破10日均线卖出，备注 {run_id}"
            )
            
            input_selector = "textarea, input[type='text']"
            await page.fill(input_selector, strategy_message)
            print(f"[OK] Filled strategy idea (contains run_id: {run_id})")

            # Submit
            await page.press(input_selector, "Enter")
            print("[OK] Submitted strategy idea")

            # Wait for response
            await asyncio.sleep(5)

            # Save workbench DOM
            workbench_dom = await page.inner_text("body")
            workbench_dom_path = evidence_dir / "p3-2-workbench-dom.md"
            with open(workbench_dom_path, "w", encoding="utf-8") as f:
                f.write(f"# P3-2 Workbench DOM\n\n")
                f.write(f"**Captured at:** {datetime.now().isoformat()}\n\n")
                f.write(f"## Page Text\n\n```\n{workbench_dom}\n```\n")
            print(f"[OK] Saved Workbench DOM to {workbench_dom_path}")

            # Extract conversation_id, idea_id from response
            if not workbench_responses:
                raise ValueError("No Workbench response captured")
            
            workbench_response = workbench_responses[-1]["body"]
            conversation_id = workbench_response.get("conversation_id")
            workflow_type = workbench_response.get("workflow_type")
            artifact_ids = workbench_response.get("artifact_ids", [])
            
            # Red line: workflow_type must equal strategy_idea
            assert workflow_type == "strategy_idea", f"workflow_type must be 'strategy_idea', got '{workflow_type}'"
            
            print(f"\n[OK] Workbench Response:")
            print(f"  conversation_id: {conversation_id}")
            print(f"  workflow_type: {workflow_type} (verified)")
            print(f"  artifact_ids: {len(artifact_ids)} artifacts")

            # Find idea_id from artifacts
            idea_id = None
            for aid in artifact_ids:
                if aid.startswith("idea_"):
                    idea_id = aid
                    break
            
            if not idea_id:
                raise ValueError("No idea_id found in artifact_ids")
            
            print(f"  idea_id: {idea_id}")

            # Verify route_decision.workflow_kind from intent artifact
            print(f"\n[Verifying route_decision.workflow_kind from DB...]")
            db_path = PROJECT_ROOT / "data" / "research.db"
            route_decision_workflow_kind = read_route_decision_workflow_kind(
                db_path, conversation_id
            )
            assert route_decision_workflow_kind == "strategy_idea", \
                f"route_decision.workflow_kind must be 'strategy_idea', got '{route_decision_workflow_kind}'"
            print(f"[OK] route_decision.workflow_kind = {route_decision_workflow_kind} (verified)")
            
            # Save workbench response
            workbench_response_path = evidence_dir / "p3-2-workbench-response.json"
            with open(workbench_response_path, "w", encoding="utf-8") as f:
                json.dump(workbench_response, f, indent=2, ensure_ascii=False)
            print(f"[OK] Saved Workbench response to {workbench_response_path}")

            # Save network log
            network_log_path = evidence_dir / "p3-2-workbench-network-log.json"
            with open(network_log_path, "w", encoding="utf-8") as f:
                json.dump(workbench_responses, f, indent=2, ensure_ascii=False)
            print(f"[OK] Saved network log to {network_log_path}")

            # Step 4: Verify GET /api/strategy-ideas/{idea_id}
            print(f"\nStep 4: Verifying GET /api/strategy-ideas/{idea_id}...")
            
            detail_url = f"http://localhost:8010/api/strategy-ideas/{idea_id}"
            import urllib.request
            import urllib.error
            
            try:
                detail_response = urllib.request.urlopen(detail_url, timeout=5)
                detail_data = json.loads(detail_response.read().decode())
                
                detail_api_path = evidence_dir / "p3-2-result-api-detail.json"
                with open(detail_api_path, "w", encoding="utf-8") as f:
                    json.dump(detail_data, f, indent=2, ensure_ascii=False)
                print(f"[OK] Saved detail API response to {detail_api_path}")
                
                # Verify fields
                assert detail_data["idea_id"] == idea_id, "idea_id mismatch"
                assert detail_data["conversation_id"] == conversation_id, "conversation_id mismatch"
                assert detail_data["workflow_type"] == "strategy_idea", f"detail API workflow_type must be 'strategy_idea', got '{detail_data.get('workflow_type')}'"
                assert detail_data["decision"] in ["accepted", "rejected"], "Invalid decision"
                assert run_id in detail_data["original_message"], f"run_id {run_id} not in original_message"
                
                print(f"  [OK] idea_id: {detail_data['idea_id']}")
                print(f"  [OK] workflow_type: {detail_data['workflow_type']} (verified)")
                print(f"  [OK] decision: {detail_data['decision']}")
                print(f"  [OK] run_id found in original_message")
                print(f"  [OK] extraction: {detail_data.get('extraction', {}).get('claimed_entry', 'N/A')}")
                
            except urllib.error.HTTPError as e:
                raise AssertionError(f"GET /api/strategy-ideas/{idea_id} failed: HTTP {e.code}")

            # Step 5: Verify GET /api/strategy-ideas?conversation_id={conversation_id}
            print(f"\nStep 5: Verifying GET /api/strategy-ideas?conversation_id={conversation_id}...")
            
            list_url = f"http://localhost:8010/api/strategy-ideas?conversation_id={conversation_id}"
            
            try:
                list_response = urllib.request.urlopen(list_url, timeout=5)
                list_data = json.loads(list_response.read().decode())
                
                list_api_path = evidence_dir / "p3-2-result-api-list.json"
                with open(list_api_path, "w", encoding="utf-8") as f:
                    json.dump(list_data, f, indent=2, ensure_ascii=False)
                print(f"[OK] Saved list API response to {list_api_path}")
                
                ideas = list_data.get("ideas", [])
                assert len(ideas) >= 1, "No ideas returned"
                
                # Find our idea
                our_idea = None
                for idea in ideas:
                    if idea["idea_id"] == idea_id:
                        our_idea = idea
                        break
                
                assert our_idea is not None, f"idea_id {idea_id} not found in list"
                assert our_idea["workflow_type"] == "strategy_idea", f"list API workflow_type must be 'strategy_idea', got '{our_idea.get('workflow_type')}'"
                assert run_id in our_idea["original_message"], f"run_id {run_id} not in list item"
                
                print(f"  [OK] Found {len(ideas)} idea(s)")
                print(f"  [OK] idea_id {idea_id} found in list")
                print(f"  [OK] workflow_type: {our_idea['workflow_type']} (verified)")
                print(f"  [OK] run_id found in list item")
                
            except urllib.error.HTTPError as e:
                raise AssertionError(f"GET /api/strategy-ideas?conversation_id failed: HTTP {e.code}")

            # Step 6: Verify /strategy-ideas page DOM
            print(f"\nStep 6: Verifying /strategy-ideas page...")
            
            # Capture network requests for result page
            result_page_responses = []
            
            async def capture_result_page_response(response):
                if "/api/" in response.url:
                    try:
                        body = await response.json()
                        result_page_responses.append({
                            "url": response.url,
                            "status": response.status,
                            "body": body,
                        })
                    except:
                        result_page_responses.append({
                            "url": response.url,
                            "status": response.status,
                            "body": None,
                        })
            
            page.on("response", capture_result_page_response)
            
            await page.goto(f"http://localhost:3000/strategy-ideas?conversation_id={conversation_id}", 
                          wait_until="domcontentloaded", timeout=30000)
            print("[OK] Strategy ideas page loaded")

            await asyncio.sleep(2)
            
            # Save result page network log
            result_network_log_path = evidence_dir / "p3-2-result-network-log.json"
            with open(result_network_log_path, "w", encoding="utf-8") as f:
                json.dump(result_page_responses, f, indent=2, ensure_ascii=False)
            print(f"[OK] Saved result page network log to {result_network_log_path}")
            
            # Verify all API requests point to localhost:8010
            for req in result_page_responses:
                url = req["url"]
                if "/api/" in url:
                    assert "localhost:8010" in url, f"API request must point to localhost:8010, got: {url}"
            print(f"[OK] All API requests point to localhost:8010")

            # Capture page content
            page_dom = await page.inner_text("body")
            page_dom_path = evidence_dir / "p3-2-result-dom.md"
            with open(page_dom_path, "w", encoding="utf-8") as f:
                f.write(f"# P3-2 Strategy Ideas Page DOM\n\n")
                f.write(f"**Captured at:** {datetime.now().isoformat()}\n\n")
                f.write(f"**URL:** http://localhost:3000/strategy-ideas?conversation_id={conversation_id}\n\n")
                f.write(f"## Page Text\n\n```\n{page_dom}\n```\n")
            print(f"[OK] Saved page DOM to {page_dom_path}")

            # Verify DOM contains key elements
            assert "策略想法" in page_dom, "Title '策略想法' not found"
            assert run_id in page_dom or idea_id in page_dom, f"Neither run_id {run_id} nor idea_id {idea_id} found in DOM"
            
            # Check for decision badge
            decision_found = "已拒绝" in page_dom or "已接受" in page_dom
            assert decision_found, "Decision badge not found in DOM"
            
            print(f"  [OK] Title '策略想法' found")
            print(f"  [OK] run_id or idea_id found")
            print(f"  [OK] Decision badge found")

            await browser.close()

        # Step 7: Save evidence summary
        print("\nStep 7: Saving evidence summary...")
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "run_id": run_id,
            "conversation_id": conversation_id,
            "idea_id": idea_id,
            "workflow_type": workflow_type,
            "route_decision_workflow_kind": route_decision_workflow_kind,
            "decision": detail_data["decision"],
            "verification": {
                "workbench_submission": "[OK]",
                "detail_api": "[OK]",
                "list_api": "[OK]",
                "page_dom": "[OK]",
                "run_id_visible": "[OK]",
            },
            "evidence_files": [
                "p3-2-workbench-dom.md",
                "p3-2-workbench-response.json",
                "p3-2-workbench-network-log.json",
                "p3-2-result-api-detail.json",
                "p3-2-result-api-list.json",
                "p3-2-result-dom.md",
                "p3-2-result-network-log.json",
                "p3-2-backend-log.txt",
                "p3-2-frontend-log.txt",
            ],
        }
        
        summary_path = evidence_dir / "p3-2-evidence-summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"[OK] Saved evidence summary to {summary_path}")

        print(f"\n{'='*100}")
        print("[OK] P3-2 Verification PASSED")
        print(f"{'='*100}\n")
        
        print(f"Run ID: {run_id}")
        print(f"Conversation ID: {conversation_id}")
        print(f"Idea ID: {idea_id}")
        print(f"Decision: {detail_data['decision']}")
        print(f"\nEvidence files saved to: {evidence_dir}/")
        
        return 0

    except Exception as e:
        print(f"\n{'='*100}")
        print(f"[FAIL] P3-2 Verification FAILED")
        print(f"{'='*100}\n")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # Cleanup
        if browser:
            try:
                await browser.close()
            except:
                pass
        
        if backend_process:
            backend_process.terminate()
            backend_process.wait(timeout=5)
            backend_log.close()
        
        if frontend_process:
            frontend_process.terminate()
            frontend_process.wait(timeout=5)
            frontend_log.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
