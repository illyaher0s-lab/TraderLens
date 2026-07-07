/**
 * Candidate Strategies Registry
 * 
 * P3-6: Registry of candidate strategy ideas (no template fit but worth reviewing)
 * - Display all candidate_unapproved ideas
 * - Show why they can't go live
 * - Show what's needed next
 * - Link to detail page
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface CandidateIdea {
  idea_id: string;
  conversation_id: string;
  original_message: string;
  candidate_status: string | null;
  candidate_reason: string | null;
  final_reason: string | null;
  live_eligible: boolean;
  required_next_step: string | null;
  created_at: string;
}

export default function CandidateStrategiesPage() {
  const [ideas, setIdeas] = useState<CandidateIdea[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";

  useEffect(() => {
    loadCandidateIdeas();
  }, []);

  const loadCandidateIdeas = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const url = `${API_BASE_URL}/api/strategy-ideas?candidate_status=candidate_unapproved`;
      const response = await fetch(url);
      
      if (!response.ok) {
        throw new Error(`Failed to load ideas: HTTP ${response.status}`);
      }
      
      const data = await response.json();
      setIdeas(data.ideas || []);
    } catch (err) {
      console.error("Failed to load candidate strategies:", err);
      setError(
        err instanceof Error 
          ? err.message 
          : "Unknown error"
      );
    } finally {
      setLoading(false);
    }
  };

  const getCandidateStatusLabel = (status: string | null) => {
    if (!status) return "未知";
    if (status === "candidate_unapproved") return "候选未批准";
    return status;
  };

  const getRequiredNextStepLabel = (step: string | null) => {
    if (!step) return "未知";
    if (step === "template_approval_required") return "需要模板批准";
    return step;
  };

  if (loading) {
    return (
      <main style={styles.container}>
        <div style={styles.loadingText}>加载中...</div>
      </main>
    );
  }

  if (error) {
    return (
      <main style={styles.container}>
        <div style={styles.errorText}>加载失败: {error}</div>
      </main>
    );
  }

  return (
    <main style={styles.container}>
      {/* Header */}
      <header style={styles.header}>
        <div>
          <h1 style={styles.title}>候选策略注册表</h1>
          <p style={styles.subtitle}>
            无匹配模板但值得复查的策略想法（不可交易 / 不生成信号）
          </p>
        </div>
        <div style={styles.headerActions}>
          <Link href="/strategy-ideas" style={styles.headerLink}>
            所有策略 →
          </Link>
          <Link href="/rejected-strategies" style={styles.headerLink}>
            拒绝注册表 →
          </Link>
        </div>
      </header>

      {/* Ideas List */}
      {ideas.length === 0 ? (
        <div style={styles.emptyState}>
          <p style={styles.emptyText}>暂无候选策略</p>
          <p style={styles.emptyHint}>
            当策略想法无法匹配现有批准模板时，会出现在这里
          </p>
        </div>
      ) : (
        <div style={styles.listContainer}>
          {ideas.map((idea) => (
            <div key={idea.idea_id} style={styles.card}>
              <div style={styles.cardHeader}>
                <Link
                  href={`/strategy-ideas/${idea.idea_id}`}
                  style={styles.ideaIdLink}
                >
                  {idea.idea_id}
                </Link>
                <span style={styles.badge}>
                  {getCandidateStatusLabel(idea.candidate_status)}
                </span>
              </div>

              <div style={styles.cardBody}>
                <div style={styles.messageText}>
                  {idea.original_message}
                </div>

                <div style={styles.detailGrid}>
                  <div style={styles.detailRow}>
                    <span style={styles.detailLabel}>候选原因</span>
                    <span style={styles.detailValue}>
                      {idea.candidate_reason || "未知"}
                    </span>
                  </div>

                  <div style={styles.detailRow}>
                    <span style={styles.detailLabel}>最终原因</span>
                    <span style={styles.detailValue}>
                      {idea.final_reason === "no_template_fit" && "无模板匹配"}
                      {idea.final_reason === "no_approved_template" && "无批准模板"}
                      {idea.final_reason && 
                       idea.final_reason !== "no_template_fit" && 
                       idea.final_reason !== "no_approved_template" && 
                       idea.final_reason}
                    </span>
                  </div>

                  <div style={styles.detailRow}>
                    <span style={styles.detailLabel}>Live 资格</span>
                    <span style={styles.detailValue}>
                      {idea.live_eligible ? "是" : "否"}
                    </span>
                  </div>

                  <div style={styles.detailRow}>
                    <span style={styles.detailLabel}>需要的下一步</span>
                    <span style={styles.detailValue}>
                      {getRequiredNextStepLabel(idea.required_next_step)}
                    </span>
                  </div>
                </div>

                <div style={styles.warningBox}>
                  ⚠️ 此策略不可交易 / 不生成信号
                </div>
              </div>

              <div style={styles.cardFooter}>
                <Link
                  href={`/strategy-ideas/${idea.idea_id}`}
                  style={styles.detailLink}
                >
                  查看详情 →
                </Link>
                <span style={styles.timestamp}>
                  {new Date(idea.created_at).toLocaleString("zh-CN")}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
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
    gap: "16px",
  },
  headerLink: {
    fontSize: "14px",
    color: "#2563eb",
    textDecoration: "none",
    padding: "8px 16px",
    borderRadius: "6px",
    border: "1px solid #2563eb",
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
    borderRadius: "8px",
    border: "1px solid #e5e7eb",
  },
  emptyText: {
    fontSize: "18px",
    color: "#374151",
    fontWeight: "500",
    margin: "0 0 8px 0",
  },
  emptyHint: {
    fontSize: "14px",
    color: "#6b7280",
    margin: 0,
  },
  listContainer: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "24px",
  },
  card: {
    backgroundColor: "#ffffff",
    border: "1px solid #e5e7eb",
    borderRadius: "8px",
    padding: "24px",
    boxShadow: "0 1px 3px rgba(0, 0, 0, 0.1)",
  },
  cardHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "16px",
    paddingBottom: "12px",
    borderBottom: "1px solid #f3f4f6",
  },
  ideaIdLink: {
    fontSize: "14px",
    fontFamily: "monospace",
    color: "#2563eb",
    textDecoration: "none",
    fontWeight: "500",
  },
  badge: {
    fontSize: "12px",
    fontWeight: "500",
    padding: "4px 12px",
    borderRadius: "12px",
    backgroundColor: "#fef3c7",
    color: "#92400e",
  },
  cardBody: {
    marginBottom: "16px",
  },
  messageText: {
    fontSize: "14px",
    color: "#374151",
    lineHeight: "1.6",
    marginBottom: "16px",
    padding: "12px",
    backgroundColor: "#f9fafb",
    borderRadius: "6px",
    borderLeft: "3px solid #d1d5db",
  },
  detailGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "12px",
    marginBottom: "16px",
  },
  detailRow: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "4px",
  },
  detailLabel: {
    fontSize: "12px",
    fontWeight: "500",
    color: "#6b7280",
    textTransform: "uppercase" as const,
  },
  detailValue: {
    fontSize: "14px",
    color: "#111827",
  },
  warningBox: {
    fontSize: "14px",
    color: "#92400e",
    backgroundColor: "#fef3c7",
    padding: "12px",
    borderRadius: "6px",
    border: "1px solid #fbbf24",
    textAlign: "center" as const,
  },
  cardFooter: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    paddingTop: "12px",
    borderTop: "1px solid #f3f4f6",
  },
  detailLink: {
    fontSize: "14px",
    color: "#2563eb",
    textDecoration: "none",
    fontWeight: "500",
  },
  timestamp: {
    fontSize: "12px",
    color: "#9ca3af",
  },
};
