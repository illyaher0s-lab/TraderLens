from pathlib import Path


ROOT = Path(__file__).parent.parent


def test_validation_page_uses_independent_non_actionable_status_card():
    card = (ROOT / "frontend" / "components" / "StrategyValidationStatusCard.tsx").read_text(
        encoding="utf-8"
    )
    page = (ROOT / "frontend" / "app" / "strategy-validations" / "page.tsx").read_text(
        encoding="utf-8"
    )

    assert "StrategyValidationStatusCard" in card
    assert "actionable" in card
    assert "无信号" in card
    assert "不能作为买卖依据" in card
    assert "<button" not in card
    assert "Action Plan" not in card
    assert "StrategyValidationStatusCard" in page


def test_510880_research_links_to_fail_closed_entry_judgement():
    home = (ROOT / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")
    page = (ROOT / "frontend" / "app" / "strategy-validations" / "page.tsx").read_text(
        encoding="utf-8"
    )

    assert "/strategy-validations?symbol=510880.SH" in home
    assert "收益差不能当跟踪误差" in home
    assert "成本与历史估值判断缺少比较依据" in home
    assert "当前未确认 510880 合格策略" in page
    assert "资格资料不可核" in page
    assert "观察／不交易" in page
    assert "核验日期未知" in page
    assert "自主成交" in page
    assert "/trades/record" in page
    assert "/observations" in page
    assert 'status?.status === "watch"' in page
    assert 'status?.status === "unavailable"' in page
    assert "本页未提供正式入场信号" in page


def test_isolated_browser_mode_labels_old_research_and_synthetic_trades():
    nav = (ROOT / "frontend" / "components" / "TopNav.tsx").read_text(
        encoding="utf-8"
    )

    assert "NEXT_PUBLIC_CARD019_ISOLATED_TEST" in nav
    assert "2026-10-16 历史研究回放，研究待核" in nav
    assert "合成测试成交" in nav
    assert "不代表实时行情" in nav
