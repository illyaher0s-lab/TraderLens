"""
Serenity Deterministic Executor (双阶段重构 - 确定性执行层).

根据 ResearchPlan 执行确定性数据检索、ticker 验证、来源审计和 red-team。

硬约束:
- 最大并发数 = 2
- 所有操作确定性
- 不涉及 LLM
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime
from backend.services.serenity_planner import ResearchPlan
from backend.services.serenity_agent import SerenityRunContext, VerifiedResearchCandidate, SerenityAgentAudit
from contracts.research import ResearchSource

MAX_RESEARCH_CONCURRENCY = 2


class DeterministicExecutor:
    """Execute research plan with deterministic data retrieval and verification."""
    
    def __init__(self, serenity_tools, validator, db):
        """
        Args:
            serenity_tools: SerenityTools instance for data retrieval
            validator: ResearchValidator instance for verify_ticker
            db: ResearchDB instance for verification record lookup
        """
        self.serenity_tools = serenity_tools
        self.validator = validator
        self.db = db
        self._executor = None  # 延迟初始化
        
        # Theme matching state
        self.theme_keywords: list[str] = []
    
    def execute(
        self, 
        plan: ResearchPlan, 
        context: SerenityRunContext,
        audit: SerenityAgentAudit,
        theme_name: str = "",
        theme_background: str = "",
        target_symbol: str = "",  # Backward-compatible single target
        target_symbols: list[str] | None = None,
    ) -> None:
        """Execute research plan and populate context.
        
        V2: only research target_symbol (already verified from Workbench).
        No automatic player discovery, peer inference, or multi-candidate exploration.
        """
        
        try:
            # 初始化线程池
            self._executor = ThreadPoolExecutor(max_workers=MAX_RESEARCH_CONCURRENCY)
            
            # Step 0: 提取主题关键词
            from backend.services.theme_matcher import extract_keywords
            self.theme_keywords = extract_keywords(theme_name, theme_background)
            
            symbols = list(target_symbols or ([target_symbol] if target_symbol else []))
            if not symbols:
                audit.errors.append("executor: V2 requires target_symbol")
                return
            
            # Step 1: retrieve the explicit batch serially; one Serenity run.
            for symbol in symbols:
                self._retrieve_data_single(symbol, plan, context, audit)
            
            # Step 1.5: 计算主题匹配
            self._compute_theme_relevance(context)
            
            # 传递 theme_keywords 到 context
            context.theme_keywords = self.theme_keywords
            
            # Step 2: V2 不做 player discovery（symbols 从 sources 提取）
            
            # Step 3: 验证目标标的
            self._verify_tickers(context, audit)
            
            # Step 4: 来源审计
            self._audit_sources(context, audit)
            
            # Step 5: red-team
            self._red_team(context, audit)
        finally:
            # 确保关闭线程池
            if self._executor:
                self._executor.shutdown(wait=True)
                self._executor = None
    
    def _retrieve_data_single(self, symbol: str, plan: ResearchPlan, context: SerenityRunContext, audit: SerenityAgentAudit):
        """V2: 仅检索单个目标标的."""
        try:
            result = self.serenity_tools.retrieve_supply_chain(
                theme_name="",
                theme_background="",
                keywords=plan.keywords[:5],
                symbols=[symbol],
                start_date=plan.start_date,
                end_date=plan.end_date,
                max_records=20,
            )
            
            audit.tool_calls.append({
                "tool": "retrieve_supply_chain",
                "params": {"symbol": symbol, "keywords": plan.keywords[:5]},
                "result_summary": {
                    "records_count": len(result.records),
                    "gaps_count": len(result.gaps),
                    "errors_count": len(result.errors),
                }
            })
            
            for record in result.records:
                context.sources_by_id[record.source_record_id] = record
            
            if result.gaps:
                audit.errors.extend([f"retrieve({symbol}): {g}" for g in result.gaps])
            if result.errors:
                audit.errors.extend([f"retrieve({symbol}): {e}" for e in result.errors])
                
        except Exception as exc:
            audit.errors.append(f"retrieve_supply_chain({symbol}) failed: {exc}")
    
    def _retrieve_data(self, plan: ResearchPlan, context: SerenityRunContext, audit: SerenityAgentAudit):
        """并发检索数据，最大并发 2."""
        
        # 为每个 seed symbol 创建检索任务
        seed_symbols = plan.seed_symbols[:10]  # 最多 10 个
        
        if not seed_symbols:
            audit.errors.append("executor: no seed_symbols in plan")
            return
        
        # 批量调用 retrieve_supply_chain
        futures = []
        for i in range(0, len(seed_symbols), MAX_RESEARCH_CONCURRENCY):
            batch = seed_symbols[i:i+MAX_RESEARCH_CONCURRENCY]
            
            for symbol in batch:
                future = self._executor.submit(
                    self.serenity_tools.retrieve_supply_chain,
                    theme_name="",
                    theme_background="",
                    keywords=plan.keywords[:5],  # 限制关键词数量
                    symbols=[symbol],
                    start_date=plan.start_date,
                    end_date=plan.end_date,
                    max_records=20,
                )
                futures.append((symbol, future))
        
        # 收集结果
        for symbol, future in futures:
            try:
                result = future.result(timeout=30)
                
                # 记录工具调用（规范化）
                audit.tool_calls.append({
                    "tool": "retrieve_supply_chain",
                    "params": {"symbol": symbol, "keywords": plan.keywords[:5]},
                    "result_summary": {
                        "records_count": len(result.records),
                        "gaps_count": len(result.gaps),
                        "errors_count": len(result.errors),
                    }
                })
                
                # 保存真实 ResearchSource 到 context
                for record in result.records:
                    context.sources_by_id[record.source_record_id] = record
                
                # 记录 gaps 和 errors
                if result.gaps:
                    audit.errors.extend([f"retrieve({symbol}): {g}" for g in result.gaps])
                if result.errors:
                    audit.errors.extend([f"retrieve({symbol}): {e}" for e in result.errors])
                    
            except Exception as exc:
                audit.errors.append(f"retrieve_supply_chain({symbol}) failed: {exc}")
                audit.tool_calls.append({
                    "tool": "retrieve_supply_chain",
                    "params": {"symbol": symbol, "keywords": plan.keywords[:5]},
                    "result_summary": {"error": str(exc)}
                })
    
    def _compute_theme_relevance(self, context: SerenityRunContext):
        """确定性计算主题匹配（Step 1.5）。"""
        from backend.services.theme_matcher import match_theme_to_source
        
        if not self.theme_keywords:
            return
        
        for sid, source in context.sources_by_id.items():
            matched, basis = match_theme_to_source(
                keywords=self.theme_keywords,
                source_title=source.title,
                source_summary=source.summary,
                source_industry="",  # TODO: 从 source 提取 industry
            )
            
            # 更新来源的主题匹配字段
            source.theme_keywords_matched = matched
            source.theme_relevance_basis = basis
    
    def _discover_players(self, context: SerenityRunContext, audit: SerenityAgentAudit):
        """从已检索的 sources 发现玩家."""
        
        source_records = list(context.sources_by_id.values())
        
        if not source_records:
            audit.errors.append("executor: no source records to discover players from")
            return
        
        # 调用 discover_players
        result = self.serenity_tools.discover_players(
            source_records=source_records,
            max_players=20,
        )
        
        # 保存发现的玩家 records
        for record in result.records:
            context.sources_by_id[record.source_record_id] = record
        
        # 记录 gaps 和 errors
        if result.gaps:
            audit.errors.extend([f"discover_players: {g}" for g in result.gaps])
        if result.errors:
            audit.errors.extend([f"discover_players: {e}" for e in result.errors])
    
    def _verify_tickers(self, context: SerenityRunContext, audit: SerenityAgentAudit):
        """批量 verify_ticker，最大并发 2."""
        
        # 从 sources 提取所有 symbols
        symbols = self._extract_symbols_from_sources(context)
        
        if not symbols:
            audit.errors.append("executor: no symbols to verify")
            return
        
        # 批量验证
        futures = []
        for i in range(0, len(symbols), MAX_RESEARCH_CONCURRENCY):
            batch = symbols[i:i+MAX_RESEARCH_CONCURRENCY]
            
            for symbol in batch:
                future = self._executor.submit(
                    self.validator.verify_ticker,
                    symbol,
                )
                futures.append((symbol, future))
        
        # 收集验证结果
        for symbol, future in futures:
            try:
                verification = future.result(timeout=10)
                
                # 记录工具调用
                audit.tool_calls.append({
                    "tool": "verify_ticker",
                    "params": {"symbol": symbol},
                    "result_summary": {
                        "confidence": verification.confidence,
                        "status": verification.status,
                        "company_name": verification.company_name,
                    }
                })
                
                # 只接受 high/medium confidence
                if verification.confidence not in ("high", "medium"):
                    audit.errors.append(
                        f"verify_ticker({symbol}): confidence={verification.confidence} — rejected"
                    )
                    continue
                
                # 放宽 status 检查：listed/suspended 都接受
                # suspended 候选会被硬过滤标记，但仍保留在 raw pool
                if verification.status not in ("listed", "suspended"):
                    audit.errors.append(
                        f"verify_ticker({symbol}): status={verification.status} — rejected"
                    )
                    continue
                
                # 执行硬过滤
                hard_filter_snapshot = self.validator.get_hard_filter_snapshot(
                    symbol, verification.status
                )
                
                validation_result = self.validator.validate_candidate(
                    symbol=symbol,
                    company_name=verification.company_name,
                    is_listed=hard_filter_snapshot.is_listed,
                    is_st=hard_filter_snapshot.is_st,
                    is_suspended=hard_filter_snapshot.is_suspended,
                    avg_daily_volume=hard_filter_snapshot.avg_daily_volume,
                )
                
                # 记录硬过滤调用
                audit.tool_calls.append({
                    "tool": "validate_candidate",
                    "params": {"symbol": symbol},
                    "result_summary": {
                        "flags": validation_result.flags,
                        "is_valid": validation_result.is_valid,
                    }
                })
                
                # 创建 VerifiedResearchCandidate（无论硬过滤是否通过）
                self._create_verified_candidate(
                    symbol, verification, validation_result.flags, context, audit
                )
                
            except Exception as exc:
                audit.errors.append(f"verify_ticker({symbol}) failed: {exc}")
                audit.tool_calls.append({
                    "tool": "verify_ticker",
                    "params": {"symbol": symbol},
                    "result_summary": {"error": str(exc)}
                })
    
    def _extract_symbols_from_sources(self, context: SerenityRunContext) -> list[str]:
        """从 source_record_id 提取 symbols."""
        seen_symbols: set[str] = set()
        
        for sid in context.sources_by_id.keys():
            # Parse symbol from source_record_id (format: tool:symbol:idx)
            parts = sid.split(":")
            if len(parts) >= 2:
                sym = parts[1]
                if "." in sym:  # looks like a ticker (e.g., 300750.SZ)
                    seen_symbols.add(sym)
        
        return list(seen_symbols)
    
    def _create_verified_candidate(
        self, 
        symbol: str, 
        verification,
        hard_filter_flags: list[str],
        context: SerenityRunContext, 
        audit: SerenityAgentAudit
    ):
        """创建 VerifiedResearchCandidate 并添加到 context."""
        
        # 找到支持该 symbol 的 source IDs
        supporting_source_ids = [
            sid for sid in context.sources_by_id.keys()
            if f":{symbol}:" in sid or sid.endswith(f":{symbol}")
        ]
        
        if not supporting_source_ids:
            audit.errors.append(
                f"create_candidate({symbol}): no supporting sources — rejected"
            )
            return
        
        candidate = VerifiedResearchCandidate(
            symbol=symbol,
            company_name=verification.company_name,
            verification_id=verification.verification_id,
            exchange=verification.exchange,
            listing_status=verification.status,
            confidence=verification.confidence,
            supporting_source_ids=supporting_source_ids,
            hard_filter_flags=hard_filter_flags,  # 保存真实硬过滤结果
            red_team_findings=[],
            unresolved_gaps=[],
        )
        
        context.verified_candidates_by_symbol[symbol] = candidate
    
    def _audit_sources(self, context: SerenityRunContext, audit: SerenityAgentAudit):
        """确定性来源审计."""
        
        # 记录工具调用
        sources_summary = {
            "total_sources": len(context.sources_by_id),
            "quality_distribution": {},
        }
        for s in context.sources_by_id.values():
            q = s.source_quality
            sources_summary["quality_distribution"][q] = sources_summary["quality_distribution"].get(q, 0) + 1
        
        # 全局检查：是否有 first_hand 来源
        has_first_hand = any(
            s.source_quality == "first_hand" 
            for s in context.sources_by_id.values()
        )
        if not has_first_hand:
            audit.errors.append("source_audit: no first_hand sources")
        
        sources_summary["has_first_hand"] = has_first_hand
        
        # 候选级检查
        for symbol in list(context.verified_candidates_by_symbol.keys()):
            candidate = context.verified_candidates_by_symbol[symbol]
            
            # 检查来源是否存在
            missing_sources = [
                sid for sid in candidate.supporting_source_ids
                if sid not in context.sources_by_id
            ]
            if missing_sources:
                audit.errors.append(
                    f"source_audit: {symbol} references non-existent sources: {missing_sources}"
                )
                # 移除该候选
                del context.verified_candidates_by_symbol[symbol]
                continue
            
            # 检查是否全部为 weak
            sources = [context.sources_by_id[sid] for sid in candidate.supporting_source_ids]
            all_weak = all(s.source_quality == "weak" for s in sources)
            if all_weak:
                candidate.unresolved_gaps.append("all_sources_weak")
                audit.errors.append(f"source_audit: {symbol} all sources are weak")
            
            # 检查是否过期（published_at 超过 2 年）
            today = date.today()
            has_recent = any(
                s.published_at and (today - s.published_at).days < 730
                for s in sources
            )
            if not has_recent:
                candidate.unresolved_gaps.append("all_sources_expired")
                audit.errors.append(f"source_audit: {symbol} all sources expired")
        
        # 记录工具调用
        audit.tool_calls.append({
            "tool": "audit_sources",
            "params": {},
            "result_summary": sources_summary
        })
        
        context.completed_checks.add("source_audit")
    
    def _red_team(self, context: SerenityRunContext, audit: SerenityAgentAudit):
        """确定性 red-team 分类。
        
        规则：
        1. data_gaps：仅记录数据缺失，不自动生成问题
        2. counter_evidence：仅记录已有来源中的明确反证，必须有 source_record_id
        3. falsification_questions：留空，等待 Synthesizer (LLM) 生成
        
        禁止：
        - 根据 data_gaps 自动生成问题
        - 将 source.gaps/errors 当作 counter_evidence（除非明确引用反方事实）
        """
        
        # 全局 gaps
        if len(context.verified_candidates_by_symbol) < 3:
            audit.errors.append("red_team: insufficient player coverage (< 3)")
        
        # 候选级 red-team
        for symbol, candidate in context.verified_candidates_by_symbol.items():
            sources = [context.sources_by_id[sid] for sid in candidate.supporting_source_ids]
            
            # 1. 数据缺口 (data_gaps) — 仅记录缺失，不生成问题
            has_financials = any("financials:" in s.source_record_id for s in sources)
            if not has_financials:
                candidate.data_gaps.append("no_financial_data")
            
            has_announcements = any("announcements:" in s.source_record_id for s in sources)
            if not has_announcements:
                candidate.data_gaps.append("no_announcement_data")
            
            has_sector = any("sector:" in s.source_record_id for s in sources)
            if not has_sector:
                candidate.data_gaps.append("no_sector_data")
            
            # 2. 真实反证 (counter_evidence) — 目前无确定性方法提取，留空
            # 未来可以：检查 source 中的具体数值冲突、公告中的负面事件等
            # 当前：不从 source.gaps 自动提取，等待人工或 LLM 补充
            
            # 3. 待验证问题 (falsification_questions) — 留空，由 Synthesizer (LLM) 生成
            # LLM 会根据主题、候选和已有数据生成具体的诘问
            
            # 向后兼容字段填充（合并三类结果）
            candidate.red_team_findings = (
                candidate.counter_evidence + 
                candidate.falsification_questions + 
                candidate.data_gaps
            )
            candidate.unresolved_gaps = candidate.data_gaps.copy()
        
        # 记录工具调用
        red_team_summary = {
            "candidates_checked": len(context.verified_candidates_by_symbol),
            "data_gaps_found": sum(len(c.data_gaps) for c in context.verified_candidates_by_symbol.values()),
            "counter_evidence_found": sum(len(c.counter_evidence) for c in context.verified_candidates_by_symbol.values()),
        }
        audit.tool_calls.append({
            "tool": "red_team",
            "params": {},
            "result_summary": red_team_summary
        })
        
        # 默认警告（不作为硬阻断）
        audit.errors.append("red_team: private_players_not_checked")
        audit.errors.append("red_team: subsidiaries_not_checked")
        audit.errors.append("red_team: acquired_or_delisted_not_checked")
        
        context.completed_checks.add("red_team")
