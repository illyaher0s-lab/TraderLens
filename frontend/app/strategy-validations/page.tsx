/**
 * Strategy Validations - Shell Page
 * 
 * P3-9: Shell page for strategy validation cases (currently empty)
 * - Display empty state (no validation cases yet)
 * - Explain validation process
 * - Link to related pages
 */

"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import TopNav from "@/components/TopNav";
import StrategyValidationStatusCard, {
  StrategyValidationStatus,
} from "@/components/StrategyValidationStatusCard";
import {
  CARD020_REVIEW_SECTIONS,
  canFreezeCard020,
  formatCard020ModelValue,
  validateCard020ParseForReview,
  validateCard020PreflightForFreeze,
} from "@/lib/card020-review";
import { buildCard020OutcomeSummary, formatCard020RunStatus } from "@/lib/card020-results";

interface Card017Metric {
  net_gain_actual_cny: string;
  net_gain_5000_equiv_cny: string;
  estimated_exit_cost_actual_cny: string;
  estimated_exit_cost_5000_equiv_cny: string;
  max_drawdown_amount_protocol_cny: string;
  max_drawdown_ratio: string;
  max_drawdown_ratio_percent: string;
  commission_actual_cny: string;
  commission_5000_equiv_cny: string;
  slippage_cost_actual_cny: string;
  slippage_cost_5000_equiv_cny: string;
  average_exposure_ratio: string;
  average_exposure_percent: string;
}

interface Card017Comparison {
  window: string;
  start_date: string;
  end_date: string;
  cost_scenario: string;
  candidate: Card017Metric;
  buy_and_hold: Card017Metric;
  comparison: {
    delta_wealth_cny: string;
    delta_drawdown_cny: string;
    classification: string;
  };
}

interface Card017Artifact {
  artifact_id: string;
  label: string;
  url: string;
}

interface Card017HistoricalResult {
  case_id: string;
  symbol: string;
  strategy_name: string;
  benchmark_name: string;
  period_start_date: string;
  period_end_date: string;
  starting_capital_cny: string;
  commission_basis: string;
  run_status: string;
  reconciliation_status: string;
  protocol_version: string;
  protocol_sha256: string;
  result_sha256: string;
  historical_execution_code_sha256: string;
  program_classification: string;
  original_report_conclusion: string;
  report_generated_at_utc: string;
  arden_recommendation: {
    advisor: string;
    value: string;
    source: string;
    is_illya_formal_decision: boolean;
  };
  acceptance_status: string;
  formal_qualification: string;
  evidence_level: string;
  actionable: boolean;
  market_status: string;
  dividend_raw_status: string;
  research_assumptions: string[];
  metric_semantics: Record<string, string>;
  comparisons: Card017Comparison[];
  provenance: {
    generated_at_utc: string;
    historical_execution_code_sha256: string;
    outputs: Array<{ artifact_id: string; filename: string; sha256: string; rows: number | null }>;
  };
  artifacts: Card017Artifact[];
}

interface HistoricalResultsResponse {
  status: "available" | "unavailable";
  items: Card017HistoricalResult[];
  message?: string;
}

interface ValidationResponse {
  validations: unknown[];
  count: number;
  validation_status: StrategyValidationStatus;
  historical_results: HistoricalResultsResponse;
}

interface Card020Protocol {
  strategy_id: string;
  protocol_revision: number;
  protocol_sha256: string;
  source_text: string;
  confirmation_statement: string;
}

interface Card020Record {
  [key: string]: unknown;
  run_id?: string;
  parse_id?: string;
  preflight_id?: string;
  freeze_id?: string;
  protocol_sha256?: string;
  source_sha256?: string;
  status?: string;
  result?: Card020ParseResult | Card020RunResult | null;
  created_at?: string;
}

interface Card020ParseResult {
  status?: string;
  fields?: Record<string, unknown>;
  source_mappings?: unknown[];
  line_coverage?: Array<{ line_number: number; classification: string }>;
  deterministic_format_lines?: number[];
  blocking_fields?: string[];
  blocking_reasons?: string[];
  source_sha256?: string;
  model?: string | null;
  parser_sha256?: string;
  call_diagnostic?: {
    attempt_count: number;
    retry_count: number;
    duration_ms: number | null;
    http_status: number | null;
    timeout: boolean;
    response_received: boolean;
    retry_stop_reason: string | null;
    attempts: Array<{
      attempt: number;
      status: "timeout" | "error" | "success";
      duration_ms: number | null;
      http_status: number | null;
      timeout: boolean;
      response_received: boolean;
    }>;
  };
}

interface Card020SourceMapping {
  field?: unknown;
  value?: unknown;
  source_line_numbers?: unknown;
  source_quotes?: unknown;
}

interface Card020Metric {
  start_nav_actual_cny: string;
  end_nav_actual_cny: string;
  evaluation_end_nav_cny: string;
  net_gain_actual_cny: string;
  return_ratio: string | null;
  annualized_return: string | null;
  realized_volatility: string | null;
  max_drawdown_amount_evaluation_cny: string;
  max_drawdown_ratio: string;
  average_exposure_ratio: string;
  average_cash_ratio: string;
  decision_values: Record<string, string>;
  [key: string]: unknown;
}

interface Card020DailyRow {
  date: string;
  cash_cny: string;
  quantity: number;
  raw_close_cny: string;
  dividend_receivable_cny: string;
  book_nav_cny: string;
}

interface Card020DividendEvent {
  event_id: string;
  record_date: string;
  ex_date: string;
  pay_date: string;
  div_cash_cny_per_share: string;
  source_refs: string[];
  entitled_quantity: number;
  entitlement_amount_cny: string;
  paid_amount_cny: string;
  paid_date: string | null;
  receivable_at_window_end_cny?: string;
}

interface Card020WindowActivity {
  window_start: string;
  window_end: string;
  trade_count: number;
  commission_total_cny: string;
  slippage_cost_total_cny: string;
  dividend_entitlement_total_cny: string;
  dividend_paid_total_cny: string;
  dividend_receivable_end_cny: string;
  dividend_events: Card020DividendEvent[];
  signal_volatility_observations: Array<{
    signal_date: string;
    window_start: string | null;
    window_end: string | null;
    signal_volatility: string | null;
    target_weight: string | null;
    target_shares: number;
  }>;
}

interface Card020Path {
  path_id: string;
  account_type: string;
  cost_scenario: string;
  trade_count: number;
  dynamic_risk_fill_count: number;
  commission_total_cny: string;
  slippage_cost_total_cny: string;
  ending_nav_cny: string;
  metrics: Record<string, Card020Metric>;
  trades: Array<Record<string, unknown>>;
  attempts: Array<Record<string, unknown>>;
  decisions: Array<Record<string, unknown>>;
  daily_snapshots: Card020DailyRow[];
  dividend_summary: {
    entitlement_total_cny: string;
    paid_total_cny: string;
    ending_receivable_cny: string;
    events: Card020DividendEvent[];
  };
  window_activity: Record<string, Card020WindowActivity>;
}

interface Card020RunResult {
  run_id?: string;
  strategy_id: string;
  period_start_date: string;
  period_end_date: string;
  starting_capital_cny: string;
  protocol_sha256: string;
  freeze_id: string;
  freeze_sha256: string;
  result_sha256: string;
  execution_bundle_sha256: string;
  run_status: string;
  evaluation_status: string;
  evaluation_category: string;
  evidence_level: string;
  category_reasons: string[];
  acceptance_status: string;
  formal_trade_qualification: boolean;
  historical_reuse: boolean;
  reconciliation_status: string;
  path_ids: string[];
  paths: Record<string, Card020Path>;
  data_provenance: Record<string, unknown>;
  reconciliation: Record<string, Record<string, unknown>>;
  not_out_of_sample: boolean;
}

interface Card020State {
  latest_parse: Card020Record | null;
  latest_preflight: Card020Record | null;
  frozen: Card020Record | null;
  runs: Card020Record[];
}

interface Card020Preflight extends Card020Record {
  status: string;
  protocol_sha256?: string;
  input_inventory_sha256?: string;
  input_inventory?: {
    market?: Record<string, unknown>;
    dividends?: Record<string, unknown>;
  };
  execution_fingerprint?: {
    executor_version?: string;
    bundle_sha256?: string;
    files?: Record<string, string>;
  };
  critical_source_gaps?: string[];
  data_limitations?: string[];
  evidence_level?: string;
  historical_metrics_computed?: boolean;
}

export default function StrategyValidationsPage() {
  const [data, setData] = useState<ValidationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [show510880EntryJudgement, setShow510880EntryJudgement] = useState(false);

  const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";

  useEffect(() => {
    setShow510880EntryJudgement(
      new URLSearchParams(window.location.search).get("symbol") === "510880.SH",
    );
    loadValidations();
  }, []);

  const loadValidations = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const url = `${API_BASE_URL}/api/strategy-validations`;
      const response = await fetch(url);
      
      if (!response.ok) {
        throw new Error(`Failed to load validations: HTTP ${response.status}`);
      }
      
      const responseData = await response.json();
      setData(responseData);
    } catch (err) {
      console.error("Failed to load validations:", err);
      setError(
        err instanceof Error 
          ? err.message 
          : "Unknown error"
      );
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <>
        <TopNav />
        <main style={styles.container}>
          {show510880EntryJudgement && <EntryJudgement loading />}
          <Card020Workflow apiBaseUrl={API_BASE_URL} />
          <div style={styles.loadingText}>加载中...</div>
        </main>
      </>
    );
  }

  if (error) {
    return (
      <>
        <TopNav />
        <main style={styles.container}>
          {show510880EntryJudgement && <EntryJudgement error />}
          <Card020Workflow apiBaseUrl={API_BASE_URL} />
          <div style={styles.errorText}>加载失败: {error}</div>
        </main>
      </>
    );
  }

  return (
    <>
    <TopNav />
    <main style={styles.container}>
      {/* Header */}
      <header style={styles.header}>
        <div>
          <h1 style={styles.title}>策略验证</h1>
          <p style={styles.subtitle}>
            模板资格验证案例与历史研究结果分区展示
          </p>
        </div>
        <div style={styles.headerActions}>
          <Link href="/strategies" style={styles.headerLink}>
            ← 返回策略工作区
          </Link>
        </div>
      </header>

      {show510880EntryJudgement && (
        <EntryJudgement
          status={data?.validation_status}
        />
      )}

      <Card020Workflow apiBaseUrl={API_BASE_URL} />

      <section className="mb-8" aria-label="历史研究结果">
        <h2 className="mb-2 text-xl font-semibold text-slate-900">历史研究结果（与资格验证分开）</h2>
        {data?.historical_results.status === "available" &&
          data.historical_results.items.map((item) => (
            <Card017History key={item.case_id} item={item} apiBaseUrl={API_BASE_URL} />
          ))}
        {data?.historical_results.status === "unavailable" && (
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
            {data.historical_results.message || "历史研究结果的来源暂不可验证，当前不展示数据。"}
          </div>
        )}
      </section>

      {data && (
        <section aria-label="现有资格验证状态">
          <h2 className="mb-2 text-sm font-semibold text-slate-700">现有资格验证状态</h2>
          <StrategyValidationStatusCard status={data.validation_status} />
        </section>
      )}

      {/* Empty State */}
      {data?.count === 0 && <div style={styles.emptyState}>
        <div style={styles.emptyIcon}>🔬</div>
        <h2 style={styles.emptyTitle}>当前没有已批准模板映射后的资格验证案例</h2>
        <p style={styles.emptyText}>
          验证案例数量: <strong>{data?.count || 0}</strong>
        </p>
        <p style={styles.emptyText}>
          这里的数量只统计资格验证案例；下方历史研究结果单独展示，不代表已获资格。
        </p>
        
        <div style={styles.infoBox}>
          <h3 style={styles.infoTitle}>什么是策略验证？</h3>
          <ul style={styles.infoList}>
            <li>只有通过已批准模板匹配的策略想法才会进入验证流程</li>
            <li>验证包括：回测验证、成本计算、风控检查、生存约束检查</li>
            <li>通过全部验证门的策略才能进入已批准策略库</li>
            <li>候选策略需要先获得模板批准才能进入验证</li>
          </ul>
        </div>

        <div style={styles.warningBox}>
          ℹ️ 当前没有策略通过模板匹配进入资格验证阶段
        </div>
      </div>}

      {/* Navigation Links */}
      <section style={styles.linksSection}>
        <h3 style={styles.linksTitle}>相关页面</h3>
        <div style={styles.linksGrid}>
          <Link href="/candidate-strategies" style={styles.linkCard}>
            <div style={styles.linkIcon}>🔍</div>
            <div style={styles.linkContent}>
              <div style={styles.linkLabel}>候选策略</div>
              <div style={styles.linkDesc}>等待模板批准的策略</div>
            </div>
          </Link>

          <Link href="/strategy-templates" style={styles.linkCard}>
            <div style={styles.linkIcon}>📐</div>
            <div style={styles.linkContent}>
              <div style={styles.linkLabel}>策略模板</div>
              <div style={styles.linkDesc}>已批准的策略模板库</div>
            </div>
          </Link>

          <Link href="/strategy-ideas" style={styles.linkCard}>
            <div style={styles.linkIcon}>💡</div>
            <div style={styles.linkContent}>
              <div style={styles.linkLabel}>策略想法</div>
              <div style={styles.linkDesc}>所有提交的策略想法</div>
            </div>
          </Link>
        </div>
      </section>
    </main>
    </>
  );
}

async function card020Request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body?.detail;
    const message = typeof detail === "string"
      ? detail
      : typeof detail?.message === "string"
        ? detail.message
        : `请求失败（HTTP ${response.status}）`;
    const error = new Error(message) as Error & { detail?: unknown };
    error.detail = detail;
    throw error;
  }
  return body as T;
}

async function card020SourceMatches(record: Card020Record | null, sourceText: string): Promise<boolean> {
  const result = record?.result && "source_sha256" in record.result
    ? record.result as Card020ParseResult
    : null;
  if (!result?.source_sha256 || !globalThis.crypto?.subtle) return false;
  const bytes = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(sourceText));
  const digest = Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, "0")).join("").toUpperCase();
  return digest === result.source_sha256.toUpperCase();
}

function formatCard020Percent(value: string | null | undefined): string {
  if (value == null || value === "") return "不可计算";
  const number = Number(value);
  return Number.isFinite(number) ? `${(number * 100).toFixed(2)}%` : "不可计算";
}

function formatCard020RawValue(value: unknown): string {
  if (value === null || value === undefined) return "未返回字段值";
  if (typeof value === "string") return value || "空值";
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return "无法显示的返回值";
  }
}

function card020DisplayList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(formatCard020RawValue) : [];
}

function Card020Workflow({ apiBaseUrl }: { apiBaseUrl: string }) {
  const root = `${apiBaseUrl.replace(/\/$/, "")}/api/research/card020`;
  const [protocol, setProtocol] = useState<Card020Protocol | null>(null);
  const [sourceText, setSourceText] = useState("");
  const sourceTextRef = useRef("");
  const [parseRecord, setParseRecord] = useState<Card020Record | null>(null);
  const [parseSourceVerified, setParseSourceVerified] = useState(false);
  const [preflight, setPreflight] = useState<Card020Preflight | null>(null);
  const [frozen, setFrozen] = useState<Card020Record | null>(null);
  const [runRecord, setRunRecord] = useState<Card020Record | null>(null);
  const [runResult, setRunResult] = useState<Card020RunResult | null>(null);
  const [confirmationChecked, setConfirmationChecked] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<string | null>(null);

  const restoreState = async (expectedSourceText = sourceTextRef.current) => {
    const state = await card020Request<Card020State>(`${root}/state`);
    const matchesSubmittedText = sourceTextRef.current === expectedSourceText
      && await card020SourceMatches(state.latest_parse, expectedSourceText);
    setParseRecord(matchesSubmittedText ? state.latest_parse : null);
    setParseSourceVerified(matchesSubmittedText);
    setPreflight(state.latest_preflight as Card020Preflight | null);
    setFrozen(state.frozen);
    const latestRun = state.runs?.[0];
    if (latestRun?.run_id) {
      const saved = await card020Request<Card020Record>(`${root}/runs/${latestRun.run_id}`);
      setRunRecord(saved);
      if (saved.result && "evaluation_category" in saved.result) {
        setRunResult(saved.result as Card020RunResult);
      }
    }
  };

  useEffect(() => {
    let active = true;
    Promise.all([
      card020Request<Card020Protocol>(`${root}/protocol`),
      card020Request<Card020State>(`${root}/state`),
    ]).then(async ([loadedProtocol, state]) => {
      if (!active) return;
      setProtocol(loadedProtocol);
      sourceTextRef.current = loadedProtocol.source_text;
      setSourceText(loadedProtocol.source_text);
      const matchesProtocol = sourceTextRef.current === loadedProtocol.source_text
        && await card020SourceMatches(state.latest_parse, loadedProtocol.source_text);
      setParseRecord(matchesProtocol ? state.latest_parse : null);
      setParseSourceVerified(matchesProtocol);
      setPreflight(state.latest_preflight as Card020Preflight | null);
      setFrozen(state.frozen);
      const latestRun = state.runs?.[0];
      if (latestRun?.run_id) {
        const saved = await card020Request<Card020Record>(`${root}/runs/${latestRun.run_id}`);
        if (!active) return;
        setRunRecord(saved);
        if (saved.result && "evaluation_category" in saved.result) {
          setRunResult(saved.result as Card020RunResult);
        }
      }
    }).catch((caught: unknown) => {
      if (active) setError(caught instanceof Error ? caught.message : "Card020 页面资料载入失败。");
    });
    return () => { active = false; };
  }, [root]);

  const post = async <T,>(endpoint: string, payload?: unknown): Promise<T> => card020Request<T>(
    `${root}/${endpoint}`,
    {
      method: "POST",
      headers: payload === undefined ? undefined : { "Content-Type": "application/json" },
      body: payload === undefined ? undefined : JSON.stringify(payload),
    },
  );

  const handleParse = async () => {
    setBusy("parse"); setError(null);
    setParseRecord(null);
    setParseSourceVerified(false);
    setPreflight(null);
    setConfirmationChecked(false);
    const submittedText = sourceTextRef.current;
    try {
      const saved = await post<Card020Record>("parse", { source_text: submittedText });
      if (submittedText !== sourceTextRef.current) return;
      setParseRecord(saved);
      const savedSourceMatches = await card020SourceMatches(saved, submittedText);
      setParseSourceVerified(savedSourceMatches);
      setConfirmationChecked(false);
      if (!savedSourceMatches) {
        setError("保存的解析原文哈希与当前固定策略原文不一致，已阻断冻结。");
      } else if (saved.status === "ready_for_confirmation") {
        const checked = await post<Card020Preflight>("preflight");
        setPreflight(checked);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "策略解析失败。");
      const detail = caught instanceof Error
        ? (caught as Error & { detail?: unknown }).detail
        : null;
      const parseId = detail && typeof detail === "object" && !Array.isArray(detail) && "parse_id" in detail
        ? detail.parse_id
        : null;
      if (typeof parseId === "string" && sourceTextRef.current === submittedText) {
        try {
          const savedFailure = await card020Request<Card020Record>(`${root}/parses/${encodeURIComponent(parseId)}`);
          if (savedFailure.status === "provider_error"
            && sourceTextRef.current === submittedText
            && await card020SourceMatches(savedFailure, submittedText)) {
            setParseRecord(savedFailure);
            setParseSourceVerified(true);
          }
        } catch {
          // Keep the original request error visible when the saved record cannot be loaded.
        }
      }
      setPreflight(null);
      if (parseRecord === null) setParseSourceVerified(false);
      setConfirmationChecked(false);
    } finally { setBusy(""); }
  };

  const handleFreeze = async () => {
    const parseId = parseRecord?.parse_id;
    if (!parseId || !preflight?.preflight_id || !canFreeze) {
      setError("解析、来源、预检或本人确认未全部通过，不能冻结。");
      return;
    }
    setBusy("freeze"); setError(null);
    try {
      const saved = await post<Card020Record>("freeze", {
        parse_id: parseId,
        preflight_id: preflight.preflight_id,
        source_sha256: parseResult?.source_sha256,
        confirmed: confirmationChecked,
      });
      setFrozen(saved);
      setConfirmationChecked(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "策略冻结失败。");
    } finally { setBusy(""); }
  };

  const handleRun = async () => {
    if (!frozen?.freeze_id) return;
    setBusy("run"); setError(null);
    try {
      const keyName = `card020-idempotency-${frozen.freeze_id}`;
      let key = sessionStorage.getItem(keyName);
      if (!key) {
        key = `card020-${window.crypto.randomUUID()}`;
        sessionStorage.setItem(keyName, key);
      }
      const saved = await post<Card020Record>("run", {
        freeze_id: frozen.freeze_id,
        idempotency_key: key,
      });
      setRunRecord(saved);
      if (saved.result && "evaluation_category" in saved.result) {
        setRunResult(saved.result as Card020RunResult);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "六路径历史核验失败。");
      await restoreState().catch(() => undefined);
    } finally { setBusy(""); }
  };

  const parseResult = parseRecord?.result && typeof parseRecord.result === "object"
    && !Array.isArray(parseRecord.result) && !("evaluation_category" in parseRecord.result)
    ? parseRecord.result as Card020ParseResult
    : null;
  const parseReview = validateCard020ParseForReview({
    record: parseRecord,
    sourceText,
    protocolSha256: protocol?.protocol_sha256 || "",
    sourceHashVerified: parseSourceVerified,
  });
  const preflightReview = validateCard020PreflightForFreeze({
    preflight,
    protocolSha256: protocol?.protocol_sha256 || "",
    parserSha256: parseResult?.parser_sha256,
  });
  const parseReady = parseReview.ready;
  const preflightReady = preflightReview.ready;
  const canFreeze = canFreezeCard020({
    parseReady,
    preflightReady,
    confirmationChecked,
    busy: busy !== "",
    frozen: Boolean(frozen?.freeze_id),
  });
  const reviewFieldKeys = new Set(CARD020_REVIEW_SECTIONS.flatMap((section) => section.fields.map((field) => field.key)));
  const rawSourceMappings = Array.isArray(parseResult?.source_mappings) ? parseResult.source_mappings : [];
  const sourceMappings = rawSourceMappings.filter((mapping): mapping is Card020SourceMapping =>
    typeof mapping === "object" && mapping !== null && !Array.isArray(mapping));
  const fields = parseResult?.fields && typeof parseResult.fields === "object" && !Array.isArray(parseResult.fields)
    ? parseResult.fields
    : {};
  const unknownFields = Object.entries(fields).filter(([key]) => !reviewFieldKeys.has(key));
  const unknownMappings = rawSourceMappings.filter((mapping) => {
    if (typeof mapping !== "object" || mapping === null || Array.isArray(mapping)) return true;
    const field = (mapping as Card020SourceMapping).field;
    return typeof field !== "string" || !reviewFieldKeys.has(field);
  });
  const dataLimitations = card020DisplayList(preflight?.data_limitations);
  const criticalSourceGaps = card020DisplayList(preflight?.critical_source_gaps);
  const rawFormatLines = Array.isArray(parseResult?.deterministic_format_lines)
    ? parseResult.deterministic_format_lines
    : [];
  const formatLines = rawFormatLines.filter((line): line is number => Number.isInteger(line));
  const reviewFieldsByKey = new Map(CARD020_REVIEW_SECTIONS.flatMap((section) => section.fields.map((field) => [field.key, field] as const)));
  const marketInventory = preflight?.input_inventory?.market;
  const dividendInventory = preflight?.input_inventory?.dividends;
  const dividendSpotChecks = Array.isArray(dividendInventory?.official_spotcheck_dates)
    ? dividendInventory.official_spotcheck_dates.map(String).join("、")
    : "未提供";

  return (
    <section aria-label="卡020固定510880波动预算研究流程" className="mb-8 rounded-xl border border-slate-300 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 pb-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-950">卡020｜510880 低频波动预算研究</h2>
          <p className="mt-1 text-sm text-slate-600">固定修订3 · {protocol?.strategy_id || "固定策略载入中"} · 仅研究结果，不代表策略资格或交易信号</p>
        </div>
        <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800">未获正式交易资格</span>
      </div>

      {error && <div role="alert" className="mt-4 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</div>}

      <div className="mt-4 grid gap-5 xl:grid-cols-2">
        <div>
          <label htmlFor="card020-source" className="block text-sm font-semibold text-slate-800">固定协议原文</label>
          <p className="mt-1 text-sm leading-5 text-slate-700">固定规则概览（不是本次模型解析结果）：510880.SH；本金 5,000 元；最近 60 个交易日估计波动，目标 10%；每月末调仓；比较基础与压力两种成本；研究区间 2018–2020，属于重复使用的历史样本。</p>
          <textarea
            id="card020-source"
            value={sourceText}
            disabled={busy !== "" || Boolean(frozen?.freeze_id)}
            rows={14}
            className="mt-2 w-full rounded-lg border border-slate-300 p-3 font-mono text-xs leading-5 text-slate-800 disabled:bg-slate-100"
            onChange={(event) => {
              sourceTextRef.current = event.target.value;
              setSourceText(event.target.value);
              setParseRecord(null);
              setParseSourceVerified(false);
              setPreflight(null);
              setConfirmationChecked(false);
            }}
          />
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <button type="button" onClick={handleParse} disabled={!protocol || busy !== "" || Boolean(frozen?.freeze_id)} className="rounded-md bg-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
              {busy === "parse" ? "真实模型解析并核验输入中…" : "真实模型解析并自动核验输入"}
            </button>
            {parseResult && <span className={`text-sm font-medium ${parseReady ? "text-green-800" : "text-amber-800"}`}>
              {parseReady ? `待本人确认 · ${parseResult.model || "模型名未返回"}` : parseResult.call_diagnostic?.timeout
                ? `模型调用超时 · ${parseResult.call_diagnostic.attempt_count} 次尝试 · ${parseResult.call_diagnostic.response_received ? "已收到响应" : "未收到响应"}`
                : "解析阻断，不能冻结"}
            </span>}
          </div>
        </div>

        <div className="space-y-4">
          <section className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <h3 className="font-semibold text-slate-900">历史输入核验</h3>
            <p className="mt-1 text-sm leading-5 text-slate-700">{preflight
              ? !preflightReady
                ? "预检发现实质输入问题，不能冻结或启动历史运行。请查看下方记录。"
                : "固定文件、适用区间覆盖与执行版本预检通过；此项预检不计算历史表现。该研究数据有明确限制，结果证据强度为低。"
              : parseReady ? "模型解析已通过，正在自动核验固定历史输入。" : "模型解析通过后自动核验，不计算策略表现。"}</p>
            <p className="mt-2 text-sm leading-5 text-slate-700">
              证据强度低；固定 2018–2020 区间曾用于此前研究，属于重复使用的历史样本，不是独立样本外结果。
            </p>
            {dataLimitations.length > 0 ? <ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-5 text-slate-600">
              {dataLimitations.map((limitation, index) => <li key={`${index}-${limitation}`}>{limitation}</li>)}
            </ul> : null}
            {criticalSourceGaps.length > 0 ? <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-red-800">
              {criticalSourceGaps.map((gap, index) => <li key={`${index}-${gap}`}>{gap}</li>)}
            </ul> : null}
            {preflight && <details data-card020-input-source-details="true" className="mt-3 rounded bg-white p-3 text-xs leading-5 text-slate-700">
              <summary className="cursor-pointer font-semibold">输入来源技术详情（可展开）</summary>
              <p className="mt-2 break-words">本次预检版本：行情快照 {String(marketInventory?.snapshot_id || "未提供")} · 分红快照 {String(dividendInventory?.snapshot_id || "未提供")} · 输入清单 SHA-256 {String(preflight.input_inventory_sha256 || "未提供")} · 执行器 {String(preflight.execution_fingerprint?.executor_version || "未提供")}。</p>
              <div className="mt-2 space-y-1">
                <p>行情来源原始状态：{String(marketInventory?.source_status || "未提供")}；适配器原始状态：{String(marketInventory?.adapter_validation_status || "未提供")}；提供方来源认证原始值：{String(marketInventory?.provider_origin_authenticated ?? "未提供")}。</p>
                <p>分红来源原始状态：{String(dividendInventory?.source_status || "未提供")}；官方抽查日期：{dividendSpotChecks}。</p>
                <p>分红覆盖记录原文：{String(dividendInventory?.coverage_record || "未提供")}。</p>
                <p>历史适配器说明原文：{String(dividendInventory?.historical_adapter_note || "未提供")}。</p>
              </div>
              <p className="mt-2 font-medium">完整输入来源记录与哈希：</p>
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all rounded bg-slate-50 p-2">{JSON.stringify(preflight.input_inventory, null, 2)}</pre>
            </details>}
            {!preflightReady && preflightReview.issues.length > 0 && <ul role="alert" className="mt-2 list-disc space-y-1 pl-5 text-sm text-red-800">
              {preflightReview.issues.map((issue) => <li key={issue}>{issue}</li>)}
            </ul>}
          </section>

          <section aria-label="卡020 AI 解析摘要" data-card020-review-summary="true" className="rounded-lg border border-blue-200 bg-blue-50/50 p-4">
            <h3 className="font-semibold text-slate-900">模型解析结果摘要</h3>
            <p className="mt-1 text-sm leading-5 text-slate-700">这里读取本次已保存的模型字段；摘要是依据实际返回值与固定修订3映射生成的中文释义，不是模型返回值。展开可查看 44 项实际返回值和逐条原文出处。缺项、未知值或不一致时不会补默认值，并会阻断冻结。</p>
            {parseRecord ? <p className={`mt-2 text-sm font-medium ${parseReady ? "text-green-800" : "text-red-800"}`}>
              {parseReady
                ? `已保存解析 · ${parseResult?.model || "模型名未返回"} · ${Object.keys(fields).length}/44 项字段核对通过`
                : `当前解析不能确认冻结 · ${Object.keys(fields).length}/44 项字段`}
            </p> : <p className="mt-2 text-sm text-slate-600">没有与当前固定原文哈希匹配的已保存解析。刷新页面只读取已保存记录，不会自动再次请求模型。</p>}
            {parseReview.issues.length > 0 && <ul role="alert" className="mt-2 list-disc space-y-1 pl-5 text-sm text-red-800">
              {parseReview.issues.map((issue) => <li key={issue}>{issue}</li>)}
              {parseReview.missingFields.length > 0 && <li>缺少字段：{parseReview.missingFields.map((key) => reviewFieldsByKey.get(key)?.label || key).join("、")}。</li>}
              {parseReview.unknownFields.length > 0 && <li>未识别字段：{parseReview.unknownFields.join("、")}。</li>}
            </ul>}
            {parseResult && <>
              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                {CARD020_REVIEW_SECTIONS.map((section) => (
                  <article key={section.title} className="rounded-md border border-blue-100 bg-white p-3">
                    <h4 className="text-sm font-semibold text-slate-900">{section.title}</h4>
                    <ul className="mt-2 space-y-2 text-sm leading-5 text-slate-700">
                      {section.fields.filter((field) => field.summary).map((field) => {
                        const reading = formatCard020ModelValue(field.key, fields[field.key]);
                        return <li key={field.key}>
                          <span className="font-medium">{field.label}：</span>
                          <span className={reading.known ? "" : "font-semibold text-red-800"}>{reading.text}</span>
                        </li>;
                      })}
                    </ul>
                  </article>
                ))}
              </div>
              {formatLines.length > 0 ? <p className="mt-3 rounded bg-slate-100 p-2 text-xs leading-5 text-slate-700">
                格式行透明标记：程序将原文第 {formatLines.join("、")} 行补记为 context；这是 Markdown 表格分隔格式，不是模型解析出的策略规则。
              </p> : null}
              <details data-card020-full-review="true" className="mt-3 rounded border border-slate-200 bg-white p-3">
                <summary className="cursor-pointer font-semibold text-slate-900">展开查看 44 项完整解析、实际返回值与逐条来源</summary>
                <p className="mt-2 text-xs leading-5 text-slate-600">以下“模型实际返回值”直接取自已保存解析记录；中文释义仅在原值与固定修订3逐字匹配时显示。缺失、额外或不匹配的值仍显示原样并阻断冻结。</p>
                <div className="mt-3 space-y-4">
                  {CARD020_REVIEW_SECTIONS.map((section) => (
                    <section key={section.title}>
                      <h4 className="font-semibold text-slate-900">{section.title}</h4>
                      <div className="mt-2 grid gap-2">
                        {section.fields.map((field) => {
                          const rawValue = fields[field.key];
                          const reading = formatCard020ModelValue(field.key, rawValue);
                          const mapping = sourceMappings.find((item) => item.field === field.key);
                          const mappingLines = Array.isArray(mapping?.source_line_numbers) ? mapping.source_line_numbers : [];
                          const mappingQuotes = Array.isArray(mapping?.source_quotes) ? mapping.source_quotes : [];
                          const citationsValid = mappingLines.length > 0
                            && mappingLines.length === mappingQuotes.length
                            && mappingLines.every((line, index) => Number.isInteger(line)
                              && typeof mappingQuotes[index] === "string" && mappingQuotes[index].trim() !== "");
                          return <article key={field.key} className="rounded border border-slate-200 p-3 text-sm">
                            <h5 className="font-semibold text-slate-900">{field.label}</h5>
                            <p className="mt-1 text-xs text-slate-600">字段：{field.key} · 中文说明：{field.explanation}</p>
                            <p className="mt-1 break-words"><span className="font-medium">模型实际返回值：</span>{formatCard020RawValue(rawValue)}</p>
                            <p className={`mt-1 ${reading.known ? "text-slate-700" : "font-semibold text-red-800"}`}><span className="font-medium">固定值中文释义：</span>{reading.text}</p>
                            {citationsValid ? mappingLines.map((line, index) => <p key={`${String(line)}-${index}`} className="mt-1 break-words border-l-2 border-blue-200 pl-2 text-xs leading-5 text-slate-600">
                              原文依据 · 第 {String(line)} 行：{String(mappingQuotes[index])}
                            </p>) : <p className="mt-1 text-xs font-semibold text-red-800">原文依据缺失或不完整，不能冻结。</p>}
                          </article>;
                        })}
                      </div>
                    </section>
                  ))}
                  {(unknownFields.length > 0 || unknownMappings.length > 0) && <section role="alert" className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-900">
                    <h4 className="font-semibold">未识别内容（已阻断冻结）</h4>
                    {unknownFields.map(([key, value]) => <p key={key}>字段 {key}：{formatCard020RawValue(value)}</p>)}
                    {unknownMappings.map((mapping, index) => <p key={`unknown-mapping-${index}`}>未识别映射：{formatCard020RawValue(mapping)}</p>)}
                  </section>}
                </div>
              </details>
            </>}
          </section>

          <section className="rounded-lg border border-slate-200 p-4">
            <h3 className="font-semibold text-slate-900">本人确认并冻结</h3>
            {frozen?.freeze_id ? (
              <div className="mt-2 space-y-1 text-sm text-slate-700">
                <p className="font-semibold text-green-800">已由页面确认并冻结；冻结记录不可编辑</p>
                <p>本人已在页面确认并冻结；确认时间：{String(frozen.confirmed_at || "未知")}</p>
              </div>
            ) : (
              <>
                <p className="mt-1 text-sm leading-5 text-slate-700">确认前先看上方中文摘要；需要时可展开核对全部原始返回值和引文。点击后冻结的是完整策略原文、这 44 项模型解析规则及其来源、预检锁定的输入清单和执行版本；这一步不会运行回测或产生真实成交，也不授予策略资格。</p>
                <label className="mt-3 flex items-start gap-2 text-sm leading-5 text-slate-800">
                  <input type="checkbox" checked={confirmationChecked} onChange={(event) => setConfirmationChecked(event.target.checked)} disabled={!parseReady || !preflightReady || busy !== ""} className="mt-1" />
                  <span>我确认冻结的是以上模型解析的完整策略和预检锁定的输入/执行版本；已了解数据限制。冻结仅保存研究规则，不代表策略合格、买入建议或交易信号。</span>
                </label>
                <button type="button" onClick={handleFreeze} disabled={!canFreeze || busy !== ""} className="mt-3 rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">
                  {busy === "freeze" ? "服务端复核并冻结中…" : "确认并冻结"}
                </button>
              </>
            )}
          </section>

          {(parseResult || preflight || frozen) && <details className="rounded-lg border border-slate-200 p-4">
            <summary className="cursor-pointer font-semibold text-slate-900">证据与技术记录（可展开）</summary>
            {preflight && <div className="mt-3 space-y-1 break-all text-xs text-slate-600">
              <p>协议 SHA-256：{String(preflight.protocol_sha256 || "")}</p>
              <p>输入清单 SHA-256：{preflight.input_inventory_sha256}</p>
              <p>执行版本：{preflight.execution_fingerprint?.executor_version} · {preflight.execution_fingerprint?.bundle_sha256}</p>
              <p>历史表现指标已计算：{String(preflight.historical_metrics_computed)}</p>
              <p>证据强度：{preflight.evidence_level || "低"}</p>
              {preflight.data_limitations && <pre className="max-h-64 overflow-auto whitespace-pre-wrap">{JSON.stringify(preflight.data_limitations, null, 2)}</pre>}
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap">{JSON.stringify(preflight.input_inventory, null, 2)}</pre>
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap">{JSON.stringify(preflight.execution_fingerprint?.files, null, 2)}</pre>
            </div>}
            {frozen && <p className="mt-2 break-all text-xs text-slate-600">冻结 SHA-256：{String(frozen.freeze_sha256 || "")} · 原文 SHA-256：{String(frozen.source_sha256 || "")}</p>}
          {parseResult && <details className="mt-3 rounded border border-slate-200 p-3">
            <summary className="cursor-pointer font-semibold text-slate-900">逐项解析来源（{rawSourceMappings.length} 项）与阻断原因</summary>
            <p className="mt-2 break-all text-xs text-slate-600">提交原文 SHA-256：{parseResult.source_sha256 || "未知"}</p>
            <p className="mt-1 break-all text-xs text-slate-600">解析模型：{parseResult.model || "未返回"} · 解析代码 SHA-256：{parseResult.parser_sha256 || "未知"}</p>
            {formatLines.length > 0 ? <p className="mt-1 text-xs text-slate-600">
              程序补记为 context 的 Markdown 表格分隔行（未由模型分类）：{formatLines.map((line) => `第 ${line} 行`).join("、")}。
            </p> : null}
            {Array.isArray(parseResult.blocking_reasons) && parseResult.blocking_reasons.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-900">{parseResult.blocking_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
            {parseResult.call_diagnostic && <section className="mt-3 rounded bg-amber-50 p-3 text-xs text-amber-950">
              <h4 className="font-semibold">模型调用诊断</h4>
              <p className="mt-1">
                {parseResult.call_diagnostic.timeout ? "调用超时" : "调用失败"} · 尝试 {parseResult.call_diagnostic.attempt_count} 次 · 重试 {parseResult.call_diagnostic.retry_count} 次 · {parseResult.call_diagnostic.response_received ? "已收到响应" : "未收到响应"}
                {parseResult.call_diagnostic.http_status !== null ? ` · HTTP ${parseResult.call_diagnostic.http_status}` : ""}
                {parseResult.call_diagnostic.duration_ms !== null ? ` · 总耗时约 ${Math.round(parseResult.call_diagnostic.duration_ms)} ms` : ""}
              </p>
              <p className="mt-1">停止原因：{parseResult.call_diagnostic.retry_stop_reason === "max_retries_reached"
                ? "达到 3 次尝试上限"
                : parseResult.call_diagnostic.retry_stop_reason || "未提供"}</p>
              {parseResult.call_diagnostic.attempts.length > 0 && <ul className="mt-1 list-disc pl-5">
                {parseResult.call_diagnostic.attempts.map((attempt) => <li key={attempt.attempt}>
                  第 {attempt.attempt} 次：{attempt.timeout ? "超时" : attempt.status === "success" ? "成功" : "失败"} · {attempt.duration_ms === null ? "耗时未提供" : `${Math.round(attempt.duration_ms)} ms`} · {attempt.response_received ? "已收到响应" : "未收到响应"}
                  {attempt.http_status !== null ? ` · HTTP ${attempt.http_status}` : ""}
                </li>)}
              </ul>}
            </section>}
          </details>}
          </details>}
        </div>
      </div>

      {frozen?.freeze_id && <section className="mt-5 rounded-lg border border-blue-200 bg-blue-50 p-4">
        <h3 className="font-semibold text-slate-900">六路径历史核验</h3>
        <p className="mt-1 text-sm leading-5 text-slate-700">固定 2018-01-02 至 2020-12-31。历史输入预检和版本哈希与冻结记录不一致时，服务端拒绝运行；同一冻结只允许一个不可覆盖批次。</p>
        <button type="button" onClick={handleRun} disabled={busy !== "" || Boolean(runRecord?.run_id)} className="mt-3 rounded-md bg-blue-800 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
          {busy === "run" ? "运行并独立核账中…" : "在页面运行固定六路径"}
        </button>
        {runRecord ? <p className="mt-2 text-sm">批次状态：{formatCard020RunStatus(runRecord.status)}{runRecord.status === "running" ? "（刷新后仍保留，不允许重跑）" : ""}</p> : null}
      </section>}

      {runResult && <Card020Results result={runResult} runRecord={runRecord} />}
    </section>
  );
}

function Card020Results({ result, runRecord }: { result: Card020RunResult; runRecord: Card020Record | null }) {
  const accountLabels: Record<string, string> = {
    candidate: "动态波动预算候选",
    buy_and_hold: "买入持有",
    static_half: "静态半仓",
  };
  const summary = buildCard020OutcomeSummary(runRecord);
  const candidateRows = summary.rows.filter((row) => row.pathId.startsWith("candidate-"));

  return (
    <section className="mt-5 border-t border-slate-200 pt-5" aria-label="卡020运行结果">
      <section aria-label="卡020模拟结果摘要" className="rounded-xl border border-slate-300 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-xl font-semibold text-slate-950">卡020历史模拟结论</h3>
            <p className="mt-1 text-sm leading-5 text-slate-700">
              {summary.periodText}{summary.pathScopeText}三个账户从 {summary.startingCapitalText} 开始；比较基础和压力两种单边滑点。
              这是固定历史模拟账面结果，不是本人实际成交或实际投资收益。
            </p>
          </div>
          <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-900">研究结果 · 不能作为交易指令</span>
        </div>

        {(!summary.ready || !summary.metricsTrusted) && <div role="alert" className="mt-3 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900">
          <p className="font-semibold">{summary.ready ? "关键数据或核账不可信，盈亏与风险指标不作可信结论；相关数值显示为“未知”。" : "批次结构或披露不完整，评价暂不可判定。"}</p>
          {summary.issues.length > 0 && <ul className="mt-1 list-disc space-y-1 pl-5">{summary.issues.map((issue) => <li key={issue}>{issue}</li>)}</ul>}
        </div>}

        <section className="mt-4 rounded-lg border border-blue-200 bg-blue-50/60 p-4">
          <h4 className="font-semibold text-slate-950">候选策略模拟盈亏</h4>
          <div className="mt-2 grid gap-3 md:grid-cols-2">
            {candidateRows.map((row) => (
              <article key={row.pathId} className="rounded-md border border-blue-100 bg-white p-3">
                <h5 className="text-sm font-semibold text-slate-900">{row.costLabel}</h5>
                <p className={"mt-1 text-lg font-semibold " + (row.pnlState === "profit" ? "text-green-800" : row.pnlState === "loss" ? "text-red-800" : "text-slate-800")}>
                  {row.pnlText}
                </p>
                <p className="mt-1 text-sm text-slate-700">起始净值 {row.startingNavText} · 期末净值 {row.endingNavText}</p>
                <p className="mt-1 text-sm text-slate-700">
                  最大回撤 {row.drawdownAmountText}（{row.drawdownRatioText}）· 佣金 {row.commissionText} · 滑点 {row.slippageText}
                </p>
              </article>
            ))}
          </div>
        </section>

        <section className="mt-4">
          <h4 className="font-semibold text-slate-950">三账户 × 两种成本：全期对照</h4>
          <p className="mt-1 text-xs leading-5 text-slate-600">固定协议规定基础单边滑点 0.05%、压力单边滑点 0.10%；佣金与滑点金额读取本次已保存批次。</p>
          <div className="mt-2 overflow-x-auto rounded-lg border border-slate-200">
            <table className="w-full min-w-[920px] text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-700">
                <tr>
                  <th className="p-2">账户 / 情景</th><th className="p-2">期末净值</th><th className="p-2">模拟盈亏 / 收益率</th>
                  <th className="p-2">最大回撤</th><th className="p-2">佣金</th><th className="p-2">滑点</th>
                </tr>
              </thead>
              <tbody>
                {summary.rows.map((row) => (
                  <tr key={row.pathId} className="border-t border-slate-200 align-top">
                    <th className="p-2 font-medium text-slate-800">{row.accountLabel}<span className="block text-xs font-normal text-slate-500">{row.costLabel}</span></th>
                    <td className="p-2">{row.endingNavText}</td>
                    <td className={"p-2 " + (row.pnlState === "profit" ? "text-green-800" : row.pnlState === "loss" ? "text-red-800" : "text-slate-700")}>{row.pnlText}</td>
                    <td className="p-2">{row.drawdownAmountText}（{row.drawdownRatioText}）</td>
                    <td className="p-2">{row.commissionText}</td>
                    <td className="p-2">{row.slippageText}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {summary.staticHalfTradeoffs.length > 0 && <section className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
          <h4 className="font-semibold text-slate-900">怎样理解静态半仓对照</h4>
          {summary.staticHalfTradeoffs.map((item) => <p key={item.costLabel} className="mt-1 text-sm leading-5 text-slate-700">{item.description}</p>)}
        </section>}

        <section className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-4">
          <h4 className="font-semibold text-amber-950">研究结论与使用边界</h4>
          <p className="mt-1 text-sm font-semibold text-amber-950">{summary.categoryLabel}</p>
          <p className="mt-1 text-sm leading-5 text-amber-900">{summary.categoryMessage}</p>
          <p className="mt-2 text-sm leading-5 text-slate-800">{summary.eligibilityText}</p>
          <p className="mt-1 text-sm leading-5 text-slate-700">{summary.evidenceText}</p>
          <p className="mt-1 text-sm leading-5 text-slate-700">
            {summary.historyText}即使显示 A 类，也只支持继续研究。
          </p>
          <div className="mt-3">
            <h5 className="text-sm font-semibold text-slate-900">数据来源与限制</h5>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm leading-5 text-slate-700">
              {summary.sourceSummary.map((item) => <li key={item}>{item}</li>)}
              {summary.criticalSourceGaps.map((item, index) => <li key={"gap-" + index}>{item}</li>)}
              {summary.limitations.map((item, index) => <li key={index}>{item}</li>)}
            </ul>
          </div>
        </section>
      </section>

      <details className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
        <summary className="cursor-pointer font-semibold text-slate-900">六路径完整明细（分段、分红、持仓与成交）</summary>
        <p className="mt-2 text-sm leading-5 text-slate-600">这里保留全期与 2018–2019、2020 分段数据、每日现金/持仓/净值、分红事件、目标调整、成交尝试和实际成交。</p>
        <div className="mt-3 grid gap-4 xl:grid-cols-2">
          {result.path_ids.map((pathId) => {
            const path = result.paths[pathId];
            if (!path) return null;
            return <Card020PathResult key={pathId} path={path} label={accountLabels[path.account_type] || "账户未知"} />;
          })}
        </div>
      </details>

      <details className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-4 text-xs text-slate-700">
        <summary className="cursor-pointer font-semibold text-slate-900">技术证据（协议、冻结、结果哈希、未舍入值与完整核账 JSON）</summary>
        <p className="mt-2 text-sm leading-5 text-slate-600">展开后可核对批次哈希、未舍入评价数值、输入来源限制、全部路径账本和独立核账记录。页面默认摘要不使用这些技术字段自行重判类别。</p>
        <div className="mt-3 grid gap-1 break-all text-xs text-slate-600">
          <p>批次编号：{typeof runRecord?.run_id === "string" && runRecord.run_id ? runRecord.run_id : "未知"}</p>
          <p>协议 SHA-256：{result.protocol_sha256}</p>
          <p>冻结 SHA-256：{result.freeze_sha256}</p>
          <p>结果 SHA-256：{result.result_sha256}</p>
          <p>执行包 SHA-256：{result.execution_bundle_sha256}</p>
        </div>
        <pre className="mt-3 max-h-[32rem] overflow-auto whitespace-pre-wrap break-all rounded bg-white p-3">{JSON.stringify(result, null, 2)}</pre>
      </details>
    </section>
  );
}

function Card020PathResult({ path, label }: { path: Card020Path; label: string }) {
  const windowLabels: Record<string, string> = { full: "全期", "2018-2019": "2018–2019", "2020": "2020（连续账户归一评价）" };
  return (
    <article className="rounded-lg border border-slate-200 p-4">
      <h4 className="font-semibold text-slate-900">{label} · {path.cost_scenario === "base" ? "基础 5bp" : "压力 10bp"}</h4>
      <p className="mt-1 text-xs text-slate-600">期末账面 NAV {path.ending_nav_cny} 元 · {path.trade_count} 笔成交 · 佣金 {path.commission_total_cny} 元 · 滑点 {path.slippage_cost_total_cny} 元</p>
      {path.account_type === "candidate" && <p className="mt-1 text-xs text-slate-600">后续月末目标实际调仓成交：{path.dynamic_risk_fill_count} 笔</p>}
      <p className="mt-1 text-xs text-slate-600">全期分红权益 {path.dividend_summary.entitlement_total_cny} 元 · 已到账 {path.dividend_summary.paid_total_cny} 元 · 期末应收 {path.dividend_summary.ending_receivable_cny} 元</p>
      <div className="mt-3 space-y-2">
        {Object.entries(path.metrics).map(([window, metric]) => {
          const activity = path.window_activity[window];
          return <section key={window} className="rounded bg-slate-50 p-3">
          <h5 className="text-sm font-semibold text-slate-800">{windowLabels[window] || window}</h5>
          <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-slate-700">
            <dt>段初实际 NAV</dt><dd>{metric.start_nav_actual_cny} 元</dd>
            <dt>期末账面 NAV</dt><dd>{metric.end_nav_actual_cny} 元</dd>
            <dt>评价终值</dt><dd>{metric.evaluation_end_nav_cny} 元</dd>
            <dt>实际净损益</dt><dd>{metric.net_gain_actual_cny} 元</dd>
            <dt>净收益率</dt><dd>{formatCard020Percent(metric.return_ratio)}</dd>
            <dt>年化收益（ACT/365）</dt><dd>{formatCard020Percent(metric.annualized_return)}</dd>
            <dt>账户实现波动</dt><dd>{formatCard020Percent(metric.realized_volatility)}</dd>
            <dt>最大回撤金额</dt><dd>{metric.max_drawdown_amount_evaluation_cny} 元</dd>
            <dt>最大回撤比例</dt><dd>{formatCard020Percent(metric.max_drawdown_ratio)}</dd>
            <dt>平均敞口／现金</dt><dd>{formatCard020Percent(metric.average_exposure_ratio)} / {formatCard020Percent(metric.average_cash_ratio)}</dd>
            <dt>本窗口成交／佣金</dt><dd>{activity?.trade_count ?? "—"} 笔 · {activity?.commission_total_cny ?? "—"} 元</dd>
            <dt>本窗口滑点成本</dt><dd>{activity?.slippage_cost_total_cny ?? "—"} 元</dd>
            <dt>分红权益／本窗口到账</dt><dd>{activity?.dividend_entitlement_total_cny ?? "—"} / {activity?.dividend_paid_total_cny ?? "—"} 元</dd>
            <dt>窗口期末分红应收</dt><dd>{activity?.dividend_receivable_end_cny ?? "—"} 元</dd>
          </dl>
          {activity?.signal_volatility_observations.length ? <details className="mt-2 rounded border border-blue-100 p-2 text-xs text-slate-700">
            <summary className="cursor-pointer font-semibold">60 日信号波动与目标（{activity.signal_volatility_observations.length} 次）</summary>
            <div className="mt-2 max-h-56 overflow-auto">
              <table className="w-full text-left"><thead><tr><th className="p-1">信号日</th><th className="p-1">60 日实现波动</th><th className="p-1">目标仓位</th><th className="p-1">目标份额</th></tr></thead>
                <tbody>{activity.signal_volatility_observations.map((item) => <tr key={item.signal_date} className="border-t border-slate-200">
                  <td className="p-1">{item.signal_date}</td><td className="p-1">{formatCard020Percent(item.signal_volatility)}</td><td className="p-1">{formatCard020Percent(item.target_weight)}</td><td className="p-1">{item.target_shares}</td>
                </tr>)}</tbody>
              </table>
            </div>
          </details> : null}
          {activity?.dividend_events.length ? <details className="mt-2 rounded border border-green-100 p-2 text-xs text-slate-700">
            <summary className="cursor-pointer font-semibold">窗口分红事件明细（{activity.dividend_events.length} 项）</summary>
            <div className="mt-2 max-h-56 overflow-auto">
              <table className="w-full whitespace-nowrap text-left"><thead><tr><th className="p-1">除息日</th><th className="p-1">每份分红</th><th className="p-1">权益份额</th><th className="p-1">权益金额</th><th className="p-1">截至窗口末到账</th><th className="p-1">窗口末应收</th></tr></thead>
                <tbody>{activity.dividend_events.map((event) => <tr key={event.event_id} className="border-t border-slate-200">
                  <td className="p-1">{event.ex_date}</td><td className="p-1">{event.div_cash_cny_per_share} 元</td><td className="p-1">{event.entitled_quantity}</td><td className="p-1">{event.entitlement_amount_cny} 元</td><td className="p-1">{event.paid_amount_cny} 元{event.paid_date ? `（${event.paid_date}）` : "（尚未到账）"}</td><td className="p-1">{event.receivable_at_window_end_cny || "0.00"} 元</td>
                </tr>)}</tbody>
              </table>
            </div>
          </details> : null}
          <details className="mt-2 text-xs text-slate-600">
            <summary className="cursor-pointer">未舍入评价数值与回撤日期</summary>
            <pre className="mt-1 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(metric, null, 2)}</pre>
          </details>
        </section>;
        })}
      </div>
      <Card020DailyLedger rows={path.daily_snapshots} />
      <details className="mt-2 text-xs text-slate-600">
        <summary className="cursor-pointer">调仓决策、成交尝试与逐笔成交</summary>
        <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify({ decisions: path.decisions, attempts: path.attempts, trades: path.trades }, null, 2)}</pre>
      </details>
    </article>
  );
}

function Card020DailyLedger({ rows }: { rows: Card020DailyRow[] }) {
  const [open, setOpen] = useState(false);
  return (
    <details className="mt-3 rounded bg-slate-50 p-3" onToggle={(event) => setOpen((event.currentTarget as HTMLDetailsElement).open)}>
      <summary className="cursor-pointer text-sm font-semibold text-slate-800">逐日账本（{rows.length} 个交易日）</summary>
      {open && <div className="mt-2 max-h-96 overflow-auto">
        <table className="w-full whitespace-nowrap text-left text-xs">
          <thead className="sticky top-0 bg-white"><tr><th className="p-2">日期</th><th className="p-2">现金</th><th className="p-2">持有份额</th><th className="p-2">原始收盘</th><th className="p-2">分红应收</th><th className="p-2">账面 NAV</th></tr></thead>
          <tbody>{rows.map((row) => <tr key={row.date} className="border-t border-slate-200">
            <td className="p-2">{row.date}</td><td className="p-2">{row.cash_cny}</td><td className="p-2">{row.quantity}</td><td className="p-2">{row.raw_close_cny}</td><td className="p-2">{row.dividend_receivable_cny}</td><td className="p-2">{row.book_nav_cny}</td>
          </tr>)}</tbody>
        </table>
      </div>}
    </details>
  );
}

function EntryJudgement({
  loading = false,
  error = false,
  status,
}: {
  loading?: boolean;
  error?: boolean;
  status?: StrategyValidationStatus;
}) {
  const reason = loading
    ? "资格核验尚未完成，验证资料仍在载入。"
    : error
      ? "资格资料不可核，验证接口暂不可用。"
      : status?.status === "watch"
        ? `现有验证阻断：${status.title}。${status.message}`
        : status?.status === "unavailable"
          ? `资格资料不可核。${status.message}`
          : "资格核验尚未完成，资料不可核。";

  return (
    <section aria-label="510880入场核验" className="mb-6 rounded-lg border border-amber-300 bg-amber-50 p-5">
      <h2 className="text-base font-semibold text-amber-950">510880 入场核验</h2>
      <p className="mt-2 text-sm font-semibold text-amber-950">
        当前未确认 510880 合格策略。
      </p>
      <p className="mt-1 text-sm leading-6 text-amber-900">{reason}</p>
      <p className="mt-1 text-sm text-amber-900">当前处理：观察／不交易。核验日期未知。</p>
      <p className="mt-2 text-sm leading-6 text-slate-700">本页未提供正式入场信号，研究结果不能替代资格核验。</p>
      <p className="mt-2 text-sm leading-6 text-slate-700">
        自主成交只登记已经发生的实际成交；记录本身不代表策略合格或交易许可。
      </p>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-sm">
        <Link href="/trades/record" className="font-medium text-blue-800 underline">登记自主成交</Link>
        <Link href="/observations" className="font-medium text-blue-800 underline">查看持仓与复盘</Link>
      </div>
    </section>
  );
}

function Card017History({
  item,
  apiBaseUrl,
}: {
  item: Card017HistoricalResult;
  apiBaseUrl: string;
}) {
  const apiRoot = apiBaseUrl.replace(/\/$/, "");
  const windowLabels: Record<string, string> = {
    full: "全期",
    "2018-2019": "2018–2019",
    "2020": "2020（非独立 OOS）",
  };

  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 pb-4">
        <div>
          <h3 className="text-lg font-semibold text-slate-900">
            {item.symbol}｜{item.strategy_name} 对比 {item.benchmark_name}
          </h3>
          <p className="mt-1 text-sm text-slate-600">
            {item.case_id} · {item.run_status} · 独立核账 {item.reconciliation_status} · 协议 {item.protocol_version}
          </p>
          <p className="mt-1 text-sm text-slate-600">
            初始本金 {item.starting_capital_cny} 元 · 评估区间 {item.period_start_date}—{item.period_end_date}
          </p>
        </div>
        <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800">
          仅研究参考 · 不可执行
        </span>
      </div>

      <dl className="mt-4 grid gap-3 md:grid-cols-2">
        <StatusLine label="历史程序分类" value={item.program_classification} />
        <StatusLine label="卡017原报告结论" value={item.original_report_conclusion} />
        <StatusLine
          label="Arden 独立顾问研究建议"
          value={`${item.arden_recommendation.advisor}：${item.arden_recommendation.value}。这不是 Illya 的正式采用决定，也不是 App 算法结论。`}
        />
        <StatusLine label="Illya 本人验收" value={item.acceptance_status} />
        <StatusLine label="正式策略资格" value={item.formal_qualification} />
      </dl>
      <p className="mt-3 text-sm text-slate-700">佣金口径：{item.commission_basis}</p>
      <p className="mt-3 text-xs leading-5 text-slate-500">
        原报告生成时间：{item.report_generated_at_utc}；Arden 建议来自本卡启动指令，两个结论按各自来源和时点保留。
      </p>

      <div className="mt-5 space-y-4">
        {item.comparisons.map((row) => (
          <section
            key={`${row.window}-${row.cost_scenario}`}
            className="rounded-lg border border-slate-200 p-4"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h4 className="font-semibold text-slate-900">
                {windowLabels[row.window] || row.window} · {row.start_date}—{row.end_date} · {row.cost_scenario}
              </h4>
              <span className="text-sm font-medium text-slate-700">
                {row.comparison.classification}
              </span>
            </div>
            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              <MetricPanel title="MA250 候选" metric={row.candidate} />
              <MetricPanel title="买入持有" metric={row.buy_and_hold} />
            </div>
            <p className="mt-3 text-sm text-slate-700">
              比较：ΔW {row.comparison.delta_wealth_cny} 元（候选退出后等值终值 − 基准）；
              ΔD {row.comparison.delta_drawdown_cny} 元（基准回撤 − 候选回撤）。
            </p>
          </section>
        ))}
      </div>

      <ul className="mt-4 list-disc space-y-1 pl-5 text-xs leading-5 text-slate-600">
        {item.research_assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}
        <li>行情来源状态：{item.market_status}；分红来源标签：{item.dividend_raw_status}。</li>
      </ul>

      <details className="mt-5 rounded-lg bg-slate-50 p-4 text-sm text-slate-700">
        <summary className="cursor-pointer font-semibold">协议、核账来源与模拟材料</summary>
        <dl className="mt-3 grid gap-2 sm:grid-cols-2">
          <StatusLine label="协议 SHA-256" value={item.protocol_sha256} />
          <StatusLine label="账单结果 SHA-256" value={item.result_sha256} />
          <StatusLine label="历史执行代码 SHA-256" value={item.historical_execution_code_sha256} />
          <StatusLine label="证据等级" value={item.evidence_level} />
        </dl>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2">
          {item.artifacts.map((artifact) => (
            <a
              key={artifact.artifact_id}
              href={`${apiRoot}${artifact.url}`}
              className="text-blue-700 underline"
            >
              {artifact.label}
            </a>
          ))}
        </div>
      </details>
    </article>
  );
}

function StatusLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-slate-500">{label}</dt>
      <dd className="mt-1 break-words text-sm text-slate-800">{value}</dd>
    </div>
  );
}

function MetricPanel({ title, metric }: { title: string; metric: Card017Metric }) {
  return (
    <div className="rounded-md bg-slate-50 p-3">
      <h5 className="mb-2 text-sm font-semibold text-slate-800">{title}</h5>
      <dl className="grid gap-2 sm:grid-cols-2">
        <StatusLine
          label="净收益（实际 / 5,000元等值；含估算退出成本）"
          value={`${metric.net_gain_actual_cny} / ${metric.net_gain_5000_equiv_cny} 元`}
        />
        <StatusLine
          label="最大回撤（协议口径：5,000元等值账面NAV）"
          value={`${metric.max_drawdown_amount_protocol_cny} 元 · ${metric.max_drawdown_ratio_percent}%`}
        />
        <StatusLine
          label="佣金（实际 / 等值）"
          value={`${metric.commission_actual_cny} / ${metric.commission_5000_equiv_cny} 元`}
        />
        <StatusLine
          label="滑点成本（实际 / 等值）"
          value={`${metric.slippage_cost_actual_cny} / ${metric.slippage_cost_5000_equiv_cny} 元`}
        />
        <StatusLine
          label="期末估算退出成本（实际 / 等值）"
          value={`${metric.estimated_exit_cost_actual_cny} / ${metric.estimated_exit_cost_5000_equiv_cny} 元`}
        />
        <StatusLine label="平均仓位敞口" value={`${metric.average_exposure_percent}%`} />
      </dl>
    </div>
  );
}

const styles = {
  container: {
    maxWidth: "1200px",
    margin: "0 auto",
    padding: "24px",
    fontFamily: "system-ui, -apple-system, sans-serif",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: "32px",
    paddingBottom: "24px",
    borderBottom: "2px solid #e5e7eb",
  },
  title: {
    fontSize: "32px",
    fontWeight: "700",
    color: "#111827",
    margin: "0 0 8px 0",
  },
  subtitle: {
    fontSize: "16px",
    color: "#6b7280",
    margin: 0,
  },
  headerActions: {
    display: "flex",
    gap: "1rem",
  },
  headerLink: {
    fontSize: "14px",
    color: "#2563eb",
    textDecoration: "none",
    padding: "8px 16px",
    borderRadius: "6px",
    border: "1px solid #e5e7eb",
    backgroundColor: "#ffffff",
    transition: "all 0.2s",
  },
  loadingText: {
    fontSize: "16px",
    color: "#6b7280",
    textAlign: "center" as const,
    padding: "48px 0",
  },
  errorText: {
    fontSize: "16px",
    color: "#dc2626",
    textAlign: "center" as const,
    padding: "48px 0",
  },
  emptyState: {
    textAlign: "center" as const,
    padding: "64px 24px",
    backgroundColor: "#f9fafb",
    borderRadius: "12px",
    border: "1px solid #e5e7eb",
    marginBottom: "32px",
  },
  emptyIcon: {
    fontSize: "64px",
    marginBottom: "16px",
  },
  emptyTitle: {
    fontSize: "24px",
    fontWeight: "600",
    color: "#111827",
    margin: "0 0 16px 0",
  },
  emptyText: {
    fontSize: "16px",
    color: "#6b7280",
    margin: "8px 0",
    lineHeight: "1.6",
  },
  infoBox: {
    marginTop: "32px",
    padding: "24px",
    backgroundColor: "#ffffff",
    borderRadius: "8px",
    border: "1px solid #e5e7eb",
    textAlign: "left" as const,
  },
  infoTitle: {
    fontSize: "18px",
    fontWeight: "600",
    color: "#111827",
    margin: "0 0 16px 0",
  },
  infoList: {
    fontSize: "14px",
    color: "#374151",
    lineHeight: "1.8",
    margin: 0,
    paddingLeft: "24px",
  },
  warningBox: {
    marginTop: "24px",
    fontSize: "14px",
    color: "#1e40af",
    backgroundColor: "#dbeafe",
    padding: "12px 24px",
    borderRadius: "6px",
    border: "1px solid #93c5fd",
  },
  linksSection: {
    marginTop: "32px",
  },
  linksTitle: {
    fontSize: "20px",
    fontWeight: "600",
    color: "#111827",
    margin: "0 0 16px 0",
  },
  linksGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))",
    gap: "16px",
  },
  linkCard: {
    display: "flex",
    alignItems: "center",
    gap: "16px",
    padding: "20px",
    backgroundColor: "#ffffff",
    border: "1px solid #e5e7eb",
    borderRadius: "8px",
    textDecoration: "none",
    transition: "all 0.2s",
    cursor: "pointer",
  },
  linkIcon: {
    fontSize: "32px",
  },
  linkContent: {
    flex: 1,
  },
  linkLabel: {
    fontSize: "16px",
    fontWeight: "600",
    color: "#111827",
    marginBottom: "4px",
  },
  linkDesc: {
    fontSize: "14px",
    color: "#6b7280",
  },
};
