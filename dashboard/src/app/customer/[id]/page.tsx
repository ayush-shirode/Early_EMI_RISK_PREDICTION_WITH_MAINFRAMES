'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { PageShell, Loading } from '@/components/PageShell';
import { RiskGauge } from '@/components/RiskGauge';
import { SpendTrendChart } from '@/components/SpendTrendChart';
import { SuggestionCards } from '@/components/SuggestionCards';
import { useCustomer } from '@/context/CustomerContext';
import { getSeverityColor } from '@/lib/customers';
import { api, fmtAsOf, inr } from '@/lib/api';
import type { CustomerDetail } from '@/lib/types';
import { FileText, MapPin, Briefcase, Calendar, DollarSign, User, Hash, Brain } from 'lucide-react';
import { ResponsiveContainer, ComposedChart, Area, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts';

const LOAN_TYPES: Record<string, string> = { H: 'Home', C: 'Car', P: 'Personal', E: 'Education' };
const fmtDate = (n: number) => `${String(n).slice(0, 4)}-${String(n).slice(4, 6)}-${String(n).slice(6, 8)}`;

function InfoRow({ label, value, icon: Icon }: { label: string; value: string; icon?: React.FC<any> }) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-[#1f293d]/50 last:border-none">
      {Icon && <Icon size={14} className="text-gray-500 mt-0.5 shrink-0" />}
      <div className="min-w-0">
        <p className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</p>
        <p className="text-sm text-gray-100 font-medium truncate">{value}</p>
      </div>
    </div>
  );
}

function CreditRing({ score }: { score: number }) {
  const norm = (Math.min(Math.max(score, 300), 900) - 300) / 600;
  const color = norm > 0.7 ? '#22c55e' : norm > 0.45 ? '#eab308' : '#ef4444';
  const circumference = Math.PI * 60;
  return (
    <div className="flex flex-col items-center gap-2">
      <svg width="150" height="85" viewBox="0 0 150 85">
        <path d="M 15 75 A 60 60 0 0 1 135 75" fill="none" stroke="#1b2438" strokeWidth="10" strokeLinecap="round" />
        <path d="M 15 75 A 60 60 0 0 1 135 75" fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"
          strokeDasharray={`${norm * circumference} ${circumference}`} />
        <text x="75" y="72" textAnchor="middle" fontSize="28" fontWeight="900" fill={color}>{score}</text>
        <text x="75" y="83" textAnchor="middle" fontSize="8" fontWeight="700" fill="#94a3b8">CREDIT SCORE</text>
      </svg>
      <span className="text-xs font-semibold" style={{ color }}>{score >= 750 ? 'Excellent' : score >= 650 ? 'Good' : 'Fair'}</span>
    </div>
  );
}

export default function CustomerDetailPage({ params }: { params: { id: string } }) {
  const { allCustomers, setSelectedCustomer } = useCustomer();
  const [c, setC] = useState<CustomerDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<CustomerDetail>(`/customers/${params.id}`).then(setC).catch(e => setError(e.message));
    const listed = allCustomers.find(x => x.id === params.id);
    if (listed) setSelectedCustomer(listed);
  }, [params.id, allCustomers, setSelectedCustomer]);

  if (error) return <PageShell><p className="p-10 text-center text-rose-400">{error}</p></PageShell>;
  if (!c) return <PageShell><Loading /></PageShell>;

  const color = getSeverityColor(c.severity);
  const coverage = Math.min(100, (c.assessedSavings / c.emiAmount) * 100);
  const history = c.monthly.map(m => ({
    month: `${String(m.yyyymm).slice(4)}/${String(m.yyyymm).slice(2, 4)}`,
    'Avg balance': Math.round(m.avg_bal), Debits: Math.round(m.debits), Salary: Math.round(m.salary),
  }));

  const printReport = () => {
    const w = window.open('', '_blank');
    if (!w) return;
    w.document.write(`<html><head><title>Risk report ${c.id}</title><style>
      body{font-family:Georgia,serif;color:#111;padding:40px;max-width:800px;margin:auto}
      table{width:100%;border-collapse:collapse;margin:16px 0}th{background:#f3f4f6;text-align:left;padding:8px 12px;font-size:11px;text-transform:uppercase}
      td{padding:8px 12px;font-size:13px;border-bottom:1px solid #e5e7eb}.s{padding:10px;border-left:3px solid #1d4ed8;margin:8px 0;background:#eff6ff;font-size:13px}
      </style></head><body>
      <p style="color:#1d4ed8;font-weight:900">VIGILANCE AI — EARLY WARNING CREDIT RISK SYSTEM</p>
      <h1>${c.name} (${c.id})</h1><p>As-of ${fmtAsOf(c.asOf)} · batch run #${c.runId} · model ${c.modelVersion}</p>
      <table><tr><th colspan="2">Risk</th></tr><tr><td>Stress probability (90 days)</td><td>${c.riskScore}%</td></tr>
      <tr><td>Tier</td><td>${c.tier}</td></tr><tr><td>Why</td><td>${c.reasoning}</td></tr><tr><td>Action</td><td>${c.action}</td></tr></table>
      <table><tr><th>Loan</th><th>Type</th><th>EMI</th><th>Tenure</th><th>Start</th><th>Status</th></tr>
      ${c.loans.map(l => `<tr><td>${l.loan_id}</td><td>${LOAN_TYPES[l.loan_type]}</td><td>${inr(l.emi_amt)}</td><td>${l.tenure} m</td><td>${fmtDate(l.start_date)}</td><td>${l.status}</td></tr>`).join('')}</table>
      <h3>Suggested actions</h3>${c.suggestions.map(s => `<div class="s">${s}</div>`).join('')}</body></html>`);
    w.document.close();
    w.focus();
    setTimeout(() => w.print(), 400);
  };

  return (
    <PageShell>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-xl font-black"
              style={{ backgroundColor: color + '20', border: `2px solid ${color}40`, color }}>
              {c.name.split(' ').map(n => n[0]).join('')}
            </div>
            <div>
              <h2 className="text-2xl font-bold text-white">{c.name}</h2>
              <p className="text-sm text-gray-400">{c.id} · {c.city} · {c.accountType} · scored as-of {fmtAsOf(c.asOf)} (run #{c.runId})</p>
            </div>
          </div>
          <div className="flex gap-2">
            <Link href={`/prediction?customerId=${c.id}`}
              className="flex items-center gap-2 border border-cyan-500/30 text-cyan-300 font-bold px-4 py-2.5 rounded-xl text-sm">
              <Brain size={15} /> SHAP analysis
            </Link>
            <button onClick={printReport}
              className="flex items-center gap-2 bg-gradient-to-r from-blue-600 to-cyan-500 text-white font-bold px-5 py-2.5 rounded-xl text-sm">
              <FileText size={15} /> Generate report
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="space-y-4">
            <div className="glass-panel p-5">
              <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-3">Profile (EWS.CUSTMAST)</h3>
              <InfoRow label="Customer ID" value={c.id} icon={Hash} />
              <InfoRow label="Age" value={`${c.age} years`} icon={User} />
              <InfoRow label="City" value={c.city} icon={MapPin} />
              <InfoRow label="Employment" value={c.accountType} icon={Briefcase} />
              <InfoRow label="Monthly income" value={inr(c.monthlyIncome)} icon={DollarSign} />
            </div>
            <div className="glass-panel p-5">
              <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-3">Loans (EWS.LOANMAST)</h3>
              <div className="space-y-2">
                {c.loans.map(l => (
                  <div key={l.loan_id} className="p-3 rounded-xl bg-[#141a27] border border-[#1f293d] text-xs">
                    <div className="flex justify-between font-mono"><span className="text-gray-200">{l.loan_id}</span><span className="text-gray-500">{l.status === 'A' ? 'active' : l.status === 'C' ? 'closed' : 'defaulted'}</span></div>
                    <p className="text-gray-400 mt-1">{LOAN_TYPES[l.loan_type]} · {inr(l.principal)} at {l.int_rate}% · {l.tenure} m from {fmtDate(l.start_date)}</p>
                    <p className="text-gray-300 mt-0.5">EMI {inr(l.emi_amt)} on day {l.due_day}</p>
                  </div>
                ))}
              </div>
            </div>
            <div className="glass-panel p-5 flex flex-col items-center">
              <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-4 self-start">Credit health</h3>
              <CreditRing score={c.creditScore} />
            </div>
          </div>

          <div className="space-y-4">
            <RiskGauge score={c.riskScore} severity={c.severity} />
            <div className="glass-panel p-5 space-y-3">
              <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest">Stress probability (next 90 days)</h3>
              <p className="text-5xl font-black font-mono text-center" style={{ color }}>{c.riskScore}%</p>
              <p className="text-xs text-gray-400 leading-relaxed">{c.reasoning}</p>
            </div>
            <div className="glass-panel p-5 space-y-3">
              <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest">Balance vs monthly EMI</h3>
              <div className="flex justify-between text-xs text-gray-400"><span>{inr(c.assessedSavings)} avg balance</span><span>{inr(c.emiAmount)} EMI</span></div>
              <div className="h-3 bg-[#1f293d] rounded-full overflow-hidden">
                <div className="h-full rounded-full" style={{ width: `${coverage}%`, backgroundColor: color }} />
              </div>
              <p className="text-xs text-gray-500 text-right">{(c.assessedSavings / c.emiAmount).toFixed(1)}× the EMI</p>
            </div>
            <div className="glass-panel p-5 text-center">
              <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-3">Repayment</h3>
              <p className="text-sm text-gray-300"><Calendar size={13} className="inline mr-1" />EMI due on day {c.emiDueDate} · {c.monthsRemaining} months left on the largest loan</p>
            </div>
          </div>

          <div className="space-y-4">
            <SpendTrendChart data={c.spendTrend} emiAmount={c.emiAmount} />
            <SuggestionCards suggestions={c.suggestions} severity={c.severity} />
          </div>
        </div>

        <div className="glass-panel p-6">
          <h3 className="text-sm font-bold tracking-wider text-gray-400 uppercase mb-1">24-month account history (EWS.TXNSUMM)</h3>
          <p className="text-xs text-gray-500 mb-4">Monthly summaries as stored on the mainframe; the model only sees the months up to the as-of date.</p>
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={history} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f293d" vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={v => `₹${(v / 1000).toFixed(0)}k`} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ backgroundColor: '#131926', borderColor: '#1f293d', borderRadius: '12px' }}
                  formatter={(v: number, n: string) => [inr(v), n]} />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                <Area type="monotone" dataKey="Avg balance" stroke="#22d3ee" fill="#22d3ee22" />
                <Line type="monotone" dataKey="Debits" stroke="#f97316" dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="Salary" stroke="#22c55e" dot={false} strokeWidth={2} strokeDasharray="4 3" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      </PageShell>
  );
}
