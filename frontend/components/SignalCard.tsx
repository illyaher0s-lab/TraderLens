/**
 * SignalCard Component
 * 
 * Display a single PlannedSignal summary.
 * 
 * Hard constraints:
 * - Display planned_action in Chinese: 入场 (enter) / 离场 (exit)
 * - Display review_status in Chinese: 待处理 / 已忽略 / 已加入观察 / 已过期
 * - NEVER display: 买入, 卖出, 推荐, 建议操作
 */

import Link from "next/link";
import type { PlannedSignal } from "@/lib/api-client";

interface SignalCardProps {
  signal: PlannedSignal;
}

/**
 * Map planned_action to Chinese display.
 */
function getPlannedActionDisplay(action: "enter" | "exit"): string {
  return action === "enter" ? "入场" : "离场";
}

/**
 * Get color class for planned_action.
 */
function getPlannedActionColor(action: "enter" | "exit"): string {
  return action === "enter" ? "text-green-700 bg-green-50" : "text-orange-700 bg-orange-50";
}

/**
 * Map review_status to Chinese display.
 */
function getReviewStatusDisplay(status: PlannedSignal["review_status"]): string {
  const statusMap: Record<PlannedSignal["review_status"], string> = {
    pending: "待处理",
    ignored: "已忽略",
    watching: "已加入观察",
    expired: "已过期",
  };
  return statusMap[status];
}

/**
 * Get color class for review_status.
 */
function getReviewStatusColor(status: PlannedSignal["review_status"]): string {
  const colorMap: Record<PlannedSignal["review_status"], string> = {
    pending: "text-blue-700 bg-blue-50",
    ignored: "text-gray-700 bg-gray-50",
    watching: "text-purple-700 bg-purple-50",
    expired: "text-red-700 bg-red-50",
  };
  return colorMap[status];
}

export default function SignalCard({ signal }: SignalCardProps) {
  return (
    <Link href={`/signals/${signal.signal_id}`}>
      <div className="rounded border border-slate-200 bg-white p-4 hover:border-slate-300 hover:shadow-sm transition-all cursor-pointer">
        {/* Header: Symbol + Planned Action */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <span className="text-lg font-semibold text-slate-900">{signal.symbol}</span>
            <span
              className={`px-2 py-1 text-xs font-medium rounded ${getPlannedActionColor(
                signal.planned_action
              )}`}
            >
              {getPlannedActionDisplay(signal.planned_action)}
            </span>
          </div>
          
          <span
            className={`px-2 py-1 text-xs font-medium rounded ${getReviewStatusColor(
              signal.review_status
            )}`}
          >
            {getReviewStatusDisplay(signal.review_status)}
          </span>
        </div>

        {/* Trigger Reason */}
        <p className="text-sm text-slate-700 mb-3 line-clamp-2">{signal.trigger_reason}</p>

        {/* Details */}
        <div className="grid grid-cols-2 gap-2 text-xs text-slate-600">
          <div>
            <span className="text-slate-500">当前价格:</span>{" "}
            <span className="font-medium">
              {signal.current_price !== null ? `¥${signal.current_price.toFixed(2)}` : "N/A"}
            </span>
          </div>
          <div>
            <span className="text-slate-500">数量:</span>{" "}
            <span className="font-medium">{signal.quantity ?? "未指定"}</span>
          </div>
          <div>
            <span className="text-slate-500">信号日期:</span>{" "}
            <span className="font-medium">{signal.signal_date}</span>
          </div>
          <div>
            <span className="text-slate-500">计划执行:</span>{" "}
            <span className="font-medium">{signal.intended_execution_date}</span>
          </div>
        </div>
      </div>
    </Link>
  );
}
