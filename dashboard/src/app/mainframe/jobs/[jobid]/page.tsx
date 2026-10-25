'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { api } from '@/lib/api';

interface Spool {
  job: { jobname: string; jobid: string; owner: string; status: string; retcode: string; class: string };
  files: { id: number; ddname: string; stepname: string | null; procstep: string | null; 'record-count'?: number }[];
}

/** JES spool output of one job, read from z/OS through Zowe. */
export default function JobPage({ params }: { params: { jobid: string } }) {
  const [spool, setSpool] = useState<Spool | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<Spool>(`/jobs/${params.jobid}/spool`).then(s => {
      setSpool(s);
      const first = s.files.find(f => ['SYSOUT', 'SYSTSPRT', 'TOOLMSG'].includes(f.ddname)) ?? s.files[0];
      if (first) setActive(first.id);
    }).catch(e => setError(e.message));
  }, [params.jobid]);

  useEffect(() => {
    if (active == null) return;
    setLoading(true);
    api.get<string>(`/jobs/${params.jobid}/spool/${active}`)
      .then(t => setText(t)).catch(e => setText(String(e.message))).finally(() => setLoading(false));
  }, [active, params.jobid]);

  if (error) return <p className="text-sm text-rose-400">{error}</p>;
  if (!spool) return <div className="flex items-center gap-2 text-sm text-gray-400"><Loader2 className="animate-spin" size={16} /> Reading the spool from JES…</div>;

  return (
    <div className="space-y-4">
      <button onClick={() => history.back()} className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-cyan-400">
        <ArrowLeft size={14} /> Back
      </button>
      <div className="glass-panel p-5 flex flex-wrap gap-6 text-sm">
        {Object.entries(spool.job).map(([k, v]) => (
          <div key={k}><p className="text-[10px] uppercase tracking-widest text-gray-500">{k}</p><p className="font-mono text-gray-100">{v ?? '—'}</p></div>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <div className="glass-panel p-3 space-y-1 h-fit">
          {spool.files.map(f => (
            <button key={f.id} onClick={() => setActive(f.id)}
              className={`w-full text-left px-3 py-2 rounded-lg text-xs font-mono transition-all ${active === f.id ? 'bg-[#1a2640] text-cyan-300' : 'text-gray-400 hover:bg-[#131926]'}`}>
              <span className="text-gray-500">{f.stepname ?? 'JES2'}{f.procstep ? `.${f.procstep}` : ''}</span> {f.ddname}
            </button>
          ))}
        </div>
        <div className="lg:col-span-3 glass-panel p-0 overflow-hidden">
          {loading ? <div className="p-6 text-sm text-gray-400">Loading…</div> : (
            <pre className="p-4 text-[11px] leading-[1.35] font-mono text-gray-200 overflow-auto max-h-[70vh] whitespace-pre">{text}</pre>
          )}
        </div>
      </div>
    </div>
  );
}
