'use client';
import { useEffect, useState } from 'react';
import { PageShell, Loading } from '@/components/PageShell';
import { RiskGauge } from '@/components/RiskGauge';
import { SpendTrendChart } from '@/components/SpendTrendChart';
import { PredictionCTA } from '@/components/PredictionCTA';
import { AlertTimeline } from '@/components/AlertTimeline';
import { EmptyState } from '@/components/EmptyState';
import { useRiskPolling } from '@/hooks/useRiskPolling';
import { useCustomer } from '@/context/CustomerContext';
import { SEVERITY_BADGE } from '@/lib/customers';
import { fmtAsOf, inr, ordinal } from '@/lib/api';
import { AlertTriangle, Calendar, RefreshCw, Sliders, Play, Wallet, Server, X } from 'lucide-react';

const MAX_EMI = 500_000;

const RING: Record<string, string> = {
  high: 'border-orange-500 shadow-[0_0_15px_rgba(249,115,22,0.15)]',
  medium: 'border-yellow-500 shadow-[0_0_15px_rgba(234,179,8,0.15)]',
  low: 'border-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.15)]',
};

export default function Dashboard() {
  const { selectedCustomer: c, loading: listLoading, error: listError, reload } = useCustomer();
  const { alerts, whatIf, clearWhatIf, triggering, error, trigger } = useRiskPolling(c?.id, 60000);
  const [customEmi, setCustomEmi] = useState('');

  useEffect(() => { if (c) setCustomEmi(String(Math.round(c.emiAmount))); }, [c]);

  if (listLoading && !c) {
    return (
      <PageShell><Loading text="Loading scored customers…" /></PageShell>
    );
  }
  if (!c) return <PageShell><EmptyState error={listError} /></PageShell>;

  const parsedEmi = parseFloat(customEmi);
  const emiInvalid = !isNaN(parsedEmi) && parsedEmi > MAX_EMI;
  const severity = whatIf ? whatIf.tier.toLowerCase() : c.severity;
  const score = whatIf ? whatIf.riskScore : c.riskScore;
  const prob = whatIf ? whatIf.probability : c.missProbability;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isNaN(parsedEmi) || parsedEmi <= 0 || emiInvalid) return;
    await trigger(parsedEmi);
  };

  return (
    <PageShell>

        <div className="glass-panel flex flex-col md:flex-row md:items-center justify-between gap-4 p-5">
          <div>
            <h2 className="text-xl font-bold tracking-tight text-white">{c.name} <span className="text-gray-500 font-mono text-base">{c.id}</span></h2>
            <p className="text-sm text-gray-400">
              {c.city} · {c.accountType.replace('-', ' ')} · {c.activeLoans} active loan{c.activeLoans === 1 ? '' : 's'} (largest: {c.loanType})
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-gray-400">
            <span className="flex items-center gap-1.5 bg-[#131926] border border-[#1f293d] px-3 py-2 rounded-xl font-mono">
              <Server size={13} className="text-cyan-400" /> batch run #{c.runId} · as-of {fmtAsOf(c.asOf)}
            </span>
            <button onClick={() => reload()}
              className="flex items-center gap-2 bg-[#131926] border border-[#1f293d] hover:border-cyan-500/30 text-gray-200 px-4 py-2 rounded-xl text-sm font-semibold">
              <RefreshCw size={14} className={listLoading ? 'animate-spin text-cyan-400' : ''} /> Refresh
            </button>
          </div>
        </div>

        {error && (
          <div className="bg-rose-950/40 border border-rose-800/40 text-rose-200 p-4 rounded-xl flex items-start gap-3.5">
            <AlertTriangle className="text-rose-400 shrink-0 mt-0.5" size={18} />
            <p className="text-xs text-rose-300/80 leading-relaxed">{error}</p>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="space-y-6 lg:col-span-1">
            <RiskGauge score={score} severity={severity} />

            <div className="glass-panel p-6 relative overflow-hidden">
              <h3 className="text-sm font-bold tracking-wider text-gray-400 uppercase mb-1 flex items-center gap-2">
                <Sliders size={16} className="text-cyan-400" /> What-if: change the EMI
              </h3>
              <p className="text-xs text-gray-500 mb-4">Re-scores this customer with the trained model, keeping every other feature from the mainframe batch.</p>
              <form onSubmit={submit} className="space-y-4">
                <div>
                  <label className="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1.5">Total monthly EMI (₹)</label>
                  <div className="relative">
                    <span className="absolute left-3 top-2.5 text-gray-500 font-mono text-sm">₹</span>
                    <input type="number" value={customEmi} onChange={e => setCustomEmi(e.target.value)} min="1" max={MAX_EMI} required
                      className={`w-full bg-[#0c101b] border rounded-xl pl-8 pr-3 py-2 text-sm text-white focus:outline-none font-mono ${emiInvalid ? 'border-rose-500' : 'border-[#1f293d] focus:border-cyan-500'}`} />
                  </div>
                  {emiInvalid && <p className="text-xs text-rose-400 mt-1">Enter the monthly EMI (max {inr(MAX_EMI)}), not the loan amount.</p>}
                </div>
                <button type="submit" disabled={triggering || emiInvalid}
                  className="w-full bg-gradient-to-r from-blue-600 to-cyan-500 hover:from-blue-700 hover:to-cyan-600 text-white font-bold py-2.5 px-4 rounded-xl text-sm flex items-center justify-center gap-2 disabled:opacity-50">
                  {triggering ? <><RefreshCw size={14} className="animate-spin" /> Re-scoring…</> : <><Play size={14} className="fill-current" /> Re-score with model</>}
                </button>
              </form>
              {whatIf && (
                <div className="mt-4 p-3 rounded-xl bg-cyan-500/5 border border-cyan-500/30 text-xs text-gray-300 space-y-1">
                  <div className="flex justify-between items-center">
                    <span className="font-bold text-cyan-300">What-if with EMI {inr(whatIf.emiAmount)}</span>
                    <button onClick={clearWhatIf} title="Back to the batch score"><X size={13} /></button>
                  </div>
                  <p>Risk {c.riskScore}% → <span className="font-bold text-white">{whatIf.riskScore}%</span> ({whatIf.tier})</p>
                </div>
              )}
            </div>

            <div className={`p-5 rounded-2xl bg-[#131926]/50 border-2 ${RING[severity] ?? RING.low}`}>
              <h4 className="text-xs font-black tracking-widest text-gray-400 uppercase mb-2">Why this score</h4>
              <p className="text-sm font-mono text-gray-200 mb-2">
                Stress probability (next 90 days): <span className="font-bold text-white text-base">{(prob * 100).toFixed(0)}%</span>
              </p>
              <p className="text-xs text-gray-400 leading-relaxed">{whatIf ? whatIf.reasoning : c.reasoning}</p>
            </div>
          </div>

          <div className="lg:col-span-2 space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="glass-panel p-4 flex items-center gap-4">
                <div className="p-3 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400"><Wallet size={20} /></div>
                <div>
                  <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block">Avg balance (3 m)</span>
                  <span className="text-base font-bold font-mono text-white">{inr(c.assessedSavings)}</span>
                </div>
              </div>
              <div className="glass-panel p-4 flex items-center gap-4">
                <div className="p-3 rounded-xl bg-orange-500/10 border border-orange-500/20 text-orange-400"><AlertTriangle size={20} /></div>
                <div>
                  <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block">Risk tier</span>
                  <span className={`text-xs font-black px-2 py-0.5 rounded border uppercase mt-0.5 inline-block ${SEVERITY_BADGE[severity]}`}>{severity}</span>
                </div>
              </div>
              <div className="glass-panel p-4 flex items-center gap-4">
                <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400"><Calendar size={20} /></div>
                <div>
                  <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block">Monthly EMI</span>
                  <span className="text-base font-bold font-mono text-white block">{inr(c.emiAmount)}</span>
                  <span className="text-[11px] text-gray-500">due on the {ordinal(c.emiDueDate)}</span>
                </div>
              </div>
            </div>

            <SpendTrendChart data={c.spendTrend} emiAmount={c.emiAmount} />
            <PredictionCTA customer={c} />
            <AlertTimeline history={alerts} />
          </div>
        </div>
      </PageShell>
  );
}
