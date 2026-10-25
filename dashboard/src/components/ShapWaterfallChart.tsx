'use client';
import { ShapFeature } from '@/lib/shap';
import styles from '@/app/prediction/prediction.module.css';

interface Props {
  features: ShapFeature[];
  baselineScore: number;
  finalScore: number;
  severity: string;
  activeFeature?: string | null;
  onFeatureHover?: (key: string | null) => void;
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#f87171',
  high: '#fb923c',
  medium: '#fbbf24',
  low: '#34d399',
};

export function ShapWaterfallChart({
  features,
  baselineScore,
  finalScore,
  severity,
  activeFeature,
  onFeatureHover,
}: Props) {
  const maxAbs = Math.max(...features.map(f => Math.abs(f.shapValue)), 1);
  const toWidth = (v: number) => `${Math.round((Math.abs(v) / maxAbs) * 88)}%`;
  const severityColor = SEVERITY_COLORS[severity] ?? '#34d399';

  return (
    <div className={styles.shapChart}>
      {/* Baseline row */}
      <div className={`${styles.shapRow} ${styles.shapBaseline}`}>
        <span className={`${styles.shapLabel} ${styles.shapMutedLabel}`}>Baseline (avg)</span>
        <div className={styles.shapTrack}>
          <div className={styles.shapBaselineFill} style={{ width: `${baselineScore}%` }} />
        </div>
        <span className={`${styles.shapValue} ${styles.shapMuted}`}>{baselineScore}</span>
      </div>

      <div className={styles.shapDivider} />

      {/* Feature rows */}
      {features.map(f => {
        const isActive = activeFeature === f.featureKey;
        return (
          <div
            key={f.featureKey}
            className={`${styles.shapRow} ${styles.shapFeatureRow}${isActive ? ` ${styles.shapActive}` : ''}`}
            title={f.explanation}
            onMouseEnter={() => onFeatureHover?.(f.featureKey)}
            onMouseLeave={() => onFeatureHover?.(null)}
          >
            <span className={`${styles.shapLabel}${isActive ? ` ${styles.shapLabelActive}` : ''}`}>
              {f.featureName}
            </span>
            <div className={styles.shapTrack}>
              {f.shapValue > 0 ? (
                <div
                  className={`${styles.shapBar} ${styles.shapBarPos}${isActive ? ` ${styles.shapBarBright}` : ''}`}
                  style={{ width: toWidth(f.shapValue) }}
                />
              ) : (
                <div
                  className={`${styles.shapBar} ${styles.shapBarNeg}${isActive ? ` ${styles.shapBarBright}` : ''}`}
                  style={{ width: toWidth(f.shapValue), marginLeft: 'auto' }}
                />
              )}
            </div>
            <span className={`${styles.shapValue} ${f.shapValue > 0 ? styles.shapPos : styles.shapNeg}`}>
              {f.shapValue > 0 ? '+' : ''}{f.shapValue.toFixed(1)}
            </span>
          </div>
        );
      })}

      <div className={styles.shapDivider} />

      {/* Final score row */}
      <div className={`${styles.shapRow} ${styles.shapFinalRow}`}>
        <span className={`${styles.shapLabel} ${styles.shapLabelBold}`}>Final risk score</span>
        <div className={styles.shapTrack}>
          <div
            className={`${styles.shapBar} ${styles.shapFinalBar}`}
            style={{ width: `${finalScore}%`, backgroundColor: severityColor }}
          />
        </div>
        <span className={`${styles.shapValue} ${styles.shapLabelBold}`} style={{ color: severityColor }}>
          {finalScore}/100
        </span>
      </div>
    </div>
  );
}
