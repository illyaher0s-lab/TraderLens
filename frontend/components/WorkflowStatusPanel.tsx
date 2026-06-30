/**
 * Workflow Status Panel
 *
 * Task 14: Display current workflow status and metadata.
 */

"use client";

interface WorkflowStatusPanelProps {
  session: {
    session_id: string;
    workflow_kind: string;
    workflow_state: string;
    title: string;
    created_at: string;
    updated_at: string;
  } | null;
  artifactCount: number;
}

const WORKFLOW_LABELS: Record<string, string> = {
  friend_stock: "朋友推荐股票",
  strategy_idea: "抖音策略验证",
};

const STATE_LABELS: Record<string, string> = {
  created: "已创建",
  researching: "研究中",
  waiting_for_approval: "等待审批",
  validating: "验证中",
  live_execution_pending: "等待实盘",
  observing: "观察中",
  reviewing: "复盘中",
  completed: "已完成",
  stopped: "已停止",
};

const STATE_COLORS: Record<string, string> = {
  created: "bg-gray-100 text-gray-700",
  researching: "bg-blue-100 text-blue-700",
  waiting_for_approval: "bg-yellow-100 text-yellow-700",
  validating: "bg-purple-100 text-purple-700",
  live_execution_pending: "bg-orange-100 text-orange-700",
  observing: "bg-green-100 text-green-700",
  reviewing: "bg-indigo-100 text-indigo-700",
  completed: "bg-green-200 text-green-800",
  stopped: "bg-red-100 text-red-700",
};

export default function WorkflowStatusPanel({
  session,
  artifactCount,
}: WorkflowStatusPanelProps) {
  if (!session) {
    return (
      <div className="bg-white rounded-lg border border-[#ebebeb] p-6">
        <h3 className="text-sm font-semibold text-[#171717] mb-4">工作流状态</h3>
        <p className="text-sm text-[#666666]">暂无活动会话</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-[#ebebeb] p-6">
      <h3 className="text-sm font-semibold text-[#171717] mb-4">工作流状态</h3>

      <div className="space-y-4">
        <div>
          <p className="text-xs text-[#808080] mb-1">工作流类型</p>
          <p className="text-sm font-medium text-[#171717]">
            {WORKFLOW_LABELS[session.workflow_kind] || session.workflow_kind}
          </p>
        </div>

        <div>
          <p className="text-xs text-[#808080] mb-1">当前状态</p>
          <span
            className={`inline-block px-2 py-1 text-xs font-medium rounded ${
              STATE_COLORS[session.workflow_state] || "bg-gray-100 text-gray-700"
            }`}
          >
            {STATE_LABELS[session.workflow_state] || session.workflow_state}
          </span>
        </div>

        <div>
          <p className="text-xs text-[#808080] mb-1">会话标题</p>
          <p className="text-sm text-[#171717]">{session.title}</p>
        </div>

        <div>
          <p className="text-xs text-[#808080] mb-1">关联证据</p>
          <p className="text-sm text-[#171717]">{artifactCount} 项</p>
        </div>

        <div className="pt-3 border-t border-[#ebebeb]">
          <p className="text-xs text-[#808080]">
            创建: {new Date(session.created_at).toLocaleString("zh-CN")}
          </p>
          <p className="text-xs text-[#808080] mt-1">
            更新: {new Date(session.updated_at).toLocaleString("zh-CN")}
          </p>
        </div>
      </div>
    </div>
  );
}
