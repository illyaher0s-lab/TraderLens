"use client";

import { useEffect, useRef, useState } from "react";

type Card021Observation = {
  status: "available" | "unavailable";
  failure_code?: string;
  failure_message?: string;
  strategy_id: string;
  protocol_revision: number;
  protocol_sha256?: string;
  protocol_verified?: boolean;
  symbol: string;
  evidence_level: string;
  signal_date?: string;
  supersedes_signal_date?: string | null;
  latest_market_data_date?: string;
  retrieved_at: string;
  judgment_at?: string;
  received_at?: string;
  snapshot_id?: string;
  snapshot_sha256?: string;
  market_input_sha256?: string;
  market_result_sha256?: string;
  implementation_sha256?: string;
  snapshot_mode?: "live_observation" | "saved_market_snapshot";
  snapshot_historical?: boolean;
  signal_window_start?: string;
  signal_window_end?: string;
  valid_adjusted_close_count?: number;
  signal_volatility?: string | null;
  target_weight?: string | null;
  target_weight_percentage?: string | null;
  target_price_raw_cny?: string | null;
  model_account_cash_cny?: string | null;
  model_reference_shares?: number | null;
  actual_shares?: number | null;
  sellable_shares_as_of_latest_market_data?: number | null;
  account_target_shares?: number | null;
  actual_delta_shares?: number | null;
  account_data_status?: string;
  account_source?: string | null;
  execution_gate?: string;
  action_decision: string;
  research_rationale?: string;
  earliest_attempt_after_signal_date?: string;
  first_attempt_status?: string;
  next_possible_attempt_date?: string;
  target_valid_until?: string;
  target_validity_status?: string;
  retry_policy_status?: string;
  retry_rule?: string;
  dividend_source?: {
    row_count?: number;
    coverage?: string;
  };
  market_constraints?: {
    round_lot_shares?: number;
    t_plus_one?: string;
    previous_session_volume_hands?: number | null;
    volume_capacity_shares_for_next_possible_attempt?: number | null;
    commission_rate?: string;
    minimum_commission_cny?: string;
    commission_ratio_limit?: string;
    minimum_order_value_for_commission_filter_cny?: string;
    volume_capacity_status?: string;
    other_fees?: string;
    suspension_and_price_limits?: string;
    execution_price?: string;
  };
  source_freshness?: {
    market_data_as_of?: string;
    calendar_coverage_through?: string;
    dividend_coverage?: string;
    origin_authenticated?: boolean;
  };
  sources?: Array<{
    endpoint: string;
    row_count?: number;
    retrieved_at: string;
    request_started_at?: string;
    received_at?: string;
  }>;
};

type Card021LiveSignalPanelProps = {
  snapshotId?: string | null;
};

function display(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" ? "未获取" : String(value);
}

export function buildCard021Summary(observation: Card021Observation) {
  const historical = observation.snapshot_mode === "saved_market_snapshot" || observation.snapshot_historical === true;
  const available = observation.status === "available";
  const expired = observation.target_validity_status === "expired" || observation.execution_gate === "blocked_target_expired";
  const actionLabel = ({
    buy: "研究规则指向买入",
    sell: "研究规则指向卖出",
    hold: "研究规则指向持有",
    not_decidable: "暂不可判断",
  } as Record<string, string>)[observation.action_decision] ?? "暂不可判断";
  const accountText = historical
    ? "这条历史快照没有当前账户资料：持仓、可卖份额、现金和分红应收均未保存或读取；本页也不跟踪未完成委托，因此无法确定当前实际买卖数量。"
    : observation.account_data_status === "no_user_confirmed_records"
      ? "没有可核实的用户确认成交记录；持仓、可卖份额、现金与分红应收未取得，实际买卖数量无法确定。"
      : observation.account_data_status === "position_confirmed_nav_missing"
        ? "已有用户确认的持仓记录（未经券商核实），但现金或分红应收缺失，无法计算账户目标份额和差额。"
        : observation.account_data_status === "provenance_unverified"
          ? "持仓记录的来源或确认状态无法核实，因此不展示实际份额或差额。"
          : observation.account_data_status === "account_nav_invalid" || observation.account_data_status === "quantity_invalid"
            ? "账户份额、现金或分红应收数据无效，无法计算实际买卖数量。"
            : observation.account_data_status === "user_confirmed_nav_available"
              ? "已按用户确认的账户记录计算信号日目标份额和差额；记录未经券商核实，结果不是订单。"
              : "没有可核实的用户确认账户记录，不能推断实际持仓或买卖数量。";
  const currentDecisionReason = historical
    ? "这条快照是历史行情，且未保存当前账户资料；不能据此判断现在是否买卖。"
    : !available
    ? "行情数据不足或未通过核验，本次没有可用目标。"
    : expired
      ? "旧目标已过有效期，不能作为当前交易依据。"
      : observation.execution_gate === "blocked_missing_account_nav_or_cash"
        ? "账户净值、现金或分红应收缺失，不能计算真实账户差额。"
        : observation.execution_gate === "blocked_attempt_date_constraints_not_checked"
          ? "尝试日的价格、市场状态、成交容量或费用尚未核实。"
          : observation.execution_gate?.startsWith("blocked_")
            ? `执行门槛为 ${observation.execution_gate}，当前条件未通过核验。`
            : !observation.execution_gate
              ? "执行门槛缺失，无法核验账户与尝试日条件。"
          : observation.account_data_status === "no_user_confirmed_records"
            ? "没有可核实的用户确认成交记录，无法判断当前账户差额。"
            : observation.action_decision !== "not_decidable"
              ? "收到的操作标签与当前执行状态无法相互核实；按保守原则不展示买卖或持有结论。"
              : observation.research_rationale ?? "账户信息或执行条件尚未完整核实。";
  const nextAttempt = observation.next_possible_attempt_date
    ? `旧目标下一可能尝试日：${observation.next_possible_attempt_date}（须在有效期内并通过执行核验；不是新买入信号）。`
    : "旧目标下一可能尝试日尚未核实，不代表可以执行。";
  const nextSignalText = !available || expired
    ? "下一信号日期尚未核实；须等实际 SSE 月末交易日收盘并取得新行情后再判断。"
    : observation.target_valid_until
      ? `下一月末新目标须在 ${observation.target_valid_until} 收盘后生成。`
      : "下一信号日期尚未核实；须等实际 SSE 月末交易日收盘并取得行情后再判断。";
  const nextStepText = !available
    ? "等待完整且可核验的行情后，再查询最新观察；本次没有目标，不按模型参考份额操作。"
    : expired
      ? "旧目标已经过期；等待实际月末收盘后取得新行情，再查看新目标，不沿用旧目标。"
      : historical
        ? "点击“查询最新观察”获取当前行情；再通过现有账户／成交确认路径核实持仓、现金和分红应收，并人工核对未完成委托。"
        : observation.account_data_status === "no_user_confirmed_records" || observation.execution_gate === "blocked_missing_account_nav_or_cash"
          ? "通过现有账户／成交确认路径核实持仓、现金和分红应收，并人工核对未完成委托；资料齐全后再查询最新观察。"
          : observation.execution_gate === "blocked_attempt_date_constraints_not_checked"
            ? "账户资料齐全后，仍须在尝试日前核实开盘价、成交容量、停牌／涨跌停和费用。"
            : "保持研究参考；只有相关数据与执行条件均经核实后，才重新判断是否可尝试。";
  const sourceStatus = observation.source_freshness?.origin_authenticated === false
    ? "行情来源未独立认证"
    : observation.source_freshness?.origin_authenticated === true
      ? "行情来源身份已核实"
      : "行情来源认证状态未核实";
  const evidenceLevel = observation.evidence_level === "低"
    ? "证据强度低"
    : observation.evidence_level
      ? `证据强度${observation.evidence_level}`
      : "证据强度未核实";
  const modelCashValue = observation.model_account_cash_cny?.trim()
    ? Number(observation.model_account_cash_cny)
    : Number.NaN;
  const modelCashText = observation.model_account_cash_cny != null && Number.isFinite(modelCashValue)
    ? new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(modelCashValue)
    : display(observation.model_account_cash_cny);

  return {
    observationLabel: historical ? "历史行情快照" : "本次行情观察",
    decisionTitle: "当前无法判断是否买卖",
    currentDecisionReason,
    historicalDecisionText: historical
      ? `快照当时的研究操作判断：${actionLabel}；仅代表该快照记录，不能作为当前买卖判断。`
      : null,
    signalText: available
      ? `${historical ? "本快照记录的最近有效月末信号" : "最近有效月末信号"}：${display(observation.signal_date)}${observation.supersedes_signal_date ? `（替代 ${observation.supersedes_signal_date} 的旧目标）` : ""}；行情数据截至 ${display(observation.latest_market_data_date)}。`
      : `未生成有效月末信号：${observation.failure_message ?? "行情数据不足或无法核验。"}`,
    targetText: available && observation.target_weight_percentage != null
      ? `目标仓位 ${display(observation.target_weight_percentage)}%（按 ${display(observation.signal_date)} 月末信号计算，月中不按价格变化重算）。`
      : "没有可核验的目标仓位。",
    modelText: available && observation.model_reference_shares != null
      ? `${modelCashText} 元模型参考：${observation.model_reference_shares} 份，按 ${display(observation.signal_date)} 信号日收盘价 ${display(observation.target_price_raw_cny)} 元计算；不是实际账户买入数量。`
      : "没有可核验的模型参考份额。",
    accountText: `${accountText}${!historical && observation.retry_rule?.includes("不跟踪") ? " 未完成委托状态本页不跟踪。" : ""}`,
    oldTargetAttemptText: !available
      ? "旧目标下一可能尝试日尚未核实。"
      : expired
        ? `旧目标有效期截至 ${display(observation.target_valid_until)}，已过期；不再作为尝试依据。`
        : nextAttempt,
    nextSignalText,
    nextStepText,
    executionText: "任何未来尝试都须核实实际持仓、现金、可卖数量、开盘价、成交容量、停牌或涨跌停及费用；本页不下单，条件未齐前只作研究参考。",
    explanationSourceText: "判断理由由确定性规则和固定说明模板生成；本页未调用真实 LLM，也未保存模型生成的解释。",
    caveatText: `正式策略资格未授予；仅研究参考。${sourceStatus}；${evidenceLevel}${historical ? "；历史快照不是当前行情。" : "。"}`,
  };
}

function updateSnapshotQuery(snapshotId: string | null) {
  const url = new URL(window.location.href);
  if (snapshotId) url.searchParams.set("card021_snapshot", snapshotId);
  else url.searchParams.delete("card021_snapshot");
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

export default function Card021LiveSignalPanel({
  snapshotId = null,
}: Card021LiveSignalPanelProps) {
  const [observation, setObservation] = useState<Card021Observation | null>(null);
  const [loading, setLoading] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);
  const requestVersionRef = useRef(0);
  const savedSnapshot = observation?.snapshot_mode === "saved_market_snapshot" || observation?.snapshot_historical === true;
  const summary = observation ? buildCard021Summary(observation) : null;

  useEffect(() => {
    const requestedSnapshotId: string = snapshotId ?? "";
    if (requestedSnapshotId.length === 0) return;
    const requestVersion = ++requestVersionRef.current;
    let active = true;
    async function loadSavedSnapshot() {
      setLoading(true);
      setRequestError(null);
      setObservation(null);
      try {
        const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";
        const response = await fetch(
          `${apiBase}/api/research/card021/510880/snapshots/${encodeURIComponent(requestedSnapshotId)}`,
          { method: "GET", cache: "no-store" },
        );
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error("保存的行情快照不存在或无法核对。");
        if (payload.status !== "available" && payload.status !== "unavailable") {
          throw new Error("保存的行情快照格式无法核验，未展示。");
        }
        if (active && requestVersionRef.current === requestVersion) {
          setObservation(payload as Card021Observation);
        }
      } catch (error) {
        if (active && requestVersionRef.current === requestVersion) {
          setRequestError(error instanceof Error ? error.message : "保存的行情快照暂不可用。");
        }
      } finally {
        if (active && requestVersionRef.current === requestVersion) setLoading(false);
      }
    }
    loadSavedSnapshot();
    return () => { active = false; };
  }, [snapshotId]);

  async function loadObservation() {
    const requestVersion = ++requestVersionRef.current;
    updateSnapshotQuery(null);
    setLoading(true);
    setRequestError(null);
    setObservation(null);
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";
      const response = await fetch(`${apiBase}/api/research/card021/510880/live-observation`, {
        method: "GET",
        cache: "no-store",
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error("最新观察暂不可用，请稍后重试。");
      if (payload.status !== "available" && payload.status !== "unavailable") {
        throw new Error("观察结果格式无法核验，未展示。");
      }
      if (requestVersionRef.current === requestVersion) {
        setObservation(payload as Card021Observation);
        if (typeof payload.snapshot_id === "string") updateSnapshotQuery(payload.snapshot_id);
      }
    } catch (error) {
      if (requestVersionRef.current === requestVersion) {
        setRequestError(error instanceof Error ? error.message : "最新观察暂不可用，请稍后重试。");
      }
    } finally {
      if (requestVersionRef.current === requestVersion) setLoading(false);
    }
  }

  return (
    <section aria-label="510880 实时研究观察" className="rounded-md border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">510880 月末波动预算观察</h3>
          <p className="mt-1 text-xs leading-5 text-slate-600">
            {savedSnapshot
              ? "当前为历史行情快照；刷新只读取本条保存结果，不查询新行情或账户数据。"
              : snapshotId && !observation
                ? "正在读取指定的历史行情快照；此操作不查询新行情或账户数据。"
                : "复用固定修订3规则；点击查询时才读取已配置行情来源和既有用户确认成交记录，不核实券商持仓，也不创建交易计划或订单。"}
          </p>
        </div>
        <button
          type="button"
          onClick={loadObservation}
          disabled={loading}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800 disabled:cursor-wait disabled:opacity-50"
        >
          {loading ? "正在查询…" : "查询最新观察"}
        </button>
      </div>

      {requestError && <p role="alert" className="mt-3 text-sm text-red-700">{requestError}</p>}
      {observation && summary && (
        <div role={observation.status === "available" ? "status" : "alert"} className="mt-4 space-y-3 border-t border-slate-200 pt-4">
          <p className="text-xs font-medium text-slate-500">{summary.observationLabel} · {observation.strategy_id} · 修订 {observation.protocol_revision}</p>
          <section aria-label="当前买卖判断" className="rounded border border-amber-300 bg-amber-50 p-4 text-slate-950">
            <h4 className="text-sm font-semibold">当前买卖判断</h4>
            <p className="mt-1 text-xl font-bold">{summary.decisionTitle}</p>
            {summary.historicalDecisionText && <p className="mt-2 text-sm text-slate-700">{summary.historicalDecisionText}</p>}
            <p className="mt-2 text-sm leading-6">{summary.currentDecisionReason}</p>
            <p className="mt-2 text-sm leading-6">{summary.accountText}</p>
            <p className="mt-3 text-sm leading-6"><span className="font-semibold">下一步：</span>{summary.nextStepText}</p>
            <p className="mt-2 text-xs leading-5 text-slate-600">{summary.explanationSourceText}</p>
          </section>

          <section aria-label="最近有效月末目标与下一信号" className="space-y-2 rounded border border-slate-200 p-4">
            <h4 className="text-sm font-semibold text-slate-900">最近有效月末目标与下一信号</h4>
            <p className="text-sm font-semibold leading-6 text-slate-900">{summary.signalText}</p>
            <p className="text-sm leading-6">{summary.targetText}</p>
            <p className="text-sm leading-6">{summary.modelText}</p>
            <p className="text-sm leading-6">{summary.oldTargetAttemptText}</p>
            <p className="text-sm font-medium leading-6">{summary.nextSignalText}</p>
            <p className="text-sm leading-6 text-slate-700">{summary.executionText}</p>
            <p className="text-sm font-semibold leading-6 text-amber-900">{summary.caveatText}</p>
          </section>

          <details className="rounded border border-slate-200 p-3">
            <summary className="cursor-pointer text-sm font-medium text-slate-800">技术证据与来源限制</summary>
            <div className="mt-3 space-y-2 break-all text-xs leading-5 text-slate-600">
              {observation.status === "unavailable" ? (
                <p>失败原因：{observation.failure_message ?? "行情数据未能核验。"} · 原因代码 {display(observation.failure_code)}</p>
              ) : (
                <>
                  <p>复权收盘窗口 {display(observation.signal_window_start)} 至 {display(observation.signal_window_end)} · 有效观察 {display(observation.valid_adjusted_close_count)} / 61 · 年化信号波动 {display(observation.signal_volatility)}</p>
                  <p>研究理由：{display(observation.research_rationale)} · 目标原始价格 {display(observation.target_price_raw_cny)} 元</p>
                  <p>旧目标最早规则尝试日 {display(observation.earliest_attempt_after_signal_date)} · 下次可能尝试日 {display(observation.next_possible_attempt_date)} · 有效截至 {display(observation.target_valid_until)} · 状态 {display(observation.target_validity_status)}</p>
                  <p>首次尝试状态 {display(observation.first_attempt_status)} · 重试策略状态 {display(observation.retry_policy_status)}</p>
                  <p>账户状态 {display(observation.account_data_status)} · 持仓 / 可卖份额 {display(observation.actual_shares)} / {display(observation.sellable_shares_as_of_latest_market_data)} · 账户目标 / 差额 {display(observation.account_target_shares)} / {display(observation.actual_delta_shares)} · 记录来源 {display(observation.account_source)}</p>
                  <p>执行门槛 {display(observation.execution_gate)} · 重试规则 {display(observation.retry_rule)}</p>
                  <p>整手 {display(observation.market_constraints?.round_lot_shares)} 份 · {display(observation.market_constraints?.t_plus_one)} · 成交容量 {display(observation.market_constraints?.volume_capacity_status)} / {display(observation.market_constraints?.volume_capacity_shares_for_next_possible_attempt)} 份 · 前一交易日成交量 {display(observation.market_constraints?.previous_session_volume_hands)} 手 · 执行价格 {display(observation.market_constraints?.execution_price)} · 停牌与涨跌停限制 {display(observation.market_constraints?.suspension_and_price_limits)}</p>
                  <p>佣金 {display(observation.market_constraints?.commission_rate)} · 最低佣金 {display(observation.market_constraints?.minimum_commission_cny)} 元 · 佣金比例上限 {display(observation.market_constraints?.commission_ratio_limit)} · 过滤门槛金额 {display(observation.market_constraints?.minimum_order_value_for_commission_filter_cny)} 元 · 其他费用 {display(observation.market_constraints?.other_fees)}</p>
                  <p>分红记录 {display(observation.dividend_source?.row_count)} 条 · 覆盖 {display(observation.dividend_source?.coverage)} · 信号窗口内复权因子变化逐日与已实施分红核对，窗口外完整性未独立审计。</p>
                </>
              )}
              <p>冻结协议 SHA-256 {display(observation.protocol_sha256)} · {observation.protocol_verified ? "已核对" : "未核对"}</p>
              <p>快照 {display(observation.snapshot_id)} · 输入 SHA-256 {display(observation.market_input_sha256)} · 结果 SHA-256 {display(observation.market_result_sha256)}</p>
              <p>快照 SHA-256 {display(observation.snapshot_sha256)} · 实现 SHA-256 {display(observation.implementation_sha256)}</p>
              <p>判断时间 {display(observation.judgment_at)} · 获取时间 {display(observation.retrieved_at)} · 数据接收时间 {display(observation.received_at)} · 市场源数据截至 {display(observation.source_freshness?.market_data_as_of ?? observation.latest_market_data_date)} · 交易日历覆盖至 {display(observation.source_freshness?.calendar_coverage_through)} · 分红源覆盖 {display(observation.source_freshness?.dividend_coverage)}</p>
              <p>行情来源身份 {observation.source_freshness?.origin_authenticated === true ? "已核实" : observation.source_freshness?.origin_authenticated === false ? "未认证" : "认证状态未核实"}；接口未做来源签名认证。</p>
              <p>查询端点：{(observation.sources ?? []).map((source) => `${source.endpoint} ${display(source.row_count)} 条（请求 ${display(source.request_started_at)}，收到 ${display(source.received_at)}）`).join(" · ") || "未获取"}</p>
            </div>
          </details>
        </div>
      )}
    </section>
  );
}
