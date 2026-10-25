'use client';
import { ShapResult } from '@/lib/shap';
import type { ModelMetrics } from '@/lib/types';
import { Cpu, Clock, Layers, BarChart3, Target, Hash, Award } from 'lucide-react';
import styles from '@/app/prediction/prediction.module.css';

export function ModelMetaCard({ shap, metrics, asOf }: { shap: ShapResult; metrics: ModelMetrics | null; asOf: string }) {
  const chips = [
    { label: 'Model', value: 'XGBoost classifier', icon: Cpu },
    { label: 'Version', value: shap.modelVersion, icon: Hash },
    { label: 'Scored', value: new Date(shap.computedAt).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }), icon: Clock },
    { label: 'Data window', value: `12 months to ${asOf}`, icon: Layers },
    { label: 'Baseline risk', value: `${shap.baselineScore}%`, icon: Target },
    { label: 'Features', value: String(shap.featureCount), icon: BarChart3 },
    ...(metrics ? [{ label: 'Validation ROC-AUC', value: metrics.validation.xgboost.roc_auc.toFixed(3), icon: Award }] : []),
  ];
  return (
    <div className={styles.metaCard}>
      <h3 className={styles.metaTitle}>Model metadata</h3>
      <div className={styles.metaGrid}>
        {chips.map(({ label, value, icon: Icon }) => (
          <div key={label} className={styles.metaChip}>
            <Icon size={13} className={styles.metaChipIcon} />
            <div>
              <p className={styles.metaChipLabel}>{label}</p>
              <p className={styles.metaChipValue}>{value}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
