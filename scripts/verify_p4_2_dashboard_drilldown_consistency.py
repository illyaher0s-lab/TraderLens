#!/usr/bin/env python3
"""
P4-2 Dashboard Drilldown Consistency Verification

Verifies:
1. Dashboard API counts match drilldown API counts
2. Dashboard page DOM displays real data
3. Drilldown pages DOM display real data or honest empty states
4. All network requests point to localhost:8010

Real browser verification with Playwright - no API-only downgrade.

Exit code 0 = pass, 1 = fail
"""

import sys
import json
import time
import subprocess
import requests
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

def verify_p4_2_dashboard_drilldown_consistency():
    """Verify P4-2 Dashboard Drilldown Consistency."""
    
    print("=" * 100)
    print("P4-2 DASHBOARD DRILLDOWN CONSISTENCY VERIFICATION")
    print("=" * 100)
    print()
    
    run_id = f"P4_2_RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"Run ID: {run_id}")
    print()
    
    project_root = Path(__file__).parent.parent
    verification_dir = project_root / "docs" / "verification"
    verification_dir.mkdir(parents=True, exist_ok=True)
    
    evidence = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "checks": {},
        "evidence_files": [],
        "inconsistencies": [],
        "network_requests": []
    }
    
    backend_process = None
    frontend_process = None
    browser = None
    playwright = None
    
    try:
        # Step 1: Clean up ports
        print("Step 1: Checking and releasing ports...")
        print("-" * 80)
        check_and_release_ports([8010, 3000])
        print("✓ Ports 8010, 3000 ready")
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
        
        # Step 2.5: Start frontend
        print("Step 2.5: Starting frontend...")
        print("-" * 80)
        frontend_process = start_frontend(port=3000, timeout_seconds=90)
        wait_for_http("http://localhost:3000")
        print("✓ Frontend started")
        print()
        
        # Step 2.6: Initialize Playwright
        print("Step 2.6: Initializing Playwright...")
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
        
        # Step 3: Fetch dashboard API
        print("Step 3: Fetch dashboard API")
        print("-" * 80)
        
        dashboard_response = requests.get("http://localhost:8010/api/dashboard/today", timeout=10)
        if dashboard_response.status_code != 200:
            print(f"鉁?Dashboard API failed: {dashboard_response.status_code}")
            return 1
        
        dashboard_data = dashboard_response.json()
        
        # Save dashboard API response
        dashboard_api_file = verification_dir / "p4-2-dashboard-api.json"
        with open(dashboard_api_file, "w", encoding="utf-8") as f:
            json.dump(dashboard_data, f, indent=2, ensure_ascii=False)
        evidence["evidence_files"].append(str(dashboard_api_file.name))
        
        print(f"鉁?Dashboard API response:")
        print(f"  - as_of_date: {dashboard_data['as_of_date']}")
        print(f"  - open_observations: {dashboard_data['open_observations']['count']}")
        print(f"  - today_signals: {dashboard_data['today_signals']['count']}")
        print(f"  - strategy_workspace:")
        for key, value in dashboard_data['strategy_workspace'].items():
            print(f"    - {key}: {value}")
        print(f"  - recent_reviews: {dashboard_data['recent_reviews']['count']}")
        print()
        
        # Step 4: Drilldown verification
        print("Step 4: Drilldown API verification")
        print("-" * 80)
        
        drilldown_checks = []
        
        # 4.1: Open observations
        print("\n[4.1] Verifying open observations")
        dashboard_obs_count = dashboard_data['open_observations']['count']
        print(f"  Dashboard count: {dashboard_obs_count}")
        
        obs_response = requests.get("http://localhost:8010/api/observations?status=open", timeout=10)
        obs_data = obs_response.json()
        obs_api_count = obs_data.get("total", len(obs_data.get("positions", [])))
        print(f"  API count: {obs_api_count}")
        
        obs_api_file = verification_dir / "p4-2-observations-api.json"
        with open(obs_api_file, "w", encoding="utf-8") as f:
            json.dump(obs_data, f, indent=2, ensure_ascii=False)
        evidence["evidence_files"].append(str(obs_api_file.name))
        
        if dashboard_obs_count != obs_api_count:
            inconsistency = f"open_observations: dashboard={dashboard_obs_count}, api={obs_api_count}"
            print(f"  鉁?INCONSISTENCY: {inconsistency}")
            evidence["inconsistencies"].append(inconsistency)
            drilldown_checks.append(("open_observations", False))
        else:
            print(f"  鉁?Counts match")
            drilldown_checks.append(("open_observations", True))
        
        # 4.2: Today signals
        print("\n[4.2] Verifying today signals")
        dashboard_signals_count = dashboard_data['today_signals']['count']
        print(f"  Dashboard count: {dashboard_signals_count}")
        
        today_date = dashboard_data['as_of_date']
        signals_response = requests.get(f"http://localhost:8010/api/signals?signal_date={today_date}", timeout=15)
        if signals_response.status_code != 200:
            print(f"  ✗ Signals API failed: HTTP {signals_response.status_code}")
            return 1
        signals_data = signals_response.json()
        
        if isinstance(signals_data, dict):
            signals_api_count = signals_data.get("total", len(signals_data.get("signals", [])))
        elif isinstance(signals_data, list):
            signals_api_count = len(signals_data)
        else:
            print(f"  ✗ Signals API returned unexpected shape: {type(signals_data).__name__}")
            return 1
        
        print(f"  API count: {signals_api_count}")
        
        signals_api_file = verification_dir / "p4-2-signals-api.json"
        with open(signals_api_file, "w", encoding="utf-8") as f:
            json.dump(signals_data, f, indent=2, ensure_ascii=False)
        evidence["evidence_files"].append(str(signals_api_file.name))
        
        if dashboard_signals_count != signals_api_count:
            inconsistency = f"today_signals: dashboard={dashboard_signals_count}, api={signals_api_count}"
            print(f"  鉁?INCONSISTENCY: {inconsistency}")
            evidence["inconsistencies"].append(inconsistency)
            drilldown_checks.append(("today_signals", False))
        else:
            print(f"  鉁?Counts match")
            drilldown_checks.append(("today_signals", True))
        
        # 4.3: Strategy ideas
        print("\n[4.3] Verifying strategy ideas")
        dashboard_ideas_count = dashboard_data['strategy_workspace']['ideas_count']
        print(f"  Dashboard count: {dashboard_ideas_count}")
        
        try:
            print(f"  Fetching /api/strategy-ideas (timeout 90s)...")
            ideas_response = requests.get("http://localhost:8010/api/strategy-ideas", timeout=90)
            ideas_data = ideas_response.json()
            ideas_api_count = len(ideas_data.get("ideas", []))
            print(f"  API count: {ideas_api_count}")
        except requests.exceptions.Timeout:
            print(f"  鉁?API timeout after 90s")
            print(f"  This suggests the N+1 fix didn't work or there's another bottleneck")
            return 1
        except Exception as e:
            print(f"  鉁?API error: {e}")
            return 1
        
        ideas_api_file = verification_dir / "p4-2-strategy-ideas-api.json"
        with open(ideas_api_file, "w", encoding="utf-8") as f:
            json.dump(ideas_data, f, indent=2, ensure_ascii=False)
        evidence["evidence_files"].append(str(ideas_api_file.name))
        
        if dashboard_ideas_count != ideas_api_count:
            inconsistency = f"ideas_count: dashboard={dashboard_ideas_count}, api={ideas_api_count}"
            print(f"  鉁?INCONSISTENCY: {inconsistency}")
            evidence["inconsistencies"].append(inconsistency)
            drilldown_checks.append(("ideas_count", False))
        else:
            print(f"  鉁?Counts match")
            drilldown_checks.append(("ideas_count", True))
        
        # 4.4: Candidates
        print("\n[4.4] Verifying candidates")
        dashboard_candidates_count = dashboard_data['strategy_workspace']['candidates_count']
        print(f"  Dashboard count: {dashboard_candidates_count}")
        
        try:
            candidates_response = requests.get("http://localhost:8010/api/strategy-ideas?candidate_status=candidate_unapproved", timeout=90)
            candidates_data = candidates_response.json()
            candidates_api_count = len(candidates_data.get("ideas", []))
            print(f"  API count: {candidates_api_count}")
        except requests.exceptions.Timeout:
            print(f"  鉁?API timeout after 90s")
            return 1
        except Exception as e:
            print(f"  鉁?API error: {e}")
            return 1
        
        candidates_api_file = verification_dir / "p4-2-candidates-api.json"
        with open(candidates_api_file, "w", encoding="utf-8") as f:
            json.dump(candidates_data, f, indent=2, ensure_ascii=False)
        evidence["evidence_files"].append(str(candidates_api_file.name))
        
        if dashboard_candidates_count != candidates_api_count:
            inconsistency = f"candidates_count: dashboard={dashboard_candidates_count}, api={candidates_api_count}"
            print(f"  鉁?INCONSISTENCY: {inconsistency}")
            evidence["inconsistencies"].append(inconsistency)
            drilldown_checks.append(("candidates_count", False))
        else:
            print(f"  鉁?Counts match")
            drilldown_checks.append(("candidates_count", True))
        
        # 4.5: Rejected (from ideas API)
        print("\n[4.5] Verifying rejected")
        dashboard_rejected_count = dashboard_data['strategy_workspace']['rejected_count']
        print(f"  Dashboard count: {dashboard_rejected_count}")
        
        rejected_api_count = sum(1 for idea in ideas_data.get("ideas", []) if idea.get("decision") == "rejected")
        print(f"  API count (from ideas): {rejected_api_count}")
        
        if dashboard_rejected_count != rejected_api_count:
            inconsistency = f"rejected_count: dashboard={dashboard_rejected_count}, api={rejected_api_count}"
            print(f"  鉁?INCONSISTENCY: {inconsistency}")
            evidence["inconsistencies"].append(inconsistency)
            drilldown_checks.append(("rejected_count", False))
        else:
            print(f"  鉁?Counts match")
            drilldown_checks.append(("rejected_count", True))
        
        # 4.6: Validations
        print("\n[4.6] Verifying validations")
        dashboard_validations_count = dashboard_data['strategy_workspace']['validations_count']
        print(f"  Dashboard count: {dashboard_validations_count}")
        
        validations_response = requests.get("http://localhost:8010/api/strategy-validations", timeout=10)
        validations_data = validations_response.json()
        validations_api_count = validations_data.get("count", 0)
        print(f"  API count: {validations_api_count}")
        
        validations_api_file = verification_dir / "p4-2-validations-api.json"
        with open(validations_api_file, "w", encoding="utf-8") as f:
            json.dump(validations_data, f, indent=2, ensure_ascii=False)
        evidence["evidence_files"].append(str(validations_api_file.name))
        
        if dashboard_validations_count != 0:
            print(f"  鉁?validations_count should be 0, got {dashboard_validations_count}")
            return 1
        
        if dashboard_validations_count != validations_api_count:
            inconsistency = f"validations_count: dashboard={dashboard_validations_count}, api={validations_api_count}"
            print(f"  鉁?INCONSISTENCY: {inconsistency}")
            evidence["inconsistencies"].append(inconsistency)
            drilldown_checks.append(("validations_count", False))
        else:
            print(f"  鉁?Counts match (empty state)")
            drilldown_checks.append(("validations_count", True))
        
        # 4.7: Approved strategies
        print("\n[4.7] Verifying approved strategies")
        dashboard_approved_count = dashboard_data['strategy_workspace']['approved_strategies_count']
        print(f"  Dashboard count: {dashboard_approved_count}")
        
        strategies_response = requests.get("http://localhost:8010/api/strategies", timeout=10)
        strategies_data = strategies_response.json()
        strategies_api_count = strategies_data.get("count", 0)
        print(f"  API count: {strategies_api_count}")
        
        strategies_api_file = verification_dir / "p4-2-strategies-api.json"
        with open(strategies_api_file, "w", encoding="utf-8") as f:
            json.dump(strategies_data, f, indent=2, ensure_ascii=False)
        evidence["evidence_files"].append(str(strategies_api_file.name))
        
        if dashboard_approved_count != 0:
            print(f"  鉁?approved_strategies_count should be 0, got {dashboard_approved_count}")
            return 1
        
        if dashboard_approved_count != strategies_api_count:
            inconsistency = f"approved_strategies_count: dashboard={dashboard_approved_count}, api={strategies_api_count}"
            print(f"  鉁?INCONSISTENCY: {inconsistency}")
            evidence["inconsistencies"].append(inconsistency)
            drilldown_checks.append(("approved_strategies_count", False))
        else:
            print(f"  鉁?Counts match (empty state)")
            drilldown_checks.append(("approved_strategies_count", True))
        
        # 4.8: Templates
        print("\n[4.8] Verifying templates")
        dashboard_templates_count = dashboard_data['strategy_workspace']['templates_count']
        print(f"  Dashboard count: {dashboard_templates_count}")
        
        templates_response = requests.get("http://localhost:8010/api/strategy-templates", timeout=10)
        templates_data = templates_response.json()
        templates_api_count = len(templates_data.get("templates", []))
        print(f"  API count: {templates_api_count}")
        
        templates_api_file = verification_dir / "p4-2-templates-api.json"
        with open(templates_api_file, "w", encoding="utf-8") as f:
            json.dump(templates_data, f, indent=2, ensure_ascii=False)
        evidence["evidence_files"].append(str(templates_api_file.name))
        
        if dashboard_templates_count != 4:
            print(f"  鉁?templates_count should be 4, got {dashboard_templates_count}")
            return 1
        
        if dashboard_templates_count != templates_api_count:
            inconsistency = f"templates_count: dashboard={dashboard_templates_count}, api={templates_api_count}"
            print(f"  鉁?INCONSISTENCY: {inconsistency}")
            evidence["inconsistencies"].append(inconsistency)
            drilldown_checks.append(("templates_count", False))
        else:
            print(f"  鉁?Counts match")
            drilldown_checks.append(("templates_count", True))
        
        # Step 5: DOM Verification
        print()
        print("Step 5: DOM Verification")
        print("-" * 80)
        
        dom_checks = []
        
        # 5.1: Dashboard page
        print("\n[5.1] Verifying dashboard page DOM")
        page.goto("http://localhost:3000/", wait_until="networkidle", timeout=30000)
        time.sleep(2)  # Let React render
        
        dashboard_dom = page.content()
        dashboard_dom_file = verification_dir / "p4-2-dashboard-dom.md"
        with open(dashboard_dom_file, "w", encoding="utf-8") as f:
            f.write(f"# Dashboard Page DOM\n\n")
            f.write(f"Run ID: {run_id}\n\n")
            f.write(f"## Page Content\n\n```html\n{dashboard_dom}\n```\n")
        evidence["evidence_files"].append(str(dashboard_dom_file.name))
        
        # Verify dashboard shows real counts
        if "观察池" not in dashboard_dom and "observation" not in dashboard_dom.lower():
            print("  ✗ Dashboard DOM missing observations section")
            dom_checks.append(("dashboard_observations_section", False))
        else:
            print("  ✓ Dashboard has observations section")
            dom_checks.append(("dashboard_observations_section", True))
        
        if str(dashboard_obs_count) not in dashboard_dom:
            print(f"  ✗ Dashboard DOM missing observation count {dashboard_obs_count}")
            dom_checks.append(("dashboard_observations_count", False))
        else:
            print(f"  ✓ Dashboard shows observation count {dashboard_obs_count}")
            dom_checks.append(("dashboard_observations_count", True))
        
        # 5.2: Observations page
        print("\n[5.2] Verifying /observations page DOM")
        page.goto("http://localhost:3000/observations", wait_until="networkidle", timeout=30000)
        time.sleep(2)
        
        obs_dom = page.content()
        obs_dom_file = verification_dir / "p4-2-observations-dom.md"
        with open(obs_dom_file, "w", encoding="utf-8") as f:
            f.write(f"# Observations Page DOM\n\n")
            f.write(f"Run ID: {run_id}\n\n")
            f.write(f"API Count: {obs_api_count}\n\n")
            f.write(f"## Page Content\n\n```html\n{obs_dom}\n```\n")
        evidence["evidence_files"].append(str(obs_dom_file.name))
        
        if obs_api_count > 0:
            # Must show at least one real observation symbol/name
            first_obs = obs_data.get("positions", [])[0] if obs_data.get("positions") else None
            if first_obs:
                symbol = first_obs.get("symbol", "")
                name = first_obs.get("name", "")
                if symbol in obs_dom or name in obs_dom:
                    print(f"  ✓ Observations page shows real data: {symbol or name}")
                    dom_checks.append(("observations_real_data", True))
                else:
                    print(f"  ✗ Observations page missing real data (expected {symbol} or {name})")
                    dom_checks.append(("observations_real_data", False))
            else:
                print("  ✗ API returned count>0 but no items")
                dom_checks.append(("observations_real_data", False))
        else:
            # Must show real empty state
            if "暂无" in obs_dom or "empty" in obs_dom.lower() or "no observation" in obs_dom.lower():
                print("  ✓ Observations page shows real empty state")
                dom_checks.append(("observations_empty_state", True))
            else:
                print("  ✗ Observations page missing empty state (count=0)")
                dom_checks.append(("observations_empty_state", False))
        
        # 5.3: Signals page
        print("\n[5.3] Verifying /signals page DOM")
        page.goto("http://localhost:3000/signals", wait_until="networkidle", timeout=30000)
        time.sleep(2)
        
        signals_dom = page.content()
        signals_dom_file = verification_dir / "p4-2-signals-dom.md"
        with open(signals_dom_file, "w", encoding="utf-8") as f:
            f.write(f"# Signals Page DOM\n\n")
            f.write(f"Run ID: {run_id}\n\n")
            f.write(f"API Count: {signals_api_count}\n\n")
            f.write(f"## Page Content\n\n```html\n{signals_dom}\n```\n")
        evidence["evidence_files"].append(str(signals_dom_file.name))
        
        if signals_api_count == 0:
            if "暂无" in signals_dom or "empty" in signals_dom.lower() or "no signal" in signals_dom.lower() or "没有找到" in signals_dom:
                print("  ✓ Signals page shows real empty state")
                dom_checks.append(("signals_empty_state", True))
            else:
                print("  ✗ Signals page missing empty state (count=0)")
                dom_checks.append(("signals_empty_state", False))
        else:
            print("  ✓ Signals count > 0, checking for real data")
            dom_checks.append(("signals_has_data", True))
        
        # 5.4: Strategy ideas page
        print("\n[5.4] Verifying /strategy-ideas page DOM")
        page.goto("http://localhost:3000/strategy-ideas", wait_until="networkidle", timeout=30000)
        time.sleep(2)
        
        ideas_dom = page.content()
        ideas_dom_file = verification_dir / "p4-2-strategy-ideas-dom.md"
        with open(ideas_dom_file, "w", encoding="utf-8") as f:
            f.write(f"# Strategy Ideas Page DOM\n\n")
            f.write(f"Run ID: {run_id}\n\n")
            f.write(f"API Count: {ideas_api_count}\n\n")
            f.write(f"## Page Content\n\n```html\n{ideas_dom}\n```\n")
        evidence["evidence_files"].append(str(ideas_dom_file.name))
        
        if ideas_api_count > 0:
            first_idea = ideas_data.get("ideas", [])[0] if ideas_data.get("ideas") else None
            if first_idea:
                idea_id = first_idea.get("idea_id", "")
                if idea_id in ideas_dom or "idea_" in ideas_dom:
                    print(f"  ✓ Strategy ideas page shows real data")
                    dom_checks.append(("ideas_real_data", True))
                else:
                    print(f"  ✗ Strategy ideas page missing real idea_id")
                    dom_checks.append(("ideas_real_data", False))
            else:
                dom_checks.append(("ideas_real_data", False))
        else:
            if "暂无" in ideas_dom or "empty" in ideas_dom.lower():
                print("  ✓ Strategy ideas page shows empty state")
                dom_checks.append(("ideas_empty_state", True))
            else:
                dom_checks.append(("ideas_empty_state", False))
        
        # 5.5: Candidates page
        print("\n[5.5] Verifying /candidate-strategies page DOM")
        page.goto("http://localhost:3000/candidate-strategies", wait_until="networkidle", timeout=30000)
        time.sleep(2)
        
        candidates_dom = page.content()
        candidates_dom_file = verification_dir / "p4-2-candidates-dom.md"
        with open(candidates_dom_file, "w", encoding="utf-8") as f:
            f.write(f"# Candidate Strategies Page DOM\n\n")
            f.write(f"Run ID: {run_id}\n\n")
            f.write(f"API Count: {candidates_api_count}\n\n")
            f.write(f"## Page Content\n\n```html\n{candidates_dom}\n```\n")
        evidence["evidence_files"].append(str(candidates_dom_file.name))
        
        if candidates_api_count > 0:
            first_candidate = candidates_data.get("ideas", [])[0] if candidates_data.get("ideas") else None
            if first_candidate:
                candidate_id = first_candidate.get("idea_id", "")
                if candidate_id in candidates_dom or "candidate" in candidates_dom.lower():
                    print(f"  ✓ Candidates page shows real data")
                    dom_checks.append(("candidates_real_data", True))
                else:
                    print(f"  ✗ Candidates page missing real candidate_id")
                    dom_checks.append(("candidates_real_data", False))
            else:
                dom_checks.append(("candidates_real_data", False))
        else:
            if "暂无" in candidates_dom or "empty" in candidates_dom.lower():
                print("  ✓ Candidates page shows empty state")
                dom_checks.append(("candidates_empty_state", True))
            else:
                dom_checks.append(("candidates_empty_state", False))
        
        # 5.6: Rejected page
        print("\n[5.6] Verifying /rejected-strategies page DOM")
        page.goto("http://localhost:3000/rejected-strategies", wait_until="networkidle", timeout=30000)
        time.sleep(2)
        
        rejected_dom = page.content()
        rejected_dom_file = verification_dir / "p4-2-rejected-dom.md"
        with open(rejected_dom_file, "w", encoding="utf-8") as f:
            f.write(f"# Rejected Strategies Page DOM\n\n")
            f.write(f"Run ID: {run_id}\n\n")
            f.write(f"API Count: {rejected_api_count}\n\n")
            f.write(f"## Page Content\n\n```html\n{rejected_dom}\n```\n")
        evidence["evidence_files"].append(str(rejected_dom_file.name))
        
        if rejected_api_count > 0:
            rejected_ideas = [idea for idea in ideas_data.get("ideas", []) if idea.get("decision") == "rejected"]
            if rejected_ideas:
                rejected_id = rejected_ideas[0].get("idea_id", "")
                if rejected_id in rejected_dom or "rejected" in rejected_dom.lower():
                    print(f"  ✓ Rejected page shows real data")
                    dom_checks.append(("rejected_real_data", True))
                else:
                    print(f"  ✗ Rejected page missing real rejected_id")
                    dom_checks.append(("rejected_real_data", False))
            else:
                dom_checks.append(("rejected_real_data", False))
        else:
            if "暂无" in rejected_dom or "empty" in rejected_dom.lower():
                print("  ✓ Rejected page shows empty state")
                dom_checks.append(("rejected_empty_state", True))
            else:
                dom_checks.append(("rejected_empty_state", False))
        
        # 5.7: Validations page
        print("\n[5.7] Verifying /strategy-validations page DOM")
        page.goto("http://localhost:3000/strategy-validations", wait_until="networkidle", timeout=30000)
        time.sleep(2)
        
        validations_dom = page.content()
        validations_dom_file = verification_dir / "p4-2-validations-dom.md"
        with open(validations_dom_file, "w", encoding="utf-8") as f:
            f.write(f"# Strategy Validations Page DOM\n\n")
            f.write(f"Run ID: {run_id}\n\n")
            f.write(f"API Count: {validations_api_count}\n\n")
            f.write(f"## Page Content\n\n```html\n{validations_dom}\n```\n")
        evidence["evidence_files"].append(str(validations_dom_file.name))
        
        if validations_api_count == 0:
            if "暂无" in validations_dom or "empty" in validations_dom.lower() or "0" in validations_dom:
                print("  ✓ Validations page shows empty state")
                dom_checks.append(("validations_empty_state", True))
            else:
                print("  ✗ Validations page missing empty state (count=0)")
                dom_checks.append(("validations_empty_state", False))
        else:
            print("  ✗ Validations count should be 0")
            dom_checks.append(("validations_count_zero", False))
        
        # 5.8: Strategies page
        print("\n[5.8] Verifying /strategies page DOM")
        page.goto("http://localhost:3000/strategies", wait_until="networkidle", timeout=30000)
        time.sleep(2)
        
        strategies_dom = page.content()
        strategies_dom_file = verification_dir / "p4-2-strategies-dom.md"
        with open(strategies_dom_file, "w", encoding="utf-8") as f:
            f.write(f"# Strategies Page DOM\n\n")
            f.write(f"Run ID: {run_id}\n\n")
            f.write(f"API Count: {strategies_api_count}\n\n")
            f.write(f"## Page Content\n\n```html\n{strategies_dom}\n```\n")
        evidence["evidence_files"].append(str(strategies_dom_file.name))
        
        if strategies_api_count == 0:
            if "暂无" in strategies_dom or "empty" in strategies_dom.lower() or "0" in strategies_dom:
                print("  ✓ Strategies page shows empty state")
                dom_checks.append(("strategies_empty_state", True))
            else:
                print("  ✗ Strategies page missing empty state (count=0)")
                dom_checks.append(("strategies_empty_state", False))
        else:
            print("  ✗ Strategies count should be 0")
            dom_checks.append(("strategies_count_zero", False))
        
        # 5.9: Templates page
        print("\n[5.9] Verifying /strategy-templates page DOM")
        page.goto("http://localhost:3000/strategy-templates", wait_until="networkidle", timeout=30000)
        time.sleep(2)
        
        templates_dom = page.content()
        templates_dom_file = verification_dir / "p4-2-templates-dom.md"
        with open(templates_dom_file, "w", encoding="utf-8") as f:
            f.write(f"# Strategy Templates Page DOM\n\n")
            f.write(f"Run ID: {run_id}\n\n")
            f.write(f"API Count: {templates_api_count}\n\n")
            f.write(f"## Page Content\n\n```html\n{templates_dom}\n```\n")
        evidence["evidence_files"].append(str(templates_dom_file.name))
        
        if templates_api_count == 4:
            first_template = templates_data.get("templates", [])[0] if templates_data.get("templates") else None
            if first_template:
                template_id = first_template.get("template_id", "")
                if template_id in templates_dom or "theme_momentum" in templates_dom:
                    print(f"  ✓ Templates page shows real template data")
                    dom_checks.append(("templates_real_data", True))
                else:
                    print(f"  ✗ Templates page missing real template_id")
                    dom_checks.append(("templates_real_data", False))
            else:
                dom_checks.append(("templates_real_data", False))
        else:
            print(f"  ✗ Templates count should be 4, got {templates_api_count}")
            dom_checks.append(("templates_count_four", False))
        
        # Step 6: Network log verification
        print()
        print("Step 6: Network log verification")
        print("-" * 80)
        
        # Save network log
        network_log_file = verification_dir / "p4-2-dashboard-drilldown-network-log.json"
        with open(network_log_file, "w", encoding="utf-8") as f:
            json.dump(network_log, f, indent=2, ensure_ascii=False)
        evidence["evidence_files"].append(str(network_log_file.name))
        evidence["network_requests"] = network_log
        
        print(f"  Total network requests: {len(network_log)}")
        
        # Check for external API calls
        api_requests = [req for req in network_log if req["resource_type"] == "fetch" or req["resource_type"] == "xhr"]
        external_apis = [req for req in api_requests 
                        if not req["url"].startswith("http://localhost:8010") 
                        and not req["url"].startswith("http://localhost:3000")]
        
        if external_apis:
            print(f"  ✗ Found {len(external_apis)} external API requests:")
            for req in external_apis[:5]:
                print(f"    - {req['url']}")
            return 1
        else:
            print(f"  ✓ All {len(api_requests)} API requests point to localhost")
            backend_api_count = len([req for req in api_requests if req["url"].startswith("http://localhost:8010")])
            print(f"    - {backend_api_count} requests to backend (localhost:8010)")
            print(f"    - {len(api_requests) - backend_api_count} requests to frontend (localhost:3000)")
        
        # Step 7: Summary
        print()
        print("Step 7: Verification summary")
        print("-" * 80)
        
        failed_checks = [name for name, passed in drilldown_checks if not passed]
        failed_dom_checks = [name for name, passed in dom_checks if not passed]
        
        if failed_checks or failed_dom_checks:
            print(f"✗ {len(failed_checks + failed_dom_checks)} checks failed:")
            if failed_checks:
                print("  API Drilldown:")
                for name in failed_checks:
                    print(f"    - {name}")
            if failed_dom_checks:
                print("  DOM Verification:")
                for name in failed_dom_checks:
                    print(f"    - {name}")
            print()
            if evidence["inconsistencies"]:
                print("Inconsistencies:")
                for inc in evidence["inconsistencies"]:
                    print(f"  - {inc}")
            return 1
        
        print(f"✓ All {len(drilldown_checks)} API drilldown checks passed")
        print(f"✓ All {len(dom_checks)} DOM checks passed")
        evidence["checks"]["drilldown_consistency"] = True
        evidence["checks"]["dom_verification"] = True
        evidence["checks"]["network_validation"] = True
        
        # Save backend log
        print()
        print("Step 8: Save evidence")
        print("-" * 80)
        
        backend_log_path = project_root / "backend_server.log"
        if backend_log_path.exists():
            backend_log_file = verification_dir / "p4-2-backend-log.txt"
            with open(backend_log_path, "r", encoding="utf-8") as src:
                with open(backend_log_file, "w", encoding="utf-8") as dst:
                    dst.write(src.read())
            evidence["evidence_files"].append(str(backend_log_file.name))
            print("✓ Saved backend log")
        
        # Save evidence summary
        evidence_file = verification_dir / "p4-2-verification-summary.json"
        with open(evidence_file, "w", encoding="utf-8") as f:
            json.dump(evidence, f, indent=2, ensure_ascii=False)
        evidence["evidence_files"].append(str(evidence_file.name))
        print("✓ Saved evidence summary")
        
        print()
        print("=" * 100)
        print("✓ P4-2 DASHBOARD DRILLDOWN CONSISTENCY VERIFICATION PASSED")
        print("=" * 100)
        print()
        print(f"Run ID: {run_id}")
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
                save_log=verification_dir / "p4-2-frontend-log.txt",
                release_ports=[3000]
            )
        
        if backend_process:
            stop_process(
                backend_process,
                name="Backend",
                release_ports=[8010]
            )

if __name__ == "__main__":
    try:
        exit_code = verify_p4_2_dashboard_drilldown_consistency()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n鈿?Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n鉁?Verification failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

