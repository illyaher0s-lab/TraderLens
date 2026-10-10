import Link from "next/link";

export default function TopNav({ tip }: { tip?: string | null }) {
  return (
    <nav className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <div className="flex items-center gap-6">
          <Link href="/" className="text-lg font-semibold text-slate-900">
            TraderLens
          </Link>
          <Link href="/" className="text-sm text-slate-600 hover:text-slate-900">
            首页
          </Link>
          <Link href="/trades/record" className="text-sm text-slate-600 hover:text-slate-900">
            记录成交
          </Link>
          <Link href="/observations" className="text-sm text-slate-600 hover:text-slate-900">
            我的持仓
          </Link>
        </div>
        {tip && (
          <div className="text-sm text-slate-600">
            {tip}
          </div>
        )}
      </div>
    </nav>
  );
}
