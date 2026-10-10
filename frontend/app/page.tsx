"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { ensurePositionMarketCheck } from "@/lib/position-market-monitor";
import TopNav from "@/components/TopNav";
import {
  formatAnnualFeeSummary,
  formatDividendYield,
  formatDrawdown,
  formatFactValue,
  formatHistoricalPercentile,
  formatMeanAmount,
  isSingleSecurityResultForCode,
} from "@/lib/single-security-format";

type NumericFact = {
  label: string;
  value: number | string;
  unit: string;
  symbol: string;
  source: string;
  endpoint: string;
  field?: string;
  date: string;
  retrieved_at: string;
  window?: string;
  verification_source_url?: string | null;
};

type KeyMetric = {
  id: string;
  label: string;
  value: string;
  source?: NumericFact;
  basis: string[];
};

interface SingleSecurityResearch {
  status: "research_completed" | "research_unavailable" | "valuation_unavailable" | "valuation_not_supported";
  symbol: string;
  name: string;
  security_type: "stock" | "fund";
  verdict: string;
  research_reference_only: boolean;
  narrative_sentences: string[];
  not_applicable?: string[];
  numeric_facts: NumericFact[];
  evidence_gaps: string[];
  etf_research?: {
    category?: string;
    valuation_conclusion?: { basis?: string | null; message?: string; label?: string | null } | null;
  } | null;
}

export default function HomePage() {
  const [code, setCode] = useState("");
  const [result, setResult] = useState<SingleSecurityResearch | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tip, setTip] = useState<string | null>(null);
  const inputCodeRef = useRef("");
  const requestVersionRef = useRef(0);

  useEffect(() => {
    ensurePositionMarketCheck().then((response) => {
      const hasPositions = response.items && response.items.length > 0;
      setTip(hasPositions ? "持仓行情已更新" : "今日无需操作");
    }).catch((error) => {
      console.error("Position market check failed:", error);
      setTip("今日无需操作");
    });
  }, []);

  const facts = result?.numeric_facts ?? [];
  const findFact = (label: string) => facts.find((fact) => fact.label === label);
  const dividendYieldFact = findFact("近12个月现金分红收益率");
  const percentileFact = findFact("ETF自身现金分红收益率历史分位");
  const valuationFact = findFact("估值参考");
  const drawdownFact = facts.find((fact) => fact.label.includes("回撤"));
  const averageAmountFact = findFact("近20个SSE交易日平均成交额");
  const indexPePercentileFact = findFact("跟踪指数PE十年分位");
  const indexPbPercentileFact = findFact("跟踪指数PB十年分位");
  const indexValuationFact = findFact("估值参考");
  const etfCategory = result?.etf_research?.category;
  const managementFeeFact = findFact("管理费率");
  const custodyFeeFact = findFact("托管费率");
  const isFund = result?.security_type === "fund";
  const keyMetrics: KeyMetric[] = !result
    ? []
    : isFund && etfCategory === "dividend"
      ? [
          {
            id: "dividend-yield-history",
            label: "ETF自身现金分红收益率 / 历史分位",
            value: `${formatDividendYield(dividendYieldFact?.value)} · 历史分位 ${formatHistoricalPercentile(percentileFact?.value)} · ${formatFactValue("估值参考", valuationFact?.value)}`,
            source: dividendYieldFact ?? percentileFact ?? valuationFact,
            basis: [
              dividendYieldFact?.window ? `当前收益率：${dividendYieldFact.window}` : "当前收益率口径未获取。",
              percentileFact?.window ? `历史分位：${percentileFact.window}` : "历史分位样本未获取。",
              valuationFact?.window ? `估值替代口径：${valuationFact.window}` : "指数估值不可用，ETF自身历史替代参考未获取。",
            ],
          },
          {
            id: "high-drawdown",
            label: drawdownFact?.label ?? "距近一年已观察最高价回撤",
            value: drawdownFact ? formatDrawdown(drawdownFact.value) : "未获取",
            source: drawdownFact,
            basis: [drawdownFact?.window ?? "高点观察区间和有效样本未获取。"],
          },
          {
            id: "average-amount",
            label: "近20个SSE交易日平均成交额",
            value: averageAmountFact ? formatMeanAmount(averageAmountFact.value) : "未获取",
            source: averageAmountFact,
            basis: [averageAmountFact?.window ?? "完整的SSE日历20日成交额未获取。"],
          },
        ]
      : isFund && etfCategory === "broad"
        ? [
            {
              id: "index-pe-percentile",
              label: "跟踪指数PE十年分位",
              value: formatHistoricalPercentile(indexPePercentileFact?.value),
              source: indexPePercentileFact,
              basis: [indexPePercentileFact?.window ?? "PE完整历史覆盖未获取。"],
            },
            {
              id: "index-pb-percentile",
              label: "跟踪指数PB十年分位",
              value: formatHistoricalPercentile(indexPbPercentileFact?.value),
              source: indexPbPercentileFact,
              basis: [indexPbPercentileFact?.window ?? "PB完整历史覆盖未获取。"],
            },
            {
              id: "index-valuation",
              label: "估值结论",
              value: indexValuationFact
                ? formatFactValue("估值参考", indexValuationFact.value)
                : result.etf_research?.valuation_conclusion?.label
                  ?? result.etf_research?.valuation_conclusion?.message
                  ?? "未形成估值结论",
              source: indexValuationFact ?? indexPePercentileFact ?? indexPbPercentileFact,
              basis: [indexValuationFact?.window ?? result.etf_research?.valuation_conclusion?.message ?? "估值规则或覆盖情况未获取。"],
            },
          ]
        : isFund
          ? [
              {
                id: "fund-close",
                label: "最近收盘价",
                value: formatFactValue("最近收盘价", findFact("最近收盘价")?.value, "元/份"),
                source: findFact("最近收盘价"),
                basis: [findFact("最近收盘价")?.window ?? "最近报告收盘价未获取。"],
              },
              {
                id: "fund-return",
                label: "近一年报告收盘价变化",
                value: formatFactValue("近一年报告收盘价变化", findFact("近一年报告收盘价变化")?.value),
                source: findFact("近一年报告收盘价变化"),
                basis: [findFact("近一年报告收盘价变化")?.window ?? "一年价格变化未获取。"],
              },
              {
                id: "fund-activity",
                label: averageAmountFact?.label ?? drawdownFact?.label ?? "近20个SSE交易日平均成交额",
                value: averageAmountFact
                  ? formatMeanAmount(averageAmountFact.value)
                  : drawdownFact ? formatDrawdown(drawdownFact.value) : "未获取",
                source: averageAmountFact ?? drawdownFact,
                basis: [averageAmountFact?.window ?? drawdownFact?.window ?? "成交额和回撤资料未获取。"],
              },
            ]
          : facts.slice(0, 3).map((fact, index) => ({
              id: `stock-${fact.endpoint}-${index}`,
              label: fact.label,
              value: formatFactValue(fact.label, fact.value, fact.unit),
              source: fact,
              basis: fact.window ? [fact.window] : [],
            }));

  const keyFactLabels = new Set([
    "近12个月现金分红收益率",
    "ETF自身现金分红收益率历史分位",
    "估值参考",
    "近20个SSE交易日平均成交额",
    "跟踪指数PE十年分位",
    "跟踪指数PB十年分位",
  ]);
  const fundDetailFacts = facts.filter((fact) =>
    !keyFactLabels.has(fact.label)
    && !fact.label.includes("回撤")
    && fact.label !== "管理费率"
    && fact.label !== "托管费率",
  );
  const annualFeeSummary = formatAnnualFeeSummary(
    managementFeeFact?.value,
    custodyFeeFact?.value,
  );
  const feeSourceFacts = [managementFeeFact, custodyFeeFact].filter(
    (fact): fact is NumericFact => Boolean(fact?.verification_source_url),
  );
  const feeSourceDates = [
    managementFeeFact?.date ? `管理费来源日期 ${managementFeeFact.date}` : "管理费来源日期未获取",
    custodyFeeFact?.date ? `托管费来源日期 ${custodyFeeFact.date}` : "托管费来源日期未获取",
  ];

  async function researchSecurity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submittedCode = code;
    const requestVersion = ++requestVersionRef.current;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";
      const response = await fetch(`${apiBase}/api/research/single-security`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "研究暂不可用，请稍后重试。");
      }
      if (!isSingleSecurityResultForCode(submittedCode, payload.symbol)) {
        throw new Error("返回证券身份与本次输入不一致，结果未展示。");
      }
      if (requestVersionRef.current === requestVersion && inputCodeRef.current === submittedCode) {
        setResult(payload as SingleSecurityResearch);
      }
    } catch (requestError) {
      if (requestVersionRef.current === requestVersion && inputCodeRef.current === submittedCode) {
        setError(requestError instanceof Error ? requestError.message : "研究暂不可用，请稍后重试。");
      }
    } finally {
      if (requestVersionRef.current === requestVersion) setLoading(false);
    }
  }

  return (
    <>
      <TopNav tip={tip} />
      <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-6 py-8">

      <section className="max-w-3xl rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="text-lg font-semibold text-slate-900">研究一只股票或 ETF</h2>
        <p className="mt-1 text-sm text-slate-600">输入六位代码，查看带来源和日期的研究结果。</p>
        <form className="mt-4 flex flex-wrap items-end gap-3" onSubmit={researchSecurity}>
          <div className="flex min-w-56 flex-col gap-1">
            <label htmlFor="security-code" className="text-sm font-medium text-slate-700">证券代码</label>
            <input
              id="security-code"
              aria-label="证券代码"
              inputMode="numeric"
              autoComplete="off"
              maxLength={6}
              pattern="[0-9]{6}"
              value={code}
              onChange={(event) => {
                const nextCode = event.target.value.replace(/\D/g, "").slice(0, 6);
                inputCodeRef.current = nextCode;
                requestVersionRef.current += 1;
                setCode(nextCode);
                setResult(null);
                setError(null);
                setLoading(false);
              }}
              placeholder="例如 510880"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none focus:border-slate-500"
            />
          </div>
          <button
            type="submit"
            disabled={loading || !/^\d{6}$/.test(code)}
            className="rounded-md bg-[#171717] px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "研究中…" : "开始研究"}
          </button>
        </form>

        {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}

        {result && (
          <div className="mt-6 space-y-5 border-t border-slate-200 pt-5">
            {result.status === "research_unavailable" && (
              <p role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-800">
                AI总结暂不可用。以下确定性计算与已核验资料仍照常展示；未形成AI综合研究判断。
              </p>
            )}
            <div>
              <p className="text-sm text-slate-500">{result.symbol} · {result.name} · {result.security_type === "fund" ? "ETF/基金" : "股票"}</p>
              <p className="mt-1 text-sm font-semibold text-amber-800">仅研究参考</p>
              <h3 className="mt-1 text-xl font-semibold text-slate-900">{result.verdict}</h3>
            </div>

            <div className="space-y-2 text-sm leading-6 text-slate-800">
              {result.narrative_sentences.map((sentence, index) => <p key={index}>{sentence}</p>)}
            </div>

            <section aria-label="可核验数值" className="rounded-md bg-slate-50 p-4">
              <h4 className="text-sm font-semibold text-slate-900">关键指标（三组）</h4>
              {keyMetrics.length === 0 ? (
                <p className="mt-2 text-sm text-slate-600">未获取可核验数值。</p>
              ) : (
                <ul className="mt-2 space-y-3">
                  {keyMetrics.map((metric) => (
                    <li key={metric.id}>
                      <p className="text-sm font-medium text-slate-900">
                        {metric.label}：{metric.value}
                      </p>
                      <p className="mt-1 text-xs text-slate-600">
                        {metric.source
                          ? `${metric.source.source} · ${metric.source.endpoint}${metric.source.field ? `.${metric.source.field}` : ""} · ${metric.source.symbol} · 来源日期 ${metric.source.date} · 获取时间 ${new Date(metric.source.retrieved_at).toLocaleString("zh-CN")}`
                          : "来源日期未获取"}
                      </p>
                      <details className="mt-1">
                        <summary className="cursor-pointer text-xs text-slate-500 hover:text-slate-700">
                          统计口径（{metric.basis.length}项）
                        </summary>
                        {metric.basis.map((basis, index) => (
                          <p key={`${metric.id}-basis-${index}`} className="mt-1 text-xs text-slate-600">
                            {basis}
                          </p>
                        ))}
                      </details>
                      {metric.source?.verification_source_url && (
                        <a
                          href={metric.source.verification_source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-1 inline-block text-xs text-blue-700 underline"
                        >
                          官方单位核验来源
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {result.security_type === "fund" && (() => {
              return (
                <section aria-label="基金资料" className="rounded-md border border-slate-200 p-4">
                  <h4 className="text-sm font-semibold text-slate-900">已核验基金资料与其他数值</h4>
                  <ul className="mt-2 space-y-3">
                    {fundDetailFacts.map((fact, index) => (
                      <li key={`${fact.endpoint}-${fact.date}-${index}`}>
                        <p className="text-sm font-medium text-slate-900">
                          {fact.label}：{formatFactValue(fact.label, fact.value, fact.unit)}
                        </p>
                        <p className="mt-1 text-xs text-slate-600">
                          {fact.source} · {fact.endpoint}{fact.field ? `.${fact.field}` : ""} · {fact.symbol} · 来源日期 {fact.date} · 获取时间 {new Date(fact.retrieved_at).toLocaleString("zh-CN")}
                        </p>
                        {fact.window && <p className="mt-1 text-xs text-slate-600">统计口径：{fact.window}</p>}
                        {fact.verification_source_url && (
                          <a
                            href={fact.verification_source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="mt-1 inline-block text-xs text-blue-700 underline"
                          >
                            官方单位核验来源
                          </a>
                        )}
                      </li>
                    ))}
                    <li key="verified-annual-fees">
                      <p className="text-sm font-medium text-slate-900">
                        {annualFeeSummary ?? `管理费${formatFactValue("管理费率", managementFeeFact?.value)} + 托管费${formatFactValue("托管费率", custodyFeeFact?.value)}；合计未获取`}
                      </p>
                      <p className="mt-1 text-xs text-slate-600">
                        {(managementFeeFact ?? custodyFeeFact)?.source ?? "来源未获取"} · fund_basic · {feeSourceDates.join(" · ")}
                      </p>
                      {feeSourceFacts.map((fact) => (
                        <a
                          key={`${fact.label}-${fact.verification_source_url}`}
                          href={fact.verification_source_url ?? undefined}
                          target="_blank"
                          rel="noreferrer"
                          className="mr-3 mt-1 inline-block text-xs text-blue-700 underline"
                        >
                          {fact.label}官方资料
                        </a>
                      ))}
                    </li>
                  </ul>
                  <p role="note" className="mt-3 text-xs leading-5 text-slate-600">
                    {annualFeeSummary
                      ? "管理费与托管费年费率合计已核验。当前未完成招募说明书中计提与派息口径关系的核对；本页不把年费率换算为分红扣项，也不从显示的股息率重复扣减。"
                      : "管理费或托管费尚未全部核验，合计未获取；不估算其与本页历史现金分红收益率的扣减关系。"}
                  </p>
                </section>
              );
            })()}

            {(result.not_applicable?.length ?? 0) > 0 && (
              <section aria-label="不适用资料">
                <h4 className="text-sm font-semibold text-slate-900">不适用资料</h4>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">
                  {result.not_applicable?.map((item, index) => <li key={index}>{item}</li>)}
                </ul>
              </section>
            )}

            <section aria-label="证据缺口">
              <h4 className="text-sm font-semibold text-slate-900">证据缺口</h4>
              {result.evidence_gaps.length === 0 ? (
                <p className="mt-1 text-sm text-slate-600">未获取。</p>
              ) : (
                <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">
                  {result.evidence_gaps.map((gap, index) => <li key={index}>{gap}</li>)}
                </ul>
              )}
            </section>
          </div>
        )}
      </section>
    </main>
    </>
  );
}
