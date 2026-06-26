"""
LLM Client for Research Conversation Agent.

Connects to cc-vibe.com API with Anthropic-compatible interface.
Supports tool calling for whitelisted research tools.

CONSTRAINTS:
- Agent can only call whitelisted tools
- Agent cannot directly mutate board state
- Agent can only create ProposedAction
- Missing API key must fail loud, not silent fallback
"""

from __future__ import annotations

import os
import json
from typing import Any, Literal
from anthropic import Anthropic


class LLMClient:
    """
    LLM client for research conversation agent.
    
    Uses Anthropic SDK with custom base URL.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://cc-vibe.com",
        model: str = "claude-sonnet-4-6",
    ):
        """
        Initialize LLM client.
        
        Args:
            api_key: API key (loads from RESEARCH_LLM_API_KEY env var if None)
            base_url: API base URL
            model: Model name
        
        Raises:
            ValueError: If API key is missing
        """
        self.api_key = api_key or os.getenv("RESEARCH_LLM_API_KEY")
        if not self.api_key:
            raise ValueError(
                "LLM API key not configured. "
                "Set RESEARCH_LLM_API_KEY environment variable or pass api_key explicitly."
            )
        
        self.base_url = base_url
        self.model = model
        
        self.client = Anthropic(
            api_key=self.api_key,
            base_url=base_url,
        )

    def create_message(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """
        Create a message with the LLM.
        
        Args:
            messages: Conversation messages
            system: System prompt
            tools: Tool definitions
            max_tokens: Maximum tokens to generate
        
        Returns:
            Response dict with content, tool_use, and usage
        
        Raises:
            ValueError: If API call fails
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                messages=messages,
                system=system,
                tools=tools,
                max_tokens=max_tokens,
            )
            
            # Convert response to dict
            result = {
                "id": response.id,
                "model": response.model,
                "role": response.role,
                "content": [],
                "stop_reason": response.stop_reason,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            }
            
            # Extract content blocks
            for block in response.content:
                if block.type == "text":
                    result["content"].append({
                        "type": "text",
                        "text": block.text,
                    })
                elif block.type == "tool_use":
                    result["content"].append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
            
            return result
        
        except Exception as exc:
            raise ValueError(f"LLM API call failed: {exc}") from exc
    
    def get_provider_name(self) -> str:
        """Get the provider name for audit metadata."""
        # Extract provider from base_url
        if "cc-vibe.com" in self.base_url:
            return "cc-vibe"
        elif "anthropic.com" in self.base_url:
            return "anthropic"
        else:
            return "custom"
    
    def get_model_name(self) -> str:
        """Get the model name for audit metadata."""
        return self.model


class ResearchAgentTools:
    """
    Whitelisted tools for research conversation agent.
    
    Agent can ONLY call these tools.
    Agent CANNOT directly mutate board state.
    """

    @staticmethod
    def get_tool_definitions() -> list[dict[str, Any]]:
        """
        Get tool definitions for LLM.
        
        Returns:
            List of tool definitions in Anthropic format
        """
        return [
            {
                "name": "read_theme",
                "description": "Read current theme summary including name, background, status, and board_version.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "theme_id": {
                            "type": "string",
                            "description": "Theme ID",
                        },
                    },
                    "required": ["theme_id"],
                },
            },
            {
                "name": "read_candidates",
                "description": "Read current candidates for a theme, including symbols, status, and hard_filter_flags.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "theme_id": {
                            "type": "string",
                            "description": "Theme ID",
                        },
                    },
                    "required": ["theme_id"],
                },
            },
            {
                "name": "verify_ticker",
                "description": "Verify ticker/company/exchange identity from Tushare data source. Returns company name, exchange, listing status, and confidence level. MUST be called before proposing to add a stock.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock symbol (e.g., '300750.SZ', '600519.SH')",
                        },
                    },
                    "required": ["symbol"],
                },
            },
            {
                "name": "propose_add_candidate",
                "description": "Propose adding a candidate stock to the theme. Creates a ProposedAction that user must apply from the board. MUST call verify_ticker first and pass the verification_id.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "theme_id": {
                            "type": "string",
                            "description": "Theme ID",
                        },
                        "symbol": {
                            "type": "string",
                            "description": "Stock symbol (verified)",
                        },
                        "verification_id": {
                            "type": "string",
                            "description": "Verification ID from verify_ticker tool (REQUIRED)",
                        },
                        "match_reason": {
                            "type": "string",
                            "description": "Why this stock matches the theme",
                        },
                    },
                    "required": ["theme_id", "symbol", "verification_id", "match_reason"],
                },
            },
        ]
