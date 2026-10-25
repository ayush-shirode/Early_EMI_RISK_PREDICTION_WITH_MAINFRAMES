'use client';
import { useEffect, useState } from 'react';
import { api, fmtAsOf, fmtTime } from '@/lib/api';
import type { ModelMetrics } from '@/lib/types';
import { ActionButton } from '@/components/ActionButton';

const LABELS: Record<string, string> = {
  debit_credit_ratio_3m: 'Spend-to-income (3 m)', cc_util_avg_3m: 'Credit-card utilisation', spend_trend_pct: 'Spending trend',
  balance_trend_pct: 'Balance trend', min_balance_3m: 'Min balance (3 m)', avg_balance_3m: 'Avg balance (3 m)',
  savings_to_emi: 'Savings vs EMI', salary_missing_6m: 'Months without salary', emi_bounce_6m: 'EMI bounces (6 m)',
  txn_bounce_6m: 'Account bounces (6 m)', late_cnt_3m: 'Late EMIs (3 m)', late_cnt_12m: 'Late EMIs (12 m)',
  missed_cnt_12m: 'Missed EMIs (12 m)', partial_cnt_12m: 'Partial EMIs (12 m)', max_dpd_12m: 'Max days past due',
  avg_dpd_6m: 'Avg days past due', dpd_trend: 'DPD trend', emi_to_income: 'EMI-to-income', credit_score: 'Credit score',
  monthly_income: 'Monthly income', total_emi: 'Total EMI', active_loans: 'Active loans', tenure_remaining: 'Tenure remaining',
  inst_due_12m: 'Installments due (12 m)', age: 'Age', emp_S: 'Salaried', emp_E: 'Self-employed', emp_B: 'Business',
};

const pct = (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`);

export default function ModelPage() {
  const [m, setM] = useState<ModelMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.get<ModelMetrics>('/model').then(setM).catch(e => setError(e.message)); }, []);

  const train = <ActionButton action="train_model" label={m ? 'Retrain model' : 'Train model'} variant={m ? 'secondary' : 'primary'} />;
  if (error) return <div className="space-y-4"><p className="text-sm text-gray-400">{error}</p>{train}</div>;
  if (!m) return <p className="text-sm text-gray-400">Loading…</p>;

  const x = m.validation.xgboost, lr = m.validation.logistic_regression;
  const maxImp = m.feature_importance[0]?.mean_abs_shap || 1;

  return (
    <div className="space-y-6">
      <div className="glass-panel p-5 flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-sm font-bold text-gray-100 font-mono">{m.model_version}</p>
          <p className="text-xs text-gray-400 mt-1">
            {m.algorithm} · trained {fmtTime(m.trained_at)} · {m.rows.toLocaleString('en-IN')} labelled rows · stressed {pct(m.positive_rate)}
          </p>
          <p className="text-xs text-gray-500 mt-1">
            Time-based split: trained on as-of {m.train_asofs.map(fmtAsOf).join(', ')} ({m.train_rows} rows), validated on {fmtAsOf(m.validation_asof)} ({m.validation_rows} rows).
            Labels come from EWSMATCH in TRAIN mode: stress = a missed or bounced EMI, or 30+ days past due, within 90 days after the as-of date.
          </p>
        </div>
        {train}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[['ROC-AUC', x.roc_auc.toFixed(3), `baseline LR ${lr.roc_auc.toFixed(3)}`],
          ['PR-AUC', x.pr_auc.toFixed(3), `base rate ${pct(x.base_rate)}`],
          ['High-tier precision', pct(x.precision_high), `of ${x.tiers.High.count} flagged High`],
          ['Caught early (Med+High)', pct(x.recall_medium_or_high), 'of customers who became stressed']].map(([l, v, s]) => (
          <div key={l} className="glass-panel p-5">
            <p className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">{l}</p>
            <p className="text-3xl font-black font-mono mt-1 text-cyan-400">{v}</p>
            <p className="text-xs text-gray-500 mt-1">{s}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-panel p-5">
          <h3 className="text-sm font-bold tracking-wider text-gray-400 uppercase mb-4">Tiers on the validation snapshot</h3>
          <table className="w-full text-sm">
            <thead><tr className="text-[10px] uppercase tracking-widest text-gray-500 border-b border-[#1f293d]">
              <th className="py-2 text-left">Tier</th><th className="py-2 text-right">Customers</th><th className="py-2 text-right">Actually stressed</th>
            </tr></thead>
            <tbody>
              {(['High', 'Medium', 'Low'] as const).map(t => (
                <tr key={t} className="border-b border-[#1f293d]/40">
                  <td className={`py-2 font-semibold ${t === 'High' ? 'text-orange-400' : t === 'Medium' ? 'text-yellow-400' : 'text-emerald-400'}`}>
                    {t} {t === 'High' ? `(≥ ${m.thresholds.high * 100}%)` : t === 'Medium' ? `(${m.thresholds.medium * 100}–${m.thresholds.high * 100}%)` : `(< ${m.thresholds.medium * 100}%)`}
                  </td>
                  <td className="py-2 text-right font-mono">{x.tiers[t].count}</td>
                  <td className="py-2 text-right font-mono">{pct(x.tiers[t].observed_stress_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3 className="text-sm font-bold tracking-wider text-gray-400 uppercase mt-6 mb-3">Confusion matrix (flagged = Medium or High)</h3>
          <div className="grid grid-cols-3 gap-1 text-xs text-center max-w-sm">
            <div />
            <div className="text-gray-500 py-1">Stressed</div><div className="text-gray-500 py-1">Not stressed</div>
            <div className="text-gray-500 py-2 text-right pr-2">Flagged</div>
            <div className="bg-emerald-500/10 border border-emerald-500/30 rounded py-2 font-mono">{x.confusion_at_medium.tp}</div>
            <div className="bg-rose-500/5 border border-rose-500/20 rounded py-2 font-mono">{x.confusion_at_medium.fp}</div>
            <div className="text-gray-500 py-2 text-right pr-2">Not flagged</div>
            <div className="bg-rose-500/10 border border-rose-500/30 rounded py-2 font-mono">{x.confusion_at_medium.fn}</div>
            <div className="bg-emerald-500/5 border border-emerald-500/20 rounded py-2 font-mono">{x.confusion_at_medium.tn}</div>
          </div>
          <p className="text-xs text-gray-500 mt-4">
            Baseline logistic regression for comparison: ROC-AUC {lr.roc_auc.toFixed(3)}, PR-AUC {lr.pr_auc.toFixed(3)}, Brier {lr.brier.toFixed(3)} (XGBoost Brier {x.brier.toFixed(3)}, lower is better calibrated).
          </p>
        </div>

        <div className="glass-panel p-5">
          <h3 className="text-sm font-bold tracking-wider text-gray-400 uppercase mb-4">Global feature importance (mean |SHAP|)</h3>
          <div className="space-y-2">
            {m.feature_importance.slice(0, 14).map(f => (
              <div key={f.feature} className="flex items-center gap-3 text-xs">
                <span className="w-44 text-gray-300 truncate">{LABELS[f.feature] ?? f.feature}</span>
                <div className="flex-1 h-2 bg-[#1f293d] rounded-full overflow-hidden">
                  <div className="h-full bg-cyan-500/70 rounded-full" style={{ width: `${(f.mean_abs_shap / maxImp) * 100}%` }} />
                </div>
                <span className="w-14 text-right font-mono text-gray-400">{(f.mean_abs_shap * 100).toFixed(2)}</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-500 mt-3">Average change in predicted risk, in percentage points.</p>
        </div>
      </div>
    </div>
  );
}
