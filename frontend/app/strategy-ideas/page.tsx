/**
 * Strategy Ideas - List Page
 * 
 * P3-2 minimum viable scope:
 * - List strategy ideas from Workbench
 * - Show original message, extraction, decision (accepted/rejected)
 * - Display rejection reason
 * - Link to Workbench conversation
 */

"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

interface StrategyIdea {
  idea_id: string;
  conversation_id: string;
  original_message: string;
  claimed_entry: string;
  claimed_exit: string;
  decision: "accepted" | "rejected";
  path_type: string;
  created_at: string;
}

function StrategyIdeasContent() {
  const searchParams = useSearchParams();
  const conversationId = searchParams.get("conversation_id");
  
  const [ideas, setIdeas] = useState<StrategyIdea[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadIdeas();
  }, [conversationId]);

  const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";
  
  const loadIdeas = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const params = new URLSearchParams();
      if (conversationId) params.set("conversation_id", conversationId);
      
      const url = `${API_BASE_URL}/api/strategy-ideas?${params}`;
      const response = await fetch(url);
      
      if (!response.ok) {
        throw new Error(`API request failed: ${url} - HTTP ${response.status}`);
      }
      
      const data = await response.json();
      setIdeas(data.ideas || []);
    } catch (err) {
      console.error("Failed to load strategy ideas:", err);
      setError(
        err instanceof Error 
          ? `${err.message}. 请检查后端服务是否在 ${API_BASE_URL} 启动。`
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
          <h1 style={styles.title}>策略想法</h1>
          <p style={styles.subtitle}>
            {conversationId 
              ? "当前会话的策略想法" 
              : "所有提交的策略想法及评估结果"}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <Link href="/strategy-templates" style={styles.backLink}>
            模板库 →
          </Link>
          <Link href="/" style={styles.backLink}>
            ← 返回首页
          </Link>
        </div>
      </header>

      {/* Empty State */}
      {ideas.length === 0 && (
        <div style={styles.emptyState}>
          <p style={styles.emptyTitle}>暂无策略想法</p>
          <p style={styles.emptyText}>
            去 <Link href="/workbench" style={styles.emptyLink}>Workbench</Link> 输入：
          </p>
          <ul style={styles.emptyList}>
            <li>"我刷到一个策略，下午两点半买入，第二天卖出"</li>
            <li>"A股放量突破策略：突破20日高点且成交量超过2倍时买入"</li>
          </ul>
        </div>
      )}

      {/* Idea Cards */}
      {ideas.length > 0 && (
        <div style={styles.cardGrid}>
          {ideas.map((idea) => (
            <div key={idea.idea_id} style={styles.card}>
              {/* Header */}
              <div style={styles.cardHeader}>
                <div style={styles.cardHeaderLeft}>
                  <h3 style={styles.cardTitle}>策略想法</h3>
                  <p style={styles.cardMeta}>
                    {new Date(idea.created_at).toLocaleString("zh-CN")}
                  </p>
                </div>
                {getDecisionBadge(idea.decision)}
              </div>

              {/* Original Message */}
              <div style={styles.cardSection}>
                <p style={styles.cardSectionTitle}>原始描述</p>
                <p style={styles.cardText}>{idea.original_message}</p>
              </div>

              {/* Extraction */}
              <div style={styles.cardSection}>
                <p style={styles.cardSectionTitle}>提取结果</p>
                <div style={styles.cardDetails}>
                  <div style={styles.cardDetailRow}>
                    <span style={styles.cardLabel}>入场条件</span>
                    <span style={styles.cardValue}>{idea.claimed_entry}</span>
                  </div>
                  <div style={styles.cardDetailRow}>
                    <span style={styles.cardLabel}>出场条件</span>
                    <span style={styles.cardValue}>{idea.claimed_exit}</span>
                  </div>
                </div>
              </div>

              {/* Path Type */}
              <div style={styles.cardSection}>
                <div style={styles.cardDetailRow}>
                  <span style={styles.cardLabel}>模板匹配</span>
                  <span style={styles.cardValue}>{getPathTypeLabel(idea.path_type)}</span>
                </div>
              </div>

              {/* Footer Actions */}
              <div style={styles.cardFooter}>
                <span style={styles.cardFooterText}>
                  Idea ID: {idea.idea_id}
                </span>
                <div style={styles.cardFooterActions}>
                  <Link 
                    href={`/strategy-ideas/${idea.idea_id}`}
                    style={styles.cardFooterLink}
                  >
                    查看详情
                  </Link>
                  <Link 
                    href={`/workbench?conversation_id=${idea.conversation_id}`}
                    style={styles.cardFooterLink}
                  >
                    查看对话 →
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}

export default function StrategyIdeasPage() {
  return (
    <Suspense fallback={<div style={{ padding: "32px", textAlign: "center" }}>加载中...</div>}>
      <StrategyIdeasContent />
    </Suspense>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    maxWidth: "1200px",
    margin: "0 auto",
    padding: "32px 24px",
    fontFamily: "'Geist', -apple-system, BlinkMacSystemFont, sans-serif",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    paddingBottom: "24px",
    borderBottom: "1px solid rgba(0, 0, 0, 0.08)",
    marginBottom: "24px",
  },
  title: {
    fontSize: "32px",
    fontWeight: 600,
    letterSpacing: "-1.28px",
    color: "#171717",
    margin: 0,
  },
  subtitle: {
    fontSize: "16px",
    fontWeight: 400,
    color: "#666666",
    marginTop: "8px",
    marginBottom: 0,
  },
  backLink: {
    fontSize: "14px",
    fontWeight: 500,
    color: "#0072f5",
    textDecoration: "none",
  },
  loadingText: {
    fontSize: "16px",
    color: "#666666",
    textAlign: "center" as const,
    padding: "48px 0",
  },
  errorText: {
    fontSize: "16px",
    color: "#ff5b4f",
    textAlign: "center" as const,
    padding: "48px 0",
  },
  emptyState: {
    textAlign: "center" as const,
    padding: "64px 24px",
    background: "#fafafa",
    borderRadius: "8px",
    boxShadow: "rgba(0, 0, 0, 0.08) 0px 0px 0px 1px",
  },
  emptyTitle: {
    fontSize: "20px",
    fontWeight: 600,
    color: "#171717",
    marginBottom: "12px",
  },
  emptyText: {
    fontSize: "16px",
    color: "#666666",
    marginBottom: "16px",
  },
  emptyLink: {
    color: "#0072f5",
    textDecoration: "underline",
  },
  emptyList: {
    listStyle: "none",
    padding: 0,
    fontSize: "14px",
    color: "#808080",
    lineHeight: 1.8,
  },
  cardGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(400px, 1fr))",
    gap: "16px",
  },
  card: {
    background: "#ffffff",
    borderRadius: "8px",
    boxShadow:
      "rgba(0,0,0,0.08) 0px 0px 0px 1px, rgba(0,0,0,0.04) 0px 2px 2px, #fafafa 0px 0px 0px 1px",
    padding: "16px",
    transition: "box-shadow 0.2s",
  },
  cardHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: "16px",
  },
  cardHeaderLeft: {
    flex: 1,
  },
  cardTitle: {
    fontSize: "18px",
    fontWeight: 600,
    letterSpacing: "-0.32px",
    color: "#171717",
    margin: 0,
  },
  cardMeta: {
    fontSize: "12px",
    fontWeight: 400,
    color: "#808080",
    marginTop: "4px",
    marginBottom: 0,
  },
  cardSection: {
    marginBottom: "16px",
    paddingBottom: "16px",
    borderBottom: "1px solid rgba(0, 0, 0, 0.08)",
  },
  cardSectionTitle: {
    fontSize: "12px",
    fontWeight: 600,
    color: "#808080",
    textTransform: "uppercase" as const,
    letterSpacing: "0.5px",
    marginBottom: "8px",
  },
  cardText: {
    fontSize: "14px",
    fontWeight: 400,
    color: "#4d4d4d",
    lineHeight: 1.5,
    margin: 0,
  },
  cardDetails: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "8px",
  },
  cardDetailRow: {
    display: "flex",
    justifyContent: "space-between",
    gap: "16px",
  },
  cardLabel: {
    fontSize: "12px",
    fontWeight: 500,
    color: "#808080",
    flexShrink: 0,
  },
  cardValue: {
    fontSize: "12px",
    fontWeight: 600,
    color: "#171717",
    textAlign: "right" as const,
  },
  cardFooter: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    paddingTop: "12px",
  },
  cardFooterText: {
    fontSize: "10px",
    fontWeight: 400,
    color: "#808080",
  },
  cardFooterActions: {
    display: "flex",
    gap: "12px",
  },
  cardFooterLink: {
    fontSize: "12px",
    fontWeight: 500,
    color: "#0072f5",
    textDecoration: "none",
  },
  badgeGreen: {
    display: "inline-block",
    padding: "2px 8px",
    fontSize: "11px",
    fontWeight: 500,
    color: "#2e6b3d",
    background: "rgba(46, 160, 67, 0.1)",
    border: "1px solid rgba(46, 160, 67, 0.4)",
    borderRadius: "4px",
  },
  badgeRed: {
    display: "inline-block",
    padding: "2px 8px",
    fontSize: "11px",
    fontWeight: 500,
    color: "#e5484d",
    background: "rgba(229, 72, 77, 0.1)",
    border: "1px solid rgba(229, 72, 77, 0.4)",
    borderRadius: "4px",
  },
  badgeGray: {
    display: "inline-block",
    padding: "2px 8px",
    fontSize: "11px",
    fontWeight: 500,
    color: "#666666",
    background: "rgba(0, 0, 0, 0.05)",
    border: "1px solid rgba(0, 0, 0, 0.15)",
    borderRadius: "4px",
  },
};
