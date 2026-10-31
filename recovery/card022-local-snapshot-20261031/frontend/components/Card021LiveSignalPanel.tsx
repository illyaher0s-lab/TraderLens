"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import LiveLoopPanel from "@/components/LiveLoopPanel";

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
  snapshot_mode?: "live_observation" | "saved_market_snapshot" | "saved_practice_observation";
  practice_observation_id?: string;
  practice_observation_sha256?: string;
  practice_observation_created_at?: string;
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
  account_cash_cny?: string | null;
  account_nav_at_signal_cny?: string | null;
  account_mode?: string;
  selected_account_mode?: "actual" | "simulated_practice";
  account_revision?: number | null;
  account_as_of_date?: string | null;
  account_valuation_date?: string | null;
  suggested_quantity_shares?: number | null;
  suggested_action_date?: string | null;
  research_action_reason?: string;
  execution_gate?: string;
  action_decision: string;
  research_rationale?: string;
  earliest_attempt_after_signal_date?: string;
  first_attempt_status?: string;
  next_possible_attempt_date?: string;
  target_valid_until?: string;
  target_validity_status?: string;
  execution_opportunity_status?: string;
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
  market_data_freshness?: {
    status?: string;
    timezone?: string;
    cutoff_time_local?: string;
    expected_data_date?: string | null;
    last_available_date?: string | null;
    missing_endpoints?: string[];
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
  practiceObservationId?: string | null;
};

function display(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" ? "未获取" : String(value);
}

function isLegacyNoAttemptObservation(observation: Card021Observation): boolean {
  if (
    observation.execution_opportunity_status
    || observation.target_validity_status !== "expired"
    || observation.execution_gate !== "blocked_target_expired"
    || !observation.target_valid_until
    || !observation.next_possible_attempt_date
    || observation.next_possible_attempt_date <= observation.target_valid_until
  ) return false;
  const time = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):\d{2}(?:\.\d+)?([+-]\d{2}:\d{2})$/.exec(observation.judgment_at ?? "");
  return Boolean(
    time
    && time[1] === observation.target_valid_until
    && time[4] === "+08:00"
    && Number(time[2]) < 15,
  );
}

export function buildCard021Summary(observation: Card021Observation) {
  const savedMarket = observation.snapshot_mode === "saved_market_snapshot";
  const savedPractice = observation.snapshot_mode === "saved_practice_observation";
  const historical = savedMarket || savedPractice || observation.snapshot_historical === true;
  const available = observation.status === "available";
  const legacyNoAttempt = isLegacyNoAttemptObservation(observation);
  const expired = !legacyNoAttempt && (
    observation.target_validity_status === "expired" || observation.execution_gate === "blocked_target_expired"
  );
  const noRemainingAttempt = legacyNoAttempt
    || observation.execution_opportunity_status === "none_before_expiry"
    || observation.execution_gate === "blocked_no_valid_execution_attempt";
  const noRemainingAttemptText = `旧目标有效期截至 ${display(observation.target_valid_until)} 收盘，但本日开盘尝试时点已过；下次可能尝试日 ${display(observation.next_possible_attempt_date)} 超出有效期，本期无剩余合规尝试机会。`;
  const targetTimeStatusText = legacyNoAttempt
    ? `有效至 ${display(observation.target_valid_until)} 收盘`
    : observation.target_validity_status === "expired"
      ? "已过期"
      : observation.target_validity_status === "active_until_next_month_end"
        ? "有效至下一月末收盘"
        : "未核实";
  const executionOpportunityText = noRemainingAttempt
    ? "本期无剩余合规尝试机会"
    : observation.execution_opportunity_status === "available_before_expiry"
      ? "有效期内仍有可尝试日"
      : "未核实";
  const retryPolicyText = noRemainingAttempt
    ? "无剩余有效尝试日"
    : display(observation.retry_policy_status);
  const actionLabel = ({
    buy: "研究参考方向：买入",
    sell: "研究参考方向：卖出",
    hold: "研究参考方向：持有",
    no_action: "研究参考方向：暂不操作",
    not_decidable: "暂不可判断",
  } as Record<string, string>)[observation.action_decision] ?? "暂不可判断";
  const isPractice = observation.selected_account_mode === "simulated_practice"
    || observation.account_mode === "simulated_practice";
  const marketFreshness = observation.market_data_freshness;
  const expectedDataDate = marketFreshness?.expected_data_date;
  const lastAvailableDate = marketFreshness?.last_available_date;
  const cutoffTime = marketFreshness?.cutoff_time_local;
  const isExpectedMonthEnd = Boolean(
    expectedDataDate && observation.target_valid_until === expectedDataDate,
  );
  const waitingForMonthEndClose = isExpectedMonthEnd
    && marketFreshness?.status === "awaiting_market_close";
  const waitingForMonthEndData = isExpectedMonthEnd
    && marketFreshness?.status === "awaiting_data_cutoff";
  const missingMonthEndData = isExpectedMonthEnd
    && marketFreshness?.status === "same_day_data_missing"
    && observation.target_validity_status === "expired";
  const oldTargetExpiredWaitingForData = observation.target_validity_status === "expired"
    && (waitingForMonthEndData || missingMonthEndData);
  const missingEndpointLabels = (marketFreshness?.missing_endpoints ?? []).map((endpoint) => ({
    fund_daily: "日行情",
    fund_adj: "复权因子",
    trade_cal: "交易日历",
  } as Record<string, string>)[endpoint] ?? endpoint);
  const marketDataStatusText = marketFreshness?.status === "awaiting_market_close"
    ? `${display(expectedDataDate)} 尚未收盘；行情完整数据截至 ${display(lastAvailableDate)}。月末信号须待实际收盘后再确认。`
    : marketFreshness?.status === "awaiting_data_cutoff"
      ? `${display(expectedDataDate)} 已收盘；当前完整行情截至 ${display(lastAvailableDate)}。服务端可查询时点为 ${display(cutoffTime)}（${display(marketFreshness.timezone)}）。`
      : marketFreshness?.status === "current"
        ? `本次已取得截至 ${display(lastAvailableDate ?? expectedDataDate)} 的行情与复权数据。`
        : marketFreshness?.status === "same_day_data_missing"
          ? `已过服务端可查询时点，但 ${display(expectedDataDate)} 缺少${missingEndpointLabels.join("、") || "必要行情数据"}；最近共同数据截至 ${display(lastAvailableDate)}。`
          : marketFreshness?.status === "required_data_missing"
            ? `计算所需行情不完整；最近共同数据截至 ${display(lastAvailableDate)}${missingEndpointLabels.length ? `，缺少${missingEndpointLabels.join("、")}` : ""}。`
            : marketFreshness?.status === "source_query_failed"
              ? `行情来源查询失败；最近共同数据截至 ${display(lastAvailableDate)}。`
              : "行情数据更新时间尚未核实。";
  const accountText = savedMarket
    ? "这条历史行情快照没有保存或读取持仓、可卖份额、现金和分红应收。"
    : !available
      ? `行情数据未齐，本次未读取${isPractice ? "模拟账户" : "账户资料"}；没有生成账户目标或执行方向，当前余额不替代旧信号 NAV。`
    : isPractice
      ? observation.account_data_status === "simulated_practice_account_available"
        ? `Card022 模拟练习账户（非实际账户）：当前现金 ¥${display(observation.account_cash_cny)}，信号日 NAV ¥${display(observation.account_nav_at_signal_cny)}（与当前现金分开），份额 ${display(observation.actual_shares)}，账户版本 ${display(observation.account_revision)}；账户状态截至 ${display(observation.account_as_of_date)}，估值行情截至 ${display(observation.account_valuation_date)}。`
        : observation.account_data_status === "account_opened_after_signal_date"
          ? `模拟账户于 ${display(observation.account_as_of_date)} 开立，晚于冻结信号日 ${display(observation.signal_date)}；当前余额不能代替信号日 NAV。`
          : observation.account_data_status === "account_state_date_mismatch"
            ? "模拟账户状态日期与本次查询日期不一致，本次不展示持仓差额或操作方向。"
            : observation.account_data_status === "unmodeled_dividend_entitlement"
              ? "模拟账户持有期间出现未入账分红，本次账户 NAV 和操作方向停止计算。"
              : "模拟练习账户尚未初始化或账户数据无法核实，本次不展示操作方向。"
      : observation.account_data_status === "no_user_confirmed_records"
        ? "当前使用实际成交记录；没有可核实的用户确认成交记录，持仓、可卖份额、现金和分红应收不足以计算实际账户方向；实际买卖数量无法确定。"
        : observation.account_data_status === "position_confirmed_nav_missing"
          ? "当前使用实际成交记录；持仓记录未经券商核实，现金或分红应收缺失，不能计算实际账户方向。"
          : observation.account_data_status === "provenance_unverified"
            ? "实际成交记录的来源或确认状态无法核实，本次不展示账户差额。"
            : "当前使用实际成交记录；实际账户资金信息不足，不能据此给出操作方向。";
  const currentDecisionReason = savedPractice
    ? noRemainingAttempt && !expired
      ? `这是保存的模拟账户观察。${noRemainingAttemptText} 点击查询最新观察可读取当前行情和账户版本。`
      : "这是保存时的模拟账户观察，用于刷新后核对同一份记录；点击查询最新观察可读取当前行情和账户版本。"
    : savedMarket
      ? "这是历史行情快照，没有当前账户资料；点击查询最新观察读取当前状态。"
    : !available
    ? oldTargetExpiredWaitingForData
      ? "旧目标已失效；月末行情尚未齐备，本次没有生成新信号。"
      : "行情数据不足或未通过核验，本次没有可用目标。"
    : expired
      ? "旧目标已过有效期，不能作为当前交易依据。"
      : noRemainingAttempt
        ? noRemainingAttemptText
    : isPractice && observation.account_data_status === "account_opened_after_signal_date"
      ? "缺少冻结信号日的账户 NAV；不会用现在的 5000 元余额回填历史目标。"
      : isPractice && observation.account_data_status !== "simulated_practice_account_available"
        ? observation.research_action_reason ?? "模拟账户信息不足，本次不计算操作方向。"
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
              ? observation.research_action_reason ?? "研究方向按固定规则生成，仅供研究参考。"
              : observation.research_rationale ?? "账户信息或执行条件尚未完整核实。";
  const nextAttempt = observation.next_possible_attempt_date
    ? `旧目标下一可能尝试日：${observation.next_possible_attempt_date}（须在有效期内并通过执行核验；不是新买入信号）。`
    : "旧目标下一可能尝试日尚未核实，不代表可以执行。";
  const oldTargetAttemptText = !available
    ? "旧目标下一可能尝试日尚未核实。"
    : expired
      ? `旧目标有效期截至 ${display(observation.target_valid_until)} 收盘，现已过期；不再作为尝试依据。`
      : noRemainingAttempt
        ? noRemainingAttemptText
        : nextAttempt;
  const monthEndNextSignalText = oldTargetExpiredWaitingForData
    ? missingMonthEndData
      ? `旧目标已失效；${display(expectedDataDate)} 新月末信号等数据补齐后再查询。`
      : `旧目标已失效；${display(expectedDataDate)} 新月末信号等服务端 ${display(cutoffTime)} 后的数据。`
    : waitingForMonthEndClose
      ? `${display(expectedDataDate)} 新月末信号须待实际收盘后查询；当前完整行情截至 ${display(lastAvailableDate)}。`
      : null;
  const nextSignalText = monthEndNextSignalText
    ?? (!available
    ? "下一月末信号日期尚无完整证据；须等实际 SSE 月末交易日收盘并取得行情数据后再核实。"
    : expired || noRemainingAttempt
      ? observation.target_valid_until
        ? `下一月末信号候选日为 ${observation.target_valid_until}；须等实际收盘行情到齐后才能确认新信号。`
        : "下一月末信号日期尚无完整证据；须等实际 SSE 月末交易日收盘并取得行情数据后再核实。"
    : observation.target_valid_until
      ? `下一月末新目标须在 ${observation.target_valid_until} 收盘后生成。`
      : "下一月末信号日期尚无完整证据；须等实际 SSE 月末交易日收盘并取得行情数据后再核实。");
  const monthEndNextStepText = oldTargetExpiredWaitingForData
    ? missingMonthEndData
      ? `等待 ${display(expectedDataDate)} 缺失行情数据补齐后再查询；不沿用旧目标。`
      : `旧目标已失效；已收盘，等待服务端 ${display(cutoffTime)} 后行情数据到齐后再查询；不沿用旧目标。`
    : waitingForMonthEndClose
      ? `等待 ${display(expectedDataDate)} 实际收盘及行情数据到齐后再查询；当前不沿用旧目标方向。`
      : null;
  const nextStepText = monthEndNextStepText ?? (savedPractice
    ? noRemainingAttempt && !expired
      ? "保存记录中的旧目标仍在当日收盘前有效，但本期没有剩余合规尝试日；点击查询最新观察获取当前行情，不沿用旧目标方向。"
      : "刷新后读取的是同一条保存记录；点击查询最新观察，重新获取行情和当前模拟账户版本。"
    : !available
    ? "等待完整且可核验的行情后，再查询最新观察；本次没有目标，不按模型参考份额操作。"
    : expired
      ? "旧目标已经过期；等待实际月末收盘后取得新行情，再查看新目标，不沿用旧目标。"
      : noRemainingAttempt
        ? "本期没有剩余合规尝试机会；等待月末收盘并取得完整行情后，再核实新信号，不沿用旧方向。"
      : isPractice && observation.account_data_status !== "simulated_practice_account_available"
        ? "等待账户状态与冻结信号日对齐；本次不生成买入、卖出或持有方向。"
        : isPractice && observation.action_decision === "buy"
          ? "如选择模拟练习，可在下方登记已确认的模拟成交；填写真实模拟成交价和日期后再确认，系统不会下单。"
          : isPractice && observation.action_decision === "sell"
            ? "如选择模拟练习，进入该模拟账户持仓登记已确认卖出；系统会核对可卖份额和 T+1。"
            : isPractice
              ? "当前方向仅为研究参考；不需要模拟成交时可保持账户状态不变。"
      : historical
        ? "点击“查询最新观察”获取当前行情；再通过现有账户／成交确认路径核实持仓、现金和分红应收，并人工核对未完成委托。"
        : observation.account_data_status === "no_user_confirmed_records" || observation.execution_gate === "blocked_missing_account_nav_or_cash"
          ? "通过现有账户／成交确认路径核实持仓、现金和分红应收，并人工核对未完成委托；资料齐全后再查询最新观察。"
          : observation.execution_gate === "blocked_attempt_date_constraints_not_checked"
            ? "账户资料齐全后，仍须在尝试日前核实开盘价、成交容量、停牌／涨跌停和费用。"
            : "保持研究参考；只有相关数据与执行条件均经核实后，才重新判断是否可尝试。");
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
  const suppressCurrentDirection = !available
    || expired
    || noRemainingAttempt
    || (isPractice && observation.account_data_status !== "simulated_practice_account_available")
    || (!isPractice && (
      observation.action_decision === "not_decidable"
      || !observation.execution_gate
      || observation.execution_gate.startsWith("blocked_")
    ));

  return {
    observationLabel: savedPractice ? "保存的模拟账户观察" : historical ? "历史行情快照" : "本次行情观察",
    decisionTitle: historical
      ? "保存的观察记录"
      : oldTargetExpiredWaitingForData
        ? "旧目标已失效；新月末信号等数据"
      : waitingForMonthEndClose && noRemainingAttempt
        ? "本期无剩余尝试；新月末信号待收盘"
      : suppressCurrentDirection
        ? "当前无法判断是否买卖"
      : ({
          buy: "研究方向：买入（仅研究参考）",
          sell: "研究方向：卖出（仅研究参考）",
          hold: "研究方向：持有",
          no_action: "研究方向：暂不操作",
          not_decidable: "当前无法判断是否买卖",
        } as Record<string, string>)[observation.action_decision] ?? "当前无法判断是否买卖",
    currentDecisionReason,
    targetTimeStatusText,
    executionOpportunityText,
    retryPolicyText,
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
    marketDataStatusText,
    oldTargetAttemptText,
    nextSignalText,
    nextStepText,
    executionText: "任何未来尝试都须核实实际持仓、现金、可卖数量、开盘价、成交容量、停牌或涨跌停及费用；本页不下单，条件未齐前只作研究参考。",
    explanationSourceText: "判断理由由确定性规则和固定说明模板生成；本页未调用真实 LLM，也未保存模型生成的解释。",
    caveatText: `正式策略资格未授予；仅研究参考。${sourceStatus}；${evidenceLevel}${historical ? "；历史快照不是当前行情。" : "。"}`,
  };
}

function updateObservationQuery(
  accountMode: "actual" | "simulated_practice",
  snapshotId: string | null,
  practiceObservationId: string | null,
) {
  const url = new URL(window.location.href);
  if (snapshotId) url.searchParams.set("card021_snapshot", snapshotId);
  else url.searchParams.delete("card021_snapshot");
  if (practiceObservationId) url.searchParams.set("card021_observation", practiceObservationId);
  else url.searchParams.delete("card021_observation");
  url.searchParams.set("card021_account_mode", accountMode);
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

export default function Card021LiveSignalPanel({
  snapshotId = null,
  practiceObservationId = null,
}: Card021LiveSignalPanelProps) {
  const [observation, setObservation] = useState<Card021Observation | null>(null);
  const [loading, setLoading] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [accountMode, setAccountMode] = useState<"actual" | "simulated_practice">("actual");
  const [practiceAccountStatus, setPracticeAccountStatus] = useState<{
    status: "not_initialized" | "existing" | "conflict";
    account_id?: string;
    cash_cents?: number;
    revision?: number;
    opened_at?: string;
  } | null>(null);
  const [practiceAccountError, setPracticeAccountError] = useState<string | null>(null);
  const [initializingPracticeAccount, setInitializingPracticeAccount] = useState(false);
  const requestVersionRef = useRef(0);
  const savedSnapshot = observation?.snapshot_mode === "saved_market_snapshot"
    || observation?.snapshot_mode === "saved_practice_observation"
    || observation?.snapshot_historical === true;
  const summary = observation ? buildCard021Summary(observation) : null;

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const mode = params.get("card021_account_mode");
    if (mode === "actual" || mode === "simulated_practice") setAccountMode(mode);
  }, []);

  async function loadPracticeAccountStatus() {
    const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";
    try {
      const response = await fetch(`${apiBase}/api/research/card021/practice-account`, { cache: "no-store" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "模拟练习账户状态无法核实。");
      setPracticeAccountStatus(payload as typeof practiceAccountStatus);
      setPracticeAccountError(null);
    } catch (error) {
      setPracticeAccountStatus({ status: "conflict" });
      setPracticeAccountError(error instanceof Error ? error.message : "模拟练习账户状态无法核实。");
    }
  }

  useEffect(() => {
    if (accountMode === "simulated_practice") loadPracticeAccountStatus();
  }, [accountMode]);

  useEffect(() => {
    const requestedObservationId = practiceObservationId ?? "";
    const requestedSnapshotId = snapshotId ?? "";
    if (!requestedObservationId && !requestedSnapshotId) return;
    const requestVersion = ++requestVersionRef.current;
    let active = true;
    async function loadSavedObservation() {
      setLoading(true);
      setRequestError(null);
      setObservation(null);
      try {
        const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";
        const url = requestedObservationId
          ? `${apiBase}/api/research/card021/510880/practice-observations/${encodeURIComponent(requestedObservationId)}`
          : `${apiBase}/api/research/card021/510880/snapshots/${encodeURIComponent(requestedSnapshotId)}`;
        const response = await fetch(url, { method: "GET", cache: "no-store" });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error("保存的观察不存在或无法核对。");
        if (payload.status !== "available" && payload.status !== "unavailable") {
          throw new Error("保存的观察格式无法核验，未展示。");
        }
        if (active && requestVersionRef.current === requestVersion) {
          setObservation(payload as Card021Observation);
        }
      } catch (error) {
        if (active && requestVersionRef.current === requestVersion) {
          setRequestError(error instanceof Error ? error.message : "保存的观察暂不可用。");
        }
      } finally {
        if (active && requestVersionRef.current === requestVersion) setLoading(false);
      }
    }
    loadSavedObservation();
    return () => { active = false; };
  }, [snapshotId, practiceObservationId]);

  async function initializePracticeAccount() {
    setInitializingPracticeAccount(true);
    setPracticeAccountError(null);
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";
      const response = await fetch(`${apiBase}/api/research/card021/practice-account/initialize`, { method: "POST" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 409) setPracticeAccountStatus({ status: "conflict" });
        throw new Error(payload.detail || "模拟练习账户未初始化。");
      }
      await loadPracticeAccountStatus();
      await loadObservation();
    } catch (error) {
      setPracticeAccountError(error instanceof Error ? error.message : "模拟练习账户未初始化。");
    } finally {
      setInitializingPracticeAccount(false);
    }
  }

  async function loadObservation() {
    const requestVersion = ++requestVersionRef.current;
    updateObservationQuery(accountMode, null, null);
    setLoading(true);
    setRequestError(null);
    setObservation(null);
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";
      const response = await fetch(`${apiBase}/api/research/card021/510880/live-observation?account_mode=${encodeURIComponent(accountMode)}`, {
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
        if (accountMode === "simulated_practice" && typeof payload.practice_observation_id === "string") {
          updateObservationQuery(accountMode, null, payload.practice_observation_id);
        } else if (typeof payload.snapshot_id === "string") {
          updateObservationQuery(accountMode, payload.snapshot_id, null);
        }
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
              ? observation?.snapshot_mode === "saved_practice_observation"
                ? "正在显示同一条已保存的模拟账户观察；刷新不读取新行情，点击查询最新观察才更新账户版本。"
                : "正在显示历史行情快照；刷新只读取本条市场记录，不读取账户数据。"
              : accountMode === "simulated_practice"
                ? "当前选择 Card022 模拟练习账户，初始资金 5000 元；与实际账户完全分开。固定修订3只生成研究参考，不会下单。"
                : "当前选择实际成交记录，只读且未经券商核实；现金或分红应收不足时不生成账户方向。固定修订3不下单。"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs text-slate-600">
            账户数据
            <select
              aria-label="账户数据类型"
              value={accountMode}
              onChange={(event) => {
                const mode = event.target.value as "actual" | "simulated_practice";
                setAccountMode(mode);
                setObservation(null);
                setRequestError(null);
                updateObservationQuery(mode, null, null);
              }}
              className="ml-2 rounded border border-slate-300 bg-white px-2 py-2 text-sm text-slate-800"
            >
              <option value="actual">实际成交记录</option>
              <option value="simulated_practice">模拟练习账户</option>
            </select>
          </label>
          <button
            type="button"
            onClick={loadObservation}
            disabled={loading}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800 disabled:cursor-wait disabled:opacity-50"
          >
            {loading ? "正在查询…" : "查询最新观察"}
          </button>
        </div>
      </div>

      {requestError && <p role="alert" className="mt-3 text-sm text-red-700">{requestError}</p>}
      {accountMode === "simulated_practice" && (
        <div className="mt-3 flex flex-wrap items-center gap-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">
          {practiceAccountStatus?.status === "not_initialized" ? (
            <>
              <span>模拟练习账户尚未初始化。</span>
              <button
                type="button"
                onClick={initializePracticeAccount}
                disabled={initializingPracticeAccount || loading}
                className="rounded border border-amber-500 px-3 py-1.5 font-medium disabled:opacity-50"
              >
                {initializingPracticeAccount ? "正在初始化…" : "初始化 5000 元模拟账户"}
              </button>
            </>
          ) : practiceAccountStatus?.status === "existing" ? (
            <>
              <span>模拟账户余额 ¥{((practiceAccountStatus.cash_cents ?? 0) / 100).toFixed(2)} · 版本 {practiceAccountStatus.revision}</span>
              <Link href="/observations?practice_account_id=card022-510880" className="font-medium underline">
                打开模拟持仓与复盘
              </Link>
            </>
          ) : practiceAccountError ? (
            <span role="alert">{practiceAccountError}</span>
          ) : (
            <span>正在核对模拟练习账户…</span>
          )}
        </div>
      )}
      {practiceAccountError && accountMode === "simulated_practice" && practiceAccountStatus?.status !== "conflict" && (
        <p role="alert" className="mt-2 text-sm text-red-700">{practiceAccountError}</p>
      )}
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
            <p className="text-sm leading-6 text-slate-700">行情更新时间：{summary.marketDataStatusText}</p>
            <p className="text-sm font-semibold leading-6 text-slate-900">{summary.signalText}</p>
            <p className="text-sm leading-6">{summary.targetText}</p>
            <p className="text-sm leading-6">{summary.modelText}</p>
            <p className="text-sm leading-6">{summary.oldTargetAttemptText}</p>
            <p className="text-sm font-medium leading-6">{summary.nextSignalText}</p>
            <p className="text-sm leading-6 text-slate-700">{summary.executionText}</p>
            <p className="text-sm font-semibold leading-6 text-amber-900">{summary.caveatText}</p>
          </section>

          {!savedSnapshot
            && accountMode === "simulated_practice"
            && practiceAccountStatus?.status === "existing"
            && observation.account_data_status === "simulated_practice_account_available"
            && observation.action_decision === "buy"
            && typeof observation.suggested_quantity_shares === "number"
            && observation.suggested_quantity_shares > 0
            && typeof observation.account_revision === "number"
            && observation.practice_observation_id && (
              <section aria-label="登记已确认的模拟买入" className="space-y-2 rounded border border-amber-200 p-4">
                <h4 className="text-sm font-semibold text-slate-900">记录模拟成交</h4>
                <p className="text-sm leading-6 text-slate-700">
                  仅当你已按冻结规则完成模拟成交后登记。填写实际模拟成交价和日期；本页不下单，也不替你推定成交价。
                </p>
                <LiveLoopPanel
                  conversationId={null}
                  practiceAccountId="card022-510880"
                  practiceExecutionOrigin="strategy_linked"
                  practiceAccountRevision={observation.account_revision}
                  initialSymbol="510880"
                  initialQuantity={observation.suggested_quantity_shares}
                  practiceObservationId={observation.practice_observation_id}
                  onUpdate={loadObservation}
                />
              </section>
            )}

          {!savedSnapshot
            && accountMode === "simulated_practice"
            && practiceAccountStatus?.status === "existing"
            && observation.account_data_status === "simulated_practice_account_available"
            && observation.action_decision === "sell"
            && observation.practice_observation_id && (
              <section aria-label="模拟持仓卖出与复盘入口" className="rounded border border-amber-200 p-4">
                <h4 className="text-sm font-semibold text-slate-900">模拟持仓卖出与复盘</h4>
                <p className="mt-1 text-sm leading-6 text-slate-700">当前方向为研究参考。进入同一模拟账户的持仓页，核对 T+1 和可卖份额后登记已完成的模拟卖出。</p>
                <Link
                  href={`/observations?practice_account_id=card022-510880&card021_observation=${encodeURIComponent(observation.practice_observation_id)}`}
                  className="mt-2 inline-block text-sm font-medium text-blue-700 underline"
                >
                  打开模拟持仓、卖出记录与复盘
                </Link>
              </section>
            )}

          <details className="rounded border border-slate-200 p-3">
            <summary className="cursor-pointer text-sm font-medium text-slate-800">技术证据与来源限制</summary>
            <div className="mt-3 space-y-2 break-all text-xs leading-5 text-slate-600">
              {observation.status === "unavailable" ? (
                <p>失败原因：{observation.failure_message ?? "行情数据未能核验。"} · 原因代码 {display(observation.failure_code)}</p>
              ) : (
                <>
                  <p>复权收盘窗口 {display(observation.signal_window_start)} 至 {display(observation.signal_window_end)} · 有效观察 {display(observation.valid_adjusted_close_count)} / 61 · 年化信号波动 {display(observation.signal_volatility)}</p>
                  <p>研究理由：{display(observation.research_rationale)} · 目标原始价格 {display(observation.target_price_raw_cny)} 元</p>
                  <p>账户数据范围：{observation.selected_account_mode === "simulated_practice" ? "Card022 模拟练习账户（独立账本）" : "实际成交记录（只读，未经券商核实）"} · 当前现金 {display(observation.account_cash_cny)} 元 · 账户版本 {display(observation.account_revision)} · 状态日期 {display(observation.account_as_of_date)}。</p>
                  <p>冻结目标 {display(observation.account_target_shares)} 份 · 当前份额 {display(observation.actual_shares)} 份 · 差额 {display(observation.actual_delta_shares)} 份 · 研究方向 {display(observation.action_decision)} · 建议数量 {display(observation.suggested_quantity_shares)} 份 · 日期 {display(observation.suggested_action_date)} · 理由 {display(observation.research_action_reason)}</p>
                  <p>旧目标最早规则尝试日 {display(observation.earliest_attempt_after_signal_date)} · 下次可能尝试日 {display(observation.next_possible_attempt_date)} · 有效截至 {display(observation.target_valid_until)} · 时间状态 {summary.targetTimeStatusText} · 执行机会 {summary.executionOpportunityText}</p>
                  <p>首次尝试状态 {display(observation.first_attempt_status)} · 重试策略状态 {summary.retryPolicyText}</p>
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
              {observation.practice_observation_id && <p>模拟观察 {display(observation.practice_observation_id)} · 账户观察 SHA-256 {display(observation.practice_observation_sha256)} · 账户观察时间 {display(observation.practice_observation_created_at)}</p>}
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
