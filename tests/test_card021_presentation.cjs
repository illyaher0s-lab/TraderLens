const assert = require("node:assert/strict");
const fs = require("node:fs");
const Module = require("node:module");
const path = require("node:path");
const ts = require("../node_modules/typescript");

const projectRoot = path.resolve(__dirname, "..");
const panelPath = path.join(projectRoot, "frontend", "components", "Card021LiveSignalPanel.tsx");
const panelSource = fs.readFileSync(panelPath, "utf8");
const compilation = ts.transpileModule(panelSource, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
    jsx: ts.JsxEmit.ReactJSX,
  },
  reportDiagnostics: true,
});
const errors = (compilation.diagnostics || []).filter((item) => item.category === ts.DiagnosticCategory.Error);
assert.equal(errors.length, 0, ts.formatDiagnosticsWithColorAndContext(errors, {
  getCurrentDirectory: () => projectRoot,
  getCanonicalFileName: (fileName) => fileName,
  getNewLine: () => "\n",
}));
const compiledPanel = new Module(panelPath, module);
compiledPanel.filename = panelPath;
compiledPanel.paths = Module._nodeModulePaths(path.dirname(panelPath));
const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {
  if (request === "@/components/LiveLoopPanel") return function LiveLoopPanelStub() { return null; };
  return originalLoad.call(this, request, parent, isMain);
};
try {
  compiledPanel._compile(compilation.outputText, panelPath);
} finally {
  Module._load = originalLoad;
}

const { buildCard021Summary } = compiledPanel.exports;
assert.equal(typeof buildCard021Summary, "function", "Card021 needs a deterministic page summary");

function makeObservation(overrides = {}) {
  return {
    status: "available",
    strategy_id: "510880-vol-budget-v1",
    protocol_revision: 3,
    symbol: "510880.SH",
    evidence_level: "低",
    retrieved_at: "2026-10-29T15:50:54+08:00",
    signal_date: "2026-09-30",
    latest_market_data_date: "2026-10-28",
    target_weight_percentage: "58.9172130881",
    target_validity_status: "active_until_next_month_end",
    target_valid_until: "2026-10-30",
    next_possible_attempt_date: "2026-10-30",
    earliest_attempt_after_signal_date: "2026-10-08",
    action_decision: "not_decidable",
    execution_gate: "blocked_missing_account_nav_or_cash",
    account_data_status: "no_user_confirmed_records",
    account_source: null,
    actual_shares: null,
    sellable_shares_as_of_latest_market_data: null,
    account_target_shares: null,
    actual_delta_shares: null,
    model_account_cash_cny: "5000.00",
    model_reference_shares: 800,
    target_price_raw_cny: "3.3680000000",
    retry_policy_status: "conditional_unresolved_remainder_not_tracked",
    retry_rule: "本页不跟踪未完成委托余量。",
    ...overrides,
  };
}

function test(name, run) {
  run();
  process.stdout.write(`✓ ${name}\n`);
}

test("empty account is undecidable and does not imply a zero-share order", () => {
  const summary = buildCard021Summary(makeObservation());
  assert.match(summary.decisionTitle, /当前无法判断是否买卖/);
  assert.match(summary.currentDecisionReason, /不能计算真实账户差额/);
  assert.match(summary.accountText, /没有可核实的用户确认成交记录/);
  assert.match(summary.accountText, /实际买卖数量无法确定/);
  assert.match(summary.accountText, /持仓/);
  assert.match(summary.accountText, /现金/);
  assert.match(summary.accountText, /未完成委托/);
  assert.match(summary.nextStepText, /查询最新观察/);
  assert.match(summary.nextStepText, /分红应收/);
  assert.match(summary.oldTargetAttemptText, /不是新买入信号/);
  assert.match(summary.nextSignalText, /2026-10-30 收盘后/);
  assert.match(summary.caveatText, /正式策略资格未授予/);
  assert.match(summary.explanationSourceText, /未调用真实 LLM/);
});

test("unavailable market evidence yields no target or action", () => {
  const summary = buildCard021Summary(makeObservation({
    status: "unavailable",
    failure_message: "61 个有效复权收盘价不完整。",
    action_decision: "buy",
    target_weight_percentage: null,
    model_reference_shares: null,
  }));
  assert.match(summary.signalText, /未生成/);
  assert.match(summary.targetText, /没有可核验的目标仓位/);
  assert.match(summary.currentDecisionReason, /行情数据不足/);
  assert.doesNotMatch(summary.currentDecisionReason, /指向买入/);
});

test("historical snapshots identify the model reference as non-account quantity", () => {
  const summary = buildCard021Summary(makeObservation({
    snapshot_mode: "saved_market_snapshot",
    snapshot_historical: true,
    account_data_status: "not_saved_or_read",
    action_decision: "buy",
  }));
  assert.match(summary.observationLabel, /历史行情快照/);
  assert.match(summary.modelText, /5,000 元模型参考/);
  assert.match(summary.modelText, /800 份/);
  assert.match(summary.modelText, /3\.3680000000 元/);
  assert.match(summary.modelText, /不是实际账户买入数量/);
  assert.match(summary.accountText, /没有保存或读取持仓、可卖份额、现金和分红应收/);
  assert.match(summary.historicalDecisionText, /快照当时的研究操作判断：研究参考方向：买入/);
  assert.match(summary.decisionTitle, /保存的观察记录/);
  assert.match(summary.currentDecisionReason, /历史行情快照，没有当前账户资料/);
  assert.doesNotMatch(summary.decisionTitle, /买入/);
});

test("old target attempt and next month-end signal are clearly separate", () => {
  const summary = buildCard021Summary(makeObservation());
  assert.match(summary.oldTargetAttemptText, /旧目标下一可能尝试日：2026-10-30/);
  assert.match(summary.oldTargetAttemptText, /不是新买入信号/);
  assert.match(summary.nextSignalText, /新目标须在 2026-10-30 收盘后生成/);
});

test("expired target does not invent the next signal date", () => {
  const summary = buildCard021Summary(makeObservation({
    target_validity_status: "expired",
    target_valid_until: "2026-10-30",
    next_possible_attempt_date: "2026-11-02",
    execution_gate: "blocked_target_expired",
    action_decision: "buy",
  }));
  assert.match(summary.currentDecisionReason, /已过有效期/);
  assert.match(summary.nextSignalText, /下一月末信号候选日为 2026-10-30/);
  assert.match(summary.decisionTitle, /当前无法判断是否买卖/);
  assert.match(summary.currentDecisionReason, /已过有效期/);
  assert.doesNotMatch(summary.decisionTitle + summary.currentDecisionReason, /指向买入/);
});

test("month-end target can remain date-valid while no compliant attempt remains", () => {
  const summary = buildCard021Summary(makeObservation({
    target_validity_status: "active_until_next_month_end",
    execution_opportunity_status: "none_before_expiry",
    target_valid_until: "2026-10-30",
    next_possible_attempt_date: "2026-11-02",
    execution_gate: "blocked_no_valid_execution_attempt",
    account_data_status: "account_opened_after_signal_date",
    action_decision: "buy",
  }));
  assert.match(summary.currentDecisionReason, /本日开盘尝试时点已过/);
  assert.match(summary.currentDecisionReason, /本期无剩余合规尝试机会/);
  assert.doesNotMatch(summary.currentDecisionReason + summary.oldTargetAttemptText, /旧目标已过期/);
  assert.match(summary.oldTargetAttemptText, /有效期截至 2026-10-30 收盘/);
  assert.match(summary.nextSignalText, /下一月末信号候选日为 2026-10-30/);
  assert.match(summary.decisionTitle, /当前无法判断是否买卖/);
  assert.doesNotMatch(summary.decisionTitle + summary.currentDecisionReason, /指向买入/);
});

test("saved legacy observation is presented by its recorded close-time validity", () => {
  const summary = buildCard021Summary(makeObservation({
    snapshot_mode: "saved_practice_observation",
    snapshot_historical: true,
    judgment_at: "2026-10-30T11:48:07.975410+08:00",
    target_validity_status: "expired",
    target_valid_until: "2026-10-30",
    next_possible_attempt_date: "2026-11-02",
    execution_gate: "blocked_target_expired",
    account_data_status: "account_opened_after_signal_date",
    action_decision: "buy",
  }));
  assert.match(summary.currentDecisionReason, /有效期截至 2026-10-30 收盘/);
  assert.match(summary.currentDecisionReason, /本期无剩余合规尝试机会/);
  assert.equal(summary.targetTimeStatusText, "有效至 2026-10-30 收盘");
  assert.equal(summary.executionOpportunityText, "本期无剩余合规尝试机会");
  assert.equal(summary.retryPolicyText, "无剩余有效尝试日");
  assert.match(panelSource, /时间状态 \{summary\.targetTimeStatusText\}/);
  assert.match(panelSource, /执行机会 \{summary\.executionOpportunityText\}/);
  assert.match(panelSource, /重试策略状态 \{summary\.retryPolicyText\}/);
  assert.doesNotMatch(summary.currentDecisionReason + summary.oldTargetAttemptText, /旧目标已过期|旧目标有效期.*现已过期/);
  assert.match(summary.nextStepText, /不沿用旧目标方向/);
  assert.match(summary.decisionTitle, /保存的观察记录/);
});

test("missing account data suppresses an inconsistent buy label", () => {
  const summary = buildCard021Summary(makeObservation({
    action_decision: "buy",
    execution_gate: "blocked_missing_account_nav_or_cash",
    account_data_status: "no_user_confirmed_records",
  }));
  assert.match(summary.currentDecisionReason, /账户净值|现金|成交记录/);
  assert.match(summary.accountText, /实际买卖数量无法确定/);
  assert.match(summary.decisionTitle, /当前无法判断是否买卖/);
  assert.doesNotMatch(summary.decisionTitle + summary.currentDecisionReason, /指向买入/);
});

test("missing execution evidence suppresses an inconsistent buy label", () => {
  const summary = buildCard021Summary(makeObservation({
    execution_gate: undefined,
    action_decision: "buy",
  }));
  assert.match(summary.currentDecisionReason, /执行门槛缺失/);
  assert.match(summary.decisionTitle, /当前无法判断是否买卖/);
  assert.doesNotMatch(summary.decisionTitle + summary.currentDecisionReason, /指向买入/);
});

test("simulated practice observations keep signal NAV, current cash, and non order status distinct", () => {
  const summary = buildCard021Summary(makeObservation({
    selected_account_mode: "simulated_practice",
    account_mode: "simulated_practice",
    account_data_status: "simulated_practice_account_available",
    account_cash_cny: "3200.00",
    account_cash_at_signal_cny: "4000.00",
    shares_at_signal: 200,
    dividend_receivable_at_signal_cny: "0.00",
    account_nav_at_signal_cny: "4673.60",
    actual_shares: 600,
    account_target_shares: 1200,
    actual_delta_shares: 600,
    account_revision: 2,
    account_as_of_date: "2026-10-30",
    account_valuation_date: "2026-10-29",
    action_decision: "buy",
    suggested_quantity_shares: 600,
    suggested_action_date: "2026-10-30",
    research_action_reason: "当前现金足以覆盖冻结目标差额。",
    execution_gate: "blocked_attempt_date_constraints_not_checked",
  }));
  assert.match(summary.accountText, /Card022 模拟练习账户/);
  assert.match(summary.accountText, /当前现金 ¥3200/);
  assert.match(summary.accountText, /信号日 NAV ¥4673\.60/);
  assert.match(summary.accountText, /与当前现金分开/);
  assert.match(summary.accountText, /账户版本 2/);
  assert.match(summary.decisionTitle, /仅研究参考/);
  assert.match(summary.currentDecisionReason, /尚未核实/);
  assert.match(summary.nextStepText, /真实模拟成交价和日期/);
  assert.match(panelSource, /practiceObservationId=\{observation\.practice_observation_id\}/);
  assert.match(panelSource, /practice_account_id=card022-510880/);
});

test("unknown practice dividend evidence is explicit and suppresses the account direction", () => {
  const summary = buildCard021Summary(makeObservation({
    selected_account_mode: "simulated_practice",
    account_mode: "simulated_practice",
    account_data_status: "dividend_source_coverage_incomplete",
    dividend_receivable_at_signal_cny: null,
    account_nav_at_signal_cny: null,
  }));
  assert.match(summary.accountText, /行情或复权因子覆盖不完整/);
  assert.match(summary.accountText, /分红应收保持未知/);
  assert.match(summary.decisionTitle, /当前无法判断是否买卖/);
  assert.doesNotMatch(summary.decisionTitle + summary.currentDecisionReason, /指向买入/);
});

test("after-close observation separates expired target from the pending month-end data", () => {
  const summary = buildCard021Summary(makeObservation({
    selected_account_mode: "simulated_practice",
    account_mode: "simulated_practice",
    account_data_status: "account_opened_after_signal_date",
    account_as_of_date: "2026-10-30",
    account_cash_cny: "5000.00",
    target_validity_status: "expired",
    target_valid_until: "2026-10-30",
    execution_gate: "blocked_target_expired",
    market_data_freshness: {
      status: "awaiting_data_cutoff",
      timezone: "Asia/Shanghai",
      cutoff_time_local: "17:00",
      expected_data_date: "2026-10-30",
      last_available_date: "2026-10-29",
      missing_endpoints: [],
    },
  }));

  assert.equal(summary.decisionTitle, "旧目标已失效；新月末信号等数据");
  assert.match(summary.accountText, /当前余额不能代替信号日 NAV/);
  assert.match(summary.marketDataStatusText, /2026-10-29/);
  assert.match(summary.marketDataStatusText, /17:00/);
  assert.match(summary.nextSignalText, /旧目标已失效/);
  assert.match(summary.nextSignalText, /17:00/);
  assert.match(summary.nextStepText, /数据.*到齐后再查询/);
});

test("after-cutoff missing data says the old target expired and the new signal is unavailable", () => {
  const summary = buildCard021Summary(makeObservation({
    status: "unavailable",
    failure_code: "latest_market_data_missing",
    failure_message: "最新已完成交易日的行情或复权因子尚未齐备。",
    selected_account_mode: "simulated_practice",
    account_mode: "simulated_practice",
    target_validity_status: "expired",
    target_valid_until: "2026-10-30",
    market_data_freshness: {
      status: "same_day_data_missing",
      timezone: "Asia/Shanghai",
      cutoff_time_local: "17:00",
      expected_data_date: "2026-10-30",
      last_available_date: "2026-10-29",
      missing_endpoints: ["fund_daily", "fund_adj"],
    },
  }));

  assert.equal(summary.decisionTitle, "旧目标已失效；新月末信号等数据");
  assert.match(summary.marketDataStatusText, /2026-10-29/);
  assert.match(summary.marketDataStatusText, /日行情.*复权/);
  assert.match(summary.nextSignalText, /新月末信号.*数据/);
  assert.match(summary.accountText, /行情数据未齐.*未读取模拟账户/);
  assert.doesNotMatch(summary.accountText, /当前现金 ¥5000/);
  assert.match(summary.nextStepText, /不沿用旧目标/);
});

test("client initialization failure shows a safe configuration category", () => {
  const summary = buildCard021Summary(makeObservation({
    status: "unavailable",
    failure_code: "market_client_unavailable",
    error_type: "ValueError",
    failure_category: "client_configuration_error",
    cause_type: "ValueError",
    market_data_freshness: { status: "unverified" },
  }));

  assert.match(summary.marketDataStatusText, /客户端配置错误/);
  assert.match(summary.marketDataStatusText, /ValueError/);
});

test("source query failure identifies the failed endpoint and sanitized error type", () => {
  const summary = buildCard021Summary(makeObservation({
    status: "unavailable",
    failure_code: "market_source_query_failed",
    failed_endpoint: "fund_adj",
    error_type: "ValueError",
    failure_category: "network_timeout",
    cause_type: "Timeout",
    http_status: null,
    market_data_freshness: {
      status: "source_query_failed",
      last_available_date: null,
    },
  }));

  assert.match(summary.marketDataStatusText, /复权因子（fund_adj）/);
  assert.match(summary.marketDataStatusText, /网络超时/);
  assert.match(summary.marketDataStatusText, /Timeout/);
  assert.match(summary.marketDataStatusText, /最近共同数据截至 未获取/);
});

test("technical evidence stays available in a collapsed native details section", () => {
  const detailsTag = panelSource.match(/<details[^>]*>/)?.[0];
  assert(detailsTag, "technical evidence needs a native details disclosure");
  assert.doesNotMatch(detailsTag, /\bopen\b/);
  assert.match(panelSource, /<summary[^>]*>技术证据与来源限制<\/summary>/);
  assert.match(panelSource, /text-xl font-bold/);
  for (const field of ["decisionTitle", "currentDecisionReason", "accountText", "marketDataStatusText", "nextStepText", "oldTargetAttemptText", "nextSignalText", "caveatText", "explanationSourceText"])
    assert(panelSource.includes(`summary.${field}`), `page must display ${field}`);
  for (const field of ["protocol_sha256", "market_input_sha256", "snapshot_sha256", "sources"])
    assert(panelSource.includes(field), `technical evidence must retain ${field}`);
});
