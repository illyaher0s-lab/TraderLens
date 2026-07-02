"""
Stock Identity Resolver - Tushare-backed stock verification

Task 20A: Production path uses Tushare stock_basic, test path uses injected fixture.

Rules:
- Production: Tushare stock_basic is the source of truth
- Test: Deterministic fixture via dependency injection
- No hardcoded stock mappings in production path
- LLM cannot confirm stock existence
- Supports bare code inference (603002 -> 603002.SH)
"""

from typing import Optional, Literal
from pydantic import BaseModel


class StockIdentityResolution(BaseModel):
    """Stock identity resolution result."""
    status: Literal[
        "verified",
        "ambiguous",
        "not_found",
        "data_fault",
        "unsupported_exchange",
        "not_applicable"
    ]
    ticker: Optional[str] = None
    company_name: Optional[str] = None
    exchange: Optional[str] = None
    list_status: Optional[str] = None
    candidates: list[dict] = []
    data_source: Literal[
        "tushare_stock_basic",
        "deterministic_fixture",
        "not_applicable"
    ]
    fault_reason: Optional[str] = None


class StockIdentityResolver:
    """
    Resolve stock identity from company name or stock code.
    
    Production: queries Tushare stock_basic
    Test: uses injected fixture
    """
    
    def __init__(self, tushare_client=None, test_fixture: Optional[dict] = None):
        """
        Args:
            tushare_client: TushareClient for production queries
            test_fixture: Dict[ticker -> dict] for testing
        """
        self.tushare_client = tushare_client
        self.test_fixture = test_fixture or {}
    
    def resolve(
        self,
        company_name: Optional[str],
        stock_code: Optional[str],
    ) -> StockIdentityResolution:
        """
        Resolve stock identity from company name or stock code.
        
        Args:
            company_name: Company name (Chinese or English)
            stock_code: Stock code (bare or with suffix)
            
        Returns:
            StockIdentityResolution with verification result
        """
        # Not applicable - no stock inputs
        if not company_name and not stock_code:
            return StockIdentityResolution(
                status="not_applicable",
                data_source="not_applicable",
            )
        
        # Check for unsupported exchanges
        if stock_code and stock_code.endswith('.BJ'):
            return StockIdentityResolution(
                status="unsupported_exchange",
                ticker=stock_code,
                data_source="not_applicable",
                fault_reason="北交所股票暂不支持",
            )
        
        # Test fixture path
        if self.test_fixture:
            return self._resolve_with_fixture(company_name, stock_code)
        
        # Production path: Tushare stock_basic
        if not self.tushare_client:
            return StockIdentityResolution(
                status="data_fault",
                data_source="tushare_stock_basic",
                fault_reason="Tushare client not configured",
            )
        
        return self._resolve_with_tushare(company_name, stock_code)
    
    def _resolve_with_fixture(
        self,
        company_name: Optional[str],
        stock_code: Optional[str],
    ) -> StockIdentityResolution:
        """Test path: use injected fixture."""
        # Try stock code first
        if stock_code:
            # Try exact match first
            if stock_code in self.test_fixture:
                identity = self.test_fixture[stock_code]
                return StockIdentityResolution(
                    status="verified",
                    ticker=identity["ticker"],
                    company_name=identity["company_name"],
                    exchange=identity["exchange"],
                    list_status=identity.get("list_status", "L"),
                    data_source="deterministic_fixture",
                )
            
            # If bare code (no suffix), infer suffix and try again
            if not stock_code.endswith(('.SH', '.SZ', '.BJ')):
                # Infer exchange from code prefix
                inferred_ticker = None
                if stock_code.startswith(('600', '601', '603', '605', '688')):
                    inferred_ticker = f"{stock_code}.SH"
                elif stock_code.startswith(('000', '001', '002', '003', '300', '301')):
                    inferred_ticker = f"{stock_code}.SZ"
                elif stock_code.startswith(('430', '8', '9')):
                    inferred_ticker = f"{stock_code}.BJ"
                
                if inferred_ticker and inferred_ticker in self.test_fixture:
                    identity = self.test_fixture[inferred_ticker]
                    return StockIdentityResolution(
                        status="verified",
                        ticker=identity["ticker"],
                        company_name=identity["company_name"],
                        exchange=identity["exchange"],
                        list_status=identity.get("list_status", "L"),
                        data_source="deterministic_fixture",
                    )
            
            return StockIdentityResolution(
                status="not_found",
                ticker=stock_code,
                data_source="deterministic_fixture",
                fault_reason=f"Stock code {stock_code} not in test fixture",
            )
        
        # Try company name
        if company_name:
            # Search by company name in fixture values
            matches = []
            for ticker, identity in self.test_fixture.items():
                if identity["company_name"] == company_name:
                    matches.append(identity)
            
            if len(matches) == 1:
                identity = matches[0]
                return StockIdentityResolution(
                    status="verified",
                    ticker=identity["ticker"],
                    company_name=identity["company_name"],
                    exchange=identity["exchange"],
                    list_status=identity.get("list_status", "L"),
                    data_source="deterministic_fixture",
                )
            elif len(matches) > 1:
                return StockIdentityResolution(
                    status="ambiguous",
                    company_name=company_name,
                    candidates=[
                        {
                            "ticker": m["ticker"],
                            "company_name": m["company_name"],
                            "exchange": m["exchange"],
                        }
                        for m in matches
                    ],
                    data_source="deterministic_fixture",
                )
            else:
                return StockIdentityResolution(
                    status="not_found",
                    company_name=company_name,
                    data_source="deterministic_fixture",
                    fault_reason=f"Company name '{company_name}' not in test fixture",
                )
        
        return StockIdentityResolution(
            status="not_found",
            data_source="deterministic_fixture",
        )
    
    def _resolve_with_tushare(
        self,
        company_name: Optional[str],
        stock_code: Optional[str],
    ) -> StockIdentityResolution:
        """Production path: query Tushare stock_basic."""
        try:
            # Try stock code first
            if stock_code:
                # If bare code (no suffix), infer suffix first (deterministic)
                query_code = stock_code
                if not stock_code.endswith(('.SH', '.SZ', '.BJ')):
                    # Infer exchange from code prefix
                    if stock_code.startswith(('600', '601', '603', '605', '688')):
                        query_code = f"{stock_code}.SH"
                    elif stock_code.startswith(('000', '001', '002', '003', '300', '301')):
                        query_code = f"{stock_code}.SZ"
                    elif stock_code.startswith(('430', '8', '9')):
                        query_code = f"{stock_code}.BJ"
                    # else: keep as-is and let Tushare return not found
                
                df = self.tushare_client.query(
                    "stock_basic",
                    ts_code=query_code,
                    fields="ts_code,name,market,list_status",
                )
                
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    ts_code = row["ts_code"]
                    name = row["name"]
                    list_status = row["list_status"]
                    
                    # Infer exchange
                    if ts_code.endswith(".SH"):
                        exchange = "SSE"
                    elif ts_code.endswith(".SZ"):
                        exchange = "SZSE"
                    elif ts_code.endswith(".BJ"):
                        exchange = "BSE"
                    else:
                        exchange = "unknown"
                    
                    return StockIdentityResolution(
                        status="verified",
                        ticker=ts_code,
                        company_name=name,
                        exchange=exchange,
                        list_status=list_status,
                        data_source="tushare_stock_basic",
                    )
                else:
                    return StockIdentityResolution(
                        status="not_found",
                        ticker=query_code,
                        data_source="tushare_stock_basic",
                        fault_reason=f"Stock code {query_code} not found in Tushare stock_basic",
                    )
            
            # Try company name
            if company_name:
                df = self.tushare_client.query(
                    "stock_basic",
                    name=company_name,
                    fields="ts_code,name,market,list_status",
                )
                
                if df is not None and not df.empty:
                    if len(df) == 1:
                        row = df.iloc[0]
                        ts_code = row["ts_code"]
                        name = row["name"]
                        list_status = row["list_status"]
                        
                        # Infer exchange
                        if ts_code.endswith(".SH"):
                            exchange = "SSE"
                        elif ts_code.endswith(".SZ"):
                            exchange = "SZSE"
                        elif ts_code.endswith(".BJ"):
                            exchange = "BSE"
                        else:
                            exchange = "unknown"
                        
                        return StockIdentityResolution(
                            status="verified",
                            ticker=ts_code,
                            company_name=name,
                            exchange=exchange,
                            list_status=list_status,
                            data_source="tushare_stock_basic",
                        )
                    else:
                        # Multiple matches
                        candidates = []
                        for _, row in df.iterrows():
                            ts_code = row["ts_code"]
                            name = row["name"]
                            
                            if ts_code.endswith(".SH"):
                                exchange = "SSE"
                            elif ts_code.endswith(".SZ"):
                                exchange = "SZSE"
                            elif ts_code.endswith(".BJ"):
                                exchange = "BSE"
                            else:
                                exchange = "unknown"
                            
                            candidates.append({
                                "ticker": ts_code,
                                "company_name": name,
                                "exchange": exchange,
                            })
                        
                        return StockIdentityResolution(
                            status="ambiguous",
                            company_name=company_name,
                            candidates=candidates,
                            data_source="tushare_stock_basic",
                        )
                else:
                    return StockIdentityResolution(
                        status="not_found",
                        company_name=company_name,
                        data_source="tushare_stock_basic",
                        fault_reason=f"Company name '{company_name}' not found in Tushare stock_basic",
                    )
        
        except Exception as e:
            return StockIdentityResolution(
                status="data_fault",
                data_source="tushare_stock_basic",
                fault_reason=f"Tushare API error: {str(e)}",
            )
        
        return StockIdentityResolution(
            status="not_found",
            data_source="tushare_stock_basic",
        )
