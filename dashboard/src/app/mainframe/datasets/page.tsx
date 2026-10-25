'use client';
import { useEffect, useState } from 'react';
import { Loader2, Database } from 'lucide-react';
import { api } from '@/lib/api';

interface DS { dsname: string; dsorg: string; recfm: string; lrecl: string; blksz: string; used: string; sizex: string; spacu: string; cdate: string; rdate: string; vol: string }

const PURPOSE: Record<string, string> = {
  JCL: 'JCL members (EWSBATCH, EWSCOMP, EWSRPTJ)', CPY: 'COBOL copybooks (record layouts)',
  CNTL: 'DFSORT / ICETOOL control statements', REXX: 'REXX execs (EWSRECON)',
  CUSTMAST: 'Input: customer master', LOANMAST: 'Input: loan master', REPAYHST: 'Input: EMI installment history',
  TXNSUMM: 'Input: monthly account summaries', 'CUST.SRT': 'Sorted, de-duplicated customers', 'CUST.DUPS': 'Duplicate customer IDs dropped by ICETOOL',
  'LOAN.SRT': 'Sorted loans', 'REPAY.SRT': 'Sorted, numeric-checked repayments', 'TXN.SRT': 'Sorted, numeric-checked summaries',
  'CUST.VALID': 'Customers that passed EWSVCUST', 'LOAN.VALID': 'Loans that passed EWSVLOAN', REJECTS: 'Rejected records with reason codes',
  EXCEPT: 'Matching exceptions from EWSMATCH', FEATURES: 'Fixed-width ML features (FEATREC)', FEATCSV: 'Features as CSV (downloaded)',
  CTLTOT: 'Control totals written by the COBOL programs', RUNCTL: 'REXX reconciliation result', SCORES: 'Model scores written back from Python',
  'SCORES.SRT': 'Scores sorted by risk', RISKRPT: 'Early intervention report printed by EWSRPT',
};

export default function DatasetsPage() {
  const [items, setItems] = useState<DS[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ lines?: string[]; members?: string[] } | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { api.get<DS[]>('/datasets').then(setItems).catch(e => setError(e.message)); }, []);

  const open = async (dsn: string) => {
    setSel(dsn);
    setPreview(null);
    setLoading(true);
    try { setPreview(await api.get(`/datasets/${encodeURIComponent(dsn)}/preview?records=60`)); }
    catch (e: any) { setPreview({ lines: [e.message] }); }
    finally { setLoading(false); }
  };

  if (error) return <p className="text-sm text-rose-400">{error}</p>;
  if (!items) return <div className="flex items-center gap-2 text-sm text-gray-400"><Loader2 className="animate-spin" size={16} /> Listing data sets on z/OS…</div>;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
      <div className="xl:col-span-3 glass-panel overflow-x-auto">
        <table className="w-full text-xs whitespace-nowrap">
          <thead>
            <tr className="border-b border-[#1f293d] text-[10px] uppercase tracking-widest text-gray-500">
              <th className="px-4 py-3 text-left">Data set</th><th className="px-2 py-3">Org</th><th className="px-2 py-3">RECFM</th>
              <th className="px-2 py-3">LRECL</th><th className="px-2 py-3">Used</th><th className="px-4 py-3 text-left">Purpose</th>
            </tr>
          </thead>
          <tbody>
            {items.map(d => {
              const short = d.dsname.split('.EWS.')[1] ?? d.dsname;
              return (
                <tr key={d.dsname} onClick={() => open(d.dsname)}
                  className={`border-b border-[#1f293d]/50 cursor-pointer ${sel === d.dsname ? 'bg-[#1a2640]' : 'hover:bg-[#1a2133]/40'}`}>
                  <td className="px-4 py-2.5 font-mono text-cyan-300">{d.dsname}</td>
                  <td className="px-2 py-2.5 text-center font-mono text-gray-400">{d.dsorg}</td>
                  <td className="px-2 py-2.5 text-center font-mono text-gray-400">{d.recfm}</td>
                  <td className="px-2 py-2.5 text-center font-mono text-gray-400">{d.lrecl}</td>
                  <td className="px-2 py-2.5 text-center font-mono text-gray-400">{d.used ? `${d.used}%` : '—'}</td>
                  <td className="px-4 py-2.5 text-gray-400">{PURPOSE[short] ?? ''}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="xl:col-span-2 glass-panel p-0 overflow-hidden">
        <div className="px-4 py-3 border-b border-[#1f293d] flex items-center gap-2 text-sm text-gray-300">
          <Database size={14} className="text-cyan-400" /> {sel ?? 'Select a data set'}
        </div>
        {loading && <p className="p-4 text-sm text-gray-400">Reading from z/OS…</p>}
        {preview?.members && (
          <div className="p-3 flex flex-wrap gap-2">
            {preview.members.map(m => (
              <button key={m} onClick={() => open(`${sel!.replace(/\(.*\)$/, '')}(${m})`)}
                className="text-xs font-mono px-2.5 py-1 rounded border border-[#1f293d] text-cyan-300 hover:border-cyan-500/40">{m}</button>
            ))}
          </div>
        )}
        {preview?.lines && (
          <pre className="p-4 text-[11px] leading-[1.35] font-mono text-gray-200 overflow-auto max-h-[70vh] whitespace-pre">{preview.lines.join('\n')}</pre>
        )}
      </div>
    </div>
  );
}
