'use client';
import { useMemo, useState } from 'react';
import Link from 'next/link';
import { PageShell, Loading } from '@/components/PageShell';
import { EmptyState } from '@/components/EmptyState';
import { useCustomer } from '@/context/CustomerContext';
import { getSeverityColor, SEVERITY_BADGE } from '@/lib/customers';
import { fmtAsOf, inr } from '@/lib/api';
import type { Customer } from '@/lib/types';
import { ExternalLink, ChevronUp, ChevronDown, Search } from 'lucide-react';

type SortKey = 'name' | 'riskScore' | 'creditScore' | 'emiAmount';
const PAGE = 50;

function RiskBar({ score, severity }: { score: number; severity: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-2 bg-[#1f293d] rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${score}%`, backgroundColor: getSeverityColor(severity) }} />
      </div>
      <span className="text-xs font-mono text-gray-300">{score}%</span>
    </div>
  );
}

export default function CustomersPage() {
  const { allCustomers, setSelectedCustomer, loading, error } = useCustomer();
  const [sortKey, setSortKey] = useState<SortKey>('riskScore');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [tier, setTier] = useState<'all' | 'high' | 'medium' | 'low'>('all');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    return allCustomers
      .filter(c => tier === 'all' || c.severity === tier)
      .filter(c => !term || c.id.toLowerCase().includes(term) || c.name.toLowerCase().includes(term) || c.city.toLowerCase().includes(term))
      .sort((a, b) => {
        const va = a[sortKey], vb = b[sortKey];
        const cmp = typeof va === 'number' && typeof vb === 'number' ? va - vb : String(va).localeCompare(String(vb));
        return sortDir === 'asc' ? cmp : -cmp;
      });
  }, [allCustomers, tier, q, sortKey, sortDir]);

  if (!loading && allCustomers.length === 0) return <PageShell><EmptyState error={error} /></PageShell>;

  const rows = filtered.slice(page * PAGE, page * PAGE + PAGE);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE));
  const count = (t: string) => allCustomers.filter(c => c.severity === t).length;
  const avgRisk = allCustomers.length ? (allCustomers.reduce((a, c) => a + c.riskScore, 0) / allCustomers.length).toFixed(1) : '—';
  const emiAtRisk = allCustomers.filter(c => c.severity !== 'low').reduce((a, c) => a + c.emiAmount, 0);

  const sort = (k: SortKey) => {
    if (sortKey === k) setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(k); setSortDir('desc'); }
  };
  const SortIcon = ({ k }: { k: SortKey }) => sortKey === k ? (sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />) : null;

  return (
    <PageShell title="Customer registry"
      subtitle={`Every borrower scored by the latest mainframe batch${allCustomers[0] ? ` (run #${allCustomers[0].runId}, as-of ${fmtAsOf(allCustomers[0].asOf)})` : ''}`}>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Scored customers', value: allCustomers.length.toLocaleString('en-IN'), cls: 'text-cyan-400' },
            { label: 'High / Medium risk', value: `${count('high')} / ${count('medium')}`, cls: 'text-orange-400' },
            { label: 'Avg stress probability', value: `${avgRisk}%`, cls: 'text-yellow-400' },
            { label: 'Monthly EMI at risk', value: inr(emiAtRisk), cls: 'text-rose-400' },
          ].map(({ label, value, cls }) => (
            <div key={label} className="glass-panel p-5">
              <p className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">{label}</p>
              <p className={`text-2xl font-black font-mono mt-1 ${cls}`}>{value}</p>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-2.5 text-gray-500" />
            <input value={q} onChange={e => { setQ(e.target.value); setPage(0); }} placeholder="Search ID, name, city"
              className="bg-[#0c101b] border border-[#1f293d] rounded-xl pl-8 pr-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500 w-64" />
          </div>
          {(['all', 'high', 'medium', 'low'] as const).map(t => (
            <button key={t} onClick={() => { setTier(t); setPage(0); }}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider border ${tier === t ? 'border-cyan-500/40 text-cyan-300 bg-cyan-500/10' : 'border-[#1f293d] text-gray-400'}`}>
              {t}{t !== 'all' ? ` (${count(t)})` : ''}
            </button>
          ))}
          <span className="text-xs text-gray-500 ml-auto">{filtered.length} shown</span>
        </div>

        <div className="glass-panel overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm whitespace-nowrap">
              <thead>
                <tr className="border-b border-[#1f293d] text-[10px] uppercase tracking-widest text-gray-500">
                  <th className="px-5 py-3.5 text-left cursor-pointer" onClick={() => sort('name')}><span className="flex items-center gap-1">Customer <SortIcon k="name" /></span></th>
                  <th className="px-5 py-3.5 text-left">City</th>
                  <th className="px-5 py-3.5 text-left">Loans</th>
                  <th className="px-5 py-3.5 text-right cursor-pointer" onClick={() => sort('emiAmount')}><span className="flex items-center justify-end gap-1">EMI <SortIcon k="emiAmount" /></span></th>
                  <th className="px-5 py-3.5 text-right cursor-pointer" onClick={() => sort('creditScore')}><span className="flex items-center justify-end gap-1">Credit <SortIcon k="creditScore" /></span></th>
                  <th className="px-5 py-3.5 text-left cursor-pointer" onClick={() => sort('riskScore')}><span className="flex items-center gap-1">Stress prob. <SortIcon k="riskScore" /></span></th>
                  <th className="px-5 py-3.5 text-center">Tier</th>
                  <th className="px-5 py-3.5 text-left">Top factor</th>
                  <th className="px-5 py-3.5 text-center"></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c: Customer) => (
                  <tr key={c.id} onClick={() => setSelectedCustomer(c)} className="border-b border-[#1f293d]/50 hover:bg-[#1a2133]/50 cursor-pointer">
                    <td className="px-5 py-3">
                      <p className="font-semibold text-gray-100">{c.name}</p>
                      <p className="text-xs text-gray-500 font-mono">{c.id} · {c.accountType}</p>
                    </td>
                    <td className="px-5 py-3 text-gray-400">{c.city}</td>
                    <td className="px-5 py-3"><span className="text-xs font-semibold bg-[#1f293d] px-2.5 py-1 rounded capitalize">{c.activeLoans} · {c.loanType}</span></td>
                    <td className="px-5 py-3 text-right font-mono text-gray-200">{inr(c.emiAmount)}</td>
                    <td className={`px-5 py-3 text-right font-mono font-bold ${c.creditScore >= 700 ? 'text-emerald-400' : 'text-yellow-400'}`}>{c.creditScore}</td>
                    <td className="px-5 py-3"><RiskBar score={c.riskScore} severity={c.severity} /></td>
                    <td className="px-5 py-3 text-center">
                      <span className={`text-[10px] font-black tracking-widest px-2.5 py-0.5 rounded border uppercase ${SEVERITY_BADGE[c.severity]}`}>{c.severity}</span>
                    </td>
                    <td className="px-5 py-3 text-xs text-gray-400">{c.topFactor}</td>
                    <td className="px-5 py-3 text-center">
                      <Link href={`/customer/${c.id}`} onClick={e => { e.stopPropagation(); setSelectedCustomer(c); }}
                        className="inline-flex items-center gap-1.5 text-xs font-semibold text-cyan-400 border border-cyan-500/30 px-3 py-1.5 rounded-lg">
                        <ExternalLink size={11} /> Details
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between px-5 py-3 border-t border-[#1f293d] text-xs text-gray-400">
            <span>Page {page + 1} of {pages}</span>
            <div className="flex gap-2">
              <button disabled={page === 0} onClick={() => setPage(p => p - 1)} className="px-3 py-1 rounded border border-[#1f293d] disabled:opacity-40">Previous</button>
              <button disabled={page + 1 >= pages} onClick={() => setPage(p => p + 1)} className="px-3 py-1 rounded border border-[#1f293d] disabled:opacity-40">Next</button>
            </div>
          </div>
        </div>
      </PageShell>
  );
}
