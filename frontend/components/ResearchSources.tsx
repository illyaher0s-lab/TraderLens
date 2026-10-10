type ResearchSource = {
  source_record_id?: string;
  source_type?: string;
  source_quality?: string;
  title?: string;
  published_at?: string | null;
  retrieved_at?: string | null;
  summary?: string;
  source_url?: string;
  gaps?: string[];
};

type ResearchSourcesProps = {
  sources?: ResearchSource[] | null;
  compact?: boolean;
};

const sourceTypeLabels: Record<string, string> = {
  announcement: "公告",
  financial_report: "财务报告",
  prospectus: "招股书",
  interaction_platform: "互动平台",
  news: "新闻",
  social_media: "社交媒体",
  unknown: "类型未知",
};

const sourceIdPrefixLabels: Record<string, string> = {
  financials: "财务事实",
  stock_company: "公司主营",
  announcements: "公司公告",
};

function getSafeSourceUrl(value?: string): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

function formatGap(gap: string): string {
  return gap === "full_text_unavailable"
    ? "全文不可用（full_text_unavailable）"
    : gap;
}

export default function ResearchSources({
  sources,
  compact = false,
}: ResearchSourcesProps) {
  if (!Array.isArray(sources) || sources.length === 0) return null;

  return (
    <section aria-label="研究来源" className={compact ? "mt-2" : "border-t border-[#ebebeb] pt-4"}>
      <h3 className={compact ? "font-medium text-[#171717]" : "text-[16px] font-semibold text-[#171717] mb-2"}>
        研究来源
      </h3>
      <ul className="space-y-2 mt-1">
        {sources.map((source, index) => {
          const sourceId = source.source_record_id?.trim();
          const sourceTypeLabel = sourceTypeLabels[source.source_type || "unknown"] || "类型未知";
          const sourcePrefix = sourceId?.split(":", 1)[0] || "";
          const categoryLabel = sourceIdPrefixLabels[sourcePrefix] || sourceTypeLabel;
          const title = source.title?.trim() || categoryLabel;
          const sourceUrl = getSafeSourceUrl(source.source_url);
          const gaps = Array.isArray(source.gaps) ? source.gaps.filter(Boolean) : [];

          return (
            <li
              key={`${sourceId || source.source_url || source.source_type || "source"}-${index}`}
              className="rounded border border-[#ebebeb] bg-[#fafafa] p-3 space-y-1 text-[13px]"
            >
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <span className="text-[11px] text-[#666666]">来源类别：{categoryLabel}</span>
                {sourceTypeLabel !== categoryLabel && (
                  <span className="text-[11px] text-[#666666]">来源类型：{sourceTypeLabel}</span>
                )}
                <span className="text-[11px] text-[#666666]">
                  来源质量：{source.source_quality || "unknown"}
                </span>
                <h4 className="font-medium text-[#171717]">{title}</h4>
                {source.published_at && (
                  <time className="text-[12px] text-[#666666]" dateTime={source.published_at}>
                    发布日期：{source.published_at}
                  </time>
                )}
                {source.retrieved_at && (
                  <time className="text-[12px] text-[#666666]" dateTime={source.retrieved_at}>
                    获取时间：{source.retrieved_at}
                  </time>
                )}
              </div>
              {source.summary && (
                <p className="text-[#333333] whitespace-pre-wrap">摘要：{source.summary}</p>
              )}
              {sourceId && <p className="text-[11px] text-[#808080]">来源 ID：{sourceId}</p>}
              {sourceUrl && (
                <a
                  className="block text-[12px] text-blue-700 underline break-all"
                  href={sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  来源 URL：{sourceUrl}
                </a>
              )}
              {gaps.length > 0 && (
                <p className="text-[12px] text-amber-800">
                  证据缺口：{gaps.map(formatGap).join("；")}
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
