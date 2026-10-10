/**
 * Workbench Timeline - P1-3 活动流可读化
 * 
 * 基于 timeline artifacts 显示每步，中文白话主文案
 */

"use client";

import { useState } from "react";
import ResearchSources from "@/components/ResearchSources";

interface TimelineItem {
  type: string;
  content: any;
}

interface WorkbenchTimelineProps {
  timeline: TimelineItem[];
}

const artifactLabels: Record<string, string> = {
  'context_loaded': '读取上下文',
  'prescan_result': '预扫描',
  'intent_extraction': '理解意图',
  'stock_identity_resolution': '核验股票',
  'workflow_route_decision': '决定流程',
  'market_scan_result': 'Market scan',
  'workflow_action_started': '开始处理',
  'friend_stock_flow': '创建研究记录',
  'research_case': '研究案例',
  'research_result': '研究结果',
  'strategy_idea': '记录策略想法',
  'strategy_idea_extraction': '提取策略条件',
  'strategy_template_mapping': '匹配策略模板',
  'strategy_idea_rejected': '拒绝策略',
  'workflow_action_completed': '处理完成',
  'workflow_action_failed': '处理失败',
  'user_message': '用户消息',
  'agent_message': '代理回复',
  'approval_card': '等待审批',
  'workflow_intent': '工作流意图',
};

function getArtifactLabel(artifactType: string): string {
  return artifactLabels[artifactType] || artifactType;
}

function getArtifactDescription(item: TimelineItem): string | null {
  const artifactType = item.content.artifact_type;
  const artifactContent = item.content.artifact_content;
  
  if (!artifactContent) return null;
  
  try {
    const data = JSON.parse(artifactContent);
    
    if (artifactType === 'context_loaded') {
      // Show what context was loaded
      if (data.claimed_stock) {
        return `读取到上一轮股票：${data.claimed_stock.company_name || data.claimed_stock.ticker || '未知'}`;
      }
      return '读取会话上下文（无已知股票）';
    }
    
    if (artifactType === 'workflow_route_decision') {
      return data.route_reason || null;
    }

    if (artifactType === 'market_scan_result') {
      if (data.status === 'hard_block') return `Market scan blocked: ${data.reason || 'unknown'}`;
      return `Data date ${data.as_of_date || 'unknown'} · ${data.machine_candidate_count ?? data.candidate_count ?? 0} machine candidates · ${data.display_candidate_count ?? data.candidates?.length ?? 0} cards · candidate_is_signal=false`;
    }
    
    if (artifactType === 'stock_identity_resolution') {
      if (data.status === 'verified') {
        return `核验通过：${data.company_name} (${data.ticker})`;
      }
      return data.fault_reason || '核验失败';
    }

    if (artifactType === 'research_case') {
      return `研究案例：${data.theme_name || item.content.artifact_id}`;
    }

    if (artifactType === 'research_result') {
      const verdict = data.research_verdict || data.research_status || 'unknown';
      const ticker = data.ticker || 'unknown';
      return `${ticker} · 研究结论：${verdict}`;
    }
    
    if (artifactType === 'strategy_idea_extraction') {
      return `入场：${data.claimed_entry}，出场：${data.claimed_exit}`;
    }
    
    if (artifactType === 'strategy_template_mapping') {
      return data.mapping_reason || null;
    }
    
    if (artifactType === 'strategy_idea_rejected') {
      return data.rejection_reason || '策略不符合要求';
    }
  } catch (e) {
    console.error('Failed to parse artifact content:', e);
  }
  
  return null;
}

function getMarketScanCards(item: TimelineItem): any[] {
  if (item.content.artifact_type !== 'market_scan_result' || !item.content.artifact_content) return [];
  try {
    const data = JSON.parse(item.content.artifact_content);
    return Array.isArray(data.candidates) ? data.candidates.slice(0, 5) : [];
  } catch {
    return [];
  }
}

function getResearchResult(item: TimelineItem): any | null {
  if (item.content.artifact_type !== 'research_result' || !item.content.artifact_content) return null;
  try {
    return JSON.parse(item.content.artifact_content);
  } catch {
    return null;
  }
}

export default function WorkbenchTimeline({ timeline }: WorkbenchTimelineProps) {
  const [expandedItems, setExpandedItems] = useState<Set<number>>(new Set());
  
  const toggleExpand = (index: number) => {
    const newExpanded = new Set(expandedItems);
    if (newExpanded.has(index)) {
      newExpanded.delete(index);
    } else {
      newExpanded.add(index);
    }
    setExpandedItems(newExpanded);
  };
  
  // Filter to show only artifact_refs and messages
  const displayItems = timeline.filter(t => 
    t.type === 'artifact_ref' || t.type === 'message'
  );
  
  return (
    <div 
      className="bg-white rounded-lg p-4"
      style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}
    >
      <h3 className="text-[14px] font-medium text-[#171717] mb-3">活动流</h3>
      
      <div className="space-y-2 max-h-[400px] overflow-y-auto">
        {displayItems.length === 0 ? (
          <div className="text-[13px] text-[#999999]">暂无活动</div>
        ) : (
          displayItems.map((item, index) => {
            const isExpanded = expandedItems.has(index);
            const isFailed = item.type === 'artifact_ref' && 
              (item.content.artifact_type?.includes('failed') || 
               item.content.artifact_type === 'strategy_idea_rejected');
            
            if (item.type === 'message') {
              // Skip messages in timeline (they're shown in chat)
              return null;
            }
            
            const label = getArtifactLabel(item.content.artifact_type);
            const description = getArtifactDescription(item);
            const marketCards = getMarketScanCards(item);
            const researchResult = getResearchResult(item);
            
            return (
              <div key={index} className="border-l-2 border-[#ebebeb] pl-3 py-1">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1">
                    <div className={`text-[13px] font-medium ${isFailed ? 'text-[#ef4444]' : 'text-[#171717]'}`}>
                      {label}
                    </div>
                    {description && (
                      <div className="text-[12px] text-[#666666] mt-0.5">
                        {description}
                      </div>
                    )}
                    {marketCards.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {marketCards.map((card) => (
                          <div key={card.symbol} className="rounded border border-[#ebebeb] bg-[#fafafa] p-2 text-[11px]">
                            <div className="font-medium text-[#171717]">{card.symbol} · {card.status === 'watch' ? 'watch' : '待研究'}</div>
                            <div className="text-[#666666]">原因：{(card.reasons || []).join('、') || '待研究'}</div>
                            <div className="text-[#2563eb]">support: {card.support?.source || 'unknown'} · {card.support?.fact_date || 'unknown'}</div>
                            <div className="text-[#b91c1c]">counter: {card.counter?.source || 'unknown'} · {card.counter?.fact_date || 'unknown'}</div>
                            <div className="text-[#666666]">unknown: {[...(card.support?.unknown || []), ...(card.counter?.unknown || [])].join('; ') || 'none'}</div>
                            <div className="text-[#666666]">scenarios: {JSON.stringify(card.support?.scenarios || { bull: 'unknown', base: 'unknown', bear: 'unknown' })}</div>
                            <div className="text-[#666666]">confidence: {card.support?.confidence || 'unknown'} / {card.counter?.confidence || 'unknown'}</div>
                            {(card.soft_risks || []).length > 0 && (
                              <div className="text-[#b45309]">软风险：{card.soft_risks.join('、')}</div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                    {researchResult && (
                      <div className="mt-2 rounded border border-[#ebebeb] bg-[#fafafa] p-2 text-[11px] space-y-1">
                        <div className="font-medium">结论：{researchResult.research_verdict || researchResult.research_status || 'unknown'}</div>
                        {researchResult.research_reason && <div>研究理由：{String(researchResult.research_reason)}</div>}
                        {researchResult.demand_driver && <div>核心逻辑：{String(researchResult.demand_driver)}</div>}
                        {Array.isArray(researchResult.supporting_evidence) && researchResult.supporting_evidence.length > 0 && (
                          <div className="text-[#2563eb]">支持证据：{researchResult.supporting_evidence.join('、')}</div>
                        )}
                        {Array.isArray(researchResult.counter_evidence) && researchResult.counter_evidence.length > 0 && (
                          <div className="text-[#b91c1c]">反证/风险：{JSON.stringify(researchResult.counter_evidence)}</div>
                        )}
                        {Array.isArray(researchResult.falsification_conditions) && researchResult.falsification_conditions.length > 0 && (
                          <div>证伪条件：{researchResult.falsification_conditions.join('；')}</div>
                        )}
                        {Array.isArray(researchResult.invalidation_conditions) && researchResult.invalidation_conditions.length > 0 && (
                          <div>失效条件：{researchResult.invalidation_conditions.join('；')}</div>
                        )}
                        {Array.isArray(researchResult.evidence_gaps) && researchResult.evidence_gaps.length > 0 && (
                          <div className="text-[#b45309]">证据缺口：{researchResult.evidence_gaps.join('；')}</div>
                        )}
                        <ResearchSources sources={researchResult.research_sources} compact />
                        {researchResult.research_status === 'research_unavailable' && (
                          <div className="font-medium text-[#b91c1c]">数据/服务不足，本次禁止形成交易决策。</div>
                        )}
                      </div>
                    )}
                  </div>
                  
                  <button
                    onClick={() => toggleExpand(index)}
                    className="text-[11px] text-[#999999] hover:text-[#171717] transition-colors"
                  >
                    {isExpanded ? '收起' : '详情'}
                  </button>
                </div>
                
                {isExpanded && (
                  <div className="mt-2 text-[11px] text-[#999999] bg-[#fafafa] p-2 rounded">
                    <div className="mb-1">
                      <span className="font-medium">ID:</span> {item.content.artifact_id}
                    </div>
                    <div className="mb-1">
                      <span className="font-medium">类型:</span> {item.content.artifact_type}
                    </div>
                    {item.content.artifact_content && (
                      <details className="mt-1">
                        <summary className="cursor-pointer font-medium">原始数据</summary>
                        <pre className="mt-1 text-[10px] overflow-x-auto">
                          {JSON.stringify(JSON.parse(item.content.artifact_content), null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
