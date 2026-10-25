import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { Run } from '@/lib/types';

/** Follows one Control Center run; polls every 2 s until it finishes. */
export function useRun(runId: number | null | undefined) {
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) { setRun(null); return; }
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const r = await api.get<Run>(`/runs/${runId}`);
        if (stop) return;
        setRun(r);
        setError(null);
        if (r.status === 'running') timer = setTimeout(tick, 2000);
      } catch (e: any) {
        if (!stop) { setError(e.message); timer = setTimeout(tick, 4000); }
      }
    };
    tick();
    return () => { stop = true; clearTimeout(timer); };
  }, [runId]);

  return { run, error };
}
