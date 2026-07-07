"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

interface TemplateDetail {
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
  supported_universe_rule_types: string[];
  sample_split_rule_ids: string[];
  benchmark_rule_id: string;
  strategy_config_payload: any;
  default_cost_model: string;
  default_fill_model: string;
  forbidden_fields: string[];
  forbidden_evidence_terms: string[];
  forbidden_market: string[];
  template_hash: string;
}

export default function TemplateDetailPage() {
  const params = useParams();
  const template_id = params.template_id as string;
  const [template, setTemplate] = useState<TemplateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!template_id) return;

    fetch(`http://localhost:8010/api/strategy-templates/${template_id}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setTemplate(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [template_id]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 p-8">
        <div className="max-w-4xl mx-auto">
          <p className="text-gray-500">加载中...</p>
        </div>
      </div>
    );
  }

  if (error || !template) {
    return (
      <div className="min-h-screen bg-gray-50 p-8">
        <div className="max-w-4xl mx-auto">
          <div className="bg-red-50 border border-red-200 rounded p-4">
            <p className="text-red-700">
              {error || "模板未找到"}
            </p>
          </div>
          <Link
            href="/strategy-templates"
            className="text-blue-600 hover:text-blue-700 mt-4 inline-block"
          >
            ← 返回模板库
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-4xl mx-auto">
        <Link
          href="/strategy-templates"
          className="text-blue-600 hover:text-blue-700 mb-4 inline-block"
        >
          ← 返回模板库
        </Link>

        <div className="bg-white rounded-lg shadow p-8">
          <div className="mb-6">
            <h1 className="text-3xl font-bold mb-2">{template.template_id}</h1>
            <div className="flex gap-2 mb-4">
              <span className="px-3 py-1 bg-green-100 text-green-700 text-sm rounded">
                {template.status}
              </span>
              <span className="px-3 py-1 bg-blue-100 text-blue-700 text-sm rounded">
                {template.version}
              </span>
              <span className="px-3 py-1 bg-purple-100 text-purple-700 text-sm rounded">
                {template.validation_gate_profile}
              </span>
            </div>
            <p className="text-gray-600">{template.market_fit}</p>
          </div>

          <div className="space-y-6">
            <section>
              <h2 className="text-xl font-semibold mb-3">假设类型</h2>
              <div className="flex gap-2 flex-wrap">
                {template.hypothesis_types.map((type) => (
                  <span
                    key={type}
                    className="px-3 py-1 bg-gray-100 text-gray-700 rounded"
                  >
                    {type}
                  </span>
                ))}
              </div>
            </section>

            <section>
              <h2 className="text-xl font-semibold mb-3">入场规则</h2>
              <p className="text-gray-700">{template.entry_rules}</p>
              <p className="text-sm text-gray-500 mt-2">
                Core Entry Rule: {template.core_entry_rule_id}
              </p>
            </section>

            <section>
              <h2 className="text-xl font-semibold mb-3">出场规则</h2>
              <p className="text-gray-700">{template.exit_rules}</p>
            </section>

            <section>
              <h2 className="text-xl font-semibold mb-3">风控规则</h2>
              <p className="text-gray-700">{template.risk_rules}</p>
            </section>

            <section>
              <h2 className="text-xl font-semibold mb-3">仓位管理</h2>
              <p className="text-gray-700">{template.position_sizing_rules}</p>
            </section>

            <section>
              <h2 className="text-xl font-semibold mb-3">策略配置</h2>
              <pre className="bg-gray-50 p-4 rounded text-sm overflow-x-auto">
                {JSON.stringify(template.strategy_config_payload, null, 2)}
              </pre>
            </section>

            <section>
              <h2 className="text-xl font-semibold mb-3">技术参数</h2>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-600">Universe Rule Types:</span>
                  <div className="mt-1">
                    {template.supported_universe_rule_types.map((type) => (
                      <span
                        key={type}
                        className="inline-block px-2 py-1 bg-gray-100 text-gray-600 rounded text-xs mr-2 mb-1"
                      >
                        {type}
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <span className="text-gray-600">Sample Split Rules:</span>
                  <div className="mt-1">
                    {template.sample_split_rule_ids.map((id) => (
                      <span
                        key={id}
                        className="inline-block px-2 py-1 bg-gray-100 text-gray-600 rounded text-xs mr-2 mb-1"
                      >
                        {id}
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <span className="text-gray-600">Benchmark Rule:</span>
                  <p className="text-gray-700 mt-1">{template.benchmark_rule_id}</p>
                </div>
                <div>
                  <span className="text-gray-600">Cost Model:</span>
                  <p className="text-gray-700 mt-1">{template.default_cost_model}</p>
                </div>
                <div>
                  <span className="text-gray-600">Fill Model:</span>
                  <p className="text-gray-700 mt-1">{template.default_fill_model}</p>
                </div>
              </div>
            </section>

            <section>
              <h2 className="text-xl font-semibold mb-3">限制条件</h2>
              <div className="space-y-3 text-sm">
                <div>
                  <span className="text-gray-600">Forbidden Markets:</span>
                  <div className="mt-1 flex gap-2 flex-wrap">
                    {template.forbidden_market.map((market) => (
                      <span
                        key={market}
                        className="px-2 py-1 bg-red-50 text-red-700 rounded text-xs"
                      >
                        {market}
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <span className="text-gray-600">Forbidden Fields:</span>
                  <div className="mt-1 flex gap-2 flex-wrap">
                    {template.forbidden_fields.map((field) => (
                      <span
                        key={field}
                        className="px-2 py-1 bg-yellow-50 text-yellow-700 rounded text-xs"
                      >
                        {field}
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <span className="text-gray-600">Forbidden Evidence Terms:</span>
                  <div className="mt-1 flex gap-2 flex-wrap">
                    {template.forbidden_evidence_terms.map((term) => (
                      <span
                        key={term}
                        className="px-2 py-1 bg-orange-50 text-orange-700 rounded text-xs"
                      >
                        {term}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </section>

            <section className="pt-4 border-t">
              <p className="text-xs text-gray-400">
                Template Hash: {template.template_hash}
              </p>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
