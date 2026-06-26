"""B3 Compatibility Tests - Protect B3 boundaries and verify isolation."""
import unittest
import inspect


class TestB3Compatibility(unittest.TestCase):
    def test_b3_does_not_import_research_db(self):
        """B3 must not import ResearchDB."""
        # Check all B3 services
        b3_services = [
            "backend.services.point_in_time_universe",
            "backend.services.financial_visibility",
            "backend.services.data_snapshot_manifest",
            "backend.services.oos_window_rules",
            "backend.services.time_consistency_guard",
            "backend.services.research_protocol_freezer",
        ]
        
        for module_name in b3_services:
            module = __import__(module_name, fromlist=[""])
            source = inspect.getsource(module)
            
            # Check no ResearchDB import
            self.assertNotIn("from backend.db.research import", source.lower())
            self.assertNotIn("import backend.db.research", source.lower())
            self.assertNotIn("researchdb", source.lower())

    def test_b3_does_not_call_llm(self):
        """B3 must not call LLM."""
        b3_services = [
            "backend.services.point_in_time_universe",
            "backend.services.financial_visibility",
            "backend.services.data_snapshot_manifest",
            "backend.services.oos_window_rules",
            "backend.services.time_consistency_guard",
            "backend.services.research_protocol_freezer",
        ]
        
        for module_name in b3_services:
            module = __import__(module_name, fromlist=[""])
            source = inspect.getsource(module)
            lines = [line for line in source.split('\n') if not line.strip().startswith('"') and not line.strip().startswith('#')]
            code_only = '\n'.join(lines).lower()
            
            # Check no LLM imports or calls
            self.assertNotIn("import llm", code_only)
            self.assertNotIn("from llm", code_only)
            self.assertNotIn("openai", code_only)
            self.assertNotIn("anthropic", code_only)

    def test_b3_does_not_call_backtest_execution(self):
        """B3 must not call strategy_core backtest execution."""
        b3_services = [
            "backend.services.point_in_time_universe",
            "backend.services.financial_visibility",
            "backend.services.data_snapshot_manifest",
            "backend.services.oos_window_rules",
            "backend.services.time_consistency_guard",
            "backend.services.research_protocol_freezer",
        ]
        
        for module_name in b3_services:
            module = __import__(module_name, fromlist=[""])
            source = inspect.getsource(module)
            
            # Check no backtest execution imports
            self.assertNotIn("from strategy_core", source.lower())
            self.assertNotIn("import strategy_core", source.lower())
            self.assertNotIn("backtest_runner", source.lower())
            self.assertNotIn("signal_generator", source.lower())

    def test_b3_does_not_create_gate_report_promotion(self):
        """B3 must not create Gate/report/promotion."""
        b3_services = [
            "backend.services.point_in_time_universe",
            "backend.services.financial_visibility",
            "backend.services.data_snapshot_manifest",
            "backend.services.oos_window_rules",
            "backend.services.time_consistency_guard",
            "backend.services.research_protocol_freezer",
        ]
        
        for module_name in b3_services:
            module = __import__(module_name, fromlist=[""])
            source = inspect.getsource(module)
            
            # Check no Gate/report/promotion references
            self.assertNotIn("PrototypeGateResult", source)
            self.assertNotIn("ImmutableBacktestReport", source)
            self.assertNotIn("StrategyPromotionRecord", source)
            self.assertNotIn("prototype_passed", source.lower())

    def test_b3_does_not_add_status_update_method(self):
        """B3 must not add status update methods."""
        # Check ResearchProtocolFreezer has no status update
        from backend.services import research_protocol_freezer
        
        freezer_source = inspect.getsource(research_protocol_freezer)
        
        # Must not have update/modify/promote methods
        self.assertNotIn("def update_", freezer_source.lower())
        self.assertNotIn("def modify_", freezer_source.lower())
        self.assertNotIn("def promote_", freezer_source.lower())
        self.assertNotIn("def set_status", freezer_source.lower())

    def test_b3_rejects_forward_watchlist_for_formal_history(self):
        """B3 must reject ForwardWatchlistSnapshot for formal historical validation."""
        from backend.services.point_in_time_universe import PointInTimeUniverseBuilder
        from contracts.strategy import ForwardWatchlistSnapshot
        from datetime import date
        
        builder = PointInTimeUniverseBuilder()
        
        watchlist = ForwardWatchlistSnapshot(
            watchlist_snapshot_id="watch_001",
            theme_id="theme_001",
            confirmed_candidate_ids=("cand_001",),
            symbols=("000001.SZ",),
            snapshot_date=date(2024, 1, 1),
            created_at=date(2024, 1, 1),
        )
        
        # Must reject
        is_valid, error = builder.validate_universe_input(watchlist)
        self.assertFalse(is_valid)
        self.assertIn("ForwardWatchlist", error)

    def test_b3_rejects_static_symbols_for_formal_history(self):
        """B3 must reject static symbol list for formal historical validation."""
        from backend.services.point_in_time_universe import PointInTimeUniverseBuilder
        
        builder = PointInTimeUniverseBuilder()
        
        # Plain list
        static_list = ["000001.SZ", "000002.SZ"]
        
        # Must reject
        is_valid, error = builder.validate_universe_input(static_list)
        self.assertFalse(is_valid)
        self.assertIn("symbol list", error.lower())

    def test_b3_forbidden_files_unchanged(self):
        """B3 implementation must not modify forbidden files."""
        import subprocess
        
        # Get all modified files in recent commits
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~10..HEAD"],
            cwd="D:/Codex/TraderLens",
            capture_output=True,
            text=True,
        )
        
        modified_files = set(result.stdout.strip().split('\n')) if result.stdout.strip() else set()
        
        # Check forbidden files not in modified list
        forbidden_files = [
            "contracts/stable.py",
            "contracts/draft.py",
            "contracts/research.py",
            "backend/db/research.py",
            "strategy_core/prototype_gate.py",
        ]
        
        for filepath in forbidden_files:
            self.assertNotIn(filepath, modified_files, 
                           f"Forbidden file {filepath} was modified in recent commits")


if __name__ == "__main__":
    unittest.main()
