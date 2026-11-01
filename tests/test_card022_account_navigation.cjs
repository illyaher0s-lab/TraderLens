const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const pageSource = fs.readFileSync(
  path.resolve(__dirname, "../frontend/app/observations/page.tsx"),
  "utf8",
);

assert.match(pageSource, /loading \? "正在加载持仓…"/);
const accountTabs = pageSource.match(/<nav aria-label="账户类型"[\s\S]*?<\/nav>/)?.[0];
assert.ok(accountTabs, "My Positions needs visible account type navigation");
assert.match(accountTabs, /href="\/observations"/, "actual records remain the default entry");
assert.match(pageSource, /const practiceAccountHref = `\/observations\?practice_account_id=card022-510880/);
assert.match(accountTabs, /href=\{practiceAccountHref\}/);
assert.match(pageSource, /card021_observation=\$\{encodeURIComponent\(practiceObservationId\)\}/);
assert.match(accountTabs, /实际记录/);
assert.match(accountTabs, /模拟练习/);
assert.match(accountTabs, /aria-current=\{!loading && !practiceAccountId \? "page" : undefined\}/);
assert.match(accountTabs, /aria-current=\{!loading && practiceAccountId \? "page" : undefined\}/);

const emptyStateStart = pageSource.indexOf("{!loading && positions.length === 0 && executionLogs.length === 0 && (");
assert.notEqual(emptyStateStart, -1, "empty-state copy needs a mode-aware check");
const emptyStateEnd = pageSource.indexOf("</main>", emptyStateStart);
const emptyState = pageSource.slice(emptyStateStart, emptyStateEnd);
const practiceBranchStart = emptyState.indexOf("{practiceAccountId ? (");
const actualBranchStart = emptyState.indexOf(") : (", practiceBranchStart);
assert.ok(practiceBranchStart >= 0 && actualBranchStart > practiceBranchStart);
const practiceEmptyState = emptyState.slice(practiceBranchStart, actualBranchStart);
const actualEmptyState = emptyState.slice(actualBranchStart);
assert.match(practiceEmptyState, /模拟账户目前暂无持仓或成交记录/);
assert.match(practiceEmptyState, /目前仅限 510880.*其他 ETF 的模拟成交不能登记在此账户/);
assert.doesNotMatch(practiceEmptyState, /Workbench|workbench|真实成交|我已经买入/);
assert.match(practiceEmptyState, /href="\/#research"/);
assert.match(actualEmptyState, /Workbench/, "actual empty state keeps its existing guidance");

process.stdout.write("Card022 account navigation contracts passed.\n");
