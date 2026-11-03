import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from requests import exceptions as requests_exc

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_client import TushareClient
from backend.services.data_tools import DataToolsService
from backend.services.research_validation import ResearchValidator


def test_config_reads_custom_api_url_from_environment(monkeypatch):
    """The local endpoint configured for the token must not be silently ignored."""
    monkeypatch.setenv("TUSHARE_API_URL", "http://example.test:8686/")

    assert TushareConfig.from_env().api_url == "http://example.test:8686/"


def test_research_validator_uses_environment_tushare_config_by_default(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "environment-token")
    monkeypatch.setenv("TUSHARE_API_URL", "https://env.example.test/dataapi")

    validator = ResearchValidator()

    assert validator.tushare_config.token == "environment-token"
    assert validator.tushare_config.api_url == "https://env.example.test/dataapi"


def test_research_validator_preserves_explicit_tushare_config(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "environment-token")
    monkeypatch.setenv("TUSHARE_API_URL", "https://env.example.test/dataapi")
    explicit_config = TushareConfig(
        token="explicit-token",
        api_url="https://explicit.example.test/dataapi",
    )

    validator = ResearchValidator(tushare_config=explicit_config)

    assert validator.tushare_config is explicit_config


def test_query_omits_fields_when_callers_do_not_request_a_field_list():
    """Passing fields=None makes the custom Tushare endpoint return empty daily data."""
    captured = {}

    class FakePro:
        _DataApi__http_url = ""

        def query(self, api_name, **kwargs):
            captured["api_name"] = api_name
            captured["kwargs"] = kwargs
            return []

    with patch("backend.app.tushare.tushare_client.ts.pro_api", return_value=FakePro()):
        client = TushareClient(TushareConfig(token="test-token"))
        client.query("daily", ts_code="600519.SH")

    assert captured["api_name"] == "daily"
    assert "fields" not in captured["kwargs"]
    assert captured["kwargs"]["ts_code"] == "600519.SH"


def test_query_single_attempt_does_not_retry_permission_failures():
    calls = []

    class FakePro:
        _DataApi__http_url = ""

        def query(self, api_name, **kwargs):
            calls.append((api_name, kwargs))
            raise RuntimeError("permission denied")

    with patch("backend.app.tushare.tushare_client.ts.pro_api", return_value=FakePro()):
        client = TushareClient(TushareConfig(
            token="test-token", retry_attempts=3, retry_delay_seconds=0,
        ))
        with pytest.raises(ValueError) as caught:
            client.query("news", single_attempt=True, src="sina")

    assert len(calls) == 1
    assert calls[0] == ("news", {"src": "sina"})
    assert "after 1 attempts" in str(caught.value)
    assert "params={'src': 'sina'}" in str(caught.value)
    assert "permission denied" in str(caught.value)
    assert not hasattr(caught.value, "safe_error_category")
    assert DataToolsService._tushare_failure_status(caught.value) == "permission_denied"


@pytest.mark.parametrize(
    ("error_factory", "expected_category", "expected_status"),
    [
        (lambda: requests_exc.Timeout("synthetic-only"), "network_timeout", None),
        (lambda: requests_exc.ConnectionError("synthetic-only"), "network_connection", None),
        (lambda: requests_exc.SSLError("synthetic-only"), "network_tls_error", None),
        (lambda: _synthetic_http_error(503), "http_response_error", 503),
        (lambda: Exception("synthetic-only"), "unclassified", None),
        (lambda: json.JSONDecodeError("synthetic-only", "", 0), "invalid_provider_response", None),
    ],
)
def test_query_opt_in_attaches_only_safe_error_diagnostics(error_factory, expected_category, expected_status):
    error = error_factory()
    forwarded_kwargs = {}

    class FakePro:
        _DataApi__http_url = ""

        def query(self, api_name, **kwargs):
            forwarded_kwargs.update(kwargs)
            raise error

    with patch("backend.app.tushare.tushare_client.ts.pro_api", return_value=FakePro()):
        with patch.object(TushareClient, "_disable_proxy"):
            client = TushareClient(TushareConfig(token="test-token", retry_delay_seconds=0))
            with pytest.raises(ValueError) as caught:
                client.query("trade_cal", single_attempt=True, safe_error_diagnostics=True)

    assert getattr(caught.value, "safe_error_category", None) == expected_category
    assert getattr(caught.value, "safe_cause_type", None) == type(error).__name__
    assert getattr(caught.value, "safe_http_status", None) == expected_status
    assert "synthetic-only" not in str(caught.value)
    assert "safe_error_diagnostics" not in forwarded_kwargs


def _synthetic_http_error(status_code):
    error = requests_exc.HTTPError("synthetic-only")
    error.response = SimpleNamespace(status_code=status_code)
    return error


@pytest.mark.parametrize(
    ("synthetic_error", "expected_status"),
    [
        ("synthetic-only-permission-denied-marker", "permission_denied"),
        ("synthetic-only unsupported api marker", "unsupported_endpoint"),
    ],
)
def test_default_query_failure_preserves_direct_caller_classification(synthetic_error, expected_status):
    class FakePro:
        _DataApi__http_url = ""

        def query(self, api_name, **kwargs):
            raise Exception(synthetic_error)

    config = TushareConfig(
        token="test-token",
        retry_attempts=1,
        retry_delay_seconds=0,
    )
    with patch("backend.app.tushare.tushare_client.ts.pro_api", return_value=FakePro()):
        with patch.object(TushareClient, "_disable_proxy"):
            client = TushareClient(config)
    with pytest.raises(ValueError) as caught:
        client.query("trade_cal", single_attempt=True)
    assert synthetic_error in str(caught.value)
    assert DataToolsService._tushare_failure_status(caught.value) == expected_status

    validator = ResearchValidator(tushare_config=config)
    validator._tushare_client = client

    snapshot = validator.get_hard_filter_snapshot("synthetic-symbol", "listed")

    assert len(snapshot.gaps) == 2
    assert all("Tushare API call failed after 1 attempts" in gap for gap in snapshot.gaps)
    assert all(synthetic_error in gap for gap in snapshot.gaps)


def test_default_data_tools_error_surface_preserves_legacy_exception_text():
    class FakePro:
        _DataApi__http_url = ""

        def query(self, api_name, **kwargs):
            raise Exception("synthetic-only-provider-message")

    config = TushareConfig(
        token="test-token",
        retry_attempts=1,
        retry_delay_seconds=0,
    )
    with patch("backend.app.tushare.tushare_client.ts.pro_api", return_value=FakePro()):
        with patch.object(TushareClient, "_disable_proxy"):
            client = TushareClient(config)

    result = DataToolsService(tushare_client=client).get_financials("synthetic-symbol")

    assert len(result.errors) == 1
    assert "Tushare income API call failed" in result.errors[0]
    assert "synthetic-only-provider-message" in result.errors[0]


def test_missing_token_is_classified_as_client_configuration_failure():
    with patch.object(TushareClient, "_disable_proxy"):
        with pytest.raises(ValueError) as caught:
            TushareClient(TushareConfig(token=None))

    assert getattr(caught.value, "safe_error_category", None) == "client_configuration_error"
    assert getattr(caught.value, "safe_cause_type", None) == "ValueError"
    assert getattr(caught.value, "safe_http_status", None) is None


def test_query_default_still_uses_configured_retries():
    calls = []

    class FakePro:
        _DataApi__http_url = ""

        def query(self, api_name, **kwargs):
            calls.append(api_name)
            raise RuntimeError("temporary provider error")

    with patch("backend.app.tushare.tushare_client.ts.pro_api", return_value=FakePro()):
        client = TushareClient(TushareConfig(
            token="test-token", retry_attempts=2, retry_delay_seconds=0,
        ))
        try:
            client.query("daily", ts_code="600519.SH")
        except ValueError:
            pass
        else:
            raise AssertionError("provider failure must still fail loudly")

    assert calls == ["daily", "daily"]
