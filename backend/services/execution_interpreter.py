"""
Execution Interpreter

Parses natural-language user execution feedback into structured ExecutionObservationDraft.

Design:
- Deterministic keyword matching for common phrases (zero LLM).
- LLM only for genuinely ambiguous input (future, not needed for V1 six phrases).
- Never auto-promotes draft to log.
- Never fabricates price/quantity.
- Never claims broker_verified.
"""

import uuid
from datetime import datetime
from typing import Optional

from contracts.live_trade import (
    ExecutionInterpretationStatus,
    ExecutionObservationDraft,
)


class ExecutionInterpreter:
    """Parse user execution feedback into draft observation."""

    def parse_user_feedback(
        self,
        raw_text: str,
        evidence_chain: dict[str, str],
    ) -> ExecutionObservationDraft:
        """
        Parse user's natural-language execution feedback.
        
        Args:
            raw_text: User's statement (e.g., "我买了", "没买")
            evidence_chain: Required IDs linking to upstream artifacts
        
        Returns:
            ExecutionObservationDraft (never ExecutionObservationLog)
        """
        normalized = raw_text.strip()

        # Deterministic keyword matching (zero LLM for these six phrases)
        
        # Pattern 1: 我买了
        if "我买了" in normalized or "买了" == normalized:
            return self._create_draft(
                raw_text=raw_text,
                evidence_chain=evidence_chain,
                parsed_action="buy",
                parsed_execution_status="executed_full",
                parsed_price=None,
                parsed_quantity=None,
                parsed_reason=None,
                missing_fields=["parsed_price", "parsed_quantity"],
                follow_up_question="请问实际成交价格和数量是多少？",
                status=ExecutionInterpretationStatus.needs_more_info,
                source="deterministic",
            )

        # Pattern 2: 没买
        if "没买" in normalized or normalized in ["没买", "没执行", "未买入"]:
            return self._create_draft(
                raw_text=raw_text,
                evidence_chain=evidence_chain,
                parsed_action="none",
                parsed_execution_status="skipped",
                parsed_price=None,
                parsed_quantity=None,
                parsed_reason=None,
                missing_fields=[],
                follow_up_question=None,
                status=ExecutionInterpretationStatus.draft_pending_confirmation,
                source="deterministic",
            )

        # Pattern 3: 只买了一半
        if "只买了一半" in normalized or "买了一半" in normalized or "部分成交" in normalized:
            return self._create_draft(
                raw_text=raw_text,
                evidence_chain=evidence_chain,
                parsed_action="buy",
                parsed_execution_status="executed_partial",
                parsed_price=None,
                parsed_quantity=None,
                parsed_reason=None,
                missing_fields=["parsed_price", "parsed_quantity"],
                follow_up_question="请问实际成交了多少股，成交价格是多少？",
                status=ExecutionInterpretationStatus.needs_more_info,
                source="deterministic",
            )

        # Pattern 4: 卖了
        if "卖了" in normalized or "已卖出" in normalized:
            return self._create_draft(
                raw_text=raw_text,
                evidence_chain=evidence_chain,
                parsed_action="sell",
                parsed_execution_status="executed_full",
                parsed_price=None,
                parsed_quantity=None,
                parsed_reason=None,
                missing_fields=["parsed_price", "parsed_quantity"],
                follow_up_question="请问卖出价格和数量是多少？",
                status=ExecutionInterpretationStatus.needs_more_info,
                source="deterministic",
            )

        # Pattern 5: 忘了执行
        if "忘了执行" in normalized or "忘记执行" in normalized or "忘了" in normalized:
            return self._create_draft(
                raw_text=raw_text,
                evidence_chain=evidence_chain,
                parsed_action="none",
                parsed_execution_status="forgot",
                parsed_price=None,
                parsed_quantity=None,
                parsed_reason="忘了执行",
                missing_fields=[],
                follow_up_question=None,
                status=ExecutionInterpretationStatus.draft_pending_confirmation,
                source="deterministic",
            )

        # Pattern 6: 价格太高没追
        if "价格太高" in normalized and ("没追" in normalized or "没买" in normalized):
            return self._create_draft(
                raw_text=raw_text,
                evidence_chain=evidence_chain,
                parsed_action="none",
                parsed_execution_status="skipped",
                parsed_price=None,
                parsed_quantity=None,
                parsed_reason="价格太高没追",
                missing_fields=[],
                follow_up_question=None,
                status=ExecutionInterpretationStatus.draft_pending_confirmation,
                source="deterministic",
            )

        # If no deterministic match, mark as needs_more_info (future: LLM fallback)
        return self._create_draft(
            raw_text=raw_text,
            evidence_chain=evidence_chain,
            parsed_action="none",
            parsed_execution_status="skipped",
            parsed_price=None,
            parsed_quantity=None,
            parsed_reason=None,
            missing_fields=["parsed_action", "parsed_execution_status"],
            follow_up_question="请明确说明是否买入/卖出，或者是否跳过执行？",
            status=ExecutionInterpretationStatus.needs_more_info,
            source="deterministic",
        )

    def _create_draft(
        self,
        raw_text: str,
        evidence_chain: dict[str, str],
        parsed_action: str,
        parsed_execution_status: str,
        parsed_price: Optional[float],
        parsed_quantity: Optional[int],
        parsed_reason: Optional[str],
        missing_fields: list[str],
        follow_up_question: Optional[str],
        status: ExecutionInterpretationStatus,
        source: str,
    ) -> ExecutionObservationDraft:
        """Create ExecutionObservationDraft with evidence chain."""
        return ExecutionObservationDraft(
            draft_id=f"draft_{uuid.uuid4().hex[:12]}",
            execution_card_id=evidence_chain["execution_card_id"],
            signal_id=evidence_chain["signal_id"],
            action_plan_id=evidence_chain["action_plan_id"],
            capital_context_id=evidence_chain["capital_context_id"],
            market_snapshot_id=evidence_chain["market_snapshot_id"],
            raw_user_text=raw_text,
            parsed_action=parsed_action,
            parsed_execution_status=parsed_execution_status,
            parsed_price=parsed_price,
            parsed_quantity=parsed_quantity,
            parsed_reason=parsed_reason,
            missing_fields=missing_fields,
            follow_up_question=follow_up_question,
            interpretation_source=source,
            status=status,
            broker_verified=False,  # Red line 2: always False
            created_at=datetime.now(),
        )
