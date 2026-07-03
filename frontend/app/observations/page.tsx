/**
 * Observation Pool - List Page
 * 
 * Vercel design system (shadow-as-border, Geist font, minimal)
 * Shows stocks user observes/holds with latest daily signals
 * 
 * P2-1 minimum viable scope:
 * - List open/closed observation positions
 * - Show latest signal type + data state
 * - No fake hold when data insufficient
 * - Empty state with clear next action
 */

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

type MarketDataState = "ok" | "unavailable" | "partial" | "stale" | "inconsistent" | "source_error" | "adapter_unsupported";
type SignalType = "hold" | "sell" | "risk" | "invalidated";
type LifecycleState = "open" | "closed";

interface LatestSignal {
  signal_type: SignalType;
  as_of_date: string;
  market_data_state: MarketDataState;
  plain_explanation: string | null;
  triggered_invalidations: string[];
}

interface ObservationPosition {
  position_id: string;
  symbol: string;
  name: string;
  entry_price: number;
  quantity: number;
  entry_thesis: string;
  lifecycle_state: LifecycleState;
  opened_at: string;
  closed_at: string | null;
  template_id: string;
  latest_signal: LatestSignal | null;
}

export default function ObservationsPage() {
  const router = useRouter();
  const [positions, setPositions] = useState<ObservationPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("open");

  useEffect(() => {
    loadPositions();
  }, [statusFilter]);

  const loadPositions = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const params = new URLSearchParams();
      if (statusFilter !== "all") {
        params.set("status", statusFilter);
      }
      
      const response = await fetch(`http://localhost:8000/api/observations?${params}`);
      if (!response.ok) throw new Error("Failed to load observations");
      
      const data = await response.json();
      setPositions(data.positions || []);
    } catch (err) {
      console.error("Failed to load observations:", err);
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const getSignalBadge = (signal: LatestSignal | null) => {
    if (!signal) {
      return <span style={styles.badgeGray}>无信号</span>;
    }

    const { signal_type, market_data_state } = signal;

    // Data state takes precedence
    if (market_data_state === "unavailable" || market_data_state === "partial") {
      return <span style={styles.badgeOrange}>数据不足</span>;
    }
    if (market_data_state === "source_error" || market_data_state === "inconsistent") {
      return <span style={styles.badgeRed}>数据异常</span>;
    }

    // Business signal
    if (signal_type === "hold") {
      return <span style={styles.badgeGreen}>持有</span>;
    }
    if (signal_type === "sell") {
      return <span style={styles.badgeBlue}>卖出</span>;
    }
    if (signal_type === "risk") {
      return <span style={styles.badgeOrange}>风险</span>;
    }
    if (signal_type === "invalidated") {
      return <span style={styles.badgeGray}>失效</span>;
    }

    return <span style={styles.badgeGray}>未知</span>;
  };

  const getUserAction = (pos: ObservationPosition): string => {
    if (pos.lifecycle_state === "closed") {
      return "已关闭";
    }

    if (!pos.latest_signal) {
      return "等待生成信号";
    }

    const { signal_type, market_data_state } = pos.latest_signal;

    if (market_data_state === "unavailable" || market_data_state === "partial") {
      return "数据不足，建议暂停操作";
    }
    if (market_data_state === "source_error" || market_data_state === "inconsistent") {
      return "数据异常，建议暂停操作";
    }

    if (signal_type === "hold") {
      return "继续持有";
    }
    if (signal_type === "sell") {
      return "建议卖出";
    }
    if (signal_type === "risk") {
      return "注意风险";
    }
    if (signal_type === "invalidated") {
      return "论据失效";
    }

    return "查看详情";
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

  const openPositions = positions.filter(p => p.lifecycle_state === "open");
  const closedPositions = positions.filter(p => p.lifecycle_state === "closed");

  return (
    <main style={styles.container}>
      {/* Header */}
      <header style={styles.header}>
        <div>
          <h1 style={styles.title}>观察池</h1>
          <p style={styles.subtitle}>
            当前观察/持有的股票，以及今日需要做什么
          </p>
        </div>
        <Link href="/" style={styles.backLink}>
          ← 返回首页
        </Link>
      </header>

      {/* Filter Tabs */}
      <div style={styles.tabs}>
        <button
          onClick={() => setStatusFilter("open")}
          style={{
            ...styles.tab,
            ...(statusFilter === "open" ? styles.tabActive : {}),
          }}
        >
          开仓 ({openPositions.length})
        </button>
        <button
          onClick={() => setStatusFilter("closed")}
          style={{
            ...styles.tab,
            ...(statusFilter === "closed" ? styles.tabActive : {}),
          }}
        >
          已关闭 ({closedPositions.length})
        </button>
        <button
          onClick={() => setStatusFilter("all")}
          style={{
            ...styles.tab,
            ...(statusFilter === "all" ? styles.tabActive : {}),
          }}
        >
          全部 ({positions.length})
        </button>
      </div>

      {/* Empty State */}
      {positions.length === 0 && (
        <div style={styles.emptyState}>
          <p style={styles.emptyTitle}>暂无观察/持仓</p>
          <p style={styles.emptyText}>
            去 <Link href="/workbench" style={styles.emptyLink}>Workbench</Link> 输入：
          </p>
          <ul style={styles.emptyList}>
            <li>"朋友推荐了某某股票"</li>
            <li>"我已经买入 XX 股，成交价 XX 元"</li>
          </ul>
        </div>
      )}

      {/* Position Cards */}
      {positions.length > 0 && (
        <div style={styles.cardGrid}>
          {positions.map((pos) => (
            <div
              key={pos.position_id}
              style={styles.card}
              onClick={() => router.push(`/observations/${pos.position_id}`)}
            >
              {/* Header */}
              <div style={styles.cardHeader}>
                <div>
                  <h3 style={styles.cardTitle}>
                    {pos.name} ({pos.symbol})
                  </h3>
                  <p style={styles.cardMeta}>
                    {new Date(pos.opened_at).toLocaleDateString("zh-CN")} 开仓
                  </p>
                </div>
                {getSignalBadge(pos.latest_signal)}
              </div>

              {/* Thesis */}
              <p style={styles.cardThesis}>{pos.entry_thesis}</p>

              {/* Position Details */}
              <div style={styles.cardDetails}>
                <div style={styles.cardDetailRow}>
                  <span style={styles.cardLabel}>进入价格</span>
                  <span style={styles.cardValue}>¥{pos.entry_price.toFixed(2)}</span>
                </div>
                <div style={styles.cardDetailRow}>
                  <span style={styles.cardLabel}>数量</span>
                  <span style={styles.cardValue}>{pos.quantity} 股</span>
                </div>
              </div>

              {/* User Action */}
              <div style={styles.cardAction}>
                <span style={styles.cardActionLabel}>今日动作：</span>
                <span style={styles.cardActionValue}>{getUserAction(pos)}</span>
              </div>

              {/* Latest Signal Date */}
              {pos.latest_signal && (
                <p style={styles.cardSignalDate}>
                  信号日期: {new Date(pos.latest_signal.as_of_date).toLocaleDateString("zh-CN")}
                </p>
              )}
            </div>
          ))}
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
  tabs: {
    display: "flex",
    gap: "8px",
    marginBottom: "24px",
    borderBottom: "1px solid rgba(0, 0, 0, 0.08)",
    paddingBottom: "0",
  },
  tab: {
    padding: "8px 16px",
    fontSize: "14px",
    fontWeight: 500,
    color: "#666666",
    background: "transparent",
    border: "none",
    borderBottom: "2px solid transparent",
    cursor: "pointer",
    transition: "all 0.2s",
  },
  tabActive: {
    color: "#171717",
    borderBottomColor: "#171717",
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
    gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
    gap: "16px",
  },
  card: {
    background: "#ffffff",
    borderRadius: "8px",
    boxShadow:
      "rgba(0,0,0,0.08) 0px 0px 0px 1px, rgba(0,0,0,0.04) 0px 2px 2px, #fafafa 0px 0px 0px 1px",
    padding: "16px",
    cursor: "pointer",
    transition: "box-shadow 0.2s",
  },
  cardHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: "12px",
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
  cardThesis: {
    fontSize: "14px",
    fontWeight: 400,
    color: "#4d4d4d",
    lineHeight: 1.5,
    marginBottom: "12px",
    display: "-webkit-box",
    WebkitLineClamp: 2,
    WebkitBoxOrient: "vertical",
    overflow: "hidden",
  },
  cardDetails: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "8px",
    paddingTop: "12px",
    borderTop: "1px solid rgba(0, 0, 0, 0.08)",
    marginBottom: "12px",
  },
  cardDetailRow: {
    display: "flex",
    justifyContent: "space-between",
  },
  cardLabel: {
    fontSize: "12px",
    fontWeight: 500,
    color: "#808080",
  },
  cardValue: {
    fontSize: "12px",
    fontWeight: 600,
    color: "#171717",
  },
  cardAction: {
    display: "flex",
    gap: "8px",
    alignItems: "center",
    paddingTop: "12px",
    borderTop: "1px solid rgba(0, 0, 0, 0.08)",
  },
  cardActionLabel: {
    fontSize: "12px",
    fontWeight: 500,
    color: "#808080",
  },
  cardActionValue: {
    fontSize: "12px",
    fontWeight: 600,
    color: "#171717",
  },
  cardSignalDate: {
    fontSize: "10px",
    fontWeight: 400,
    color: "#808080",
    marginTop: "8px",
    marginBottom: 0,
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
  badgeBlue: {
    display: "inline-block",
    padding: "2px 8px",
    fontSize: "11px",
    fontWeight: 500,
    color: "#0068d6",
    background: "#ebf5ff",
    border: "1px solid #0068d6",
    borderRadius: "4px",
  },
  badgeOrange: {
    display: "inline-block",
    padding: "2px 8px",
    fontSize: "11px",
    fontWeight: 500,
    color: "#7a4a10",
    background: "rgba(224, 122, 48, 0.1)",
    border: "1px solid rgba(224, 122, 48, 0.4)",
    borderRadius: "4px",
  },
  badgeRed: {
    display: "inline-block",
    padding: "2px 8px",
    fontSize: "11px",
    fontWeight: 500,
    color: "#991b1b",
    background: "rgba(239, 68, 68, 0.1)",
    border: "1px solid rgba(239, 68, 68, 0.4)",
    borderRadius: "4px",
  },
  badgeGray: {
    display: "inline-block",
    padding: "2px 8px",
    fontSize: "11px",
    fontWeight: 500,
    color: "#555555",
    background: "rgba(100, 100, 100, 0.1)",
    border: "1px solid rgba(100, 100, 100, 0.4)",
    borderRadius: "4px",
  },
};
