/**
 * Approval Card Component
 *
 * Task 14: Display result-level approval cards.
 * Design: Vercel style - shadow-as-border, subtle status colors, clear hierarchy.
 *
 * Hard constraints:
 * - Only result-level decisions
 * - No technical parameters
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

const DECISION_STYLES: Record<string, string> = {
  continue: "bg-[#171717] text-white hover:bg-[#000000]",
  stop: "bg-white text-[#171717] hover:bg-[#fafafa]",
  downgrade_to_observation: "bg-white text-[#171717] hover:bg-[#fafafa]",
  enter_risk_capped_live_execution: "bg-white text-[#171717] hover:bg-[#fafafa]",
  accept_execution_record_interpretation: "bg-white text-[#171717] hover:bg-[#fafafa]",
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
      <div className="bg-white rounded-lg p-6" style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}>
        <div className="flex items-start gap-3 mb-4">
          <div className="flex-shrink-0 w-6 h-6 rounded-full bg-[#f0fdf4] flex items-center justify-center">
            <span className="text-[#16a34a] text-sm">✓</span>
          </div>
          <div className="flex-1">
            <h3 className="text-[16px] font-semibold text-[#171717] tracking-tight">{card.title}</h3>
            <p className="text-[14px] text-[#666666] mt-1 font-normal leading-relaxed">
              {card.plain_language_summary}
            </p>
          </div>
        </div>

        <div className="bg-[#f0fdf4] rounded-lg p-3" style={{ boxShadow: '0px 0px 0px 1px rgba(34,197,94,0.2)' }}>
          <p className="text-[14px] font-medium text-[#16a34a]">
            已决策: {DECISION_LABELS[card.decision] || card.decision}
          </p>
          {card.decided_at && (
            <p className="text-[12px] text-[#22c55e] mt-1">
              {new Date(card.decided_at).toLocaleString("zh-CN")}
            </p>
          )}
        </div>
      </div>
    );
  }

  // Pending decision
  return (
    <div className="bg-white rounded-lg p-6" style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}>
      <div className="flex items-start gap-3 mb-4">
        <div className="flex-shrink-0 w-6 h-6 rounded-full bg-[#fef3c7] flex items-center justify-center">
          <span className="text-[#f59e0b] text-sm font-medium">?</span>
        </div>
        <div className="flex-1">
          <h3 className="text-[16px] font-semibold text-[#171717] tracking-tight">{card.title}</h3>
          <p className="text-[14px] text-[#666666] mt-1 font-normal leading-relaxed whitespace-pre-wrap">
            {card.plain_language_summary}
          </p>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-[#fef2f2]" style={{ boxShadow: '0px 0px 0px 1px rgba(254,202,202,0.5)' }}>
          <p className="text-[14px] text-[#991b1b]">{error}</p>
        </div>
      )}

      <div className="space-y-3">
        <p className="text-[12px] font-medium text-[#808080] uppercase tracking-wide">
          选择操作
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {card.allowed_decisions.map((decision) => {
            const isStop = decision === "stop";
            return (
              <button
                key={decision}
                onClick={() => handleDecide(decision)}
                disabled={isSubmitting || selectedDecision !== null}
                className={`px-4 py-3 text-[14px] font-medium rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                  DECISION_STYLES[decision] || "bg-white text-[#171717] hover:bg-[#fafafa]"
                }`}
                style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}
              >
                {selectedDecision === decision ? (
                  <span className="flex items-center justify-center gap-2">
                    <div className="animate-spin rounded-full h-4 w-4 border-2 border-[#ebebeb] border-t-[#171717]"></div>
                    提交中...
                  </span>
                ) : (
                  DECISION_LABELS[decision] || decision
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-4 pt-4" style={{ borderTop: '1px solid rgba(0,0,0,0.08)' }}>
        <p className="text-[12px] text-[#808080]">
          阶段: {card.stage} · 关联证据: {card.artifact_ids.length} 项
        </p>
      </div>
    </div>
  );
}
