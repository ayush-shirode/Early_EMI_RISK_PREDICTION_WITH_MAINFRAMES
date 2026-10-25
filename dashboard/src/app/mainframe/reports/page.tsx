'use client';
import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';

type Tab = 'riskrpt' | 'rejects' | 'exceptions' | 'runctl';
const TABS: { key: Tab; label: string; note: string }[] = [
  { key: 'riskrpt', label: 'Intervention report', note: 'EWS.RISKRPT, printed on z/OS by COBOL EWSRPT from the scores written back to EWS.SCORES.' },
  { key: 'rejects', label: 'Rejected records', note: 'EWS.REJECTS, written by DFSORT (S01/S02) and the validation programs EWSVCUST (C..) and EWSVLOAN (L..).' },
  { key: 'exceptions', label: 'Matching exceptions', note: 'EWS.EXCEPT, written by EWSMATCH for records with no valid parent (orphans) or invalid dates.' },
  { key: 'runctl', label: 'Reconciliation', note: 'EWS.RUNCTL, written by REXX EWSRECON. The backend refuses to score unless STATUS=OK.' },
];

function Reports() {
  const runId = useSearchParams().get('runId');
  const [tab, setTab] = useState<Tab>('riskrpt');
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    api.get(`/reports/${tab}${runId ? `?runId=${runId}` : ''}`).then(setData).catch(e => setError(e.message));
  }, [tab, runId]);

  const current = TABS.find(t => t.key === tab)!;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-3.5 py-1.5 rounded-lg text-sm font-semibold ${tab === t.key ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/30' : 'text-gray-400 border border-[#1f293d] hover:text-gray-200'}`}>
            {t.label}
          </button>
        ))}
      </div>
      <p className="text-xs text-gray-500">{current.note}{data?.runId ? ` Run #${data.runId}.` : ''}</p>
      {error && <p className="text-sm text-rose-400">{error}</p>}
      {!data && !error && <p className="text-sm text-gray-400">Loading…</p>}

      {data && tab === 'riskrpt' && (
        <div className="glass-panel p-0 overflow-hidden">
          <pre className="p-4 text-[11px] leading-[1.35] font-mono text-gray-200 overflow-auto max-h-[75vh] whitespace-pre">
            {data.lines.map((l: string) => l.slice(1)).join('\n')}
          </pre>
        </div>
      )}

      {data && (tab === 'rejects' || tab === 'exceptions') && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="glass-panel p-5 h-fit">
            <p className="text-sm font-bold text-gray-100 mb-3">{data.total} records by reason</p>
            <div className="space-y-2">
              {data.summary.map((s: any) => (
                <div key={s.code + s.source} className="flex justify-between gap-3 text-xs">
                  <span className="text-gray-400"><span className="font-mono text-cyan-300">{s.code}</span> {s.text} <span className="text-gray-600">({s.source})</span></span>
                  <span className="font-mono text-gray-100">{s.count}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="lg:col-span-2 glass-panel overflow-auto max-h-[70vh]">
            <table className="w-full text-xs">
              <thead><tr className="border-b border-[#1f293d] text-[10px] uppercase tracking-widest text-gray-500">
                <th className="px-3 py-2 text-left">Source</th><th className="px-3 py-2 text-left">Key</th>
                <th className="px-3 py-2 text-left">Code</th><th className="px-3 py-2 text-left">Record (first 58 bytes)</th>
              </tr></thead>
              <tbody>
                {data.rows.map((r: any, i: number) => (
                  <tr key={i} className="border-b border-[#1f293d]/40">
                    <td className="px-3 py-1.5 font-mono text-gray-400">{r.source}</td>
                    <td className="px-3 py-1.5 font-mono text-gray-200">{r.key}</td>
                    <td className="px-3 py-1.5 font-mono text-cyan-300" title={r.reason_text}>{r.reason_code}</td>
                    <td className="px-3 py-1.5 font-mono text-gray-500 whitespace-pre">{r.data}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {data && tab === 'runctl' && (
        <div className="glass-panel p-5 grid grid-cols-1 md:grid-cols-2 gap-x-10 gap-y-1.5">
          {Object.entries(data.values).map(([k, v]) => (
            <div key={k} className="flex justify-between text-xs font-mono border-b border-[#1f293d]/40 py-1">
              <span className="text-gray-500">{k}</span>
              <span className={v === 'OK' ? 'text-emerald-400' : v === 'FAIL' ? 'text-rose-400' : 'text-gray-100'}>{String(v)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ReportsPage() {
  return <Suspense fallback={<p className="text-sm text-gray-400">Loading…</p>}><Reports /></Suspense>;
}
