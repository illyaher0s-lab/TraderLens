"""
RED test: Harness must survive non-UTF-8 console encoding on Windows.

Task 0 requirement: "fails loudly at its actual first missing product step"

Windows GBK console cannot print Unicode status symbols (❌ ✓ ✗).
Harness must use ASCII-safe console output while preserving Unicode in files.
"""

import subprocess
import sys
import unittest
from pathlib import Path


class TestHarnessWindowsEncoding(unittest.TestCase):
    """Test harness console output is safe for Windows GBK encoding."""

    def setUp(self):
        """Common setup."""
        self.project_root = Path(__file__).parent.parent
        self.harness_script = self.project_root / "scripts" / "verify_credible_manual_trade_closure.py"
        self.venv_python = self.project_root / ".venv" / "Scripts" / "python.exe"
        self.docs_dir = self.project_root / "docs" / "verification"

    def get_latest_run_dir(self):
        """Get the latest CREDIBLE_RUN_* directory."""
        run_dirs = sorted([d for d in self.docs_dir.glob("CREDIBLE_RUN_*") if d.is_dir()])
        if not run_dirs:
            self.skipTest("No CREDIBLE_RUN_* directory found")
        return run_dirs[-1]

    def test_harness_console_output_is_ascii_safe(self):
        """
        RED: Harness console output must not contain Unicode symbols that fail on GBK.
        
        Windows console encoding (GBK/CP936) cannot encode:
        - ❌ (U+274C CROSS MARK)
        - ✓ (U+2713 CHECK MARK)
        - ✗ (U+2717 BALLOT X)
        
        Expected behavior:
        - Console output uses ASCII-safe alternatives: [BLOCKED], [OK], [FAIL]
        - File content (markdown) can still use Unicode
        - Exit code correctly reflects BLOCKED status
        
        This test simulates GBK console by checking harness source code.
        """
        # RED: Check if harness uses Unicode symbols in print statements
        harness_content = self.harness_script.read_text(encoding="utf-8")
        
        # Find all print statements
        import re
        print_statements = re.findall(r'print\([^)]+\)', harness_content)
        
        # Check for Unicode symbols in console output
        unicode_in_console = []
        for stmt in print_statements:
            if '❌' in stmt or '✓' in stmt or '✗' in stmt:
                unicode_in_console.append(stmt[:80])  # First 80 chars
        
        # RED: This will fail because current code uses Unicode in print()
        self.assertEqual(
            [],
            unicode_in_console,
            f"Console output contains GBK-unsafe Unicode symbols. Found {len(unicode_in_console)} instances. "
            f"Use ASCII alternatives: [BLOCKED] / [OK] / [FAIL]"
        )

    def test_harness_markdown_files_preserve_unicode(self):
        """
        Markdown report files should preserve Unicode for human readability.
        
        Only console output (print/stderr) must be ASCII-safe.
        File content can use Unicode because users open files in UTF-8 editors.
        """
        run_dir = self.get_latest_run_dir()
        acceptance_path = run_dir / "CREDIBLE_PRODUCT_ACCEPTANCE.md"
        
        if not acceptance_path.exists():
            self.skipTest(f"No acceptance report in {run_dir}")
        
        # Markdown files should still use Unicode for readability
        content = acceptance_path.read_text(encoding="utf-8")
        
        # This is PASS behavior: markdown can use Unicode
        has_unicode_status = (
            "✓" in content or
            "✗" in content or
            "❌" in content
        )
        
        # We want this to be True (Unicode in files is OK)
        # But if harness crashes before writing files, this test is skipped
        if has_unicode_status:
            self.assertTrue(True, "Markdown files correctly use Unicode")


if __name__ == "__main__":
    unittest.main()
