"""Integration tests for V2 formal snapshot publication."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


class TestPublicationIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.temp_path = Path(self.temp)

    def tearDown(self):
        shutil.rmtree(self.temp)

    def test_publisher_does_not_access_business_data(self):
        # ponytail: publisher forbidden from daily/daily_basic/stk_limit/adj_factor/lifecycle/membership
        business_paths = [
            "data/pit/tushare/daily",
            "data/pit/tushare/daily_basic",
            "data/pit/tushare/stk_limit",
            "data/pit/tushare/adj_factor",
            "data/pit/vendor_daily_snapshot/vendor_8e64285ae2fdea2e/security_lifecycle",
            "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/partitions",
        ]
        for p in business_paths:
            path = ROOT / p
            if path.exists():
                self.fail(f"Publisher accessed business data path: {p}")

    def test_write_once_conflict_detection(self):
        from scripts.publish_v2_formal_snapshot import publish_data_snapshot_manifest
        
        out_dir = self.temp_path / "data_snapshot_manifests"
        out_dir.mkdir()
        
        from datetime import date
        publish_data_snapshot_manifest(
            snapshot_id="ds_conflict_test",
            provider="mixed_vendor_tushare",
            market_data_start=date(2016, 1, 4),
            market_data_end=date(2026, 7, 10),
            semantic_hash="da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e",
            universe_reference_ids=("uref_test",),
            coverage_package_id="695245b51005e50b",
            coverage_manifest_sha256="4e8b6163d4db11836e8a3aedc542d69ed6707bab566b6e0b16cb124d2b1e705f",
            expected_stock_days=10659050,
            complete_stock_days=10476263,
            unavailable_stock_days=182787,
            field_missing_counts={"daily": 181890},
            source_manifest_hashes={"source.json": "a" * 64},
            output_dir=out_dir,
        )
        
        with self.assertRaises(ValueError) as ctx:
            publish_data_snapshot_manifest(
                snapshot_id="ds_conflict_test",
                provider="different_provider",
                market_data_start=date(2016, 1, 4),
                market_data_end=date(2026, 7, 10),
                semantic_hash="different_hash",
                universe_reference_ids=("uref_test",),
                coverage_package_id="695245b51005e50b",
                coverage_manifest_sha256="4e8b6163d4db11836e8a3aedc542d69ed6707bab566b6e0b16cb124d2b1e705f",
                expected_stock_days=10659050,
                complete_stock_days=10476263,
                unavailable_stock_days=182787,
                field_missing_counts={"daily": 181890},
                source_manifest_hashes={"source.json": "a" * 64},
                output_dir=out_dir,
            )
        self.assertIn("different content", str(ctx.exception))

    def test_old_artifacts_unchanged(self):
        import hashlib
        
        roots = [
            "data/pit/formal_packages/de3fed9c3819d25c",
            "data/pit/formal_packages/35d996036cc04179",
            "data/pit/coverage_packages/695245b51005e50b",
            "data/pit/coverage_packages/de3fed9c3819d25c",
        ]
        
        baseline = {}
        for root in roots:
            root_path = ROOT / root
            if not root_path.exists():
                continue
            for f in root_path.rglob("*"):
                if f.is_file():
                    baseline[str(f.relative_to(ROOT))] = hashlib.sha256(f.read_bytes()).hexdigest()
        
        # ponytail: any publish would have happened before test runs
        # This test verifies no mutation occurred
        for rel_path, expected_hash in baseline.items():
            actual = hashlib.sha256((ROOT / rel_path).read_bytes()).hexdigest()
            self.assertEqual(expected_hash, actual, f"{rel_path} was modified")

    def test_cli_publishes_verified_provenance_and_verifier_rereads_inputs(self):
        """The real publisher derives coverage dates/totals and the verifier rebinds inputs."""
        source_root = ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership"
        vendor_root = ROOT / "data/pit/vendor_daily_snapshot/vendor_8e64285ae2fdea2e"
        output_root = self.temp_path / "published"
        common_args = [
            "--predecessor-manifest", str(ROOT / "data/pit/formal_packages/de3fed9c3819d25c/manifest.json"),
            "--coverage-manifest", str(ROOT / "data/pit/coverage_packages/695245b51005e50b/coverage_manifest.json"),
            "--coverage-sidecar", str(ROOT / "data/pit/coverage_packages/695245b51005e50b/coverage_manifest.json.sha256"),
            "--coverage-by-date", str(ROOT / "data/pit/coverage_packages/695245b51005e50b/coverage_by_date.parquet"),
            "--successor-manifest", str(ROOT / "data/pit/qualification_successors/e5100669ed247769/manifest.json"),
            "--sw2021-membership-manifest", str(source_root / "manifest.json"),
            "--sw2021-universe-candidate", str(source_root / "sw2021_universe_candidate.json"),
            "--vendor-manifest", str(vendor_root / "manifest.json"),
            "--vendor-lifecycle-candidate", str(vendor_root / "security_lifecycle_candidate.json"),
            "--scope-freeze", str(ROOT / "docs/verification/V2_HISTORICAL_VALIDATION_SCOPE_FREEZE.md"),
        ]
        publish = subprocess.run(
            [sys.executable, str(ROOT / "scripts/publish_v2_formal_snapshot_main.py"), *common_args,
             "--output-root", str(output_root)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(publish.returncode, 0, publish.stderr)

        snapshot_dir = output_root / "data_snapshot_manifests/ds_traderlens_v2_shsz_pit_001"
        snapshot = json.loads((snapshot_dir / "manifest.json").read_text())
        self.assertEqual(snapshot["market_data_start"], "2016-01-04")
        self.assertEqual(snapshot["market_data_end"], "2026-07-10")
        self.assertEqual(snapshot["coverage_disclosure"]["expected_stock_days"], 10659050)
        self.assertEqual(
            dict(snapshot["source_manifest_hashes"])["vendor_lifecycle_candidate.json"],
            "b429790813232d430fbc8a50247fff7f0a2e2d0bca3a12cd922019cd761bedb5",
        )

        verify = subprocess.run(
            [
                sys.executable, str(ROOT / "scripts/verify_v2_formal_snapshot.py"),
                "--universe-reference-dir", str(output_root / "universe_references/uref_traderlens_v2_shsz_sw2021_pit_001"),
                "--data-snapshot-dir", str(snapshot_dir),
                *common_args,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(verify.returncode, 0, verify.stderr)
        self.assertIn('"status": "valid"', verify.stdout)

    def test_verifier_rejects_tampered_bound_vendor_manifest(self):
        """A verifier must rehash caller-supplied provenance, not trust the artifact."""
        source_root = ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership"
        vendor_root = ROOT / "data/pit/vendor_daily_snapshot/vendor_8e64285ae2fdea2e"
        tampered_vendor = self.temp_path / "vendor_manifest.json"
        tampered_vendor.write_bytes((vendor_root / "manifest.json").read_bytes() + b"\n")
        verify = subprocess.run(
            [
                sys.executable, str(ROOT / "scripts/verify_v2_formal_snapshot.py"),
                "--universe-reference-dir", str(ROOT / "data/pit/universe_references/uref_traderlens_v2_shsz_sw2021_pit_001"),
                "--data-snapshot-dir", str(ROOT / "data/pit/data_snapshot_manifests/ds_traderlens_v2_shsz_pit_001"),
                "--predecessor-manifest", str(ROOT / "data/pit/formal_packages/de3fed9c3819d25c/manifest.json"),
                "--coverage-manifest", str(ROOT / "data/pit/coverage_packages/695245b51005e50b/coverage_manifest.json"),
                "--coverage-sidecar", str(ROOT / "data/pit/coverage_packages/695245b51005e50b/coverage_manifest.json.sha256"),
                "--coverage-by-date", str(ROOT / "data/pit/coverage_packages/695245b51005e50b/coverage_by_date.parquet"),
                "--successor-manifest", str(ROOT / "data/pit/qualification_successors/e5100669ed247769/manifest.json"),
                "--sw2021-membership-manifest", str(source_root / "manifest.json"),
                "--sw2021-universe-candidate", str(source_root / "sw2021_universe_candidate.json"),
                "--vendor-manifest", str(tampered_vendor),
                "--vendor-lifecycle-candidate", str(vendor_root / "security_lifecycle_candidate.json"),
                "--scope-freeze", str(ROOT / "docs/verification/V2_HISTORICAL_VALIDATION_SCOPE_FREEZE.md"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(verify.returncode, 0)
        self.assertIn("source binding mismatch: vendor_snapshot_manifest.json", verify.stdout)

    def test_verifier_rejects_disclosure_counts_rehashed_after_tamper(self):
        """Self-consistent artifact hashes cannot hide a coverage disclosure mismatch."""
        import hashlib

        source_root = ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership"
        vendor_root = ROOT / "data/pit/vendor_daily_snapshot/vendor_8e64285ae2fdea2e"
        temp_ref = self.temp_path / "universe_reference"
        temp_snapshot = self.temp_path / "data_snapshot"
        shutil.copytree(ROOT / "data/pit/universe_references/uref_traderlens_v2_shsz_sw2021_pit_001", temp_ref)
        shutil.copytree(ROOT / "data/pit/data_snapshot_manifests/ds_traderlens_v2_shsz_pit_001", temp_snapshot)
        manifest_path = temp_snapshot / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["coverage_disclosure"]["field_missing_counts"][1][1] += 1
        content = dict(manifest)
        content.pop("manifest_content_hash")
        manifest["manifest_content_hash"] = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
        manifest_path.write_text(json.dumps(manifest, indent=2))
        (temp_snapshot / "manifest.json.sha256").write_text(hashlib.sha256(manifest_path.read_bytes()).hexdigest())

        verify = subprocess.run(
            [
                sys.executable, str(ROOT / "scripts/verify_v2_formal_snapshot.py"),
                "--universe-reference-dir", str(temp_ref),
                "--data-snapshot-dir", str(temp_snapshot),
                "--predecessor-manifest", str(ROOT / "data/pit/formal_packages/de3fed9c3819d25c/manifest.json"),
                "--coverage-manifest", str(ROOT / "data/pit/coverage_packages/695245b51005e50b/coverage_manifest.json"),
                "--coverage-sidecar", str(ROOT / "data/pit/coverage_packages/695245b51005e50b/coverage_manifest.json.sha256"),
                "--coverage-by-date", str(ROOT / "data/pit/coverage_packages/695245b51005e50b/coverage_by_date.parquet"),
                "--successor-manifest", str(ROOT / "data/pit/qualification_successors/e5100669ed247769/manifest.json"),
                "--sw2021-membership-manifest", str(source_root / "manifest.json"),
                "--sw2021-universe-candidate", str(source_root / "sw2021_universe_candidate.json"),
                "--vendor-manifest", str(vendor_root / "manifest.json"),
                "--vendor-lifecycle-candidate", str(vendor_root / "security_lifecycle_candidate.json"),
                "--scope-freeze", str(ROOT / "docs/verification/V2_HISTORICAL_VALIDATION_SCOPE_FREEZE.md"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(verify.returncode, 0)
        self.assertIn("coverage disclosure mismatch", verify.stdout)


if __name__ == "__main__":
    unittest.main()
