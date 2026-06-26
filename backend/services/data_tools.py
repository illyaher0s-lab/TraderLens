"""
Data tools for Evidence Agent.

All tools return the unified DataToolResult contract:
- raw_data: list[dict] — raw records from data source (NO filling)
- gaps: list[str] — data gaps detected (missing fields, empty results)
- errors: list[str] — data source errors (API failures, timeouts)
- source: str — data source identifier
- retrieved_at: datetime — when data was fetched

LLM may only read and summarise tool results. It must not fabricate, fill,
or interpret missing data as "normal". Missing data is always recorded as a gap.

Tools:
- get_financials(symbol) — Tushare income API
- get_announcements(symbol) — (pending)
- get_sector_and_peers(symbol) — (pending)
"""

from __future__ import annotations

from datetime import datetime
from contracts.research import DataToolResult


class DataToolsService:
    """
    Service that provides data tools for Evidence Agent.

    Each tool accepts a symbol and returns DataToolResult.
    Never returns data for symbols not explicitly requested.
    Missing fields are NOT filled with defaults.
    """

    def __init__(self, tushare_client=None):
        """
        Initialize data tools service.

        Args:
            tushare_client: TushareClient instance for API access.
                            If None, tools that require Tushare will report errors.
        """
        self._tushare = tushare_client

    # ------------------------------------------------------------------
    # get_financials
    # ------------------------------------------------------------------

    _INCOME_FIELDS = [
        "ts_code", "end_date", "ann_date", "report_type",
        "total_revenue", "revenue", "oper_cost", "operate_profit",
        "total_profit", "n_income", "n_income_attr_p", "basic_eps",
        "diluted_eps", "ebit", "ebitda",
    ]

    def get_financials(self, symbol: str) -> DataToolResult:
        """
        Fetch financial data (income statement) from Tushare.

        Returns the most recent 4 reporting periods. Fields that are missing
        in the API response are NOT filled with defaults — they are recorded
        as gaps.

        Args:
            symbol: Stock symbol (e.g. '300750.SZ')

        Returns:
            DataToolResult with raw_data, gaps, and errors
        """
        now = datetime.now()
        gaps: list[str] = []
        errors: list[str] = []
        raw_data: list[dict] = []

        if self._tushare is None:
            return DataToolResult(
                tool_name="get_financials",
                raw_data=[],
                source="tushare_income",
                retrieved_at=now,
                gaps=["tushare_client_not_configured"],
                errors=["No Tushare client available"],
            )

        try:
            df = self._tushare.query(
                "income",
                ts_code=symbol,
                fields=",".join(self._INCOME_FIELDS),
                limit=4,
            )
        except Exception as exc:
            return DataToolResult(
                tool_name="get_financials",
                raw_data=[],
                source="tushare_income",
                retrieved_at=now,
                gaps=[],
                errors=[f"Tushare income API call failed: {exc}"],
            )

        if df is None or len(df) == 0:
            return DataToolResult(
                tool_name="get_financials",
                raw_data=[],
                source="tushare_income",
                retrieved_at=now,
                gaps=["income_data_empty"],
                errors=[],
            )

        # Convert DataFrame to list of dicts, recording missing fields
        for _, row in df.iterrows():
            record: dict = {}
            row_gaps: list[str] = []
            for field in self._INCOME_FIELDS:
                val = row.get(field)
                if val is None or (isinstance(val, float) and str(val) == "nan"):
                    row_gaps.append(f"income.{field}_missing")
                else:
                    # Convert numpy/pandas types to native Python
                    if hasattr(val, "item"):
                        val = val.item()
                    record[field] = val
            raw_data.append(record)
            if row_gaps:
                gaps.append(f"row_{len(raw_data)}: {', '.join(row_gaps)}")

        # Check overall field coverage
        expected_count = len(raw_data)
        for field in ("total_revenue", "n_income", "basic_eps"):
            present = sum(1 for r in raw_data if field in r)
            if present == 0:
                gaps.append(f"income.{field}_missing_all_rows")
            elif present < expected_count:
                gaps.append(f"income.{field}_partial({present}/{expected_count})")

        return DataToolResult(
            tool_name="get_financials",
            raw_data=raw_data,
            source="tushare_income",
            retrieved_at=now,
            gaps=gaps,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # get_announcements
    # ------------------------------------------------------------------

    _ANNS_FIELDS = [
        "ts_code", "ann_date", "title", "ann_type",
        "pub_date", "content_type",
    ]
    _ANNS_OPTIONAL_FIELDS = ["file_url"]

    def get_announcements(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        keywords: list[str] | None = None,
    ) -> DataToolResult:
        """
        Fetch corporate announcements from Tushare.

        Returns announcements for the given symbol. Supports optional date
        range filtering (start_date/end_date in YYYYMMDD format) and keyword
        filtering (case-insensitive substring matching on title).

        Preserved fields per announcement:
        - ts_code (symbol)
        - ann_date (announcement date)
        - title (announcement title)
        - ann_type (announcement type code)
        - pub_date (publish date)

        Keyword filtering is deterministic string matching — no LLM involved.

        Args:
            symbol: Stock symbol (e.g. '300750.SZ')
            start_date: Optional start date filter (YYYYMMDD)
            end_date: Optional end date filter (YYYYMMDD)
            keywords: Optional keyword list for title matching

        Returns:
            DataToolResult with raw_data, gaps, and errors
        """
        now = datetime.now()
        gaps: list[str] = []
        errors: list[str] = []
        raw_data: list[dict] = []

        if self._tushare is None:
            return DataToolResult(
                tool_name="get_announcements",
                raw_data=[],
                source="tushare_anns",
                retrieved_at=now,
                gaps=["tushare_client_not_configured"],
                errors=["No Tushare client available"],
            )

        try:
            df = self._tushare.query(
                "anns",
                ts_code=symbol,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as exc:
            return DataToolResult(
                tool_name="get_announcements",
                raw_data=[],
                source="tushare_anns",
                retrieved_at=now,
                gaps=[],
                errors=[f"Tushare anns API call failed: {exc}"],
            )

        if df is None or len(df) == 0:
            return DataToolResult(
                tool_name="get_announcements",
                raw_data=[],
                source="tushare_anns",
                retrieved_at=now,
                gaps=["announcements_data_empty"],
                errors=[],
            )

        # Convert DataFrame — preserved: symbol, ann_date, title, ann_type, pub_date
        preserved_fields = [
            "ts_code", "ann_date", "title", "ann_type", "pub_date",
        ]

        for _, row in df.iterrows():
            record: dict = {}
            row_gaps: list[str] = []
            for field in preserved_fields:
                val = row.get(field) if field in row.index else None
                if val is None or (isinstance(val, float) and str(val) == "nan"):
                    row_gaps.append(f"anns.{field}_missing")
                else:
                    if hasattr(val, "item"):
                        val = val.item()
                    record[field] = val
            # Only include announcement if it has a title
            if not record.get("title"):
                row_gaps.append("anns.title_missing")
                gaps.append(f"row_{len(raw_data) + 1}: {', '.join(row_gaps)}")
                continue
            raw_data.append(record)
            if row_gaps:
                gaps.append(f"row_{len(raw_data)}: {', '.join(row_gaps)}")

        # --- Deterministic filtering ---

        # 1) Date range filtering (already requested via API, but double-check)
        filtered_by_date = 0
        if start_date or end_date:
            keep = []
            for r in raw_data:
                ann_date = r.get("ann_date", "")
                if start_date and ann_date < start_date:
                    filtered_by_date += 1
                    continue
                if end_date and ann_date > end_date:
                    filtered_by_date += 1
                    continue
                keep.append(r)
            raw_data = keep
        if filtered_by_date > 0:
            gaps.append(f"announcements_filtered_by_date({filtered_by_date})")

        # 2) Keyword filtering (deterministic substring match)
        if keywords:
            kw_set = {k.lower() for k in keywords if k}
            if kw_set:
                keep = []
                for r in raw_data:
                    title = (r.get("title") or "").lower()
                    if any(kw in title for kw in kw_set):
                        keep.append(r)
                filtered_out = len(raw_data) - len(keep)
                raw_data = keep
                if filtered_out > 0:
                    gaps.append(
                        f"announcements_filtered_by_keywords({filtered_out} "
                        f"of {len(raw_data) + filtered_out})"
                    )

        # Post-filter emptiness check
        if len(raw_data) == 0:
            return DataToolResult(
                tool_name="get_announcements",
                raw_data=[],
                source="tushare_anns",
                retrieved_at=now,
                gaps=gaps or ["announcements_data_empty_after_filter"],
                errors=errors,
            )

        # Check field coverage across remaining rows
        for field in preserved_fields:
            present = sum(1 for r in raw_data if field in r)
            if present == 0:
                gaps.append(f"anns.{field}_missing_all_rows")
            elif present < len(raw_data):
                gaps.append(f"anns.{field}_partial({present}/{len(raw_data)})")

        return DataToolResult(
            tool_name="get_announcements",
            raw_data=raw_data,
            source="tushare_anns",
            retrieved_at=now,
            gaps=gaps,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # get_sector_and_peers
    # ------------------------------------------------------------------

    def get_sector_and_peers(
        self,
        symbol: str,
        snapshot_date: str | None = None,
    ) -> DataToolResult:
        """
        Fetch industry classification and peer stocks from Tushare.

        Industry and peer list are sourced from Tushare stock_basic — NOT
        inferred by LLM. Model summaries must be separated from raw facts.

        Args:
            symbol: Stock symbol (e.g. '300750.SZ')
            snapshot_date: Snapshot date (YYYYMMDD). Records the point-in-time
                           validity of the classification. If None, a gap is
                           recorded — the current date is NEVER used as a
                           silent default.

        Returns:
            DataToolResult with:
            - raw_data[0]: dict with symbol, industry, classification_source,
                           snapshot_date (or gap), peer_symbols, peer_company_names
        """
        now = datetime.now()
        gaps: list[str] = []
        errors: list[str] = []

        # snapshot_date is mandatory — never silently default to "today"
        if snapshot_date is None:
            gaps.append("snapshot_date_missing")

        if self._tushare is None:
            return DataToolResult(
                tool_name="get_sector_and_peers",
                raw_data=[],
                source="tushare_stock_basic",
                retrieved_at=now,
                gaps=gaps + (["tushare_client_not_configured"] if not gaps else []),
                errors=["No Tushare client available"] if not gaps else [],
            )

        # Step 1: get industry from stock_basic
        try:
            target_df = self._tushare.query(
                "stock_basic",
                ts_code=symbol,
                fields="ts_code,name,industry,list_status",
            )
        except Exception as exc:
            return DataToolResult(
                tool_name="get_sector_and_peers",
                raw_data=[],
                source="tushare_stock_basic",
                retrieved_at=now,
                gaps=gaps,
                errors=[f"Tushare stock_basic query failed: {exc}"],
            )

        if target_df is None or len(target_df) == 0:
            return DataToolResult(
                tool_name="get_sector_and_peers",
                raw_data=[],
                source="tushare_stock_basic",
                retrieved_at=now,
                gaps=gaps + ["stock_basic_missing_for_target"],
                errors=[],
            )

        target_row = target_df.iloc[0]
        company_name = target_row.get("name")
        industry = target_row.get("industry")
        list_status = target_row.get("list_status")

        # Record gapped fields in the target row
        if company_name is None or (isinstance(company_name, float) and str(company_name) == "nan"):
            gaps.append("target_company_name_missing")
            company_name = None
        else:
            if hasattr(company_name, "item"):
                company_name = company_name.item()

        if industry is None or (isinstance(industry, float) and str(industry) == "nan") or str(industry).strip() == "":
            gaps.append("industry_unknown_for_target")
            # Cannot proceed to find peers without industry
            return DataToolResult(
                tool_name="get_sector_and_peers",
                raw_data=[{
                    "symbol": symbol,
                    "company_name": company_name,
                    "industry": None,
                    "classification_source": None,
                    "snapshot_date": snapshot_date,
                    "peer_symbols": [],
                    "peer_company_names": [],
                }],
                source="tushare_stock_basic",
                retrieved_at=now,
                gaps=gaps,
                errors=[],
            )
        else:
            if hasattr(industry, "item"):
                industry = industry.item()

        # Step 2: find peers in the same industry
        try:
            peers_df = self._tushare.query(
                "stock_basic",
                industry=str(industry),
                fields="ts_code,name,industry,list_status",
            )
        except Exception as exc:
            return DataToolResult(
                tool_name="get_sector_and_peers",
                raw_data=[{
                    "symbol": symbol,
                    "company_name": company_name,
                    "industry": industry,
                    "classification_source": "tushare_stock_basic",
                    "snapshot_date": snapshot_date,
                    "peer_symbols": [],
                    "peer_company_names": [],
                }],
                source="tushare_stock_basic",
                retrieved_at=now,
                gaps=gaps,
                errors=[f"Tushare industry peers query failed: {exc}"],
            )

        if peers_df is None or len(peers_df) == 0:
            return DataToolResult(
                tool_name="get_sector_and_peers",
                raw_data=[{
                    "symbol": symbol,
                    "company_name": company_name,
                    "industry": industry,
                    "classification_source": "tushare_stock_basic",
                    "snapshot_date": snapshot_date,
                    "peer_symbols": [],
                    "peer_company_names": [],
                }],
                source="tushare_stock_basic",
                retrieved_at=now,
                gaps=gaps + ["no_peers_found_in_industry"],
                errors=[],
            )

        peer_symbols: list[str] = []
        peer_names: list[str] = []

        for _, row in peers_df.iterrows():
            peer_ts_code = row.get("ts_code")
            peer_name = row.get("name")

            # Skip self
            if peer_ts_code == symbol:
                continue

            # Identity check: peer must have a valid name
            if peer_name is None or (isinstance(peer_name, float) and str(peer_name) == "nan"):
                gaps.append(f"peer_identity_missing:name({peer_ts_code})")
                continue
            if hasattr(peer_name, "item"):
                peer_name = peer_name.item()

            if peer_ts_code is None:
                gaps.append(f"peer_identity_missing:ts_code")
                continue
            if hasattr(peer_ts_code, "item"):
                peer_ts_code = peer_ts_code.item()

            peer_symbols.append(peer_ts_code)
            peer_names.append(peer_name)

        if len(peer_symbols) == 0:
            gaps.append("no_peers_after_identity_check")

        return DataToolResult(
            tool_name="get_sector_and_peers",
            raw_data=[{
                "symbol": symbol,
                "company_name": company_name,
                "industry": industry,
                "classification_source": "tushare_stock_basic",
                "snapshot_date": snapshot_date,
                "peer_symbols": peer_symbols,
                "peer_company_names": peer_names,
            }],
            source="tushare_stock_basic",
            retrieved_at=now,
            gaps=gaps,
            errors=errors,
        )
