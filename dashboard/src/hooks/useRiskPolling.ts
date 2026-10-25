import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import type { Prediction } from '@/lib/types';

interface WhatIf {
  probability: number; riskScore: number; tier: string; reasoning: string; action: string; emiAmount: number;
}

/** Prediction history for one customer, plus what-if re-scoring with a different EMI. */
export function useRiskPolling(userId: string | undefined, intervalMs = 30000) {
  const [alerts, setAlerts] = useState<Prediction[]>([]);
  const [whatIf, setWhatIf] = useState<WhatIf | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchHistory = useCallback(async (showLoading = false) => {
    if (!userId) return;
    if (showLoading) setLoading(true);
    try {
      const rows = await api.get<any[]>(`/customers/${userId}/history`);
      setAlerts(rows.map(r => ({
        prediction_id: `run #${r.run_id}`,
        severity: r.tier.toLowerCase(),
        miss_probability: r.probability,
        reasoning: r.reasoning,
        created_at: r.created_at,
        emi_amount: Math.round(r.total_emi),
        emi_due_date: `as-of ${String(r.as_of).replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3')}`,
      })));
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    setWhatIf(null);
    fetchHistory(true);
    const id = setInterval(() => fetchHistory(false), intervalMs);
    return () => clearInterval(id);
  }, [userId, intervalMs, fetchHistory]);

  const trigger = async (emiAmount: number) => {
    if (!userId) return false;
    setTriggering(true);
    setError(null);
    try {
      setWhatIf(await api.post<WhatIf>(`/customers/${userId}/what-if`, { emiAmount }));
      return true;
    } catch (e: any) {
      setError(e.message);
      return false;
    } finally {
      setTriggering(false);
    }
  };

  return { alerts, whatIf, clearWhatIf: () => setWhatIf(null), loading, triggering, error,
           refresh: () => fetchHistory(true), trigger };
}
