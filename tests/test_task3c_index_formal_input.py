"""Task 3C-Index: Formal execution partition input-index preview."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def make_minimal_root(root: Path):
    """ponytail: 7接口全造空"""
    for iface in ["daily", "daily_basic", "adj_factor", "stk_limit", "suspend_d", "stock_st", "trade_cal"]:
        (root / iface).mkdir()


class TestFormalInputIndexBuilder(unittest.TestCase):
    """RED: builder计算interface content hash"""
    
    def test_001_single_file_deterministic_hash(self):
        """单文件interface → 确定性hash"""
        from backend.services.formal_input_index import build_input_index
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            make_minimal_root(root)
            part_dir = root / "daily" / "trade_date=20160104"
            part_dir.mkdir()
            (part_dir / "part.parquet").write_bytes(b"fake_data")
            
            idx = build_input_index(root)
            
            self.assertIn("daily", idx["interfaces"])
            daily = idx["interfaces"]["daily"]
            self.assertEqual(len(daily["entries"]), 1)
            self.assertEqual(daily["entries"][0]["path"], "daily/trade_date=20160104/part.parquet")
            self.assertIsNotNone(daily["interface_content_hash"])
    
    def test_002_tampered_file_rejected_by_verifier(self):
        """单文件内容篡改 → verifier拒绝"""
        from backend.services.formal_input_index import build_input_index, verify_input_index
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            make_minimal_root(root)
            part_dir = root / "daily" / "trade_date=20160104"
            part_dir.mkdir()
            fpath = part_dir / "part.parquet"
            fpath.write_bytes(b"original")
            
            idx = build_input_index(root)
            
            # 篡改
            fpath.write_bytes(b"tampered")
            
            result = verify_input_index(idx, root)
            self.assertFalse(result["is_valid"])
            self.assertIn("hash", result["error"].lower())
    
    def test_003_missing_interface_fails_loud(self):
        """缺失必需接口 → 拒绝"""
        from backend.services.formal_input_index import build_input_index
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # ponytail: 7接口全需要
            for iface in ["daily", "adj_factor", "stk_limit", "suspend_d", "stock_st", "trade_cal"]:
                (root / iface).mkdir()
            # 缺 daily_basic
            
            with self.assertRaises(ValueError) as ctx:
                build_input_index(root)
            self.assertIn("missing", str(ctx.exception).lower())


class TestFormalInputIndexVerifier(unittest.TestCase):
    """RED: verifier独立重算hash"""
    
    def test_011_missing_file_rejected(self):
        """缺失文件 → 拒绝"""
        from backend.services.formal_input_index import build_input_index, verify_input_index
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            make_minimal_root(root)
            part_dir = root / "daily" / "trade_date=20160104"
            part_dir.mkdir()
            fpath = part_dir / "part.parquet"
            fpath.write_bytes(b"data")
            
            idx = build_input_index(root)
            
            # 删除
            fpath.unlink()
            
            result = verify_input_index(idx, root)
            self.assertFalse(result["is_valid"])
            self.assertIn("missing", result["error"].lower())
    
    def test_012_extra_file_rejected(self):
        """额外未登记文件 → 拒绝"""
        from backend.services.formal_input_index import build_input_index, verify_input_index
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            make_minimal_root(root)
            part_dir = root / "daily" / "trade_date=20160104"
            part_dir.mkdir()
            (part_dir / "part.parquet").write_bytes(b"data")
            
            idx = build_input_index(root)
            
            # 添加额外文件
            (part_dir / "extra.parquet").write_bytes(b"extra")
            
            result = verify_input_index(idx, root)
            self.assertFalse(result["is_valid"])
            self.assertIn("extra", result["error"].lower())
    
    def test_013_tampered_byte_size_rejected(self):
        """篡改 byte_size → 拒绝"""
        from backend.services.formal_input_index import build_input_index, verify_input_index
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            make_minimal_root(root)
            part_dir = root / "daily" / "trade_date=20160104"
            part_dir.mkdir()
            (part_dir / "part.parquet").write_bytes(b"data")
            
            idx = build_input_index(root)
            idx["interfaces"]["daily"]["entries"][0]["byte_size"] = 9999
            
            result = verify_input_index(idx, root)
            self.assertFalse(result["is_valid"])
            self.assertIn("size", result["error"].lower())
    
    def test_014_tampered_interface_hash_rejected(self):
        """篡改 interface_content_hash → 拒绝"""
        from backend.services.formal_input_index import build_input_index, verify_input_index
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            make_minimal_root(root)
            part_dir = root / "daily" / "trade_date=20160104"
            part_dir.mkdir()
            (part_dir / "part.parquet").write_bytes(b"data")
            
            idx = build_input_index(root)
            idx["interfaces"]["daily"]["interface_content_hash"] = "tampered"
            
            result = verify_input_index(idx, root)
            self.assertFalse(result["is_valid"])
            self.assertIn("interface", result["error"].lower())
    
    def test_021_real_formal_root_preview(self):
        """真实formal root → 完整扫描"""
        from backend.services.formal_input_index import build_input_index, verify_input_index
        import time
        
        real_root = REPO_ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
        if not real_root.exists():
            self.skipTest("Real formal root not found")
        
        start = time.time()
        idx = build_input_index(real_root)
        build_time = time.time() - start
        
        # 7接口+绑定
        expected = ["daily", "daily_basic", "adj_factor", "stk_limit", "suspend_d", "stock_st", "trade_cal"]
        for iface in expected:
            self.assertIn(iface, idx["interfaces"])
            self.assertGreater(len(idx["interfaces"][iface]["entries"]), 0)
        
        self.assertIn("bindings", idx)
        self.assertIn("ds_traderlens_v2_shsz_pit_001", idx["bindings"])
        self.assertIn("input_index_hash", idx)
        
        start = time.time()
        result = verify_input_index(idx, real_root)
        verify_time = time.time() - start
        
        self.assertTrue(result["is_valid"], f"Failed: {result['error']}")
        total = sum(len(iface["entries"]) for iface in idx["interfaces"].values())
        print(f"\n{total} files, build {build_time:.1f}s, verify {verify_time:.1f}s")


if __name__ == "__main__":
    unittest.main()

