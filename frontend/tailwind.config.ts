import type { Config } from "tailwindcss";

const config: Config = {
  content: {
    relative: true,
    files: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  },
  theme: {
    extend: {},
  },
  plugins: [],
};

export default config;
