/**
 * Agent Activity Panel
 *
 * Task 23: Display agent execution steps based on timeline artifacts.
 * Design: Codex/Claude Code inspired - show each step with status.
 *
 * Status rules:
 * - completed: action finished successfully
 * - failed: action failed with error
 * - waiting_for_user: need user clarification/approval
 * - running: currently in progress (only if workflow_state matches)
 *
 * Red lines:
 * - If workflow_state=researching/validating but no action artifacts, show "状态异常：缺少动作记录"
 * - If workflow_state=stopped, show failure reason, not "completed"
 * - If rejected_strategy, show "已记录，但不可用于实盘"
 */

"use client";

interface TimelineItem {
  type: string;
  content: any;
}

interface AgentActivityPanelProps {
  timeline: TimelineItem[];
  workflowState: string;
  workflowKind: string;
}

interface ActivityStep {
  title: string;
  artifactType: string;
  status: "completed" | "failed" | "waiting_for_user" | "running" | "anomaly";
  createdAt: string;
  summary?: string;
  artifactId?: string;
}

export default function AgentActivityPanel({
  timeline,
  workflowState,
  workflowKind,
}: AgentActivityPanelProps) {
  // Extract artifact_ref items from timeline
  const artifacts = timeline.filter((item) => item.type === "artifact_ref");

  // Map artifacts to activity steps
  const steps: ActivityStep[] = artifacts.map((item) => {
    const artifactType = item.content.artifact_type || "unknown";
    const createdAt = item.content.created_at;
    const artifactId = item.content.artifact_id;

    return mapArtifactToStep(artifactType, createdAt, artifactId, workflowState);
  });

  // Check for anomaly: workflow_state indicates action but no action artifacts
  const hasActionArtifacts = artifacts.some((item) => {
    const type = item.content.artifact_type;
    return (
      type !== "workflow_intent" &&
      type !== "user_message" &&
      type !== "agent_message"
    );
  });

  const isRunningState =
    workflowState === "researching" || workflowState === "validating";
  const hasAnomaly = isRunningState && !hasActionArtifacts;

  if (hasAnomaly) {
    steps.push({
      title: "状态异常：缺少动作记录",
      artifactType: "anomaly",
      status: "anomaly",
      createdAt: new Date().toISOString(),
      summary: `系统显示"${workflowState}"，但 timeline 中没有真实的业务动作记录。请刷新页面或联系技术支持。`,
    });
  }

  if (steps.length === 0) {
    return (
      <div
        className="bg-white rounded-lg p-6"
        style={{ boxShadow: "0px 0px 0px 1px rgba(0,0,0,0.08)" }}
      >
        <h3 className="text-[16px] font-semibold text-[#171717] mb-2 tracking-tight">
          Agent Activity
        </h3>
        <p className="text-[14px] text-[#666666] font-normal">
          暂无执行步骤
        </p>
      </div>
    );
  }

  return (
    <div
      className="bg-white rounded-lg p-6"
      style={{ boxShadow: "0px 0px 0px 1px rgba(0,0,0,0.08)" }}
    >
      <h3 className="text-[16px] font-semibold text-[#171717] mb-4 tracking-tight">
        Agent Activity
      </h3>

      <div className="space-y-3">
        {steps.map((step, idx) => (
          <div key={idx} className="flex items-start gap-3">
            {/* Status Icon */}
            <div className="flex-shrink-0 mt-0.5">
              {renderStatusIcon(step.status)}
            </div>

            {/* Step Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <p className="text-[14px] font-medium text-[#171717]">
                  {step.title}
                </p>
                {renderStatusBadge(step.status)}
              </div>

              {step.summary && (
                <p className="text-[12px] text-[#666666] mt-1 font-normal leading-relaxed">
                  {step.summary}
                </p>
              )}

              {step.artifactId && (
                <details className="mt-2">
                  <summary className="text-[11px] text-[#808080] cursor-pointer hover:text-[#171717]">
                    详细信息
                  </summary>
                  <p className="text-[11px] text-[#808080] mt-1 font-mono break-all">
                    {step.artifactId}
                  </p>
                </details>
              )}

              <p className="text-[11px] text-[#808080] mt-1">
                {new Date(step.createdAt).toLocaleString("zh-CN")}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Map artifact type to activity step
 */
function mapArtifactToStep(
  artifactType: string,
  createdAt: string,
  artifactId: string,
  workflowState: string
): ActivityStep {
  // Workflow intent
  if (artifactType === "workflow_intent") {
    return {
      title: "识别任务意图",
      artifactType,
      status: "completed",
      createdAt,
      summary: "系统已识别用户意图，开始编排业务流程。",
      artifactId,
    };
  }

  // Friend stock flow
  if (artifactType === "friend_stock_flow") {
    return {
      title: "识别股票/公司",
      artifactType,
      status: "completed",
      createdAt,
      summary: "Ticker 验证完成，已确认公司信息。",
      artifactId,
    };
  }

  if (artifactType === "research_report") {
    return {
      title: "完成公司研究",
      artifactType,
      status: "completed",
      createdAt,
      summary: "产业链研究已完成，等待审批决定。",
      artifactId,
    };
  }

  // Strategy idea flow
  if (artifactType === "strategy_idea") {
    return {
      title: "记录策略想法",
      artifactType,
      status: "completed",
      createdAt,
      summary: "策略想法已记录，默认为不可信状态。",
      artifactId,
    };
  }

  if (artifactType === "strategy_idea_extraction") {
    return {
      title: "提取策略规则",
      artifactType,
      status: "completed",
      createdAt,
      summary: "LLM 已提取入场条件和出场条件。",
      artifactId,
    };
  }

  if (artifactType === "template_mapping") {
    return {
      title: "匹配策略模板",
      artifactType,
      status: "completed",
      createdAt,
      summary: "确定性模板匹配完成。",
      artifactId,
    };
  }

  if (artifactType === "rejected_strategy") {
    return {
      title: "策略被拒绝/暂不可用",
      artifactType,
      status: workflowState === "stopped" ? "completed" : "failed",
      createdAt,
      summary: "该策略想法已记录到拒绝注册表，不可用于实盘交易，不会生成交易信号。",
      artifactId,
    };
  }

  if (artifactType === "blocked_strategy_idea") {
    return {
      title: "策略被阻止",
      artifactType,
      status: "failed",
      createdAt,
      summary: "策略想法不符合安全规范，已被阻止。",
      artifactId,
    };
  }

  // Approval card
  if (artifactType === "approval_card") {
    return {
      title: "等待结果审批",
      artifactType,
      status: "waiting_for_user",
      createdAt,
      summary: "需要用户审批决定是否继续。",
      artifactId,
    };
  }

  // Live loop artifacts
  if (artifactType === "execution_observation_log" || artifactType.includes("execution_log")) {
    return {
      title: "记录执行反馈",
      artifactType,
      status: "completed",
      createdAt,
      summary: "买入/卖出记录已保存。",
      artifactId,
    };
  }

  if (artifactType === "observation_position") {
    return {
      title: "进入持仓观察",
      artifactType,
      status: "completed",
      createdAt,
      summary: "持仓已进入观察池。",
      artifactId,
    };
  }

  if (artifactType === "daily_observation_signal" || artifactType.includes("daily_signal")) {
    return {
      title: "生成今日观察信号",
      artifactType,
      status: "completed",
      createdAt,
      summary: "确定性 reducer 已生成今日信号（hold/sell/risk）。",
      artifactId,
    };
  }

  if (artifactType === "discipline_review") {
    return {
      title: "生成纪律复盘",
      artifactType,
      status: "completed",
      createdAt,
      summary: "交易纪律复盘报告已生成。",
      artifactId,
    };
  }

  if (artifactType === "pnl_record") {
    return {
      title: "盈亏记录",
      artifactType,
      status: "completed",
      createdAt,
      summary: "P&L 计算完成。",
      artifactId,
    };
  }

  // Failed/waiting artifacts
  if (artifactType === "failed_action") {
    return {
      title: "操作失败",
      artifactType,
      status: "failed",
      createdAt,
      summary: "业务操作执行失败，请查看详细信息。",
      artifactId,
    };
  }

  if (artifactType === "waiting_for_user_action") {
    return {
      title: "等待用户输入",
      artifactType,
      status: "waiting_for_user",
      createdAt,
      summary: "需要用户提供更多信息。",
      artifactId,
    };
  }

  // Default: completed
  return {
    title: artifactType,
    artifactType,
    status: "completed",
    createdAt,
    artifactId,
  };
}

/**
 * Render status icon
 */
function renderStatusIcon(status: ActivityStep["status"]) {
  switch (status) {
    case "completed":
      return (
        <div className="w-5 h-5 rounded-full bg-[#d1fae5] flex items-center justify-center">
          <svg className="w-3 h-3 text-[#16a34a]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
      );
    case "failed":
      return (
        <div className="w-5 h-5 rounded-full bg-[#fee2e2] flex items-center justify-center">
          <svg className="w-3 h-3 text-[#dc2626]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </div>
      );
    case "waiting_for_user":
      return (
        <div className="w-5 h-5 rounded-full bg-[#fef3c7] flex items-center justify-center">
          <svg className="w-3 h-3 text-[#f59e0b]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
      );
    case "running":
      return (
        <div className="w-5 h-5 rounded-full bg-[#eff6ff] flex items-center justify-center">
          <div className="w-3 h-3 border-2 border-[#3b82f6] border-t-transparent rounded-full animate-spin"></div>
        </div>
      );
    case "anomaly":
      return (
        <div className="w-5 h-5 rounded-full bg-[#fef2f2] flex items-center justify-center">
          <svg className="w-3 h-3 text-[#dc2626]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
      );
    default:
      return (
        <div className="w-5 h-5 rounded-full bg-[#fafafa] flex items-center justify-center">
          <div className="w-2 h-2 rounded-full bg-[#808080]"></div>
        </div>
      );
  }
}

/**
 * Render status badge
 */
function renderStatusBadge(status: ActivityStep["status"]) {
  switch (status) {
    case "completed":
      return (
        <span className="text-[11px] text-[#16a34a] font-medium">
          ✓ 完成
        </span>
      );
    case "failed":
      return (
        <span className="text-[11px] text-[#dc2626] font-medium">
          ✗ 失败
        </span>
      );
    case "waiting_for_user":
      return (
        <span className="text-[11px] text-[#f59e0b] font-medium">
          ⏸ 等待用户
        </span>
      );
    case "running":
      return (
        <span className="text-[11px] text-[#3b82f6] font-medium">
          ⟳ 进行中
        </span>
      );
    case "anomaly":
      return (
        <span className="text-[11px] text-[#dc2626] font-medium">
          ⚠ 异常
        </span>
      );
    default:
      return null;
  }
}
