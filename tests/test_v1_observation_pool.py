"""
Task 9: Observation Pool Tests

Red lines enforced:
1. Position only from confirmed log, never from draft
2. Daily signals 100% deterministic reducer, LLM never decides
3. Zero LLM for hold signals
4. MarketDataFault non-ok → downgrade only
"""

import pytest
from datetime import datetime, date
from unittest.mock import Mock, patch
import uuid

from contracts.live_trade import (
    ExecutionObservationLog,
    ExecutionObservationDraft,
    ExecutionInterpretationStatus,
    ObservationPosition,
    PositionLifecycleState,
    DailyObservationSignal,
    DailySignalType,
    InvalidationTrigger,
    ExplanationSource,
)
from contracts.market_data_fault import MarketDataFaultState
from backend.services.observation_pool import ObservationPool


@pytest.fixture
def pool():
    """Create observation pool instance."""
    return ObservationPool()


@pytest.fixture
def confirmed_log():
    """Create a confirmed buy log."""
    return ExecutionObservationLog(
        log_id="log_001",
        draft_id="draft_001",
        execution_card_id="exec_001",
        signal_id="sig_001",
        action_plan_id="plan_001",
        capital_context_id="cap_001",
        market_snapshot_id="snap_001",
        confirmed_action="buy",
        confirmed_execution_status="executed_full",
        confirmed_price=10.5,
        confirmed_quantity=100,
        reason=None,
        confirmed_by_user=True,
        broker_verified=False,
        confirmed_at=datetime.now(),
    )


@pytest.fixture
def mock_template_rules():
    """Mock template exit/risk rules."""
    return {
        "template_id": "template_001",
        "template_version": "v1",
        "exit_rules": {"profit_target": 0.15, "time_stop_days": 30},
        "risk_rules": {"stop_loss": -0.08, "trailing_stop": -0.05},
    }


def test_position_created_from_confirmed_log(pool, confirmed_log, mock_template_rules):
    """Red line 1: confirmed log successfully creates position with evidence chain."""
    position = pool.create_position_from_log(
        log=confirmed_log,
        symbol="600000.SH",
        name="浦发银行",
        template_id=mock_template_rules["template_id"],
        template_version=mock_template_rules["template_version"],
        entry_thesis="银行股反弹+利率上行预期",
    )

    # Verify position created
    assert position.lifecycle_state == PositionLifecycleState.open
    assert position.entry_price == 10.5
    assert position.quantity == 100

    # Verify evidence chain (5 IDs + source_log_id)
    assert position.source_log_id == "log_001"
    assert position.execution_card_id == "exec_001"
    assert position.signal_id == "sig_001"
    assert position.action_plan_id == "plan_001"
    assert position.capital_context_id == "cap_001"

    # Verify template lock
    assert position.template_id == "template_001"
    assert position.template_version == "v1"


def test_draft_cannot_create_position(pool):
    """Red line 1: draft cannot create position."""
    draft = ExecutionObservationDraft(
        draft_id="draft_001",
        execution_card_id="exec_001",
        signal_id="sig_001",
        action_plan_id="plan_001",
        capital_context_id="cap_001",
        market_snapshot_id="snap_001",
        raw_user_text="我买了",
        parsed_action="buy",
        parsed_execution_status="executed_full",
        parsed_price=None,
        parsed_quantity=None,
        parsed_reason=None,
        missing_fields=["parsed_price", "parsed_quantity"],
        follow_up_question="请问实际成交价格和数量是多少？",
        interpretation_source="deterministic",
        status=ExecutionInterpretationStatus.needs_more_info,
        broker_verified=False,
        created_at=datetime.now(),
    )

    # Attempt to create position from draft
    with pytest.raises((ValueError, TypeError), match="draft|confirmed|log"):
        pool.create_position_from_log(
            log=draft,  # ← wrong type
            symbol="600000.SH",
            name="浦发银行",
            template_id="template_001",
            template_version="v1",
            entry_thesis="test",
        )


def test_hold_signal_zero_llm_calls(pool, confirmed_log, mock_template_rules):
    """Red line 3: hold signal has zero LLM calls."""
    position = pool.create_position_from_log(
        log=confirmed_log,
        symbol="600000.SH",
        name="浦发银行",
        template_id=mock_template_rules["template_id"],
        template_version=mock_template_rules["template_version"],
        entry_thesis="银行股反弹",
    )

    # Mock LLM to verify it's not called
    with patch("backend.services.observation_pool.call_llm") as mock_llm:
        signal = pool.generate_daily_signal(
            position=position,
            current_price=11.0,  # +4.8% gain, not hitting any threshold
            market_data_state=MarketDataFaultState.ok,
            template_rules=mock_template_rules,
            as_of_date=date.today(),
        )

        # Verify signal is hold
        assert signal.signal_type == DailySignalType.hold
        assert signal.triggered_invalidations == []
        
        # Red line 3: zero LLM calls
        assert signal.explanation_source in [ExplanationSource.none, ExplanationSource.template_text]
        mock_llm.assert_not_called()


def test_stop_loss_hit_with_rule_trace(pool, confirmed_log, mock_template_rules):
    """Stop loss hit → sell signal with complete rule_trace."""
    position = pool.create_position_from_log(
        log=confirmed_log,
        symbol="600000.SH",
        name="浦发银行",
        template_id=mock_template_rules["template_id"],
        template_version=mock_template_rules["template_version"],
        entry_thesis="银行股反弹",
    )

    # Current price triggers stop loss (-8.8% < -8%)
    signal = pool.generate_daily_signal(
        position=position,
        current_price=9.58,  # -8.8% loss
        market_data_state=MarketDataFaultState.ok,
        template_rules=mock_template_rules,
        as_of_date=date.today(),
    )

    # Verify signal type
    assert signal.signal_type == DailySignalType.sell

    # Verify rule_trace contains threshold/actual/hit
    assert "rule" in signal.rule_trace
    assert signal.rule_trace["rule"] == "stop_rule"
    assert "threshold" in signal.rule_trace
    assert signal.rule_trace["threshold"] == -0.08
    assert "actual" in signal.rule_trace
    assert signal.rule_trace["actual"] < -0.08
    assert "hit" in signal.rule_trace
    assert signal.rule_trace["hit"] is True


def test_fundamental_breach_invalidation(pool, confirmed_log, mock_template_rules):
    """Fundamental breach → invalidated signal with trigger."""
    position = pool.create_position_from_log(
        log=confirmed_log,
        symbol="600000.SH",
        name="浦发银行",
        template_id=mock_template_rules["template_id"],
        template_version=mock_template_rules["template_version"],
        entry_thesis="银行股反弹",
    )

    # Simulate fundamental breach (e.g., earnings miss)
    signal = pool.generate_daily_signal(
        position=position,
        current_price=10.0,
        market_data_state=MarketDataFaultState.ok,
        template_rules=mock_template_rules,
        as_of_date=date.today(),
        external_triggers=[InvalidationTrigger.fundamental_breach],
    )

    # Verify signal type
    assert signal.signal_type == DailySignalType.invalidated

    # Verify invalidation trigger recorded
    assert InvalidationTrigger.fundamental_breach in signal.triggered_invalidations


def test_multiple_triggers_all_recorded(pool, confirmed_log, mock_template_rules):
    """Multiple invalidation triggers → all recorded in list."""
    position = pool.create_position_from_log(
        log=confirmed_log,
        symbol="600000.SH",
        name="浦发银行",
        template_id=mock_template_rules["template_id"],
        template_version=mock_template_rules["template_version"],
        entry_thesis="银行股反弹+主题炒作",
    )

    # Multiple triggers hit simultaneously
    signal = pool.generate_daily_signal(
        position=position,
        current_price=9.5,  # Also price break
        market_data_state=MarketDataFaultState.ok,
        template_rules=mock_template_rules,
        as_of_date=date.today(),
        external_triggers=[
            InvalidationTrigger.theme_faded,
            InvalidationTrigger.event_risk,
        ],
    )

    # Verify all triggers recorded
    assert len(signal.triggered_invalidations) >= 2
    assert InvalidationTrigger.theme_faded in signal.triggered_invalidations
    assert InvalidationTrigger.event_risk in signal.triggered_invalidations


def test_market_data_fault_stale_downgrade(pool, confirmed_log, mock_template_rules):
    """Red line 4: MarketDataFault=stale → downgrade, not hold."""
    position = pool.create_position_from_log(
        log=confirmed_log,
        symbol="600000.SH",
        name="浦发银行",
        template_id=mock_template_rules["template_id"],
        template_version=mock_template_rules["template_version"],
        entry_thesis="银行股反弹",
    )

    signal = pool.generate_daily_signal(
        position=position,
        current_price=11.0,
        market_data_state=MarketDataFaultState.stale,  # Data fault
        template_rules=mock_template_rules,
        as_of_date=date.today(),
    )

    # Red line 4: must not output hold
    assert signal.signal_type != DailySignalType.hold
    # Should downgrade to risk
    assert signal.signal_type == DailySignalType.risk
    # Market data state recorded
    assert signal.market_data_state == MarketDataFaultState.stale


def test_market_data_fault_unavailable_downgrade(pool, confirmed_log, mock_template_rules):
    """Red line 4: MarketDataFault=unavailable → risk/pause."""
    position = pool.create_position_from_log(
        log=confirmed_log,
        symbol="600000.SH",
        name="浦发银行",
        template_id=mock_template_rules["template_id"],
        template_version=mock_template_rules["template_version"],
        entry_thesis="银行股反弹",
    )

    signal = pool.generate_daily_signal(
        position=position,
        current_price=11.0,
        market_data_state=MarketDataFaultState.unavailable,
        template_rules=mock_template_rules,
        as_of_date=date.today(),
    )

    # Must not be hold
    assert signal.signal_type != DailySignalType.hold
    # Should be risk or invalidated
    assert signal.signal_type in [DailySignalType.risk, DailySignalType.invalidated]


def test_sell_signal_calls_llm_once(pool, confirmed_log, mock_template_rules):
    """Sell signal may call LLM once for explanation, but LLM output doesn't change signal_type."""
    position = pool.create_position_from_log(
        log=confirmed_log,
        symbol="600000.SH",
        name="浦发银行",
        template_id=mock_template_rules["template_id"],
        template_version=mock_template_rules["template_version"],
        entry_thesis="银行股反弹",
    )

    # Mock LLM to return explanation
    with patch("backend.services.observation_pool.call_llm") as mock_llm:
        mock_llm.return_value = "止损线触发，建议立即卖出"

        signal = pool.generate_daily_signal(
            position=position,
            current_price=9.58,  # Stop loss hit
            market_data_state=MarketDataFaultState.ok,
            template_rules=mock_template_rules,
            as_of_date=date.today(),
        )

        # Verify signal type determined by reducer, not LLM
        assert signal.signal_type == DailySignalType.sell

        # LLM called at most once
        assert mock_llm.call_count <= 1

        # If LLM was called, explanation_source reflects it
        if mock_llm.called:
            assert signal.explanation_source == ExplanationSource.llm_assisted
            assert signal.plain_explanation is not None


def test_closed_position_no_daily_signal(pool, confirmed_log, mock_template_rules):
    """Closed position does not generate daily signals."""
    position = pool.create_position_from_log(
        log=confirmed_log,
        symbol="600000.SH",
        name="浦发银行",
        template_id=mock_template_rules["template_id"],
        template_version=mock_template_rules["template_version"],
        entry_thesis="银行股反弹",
    )

    # Close position
    closed_position = pool.close_position(position)
    assert closed_position.lifecycle_state == PositionLifecycleState.closed

    # Attempt to generate signal for closed position
    with pytest.raises(ValueError, match="closed|lifecycle"):
        pool.generate_daily_signal(
            position=closed_position,
            current_price=11.0,
            market_data_state=MarketDataFaultState.ok,
            template_rules=mock_template_rules,
            as_of_date=date.today(),
        )


def test_reducer_deterministic_same_input_same_output(pool, confirmed_log, mock_template_rules):
    """Red line 2: reducer is deterministic — same input produces same output."""
    position = pool.create_position_from_log(
        log=confirmed_log,
        symbol="600000.SH",
        name="浦发银行",
        template_id=mock_template_rules["template_id"],
        template_version=mock_template_rules["template_version"],
        entry_thesis="银行股反弹",
    )

    # Run reducer twice with identical inputs (no mocking needed — reducer is pure)
    signal1 = pool.generate_daily_signal(
        position=position,
        current_price=10.5,
        market_data_state=MarketDataFaultState.ok,
        template_rules=mock_template_rules,
        as_of_date=date(2026, 6, 30),
    )

    signal2 = pool.generate_daily_signal(
        position=position,
        current_price=10.5,
        market_data_state=MarketDataFaultState.ok,
        template_rules=mock_template_rules,
        as_of_date=date(2026, 6, 30),
    )

    # Verify same output (deterministic reducer)
    assert signal1.signal_type == signal2.signal_type
    assert signal1.triggered_invalidations == signal2.triggered_invalidations
    assert signal1.rule_trace == signal2.rule_trace


def test_reducer_only_uses_whitelisted_rules(pool, confirmed_log, mock_template_rules):
    """Reducer only uses whitelisted rules, no unauthorized rules."""
    # Whitelist from Task 9
    WHITELISTED_RULES = {
        "stop_rule",
        "profit_target",
        "time_stop",
        # Six invalidation triggers become "invalidation_triggers" in rule_trace
        "invalidation_triggers",
        "market_data_fault",
        "default_hold",
    }

    position = pool.create_position_from_log(
        log=confirmed_log,
        symbol="600000.SH",
        name="浦发银行",
        template_id=mock_template_rules["template_id"],
        template_version=mock_template_rules["template_version"],
        entry_thesis="银行股反弹",
    )

    # Test various scenarios
    test_scenarios = [
        # (current_price, market_data_state, external_triggers, expected_rule)
        (10.5, MarketDataFaultState.ok, [], "default_hold"),  # Hold
        (9.2, MarketDataFaultState.ok, [], "stop_rule"),  # Stop loss
        (11.0, MarketDataFaultState.stale, [], "market_data_fault"),  # Data fault
        (10.5, MarketDataFaultState.ok, [InvalidationTrigger.theme_faded], "invalidation_triggers"),  # Invalidation
    ]

    for price, data_state, triggers, expected_rule in test_scenarios:
        signal = pool.generate_daily_signal(
            position=position,
            current_price=price,
            market_data_state=data_state,
            template_rules=mock_template_rules,
            as_of_date=date.today(),
            external_triggers=triggers,
        )

        actual_rule = signal.rule_trace.get("rule")
        
        # Assert rule is in whitelist
        assert actual_rule in WHITELISTED_RULES, (
            f"Unauthorized rule '{actual_rule}' found. "
            f"Whitelist: {WHITELISTED_RULES}. "
            f"Scenario: price={price}, data_state={data_state.value}, triggers={triggers}"
        )
