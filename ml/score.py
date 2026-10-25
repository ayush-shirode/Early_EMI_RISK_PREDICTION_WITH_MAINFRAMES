"""Score a FEATCSV file from EWSBATCH: probability, tier, action, SHAP explanation.

Results go to SQLite (for the dashboard) and to SCOREREC fixed-width records that the
backend uploads back to the mainframe (EWS.SCORES) for the EWSRPT report.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap

from ml import features_meta as meta
from ml.layouts import SCOREREC
from ml.train import MODEL_FEATURES, read_features, to_matrix
from pipeline import db
from pipeline.config import ARTIFACTS_DIR, TIER_HIGH, TIER_MEDIUM

ACTIONS = {
    "High": ("INTV", "Prioritise early intervention: call the customer and review restructuring "
                     "or a payment-holiday option before the next due date"),
    "Medium": ("REVW", "Review the repayment pattern and send a reminder a few days before the due date"),
    "Low": ("MON", "Continue regular monitoring"),
}


def model_exists() -> bool:
    return (ARTIFACTS_DIR / "model.joblib").exists()


@lru_cache(maxsize=1)
def _bundle(mtime: float) -> dict:
    b = joblib.load(ARTIFACTS_DIR / "model.joblib")
    b["explainer"] = shap.TreeExplainer(b["model"], data=b["background"], model_output="probability",
                                        feature_perturbation="interventional")
    return b


def bundle() -> dict:
    return _bundle((ARTIFACTS_DIR / "model.joblib").stat().st_mtime)


def metrics() -> dict | None:
    p = ARTIFACTS_DIR / "metrics.json"
    return json.loads(p.read_text()) if p.exists() else None


def tier_of(p: float) -> str:
    return "High" if p >= TIER_HIGH else "Medium" if p >= TIER_MEDIUM else "Low"


def explain(X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, float]:
    b = bundle()
    probs = b["model"].predict_proba(X[MODEL_FEATURES])[:, 1]
    sv = np.asarray(b["explainer"].shap_values(X[MODEL_FEATURES]))
    base = float(np.ravel(b["explainer"].expected_value)[0])
    return probs, sv, base


def shap_detail(row: pd.Series, shap_row: np.ndarray, base: float, prob: float) -> dict:
    feats = []
    for name, value, contrib in zip(MODEL_FEATURES, row[MODEL_FEATURES], shap_row):
        feats.append({
            "key": name, "label": meta.label(name), "value": float(value),
            "display": meta.fmt(name, float(value)), "shap": float(contrib),
            "phrase": meta.phrase(name, float(value), contrib > 0),
        })
    feats.sort(key=lambda f: -abs(f["shap"]))
    return {"base": base, "probability": prob, "features": feats}


def reasoning(detail: dict, tier: str) -> str:
    up = [f for f in detail["features"] if f["shap"] > 0.005][:3]
    down = [f for f in detail["features"] if f["shap"] < -0.005][:2]
    if tier == "Low" or not up:
        why = " and ".join(f["phrase"] for f in down) or "no warning signs in the recent data"
        return f"{tier} risk: {why}."
    text = f"{tier} risk mainly because of " + ", ".join(f["phrase"] for f in up[:-1])
    text += (" and " if len(up) > 1 else "") + up[-1]["phrase"] + "."
    if down:
        text += f" Partly offset by {down[0]['phrase']}."
    return text


def score_frame(df: pd.DataFrame) -> list[dict]:
    X = to_matrix(df)
    probs, sv, base = explain(X)
    out = []
    for i, (_, row) in enumerate(df.iterrows()):
        p = float(probs[i])
        tier = tier_of(p)
        detail = shap_detail(X.iloc[i], sv[i], base, p)
        top_up = next((f for f in detail["features"] if f["shap"] > 0), detail["features"][0])
        out.append({
            "cust_id": row["cust_id"], "as_of": int(row["as_of_date"]), "probability": p, "tier": tier,
            "action_code": ACTIONS[tier][0], "action": ACTIONS[tier][1], "top_factor": top_up["label"],
            "reasoning": reasoning(detail, tier), "features": {k: row[k] for k in df.columns}, "shap": detail,
            "total_emi": float(row["total_emi"]),
        })
    return out


def score_run(run_id: int, features_csv: Path) -> dict:
    df = read_features(features_csv)
    rows = score_frame(df)
    version = bundle()["version"]
    now = db.now()
    with db.tx() as con:
        con.executemany(
            "INSERT INTO predictions(run_id, cust_id, as_of, probability, tier, action, top_factor, reasoning, "
            "features, shap, model_version, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [(run_id, r["cust_id"], r["as_of"], r["probability"], r["tier"], r["action"], r["top_factor"],
              r["reasoning"], json.dumps(r["features"], default=str), json.dumps(r["shap"]), version, now)
             for r in rows])
    records = [SCOREREC.format({
        "cust_id": r["cust_id"], "asof": r["as_of"], "prob": round(r["probability"], 4),
        "tier": r["tier"].upper(), "action": r["action_code"], "top_factor": r["top_factor"].upper(),
        "total_emi": r["total_emi"]}) for r in rows]
    tiers = {t: sum(1 for r in rows if r["tier"] == t) for t in ("High", "Medium", "Low")}
    return {"scored": len(rows), "tiers": tiers, "model_version": version, "score_records": records}


def what_if(features: dict, overrides: dict) -> dict:
    """Re-score one customer with changed inputs (used by the dashboard EMI simulator)."""
    row = {**features, **overrides}
    if "total_emi" in overrides:
        emi = float(overrides["total_emi"])
        row["emi_to_income"] = min(emi / float(row["monthly_income"]), 99.9999)
        row["savings_to_emi"] = min(float(row["avg_balance_3m"]) / emi, 9999.99) if emi else 9999.99
    r = score_frame(pd.DataFrame([row]))[0]
    return {k: r[k] for k in ("probability", "tier", "action", "reasoning", "shap")}
