/**
 * ReviewForm Component
 * 
 * Form for reviewing a PlannedSignal.
 * 
 * Hard constraints:
 * - Only allow review_status: ignored / watching / expired
 * - Cannot set back to pending
 * - rejection_reason required when status is ignored
 * - Cannot modify PlannedSignal fields (immutable)
 */

"use client";

import { useState } from "react";
import type { PlannedSignal, SignalReviewRequest } from "@/lib/api-client";

interface ReviewFormProps {
  signal: PlannedSignal;
  onSubmit: (request: SignalReviewRequest) => Promise<void>;
  isSubmitting?: boolean;
}

export default function ReviewForm({ signal, onSubmit, isSubmitting = false }: ReviewFormProps) {
  const [reviewStatus, setReviewStatus] = useState<"ignored" | "watching" | "expired">("watching");
  const [reviewedBy, setReviewedBy] = useState("local_user");
  const [rejectionReason, setRejectionReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validate: rejection_reason required if status is ignored
    if (reviewStatus === "ignored" && !rejectionReason.trim()) {
      setError("忽略信号时必须填写原因");
      return;
    }

    try {
      await onSubmit({
        review_status: reviewStatus,
        reviewed_by: reviewedBy,
        rejection_reason: reviewStatus === "ignored" ? rejectionReason : undefined,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Current Status Display */}
      <div className="rounded bg-slate-50 p-3 border border-slate-200">
        <div className="text-sm text-slate-600">当前状态</div>
        <div className="text-base font-medium text-slate-900 mt-1">
          {signal.review_status === "pending" && "待处理"}
          {signal.review_status === "ignored" && "已忽略"}
          {signal.review_status === "watching" && "已加入观察"}
          {signal.review_status === "expired" && "已过期"}
        </div>
        {signal.reviewed_by && (
          <div className="text-xs text-slate-500 mt-1">
            由 {signal.reviewed_by} 于 {signal.reviewed_at ? new Date(signal.reviewed_at).toLocaleString("zh-CN") : "未知时间"} 审核
          </div>
        )}
      </div>

      {/* Review Status Selection */}
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-2">
          新状态 <span className="text-red-500">*</span>
        </label>
        <div className="space-y-2">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="review_status"
              value="watching"
              checked={reviewStatus === "watching"}
              onChange={(e) => setReviewStatus(e.target.value as "watching")}
              className="w-4 h-4 text-purple-600 focus:ring-purple-500"
            />
            <span className="text-sm text-slate-700">加入观察</span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="review_status"
              value="ignored"
              checked={reviewStatus === "ignored"}
              onChange={(e) => setReviewStatus(e.target.value as "ignored")}
              className="w-4 h-4 text-gray-600 focus:ring-gray-500"
            />
            <span className="text-sm text-slate-700">忽略</span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="review_status"
              value="expired"
              checked={reviewStatus === "expired"}
              onChange={(e) => setReviewStatus(e.target.value as "expired")}
              className="w-4 h-4 text-red-600 focus:ring-red-500"
            />
            <span className="text-sm text-slate-700">标记为已过期</span>
          </label>
        </div>
      </div>

      {/* Reviewed By */}
      <div>
        <label htmlFor="reviewed_by" className="block text-sm font-medium text-slate-700 mb-1">
          审核人 <span className="text-red-500">*</span>
        </label>
        <input
          id="reviewed_by"
          type="text"
          value={reviewedBy}
          onChange={(e) => setReviewedBy(e.target.value)}
          required
          className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="local_user"
        />
      </div>

      {/* Rejection Reason (required if ignored) */}
      {reviewStatus === "ignored" && (
        <div>
          <label htmlFor="rejection_reason" className="block text-sm font-medium text-slate-700 mb-1">
            忽略原因 <span className="text-red-500">*</span>
          </label>
          <textarea
            id="rejection_reason"
            value={rejectionReason}
            onChange={(e) => setRejectionReason(e.target.value)}
            required
            rows={3}
            className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="请说明为什么忽略这个信号（必填）"
          />
          <p className="text-xs text-slate-500 mt-1">
            忽略信号时必须填写原因，以便后续复盘
          </p>
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="rounded bg-red-50 border border-red-200 p-3">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Submit Button */}
      <button
        type="submit"
        disabled={isSubmitting}
        className="w-full px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isSubmitting ? "提交中..." : "提交审核"}
      </button>
    </form>
  );
}
