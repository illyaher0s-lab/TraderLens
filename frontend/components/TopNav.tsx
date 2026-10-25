import Link from "next/link";

const isCard019IsolatedTest = process.env.NEXT_PUBLIC_CARD019_ISOLATED_TEST === "1";

export default function TopNav({ tip }: { tip?: string | null }) {
  return (
    <>
    <nav className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <div className="flex items-center gap-6">
          <Link href="/" className="text-lg font-semibold text-slate-900">
            TraderLens
          </Link>
          <Link href="/" className="text-sm text-slate-600 hover:text-slate-900">
            今天
          </Link>
          <Link href="/trades/record" className="text-sm text-slate-600 hover:text-slate-900">
            记录成交
          </Link>
          <Link href="/observations" className="text-sm text-slate-600 hover:text-slate-900">
            我的持仓
          </Link>
          <Link href="/#research" className="text-sm text-slate-600 hover:text-slate-900">
            研究
          </Link>
          <Link href="/strategy-validations" className="text-sm text-slate-600 hover:text-slate-900">
            策略验证
          </Link>
        </div>
        {tip && (
          <div className="text-sm text-slate-600">
            {tip}
          </div>
        )}
      </div>
    </nav>
    {isCard019IsolatedTest && (
      <aside role="status" aria-label="隔离测试环境" className="border-b border-amber-300 bg-amber-100 px-6 py-2 text-center text-sm font-semibold text-amber-950">
        隔离测试环境：2026-10-16 历史研究回放，研究待核 · 合成测试成交 · 不代表实时行情、真实账户或正式模拟结果。
      </aside>
    )}
    </>
  );
}
