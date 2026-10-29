'use client';
import { useState } from 'react';
import { Database, Loader2 } from 'lucide-react';
import { api, fmtAsOf } from '@/lib/api';
import type { VsamCustomer } from '@/lib/types';

/** Reads the customer by key from the VSAM KSDS on z/OS, live, on request (a z/OSMF IDCAMS call takes a few seconds). */
export function VsamCard({ custId }: { custId: string }) {
  const [data, setData] = useState<VsamCustomer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setBusy(true);
    setError(null);
    try {
      setData(await api.get<VsamCustomer>(`/customers/${custId}/vsam`));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const s = data?.score;
  const delta = s && s.prev_asof ? (s.prob - s.prev_prob) * 100 : null;

  return (
    <div className="glass-panel p-5 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest">Live from VSAM (z/OS)</h3>
        <button onClick={load} disabled={busy}
          className="flex items-center gap-1.5 text-xs font-semibold border border-cyan-500/30 text-cyan-300 px-3 py-1.5 rounded-lg disabled:opacity-50">
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Database size={12} />} {data ? 'Re-read' : 'Read by key'}
        </button>
      </div>
      {!data && !error && (
        <p className="text-xs text-gray-500">Reads this customer by key from the KSDS clusters on the mainframe, not from the local copy.</p>
      )}
      {error && <p className="text-xs text-rose-400">{error}</p>}
      {data && (
        <div className="text-xs space-y-1.5">
          {data.customer && <p className="text-gray-300">{data.customer.cust_name} · {data.customer.city} · credit score {data.customer.credit_score}</p>}
          {s ? (
            <>
              <p className="text-gray-300">
                Latest score <span className="font-mono text-white">{(s.prob * 100).toFixed(2)}%</span> {s.tier.trim()} ({s.action}) as-of {fmtAsOf(s.asof)}
              </p>
              {delta !== null && (
                <p className="text-gray-400">
                  Previous {(s.prev_prob * 100).toFixed(2)}% {s.prev_tier.trim()} as-of {fmtAsOf(s.prev_asof)} ·{' '}
                  <span className={delta > 0 ? 'text-rose-400' : 'text-emerald-400'}>{delta > 0 ? '+' : ''}{delta.toFixed(2)} pts</span>
                </p>
              )}
              <p className="text-gray-500">Scored {s.times_scored}× · top factor {s.top_factor}</p>
            </>
          ) : <p className="text-gray-500">No score record in {data.source.score} yet.</p>}
          <p className="text-[10px] text-gray-600 font-mono pt-1">{data.source.customer} + {data.source.score} · {data.ms} ms</p>
        </div>
      )}
    </div>
  );
}
