"""
Task 8: Execution Observation Log Tests

Red line enforcement:
1. Draft never becomes log without explicit confirm/correct.
2. broker_verified is always False and cannot be set True.
3. No fabricated price/quantity — missing fields trigger needs_more_info.
4. Six test phrases use deterministic rules, zero LLM calls.
"""

import pytest
from datetime import datetime

from contracts.live_trade import (
    ExecutionInterpretationStatus,
    ExecutionObservationDraft,
    ExecutionObservationLog,
)
from backend.services.execution_interpreter import ExecutionInterpreter


@pytest.fixture
def interpreter():
    """Create interpreter instance."""
    return ExecutionInterpreter()


# Evidence chain IDs for testing
EVIDENCE = {
    "execution_card_id": "exec_card_001",
    "signal_id": "signal_001",
    "action_plan_id": "plan_001",
    "capital_context_id": "capital_001",
    "market_snapshot_id": "snapshot_001",
}


def test_bought_triggers_needs_more_info(interpreter):
    """我买了 → needs_more_info with price/quantity追问."""
    draft = interpreter.parse_user_feedback(
        raw_text="我买了",
        evidence_chain=EVIDENCE,
    )

    # Red line 1: only draft, never log
    assert isinstance(draft, ExecutionObservationDraft)
    assert draft.status == ExecutionInterpretationStatus.needs_more_info

    # Parsed action/status correct
    assert draft.parsed_action == "buy"
    assert draft.parsed_execution_status == "executed_full"

    # Red line 3: no fabricated data
    assert draft.parsed_price is None
    assert draft.parsed_quantity is None

    # White-talk follow-up question
    assert draft.follow_up_question is not None
    assert "价格" in draft.follow_up_question or "数量" in draft.follow_up_question
    assert set(draft.missing_fields) == {"parsed_price", "parsed_quantity"}

    # Evidence chain complete
    assert draft.execution_card_id == EVIDENCE["execution_card_id"]
    assert draft.signal_id == EVIDENCE["signal_id"]
    assert draft.action_plan_id == EVIDENCE["action_plan_id"]
    assert draft.capital_context_id == EVIDENCE["capital_context_id"]
    assert draft.market_snapshot_id == EVIDENCE["market_snapshot_id"]

    # Red line 2: broker_verified locked False
    assert draft.broker_verified is False

    # Red line 4: deterministic, zero LLM
    assert draft.interpretation_source == "deterministic"


def test_did_not_buy_skip(interpreter):
    """没买 → skipped, no追问."""
    draft = interpreter.parse_user_feedback(
        raw_text="没买",
        evidence_chain=EVIDENCE,
    )

    assert draft.status == ExecutionInterpretationStatus.draft_pending_confirmation
    assert draft.parsed_action == "none"
    assert draft.parsed_execution_status == "skipped"
    assert draft.parsed_price is None
    assert draft.parsed_quantity is None
    assert draft.follow_up_question is None
    assert draft.missing_fields == []
    assert draft.broker_verified is False
    assert draft.interpretation_source == "deterministic"


def test_only_bought_half_triggers_needs_more_info(interpreter):
    """只买了一半 → needs_more_info追问实际数量."""
    draft = interpreter.parse_user_feedback(
        raw_text="只买了一半",
        evidence_chain=EVIDENCE,
    )

    assert draft.status == ExecutionInterpretationStatus.needs_more_info
    assert draft.parsed_action == "buy"
    assert draft.parsed_execution_status == "executed_partial"
    assert draft.parsed_price is None
    assert draft.parsed_quantity is None
    assert draft.follow_up_question is not None
    assert "实际" in draft.follow_up_question or "多少" in draft.follow_up_question
    assert draft.broker_verified is False
    assert draft.interpretation_source == "deterministic"


def test_sold(interpreter):
    """卖了 → needs_more_info追问价格/数量."""
    draft = interpreter.parse_user_feedback(
        raw_text="卖了",
        evidence_chain=EVIDENCE,
    )

    assert draft.status == ExecutionInterpretationStatus.needs_more_info
    assert draft.parsed_action == "sell"
    assert draft.parsed_execution_status == "executed_full"
    assert draft.parsed_price is None
    assert draft.parsed_quantity is None
    assert draft.follow_up_question is not None
    assert draft.broker_verified is False
    assert draft.interpretation_source == "deterministic"


def test_forgot_to_execute(interpreter):
    """忘了执行 → forgot, reason recorded."""
    draft = interpreter.parse_user_feedback(
        raw_text="忘了执行",
        evidence_chain=EVIDENCE,
    )

    assert draft.status == ExecutionInterpretationStatus.draft_pending_confirmation
    assert draft.parsed_action == "none"
    assert draft.parsed_execution_status == "forgot"
    assert draft.parsed_reason == "忘了执行"
    assert draft.broker_verified is False
    assert draft.interpretation_source == "deterministic"


def test_price_too_high_did_not_chase(interpreter):
    """价格太高没追 → skipped with reason."""
    draft = interpreter.parse_user_feedback(
        raw_text="价格太高没追",
        evidence_chain=EVIDENCE,
    )

    assert draft.status == ExecutionInterpretationStatus.draft_pending_confirmation
    assert draft.parsed_action == "none"
    assert draft.parsed_execution_status == "skipped"
    assert "价格太高" in draft.parsed_reason
    assert draft.broker_verified is False
    assert draft.interpretation_source == "deterministic"


def test_draft_never_writes_logs_table(interpreter):
    """Red line 1: parsing never writes execution_observation_logs."""
    # This test verifies the contract — actual DB layer will enforce it
    draft = interpreter.parse_user_feedback(
        raw_text="我买了",
        evidence_chain=EVIDENCE,
    )

    # Verify draft is draft, not log
    assert isinstance(draft, ExecutionObservationDraft)
    assert not isinstance(draft, ExecutionObservationLog)


def test_no_market_snapshot_backfill_price(interpreter):
    """Red line 3: 我买了 must NOT backfill price from market_snapshot."""
    draft = interpreter.parse_user_feedback(
        raw_text="我买了",
        evidence_chain=EVIDENCE,
    )

    # Even though market_snapshot_id is present, parsed_price must be None
    assert draft.parsed_price is None
    assert draft.market_snapshot_id == EVIDENCE["market_snapshot_id"]


def test_broker_verified_guard_rejects_true():
    """Red line 2: any attempt to set broker_verified=True is rejected."""
    with pytest.raises(ValueError, match="broker_verified.*must.*False"):
        ExecutionObservationDraft(
            draft_id="draft_001",
            execution_card_id="exec_001",
            signal_id="sig_001",
            action_plan_id="plan_001",
            capital_context_id="cap_001",
            market_snapshot_id="snap_001",
            raw_user_text="test",
            parsed_action="buy",
            parsed_execution_status="executed_full",
            parsed_price=None,
            parsed_quantity=None,
            parsed_reason=None,
            missing_fields=[],
            follow_up_question=None,
            interpretation_source="deterministic",
            status=ExecutionInterpretationStatus.draft_pending_confirmation,
            broker_verified=True,  # ← this must be rejected
            created_at=datetime.now(),
        )


def test_all_six_phrases_zero_llm_calls(interpreter):
    """Red line 4: all six test phrases use deterministic rules, zero LLM."""
    phrases = [
        "我买了",
        "没买",
        "只买了一半",
        "卖了",
        "忘了执行",
        "价格太高没追",
    ]

    for phrase in phrases:
        draft = interpreter.parse_user_feedback(
            raw_text=phrase,
            evidence_chain=EVIDENCE,
        )
        # All must be deterministic (no LLM)
        assert draft.interpretation_source == "deterministic"
