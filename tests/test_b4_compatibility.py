"""B4 Task 11: Compatibility and boundary tests.

Protects B4 boundaries by checking production code files for forbidden imports/keywords:
- No LLM (OpenAI, Anthropic, LangChain)
- No research/strategy DB direct access
- No Gate/promotion/prototype_passed
- No formal report / Signal Board
- No modification of B3 frozen objects
"""
import ast
import unittest
import subprocess
from pathlib import Path


# B4 production files to scan (Task 1-11 deliverables)
B4_PRODUCTION_FILES = [
    "backend/services/backtest_engine_qualification.py",
    "backend/services/backtest_time_cursor.py",
    "backend/services/future_data_guard.py",
    "backend/services/canary_strategies.py",
    "backend/services/b4_protocol_types.py",
    "strategy_core/fill_simulator.py",
    "strategy_core/portfolio.py",
    "strategy_core/cursor_bound_data_view.py",
    "strategy_core/trading_calendar.py",
    "strategy_core/signals.py",
    "strategy_core/orders.py",
    "strategy_core/transaction_costs.py",
    "strategy_core/position_sizer.py",
]

# Files with mixed legacy + B4 code requiring selective scanning
B4_MIXED_LEGACY_FILES = [
    "strategy_core/backtest_engine.py",  # Has legacy run_backtest (Gate) + B4 run_event_backtest
]

# Forbidden files that must not be modified by B4
FORBIDDEN_FILES = [
    "contracts/stable.py",
    "contracts/draft.py",
    "contracts/research.py",
    "contracts/strategy.py",
    "backend/db/research.py",
    "backend/db/strategy.py",
    "strategy_core/prototype_gate.py",
    "backend/services/canary_strategies.py",
]


def extract_function_by_ast(source_code: str, function_name: str) -> str:
    """
    Extract exact function definition using AST.

    Args:
        source_code: Full source code
        function_name: Function name to extract

    Returns:
        Extracted function source code

    Raises:
        AssertionError: If function not found
    """
    tree = ast.parse(source_code)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            # Extract exact source segment for this function
            func_source = ast.get_source_segment(source_code, node)
            if func_source is None:
                raise AssertionError(
                    f"Function '{function_name}' found but ast.get_source_segment failed"
                )
            return func_source

    raise AssertionError(
        f"Function '{function_name}' not found in source (boundary extraction failed)"
    )


def get_b4_file_contents():
    """Read all B4 production files."""
    project_root = Path(__file__).parent.parent
    contents = {}

    for file_path in B4_PRODUCTION_FILES:
        full_path = project_root / file_path
        if full_path.exists():
            contents[file_path] = full_path.read_text(encoding='utf-8')

    # Mixed legacy files: extract only B4 sections using AST
    for file_path in B4_MIXED_LEGACY_FILES:
        full_path = project_root / file_path
        if full_path.exists():
            full_content = full_path.read_text(encoding='utf-8')

            # For backtest_engine.py: extract run_event_backtest function only
            if "backtest_engine.py" in file_path:
                # Use AST to extract exact function definition (fail loud if missing)
                b4_content = extract_function_by_ast(full_content, "run_event_backtest")
                contents[file_path] = b4_content
            else:
                # Other mixed files: include full content for now
                contents[file_path] = full_content

    return contents


class TestB4DoesNotCallLLM(unittest.TestCase):
    """B4 must not call LLM APIs."""
    
    def test_b4_does_not_call_llm(self):
        """B4 production files must not import OpenAI/Anthropic/LangChain."""
        contents = get_b4_file_contents()
        self.assertGreater(len(contents), 0, "No B4 files found")

        forbidden_llm_keywords = [
            "openai",
            "anthropic",
            "langchain",
            "from openai",
            "import openai",
            "from anthropic",
            "import anthropic",
            "from langchain",
            "import langchain",
            "OpenAI(",
            "Anthropic(",
            "ChatOpenAI",
            "ChatAnthropic",
        ]

        violations = []
        for file_path, content in contents.items():
            # Skip test file itself
            if "test_b4_compatibility.py" in file_path:
                continue

            content_lower = content.lower()
            for keyword in forbidden_llm_keywords:
                if keyword.lower() in content_lower:
                    violations.append(f"{file_path} contains forbidden LLM keyword: {keyword}")

        if violations:
            self.fail("B4 must not call LLM:\n" + "\n".join(violations))


class TestB4DoesNotImportResearchDB(unittest.TestCase):
    """B4 must not import research/strategy DB directly."""
    
    def test_b4_does_not_import_research_db(self):
        """B4 must not import backend.db.research or backend.db.strategy."""
        contents = get_b4_file_contents()
        
        forbidden_db_imports = [
            "from backend.db.research",
            "import backend.db.research",
            "from backend.db.strategy",
            "import backend.db.strategy",
            "ResearchDB",
            "StrategyDB",
        ]
        
        violations = []
        for file_path, content in contents.items():
            for keyword in forbidden_db_imports:
                if keyword in content:
                    violations.append(f"{file_path} contains forbidden DB import: {keyword}")
        
        if violations:
            self.fail("B4 must not import research/strategy DB:\n" + "\n".join(violations))


class TestB4DoesNotCreateGateResult(unittest.TestCase):
    """B4 must not create Gate result."""
    
    def test_b4_does_not_create_gate_result(self):
        """B4 must not create PrototypeGateResult."""
        contents = get_b4_file_contents()
        
        forbidden_gate_keywords = [
            "PrototypeGateResult",
            "prototype_gate_result",
            "GateVerdict",
            "gate_verdict",
        ]
        
        violations = []
        for file_path, content in contents.items():
            for keyword in forbidden_gate_keywords:
                if keyword in content:
                    violations.append(f"{file_path} contains forbidden Gate keyword: {keyword}")
        
        if violations:
            self.fail("B4 must not create Gate result:\n" + "\n".join(violations))


class TestB4DoesNotCreatePromotionRecord(unittest.TestCase):
    """B4 must not create promotion record."""
    
    def test_b4_does_not_create_promotion_record(self):
        """B4 must not create StrategyPromotionRecord."""
        contents = get_b4_file_contents()
        
        forbidden_promotion_keywords = [
            "StrategyPromotionRecord",
            "StrategyPromotionReducer",
            "promote_to_prototype_passed",
            "promotion_record",
        ]
        
        violations = []
        for file_path, content in contents.items():
            for keyword in forbidden_promotion_keywords:
                if keyword in content:
                    violations.append(f"{file_path} contains forbidden promotion keyword: {keyword}")
        
        if violations:
            self.fail("B4 must not create promotion record:\n" + "\n".join(violations))


class TestB4DoesNotWritePrototypePassed(unittest.TestCase):
    """B4 must not write prototype_passed."""
    
    def test_b4_does_not_write_prototype_passed(self):
        """B4 must not write prototype_passed state."""
        contents = get_b4_file_contents()
        
        forbidden_keywords = [
            "prototype_passed",
            "candidate_for_prototype_passed",
            "PrototypePassed",
        ]
        
        violations = []
        for file_path, content in contents.items():
            for keyword in forbidden_keywords:
                if keyword in content:
                    violations.append(f"{file_path} contains forbidden prototype_passed: {keyword}")
        
        if violations:
            self.fail("B4 must not write prototype_passed:\n" + "\n".join(violations))


class TestB4DoesNotModifyStrategyDraft(unittest.TestCase):
    """B4 must not modify strategy draft."""
    
    def test_b4_does_not_modify_strategy_draft(self):
        """B4 must not import or modify StrategyDraft."""
        contents = get_b4_file_contents()
        
        forbidden_keywords = [
            "from contracts.draft",
            "import contracts.draft",
            "StrategyDraft",
        ]
        
        violations = []
        for file_path, content in contents.items():
            for keyword in forbidden_keywords:
                if keyword in content:
                    violations.append(f"{file_path} contains forbidden draft import: {keyword}")
        
        if violations:
            self.fail("B4 must not modify strategy draft:\n" + "\n".join(violations))


class TestB4DoesNotModifyResearchProtocolSnapshot(unittest.TestCase):
    """B4 must not modify ResearchProtocolSnapshot (read-only)."""
    
    def test_b4_does_not_modify_research_protocol_snapshot(self):
        """B4 may read but not modify ResearchProtocolSnapshot."""
        contents = get_b4_file_contents()
        
        # B4 can import ResearchProtocolSnapshot (Task 10 allows reading)
        # But cannot mutate it
        forbidden_mutation_patterns = [
            ".protocol_snapshot_id =",
            ".data_snapshot_hash =",
            ".frozen_at =",
            "protocol.update(",
            "protocol_snapshot.update(",
        ]
        
        violations = []
        for file_path, content in contents.items():
            for pattern in forbidden_mutation_patterns:
                if pattern in content:
                    violations.append(f"{file_path} contains forbidden protocol mutation: {pattern}")
        
        if violations:
            self.fail("B4 must not modify ResearchProtocolSnapshot:\n" + "\n".join(violations))


class TestB4DoesNotImportPrototypeGate(unittest.TestCase):
    """B4 must not import prototype_gate."""
    
    def test_b4_does_not_import_prototype_gate(self):
        """B4 must not import strategy_core.prototype_gate."""
        contents = get_b4_file_contents()
        
        forbidden_imports = [
            "from strategy_core.prototype_gate",
            "import strategy_core.prototype_gate",
            "from .prototype_gate",
            "import prototype_gate",
        ]
        
        violations = []
        for file_path, content in contents.items():
            for keyword in forbidden_imports:
                if keyword in content:
                    violations.append(f"{file_path} contains forbidden prototype_gate import: {keyword}")
        
        if violations:
            self.fail("B4 must not import prototype_gate:\n" + "\n".join(violations))


class TestB4ForbiddenFilesUnchangedByGitDiffHelper(unittest.TestCase):
    """Git diff helper: forbidden files not modified."""
    
    def test_b4_forbidden_files_unchanged_by_git_diff_helper(self):
        """Forbidden files must not appear in git diff."""
        project_root = Path(__file__).parent.parent
        
        try:
            # Check staged changes
            result_staged = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            # Check unstaged changes
            result_unstaged = subprocess.run(
                ["git", "diff", "--name-only"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            changed_files = set()
            if result_staged.returncode == 0:
                changed_files.update(result_staged.stdout.strip().split("\n"))
            if result_unstaged.returncode == 0:
                changed_files.update(result_unstaged.stdout.strip().split("\n"))
            
            # Filter out empty strings
            changed_files = {f for f in changed_files if f}
            
            # Check if any forbidden file is modified
            violations = []
            for forbidden_file in FORBIDDEN_FILES:
                if forbidden_file in changed_files:
                    violations.append(f"Forbidden file modified: {forbidden_file}")
            
            if violations:
                self.fail("Forbidden files modified:\n" + "\n".join(violations))
        
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Git not available or timeout - skip this test
            self.skipTest("Git not available")


class TestB4HasNoSignalBoardDependency(unittest.TestCase):
    """B4 must not depend on Signal Board or formal report."""

    def test_b4_has_no_signal_board_dependency(self):
        """B4 must not create formal report or depend on Signal Board."""
        contents = get_b4_file_contents()

        forbidden_keywords = [
            "ImmutableBacktestReport",
            "formal_report",
            "signal_board",
            "SignalBoard",
            "ActionPlan",
            "action_plan",
        ]

        violations = []
        for file_path, content in contents.items():
            for keyword in forbidden_keywords:
                if keyword in content:
                    violations.append(f"{file_path} contains forbidden Signal Board/report: {keyword}")

        if violations:
            self.fail("B4 must not depend on Signal Board/formal report:\n" + "\n".join(violations))


class TestASTExtractorRegression(unittest.TestCase):
    """Regression test for AST-based function extractor."""

    def test_extractor_excludes_legacy_before_and_after(self):
        """
        Prove AST extractor returns only target function, excluding legacy before/after.

        Synthetic source:
        - legacy_before() with prototype_gate keyword
        - run_event_backtest() without forbidden keywords
        - legacy_after() with prototype_gate keyword

        Extractor must return only run_event_backtest source.
        """
        synthetic_source = '''
def legacy_before():
    """Legacy function with Gate."""
    from strategy_core.prototype_gate import evaluate_prototype_gate
    result = evaluate_prototype_gate()
    return result

def run_event_backtest(protocol_snapshot_id: str, data_snapshot_hash: str):
    """B4 event-driven backtest."""
    if not protocol_snapshot_id:
        raise ValueError("protocol_snapshot_id required")
    if not data_snapshot_hash:
        raise ValueError("data_snapshot_hash required")
    return {"status": "ok"}

def legacy_after():
    """Another legacy function with Gate."""
    from strategy_core.prototype_gate import evaluate_prototype_gate
    gate_result = evaluate_prototype_gate()
    return gate_result
'''

        # Extract run_event_backtest using AST
        extracted = extract_function_by_ast(synthetic_source, "run_event_backtest")

        # Assertions: extracted must contain only run_event_backtest
        self.assertIn("def run_event_backtest", extracted)
        self.assertIn("protocol_snapshot_id required", extracted)
        self.assertIn("data_snapshot_hash required", extracted)

        # Must NOT contain legacy functions or prototype_gate
        self.assertNotIn("legacy_before", extracted)
        self.assertNotIn("legacy_after", extracted)
        self.assertNotIn("prototype_gate", extracted)
        self.assertNotIn("evaluate_prototype_gate", extracted)

        # Verify extraction is precise (no leading/trailing legacy code)
        lines = extracted.strip().split('\n')
        first_line = lines[0].strip()
        self.assertTrue(
            first_line.startswith("def run_event_backtest"),
            f"First line must be function definition, got: {first_line}"
        )


if __name__ == "__main__":
    unittest.main()
