export interface StrategyValidationStatus {
  status: "watch" | "unavailable";
  user_facing_level: "watch" | "unavailable";
  actionable: boolean;
  candidate_is_signal: boolean;
  reason_code: string;
  title: string;
  message: string;
  missing: string[];
  b4_verified: boolean;
  b4_summary: {
    artifact_id: string;
    supplement_id: string;
    protocol_snapshot_id: string;
    strategy_revision_id: string;
    is_range: { start: string; end: string };
    future_violations: number;
    oos_read_count: number;
  } | null;
  audit_sha256: string | null;
}

const MISSING_LABELS: Record<string, string> = {
  base_cost: "基础交易成本核验",
  stress_cost: "成本压力核验",
  benchmark_comparison: "市场基准比较",
  same_universe_control_comparison: "同股票池对照",
};

export default function StrategyValidationStatusCard({
  status,
}: {
  status: StrategyValidationStatus;
}) {
  const unavailable = status.status === "unavailable";
  return (
    <section
      data-testid="strategy-validation-status"
      className={`mb-6 rounded-lg border p-5 ${
        unavailable
          ? "border-slate-200 bg-slate-50"
          : "border-amber-200 bg-amber-50"
      }`}
      data-reason-code={status.reason_code}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          策略验证状态
        </div>
        <div className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-700">
          {unavailable ? "状态暂不可用" : "观察 / 暂不可执行"}
        </div>
      </div>
      <h2 className="mt-3 text-base font-semibold text-slate-900">{status.title}</h2>
      <p className="mt-2 text-sm leading-6 text-slate-700">{status.message}</p>
      {!unavailable && (
        <p className="mt-2 text-xs font-medium text-amber-800">
          当前是验证阻断，不是“无信号”；actionable=false，不能作为买卖依据。
        </p>
      )}
      {status.missing.length > 0 && (
        <details className="mt-3 text-sm text-slate-700">
          <summary className="cursor-pointer font-medium">查看尚未完成的验证项</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {status.missing.map((item) => (
              <li key={item}>{MISSING_LABELS[item] || "验证项暂不可用"}</li>
            ))}
          </ul>
        </details>
      )}
      {status.b4_verified && status.b4_summary && (
        <div className="mt-4 border-t border-amber-200 pt-3 text-xs text-slate-600">
          <div>历史回测已验证：{status.b4_summary.is_range.start} 至 {status.b4_summary.is_range.end}</div>
          <div className="mt-1">
            B4：{status.b4_summary.artifact_id}；未来数据违规 {status.b4_summary.future_violations} 次；OOS 未读取。
          </div>
        </div>
      )}
    </section>
  );
}
