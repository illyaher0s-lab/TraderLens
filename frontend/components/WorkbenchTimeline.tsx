/**
 * Workbench Timeline Component
 *
 * Task 14: Display session timeline with messages, artifacts, and approval cards.
 * Design: Vercel style - shadow-as-border, minimal icons, clean hierarchy.
 */

"use client";

interface TimelineItem {
  type: string;
  content: any;
}

interface WorkbenchTimelineProps {
  timeline: TimelineItem[];
}

export default function WorkbenchTimeline({ timeline }: WorkbenchTimelineProps) {
  if (timeline.length === 0) {
    return null;
  }

  const renderItem = (item: TimelineItem, idx: number) => {
    switch (item.type) {
      case "message":
        return (
          <div key={idx} className="flex items-start gap-3">
            <div className={`flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-medium ${
              item.content.role === "user" 
                ? "bg-[#171717] text-white" 
                : "bg-[#f0fdf4] text-[#16a34a]"
            }`}>
              {item.content.role === "user" ? "U" : "A"}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[12px] font-medium text-[#171717]">
                {item.content.role === "user" ? "用户" : "助手"}
              </p>
              <p className="text-[12px] text-[#666666] mt-1 break-words font-normal leading-relaxed">
                {item.content.content.substring(0, 100)}
                {item.content.content.length > 100 ? "..." : ""}
              </p>
              {item.content.created_at && (
                <p className="text-[11px] text-[#808080] mt-1">
                  {new Date(item.content.created_at).toLocaleTimeString("zh-CN")}
                </p>
              )}
            </div>
          </div>
        );

      case "artifact_ref":
        // Task 19: Support live loop artifacts with readable labels
        const artifactType = item.content.artifact_type || "artifact";
        const getArtifactLabel = (type: string) => {
          if (type.includes("execution_log")) return "执行记录";
          if (type.includes("observation_position")) return "持仓观察";
          if (type.includes("daily_signal")) return "今日信号";
          if (type.includes("discipline_review")) return "纪律复盘";
          if (type.includes("pnl_record")) return "盈亏记录";
          return type;
        };
        
        return (
          <div key={idx} className="flex items-start gap-3">
            <div className="flex-shrink-0 w-5 h-5 rounded-full bg-[#f3e8ff] flex items-center justify-center text-[10px] font-medium text-[#7c3aed]">
              📎
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[12px] font-medium text-[#171717]">
                {getArtifactLabel(artifactType)}
              </p>
              <p className="text-[11px] text-[#666666] mt-1 font-mono truncate">
                {item.content.artifact_id}
              </p>
            </div>
          </div>
        );

      case "approval_card":
        return (
          <div key={idx} className="flex items-start gap-3">
            <div className="flex-shrink-0 w-5 h-5 rounded-full bg-[#fef3c7] flex items-center justify-center text-[10px] font-medium text-[#f59e0b]">
              ✓
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[12px] font-medium text-[#171717]">审批卡</p>
              <p className="text-[12px] text-[#666666] mt-1 font-normal">
                {item.content.title || "待审批"}
              </p>
            </div>
          </div>
        );

      default:
        return (
          <div key={idx} className="flex items-start gap-3">
            <div className="flex-shrink-0 w-5 h-5 rounded-full bg-[#fafafa] flex items-center justify-center text-[10px] font-medium text-[#808080]">
              •
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[12px] text-[#666666] font-normal">{item.type}</p>
            </div>
          </div>
        );
    }
  };

  return (
    <div className="bg-white rounded-lg p-4" style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}>
      <h3 className="text-[14px] font-semibold text-[#171717] mb-4 tracking-tight">会话时间线</h3>
      <div className="space-y-3">
        {timeline.map((item, idx) => renderItem(item, idx))}
      </div>
      <div className="mt-4 pt-3" style={{ borderTop: '1px solid rgba(0,0,0,0.08)' }}>
        <p className="text-[12px] text-[#808080] font-normal">共 {timeline.length} 项</p>
      </div>
    </div>
  );
}
