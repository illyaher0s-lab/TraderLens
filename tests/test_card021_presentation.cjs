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
compiledPanel._compile(compilation.outputText, panelPath);

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
  assert.match(summary.accountText, /持仓、可卖份额、现金和分红应收均未保存或读取/);
  assert.match(summary.historicalDecisionText, /快照当时的研究操作判断：研究规则指向买入/);
  assert.match(summary.decisionTitle, /当前无法判断是否买卖/);
  assert.match(summary.currentDecisionReason, /历史行情.*未保存当前账户资料/);
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
  assert.match(summary.nextSignalText, /下一信号日期尚未核实/);
  assert.match(summary.decisionTitle, /当前无法判断是否买卖/);
  assert.match(summary.currentDecisionReason, /已过有效期/);
  assert.doesNotMatch(summary.decisionTitle + summary.currentDecisionReason, /指向买入/);
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

test("technical evidence stays available in a collapsed native details section", () => {
  const detailsTag = panelSource.match(/<details[^>]*>/)?.[0];
  assert(detailsTag, "technical evidence needs a native details disclosure");
  assert.doesNotMatch(detailsTag, /\bopen\b/);
  assert.match(panelSource, /<summary[^>]*>技术证据与来源限制<\/summary>/);
  assert.match(panelSource, /text-xl font-bold/);
  for (const field of ["decisionTitle", "currentDecisionReason", "accountText", "nextStepText", "oldTargetAttemptText", "nextSignalText", "caveatText", "explanationSourceText"])
    assert(panelSource.includes(`summary.${field}`), `page must display ${field}`);
  for (const field of ["protocol_sha256", "market_input_sha256", "snapshot_sha256", "sources"])
    assert(panelSource.includes(field), `technical evidence must retain ${field}`);
});
