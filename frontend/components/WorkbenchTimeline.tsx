/**
 * Workbench Timeline Component
 *
 * Task 14: Display session timeline with messages, artifacts, and approval cards.
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
            <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
              item.content.role === "user" 
                ? "bg-blue-100 text-blue-700" 
                : "bg-green-100 text-green-700"
            }`}>
              {item.content.role === "user" ? "U" : "A"}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-[#171717]">
                {item.content.role === "user" ? "用户" : "助手"}
              </p>
              <p className="text-xs text-[#666666] mt-1 break-words">
                {item.content.content.substring(0, 100)}
                {item.content.content.length > 100 ? "..." : ""}
              </p>
              {item.content.created_at && (
                <p className="text-xs text-[#808080] mt-1">
                  {new Date(item.content.created_at).toLocaleTimeString("zh-CN")}
                </p>
              )}
            </div>
          </div>
        );

      case "artifact_ref":
        return (
          <div key={idx} className="flex items-start gap-3">
            <div className="flex-shrink-0 w-6 h-6 rounded-full bg-purple-100 flex items-center justify-center text-xs font-medium text-purple-700">
              📎
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-[#171717]">
                {item.content.artifact_type || "artifact"}
              </p>
              <p className="text-xs text-[#666666] mt-1 font-mono truncate">
                {item.content.artifact_id}
              </p>
            </div>
          </div>
        );

      case "approval_card":
        return (
          <div key={idx} className="flex items-start gap-3">
            <div className="flex-shrink-0 w-6 h-6 rounded-full bg-yellow-100 flex items-center justify-center text-xs font-medium text-yellow-700">
              ✓
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-[#171717]">审批卡</p>
              <p className="text-xs text-[#666666] mt-1">
                {item.content.title || "待审批"}
              </p>
            </div>
          </div>
        );

      default:
        return (
          <div key={idx} className="flex items-start gap-3">
            <div className="flex-shrink-0 w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center text-xs font-medium text-gray-700">
              •
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-[#666666]">{item.type}</p>
            </div>
          </div>
        );
    }
  };

  return (
    <div className="bg-white rounded-lg border border-[#ebebeb] p-4">
      <h3 className="text-sm font-semibold text-[#171717] mb-4">会话时间线</h3>
      <div className="space-y-3">
        {timeline.map((item, idx) => renderItem(item, idx))}
      </div>
      <div className="mt-4 pt-3 border-t border-[#ebebeb]">
        <p className="text-xs text-[#808080]">共 {timeline.length} 项</p>
      </div>
    </div>
  );
}
