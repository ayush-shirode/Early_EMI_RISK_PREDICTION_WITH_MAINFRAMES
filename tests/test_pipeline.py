"""Backend logic that does not need a mainframe: parsers, step-RC parsing, API validation."""
from fastapi.testclient import TestClient

from pipeline import actions, zowe

JESYSMSG = """
 IEF142I EWSBATCH STEP005 - STEP WAS EXECUTED - COND CODE 0000
 IEF142I EWSBATCH STEP050 - STEP WAS EXECUTED - COND CODE 0004
 IEF472I EWSBATCH STEP070 - COMPLETION CODE - SYSTEM=0C7 USER=0000 REASON=00000000
 IEF272I EWSBATCH STEP080 - STEP WAS NOT EXECUTED.
 IEF142I EWSCOMP CVCUST COBOL - STEP WAS EXECUTED - COND CODE 0000
"""


def test_step_results_parsing(monkeypatch):
    monkeypatch.setattr(zowe, "spool_files", lambda j: [{"ddname": "JESYSMSG", "id": 4}])
    monkeypatch.setattr(zowe, "spool_content", lambda j, i: JESYSMSG)
    steps = zowe.step_results("JOB00001")
    assert steps[0] == {"step": "STEP005", "procstep": None, "rc": 0, "status": "executed"}
    assert steps[1]["rc"] == 4
    assert steps[2]["status"] == "abended" and steps[2]["abend"] == "S0C7"
    assert steps[3]["status"] == "not executed"
    assert steps[4]["step"] == "CVCUST" and steps[4]["procstep"] == "COBOL"


def test_runctl_parsing():
    rc = actions.parse_runctl("ASOF=20260930\nMODE=SCORE\nFEATURES=1023\nSTATUS=OK\n")
    assert rc == {"ASOF": 20260930, "MODE": "SCORE", "FEATURES": 1023, "STATUS": "OK"}


def test_reject_parsing():
    line = "CUSTMAST" + "CUST0001  " + "C02 " + "AGE IS NOT NUMERIC".ljust(40) + "X" * 58
    r = actions.parse_rejects(line)[0]
    assert r["source"] == "CUSTMAST" and r["key"] == "CUST0001" and r["reason_code"] == "C02"


def test_names_restrict_browsing():
    n = actions.Names("Z99999")
    assert n.is_project_dataset("Z99999.EWS.CUSTMAST")
    assert not n.is_project_dataset("SYS1.PARMLIB")
    assert not n.is_project_dataset("Z99999.CBL")


def client():
    from api.main import app
    return TestClient(app)


def test_api_rejects_unknown_actions_and_parameters():
    c = client()
    assert c.post("/actions/rm_rf", json={}).status_code == 404
    assert c.post("/actions/test_connection", json={"cmd": "x"}).status_code == 400
    assert c.post("/actions/generate_data", json={"customers": 999999}).status_code == 400
    assert c.post("/actions/run_batch", json={"asof": "20991231"}).status_code == 400
    assert c.post("/actions/reset_data", json={}).status_code == 400


def test_api_validates_job_ids_and_dataset_names(monkeypatch):
    monkeypatch.setattr(actions, "hlq", lambda: "Z99999")
    c = client()
    assert c.get("/jobs/..%2Fetc/spool").status_code in (400, 404)
    assert c.get("/jobs/NOTAJOB/spool").status_code == 400
    assert c.get("/datasets/SYS1.PARMLIB/preview").status_code == 403
