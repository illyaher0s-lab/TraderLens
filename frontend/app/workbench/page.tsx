/**
 * Agent Workbench Page
 *
 * Task 14: V1 Minimum Profitable Loop - unified agent conversation interface.
 *
 * User can:
 * - Chat with agent using natural language
 * - Start friend-stock or strategy-idea workflows
 * - Approve result-level decisions via approval cards
 *
 * User cannot:
 * - Fill technical parameters (OOS, threshold, stop_loss, liquidity_rule, position_size, backtest_param)
 * - Access automatic trading or broker connections
 *
 * Hard constraints:
 * - No landing page, first screen is usable agent workbench
 * - No technical field inputs
 * - Approval cards only show result-level decisions
 */

"use client";

import { useState, useEffect } from "react";
import AgentChatPanel from "@/components/AgentChatPanel";
import ApprovalCard from "@/components/ApprovalCard";
import WorkbenchTimeline from "@/components/WorkbenchTimeline";
import WorkflowStatusPanel from "@/components/WorkflowStatusPanel";
import {
  sendWorkbenchMessage,
  getWorkbenchSession,
  decideApprovalCard,
  type WorkbenchMessageResponse,
  type WorkbenchSession,
  type ApprovalCardData,
} from "@/lib/api-client";

interface Message {
  role: "user" | "agent";
  content: string;
  created_at?: string;
}

export default function WorkbenchPage() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [session, setSession] = useState<WorkbenchSession | null>(null);
  const [currentApprovalCard, setCurrentApprovalCard] = useState<ApprovalCardData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isDeciding, setIsDeciding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load session on conversation_id change
  useEffect(() => {
    if (conversationId) {
      loadSession();
    }
  }, [conversationId]);

  const loadSession = async () => {
    if (!conversationId) return;

    try {
      const data = await getWorkbenchSession(conversationId);
      setSession(data);

      // Extract messages from timeline
      const timelineMessages: Message[] = data.timeline
        .filter((item) => item.type === "message")
        .map((item) => ({
          role: item.content.role,
          content: item.content.content,
          created_at: item.content.created_at,
        }));

      setMessages(timelineMessages);

      // Extract latest approval card
      const approvalCards = data.timeline
        .filter((item) => item.type === "approval_card")
        .map((item) => item.content);

      if (approvalCards.length > 0) {
        setCurrentApprovalCard(approvalCards[approvalCards.length - 1]);
      }
    } catch (err) {
      console.error("Failed to load session:", err);
      setError(err instanceof Error ? err.message : "加载会话失败");
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

      // Add user message
      setMessages((prev) => [
        ...prev,
        { role: "user", content: message },
      ]);

      // Add agent reply
      setMessages((prev) => [
        ...prev,
        { role: "agent", content: response.agent_reply },
      ]);

      // Update approval card if present
      if (response.approval_card) {
        setCurrentApprovalCard(response.approval_card);
      }

      // Refresh session to get full timeline
      if (response.conversation_id) {
        setConversationId(response.conversation_id);
      }
    } catch (err) {
      console.error("Failed to send message:", err);
      setError(err instanceof Error ? err.message : "发送消息失败");
    } finally {
      setIsLoading(false);
    }
  };

  const handleDecide = async (decision: string, decidedBy: string) => {
    if (!conversationId || !currentApprovalCard) return;

    setIsDeciding(true);
    setError(null);

    try {
      await decideApprovalCard(conversationId, currentApprovalCard.approval_card_id, {
        decision,
        decided_by: decidedBy,
      });

      // Refresh session
      await loadSession();
    } catch (err) {
      console.error("Failed to decide:", err);
      throw err; // Let ApprovalCard handle the error
    } finally {
      setIsDeciding(false);
    }
  };

  const artifactCount = session?.timeline.filter((item) => item.type === "artifact_ref").length || 0;

  return (
    <div className="min-h-screen bg-[#fafafa]">
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Page Header */}
        <div className="mb-6">
          <h1 className="text-3xl font-semibold text-[#171717] tracking-tight">
            Agent Workbench
          </h1>
          <p className="text-sm text-[#666666] mt-2">
            和助手对话，启动朋友推荐股票或抖音策略验证流程
          </p>
          <p className="text-xs text-[#808080] mt-1">
            不是买卖建议｜不会自动交易｜需要人工审核
          </p>
        </div>

        {/* Error Banner */}
        {error && (
          <div className="mb-6 p-4 rounded-lg bg-red-50 border border-red-200">
            <p className="text-sm text-red-700">{error}</p>
            <button
              onClick={() => setError(null)}
              className="mt-2 text-sm text-red-600 hover:underline"
            >
              关闭
            </button>
          </div>
        )}

        {/* Main Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column: Chat */}
          <div className="lg:col-span-2">
            <div className="h-[600px]">
              <AgentChatPanel
                messages={messages}
                onSendMessage={handleSendMessage}
                isLoading={isLoading}
              />
            </div>

            {/* Approval Card */}
            {currentApprovalCard && !currentApprovalCard.decision && (
              <div className="mt-6">
                <ApprovalCard
                  card={currentApprovalCard}
                  onDecide={handleDecide}
                  isSubmitting={isDeciding}
                />
              </div>
            )}
          </div>

          {/* Right Column: Status & Timeline */}
          <div className="space-y-6">
            <WorkflowStatusPanel
              session={session?.session || null}
              artifactCount={artifactCount}
            />

            {session && session.timeline.length > 0 && (
              <WorkbenchTimeline timeline={session.timeline} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
