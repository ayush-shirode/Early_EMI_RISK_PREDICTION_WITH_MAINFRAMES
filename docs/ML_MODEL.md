# Machine-learning component

Code: `ml/` (`generate_data.py`, `features_ref.py`, `train.py`, `score.py`, `features_meta.py`, `layouts.py`).

## 1. Target (label)

**EMI stress in the next 90 days** = at least one installment due in the 90 days after the as-of date that was **missed**, **bounced**, or paid **30+ days late**.

The label is computed on the mainframe by EWSMATCH in `MODE=TRAIN`, from the same repayment history as the features but only from the period *after* the as-of date. Customers already in default at the as-of date (an installment unpaid for 90+ days) are excluded, since the goal is to warn *before* trouble.

## 2. Features

All computed by COBOL from data up to the as-of date (verified by `test_features_only_use_data_up_to_asof`).

| Group | Feature | Definition |
|---|---|---|
| Profile | `age`, `credit_score`, `monthly_income`, `emp_type` | from CUSTMAST (emp_type one-hot encoded as `emp_S/E/B`) |
| Exposure | `active_loans`, `total_emi` | active loans and the sum of their EMIs |
| | `emi_to_income` | total EMI ÷ monthly income |
| | `tenure_remaining` | months left on the longest active loan |
| Repayment behaviour | `inst_due_12m` | installments due in the last 12 months |
| | `late_cnt_3m`, `late_cnt_12m` | late payments (status L) |
| | `missed_cnt_12m`, `partial_cnt_12m` | missed (M) and partial (R) payments |
| | `emi_bounce_6m` | EMI auto-debits that bounced (B), last 6 months |
| | `max_dpd_12m`, `avg_dpd_6m` | maximum / average days past due |
| | `dpd_trend` | avg DPD last 3 months − avg DPD previous 3 months |
| Liquidity | `avg_balance_3m`, `min_balance_3m` | from monthly summaries |
| | `balance_trend_pct` | % change of avg balance, last 3 vs previous 3 months |
| | `savings_to_emi` | avg balance ÷ total EMI |
| Income & spending | `salary_missing_6m` | months without a salary credit |
| | `debit_credit_ratio_3m` | money out ÷ money in, last 3 months |
| | `spend_trend_pct` | % change of monthly debits, last 3 vs previous 3 months |
| | `cc_util_avg_3m` | average credit-card utilisation |

## 3. Data

The data is synthetic (Z Xplore is a shared system, so no real customer data is used). `generate_data.py` simulates each borrower month by month for 24 months (Oct 2024 – Sep 2026):

* a hidden *fragility* drives credit score, EMI burden and the chance of a **stress episode**;
* an episode has a **pre-warning phase** (3 months: spending up to +30%, more small late payments, rising card utilisation, falling balance) followed by a **shock** (salary missing or income cut, expense surge) during which EMIs bounce, are paid late or missed;
* balances evolve from income, spending and EMIs; surplus is swept to a deposit;
* about 1% of records are corrupted on purpose (non-numeric fields, invalid dates, duplicates, orphans) to exercise validation.

The generator is seeded and deterministic. 1,500 customers produce about 77,000 records.

## 4. Training (`ml/train.py`)

| Item | Choice |
|---|---|
| Training data | EWSBATCH TRAIN runs at 2025-09-30, 2025-12-31, 2026-03-31, 2026-06-30 → 4,480 labelled rows, 10.8% positive |
| Split | **time-based**: train on the first three snapshots (3,371 rows), validate on 2026-06-30 (1,109 rows). A random split would leak, because the same customer appears in several snapshots. |
| Main model | XGBoost, 250 trees, depth 3, learning rate 0.04, `min_child_weight=8`, `reg_lambda=5`, subsample 0.8 (shallow and regularised: deeper trees overfit a few thousand rows) |
| Baseline | Logistic regression on standardised features, `class_weight="balanced"` |
| Deployed model | XGBoost refit on all four snapshots after evaluation |
| Artifacts | `ml/artifacts/model.joblib` (model, feature list, 200-row SHAP background sample, version) and `ml/artifacts/metrics.json` |

## 5. Results on the held-out snapshot

| Metric | XGBoost | Logistic regression |
|---|---|---|
| ROC-AUC | **0.825** | 0.823 |
| PR-AUC (base rate 10.6%) | **0.537** | 0.521 |
| Brier score (calibration, lower is better) | **0.068** | 0.147 |
| High tier: customers / actually stressed | 50 / **74%** | 157 / 44% |
| Medium tier: customers / actually stressed | 45 / 47% | 390 / 8% |
| Low tier: customers / actually stressed | 1,014 / 5.9% | 562 / 3.4% |
| Stressed customers caught early (Medium+High) | 49% | 84% |

How to read this: both models rank customers about equally well (similar AUC), but XGBoost's probabilities are **calibrated** (Brier 0.068), so its tiers mean what they say: 3 out of 4 customers marked High really ran into EMI stress within 90 days, against 1 in 10 on average. The balanced logistic regression flags many more customers (higher recall, many more false alarms). The thresholds can be moved in `pipeline/config.py` (`TIER_MEDIUM`, `TIER_HIGH`) to trade precision for recall.

Most important features (mean |SHAP|, in probability points): spend-to-income ratio (3.9), credit-card utilisation (3.1), spending trend (2.9), installments due (0.95), active loans (0.8), DPD trend (0.6). The model learned the *early* signals (spending and liquidity) rather than relying on past delinquency, which is the purpose of the project.

These numbers come from synthetic data with a built-in signal; on real data, expect different values.

## 6. Tiers and actions

| Tier | Probability | Action code | Suggested action |
|---|---|---|---|
| High | ≥ 60% | `INTV` | Prioritise early intervention: call the customer, review restructuring or a payment holiday before the next due date |
| Medium | 30–60% | `REVW` | Review the repayment pattern and send a reminder a few days before the due date |
| Low | < 30% | `MON` | Continue regular monitoring |

## 7. Explanations (SHAP)

`shap.TreeExplainer(model, data=background, model_output="probability", feature_perturbation="interventional")` gives, for every customer, one contribution per feature in **probability units**, such that

```
baseline (average predicted risk, ~9%) + Σ contributions = this customer's probability
```

The dashboard shows them ×100 as "points" in the waterfall chart. From the contributions the backend builds:

* **reasoning text**: the top 3 risk-raising features and the main mitigating one, using phrases from `ml/features_meta.py`, e.g. *"High risk mainly because of spending 2.61× what comes in, credit cards 70% utilised and spending up 13% over 3 months. Partly offset by 4 installments due in 12 months."* This is deterministic and traceable to the numbers, unlike LLM-generated text;
* **suggestions**: the tier action plus advice tied to the top risk drivers (e.g. salary missing → verify employment, bounces → re-verify the NACH mandate);
* **top factor**: written back to the mainframe in SCOREREC and printed in the COBOL report.

## 8. Scoring (`ml/score.py`)

`score_run(run_id, features.csv)`: read the FEATCSV downloaded from z/OS → feature matrix → probability, tier, action, SHAP, reasoning → insert into SQLite `predictions` → return SCOREREC lines for the write-back.

`what_if(features, {"total_emi": x})`: the dashboard's EMI simulator. It recomputes `emi_to_income` and `savings_to_emi` for the new EMI, keeps all other mainframe features, and re-scores.

## 9. Retraining

Click **Train model** (Mainframe → Overview or Model). It re-runs the four TRAIN batches on whatever data is currently on the mainframe, retrains, evaluates and replaces the artifacts; the next batch run uses the new model. The model version (`xgb-YYYYMMDD-HHMMSS`) is stored with every prediction.
