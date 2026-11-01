const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const pageSource = fs.readFileSync(
  path.resolve(__dirname, "../frontend/app/observations/page.tsx"),
  "utf8",
);
const cashNotice = pageSource.match(
  /\{!loading && !practiceAccountId && \(\s*<section[\s\S]*?aria-label="实际账户现金占位"[\s\S]*?<\/section>\s*\)\}/,
)?.[0];

assert.ok(cashNotice, "actual-mode cash placeholder should be shown after account mode resolves");
assert.match(cashNotice, /可用现金未录入；¥0\.00 为显示占位，并非已核实余额/);
assert.doesNotMatch(cashNotice, /fetch\(|JSON\.stringify|setPracticeAccount|cash_cny|Number\(/);
assert.equal((pageSource.match(/¥0\.00/g) || []).length, 1, "placeholder amount stays a single display literal");

process.stdout.write("Card022 actual cash placeholder is display-only.\n");
