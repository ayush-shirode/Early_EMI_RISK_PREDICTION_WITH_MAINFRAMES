"""Fixed-width record layouts that mirror the COBOL copybooks in mainframe/copybooks.

These are the data contract between Python and z/OS. Every file that crosses the
boundary uses display (zoned) numerics only, so Zowe's text-mode ASCII<->EBCDIC
conversion is lossless. tests/test_layouts.py checks these against the copybooks.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class Field:
    name: str
    length: int
    kind: str = "X"  # "X" = text, "9" = unsigned zoned decimal
    scale: int = 0   # implied decimal places for "9" fields


@dataclass(frozen=True)
class Layout:
    name: str
    copybook: str
    lrecl: int
    fields: tuple[Field, ...]

    @property
    def used(self) -> int:
        return sum(f.length for f in self.fields)

    def offsets(self) -> dict[str, tuple[int, int]]:
        """1-based start position and length of every field (as DFSORT sees them)."""
        pos, out = 1, {}
        for f in self.fields:
            out[f.name] = (pos, f.length)
            pos += f.length
        return out

    def format(self, values: dict) -> str:
        parts = []
        for f in self.fields:
            v = values.get(f.name)
            if f.kind == "X":
                s = "" if v is None else str(v)
                parts.append(s[: f.length].ljust(f.length))
            else:
                q = Decimal(str(v if v is not None else 0)).quantize(
                    Decimal(1).scaleb(-f.scale), rounding=ROUND_HALF_UP
                )
                if q < 0:
                    raise ValueError(f"{self.name}.{f.name}: negative value {v} not allowed")
                digits = str(int(q.scaleb(f.scale)))
                if len(digits) > f.length:
                    raise ValueError(f"{self.name}.{f.name}: {v} does not fit PIC 9 length {f.length}")
                parts.append(digits.zfill(f.length))
        rec = "".join(parts).ljust(self.lrecl)
        assert len(rec) == self.lrecl
        return rec

    def parse(self, line: str) -> dict:
        line = line.rstrip("\r\n").ljust(self.lrecl)
        out, pos = {}, 0
        for f in self.fields:
            raw = line[pos : pos + f.length]
            pos += f.length
            if f.kind == "X":
                out[f.name] = raw.rstrip()
            elif raw.strip().isdigit():
                out[f.name] = int(raw) / (10**f.scale) if f.scale else int(raw)
            else:
                out[f.name] = None
        return out


def X(name: str, n: int) -> Field:
    return Field(name, n, "X")


def N(name: str, digits: int, scale: int = 0) -> Field:
    """PIC 9(digits-scale)V9(scale): `digits` is the total stored length."""
    return Field(name, digits, "9", scale)


CUSTREC = Layout("CUSTREC", "CUSTREC.cpy", 100, (
    X("cust_id", 8), X("cust_name", 30), X("city", 20), X("emp_type", 1),
    N("age", 3), N("monthly_income", 9, 2), N("credit_score", 3),
    N("open_date", 8), X("status", 1), X("filler", 17),
))

LOANREC = Layout("LOANREC", "LOANREC.cpy", 80, (
    X("loan_id", 10), X("cust_id", 8), X("loan_type", 1),
    N("principal", 11, 2), N("int_rate", 4, 2), N("tenure", 3),
    N("start_date", 8), N("emi_amt", 9, 2), N("due_day", 2),
    N("outstanding", 11, 2), X("status", 1), X("filler", 12),
))

REPAYREC = Layout("REPAYREC", "REPAYREC.cpy", 80, (
    X("loan_id", 10), X("cust_id", 8), N("inst_no", 3), N("due_date", 8),
    N("paid_date", 8), N("due_amt", 9, 2), N("paid_amt", 9, 2), N("dpd", 3),
    X("status", 1), X("filler", 21),
))

TXNREC = Layout("TXNREC", "TXNREC.cpy", 80, (
    X("cust_id", 8), N("yyyymm", 6), N("credits", 9, 2), N("debits", 9, 2),
    N("salary", 9, 2), N("min_bal", 9, 2), N("avg_bal", 9, 2), N("bounces", 2),
    N("cc_util", 5, 2), X("filler", 14),
))

SCOREREC = Layout("SCOREREC", "SCOREREC.cpy", 80, (
    X("cust_id", 8), N("asof", 8), N("prob", 5, 4), X("tier", 6), X("action", 4),
    X("top_factor", 30), N("total_emi", 9, 2), X("filler", 10),
))

# Latest score per customer in the VSAM KSDS EWS.SCORKSDS (key = cust_id), kept by EWSSUPD.
SCOREVS = Layout("SCOREVS", "SCOREVS.cpy", 100, (
    X("cust_id", 8), N("asof", 8), N("prob", 5, 4), X("tier", 6), X("action", 4),
    X("top_factor", 30), N("total_emi", 9, 2), N("prev_asof", 8), N("prev_prob", 5, 4),
    X("prev_tier", 6), N("times_scored", 4), X("filler", 7),
))

REJREC = Layout("REJREC", "REJREC.cpy", 120, (
    X("source", 8), X("key", 10), X("reason_code", 4), X("reason_text", 40), X("data", 58),
))

# FEATREC is produced by COBOL with numeric-edited PICs and converted to CSV by DFSORT.
# Python only reads the CSV; this tuple fixes the column order and the field widths
# that mainframe/sortcntl/FEAT2CSV relies on (checked in tests).
FEATURE_FIELDS: tuple[tuple[str, int], ...] = (
    ("cust_id", 8), ("as_of_date", 8), ("emp_type", 1), ("age", 3),
    ("monthly_income", 10), ("credit_score", 3), ("active_loans", 2),
    ("total_emi", 10), ("emi_to_income", 7), ("tenure_remaining", 3),
    ("inst_due_12m", 3), ("late_cnt_3m", 2), ("late_cnt_12m", 2),
    ("missed_cnt_12m", 2), ("partial_cnt_12m", 2), ("emi_bounce_6m", 2),
    ("txn_bounce_6m", 2), ("max_dpd_12m", 3), ("avg_dpd_6m", 6), ("dpd_trend", 7),
    ("avg_balance_3m", 10), ("min_balance_3m", 10), ("balance_trend_pct", 8),
    ("savings_to_emi", 7), ("salary_missing_6m", 1), ("debit_credit_ratio_3m", 8),
    ("spend_trend_pct", 8), ("cc_util_avg_3m", 6), ("label_stress_90d", 1),
)
FEATREC_LRECL = 200

INPUT_LAYOUTS = {
    "CUSTMAST": CUSTREC,
    "LOANMAST": LOANREC,
    "REPAYHST": REPAYREC,
    "TXNSUMM": TXNREC,
}


def feat2csv_control() -> str:
    """DFSORT statements for member FEAT2CSV, derived from FEATURE_FIELDS.

    INREC inserts a comma after every FEATREC field, OUTFIL squeezes out the blanks
    left by numeric editing (SQZ), adds a header and writes variable-length records
    (FTOV + VLTRIM) so the CSV has no trailing blanks.
    """
    pos, items = 1, []
    for i, (_, length) in enumerate(FEATURE_FIELDS):
        items.append(f"{pos},{length}")
        if i < len(FEATURE_FIELDS) - 1:
            items.append("C','")
        pos += length
    csv_len = pos - 1 + len(FEATURE_FIELDS) - 1
    header = ",".join(name for name, _ in FEATURE_FIELDS)

    def wrap(prefix: str, parts: list[str], indent: str = "               ") -> list[str]:
        lines, cur = [], prefix
        for p in parts:
            if len(cur) + len(p) + 1 > 69:
                lines.append(cur)
                cur = indent
            cur += p + ","
        lines.append(cur)
        return lines

    chunks = [header[i:i + 48] for i in range(0, len(header), 48)]
    out = [
        "* FEAT2CSV - TURN FIXED-WIDTH FEATURE RECORDS (FEATREC) INTO CSV",
        "*  INREC  : PUT A COMMA AFTER EVERY FIELD",
        "*  OUTFIL : SQUEEZE OUT THE BLANKS OF THE EDITED NUMBERS, ADD THE",
        "*           HEADER LINE, WRITE VARIABLE-LENGTH RECORDS (FTOV) AND",
        "*           TRIM TRAILING BLANKS (VLTRIM)",
        "* GENERATED FROM ml/layouts.py FEATURE_FIELDS - DO NOT EDIT BY HAND",
        "  OPTION COPY",
    ]
    inrec = wrap("  INREC BUILD=(", items)
    inrec[-1] = inrec[-1].rstrip(",") + ")"
    out += inrec
    out.append("  OUTFIL FNAMES=SORTOUT,FTOV,VLTRIM=C' ',REMOVECC,")
    hdr = wrap("    HEADER1=(", [f"C'{c}'" for c in chunks], indent="             ")
    hdr[-1] = hdr[-1].rstrip(",") + "),"
    out += hdr
    out.append(f"    BUILD=(1,{csv_len},SQZ=(SHIFT=LEFT),300X)")
    return "\n".join(out) + "\n"
