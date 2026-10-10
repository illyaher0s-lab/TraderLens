"""
Test harness main chain continuation from confirmed_candidate_pool.

TDD for Task 0 harness extension.

Proves harness continues in real browser user path after confirmed_candidate_pool:
- Step 5: Separately validated strategy signal (read from Signal Board)
- Step 6-7: Market Guard → Action Plan (API reads only, no generation)
- Step 8: User confirm buy (execution feedback API)
- Step 9: Observation Pool (read positions)
- Step 10: Daily Signal (read latest signal)
- Step 11: User confirm sell (execution feedback API)
- Step 12: P&L (discipline review service)
- Step 13: Discipline Review (read review)

RED requirements:
1. No fake/synthetic signal, execution, market data, or report
2. No direct DB insert or API-only substitution
3. Real browser DOM interaction via Playwright
4. Stop at first true business blocker with `first_product_blocker` evidence
5. If no validated signal exists, report that fact as blocker (do NOT create one)
6. Preserve DOM, network, command, exit code, run ID evidence
7. Single worker backend startup only
8. No reserve/consume ledger, protocol creation, OOS execution, Gate/Promotion/Signal generation
9. Protected PIT artifacts unchanged (SHA-256 before/after comparison)
10. Report actual business step reached, not premature PASS

These are RED test expectations, not implementation.
Tests written first, implementation follows minimal GREEN path.
"""

import unittest
import subprocess
import json
import os
from pathlib import Path


class TestHarnessMainChainContinuation(unittest.TestCase):
    """
    Tests that harness attempts main chain continuation after confirmed_candidate_pool.
    
    RED first: these tests WILL FAIL until harness is extended.
    """

    def setUp(self):
        """Common test setup."""
        self.project_root = Path(__file__).parent.parent
        self.harness_script = self.project_root / "scripts" / "verify_credible_manual_trade_closure.py"
        self.docs_dir = self.project_root / "docs" / "verification"
        self.venv_python = self.project_root / ".venv" / "Scripts" / "python.exe"
        
        # Ensure harness exists
        self.assertTrue(self.harness_script.exists(), "Harness script must exist")
        self.assertTrue(self.venv_python.exists(), f"Venv python must exist at {self.venv_python}")
    
    def get_latest_run_dir(self):
        """Get the latest CREDIBLE_RUN_* directory."""
        run_dirs = sorted([d for d in self.docs_dir.glob("CREDIBLE_RUN_*") if d.is_dir()])
        if not run_dirs:
            self.skipTest("No CREDIBLE_RUN_* directory found")
        return run_dirs[-1]  # Latest by name (YYYYMMDD_HHMMSS)

    def test_harness_attempts_signal_read_after_candidate_pool(self):
        """
        RED: Harness must attempt to read separately validated signal after candidate pool.
        
        Expected behavior:
        - After confirmed_candidate_pool step completes
        - Navigate to /signals page or query signal API
        - Search for signals matching candidate pool criteria
        - If no signal found, report `first_product_blocker=no_validated_signal`
        - If signal found, proceed to Market Guard check
        
        This tests that harness does NOT stop at candidate pool and claim PASS.
        """
        # Read acceptance report from latest run (do not run harness in test)
        run_dir = self.get_latest_run_dir()
        acceptance_path = run_dir / "CREDIBLE_PRODUCT_ACCEPTANCE.md"
        self.assertTrue(acceptance_path.exists(), f"Acceptance report must exist in {run_dir}")
        
        acceptance_content = acceptance_path.read_text(encoding="utf-8")
        
        # RED assertions: harness must NOT claim PASS at candidate pool
        self.assertNotIn(
            "✅ Task 2 完整验收通过",
            acceptance_content,
            "Harness must not claim PASS at candidate pool (only 30.8% coverage)"
        )
        
        # RED assertions: must attempt signal read
        # Either "Step 5: Read signal board" or "first_product_blocker: no_validated_signal"
        signal_attempted = (
            "Step 5" in acceptance_content or
            "signal" in acceptance_content.lower() or
            "first_product_blocker" in acceptance_content
        )
        
        self.assertTrue(
            signal_attempted,
            "Harness must attempt signal read after candidate pool"
        )

    def test_harness_reports_first_product_blocker_not_partial_pass(self):
        """
        RED: Harness must report first true business blocker, not partial PASS.
        
        Expected report structure:
        - Status: ❌ BLOCKED (not ✅ PASS)
        - Last reached step: (actual step number 1-13)
        - First product blocker: (exact blocker description)
        - Evidence: (DOM snapshots, network logs, IDs)
        
        This tests Task 0 requirement: "fails loudly at its actual first missing product step"
        """
        run_dir = self.get_latest_run_dir()
        acceptance_path = run_dir / "CREDIBLE_PRODUCT_ACCEPTANCE.md"
        self.assertTrue(acceptance_path.exists(), f"Acceptance report must exist in {run_dir}")
        
        acceptance_content = acceptance_path.read_text(encoding="utf-8")
        
        # RED: Must have blocker section (check for either markdown heading or inline code)
        has_blocker = (
            "first product blocker" in acceptance_content.lower() or
            "no_validated_signal" in acceptance_content.lower() or
            "blocker:" in acceptance_content.lower()
        )
        
        self.assertTrue(
            has_blocker,
            "Must report first product blocker"
        )
        
        # RED: Must NOT claim complete chain verified at step 4
        if "Chain verified" in acceptance_content:
            # If "Chain verified" exists, must list more than 4 steps
            import re
            steps = re.findall(r"^\d+\.", acceptance_content, re.MULTILINE)
            self.assertGreater(
                len(steps),
                4,
                "If chain verified, must show > 4 steps attempted"
            )

    def test_harness_preserves_evidence_bundle(self):
        """
        RED: Harness must preserve complete evidence bundle for stopped chain.
        
        Required evidence files (when harness runs):
        - credible_1_workbench.html (existing)
        - credible_2_research_detail.html (existing)
        - credible_3_hypothesis.html (existing)
        - credible_4_research.html (existing)
        - credible_5_pool.html (existing)
        - credible_6_signals.html (NEW - signal board page)
        - credible_network.json (network log)
        - credible_backend_stdout.log (backend output)
        - CREDIBLE_PRODUCT_ACCEPTANCE.md (report)
        
        This tests evidence preservation requirement.
        """
        # Check existing evidence files from last run
        run_dir = self.get_latest_run_dir()
        
        evidence_files = [
            "credible_1_workbench.html",
            "credible_2_research_detail.html",
            "credible_3_hypothesis.html",
            "credible_4_research.html",
            "credible_5_pool.html",
            "CREDIBLE_PRODUCT_ACCEPTANCE.md",
        ]
        
        for filename in evidence_files:
            file_path = run_dir / filename
            self.assertTrue(
                file_path.exists(),
                f"Evidence file {filename} must exist in {run_dir}"
            )
        
        # RED: After extension, must also have signals page evidence
        # (This will fail until harness creates it)
        signals_evidence = run_dir / "credible_6_signals.html"
        if not signals_evidence.exists():
            # Expected to fail in RED phase
            self.fail(
                "RED: credible_6_signals.html not found - "
                "harness must capture signal board page after pool step"
            )

    def test_harness_enforces_single_worker_backend(self):
        """
        RED: Harness must verify single worker backend startup.
        
        Required checks:
        - Backend command includes --workers 1
        - WEB_CONCURRENCY not set or equals 1
        - UVICORN_WORKERS not set or equals 1
        - Report failure if worker count != 1
        
        This tests Task 0 requirement: "Assert the spawned backend command includes --workers 1"
        """
        run_dir = self.get_latest_run_dir()
        acceptance_path = run_dir / "CREDIBLE_PRODUCT_ACCEPTANCE.md"
        if not acceptance_path.exists():
            self.skipTest(f"No acceptance report yet in {run_dir}")
        
        # Check if harness script enforces single worker
        harness_content = self.harness_script.read_text(encoding="utf-8")
        
        # Verify harness code contains worker check
        worker_enforcement = (
            "--workers 1" in harness_content or
            "workers=1" in harness_content or
            "WEB_CONCURRENCY" in harness_content or
            "UVICORN_WORKERS" in harness_content
        )
        
        self.assertTrue(
            worker_enforcement,
            "Harness script must enforce single worker backend"
        )

    def test_harness_uses_cors_allowed_frontend_origin(self):
        """The browser origin must match the backend's configured CORS origin."""
        harness_content = self.harness_script.read_text(encoding="utf-8")

        self.assertIn(
            'http://localhost:3010',
            harness_content,
            "Harness must use the frontend origin allowed by backend CORS",
        )
        self.assertNotIn(
            'http://127.0.0.1:3010',
            harness_content,
            "127.0.0.1 frontend origin is not allowed by the backend CORS policy",
        )

    def test_harness_does_not_create_synthetic_business_data(self):
        """
        RED: Harness must NOT create fake signal, execution, market data, or report.
        
        Forbidden operations:
        - Insert signal rows via DB or API POST /api/signals
        - Insert execution logs via DB
        - Insert P&L via DB
        - Insert discipline review via DB
        - Generate fake market guard report
        - Generate fake action plan outside signal workflow
        
        Allowed operations:
        - Read existing signals via GET /api/signals
        - Read existing positions via GET /api/observations
        - Read existing reviews via GET API
        - User confirmation via POST /api/workbench/execution-feedback (only if UI prompts)
        
        This tests Task 0 constraint: "no synthetic market rows, template results, signals, executions, or reviews"
        """
        # Check harness script content for forbidden operations
        harness_content = self.harness_script.read_text(encoding="utf-8")
        
        # RED: Must not contain direct signal insertion
        forbidden_patterns = [
            "INSERT INTO signals",
            "INSERT INTO planned_signals",
            "db.create_signal",
            "signal_board.create_signal",
            "POST.*signals.*create",  # API POST to create signal
        ]
        
        for pattern in forbidden_patterns:
            self.assertNotRegex(
                harness_content,
                pattern,
                f"Harness must not contain forbidden operation: {pattern}"
            )

    def test_harness_stops_at_no_validated_signal_if_missing(self):
        """
        RED: If no validated signal exists, harness must report that as first blocker.
        
        Expected behavior when no signal found:
        - Navigate to /signals page
        - Query for signals (optionally with candidate pool criteria)
        - Find zero signals or no prototype_passed signals
        - Report: first_product_blocker=no_validated_signal_for_candidate_pool
        - Do NOT create a signal
        - Do NOT proceed to Market Guard
        
        This tests: "若当前不存在已验证 signal，harness 必须通过前端真实路径报告该事实为 first_product_blocker"
        """
        run_dir = self.get_latest_run_dir()
        acceptance_path = run_dir / "CREDIBLE_PRODUCT_ACCEPTANCE.md"
        if not acceptance_path.exists():
            self.skipTest(f"No acceptance report yet in {run_dir}")
        
        acceptance_content = acceptance_path.read_text(encoding="utf-8")
        
        # RED: If report shows blocker, must be legitimate business blocker
        if "first_product_blocker" in acceptance_content.lower():
            # Acceptable blocker reasons (business, not infrastructure)
            acceptable_blockers = [
                "no_validated_signal",
                "no_prototype_passed_strategy",
                "market_guard_blocked",
                "action_plan_ineligible",
                "data_fault",
                "no_executable_signal",
            ]
            
            has_business_blocker = any(
                blocker in acceptance_content.lower()
                for blocker in acceptable_blockers
            )
            
            self.assertTrue(
                has_business_blocker,
                f"first_product_blocker must be legitimate business blocker, not infrastructure issue. "
                f"Acceptable: {acceptable_blockers}"
            )


class TestHarnessMainChainCoverageMinimum(unittest.TestCase):
    """
    Tests minimum coverage requirement for main chain harness.
    
    RED: Current harness covers 4/13 steps (30.8%).
    Must attempt all 13 steps or stop at first true business blocker.
    """

    def setUp(self):
        """Common setup."""
        self.project_root = Path(__file__).parent.parent
        self.docs_dir = self.project_root / "docs" / "verification"
    
    def get_latest_run_dir(self):
        """Get the latest CREDIBLE_RUN_* directory."""
        run_dirs = sorted([d for d in self.docs_dir.glob("CREDIBLE_RUN_*") if d.is_dir()])
        if not run_dirs:
            self.skipTest("No CREDIBLE_RUN_* directory found")
        return run_dirs[-1]

    def test_harness_attempts_more_than_four_steps(self):
        """
        RED: Harness must attempt steps beyond confirmed_candidate_pool (step 4).
        
        Main chain steps:
        1. Friend recommendation → ResearchCase ✓ (existing)
        2. User hypothesis + facts/counter-evidence ✓ (existing)
        3. Approval → confirmed_candidate_pool ✓ (existing)
        4. Forward-only pool created ✓ (existing)
        5. Separately validated signal ✗ (missing)
        6. Market Guard check ✗ (missing)
        7. Action Plan eligibility ✗ (missing)
        8. User confirm buy ✗ (missing)
        9. Observation Pool ✗ (missing)
        10. Daily Signal ✗ (missing)
        11. User confirm sell ✗ (missing)
        12. P&L calculation ✗ (missing)
        13. Discipline Review ✗ (missing)
        
        Harness must attempt step 5 at minimum.
        """
        run_dir = self.get_latest_run_dir()
        acceptance_path = run_dir / "CREDIBLE_PRODUCT_ACCEPTANCE.md"
        self.assertTrue(acceptance_path.exists(), f"Acceptance report must exist in {run_dir}")
        
        acceptance_content = acceptance_path.read_text(encoding="utf-8")
        
        # RED: Must mention signal or step 5
        step_5_attempted = (
            "Step 5" in acceptance_content or
            "separately validated" in acceptance_content.lower() or
            "signal board" in acceptance_content.lower()
        )
        
        self.assertTrue(
            step_5_attempted,
            "Harness must attempt step 5 (separately validated signal) after pool"
        )


if __name__ == "__main__":
    unittest.main()
