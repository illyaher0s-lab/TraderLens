/**
 * Approved Strategy Library
 * 
 * P3-7: Shell page for approved strategy library (currently empty)
 * - Display empty state (no approved strategies yet)
 * - Explain difference between strategies, candidates, templates
 * - Link to related pages
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface StrategyLibraryResponse {
  strategies: any[];
  count: number;
}

export default function StrategiesPage() {
  const [data, setData] = useState<StrategyLibraryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";

  useEffect(() => {
    loadStrategies();
  }, []);

  const loadStrategies = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const url = `${API_BASE_URL}/api/strategies`;
      const response = await fetch(url);
      
      if (!response.ok) {
        throw new Error(`Failed to load strategies: HTTP ${response.status}`);
      }
      
      const responseData = await response.json();
      setData(responseData);
    } catch (err) {
      console.error("Failed to load strategies:", err);
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
          <h1 style={styles.title}>已批准策略库</h1>
          <p style={styles.subtitle}>
            可交易的生产环境策略（当前为空）
          </p>
        </div>
      </header>

      {/* Empty State */}
      <div style={styles.emptyState}>
        <div style={styles.emptyIcon}>📋</div>
        <h2 style={styles.emptyTitle}>当前没有已批准策略</h2>
        <p style={styles.emptyText}>
          已批准策略是经过完整验证、可用于实盘交易的策略。
        </p>
        <p style={styles.emptyText}>
          策略数量: <strong>{data?.count || 0}</strong>
        </p>
        
        <div style={styles.infoBox}>
          <h3 style={styles.infoTitle}>什么可以成为已批准策略？</h3>
          <ul style={styles.infoList}>
            <li>策略想法 (Strategy Ideas) 提交后会被评估</li>
            <li>如果无法匹配已批准模板，会成为候选策略 (Candidate)</li>
            <li>如果完全不符合要求，会进入拒绝注册表 (Rejected)</li>
            <li>只有通过模板匹配和完整验证的策略才能进入此库</li>
          </ul>
        </div>

        <div style={styles.warningBox}>
          ⚠️ 候选策略和拒绝的想法不会出现在此页面
        </div>
      </div>

      {/* Navigation Links */}
      <section style={styles.linksSection}>
        <h3 style={styles.linksTitle}>相关页面</h3>
        <div style={styles.linksGrid}>
          <Link href="/strategy-ideas" style={styles.linkCard}>
            <div style={styles.linkIcon}>💡</div>
            <div style={styles.linkContent}>
              <div style={styles.linkLabel}>策略想法</div>
              <div style={styles.linkDesc}>所有提交的策略想法</div>
            </div>
          </Link>

          <Link href="/candidate-strategies" style={styles.linkCard}>
            <div style={styles.linkIcon}>🔍</div>
            <div style={styles.linkContent}>
              <div style={styles.linkLabel}>候选策略</div>
              <div style={styles.linkDesc}>无匹配模板但值得复查</div>
            </div>
          </Link>

          <Link href="/rejected-strategies" style={styles.linkCard}>
            <div style={styles.linkIcon}>❌</div>
            <div style={styles.linkContent}>
              <div style={styles.linkLabel}>拒绝注册表</div>
              <div style={styles.linkDesc}>被拒绝的策略想法</div>
            </div>
          </Link>

          <Link href="/strategy-templates" style={styles.linkCard}>
            <div style={styles.linkIcon}>📐</div>
            <div style={styles.linkContent}>
              <div style={styles.linkLabel}>策略模板</div>
              <div style={styles.linkDesc}>已批准的策略模板库</div>
            </div>
          </Link>
        </div>
      </section>
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
    color: "#92400e",
    backgroundColor: "#fef3c7",
    padding: "12px 24px",
    borderRadius: "6px",
    border: "1px solid #fbbf24",
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
