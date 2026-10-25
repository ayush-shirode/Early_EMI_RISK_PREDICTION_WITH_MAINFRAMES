"""Synthetic data generator and the reference implementation of the EWSBATCH rules."""
import json

import pytest

from ml.features_ref import FEATURE_COLUMNS, compute_features, load_inputs, validate_customer, validate_loan
from ml.generate_data import generate
from ml.layouts import CUSTREC, LOANREC


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    out = tmp_path_factory.mktemp("gen")
    manifest = generate(250, 7, out)
    return out, manifest


def test_every_record_has_its_lrecl(data):
    out, _ = data
    for name, lrecl in {"custmast.txt": 100, "loanmast.txt": 80, "repayhst.txt": 80, "txnsumm.txt": 80}.items():
        lines = (out / name).read_text().splitlines()
        assert lines and all(len(l) == lrecl for l in lines), name


def test_generator_is_deterministic(data, tmp_path):
    out, manifest = data
    again = generate(250, 7, tmp_path)
    assert again["records"] == manifest["records"]
    assert (tmp_path / "repayhst.txt").read_text() == (out / "repayhst.txt").read_text()


def test_injected_customer_defects_are_rejected(data):
    out, manifest = data
    custs = [CUSTREC.parse(l) for l in (out / "custmast.txt").read_text().splitlines()]
    by_id = {}
    for c in custs:
        by_id.setdefault(c["cust_id"], []).append(c)
    for d in manifest["defects"]:
        if d["file"] == "CUSTMAST" and d["code"].startswith("C"):
            codes = {validate_customer(c) for c in by_id[d["key"]]}
            assert d["code"] in codes, d


def test_injected_loan_defects_are_rejected(data):
    out, manifest = data
    loans = {LOANREC.parse(l)["loan_id"]: LOANREC.parse(l) for l in (out / "loanmast.txt").read_text().splitlines()}
    for d in manifest["defects"]:
        if d["file"] == "LOANMAST" and d["code"].startswith("L"):
            assert validate_loan(loans[d["key"]]) == d["code"], d


def test_train_mode_has_labels_score_mode_does_not(data):
    out, _ = data
    inputs = load_inputs(out)
    train = compute_features(inputs, 20260331, "TRAIN")
    score = compute_features(inputs, 20260930, "SCORE")
    assert train and score
    assert {r["label_stress_90d"] for r in train} <= {"0", "1"}
    assert {r["label_stress_90d"] for r in score} == {""}
    assert list(train[0]) == FEATURE_COLUMNS


def test_features_only_use_data_up_to_asof(data):
    """Changing anything after the as-of date must not change the features (no leakage)."""
    out, _ = data
    inputs = load_inputs(out)
    before = compute_features(inputs, 20260331, "SCORE")
    for t in inputs["txn"]:
        if t["yyyymm"] and t["yyyymm"] > 202603:
            t["debits"] = (t["debits"] or 0) * 3
    for r in inputs["repay"]:
        if r["due_date"] and r["due_date"] > 20260331:
            r["status"], r["dpd"] = "M", 120
    assert compute_features(inputs, 20260331, "SCORE") == before


def test_manifest_written(data):
    out, manifest = data
    assert json.loads((out / "manifest.json").read_text())["records"] == manifest["records"]
