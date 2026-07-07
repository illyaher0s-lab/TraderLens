/**
 * Strategy Idea Detail Page
 * 
 * P3-3: Single strategy idea detail view
 * - Display full extraction/mapping/rejection chain
 * - Answer "Why was this strategy rejected?"
 * - Link back to list and Workbench
 */

"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

interface StrategyIdeaDetail {
  idea_id: string;
  conversation_id: string;
  workflow_type: string;
  original_message: string;
  agent_reply: string;
  extraction: {
    claimed_entry?: string;
    claimed_exit?: string;
    claimed_edge?: string;
  } | null;
  mapping: {
    path_type?: string;
    matched_template_id?: string | null;
    template_version?: string | null;
    mapping_reason?: string;
    live_eligible?: boolean;
  } | null;
  rejection: {
    rejection_reason?: string;
    rejected_at?: string;
  } | null;
  decision: "accepted" | "rejected";
  rejection_reason: string | null;
  path_type: string;
  mapping_reason: string | null;
  mapped_template_id: string | null;
  template_version: string | null;
  considered_template_ids: string[];
  mismatch_reasons: Record<string, string>;
  final_reason: string | null;
  live_eligible: boolean;
  candidate_status: string | null;
  candidate_reason: string | null;
  required_next_step: string | null;
  extraction_artifact_id: string | null;
  mapping_artifact_id: string | null;
  rejection_artifact_id: string | null;
  created_at: string;
}

export default function StrategyIdeaDetailPage() {
  const params = useParams();
  const ideaId = params.idea_id as string;
  
  const [idea, setIdea] = useState<StrategyIdeaDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";

  useEffect(() => {
    loadIdea();
  }, [ideaId]);

  const loadIdea = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const url = `${API_BASE_URL}/api/strategy-ideas/${ideaId}`;
      const response = await fetch(url);
      
      if (!response.ok) {
        throw new Error(`Failed to load idea: HTTP ${response.status}`);
      }
      
      const data = await response.json();
      setIdea(data);
    } catch (err) {
      console.error("Failed to load strategy idea:", err);
      setError(
        err instanceof Error 
          ? err.message 
          : "Unknown error"
      );
    } finally {
      setLoading(false);
    }
  };

  const getDecisionBadge = (decision: string) => {
    if (decision === "rejected") {
      return <span style={styles.badgeRed}>已拒绝</span>;
    }
    if (decision === "accepted") {
      return <span style={styles.badgeGreen}>已接受</span>;
    }
    return <span style={styles.badgeGray}>未知</span>;
  };

  const getRejectionReasonLabel = (reason: string | null) => {
    if (!reason) return "未知";
    if (reason === "no_approved_template") return "无批准模板";
    if (reason === "extraction_failed") return "提取失败";
    if (reason === "mapping_failed") return "映射失败";
    return reason;
  };

  const getPathTypeLabel = (pathType: string) => {
    if (pathType === "no_template_fit") return "无匹配模板";
    if (pathType === "approved_template_match") return "已批准模板";
    if (pathType === "candidate_evaluation") return "候选评估";
    return pathType;
  };

  if (loading) {
    return (
      <main style={styles.container}>
        <div style={styles.loadingText}>加载中...</div>
      </main>
    );
  }

  if (error || !idea) {
    return (
      <main style={styles.container}>
        <div style={styles.errorText}>
          加载失败: {error || "Idea not found"}
        </div>
        <Link href="/strategy-ideas" style={styles.backLink}>
          ← 返回列表
        </Link>
      </main>
    );
  }

  return (
    <main style={styles.container}>
      {/* Header */}
      <header style={styles.header}>
        <div>
          <h1 style={styles.title}>策略想法详情</h1>
          <p style={styles.subtitle}>
            完整的提取、映射和决策链路
          </p>
        </div>
        <div style={styles.headerActions}>
          <Link 
            href={`/strategy-ideas?conversation_id=${idea.conversation_id}`}
            style={styles.headerLink}
          >
            ← 返回列表
          </Link>
          <Link 
            href={`/workbench?conversation_id=${idea.conversation_id}`}
            style={styles.headerLink}
          >
            查看对话
          </Link>
        </div>
      </header>

      {/* Decision Badge */}
      <div style={styles.decisionSection}>
        {getDecisionBadge(idea.decision)}
        {idea.decision === "rejected" && idea.rejection_reason && (
          <span style={styles.rejectionReasonText}>
            原因: {getRejectionReasonLabel(idea.rejection_reason)}
          </span>
        )}
      </div>

      {/* Original Message */}
      <section style={styles.section}>
        <h2 style={styles.sectionTitle}>原始描述</h2>
        <div style={styles.card}>
          <p style={styles.messageText}>{idea.original_message}</p>
        </div>
      </section>

      {/* Agent Reply */}
      {idea.agent_reply && (
        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Agent 回复</h2>
          <div style={styles.card}>
            <p style={styles.messageText}>{idea.agent_reply}</p>
          </div>
        </section>
      )}

      {/* Extraction */}
      <section style={styles.section}>
        <h2 style={styles.sectionTitle}>
          提取结果
          {idea.extraction_artifact_id && (
            <span style={styles.artifactId}>
              {idea.extraction_artifact_id}
            </span>
          )}
        </h2>
        <div style={styles.card}>
          {idea.extraction ? (
            <div style={styles.detailGrid}>
              <div style={styles.detailRow}>
                <span style={styles.detailLabel}>入场条件</span>
                <span style={styles.detailValue}>
                  {idea.extraction.claimed_entry || "未提取"}
                </span>
              </div>
              <div style={styles.detailRow}>
                <span style={styles.detailLabel}>出场条件</span>
                <span style={styles.detailValue}>
                  {idea.extraction.claimed_exit || "未提取"}
                </span>
              </div>
              {idea.extraction.claimed_edge && (
                <div style={styles.detailRow}>
                  <span style={styles.detailLabel}>边界条件</span>
                  <span style={styles.detailValue}>
                    {idea.extraction.claimed_edge}
                  </span>
                </div>
              )}
            </div>
          ) : (
            <p style={styles.emptyText}>无提取结果</p>
          )}
        </div>
      </section>

      {/* Mapping */}
      <section style={styles.section}>
        <h2 style={styles.sectionTitle}>
          模板映射
          {idea.mapping_artifact_id && (
            <span style={styles.artifactId}>
              {idea.mapping_artifact_id}
            </span>
          )}
        </h2>
        <div style={styles.card}>
          {idea.mapping ? (
            <div style={styles.detailGrid}>
              <div style={styles.detailRow}>
                <span style={styles.detailLabel}>匹配路径</span>
                <span style={styles.detailValue}>
                  {getPathTypeLabel(idea.path_type)}
                </span>
              </div>
              <div style={styles.detailRow}>
                <span style={styles.detailLabel}>匹配模板</span>
                <span style={styles.detailValue}>
                  {idea.mapped_template_id ? (
                    <Link
                      href={`/strategy-templates/${idea.mapped_template_id}`}
                      className="text-blue-600 hover:text-blue-700 underline"
                    >
                      {idea.mapped_template_id}
                    </Link>
                  ) : (
                    <span className="text-gray-400">无匹配模板</span>
                  )}
                </span>
              </div>
              {idea.template_version && (
                <div style={styles.detailRow}>
                  <span style={styles.detailLabel}>模板版本</span>
                  <span style={styles.detailValue}>
                    {idea.template_version}
                  </span>
                </div>
              )}
              {idea.mapping_reason && (
                <div style={styles.detailRow}>
                  <span style={styles.detailLabel}>映射原因</span>
                  <span style={styles.detailValue}>
                    {idea.mapping_reason}
                  </span>
                </div>
              )}
              <div style={styles.detailRow}>
                <span style={styles.detailLabel}>Live 资格</span>
                <span style={styles.detailValue}>
                  {idea.live_eligible ? "是" : "否"}
                </span>
              </div>
              
              {/* Considered Templates */}
              {idea.considered_template_ids && idea.considered_template_ids.length > 0 && (
                <div style={styles.detailRow}>
                  <span style={styles.detailLabel}>已评估模板</span>
                  <span style={styles.detailValue}>
                    {idea.considered_template_ids.map((templateId, idx) => (
                      <span key={templateId}>
                        <Link
                          href={`/strategy-templates/${templateId}`}
                          className="text-blue-600 hover:text-blue-700 underline"
                        >
                          {templateId}
                        </Link>
                        {idx < idea.considered_template_ids.length - 1 && ", "}
                      </span>
                    ))}
                  </span>
                </div>
              )}
              
              {/* Mismatch Reasons */}
              {idea.mismatch_reasons && Object.keys(idea.mismatch_reasons).length > 0 && (
                <div style={{...styles.detailRow, flexDirection: "column", alignItems: "flex-start"}}>
                  <span style={styles.detailLabel}>不匹配原因</span>
                  <div style={{marginTop: "8px", width: "100%"}}>
                    {Object.entries(idea.mismatch_reasons).map(([templateId, reason]) => (
                      <div key={templateId} style={{marginBottom: "12px", paddingLeft: "16px"}}>
                        <div style={{fontWeight: 500, color: "#374151", marginBottom: "4px"}}>
                          <Link
                            href={`/strategy-templates/${templateId}`}
                            className="text-blue-600 hover:text-blue-700 underline"
                          >
                            {templateId}
                          </Link>
                        </div>
                        <div style={{color: "#6b7280", fontSize: "14px"}}>
                          {reason}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {/* Final Reason */}
              {idea.final_reason && (
                <div style={styles.detailRow}>
                  <span style={styles.detailLabel}>最终结论</span>
                  <span style={styles.detailValue}>
                    {idea.final_reason === "no_template_fit" && "无模板匹配"}
                    {idea.final_reason === "no_approved_template" && "无批准模板"}
                    {idea.final_reason !== "no_template_fit" && idea.final_reason !== "no_approved_template" && idea.final_reason}
                  </span>
                </div>
              )}
            </div>
          ) : (
            <p style={styles.emptyText}>无映射结果</p>
          )}
        </div>
      </section>

      {/* Rejection (if rejected) */}
      {idea.rejection && (
        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>
            拒绝详情
            {idea.rejection_artifact_id && (
              <span style={styles.artifactId}>
                {idea.rejection_artifact_id}
              </span>
            )}
          </h2>
          <div style={{...styles.card, borderLeft: "4px solid #ef4444"}}>
            <div style={styles.detailGrid}>
              <div style={styles.detailRow}>
                <span style={styles.detailLabel}>拒绝原因</span>
                <span style={styles.detailValue}>
                  {getRejectionReasonLabel(idea.rejection.rejection_reason || null)}
                </span>
              </div>
              {idea.rejection.rejected_at && (
                <div style={styles.detailRow}>
                  <span style={styles.detailLabel}>拒绝时间</span>
                  <span style={styles.detailValue}>
                    {new Date(idea.rejection.rejected_at).toLocaleString("zh-CN")}
                  </span>
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* Candidate Status (if candidate) */}
      {idea.candidate_status && (
        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>候选策略状态</h2>
          <div style={{...styles.card, borderLeft: "4px solid #f59e0b"}}>
            <div style={styles.detailGrid}>
              <div style={styles.detailRow}>
                <span style={styles.detailLabel}>候选状态</span>
                <span style={styles.detailValue}>
                  {idea.candidate_status === "candidate_unapproved" && "候选未批准"}
                  {idea.candidate_status !== "candidate_unapproved" && idea.candidate_status}
                </span>
              </div>
              <div style={styles.detailRow}>
                <span style={styles.detailLabel}>候选原因</span>
                <span style={styles.detailValue}>
                  {idea.candidate_reason === "no_approved_template_fit" && "无批准模板匹配"}
                  {idea.candidate_reason !== "no_approved_template_fit" && idea.candidate_reason}
                </span>
              </div>
              <div style={styles.detailRow}>
                <span style={styles.detailLabel}>需要的下一步</span>
                <span style={styles.detailValue}>
                  {idea.required_next_step === "template_approval_required" && "需要模板批准"}
                  {idea.required_next_step !== "template_approval_required" && idea.required_next_step}
                </span>
              </div>
              <div style={styles.detailRow}>
                <span style={styles.detailLabel}>Live 资格</span>
                <span style={styles.detailValue}>
                  {idea.live_eligible ? "是" : "否"}
                </span>
              </div>
            </div>
            
            <div style={{
              marginTop: "16px",
              padding: "12px",
              backgroundColor: "#fef3c7",
              border: "1px solid #fbbf24",
              borderRadius: "6px",
              fontSize: "14px",
              color: "#92400e",
              textAlign: "center" as const,
            }}>
              ⚠️ 此策略不可交易 / 不生成信号
            </div>
          </div>
        </section>
      )}

      {/* Metadata */}
      <section style={styles.section}>
        <h2 style={styles.sectionTitle}>元数据</h2>
        <div style={styles.card}>
          <div style={styles.detailGrid}>
            <div style={styles.detailRow}>
              <span style={styles.detailLabel}>Idea ID</span>
              <span style={styles.detailValue}>{idea.idea_id}</span>
            </div>
            <div style={styles.detailRow}>
              <span style={styles.detailLabel}>Conversation ID</span>
              <span style={styles.detailValue}>{idea.conversation_id}</span>
            </div>
            <div style={styles.detailRow}>
              <span style={styles.detailLabel}>Workflow Type</span>
              <span style={styles.detailValue}>{idea.workflow_type}</span>
            </div>
            <div style={styles.detailRow}>
              <span style={styles.detailLabel}>创建时间</span>
              <span style={styles.detailValue}>
                {new Date(idea.created_at).toLocaleString("zh-CN")}
              </span>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    maxWidth: "900px",
    margin: "0 auto",
    padding: "32px 24px",
    fontFamily: "system-ui, -apple-system, sans-serif",
  },
  loadingText: {
    textAlign: "center",
    padding: "48px",
    color: "#6b7280",
    fontSize: "16px",
  },
  errorText: {
    textAlign: "center",
    padding: "48px",
    color: "#ef4444",
    fontSize: "16px",
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
    margin: 0,
    fontSize: "32px",
    fontWeight: "700",
    color: "#111827",
  },
  subtitle: {
    margin: "8px 0 0 0",
    fontSize: "16px",
    color: "#6b7280",
  },
  headerActions: {
    display: "flex",
    gap: "16px",
  },
  headerLink: {
    fontSize: "14px",
    color: "#2563eb",
    textDecoration: "none",
    padding: "8px 16px",
    border: "1px solid #2563eb",
    borderRadius: "6px",
    transition: "all 0.2s",
  },
  backLink: {
    display: "inline-block",
    fontSize: "14px",
    color: "#2563eb",
    textDecoration: "none",
    padding: "8px 16px",
    border: "1px solid #2563eb",
    borderRadius: "6px",
    marginTop: "16px",
  },
  decisionSection: {
    display: "flex",
    alignItems: "center",
    gap: "16px",
    marginBottom: "32px",
    padding: "16px",
    backgroundColor: "#f9fafb",
    borderRadius: "8px",
  },
  badgeGreen: {
    display: "inline-block",
    padding: "6px 12px",
    fontSize: "14px",
    fontWeight: "600",
    color: "#065f46",
    backgroundColor: "#d1fae5",
    borderRadius: "6px",
  },
  badgeRed: {
    display: "inline-block",
    padding: "6px 12px",
    fontSize: "14px",
    fontWeight: "600",
    color: "#991b1b",
    backgroundColor: "#fee2e2",
    borderRadius: "6px",
  },
  badgeGray: {
    display: "inline-block",
    padding: "6px 12px",
    fontSize: "14px",
    fontWeight: "600",
    color: "#374151",
    backgroundColor: "#e5e7eb",
    borderRadius: "6px",
  },
  rejectionReasonText: {
    fontSize: "14px",
    color: "#991b1b",
    fontWeight: "500",
  },
  section: {
    marginBottom: "32px",
  },
  sectionTitle: {
    margin: "0 0 12px 0",
    fontSize: "20px",
    fontWeight: "600",
    color: "#111827",
    display: "flex",
    alignItems: "center",
    gap: "12px",
  },
  artifactId: {
    fontSize: "12px",
    fontWeight: "400",
    color: "#6b7280",
    fontFamily: "monospace",
  },
  card: {
    backgroundColor: "#ffffff",
    border: "1px solid #e5e7eb",
    borderRadius: "8px",
    padding: "20px",
  },
  messageText: {
    margin: 0,
    fontSize: "15px",
    lineHeight: "1.6",
    color: "#374151",
    whiteSpace: "pre-wrap",
  },
  detailGrid: {
    display: "flex",
    flexDirection: "column",
    gap: "16px",
  },
  detailRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: "16px",
  },
  detailLabel: {
    fontSize: "14px",
    fontWeight: "600",
    color: "#6b7280",
    minWidth: "120px",
  },
  detailValue: {
    fontSize: "14px",
    color: "#111827",
    flex: 1,
    textAlign: "right",
    wordBreak: "break-all",
  },
  emptyText: {
    margin: 0,
    fontSize: "14px",
    color: "#9ca3af",
    fontStyle: "italic",
  },
};
