/** Typed client for the FastAPI backend (proxied by Next.js at /api/backend). */
const BASE = '/api/backend';

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { cache: 'no-store', ...init });
  } catch {
    throw new ApiError('Backend not reachable. Start it with `make dev`.', 0);
  }
  const text = await res.text();
  if (!res.ok) {
    let msg = text;
    try { msg = JSON.parse(text).detail ?? text; } catch { /* plain text */ }
    if (res.status >= 500 && !msg) msg = 'Backend not reachable. Start it with `make dev`.';
    throw new ApiError(typeof msg === 'string' ? msg : JSON.stringify(msg), res.status);
  }
  const type = res.headers.get('content-type') ?? '';
  return (type.includes('application/json') ? JSON.parse(text) : text) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown = {}) =>
    request<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
};

export function startAction(name: string, params: Record<string, unknown> = {}) {
  return api.post<{ runId: number }>(`/actions/${name}`, params);
}

export const ACTION_LABELS: Record<string, string> = {
  test_connection: 'Test connection',
  setup: 'Set up mainframe',
  compile: 'Recompile COBOL',
  upload_sources: 'Upload JCL / DFSORT / REXX',
  generate_data: 'Generate & upload data',
  train_model: 'Train model',
  run_batch: 'Run batch & score',
  reset_data: 'Reset mainframe data',
};

export const inr = (v: number) => `₹${Math.round(v).toLocaleString('en-IN')}`;

export function fmtAsOf(asof: number | string | undefined) {
  if (!asof) return '—';
  const s = String(asof);
  return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
}

export function fmtTime(iso: string | null | undefined) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function duration(a: string | null, b: string | null) {
  if (!a) return '';
  const s = Math.max(0, Math.round(((b ? new Date(b) : new Date()).getTime() - new Date(a).getTime()) / 1000));
  return s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`;
}

/** Month-end as-of dates inside the data history window (the backend validates the same range). */
export const ASOF_OPTIONS: number[] = (() => {
  const out: number[] = [];
  let y = 2026, m = 9;
  while (y > 2025 || m >= 3) {
    out.push(y * 10000 + m * 100 + new Date(y, m, 0).getDate());
    if (m === 1) { y -= 1; m = 12; } else { m -= 1; }
  }
  return out;
})();
