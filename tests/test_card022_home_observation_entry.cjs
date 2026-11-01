const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const pageSource = fs.readFileSync(
  path.resolve(__dirname, "../frontend/app/page.tsx"),
  "utf8",
);

function assertPageMatches(pattern, message) {
  assert.ok(pattern.test(pageSource), message);
}

assertPageMatches(
  /const \[showCard021Observation, setShowCard021Observation\] = useState\(false\);/,
  "home needs local state for opening the existing observation panel",
);

const entryLabelIndex = pageSource.indexOf("打开 510880 策略观察");
assert.notEqual(entryLabelIndex, -1, "home needs a direct 510880 observation entry");
const entryButtonStart = pageSource.lastIndexOf("<button", entryLabelIndex);
const entryButtonEnd = pageSource.indexOf("</button>", entryLabelIndex);
assert.ok(entryButtonStart >= 0 && entryButtonEnd > entryButtonStart, "direct entry must be a button");
const entryButton = pageSource.slice(entryButtonStart, entryButtonEnd + "</button>".length);
assert.match(entryButton, /type="button"/);
assert.match(entryButton, /aria-controls="card021-observation"/);
assert.match(entryButton, /onClick=\{\(\) => setShowCard021Observation\(true\)\}/);
assert.doesNotMatch(entryButton, /researchSecurity|fetch\(|single-security|loadObservation/);

assertPageMatches(
  /const card021PanelVisible = showCard021Observation \|\| Boolean\(\s*card021SnapshotId \|\| card021PracticeObservationId \|\| result\?\.symbol === "510880\.SH",\s*\);/,
  "direct entry must reveal the existing panel while preserving research and saved-record entries",
);
assertPageMatches(/id="card021-observation"[\s\S]*?<Card021LiveSignalPanel/, "the direct entry must reveal Card021's existing panel");
assertPageMatches(/snapshotId=\{card021SnapshotId\}/, "saved market snapshots must remain connected");
assertPageMatches(/practiceObservationId=\{card021PracticeObservationId\}/, "saved practice observations must remain connected");

process.stdout.write("Card022 home observation entry contract passed.\n");
