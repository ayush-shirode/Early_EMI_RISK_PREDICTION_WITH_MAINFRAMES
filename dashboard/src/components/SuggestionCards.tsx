'use client';
import { Lightbulb, TrendingDown, Ban, AlertOctagon, HelpCircle } from 'lucide-react';

interface Props {
  suggestions: string[];
  severity: string;
}

export function SuggestionCards({ suggestions = [], severity = 'low' }: Props) {
  // Map icons dynamically based on text keyword matches
  const getIcon = (text: string, index: number) => {
    const lower = text.toLowerCase();
    if (lower.includes('reduce') || lower.includes('limit') || lower.includes('spending')) {
      return <TrendingDown className="text-orange-400" size={18} />;
    }
    if (lower.includes('avoid') || lower.includes('cancel') || lower.includes('restrict')) {
      return <Ban className="text-red-400" size={18} />;
    }
    if (lower.includes('emergency') || lower.includes('danger') || lower.includes('critical')) {
      return <AlertOctagon className="text-rose-500 animate-pulse" size={18} />;
    }
    // Fallback based on index
    const iconList = [
      <Lightbulb className="text-amber-400" size={18} />,
      <TrendingDown className="text-cyan-400" size={18} />,
      <HelpCircle className="text-blue-400" size={18} />
    ];
    return iconList[index % iconList.length];
  };

  return (
    <div className="glass-panel p-6 overflow-hidden flex flex-col h-full justify-between">
      <div>
        <h3 className="text-sm font-bold tracking-wider text-gray-400 uppercase mb-4 flex items-center gap-2">
          <span>🧠 AI Decision Recommendations</span>
        </h3>
        
        {suggestions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <span className="text-3xl mb-2">✨</span>
            <p className="text-sm text-gray-400">No active AI suggestions. Trigger a prediction run to populate.</p>
          </div>
        ) : (
          <div className="space-y-3.5">
            {suggestions.map((item, idx) => (
              <div 
                key={idx} 
                className="flex items-start gap-3.5 p-3.5 rounded-xl bg-[#1a2133]/60 border border-[#2b3a57] hover:border-cyan-500/30 transition-all duration-200"
              >
                <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-[#24314c] border border-[#3b4c6b] shrink-0">
                  {getIcon(item, idx)}
                </div>
                <p className="text-sm text-gray-200 leading-relaxed">{item}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="mt-4 pt-3 border-t border-[#1f293d] text-[10px] text-gray-500 flex items-center justify-between">
        <span>Engine model: TinyLlama v1.1</span>
        <span>Validated via Zod contract</span>
      </div>
    </div>
  );
}
