const assert = require("node:assert/strict");
const fs = require("node:fs");
const Module = require("node:module");
const path = require("node:path");
const ts = require("typescript");

const pagePath = path.resolve(__dirname, "../frontend/app/observations/page.tsx");
const source = fs.readFileSync(pagePath, "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
}).outputText;

async function loadError(fetchResult) {
  let stateIndex = 0;
  let message = null;
  const effects = [];
  const fakeReact = {
    useState(initial) {
      const index = stateIndex++;
      return [initial, (value) => { if (index === 5) message = value; }];
    },
    useEffect(effect) { effects.push(effect); },
  };
  const originalLoad = Module._load;
  const originalFetch = global.fetch;
  const originalWindow = global.window;
  const originalConsoleError = console.error;
  global.fetch = fetchResult;
  global.window = { location: { search: "?practice_account_id=card022-510880" } };
  console.error = () => {};
  Module._load = function(request, parent, isMain) {
    if (request === "react") return fakeReact;
    if (request === "react/jsx-runtime") return { jsx: () => ({}), jsxs: () => ({}), Fragment: Symbol("Fragment") };
    if (request === "next/link") return { __esModule: true, default: () => null };
    if (request === "@/lib/position-market-monitor") return { ensurePositionMarketCheck: async () => ({ items: [] }) };
    if (request === "@/lib/api-client") return {};
    if (request === "@/components/TopNav") return { __esModule: true, default: () => null };
    return originalLoad.call(this, request, parent, isMain);
  };
  try {
    const page = new Module(pagePath, module);
    page.filename = pagePath;
    page.paths = Module._nodeModulePaths(path.dirname(pagePath));
    page._compile(compiled, pagePath);
    page.exports.default();
    for (const effect of effects) effect();
    await new Promise((resolve) => setImmediate(resolve));
    return message;
  } finally {
    Module._load = originalLoad;
    global.fetch = originalFetch;
    global.window = originalWindow;
    console.error = originalConsoleError;
  }
}

(async () => {
  const conflict = await loadError(async () => ({
    ok: false, status: 409, json: async () => ({ detail: "模拟练习账户尚未初始化。" }),
  }));
  assert.match(conflict, /模拟练习账户尚未初始化/);
  assert.doesNotMatch(conflict, /请检查后端服务/);
  const networkError = await loadError(async () => { throw new TypeError("Failed to fetch"); });
  assert.match(networkError, /检查后端服务/);
  console.log("Observation error handling passed.");
})().catch((error) => { console.error(error); process.exitCode = 1; });
