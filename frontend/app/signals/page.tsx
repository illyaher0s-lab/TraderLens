/**
 * Signal Board - List Page (v0.1 UI Layout)
 * 
 * Vercel-inspired design system
 * Internal tool: clean, table-based, review-focused
 * 
 * Hard constraints:
 * - No charts
 * - No real-time refresh
 * - No keyboard shortcuts (M4 v0)
 * - Display planned_action with neutral labels
 * - All data from Signal Board API
 */

"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  listSignals,
  listStrategies,
  reviewSignal,
  type PlannedSignal,
  type SignalReviewRequest,
  type StrategyInfo,
} from "@/lib/api-client";

const PAGE_SIZE = 50;

export default function SignalsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  
  const [signals, setSignals] = useState<PlannedSignal[]>([]);
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [totalSignals, setTotalSignals] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [reviewingSignalId, setReviewingSignalId] = useState<string | null>(null);
  const [ignoreSignalId, setIgnoreSignalId] = useState<string | null>(null);
  const [ignoreReason, setIgnoreReason] = useState("");

  // Filters - read from URL query params
  const [statusFilter, setStatusFilter] = useState<string>(searchParams.get("status") || "all");
  const [actionFilter, setActionFilter] = useState<string>(searchParams.get("action") || "all");
  const [strategyIdFilter, setStrategyIdFilter] = useState<string>(searchParams.get("strategy_id") || "all");
  const [strategyVersionFilter, setStrategyVersionFilter] = useState<string>(searchParams.get("strategy_version") || "all");
  const [signalDateFilter, setSignalDateFilter] = useState<string>(searchParams.get("signal_date") || "");

  useEffect(() => {
    loadStrategies();
  }, []);

  useEffect(() => {
    loadSignals(true);
  }, [statusFilter, strategyIdFilter, strategyVersionFilter, signalDateFilter]);

  const loadStrategies = async () => {
    try {
      const data = await listStrategies();
      setStrategies(data);
    } catch (err) {
      console.error("Failed to load strategies:", err);
    }
  };

  const buildSignalParams = (offset: number) => {
    const params: any = { limit: PAGE_SIZE, offset };

    if (statusFilter !== "all") {
      params.status = statusFilter;
    }

    if (strategyIdFilter !== "all") {
      params.strategy_id = strategyIdFilter;
    }

    if (strategyVersionFilter !== "all") {
      params.strategy_version = strategyVersionFilter;
    }

    if (signalDateFilter) {
      params.signal_date = signalDateFilter;
    }

    return params;
  };

  const loadSignals = async (reset = true) => {
    try {
      if (reset) {
        setLoading(true);
      } else {
        setLoadingMore(true);
      }
      setError(null);

      const offset = reset ? 0 : signals.length;
      const data = await listSignals(buildSignalParams(offset));
      setSignals((current) => reset ? data.items : [...current, ...data.items]);
      setTotalSignals(data.total);
      setHasMore(data.has_more);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载信号失败");
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  const updateURLParams = (updates: Record<string, string>) => {
    const params = new URLSearchParams(searchParams.toString());
    Object.entries(updates).forEach(([key, value]) => {
      if (value === "all" || value === "") {
        params.delete(key);
      } else {
        params.set(key, value);
      }
    });
    const query = params.toString();
    router.push(query ? `/signals?${query}` : "/signals", { scroll: false });
  };

  const handleStrategyIdChange = (value: string) => {
    setStrategyIdFilter(value);

    if (value !== strategyIdFilter) {
      setStrategyVersionFilter("all");
    }
    updateURLParams({ strategy_id: value, strategy_version: "all" });
  };

  const handleStrategyVersionChange = (value: string) => {
    setStrategyVersionFilter(value);
    updateURLParams({ strategy_version: value });
  };

  const handleStatusChange = (value: string) => {
    setStatusFilter(value);
    updateURLParams({ status: value });
  };

  const handleActionChange = (value: string) => {
    setActionFilter(value);
    updateURLParams({ action: value });
  };

  const handleSignalDateChange = (value: string) => {
    setSignalDateFilter(value);
    updateURLParams({ signal_date: value });
  };

  const handleClearFilters = () => {
    setStatusFilter("all");
    setActionFilter("all");
    setStrategyIdFilter("all");
    setStrategyVersionFilter("all");
    setSignalDateFilter("");
    router.push("/signals");
  };

  const applySignalUpdate = (updatedSignal: PlannedSignal) => {
    const shouldRemoveFromFilteredPage =
      statusFilter !== "all" && updatedSignal.review_status !== statusFilter;

    setSignals((current) =>
      current.flatMap((signal) => {
        if (signal.signal_id !== updatedSignal.signal_id) {
          return [signal];
        }
        return shouldRemoveFromFilteredPage ? [] : [updatedSignal];
      })
    );

    if (shouldRemoveFromFilteredPage) {
      setTotalSignals((current) => Math.max(0, current - 1));
    }
  };

  const handleQuickReview = async (
    signal: PlannedSignal,
    reviewStatus: SignalReviewRequest["review_status"],
    rejectionReason?: string
  ) => {
    const trimmedReason = rejectionReason?.trim();
    if (reviewStatus === "ignored" && !trimmedReason) {
      setError("请填写忽略原因");
      return;
    }

    try {
      setError(null);
      setReviewingSignalId(signal.signal_id);
      const updatedSignal = await reviewSignal(signal.signal_id, {
        review_status: reviewStatus,
        reviewed_by: "local_user",
        rejection_reason: reviewStatus === "ignored" ? trimmedReason : undefined,
      });
      applySignalUpdate(updatedSignal);
      setIgnoreSignalId(null);
      setIgnoreReason("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "审核提交失败");
    } finally {
      setReviewingSignalId(null);
    }
  };

  const uniqueStrategyIds = Array.from(new Set(strategies.map(s => s.strategy_id)));
  
  const availableVersions = strategyIdFilter === "all" 
    ? strategies 
    : strategies.filter(s => s.strategy_id === strategyIdFilter);

  const filteredSignals = signals.filter((signal) => {
    if (actionFilter !== "all" && signal.planned_action !== actionFilter) {
      return false;
    }
    return true;
  });

  const statusCounts = {
    pending: filteredSignals.filter(s => s.review_status === "pending").length,
    watching: filteredSignals.filter(s => s.review_status === "watching").length,
    ignored: filteredSignals.filter(s => s.review_status === "ignored").length,
    expired: filteredSignals.filter(s => s.review_status === "expired").length,
  };

  const getStatusBadgeClass = (status: string) => {
    const baseClass = "px-2 py-0.5 text-xs font-medium rounded-md";
    switch (status) {
      case "pending":
        return `${baseClass} bg-blue-50 text-blue-700`;
      case "watching":
        return `${baseClass} bg-green-50 text-green-700`;
      case "ignored":
        return `${baseClass} bg-gray-100 text-gray-600`;
      case "expired":
        return `${baseClass} bg-red-50 text-red-600`;
      default:
        return `${baseClass} bg-gray-100 text-gray-600`;
    }
  };

  const getActionBadgeClass = (action: string) => {
    const baseClass = "px-2 py-0.5 text-xs font-medium rounded-md";
    return action === "enter"
      ? `${baseClass} bg-emerald-50 text-emerald-700`
      : `${baseClass} bg-orange-50 text-orange-700`;
  };

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      pending: "待处理",
      watching: "观察中",
      ignored: "已忽略",
      expired: "已过期",
    };
    return labels[status] || status;
  };

  return (
    <div className="min-h-screen bg-white">
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Page Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-semibold text-[#171717] tracking-tight">
            Signal Board
          </h1>
          <p className="text-sm text-[#666666] mt-2">
            查看策略生成的计划信号，并进行人工审核
          </p>
          <p className="text-xs text-[#808080] mt-1">
            数据来源：Strategy Core｜不包含实时行情｜不做自动执行
          </p>
        </div>

        {/* Filter Bar */}
        <div className="bg-white border border-[#ebebeb] rounded-lg p-4 mb-6">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {/* Strategy Filter */}
            <div>
              <label htmlFor="strategy-filter" className="block text-xs font-medium text-[#4d4d4d] mb-1.5">
                策略
              </label>
              <select
                id="strategy-filter"
                value={strategyIdFilter}
                onChange={(e) => handleStrategyIdChange(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-[#ebebeb] rounded-md bg-white text-[#171717] focus:outline-none focus:ring-2 focus:ring-[#0072f5] focus:border-transparent"
              >
                <option value="all">全部策略</option>
                {uniqueStrategyIds.map((strategyId) => (
                  <option key={strategyId} value={strategyId}>
                    {strategyId}
                  </option>
                ))}
              </select>
            </div>

            {/* Version Filter */}
            <div>
              <label htmlFor="version-filter" className="block text-xs font-medium text-[#4d4d4d] mb-1.5">
                版本
              </label>
              <select
                id="version-filter"
                value={strategyVersionFilter}
                onChange={(e) => handleStrategyVersionChange(e.target.value)}
                disabled={strategyIdFilter === "all"}
                className="w-full px-3 py-2 text-sm border border-[#ebebeb] rounded-md bg-white text-[#171717] focus:outline-none focus:ring-2 focus:ring-[#0072f5] focus:border-transparent disabled:bg-[#fafafa] disabled:text-[#808080] disabled:cursor-not-allowed"
              >
                <option value="all">全部版本</option>
                {availableVersions.map((strategy) => (
                  <option key={`${strategy.strategy_id}-${strategy.strategy_version}`} value={strategy.strategy_version}>
                    {strategy.strategy_version} ({strategy.signal_count})
                  </option>
                ))}
              </select>
            </div>

            {/* Status Filter */}
            <div>
              <label htmlFor="status-filter" className="block text-xs font-medium text-[#4d4d4d] mb-1.5">
                状态
              </label>
              <select
                id="status-filter"
                value={statusFilter}
                onChange={(e) => handleStatusChange(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-[#ebebeb] rounded-md bg-white text-[#171717] focus:outline-none focus:ring-2 focus:ring-[#0072f5] focus:border-transparent"
              >
                <option value="all">全部</option>
                <option value="pending">待处理</option>
                <option value="watching">观察中</option>
                <option value="ignored">已忽略</option>
                <option value="expired">已过期</option>
              </select>
            </div>

            {/* Action Filter */}
            <div>
              <label htmlFor="action-filter" className="block text-xs font-medium text-[#4d4d4d] mb-1.5">
                计划动作
              </label>
              <select
                id="action-filter"
                value={actionFilter}
                onChange={(e) => handleActionChange(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-[#ebebeb] rounded-md bg-white text-[#171717] focus:outline-none focus:ring-2 focus:ring-[#0072f5] focus:border-transparent"
              >
                <option value="all">全部</option>
                <option value="enter">入场</option>
                <option value="exit">离场</option>
              </select>
            </div>

            {/* Signal Date Filter */}
            <div>
              <label htmlFor="signal-date-filter" className="block text-xs font-medium text-[#4d4d4d] mb-1.5">
                信号日期
              </label>
              <input
                id="signal-date-filter"
                type="date"
                value={signalDateFilter}
                onChange={(e) => handleSignalDateChange(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-[#ebebeb] rounded-md bg-white text-[#171717] focus:outline-none focus:ring-2 focus:ring-[#0072f5] focus:border-transparent"
              />
            </div>
          </div>

          {/* Clear Filters */}
          {(statusFilter !== "all" || actionFilter !== "all" || strategyIdFilter !== "all" || strategyVersionFilter !== "all" || signalDateFilter !== "") && (
            <div className="mt-4 pt-4 border-t border-[#ebebeb]">
              <button
                onClick={handleClearFilters}
                className="text-sm text-[#0072f5] hover:underline"
              >
                清除筛选
              </button>
            </div>
          )}
        </div>

        {/* Summary Bar */}
        <div className="bg-[#fafafa] border border-[#ebebeb] rounded-lg p-4 mb-6">
          <div className="flex flex-wrap items-center gap-6 text-sm">
            <div className="font-medium text-[#171717]">
              已显示 {filteredSignals.length} / {totalSignals} 条信号
            </div>
            <div className="flex gap-4 text-[#666666]">
              <span>待处理: <span className="font-medium text-[#171717]">{statusCounts.pending}</span></span>
              <span>观察中: <span className="font-medium text-[#171717]">{statusCounts.watching}</span></span>
              <span>已忽略: <span className="font-medium text-[#171717]">{statusCounts.ignored}</span></span>
              <span>已过期: <span className="font-medium text-[#171717]">{statusCounts.expired}</span></span>
            </div>
          </div>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-2 border-[#ebebeb] border-t-[#171717]"></div>
            <p className="text-sm text-[#666666] mt-3">加载中...</p>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="border border-red-200 bg-red-50 rounded-lg p-4">
            <p className="text-sm text-red-700">错误: {error}</p>
            <button
              onClick={() => loadSignals(true)}
              className="mt-2 px-4 py-2 text-sm bg-red-100 text-red-700 rounded-md hover:bg-red-200"
            >
              重试
            </button>
          </div>
        )}

        {/* Signal Table */}
        {!loading && !error && (
          <>
            {filteredSignals.length === 0 ? (
              <div className="text-center py-12 border border-[#ebebeb] rounded-lg bg-[#fafafa]">
                <p className="text-[#666666]">没有找到符合条件的信号</p>
                {(statusFilter !== "all" || actionFilter !== "all" || strategyIdFilter !== "all" || strategyVersionFilter !== "all" || signalDateFilter !== "") && (
                  <button
                    onClick={handleClearFilters}
                    className="mt-2 text-sm text-[#0072f5] hover:underline"
                  >
                    清除筛选
                  </button>
                )}
              </div>
            ) : (
              <>
                <div className="border border-[#ebebeb] rounded-lg overflow-hidden">
                  <table className="w-full">
                    <thead className="bg-[#fafafa] border-b border-[#ebebeb]">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-medium text-[#666666] uppercase tracking-wide">股票代码</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-[#666666] uppercase tracking-wide">计划动作</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-[#666666] uppercase tracking-wide">状态</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-[#666666] uppercase tracking-wide">触发原因</th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-[#666666] uppercase tracking-wide">价格</th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-[#666666] uppercase tracking-wide">数量</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-[#666666] uppercase tracking-wide">信号日期</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-[#666666] uppercase tracking-wide">计划执行</th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-[#666666] uppercase tracking-wide">操作</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-[#ebebeb]">
                      {filteredSignals.map((signal) => (
                        <tr key={signal.signal_id} className="hover:bg-[#fafafa] transition-colors">
                          <td className="px-4 py-3 text-sm font-medium text-[#171717]">
                            {signal.symbol}
                          </td>
                          <td className="px-4 py-3 text-sm">
                            <span className={getActionBadgeClass(signal.planned_action)}>
                              {signal.planned_action === "enter" ? "入场" : "离场"}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-sm">
                            <span className={getStatusBadgeClass(signal.review_status)}>
                              {getStatusLabel(signal.review_status)}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-sm text-[#666666] max-w-xs truncate" title={signal.trigger_reason}>
                            {signal.trigger_reason}
                          </td>
                          <td className="px-4 py-3 text-sm text-[#171717] text-right font-mono">
                            {signal.current_price ? `¥${signal.current_price.toFixed(2)}` : "-"}
                          </td>
                          <td className="px-4 py-3 text-sm text-[#171717] text-right font-mono">
                            {signal.quantity || "-"}
                          </td>
                          <td className="px-4 py-3 text-sm text-[#666666]">
                            {signal.signal_date}
                          </td>
                          <td className="px-4 py-3 text-sm text-[#666666]">
                            {signal.intended_execution_date}
                          </td>
                          <td className="px-4 py-3 text-sm">
                            <div className="flex flex-col items-center gap-2">
                              <Link
                                href={`/signals/${signal.signal_id}`}
                                className="text-[#0072f5] hover:underline"
                              >
                                查看
                              </Link>
                              {signal.review_status === "pending" && (
                                <div className="flex flex-wrap justify-center gap-2">
                                  <button
                                    type="button"
                                    onClick={() => handleQuickReview(signal, "watching")}
                                    disabled={reviewingSignalId === signal.signal_id}
                                    className="px-2 py-1 text-xs border border-green-200 rounded-md text-green-700 bg-green-50 hover:bg-green-100 disabled:opacity-50 disabled:cursor-not-allowed"
                                    title="需要填写观察备注时，请进入详情页"
                                  >
                                    加入观察
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setError(null);
                                      setIgnoreSignalId(signal.signal_id);
                                      setIgnoreReason("");
                                    }}
                                    disabled={reviewingSignalId === signal.signal_id}
                                    className="px-2 py-1 text-xs border border-gray-200 rounded-md text-gray-700 bg-gray-50 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                                  >
                                    忽略
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => handleQuickReview(signal, "expired")}
                                    disabled={reviewingSignalId === signal.signal_id}
                                    className="px-2 py-1 text-xs border border-red-200 rounded-md text-red-700 bg-red-50 hover:bg-red-100 disabled:opacity-50 disabled:cursor-not-allowed"
                                  >
                                    标记过期
                                  </button>
                                </div>
                              )}
                              {ignoreSignalId === signal.signal_id && (
                                <div className="w-48 space-y-2">
                                  <input
                                    type="text"
                                    value={ignoreReason}
                                    onChange={(e) => setIgnoreReason(e.target.value)}
                                    placeholder="填写忽略原因"
                                    className="w-full px-2 py-1 text-xs border border-[#ebebeb] rounded-md focus:outline-none focus:ring-2 focus:ring-[#0072f5]"
                                  />
                                  <div className="flex justify-center gap-2">
                                    <button
                                      type="button"
                                      onClick={() => handleQuickReview(signal, "ignored", ignoreReason)}
                                      disabled={reviewingSignalId === signal.signal_id}
                                      className="px-2 py-1 text-xs rounded-md bg-[#171717] text-white hover:bg-[#333333] disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                      确认
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setIgnoreSignalId(null);
                                        setIgnoreReason("");
                                      }}
                                      disabled={reviewingSignalId === signal.signal_id}
                                      className="px-2 py-1 text-xs border border-[#ebebeb] rounded-md text-[#666666] bg-white hover:bg-[#fafafa] disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                      取消
                                    </button>
                                  </div>
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {hasMore && (
                  <div className="mt-4 text-center">
                    <button
                      onClick={() => loadSignals(false)}
                      disabled={loadingMore}
                      className="px-4 py-2 text-sm border border-[#ebebeb] rounded-md bg-white text-[#171717] hover:bg-[#fafafa] disabled:bg-[#fafafa] disabled:text-[#808080] disabled:cursor-not-allowed"
                    >
                      {loadingMore ? "加载中..." : "加载更多"}
                    </button>
                  </div>
                )}
              </>
            )}
          </>
        )}

        {/* Footer */}
        <div className="mt-8 text-center text-xs text-[#808080] border-t border-[#ebebeb] pt-6">
          <p>Signal Board v0.1 - 内部工具版本</p>
        </div>
      </div>
    </div>
  );
}

