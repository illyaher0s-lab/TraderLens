"""B2 Strategy Config Validator - Deterministic validation without LLM."""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from backend.services.strategy_template_library import (
    StrategyTemplate,
    StrategyTemplateLibrary,
)
from contracts.strategy import BacktestUniverseSpec, ForwardWatchlistSnapshot


# Forbidden terms that indicate Evidence events in trade rules
EVIDENCE_EVENT_TERMS = (
    "announcement",
    "announcements",
    "公告",
    "订单",
    "客户认证",
    "中标",
    "合同",
    "互动易",
    "问询函",
    "业绩预告",
    "减持",
    "pledge",
    "revenue_purity",
    "customer_certification",
    "disclosure",
    "report",
)

# Forbidden fields that LLM/user cannot set
FORBIDDEN_FIELDS = (
    "status",
    "hash",
    "gate_verdict",
    "oos_budget",
    "oos_start",
    "oos_end",
    "cost_model_override",
    "benchmark_override",
)


class StrategyValidationError(BaseModel):
    """Structured validation error with repair hint."""
    
    model_config = ConfigDict(frozen=True)
    
    code: str
    field_path: str
    message: str
    repairable: bool


class StrategyValidationResult(BaseModel):
    """Validation result with structured errors."""
    
    model_config = ConfigDict(frozen=True)
    
    status: Literal["pass", "fail"]
    errors: tuple[StrategyValidationError, ...] = ()


class StrategyConfigValidator:
    """Deterministic validator for strategy config - no LLM, no DB writes."""
    
    def __init__(self):
        self.library = StrategyTemplateLibrary()
    
    def validate(
        self,
        config: dict,
        template: StrategyTemplate,
    ) -> StrategyValidationResult:
        """
        Validate strategy config against template.
        
        Returns structured errors if validation fails.
        Does not mutate config.
        Does not call LLM.
        Does not write to database.
        """
        errors = []
        
        # Check template exists in library
        try:
            registered_template = self.library.get_template(template.template_id)
        except KeyError:
            errors.append(StrategyValidationError(
                code="unknown_template",
                field_path="template_id",
                message=f"Unknown template: {template.template_id}",
                repairable=False,
            ))
            return StrategyValidationResult(status="fail", errors=tuple(errors))
        
        # Check forbidden fields
        for field in FORBIDDEN_FIELDS:
            if field in config:
                errors.append(StrategyValidationError(
                    code="forbidden_field",
                    field_path=field,
                    message=f"Field '{field}' cannot be set by user or LLM",
                    repairable=False,
                ))
        
        # Check for parameter search patterns (range, variants, grid)
        for key, value in self._flatten_dict(config).items():
            if isinstance(value, list) and len(value) > 1:
                if any(suffix in key for suffix in ["_range", "_variants", "_grid"]):
                    errors.append(StrategyValidationError(
                        code="parameter_search",
                        field_path=key,
                        message=f"Parameter search not allowed: {key}",
                        repairable=False,
                    ))
        
        # Check for Evidence event terms in trade rules (entry/exit/risk)
        # Recursively check both keys and string values
        for section in ["entry", "exit", "risk"]:
            if section in config:
                violations = self._check_evidence_terms_recursive(
                    config[section], parent_path=section
                )
                for path, term in violations:
                    errors.append(StrategyValidationError(
                        code="evidence_term_in_trade_rule",
                        field_path=path,
                        message=f"Evidence term '{term}' not allowed in trade rules",
                        repairable=False,
                    ))
        
        # Check required sections
        for section in ["entry", "exit", "risk"]:
            if section not in config:
                errors.append(StrategyValidationError(
                    code="missing_section",
                    field_path=section,
                    message=f"Required section '{section}' missing",
                    repairable=True,
                ))
        
        # Check exact match with template payload
        if not errors:  # Only check if no structural errors
            expected = registered_template.strategy_config_payload
            if not self._deep_equal(config, expected):
                errors.append(StrategyValidationError(
                    code="config_mismatch",
                    field_path="strategy_config_payload",
                    message="Config does not match template exactly",
                    repairable=False,
                ))
        
        if errors:
            return StrategyValidationResult(status="fail", errors=tuple(errors))
        
        return StrategyValidationResult(status="pass", errors=())
    
    def validate_universe(self, universe: Any) -> StrategyValidationResult:
        """Validate that universe is BacktestUniverseSpec, not watchlist or symbol list."""
        errors = []
        
        if isinstance(universe, ForwardWatchlistSnapshot):
            errors.append(StrategyValidationError(
                code="invalid_universe_type",
                field_path="backtest_universe_spec",
                message="ForwardWatchlistSnapshot not allowed for formal backtest",
                repairable=False,
            ))
        elif isinstance(universe, (list, tuple)):
            errors.append(StrategyValidationError(
                code="invalid_universe_type",
                field_path="backtest_universe_spec",
                message="Plain symbol list not allowed for formal backtest",
                repairable=False,
            ))
        elif not isinstance(universe, BacktestUniverseSpec):
            errors.append(StrategyValidationError(
                code="invalid_universe_type",
                field_path="backtest_universe_spec",
                message="Must be BacktestUniverseSpec",
                repairable=False,
            ))
        
        if errors:
            return StrategyValidationResult(status="fail", errors=tuple(errors))
        
        return StrategyValidationResult(status="pass", errors=())
    
    def _flatten_dict(self, d: dict, parent_key: str = "") -> dict:
        """Flatten nested dict to dot-notation paths."""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key).items())
            else:
                items.append((new_key, v))
        return dict(items)
    
    def _deep_equal(self, a: Any, b: Any) -> bool:
        """Deep equality check for config matching."""
        if type(a) != type(b):
            return False
        if isinstance(a, dict):
            if set(a.keys()) != set(b.keys()):
                return False
            return all(self._deep_equal(a[k], b[k]) for k in a)
        if isinstance(a, (list, tuple)):
            if len(a) != len(b):
                return False
            return all(self._deep_equal(x, y) for x, y in zip(a, b))
        return a == b
    
    def _check_evidence_terms_recursive(
        self, obj: Any, parent_path: str
    ) -> list[tuple[str, str]]:
        """
        Recursively check for Evidence event terms in keys and string values.
        
        Returns list of (path, term) tuples for violations.
        """
        violations = []
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                current_path = f"{parent_path}.{key}"
                
                # Check key
                key_lower = key.lower()
                for term in EVIDENCE_EVENT_TERMS:
                    if term.lower() in key_lower:
                        violations.append((current_path, term))
                        break
                
                # Recurse into value
                violations.extend(self._check_evidence_terms_recursive(value, current_path))
        
        elif isinstance(obj, (list, tuple)):
            for i, item in enumerate(obj):
                violations.extend(
                    self._check_evidence_terms_recursive(item, f"{parent_path}[{i}]")
                )
        
        elif isinstance(obj, str):
            # Check string value
            obj_lower = obj.lower()
            for term in EVIDENCE_EVENT_TERMS:
                if term.lower() in obj_lower:
                    violations.append((parent_path, term))
                    break
        
        return violations
