/**
 * Agent Chat Panel
 *
 * Task 14: Main chat interface for V1 agent workbench.
 *
 * User inputs natural language, agent replies without exposing technical parameters.
 */

"use client";

import { useState, useEffect, useRef } from "react";

interface Message {
  role: "user" | "agent";
  content: string;
  created_at?: string;
}

interface AgentChatPanelProps {
  messages: Message[];
  onSendMessage: (message: string) => Promise<void>;
  isLoading: boolean;
}

export default function AgentChatPanel({
  messages,
  onSendMessage,
  isLoading,
}: AgentChatPanelProps) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    setInput("");
    await onSendMessage(trimmed);
  };

  return (
    <div className="flex flex-col h-full bg-white rounded-lg border border-[#ebebeb]">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-[#666666] text-sm mb-4">
              你好，我可以帮你：
            </p>
            <ul className="text-[#808080] text-sm space-y-2">
              <li>• 调查朋友推荐的股票（告诉我公司名或股票代码）</li>
              <li>• 验证抖音/视频看到的交易策略</li>
            </ul>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-4 py-2 ${
                  msg.role === "user"
                    ? "bg-[#0072f5] text-white"
                    : "bg-[#fafafa] text-[#171717] border border-[#ebebeb]"
                }`}
              >
                <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                {msg.created_at && (
                  <p className={`text-xs mt-1 ${msg.role === "user" ? "text-blue-100" : "text-[#808080]"}`}>
                    {new Date(msg.created_at).toLocaleTimeString("zh-CN")}
                  </p>
                )}
              </div>
            </div>
          ))
        )}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-[#fafafa] rounded-lg px-4 py-2 border border-[#ebebeb]">
              <div className="flex items-center gap-2">
                <div className="animate-spin rounded-full h-4 w-4 border-2 border-[#ebebeb] border-t-[#171717]"></div>
                <span className="text-sm text-[#666666]">思考中...</span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="border-t border-[#ebebeb] p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="输入消息..."
            disabled={isLoading}
            className="flex-1 px-4 py-2 text-sm border border-[#ebebeb] rounded-md focus:outline-none focus:ring-2 focus:ring-[#0072f5] focus:border-transparent disabled:bg-[#fafafa] disabled:text-[#808080]"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="px-6 py-2 text-sm font-medium rounded-md bg-[#0072f5] text-white hover:bg-[#0061d5] disabled:bg-[#ebebeb] disabled:text-[#808080] disabled:cursor-not-allowed transition-colors"
          >
            发送
          </button>
        </div>
      </form>
    </div>
  );
}
