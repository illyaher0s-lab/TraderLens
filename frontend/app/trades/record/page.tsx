import LiveLoopPanel from "@/components/LiveLoopPanel";
import TopNav from "@/components/TopNav";

export const metadata = {
  title: "记录成交 | TraderLens",
};

export default function TradeRecordPage() {
  return (
    <>
      <TopNav />
      <div className="min-h-screen bg-[#fafafa]">
        <main className="mx-auto max-w-3xl p-6">
        <header className="my-5">
          <h1 className="text-[24px] font-semibold text-[#171717]">
            记录一笔已完成的成交
          </h1>
          <p className="mt-2 text-[14px] text-[#666666]">
            这里只登记你已经完成的交易，不会下单；这笔自主成交不会关联未验证的计划。
          </p>
        </header>
          <LiveLoopPanel conversationId={null} />
        </main>
      </div>
    </>
  );
}
