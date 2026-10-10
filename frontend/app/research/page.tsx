'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';

interface ResearchCase {
  theme_id: string;
  theme_name: string;
  status: string;
  source_type: string;
  created_at: string;
}

export default function ResearchPage() {
  const [cases, setCases] = useState<ResearchCase[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('http://localhost:8010/api/research/themes')
      .then(res => res.json())
      .then(data => {
        setCases(data);
        setLoading(false);
      })
      .catch(err => {
        console.error('Failed to load research cases:', err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-white p-6">
        <div className="max-w-[1200px] mx-auto">
          <h1 className="text-[24px] font-semibold text-[#171717] mb-6">研究案例</h1>
          <p className="text-[#808080]">加载中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white p-6">
      <div className="max-w-[1200px] mx-auto">
        <h1 className="text-[24px] font-semibold text-[#171717] mb-6">研究案例</h1>

        <div className="space-y-4">
          {cases.length === 0 && (
            <p className="text-[#808080]">暂无研究案例</p>
          )}

          {cases.map(c => (
            <Link
              key={c.theme_id}
              href={`/research/${c.theme_id}`}
              className="block border border-[#ebebeb] rounded-lg p-4 hover:border-[#171717] transition-colors"
            >
              <div className="flex justify-between items-start">
                <div>
                  <h2 className="text-[16px] font-medium text-[#171717]">{c.theme_name}</h2>
                  <p className="text-[14px] text-[#808080] mt-1">
                    来源: {c.source_type === 'manual_stock' ? '朋友荐股' : c.source_type}
                  </p>
                </div>
                <span className={`text-[14px] px-3 py-1 rounded ${
                  c.status === 'draft' ? 'bg-[#ebebeb] text-[#808080]' :
                  c.status === 'in_progress' ? 'bg-blue-50 text-blue-600' :
                  'bg-green-50 text-green-600'
                }`}>
                  {c.status}
                </span>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
