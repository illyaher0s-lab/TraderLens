/**
 * Signal Board - Detail Page
 * 
 * Display single PlannedSignal with all fields and review form.
 * 
 * Hard constraints:
 * - Display planned_action: 入场 / 离场 (not 买入 / 卖出)
 * - Show all audit fields (signal_id, strategy_version, snapshot_hash)
 * - Review form only allows: ignored / watching / expired
 * - No charts
 * - All data from Signal Board API
 */

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import ReviewForm from "@/components/ReviewForm";
import ActionPlanPanel from "@/components/ActionPlanPanel";
import {
  getSignal,
  reviewSignal,
  getActionPlan,
  submitActionDecision,
  type PlannedSignal,
  type SignalReviewRequest,
  type ActionPlan,
  type ActionPlanDecisionRequest
} from "@/lib/api-client";

export default function SignalDetailPage({ params }: { params: { signal_id: string } }) {
  const router = useRouter();
  const [signal, setSignal] = useState<PlannedSignal | null>(null);
  const [actionPlan, setActionPlan] = useState<ActionPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionPlanLoading, setActionPlanLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionPlanError, setActionPlanError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);

  useEffect(() => {
    loadSignal();
  }, [params.signal_id]);

  const loadSignal = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getSignal(params.signal_id);
      setSignal(data);

      // Load Action Plan after signal is loaded
      loadActionPlan();
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载信号失败");
    } finally {
      setLoading(false);
    }
  };

  const loadActionPlan = async () => {
    try {
      setActionPlanLoading(true);
      setActionPlanError(null);
      const data = await getActionPlan(params.signal_id);
      setActionPlan(data);
    } catch (err) {
      setActionPlanError(err instanceof Error ? err.message : "加载执行计划失败");
    } finally {
      setActionPlanLoading(false);
    }
  };

  const handleReview = async (request: SignalReviewRequest) => {
    try {
      setIsSubmitting(true);
      const updatedSignal = await reviewSignal(params.signal_id, request);
      setSignal(updatedSignal);
      setSubmitSuccess(true);

      // Reload Action Plan after review status change
      loadActionPlan();

      // Hide success message after 3 seconds
      setTimeout(() => setSubmitSuccess(false), 3000);
    } catch (err) {
      // Error is handled by ReviewForm component
      throw err;
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleActionPlanDecision = async (request: ActionPlanDecisionRequest) => {
    try {
      setIsSubmitting(true);
      const updatedActionPlan = await submitActionDecision(params.signal_id, request);
      setActionPlan(updatedActionPlan);
      setSubmitSuccess(true);

      // Reload signal to reflect review_status change
      const updatedSignal = await getSignal(params.signal_id);
      setSignal(updatedSignal);

      // Hide success message after 3 seconds
      setTimeout(() => setSubmitSuccess(false), 3000);
    } catch (err) {
      throw err;
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p className="text-sm text-slate-600 mt-2">加载中...</p>
        </div>
      </div>
    );
  }

  if (error || !signal) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="max-w-md w-full p-6">
          <div className="rounded-lg bg-red-50 border border-red-200 p-4">
            <p className="text-sm text-red-700">{error || "信号未找到"}</p>
            <div className="mt-4 flex gap-2">
              <button
                onClick={loadSignal}
                className="px-3 py-1.5 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200"
              >
                重试
              </button>
              <Link
                href="/signals"
                className="px-3 py-1.5 text-sm bg-slate-100 text-slate-700 rounded hover:bg-slate-200"
              >
                返回列表
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-5xl mx-auto px-4 py-8">
        {/* Back Link */}
        <Link
          href="/signals"
          className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline mb-6"
        >
          ← 返回信号列表
        </Link>

        {/* Success Message */}
        {submitSuccess && (
          <div className="mb-6 rounded-lg bg-green-50 border border-green-200 p-4">
            <p className="text-sm text-green-700">✓ 审核提交成功</p>
          </div>
        )}

        {/* Header */}
        <div className="bg-white rounded-lg border border-slate-200 p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-2xl font-semibold text-slate-900">{signal.symbol}</h1>
            <div className="flex items-center gap-2">
              <span
                className={`px-3 py-1 text-sm font-medium rounded ${
                  signal.planned_action === "enter"
                    ? "text-green-700 bg-green-50"
                    : "text-orange-700 bg-orange-50"
                }`}
              >
                {signal.planned_action === "enter" ? "入场" : "离场"}
              </span>
              <span
                className={`px-3 py-1 text-sm font-medium rounded ${
                  signal.review_status === "pending"
                    ? "text-blue-700 bg-blue-50"
                    : signal.review_status === "watching"
                    ? "text-purple-700 bg-purple-50"
                    : signal.review_status === "ignored"
                    ? "text-gray-700 bg-gray-50"
                    : "text-red-700 bg-red-50"
                }`}
              >
                {signal.review_status === "pending" && "待处理"}
                {signal.review_status === "watching" && "已加入观察"}
                {signal.review_status === "ignored" && "已忽略"}
                {signal.review_status === "expired" && "已过期"}
              </span>
            </div>
          </div>

          <div className="text-sm text-slate-700">
            <strong>触发原因:</strong> {signal.trigger_reason}
          </div>
          <p className="text-xs text-slate-500 mt-2">
            仅显示已通过验证的计划信号；不是买卖建议；不会自动交易。
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {/* Left Column: Signal Info + Audit Info */}
          <div className="md:col-span-2 space-y-6">
            {/* A. Signal Information */}
            <div className="bg-white rounded-lg border border-slate-200 p-6">
              <h2 className="text-lg font-semibold text-slate-900 mb-4">信号信息</h2>
              <dl className="space-y-3">
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-sm text-slate-600">股票代码</dt>
                  <dd className="col-span-2 text-sm font-medium text-slate-900">{signal.symbol}</dd>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-sm text-slate-600">计划动作</dt>
                  <dd className="col-span-2 text-sm font-medium text-slate-900">
                    {signal.planned_action === "enter" ? "入场" : "离场"}
                  </dd>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-sm text-slate-600">触发原因</dt>
                  <dd className="col-span-2 text-sm text-slate-900">{signal.trigger_reason}</dd>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-sm text-slate-600">数量</dt>
                  <dd className="col-span-2 text-sm text-slate-900">
                    {signal.quantity !== null ? signal.quantity : "未指定"}
                  </dd>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-sm text-slate-600">当前价格</dt>
                  <dd className="col-span-2 text-sm text-slate-900">
                    {signal.current_price !== null ? `¥${signal.current_price.toFixed(2)}` : "N/A"}
                  </dd>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-sm text-slate-600">持仓前数量</dt>
                  <dd className="col-span-2 text-sm text-slate-900">
                    {signal.position_before !== null ? signal.position_before : "N/A"}
                  </dd>
                </div>
              </dl>
            </div>

            {/* B. Audit Information */}
            <div className="bg-white rounded-lg border border-slate-200 p-6">
              <h2 className="text-lg font-semibold text-slate-900 mb-4">审计信息</h2>
              <dl className="space-y-3">
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-sm text-slate-600">信号 ID</dt>
                  <dd className="col-span-2 text-xs font-mono text-slate-900 break-all">
                    {signal.signal_id}
                  </dd>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-sm text-slate-600">策略 ID</dt>
                  <dd className="col-span-2 text-sm text-slate-900">{signal.strategy_id}</dd>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-sm text-slate-600">策略版本</dt>
                  <dd className="col-span-2 text-sm font-mono text-slate-900">{signal.strategy_version}</dd>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-sm text-slate-600">数据快照</dt>
                  <dd className="col-span-2 text-xs font-mono text-slate-900 break-all">
                    {signal.snapshot_hash}
                  </dd>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-sm text-slate-600">信号日期</dt>
                  <dd className="col-span-2 text-sm text-slate-900">{signal.signal_date}</dd>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-sm text-slate-600">计划执行日期</dt>
                  <dd className="col-span-2 text-sm text-slate-900">{signal.intended_execution_date}</dd>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <dt className="text-sm text-slate-600">创建时间</dt>
                  <dd className="col-span-2 text-sm text-slate-900">
                    {new Date(signal.created_at).toLocaleString("zh-CN")}
                  </dd>
                </div>
              </dl>
            </div>

            {/* C. Action Plan */}
            {actionPlanLoading && (
              <div className="bg-white rounded-lg border border-slate-200 p-6">
                <div className="text-center">
                  <div className="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
                  <p className="text-sm text-slate-600 mt-2">加载执行计划...</p>
                </div>
              </div>
            )}

            {actionPlanError && (
              <div className="bg-white rounded-lg border border-slate-200 p-6">
                <div className="text-sm text-red-700">{actionPlanError}</div>
              </div>
            )}

            {actionPlan && !actionPlanLoading && !actionPlanError && (
              <ActionPlanPanel
                actionPlan={actionPlan}
                onDecisionSubmit={handleActionPlanDecision}
                isSubmitting={isSubmitting}
              />
            )}
          </div>

          {/* Right Column: Review Form */}
          <div>
            <div className="bg-white rounded-lg border border-slate-200 p-6 sticky top-8">
              <h2 className="text-lg font-semibold text-slate-900 mb-4">人工审核</h2>
              <ReviewForm signal={signal} onSubmit={handleReview} isSubmitting={isSubmitting} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
