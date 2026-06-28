from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_CLIENT = ROOT / "frontend" / "lib" / "api-client.ts"
SIGNALS_PAGE = ROOT / "frontend" / "app" / "signals" / "page.tsx"
SIGNAL_DETAIL_PAGE = ROOT / "frontend" / "app" / "signals" / "[signal_id]" / "page.tsx"


def test_frontend_planned_signal_includes_admission_metadata():
    source = API_CLIENT.read_text(encoding="utf-8")

    assert "strategy_revision_id: string | null" in source
    assert "lifecycle_state_at_generation: string | null" in source
    assert "admission_source: string | null" in source


def test_signal_board_visible_copy_has_decision_boundary_disclaimer():
    list_source = SIGNALS_PAGE.read_text(encoding="utf-8")
    detail_source = SIGNAL_DETAIL_PAGE.read_text(encoding="utf-8")

    required_phrases = [
        "不是买卖建议",
        "不会自动交易",
        "仅显示已通过验证的计划信号",
    ]

    combined = list_source + "\n" + detail_source
    for phrase in required_phrases:
        assert phrase in combined, f"Missing required phrase: {phrase}"


def test_signal_board_visible_copy_has_no_profit_or_live_trading_claims():
    combined = (
        SIGNALS_PAGE.read_text(encoding="utf-8")
        + "\n"
        + SIGNAL_DETAIL_PAGE.read_text(encoding="utf-8")
    )

    forbidden = [
        "保证盈利",
        "稳定盈利",
        "实盘可用",
        "立即买入",
        "立即卖出",
        "推荐买入",
        "推荐卖出",
        "最佳策略",
        "一键下单",
        "策略排名",
        "支持自动交易",
        "开启自动交易",
        "自动交易已启用",
        "一键自动交易",
        "可自动交易",
        "自动执行交易",
    ]

    for phrase in forbidden:
        assert phrase not in combined, f"Forbidden phrase found: {phrase}"
