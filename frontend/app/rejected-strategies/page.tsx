/**
 * Rejected Strategies Registry
 * 
 * P3-3: Registry of all rejected strategy ideas
 * - Display all rejected ideas
 * - Show rejection reason
 * - Link to detail page
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface RejectedIdea {
  idea_id: string;
  conversation_id: string;
  original_message: string;
  rejection_reason: string | null;
  path_type: string;
  created_at: string;
  claimed_entry?: string;
  claimed_exit?: string;
}

export default function RejectedStrategiesPage() {
  const [ideas, setIdeas] = useState<RejectedIdea[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";

  useEffect(() => {
    loadRejectedIdeas();
  }, []);

  const loadRejectedIdeas = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const url = `${API_BASE_URL}/api/strategy-ideas`;
      const response = await fetch(url);
      
      if (!response.ok) {
        throw new Error(`Failed to load ideas: HTTP ${response.status}`);
      }
      
      const data = await response.json();
      
      // Filter rejected ideas only
      const rejected = (data.ideas || []).filter(
        (idea: any) => idea.decision === "rejected"
      );
      
      setIdeas(rejected);
    } catch (err) {
      console.error("Failed to load rejected strategies:", err);
      setError(
        err instanceof Error 
          ? err.message 
          : "Unknown error"
      );
    } finally {
      setLoading(false);
    }
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
          <h1 style={styles.title}>策略拒绝注册表</h1>
          <p style={styles.subtitle}>
            所有被拒绝的策略想法及原因追踪
          </p>
        </div>
        <div style={styles.headerActions}>
          <Link href="/strategy-ideas" style={styles.headerLink}>
            所有策略
          </Link>
          <Link href="/" style={styles.headerLink}>
            返回首页
          </Link>
        </div>
      </header>

      {/* Empty State */}
      {ideas.length === 0 && (
        <div style={styles.emptyState}>
          <p style={styles.emptyTitle}>暂无被拒绝的策略</p>
          <p style={styles.emptyText}>
            所有提交的策略想法都已通过验证
          </p>
        </div>
      )}

      {/* Rejected Ideas Table */}
      {ideas.length > 0 && (
        <div style={styles.tableContainer}>
          <table style={styles.table}>
            <thead>
              <tr style={styles.tableHeaderRow}>
                <th style={{...styles.tableHeader, width: "40%"}}>原始描述</th>
                <th style={{...styles.tableHeader, width: "20%"}}>拒绝原因</th>
                <th style={{...styles.tableHeader, width: "15%"}}>匹配路径</th>
                <th style={{...styles.tableHeader, width: "15%"}}>创建时间</th>
                <th style={{...styles.tableHeader, width: "10%"}}>操作</th>
              </tr>
            </thead>
            <tbody>
              {ideas.map((idea) => (
                <tr key={idea.idea_id} style={styles.tableRow}>
                  <td style={styles.tableCell}>
                    <p style={styles.messagePreview}>
                      {idea.original_message.length > 100
                        ? idea.original_message.slice(0, 100) + "..."
                        : idea.original_message}
                    </p>
                    {(idea.claimed_entry || idea.claimed_exit) && (
                      <p style={styles.extractionHint}>
                        入场: {idea.claimed_entry || "未提取"} / 
                        出场: {idea.claimed_exit || "未提取"}
                      </p>
                    )}
                  </td>
                  <td style={styles.tableCell}>
                    <span style={styles.rejectionBadge}>
                      {getRejectionReasonLabel(idea.rejection_reason)}
                    </span>
                  </td>
                  <td style={styles.tableCell}>
                    {getPathTypeLabel(idea.path_type)}
                  </td>
                  <td style={styles.tableCell}>
                    {new Date(idea.created_at).toLocaleDateString("zh-CN")}
                  </td>
                  <td style={styles.tableCell}>
                    <Link 
                      href={`/strategy-ideas/${idea.idea_id}`}
                      style={styles.detailLink}
                    >
                      查看
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Summary */}
      {ideas.length > 0 && (
        <div style={styles.summary}>
          共 {ideas.length} 条被拒绝的策略想法
        </div>
      )}
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    maxWidth: "1200px",
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
    gap: "12px",
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
  emptyState: {
    textAlign: "center",
    padding: "64px 24px",
    backgroundColor: "#f9fafb",
    borderRadius: "8px",
  },
  emptyTitle: {
    margin: "0 0 8px 0",
    fontSize: "18px",
    fontWeight: "600",
    color: "#374151",
  },
  emptyText: {
    margin: 0,
    fontSize: "14px",
    color: "#6b7280",
  },
  tableContainer: {
    overflowX: "auto",
    backgroundColor: "#ffffff",
    border: "1px solid #e5e7eb",
    borderRadius: "8px",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
  },
  tableHeaderRow: {
    backgroundColor: "#f9fafb",
  },
  tableHeader: {
    padding: "12px 16px",
    textAlign: "left",
    fontSize: "13px",
    fontWeight: "600",
    color: "#374151",
    borderBottom: "2px solid #e5e7eb",
  },
  tableRow: {
    borderBottom: "1px solid #f3f4f6",
  },
  tableCell: {
    padding: "16px",
    fontSize: "14px",
    color: "#374151",
    verticalAlign: "top",
  },
  messagePreview: {
    margin: "0 0 4px 0",
    fontSize: "14px",
    lineHeight: "1.5",
    color: "#111827",
  },
  extractionHint: {
    margin: 0,
    fontSize: "12px",
    color: "#6b7280",
  },
  rejectionBadge: {
    display: "inline-block",
    padding: "4px 8px",
    fontSize: "12px",
    fontWeight: "500",
    color: "#991b1b",
    backgroundColor: "#fee2e2",
    borderRadius: "4px",
  },
  detailLink: {
    fontSize: "13px",
    color: "#2563eb",
    textDecoration: "none",
    fontWeight: "500",
  },
  summary: {
    marginTop: "24px",
    padding: "16px",
    textAlign: "center",
    fontSize: "14px",
    color: "#6b7280",
    backgroundColor: "#f9fafb",
    borderRadius: "8px",
  },
};
