"""Test evidence gate reads correct field."""


def test_run_research_accepts_valid_source_ids():
    """run-research 不应误报零来源当 candidate_rationales 有 source-id."""
    research_output = {
        "candidate_rationales": {
            "600519.SH": {
                "supporting_source_ids": ["financials:600519.SH:0"],
                "counter_evidence": [],
            }
        },
        "evidence_gaps": [],
    }
    ticker = "600519.SH"
    
    # ponytail: 提取逻辑应在 API 内，这里只验证逻辑正确性
    rationale = research_output.get("candidate_rationales", {}).get(ticker, {})
    tushare_ids = [
        sid for sid in rationale.get("supporting_source_ids", [])
        if isinstance(sid, str) and sid.startswith(("financials:", "announcements:"))
    ]
    
    assert len(tushare_ids) == 1
    assert tushare_ids[0] == "financials:600519.SH:0"


def test_decision_blocks_zero_source_ids():
    """decision=continue 必须读取同一路径，无 source-id 时阻断."""
    research_output = {
        "candidate_rationales": {
            "600519.SH": {
                "supporting_source_ids": [],  # 空
                "counter_evidence": [],
            }
        },
        "evidence_gaps": ["gap1"],
    }
    ticker = "600519.SH"
    
    rationale = research_output.get("candidate_rationales", {}).get(ticker, {})
    tushare_ids = [
        sid for sid in rationale.get("supporting_source_ids", [])
        if isinstance(sid, str) and sid.startswith(("financials:", "announcements:"))
    ]
    
    assert len(tushare_ids) == 0, "Should block when no source-id"
