/**
 * Live Loop Panel
 *
 * Task 19: 人工执行记录面板 - 让用户在 Workbench 记录买入/卖出，生成今日信号，查看盈亏复盘。
 * Design: Vercel style - shadow-as-border, minimal color, clean hierarchy.
 *
 * 核心约束：
 * - 不自动交易
 * - 不接券商
 * - 不暴露技术参数
 * - 用户人工执行后手动记录
 */

"use client";

import { useState } from "react";
import {
  createExecutionCard,
  submitExecutionFeedback,
  generateDailySignal,
  type ExecutionCardResponse,
  type ExecutionFeedbackResponse,
  type DailySignalResponse,
} from "@/lib/api-client";

interface LiveLoopPanelProps {
  conversationId: string | null;
  onUpdate: () => void;
}

export default function LiveLoopPanel({
  conversationId,
  onUpdate,
}: LiveLoopPanelProps) {
  const [feedback, setFeedback] = useState("");
  const [symbol, setSymbol] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isGeneratingSignal, setIsGeneratingSignal] = useState(false);
  const [isCreatingCard, setIsCreatingCard] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<ExecutionCardResponse | ExecutionFeedbackResponse | DailySignalResponse | null>(null);

  const handleCreateExecutionCard = async () => {
    if (!conversationId) return;

    setIsCreatingCard(true);
    setError(null);
    setLastResult(null);

    try {
      const result = await createExecutionCard(conversationId);
      setLastResult(result);
      onUpdate();
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成执行计划失败");
    } finally {
      setIsCreatingCard(false);
    }
  };

  const handleSubmitFeedback = async () => {
    if (!conversationId || !feedback.trim()) return;

    setIsSubmitting(true);
    setError(null);
    setLastResult(null);

    try {
      const result = await submitExecutionFeedback(conversationId, {
        feedback: feedback.trim(),
        symbol: symbol.trim() || undefined,
      });

      setLastResult(result);
      setFeedback("");
      setSymbol("");
      onUpdate();
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleGenerateSignal = async () => {
    if (!conversationId) return;

    setIsGeneratingSignal(true);
    setError(null);
    setLastResult(null);

    try {
      const result = await generateDailySignal(conversationId);
      setLastResult(result);
      onUpdate();
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成信号失败");
    } finally {
      setIsGeneratingSignal(false);
    }
  };

  if (!conversationId) {
    return (
      <div className="bg-white rounded-lg p-6" style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}>
        <h3 className="text-[16px] font-semibold text-[#171717] mb-2 tracking-tight">
          人工执行记录
        </h3>
        <p className="text-[14px] text-[#666666] font-normal">
          请先开始对话
        </p>
      </div>
    );
  }

  const renderResult = () => {
    if (!lastResult) return null;

    // Execution card result
    if ("execution_card_id" in lastResult) {
      return (
        <div className="mt-4 p-4 rounded-lg bg-[#f0fdf4]" style={{ boxShadow: '0px 0px 0px 1px rgba(34,197,94,0.2)' }}>
          <p className="text-[14px] font-medium text-[#16a34a] mb-2">
            ✓ 执行计划已生成
          </p>
          <p className="text-[12px] text-[#22c55e] font-mono">
            ID: {lastResult.execution_card_id}
          </p>
          {lastResult.agent_reply && (
            <p className="text-[14px] text-[#171717] mt-2">
              {lastResult.agent_reply}
            </p>
          )}
        </div>
      );
    }

    // Execution feedback result
    if ("action" in lastResult && lastResult.status === "success") {
      const isBuy = lastResult.action === "buy";
      const isSell = lastResult.action === "sell";

      return (
        <div className="mt-4 p-4 rounded-lg bg-[#f0fdf4]" style={{ boxShadow: '0px 0px 0px 1px rgba(34,197,94,0.2)' }}>
          <p className="text-[14px] font-medium text-[#16a34a] mb-2">
            ✓ {isBuy ? "买入记录已保存" : isSell ? "卖出记录已保存" : "记录已保存"}
          </p>
          {lastResult.position_id && (
            <p className="text-[12px] text-[#22c55e] font-mono">
              持仓 ID: {lastResult.position_id}
            </p>
          )}
          {lastResult.realized_pnl !== undefined && (
            <div className="mt-2 pt-2" style={{ borderTop: '1px solid rgba(34,197,94,0.2)' }}>
              <p className="text-[14px] font-medium text-[#171717]">
                盈亏: {lastResult.realized_pnl >= 0 ? "+" : ""}{lastResult.realized_pnl?.toFixed(2)}
                {lastResult.pnl_pct !== undefined && (
                  <span className="ml-2 text-[#666666]">
                    ({lastResult.pnl_pct >= 0 ? "+" : ""}{lastResult.pnl_pct?.toFixed(2)}%)
                  </span>
                )}
              </p>
              {lastResult.discipline_review_id && (
                <p className="text-[12px] text-[#666666] mt-1">
                  纪律复盘已生成
                </p>
              )}
            </div>
          )}
        </div>
      );
    }

    // Follow-up question
    if ("follow_up_question" in lastResult && lastResult.status === "needs_more_info") {
      return (
        <div className="mt-4 p-4 rounded-lg bg-[#fef3c7]" style={{ boxShadow: '0px 0px 0px 1px rgba(251,191,36,0.2)' }}>
          <p className="text-[14px] text-[#d97706]">
            {lastResult.follow_up_question}
          </p>
        </div>
      );
    }

    // Daily signal result
    if ("signals" in lastResult) {
      if (lastResult.status === "no_open_positions") {
        return (
          <div className="mt-4 p-4 rounded-lg bg-[#fafafa]" style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}>
            <p className="text-[14px] text-[#666666]">
              {lastResult.message || "没有持仓需要观察"}
            </p>
          </div>
        );
      }

      if (lastResult.status === "success" && lastResult.signals.length > 0) {
        return (
          <div className="mt-4 p-4 rounded-lg bg-[#f0fdf4]" style={{ boxShadow: '0px 0px 0px 1px rgba(34,197,94,0.2)' }}>
            <p className="text-[14px] font-medium text-[#16a34a] mb-3">
              ✓ 生成 {lastResult.signals.length} 个信号
            </p>
            <div className="space-y-2">
              {lastResult.signals.map((signal, idx) => (
                <div key={idx} className="text-[12px] text-[#666666]">
                  <span className="font-mono text-[#171717]">{signal.symbol}</span>
                  <span className="mx-2">·</span>
                  <span>{signal.signal_type}</span>
                </div>
              ))}
            </div>
          </div>
        );
      }
    }

    return null;
  };

  return (
    <div className="bg-white rounded-lg p-6" style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}>
      <h3 className="text-[16px] font-semibold text-[#171717] mb-1 tracking-tight">
        人工执行记录
      </h3>
      <p className="text-[12px] text-[#808080] mb-4 font-normal">
        这是人工处理计划，不会自动交易
      </p>

      {/* Error Banner */}
      {error && (
        <div className="mb-4 p-3 rounded-lg bg-[#fef2f2]" style={{ boxShadow: '0px 0px 0px 1px rgba(254,202,202,0.5)' }}>
          <p className="text-[14px] text-[#991b1b]">{error}</p>
          <button
            onClick={() => setError(null)}
            className="mt-2 text-[12px] text-[#dc2626] hover:underline"
          >
            关闭
          </button>
        </div>
      )}

      {/* Execution Card Button */}
      <div className="mb-4">
        <button
          onClick={handleCreateExecutionCard}
          disabled={isCreatingCard}
          className="w-full px-4 py-2 text-[14px] font-medium rounded-md bg-white text-[#171717] hover:bg-[#fafafa] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}
        >
          {isCreatingCard ? "生成中..." : "生成执行计划"}
        </button>
      </div>

      {/* Feedback Input */}
      <div className="space-y-3">
        <div>
          <label className="block text-[12px] text-[#808080] mb-1 font-normal">
            股票代码（可选）
          </label>
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="例如: 600519"
            disabled={isSubmitting}
            className="w-full px-3 py-2 text-[14px] rounded-md focus:outline-none disabled:bg-[#fafafa] disabled:text-[#808080] font-normal"
            style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}
          />
        </div>

        <div>
          <label className="block text-[12px] text-[#808080] mb-1 font-normal">
            记录买入/卖出
          </label>
          <textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="例如: 已买入 100 股，成交价 12.34&#10;或: 已卖出 100 股，成交价 13.10"
            disabled={isSubmitting}
            rows={3}
            className="w-full px-3 py-2 text-[14px] rounded-md focus:outline-none disabled:bg-[#fafafa] disabled:text-[#808080] font-normal resize-none"
            style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}
          />
        </div>

        <button
          onClick={handleSubmitFeedback}
          disabled={!feedback.trim() || isSubmitting}
          className="w-full px-4 py-2 text-[14px] font-medium rounded-md bg-[#171717] text-white hover:bg-[#000000] disabled:bg-[#ebebeb] disabled:text-[#808080] disabled:cursor-not-allowed transition-colors"
        >
          {isSubmitting ? "提交中..." : "提交记录"}
        </button>
      </div>

      {/* Daily Signal Button */}
      <div className="mt-4 pt-4" style={{ borderTop: '1px solid rgba(0,0,0,0.08)' }}>
        <button
          onClick={handleGenerateSignal}
          disabled={isGeneratingSignal}
          className="w-full px-4 py-2 text-[14px] font-medium rounded-md bg-white text-[#171717] hover:bg-[#fafafa] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}
        >
          {isGeneratingSignal ? "生成中..." : "生成今日信号"}
        </button>
      </div>

      {/* Result Display */}
      {renderResult()}
    </div>
  );
}
