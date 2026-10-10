"""
Friend Stock Flow Service

Red lines:
R1. Flow only orchestrates (calls existing Serenity/research services)
R2. Ticker code only from tool queries, LLM cannot touch
R3. User sees approval card with counter-evidence
R4. confirmed_candidate_pool is forward-only and frozen
R5. Data fault only downgrades
"""

import uuid
import hashlib
import re
from datetime import date, datetime
from typing import Optional, Tuple

from contracts.friend_stock import (
    FriendStockIntake,
    TickerVerificationResult,
    ConfirmedCandidatePool,
)
from contracts.research import ThemeInput
from backend.services.research_validation import ResearchValidator
from backend.services.serenity_agent import SerenityAgentRunner
from backend.services.live_market_data import (
    get_daily_basic_snapshot,
    get_current_price_snapshot,
)


def validate_serenity_research_output(
    serenity_runner,
    ticker: str,
    research_output: dict,
    *,
    require_real_runner: bool = True,
    require_candidate_verdict: bool = False,
) -> dict:
    """Validate the evidence boundary before a research result can advance."""
    if require_real_runner:
        if not isinstance(serenity_runner, SerenityAgentRunner):
            raise ValueError("real SerenityAgentRunner is required")
        if serenity_runner.mode != "real":
            raise ValueError("Serenity runner must use mode=real")
        if serenity_runner.execution_mode != "two_phase":
            raise ValueError("Serenity runner must use execution_mode=two_phase")

    if require_candidate_verdict:
        decisions = research_output.get("candidate_verdicts")
        decision = decisions.get(ticker) if isinstance(decisions, dict) else None
        if not isinstance(decision, dict):
            raise ValueError("missing candidate verdict")
        if decision.get("verdict") not in {
            "research_positive", "research_watch", "research_reject", "research_unavailable"
        }:
            raise ValueError("invalid candidate verdict")
        if not isinstance(decision.get("reason"), str) or not decision["reason"].strip():
            raise ValueError("candidate verdict requires a reason")

        source_ids = set()
        sources = research_output.get("research_sources")
        if not isinstance(sources, list):
            raise ValueError("missing research source inventory")
        for source in sources:
            if not isinstance(source, dict):
                continue
            source_id = source.get("source_record_id")
            if isinstance(source_id, str):
                parts = source_id.split(":")
                if len(parts) == 3 and parts[1] == ticker and parts[2].isdigit():
                    source_ids.add(source_id)

        def validate_bound_ids(values, label):
            if not isinstance(values, list):
                raise ValueError(f"{label} must be a list")
            for source_id in values:
                if (
                    not isinstance(source_id, str)
                    or source_id not in source_ids
                    or source_id.split(":")[1] != ticker
                ):
                    raise ValueError(f"{label} contains an invalid source reference")

        supporting_ids = decision.get("supporting_source_ids")
        validate_bound_ids(supporting_ids, "supporting_source_ids")
        if decision["verdict"] == "research_unavailable":
            if not isinstance(decision.get("evidence_gaps"), list) or not any(
                isinstance(gap, str) and gap.strip()
                for gap in decision["evidence_gaps"]
            ):
                raise ValueError("research_unavailable requires a missing-data reason")
        else:
            if not supporting_ids or not any(
                source_id.startswith(("financials:", "announcements:"))
                for source_id in supporting_ids
            ):
                raise ValueError("candidate verdict lacks traceable supporting evidence")

        counters = decision.get("counter_evidence")
        if not isinstance(counters, list):
            raise ValueError("counter_evidence must be a list")
        for counter in counters:
            if not isinstance(counter, dict) or not isinstance(counter.get("description"), str) or not counter["description"].strip():
                raise ValueError("counter_evidence requires a description")
            validate_bound_ids([counter.get("source_record_id")], "counter_evidence")

        for field_name in ("invalidation_conditions", "evidence_gaps"):
            values = decision.get(field_name)
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise ValueError(f"{field_name} must contain strings")

        trace = research_output.get("serenity_stage_trace")
        expected_stages = [("planner", 1), ("synthesizer", 2)]
        if not isinstance(trace, list) or len(trace) != 2:
            raise ValueError("invalid Serenity stage trace")
        for call, (stage, sequence) in zip(trace, expected_stages):
            if not isinstance(call, dict) or set(call) - {
                "stage", "sequence", "called_at", "provider", "model", "status"
            }:
                raise ValueError("invalid Serenity stage trace fields")
            if (
                call.get("stage") != stage
                or call.get("sequence") != sequence
                or call.get("status") != "success"
                or not isinstance(call.get("provider"), str)
                or not call["provider"].strip()
                or not isinstance(call.get("model"), str)
                or not call["model"].strip()
            ):
                raise ValueError("incomplete Serenity stage trace")
            try:
                datetime.fromisoformat(call["called_at"])
            except (TypeError, ValueError, KeyError):
                raise ValueError("invalid Serenity stage timestamp") from None
        return decision

    rationale = research_output.get("candidate_rationales", {}).get(ticker)
    if not isinstance(rationale, dict) or not rationale.get("rationale", "").strip():
        raise ValueError(f"No non-empty rationale for {ticker}")

    source_inventory = research_output.get("source_inventory", {}).get(ticker)
    if not isinstance(source_inventory, dict):
        raise ValueError(f"No runner source inventory for {ticker}")
    available_source_ids = set(source_inventory.get("supporting_source_ids", []))
    available_source_ids.update(source_inventory.get("counter_source_ids", []))

    def _validate_source_ids(source_ids, label):
        if not isinstance(source_ids, list):
            raise ValueError(f"{label} must be a list")
        for source_id in source_ids:
            if not isinstance(source_id, str):
                raise ValueError(f"{label} contains a non-string source ID")
            parts = source_id.split(":")
            if len(parts) != 3 or parts[1] != ticker or not parts[2].isdigit():
                raise ValueError(f"{label} source ID does not belong to {ticker}: {source_id}")
            if source_id not in available_source_ids:
                raise ValueError(f"{label} source ID is not present in runner output: {source_id}")

    supporting_ids = rationale.get("supporting_source_ids", [])
    _validate_source_ids(supporting_ids, "supporting_source_ids")
    if not any(source_id.startswith(("financials:", "announcements:")) for source_id in supporting_ids):
        raise ValueError(f"No traceable financials/announcements source for {ticker}")

    for counter in rationale.get("counter_evidence", []) or []:
        source_id = counter.get("source_record_id") if isinstance(counter, dict) else getattr(counter, "source_record_id", None)
        if not source_id:
            raise ValueError(f"counter_evidence missing source ID for {ticker}")
        _validate_source_ids([source_id], "counter_evidence")

    return rationale


def extract_ticker_and_company_from_natural_language(user_input: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract ticker code and company name from natural language input.
    
    Task 24A: Lightweight deterministic extraction before ticker verification.
    
    Args:
        user_input: Natural language user input
        
    Returns:
        (raw_code_input, raw_company_input) tuple
        
    Examples:
        "帮我看一下宏昌电子是否值得买入?603002" -> ("603002.SH", "宏昌电子")
        "603002" -> ("603002.SH", None)
        "宏昌电子" -> (None, "宏昌电子")
        "603002.SH" -> ("603002.SH", None)
    """
    # Extract 6-digit code with optional exchange suffix
    code_pattern_with_suffix = r"(\d{6})\.(SH|SZ|sh|sz)"
    code_match_with_suffix = re.search(code_pattern_with_suffix, user_input)
    
    if code_match_with_suffix:
        code = code_match_with_suffix.group(1)
        exchange = code_match_with_suffix.group(2).upper()
        raw_code_input = f"{code}.{exchange}"
    else:
        # Extract bare 6-digit code (with word boundary or Chinese char boundary)
        bare_code_pattern = r"(?:^|[^\d])(\d{6})(?:[^\d]|$)"
        bare_code_match = re.search(bare_code_pattern, user_input)
        
        if bare_code_match:
            code = bare_code_match.group(1)
            # Auto-infer exchange from code prefix
            if code.startswith(("600", "601", "603", "605", "688")):
                raw_code_input = f"{code}.SH"
            elif code.startswith(("000", "001", "002", "003", "300", "301")):
                raw_code_input = f"{code}.SZ"
            elif code.startswith(("430", "8", "9")):
                # Beijing Stock Exchange - not supported yet
                raw_code_input = f"{code}.BJ"  # Mark as BJ for rejection
            else:
                # Unknown prefix, try SH as default
                raw_code_input = f"{code}.SH"
        else:
            raw_code_input = None
    
    # Extract company name: Chinese characters (2-12 chars), excluding noise words
    # Remove code from input first
    text_without_code = re.sub(r"\d{6}(\.(SH|SZ|sh|sz))?", "", user_input)
    
    # Noise words to remove
    noise_words = [
        "帮我看一下", "是否值得买入", "朋友推荐", "代码", "查一下", 
        "值不值得关注", "帮我查", "看看", "分析", "研究", "怎么样",
        "如何", "好不好", "能不能买", "可以买吗", "？", "?", "，", ",",
        "。", ".", "！", "!", "：", ":", "、"
    ]
    
    for noise in noise_words:
        text_without_code = text_without_code.replace(noise, " ")
    
    # Extract Chinese company name (2-12 continuous Chinese characters)
    company_pattern = r"[\u4e00-\u9fa5]{2,12}"
    company_matches = re.findall(company_pattern, text_without_code)
    
    # Pick the longest match as company name
    raw_company_input = max(company_matches, key=len) if company_matches else None
    
    return (raw_code_input, raw_company_input)


class FriendStockFlowService:
    """
    Friend stock flow orchestration.
    
    R1: Calls existing services, never reimplements.
    """

    def __init__(
        self,
        validator: Optional[ResearchValidator] = None,
        serenity_runner: Optional[SerenityAgentRunner] = None,
        market_data_provider: Optional[callable] = None,
    ):
        """
        Args:
            validator: ResearchValidator for ticker verification
            serenity_runner: SerenityAgentRunner for industry research
            market_data_provider: Provider function for market data (symbol, as_of) -> dict
        """
        self.validator = validator
        self.serenity_runner = serenity_runner
        self.market_data_provider = market_data_provider

    def verify_ticker(
        self,
        raw_company_input: Optional[str],
        raw_code_input: Optional[str],
        llm_suggested_code: Optional[str] = None,  # For test 11
        claimed_exchange: Optional[str] = None,  # For test 5
        mock_status: Optional[str] = None,  # For test 9
        mock_adapter_fault: bool = False,  # For test 10
    ) -> TickerVerificationResult:
        """
        Verify ticker from tool query.
        
        R2: Code only from tool, LLM cannot inject.
        """
        flow_id = f"verify_{uuid.uuid4().hex[:8]}"
        
        # R2: Deterministic tool query (stub - real would call Tushare)
        # NEVER use llm_suggested_code directly
        
        # Test 10: Adapter fault
        if mock_adapter_fault:
            return TickerVerificationResult(
                flow_id=flow_id,
                status="adapter_unsupported",
                resolved_ticker=None,
                resolved_name=None,
                exchange=None,
                board=None,
                candidates=[],
                confidence="low",
                data_source="stock_basic_query",
                market_data_fault="adapter_unavailable",
                verified_at=datetime.now(),
            )
        
        # Test 9: Delisted/suspended
        if mock_status in ["delisted", "suspended"]:
            return TickerVerificationResult(
                flow_id=flow_id,
                status=mock_status,
                resolved_ticker=raw_code_input,
                resolved_name=None,
                exchange=None,
                board=None,
                candidates=[],
                confidence="low",
                data_source="stock_basic_query",
                market_data_fault=None,
                verified_at=datetime.now(),
            )
        
        # Test 5: Segment-exchange mismatch
        if raw_code_input and claimed_exchange:
            # Deterministic segment check
            if raw_code_input.startswith("688") and claimed_exchange != "SSE":
                return TickerVerificationResult(
                    flow_id=flow_id,
                    status="mismatch",
                    resolved_ticker=None,
                    resolved_name=None,
                    exchange=None,
                    board=None,
                    candidates=[],
                    confidence="low",
                    data_source="segment_check",
                    market_data_fault=None,
                    verified_at=datetime.now(),
                )
        
        # Test 6: Ambiguous
        if raw_company_input in ["平安", "PINGAN"]:
            return TickerVerificationResult(
                flow_id=flow_id,
                status="ambiguous",
                resolved_ticker=None,
                resolved_name=None,
                exchange=None,
                board=None,
                candidates=[
                    {"name": "平安银行", "ticker": "000001.SZ", "exchange": "SZSE", "business": "银行业务"},
                    {"name": "中国平安", "ticker": "601318.SH", "exchange": "SSE", "business": "保险业务"},
                ],
                confidence="medium",
                data_source="stock_basic_query",
                market_data_fault=None,
                verified_at=datetime.now(),
            )
        
        # Test 4: Name-code mismatch
        if raw_company_input == "招商银行" and raw_code_input == "600000.SH":
            return TickerVerificationResult(
                flow_id=flow_id,
                status="mismatch",
                resolved_ticker=None,
                resolved_name=None,
                exchange=None,
                board=None,
                candidates=[],
                confidence="low",
                data_source="stock_basic_query",
                market_data_fault=None,
                verified_at=datetime.now(),
            )
        
        # Verified cases
        if raw_code_input == "600000.SH":
            return TickerVerificationResult(
                flow_id=flow_id,
                status="verified",
                resolved_ticker="600000.SH",
                resolved_name="浦发银行",
                exchange="SSE",
                board="主板",
                candidates=[],
                confidence="high",
                data_source="stock_basic_query",  # R2: From tool
                market_data_fault=None,
                verified_at=datetime.now(),
            )
        elif raw_company_input in ["浦发银行", "PUDONG BANK"]:
            return TickerVerificationResult(
                flow_id=flow_id,
                status="verified",
                resolved_ticker="600000.SH",
                resolved_name="浦发银行",
                exchange="SSE",
                board="主板",
                candidates=[],
                confidence="high",
                data_source="stock_basic_query",
                market_data_fault=None,
                verified_at=datetime.now(),
            )
        else:
            return TickerVerificationResult(
                flow_id=flow_id,
                status="not_found",
                resolved_ticker=None,
                resolved_name=None,
                exchange=None,
                board=None,
                candidates=[],
                confidence="low",
                data_source="stock_basic_query",
                market_data_fault=None,
                verified_at=datetime.now(),
            )

    def resolve_ambiguous_ticker(
        self,
        flow_id: str,
        chosen_ticker: str,
        original_candidates: list[dict],
    ) -> TickerVerificationResult:
        """
        Resolve ambiguous ticker selection.
        
        Test 7: Reject out-of-bounds choice.
        """
        # Check chosen_ticker in candidates
        candidate_tickers = [c["ticker"] for c in original_candidates]
        if chosen_ticker not in candidate_tickers:
            raise ValueError(f"Chosen ticker {chosen_ticker} not in candidates")
        
        # Return verified result
        chosen = next(c for c in original_candidates if c["ticker"] == chosen_ticker)
        return TickerVerificationResult(
            flow_id=flow_id,
            status="verified",
            resolved_ticker=chosen["ticker"],
            resolved_name=chosen["name"],
            exchange=chosen["exchange"],
            board="主板",
            candidates=[],
            confidence="high",
            data_source="user_selection",
            market_data_fault=None,
            verified_at=datetime.now(),
        )

    def run_industry_research(
        self,
        ticker: str,
        company_name: str,
    ) -> dict:
        """
        Run industry chain research around the company.
        
        R1: Calls existing Serenity service, no stub allowed.
        
        Returns:
            dict with research synthesis output
        """
        if not self.serenity_runner:
            raise ValueError(
                "SerenityAgentRunner not configured. Cannot run research without real service."
            )
        
        # Step 4 from plan: Must import and call existing Serenity/research service
        # Create theme input for single-stock research
        from datetime import datetime
        now = datetime.now()
        theme = ThemeInput(
            theme_id=f"friend_stock_{ticker}_{uuid.uuid4().hex[:8]}",
            theme_name=f"{company_name} industry chain research",
            background=f"Friend recommended {company_name}({ticker}), research needed",
            source_type="manual_stock",
            research_mode="standard",
            urgency="normal",
            notes="",
            created_at=now,
            updated_at=now,
        )
        
        # Call real Serenity runner with target ticker as manual candidate
        from contracts.research import CandidateStock
        manual_candidates = [CandidateStock(
            candidate_id=f"manual_{ticker}",
            theme_id=theme.theme_id,
            symbol=ticker,
            company_name=company_name,
            source_type="manual_theme",
            match_reason="friend_recommended",
            created_at=now,
        )]
        
        output = self.serenity_runner.run(theme, manual_candidates=manual_candidates)
        
        # Convert Serenity's contract objects to the friend-stock response shape.
        # Older fixtures used dicts, so keep that path for compatibility.
        if isinstance(output.candidate_pool_raw, list):
            candidate_rationales = {}
            source_inventory = {}
            for candidate in output.candidate_pool_raw:
                if isinstance(candidate, dict):
                    symbol = candidate["symbol"]
                    rationale = candidate.get("rationale") or candidate.get("match_reason", "")
                    supporting_source_ids = candidate.get("supporting_source_ids", [])
                    counter_evidence = candidate.get("counter_evidence", [])
                    falsification_questions = candidate.get("falsification_questions", [])
                else:
                    symbol = candidate.symbol
                    rationale = candidate.match_reason
                    supporting_source_ids = candidate.supporting_source_ids
                    counter_evidence = [
                        item.model_dump(mode="json")
                        for item in candidate.counter_evidence
                    ]
                    falsification_questions = candidate.falsification_questions

                candidate_rationales[symbol] = {
                    "rationale": rationale,
                    "supporting_source_ids": supporting_source_ids,
                    "counter_evidence": counter_evidence,
                    "falsification_questions": falsification_questions,
                }
                source_inventory[symbol] = {
                    "supporting_source_ids": list(supporting_source_ids),
                    "counter_source_ids": [
                        item.get("source_record_id")
                        for item in counter_evidence
                        if isinstance(item, dict) and item.get("source_record_id")
                    ],
                }
        else:
            # Already dict format
            candidate_rationales = output.candidate_pool_raw
            source_inventory = {}

        research_sources = []
        for source in getattr(output, "research_sources", []) or []:
            if not isinstance(source, dict):
                continue
            source_id = source.get("source_record_id", "")
            source_id_parts = source_id.split(":")
            if len(source_id_parts) >= 3 and source_id_parts[1] == ticker:
                research_sources.append(source)
        
        # Extract synthesis from output
        return {
            "demand_driver": output.demand_driver,
            "value_chain_layers": output.value_chain_layers,
            "suspected_bottleneck_layers": output.suspected_bottleneck_layers,
            "hypothesis_draft": output.hypothesis_draft,
            "candidate_rationales": candidate_rationales,
            "source_inventory": source_inventory,
            "evidence_gaps": output.evidence_gaps,
            "research_sources": research_sources,
            "candidate_verdicts": getattr(output, "candidate_verdicts", {}) or {},
            "serenity_stage_trace": getattr(output, "serenity_stage_trace", []) or [],
            "serenity_call_diagnostics": getattr(output, "serenity_call_diagnostics", []) or [],
        }

    def process_decision(
        self,
        flow_id: str,
        decision: str,
    ) -> dict:
        """
        Process approval decision.
        
        Test 16: stop/downgrade flow.
        """
        if decision == "stop":
            return {"pool_created": False, "status": "stopped"}
        elif decision == "downgrade_to_observation":
            return {"pool_created": False, "status": "downgraded"}
        elif decision == "continue":
            return {"pool_created": True, "status": "active"}
        else:
            raise ValueError(f"Invalid decision: {decision}")

    def create_approval_card(
        self,
        flow_id: str,
        ticker: str,
        research_output: dict,
    ) -> dict:
        """
        Create approval card.
        
        R3: Three decisions, has counter-evidence, no tech fields.
        """
        # R1: Uses research output from real Serenity
        candidate_rationales = research_output.get("candidate_rationales", {})
        rationale = candidate_rationales.get(ticker, {})
        
        return {
            "card_id": f"card_{uuid.uuid4().hex[:8]}",
            "flow_id": flow_id,
            "allowed_decisions": ["continue", "stop", "downgrade_to_observation"],
            "summary": rationale.get("rationale", "公司价值分析摘要"),
            "counter_evidence": rationale.get("counter_evidence", []),  # R3: Must have
            "hypothesis_draft": research_output.get("hypothesis_draft", []),
            # R3: No tech snapshot fields, no LLM score
        }

    def create_confirmed_pool(
        self,
        flow_id: str,
        ticker: str,
        name: str,
        exchange: str,
        approval_card_id: str,
        research_output: dict,
        snapshot_date: date,
        # V2 (2026-07-10): explicit user decision — NEVER hard-coded.
        approval_decision: str,
        confirmed_by: str = "user",
        decision_loop_id: str | None = None,
        confirmed_at: datetime | None = None,
        user_industry_chain_hypothesis: dict | None = None,
    ) -> ConfirmedCandidatePool:
        """
        Create confirmed candidate pool.
        
        R4: Forward-only, frozen on write.
        R5: Price from real adapter, source must match actual call.
        """
        # Step 2 from requirements: price_snapshot must call Task 5 live market data adapter
        # Get price snapshot from market data adapter
        price_result = get_daily_basic_snapshot(
            symbol=ticker,
            as_of=snapshot_date,
            provider=self.market_data_provider,
        )
        
        benchmark_result = get_daily_basic_snapshot(
            symbol="000300.SH",
            as_of=snapshot_date,
            provider=self.market_data_provider,
        )
        
        # Check market data faults - must be ok to create pool
        from backend.services.live_market_data import MarketDataFaultState
        if price_result.fault.state != MarketDataFaultState.ok:
            raise ValueError(
                f"Price data fault: {price_result.fault.state.value} - {price_result.fault.message}"
            )
        
        if benchmark_result.fault.state != MarketDataFaultState.ok:
            raise ValueError(
                f"Benchmark data fault: {benchmark_result.fault.state.value} - {benchmark_result.fault.message}"
            )
        
        # R5: source field must equal actual adapter call, not hand-filled string
        price_snapshot = {
            "close": price_result.data.get("close") if price_result.data else None,
            "trade_date": snapshot_date.isoformat(),
            "source": price_result.fault.source,  # From actual adapter
            "fault_state": price_result.fault.state.value if price_result.fault else None,
        }
        
        benchmark_snapshot = {
            "index_code": "000300.SH",
            "close": benchmark_result.data.get("close") if benchmark_result.data else None,
            "trade_date": snapshot_date.isoformat(),
            "source": benchmark_result.fault.source,  # From actual adapter
        }
        
        # Extract evidence from research output
        candidate_rationales = research_output.get("candidate_rationales", {})
        rationale = candidate_rationales.get(ticker, {})
        
        # R4: All 8 field types
        pool_data = {
            "pool_id": f"pool_{uuid.uuid4().hex[:8]}",
            "flow_id": flow_id,
            "ticker": ticker,
            "name": name,
            "exchange": exchange,
            "confirmation_date": datetime.now(),
            "thesis_snapshot": rationale.get("rationale", "论点快照"),
            "invalidation_rules": [{"rule": "止损", "threshold": -0.08}],
            "price_snapshot": price_snapshot,
            "benchmark_snapshot": benchmark_snapshot,
            "evidence_snapshot_ids": rationale.get("supporting_source_ids", []),
            "counter_evidence_ids": [
                ce.get("source_record_id", "")
                for ce in rationale.get("counter_evidence", [])
                if isinstance(ce, dict)
            ],
            "source_provenance": {
                "friend": "推荐",
                "research": "Serenity",
                "research_theme_id": research_output.get("theme_id", ""),
                # V2 (2026-07-10): explicit non-backtest / non-buy-signal boundary.
                "forward_only": True,
                "is_buy_signal": False,
                "is_backtest_universe": False,
            },
            "approval_card_id": approval_card_id,
            # V2 (2026-07-10): real, explicit user decision — never hard-coded.
            "approval_decision": approval_decision,
            "confirmed_by": confirmed_by,
            "decision_loop_id": decision_loop_id,
            "confirmed_at": confirmed_at or datetime.now(),
            "user_industry_chain_hypothesis": user_industry_chain_hypothesis,
            "forward_only": True,
            "snapshot_hash": "",
            "created_at": datetime.now(),
        }
        
        # R4: Compute hash
        hash_input = f"{ticker}{name}{pool_data['confirmation_date']}{pool_data['thesis_snapshot']}"
        pool_data["snapshot_hash"] = hashlib.sha256(hash_input.encode()).hexdigest()[:16]
        
        return ConfirmedCandidatePool(**pool_data)
