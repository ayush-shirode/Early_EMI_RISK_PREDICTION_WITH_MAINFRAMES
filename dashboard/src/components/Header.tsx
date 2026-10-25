'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Cpu } from 'lucide-react';
import { useCustomer } from '@/context/CustomerContext';
import { getSeverityColor } from '@/lib/customers';
import { api } from '@/lib/api';
import type { MainframeStatus } from '@/lib/types';
import { Nav } from '@/components/Nav';

function MainframeIndicator() {
  const [state, setState] = useState<{ ok: boolean; label: string; title: string } | null>(null);

  useEffect(() => {
    let stop = false;
    const load = async () => {
      try {
        const s = await api.get<MainframeStatus>('/mainframe/status');
        if (stop) return;
        const mf = s.mainframe;
        if (s.active_run) setState({ ok: true, label: `RUN #${s.active_run} ACTIVE`, title: 'A mainframe action is running' });
        else if (mf?.ok) setState({ ok: true, label: `z/OS ${mf.connection?.user}`, title: `Connected to ${mf.connection?.system}` });
        else setState({ ok: false, label: 'MAINFRAME OFFLINE', title: mf?.error ?? 'Not connected' });
      } catch (e: any) {
        if (!stop) setState({ ok: false, label: 'BACKEND OFFLINE', title: e.message });
      }
    };
    load();
    const id = setInterval(load, 30000);
    return () => { stop = true; clearInterval(id); };
  }, []);

  if (!state) return null;
  return (
    <Link href="/mainframe" title={state.title}
      className="flex items-center gap-2 bg-[#131926] border border-[#1f293d] px-3 py-1.5 rounded-lg hover:border-cyan-500/30">
      <span className="relative flex h-2.5 w-2.5">
        {state.ok && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />}
        <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${state.ok ? 'bg-emerald-500' : 'bg-rose-500'}`} />
      </span>
      <span className="text-xs text-gray-300 font-mono font-semibold uppercase tracking-wider">{state.label}</span>
    </Link>
  );
}

export function Header() {
  const { selectedCustomer, setSelectedCustomer, allCustomers } = useCustomer();

  return (
    <header className="border-b border-[#1f293d] bg-[#0c101b]/85 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 pt-3 flex flex-wrap items-center justify-between gap-3">
        <Link href="/" className="flex items-center gap-3 shrink-0">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 to-cyan-400 text-white shadow-[0_0_15px_rgba(59,130,246,0.5)]">
            <Cpu size={22} />
          </div>
          <div>
            <h1 className="text-xl font-extrabold tracking-tight text-white leading-none">
              VIGILANCE <span className="bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">AI</span>
            </h1>
            <p className="text-[11px] text-gray-400 tracking-wider font-semibold uppercase mt-1">Early Warning Credit Risk · z/OS + ML</p>
          </div>
        </Link>

        <div className="flex flex-wrap items-center gap-3">
          {selectedCustomer && (
            <label className="flex items-center gap-2">
              <span className="hidden md:inline text-xs text-gray-400 uppercase font-semibold">Profile</span>
              <span className="relative">
                <select
                  value={selectedCustomer.id}
                  onChange={(e) => {
                    const found = allCustomers.find(c => c.id === e.target.value);
                    if (found) setSelectedCustomer(found);
                  }}
                  className="bg-[#131926] border border-[#1f293d] rounded-lg pl-8 pr-3 py-1.5 text-sm font-semibold text-gray-200 focus:outline-none focus:border-cyan-500 cursor-pointer appearance-none w-[240px] truncate"
                >
                  {allCustomers.map(c => (
                    <option key={c.id} value={c.id}>{c.id} · {c.name} · {c.riskScore}%</option>
                  ))}
                </select>
                <span className="absolute left-2.5 top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full pointer-events-none"
                  style={{ backgroundColor: getSeverityColor(selectedCustomer.severity) }} />
              </span>
            </label>
          )}
          <MainframeIndicator />
        </div>
      </div>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-2">
        <Nav />
      </div>
    </header>
  );
}
