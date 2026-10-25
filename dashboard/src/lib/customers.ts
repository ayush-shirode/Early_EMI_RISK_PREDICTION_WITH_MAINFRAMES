export type { Customer } from './types';

export const SEVERITY_COLORS: Record<string, string> = {
  low: '#22c55e',
  medium: '#eab308',
  high: '#f97316',
};

export function getSeverityColor(severity: string): string {
  return SEVERITY_COLORS[severity] ?? '#22c55e';
}

export const SEVERITY_BADGE: Record<string, string> = {
  high: 'bg-orange-500/10 text-orange-400 border-orange-500/30',
  medium: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30',
  low: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
};
