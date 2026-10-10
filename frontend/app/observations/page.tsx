/**
 * Observation Pool - List Page
 * 
 * Vercel design system (shadow-as-border, Geist font, minimal)
 * Shows stocks user observes/holds with latest daily signals
 * 
 * P2-1 minimum viable scope:
 * - List open/closed observation positions
 * - Show latest signal type + data state
 * - No fake hold when data insufficient
 * - Empty state with clear next action
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ensurePositionMarketCheck, type PositionMarketState } from "@/lib/position-market-monitor";
import { submitExecutionFeedback } from "@/lib/api-client";
import TopNav from "@/components/TopNav";

type MarketDataState = "ok" | "unavailable" | "partial" | "stale" | "inconsistent" | "source_error" | "adapter_unsupported";
type SignalType = "hold" | "sell" | "risk" | "invalidated";
type LifecycleState = "open" | "closed";

interface LatestSignal {
  signal_type: SignalType | null;
  as_of_date: string;
  market_data_state: MarketDataState;
  plain_explanation: string | null;
  triggered_invalidations: string[];
}

interface ObservationPosition {
  position_id: string;
  symbol: string;
  name: string;
  entry_price: number;
  quantity: number;
  sellable_quantity: number;
  entry_thesis: string;
  lifecycle_state: LifecycleState;
  opened_at: string;
  execution_date: string | null;
  recorded_at: string;
  closed_at: string | null;
  template_id: string;
  record_source?: string;
  trade_type: "actual" | "simulated" | "unknown";
  plan_linked?: boolean;
  security_type?: "stock" | "fund" | "unknown";
  quantity_unit?: "share" | "fund_share" | "unknown";
  latest_signal: LatestSignal | null;
}

interface FeeCalculation {
  source: "user_confirmed" | "simulated_estimate" | "mixed" | "unknown";
  amount: number | null;
  commission: number | null;
  stamp_duty: number | null;
  estimated_amount: number | null;
  confirmed_amount: number | null;
  note: string | null;
}

interface ExecutionLog {
  log_id: string;
  execution_date: string | null;
  recorded_at: string;
  confirmed_action: string;
  confirmed_price: number | null;
  confirmed_quantity: number | null;
  confirmed_fees: number | null;
  fee_calculation: FeeCalculation | null;
  symbol: string | null;
  name: string | null;
  record_source: string;
  trade_type: "actual" | "simulated" | "unknown";
  plan_linked: boolean;
  trade_amount: string | null;
  security_type: "stock" | "fund" | "unknown";
  quantity_unit: "share" | "fund_share" | "unknown";
  trade_source: string | null;
  reason: string | null;
  sell_reason: string | null;
  exit_plan_target_price: number | null;
  exit_plan_stop_price: number | null;
  exit_plan_conditions: string | null;
  exit_plan_entered_at: string | null;
  exit_plan_is_retrospective: boolean | null;
  voided: boolean;
  voided_at: string | null;
  void_reason: string | null;
}

interface DisciplineReview {
  review_id: string;
  position_id: string | null;
  buy_log_id: string | null;
  sell_log_id: string;
  trade_type: "actual" | "simulated" | "unknown";
  execution_rule_status: "verified" | "unverified" | "actual_recorded";
  holding_days: number | null;
  dividend_status: "unverified";
  plan_comparison: {
    status: string;
    message: string;
    entered_at: string | null;
    entered_after_buy: boolean | null;
    target_price: number | null;
    stop_price: number | null;
    conditions: string | null;
  };
  deterministic_summary: string;
  same_day_event_order_note?: string | null;
  ai_review_text: string | null;
  ai_review_status: "not_requested" | "available" | "unavailable";
  pnl_record: {
    gross_pnl_amount: number | null;
    gross_pnl_pct: number | null;
    pnl_amount: number | null;
    pnl_pct: number | null;
    fees: number | null;
    missing_fields: string[];
    fee_calculation?: FeeCalculation;
  };
}

const formatPrice = (value: number | null) => value == null
  ? "未知"
  : value.toLocaleString("zh-CN", { maximumFractionDigits: 3 });

const quantityUnitLabel = (unit?: string) => unit === "share"
  ? "股"
  : unit === "fund_share" ? "基金份额" : "单位未知";

const tradeSourceLabel: Record<string, string> = {
  self_research: "自己研究",
  friend: "朋友推荐",
  media: "媒体信息",
  system_suggestion: "用户选择：系统建议",
};

const executionFeeLabel = (log: ExecutionLog): string => {
  if (log.confirmed_fees != null) return `¥${log.confirmed_fees.toFixed(2)}（已确认）`;
  if (log.fee_calculation?.amount != null) return `约¥${log.fee_calculation.amount.toFixed(2)}（估算）`;
  if (log.fee_calculation?.estimated_amount != null) {
    return `估算佣金¥${log.fee_calculation.estimated_amount.toFixed(2)}，税费未知`;
  }
  return "未知";
};

const sellReasonLabel: Record<string, string> = {
  target: "达到目标",
  stop: "触及止损",
  changed_judgment: "判断改变",
  fear: "恐惧",
  urgent_cash: "急需用钱",
};

function PositionSellForm({
  position,
  onSaved,
  activeSellLogs,
}: {
  position: ObservationPosition;
  onSaved: () => void;
  activeSellLogs: ExecutionLog[];
}) {
  const [expanded, setExpanded] = useState(false);
  const [price, setPrice] = useState("");
  const [quantity, setQuantity] = useState("");
  const [executionDate, setExecutionDate] = useState(
    () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(new Date()),
  );
  const [fees, setFees] = useState("");
  const [sellReason, setSellReason] = useState<"target" | "stop" | "changed_judgment" | "fear" | "urgent_cash" | "">("");
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [operationId, setOperationId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const canSell = position.sellable_quantity > 0;
  const sixDigitSymbol = position.symbol.split(".", 1)[0];

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (!canSell || !sellReason || !confirmed || !price.trim() || !quantity.trim()) return;
    setSubmitting(true);
    setMessage(null);
    const currentOperationId = operationId || crypto.randomUUID();
    setOperationId(currentOperationId);
    try {
      await submitExecutionFeedback({
        symbol: sixDigitSymbol,
        action: "sell",
        position_id: position.position_id,
        trade_type: position.trade_type as "actual" | "simulated",
        price: price.trim(),
        quantity: Number(quantity),
        execution_date: executionDate,
        operation_id: currentOperationId,
        confirmed_already_executed: true,
        fees: fees.trim() || undefined,
        reason: reason.trim() || undefined,
        sell_reason: sellReason,
      });
      setMessage("卖出记录已登记。");
      setPrice("");
      setQuantity("");
      setFees("");
      setReason("");
      setSellReason("");
      setConfirmed(false);
      setOperationId(null);
      onSaved();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "登记失败，请检查成交信息。重试会沿用本次操作编号。");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div onClick={(event) => event.stopPropagation()} style={{ marginTop: "0" }}>
      {!canSell && (
        <div role="note" style={styles.sellBlockedNote}>
          <p style={styles.cardMeta}>
            当前可卖数量为 0。请先核对 T+1 限制和同代码、同类型的有效卖出记录；系统不会绕过持仓校验。
          </p>
          {activeSellLogs.length > 0 && (
            <div style={{ display: "grid", gap: "4px", marginTop: "6px" }}>
              <p style={styles.cardMeta}>这些未作废记录可能影响可卖量；请先查看记录并按需填写作废原因：</p>
              {activeSellLogs.map((log) => (
                <a key={log.log_id} href={"#execution-log-" + log.log_id} style={styles.emptyLink}>
                  {log.execution_date || "日期未知"} · {log.confirmed_quantity == null ? "数量未知" : `${log.confirmed_quantity} ${quantityUnitLabel(log.quantity_unit)}`} · 查看卖出记录和作废入口
                </a>
              ))}
            </div>
          )}
        </div>
      )}
      {!expanded ? (
        <button
          type="button"
          aria-label={"卖出 " + position.name + "（" + sixDigitSymbol + "）"}
          onClick={() => setExpanded(true)}
          disabled={!canSell}
          style={canSell ? styles.sellButton : { ...styles.sellButton, background: "#f3f4f6", color: "#666666", cursor: "not-allowed" }}
        >
          卖出
        </button>
      ) : (
        <form onSubmit={submit} onClick={(event) => event.stopPropagation()} style={styles.sellForm}>
          <p style={styles.cardMeta}>标的和记录类型来自所选持仓，不能在此修改。</p>
          <div style={styles.sellIdentity}>{position.name}（{sixDigitSymbol}）· {position.trade_type === "actual" ? "实际" : "模拟"}</div>
          <label style={styles.sellLabel}>成交价（元）
            <input required inputMode="decimal" value={price} onChange={(event) => { setPrice(event.target.value); setOperationId(null); }} style={styles.sellInput} />
          </label>
          <label style={styles.sellLabel}>成交数量（最多 {position.sellable_quantity}）
            <input required type="number" min="1" max={position.sellable_quantity} step="1" value={quantity} onChange={(event) => { setQuantity(event.target.value); setOperationId(null); }} style={styles.sellInput} />
          </label>
          <label style={styles.sellLabel}>成交日期
            <input required type="date" max={new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(new Date())} value={executionDate} onChange={(event) => { setExecutionDate(event.target.value); setOperationId(null); }} style={styles.sellInput} />
          </label>
          <label style={styles.sellLabel}>卖出原因
            <select required value={sellReason} onChange={(event) => { setSellReason(event.target.value as typeof sellReason); setOperationId(null); }} style={styles.sellInput}>
              <option value="">请选择</option>
              <option value="target">达到目标</option>
              <option value="stop">触及止损</option>
              <option value="changed_judgment">判断改变</option>
              <option value="fear">恐惧</option>
              <option value="urgent_cash">急需用钱</option>
            </select>
          </label>
          <label style={styles.sellLabel}>实际成交费用（元；模拟记录可留空）
            <input inputMode="decimal" value={fees} onChange={(event) => { setFees(event.target.value); setOperationId(null); }} style={styles.sellInput} />
          </label>
          <label style={styles.sellLabel}>补充说明（选填）
            <input maxLength={160} value={reason} onChange={(event) => { setReason(event.target.value); setOperationId(null); }} style={styles.sellInput} />
          </label>
          <label style={styles.sellConfirm}>
            <input type="checkbox" checked={confirmed} onChange={(event) => { setConfirmed(event.target.checked); setOperationId(null); }} />
            我确认这笔卖出已经成交；这里只登记，不会下单。
          </label>
          {message && <p role="status" style={styles.cardMeta}>{message}</p>}
          <div style={{ display: "flex", gap: "8px" }}>
            <button type="submit" disabled={!confirmed || !sellReason || !price.trim() || !quantity.trim() || Number(quantity) > position.sellable_quantity || submitting} style={styles.sellButton}>
              {submitting ? "登记中…" : "确认登记"}
            </button>
            <button type="button" onClick={() => setExpanded(false)} disabled={submitting} style={styles.sellCancel}>取消</button>
          </div>
        </form>
      )}
    </div>
  );
}

function VoidExecutionLogControl({
  log,
  apiBaseUrl,
  onSaved,
}: {
  log: ExecutionLog;
  apiBaseUrl: string;
  onSaved: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (!reason.trim()) return;
    setSubmitting(true);
    setMessage(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/observations/execution-logs/${encodeURIComponent(log.log_id)}/void`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: reason.trim() }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `作废失败（HTTP ${response.status}）`);
      setMessage("记录已作废，原记录仍保留在历史中。");
      onSaved();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "作废失败，请重试。");
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <div onClick={(event) => event.stopPropagation()} style={{ marginTop: "0" }}>
      {!expanded ? (
        <button type="button" onClick={() => setExpanded(true)} style={styles.voidButton}>作废此记录</button>
      ) : (
        <form onSubmit={submit} onClick={(event) => event.stopPropagation()} style={styles.sellForm}>
          <label style={styles.sellLabel}>作废原因（必填）
            <input required maxLength={160} value={reason} onChange={(event) => setReason(event.target.value)} style={styles.sellInput} />
          </label>
          {message && <p role="status" style={styles.cardMeta}>{message}</p>}
          <div style={{ display: "flex", gap: "8px" }}>
            <button type="submit" disabled={!reason.trim() || submitting} style={styles.voidButton}>{submitting ? "提交中…" : "确认作废"}</button>
            <button type="button" onClick={() => setExpanded(false)} disabled={submitting} style={styles.sellCancel}>取消</button>
          </div>
        </form>
      )}
    </div>
  );
}

export default function ObservationsPage() {
  const [positions, setPositions] = useState<ObservationPosition[]>([]);
  const [executionLogs, setExecutionLogs] = useState<ExecutionLog[]>([]);
  const [disciplineReviews, setDisciplineReviews] = useState<DisciplineReview[]>([]);
  const [marketStates, setMarketStates] = useState<Record<string, PositionMarketState>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [executionFilter, setExecutionFilter] = useState<"active" | "voided">("active");
  const [showAllExecutionLogs, setShowAllExecutionLogs] = useState(false);

  useEffect(() => {
    loadPositions();
  }, []);

  const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";
  
  const loadPositions = async () => {
    try {
      setLoading(true);
      setError(null);

      let marketCheck: PositionMarketState[] = [];
      try {
        const result = await ensurePositionMarketCheck();
        marketCheck = result.items || [];
      } catch (marketError) {
        console.error("Failed to check position market data:", marketError);
      }
      
      const url = API_BASE_URL + "/api/observations";
      const response = await fetch(url);

      if (!response.ok) {
        throw new Error("API request failed: " + url + " - HTTP " + response.status);
      }

      const data = await response.json();
      setPositions(data.positions || []);
      setExecutionLogs(data.execution_logs || []);
      setDisciplineReviews(data.discipline_reviews || []);
      setMarketStates(Object.fromEntries(marketCheck.map((item) => [item.position_id, item])));
    } catch (err) {
      console.error("Failed to load observations:", err);
      setError(
        err instanceof Error 
          ? `${err.message}. 请检查后端服务是否在 ${API_BASE_URL} 启动。`
          : "Unknown error"
      );
    } finally {
      setLoading(false);
    }
  };

  const getUserAction = (pos: ObservationPosition): string => {
    if (pos.lifecycle_state === "closed") {
      return "已关闭";
    }

    if (!pos.latest_signal) {
      return "等待生成信号";
    }

    const { signal_type, market_data_state } = pos.latest_signal;

    if (market_data_state === "unavailable" || market_data_state === "partial") {
      return "数据不足，建议暂停操作";
    }
    if (market_data_state === "source_error" || market_data_state === "inconsistent") {
      return "数据异常，建议暂停操作";
    }

    if (signal_type === "hold") {
      return "继续持有";
    }
    if (signal_type === "sell") {
      return "建议卖出";
    }
    if (signal_type === "risk") {
      return "注意风险";
    }
    if (signal_type === "invalidated") {
      return "论据失效";
    }

    return "查看详情";
  };

  if (loading) {
    return (
      <main style={styles.container}>
        <div style={styles.loadingText}>加载中...</div>
      </main>
    );
  }

  if (error) {
    return (
      <main style={styles.container}>
        <div style={styles.errorText}>加载失败: {error}</div>
      </main>
    );
  }

  const isCurrentPosition = (position: ObservationPosition) =>
    position.lifecycle_state === "open"
    && position.record_source === "autonomous_manual"
    && (position.trade_type === "actual" || position.trade_type === "simulated")
    && position.security_type !== "unknown";
  const currentPositions = positions.filter(isCurrentPosition);
  const historyPositions = positions.filter((position) => !isCurrentPosition(position));
  const executionLogById = new Map(
    executionLogs.map((log): [string, ExecutionLog] => [log.log_id, log]),
  );
  const filteredExecutionLogs = executionLogs
    .filter((log) => executionFilter === "voided" ? log.voided : !log.voided)
    .sort((left, right) => new Date(right.recorded_at).getTime() - new Date(left.recorded_at).getTime());
  const shownExecutionLogs = showAllExecutionLogs ? filteredExecutionLogs : filteredExecutionLogs.slice(0, 10);
  const todayStatus = currentPositions.map((position) => {
    const market = marketStates[position.position_id];
    const signal = position.latest_signal;
    const isCurrent = Boolean(
      market
      && market.status === "ok"
      && market.trade_date
      && market.trade_date === market.expected_trade_date
      && signal
      && signal.market_data_state === "ok"
      && signal.as_of_date.slice(0, 10) === market.trade_date
      && signal.signal_type,
    );
    const alert = market?.alerts.includes("stop_reached")
      ? "收盘价已触及止损价"
      : market?.alerts.includes("target_reached")
        ? "收盘价已达到目标价"
        : null;
    return { position, isCurrent, alert, action: getUserAction(position) };
  });
  const attentionToday = todayStatus.filter((item) =>
    item.isCurrent && (item.alert || item.position.latest_signal?.signal_type !== "hold"),
  );
  const unavailableToday = todayStatus.filter((item) => !item.isCurrent);
  const todayPrompt = currentPositions.length === 0
    ? "当前无持仓，今日无需操作"
    : attentionToday.length > 0
      ? "今日需关注：" + attentionToday.map((item) => item.position.name + "：" + (item.alert || item.action)).join("；")
        + (unavailableToday.length > 0 ? "；另有 " + unavailableToday.length + " 项数据或信号待确认" : "")
      : unavailableToday.length > 0
        ? "行情或持仓信号未能确认，暂不能判断今日是否需要操作。"
        : "今日无需操作";
  const formatDistance = (value: number | null) =>
    value == null ? "距离未知" : (value > 0 ? "+" : "") + value.toFixed(2) + "%";

  const missingReviewSummary = (review: DisciplineReview): string => {
    const missing = review.pnl_record.missing_fields;
    const gaps: string[] = [];
    if (review.pnl_record.fees == null || missing.includes("fees")) gaps.push("未扣费用");
    if (missing.includes("execution_rule")) gaps.push("模拟交易日期无法核实");
    if (missing.includes("matching_quantity")) gaps.push("卖出数量超过可匹配持仓");
    if (missing.includes("buy_log")) gaps.push("缺少匹配买入记录");
    if (missing.length && gaps.length === 0) gaps.push("信息不全，无法判断");
    return gaps.length ? gaps.join("；") : "信息不足，无法判断";
  };

  return (
    <>
      <TopNav tip={todayPrompt} />
      <main style={styles.container}>
        <h1 style={styles.title}>我的持仓</h1>

      <section aria-label="今日提示" style={styles.todayPrompt}>
        <strong>今日提示</strong>
        <span>{todayPrompt}</span>
      </section>

      <section aria-label="当前持仓" style={styles.section}>
        <div style={styles.sectionHeading}>
          <h2 style={styles.sectionTitle}>当前持仓</h2>
          <span style={styles.sectionHint}>卖出按钮只登记已完成的成交，不会下单。</span>
        </div>
        {currentPositions.length === 0 ? (
          <p style={styles.emptyText}>暂无可识别的当前持仓。历史条目仍保留在下方。</p>
        ) : (
          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.tableHead}>名称 / 代码</th>
                  <th style={styles.tableHead}>类型</th>
                  <th style={styles.tableHead}>持有 / 可卖</th>
                  <th style={styles.tableHead}>平均成本</th>
                  <th style={styles.tableHead}>最新收盘</th>
                  <th style={styles.tableHead}>浮动盈亏</th>
                  <th style={styles.tableHead}>距止损 / 目标</th>
                  <th style={styles.tableHead}>操作</th>
                </tr>
              </thead>
              <tbody>
                {currentPositions.map((position) => {
                  const market = marketStates[position.position_id];
                  const activeSellLogs = executionLogs.filter((log) =>
                    !log.voided
                    && log.confirmed_action === "sell"
                    && log.symbol === position.symbol
                    && log.trade_type === position.trade_type,
                  );
                  const unit = quantityUnitLabel(position.quantity_unit);
                  const profit = market?.unrealized_pnl;
                  const stopDistance = market?.stop_price == null
                    ? "未设止损"
                    : "距止损 " + formatDistance(market.distance_to_stop_pct);
                  const targetDistance = market?.target_price == null
                    ? "未设目标"
                    : "距目标 " + formatDistance(market.distance_to_target_pct);
                  return (
                    <tr key={position.position_id}>
                      <td style={styles.tableCell}>
                        <Link href={"/observations/" + position.position_id} style={styles.positionLink}>
                          <strong>{position.name}</strong>
                          <span>{position.symbol}</span>
                        </Link>
                      </td>
                      <td style={styles.tableCell}>{position.trade_type === "actual" ? "实际" : "模拟"}</td>
                      <td style={styles.tableCell}>
                        {position.quantity} {unit}
                        <small style={styles.cellSubtext}>{position.sellable_quantity} {unit} 可卖</small>
                      </td>
                      <td style={styles.tableCell}>¥{formatPrice(position.entry_price)}</td>
                      <td style={styles.tableCell}>
                        {market?.close == null ? "未知" : "¥" + formatPrice(market.close)}
                        <small style={styles.cellSubtext}>{market?.trade_date || "日期未知"}</small>
                      </td>
                      <td style={{
                        ...styles.tableCell,
                        color: profit == null ? "#666666" : profit >= 0 ? "#067647" : "#b42318",
                        fontWeight: 600,
                      }}>
                        {profit == null ? "未知" : (profit >= 0 ? "+" : "") + "¥" + profit.toFixed(2)}
                        <small style={styles.cellSubtext}>毛额，未含费用</small>
                      </td>
                      <td style={styles.tableCell}>
                        {stopDistance}
                        <small style={styles.cellSubtext}>{targetDistance}</small>
                      </td>
                      <td style={styles.tableCell}>
                        <PositionSellForm
                          position={position}
                          onSaved={loadPositions}
                          activeSellLogs={activeSellLogs}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {historyPositions.length > 0 && (
        <details style={styles.disclosure}>
          <summary style={styles.disclosureSummary}>历史记录（{historyPositions.length}）</summary>
          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.tableHead}>名称 / 代码</th>
                  <th style={styles.tableHead}>记录状态</th>
                  <th style={styles.tableHead}>数量</th>
                  <th style={styles.tableHead}>记录时间</th>
                </tr>
              </thead>
              <tbody>
                {historyPositions.map((position) => (
                  <tr key={position.position_id}>
                    <td style={styles.tableCell}>
                      <Link href={"/observations/" + position.position_id} style={styles.positionLink}>
                        <strong>{position.name || "历史记录"}</strong>
                        <span>{position.symbol || "代码未记录"}</span>
                      </Link>
                    </td>
                    <td style={styles.tableCell}>
                      {position.lifecycle_state === "closed" ? "已结束" : "历史记录 · 仅供查看"}
                    </td>
                    <td style={styles.tableCell}>
                      {position.quantity} {quantityUnitLabel(position.quantity_unit)}
                    </td>
                    <td style={styles.tableCell}>
                      {position.execution_date || "日期未记载"}
                      <small style={styles.cellSubtext}>
                        录入 {new Date(position.recorded_at).toLocaleDateString("zh-CN")}
                      </small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      <section aria-label="成交记录" style={styles.section}>
        <div style={styles.sectionHeading}>
          <h2 style={styles.sectionTitle}>成交记录</h2>
          <span style={styles.sectionHint}>默认显示最近 10 条有效记录。</span>
        </div>
        <div style={styles.tabs}>
          <button
            onClick={() => { setExecutionFilter("active"); setShowAllExecutionLogs(false); }}
            style={{ ...styles.tab, ...(executionFilter === "active" ? styles.tabActive : {}) }}
          >
            有效记录（{executionLogs.filter((log) => !log.voided).length}）
          </button>
          <button
            onClick={() => { setExecutionFilter("voided"); setShowAllExecutionLogs(false); }}
            style={{ ...styles.tab, ...(executionFilter === "voided" ? styles.tabActive : {}) }}
          >
            已作废（{executionLogs.filter((log) => log.voided).length}）
          </button>
        </div>
        {shownExecutionLogs.length === 0 ? (
          <p style={styles.emptyText}>暂无成交记录</p>
        ) : (
          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.tableHead}>日期</th>
                  <th style={styles.tableHead}>名称 / 代码</th>
                  <th style={styles.tableHead}>方向</th>
                  <th style={styles.tableHead}>数量</th>
                  <th style={styles.tableHead}>成交价</th>
                  <th style={styles.tableHead}>费用</th>
                  <th style={styles.tableHead}>状态</th>
                  <th style={styles.tableHead}>操作</th>
                </tr>
              </thead>
              <tbody>
                {shownExecutionLogs.map((log) => (
                  <tr key={log.log_id} id={"execution-log-" + log.log_id}>
                    <td style={styles.tableCell}>
                      {log.execution_date || "成交日未记载"}
                      <small style={styles.cellSubtext}>
                        录入 {new Date(log.recorded_at).toLocaleDateString("zh-CN")}
                      </small>
                    </td>
                    <td style={styles.tableCell}>
                      <strong>{log.name || "历史记录"}</strong>
                      <small style={styles.cellSubtext}>{log.symbol || "代码未记录"}</small>
                    </td>
                    <td style={styles.tableCell}>
                      {log.confirmed_action === "buy" ? "买入" : log.confirmed_action === "sell" ? "卖出" : "成交"}
                    </td>
                    <td style={styles.tableCell}>
                      {log.confirmed_quantity == null
                        ? "未知"
                        : String(log.confirmed_quantity) + (log.quantity_unit === "share" ? " 股" : log.quantity_unit === "fund_share" ? " 份" : "")}
                    </td>
                    <td style={styles.tableCell}>
                      {log.confirmed_price == null ? "未知" : "¥" + formatPrice(log.confirmed_price)}
                    </td>
                    <td style={styles.tableCell}>{executionFeeLabel(log)}</td>
                    <td style={styles.tableCell}>
                      {log.voided ? "已作废 · " + (log.void_reason || "原因未记录") : "有效"}
                    </td>
                    <td style={styles.tableCell}>
                      {log.voided ? "—" : (
                        <VoidExecutionLogControl log={log} apiBaseUrl={API_BASE_URL} onSaved={loadPositions} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {filteredExecutionLogs.length > 10 && (
          <button
            type="button"
            onClick={() => setShowAllExecutionLogs((shown) => !shown)}
            style={styles.moreButton}
          >
            {showAllExecutionLogs ? "收起记录" : "显示其余 " + (filteredExecutionLogs.length - 10) + " 条"}
          </button>
        )}
      </section>

      {/* Durable per-sale reviews from the same live-trade ledger */}
      <details style={styles.disclosure}>
        <summary style={styles.disclosureSummary}>已平仓复盘（{disciplineReviews.length}）</summary>
        <section aria-label="已平仓复盘" style={{ marginBottom: "24px" }}>
        <h2 style={{ fontSize: "20px", fontWeight: 600, margin: "0 0 12px" }}>
          卖出复盘
        </h2>
        {disciplineReviews.length === 0 ? (
          <p style={styles.emptyText}>暂无卖出复盘</p>
        ) : (
          <div style={styles.cardGrid}>
            {disciplineReviews.map((review) => {
              const sellLog = executionLogById.get(review.sell_log_id);
              const buyLog = review.buy_log_id ? executionLogById.get(review.buy_log_id) : undefined;
              const pnl = review.pnl_record;
              const plan = review.plan_comparison;
              const netPnl = pnl.fees != null && pnl.pnl_amount != null ? pnl.pnl_amount : null;
              const feeSource = pnl.fee_calculation?.source;
              const netSummary = netPnl == null
                ? pnl.fees == null
                  ? pnl.fee_calculation?.estimated_amount != null
                    ? "税费范围未核，净盈亏未确认，分红未核。"
                    : "未扣费用，分红未核。"
                  : `净盈亏暂无法确认：${missingReviewSummary(review)}，分红未核。`
                : `${feeSource === "simulated_estimate" ? "扣估算费用后" : feeSource === "mixed" ? "扣估算及已确认费用后" : "扣费用后"}盈亏 ${netPnl >= 0 ? "+" : "-"}¥${Math.abs(netPnl).toFixed(2)}，分红未核。`;
              const grossSummary = pnl.gross_pnl_amount == null
                ? "毛盈亏信息不足"
                : `毛盈亏 ${pnl.gross_pnl_amount >= 0 ? "+" : "-"}¥${Math.abs(pnl.gross_pnl_amount).toFixed(2)}`;
              const planMessage = (plan.message || "计划信息不足，无法判断").replace(/[。；;\s]+$/g, "");
              const aiReviewStatus = review.ai_review_status === "available" && review.ai_review_text
                ? `AI建议：${review.ai_review_text}`
                : review.ai_review_status === "unavailable"
                  ? "AI复盘暂不可用，系统核对结果仍保留。"
                  : sellLog?.record_source === "autonomous_manual" && review.trade_type !== "unknown"
                    ? "AI建议未提供，系统核对结果仍保留。"
                    : "AI建议未提供。";
              return (
                <article key={review.review_id} style={styles.card}>
                  <div style={styles.cardHeader}>
                    <div>
                      <h3 style={styles.cardTitle}>
                        {sellLog?.name || sellLog?.symbol || (review.trade_type === "unknown" ? "历史卖出复盘" : "未匹配标的")}
                        {sellLog?.symbol ? ` (${sellLog.symbol})` : ""}
                      </h3>
                      <p style={styles.cardMeta}>
                        卖出日期：{sellLog?.execution_date || "未知"} · {review.trade_type === "simulated" ? "模拟记录" : review.trade_type === "actual" ? "实际交易记录" : "历史记录"}
                      </p>
                    </div>
                  </div>
                  <p style={{ ...styles.cardMeta, color: "#171717", fontWeight: 600 }}>结果：{grossSummary}；{netSummary}</p>
                  <p style={styles.cardMeta}>计划对照：{planMessage}。</p>
                  {review.same_day_event_order_note && <p style={styles.cardMeta}>{review.same_day_event_order_note}</p>}
                  <p style={styles.cardMeta}>{aiReviewStatus}</p>
                  <div style={styles.cardDetails}>
                    {buyLog ? (
                      <>
                        <div style={styles.cardDetailRow}>
                          <span style={styles.cardLabel}>买入记录</span>
                          <span style={styles.cardValue}>
                            {buyLog.execution_date || "成交日期未知"} · {buyLog.confirmed_price == null ? "价格未知" : `¥${formatPrice(buyLog.confirmed_price)}`} · {buyLog.confirmed_quantity == null ? "数量未知" : `${buyLog.confirmed_quantity} ${quantityUnitLabel(buyLog.quantity_unit)}`}
                          </span>
                        </div>
                        <p style={styles.cardMeta}>买入来源：{buyLog.trade_source ? tradeSourceLabel[buyLog.trade_source] || "未记录" : "未记录"} · 买入理由：{buyLog.reason || "未填理由"}</p>
                      </>
                    ) : (
                      <p style={styles.cardMeta}>买入记录：信息不足，无法匹配；买入日期、价格、数量、来源和理由未知。</p>
                    )}
                    {sellLog ? (
                      <>
                        <div style={styles.cardDetailRow}>
                          <span style={styles.cardLabel}>卖出记录</span>
                          <span style={styles.cardValue}>
                            {sellLog.execution_date || "成交日期未知"} · {sellLog.confirmed_price == null ? "价格未知" : `¥${formatPrice(sellLog.confirmed_price)}`} · {sellLog.confirmed_quantity == null ? "数量未知" : `${sellLog.confirmed_quantity} ${quantityUnitLabel(sellLog.quantity_unit)}`}
                          </span>
                        </div>
                        <p style={styles.cardMeta}>卖出原因：{sellReasonLabel[sellLog.sell_reason || ""] || "未记录"} · 补充说明：{sellLog.reason || "未记录"}</p>
                      </>
                    ) : (
                      <p style={styles.cardMeta}>卖出记录：信息不足，无法匹配；卖出日期、价格、数量、来源和原因未知。</p>
                    )}
                  </div>
                  <div style={styles.cardDetails}>
                    <div style={styles.cardDetailRow}>
                      <span style={styles.cardLabel}>毛盈亏</span>
                      <span style={styles.cardValue}>
                        {pnl.gross_pnl_amount == null || pnl.gross_pnl_pct == null
                          ? "信息不足，无法判断"
                          : `${pnl.gross_pnl_amount >= 0 ? "+" : "-"}¥${Math.abs(pnl.gross_pnl_amount).toFixed(2)}（${pnl.gross_pnl_pct >= 0 ? "+" : "-"}${Math.abs(pnl.gross_pnl_pct * 100).toFixed(2)}%）`}
                      </span>
                    </div>
                    <div style={styles.cardDetailRow}>
                      <span style={styles.cardLabel}>扣费净盈亏</span>
                      <span style={styles.cardValue}>{netSummary}</span>
                    </div>
                    <div style={styles.cardDetailRow}>
                      <span style={styles.cardLabel}>本次计入费用</span>
                      <span style={styles.cardValue}>{pnl.fees == null ? "未知" : `${feeSource === "simulated_estimate" ? "约" : ""}¥${pnl.fees.toFixed(2)}${feeSource === "simulated_estimate" ? "（估算）" : feeSource === "mixed" ? "（含估算）" : ""}`}</span>
                    </div>
                    <div style={styles.cardDetailRow}>
                      <span style={styles.cardLabel}>持有自然日</span>
                      <span style={styles.cardValue}>{review.holding_days == null ? "未知" : `${review.holding_days} 天`}</span>
                    </div>
                    <div style={styles.cardDetailRow}>
                      <span style={styles.cardLabel}>分红</span>
                      <span style={styles.cardValue}>分红未核</span>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      </details>

      {/* Empty State */}
      {positions.length === 0 && executionLogs.length === 0 && (
        <div style={styles.emptyState}>
          <p style={styles.emptyTitle}>暂无观察/持仓</p>
          <p style={styles.emptyText}>
            去 <Link href="/workbench" style={styles.emptyLink}>Workbench</Link> 输入：
          </p>
          <ul style={styles.emptyList}>
            <li>"朋友推荐了某某股票"</li>
            <li>"我已经买入 XX 股，成交价 XX 元"</li>
          </ul>
        </div>
      )}


    </main>
    </>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    maxWidth: "1200px",
    margin: "0 auto",
    padding: "32px 24px",
    fontFamily: "'Geist', -apple-system, BlinkMacSystemFont, sans-serif",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    paddingBottom: "24px",
    borderBottom: "1px solid rgba(0, 0, 0, 0.08)",
    marginBottom: "24px",
  },
  title: {
    fontSize: "32px",
    fontWeight: 600,
    letterSpacing: "-1.28px",
    color: "#171717",
    margin: 0,
  },
  subtitle: {
    fontSize: "16px",
    fontWeight: 400,
    color: "#666666",
    marginTop: "8px",
    marginBottom: 0,
  },
  backLink: {
    fontSize: "14px",
    fontWeight: 500,
    color: "#0072f5",
    textDecoration: "none",
  },
  tabs: {
    display: "flex",
    gap: "8px",
    marginBottom: "24px",
    borderBottom: "1px solid rgba(0, 0, 0, 0.08)",
    paddingBottom: "0",
  },
  tab: {
    padding: "8px 16px",
    fontSize: "14px",
    fontWeight: 500,
    color: "#666666",
    background: "transparent",
    border: "none",
    borderBottom: "2px solid transparent",
    cursor: "pointer",
    transition: "all 0.2s",
  },
  tabActive: {
    color: "#171717",
    borderBottomColor: "#171717",
  },
  headerActions: { display: "flex", alignItems: "center", gap: "16px" },
  recordBuyButton: { display: "inline-flex", alignItems: "center", borderRadius: "6px", padding: "9px 14px", background: "#171717", color: "#ffffff", fontSize: "14px", fontWeight: 600, textDecoration: "none" },
  todayPrompt: { display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "baseline", marginBottom: "20px", padding: "12px 14px", borderRadius: "6px", background: "#f5f7fa", color: "#333333", fontSize: "14px" },
  section: { marginBottom: "24px" },
  sectionHeading: { display: "flex", flexWrap: "wrap", alignItems: "baseline", justifyContent: "space-between", gap: "8px", marginBottom: "10px" },
  sectionTitle: { margin: 0, fontSize: "20px", fontWeight: 600, color: "#171717" },
  sectionHint: { color: "#777777", fontSize: "12px" },
  tableWrap: { overflowX: "auto", borderRadius: "8px", boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px" },
  table: { width: "100%", minWidth: "900px", borderCollapse: "collapse", background: "#ffffff", fontSize: "13px" },
  tableHead: { padding: "10px 12px", textAlign: "left" as const, whiteSpace: "nowrap" as const, color: "#666666", fontSize: "12px", fontWeight: 500, borderBottom: "1px solid #e5e5e5", background: "#fafafa" },
  tableCell: { padding: "11px 12px", textAlign: "left" as const, verticalAlign: "middle" as const, borderBottom: "1px solid #eeeeee", color: "#222222", whiteSpace: "nowrap" as const },
  positionLink: { display: "grid", gap: "3px", color: "#171717", textDecoration: "none" },
  cellSubtext: { display: "block", marginTop: "3px", color: "#808080", fontSize: "11px", fontWeight: 400 },
  disclosure: { marginBottom: "16px", borderBottom: "1px solid #e5e5e5" },
  disclosureSummary: { padding: "12px 0", cursor: "pointer", fontSize: "15px", fontWeight: 600, color: "#333333" },
  moreButton: { marginTop: "10px", padding: "7px 10px", border: "1px solid #d4d4d4", borderRadius: "5px", background: "#ffffff", color: "#444444", cursor: "pointer" },
  loadingText: {
    fontSize: "16px",
    color: "#666666",
    textAlign: "center" as const,
    padding: "48px 0",
  },
  errorText: {
    fontSize: "16px",
    color: "#ff5b4f",
    textAlign: "center" as const,
    padding: "48px 0",
  },
  emptyState: {
    textAlign: "center" as const,
    padding: "64px 24px",
    background: "#fafafa",
    borderRadius: "8px",
    boxShadow: "rgba(0, 0, 0, 0.08) 0px 0px 0px 1px",
  },
  emptyTitle: {
    fontSize: "20px",
    fontWeight: 600,
    color: "#171717",
    marginBottom: "12px",
  },
  emptyText: {
    fontSize: "16px",
    color: "#666666",
    marginBottom: "16px",
  },
  emptyLink: {
    color: "#0072f5",
    textDecoration: "underline",
  },
  emptyList: {
    listStyle: "none",
    padding: 0,
    fontSize: "14px",
    color: "#808080",
    lineHeight: 1.8,
  },
  cardGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
    gap: "16px",
  },
  card: {
    background: "#ffffff",
    borderRadius: "8px",
    boxShadow:
      "rgba(0,0,0,0.08) 0px 0px 0px 1px, rgba(0,0,0,0.04) 0px 2px 2px, #fafafa 0px 0px 0px 1px",
    padding: "16px",
    cursor: "pointer",
    transition: "box-shadow 0.2s",
  },
  cardHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: "12px",
  },
  cardTitle: {
    fontSize: "18px",
    fontWeight: 600,
    letterSpacing: "-0.32px",
    color: "#171717",
    margin: 0,
  },
  cardMeta: {
    fontSize: "12px",
    fontWeight: 400,
    color: "#808080",
    marginTop: "4px",
    marginBottom: 0,
  },
  cardThesis: {
    fontSize: "14px",
    fontWeight: 400,
    color: "#4d4d4d",
    lineHeight: 1.5,
    marginBottom: "12px",
    display: "-webkit-box",
    WebkitLineClamp: 2,
    WebkitBoxOrient: "vertical",
    overflow: "hidden",
  },
  cardDetails: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "8px",
    paddingTop: "12px",
    borderTop: "1px solid rgba(0, 0, 0, 0.08)",
    marginBottom: "12px",
  },
  cardDetailRow: {
    display: "flex",
    justifyContent: "space-between",
  },
  cardLabel: {
    fontSize: "12px",
    fontWeight: 500,
    color: "#808080",
  },
  cardValue: {
    fontSize: "12px",
    fontWeight: 600,
    color: "#171717",
  },
  sellForm: {
    display: "grid",
    gap: "10px",
    marginTop: "10px",
    padding: "12px",
    borderRadius: "6px",
    background: "#fafafa",
    boxShadow: "rgba(0, 0, 0, 0.08) 0px 0px 0px 1px",
  },
  sellLabel: {
    display: "grid",
    gap: "4px",
    fontSize: "12px",
    color: "#666666",
  },
  sellInput: {
    width: "100%",
    padding: "8px",
    border: "1px solid #d4d4d4",
    borderRadius: "4px",
    background: "#ffffff",
    color: "#171717",
  },
  sellIdentity: {
    fontSize: "13px",
    fontWeight: 600,
    color: "#171717",
  },
  sellConfirm: {
    display: "flex",
    gap: "8px",
    alignItems: "flex-start",
    fontSize: "12px",
    color: "#666666",
  },
  sellButton: {
    border: "none",
    borderRadius: "4px",
    padding: "8px 12px",
    background: "#171717",
    color: "#ffffff",
    fontSize: "12px",
    cursor: "pointer",
  },
  sellCancel: {
    border: "1px solid #d4d4d4",
    borderRadius: "4px",
    padding: "8px 12px",
    background: "#ffffff",
    color: "#444444",
    fontSize: "12px",
    cursor: "pointer",
  },
  voidButton: {
    border: "1px solid #b42318",
    borderRadius: "4px",
    padding: "8px 12px",
    background: "#ffffff",
    color: "#b42318",
    fontSize: "12px",
    cursor: "pointer",
  },
  cardAction: {
    display: "flex",
    gap: "8px",
    alignItems: "center",
    paddingTop: "12px",
    borderTop: "1px solid rgba(0, 0, 0, 0.08)",
  },
  cardActionLabel: {
    fontSize: "12px",
    fontWeight: 500,
    color: "#808080",
  },
  cardActionValue: {
    fontSize: "12px",
    fontWeight: 600,
    color: "#171717",
  },
  cardSignalDate: {
    fontSize: "10px",
    fontWeight: 400,
    color: "#808080",
    marginTop: "8px",
    marginBottom: 0,
  },
  badgeGreen: {
    display: "inline-block",
    padding: "2px 8px",
    fontSize: "11px",
    fontWeight: 500,
    color: "#2e6b3d",
    background: "rgba(46, 160, 67, 0.1)",
    border: "1px solid rgba(46, 160, 67, 0.4)",
    borderRadius: "4px",
  },
  badgeBlue: {
    display: "inline-block",
    padding: "2px 8px",
    fontSize: "11px",
    fontWeight: 500,
    color: "#0068d6",
    background: "#ebf5ff",
    border: "1px solid #0068d6",
    borderRadius: "4px",
  },
  badgeOrange: {
    display: "inline-block",
    padding: "2px 8px",
    fontSize: "11px",
    fontWeight: 500,
    color: "#7a4a10",
    background: "rgba(224, 122, 48, 0.1)",
    border: "1px solid rgba(224, 122, 48, 0.4)",
    borderRadius: "4px",
  },
  badgeRed: {
    display: "inline-block",
    padding: "2px 8px",
    fontSize: "11px",
    fontWeight: 500,
    color: "#991b1b",
    background: "rgba(239, 68, 68, 0.1)",
    border: "1px solid rgba(239, 68, 68, 0.4)",
    borderRadius: "4px",
  },
  badgeGray: {
    display: "inline-block",
    padding: "2px 8px",
    fontSize: "11px",
    fontWeight: 500,
    color: "#555555",
    background: "rgba(100, 100, 100, 0.1)",
    border: "1px solid rgba(100, 100, 100, 0.4)",
    borderRadius: "4px",
  },
};
