"""Train the EMI-stress model on feature files produced by EWSBATCH in TRAIN mode.

Time-based evaluation: the latest as-of snapshot is held out for validation, all
earlier snapshots are used for training (a customer appears in several snapshots,
so a random split would leak). The deployed model is then refit on all snapshots.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from ml.features_ref import FEATURE_COLUMNS
from pipeline.config import ARTIFACTS_DIR, TIER_HIGH, TIER_MEDIUM

ID_COLUMNS = ("cust_id", "as_of_date", "emp_type", "label_stress_90d")
NUMERIC = [c for c in FEATURE_COLUMNS if c not in ID_COLUMNS]
MODEL_FEATURES = NUMERIC + ["emp_S", "emp_E", "emp_B"]


def read_features(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"cust_id": str, "emp_type": str, "label_stress_90d": str})


def to_matrix(df: pd.DataFrame) -> pd.DataFrame:
    X = df[NUMERIC].astype(float).copy()
    for t in "SEB":
        X[f"emp_{t}"] = (df["emp_type"] == t).astype(float)
    return X[MODEL_FEATURES]


def xgb() -> XGBClassifier:
    # Shallow, regularised trees: a few thousand rows overfit deeper models.
    return XGBClassifier(n_estimators=250, max_depth=3, learning_rate=0.04, subsample=0.8,
                         colsample_bytree=0.7, min_child_weight=8, reg_lambda=5,
                         eval_metric="logloss", random_state=7, n_jobs=4)


def evaluate(y: np.ndarray, p: np.ndarray) -> dict:
    high, medium = p >= TIER_HIGH, (p >= TIER_MEDIUM) & (p < TIER_HIGH)
    flagged = p >= TIER_MEDIUM

    def rate(mask):
        return float(y[mask].mean()) if mask.any() else None

    return {
        "roc_auc": float(roc_auc_score(y, p)),
        "pr_auc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "base_rate": float(y.mean()),
        "tiers": {
            "High": {"count": int(high.sum()), "observed_stress_rate": rate(high)},
            "Medium": {"count": int(medium.sum()), "observed_stress_rate": rate(medium)},
            "Low": {"count": int((~flagged).sum()), "observed_stress_rate": rate(~flagged)},
        },
        # Of the customers who really became stressed, how many did Medium+High catch early?
        "recall_medium_or_high": float(flagged[y == 1].mean()) if (y == 1).any() else None,
        "precision_high": rate(high),
        "confusion_at_medium": {
            "tp": int((flagged & (y == 1)).sum()), "fp": int((flagged & (y == 0)).sum()),
            "fn": int((~flagged & (y == 1)).sum()), "tn": int((~flagged & (y == 0)).sum()),
        },
    }


def train(paths: list[Path], out_dir: Path = ARTIFACTS_DIR) -> dict:
    df = pd.concat([read_features(p) for p in paths], ignore_index=True)
    df = df[df["label_stress_90d"].isin(["0", "1"])]
    y = (df["label_stress_90d"] == "1").astype(int).to_numpy()
    X = to_matrix(df)
    asofs = sorted(df["as_of_date"].unique())
    if len(asofs) < 2:
        raise ValueError("Need at least two TRAIN snapshots for a time-based split")
    valid = (df["as_of_date"] == asofs[-1]).to_numpy()

    lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))
    lr.fit(X[~valid], y[~valid])
    model_v = xgb().fit(X[~valid], y[~valid])
    validation = {
        "xgboost": evaluate(y[valid], model_v.predict_proba(X[valid])[:, 1]),
        "logistic_regression": evaluate(y[valid], lr.predict_proba(X[valid])[:, 1]),
    }

    final = xgb().fit(X, y)
    background = X.sample(n=min(200, len(X)), random_state=7)
    explainer = shap.TreeExplainer(final, data=background, model_output="probability",
                                   feature_perturbation="interventional")
    sample = X.sample(n=min(500, len(X)), random_state=11)
    importance = np.abs(explainer.shap_values(sample)).mean(axis=0)

    version = "xgb-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    metrics = {
        "model_version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "algorithm": "XGBoost (gradient-boosted trees), baseline: logistic regression",
        "rows": int(len(df)),
        "positive_rate": float(y.mean()),
        "train_asofs": [int(a) for a in asofs[:-1]],
        "validation_asof": int(asofs[-1]),
        "train_rows": int((~valid).sum()),
        "validation_rows": int(valid.sum()),
        "thresholds": {"medium": TIER_MEDIUM, "high": TIER_HIGH},
        "validation": validation,
        "feature_importance": sorted(
            [{"feature": f, "mean_abs_shap": float(v)} for f, v in zip(MODEL_FEATURES, importance)],
            key=lambda d: -d["mean_abs_shap"]),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": final, "features": MODEL_FEATURES, "background": background,
                 "version": version}, out_dir / "model.joblib")
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    import sys

    m = train([Path(p) for p in sys.argv[1:]])
    print(json.dumps({k: m[k] for k in ("model_version", "rows", "positive_rate", "validation")}, indent=2))
