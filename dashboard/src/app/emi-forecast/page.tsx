'use client';
import { useState } from 'react';
import Link from 'next/link';
import { Header } from '@/components/Header';
import { EmptyState } from '@/components/EmptyState';
import { useCustomer } from '@/context/CustomerContext';
import { getSeverityColor, SEVERITY_BADGE } from '@/lib/customers';
import { inr } from '@/lib/api';
import { ExternalLink } from 'lucide-react';

function MissBar({ probability, severity }: { probability: number; severity: string }) {
  const color = getSeverityColor(severity);
  const pct = Math.round(probability * 100);
  return (
    <div className="relative w-full h-7 bg-[#1f293d] rounded-lg overflow-hidden">
      <div
        className="h-full rounded-lg transition-all duration-700"
        style={{ width: `${pct}%`, backgroundColor: color + '60', borderRight: `2px solid ${color}` }}
      />
      <span className="absolute inset-0 flex items-center justify-center text-xs font-black font-mono"
        style={{ color }}>
        {pct}% stress probability
      </span>
    </div>
  );
}

function SavingsBar({ savings, emiAmount, severity }: { savings: number; emiAmount: number; severity: string }) {
  const color = getSeverityColor(severity);
  const pct = Math.min(100, (savings / emiAmount) * 100);
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-gray-500">
        <span>{inr(savings)} avg balance</span>
        <span>{inr(emiAmount)} EMI</span>
      </div>
      <div className="h-2 bg-[#1f293d] rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

export default function EmiForecastPage() {
  const today = new Date();
  const { allCustomers: CUSTOMERS } = useCustomer();
  const [limit, setLimit] = useState(20);
  if (!CUSTOMERS.length) return <div className="min-h-screen bg-darkBg flex flex-col"><Header /><EmptyState /></div>;
  // Customers arrive sorted by stress probability; the forecast focuses on those the model flags.
  const flagged = CUSTOMERS.filter(c => c.severity !== 'low');
  const sortedCustomers = flagged.slice(0, limit);

  const getDaysUntil = (emiDueDate: string) => {
    const day = parseInt(emiDueDate);
    let due = new Date(today.getFullYear(), today.getMonth(), day);
    if (due < today) due = new Date(today.getFullYear(), today.getMonth() + 1, day);
    return Math.ceil((due.getTime() - today.getTime()) / 86400000);
  };

  const safe = CUSTOMERS.filter(c => c.severity === 'low').length;
  const atRisk = CUSTOMERS.filter(c => c.severity === 'medium').length;
  const critical = CUSTOMERS.filter(c => c.severity === 'high').length;
  const badgeStyles = SEVERITY_BADGE;

  return (
    <div className="min-h-screen bg-darkBg text-gray-100 flex flex-col">
      <Header />
      <main className="flex-1 p-6 max-w-7xl mx-auto w-full space-y-6">

        <div>
          <h2 className="text-2xl font-bold text-white">EMI Miss Forecast</h2>
          <p className="text-sm text-gray-400 mt-0.5">Borrowers the model flags (Medium/High) ahead of their next EMI dates</p>
        </div>

        {/* Summary Banner */}
        <div className="grid grid-cols-3 gap-4">
          <div className="glass-panel p-5 border-l-4 border-emerald-500">
            <p className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Low risk</p>
            <p className="text-4xl font-black font-mono text-emerald-400">{safe}</p>
            <p className="text-xs text-gray-500 mt-1">Continue regular monitoring</p>
          </div>
          <div className="glass-panel p-5 border-l-4 border-amber-500">
            <p className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Medium risk</p>
            <p className="text-4xl font-black font-mono text-amber-400">{atRisk}</p>
            <p className="text-xs text-gray-500 mt-1">Review repayment pattern, pre-due reminder</p>
          </div>
          <div className="glass-panel p-5 border-l-4 border-rose-500">
            <p className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">High risk</p>
            <p className="text-4xl font-black font-mono text-rose-400">{critical}</p>
            <p className="text-xs text-gray-500 mt-1">Prioritise early intervention</p>
          </div>
        </div>

        {/* Forecast Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {sortedCustomers.map(c => {
            const color = getSeverityColor(c.severity);
            const daysUntil = getDaysUntil(c.emiDueDate);
            return (
              <div
                key={c.id}
                className="glass-panel p-5 space-y-4 relative overflow-hidden"
                style={{ borderLeft: `3px solid ${color}` }}
              >
                {/* Subtle bg glow */}
                <div className="absolute top-0 right-0 w-32 h-32 rounded-full blur-[80px] opacity-5 pointer-events-none" style={{ backgroundColor: color }} />

                {/* Header row */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center text-sm font-black"
                      style={{ backgroundColor: color + '20', color, border: `1.5px solid ${color}40` }}>
                      {c.name.split(' ').map(n => n[0]).join('')}
                    </div>
                    <div>
                      <p className="font-bold text-gray-100">{c.name}</p>
                      <p className="text-xs text-gray-500">{c.city} · {c.accountType}</p>
                    </div>
                  </div>
                  <span className={`text-[10px] font-black tracking-widest px-2.5 py-0.5 rounded border uppercase ${badgeStyles[c.severity]}`}>
                    {c.severity}
                  </span>
                </div>

                {/* EMI + Due */}
                <div className="flex items-center gap-6 text-sm">
                  <div>
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider">EMI Amount</p>
                    <p className="font-mono font-bold text-gray-100">{inr(c.emiAmount)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider">Due Date</p>
                    <p className="font-mono font-bold text-gray-100">{c.emiDueDate}th of month</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider">Days Until Due</p>
                    <p className="font-mono font-bold" style={{ color: daysUntil <= 3 ? '#ef4444' : daysUntil <= 7 ? '#f97316' : '#94a3b8' }}>
                      {daysUntil} days
                    </p>
                  </div>
                </div>

                {/* Miss probability bar */}
                <MissBar probability={c.missProbability} severity={c.severity} />

                {/* Savings bar */}
                <SavingsBar savings={c.assessedSavings} emiAmount={c.emiAmount} severity={c.severity} />

                {/* First AI suggestion */}
                <p className="text-xs text-gray-400 leading-relaxed border-l-2 pl-3 py-1" style={{ borderColor: color + '60' }}>
                  {c.suggestions[0]}
                </p>

                {/* View full report */}
                <Link
                  href={`/customer/${c.id}`}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold border px-3 py-1.5 rounded-lg transition-all"
                  style={{ color, borderColor: color + '40' }}
                >
                  <ExternalLink size={11} />
                  View Full Report
                </Link>
              </div>
            );
          })}
        </div>

        {flagged.length > limit && (
          <div className="text-center">
            <button onClick={() => setLimit(l => l + 20)}
              className="px-4 py-2 rounded-xl text-sm font-semibold border border-[#1f293d] text-gray-300 hover:border-cyan-500/40">
              Show more ({flagged.length - limit} remaining)
            </button>
          </div>
        )}

        {/* Timeline Table */}
        <div className="glass-panel overflow-hidden">
          <div className="px-6 py-4 border-b border-[#1f293d]">
            <h3 className="text-sm font-bold tracking-wider text-gray-400 uppercase">Next EMI dates — flagged customers ({flagged.length})</h3>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1f293d] text-[10px] uppercase tracking-widest text-gray-500">
                <th className="px-5 py-3 text-left">Customer</th>
                <th className="px-5 py-3 text-right">EMI Amount</th>
                <th className="px-5 py-3 text-center">Due Date</th>
                <th className="px-5 py-3 text-center">Days Until Due</th>
                <th className="px-5 py-3 text-center">Predicted Status</th>
                <th className="px-5 py-3 text-center">Action</th>
              </tr>
            </thead>
            <tbody>
              {[...flagged]
                .sort((a, b) => getDaysUntil(a.emiDueDate) - getDaysUntil(b.emiDueDate))
                .map(c => {
                  const days = getDaysUntil(c.emiDueDate);
                  const rowHighlight =
                    days <= 3 ? 'bg-rose-900/10 border-l-2 border-rose-500/50' :
                    days <= 7 ? 'bg-amber-900/10 border-l-2 border-amber-500/50' : '';
                  return (
                    <tr key={c.id} className={`border-b border-[#1f293d]/50 hover:bg-[#1a2133]/40 transition-colors ${rowHighlight}`}>
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-2">
                          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: getSeverityColor(c.severity) }} />
                          <span className="font-semibold text-gray-100">{c.name}</span>
                        </div>
                      </td>
                      <td className="px-5 py-3.5 text-right font-mono text-gray-300">{inr(c.emiAmount)}</td>
                      <td className="px-5 py-3.5 text-center text-gray-400 font-mono text-xs">
                        {c.emiDueDate}th
                      </td>
                      <td className="px-5 py-3.5 text-center">
                        <span className={`font-mono font-bold ${days <= 3 ? 'text-rose-400' : days <= 7 ? 'text-amber-400' : 'text-gray-300'}`}>
                          {days} days
                        </span>
                      </td>
                      <td className="px-5 py-3.5 text-center">
                        <span className={`text-[10px] font-black tracking-widest px-2.5 py-0.5 rounded border uppercase ${badgeStyles[c.severity]}`}>
                          {c.severity}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 text-center">
                        <Link
                          href={`/customer/${c.id}`}
                          className="text-xs font-semibold text-cyan-400 hover:text-cyan-300 transition-colors"
                        >
                          View
                        </Link>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>

      </main>
    </div>
  );
}
