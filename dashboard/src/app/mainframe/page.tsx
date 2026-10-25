'use client';
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { CheckCircle2, Circle, RefreshCw, AlertTriangle, Server, Loader2 } from 'lucide-react';
import { api, fmtAsOf, fmtTime, ASOF_OPTIONS } from '@/lib/api';
import type { MainframeStatus } from '@/lib/types';
import { ActionButton } from '@/components/ActionButton';


function Step({ n, title, done, active, children, detail }: {
  n: number; title: string; done: boolean; active: boolean; detail?: React.ReactNode; children?: React.ReactNode;
}) {
  return (
    <div className={`p-5 rounded-2xl border transition-all ${active ? 'border-cyan-500/40 bg-cyan-500/5' : 'border-[#1f293d] bg-[#131926]/60'}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          {done ? <CheckCircle2 className="text-emerald-400 mt-0.5" size={20} /> : <Circle className="text-gray-600 mt-0.5" size={20} />}
          <div>
            <p className="text-sm font-bold text-gray-100">{n}. {title}</p>
            <div className="text-xs text-gray-400 mt-1 leading-relaxed">{detail}</div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">{children}</div>
      </div>
    </div>
  );
}

export default function MainframeOverview() {
  const [status, setStatus] = useState<MainframeStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [customers, setCustomers] = useState(1500);
  const [seed, setSeed] = useState(42);
  const [asof, setAsof] = useState(20260930);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    try {
      setStatus(await api.get<MainframeStatus>(`/mainframe/status${refresh ? '?refresh=true' : ''}`));
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (error) {
    return (
      <div className="bg-rose-950/40 border border-rose-800/40 text-rose-200 p-5 rounded-xl flex gap-3">
        <AlertTriangle className="text-rose-400 shrink-0" size={18} />
        <div>
          <p className="font-bold text-sm">Backend not reachable</p>
          <p className="text-xs mt-1">{error}</p>
        </div>
      </div>
    );
  }
  if (!status) {
    return <div className="flex items-center gap-2 text-gray-400 text-sm"><Loader2 className="animate-spin" size={16} /> Checking the mainframe (several Zowe calls)…</div>;
  }

  const mf = status.mainframe;
  const connected = !!mf?.ok;
  const libsOk = connected && Object.values(mf!.libraries ?? {}).every(Boolean);
  const progsOk = connected && Object.values(mf!.programs ?? {}).every(Boolean);
  const setupDone = libsOk && progsOk;
  const dataOk = connected && Object.values(mf!.inputs ?? {}).every(Boolean);
  const modelOk = !!status.model;
  const scored = !!status.last_score_run && status.last_score_run.status === 'ok';
  const busy = !!status.active_run;
  const next = !connected ? 1 : !setupDone ? 2 : !dataOk ? 3 : !modelOk ? 4 : !scored ? 5 : 0;
  const last = status.last_score_run;

  return (
    <div className="space-y-6">
      {busy && (
        <Link href={`/mainframe/runs/${status.active_run}`}
          className="flex items-center gap-3 p-4 rounded-xl border border-cyan-500/40 bg-cyan-500/5 text-sm text-cyan-200">
          <Loader2 className="animate-spin text-cyan-400" size={16} />
          Run #{status.active_run} is in progress. Open it to follow the steps live.
        </Link>
      )}

      <div className="glass-panel p-6 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className={`p-3 rounded-xl border ${connected ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-rose-500/10 border-rose-500/30 text-rose-400'}`}>
            <Server size={22} />
          </div>
          <div>
            <p className="text-sm font-bold text-gray-100">
              {connected ? `Connected to ${mf!.connection?.system}` : 'Not connected to the mainframe'}
            </p>
            <p className="text-xs text-gray-400 font-mono mt-0.5">
              {connected
                ? `user ${mf!.connection?.user} · z/OSMF ${mf!.connection?.zosmf_version} · port ${mf!.connection?.port} · HLQ ${mf!.hlq}.EWS`
                : mf?.error}
            </p>
            <p className="text-[11px] text-gray-500 mt-0.5">Checked {status.checked_at ? new Date(status.checked_at * 1000).toLocaleTimeString('en-IN') : '—'}</p>
          </div>
        </div>
        <button onClick={() => load(true)} disabled={loading}
          className="flex items-center gap-2 bg-[#131926] border border-[#1f293d] hover:border-cyan-500/30 text-gray-200 px-4 py-2 rounded-xl text-sm font-semibold disabled:opacity-50">
          <RefreshCw size={14} className={loading ? 'animate-spin text-cyan-400' : ''} /> Re-check
        </button>
      </div>

      <div className="space-y-3">
        <Step n={1} title="Connect to z/OS" done={connected} active={next === 1}
          detail={connected ? 'z/OSMF answers with your Zowe profile credentials.'
            : <>Zowe CLI could not reach z/OSMF. Credentials live in the Zowe secure store; set them once in a terminal with <span className="font-mono">zowe config secure</span>, then re-check.</>}>
          <ActionButton action="test_connection" label="Test connection" variant="secondary" disabled={busy} />
        </Step>

        <Step n={2} title="Set up the mainframe" done={setupDone} active={next === 2}
          detail={<>Allocates the EWS libraries, uploads copybooks, COBOL, DFSORT, REXX and JCL, then submits <span className="font-mono">EWSCOMP</span> to compile and link the 4 COBOL programs.
            {connected && <div className="flex flex-wrap gap-1.5 mt-2">
              {Object.entries({ ...mf!.libraries, ...mf!.programs }).map(([k, v]) => (
                <span key={k} className={`text-[10px] font-mono px-2 py-0.5 rounded border ${v ? 'border-emerald-500/30 text-emerald-300' : 'border-gray-600 text-gray-500'}`}>{k}</span>
              ))}</div>}</>}>
          <ActionButton action="setup" label={setupDone ? 'Run setup again' : 'Set up mainframe'} variant={setupDone ? 'secondary' : 'primary'} disabled={busy || !connected} />
          {setupDone && <ActionButton action="compile" label="Recompile COBOL" variant="secondary" disabled={busy} />}
        </Step>

        <Step n={3} title="Generate & upload input data" done={dataOk} active={next === 3}
          detail={<>Creates synthetic customers, loans, 24 months of EMI history and account summaries in the copybook formats (including ~1% deliberately bad records), and uploads them to the 4 input data sets.
            {status.data && <span className="block mt-1 text-gray-500">Current data: {status.data.customers} customers, seed {status.data.seed}, {Object.values(status.data.records).reduce((a, b) => a + b, 0).toLocaleString('en-IN')} records, uploaded {fmtTime(status.data.generated_at)}</span>}</>}>
          <label className="text-xs text-gray-400">Customers
            <input type="number" min={200} max={3000} value={customers} onChange={e => setCustomers(+e.target.value)}
              className="ml-2 w-20 bg-[#0c101b] border border-[#1f293d] rounded-lg px-2 py-1 text-sm font-mono text-white" />
          </label>
          <label className="text-xs text-gray-400">Seed
            <input type="number" min={1} value={seed} onChange={e => setSeed(+e.target.value)}
              className="ml-2 w-16 bg-[#0c101b] border border-[#1f293d] rounded-lg px-2 py-1 text-sm font-mono text-white" />
          </label>
          <ActionButton action="generate_data" label="Generate & upload" params={{ customers, seed }}
            variant={dataOk ? 'secondary' : 'primary'} disabled={busy || !setupDone} />
        </Step>

        <Step n={4} title="Train the model" done={modelOk} active={next === 4}
          detail={<>Runs <span className="font-mono">EWSBATCH</span> in TRAIN mode for 4 quarter-end dates (the COBOL program also derives the 90-day outcome label), downloads the features and trains XGBoost.
            {status.model && <span className="block mt-1 text-gray-500">Model {status.model.model_version}: ROC-AUC {status.model.roc_auc.toFixed(3)} on {status.model.rows.toLocaleString('en-IN')} rows · <Link href="/mainframe/model" className="text-cyan-400">details</Link></span>}</>}>
          <ActionButton action="train_model" label={modelOk ? 'Retrain' : 'Train model'} variant={modelOk ? 'secondary' : 'primary'} disabled={busy || !dataOk} />
        </Step>

        <Step n={5} title="Run the batch & score customers" done={scored} active={next === 5}
          detail={<>Submits <span className="font-mono">EWSBATCH</span> (DFSORT → COBOL validate → COBOL match → DFSORT CSV → REXX reconcile), scores every customer, writes the scores back to <span className="font-mono">EWS.SCORES</span> and runs <span className="font-mono">EWSRPTJ</span> for the intervention report.
            {last && <span className="block mt-1 text-gray-500">Last run #{last.id}: {last.status} · as-of {fmtAsOf(last.summary?.asof)} · {last.summary?.tiers ? `${last.summary.tiers.High} high / ${last.summary.tiers.Medium} medium / ${last.summary.tiers.Low} low` : last.error}</span>}</>}>
          <select value={asof} onChange={e => setAsof(+e.target.value)}
            className="bg-[#0c101b] border border-[#1f293d] rounded-lg px-2 py-1.5 text-sm font-mono text-white">
            {ASOF_OPTIONS.map(a => <option key={a} value={a}>as-of {fmtAsOf(a)}</option>)}
          </select>
          <ActionButton action="run_batch" label="Run batch & score" params={{ asof }} disabled={busy || !modelOk} />
        </Step>
      </div>

      {next === 0 && (
        <div className="glass-panel p-5 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-gray-300">Everything is set up. The risk pages show the customers scored by run #{last?.id}.</p>
          <div className="flex gap-2">
            <Link href="/" className="px-4 py-2 rounded-xl text-sm font-bold bg-gradient-to-r from-blue-600 to-cyan-500 text-white">Open dashboard</Link>
            <Link href="/mainframe/reports" className="px-4 py-2 rounded-xl text-sm font-semibold border border-[#1f293d] text-gray-200">Mainframe reports</Link>
          </div>
        </div>
      )}

      <div className="glass-panel p-5 flex flex-wrap items-center justify-between gap-3 border-rose-900/40">
        <div>
          <p className="text-sm font-bold text-rose-300">Reset mainframe data</p>
          <p className="text-xs text-gray-500">Deletes the EWS input, work and output data sets (keeps the JCL, copybook, DFSORT and REXX libraries).</p>
        </div>
        <ActionButton action="reset_data" label="Reset data" params={{ confirm: true }} variant="danger" disabled={busy || !connected}
          confirm="Delete all EWS data sets on the mainframe (libraries are kept)?" />
      </div>
    </div>
  );
}
