from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest


REPO_ROOT = Path(
    os.environ.get("TRADERLENS_SOURCE_ROOT", Path(__file__).resolve().parents[1])
).resolve()


class TestV3B5FormalAdmission(unittest.TestCase):
    def test_current_verified_inputs_publish_independently_verified_formal_contract(self) -> None:
        from scripts.publish_v3_b5_bundle import publish_verified_b5_bundle
        from scripts.verify_v3_b5_bundle import verify_verified_b5_bundle

        with tempfile.TemporaryDirectory() as temp_dir:
            published = publish_verified_b5_bundle(REPO_ROOT, Path(temp_dir) / "bundles")
            self.assertIn(published["status"], {"published", "already_published"})
            bundle_dir = Path(published["path"])
            manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
            verified = verify_verified_b5_bundle(REPO_ROOT, bundle_dir)

        self.assertEqual(manifest["authorization_scope"], "v3_b5_formal_b6_preflight")
        self.assertFalse(manifest["not_authorized_for_b6_oos_gate_promotion_signal"])
        self.assertEqual(
            manifest["lineage"]["b3_execution_input"]["artifact_id"],
            "05f38a2884dc7e47",
        )
        self.assertEqual(
            manifest["lineage"]["b3_execution_input"]["manifest_sha256"],
            "741e511778ba7d520230c8378c952fd85dc407129d66cfb4366c7112530793a6",
        )
        self.assertEqual(verified["status"], "verified")
        self.assertEqual(verified["verifier_identity"], manifest["verifier_identity"])
        self.assertEqual(verified["verifier_identity"]["verifier_id"], "v3_b5_formal_independent_verifier.v1")
        self.assertEqual(
            verified["verifier_identity"]["engine_source_path"],
            "backend/services/v3_b5_bundle.py",
        )
        self.assertEqual(
            verified["verifier_identity"]["source_loader_path"],
            "scripts/publish_v3_b5_bundle.py",
        )


if __name__ == "__main__":
    unittest.main()
