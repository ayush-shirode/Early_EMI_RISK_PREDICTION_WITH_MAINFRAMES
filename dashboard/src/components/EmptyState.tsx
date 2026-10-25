'use client';
import Link from 'next/link';
import { Server } from 'lucide-react';

export function EmptyState({ error }: { error?: string | null }) {
  return (
    <div className="glass-panel p-10 flex flex-col items-center text-center gap-4 max-w-2xl mx-auto mt-10">
      <div className="p-4 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
        <Server size={28} />
      </div>
      <h2 className="text-xl font-bold text-white">No scored customers yet</h2>
      <p className="text-sm text-gray-400 leading-relaxed">
        {error
          ? <>The backend returned: <span className="font-mono text-rose-300">{error}</span></>
          : <>Risk scores are produced by the mainframe batch and the ML model. Open the Mainframe Control
             Center and follow the setup steps: set up the mainframe, generate data, train the model, run the batch.</>}
      </p>
      <Link href="/mainframe"
        className="bg-gradient-to-r from-blue-600 to-cyan-500 text-white font-bold px-5 py-2.5 rounded-xl text-sm shadow-[0_0_15px_rgba(59,130,246,0.3)]">
        Open Mainframe Control Center
      </Link>
    </div>
  );
}
