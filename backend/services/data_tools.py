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
import math
import re
from datetime import date, datetime, timedelta
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from contracts.research import DataToolResult


# 510880 raw m_fee/c_fee values 0.5/0.1 match the SSE 2026-06-13 prospectus's annual rates 0.50%/0.10%.
_SSE_510880_FEE_SOURCE = "https://www.sse.com.cn/disclosure/fund/announcement/c/new/2026-06-13/510880_20260613_RW6R.pdf"
# Tushare total_netasset=19,086,808,965.54 on 2025-06-30 exactly matches the SSE H1 report's RMB net assets.
_SSE_510880_SCALE_SOURCE = "https://www.sse.com.cn/disclosure/fund/announcement/c/new/2025-08-30/510880_20250830_FK6G.pdf"
_TUSHARE_FUND_SHARE_DOCS = "https://tushare.pro/document/2?doc_id=207"
_DIVIDEND_YIELD_HISTORY_COVERAGE_MIN = 0.90


def _trailing_yield_valuation_label(percentile: float) -> str:
    if percentile >= 80.0:
        return "相对历史偏便宜"
    if percentile <= 20.0:
        return "相对历史偏贵"
    return "中性"


def _classify_etf_category(fund_type: object, benchmark: object) -> str:
    """Classify only from the exact fund type and full benchmark returned for the ETF."""
    kind = fund_type.strip() if isinstance(fund_type, str) else ""
    basis = benchmark.strip() if isinstance(benchmark, str) else ""
    if not kind or not basis:
        return "unclassified"
    if kind != "股票型":
        return "other"

    if "红利" in basis or "股息" in basis:
        return "dividend"
    if any(token in basis for token in (
        "医药", "医疗", "证券公司", "银行", "行业", "半导体", "芯片", "新能源",
        "光伏", "军工", "传媒", "通信", "计算机", "房地产", "煤炭", "有色",
        "白酒", "消费", "汽车", "电力", "农业", "钢铁", "化工",
    )):
        return "industry"
    if any(token in basis for token in (
        "沪深300指数", "上证50成份指数", "上证50指数", "中证500指数",
        "中证1000指数", "中证800指数", "上证综指", "深证成份指数",
        "中小企业100指数", "创业板指数", "创业板50指数", "科创板50成份指数",
        "科创50指数", "中证A50指数", "中证A500指数",
    )):
        return "broad"
    return "unclassified"


def _etf_valuation_conclusion(
    category: str,
    *,
    pe_percentile: float | None = None,
    pb_percentile: float | None = None,
    dividend_yield_percentile: float | None = None,
) -> dict:
    """Apply fixed research-only ETF valuation bands without model judgment."""
    def valid_percentile(value: float | None) -> bool:
        return value is not None and math.isfinite(value) and 0.0 <= value <= 100.0

    def result(status, verdict, label, basis, message, invalidation_condition):
        return {
            "status": status,
            "verdict": verdict,
            "label": label,
            "basis": basis,
            "message": message,
            "invalidation_condition": invalidation_condition,
        }

    if category == "other" or category == "unclassified":
        return result(
            "not_supported", "research_unavailable", None, None,
            "该类型暂不提供估值判断",
            "该类型暂无经验证的估值判断规则；补齐适用规则前不形成估值结论。",
        )

    has_pe = valid_percentile(pe_percentile)
    has_pb = valid_percentile(pb_percentile)
    if has_pe and has_pb:
        cheap = pe_percentile <= 20.0 and pb_percentile <= 20.0
        expensive = pe_percentile >= 80.0 and pb_percentile >= 80.0
        conflict = (
            (pe_percentile <= 20.0 and pb_percentile >= 80.0)
            or (pb_percentile <= 20.0 and pe_percentile >= 80.0)
        )
        if conflict:
            return result(
                "conclusive", "research_watch", "估值信号冲突，观察", "index_pe_pb",
                "跟踪指数PE与PB分位处于相反区间，信号冲突，暂观察。",
                "若同一跟踪指数的完整十年PE/PB分位跨越20%或80%边界，按更新后的覆盖和分位重新评估；这不是交易止损。",
            )
        if cheap:
            return result(
                "conclusive", "research_positive", "相对偏便宜", "index_pe_pb",
                "跟踪指数PE与PB十年分位均处于低位，估值相对偏便宜。",
                "若同一跟踪指数PE或PB十年分位升至20%以上，撤回相对偏便宜判断并重评；这不是交易止损。",
            )
        if expensive:
            return result(
                "conclusive", "research_reject", "相对偏贵", "index_pe_pb",
                "跟踪指数PE与PB十年分位均处于高位，估值相对偏贵。",
                "若同一跟踪指数PE或PB十年分位降至80%以下，撤回相对偏贵判断并重评；这不是交易止损。",
            )
        return result(
            "conclusive", "research_watch", "估值中性，观察", "index_pe_pb",
            "跟踪指数PE与PB十年分位未同时落入相对便宜或偏贵区间，暂观察。",
            "若同一跟踪指数PE或PB十年分位跨越20%或80%边界，按更新后的完整覆盖重新评估；这不是交易止损。",
        )

    if category == "dividend" and not has_pe and not has_pb and valid_percentile(dividend_yield_percentile):
        value = dividend_yield_percentile
        label = _trailing_yield_valuation_label(value)
        if value >= 80.0:
            verdict = "research_positive"
            invalidation = "若ETF自身同口径股息率历史分位降至80%以下，撤回相对偏便宜判断并重评；这不是交易止损。"
        elif value <= 20.0:
            verdict = "research_reject"
            invalidation = "若ETF自身同口径股息率历史分位升至20%以上，撤回相对偏贵判断并重评；这不是交易止损。"
        else:
            verdict = "research_watch"
            invalidation = "若ETF自身同口径股息率历史分位进入20%或80%边界区间，撤回中性标签并重评；这不是交易止损。"
        return result(
            "conclusive", verdict, label, "own_dividend_yield",
            f"ETF自身已派付现金分红收益率历史分位{label}；仅与本ETF历史比较，不等同于指数估值",
            invalidation,
        )

    if category == "industry":
        message = "跟踪指数的估值数据未覆盖，暂不提供估值判断"
    else:
        message = "跟踪指数PE/PB十年分位未完整覆盖，暂不提供估值判断"
    return result(
        "data_gap", "research_unavailable", None, None, message,
        "补齐同一跟踪指数PE与PB的完整十年分位后再形成估值判断。",
    )


def _is_510880_dividend_valuation(symbol: str, index_code: str) -> bool:
    return symbol == "510880.SH" and index_code == "000015.SH"


def _etf_gap_categories(text: object) -> set[str]:
    """Map the small set of ETF evidence gaps to stable categories for deduplication."""
    if not isinstance(text, str):
        return set()
    value = text.casefold()
    categories = set()
    if any(token in value for token in ("成分", "持仓", "行业权重")):
        categories.add("holdings")
    if any(token in value for token in ("跟踪误差", "跟踪差异")):
        categories.add("tracking_error")
    if any(token in value for token in ("pe/pb", "指数估值", "跟踪指数估值")):
        categories.add("index_valuation")
    if "指数" in value and any(token in value for token in ("股息率", "股息收益率")):
        categories.add("index_dividend_yield")
    if any(token in value for token in ("现金分红", "已实施派息", "分红记录")):
        categories.add("cash_distribution")
    if "基金份额" in value or "份额规模" in value:
        categories.add("fund_shares")
    if "fund_daily" in value or ("收盘价" in value and ("缺少" in value or "覆盖" in value)):
        categories.add("price_history")
    if "成交额" in value:
        categories.add("trading_amount")
    if "净资产" in value or "资产规模" in value:
        categories.add("asset_scale")
    if "管理费" in value:
        categories.add("management_fee")
    if "托管费" in value:
        categories.add("custody_fee")
    return categories


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

    def get_security_quote_snapshot(
        self,
        symbol: str,
        security_type: str,
        *,
        as_of: date | None = None,
        lookback_days: int = 30,
    ) -> DataToolResult:
        """Fetch the latest dated close from the matching stock or fund API."""
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        if security_type not in {"stock", "fund"}:
            return DataToolResult(
                tool_name="get_security_quote_snapshot",
                raw_data=[],
                source="unknown",
                retrieved_at=now,
                gaps=["security_type_not_supported"],
                errors=[],
            )
        if self._tushare is None:
            return DataToolResult(
                tool_name="get_security_quote_snapshot",
                raw_data=[],
                source=f"tushare_{'fund_daily' if security_type == 'fund' else 'daily'}",
                retrieved_at=now,
                gaps=["tushare_client_not_configured"],
                errors=[],
            )
        if type(lookback_days) is not int or not 1 <= lookback_days <= 60:
            return DataToolResult(
                tool_name="get_security_quote_snapshot",
                raw_data=[],
                source=f"tushare_{'fund_daily' if security_type == 'fund' else 'daily'}",
                retrieved_at=now,
                gaps=["quote_lookback_invalid"],
                errors=[],
            )

        as_of_date = as_of or now.date()
        start_date = as_of_date - timedelta(days=lookback_days)
        api_name = "fund_daily" if security_type == "fund" else "daily"
        source = f"tushare_{api_name}"
        try:
            rows = self._tushare.query(
                api_name,
                ts_code=symbol,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=as_of_date.strftime("%Y%m%d"),
                fields="ts_code,trade_date,close",
            )
        except Exception:
            return DataToolResult(
                tool_name="get_security_quote_snapshot",
                raw_data=[],
                source=source,
                retrieved_at=now,
                gaps=["quote_request_failed"],
                errors=["行情接口请求失败，未返回可核验收盘数据。"],
            )

        if rows is None or getattr(rows, "empty", False) or len(rows) == 0:
            return DataToolResult(
                tool_name="get_security_quote_snapshot",
                raw_data=[],
                source=source,
                retrieved_at=now,
                gaps=["quote_data_empty"],
                errors=[],
            )

        valid_rows: list[tuple[date, float]] = []
        for _, row in rows.iterrows():
            if row.get("ts_code") != symbol:
                continue
            raw_date = row.get("trade_date")
            if isinstance(raw_date, datetime):
                trade_date = raw_date.date()
            elif isinstance(raw_date, date):
                trade_date = raw_date
            else:
                digits = "".join(char for char in str(raw_date or "") if char.isdigit())
                try:
                    trade_date = date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
                except (ValueError, IndexError):
                    continue
            if trade_date > as_of_date:
                continue
            raw_close = row.get("close")
            if raw_close is None or isinstance(raw_close, bool):
                continue
            try:
                close = float(raw_close)
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(close) and close > 0:
                valid_rows.append((trade_date, close))

        if not valid_rows:
            return DataToolResult(
                tool_name="get_security_quote_snapshot",
                raw_data=[],
                source=source,
                retrieved_at=now,
                gaps=["quote_code_date_or_close_unverified"],
                errors=[],
            )

        trade_date, close = max(valid_rows, key=lambda item: item[0])
        return DataToolResult(
            tool_name="get_security_quote_snapshot",
            raw_data=[{
                "ts_code": symbol,
                "trade_date": trade_date.isoformat(),
                "close": close,
            }],
            source=source,
            retrieved_at=now,
            gaps=[],
            errors=[],
        )

    @staticmethod
    def _finite_number(value) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _parse_trade_date(value) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        digits = "".join(character for character in str(value or "") if character.isdigit())
        if len(digits) < 8:
            return None
        try:
            return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            return None

    @staticmethod
    def _tushare_failure_status(exc: Exception) -> str:
        chain = []
        current: BaseException | None = exc
        seen: set[int] = set()
        while isinstance(current, BaseException) and id(current) not in seen:
            seen.add(id(current))
            chain.append(current)
            current = current.__cause__ or current.__context__
        text = " ".join(str(item) for item in chain).lower()
        class_names = " ".join(type(item).__name__.lower() for item in chain)
        if any(token in text or token in class_names for token in (
            "timeout", "timed out", "readtimeout", "connecttimeout",
        )):
            return "timeout"
        if any(token in text for token in (
            "permission", "no permission", "积分不足", "权限不足", "无权限", "未开通",
        )):
            return "permission_denied"
        if any(token in text for token in (
            "unknown api", "api not found", "api does not exist", "unsupported api",
            "接口不存在", "接口未实现", "接口不支持", "不支持该接口",
        )):
            return "unsupported_endpoint"
        return "provider_error"

    @staticmethod
    def _bundle_gap(api_name: str, status: str) -> str:
        if status == "empty_no_rows":
            return f"Tushare {api_name} 返回空结果，相关指标无法核验。"
        if status == "permission_denied":
            return f"Tushare {api_name} 明确返回权限不足，相关指标无法核验。"
        if status == "unsupported_endpoint":
            return f"Tushare {api_name} 明确报告接口不存在或不支持，相关指标无法核验。"
        if status == "timeout":
            return f"Tushare {api_name} 请求超时，相关指标无法核验。"
        if status == "provider_error":
            return f"Tushare {api_name} 请求失败，提供方错误类型未能进一步核实。"
        return f"Tushare {api_name} 数据未请求，相关指标无法核验。"

    def get_etf_research_bundle(
        self,
        symbol: str,
        *,
        as_of: date | None = None,
        now: datetime | None = None,
        calendar_rows: list[dict] | None = None,
    ) -> dict:
        """Fetch a source-bound ETF research bundle and compute its metrics deterministically."""
        shanghai = ZoneInfo("Asia/Shanghai")
        retrieved_at = datetime.now(shanghai)
        local_now = (
            datetime.combine(as_of, datetime.max.time(), tzinfo=shanghai)
            if as_of is not None
            else now.replace(tzinfo=shanghai) if now is not None and now.tzinfo is None
            else now.astimezone(shanghai) if now is not None
            else retrieved_at
        )
        reference_date = as_of or local_now.date()
        publish_cutoff = reference_date
        if as_of is None and local_now.hour < 18:
            publish_cutoff -= timedelta(days=1)
        as_of_date = reference_date
        start_1y = as_of_date - timedelta(days=365)
        start_10y = as_of_date - timedelta(days=3652)
        statuses: dict[str, str] = {}
        gaps: list[str] = []
        sources: list[dict] = []
        metrics: dict[str, dict | None] = {
            "etf_type": None,
            "fund_type": None,
            "benchmark": None,
            "underlying_index": None,
            "fund_found_date": None,
            "management_fee": None,
            "custody_fee": None,
            "latest_price": None,
            "fund_size_shares": None,
            "asset_scale": None,
            "average_amount_20d": None,
            "price_change_1y": None,
            "distance_from_1y_high_pct": None,
            "price_coverage_1y": None,
            "index_valuation_coverage": None,
            "trailing_cash_dividend_per_share": None,
            "trailing_dividend_yield": None,
            "trailing_dividend_yield_percentile_10y": None,
            "trailing_dividend_yield_valuation": None,
            "trailing_dividend_yield_coverage_10y": None,
            "underlying_pe": None,
            "underlying_pe_percentile_10y": None,
            "underlying_pb": None,
            "underlying_pb_percentile_10y": None,
            "underlying_dividend_yield": None,
        }
        bundle = {
            "symbol": symbol,
            "is_etf": False,
            "category": "unclassified",
            "fund_type": None,
            "benchmark": None,
            "valuation_conclusion": None,
            "as_of": as_of_date.isoformat(),
            "retrieved_at": retrieved_at.isoformat(),
            "metrics": metrics,
            "endpoint_statuses": statuses,
            "sources": sources,
            "gaps": gaps,
            "investment_assumption": None,
        }

        if self._tushare is None:
            statuses["etf_basic"] = "provider_error"
            gaps.append("Tushare client 未配置，ETF 映射和指标均无法核验。")
            return bundle

        def fetch(api_name: str, fields: str, expected_code: str, **params) -> list[dict]:
            try:
                frame = self._tushare.query(api_name, fields=fields, **params)
            except Exception as exc:
                status = self._tushare_failure_status(exc)
                statuses[api_name] = status
                gaps.append(self._bundle_gap(api_name, status))
                return []
            if frame is None:
                statuses[api_name] = "provider_error"
                gaps.append(self._bundle_gap(api_name, "provider_error"))
                return []
            try:
                empty = bool(getattr(frame, "empty", False)) or len(frame) == 0
            except (TypeError, ValueError):
                empty = False
            if empty:
                statuses[api_name] = "empty_no_rows"
                gaps.append(self._bundle_gap(api_name, "empty_no_rows"))
                return []
            if hasattr(frame, "iterrows"):
                rows = [row.to_dict() for _, row in frame.iterrows()]
            elif isinstance(frame, list):
                rows = [dict(row) for row in frame if isinstance(row, dict)]
            else:
                statuses[api_name] = "provider_error"
                gaps.append(self._bundle_gap(api_name, "provider_error"))
                return []
            exact_rows = [row for row in rows if row.get("ts_code") == expected_code]
            if not exact_rows:
                statuses[api_name] = "provider_error"
                gaps.append(f"Tushare {api_name} 返回记录未能按请求代码核验。")
                return []
            statuses[api_name] = "allowed_with_data"
            return exact_rows

        etf_rows = fetch(
            "etf_basic",
            "ts_code,csname,extname,cname,index_code,index_name,setup_date,list_date,list_status,exchange,mgr_name,custod_name,mgt_fee,etf_type",
            symbol,
            ts_code=symbol,
        )
        exact_etfs = [
            row for row in etf_rows
            if row.get("list_status") in {None, "L"}
            and isinstance(row.get("index_code"), str)
            and row["index_code"].strip()
        ]
        if len(exact_etfs) != 1:
            if etf_rows:
                gaps.append("ETF基础信息未形成唯一、有效的跟踪基准映射，未按名称猜测基准。")
            return bundle

        etf = exact_etfs[0]
        index_code = etf["index_code"].strip()
        index_mapping_valid = bool(re.fullmatch(r"\d{6}\.(?:SH|SZ)", index_code))
        setup_date = self._parse_trade_date(etf.get("setup_date"))
        listing_date = self._parse_trade_date(etf.get("list_date")) or setup_date
        fund_rows = fetch(
            "fund_basic",
            "ts_code,name,management,custodian,fund_type,found_date,m_fee,c_fee,benchmark,status,market",
            symbol,
            ts_code=symbol,
            market="E",
        )
        fund = fund_rows[0] if len(fund_rows) == 1 else {}
        fund_type = fund.get("fund_type") if isinstance(fund.get("fund_type"), str) else None
        benchmark = fund.get("benchmark") if isinstance(fund.get("benchmark"), str) else None
        category = _classify_etf_category(fund_type, benchmark)
        dividend_valuation_eligible = category == "dividend"
        bundle.update({
            "is_etf": True,
            "category": category,
            "fund_type": fund_type,
            "benchmark": benchmark,
        })
        if not fund_rows:
            gaps.append("fund_basic未返回该代码的类型和业绩比较基准，ETF分类无法核验。")
        elif category == "unclassified":
            gaps.append("fund_basic类型或完整业绩比较基准未匹配固定ETF模板，不按名称猜测分类。")
        index_name = etf.get("index_name") if isinstance(etf.get("index_name"), str) else None
        metrics["etf_type"] = {
            "value": etf.get("etf_type"),
            "unit": None,
            "source": "Tushare-compatible",
            "endpoint": "etf_basic",
            "field": "etf_type",
            "as_of": retrieved_at.date().isoformat(),
            "window": "ETF基础信息当前分类字段",
        }
        metrics["fund_type"] = {
            "value": fund_type,
            "unit": None,
            "source": "Tushare-compatible",
            "endpoint": "fund_basic",
            "field": "fund_type",
            "as_of": retrieved_at.date().isoformat(),
            "window": "基金基础信息当前投资类型",
        } if fund_type else None
        metrics["benchmark"] = {
            "value": benchmark,
            "unit": None,
            "source": "Tushare-compatible",
            "endpoint": "fund_basic",
            "field": "benchmark",
            "as_of": retrieved_at.date().isoformat(),
            "window": "基金基础信息当前业绩比较基准",
        } if benchmark else None
        metrics["underlying_index"] = {
            "value": index_code,
            "name": index_name,
            "unit": None,
            "source": "Tushare-compatible",
            "endpoint": "etf_basic",
            "field": "index_code",
            "as_of": retrieved_at.date().isoformat(),
            "window": "ETF基础信息当前映射",
        }
        if setup_date:
            metrics["fund_found_date"] = {
                "value": setup_date.isoformat(),
                "unit": "date",
                "source": "Tushare-compatible",
                "endpoint": "etf_basic",
                "field": "setup_date",
                "as_of": setup_date.isoformat(),
                "window": "基金设立日期",
            }
        sources.append({
            "source_record_id": f"etf_basic:{symbol}:0",
            "endpoint": "etf_basic",
            "title": "ETF基础信息和跟踪指数映射",
            "as_of": retrieved_at.date().isoformat(),
            "summary": (
                f"Tushare etf_basic exact code {symbol}; index_code={index_code}; "
                f"index_name={index_name or '未返回'}; setup_date={setup_date.isoformat() if setup_date else '未返回'}; "
                f"etf_type={etf.get('etf_type') or '未返回'}; category={category}; "
                f"custodian={etf.get('custod_name') or '未返回'}; "
                f"management_fee_raw={etf.get('mgt_fee') if etf.get('mgt_fee') is not None else '未返回'} "
                "(Tushare文档未标注费率单位)。"
            ),
            "gaps": [],
        })

        if calendar_rows is None:
            try:
                from backend.api.observations import get_position_market_monitor

                calendar_rows = get_position_market_monitor().trade_calendar_rows_between(
                    start_10y, as_of_date,
                )
            except Exception as exc:
                status = self._tushare_failure_status(exc)
                if status == "provider_error" and "calendar does not cover" in str(exc).lower():
                    status = "empty_no_rows"
                statuses["trade_cal"] = status
                gaps.append(self._bundle_gap("trade_cal", status))
                calendar_rows = None

        calendar_by_date: dict[date, bool] = {}
        calendar_error = False
        expected_calendar_dates = {
            start_10y + timedelta(days=offset)
            for offset in range((as_of_date - start_10y).days + 1)
        }
        if calendar_rows is not None:
            for row in calendar_rows:
                row_date = self._parse_trade_date(row.get("cal_date"))
                if row_date is not None and row_date not in expected_calendar_dates:
                    continue
                raw_open = str(row.get("is_open", "")).strip()
                exchange = row.get("exchange")
                if (
                    row_date is None
                    or exchange not in {None, "", "SSE"}
                    or raw_open not in {"0", "1", "0.0", "1.0", "False", "True", "false", "true"}
                ):
                    calendar_error = True
                    continue
                is_open = raw_open in {"1", "1.0", "True", "true"}
                if row_date in calendar_by_date:
                    calendar_error = True
                calendar_by_date[row_date] = is_open
        missing_calendar_dates = sorted(expected_calendar_dates - set(calendar_by_date))
        if calendar_rows is not None and (calendar_error or missing_calendar_dates):
            statuses["trade_cal"] = "empty_no_rows" if missing_calendar_dates else "provider_error"
            gaps.append(
                "SSE交易日历在近十年区间覆盖不完整或存在冲突，不能核验行情样本完整性。"
            )
            calendar_by_date = {}
        elif calendar_rows is not None:
            statuses["trade_cal"] = "allowed_with_data"

        expected_publish_sessions = sorted(
            day for day, is_open in calendar_by_date.items()
            if is_open and day <= publish_cutoff
        )
        expected_publish_date = expected_publish_sessions[-1] if expected_publish_sessions else None
        if expected_publish_date is not None:
            as_of_date = expected_publish_date
        bundle["as_of"] = as_of_date.isoformat()
        start_1y = as_of_date - timedelta(days=365)
        open_dates_10y = sorted(
            day for day, is_open in calendar_by_date.items()
            if is_open and day <= as_of_date
        )
        open_dates_1y = [day for day in open_dates_10y if start_1y <= day]
        baseline_dates = [day for day in open_dates_10y if day <= start_1y]
        baseline_date = baseline_dates[-1] if baseline_dates else None
        metrics["index_valuation_coverage"] = {
            "window_start": start_10y.isoformat(),
            "window_end": as_of_date.isoformat(),
            "expected_open_days": len(open_dates_10y),
            "pe_sample_points": 0,
            "pe_sample_start": None,
            "pe_sample_end": None,
            "pe_coverage_complete": False,
            "pb_sample_points": 0,
            "pb_sample_start": None,
            "pb_sample_end": None,
            "pb_coverage_complete": False,
        }
        metrics["price_coverage_1y"] = {
            "window_start": start_1y.isoformat(),
            "window_end": as_of_date.isoformat(),
            "expected_publish_date": expected_publish_date.isoformat() if expected_publish_date else None,
            "baseline_date": baseline_date.isoformat() if baseline_date else None,
            "expected_start_session": open_dates_1y[0].isoformat() if open_dates_1y else None,
            "expected_end_session": open_dates_1y[-1].isoformat() if open_dates_1y else None,
            "expected_sessions": len(open_dates_1y),
            "observed_sessions": 0,
            "missing_dates": [],
            "missing_high_dates": [],
            "missing_session_details": [],
            "leading_missing_dates": [],
            "trailing_missing_dates": [],
            "not_listed_dates": [],
            "coverage_complete": False,
        }
        if calendar_by_date:
            sources.append({
                "source_record_id": f"trade_cal:{symbol}:0",
                "endpoint": "trade_cal",
                "title": "上交所交易日历覆盖",
                "as_of": as_of_date.isoformat(),
                "summary": (
                    f"Tushare-compatible SSE trade_cal covers {start_10y.isoformat()} to {as_of_date.isoformat()}; "
                    f"{len(open_dates_10y)} open sessions in ten years; "
                    f"one-year window has {len(open_dates_1y)} expected sessions from "
                    f"{open_dates_1y[0].isoformat() if open_dates_1y else 'unavailable'} to "
                    f"{open_dates_1y[-1].isoformat() if open_dates_1y else 'unavailable'}; "
                    f"price-return baseline session is {baseline_date.isoformat() if baseline_date else 'unavailable'}."
                ),
                "gaps": [],
            })
        else:
            gaps.append("缺少完整SSE交易日历，近20交易日和一年区间均不可判定为完整。")

        fund_rows = fetch(
            "fund_basic",
            "ts_code,name,management,custodian,fund_type,found_date,m_fee,c_fee,benchmark,status,market",
            symbol,
            ts_code=symbol,
            market="E",
        )
        if fund_rows:
            fund = fund_rows[0]
            found_date = self._parse_trade_date(fund.get("found_date"))
            if found_date:
                metrics["fund_found_date"] = {
                    "value": found_date.isoformat(),
                    "unit": "date",
                    "source": "Tushare-compatible",
                    "endpoint": "fund_basic",
                    "field": "found_date",
                    "as_of": found_date.isoformat(),
                    "window": "基金成立日期",
                }
            for key, field_name in (("management_fee", "m_fee"), ("custody_fee", "c_fee")):
                value = self._finite_number(fund.get(field_name))
                if value is not None:
                    expected_fee = 0.5 if key == "management_fee" else 0.1
                    fee_unit_verified = (
                        symbol == "510880.SH"
                        and math.isclose(value, expected_fee, rel_tol=0.0, abs_tol=1e-12)
                    )
                    metrics[key] = {
                        "value": value,
                        "unit": "%/年" if fee_unit_verified else None,
                        "unit_status": "上交所2026-06-13更新招募说明书核验年费率" if fee_unit_verified else "费率单位或当前费率未由适用的官方基金资料核验",
                        "source": "Tushare-compatible",
                        "endpoint": "fund_basic",
                        "field": field_name,
                        "as_of": retrieved_at.date().isoformat(),
                        "window": "基金运作年费率；按官方资料核验原始接口值",
                        "verification_source_url": _SSE_510880_FEE_SOURCE if fee_unit_verified else None,
                    }
                    if not fee_unit_verified:
                        gaps.append("管理费和托管费字段已返回，但原始费率值或适用的官方费率单位未能核验。")
            sources.append({
                "source_record_id": f"fund_basic:{symbol}:0",
                "endpoint": "fund_basic",
                "title": "基金基础信息和费用字段",
                "as_of": retrieved_at.date().isoformat(),
                "summary": (
                    f"Tushare fund_basic exact code {symbol}; name={fund.get('name') or '未返回'}; "
                    f"found_date={found_date.isoformat() if found_date else '未返回'}; "
                    f"m_fee_raw={fund.get('m_fee') if fund.get('m_fee') is not None else '未返回'}; "
                    f"c_fee_raw={fund.get('c_fee') if fund.get('c_fee') is not None else '未返回'}; "
                    f"benchmark={fund.get('benchmark') or '未返回'}; "
                    + ("0.50%/年管理费、0.10%/年托管费由上交所最新官方招募说明书核验。" if symbol == "510880.SH" else "Tushare接口文档未定义其他基金的费率单位。")
                ),
                "gaps": [],
            })

        nav_rows = fetch(
            "fund_nav",
            "ts_code,ann_date,nav_date,unit_nav,accum_nav,accum_div,net_asset,total_netasset,adj_nav",
            symbol,
            ts_code=symbol,
            start_date=start_1y.strftime("%Y%m%d"),
            end_date=as_of_date.strftime("%Y%m%d"),
        )
        nav_by_date = []
        for row in nav_rows:
            row_date = self._parse_trade_date(row.get("nav_date"))
            if row_date is None or row_date > as_of_date:
                continue
            amount = self._finite_number(row.get("total_netasset"))
            field_name = "total_netasset"
            if amount is None:
                amount = self._finite_number(row.get("net_asset"))
                field_name = "net_asset"
            if amount is not None:
                nav_by_date.append((row_date, amount, field_name))
        if nav_by_date:
            nav_date, amount, field_name = max(nav_by_date, key=lambda item: item[0])
            scale_unit_verified = symbol == "510880.SH"
            metrics["asset_scale"] = {
                "value": amount,
                "unit": "元" if scale_unit_verified else None,
                "unit_status": "与上交所2025年中期报告同日净资产原值完全匹配，核验为人民币元" if scale_unit_verified else "基金净资产字段单位未核验",
                "source": "Tushare-compatible",
                "endpoint": "fund_nav",
                "field": field_name,
                "as_of": nav_date.isoformat(),
                "window": "最近可用净值日",
                "verification_source_url": _SSE_510880_SCALE_SOURCE if scale_unit_verified else None,
            }
            if scale_unit_verified:
                sources.append({
                    "source_record_id": f"fund_nav:{symbol}:0",
                    "endpoint": "fund_nav",
                    "title": "基金最近可用净资产规模",
                    "as_of": nav_date.isoformat(),
                    "summary": f"Tushare fund_nav.{field_name}={amount} 元，nav_date={nav_date.isoformat()}；字段单位由2025-06-30同日官方报告核验。",
                    "gaps": [],
                })
            else:
                gaps.append("净资产字段返回值的单位未核验，资产规模不可安全展示或换算。")
        else:
            gaps.append("fund_nav 的 net_asset 与 total_netasset 在查询期均无可用值，资产规模不可获取。")

        share_rows = fetch(
            "fund_share",
            "ts_code,trade_date,fd_share",
            symbol,
            ts_code=symbol,
            start_date=start_1y.strftime("%Y%m%d"),
            end_date=as_of_date.strftime("%Y%m%d"),
        )
        valid_shares = []
        for row in share_rows:
            row_date = self._parse_trade_date(row.get("trade_date"))
            shares = self._finite_number(row.get("fd_share"))
            if row_date is not None and row_date <= as_of_date and shares is not None and shares >= 0:
                valid_shares.append((row_date, shares))
        if valid_shares:
            shares_date, shares = max(valid_shares, key=lambda item: item[0])
            metrics["fund_size_shares"] = {
                "value": shares,
                "unit": "万份",
                "source": "Tushare-compatible",
                "endpoint": "fund_share",
                "field": "fd_share",
                "as_of": shares_date.isoformat(),
                "window": "最近可用份额日期",
                "verification_source_url": _TUSHARE_FUND_SHARE_DOCS,
            }
            sources.append({
                "source_record_id": f"fund_share:{symbol}:0",
                "endpoint": "fund_share",
                "title": "ETF最近可用基金份额",
                "as_of": shares_date.isoformat(),
                "summary": f"Tushare fund_share.fd_share={shares} 万份, trade_date={shares_date.isoformat()}.",
                "gaps": [],
            })
        else:
            gaps.append("fund_share 查询期内没有可核验的基金份额记录；单位为万份的资产份额不可获取。")

        daily_rows = fetch(
            "fund_daily",
            "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
            symbol,
            ts_code=symbol,
            start_date=start_10y.strftime("%Y%m%d"),
            end_date=as_of_date.strftime("%Y%m%d"),
        )
        by_date: dict[date, dict] = {}
        conflicted_dates: set[date] = set()
        for row in daily_rows:
            row_date = self._parse_trade_date(row.get("trade_date"))
            if (
                row_date is None or row_date < start_10y
                or row_date > as_of_date or row_date not in calendar_by_date
                or not calendar_by_date[row_date]
                or (listing_date is not None and row_date < listing_date)
            ):
                continue
            record = {
                "close": self._finite_number(row.get("close")),
                "high": self._finite_number(row.get("high")),
                "vol": self._finite_number(row.get("vol")),
                "amount": self._finite_number(row.get("amount")),
            }
            record = {
                key: value if value is not None and (value >= 0 if key in {"amount", "vol"} else value > 0) else None
                for key, value in record.items()
            }
            if row_date in conflicted_dates:
                continue
            previous = by_date.get(row_date)
            if previous is None:
                by_date[row_date] = record
                continue
            conflict_fields = [
                field for field, value in record.items()
                if value is not None and previous.get(field) is not None
                and not math.isclose(value, previous[field], rel_tol=1e-12, abs_tol=1e-12)
            ]
            if conflict_fields:
                gaps.append(
                    f"fund_daily 在 {row_date.isoformat()} 返回冲突行情字段 {','.join(conflict_fields)}，该日已排除。"
                )
                by_date.pop(row_date, None)
                conflicted_dates.add(row_date)
                continue
            for field, value in record.items():
                if previous.get(field) is None and value is not None:
                    previous[field] = value

        expected_closes = open_dates_1y
        not_listed_dates = [
            day for day in expected_closes if listing_date is not None and day < listing_date
        ]
        active_expected_closes = [day for day in expected_closes if day not in set(not_listed_dates)]
        observed_closes = {
            day for day in active_expected_closes
            if day in by_date
            and by_date[day].get("close") is not None
            and by_date[day].get("vol") != 0
        }
        missing_closes = [day for day in active_expected_closes if day not in observed_closes]
        first_observed_close = min(observed_closes) if observed_closes else None
        last_observed_close = max(observed_closes) if observed_closes else None
        missing_session_details = []
        for day in missing_closes:
            record = by_date.get(day)
            if record is not None and record.get("vol") == 0:
                gap_category = "zero_volume_no_trade_or_suspension"
            elif record is not None:
                gap_category = "row_without_valid_close"
            elif first_observed_close is None or day < first_observed_close:
                gap_category = "leading_history_missing"
            elif last_observed_close is None or day > last_observed_close:
                gap_category = "trailing_history_missing"
            else:
                gap_category = "middle_session_missing"
            missing_session_details.append({"date": day.isoformat(), "category": gap_category})
        leading_missing_dates = [
            item["date"] for item in missing_session_details
            if item["category"] == "leading_history_missing"
        ]
        trailing_missing_dates = [
            item["date"] for item in missing_session_details
            if item["category"] == "trailing_history_missing"
        ]
        baseline_close = (
            by_date.get(baseline_date, {}).get("close") if baseline_date is not None else None
        )
        baseline_observed = (
            baseline_close is not None
            and (listing_date is None or baseline_date is not None and baseline_date >= listing_date)
            and by_date.get(baseline_date, {}).get("vol") != 0
        )
        close_coverage_complete = (
            bool(expected_closes) and not not_listed_dates and not missing_closes
        )
        price_coverage_complete = close_coverage_complete and baseline_observed
        close_coverage_ratio = (
            len(observed_closes) / len(active_expected_closes)
            if active_expected_closes else None
        )
        latest_date = max(observed_closes) if observed_closes else None
        latest_close = by_date.get(latest_date, {}).get("close") if latest_date else None
        metrics["price_coverage_1y"].update({
            "observed_sessions": len(observed_closes),
            "expected_listed_sessions": len(active_expected_closes),
            "coverage_ratio": close_coverage_ratio,
            "missing_dates": [day.isoformat() for day in missing_closes],
            "missing_session_details": missing_session_details,
            "missing_high_dates": [],
            "leading_missing_dates": leading_missing_dates,
            "trailing_missing_dates": trailing_missing_dates,
            "not_listed_dates": [day.isoformat() for day in not_listed_dates],
            "listing_date": listing_date.isoformat() if listing_date else None,
            "first_observed_date": first_observed_close.isoformat() if first_observed_close else None,
            "last_observed_date": last_observed_close.isoformat() if last_observed_close else None,
            "baseline_observed": baseline_observed,
            "coverage_complete": price_coverage_complete,
        })
        if missing_closes:
            gaps.append(
                "fund_daily 一年区间有效上市日收盘价缺少 "
                f"{len(missing_closes)}/{len(active_expected_closes)} 个预期SSE交易日；"
                "日期与原因："
                + "; ".join(f"{item['date']}({item['category']})" for item in missing_session_details)
                + "。观察到的区间指标仍按有效行情计算，未将样本称为完整一年。"
            )
        if not_listed_dates:
            gaps.append(
                f"一年窗口早于ETF上市日 {listing_date.isoformat()} 的未上市交易日共 {len(not_listed_dates)} 个；"
                "该基金可得历史不足完整一年。"
            )
        if baseline_date is not None and not baseline_observed:
            gaps.append(
                f"fund_daily 缺少截止日之前基准交易日 {baseline_date.isoformat()} 的收盘价，一年涨跌幅未计算。"
            )

        if latest_date is not None and latest_close is not None:
            is_stale = expected_publish_date is not None and latest_date < expected_publish_date
            metrics["latest_price"] = {
                "value": latest_close,
                "unit": "元/份",
                "source": "Tushare-compatible",
                "endpoint": "fund_daily",
                "field": "close",
                "as_of": latest_date.isoformat(),
                "expected_as_of": expected_publish_date.isoformat() if expected_publish_date else None,
                "stale": is_stale,
                "window": "最近已获取的有效SSE报告收盘价；未复权且不含分红再投总回报",
            }
            if is_stale:
                gaps.append(
                    f"最近有效收盘价日期 {latest_date.isoformat()} 早于预期公布日 "
                    f"{expected_publish_date.isoformat()}，行情已过期。"
                )
        else:
            gaps.append("fund_daily 缺少最近预期SSE交易日的有效收盘价，当前价格不可核验。")

        price_change = None
        endpoints_complete = latest_close is not None and baseline_close is not None
        metrics["price_coverage_1y"]["price_change_endpoints_complete"] = endpoints_complete
        if endpoints_complete:
            price_change = (latest_close / baseline_close - 1.0) * 100.0
            metrics["price_change_1y"] = {
                "value": price_change,
                "unit": "%",
                "source": "Tushare-compatible",
                "endpoint": "fund_daily",
                "field": "close",
                "as_of": latest_date.isoformat(),
                "window": (
                    f"报告收盘价：基准交易日 {baseline_date.isoformat()} 至 {latest_date.isoformat()}；"
                    "未复权计算，不含分红再投及分红总回报"
                ),
                "baseline_date": baseline_date.isoformat(),
                "baseline_value": baseline_close,
                "latest_value": latest_close,
            }

        high_reference_dates = [day for day in active_expected_closes if latest_date is not None and day <= latest_date]
        observed_highs = {
            day for day in high_reference_dates
            if day in by_date and by_date[day].get("high") is not None and by_date[day].get("vol") != 0
        }
        missing_highs = [day for day in high_reference_dates if day not in observed_highs]
        metrics["price_coverage_1y"]["missing_high_dates"] = [day.isoformat() for day in missing_highs]
        high_field = "high" if observed_highs else "close"
        high_sample_dates = observed_highs or {
            day for day in high_reference_dates if day in observed_closes
        }
        if latest_close is not None and len(high_sample_dates) >= 2:
            period_high = max(by_date[day][high_field] for day in high_sample_dates)
            sample_start = min(high_sample_dates)
            sample_end = max(high_sample_dates)
            has_full_year_scope = (
                sample_start == active_expected_closes[0]
                and sample_end == latest_date
                and not not_listed_dates
                and close_coverage_ratio is not None
                and close_coverage_ratio >= _DIVIDEND_YIELD_HISTORY_COVERAGE_MIN
            )
            label = "距近一年已观察到的最高价" if has_full_year_scope else "距实际观察区间最高价"
            if high_field == "close":
                label = label.replace("最高价", "最高收盘价")
            metrics["distance_from_1y_high_pct"] = {
                "value": (latest_close / period_high - 1.0) * 100.0,
                "unit": "%",
                "label": label,
                "source": "Tushare-compatible",
                "endpoint": "fund_daily",
                "field": high_field,
                "as_of": latest_date.isoformat(),
                "window": (
                    f"观察日期 {sample_start.isoformat()}至{sample_end.isoformat()}；"
                    f"有效样本 {len(high_sample_dates)}/{len(active_expected_closes)} 个已上市SSE交易日；"
                    + ("使用日内最高价" if high_field == "high" else "日内最高价无值，使用收盘价")
                ),
                "period_high": period_high,
                "sample_sessions": len(high_sample_dates),
                "expected_sessions": len(active_expected_closes),
            }
        else:
            gaps.append("一年窗口内少于两个有效价格观察点，距观察区间高点指标未计算。")
        if missing_highs:
            gaps.append(
                "fund_daily 日内最高价缺少日期："
                + ", ".join(day.isoformat() for day in missing_highs)
                + "；距高点按仍可核验的最高价样本计算。"
            )

        latest_twenty_sessions = expected_closes[-20:]
        amount_complete = len(latest_twenty_sessions) == 20 and all(
            day in by_date and by_date[day].get("amount") is not None
            for day in latest_twenty_sessions
        )
        if amount_complete:
            amount_rows = [(day, by_date[day]["amount"]) for day in latest_twenty_sessions]
            if all(amount >= 0 for _, amount in amount_rows):
                mean_amount_yuan = sum(amount for _, amount in amount_rows) / 20.0 * 1000.0
                metrics["average_amount_20d"] = {
                    "value": mean_amount_yuan,
                    "unit": "元",
                    "source": "Tushare-compatible",
                    "endpoint": "fund_daily",
                    "field": "amount",
                    "as_of": amount_rows[-1][0].isoformat(),
                    "window": f"SSE日历最近20个交易日：{amount_rows[0][0].isoformat()}至{amount_rows[-1][0].isoformat()}；接口千元换算为元",
                }
            else:
                gaps.append("SSE日历最近20个交易日的成交额含无效负值，20日平均成交额不可计算。")
        else:
            missing_amounts = [
                day.isoformat() for day in latest_twenty_sessions
                if day not in by_date or by_date[day].get("amount") is None
            ]
            gaps.append(
                "fund_daily 未覆盖SSE日历最近20个交易日的全部有效成交额；缺少日期："
                + (", ".join(missing_amounts) if missing_amounts else "有效交易日不足20天")
                + "。"
            )

        if latest_close is not None:
            distance_metric = metrics["distance_from_1y_high_pct"]
            price_change_text = f"{price_change:.6f}%" if price_change is not None else "unavailable"
            distance_text = (
                f"{distance_metric['value']:.6f}% using {distance_metric['field']}"
                if distance_metric is not None else "unavailable"
            )
            baseline_text = baseline_date.isoformat() if baseline_date is not None else "unavailable"
            sources.append({
                "source_record_id": f"fund_daily:{symbol}:0",
                "endpoint": "fund_daily",
                "title": "ETF报告收盘价、日内高点与成交额",
                "as_of": latest_date.isoformat(),
                "summary": (
                    f"Tushare fund_daily reported close={latest_close} 元/份 on {latest_date.isoformat()}; "
                    f"reported-close change={price_change_text} from baseline session {baseline_text} "
                    f"to {latest_date.isoformat()} when both endpoints exist, otherwise unavailable; "
                    f"distance from one-year high={distance_text}; "
                    f"mean amount of calendar-defined latest 20 open sessions="
                    f"{metrics['average_amount_20d']['value'] if metrics['average_amount_20d'] else 'unavailable'} 元 "
                    "(Tushare fund_daily.amount in thousand CNY converted to CNY). "
                    "Price change uses reported, unadjusted closes and excludes distributions and dividend reinvestment. "
                    f"One-year listed-session close coverage={len(observed_closes)}/{len(active_expected_closes)}; "
                    f"observed high sample={len(observed_highs)}/{len(active_expected_closes)}."
                ),
                "gaps": [
                    gap for gap in gaps
                    if "fund_daily" in gap or "成交额" in gap or "区间日内最高价" in gap
                ],
            })
        else:
            gaps.append("fund_daily 缺少最近预期SSE交易日的有效收盘价，行情指标不可核验。")

        div_rows = fetch(
            "fund_div",
            "ts_code,ann_date,imp_anndate,base_date,div_proc,record_date,ex_date,pay_date,earpay_date,net_ex_date,div_cash,base_unit,ear_distr,ear_amount,account_date,base_year",
            symbol,
            ts_code=symbol,
        )
        valid_dividends: dict[tuple, dict] = {}
        missing_implementation_dates = 0
        for row in div_rows:
            ex_date = self._parse_trade_date(row.get("ex_date"))
            pay_date = self._parse_trade_date(row.get("pay_date"))
            implementation_date = self._parse_trade_date(row.get("imp_anndate"))
            cash = self._finite_number(row.get("div_cash"))
            if str(row.get("div_proc") or "").strip() != "实施":
                continue
            if ex_date is None or pay_date is None or cash is None or cash <= 0:
                continue
            if implementation_date is None:
                missing_implementation_dates += 1
                continue
            key = (ex_date.isoformat(), pay_date.isoformat(), implementation_date.isoformat(), cash)
            valid_dividends.setdefault(key, {
                "ex_date": ex_date,
                "pay_date": pay_date,
                "implementation_date": implementation_date,
                "cash": cash,
            })
        all_dividend_events = sorted(
            valid_dividends.values(), key=lambda item: (item["pay_date"], item["ex_date"]),
        )
        if missing_implementation_dates:
            gaps.append(
                f"fund_div 有 {missing_implementation_dates} 条已实施现金分红缺少实施公告日期；"
                "这些事件已从点时收益率计算中排除。"
            )

        distribution_reference_date = latest_date or as_of_date
        cash_window_start = distribution_reference_date - timedelta(days=365)
        dividend_events = [
            event for event in all_dividend_events
            if cash_window_start < event["pay_date"] <= distribution_reference_date
            and event["ex_date"] <= distribution_reference_date
            and event["implementation_date"] <= distribution_reference_date
        ]
        dividend_events = sorted(dividend_events, key=lambda item: (item["pay_date"], item["ex_date"]))
        trailing_cash = sum(event["cash"] for event in dividend_events)
        if dividend_events:
            dividend_as_of = max(event["pay_date"] for event in dividend_events).isoformat()
            event_facts = [
                {
                    "implementation_date": event["implementation_date"].isoformat(),
                    "ex_date": event["ex_date"].isoformat(),
                    "pay_date": event["pay_date"].isoformat(),
                    "cash_per_share": event["cash"],
                }
                for event in dividend_events
            ]
            metrics["trailing_cash_dividend_per_share"] = {
                "value": trailing_cash,
                "unit": "元/份",
                "source": "Tushare-compatible",
                "endpoint": "fund_div",
                "field": "div_cash",
                "as_of": dividend_as_of,
                "window": (
                    f"{cash_window_start.isoformat()}之后至{distribution_reference_date.isoformat()}；"
                    "按派息日计入已实施事件，且实施公告日、除息日均不晚于分母收盘日"
                ),
                "events": event_facts,
            }
        else:
            event_facts = []
            gaps.append("最近滚动365天没有按实施公告日、除息日和派息日核验的正额现金分红记录。")

        if trailing_cash > 0 and dividend_events:
            condition_value = f"{trailing_cash:.12g}"
            condition = (
                f"如果未来滚动一年按同口径实际支付的每份现金分红低于本次核验的{condition_value}元/份，"
                "则关于现金分红维持当前水平的研究假设不成立，需重新评估。"
                "这是一项待检验假设，不代表分红稳定或保证。"
            )
            bundle["investment_assumption"] = {
                "kind": "trailing_cash_dividend_baseline",
                "baseline_value": trailing_cash,
                "unit": "元/份",
                "endpoint": "fund_div",
                "source": "Tushare-compatible",
                "as_of": distribution_reference_date.isoformat(),
                "window": "按实施公告日、除息日和派息日点时核验的过去滚动365天已实施派息",
                "condition": condition,
                "events": event_facts,
                "limitation": "仅为待检验研究假设，不代表分红稳定或保证。",
            }

        if dividend_valuation_eligible and metrics["latest_price"] and dividend_events:
            latest_price = metrics["latest_price"]
            yield_pct = trailing_cash / latest_price["value"] * 100.0
            metrics["trailing_dividend_yield"] = {
                "value": yield_pct,
                "unit": "%",
                "source": "Tushare-compatible",
                "endpoint": "fund_div+fund_daily",
                "field": "rolling_365d_div_cash/reported_close",
                "as_of": latest_price["as_of"],
                "window": (
                    f"滚动365天已派付现金分红 {trailing_cash} 元/份 ÷ "
                    f"{latest_price['as_of']} 未复权报告收盘价 {latest_price['value']} 元/份；"
                    "只作510880自身历史比较，不代表未来分红或总回报"
                ),
            }
        elif dividend_valuation_eligible:
            gaps.append("510880自身现金分红收益率缺少同日有效收盘价或已实施派息，暂不计算。")

        history_expected_start = max(start_10y, listing_date) if listing_date else start_10y
        earliest_distribution = min(
            (event["pay_date"] for event in all_dividend_events), default=None,
        )
        if earliest_distribution is None:
            history_effective_start = None
        elif earliest_distribution > history_expected_start - timedelta(days=365):
            history_effective_start = earliest_distribution + timedelta(days=365)
        else:
            history_effective_start = history_expected_start
        yield_expected_dates = [
            day for day in open_dates_10y
            if history_effective_start is not None
            and history_effective_start <= day <= distribution_reference_date
        ]
        yield_by_date: dict[date, float] = {}
        if dividend_valuation_eligible and yield_expected_dates:
            for day in yield_expected_dates:
                close = by_date.get(day, {}).get("close")
                volume = by_date.get(day, {}).get("vol")
                if close is None or volume == 0:
                    continue
                trailing_start = day - timedelta(days=365)
                day_cash = sum(
                    event["cash"] for event in all_dividend_events
                    if trailing_start < event["pay_date"] <= day
                    and event["ex_date"] <= day
                    and event["implementation_date"] <= day
                )
                yield_by_date[day] = day_cash / close * 100.0

        yield_sample_dates = sorted(yield_by_date)
        yield_sample_count = len(yield_sample_dates)
        yield_coverage_ratio = (
            yield_sample_count / len(yield_expected_dates) if yield_expected_dates else 0.0
        )
        yield_coverage_complete = bool(yield_expected_dates) and yield_sample_count == len(yield_expected_dates)
        yield_coverage_sufficient = (
            dividend_valuation_eligible
            and bool(yield_expected_dates)
            and yield_coverage_ratio >= _DIVIDEND_YIELD_HISTORY_COVERAGE_MIN
            and missing_implementation_dates == 0
        )
        if dividend_valuation_eligible:
            metrics["trailing_dividend_yield_coverage_10y"] = {
                "window_start": history_effective_start.isoformat() if history_effective_start else None,
                "window_end": distribution_reference_date.isoformat(),
                "sample_start": yield_sample_dates[0].isoformat() if yield_sample_dates else None,
                "sample_end": yield_sample_dates[-1].isoformat() if yield_sample_dates else None,
                "expected_sessions": len(yield_expected_dates),
                "sample_points": yield_sample_count,
                "coverage_ratio": yield_coverage_ratio,
                "coverage_complete": yield_coverage_complete,
                "coverage_sufficient": yield_coverage_sufficient,
                "coverage_threshold": _DIVIDEND_YIELD_HISTORY_COVERAGE_MIN,
                "dividend_history_first_pay_date": earliest_distribution.isoformat() if earliest_distribution else None,
                "dividend_history_headroom_complete": bool(
                    earliest_distribution
                    and earliest_distribution <= history_expected_start - timedelta(days=365)
                ),
                "basis": "同一SSE交易日的fund_daily未复权收盘价；只计支付日在前365天内且实施公告日和除息日不晚于当日的现金分红",
            }
            if yield_coverage_sufficient and metrics["trailing_dividend_yield"]:
                history_values = [
                    value for day, value in yield_by_date.items()
                    if latest_date is not None and day < latest_date
                ]
                if history_values:
                    current_yield = metrics["trailing_dividend_yield"]["value"]
                    percentile = sum(value <= current_yield for value in history_values) / len(history_values) * 100.0
                    metrics["trailing_dividend_yield_percentile_10y"] = {
                        "value": percentile,
                        "unit": "%分位",
                        "source": "Tushare-compatible",
                        "endpoint": "fund_div+fund_daily",
                        "field": "rolling_365d_div_cash/reported_close",
                        "as_of": latest_date.isoformat(),
                        "window": (
                            f"510880可得历史区间 {yield_sample_dates[0].isoformat()}至"
                            f"{yield_sample_dates[-1].isoformat()}；当前值对比此前 {len(history_values)} 个交易日样本；"
                            f"覆盖 {yield_sample_count}/{len(yield_expected_dates)}"
                        ),
                        "sample_points": len(history_values),
                    }
                else:
                    gaps.append("510880自身现金分红收益率缺少可比较的历史交易日样本，暂不形成历史分位。")
            elif not yield_coverage_sufficient:
                gaps.append(
                    "510880自身现金分红收益率历史覆盖不足："
                    f"可得区间 {history_effective_start.isoformat() if history_effective_start else '不可核验'}至"
                    f"{distribution_reference_date.isoformat()}，样本 {yield_sample_count}/{len(yield_expected_dates)}；"
                    "未覆盖窗口不按零收益填补，暂不形成历史分位。"
                )

        if dividend_events:
            yield_metric = metrics["trailing_dividend_yield"]
            yield_text = (
                f"{yield_metric['value']:.6f}% using reported close on {yield_metric['as_of']}"
                if yield_metric else "not applicable to this ETF"
            )
            sources.append({
                "source_record_id": f"fund_div:{symbol}:0",
                "endpoint": "fund_div",
                "title": "ETF已实施现金分红和点时收益率",
                "as_of": dividend_as_of,
                "summary": (
                    f"Tushare fund_div rolling 365-day paid cash={trailing_cash} 元/份 as of "
                    f"{distribution_reference_date.isoformat()}; events={json.dumps(event_facts, ensure_ascii=False)}. "
                    f"ETF cash yield={yield_text}; historical event inclusion requires implementation announcement, "
                    "ex-date, and pay-date to be known by each observation date."
                ),
                "gaps": [],
            })

        index_valuation_applicable = category in {"dividend", "broad", "industry"} and index_mapping_valid
        if index_valuation_applicable:
            index_rows = fetch(
                "index_dailybasic",
                "ts_code,trade_date,pe,pe_ttm,pb",
                index_code,
                ts_code=index_code,
                start_date=start_10y.strftime("%Y%m%d"),
                end_date=as_of_date.strftime("%Y%m%d"),
            )
        else:
            statuses["index_dailybasic"] = "not_applicable"
            index_rows = []
        if statuses.get("index_dailybasic") == "empty_no_rows":
            empty_gap = self._bundle_gap("index_dailybasic", "empty_no_rows")
            gaps[:] = [gap for gap in gaps if gap != empty_gap]
        expected_index_dates = set(open_dates_10y)
        daily_index_values: dict[str, dict[date, float]] = {"pe": {}, "pb": {}}
        conflicting_index_dates: dict[str, set[date]] = {"pe": set(), "pb": set()}
        for row in index_rows:
            row_date = self._parse_trade_date(row.get("trade_date"))
            if row_date not in expected_index_dates:
                continue
            for field_name in ("pe", "pb"):
                value = self._finite_number(row.get(field_name))
                if value is None or value <= 0 or row_date in conflicting_index_dates[field_name]:
                    continue
                previous = daily_index_values[field_name].get(row_date)
                if previous is not None and not math.isclose(value, previous, rel_tol=1e-12, abs_tol=1e-12):
                    daily_index_values[field_name].pop(row_date, None)
                    conflicting_index_dates[field_name].add(row_date)
                    continue
                daily_index_values[field_name][row_date] = value

        index_coverage = metrics["index_valuation_coverage"]
        index_source_lines = []
        for field_name, metric_name, percentile_name in (
            ("pe", "underlying_pe", "underlying_pe_percentile_10y"),
            ("pb", "underlying_pb", "underlying_pb_percentile_10y"),
        ):
            values = daily_index_values[field_name]
            dated_series = sorted(values.items(), key=lambda item: item[0])
            valid_dates = set(values)
            sample_start = dated_series[0][0] if dated_series else None
            sample_end = dated_series[-1][0] if dated_series else None
            complete = bool(expected_index_dates) and valid_dates == expected_index_dates
            index_coverage.update({
                f"{field_name}_sample_points": len(dated_series),
                f"{field_name}_sample_start": sample_start.isoformat() if sample_start else None,
                f"{field_name}_sample_end": sample_end.isoformat() if sample_end else None,
                f"{field_name}_coverage_complete": complete,
            })
            expected_latest = open_dates_10y[-1] if open_dates_10y else None
            if expected_latest is not None and expected_latest in values:
                latest_value = values[expected_latest]
                metrics[metric_name] = {
                    "value": latest_value,
                    "unit": "倍",
                    "source": "Tushare-compatible",
                    "endpoint": "index_dailybasic",
                    "field": field_name,
                    "as_of": expected_latest.isoformat(),
                    "window": "最近预期SSE交易日",
                }
                if complete:
                    metrics[percentile_name] = {
                        "value": sum(value <= latest_value for value in values.values()) / len(values) * 100.0,
                        "unit": "%",
                        "source": "Tushare-compatible",
                        "endpoint": "index_dailybasic",
                        "field": field_name,
                        "as_of": expected_latest.isoformat(),
                        "window": (
                            f"完整SSE交易日 {start_10y.isoformat()}至{as_of_date.isoformat()}；"
                            f"{len(values)}个预期交易日样本"
                        ),
                    }
            elif dated_series:
                gaps.append(
                    f"跟踪指数 {field_name.upper()} 缺少最近预期SSE交易日值，当前估值不可核验。"
                )
            if not complete:
                index_source_lines.append(
                    f"{field_name.upper()} sample={len(dated_series)}/{len(expected_index_dates)} "
                    f"expected sessions, from {sample_start.isoformat() if sample_start else 'unavailable'} "
                    f"to {sample_end.isoformat() if sample_end else 'unavailable'}; ten-year percentile unavailable."
                )
            else:
                index_source_lines.append(
                    f"{field_name.upper()} complete sample={len(dated_series)} sessions, "
                    f"from {sample_start.isoformat()} to {sample_end.isoformat()}."
                )
        if index_rows:
            sources.append({
                "source_record_id": f"index_dailybasic:{index_code}:0",
                "endpoint": "index_dailybasic",
                "title": "跟踪指数估值及十年覆盖",
                "as_of": as_of_date.isoformat(),
                "summary": (
                    f"Tushare index_dailybasic exact code {index_code}; "
                    + " ".join(index_source_lines)
                ),
                "gaps": [line for line in gaps if "指数" in line or "估值" in line],
            })
        elif statuses.get("index_dailybasic") == "empty_no_rows":
            index_valuation_gap = (
                f"跟踪指数 {index_code} 的PE/PB当前值及十年估值分位数均未能核验："
                "index_dailybasic 返回空结果。"
            )
            gaps.append(index_valuation_gap)
            sources.append({
                "source_record_id": f"index_dailybasic:{index_code}:0",
                "endpoint": "index_dailybasic",
                "title": "跟踪指数估值接口未返回数据",
                "as_of": as_of_date.isoformat(),
                "summary": (
                    f"Tushare index_dailybasic exact code {index_code}; endpoint returned no rows; "
                    "current PE/PB and ten-year valuation coverage are unavailable."
                ),
                "gaps": [index_valuation_gap],
            })
        elif statuses.get("index_dailybasic"):
            sources.append({
                "source_record_id": f"index_dailybasic:{index_code}:0",
                "endpoint": "index_dailybasic",
                "title": "跟踪指数估值接口状态",
                "as_of": as_of_date.isoformat(),
                "summary": (
                    f"Tushare index_dailybasic exact code {index_code}; "
                    f"endpoint status={statuses['index_dailybasic']}; valuation coverage unavailable."
                ),
                "gaps": [
                    gap for gap in gaps
                    if "index_dailybasic" in gap or ("指数" in gap and "估值" in gap)
                ],
            })
        if index_valuation_applicable:
            gaps.append("Tushare index_dailybasic没有股息率字段；底层指数股息率不可由本接口核验。")

        if dividend_valuation_eligible:
            yield_percentile = metrics["trailing_dividend_yield_percentile_10y"]
            index_valuation_missing = (
                metrics["underlying_pe"] is None and metrics["underlying_pb"] is None
            )
            if yield_percentile and index_valuation_missing:
                coverage = metrics["trailing_dividend_yield_coverage_10y"] or {}
                valuation = _trailing_yield_valuation_label(yield_percentile["value"])
                metrics["trailing_dividend_yield_valuation"] = {
                    "value": valuation,
                    "percentile": yield_percentile["value"],
                    "unit": None,
                    "source": "Tushare-compatible",
                    "endpoint": "fund_div+fund_daily",
                    "field": "rolling_365d_div_cash/reported_close",
                    "as_of": latest_date.isoformat() if latest_date else as_of_date.isoformat(),
                    "window": (
                        f"510880自身可得历史 {coverage.get('window_start')}至{coverage.get('window_end')}；"
                        f"此前{yield_percentile['sample_points']}个交易日样本；"
                        "收益率分位≥80为相对偏便宜，≤20为相对偏贵，其余中性"
                    ),
                    "sample_points": yield_percentile["sample_points"],
                    "limitation": "只与该ETF自身可得历史比较，不等同于指数估值，不代表未来分红或回报。",
                }
                gaps[:] = [
                    gap for gap in gaps
                    if not _etf_gap_categories(gap).intersection({"index_valuation", "index_dividend_yield"})
                ]
                gaps.append(
                    "跟踪指数PE/PB与指数股息率无可用覆盖；已以510880 ETF自身现金分红收益率历史分位（滚动365天）作"
                    f"替代参考（{coverage.get('window_start')}至{coverage.get('window_end')}，"
                    f"历史样本 {yield_percentile['sample_points']} 个），仅与本ETF自身历史比较，"
                    "不等同于指数估值，也不代表未来分红或回报。"
                )

        if metrics["latest_price"] and metrics["trailing_cash_dividend_per_share"]:
            bundle["sources"].append({
                "source_record_id": f"fund_price:{symbol}:0",
                "endpoint": "fund_daily",
                "title": "用于分红收益率的ETF收盘价",
                "as_of": metrics["latest_price"]["as_of"],
                "summary": (
                    f"Tushare fund_daily.close={metrics['latest_price']['value']} 元/份 on "
                    f"{metrics['latest_price']['as_of']}; reported close used as yield denominator."
                ),
                "gaps": [],
            })
        pe_percentile = metrics["underlying_pe_percentile_10y"]
        pb_percentile = metrics["underlying_pb_percentile_10y"]
        dividend_percentile = metrics["trailing_dividend_yield_percentile_10y"]
        bundle["valuation_conclusion"] = _etf_valuation_conclusion(
            category,
            pe_percentile=pe_percentile.get("value") if isinstance(pe_percentile, dict) else None,
            pb_percentile=pb_percentile.get("value") if isinstance(pb_percentile, dict) else None,
            dividend_yield_percentile=(
                dividend_percentile.get("value")
                if category == "dividend" and isinstance(dividend_percentile, dict)
                else None
            ),
        )
        bundle["gaps"] = list(dict.fromkeys(gaps))
        return bundle

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
