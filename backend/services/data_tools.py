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

import json
import re
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from contracts.research import DataToolResult


class DataToolsService:
    """
    Service that provides data tools for Evidence Agent.

    Each tool accepts a symbol and returns DataToolResult.
    Never returns data for symbols not explicitly requested.
    Missing fields are NOT filled with defaults.
    """

    def __init__(self, tushare_client=None, sse_transport=None):
        """
        Initialize data tools service.

        Args:
            tushare_client: TushareClient instance for API access.
                            If None, tools that require Tushare will report errors.
        """
        self._tushare = tushare_client
        self._sse_transport = sse_transport

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
            row_symbol = row.get("ts_code") if "ts_code" in row.index else None
            if not isinstance(row_symbol, str) or row_symbol != symbol:
                gaps.append("income.ts_code_mismatch")
                continue

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

    _ANNOUNCEMENT_FIELDS = [
        "ann_date", "ts_code", "name", "title", "url", "rec_time",
    ]

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

        Preserved fields per announcement follow Tushare's anns_d contract:
        ann_date, ts_code, name, title, url, and rec_time.

        Keyword filtering is deterministic string matching — no LLM involved.

        Args:
            symbol: Stock symbol (e.g. '300750.SZ')
            start_date: Optional start date filter (YYYYMMDD)
            end_date: Optional end date filter (YYYYMMDD)
            keywords: Optional keyword list for title matching

        Returns:
            DataToolResult with raw_data, gaps, and errors
        """
        # Shanghai-listed symbols use the SSE metadata list when that transport
        # is configured. Keeping the existing provider path when it is absent
        # preserves callers that have not yet opted into the SSE transport.
        if self._is_sse_symbol(symbol) and self._sse_transport is not None:
            return self._get_sse_announcements(symbol, keywords=keywords)

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
                "anns_d",
                ts_code=symbol,
                start_date=start_date,
                end_date=end_date,
                fields=",".join(self._ANNOUNCEMENT_FIELDS),
            )
        except Exception as exc:
            return DataToolResult(
                tool_name="get_announcements",
                raw_data=[],
                source="tushare_anns",
                retrieved_at=now,
                gaps=[],
                errors=[f"Tushare anns_d API call failed: {exc}"],
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

        preserved_fields = self._ANNOUNCEMENT_FIELDS

        for _, row in df.iterrows():
            row_symbol = row.get("ts_code") if "ts_code" in row.index else None
            if not isinstance(row_symbol, str) or row_symbol != symbol:
                gaps.append("anns_d.ts_code_mismatch")
                continue

            record: dict = {}
            row_gaps: list[str] = []
            for field in preserved_fields:
                val = row.get(field) if field in row.index else None
                if val is None or (isinstance(val, float) and str(val) == "nan"):
                    row_gaps.append(f"anns_d.{field}_missing")
                else:
                    if hasattr(val, "item"):
                        val = val.item()
                    record[field] = val
            # Only include announcement if it has a title
            if not record.get("title"):
                row_gaps.append("anns_d.title_missing")
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
                gaps.append(f"anns_d.{field}_missing_all_rows")
            elif present < len(raw_data):
                gaps.append(f"anns_d.{field}_partial({present}/{len(raw_data)})")

        return DataToolResult(
            tool_name="get_announcements",
            raw_data=raw_data,
            source="tushare_anns",
            retrieved_at=now,
            gaps=gaps,
            errors=errors,
        )

    @staticmethod
    def _is_sse_symbol(symbol: str) -> bool:
        return isinstance(symbol, str) and re.fullmatch(r"\d{6}\.SH", symbol) is not None

    @staticmethod
    def _normalize_sse_url(value: str) -> str | None:
        if not isinstance(value, str):
            return None
        url = value.strip()
        if not url or url.startswith("//"):
            return None

        input_url = urlparse(url)
        if input_url.scheme or input_url.netloc:
            if input_url.scheme.lower() != "https" or not input_url.netloc:
                return None
        elif url.startswith("/disclosure/"):
            url = "https://static.sse.com.cn" + url
        elif url.startswith("disclosure/"):
            url = "https://static.sse.com.cn/" + url
        else:
            return None

        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            port = parsed.port
        except ValueError:
            return None
        if (
            parsed.scheme != "https"
            or not (host == "sse.com.cn" or host.endswith(".sse.com.cn"))
            or parsed.username is not None
            or parsed.password is not None
            or port not in (None, 443)
        ):
            return None
        return url

    @staticmethod
    def _parse_sse_payload(body: bytes | str) -> dict:
        if isinstance(body, bytes):
            text = body.decode("utf-8-sig")
        elif isinstance(body, str):
            text = body.lstrip("\ufeff")
        else:
            raise ValueError("SSE response body must be text or bytes")
        text = text.strip()

        if text.startswith("{"):
            payload = json.loads(text)
        else:
            match = re.fullmatch(
                r"jsonpCallback72641\s*\((.*)\)\s*;?",
                text,
                flags=re.DOTALL,
            )
            if match is None:
                raise ValueError("SSE response is neither JSON nor expected JSONP")
            payload = json.loads(match.group(1))
        if not isinstance(payload, dict):
            raise ValueError("SSE response must be a JSON object")
        if not isinstance(payload.get("result"), list):
            raise ValueError("SSE response is missing result list")
        if not isinstance(payload.get("pageHelp"), dict):
            raise ValueError("SSE response is missing pageHelp object")
        return payload

    def _fetch_sse_response(self, url: str, *, headers: dict, timeout: int):
        request = Request(url, headers=headers, method="GET")
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()

    def _get_sse_announcements(
        self,
        symbol: str,
        *,
        keywords: list[str] | None,
    ) -> DataToolResult:
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        end_day = now.date()
        begin_day = end_day - timedelta(days=179)
        begin_date = begin_day.isoformat()
        end_date = end_day.isoformat()
        gaps: list[str] = []
        errors: list[str] = []
        raw_data: list[dict] = []

        params = {
            "isPagination": "true",
            "productId": symbol[:6],
            "keyWord": "",
            "isNew": "1",
            "reportType2": "",
            "reportType": "ALL",
            "beginDate": begin_date,
            "endDate": end_date,
            "pageHelp.pageSize": "20",
            "pageHelp.pageCount": "50",
            "pageHelp.pageNo": "1",
            "pageHelp.beginPage": "1",
            "pageHelp.cacheSize": "1",
            "pageHelp.endPage": "5",
            "jsonCallBack": "jsonpCallback72641",
        }
        url = (
            "https://query.sse.com.cn/security/stock/queryCompanyStatementNew.do?"
            + urlencode(params)
        )
        headers = {
            "Accept": "application/json,*/*",
            "Referer": (
                "https://www.sse.com.cn/assortment/stock/list/info/announcement/"
                f"index.shtml?productId={symbol[:6]}"
            ),
            "User-Agent": "Mozilla/5.0",
        }

        try:
            status, _content_type, body = self._sse_transport(
                url, headers=headers, timeout=15,
            )
            if status != 200:
                raise ValueError(f"SSE announcement request returned HTTP {status}")
            payload = self._parse_sse_payload(body)
        except Exception as exc:
            return DataToolResult(
                tool_name="get_announcements",
                raw_data=[],
                source="sse_company_announcements",
                retrieved_at=now,
                gaps=[],
                errors=[f"SSE announcement list failed: {exc}"],
            )

        if not payload["result"]:
            return DataToolResult(
                tool_name="get_announcements",
                raw_data=[],
                source="sse_company_announcements",
                retrieved_at=now,
                gaps=["announcements_data_empty"],
                errors=[],
            )

        keyword_set = {item.casefold() for item in (keywords or []) if item}
        for index, row in enumerate(payload["result"]):
            if not isinstance(row, dict):
                errors.append(f"SSE announcement row {index} is not an object")
                continue

            raw_code = row.get("security_Code") or row.get("SECURITY_CODE")
            if isinstance(raw_code, str):
                raw_code = raw_code.strip().upper()
                row_code = f"{raw_code}.SH" if re.fullmatch(r"\d{6}", raw_code) else raw_code
            else:
                row_code = ""
            title = row.get("title") or row.get("TITLE")
            raw_date = row.get("SSEDate") or row.get("SSEDATE")
            raw_url = row.get("URL") or row.get("url")

            missing = []
            if not row_code:
                missing.append("security code")
            if not isinstance(raw_date, str) or not raw_date.strip():
                missing.append("SSEDate")
            if not isinstance(title, str) or not title.strip():
                missing.append("title")
            if not isinstance(raw_url, str) or not raw_url.strip():
                missing.append("URL")
            if missing:
                errors.append(
                    f"SSE announcement row {index} missing required field(s): "
                    + ", ".join(missing)
                )
                continue

            try:
                date_text = raw_date.strip()
                published = datetime.strptime(
                    date_text, "%Y-%m-%d" if "-" in date_text else "%Y%m%d",
                ).date()
            except ValueError:
                errors.append(f"SSE announcement row {index} has invalid SSEDate")
                continue
            official_url = self._normalize_sse_url(raw_url)
            if official_url is None:
                errors.append(f"SSE announcement row {index} has a non-official URL")
                continue
            if row_code != symbol:
                gaps.append(f"sse_announcement_code_mismatch({row_code})")
                continue
            if published < begin_day or published > end_day:
                gaps.append("sse_announcement_outside_180_day_window")
                continue

            title = title.strip()
            if keyword_set and not any(word in title.casefold() for word in keyword_set):
                continue
            raw_data.append({
                "source": "sse",
                "code": symbol,
                "date": published.isoformat(),
                "title": title,
                "url": official_url,
                "retrieved_at": now,
                "gaps": ["full_text_unavailable"],
            })
            if len(raw_data) == 20:
                break

        if not raw_data and not errors and not gaps:
            gaps.append("announcements_filtered_by_keywords")
        return DataToolResult(
            tool_name="get_announcements",
            raw_data=raw_data,
            source="sse_company_announcements",
            retrieved_at=now,
            gaps=gaps,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # get_sector_and_peers
    # ------------------------------------------------------------------

    _COMPANY_PROFILE_FIELDS = "ts_code,com_name,main_business,business_scope"

    def get_company_profile(self, symbol: str) -> DataToolResult:
        """Fetch one symbol's reported company-main-business profile."""
        now = datetime.now()
        gaps: list[str] = []

        if self._tushare is None:
            return DataToolResult(
                tool_name="get_company_profile",
                raw_data=[],
                source="tushare_stock_company",
                retrieved_at=now,
                gaps=["tushare_client_not_configured"],
                errors=["No Tushare client available"],
            )

        try:
            df = self._tushare.query(
                "stock_company",
                ts_code=symbol,
                fields=self._COMPANY_PROFILE_FIELDS,
            )
        except Exception as exc:
            return DataToolResult(
                tool_name="get_company_profile",
                raw_data=[],
                source="tushare_stock_company",
                retrieved_at=now,
                gaps=[],
                errors=[f"Tushare stock_company query failed: {exc}"],
            )

        if df is None or len(df) == 0:
            return DataToolResult(
                tool_name="get_company_profile",
                raw_data=[],
                source="tushare_stock_company",
                retrieved_at=now,
                gaps=["stock_company_data_empty"],
                errors=[],
            )

        raw_data: list[dict] = []
        for _, row in df.iterrows():
            row_symbol = row.get("ts_code") if "ts_code" in row.index else None
            if not isinstance(row_symbol, str) or row_symbol != symbol:
                gaps.append("stock_company.ts_code_mismatch")
                continue

            main_business = row.get("main_business")
            if not isinstance(main_business, str) or not main_business.strip():
                gaps.append("stock_company.main_business_missing")
                continue

            record = {
                "ts_code": row_symbol,
                "main_business": main_business.strip(),
            }
            for field in ("com_name", "business_scope"):
                value = row.get(field) if field in row.index else None
                if isinstance(value, str) and value.strip():
                    record[field] = value.strip()
            raw_data.append(record)

        if not raw_data and not gaps:
            gaps.append("stock_company_no_valid_profile")

        return DataToolResult(
            tool_name="get_company_profile",
            raw_data=raw_data,
            source="tushare_stock_company",
            retrieved_at=now,
            gaps=gaps,
            errors=[],
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
