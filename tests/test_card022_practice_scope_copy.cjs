const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const pageSource = fs.readFileSync(
  path.resolve(__dirname, "../frontend/app/observations/page.tsx"),
  "utf8",
);
const emptyStateStart = pageSource.indexOf("{!loading && positions.length === 0 && executionLogs.length === 0 && (");
assert.notEqual(emptyStateStart, -1, "empty state should stay scoped to an empty account");
const emptyStateEnd = pageSource.indexOf("</main>", emptyStateStart);
const emptyState = pageSource.slice(emptyStateStart, emptyStateEnd);
const practiceBranchStart = emptyState.indexOf("{practiceAccountId ? (");
const actualBranchStart = emptyState.indexOf(") : (", practiceBranchStart);
assert.ok(practiceBranchStart >= 0 && actualBranchStart > practiceBranchStart);
const practiceEmptyState = emptyState.slice(practiceBranchStart, actualBranchStart);

assert.match(practiceEmptyState, /这份 Card022 模拟练习账户目前仅限 510880/);
assert.match(practiceEmptyState, /其他 ETF 的模拟成交不能登记在此账户/);
assert.match(practiceEmptyState, /href="\/#research" style=\{styles\.emptyLink\}>返回研究入口<\/Link>/);
assert.doesNotMatch(practiceEmptyState, /510880 研究入口/);

process.stdout.write("Card022 practice account scope copy passed.\n");
