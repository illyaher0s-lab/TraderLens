const assert = require("node:assert/strict");
const fs = require("node:fs");
const Module = require("node:module");
const path = require("node:path");
const ts = require("../node_modules/typescript");

const projectRoot = path.resolve(__dirname, "..");
const helperPath = path.join(projectRoot, "frontend", "lib", "card020-review.ts");
const helperSource = fs.readFileSync(helperPath, "utf8");
const compilation = ts.transpileModule(helperSource, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
  },
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

const {
  CARD020_REVIEW_SECTIONS,
  CARD020_REVIEW_PROTOCOL_SHA256,
  formatCard020ModelValue,
  validateCard020ParseForReview,
  validateCard020PreflightForFreeze,
  canFreezeCard020,
} = compiledModule.exports;
const protocolSha256 = CARD020_REVIEW_PROTOCOL_SHA256;
const sourceSha256 = "B".repeat(64);
const parserSha256 = "C".repeat(64);

function makeFixture() {
  const fields = CARD020_REVIEW_SECTIONS.flatMap((section) => section.fields);
  const sourceLines = ["固定策略原文", "|规则|值|", "|---|---|"];
  const sourceMappings = [];
  const values = {};
  const lineCoverage = [
    { line_number: 1, classification: "context" },
    { line_number: 2, classification: "context" },
    { line_number: 3, classification: "context" },
  ];

  fields.forEach(({ key }, index) => {
    const lineNumber = sourceLines.length + 1;
    const quote = `策略规则 ${key}`;
    sourceLines.push(quote);
    const value = fields[index].expectedValue;
    values[key] = value;
    sourceMappings.push({
      field: key,
      value,
      source_line_numbers: [lineNumber],
      source_quotes: [quote],
    });
    lineCoverage.push({ line_number: lineNumber, classification: "mapped_rule" });
  });

  const sourceText = sourceLines.join("\n");
  const result = {
    status: "ready_for_confirmation",
    fields: values,
    source_mappings: sourceMappings,
    line_coverage: lineCoverage,
    deterministic_format_lines: [3],
    blocking_fields: [],
    blocking_reasons: [],
    source_sha256: sourceSha256,
    parser_sha256: parserSha256,
  };
  const record = {
    parse_id: "card020_parse_synthetic",
    protocol_sha256: protocolSha256,
    source_sha256: sourceSha256,
    status: "ready_for_confirmation",
    result,
  };
  const preflight = {
    preflight_id: "card020_preflight_synthetic",
    protocol_sha256: protocolSha256,
    status: "passed_with_disclosed_data_limits",
    input_inventory_sha256: "D".repeat(64),
    input_inventory: {
      market: {
        snapshot_id: "market-snapshot-test",
        manifest_sha256: "1".repeat(64),
        source_status: "downloaded_unverified_for_research_use",
        adapter_validation_status: "degraded",
        provider_origin_authenticated: false,
      },
      dividends: {
        snapshot_id: "dividend-snapshot-test",
        manifest_sha256: "2".repeat(64),
        source_status: "raw_unverified (preserved from the existing adapter)",
        official_spotcheck_dates: ["2019-01-10", "2020-01-13"],
        coverage_record: "closed pre-existing coverage record",
        historical_adapter_note: "raw_unverified snapshot remains incomplete",
      },
    },
    execution_fingerprint: {
      executor_version: "card020-test",
      bundle_sha256: "E".repeat(64),
      files: { "backend/services/strategy_idea_flow.py": parserSha256 },
    },
    critical_source_gaps: [],
    data_limitations: [
      "固定行情快照可复核哈希，但不认证提供方来源。",
      "开盘可交易状态未获交易所认证，不模拟排队优先级。",
      "成交量与成交额单位文件没有把该文档绑定到原始文件。",
      "分红快照保留未验证标记，仅有有限官方抽查。",
    ],
    evidence_level: "low",
    historical_metrics_computed: false,
  };
  return { fields, sourceLines, sourceText, record, preflight };
}

function validateFixture(fixture) {
  const parse = validateCard020ParseForReview({
    record: fixture.record,
    sourceText: fixture.sourceText,
    protocolSha256,
    sourceHashVerified: true,
  });
  const preflight = validateCard020PreflightForFreeze({
    preflight: fixture.preflight,
    protocolSha256,
    parserSha256: fixture.record.result.parser_sha256,
  });
  return { parse, preflight };
}

function test(name, run) {
  run();
  process.stdout.write(`✓ ${name}\n`);
}

test("field review has six readable groups and all 44 fields", () => {
  assert.deepEqual(CARD020_REVIEW_SECTIONS.map((section) => section.title), [
    "标的与本金",
    "信号与调仓",
    "交易与成本",
    "分红和净值",
    "样本与比较账户",
    "评价与研究限制",
  ]);
  const metadata = CARD020_REVIEW_SECTIONS.flatMap((section) => section.fields);
  const keys = metadata.map((field) => field.key);
  assert.equal(keys.length, 44);
  assert.equal(new Set(keys).size, 44);
  assert(metadata.every((field) => typeof field.label === "string" && field.label.length > 0));
  assert(metadata.every((field) => typeof field.expectedValue === "string" && field.expectedValue.length > 0));
});

test("fixed known values get a Chinese reading; unknown values remain visible and untrusted", () => {
  const known = formatCard020ModelValue("symbol", "510880.SH");
  assert.equal(known.known, true);
  assert.match(known.text, /510880\.SH/);

  const unknown = formatCard020ModelValue("symbol", "mystery-instrument");
  assert.equal(unknown.known, false);
  assert.match(unknown.text, /mystery-instrument/);
});

test("complete saved parse and disclosed preflight can be confirmed only after checkbox", () => {
  const fixture = makeFixture();
  const { parse, preflight } = validateFixture(fixture);
  assert.equal(parse.ready, true, parse.issues.join("\n"));
  assert.equal(preflight.ready, true, preflight.issues.join("\n"));
  assert.equal(canFreezeCard020({ parseReady: parse.ready, preflightReady: preflight.ready, confirmationChecked: false, busy: false, frozen: false }), false);
  assert.equal(canFreezeCard020({ parseReady: parse.ready, preflightReady: preflight.ready, confirmationChecked: true, busy: false, frozen: false }), true);
});

test("missing and unknown fields are explicit blockers", () => {
  const missing = makeFixture();
  const missingKey = missing.fields[0].key;
  delete missing.record.result.fields[missingKey];
  missing.record.result.source_mappings.shift();
  const missingReview = validateFixture(missing).parse;
  assert.equal(missingReview.ready, false);
  assert(missingReview.missingFields.includes(missingKey));

  const unknown = makeFixture();
  unknown.record.result.fields.unexpected_parameter = "not silently discarded";
  const unknownReview = validateFixture(unknown).parse;
  assert.equal(unknownReview.ready, false);
  assert(unknownReview.unknownFields.includes("unexpected_parameter"));
});

test("field disagreement, incorrect citations, and uncovered lines block confirmation", () => {
  const disagreement = makeFixture();
  disagreement.record.result.source_mappings[0].value = "different model value";
  const disagreementReview = validateFixture(disagreement).parse;
  assert.equal(disagreementReview.ready, false);
  assert(disagreementReview.issues.some((issue) => issue.includes("字段记录不一致")));

  const badQuote = makeFixture();
  badQuote.record.result.source_mappings[0].source_quotes[0] = "not in the cited line";
  assert.equal(validateFixture(badQuote).parse.ready, false);

  const uncovered = makeFixture();
  uncovered.record.result.line_coverage.pop();
  assert.equal(validateFixture(uncovered).parse.ready, false);
});

test("parser or preflight protocol/fingerprint changes fail closed", () => {
  const staleParser = makeFixture();
  staleParser.preflight.execution_fingerprint.files["backend/services/strategy_idea_flow.py"] = "F".repeat(64);
  assert.equal(validateFixture(staleParser).preflight.ready, false);

  const blockedParse = makeFixture();
  blockedParse.record.result.status = "blocked";
  assert.equal(validateFixture(blockedParse).parse.ready, false);

  const blockedPreflight = makeFixture();
  blockedPreflight.preflight.critical_source_gaps = ["来源不完整"];
  assert.equal(validateFixture(blockedPreflight).preflight.ready, false);

  assert.equal(canFreezeCard020({ parseReady: true, preflightReady: false, confirmationChecked: true, busy: false, frozen: false }), false);
});
