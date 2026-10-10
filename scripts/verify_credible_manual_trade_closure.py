#!/usr/bin/env python3
"""
Credible Manual Trade Closure — Task 0 (extended)

Full chain: friend rec -> ResearchCase -> user hypothesis (pending, verbatim)
-> real research (LLM + Tushare) -> explicit user decision
(continue/observe/stop) -> forward-only confirmed_candidate_pool.

Single-worker backend (--workers 1), REAL LLM + Tushare (no stub/fixture/fake).
Fails at first missing step. Asserts 1..3 real LLM calls via [LLM_TELEMETRY].

Req 7/8: extend ONLY this script; run once; fix-once-retry-once.
"""

import json
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.runtime_process_helpers import (
    check_and_release_ports,
    start_backend,
    start_frontend,
    wait_for_http,
    stop_process,
)

RUN_ID = f"CREDIBLE_RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
DOCS_ROOT = Path(__file__).parent.parent / "docs" / "verification"
DOCS = DOCS_ROOT / RUN_ID
DOCS.mkdir(parents=True, exist_ok=True)

# Verbatim, PENDING-ONLY user hypothesis (never a verified chain / dataset).
USER_HYPOTHESIS = {
    "upstream_entity": "贵州茅台",
    "downstream_entity": "白酒渠道经销商",
    "relation_type": "supplier",
    "asserted_by": "user",
    "scope_note": "pending",
}

# --- backend stdout drain for LLM telemetry ---
def _drain_backend(process, lines_out, stop_event):
    """Drain stdout from process into lines_out until stop_event."""
    try:
        for line in process.stdout:
            lines_out.append(line)
            if stop_event.is_set():
                break
    except Exception:
        pass


def _count_telemetry(lines):
    return sum(1 for l in lines if "[LLM_TELEMETRY]" in l)


def _telemetry_latencies(lines):
    out = []
    for l in lines:
        if "[LLM_TELEMETRY]" in l:
            m = re.search(r"elapsed_s=([0-9.]+)", l)
            if m:
                out.append(float(m.group(1)))
    return out


def main():
    print("=" * 80)
    print("CREDIBLE MANUAL TRADE CLOSURE — TASK 0 (extended)")
    print(f"Run ID: {RUN_ID}")
    print("=" * 80)

    timings = {}
    user_wait = {"total": 0.0}
    start_time = time.time()

    check_and_release_ports([8010, 3010])

    backend = None
    backend_lines = []
    backend_reader_stop = threading.Event()
    frontend = None
    pw = None
    browser = None

    t0 = time.time()
    backend = start_backend(
        port=8010,
        project_root=Path(__file__).parent.parent,
        extra_env={
            "RESEARCH_CONVERSATION_MODE": "real",
        },
    )
    timings["backend_start"] = time.time() - t0
    print(f"[TIMING] Backend start: {timings['backend_start']:.1f}s")

    # Drain backend stdout (real LLM telemetry lives here).
    reader = threading.Thread(
        target=_drain_backend,
        args=(backend, backend_lines, backend_reader_stop),
        daemon=True,
    )
    reader.start()

    t0 = time.time()
    frontend = start_frontend(port=3010, project_root=Path(__file__).parent.parent)
    timings["frontend_start"] = time.time() - t0
    print(f"[TIMING] Frontend start: {timings['frontend_start']:.1f}s")

    if not wait_for_http(
        "http://localhost:3010/workbench",
        timeout_seconds=60,
        process=frontend,
        process_name="Frontend Workbench route",
    ):
        raise RuntimeError("Frontend Workbench route did not become ready")

    t0 = time.time()
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context()
    page = ctx.new_page()
    timings["browser_start"] = time.time() - t0
    print(f"[TIMING] Browser start: {timings['browser_start']:.1f}s")

    net_log, console_log, page_errors = [], [], []
    page.on("request", lambda r: net_log.append({"url": r.url, "method": r.method, "ts": time.time()}))
    page.on("console", lambda msg: console_log.append({"type": msg.type, "text": msg.text, "ts": time.time()}))
    page.on("pageerror", lambda err: page_errors.append({"error": str(err), "ts": time.time()}))
    page.on("requestfailed", lambda req: net_log.append({"url": req.url, "method": req.method, "failure": str(req.failure), "ts": time.time()}))

    failure = None
    try:
        # [1] Friend recommendation -> ResearchCase
        t0 = time.time()
        page.goto("http://localhost:3010/workbench", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("input[placeholder='输入消息...']", timeout=10000)
        page.wait_for_timeout(500)
        user_wait["total"] += 0.5
        timings["workbench_load"] = time.time() - t0
        print(f"[TIMING] Workbench load: {timings['workbench_load']:.1f}s")

        t0 = time.time()
        input_locator = page.locator("input[placeholder='输入消息...']").first
        input_locator.click()
        input_locator.type(f"朋友推荐贵州茅台（600519），备注 {RUN_ID}", delay=50)
        with page.expect_response("**/api/agent/workbench/message", timeout=20000) as response_info:
            input_locator.press("Enter")
        response = response_info.value
        timings["post_response"] = time.time() - t0
        print(f"[TIMING] POST response: {timings['post_response']:.1f}s, status={response.status}")

        if response.status != 200:
            try:
                body = response.text()
                (DOCS / "credible_post_response.txt").write_text(body[:2000], encoding="utf-8")
            except Exception as e:
                print(f"[ERROR] Could not read response body: {e}")
            failure = f"POST failed: {response.status}"
            raise AssertionError(failure)

        page.wait_for_timeout(2000)
        user_wait["total"] += 2.0
        dom = page.content()
        (DOCS / "credible_1_workbench.html").write_text(dom, encoding="utf-8")

        if "case_" not in dom and "研究案例" not in dom and "research_unavailable" not in dom:
            failure = "ResearchCase not created (no case_ ID or status)"
            raise AssertionError(failure)
        print("[1] ResearchCase created")

        case_id = None
        m = re.search(r"case_[0-9a-f]{12}", dom)
        if m:
            case_id = m.group(0)
            print(f"[1.1] Case ID: {case_id}")
        if not case_id:
            failure = "Case ID not found in Workbench response"
            raise AssertionError(failure)

        # [1.2] Navigate to ResearchCase detail page
        t0 = time.time()
        page.goto(f"http://localhost:3010/research/{case_id}", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(2000)
        user_wait["total"] += 2.0
        timings["research_page_load"] = time.time() - t0
        print(f"[TIMING] Research detail page: {timings['research_page_load']:.1f}s")
        detail_dom = page.content()
        (DOCS / "credible_2_research_detail.html").write_text(detail_dom, encoding="utf-8")

        if case_id not in detail_dom:
            failure = f"Case ID {case_id} not visible on detail page"
            raise AssertionError(failure)
        if "用户产业链假设（待验证）" not in detail_dom:
            failure = "Hypothesis (pending) section missing on detail page"
            raise AssertionError(failure)
        print("[1.2] ResearchCase detail page verified (hypothesis section present)")

        # [2] Save user hypothesis VERBATIM as pending-only
        t0 = time.time()
        page.locator("textarea").fill(json.dumps(USER_HYPOTHESIS, ensure_ascii=False))
        with page.expect_response(f"**/api/research/themes/{case_id}/hypothesis", timeout=20000) as hi:
            page.locator("button:has-text('保存假设')").click()
        hr = hi.value
        timings["hypothesis_save"] = time.time() - t0
        print(f"[TIMING] Hypothesis save: {timings['hypothesis_save']:.1f}s, status={hr.status}")
        if hr.status != 200:
            failure = f"Hypothesis save failed: {hr.status}"
            raise AssertionError(failure)
        page.wait_for_timeout(1500)
        user_wait["total"] += 1.5
        # Wait for verbatim hypothesis to render (pending-only view).
        page.wait_for_function(
            "() => document.body.innerText.includes('白酒渠道经销商')",
            timeout=15000,
        )
        detail_dom = page.content()
        (DOCS / "credible_3_hypothesis.html").write_text(detail_dom, encoding="utf-8")
        if "白酒渠道经销商" not in detail_dom:
            failure = "Hypothesis verbatim content not rendered after save"
            raise AssertionError(failure)
        if "不会被当作数据集" not in detail_dom:
            failure = "Pending-only disclaimer missing on detail page"
            raise AssertionError(failure)
        print("[2] User hypothesis saved verbatim as PENDING (never a verified chain)")

        # [3] Run REAL research (LLM + Tushare)
        tele_before = _count_telemetry(backend_lines)
        t0 = time.time()
        with page.expect_response(f"**/api/research/themes/{case_id}/run-research", timeout=300000) as ri:
            page.locator("button:has-text('运行研究')").click()
        rr = ri.value
        timings["run_research"] = time.time() - t0
        print(f"[TIMING] Run research: {timings['run_research']:.1f}s, status={rr.status}")

        if rr.status != 200:
            try:
                body = rr.text()
                (DOCS / "credible_research_fail.txt").write_text(body[:3000], encoding="utf-8")
            except Exception:
                pass
            failure = f"Run research failed: {rr.status}"
            raise AssertionError(failure)

        research_body = rr.json()
        # Wait for research output to render (button label flips to 重新运行研究).
        page.locator("button:has-text('重新运行研究')").wait_for(state="attached", timeout=30000)
        detail_dom = page.content()
        (DOCS / "credible_4_research.html").write_text(detail_dom, encoding="utf-8")

        # Assert real LLM call count 1..3 (isolated to this research run).
        tele_after = _count_telemetry(backend_lines)
        llm_calls = tele_after - tele_before
        tele_lines = [l for l in backend_lines[tele_before:tele_after] if "[LLM_TELEMETRY]" in l]
        llm_latencies = _telemetry_latencies(tele_lines)
        print(f"[3] Real LLM calls this run: {llm_calls} (telemetry lines: {len(tele_lines)})")
        if not (1 <= llm_calls <= 3):
            failure = f"Real LLM call count out of range [1,3]: {llm_calls}"
            raise AssertionError(failure)
        if "支撑事实 / 反证：" not in detail_dom and "数据缺口：" not in detail_dom and "价值链层级：" not in detail_dom:
            failure = "Research output did not render traceable facts/counter/gaps"
            raise AssertionError(failure)
        print("[3] Real research produced traceable facts / counter-evidence / gaps")

        # Extract Tushare source IDs (no secrets) from research output.
        source_ids = []
        for _sym, c in (research_body.get("candidate_rationales") or {}).items():
            if isinstance(c, dict):
                source_ids.extend(c.get("supporting_source_ids") or [])
        evidence_gaps = research_body.get("evidence_gaps") or []
        print(f"[3] Tushare source IDs referenced: {source_ids}")
        print(f"[3] Evidence gaps: {evidence_gaps}")

        # [4] Explicit user decision: continue -> forward-only pool (via deterministic reducer)
        t0 = time.time()
        with page.expect_response(f"**/api/research/themes/{case_id}/decision", timeout=60000) as di:
            page.locator("button:has-text('继续')").click()
        dr = di.value
        timings["decision"] = time.time() - t0
        print(f"[TIMING] Decision (continue): {timings['decision']:.1f}s, status={dr.status}")

        if dr.status != 200:
            try:
                body = dr.text()
                (DOCS / "credible_decision_fail.txt").write_text(body[:3000], encoding="utf-8")
            except Exception:
                pass
            failure = f"Decision (continue) failed: {dr.status}"
            raise AssertionError(failure)

        decision_body = dr.json()
        # Wait for forward-only pool card to render.
        page.wait_for_function(
            "() => document.body.innerText.includes('前向候选池')",
            timeout=30000,
        )
        detail_dom = page.content()
        (DOCS / "credible_5_pool.html").write_text(detail_dom, encoding="utf-8")

        # Trust-boundary assertions (Req 3/4).
        assert decision_body.get("forward_only") is True, "pool not forward_only"
        assert decision_body.get("is_buy_signal") is False, "pool mislabeled as buy signal"
        assert decision_body.get("is_backtest_universe") is False, "pool mislabeled as backtest universe"
        assert decision_body.get("approval_decision") == "continue", "decision != continue"
        assert decision_body.get("confirmed_by") == "user", "confirmed_by != user"
        assert decision_body.get("confirmed_id"), "confirmed_id missing"
        assert decision_body.get("pool_id"), "pool_id missing"
        if "前向唯一" not in detail_dom or "不是买入信号" not in detail_dom:
            failure = "Forward-only disclaimer (not buy signal / not backtest universe) missing"
            raise AssertionError(failure)
        print("[4] Explicit continue -> forward-only confirmed_candidate_pool created via deterministic reducer")
        print("    forward_only=True, is_buy_signal=False, is_backtest_universe=False")

        # [5] Read separately validated strategy signal via real browser DOM
        print("\n[5] Navigating to Signal Board...")
        t0 = time.time()
        page.goto("http://localhost:3010/signals", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=30000)
        timings["signals_page_load"] = time.time() - t0
        signals_dom = page.content()
        (DOCS / "credible_6_signals.html").write_text(signals_dom, encoding="utf-8")
        
        # Check visible DOM for signal rows with prototype_passed lifecycle
        # ponytail: DOM text search, not API substitute
        if "prototype_passed" not in signals_dom or "signal_" not in signals_dom:
            # FIRST PRODUCT BLOCKER: no validated signal visible
            print("[5] [BLOCKED] No prototype_passed signal in visible DOM")
            
            total_wall = time.time() - start_time
            productive = total_wall - user_wait["total"]
            
            blocker_summary = {
                "run_id": RUN_ID,
                "status": "BLOCKED",
                "first_product_blocker": "no_validated_signal_visible_in_dom",
                "blocker_detail": "Signal Board DOM contains no visible signal row with lifecycle_state=prototype_passed",
                "last_completed_step": 4,
                "steps_completed": [
                    "1. Friend recommendation → ResearchCase",
                    "2. User hypothesis (pending verification)",
                    "3. Real research (LLM + Tushare)",
                    "4. Explicit continue → confirmed_candidate_pool",
                ],
                "steps_blocked": [
                    "5. Separately validated strategy signal (BLOCKED - no prototype_passed in DOM)",
                ],
                "case_id": case_id,
                "real_llm_calls": llm_calls,
                "timings_s": {k: round(v, 2) for k, v in timings.items()},
                "total_wall_s": round(total_wall, 2),
                "productive_total_s": round(productive, 2),
            }
            (DOCS / "credible_blocker.json").write_text(json.dumps(blocker_summary, indent=2, ensure_ascii=False), encoding="utf-8")
            (DOCS / "credible_backend_stdout.log").write_text("".join(backend_lines), encoding="utf-8")
            (DOCS / "CREDIBLE_PRODUCT_ACCEPTANCE.md").write_text(
                f"# Credible Product Acceptance — Task 0 (extended)\n\n"
                f"**Run ID:** `{RUN_ID}`\n"
                f"**Status:** ❌ BLOCKED\n\n"
                f"## First Product Blocker\n"
                f"**Step 5:** Separately validated strategy signal\n\n"
                f"**Blocker:** `no_validated_signal_visible_in_dom`\n\n"
                f"{blocker_summary['blocker_detail']}\n\n"
                f"## Steps Completed (1-4)\n"
                f"1. ✓ Friend recommendation → ResearchCase (`{case_id}`)\n"
                f"2. ✓ User hypothesis (pending verification) persisted verbatim\n"
                f"3. ✓ Real research (LLM + Tushare) generated traceable facts/counter-evidence/gaps\n"
                f"4. ✓ Explicit continue → forward-only confirmed_candidate_pool\n\n"
                f"## Steps Blocked (5-13)\n"
                f"5. ✗ Separately validated strategy signal (BLOCKED - no prototype_passed signal in DOM)\n"
                f"6. ✗ Market Guard (not reached)\n"
                f"7. ✗ Action Plan (not reached)\n"
                f"8. ✗ User confirm buy (not reached)\n"
                f"9. ✗ Observation Pool (not reached)\n"
                f"10. ✗ Daily Signal (not reached)\n"
                f"11. ✗ User confirm sell (not reached)\n"
                f"12. ✗ P&L (not reached)\n"
                f"13. ✗ Discipline Review (not reached)\n\n"
                f"## Real LLM calls: {llm_calls} (range [1,3] OK)\n"
                f"## Timings (s): {json.dumps({k: round(v,2) for k,v in timings.items()}, ensure_ascii=False)}\n"
                f"## Total wall: {round(total_wall,2)}s | productive: {round(productive,2)}s\n\n"
                f"## Evidence\n"
                f"- `credible_1_workbench.html`\n"
                f"- `credible_2_research_detail.html`\n"
                f"- `credible_3_hypothesis.html`\n"
                f"- `credible_4_research.html`\n"
                f"- `credible_5_pool.html`\n"
                f"- `credible_6_signals.html` (Signal Board - no prototype_passed signals visible)\n"
                f"- `credible_blocker.json`\n"
                f"- `credible_backend_stdout.log`\n",
                encoding="utf-8",
            )
            
            print(f"\n[BLOCKED] at step 5: {blocker_summary['first_product_blocker']}")
            print(f"   Completed: 1-4 | Evidence: {DOCS}")
            sys.exit(1)
        
        # Signal visible: extract first signal_id from DOM, navigate to detail
        print("[5] [OK] prototype_passed signal visible in DOM")
        m = re.search(r"signal_[0-9a-f]{12}", signals_dom)
        if not m:
            failure = "Signal ID not found in DOM after prototype_passed check"
            raise AssertionError(failure)
        signal_id = m.group(0)
        print(f"[5.1] Signal ID: {signal_id}")
        
        # [6] Navigate to signal detail page, check Action Plan availability
        print("\n[6] Navigating to signal detail page...")
        t0 = time.time()
        page.goto(f"http://localhost:3010/signals/{signal_id}", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=30000)
        timings["signal_detail_load"] = time.time() - t0
        signal_detail_dom = page.content()
        (DOCS / "credible_7_signal_detail.html").write_text(signal_detail_dom, encoding="utf-8")
        
        # Check if Action Plan section is visible in DOM
        # ponytail: text search for Action Plan / 执行计划
        if "执行计划" not in signal_detail_dom and "Action Plan" not in signal_detail_dom:
            # FIRST PRODUCT BLOCKER: Action Plan not available
            print("[6] [BLOCKED] Action Plan not visible in signal detail page")
            
            total_wall = time.time() - start_time
            productive = total_wall - user_wait["total"]
            
            blocker_summary = {
                "run_id": RUN_ID,
                "status": "BLOCKED",
                "first_product_blocker": "action_plan_not_visible",
                "blocker_detail": f"Signal detail page for {signal_id} contains no Action Plan section",
                "last_completed_step": 5,
                "steps_completed": [
                    "1. Friend recommendation → ResearchCase",
                    "2. User hypothesis (pending verification)",
                    "3. Real research (LLM + Tushare)",
                    "4. Explicit continue → confirmed_candidate_pool",
                    "5. Separately validated strategy signal (found in DOM)",
                ],
                "steps_blocked": [
                    "6. Action Plan (BLOCKED - not visible on signal detail page)",
                ],
                "case_id": case_id,
                "signal_id": signal_id,
                "real_llm_calls": llm_calls,
                "timings_s": {k: round(v, 2) for k, v in timings.items()},
                "total_wall_s": round(total_wall, 2),
                "productive_total_s": round(productive, 2),
            }
            (DOCS / "credible_blocker.json").write_text(json.dumps(blocker_summary, indent=2, ensure_ascii=False), encoding="utf-8")
            (DOCS / "credible_backend_stdout.log").write_text("".join(backend_lines), encoding="utf-8")
            (DOCS / "CREDIBLE_PRODUCT_ACCEPTANCE.md").write_text(
                f"# Credible Product Acceptance — Task 0 (extended)\n\n"
                f"**Run ID:** `{RUN_ID}`\n"
                f"**Status:** ❌ BLOCKED\n\n"
                f"## First Product Blocker\n"
                f"**Step 6:** Action Plan\n\n"
                f"**Blocker:** `action_plan_not_visible`\n\n"
                f"{blocker_summary['blocker_detail']}\n\n"
                f"## Steps Completed (1-5)\n"
                f"1. ✓ Friend recommendation → ResearchCase (`{case_id}`)\n"
                f"2. ✓ User hypothesis (pending verification) persisted verbatim\n"
                f"3. ✓ Real research (LLM + Tushare) generated traceable facts/counter-evidence/gaps\n"
                f"4. ✓ Explicit continue → forward-only confirmed_candidate_pool\n"
                f"5. ✓ Separately validated strategy signal found (`{signal_id}`)\n\n"
                f"## Steps Blocked (6-13)\n"
                f"6. ✗ Action Plan (BLOCKED - not visible on signal detail page)\n"
                f"7. ✗ User confirm buy (not reached)\n"
                f"8. ✗ Observation Pool (not reached)\n"
                f"9. ✗ Daily Signal (not reached)\n"
                f"10. ✗ User confirm sell (not reached)\n"
                f"11. ✗ P&L (not reached)\n"
                f"12. ✗ Discipline Review (not reached)\n\n"
                f"## Real LLM calls: {llm_calls} (range [1,3] OK)\n"
                f"## Timings (s): {json.dumps({k: round(v,2) for k,v in timings.items()}, ensure_ascii=False)}\n"
                f"## Total wall: {round(total_wall,2)}s | productive: {round(productive,2)}s\n\n"
                f"## Evidence\n"
                f"- `credible_1_workbench.html`\n"
                f"- `credible_2_research_detail.html`\n"
                f"- `credible_3_hypothesis.html`\n"
                f"- `credible_4_research.html`\n"
                f"- `credible_5_pool.html`\n"
                f"- `credible_6_signals.html`\n"
                f"- `credible_7_signal_detail.html` (no Action Plan section)\n"
                f"- `credible_blocker.json`\n"
                f"- `credible_backend_stdout.log`\n",
                encoding="utf-8",
            )
            
            print(f"\n[BLOCKED] at step 6: {blocker_summary['first_product_blocker']}")
            print(f"   Completed: 1-5 | Signal: {signal_id} | Evidence: {DOCS}")
            sys.exit(1)
        
        print("[6] [OK] Action Plan section visible in DOM")
        
        # [7] Check for user action button (confirm buy / 确认买入)
        print("\n[7] Checking for user action confirmation button...")
        if "确认买入" not in signal_detail_dom and "确认执行" not in signal_detail_dom and "user_marked_execute" not in signal_detail_dom:
            # FIRST PRODUCT BLOCKER: no confirmation button
            print("[7] [BLOCKED] No user action confirmation button visible")
            
            total_wall = time.time() - start_time
            productive = total_wall - user_wait["total"]
            
            blocker_summary = {
                "run_id": RUN_ID,
                "status": "BLOCKED",
                "first_product_blocker": "no_user_action_button",
                "blocker_detail": f"Action Plan for {signal_id} has no visible user confirmation button",
                "last_completed_step": 6,
                "steps_completed": [
                    "1. Friend recommendation → ResearchCase",
                    "2. User hypothesis (pending verification)",
                    "3. Real research (LLM + Tushare)",
                    "4. Explicit continue → confirmed_candidate_pool",
                    "5. Separately validated strategy signal (found in DOM)",
                    "6. Action Plan (visible on signal detail page)",
                ],
                "steps_blocked": [
                    "7. User confirm buy (BLOCKED - no confirmation button visible)",
                ],
                "case_id": case_id,
                "signal_id": signal_id,
                "real_llm_calls": llm_calls,
                "timings_s": {k: round(v, 2) for k, v in timings.items()},
                "total_wall_s": round(total_wall, 2),
                "productive_total_s": round(productive, 2),
            }
            (DOCS / "credible_blocker.json").write_text(json.dumps(blocker_summary, indent=2, ensure_ascii=False), encoding="utf-8")
            (DOCS / "credible_backend_stdout.log").write_text("".join(backend_lines), encoding="utf-8")
            (DOCS / "CREDIBLE_PRODUCT_ACCEPTANCE.md").write_text(
                f"# Credible Product Acceptance — Task 0 (extended)\n\n"
                f"**Run ID:** `{RUN_ID}`\n"
                f"**Status:** ❌ BLOCKED\n\n"
                f"## First Product Blocker\n"
                f"**Step 7:** User confirm buy\n\n"
                f"**Blocker:** `no_user_action_button`\n\n"
                f"{blocker_summary['blocker_detail']}\n\n"
                f"## Steps Completed (1-6)\n"
                f"1. ✓ Friend recommendation → ResearchCase (`{case_id}`)\n"
                f"2. ✓ User hypothesis (pending verification) persisted verbatim\n"
                f"3. ✓ Real research (LLM + Tushare) generated traceable facts/counter-evidence/gaps\n"
                f"4. ✓ Explicit continue → forward-only confirmed_candidate_pool\n"
                f"5. ✓ Separately validated strategy signal found (`{signal_id}`)\n"
                f"6. ✓ Action Plan visible on signal detail page\n\n"
                f"## Steps Blocked (7-13)\n"
                f"7. ✗ User confirm buy (BLOCKED - no confirmation button visible)\n"
                f"8. ✗ Observation Pool (not reached)\n"
                f"9. ✗ Daily Signal (not reached)\n"
                f"10. ✗ User confirm sell (not reached)\n"
                f"11. ✗ P&L (not reached)\n"
                f"12. ✗ Discipline Review (not reached)\n\n"
                f"## Real LLM calls: {llm_calls} (range [1,3] OK)\n"
                f"## Timings (s): {json.dumps({k: round(v,2) for k,v in timings.items()}, ensure_ascii=False)}\n"
                f"## Total wall: {round(total_wall,2)}s | productive: {round(productive,2)}s\n\n"
                f"## Evidence\n"
                f"- `credible_1_workbench.html`\n"
                f"- `credible_2_research_detail.html`\n"
                f"- `credible_3_hypothesis.html`\n"
                f"- `credible_4_research.html`\n"
                f"- `credible_5_pool.html`\n"
                f"- `credible_6_signals.html`\n"
                f"- `credible_7_signal_detail.html` (Action Plan visible, no user button)\n"
                f"- `credible_blocker.json`\n"
                f"- `credible_backend_stdout.log`\n",
                encoding="utf-8",
            )
            
            print(f"\n[BLOCKED] at step 7: {blocker_summary['first_product_blocker']}")
            print(f"   Completed: 1-6 | Signal: {signal_id} | Evidence: {DOCS}")
            sys.exit(1)
        
        print("[7] [OK] User action button visible (stopped at first product UI element requiring real user decision)")
        print(f"   Main chain reached: signal → Action Plan → user confirmation boundary")
        print(f"   Steps 8-13 (Observation Pool → Daily Signal → sell → P&L → Review) require actual execution, out of scope for harness")
        
        # Success: reached user confirmation boundary (step 7)
        total_wall = time.time() - start_time
        productive = total_wall - user_wait["total"]
        
        summary = {
            "run_id": RUN_ID,
            "status": "REACHED_USER_BOUNDARY",
            "last_completed_step": 7,
            "case_id": case_id,
            "signal_id": signal_id,
            "real_llm_calls": llm_calls,
            "llm_per_call_latency_s": [round(x, 3) for x in llm_latencies],
            "llm_total_latency_s": round(sum(llm_latencies), 3),
            "tushare_source_ids": source_ids,
            "evidence_gaps": evidence_gaps,
            "timings_s": {k: round(v, 2) for k, v in timings.items()},
            "total_wall_s": round(total_wall, 2),
            "user_wait_s": round(user_wait["total"], 2),
            "productive_total_s": round(productive, 2),
            "network_requests": len(net_log),
            "console_messages": len(console_log),
            "page_errors": len(page_errors),
        }
        (DOCS / "credible_success.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        (DOCS / "credible_backend_stdout.log").write_text("".join(backend_lines), encoding="utf-8")
        (DOCS / "CREDIBLE_PRODUCT_ACCEPTANCE.md").write_text(
            f"# Credible Product Acceptance — Task 0 (extended)\n\n"
            f"**Run ID:** `{RUN_ID}`\n"
            f"**Status:** ✅ REACHED_USER_BOUNDARY (steps 1-7 complete)\n\n"
            f"## Steps Completed (1-7)\n"
            f"1. ✓ Friend recommendation → ResearchCase (`{case_id}`)\n"
            f"2. ✓ User hypothesis (pending verification) persisted verbatim\n"
            f"3. ✓ Real research (LLM + Tushare) generated traceable facts/counter-evidence/gaps\n"
            f"4. ✓ Explicit continue → forward-only confirmed_candidate_pool\n"
            f"5. ✓ Separately validated strategy signal found (`{signal_id}`)\n"
            f"6. ✓ Action Plan visible on signal detail page\n"
            f"7. ✓ User action button visible (confirmation boundary reached)\n\n"
            f"## Steps Out of Scope (8-13)\n"
            f"8-13: Observation Pool → Daily Signal → sell → P&L → Review (require actual execution)\n\n"
            f"## Real LLM calls: {llm_calls} (range [1,3] OK)\n"
            f"## Tushare source IDs: {source_ids}\n"
            f"## Evidence gaps: {evidence_gaps}\n"
            f"## Timings (s): {json.dumps({k: round(v,2) for k,v in timings.items()}, ensure_ascii=False)}\n"
            f"## Total wall: {round(total_wall,2)}s | user-wait: {round(user_wait['total'],2)}s | productive: {round(productive,2)}s\n\n"
            f"## Evidence\n"
            f"- `credible_1_workbench.html`\n"
            f"- `credible_2_research_detail.html`\n"
            f"- `credible_3_hypothesis.html`\n"
            f"- `credible_4_research.html`\n"
            f"- `credible_5_pool.html`\n"
            f"- `credible_6_signals.html`\n"
            f"- `credible_7_signal_detail.html`\n"
            f"- `credible_success.json`\n"
            f"- `credible_backend_stdout.log`\n",
            encoding="utf-8",
        )
        
        print(f"\n✅ Harness reached user action boundary at step 7")
        print(f"   Completed: 1-7 | Signal: {signal_id} | LLM calls: {llm_calls}")
        print(f"   Productive time: {round(productive,2)}s | Evidence: {DOCS}")

    except Exception as e:
        if not failure:
            failure = str(e)
        print(f"\n[FAIL] {failure}")
        trace = {
            "run_id": RUN_ID,
            "failure": failure,
            "network_requests": len(net_log),
            "console_messages": len(console_log),
            "page_errors": len(page_errors),
            "timings": {k: round(v, 2) for k, v in timings.items()},
            "backend_tail": "".join(backend_lines[-40:]),
        }
        (DOCS / "credible_failure.json").write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
        (DOCS / "credible_network.json").write_text(json.dumps(net_log, indent=2), encoding="utf-8")
        (DOCS / "credible_console.json").write_text(json.dumps(console_log, indent=2, ensure_ascii=False), encoding="utf-8")
        (DOCS / "credible_page_errors.json").write_text(json.dumps(page_errors, indent=2, ensure_ascii=False), encoding="utf-8")
        (DOCS / "credible_backend_stdout.log").write_text("".join(backend_lines), encoding="utf-8")
        (DOCS / "CREDIBLE_PRODUCT_ACCEPTANCE.md").write_text(
            f"# Credible Product Acceptance — Task 0 (extended)\n\n"
            f"**Run ID:** `{RUN_ID}`\n"
            f"**Status:** ❌ FAILED\n\n"
            f"**First failure:** {failure}\n\n"
            f"**Evidence:**\n"
            f"- `credible_failure.json`\n"
            f"- `credible_backend_stdout.log`\n"
            f"- `credible_network.json`\n",
            encoding="utf-8",
        )
        sys.exit(1)
    finally:
        backend_reader_stop.set()
        try:
            reader.join(timeout=3)
        except Exception:
            pass
        if browser is not None:
            browser.close()
        if pw is not None:
            pw.stop()
        if frontend is not None:
            stop_process(frontend, "Frontend")
        if backend is not None:
            stop_process(backend, "Backend")


if __name__ == "__main__":
    main()
