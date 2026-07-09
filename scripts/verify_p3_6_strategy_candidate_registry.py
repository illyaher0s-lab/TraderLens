"""
P3-6 Strategy Idea Candidate Registry Verification

Verifies that strategy ideas with no template fit are visible as candidates:
- candidate_status = candidate_unapproved
- candidate_reason = no_approved_template_fit
- required_next_step = template_approval_required
- live_eligible = false
- Cannot trade / No signals
"""

import sys
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))
from runtime_process_helpers import (
    start_backend,
    wait_for_http,
    check_and_release_ports,
)


def run_verification():
    """Run P3-6 verification."""
    print("=" * 80)
    print("P3-6 STRATEGY IDEA CANDIDATE REGISTRY VERIFICATION")
    print("=" * 80)
    
    run_id = f"P2RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"\n[INFO] Run ID: {run_id}\n")
    
    evidence_dir = Path(__file__).parent.parent / "docs" / "verification"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    backend_process = None
    frontend_process = None
    
    try:
        # Step 1: Clean up ports
        print("[STEP 1] Checking and releasing ports...")
        check_and_release_ports([8010, 3010])
        print("[OK] Ports ready\n")
        
        # Step 2: Start backend
        print("[STEP 2] Starting backend...")
        backend_process = start_backend()
        wait_for_http("http://localhost:8010/health")
        print("[OK] Backend started\n")
        
        # Step 3: Start frontend
        print("[STEP 3] Starting frontend...")
        frontend_log_path = evidence_dir / "p3-6-frontend-log.txt"
        with open(frontend_log_path, "w", encoding="utf-8") as log_file:
            frontend_process = subprocess.Popen(
                "npm run dev",
                cwd=Path(__file__).parent.parent / "frontend",
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                shell=True,
            )
        
        wait_for_http("http://localhost:3010")
        print("[OK] Frontend started\n")
        
        # Step 4: Submit strategy idea via Workbench
        print("[STEP 4] Submitting strategy idea via Workbench...")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            
            # Listen to network requests
            network_log = []
            workbench_response_promise = []
            
            def log_request(request):
                network_log.append({
                    "url": request.url,
                    "method": request.method,
                    "timestamp": datetime.now().isoformat(),
                })
            
            def log_response(response):
                for entry in network_log:
                    if entry["url"] == response.url and "status" not in entry:
                        entry["status"] = response.status
                        if "/api/agent/workbench/message" in response.url and response.request.method == "POST":
                            try:
                                body = response.json()
                                entry["response_body"] = body
                                workbench_response_promise.append(body)
                            except:
                                pass
            
            context.on("request", log_request)
            context.on("response", log_response)
            
            page = context.new_page()
            page.goto("http://localhost:3010/workbench", wait_until="networkidle")
            
            # Wait for input to be visible
            page.wait_for_selector("input[type='text'], input:not([type])", state="visible", timeout=10000)
            
            # Submit strategy idea with run_id
            strategy_text = f"[{run_id}] 我有个策略想法：下午两点半后，如果看到成交量放大且股价突破前高，就买入，第二天早盘卖出。"
            
            input_field = page.locator("input[type='text'], input:not([type])").first
            input_field.fill(strategy_text)
            
            # Wait for workbench response before submitting
            with page.expect_response(lambda r: "/api/agent/workbench/message" in r.url and r.request.method == "POST") as response_info:
                input_field.press("Enter")
            
            # Get the response
            response = response_info.value
            workbench_response = response.json()
            workbench_response_promise.append(workbench_response)
            
            # Additional wait for UI update
            time.sleep(2)
            
            # Save Workbench DOM
            workbench_dom = page.content()
            workbench_dom_path = evidence_dir / "p3-6-workbench-dom.md"
            with open(workbench_dom_path, "w", encoding="utf-8") as f:
                f.write(f"# Workbench DOM - {run_id}\n\n")
                f.write(workbench_dom)
            
            # Save network log
            network_log_path = evidence_dir / "p3-6-workbench-network-log.json"
            with open(network_log_path, "w", encoding="utf-8") as f:
                json.dump(network_log, f, indent=2, ensure_ascii=False)
            
            # Extract conversation_id from response
            conversation_id = None
            
            if workbench_response_promise:
                workbench_response = workbench_response_promise[0]
                conversation_id = workbench_response.get("conversation_id")
            
            if not workbench_response:
                # Fallback: search network log
                for entry in network_log:
                    if "/api/agent/workbench/message" in entry["url"] and entry.get("response_body"):
                        workbench_response = entry["response_body"]
                        conversation_id = workbench_response.get("conversation_id")
                        break
            
            if not conversation_id:
                print(f"[FAIL] Failed to extract conversation_id from Workbench response")
                print(f"  Network log entries: {len(network_log)}")
                print(f"  Workbench responses captured: {len(workbench_response_promise)}")
                return 1
            
            print(f"[OK] Submitted strategy idea")
            print(f"  conversation_id: {conversation_id}")
            
            # Save Workbench response
            response_path = evidence_dir / "p3-6-workbench-response.json"
            with open(response_path, "w", encoding="utf-8") as f:
                json.dump(workbench_response, f, indent=2, ensure_ascii=False)
            
            browser.close()
        
        # Step 5: Verify idea via API
        print("\n[STEP 5] Verifying strategy idea via API...")
        
        import urllib.request
        
        # Get list of ideas for this conversation
        list_url = f"http://localhost:8010/api/strategy-ideas?conversation_id={conversation_id}"
        with urllib.request.urlopen(list_url) as response:
            list_data = json.loads(response.read().decode())
        
        list_api_path = evidence_dir / "p3-6-result-api-list.json"
        with open(list_api_path, "w", encoding="utf-8") as f:
            json.dump(list_data, f, indent=2, ensure_ascii=False)
        
        ideas = list_data.get("ideas", [])
        if not ideas:
            print(f"[FAIL] No ideas found for conversation {conversation_id}")
            return 1
        
        # Get the most recent idea
        idea = ideas[0]
        idea_id = idea["idea_id"]
        
        print(f"[OK] Found idea: {idea_id}")
        
        # Verify idea belongs to this run
        if run_id not in idea.get("original_message", ""):
            print(f"[FAIL] Idea does not belong to this run")
            print(f"  Expected run_id: {run_id}")
            print(f"  Actual message: {idea.get('original_message', '')[:100]}")
            return 1
        
        print(f"[OK] Idea belongs to run {run_id}")
        
        # Get detail
        detail_url = f"http://localhost:8010/api/strategy-ideas/{idea_id}"
        with urllib.request.urlopen(detail_url) as response:
            detail_data = json.loads(response.read().decode())
        
        detail_api_path = evidence_dir / "p3-6-result-api-detail.json"
        with open(detail_api_path, "w", encoding="utf-8") as f:
            json.dump(detail_data, f, indent=2, ensure_ascii=False)
        
        # Verify decision
        decision = detail_data.get("decision")
        if decision != "rejected":
            print(f"[FAIL] Expected decision=rejected, got: {decision}")
            return 1
        
        print(f"[OK] decision: {decision}")
        
        # Verify mapped_template_id is null
        mapped_template_id = detail_data.get("mapped_template_id")
        if mapped_template_id is not None:
            print(f"[FAIL] Expected mapped_template_id=null, got: {mapped_template_id}")
            return 1
        
        print(f"[OK] mapped_template_id: null")
        
        # Verify final_reason
        final_reason = detail_data.get("final_reason")
        if final_reason != "no_template_fit":
            print(f"[FAIL] Expected final_reason=no_template_fit, got: {final_reason}")
            return 1
        
        print(f"[OK] final_reason: {final_reason}")
        
        # Verify live_eligible
        live_eligible = detail_data.get("live_eligible", True)
        if live_eligible:
            print(f"[FAIL] Expected live_eligible=false, got: {live_eligible}")
            return 1
        
        print(f"[OK] live_eligible: false")
        
        # Verify candidate_status
        candidate_status = detail_data.get("candidate_status")
        if candidate_status != "candidate_unapproved":
            print(f"[FAIL] Expected candidate_status=candidate_unapproved, got: {candidate_status}")
            return 1
        
        print(f"[OK] candidate_status: {candidate_status}")
        
        # Verify candidate_reason
        candidate_reason = detail_data.get("candidate_reason")
        if candidate_reason != "no_approved_template_fit":
            print(f"[FAIL] Expected candidate_reason=no_approved_template_fit, got: {candidate_reason}")
            return 1
        
        print(f"[OK] candidate_reason: {candidate_reason}")
        
        # Verify required_next_step
        required_next_step = detail_data.get("required_next_step")
        if required_next_step != "template_approval_required":
            print(f"[FAIL] Expected required_next_step=template_approval_required, got: {required_next_step}")
            return 1
        
        print(f"[OK] required_next_step: {required_next_step}")
        
        # Step 6: Verify candidate_status filter
        print("\n[STEP 6] Verifying candidate_status filter...")
        
        candidate_list_url = f"http://localhost:8010/api/strategy-ideas?candidate_status=candidate_unapproved"
        with urllib.request.urlopen(candidate_list_url) as response:
            candidate_list_data = json.loads(response.read().decode())
        
        candidate_list_path = evidence_dir / "p3-6-candidate-api-list.json"
        with open(candidate_list_path, "w", encoding="utf-8") as f:
            json.dump(candidate_list_data, f, indent=2, ensure_ascii=False)
        
        candidate_ideas = candidate_list_data.get("ideas", [])
        candidate_idea_ids = [i["idea_id"] for i in candidate_ideas]
        
        if idea_id not in candidate_idea_ids:
            print(f"[FAIL] Idea {idea_id} not found in candidate list")
            return 1
        
        print(f"[OK] Idea found in candidate list ({len(candidate_ideas)} total)")
        
        # Step 7: Verify detail page DOM
        print("\n[STEP 7] Verifying detail page DOM...")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            
            # Listen to network
            detail_network_log = []
            def log_detail_request(request):
                detail_network_log.append({
                    "url": request.url,
                    "method": request.method,
                })
            
            context.on("request", log_detail_request)
            
            page = context.new_page()
            page.goto(f"http://localhost:3010/strategy-ideas/{idea_id}", wait_until="networkidle")
            
            time.sleep(2)
            
            # Verify DOM content
            dom_content = page.content()
            
            # Check for candidate section
            if "候选策略状态" not in dom_content:
                print(f"[FAIL] DOM does not show candidate section")
                return 1
            
            print(f"[OK] DOM shows candidate section")
            
            # Check for "不可交易 / 不生成信号"
            if "不可交易" not in dom_content or "不生成信号" not in dom_content:
                print(f"[FAIL] DOM does not show 'no trading / no signals' warning")
                return 1
            
            print(f"[OK] DOM shows 'no trading / no signals' warning")
            
            # Save DOM
            detail_dom_path = evidence_dir / f"p3-6-idea-detail-dom-{idea_id}.md"
            with open(detail_dom_path, "w", encoding="utf-8") as f:
                f.write(f"# Strategy Idea Detail DOM - {idea_id}\n\n")
                f.write(dom_content)
            
            # Save network log
            detail_network_path = evidence_dir / "p3-6-result-network-log.json"
            with open(detail_network_path, "w", encoding="utf-8") as f:
                json.dump(detail_network_log, f, indent=2, ensure_ascii=False)
            
            # Verify all API requests go to localhost:8010
            for entry in detail_network_log:
                if "/api/" in entry["url"]:
                    if "localhost:8010" not in entry["url"]:
                        print(f"[FAIL] API request not to localhost:8010: {entry['url']}")
                        return 1
            
            print(f"[OK] All API requests to localhost:8010")
            
            browser.close()
        
        # Step 8: Verify candidate registry page
        print("\n[STEP 8] Verifying candidate registry page...")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("http://localhost:3010/candidate-strategies", wait_until="networkidle")
            
            time.sleep(2)
            
            # Verify DOM content
            dom_content = page.content()
            
            # Check for idea_id
            if idea_id not in dom_content:
                print(f"[FAIL] Candidate registry does not show idea {idea_id}")
                return 1
            
            print(f"[OK] Candidate registry shows idea {idea_id}")
            
            # Check for run_id
            if run_id not in dom_content:
                print(f"[FAIL] Candidate registry does not show run_id {run_id}")
                return 1
            
            print(f"[OK] Candidate registry shows run_id")
            
            # Check for candidate_status
            if "候选未批准" not in dom_content:
                print(f"[FAIL] Candidate registry does not show candidate status")
                return 1
            
            print(f"[OK] Candidate registry shows candidate status")
            
            # Save DOM
            candidate_dom_path = evidence_dir / "p3-6-candidate-registry-dom.md"
            with open(candidate_dom_path, "w", encoding="utf-8") as f:
                f.write(f"# Candidate Registry DOM - {run_id}\n\n")
                f.write(dom_content)
            
            browser.close()
        
        # Step 9: Save evidence summary
        print("\n[STEP 9] Saving evidence summary...")
        
        evidence_summary = {
            "run_id": run_id,
            "conversation_id": conversation_id,
            "idea_id": idea_id,
            "decision": decision,
            "mapped_template_id": mapped_template_id,
            "final_reason": final_reason,
            "live_eligible": live_eligible,
            "candidate_status": candidate_status,
            "candidate_reason": candidate_reason,
            "required_next_step": required_next_step,
            "verification_timestamp": datetime.now().isoformat(),
        }
        
        summary_path = evidence_dir / "p3-6-evidence-summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(evidence_summary, f, indent=2, ensure_ascii=False)
        
        print(f"[OK] Evidence summary saved")
        
        print("\n" + "=" * 80)
        print("P3-6 VERIFICATION PASSED")
        print("=" * 80)
        return 0
        
    except Exception as e:
        print(f"\n[FAIL] Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
        
    finally:
        # Cleanup
        if frontend_process:
            frontend_process.terminate()
            try:
                frontend_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                frontend_process.kill()
        
        if backend_process:
            backend_process.terminate()
            try:
                backend_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend_process.kill()


if __name__ == "__main__":
    exit_code = run_verification()
    sys.exit(exit_code)
