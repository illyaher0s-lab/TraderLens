type DisplayValue = number | string | null | undefined;

function finiteNumber(value: DisplayValue): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string" || !value.trim()) return null;
  if (/^(?:unknown|null|undefined|nan|none)$/i.test(value.trim())) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function fixed(value: number, digits: number): string {
  return new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function unavailableOrText(value: DisplayValue): string {
  if (typeof value === "string" && value.trim() && !/^(?:unknown|null|undefined|nan|none)$/i.test(value.trim())) {
    return value.trim();
  }
  return "未获取";
}

export function formatDividendYield(value: DisplayValue): string {
  const number = finiteNumber(value);
  return number === null || number < 0 ? "未获取" : `${fixed(number, 2)}%`;
}

export function formatHistoricalPercentile(value: DisplayValue): string {
  const number = finiteNumber(value);
  return number === null || number < 0 || number > 100 ? "未获取" : `${fixed(number, 2)}%`;
}

export function formatDrawdown(value: DisplayValue): string {
  const number = finiteNumber(value);
  return number === null ? "未获取" : `${fixed(Math.max(0, -number), 2)}%`;
}

export function formatMeanAmount(value: DisplayValue): string {
  const number = finiteNumber(value);
  return number === null || number < 0 ? "未获取" : `${fixed(number / 100_000_000, 2)}亿元`;
}

export function formatAssetNetValue(value: DisplayValue): string {
  const number = finiteNumber(value);
  return number === null || number < 0 ? "未获取" : `${fixed(number / 100_000_000, 2)}亿元`;
}

export function formatFundShares(value: DisplayValue): string {
  const number = finiteNumber(value);
  return number === null || number < 0 ? "未获取" : `${fixed(number / 10_000, 2)}亿份`;
}

export function formatAnnualFeeSummary(
  managementFee: DisplayValue,
  custodyFee: DisplayValue,
): string | null {
  const management = finiteNumber(managementFee);
  const custody = finiteNumber(custodyFee);
  if (management === null || custody === null || management < 0 || custody < 0) return null;
  return `管理费${fixed(management, 2)}% + 托管费${fixed(custody, 2)}% = 合计${fixed(management + custody, 2)}%/年`;
}

export function formatFactValue(label: string, value: DisplayValue, unit = ""): string {
  if (label === "近12个月现金分红收益率") return formatDividendYield(value);
  if (label === "ETF自身现金分红收益率历史分位") return formatHistoricalPercentile(value);
  if (label.includes("回撤")) return formatDrawdown(value);
  if (label === "近20个SSE交易日平均成交额") return formatMeanAmount(value);
  if (label === "资产净值") return formatAssetNetValue(value);
  if (label === "基金份额规模") return formatFundShares(value);

  const number = finiteNumber(value);
  if (number === null) return unavailableOrText(value);
  if (label === "管理费率" || label === "托管费率") return `${fixed(number, 2)}%/年`;
  if (label === "近一年报告收盘价变化") return `${fixed(number, 2)}%`;
  const formatted = fixed(number, 2);
  return unit ? `${formatted} ${unit}` : formatted;
}

export function isSingleSecurityResultForCode(code: string, symbol: unknown): boolean {
  if (typeof symbol !== "string") return false;
  if (code === "510880.SH") return symbol === "510880.SH";
  if (!/^\d{6}$/.test(code)) return false;
  const match = /^(\d{6})\.(SH|SZ|BJ)$/.exec(symbol);
  return Boolean(match && match[1] === code);
}

type PercentileMetric = {
  value?: DisplayValue;
  as_of?: string | null;
  window?: string | null;
  source?: string | null;
  endpoint?: string | null;
  field?: string | null;
  unit?: string | null;
  label?: string | null;
  stale?: boolean | null;
  coverage_complete?: boolean | null;
} | null | undefined;

type ResearchSourceForDisplay = {
  source_record_id?: string;
  endpoint?: string;
  title?: string;
  as_of?: string | null;
  summary?: string;
  gaps?: string[];
};

export type EtfResearchForDisplay = {
  is_etf?: boolean | null;
  category?: string | null;
  fund_type?: string | null;
  benchmark?: string | null;
  symbol?: string | null;
  gaps?: string[];
  endpoint_statuses?: Record<string, string>;
  sources?: ResearchSourceForDisplay[];
  valuation_conclusion?: {
    status?: string | null;
    basis?: string | null;
    verdict?: string | null;
    label?: string | null;
    message?: string | null;
  } | null;
  metrics?: {
    underlying_index?: { value?: string | null } | null;
    underlying_pe_percentile_10y?: PercentileMetric;
    underlying_pb_percentile_10y?: PercentileMetric;
    latest_price?: PercentileMetric;
    price_change_1y?: PercentileMetric;
    distance_from_1y_high_pct?: PercentileMetric;
    average_amount_20d?: PercentileMetric;
    trailing_cash_dividend_per_share?: PercentileMetric;
    trailing_dividend_yield?: PercentileMetric;
    trailing_dividend_yield_percentile_10y?: PercentileMetric;
    trailing_dividend_yield_valuation?: PercentileMetric;
    asset_scale?: PercentileMetric;
    fund_size_shares?: PercentileMetric;
    management_fee?: PercentileMetric;
    custody_fee?: PercentileMetric;
    price_coverage_1y?: { coverage_complete?: boolean | null } | null;
    [key: string]: unknown;
  } | null;
} | null | undefined;

export type EtfValuationKeyMetric = {
  id: string;
  label: string;
  value: string;
  detail: string;
  basis: string[];
};

function validPercentileMetric(metric: PercentileMetric): number | null {
  const value = finiteNumber(metric?.value);
  const hasProvenance = Boolean(
    metric?.source?.trim() &&
    metric.endpoint?.trim() &&
    metric.field?.trim() &&
    metric.unit?.trim() &&
    metric.as_of &&
    /^\d{4}-\d{2}-\d{2}$/.test(metric.as_of) &&
    metric.window?.trim()
  );
  return hasProvenance && value !== null && value >= 0 && value <= 100 ? value : null;
}

function metricSourceDetail(metric: PercentileMetric, indexCode?: string): string {
  if (!metric) return "来源日期未获取";
  const endpoint = metric.endpoint
    ? `${metric.endpoint}${metric.field ? `.${metric.field}` : ""}`
    : null;
  const date = metric.as_of ? `数据日期 ${metric.as_of}` : "来源日期未获取";
  return [metric.source, endpoint, indexCode ? `指数 ${indexCode}` : null, date]
    .filter((part): part is string => Boolean(part))
    .join(" · ");
}

function etfMetric(
  id: string,
  label: string,
  value: string,
  metric: PercentileMetric,
  indexCode?: string,
): EtfValuationKeyMetric {
  return {
    id,
    label,
    value,
    detail: metricSourceDetail(metric, indexCode),
    basis: [metric?.window ?? "统计口径未获取。"],
  };
}

// Only display numeric values that directly support the existing deterministic conclusion.
export function etfValuationKeyMetrics(etf: EtfResearchForDisplay): EtfValuationKeyMetric[] {
  const conclusion = etf?.valuation_conclusion;
  if (conclusion?.status !== "conclusive") return [];

  const metrics = etf?.metrics;
  if (conclusion.basis === "index_pe_pb") {
    const pe = metrics?.underlying_pe_percentile_10y;
    const pb = metrics?.underlying_pb_percentile_10y;
    if (validPercentileMetric(pe) === null || validPercentileMetric(pb) === null) return [];
    const indexCode = metrics?.underlying_index?.value ?? undefined;
    return [
      etfMetric("etf-index-pe-percentile", "跟踪指数PE十年分位", formatHistoricalPercentile(pe?.value), pe, indexCode),
      etfMetric("etf-index-pb-percentile", "跟踪指数PB十年分位", formatHistoricalPercentile(pb?.value), pb, indexCode),
    ];
  }

  if (conclusion.basis === "own_dividend_yield") {
    const yieldMetric = metrics?.trailing_dividend_yield;
    const percentileMetric = metrics?.trailing_dividend_yield_percentile_10y;
    if (validPercentileMetric(percentileMetric) === null) return [];
    const result: EtfValuationKeyMetric[] = [];
    const yieldValue = finiteNumber(yieldMetric?.value);
    const yieldHasProvenance = Boolean(
      yieldMetric?.source?.trim() &&
      yieldMetric.endpoint?.trim() &&
      yieldMetric.field?.trim() &&
      yieldMetric.unit?.trim() &&
      yieldMetric.as_of &&
      /^\d{4}-\d{2}-\d{2}$/.test(yieldMetric.as_of) &&
      yieldMetric.window?.trim()
    );
    if (yieldHasProvenance && yieldValue !== null && yieldValue >= 0) {
      result.push(etfMetric(
        "etf-own-dividend-yield",
        "ETF自身现金分红收益率",
        formatDividendYield(yieldValue),
        yieldMetric,
      ));
    }
    result.push(etfMetric(
      "etf-own-dividend-yield-percentile",
      "ETF自身现金分红收益率历史分位",
      formatHistoricalPercentile(percentileMetric?.value),
      percentileMetric,
    ));
    return result;
  }

  return [];
}

export type EtfCoverageFact = {
  label?: string | null;
  value?: DisplayValue;
  unit?: string | null;
  symbol?: string | null;
  source?: string | null;
  endpoint?: string | null;
  field?: string | null;
  date?: string | null;
  window?: string | null;
};

export type EtfResearchCoverageInput = {
  identitySource?: {
    source?: string | null;
    endpoint?: string | null;
    symbol?: string | null;
    retrieved_at?: string | null;
  } | null;
  numericFacts?: EtfCoverageFact[];
  sources?: ResearchSourceForDisplay[];
  etf?: EtfResearchForDisplay;
  evidenceGaps?: string[];
  notApplicable?: string[];
};

export type EtfResearchCoverage = {
  covered: string[];
  limited: string[];
  notCovered: string[];
};

function hasText(value: unknown): value is string {
  return typeof value === "string" && Boolean(value.trim()) &&
    !/^(?:unknown|null|undefined|none|未获取|未知|无)$/i.test(value.trim());
}

function hasFactValue(value: DisplayValue): boolean {
  if (finiteNumber(value) !== null) return true;
  return typeof value === "string" && hasText(value);
}

function sourceRecordMatchesFact(
  fact: EtfCoverageFact,
  sources: ResearchSourceForDisplay[],
): boolean {
  if (!fact.endpoint || !fact.date) return false;
  const factDate = fact.date;
  const factEndpoints = fact.endpoint.split("+").map((item) => item.trim()).filter(Boolean);
  return sources.some((source) => {
    if (!source.endpoint) return false;
    const sourceEndpoints = source.endpoint.split("+").map((item) => item.trim()).filter(Boolean);
    const sourceDateMatches = source.as_of === factDate;
    const indexField = fact.field?.toUpperCase();
    const indexSummaryMatchesFactDate = Boolean(
      (indexField === "PE" || indexField === "PB") &&
      source.summary &&
      new RegExp(`(?:^|\\s)${indexField} complete sample=[^.]*\\bto ${factDate}\\.`).test(source.summary)
    );
    const indexCoverageEndsAtFactDate = Boolean(
      factEndpoints.includes("index_dailybasic") &&
      sourceEndpoints.includes("index_dailybasic") &&
      source.as_of && /^\d{4}-\d{2}-\d{2}$/.test(source.as_of) &&
      /^\d{4}-\d{2}-\d{2}$/.test(factDate) &&
      source.as_of > factDate &&
      indexSummaryMatchesFactDate
    );
    return (
      sourceEndpoints.some((endpoint) => factEndpoints.includes(endpoint)) &&
      (sourceDateMatches || indexCoverageEndsAtFactDate)
    );
  });
}

function metricSupportsFact(fact: EtfCoverageFact, metric: PercentileMetric): boolean {
  if (metric === null || metric === undefined) return true;
  return Boolean(
    hasFactValue(metric.value) &&
    hasText(metric.unit) && metric.unit === fact.unit &&
    hasText(metric.source) && metric.source === fact.source &&
    hasText(metric.endpoint) && metric.endpoint === fact.endpoint &&
    hasText(metric.field) && metric.field === fact.field &&
    metric.as_of && metric.as_of === fact.date &&
    hasText(metric.window)
  );
}

function metricForFact(fact: EtfCoverageFact, etf: EtfResearchForDisplay): PercentileMetric {
  const label = fact.label ?? "";
  const metricName = label === "最近收盘价" ? "latest_price"
    : label === "近一年报告收盘价变化" ? "price_change_1y"
    : label.startsWith("距") && label.includes("回撤") ? "distance_from_1y_high_pct"
    : label === "近20个SSE交易日平均成交额" ? "average_amount_20d"
    : label === "近12个月已实施现金分红" ? "trailing_cash_dividend_per_share"
    : label === "近12个月现金分红收益率" ? "trailing_dividend_yield"
    : label === "ETF自身现金分红收益率历史分位" ? "trailing_dividend_yield_percentile_10y"
    : label === "资产净值" ? "asset_scale"
    : label === "基金份额规模" ? "fund_size_shares"
    : label === "管理费率" ? "management_fee"
    : label === "托管费率" ? "custody_fee"
    : label === "跟踪指数PE" ? "underlying_pe"
    : label === "跟踪指数PB" ? "underlying_pb"
    : null;
  if (!metricName) return null;
  const value = etf?.metrics?.[metricName];
  return value && typeof value === "object" ? value as PercentileMetric : null;
}

function identityHasSource(
  etf: EtfResearchForDisplay,
  identitySource: EtfResearchCoverageInput["identitySource"],
): boolean {
  const identity = identitySource;
  if (
    !identity || !hasText(identity.source) || !hasText(identity.endpoint) ||
    !hasText(identity.symbol) || !hasText(identity.retrieved_at) ||
    (etf?.symbol && identity.symbol !== etf.symbol)
  ) return false;
  return true;
}

export function hasVerifiableEtfValuation(
  etf: EtfResearchForDisplay,
  identitySource?: EtfResearchCoverageInput["identitySource"],
  sourcesOverride?: ResearchSourceForDisplay[],
): boolean {
  if (etf?.is_etf !== true) return false;
  const sources = sourcesOverride ?? etf.sources ?? [];
  if (!identityHasSource(etf, identitySource)) return false;

  const conclusion = etf.valuation_conclusion;
  if (!conclusion?.status || !hasText(conclusion.message)) return false;
  if (conclusion.status === "conclusive") {
    if (etfValuationKeyMetrics(etf).length === 0) return false;
    const metrics = etf.metrics;
    const valuationMetrics = conclusion.basis === "index_pe_pb"
      ? [metrics?.underlying_pe_percentile_10y, metrics?.underlying_pb_percentile_10y]
      : conclusion.basis === "own_dividend_yield"
        ? [metrics?.trailing_dividend_yield_percentile_10y]
        : [];
    return valuationMetrics.length > 0 && valuationMetrics.every((metric) => (
      Boolean(metric && sourceRecordMatchesFact({ endpoint: metric.endpoint, field: metric.field, date: metric.as_of }, sources))
    ));
  }
  if (conclusion.status === "data_gap") {
    const hasObservedGap = (etf.gaps ?? []).some((gap) => (
      hasText(gap) && /估值|PE|PB|分位|收益率|index_dailybasic/i.test(gap)
    ));
    const hasGapStatus = ["index_dailybasic", "fund_div", "fund_daily"].some((endpoint) => (
      ["empty_no_rows", "not_applicable"].includes(etf.endpoint_statuses?.[endpoint] ?? "")
    ));
    return hasObservedGap || hasGapStatus;
  }
  if (conclusion.status === "not_supported") {
    if (etf.category !== "other") return false;
    const hasClassificationSource = sources.some((source) => (
      source.as_of && /^\d{4}-\d{2}-\d{2}$/.test(source.as_of) &&
      ["fund_basic", "etf_basic"].some((endpoint) => source.endpoint?.split("+").includes(endpoint))
    ));
    const hasUnsupportedStatus = etf.endpoint_statuses?.index_dailybasic === "not_applicable";
    return Boolean(etf.category && hasClassificationSource && hasUnsupportedStatus);
  }
  return false;
}

function factIsLimited(
  fact: EtfCoverageFact,
  metric: PercentileMetric,
  etf: EtfResearchForDisplay,
  gaps: string[],
): boolean {
  if (metric?.stale === true || metric?.coverage_complete === false) return true;
  const label = fact.label ?? "";
  if (
    (label === "近一年报告收盘价变化" || (label.startsWith("距") && label.includes("回撤"))) &&
    etf?.metrics?.price_coverage_1y?.coverage_complete !== true
  ) return true;
  if (metric?.label?.includes("实际观察区间") || fact.window?.includes("实际观察区间")) return true;
  return gaps.some((gap) => (
    (label === "最近收盘价" && gap.includes("行情已过期")) ||
    (label === "近20个SSE交易日平均成交额" && gap.includes("最近20个交易日")) ||
    ((label === "近一年报告收盘价变化" || (label.startsWith("距") && label.includes("回撤"))) &&
      (gap.includes("一年区间") || gap.includes("一年窗口") || gap.includes("历史样本")))
  ));
}

export function getEtfResearchCoverage(input: EtfResearchCoverageInput): EtfResearchCoverage {
  const etf = input.etf;
  const sources = input.sources ?? etf?.sources ?? [];
  const gaps = input.evidenceGaps ?? [];
  const covered: string[] = [];
  const limited: string[] = [];
  const notCovered: string[] = [];
  const addUnique = (list: string[], value: string) => {
    if (!list.includes(value)) list.push(value);
  };

  const identity = input.identitySource;
  const identityLabel = etf?.is_etf === true ? "ETF身份" : "基金身份";
  const identitySourceFound = identityHasSource(etf, identity);
  if (identitySourceFound) addUnique(covered, identityLabel);
  else addUnique(notCovered, `${identityLabel}来源未核实`);

  const valuationIsVerifiable = hasVerifiableEtfValuation(etf, input.identitySource, sources);
  const valuationConclusion = etf?.valuation_conclusion;
  if (valuationIsVerifiable && valuationConclusion?.status === "conclusive") {
    addUnique(covered, "估值参考");
  } else if (valuationIsVerifiable && valuationConclusion?.status === "data_gap") {
    addUnique(notCovered, `估值资料缺口：${valuationConclusion.message}`);
  } else if (valuationIsVerifiable && valuationConclusion?.status === "not_supported") {
    addUnique(notCovered, `估值方法限制：${valuationConclusion.message}`);
  } else {
    addUnique(notCovered, etf?.is_etf === true
      ? etfNoValuationMessage(true, etf)
      : "本次未提供可核验的ETF估值参考。");
  }

  for (const fact of input.numericFacts ?? []) {
    const label = fact.label?.trim();
    if (!label || label === "估值参考") continue;
    const unitVerified = hasText(fact.unit);
    const provenanceVerified = Boolean(
      hasFactValue(fact.value) &&
      unitVerified &&
      hasText(fact.source) &&
      hasText(fact.endpoint) &&
      hasText(fact.field) &&
      fact.date && /^\d{4}-\d{2}-\d{2}$/.test(fact.date) &&
      hasText(fact.symbol) &&
      (!etf?.symbol || fact.symbol === etf.symbol) &&
      sourceRecordMatchesFact(fact, sources)
    );
    const metric = metricForFact(fact, etf);
    const metricMismatch = !metricSupportsFact(fact, metric);
    const endpointStatuses = etf?.endpoint_statuses ?? {};
    const endpointUnavailable = (fact.endpoint ?? "").split("+").some((endpoint) => (
      ["not_applicable", "empty_no_rows"].includes(endpointStatuses[endpoint])
    ));
    if (!provenanceVerified || metricMismatch || endpointUnavailable) {
      addUnique(notCovered, `${label}（来源、日期、字段或单位未完整核实）`);
      continue;
    }
    if (factIsLimited(fact, metric, etf, gaps)) addUnique(limited, label);
    else addUnique(covered, label);
  }

  for (const gap of gaps) if (hasText(gap)) addUnique(notCovered, gap);
  for (const item of input.notApplicable ?? []) {
    if (hasText(item)) addUnique(notCovered, `不适用：${item}`);
  }
  if (covered.length === 0 && limited.length === 0) {
    addUnique(notCovered, "本次没有带完整来源信息的可列示事实。");
  }
  return { covered, limited, notCovered };
}

export function neutralizeUnsupportedFundEvaluations(text: string): string {
  return text
    .replace(/(?:比较|较为|相对|非常)?合理(?:的)?((?:管理|托管)?费率|费用|管理费|托管费)/g, "$1是否适当未评估")
    .replace(/(?:比较|较为|相对|非常)?(?:充足|充分|足够|良好|较好)(?:的)?流动性/g, "流动性是否充足未评估")
    .replace(/(?:比较|较为|相对|非常)?(?:充足|充分|足够|良好|较好)(?:的)?成交额/g, "成交额是否充足未评估")
    .replace(/((?:管理|托管)?费率)(?:明显|比较|较为|相对|非常)?合理/g, "$1是否适当未评估")
    .replace(/费用(?:明显|比较|较为|相对|非常)?合理/g, "费用适当性未评估")
    .replace(/(流动性)(?:明显|比较|较为|相对|非常)?(?:充足|充分|足够|良好|较好)/g, "$1是否充足未评估")
    .replace(/(成交额)(?:明显|比较|较为|相对|非常)?(?:充足|充分|足够|良好|较好)/g, "$1是否充足未评估");
}

export function etfNoValuationMessage(
  isVerifiedEtf: boolean,
  etf: EtfResearchForDisplay,
): string {
  if (!isVerifiedEtf) return "ETF身份或类别未核实，因此不展示估值数值；核验资料见展开详情。";

  const status = etf?.valuation_conclusion?.status;
  if (!status) return "估值状态或来源未核实，因此不展示估值结论；原始响应见展开详情。";
  if (status === "conclusive") {
    return "估值指标或来源链（来源、日期、字段、单位）未完整核实，因此不展示估值数值；原始响应见展开详情。";
  }
  if (status === "data_gap") {
    return "估值资料存在缺口，因此不展示估值数值；缺项及影响见下方。";
  }
  if (status === "not_supported") {
    if (etf?.category === "other") {
      return "现有估值规则不覆盖已核验的基金类别，因此不展示估值数值。";
    }
    if (etf?.category === "unclassified" || !etf?.category) {
      return "基金类别尚未核实，因此本次暂不判断估值。";
    }
    return "估值类别尚未确认适用现有规则，因此本次暂不判断估值。";
  }
  return "现有规则所需数值未完整核实，因此不展示估值数值。";
}

const ETF_INDEX_DIVIDEND_FIELD_GAP =
  "Tushare index_dailybasic没有股息率字段；底层指数股息率不可由本接口核验。";
const ETF_OWN_YIELD_REPLACEMENT_PREFIX =
  "跟踪指数PE/PB与指数股息率无可用覆盖；已以510880 ETF自身现金分红收益率历史分位（滚动365天）作替代参考（";
const ETF_UNCLASSIFIED_GAP =
  "fund_basic类型或完整业绩比较基准未匹配固定ETF分类，不按名称猜测分类。";

export function explainEtfEvidenceGap(gap: string, etf: EtfResearchForDisplay): string {
  const status = etf?.valuation_conclusion?.status;
  const basis = etf?.valuation_conclusion?.basis;
  const category = etf?.category;

  if (
    status === "not_supported" &&
    (gap === "index_dailybasic: not_applicable" || gap === ETF_UNCLASSIFIED_GAP)
  ) {
    return etfNoValuationMessage(true, etf);
  }

  if (gap === ETF_INDEX_DIVIDEND_FIELD_GAP) {
    if (status === "conclusive" && basis === "own_dividend_yield") {
      return "当前接口没有底层指数股息率字段；本次估值仍依据510880自身现金分红收益率历史分位参考，不代表指数估值或未来分红。";
    }
    if (status === "conclusive" && basis === "index_pe_pb") {
      return "当前接口没有底层指数股息率字段；这只说明该字段无法由本接口核验，不改变基于PE/PB的现有估值结论。";
    }
    return "当前接口没有底层指数股息率字段；这项资料无法由本接口核验。";
  }

  if (
    status === "conclusive" && basis === "own_dividend_yield" && category === "dividend" &&
    gap.startsWith(ETF_OWN_YIELD_REPLACEMENT_PREFIX)
  ) {
    return "跟踪指数PE/PB与指数股息率没有可用覆盖；本次估值按现有规则采用510880自身现金分红收益率历史分位作为替代参考。仅与本ETF自身历史比较，不等同于指数估值，也不代表未来分红或回报。";
  }

  if (
    status === "data_gap" &&
    /^跟踪指数 \S+ 的PE\/PB当前值及十年估值分位数均未能核验：index_dailybasic 返回空结果。$/.test(gap)
  ) {
    return "跟踪指数PE/PB当前值及十年估值分位数均未能核验，因此本次不提供该口径的估值判断。";
  }

  if (
    /^最近有效收盘价日期 \d{4}-\d{2}-\d{2} 早于预期公布日 \d{4}-\d{2}-\d{2}，行情已过期。$/.test(gap)
  ) {
    return "最近有效收盘价已有过期标记，不能当作当前行情。";
  }

  if (
    gap.startsWith("fund_daily 一年区间有效上市日收盘价缺少 ") &&
    gap.endsWith("观察到的区间指标仍按有效行情计算，未将样本称为完整一年。")
  ) {
    return "一年区间收盘价样本覆盖不完整；观察到的区间指标仍按有效行情计算，不能称作完整一年。";
  }

  if (gap.startsWith("fund_daily 未覆盖SSE日历最近20个交易日的全部有效成交额；缺少日期：")) {
    return "SSE日历最近20个交易日的有效成交额未完整，不能计算完整20日平均成交额；这项缺口不表示最近有效收盘价无效。";
  }

  if (gap === "fund_daily 缺少最近预期SSE交易日的有效收盘价，当前价格不可核验。") {
    return "基金最近预期SSE交易日的有效收盘价未核实，当前价格不可核验。";
  }

  if (gap === "基金当前成分明细与行业权重未获取。") {
    return "基金持仓明细或行业权重未核实，影响：无法判断基金实际配置。";
  }

  return gap;
}

export type InvestmentAssumptionSummaryInput = {
  kind?: string | null;
} | null | undefined;

export function formatInvestmentAssumptionSummary(
  assumption: InvestmentAssumptionSummaryInput,
  originalText: string,
): string {
  if (assumption?.kind === "trailing_cash_dividend_baseline") {
    return "观察已派付现金分红是否变化；仅作研究观察假设。";
  }
  if (assumption?.kind === "average_amount_20d_baseline") {
    return "观察同口径平均成交额是否变化；仅作研究观察假设。";
  }
  if (assumption) return "观察条件请查看展开详情；仅作研究观察假设。";
  return originalText;
}
