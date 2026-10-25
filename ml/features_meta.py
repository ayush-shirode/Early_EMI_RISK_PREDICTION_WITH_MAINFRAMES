"""Human-readable names and explanation phrases for the model features."""
from __future__ import annotations


def _inr(v: float) -> str:
    return f"₹{v:,.0f}"


# key: (label, value formatter, phrase when it RAISES risk, phrase when it LOWERS risk)
FEATURES: dict[str, tuple] = {
    "age": ("Age", lambda v: f"{v:.0f} yrs", "age profile ({v})", "age profile ({v})"),
    "monthly_income": ("Monthly income", _inr, "a modest income of {v}", "a solid income of {v}"),
    "credit_score": ("Credit score", lambda v: f"{v:.0f}", "a credit score of {v}", "a strong credit score of {v}"),
    "active_loans": ("Active loans", lambda v: f"{v:.0f}", "{v} active loans", "only {v} active loan(s)"),
    "total_emi": ("Total EMI", _inr, "a total EMI of {v}", "a manageable EMI of {v}"),
    "emi_to_income": ("EMI-to-income ratio", lambda v: f"{v * 100:.0f}%",
                      "EMIs take {v} of income", "EMIs take only {v} of income"),
    "tenure_remaining": ("Loan tenure remaining", lambda v: f"{v:.0f} months",
                         "{v} of repayments still ahead", "only {v} of repayments left"),
    "inst_due_12m": ("Installments due (12 m)", lambda v: f"{v:.0f}", "{v} installments due in 12 months",
                     "{v} installments due in 12 months"),
    "late_cnt_3m": ("Late payments (3 m)", lambda v: f"{v:.0f}", "{v} late EMI payment(s) in the last 3 months",
                    "no late EMIs in the last 3 months"),
    "late_cnt_12m": ("Late payments (12 m)", lambda v: f"{v:.0f}", "{v} late EMI payment(s) in the last year",
                     "few late EMIs in the last year ({v})"),
    "missed_cnt_12m": ("Missed EMIs (12 m)", lambda v: f"{v:.0f}", "{v} missed EMI(s) in the last year",
                       "no missed EMIs in the last year"),
    "partial_cnt_12m": ("Partial payments (12 m)", lambda v: f"{v:.0f}", "{v} partial EMI payment(s) in the last year",
                        "no partial EMI payments"),
    "emi_bounce_6m": ("EMI bounces (6 m)", lambda v: f"{v:.0f}", "{v} EMI auto-debit(s) bounced in 6 months",
                      "no EMI bounces in 6 months"),
    "txn_bounce_6m": ("Account bounces (6 m)", lambda v: f"{v:.0f}", "{v} failed debits on the account in 6 months",
                      "no failed debits in 6 months"),
    "max_dpd_12m": ("Max days past due (12 m)", lambda v: f"{v:.0f} days", "payments up to {v} late",
                    "never more than {v} late"),
    "avg_dpd_6m": ("Avg days past due (6 m)", lambda v: f"{v:.1f} days", "EMIs paid {v} late on average",
                   "EMIs paid on time ({v} late on average)"),
    "dpd_trend": ("Days-past-due trend", lambda v: f"{v:+.1f} days", "payment delays growing ({v})",
                  "payment delays shrinking ({v})"),
    "avg_balance_3m": ("Avg balance (3 m)", _inr, "a low average balance of {v}", "a healthy average balance of {v}"),
    "min_balance_3m": ("Min balance (3 m)", _inr, "balance dipping to {v}", "balance never below {v}"),
    "balance_trend_pct": ("Balance trend (3 m)", lambda v: f"{v:+.0f}%", "balance falling {v} over 3 months",
                          "balance growing {v} over 3 months"),
    "savings_to_emi": ("Savings vs EMI", lambda v: f"{v:.1f}× EMI", "savings cover only {v}",
                       "savings cover {v}"),
    "salary_missing_6m": ("Months without salary (6 m)", lambda v: f"{v:.0f}",
                          "{v} month(s) without a salary credit", "salary credited every month"),
    "debit_credit_ratio_3m": ("Spend-to-income (3 m)", lambda v: f"{v:.2f}",
                              "spending {v}× what comes in", "spending within income ({v}×)"),
    "spend_trend_pct": ("Spending trend (3 m)", lambda v: f"{v:+.0f}%", "spending up {v} over 3 months",
                        "spending down {v} over 3 months"),
    "cc_util_avg_3m": ("Credit-card utilisation", lambda v: f"{v:.0f}%", "credit cards {v} utilised",
                       "credit-card utilisation at {v}"),
    "emp_S": ("Salaried", lambda v: "yes" if v else "no", "employment type", "salaried employment"),
    "emp_E": ("Self-employed", lambda v: "yes" if v else "no", "self-employed income", "employment type"),
    "emp_B": ("Business owner", lambda v: "yes" if v else "no", "business income", "employment type"),
}


def label(key: str) -> str:
    return FEATURES.get(key, (key,))[0]


def fmt(key: str, value: float) -> str:
    meta = FEATURES.get(key)
    return meta[1](value) if meta else f"{value}"


# Trend features are worded from the sign of the value, not from the SHAP direction.
TRENDS = {"balance_trend_pct": ("balance", "%", "over 3 months"),
          "spend_trend_pct": ("spending", "%", "over 3 months"),
          "dpd_trend": ("payment delays", " days", "vs the quarter before")}


def phrase(key: str, value: float, raises_risk: bool) -> str:
    if key in TRENDS:
        noun, unit, span = TRENDS[key]
        amount = f"{abs(value):.0f}{unit}" if unit == "%" else f"{abs(value):.1f}{unit}"
        if round(value) == 0 and unit == "%":
            return f"{noun} flat {span}"
        return f"{noun} {'up' if value > 0 else 'down'} {amount} {span}"
    meta = FEATURES.get(key)
    if not meta:
        return f"{key} = {value}"
    return (meta[2] if raises_risk else meta[3]).format(v=meta[1](value))


# Practical suggestions for a relationship manager, keyed by the feature that drives risk.
SUGGESTIONS = {
    "debit_credit_ratio_3m": "Outflows exceed inflows: offer a budgeting call and check for new unsecured borrowing.",
    "spend_trend_pct": "Spending is rising quickly: send a pre-due reminder and review discretionary categories.",
    "cc_util_avg_3m": "Credit cards are heavily used: check for revolving balances that compete with the EMI.",
    "balance_trend_pct": "The account balance is draining: schedule a reminder 5 days before the EMI date.",
    "min_balance_3m": "The balance has dipped close to zero: confirm funds before the next auto-debit.",
    "avg_balance_3m": "Low average balance: confirm the EMI account will be funded on the due date.",
    "savings_to_emi": "Savings barely cover one EMI: discuss an emergency buffer or EMI date realignment.",
    "salary_missing_6m": "Salary credits are missing: verify employment status and offer a short payment holiday.",
    "emi_bounce_6m": "Recent EMI bounces: re-verify the NACH mandate and debit account before the next cycle.",
    "txn_bounce_6m": "Other debits are failing on the account: early sign of a cash crunch, contact proactively.",
    "late_cnt_3m": "Recent late payments: a courtesy call before the due date usually prevents a miss.",
    "late_cnt_12m": "Repeated late payments: review whether the EMI date matches the salary date.",
    "missed_cnt_12m": "Missed EMIs in the last year: assess restructuring before the account slips into default.",
    "partial_cnt_12m": "Partial payments: the EMI may be unaffordable; evaluate tenure extension.",
    "max_dpd_12m": "Payments have run well past due: monitor closely this cycle.",
    "avg_dpd_6m": "EMIs are usually paid late: suggest moving the due date after the salary credit.",
    "dpd_trend": "Payment delays are increasing: intervene before they cross 30 days.",
    "emi_to_income": "EMIs take a large share of income: consider tenure extension to lower the EMI.",
    "credit_score": "Weak bureau score: watch for new credit enquiries elsewhere.",
}
