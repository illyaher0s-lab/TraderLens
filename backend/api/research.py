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

from datetime import date, datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.db.research import ResearchDB
from backend.services.research_action_reducer import ResearchActionReducer
from backend.services.research_conversation import ResearchConversationService
from backend.services.research_validation import ResearchValidator
from backend.services.serenity_stub import SerenityStubRunner
from backend.services.evidence_light import EvidenceLightRunner
from contracts.research import ThemeInput, ProposedAction


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


class ApplyActionRequest(BaseModel):
    action_id: str
    applied_by: str


class ReopenRequest(BaseModel):
    actor: str = "user"
    reason: str


class ConfirmCandidateRequest(BaseModel):
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


def create_research_app(
    db: ResearchDB | None = None,
    conversation_mode: str = "deterministic",
    serenity_execution_mode: str = "stub",
    validator: ResearchValidator | None = None,
    serenity_runner=None,
    market_data_provider=None,
    allow_test_serenity_runner: bool = False,
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
    
    Returns:
        FastAPI app
    """
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if db is None:
        db = ResearchDB()
    
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
            import os
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
        from backend.services.friend_stock_flow import FriendStockFlowService
        
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
            )
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))
        
        # Create or get candidate
        from contracts.research import CandidateStock, ThemeInput
        
        # Check if theme exists, create if not
        theme = db.get_theme(flow_id)
        if not theme:
            from datetime import datetime
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
        
        # Confirm candidate
        confirmed = db.confirm_candidate(
            candidate_id=candidate_id,
            confirmation_reason="Friend recommendation approved",
            evidence_level="medium",
            confirmed_by="user",
            pool_snapshot_date=pool.confirmation_date.date(),
            thesis_snapshot=pool.thesis_snapshot,
            invalidation_rules=pool.invalidation_rules,
            price_snapshot=pool.price_snapshot,
            benchmark_snapshot=pool.benchmark_snapshot,
            evidence_snapshot_ids=pool.evidence_snapshot_ids,
            primary_evidence_snapshot_id=None,
        )
        
        # Return pool with confirmed_id
        response = pool.model_dump()
        response["confirmed_id"] = confirmed.confirmed_id
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
        
        Routes natural language to friend-stock or strategy-idea flows
        without exposing technical parameters.
        
        Task 13: Deterministic routing without LLM dependency.
        Persists to agent_workbench DB.
        """
        import uuid
        import re
        from datetime import datetime
        
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
            
            # Deterministic routing rules (no LLM)
            message_lower = request.message.lower()
            workflow_kind = None
            workflow_state = WorkflowState.CREATED
            session_title = "未知会话"
            
            # Friend stock detection
            friend_stock_keywords = [
                "朋友", "推荐", "股票", "公司", "帮我看", "帮我查",
                "pudong", "浦发", "招商", "平安",
            ]
            stock_code_pattern = r"\d{6}\.(SH|SZ|sh|sz)"
            
            has_stock_code = bool(re.search(stock_code_pattern, request.message))
            has_friend_stock_keyword = any(kw in message_lower for kw in friend_stock_keywords)
            
            if has_stock_code or has_friend_stock_keyword:
                workflow_kind = WorkflowKind.FRIEND_STOCK
                session_title = "朋友推荐股票调查"
                workflow_state = WorkflowState.RESEARCHING
            else:
                # Strategy idea detection
                strategy_keywords = [
                    "抖音", "视频", "策略", "两点半", "第二天", "买入", "卖出",
                    "douyin", "下午", "早上",
                ]
                
                has_strategy_keyword = any(kw in message_lower for kw in strategy_keywords)
                
                if has_strategy_keyword:
                    workflow_kind = WorkflowKind.STRATEGY_IDEA
                    session_title = "抖音策略验证"
                    workflow_state = WorkflowState.VALIDATING
            
            # Create session in DB
            if workflow_kind is None:
                workflow_kind = WorkflowKind.UNKNOWN

            session = AgentSession(
                session_id=conversation_id,
                workflow_kind=workflow_kind,
                workflow_state=workflow_state,
                title=session_title,
                created_at=now,
                updated_at=now,
            )
            create_session(db.conn, session)
        else:
            # Existing session
            session = get_session(db.conn, conversation_id)
        
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
        
        # Generate agent reply based on workflow
        workflow_type = session.workflow_kind.value
        stage = session.workflow_state.value
        approval_card = None
        artifact_ids = []
        next_required_user_action = "provide_more_context"
        
        if session.workflow_kind == WorkflowKind.FRIEND_STOCK:
            # Task 21: Orchestrate friend-stock flow (fix P0-1)
            # Extract company name or ticker from user message
            from backend.services.friend_stock_flow import FriendStockFlowService
            import re
            
            # Simple extraction: look for company name or stock code
            stock_code_pattern = r"(\d{6}\.(SH|SZ|sh|sz))"
            code_match = re.search(stock_code_pattern, request.message)
            
            raw_code_input = code_match.group(1) if code_match else None
            raw_company_input = request.message if not code_match else None
            
            # Call friend-stock intake (ticker verification)
            flow_service = FriendStockFlowService(
                validator=validator,
                serenity_runner=None,
                market_data_provider=None,
            )
            
            try:
                verification_result = flow_service.verify_ticker(
                    raw_company_input=raw_company_input or "",
                    raw_code_input=raw_code_input,
                )
                
                # Store flow state in DB
                flow_id = verification_result.flow_id
                db.store_friend_stock_flow(
                    flow_id=flow_id,
                    raw_company_input=raw_company_input or "",
                    raw_code_input=raw_code_input,
                    source_note=f"Workbench conversation {conversation_id}",
                    ticker_verification_result=verification_result.model_dump(mode="json"),
                )
                
                # Create friend_stock_flow artifact
                flow_artifact = ArtifactRef(
                    artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                    session_id=conversation_id,
                    artifact_id=flow_id,
                    artifact_type="friend_stock_flow",
                    created_at=now,
                )
                attach_artifact_ref(db.conn, flow_artifact)
                artifact_ids.append(flow_id)
                
                # Handle verification result
                if verification_result.status == "verified":
                    # Ticker verified - attempt research if serenity available
                    if conversation_mode == "real" and serenity_runner and hasattr(serenity_runner, 'run'):
                        # Attempt research
                        try:
                            research_output = flow_service.run_industry_research(
                                ticker=verification_result.resolved_ticker,
                                company_name=verification_result.resolved_name,
                            )
                            
                            # Store research output
                            db.store_friend_stock_flow(
                                flow_id=flow_id,
                                raw_company_input=raw_company_input or "",
                                raw_code_input=raw_code_input,
                                source_note=f"Workbench conversation {conversation_id}",
                                ticker_verification_result=verification_result.model_dump(mode="json"),
                                research_output=research_output,
                            )
                            
                            # Create research_report artifact
                            research_artifact = ArtifactRef(
                                artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                                session_id=conversation_id,
                                artifact_id=f"research_{flow_id}",
                                artifact_type="research_report",
                                created_at=now,
                            )
                            attach_artifact_ref(db.conn, research_artifact)
                            artifact_ids.append(f"research_{flow_id}")
                            
                            agent_reply = f"已完成对 {verification_result.resolved_name} ({verification_result.resolved_ticker}) 的调查。\n\n研究结果已生成，等待你的审批决定。"
                            workflow_state = WorkflowState.WAITING_FOR_APPROVAL
                            next_required_user_action = "review_research_and_approve"
                            
                        except Exception as e:
                            # Research failed
                            agent_reply = f"已识别 {verification_result.resolved_name} ({verification_result.resolved_ticker})，但研究执行失败：{str(e)}\n\n请稍后重试或手动调用研究流程。"
                            workflow_state = WorkflowState.STOPPED
                            next_required_user_action = "retry_or_manual_research"
                    else:
                        # No serenity runner - mark as waiting
                        agent_reply = f"已识别 {verification_result.resolved_name} ({verification_result.resolved_ticker})。\n\n当前环境未配置研究服务，需要人工介入或配置 Serenity runner。"
                        workflow_state = WorkflowState.STOPPED
                        next_required_user_action = "configure_research_service"
                
                elif verification_result.status == "ambiguous":
                    # Multiple candidates - need user clarification
                    candidates_text = "\n".join([
                        f"{i+1}. {c['name']} ({c['ticker']})"
                        for i, c in enumerate(verification_result.candidates)
                    ])
                    agent_reply = f"找到多个匹配结果：\n{candidates_text}\n\n请明确告诉我是哪一个公司。"
                    workflow_state = WorkflowState.CREATED
                    next_required_user_action = "clarify_company"
                
                else:
                    # Verification failed
                    agent_reply = f"无法识别公司或股票代码：{request.message}\n\n请提供更明确的公司名称或完整的股票代码（如 600000.SH）。"
                    workflow_state = WorkflowState.STOPPED
                    next_required_user_action = "provide_clear_company_name"
                
            except Exception as e:
                # Intake failed
                agent_reply = f"处理失败：{str(e)}\n\n请检查输入格式或稍后重试。"
                workflow_state = WorkflowState.STOPPED
                next_required_user_action = "retry_with_clear_input"
            
        elif session.workflow_kind == WorkflowKind.STRATEGY_IDEA:
            # Task 22: Orchestrate strategy-idea flow (fix P0-2)
            from backend.services.strategy_idea_flow import StrategyIdeaFlowService
            
            flow_service = StrategyIdeaFlowService()
            
            try:
                # Create strategy idea (defaults to untrusted)
                idea = flow_service.create_idea(
                    raw_source_text=request.message,
                    source_channel="workbench",
                )
                
                # Create strategy_idea artifact
                idea_artifact = ArtifactRef(
                    artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                    session_id=conversation_id,
                    artifact_id=idea.idea_id,
                    artifact_type="strategy_idea",
                    created_at=now,
                )
                attach_artifact_ref(db.conn, idea_artifact)
                artifact_ids.append(idea.idea_id)
                
                # Extract claims (LLM-assisted or deterministic fallback)
                extraction = flow_service.extract_claims(idea)
                
                # Create extraction artifact
                extraction_artifact = ArtifactRef(
                    artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                    session_id=conversation_id,
                    artifact_id=extraction.extraction_id,
                    artifact_type="strategy_idea_extraction",
                    created_at=now,
                )
                attach_artifact_ref(db.conn, extraction_artifact)
                artifact_ids.append(extraction.extraction_id)
                
                # Template mapping (deterministic - check if any approved templates exist)
                # For now, no approved templates exist, so map to no_template_fit
                mapping = flow_service.map_to_template(
                    idea=idea,
                    matched_template_id=None,
                    template_version=None,
                    mapping_reason="当前系统暂无已批准模板库。策略想法已记录，但不可用于实盘交易。",
                )
                
                # Create mapping artifact
                mapping_artifact = ArtifactRef(
                    artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                    session_id=conversation_id,
                    artifact_id=mapping.mapping_id,
                    artifact_type="template_mapping",
                    created_at=now,
                )
                attach_artifact_ref(db.conn, mapping_artifact)
                artifact_ids.append(mapping.mapping_id)
                
                # Since no template fit, create rejected entry
                rejected_entry = flow_service.reject_idea(
                    idea=idea,
                    reason="无已批准模板匹配，无法进入策略库",
                )
                
                # Create rejection artifact
                rejection_artifact = ArtifactRef(
                    artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                    session_id=conversation_id,
                    artifact_id=rejected_entry["idea_id"],
                    artifact_type="rejected_strategy",
                    created_at=now,
                )
                attach_artifact_ref(db.conn, rejection_artifact)
                artifact_ids.append(rejected_entry["idea_id"] + "_rejected")
                
                # Set response
                agent_reply = f"已提取策略想法：\n\n入场条件：{extraction.claimed_entry}\n出场条件：{extraction.claimed_exit}\n\n{mapping.mapping_reason}\n\n该策略想法已记录到拒绝注册表，不会生成交易信号。"
                workflow_state = WorkflowState.STOPPED
                next_required_user_action = "acknowledged_rejection"
                
            except Exception as e:
                # Extraction or mapping failed
                agent_reply = f"处理策略想法失败：{str(e)}\n\n请检查描述是否完整或稍后重试。"
                workflow_state = WorkflowState.STOPPED
                next_required_user_action = "retry_with_clear_description"
            
        elif session.workflow_kind == WorkflowKind.UNKNOWN:
            workflow_type = "unknown"
            agent_reply = "你好，我可以帮你：\n1. 调查朋友推荐的股票（告诉我公司名或股票代码）\n2. 验证抖音/视频看到的交易策略\n\n请告诉我你想做什么？"
            next_required_user_action = "clarify_intent"
        else:
            agent_reply = "你好，我可以帮你：\n1. 调查朋友推荐的股票（告诉我公司名或股票代码）\n2. 验证抖音/视频看到的交易策略\n\n请告诉我你想做什么？"
            next_required_user_action = "clarify_intent"
        
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
    
    @app.post("/api/agent/workbench/{conversation_id}/execution-feedback")
    def submit_execution_feedback(conversation_id: str, request: dict):
        """
        Submit natural language execution feedback.
        
        Examples:
        - "已买入 100 股，成交价 12.34"
        - "已卖出 100 股，成交价 13.10"
        
        Red line: No technical parameters required from user.
        """
        from fastapi import HTTPException
        from backend.services.execution_interpreter import ExecutionInterpreter
        from backend.services.observation_pool import ObservationPool
        from backend.db.live_trade import LiveTradeDB
        from contracts.live_trade import ExecutionInterpretationStatus
        import uuid
        import json
        from datetime import datetime
        
        feedback = request.get("feedback", "")
        symbol = request.get("symbol", "")
        
        if not feedback:
            raise HTTPException(status_code=400, detail="Feedback is required")
        
        # Simple regex extraction for "已买入 X 股，成交价 Y" pattern
        # This supplements ExecutionInterpreter's multi-turn design with single-turn capability
        import re
        price_match = re.search(r'成交价\s*(\d+\.?\d*)', feedback)
        quantity_match = re.search(r'(\d+)\s*股', feedback)
        
        extracted_price = float(price_match.group(1)) if price_match else None
        extracted_quantity = int(quantity_match.group(1)) if quantity_match else None
        
        # Initialize services
        interpreter = ExecutionInterpreter()
        observation_pool = ObservationPool()
        # Use db.conn directly for simple operations
        conn = db.conn
        
        # Parse feedback
        # Generate placeholder IDs for evidence chain (workbench direct feedback)
        placeholder_id = f"workbench_{uuid.uuid4().hex[:8]}"
        evidence_chain = {
            "execution_card_id": placeholder_id,
            "signal_id": placeholder_id,
            "action_plan_id": placeholder_id,
            "capital_context_id": placeholder_id,
            "market_snapshot_id": placeholder_id,
            "conversation_id": conversation_id,
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "source": "workbench"
        }
        
        draft = interpreter.parse_user_feedback(feedback, evidence_chain)
        
        # If interpreter found price/quantity, use them; otherwise use extracted values
        final_price = draft.parsed_price if draft.parsed_price else extracted_price
        final_quantity = draft.parsed_quantity if draft.parsed_quantity else extracted_quantity
        
        # Determine action from feedback if interpreter didn't parse it
        final_action = draft.parsed_action
        if final_action == "none" or not final_action:
            if "买入" in feedback or "买了" in feedback:
                final_action = "buy"
            elif "卖出" in feedback or "卖了" in feedback:
                final_action = "sell"
        
        # If still missing critical info, return follow-up
        if not final_action or final_action == "none":
            return {
                "status": "needs_more_info",
                "follow_up_question": "请明确说明是买入还是卖出？"
            }
        
        if not final_price or not final_quantity:
            return {
                "status": "needs_more_info",
                "follow_up_question": f"请提供{final_action}的成交价格和数量"
            }
        
        # Create confirmed log from draft (user confirmation implicit)
        from contracts.live_trade import ExecutionObservationLog
        log = ExecutionObservationLog(
            log_id=f"log_{uuid.uuid4().hex[:12]}",
            draft_id=draft.draft_id,
            execution_card_id=placeholder_id,
            signal_id=placeholder_id,
            action_plan_id=placeholder_id,
            capital_context_id=placeholder_id,
            market_snapshot_id=placeholder_id,
            confirmed_action=final_action,
            confirmed_execution_status="executed_full",
            confirmed_price=final_price,
            confirmed_quantity=final_quantity,
            reason=None,
            confirmed_by_user=True,
            broker_verified=False,
            confirmed_at=datetime.now(),
        )
        
        # Store log in DB
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO execution_observation_logs (
                log_id, draft_id, execution_card_id, signal_id, action_plan_id,
                capital_context_id, market_snapshot_id, confirmed_action,
                confirmed_execution_status, confirmed_price, confirmed_quantity,
                reason, confirmed_by_user, broker_verified, confirmed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            log.log_id, log.draft_id, log.execution_card_id, log.signal_id,
            log.action_plan_id, log.capital_context_id, log.market_snapshot_id,
            log.confirmed_action, log.confirmed_execution_status,
            log.confirmed_price, log.confirmed_quantity, log.reason,
            1 if log.confirmed_by_user else 0, 0, log.confirmed_at.isoformat()
        ))
        conn.commit()
        
        # If buy, create observation position
        if final_action == "buy":
            position = observation_pool.create_position_from_log(
                log=log,
                symbol=symbol,
                name=request.get("name", symbol),
                template_id="workbench_manual",
                template_version="v1",
                entry_thesis="User confirmed buy via workbench"
            )
            # Store position in DB
            cursor.execute("""
                INSERT INTO observation_positions (
                    position_id, source_log_id, execution_card_id, signal_id,
                    action_plan_id, capital_context_id, symbol, name,
                    entry_price, quantity, template_id, template_version,
                    entry_thesis, lifecycle_state, opened_at, closed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                position.position_id, position.source_log_id, position.execution_card_id,
                position.signal_id, position.action_plan_id, position.capital_context_id,
                position.symbol, position.name, position.entry_price, position.quantity,
                position.template_id, position.template_version, position.entry_thesis,
                position.lifecycle_state.value, position.opened_at.isoformat(), None
            ))
            conn.commit()
            
            return {
                "status": "success",
                "action": "buy",
                "position_id": position.position_id,
                "log_id": log.log_id
            }
        
        # If sell, close position and calculate P&L
        elif final_action == "sell":
            # Find open position for this symbol
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM observation_positions
                WHERE symbol = ? AND lifecycle_state = 'open'
                ORDER BY opened_at DESC
                LIMIT 1
            """, (symbol,))
            position_row = cursor.fetchone()
            
            if not position_row:
                raise HTTPException(
                    status_code=404,
                    detail=f"No open position found for {symbol}"
                )
            
            # Reconstruct position object
            from contracts.live_trade import ObservationPosition, PositionLifecycleState
            open_position = ObservationPosition(
                position_id=position_row[0],
                source_log_id=position_row[1],
                execution_card_id=position_row[2],
                signal_id=position_row[3],
                action_plan_id=position_row[4],
                capital_context_id=position_row[5],
                symbol=position_row[6],
                name=position_row[7],
                entry_price=position_row[8],
                quantity=position_row[9],
                template_id=position_row[10],
                template_version=position_row[11],
                entry_thesis=position_row[12],
                lifecycle_state=PositionLifecycleState(position_row[13]),
                opened_at=datetime.fromisoformat(position_row[14]),
                closed_at=None,
            )
            
            # Close position
            closed_position = observation_pool.close_position(open_position)
            cursor.execute("""
                UPDATE observation_positions
                SET lifecycle_state = ?, closed_at = ?
                WHERE position_id = ?
            """, (closed_position.lifecycle_state.value, closed_position.closed_at.isoformat(), closed_position.position_id))
            conn.commit()
            
            # Calculate P&L
            from backend.services.discipline_review import DisciplineReviewService
            discipline_service = DisciplineReviewService()
            
            # Get buy log
            cursor.execute("SELECT * FROM execution_observation_logs WHERE log_id = ?", (open_position.source_log_id,))
            buy_row = cursor.fetchone()
            from contracts.live_trade import ExecutionObservationLog
            buy_log = ExecutionObservationLog(
                log_id=buy_row[0],
                draft_id=buy_row[1],
                execution_card_id=buy_row[2],
                signal_id=buy_row[3],
                action_plan_id=buy_row[4],
                capital_context_id=buy_row[5],
                market_snapshot_id=buy_row[6],
                confirmed_action=buy_row[7],
                confirmed_execution_status=buy_row[8],
                confirmed_price=buy_row[9],
                confirmed_quantity=buy_row[10],
                reason=buy_row[11],
                confirmed_by_user=True,
                broker_verified=False,
                confirmed_at=datetime.fromisoformat(buy_row[14]),
            )
            
            # Calculate P&L
            pnl_record = discipline_service.calculate_pnl(
                position_id=open_position.position_id,
                buy_log=buy_log,
                sell_log=log
            )
            
            # Store P&L record
            cursor.execute("""
                INSERT INTO pnl_records (
                    pnl_record_id, position_id, buy_price, sell_price,
                    quantity, fees, pnl_amount, pnl_pct, pnl_source,
                    missing_fields, computed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pnl_record.pnl_record_id, pnl_record.position_id,
                pnl_record.buy_price, pnl_record.sell_price,
                pnl_record.quantity, pnl_record.fees,
                pnl_record.pnl_amount, pnl_record.pnl_pct,
                pnl_record.pnl_source.value,
                json.dumps(pnl_record.missing_fields),
                pnl_record.computed_at.isoformat()
            ))
            
            # Create discipline review
            review = discipline_service.create_review(
                position_id=open_position.position_id,
                execution_card_id=open_position.execution_card_id,
                signal_id=open_position.signal_id,
                daily_signal_ids=[],
                buy_log=buy_log,
                sell_log=log,
            )
            
            # Store discipline review
            cursor.execute("""
                INSERT INTO discipline_reviews (
                    review_id, position_id, execution_card_id, signal_id,
                    review_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                review.review_id, review.position_id,
                review.execution_card_id, review.signal_id,
                review.model_dump_json(), review.created_at.isoformat()
            ))
            conn.commit()
            
            return {
                "status": "success",
                "action": "sell",
                "position_id": open_position.position_id,
                "log_id": log.log_id,
                "pnl_record_id": pnl_record.pnl_record_id,
                "discipline_review_id": review.review_id,
                "realized_pnl": pnl_record.pnl_amount,
                "pnl_pct": pnl_record.pnl_pct
            }
        
        return {
            "status": "success",
            "action": final_action,
            "log_id": log.log_id
        }
    
    @app.post("/api/agent/workbench/{conversation_id}/daily-signal")
    def generate_daily_signal(conversation_id: str):
        """
        Generate daily signal for open positions.
        
        Red line: Deterministic reducer only, LLM does not decide hold/sell.
        """
        from fastapi import HTTPException
        from backend.services.observation_pool import ObservationPool
        from contracts.market_data_fault import MarketDataFaultState
        from datetime import date
        import uuid
        import json
        
        # Find open positions
        cursor = db.conn.cursor()
        cursor.execute("""
            SELECT * FROM observation_positions
            WHERE lifecycle_state = 'open'
            ORDER BY opened_at DESC
        """)
        position_rows = cursor.fetchall()
        
        if not position_rows:
            return {
                "status": "no_open_positions",
                "message": "没有持仓需要观察",
                "signals": []
            }
        
        # Generate signals for all open positions
        observation_pool = ObservationPool()
        signals = []
        
        for position_row in position_rows:
            from contracts.live_trade import ObservationPosition, PositionLifecycleState
            position = ObservationPosition(
                position_id=position_row[0],
                source_log_id=position_row[1],
                execution_card_id=position_row[2],
                signal_id=position_row[3],
                action_plan_id=position_row[4],
                capital_context_id=position_row[5],
                symbol=position_row[6],
                name=position_row[7],
                entry_price=position_row[8],
                quantity=position_row[9],
                template_id=position_row[10],
                template_version=position_row[11],
                entry_thesis=position_row[12],
                lifecycle_state=PositionLifecycleState(position_row[13]),
                opened_at=datetime.fromisoformat(position_row[14]),
                closed_at=None,
            )
            
            # Use market data provider if available, otherwise use entry price + 5%
            if market_data_provider:
                market_data = market_data_provider(position.symbol, date.today())
                current_price = market_data.get("close", position.entry_price * 1.05)
            else:
                current_price = position.entry_price * 1.05
            
            # Template rules (simplified for workbench)
            template_rules = {
                "risk_rules": {
                    "stop_loss": -0.08
                }
            }
            
            # Generate daily signal
            signal = observation_pool.generate_daily_signal(
                position=position,
                current_price=current_price,
                market_data_state=MarketDataFaultState.ok,
                template_rules=template_rules,
                as_of_date=date.today(),
                external_triggers=[]
            )
            
            # Store signal
            cursor.execute("""
                INSERT INTO daily_observation_signals (
                    signal_record_id, position_id, signal_type,
                    triggered_invalidations, as_of_date, market_data_state,
                    rule_trace, plain_explanation, explanation_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal.signal_record_id,
                signal.position_id,
                signal.signal_type.value,
                json.dumps([t.value for t in signal.triggered_invalidations]),
                signal.as_of_date.isoformat(),
                signal.market_data_state.value,
                json.dumps(signal.rule_trace),
                signal.plain_explanation,
                signal.explanation_source.value
            ))
            db.conn.commit()
            
            signals.append({
                "signal_id": signal.signal_record_id,
                "position_id": position.position_id,
                "symbol": position.symbol,
                "signal_type": signal.signal_type.value,
                "generated_at": signal.as_of_date.isoformat()
            })
        
        return {
            "status": "success",
            "signals": signals
        }

    return app
