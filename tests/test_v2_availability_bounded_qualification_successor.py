"""V2 availability-bounded qualification successor: metadata-only TDD tests."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


class TestSuccessorBuilder(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.temp_path = Path(self.temp)
        
        # Copy predecessor manifest
        pred_src = ROOT / "data/pit/formal_packages/de3fed9c3819d25c/manifest.json"
        pred_dir = self.temp_path / "predecessor"
        pred_dir.mkdir()
        shutil.copy2(pred_src, pred_dir / "manifest.json")
        
        # Copy coverage manifest + sidecar + 3 parquets
        cov_src_dir = ROOT / "data/pit/coverage_packages/695245b51005e50b"
        cov_dir = self.temp_path / "coverage"
        cov_dir.mkdir()
        shutil.copy2(cov_src_dir / "coverage_manifest.json", cov_dir / "coverage_manifest.json")
        shutil.copy2(cov_src_dir / "coverage_manifest.json.sha256", cov_dir / "coverage_manifest.json.sha256")
        for name in ["coverage_by_code.parquet", "coverage_by_date.parquet", "unavailable_security_dates.parquet"]:
            shutil.copy2(cov_src_dir / name, cov_dir / name)
        
        # Copy scope freeze
        scope_src = ROOT / "docs/verification/V2_HISTORICAL_VALIDATION_SCOPE_FREEZE.md"
        shutil.copy2(scope_src, self.temp_path / "scope_freeze.md")
        
        self.out_dir = self.temp_path / "successors"
        self.out_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp)

    def _build_kwargs(self):
        return {
            "predecessor_manifest_path": self.temp_path / "predecessor/manifest.json",
            "coverage_manifest_path": self.temp_path / "coverage/coverage_manifest.json",
            "coverage_sidecar_path": self.temp_path / "coverage/coverage_manifest.json.sha256",
            "coverage_by_code_path": self.temp_path / "coverage/coverage_by_code.parquet",
            "coverage_by_date_path": self.temp_path / "coverage/coverage_by_date.parquet",
            "unavailable_path": self.temp_path / "coverage/unavailable_security_dates.parquet",
            "scope_freeze_path": self.temp_path / "scope_freeze.md",
        }

    def test_deterministic_successor_from_isolated_inputs(self):
        from scripts.build_v2_availability_bounded_qualification_successor import build_successor
        
        result = build_successor(
            predecessor_manifest_path=self.temp_path / "predecessor/manifest.json",
            coverage_manifest_path=self.temp_path / "coverage/coverage_manifest.json",
            coverage_sidecar_path=self.temp_path / "coverage/coverage_manifest.json.sha256",
            coverage_by_code_path=self.temp_path / "coverage/coverage_by_code.parquet",
            coverage_by_date_path=self.temp_path / "coverage/coverage_by_date.parquet",
            unavailable_path=self.temp_path / "coverage/unavailable_security_dates.parquet",
            scope_freeze_path=self.temp_path / "scope_freeze.md",
            output_dir=self.out_dir,
        )
        
        self.assertEqual(result["status"], "availability_bounded_qualified")
        self.assertIsNotNone(result["successor_id"])
        self.assertEqual(len(result["successor_id"]), 16)
        
        manifest_path = self.out_dir / result["successor_id"] / "manifest.json"
        self.assertTrue(manifest_path.exists())
        
        sidecar_path = self.out_dir / result["successor_id"] / "manifest.json.sha256"
        self.assertTrue(sidecar_path.exists())
        
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(manifest["status"], "availability_bounded_qualified")
        self.assertEqual(manifest["predecessor_qualification_package_id"], "de3fed9c3819d25c")
        self.assertEqual(manifest["predecessor_original_status"], "not_qualified")
        self.assertEqual(manifest["coverage_package_id"], "695245b51005e50b")

    def test_preserves_predecessor_immutable_fields(self):
        from scripts.build_v2_availability_bounded_qualification_successor import build_successor
        
        result = build_successor(
            predecessor_manifest_path=self.temp_path / "predecessor/manifest.json",
            coverage_manifest_path=self.temp_path / "coverage/coverage_manifest.json",
            coverage_sidecar_path=self.temp_path / "coverage/coverage_manifest.json.sha256",
            coverage_by_code_path=self.temp_path / "coverage/coverage_by_code.parquet",
            coverage_by_date_path=self.temp_path / "coverage/coverage_by_date.parquet",
            unavailable_path=self.temp_path / "coverage/unavailable_security_dates.parquet",
            scope_freeze_path=self.temp_path / "scope_freeze.md",
            output_dir=self.out_dir,
        )
        
        manifest_path = self.out_dir / result["successor_id"] / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        
        self.assertEqual(manifest["predecessor_original_status"], "not_qualified")
        self.assertEqual(manifest["predecessor_manifest_sha256"], "1cdb48bf9b78b7664513bd3afa7ac4466483529dedcf78bd996d1846b7f2087d")

    def test_binds_coverage_artifacts(self):
        from scripts.build_v2_availability_bounded_qualification_successor import build_successor
        
        result = build_successor(
            predecessor_manifest_path=self.temp_path / "predecessor/manifest.json",
            coverage_manifest_path=self.temp_path / "coverage/coverage_manifest.json",
            coverage_sidecar_path=self.temp_path / "coverage/coverage_manifest.json.sha256",
            coverage_by_code_path=self.temp_path / "coverage/coverage_by_code.parquet",
            coverage_by_date_path=self.temp_path / "coverage/coverage_by_date.parquet",
            unavailable_path=self.temp_path / "coverage/unavailable_security_dates.parquet",
            scope_freeze_path=self.temp_path / "scope_freeze.md",
            output_dir=self.out_dir,
        )
        
        manifest_path = self.out_dir / result["successor_id"] / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        
        self.assertEqual(manifest["coverage_manifest_sha256"], "4e8b6163d4db11836e8a3aedc542d69ed6707bab566b6e0b16cb124d2b1e705f")
        self.assertEqual(manifest["coverage_structural_validation"], "passed")
        self.assertEqual(manifest["coverage_structural_errors"], [])
        self.assertEqual(manifest["coverage_expected_stock_days"], 10659050)
        self.assertEqual(manifest["coverage_complete_stock_days"], 10476263)
        self.assertEqual(manifest["coverage_unavailable_stock_days"], 182787)

    def test_template_binding(self):
        from scripts.build_v2_availability_bounded_qualification_successor import build_successor
        
        result = build_successor(
            predecessor_manifest_path=self.temp_path / "predecessor/manifest.json",
            coverage_manifest_path=self.temp_path / "coverage/coverage_manifest.json",
            coverage_sidecar_path=self.temp_path / "coverage/coverage_manifest.json.sha256",
            coverage_by_code_path=self.temp_path / "coverage/coverage_by_code.parquet",
            coverage_by_date_path=self.temp_path / "coverage/coverage_by_date.parquet",
            unavailable_path=self.temp_path / "coverage/unavailable_security_dates.parquet",
            scope_freeze_path=self.temp_path / "scope_freeze.md",
            output_dir=self.out_dir,
        )
        
        manifest_path = self.out_dir / result["successor_id"] / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        
        expected_hash = "17a1be7ea3547e7a3cc85ea25e63b43aa2ddb4e8ced50c699db5a1bdd9cec9f0"
        self.assertEqual(manifest["template_id"], "relative_strength_rotation_shsz_sw2021_v1")
        self.assertEqual(manifest["template_version"], "v1_shsz_sw2021_pit")
        self.assertEqual(manifest["template_hash"], expected_hash)
        self.assertEqual(manifest["predecessor_template_hash"], expected_hash)
        self.assertEqual(manifest["coverage_template_hash"], expected_hash)

    def test_verifier_validates_all_bindings(self):
        from scripts.build_v2_availability_bounded_qualification_successor import build_successor
        from scripts.verify_v2_availability_bounded_qualification_successor import verify_successor
        
        result = build_successor(
            predecessor_manifest_path=self.temp_path / "predecessor/manifest.json",
            coverage_manifest_path=self.temp_path / "coverage/coverage_manifest.json",
            coverage_sidecar_path=self.temp_path / "coverage/coverage_manifest.json.sha256",
            coverage_by_code_path=self.temp_path / "coverage/coverage_by_code.parquet",
            coverage_by_date_path=self.temp_path / "coverage/coverage_by_date.parquet",
            unavailable_path=self.temp_path / "coverage/unavailable_security_dates.parquet",
            scope_freeze_path=self.temp_path / "scope_freeze.md",
            output_dir=self.out_dir,
        )
        
        successor_dir = self.out_dir / result["successor_id"]
        verify_result = verify_successor(successor_dir, **self._build_kwargs())
        self.assertEqual(verify_result["status"], "valid")

    def test_rejects_tampered_predecessor_manifest_hash(self):
        from scripts.build_v2_availability_bounded_qualification_successor import build_successor
        
        # Tamper predecessor
        pred_manifest = self.temp_path / "predecessor/manifest.json"
        data = json.loads(pred_manifest.read_text())
        data["blocking_gap_count"] = 0
        pred_manifest.write_text(json.dumps(data))
        
        with self.assertRaises(ValueError) as ctx:
            build_successor(
                predecessor_manifest_path=pred_manifest,
                coverage_manifest_path=self.temp_path / "coverage/coverage_manifest.json",
                coverage_sidecar_path=self.temp_path / "coverage/coverage_manifest.json.sha256",
                coverage_by_code_path=self.temp_path / "coverage/coverage_by_code.parquet",
                coverage_by_date_path=self.temp_path / "coverage/coverage_by_date.parquet",
                unavailable_path=self.temp_path / "coverage/unavailable_security_dates.parquet",
                scope_freeze_path=self.temp_path / "scope_freeze.md",
                output_dir=self.out_dir,
            )
        self.assertIn("predecessor", str(ctx.exception).lower())

    def test_rejects_tampered_coverage_sidecar(self):
        from scripts.build_v2_availability_bounded_qualification_successor import build_successor
        
        sidecar = self.temp_path / "coverage/coverage_manifest.json.sha256"
        sidecar.write_text("0" * 64)
        
        with self.assertRaises(ValueError):
            build_successor(
                predecessor_manifest_path=self.temp_path / "predecessor/manifest.json",
                coverage_manifest_path=self.temp_path / "coverage/coverage_manifest.json",
                coverage_sidecar_path=sidecar,
                coverage_by_code_path=self.temp_path / "coverage/coverage_by_code.parquet",
                coverage_by_date_path=self.temp_path / "coverage/coverage_by_date.parquet",
                unavailable_path=self.temp_path / "coverage/unavailable_security_dates.parquet",
                scope_freeze_path=self.temp_path / "scope_freeze.md",
                output_dir=self.out_dir,
            )

    def test_rejects_structural_errors(self):
        from scripts.build_v2_availability_bounded_qualification_successor import build_successor
        import hashlib
        
        cov_manifest = self.temp_path / "coverage/coverage_manifest.json"
        data = json.loads(cov_manifest.read_text())
        data["structural_errors"] = ["test error"]
        cov_manifest.write_text(json.dumps(data))
        
        # Update sidecar
        new_hash = hashlib.sha256(cov_manifest.read_bytes()).hexdigest()
        (self.temp_path / "coverage/coverage_manifest.json.sha256").write_text(new_hash)
        
        with self.assertRaises(ValueError) as ctx:
            build_successor(
                predecessor_manifest_path=self.temp_path / "predecessor/manifest.json",
                coverage_manifest_path=cov_manifest,
                coverage_sidecar_path=self.temp_path / "coverage/coverage_manifest.json.sha256",
                coverage_by_code_path=self.temp_path / "coverage/coverage_by_code.parquet",
                coverage_by_date_path=self.temp_path / "coverage/coverage_by_date.parquet",
                unavailable_path=self.temp_path / "coverage/unavailable_security_dates.parquet",
                scope_freeze_path=self.temp_path / "scope_freeze.md",
                output_dir=self.out_dir,
            )
        self.assertIn("structural", str(ctx.exception).lower())

    def test_rejects_arithmetic_mismatch(self):
        from scripts.build_v2_availability_bounded_qualification_successor import build_successor
        import hashlib
        
        cov_manifest = self.temp_path / "coverage/coverage_manifest.json"
        data = json.loads(cov_manifest.read_text())
        data["complete_stock_days"] = 1
        cov_manifest.write_text(json.dumps(data))
        
        # Update sidecar
        new_hash = hashlib.sha256(cov_manifest.read_bytes()).hexdigest()
        (self.temp_path / "coverage/coverage_manifest.json.sha256").write_text(new_hash)
        
        with self.assertRaises(ValueError) as ctx:
            build_successor(
                predecessor_manifest_path=self.temp_path / "predecessor/manifest.json",
                coverage_manifest_path=cov_manifest,
                coverage_sidecar_path=self.temp_path / "coverage/coverage_manifest.json.sha256",
                coverage_by_code_path=self.temp_path / "coverage/coverage_by_code.parquet",
                coverage_by_date_path=self.temp_path / "coverage/coverage_by_date.parquet",
                unavailable_path=self.temp_path / "coverage/unavailable_security_dates.parquet",
                scope_freeze_path=self.temp_path / "scope_freeze.md",
                output_dir=self.out_dir,
            )
        self.assertIn("arithmetic", str(ctx.exception).lower())

    def test_rejects_coverage_without_predecessor_content_hash_binding(self):
        """A matching package ID cannot replace the predecessor content hash binding."""
        from scripts.build_v2_availability_bounded_qualification_successor import build_successor
        import hashlib

        cov_manifest = self.temp_path / "coverage/coverage_manifest.json"
        data = json.loads(cov_manifest.read_text())
        data["input_manifest_content_hashes"]["qualification_manifest.json"] = "0" * 64
        cov_manifest.write_text(json.dumps(data))
        (self.temp_path / "coverage/coverage_manifest.json.sha256").write_text(
            hashlib.sha256(cov_manifest.read_bytes()).hexdigest()
        )

        with self.assertRaises(ValueError) as ctx:
            build_successor(output_dir=self.out_dir, **self._build_kwargs())

        self.assertIn("predecessor", str(ctx.exception).lower())
        self.assertEqual(list(self.out_dir.iterdir()), [])

    def test_verifier_rechecks_mutated_predecessor_input(self):
        """Verifier must compare the successor to current predecessor bytes, not itself."""
        from scripts.build_v2_availability_bounded_qualification_successor import build_successor
        from scripts.verify_v2_availability_bounded_qualification_successor import verify_successor

        result = build_successor(output_dir=self.out_dir, **self._build_kwargs())
        predecessor = self.temp_path / "predecessor/manifest.json"
        data = json.loads(predecessor.read_text())
        data["blocking_gap_count"] = 0
        predecessor.write_text(json.dumps(data))

        verification = verify_successor(
            self.out_dir / result["successor_id"],
            **self._build_kwargs(),
        )

        self.assertEqual(verification["status"], "invalid")
        self.assertIn("predecessor", verification["reason"])

    def test_verifier_rechecks_mutated_scope_freeze_input(self):
        """Verifier must compare the successor to the bound scope-freeze bytes."""
        from scripts.build_v2_availability_bounded_qualification_successor import build_successor
        from scripts.verify_v2_availability_bounded_qualification_successor import verify_successor

        result = build_successor(output_dir=self.out_dir, **self._build_kwargs())
        scope_freeze = self.temp_path / "scope_freeze.md"
        scope_freeze.write_bytes(scope_freeze.read_bytes() + b"\nmodified")

        verification = verify_successor(
            self.out_dir / result["successor_id"],
            **self._build_kwargs(),
        )

        self.assertEqual(verification["status"], "invalid")
        self.assertIn("scope", verification["reason"])

    def test_verifier_rechecks_mutated_coverage_parquet_input(self):
        """Verifier must hash the bound parquet bytes, not trust successor metadata."""
        from scripts.build_v2_availability_bounded_qualification_successor import build_successor
        from scripts.verify_v2_availability_bounded_qualification_successor import verify_successor

        result = build_successor(output_dir=self.out_dir, **self._build_kwargs())
        parquet = self.temp_path / "coverage/coverage_by_code.parquet"
        parquet.write_bytes(parquet.read_bytes() + b"tampered")

        verification = verify_successor(
            self.out_dir / result["successor_id"],
            **self._build_kwargs(),
        )

        self.assertEqual(verification["status"], "invalid")
        self.assertIn("parquet", verification["reason"])

    def test_verifier_rechecks_successor_template_version(self):
        """A rewritten successor sidecar cannot legitimize a false template version."""
        from scripts.build_v2_availability_bounded_qualification_successor import build_successor
        from scripts.verify_v2_availability_bounded_qualification_successor import verify_successor
        import hashlib

        result = build_successor(output_dir=self.out_dir, **self._build_kwargs())
        manifest_path = self.out_dir / result["successor_id"] / "manifest.json"
        data = json.loads(manifest_path.read_text())
        data["template_version"] = "forged"
        manifest_path.write_text(json.dumps(data))
        (manifest_path.parent / "manifest.json.sha256").write_text(
            hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        )

        verification = verify_successor(
            self.out_dir / result["successor_id"],
            **self._build_kwargs(),
        )

        self.assertEqual(verification["status"], "invalid")
        self.assertIn("template version", verification["reason"])

    def test_cli_builds_from_explicit_metadata_paths(self):
        """The builder script must publish from explicit metadata paths, not exit silently."""
        command = [
            sys.executable,
            str(ROOT / "scripts/build_v2_availability_bounded_qualification_successor.py"),
            "--predecessor-manifest", str(self.temp_path / "predecessor/manifest.json"),
            "--coverage-manifest", str(self.temp_path / "coverage/coverage_manifest.json"),
            "--coverage-sidecar", str(self.temp_path / "coverage/coverage_manifest.json.sha256"),
            "--coverage-by-code", str(self.temp_path / "coverage/coverage_by_code.parquet"),
            "--coverage-by-date", str(self.temp_path / "coverage/coverage_by_date.parquet"),
            "--unavailable", str(self.temp_path / "coverage/unavailable_security_dates.parquet"),
            "--scope-freeze", str(self.temp_path / "scope_freeze.md"),
            "--output-root", str(self.out_dir),
        ]

        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(any(self.out_dir.iterdir()))

    def test_rejects_existing_deterministic_output_without_overwrite(self):
        """A repeated build must not overwrite an immutable successor directory."""
        from scripts.build_v2_availability_bounded_qualification_successor import build_successor

        build_successor(output_dir=self.out_dir, **self._build_kwargs())

        with self.assertRaises(RuntimeError) as ctx:
            build_successor(output_dir=self.out_dir, **self._build_kwargs())

        self.assertIn("already exists", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
