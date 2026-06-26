"""B3 Financial Visibility Guard - Prevent future function via announcement date enforcement."""
from __future__ import annotations

from datetime import date


class FinancialVisibilityGuard:
    """
    Guard financial data visibility based on announcement dates.
    
    Enforces:
    - Financial data requires ann_date (announcement date), not end_date (report period)
    - Unknown/missing ann_date blocks usage (no inference, fail loud)
    - Data announced after as_of_date (future) cannot be used
    - No LLM calls, deterministic only
    
    Purpose: Prevent fake historical validation by using data not available at backtest time.
    """
    
    def check_visibility(
        self,
        symbol: str,
        report_period_end: date,
        ann_date: date | None,
        as_of_date: date,
    ) -> tuple[bool, str]:
        """
        Check if financial data is visible as of a specific date.
        
        Args:
            symbol: Stock symbol
            report_period_end: Financial report period end date
            ann_date: Announcement date (when data became public)
            as_of_date: Date to check visibility for
        
        Returns:
            (is_visible, error_message)
            
        Rules:
            - ann_date is required (None/missing → not visible)
            - ann_date must be <= as_of_date (future data → not visible)
            - No inference or estimation of missing ann_date
        """
        # Check 1: ann_date is required
        if ann_date is None:
            return (
                False,
                f"Financial data for {symbol} period {report_period_end} has no ann_date, cannot use",
            )
        
        # Check 2: ann_date must not be in the future relative to as_of_date
        if ann_date > as_of_date:
            return (
                False,
                f"Financial data for {symbol} announced on {ann_date} is future relative to {as_of_date}",
            )
        
        # Visible
        return (True, "")
    
    def validate_financial_dataset(
        self,
        financial_records: list[dict],
        as_of_date: date,
    ) -> tuple[bool, list[str]]:
        """
        Validate entire financial dataset for time consistency.
        
        Returns (all_valid, error_list).
        """
        errors = []
        
        for record in financial_records:
            symbol = record.get("symbol", "unknown")
            report_period_end = record.get("report_period_end")
            ann_date = record.get("ann_date")
            
            is_visible, error = self.check_visibility(
                symbol=symbol,
                report_period_end=report_period_end,
                ann_date=ann_date,
                as_of_date=as_of_date,
            )
            
            if not is_visible:
                errors.append(error)
        
        return (len(errors) == 0, errors)
