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

interface ValidationResponse {
  validations: any[];
  count: number;
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
          <h1 style={styles.title}>策略验证</h1>
          <p style={styles.subtitle}>
            通过模板匹配的策略验证案例（当前为空）
          </p>
        </div>
        <div style={styles.headerActions}>
          <Link href="/strategies" style={styles.headerLink}>
            ← 返回策略工作区
          </Link>
        </div>
      </header>

      {/* Empty State */}
      <div style={styles.emptyState}>
        <div style={styles.emptyIcon}>🔬</div>
        <h2 style={styles.emptyTitle}>当前没有策略验证案例</h2>
        <p style={styles.emptyText}>
          验证案例数量: <strong>{data?.count || 0}</strong>
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
          ℹ️ 当前没有策略通过模板匹配进入验证阶段
        </div>
      </div>

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
