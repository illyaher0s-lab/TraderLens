"""
Test startup configuration for Research API.

Tests that:
- Real mode requires both RESEARCH_LLM_API_KEY and TUSHARE_TOKEN
- Deterministic mode works without credentials
- Missing credentials fail loud with clear error
"""

import os
import unittest
from pathlib import Path
from backend.db.research import ResearchDB
from backend.api.research import create_research_app


class TestStartupConfiguration(unittest.TestCase):
    """Test Research API startup configuration."""

    def setUp(self):
        """Set up test database."""
        self.db = ResearchDB(":memory:")

    def test_deterministic_mode_works_without_credentials(self):
        """Deterministic mode does not require API keys."""
        # Should not raise even without credentials
        app = create_research_app(db=self.db, conversation_mode="deterministic")
        self.assertIsNotNone(app)

    def test_real_mode_with_credentials_works(self):
        """Real mode works when credentials are provided."""
        # Anthropic SDK requires HOME/USERPROFILE to resolve credential config
        # directory. Batch runners and headless CI may not have these set.
        # Use tempdir as fallback so the SDK can initialise without disk config.
        userprofile = os.environ.get("USERPROFILE")
        home = os.environ.get("HOME")
        if not userprofile and not home:
            import tempfile
            tmpdir = tempfile.mkdtemp(prefix="traderlens_home_")
            os.environ["USERPROFILE"] = tmpdir
        
        try:
            # Set fake credentials
            original_llm_key = os.environ.get("RESEARCH_LLM_API_KEY")
            original_tushare = os.environ.get("TUSHARE_TOKEN")
            os.environ["RESEARCH_LLM_API_KEY"] = "fake_key_for_test"
            os.environ["TUSHARE_TOKEN"] = "fake_token_for_test"
            
            try:
                # Should not raise (must specify serenity_execution_mode for real mode)
                app = create_research_app(
                    db=self.db,
                    conversation_mode="real",
                    serenity_execution_mode="two_phase"
                )
                self.assertIsNotNone(app)
            finally:
                # Restore original env vars
                if original_llm_key:
                    os.environ["RESEARCH_LLM_API_KEY"] = original_llm_key
                else:
                    os.environ.pop("RESEARCH_LLM_API_KEY", None)
                if original_tushare:
                    os.environ["TUSHARE_TOKEN"] = original_tushare
                else:
                    os.environ.pop("TUSHARE_TOKEN", None)
        finally:
            # Only pop USERPROFILE if we set it
            if not userprofile and not home:
                os.environ.pop("USERPROFILE", None)

    def test_real_mode_missing_llm_key_fails_loud(self):
        """Real mode without LLM key fails with clear error."""
        # Save and remove LLM key
        original_key = os.environ.get("RESEARCH_LLM_API_KEY")
        os.environ.pop("RESEARCH_LLM_API_KEY", None)
        
        # Ensure Tushare is set
        original_tushare = os.environ.get("TUSHARE_TOKEN")
        os.environ["TUSHARE_TOKEN"] = "fake_token"
        
        try:
            with self.assertRaises(ValueError) as ctx:
                app = create_research_app(
                    db=self.db,
                    conversation_mode="real",
                    serenity_execution_mode="two_phase"
                )
            
            # Check error message is clear
            self.assertIn("RESEARCH_LLM_API_KEY", str(ctx.exception))
            self.assertIn("Real mode requires", str(ctx.exception))
        
        finally:
            # Restore
            if original_key:
                os.environ["RESEARCH_LLM_API_KEY"] = original_key
            else:
                os.environ.pop("RESEARCH_LLM_API_KEY", None)
            
            if original_tushare:
                os.environ["TUSHARE_TOKEN"] = original_tushare
            else:
                os.environ.pop("TUSHARE_TOKEN", None)

    def test_real_mode_missing_tushare_token_fails_loud(self):
        """Real mode without Tushare token fails with clear error."""
        # Save and remove Tushare token
        original_tushare = os.environ.get("TUSHARE_TOKEN")
        os.environ.pop("TUSHARE_TOKEN", None)
        
        # Ensure LLM key is set
        original_llm_key = os.environ.get("RESEARCH_LLM_API_KEY")
        os.environ["RESEARCH_LLM_API_KEY"] = "fake_key"
        
        try:
            with self.assertRaises(ValueError) as ctx:
                app = create_research_app(
                    db=self.db,
                    conversation_mode="real",
                    serenity_execution_mode="two_phase"
                )
            
            # Check error message is clear
            self.assertIn("TUSHARE_TOKEN", str(ctx.exception))
            self.assertIn("Real mode requires", str(ctx.exception))
        
        finally:
            # Restore
            if original_tushare:
                os.environ["TUSHARE_TOKEN"] = original_tushare
            else:
                os.environ.pop("TUSHARE_TOKEN", None)
            
            if original_llm_key:
                os.environ["RESEARCH_LLM_API_KEY"] = original_llm_key
            else:
                os.environ.pop("RESEARCH_LLM_API_KEY", None)


if __name__ == "__main__":
    unittest.main()
