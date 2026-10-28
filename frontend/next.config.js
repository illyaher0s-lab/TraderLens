const isolatedDistDirs = {
  CARD019_NEXT_DIST_DIR: ".next-card019-20261025",
  CARD020_NEXT_DIST_DIR: ".next-card020-20261027",
};
const requests = Object.entries(isolatedDistDirs).filter(([name]) => process.env[name]);

if (requests.length > 1) {
  throw new Error("Only one isolated TraderLens validation build directory can be selected at a time.");
}

const [requestedName, requestedDistDir] = requests[0] || [];
if (requestedDistDir && process.env[requestedName] !== requestedDistDir) {
  throw new Error(`${requestedName} only permits its fixed isolated build directory.`);
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  distDir: requestedDistDir || ".next",
  ...(requestedName === "CARD020_NEXT_DIST_DIR"
    ? { typescript: { tsconfigPath: "tsconfig.card020.json" } }
    : {}),
};

module.exports = nextConfig;
