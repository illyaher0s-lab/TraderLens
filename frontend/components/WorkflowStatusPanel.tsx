/**
 * Workflow Status Panel - P1-3 状态诚实化
 * 
 * 从 timeline artifacts 推导真实状态，不自造状态机
 * 只使用业务状态 artifacts，忽略 user_message/agent_message/workflow_intent
 */

"use client";

interface TimelineItem {
  type: string;
  content: any;
}

interface WorkflowStatusPanelProps {
  timeline: TimelineItem[];
}

function deriveStatusFromTimeline(timeline: TimelineItem[]) {
  // Filter to business artifacts only (ignore messages and workflow_intent)
  const artifacts = timeline.filter(t => 
    t.type === 'artifact_ref' && 
    t.content.artifact_type !== 'user_message' &&
    t.content.artifact_type !== 'agent_message' &&
    t.content.artifact_type !== 'workflow_intent'
  );
  
  if (artifacts.length === 0) {
    return {
      status: 'idle',
      statusText: '空闲',
      lastAction: null,
      currentObject: null,
      nextWaitingFor: null,
    };
  }
  
  // Get last business artifact
  const lastArtifact = artifacts[artifacts.length - 1];
  const artifactType = lastArtifact.content.artifact_type;
  
  // Find route_decision to get workflow context
  const routeDecision = artifacts.find(a => a.content.artifact_type === 'workflow_route_decision');
  let workflowKind = null;
  let routeReason = null;
  
  if (routeDecision && routeDecision.content.artifact_content) {
    try {
      const routeData = JSON.parse(routeDecision.content.artifact_content);
      workflowKind = routeData.workflow_kind;
      routeReason = routeData.route_reason;
    } catch (e) {
      console.error('Failed to parse route_decision:', e);
    }
  }
  
  // Find stock identity if exists
  let stockName = null;
  const stockIdentity = artifacts.find(a => a.content.artifact_type === 'stock_identity_resolution');
  if (stockIdentity && stockIdentity.content.artifact_content) {
    try {
      const stockData = JSON.parse(stockIdentity.content.artifact_content);
      if (stockData.company_name) {
        stockName = stockData.company_name;
      }
    } catch (e) {}
  }
  
  // Derive status from last business artifact type
  if (artifactType === 'workflow_action_failed') {
    return {
      status: 'failed',
      statusText: '失败',
      lastAction: getActionLabel(workflowKind),
      currentObject: stockName,
      nextWaitingFor: '需要重试或调整输入',
    };
  }
  
  if (artifactType === 'workflow_action_completed') {
    // Handler action completed (not research completed)
    // Check what workflow it was
    if (workflowKind === 'friend_stock') {
      // Friend stock flow created, but research not started
      return {
        status: 'waiting',
        statusText: '等待中',
        lastAction: '创建研究记录',
        currentObject: stockName,
        nextWaitingFor: '等待研究服务配置',
      };
    } else if (workflowKind === 'strategy_idea') {
      // Strategy idea rejected/completed
      return {
        status: 'completed',
        statusText: '完成',
        lastAction: '策略想法评估',
        currentObject: '策略想法',
        nextWaitingFor: null,
      };
    }
    
    return {
      status: 'completed',
      statusText: '完成',
      lastAction: getActionLabel(workflowKind),
      currentObject: stockName,
      nextWaitingFor: null,
    };
  }
  
  if (artifactType === 'friend_stock_flow') {
    // Read flow status from artifact_content
    let flowStatus = 'waiting';
    if (lastArtifact.content.artifact_content) {
      try {
        const flowData = JSON.parse(lastArtifact.content.artifact_content);
        flowStatus = flowData.status || 'waiting';
      } catch (e) {}
    }
    
    return {
      status: 'waiting',
      statusText: '等待中',
      lastAction: '创建研究记录',
      currentObject: stockName,
      nextWaitingFor: flowStatus === 'waiting' ? '等待研究服务配置' : '处理中',
    };
  }
  
  if (artifactType === 'strategy_idea_rejected') {
    return {
      status: 'completed',
      statusText: '已拒绝',
      lastAction: '策略想法评估',
      currentObject: '策略想法',
      nextWaitingFor: null,
    };
  }
  
  if (artifactType === 'workflow_route_decision') {
    if (workflowKind === 'unknown') {
      return {
        status: 'needs_clarification',
        statusText: '需要澄清',
        lastAction: '理解意图',
        currentObject: null,
        nextWaitingFor: routeReason || '需要更多信息',
      };
    }
  }
  
  // Default: processing
  return {
    status: 'idle',
    statusText: '准备中',
    lastAction: getActionLabel(workflowKind),
    currentObject: stockName,
    nextWaitingFor: null,
  };
}

function getActionLabel(workflowKind: string | null): string {
  const labels: Record<string, string> = {
    'friend_stock': '股票调研',
    'strategy_idea': '策略想法评估',
    'execution_feedback': '执行反馈',
    'position_followup': '持仓跟进',
    'theme_research': '主题研究',
  };
  return labels[workflowKind || ''] || '处理中';
}

export default function WorkflowStatusPanel({ timeline }: WorkflowStatusPanelProps) {
  const status = deriveStatusFromTimeline(timeline);
  
  const statusColors: Record<string, string> = {
    'idle': 'text-[#666666]',
    'waiting': 'text-[#f59e0b]',
    'completed': 'text-[#10b981]',
    'failed': 'text-[#ef4444]',
    'needs_clarification': 'text-[#3b82f6]',
  };
  
  const statusIcons: Record<string, string> = {
    'idle': '○',
    'waiting': '⏸',
    'completed': '✓',
    'failed': '✗',
    'needs_clarification': '?',
  };
  
  return (
    <div 
      className="bg-white rounded-lg p-4"
      style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}
    >
      <h3 className="text-[14px] font-medium text-[#171717] mb-3">当前状态</h3>
      
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
