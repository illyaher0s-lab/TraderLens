"""
Tushare API Client - M3.1

Wrapper for Tushare API with proxy disabling and rate limiting.
"""

from __future__ import annotations

import os
import time
from typing import Any

import tushare as ts

from backend.app.tushare.config import TushareConfig


class TushareClient:
    """
    Tushare API client with proxy handling and rate limiting.
    
    M3.1 Design:
    - Disables HTTP/HTTPS proxy on init (VPN compatibility)
    - Enforces rate limits to avoid API throttling
    - Provides retry logic for transient failures
    - Fail-loud on API errors (no silent fallback)
    """
    
    def __init__(self, config: TushareConfig):
        """
        Initialize Tushare client.
        
        Args:
            config: TushareConfig with token and settings
        
        Raises:
            ValueError: If token is missing
        """
        self.config = config
        
        # Disable proxy for Tushare API access (VPN compatibility)
        self._disable_proxy()
        
        # Initialize Tushare pro API
        token = config.ensure_token()
        self.pro = ts.pro_api(token, timeout=config.request_timeout_seconds)
        self.pro._DataApi__http_url = config.api_url
        
        # Rate limiting state
        self._last_request_time: float = 0.0
        self._min_request_interval = 60.0 / config.requests_per_minute
    
    @staticmethod
    def _disable_proxy() -> None:
        """
        Disable HTTP/HTTPS proxy environment variables.
        
        Required when VPN is active to ensure Tushare API calls succeed.
        """
        for key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]:
            os.environ.pop(key, None)
    
    def _enforce_rate_limit(self) -> None:
        """
        Enforce rate limit by sleeping if needed.
        
        Ensures minimum interval between requests.
        """
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()
    
    def query(
        self,
        api_name: str,
        fields: str | None = None,
        **kwargs: Any
    ) -> Any:
        """
        Query Tushare API with rate limiting and retry logic.
        
        Args:
            api_name: Tushare API name (e.g., "daily", "stock_basic")
            fields: Comma-separated field names (optional)
            **kwargs: API-specific parameters
        
        Returns:
            DataFrame from Tushare API
        
        Raises:
            ValueError: If API call fails after retries
        
        Example:
            df = client.query("daily", ts_code="600519.SH", start_date="20230101", end_date="20231231")
        """
        self._enforce_rate_limit()
        
        last_error: Exception | None = None
        
        for attempt in range(self.config.retry_attempts):
            try:
                query_kwargs = dict(kwargs)
                if fields is not None:
                    query_kwargs["fields"] = fields
                df = self.pro.query(api_name, **query_kwargs)
                
                # Tushare returns DataFrame, check if empty or error
                if df is None:
                    raise ValueError(f"Tushare API returned None for {api_name}")
                
                return df
            
            except Exception as e:
                last_error = e
                
                if attempt < self.config.retry_attempts - 1:
                    # Retry with exponential backoff
                    delay = self.config.retry_delay_seconds * (2 ** attempt)
                    time.sleep(delay)
                else:
                    # Last attempt failed
                    break
        
        # All retries exhausted
        raise ValueError(
            f"Tushare API call failed after {self.config.retry_attempts} attempts: "
            f"api={api_name}, params={kwargs}, error={last_error}"
        )
