'use client';
import Link from 'next/link';
import { CheckCircle2, XCircle, Loader2, Circle, MinusCircle, FileText } from 'lucide-react';
import type { Run, RunStep } from '@/lib/types';
import { duration } from '@/lib/api';

const ICON = {
  ok: <CheckCircle2 size={18} className="text-emerald-400" />,
  failed: <XCircle size={18} className="text-rose-400" />,
  running: <Loader2 size={18} className="text-cyan-400 animate-spin" />,
  pending: <Circle size={18} className="text-gray-600" />,
  skipped: <MinusCircle size={18} className="text-gray-600" />,
};

function rcClass(s: { rc: number | null; status: string }) {
  if (s.status === 'abended') return 'bg-rose-500/15 text-rose-300 border-rose-500/40';
  if (s.status === 'not executed') return 'bg-gray-500/10 text-gray-500 border-gray-600/40';
  if ((s.rc ?? 0) === 0) return 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30';
  if ((s.rc ?? 0) <= 4) return 'bg-yellow-500/10 text-yellow-300 border-yellow-500/30';
  return 'bg-rose-500/15 text-rose-300 border-rose-500/40';
}

/** JCL step return codes, e.g. STEP070 RC 4. */
export function JobSteps({ steps }: { steps: NonNullable<RunStep['data']['steps']> }) {
  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {steps.map((s, i) => (
        <span key={i} title={s.status}
          className={`text-[10px] font-mono px-2 py-0.5 rounded border ${rcClass(s)}`}>
          {s.step}{s.procstep ? `.${s.procstep}` : ''}{' '}
          {s.status === 'abended' ? s.abend : s.status === 'not executed' ? 'skipped' : `RC ${s.rc}`}
        </span>
      ))}
    </div>
  );
}

export function RunTimeline({ run }: { run: Run }) {
  return (
    <ol className="relative border-l border-[#1f293d] ml-3 space-y-4">
      {(run.steps ?? []).map(step => (
        <li key={step.seq} className="ml-6">
          <span className="absolute -left-[10px] bg-darkBg rounded-full">{ICON[step.status]}</span>
          <div className={`p-3.5 rounded-xl border ${step.status === 'running' ? 'border-cyan-500/40 bg-cyan-500/5'
            : step.status === 'failed' ? 'border-rose-500/40 bg-rose-500/5' : 'border-[#1f293d] bg-[#141a27]'}`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className={`text-sm font-semibold ${step.status === 'pending' || step.status === 'skipped' ? 'text-gray-500' : 'text-gray-100'}`}>
                {step.name}
              </span>
              <span className="text-[11px] font-mono text-gray-500">
                {duration(step.started_at, step.status === 'running' ? null : step.finished_at)}
              </span>
            </div>
            {step.detail && (
              <p className={`text-xs mt-1 leading-relaxed ${step.status === 'failed' ? 'text-rose-300' : 'text-gray-400'}`}>
                {step.detail}
              </p>
            )}
            {step.data?.steps && step.data.steps.length > 0 && <JobSteps steps={step.data.steps} />}
            {step.data?.jobid && (
              <Link href={`/mainframe/jobs/${step.data.jobid}`}
                className="inline-flex items-center gap-1.5 mt-2 text-xs font-semibold text-cyan-400 hover:text-cyan-300">
                <FileText size={12} /> Job output {step.data.jobname} {step.data.jobid}
              </Link>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
