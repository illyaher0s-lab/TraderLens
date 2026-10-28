const assert = require("node:assert/strict");
const fs = require("node:fs");
const Module = require("node:module");
const path = require("node:path");
const ts = require("../node_modules/typescript");

const projectRoot = path.resolve(__dirname, "..");
const helperPath = path.join(projectRoot, "frontend", "lib", "card020-results.ts");
const helperSource = fs.readFileSync(helperPath, "utf8");
const compilation = ts.transpileModule(helperSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  reportDiagnostics: true,
});
const errors = (compilation.diagnostics || []).filter((item) => item.category === ts.DiagnosticCategory.Error);
assert.equal(errors.length, 0, ts.formatDiagnosticsWithColorAndContext(errors, {
  getCurrentDirectory: () => projectRoot,
  getCanonicalFileName: (fileName) => fileName,
  getNewLine: () => "\n",
}));
const compiledModule = new Module(helperPath, module);
compiledModule.filename = helperPath;
compiledModule.paths = Module._nodeModulePaths(path.dirname(helperPath));
compiledModule._compile(compilation.outputText, helperPath);

const { buildCard020OutcomeSummary, formatCard020RunStatus } = compiledModule.exports;
const rawDividendGap = "The raw snapshot is marked raw_unverified; official announcement checks cover only 2019-01-10 and 2020-01-13. They do not establish full-history completeness or independently verify every historical event.";
const expectedPaths = [
  ["candidate-base", "candidate", "base", "5365.60", "365.60", "0.07312", "931.60", "0.1698078815", "55.00", "16.00"],
  ["candidate-stress", "candidate", "stress", "5355.40", "355.40", "0.07108", "932.80", "0.1701258435", "55.00", "26.20"],
  ["buy_and_hold-base", "buy_and_hold", "base", "4971.00", "-29.00", "-0.0058", "1236.80", "0.2254383726", "5.00", "3.20"],
  ["buy_and_hold-stress", "buy_and_hold", "stress", "4967.80", "-32.20", "-0.00644", "1236.80", "0.2255699434", "5.00", "6.40"],
  ["static_half-base", "static_half", "base", "4983.00", "-17.00", "-0.0034", "618.40", "0.1180017555", "5.00", "1.60"],
  ["static_half-stress", "static_half", "stress", "4981.40", "-18.60", "-0.00372", "618.40", "0.1180377935", "5.00", "3.20"],
];

function makeResult() {
  const paths = {};
  const reconciliation = {};
  for (const [pathId, account, cost, ending, pnl, ratio, ddAmount, ddRatio, commission, slippage] of expectedPaths) {
    const starting = account === "candidate" ? "5000.00" : "5000.00";
    paths[pathId] = {
      path_id: pathId,
      account_type: account,
      cost_scenario: cost,
      trade_count: account === "candidate" ? 11 : 1,
      dynamic_risk_fill_count: account === "candidate" ? 10 : 0,
      commission_total_cny: commission,
      slippage_cost_total_cny: slippage,
      metrics: {
        full: {
          start_nav_actual_cny: starting,
          end_nav_actual_cny: ending,
          evaluation_end_nav_cny: ending,
          net_gain_actual_cny: pnl,
          return_ratio: ratio,
          decision_values: {
            evaluation_end_nav_cny: ending,
            max_drawdown_amount_evaluation_cny: ddAmount,
            max_drawdown_ratio: ddRatio,
          },
        },
      },
    };
    reconciliation[pathId] = { status: "passed" };
  }
  return {
    strategy_id: "510880-vol-budget-v1",
    freeze_id: "card020_freeze_fixture",
    protocol_sha256: "A".repeat(64),
    freeze_sha256: "B".repeat(64),
    result_sha256: "C".repeat(64),
    runner_sha256: "D".repeat(64),
    execution_bundle_sha256: "E".repeat(64),
    input_inventory_sha256: "F".repeat(64),
    run_status: "completed",
    protocol_revision: 3,
    period_start_date: "2018-01-02",
    period_end_date: "2020-12-31",
    starting_capital_cny: "5000.00",
    evaluation_status: "evaluated",
    evaluation_category: "A",
    category_reasons: ["固定规则判定"],
    acceptance_status: "not_qualified",
    formal_trade_qualification: false,
    evidence_level: "low",
    historical_reuse: true,
    not_out_of_sample: true,
    reconciliation_status: "passed",
    path_ids: expectedPaths.map(([pathId]) => pathId),
    paths,
    reconciliation,
    data_provenance: {
      market: { source_status: "downloaded_unverified_for_research_use", provider_origin_authenticated: false },
      dividends: { source_status: "raw_unverified", evidence_gap: rawDividendGap },
      critical_source_gaps: [],
      data_limitations: ["市场来源未认证。", "历史样本重复使用。"],
    },
  };
}

function makeRunRecord(result = makeResult()) {
  return {
    run_id: "card020_run_fixture",
    freeze_id: result.freeze_id,
    status: "completed",
    result,
  };
}

function test(name, run) {
  run();
  process.stdout.write(`✓ ${name}\n`);
}

test("persisted run statuses display in Chinese and unknown values stay explicit", () => {
  assert.equal(typeof formatCard020RunStatus, "function");
  assert.equal(formatCard020RunStatus("completed"), "已完成");
  assert.equal(formatCard020RunStatus("running"), "运行中");
  assert.equal(formatCard020RunStatus("failed"), "失败");
  assert.equal(formatCard020RunStatus("unexpected"), "状态未知");
  assert.equal(formatCard020RunStatus(null), "状态未知");
});

test("saved result produces six formatted Chinese comparison rows and A remains research-only", () => {
  const record = makeRunRecord();
  assert.equal("run_id" in record.result, false);
  const summary = buildCard020OutcomeSummary(record);
  assert.equal(summary.ready, true, summary.issues.join("\n"));
  assert.equal(summary.metricsTrusted, true);
  assert.equal(summary.rows.length, 6);
  const candidate = summary.rows.find((row) => row.pathId === "candidate-base");
  assert.equal(candidate.pnlState, "profit");
  assert.equal(candidate.pnlText, "模拟盈利 +365.60 元（+7.31%）");
  assert.equal(candidate.endingNavText, "5,365.60 元");
  assert.equal(candidate.drawdownAmountText, "931.60 元");
  assert.equal(candidate.commissionText, "55.00 元");
  assert.equal(candidate.slippageText, "16.00 元");
  assert.match(candidate.costLabel, /单边滑点 0.05%/);
  assert.match(summary.categoryLabel, /A 类/);
  assert.match(summary.eligibilityText, /未获正式策略资格/);
  assert.match(summary.eligibilityText, /正式交易计划或交易信号/);
  assert(summary.sourceSummary.some((item) => item.includes("仅覆盖 2019-01-10 和 2020-01-13")));
  assert(summary.sourceSummary.some((item) => item.includes("不能证明完整历史覆盖")));
  assert.equal(summary.sourceSummary.some((item) => item.includes(rawDividendGap)), false);
  assert.equal(summary.staticHalfTradeoffs[0].candidateEndingNavHigher, true);
  assert.equal(summary.staticHalfTradeoffs[0].staticHalfDrawdownLower, true);
});

test("negative saved P&L is described as a loss, not overwritten by example gains", () => {
  const record = makeRunRecord();
  const result = record.result;
  result.evaluation_category = "B";
  result.paths["candidate-base"].metrics.full.end_nav_actual_cny = "4900.00";
  result.paths["candidate-base"].metrics.full.evaluation_end_nav_cny = "4900.00";
  result.paths["candidate-base"].metrics.full.net_gain_actual_cny = "-100.00";
  result.paths["candidate-base"].metrics.full.return_ratio = "-0.02";
  result.paths["candidate-base"].metrics.full.decision_values.evaluation_end_nav_cny = "4900.00";

  const summary = buildCard020OutcomeSummary(record);
  const candidate = summary.rows.find((row) => row.pathId === "candidate-base");
  assert.equal(candidate.pnlState, "loss");
  assert.equal(candidate.pnlText, "模拟亏损 -100.00 元（-2.00%）");
  assert.notEqual(candidate.pnlText, "模拟盈利 +365.60 元（+7.31%）");
});

test("missing values or failed reconciliation block numerical conclusions", () => {
  const missing = makeRunRecord();
  delete missing.result.paths["candidate-base"].metrics.full.decision_values.max_drawdown_ratio;
  const missingSummary = buildCard020OutcomeSummary(missing);
  assert.equal(missingSummary.ready, false);
  assert.equal(missingSummary.metricsTrusted, false);
  assert.equal(missingSummary.rows.find((row) => row.pathId === "candidate-base").pnlState, "unknown");

  const unreconciled = makeRunRecord();
  unreconciled.result.reconciliation["static_half-stress"].status = "failed";
  const blocked = buildCard020OutcomeSummary(unreconciled);
  assert.equal(blocked.ready, false);
  assert.equal(blocked.metricsTrusted, false);
  assert.match(blocked.issues.join(" "), /核账/);
});

test("A classification cannot imply official qualification; reused-sample disclosure is required", () => {
  const result = makeRunRecord();
  result.result.formal_trade_qualification = true;
  const inconsistent = buildCard020OutcomeSummary(result);
  assert.equal(inconsistent.ready, false);
  assert.equal(inconsistent.metricsTrusted, false);

  const missingBoundary = makeRunRecord();
  delete missingBoundary.result.not_out_of_sample;
  const boundary = buildCard020OutcomeSummary(missingBoundary);
  assert.equal(boundary.ready, false);
  assert.equal(boundary.metricsTrusted, false);
});

test("C explanation follows the saved reason and does not invent the trigger", () => {
  const noFills = makeRunRecord();
  noFills.result.evaluation_category = "C";
  noFills.result.category_reasons = ["初始建仓以外，没有实际成交形成动态风险调整。"];
  const noFillSummary = buildCard020OutcomeSummary(noFills);
  assert.match(noFillSummary.categoryMessage, /没有出现初始建仓以外的实际调仓成交/);

  const dominated = makeRunRecord();
  dominated.result.evaluation_category = "C";
  dominated.result.category_reasons = ["同一简单对照在基础与压力成本下均支配候选：buy_and_hold。"];
  const dominatedSummary = buildCard020OutcomeSummary(dominated);
  assert.match(dominatedSummary.categoryMessage, /同一个简单对照在基础和压力两种成本情景下均达到固定支配条件/);
});

test("outer run identity and freeze reference are required and must match the immutable result", () => {
  const missingRunId = makeRunRecord();
  delete missingRunId.run_id;
  const missing = buildCard020OutcomeSummary(missingRunId);
  assert.equal(missing.ready, false);
  assert.equal(missing.metricsTrusted, false);
  assert.equal(missing.rows[0].pnlState, "unknown");

  const mismatchedFreeze = makeRunRecord();
  mismatchedFreeze.freeze_id = "card020_freeze_other";
  const mismatch = buildCard020OutcomeSummary(mismatchedFreeze);
  assert.equal(mismatch.ready, false);
  assert.equal(mismatch.metricsTrusted, false);
  assert.match(mismatch.issues.join(" "), /冻结/);
});
