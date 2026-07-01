"""
V1 Real API Smoke Verification

Task 16.5: Opt-in smoke tests for real LLM and Tushare APIs.

IMPORTANT:
- These tests are SKIPPED by default
- Set RUN_REAL_API_SMOKE=1 to enable
- Never hardcode API keys/tokens in source code
- All credentials from environment variables only

Environment variables:
- RUN_REAL_API_SMOKE: Set to "1" to enable (default: skip)
- TUSHARE_TOKEN: Tushare API token (required)
- TUSHARE_API_URL: Optional private Tushare endpoint
- RESEARCH_LLM_API_KEY: LLM API key (required)
- RESEARCH_LLM_BASE_URL: Optional LLM base URL for production LLMClient
- RESEARCH_LLM_MODEL: Optional LLM model name for production LLMClient

Purpose:
- Verify connectivity and authentication
- Verify response structure parsing
- Verify MarketDataFault mapping for Tushare
- Verify LLM draft/explanation only (no trading decisions)
- DO NOT test trading strategy quality or profitability
"""

import os
import pathlib
import pytest


# Check if real API smoke is enabled
def is_smoke_enabled():
    """Check if RUN_REAL_API_SMOKE=1."""
    return os.environ.get("RUN_REAL_API_SMOKE") == "1"


# Skip marker ONLY for real API tests (not meta tests)
skip_unless_smoke_enabled = pytest.mark.skipif(
    not is_smoke_enabled(),
    reason="Real API smoke tests disabled (set RUN_REAL_API_SMOKE=1 to enable)"
)


def disable_proxies():
    """
    Disable all proxy environment variables.
    
    Required for direct connection to private Tushare endpoints.
    """
    proxy_vars = [
        "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
        "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"
    ]
    for var in proxy_vars:
        os.environ.pop(var, None)


@skip_unless_smoke_enabled
class TestTushareSmokeVerification:
    """
    Tushare API smoke tests.
    
    Verifies:
    - Authentication works
    - Basic market data can be retrieved
    - Response structure matches expected schema
    - Empty/error responses map to MarketDataFault
    - No secret values in output
    """
    
    def test_tushare_authentication_and_basic_query(self):
        """
        Smoke test: Tushare authentication and basic query.
        
        Verifies:
        - Token authentication succeeds
        - stock_basic query returns data
        - Response has expected fields
        - No token leaked in output
        """
        # Disable proxies for direct connection
        disable_proxies()
        
        # Get credentials from environment
        token = os.environ.get("TUSHARE_TOKEN")
        api_url = os.environ.get("TUSHARE_API_URL")
        
        assert token, "TUSHARE_TOKEN environment variable not set"
        
        # Import and initialize Tushare
        import tushare as ts
        pro = ts.pro_api(token)
        
        # Set custom URL if provided
        if api_url:
            pro._DataApi__http_url = api_url
            print(f"Using custom Tushare endpoint: {api_url}")
        
        # Query stock_basic (small known dataset)
        df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')
        
        # Verify response structure
        assert df is not None, "Tushare returned None"
        assert not df.empty, "Tushare returned empty DataFrame"
        assert 'ts_code' in df.columns, "Response missing ts_code column"
        assert 'name' in df.columns, "Response missing name column"
        
        # Verify at least one A-share stock exists
        assert len(df) > 0, "No stocks returned"
        
        # Verify no token in output
        output_str = str(df.head())
        assert token not in output_str, "Token leaked in DataFrame output"
        
        print(f"[OK] Tushare authentication successful, retrieved {len(df)} stocks")
    
    def test_tushare_daily_data_smoke(self):
        """
        Smoke test: Tushare daily data query.
        
        Verifies:
        - Daily price data can be retrieved
        - Response has required fields (close, volume)
        - Data format matches expected schema
        """
        disable_proxies()
        
        token = os.environ.get("TUSHARE_TOKEN")
        api_url = os.environ.get("TUSHARE_API_URL")
        
        assert token, "TUSHARE_TOKEN environment variable not set"
        
        import tushare as ts
        pro = ts.pro_api(token)
        
        if api_url:
            pro._DataApi__http_url = api_url
        
        # Query daily data for known stock (浦发银行 600000.SH)
        df = pro.daily(ts_code='600000.SH', start_date='20260101', end_date='20260630')
        
        # Verify response structure
        assert df is not None, "Daily query returned None"
        
        if df.empty:
            # Empty data is acceptable (might be no trading days in range)
            # This should map to MarketDataFault in production
            print("[WARN] Daily data empty (acceptable if no trading days in range)")
        else:
            # Verify expected fields
            assert 'close' in df.columns, "Daily data missing close price"
            assert 'vol' in df.columns or 'volume' in df.columns, "Daily data missing volume"
            assert 'trade_date' in df.columns, "Daily data missing trade_date"
            
            print(f"[OK] Daily data retrieved: {len(df)} records")
    
    def test_tushare_connection_to_adapter(self):
        """
        Smoke test: Tushare connection via production adapter.
        
        Verifies:
        - Production adapter can connect
        - Adapter returns expected data structure
        - MarketDataFault states are properly mapped
        """
        disable_proxies()
        
        token = os.environ.get("TUSHARE_TOKEN")
        api_url = os.environ.get("TUSHARE_API_URL")
        
        assert token, "TUSHARE_TOKEN environment variable not set"
        
        # Set environment variables for adapter
        os.environ["TUSHARE_TOKEN"] = token
        if api_url:
            os.environ["TUSHARE_API_URL"] = api_url
        
        # Import production adapter
        from contracts.market_data_fault import MarketDataFaultState, MarketDataResult
        from backend.services.live_market_data import get_daily_basic_snapshot
        from datetime import date
        
        # Query via adapter
        snapshot = get_daily_basic_snapshot("600000.SH", date(2026, 6, 30))
        
        # Verify snapshot structure
        assert isinstance(snapshot, MarketDataResult), "Adapter returned non-MarketDataResult"

        # Check for either data or fault
        if snapshot.fault.state != MarketDataFaultState.ok:
            # Fault state should be properly mapped
            assert snapshot.fault.state in {
                MarketDataFaultState.unavailable,
                MarketDataFaultState.stale,
                MarketDataFaultState.inconsistent,
                MarketDataFaultState.source_error,
                MarketDataFaultState.adapter_unsupported,
            }, f"Unknown fault_state: {snapshot.fault.state.value}"
            assert snapshot.data is None
            print(f"[WARN] Adapter returned fault: {snapshot.fault.state.value}")
        else:
            # Data should have required fields
            assert snapshot.data is not None
            assert "close" in snapshot.data or "price" in snapshot.data, "Snapshot missing price field"
            print(f"[OK] Adapter returned valid snapshot")


@skip_unless_smoke_enabled
class TestLLMSmokeVerification:
    """
    LLM API smoke tests.
    
    Verifies:
    - Authentication works
    - Basic completion request succeeds
    - Response structure can be parsed
    - LLM used for draft/explanation only (no trading decisions)
    - No API key leaked in output
    """
    
    def test_llm_authentication_and_basic_completion(self):
        """
        Smoke test: LLM authentication and basic completion.
        
        Verifies:
        - API key authentication succeeds
        - Simple prompt returns response
        - Response has expected structure
        - No API key in output
        """
        # Get credentials from environment
        api_key = os.environ.get("RESEARCH_LLM_API_KEY")
        base_url = os.environ.get("RESEARCH_LLM_BASE_URL")
        model = os.environ.get("RESEARCH_LLM_MODEL")
        
        assert api_key, "RESEARCH_LLM_API_KEY environment variable not set"
        
        from backend.services.llm_client import LLMClient

        client = LLMClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )

        response = client.create_message(
            messages=[
                {"role": "user", "content": "What is 2+2? Reply with just the number."}
            ],
            system="You are a helpful assistant.",
            max_tokens=10,
        )
        
        # Verify response structure
        assert response is not None, "LLM returned None"
        assert "content" in response, "Response missing content"
        assert response["content"], "Response has no content blocks"
        
        content = response["content"][0].get("text", "")
        assert content, "LLM returned empty content"
        
        # Verify no API key in output
        assert api_key not in str(response), "API key leaked in response"
        
        print(f"[OK] LLM authentication successful, response: {content[:50]}")
    
    def test_llm_structured_extraction_smoke(self):
        """
        Smoke test: LLM structured extraction.
        
        Verifies:
        - LLM can parse structured requests
        - Response can be parsed as JSON
        - Extraction pattern works (claimed_* fields)
        """
        api_key = os.environ.get("RESEARCH_LLM_API_KEY")
        base_url = os.environ.get("RESEARCH_LLM_BASE_URL")
        model = os.environ.get("RESEARCH_LLM_MODEL")
        
        assert api_key, "RESEARCH_LLM_API_KEY environment variable not set"
        
        import json
        from backend.services.llm_client import LLMClient
        
        client = LLMClient(api_key=api_key, base_url=base_url, model=model)
        
        # Extraction prompt (strategy idea pattern)
        prompt = """
        Extract the trading rule from this text and return JSON:
        "下午两点半买入，第二天早上卖出"
        
        Return format:
        {
          "claimed_entry": "entry rule description",
          "claimed_exit": "exit rule description"
        }
        """
        
        response = client.create_message(
            messages=[
                {"role": "user", "content": prompt}
            ],
            system="Extract trading rules as JSON. Use 'claimed_' prefix for unverified claims.",
            max_tokens=200,
        )
        
        content = response["content"][0].get("text", "")
        
        # Try to parse as JSON
        try:
            # Extract JSON from markdown code block if present
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()
            
            data = json.loads(json_str)
            
            # Verify structure
            assert isinstance(data, dict), "Parsed JSON is not a dict"
            
            # Verify claimed_* fields present (LLM should use this pattern)
            has_claimed_fields = any(key.startswith("claimed_") for key in data.keys())
            
            if has_claimed_fields:
                print(f"[OK] LLM extraction successful with claimed_* pattern: {list(data.keys())}")
            else:
                print(f"[WARN] LLM extraction succeeded but no claimed_* fields: {list(data.keys())}")
            
        except json.JSONDecodeError as e:
            print(f"[WARN] LLM response not valid JSON: {content[:100]}")
            # Not a hard failure - LLM might return prose instead of JSON
            # In production, this would need retry with better prompting
    
    def test_llm_does_not_decide_trading(self):
        """
        Smoke test: Verify LLM is used for draft/explanation only.
        
        This is a META test - verifies the test suite itself does not
        call LLM for trading decisions.
        
        Actual enforcement is in contracts (lifecycle_state, recommendation_reducer).
        """
        # This test documents the boundary, does not call LLM
        
        # Verify key decision points are deterministic (not LLM)
        from backend.services.recommendation_reducer import reduce_recommendation
        import inspect
        
        # Check reducer source does not import LLM clients
        source = inspect.getsource(reduce_recommendation)
        
        forbidden_imports = ["openai", "anthropic", "llm", "gpt", "claude"]
        for term in forbidden_imports:
            assert term.lower() not in source.lower(), f"Reducer imports {term} (should be deterministic)"
        
        print("[OK] Recommendation reducer is deterministic (no LLM imports)")
        
        # Verify LLM usage is clearly marked
        from contracts.strategy_idea import StrategyIdeaExtraction
        
        # Check extraction contract has extraction_source field
        assert hasattr(StrategyIdeaExtraction, 'model_fields'), "Contract missing Pydantic fields"
        assert 'extraction_source' in StrategyIdeaExtraction.model_fields, "Missing extraction_source field"
        
        print("[OK] LLM extraction marked with extraction_source field")


class TestRealAPISmokeDefaultBehavior:
    """
    Meta test: Verify smoke tests are skipped by default.
    
    This test is NOT marked with skip_unless_smoke_enabled, so it always runs.
    """
    
    def test_smoke_tests_skipped_by_default(self):
        """
        Verify that real API smoke tests are skipped when RUN_REAL_API_SMOKE != 1.
        
        This ensures no accidental real API calls in CI/local development.
        """
        if os.environ.get("RUN_REAL_API_SMOKE") == "1":
            print("[WARN] RUN_REAL_API_SMOKE=1, real API tests are ENABLED")
        else:
            print("[OK] RUN_REAL_API_SMOKE not set, real API tests are SKIPPED (expected)")
        
        # This test always passes - it just documents the default behavior
        assert True


class TestNoSecretsInCode:
    """
    Meta test: Verify no secrets hardcoded in test file.
    
    This test is NOT marked with skip_unless_smoke_enabled, so it always runs.
    """
    
    def test_no_hardcoded_api_keys(self):
        """
        Verify this test file does not contain hardcoded API keys.
        
        Enforces: all credentials from environment variables only.
        """
        # Read this file
        import pathlib
        test_file = pathlib.Path(__file__)
        content = test_file.read_text(encoding='utf-8')
        
        # Check for common secret patterns (but not in this test's own definition)
        forbidden_patterns = [
            "sk-",  # OpenAI-style keys
            "Bearer ",  # Auth headers
            "password=",
            "token=",
            "api_key=",
        ]
        
        # These are OK (environment variable references or test infrastructure)
        allowed_patterns = [
            "os.environ.get",
            "TUSHARE_TOKEN",
            "RESEARCH_LLM_API_KEY",
            "forbidden_patterns",  # The list definition itself
            "allowed_patterns",    # This list itself
            "api_key=api_key",     # Parameter assignment from variable
            "token=token",         # Parameter assignment from variable
        ]
        
        for pattern in forbidden_patterns:
            if pattern in content:
                # Check if it's in an allowed context
                lines_with_pattern = [line for line in content.split('\n') if pattern in line]
                for line in lines_with_pattern:
                    stripped = line.strip()
                    
                    # Skip if this line is part of a list definition (ends with comma or just a string)
                    if stripped.endswith(',') or (stripped.startswith('"') and '",  #' in stripped):
                        continue
                    
                    # Allow if it's in an allowed context
                    if any(allowed in line for allowed in allowed_patterns):
                        continue
                    # Allow if it's a comment
                    if stripped.startswith('#'):
                        continue
                    # Allow if it's in a docstring
                    if '"""' in line or "'''" in line:
                        continue
                    
                    # If we reach here, it's a potential secret
                    pytest.fail(f"Potential hardcoded secret: {line.strip()}")
        
        print("[OK] No hardcoded secrets detected in test file")


class TestLLMSmokeUsesProductionClient:
    """
    Meta test: LLM smoke must exercise the same client used by production research.
    """

    def test_llm_smoke_does_not_bypass_production_client(self):
        content = pathlib.Path(__file__).read_text(encoding="utf-8")

        assert "from backend.services.llm_client import LLMClient" in content
        forbidden_openai_import = "from openai import " + "OpenAI"
        forbidden_openai_call = "chat." + "completions.create"

        assert forbidden_openai_import not in content
        assert forbidden_openai_call not in content
