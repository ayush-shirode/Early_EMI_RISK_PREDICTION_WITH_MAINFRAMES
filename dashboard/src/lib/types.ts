export type Severity = 'low' | 'medium' | 'high';

/** One scored borrower, as returned by GET /customers (built from mainframe data + model output). */
export interface Customer {
  id: string;
  name: string;
  city: string;
  accountType: 'salaried' | 'self-employed' | 'business';
  age: number;
  monthlyIncome: number;
  creditScore: number;
  emiAmount: number;           // total EMI of all active loans
  emiDueDate: string;          // due day of the largest active loan
  loanType: 'home' | 'car' | 'personal' | 'education';
  loanTenureMonths: number;
  loanStartDate: string;
  monthsRemaining: number;
  activeLoans: number;
  riskScore: number;           // probability x 100
  missProbability: number;     // probability of EMI stress in the next 90 days
  severity: Severity;
  tier: 'Low' | 'Medium' | 'High';
  assessedSavings: number;     // average balance, last 3 months
  spendTrend: { month: string; amount: number }[];
  suggestions: string[];
  reasoning: string;
  topFactor: string;
  action: string;
  asOf: number;
  lastPredictionAt: string;
  modelVersion: string;
  runId: number;
}

export interface CustomerDetail extends Customer {
  loans: {
    loan_id: string; loan_type: string; principal: number; int_rate: number; tenure: number;
    start_date: number; emi_amt: number; due_day: number; outstanding: number; status: string;
  }[];
  monthly: {
    yyyymm: number; credits: number; debits: number; salary: number;
    min_bal: number; avg_bal: number; bounces: number; cc_util: number;
  }[];
}

/** A past prediction, shown in the alert timeline. */
export interface Prediction {
  prediction_id: string;
  severity: Severity;
  miss_probability: number;
  reasoning: string;
  created_at: string;
  emi_amount: number;
  emi_due_date: string;
}

export interface ExplanationFeature {
  key: string; label: string; value: number; display: string; shap: number; phrase: string;
}

export interface Explanation {
  custId: string; asOf: number; probability: number; tier: string; base: number;
  features: ExplanationFeature[]; otherFeaturesShap: number; featureCount: number;
  reasoning: string; action: string; modelVersion: string; computedAt: string;
}

export interface RunStep {
  seq: number; name: string; status: 'pending' | 'running' | 'ok' | 'failed' | 'skipped';
  started_at: string | null; finished_at: string | null; detail: string | null;
  data: {
    jobid?: string; jobname?: string; retcode?: string;
    steps?: { step: string; procstep: string | null; rc: number | null; status: string; abend?: string }[];
    runctl?: Record<string, string | number>;
    [k: string]: unknown;
  };
}

export interface Run {
  id: number; action: string; params: Record<string, unknown>;
  status: 'running' | 'ok' | 'failed'; started_at: string; finished_at: string | null;
  error: string | null; summary: Record<string, any>; steps?: RunStep[];
}

export interface MainframeStatus {
  mainframe: {
    ok: boolean; error?: string;
    connection?: { user: string; system: string; zos_version: string; zosmf_version: string; port: string };
    hlq?: string;
    libraries?: Record<string, boolean>;
    programs?: Record<string, boolean>;
    inputs?: Record<string, boolean>;
    datasets?: string[];
  } | null;
  checked_at: number;
  data: { customers: number; seed: number; records: Record<string, number>; defects: number; generated_at: string } | null;
  model: { model_version: string; trained_at: string; rows: number; roc_auc: number } | null;
  last_score_run: Run | null;
  active_run: number | null;
}

export interface ModelMetrics {
  model_version: string; trained_at: string; algorithm: string; rows: number; positive_rate: number;
  train_asofs: number[]; validation_asof: number; train_rows: number; validation_rows: number;
  thresholds: { medium: number; high: number };
  validation: Record<'xgboost' | 'logistic_regression', {
    roc_auc: number; pr_auc: number; brier: number; base_rate: number;
    tiers: Record<'High' | 'Medium' | 'Low', { count: number; observed_stress_rate: number | null }>;
    recall_medium_or_high: number; precision_high: number;
    confusion_at_medium: { tp: number; fp: number; fn: number; tn: number };
  }>;
  feature_importance: { feature: string; mean_abs_shap: number }[];
}
