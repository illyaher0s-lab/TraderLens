"""B2 Hypothesis Repair Loop - Bounded retry with max 2 repairs."""
from __future__ import annotations

from backend.services.hypothesis_builder import HypothesisBuilder
from backend.services.hypothesis_builder_types import (
    HypothesisBuilderInput,
    HypothesisBuilderResult,
    HypothesisBuilderValidationErrorContext,
)


class HypothesisRepairLoop:
    """
    Bounded repair loop for B2 hypothesis builder.
    
    Max repairs = 2.
    Each repair re-runs full validation.
    Repair receives structured validation errors from previous attempt.
    Repair cannot modify template parameters (they come from library).
    Repair cannot introduce Evidence/announcement/status/hash/Gate/budget.
    
    Normal path: validation passes, 0 repairs.
    Repair path: validation fails, LLM retries with errors, max 2 attempts.
    """
    
    def __init__(self, builder: HypothesisBuilder, max_repairs: int = 2):
        self.builder = builder
        self.max_repairs = max_repairs
    
    def run(self, input: HypothesisBuilderInput) -> HypothesisBuilderResult:
        """
        Run hypothesis builder with bounded repair loop.
        
        Returns success with draft or failure after exhausting repairs.
        """
        # First attempt (no previous errors)
        result = self.builder.build(input)
        
        if result.status == "success":
            return result
        
        # Repair loop (max 2 attempts)
        for attempt in range(1, self.max_repairs + 1):
            # Convert validation errors to context
            error_contexts = tuple(
                HypothesisBuilderValidationErrorContext(
                    code=err,
                    field_path="unknown",
                    message=err,
                    repairable=True,
                )
                for err in result.validation_errors
            )
            
            # Retry with structured errors
            repair_input = input.model_copy(
                update={"previous_validation_errors": error_contexts}
            )
            result = self.builder.build(repair_input)
            
            if result.status == "success":
                # Update repair count in result
                return result.model_copy(update={"repair_attempts": attempt})
            
            # Continue to next repair
        
        # Exhausted repairs
        return result.model_copy(
            update={
                "failure_stage": "repair_exhausted",
                "repair_attempts": self.max_repairs,
            }
        )

