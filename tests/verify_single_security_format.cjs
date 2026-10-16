const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

const formatterPath = path.join(__dirname, "..", "frontend", "lib", "single-security-format.ts");
const source = fs.readFileSync(formatterPath, "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const formatterModule = { exports: {} };
vm.runInNewContext(compiled, { exports: formatterModule.exports, module: formatterModule });

const {
  etfNoValuationMessage,
  etfValuationKeyMetrics,
  formatAnnualFeeSummary,
  formatAssetNetValue,
  formatDividendYield,
  formatDrawdown,
  formatFundShares,
  formatHistoricalPercentile,
  formatMeanAmount,
  formatInvestmentAssumptionSummary,
  getEtfResearchCoverage,
  hasVerifiableEtfValuation,
  isSingleSecurityResultForCode,
  neutralizeUnsupportedFundEvaluations,
} = formatterModule.exports;

assert.equal(formatDividendYield(4.1861826698), "4.19%");
assert.equal(formatHistoricalPercentile(48.825710754), "48.83%");
assert.equal(formatDrawdown(-3.366336633), "3.37%");
assert.equal(formatDrawdown(0), "0.00%");
assert.equal(formatDrawdown(null), "未获取");
assert.equal(formatDrawdown(Number.NaN), "未获取");
assert.equal(formatDrawdown(Number.POSITIVE_INFINITY), "未获取");
assert.equal(formatMeanAmount(447074604.09999996), "4.47亿元");
assert.equal(formatAssetNetValue(25177624140.25), "251.78亿元");
assert.equal(formatFundShares(560067.57), "56.01亿份");
assert.equal(formatAnnualFeeSummary(0.5, 0.1), "管理费0.50% + 托管费0.10% = 合计0.60%/年");
assert.equal(formatAnnualFeeSummary(0.5, null), null);
assert.equal(formatterModule.exports.formatFactValue("最近收盘价", 3.431, "元/份"), "3.43 元/份");
assert.equal(formatterModule.exports.formatFactValue("近12个月已实施现金分红", 0.143, "元/份"), "0.14 元/份");
assert.equal(isSingleSecurityResultForCode("518880", "518880.SH"), true);
assert.equal(isSingleSecurityResultForCode("18880", "518880.SH"), false);
assert.equal(isSingleSecurityResultForCode("510300", "518880.SH"), false);
assert.equal(isSingleSecurityResultForCode("510880.SH", "510880.SH"), true);
assert.equal(isSingleSecurityResultForCode("510880.SH", "510880.SZ"), false);

const { explainEtfEvidenceGap } = formatterModule.exports;
const broadMetric = etfValuationKeyMetrics({
  valuation_conclusion: { status: "conclusive", basis: "index_pe_pb", message: "跟踪指数PE与PB十年分位均处于中间档（20%–80%），中性。" },
  metrics: {
    underlying_index: { value: "000300.SH" },
    underlying_pe_percentile_10y: { value: 41.25, unit: "%", endpoint: "index_dailybasic", field: "pe", as_of: "2026-10-09", source: "synthetic test fixture", window: "synthetic fixture" },
    underlying_pb_percentile_10y: { value: 62.5, unit: "%", endpoint: "index_dailybasic", field: "pb", as_of: "2026-10-09", source: "synthetic test fixture", window: "synthetic fixture" },
  },
});
assert.equal(broadMetric.length, 2);
assert.equal(broadMetric[0].label, "跟踪指数PE十年分位");
assert.equal(broadMetric[0].value, "41.25%");
assert.equal(broadMetric[1].label, "跟踪指数PB十年分位");
assert.equal(broadMetric[1].value, "62.50%");

const dividendMetrics = etfValuationKeyMetrics({
  valuation_conclusion: { status: "conclusive", basis: "own_dividend_yield" },
  metrics: {
    trailing_dividend_yield: { value: 3.25, unit: "%", endpoint: "fund_div+fund_daily", field: "rolling_365d_div_cash/reported_close", as_of: "2026-10-09", source: "synthetic test fixture", window: "synthetic fixture" },
    trailing_dividend_yield_percentile_10y: { value: 55, unit: "%分位", endpoint: "fund_div+fund_daily", field: "rolling_365d_div_cash/reported_close", as_of: "2026-10-09", source: "synthetic test fixture", window: "synthetic fixture" },
  },
});
assert.equal(dividendMetrics.length, 2);
assert.equal(dividendMetrics[0].label, "ETF自身现金分红收益率");
assert.equal(dividendMetrics[0].value, "3.25%");
assert.equal(dividendMetrics[1].label, "ETF自身现金分红收益率历史分位");
assert.equal(dividendMetrics[1].value, "55.00%");

const gapMetrics = etfValuationKeyMetrics({
  valuation_conclusion: { status: "data_gap", basis: null, message: "跟踪指数的估值数据未覆盖，暂不提供估值判断" },
  metrics: { underlying_pe_percentile_10y: { value: 25 }, underlying_pb_percentile_10y: { value: 30 } },
});
const unsupportedMetrics = etfValuationKeyMetrics({
  valuation_conclusion: { status: "not_supported", basis: null, message: "该类型暂不提供估值判断" },
  metrics: { underlying_pe_percentile_10y: { value: 25 }, underlying_pb_percentile_10y: { value: 30 } },
});
assert.equal(gapMetrics.length, 0);
assert.equal(unsupportedMetrics.length, 0);
assert.equal(etfValuationKeyMetrics(null).length, 0);
assert.equal(etfValuationKeyMetrics({
  valuation_conclusion: { status: "conclusive", basis: "index_pe_pb" },
  metrics: {
    underlying_pe_percentile_10y: { value: 41.25, unit: "%", endpoint: "index_dailybasic", field: "pe", as_of: "2026-10-09", source: "synthetic test fixture", window: "synthetic fixture" },
    underlying_pb_percentile_10y: { value: 62.5, endpoint: "index_dailybasic", field: "pb", as_of: "2026-10-09", source: "synthetic test fixture", window: "synthetic fixture" },
  },
}).length, 0);

const completeCoverageInput = {
  identitySource: {
    source: "Tushare-compatible", endpoint: "fund_basic", symbol: "510300.SH",
    retrieved_at: "2026-10-09T19:00:00+08:00",
  },
  numericFacts: [
    {
      label: "最近收盘价", value: 3.431, unit: "元/份", symbol: "510300.SH",
      source: "Tushare-compatible", endpoint: "fund_daily", field: "close", date: "2026-10-09",
    },
    {
      label: "管理费率", value: 0.5, unit: "%/年", symbol: "510300.SH",
      source: "Tushare-compatible", endpoint: "fund_basic", field: "management_fee", date: "2026-10-09",
    },
    {
      label: "估值参考", value: "中性", unit: "", symbol: "510300.SH",
      source: "Tushare-compatible", endpoint: "index_dailybasic", field: "valuation_label", date: "2026-10-09",
    },
  ],
  sources: [
    { endpoint: "fund_daily", as_of: "2026-10-09" },
    { endpoint: "fund_basic", as_of: "2026-10-09" },
    { endpoint: "index_dailybasic", as_of: "2026-10-09" },
  ],
  etf: {
    is_etf: true,
    sources: [
      { endpoint: "fund_basic", as_of: "2026-10-09" },
      { endpoint: "fund_daily", as_of: "2026-10-09" },
      { endpoint: "index_dailybasic", as_of: "2026-10-09" },
    ],
    valuation_conclusion: { status: "conclusive", basis: "index_pe_pb", message: "估值规则给出中性结果。" },
    metrics: {
      latest_price: { value: 3.431, unit: "元/份", source: "Tushare-compatible", endpoint: "fund_daily", field: "close", as_of: "2026-10-09", window: "最近报告收盘价", stale: false },
      price_coverage_1y: { coverage_complete: true },
      underlying_pe_percentile_10y: { value: 41.25, unit: "%", endpoint: "index_dailybasic", field: "pe", as_of: "2026-10-09", source: "Tushare-compatible", window: "完整SSE交易日样本" },
      underlying_pb_percentile_10y: { value: 62.5, unit: "%", endpoint: "index_dailybasic", field: "pb", as_of: "2026-10-09", source: "Tushare-compatible", window: "完整SSE交易日样本" },
    },
  },
  evidenceGaps: [],
  notApplicable: [],
};
const completeCoverage = getEtfResearchCoverage(completeCoverageInput);
assert.deepEqual(Array.from(completeCoverage.covered), ["ETF身份", "估值参考", "最近收盘价", "管理费率"]);
assert.equal(completeCoverage.notCovered.some((item) => item.startsWith("估值参考（")), false);
assert.equal(completeCoverage.limited.length, 0);
assert.equal(JSON.stringify(completeCoverage).includes("3.431"), false);
assert.equal(JSON.stringify(completeCoverage).includes("合理"), false);
const identityOnlyCoverage = getEtfResearchCoverage({
  identitySource: {
    source: "Tushare-compatible", endpoint: "fund_basic", symbol: "518880.SH",
    retrieved_at: "2026-10-09T19:00:00+08:00",
  },
  sources: [],
  etf: null,
});
assert.equal(identityOnlyCoverage.covered.includes("基金身份"), true);
assert.equal(typeof hasVerifiableEtfValuation, "function");
assert.equal(hasVerifiableEtfValuation(
  completeCoverageInput.etf,
  completeCoverageInput.identitySource,
  completeCoverageInput.sources,
), true);
assert.equal(hasVerifiableEtfValuation(
  completeCoverageInput.etf,
  completeCoverageInput.identitySource,
), true);
const indexValuationWithRequestDate = {
  ...completeCoverageInput.etf,
  symbol: "510300.SH",
  sources: [
    { endpoint: "fund_basic", as_of: "2026-10-12" },
    {
      endpoint: "index_dailybasic",
      as_of: "2026-10-12",
      summary: "PE complete sample=2428 sessions, from 2016-10-12 to 2026-10-09. PB complete sample=2428 sessions, from 2016-10-12 to 2026-10-09.",
    },
  ],
  metrics: {
    ...completeCoverageInput.etf.metrics,
    underlying_pe_percentile_10y: {
      ...completeCoverageInput.etf.metrics.underlying_pe_percentile_10y,
      as_of: "2026-10-09",
    },
    underlying_pb_percentile_10y: {
      ...completeCoverageInput.etf.metrics.underlying_pb_percentile_10y,
      as_of: "2026-10-09",
    },
  },
};
assert.equal(hasVerifiableEtfValuation(
  indexValuationWithRequestDate,
  completeCoverageInput.identitySource,
), true);
assert.equal(hasVerifiableEtfValuation({
  ...indexValuationWithRequestDate,
  sources: indexValuationWithRequestDate.sources.map((source) => (
    source.endpoint === "index_dailybasic"
      ? { ...source, summary: source.summary.replace("to 2026-10-09", "to 2026-10-08") }
      : source
  )),
}, completeCoverageInput.identitySource), false);
assert.equal(hasVerifiableEtfValuation({
  is_etf: true,
  sources: [{ endpoint: "fund_basic", as_of: "2026-10-09" }],
}, completeCoverageInput.identitySource, completeCoverageInput.sources), false);
assert.equal(hasVerifiableEtfValuation({
  ...completeCoverageInput.etf,
  sources: [],
}, completeCoverageInput.identitySource), false);
assert.equal(hasVerifiableEtfValuation({
  is_etf: true,
  category: "industry",
  valuation_conclusion: { status: "data_gap", message: "估值数据未覆盖" },
  gaps: ["跟踪指数估值数据未覆盖。"],
  endpoint_statuses: { index_dailybasic: "empty_no_rows" },
}, completeCoverageInput.identitySource, [{ endpoint: "fund_basic", as_of: "2026-10-09" }]), true);
const dividendDateSemanticsInput = {
  identitySource: {
    source: "Tushare-compatible", endpoint: "fund_basic", symbol: "510880.SH",
    retrieved_at: "2026-10-12T20:27:50+08:00",
  },
  numericFacts: [
    {
      label: "近12个月已实施现金分红", value: 0.143, unit: "元/份", symbol: "510880.SH",
      source: "Tushare-compatible", endpoint: "fund_div", field: "div_cash", date: "2026-01-26",
    },
    {
      label: "近12个月现金分红收益率", value: 4.15, unit: "%", symbol: "510880.SH",
      source: "Tushare-compatible", endpoint: "fund_div+fund_daily",
      field: "rolling_365d_div_cash/reported_close", date: "2026-10-12",
    },
  ],
  etf: {
    is_etf: true,
    symbol: "510880.SH",
    sources: [
      { endpoint: "fund_basic", as_of: "2026-10-12" },
      { endpoint: "fund_div", as_of: "2026-01-26" },
      { endpoint: "fund_daily", as_of: "2026-10-12" },
    ],
    valuation_conclusion: { status: "conclusive", basis: "own_dividend_yield", message: "ETF自身历史分位参考。" },
    metrics: {
      trailing_cash_dividend_per_share: {
        value: 0.143, unit: "元/份", source: "Tushare-compatible", endpoint: "fund_div",
        field: "div_cash", as_of: "2026-01-26", window: "按派息日计入已实施事件",
      },
      trailing_dividend_yield: {
        value: 4.15, unit: "%", source: "Tushare-compatible", endpoint: "fund_div+fund_daily",
        field: "rolling_365d_div_cash/reported_close", as_of: "2026-10-12", window: "滚动365天派息除以当日收盘价",
      },
      trailing_dividend_yield_percentile_10y: {
        value: 46.6, unit: "%分位", source: "Tushare-compatible", endpoint: "fund_div+fund_daily",
        field: "rolling_365d_div_cash/reported_close", as_of: "2026-10-12", window: "十年历史样本",
      },
    },
  },
};
const dividendDateSemanticsCoverage = getEtfResearchCoverage(dividendDateSemanticsInput);
assert.equal(dividendDateSemanticsCoverage.covered.includes("近12个月已实施现金分红"), true);
assert.equal(dividendDateSemanticsCoverage.covered.includes("近12个月现金分红收益率"), true);
assert.equal(hasVerifiableEtfValuation({
  is_etf: true,
  category: "other",
  valuation_conclusion: { status: "not_supported", message: "该类型暂不提供估值判断" },
  endpoint_statuses: { index_dailybasic: "not_applicable" },
}, completeCoverageInput.identitySource, [{ endpoint: "fund_basic", as_of: "2026-10-09" }]), true);
const unclassifiedUnsupportedValuation = {
  is_etf: true,
  symbol: "510300.SH",
  category: "unclassified",
  sources: [{ endpoint: "fund_basic", as_of: "2026-10-09" }],
  valuation_conclusion: { status: "not_supported", message: "该类型暂不提供估值判断。" },
  endpoint_statuses: { index_dailybasic: "not_applicable" },
};
assert.equal(hasVerifiableEtfValuation(
  unclassifiedUnsupportedValuation,
  completeCoverageInput.identitySource,
), false);
const unclassifiedUnsupportedCoverage = getEtfResearchCoverage({
  identitySource: completeCoverageInput.identitySource,
  etf: unclassifiedUnsupportedValuation,
});
assert.equal(unclassifiedUnsupportedCoverage.notCovered.some((item) => item.includes("基金类别尚未核实")), true);
assert.equal(unclassifiedUnsupportedCoverage.notCovered.some((item) => item.startsWith("估值方法限制：")), false);
const verifiedDataGapInput = {
  identitySource: {
    source: "Tushare-compatible", endpoint: "fund_basic", symbol: "512010.SH",
    retrieved_at: "2026-10-09T19:00:00+08:00",
  },
  etf: {
    is_etf: true,
    symbol: "512010.SH",
    category: "industry",
    sources: [
      { endpoint: "fund_basic", as_of: "2026-10-09" },
      { endpoint: "index_dailybasic", as_of: "2026-10-09" },
    ],
    valuation_conclusion: { status: "data_gap", message: "跟踪指数估值数据未覆盖，暂不提供估值判断。" },
    gaps: ["跟踪指数估值数据未覆盖。"],
    endpoint_statuses: { index_dailybasic: "empty_no_rows" },
  },
};
const verifiedDataGapCoverage = getEtfResearchCoverage(verifiedDataGapInput);
assert.equal(verifiedDataGapCoverage.covered.includes("估值参考"), false);
assert.equal(verifiedDataGapCoverage.notCovered.includes("估值资料缺口：跟踪指数估值数据未覆盖，暂不提供估值判断。"), true);
const verifiedUnsupportedInput = {
  identitySource: {
    source: "Tushare-compatible", endpoint: "fund_basic", symbol: "518880.SH",
    retrieved_at: "2026-10-09T19:00:00+08:00",
  },
  etf: {
    is_etf: true,
    symbol: "518880.SH",
    category: "other",
    sources: [{ endpoint: "fund_basic", as_of: "2026-10-09" }],
    valuation_conclusion: { status: "not_supported", message: "现有估值规则不覆盖已核验的基金类别。" },
    endpoint_statuses: { index_dailybasic: "not_applicable" },
  },
};
const verifiedUnsupportedCoverage = getEtfResearchCoverage(verifiedUnsupportedInput);
assert.equal(verifiedUnsupportedCoverage.covered.includes("估值参考"), false);
assert.equal(verifiedUnsupportedCoverage.notCovered.includes("估值方法限制：现有估值规则不覆盖已核验的基金类别。"), true);

const limitedCoverage = getEtfResearchCoverage({
  identitySource: null,
  numericFacts: [
    {
      label: "最近收盘价", value: 3.431, unit: "元/份", symbol: "510300.SH",
      source: "Tushare-compatible", endpoint: "fund_daily", field: "close", date: "2026-10-09",
    },
    {
      label: "近一年报告收盘价变化", value: 2.1, unit: "%", symbol: "510300.SH",
      source: "Tushare-compatible", endpoint: "fund_daily", field: "close", date: "2026-10-09",
    },
    {
      label: "管理费率", value: 0.5, unit: "", symbol: "510300.SH",
      source: "Tushare-compatible", endpoint: "fund_basic", field: "management_fee", date: "2026-10-09",
    },
  ],
  sources: [
    { endpoint: "fund_daily", as_of: "2026-10-09" },
    { endpoint: "fund_basic", as_of: "2026-10-09" },
  ],
  etf: {
    is_etf: true,
    valuation_conclusion: { status: "data_gap", basis: null },
    metrics: {
      latest_price: { value: 3.431, unit: "元/份", source: "Tushare-compatible", endpoint: "fund_daily", field: "close", as_of: "2026-10-09", window: "最近报告收盘价", stale: true },
      price_change_1y: { value: 2.1, unit: "%", source: "Tushare-compatible", endpoint: "fund_daily", field: "close", as_of: "2026-10-09", window: "部分观察样本" },
      price_coverage_1y: { coverage_complete: false },
    },
  },
  evidenceGaps: ["最近收盘价已过期。", "一年历史样本不完整。"],
  notApplicable: ["index_dailybasic: not_applicable"],
});
assert.equal(limitedCoverage.covered.includes("估值参考"), false);
assert.equal(limitedCoverage.covered.includes("最近收盘价"), false);
assert.equal(limitedCoverage.limited.includes("最近收盘价"), true);
assert.equal(limitedCoverage.limited.includes("近一年报告收盘价变化"), true);
assert.equal(limitedCoverage.covered.includes("管理费率"), false);
assert.equal(limitedCoverage.notCovered.some((item) => item.includes("管理费率")), true);
assert.equal(limitedCoverage.notCovered.some((item) => item.includes("not_applicable")), true);
const incompleteMetricCoverage = getEtfResearchCoverage({
  identitySource: {
    source: "Tushare-compatible", endpoint: "fund_basic", symbol: "510300.SH",
    retrieved_at: "2026-10-09T19:00:00+08:00",
  },
  numericFacts: [
    {
      label: "管理费率", value: 0.5, unit: "%/年", symbol: "510300.SH",
      source: "Tushare-compatible", endpoint: "fund_basic", field: "management_fee", date: "2026-10-09",
    },
    {
      label: "资产净值", value: 25, unit: "亿元", symbol: "510300.SH",
      source: "Tushare-compatible", endpoint: "fund_basic", field: "net_asset", date: "2026-10-09",
    },
  ],
  sources: [{ endpoint: "fund_basic", as_of: "2026-10-09" }],
  etf: {
    is_etf: true,
    valuation_conclusion: { status: "data_gap", basis: null },
    metrics: {
      management_fee: { value: 0.5, unit: "", source: "Tushare-compatible", endpoint: "fund_basic", field: "management_fee", as_of: "2026-10-09", window: "基金资料" },
      asset_scale: { value: null, unit: "亿元", source: "Tushare-compatible", endpoint: "fund_basic", field: "net_asset", as_of: "2026-10-09", window: "基金资料" },
    },
  },
});
assert.equal(incompleteMetricCoverage.covered.includes("管理费率"), false);
assert.equal(incompleteMetricCoverage.notCovered.some((item) => item.includes("管理费率")), true);
assert.equal(incompleteMetricCoverage.covered.includes("资产净值"), false);
assert.equal(incompleteMetricCoverage.notCovered.some((item) => item.includes("资产净值")), true);
assert.match(etfNoValuationMessage(true, { is_etf: true }), /估值状态或来源未核实.*展开详情/);
assert.equal(neutralizeUnsupportedFundEvaluations("管理费率合理，基金流动性充足。"), "管理费率是否适当未评估，基金流动性是否充足未评估。");
assert.equal(neutralizeUnsupportedFundEvaluations("合理费率；充足流动性。"), "费率是否适当未评估；流动性是否充足未评估。");

const pageSource = fs.readFileSync(path.join(__dirname, "..", "frontend", "app", "page.tsx"), "utf8");
function renderPageWithFundResult(result) {
  let stateIndex = 0;
  const reactForPage = {
    useState(initialValue) {
      const index = stateIndex++;
      return [index === 1 ? result : initialValue, () => {}];
    },
    useRef(initialValue) {
      return { current: initialValue };
    },
    useEffect() {},
  };
  const pageModule = { exports: {} };
  const pageRequire = (specifier) => {
    if (specifier === "react") return reactForPage;
    if (specifier === "react/jsx-runtime") return require("react/jsx-runtime");
    if (specifier === "next/link") {
      return { __esModule: true, default: ({ children, ...props }) => React.createElement("a", props, children) };
    }
    if (specifier === "@/lib/position-market-monitor") return { ensurePositionMarketCheck: () => Promise.resolve({ items: [] }) };
    if (specifier === "@/components/TopNav") return { __esModule: true, default: () => null };
    if (specifier === "@/lib/single-security-format") return formatterModule.exports;
    throw new Error(`Unexpected page import: ${specifier}`);
  };
  const compiledPage = ts.transpileModule(pageSource, {
    compilerOptions: {
      esModuleInterop: true,
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  vm.runInNewContext(compiledPage, {
    exports: pageModule.exports,
    module: pageModule,
    process: { env: {} },
    require: pageRequire,
  });
  return renderToStaticMarkup(React.createElement(pageModule.exports.default));
}

function makeFundApiFixture(symbol, fixture) {
  const etfResearch = fixture.etf;
  return {
    status: "research_completed",
    symbol,
    name: "",
    security_type: "fund",
    verdict: etfResearch.valuation_conclusion?.message ?? "",
    research_reference_only: true,
    narrative_sentences: [],
    rationale: null,
    main_risk: null,
    invalidation_condition: null,
    explanation_items: [],
    identity_source: fixture.identitySource,
    sources: fixture.sources ?? etfResearch.sources ?? [],
    not_applicable: fixture.notApplicable ?? [],
    numeric_facts: fixture.numericFacts ?? [],
    evidence_gaps: fixture.evidenceGaps ?? etfResearch.gaps ?? [],
    investment_assumption: null,
    research_diagnostic: { rationale_source: "deterministic_etf_summary" },
    etf_research: etfResearch,
  };
}

const sharedEtfApiFixtures = [
  makeFundApiFixture("510880.SH", dividendDateSemanticsInput),
  makeFundApiFixture("510300.SH", completeCoverageInput),
  makeFundApiFixture("512010.SH", verifiedDataGapInput),
  makeFundApiFixture("518880.SH", verifiedUnsupportedInput),
];
for (const fixture of sharedEtfApiFixtures) {
  const html = renderPageWithFundResult(fixture);
  const investmentSection = html.match(/<section[^>]*aria-label="投资判断"[^>]*>[\s\S]*?<\/section>/)?.[0];
  assert.ok(investmentSection, `${fixture.symbol}: shared investment section is rendered`);
  assert.match(investmentSection, /投资判断：未评估/);
  assert.match(investmentSection, /无依据（仅针对买卖建议）/);
  assert.match(investmentSection, /当前接口未提供独立买卖判断。这是系统能力限制，不是研究后得出的投资结论。/);
  assert.doesNotMatch(investmentSection, /研究尚不完整|值得买入|result\.(?:verdict|explanation_items|etf_research|investment_assumption)/);
  assert.equal((html.match(/无依据（仅针对买卖建议）/g) ?? []).length, 1);
}
const renderedDividendFixture = renderPageWithFundResult(sharedEtfApiFixtures[0]);
assert.match(renderedDividendFixture, /ETF自身历史分位参考/);
assert.match(renderedDividendFixture, /4\.15%/);
assert.match(renderedDividendFixture, /46\.60%/);
const renderedIndexFixture = renderPageWithFundResult(sharedEtfApiFixtures[1]);
assert.match(renderedIndexFixture, /估值规则结果/);
assert.match(renderedIndexFixture, /41\.25%/);
assert.match(renderedIndexFixture, /62\.50%/);
const renderedGapFixture = renderPageWithFundResult(sharedEtfApiFixtures[2]);
assert.match(renderedGapFixture, /估值资料缺口/);
const renderedUnsupportedFixture = renderPageWithFundResult(sharedEtfApiFixtures[3]);
assert.match(renderedUnsupportedFixture, /估值方法限制/);
const v22Sources = Array.from({ length: 4 }, (_, index) => ({
  source_record_id: `tushare_news:feed:1:${index}`,
  source_type: "news_feed",
  title: `研究引用标题 ${index + 1}`,
  requested_source: "sina",
  source: null,
  published_at: "2026-10-14 09:30:00",
  retrieved_at: "2026-10-14T09:31:00+08:00",
  source_url: null,
  summary: `新闻 feed 摘录 ${index + 1}`,
  reference_only: true,
}));
const v22Evidence = v22Sources.map((source) => ({
  text: `支持证据 ${source.source_record_id}`,
  evidence_level: "low",
  source_ids: [source.source_record_id],
}));
const renderedV22 = renderPageWithFundResult({
  ...sharedEtfApiFixtures[0],
  transaction_status: {
    eligibility: "本次未评估交易资格",
    signal: "本次未提供交易信号",
  },
  research_v2_2: {
    status: "success",
    version: "v2.2",
    hypothesis: "核验底层证据是否支持当前研究判断。",
    conclusion: "当前研究结论保留证据边界。",
    layers: ["underlying_assets", "etf_product", "current_timing"].map((layer_id) => ({
      layer_id,
      adequacy: "limited",
      judgment: "现有来源只支持有限研究判断。",
      evidence_level: "low",
      supporting_evidence: layer_id === "underlying_assets" ? v22Evidence : [],
      counter_evidence: [],
      risks: [],
      thesis_changers: [],
      missing_evidence: ["仍需核验更完整的资料。"],
    })),
    next_step: "等待具体条件",
    next_step_reason: "补齐来源后再评估。",
    sources: v22Sources,
    tool_trace: [{
      tool: "search_news",
      origin: "llm_tool_use",
      hypothesis: "核验是否有近期变化。",
      evidence_need: "补充 feed 参考资料。",
      requested_source: "sina",
      request_sent: true,
      row_count: 4,
      nonempty_body_count: 4,
      source_ids: v22Sources.map((source) => source.source_record_id),
      status: "ok",
    }],
  },
});
assert.match(renderedV22, /当前研究结论保留证据边界/);
assert.match(renderedV22, /本次未评估交易资格/);
assert.match(renderedV22, /本次未提供交易信号/);
for (const source of v22Sources) {
  assert.match(renderedV22, new RegExp(source.title));
}
assert.match(renderedV22, /链接未提供/);
assert.doesNotMatch(renderedV22, /投资判断：未评估|可追溯关键数值（最多三项）|href="(?:null|undefined)"/);
assert.ok(renderedV22.indexOf("研究结论") < renderedV22.indexOf("本次未评估交易资格"));
const renderedRawJsonDisclosure = renderPageWithFundResult({
  ...sharedEtfApiFixtures[0],
  sources: [{
    source_record_id: "source:ssr-fixture",
    source_type: "news_feed",
    title: "SSR_SOURCE_TRACE_MARKER",
    summary: "SSR source trace remains available for diagnostics.",
  }],
  investment_assumption: {
    kind: "trailing_cash_dividend_baseline",
    condition: "继续观察已披露现金分红及其来源日期。",
  },
});
const sourceJsonDisclosure = renderedRawJsonDisclosure.match(/<details[^>]*><summary[^>]*>查看来源追溯字段<\/summary>[\s\S]*?<\/details>/)?.[0];
const assumptionJsonDisclosure = renderedRawJsonDisclosure.match(/<details[^>]*><summary[^>]*>查看观察条件原始字段<\/summary>[\s\S]*?<\/details>/)?.[0];
assert.ok(sourceJsonDisclosure);
assert.ok(assumptionJsonDisclosure);
assert.doesNotMatch(sourceJsonDisclosure, /^<details[^>]*\bopen(?:=|\s|>)/);
assert.doesNotMatch(assumptionJsonDisclosure, /^<details[^>]*\bopen(?:=|\s|>)/);
assert.match(sourceJsonDisclosure, /SSR_SOURCE_TRACE_MARKER/);
assert.match(assumptionJsonDisclosure, /trailing_cash_dividend_baseline/);
assert.match(renderedRawJsonDisclosure, /观察已派付现金分红是否变化/);
const renderedV22PermissionFailure = renderPageWithFundResult({
  ...sharedEtfApiFixtures[0],
  transaction_status: {
    eligibility: "本次未评估交易资格",
    signal: "本次未提供交易信号",
  },
  research_v2_2: { status: "unavailable", failure_reason: "permission_denied", sources: [], tool_trace: [] },
});
assert.match(renderedV22PermissionFailure, /新闻接口权限不足，本次未重试，也未切换来源/);
assert.match(renderedV22PermissionFailure, /本次未提供交易信号/);
const renderedV22ProtocolFailure = renderPageWithFundResult({
  ...sharedEtfApiFixtures[0],
  transaction_status: {
    eligibility: "本次未评估交易资格",
    signal: "本次未提供交易信号",
  },
  research_v2_2: { status: "unavailable", failure_reason: "response_protocol_mismatch", sources: [], tool_trace: [] },
});
assert.match(renderedV22ProtocolFailure, /模型未按约定提交结构化研究结果，本次研究已停止/);
assert.match(renderedV22ProtocolFailure, /本次未提供交易信号/);
assert.match(pageSource, /getEtfResearchCoverage\(/);
assert.match(pageSource, /hasVerifiableEtfValuation\(/);
assert.match(pageSource, /hasVerifiableEtfValuation\(\s*result\.etf_research,\s*result\.identity_source,?\s*\)/);
assert.match(pageSource, /getEtfResearchCoverage\(\{\s*identitySource: result\.identity_source,\s*numericFacts: facts,\s*sources: result\.etf_research\?\.sources,/);
assert.match(pageSource, /etfValuationConclusion\?\.label/);
assert.match(pageSource, /etfValuationConclusion\?\.message/);
assert.match(pageSource, /接口原始综合意见/);
assert.match(pageSource, /function evidenceLevelLabel/);
assert.match(pageSource, /evidenceLevelLabel\(item\.evidence_level\)/);
assert.doesNotMatch(pageSource, /canShowFundEvidenceLevels/);
assert.match(pageSource, /原始逐项说明/);
assert.match(pageSource, /aria-label="投资判断"/);
assert.match(pageSource, /aria-label="估值结论与依据"/);
assert.match(pageSource, /投资判断：未评估/);
assert.match(pageSource, /const valuationRationale = hasVerifiedEtfValuation && hasDeterministicEtfRationale/);
assert.match(pageSource, /逐项证据等级未返回/);
assert.doesNotMatch(pageSource, /无依据（响应未提供逐项标签）/);
assert.match(pageSource, /neutralizeUnsupportedFundEvaluations/);
assert.match(pageSource, /hasVerifiedEtfValuation && hasDeterministicEtfRationale/);
assert.match(pageSource, /!hasFundRiskItem && result\.main_risk/);
assert.match(pageSource, /!hasFundInvalidationItem && !result\.investment_assumption/);
assert.doesNotMatch(pageSource, /逐项证据等级也未核实/);
const indexGap = explainEtfEvidenceGap(
  "跟踪指数 000913.SH 的PE/PB当前值及十年估值分位数均未能核验：index_dailybasic 返回空结果。",
  { category: "broad", valuation_conclusion: { status: "data_gap" } },
);
assert.match(indexGap, /PE\/PB当前值及十年估值分位数均未能核验.*不提供该口径的估值判断/);
const unsupportedGap = explainEtfEvidenceGap(
  "index_dailybasic: not_applicable",
  { category: "other", valuation_conclusion: { status: "not_supported" } },
);
assert.match(unsupportedGap, /现有估值规则不覆盖已核验的基金类别/);
assert.doesNotMatch(unsupportedGap, /PE\/PB数据缺失|缺少.*估值/);
assert.match(
  explainEtfEvidenceGap(
    "最近有效收盘价日期 2026-10-08 早于预期公布日 2026-10-09，行情已过期。",
    { category: "broad", valuation_conclusion: { status: "data_gap" } },
  ),
  /已有过期标记.*不能当作当前行情/,
);
assert.match(
  explainEtfEvidenceGap(
    "基金当前成分明细与行业权重未获取。",
    { category: "broad", valuation_conclusion: { status: "conclusive", basis: "index_pe_pb" } },
  ),
  /持仓.*行业权重.*无法判断基金实际配置/,
);

const unclassifiedNotSupported = explainEtfEvidenceGap(
  "index_dailybasic: not_applicable",
  {
    category: "unclassified",
    valuation_conclusion: { status: "not_supported" },
  },
);
assert.match(unclassifiedNotSupported, /基金类别尚未核实/);
assert.doesNotMatch(unclassifiedNotSupported, /方法不适用/);
assert.match(
  etfNoValuationMessage(true, {
    category: "unclassified",
    valuation_conclusion: { status: "not_supported" },
  }),
  /基金类别尚未核实/,
);
assert.match(
  etfNoValuationMessage(true, {
    category: "other",
    valuation_conclusion: { status: "not_supported" },
  }),
  /现有估值规则不覆盖已核验的基金类别/,
);

const noDividendField = explainEtfEvidenceGap(
  "Tushare index_dailybasic没有股息率字段；底层指数股息率不可由本接口核验。",
  {
    category: "dividend",
    valuation_conclusion: { status: "conclusive", basis: "index_pe_pb" },
  },
);
assert.match(noDividendField, /股息率字段.*无法由本接口核验/);
assert.doesNotMatch(noDividendField, /PE\/PB.*未能核验|无法按现有规则判断估值/);

const ownYieldReplacementGap = explainEtfEvidenceGap(
  "跟踪指数PE/PB与指数股息率无可用覆盖；已以510880 ETF自身现金分红收益率历史分位（滚动365天）作替代参考（2025-01-01至2026-01-01，历史样本 250 个），仅与本ETF自身历史比较，不等同于指数估值，也不代表未来分红或回报。",
  {
    category: "dividend",
    valuation_conclusion: { status: "conclusive", basis: "own_dividend_yield" },
  },
);
assert.match(ownYieldReplacementGap, /自身现金分红收益率历史分位.*替代参考/);
assert.doesNotMatch(ownYieldReplacementGap, /无法判断估值/);

const validLatestPrice = {
  category: "dividend",
  valuation_conclusion: { status: "conclusive", basis: "own_dividend_yield" },
  metrics: { latest_price: { value: 3.4, as_of: "2026-10-09" } },
};
const priceHistoryGap = explainEtfEvidenceGap(
  "fund_daily 一年区间有效上市日收盘价缺少 3/250 个预期SSE交易日；日期与原因：2026-01-01(middle_session_missing)。观察到的区间指标仍按有效行情计算，未将样本称为完整一年。",
  validLatestPrice,
);
assert.match(priceHistoryGap, /一年区间.*覆盖不完整/);
assert.doesNotMatch(priceHistoryGap, /最新.*无效|当前价格.*不可核验/);

const amountHistoryGap = explainEtfEvidenceGap(
  "fund_daily 未覆盖SSE日历最近20个交易日的全部有效成交额；缺少日期：2026-10-01。",
  validLatestPrice,
);
assert.match(amountHistoryGap, /最近20个交易日的有效成交额未完整/);
assert.match(amountHistoryGap, /不能计算完整20日平均成交额/);
assert.match(amountHistoryGap, /这项缺口不表示最近有效收盘价无效/);
assert.doesNotMatch(amountHistoryGap, /最新.*无效|当前价格.*不可核验/);

const unknownGap = "unrecognized existing gap text";
assert.equal(explainEtfEvidenceGap(unknownGap, validLatestPrice), unknownGap);

const dividendAssumptionOriginal = "原条件：低于本次核验的0.143元/份；期间为滚动365天。";
const dividendAssumptionSummary = formatInvestmentAssumptionSummary(
  { kind: "trailing_cash_dividend_baseline" },
  dividendAssumptionOriginal,
);
assert.equal(dividendAssumptionSummary, "观察已派付现金分红是否变化；仅作研究观察假设。");
assert.doesNotMatch(dividendAssumptionSummary, /\d/);
const amountAssumptionSummary = formatInvestmentAssumptionSummary(
  { kind: "average_amount_20d_baseline" },
  "原条件：低于123456元；期间为滚动20个SSE交易日。",
);
assert.equal(amountAssumptionSummary, "观察同口径平均成交额是否变化；仅作研究观察假设。");
assert.doesNotMatch(amountAssumptionSummary, /\d/);
assert.equal(
  formatInvestmentAssumptionSummary({ kind: "unknown" }, dividendAssumptionOriginal),
  "观察条件请查看展开详情；仅作研究观察假设。",
);
assert.doesNotMatch(
  formatInvestmentAssumptionSummary({ kind: "unknown" }, dividendAssumptionOriginal),
  /\d/,
);
