"""
P3-7 Strategy Library Shell Verification

Verifies the minimal /strategies page and API:
- GET /api/strategies returns empty list
- /strategies page displays empty state correctly
- Links to related pages work
- No fake approved strategies
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
    """Run P3-7 verification."""
    print("=" * 80)
    print("P3-7 STRATEGY LIBRARY SHELL VERIFICATION")
    print("=" * 80)
    
    run_id = f"P3_7_RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"\n[INFO] Run ID: {run_id}\n")
    
    evidence_dir = Path(__file__).parent.parent / "docs" / "verification"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    backend_process = None
    frontend_process = None
    
    try:
        # Step 1: Clean up ports
        print("[STEP 1] Checking and releasing ports...")
        check_and_release_ports([8010, 3000])
        print("[OK] Ports ready\n")
        
        # Step 2: Start backend
        print("[STEP 2] Starting backend...")
        backend_process = start_backend()
        wait_for_http("http://localhost:8010/health")
        print("[OK] Backend started\n")
        
        # Step 3: Start frontend
        print("[STEP 3] Starting frontend...")
        frontend_log_path = evidence_dir / "p3-7-frontend-log.txt"
        with open(frontend_log_path, "w", encoding="utf-8") as log_file:
            frontend_process = subprocess.Popen(
                "npm run dev",
                cwd=Path(__file__).parent.parent / "frontend",
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                shell=True,
            )
        
        wait_for_http("http://localhost:3000")
        print("[OK] Frontend started\n")
        
        # Step 4: Verify API endpoint
        print("[STEP 4] Verifying /api/strategies endpoint...")
        
        import urllib.request
        
        api_url = "http://localhost:8010/api/strategies"
        with urllib.request.urlopen(api_url) as response:
            api_data = json.loads(response.read().decode())
        
        api_response_path = evidence_dir / "p3-7-api-strategies-response.json"
        with open(api_response_path, "w", encoding="utf-8") as f:
            json.dump(api_data, f, indent=2, ensure_ascii=False)
        
        # Verify response structure
        if "strategies" not in api_data:
            print("[FAIL] API response missing 'strategies' field")
            return 1
        
        if "count" not in api_data:
            print("[FAIL] API response missing 'count' field")
            return 1
        
        # Verify empty state
        strategies = api_data.get("strategies", [])
        count = api_data.get("count", -1)
        
        if strategies != []:
            print(f"[FAIL] Expected empty strategies list, got {len(strategies)} strategies")
            print("[FAIL] Red line violation: No approved strategies should exist")
            return 1
        
        if count != 0:
            print(f"[FAIL] Expected count=0, got count={count}")
            return 1
        
        print(f"[OK] API returns empty approved strategy library")
        print(f"  strategies: {strategies}")
        print(f"  count: {count}")
        
        # Step 5: Verify frontend page
        print("\n[STEP 5] Verifying /strategies page...")
        
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
                        if "/api/strategies" in response.url:
                            try:
                                body = response.json()
                                entry["response_body"] = body
                            except:
                                pass
            
            context.on("request", log_request)
            context.on("response", log_response)
            
            page = context.new_page()
            page.goto("http://localhost:3000/strategies", wait_until="networkidle")
            
            # Wait for page to render
            time.sleep(2)
            
            # Save DOM
            page_dom = page.content()
            dom_path = evidence_dir / "p3-7-strategies-dom.md"
            with open(dom_path, "w", encoding="utf-8") as f:
                f.write(f"# /strategies Page DOM - {run_id}\n\n")
                f.write(page_dom)
            
            # Save network log
            network_log_path = evidence_dir / "p3-7-strategies-network-log.json"
            with open(network_log_path, "w", encoding="utf-8") as f:
                json.dump(network_log, f, indent=2, ensure_ascii=False)
            
            # Verify DOM content
            page_content = page.content().lower()
            
            # Check for empty state message
            if "当前没有已批准策略" not in page.content():
                print("[FAIL] Page missing empty state message")
                return 1
            
            # Check for count display
            if "策略数量" not in page.content():
                print("[FAIL] Page missing strategy count display")
                return 1
            
            # Verify links to related pages
            required_links = [
                "/strategy-ideas",
                "/candidate-strategies",
                "/rejected-strategies",
                "/strategy-templates",
            ]
            
            page_html = page.content()
            missing_links = []
            
            for link in required_links:
                if f'href="{link}"' not in page_html:
                    missing_links.append(link)
            
            if missing_links:
                print(f"[FAIL] Page missing required links: {missing_links}")
                return 1
            
            print("[OK] Page displays empty state correctly")
            print(f"  Found all 4 required links")
            
            # Verify all API requests go to localhost:8010
            api_requests = [entry for entry in network_log if "/api/" in entry["url"]]
            non_local_requests = [
                entry for entry in api_requests 
                if not entry["url"].startswith("http://localhost:8010")
            ]
            
            if non_local_requests:
                print(f"[FAIL] Found {len(non_local_requests)} non-localhost API requests")
                for entry in non_local_requests:
                    print(f"  {entry['url']}")
                return 1
            
            print(f"[OK] All {len(api_requests)} API requests go to localhost:8010")
            
            browser.close()
        
        # Step 6: Generate evidence summary
        print("\n[STEP 6] Generating evidence summary...")
        
        evidence_summary = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "verification_status": "PASSED",
            "api_response": api_data,
            "evidence_files": [
                str(api_response_path.name),
                str(dom_path.name),
                str(network_log_path.name),
                str(frontend_log_path.name),
            ],
            "checks": {
                "api_strategies_empty": strategies == [],
                "api_count_zero": count == 0,
                "page_empty_state": True,
                "page_count_display": True,
                "required_links": len(required_links),
                "api_requests_localhost": len(api_requests),
            }
        }
        
        summary_path = evidence_dir / "p3-7-verification-summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(evidence_summary, f, indent=2, ensure_ascii=False)
        
        print(f"[OK] Evidence summary saved: {summary_path.name}")
        
        print("\n" + "=" * 80)
        print("PASS: P3-7 VERIFICATION PASSED")
        print("=" * 80)
        print(f"\nRun ID: {run_id}")
        print(f"API strategies count: {count}")
        print(f"Evidence files: {len(evidence_summary['evidence_files'])}")
        
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
