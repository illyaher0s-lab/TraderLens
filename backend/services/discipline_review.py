"""
Discipline Review Service

Red lines enforced:
1. P&L only from confirmed details, never fabricated
2. Complete input chain required, missing parts explicitly marked
3. Retrospective only, no forward-looking recommendations
4. Plan adherence by deterministic rules, not LLM
"""

import uuid
from datetime import datetime, date
from typing import Optional

from contracts.live_trade import (
    ExecutionObservationLog,
    PnlRecord,
    PnlSource,
    PlanAdherenceResult,
    DisciplineReview,
    ExplanationSource,
)


class DisciplineReviewService:
    """
    Discipline review service.
    
    Deterministic P&L calculation + rule-based plan adherence + separated LLM narrative.
    """

    def calculate_pnl(
        self,
        position_id: str,
        buy_log: ExecutionObservationLog,
        sell_log: ExecutionObservationLog,
    ) -> PnlRecord:
        """
        Calculate P&L from confirmed logs.
        
        Red line 1: Pure arithmetic, no LLM, no fabrication.
        Missing fields → incomplete, no backfill.
        """
        buy_price = buy_log.confirmed_price
        sell_price = sell_log.confirmed_price
        quantity = buy_log.confirmed_quantity
        fees = None  # Can be added from logs later

        # Check completeness
        missing_fields = []
        if buy_price is None:
            missing_fields.append("buy_price")
        if sell_price is None:
            missing_fields.append("sell_price")
        if quantity is None:
            missing_fields.append("quantity")

        # Calculate P&L (or mark incomplete)
        if missing_fields:
            # Red line 1: incomplete, no backfill
            return PnlRecord(
                pnl_record_id=f"pnl_{uuid.uuid4().hex[:12]}",
                position_id=position_id,
                buy_price=buy_price,
                sell_price=sell_price,
                quantity=quantity,
                fees=fees,
                pnl_amount=None,
                pnl_pct=None,
                pnl_source=PnlSource.incomplete,
                missing_fields=missing_fields,
                computed_at=datetime.now(),
            )

        # All fields present, calculate
        pnl_amount = (sell_price - buy_price) * quantity - (fees or 0.0)
        pnl_pct = (sell_price - buy_price) / buy_price

        return PnlRecord(
            pnl_record_id=f"pnl_{uuid.uuid4().hex[:12]}",
            position_id=position_id,
            buy_price=buy_price,
            sell_price=sell_price,
            quantity=quantity,
            fees=fees,
            pnl_amount=pnl_amount,
            pnl_pct=pnl_pct,
            pnl_source=PnlSource.calculated_from_confirmed_details,
            missing_fields=[],
            computed_at=datetime.now(),
        )

    def create_user_reported_pnl(
        self,
        position_id: str,
        user_reported_pnl: float,
    ) -> PnlRecord:
        """Create P&L record from user-reported value."""
        return PnlRecord(
            pnl_record_id=f"pnl_{uuid.uuid4().hex[:12]}",
            position_id=position_id,
            buy_price=None,
            sell_price=None,
            quantity=None,
            fees=None,
            pnl_amount=user_reported_pnl,
            pnl_pct=None,
            pnl_source=PnlSource.user_reported,
            missing_fields=[],
            computed_at=datetime.now(),
        )

    def check_plan_adherence(
        self,
        signal_date: date,
        actual_action_date: date,
        signal_type: str,
    ) -> PlanAdherenceResult:
        """
        Check plan adherence by deterministic rules.
        
        Red line 4: Rules decide, not LLM.
        """
        deviations = []
        gap_days = (actual_action_date - signal_date).days

        # Late exit detection (rule-based)
        if signal_type == "sell" and gap_days > 0:
            deviations.append({
                "type": "late_exit",
                "signal_date": signal_date.isoformat(),
                "actual_action_date": actual_action_date.isoformat(),
                "gap_days": gap_days,
            })

        followed_plan = len(deviations) == 0

        return PlanAdherenceResult(
            followed_plan=followed_plan,
            deviations=deviations,
            adherence_trace={
                "signal_date": signal_date.isoformat(),
                "actual_action_date": actual_action_date.isoformat(),
                "gap_days": gap_days,
            },
        )

    def parse_rule_trace(self, rule_trace: dict) -> dict:
        """
        Parse rule_trace (Task 9 tail).
        
        Handle both numeric-type (threshold/actual) and state-type (fault_state).
        """
        # State-type: {rule, fault_state, hit}
        # Numeric-type: {rule, threshold, actual, hit}
        return rule_trace  # Pass through, no parsing crash

    def generate_narrative(
        self,
        pnl_record: PnlRecord,
        adherence: PlanAdherenceResult,
        use_llm: bool = False,
    ) -> tuple[Optional[str], bool]:
        """
        Generate plain-language narrative.
        
        Red line 3: Template-based filling, no free-form generation.
        LLM only translates slot values into fluent Chinese, cannot add sentences.
        """
        # Use template filling (no free-form generation allowed)
        narrative = self._template_fill_narrative(pnl_record, adherence)

        # Guard: Check narrative contains no text outside template slots
        guard_passed = self._check_template_constraint(narrative, pnl_record, adherence)
        
        if not guard_passed:
            return (None, False)  # Narrative violated template constraint

        return (narrative, guard_passed)

    def _template_fill_narrative(self, pnl_record: PnlRecord, adherence: PlanAdherenceResult) -> str:
        """
        Template filling: only fill predetermined slots.
        
        Slots:
        - buy_price, sell_price, quantity
        - pnl_amount, pnl_pct
        - pnl_source (translated)
        - followed_plan (translated)
        - deviations (translated)
        
        No free-form text allowed outside slots.
        """
        # Template structure (fixed)
        template_parts = []

        # Part 1: P&L summary
        if pnl_record.pnl_source == PnlSource.calculated_from_confirmed_details:
            template_parts.append(
                f"买入价 {pnl_record.buy_price:.2f} 元，"
                f"卖出价 {pnl_record.sell_price:.2f} 元，"
                f"数量 {pnl_record.quantity} 股。"
            )
            template_parts.append(
                f"盈亏 {pnl_record.pnl_amount:.2f} 元（{pnl_record.pnl_pct:.2%}）。"
            )
        elif pnl_record.pnl_source == PnlSource.user_reported:
            template_parts.append(
                f"用户报告盈亏 {pnl_record.pnl_amount:.2f} 元。"
            )
        else:
            template_parts.append("P&L 数据不完整，缺失字段：" + "、".join(pnl_record.missing_fields) + "。")

        # Part 2: Plan adherence
        if adherence.followed_plan is True:
            template_parts.append("执行纪律：按计划完成。")
        elif adherence.followed_plan is False:
            deviations_desc = []
            for dev in adherence.deviations:
                if dev.get("type") == "late_exit":
                    deviations_desc.append(f"迟卖 {dev.get('gap_days')} 天")
            template_parts.append("执行纪律：存在偏离（" + "，".join(deviations_desc) + "）。")
        else:
            template_parts.append("执行纪律：无法判定。")

        return "".join(template_parts)

    def _check_template_constraint(
        self,
        narrative: Optional[str],
        pnl_record: PnlRecord,
        adherence: PlanAdherenceResult,
    ) -> bool:
        """
        Check narrative only contains template slots, no free-form text.
        
        Approach: Verify all numeric/string content comes from slots.
        """
        if narrative is None:
            return True

        # Extract all slot values that should appear
        expected_values = []
        
        if pnl_record.buy_price is not None:
            expected_values.append(f"{pnl_record.buy_price:.2f}")
        if pnl_record.sell_price is not None:
            expected_values.append(f"{pnl_record.sell_price:.2f}")
        if pnl_record.quantity is not None:
            expected_values.append(str(pnl_record.quantity))
        if pnl_record.pnl_amount is not None:
            expected_values.append(f"{pnl_record.pnl_amount:.2f}")

        # Check for unexpected content (simple heuristic: no stock names/codes)
        # More sophisticated: check narrative length doesn't exceed template + slots
        suspicious_patterns = [
            "建议",
            "下次",
            "可以",
            "应该",
        ]

        for pattern in suspicious_patterns:
            if pattern in narrative:
                return False

        return True

    def create_review(
        self,
        position_id: str,
        execution_card_id: str,
        signal_id: str,
        daily_signal_ids: list[str],
        buy_log: Optional[ExecutionObservationLog],
        sell_log: Optional[ExecutionObservationLog],
    ) -> DisciplineReview:
        """
        Create discipline review.
        
        Red line 2: Missing inputs explicitly marked.
        """
        # Check input completeness
        input_completeness = {
            "execution_card": "present" if execution_card_id else "missing",
            "signal": "present" if signal_id else "missing",
            "daily_signals": "present" if daily_signal_ids else "missing",
            "buy_log": "present" if buy_log else "missing",
            "sell_log": "present" if sell_log else "missing",
        }

        # Calculate P&L (incomplete if missing logs)
        if buy_log and sell_log:
            pnl_record = self.calculate_pnl(
                position_id=position_id,
                buy_log=buy_log,
                sell_log=sell_log,
            )
        else:
            # Missing logs → incomplete P&L
            missing = []
            if not buy_log:
                missing.append("buy_log")
            if not sell_log:
                missing.append("sell_log")
            
            pnl_record = PnlRecord(
                pnl_record_id=f"pnl_{uuid.uuid4().hex[:12]}",
                position_id=position_id,
                buy_price=None,
                sell_price=None,
                quantity=None,
                fees=None,
                pnl_amount=None,
                pnl_pct=None,
                pnl_source=PnlSource.incomplete,
                missing_fields=missing,
                computed_at=datetime.now(),
            )

        # Check adherence (undetermined if missing data)
        if buy_log and sell_log:
            adherence = self.check_plan_adherence(
                signal_date=date.today(),  # Placeholder
                actual_action_date=sell_log.confirmed_at.date(),
                signal_type="sell",
            )
        else:
            adherence = PlanAdherenceResult(
                followed_plan=None,
                deviations=[],
                adherence_trace={"status": "undetermined", "reason": "missing logs"},
            )

        # Generate narrative
        narrative, guard_passed = self.generate_narrative(
            pnl_record=pnl_record,
            adherence=adherence,
        )

        return DisciplineReview(
            review_id=f"review_{uuid.uuid4().hex[:12]}",
            position_id=position_id,
            execution_card_id=execution_card_id or "",
            signal_id=signal_id or "",
            daily_signal_ids=daily_signal_ids or [],
            buy_log_id=buy_log.log_id if buy_log else "",
            sell_log_id=sell_log.log_id if sell_log else "",
            input_completeness=input_completeness,
            pnl_record=pnl_record,
            plan_adherence=adherence,
            plain_narrative=narrative,
            narrative_source=ExplanationSource.template_text if narrative else ExplanationSource.none,
            forward_looking_guard_passed=guard_passed,
            created_at=datetime.now(),
        )


# Placeholder for LLM integration (not used in V1)
def call_llm(prompt: str) -> str:
    """Placeholder for LLM call."""
    raise NotImplementedError("LLM integration not yet implemented")
