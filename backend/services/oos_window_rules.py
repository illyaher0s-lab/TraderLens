"""B3 OOS Window Rules - Deterministic out-of-sample window generation."""
from __future__ import annotations

import hashlib
import json
from datetime import date

from backend.services.b3_protocol_types import OOSWindowSpec


class OOSWindowRuleRegistry:
    """
    Registry for deterministic OOS window rules.
    
    User/LLM cannot supply OOS start/end dates.
    Only registered rules accepted.
    Same calendar + same rule → same window.
    """
    
    REGISTERED_RULES = frozenset([
        "latest_252_trading_days",
        "fixed_ratio_70_30",
    ])
    
    def generate(
        self,
        rule_id: str,
        trading_calendar: tuple[date, ...],
        available_start: date,
        available_end: date,
    ) -> OOSWindowSpec:
        """
        Generate OOS window using registered rule.
        
        Args:
            rule_id: Registered rule identifier
            trading_calendar: Tuple of trading days (sorted)
            available_start: Available data start date
            available_end: Available data end date
        
        Returns:
            OOSWindowSpec with deterministic window
        
        Raises:
            ValueError: If rule unregistered or insufficient data
        """
        # Reject unregistered rules
        if rule_id not in self.REGISTERED_RULES:
            raise ValueError(
                f"Unregistered OOS rule '{rule_id}'. "
                f"Only registered rules allowed: {sorted(self.REGISTERED_RULES)}"
            )
        
        # Validate trading calendar
        if len(trading_calendar) == 0:
            raise ValueError("Trading calendar cannot be empty")
        
        # Dispatch to rule implementation
        if rule_id == "latest_252_trading_days":
            return self._generate_latest_252_days(
                trading_calendar, available_start, available_end
            )
        elif rule_id == "fixed_ratio_70_30":
            return self._generate_fixed_ratio_70_30(
                trading_calendar, available_start, available_end
            )
        else:
            raise ValueError(f"Rule '{rule_id}' registered but not implemented")
    
    def _generate_latest_252_days(
        self,
        trading_calendar: tuple[date, ...],
        available_start: date,
        available_end: date,
    ) -> OOSWindowSpec:
        """
        Use latest 252 trading days as OOS window.
        
        Fails if fewer than 252 days available.
        """
        if len(trading_calendar) < 252:
            raise ValueError(
                f"Insufficient trading days for latest_252_trading_days rule. "
                f"Required: 252, available: {len(trading_calendar)}"
            )
        
        # Take last 252 days
        oos_calendar = trading_calendar[-252:]
        
        return OOSWindowSpec(
            oos_window_rule_id="latest_252_trading_days",
            oos_window_start=oos_calendar[0],
            oos_window_end=oos_calendar[-1],
            generated_at=date.today(),
        )
    
    def _generate_fixed_ratio_70_30(
        self,
        trading_calendar: tuple[date, ...],
        available_start: date,
        available_end: date,
    ) -> OOSWindowSpec:
        """
        Split calendar 70% in-sample / 30% out-of-sample.
        
        Minimum 30 OOS days required.
        """
        total_days = len(trading_calendar)
        
        # Calculate split point (70% IS, 30% OOS)
        is_days = int(total_days * 0.7)
        oos_days = total_days - is_days
        
        if oos_days < 30:
            raise ValueError(
                f"Insufficient trading days for fixed_ratio_70_30 rule. "
                f"OOS days: {oos_days}, minimum required: 30"
            )
        
        # OOS starts after IS period
        oos_calendar = trading_calendar[is_days:]
        
        return OOSWindowSpec(
            oos_window_rule_id="fixed_ratio_70_30",
            oos_window_start=oos_calendar[0],
            oos_window_end=oos_calendar[-1],
            generated_at=date.today(),
        )
    
    def compute_shared_oos_window_id(
        self,
        rule_id: str,
        trading_calendar: tuple[date, ...],
        available_start: date,
        available_end: date,
    ) -> str:
        """
        Compute stable shared_oos_window_id from inputs.
        
        Same rule + same calendar → same ID.
        """
        fingerprint = {
            "rule_id": rule_id,
            "calendar_start": str(trading_calendar[0]) if trading_calendar else "",
            "calendar_end": str(trading_calendar[-1]) if trading_calendar else "",
            "calendar_length": len(trading_calendar),
            "available_start": str(available_start),
            "available_end": str(available_end),
        }
        
        serialized = json.dumps(fingerprint, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
