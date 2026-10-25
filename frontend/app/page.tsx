"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { ensurePositionMarketCheck } from "@/lib/position-market-monitor";
import TopNav from "@/components/TopNav";
import {
  formatAnnualFeeSummary,
  formatFactValue,
  etfValuationKeyMetrics,
  etfNoValuationMessage,
  explainEtfEvidenceGap,
  getEtfResearchCoverage,
  hasVerifiableEtfValuation,
  formatInvestmentAssumptionSummary,
  isSingleSecurityResultForCode,
  neutralizeUnsupportedFundEvaluations,
  type EtfResearchForDisplay,
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
  detail?: string;
  basis: string[];
};

type ExplanationItem = {
  kind: string;
  label: string;
  text: string;
  evidence_level?: string | null;
  note?: string | null;
};

type InvestmentAssumption = {
  kind?: string;
  baseline_value?: number | null;
  unit?: string | null;
  endpoint?: string | null;
  source?: string | null;
  as_of?: string | null;
  window?: string | null;
  condition?: string | null;
  limitation?: string | null;
};

type V21FactRef = {
  id: string;
  label?: string;
  value: number | string | null;
  unit?: string;
  as_of?: string;
  source_title?: string;
  source_url?: string;
  source_pages?: string[];
};

type V21Evidence = {
  text: string;
  evidence_level: string;
  fact_refs: V21FactRef[];
};

type V21Research = {
  status: "success" | "unavailable";
  failure_reason?: string;
  snapshot?: { version?: string; sha256?: string; as_of?: string; source_count?: number } | null;
  llm?: { status?: string; call_id?: string | null; model?: string };
  layers?: Array<{
    layer_id: "underlying_assets" | "etf_product" | "current_timing";
    adequacy: "sufficient" | "limited" | "insufficient";
    judgment: string;
    evidence_level: string;
    supporting_evidence: V21Evidence[];
    counter_evidence: V21Evidence[];
    risks: V21Evidence[];
    thesis_changers: V21Evidence[];
    missing_evidence: string[];
  }>;
  core_reason?: string;
  summary_facts?: V21FactRef[];
  next_step?: string;
  next_step_reason?: string;
};

type V22SourceRef = {
  source_record_id: string;
  source_type?: string;
  source_quality?: string;
  title?: string;
  endpoint?: string;
  entity?: string;
  kind?: string;
  source?: string | null;
  requested_source?: string | null;
  source_field_present?: boolean;
  as_of?: string | null;
  published_at?: string | null;
  retrieved_at?: string | null;
  snapshot_created_at?: string | null;
  source_url?: string | null;
  summary?: string;
  reference_only?: boolean;
};

type V22Evidence = {
  text: string;
  evidence_level: string;
  source_ids: string[];
};

type V22Research = {
  status: "success" | "unavailable";
  version?: string;
  failure_reason?: string | null;
  hypothesis?: string | null;
  conclusion?: string | null;
  layers?: Array<{
    layer_id: "underlying_assets" | "etf_product" | "current_timing";
    adequacy: "sufficient" | "limited" | "insufficient";
    judgment: string;
    evidence_level: string;
    supporting_evidence: V22Evidence[];
    counter_evidence: V22Evidence[];
    risks: V22Evidence[];
    thesis_changers: V22Evidence[];
    missing_evidence: string[];
  }>;
  next_step?: string | null;
  next_step_reason?: string | null;
  sources?: V22SourceRef[];
  tool_trace?: Array<{
    tool: string;
    origin?: string;
    hypothesis?: string | null;
    evidence_need?: string | null;
    requested_source?: string | null;
    request_sent?: boolean;
    row_count?: number;
    nonempty_body_count?: number;
    source_ids?: string[];
    status?: string;
  }>;
};

type V22TransactionStatus = {
  eligibility?: string;
  signal?: string;
};

interface SingleSecurityResearch {
  status: "research_completed" | "research_unavailable";
  symbol: string;
  name: string;
  security_type: "stock" | "fund";
  verdict: string;
  research_reference_only: boolean;
  narrative_sentences: string[];
  rationale?: string | null;
  main_risk?: string | null;
  invalidation_condition?: string;
  explanation_items?: ExplanationItem[];
  identity_source?: {
    source?: string | null;
    endpoint?: string | null;
    symbol?: string | null;
    retrieved_at?: string | null;
  } | null;
  sources?: Array<{
    source_record_id?: string;
    source_type?: string;
    source_quality?: string;
    title?: string;
    published_at?: string | null;
    retrieved_at?: string;
    summary?: string;
    source_url?: string;
    announcement_code?: string;
    gaps?: string[];
    errors?: string[];
  }>;
  not_applicable?: string[];
  numeric_facts: NumericFact[];
  evidence_gaps: string[];
  investment_assumption?: InvestmentAssumption | null;
  research_diagnostic?: {
    failure_reason?: string | null;
    rationale_source?: string | null;
  } | null;
  research_v2_1?: V21Research | null;
  research_v2_2?: V22Research | null;
  transaction_status?: V22TransactionStatus | null;
  etf_research?: EtfResearchForDisplay;
}

function isSupportedResearchCode(value: string): boolean {
  return /^\d{6}$/.test(value) || value === "510880.SH";
}

function evidenceLevelClass(level: string | null | undefined): string {
  if (level === "已验证规则") return "border-blue-200 bg-blue-50 text-blue-800";
  if (level === "仅研究参考") return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-slate-300 bg-slate-100 text-slate-700";
}

function evidenceLevelLabel(level: string | null | undefined): string {
  switch (level) {
    case "已验证规则":
    case "仅研究参考":
    case "无依据":
      return level;
    default:
      return "等级未核验";
  }
}

function v21EvidenceLabel(level: string | null | undefined): string {
  switch (level) {
    case "high": return "高";
    case "medium": return "中";
    case "low": return "低";
    case "data_insufficient": return "数据不足";
    default: return "等级未核验";
  }
}

function V21ResearchBlock({ research }: { research: V21Research }) {
  const layerLabels: Record<"underlying_assets" | "etf_product" | "current_timing", string> = {
    underlying_assets: "底层资产",
    etf_product: "ETF产品",
    current_timing: "当前时机",
  };
  const evidenceGroups = [
    ["支持证据", "supporting_evidence"],
    ["经济反证", "counter_evidence"],
    ["风险", "risks"],
    ["可能改变观点的事实", "thesis_changers"],
  ] as const;

  return (
    <section aria-label="V2.1 ETF深度研究" className="rounded-md border border-blue-200 bg-blue-50/40 p-4">
      <h4 className="text-base font-semibold text-slate-900">V2.1 ETF深度研究 · 仅研究参考</h4>
      {research.status !== "success" ? (
        <p role="alert" className="mt-2 rounded border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-900">
          AI深度研究未完成。本次没有研究层结论；下方确定性估值与原始资料仍单独展示。
        </p>
      ) : (
        <>
          <div className="mt-3 rounded border border-slate-200 bg-white p-3">
            <p className="text-sm font-semibold text-slate-900">核心理由</p>
            <p className="mt-1 text-sm leading-6 text-slate-800">{research.core_reason}</p>
          </div>
          {(research.summary_facts ?? []).length > 0 && (
            <div className="mt-3 rounded border border-slate-200 bg-white p-3">
              <p className="text-sm font-semibold text-slate-900">可追溯关键数值（最多三项）</p>
              <ul className="mt-2 space-y-2">
                {(research.summary_facts ?? []).slice(0, 3).map((fact) => (
                  <li key={fact.id} className="text-sm">
                    <p className="font-medium text-slate-900">{fact.label ?? fact.id}：{fact.value}{fact.unit ? ` ${fact.unit}` : ""}</p>
                    <p className="mt-0.5 text-xs text-slate-600">{fact.source_title ?? fact.id} · 来源日期 {fact.as_of ?? "未核"}{fact.source_pages?.length ? ` · ${fact.source_pages.join("、")}` : ""}</p>
                    {fact.source_url && <a href={fact.source_url} target="_blank" rel="noreferrer" className="text-xs text-blue-700 underline">查看来源</a>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="mt-3 rounded border border-slate-200 bg-white p-3">
            <p className="text-sm font-semibold text-slate-900">建议的研究下一步：{research.next_step}</p>
            <p className="mt-1 text-sm leading-6 text-slate-700">{research.next_step_reason}</p>
            <p className="mt-1 text-xs text-slate-600">研究候选不代表入池、策略通过或交易授权。</p>
          </div>
          <div className="mt-3 space-y-2">
            {(research.layers ?? []).map((layer) => (
              <details key={layer.layer_id} className="rounded border border-slate-200 bg-white p-3">
                <summary className="cursor-pointer text-sm font-semibold text-slate-900">
                  {layerLabels[layer.layer_id]} · {layer.adequacy === "sufficient" ? "资料较充分" : layer.adequacy === "limited" ? "资料有限" : "资料不足"} · 证据强度{v21EvidenceLabel(layer.evidence_level)}
                </summary>
                <p className="mt-2 text-sm leading-6 text-slate-800">{layer.judgment}</p>
                {evidenceGroups.map(([label, key]) => {
                  const items = layer[key];
                  if (!items.length) return null;
                  return (
                    <div key={key} className="mt-3">
                      <h5 className="text-sm font-semibold text-slate-800">{label}</h5>
                      <ul className="mt-1 space-y-2">
                        {items.map((item, index) => (
                          <li key={`${key}-${index}`} className="text-sm leading-6 text-slate-700">
                            <p>{item.text} <span className="text-xs text-slate-500">（证据强度{v21EvidenceLabel(item.evidence_level)}）</span></p>
                            {item.fact_refs.map((fact) => (
                              <p key={fact.id} className="ml-3 mt-0.5 text-xs leading-5 text-slate-500">
                                {fact.label ?? fact.id}：{fact.value}{fact.unit ? ` ${fact.unit}` : ""} · {fact.source_title ?? fact.id} · {fact.as_of ?? "日期未核"}{fact.source_pages?.length ? ` · ${fact.source_pages.join("、")}` : ""}
                                {fact.source_url && <> · <a href={fact.source_url} target="_blank" rel="noreferrer" className="text-blue-700 underline">来源</a></>}
                              </p>
                            ))}
                          </li>
                        ))}
                      </ul>
                    </div>
                  );
                })}
                {layer.missing_evidence.length > 0 && (
                  <div className="mt-3">
                    <h5 className="text-sm font-semibold text-slate-800">尚缺资料</h5>
                    <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">{layer.missing_evidence.map((item, index) => <li key={index}>{item}</li>)}</ul>
                  </div>
                )}
              </details>
            ))}
          </div>
        </>
      )}
      <details className="mt-3 rounded border border-slate-200 bg-white p-3">
        <summary className="cursor-pointer text-xs font-semibold text-slate-700">研究快照与模型调用记录</summary>
        <dl className="mt-2 grid gap-1 break-all text-xs text-slate-600">
          <div>快照版本：{research.snapshot?.version ?? "未载入"}</div>
          <div>快照SHA-256：{research.snapshot?.sha256 ?? "未生成"}</div>
          <div>快照日期：{research.snapshot?.as_of ?? "未核"} · 来源数：{research.snapshot?.source_count ?? "未返回"}</div>
          <div>LLM状态：{research.llm?.status ?? "未调用或未记录"} · 调用编号：{research.llm?.call_id ?? "未返回"}</div>
        </dl>
      </details>
    </section>
  );
}

function isSafeSourceUrl(value: string | null | undefined): value is string {
  if (!value) return false;
  try {
    return new URL(value).protocol === "https:";
  } catch {
    return false;
  }
}

function v22FailureMessage(reason: string | null | undefined): string {
  const known: Record<string, string> = {
    permission_denied: "新闻接口权限不足，本次未重试，也未切换来源。",
    news_window_invalid: "新闻时间窗口无效，未发出新闻请求。",
    news_window_out_of_bounds: "新闻时间窗口超出限制，未发出新闻请求。",
    news_tool_failed: "新闻工具调用失败，本次研究已停止。",
    tool_not_allowed: "模型请求了未授权工具，本次研究已停止。",
    tool_input_invalid: "研究工具参数不符合限制，本次研究已停止。",
    tool_budget_exhausted: "取证工具预算已用尽，研究未完成。",
    llm_round_budget_exhausted: "模型轮次预算已用尽，研究未完成。",
    llm_budget_exhausted: "模型请求预算已用尽，研究未完成。",
    llm_timeout: "模型服务超时，研究未完成。",
    llm_request_failed: "模型服务请求失败，研究未完成。",
    source_snapshot_invalid: "已核验研究快照未通过来源校验，本次研究已停止。",
    response_protocol_mismatch: "模型未按约定提交结构化研究结果，本次研究已停止。",
    response_schema_or_source_validation_failed: "研究结果或来源引用未通过校验，本次未展示为完成结果。",
    source_validation_or_model_error: "研究来源或模型结果未通过校验，本次未展示为完成结果。",
  };
  return reason ? known[reason] ?? "具体失败原因未能核实；本次研究未完成。" : "具体失败原因未能核实；本次研究未完成。";
}

function V22ResearchBlock({
  research,
  transactionStatus,
}: {
  research: V22Research;
  transactionStatus?: V22TransactionStatus | null;
}) {
  const layerLabels: Record<"underlying_assets" | "etf_product" | "current_timing", string> = {
    underlying_assets: "底层资产",
    etf_product: "ETF产品",
    current_timing: "当前时机",
  };
  const evidenceGroups = [
    ["支持证据", "supporting_evidence"],
    ["反面证据", "counter_evidence"],
    ["风险", "risks"],
    ["可能改变观点的事实", "thesis_changers"],
  ] as const;
  const sourceById = new Map(
    (research.sources ?? []).map((source) => [source.source_record_id, source]),
  );
  const eligibility = transactionStatus?.eligibility ?? "本次未评估交易资格";
  const signal = transactionStatus?.signal ?? "本次未提供交易信号";

  return (
    <section aria-label="V2.2 ETF深度研究" className="rounded-md border border-blue-200 bg-blue-50/40 p-4">
      <h4 className="text-base font-semibold text-slate-900">V2.2 ETF深度研究 · 仅研究参考</h4>
      {research.status === "success" ? (
        <>
          <div className="mt-3 rounded border border-slate-200 bg-white p-3">
            <p className="text-sm font-semibold text-slate-900">研究结论</p>
            <p className="mt-1 text-sm leading-6 text-slate-800">{research.conclusion}</p>
          </div>
          <div aria-label="本次交易状态" className="mt-3 rounded border border-amber-200 bg-amber-50 p-3">
            <p className="text-sm font-semibold text-slate-900">本次交易状态</p>
            <p className="mt-1 text-sm text-slate-700">{eligibility}</p>
            <p className="text-sm text-slate-700">{signal}</p>
          </div>
          {research.hypothesis && (
            <div className="mt-3 rounded border border-slate-200 bg-white p-3">
              <p className="text-sm font-semibold text-slate-900">待检验假说</p>
              <p className="mt-1 text-sm leading-6 text-slate-800">{research.hypothesis}</p>
            </div>
          )}
          <div className="mt-3 space-y-2">
            {(research.layers ?? []).map((layer) => (
              <details key={layer.layer_id} className="rounded border border-slate-200 bg-white p-3">
                <summary className="cursor-pointer text-sm font-semibold text-slate-900">
                  {layerLabels[layer.layer_id]} · {layer.adequacy === "sufficient" ? "资料较充分" : layer.adequacy === "limited" ? "资料有限" : "资料不足"} · 证据强度{v21EvidenceLabel(layer.evidence_level)}
                </summary>
                <p className="mt-2 text-sm leading-6 text-slate-800">{layer.judgment}</p>
                {evidenceGroups.map(([label, key]) => {
                  const items = layer[key];
                  if (!items.length) return null;
                  return (
                    <div key={key} className="mt-3">
                      <h5 className="text-sm font-semibold text-slate-800">{label}</h5>
                      <ul className="mt-1 space-y-2">
                        {items.map((item, index) => (
                          <li key={`${key}-${index}`} className="text-sm leading-6 text-slate-700">
                            <p>{item.text} <span className="text-xs text-slate-500">（证据强度{v21EvidenceLabel(item.evidence_level)}）</span></p>
                            {item.source_ids.map((sourceId) => {
                              const source = sourceById.get(sourceId);
                              if (!source) {
                                return <p key={sourceId} className="ml-3 mt-0.5 text-xs text-amber-800">来源记录未返回：{sourceId}</p>;
                              }
                              const isNews = source.source_type === "news_feed";
                              return (
                                <div key={sourceId} className="ml-3 mt-0.5 text-xs leading-5 text-slate-600">
                                  <p>{source.title ?? sourceId}{isNews ? " · 新闻 feed 研究参考" : ""}</p>
                                  <p>
                                    {isNews && `${source.source ? `来源字段：${source.source}` : "来源字段未提供"} · `}
                                    {source.requested_source && `请求来源：${source.requested_source} · `}
                                    {source.published_at || source.as_of || "发表日期未提供"}
                                    {source.retrieved_at && ` · 获取时间 ${source.retrieved_at}`}
                                    {source.snapshot_created_at && ` · 快照日期 ${source.snapshot_created_at}`}
                                  </p>
                                  {source.summary && <p className="mt-0.5 whitespace-pre-wrap">{source.summary}</p>}
                                  {isSafeSourceUrl(source.source_url) ? (
                                    <a href={source.source_url} target="_blank" rel="noreferrer" className="text-blue-700 underline">查看来源</a>
                                  ) : (
                                    <p>链接未提供</p>
                                  )}
                                </div>
                              );
                            })}
                          </li>
                        ))}
                      </ul>
                    </div>
                  );
                })}
                {layer.missing_evidence.length > 0 && (
                  <div className="mt-3">
                    <h5 className="text-sm font-semibold text-slate-800">尚缺资料</h5>
                    <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">
                      {layer.missing_evidence.map((item, index) => <li key={index}>{item}</li>)}
                    </ul>
                  </div>
                )}
              </details>
            ))}
          </div>
          <div className="mt-3 rounded border border-slate-200 bg-white p-3">
            <p className="text-sm font-semibold text-slate-900">下一步：{research.next_step}</p>
            <p className="mt-1 text-sm leading-6 text-slate-700">{research.next_step_reason}</p>
          </div>
          {(research.tool_trace ?? []).length > 0 && (
            <details className="mt-3 rounded border border-slate-200 bg-white p-3">
              <summary className="cursor-pointer text-xs font-semibold text-slate-700">Agent 取证记录</summary>
              <ul className="mt-2 space-y-2 text-xs leading-5 text-slate-600">
                {(research.tool_trace ?? []).map((item, index) => (
                  <li key={`${item.tool}-${index}`}>
                    <p>{item.tool === "read_etf_evidence" ? "读取已核验 ETF 证据" : item.tool === "search_major_news" ? "查询 major_news feed" : item.tool === "search_news" ? "查询 news feed" : item.tool === "finish_research" ? "主动结束研究" : "研究工具"} · {item.status ?? "状态未返回"}</p>
                    {item.hypothesis && <p>假说：{item.hypothesis}</p>}
                    {item.evidence_need && <p>取证需要：{item.evidence_need}</p>}
                    {item.requested_source && <p>请求来源：{item.requested_source} · 返回记录 {item.row_count ?? 0} 条 · 有正文 {item.nonempty_body_count ?? 0} 条</p>}
                    {item.request_sent === false && <p>未发送外部请求</p>}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      ) : (
        <>
          <p role="alert" className="mt-2 rounded border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-900">
            AI深度研究未完成，本次没有研究层结论。{v22FailureMessage(research.failure_reason)}
          </p>
          <div className="mt-3 rounded border border-amber-200 bg-amber-50 p-3">
            <p className="text-sm font-semibold text-slate-900">本次交易状态</p>
            <p className="mt-1 text-sm text-slate-700">{eligibility}</p>
            <p className="text-sm text-slate-700">{signal}</p>
          </div>
        </>
      )}
    </section>
  );
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
  const isFund = result?.security_type === "fund";
  const isVerifiedEtf = result?.etf_research?.is_etf === true;
  const hasVerifiedEtfValuation = Boolean(
    isFund && result && hasVerifiableEtfValuation(
      result.etf_research,
      result.identity_source,
    )
  );
  const etfValuationConclusion = result?.etf_research?.valuation_conclusion;
  const hasDeterministicEtfRationale = [
    "deterministic_etf_summary",
    "deterministic_etf_data_gap",
    "deterministic_etf_not_supported",
    "deterministic_etf_unverified",
  ].includes(result?.research_diagnostic?.rationale_source ?? "");
  const findFact = (label: string) => facts.find((fact) => fact.label === label);
  const visibleEvidenceGaps = isFund
    ? (result?.evidence_gaps ?? [])
        .map((gap) => explainEtfEvidenceGap(gap, result?.etf_research))
        .filter((gap, index, gaps) => gaps.indexOf(gap) === index)
    : result?.evidence_gaps ?? [];
  const fundCoverage = isFund && result
    ? getEtfResearchCoverage({
        identitySource: result.identity_source,
        numericFacts: facts,
        sources: result.etf_research?.sources,
        etf: result.etf_research,
        evidenceGaps: visibleEvidenceGaps,
        notApplicable: result.not_applicable,
      })
    : { covered: [], limited: [], notCovered: [] };
  const fundExplanationItems = result?.explanation_items ?? [];
  const fundConclusionItem = fundExplanationItems.find((item) => item.kind === "conclusion");
  const fundReasonItem = fundExplanationItems.find((item) => item.kind === "reason");
  const hasFundRiskItem = fundExplanationItems.some((item) => item.kind === "risk");
  const hasFundInvalidationItem = fundExplanationItems.some((item) => item.kind === "invalidation_condition");
  const secondaryFundItems = fundExplanationItems.filter(
    (item) => item.kind !== "conclusion" && item.kind !== "reason",
  );
  const valuationRationale = hasVerifiedEtfValuation && hasDeterministicEtfRationale
    ? fundReasonItem?.text ?? result?.rationale ?? null
    : null;
  const keyMetrics: KeyMetric[] = !result
    ? []
    : isFund
      ? hasVerifiedEtfValuation ? etfValuationKeyMetrics(result.etf_research) : []
      : facts.slice(0, 3).map((fact, index) => ({
          id: `stock-${fact.endpoint}-${index}`,
          label: fact.label,
          value: formatFactValue(fact.label, fact.value, fact.unit),
          source: fact,
          basis: fact.window ? [fact.window] : [],
        }));
  const managementFeeFact = findFact("管理费率");
  const custodyFeeFact = findFact("托管费率");
  const annualFeeSummary = formatAnnualFeeSummary(managementFeeFact?.value, custodyFeeFact?.value);
  const invalidationText = result?.invalidation_condition ??
    result?.explanation_items?.find((item) => item.kind === "invalidation_condition")?.text;

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
        body: JSON.stringify({
          code: submittedCode,
          ...((submittedCode === "510880" || submittedCode === "510880.SH")
            ? { research_version: "v2.2" }
            : {}),
        }),
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

      <section id="research" className="max-w-3xl scroll-mt-6 rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="text-lg font-semibold text-slate-900">研究一只股票或 ETF</h2>
        <p className="mt-1 text-sm text-slate-600">输入六位代码，或输入510880.SH，查看带来源和日期的研究结果。</p>
        <form className="mt-4 flex flex-wrap items-end gap-3" onSubmit={researchSecurity}>
          <div className="flex min-w-56 flex-col gap-1">
            <label htmlFor="security-code" className="text-sm font-medium text-slate-700">证券代码</label>
            <input
              id="security-code"
              aria-label="证券代码"
              inputMode="text"
              autoComplete="off"
              maxLength={9}
              pattern="[0-9]{6}|510880\.SH"
              value={code}
              onChange={(event) => {
                const nextCode = event.target.value.toUpperCase().replace(/[^0-9.SH]/g, "").slice(0, 9);
                inputCodeRef.current = nextCode;
                requestVersionRef.current += 1;
                setCode(nextCode);
                setResult(null);
                setError(null);
                setLoading(false);
              }}
              placeholder="例如 510880 或 510880.SH"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none focus:border-slate-500"
            />
          </div>
          <button
            type="submit"
            disabled={loading || !isSupportedResearchCode(code)}
            className="rounded-md bg-[#171717] px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "研究中…" : "开始研究"}
          </button>
        </form>

        {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}

        {result && (
          <div className="mt-6 space-y-5 border-t border-slate-200 pt-5">
            {result.status === "research_unavailable" && !result.research_v2_1 && !result.research_v2_2 && (
              <p role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-800">
                AI总结暂不可用。以下确定性计算与已核验资料仍照常展示；未形成AI综合研究判断。
              </p>
            )}
            {result.status === "research_unavailable" && result.research_v2_1 && (
              <p role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-800">
                V2.1 AI深度研究暂不可用；未用确定性估值代替研究层结论。
              </p>
            )}
            {result.research_diagnostic?.failure_reason === "not_called_by_rule" && (
              <p role="note" className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
                该类型按规则不调用AI
              </p>
            )}
            <div>
              <p className="text-sm text-slate-500">{result.symbol} · {result.name} · {result.security_type === "fund" ? "ETF/基金" : "股票"}</p>
              <p className="mt-1 text-sm font-semibold text-amber-800">仅研究参考</p>
              {!isFund && <h3 className="mt-1 text-xl font-semibold text-slate-900">{result.verdict}</h3>}
            </div>

            {result.symbol === "510880.SH" && (
              <section aria-label="510880策略资格入口" className="rounded-md border border-amber-200 bg-amber-50 p-4">
                <h3 className="text-sm font-semibold text-amber-950">510880 策略资格尚未确认</h3>
                <p className="mt-1 text-sm leading-6 text-amber-900">
                  研究内容仍待核实：收益差不能当跟踪误差，成本与历史估值判断缺少比较依据；仅研究参考，不能据此入场。
                </p>
                <Link
                  href="/strategy-validations?symbol=510880.SH"
                  className="mt-2 inline-block text-sm font-medium text-blue-800 underline"
                >
                  查看资格核验与交易边界
                </Link>
              </section>
            )}

            {result.research_v2_2 && (
              <V22ResearchBlock research={result.research_v2_2} transactionStatus={result.transaction_status} />
            )}
            {result.research_v2_1 && <V21ResearchBlock research={result.research_v2_1} />}

            {isFund ? (
              <>
                {!result.research_v2_2 && <section aria-label="投资判断" className="rounded-md border border-amber-200 bg-amber-50 p-4">
                  <h4 className="text-sm font-semibold text-slate-900">投资判断：未评估</h4>
                  <p className="mt-1">
                    <span className="rounded border border-slate-300 bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
                      逐项等级：无依据（仅针对买卖建议）
                    </span>
                  </p>
                  <p className="mt-1 text-xs leading-5 text-slate-600">
                    当前接口未提供独立买卖判断。这是系统能力限制，不是研究后得出的投资结论。
                  </p>
                </section>}

                <section aria-label="估值结论与依据" className="rounded-md border border-slate-200 p-4">
                  <h4 className="text-sm font-semibold text-slate-900">估值结论</h4>
                  {hasVerifiedEtfValuation ? (
                    <div className="mt-1 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-base font-semibold text-slate-900">
                          {etfValuationConclusion?.label ?? (
                            etfValuationConclusion?.status === "data_gap" ? "估值资料缺口"
                              : etfValuationConclusion?.status === "not_supported" ? "估值方法限制"
                                : "估值规则结果"
                          )}
                        </p>
                      {fundConclusionItem ? (
                        <span className={`rounded border px-2 py-0.5 text-xs ${evidenceLevelClass(fundConclusionItem.evidence_level)}`}>
                          {evidenceLevelLabel(fundConclusionItem.evidence_level)}
                        </span>
                      ) : (
                        <span className="rounded border border-slate-300 bg-slate-100 px-2 py-0.5 text-xs text-slate-700">等级未返回</span>
                      )}
                      </div>
                      <p className="text-sm leading-6 text-slate-700">{etfValuationConclusion?.message}</p>
                    </div>
                  ) : (
                    <p className="mt-1 text-sm leading-6 text-slate-800">{etfNoValuationMessage(isVerifiedEtf, result.etf_research)}</p>
                  )}
                  {!isVerifiedEtf && result.verdict && (
                    <p className="mt-2 text-sm leading-6 text-slate-800">
                      研究层意见（仅研究参考）：{result.verdict}
                      {fundConclusionItem && `（逐项等级：${evidenceLevelLabel(fundConclusionItem.evidence_level)}）`}
                    </p>
                  )}
                  <h5 className="mt-3 text-sm font-semibold text-slate-900">估值依据</h5>
                  {hasVerifiedEtfValuation && hasDeterministicEtfRationale ? (
                    valuationRationale ? (
                      <div className="mt-1 flex flex-wrap items-start gap-2">
                        <p className="text-sm leading-6 text-slate-800">
                          {neutralizeUnsupportedFundEvaluations(valuationRationale)}
                        </p>
                        {fundReasonItem && (
                          <span className={`rounded border px-2 py-0.5 text-xs ${evidenceLevelClass(fundReasonItem.evidence_level)}`}>
                            {evidenceLevelLabel(fundReasonItem.evidence_level)}
                          </span>
                        )}
                      </div>
                    ) : (
                      <p className="mt-1 text-sm text-slate-600">估值依据说明未返回。</p>
                    )
                  ) : hasVerifiedEtfValuation ? (
                    <p className="mt-1 text-sm leading-6 text-slate-600">估值结论有来源支持；理由段来源未核实，原始估值资料见展开详情。</p>
                  ) : (
                    <p className="mt-1 text-sm leading-6 text-slate-600">本次没有可核验的估值结论或依据。</p>
                  )}
                </section>

                {secondaryFundItems.length > 0 && (
                  <section aria-label="风险与观察条件" className="space-y-3">
                    {secondaryFundItems.map((item, index) => (
                      <div key={`${item.kind}-${index}`} className="rounded-md border border-slate-200 p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-semibold text-slate-900">{item.label}</p>
                          <span className={`rounded border px-2 py-0.5 text-xs ${evidenceLevelClass(item.evidence_level)}`}>
                            {evidenceLevelLabel(item.evidence_level)}
                          </span>
                        </div>
                        <p className="mt-1 text-sm leading-6 text-slate-800">
                          {item.kind === "invalidation_condition"
                            ? result.investment_assumption
                              ? formatInvestmentAssumptionSummary(result.investment_assumption, item.text)
                              : "观察条件未核实；原撤回条件已保留在展开详情。"
                            : neutralizeUnsupportedFundEvaluations(item.text)}
                        </p>
                        {item.note && <p className="mt-1 text-xs leading-5 text-slate-600">{item.note}</p>}
                      </div>
                    ))}
                  </section>
                )}
                {!hasFundRiskItem && result.main_risk && (
                  <section aria-label="风险资料" className="rounded-md border border-slate-200 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="text-sm font-semibold text-slate-900">风险资料</h4>
                      <span className={`rounded border px-2 py-0.5 text-xs ${evidenceLevelClass(null)}`}>等级未返回</span>
                    </div>
                    <p className="mt-1 text-sm leading-6 text-slate-800">{neutralizeUnsupportedFundEvaluations(result.main_risk)}</p>
                  </section>
                )}
                {result.investment_assumption && !secondaryFundItems.some((item) => item.kind === "invalidation_condition") && (
                  <section aria-label="观察假设" className="rounded-md border border-slate-200 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="text-sm font-semibold text-slate-900">观察假设</h4>
                      <span className={`rounded border px-2 py-0.5 text-xs ${evidenceLevelClass(null)}`}>等级未返回</span>
                    </div>
                    <p className="mt-1 text-sm leading-6 text-slate-800">
                      {formatInvestmentAssumptionSummary(result.investment_assumption, "")}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-slate-600">仅作研究观察假设，不是估值失效条件或交易指令。</p>
                  </section>
                )}
                {!hasFundInvalidationItem && !result.investment_assumption && result.invalidation_condition && (
                  <section aria-label="撤回条件" className="rounded-md border border-slate-200 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="text-sm font-semibold text-slate-900">撤回条件</h4>
                      <span className={`rounded border px-2 py-0.5 text-xs ${evidenceLevelClass(null)}`}>等级未返回</span>
                    </div>
                    <p className="mt-1 text-sm leading-6 text-slate-800">原撤回条件等级未返回；完整原文保留在展开详情。</p>
                    <p className="mt-1 text-xs leading-5 text-slate-600">这不构成估值失效条件或交易指令。</p>
                  </section>
                )}
                {(result.explanation_items ?? []).length === 0 && (
                  <p role="note" className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-700">
                    逐项证据等级未返回，无法核验各项等级；这不表示整体研究均无依据。原始研究说明见下方展开详情。
                  </p>
                )}
              {fundExplanationItems.some((item) => item.kind === "reason" && item.evidence_level === "已验证规则") && (
                  <p role="note" className="rounded-md bg-slate-50 p-3 text-xs leading-5 text-slate-600">
                    “已验证规则”只说明对应理由由固定规则形成，不表示独立投资判断已完成、策略已通过验证或保证盈利。
                  </p>
                )}
              </>
            ) : (
              <div className="space-y-2 text-sm leading-6 text-slate-800">
                {result.narrative_sentences.map((sentence, index) => <p key={index}>{sentence}</p>)}
              </div>
            )}

            {isFund && (
              <section aria-label="资料覆盖" className="rounded-md border border-slate-200 p-4">
                <h4 className="text-sm font-semibold text-slate-900">本次资料覆盖</h4>
                <p className="mt-1 text-xs leading-5 text-slate-600">只列可追溯资料；覆盖状态不代表独立投资判断已完成。</p>
                <dl className="mt-3 space-y-2 text-sm leading-6">
                  <div>
                    <dt className="font-medium text-slate-900">已覆盖</dt>
                    <dd className="text-slate-700">{fundCoverage.covered.join("、") || "未返回来源、日期、字段与单位齐全的事实。"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-slate-900">已取得但有限</dt>
                    <dd className="text-slate-700">{fundCoverage.limited.join("、") || "未发现可列示的有限样本。"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-slate-900">尚未覆盖</dt>
                    <dd className="text-slate-700">
                      {fundCoverage.notCovered.join("；") || "本次未返回明确缺口；这不表示独立投资判断已完成。"}
                    </dd>
                  </div>
                </dl>
              </section>
            )}

            <section aria-label="可核验数值" className="rounded-md bg-slate-50 p-4">
              <h4 className="text-sm font-semibold text-slate-900">关键数值（最多三项）</h4>
              {keyMetrics.length === 0 ? (
                <p className="mt-2 text-sm text-slate-600">
                  {!isFund
                    ? "未获取可核验数值。"
                    : etfNoValuationMessage(isVerifiedEtf, result.etf_research)}
                </p>
              ) : (
                <ul className="mt-2 space-y-3">
                  {keyMetrics.map((metric) => (
                    <li key={metric.id}>
                      <p className="text-sm font-medium text-slate-900">
                        {metric.label}：{metric.value}
                      </p>
                      {!isFund && metric.source && (
                        <>
                          <p className="mt-1 text-xs text-slate-600">
                            {`${metric.source.source} · ${metric.source.endpoint}${metric.source.field ? `.${metric.source.field}` : ""} · ${metric.source.symbol} · 来源日期 ${metric.source.date} · 获取时间 ${new Date(metric.source.retrieved_at).toLocaleString("zh-CN")}`}
                          </p>
                          {metric.basis.map((basis, index) => (
                            <p key={`${metric.id}-basis-${index}`} className="mt-1 text-xs text-slate-600">统计口径：{basis}</p>
                          ))}
                          {metric.source.verification_source_url && (
                            <a href={metric.source.verification_source_url} target="_blank" rel="noreferrer" className="mt-1 inline-block text-xs text-blue-700 underline">
                              官方单位核验来源
                            </a>
                          )}
                        </>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {isFund && keyMetrics.length > 0 && <p className="mt-2 text-xs text-slate-600">来源日期与统计口径见展开详情。</p>}
            </section>

            {isFund && (
              <details className="rounded-md border border-slate-200 p-4">
                <summary className="cursor-pointer text-sm font-semibold text-slate-900">展开基金资料、来源日期、口径与原始缺口</summary>
                <div className="mt-4 space-y-5">
                  <section aria-label="原始研究说明">
                    <h4 className="text-sm font-semibold text-slate-900">接口返回的原始研究说明</h4>
                    {result.verdict && (
                      <p className="mt-1 text-sm leading-6 text-slate-700">接口原始综合意见：{result.verdict}</p>
                    )}
                    {(result.explanation_items ?? []).length === 0 && (
                      <p className="mt-1 text-xs leading-5 text-slate-600">逐项证据等级未返回；以下保留原文，不据此推断整体研究无依据或已验证。</p>
                    )}
                    <div className="mt-2 space-y-2 text-sm leading-6 text-slate-700">
                      {result.narrative_sentences.map((sentence, index) => (
                        <p key={`raw-narrative-${index}`}>{neutralizeUnsupportedFundEvaluations(sentence)}</p>
                      ))}
                      {result.rationale && !result.narrative_sentences.includes(`理由：${result.rationale}`) && (
                        <p>理由字段原文：{neutralizeUnsupportedFundEvaluations(result.rationale)}</p>
                      )}
                    </div>
                  </section>

                  {fundExplanationItems.length > 0 && (
                    <section aria-label="原始逐项说明">
                      <h4 className="text-sm font-semibold text-slate-900">原始逐项说明</h4>
                      <ul className="mt-2 space-y-2 text-sm leading-6 text-slate-700">
                        {fundExplanationItems.map((item, index) => (
                          <li key={`raw-explanation-${item.kind}-${index}`}>
                            <p><span className="font-medium">{item.label}：</span>{neutralizeUnsupportedFundEvaluations(item.text)}</p>
                            <p className="text-xs text-slate-600">接口等级原值：{item.evidence_level ?? "未返回"}</p>
                            {item.note && <p className="text-xs text-slate-600">{item.note}</p>}
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}

                  <section aria-label="基金数值资料">
                    <h4 className="text-sm font-semibold text-slate-900">已返回的基金数值与来源</h4>
                    {facts.length === 0 ? <p className="mt-1 text-sm text-slate-600">未获取数值资料。</p> : (
                      <ul className="mt-2 space-y-3">
                        {facts.map((fact, index) => (
                          <li key={`${fact.endpoint}-${fact.date}-${index}`}>
                            <p className="text-sm font-medium text-slate-900">{fact.label}：{formatFactValue(fact.label, fact.value, fact.unit)}</p>
                            <p className="mt-1 text-xs text-slate-600">{fact.source} · {fact.endpoint}{fact.field ? `.${fact.field}` : ""} · {fact.symbol} · 来源日期 {fact.date} · 获取时间 {fact.retrieved_at}</p>
                            {fact.window && <p className="mt-1 text-xs text-slate-600">统计口径：{fact.window}</p>}
                            {fact.verification_source_url && <a href={fact.verification_source_url} target="_blank" rel="noreferrer" className="mt-1 inline-block text-xs text-blue-700 underline">官方单位核验来源</a>}
                          </li>
                        ))}
                      </ul>
                    )}
                    <p className="mt-3 text-sm font-medium text-slate-900">{annualFeeSummary ?? `管理费${formatFactValue("管理费率", managementFeeFact?.value)} + 托管费${formatFactValue("托管费率", custodyFeeFact?.value)}；合计未获取`}</p>
                    <p role="note" className="mt-1 text-xs leading-5 text-slate-600">
                      {annualFeeSummary
                        ? "管理费与托管费年费率合计已核验。当前未完成招募说明书中计提与派息口径关系的核对；本页不把年费率换算为分红扣项，也不从显示的股息率重复扣减。"
                        : "管理费或托管费尚未全部核验，合计未获取；不估算其与本页历史现金分红收益率的扣减关系。"}
                    </p>
                  </section>

                  <section aria-label="估值规则原始资料">
                    <h4 className="text-sm font-semibold text-slate-900">基金类别与估值资料</h4>
                    <dl className="mt-2 grid gap-2 text-xs text-slate-700 sm:grid-cols-2">
                      {[
                        ["已核验 ETF 身份", String(result.etf_research?.is_etf ?? "未获取")],
                        ["基金类别", result.etf_research?.category ?? result.etf_research?.fund_type ?? "未获取"],
                        ["跟踪基准", result.etf_research?.benchmark ?? "未获取"],
                        ["估值状态", result.etf_research?.valuation_conclusion?.status ?? "未获取"],
                        ["估值口径", result.etf_research?.valuation_conclusion?.basis ?? "未获取"],
                        ["规则原文", result.etf_research?.valuation_conclusion?.message ?? "未获取"],
                      ].map(([label, value]) => <div key={label}><dt className="font-medium">{label}</dt><dd className="mt-0.5 break-words">{value}</dd></div>)}
                    </dl>
                    {(result.identity_source || result.sources?.length || result.etf_research) && (
                      <details className="mt-3 rounded border border-slate-200 p-3">
                        <summary className="cursor-pointer text-xs font-semibold text-slate-700">查看来源追溯字段</summary>
                        <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-3 text-xs text-slate-700">{JSON.stringify({ identity_source: result.identity_source, sources: result.sources, etf_research: result.etf_research }, null, 2)}</pre>
                      </details>
                    )}
                    {keyMetrics.map((metric) => <p key={`${metric.id}-source`} className="mt-2 text-xs text-slate-600">{metric.label}来源与口径：{metric.detail}；统计口径：{metric.basis.join("；")}</p>)}
                  </section>

                  {result.investment_assumption && (
                    <section aria-label="观察假设原始条件">
                      <h4 className="text-sm font-semibold text-slate-900">观察假设原始条件</h4>
                      {invalidationText && <p className="mt-2 text-xs leading-5 text-slate-700">完整原撤回条件：{invalidationText}</p>}
                      <details className="mt-2 rounded border border-slate-200 p-3">
                        <summary className="cursor-pointer text-xs font-semibold text-slate-700">查看观察条件原始字段</summary>
                        <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-3 text-xs text-slate-700">{JSON.stringify(result.investment_assumption, null, 2)}</pre>
                      </details>
                    </section>
                  )}
                  {!result.investment_assumption && invalidationText && (
                    <section aria-label="原撤回条件">
                      <h4 className="text-sm font-semibold text-slate-900">原撤回条件</h4>
                      <p className="mt-2 text-xs leading-5 text-slate-700">{invalidationText}</p>
                    </section>
                  )}

                  {(result.not_applicable?.length ?? 0) > 0 && (
                    <section aria-label="原始不适用资料">
                      <h4 className="text-sm font-semibold text-slate-900">原始不适用资料</h4>
                      <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-slate-700">{result.not_applicable?.map((item, index) => <li key={index}>{item}</li>)}</ul>
                    </section>
                  )}
                  <section aria-label="原始证据缺口">
                    <h4 className="text-sm font-semibold text-slate-900">原始证据缺口</h4>
                    <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-slate-700">
                      {(result.etf_research?.gaps ?? []).map((gap, index) => <li key={`etf-${index}`}>{gap}</li>)}
                      {result.evidence_gaps.map((gap, index) => <li key={`api-${index}`}>{gap}</li>)}
                      {result.etf_research?.gaps?.length === 0 && result.evidence_gaps.length === 0 && <li>未返回。</li>}
                    </ul>
                  </section>
                </div>
              </details>
            )}

            {!isFund && visibleEvidenceGaps.length > 0 && (
              <section aria-label="证据缺口与影响">
                <h4 className="text-sm font-semibold text-slate-900">证据缺口与影响</h4>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">
                  {visibleEvidenceGaps.map((gap, index) => <li key={index}>{gap}</li>)}
                </ul>
              </section>
            )}
            {!isFund && result.evidence_gaps.length === 0 && (
              <section aria-label="证据缺口">
                <h4 className="text-sm font-semibold text-slate-900">证据缺口</h4>
                <p className="mt-1 text-sm text-slate-600">未获取。</p>
              </section>
            )}
          </div>
        )}
      </section>
    </main>
    </>
  );
}
