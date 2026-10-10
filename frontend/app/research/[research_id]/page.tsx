'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import ResearchSources from '@/components/ResearchSources';

interface ResearchCase {
  theme_id: string;
  theme_name: string;
  status: string;
  source_type: string;
  background: string;
  research_mode: string;
  notes: string;
  created_at: string;
  updated_at: string;
  user_industry_chain_hypothesis?: any | null;
  research_output?: any | null;
  approval_decision?: string | null;
  confirmed_by?: string | null;
  decision_loop_id?: string | null;
}

const API = 'http://localhost:8010';

function extractTicker(name: string): string {
  const m = name.match(/\(([0-9]{6})/);
  if (!m) return '';
  const code = m[1];
  // ponytail: 沪市 60 开头 → .SH，深市 00/30 开头 → .SZ
  if (code.startsWith('60')) return `${code}.SH`;
  if (code.startsWith('00') || code.startsWith('30')) return `${code}.SZ`;
  return code; // 其他保留原样
}
function extractCompany(name: string): string {
  return name.split(' (')[0].trim();
}
function pretty(v: any): string {
  try { return JSON.stringify(v, null, 2); } catch { return String(v); }
}

export default function ResearchDetailPage() {
  const params = useParams();
  const researchId = params.research_id as string;

  const [researchCase, setResearchCase] = useState<ResearchCase | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [serviceHealth, setServiceHealth] = useState<any>(null);

  const [hypInput, setHypInput] = useState('');
  const [hypSaved, setHypSaved] = useState(false);
  const [researching, setResearching] = useState(false);
  const [researchError, setResearchError] = useState<string | null>(null);
  const [deciding, setDeciding] = useState(false);
  const [poolResult, setPoolResult] = useState<any | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);

  const loadCase = () => {
    Promise.all([
      fetch(`${API}/api/research/themes/${researchId}`).then(r => r.json()),
      fetch(`${API}/api/research/service-health`).then(r => r.json()).catch(() => null)
    ]).then(([caseData, healthData]) => {
      setResearchCase(caseData);
      setServiceHealth(healthData);
      setHypSaved(!!caseData.user_industry_chain_hypothesis);
      setLoading(false);
    }).catch(err => {
      console.error('Failed to load research case:', err);
      setError(err.message);
      setLoading(false);
    });
  };

  useEffect(() => { if (researchId) loadCase(); }, [researchId]);

  const saveHypothesis = async () => {
    let parsed: any = null;
    try {
      parsed = hypInput.trim() ? JSON.parse(hypInput) : null;
    } catch (e) {
      setResearchError('假设必须是合法 JSON 对象');
      return;
    }
    if (!parsed || typeof parsed !== 'object') {
      setResearchError('假设必须是 JSON 对象，例如 {"upstream_entity":"某公司","relation_type":"supplier"}');
      return;
    }
    const r = await fetch(`${API}/api/research/themes/${researchId}/hypothesis`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_industry_chain_hypothesis: parsed }),
    });
    if (!r.ok) {
      setResearchError(`保存失败：${r.status}`);
      return;
    }
    setResearchError(null);
    setHypSaved(true);
    loadCase();
  };

  const runResearch = async () => {
    if (!researchCase) return;
    const ticker = extractTicker(researchCase.theme_name);
    const company = extractCompany(researchCase.theme_name);
    if (!ticker) {
      setResearchError('无法从案例名解析 6 位代码，请手动调用研究接口');
      return;
    }
    setResearching(true);
    setResearchError(null);
    const r = await fetch(`${API}/api/research/themes/${researchId}/run-research`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker, company_name: company }),
    });
    setResearching(false);
    if (!r.ok) {
      const t = await r.text();
      setResearchError(`研究未完成（${r.status}）：${t.slice(0, 220)}`);
      return;
    }
    setPoolResult(null);
    loadCase();
  };

  const decide = async (decision: string) => {
    if (!researchCase) return;
    const ticker = extractTicker(researchCase.theme_name);
    const company = extractCompany(researchCase.theme_name);
    if (!ticker) {
      setDecisionError('无法从案例名解析代码');
      return;
    }
    setDeciding(true);
    setDecisionError(null);
    const r = await fetch(`${API}/api/research/themes/${researchId}/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        decision,
        confirmed_by: 'user',
        decision_loop_id: `loop_${researchId}`,
        ticker,
        company_name: company,
        exchange: ticker.startsWith('6') ? 'SSE' : 'SZSE',
        snapshot_date: new Date().toISOString().slice(0, 10),
      }),
    });
    setDeciding(false);
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      setDecisionError(`决策未执行（${r.status}）：${JSON.stringify(body).slice(0, 220)}`);
      return;
    }
    if (decision === 'continue') {
      setPoolResult(body);
    } else {
      loadCase();
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-white p-6">
        <div className="max-w-[1200px] mx-auto">
          <Link href="/research" className="text-[14px] text-[#808080] hover:text-[#171717] mb-4 inline-block">
            ← 返回列表
          </Link>
          <p className="text-[#808080]">加载中...</p>
        </div>
      </div>
    );
  }

  if (error || !researchCase) {
    return (
      <div className="min-h-screen bg-white p-6">
        <div className="max-w-[1200px] mx-auto">
          <Link href="/research" className="text-[14px] text-[#808080] hover:text-[#171717] mb-4 inline-block">
            ← 返回列表
          </Link>
          <p className="text-red-600">加载失败: {error || '未找到研究案例'}</p>
        </div>
      </div>
    );
  }

  const ro = researchCase.research_output;

  return (
    <div className="min-h-screen bg-white p-6">
      <div className="max-w-[1200px] mx-auto">
        <Link href="/research" className="text-[14px] text-[#808080] hover:text-[#171717] mb-4 inline-block">
          ← 返回列表
        </Link>

        <div className="border border-[#ebebeb] rounded-lg p-6">
          <div className="flex justify-between items-start mb-6">
            <div>
              <h1 className="text-[24px] font-semibold text-[#171717]">{researchCase.theme_name}</h1>
              <p className="text-[14px] text-[#808080] mt-2">ID: {researchCase.theme_id}</p>
            </div>
            <span className={`text-[14px] px-3 py-1 rounded ${
              researchCase.status === 'draft' ? 'bg-[#ebebeb] text-[#808080]' :
              researchCase.status === 'in_progress' ? 'bg-blue-50 text-blue-600' :
              'bg-green-50 text-green-600'
            }`}>
              {researchCase.status}
            </span>
          </div>

          <div className="space-y-6">
            <div>
              <h2 className="text-[14px] font-medium text-[#171717] mb-1">来源</h2>
              <p className="text-[14px] text-[#808080]">
                {researchCase.source_type === 'manual_stock' ? '朋友荐股' : researchCase.source_type}
              </p>
            </div>

            <div>
              <h2 className="text-[14px] font-medium text-[#171717] mb-1">背景</h2>
              <p className="text-[14px] text-[#808080]">{researchCase.background}</p>
            </div>

            {researchCase.notes && (
              <div>
                <h2 className="text-[14px] font-medium text-[#171717] mb-1">备注</h2>
                <p className="text-[14px] text-[#808080]">{researchCase.notes}</p>
              </div>
            )}

            {!serviceHealth?.is_healthy && (
              <div className="bg-yellow-50 border border-yellow-200 rounded p-4">
                <p className="text-[14px] text-yellow-900 font-medium">⚠️ 研究服务配置状态</p>
                <p className="text-[14px] text-yellow-800 mt-2">
                  需要配置真实研究服务（RESEARCH_CONVERSATION_MODE=real, SERENITY_EXECUTION_MODE=two_phase）才能运行研究。
                </p>
              </div>
            )}

            {/* V2: 用户产业链假设（待验证） */}
            <div className="border-t border-[#ebebeb] pt-4">
              <h2 className="text-[16px] font-semibold text-[#171717] mb-2">
                用户产业链假设（待验证）
              </h2>
              {hypSaved && researchCase.user_industry_chain_hypothesis ? (
                <pre className="text-[13px] text-[#171717] bg-[#f7f7f7] rounded p-3 overflow-auto whitespace-pre-wrap">
                  {pretty(researchCase.user_industry_chain_hypothesis)}
                </pre>
              ) : (
                <div className="space-y-2">
                  <textarea
                    className="w-full border border-[#ebebeb] rounded p-2 text-[13px] font-mono"
                    rows={4}
                    placeholder='{"upstream_entity":"某公司","relation_type":"supplier","scope_note":"待验证"}'
                    value={hypInput}
                    onChange={e => setHypInput(e.target.value)}
                  />
                  <button
                    className="text-[14px] px-3 py-1.5 rounded bg-[#171717] text-white hover:bg-black"
                    onClick={saveHypothesis}
                  >
                    保存假设（待验证，不作为已验证链）
                  </button>
                </div>
              )}
              <p className="text-[12px] text-[#808080] mt-2">
                该假设为待验证状态，不会被当作数据集、已验证产业链或回测 universe。
              </p>
            </div>

            {/* V2: 真实研究（LLM + Tushare） */}
            <div className="border-t border-[#ebebeb] pt-4">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-[16px] font-semibold text-[#171717]">
                  研究（真实 LLM + Tushare）
                </h2>
                <button
                  className="text-[14px] px-3 py-1.5 rounded border border-[#171717] text-[#171717] hover:bg-[#171717] hover:text-white disabled:opacity-40"
                  onClick={runResearch}
                  disabled={researching}
                >
                  {researching ? '研究中...' : (ro ? '重新运行研究' : '运行研究')}
                </button>
              </div>
              {researchError && <p className="text-[13px] text-red-600 mt-2">{researchError}</p>}
              {ro && (
                <div className="space-y-3 text-[14px] text-[#171717] mt-3">
                  <div className={`rounded p-3 ${ro.research_status === 'research_unavailable' ? 'bg-red-50 text-red-800' : 'bg-blue-50 text-blue-800'}`}>
                    <div className="font-medium">研究结论：{String(ro.research_verdict || ro.research_status || 'unknown')}</div>
                    {ro.research_status === 'research_unavailable' && (
                      <div className="mt-1">数据/服务不足，本次禁止形成交易决策。</div>
                    )}
                  </div>
                  {ro.demand_driver && (
                    <div><span className="font-medium">需求驱动：</span>{String(ro.demand_driver)}</div>
                  )}
                  {Array.isArray(ro.value_chain_layers) && ro.value_chain_layers.length > 0 && (
                    <div>
                      <span className="font-medium">价值链层级：</span>
                      <ul className="list-disc ml-5 text-[#808080]">
                        {ro.value_chain_layers.map((l: any, i: number) => (
                          <li key={i}>{pretty(l)}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {Array.isArray(ro.suspected_bottleneck_layers) && ro.suspected_bottleneck_layers.length > 0 && (
                    <div>
                      <span className="font-medium">疑似瓶颈：</span>
                      <ul className="list-disc ml-5 text-[#808080]">
                        {ro.suspected_bottleneck_layers.map((l: any, i: number) => (
                          <li key={i}>{pretty(l)}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {ro.candidate_rationales && typeof ro.candidate_rationales === 'object' && (
                    <div>
                      <span className="font-medium">支撑事实 / 反证：</span>
                      <div className="space-y-2 mt-1">
                        {Object.entries(ro.candidate_rationales).map(([sym, c]: any) => (
                          <div key={sym} className="bg-[#f7f7f7] rounded p-2">
                            <div className="text-[#171717] font-medium">{sym}</div>
                            <div className="text-[#808080]">论点：{(c as any).rationale}</div>
                            {Array.isArray((c as any).supporting_source_ids) && (c as any).supporting_source_ids.length > 0 && (
                              <div className="text-[#2563eb]">支持证据：{(c as any).supporting_source_ids.join('、')}</div>
                            )}
                            {Array.isArray((c as any).counter_evidence) && (c as any).counter_evidence.length > 0 && (
                              <div className="text-[#808080]">反证：{pretty((c as any).counter_evidence)}</div>
                            )}
                            {Array.isArray((c as any).falsification_questions) && (c as any).falsification_questions.length > 0 && (
                              <div className="text-[#b45309]">证伪条件：{(c as any).falsification_questions.join('；')}</div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {Array.isArray(ro.falsification_conditions) && ro.falsification_conditions.length > 0 && (
                    <div><span className="font-medium">证伪条件：</span>{ro.falsification_conditions.join('；')}</div>
                  )}
                  {Array.isArray(ro.supporting_evidence) && ro.supporting_evidence.length > 0 && (
                    <div><span className="font-medium">支持证据：</span>{ro.supporting_evidence.join('、')}</div>
                  )}
                  {Array.isArray(ro.counter_evidence) && ro.counter_evidence.length > 0 && (
                    <div><span className="font-medium">反证/风险：</span>{pretty(ro.counter_evidence)}</div>
                  )}
                  {Array.isArray(ro.evidence_gaps) && ro.evidence_gaps.length > 0 && (
                    <div>
                      <span className="font-medium">数据缺口：</span>
                      <ul className="list-disc ml-5 text-[#808080]">
                        {ro.evidence_gaps.map((g: any, i: number) => (
                          <li key={i}>{String(g)}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <ResearchSources sources={ro.research_sources} />
                </div>
              )}
            </div>

            {/* V2: 用户决策（continue/observe/stop） */}
            {ro && !poolResult && (
              <div className="border-t border-[#ebebeb] pt-4">
                <h2 className="text-[16px] font-semibold text-[#171717] mb-2">决策</h2>
                <div className="flex gap-3">
                  <button
                    className="text-[14px] px-4 py-2 rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-40"
                    onClick={() => decide('continue')}
                    disabled={deciding}
                  >
                    继续（continue）
                  </button>
                  <button
                    className="text-[14px] px-4 py-2 rounded border border-[#808080] text-[#171717] hover:bg-[#f7f7f7] disabled:opacity-40"
                    onClick={() => decide('observe')}
                    disabled={deciding}
                  >
                    观察（observe）
                  </button>
                  <button
                    className="text-[14px] px-4 py-2 rounded border border-red-300 text-red-600 hover:bg-red-50 disabled:opacity-40"
                    onClick={() => decide('stop')}
                    disabled={deciding}
                  >
                    停止（stop）
                  </button>
                </div>
                {decisionError && <p className="text-[13px] text-red-600 mt-2">{decisionError}</p>}
                {researchCase.approval_decision && researchCase.approval_decision !== 'continue' && (
                  <p className="text-[14px] text-[#808080] mt-2">
                    已记录决策：{researchCase.approval_decision}（未创建候选池）
                  </p>
                )}
              </div>
            )}

            {/* V2: 前向候选池（非买入信号 / 非历史回测 universe） */}
            {poolResult && (
              <div className="border-t border-[#ebebeb] pt-4">
                <h2 className="text-[16px] font-semibold text-[#171717] mb-2">前向候选池（Confirmed Candidate Pool）</h2>
                <div className="bg-[#f7f7f7] rounded p-4 space-y-2 text-[14px] text-[#171717]">
                  <div>Pool ID: {poolResult.pool_id}</div>
                  <div>Confirmed ID: {poolResult.confirmed_id}</div>
                  <div>标的：{poolResult.name}（{poolResult.ticker}）</div>
                  <div>决策：{poolResult.approval_decision} · 审批人：{poolResult.confirmed_by}</div>
                  <div>决策循环：{poolResult.decision_loop_id}</div>
                </div>
                <div className="mt-3 bg-[#fff7ed] border border-[#fde68a] rounded p-3 text-[13px] text-[#92400e]">
                  ⚠️ 该候选池为前向唯一的研究产出：<strong>不是买入信号</strong>，也<strong>不是历史回测 universe</strong>。
                  它仅可在某策略经独立验证达到 prototype_passed 后，供当前 Signal Board 生成使用。
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
