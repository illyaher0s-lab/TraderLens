"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { researchApi, Theme, ConversationMessage, ProposedAction } from "@/lib/research-api-client";

interface Candidate {
  candidate_id: string;
  symbol: string;
  company_name: string | null;
  status: string;
  match_reason: string;
  hard_filter_flags: string[];
}

export default function ThemeDetailPage() {
  const params = useParams();
  const router = useRouter();
  const themeId = params.theme_id as string;

  const [theme, setTheme] = useState<Theme | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [pendingActions, setPendingActions] = useState<ProposedAction[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [inputMessage, setInputMessage] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadTheme();
    loadConversation();
    loadPendingActions();
    loadCandidates();
  }, [themeId]);

  async function loadTheme() {
    try {
      const data = await researchApi.getTheme(themeId);
      setTheme(data);
    } catch (error) {
      console.error("Failed to load theme:", error);
    } finally {
      setLoading(false);
    }
  }

  async function loadConversation() {
    try {
      const data = await researchApi.getConversation(themeId);
      setMessages(data);
    } catch (error) {
      console.error("Failed to load conversation:", error);
    }
  }

  async function loadPendingActions() {
    try {
      const data = await researchApi.getPendingActions(themeId);
      setPendingActions(data);
    } catch (error) {
      console.error("Failed to load pending actions:", error);
    }
  }

  async function loadCandidates() {
    try {
      const response = await fetch(`http://localhost:8000/api/research/themes/${themeId}/candidates`);
      if (response.ok) {
        const data = await response.json();
        setCandidates(data);
      }
    } catch (error) {
      console.error("Failed to load candidates:", error);
    }
  }

  async function handleSendMessage() {
    if (!inputMessage.trim()) return;

    try {
      const result = await researchApi.sendMessage(themeId, inputMessage);
      setMessages([...messages, result.user_message, result.agent_message]);
      setPendingActions([...pendingActions, ...result.proposed_actions]);
      setInputMessage("");
    } catch (error) {
      console.error("Failed to send message:", error);
    }
  }

  async function handleApplyAction(actionId: string) {
    try {
      const result = await researchApi.applyAction(actionId, "user_001");
      if (result.applied) {
        await loadTheme();
        await loadPendingActions();
        await loadCandidates();
      } else {
        alert(`应用失败: ${result.rejection_reason}`);
      }
    } catch (error) {
      console.error("Failed to apply action:", error);
      alert("应用动作时出错");
    }
  }

  async function handleRunSerenity() {
    try {
      await researchApi.runSerenity(themeId);
      loadTheme();
      alert("Serenity 分析完成");
    } catch (error) {
      console.error("Failed to run Serenity:", error);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-white p-8">
        <p className="text-gray-600">加载中...</p>
      </div>
    );
  }

  if (!theme) {
    return (
      <div className="min-h-screen bg-white p-8">
        <p className="text-gray-600">主题未找到</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      {/* Top Navigation Bar - Vercel Style */}
      <div className="border-b" style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px" }}>
        <div className="max-w-full mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => router.push("/themes")}
                className="px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-50 rounded-md transition-colors"
                style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px" }}
              >
                ← 返回
              </button>
              <div>
                <h1 className="text-lg font-semibold text-gray-900" style={{ letterSpacing: "-0.32px" }}>
                  {theme.theme_name}
                </h1>
                <p className="text-xs text-gray-600">{theme.background}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="px-3 py-1 text-xs font-medium bg-gray-50 text-gray-700 rounded-full">
                版本 {theme.board_version}
              </span>
              <span className="px-3 py-1 text-xs font-medium bg-gray-50 text-gray-700 rounded-full">
                {theme.status}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content: 25% Chat + 75% Board */}
      <div className="flex h-[calc(100vh-73px)]">
        {/* Left: Conversation (25%) */}
        <div className="w-1/4 border-r flex flex-col" style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px" }}>
          <div className="px-4 py-3 border-b" style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px" }}>
            <h2 className="text-sm font-semibold text-gray-900">对话控制</h2>
            <p className="text-xs text-gray-600 mt-1">AI 转换为待审核动作</p>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.length === 0 ? (
              <p className="text-xs text-gray-500">开始对话...</p>
            ) : (
              messages.map((msg) => (
                <div
                  key={msg.message_id}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[90%] px-3 py-2 rounded-md text-xs ${
                      msg.role === "user"
                        ? "bg-gray-900 text-white"
                        : "bg-gray-50 text-gray-900"
                    }`}
                  >
                    {msg.content}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Input */}
          <div className="border-t p-4" style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px" }}>
            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyPress={(e) => e.key === "Enter" && handleSendMessage()}
              placeholder="add 300750.SZ"
              className="w-full px-3 py-2 text-sm border-0 rounded-md mb-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px" }}
            />
            <button
              onClick={handleSendMessage}
              className="w-full px-3 py-2 bg-gray-900 text-white text-sm font-medium rounded-md hover:bg-gray-800 transition-colors"
            >
              发送
            </button>
          </div>
        </div>

        {/* Right: Board (75%) */}
        <div className="w-3/4 flex flex-col overflow-y-auto">
          <div className="p-6 space-y-6">
            {/* Pending Actions */}
            {pendingActions.length > 0 && (
              <div>
                <h3 className="text-base font-semibold text-gray-900 mb-3" style={{ letterSpacing: "-0.32px" }}>
                  待审核动作
                </h3>
                <div className="space-y-3">
                  {pendingActions.map((action) => (
                    <div
                      key={action.action_id}
                      className="bg-yellow-50 rounded-lg p-4"
                      style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px" }}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <p className="text-sm font-medium text-gray-900">{action.action}</p>
                          <p className="text-xs text-gray-600 mt-1">{action.rationale}</p>
                          <div className="mt-2 text-xs text-gray-500">
                            {action.proposed_by} · v{action.board_version}
                          </div>
                        </div>
                        <div className="flex gap-2 ml-4">
                          <button
                            onClick={() => handleApplyAction(action.action_id)}
                            className="px-3 py-1 bg-gray-900 text-white text-xs font-medium rounded-md hover:bg-gray-800"
                          >
                            应用
                          </button>
                          <button className="px-3 py-1 bg-white text-gray-700 text-xs font-medium rounded-md hover:bg-gray-50"
                            style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px" }}>
                            拒绝
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Research Actions */}
            <div>
              <h3 className="text-base font-semibold text-gray-900 mb-3" style={{ letterSpacing: "-0.32px" }}>
                研究操作
              </h3>
              <button
                onClick={handleRunSerenity}
                className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-md hover:bg-gray-800"
              >
                运行 Serenity 分析
              </button>
            </div>

            {/* Candidates */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-base font-semibold text-gray-900" style={{ letterSpacing: "-0.32px" }}>
                  候选股票
                </h3>
                {candidates.length > 0 && (
                  <button
                    onClick={async () => {
                      try {
                        const candidateIds = candidates.map(c => c.candidate_id);
                        await fetch("http://localhost:8000/api/research/candidates/run-evidence", {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify(candidateIds),
                        });
                        alert("Evidence 分析完成");
                        await loadCandidates();
                      } catch (error) {
                        console.error("Failed to run evidence:", error);
                      }
                    }}
                    className="px-3 py-1 bg-white text-gray-700 text-xs font-medium rounded-md hover:bg-gray-50"
                    style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px" }}
                  >
                    运行 Evidence
                  </button>
                )}
              </div>
              {candidates.length === 0 ? (
                <p className="text-sm text-gray-500">暂无候选</p>
              ) : (
                <div className="space-y-2">
                  {candidates.map((candidate) => (
                    <div
                      key={candidate.candidate_id}
                      className="bg-white rounded-lg p-4"
                      style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px, rgba(0,0,0,0.04) 0px 2px 2px" }}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-semibold text-gray-900">{candidate.symbol}</p>
                          {candidate.company_name && (
                            <p className="text-xs text-gray-600">{candidate.company_name}</p>
                          )}
                          <p className="text-xs text-gray-500 mt-1">{candidate.match_reason}</p>
                        </div>
                        <div className="flex flex-col gap-1">
                          <span className="px-3 py-1 text-xs font-medium bg-gray-50 text-gray-700 rounded-full">
                            {candidate.status}
                          </span>
                          {candidate.hard_filter_flags.length > 0 && (
                            <span className="px-3 py-1 text-xs font-medium bg-red-50 text-red-700 rounded-full">
                              {candidate.hard_filter_flags.length} 风险
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Confirmed Pool */}
            <div>
              <h3 className="text-base font-semibold text-gray-900 mb-3" style={{ letterSpacing: "-0.32px" }}>
                已确认候选池
              </h3>
              <p className="text-sm text-gray-500">暂无已确认候选</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
