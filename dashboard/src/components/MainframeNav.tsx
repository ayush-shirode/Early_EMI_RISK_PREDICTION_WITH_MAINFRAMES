'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const TABS = [
  { href: '/mainframe', label: 'Overview' },
  { href: '/mainframe/runs', label: 'Batch runs' },
  { href: '/mainframe/datasets', label: 'Data sets' },
  { href: '/mainframe/reports', label: 'Reports' },
  { href: '/mainframe/model', label: 'Model' },
];

export function MainframeNav() {
  const path = usePathname();
  return (
    <div className="flex flex-wrap gap-2 border-b border-[#1f293d] pb-3">
      {TABS.map(t => {
        const active = t.href === '/mainframe' ? path === t.href : path.startsWith(t.href);
        return (
          <Link key={t.href} href={t.href}
            className={`px-3.5 py-1.5 rounded-lg text-sm font-semibold transition-all ${active
              ? 'bg-[#1a2640] text-cyan-400 border border-cyan-500/30'
              : 'text-gray-400 hover:text-gray-200 hover:bg-[#131926]'}`}>
            {t.label}
          </Link>
        );
      })}
    </div>
  );
}
