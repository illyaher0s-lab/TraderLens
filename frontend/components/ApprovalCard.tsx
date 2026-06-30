/**
 * Approval Card Component
 *
 * Task 14: Display result-level approval cards.
 *
 * Hard constraints:
 * - Only result-level decisions (continue, stop, downgrade_to_observation, etc.)
 * - No technical parameters (OOS, threshold, stop_loss, liquidity_rule, position_size, backtest_param)
 * - Plain language summary
 */

"use client";

import { useState } from "react";
import type { ApprovalCardData } from "@/lib/api-client";

interface ApprovalCardProps {
  card: ApprovalCardData;
  onDecide: (decision: string, decidedBy: string) => Promise<void>;
  isSubmitting: boolean;
}

const DECISION_LABELS: Record<string, string> = {
  continue: "继续",
  stop: "停止",
  downgrade_to_observation: "降级观察",
  enter_risk_capped_live_execution: "进入小资金实盘观察",
  accept_execution_record_interpretation: "接受记录解释",
};

const DECISION_COLORS: Record<string, string> = {
  continue: "bg-green-600 hover:bg-green-700",
  stop: "bg-red-600 hover:bg-red-700",
  downgrade_to_observation: "bg-gray-600 hover:bg-gray-700",
  enter_risk_capped_live_execution: "bg-blue-600 hover:bg-blue-700",
  accept_execution_record_interpretation: "bg-blue-600 hover:bg-blue-700",
};

export default function ApprovalCard({
  card,
  onDecide,
  isSubmitting,
}: ApprovalCardProps) {
  const [selectedDecision, setSelectedDecision] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleDecide = async (decision: string) => {
    setSelectedDecision(decision);
    setError(null);

    try {
      await onDecide(decision, "user");
    } catch (err) {
      setError(err instanceof Error ? err.message : "决策提交失败");
      setSelectedDecision(null);
    }
  };

  // Already decided
  if (card.decision) {
    return (
      <div className="bg-white rounded-lg border border-[#ebebeb] p-6">
        <div className="flex items-start gap-3 mb-4">
          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-green-100 flex items-center justify-center">
            <span className="text-green-700 text-lg">✓</span>
          </div>
          <div className="flex-1">
            <h3 className="text-base font-semibold text-[#171717]">{card.title}</h3>
            <p className="text-sm text-[#666666] mt-1">
              {card.plain_language_summary}
            </p>
          </div>
        </div>

        <div className="bg-green-50 border border-green-200 rounded-lg p-3">
          <p className="text-sm font-medium text-green-900">
            已决策: {DECISION_LABELS[card.decision] || card.decision}
          </p>
          {card.decided_at && (
            <p className="text-xs text-green-700 mt-1">
              {new Date(card.decided_at).toLocaleString("zh-CN")}
            </p>
          )}
        </div>
      </div>
    );
  }

  // Pending decision
  return (
    <div className="bg-white rounded-lg border border-[#ebebeb] p-6">
      <div className="flex items-start gap-3 mb-4">
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center">
          <span className="text-blue-700 text-lg">?</span>
        </div>
        <div className="flex-1">
          <h3 className="text-base font-semibold text-[#171717]">{card.title}</h3>
          <p className="text-sm text-[#666666] mt-1 whitespace-pre-wrap">
            {card.plain_language_summary}
          </p>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      <div className="space-y-2">
        <p className="text-xs font-medium text-[#666666] uppercase tracking-wide mb-3">
          选择操作
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {card.allowed_decisions.map((decision) => (
            <button
              key={decision}
              onClick={() => handleDecide(decision)}
              disabled={isSubmitting || selectedDecision !== null}
              className={`px-4 py-3 text-sm font-medium rounded-md text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                DECISION_COLORS[decision] || "bg-gray-600 hover:bg-gray-700"
              }`}
            >
              {selectedDecision === decision ? (
                <span className="flex items-center justify-center gap-2">
                  <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                  提交中...
                </span>
              ) : (
                DECISION_LABELS[decision] || decision
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 pt-4 border-t border-[#ebebeb]">
        <p className="text-xs text-[#808080]">
          阶段: {card.stage} · 关联证据: {card.artifact_ids.length} 项
        </p>
      </div>
    </div>
  );
}
