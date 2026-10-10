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

import { useEffect, useState } from "react";
import {
  createExecutionCard,
  submitExecutionFeedback,
  lookupExecutionSecurity,
  generateDailySignal,
  type ExecutionCardResponse,
  type ExecutionFeedbackResponse,
  type ExecutionSecurityIdentity,
  type DailySignalResponse,
} from "@/lib/api-client";

const estimateRateCents = (amount: string, rateNumerator: bigint): bigint | null => {
  const match = amount.match(/^(\d+)(?:\.(\d+))?$/);
  if (!match) return null;
  const fraction = match[2] || "";
  const amountUnits = BigInt(`${match[1]}${fraction}`);
  const scale = BigInt(`1${"0".repeat(fraction.length)}`);
  const denominator = scale * BigInt(10_000);
  const numerator = amountUnits * rateNumerator * BigInt(100);
  const remainder = numerator % denominator;
  const rounded = numerator / denominator + (remainder * BigInt(2) >= denominator ? BigInt(1) : BigInt(0));
  return rounded;
};

const formatCents = (cents: bigint): string =>
  `${cents / BigInt(100)}.${(cents % BigInt(100)).toString().padStart(2, "0")}`;

interface LiveLoopPanelProps {
  conversationId: string | null;
  onUpdate?: () => void;
}

export default function LiveLoopPanel({
  conversationId,
  onUpdate,
}: LiveLoopPanelProps) {
  const [symbol, setSymbol] = useState("");
  const [action] = useState<"buy" | "sell">("buy");
  const [tradeType, setTradeType] = useState<"actual" | "simulated" | "">("");
  const [price, setPrice] = useState("");
  const [quantity, setQuantity] = useState("");
  const [executionDate, setExecutionDate] = useState("");
  const [fees, setFees] = useState("");
  const [tradeSource, setTradeSource] = useState<"self_research" | "friend" | "media" | "system_suggestion" | "">("");
  const [reason, setReason] = useState("");
  const [sellReason, setSellReason] = useState<"target" | "stop" | "changed_judgment" | "fear" | "urgent_cash" | "">("");
  const [exitTarget, setExitTarget] = useState("");
  const [exitStop, setExitStop] = useState("");
  const [exitConditions, setExitConditions] = useState("");
  const [securityIdentity, setSecurityIdentity] = useState<ExecutionSecurityIdentity | null>(null);
  const [securityLookupMessage, setSecurityLookupMessage] = useState<string | null>(null);
  const [confirmQuantityAnomaly, setConfirmQuantityAnomaly] = useState(false);
  const [confirmedAlreadyExecuted, setConfirmedAlreadyExecuted] = useState(false);
  const [operationId, setOperationId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isGeneratingSignal, setIsGeneratingSignal] = useState(false);
  const [isCreatingCard, setIsCreatingCard] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<ExecutionCardResponse | ExecutionFeedbackResponse | DailySignalResponse | null>(null);

  useEffect(() => {
    let canceled = false;
    const code = symbol.trim();
    setSecurityIdentity(null);
    setSecurityLookupMessage(null);
    if (!/^\d{6}$/.test(code)) return;

    const timeout = window.setTimeout(() => {
      lookupExecutionSecurity(code)
        .then((identity) => {
          if (!canceled) setSecurityIdentity(identity);
        })
        .catch(() => {
          if (!canceled) setSecurityLookupMessage("名称查询暂不可用；仍可登记，系统会保留身份未知状态。");
        });
    }, 250);
    return () => {
      canceled = true;
      window.clearTimeout(timeout);
    };
  }, [symbol]);

  const tradeAmountPreview = (() => {
    const match = price.trim().match(/^(\d+)(?:\.(\d+))?$/);
    if (!match || !/^\d+$/.test(quantity.trim())) return null;
    try {
      const decimals = match[2] || "";
      const scaledPrice = BigInt(`${match[1]}${decimals}`);
      const amount = scaledPrice * BigInt(quantity.trim());
      const padded = amount.toString().padStart(decimals.length + 1, "0");
      return decimals
        ? `${padded.slice(0, -decimals.length)}.${padded.slice(-decimals.length)}`
        : padded;
    } catch {
      return null;
    }
  })();

  const feePreviewMessage = (() => {
    if (fees.trim()) {
      const entered = Number(fees);
      return Number.isFinite(entered) && entered >= 0
        ? `将按你填写的 ¥${entered.toFixed(2)} 记录；填写 0 表示确认零费用。`
        : "请输入有效费用，或留空。";
    }
    if (tradeType === "actual") return "实际成交留空后费用保持未知。";
    if (tradeType !== "simulated") return "选择交易类型后显示费用说明。";
    if (tradeAmountPreview == null) return "填写成交价和数量后显示费用估算；留空不会把估算写成已确认费用。";

    const commissionCents = estimateRateCents(tradeAmountPreview, BigInt(3));
    if (commissionCents == null) return "成交金额暂不能用于费用估算。";
    const estimatedCommission = commissionCents < BigInt(500) ? BigInt(500) : commissionCents;
    const commissionText = formatCents(estimatedCommission);
    if (securityIdentity?.security_type === "fund") {
      return `模拟费用估算约 ¥${commissionText}（佣金按成交金额0.03%，每单最低¥5；基金不计印花税）。这是应用内估算，不代表券商报价。`;
    }
    if (securityIdentity?.security_type === "stock") {
      if (!executionDate || executionDate < "2023-08-28") {
        return `估算佣金约 ¥${commissionText}；该股票成交日期的印花税不支持估算，费用合计未知。`;
      }
      const stampCents = action === "sell" ? estimateRateCents(tradeAmountPreview, BigInt(5)) : BigInt(0);
      if (stampCents == null) return "印花税暂不能用于估算，费用合计未知。";
      const total = estimatedCommission + stampCents;
      return `模拟费用估算约 ¥${formatCents(total)}（简化佣金最低¥5${action === "sell" ? "，另含按成交日期估算的印花税" : "，买入不计印花税"}）。这是应用内估算，不代表券商报价。`;
    }
    return `估算佣金约 ¥${commissionText}；证券类型未知，税费无法估算，费用合计未知。`;
  })();

  const handleCreateExecutionCard = async () => {
    if (!conversationId) return;

    setIsCreatingCard(true);
    setError(null);
    setLastResult(null);

    try {
      const result = await createExecutionCard(conversationId);
      setLastResult(result);
      onUpdate?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成执行计划失败");
    } finally {
      setIsCreatingCard(false);
    }
  };

  const handleSubmitFeedback = async () => {
    if (!/^\d{6}$/.test(symbol.trim()) || !tradeType || !price.trim() || !quantity.trim() || !executionDate || !confirmedAlreadyExecuted || (action === "sell" && !sellReason)) return;

    setIsSubmitting(true);
    setError(null);
    setLastResult(null);

    try {
      const requestOperationId = operationId || crypto.randomUUID();
      setOperationId(requestOperationId);
      if (fees.trim() && (!Number.isFinite(Number(fees)) || Number(fees) < 0)) {
        throw new Error("手续费必须是大于或等于 0 的有效数字");
      }
      const result = await submitExecutionFeedback({
        symbol: symbol.trim(),
        action,
        trade_type: tradeType,
        price: price.trim(),
        quantity: Number(quantity),
        execution_date: executionDate,
        operation_id: requestOperationId,
        confirmed_already_executed: true,
        fees: fees.trim() ? fees.trim() : undefined,
        trade_source: tradeSource || undefined,
        reason: action === "buy" && reason.trim() ? reason.trim() : undefined,
        sell_reason: action === "sell" && sellReason ? sellReason : undefined,
        exit_plan_target_price: action === "buy" && exitTarget.trim() ? exitTarget.trim() : undefined,
        exit_plan_stop_price: action === "buy" && exitStop.trim() ? exitStop.trim() : undefined,
        exit_plan_conditions: action === "buy" && exitConditions.trim() ? exitConditions.trim() : undefined,
        confirm_quantity_anomaly: confirmQuantityAnomaly,
      });

      setLastResult(result);
      setSymbol("");
      setTradeType("");
      setPrice("");
      setQuantity("");
      setExecutionDate("");
      setFees("");
      setTradeSource("");
      setReason("");
      setSellReason("");
      setExitTarget("");
      setExitStop("");
      setExitConditions("");
      setConfirmQuantityAnomaly(false);
      setConfirmedAlreadyExecuted(false);
      setOperationId(null);
      onUpdate?.();
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
      onUpdate?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成信号失败");
    } finally {
      setIsGeneratingSignal(false);
    }
  };

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
          <p className="text-[12px] text-[#666666]">
            {lastResult.record_source === "autonomous_manual" ? "自主成交记录 · 未关联已验证计划" : ""}
          </p>
          {lastResult.trade_type && (
            <p className="text-[12px] text-[#666666]">
              {lastResult.trade_type === "simulated" ? "模拟记录" : "实际交易记录"}
            </p>
          )}
          {lastResult.position_id && (
            <p className="text-[12px] text-[#22c55e] font-mono">
              持仓 ID: {lastResult.position_id}
            </p>
          )}
          <p className="text-[12px] text-[#666666] mt-1">
            本次费用：{lastResult.fees != null
              ? `¥${lastResult.fees.toFixed(2)}（已确认）`
              : lastResult.fee_calculation?.amount != null
                ? `约¥${lastResult.fee_calculation.amount.toFixed(2)}（估算）`
                : lastResult.fee_calculation?.estimated_amount != null
                  ? `估算佣金约¥${lastResult.fee_calculation.estimated_amount.toFixed(2)}，税费未知`
                  : "未知"}
          </p>
          {lastResult.action === "sell" && (
            <p className="text-[14px] text-[#171717] mt-2">
              毛盈亏（未扣费用）：{lastResult.gross_pnl_amount == null || lastResult.gross_pnl_pct == null
                ? "信息不足，无法判断"
                : `${lastResult.gross_pnl_amount >= 0 ? "+" : "-"}¥${Math.abs(lastResult.gross_pnl_amount).toFixed(2)}（${lastResult.gross_pnl_pct >= 0 ? "+" : "-"}${Math.abs(lastResult.gross_pnl_pct * 100).toFixed(2)}%）`}
            </p>
          )}
          {lastResult.trade_amount && (
            <p className="text-[12px] text-[#666666] mt-1">成交金额：¥{lastResult.trade_amount}</p>
          )}
          {lastResult.action === "sell" && lastResult.realized_pnl == null && (
            <p className="text-[14px] text-[#92400e] mt-2">
              扣费净盈亏未核：{lastResult.pnl_missing_fields?.includes("execution_rule")
                ? "模拟交易日期无法核实"
                : lastResult.pnl_missing_fields?.includes("fees")
                  ? "未扣费用"
                  : lastResult.pnl_missing_fields?.includes("matching_quantity")
                    ? "卖出数量超过可匹配持仓，信息不足，无法判断净盈亏"
                    : lastResult.pnl_missing_fields?.includes("buy_log")
                      ? "缺少匹配买入记录，信息不足，无法判断净盈亏"
                      : "缺少可匹配的自主记录持仓，信息不足，无法判断净盈亏"}
            </p>
          )}
          {lastResult.realized_pnl != null && (
            <div className="mt-2 pt-2" style={{ borderTop: '1px solid rgba(34,197,94,0.2)' }}>
              <p className="text-[14px] font-medium text-[#171717]">
                {lastResult.pnl_fee_calculation?.source === "simulated_estimate"
                  ? "扣估算费用后盈亏"
                  : lastResult.pnl_fee_calculation?.source === "mixed"
                    ? "扣估算及已确认费用后盈亏"
                    : "扣费用后盈亏"}（分红未核）: {lastResult.realized_pnl >= 0 ? "+" : "-"}¥{Math.abs(lastResult.realized_pnl).toFixed(2)}
                {lastResult.pnl_pct != null && (
                  <span className="ml-2 text-[#666666]">
                    ({lastResult.pnl_pct >= 0 ? "+" : ""}{(lastResult.pnl_pct * 100).toFixed(2)}%)
                  </span>
                )}
              </p>
            </div>
          )}
          {lastResult.action === "sell" && lastResult.discipline_review_id && (
            <p className="text-[12px] text-[#666666] mt-1">
              本次卖出复盘已保存，可在观察池查看。
            </p>
          )}
          {lastResult.warnings?.map((warning, index) => (
            <p key={index} className="text-[12px] text-[#92400e] mt-2">{warning}</p>
          ))}
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

      if (lastResult.status === "market_data_unavailable") {
        return (
          <div className="mt-4 p-4 rounded-lg bg-[#fef3c7]" style={{ boxShadow: '0px 0px 0px 1px rgba(251,191,36,0.2)' }}>
            <p className="text-[14px] text-[#92400e]">
              {lastResult.message || "行情不可用，未生成信号"}
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
        这里只登记已完成的成交，不会下单。请核对 T+1、停牌及涨跌停异常。
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
      {conversationId && (
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
      )}

      {/* Feedback Input */}
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[12px] text-[#808080] mb-1 font-normal">方向</label>
            <div className="w-full px-3 py-2 text-[14px] rounded-md bg-[#fafafa] text-[#666666]" style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}>
              买入（卖出请从观察池的现有持仓登记）
            </div>
          </div>
          <div>
            <label className="block text-[12px] text-[#808080] mb-1 font-normal">六位证券代码</label>
            <input
              type="text"
              inputMode="numeric"
              maxLength={6}
              value={symbol}
              onChange={(e) => { setSymbol(e.target.value.replace(/\D/g, "").slice(0, 6)); setOperationId(null); }}
              placeholder="例如：510880"
              disabled={isSubmitting}
              className="w-full px-3 py-2 text-[14px] rounded-md focus:outline-none disabled:bg-[#fafafa] disabled:text-[#808080] font-normal"
              style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}
            />
          </div>
        </div>

        <div>
          <label className="block text-[12px] text-[#808080] mb-1 font-normal">记录类型</label>
          <select
            value={tradeType}
            onChange={(e) => { setTradeType(e.target.value as typeof tradeType); setConfirmedAlreadyExecuted(false); setOperationId(null); }}
            disabled={isSubmitting}
            required
            className="w-full px-3 py-2 text-[14px] rounded-md bg-white"
            style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}
          >
            <option value="">请选择实际或模拟</option>
            <option value="actual">实际交易</option>
            <option value="simulated">模拟交易</option>
          </select>
        </div>

        <div>
          <label className="block text-[12px] text-[#808080] mb-1 font-normal">证券名称（系统核实后自动带出）</label>
          <input
            type="text"
            readOnly
            value={securityIdentity?.name || ""}
            placeholder={securityLookupMessage ? "未核实" : symbol.length === 6 ? "查询中或无可靠名称" : "输入六位代码后查询"}
            className="w-full px-3 py-2 text-[14px] rounded-md bg-[#fafafa] text-[#666666]"
            style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}
          />
          <p className="mt-1 text-[11px] text-[#999999]">
            {securityLookupMessage || (securityIdentity?.status === "verified"
              ? `身份已核实 · ${securityIdentity.security_type === "fund" ? "场内基金，基金份额" : "股票，股"}`
              : securityIdentity?.status === "unknown" ? "未找到可靠身份；仍可登记，名称和交易单位将保留未知。"
              : symbol.length !== 6 ? "输入六位代码后查询；查询失败只影响身份显示，不影响已成交事实登记。"
                : "名称查询暂未返回；仍可登记，系统会保留身份未知状态。")}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[12px] text-[#808080] mb-1 font-normal">成交价（元）</label>
            <input
              type="text"
              inputMode="decimal"
              value={price}
              onChange={(e) => { setPrice(e.target.value); setOperationId(null); }}
              placeholder="ETF可录入三位小数"
              disabled={isSubmitting}
              className="w-full px-3 py-2 text-[14px] rounded-md"
              style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}
            />
          </div>
          <div>
            <label className="block text-[12px] text-[#808080] mb-1 font-normal">成交数量（{securityIdentity?.quantity_unit === "share" ? "股" : securityIdentity?.quantity_unit === "fund_share" ? "基金份额" : "单位未知"}）</label>
            <input
              type="number"
              min="1"
              step="1"
              value={quantity}
              onChange={(e) => { setQuantity(e.target.value); setOperationId(null); }}
              disabled={isSubmitting}
              className="w-full px-3 py-2 text-[14px] rounded-md"
              style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}
            />
          </div>
        </div>
        <p className="text-[12px] text-[#666666]">
          成交金额：{tradeAmountPreview == null ? "填写价格和数量后计算" : `¥${tradeAmountPreview}`}
        </p>

        {action === "sell" && (
          <div>
            <label className="block text-[12px] text-[#808080] mb-1 font-normal">卖出原因</label>
            <select
              value={sellReason}
              onChange={(e) => { setSellReason(e.target.value as typeof sellReason); setOperationId(null); }}
              disabled={isSubmitting}
              className="w-full px-3 py-2 text-[14px] rounded-md bg-white"
              style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}
            >
              <option value="">请选择卖出原因</option>
              <option value="target">达到目标</option>
              <option value="stop">触及止损</option>
              <option value="changed_judgment">判断改变</option>
              <option value="fear">恐惧</option>
              <option value="urgent_cash">急需用钱</option>
            </select>
          </div>
        )}

        <div>
          <label className="block text-[12px] text-[#808080] mb-1 font-normal">成交来源</label>
          <select
            value={tradeSource}
            onChange={(e) => { setTradeSource(e.target.value as typeof tradeSource); setOperationId(null); }}
            disabled={isSubmitting}
            className="w-full px-3 py-2 text-[14px] rounded-md bg-white"
            style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}
          >
            <option value="">暂不填写</option>
            <option value="self_research">自己研究</option>
            <option value="friend">朋友推荐</option>
            <option value="media">媒体信息</option>
            <option value="system_suggestion">系统建议</option>
          </select>
        </div>

        {action === "buy" && (
          <div>
            <label className="block text-[12px] text-[#808080] mb-1 font-normal">买入理由（选填）</label>
            <input
              type="text"
              maxLength={160}
              value={reason}
              onChange={(e) => { setReason(e.target.value); setOperationId(null); }}
              placeholder="不确定或不记得时可留空"
              disabled={isSubmitting}
              className="w-full px-3 py-2 text-[14px] rounded-md"
              style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}
            />
          </div>
        )}

        {action === "buy" && (
          <fieldset className="space-y-2 rounded-md p-3" style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}>
            <legend className="px-1 text-[12px] text-[#666666]">个人退出计划（可选）</legend>
            <p className="text-[11px] text-[#92400e]">
              这是成交后录入的个人回忆，不证明这些计划在成交前已经存在，也不会关联系统 Action Plan。
            </p>
            <div className="grid grid-cols-2 gap-3">
              <input type="text" inputMode="decimal" value={exitTarget} onChange={(e) => { setExitTarget(e.target.value); setOperationId(null); }} placeholder="目标价（元）" className="w-full px-3 py-2 text-[13px] rounded-md" style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }} />
              <input type="text" inputMode="decimal" value={exitStop} onChange={(e) => { setExitStop(e.target.value); setOperationId(null); }} placeholder="止损价（元）" className="w-full px-3 py-2 text-[13px] rounded-md" style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }} />
            </div>
            <input type="text" maxLength={300} value={exitConditions} onChange={(e) => { setExitConditions(e.target.value); setOperationId(null); }} placeholder="退出条件（可留空）" className="w-full px-3 py-2 text-[13px] rounded-md" style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }} />
            {securityIdentity?.security_type === "stock" && Number(quantity) > 0 && Number(quantity) % 100 !== 0 && (
              <p className="text-[12px] text-[#92400e]">系统核实为股票且买入数量不是100股整数倍；请核对记录类型和成交事实。</p>
            )}
            <label className="flex items-start gap-2 text-[12px] text-[#666666]">
              <input type="checkbox" checked={confirmQuantityAnomaly} onChange={(e) => { setConfirmQuantityAnomaly(e.target.checked); setOperationId(null); }} disabled={isSubmitting} className="mt-0.5" />
              <span>若系统核实为股票且数量异常，我确认数量与这笔成交记录一致。</span>
            </label>
          </fieldset>
        )}

        <div>
          <label className="block text-[12px] text-[#808080] mb-1 font-normal">
            成交日期
          </label>
          <input
            type="date"
            value={executionDate}
            onChange={(e) => { setExecutionDate(e.target.value); setOperationId(null); }}
            disabled={isSubmitting}
            required
            className="w-full px-3 py-2 text-[14px] rounded-md focus:outline-none disabled:bg-[#fafafa] disabled:text-[#808080] font-normal"
            style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}
          />
          <p className="mt-1 text-[11px] text-[#999999]">填写本次记录的成交日；系统另行保存录入时间。补录个人计划会标记为事后回忆。</p>
        </div>

        <div>
          <label className="block text-[12px] text-[#808080] mb-1 font-normal">
            确认本次成交费用（元；可留空）
          </label>
          <input
            type="text"
            inputMode="decimal"
            min="0"
            step="0.01"
            value={fees}
            onChange={(e) => { setFees(e.target.value); setOperationId(null); }}
            placeholder="留空使用模拟估算；填写 0 表示确认零费用"
            disabled={isSubmitting}
            className="w-full px-3 py-2 text-[14px] rounded-md focus:outline-none disabled:bg-[#fafafa] disabled:text-[#808080] font-normal"
            style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}
          />
          <p className="mt-1 text-[11px] text-[#666666]">{feePreviewMessage}</p>
        </div>

        <label className="flex items-start gap-2 text-[12px] text-[#666666]">
          <input
            type="checkbox"
            checked={confirmedAlreadyExecuted}
            onChange={(e) => { setConfirmedAlreadyExecuted(e.target.checked); setOperationId(null); }}
            disabled={isSubmitting}
            className="mt-0.5"
          />
          <span>{tradeType === "simulated" ? "我确认这是模拟成交记录；本页面只做记录，不会提交订单。" : "我确认这笔实际交易已经成交；本页面只做记录，不会提交订单。"}</span>
        </label>

        <button
          onClick={handleSubmitFeedback}
          disabled={!/^\d{6}$/.test(symbol.trim()) || !tradeType || !price.trim() || !quantity.trim() || !executionDate || !confirmedAlreadyExecuted || (action === "sell" && !sellReason) || isSubmitting}
          className="w-full px-4 py-2 text-[14px] font-medium rounded-md bg-[#171717] text-white hover:bg-[#000000] disabled:bg-[#ebebeb] disabled:text-[#808080] disabled:cursor-not-allowed transition-colors"
        >
          {isSubmitting ? "提交中..." : "提交记录"}
        </button>
      </div>

      {/* Daily Signal Button */}
      {conversationId && (
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
      )}

      {/* Result Display */}
      {renderResult()}
    </div>
  );
}
