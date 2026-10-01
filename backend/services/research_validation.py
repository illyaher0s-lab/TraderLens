"""
Research validation service.

Ticker verification from trusted data source (Tushare):
- verify_ticker: confirm company name, ticker, exchange, listing status from Tushare API

Deterministic candidate checks:
- unknown_symbol: stock identity does not exist
- not_listed: stock is not listed
- is_st: stock is ST/ST*
- is_suspended: stock is suspended
- low_liquidity: average daily volume below threshold

CONSTRAINTS:
- Ticker verification MUST NOT use model memory
- All stock identity facts MUST come from data source API
- LLM physically has no access to these fields
"""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple, Literal

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_client import TushareClient


class ValidationResult(NamedTuple):
    """Validation result with flags and validity status."""
    flags: list[str]
    is_valid: bool


class HardFilterSnapshot(NamedTuple):
    """Hard-filter facts collected from deterministic data sources."""
    is_listed: bool | None
    is_st: bool | None
    is_suspended: bool | None
    avg_daily_volume: float | None
    source: str
    retrieved_at: datetime
    gaps: list[str]


class TickerVerificationResult(NamedTuple):
    """
    Ticker verification result from trusted data source.
    
    MUST NOT come from model memory.
    All fields populated from Tushare API or marked as unknown.
    
    verification_id: Unique ID for this verification (UUID)
    """
    verification_id: str
    company_name: str
    ticker: str
    exchange: str
    status: Literal["listed", "delisted", "suspended", "acquired", "private", "unknown"]
    confidence: Literal["high", "medium", "low"]
    source: str
    notes: str
    verified_at: datetime


class ResearchValidator:
    """
    Research candidate validation.
    
    Ticker verification: from Tushare API (NOT model memory)
    Hard filters: deterministic checks on verified data
    """

    def __init__(
        self,
        liquidity_threshold: float = 1000000.0,
        tushare_config: TushareConfig | None = None,
    ):
        """
        Initialize validator.
        
        Args:
            liquidity_threshold: Minimum average daily volume (RMB) required
            tushare_config: Tushare configuration (optional, loads from env if None)
        """
        self.liquidity_threshold = liquidity_threshold
        self.tushare_config = (
            tushare_config if tushare_config is not None else TushareConfig.from_env()
        )
        self._tushare_client: TushareClient | None = None

    @property
    def tushare_client(self) -> TushareClient:
        """Lazy-initialize Tushare client."""
        if self._tushare_client is None:
            self._tushare_client = TushareClient(self.tushare_config)
        return self._tushare_client

    def verify_ticker(self, symbol: str) -> TickerVerificationResult:
        """
        Verify ticker/company/exchange identity from trusted data source.
        
        MUST NOT use model memory.
        All facts come from Tushare API.
        
        Returns verification_id that can be used to prove this verification happened.
        
        Args:
            symbol: Stock symbol (e.g., "300750.SZ", "600519.SH")
        
        Returns:
            TickerVerificationResult with verified identity, confidence, and verification_id
        
        Confidence levels:
        - high: found in Tushare stock_basic, listed
        - medium: found but delisted/suspended
        - low: not found or data incomplete
        """
        import uuid
        now = datetime.now()
        verification_id = f"verify_{uuid.uuid4().hex[:16]}_{int(now.timestamp())}"

        try:
            # Query Tushare stock_basic API
            df = self.tushare_client.query(
                "stock_basic",
                ts_code=symbol,
                fields="ts_code,name,area,industry,market,list_status,list_date,delist_date",
            )

            if df is None or df.empty:
                # Not found in Tushare
                return TickerVerificationResult(
                    verification_id=verification_id,
                    company_name="",
                    ticker=symbol,
                    exchange="",
                    status="unknown",
                    confidence="low",
                    source="tushare",
                    notes=f"Stock {symbol} not found in Tushare stock_basic",
                    verified_at=now,
                )

            # Extract data
            row = df.iloc[0]
            ts_code = row["ts_code"]
            company_name = row["name"]
            list_status = row["list_status"]  # L=listed, D=delisted, P=paused
            delist_date = row.get("delist_date")

            # Determine exchange from ts_code suffix
            if ts_code.endswith(".SH"):
                exchange = "SSE"  # Shanghai Stock Exchange
            elif ts_code.endswith(".SZ"):
                exchange = "SZSE"  # Shenzhen Stock Exchange
            elif ts_code.endswith(".BJ"):
                exchange = "BSE"  # Beijing Stock Exchange
            else:
                exchange = "unknown"

            # Determine status and confidence
            if list_status == "L":
                status = "listed"
                confidence = "high"
                notes = f"Listed on {exchange}"
            elif list_status == "D":
                status = "delisted"
                confidence = "medium"
                notes = f"Delisted on {delist_date}" if delist_date else "Delisted"
            elif list_status == "P":
                status = "suspended"
                confidence = "medium"
                notes = "Trading paused"
            else:
                status = "unknown"
                confidence = "low"
                notes = f"Unknown list_status: {list_status}"

            return TickerVerificationResult(
                verification_id=verification_id,
                company_name=company_name,
                ticker=ts_code,
                exchange=exchange,
                status=status,
                confidence=confidence,
                source="tushare",
                notes=notes,
                verified_at=now,
            )

        except Exception as e:
            # API call failed
            return TickerVerificationResult(
                verification_id=verification_id,
                company_name="",
                ticker=symbol,
                exchange="",
                status="unknown",
                confidence="low",
                source="tushare",
                notes=f"Tushare API error: {str(e)}",
                verified_at=now,
            )

    def validate_candidate(
        self,
        symbol: str,
        company_name: str | None,
        is_listed: bool | None,
        is_st: bool | None,
        is_suspended: bool | None,
        avg_daily_volume: float | None,
    ) -> ValidationResult:
        """
        Validate a candidate stock.
        
        Args:
            symbol: Stock symbol
            company_name: Company name (None if unknown)
            is_listed: Whether stock is currently listed
            is_st: Whether stock is ST/ST*
            is_suspended: Whether stock is suspended
            avg_daily_volume: Average daily trading volume (RMB)
        
        Returns:
            ValidationResult with flags and validity status
        """
        flags = []

        # Check unknown symbol
        if company_name is None:
            flags.append("unknown_symbol")

        # Check not listed. Unknown is not a pass.
        if is_listed is None:
            flags.append("unknown_listing_status")
        elif not is_listed:
            flags.append("not_listed")

        # Check ST. Unknown is not a pass.
        if is_st is None:
            flags.append("unknown_st_status")
        elif is_st:
            flags.append("is_st")

        # Check suspended. Unknown is not a pass.
        if is_suspended is None:
            flags.append("unknown_suspension_status")
        elif is_suspended:
            flags.append("is_suspended")

        # Check low liquidity. Unknown is not a pass.
        if avg_daily_volume is None:
            flags.append("unknown_liquidity")
        elif avg_daily_volume < self.liquidity_threshold:
            flags.append("low_liquidity")

        is_valid = len(flags) == 0
        return ValidationResult(flags=flags, is_valid=is_valid)

    def get_hard_filter_snapshot(self, symbol: str, verified_status: str) -> HardFilterSnapshot:
        """Collect hard-filter facts from deterministic market data tools."""
        now = datetime.now()
        gaps: list[str] = []

        is_listed = verified_status == "listed" if verified_status != "unknown" else None
        is_suspended = verified_status == "suspended" if verified_status != "unknown" else None
        is_st: bool | None = None
        avg_daily_volume: float | None = None

        try:
            stock_df = self.tushare_client.query(
                "stock_basic",
                ts_code=symbol,
                fields="ts_code,name,list_status",
            )
            if stock_df is None or stock_df.empty:
                gaps.append("stock_basic_missing")
            else:
                name = str(stock_df.iloc[0].get("name") or "")
                is_st = name.upper().startswith("ST") or name.upper().startswith("*ST")
        except Exception as exc:
            gaps.append(f"stock_basic_error:{exc}")

        try:
            daily_df = self.tushare_client.query(
                "daily_basic",
                ts_code=symbol,
                fields="ts_code,trade_date,amount",
            )
            if daily_df is None or daily_df.empty or "amount" not in daily_df:
                gaps.append("daily_basic_amount_missing")
            else:
                amount_values = daily_df["amount"].dropna()
                if amount_values.empty:
                    gaps.append("daily_basic_amount_missing")
                else:
                    avg_daily_volume = float(amount_values.astype(float).mean())
        except Exception as exc:
            gaps.append(f"daily_basic_error:{exc}")

        return HardFilterSnapshot(
            is_listed=is_listed,
            is_st=is_st,
            is_suspended=is_suspended,
            avg_daily_volume=avg_daily_volume,
            source="tushare",
            retrieved_at=now,
            gaps=gaps,
        )
