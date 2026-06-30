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
) -> FastAPI:
    """
    Create Research API app.
    
    Args:
        db: Research database (if None, creates default)
        conversation_mode: Conversation mode ("real" or "deterministic", default "deterministic")
        serenity_execution_mode: Serenity execution mode ("stub" or "two_phase", default "stub")
        validator: ResearchValidator (if None, creates default with env config)
        serenity_runner: SerenityRunner (if provided, must match mode constraints)
    
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
        
        # Check LLM API key
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
    conversation = ResearchConversationService(db, mode=conversation_mode)
    
    # Build or validate Serenity runner
    if serenity_runner is not None:
        # Validate injected runner matches mode constraints
        from backend.services.serenity_stub import SerenityStubRunner
        from backend.services.serenity_agent import SerenityAgentRunner
        
        if conversation_mode == "real":
            # Must be SerenityAgentRunner with exact mode and execution_mode
            if not isinstance(serenity_runner, SerenityAgentRunner):
                raise ValueError(
                    f"conversation_mode='real' requires SerenityAgentRunner, "
                    f"but got {type(serenity_runner).__name__}. "
                    "Remove serenity_runner parameter or provide a real SerenityAgentRunner."
                )
            if serenity_runner.mode != "real":
                raise ValueError(
                    f"conversation_mode='real' requires SerenityAgentRunner with mode='real', "
                    f"but got mode='{serenity_runner.mode}'."
                )
            if serenity_runner.execution_mode != "two_phase":
                raise ValueError(
                    f"conversation_mode='real' requires SerenityAgentRunner with execution_mode='two_phase', "
                    f"but got execution_mode='{serenity_runner.execution_mode}'."
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
        result = conversation.process_user_message(
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
        
        result = flow_service.resolve_ambiguous_ticker(
            flow_id=flow_id,
            chosen_ticker=request.chosen_ticker,
            original_candidates=original_candidates,
        )
        
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
        
        research_output = flow_service.run_industry_research(
            ticker=ticker,
            company_name=company_name,
        )
        
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
        
        if request.name != verification_result.get("resolved_name"):
            raise HTTPException(
                status_code=400,
                detail=f"Request name '{request.name}' does not match verified name '{verification_result.get('resolved_name')}'"
            )
        
        if request.exchange != verification_result.get("exchange"):
            raise HTTPException(
                status_code=400,
                detail=f"Request exchange '{request.exchange}' does not match verified exchange '{verification_result.get('exchange')}'"
            )
        
        research_output = flow_state.get("research_output")
        if not research_output:
            raise HTTPException(status_code=400, detail="Research not completed for this flow")
        
        # Market data unavailable blocks pool creation
        raise HTTPException(
            status_code=503,
            detail="Market data adapter unavailable. Cannot create pool without live price snapshot."
        )
        
        # Note: The code below would execute if market data were available
        # Wire services
        # if conversation_mode == "real" and hasattr(serenity_runner, 'run'):
        #     serenity = serenity_runner
        # else:
        #     serenity = None
        #
        # flow_service = FriendStockFlowService(
        #     validator=validator,
        #     serenity_runner=serenity,
        #     market_data_provider=real_market_data_provider,  # Must be real, not mock
        # )
        #
        # # Parse snapshot date
        # snapshot_date = date.fromisoformat(request.snapshot_date)
        #
        # pool = flow_service.create_confirmed_pool(
        #     flow_id=flow_id,
        #     ticker=request.ticker,
        #     name=request.name,
        #     exchange=request.exchange,
        #     approval_card_id=request.approval_card_id,
        #     research_output=research_output,
        #     snapshot_date=snapshot_date,
        # )
        #
        # # Persist to DB with real verification_id
        # confirmed = db.confirm_candidate(
        #     candidate_id="cand_" + pool.pool_id,
        #     confirmation_reason="Friend recommendation approved",
        #     evidence_level="medium",
        #     confirmed_by="user",
        #     pool_snapshot_date=pool.confirmation_date.date(),
        #     thesis_snapshot=pool.thesis_snapshot,
        #     invalidation_rules=pool.invalidation_rules,
        #     price_snapshot=pool.price_snapshot,
        #     benchmark_snapshot=pool.benchmark_snapshot,
        #     evidence_snapshot_ids=pool.evidence_snapshot_ids,
        #     primary_evidence_snapshot_id=None,
        # )
        #
        # return pool.model_dump()

    return app
