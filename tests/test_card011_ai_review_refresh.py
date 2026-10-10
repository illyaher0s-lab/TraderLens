from datetime import datetime
import json

import pytest

from backend.db.live_trade import LiveTradeDB
from backend.services.discipline_review import DisciplineReviewService
from backend.services.llm_client import LLMCallResult
from contracts.live_trade import ExecutionObservationLog, TradeType


VALID_REVIEW = (
    "结果：本次交易为盈利，费用仍为估算。"
    "计划：未记录事前退出计划，无法判断是否按计划执行。"
    "建议：下一笔交易建立前先写明止损条件和目标退出条件。"
)


def _review_inputs():
    buy = ExecutionObservationLog(
        log_id="buy_card011", draft_id=None, execution_card_id=None,
        signal_id=None, action_plan_id=None, capital_context_id=None,
        market_snapshot_id=None, confirmed_action="buy",
        confirmed_execution_status="executed_full", confirmed_price=10,
        confirmed_quantity=100, reason="分批布局10%", confirmed_by_user=True,
        broker_verified=False, confirmed_at=datetime(2026, 10, 1),
        trade_type=TradeType.actual, record_source="autonomous_manual",
        operation_id="buy-operation-card011", operation_fingerprint="buy-fingerprint-card011",
    )
    sell = ExecutionObservationLog(
        log_id="sell_card011", draft_id=None, execution_card_id=None,
        signal_id=None, action_plan_id=None, capital_context_id=None,
        market_snapshot_id=None, confirmed_action="sell",
        confirmed_execution_status="executed_full", confirmed_price=11,
        confirmed_quantity=100, reason="回落3%", confirmed_by_user=True,
        broker_verified=False, confirmed_at=datetime(2026, 10, 2),
        trade_type=TradeType.actual, record_source="autonomous_manual",
        operation_id="sell-operation-card011", operation_fingerprint="sell-fingerprint-card011",
    )
    review = DisciplineReviewService().create_review(
        position_id="position_card011", execution_card_id=None, signal_id=None,
        daily_signal_ids=[], buy_log=buy, sell_log=sell,
        execution_rule_status="actual_recorded",
    )
    return review, buy, sell


def test_ai_review_accepts_three_sentences_for_result_plan_and_advice():
    accepted, reason = DisciplineReviewService._validate_ai_review_text_with_reason(VALID_REVIEW)

    assert accepted == VALID_REVIEW
    assert reason == "accepted"


def test_ai_review_accepts_five_sentences_with_plan_evaluation():
    narrative = (
        "结果：本次交易持平。"
        "计划：价格条件达到已记录目标价。"
        "实际触发过程仍未核实。"
        "分红情况仍待核实。"
        "建议：下一笔交易建立前先写明退出条件。"
    )

    accepted, reason = DisciplineReviewService._validate_ai_review_text_with_reason(narrative)

    assert accepted == narrative
    assert reason == "accepted"


@pytest.mark.parametrize(
    ("narrative", "expected_reason"),
    [
        (
            "结果：本次盈利为10元。计划：未记录退出计划。建议：下一笔先写明退出条件。",
            "numeric_content",
        ),
        (
            "结果：市场变化带来盈利。计划：已记录。建议：下一笔先写明退出条件。",
            "forbidden_content",
        ),
        (
            "结果：本次交易持平。计划：未记录。实际过程未知。分红待核实。"
            "另有信息缺失。建议：下一笔先写明退出条件。",
            "sentence_count",
        ),
        (
            "结果：本次交易持平。计划：未记录。建议：下一笔先写明第1项退出条件。",
            "numeric_content",
        ),
        (
            "结果：本次交易持平。计划：未记录。建议：下一笔先设定收益目标20%。",
            "numeric_content",
        ),
        (
            "结果：本次交易持平。计划：未记录。建议：下一笔先写明０项退出条件。",
            "numeric_content",
        ),
    ],
)
def test_ai_review_keeps_numeric_market_and_sentence_count_guards(narrative, expected_reason):
    accepted, reason = DisciplineReviewService._validate_ai_review_text_with_reason(narrative)

    assert accepted is None
    assert reason == expected_reason


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(12.0, "盈利"), (-12.0, "亏损"), (0.0, "持平"), (None, "未知")],
)
def test_ai_outcome_category_uses_deterministic_net_result(amount, expected):
    assert DisciplineReviewService._ai_outcome_category(amount) == expected


@pytest.mark.parametrize(
    ("status", "expected_phrase"),
    [
        ("target_met", "达到已记录目标价"),
        ("target_not_met", "未达到已记录目标价"),
        ("no_plan", "无法判断是否按计划执行"),
        ("retrospective_price_comparison", "计划为事后记录，不能据此判定"),
    ],
)
def test_ai_plan_conclusion_is_projected_from_deterministic_status(status, expected_phrase):
    conclusion = DisciplineReviewService._ai_plan_conclusion(status)

    assert expected_phrase in conclusion
    assert not any(character.isdigit() for character in conclusion)


def _response(text, retry_count=0):
    return LLMCallResult(
        {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"},
        {
            "status": "success", "response_received": True,
            "attempt_count": retry_count + 1, "timeout": retry_count > 0,
            "attempts": [],
        },
    )


class _SequenceClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create_message(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_ai_review_retries_once_for_digits_and_tracks_network_retries_separately():
    review, buy, sell = _review_inputs()
    first = _response("结果：本次盈利10元。计划：未记录退出计划。建议：下一笔先写明退出条件。", retry_count=2)
    second = _response(VALID_REVIEW)
    client = _SequenceClient([first, second])

    text, status, diagnostic = DisciplineReviewService().generate_ai_review_with_diagnostic(
        review, buy, sell, client,
    )

    assert (text, status) == (VALID_REVIEW, "available")
    assert len(client.calls) == 2
    assert diagnostic["format_retry_count"] == 1
    assert diagnostic["format_retry_reason"] == "numeric_content"
    assert [item["retry_count"] for item in diagnostic["provider_diagnostics"]] == [2, 0]
    assert "上一轮" in client.calls[1]["system"]
    for call in client.calls:
        payload_text = call["messages"][0]["content"]
        assert not any(character.isdigit() for character in payload_text)
        assert not any(character.isdigit() for character in call["system"])
    payload = json.loads(client.calls[0]["messages"][0]["content"])
    assert payload["result"]["outcome_category"] == DisciplineReviewService._ai_outcome_category(
        review.pnl_record.pnl_amount,
    )
    assert payload["plan_discipline"]["conclusion"] == DisciplineReviewService._ai_plan_conclusion("no_plan")
    assert "具体数值已省略" in payload["user_reasons"]["buy"]


def test_ai_review_degrades_after_two_numeric_generation_attempts():
    review, buy, sell = _review_inputs()
    client = _SequenceClient([
        _response("结果：盈利10元。计划：未记录。建议：下一笔先写计划。"),
        _response("结果：盈利0元。计划：未记录。建议：下一笔先写计划。"),
    ])

    text, status, diagnostic = DisciplineReviewService().generate_ai_review_with_diagnostic(
        review, buy, sell, client,
    )

    assert text is None
    assert status == "unavailable"
    assert len(client.calls) == 2
    assert diagnostic["format_retry_count"] == 1
    assert diagnostic["validation_reason"] == "numeric_content"


def test_refreshing_ai_text_preserves_deterministic_review_fields(tmp_path):
    review, _, _ = _review_inputs()
    db = LiveTradeDB(tmp_path / "live_trade.db")
    db.save_discipline_review(review)
    before = db.get_discipline_review(review.review_id)
    db.update_discipline_review_ai_text(review.review_id, VALID_REVIEW)
    after = db.get_discipline_review(review.review_id)

    assert after is not None
    assert after.ai_review_text == VALID_REVIEW
    assert after.ai_review_status == "available"
    assert after.model_dump(mode="json") == before.model_copy(update={
        "ai_review_text": VALID_REVIEW,
        "ai_review_status": "available",
    }).model_dump(mode="json")

    with pytest.raises(ValueError, match="must not contain digits"):
        db.update_discipline_review_ai_text(review.review_id, VALID_REVIEW + "0")
    assert db.get_discipline_review(review.review_id) == after
