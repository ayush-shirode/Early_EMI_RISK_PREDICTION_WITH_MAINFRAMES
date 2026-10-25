'use client';
import Link from 'next/link';
import { Brain, ArrowRight } from 'lucide-react';
import type { Customer } from '@/lib/types';
import { getSeverityColor } from '@/lib/customers';
import styles from '@/app/prediction/prediction.module.css';

export function PredictionCTA({ customer }: { customer: Customer }) {
  const sevColor = getSeverityColor(customer.severity);
  return (
    <div className={styles.ctaCard}>
      <div className={styles.ctaLeft}>
        <div className={styles.ctaIconWrap}><Brain size={22} style={{ color: '#22d3ee' }} /></div>
        <div>
          <p className={styles.ctaTitle}>SHAP explanation ready</p>
          <p className={styles.ctaSub}>
            {customer.name} —{' '}
            <span style={{ color: sevColor, fontWeight: 700, textTransform: 'uppercase', fontSize: '11px' }}>{customer.severity}</span>{' '}
            risk · <span style={{ color: sevColor, fontWeight: 700 }}>{customer.riskScore}%</span> stress probability · top factor: {customer.topFactor}
          </p>
        </div>
      </div>
      <Link href={`/prediction?customerId=${customer.id}`} className={styles.ctaLink}>
        <button className={styles.ctaBtn}>View full analysis <ArrowRight size={15} /></button>
      </Link>
    </div>
  );
}
