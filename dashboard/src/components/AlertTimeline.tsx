'use client';
import { ShieldAlert, Clock, Info } from 'lucide-react';
import { Prediction } from '@/lib/types';

interface Props {
  history: Prediction[];
  title?: string;
}

export function AlertTimeline({ history = [], title = 'Prediction history (one per batch run)' }: Props) {
  const getSeverityStyles = (severity: string) => {
    switch (severity) {
      case 'high':
        return { bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/30' };
      case 'medium':
        return { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30' };
      default:
        return { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/30' };
    }
  };

  const formatDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toLocaleString('en-IN', {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="glass-panel p-6 flex flex-col overflow-hidden">
      <div className="flex items-center justify-between mb-4 border-b border-[#1f293d] pb-3">
        <h3 className="text-sm font-bold tracking-wider text-gray-400 uppercase flex items-center gap-2">
          <ShieldAlert size={16} className="text-blue-400" />
          <span>{title}</span>
        </h3>
        <span className="text-[10px] bg-[#1a2133] border border-[#2b3a57] text-gray-400 px-2 py-0.5 rounded font-mono uppercase">
          {history.length} {history.length === 1 ? 'run' : 'runs'}
        </span>
      </div>

      <div className="overflow-y-auto max-h-[340px] pr-2 space-y-4">
        {history.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-center text-gray-500">
            <Clock size={28} className="mb-2 text-gray-600 animate-pulse" />
            <p className="text-sm">No earlier predictions for this customer.</p>
          </div>
        ) : (
          <div className="relative border-l border-[#1f293d] ml-2 pl-5 space-y-4">
            {history.map((pred) => {
              const styles = getSeverityStyles(pred.severity);
              return (
                <div key={pred.prediction_id} className="relative group">
                  {/* Timeline circular notch indicator */}
                  <span 
                    className={`absolute -left-[26px] top-1.5 flex h-3 w-3 rounded-full border-2 bg-darkBg transition-all group-hover:scale-125`}
                    style={{ borderColor: pred.severity === 'high' ? '#f97316' : pred.severity === 'medium' ? '#eab308' : '#10b981' }}
                  />

                  <div className="p-3.5 rounded-xl bg-[#141a27] border border-[#1f293d] hover:border-[#3b82f6]/20 transition-all">
                    <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                      <span className="text-xs text-gray-400 font-mono flex items-center gap-1">
                        <Clock size={11} />
                        {formatDate(pred.created_at)}
                      </span>
                      
                      <div className="flex items-center gap-2">
                        <span className={`text-[10px] font-black tracking-widest px-2 py-0.5 rounded border uppercase ${styles.bg} ${styles.text} ${styles.border}`}>
                          {pred.severity}
                        </span>
                        <span className="text-xs font-mono font-semibold text-gray-300">
                          Risk: {(pred.miss_probability * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>

                    <p className="text-sm text-gray-300 leading-relaxed font-sans font-normal mb-2">
                      {pred.reasoning}
                    </p>

                    <div className="text-[10px] text-gray-500 flex items-center justify-between bg-[#0e131d]/60 px-2 py-1 rounded">
                      <span className="font-mono">EMI: ₹{pred.emi_amount}</span>
                      <span>{pred.emi_due_date}</span>
                      <span>ID: {pred.prediction_id}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
