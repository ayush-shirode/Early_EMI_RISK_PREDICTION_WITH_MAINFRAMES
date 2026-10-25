"""Python reference implementation of the EWSBATCH rules (DFSORT + EWSVCUST + EWSVLOAN + EWSMATCH).

It is *not* used in the normal flow: the mainframe computes the features. It exists to
  1. verify the mainframe output (tests compare FEATCSV with this, field by field), and
  2. let the ML code be developed and tested without a mainframe connection.
Any change to the COBOL rules must be mirrored here, and vice versa.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from ml.layouts import CUSTREC, FEATURE_FIELDS, LOANREC, REPAYREC, TXNREC

FEATURE_COLUMNS = [name for name, _ in FEATURE_FIELDS]


def _valid_date(n) -> bool:
    if not isinstance(n, int):
        return False
    try:
        date(n // 10000, n // 100 % 100, n % 100)
        return n // 10000 >= 1601
    except ValueError:
        return False


def _int_date(n: int) -> int:
    return date(n // 10000, n // 100 % 100, n % 100).toordinal()


def _r(x: float, places: int) -> float:
    return float(Decimal(str(x)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def validate_customer(c: dict) -> str | None:
    if not c["cust_id"].strip():
        return "C01"
    if c["age"] is None:
        return "C02"
    if not 21 <= c["age"] <= 75:
        return "C03"
    if not c["monthly_income"]:
        return "C04"
    if c["credit_score"] is None or not 300 <= c["credit_score"] <= 900:
        return "C05"
    if not _valid_date(c["open_date"]):
        return "C06"
    if c["emp_type"] not in ("S", "E", "B"):
        return "C07"
    if c["status"] not in ("A", "C"):
        return "C08"
    return None


def validate_loan(ln: dict) -> str | None:
    if not ln["loan_id"].strip() or not ln["cust_id"].strip():
        return "L01"
    if ln["loan_type"] not in ("H", "C", "P", "E"):
        return "L02"
    if not ln["principal"]:
        return "L03"
    if not ln["emi_amt"]:
        return "L04"
    if ln["tenure"] is None or not 1 <= ln["tenure"] <= 360:
        return "L05"
    if not _valid_date(ln["start_date"]):
        return "L06"
    if ln["due_day"] is None or not 1 <= ln["due_day"] <= 28:
        return "L07"
    if ln["status"] not in ("A", "C", "D"):
        return "L08"
    if ln["int_rate"] is None or ln["outstanding"] is None:
        return "L09"
    return None


def _all_numeric(rec: dict, layout) -> bool:
    return all(rec[f.name] is not None for f in layout.fields if f.kind == "9")


def load_inputs(data_dir: Path) -> dict:
    def read(name, layout):
        return [layout.parse(l) for l in (data_dir / name).read_text().splitlines() if l.strip()]
    return {
        "cust": read("custmast.txt", CUSTREC), "loan": read("loanmast.txt", LOANREC),
        "repay": read("repayhst.txt", REPAYREC), "txn": read("txnsumm.txt", TXNREC),
    }


def compute_features(inputs: dict, asof: int, mode: str = "SCORE") -> list[dict]:
    # STEP010: dedupe customers, keep first occurrence (DFSORT OPTION EQUALS + SUM FIELDS=NONE)
    seen, custs = set(), []
    for c in inputs["cust"]:
        if c["cust_id"] not in seen:
            seen.add(c["cust_id"])
            custs.append(c)
    # STEP030/040: DFSORT numeric checks
    repays = [r for r in inputs["repay"] if _all_numeric(r, REPAYREC)]
    txns = [t for t in inputs["txn"] if _all_numeric(t, TXNREC)]
    # STEP050/060: COBOL validation
    custs = [c for c in custs if validate_customer(c) is None]
    loans = [ln for ln in inputs["loan"] if validate_loan(ln) is None]

    asof_int = _int_date(asof)
    asof_idx = (asof // 10000) * 12 + asof // 100 % 100
    by_cust_loans: dict[str, list] = {}
    for ln in loans:
        by_cust_loans.setdefault(ln["cust_id"], []).append(ln)
    by_cust_repay: dict[str, list] = {}
    for r in repays:
        by_cust_repay.setdefault(r["cust_id"], []).append(r)
    by_cust_txn: dict[str, list] = {}
    for t in txns:
        by_cust_txn.setdefault(t["cust_id"], []).append(t)

    rows = []
    for c in sorted(custs, key=lambda c: c["cust_id"].encode("cp037")):
        cid = c["cust_id"]
        my_loans = by_cust_loans.get(cid, [])[:20]
        loan_ids = {ln["loan_id"] for ln in my_loans}
        active, total_emi, tenure_max = 0, 0.0, 0
        for ln in my_loans:
            sd = ln["start_date"]
            elapsed = asof_idx - ((sd // 10000) * 12 + sd // 100 % 100)
            if sd <= asof and elapsed < ln["tenure"]:
                active += 1
                total_emi += ln["emi_amt"]
                tenure_max = max(tenure_max, ln["tenure"] - elapsed)

        a = dict(inst12=0, late3=0, late12=0, missed12=0, partial12=0, bounce6=0, maxdpd=0,
                 dsum6=0, dn6=0, dsum_r=0, dn_r=0, dsum_p=0, dn_p=0)
        in_default, label = False, "0" if mode == "TRAIN" else ""
        for r in by_cust_repay.get(cid, []):
            if r["loan_id"] not in loan_ids:
                continue
            if not _valid_date(r["due_date"]) or (r["paid_date"] and not _valid_date(r["paid_date"])):
                continue
            due = r["due_date"]
            m_ago = asof_idx - ((due // 10000) * 12 + due // 100 % 100)
            if due <= asof:
                if r["paid_date"] and r["paid_date"] <= asof:
                    dpd, st = r["dpd"], r["status"]
                else:
                    dpd = asof_int - _int_date(due)
                    st = "M" if dpd > 30 else "L" if dpd > 0 else "P"
                    if dpd >= 90:
                        in_default = True
                dpd = min(dpd, 999)
                if m_ago <= 11:
                    a["inst12"] += 1
                    a["maxdpd"] = max(a["maxdpd"], dpd)
                    if st == "L":
                        a["late12"] += 1
                        if m_ago <= 2:
                            a["late3"] += 1
                    elif st == "M":
                        a["missed12"] += 1
                    elif st == "R":
                        a["partial12"] += 1
                    elif st == "B" and m_ago <= 5:
                        a["bounce6"] += 1
                if m_ago <= 5:
                    a["dsum6"] += dpd
                    a["dn6"] += 1
                    if m_ago <= 2:
                        a["dsum_r"] += dpd
                        a["dn_r"] += 1
                    else:
                        a["dsum_p"] += dpd
                        a["dn_p"] += 1
            elif mode == "TRAIN" and _int_date(due) <= asof_int + 90:
                if r["status"] in ("M", "B") or r["dpd"] >= 30:
                    label = "1"

        t = dict(nr=0, np=0, bal_r=0.0, bal_p=0.0, cred_r=0.0, deb_r=0.0, deb_p=0.0, cc=0.0,
                 minbal=0.0, tb6=0, salmiss=0)
        for x in by_cust_txn.get(cid, []):
            ym = x["yyyymm"]
            m_ago = asof_idx - ((ym // 100) * 12 + ym % 100)
            if not 0 <= m_ago <= 5:
                continue
            t["tb6"] += x["bounces"]
            if x["salary"] == 0:
                t["salmiss"] += 1
            if m_ago <= 2:
                t["nr"] += 1
                t["bal_r"] += x["avg_bal"]
                t["cred_r"] += x["credits"]
                t["deb_r"] += x["debits"]
                t["cc"] += x["cc_util"]
                t["minbal"] = x["min_bal"] if t["nr"] == 1 else min(t["minbal"], x["min_bal"])
            else:
                t["np"] += 1
                t["bal_p"] += x["avg_bal"]
                t["deb_p"] += x["debits"]

        if c["status"] != "A" or active == 0 or in_default:
            continue

        def clamp(v, hi, lo=0.0):
            return max(lo, min(hi, v))

        avg_r = a["dsum_r"] / a["dn_r"] if a["dn_r"] else 0.0
        avg_p = a["dsum_p"] / a["dn_p"] if a["dn_p"] else 0.0
        bal3 = t["bal_r"] / t["nr"] if t["nr"] else 0.0
        balp = t["bal_p"] / t["np"] if t["np"] else 0.0
        debr = t["deb_r"] / t["nr"] if t["nr"] else 0.0
        debp = t["deb_p"] / t["np"] if t["np"] else 0.0
        if t["cred_r"] > 0:
            dcr = t["deb_r"] / t["cred_r"]
        else:
            dcr = 999.9999 if t["deb_r"] > 0 else 0.0
        rows.append({
            "cust_id": cid, "as_of_date": asof, "emp_type": c["emp_type"], "age": c["age"],
            "monthly_income": c["monthly_income"], "credit_score": c["credit_score"],
            "active_loans": active, "total_emi": _r(total_emi, 2),
            "emi_to_income": _r(clamp(total_emi / c["monthly_income"], 99.9999), 4),
            "tenure_remaining": tenure_max, "inst_due_12m": a["inst12"],
            "late_cnt_3m": a["late3"], "late_cnt_12m": a["late12"], "missed_cnt_12m": a["missed12"],
            "partial_cnt_12m": a["partial12"], "emi_bounce_6m": a["bounce6"], "txn_bounce_6m": min(t["tb6"], 99),
            "max_dpd_12m": a["maxdpd"],
            "avg_dpd_6m": _r(a["dsum6"] / a["dn6"], 2) if a["dn6"] else 0.0,
            "dpd_trend": _r(clamp(avg_r - avg_p, 999.99, -999.99), 2),
            "avg_balance_3m": _r(bal3, 2), "min_balance_3m": _r(t["minbal"], 2),
            "balance_trend_pct": _r(clamp((bal3 - balp) / balp * 100, 9999.99, -9999.99), 2) if balp > 0 else 0.0,
            "savings_to_emi": _r(clamp(bal3 / total_emi, 9999.99), 2),
            "salary_missing_6m": t["salmiss"],
            "debit_credit_ratio_3m": _r(clamp(dcr, 999.9999), 4),
            "spend_trend_pct": _r(clamp((debr - debp) / debp * 100, 9999.99, -9999.99), 2) if debp > 0 else 0.0,
            "cc_util_avg_3m": _r(t["cc"] / t["nr"], 2) if t["nr"] else 0.0,
            "label_stress_90d": label,
        })
    return rows
