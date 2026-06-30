/**
 * Agent Chat Panel
 *
 * Task 14: Main chat interface for V1 agent workbench.
 * Design: Vercel style - shadow-as-border, minimal color, clean typography.
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
    <div className="flex flex-col h-full bg-white rounded-lg" style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}>
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-[#666666] text-[14px] mb-4 font-normal">
              你好，我可以帮你：
            </p>
            <ul className="text-[#808080] text-[14px] space-y-2 font-normal">
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
                className={`max-w-[80%] rounded-lg px-4 py-3 ${
                  msg.role === "user"
                    ? "bg-[#171717] text-white"
                    : "bg-[#fafafa] text-[#171717]"
                }`}
                style={msg.role === "agent" ? { boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' } : {}}
              >
                <p className="text-[14px] whitespace-pre-wrap font-normal leading-relaxed">{msg.content}</p>
                {msg.created_at && (
                  <p className={`text-[12px] mt-2 ${msg.role === "user" ? "text-white/70" : "text-[#808080]"}`}>
                    {new Date(msg.created_at).toLocaleTimeString("zh-CN")}
                  </p>
                )}
              </div>
            </div>
          ))
        )}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-[#fafafa] rounded-lg px-4 py-3" style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}>
              <div className="flex items-center gap-2">
                <div className="animate-spin rounded-full h-4 w-4 border-2 border-[#ebebeb] border-t-[#171717]"></div>
                <span className="text-[14px] text-[#666666] font-normal">思考中...</span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input - Vercel style with shadow-border */}
      <form onSubmit={handleSubmit} className="p-4" style={{ borderTop: '1px solid rgba(0,0,0,0.08)' }}>
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="输入消息..."
            disabled={isLoading}
            className="flex-1 px-4 py-2 text-[14px] rounded-md focus:outline-none disabled:bg-[#fafafa] disabled:text-[#808080] font-normal"
            style={{ boxShadow: '0px 0px 0px 1px rgba(0,0,0,0.08)' }}
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="px-6 py-2 text-[14px] font-medium rounded-md bg-[#171717] text-white hover:bg-[#000000] disabled:bg-[#ebebeb] disabled:text-[#808080] disabled:cursor-not-allowed transition-colors"
          >
            发送
          </button>
        </div>
      </form>
    </div>
  );
}
