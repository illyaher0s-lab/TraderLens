/**
 * Agent Workbench Page - P1-3 状态诚实化
 *
 * 布局：桌面左55%聊天/右45%状态，移动端单列
 * 刷新：发消息后自动拉 timeline，仅 running job 时轮询
 */

"use client";

import Link from "next/link";
import { useState, useEffect, useRef } from "react";
import AgentChatPanel from "@/components/AgentChatPanel";
import ApprovalCard from "@/components/ApprovalCard";
import WorkbenchTimeline from "@/components/WorkbenchTimeline";
import WorkflowStatusPanel from "@/components/WorkflowStatusPanel";
import LiveLoopPanel from "@/components/LiveLoopPanel";
import {
  sendWorkbenchMessage,
  getWorkbenchSession,
  decideApprovalCard,
} from "@/lib/api-client";

interface Message {
  role: "user" | "agent";
  content: string;
  created_at?: string;
}

export default function WorkbenchPage() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [currentApprovalCard, setCurrentApprovalCard] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    // Cleanup polling on unmount
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };
  }, []);

  const loadSession = async (sessionId: string) => {
    try {
      const data = await getWorkbenchSession(sessionId);

      // Extract messages from timeline
      const timelineMessages = data.timeline
        .filter((item: any) => item.type === "message")
        .map((item: any) => ({
          role: item.content.role,
          content: item.content.content,
          created_at: item.content.created_at,
        }));

      setMessages(timelineMessages);
      setTimeline(data.timeline);

      // Extract latest approval card
      const approvalCards = data.timeline
        .filter((item: any) => item.type === "approval_card")
        .map((item: any) => item.content);

      if (approvalCards.length > 0) {
        setCurrentApprovalCard(approvalCards[approvalCards.length - 1]);
      }

      // Start/stop polling based on running jobs
      managePolling(data.timeline);
    } catch (err) {
      console.error("Failed to load session:", err);
      setError(err instanceof Error ? err.message : "加载会话失败");
    }
  };

  const managePolling = (timelineData: any[]) => {
    // Check if there's a real running job_id in timeline
    // P1-2 implementation: no job_id, so friend_stock waiting should NOT poll
    
    const artifacts = timelineData.filter((t: any) => t.type === 'artifact_ref');
    
    // Look for artifacts that contain job_id (real running jobs)
    let hasRunningJob = false;
    
    for (const artifact of artifacts) {
      if (artifact.content.artifact_content) {
        try {
          const data = JSON.parse(artifact.content.artifact_content);
          // Check if there's a job_id field indicating a real running job
          if (data.job_id && data.job_status === 'running') {
            hasRunningJob = true;
            break;
          }
        } catch (e) {
          // Ignore parse errors
        }
      }
    }
    
    // P1-2 current state: no job dispatch implemented
    // workflow_action_started alone does NOT trigger polling
    // Only real job_id with running status triggers polling
    
    if (hasRunningJob && !pollingIntervalRef.current) {
      // Start polling
      pollingIntervalRef.current = setInterval(() => {
        if (conversationId) {
          loadSession(conversationId);
        }
      }, 2000); // Poll every 2 seconds
    } else if (!hasRunningJob && pollingIntervalRef.current) {
      // Stop polling
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  };

  const handleSendMessage = async (message: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await sendWorkbenchMessage({
        conversation_id: conversationId || undefined,
        message,
      });

      // Update conversation ID
      if (!conversationId) {
        setConversationId(response.conversation_id);
      }

      // Refresh timeline immediately after sending
      await loadSession(response.conversation_id);
    } catch (err) {
      console.error("Failed to send message:", err);
      setError(err instanceof Error ? err.message : "发送消息失败");
    } finally {
      setIsLoading(false);
    }
  };

  const handleApprovalDecision = async (
    decision: string,
    decidedBy: string
  ) => {
    if (!conversationId || !currentApprovalCard) return;

    try {
      await decideApprovalCard(
        conversationId,
        currentApprovalCard.approval_card_id,
        {
          decision: decision as "approved" | "rejected",
          decided_by: decidedBy,
        }
      );

      // Reload session after decision
      await loadSession(conversationId);
    } catch (err) {
      console.error("Failed to decide approval card:", err);
      setError(err instanceof Error ? err.message : "决策失败");
    }
  };

  return (
    <div className="min-h-screen bg-white">
      <div className="max-w-[1600px] mx-auto p-6">
        {/* Header */}
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-[24px] font-semibold text-[#171717]">
              TraderLens 工作台
            </h1>
            <p className="text-[14px] text-[#666666] mt-1">
              与 AI 对话开始股票调研或策略评估
            </p>
            <p className="text-[12px] text-[#999999] mt-2">
              不是买卖建议 • 不会自动交易 • 需要人工审核
            </p>
          </div>
          <Link
            href="/trades/record"
            className="inline-flex items-center rounded-md bg-[#171717] px-4 py-2 text-[14px] font-medium text-white hover:bg-black"
          >
            记录成交
          </Link>
        </div>

        {/* Error Banner */}
        {error && (
          <div
            className="mb-4 p-4 bg-[#fef2f2] rounded-lg"
            style={{ boxShadow: "0px 0px 0px 1px rgba(239,68,68,0.2)" }}
          >
            <div className="text-[14px] text-[#ef4444]">{error}</div>
          </div>
        )}

        {/* Main Layout: Desktop 55/45, Mobile Single Column */}
        <div className="grid grid-cols-1 lg:grid-cols-[55%_45%] gap-6">
          {/* Left: Chat Panel */}
          <div className="flex flex-col">
            <AgentChatPanel
              messages={messages}
              onSendMessage={handleSendMessage}
              isLoading={isLoading}
            />

            {/* Approval Card (below chat on mobile, inline on desktop) */}
            {currentApprovalCard && (
              <div className="mt-4">
                <ApprovalCard
                  card={currentApprovalCard}
                  onDecide={handleApprovalDecision}
                  isSubmitting={isLoading}
                />
              </div>
            )}
          </div>

          {/* Right: Status Panels (上到下：当前状态/活动流/执行记录) */}
          <div className="flex flex-col gap-4">
            {/* 当前状态 */}
            <WorkflowStatusPanel timeline={timeline} />

            {/* 活动流 */}
            <WorkbenchTimeline timeline={timeline} />

            {/* 执行记录 */}
            {conversationId && (
              <LiveLoopPanel 
                conversationId={conversationId}
                onUpdate={() => loadSession(conversationId)}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
