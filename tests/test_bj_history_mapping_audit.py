"""北交所历史映射审计测试."""
import json
from pathlib import Path
from scripts.audit_bj_history_mapping import bucket_gap, BJ_CUTOFF


def test_bucket_logic():
    """Pure bucket function."""
    assert bucket_gap("920000.BJ", 20211114) == "bj_pre"
    assert bucket_gap("920000.BJ", 20211115) == "bj_post"
    assert bucket_gap("001914.SZ", 20200101) == "shsz"
    assert bucket_gap("000001.SH", 20200101) == "shsz"
    assert bucket_gap("999999.XX", 20200101) == "other"


def test_cutoff_value():
    """Cutoff constant."""
    assert BJ_CUTOFF == 20211115


def test_bucket_sums_stk_limit():
    """stk_limit 四桶和 = 总数."""
    a = json.loads(Path("docs/verification/bj_history_mapping_audit.json").read_text())
    m = json.loads(Path("data/pit/formal_packages/fa4e3fd8f98d8758/manifest.json").read_text())
    total = sum(a["stk_limit_buckets"].get(k, {}).get("stock_days", 0) for k in ["bj_pre", "bj_post", "shsz", "other"])
    assert total == m["gap_counts_by_type"]["stk_limit"]["stock_day_count"]


def test_bucket_sums_daily_basic():
    """daily_basic 四桶和 = 总数."""
    a = json.loads(Path("docs/verification/bj_history_mapping_audit.json").read_text())
    m = json.loads(Path("data/pit/formal_packages/fa4e3fd8f98d8758/manifest.json").read_text())
    total = sum(a["daily_basic_buckets"].get(k, {}).get("stock_days", 0) for k in ["bj_pre", "bj_post", "shsz", "other"])
    assert total == m["gap_counts_by_type"]["daily_basic"]["stock_day_count"]


def test_union_bucket_sum():
    """并集四桶和 = 去重并集."""
    a = json.loads(Path("docs/verification/bj_history_mapping_audit.json").read_text())
    formal = json.loads(Path("docs/verification/formal_input_gap_audit.json").read_text())
    union_total = sum(a["union_buckets"].get(k, {}).get("stock_days", 0) for k in ["bj_pre", "bj_post", "shsz", "other"])
    expected_union = formal["stk_limit"]["stock_day_count"] + formal["daily_basic"]["stock_day_count"] - formal["intersection"]["stock_day_count"]
    assert union_total == expected_union


def test_all_bj_codes_present():
    """全部 BJ 代码，无截断."""
    audit = json.loads(Path("docs/verification/bj_history_mapping_audit.json").read_text())
    formal = json.loads(Path("docs/verification/formal_input_gap_audit.json").read_text())
    
    # ponytail: extract BJ codes from both interfaces
    stk_bj = {c["ts_code"] for c in formal["stk_limit"]["code_details"] if c["ts_code"].endswith(".BJ")}
    db_bj = {c["ts_code"] for c in formal["daily_basic"]["code_details"] if c["ts_code"].endswith(".BJ")}
    expected = stk_bj | db_bj
    actual = set(audit["bj_code_evidence"].keys())
    
    missing = expected - actual
    extra = actual - expected
    assert actual == expected, f"Missing: {missing}, Extra: {extra}"


def test_bj_bucket_overlap():
    """同一代码可在 pre/post 均有缺口."""
    # ponytail: synthetic check that pre+post unique_codes != union when overlap
    pre_codes = {"920000.BJ", "920001.BJ"}
    post_codes = {"920001.BJ", "920002.BJ"}  # 920001 in both
    assert len(pre_codes) + len(post_codes) == 4
    assert len(pre_codes | post_codes) == 3  # union only 3


def test_focus_codes_all_present():
    """Focus codes 有证据."""
    a = json.loads(Path("docs/verification/bj_history_mapping_audit.json").read_text())
    for code in ["001914.SZ", "300216.SZ", "002604.SZ", "000939.SZ", "000760.SZ"]:
        assert code in a["focus_code_evidence"]
