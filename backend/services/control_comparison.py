"""Control Comparison - Deterministic benchmark and control comparison."""
from __future__ import annotations


class ControlComparison:
    """
    Deterministic benchmark and control comparison.
    
    Requirements:
    - Gate cannot pass on absolute profit alone
    - Must compare against frozen benchmark
    - Must compare against same-universe control (e.g., equal-weight)
    - Beta-dominated results (pure market tracking) block candidate
    - Single-symbol/single-month concentration blocks candidate
    - No LLM scoring
    """
    
    # System-frozen concentration thresholds
    MAX_SINGLE_SYMBOL_CONTRIBUTION_PCT = 50.0
    MAX_SINGLE_MONTH_CONTRIBUTION_PCT = 50.0
    
    # Beta domination thresholds
    MIN_BETA_CORRELATION = 0.90
    MAX_BETA_DEVIATION = 0.15  # Beta must differ from 1.0 by > 0.15
    
    def check_absolute_profit_only(
        self,
        strategy_return: float,
        has_benchmark_comparison: bool,
        has_control_comparison: bool,
    ) -> dict:
        """
        Check if strategy has only absolute profit without benchmark/control.
        
        Absolute profit alone cannot pass Gate.
        
        Returns:
            dict with verdict and reason
        """
        if not has_benchmark_comparison or not has_control_comparison:
            return {
                "verdict": "needs_review",
                "reason": (
                    "Absolute profit alone cannot pass. "
                    "Benchmark and control comparison required."
                ),
            }
        
        return {
            "verdict": "can_proceed",
            "reason": "Benchmark and control comparison present",
        }
    
    def validate_benchmark_comparison(
        self,
        benchmark_comparison: dict | None,
    ) -> dict:
        """
        Validate benchmark comparison is present.
        
        Returns:
            dict with can_candidate flag
        """
        if benchmark_comparison is None:
            return {
                "can_candidate": False,
                "reason": "Benchmark comparison required for candidate verdict",
            }
        
        return {
            "can_candidate": True,
            "reason": "Benchmark comparison present",
        }
    
    def validate_control_comparison(
        self,
        control_comparison: dict | None,
    ) -> dict:
        """
        Validate same-universe control comparison is present.
        
        Returns:
            dict with can_candidate flag
        """
        if control_comparison is None:
            return {
                "can_candidate": False,
                "reason": "Same-universe control comparison required for candidate verdict",
            }
        
        return {
            "can_candidate": True,
            "reason": "Control comparison present",
        }
    
    def check_beta_domination(
        self,
        strategy_return: float,
        benchmark_return: float,
        correlation: float,
        beta: float,
    ) -> dict:
        """
        Check if strategy is beta-dominated (pure market tracking).
        
        Beta-dominated means high correlation with benchmark and beta near 1.0,
        indicating no alpha generation.
        
        Returns:
            dict with is_beta_dominated flag and can_candidate
        """
        # Check if strategy is just tracking the market
        is_high_correlation = correlation >= self.MIN_BETA_CORRELATION
        is_beta_near_one = abs(beta - 1.0) <= self.MAX_BETA_DEVIATION
        
        is_beta_dominated = is_high_correlation and is_beta_near_one
        
        if is_beta_dominated:
            return {
                "is_beta_dominated": True,
                "can_candidate": False,
                "reason": (
                    f"Beta-dominated result (correlation={correlation:.2f}, beta={beta:.2f}). "
                    f"Strategy appears to track market with no alpha generation."
                ),
            }
        
        return {
            "is_beta_dominated": False,
            "can_candidate": True,
            "reason": "Not beta-dominated",
        }
    
    def check_single_symbol_concentration(
        self,
        top_symbol_contribution_pct: float,
    ) -> dict:
        """
        Check if single symbol contributes >50% of returns.
        
        Returns:
            dict with is_concentrated flag and can_candidate
        """
        is_concentrated = top_symbol_contribution_pct > self.MAX_SINGLE_SYMBOL_CONTRIBUTION_PCT
        
        if is_concentrated:
            return {
                "is_concentrated": True,
                "can_candidate": False,
                "reason": (
                    f"Single symbol concentration too high ({top_symbol_contribution_pct:.1f}% > "
                    f"{self.MAX_SINGLE_SYMBOL_CONTRIBUTION_PCT:.1f}%). "
                    f"Strategy may be single-stock bet."
                ),
            }
        
        return {
            "is_concentrated": False,
            "can_candidate": True,
            "reason": "Symbol concentration acceptable",
        }
    
    def check_single_month_concentration(
        self,
        top_month_contribution_pct: float,
    ) -> dict:
        """
        Check if single month contributes >50% of returns.
        
        Returns:
            dict with is_concentrated flag and can_candidate
        """
        is_concentrated = top_month_contribution_pct > self.MAX_SINGLE_MONTH_CONTRIBUTION_PCT
        
        if is_concentrated:
            return {
                "is_concentrated": True,
                "can_candidate": False,
                "reason": (
                    f"Single month concentration too high ({top_month_contribution_pct:.1f}% > "
                    f"{self.MAX_SINGLE_MONTH_CONTRIBUTION_PCT:.1f}%). "
                    f"Strategy may depend on single event."
                ),
            }
        
        return {
            "is_concentrated": False,
            "can_candidate": True,
            "reason": "Month concentration acceptable",
        }
