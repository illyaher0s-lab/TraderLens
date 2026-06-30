/**
 * Workflow Status Panel
 *
 * Task 14: Display current workflow status and metadata.
 * Design: Vercel style - shadow-as-border, subtle state colors, clean information hierarchy.
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

const STATE_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  created: { bg: "#fafafa", text: "#666666", border: "rgba(0,0,0,0.08)" },
  researching: { bg: "#eff6ff", text: "#1d4ed8", border: "rgba(59,130,246,0.2)" },
  waiting_for_approval: { bg: "#fef3c7", text: "#d97706", border: "rgba(251,191,36,0.2)" },
  validating: { bg: "#f3e8ff", text: "#7c3aed", border: "rgba(168,85,247,0.2)" },
  live_execution_pending: { bg: "#fed7aa", text: "#c2410c", border: "rgba(251,146,60,0.2)" },
  observing: { bg: "#d1fae5", text: "#047857", border: "rgba(34,197,94,0.2)" },
  reviewing: { bg: "#e0e7ff", text: "#4338ca", border: "rgba(99,102,241,0.2)" },
  completed: { bg: "#d1fae5", text: "#15803d", border: "rgba(34,197,94,0.3)" },
  stopped: { bg: "#fee2e2", text: "#b91c1c", border: "rgba(239,68,68,0.2)" },
};

export default function WorkflowStatusPanel({
  session,
  artifactCount,
}: WorkflowStatusPanelProps) {
  if (!session) {
    return (
      <div className="bg-white rounded-lg p-6" style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}>
        <h3 className="text-[14px] font-semibold text-[#171717] mb-4 tracking-tight">工作流状态</h3>
        <p className="text-[14px] text-[#666666] font-normal">暂无活动会话</p>
      </div>
    );
  }

  const stateStyle = STATE_COLORS[session.workflow_state] || STATE_COLORS.created;

  return (
    <div className="bg-white rounded-lg p-6" style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}>
      <h3 className="text-[14px] font-semibold text-[#171717] mb-4 tracking-tight">工作流状态</h3>

      <div className="space-y-4">
        <div>
          <p className="text-[12px] text-[#808080] mb-1 font-normal">工作流类型</p>
          <p className="text-[14px] font-medium text-[#171717]">
            {WORKFLOW_LABELS[session.workflow_kind] || session.workflow_kind}
          </p>
        </div>

        <div>
          <p className="text-[12px] text-[#808080] mb-2 font-normal">当前状态</p>
          <span
            className="inline-block px-3 py-1 text-[12px] font-medium rounded"
            style={{
              backgroundColor: stateStyle.bg,
              color: stateStyle.text,
              boxShadow: `0px 0px 0px 1px ${stateStyle.border}`,
            }}
          >
            {STATE_LABELS[session.workflow_state] || session.workflow_state}
          </span>
        </div>

        <div>
          <p className="text-[12px] text-[#808080] mb-1 font-normal">会话标题</p>
          <p className="text-[14px] text-[#171717] font-normal">{session.title}</p>
        </div>

        <div>
          <p className="text-[12px] text-[#808080] mb-1 font-normal">关联证据</p>
          <p className="text-[14px] text-[#171717] font-normal">{artifactCount} 项</p>
        </div>

        <div className="pt-3" style={{ borderTop: '1px solid rgba(0,0,0,0.08)' }}>
          <p className="text-[12px] text-[#808080] font-normal">
            创建: {new Date(session.created_at).toLocaleString("zh-CN")}
          </p>
          <p className="text-[12px] text-[#808080] mt-1 font-normal">
            更新: {new Date(session.updated_at).toLocaleString("zh-CN")}
          </p>
        </div>
      </div>
    </div>
  );
}
