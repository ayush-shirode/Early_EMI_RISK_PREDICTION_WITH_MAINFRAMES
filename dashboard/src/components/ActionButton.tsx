'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Play, Loader2 } from 'lucide-react';
import { startAction } from '@/lib/api';

interface Props {
  action: string;
  label: string;
  params?: Record<string, unknown>;
  disabled?: boolean;
  confirm?: string;
  variant?: 'primary' | 'secondary' | 'danger';
  onStarted?: (runId: number) => void;
}

/** Starts a whitelisted backend action and opens its live run page. */
export function ActionButton({ action, label, params = {}, disabled, confirm, variant = 'primary', onStarted }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const click = async () => {
    if (confirm && !window.confirm(confirm)) return;
    setBusy(true);
    setError(null);
    try {
      const { runId } = await startAction(action, params);
      if (onStarted) onStarted(runId);
      else router.push(`/mainframe/runs/${runId}`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const styles = {
    primary: 'bg-gradient-to-r from-blue-600 to-cyan-500 hover:from-blue-700 hover:to-cyan-600 text-white shadow-[0_0_15px_rgba(59,130,246,0.25)]',
    secondary: 'bg-[#131926] border border-[#1f293d] hover:border-cyan-500/40 text-gray-200',
    danger: 'bg-rose-950/40 border border-rose-800/50 hover:border-rose-500/60 text-rose-300',
  }[variant];

  return (
    <div className="inline-flex flex-col gap-1">
      <button onClick={click} disabled={disabled || busy}
        className={`inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition-all disabled:opacity-40 disabled:cursor-not-allowed ${styles}`}>
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Play size={13} className="fill-current" />}
        {label}
      </button>
      {error && <span className="text-xs text-rose-400 max-w-xs">{error}</span>}
    </div>
  );
}
