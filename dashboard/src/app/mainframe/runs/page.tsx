'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api, ACTION_LABELS, fmtAsOf, fmtTime, duration, ASOF_OPTIONS } from '@/lib/api';
import type { Run } from '@/lib/types';
import { ActionButton } from '@/components/ActionButton';

const STATUS = {
  ok: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
  failed: 'bg-rose-500/10 text-rose-300 border-rose-500/30',
  running: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30',
};

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [asof, setAsof] = useState(20260930);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stop = false;
    const load = async () => {
      try {
        const r = await api.get<Run[]>('/runs?limit=50');
        if (!stop) { setRuns(r); setError(null); }
      } catch (e: any) { if (!stop) setError(e.message); }
    };
    load();
    const id = setInterval(load, 5000);
    return () => { stop = true; clearInterval(id); };
  }, []);

  const busy = runs.some(r => r.status === 'running');

  return (
    <div className="space-y-6">
      <div className="glass-panel p-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-bold text-gray-100">Run the daily batch</p>
          <p className="text-xs text-gray-400 mt-1 max-w-xl">
            Submits EWSBATCH on z/OS for the chosen as-of date, scores every eligible customer with the trained model,
            writes the scores back to the mainframe and prints the intervention report with EWSRPTJ.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select value={asof} onChange={e => setAsof(+e.target.value)}
            className="bg-[#0c101b] border border-[#1f293d] rounded-lg px-2 py-2 text-sm font-mono text-white">
            {ASOF_OPTIONS.map(a => <option key={a} value={a}>as-of {fmtAsOf(a)}</option>)}
          </select>
          <ActionButton action="run_batch" label="Run batch & score" params={{ asof }} disabled={busy} />
          <ActionButton action="train_model" label="Train model" variant="secondary" disabled={busy} />
        </div>
      </div>

      {error && <p className="text-sm text-rose-400">{error}</p>}

      <div className="glass-panel overflow-x-auto">
        <table className="w-full text-sm whitespace-nowrap">
          <thead>
            <tr className="border-b border-[#1f293d] text-[10px] uppercase tracking-widest text-gray-500">
              <th className="px-5 py-3 text-left">Run</th>
              <th className="px-5 py-3 text-left">Action</th>
              <th className="px-5 py-3 text-left">Parameters</th>
              <th className="px-5 py-3 text-left">Started</th>
              <th className="px-5 py-3 text-left">Duration</th>
              <th className="px-5 py-3 text-left">Status</th>
            </tr>
          </thead>
          <tbody>
            {runs.map(r => (
              <tr key={r.id} className="border-b border-[#1f293d]/50 hover:bg-[#1a2133]/40">
                <td className="px-5 py-3 font-mono">
                  <Link href={`/mainframe/runs/${r.id}`} className="text-cyan-400 hover:text-cyan-300">#{r.id}</Link>
                </td>
                <td className="px-5 py-3 text-gray-200">{ACTION_LABELS[r.action] ?? r.action}</td>
                <td className="px-5 py-3 font-mono text-xs text-gray-400">
                  {Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join(' ') || '—'}
                </td>
                <td className="px-5 py-3 text-xs text-gray-400">{fmtTime(r.started_at)}</td>
                <td className="px-5 py-3 text-xs font-mono text-gray-400">{duration(r.started_at, r.finished_at)}</td>
                <td className="px-5 py-3">
                  <span className={`text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded border ${STATUS[r.status]}`}>{r.status}</span>
                  {r.error && <p className="text-xs text-rose-300/80 mt-1 max-w-md truncate whitespace-normal" title={r.error}>{r.error}</p>}
                </td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr><td colSpan={6} className="px-5 py-10 text-center text-gray-500">No runs yet. Start with the Overview checklist.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
