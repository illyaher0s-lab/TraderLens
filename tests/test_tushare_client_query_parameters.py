from unittest.mock import patch

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_client import TushareClient
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
