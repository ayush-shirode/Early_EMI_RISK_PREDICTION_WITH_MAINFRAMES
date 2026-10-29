"""VSAM support without a mainframe: IDCAMS output parsing, keyed lookup, data set naming."""
import re

import pytest
from fastapi.testclient import TestClient

from ml.layouts import SCOREVS
from pipeline import actions, runner, zos
from pipeline.config import Names
from tests.conftest import ROOT

# Real IDCAMS PRINT ... HEX output for CUST0166 (z/OS 3.1, 2026-10-29), as z/OSMF returns it.
PRINT_HEX = [
    "PRINT INDATASET('Z72230.EWS.VSTEST') FROMKEY(CUST0166) TOKEY(CUST0167) HEX",
    "KEY OF RECORD - C3E4E2E3F0F1F6F6",
    "C3E4E2E3F0F1F6F6D28199819540C9A885994040404040404040404040404040404040404040D1818997A4994040404040404040404040404040E2F0",
    "F3F2F0F0F3F5F5F0F0F0F0F7F8F3F2F0F1F9F0F2F1F0C14040404040404040404040404040404040",
    "KEY OF RECORD - C3E4E2E3F0F1F6F7",
    "C3E4E2E3F0F1F6F7E29585888140D781A3859340404040404040404040404040404040404040D4A4948281894040404040404040404040404040C5F0",
    "F2F4F0F0F3F7F4F0F0F0F0F7F6F2F2F0F2F1F0F7F2F1C14040404040404040404040404040404040",
    "IDC0005I NUMBER OF RECORDS PROCESSED WAS 2",
]

LISTCAT = [
    "CLUSTER ------- Z72230.EWS.SCORKSDS",
    "       DATASET-OWNER-----(NULL)     CREATION--------2026.302",
    "   DATA ------- Z72230.EWS.SCORKSDS.DATA",
    "       KEYLEN-----------------8     AVGLRECL-------------100     BUFSPACE------------7168     CISIZE---------------512",
    "       RKP--------------------0     MAXLRECL-------------100     EXCPEXIT----------(NULL)     CI/CA----------------735",
    "       REC-TOTAL-----------1054     SPLITS-CI--------------0     EXCPS----------------426",
    "       REC-DELETED------------1     SPLITS-CA--------------0     EXTENTS----------------1",
    "       REC-INSERTED-----------0     FREESPACE-%CI----------0     SYSTEM-TIMESTAMP:",
    "       REC-UPDATED---------1023     FREESPACE-%CA----------0          X'DE51C6F0A1B2C3D4'",
    "       VOLSER------------ZXPC02     DEVTYPE------X'3010200F'     EXTENT-NUMBER----------1",
    "   INDEX ------ Z72230.EWS.SCORKSDS.INDEX",
    "       REC-TOTAL--------------1     SPLITS-CI--------------0     EXCPS------------------3",
]


def test_print_hex_records_decode_from_ebcdic():
    recs = [zos.ebcdic(b) for b in zos.parse_print_hex(PRINT_HEX)]
    assert len(recs) == 2 and all(len(r) == 100 for r in recs)
    assert recs[0].startswith("CUST0166Karan Iyer") and recs[0][58] == "S" and recs[0][82] == "A"
    assert recs[1][:8] == "CUST0167"


def test_listcat_statistics_come_from_the_data_component():
    lc = zos.parse_listcat(LISTCAT)
    assert lc["cluster"] == {"name": "Z72230.EWS.SCORKSDS", "created": "2026.302"}
    d = lc["data"]
    assert (d["rec-total"], d["rec-updated"], d["rec-deleted"], d["rec-inserted"]) == (1054, 1023, 1, 0)
    assert (d["keylen"], d["rkp"], d["cisize"], d["volser"]) == (8, 0, 512, "ZXPC02")
    assert lc["index"]["rec-total"] == 1


def test_key_not_found_is_an_empty_result_not_an_error(monkeypatch):
    def fail(*a, **k):
        raise zos.ZosError("IDCAMS completed with return code=12 ... NUMBER OF RECORDS PROCESSED WAS 0 ...")
    monkeypatch.setattr(zos, "idcams", fail)
    assert zos.vsam_read("Z.EWS.SCORKSDS", "CUST9999") == []
    with pytest.raises(zos.ZosError):
        zos.vsam_read("Z.EWS.SCORKSDS", "BAD KEY")


def test_vsam_customer_parses_both_records(monkeypatch):
    score = SCOREVS.format({"cust_id": "CUST0166", "asof": 20260930, "prob": 0.8811, "tier": "HIGH", "action": "INTV",
                            "top_factor": "SPEND-TO-INCOME (3 M)", "total_emi": 13312.41, "prev_asof": 20260831,
                            "prev_prob": 0.8924, "prev_tier": "HIGH", "times_scored": 2})
    cust = zos.ebcdic(zos.parse_print_hex(PRINT_HEX)[0])
    monkeypatch.setattr(actions, "hlq", lambda: "Z72230")
    monkeypatch.setattr(zos, "vsam_read", lambda dsn, key: [cust] if dsn.endswith("CUSTKSDS") else [score])
    r = actions.vsam_customer("cust0166")
    assert r["customer"]["cust_name"] == "Karan Iyer" and r["customer"]["credit_score"] == 783
    assert r["score"]["prob"] == 0.8811 and r["score"]["prev_prob"] == 0.8924 and r["score"]["times_scored"] == 2
    with pytest.raises(runner.ActionError):
        actions.vsam_customer("CUST01'; DELETE")


def test_program_counters_are_read_from_sysout(monkeypatch):
    sysout = (" EWSSUPD SCOREKS EMPTY OR NEW (FS 35) - LOADING\n EWSSUPD READ         000001023\n"
              " EWSSUPD ADDED        000000000\n EWSSUPD UPDATED      000001023\n EWSSUPD TIER-CHANGED 000000049\n")
    monkeypatch.setattr(zos, "spool_files", lambda j: [{"id": 9, "stepname": "STEP008", "ddname": "SYSOUT"}])
    monkeypatch.setattr(zos, "spool_content", lambda j, i: sysout)
    assert actions.job_displays("JOB1", "STEP008", "EWSSUPD") == {
        "read": 1023, "added": 0, "updated": 1023, "tier_changed": 49}


def test_report_lines_carry_the_name_read_from_vsam():
    line = (" " + "1".rjust(7) + "  CUST0166  " + " 88.11" + "  HIGH    INTV  " + "   13,312.41" + " " * 5
            + "SPEND-TO-INCOME (3 M)".ljust(30) + "  " + "Karan Iyer".ljust(30) + " " * 12)
    assert len(line) == 133
    r = actions.parse_riskrpt([line])[0]
    assert (r["cust_id"], r["top_factor"], r["name"], r["total_emi"]) == (
        "CUST0166", "SPEND-TO-INCOME (3 M)", "Karan Iyer", 13312.41)


def test_dataset_qualifiers_fit_eight_characters():
    """z/OS rejects a qualifier longer than 8 characters (IEF642I); this caught SCOREKSDS."""
    n = Names("Z99999")
    for name in [v for v in vars(n).values() if isinstance(v, str) and "." in v]:
        assert all(1 <= len(q) <= 8 for q in name.split(".")), name
    for f in (ROOT / "mainframe" / "jcl").iterdir():
        for dsn in re.findall(r"(?:DSN=|NAME\(|ENTRIES\(|OUTDATASET\()&SYSUID\.\.([A-Z0-9.#@$]+)", f.read_text()):
            assert all(1 <= len(q) <= 8 for q in dsn.split(".")), f"{f.name}: {dsn}"


def test_api_rejects_bad_customer_ids_for_vsam(monkeypatch):
    from api.main import app
    monkeypatch.setattr(actions, "hlq", lambda: "Z99999")
    assert TestClient(app).get("/customers/NOT-AN-ID/vsam").status_code == 400
