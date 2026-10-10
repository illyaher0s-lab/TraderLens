"""V2 formal snapshot manifest publication tests."""
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


class TestUniverseReferencePublication(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.temp_path = Path(self.temp)
        self.out_dir = self.temp_path / "universe_references"
        self.out_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp)

    def test_publishes_metadata_only_universe_reference(self):
        from scripts.publish_v2_formal_snapshot import publish_universe_reference
        
        result = publish_universe_reference(
            universe_reference_id="uref_test_001",
            sw2021_membership_manifest_sha256="a38b3cc6be947b290078fe637466991ee8d13dee2794d398fb709d5c4c3826f3",
            sw2021_universe_candidate_sha256="8374602c2b4fda9ca5f9ae2d27daa2ceceee1fe31fb7894dc10d1d8d789fb994",
            universe_definition_hash="55d2ceb6e20641b69a1dc07e17d9d8707abc4488132acf0734c6946f1dbf94dc",
            source_taxonomy="SW2021",
            output_dir=self.out_dir,
        )
        
        self.assertEqual(result["status"], "published")
        self.assertEqual(result["universe_reference_id"], "uref_test_001")
        
        manifest_path = self.out_dir / "uref_test_001" / "manifest.json"
        self.assertTrue(manifest_path.exists())
        
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(manifest["universe_reference_id"], "uref_test_001")
        self.assertEqual(manifest["source_taxonomy"], "SW2021")
        self.assertTrue(manifest["provenance_only"])
        self.assertTrue(manifest["not_authorized_for_b6_oos_gate_promotion_signal"])

    def test_idempotent_publish(self):
        from scripts.publish_v2_formal_snapshot import publish_universe_reference
        
        result1 = publish_universe_reference(
            universe_reference_id="uref_test_002",
            sw2021_membership_manifest_sha256="a38b3cc6be947b290078fe637466991ee8d13dee2794d398fb709d5c4c3826f3",
            sw2021_universe_candidate_sha256="8374602c2b4fda9ca5f9ae2d27daa2ceceee1fe31fb7894dc10d1d8d789fb994",
            universe_definition_hash="55d2ceb6e20641b69a1dc07e17d9d8707abc4488132acf0734c6946f1dbf94dc",
            source_taxonomy="SW2021",
            output_dir=self.out_dir,
        )
        self.assertEqual(result1["status"], "published")
        
        result2 = publish_universe_reference(
            universe_reference_id="uref_test_002",
            sw2021_membership_manifest_sha256="a38b3cc6be947b290078fe637466991ee8d13dee2794d398fb709d5c4c3826f3",
            sw2021_universe_candidate_sha256="8374602c2b4fda9ca5f9ae2d27daa2ceceee1fe31fb7894dc10d1d8d789fb994",
            universe_definition_hash="55d2ceb6e20641b69a1dc07e17d9d8707abc4488132acf0734c6946f1dbf94dc",
            source_taxonomy="SW2021",
            output_dir=self.out_dir,
        )
        self.assertEqual(result2["status"], "already_published")


class TestDataSnapshotPublication(unittest.TestCase):
    SOURCE_HASHES = {"source.json": "a" * 64}

    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.temp_path = Path(self.temp)
        self.out_dir = self.temp_path / "data_snapshot_manifests"
        self.out_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp)

    def test_publishes_formal_snapshot_with_fixed_semantic_hash(self):
        from scripts.publish_v2_formal_snapshot import publish_data_snapshot_manifest
        
        result = publish_data_snapshot_manifest(
            snapshot_id="ds_test_001",
            provider="mixed_vendor_tushare",
            market_data_start=date(2016, 1, 4),
            market_data_end=date(2026, 7, 10),
            semantic_hash="da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e",
            universe_reference_ids=("uref_test_001",),
            coverage_package_id="695245b51005e50b",
            coverage_manifest_sha256="4e8b6163d4db11836e8a3aedc542d69ed6707bab566b6e0b16cb124d2b1e705f",
            expected_stock_days=10659050,
            complete_stock_days=10476263,
            unavailable_stock_days=182787,
            field_missing_counts={"daily": 181890, "daily_basic": 181903},
            source_manifest_hashes=self.SOURCE_HASHES,
            output_dir=self.out_dir,
        )
        
        self.assertEqual(result["status"], "published")
        manifest_path = self.out_dir / "ds_test_001" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        
        self.assertEqual(manifest["snapshot_id"], "ds_test_001")
        self.assertEqual(manifest["provider"], "mixed_vendor_tushare")
        self.assertIsNone(manifest["retrieval_date"])
        self.assertEqual(manifest["retrieval_date_status"], "unknown")
        self.assertEqual(manifest["semantic_hash"], "da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e")
        self.assertEqual(manifest["quality_status"], "ok")
        self.assertEqual(manifest["gaps"], ["availability_limited"])
        self.assertTrue(manifest["not_authorized_for_b6_oos_gate_promotion_signal"])
        self.assertEqual(manifest["universe_snapshot_ids"], [])
        self.assertEqual(manifest["universe_reference_ids"], ["uref_test_001"])

    def test_coverage_disclosure_sorted_by_field_name(self):
        from scripts.publish_v2_formal_snapshot import publish_data_snapshot_manifest
        
        result = publish_data_snapshot_manifest(
            snapshot_id="ds_test_002",
            provider="mixed_vendor_tushare",
            market_data_start=date(2016, 1, 4),
            market_data_end=date(2026, 7, 10),
            semantic_hash="da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e",
            universe_reference_ids=("uref_test_001",),
            coverage_package_id="695245b51005e50b",
            coverage_manifest_sha256="4e8b6163d4db11836e8a3aedc542d69ed6707bab566b6e0b16cb124d2b1e705f",
            expected_stock_days=10659050,
            complete_stock_days=10476263,
            unavailable_stock_days=182787,
            field_missing_counts={"stk_limit": 7699, "adj_factor": 258, "daily_basic": 181903, "daily": 181890},
            source_manifest_hashes=self.SOURCE_HASHES,
            output_dir=self.out_dir,
        )
        
        manifest_path = self.out_dir / "ds_test_002" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        disclosure = manifest["coverage_disclosure"]
        field_names = [item[0] for item in disclosure["field_missing_counts"]]
        self.assertEqual(field_names, sorted(field_names))

    def test_rejects_same_id_different_content(self):
        from scripts.publish_v2_formal_snapshot import publish_data_snapshot_manifest
        
        publish_data_snapshot_manifest(
            snapshot_id="ds_test_003",
            provider="mixed_vendor_tushare",
            market_data_start=date(2016, 1, 4),
            market_data_end=date(2026, 7, 10),
            semantic_hash="da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e",
            universe_reference_ids=("uref_test_001",),
            coverage_package_id="695245b51005e50b",
            coverage_manifest_sha256="4e8b6163d4db11836e8a3aedc542d69ed6707bab566b6e0b16cb124d2b1e705f",
            expected_stock_days=10659050,
            complete_stock_days=10476263,
            unavailable_stock_days=182787,
            field_missing_counts={"daily": 181890},
            source_manifest_hashes=self.SOURCE_HASHES,
            output_dir=self.out_dir,
        )
        
        with self.assertRaises(ValueError) as ctx:
            publish_data_snapshot_manifest(
                snapshot_id="ds_test_003",
                provider="mixed_vendor_tushare",
                market_data_start=date(2016, 1, 4),
                market_data_end=date(2026, 7, 10),
                semantic_hash="different_hash",
                universe_reference_ids=("uref_test_001",),
                coverage_package_id="695245b51005e50b",
                coverage_manifest_sha256="4e8b6163d4db11836e8a3aedc542d69ed6707bab566b6e0b16cb124d2b1e705f",
                expected_stock_days=10659050,
                complete_stock_days=10476263,
                unavailable_stock_days=182787,
                field_missing_counts={"daily": 181890},
                source_manifest_hashes=self.SOURCE_HASHES,
                output_dir=self.out_dir,
            )
        self.assertIn("different content", str(ctx.exception))

    def test_manifest_published_at_is_audit_field(self):
        from scripts.publish_v2_formal_snapshot import publish_data_snapshot_manifest
        
        result = publish_data_snapshot_manifest(
            snapshot_id="ds_test_004",
            provider="mixed_vendor_tushare",
            market_data_start=date(2016, 1, 4),
            market_data_end=date(2026, 7, 10),
            semantic_hash="da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e",
            universe_reference_ids=("uref_test_001",),
            coverage_package_id="695245b51005e50b",
            coverage_manifest_sha256="4e8b6163d4db11836e8a3aedc542d69ed6707bab566b6e0b16cb124d2b1e705f",
            expected_stock_days=10659050,
            complete_stock_days=10476263,
            unavailable_stock_days=182787,
            field_missing_counts={"daily": 181890},
            source_manifest_hashes=self.SOURCE_HASHES,
            output_dir=self.out_dir,
        )
        
        manifest_path = self.out_dir / "ds_test_004" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        self.assertIsNotNone(manifest["manifest_published_at"])
        self.assertTrue(datetime.fromisoformat(manifest["manifest_published_at"]))

    def test_manifest_content_hash_excludes_itself(self):
        from scripts.publish_v2_formal_snapshot import publish_data_snapshot_manifest
        
        result = publish_data_snapshot_manifest(
            snapshot_id="ds_test_005",
            provider="mixed_vendor_tushare",
            market_data_start=date(2016, 1, 4),
            market_data_end=date(2026, 7, 10),
            semantic_hash="da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e",
            universe_reference_ids=("uref_test_001",),
            coverage_package_id="695245b51005e50b",
            coverage_manifest_sha256="4e8b6163d4db11836e8a3aedc542d69ed6707bab566b6e0b16cb124d2b1e705f",
            expected_stock_days=10659050,
            complete_stock_days=10476263,
            unavailable_stock_days=182787,
            field_missing_counts={"daily": 181890},
            source_manifest_hashes=self.SOURCE_HASHES,
            output_dir=self.out_dir,
        )
        
        manifest_path = self.out_dir / "ds_test_005" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        content_hash = manifest.pop("manifest_content_hash")
        recomputed = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
        self.assertEqual(content_hash, recomputed)

    def test_retrieval_date_verified_requires_date(self):
        from backend.services.b3_protocol_types import DataSnapshotManifest
        
        with self.assertRaises(ValueError) as ctx:
            DataSnapshotManifest(
                snapshot_id="test",
                provider="mixed_vendor_tushare",
                retrieval_date=None,
                retrieval_date_status="verified",
                market_data_start=date(2016, 1, 4),
                market_data_end=date(2026, 7, 10),
                universe_snapshot_ids=(),
                semantic_hash="da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e",
                quality_status="ok",
                gaps=("availability_limited",),
            )
        self.assertIn("verified", str(ctx.exception).lower())

    def test_retrieval_date_unknown_requires_none(self):
        from backend.services.b3_protocol_types import DataSnapshotManifest
        
        with self.assertRaises(ValueError) as ctx:
            DataSnapshotManifest(
                snapshot_id="test",
                provider="mixed_vendor_tushare",
                retrieval_date=date(2026, 7, 14),
                retrieval_date_status="unknown",
                market_data_start=date(2016, 1, 4),
                market_data_end=date(2026, 7, 10),
                universe_snapshot_ids=(),
                semantic_hash="da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e",
                quality_status="ok",
                gaps=("availability_limited",),
            )
        self.assertIn("unknown", str(ctx.exception).lower())

    def test_v2_formal_manifest_rejects_universe_reference_as_snapshot(self):
        from backend.services.b3_protocol_types import DataSnapshotManifest

        with self.assertRaises(ValueError) as ctx:
            DataSnapshotManifest(
                snapshot_id="ds_test",
                provider="mixed_vendor_tushare",
                retrieval_date=None,
                retrieval_date_status="unknown",
                market_data_start=date(2016, 1, 4),
                market_data_end=date(2026, 7, 10),
                universe_snapshot_ids=("uref_traderlens_v2_shsz_sw2021_pit_001",),
                universe_reference_ids=("uref_traderlens_v2_shsz_sw2021_pit_001",),
                semantic_hash="da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e",
                quality_status="ok",
                gaps=("availability_limited",),
            )
        self.assertIn("universe_snapshot_ids", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
