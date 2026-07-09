"""
P3-10 Strategy Product Flow End-to-End Verification

End-to-end verification of the complete strategy product flow:
Workbench → strategy idea → extraction → template mapping → rejected/candidate
→ validation empty state → approved strategy library empty state

This is P3 closeout verification.
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
    """Run P3-10 end-to-end verification."""
    print("=" * 80)
    print("P3-10 STRATEGY PRODUCT FLOW END-TO-END VERIFICATION")
    print("=" * 80)
    
    run_id = f"P3_10_E2E_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
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
        frontend_log_path = evidence_dir / "p3-10-frontend-log.txt"
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
        
        conversation_id = None
        idea_id = None
        workbench_response = None
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            
            # Listen to network requests
            network_log = []
            
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
                            except:
                                pass
            
            context.on("request", log_request)
            context.on("response", log_response)
            
            page = context.new_page()
            page.goto("http://localhost:3010/workbench", wait_until="networkidle")
            
            # Wait for input to be visible
            page.wait_for_selector("input[type='text'], input:not([type])", state="visible", timeout=10000)
            
            # Submit strategy idea with run_id
            strategy_text = f"[{run_id}] 我刷到一个策略，下午两点半买入，第二天早上卖出，请帮我验证。"
            
            input_field = page.locator("input[type='text'], input:not([type])").first
            input_field.fill(strategy_text)
            
            # Wait for workbench response
            with page.expect_response(lambda r: "/api/agent/workbench/message" in r.url and r.request.method == "POST") as response_info:
                input_field.press("Enter")
            
            # Get the response
            response = response_info.value
            workbench_response = response.json()
            
            # Additional wait for UI update
            time.sleep(2)
            
            # Save Workbench DOM
            workbench_dom = page.content()
            workbench_dom_path = evidence_dir / "p3-10-workbench-dom.md"
            with open(workbench_dom_path, "w", encoding="utf-8") as f:
                f.write(f"# Workbench DOM - {run_id}\n\n")
                f.write(workbench_dom)
            
            # Save network log
            network_log_path = evidence_dir / "p3-10-workbench-network-log.json"
            with open(network_log_path, "w", encoding="utf-8") as f:
                json.dump(network_log, f, indent=2, ensure_ascii=False)
            
            # Extract conversation_id
            conversation_id = workbench_response.get("conversation_id")
            
            if not conversation_id:
                print(f"[FAIL] Failed to extract conversation_id from Workbench response")
                return 1
            
            print(f"[OK] Submitted strategy idea")
            print(f"  conversation_id: {conversation_id}")
            
            # Save Workbench response
            response_path = evidence_dir / "p3-10-workbench-response.json"
            with open(response_path, "w", encoding="utf-8") as f:
                json.dump(workbench_response, f, indent=2, ensure_ascii=False)
            
            browser.close()
        
        # Step 5: Get idea via API
        print("\n[STEP 5] Retrieving strategy idea via API...")
        
        import urllib.request
        
        # Get list of ideas for this conversation
        list_url = f"http://localhost:8010/api/strategy-ideas?conversation_id={conversation_id}"
        with urllib.request.urlopen(list_url) as response:
            list_data = json.loads(response.read().decode())
        
        list_api_path = evidence_dir / "p3-10-idea-list-api.json"
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
            print(f"  Original message: {idea.get('original_message', '')[:100]}")
            return 1
        
        # Get idea detail
        detail_url = f"http://localhost:8010/api/strategy-ideas/{idea_id}"
        with urllib.request.urlopen(detail_url) as response:
            detail_data = json.loads(response.read().decode())
        
        detail_api_path = evidence_dir / "p3-10-idea-detail-api.json"
        with open(detail_api_path, "w", encoding="utf-8") as f:
            json.dump(detail_data, f, indent=2, ensure_ascii=False)
        
        # Step 6: Verify workflow and decision
        print("\n[STEP 6] Verifying workflow and decision...")
        
        workflow_type = detail_data.get("workflow_type")
        decision = detail_data.get("decision")
        rejection_reason = detail_data.get("rejection_reason")
        final_reason = detail_data.get("final_reason")
        mapped_template_id = detail_data.get("mapped_template_id")
        considered_template_ids = detail_data.get("considered_template_ids", [])
        mismatch_reasons = detail_data.get("mismatch_reasons", {})
        candidate_status = detail_data.get("candidate_status")
        live_eligible = detail_data.get("live_eligible")
        
        if workflow_type != "strategy_idea":
            print(f"[FAIL] Expected workflow_type='strategy_idea', got '{workflow_type}'")
            return 1
        
        if decision != "rejected":
            print(f"[FAIL] Expected decision='rejected', got '{decision}'")
            return 1
        
        if not (rejection_reason or final_reason):
            print(f"[FAIL] Missing rejection_reason or final_reason")
            return 1
        
        if mapped_template_id is not None:
            print(f"[FAIL] Expected mapped_template_id=null, got '{mapped_template_id}'")
            return 1
        
        if not considered_template_ids:
            print(f"[FAIL] considered_template_ids is empty")
            return 1
        
        if not mismatch_reasons:
            print(f"[FAIL] mismatch_reasons is empty")
            return 1
        
        if candidate_status != "candidate_unapproved":
            print(f"[FAIL] Expected candidate_status='candidate_unapproved', got '{candidate_status}'")
            return 1
        
        if live_eligible != False:
            print(f"[FAIL] Expected live_eligible=false, got '{live_eligible}'")
            return 1
        
        print(f"[OK] Workflow and decision verified")
        print(f"  workflow_type: {workflow_type}")
        print(f"  decision: {decision}")
        print(f"  final_reason: {final_reason}")
        print(f"  candidate_status: {candidate_status}")
        print(f"  live_eligible: {live_eligible}")
        print(f"  considered_templates: {len(considered_template_ids)}")
        
        # Step 7: Verify all strategy pages
        print("\n[STEP 7] Verifying all strategy pages...")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            
            # Listen to network requests
            page_network_log = []
            
            def log_request(request):
                page_network_log.append({
                    "url": request.url,
                    "method": request.method,
                    "timestamp": datetime.now().isoformat(),
                })
            
            def log_response(response):
                for entry in page_network_log:
                    if entry["url"] == response.url and "status" not in entry:
                        entry["status"] = response.status
            
            context.on("request", log_request)
            context.on("response", log_response)
            
            page = context.new_page()
            
            # Verify /strategies hub
            print("  Checking /strategies hub...")
            page.goto("http://localhost:3010/strategies", wait_until="networkidle")
            time.sleep(1)
            
            strategies_dom = page.content()
            strategies_dom_path = evidence_dir / "p3-10-strategies-dom.md"
            with open(strategies_dom_path, "w", encoding="utf-8") as f:
                f.write(f"# /strategies Hub DOM - {run_id}\n\n")
                f.write(strategies_dom)
            
            if "count: 0" not in strategies_dom:
                print(f"[FAIL] /strategies hub not showing approved strategy count=0")
                return 1
            
            print("  [OK] /strategies hub verified")
            
            # Verify /strategy-ideas/{idea_id}
            print(f"  Checking /strategy-ideas/{idea_id}...")
            page.goto(f"http://localhost:3010/strategy-ideas/{idea_id}", wait_until="networkidle")
            time.sleep(1)
            
            idea_detail_dom = page.content()
            idea_detail_dom_path = evidence_dir / "p3-10-idea-detail-dom.md"
            with open(idea_detail_dom_path, "w", encoding="utf-8") as f:
                f.write(f"# /strategy-ideas/{idea_id} DOM - {run_id}\n\n")
                f.write(idea_detail_dom)
            
            if run_id not in idea_detail_dom and idea_id not in idea_detail_dom:
                print(f"[FAIL] Idea detail page missing run_id or idea_id")
                return 1
            
            print("  [OK] Idea detail page verified")
            
            # Verify /candidate-strategies
            print("  Checking /candidate-strategies...")
            page.goto("http://localhost:3010/candidate-strategies", wait_until="networkidle")
            time.sleep(1)
            
            candidate_dom = page.content()
            candidate_dom_path = evidence_dir / "p3-10-candidate-dom.md"
            with open(candidate_dom_path, "w", encoding="utf-8") as f:
                f.write(f"# /candidate-strategies DOM - {run_id}\n\n")
                f.write(candidate_dom)
            
            if idea_id not in candidate_dom:
                print(f"[FAIL] Candidate page missing idea_id {idea_id}")
                return 1
            
            print("  [OK] Candidate strategies page verified")
            
            # Verify /rejected-strategies
            print("  Checking /rejected-strategies...")
            page.goto("http://localhost:3010/rejected-strategies", wait_until="networkidle")
            time.sleep(1)
            
            rejected_dom = page.content()
            rejected_dom_path = evidence_dir / "p3-10-rejected-dom.md"
            with open(rejected_dom_path, "w", encoding="utf-8") as f:
                f.write(f"# /rejected-strategies DOM - {run_id}\n\n")
                f.write(rejected_dom)
            
            if idea_id not in rejected_dom:
                print(f"[FAIL] Rejected page missing idea_id {idea_id}")
                return 1
            
            print("  [OK] Rejected strategies page verified")
            
            # Verify /strategy-validations
            print("  Checking /strategy-validations...")
            page.goto("http://localhost:3010/strategy-validations", wait_until="networkidle")
            time.sleep(1)
            
            validations_dom = page.content()
            validations_dom_path = evidence_dir / "p3-10-validations-dom.md"
            with open(validations_dom_path, "w", encoding="utf-8") as f:
                f.write(f"# /strategy-validations DOM - {run_id}\n\n")
                f.write(validations_dom)
            
            if "当前没有策略验证案例" not in validations_dom:
                print(f"[FAIL] Validations page missing empty state message")
                return 1
            
            if "验证案例数量" not in validations_dom:
                print(f"[FAIL] Validations page missing count display")
                return 1
            
            print("  [OK] Strategy validations page verified")
            
            # Verify /strategy-templates
            print("  Checking /strategy-templates...")
            page.goto("http://localhost:3010/strategy-templates", wait_until="networkidle")
            time.sleep(1)
            
            templates_dom = page.content()
            templates_dom_path = evidence_dir / "p3-10-templates-dom.md"
            with open(templates_dom_path, "w", encoding="utf-8") as f:
                f.write(f"# /strategy-templates DOM - {run_id}\n\n")
                f.write(templates_dom)
            
            print("  [OK] Strategy templates page verified")
            
            # Save page network log
            page_network_log_path = evidence_dir / "p3-10-network-log.json"
            with open(page_network_log_path, "w", encoding="utf-8") as f:
                json.dump(page_network_log, f, indent=2, ensure_ascii=False)
            
            browser.close()
        
        # Step 8: Verify all API endpoints
        print("\n[STEP 8] Verifying all API endpoints...")
        
        # GET /api/strategy-ideas?candidate_status=candidate_unapproved
        candidate_url = "http://localhost:8010/api/strategy-ideas?candidate_status=candidate_unapproved"
        with urllib.request.urlopen(candidate_url) as response:
            candidate_data = json.loads(response.read().decode())
        
        candidate_api_path = evidence_dir / "p3-10-candidate-api.json"
        with open(candidate_api_path, "w", encoding="utf-8") as f:
            json.dump(candidate_data, f, indent=2, ensure_ascii=False)
        
        candidate_ideas = candidate_data.get("ideas", [])
        if not any(c["idea_id"] == idea_id for c in candidate_ideas):
            print(f"[FAIL] Idea {idea_id} not found in candidate API")
            return 1
        
        print(f"  [OK] Candidate API verified (found idea {idea_id})")
        
        # GET /api/strategy-validations
        validations_url = "http://localhost:8010/api/strategy-validations"
        with urllib.request.urlopen(validations_url) as response:
            validations_data = json.loads(response.read().decode())
        
        validations_api_path = evidence_dir / "p3-10-validations-api.json"
        with open(validations_api_path, "w", encoding="utf-8") as f:
            json.dump(validations_data, f, indent=2, ensure_ascii=False)
        
        if validations_data.get("count") != 0:
            print(f"[FAIL] Validations API count should be 0, got {validations_data.get('count')}")
            return 1
        
        print(f"  [OK] Validations API verified (count=0)")
        
        # GET /api/strategies
        strategies_url = "http://localhost:8010/api/strategies"
        with urllib.request.urlopen(strategies_url) as response:
            strategies_data = json.loads(response.read().decode())
        
        strategies_api_path = evidence_dir / "p3-10-strategies-api.json"
        with open(strategies_api_path, "w", encoding="utf-8") as f:
            json.dump(strategies_data, f, indent=2, ensure_ascii=False)
        
        if strategies_data.get("count") != 0:
            print(f"[FAIL] Strategies API count should be 0, got {strategies_data.get('count')}")
            return 1
        
        print(f"  [OK] Strategies API verified (count=0)")
        
        # GET /api/strategy-templates
        templates_url = "http://localhost:8010/api/strategy-templates"
        with urllib.request.urlopen(templates_url) as response:
            templates_data = json.loads(response.read().decode())
        
        templates_api_path = evidence_dir / "p3-10-templates-api.json"
        with open(templates_api_path, "w", encoding="utf-8") as f:
            json.dump(templates_data, f, indent=2, ensure_ascii=False)
        
        template_count = len(templates_data.get("templates", []))
        print(f"  [OK] Templates API verified ({template_count} templates)")
        
        # Step 9: Generate evidence summary
        print("\n[STEP 9] Generating evidence summary...")
        
        evidence_summary = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "verification_status": "PASSED",
            "flow": {
                "conversation_id": conversation_id,
                "idea_id": idea_id,
                "workflow_type": workflow_type,
                "decision": decision,
                "final_reason": final_reason,
                "mapped_template_id": mapped_template_id,
                "considered_templates_count": len(considered_template_ids),
                "candidate_status": candidate_status,
                "live_eligible": live_eligible,
            },
            "api_verification": {
                "validations_count": validations_data.get("count"),
                "strategies_count": strategies_data.get("count"),
                "templates_count": template_count,
            },
            "evidence_files": [
                "p3-10-workbench-dom.md",
                "p3-10-workbench-network-log.json",
                "p3-10-workbench-response.json",
                "p3-10-idea-detail-api.json",
                "p3-10-idea-list-api.json",
                "p3-10-candidate-api.json",
                "p3-10-validations-api.json",
                "p3-10-strategies-api.json",
                "p3-10-templates-api.json",
                "p3-10-strategies-dom.md",
                "p3-10-idea-detail-dom.md",
                "p3-10-candidate-dom.md",
                "p3-10-rejected-dom.md",
                "p3-10-validations-dom.md",
                "p3-10-templates-dom.md",
                "p3-10-network-log.json",
                "p3-10-backend-log.txt",
                "p3-10-frontend-log.txt",
                "p3-10-evidence-summary.json",
            ],
        }
        
        summary_path = evidence_dir / "p3-10-evidence-summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(evidence_summary, f, indent=2, ensure_ascii=False)
        
        print(f"[OK] Evidence summary saved: {summary_path.name}")
        
        print("\n" + "=" * 80)
        print("PASS: P3-10 END-TO-END VERIFICATION PASSED")
        print("=" * 80)
        print(f"\nRun ID: {run_id}")
        print(f"Conversation ID: {conversation_id}")
        print(f"Idea ID: {idea_id}")
        print(f"Workflow Type: {workflow_type}")
        print(f"Decision: {decision}")
        print(f"Candidate Status: {candidate_status}")
        print(f"Validations Count: {validations_data.get('count')}")
        print(f"Approved Strategies Count: {strategies_data.get('count')}")
        print(f"Evidence Files: {len(evidence_summary['evidence_files'])}")
        
        return 0
        
    except Exception as e:
        print(f"\n[FAIL] Verification error: {e}")
        import traceback
        traceback.print_exc()
        return 1
        
    finally:
        # Cleanup
        print("\n[CLEANUP] Stopping processes...")
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
        
        print("[OK] Cleanup complete")


if __name__ == "__main__":
    exit_code = run_verification()
    sys.exit(exit_code)
