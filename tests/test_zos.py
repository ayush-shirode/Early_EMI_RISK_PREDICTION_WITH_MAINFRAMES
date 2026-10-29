"""The z/OSMF client and the cross-process run lock, without a mainframe."""
import json
import subprocess
import sys

import pytest

from pipeline import db, runner, zos


class FakeResponse:
    def __init__(self, status=200, body=None, text=""):
        self.status_code, self._body = status, body
        self.content = (json.dumps(body) if body is not None else text).encode()
        self.text, self.encoding, self.reason = self.content.decode(), "iso-8859-1", "x"

    def json(self):
        if self._body is None:
            raise ValueError
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        return self.responses.pop(0)


@pytest.fixture
def fake(monkeypatch):
    def install(*responses):
        s = FakeSession(responses)
        monkeypatch.setattr(zos, "_session", lambda: (s, "https://zos:10443"))
        return s
    db.init()
    return install


def test_submit_sends_jcl_symbols_as_headers(fake):
    s = fake(FakeResponse(201, {"jobid": "JOB00042", "jobname": "EWSBATCH", "status": "INPUT"}))
    job = zos.submit("z72230.ews.jcl(ewsbatch)", {"ASOFDT": 20260930, "MODE": "SCORE"}, wait=False)
    method, url, kw = s.calls[0]
    assert (method, url) == ("PUT", "https://zos:10443/zosmf/restjobs/jobs")
    assert kw["json"] == {"file": "//'Z72230.EWS.JCL(EWSBATCH)'"}
    assert kw["headers"] == {"X-IBM-JCL-Symbol-ASOFDT": "20260930", "X-IBM-JCL-Symbol-MODE": "SCORE"}
    assert job["jobid"] == "JOB00042" and zos._jobnames["JOB00042"] == "EWSBATCH"


def test_dataset_paths_are_quoted_and_upper_case(fake):
    s = fake(FakeResponse(200, text="REC1\n"))
    assert zos.download_text("z72230.ews.jcl(ewscomp)") == "REC1\n"
    assert s.calls[0][1].endswith("/zosmf/restfiles/ds/Z72230.EWS.JCL(EWSCOMP)")
    assert zos._ds("A.B#C") == "/zosmf/restfiles/ds/A.B%23C"


def test_create_sequential_uses_half_track_blocking(fake):
    s = fake(FakeResponse(201, text=""))
    zos.create_sequential("Z.EWS.X", "FB", 100, "15TRK")
    assert s.calls[0][2]["json"] == {"dsorg": "PS", "alcunit": "TRK", "primary": 15, "secondary": 7,
                                     "recfm": "FB", "blksize": 27900, "lrecl": 100}


def test_errors_carry_the_zosmf_message(fake):
    fake(FakeResponse(404, {"category": 1, "rc": 4, "message": "Data set not found", "details": ["Z.EWS.NOPE"]}))
    with pytest.raises(zos.ZosError, match="Data set not found Z.EWS.NOPE"):
        zos.download_text("Z.EWS.NOPE")
    fake(FakeResponse(401, text="<html>Unauthorized</html>"))
    with pytest.raises(zos.ZosError, match="user ID or password"):
        zos.list_datasets("Z.EWS.**")


def test_a_run_in_another_live_process_blocks_a_new_one():
    db.init()
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        with db.tx() as con:
            cur = con.execute("INSERT INTO runs(action, params, status, started_at, pid, source) "
                              "VALUES('run_batch', '{}', 'running', ?, ?, 'TUI')", (db.now(), other.pid))
            rid = cur.lastrowid
        assert runner.active_run_id() == rid
        with pytest.raises(runner.Busy, match="TUI"):
            runner.start("test_connection", lambda ctx: None, {})
    finally:
        other.kill()
        other.wait()
    # once that process is gone its run no longer blocks, and it is marked failed
    assert runner.active_run_id() is None
    new = runner.run_inline("test_connection", lambda ctx: ctx.plan([]), {})
    assert runner.get_run(rid)["status"] == "failed"
    assert runner.get_run(new)["status"] == "ok"
