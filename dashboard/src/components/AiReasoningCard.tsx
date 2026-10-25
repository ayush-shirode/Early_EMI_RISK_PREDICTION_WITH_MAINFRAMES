'use client';
import { ShapResult } from '@/lib/shap';
import { Brain, TrendingUp, Shield, Lightbulb } from 'lucide-react';
import styles from '@/app/prediction/prediction.module.css';

/** Plain-language summary built from the SHAP values (no LLM: deterministic and traceable). */
export function AiReasoningCard({ shap, reasoning, action }: { shap: ShapResult; reasoning: string; action: string }) {
  const topDriver = shap.features.find(f => f.shapValue > 0);
  const topMitigator = shap.features.find(f => f.shapValue < 0);
  return (
    <div className={styles.reasoningCard}>
      <div className={styles.reasoningHeader}>
        <Brain size={16} style={{ color: '#22d3ee' }} />
        <h3 className={styles.reasoningTitle}>Why this score</h3>
      </div>
      <p className={styles.reasoningSummary}>{reasoning}</p>
      <div className={styles.reasoningBlocks}>
        {topDriver && (
          <div className={`${styles.reasoningBlock} ${styles.reasoningBlockRisk}`}>
            <div className={styles.reasoningBlockHeader}><TrendingUp size={13} /><span>Primary risk driver</span></div>
            <p className={styles.reasoningBlockName}>{topDriver.featureName} — {topDriver.rawValue} (+{topDriver.shapValue} pts)</p>
            <p className={styles.reasoningBlockText}>{topDriver.explanation}</p>
          </div>
        )}
        {topMitigator && (
          <div className={`${styles.reasoningBlock} ${styles.reasoningBlockSafe}`}>
            <div className={styles.reasoningBlockHeader}><Shield size={13} /><span>Mitigating factor</span></div>
            <p className={styles.reasoningBlockName}>{topMitigator.featureName} — {topMitigator.rawValue} ({topMitigator.shapValue} pts)</p>
            <p className={styles.reasoningBlockText}>{topMitigator.explanation}</p>
          </div>
        )}
        <div className={`${styles.reasoningBlock} ${styles.reasoningBlockAction}`}>
          <div className={styles.reasoningBlockHeader}><Lightbulb size={13} /><span>Recommended action</span></div>
          <p className={styles.reasoningBlockText}>{action}</p>
        </div>
      </div>
    </div>
  );
}
