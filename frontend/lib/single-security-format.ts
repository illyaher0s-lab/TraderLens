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
  if (!/^\d{6}$/.test(code) || typeof symbol !== "string") return false;
  const match = /^(\d{6})\.(SH|SZ|BJ)$/.exec(symbol);
  return Boolean(match && match[1] === code);
}

type PercentileMetric = {
  value?: DisplayValue;
  as_of?: string | null;
  window?: string | null;
  source?: string | null;
} | null | undefined;

export type EtfResearchForDisplay = {
  valuation_conclusion?: {
    status?: string | null;
    basis?: string | null;
    message?: string | null;
  } | null;
  metrics?: {
    underlying_index?: { value?: string | null } | null;
    underlying_pe_percentile_10y?: PercentileMetric;
    underlying_pb_percentile_10y?: PercentileMetric;
  } | null;
} | null | undefined;

export type EtfValuationKeyMetric = {
  kind: "index_pe_pb" | "gap";
  label: string;
  value: string;
  detail: string;
  basis: string[];
};

// First key-metric group for ETFs whose deterministic conclusion is not the 510880 own-yield substitute.
export function etfValuationKeyMetric(etf: EtfResearchForDisplay): EtfValuationKeyMetric | null {
  const conclusion = etf?.valuation_conclusion;
  if (!conclusion) return null;
  if (conclusion.status === "data_gap" || conclusion.status === "not_supported") {
    return {
      kind: "gap",
      label: "估值判断",
      value: unavailableOrText(conclusion.message ?? undefined),
      detail: "确定性估值规则；未使用替代数据",
      basis: [],
    };
  }
  if (conclusion.basis !== "index_pe_pb") return null;
  const pe = etf?.metrics?.underlying_pe_percentile_10y;
  const pb = etf?.metrics?.underlying_pb_percentile_10y;
  const indexCode = unavailableOrText(etf?.metrics?.underlying_index?.value ?? undefined);
  const asOf = unavailableOrText(pe?.as_of ?? pb?.as_of ?? undefined);
  const source = unavailableOrText(pe?.source ?? pb?.source ?? undefined);
  return {
    kind: "index_pe_pb",
    label: "跟踪指数PE / PB十年分位",
    value: `PE ${formatHistoricalPercentile(pe?.value)} · PB ${formatHistoricalPercentile(pb?.value)}`,
    detail: `${source} · index_dailybasic · 指数 ${indexCode} · 数据日期 ${asOf}`,
    basis: [
      pe?.window ? `PE：${pe.window}` : "PE十年覆盖口径未获取。",
      pb?.window ? `PB：${pb.window}` : "PB十年覆盖口径未获取。",
    ],
  };
}
