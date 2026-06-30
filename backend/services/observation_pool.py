"""
Observation Pool Service

Red lines enforced:
1. Position only from confirmed log, never from draft.
2. Daily signals 100% deterministic reducer, LLM never decides.
3. Zero LLM for hold signals, max 1 call for sell/risk/invalidated explanation.
4. MarketDataFault non-ok → downgrade only, never upgrade.
"""

import uuid
from datetime import datetime, date
from typing import Optional

from contracts.live_trade import (
    ExecutionObservationLog,
    ObservationPosition,
    PositionLifecycleState,
    DailyObservationSignal,
    DailySignalType,
    InvalidationTrigger,
    ExplanationSource,
)
from contracts.market_data_fault import MarketDataFaultState


class ObservationPool:
    """
    Observation pool for live positions.
    
    Deterministic reducer + separated LLM explanation layer.
    """

    def create_position_from_log(
        self,
        log: ExecutionObservationLog,
        symbol: str,
        name: str,
        template_id: str,
        template_version: str,
        entry_thesis: str,
    ) -> ObservationPosition:
        """
        Create position from confirmed log.
        
        Red line 1: only accepts ExecutionObservationLog, rejects drafts.
        """
        # Type guard: reject non-log objects
        if not isinstance(log, ExecutionObservationLog):
            raise TypeError("Position can only be created from ExecutionObservationLog (confirmed log), not draft")

        # Require buy action
        if log.confirmed_action != "buy":
            raise ValueError("Position can only be created from buy action")

        # Require price and quantity
        if log.confirmed_price is None or log.confirmed_quantity is None:
            raise ValueError("Position requires confirmed_price and confirmed_quantity")

        return ObservationPosition(
            position_id=f"pos_{uuid.uuid4().hex[:12]}",
            source_log_id=log.log_id,
            execution_card_id=log.execution_card_id,
            signal_id=log.signal_id,
            action_plan_id=log.action_plan_id,
            capital_context_id=log.capital_context_id,
            symbol=symbol,
            name=name,
            entry_price=log.confirmed_price,
            quantity=log.confirmed_quantity,
            template_id=template_id,
            template_version=template_version,
            entry_thesis=entry_thesis,
            lifecycle_state=PositionLifecycleState.open,
            opened_at=log.confirmed_at,
            closed_at=None,
        )

    def close_position(self, position: ObservationPosition) -> ObservationPosition:
        """Close a position."""
        if position.lifecycle_state == PositionLifecycleState.closed:
            raise ValueError("Position already closed")

        return ObservationPosition(
            position_id=position.position_id,
            source_log_id=position.source_log_id,
            execution_card_id=position.execution_card_id,
            signal_id=position.signal_id,
            action_plan_id=position.action_plan_id,
            capital_context_id=position.capital_context_id,
            symbol=position.symbol,
            name=position.name,
            entry_price=position.entry_price,
            quantity=position.quantity,
            template_id=position.template_id,
            template_version=position.template_version,
            entry_thesis=position.entry_thesis,
            lifecycle_state=PositionLifecycleState.closed,
            opened_at=position.opened_at,
            closed_at=datetime.now(),
        )

    def generate_daily_signal(
        self,
        position: ObservationPosition,
        current_price: float,
        market_data_state: MarketDataFaultState,
        template_rules: dict,
        as_of_date: date,
        external_triggers: Optional[list[InvalidationTrigger]] = None,
    ) -> DailyObservationSignal:
        """
        Generate daily signal for a position.
        
        Red line 2: 100% deterministic reducer.
        Red line 3: Zero LLM for hold, max 1 for sell/risk/invalidated explanation.
        Red line 4: MarketDataFault non-ok → downgrade only.
        """
        # Closed positions cannot generate signals
        if position.lifecycle_state == PositionLifecycleState.closed:
            raise ValueError("Cannot generate signal for closed position")

        external_triggers = external_triggers or []

        # Run deterministic reducer
        signal_type, triggered_invalidations, rule_trace = self._deterministic_reducer(
            position=position,
            current_price=current_price,
            market_data_state=market_data_state,
            template_rules=template_rules,
            external_triggers=external_triggers,
        )

        # Generate explanation (only for non-hold signals)
        plain_explanation, explanation_source = self._generate_explanation(
            signal_type=signal_type,
            triggered_invalidations=triggered_invalidations,
            rule_trace=rule_trace,
            position=position,
        )

        return DailyObservationSignal(
            signal_record_id=f"sig_{uuid.uuid4().hex[:12]}",
            position_id=position.position_id,
            signal_type=signal_type,
            triggered_invalidations=triggered_invalidations,
            as_of_date=datetime.combine(as_of_date, datetime.min.time()),
            market_data_state=market_data_state,
            rule_trace=rule_trace,
            plain_explanation=plain_explanation,
            explanation_source=explanation_source,
        )

    def _deterministic_reducer(
        self,
        position: ObservationPosition,
        current_price: float,
        market_data_state: MarketDataFaultState,
        template_rules: dict,
        external_triggers: list[InvalidationTrigger],
    ) -> tuple[DailySignalType, list[InvalidationTrigger], dict]:
        """
        Deterministic reducer: pure function, no LLM/random/time side effects.
        
        Priority (hardwired):
        1. MarketDataFault non-ok → downgrade
        2. Invalidation triggers
        3. Sell rules
        4. Risk rules
        5. Hold (default)
        
        Returns: (signal_type, triggered_invalidations, rule_trace)
        """
        # Priority 1: MarketDataFault non-ok → downgrade (red line 4)
        if market_data_state != MarketDataFaultState.ok:
            return (
                DailySignalType.risk,
                [],
                {
                    "rule": "market_data_fault",
                    "fault_state": market_data_state.value,
                    "hit": True,
                },
            )

        # Calculate P&L
        pnl_pct = (current_price - position.entry_price) / position.entry_price
        stop_loss_threshold = template_rules.get("risk_rules", {}).get("stop_loss", -0.08)

        # Priority 2: Check invalidation triggers (external only, not stop_rule)
        # stop_rule goes to sell branch, not invalidation
        all_triggers = list(external_triggers)  # Copy external triggers

        if all_triggers:
            return (
                DailySignalType.invalidated,
                all_triggers,
                {
                    "rule": "invalidation_triggers",
                    "triggers": [t.value for t in all_triggers],
                    "hit": True,
                },
            )

        # Priority 3: Check sell rules
        # Stop loss hit → sell (not invalidation)
        # Semantic: actual <= threshold (boundary inclusive)
        if pnl_pct <= stop_loss_threshold:
            return (
                DailySignalType.sell,
                [],
                {
                    "rule": "stop_rule",
                    "threshold": stop_loss_threshold,
                    "actual": pnl_pct,
                    "hit": True,
                },
            )

        # Priority 4: Profit target (future implementation)
        # profit_target = template_rules.get("exit_rules", {}).get("profit_target", 0.15)
        # if pnl_pct >= profit_target:
        #     return (DailySignalType.sell, [], {"rule": "profit_target", ...})

        # Priority 5: Default hold
        return (
            DailySignalType.hold,
            [],
            {
                "rule": "default_hold",
                "pnl_pct": pnl_pct,
                "hit": False,
            },
        )

    def _generate_explanation(
        self,
        signal_type: DailySignalType,
        triggered_invalidations: list[InvalidationTrigger],
        rule_trace: dict,
        position: ObservationPosition,
    ) -> tuple[Optional[str], ExplanationSource]:
        """
        Generate plain-language explanation.
        
        Red line 3: Only called for sell/risk/invalidated, never for hold.
        LLM output does NOT change signal_type (already decided by reducer).
        """
        # Hold signals: no explanation needed (red line 3: zero LLM)
        if signal_type == DailySignalType.hold:
            return (None, ExplanationSource.none)

        # For now, use template text (LLM integration can be added later)
        # This satisfies red line 3: zero LLM for hold, and max 1 for others
        
        if signal_type == DailySignalType.sell:
            if rule_trace.get("rule") == "stop_rule":
                explanation = f"止损线触发（阈值 {rule_trace.get('threshold', 'N/A')}，实际 {rule_trace.get('actual', 'N/A'):.2%}），建议卖出"
                return (explanation, ExplanationSource.template_text)

        if signal_type == DailySignalType.risk:
            if rule_trace.get("rule") == "market_data_fault":
                explanation = f"市场数据异常（{rule_trace.get('fault_state', 'unknown')}），建议观望"
                return (explanation, ExplanationSource.template_text)

        if signal_type == DailySignalType.invalidated:
            triggers_text = ", ".join([t.value for t in triggered_invalidations])
            explanation = f"失效触发器：{triggers_text}"
            return (explanation, ExplanationSource.template_text)

        # Fallback
        return ("信号已触发，请复核", ExplanationSource.template_text)


# Placeholder for LLM integration (not used in V1, satisfies red line 3)
def call_llm(prompt: str) -> str:
    """Placeholder for LLM call (not used in deterministic reducer)."""
    raise NotImplementedError("LLM integration not yet implemented")
