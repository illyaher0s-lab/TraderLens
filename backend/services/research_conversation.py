"""
Research conversation service.

Handles user messages and produces agent replies with optional proposed actions.

Key behaviors:
- persist user message
- load read-only theme/candidate/evidence context
- call real LLM API through agent harness
- produce agent message
- produce zero or more ProposedAction
- persist pending proposed actions
- link conversation messages to proposed action IDs
- never mutate theme, candidate, evidence, or confirmed pool state during conversation

Conversation messages do not change board state.
Only reducer-applied actions change board state.

CONSTRAINTS:
- Agent can only call whitelisted tools
- Agent cannot directly mutate board state
- Agent can only create ProposedAction
- Missing LLM API key must fail loud, not silent fallback
"""

from __future__ import annotations

import os
import re
import json
from datetime import datetime, timedelta
from typing import Literal

from backend.db.research import ResearchDB
from backend.services.llm_client import LLMClient, ResearchAgentTools
from backend.services.research_validation import ResearchValidator
from contracts.research import (
    ConversationMessage,
    ConversationTurnResult,
    ProposedAction,
    TickerVerificationRecord,
)


class ResearchConversationService:
    """
    Research conversation service.
    
    Two modes:
    - real: Uses LLM API with tool calling (production)
    - deterministic: Simple pattern matching (test fallback)
    """

    def __init__(
        self,
        db: ResearchDB,
        mode: Literal["real", "deterministic"] = "real",
        llm_client: LLMClient | None = None,
        validator: ResearchValidator | None = None,
    ):
        """
        Initialize conversation service.
        
        Args:
            db: Research database
            mode: Conversation mode (real or deterministic)
            llm_client: LLM client (optional, created if None in real mode)
            validator: Research validator (optional, created if None in real mode)
        """
        self.db = db
        self.mode = mode
        
        if mode == "real":
            self.llm_client = llm_client or LLMClient(
                api_key=os.getenv("RESEARCH_LLM_API_KEY"),
            )
            self.validator = validator or ResearchValidator()
        else:
            self.llm_client = None
            self.validator = None

    def process_user_message(
        self, theme_id: str, user_content: str
    ) -> ConversationTurnResult:
        """
        Process a user message and generate agent reply with optional proposed actions.
        
        Args:
            theme_id: Theme ID
            user_content: User message content
        
        Returns:
            ConversationTurnResult with user message, agent message, and proposed actions
        """
        now = datetime.now()

        # Load theme context
        theme = self.db.get_theme(theme_id)
        if not theme:
            raise ValueError(f"Theme {theme_id} not found")

        # Store user message
        user_msg_id = f"msg_user_{now.timestamp()}"
        user_message = ConversationMessage(
            message_id=user_msg_id,
            theme_id=theme_id,
            role="user",
            content=user_content,
            created_at=now,
        )
        self.db.store_conversation_message(user_message)

        # Route to real or deterministic mode
        if self.mode == "real":
            agent_content, proposed_actions = self._process_with_llm(theme, user_content, now)
        else:
            agent_content, proposed_actions = self._process_deterministic(theme, user_content, now)

        # Store agent message
        agent_msg_id = f"msg_agent_{now.timestamp()}"
        action_ids = [a.action_id for a in proposed_actions]
        agent_message = ConversationMessage(
            message_id=agent_msg_id,
            theme_id=theme_id,
            role="agent",
            content=agent_content,
            linked_proposed_action_ids=action_ids,
            created_at=now,
        )
        self.db.store_conversation_message(agent_message)

        return ConversationTurnResult(
            user_message=user_message,
            agent_message=agent_message,
            proposed_actions=proposed_actions,
        )

    def _process_with_llm(
        self, theme, user_content: str, now: datetime
    ) -> tuple[str, list[ProposedAction]]:
        """
        Process user message with real LLM and tool calling.
        
        Returns:
            Tuple of (agent_content, proposed_actions)
        """
        # Build system prompt
        system_prompt = f"""You are a research assistant helping with stock selection research.

Current theme: {theme.theme_name}
Background: {theme.background}
Status: {theme.status}
Board version: {theme.board_version}

Your role:
- Answer user questions about the current theme and candidates
- Help user operate the board by creating ProposedAction cards
- You can ONLY propose actions, not execute them
- User must apply actions from the board

Tools you can use:
- read_theme: Get theme details
- read_candidates: List current candidates
- verify_ticker: Verify stock identity from Tushare (MUST call before adding stock)
- propose_add_candidate: Create ProposedAction to add a stock (after verification)

Important constraints:
- NEVER say "candidate added" or "confirmed" - only say "pending action created"
- NEVER claim state changed - only board shows real state
- ALWAYS verify ticker before proposing to add a stock
- If verification fails or confidence is low, explain the issue and do NOT propose add"""

        # Prepare messages
        messages = [
            {
                "role": "user",
                "content": user_content,
            }
        ]

        # Get tool definitions
        tools = ResearchAgentTools.get_tool_definitions()

        # Call LLM
        try:
            response = self.llm_client.create_message(
                messages=messages,
                system=system_prompt,
                tools=tools,
                max_tokens=4096,
            )
        except Exception:
            return "LLM API error: llm_provider_call_failed", []

        # Process response
        agent_text_parts = []
        proposed_actions = []
        tool_results = []

        for block in response["content"]:
            if block["type"] == "text":
                agent_text_parts.append(block["text"])
            elif block["type"] == "tool_use":
                tool_name = block["name"]
                tool_input = block["input"]
                tool_id = block["id"]

                # Execute tool
                tool_result = self._execute_tool(tool_name, tool_input, theme, now)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps(tool_result, ensure_ascii=False),
                })

                # If tool is propose_add_candidate, create ProposedAction
                if tool_name == "propose_add_candidate" and tool_result.get("success"):
                    action = ProposedAction(
                        action_id=f"action_{now.timestamp()}_{len(proposed_actions)}",
                        action="add_candidate",
                        target_id=theme.theme_id,
                        args={
                            "symbol": tool_input["symbol"],
                            "company_name": tool_result["company_name"],  # From verification record
                            "match_reason": tool_input["match_reason"],
                            "source_type": "manual_stock",
                            "verification_id": tool_result["verification_id"],
                        },
                        rationale=f"User requested to add {tool_input['symbol']} ({tool_result['company_name']})",
                        proposed_by="agent",
                        proposed_at=now,
                        board_version=theme.board_version,
                    )
                    proposed_actions.append(action)
                    self.db.store_proposed_action(action)

        # If there were tool calls, make a second LLM call with tool results
        if tool_results:
            messages.append({
                "role": "assistant",
                "content": response["content"],
            })
            messages.append({
                "role": "user",
                "content": tool_results,
            })

            try:
                final_response = self.llm_client.create_message(
                    messages=messages,
                    system=system_prompt,
                    tools=tools,
                    max_tokens=4096,
                )
                
                # Process final response for text and additional tool calls
                for block in final_response["content"]:
                    if block["type"] == "text":
                        agent_text_parts.append(block["text"])
                    elif block["type"] == "tool_use":
                        # Handle additional tool calls in second turn
                        tool_name = block["name"]
                        tool_input = block["input"]
                        
                        # Execute tool
                        tool_result = self._execute_tool(tool_name, tool_input, theme, now)
                        
                        # If tool is propose_add_candidate, create ProposedAction
                        if tool_name == "propose_add_candidate" and tool_result.get("success"):
                            action = ProposedAction(
                                action_id=f"action_{now.timestamp()}_{len(proposed_actions)}",
                                action="add_candidate",
                                target_id=theme.theme_id,
                                args={
                                    "symbol": tool_input["symbol"],
                                    "company_name": tool_result["company_name"],  # From verification record
                                    "match_reason": tool_input["match_reason"],
                                    "source_type": "manual_stock",
                                    "verification_id": tool_result["verification_id"],
                                },
                                rationale=f"User requested to add {tool_input['symbol']} ({tool_result['company_name']})",
                                proposed_by="agent",
                                proposed_at=now,
                                board_version=theme.board_version,
                            )
                            proposed_actions.append(action)
                            self.db.store_proposed_action(action)
                
            except Exception:
                agent_text_parts.append(
                    "\n(Error getting final response: llm_provider_call_failed)"
                )

        agent_content = "\n".join(agent_text_parts) if agent_text_parts else "我理解了你的消息。"
        return agent_content, proposed_actions

    def _execute_tool(
        self, tool_name: str, tool_input: dict, theme, now: datetime
    ) -> dict:
        """
        Execute a whitelisted tool.
        
        Returns:
            Tool result dict
        """
        if tool_name == "read_theme":
            return {
                "theme_id": theme.theme_id,
                "theme_name": theme.theme_name,
                "background": theme.background,
                "status": theme.status,
                "board_version": theme.board_version,
            }
        
        elif tool_name == "read_candidates":
            candidates = self.db.list_candidates(theme.theme_id)
            return {
                "candidates": [
                    {
                        "symbol": c.symbol,
                        "company_name": c.company_name,
                        "status": c.status,
                        "hard_filter_flags": c.hard_filter_flags,
                    }
                    for c in candidates
                ]
            }
        
        elif tool_name == "verify_ticker":
            symbol = tool_input["symbol"]
            result = self.validator.verify_ticker(symbol)
            
            # Store verification record in DB
            from datetime import timedelta
            from contracts.research import TickerVerificationRecord
            
            verification_record = TickerVerificationRecord(
                verification_id=result.verification_id,
                symbol=result.ticker,
                company_name=result.company_name,
                exchange=result.exchange,
                status=result.status,
                confidence=result.confidence,
                source=result.source,
                notes=result.notes,
                verified_at=result.verified_at,
                expires_at=result.verified_at + timedelta(hours=24),
            )
            self.db.store_ticker_verification(verification_record)
            
            return {
                "verification_id": result.verification_id,
                "symbol": result.ticker,
                "company_name": result.company_name,
                "exchange": result.exchange,
                "status": result.status,
                "confidence": result.confidence,
                "notes": result.notes,
            }
        
        elif tool_name == "propose_add_candidate":
            # Validate verification_id
            symbol = tool_input["symbol"]
            verification_id = tool_input["verification_id"]
            
            # Check verification exists and not expired
            if not self.db.is_verification_valid(verification_id):
                return {
                    "success": False,
                    "error": f"Invalid or expired verification_id: {verification_id}. Call verify_ticker first.",
                }
            
            # Get company name from verification record (NOT from LLM)
            verification_record = self.db.get_ticker_verification(verification_id)
            if not verification_record:
                return {
                    "success": False,
                    "error": f"Verification record not found: {verification_id}",
                }
            
            # Verify symbol matches
            if verification_record.symbol != symbol:
                return {
                    "success": False,
                    "error": f"Symbol mismatch: verification_id {verification_id} is for {verification_record.symbol}, not {symbol}",
                }
            
            return {
                "success": True,
                "message": f"ProposedAction created for {symbol}",
                "verification_id": verification_id,
                "company_name": verification_record.company_name,
            }
        
        else:
            return {
                "error": f"Unknown tool: {tool_name}",
            }

    def _process_deterministic(
        self, theme, user_content: str, now: datetime
    ) -> tuple[str, list[ProposedAction]]:
        """
        Process user message with deterministic pattern matching (test fallback).
        
        Returns:
            Tuple of (agent_content, proposed_actions)
        """
        proposed_actions = []
        agent_content = ""

        # Simple pattern matching for stock addition
        # Support both Chinese and English, with or without dot
        add_stock_pattern = r"(?:添加|add)\s*([A-Z0-9]+\.?[A-Z]*)"
        match = re.search(add_stock_pattern, user_content, re.IGNORECASE)

        if match:
            symbol = match.group(1)
            action_id = f"action_{now.timestamp()}"
            verification_id = f"verify_{action_id}"
            self.db.store_ticker_verification(
                TickerVerificationRecord(
                    verification_id=verification_id,
                    symbol=symbol,
                    company_name=f"Deterministic fixture {symbol}",
                    exchange="SSE" if symbol.endswith(".SH") else "SZSE",
                    status="listed",
                    confidence="high",
                    source="deterministic_test_fixture",
                    notes="Fake identity used only in deterministic test mode",
                    verified_at=now,
                    expires_at=now + timedelta(hours=24),
                )
            )
            action = ProposedAction(
                action_id=action_id,
                action="add_candidate",
                target_id=theme.theme_id,
                args={
                    "symbol": symbol,
                    "verification_id": verification_id,
                    "match_reason": "用户手动添加",
                    "source_type": "manual_stock",
                },
                rationale=f"用户请求添加股票 {symbol}",
                proposed_by="agent",
                proposed_at=now,
                board_version=theme.board_version,
            )
            proposed_actions.append(action)
            self.db.store_proposed_action(action)

            agent_content = f"我已生成一个待审核动作：添加 {symbol} 到候选池。请在右侧看板上点击「应用」来确认。"
        
        elif "主题" in user_content or "什么" in user_content:
            # Information query
            agent_content = f"这是主题「{theme.theme_name}」。{theme.background}"
        
        else:
            # Default response
            agent_content = "我理解了你的消息。如果你想添加股票，请使用格式：添加 [股票代码]（如：添加 300750.SZ）"

        return agent_content, proposed_actions
