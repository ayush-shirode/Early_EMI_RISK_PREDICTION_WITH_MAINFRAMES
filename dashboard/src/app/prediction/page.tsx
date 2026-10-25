'use client';

import { useState, useEffect, useMemo, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { Printer, BarChart3, Zap } from 'lucide-react';

import { useCustomer } from '@/context/CustomerContext';
import { toShapResult, ShapResult } from '@/lib/shap';
import { api, fmtAsOf, inr } from '@/lib/api';
import type { Explanation, ModelMetrics, Prediction } from '@/lib/types';
import { EmptyState } from '@/components/EmptyState';
import { PageShell, Loading } from '@/components/PageShell';
import { AlertTimeline } from '@/components/AlertTimeline';
import { ShapWaterfallChart } from '@/components/ShapWaterfallChart';
import { FeatureDetailTable } from '@/components/FeatureDetailTable';
import { ModelMetaCard } from '@/components/ModelMetaCard';
import { AiReasoningCard } from '@/components/AiReasoningCard';

import styles from './prediction.module.css';

/* ---------- severity helpers ---------- */
const SEV_TEXT: Record<string, string> = { high: '#fb923c', medium: '#fbbf24', low: '#34d399' };
const SEV_BG: Record<string, string> = { high: 'rgba(124,45,18,0.3)', medium: 'rgba(113,63,18,0.3)', low: 'rgba(20,83,45,0.3)' };

function getMissProbColor(p: number) {
  if (p >= 0.6) return '#fb923c';
  if (p >= 0.3) return '#fbbf24';
  return '#34d399';
}

/* ---------- inner page content (uses hooks that need Suspense) ---------- */
function PredictionContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { selectedCustomer, setSelectedCustomer, allCustomers } = useCustomer();

  // resolve customer from query param, fallback to context
  const paramId = searchParams.get('customerId');
  const customer = useMemo(() => {
    if (paramId) return allCustomers.find(c => c.id === paramId) ?? selectedCustomer;
    return selectedCustomer;
  }, [paramId, selectedCustomer, allCustomers]);

  const [shap, setShap] = useState<ShapResult | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [metrics, setMetrics] = useState<ModelMetrics | null>(null);
  const [history, setHistory] = useState<Prediction[]>([]);
  const [activeFeature, setActiveFeature] = useState<string | null>(null);

  useEffect(() => { api.get<ModelMetrics>('/model').then(setMetrics).catch(() => setMetrics(null)); }, []);
  useEffect(() => {
    if (!customer) return;
    setShap(null);
    api.get<Explanation>(`/customers/${customer.id}/explanation?top=12`).then(e => {
      setExplanation(e);
      const r = toShapResult(e);
      if (Math.abs(r.otherFeatures) >= 0.05) {
        r.features.push({ featureName: `Other ${e.featureCount - e.features.length} features`, featureKey: '_other',
          rawValue: '—', shapValue: r.otherFeatures, direction: r.otherFeatures > 0 ? 'increase' : 'decrease',
          impact: 'low', explanation: 'Combined contribution of the remaining features.' });
      }
      setShap(r);
    }).catch(() => setShap(null));
    api.get<any[]>(`/customers/${customer.id}/history`).then(rows => setHistory(rows.map(r => ({
      prediction_id: `run #${r.run_id}`, severity: r.tier.toLowerCase(), miss_probability: r.probability,
      reasoning: r.reasoning, created_at: r.created_at, emi_amount: Math.round(r.total_emi),
      emi_due_date: `as-of ${fmtAsOf(r.as_of)}`,
    })))).catch(() => setHistory([]));
  }, [customer]);

  if (!customer) return <PageShell><EmptyState /></PageShell>;
  if (!shap || !explanation) return <PageShell><Loading text="Loading SHAP explanation…" /></PageShell>;

  // savings coverage
  const savingsCoverage = Math.min(100, Math.round((customer.assessedSavings / customer.emiAmount) * 100));
  const savingsColor = savingsCoverage >= 100 ? '#34d399' : savingsCoverage >= 60 ? '#fbbf24' : '#f87171';

  const missPercent = Math.round(customer.missProbability * 100);
  const missColor = getMissProbColor(customer.missProbability);
  const sevColor = SEV_TEXT[customer.severity] ?? '#34d399';
  const sevBg = SEV_BG[customer.severity] ?? 'rgba(20,83,45,0.3)';
  const previous = history[1];
  const prevScore = previous ? Math.round(previous.miss_probability * 100) : null;

  const handleCustomerChange = (id: string) => {
    const found = allCustomers.find(c => c.id === id);
    if (found) {
      setSelectedCustomer(found);
      router.replace(`/prediction?customerId=${id}`);
    }
  };

  const predMeta = new Date(customer.lastPredictionAt).toLocaleString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });

  return (
    <PageShell
      title={<>Risk explanation <span className="text-gray-500 font-semibold text-lg">{customer.name} · {customer.id}</span></>}
      subtitle={`Scored ${predMeta} · batch run #${customer.runId} · as-of ${fmtAsOf(customer.asOf)} · model ${shap.modelVersion}`}
      actions={<>
        <select value={customer.id} onChange={e => handleCustomerChange(e.target.value)}
          className="no-print bg-[#131926] border border-[#1f293d] rounded-lg px-3 py-2 text-sm font-semibold text-gray-200 focus:outline-none focus:border-cyan-500 max-w-[260px]">
          {allCustomers.map(c => (
            <option key={c.id} value={c.id}>{c.id} · {c.name} · {c.riskScore}%</option>
          ))}
        </select>
        <button onClick={() => window.print()}
          className="no-print flex items-center gap-2 bg-[#131926] border border-[#1f293d] hover:border-cyan-500/30 text-gray-200 px-4 py-2 rounded-xl text-sm font-semibold">
          <Printer size={14} /> Download PDF
        </button>
      </>}>
    <div id="printable" className={styles.page}>
      <main className={styles.main}>

        {/* ===== ZONE 2: STAT CARDS ===== */}
        <div className={styles.statRow}>

          {/* Card 1 — Miss Probability */}
          <div className={styles.statCard}>
            <span className={styles.statLabel}>Stress probability</span>
            <span className={styles.statValue} style={{ color: missColor }}>
              {missPercent}%
            </span>
            <span className={styles.statSub}>
              Missed/bounced EMI or 30+ days late within 90 days
            </span>
          </div>

          {/* Card 2 — Risk Score */}
          <div className={styles.statCard}>
            <span className={styles.statLabel}>Risk tier</span>
            <span className={styles.statValue} style={{ color: sevColor }}>
              {shap.finalScore}
              <span style={{ fontSize: '14px', color: 'var(--text-muted)', fontWeight: 400 }}>/100</span>
            </span>
            <span className={styles.statSub} style={{
              display: 'inline-flex', alignItems: 'center', gap: '6px',
              background: sevBg, color: sevColor,
              padding: '2px 8px', borderRadius: '6px', fontWeight: 700, fontSize: '10px',
              textTransform: 'uppercase', letterSpacing: '0.08em',
            }}>
              {customer.severity}
            </span>
            <p style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
              Baseline (average customer): {shap.baselineScore}%
            </p>
          </div>

          {/* Card 3 — EMI Context */}
          <div className={styles.statCard}>
            <span className={styles.statLabel}>EMI Context</span>
            <span className={styles.statValue} style={{ fontSize: '20px', color: 'var(--text-primary)' }}>
              {inr(customer.emiAmount)}
            </span>
            <span className={styles.statSub}>
              {customer.activeLoans} active loan(s) · avg balance {inr(customer.assessedSavings)}
            </span>
            <div>
              <p style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '3px' }}>
                Balance covers {(customer.assessedSavings / customer.emiAmount).toFixed(1)}× the EMI
              </p>
              <div className={styles.savingsBar}>
                <div
                  className={styles.savingsFill}
                  style={{ width: `${savingsCoverage}%`, background: savingsColor }}
                />
              </div>
            </div>
          </div>

          {/* Card 4 — Prediction Delta */}
          <div className={styles.statCard}>
            <span className={styles.statLabel}>Change vs previous run</span>
            <span
              className={styles.statValue}
              style={{ fontSize: '22px', color: prevScore == null ? 'var(--text-muted)' : customer.riskScore > prevScore ? '#f87171' : '#34d399' }}
            >
              {prevScore == null ? 'first run' : `${customer.riskScore > prevScore ? '↑' : customer.riskScore < prevScore ? '↓' : '→'} ${Math.abs(customer.riskScore - prevScore)} pts`}
            </span>
            <span className={styles.statSub}>
              {previous ? `previous: ${prevScore}% (${previous.prediction_id}, ${previous.emi_due_date})` : 'No earlier batch run for this customer'}
            </span>
          </div>
        </div>

        {/* ===== ZONE 3: MAIN TWO-COLUMN GRID ===== */}
        <div className={styles.contentGrid}>

          {/* LEFT — SHAP Waterfall Chart */}
          <div className={styles.sectionCard}>
            <h2 className={styles.sectionTitle}>
              <BarChart3 size={15} className="text-cyan-400" style={{ color: '#22d3ee' }} />
              SHAP waterfall — contribution to the stress probability (points)
            </h2>
            <ShapWaterfallChart
              features={shap.features}
              baselineScore={shap.baselineScore}
              finalScore={shap.finalScore}
              severity={customer.severity}
              activeFeature={activeFeature}
              onFeatureHover={setActiveFeature}
            />
          </div>

          {/* RIGHT — Detail Table + Meta + Reasoning */}
          <div className={styles.rightCol}>

            {/* Feature Detail Table */}
            <div className={styles.sectionCard}>
              <h2 className={styles.sectionTitle}>
                <Zap size={15} style={{ color: '#fbbf24' }} />
                Feature Detail Table
              </h2>
              <FeatureDetailTable
                features={shap.features}
                activeFeature={activeFeature}
                onFeatureClick={setActiveFeature}
              />
            </div>

            {/* Model Metadata */}
            <ModelMetaCard shap={shap} metrics={metrics} asOf={fmtAsOf(customer.asOf)} />

            {/* AI Reasoning */}
            <AiReasoningCard shap={shap} reasoning={explanation.reasoning} action={explanation.action} />
          </div>
        </div>

        {/* ===== ZONE 4: ALERT TIMELINE ===== */}
        <AlertTimeline history={history} title={`Prediction history — ${customer.name}`} />

      </main>
    </div>
    </PageShell>
  );
}

/* ---------- page export with Suspense (needed for useSearchParams in App Router) ---------- */
export default function PredictionPage() {
  return (
    <Suspense fallback={<PageShell><Loading text="Loading analysis…" /></PageShell>}>
      <PredictionContent />
    </Suspense>
  );
}
