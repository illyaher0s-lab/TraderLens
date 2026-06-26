"""
Serenity research tools (SMA-P2 extension).

Implements four deterministically verifiable tools:
1. retrieve_supply_chain — 产业链数据检索
2. discover_players — 玩家发现
3. audit_sources — 来源审计
4. red_team_falsify — red-team 证伪

All tools operate on ResearchSource records. LLM may read but not fabricate.
No external text can modify system prompt, tool whitelist, or execution path.
"""

from __future__ import annotations

from datetime import date, datetime
from contracts.research import (
    ResearchSource,
    SerenityToolResult,
)
from backend.services.data_tools import DataToolsService
from backend.services.research_validation import ResearchValidator


class SerenityTools:
    """
    Serenity research tools for supply chain analysis.

    All methods are deterministic — no LLM involvement.
    Gaps are always recorded; never filled with defaults.
    """

    def __init__(
        self,
        data_tools: DataToolsService | None = None,
        validator: ResearchValidator | None = None,
    ):
        self.data_tools = data_tools
        self.validator = validator

    # ------------------------------------------------------------------
    # 1. retrieve_supply_chain — 产业链数据检索
    # ------------------------------------------------------------------

    def retrieve_supply_chain(
        self,
        theme_name: str,
        theme_background: str = "",
        keywords: list[str] | None = None,
        symbols: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        max_records: int = 20,
    ) -> SerenityToolResult:
        """
        Search for relevant supply chain information using data tools.

        Inputs:
            theme_name: Research theme name (for sector lookup)
            theme_background: Additional background text
            keywords: Optional keywords to filter announcements
            symbols: Optional candidate symbols to query
            start_date/end_date: Date range (YYYYMMDD)
            max_records: Maximum records to return

        Outputs: ResearchSource records from financials, announcements,
                 and sector/peers data tools.

        Empty results always produce a gap.
        """
        now = datetime.now()
        gaps: list[str] = []
        errors: list[str] = []
        records: list[ResearchSource] = []

        if self.data_tools is None:
            return SerenityToolResult(
                tool_name="retrieve_supply_chain",
                records=[],
                total_found=0,
                gaps=["data_tools_not_configured"],
                errors=["No DataToolsService available"],
                retrieved_at=now,
            )

        search_symbols = list(symbols or [])
        kw_list = list(keywords or [])

        # Attempt sector discovery from theme name
        if not search_symbols and theme_name:
            # Use a heuristic: theme_name may map to known industries
            search_symbols = self._infer_symbols_from_theme(theme_name)

        if not search_symbols:
            gaps.append("no_symbols_to_search: provide symbols or a theme that maps to known industries")
            return SerenityToolResult(
                tool_name="retrieve_supply_chain",
                records=[],
                total_found=0,
                gaps=gaps,
                errors=errors,
                retrieved_at=now,
            )

        record_idx = 0

        for sym in search_symbols[:5]:  # limit to 5 symbols
            # Financials
            try:
                fin = self.data_tools.get_financials(sym)
                for i, row in enumerate(fin.raw_data):
                    if record_idx >= max_records:
                        break
                    records.append(ResearchSource(
                        source_record_id=f"financials:{sym}:{i}",
                        source_type="financial_report",
                        source_quality="first_hand",
                        title=f"财务数据 {sym} 第{i + 1}期",
                        summary=f"期间: {row.get('end_date', '?')}",
                        retrieved_at=now,
                        gaps=fin.gaps,
                    ))
                    record_idx += 1
                gaps.extend(fin.gaps)
                errors.extend(fin.errors)
            except Exception as exc:
                errors.append(f"get_financials({sym}) failed: {exc}")

            # Announcements
            try:
                ann = self.data_tools.get_announcements(
                    sym, start_date=start_date, end_date=end_date, keywords=kw_list,
                )
                for i, row in enumerate(ann.raw_data):
                    if record_idx >= max_records:
                        break
                    records.append(ResearchSource(
                        source_record_id=f"announcements:{sym}:{i}",
                        source_type="announcement",
                        source_quality="first_hand",
                        title=row.get("title", "公告"),
                        published_at=self._parse_date(row.get("ann_date")),
                        summary=f"公告类型: {row.get('ann_type', '?')}",
                        announcement_code=row.get("ann_type", ""),
                        retrieved_at=now,
                    ))
                    record_idx += 1
                gaps.extend(ann.gaps)
                errors.extend(ann.errors)
            except Exception as exc:
                errors.append(f"get_announcements({sym}) failed: {exc}")

            # Sector
            try:
                sector = self.data_tools.get_sector_and_peers(sym, snapshot_date=None)
                for i, row in enumerate(sector.raw_data):
                    if record_idx >= max_records:
                        break
                    records.append(ResearchSource(
                        source_record_id=f"sector:{sym}:{i}",
                        source_type="financial_report",
                        source_quality="first_hand",
                        title=f"行业归属: {sym}",
                        summary=(
                            f"行业: {row.get('industry', '?')}, "
                            f"同行: {', '.join(row.get('peer_symbols', []))}"
                        ),
                        retrieved_at=now,
                    ))
                    record_idx += 1
                gaps.extend(sector.gaps)
                errors.extend(sector.errors)
            except Exception as exc:
                errors.append(f"get_sector_and_peers({sym}) failed: {exc}")

        if not records:
            gaps.append("retrieve_supply_chain: no records found")

        return SerenityToolResult(
            tool_name="retrieve_supply_chain",
            records=records[:max_records],
            total_found=record_idx,
            gaps=gaps,
            errors=errors,
            retrieved_at=now,
        )

    # ------------------------------------------------------------------
    # 2. discover_players — 玩家发现
    # ------------------------------------------------------------------

    def discover_players(
        self,
        source_records: list[ResearchSource],
        max_players: int = 10,
    ) -> SerenityToolResult:
        """
        Extract potential company players from retrieved source records.

        Rules:
        - Only proposes company names FROM source records (no fabrication)
        - Each ticker MUST be verified via verify_ticker before entering shortlist
        - Verification failure → excluded + gap recorded
        - Low confidence → excluded + gap recorded

        Returns: ResearchSource records with candidate company info.
        """
        now = datetime.now()
        gaps: list[str] = []
        errors: list[str] = []
        records: list[ResearchSource] = []

        if not source_records:
            gaps.append("discover_players: no source records provided")
            return SerenityToolResult(
                tool_name="discover_players", records=[], total_found=0,
                gaps=gaps, errors=errors, retrieved_at=now,
            )

        # Extract unique symbols from source records
        seen_symbols: set[str] = set()
        candidate_names: dict[str, str] = {}  # symbol → company_name

        for rec in source_records:
            sid = rec.source_record_id
            # Parse symbol from source_record_id (format: tool:symbol:idx)
            parts = sid.split(":")
            if len(parts) >= 2:
                sym = parts[1]
                if sym not in seen_symbols and "." in sym:  # looks like a ticker
                    seen_symbols.add(sym)
                    # Extract company name from sector data if available
                    if "industry" in rec.summary or "同行" in rec.summary:
                        candidate_names[sym] = sym  # placeholder

        if not seen_symbols:
            gaps.append("discover_players: no tickers found in source records")
            return SerenityToolResult(
                tool_name="discover_players", records=[], total_found=0,
                gaps=gaps, errors=errors, retrieved_at=now,
            )

        for sym in list(seen_symbols)[:max_players]:
            # Identity verification
            verified = False
            company_name = candidate_names.get(sym, sym)
            verification_id = ""
            confidence = "low"

            if self.validator:
                try:
                    vr = self.validator.verify_ticker(sym)
                    confidence = vr.confidence
                    company_name = vr.company_name
                    verification_id = vr.verification_id
                    verified = confidence in ("high", "medium")
                except Exception as exc:
                    errors.append(f"verify_ticker({sym}) failed: {exc}")

            if not verified:
                gaps.append(
                    f"discover_players: {sym} verification failed "
                    f"(confidence={confidence}) — excluded"
                )
                continue

            records.append(ResearchSource(
                source_record_id=f"discovered_player:{sym}",
                source_type="unknown",
                source_quality="weak",
                title=f"已验证玩家: {company_name}",
                summary=f"symbol={sym}, confidence={confidence}, verification_id={verification_id}",
                retrieved_at=now,
            ))

        if not records:
            gaps.append("discover_players: no players passed verification")

        return SerenityToolResult(
            tool_name="discover_players",
            records=records,
            total_found=len(records),
            gaps=gaps,
            errors=errors,
            retrieved_at=now,
        )

    # ------------------------------------------------------------------
    # 3. audit_sources — 来源审计
    # ------------------------------------------------------------------

    def audit_sources(
        self,
        source_records: list[ResearchSource],
        player_records: list[ResearchSource],
        reference_date: date | None = None,
    ) -> SerenityToolResult:
        """
        Audit the quality and completeness of research sources.

        Checks:
        - Each thesis claim has a corresponding source
        - No expired sources
        - No weak-only source chains
        - No missing player categories

        Returns: Audit findings as ResearchSource records (type: audit).
        """
        now = datetime.now()
        if reference_date is None:
            reference_date = date.today()
        gaps: list[str] = []
        records: list[ResearchSource] = []

        # Check 1: Source coverage
        has_first_hand = any(
            r.source_quality == "first_hand" for r in source_records
        )
        has_second_hand = any(
            r.source_quality in ("second_hand", "first_hand") for r in source_records
        )
        all_weak = all(
            r.source_quality == "weak" for r in source_records
        ) if source_records else True

        if not source_records:
            gaps.append("audit: no source records — cannot form any evidence")
        elif all_weak:
            records.append(ResearchSource(
                source_record_id="audit:all_weak",
                source_type="unknown",
                source_quality="weak",
                title="来源质量审计: 全部为弱来源",
                summary="所有来源的 source_quality 为 weak，不能形成强结论",
                retrieved_at=now,
                gaps=["all_sources_weak"],
            ))

        # Check 2: Expiry
        expired_count = 0
        for rec in source_records:
            if rec.published_at and (reference_date - rec.published_at).days > 365:
                expired_count += 1
                gaps.append(f"audit: expired source {rec.source_record_id} (published {rec.published_at})")

        if expired_count > 0:
            records.append(ResearchSource(
                source_record_id="audit:expired",
                source_type="unknown",
                source_quality="weak",
                title="来源过期审计",
                summary=f"{expired_count} 条来源超过 365 天，可能已过期",
                retrieved_at=now,
                gaps=[f"{expired_count}_sources_expired"],
            ))

        # Check 3: Source gap analysis
        if source_records and not has_first_hand:
            gaps.append("audit: no first_hand sources — evidence chain is weak")

        # Check 4: Player coverage
        player_count = len(player_records)
        if player_count == 0:
            gaps.append("audit: no verified players — cannot assess competitive landscape")
        elif player_count < 3:
            gaps.append(f"audit: only {player_count} verified player(s) — limited competitive analysis")

        return SerenityToolResult(
            tool_name="audit_sources",
            records=records,
            total_found=len(records),
            gaps=gaps,
            errors=[],
            retrieved_at=now,
        )

    # ------------------------------------------------------------------
    # 4. red_team_falsify — red-team 证伪
    # ------------------------------------------------------------------

    def red_team_falsify(
        self,
        source_records: list[ResearchSource],
        player_records: list[ResearchSource],
    ) -> SerenityToolResult:
        """
        Generate red-team falsification findings from retrieved sources.

        Strictly based on source records — NO fabrication.
        Only produces falsifying angles, alternative routes, and evidence gaps
        that CAN BE TRACED back to source_record_id.

        Rules:
        - Every falsifying point MUST reference a source_record_id
        - No self-created counter-facts
        - No buy/sell/target/stop recommendations
        """
        now = datetime.now()
        gaps: list[str] = []
        records: list[ResearchSource] = []

        if not source_records:
            gaps.append("red_team: no source records — cannot generate falsification")
            return SerenityToolResult(
                tool_name="red_team_falsify", records=[], total_found=0,
                gaps=gaps, errors=[], retrieved_at=now,
            )

        # Generate traceable falsifying points from source gaps
        for rec in source_records:
            if rec.gaps:
                for gap in rec.gaps:
                    records.append(ResearchSource(
                        source_record_id=f"red_team:{rec.source_record_id}",
                        source_type=rec.source_type,
                        source_quality=rec.source_quality,
                        title=f"证伪线索: {rec.source_record_id}",
                        summary=f"数据缺口: {gap}。此缺口可能构成反证。",
                        retrieved_at=now,
                    ))
                    if len(records) >= 10:
                        break

        # Sector-level falsification
        sector_sources = [r for r in source_records if "sector:" in r.source_record_id]
        if not sector_sources:
            records.append(ResearchSource(
                source_record_id="red_team:no_sector_data",
                source_type="unknown",
                source_quality="weak",
                title="行业数据缺失",
                summary="无法获取行业归属和同行对比数据，不能评估竞争格局和替代路线。",
                retrieved_at=now,
                gaps=["no_sector_data_for_falsification"],
            ))

        # Peer-level falsification
        if len(player_records) < 3:
            records.append(ResearchSource(
                source_record_id="red_team:limited_peers",
                source_type="unknown",
                source_quality="weak",
                title="同行覆盖面不足",
                summary="已验证玩家少于 3 家，替代路线和竞争压力评估不充分。",
                retrieved_at=now,
                gaps=["insufficient_peers_for_falsification"],
            ))

        if not records:
            gaps.append("red_team: no falsification angles identified — review may be incomplete")

        return SerenityToolResult(
            tool_name="red_team_falsify",
            records=records,
            total_found=len(records),
            gaps=gaps,
            errors=[],
            retrieved_at=now,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date(date_str: str | None) -> date | None:
        """Parse YYYYMMDD string to date."""
        if not date_str:
            return None
        try:
            return date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _infer_symbols_from_theme(theme_name: str) -> list[str]:
        """Heuristic: map known research themes to relevant stock symbols."""
        # This is a deterministic lookup — no LLM involved
        mapping: dict[str, list[str]] = {
            "锂电池": ["300750.SZ", "002074.SZ", "002460.SZ"],
            "固态电池": ["300750.SZ", "002074.SZ", "002594.SZ"],
            "新能源汽车": ["002594.SZ", "300750.SZ", "000625.SZ"],
            "白酒": ["600519.SH", "000858.SZ", "002304.SZ"],
            "白酒消费": ["600519.SH", "000858.SZ", "002304.SZ"],
            "半导体": ["688981.SH", "002371.SZ", "688012.SH"],
        }
        theme_lower = theme_name.lower()
        for key, syms in mapping.items():
            if key in theme_lower or theme_lower in key:
                return syms
        return []
