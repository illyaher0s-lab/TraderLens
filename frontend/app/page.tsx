"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

interface DashboardData {
  as_of_date: string;
  open_observations: {
    count: number;
    items: Array<{
      position_id: string;
      symbol: string;
      name: string;
      entry_price: number;
      opened_at: string;
    }>;
  };
  today_signals: {
    count: number;
    items: Array<{
      stock_code: string;
      stock_name: string;
      signal_type: string | null;
      signal_date: string;
    }>;
  };
  strategy_workspace: {
    ideas_count: number;
    candidates_count: number;
    rejected_count: number;
    validations_count: number;
    approved_strategies_count: number;
    templates_count: number;
  };
  recent_reviews: {
    count: number;
    items: any[];
  };
  data_state: string;
}

export default function DailyCommandCenter() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("http://localhost:8010/api/dashboard/today")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch dashboard data");
        return res.json();
      })
      .then((data) => {
        setData(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-6 py-8">
        <div className="text-sm text-slate-500">加载中...</div>
      </main>
    );
  }

  if (error || !data) {
    return (
      <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-6 py-8">
        <div className="text-sm text-red-600">加载失败: {error}</div>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-6 py-8">
      {/* Header */}
      <header className="border-b border-slate-200 pb-4">
        <h1 className="text-2xl font-semibold text-slate-900">每日工作台</h1>
        <p className="mt-1 text-sm text-slate-500">
          {data.as_of_date} · TraderLens Daily Command Center
        </p>
      </header>

      {/* Quick Actions */}
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Link
          href="/workbench"
          className="rounded-lg border border-slate-200 bg-white p-4 transition-all hover:border-slate-300 hover:shadow-sm"
        >
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
            对话入口
          </div>
          <div className="mt-2 text-sm font-medium text-slate-900">
            Agent Workbench
          </div>
        </Link>

        <Link
          href="/observations"
          className="rounded-lg border border-slate-200 bg-white p-4 transition-all hover:border-slate-300 hover:shadow-sm"
        >
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
            观察池
          </div>
          <div className="mt-2 text-sm font-medium text-slate-900">
            Observation Pool
          </div>
        </Link>

        <Link
          href="/signals"
          className="rounded-lg border border-slate-200 bg-white p-4 transition-all hover:border-slate-300 hover:shadow-sm"
        >
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
            信号板
          </div>
          <div className="mt-2 text-sm font-medium text-slate-900">
            Signal Board
          </div>
        </Link>

        <Link
          href="/strategies"
          className="rounded-lg border border-slate-200 bg-white p-4 transition-all hover:border-slate-300 hover:shadow-sm"
        >
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
            策略工作区
          </div>
          <div className="mt-2 text-sm font-medium text-slate-900">
            Strategy Workspace
          </div>
        </Link>
      </section>

      {/* Main Content Grid */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Open Observations */}
        <section className="rounded-lg border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-4 py-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-900">
                持仓观察
              </h2>
              <Link
                href="/observations"
                className="text-xs font-medium text-blue-600 hover:text-blue-700"
              >
                查看全部 →
              </Link>
            </div>
          </div>
          <div className="p-4">
            {data.open_observations.count === 0 ? (
              <div className="py-6 text-center text-sm text-slate-500">
                暂无持仓观察
              </div>
            ) : (
              <div className="space-y-2">
                <div className="mb-3 text-xs text-slate-500">
                  {data.open_observations.count} 个持仓
                </div>
                {data.open_observations.items.map((obs) => (
                  <Link
                    key={obs.position_id}
                    href={`/observations/${obs.position_id}`}
                    className="block rounded border border-slate-100 p-3 transition-colors hover:bg-slate-50"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="text-sm font-medium text-slate-900">
                          {obs.symbol}
                        </div>
                        <div className="mt-1 text-xs text-slate-500">
                          {obs.name}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-xs text-slate-500">
                          ¥{obs.entry_price.toFixed(2)}
                        </div>
                        <div className="mt-1 text-xs text-slate-400">
                          {new Date(obs.opened_at).toLocaleDateString()}
                        </div>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </section>

        {/* Today Signals */}
        <section className="rounded-lg border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-4 py-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-900">
                今日信号
              </h2>
              <Link
                href="/signals"
                className="text-xs font-medium text-blue-600 hover:text-blue-700"
              >
                查看全部 →
              </Link>
            </div>
          </div>
          <div className="p-4">
            {data.today_signals.count === 0 ? (
              <div className="py-6 text-center text-sm text-slate-500">
                今日暂无信号
              </div>
            ) : (
              <div className="space-y-2">
                <div className="mb-3 text-xs text-slate-500">
                  {data.today_signals.count} 条信号
                </div>
                {data.today_signals.items.map((sig, idx) => (
                  <div
                    key={idx}
                    className="rounded border border-slate-100 p-3"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="text-sm font-medium text-slate-900">
                          {sig.stock_code}
                        </div>
                        <div className="mt-1 text-xs text-slate-500">
                          {sig.stock_name}
                        </div>
                      </div>
                      <div className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                        {sig.signal_type || "N/A"}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        {/* Strategy Workspace */}
        <section className="rounded-lg border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-4 py-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-900">
                策略工作区
              </h2>
              <Link
                href="/strategies"
                className="text-xs font-medium text-blue-600 hover:text-blue-700"
              >
                查看详情 →
              </Link>
            </div>
          </div>
          <div className="p-4">
            <div className="grid grid-cols-2 gap-3">
              <Link
                href="/strategy-ideas"
                className="rounded border border-slate-100 p-3 transition-colors hover:bg-slate-50"
              >
                <div className="text-xs text-slate-500">策略想法</div>
                <div className="mt-1 text-lg font-semibold text-slate-900">
                  {data.strategy_workspace.ideas_count}
                </div>
              </Link>

              <Link
                href="/candidate-strategies"
                className="rounded border border-slate-100 p-3 transition-colors hover:bg-slate-50"
              >
                <div className="text-xs text-slate-500">待批准</div>
                <div className="mt-1 text-lg font-semibold text-slate-900">
                  {data.strategy_workspace.candidates_count}
                </div>
              </Link>

              <Link
                href="/rejected-strategies"
                className="rounded border border-slate-100 p-3 transition-colors hover:bg-slate-50"
              >
                <div className="text-xs text-slate-500">已拒绝</div>
                <div className="mt-1 text-lg font-semibold text-slate-900">
                  {data.strategy_workspace.rejected_count}
                </div>
              </Link>

              <Link
                href="/strategy-validations"
                className="rounded border border-slate-100 p-3 transition-colors hover:bg-slate-50"
              >
                <div className="text-xs text-slate-500">验证案例</div>
                <div className="mt-1 text-lg font-semibold text-slate-900">
                  {data.strategy_workspace.validations_count}
                </div>
              </Link>

              <Link
                href="/strategies"
                className="rounded border border-slate-100 p-3 transition-colors hover:bg-slate-50"
              >
                <div className="text-xs text-slate-500">已批准策略</div>
                <div className="mt-1 text-lg font-semibold text-slate-900">
                  {data.strategy_workspace.approved_strategies_count}
                </div>
              </Link>

              <Link
                href="/strategy-templates"
                className="rounded border border-slate-100 p-3 transition-colors hover:bg-slate-50"
              >
                <div className="text-xs text-slate-500">策略模板</div>
                <div className="mt-1 text-lg font-semibold text-slate-900">
                  {data.strategy_workspace.templates_count}
                </div>
              </Link>
            </div>
          </div>
        </section>

        {/* Recent Reviews */}
        <section className="rounded-lg border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-4 py-3">
            <h2 className="text-sm font-semibold text-slate-900">
              近期复盘
            </h2>
          </div>
          <div className="p-4">
            {data.recent_reviews.count === 0 ? (
              <div className="py-6 text-center text-sm text-slate-500">
                暂无复盘记录
              </div>
            ) : (
              <div className="space-y-2">
                {data.recent_reviews.items.map((review, idx) => (
                  <div
                    key={idx}
                    className="rounded border border-slate-100 p-3"
                  >
                    <div className="text-sm font-medium text-slate-900">
                      {review.title}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
