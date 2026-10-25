const isolatedDistDir = ".next-card019-20261025";
const requestedDistDir = process.env.CARD019_NEXT_DIST_DIR;

if (requestedDistDir && requestedDistDir !== isolatedDistDir) {
  throw new Error("CARD019_NEXT_DIST_DIR only permits the fixed Card 019 isolated build directory.");
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  distDir: requestedDistDir || ".next",
};

module.exports = nextConfig;
