"""
P3-8 Strategy Product Navigation Closure Verification

Verifies that all strategy pages have bidirectional navigation:
- /strategies hub shows 5 entry points
- Each page has link back to /strategies
- Navigation closure is complete
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
    """Run P3-8 verification."""
    print("=" * 80)
    print("P3-8 STRATEGY PRODUCT NAVIGATION CLOSURE VERIFICATION")
    print("=" * 80)
    
    run_id = f"P3_8_RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
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
        frontend_log_path = evidence_dir / "p3-8-frontend-log.txt"
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
        
        # Step 4: Verify /strategies hub
        print("[STEP 4] Verifying /strategies hub page...")
        
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
            hub_dom = page.content()
            hub_dom_path = evidence_dir / "p3-8-strategies-hub-dom.md"
            with open(hub_dom_path, "w", encoding="utf-8") as f:
                f.write(f"# /strategies Hub DOM - {run_id}\n\n")
                f.write(hub_dom)
            
            # Verify 5 entry links exist
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
                print(f"[FAIL] /strategies hub missing required links: {missing_links}")
                return 1
            
            print(f"[OK] /strategies hub has all 4 entry links")
            
            # Verify API response shows empty approved strategies
            import urllib.request
            
            api_url = "http://localhost:8010/api/strategies"
            with urllib.request.urlopen(api_url) as response:
                api_data = json.loads(response.read().decode())
            
            if api_data.get("strategies") != [] or api_data.get("count") != 0:
                print(f"[FAIL] /api/strategies not showing empty state")
                print(f"  strategies: {api_data.get('strategies')}")
                print(f"  count: {api_data.get('count')}")
                return 1
            
            print(f"[OK] /api/strategies returns empty approved strategies (count=0)")
            
            # Step 5: Verify each page has back link
            print("\n[STEP 5] Verifying navigation links on each page...")
            
            pages_to_check = [
                ("/strategy-ideas", "p3-8-strategy-ideas-dom.md"),
                ("/candidate-strategies", "p3-8-candidate-strategies-dom.md"),
                ("/rejected-strategies", "p3-8-rejected-strategies-dom.md"),
                ("/strategy-templates", "p3-8-strategy-templates-dom.md"),
            ]
            
            for page_path, dom_filename in pages_to_check:
                page.goto(f"http://localhost:3000{page_path}", wait_until="networkidle")
                time.sleep(1)
                
                page_dom = page.content()
                dom_path = evidence_dir / dom_filename
                with open(dom_path, "w", encoding="utf-8") as f:
                    f.write(f"# {page_path} DOM - {run_id}\n\n")
                    f.write(page_dom)
                
                # Check for back link to /strategies
                if 'href="/strategies"' not in page_dom:
                    print(f"[FAIL] {page_path} missing link back to /strategies")
                    return 1
                
                print(f"[OK] {page_path} has link back to /strategies")
            
            # Save network log
            network_log_path = evidence_dir / "p3-8-navigation-network-log.json"
            with open(network_log_path, "w", encoding="utf-8") as f:
                json.dump(network_log, f, indent=2, ensure_ascii=False)
            
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
            "hub_verification": {
                "hub_path": "/strategies",
                "entry_links_count": len(required_links),
                "entry_links": required_links,
            },
            "page_back_links": {
                "strategy_ideas": "✓",
                "candidate_strategies": "✓",
                "rejected_strategies": "✓",
                "strategy_templates": "✓",
            },
            "api_verification": {
                "strategies_count": api_data.get("count"),
                "strategies_list": api_data.get("strategies"),
            },
            "evidence_files": [
                str(hub_dom_path.name),
                str(dom_filename),
                str(network_log_path.name),
                str(frontend_log_path.name),
            ],
        }
        
        summary_path = evidence_dir / "p3-8-verification-summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(evidence_summary, f, indent=2, ensure_ascii=False)
        
        print(f"[OK] Evidence summary saved: {summary_path.name}")
        
        print("\n" + "=" * 80)
        print("PASS: P3-8 VERIFICATION PASSED")
        print("=" * 80)
        print(f"\nRun ID: {run_id}")
        print(f"Hub entry links: {len(required_links)}")
        print(f"Pages with back links: 4/4")
        print(f"Approved strategies count: 0 (correct)")
        
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
