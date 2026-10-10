from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
SOURCE_REL = Path(
    "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership"
)
SOURCE_MANIFEST_REL = SOURCE_REL / "manifest.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_partition(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def _fixture_repo(root: Path, *, rows_a: list[dict] | None = None, rows_b: list[dict] | None = None) -> tuple[Path, Path]:
    source = root / SOURCE_REL
    source.mkdir(parents=True)
    rows_a = rows_a or [{
        "ts_code": "000001.SZ", "l1_code": "801010.SI", "l1_name": "农林牧渔",
        "in_date": "20200101", "out_date": None, "is_new": "Y",
    }]
    rows_b = rows_b or [{
        "ts_code": "000002.SZ", "l1_code": "801020.SI", "l1_name": "采掘",
        "in_date": "20200101", "out_date": None, "is_new": "N",
    }]
    files = [
        ("SW2021_801010.SI_is_new_Y.parquet", "801010.SI", "农林牧渔", "Y", rows_a),
        ("SW2021_801020.SI_is_new_N.parquet", "801020.SI", "采掘", "N", rows_b),
    ]
    partitions = []
    for name, l1_code, l1_name, is_new, rows in files:
        path = source / name
        _write_partition(path, rows)
        partitions.append({
            "name": name,
            "l1_code": l1_code,
            "l1_name": l1_name,
            "src": "SW2021",
            "is_new": is_new,
            "row_count": len(rows),
            "sha256": _sha(path),
        })
    manifest = {
        "status": "collected_verified",
        "partition_count": len(partitions),
        "partitions": partitions,
    }
    manifest_path = source / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return root, manifest_path


class V3B5SourceInventoryTests(unittest.TestCase):
    def test_real_source_selects_exact_61_partitions_and_exact_hashes(self):
        from backend.services.v3_b5_source_inventory import publish_source_inventory, verify_source_inventory

        with tempfile.TemporaryDirectory() as tmp:
            result = publish_source_inventory(ROOT, Path(tmp))
            self.assertEqual(result["status"], "published")
            manifest = json.loads((Path(result["path"]) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["accepted_partition_count"], 61)
            self.assertEqual(manifest["accepted_row_count"], 7804)
            self.assertEqual(manifest["source_manifest_sha256"], "a38b3cc6be947b290078fe637466991ee8d13dee2794d398fb709d5c4c3826f3")
            self.assertTrue(all(part["name"].startswith("SW2021_") for part in manifest["partitions"]))
            for part in manifest["partitions"]:
                self.assertEqual(part["sha256"], _sha(ROOT / SOURCE_REL / part["name"]))
            verified = verify_source_inventory(ROOT, Path(result["path"]))
            self.assertEqual(verified["status"], "verified")

    def test_exact_v3_bindings_and_write_once(self):
        from backend.services.v3_b5_source_inventory import publish_source_inventory

        with tempfile.TemporaryDirectory() as tmp:
            fixture_root, manifest_path = _fixture_repo(Path(tmp) / "repo")
            out = Path(tmp) / "out"
            first = publish_source_inventory(
                fixture_root, out, source_manifest_rel=SOURCE_MANIFEST_REL,
                expected_source_manifest_sha256=_sha(manifest_path), expected_partition_count=2,
            )
            manifest = json.loads((Path(first["path"]) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["template"]["template_id"], "relative_strength_rotation_shsz_sw2021_v3")
            self.assertEqual(manifest["template"]["template_version"], "v3_shsz_sw2021_pit_12m_liquidity20d")
            self.assertEqual(manifest["strategy_revision_id"], "6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc")
            self.assertTrue(manifest["not_authorized_for_b6_oos_gate_promotion_signal"])
            second = publish_source_inventory(
                fixture_root, out, source_manifest_rel=SOURCE_MANIFEST_REL,
                expected_source_manifest_sha256=_sha(manifest_path), expected_partition_count=2,
            )
            self.assertEqual(second["status"], "already_published")
            target_manifest = Path(first["path"]) / "manifest.json"
            target_manifest.write_bytes(target_manifest.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "write-once"):
                publish_source_inventory(
                    fixture_root, out, source_manifest_rel=SOURCE_MANIFEST_REL,
                    expected_source_manifest_sha256=_sha(manifest_path), expected_partition_count=2,
                )

    def _assert_rejected(self, *, rows_a=None, rows_b=None, mutate=None, message=""):
        from backend.services.v3_b5_source_inventory import publish_source_inventory

        with tempfile.TemporaryDirectory() as tmp:
            repo, manifest_path = _fixture_repo(Path(tmp) / "repo", rows_a=rows_a, rows_b=rows_b)
            if mutate:
                mutate(manifest_path, manifest_path.parent)
            with self.assertRaisesRegex(ValueError, message or ".+"):
                publish_source_inventory(
                    repo, Path(tmp) / "out", source_manifest_rel=SOURCE_MANIFEST_REL,
                    expected_source_manifest_sha256=_sha(manifest_path), expected_partition_count=2,
                )

    def test_missing_required_l1_code_rejected(self):
        self._assert_rejected(
            rows_a=[{"ts_code": "000001.SZ", "in_date": "20200101", "out_date": None, "is_new": "Y"}],
            message="required fields",
        )

    def test_missing_effective_date_rejected(self):
        self._assert_rejected(
            rows_a=[{"ts_code": "000001.SZ", "l1_code": "801010.SI", "l1_name": "农林牧渔", "in_date": None, "out_date": None, "is_new": "Y"}],
            message="effective",
        )

    def test_declared_hash_mismatch_rejected(self):
        def mutate(_manifest_path, source):
            (source / "SW2021_801010.SI_is_new_Y.parquet").write_bytes(b"tampered")

        self._assert_rejected(mutate=mutate, message="hash mismatch")

    def test_missing_partition_rejected(self):
        def mutate(manifest_path, source):
            (source / "SW2021_801020.SI_is_new_N.parquet").unlink()

        self._assert_rejected(mutate=mutate, message="missing partition")

    def test_duplicate_identity_rejected(self):
        duplicate = {"ts_code": "000001.SZ", "l1_code": "801010.SI", "l1_name": "农林牧渔", "in_date": "20200101", "out_date": None, "is_new": "Y"}
        self._assert_rejected(rows_a=[duplicate, duplicate], message="duplicate identity")

    def test_overlapping_active_l1_codes_rejected(self):
        def mutate(manifest_path, source):
            path = source / "SW2021_801020.SI_is_new_N.parquet"
            _write_partition(path, [{"ts_code": "000001.SZ", "l1_code": "801020.SI", "l1_name": "采掘", "in_date": "20200102", "out_date": None, "is_new": "N"}])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["partitions"][1]["row_count"] = 1
            manifest["partitions"][1]["sha256"] = _sha(path)
            manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

        self._assert_rejected(mutate=mutate, message="overlapping")

    def test_verifier_rejects_source_tamper(self):
        from backend.services.v3_b5_source_inventory import publish_source_inventory, verify_source_inventory

        with tempfile.TemporaryDirectory() as tmp:
            repo, manifest_path = _fixture_repo(Path(tmp) / "repo")
            result = publish_source_inventory(
                repo, Path(tmp) / "out", source_manifest_rel=SOURCE_MANIFEST_REL,
                expected_source_manifest_sha256=_sha(manifest_path), expected_partition_count=2,
            )
            (manifest_path.parent / "SW2021_801010.SI_is_new_Y.parquet").write_bytes(b"tampered")
            verified = verify_source_inventory(
                repo, Path(result["path"]), source_manifest_rel=SOURCE_MANIFEST_REL,
                expected_source_manifest_sha256=_sha(manifest_path), expected_partition_count=2,
            )
            self.assertEqual(verified["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
