"""Health of the two channels to the mainframe, fed by the TUI's heartbeat workers."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from pipeline import oplog


@dataclass
class Channel:
    name: str                       # ZOSMF | SSH
    state: str = "UNKNOWN"          # UP | DOWN | UNKNOWN | NOKEY | NOLOGON
    last_ms: int | None = None
    history: deque = field(default_factory=lambda: deque(maxlen=60))
    ok: int = 0
    fail: int = 0
    since: float = field(default_factory=time.time)
    checked_at: float | None = None
    last_error: str | None = None

    def _set(self, state: str) -> None:
        if state != self.state:
            if state == "UP":
                oplog.write("EWS400I", f"{self.name} CHANNEL UP ({self.last_ms} MS)", self.last_ms, channel="CONN")
            elif state == "DOWN":
                oplog.write("EWS401E", f"{self.name} CHANNEL DOWN: {self.last_error}", channel="CONN")
            self.state, self.since = state, time.time()

    def record_ok(self, ms: int) -> None:
        self.ok += 1
        self.last_ms, self.checked_at = ms, time.time()
        self.history.append(ms)
        self._set("UP")

    def record_fail(self, error: str) -> None:
        self.fail += 1
        self.last_error, self.checked_at = error[:300], time.time()
        self.history.append(0)
        self._set("DOWN")

    def record_state(self, state: str, error: str | None = None) -> None:
        self.last_error, self.checked_at = error, time.time()
        self._set(state)

    @property
    def availability(self) -> float | None:
        total = self.ok + self.fail
        return 100 * self.ok / total if total else None


class Monitor:
    def __init__(self) -> None:
        self.zosmf = Channel("ZOSMF")
        self.ssh = Channel("SSH")
        self.zosmf_info: dict = {}      # /zosmf/info
        self.agent_info: dict = {}      # ewsagent.py info
        self.agent_at: float | None = None
        self.agent_error: str | None = None
