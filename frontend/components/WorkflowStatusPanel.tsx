/**
 * Workflow Status Panel
 *
 * Derives the visible status from timeline artifacts. The latest route_decision
 * starts the current turn; older artifacts must not control the current state.
 */

"use client";

interface TimelineItem {
  type: string;
  content: any;
}

interface WorkflowStatusPanelProps {
  timeline: TimelineItem[];
}

type DerivedStatus = {
  status: "idle" | "waiting" | "completed" | "failed" | "needs_clarification";
  statusText: string;
  lastAction: string | null;
  currentObject: string | null;
  nextWaitingFor: string | null;
};

function parseJson(value: unknown): any | null {
  if (typeof value !== "string" || value.length === 0) return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function getTurnArtifacts(timeline: TimelineItem[]) {
  const artifacts = timeline.filter(
    (t) =>
      t.type === "artifact_ref" &&
      t.content.artifact_type !== "user_message" &&
      t.content.artifact_type !== "agent_message" &&
      t.content.artifact_type !== "workflow_intent"
  );

  const latestRouteIndex = artifacts
    .map((item) => item.content.artifact_type)
    .lastIndexOf("workflow_route_decision");

  if (latestRouteIndex === -1) {
    return { artifacts, currentTurnArtifacts: artifacts };
  }

  return {
    artifacts,
    currentTurnArtifacts: artifacts.slice(latestRouteIndex),
  };
}

function findLatestArtifact(artifacts: TimelineItem[], artifactType: string) {
  for (let i = artifacts.length - 1; i >= 0; i -= 1) {
    if (artifacts[i].content.artifact_type === artifactType) {
      return artifacts[i];
    }
  }
  return null;
}

function deriveStatusFromTimeline(timeline: TimelineItem[]): DerivedStatus {
  const { artifacts, currentTurnArtifacts } = getTurnArtifacts(timeline);

  if (artifacts.length === 0) {
    return {
      status: "idle",
      statusText: "空闲",
      lastAction: null,
      currentObject: null,
      nextWaitingFor: null,
    };
  }

  const latestRoute = findLatestArtifact(
    currentTurnArtifacts,
    "workflow_route_decision"
  );
  const routeData = parseJson(latestRoute?.content.artifact_content);
  const workflowKind = routeData?.workflow_kind ?? null;
  const routeReason = routeData?.route_reason ?? null;

  const latestStockIdentity =
    findLatestArtifact(currentTurnArtifacts, "stock_identity_resolution") ??
    findLatestArtifact(artifacts, "stock_identity_resolution");
  const stockData = parseJson(latestStockIdentity?.content.artifact_content);
  const stockName = stockData?.company_name ?? null;

  const lastArtifact = currentTurnArtifacts[currentTurnArtifacts.length - 1];
  const artifactType = lastArtifact?.content.artifact_type;
  const hasStrategyRejected = currentTurnArtifacts.some(
    (item) => item.content.artifact_type === "strategy_idea_rejected"
  );
  const hasFriendStockFlow = currentTurnArtifacts.some(
    (item) => item.content.artifact_type === "friend_stock_flow"
  );

  if (artifactType === "workflow_action_failed") {
    return {
      status: "failed",
      statusText: "失败",
      lastAction: getActionLabel(workflowKind),
      currentObject: stockName,
      nextWaitingFor: "需要重试或调整输入",
    };
  }

  if (artifactType === "workflow_route_decision" && workflowKind === "unknown") {
    return {
      status: "needs_clarification",
      statusText: "需要澄清",
      lastAction: "理解意图",
      currentObject: null,
      nextWaitingFor: routeReason || "需要更多信息",
    };
  }

  if (hasStrategyRejected) {
    return {
      status: "completed",
      statusText: "已记录",
      lastAction: "策略想法评估",
      currentObject: "策略想法",
      nextWaitingFor: null,
    };
  }

  if (hasFriendStockFlow) {
    const flowArtifact = findLatestArtifact(currentTurnArtifacts, "friend_stock_flow");
    const flowData = parseJson(flowArtifact?.content.artifact_content);
    const flowStatus = flowData?.status || "waiting";

    if (flowStatus === "completed") {
      return {
        status: "completed",
        statusText: "完成",
        lastAction: "创建研究记录",
        currentObject: stockName,
        nextWaitingFor: null,
      };
    }

    return {
      status: "waiting",
      statusText: "等待中",
      lastAction: "创建研究记录",
      currentObject: stockName,
      nextWaitingFor:
        flowStatus === "waiting" ? "等待研究服务配置" : "等待研究服务处理",
    };
  }

  if (artifactType === "workflow_action_completed") {
    return {
      status: "completed",
      statusText: "完成",
      lastAction: getActionLabel(workflowKind),
      currentObject: stockName,
      nextWaitingFor: null,
    };
  }

  return {
    status: "idle",
    statusText: "准备中",
    lastAction: getActionLabel(workflowKind),
    currentObject: stockName,
    nextWaitingFor: null,
  };
}

function getActionLabel(workflowKind: string | null): string {
  const labels: Record<string, string> = {
    friend_stock: "股票调研",
    strategy_idea: "策略想法评估",
    execution_feedback: "执行反馈",
    position_followup: "持仓跟进",
    theme_research: "主题研究",
  };
  return labels[workflowKind || ""] || "处理";
}

export default function WorkflowStatusPanel({ timeline }: WorkflowStatusPanelProps) {
  const status = deriveStatusFromTimeline(timeline);

  const statusColors: Record<string, string> = {
    idle: "text-[#666666]",
    waiting: "text-[#f59e0b]",
    completed: "text-[#10b981]",
    failed: "text-[#ef4444]",
    needs_clarification: "text-[#3b82f6]",
  };

  const statusIcons: Record<string, string> = {
    idle: "○",
    waiting: "⏸",
    completed: "✓",
    failed: "!",
    needs_clarification: "?",
  };

  return (
    <div
      className="bg-white rounded-lg p-4"
      style={{ boxShadow: "0px 0px 0px 1px rgba(0,0,0,0.08)" }}
    >
      <h3 className="text-[14px] font-medium text-[#171717] mb-3">
        当前状态
      </h3>

      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className={`text-[18px] ${statusColors[status.status]}`}>
            {statusIcons[status.status]}
          </span>
          <span className={`text-[14px] font-medium ${statusColors[status.status]}`}>
            {status.statusText}
          </span>
        </div>

        {status.lastAction && (
          <div className="text-[13px] text-[#666666]">
            <span className="text-[#999999]">最后动作：</span>
            {status.lastAction}
          </div>
        )}

        {status.currentObject && (
          <div className="text-[13px] text-[#666666]">
            <span className="text-[#999999]">处理对象：</span>
            {status.currentObject}
          </div>
        )}

        {status.nextWaitingFor && (
          <div className="text-[13px] text-[#666666]">
            <span className="text-[#999999]">等待：</span>
            {status.nextWaitingFor}
          </div>
        )}

        {!status.lastAction && !status.currentObject && !status.nextWaitingFor && (
          <div className="text-[13px] text-[#999999]">
            发送消息开始对话
          </div>
        )}
      </div>
    </div>
  );
}
