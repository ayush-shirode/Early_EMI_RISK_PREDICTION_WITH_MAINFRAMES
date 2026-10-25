"""The Python layouts, the COBOL copybooks and the DFSORT positions must agree byte for byte."""
import re

import pytest

from ml import layouts
from ml.layouts import FEATREC_LRECL, FEATURE_FIELDS, feat2csv_control
from tests.conftest import ROOT

MF = ROOT / "mainframe"


def pic_length(pic: str) -> int:
    pic = re.sub(r"(.)\((\d+)\)", lambda m: m.group(1) * int(m.group(2)), pic.upper())
    return len(pic.replace("V", "").replace("S", ""))


def copybook_fields(name: str) -> list[int]:
    out = []
    for line in (MF / "copybooks" / name).read_text().splitlines():
        if len(line) > 6 and line[6] == "*":
            continue
        m = re.search(r"\bPIC\s+(\S+?)\.?(\s|$)", line)
        if m:
            out.append(pic_length(m.group(1).rstrip(".")))
    return out


@pytest.mark.parametrize("layout", [layouts.CUSTREC, layouts.LOANREC, layouts.REPAYREC,
                                    layouts.TXNREC, layouts.SCOREREC, layouts.REJREC])
def test_layout_matches_copybook(layout):
    assert [f.length for f in layout.fields] == copybook_fields(layout.copybook)
    assert layout.used == layout.lrecl


def test_featrec_matches_feature_fields():
    lengths = copybook_fields("FEATREC.cpy")
    assert lengths[:-1] == [n for _, n in FEATURE_FIELDS]
    assert sum(lengths) == FEATREC_LRECL


def test_feat2csv_member_is_generated_from_layouts():
    assert (MF / "sortcntl" / "FEAT2CSV").read_text() == feat2csv_control()


def test_format_parse_roundtrip():
    rec = {"cust_id": "CUST0001", "cust_name": "Test Name", "city": "Pune", "emp_type": "S", "age": 30,
           "monthly_income": 51234.5, "credit_score": 712, "open_date": 20200115, "status": "A"}
    line = layouts.CUSTREC.format(rec)
    assert len(line) == 100
    back = layouts.CUSTREC.parse(line)
    assert back["monthly_income"] == 51234.5 and back["age"] == 30 and back["cust_name"] == "Test Name"


def test_format_rejects_overflow_and_negatives():
    with pytest.raises(ValueError):
        layouts.TXNREC.format({"cust_id": "X", "credits": 10_000_000})
    with pytest.raises(ValueError):
        layouts.TXNREC.format({"cust_id": "X", "credits": -1})


@pytest.mark.parametrize("folder,limit", [("cobol", 72), ("copybooks", 80), ("jcl", 71), ("sortcntl", 71), ("rexx", 72)])
def test_source_lines_fit_fixed_columns(folder, limit):
    for f in (MF / folder).iterdir():
        for n, line in enumerate(f.read_text().splitlines(), 1):
            assert len(line) <= limit, f"{f.name}:{n} is {len(line)} columns"
            assert line.isascii(), f"{f.name}:{n} has non-ASCII text (EBCDIC conversion would break it)"


def test_cobol_code_stays_out_of_sequence_area():
    for f in (MF / "cobol").iterdir():
        for n, line in enumerate(f.read_text().splitlines(), 1):
            if len(line) > 6 and line[6] != "*":
                assert len(line.rstrip()) <= 72, f"{f.name}:{n}"
