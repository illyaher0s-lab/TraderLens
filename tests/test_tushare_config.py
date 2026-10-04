"""
Test Tushare Configuration - M3.1 Scaffolding

Verify config loading, path resolution, and token handling.
"""

import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.tushare.config import TushareConfig


class TestTushareConfig(unittest.TestCase):
    """Test TushareConfig creation and path resolution."""
    
    def test_default_config_creation(self):
        """Can create config without token (fails only on API call)."""
        config = TushareConfig()
        
        # Should not raise on creation
        self.assertIsNone(config.token)
        self.assertEqual(config.api_url, "http://8.163.90.143:8686/")
        self.assertEqual(config.requests_per_minute, 60)
    
    def test_default_snapshot_root(self):
        """Default snapshot root resolves to data/tushare_snapshots."""
        config = TushareConfig()
        
        # Should resolve to project_root/data/tushare_snapshots
        snapshot_root = config._default_snapshot_root()
        # Windows uses backslashes
        self.assertTrue(str(snapshot_root).endswith("data\\tushare_snapshots") or 
                        str(snapshot_root).endswith("data/tushare_snapshots"))
        self.assertIsInstance(snapshot_root, Path)
    
    def test_metadata_and_data_dirs(self):
        """Metadata and data dirs resolve correctly."""
        config = TushareConfig()
        
        metadata_dir = config.metadata_dir
        data_dir = config.data_dir
        
        self.assertTrue(str(metadata_dir).endswith("metadata"))
        self.assertTrue(str(data_dir).endswith("data"))
        self.assertEqual(metadata_dir.parent, data_dir.parent)
    
    def test_custom_snapshot_root(self):
        """Can override snapshot root."""
        custom_root = Path("/tmp/custom_snapshots")
        config = TushareConfig(snapshot_root=custom_root)
        
        self.assertEqual(config.metadata_dir, custom_root / "metadata")
        self.assertEqual(config.data_dir, custom_root / "data")
    
    def test_ensure_token_fails_when_missing(self):
        """ensure_token raises ValueError when token not configured."""
        config = TushareConfig(token=None)
        
        with self.assertRaises(ValueError) as ctx:
            config.ensure_token()
        
        self.assertIn("Tushare token not configured", str(ctx.exception))
    
    def test_ensure_token_returns_when_present(self):
        """ensure_token returns token when configured."""
        config = TushareConfig(token="test_token_123")
        
        token = config.ensure_token()
        self.assertEqual(token, "test_token_123")
    
    def test_from_env_without_env_vars(self):
        """from_env creates config even without env vars."""
        with patch.dict("os.environ", {}, clear=True):
            config = TushareConfig.from_env()

        self.assertIsNotNone(config)
        self.assertEqual(config.api_url, "http://8.163.90.143:8686/")

    def test_from_env_reads_api_url_override(self):
        with patch.dict(
            "os.environ",
            {"TUSHARE_API_URL": "https://provider.example/api"},
            clear=True,
        ):
            config = TushareConfig.from_env()

        self.assertEqual(config.api_url, "https://provider.example/api")

    def test_from_env_blank_api_url_uses_default(self):
        with patch.dict("os.environ", {"TUSHARE_API_URL": ""}, clear=True):
            config = TushareConfig.from_env()

        self.assertEqual(config.api_url, "http://8.163.90.143:8686/")


if __name__ == "__main__":
    unittest.main()
