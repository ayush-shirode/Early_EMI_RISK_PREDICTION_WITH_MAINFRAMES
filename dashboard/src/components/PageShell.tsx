import { Header } from '@/components/Header';

interface Props {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
}

/** Common frame for every page: global header, centred content column, optional title row. */
export function PageShell({ title, subtitle, actions, children }: Props) {
  return (
    <div className="min-h-screen bg-darkBg text-gray-100 flex flex-col">
      <Header />
      <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
        {(title || actions) && (
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="min-w-0">
              {title && <h2 className="text-2xl font-bold text-white tracking-tight">{title}</h2>}
              {subtitle && <p className="text-sm text-gray-400 mt-1">{subtitle}</p>}
            </div>
            {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
          </div>
        )}
        {children}
      </main>
    </div>
  );
}

/** Centred loading line used while a page waits for data. */
export function Loading({ text = 'Loading…' }: { text?: string }) {
  return (
    <div className="flex items-center justify-center py-24 text-xs text-gray-400 font-mono uppercase tracking-wider animate-pulse">
      {text}
    </div>
  );
}
