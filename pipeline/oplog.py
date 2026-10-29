"""Operator log: every mainframe call, run event and connection change, in one table.

The TUI shows it as the SYSLOG screen. Message IDs follow the z/OS convention
PPPnnnS (prefix, number, severity I/W/E):

    EWS100I  z/OSMF request ok            EWS101E  z/OSMF request failed    EWS102W  retried
    EWS110I  job submitted                EWS111I  job ended                EWS112E  job failed
    EWS120I  upload                       EWS121I  download
    EWS200I  run started                  EWS201I  step ok                  EWS202E  step failed
    EWS203I  run ended ok                 EWS204E  run failed
    EWS300I  SSH command                  EWS301E  SSH failed               EWS302I  SSH connected
    EWS400I  channel up                   EWS401E  channel down
    EWS500I  logon / logoff

Writing never raises: logging must not break a mainframe call.
"""
from __future__ import annotations

import os

from pipeline import db

KEEP_ROWS = 20000
_writes = 0


def write(msgid: str, text: str, ms: int | None = None, channel: str = "ZOSMF") -> None:
    global _writes
    level = msgid[-1] if msgid[-1] in "IWE" else "I"
    try:
        with db.tx() as con:
            con.execute("INSERT INTO oplog(ts, pid, channel, level, msgid, text, ms) VALUES(?,?,?,?,?,?,?)",
                        (db.now(), os.getpid(), channel, level, msgid, text[:1000], ms))
            _writes += 1
            if _writes % 500 == 0:
                con.execute("DELETE FROM oplog WHERE id <= (SELECT MAX(id) FROM oplog) - ?", (KEEP_ROWS,))
    except Exception:
        pass


def read(after_id: int = 0, limit: int = 500, errors_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM oplog WHERE id > ?"
    if errors_only:
        sql += " AND level IN ('E', 'W')"
    if after_id:
        return db.query(sql + " ORDER BY id LIMIT ?", (after_id, limit))
    rows = db.query(sql + " ORDER BY id DESC LIMIT ?", (after_id, limit))
    return rows[::-1]
