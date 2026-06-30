import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-6 px-6 py-8">
      <header className="border-b border-slate-200 pb-4">
        <h1 className="text-2xl font-semibold">TraderLens</h1>
        <p className="mt-2 text-sm text-slate-600">
          A-share strategy research and execution decision workspace.
        </p>
      </header>

      <section className="grid gap-3 md:grid-cols-3">
        <Link href="/workbench">
          <div className="rounded border border-slate-200 bg-white p-4 hover:border-slate-300 hover:shadow-sm transition-all cursor-pointer">
            <h2 className="text-sm font-medium">Agent Workbench</h2>
            <p className="mt-2 text-sm text-slate-500">和助手对话，启动股票调查或策略验证</p>
            <p className="mt-1 text-xs text-green-600 font-medium">V1 可用</p>
          </div>
        </Link>

        <Link href="/signals">
          <div className="rounded border border-slate-200 bg-white p-4 hover:border-slate-300 hover:shadow-sm transition-all cursor-pointer">
            <h2 className="text-sm font-medium">Signal Board</h2>
            <p className="mt-2 text-sm text-slate-500">查看策略信号，进行人工审核</p>
            <p className="mt-1 text-xs text-green-600 font-medium">M4 可用</p>
          </div>
        </Link>

        <div className="rounded border border-slate-200 bg-white p-4">
          <h2 className="text-sm font-medium">Contracts</h2>
          <p className="mt-2 text-sm text-slate-500">M0 scaffold ready for integration.</p>
        </div>
      </section>
    </main>
  );
}
