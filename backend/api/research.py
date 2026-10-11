"""
Research API endpoints.

Routes:
- POST /api/research/themes - Create theme
- GET /api/research/themes - List themes
- GET /api/research/themes/{theme_id} - Get theme
- POST /api/research/themes/{theme_id}/candidates - Add candidate
- POST /api/research/themes/{theme_id}/run-serenity - Run Serenity (auto-pass analysis)
- POST /api/research/candidates/run-evidence - Run Evidence (auto-pass analysis)
- POST /api/research/actions/apply - Apply proposed action
- GET /api/research/themes/{theme_id}/pending-actions - List pending actions
- GET /api/research/themes/{theme_id}/conversation - Get conversation history
- POST /api/research/themes/{theme_id}/conversation - Send message
- POST /api/research/candidates/{candidate_id}/confirm - Confirm candidate
- POST /api/research/candidates/{candidate_id}/reject - Reject candidate
- POST /api/research/themes/{theme_id}/reopen-to-serenity - Reopen theme to Serenity
- POST /api/research/candidates/{candidate_id}/reopen-to-evidence - Reopen candidate to Evidence
- GET /api/research/themes/{theme_id}/confirmed-candidates - List confirmed candidates

Key rules:
- run_serenity and run_evidence are auto-pass analysis routes (do not increment board_version)
- Only state-changing actions use ProposedAction and reducer apply
- board_version is theme-level and increments only after successful reducer-applied state mutation
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import uuid
import hashlib
import os
import re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal
from backend.db.research import ResearchDB
from backend.services.research_action_reducer import ResearchActionReducer
from backend.services.research_conversation import ResearchConversationService
from backend.services.research_validation import ResearchValidator
from backend.services.serenity_stub import SerenityStubRunner
from backend.services.evidence_light import EvidenceLightRunner
from contracts.research import ThemeInput, ProposedAction

# P1-1 Route Decision handlers
from backend.api.workbench_handlers import (
    HandlerResult,
    handle_market_scan,
    handle_friend_stock,
    handle_strategy_idea,
    handle_position_followup,
    handle_theme_research_deferred,
    handle_clarification,
    handle_add_to_observation,
)
from backend.db.agent_workbench import list_messages, list_artifact_refs


class CreateThemeRequest(BaseModel):
    theme_name: str
    background: str
    source_type: str
    research_mode: str = "standard"
    urgency: str = "normal"
    notes: str = ""


class AddCandidateRequest(BaseModel):
    symbol: str
    verification_id: str
    match_reason: str
    source_type: str
    applied_by: str = "user"


class ConversationRequest(BaseModel):
    content: str


class ExecutionFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(pattern=r"^\d{6}$")
    action: Literal["buy", "sell"]
    position_id: str | None = None
    trade_type: Literal["actual", "simulated"]
    price: Decimal = Field(gt=0)
    quantity: int = Field(gt=0)
    execution_date: date
    operation_id: str = Field(min_length=1, max_length=128)
    confirmed_already_executed: bool
    fees: Decimal | None = Field(default=None, ge=0)
    trade_source: Literal["self_research", "friend", "media", "system_suggestion"] | None = None
    reason: str | None = Field(default=None, max_length=160)
    sell_reason: Literal["target", "stop", "changed_judgment", "fear", "urgent_cash"] | None = None
    exit_plan_target_price: Decimal | None = Field(default=None, gt=0)
    exit_plan_stop_price: Decimal | None = Field(default=None, gt=0)
    exit_plan_conditions: str | None = Field(default=None, max_length=300)
    confirm_quantity_anomaly: bool = False

    @model_validator(mode="after")
    def validate_structured_execution(self):
        if self.action == "sell" and not self.position_id:
            raise ValueError("卖出必须从持仓页面选择现有持仓。")
        if self.action == "buy" and self.position_id is not None:
            raise ValueError("买入记录不能指定已有持仓。")
        if self.action == "sell" and self.sell_reason is None:
            raise ValueError("请选择卖出原因。")
        if self.action == "buy" and self.sell_reason is not None:
            raise ValueError("买入记录不能填写卖出原因。")
        if self.action == "sell" and any((
            self.exit_plan_target_price is not None,
            self.exit_plan_stop_price is not None,
            bool((self.exit_plan_conditions or "").strip()),
        )):
            raise ValueError("个人退出计划只用于买入记录。")
        if self.exit_plan_conditions is not None:
            self.exit_plan_conditions = self.exit_plan_conditions.strip() or None
        if self.reason is not None:
            self.reason = self.reason.strip() or None
        return self


class SingleSecurityResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^\d{6}$")


class ApplyActionRequest(BaseModel):
    action_id: str
    applied_by: str


class ReopenRequest(BaseModel):
    actor: str = "user"
    reason: str


class ConfirmCandidateRequest(BaseModel):
    approval_card_id: str | None = None
    confirmation_reason: str
    evidence_level: str
    confirmed_by: str
    pool_snapshot_date: str
    thesis_snapshot: str
    invalidation_rules: list[dict]
    price_snapshot: dict
    benchmark_snapshot: dict
    override_reason: str | None = None
    evidence_snapshot_ids: list[str] = []
    primary_evidence_snapshot_id: str | None = None


def _safe_research_sentence(text: object, symbol: str) -> str | None:
    """Reject an entire model sentence if it contains an unallowlisted number."""
    if not isinstance(text, str):
        return None
    value = text.strip()
    if not value or len(value) > 240 or "\n" in value or "\r" in value or "字段" in value:
        return None
    if any(character in value for character in "¥￥$%％"):
        return None

    allowed_codes = {symbol}
    if "." in symbol:
        allowed_codes.add(symbol.split(".", 1)[0])
    for match in re.finditer(r"(?<![A-Za-z])\d+(?:\.\d+)?", value):
        token = match.group(0)
        if token not in allowed_codes:
            return None
        following = value[match.end():]
        if token != symbol and re.match(r"(?:元|价|股|份|倍|点|日|年|月|周|天|次)", following):
            return None
    chinese_quantity = re.compile(
        r"(?:第\s*)?[零一二三四五六七八九十百千万亿两]+"
        r"(?:点[零一二三四五六七八九十百千万亿两]+)?"
        r"(?:元|股|份|倍|个|日|年|月|周|天|项|家|次|只|种|季|成)"
    )
    if chinese_quantity.search(value):
        return None
    sentence_text = value
    for code in sorted(allowed_codes, key=len, reverse=True):
        sentence_text = sentence_text.replace(code, "")
    if sum(character in sentence_text for character in "。！？.!?") > 1:
        return None
    return value if value.endswith(("。", "！", "？", ".", "!", "?")) else f"{value}。"


def _deterministic_etf_rationale(bundle: dict, verdict: str | None = None) -> str:
    """Summarize only which ETF data was verified and which decision gaps remain."""
    metrics = bundle.get("metrics", {}) if isinstance(bundle, dict) else {}
    verified = []
    if metrics.get("price_change_1y"):
        verified.append("区间报告收盘价变化")
    elif metrics.get("latest_price"):
        verified.append("最近报告收盘价")
    distance = metrics.get("distance_from_1y_high_pct")
    if isinstance(distance, dict):
        basis = "日内最高价" if distance.get("field") == "high" else "最高收盘价"
        verified.append(f"距区间{basis}的距离")
    if metrics.get("average_amount_20d"):
        verified.append("近期成交额")
    if metrics.get("trailing_cash_dividend_per_share"):
        verified.append("已实施现金派息")
    if metrics.get("trailing_dividend_yield_valuation"):
        verified.append("ETF自身分红收益率历史分位估值参考")
    if not verified:
        verified.append("可核验行情信息")

    remaining = ["基金持仓与行业权重", "实际跟踪差异"]
    if metrics.get("underlying_pe") is None and metrics.get("underlying_pb") is None:
        remaining.append("跟踪指数估值")
    if verdict == "research_positive":
        closing = "现有证据支持继续人工研究；这些缺口需要补齐，且该判断不构成买入或执行许可。"
    elif verdict == "research_reject":
        closing = "现有证据不支持继续研究；后续新增证据可能改变该判断。"
    elif verdict == "research_unavailable":
        closing = "当前无法形成完整判断，需要先补充相关证据。"
    else:
        closing = "当前只适合继续观察。"
    return f"已核验ETF的{'、'.join(verified)}；但{'、'.join(remaining)}仍有缺口，{closing}"


def _etf_reason_uses_available_data(reason: str, bundle: dict) -> bool:
    """Require a model reason to mention a metric that this ETF bundle actually verified."""
    metrics = bundle.get("metrics", {}) if isinstance(bundle, dict) else {}
    supported_terms = []
    if metrics.get("price_change_1y") or metrics.get("latest_price"):
        supported_terms.extend(("价格", "收盘价", "涨跌"))
    if metrics.get("distance_from_1y_high_pct"):
        supported_terms.extend(("高点", "最高价", "最高收盘"))
    if metrics.get("average_amount_20d"):
        supported_terms.extend(("成交额", "流动性"))
    if metrics.get("trailing_cash_dividend_per_share"):
        supported_terms.extend(("现金分红", "分红", "派息", "股息"))
    if metrics.get("underlying_pe") or metrics.get("underlying_pb"):
        supported_terms.extend(("估值", "PE", "PB"))
    if metrics.get("fund_size_shares"):
        supported_terms.extend(("基金份额", "份额"))
    return any(term in reason for term in supported_terms)


def create_research_app(
    db: ResearchDB | None = None,
    conversation_mode: str = "deterministic",
    serenity_execution_mode: str = "stub",
    validator: ResearchValidator | None = None,
    serenity_runner=None,
    market_data_provider=None,
    allow_test_serenity_runner: bool = False,
    stock_resolver_fixture: dict | None = None,
    stock_resolver_override=None,  # New: for test injection
    strategy_flow_service_override=None,  # New: for test injection
    market_scan_lane_runner=None,  # Test-only deterministic lane boundary
) -> FastAPI:
    """
    Create Research API app.

    Args:
        db: Research database (if None, creates default)
        conversation_mode: Conversation mode ("real" or "deterministic", default "deterministic")
        serenity_execution_mode: Serenity execution mode ("stub" or "two_phase", default "stub")
        validator: ResearchValidator (if None, creates default with env config)
        serenity_runner: SerenityRunner (if provided, must match mode constraints)
        market_data_provider: Market data provider function (symbol, as_of) -> dict
        allow_test_serenity_runner: Allows tests to inject a fake runner without real credentials
        stock_resolver_fixture: Test fixture for StockIdentityResolver (deterministic mode only)

    Returns:
        FastAPI app
    """
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3010",
            "http://127.0.0.1:3010",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if db is None:
        db = ResearchDB()  # V2 Task 2: default path restored

    # Store DB in app.state for test access
    app.state.db = db

    # Strict conversation_mode validation
    if conversation_mode not in ("real", "deterministic"):
        raise ValueError(
            f"Invalid conversation_mode='{conversation_mode}'. "
            "Allowed values: 'real', 'deterministic'"
        )

    # Strict configuration matrix validation
    if conversation_mode == "real":
        if serenity_execution_mode != "two_phase":
            raise ValueError(
                f"conversation_mode='real' requires serenity_execution_mode='two_phase', "
                f"but got '{serenity_execution_mode}'. No silent fallback allowed."
            )

        # Check LLM API key (skip only for explicit test runner injection)
        if not (allow_test_serenity_runner and serenity_runner is not None):
            llm_key = os.getenv("RESEARCH_LLM_API_KEY")
            if not llm_key:
                raise ValueError(
                    "Real mode requires RESEARCH_LLM_API_KEY environment variable. "
                    "Set the variable or use conversation_mode='deterministic' for testing."
                )

            # Check Tushare token
            tushare_token = os.getenv("TUSHARE_TOKEN")
            if not tushare_token:
                raise ValueError(
                    "Real mode requires TUSHARE_TOKEN environment variable. "
                    "Set the variable or use conversation_mode='deterministic' for testing."
                )

    if conversation_mode == "deterministic":
        if serenity_execution_mode != "stub":
            raise ValueError(
                f"conversation_mode='deterministic' only allows serenity_execution_mode='stub', "
                f"but got '{serenity_execution_mode}'. Use conversation_mode='real' for two_phase."
            )

    if validator is None:
        validator = ResearchValidator()

    # V2 Task 2: wire real Tushare daily-basic provider for pool price snapshot
    # (real mode only; deterministic mode injects its own provider for tests).
    # Guard on a real token so token-less test envs don't crash at app build.
    if (
        market_data_provider is None
        and conversation_mode == "real"
        and os.getenv("TUSHARE_TOKEN")
    ):
        _tc = validator.tushare_client

        def _norm_tushare_code(symbol: str) -> str:
            """Normalize a 6-digit code to Tushare ts_code (e.g. 600519 -> 600519.SH)."""
            s = (symbol or "").strip()
            if "." in s:
                return s
            if len(s) == 6:
                if s[0] == "6":
                    return s + ".SH"
                if s[0] in ("0", "3"):
                    return s + ".SZ"
                if s[0] in ("8", "4"):
                    return s + ".BJ"
            return s

        def _real_daily_basic(symbol: str, as_of: date) -> dict:
            """Real Tushare daily-basic lookup; tolerates non-trading days."""
            ts_code = _norm_tushare_code(symbol)
            end = as_of.strftime("%Y%m%d")
            start = (as_of - timedelta(days=10)).strftime("%Y%m%d")
            
            # ponytail: known benchmarks route to index_daily
            api = "index_daily" if ts_code in ["000300.SH", "000016.SH", "399001.SZ", "399006.SZ"] else "daily"
            
            try:
                df = _tc.query(api, ts_code=ts_code, start_date=start, end_date=end)
            except Exception:
                return {}
            if df is None or getattr(df, "empty", True) or len(df) == 0:
                return {}
            df = df.sort_values("trade_date")
            row = df.iloc[-1]
            return {
                "close": float(row["close"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "vol": float(row["vol"]) if "vol" in row else float(row.get("volume", 0.0)),
            }

        market_data_provider = _real_daily_basic

    reducer = ResearchActionReducer(db, validator)
    conversation: ResearchConversationService | None = None

    def get_conversation_service() -> ResearchConversationService:
        nonlocal conversation
        if conversation is None:
            conversation = ResearchConversationService(db, mode=conversation_mode)
        return conversation

    # Build or validate Serenity runner
    if serenity_runner is not None:
        # Validate injected runner matches mode constraints
        from backend.services.serenity_stub import SerenityStubRunner
        from backend.services.serenity_agent import SerenityAgentRunner

        if conversation_mode == "real":
            is_allowed_test_runner = (
                allow_test_serenity_runner
                and type(serenity_runner).__module__ == "tests.fake_serenity_runner"
                and type(serenity_runner).__name__ == "FakeSerenityRunner"
                and hasattr(serenity_runner, "run")
            )

            if not isinstance(serenity_runner, SerenityAgentRunner) and not is_allowed_test_runner:
                raise ValueError(
                    f"conversation_mode='real' requires SerenityAgentRunner, "
                    f"but got {type(serenity_runner).__name__}."
                )

        if conversation_mode == "deterministic":
            # Must be SerenityStubRunner
            if not isinstance(serenity_runner, SerenityStubRunner):
                raise ValueError(
                    f"conversation_mode='deterministic' requires SerenityStubRunner, "
                    f"but got {type(serenity_runner).__name__}. "
                    "Remove serenity_runner parameter or use conversation_mode='real' for two_phase."
                )
    else:
        # Build runner based on mode
        if serenity_execution_mode == "stub":
            from backend.services.serenity_stub import SerenityStubRunner
            serenity_runner = SerenityStubRunner()
        elif serenity_execution_mode == "two_phase":
            # Build real SerenityAgentRunner with two-phase mode
            from backend.services.serenity_agent import SerenityAgentRunner
            from backend.services.serenity_tools import SerenityTools
            from backend.services.data_tools import DataToolsService
            from backend.services.llm_client import LLMClient

            llm_client = LLMClient()

            # Wire DataToolsService with Tushare client
            data_tools = DataToolsService(tushare_client=validator.tushare_client)
            data_tools._sse_transport = data_tools._fetch_sse_response
            tools = SerenityTools(data_tools=data_tools, validator=validator)

            serenity_runner = SerenityAgentRunner(
                llm_client=llm_client,
                validator=validator,
                tools=tools,
                mode="real",
                db=db,
                execution_mode="two_phase",
            )
        else:
            raise ValueError(
                f"Invalid serenity_execution_mode='{serenity_execution_mode}'. "
                "Allowed values: 'stub', 'two_phase'"
            )

    evidence_runner = EvidenceLightRunner()

    @app.post("/api/research/themes")
    def create_theme(request: CreateThemeRequest):
        """Create a new research theme."""
        now = datetime.now()
        theme_id = f"theme_{now.timestamp()}"

        theme = ThemeInput(
            theme_id=theme_id,
            theme_name=request.theme_name,
            background=request.background,
            source_type=request.source_type,
            research_mode=request.research_mode,
            urgency=request.urgency,
            notes=request.notes,
            status="draft",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        db.create_theme(theme)

        return {"theme_id": theme_id, "status": "created"}

    @app.get("/api/research/themes")
    def list_themes():
        """List all themes."""
        themes = db.list_themes()
        return [t.model_dump() for t in themes]

    @app.get("/api/research/themes/{theme_id}")
    def get_theme(theme_id: str):
        """Get a theme by ID."""
        theme = db.get_theme(theme_id)
        if not theme:
            raise HTTPException(status_code=404, detail="Theme not found")
        return theme.model_dump()

    @app.post("/api/research/themes/{theme_id}/candidates")
    def add_candidate(theme_id: str, request: AddCandidateRequest):
        """Add a verified candidate through the deterministic reducer."""
        theme = db.get_theme(theme_id)
        if not theme:
            raise HTTPException(status_code=404, detail="Theme not found")

        now = datetime.now()
        action = ProposedAction(
            action_id=f"action_{now.timestamp()}",
            action="add_candidate",
            target_id=theme_id,
            args={
                "symbol": request.symbol,
                "verification_id": request.verification_id,
                "source_type": request.source_type,
                "match_reason": request.match_reason,
            },
            rationale=request.match_reason,
            proposed_by="user",
            proposed_at=now,
            board_version=theme.board_version,
        )
        db.store_proposed_action(action)
        result = reducer.apply_action(action, applied_by=request.applied_by)
        if not result.applied:
            raise HTTPException(status_code=400, detail=result.rejection_reason)

        return {
            "candidate_id": f"cand_{action.action_id}",
            "action_id": action.action_id,
            "status": "added",
        }

    @app.get("/api/research/themes/{theme_id}/candidates")
    def list_candidates(theme_id: str):
        """List all candidates for a theme."""
        candidates = db.list_candidates(theme_id)
        return [c.model_dump(mode='json') for c in candidates]

    @app.post("/api/research/themes/{theme_id}/run-serenity")
    def run_serenity(theme_id: str):
        """
        Run Serenity analysis (auto-pass analysis route).

        Does not increment board_version.
        Persists SerenityOutput.
        """
        theme = db.get_theme(theme_id)
        if not theme:
            raise HTTPException(status_code=404, detail="Theme not found")

        manual_candidates = db.list_candidates(theme_id)
        output = serenity_runner.run(theme, manual_candidates)

        # Persist Serenity output
        db.store_serenity_output(output)

        return {
            "theme_id": theme_id,
            "status": "serenity_done",
            "candidate_count": len(output.candidate_pool_raw),
            "shortlist_count": len(output.candidate_shortlist),
        }

    @app.get("/api/research/themes/{theme_id}/serenity")
    def get_serenity_output(theme_id: str):
        """Get Serenity analysis output for a theme."""
        output = db.get_serenity_output(theme_id)
        if not output:
            raise HTTPException(status_code=404, detail="Serenity output not found")
        return output.model_dump()

    @app.post("/api/research/candidates/run-evidence")
    def run_evidence(candidate_ids: list[str]):
        """
        Run Evidence analysis (auto-pass analysis route).

        Does not increment board_version.
        Persists EvidenceOutput.
        """
        results = []
        for candidate_id in candidate_ids:
            candidate = db.get_candidate(candidate_id)
            if not candidate:
                continue

            # Get real ticker verification data
            # First check if we have a recent verification record
            verification_id = candidate.verification_id
            verification_record = None

            if verification_id:
                verification_record = db.get_ticker_verification(verification_id)

            if not verification_id or not verification_record:
                raise HTTPException(
                    status_code=400,
                    detail="Candidate is missing a persisted verification_id",
                )

            if not db.is_verification_valid(verification_id):
                raise HTTPException(
                    status_code=400,
                    detail="Candidate verification_id is expired or invalid",
                )

            if verification_record.symbol != candidate.symbol:
                raise HTTPException(
                    status_code=400,
                    detail=f"Candidate verification_id is for {verification_record.symbol}, not {candidate.symbol}",
                )

            hard_filter_snapshot = validator.get_hard_filter_snapshot(
                candidate.symbol,
                verification_record.status,
            )

            validation_result = validator.validate_candidate(
                symbol=candidate.symbol,
                company_name=verification_record.company_name or None,
                is_listed=hard_filter_snapshot.is_listed,
                is_st=hard_filter_snapshot.is_st,
                is_suspended=hard_filter_snapshot.is_suspended,
                avg_daily_volume=hard_filter_snapshot.avg_daily_volume,
            )

            # Run evidence
            evidence = evidence_runner.run_light_check(
                candidate_id=candidate_id,
                symbol=candidate.symbol,
                validation_result=validation_result,
                hard_filter_metadata={
                    "source": hard_filter_snapshot.source,
                    "retrieved_at": hard_filter_snapshot.retrieved_at.isoformat(),
                    "is_listed": hard_filter_snapshot.is_listed,
                    "is_st": hard_filter_snapshot.is_st,
                    "is_suspended": hard_filter_snapshot.is_suspended,
                    "avg_daily_volume": hard_filter_snapshot.avg_daily_volume,
                    "gaps": hard_filter_snapshot.gaps,
                },
            )

            # Persist Evidence output
            db.store_evidence_output(evidence)

            results.append({
                "candidate_id": candidate_id,
                "evidence_level": evidence.evidence_level,
                "blocking_issues": evidence.blocking_issues,
            })

        return {"results": results}

    @app.get("/api/research/candidates/{candidate_id}/evidence")
    def get_evidence_output(candidate_id: str):
        """Get Evidence output for a candidate."""
        output = db.get_evidence_output(candidate_id)
        if not output:
            raise HTTPException(status_code=404, detail="Evidence output not found")
        return output.model_dump()

    @app.post("/api/research/actions/apply")
    def apply_action(request: ApplyActionRequest):
        """Apply a proposed action through reducer."""
        proposed = db.get_proposed_action(request.action_id)
        if not proposed:
            raise HTTPException(status_code=404, detail="Proposed action not found")

        result = reducer.apply_action(proposed, applied_by=request.applied_by)

        return {
            "action_id": result.action_id,
            "applied": result.applied,
            "rejection_reason": result.rejection_reason,
        }

    @app.get("/api/research/themes/{theme_id}/pending-actions")
    def list_pending_actions(theme_id: str):
        """List pending proposed actions for a theme."""
        actions = db.list_pending_actions_by_theme(theme_id)
        return [a.model_dump() for a in actions]

    @app.get("/api/research/themes/{theme_id}/conversation")
    def get_conversation(theme_id: str):
        """Get conversation history for a theme."""
        messages = db.list_conversation_by_theme(theme_id)
        return [m.model_dump() for m in messages]

    @app.post("/api/research/themes/{theme_id}/conversation")
    def send_message(theme_id: str, request: ConversationRequest):
        """Send a message and get agent reply with optional proposed actions."""
        result = get_conversation_service().process_user_message(
            theme_id=theme_id,
            user_content=request.content,
        )

        return {
            "user_message": result.user_message.model_dump(),
            "agent_message": result.agent_message.model_dump(),
            "proposed_actions": [a.model_dump() for a in result.proposed_actions],
        }

    @app.post("/api/research/candidates/{candidate_id}/confirm")
    def confirm_candidate(candidate_id: str, request: ConfirmCandidateRequest):
        """Confirm a candidate (human confirmation only)."""
        try:
            confirmed = reducer.confirm_candidate(
                candidate_id=candidate_id,
                confirmation_reason=request.confirmation_reason,
                evidence_level=request.evidence_level,
                confirmed_by=request.confirmed_by,
                pool_snapshot_date=date.fromisoformat(request.pool_snapshot_date),
                thesis_snapshot=request.thesis_snapshot,
                invalidation_rules=request.invalidation_rules,
                price_snapshot=request.price_snapshot,
                benchmark_snapshot=request.benchmark_snapshot,
                approval_card_id=request.approval_card_id,
                override_reason=request.override_reason,
                evidence_snapshot_ids=request.evidence_snapshot_ids,
                primary_evidence_snapshot_id=request.primary_evidence_snapshot_id,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return {"confirmed_id": confirmed.confirmed_id, "status": "confirmed"}

    @app.post("/api/research/candidates/{candidate_id}/reject")
    def reject_candidate(candidate_id: str, actor: str = "user", reason: str = ""):
        """
        Reject a candidate.

        Updates candidate status to 'rejected'.
        Records actor, reason, and timestamp.
        Increments board_version.
        """
        candidate = db.get_candidate(candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        now = datetime.now()

        # Update candidate status
        cursor = db.conn.cursor()
        cursor.execute(
            "UPDATE research_candidates SET status = 'rejected' WHERE candidate_id = ?",
            (candidate_id,)
        )
        db.conn.commit()

        # Increment board_version
        db.increment_board_version(candidate.theme_id)

        # Return audit info
        return {
            "candidate_id": candidate_id,
            "status": "rejected",
            "rejected_by": actor,
            "reason": reason,
            "rejected_at": now.isoformat(),
        }

    @app.post("/api/research/themes/{theme_id}/reopen-to-serenity")
    def reopen_to_serenity(theme_id: str, request: ReopenRequest):
        """Reopen theme to Serenity with reason."""
        if not request.reason.strip():
            raise HTTPException(status_code=400, detail="Reason is required")

        now = datetime.now()
        result = db.reopen_theme_to_serenity(
            theme_id=theme_id,
            actor=request.actor,
            reason=request.reason,
            timestamp=now,
        )

        # Increment board_version
        db.increment_board_version(theme_id)

        return result

    @app.post("/api/research/candidates/{candidate_id}/reopen-to-evidence")
    def reopen_to_evidence(candidate_id: str, request: ReopenRequest):
        """Reopen candidate to Evidence with reason."""
        if not request.reason.strip():
            raise HTTPException(status_code=400, detail="Reason is required")

        candidate = db.get_candidate(candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        now = datetime.now()
        result = db.reopen_candidate_to_evidence(
            candidate_id=candidate_id,
            actor=request.actor,
            reason=request.reason,
            timestamp=now,
        )

        # Increment board_version
        db.increment_board_version(candidate.theme_id)

        return result

    @app.get("/api/research/themes/{theme_id}/confirmed-candidates")
    def list_confirmed_candidates(theme_id: str):
        """List confirmed candidates for a theme."""
        candidates = db.list_confirmed_candidates(theme_id)
        return [c.model_dump() for c in candidates]

    # Friend-stock flow endpoints
    class FriendStockIntakeRequest(BaseModel):
        raw_company_input: str
        raw_code_input: str | None = None
        source_note: str

    class ResolveAmbiguousRequest(BaseModel):
        chosen_ticker: str

    class CreateApprovalCardRequest(BaseModel):
        ticker: str

    class CreateConfirmedPoolRequest(BaseModel):
        ticker: str
        name: str
        exchange: str
        approval_card_id: str
        snapshot_date: str  # ISO date
        decision: str = "continue"  # V2: explicit, must be honored by caller

    # V2 (2026-07-10): ResearchCase (theme) keyed endpoints for the
    # credible manual-trading closure chain. These hang off the ResearchCase
    # that the workbench friend-recommendation handler already creates.
    class CreateHypothesisRequest(BaseModel):
        user_industry_chain_hypothesis: dict  # verbatim, pending-only

    class RunResearchRequest(BaseModel):
        ticker: str
        company_name: str
        decision_loop_id: str | None = None  # LLM budget attribution

    class CreateDecisionRequest(BaseModel):
        decision: str  # explicit: "continue" | "observe" | "stop"
        confirmed_by: str = "user"  # human approver; never default/LLM/stub
        decision_loop_id: str | None = None
        ticker: str
        company_name: str
        exchange: str
        snapshot_date: str  # ISO date
        approval_card_id: str | None = None

    @app.post("/api/research/friend-stock/intake")
    def friend_stock_intake(request: FriendStockIntakeRequest):
        """
        Intake friend-recommended stock.

        Returns ticker verification result.
        """
        from backend.services.friend_stock_flow import FriendStockFlowService
        import uuid

        flow_service = FriendStockFlowService(
            validator=validator,
            serenity_runner=None,  # Will be wired when needed
            market_data_provider=None,
        )

        result = flow_service.verify_ticker(
            raw_company_input=request.raw_company_input,
            raw_code_input=request.raw_code_input,
        )

        # Store flow state
        flow_id = result.flow_id
        db.store_friend_stock_flow(
            flow_id=flow_id,
            raw_company_input=request.raw_company_input,
            raw_code_input=request.raw_code_input,
            source_note=request.source_note,
            ticker_verification_result=result.model_dump(mode="json"),  # Serialize to dict
        )

        return result.model_dump()

    @app.post("/api/research/friend-stock/{flow_id}/resolve-ambiguous")
    def resolve_ambiguous_ticker(flow_id: str, request: ResolveAmbiguousRequest):
        """
        Resolve ambiguous ticker by user selection.
        """
        from backend.services.friend_stock_flow import (
            FriendStockFlowService,
            validate_serenity_research_output,
        )

        flow_service = FriendStockFlowService()

        # Fetch flow state from DB
        flow_state = db.get_friend_stock_flow(flow_id)
        if not flow_state:
            raise HTTPException(status_code=404, detail="Flow not found")

        verification_result = flow_state.get("ticker_verification_result")
        if not verification_result or verification_result.get("status") != "ambiguous":
            raise HTTPException(status_code=400, detail="Flow is not in ambiguous state")

        original_candidates = verification_result.get("candidates", [])

        try:
            result = flow_service.resolve_ambiguous_ticker(
                flow_id=flow_id,
                chosen_ticker=request.chosen_ticker,
                original_candidates=original_candidates,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Update flow state
        db.store_friend_stock_flow(
            flow_id=flow_id,
            raw_company_input=flow_state["raw_company_input"],
            raw_code_input=flow_state["raw_code_input"],
            source_note=flow_state["source_note"],
            ticker_verification_result=result.model_dump(mode="json"),  # Serialize to dict
        )

        return result.model_dump()

    @app.post("/api/research/friend-stock/{flow_id}/run-research")
    def run_friend_stock_research(flow_id: str, ticker: str, company_name: str):
        """
        Run industry research for friend-recommended stock.

        Returns research synthesis output.
        """
        from backend.services.friend_stock_flow import FriendStockFlowService

        # Fetch flow state from DB
        flow_state = db.get_friend_stock_flow(flow_id)
        if not flow_state:
            raise HTTPException(status_code=404, detail="Flow not found")

        # Wire real Serenity runner if in real mode
        if conversation_mode == "real" and hasattr(serenity_runner, 'run'):
            serenity = serenity_runner
        else:
            serenity = None

        flow_service = FriendStockFlowService(
            validator=validator,
            serenity_runner=serenity,
            market_data_provider=None,
        )

        try:
            research_output = flow_service.run_industry_research(
                ticker=ticker,
                company_name=company_name,
            )
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))

        # Update flow state with research output
        db.store_friend_stock_flow(
            flow_id=flow_id,
            raw_company_input=flow_state["raw_company_input"],
            raw_code_input=flow_state["raw_code_input"],
            source_note=flow_state["source_note"],
            ticker_verification_result=flow_state.get("ticker_verification_result"),
            research_output=research_output,
        )

        return research_output

    @app.post("/api/research/friend-stock/{flow_id}/create-pool")
    def create_friend_stock_pool(flow_id: str, request: CreateConfirmedPoolRequest):
        """
        Create confirmed candidate pool for friend-recommended stock.

        Returns confirmed pool record.
        """
        from backend.services.friend_stock_flow import FriendStockFlowService
        from datetime import date

        # Fetch flow state from DB
        flow_state = db.get_friend_stock_flow(flow_id)
        if not flow_state:
            raise HTTPException(status_code=404, detail="Flow not found")

        # Verify ticker was verified
        verification_result = flow_state.get("ticker_verification_result")
        if not verification_result:
            raise HTTPException(status_code=400, detail="Ticker not verified for this flow")

        if verification_result.get("status") != "verified":
            raise HTTPException(
                status_code=400,
                detail=f"Ticker verification status is '{verification_result.get('status')}', must be 'verified'"
            )

        # Verify request matches verification result
        if request.ticker != verification_result.get("resolved_ticker"):
            raise HTTPException(
                status_code=400,
                detail=f"Request ticker '{request.ticker}' does not match verified ticker '{verification_result.get('resolved_ticker')}'"
            )

        if request.exchange != verification_result.get("exchange"):
            raise HTTPException(
                status_code=400,
                detail=f"Request exchange '{request.exchange}' does not match verified exchange '{verification_result.get('exchange')}'"
            )

        # Use resolved_name from verification, not request.name (may be English alias)
        resolved_name = verification_result.get("resolved_name")

        research_output = flow_state.get("research_output")
        if not research_output:
            raise HTTPException(status_code=400, detail="Research not completed for this flow")

        # Check if market data provider available
        if market_data_provider is None:
            raise HTTPException(
                status_code=503,
                detail="Market data adapter unavailable. Cannot create pool without live price snapshot."
            )

        # Wire services
        if conversation_mode == "real" and hasattr(serenity_runner, 'run'):
            serenity = serenity_runner
        else:
            serenity = None

        flow_service = FriendStockFlowService(
            validator=validator,
            serenity_runner=serenity,
            market_data_provider=market_data_provider,
        )

        # Parse snapshot date
        snapshot_date = date.fromisoformat(request.snapshot_date)

        # V2 (2026-07-10): explicit decision — never silently approved.
        if (request.decision or "").strip() != "continue":
            raise HTTPException(
                status_code=400,
                detail="decision must be an explicit 'continue' to create a pool",
            )
        legacy_theme = db.get_theme(flow_id)

        # Create pool
        try:
            pool = flow_service.create_confirmed_pool(
                flow_id=flow_id,
                ticker=request.ticker,
                name=resolved_name,
                exchange=request.exchange,
                approval_card_id=request.approval_card_id,
                research_output=research_output,
                snapshot_date=snapshot_date,
                approval_decision=request.decision,
                confirmed_by="user",
                decision_loop_id=None,
                confirmed_at=datetime.now(),
                user_industry_chain_hypothesis=(
                    legacy_theme.user_industry_chain_hypothesis
                    if legacy_theme else None
                ),
            )
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))

        # Create or get candidate
        from contracts.research import CandidateStock, ThemeInput

        # Check if theme exists, create if not
        theme = db.get_theme(flow_id)
        if not theme:
            now = datetime.now()
            theme_input = ThemeInput(
                theme_id=flow_id,
                theme_name=f"Friend recommendation: {resolved_name}",
                background=f"Friend recommended {resolved_name} ({request.ticker})",
                source_type="manual_stock",
                research_mode="standard",
                urgency="normal",
                notes="",
                created_at=now,
                updated_at=now,
            )
            db.create_theme(theme_input)

        # Check if candidate exists, create if not
        candidate_id = f"cand_{pool.pool_id}"
        candidate = db.get_candidate(candidate_id)
        if not candidate:
            candidate = CandidateStock(
                candidate_id=candidate_id,
                theme_id=flow_id,
                symbol=pool.ticker,
                company_name=pool.name,
                verification_id=verification_result.get("flow_id", ""),
                source_type="manual_stock",
                chain_layer="",
                match_reason="Friend recommendation",
                match_confidence="high",
                status="raw",
                hard_filter_flags=[],
                created_at=pool.created_at,
            )
            db.add_candidate(candidate)

        evidence_output = dict(research_output)
        evidence_output.setdefault("blocking_issues", [])
        packet_data = json.dumps(evidence_output, sort_keys=True, ensure_ascii=False)
        snapshot_id = f"friend_research_{candidate_id}_{snapshot_date.isoformat()}"
        db.store_evidence_snapshot(
            snapshot_id=snapshot_id,
            candidate_id=candidate_id,
            verification_id=candidate.verification_id,
            snapshot_date=snapshot_date.isoformat(),
            symbol=candidate.symbol,
            evidence_output=evidence_output,
            packet_input_hash=hashlib.sha256(packet_data.encode("utf-8")).hexdigest(),
            packet_data=packet_data,
        )

        # All production confirmation paths pass through the same reducer guard.
        try:
            confirmed = reducer.confirm_candidate(
                candidate_id=candidate_id,
                confirmation_reason="Friend recommendation approved",
                evidence_level="medium",
                confirmed_by="user",
                pool_snapshot_date=pool.confirmation_date.date(),
                thesis_snapshot=pool.thesis_snapshot,
                invalidation_rules=pool.invalidation_rules,
                price_snapshot=pool.price_snapshot,
                benchmark_snapshot=pool.benchmark_snapshot,
                approval_card_id=request.approval_card_id,
                evidence_snapshot_ids=[snapshot_id],
                primary_evidence_snapshot_id=snapshot_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        # Return pool with confirmed_id
        response = pool.model_dump()
        response["confirmed_id"] = confirmed.confirmed_id
        return response

    # ========================================================================
    # V2 (2026-07-10): ResearchCase-keyed closure chain
    #   hypothesis (pending) -> real research -> explicit decision -> pool
    # ========================================================================
    @app.post("/api/research/themes/{theme_id}/hypothesis")
    def save_research_hypothesis(theme_id: str, request: CreateHypothesisRequest):
        """Persist user-proposed industry-chain hypothesis VERBATIM as pending-only."""
        theme = db.get_theme(theme_id)
        if not theme:
            raise HTTPException(status_code=404, detail="ResearchCase not found")
        if not isinstance(request.user_industry_chain_hypothesis, dict):
            raise HTTPException(status_code=400, detail="hypothesis must be an object")
        db.store_hypothesis(theme_id, request.user_industry_chain_hypothesis)
        return {"theme_id": theme_id, "status": "pending_hypothesis_saved"}

    @app.post("/api/research/themes/{theme_id}/run-research")
    def run_research_for_theme(theme_id: str, request: RunResearchRequest):
        """Run REAL Serenity+Tushare synthesis; persist traceable facts/counter/gaps."""
        from backend.services.friend_stock_flow import (
            FriendStockFlowService,
            validate_serenity_research_output,
        )
        from contracts.research import CandidateStock

        theme = db.get_theme(theme_id)
        if not theme:
            raise HTTPException(status_code=404, detail="ResearchCase not found")

        # Only a real runner may produce research; else research_unavailable.
        if not (conversation_mode == "real" and hasattr(serenity_runner, "run")):
            raise HTTPException(
                status_code=503,
                detail="research_unavailable: real Serenity runner not configured",
            )

        flow_service = FriendStockFlowService(
            validator=validator,
            serenity_runner=serenity_runner,
            market_data_provider=None,
        )
        try:
            research_output = flow_service.run_industry_research(
                ticker=request.ticker,
                company_name=request.company_name,
            )
            validate_serenity_research_output(
                serenity_runner,
                request.ticker,
                research_output,
                require_real_runner=not allow_test_serenity_runner,
            )
        except ValueError:
            # Insufficient facts / service fault -> research_unavailable, no candidate.
            raise HTTPException(
                status_code=503,
                detail="research_unavailable: serenity_execution_failed",
            ) from None

        # 零来源防御：无 traceable source → research_unavailable
        rationale = research_output.get("candidate_rationales", {}).get(request.ticker, {})
        tushare_ids = [
            sid for sid in rationale.get("supporting_source_ids", [])
            if isinstance(sid, str) and sid.startswith(("financials:", "announcements:"))
        ]
        if not tushare_ids:
            raise HTTPException(
                status_code=503,
                detail="research_unavailable: traceable_sources_unavailable",
            )

        # Persist synthesis on the ResearchCase (read-only source for approval card).
        db.store_research_output(theme_id, research_output)

        # Create candidate (idempotent) so evidence snapshots can attach.
        candidate_id = f"cand_{theme_id}"
        candidate = db.get_candidate(candidate_id)
        if not candidate:
            candidate = CandidateStock(
                candidate_id=candidate_id,
                theme_id=theme_id,
                symbol=request.ticker,
                company_name=request.company_name,
                verification_id=None,
                source_type="manual_stock",
                chain_layer="",
                match_reason="朋友推荐",
                match_confidence="high",
                status="raw",
                created_at=datetime.now(),
            )
            db.add_candidate(candidate)

        # Persist the synthesis as an immutable evidence snapshot so the
        # deterministic reducer can validate it at confirmation time.
        snapshot_id = f"snap_{theme_id}_{uuid.uuid4().hex[:8]}"
        evidence_output = dict(research_output)
        evidence_output.setdefault("blocking_issues", [])
        packet_data = json.dumps(evidence_output, sort_keys=True, ensure_ascii=False)
        packet_hash = hashlib.sha256(packet_data.encode("utf-8")).hexdigest()
        db.store_evidence_snapshot(
            snapshot_id=snapshot_id,
            candidate_id=candidate_id,
            verification_id=None,
            snapshot_date=date.today().isoformat(),
            symbol=request.ticker,
            evidence_output=evidence_output,
            packet_input_hash=packet_hash,
            tool_result_hash="",
            packet_data=packet_data,
            audit_id=None,
        )
        return research_output

    @app.post("/api/research/themes/{theme_id}/decision")
    def apply_research_decision(theme_id: str, request: CreateDecisionRequest):
        """Require an EXPLICIT user decision; gate pool creation on 'continue'.

        Default / LLM-text / stub / data-error / LLM-error never count as
        approval. Only a real 'continue' (a human click) builds the
        forward-only confirmed candidate pool, via the deterministic reducer.
        """
        from backend.services.friend_stock_flow import FriendStockFlowService
        from contracts.research import CandidateStock
        from backend.services.research_action_reducer import ResearchActionReducer

        theme = db.get_theme(theme_id)
        if not theme:
            raise HTTPException(status_code=404, detail="ResearchCase not found")

        decision = (request.decision or "").strip()
        if decision not in ("continue", "observe", "stop"):
            raise HTTPException(
                status_code=400,
                detail="decision must be an explicit 'continue' / 'observe' / 'stop'",
            )
        if decision == "continue" and not (request.approval_card_id or "").strip():
            raise HTTPException(status_code=400, detail="approval_provenance_required")

        # Persist the explicit decision + approver (audit).
        db.record_decision(theme_id, decision, request.confirmed_by, request.decision_loop_id)

        if decision != "continue":
            # observe/stop: record only, never create a candidate pool.
            return {
                "pool_created": False,
                "status": decision,
                "message": f"已记录：{decision}（仅 continue 创建前向候选池）",
            }

        # --- continue: build the forward-only confirmed candidate pool ---
        if not (conversation_mode == "real" and hasattr(serenity_runner, "run")):
            raise HTTPException(
                status_code=503,
                detail="research_unavailable: real Serenity runner not configured",
            )
        if market_data_provider is None:
            raise HTTPException(
                status_code=503,
                detail="Market data adapter unavailable. Cannot create pool without live price snapshot.",
            )

        research_output = theme.research_output
        if not research_output:
            raise HTTPException(
                status_code=503,
                detail="research_unavailable: no research synthesis for this case",
            )
        
        # 零来源防御：历史 case 也必须有 traceable source
        rationale = research_output.get("candidate_rationales", {}).get(request.ticker, {})
        tushare_ids = [
            sid for sid in rationale.get("supporting_source_ids", [])
            if isinstance(sid, str) and sid.startswith(("financials:", "announcements:"))
        ]
        if not tushare_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot continue: zero traceable sources. Only user hypothesis and gaps present."
            )

        flow_service = FriendStockFlowService(
            validator=validator,
            serenity_runner=serenity_runner,
            market_data_provider=market_data_provider,
        )
        snapshot_date = date.fromisoformat(request.snapshot_date)
        try:
            pool = flow_service.create_confirmed_pool(
                flow_id=theme_id,
                ticker=request.ticker,
                name=request.company_name,
                exchange=request.exchange,
                approval_card_id=request.approval_card_id,
                research_output=research_output,
                snapshot_date=snapshot_date,
                approval_decision="continue",  # explicit, gated above
                confirmed_by=request.confirmed_by,
                decision_loop_id=request.decision_loop_id,
                confirmed_at=datetime.now(),
                user_industry_chain_hypothesis=theme.user_industry_chain_hypothesis,
            )
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))

        # Create/confirm candidate via the DETERMINISTIC reducer (V2 Req 5).
        candidate_id = f"cand_{theme_id}"
        candidate = db.get_candidate(candidate_id)
        if not candidate:
            candidate = CandidateStock(
                candidate_id=candidate_id,
                theme_id=theme_id,
                symbol=pool.ticker,
                company_name=pool.name,
                verification_id=None,
                source_type="manual_stock",
                chain_layer="",
                match_reason="朋友推荐",
                match_confidence="high",
                status="raw",
                created_at=pool.created_at,
            )
            db.add_candidate(candidate)

        snapshots = db.get_evidence_snapshots_for_candidate(candidate_id)
        snapshot_ids = [s["snapshot_id"] for s in snapshots]
        if not snapshot_ids:
            raise HTTPException(
                status_code=503,
                detail="research_unavailable: no evidence snapshot to confirm candidate",
            )

        reducer = ResearchActionReducer(db, validator)
        try:
            confirmed = reducer.confirm_candidate(
                candidate_id=candidate_id,
                confirmation_reason="用户显式确认（continue）",
                evidence_level="medium",
                confirmed_by=request.confirmed_by,
                pool_snapshot_date=snapshot_date,
                thesis_snapshot=pool.thesis_snapshot,
                invalidation_rules=pool.invalidation_rules,
                price_snapshot=pool.price_snapshot,
                benchmark_snapshot=pool.benchmark_snapshot,
                approval_card_id=request.approval_card_id,
                evidence_snapshot_ids=snapshot_ids,
                primary_evidence_snapshot_id=snapshot_ids[0],
            )
        except ValueError as e:
            raise HTTPException(status_code=503, detail=f"confirmation blocked: {e}")

        response = pool.model_dump()
        response["confirmed_id"] = confirmed.confirmed_id
        response["forward_only"] = True
        response["is_buy_signal"] = False
        response["is_backtest_universe"] = False
        response["decision_loop_id"] = request.decision_loop_id
        response["confirmed_by"] = request.confirmed_by
        return response

    # ========================================================================
    # Task 13: Unified Agent Workbench API
    # ========================================================================

    # Import agent_workbench DB functions
    from backend.db.agent_workbench import (
        init_agent_workbench_db,
        create_session,
        get_session,
        update_session_state,
        append_message,
        attach_artifact_ref,
        update_approval_card,
        list_approval_cards,
        get_session_timeline,
    )
    from contracts.agent_workbench import (
        AgentSession,
        AgentMessage,
        ArtifactRef,
        WorkflowKind,
        WorkflowState,
    )
    from backend.services.approval_card_reducer import (
        apply_decision,
    )

    # Initialize agent_workbench schema on app.state.db connection
    init_agent_workbench_db(db.conn)

    # Initialize live_trade tables on same connection
    # Note: LiveTradeDB uses separate file, but for workbench integration we init schema here
    cursor = db.conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS execution_observation_logs (
            log_id TEXT PRIMARY KEY,
            draft_id TEXT,
            execution_card_id TEXT NOT NULL,
            signal_id TEXT NOT NULL,
            action_plan_id TEXT NOT NULL,
            capital_context_id TEXT NOT NULL,
            market_snapshot_id TEXT NOT NULL,
            confirmed_action TEXT NOT NULL,
            confirmed_execution_status TEXT NOT NULL,
            confirmed_price REAL,
            confirmed_quantity INTEGER,
            reason TEXT,
            confirmed_by_user INTEGER NOT NULL,
            broker_verified INTEGER NOT NULL CHECK(broker_verified = 0),
            confirmed_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS observation_positions (
            position_id TEXT PRIMARY KEY,
            source_log_id TEXT NOT NULL,
            execution_card_id TEXT,
            signal_id TEXT,
            action_plan_id TEXT,
            capital_context_id TEXT,
            symbol TEXT NOT NULL,
            name TEXT NOT NULL,
            entry_price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            template_id TEXT,
            template_version TEXT,
            entry_thesis TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            FOREIGN KEY (source_log_id) REFERENCES execution_observation_logs(log_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pnl_records (
            pnl_record_id TEXT PRIMARY KEY,
            position_id TEXT NOT NULL,
            buy_price REAL,
            sell_price REAL,
            quantity INTEGER,
            fees REAL,
            pnl_amount REAL NOT NULL,
            pnl_pct REAL,
            pnl_source TEXT NOT NULL,
            missing_fields TEXT NOT NULL,
            computed_at TEXT NOT NULL,
            FOREIGN KEY (position_id) REFERENCES observation_positions(position_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_observation_signals (
            signal_record_id TEXT PRIMARY KEY,
            position_id TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            triggered_invalidations TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            market_data_state TEXT NOT NULL,
            rule_trace TEXT NOT NULL,
            plain_explanation TEXT,
            explanation_source TEXT NOT NULL,
            FOREIGN KEY (position_id) REFERENCES observation_positions(position_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS discipline_reviews (
            review_id TEXT PRIMARY KEY,
            position_id TEXT NOT NULL,
            execution_card_id TEXT NOT NULL,
            signal_id TEXT NOT NULL,
            review_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    db.conn.commit()

    class WorkbenchMessageRequest(BaseModel):
        model_config = ConfigDict(extra="forbid")

        conversation_id: str | None = None
        message: str
        context: dict | None = None

    class ApprovalDecisionRequest(BaseModel):
        decision: str
        decided_by: str

    @app.post("/api/agent/workbench/message")
    def workbench_message(request: WorkbenchMessageRequest):
        """
        Unified agent workbench endpoint.

        Single-source route decision architecture:
        - route_decision = router.route(...) is the ONLY裁决源
        - match route_decision.workflow_kind dispatches to dedicated handlers
        - response.workflow_type MUST == route_decision.workflow_kind (no override)
        - Handlers do NOT read session.workflow_kind for business logic

        Task 13: Deterministic routing without LLM dependency.
        Persists to agent_workbench DB.
        """
        import uuid
        import re
        # Import handlers
        from backend.api.workbench_handlers import (
            HandlerResult,
            handle_market_scan,
            handle_friend_stock,
            handle_strategy_idea,
            handle_position_followup,
            handle_theme_research_deferred,
            handle_clarification,
            handle_add_to_observation,
        )

        now = datetime.now()

        # Get or create session
        conversation_id = request.conversation_id
        session_exists = False

        if conversation_id:
            try:
                session = get_session(db.conn, conversation_id)
                session_exists = True
            except ValueError:
                session_exists = False

        if not session_exists:
            # Create new session
            conversation_id = f"sess_{uuid.uuid4().hex[:12]}"

            # Task 20A: Hybrid Agent Intent Routing Pipeline
            # Step 1: Deterministic PreScan (fast local patterns)
            from backend.services.workbench_prescan import prescan_message
            from backend.services.workbench_intent_extractor import LLMIntentExtractor
            from backend.services.stock_identity_resolver import StockIdentityResolver
            from backend.services.workbench_workflow_router import WorkbenchWorkflowRouter

            prescan = prescan_message(request.message)

            # Step 2: LLM Intent Extraction (semantic understanding)
            intent_extractor = LLMIntentExtractor(
                llm_client=None,  # Will use deterministic mode for now
                mode="deterministic"
            )
            intent_extraction = intent_extractor.extract_intent(request.message, prescan)

            # Step 3: Stock Identity Resolution (Tushare verification)
            # Use real Tushare client if available (conversation_mode="real")
            # Or use injected test fixture (deterministic mode)
            if stock_resolver_override is not None:
                # Test injection path
                stock_resolver = stock_resolver_override
            else:
                # Normal path
                stock_resolver = StockIdentityResolver(
                    tushare_client=validator.tushare_client if conversation_mode == "real" else None,
                    test_fixture=stock_resolver_fixture if conversation_mode == "deterministic" else None,
                )

            stock_identity = stock_resolver.resolve(
                company_name=intent_extraction.extracted_company_name,
                stock_code=intent_extraction.extracted_stock_code,
            )

            # Step 4: Deterministic Workflow Router (final decision)
            router = WorkbenchWorkflowRouter()
            # New session has no open positions
            route_decision = router.route(prescan, intent_extraction, stock_identity, open_positions=[])

            # Session title based on route decision
            if route_decision.workflow_kind == "friend_stock" and stock_identity.status == "verified":
                session_title = f"{stock_identity.company_name}股票调查"
            elif route_decision.workflow_kind == "strategy_idea":
                session_title = "策略想法验证"
            elif route_decision.workflow_kind == "execution_feedback":
                session_title = "执行反馈"
            elif route_decision.workflow_kind == "position_followup":
                session_title = "持仓跟进"
            elif route_decision.workflow_kind == "theme_research":
                session_title = "主题研究"
            else:
                session_title = "对话"

            # Map route_decision.workflow_state to WorkflowState enum
            workflow_state_map = {
                "created": WorkflowState.CREATED,
                "waiting_for_clarification": WorkflowState.CREATED,
                "stopped": WorkflowState.STOPPED,
            }
            workflow_state = workflow_state_map.get(route_decision.workflow_state, WorkflowState.CREATED)

            # Store route_decision.workflow_kind in session for DB persistence ONLY
            # Business logic MUST use route_decision.workflow_kind, NOT session.workflow_kind
            # Map to WorkflowKind enum for DB type safety
            workflow_kind_for_db_map = {
                "friend_stock": WorkflowKind.FRIEND_STOCK,
                "strategy_idea": WorkflowKind.STRATEGY_IDEA,
                "execution_feedback": WorkflowKind.FRIEND_STOCK,  # DB doesn't have EXECUTION_FEEDBACK enum yet
                "position_followup": WorkflowKind.FRIEND_STOCK,  # DB doesn't have POSITION_FOLLOWUP enum yet
                "theme_research": WorkflowKind.FRIEND_STOCK,  # DB doesn't have THEME_RESEARCH enum yet
                "market_scan": WorkflowKind.UNKNOWN,
                "unknown": WorkflowKind.UNKNOWN,
                "clarification": WorkflowKind.UNKNOWN,
            }
            workflow_kind_for_db = workflow_kind_for_db_map.get(route_decision.workflow_kind, WorkflowKind.UNKNOWN)

            session = AgentSession(
                session_id=conversation_id,
                workflow_kind=workflow_kind_for_db,
                workflow_state=workflow_state,
                title=session_title,
                created_at=now,
                updated_at=now,
            )
            create_session(db.conn, session)

            # Initialize claimed_stock for new session
            claimed_stock = None
            open_positions = []

            # Task 20A: Record pipeline activity artifacts
            # Artifact 0: Context loaded (new session, no prior context)
            context_loaded_artifact = ArtifactRef(
                artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                session_id=conversation_id,
                artifact_id=f"context_loaded_{conversation_id}",
                artifact_type="context_loaded",
                created_at=now,
            )
            attach_artifact_ref(db.conn, context_loaded_artifact)

            # Artifact 1: PreScan result
            prescan_artifact = ArtifactRef(
                artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                session_id=conversation_id,
                artifact_id=f"prescan_{conversation_id}",
                artifact_type="prescan_result",
                created_at=now,
            )
            attach_artifact_ref(db.conn, prescan_artifact)

            # Artifact 2: Intent extraction
            intent_artifact = ArtifactRef(
                artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                session_id=conversation_id,
                artifact_id=f"intent_{conversation_id}",
                artifact_type="intent_extraction",
                created_at=now,
            )
            attach_artifact_ref(db.conn, intent_artifact)

            # Artifact 3: Stock identity resolution (if applicable)
            if stock_identity.status != "not_applicable":
                stock_identity_artifact = ArtifactRef(
                    artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                    session_id=conversation_id,
                    artifact_id=f"stock_identity_{conversation_id}",
                    artifact_type="stock_identity_resolution",
                    created_at=now,
                )
                attach_artifact_ref(db.conn, stock_identity_artifact)

            # Artifact 4: Workflow route decision
            route_artifact = ArtifactRef(
                artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                session_id=conversation_id,
                artifact_id=f"route_{conversation_id}",
                artifact_type="workflow_route_decision",
                created_at=now,
            )
            route_decision_content = json.dumps({
                "workflow_kind": route_decision.workflow_kind,
                "workflow_state": route_decision.workflow_state,
                "route_reason": route_decision.route_reason,
                "next_required_user_action": route_decision.next_required_user_action,
                "allowed_to_start_workflow": route_decision.allowed_to_start_workflow,
            })
            attach_artifact_ref(db.conn, route_artifact, content=route_decision_content)
        else:
            # Existing session - load session context and run pipeline
            session = get_session(db.conn, conversation_id)

            # Load session context
            recent_messages = list_messages(db.conn, conversation_id)[-10:]  # Last 10 messages
            recent_artifacts = list_artifact_refs(db.conn, conversation_id)

            # Extract claimed entities from session state
            claimed_stock = None
            claimed_strategy = None
            open_positions = []

            # Look for verified stock in recent artifacts
            for artifact in recent_artifacts:
                if artifact.artifact_type == "friend_stock_flow":
                    flow = db.get_friend_stock_flow(artifact.artifact_id)
                    if flow and flow.get("raw_code_input"):
                        claimed_stock = {
                            "ticker": flow.get("raw_code_input"),
                            "company_name": flow.get("raw_company_input"),
                            "original_context": flow.get("source_note", ""),  # Preserve original user message
                        }

            cursor = db.conn.cursor()
            cursor.execute(
                """
                SELECT position_id, symbol, name
                FROM observation_positions
                WHERE lifecycle_state = 'open'
                ORDER BY opened_at DESC
                """
            )
            open_positions = [
                {"position_id": row[0], "symbol": row[1], "name": row[2]}
                for row in cursor.fetchall()
            ]

            # Record context_loaded activity
            context_loaded_artifact = ArtifactRef(
                artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                session_id=conversation_id,
                artifact_id=f"context_loaded_{uuid.uuid4().hex[:8]}",
                artifact_type="context_loaded",
                created_at=now,
            )
            attach_artifact_ref(db.conn, context_loaded_artifact)

            # Run pipeline again for existing session
            from backend.services.workbench_prescan import prescan_message
            from backend.services.workbench_intent_extractor import LLMIntentExtractor
            from backend.services.stock_identity_resolver import StockIdentityResolver
            from backend.services.workbench_workflow_router import WorkbenchWorkflowRouter

            prescan = prescan_message(request.message)

            intent_extractor = LLMIntentExtractor(
                llm_client=None,
                mode="deterministic"
            )
            intent_extraction = intent_extractor.extract_intent(request.message, prescan)
            if (
                claimed_stock
                and not intent_extraction.extracted_company_name
                and not intent_extraction.extracted_stock_code
                and intent_extraction.primary_intent in ["unknown", "stock_research"]
            ):
                intent_extraction.extracted_stock_code = claimed_stock["ticker"]
                intent_extraction.extracted_company_name = claimed_stock.get("company_name")

            # Use real Tushare client or injected test fixture
            if stock_resolver_override is not None:
                # Test injection path
                stock_resolver = stock_resolver_override
            else:
                # Normal path
                stock_resolver = StockIdentityResolver(
                    tushare_client=validator.tushare_client if conversation_mode == "real" else None,
                    test_fixture=stock_resolver_fixture if conversation_mode == "deterministic" else None,
                )

            stock_identity = stock_resolver.resolve(
                company_name=intent_extraction.extracted_company_name,
                stock_code=intent_extraction.extracted_stock_code,
            )

            router = WorkbenchWorkflowRouter()
            route_decision = router.route(prescan, intent_extraction, stock_identity, open_positions=open_positions)

            # Record activity artifacts for existing session
            # Artifact 1: PreScan result
            prescan_artifact = ArtifactRef(
                artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                session_id=conversation_id,
                artifact_id=f"prescan_{uuid.uuid4().hex[:8]}",
                artifact_type="prescan_result",
                created_at=now,
            )
            attach_artifact_ref(db.conn, prescan_artifact)

            # Artifact 2: Intent extraction
            intent_artifact = ArtifactRef(
                artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                session_id=conversation_id,
                artifact_id=f"intent_{uuid.uuid4().hex[:8]}",
                artifact_type="intent_extraction",
                created_at=now,
            )
            attach_artifact_ref(db.conn, intent_artifact)

            # Artifact 3: Stock identity resolution (if applicable)
            if stock_identity.status != "not_applicable":
                stock_identity_artifact = ArtifactRef(
                    artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                    session_id=conversation_id,
                    artifact_id=f"stock_identity_{uuid.uuid4().hex[:8]}",
                    artifact_type="stock_identity_resolution",
                    created_at=now,
                )
                attach_artifact_ref(db.conn, stock_identity_artifact)

            # Artifact 4: Workflow route decision
            route_artifact = ArtifactRef(
                artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                session_id=conversation_id,
                artifact_id=f"route_{uuid.uuid4().hex[:8]}",
                artifact_type="workflow_route_decision",
                created_at=now,
            )
            route_decision_content = json.dumps({
                "workflow_kind": route_decision.workflow_kind,
                "workflow_state": route_decision.workflow_state,
                "route_reason": route_decision.route_reason,
                "next_required_user_action": route_decision.next_required_user_action,
                "allowed_to_start_workflow": route_decision.allowed_to_start_workflow,
            })
            attach_artifact_ref(db.conn, route_artifact, content=route_decision_content)

        # Store user message
        user_message_id = f"msg_{uuid.uuid4().hex[:12]}"
        user_message = AgentMessage(
            message_id=user_message_id,
            session_id=conversation_id,
            role="user",
            content=request.message,
            created_at=now,
        )
        append_message(db.conn, user_message)

        # Single-source route decision dispatch to handlers
        # CRITICAL: response.workflow_type MUST == route_decision.workflow_kind (no override)
        # Both new and existing sessions use the same handler dispatch logic
        workflow_kind = route_decision.workflow_kind

        # Dispatch to handler based on route_decision.workflow_kind (ONLY裁决源)
        if workflow_kind == "friend_stock":
            handler_result = handle_friend_stock(
                db.conn,
                conversation_id,
                request.message,
                stock_identity,
                route_decision,
                now,
                validator,
                serenity_runner,
                market_data_provider,
                research_db=db,  # V2 Task 2: pass ResearchDB instance
            )
        elif workflow_kind == "strategy_idea":
            handler_result = handle_strategy_idea(
                db.conn,
                conversation_id,
                request.message,
                route_decision,
                now,
                strategy_flow_service=strategy_flow_service_override,
            )
        elif workflow_kind == "market_scan":
            handler_result = handle_market_scan(
                db.conn,
                conversation_id,
                request.message,
                route_decision,
                now,
                research_db=db,
                validator=validator,
                serenity_runner=serenity_runner,
                evidence_runner=evidence_runner,
                lane_runner=market_scan_lane_runner,
            )
        elif workflow_kind == "execution_feedback":
            handler_result = HandlerResult(
                agent_reply="暂不支持，请在页面记录已经成交的交易。此处只解释，不会下单或登记交易。",
                artifact_ids=[],
                next_required_user_action="record_trade_in_page",
            )
        elif workflow_kind == "position_followup":
            handler_result = handle_position_followup(
                db.conn,
                conversation_id,
                request.message,
                stock_identity,
                route_decision,
                now,
                open_positions,
            )
        elif workflow_kind == "add_to_observation":
            handler_result = handle_add_to_observation(
                db.conn,
                conversation_id,
                request.message,
                claimed_stock,
                route_decision,
                now,
            )
        elif workflow_kind == "theme_research":
            handler_result = handle_theme_research_deferred(
                db.conn,
                conversation_id,
                request.message,
                route_decision,
                now,
            )
        else:  # unknown, clarification, or any other
            handler_result = handle_clarification(
                db.conn,
                conversation_id,
                request.message,
                route_decision,
                now,
            )

        agent_reply = handler_result.agent_reply
        artifact_ids = handler_result.artifact_ids
        next_required_user_action = handler_result.next_required_user_action or route_decision.next_required_user_action

        # CRITICAL: workflow_type MUST == route_decision.workflow_kind (no session.workflow_kind override)
        workflow_type = workflow_kind
        workflow_state_map = {
            "created": WorkflowState.CREATED,
            "waiting_for_clarification": WorkflowState.CREATED,
            "stopped": WorkflowState.STOPPED,
            "waiting_for_approval": WorkflowState.WAITING_FOR_APPROVAL,
            "observing": WorkflowState.OBSERVING,
            "completed": WorkflowState.COMPLETED,
        }
        workflow_state = workflow_state_map.get(
            handler_result.workflow_state or route_decision.workflow_state,
            WorkflowState.CREATED,
        )
        stage = session.workflow_state.value
        approval_card = handler_result.approval_card
        # Store agent message
        agent_message_id = f"msg_{uuid.uuid4().hex[:12]}"
        agent_message = AgentMessage(
            message_id=agent_message_id,
            session_id=conversation_id,
            role="agent",
            content=agent_reply,
            created_at=now,
        )
        append_message(db.conn, agent_message)

        # Create artifact refs for this exchange
        user_msg_artifact = ArtifactRef(
            artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
            session_id=conversation_id,
            artifact_id=user_message_id,
            artifact_type="user_message",
            created_at=now,
        )
        attach_artifact_ref(db.conn, user_msg_artifact)
        artifact_ids.append(user_message_id)

        agent_msg_artifact = ArtifactRef(
            artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
            session_id=conversation_id,
            artifact_id=agent_message_id,
            artifact_type="agent_message",
            created_at=now,
        )
        attach_artifact_ref(db.conn, agent_msg_artifact)
        artifact_ids.append(agent_message_id)

        # Create workflow intent artifact
        workflow_intent_id = f"intent_{conversation_id}"
        intent_artifact = ArtifactRef(
            artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
            session_id=conversation_id,
            artifact_id=workflow_intent_id,
            artifact_type="workflow_intent",
            created_at=now,
        )
        attach_artifact_ref(db.conn, intent_artifact)
        artifact_ids.append(workflow_intent_id)

        # Task 21: Update session workflow_state if changed during orchestration
        if session.workflow_state != workflow_state:
            update_session_state(db.conn, conversation_id, workflow_state)
            stage = workflow_state.value

        return {
            "conversation_id": conversation_id,
            "workflow_type": workflow_type,
            "stage": stage,
            "agent_reply": agent_reply,
            "approval_card": approval_card.model_dump() if approval_card else None,
            "artifact_ids": artifact_ids,
            "next_required_user_action": next_required_user_action,
        }

    @app.get("/api/agent/workbench/{conversation_id}")
    def get_workbench_session(conversation_id: str):
        """
        Get agent workbench session with timeline.

        Returns:
        - session metadata
        - timeline (messages, artifact_refs, approval_cards in insertion order)
        """
        try:
            session = get_session(db.conn, conversation_id)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Session not found: {conversation_id}")

        timeline = get_session_timeline(db.conn, conversation_id)

        return {
            "session": session.model_dump(),
            "timeline": timeline,
        }

    @app.post("/api/agent/workbench/{conversation_id}/approval-cards/{card_id}/decide")
    def decide_approval_card(conversation_id: str, card_id: str, request: ApprovalDecisionRequest):
        """
        Apply user decision to approval card.

        Uses approval_card_reducer for deterministic validation.
        """
        from datetime import datetime

        # Verify session exists
        try:
            session = get_session(db.conn, conversation_id)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Session not found: {conversation_id}")

        # Get all approval cards for this session
        cards = list_approval_cards(db.conn, conversation_id)

        # Find the card
        card = None
        for c in cards:
            if c.approval_card_id == card_id:
                card = c
                break

        if not card:
            raise HTTPException(status_code=404, detail=f"Approval card not found: {card_id}")

        # Check if already decided
        if card.decision is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Approval card already decided: {card.decision} by {card.decided_by}"
            )

        # Apply decision using reducer
        try:
            decided_card = apply_decision(
                card=card,
                decision=request.decision,
                decided_by=request.decided_by,
                decided_at=datetime.now(),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        update_approval_card(db.conn, decided_card)

        return {
            "approval_card_id": decided_card.approval_card_id,
            "decision": decided_card.decision,
            "decided_by": decided_card.decided_by,
            "decided_at": decided_card.decided_at.isoformat() if decided_card.decided_at else None,
        }


    @app.post("/api/agent/workbench/{conversation_id}/execution-card")
    def create_execution_card(conversation_id: str):
        """
        Create execution card from qualified artifact.

        Red line: Must have confirmed_candidate or prototype_passed artifact.
        Cannot fabricate execution card without qualified source.
        """
        # Check if conversation has qualified artifact
        # For now, return 404 to indicate not yet implemented with proper checks
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail="No qualified artifact (confirmed_candidate or prototype_passed) found for this conversation"
        )

    manual_security_cache: dict[str, tuple[float, dict]] = {}
    app.state.manual_security_cache = manual_security_cache

    def _canonical_manual_symbol(code: str) -> str:
        """Keep one stable Tushare-style key for each entered six-digit code."""
        suffix = {
            "0": "SZ", "1": "SZ", "2": "SZ", "3": "SZ",
            "4": "BJ", "5": "SH", "6": "SH", "8": "BJ", "9": "BJ",
        }.get(code[0]) if len(code) == 6 and code.isdigit() else None
        return f"{code}.{suffix}" if suffix else code

    def _resolve_manual_security(code: str) -> dict:
        import time

        canonical_symbol = _canonical_manual_symbol(code)
        cached = manual_security_cache.get(code)
        if cached and cached[0] > time.monotonic():
            return dict(cached[1])

        result = {
            "status": "unknown",
            "symbol": canonical_symbol,
            "name": None,
            "security_type": "unknown",
            "quantity_unit": "unknown",
            "data_source": "identity_not_found",
        }

        if conversation_mode == "deterministic":
            for key, identity in (stock_resolver_fixture or {}).items():
                ticker = str(identity.get("ticker") or key)
                if ticker.split(".", 1)[0] != code:
                    continue
                result.update({
                    "status": "verified",
                    "symbol": ticker,
                    "name": identity.get("company_name") or identity.get("name"),
                    "security_type": identity.get("security_type", "stock"),
                    "quantity_unit": identity.get("quantity_unit", "share"),
                    "data_source": "deterministic_fixture",
                })
                break
        else:
            lookup_failed = False
            try:
                tushare_client = validator.tushare_client
                fund_rows = tushare_client.query(
                    "fund_basic",
                    ts_code=canonical_symbol,
                    market="E",
                    fields="ts_code,name,market",
                )
                if fund_rows is not None and not fund_rows.empty:
                    fund = next(
                        (row for _, row in fund_rows.iterrows()
                         if str(row.get("ts_code", "")) == canonical_symbol),
                        None,
                    )
                    if fund is not None:
                        result.update({
                            "status": "verified",
                            "name": str(fund["name"]),
                            "security_type": "fund",
                            "quantity_unit": "fund_share",
                            "data_source": "tushare_fund_basic",
                            "retrieved_at": datetime.now().astimezone().isoformat(),
                        })
                        manual_security_cache[code] = (time.monotonic() + 900, dict(result))
                        return result
            except Exception:
                lookup_failed = True

            try:
                from backend.services.stock_identity_resolver import StockIdentityResolver

                stock = StockIdentityResolver(tushare_client=validator.tushare_client).resolve(
                    company_name=None,
                    stock_code=canonical_symbol,
                )
                if stock.status == "verified" and stock.ticker:
                    result.update({
                        "status": "verified",
                        "symbol": stock.ticker,
                        "name": stock.company_name,
                        "security_type": "stock",
                        "quantity_unit": "share",
                        "data_source": stock.data_source,
                        "retrieved_at": datetime.now().astimezone().isoformat(),
                    })
                elif stock.status == "data_fault" or lookup_failed:
                    result.update({"status": "unavailable", "data_source": "identity_lookup_error"})
            except Exception:
                result.update({"status": "unavailable", "data_source": "identity_lookup_error"})

        if result.get("status") == "verified" and not result.get("retrieved_at"):
            result["retrieved_at"] = datetime.now().astimezone().isoformat()
        manual_security_cache[code] = (time.monotonic() + 900, dict(result))
        return result

    @app.get("/api/agent/workbench/security-identity/{code}")
    def get_manual_security_identity(code: str):
        if not re.fullmatch(r"\d{6}", code):
            raise HTTPException(status_code=422, detail="请输入六位证券代码。")
        return _resolve_manual_security(code)

    @app.post("/api/research/single-security")
    def research_single_security(request: SingleSecurityResearchRequest):
        """Run one non-persisted, source-bound stock or ETF research request."""
        if conversation_mode != "real":
            raise HTTPException(status_code=503, detail="真实研究服务当前不可用。")

        identity = _resolve_manual_security(request.code)
        if identity.get("status") != "verified":
            raise HTTPException(
                status_code=503,
                detail="证券身份未能由真实来源核验，未生成研究结论。",
            )

        from backend.services.data_tools import DataToolsService, _etf_gap_categories
        from backend.services.serenity_agent import SerenityAgentRunner
        from contracts.research import ResearchSource

        if not isinstance(serenity_runner, SerenityAgentRunner) or serenity_runner.mode != "real":
            raise HTTPException(status_code=503, detail="真实研究服务当前不可用。")

        symbol = identity["symbol"]
        security_type = identity["security_type"]
        name = identity.get("name") or "名称未获取"
        data_tools = DataToolsService(tushare_client=validator.tushare_client)
        etf_bundle = (
            data_tools.get_etf_research_bundle(symbol)
            if security_type == "fund" else None
        )
        is_verified_etf = bool(etf_bundle and etf_bundle.get("is_etf"))
        quote_result = None if is_verified_etf else data_tools.get_security_quote_snapshot(
            symbol, security_type,
        )

        identity_source_id = f"security_identity:{symbol}:0"
        identity_retrieved_at = identity.get("retrieved_at")
        try:
            identity_retrieved = datetime.fromisoformat(identity_retrieved_at)
        except (TypeError, ValueError):
            identity_retrieved = datetime.now().astimezone()
        identity_source = ResearchSource(
            source_record_id=identity_source_id,
            source_type="unknown",
            source_quality="first_hand",
            title=f"证券身份核验：{name}",
            summary=f"由 {identity.get('data_source', 'unknown')} 核验；证券类型为 {'基金' if security_type == 'fund' else '股票'}。",
            retrieved_at=identity_retrieved,
        )
        sources_by_id = {identity_source_id: identity_source}
        facts = []
        if quote_result and quote_result.raw_data:
            quote = quote_result.raw_data[0]
            endpoint = quote_result.source.removeprefix("tushare_")
            facts.append({
                "label": "最近收盘价",
                "value": quote["close"],
                "unit": "元/份" if security_type == "fund" else "元/股",
                "symbol": symbol,
                "source": "Tushare-compatible",
                "endpoint": endpoint,
                "date": quote["trade_date"],
                "retrieved_at": quote_result.retrieved_at.isoformat(),
            })
            quote_source_id = f"{endpoint}:{symbol}:0"
            quote_date = date.fromisoformat(quote["trade_date"])
            sources_by_id[quote_source_id] = ResearchSource(
                source_record_id=quote_source_id,
                source_type="unknown",
                source_quality="first_hand",
                title=f"{name}最近收盘行情",
                published_at=quote_date,
                summary=f"交易日 {quote['trade_date']} 收盘 {quote['close']} {facts[0]['unit']}。",
                retrieved_at=quote_result.retrieved_at,
            )
        if is_verified_etf:
            bundle_retrieved_at = datetime.fromisoformat(etf_bundle["retrieved_at"])
            for source in etf_bundle.get("sources", []):
                if not isinstance(source, dict):
                    continue
                source_id = source.get("source_record_id")
                if not isinstance(source_id, str) or not source_id:
                    continue
                published_at = None
                try:
                    published_at = date.fromisoformat(source.get("as_of"))
                except (TypeError, ValueError):
                    pass
                sources_by_id[source_id] = ResearchSource(
                    source_record_id=source_id,
                    source_type="unknown",
                    source_quality="first_hand",
                    title=str(source.get("title") or source.get("endpoint") or "ETF来源"),
                    published_at=published_at,
                    summary=str(source.get("summary") or ""),
                    gaps=[str(gap) for gap in source.get("gaps", []) if isinstance(gap, str)],
                    retrieved_at=bundle_retrieved_at,
                )

            distance_metric = etf_bundle["metrics"].get("distance_from_1y_high_pct")
            distance_label = (
                "距近一年已观察最高价回撤"
                if isinstance(distance_metric, dict)
                and distance_metric.get("label") == "距近一年已观察到的最高价"
                else "距实际观察区间最高价回撤"
            )
            metric_facts = (
                ("最近收盘价", etf_bundle["metrics"].get("latest_price")),
                ("近20个SSE交易日平均成交额", etf_bundle["metrics"].get("average_amount_20d")),
                ("近12个月已实施现金分红", etf_bundle["metrics"].get("trailing_cash_dividend_per_share")),
                ("近一年报告收盘价变化", etf_bundle["metrics"].get("price_change_1y")),
                (distance_label, distance_metric),
                ("近12个月现金分红收益率", etf_bundle["metrics"].get("trailing_dividend_yield")),
                ("ETF自身现金分红收益率历史分位", etf_bundle["metrics"].get("trailing_dividend_yield_percentile_10y")),
                ("估值参考", etf_bundle["metrics"].get("trailing_dividend_yield_valuation")),
                ("资产净值", etf_bundle["metrics"].get("asset_scale")),
                ("基金份额规模", etf_bundle["metrics"].get("fund_size_shares")),
                ("管理费率", etf_bundle["metrics"].get("management_fee")),
                ("托管费率", etf_bundle["metrics"].get("custody_fee")),
                ("跟踪指数PE", etf_bundle["metrics"].get("underlying_pe")),
                ("跟踪指数PB", etf_bundle["metrics"].get("underlying_pb")),
            )
            for label, metric in metric_facts:
                if not isinstance(metric, dict):
                    continue
                if label in {"资产净值", "管理费率", "托管费率"} and not metric.get("unit"):
                    continue
                facts.append({
                    "label": label,
                    "value": metric["value"],
                    "unit": metric.get("unit") or "",
                    "symbol": symbol,
                    "source": metric.get("source", "Tushare-compatible"),
                    "endpoint": metric["endpoint"],
                    "field": metric["field"],
                    "date": metric["as_of"],
                    "retrieved_at": bundle_retrieved_at.isoformat(),
                    "window": metric.get("window"),
                    "verification_source_url": metric.get("verification_source_url"),
                })

        model_decision = None
        model_gaps: list[str] = []
        llm_call_count = 0
        model_call_diagnostics: list[dict] = []
        sources: list[dict] = [source.model_dump(mode="json") for source in sources_by_id.values()]

        fund_gaps: list[str] = []
        not_applicable: list[str] = []
        if security_type == "fund":
            from backend.services.serenity_agent import (
                SerenityAgentAudit,
                SerenityRunContext,
                VerifiedResearchCandidate,
            )
            from backend.services.serenity_synthesizer import ResearchSynthesizer

            fund_gaps = [
                "基金当前成分明细与行业权重未获取。",
                "基金实际跟踪差异未获取。",
            ]
            not_applicable = [
                "公司财报不适用于基金研究。",
                "公司画像与股票行业分类不适用于基金研究。",
            ]
            if is_verified_etf:
                fund_gaps.extend(etf_bundle.get("gaps", []))
                if (
                    etf_bundle["metrics"].get("trailing_cash_dividend_per_share") is None
                    and not any("cash_distribution" in _etf_gap_categories(gap) for gap in fund_gaps)
                ):
                    fund_gaps.append("近12个月已实施现金分红合计未能核验。")
            else:
                fund_gaps.append("基金分红与公告正文未获取。")
            source_ids = list(sources_by_id)
            candidate = VerifiedResearchCandidate(
                symbol=symbol,
                company_name=name,
                verification_id=identity_source_id,
                exchange="SSE" if symbol.endswith(".SH") else "SZSE" if symbol.endswith(".SZ") else "unknown",
                listing_status="verified",
                confidence="high",
                supporting_source_ids=source_ids,
                data_gaps=list(fund_gaps),
                unresolved_gaps=list(fund_gaps),
            )
            context = SerenityRunContext(
                sources_by_id=sources_by_id,
                verified_candidates_by_symbol={symbol: candidate},
            )
            now = datetime.now()
            theme = ThemeInput(
                theme_id=f"single_fund_{uuid.uuid4().hex[:10]}",
                theme_name=f"{symbol} 场内基金研究",
                background=(
                    "目标是经真实身份接口核验的场内基金，不是上市公司。"
                    "只依据已绑定的ETF基础信息、份额、价格成交额、真实现金分红和跟踪指数来源。"
                    "公司财报、主营业务和股票行业资料不适用。不得推断未获取的基金持仓、基准成分、"
                    "分红、跟踪误差或指数估值；证据缺口必须明示。"
                    "candidate_verdicts.reason必须是简体中文单句，不超过120字，只定性解读已获取的ETF证据；"
                    "不得含数字、日期、百分比、金额或代码。数值与撤回条件由系统单独展示。"
                ),
                source_type="manual_theme",
                research_mode="standard",
                created_at=now,
                updated_at=now,
            )
            audit = SerenityAgentAudit()
            audit.mode = "real"
            try:
                synthesis = ResearchSynthesizer(serenity_runner.llm_client).synthesize(
                    theme, context, audit,
                )
                model_decision = synthesis.candidate_verdicts.get(symbol)
                if not isinstance(model_decision, dict):
                    raise ValueError("missing_candidate_verdict")
                model_gaps = list(model_decision.get("evidence_gaps") or [])
            except Exception:
                model_decision = None
                model_gaps.append("研究层综合未能完成，未形成积极判断。")
            llm_call_count = len(audit.call_diagnostics)
            model_call_diagnostics = [
                dict(item) for item in audit.call_diagnostics if isinstance(item, dict)
            ]
            sources = [source.model_dump(mode="json") for source in sources_by_id.values()]
        else:
            from backend.services.friend_stock_flow import (
                FriendStockFlowService,
                validate_serenity_research_output,
            )

            transient_runner = SerenityAgentRunner(
                llm_client=serenity_runner.llm_client,
                validator=validator,
                tools=serenity_runner.serenity_tools,
                mode="real",
                execution_mode="two_phase",
                max_turns=serenity_runner.max_turns,
                db=None,
            )
            try:
                research_output = FriendStockFlowService(
                    validator=validator,
                    serenity_runner=transient_runner,
                    market_data_provider=None,
                ).run_industry_research(ticker=symbol, company_name=name)
                model_decision = validate_serenity_research_output(
                    transient_runner,
                    symbol,
                    research_output,
                    require_real_runner=True,
                    require_candidate_verdict=True,
                )
                model_gaps = list(model_decision.get("evidence_gaps") or [])
                model_call_diagnostics = [
                    dict(item) for item in research_output.get("serenity_call_diagnostics", [])
                    if isinstance(item, dict)
                ]
                sources.extend(
                    source for source in research_output.get("research_sources", [])
                    if isinstance(source, dict)
                )
                llm_call_count = len(research_output.get("serenity_stage_trace", []) or [])
            except Exception as exc:
                model_decision = None
                model_gaps.append("真实研究资料或研究层输出未能核验。")
                model_call_diagnostics = [
                    dict(item) for item in getattr(exc, "call_diagnostics", [])
                    if isinstance(item, dict)
                ]

        verdict_labels = {
            "research_positive": "值得研究",
            "research_watch": "观察",
            "research_reject": "不建议",
            "research_unavailable": "等待更多证据",
        }
        raw_verdict = model_decision.get("verdict") if isinstance(model_decision, dict) else None
        verdict = verdict_labels.get(raw_verdict, "等待更多证据")
        candidate_verdict_parsed = isinstance(raw_verdict, str) and raw_verdict in verdict_labels
        deterministic_etf_valuation = (
            etf_bundle["metrics"].get("trailing_dividend_yield_valuation")
            if is_verified_etf else None
        )
        if not candidate_verdict_parsed and isinstance(deterministic_etf_valuation, dict):
            verdict = (
                f"{deterministic_etf_valuation['value']}"
                "（仅510880自身现金分红收益率历史分位参考）"
            )
        safe_diagnostic_keys = {
            "call_id", "stage", "provider", "model", "status", "exception_class", "http_status",
            "provider_error_code", "timeout", "response_received", "parse_reached",
            "failure_class", "source_count", "duration_ms",
            "attempt_count", "retry_count", "retry_stop_reason", "exception_chain",
            "response_error_text", "attempts",
        }
        safe_call_diagnostics = [
            {key: value for key, value in item.items() if key in safe_diagnostic_keys}
            for item in model_call_diagnostics
        ]
        last_call = model_call_diagnostics[-1] if model_call_diagnostics else {}
        if not model_call_diagnostics:
            model_failure_reason = "model_call_not_recorded"
        elif last_call.get("status") != "success":
            model_failure_reason = (
                "response_parse_or_validation_failed"
                if last_call.get("response_received") is True
                else last_call.get("failure_class") or "provider_request_failed"
            )
        elif not candidate_verdict_parsed:
            model_failure_reason = "candidate_verdict_missing"
        else:
            model_failure_reason = None
        model_reason = model_decision.get("reason") if isinstance(model_decision, dict) else None
        safe_model_rationale = _safe_research_sentence(
            model_reason,
            symbol,
        )
        if (
            is_verified_etf
            and safe_model_rationale
            and not _etf_reason_uses_available_data(safe_model_rationale, etf_bundle)
        ):
            safe_model_rationale = None
        model_reason_filtered = bool(model_reason) and safe_model_rationale is None
        rationale_source = "llm"
        if safe_model_rationale:
            rationale = safe_model_rationale
        elif is_verified_etf:
            rationale = _deterministic_etf_rationale(etf_bundle, raw_verdict)
            rationale_source = "deterministic_etf_summary"
        elif security_type == "fund":
            rationale = "本次仅核验基金身份和有日期的行情，基金专属材料仍有缺口，先等待补充证据。"
            rationale_source = "safe_fallback"
        else:
            rationale = "本次可核验资料不足以支撑更积极的研究判断。"
            rationale_source = "safe_fallback"
        if model_reason_filtered and not is_verified_etf:
            model_gaps.append("模型理由含未授权数字或格式不合规，该段未展示。")

        counters = model_decision.get("counter_evidence", []) if isinstance(model_decision, dict) else []
        counter_text = next((
            safe for item in counters if isinstance(item, dict)
            if (safe := _safe_research_sentence(item.get("description"), symbol))
        ), None)
        if is_verified_etf:
            risk_parts = ["基金当前成分明细、行业权重和实际跟踪差异未获取。"]
            if (
                etf_bundle["metrics"].get("underlying_pe") is None
                and etf_bundle["metrics"].get("underlying_pb") is None
            ):
                if etf_bundle["metrics"].get("trailing_dividend_yield_valuation"):
                    risk_parts.append("跟踪指数PE/PB未覆盖；ETF自身股息率仅作自身历史替代参考。")
                else:
                    risk_parts.append("跟踪指数PE/PB当前值未能核验。")
            if (
                etf_bundle["metrics"].get("underlying_dividend_yield") is None
                and not etf_bundle["metrics"].get("trailing_dividend_yield_valuation")
            ):
                risk_parts.append("跟踪指数股息率无法由本次接口核验。")
            main_risk = "".join(risk_parts)
        else:
            main_risk = (
                "基金持仓、基准跟踪和分红资料本次未核，相关风险无法评估。"
                if security_type == "fund"
                else counter_text or "研究来源仍有待核实事项，相关风险尚未查清。"
            )
        conditions = model_decision.get("invalidation_conditions", []) if isinstance(model_decision, dict) else []
        model_invalidation = next((
            safe for value in conditions
            if (safe := _safe_research_sentence(value, symbol))
        ), None)
        investment_assumption = None
        if is_verified_etf:
            model_reason = str(model_decision.get("reason") or "") if isinstance(model_decision, dict) else ""
            dividend_reason = any(token in model_reason for token in ("分红", "派息", "股息", "现金分配"))
            if dividend_reason:
                dividend_baseline = etf_bundle.get("investment_assumption")
                if dividend_baseline:
                    investment_assumption = dict(dividend_baseline)
                    invalidation = (
                        "本次研究理由涉及现金分红，并依赖以下待检验假设："
                        + dividend_baseline["condition"]
                    )
                else:
                    invalidation = (
                        "本次研究理由涉及现金分红，但近12个月已实施现金分红总额未能核验；"
                        "当前无法给出可靠的数值撤回条件，补齐真实派息数据后重新评估。"
                    )
            else:
                amount_baseline = etf_bundle["metrics"].get("average_amount_20d")
                if isinstance(amount_baseline, dict) and amount_baseline.get("value", 0) > 0:
                    amount_value = f"{amount_baseline['value']:.12g}"
                    condition = (
                        f"如果未来滚动20个SSE交易日按同口径计算的平均成交额低于本次核验的{amount_value}元，"
                        "则本次研究理由所依赖的当前流动性水平假设不成立，需重新评估。"
                        "这是一项待检验假设，不代表未来流动性保证。"
                    )
                    investment_assumption = {
                        "kind": "average_amount_20d_baseline",
                        "baseline_value": amount_baseline["value"],
                        "unit": "元",
                        "endpoint": "fund_daily",
                        "source": "Tushare-compatible",
                        "as_of": amount_baseline["as_of"],
                        "window": amount_baseline["window"],
                        "condition": condition,
                        "limitation": "仅为可观察的研究假设，不代表未来流动性保证。",
                    }
                    invalidation = condition
                else:
                    invalidation = (
                        "本次研究理由未基于分红，但完整的SSE日历最近20日平均成交额不可核验；"
                        "当前无法给出可靠的数值流动性撤回条件。"
                    )
        elif security_type == "fund":
            invalidation = "基金身份或行情来源核验不一致时，撤回本次结论并重新核对。"
        else:
            invalidation = model_invalidation or "标的身份或支持来源核验不一致时，撤回结论并重新研究。"

        evidence_gaps = []
        if security_type == "fund":
            evidence_gaps.extend(fund_gaps)
        source_etf_gap_categories = (
            set().union(*(
                _etf_gap_categories(gap)
                for gap in [*fund_gaps, *(etf_bundle.get("gaps", []) if is_verified_etf else [])]
            ))
            if is_verified_etf else set()
        )
        quote_gaps = [*(quote_result.gaps if quote_result else []), *(quote_result.errors if quote_result else [])]
        for gap in [*quote_gaps, *model_gaps]:
            if is_verified_etf and gap in model_gaps:
                model_categories = _etf_gap_categories(gap)
                if model_categories and model_categories.issubset(source_etf_gap_categories):
                    continue
            if security_type == "fund" and any(
                marker in gap for marker in ("公司财报", "公司画像", "股票行业分类")
            ):
                continue
            safe_gap = _safe_research_sentence(gap, symbol)
            if safe_gap:
                evidence_gaps.append(safe_gap)
            elif gap and not is_verified_etf:
                evidence_gaps.append("部分研究说明含未授权数字或格式不合规，该段未展示。")
        if not facts:
            evidence_gaps.append("最近收盘行情未获取或未能按代码、交易日和收盘价核验。")
        evidence_gaps = list(dict.fromkeys(evidence_gaps))

        narrative_sentences = [
            f"结论：{verdict}；仅研究参考。",
            f"理由：{rationale}",
            f"主要风险：{main_risk}",
            f"撤回条件：{invalidation}",
        ]
        if is_verified_etf:
            valuation = etf_bundle["metrics"].get("trailing_dividend_yield_valuation")
            if isinstance(valuation, dict):
                narrative_sentences.append(
                    f"估值参考：510880自身现金分红收益率处于{valuation['value']}；"
                    "该结论只比较本ETF可得历史，不等同于指数估值，也不代表未来分红或回报。"
                )
        return {
            "status": "research_completed" if candidate_verdict_parsed else "research_unavailable",
            "symbol": symbol,
            "name": name,
            "security_type": security_type,
            "etf_research": etf_bundle if is_verified_etf else None,
            "identity_source": {
                "source": "Tushare-compatible",
                "endpoint": "fund_basic" if security_type == "fund" else "stock_basic",
                "symbol": symbol,
                "retrieved_at": identity.get("retrieved_at"),
            },
            "verdict": verdict,
            "research_reference_only": True,
            "rationale": rationale,
            "main_risk": main_risk,
            "invalidation_condition": invalidation,
            "investment_assumption": investment_assumption,
            "narrative_sentences": narrative_sentences,
            "numeric_facts": facts if is_verified_etf else facts[:3],
            "sources": sources,
            "not_applicable": not_applicable,
            "evidence_gaps": evidence_gaps,
            "llm_call_count": llm_call_count,
            "research_diagnostic": {
                "llm_call_count": llm_call_count,
                "calls": safe_call_diagnostics,
                "candidate_verdict_parsed": candidate_verdict_parsed,
                "candidate_verdict": raw_verdict if candidate_verdict_parsed else None,
                "failure_reason": model_failure_reason,
                "rationale_source": rationale_source,
                "model_reason_filtered": model_reason_filtered,
            },
        }

    def _submit_execution_feedback(request: ExecutionFeedbackRequest):
        """Record a user-confirmed completed trade in the shared live-trade ledger."""
        import hashlib
        import json
        import sqlite3
        import uuid
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from fastapi import HTTPException
        from backend.config.runtime_paths import get_live_trade_db_path
        from backend.db.live_trade import LiveTradeDB
        from backend.services.observation_pool import ObservationPool
        from backend.services.discipline_review import DisciplineReviewService
        from contracts.live_trade import ExecutionObservationLog, PositionLifecycleState, TradeType

        if request.confirmed_already_executed is not True:
            raise HTTPException(status_code=400, detail="只能登记已完成的成交记录，请先确认本次成交。")
        if request.execution_date > datetime.now(ZoneInfo("Asia/Shanghai")).date():
            raise HTTPException(status_code=400, detail="成交日期不能晚于今天。")

        symbol = _canonical_manual_symbol(request.symbol)
        action = request.action
        price_decimal = request.price
        trade_amount_decimal = price_decimal * Decimal(request.quantity)
        price = float(price_decimal)
        quantity = request.quantity
        fees = float(request.fees) if request.fees is not None else None
        has_exit_plan = any((
            request.exit_plan_target_price is not None,
            request.exit_plan_stop_price is not None,
            request.exit_plan_conditions is not None,
        ))
        now = datetime.now()
        canonical_decimal = lambda value: format(value.normalize(), "f") if value is not None else None
        payload = {
            "action": action,
            "symbol": symbol,
            "position_id": request.position_id,
            "execution_date": request.execution_date.isoformat(),
            "price": canonical_decimal(price_decimal),
            "quantity": quantity,
            "fees": canonical_decimal(request.fees),
            "trade_amount": format(trade_amount_decimal, "f"),
            "trade_source": request.trade_source,
            "reason": request.reason,
            "sell_reason": request.sell_reason,
            "exit_plan_target_price": canonical_decimal(request.exit_plan_target_price),
            "exit_plan_stop_price": canonical_decimal(request.exit_plan_stop_price),
            "exit_plan_conditions": request.exit_plan_conditions,
            "confirm_quantity_anomaly": request.confirm_quantity_anomaly,
        }
        payload_fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest()
        fingerprint = hashlib.sha256(
            json.dumps(
                {"trade_type": request.trade_type, "payload_fingerprint": payload_fingerprint},
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        live_db = LiveTradeDB(get_live_trade_db_path())
        previous = live_db.get_manual_operation(request.operation_id)
        if previous:
            if previous["operation_fingerprint"] != fingerprint:
                raise HTTPException(status_code=409, detail="该操作编号已用于不同的成交内容，请刷新后重新提交。")
            return json.loads(previous["operation_response"])

        # Resolve only after the idempotency check: read-side identity can change
        # independently, while a retry must return its original saved response.
        identity = _resolve_manual_security(request.symbol)
        name = identity["name"] or "名称未知"

        quantity_warning = (
            action == "buy"
            and identity["security_type"] == "stock"
            and quantity % 100 != 0
        )
        if quantity_warning and not request.confirm_quantity_anomaly:
            raise HTTPException(
                status_code=400,
                detail="该股票买入数量不是100股整数倍。若这是已完成的实际成交，请确认后继续登记。",
            )

        open_position = None
        buy_log = None
        held_quantity = None
        simulated_execution_rule_verified = None
        simulated_execution_rule_warning = None
        if action == "sell":
            open_position = live_db.get_position(request.position_id)
            if (
                open_position is None
                or open_position.lifecycle_state != PositionLifecycleState.open
                or open_position.record_source != "autonomous_manual"
                or open_position.trade_type != TradeType(request.trade_type)
                or open_position.symbol != symbol
            ):
                raise HTTPException(
                    status_code=400,
                    detail="所选持仓已关闭或与代码、实际/模拟类型不匹配。若这是实际成交，请先补录遗漏的买入记录。",
                )
            buy_log = live_db.get_log(open_position.source_log_id)
            if (
                buy_log is None
                or buy_log.confirmed_action != "buy"
                or buy_log.trade_type != open_position.trade_type
                or buy_log.symbol != open_position.symbol
            ):
                raise HTTPException(
                    status_code=400,
                    detail="所选持仓缺少可核实的同类型买入记录，不能登记卖出。若这是实际成交，请先补录遗漏的买入记录。",
                )
            supported_t1_rule = bool(
                request.trade_type == "simulated"
                and identity["status"] == "verified"
                and buy_log.execution_date is not None
                and buy_log.security_type == identity["security_type"]
                and (
                    identity["security_type"] == "stock"
                    or (symbol == "510880.SH" and identity["security_type"] == "fund")
                )
            )
            if supported_t1_rule and request.execution_date <= buy_log.execution_date:
                raise HTTPException(
                    status_code=400,
                    detail="模拟股票卖出受 T+1 限制，不能在买入当日或买入日前卖出。",
                )
            sellable_quantity = live_db.get_sellable_quantity(
                symbol=symbol,
                trade_type=TradeType(request.trade_type),
                record_source="autonomous_manual",
                execution_date=request.execution_date,
            )
            held_quantity = live_db.get_position_quantity(
                symbol=symbol,
                trade_type=TradeType(request.trade_type),
                record_source="autonomous_manual",
                execution_date=request.execution_date,
            )
            if quantity > sellable_quantity:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"卖出数量超过可卖数量（当前最多 {sellable_quantity} {open_position.symbol}）。"
                        "若这是实际成交，请先补录遗漏的买入记录，再登记卖出。"
                    ),
            )
            if request.trade_type == "simulated" and open_position:
                if supported_t1_rule:
                    simulated_execution_rule_verified = False
                    try:
                        from backend.api.observations import get_position_market_monitor

                        calendar_rows = get_position_market_monitor().trade_calendar_rows_between(
                            buy_log.execution_date,
                            request.execution_date,
                        )
                        open_dates = {
                            datetime.strptime(str(row["cal_date"]), "%Y%m%d").date()
                            for row in calendar_rows
                            if str(row.get("is_open", "")).strip() in {"1", "1.0", "True", "true"}
                        }
                        if buy_log.execution_date in open_dates and request.execution_date in open_dates:
                            simulated_execution_rule_verified = True
                        else:
                            simulated_execution_rule_warning = "成交日期未能按上交所交易日历核实；暂不能验证该模拟卖出。"
                    except Exception:
                        simulated_execution_rule_warning = "上交所交易日历未能核实；暂不能验证该模拟卖出。"
                else:
                    simulated_execution_rule_verified = False
                    simulated_execution_rule_warning = "交易规则未核，暂不能验证该模拟卖出。"
                if simulated_execution_rule_verified is not True:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            simulated_execution_rule_warning.rstrip("。") + "，未保存记录。"
                            if simulated_execution_rule_warning
                            else "模拟卖出的 T+1 交易日规则无法核实，未保存记录。"
                        ),
                    )

        log_id = f"log_{uuid.uuid4().hex[:12]}"
        log = ExecutionObservationLog(
            log_id=log_id,
            draft_id=None,
            execution_card_id=None,
            signal_id=None,
            action_plan_id=None,
            capital_context_id=None,
            market_snapshot_id=None,
            confirmed_action=action,
            confirmed_execution_status="executed_full",
            confirmed_price=price,
            confirmed_quantity=quantity,
            reason=request.reason,
            confirmed_by_user=True,
            broker_verified=False,
            confirmed_at=now,
            execution_date=request.execution_date,
            confirmed_fees=fees,
            confirmed_trade_amount=format(trade_amount_decimal, "f"),
            trade_type=TradeType(request.trade_type),
            symbol=symbol,
            name=name,
            security_type=identity["security_type"],
            quantity_unit=identity["quantity_unit"],
            trade_source=request.trade_source,
            sell_reason=request.sell_reason,
            exit_plan_target_price=(
                float(request.exit_plan_target_price) if request.exit_plan_target_price is not None else None
            ),
            exit_plan_stop_price=(
                float(request.exit_plan_stop_price) if request.exit_plan_stop_price is not None else None
            ),
            exit_plan_conditions=request.exit_plan_conditions,
            exit_plan_entered_at=now if has_exit_plan else None,
            exit_plan_is_retrospective=True if has_exit_plan else None,
            record_source="autonomous_manual",
            operation_id=request.operation_id,
            operation_fingerprint=fingerprint,
        )
        review_service = DisciplineReviewService()
        fee_calculation = review_service.calculate_order_fee(log)

        position = None
        close_position_id = None
        remaining_quantity = None
        review = None
        ai_review_diagnostic = None
        position_id = None
        pnl_record = None
        warnings = [
            (
                "这是模拟成交记录，不代表券商账户成交；系统不会下单，请自行核对 T+1、停牌及涨跌停异常。"
                if request.trade_type == "simulated"
                else "仅登记已完成的成交，不会下单；请自行核对 T+1、停牌及涨跌停异常。"
            )
        ]
        if identity["security_type"] == "unknown":
            warnings.append("证券身份或交易单位未能核实；记录保留为未知，不据此推断标的名称或买入手数。")
        if quantity_warning:
            warnings.append("已按你的确认保留非100股整数倍的成交数量。")
        if request.trade_source == "system_suggestion":
            warnings.append("“系统建议”是你选择的来源描述，不代表本记录已关联已验证策略或Action Plan。")

        if action == "buy":
            position = ObservationPool().create_position_from_log(
                log=log,
                symbol=symbol,
                name=name,
                template_id="manual_unlinked",
                template_version="v1",
                entry_thesis=request.reason or "",
            )
            position_id = position.position_id
        else:
            review_execution_rule_status = (
                "actual_recorded" if request.trade_type == "actual"
                else "verified" if simulated_execution_rule_verified is True
                else "unverified"
            )
            ledger_logs = live_db.list_manual_position_logs(
                symbol=symbol,
                trade_type=TradeType(request.trade_type),
                record_source="autonomous_manual",
                execution_date=request.execution_date,
            )
            buy_logs = [item for item in ledger_logs if item.confirmed_action == "buy"]
            review_buy_log = buy_logs[0] if len(buy_logs) == 1 else None
            differing_buy_sources = len({
                (item.action_plan_id, item.trade_source, item.reason)
                for item in buy_logs
            }) > 1
            pnl_record = review_service.calculate_manual_position_pnl(
                open_position.position_id,
                ledger_logs,
                log,
            )
            review = review_service.create_review(
                position_id=open_position.position_id if open_position else None,
                execution_card_id=None,
                signal_id=None,
                daily_signal_ids=[],
                buy_log=review_buy_log,
                sell_log=log,
                execution_rule_status=review_execution_rule_status,
                additional_missing_fields=[],
                pnl_record_override=pnl_record,
                buy_log_ids=[item.log_id for item in buy_logs],
                multiple_buy_sources=differing_buy_sources,
            )
            if len(buy_logs) > 1:
                ai_review_text, ai_review_status, ai_review_diagnostic = (
                    None,
                    "not_requested",
                    {"status": "not_requested", "reason": "multiple_buy_records"},
                )
            else:
                llm_client = (
                    getattr(serenity_runner, "llm_client", None)
                    if conversation_mode == "real"
                    else None
                )
                ai_review_text, ai_review_status, ai_review_diagnostic = review_service.generate_ai_review_with_diagnostic(
                    review,
                    review_buy_log,
                    log,
                    llm_client,
                )
            review = review.model_copy(update={
                "ai_review_text": ai_review_text,
                "ai_review_status": ai_review_status,
            })
            pnl_record = review.pnl_record
            if open_position:
                position_id = open_position.position_id
                close_position_id = open_position.position_id
                remaining = (held_quantity or 0) - quantity
                remaining_quantity = remaining if remaining > 0 else None

        response = {
            "status": "success",
            "action": action,
            "trade_type": request.trade_type,
            "pnl_trade_type": pnl_record.trade_type.value if pnl_record else None,
            "position_id": position_id,
            "log_id": log_id,
            "pnl_record_id": pnl_record.pnl_record_id if pnl_record else None,
            "discipline_review_id": review.review_id if review else None,
            "ai_review_diagnostic": ai_review_diagnostic if review else None,
            "realized_pnl": pnl_record.pnl_amount if pnl_record else None,
            "pnl_pct": pnl_record.pnl_pct if pnl_record else None,
            "gross_pnl_amount": pnl_record.gross_pnl_amount if pnl_record else None,
            "gross_pnl_pct": pnl_record.gross_pnl_pct if pnl_record else None,
            "fees": fees,
            "fee_calculation": fee_calculation.model_dump(mode="json"),
            "pnl_fee_calculation": (
                pnl_record.fee_calculation.model_dump(mode="json")
                if pnl_record else None
            ),
            "pnl_source": pnl_record.pnl_source.value if pnl_record else None,
            "trade_amount": format(trade_amount_decimal, "f"),
            "execution_date": request.execution_date.isoformat(),
            "recorded_at": now.isoformat(),
            "security_identity_status": identity["status"],
            "security_type": identity["security_type"],
            "quantity_unit": identity["quantity_unit"],
            "trade_source": request.trade_source,
            "sell_reason": request.sell_reason,
            "exit_plan_target_price": log.exit_plan_target_price,
            "exit_plan_stop_price": log.exit_plan_stop_price,
            "exit_plan_conditions": log.exit_plan_conditions,
            "exit_plan_entered_at": now.isoformat() if has_exit_plan else None,
            "exit_plan_is_retrospective": True if has_exit_plan else None,
            "pnl_fees": pnl_record.fees if pnl_record else None,
            "pnl_missing_fields": pnl_record.missing_fields if pnl_record else (
                ["execution_rule"] if simulated_execution_rule_verified is False
                else ["matching_position"] if action == "sell"
                else ["fees"] if fees is None
                else []
            ),
            "execution_rule_status": (
                "actual_recorded" if action == "sell" and request.trade_type == "actual"
                else "verified" if action == "sell" and simulated_execution_rule_verified is True
                else "unverified" if action == "sell"
                else None
            ),
            "record_source": "autonomous_manual",
            "plan_linked": False,
            "warnings": warnings,
        }
        try:
            live_db.save_manual_operation(
                log,
                response,
                position=position,
                close_position_id=close_position_id,
                remaining_quantity=remaining_quantity,
                review=review,
            )
        except sqlite3.IntegrityError:
            previous = live_db.get_manual_operation(request.operation_id)
            if previous:
                if previous["operation_fingerprint"] != fingerprint:
                    raise HTTPException(status_code=409, detail="该操作编号已用于不同的成交内容，请刷新后重新提交。")
                return json.loads(previous["operation_response"])
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return response

    @app.post("/api/agent/workbench/execution-feedback")
    def submit_execution_feedback(request: ExecutionFeedbackRequest):
        return _submit_execution_feedback(request)

    @app.post("/api/agent/workbench/{conversation_id}/daily-signal")
    def generate_daily_signal(conversation_id: str):
        """Refuse to infer a position signal without a real current quote."""
        from backend.db.live_trade import LiveTradeDB
        from backend.config.runtime_paths import get_live_trade_db_path

        live_trade_db = LiveTradeDB(get_live_trade_db_path())
        with live_trade_db._get_conn() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM observation_positions WHERE lifecycle_state = 'open'"
            ).fetchone()[0]
        if count == 0:
            return {"status": "no_open_positions", "message": "没有持仓需要观察", "signals": []}
        return {
            "status": "market_data_unavailable",
            "message": "当前没有可验证的实时行情，暂不生成持仓信号。",
            "signals": [],
        }

    @app.get("/api/research/service-health")
    def get_service_health():
        """Get research service health status (no sensitive values)."""
        import os

        conversation_mode = os.getenv("RESEARCH_CONVERSATION_MODE", "real")
        serenity_mode = os.getenv("SERENITY_EXECUTION_MODE", "")

        llm_configured = bool(os.getenv("RESEARCH_LLM_API_KEY"))
        tushare_configured = bool(os.getenv("TUSHARE_TOKEN"))

        is_real_mode = conversation_mode == "real" and serenity_mode == "two_phase"
        is_healthy = is_real_mode and llm_configured and tushare_configured

        return {
            "mode": conversation_mode,
            "serenity": serenity_mode,
            "llm_configured": llm_configured,
            "tushare_configured": tushare_configured,
            "is_real_mode": is_real_mode,
            "is_healthy": is_healthy,
        }

    return app

# Default app instance for uvicorn
app = create_research_app()
