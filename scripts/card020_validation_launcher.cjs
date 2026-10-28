"use strict";

const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { loadEnvConfig } = require("@next/env");

const PROJECT_ROOT = path.resolve(__dirname, "..");
const PYTHON = path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe");
const NEXT_CLI = path.join(PROJECT_ROOT, "node_modules", "next", "dist", "bin", "next");
const API_PORT = 8010;
const FRONTEND_PORT = 3000;
const API_URL = `http://127.0.0.1:${API_PORT}`;
const PAGE_URL = `http://127.0.0.1:${FRONTEND_PORT}/strategy-validations?symbol=510880.SH`;
const ISOLATED_RESEARCH_DB = String.raw`D:\TraderLens_validation\card020-20261027\research.db`;

const children = [];
let stopping = false;

function configureValidationEnvironment(env) {
  env.RESEARCH_CONVERSATION_MODE = "real";
  env.SERENITY_EXECUTION_MODE = "two_phase";
  env.BACKEND_PORT = String(API_PORT);
  env.NEXT_PUBLIC_API_BASE_URL = API_URL;
  env.CARD020_NEXT_DIST_DIR = ".next-card020-20261027";
  return env;
}

function loadProjectEnvironment() {
  let parseFailed = false;
  loadEnvConfig(PROJECT_ROOT, true, {
    info() {},
    warn() {},
    error() { parseFailed = true; },
  });
  if (parseFailed) {
    throw new Error("项目环境配置无法解析；配置值已隐藏，未启动服务。");
  }
}

function assertRequiredRealConfiguration(env) {
  const missing = ["RESEARCH_LLM_API_KEY", "TUSHARE_TOKEN"].filter((name) => !env[name]);
  if (missing.length) {
    throw new Error(`真实研究配置缺少 ${missing.join("、")}；没有显示任何配置值。`);
  }
}

function assertPortFree(port) {
  return new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.once("error", (error) => {
      if (error.code === "EADDRINUSE") {
        reject(new Error(`端口 ${port} 已被占用；启动器不会停止或修改其他进程。`));
      } else {
        reject(new Error(`无法检查端口 ${port}（${error.code || "未知错误"}）。`));
      }
    });
    probe.listen(port, "127.0.0.1", () => probe.close(resolve));
  });
}

function startChild(executable, args, label) {
  const child = spawn(executable, args, {
    cwd: PROJECT_ROOT,
    env: process.env,
    stdio: "inherit",
    windowsHide: false,
  });
  child.label = label;
  child.spawnError = null;
  child.once("error", (error) => { child.spawnError = error; });
  children.push(child);
  return child;
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitForHttp(url, child, label, validate = () => true) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (child.spawnError) {
      throw new Error(`${label} 无法启动（${child.spawnError.code || "启动错误"}）。`);
    }
    if (child.exitCode !== null) {
      throw new Error(`${label} 在就绪前退出，退出码 ${child.exitCode}。`);
    }
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1500) });
      if (response.ok && await validate(response)) return;
    } catch {
      // The service may still be starting; do not print response bodies or env values.
    }
    await delay(1000);
  }
  throw new Error(`${label} 未在 60 秒内就绪；请查看本窗口和服务窗口的错误信息。`);
}

function requestStop() {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (child.exitCode === null && !child.killed) child.kill();
  }
}

function waitUntilChildExits() {
  return Promise.race(children.map((child) => new Promise((resolve) => {
    if (child.exitCode !== null) return resolve(child);
    child.once("exit", () => resolve(child));
  })));
}

async function main() {
  loadProjectEnvironment();
  configureValidationEnvironment(process.env);
  assertRequiredRealConfiguration(process.env);
  if (!fs.existsSync(PYTHON) || !fs.existsSync(NEXT_CLI)) {
    throw new Error("缺少项目 .venv Python 或本地 Next.js；没有启动服务。");
  }
  await assertPortFree(API_PORT);
  await assertPortFree(FRONTEND_PORT);

  process.on("SIGINT", requestStop);
  process.on("SIGTERM", requestStop);

  const api = startChild(PYTHON, [
    "-m", "uvicorn", "scripts.card020_validation_app:app",
    "--host", "127.0.0.1", "--port", String(API_PORT),
    "--log-level", "warning", "--no-access-log",
  ], "API");
  await waitForHttp(`${API_URL}/health`, api, "隔离 API", async (response) => {
    const health = await response.json();
    return health.status === "ok"
      && health.conversation_mode === "real"
      && health.live_trade_database === "isolated_guarded"
      && health.research_database === ISOLATED_RESEARCH_DB;
  });

  const frontend = startChild(process.execPath, [
    NEXT_CLI, "dev", "frontend", "--hostname", "127.0.0.1", "--port", String(FRONTEND_PORT),
  ], "Frontend");
  await waitForHttp(PAGE_URL, frontend, "原始前端页面");

  console.log(`卡020隔离验证页已就绪：${PAGE_URL}`);
  console.log(`研究记录保存在隔离库：${ISOLATED_RESEARCH_DB}`);
  console.log("正式交易账本路径受守卫限制；按 Ctrl+C 可停止本启动器启动的服务。");

  const exited = await waitUntilChildExits();
  if (!stopping) {
    console.error(`${exited.label} 已退出（退出码 ${exited.exitCode}）；正在停止本启动器启动的另一服务。`);
    requestStop();
  }
}

if (require.main === module) {
  main().catch((error) => {
    console.error(`卡020启动失败：${error.message}`);
    requestStop();
    process.exitCode = 1;
  });
}

module.exports = { configureValidationEnvironment, assertRequiredRealConfiguration };
