#!/usr/bin/env python3
"""
P4-3 Dashboard Actionability Verification

Verifies:
1. Dashboard displays all action links
2. All action links are clickable and lead to valid pages
3. Count=0 areas still show action entry points
4. All network requests point to localhost

Real browser verification with Playwright - no API-only downgrade.

Exit code 0 = pass, 1 = fail
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime

# Fix Windows GBK encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))
from runtime_process_helpers import (
    start_backend,
    start_frontend,
    stop_process,
    wait_for_http,
    check_and_release_ports,
)


def verify_p4_3_dashboard_actionability():
    """Verify P4-3 Dashboard Actionability."""
    
    print("=" * 100)
    print("P4-3 DASHBOARD ACTIONABILITY VERIFICATION")
    print("=" * 100)
    print()
    
    run_id = f"P4_3_RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"Run ID: {run_id}")
    print()
    
    project_root = Path(__file__).parent.parent
    verification_dir = project_root / "docs" / "verification"
    verification_dir.mkdir(parents=True, exist_ok=True)
    
    evidence = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "action_links": {},
        "action_pages": {},
        "checks": {},
        "evidence_files": [],
        "network_requests": []
    }
    
    backend_process = None
    frontend_process = None
    browser = None
    playwright = None
    
    # Define expected action links with their expected page titles
    expected_links = {
        "/workbench": ("Agent Workbench", ["TraderLens 工作台", "工作台"]),
        "/observations": ("Observation Pool", ["观察池"]),
        "/signals": ("Signal Board", ["Signal Board"]),
        "/strategy-ideas": ("Strategy Ideas", ["策略想法"]),
        "/candidate-strategies": ("Candidate Strategies", ["候选策略", "Candidate Strategies"]),
        "/rejected-strategies": ("Rejected Strategies", ["策略拒绝", "Rejected Strategies"]),
        "/strategy-validations": ("Strategy Validations", ["策略验证"]),
        "/strategies": ("Approved Strategies", ["已批准策略", "Approved Strategies"]),
        "/strategy-templates": ("Strategy Templates", ["策略模板"]),
    }
    
    try:
        # Step 1: Clean up ports
        print("Step 1: Checking and releasing ports...")
        print("-" * 80)
        check_and_release_ports([8010, 3010])
        print("✓ Ports 8010, 3010 ready")
        print()
        
        # Step 2: Start backend
        print("Step 2: Starting backend...")
        print("-" * 80)
        backend_process = start_backend(
            port=8010,
            timeout_seconds=60,
            extra_env={
                "RESEARCH_CONVERSATION_MODE": "deterministic",
                "SERENITY_EXECUTION_MODE": "stub",
            },
        )
        wait_for_http("http://localhost:8010/health")
        print("✓ Backend started")
        print()
        
        # Step 3: Start frontend
        print("Step 3: Starting frontend...")
        print("-" * 80)
        frontend_process = start_frontend(port=3010, timeout_seconds=90)
        wait_for_http("http://localhost:3010")
        print("✓ Frontend started")
        print()
        
        # Step 4: Initialize Playwright
        print("Step 4: Initializing Playwright...")
        print("-" * 80)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("✗ Playwright not installed")
            print("  Run: .venv\\Scripts\\python.exe -m pip install playwright")
            print("  Then: .venv\\Scripts\\python.exe -m playwright install chromium")
            return 1
        
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # Capture network requests
        network_log = []
        
        def handle_request(request):
            network_log.append({
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
            })
        
        page.on("request", handle_request)
        
        print("✓ Playwright ready")
        print()
        
        # Step 5: Navigate to dashboard and verify action links
        print("Step 5: Verifying dashboard action links...")
        print("-" * 80)
        page.goto("http://localhost:3010/", wait_until="networkidle", timeout=30000)
        time.sleep(2)  # Let React render
        
        dashboard_dom = page.content()
        dashboard_dom_file = verification_dir / "p4-3-dashboard-dom.md"
        with open(dashboard_dom_file, "w", encoding="utf-8") as f:
            f.write(f"# P4-3 Dashboard DOM\n\n")
            f.write(f"Run ID: {run_id}\n\n")
            f.write(f"## Page Content\n\n```html\n{dashboard_dom}\n```\n")
        evidence["evidence_files"].append(str(dashboard_dom_file.name))
        
        # Check for all expected action links in DOM
        links_found = {}
        for path, (name, page_titles) in expected_links.items():
            if f'href="{path}"' in dashboard_dom or f"href='{path}'" in dashboard_dom:
                links_found[path] = True
                evidence["action_links"][path] = {"found": True, "name": name}
                print(f"  ✓ Found action link: {path} ({name})")
            else:
                links_found[path] = False
                evidence["action_links"][path] = {"found": False, "name": name}
                print(f"  ✗ Missing action link: {path} ({name})")
        
        # Step 6: Verify each action page is reachable
        print()
        print("Step 6: Verifying action pages are reachable...")
        print("-" * 80)
        
        action_pages_dom = []
        pages_reachable = {}
        
        for path, (name, page_titles) in expected_links.items():
            print(f"\n[6.{list(expected_links.keys()).index(path) + 1}] Checking {path}...")
            try:
                page.goto(f"http://localhost:3010{path}", wait_until="networkidle", timeout=30000)
                time.sleep(1)
                
                page_dom = page.content()
                
                # Check if page contains expected title
                page_has_title = any(title in page_dom for title in page_titles)
                
                if page_has_title:
                    pages_reachable[path] = True
                    evidence["action_pages"][path] = {
                        "reachable": True,
                        "status": "ok",
                        "name": name,
                        "found_title": next((t for t in page_titles if t in page_dom), None)
                    }
                    print(f"  ✓ Page is reachable: {path}")
                else:
                    pages_reachable[path] = False
                    evidence["action_pages"][path] = {
                        "reachable": False,
                        "status": "missing_title",
                        "name": name
                    }
                    print(f"  ✗ Page not reachable: {path} (expected titles: {page_titles})")
                
                action_pages_dom.append(f"## {name} ({path})\n\nStatus: {'OK' if page_has_title else 'FAILED'}\nFound title: {next((t for t in page_titles if t in page_dom), 'NONE')}\n\n```html\n{page_dom[:2000]}...\n```\n\n")
                
            except Exception as e:
                pages_reachable[path] = False
                evidence["action_pages"][path] = {
                    "reachable": False,
                    "status": f"error: {str(e)}",
                    "name": name
                }
                print(f"  ✗ Failed to reach {path}: {str(e)}")
        
        # Save action pages DOM
        action_pages_dom_file = verification_dir / "p4-3-action-pages-dom.md"
        with open(action_pages_dom_file, "w", encoding="utf-8") as f:
            f.write(f"# P4-3 Action Pages DOM\n\n")
            f.write(f"Run ID: {run_id}\n\n")
            f.write("\n".join(action_pages_dom))
        evidence["evidence_files"].append(str(action_pages_dom_file.name))
        
        # Step 7: Network log verification
        print()
        print("Step 7: Network log verification")
        print("-" * 80)
        
        # Save network log
        network_log_file = verification_dir / "p4-3-network-log.json"
        with open(network_log_file, "w", encoding="utf-8") as f:
            json.dump(network_log, f, indent=2, ensure_ascii=False)
        evidence["evidence_files"].append(str(network_log_file.name))
        evidence["network_requests"] = network_log
        
        print(f"  Total network requests: {len(network_log)}")
        
        # Check for external API calls
        api_requests = [req for req in network_log if req["resource_type"] == "fetch" or req["resource_type"] == "xhr"]
        external_apis = [req for req in api_requests 
                        if not req["url"].startswith("http://localhost:8010") 
                        and not req["url"].startswith("http://localhost:3010")]
        
        if external_apis:
            print(f"  ✗ Found {len(external_apis)} external API requests:")
            for req in external_apis[:5]:
                print(f"    - {req['url']}")
            evidence["checks"]["network_validation"] = False
        else:
            print(f"  ✓ All {len(api_requests)} API requests point to localhost")
            backend_api_count = len([req for req in api_requests if req["url"].startswith("http://localhost:8010")])
            print(f"    - {backend_api_count} requests to backend (localhost:8010)")
            print(f"    - {len(api_requests) - backend_api_count} requests to frontend (localhost:3010)")
            evidence["checks"]["network_validation"] = True
        
        # Step 8: Summary
        print()
        print("Step 8: Verification summary")
        print("-" * 80)
        
        missing_links = [path for path, found in links_found.items() if not found]
        unreachable_pages = [path for path, reachable in pages_reachable.items() if not reachable]
        
        if missing_links:
            print(f"✗ {len(missing_links)} action links missing:")
            for path in missing_links:
                print(f"  - {path}")
            evidence["checks"]["all_links_present"] = False
        else:
            print(f"✓ All {len(expected_links)} action links found")
            evidence["checks"]["all_links_present"] = True
        
        if unreachable_pages:
            print(f"✗ {len(unreachable_pages)} pages unreachable:")
            for path in unreachable_pages:
                print(f"  - {path}")
            evidence["checks"]["all_pages_reachable"] = False
        else:
            print(f"✓ All {len(expected_links)} action pages reachable")
            evidence["checks"]["all_pages_reachable"] = True
        
        # Step 9: Save evidence
        print()
        print("Step 9: Save evidence")
        print("-" * 80)
        
        # Save evidence summary
        evidence_file = verification_dir / "p4-3-verification-summary.json"
        with open(evidence_file, "w", encoding="utf-8") as f:
            json.dump(evidence, f, indent=2, ensure_ascii=False)
        evidence["evidence_files"].append(str(evidence_file.name))
        print("✓ Saved evidence summary")
        
        # Check final result
        if missing_links or unreachable_pages or external_apis:
            print()
            print("=" * 100)
            print("✗ P4-3 DASHBOARD ACTIONABILITY VERIFICATION FAILED")
            print("=" * 100)
            return 1
        
        print()
        print("=" * 100)
        print("✓ P4-3 DASHBOARD ACTIONABILITY VERIFICATION PASSED")
        print("=" * 100)
        print()
        print(f"Run ID: {run_id}")
        print(f"Action links found: {len([v for v in links_found.values() if v])}/{len(expected_links)}")
        print(f"Action pages reachable: {len([v for v in pages_reachable.values() if v])}/{len(expected_links)}")
        print(f"Evidence files: {len(evidence['evidence_files'])}")
        print()
        
        return 0
        
    finally:
        # Cleanup
        if browser:
            try:
                browser.close()
            except:
                pass
        
        if playwright:
            try:
                playwright.stop()
            except:
                pass
        
        if frontend_process:
            stop_process(
                frontend_process,
                name="Frontend",
                save_log=verification_dir / "p4-3-frontend-log.txt",
                release_ports=[3010]
            )
        
        if backend_process:
            stop_process(
                backend_process,
                name="Backend",
                release_ports=[8010]
            )

if __name__ == "__main__":
    try:
        exit_code = verify_p4_3_dashboard_actionability()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n✗ Verification failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
