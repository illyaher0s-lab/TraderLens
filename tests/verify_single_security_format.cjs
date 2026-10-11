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
} = formatterModule.exports;

assert.equal(formatDividendYield(4.1861826698), "4.19%");
assert.equal(formatHistoricalPercentile(48.825710754), "49%");
assert.equal(formatDrawdown(-3.366336633), "3.37%");
assert.equal(formatDrawdown(0), "0.00%");
assert.equal(formatDrawdown(null), "未获取");
assert.equal(formatDrawdown(Number.NaN), "未获取");
assert.equal(formatDrawdown(Number.POSITIVE_INFINITY), "未获取");
assert.equal(formatMeanAmount(447074604.09999996), "4.47亿元");
assert.equal(formatAssetNetValue(25177624140.25), "251.8亿元");
assert.equal(formatFundShares(560067.57), "56.0亿份");
assert.equal(formatAnnualFeeSummary(0.5, 0.1), "管理费0.5% + 托管费0.1% = 合计0.6%/年");
assert.equal(formatAnnualFeeSummary(0.5, null), null);
