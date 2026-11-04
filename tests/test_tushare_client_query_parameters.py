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
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("TUSHARE_SNAPSHOT_ROOT", raising=False)
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
    assert "permission denied" in str(caught.value)
    assert "params=" not in str(caught.value)
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
    assert getattr(caught.value, "safe_provider_message", None) == str(error)
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


def test_query_default_surfaces_sanitized_provider_message_without_request_or_credentials():
    secret = "test-token-that-must-not-escape"
    url_token = "url-token-that-must-not-escape"
    api_url = f"https://proxy.example/api?token={url_token}"

    class FakePro:
        _DataApi__http_url = ""

        def query(self, api_name, **kwargs):
            raise RuntimeError(
                f"token无效; token={secret}; request URL={api_url}; key={secret}"
            )

    with patch("backend.app.tushare.tushare_client.ts.pro_api", return_value=FakePro()):
        with patch.object(TushareClient, "_disable_proxy"):
            client = TushareClient(TushareConfig(
                token=secret, api_url=api_url, retry_attempts=1, retry_delay_seconds=0,
            ))

    with pytest.raises(ValueError) as caught:
        client.query("etf_basic", single_attempt=True, ts_code="510880.SH")

    safe_message = str(caught.value)
    assert "token无效" in safe_message
    assert secret not in safe_message
    assert url_token not in safe_message
    assert "proxy.example" not in safe_message
    assert "ts_code" not in safe_message
    assert "params=" not in safe_message
    assert getattr(caught.value, "safe_provider_message", None) == "token无效; token=[凭据已隐藏]; request URL=[URL已隐藏]; key=[凭据已隐藏]"
    assert not hasattr(caught.value, "safe_error_category")


def test_query_safe_diagnostics_attaches_sanitized_provider_message_only():
    secret = "test-token-that-must-not-escape"
    api_url = "https://proxy.example/api?token=url-token-that-must-not-escape"
    raw_message = f"token无效; token={secret}; URL={api_url}"

    class FakePro:
        _DataApi__http_url = ""

        def query(self, api_name, **kwargs):
            raise RuntimeError(raw_message)

    with patch("backend.app.tushare.tushare_client.ts.pro_api", return_value=FakePro()):
        with patch.object(TushareClient, "_disable_proxy"):
            client = TushareClient(TushareConfig(
                token=secret, api_url=api_url, retry_attempts=1, retry_delay_seconds=0,
            ))

    with pytest.raises(ValueError) as caught:
        client.query("etf_basic", single_attempt=True, safe_error_diagnostics=True, ts_code="159263.SZ")

    safe_message = getattr(caught.value, "safe_provider_message", None)
    assert safe_message is not None
    assert "token无效" in safe_message
    assert secret not in safe_message
    assert "url-token-that-must-not-escape" not in safe_message
    assert "proxy.example" not in safe_message
    assert "token无效" not in str(caught.value)
    assert getattr(caught.value, "safe_error_category", None) == "unclassified"


def test_query_omits_unsafe_structured_provider_text():
    secret = "test-token-that-must-not-escape"
    raw_message = f'{{"request":{{"token":"{secret}"}},"body":"private"}}'

    class FakePro:
        _DataApi__http_url = ""

        def query(self, api_name, **kwargs):
            raise RuntimeError(raw_message)

    with patch("backend.app.tushare.tushare_client.ts.pro_api", return_value=FakePro()):
        with patch.object(TushareClient, "_disable_proxy"):
            client = TushareClient(TushareConfig(
                token=secret, retry_attempts=1, retry_delay_seconds=0,
            ))

    with pytest.raises(ValueError) as caught:
        client.query("trade_cal", single_attempt=True)

    assert getattr(caught.value, "safe_provider_message", None) is None
    assert secret not in str(caught.value)
    assert "request" not in str(caught.value).lower()
    assert not hasattr(caught.value, "safe_error_category")


def test_query_extracts_provider_message_from_json_without_exposing_other_fields():
    secret = "test-token-that-must-not-escape"
    raw_message = json.dumps({
        "code": -1,
        "msg": "token无效",
        "data": {"token": secret},
    })

    class FakePro:
        _DataApi__http_url = ""

        def query(self, api_name, **kwargs):
            raise RuntimeError(raw_message)

    with patch("backend.app.tushare.tushare_client.ts.pro_api", return_value=FakePro()):
        with patch.object(TushareClient, "_disable_proxy"):
            client = TushareClient(TushareConfig(
                token=secret, retry_attempts=1, retry_delay_seconds=0,
            ))

    with pytest.raises(ValueError) as caught:
        client.query("etf_basic", single_attempt=True, ts_code="159263.SZ")

    assert getattr(caught.value, "safe_provider_message", None) == "token无效"
    assert "token无效" in str(caught.value)
    assert secret not in str(caught.value)
    assert "data" not in str(caught.value)


@pytest.mark.parametrize("safe_error_diagnostics", [False, True])
@pytest.mark.parametrize(
    "provider_url",
    [
        "https://proxy.example/api?token=url-token-that-must-not-escape&mode=invalid",
        "proxy.example/api?token=url-token-that-must-not-escape&mode=invalid",
    ],
)
def test_query_redacts_url_with_token_when_url_is_at_message_end(safe_error_diagnostics, provider_url):
    url_token = "url-token-that-must-not-escape"
    raw_message = f"provider rejected {provider_url}"

    class FakePro:
        _DataApi__http_url = ""

        def query(self, api_name, **kwargs):
            raise RuntimeError(raw_message)

    with patch("backend.app.tushare.tushare_client.ts.pro_api", return_value=FakePro()):
        with patch.object(TushareClient, "_disable_proxy"):
            client = TushareClient(TushareConfig(
                token="test-token", retry_attempts=1, retry_delay_seconds=0,
            ))

    with pytest.raises(ValueError) as caught:
        client.query(
            "etf_basic", single_attempt=True,
            safe_error_diagnostics=safe_error_diagnostics,
        )

    safe_message = getattr(caught.value, "safe_provider_message", None)
    assert safe_message == "provider rejected [URL已隐藏]"
    assert url_token not in str(caught.value)
    assert "proxy.example" not in str(caught.value)


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
