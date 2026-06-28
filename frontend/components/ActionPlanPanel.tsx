/**
 * Action Plan Panel
 *
 * C3 Human Execution Boundary - displays pre-action checks and decision buttons.
 *
 * Hard constraints:
 * - Title: "人工处理计划"
 * - Required disclaimer: "这是人工处理计划，不是买卖建议，不会自动交易。"
 * - Allowed button labels: 准备执行, 部分执行, 今日放弃, 标记过期
 * - Disable "准备执行" if blocking check exists or freshness_status == expired
 * - Require reason for partial/skip/expired decisions
 * - No broker/order/fill/P&L fields
 */

"use client";

import { useState } from "react";
import type { ActionPlan, ActionPlanDecisionRequest, ActionCheck } from "@/lib/api-client";

interface ActionPlanPanelProps {
  actionPlan: ActionPlan;
  onDecisionSubmit: (request: ActionPlanDecisionRequest) => Promise<void>;
  isSubmitting: boolean;
}

export default function ActionPlanPanel({ actionPlan, onDecisionSubmit, isSubmitting }: ActionPlanPanelProps) {
  const [selectedDecision, setSelectedDecision] = useState<"execute" | "partial" | "skip" | "expired" | null>(null);
  const [reason, setReason] = useState("");
  const [manualNotes, setManualNotes] = useState("");
  const [showReasonInput, setShowReasonInput] = useState(false);

  // Check if any blocking check exists
  const hasBlockingCheck = [...actionPlan.pre_action_checks, ...actionPlan.invalidation_checks].some(
    (check) => check.blocking && check.status === "blocked"
  );

  // Disable execute button if blocking exists or expired
  const canExecute = !hasBlockingCheck && actionPlan.freshness_status !== "expired";

  const handleDecisionClick = (decision: "execute" | "partial" | "skip" | "expired") => {
    setSelectedDecision(decision);

    // Show reason input for partial/skip/expired
    if (decision === "partial" || decision === "skip" || decision === "expired") {
      setShowReasonInput(true);
    } else {
      setShowReasonInput(false);
      // Submit immediately for execute
      handleSubmit(decision);
    }
  };

  const handleSubmit = async (decision: "execute" | "partial" | "skip" | "expired") => {
    const request: ActionPlanDecisionRequest = {
      decision,
      decided_by: "user",
      reason: reason.trim() || undefined,
      manual_notes: manualNotes.trim() || undefined,
    };

    try {
      await onDecisionSubmit(request);
      // Reset form on success
      setSelectedDecision(null);
      setReason("");
      setManualNotes("");
      setShowReasonInput(false);
    } catch (err) {
      // Error handled by parent
      throw err;
    }
  };

  const renderCheck = (check: ActionCheck) => {
    const statusColors = {
      pass: "text-green-700 bg-green-50 border-green-200",
      warning: "text-yellow-700 bg-yellow-50 border-yellow-200",
      blocked: "text-red-700 bg-red-50 border-red-200",
      unknown: "text-gray-700 bg-gray-50 border-gray-200",
    };

    const statusIcons = {
      pass: "✓",
      warning: "⚠",
      blocked: "✗",
      unknown: "?",
    };

    return (
      <div key={check.check_id} className={`p-3 rounded border ${statusColors[check.status]}`}>
        <div className="flex items-start gap-2">
          <span className="text-lg leading-none">{statusIcons[check.status]}</span>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium">{check.label}</div>
            <div className="text-xs mt-1">{check.detail}</div>
            {check.blocking && check.status === "blocked" && (
              <div className="text-xs font-semibold mt-1">阻断条件</div>
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-6">
      <h2 className="text-lg font-semibold text-slate-900 mb-2">人工处理计划</h2>
      <p className="text-xs text-slate-600 mb-4">
        这是人工处理计划，不是买卖建议，不会自动交易。
      </p>

      {/* Existing Decision Display */}
      {actionPlan.user_decision && (
        <div className="mb-4 p-3 rounded bg-blue-50 border border-blue-200">
          <div className="text-sm font-medium text-blue-900">
            已决策: {actionPlan.user_decision.decision === "execute" && "准备执行"}
            {actionPlan.user_decision.decision === "partial" && "部分执行"}
            {actionPlan.user_decision.decision === "skip" && "今日放弃"}
            {actionPlan.user_decision.decision === "expired" && "标记过期"}
          </div>
          {actionPlan.user_decision.reason && (
            <div className="text-xs text-blue-700 mt-1">原因: {actionPlan.user_decision.reason}</div>
          )}
          <div className="text-xs text-blue-600 mt-1">
            决策时间: {new Date(actionPlan.user_decision.decided_at).toLocaleString("zh-CN")}
          </div>
        </div>
      )}

      {/* Pre-action Checks */}
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-slate-900 mb-2">执行前检查</h3>
        <div className="space-y-2">
          {actionPlan.pre_action_checks.map(renderCheck)}
        </div>
      </div>

      {/* Invalidation Checks */}
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-slate-900 mb-2">无效化检查</h3>
        <div className="space-y-2">
          {actionPlan.invalidation_checks.map(renderCheck)}
        </div>
      </div>

      {/* Risk Warnings */}
      {actionPlan.risk_warnings.length > 0 && (
        <div className="mb-4 p-3 rounded bg-yellow-50 border border-yellow-200">
          <div className="text-sm font-medium text-yellow-900 mb-1">风险提示</div>
          {actionPlan.risk_warnings.map((warning, idx) => (
            <div key={idx} className="text-xs text-yellow-700">• {warning}</div>
          ))}
        </div>
      )}

      {/* Decision Buttons */}
      {!showReasonInput && (
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => handleDecisionClick("execute")}
            disabled={!canExecute || isSubmitting}
            className={`px-4 py-2 text-sm font-medium rounded ${
              canExecute
                ? "bg-green-600 text-white hover:bg-green-700"
                : "bg-gray-200 text-gray-400 cursor-not-allowed"
            }`}
          >
            准备执行
          </button>
          <button
            onClick={() => handleDecisionClick("partial")}
            disabled={isSubmitting}
            className="px-4 py-2 text-sm font-medium rounded bg-blue-600 text-white hover:bg-blue-700"
          >
            部分执行
          </button>
          <button
            onClick={() => handleDecisionClick("skip")}
            disabled={isSubmitting}
            className="px-4 py-2 text-sm font-medium rounded bg-gray-600 text-white hover:bg-gray-700"
          >
            今日放弃
          </button>
          <button
            onClick={() => handleDecisionClick("expired")}
            disabled={isSubmitting}
            className="px-4 py-2 text-sm font-medium rounded bg-red-600 text-white hover:bg-red-700"
          >
            标记过期
          </button>
        </div>
      )}

      {/* Reason Input Form */}
      {showReasonInput && selectedDecision && (
        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              原因 <span className="text-red-600">*</span>
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 border border-slate-300 rounded text-sm"
              placeholder="请说明决策原因"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              备注 (可选)
            </label>
            <textarea
              value={manualNotes}
              onChange={(e) => setManualNotes(e.target.value)}
              rows={2}
              className="w-full px-3 py-2 border border-slate-300 rounded text-sm"
              placeholder="补充说明"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => handleSubmit(selectedDecision)}
              disabled={!reason.trim() || isSubmitting}
              className={`flex-1 px-4 py-2 text-sm font-medium rounded ${
                reason.trim() && !isSubmitting
                  ? "bg-blue-600 text-white hover:bg-blue-700"
                  : "bg-gray-200 text-gray-400 cursor-not-allowed"
              }`}
            >
              提交
            </button>
            <button
              onClick={() => {
                setShowReasonInput(false);
                setSelectedDecision(null);
                setReason("");
                setManualNotes("");
              }}
              disabled={isSubmitting}
              className="px-4 py-2 text-sm font-medium rounded bg-gray-200 text-gray-700 hover:bg-gray-300"
            >
              取消
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
