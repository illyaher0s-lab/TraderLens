"""B4 Task 11: Compatibility and boundary tests.

Protects B4 boundaries by checking production code files for forbidden imports/keywords:
- No LLM (OpenAI, Anthropic, LangChain)
- No research/strategy DB direct access
- No Gate/promotion/prototype_passed
- No formal report / Signal Board
- No modification of B3 frozen objects
"""
import ast
import hashlib
import tempfile
import unittest
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


def _file_fingerprint(path: Path) -> tuple[int, int, str]:
    data = path.read_bytes()
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, hashlib.sha256(data).hexdigest()


def _tree_fingerprint(root: Path) -> dict[str, tuple[int, int, str]]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): _file_fingerprint(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class TestB4ProtectedFilesUnchangedByTempRunner(unittest.TestCase):
    """The real B4 temp writer must preserve protected repository inputs."""

    def test_b4_temp_runner_preserves_inputs_and_writes_only_temp(self):
        project_root = Path(__file__).parent.parent.resolve()
        protected = {
            project_root / relative_path: _file_fingerprint(project_root / relative_path)
            for relative_path in FORBIDDEN_FILES[2:6]
        }
        source_dirs = (
            project_root / "data/pit/v3_b4_is_results",
            project_root / "data/pit/v3_execution_semantics_supplements",
        )
        source_before = {path: _tree_fingerprint(path) for path in source_dirs}

        from scripts.publish_v3_execution_semantics import publish_v3_execution_semantics
        from scripts.run_v3_b4_is_once import run_v3_b4_is_once
        from tests.test_run_v3_b4_is_once import _fixture_data

        with tempfile.TemporaryDirectory() as raw_tmp:
            temp_root = Path(raw_tmp)
            supplement = publish_v3_execution_semantics(
                output_root=temp_root / "supplements"
            )
            result = run_v3_b4_is_once(
                repo_root=project_root,
                output_root=temp_root / "b4-results",
                audit_path=temp_root / "audit.json",
                data_source=_fixture_data(),
                supplement_dir=Path(supplement["path"]),
            )

            artifact_path = Path(result["path"]).resolve()
            self.assertTrue(artifact_path.is_relative_to(temp_root / "b4-results"))
            self.assertEqual(result["status"], "published")
            self.assertEqual(result["read_audit"]["oos_read_count"], 0)
            self.assertEqual(
                {
                    path.relative_to(artifact_path).as_posix()
                    for path in artifact_path.rglob("*")
                    if path.is_file()
                },
                {
                    "manifest.json",
                    "manifest.json.sha256",
                    "event_result.json",
                    "event_result.json.sha256",
                },
            )
            self.assertTrue((temp_root / "audit.json").is_file())
            self.assertTrue(
                all(
                    path.is_relative_to(temp_root)
                    for path in (artifact_path, Path(supplement["path"]).resolve(), temp_root / "audit.json")
                )
            )

        self.assertEqual(
            protected,
            {
                path: _file_fingerprint(path)
                for path in protected
            },
        )
        self.assertEqual(
            source_before,
            {path: _tree_fingerprint(path) for path in source_dirs},
        )

    def test_compatibility_module_has_no_process_invocation(self):
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        imported_modules = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertNotIn("subprocess", imported_modules)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "subprocess")
            if isinstance(node, ast.Call):
                self.assertFalse(
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "subprocess"
                )


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
