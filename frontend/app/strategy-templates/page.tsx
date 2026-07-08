"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface StrategyTemplate {
  template_id: string;
  version: string;
  status: string;
  hypothesis_types: string[];
  market_fit: string;
  entry_rules: string;
  exit_rules: string;
  risk_rules: string;
  position_sizing_rules: string;
  validation_gate_profile: string;
  core_entry_rule_id: string;
  template_hash: string;
}

export default function StrategyTemplatesPage() {
  const [templates, setTemplates] = useState<StrategyTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("http://localhost:8010/api/strategy-templates")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setTemplates(data.templates || []);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 p-8">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-3xl font-bold mb-8">策略模板库</h1>
          <p className="text-gray-500">加载中...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 p-8">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-3xl font-bold mb-8">策略模板库</h1>
          <div className="bg-red-50 border border-red-200 rounded p-4">
            <p className="text-red-700">加载失败: {error}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold">策略模板库</h1>
          <Link
            href="/strategies"
            className="text-blue-600 hover:text-blue-700"
          >
            ← 返回策略工作区
          </Link>
        </div>

        {templates.length === 0 ? (
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <p className="text-gray-500 text-lg mb-4">
              当前没有已批准的策略模板
            </p>
            <p className="text-gray-400 text-sm">
              策略模板需要经过严格的回测验证和人工审核后才能进入模板库。
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {templates.map((template) => (
              <div
                key={`${template.template_id}-${template.version}`}
                className="bg-white rounded-lg shadow p-6 hover:shadow-md transition-shadow"
              >
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h2 className="text-xl font-semibold mb-2">
                      {template.template_id}
                    </h2>
                    <div className="flex gap-2 mb-2">
                      <span className="px-2 py-1 bg-green-100 text-green-700 text-xs rounded">
                        {template.status}
                      </span>
                      <span className="px-2 py-1 bg-blue-100 text-blue-700 text-xs rounded">
                        {template.version}
                      </span>
                    </div>
                    <p className="text-gray-600 text-sm mb-2">
                      {template.market_fit}
                    </p>
                    <div className="flex gap-2 flex-wrap">
                      {template.hypothesis_types.map((type) => (
                        <span
                          key={type}
                          className="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded"
                        >
                          {type}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="space-y-3 text-sm">
                  <div>
                    <span className="font-medium text-gray-700">入场规则:</span>
                    <p className="text-gray-600 mt-1">{template.entry_rules}</p>
                  </div>
                  <div>
                    <span className="font-medium text-gray-700">出场规则:</span>
                    <p className="text-gray-600 mt-1">{template.exit_rules}</p>
                  </div>
                  <div>
                    <span className="font-medium text-gray-700">风控规则:</span>
                    <p className="text-gray-600 mt-1">{template.risk_rules}</p>
                  </div>
                  <div>
                    <span className="font-medium text-gray-700">
                      仓位管理:
                    </span>
                    <p className="text-gray-600 mt-1">
                      {template.position_sizing_rules}
                    </p>
                  </div>
                </div>

                <div className="mt-4 pt-4 border-t flex justify-between items-center">
                  <div className="text-xs text-gray-400">
                    Core Entry: {template.core_entry_rule_id}
                  </div>
                  <Link
                    href={`/strategy-templates/${template.template_id}`}
                    className="text-blue-600 hover:text-blue-700 text-sm"
                  >
                    查看详情 →
                    </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
