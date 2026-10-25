"""Golden test: the features computed by COBOL on z/OS must equal the Python reference rules.

Uses the latest batch run downloaded by the backend (data/runs/<id>/*/features.csv) and the
input files that were uploaded for it (data/input). Skipped when no such run exists.
"""
import json

import pandas as pd
import pytest

from ml.features_ref import FEATURE_COLUMNS, compute_features, load_inputs
from pipeline.config import INPUT_DIR, RUNS_DIR


def latest_feature_files():
    if not (INPUT_DIR / "manifest.json").exists():
        return []
    generated = (INPUT_DIR / "manifest.json").stat().st_mtime
    files = [p for p in RUNS_DIR.glob("*/*/features.csv") if p.stat().st_mtime > generated]
    return sorted(files, key=lambda p: p.stat().st_mtime)[-2:]


@pytest.mark.parametrize("path", latest_feature_files() or [None])
def test_mainframe_features_equal_reference(path):
    if path is None:
        pytest.skip("No mainframe batch output newer than the current input data")
    runctl = dict(l.split("=", 1) for l in (path.parent / "runctl.txt").read_text().splitlines() if "=" in l)
    asof, mode = int(runctl["ASOF"]), runctl["MODE"].strip()
    mf = pd.read_csv(path, dtype=str).fillna("")
    ref = pd.DataFrame(compute_features(load_inputs(INPUT_DIR), asof, mode)).astype(str)
    assert list(mf.columns) == FEATURE_COLUMNS
    assert sorted(mf.cust_id) == sorted(ref.cust_id)
    m = mf.merge(ref, on="cust_id", suffixes=("_mf", "_py"))
    for col in FEATURE_COLUMNS[1:]:
        a, b = m[f"{col}_mf"], m[f"{col}_py"]
        if col in ("emp_type", "label_stress_90d"):
            assert (a == b).all(), col
        else:
            diff = (a.astype(float) - b.astype(float)).abs().max()
            assert diff <= 0.011, f"{col} differs by {diff}"
