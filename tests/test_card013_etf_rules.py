import backend.services.data_tools as data_tools


def _required_rule(name):
    rule = getattr(data_tools, name, None)
    assert callable(rule), f"missing deterministic ETF rule: {name}"
    return rule


def test_etf_category_uses_fund_type_and_full_benchmark_specificity():
    classify = _required_rule("_classify_etf_category")

    assert classify("股票型", "沪深300指数×100%") == "broad"
    assert classify("股票型", "上交所上证红利指数×100%") == "dividend"
    assert classify("股票型", "沪深300医药卫生指数×100%") == "industry"
    assert classify("股票型", "中证全指证券公司指数×100%") == "industry"
    assert classify("其他", "国内黄金现货价格收益率(Au99.99合约)×100%") == "other"
    assert classify("混合型", "沪深300指数×100%") == "other"
    assert classify("股票型", "未识别基准") == "unclassified"


def test_etf_valuation_rule_requires_exact_core_and_uses_frozen_directions():
    decide = _required_rule("_etf_valuation_conclusion")

    cheap = decide("broad", pe_percentile=15.0, pb_percentile=20.0)
    assert cheap["status"] == "conclusive"
    assert cheap["verdict"] == "research_positive"
    assert cheap["label"] == "相对偏便宜"

    expensive = decide("broad", pe_percentile=80.0, pb_percentile=90.0)
    assert expensive["verdict"] == "research_reject"
    assert expensive["label"] == "相对偏贵"

    conflict = decide("broad", pe_percentile=10.0, pb_percentile=90.0)
    assert conflict["verdict"] == "research_watch"
    assert conflict["status"] == "conclusive"
    assert "冲突" in conflict["message"]

    missing = decide("broad", pe_percentile=10.0, pb_percentile=None)
    assert missing["status"] == "data_gap"
    assert missing["verdict"] == "research_unavailable"


def test_dividend_history_is_explicit_substitute_but_sector_and_other_do_not_borrow():
    decide = _required_rule("_etf_valuation_conclusion")

    dividend = decide(
        "dividend", pe_percentile=None, pb_percentile=None,
        dividend_yield_percentile=80.0,
    )
    assert dividend["status"] == "conclusive"
    assert dividend["verdict"] == "research_positive"
    assert dividend["basis"] == "own_dividend_yield"
    assert "自身" in dividend["message"]
    assert "不等同于指数估值" in dividend["message"]

    industry = decide("industry", pe_percentile=None, pb_percentile=None)
    assert industry["status"] == "data_gap"
    assert industry["verdict"] == "research_unavailable"
    assert industry["message"] == "跟踪指数的估值数据未覆盖，暂不提供估值判断"

    other = decide("other", pe_percentile=None, pb_percentile=None)
    assert other["status"] == "not_supported"
    assert other["verdict"] == "research_unavailable"
    assert other["message"] == "该类型暂不提供估值判断"
