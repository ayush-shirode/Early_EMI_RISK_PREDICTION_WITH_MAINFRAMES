"""Background executor for UI actions.

One action runs at a time (the mainframe data sets are shared), across processes: the
web backend, the operator TUI and the CLI all check the runs table before starting, and
a run whose process has died no longer blocks anyone. Each action declares its steps up
front so the UI can draw the full timeline immediately; every step's status, timing,
detail text and data (job IDs, return codes, counts) is persisted.
"""
from __future__ import annotations

import json
import os
import threading
import traceback
from contextlib import contextmanager
from pathlib import Path

from pipeline import db, oplog
from pipeline.config import RUNS_DIR


class ActionError(RuntimeError):
    """A failure with a message meant for the user."""


class Busy(RuntimeError):
    pass


class RunContext:
    def __init__(self, run_id: int, params: dict):
        self.run_id = run_id
        self.params = params
        self.dir: Path = RUNS_DIR / str(run_id)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.summary: dict = {}
        self._steps: list[str] = []

    def plan(self, names: list[str]) -> None:
        self._steps = list(names)
        with db.tx() as con:
            con.execute("DELETE FROM run_steps WHERE run_id=?", (self.run_id,))
            con.executemany(
                "INSERT INTO run_steps(run_id, seq, name, status) VALUES(?,?,?, 'pending')",
                [(self.run_id, i, n) for i, n in enumerate(names)],
            )

    def add_steps(self, names: list[str]) -> None:
        start = len(self._steps)
        self._steps += names
        with db.tx() as con:
            con.executemany(
                "INSERT INTO run_steps(run_id, seq, name, status) VALUES(?,?,?, 'pending')",
                [(self.run_id, start + i, n) for i, n in enumerate(names)],
            )

    @contextmanager
    def step(self, name: str):
        seq = self._steps.index(name)
        handle = StepHandle(self.run_id, seq)
        with db.tx() as con:
            con.execute("UPDATE run_steps SET status='running', started_at=? WHERE run_id=? AND seq=?",
                        (db.now(), self.run_id, seq))
        try:
            yield handle
        except Exception as e:
            handle.finish("failed", str(e))
            oplog.write("EWS202E", f"RUN #{self.run_id} STEP {seq + 1} {name.upper()} FAILED: {e}", channel="RUN")
            raise
        handle.finish("ok")
        oplog.write("EWS201I", f"RUN #{self.run_id} STEP {seq + 1} {name.upper()} OK"
                    + (f" - {handle._detail}" if handle._detail else ""), channel="RUN")


class StepHandle:
    def __init__(self, run_id: int, seq: int):
        self.run_id, self.seq = run_id, seq
        self._data: dict = {}
        self._detail: str | None = None

    def detail(self, text: str) -> None:
        self._detail = text
        self._save()

    def data(self, **kw) -> None:
        self._data.update(kw)
        self._save()

    def _save(self, status: str | None = None, finished: bool = False) -> None:
        sets, args = ["detail=?", "data=?"], [self._detail, json.dumps(self._data, default=str)]
        if status:
            sets.append("status=?")
            args.append(status)
        if finished:
            sets.append("finished_at=?")
            args.append(db.now())
        with db.tx() as con:
            con.execute(f"UPDATE run_steps SET {', '.join(sets)} WHERE run_id=? AND seq=?",
                        (*args, self.run_id, self.seq))

    def finish(self, status: str, error: str | None = None) -> None:
        if error:
            self._detail = error
        self._save(status, finished=True)


_guard = threading.Lock()


def active_run_id() -> int | None:
    """The run in progress in any process (backend, TUI, CLI), if any."""
    for r in db.query("SELECT id, pid FROM runs WHERE status='running' ORDER BY id DESC"):
        if db.pid_alive(r["pid"]):
            return r["id"]
    return None


def _claim(action: str, params: dict, source: str) -> int:
    """Insert the run if no other live run exists. BEGIN IMMEDIATE makes check + insert atomic across processes."""
    with _guard, db.tx() as con:
        con.execute("BEGIN IMMEDIATE")
        db.fail_orphaned_runs(con)
        busy = con.execute("SELECT id, source FROM runs WHERE status='running' ORDER BY id DESC").fetchone()
        if busy:
            raise Busy(f"Run #{busy['id']} is still active" + (f" (started from the {busy['source']})" if busy["source"] else ""))
        cur = con.execute("INSERT INTO runs(action, params, status, started_at, pid, source) VALUES(?,?, 'running', ?,?,?)",
                          (action, json.dumps(params), db.now(), os.getpid(), source))
        run_id = cur.lastrowid
    oplog.write("EWS200I", f"RUN #{run_id} {action.upper()} STARTED FROM {source}"
                + (f" {json.dumps(params)}" if params else ""), channel="RUN")
    return run_id


def start(action: str, fn, params: dict, source: str = "API") -> int:
    run_id = _claim(action, params, source)
    threading.Thread(target=_execute, args=(run_id, fn, params), daemon=True, name=f"run-{run_id}").start()
    return run_id


def run_inline(action: str, fn, params: dict, source: str = "CLI") -> int:
    """Same as start() but in the calling thread (used by the debugging CLI)."""
    run_id = _claim(action, params, source)
    _execute(run_id, fn, params)
    return run_id


def _execute(run_id: int, fn, params: dict) -> None:
    ctx = RunContext(run_id, params)
    status, error = "ok", None
    try:
        fn(ctx, **params)
    except Exception as e:  # every failure ends the run with a readable message
        status = "failed"
        error = str(e) if isinstance(e, ActionError) or str(e) else repr(e)
        (ctx.dir / "error.txt").write_text(traceback.format_exc())
    finally:
        with db.tx() as con:
            con.execute("UPDATE run_steps SET status='skipped' WHERE run_id=? AND status='pending'", (run_id,))
            con.execute("UPDATE runs SET status=?, error=?, finished_at=?, summary=? WHERE id=?",
                        (status, error, db.now(), json.dumps(ctx.summary, default=str), run_id))
        if status == "ok":
            oplog.write("EWS203I", f"RUN #{run_id} ENDED OK", channel="RUN")
        else:
            oplog.write("EWS204E", f"RUN #{run_id} FAILED: {error}", channel="RUN")


def get_run(run_id: int) -> dict | None:
    rows = db.query("SELECT * FROM runs WHERE id=?", (run_id,))
    if not rows:
        return None
    run = rows[0]
    run["params"] = json.loads(run["params"])
    run["summary"] = json.loads(run["summary"])
    run["steps"] = db.query("SELECT seq, name, status, started_at, finished_at, detail, data "
                            "FROM run_steps WHERE run_id=? ORDER BY seq", (run_id,))
    for s in run["steps"]:
        s["data"] = json.loads(s["data"])
    return run


def list_runs(limit: int = 50, action: str | None = None) -> list[dict]:
    sql = "SELECT id, action, params, status, started_at, finished_at, error, source FROM runs"
    args: tuple = ()
    if action:
        sql += " WHERE action=?"
        args = (action,)
    rows = db.query(sql + " ORDER BY id DESC LIMIT ?", (*args, limit))
    for r in rows:
        r["params"] = json.loads(r["params"])
    return rows
