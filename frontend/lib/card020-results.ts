const EXPECTED_PATHS = [
  { id: "candidate-base", account: "candidate", cost: "base" },
  { id: "candidate-stress", account: "candidate", cost: "stress" },
  { id: "buy_and_hold-base", account: "buy_and_hold", cost: "base" },
  { id: "buy_and_hold-stress", account: "buy_and_hold", cost: "stress" },
  { id: "static_half-base", account: "static_half", cost: "base" },
  { id: "static_half-stress", account: "static_half", cost: "stress" },
] as const;

type PnlState = "profit" | "loss" | "flat" | "unknown";

export interface Card020OutcomeRow {
  pathId: string;
  accountLabel: string;
  costLabel: string;
  startingNavText: string;
  endingNavText: string;
  pnlText: string;
  pnlState: PnlState;
  returnText: string;
  drawdownAmountText: string;
  drawdownRatioText: string;
  commissionText: string;
  slippageText: string;
}

export interface Card020StaticHalfTradeoff {
  costLabel: string;
  candidateEndingNavHigher: boolean;
  staticHalfDrawdownLower: boolean;
  description: string;
}

export interface Card020OutcomeSummary {
  ready: boolean;
  metricsTrusted: boolean;
  issues: string[];
  periodText: string;
  pathScopeText: string;
  historyText: string;
  startingCapitalText: string;
  categoryLabel: string;
  categoryMessage: string;
  eligibilityText: string;
  evidenceText: string;
  sourceSummary: string[];
  criticalSourceGaps: string[];
  limitations: string[];
  rows: Card020OutcomeRow[];
  staticHalfTradeoffs: Card020StaticHalfTradeoff[];
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function numericText(value: unknown): string | null {
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : null;
  if (typeof value !== "string" || !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(value.trim())) return null;
  return value.trim();
}

function decimalParts(value: unknown): { negative: boolean; whole: string; fraction: string } | null {
  const raw = numericText(value);
  if (raw === null) return null;
  const negative = raw.startsWith("-");
  const unsigned = raw.replace(/^[+-]/, "");
  const [whole, fraction = ""] = unsigned.split(".");
  return {
    negative,
    whole: (whole || "0").replace(/^0+(?=\d)/, ""),
    fraction: fraction.replace(/0+$/, ""),
  };
}

function compareDecimals(left: unknown, right: unknown): number | null {
  const a = decimalParts(left);
  const b = decimalParts(right);
  if (!a || !b) return null;
  const aIsZero = /^0*$/.test(a.whole) && a.fraction === "";
  const bIsZero = /^0*$/.test(b.whole) && b.fraction === "";
  if (aIsZero && bIsZero) return 0;
  if (a.negative !== b.negative) return a.negative ? -1 : 1;
  const wholeA = a.whole.replace(/^0+(?=\d)/, "") || "0";
  const wholeB = b.whole.replace(/^0+(?=\d)/, "") || "0";
  let absoluteComparison = wholeA.length === wholeB.length
    ? (wholeA === wholeB ? 0 : wholeA > wholeB ? 1 : -1)
    : wholeA.length > wholeB.length ? 1 : -1;
  if (absoluteComparison === 0) {
    const scale = Math.max(a.fraction.length, b.fraction.length);
    let fractionA = a.fraction;
    let fractionB = b.fraction;
    while (fractionA.length < scale) fractionA += "0";
    while (fractionB.length < scale) fractionB += "0";
    absoluteComparison = fractionA === fractionB ? 0 : fractionA > fractionB ? 1 : -1;
  }
  return a.negative ? -absoluteComparison : absoluteComparison;
}

function displayNumber(value: unknown, digits: number, signed = false): string {
  const raw = numericText(value);
  const number = raw === null ? Number.NaN : Number(raw);
  if (!Number.isFinite(number)) return "未知";
  const text = new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Math.abs(number));
  const sign = number < 0 ? "-" : signed && number > 0 ? "+" : "";
  return sign + text;
}

export function formatCard020SummaryMoney(value: unknown, signed = false): string {
  const formatted = displayNumber(value, 2, signed);
  return formatted === "未知" ? formatted : formatted + " 元";
}

export function formatCard020RunStatus(value: unknown): string {
  if (typeof value !== "string") return "状态未知";
  const labels: Record<string, string> = {
    completed: "已完成",
    running: "运行中",
    failed: "失败",
  };
  return labels[value] || "状态未知";
}

function formatPercent(value: unknown, signed = false): string {
  const raw = numericText(value);
  if (raw === null) return "未知";
  const formatted = displayNumber(Number(raw) * 100, 2, signed);
  return formatted === "未知" ? formatted : formatted + "%";
}

function unknownRow(pathId: string, account: string, cost: string): Card020OutcomeRow {
  return {
    pathId, accountLabel: account, costLabel: cost,
    startingNavText: "未知", endingNavText: "未知", pnlText: "盈亏未知",
    pnlState: "unknown", returnText: "未知", drawdownAmountText: "未知",
    drawdownRatioText: "未知", commissionText: "未知", slippageText: "未知",
  };
}

function accountLabel(account: string): string {
  if (account === "candidate") return "动态波动预算候选";
  if (account === "buy_and_hold") return "买入持有";
  if (account === "static_half") return "静态半仓";
  return "账户未知";
}

function costLabel(cost: string): string {
  return cost === "base"
    ? "基础成本（单边滑点 0.05%）"
    : cost === "stress"
      ? "压力成本（单边滑点 0.10%）"
      : "成本情景未知";
}

function categoryFor(category: string, rawReasons: unknown): { label: string; message: string } | null {
  const reasons = Array.isArray(rawReasons)
    ? rawReasons.filter((reason): reason is string => typeof reason === "string")
    : [];
  const labels: Record<string, { label: string; message: string }> = {
    A: { label: "A 类｜支持继续研究", message: "这只是历史研究结果，不表示策略已可用于交易。" },
    B: { label: "B 类｜有效结果仍有取舍", message: "请结合基础/压力成本及分段结果理解收益与风险。" },
    C: { label: "C 类｜未满足额外动态调仓条件", message: "" },
    D: { label: "D 类｜关键数据或核账不可信", message: "证据不足，不能据此判断策略表现。" },
  };
  const categoryInfo = labels[category];
  if (!categoryInfo) return null;
  if (category === "C") {
    if (reasons.some((reason) => reason.includes("初始建仓以外，没有实际成交形成动态风险调整"))) {
      categoryInfo.message = "本次模拟没有出现初始建仓以外的实际调仓成交，因此未形成动态调仓证据。";
    } else if (reasons.some((reason) => reason.includes("同一简单对照在基础与压力成本下均支配候选"))) {
      categoryInfo.message = "同一个简单对照在基础和压力两种成本情景下均达到固定支配条件。";
    } else {
      categoryInfo.message = "批次标记为 C 类，但记录没有提供可识别的触发原因；具体原因未知。";
    }
  }
  return categoryInfo;
}

export function buildCard020OutcomeSummary(runRecordValue: unknown): Card020OutcomeSummary {
  const issues: string[] = [];
  const runRecord = asRecord(runRecordValue);
  const result = asRecord(runRecord?.result);
  const paths = asRecord(result?.paths);
  const reconciliation = asRecord(result?.reconciliation);
  const provenance = asRecord(result?.data_provenance);
  const market = asRecord(provenance?.market);
  const dividends = asRecord(provenance?.dividends);
  const rawLimitations = provenance?.data_limitations;
  const limitations = Array.isArray(rawLimitations)
    ? rawLimitations.filter((item): item is string => typeof item === "string" && item.trim() !== "")
    : [];
  const criticalSourceGaps = Array.isArray(provenance?.critical_source_gaps)
    ? provenance.critical_source_gaps.filter((item): item is string => typeof item === "string" && item.trim() !== "")
    : [];
  const sourceSummary: string[] = [];

  if (market?.provider_origin_authenticated === false) {
    sourceSummary.push("行情文件可核对哈希，但提供方来源未认证。");
  } else if (typeof market?.source_status === "string") {
    sourceSummary.push("行情来源真实性状态未知。");
  }
  if (typeof dividends?.source_status === "string" && dividends.source_status.includes("raw_unverified")) {
    const evidenceGap = typeof dividends.evidence_gap === "string" ? dividends.evidence_gap : "";
    const checkedDates = evidenceGap.match(/\b\d{4}-\d{2}-\d{2}\b/g) || [];
    const knownLimitedReview = /official announcement checks cover only/i.test(evidenceGap)
      && /do not establish full-history completeness/i.test(evidenceGap)
      && /independently verify every historical event/i.test(evidenceGap)
      && checkedDates.length >= 2;
    sourceSummary.push(knownLimitedReview
      ? "分红快照保留 raw_unverified（原始资料未验证）标记；官方公告核查仅覆盖 "
        + checkedDates.join(" 和 ")
        + "，不能证明完整历史覆盖，也未逐条独立核验所有历史事件。"
      : "分红快照保留 raw_unverified（原始资料未验证）标记；官方核查范围与历史完整性未知，原始说明见技术证据。");
  } else {
    sourceSummary.push("分红来源验证状态未知。");
  }

  const categoryCode = typeof result?.evaluation_category === "string" ? result.evaluation_category : "";
  const category = categoryFor(categoryCode, result?.category_reasons);
  const sha256Pattern = /^[A-Fa-f0-9]{64}$/;
  if (typeof runRecord?.run_id !== "string" || !runRecord.run_id.trim() || runRecord.status !== "completed") {
    issues.push("保存的外层批次编号或状态缺失、无效。");
  }
  if (typeof result?.freeze_id !== "string" || !result.freeze_id.trim()
    || typeof runRecord?.freeze_id !== "string" || runRecord.freeze_id !== result.freeze_id) {
    issues.push("外层批次冻结引用与不可变结果不一致。");
  }
  if (result?.run_status !== "completed") issues.push("模拟批次未完成。");
  if (result?.reconciliation_status !== "passed") issues.push("批次总核账未通过。");
  if (!category) issues.push("评价类别缺失或无法识别。");
  if (typeof result?.protocol_sha256 !== "string" || !sha256Pattern.test(result.protocol_sha256)
    || typeof result?.freeze_sha256 !== "string" || !sha256Pattern.test(result.freeze_sha256)
    || typeof result?.result_sha256 !== "string" || !sha256Pattern.test(result.result_sha256)
    || typeof result?.runner_sha256 !== "string" || !sha256Pattern.test(result.runner_sha256)
    || typeof result?.execution_bundle_sha256 !== "string" || !sha256Pattern.test(result.execution_bundle_sha256)
    || typeof result?.input_inventory_sha256 !== "string" || !sha256Pattern.test(result.input_inventory_sha256)) {
    issues.push("批次、冻结或执行版本引用缺失或格式无效。");
  }
  if (result?.formal_trade_qualification !== false || result?.acceptance_status !== "not_qualified") {
    issues.push("正式资格状态缺失或与研究边界不一致。");
  }
  if (result?.evidence_level !== "low" || result?.historical_reuse !== true || result?.not_out_of_sample !== true) {
    issues.push("证据强度或历史样本限制未完整披露。");
  }
  if (!Array.isArray(provenance?.critical_source_gaps) || provenance.critical_source_gaps.length > 0) {
    issues.push("关键来源缺口检查缺失或存在未解决缺口。");
  }
  if (!market || typeof market.source_status !== "string" || market.provider_origin_authenticated !== false
    || !dividends || typeof dividends.source_status !== "string" || typeof dividends.evidence_gap !== "string"
    || dividends.evidence_gap.trim() === "" || limitations.length === 0) {
    issues.push("数据来源和限制说明不完整。");
  }
  const rawPathIds = result?.path_ids;
  const expectedPathIds = EXPECTED_PATHS.map((path) => path.id);
  if (!Array.isArray(rawPathIds) || rawPathIds.length !== expectedPathIds.length
    || expectedPathIds.some((pathId, index) => rawPathIds[index] !== pathId)) {
    issues.push("三账户、两种成本的六条固定路径不完整。");
  }

  const rows: Card020OutcomeRow[] = [];
  const trustedPaths = new Map<string, { metric: Record<string, unknown>; decision: Record<string, unknown> }>();
  for (const expected of EXPECTED_PATHS) {
    const path = asRecord(paths?.[expected.id]);
    const metrics = asRecord(path?.metrics);
    const full = asRecord(metrics?.full);
    const decision = asRecord(full?.decision_values);
    if (!path || path.path_id !== expected.id || path.account_type !== expected.account || path.cost_scenario !== expected.cost
      || !full || !decision || asRecord(reconciliation?.[expected.id])?.status !== "passed") {
      issues.push(expected.id + " 路径或独立核账记录不完整。");
      rows.push(unknownRow(expected.id, accountLabel(expected.account), costLabel(expected.cost)));
      continue;
    }
    const requiredValues = [
      full.start_nav_actual_cny, full.end_nav_actual_cny, full.net_gain_actual_cny, full.return_ratio,
      decision.max_drawdown_amount_evaluation_cny, decision.max_drawdown_ratio,
      path.commission_total_cny, path.slippage_cost_total_cny,
    ];
    if (requiredValues.some((value) => numericText(value) === null)) {
      issues.push(expected.id + " 缺少终值、盈亏、回撤或成本数值。");
      rows.push(unknownRow(expected.id, accountLabel(expected.account), costLabel(expected.cost)));
      continue;
    }
    const pnlSign = compareDecimals(full.net_gain_actual_cny, "0");
    if (pnlSign === null) {
      issues.push(expected.id + " 净盈亏不可核。");
      rows.push(unknownRow(expected.id, accountLabel(expected.account), costLabel(expected.cost)));
      continue;
    }
    const pnlState: PnlState = pnlSign > 0 ? "profit" : pnlSign < 0 ? "loss" : "flat";
    const pnlDescription = pnlState === "profit" ? "模拟盈利" : pnlState === "loss" ? "模拟亏损" : "模拟盈亏持平";
    const pnlAmount = formatCard020SummaryMoney(full.net_gain_actual_cny, true);
    const returnValue = formatPercent(full.return_ratio, true);
    rows.push({
      pathId: expected.id,
      accountLabel: accountLabel(expected.account),
      costLabel: costLabel(expected.cost),
      startingNavText: formatCard020SummaryMoney(full.start_nav_actual_cny),
      endingNavText: formatCard020SummaryMoney(full.end_nav_actual_cny),
      pnlText: pnlDescription + " " + pnlAmount + "（" + returnValue + "）",
      pnlState,
      returnText: returnValue,
      drawdownAmountText: formatCard020SummaryMoney(decision.max_drawdown_amount_evaluation_cny),
      drawdownRatioText: formatPercent(decision.max_drawdown_ratio),
      commissionText: formatCard020SummaryMoney(path.commission_total_cny),
      slippageText: formatCard020SummaryMoney(path.slippage_cost_total_cny),
    });
    trustedPaths.set(expected.id, { metric: full, decision });
  }

  const startingCapital = numericText(result?.starting_capital_cny);
  const periodStart = typeof result?.period_start_date === "string" ? result.period_start_date : "";
  const periodEnd = typeof result?.period_end_date === "string" ? result.period_end_date : "";
  if (startingCapital === null || !periodStart || !periodEnd) issues.push("初始本金或研究区间缺失。");
  const reconPathsComplete = EXPECTED_PATHS.every((path) => asRecord(reconciliation?.[path.id])?.status === "passed");
  if (!reconPathsComplete) issues.push("至少一条路径没有通过独立核账。");

  const metricsTrusted = issues.length === 0 && categoryCode !== "D";
  if (!metricsTrusted) {
    for (let index = 0; index < rows.length; index += 1) {
      rows[index] = unknownRow(rows[index].pathId, rows[index].accountLabel, rows[index].costLabel);
    }
  }

  const staticHalfTradeoffs: Card020StaticHalfTradeoff[] = [];
  if (metricsTrusted) {
    for (const cost of ["base", "stress"] as const) {
      const candidate = trustedPaths.get("candidate-" + cost);
      const staticHalf = trustedPaths.get("static_half-" + cost);
      if (!candidate || !staticHalf) continue;
      const candidateEndingNavHigher = compareDecimals(candidate.metric.end_nav_actual_cny, staticHalf.metric.end_nav_actual_cny) === 1;
      const staticHalfDrawdownLower = compareDecimals(
        staticHalf.decision.max_drawdown_amount_evaluation_cny,
        candidate.decision.max_drawdown_amount_evaluation_cny,
      ) === -1;
      staticHalfTradeoffs.push({
        costLabel: cost === "base" ? "基础成本" : "压力成本",
        candidateEndingNavHigher,
        staticHalfDrawdownLower,
        description: candidateEndingNavHigher && staticHalfDrawdownLower
          ? "静态半仓在" + (cost === "base" ? "基础" : "压力") + "成本下期末净值较低、最大回撤也较小；这是收益与风险的取舍，不代表哪种适合实际使用。"
          : "静态半仓在" + (cost === "base" ? "基础" : "压力") + "成本下的期末净值和最大回撤呈现不同取舍，请看完整数据。",
      });
    }
  }

  const ready = issues.length === 0;
  const eligibilityText = result?.formal_trade_qualification === false && result?.acceptance_status === "not_qualified"
    ? "未获正式策略资格；本研究不能生成正式交易计划或交易信号。"
    : "正式资格状态未知；不要据此使用策略，也不要生成交易计划或信号。";
  const evidenceText = result?.evidence_level === "low"
    ? "证据强度低；来源认证与历史资料限制会影响结果可信度。"
    : "证据强度未知；不能把历史结果当作可用依据。";
  const historyText = result?.historical_reuse === true && result?.not_out_of_sample === true
    ? "本区间已经用于历史研究，不是独立样本外结果；不能据此证明未来表现。"
    : "本区间是否重复使用、是否属于独立样本外未知；不能把它当作独立样本外证据。";
  return {
    ready,
    metricsTrusted,
    issues: Array.from(new Set(issues)),
    periodText: periodStart && periodEnd ? "固定历史模拟：" + periodStart + " 至 " + periodEnd + "。" : "历史模拟区间未知。",
    pathScopeText: ready ? "三账户 × 两种成本，共六条固定路径。" : "账户或成本路径覆盖不完整，范围未知。",
    historyText,
    startingCapitalText: startingCapital === null ? "未知" : formatCard020SummaryMoney(startingCapital),
    categoryLabel: ready && category ? category.label : "结果暂不可判定",
    categoryMessage: ready && category ? category.message : "批次数据、披露或独立核账不完整；盈亏和评价暂按未知处理。",
    eligibilityText,
    evidenceText,
    sourceSummary,
    criticalSourceGaps: criticalSourceGaps.length ? criticalSourceGaps : (Array.isArray(provenance?.critical_source_gaps) ? [] : ["关键来源缺口记录未提供。"]),
    limitations: limitations.length ? limitations : ["数据限制未提供，不能完整解读结果。"],
    rows,
    staticHalfTradeoffs,
  };
}
