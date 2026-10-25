'use client';
import { useState, useMemo } from 'react';
import { ShapFeature } from '@/lib/shap';
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
import styles from '@/app/prediction/prediction.module.css';

interface Props {
  features: ShapFeature[];
  activeFeature?: string | null;
  onFeatureClick?: (key: string | null) => void;
}

type SortKey = 'impact' | 'name' | 'value';
type SortDir = 'asc' | 'desc';

const IMPACT_ORDER = { high: 3, medium: 2, low: 1 };

export function FeatureDetailTable({ features, activeFeature, onFeatureClick }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('impact');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const sorted = useMemo(() => {
    return [...features].sort((a, b) => {
      let cmp = 0;
      if (sortKey === 'impact') cmp = IMPACT_ORDER[a.impact] - IMPACT_ORDER[b.impact];
      else if (sortKey === 'name') cmp = a.featureName.localeCompare(b.featureName);
      else if (sortKey === 'value') cmp = Math.abs(a.shapValue) - Math.abs(b.shapValue);
      return sortDir === 'desc' ? -cmp : cmp;
    });
  }, [features, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('desc'); }
  };

  const SortIcon = ({ k }: { k: SortKey }) => {
    if (sortKey !== k) return <ArrowUpDown size={11} style={{ color: '#4b5563' }} />;
    return sortDir === 'desc'
      ? <ArrowDown size={11} style={{ color: '#22d3ee' }} />
      : <ArrowUp size={11} style={{ color: '#22d3ee' }} />;
  };

  const impactChip = (impact: string) => {
    const cls = impact === 'high'
      ? `${styles.featChip} ${styles.featChipHigh}`
      : impact === 'medium'
      ? `${styles.featChip} ${styles.featChipMed}`
      : `${styles.featChip} ${styles.featChipLow}`;
    return <span className={cls}>{impact}</span>;
  };

  return (
    <div className={styles.featTableWrapper}>
      <table className={styles.featTable}>
        <thead>
          <tr>
            <th onClick={() => toggleSort('name')} className={`${styles.featTh} ${styles.featThClick}`}>
              <span className={styles.featThInner}>Feature <SortIcon k="name" /></span>
            </th>
            <th className={styles.featTh}>Actual Value</th>
            <th onClick={() => toggleSort('value')} className={`${styles.featTh} ${styles.featThClick}`}>
              <span className={styles.featThInner}>SHAP Impact <SortIcon k="value" /></span>
            </th>
            <th onClick={() => toggleSort('impact')} className={`${styles.featTh} ${styles.featThClick}`}>
              <span className={styles.featThInner}>Level <SortIcon k="impact" /></span>
            </th>
            <th className={styles.featTh}>Direction</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(f => {
            const isActive = activeFeature === f.featureKey;
            return (
              <tr
                key={f.featureKey}
                className={`${styles.featTr}${isActive ? ` ${styles.featTrActive}` : ''}`}
                onClick={() => onFeatureClick?.(isActive ? null : f.featureKey)}
                title={f.explanation}
              >
                <td className={`${styles.featTd} ${styles.featName}`}>{f.featureName}</td>
                <td className={`${styles.featTd} ${styles.featMono}`}>{f.rawValue}</td>
                <td className={`${styles.featTd} ${styles.featMono} ${styles.featShap} ${f.shapValue > 0 ? styles.featPos : styles.featNeg}`}>
                  {f.shapValue > 0 ? '+' : ''}{f.shapValue.toFixed(1)}
                </td>
                <td className={styles.featTd}>{impactChip(f.impact)}</td>
                <td className={`${styles.featTd} ${styles.featDir} ${f.direction === 'increase' ? styles.featPos : styles.featNeg}`}>
                  {f.direction === 'increase' ? '↑ Increases risk' : '↓ Reduces risk'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
