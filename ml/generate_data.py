"""Synthetic, reproducible bank data in the exact fixed-width formats of the mainframe copybooks.

Every customer is simulated month by month. A minority go through a "stress episode"
(income shock and/or expense surge). Spending and balances deteriorate a few months
*before* repayments start failing, which is the early-warning signal the model learns.

About 1-2% deliberately bad records are injected (non-numeric fields, invalid dates,
duplicate IDs, orphans) so the DFSORT/COBOL validation steps have something to catch.
The manifest written next to the files lists every injected defect.

Usage:  python -m ml.generate_data --customers 1500 --seed 42 --out data/input
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

from ml.layouts import CUSTREC, LOANREC, REPAYREC, TXNREC

HISTORY_START = date(2024, 10, 1)  # first month of account history
DATA_END = date(2026, 9, 30)       # extraction date: nothing after this exists yet

FIRST = ["Aarav", "Vivaan", "Aditya", "Arjun", "Sai", "Reyansh", "Ishaan", "Kabir", "Rohan", "Karan",
         "Ananya", "Diya", "Priya", "Isha", "Kavya", "Meera", "Neha", "Pooja", "Riya", "Sneha",
         "Rahul", "Vikram", "Amit", "Suresh", "Deepak", "Nikhil", "Sanjay", "Anjali", "Lakshmi", "Fatima",
         "Imran", "Farhan", "Gurpreet", "Harpreet", "Joseph", "Maria", "Tanvi", "Yash", "Om", "Zoya"]
LAST = ["Sharma", "Verma", "Patel", "Shah", "Nair", "Iyer", "Reddy", "Rao", "Kulkarni", "Deshpande",
        "Joshi", "Gupta", "Agarwal", "Singh", "Kaur", "Khan", "Sheikh", "Das", "Bose", "Mukherjee",
        "Menon", "Pillai", "Pawar", "Patil", "Shirode", "Jain", "Mehta", "Chopra", "Kapoor", "Fernandes"]
CITIES = ["Mumbai", "Pune", "Bengaluru", "Hyderabad", "Chennai", "Delhi", "Kolkata", "Ahmedabad",
          "Jaipur", "Lucknow", "Nagpur", "Indore", "Kochi", "Surat", "Nashik", "Coimbatore"]
LOAN_TYPES = {"H": (240, 8.5, 9.5), "C": (60, 9.0, 11.0), "P": (36, 11.5, 16.0), "E": (84, 9.5, 12.0)}


def month_add(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, 1)


def emi(principal: float, annual_rate: float, months: int) -> float:
    r = annual_rate / 1200
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


class Customer:
    def __init__(self, idx: int, rng: random.Random):
        self.rng = rng
        self.cust_id = f"CUST{idx:04d}"
        self.name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        self.city = rng.choice(CITIES)
        self.emp_type = rng.choices("SEB", weights=[70, 20, 10])[0]
        self.age = rng.randint(23, 62)
        self.income = round(min(max(rng.lognormvariate(10.9, 0.45), 18000), 600000), -2)
        # Latent financial fragility drives credit score, EMI burden and the chance of an episode.
        self.fragility = rng.betavariate(2, 5)
        self.credit_score = int(min(900, max(300, rng.gauss(790 - 260 * self.fragility, 35))))
        self.open_date = date(rng.randint(2012, 2023), rng.randint(1, 12), rng.randint(1, 28))
        self.status = "A" if rng.random() > 0.01 else "C"
        self.spend_ratio = rng.uniform(0.40, 0.62) + 0.12 * self.fragility
        self.balance = self.income * rng.uniform(0.6, 3.0) * (1.2 - self.fragility)
        self.cc_base = rng.uniform(8, 45) + 25 * self.fragility
        # Stress episode: pre-warning months, then shock months.
        self.episode = None
        if rng.random() < 0.18 + 0.45 * self.fragility:
            start = rng.randint(2, 26)  # month index relative to HISTORY_START (may be after the window)
            self.episode = (start, rng.randint(4, 10), rng.choice(["income", "expense", "both"]))
        self.loans: list[dict] = []

    def stress(self, m: int) -> tuple[float, bool, float]:
        """Return (pre-warning ramp 0..1, in_shock, income_factor) for month index m."""
        if not self.episode:
            return 0.0, False, 1.0
        start, length, kind = self.episode
        if start - 3 <= m < start:
            return (m - (start - 4)) / 3, False, 1.0
        if start <= m < start + length:
            factor = 1.0
            if kind in ("income", "both"):
                factor = 0.0 if (self.emp_type == "S" and self.rng.random() < 0.65) else self.rng.uniform(0.25, 0.6)
            return 1.0, True, factor
        return 0.0, False, 1.0


def build_loans(c: Customer, rng: random.Random) -> None:
    n = rng.choices([1, 2, 3], weights=[55, 33, 12])[0]
    target_ratio = rng.uniform(0.12, 0.38) + 0.25 * c.fragility
    remaining_emi = c.income * target_ratio
    for seq in range(1, n + 1):
        ltype = rng.choices("HCPE", weights=[30, 30, 30, 10])[0]
        max_tenure, rlo, rhi = LOAN_TYPES[ltype]
        tenure = rng.choice([t for t in (12, 24, 36, 48, 60, 84, 120, 180, 240) if t <= max_tenure])
        rate = round(rng.uniform(rlo, rhi), 2)
        share = remaining_emi if seq == n else remaining_emi * rng.uniform(0.3, 0.7)
        remaining_emi -= share
        share = max(share, 1500)
        r = rate / 1200
        principal = round(share * ((1 + r) ** tenure - 1) / (r * (1 + r) ** tenure), -3)
        principal = max(principal, 25000)
        # Start so that most loans are running inside the history window; some start inside it.
        start = month_add(HISTORY_START, rng.randint(-min(tenure - 6, 60), 20))
        start = start.replace(day=rng.randint(1, 28))
        c.loans.append({
            "loan_id": f"LN{int(c.cust_id[4:]):05d}{seq:03d}", "cust_id": c.cust_id, "loan_type": ltype,
            "principal": principal, "int_rate": rate, "tenure": tenure, "start_date": start,
            "emi_amt": round(emi(principal, rate, tenure), 2), "due_day": rng.randint(1, 28),
            "status": "A", "consecutive_missed": 0,
        })


def simulate(c: Customer, rng: random.Random):
    """Yield (txn_month_values, [repayment records]) for every history month."""
    months = (DATA_END.year - HISTORY_START.year) * 12 + DATA_END.month - HISTORY_START.month + 1
    txns, repays = [], []
    balance = c.balance
    for m in range(months):
        mstart = month_add(HISTORY_START, m)
        ramp, shock, inc_factor = c.stress(m)
        salary = c.income * inc_factor
        if c.emp_type != "S":
            salary *= rng.uniform(0.8, 1.2)
        salary = round(salary, 2) if salary > 0 else 0.0
        other_credit = round(c.income * rng.uniform(0, 0.08), 2)
        credits = salary + other_credit
        surge = 0.0
        if c.episode and c.episode[2] in ("expense", "both"):
            surge = 0.30 * ramp + (0.25 if shock else 0)
        spend = c.income * c.spend_ratio * (1 + 0.30 * ramp + surge + rng.uniform(-0.06, 0.06))
        if shock and inc_factor < 0.5:
            spend *= 0.85  # people cut back a little, not enough
        start_bal = balance
        balance += credits
        low = balance
        balance -= spend * 0.5
        low = min(low, balance)
        bounces = 0
        emi_paid_total = 0.0
        for ln in c.loans:
            inst_no = (mstart.year - ln["start_date"].year) * 12 + mstart.month - ln["start_date"].month
            if inst_no < 1 or inst_no > ln["tenure"]:
                continue
            due = date(mstart.year, mstart.month, ln["due_day"])
            if due > DATA_END:
                continue
            amt = ln["emi_amt"]
            risk = 0.008 + 0.03 * c.fragility + 0.30 * ramp * (1 if shock else 0.35)
            if balance >= amt and rng.random() > risk:
                status, dpd, paid_amt = "P", 0, amt
                if rng.random() < 0.02 + 0.30 * ramp:
                    status, dpd = "L", rng.randint(1, 9)
            elif balance >= amt * 0.5 and rng.random() < 0.35:
                status, dpd, paid_amt = "R", rng.randint(10, 45), round(balance * 0.9 if balance < amt else amt * 0.6, 2)
            elif rng.random() < 0.55 and not (shock and ln["consecutive_missed"] >= 1):
                status, dpd, paid_amt = "B", rng.randint(6, 40), amt
                bounces += 1
            elif balance >= amt:
                status, dpd, paid_amt = "L", rng.randint(10, 35), amt
            else:
                status, dpd, paid_amt = "M", 0, 0.0
                bounces += 1
            if status == "M":
                ln["consecutive_missed"] += 1
                paid_date = None
                dpd = min(999, (DATA_END - due).days)
            else:
                ln["consecutive_missed"] = 0
                paid_date = due + timedelta(days=dpd)
                if paid_date > DATA_END:  # not yet paid at extraction time
                    paid_date, paid_amt, status = None, 0.0, "M"
                    dpd = (DATA_END - due).days
            if ln["consecutive_missed"] >= 3:
                ln["status"] = "D"
            balance -= paid_amt
            emi_paid_total += paid_amt
            low = min(low, balance)
            if due >= HISTORY_START:
                repays.append({
                    "loan_id": ln["loan_id"], "cust_id": c.cust_id, "inst_no": inst_no,
                    "due_date": int(due.strftime("%Y%m%d")),
                    "paid_date": int(paid_date.strftime("%Y%m%d")) if paid_date else 0,
                    "due_amt": amt, "paid_amt": paid_amt, "dpd": dpd, "status": status,
                })
        balance -= spend * 0.5
        balance = max(balance, 0.0)
        if balance > 4 * c.income:  # surplus swept to a fixed deposit (not a spend debit)
            balance -= (balance - 4 * c.income) * 0.5
        low = max(min(low, balance), 0.0)
        if shock and rng.random() < 0.3:
            bounces += 1  # other auto-debits failing
        debits = spend + emi_paid_total
        txns.append({
            "cust_id": c.cust_id, "yyyymm": mstart.year * 100 + mstart.month,
            "credits": round(credits, 2), "debits": round(debits, 2), "salary": salary,
            "min_bal": round(low, 2), "avg_bal": round(max((start_bal + balance) / 2, 0), 2),
            "bounces": min(bounces, 99),
            "cc_util": round(min(c.cc_base + 35 * ramp + rng.uniform(-5, 5), 100), 2),
        })
    for ln in c.loans:
        last_inst = month_add(ln["start_date"].replace(day=1), ln["tenure"])
        if ln["status"] != "D" and last_inst <= DATA_END.replace(day=1):
            ln["status"] = "C"
    return txns, repays


def generate(customers: int, seed: int, out: Path) -> dict:
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    cust_lines, loan_lines, repay_lines, txn_lines = [], [], [], []
    for i in range(1, customers + 1):
        c = Customer(i, rng)
        build_loans(c, rng)
        txns, repays = simulate(c, rng)
        cust_lines.append(CUSTREC.format({
            "cust_id": c.cust_id, "cust_name": c.name, "city": c.city, "emp_type": c.emp_type,
            "age": c.age, "monthly_income": c.income, "credit_score": c.credit_score,
            "open_date": int(c.open_date.strftime("%Y%m%d")), "status": c.status,
        }))
        for ln in c.loans:
            paid = sum(1 for r in repays if r["loan_id"] == ln["loan_id"] and r["status"] != "M")
            elapsed = max(0, min(ln["tenure"], (DATA_END.year - ln["start_date"].year) * 12
                                 + DATA_END.month - ln["start_date"].month))
            outstanding = max(0.0, ln["principal"] * (1 - elapsed / ln["tenure"]) * 1.02) if paid else ln["principal"]
            loan_lines.append(LOANREC.format({
                **ln, "start_date": int(ln["start_date"].strftime("%Y%m%d")), "outstanding": round(outstanding, 2),
            }))
        repay_lines += [REPAYREC.format(r) for r in repays]
        txn_lines += [TXNREC.format(t) for t in txns]

    defects = inject_defects(rng, cust_lines, loan_lines, repay_lines, txn_lines)
    # Files are written in random order on purpose: DFSORT sorts them on the mainframe.
    for lines in (cust_lines, loan_lines, repay_lines, txn_lines):
        rng.shuffle(lines)
    files = {"custmast.txt": cust_lines, "loanmast.txt": loan_lines,
             "repayhst.txt": repay_lines, "txnsumm.txt": txn_lines}
    for name, lines in files.items():
        (out / name).write_text("\n".join(lines) + "\n", encoding="ascii")
    manifest = {
        "customers": customers, "seed": seed,
        "history_start": HISTORY_START.isoformat(), "data_end": DATA_END.isoformat(),
        "records": {name: len(lines) for name, lines in files.items()},
        "defects": defects,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def _set(line: str, layout, field: str, raw: str) -> str:
    pos, length = layout.offsets()[field]
    return line[: pos - 1] + raw[:length].ljust(length) + line[pos - 1 + length:]


def inject_defects(rng, cust, loan, repay, txn) -> list[dict]:
    """Corrupt ~1.5% of records. Each defect maps to the reason code that must catch it."""
    defects = []
    n_cust = max(4, len(cust) // 60)

    def pick(lines, k):
        return rng.sample(range(len(lines)), k)

    cust_defects = [
        ("age", "4A2", "C02"), ("age", "017", "C03"), ("monthly_income", "000000000", "C04"),
        ("credit_score", "950", "C05"), ("open_date", "20231345", "C06"), ("emp_type", "X", "C07"),
        ("status", "Z", "C08"),
    ]
    for n, i in enumerate(pick(cust, n_cust)):
        field, raw, code = cust_defects[n % len(cust_defects)]
        cust[i] = _set(cust[i], CUSTREC, field, raw)
        defects.append({"file": "CUSTMAST", "key": cust[i][:8], "code": code, "step": "EWSVCUST"})
    # Duplicate customer IDs: DFSORT keeps the first and diverts the rest to EWS.CUST.DUPS.
    for i in pick(cust, max(2, len(cust) // 400)):
        dup = _set(cust[i], CUSTREC, "cust_name", "DUPLICATE ENTRY")
        cust.append(dup)
        defects.append({"file": "CUSTMAST", "key": dup[:8], "code": "DUP", "step": "DFSORT SRTCUST"})

    # Orphan loan: customer does not exist -> EWSMATCH exception M01.
    orphan = _set(_set(loan[0], LOANREC, "cust_id", "CUSTX999"), LOANREC, "loan_id", "LNX9999001")
    loan.append(orphan)
    defects.append({"file": "LOANMAST", "key": "LNX9999001", "code": "M01", "step": "EWSMATCH"})
    loan_defects = [("emi_amt", "000000000", "L04"), ("tenure", "000", "L05"),
                    ("start_date", "20250231", "L06"), ("loan_type", "Q", "L02"), ("status", "Z", "L08")]
    for n, i in enumerate(pick(loan, max(3, len(loan) // 80))):
        field, raw, code = loan_defects[n % len(loan_defects)]
        loan[i] = _set(loan[i], LOANREC, field, raw)
        defects.append({"file": "LOANMAST", "key": loan[i][:10], "code": code, "step": "EWSVLOAN"})

    txn.append(_set(txn[0], TXNREC, "cust_id", "CUSTX998"))
    defects.append({"file": "TXNSUMM", "key": "CUSTX998", "code": "M03", "step": "EWSMATCH"})
    for i in pick(repay, max(3, len(repay) // 250)):
        repay[i] = _set(repay[i], REPAYREC, "paid_amt", "12A45O000")
        defects.append({"file": "REPAYHST", "key": repay[i][:10], "code": "S01", "step": "DFSORT SRTREPAY"})
    for i in pick(txn, max(3, len(txn) // 250)):
        txn[i] = _set(txn[i], TXNREC, "debits", "N/A      ")
        defects.append({"file": "TXNSUMM", "key": txn[i][:8], "code": "S02", "step": "DFSORT SRTTXN"})
    return defects


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--customers", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "input")
    a = ap.parse_args()
    m = generate(a.customers, a.seed, a.out)
    print(json.dumps({k: v for k, v in m.items() if k != "defects"}, indent=2), f"\ndefects: {len(m['defects'])}")


if __name__ == "__main__":
    main()
