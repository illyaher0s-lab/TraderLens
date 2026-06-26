# Deferred Backlog v1

**Purpose**: Track features explicitly NOT doing now, but may need later.  
**Update Rule**: Every milestone closeout must update this file.

---

## 1. Evidence light_check integration

- **deferred_from_milestone**: M4
- **reason_deferred**: M4 主线必须先完成 Signal Board v0，避免研究检查拖慢看板闭环
- **suggested_future_milestone**: M4.1
- **prerequisite**: PlannedSignal metadata 稳定
- **trigger_to_revisit**: Signal Board v0 可生成、展示、review 并通过测试
- **current_decision**: 不进 M4 主线，可作为 M4.1 第一优先级

**Scope if revisited**:
- ST-flag check (reject buy signals for ST stocks)
- Suspension check (reject signals for suspended stocks)
- Limit up/down check (reject signals hitting limit)
- Liquidity check (reject signals for illiquid stocks)

**Integration point**: Run light_check AFTER signal generation, BEFORE storing to DB. Attach results to `PlannedSignal.metadata`.

---

## 2. Evidence deep_check

- **deferred_from_milestone**: M4
- **reason_deferred**: 需要 LLM tool-use、证据分级、审计、eval，复杂度高
- **suggested_future_milestone**: M5 或 M6
- **prerequisite**: Evidence light_check 已稳定，Signal Board 已能展示 evidence warning
- **trigger_to_revisit**: light_check 不能满足研究排雷需求
- **current_decision**: 不做

**Scope if revisited**:
- Multi-round LLM interrogation
- Web search for company news
- Sentiment analysis from social media
- Fundamental data deep dive

---

## 3. Serenity 产业链瓶颈映射

- **deferred_from_milestone**: M4
- **reason_deferred**: 属于上游研究自动化，不是当前 Signal Board 闭环必需
- **suggested_future_milestone**: M5
- **prerequisite**: Evidence light_check / basic research pool 稳定
- **trigger_to_revisit**: 需要从主题自动生成候选池和策略假设
- **current_decision**: 不做

**Scope if revisited**:
- Industry chain analysis
- Supply chain bottleneck identification
- Reverse mapping from trends to stocks

---

## 4. Multi-strategy Signal Board

- **deferred_from_milestone**: M4
- **reason_deferred**: v0 先验证单策略链路，避免 UI 和状态复杂化
- **suggested_future_milestone**: M4.1
- **prerequisite**: 单策略 Signal Board v0 稳定
- **trigger_to_revisit**: 用户需要同时观察多个策略信号
- **current_decision**: 不做

**Scope if revisited**:
- Strategy selector dropdown
- Multi-strategy summary view
- Cross-strategy signal comparison

---

## 5. Historical signal audit page

- **deferred_from_milestone**: M4
- **reason_deferred**: M4 只做最小 list/detail/review
- **suggested_future_milestone**: M4.1
- **prerequisite**: planned_signals 表稳定，有足够历史记录
- **trigger_to_revisit**: 需要复盘"哪些信号被忽略后涨了/跌了"
- **current_decision**: 不做复杂审计页

**Scope if revisited**:
- Historical signal outcome tracking
- Retrospective performance analysis
- "Missed opportunity" reports
- Review decision quality metrics

---

## 6. Frontend keyboard shortcuts / mobile polish

- **deferred_from_milestone**: M4
- **reason_deferred**: 非核心交易闭环
- **suggested_future_milestone**: M4.1 或体验优化阶段
- **prerequisite**: 基础页面可用
- **trigger_to_revisit**: 用户开始高频使用 Signal Board
- **current_decision**: 不做

**Scope if revisited**:
- Keyboard shortcuts (j/k nav, r review, i ignore)
- Mobile-responsive layout refinements
- Touch gesture support
- PWA (Progressive Web App) manifest

---

## 7. Notification push

- **deferred_from_milestone**: M4
- **reason_deferred**: Signal Board 还没验证日常使用价值
- **suggested_future_milestone**: M5
- **prerequisite**: 每日信号生成稳定
- **trigger_to_revisit**: 用户需要收盘后自动提醒
- **current_decision**: 不做

**Scope if revisited**:
- Email notifications (new signals generated)
- Telegram bot integration
- Browser push notifications
- Configurable notification rules

---

## 8. Async queue

- **deferred_from_milestone**: M4
- **reason_deferred**: v0 同步脚本足够，避免 Redis/Celery 提前复杂化
- **suggested_future_milestone**: M5+
- **prerequisite**: 信号生成或回测耗时影响使用
- **trigger_to_revisit**: 单次任务超过 1 分钟或需要后台批量运行
- **current_decision**: 不做

**Scope if revisited**:
- Background job workers (Celery, RQ)
- Message queues (Redis, RabbitMQ)
- Distributed task execution
- Job status tracking UI

---

## 9. Broker API / auto execution

- **deferred_from_milestone**: M4
- **reason_deferred**: 当前系统仍是实盘前验证和人工决策工具
- **suggested_future_milestone**: 不排期
- **prerequisite**: Signal Board、持仓记录、风控、人工确认、执行日志都稳定
- **trigger_to_revisit**: 用户明确要进入模拟盘/小资金执行验证阶段
- **current_decision**: 不做

**Scope if revisited**:
- Broker API integration (order placement, position query, account balance)
- Auto-execution engine
- Position synchronization
- Risk management pre-checks
- Execution audit trail

---

## 10. Real-time data feed

- **deferred_from_milestone**: M4
- **reason_deferred**: M4 uses EOD frozen snapshots only. Real-time requires different pipeline.
- **suggested_future_milestone**: M5+
- **prerequisite**: EOD signal generation proven useful
- **trigger_to_revisit**: 用户需要盘中信号更新或日内策略
- **current_decision**: 不做

**Scope if revisited**:
- Live tick data stream (websockets)
- Intraday bar updates
- Real-time signal regeneration
- Streaming database (InfluxDB, TimescaleDB)

---

## 11. Performance target: 100 signals < 10s

- **deferred_from_milestone**: M4
- **reason_deferred**: Premature optimization. v0 focuses on correctness, not speed.
- **suggested_future_milestone**: M4.1
- **prerequisite**: Signal generation proven correct and deterministic
- **trigger_to_revisit**: Signal generation takes >30s for typical use case
- **current_decision**: 不做性能优化

**Optimization strategies if revisited**:
- Profile `strategy_core.generate_signals()`
- Parallelize signal generation across symbols
- Cache intermediate calculations
- Database query optimization

---

## 12. Signal Board 前端增强功能

- **deferred_from_milestone**: M4 Phase 3
- **reason_deferred**: v0 只实现最小可用功能，避免过度设计
- **suggested_future_milestone**: M4.1
- **prerequisite**: Signal Board v0 稳定运行，用户开始高频使用
- **trigger_to_revisit**: 用户反馈需要更高效的操作方式
- **current_decision**: 不做

**Scope if revisited**:
- Keyboard shortcuts (j/k nav, r review, i ignore, w watch)
- Batch operations (multi-select signals, batch review)
- Real-time refresh (polling or WebSocket)
- Advanced filters (date range picker, strategy selector)
- Chart integration (price charts, performance charts)
- Mobile-optimized UI (touch gestures, responsive layout)
- Signal history view (past signals, review decisions)
- Export to CSV/Excel

---

## 13. Signal Board 性能优化

- **deferred_from_milestone**: M4 Phase 3
- **reason_deferred**: v0 不需要处理大量数据，避免提前优化
- **suggested_future_milestone**: M4.1
- **prerequisite**: 信号数量 > 1000 或页面加载变慢
- **trigger_to_revisit**: 用户抱怨页面慢或需要加载历史信号
- **current_decision**: 不做

**Scope if revisited**:
- Virtual scrolling (react-window, react-virtualized)
- Server-side pagination (cursor-based or offset-based)
- Client-side caching (React Query, SWR)
- Optimistic UI updates
- Lazy loading images/components

---

**Last Updated**: 2026-06-23 (M4 Phase 3 完成)  
**Next Update**: M4 closeout

---

## M4.1 Closeout Update

**Updated**: 2026-06-23  
**Reason**: M4.1 daily-ready work has been manually accepted and closed.

Completed from earlier deferred scope:
- Multi-strategy selector.
- Offset-based pagination.
- Signal date filter.
- Load More.
- List-page quick review for `watching`, `ignored`, and `expired`.
- Inline rejection reason for ignored signals.

Still deferred after M4.1:
- Evidence light_check / `risk_flags` / `evidence_status`.
- `watch_note` field and schema migration.
- Batch review.
- Keyboard shortcuts.
- Export.
- Charts.
- Virtual scrolling.
- React Query / SWR cache.
- Advanced search.
- Real-time refresh.
- Broker API and auto-execution.

Decision:
- M4.1 closed around daily review workflow.
- Evidence light_check should be revisited only if the next pain point is signal quality triage.
- UX-heavy items should be revisited only if review speed becomes the next pain point.
