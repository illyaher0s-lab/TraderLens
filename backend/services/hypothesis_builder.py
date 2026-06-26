"""B2 Hypothesis Builder - Main service for template selection and draft generation."""
from __future__ import annotations

import json
from datetime import datetime

from backend.services.hypothesis_builder_types import (
    HypothesisBuilderInput,
    HypothesisBuilderResult,
    LLMTemplateSelection,
)
from backend.services.strategy_config_validator import StrategyConfigValidator
from backend.services.strategy_template_library import StrategyTemplateLibrary
from contracts.strategy import BacktestUniverseSpec, StrategyDraft, StrategyLifecycleState


class HypothesisBuilder:
    """
    B2 Hypothesis Builder - Orchestrates template selection and strategy draft creation.
    
    Normal path:
    1. LLM selects template (1 call)
    2. System generates config from template
    3. Validator checks config
    4. Create StrategyDraft + initial StrategyLifecycleState
    5. Return result (no DB write)
    
    Does NOT:
    - Let LLM set parameters
    - Let Evidence events enter trade rules
    - Write status/hash/Gate/budget
    - Write to database
    - Generate multiple variants
    """
    
    def __init__(
        self,
        template_library: StrategyTemplateLibrary,
        validator: StrategyConfigValidator,
        llm_client,
    ):
        self.template_library = template_library
        self.validator = validator
        self.llm_client = llm_client
    
    def build(self, input: HypothesisBuilderInput) -> HypothesisBuilderResult:
        """
        Build strategy draft from hypothesis.
        
        Returns success with draft or failure with errors.
        Does not write to database.
        """
        # Validate universe type
        if not isinstance(input.backtest_universe_spec, BacktestUniverseSpec):
            return HypothesisBuilderResult(
                status="failed",
                strategy_revision_id=input.strategy_revision_id,
                failure_stage="validation",
                errors=("Universe must be BacktestUniverseSpec",),
            )
        
        # LLM selects template (single call)
        try:
            selection = self.llm_client.select_template(input)
        except Exception as e:
            return HypothesisBuilderResult(
                status="failed",
                strategy_revision_id=input.strategy_revision_id,
                failure_stage="template_selection",
                errors=(str(e),),
            )
        
        # Get template
        try:
            template = self.template_library.get_template(selection.strategy_template_id)
        except KeyError:
            return HypothesisBuilderResult(
                status="failed",
                strategy_revision_id=input.strategy_revision_id,
                failure_stage="template_selection",
                errors=(f"Unknown template: {selection.strategy_template_id}",),
                raw_llm_output_snapshot=selection.model_dump_json(),
            )
        
        # Generate config from template (deterministic, no LLM params)
        config = template.strategy_config_payload
        
        # Validate config
        validation_result = self.validator.validate(config, template)
        if validation_result.status != "pass":
            return HypothesisBuilderResult(
                status="failed",
                strategy_revision_id=input.strategy_revision_id,
                selected_template_id=template.template_id,
                template_selection_reason=selection.template_selection_reason,
                failure_stage="validation",
                validation_errors=tuple(e.message for e in validation_result.errors),
                errors=tuple(e.message for e in validation_result.errors),
            )
        
        # Convert to canonical JSON
        strategy_config_json = json.dumps(config, sort_keys=True)
        
        # Success - return result (no DB write, no status, no Gate)
        return HypothesisBuilderResult(
            status="success",
            strategy_revision_id=input.strategy_revision_id,
            selected_template_id=template.template_id,
            template_selection_reason=selection.template_selection_reason,
            unmapped_hypothesis_elements=selection.unmapped_hypothesis_elements,
            strategy_config_json=strategy_config_json,
            validation_result="pass",
            repair_attempts=0,
        )
