const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

const formatterPath = path.join(__dirname, "..", "frontend", "lib", "single-security-format.ts");
const source = fs.readFileSync(formatterPath, "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const formatterModule = { exports: {} };
vm.runInNewContext(compiled, { exports: formatterModule.exports, module: formatterModule });

const {
  formatAnnualFeeSummary,
  formatAssetNetValue,
  formatDividendYield,
  formatDrawdown,
  formatFundShares,
  formatHistoricalPercentile,
  formatMeanAmount,
  isSingleSecurityResultForCode,
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
