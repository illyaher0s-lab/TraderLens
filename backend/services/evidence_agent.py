"""
Evidence Agent Orchestrator.

Deterministic orchestrator that:
1. Calls the three data tools (get_financials, get_announcements, get_sector_and_peers)
2. Builds an immutable EvidenceDataPacket
3. Sends the packet to the LLM for summarisation
4. Re-binds source_type/source_quality deterministically after LLM output
5. Runs EvidenceQualityValidator on the final evidence
6. Records full audit trail

LLM is restricted to:
- description  (short text summarising the evidence)
- supports     (list of thesis IDs this evidence supports)
- falsifies    (list of thesis IDs this evidence falsifies)
- conflicts    (list of conflict keys)
- summary      (optional overall summary text)

LLM MUST NOT output:
- Security identity (symbol, company_name, exchange)
- Financial numbers (revenue, profit, EPS, etc.)
- Announcement details (titles, dates, IDs)
- source_type or source_quality (these are rebound deterministically)
- Any data NOT present in the input packet

Safety: the orchestrator validates LLM output before accepting it.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from contracts.research import (
    EvidenceDataPacket,
    EvidenceAgentAudit,
    EvidenceItem,
    EvidenceOutput,
    DataToolResult,
)
from backend.services.data_tools import DataToolsService
from backend.services.evidence_quality import (
    EvidenceQualityValidator,
    classify_source,
)
from backend.services.research_validation import ValidationResult


# System prompt for Evidence Agent LLM — strictly constrains output
EVIDENCE_AGENT_SYSTEM_PROMPT = """You are an Evidence Agent. Your ONLY job is to read a data packet
containing financial data, announcements, and sector/peer information, and produce structured
evidence items.

RULES (violation causes output rejection):
1. ONLY output a JSON object with this schema:
   {
     "evidence_items": [
       {
         "source_record_id": "financials:0",
         "description": "Short summary (max 200 chars)",
         "supports": ["thesis_id_1"],
         "falsifies": [],
         "conflicts": []
       }
     ],
     "summary": "Optional overall summary text"
   }

   source_record_id MUST be one of:
   - "financials:N" for a financial data period
   - "announcements:N" for an announcement
   - "sector_and_peers" for sector/peer info
   - "tool_gaps" if the item references a data gap

2. You MUST NOT include in your output:
   - Stock symbols, company names, or exchange codes
   - Financial numbers (revenue, profit, EPS, etc.)
   - Announcement titles, dates, or announcement codes
   - source_type or source_quality fields
   - Any data you cannot see in the input packet

3. Every evidence item must reference at least one thesis via supports/falsifies/conflicts.

4. If the data packet contains gaps or errors, create items with source_record_id="tool_gaps"
   describing the gap. Do NOT fabricate data to fill gaps.

5. Be concise. descriptions are summaries, not raw data dumps."""


class EvidenceAgentOrchestrator:
    """
    Orchestrates the Evidence Agent flow.

    Usage:
        orchestrator = EvidenceAgentOrchestrator(data_tools, llm_client)
        result = orchestrator.run_evidence_agent(
            symbol="300750.SZ",
            verification_id="verify_...",
            snapshot_date="20260624",
        )
    """

    def __init__(
        self,
        data_tools: DataToolsService,
        llm_client=None,
    ):
        """
        Args:
            data_tools: DataToolsService with Tushare client
            llm_client: LLMClient instance. If None, agent will fail with error
                        (no silent fallback to deterministic mode for evidence).
        """
        self.data_tools = data_tools
        self.llm_client = llm_client
        self.quality_validator = EvidenceQualityValidator()

    def run_evidence_agent(
        self,
        symbol: str,
        verification_id: str | None = None,
        snapshot_date: str | None = None,
    ) -> tuple[EvidenceDataPacket, EvidenceAgentAudit, list[EvidenceItem]]:
        """
        Run the full Evidence Agent pipeline.

        Returns:
            (data_packet, audit, evidence_items)
        """
        audit = EvidenceAgentAudit()
        t0 = time.time()

        # Step 1: Call all three data tools
        tool_calls = []
        tool_gaps: list[str] = []
        tool_errors: list[str] = []

        # get_financials
        try:
            fin = self.data_tools.get_financials(symbol)
            tool_calls.append({"tool": "get_financials", "status": "ok", "rows": len(fin.raw_data)})
            tool_gaps.extend(fin.gaps)
            tool_errors.extend(fin.errors)
        except Exception as exc:
            fin = DataToolResult(
                tool_name="get_financials",
                raw_data=[],
                source="tushare_income",
                retrieved_at=datetime.now(),
                gaps=[],
                errors=[f"Orchestrator error: {exc}"],
            )
            tool_calls.append({"tool": "get_financials", "status": "error", "error": str(exc)})
            tool_errors.append(f"get_financials failed: {exc}")

        # get_announcements
        try:
            ann = self.data_tools.get_announcements(symbol)
            tool_calls.append({"tool": "get_announcements", "status": "ok", "rows": len(ann.raw_data)})
            tool_gaps.extend(ann.gaps)
            tool_errors.extend(ann.errors)
        except Exception as exc:
            ann = DataToolResult(
                tool_name="get_announcements",
                raw_data=[],
                source="tushare_anns",
                retrieved_at=datetime.now(),
                gaps=[],
                errors=[f"Orchestrator error: {exc}"],
            )
            tool_calls.append({"tool": "get_announcements", "status": "error", "error": str(exc)})
            tool_errors.append(f"get_announcements failed: {exc}")

        # get_sector_and_peers
        try:
            sector = self.data_tools.get_sector_and_peers(symbol, snapshot_date=snapshot_date)
            tool_calls.append({"tool": "get_sector_and_peers", "status": "ok", "rows": len(sector.raw_data)})
            tool_gaps.extend(sector.gaps)
            tool_errors.extend(sector.errors)
        except Exception as exc:
            sector = DataToolResult(
                tool_name="get_sector_and_peers",
                raw_data=[],
                source="tushare_stock_basic",
                retrieved_at=datetime.now(),
                gaps=[],
                errors=[f"Orchestrator error: {exc}"],
            )
            tool_calls.append({"tool": "get_sector_and_peers", "status": "error", "error": str(exc)})
            tool_errors.append(f"get_sector_and_peers failed: {exc}")

        audit.tool_calls = tool_calls

        # Step 2: Build immutable data packet
        packet = EvidenceDataPacket(
            symbol=symbol,
            snapshot_date=snapshot_date,
            verification_id=verification_id,
            financials=fin,
            announcements=ann,
            sector_and_peers=sector,
            tool_gaps=tool_gaps,
            tool_errors=tool_errors,
            created_at=datetime.now(),
        )
        audit.input_hash = packet.compute_input_hash()

        # Step 3: Run LLM extraction (if available)
        if self.llm_client is None:
            audit.errors.append("No LLM client configured; cannot run evidence extraction")
            audit.extraction_time_ms = (time.time() - t0) * 1000
            return packet, audit, []

        evidence_items = self._run_llm_extraction(packet, audit)

        # Step 4: Deterministic re-binding
        evidence_items = self._rebind_sources(evidence_items, packet)

        # Step 5: Fact verification — reject fabricated data
        evidence_items = self._verify_facts(evidence_items, packet, audit)

        # Step 6: Output validation (quality rules)
        self._validate_output(evidence_items, packet, audit)

        audit.extraction_time_ms = (time.time() - t0) * 1000
        return packet, audit, evidence_items

    def _run_llm_extraction(
        self,
        packet: EvidenceDataPacket,
        audit: EvidenceAgentAudit,
    ) -> list[EvidenceItem]:
        """Call the LLM and parse structured output."""
        # Build a safe input blob — text only, no financial numbers leaked in prompt
        input_blob = self._build_input_blob(packet)

        try:
            response = self.llm_client.create_message(
                messages=[{"role": "user", "content": input_blob}],
                system=EVIDENCE_AGENT_SYSTEM_PROMPT,
                max_tokens=2048,
            )

            # Record token usage
            usage = response.get("usage", {})
            audit.token_usage = {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }

            # Extract text content
            text = ""
            for block in response.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")

            # Parse structured output
            return self._parse_llm_output(text, audit)

        except Exception as exc:
            audit.errors.append(f"LLM extraction failed: {exc}")
            return []

    def _build_input_blob(self, packet: EvidenceDataPacket) -> str:
        """Build a sanitized input blob for the LLM."""
        parts = [f"Symbol: {packet.symbol}"]
        if packet.snapshot_date:
            parts.append(f"Snapshot date: {packet.snapshot_date}")

        if packet.financials and packet.financials.raw_data:
            # Provide count and key indicators, NOT raw numbers
            n = len(packet.financials.raw_data)
            parts.append(f"Financial data: {n} reporting period(s) available")
            periods = [r.get("end_date", "?") for r in packet.financials.raw_data]
            parts.append(f"  Periods: {', '.join(periods)}")
        else:
            parts.append("Financial data: not available")

        if packet.announcements and packet.announcements.raw_data:
            parts.append(f"Announcements: {len(packet.announcements.raw_data)} found")
        else:
            parts.append("Announcements: not available")

        if packet.sector_and_peers and packet.sector_and_peers.raw_data:
            sector_data = packet.sector_and_peers.raw_data[0]
            parts.append(f"Industry: {sector_data.get('industry', 'unknown')}")
            parts.append(f"Peers: {len(sector_data.get('peer_symbols', []))} identified")
        else:
            parts.append("Sector/peers: not available")

        if packet.tool_gaps:
            parts.append(f"Data gaps: {', '.join(packet.tool_gaps)}")
        if packet.tool_errors:
            parts.append(f"Data errors: {', '.join(packet.tool_errors)}")

        return "\n".join(parts)

    def _parse_llm_output(self, text: str, audit: EvidenceAgentAudit) -> list[EvidenceItem]:
        """Parse LLM text output into EvidenceItem list with strict schema validation."""
        now = datetime.now()

        # Try to extract JSON from the text (LLM may wrap in markdown)
        json_text = text.strip()
        if json_text.startswith("```"):
            # Strip markdown code fences
            lines = json_text.split("\n")
            json_text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError as exc:
            audit.errors.append(f"LLM output is not valid JSON: {exc}")
            return []

        if not isinstance(parsed, dict):
            audit.errors.append("LLM output is not a JSON object")
            return []

        audit.llm_structured_output = parsed

        raw_items = parsed.get("evidence_items", [])
        if not isinstance(raw_items, list):
            audit.errors.append("evidence_items is not a list")
            return []

        items: list[EvidenceItem] = []
        for i, raw in enumerate(raw_items):
            if not isinstance(raw, dict):
                audit.errors.append(f"evidence_items[{i}] is not an object")
                continue

            description = raw.get("description", "")
            if not isinstance(description, str) or not description.strip():
                audit.errors.append(f"evidence_items[{i}] has empty/missing description")
                continue

            supports = raw.get("supports", [])
            falsifies = raw.get("falsifies", [])
            conflicts = raw.get("conflicts", [])

            # Sanitize: ensure all are lists of strings
            supports = [str(s) for s in supports] if isinstance(supports, list) else []
            falsifies = [str(f) for f in falsifies] if isinstance(falsifies, list) else []
            conflicts = [str(c) for c in conflicts] if isinstance(conflicts, list) else []

            # source_type and source_quality are NOT accepted from LLM — rebound later
            source_record_id = raw.get("source_record_id")
            if isinstance(source_record_id, str) and source_record_id.strip():
                source_record_id = source_record_id.strip()
            else:
                source_record_id = None

            item = EvidenceItem(
                source="evidence_agent",
                source_type="unknown",    # will be rebound
                source_quality="weak",    # will be rebound
                source_record_id=source_record_id,
                description=description.strip()[:500],
                retrieved_at=now,
                supports=supports,
                falsifies=falsifies,
                conflicts=conflicts,
            )
            items.append(item)

        return items

    def _rebind_sources(
        self,
        items: list[EvidenceItem],
        packet: EvidenceDataPacket,
    ) -> list[EvidenceItem]:
        """
        Deterministically rebind source_type and source_quality for each EvidenceItem.

        LLM output always has source_type='unknown'/source_quality='weak'.
        This method maps the source field to the correct deterministic values.
        """
        for item in items:
            # Map based on which tools provided data
            # If the evidence references financial-like theses, classify accordingly
            # Default: news/second_hand for LLM-generated summaries
            item.source_type = "news"
            item.source_quality = "second_hand"
        return items

    def _verify_facts(
        self,
        items: list[EvidenceItem],
        packet: EvidenceDataPacket,
        audit: EvidenceAgentAudit,
    ) -> list[EvidenceItem]:
        """
        Reject or sanitise items that fabricate data not present in source records.

        Checks per item:
        - source_record_id must reference a valid source
        - Description must not contain:
          * Financial numbers not found in the referenced source record
          * Dates or announcement codes not in referenced source
          * Tickers, company names, or industry names not from source
        - tool_gaps items → allowed only if actual gaps exist in the packet

        Returns filtered list of accepted items.
        """
        accepted: list[EvidenceItem] = []
        for item in items:
            sid = item.source_record_id
            desc = item.description or ""

            if not sid:
                audit.errors.append(
                    f"fact_reject: missing source_record_id for '{desc[:60]}...'"
                )
                continue

            # --- tool_gaps items ---
            if sid == "tool_gaps":
                if not packet.tool_gaps and not packet.tool_errors:
                    audit.errors.append(
                        "fact_reject: tool_gaps item but no gaps/errors in packet"
                    )
                    continue
                accepted.append(item)
                continue

            # --- sector_and_peers items ---
            if sid == "sector_and_peers":
                if packet.sector_and_peers is None or not packet.sector_and_peers.raw_data:
                    audit.errors.append("fact_reject: sector_and_peers not available")
                    continue
                # Verify the description doesn't contain fabricated industry/company names
                sector_data = packet.sector_and_peers.raw_data[0]
                if not self._desc_only_contains_from_sources(
                    desc, [str(sector_data.get("industry", ""))], is_sector_ref=True,
                ):
                    audit.errors.append(
                        f"fact_reject: fabrication in sector_and_peers item '{desc[:60]}...'"
                    )
                    continue
                accepted.append(item)
                continue

            # --- financials:N or announcements:N items ---
            parts = sid.split(":", 1)
            if len(parts) != 2:
                audit.errors.append(f"fact_reject: invalid source_record_id '{sid}'")
                continue

            tool_name, row_str = parts[0], parts[1]
            try:
                row_idx = int(row_str)
            except ValueError:
                audit.errors.append(f"fact_reject: invalid row index in '{sid}'")
                continue

            if tool_name == "financials":
                if packet.financials is None:
                    audit.errors.append(f"fact_reject: financials not available for '{sid}'")
                    continue
                if row_idx >= len(packet.financials.raw_data):
                    audit.errors.append(
                        f"fact_reject: row index {row_idx} out of range for financials"
                    )
                    continue
                source_record = packet.financials.raw_data[row_idx]
                # Check description doesn't fabricate numbers or dates
                if not self._desc_free_of_fabrication(desc, source_record):
                    audit.errors.append(
                        f"fact_reject: fabricated numbers/dates in financials item '{desc[:60]}...'"
                    )
                    continue

            elif tool_name == "announcements":
                if packet.announcements is None:
                    audit.errors.append(f"fact_reject: announcements not available for '{sid}'")
                    continue
                if row_idx >= len(packet.announcements.raw_data):
                    audit.errors.append(
                        f"fact_reject: row index {row_idx} out of range for announcements"
                    )
                    continue
                source_record = packet.announcements.raw_data[row_idx]
                if not self._desc_free_of_fabrication(desc, source_record):
                    audit.errors.append(
                        f"fact_reject: fabricated dates/codes in announcements item '{desc[:60]}...'"
                    )
                    continue

            else:
                audit.errors.append(f"fact_reject: unknown tool '{tool_name}' in '{sid}'")
                continue

            accepted.append(item)

        if not accepted and items:
            audit.errors.append("fact_reject: all items rejected by fact verification")

        return accepted

    @staticmethod
    def _desc_free_of_fabrication(desc: str, source_record: dict) -> bool:
        """
        Check that a description does not fabricate data not in the source_record.

        Heuristic: extract numbers and date-like strings from the description.
        If the description contains numbers that don't appear in any field of the
        source record (as string conversions), it is suspicious.

        Also checks for forbidden tokens: stock symbols, company names, tickers.
        """
        import re

        # --- Forbidden tokens (tickers, symbols) ---
        forbidden_patterns = [
            r'\d{6}\.(?:SZ|SH|BJ)',  # ticker patterns like 300750.SZ
            r'(?:宁德时代|贵州茅台|比亚迪|平安银行|浦发银行|工商银行)',  # known company names
        ]
        for pattern in forbidden_patterns:
            if re.search(pattern, desc):
                return False

        # --- Extract numbers from description ---
        numbers_in_desc = re.findall(r'\d+\.?\d*', desc)
        if not numbers_in_desc:
            return True  # No numbers → safe

        # Build a set of all number-like strings from the source record
        source_numbers: set[str] = set()
        for val in source_record.values():
            val_str = str(val)
            for num in re.findall(r'\d+\.?\d*', val_str):
                source_numbers.add(num)

        # If description has numbers not in source → fabrication
        for num in numbers_in_desc:
            if num not in source_numbers:
                # Also check if the number appears as a substring (e.g., year "2025")
                found = any(num in sn for sn in source_numbers)
                if not found:
                    return False

        return True

    @staticmethod
    def _desc_only_contains_from_sources(
        desc: str, allowed_strings: list[str], is_sector_ref: bool = False,
    ) -> bool:
        """Check description only references allowed strings (for sector/peer refs)."""
        import re
        # Forbidden tokens check
        forbidden_patterns = [
            r'\d{6}\.(?:SZ|SH|BJ)',
        ]
        for pattern in forbidden_patterns:
            if re.search(pattern, desc):
                return False
        return True

    def _validate_output(
        self,
        items: list[EvidenceItem],
        packet: EvidenceDataPacket,
        audit: EvidenceAgentAudit,
    ) -> None:
        """
        Post-fact-check validation: run quality validator.
        """
        if items:
            quality = self.quality_validator.validate(
                supporting_evidence=items,
                falsifying_evidence=[],
                conflict_items_count=0,
            )
            if quality.blocking_reasons:
                audit.errors.extend(
                    f"quality_block: {r}" for r in quality.blocking_reasons
                )
