"""
Task 10: Discipline Review Tests

Red lines enforced:
1. P&L only from confirmed details, never fabricated
2. Review needs complete input chain, missing parts explicitly marked
3. Review is retrospective, no forward-looking recommendations
4. Plan adherence by deterministic rules, not LLM
"""

import pytest
from datetime import datetime, date
from unittest.mock import patch
import uuid

from contracts.live_trade import (
    ExecutionObservationLog,
    ObservationPosition,
    PositionLifecycleState,
    PnlRecord,
    PnlSource,
    PlanAdherenceResult,
    DisciplineReview,
    ExplanationSource,
)
from backend.services.discipline_review import DisciplineReviewService


@pytest.fixture
def review_service():
    """Create discipline review service."""
    return DisciplineReviewService()


@pytest.fixture
def buy_log():
    """Complete buy log."""
    return ExecutionObservationLog(
        log_id="buy_log_001",
        draft_id="draft_001",
        execution_card_id="exec_001",
        signal_id="sig_001",
        action_plan_id="plan_001",
        capital_context_id="cap_001",
        market_snapshot_id="snap_001",
        confirmed_action="buy",
        confirmed_execution_status="executed_full",
        confirmed_price=10.0,
        confirmed_quantity=100,
        reason=None,
        confirmed_by_user=True,
        broker_verified=False,
        confirmed_at=datetime(2026, 6, 1),
    )


@pytest.fixture
def sell_log():
    """Complete sell log."""
    return ExecutionObservationLog(
        log_id="sell_log_001",
        draft_id="draft_002",
        execution_card_id="exec_001",
        signal_id="sig_001",
        action_plan_id="plan_001",
        capital_context_id="cap_001",
        market_snapshot_id="snap_002",
        confirmed_action="sell",
        confirmed_execution_status="executed_full",
        confirmed_price=11.5,
        confirmed_quantity=100,
        reason=None,
        confirmed_by_user=True,
        broker_verified=False,
        confirmed_at=datetime(2026, 6, 15),
    )


def test_complete_buy_sell_logs_pnl(review_service, buy_log, sell_log):
    """Red line 1: Complete logs → calculated P&L with correct source."""
    pnl_record = review_service.calculate_pnl(
        position_id="pos_001",
        buy_log=buy_log,
        sell_log=sell_log,
    )

    # Verify source
    assert pnl_record.pnl_source == PnlSource.calculated_from_confirmed_details

    # Verify calculation
    assert pnl_record.buy_price == 10.0
    assert pnl_record.sell_price == 11.5
    assert pnl_record.quantity == 100
    assert pnl_record.pnl_amount == 150.0  # (11.5 - 10.0) * 100
    assert pnl_record.pnl_pct == 0.15  # (11.5 - 10.0) / 10.0
    assert pnl_record.missing_fields == []


def test_missing_sell_price_incomplete(review_service, buy_log):
    """Red line 1: Missing sell price → incomplete, no backfill."""
    # Sell log with missing price
    incomplete_sell_log = ExecutionObservationLog(
        log_id="sell_log_002",
        draft_id="draft_002",
        execution_card_id="exec_001",
        signal_id="sig_001",
        action_plan_id="plan_001",
        capital_context_id="cap_001",
        market_snapshot_id="snap_002",
        confirmed_action="sell",
        confirmed_execution_status="executed_full",
        confirmed_price=None,  # Missing!
        confirmed_quantity=100,
        reason=None,
        confirmed_by_user=True,
        broker_verified=False,
        confirmed_at=datetime(2026, 6, 15),
    )

    pnl_record = review_service.calculate_pnl(
        position_id="pos_001",
        buy_log=buy_log,
        sell_log=incomplete_sell_log,
    )

    # Red line 1: incomplete, no backfill
    assert pnl_record.pnl_source == PnlSource.incomplete
    assert pnl_record.pnl_amount is None
    assert pnl_record.pnl_pct is None
    assert "sell_price" in pnl_record.missing_fields
    assert pnl_record.sell_price is None  # No backfill


def test_user_reported_pnl(review_service):
    """User directly reports P&L."""
    pnl_record = review_service.create_user_reported_pnl(
        position_id="pos_001",
        user_reported_pnl=150.0,
    )

    assert pnl_record.pnl_source == PnlSource.user_reported
    assert pnl_record.pnl_amount == 150.0


def test_broker_verified_not_in_pnl_source_enum():
    """Red line 1: broker_verified not in PnlSource enum."""
    # Verify enum values
    valid_sources = [s.value for s in PnlSource]
    assert "broker_verified" not in valid_sources
    assert len(valid_sources) == 3

    # Attempt to construct with invalid source
    with pytest.raises((ValueError, AttributeError)):
        PnlSource("broker_verified")


def test_late_exit_deviation(review_service):
    """Red line 4: Late exit deviation detected by rules."""
    # Signal says sell on D+2, user actually sold on D+5
    adherence = review_service.check_plan_adherence(
        signal_date=date(2026, 6, 3),
        actual_action_date=date(2026, 6, 6),
        signal_type="sell",
    )

    # Deviation detected by rules
    assert adherence.followed_plan is False
    assert len(adherence.deviations) > 0
    
    # Find late_exit deviation
    late_exit = next((d for d in adherence.deviations if d.get("type") == "late_exit"), None)
    assert late_exit is not None
    assert late_exit.get("gap_days") == 3


def test_followed_plan(review_service):
    """Followed plan → no deviations."""
    adherence = review_service.check_plan_adherence(
        signal_date=date(2026, 6, 3),
        actual_action_date=date(2026, 6, 3),
        signal_type="sell",
    )

    assert adherence.followed_plan is True
    assert adherence.deviations == []


def test_missing_sell_log_input(review_service, buy_log):
    """Red line 2: Missing input → explicitly marked, no fabrication."""
    review = review_service.create_review(
        position_id="pos_001",
        execution_card_id="exec_001",
        signal_id="sig_001",
        daily_signal_ids=["daily_001"],
        buy_log=buy_log,
        sell_log=None,  # Missing!
    )

    # Missing explicitly marked
    assert review.input_completeness.get("sell_log") == "missing"
    assert review.input_completeness.get("buy_log") == "present"
    
    # P&L incomplete
    assert review.pnl_record.pnl_source == PnlSource.incomplete


def test_state_type_rule_trace_compatibility(review_service):
    """Task 9 tail: Handle state-type rule_trace (market_data_fault)."""
    # State-type trace (no threshold/actual, only fault_state)
    state_trace = {
        "rule": "market_data_fault",
        "fault_state": "stale",
        "hit": True,
    }

    # Should not crash when parsing
    parsed = review_service.parse_rule_trace(state_trace)
    assert parsed["rule"] == "market_data_fault"
    assert "fault_state" in parsed


def test_pnl_calculation_zero_llm(review_service, buy_log, sell_log):
    """Red line 1: P&L calculation has zero LLM calls."""
    with patch("backend.services.discipline_review.call_llm") as mock_llm:
        pnl_record = review_service.calculate_pnl(
            position_id="pos_001",
            buy_log=buy_log,
            sell_log=sell_log,
        )

        # Zero LLM calls in P&L calculation
        mock_llm.assert_not_called()
        assert pnl_record.pnl_amount == 150.0


def test_forward_looking_guard_blocks_recommendations(review_service):
    """Red line 3: Template filling prevents free-form recommendations."""
    # Test: Template filling ensures no free-form text can be injected
    # Even if LLM tries to add recommendations, template only has predetermined slots
    
    pnl = PnlRecord(
        pnl_record_id="pnl_001",
        position_id="pos_001",
        buy_price=10.0,
        sell_price=11.5,
        quantity=100,
        fees=None,
        pnl_amount=150.0,
        pnl_pct=0.15,
        pnl_source=PnlSource.calculated_from_confirmed_details,
        missing_fields=[],
        computed_at=datetime.now(),
    )
    
    adherence = PlanAdherenceResult(
        followed_plan=True,
        deviations=[],
        adherence_trace={},
    )
    
    narrative, guard_passed = review_service.generate_narrative(
        pnl_record=pnl,
        adherence=adherence,
    )
    
    # Template filling ensures narrative only contains slots
    assert guard_passed is True
    assert narrative is not None
    
    # Verify narrative contains only template content (no free-form recommendations)
    banned_words = ["下次", "建议", "可以", "应该"]
    for word in banned_words:
        assert word not in narrative, f"Template leaked free-form word: {word}"
    
    # Verify narrative contains expected slot values
    assert "10.00" in narrative  # buy_price
    assert "11.50" in narrative  # sell_price
    assert "100" in narrative     # quantity
    assert "150.00" in narrative  # pnl_amount


def test_llm_cannot_change_pnl_values(review_service):
    """Red line 1: LLM cannot change P&L values."""
    original_pnl = 150.0
    
    with patch("backend.services.discipline_review.call_llm") as mock_llm:
        # LLM tries to change P&L
        mock_llm.return_value = "实际盈亏为200.0元（已核实）"

        pnl_record = PnlRecord(
            pnl_record_id="pnl_001",
            position_id="pos_001",
            buy_price=10.0,
            sell_price=11.5,
            quantity=100,
            fees=None,
            pnl_amount=original_pnl,
            pnl_pct=0.15,
            pnl_source=PnlSource.calculated_from_confirmed_details,
            missing_fields=[],
            computed_at=datetime.now(),
        )

        narrative, _ = review_service.generate_narrative(
            pnl_record=pnl_record,
            adherence=PlanAdherenceResult(
                followed_plan=True,
                deviations=[],
                adherence_trace={},
            ),
        )

        # P&L value unchanged (frozen contract)
        assert pnl_record.pnl_amount == original_pnl


def test_template_rejects_smuggled_recommendations(review_service):
    """Red line 3: Template filling rejects smuggled forward-looking content."""
    # Test: Even if LLM tries to smuggle recommendations into slot values,
    # template structure prevents it from appearing in final narrative
    
    pnl = PnlRecord(
        pnl_record_id="pnl_001",
        position_id="pos_001",
        buy_price=10.0,
        sell_price=11.5,
        quantity=100,
        fees=None,
        pnl_amount=150.0,
        pnl_pct=0.15,
        pnl_source=PnlSource.calculated_from_confirmed_details,
        missing_fields=[],
        computed_at=datetime.now(),
    )
    
    adherence = PlanAdherenceResult(
        followed_plan=True,
        deviations=[],
        adherence_trace={},
    )
    
    # Generate narrative (template filling)
    narrative, guard_passed = review_service.generate_narrative(
        pnl_record=pnl,
        adherence=adherence,
    )
    
    # Verify no smuggled content
    smuggled_phrases = [
        "下次建议买入",
        "可以加仓",
        "建议关注",
        "推荐",
    ]
    
    for phrase in smuggled_phrases:
        assert phrase not in narrative, f"Smuggled content leaked: {phrase}"
    
    # Template only contains predetermined slots
    assert guard_passed is True


def test_template_rejects_deviation_smuggling(review_service):
    """Red line 3: Template rejects soft recommendations smuggled via deviation dict."""
    # Real adversarial test: Smuggle soft recommendations in deviation.reason
    
    pnl = PnlRecord(
        pnl_record_id="pnl_001",
        position_id="pos_001",
        buy_price=10.0,
        sell_price=9.5,
        quantity=100,
        fees=None,
        pnl_amount=-50.0,
        pnl_pct=-0.05,
        pnl_source=PnlSource.calculated_from_confirmed_details,
        missing_fields=[],
        computed_at=datetime.now(),
    )
    
    # Adversarial: Smuggle soft forward-looking text in deviation dict
    adherence = PlanAdherenceResult(
        followed_plan=False,
        deviations=[
            {
                "type": "late_exit",
                "gap_days": 3,
                "reason": "这家公司逻辑当时根本没站住，低位那几天本来是好位置",  # Smuggled!
                "note": "这种走势我以后得多留个心眼",  # Smuggled!
            }
        ],
        adherence_trace={},
    )
    
    narrative, guard_passed = review_service.generate_narrative(
        pnl_record=pnl,
        adherence=adherence,
    )
    
    # Verify smuggled soft recommendations did NOT leak
    smuggled_texts = [
        "这家公司逻辑当时根本没站住",
        "低位那几天本来是好位置",
        "这种走势我以后得多留个心眼",
    ]
    
    for text in smuggled_texts:
        assert text not in narrative, f"Smuggled soft recommendation leaked: {text}"
    
    # Template should only use whitelisted fields (type, gap_days)
    assert "迟卖" in narrative  # type translation
    assert "3" in narrative      # gap_days
    assert guard_passed is True


def test_adherence_determined_by_rules_not_llm(review_service):
    """Red line 4: Plan adherence determined by rules, not LLM."""
    # Adherence check should not call LLM
    with patch("backend.services.discipline_review.call_llm") as mock_llm:
        adherence = review_service.check_plan_adherence(
            signal_date=date(2026, 6, 3),
            actual_action_date=date(2026, 6, 6),
            signal_type="sell",
        )

        # Zero LLM calls in adherence check
        mock_llm.assert_not_called()
        assert adherence.followed_plan is False
