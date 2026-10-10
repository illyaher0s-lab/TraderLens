"""RED tests for stock_st reconciled acceptance _003 full verification."""
import json
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestStockStReconciledAcceptance003(unittest.TestCase):
    """RED tests — current verifier misses these."""
    
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).parent.parent
        cls.artifact_id = "stacc_traderlens_v2_shsz_stock_st_003"
        
        # ponytail: publish once for all tests
        from scripts.publish_stock_st_reconciled_acceptance import publish_acceptance
        publish_acceptance(cls.repo_root, cls.artifact_id)
    
    def test_partition_6_tamper_detected(self):
        """RED: verifier misses partition[5] (6th) tamper."""
        from scripts.publish_stock_st_reconciled_acceptance import publish_acceptance, verify_acceptance, compute_file_hash
        
        # ponytail: publish clean first
        publish_acceptance(self.repo_root, self.artifact_id)
        
        # ponytail: corrupt partition 6
        staging = self.repo_root / f"data/pit/.staging/{self.artifact_id}_tamper6"
        final = self.repo_root / f"data/pit/stock_st_reconciled_acceptances/{self.artifact_id}"
        shutil.copytree(final, staging)
        
        manifest = json.loads((staging / "manifest.json").read_text())
        manifest["partitions"][5]["file_sha256"] = "0" * 64
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
        
        # ponytail: RED — should reject, but current verifier only checks first 5
        with self.assertRaises(AssertionError, msg="Verifier should catch partition 6 tamper"):
            verify_acceptance(self.repo_root, staging)
        
        shutil.rmtree(staging, ignore_errors=True)
    
    def test_partition_last_tamper_detected(self):
        """RED: verifier misses last partition tamper."""
        from scripts.publish_stock_st_reconciled_acceptance import publish_acceptance, verify_acceptance
        
        staging = self.repo_root / f"data/pit/.staging/{self.artifact_id}_tamper_last"
        final = self.repo_root / f"data/pit/stock_st_reconciled_acceptances/{self.artifact_id}"
        shutil.copytree(final, staging)
        
        manifest = json.loads((staging / "manifest.json").read_text())
        manifest["partitions"][-1]["file_sha256"] = "f" * 64
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
        
        with self.assertRaises(AssertionError, msg="Verifier should catch last partition tamper"):
            verify_acceptance(self.repo_root, staging)
        
        shutil.rmtree(staging, ignore_errors=True)
    
    def test_outcomes_tamper_detected(self):
        """RED: verifier doesn't verify outcomes content."""
        from scripts.publish_stock_st_reconciled_acceptance import verify_acceptance
        
        staging = self.repo_root / f"data/pit/.staging/{self.artifact_id}_outcomes_tamper"
        final = self.repo_root / f"data/pit/stock_st_reconciled_acceptances/{self.artifact_id}"
        shutil.copytree(final, staging)
        
        # ponytail: corrupt outcomes
        outcomes = json.loads((staging / "empty_outcomes.json").read_text())
        outcomes["outcomes"][0]["row_count"] = 999
        (staging / "empty_outcomes.json").write_text(json.dumps(outcomes, indent=2, sort_keys=True))
        
        with self.assertRaises(AssertionError, msg="Verifier should catch outcomes tamper"):
            verify_acceptance(self.repo_root, staging)
        
        shutil.rmtree(staging, ignore_errors=True)
    
    def test_outcomes_external_path_rejected(self):
        """RED: verifier reads .staging fallback."""
        from scripts.publish_stock_st_reconciled_acceptance import verify_acceptance
        
        staging = self.repo_root / f"data/pit/.staging/{self.artifact_id}_external"
        final = self.repo_root / f"data/pit/stock_st_reconciled_acceptances/{self.artifact_id}"
        shutil.copytree(final, staging)
        
        # ponytail: delete artifact-local outcomes
        (staging / "empty_outcomes.json").unlink()
        (staging / "empty_outcomes.json.sha256").unlink()
        
        with self.assertRaises((FileNotFoundError, AssertionError), msg="Verifier should reject missing artifact-local outcomes"):
            verify_acceptance(self.repo_root, staging)
        
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
