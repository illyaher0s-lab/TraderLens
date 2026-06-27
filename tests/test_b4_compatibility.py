"""B4 Task 11: Compatibility and boundary tests.

Protects B4 boundaries by checking production code files for forbidden imports/keywords:
- No LLM (OpenAI, Anthropic, LangChain)
- No research/strategy DB direct access
- No Gate/promotion/prototype_passed
- No formal report / Signal Board
- No modification of B3 frozen objects
"""
import unittest
import subprocess
from pathlib import Path


# B4 production files to scan (Task 1-10 deliverables)
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
]

# Optional B4 files (future tasks, not scanned)
B4_OPTIONAL_FILES = [
    # Note: strategy_core/backtest_engine.py is legacy, not B4
    # Note: strategy_core/signals.py, orders.py may not exist yet
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


def get_b4_file_contents():
    """Read all B4 production files."""
    project_root = Path(__file__).parent.parent
    contents = {}
    
    for file_path in B4_PRODUCTION_FILES:
        full_path = project_root / file_path
        if full_path.exists():
            contents[file_path] = full_path.read_text(encoding='utf-8')
    
    for file_path in B4_OPTIONAL_FILES:
        full_path = project_root / file_path
        if full_path.exists():
            contents[file_path] = full_path.read_text(encoding='utf-8')
    
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


if __name__ == "__main__":
    unittest.main()
