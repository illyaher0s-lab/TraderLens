"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { researchApi, Theme } from "@/lib/research-api-client";

export default function ThemesPage() {
  const router = useRouter();
  const [themes, setThemes] = useState<Theme[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [formData, setFormData] = useState({
    theme_name: "",
    background: "",
    source_type: "manual_theme",
    research_mode: "standard",
    urgency: "normal",
    notes: "",
  });

  useEffect(() => {
    loadThemes();
  }, []);

  async function loadThemes() {
    try {
      const data = await researchApi.listThemes();
      setThemes(data);
    } catch (error) {
      console.error("Failed to load themes:", error);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate() {
    try {
      const result = await researchApi.createTheme(formData);
      router.push(`/themes/${result.theme_id}`);
    } catch (error) {
      console.error("Failed to create theme:", error);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-white p-8">
        <p className="text-gray-600">加载中...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      {/* Top Navigation - Vercel Style */}
      <div className="border-b" style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px" }}>
        <div className="max-w-6xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-semibold text-gray-900" style={{ letterSpacing: "-0.96px" }}>
              研究主题
            </h1>
            <button
              onClick={() => setShowCreateForm(true)}
              className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-md hover:bg-gray-800 transition-colors"
            >
              创建主题
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-8">
        {showCreateForm && (
          <div className="bg-white rounded-lg p-6 mb-6" style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px, rgba(0,0,0,0.04) 0px 2px 4px" }}>
            <h2 className="text-lg font-semibold mb-4 text-gray-900" style={{ letterSpacing: "-0.32px" }}>
              创建新主题
            </h2>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  主题名称
                </label>
                <input
                  type="text"
                  value={formData.theme_name}
                  onChange={(e) => setFormData({ ...formData, theme_name: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px" }}
                  placeholder="例如：新能源产业链"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  背景说明
                </label>
                <textarea
                  value={formData.background}
                  onChange={(e) => setFormData({ ...formData, background: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px" }}
                  rows={3}
                  placeholder="描述主题背景..."
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    来源类型
                  </label>
                  <select
                    value={formData.source_type}
                    onChange={(e) => setFormData({ ...formData, source_type: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px" }}
                  >
                    <option value="manual_theme">手动创建</option>
                    <option value="market_scan">市场扫描</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    研究模式
                  </label>
                  <select
                    value={formData.research_mode}
                    onChange={(e) => setFormData({ ...formData, research_mode: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px" }}
                  >
                    <option value="quick_scan">快速扫描</option>
                    <option value="standard">标准研究</option>
                    <option value="deep_research">深度研究</option>
                  </select>
                </div>
              </div>

              <div className="flex gap-2">
                <button
                  onClick={handleCreate}
                  className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-md hover:bg-gray-800"
                >
                  创建
                </button>
                <button
                  onClick={() => setShowCreateForm(false)}
                  className="px-4 py-2 bg-white text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50"
                  style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px" }}
                >
                  取消
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="space-y-3">
          {themes.length === 0 ? (
            <div className="bg-white rounded-lg p-8 text-center" style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px" }}>
              <p className="text-sm text-gray-600">暂无主题，点击上方按钮创建第一个主题</p>
            </div>
          ) : (
            themes.map((theme) => (
              <div
                key={theme.theme_id}
                onClick={() => router.push(`/themes/${theme.theme_id}`)}
                className="bg-white rounded-lg p-6 hover:bg-gray-50 cursor-pointer transition-colors"
                style={{ boxShadow: "rgba(0,0,0,0.08) 0px 0px 0px 1px, rgba(0,0,0,0.04) 0px 2px 4px" }}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="text-base font-semibold text-gray-900 mb-2" style={{ letterSpacing: "-0.32px" }}>
                      {theme.theme_name}
                    </h3>
                    <p className="text-sm text-gray-600 mb-4">{theme.background}</p>
                    <div className="flex gap-2">
                      <span className="px-3 py-1 text-xs font-medium bg-gray-50 text-gray-700 rounded-full">
                        {theme.source_type === "manual_theme" ? "手动创建" : "市场扫描"}
                      </span>
                      <span className="px-3 py-1 text-xs font-medium bg-gray-50 text-gray-700 rounded-full">
                        {theme.research_mode === "quick_scan"
                          ? "快速扫描"
                          : theme.research_mode === "standard"
                          ? "标准研究"
                          : "深度研究"}
                      </span>
                      <span className="px-3 py-1 text-xs font-medium bg-gray-50 text-gray-700 rounded-full">
                        {theme.status}
                      </span>
                    </div>
                  </div>
                  <div className="text-xs text-gray-500">
                    版本 {theme.board_version}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
