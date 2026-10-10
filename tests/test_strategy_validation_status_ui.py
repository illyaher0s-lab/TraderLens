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
