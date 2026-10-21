/**
 * Strategy Validations - Shell Page
 * 
 * P3-9: Shell page for strategy validation cases (currently empty)
 * - Display empty state (no validation cases yet)
 * - Explain validation process
 * - Link to related pages
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import TopNav from "@/components/TopNav";
import StrategyValidationStatusCard, {
  StrategyValidationStatus,
} from "@/components/StrategyValidationStatusCard";

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

export default function StrategyValidationsPage() {
  const [data, setData] = useState<ValidationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";

  useEffect(() => {
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
