'use client';
import Link from 'next/link';
import { useEffect } from 'react';
import { AlertTriangle, ArrowLeft } from 'lucide-react';
import { useRun } from '@/hooks/useRun';
import { ACTION_LABELS, fmtAsOf, fmtTime, duration } from '@/lib/api';
import { RunTimeline } from '@/components/RunTimeline';
import { useCustomer } from '@/context/CustomerContext';

const CHECK_LABELS: Record<string, string> = {
  CHK_CUST_SORT: 'Customers in = sorted + duplicates',
  CHK_CUST_VALID: 'Sorted customers = valid + rejected',
  CHK_LOAN: 'Loans in = valid + rejected',
  CHK_REPAY: 'Repayments in = sorted + rejected',
  CHK_TXN: 'Account summaries in = sorted + rejected',
  CHK_MATCH: 'EWSMATCH read every valid record',
  CHK_FEATURES: 'Features = customers − exclusions',
};

export default function RunPage({ params }: { params: { id: string } }) {
  const { run, error } = useRun(Number(params.id));
  const { reload } = useCustomer();

  useEffect(() => {
    if (run?.status === 'ok' && run.action === 'run_batch') reload();
  }, [run?.status, run?.action, reload]);

  if (error) return <p className="text-sm text-rose-400">{error}</p>;
  if (!run) return <p className="text-sm text-gray-400">Loading run…</p>;

  const runctl = run.summary?.runctl
    ?? [...(run.steps ?? [])].reverse().find(s => s.data?.runctl)?.data.runctl;

  return (
    <div className="space-y-6">
      <Link href="/mainframe/runs" className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-cyan-400">
        <ArrowLeft size={14} /> All runs
      </Link>

      <div className="glass-panel p-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-lg font-bold text-white">Run #{run.id} · {ACTION_LABELS[run.action] ?? run.action}</p>
          <p className="text-xs text-gray-400 font-mono mt-1">
            {Object.entries(run.params).map(([k, v]) => `${k}=${v}`).join(' ')}
            {' '}· started {fmtTime(run.started_at)} · {duration(run.started_at, run.finished_at)}
          </p>
        </div>
        <span className={`text-xs font-black uppercase tracking-widest px-3 py-1 rounded border ${
          run.status === 'ok' ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
            : run.status === 'failed' ? 'bg-rose-500/10 text-rose-300 border-rose-500/30'
            : 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30 animate-pulse'}`}>{run.status}</span>
      </div>

      {run.error && (
        <div className="bg-rose-950/40 border border-rose-800/40 text-rose-200 p-4 rounded-xl flex gap-3">
          <AlertTriangle className="text-rose-400 shrink-0" size={18} />
          <p className="text-sm">{run.error}</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 glass-panel p-6">
          <h3 className="text-sm font-bold tracking-wider text-gray-400 uppercase mb-5">Steps</h3>
          <RunTimeline run={run} />
        </div>

        <div className="space-y-6">
          {run.summary?.tiers && (
            <div className="glass-panel p-5 space-y-3">
              <h3 className="text-sm font-bold tracking-wider text-gray-400 uppercase">Scoring result</h3>
              <p className="text-xs text-gray-400">As-of {fmtAsOf(run.summary.asof)} · {run.summary.scored} customers</p>
              {(['High', 'Medium', 'Low'] as const).map(t => (
                <div key={t} className="flex justify-between text-sm">
                  <span className={t === 'High' ? 'text-orange-400' : t === 'Medium' ? 'text-yellow-400' : 'text-emerald-400'}>{t}</span>
                  <span className="font-mono text-gray-100">{run.summary.tiers[t]}</span>
                </div>
              ))}
              <div className="flex flex-wrap gap-2 pt-2">
                <Link href="/customers" className="text-xs font-semibold text-cyan-400 border border-cyan-500/30 px-3 py-1.5 rounded-lg">Scored customers</Link>
                <Link href={`/mainframe/reports?runId=${run.id}`} className="text-xs font-semibold text-cyan-400 border border-cyan-500/30 px-3 py-1.5 rounded-lg">Mainframe reports</Link>
              </div>
            </div>
          )}

          {run.summary?.validation && (
            <div className="glass-panel p-5 space-y-2">
              <h3 className="text-sm font-bold tracking-wider text-gray-400 uppercase">Model</h3>
              <p className="text-xs font-mono text-gray-300">{run.summary.model_version}</p>
              <p className="text-sm text-gray-200">ROC-AUC {run.summary.validation.xgboost.roc_auc.toFixed(3)} · PR-AUC {run.summary.validation.xgboost.pr_auc.toFixed(3)}</p>
              <Link href="/mainframe/model" className="text-xs text-cyan-400">Full evaluation →</Link>
            </div>
          )}

          {runctl && (
            <div className="glass-panel p-5">
              <h3 className="text-sm font-bold tracking-wider text-gray-400 uppercase mb-3">REXX reconciliation (RUNCTL)</h3>
              <div className="space-y-1.5">
                {Object.entries(runctl).filter(([k]) => k.startsWith('CHK_')).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-2 text-xs">
                    <span className="text-gray-400">{CHECK_LABELS[k] ?? k}</span>
                    <span className={v === 'OK' ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>{String(v)}</span>
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-4 pt-3 border-t border-[#1f293d]">
                {Object.entries(runctl).filter(([k]) => !k.startsWith('CHK_') && !k.startsWith('REJECT_')).map(([k, v]) => (
                  <div key={k} className="flex justify-between text-[11px] font-mono">
                    <span className="text-gray-500">{k}</span><span className="text-gray-200">{String(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
