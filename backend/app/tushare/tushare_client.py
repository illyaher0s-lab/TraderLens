"""
Tushare API Client - M3.1

Wrapper for Tushare API with proxy disabling and rate limiting.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from requests import exceptions as requests_exc

import tushare as ts

from backend.app.tushare.config import TushareConfig


_SAFE_ERROR_CATEGORIES = frozenset({
    "client_configuration_error",
    "client_initialization_error",
    "network_tls_error",
    "network_timeout",
    "network_connection",
    "http_response_error",
    "provider_api_error",
    "invalid_provider_response",
    "unclassified",
})


def _safe_http_status(error: Exception) -> int | None:
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    return status if type(status) is int and 100 <= status <= 599 else None


def _safe_error_category(error: Exception) -> str:
    attached = getattr(error, "safe_error_category", None)
    if isinstance(attached, str) and attached in _SAFE_ERROR_CATEGORIES:
        return attached
    if isinstance(error, requests_exc.SSLError):
        return "network_tls_error"
    if isinstance(error, (requests_exc.Timeout, TimeoutError)):
        return "network_timeout"
    if isinstance(error, (requests_exc.ConnectionError, ConnectionError)):
        return "network_connection"
    if isinstance(error, requests_exc.HTTPError):
        return "http_response_error"
    if isinstance(error, json.JSONDecodeError):
        return "invalid_provider_response"
    if type(error) is Exception:
        return "provider_api_error"
    return "unclassified"


def _safe_cause_type(error: Exception) -> str:
    cause_type = getattr(error, "safe_cause_type", None)
    if (
        isinstance(cause_type, str)
        and len(cause_type) <= 64
        and cause_type.isascii()
        and cause_type.isidentifier()
    ):
        return cause_type
    name = type(error).__name__
    return name if len(name) <= 64 and name.isascii() and name.isidentifier() else "UnknownError"


def _attach_safe_error_diagnostics(error: Exception, category: str) -> None:
    error.safe_error_category = category
    error.safe_cause_type = type(error).__name__
    error.safe_http_status = _safe_http_status(error)


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
        
        # Initialize Tushare pro API.
        try:
            token = config.ensure_token()
        except ValueError as exc:
            _attach_safe_error_diagnostics(exc, "client_configuration_error")
            raise
        try:
            self.pro = ts.pro_api(token, timeout=config.request_timeout_seconds)
            self.pro._DataApi__http_url = config.api_url
        except Exception as exc:
            _attach_safe_error_diagnostics(exc, "client_initialization_error")
            raise
        
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
        *,
        single_attempt: bool = False,
        **kwargs: Any
    ) -> Any:
        """
        Query Tushare API with rate limiting and retry logic.
        
        Args:
            api_name: Tushare API name (e.g., "daily", "stock_basic")
            fields: Comma-separated field names (optional)
            single_attempt: Disable wrapper retries for this bounded query only.
            **kwargs: API-specific parameters
        
        Returns:
            DataFrame from Tushare API
        
        Raises:
            ValueError: If API call fails after retries
        
        Example:
            df = client.query("daily", ts_code="600519.SH", start_date="20230101", end_date="20231231")
        """
        self._enforce_rate_limit()

        if type(single_attempt) is not bool:
            raise ValueError("single_attempt must be a boolean")
        attempt_limit = 1 if single_attempt else self.config.retry_attempts
        last_error: Exception | None = None

        for attempt in range(attempt_limit):
            try:
                query_kwargs = dict(kwargs)
                if fields is not None:
                    query_kwargs["fields"] = fields
                df = self.pro.query(api_name, **query_kwargs)
                
                # Tushare returns DataFrame, check if empty or error
                if df is None:
                    empty_response = ValueError(f"Tushare API returned None for {api_name}")
                    _attach_safe_error_diagnostics(empty_response, "invalid_provider_response")
                    raise empty_response
                
                return df
            
            except Exception as e:
                last_error = e
                
                if attempt < attempt_limit - 1:
                    # Retry with exponential backoff
                    delay = self.config.retry_delay_seconds * (2 ** attempt)
                    time.sleep(delay)
                else:
                    # Last attempt failed
                    break
        
        # Do not embed provider response text or query parameters in the exception.
        error = ValueError(f"Tushare API call failed after {attempt_limit} attempts: api={api_name}")
        error.safe_error_category = _safe_error_category(last_error)
        error.safe_cause_type = _safe_cause_type(last_error)
        error.safe_http_status = (
            getattr(last_error, "safe_http_status", None)
            if type(getattr(last_error, "safe_http_status", None)) is int
            else _safe_http_status(last_error)
        )
        raise error from None
