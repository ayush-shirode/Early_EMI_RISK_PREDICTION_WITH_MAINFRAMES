"""EWS operator console: a 3270/ISPF-style terminal UI for the mainframe side of the project.

    make tui            (or: .venv/bin/python -m tui)

It talks to z/OS directly, through the same modules as the web backend: z/OSMF REST
(pipeline/zos.py) and SSH (pipeline/uss.py). It does not need the backend running; both
share the SQLite database, so runs started here appear in the dashboard and vice versa.
"""
from __future__ import annotations

import time

from rich.text import Text
from textual import work
from textual.app import App
from textual.binding import Binding

from pipeline import db, runner, uss, zos, zosconf
from tui.monitor import Monitor
from tui.panels import DIM, GREEN, RED, STATE_COLOR, TURQ, WHITE, YELLOW, ConfirmDialog, Panel
from tui.screens import (OPTIONS, ConnScreen, DslistScreen, LogonScreen, MainMenu, PipelineScreen, ReportsScreen,
                         SdsfScreen, ShellScreen, SyslogScreen, VsamScreen)

SCREENS = {"0": LogonScreen, "1": ConnScreen, "2": DslistScreen, "3": SdsfScreen, "4": PipelineScreen,
           "5": SyslogScreen, "6": ShellScreen, "7": ReportsScreen, "8": VsamScreen}
NAMES = {name: key for key, name, _ in OPTIONS} | {"LOG": "5", "ST": "3", "PIPE": "4", "CMD": "6", "CONN": "1",
                                                   "DS": "2", "RPT": "7", "LOGON": "0",
                                                   "KSDS": "8"}


class EwsConsole(App):
    CSS_PATH = "ews.tcss"
    TITLE = "EWS OPERATOR CONSOLE"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [Binding("ctrl+c", "exit", show=False, priority=True)]

    def __init__(self):
        super().__init__()
        self.monitor = Monitor()
        self.started_runs: set[int] = set()

    def on_mount(self) -> None:
        db.init()
        self.set_interval(1, self.refresh_status)
        self.set_interval(15, self.beat_zosmf)
        self.set_interval(30, self.beat_ssh)
        self.set_interval(300, self.refresh_agent)
        if zosconf.is_configured():
            self.push_screen(MainMenu())
            self.beat_zosmf()
            self.beat_ssh()
            self.refresh_agent()
        else:
            self.push_screen(LogonScreen())

    # ------------------------------------------------------------ navigation
    def menu_depth(self) -> int:
        return next((i for i, s in enumerate(self.screen_stack) if isinstance(s, MainMenu)), -1)

    def open_option(self, key: str, screen: Panel | None = None) -> None:
        key = key.upper()
        if key in ("X", "EXIT"):
            self.action_exit()
            return
        if key not in SCREENS:
            self.screen.say(f"EWS000E OPTION {key} IS NOT VALID", "E") if isinstance(self.screen, Panel) else None
            return
        depth = self.menu_depth()
        if depth >= 0:
            while len(self.screen_stack) > depth + 1:
                self.pop_screen()
        self.push_screen(screen or SCREENS[key]())

    def end_panel(self) -> None:
        """F3: back one panel; on the primary menu, exit."""
        if isinstance(self.screen, MainMenu):
            self.action_exit()
        elif isinstance(self.screen, LogonScreen) and self.menu_depth() < 0:
            self.action_exit()
        else:
            self.pop_screen()

    def run_command(self, text: str, panel: Panel) -> None:
        up = text.upper().strip()
        if up.startswith("="):
            self.open_option(up[1:].strip() or "X")
            return
        if panel.command(text):
            return
        verb = up.split()[0]
        if up in SCREENS or up == "X":
            self.open_option(up)
        elif verb in NAMES and len(up.split()) == 1:
            self.open_option(NAMES[verb])
        elif verb == "TSO" or up.startswith("/"):
            self.open_option("6", ShellScreen(first=text))
        elif verb in ("EXIT", "END", "LOGOFF"):
            self.action_exit()
        else:
            panel.say(f"EWS000E COMMAND {verb} NOT FOUND - F1 FOR HELP", "E")

    def logged_on(self) -> None:
        self.monitor.zosmf.record_state("UNKNOWN")
        self.beat_zosmf()
        self.beat_ssh()
        self.refresh_agent()
        if self.menu_depth() >= 0:
            self.pop_screen()
        else:
            self.switch_screen(MainMenu())

    def logoff(self) -> None:
        zosconf.logout()
        uss.close()
        self.monitor.zosmf.record_state("NOLOGON")
        self.open_option("0")

    def action_exit(self) -> None:
        mine = runner.active_run_id()
        if mine in self.started_runs:
            self.push_screen(ConfirmDialog("EXIT", Text(
                f"Run #{mine} was started from this console and is still active.\n"
                "Leaving the console aborts it. Exit anyway?", style=YELLOW)),
                lambda ok: ok and self.exit())
        else:
            self.exit()

    # ------------------------------------------------------------ status line
    def sysname(self) -> str:
        a = self.monitor.agent_info.get("sysname")
        if a:
            return a
        host = self.monitor.zosmf_info.get("zosmf_hostname")
        return host.split(".")[0] if host else "----"

    def refresh_status(self) -> None:
        if not isinstance(self.screen, Panel):
            return
        m = self.monitor
        t = Text(" ")
        for ch in (m.zosmf, m.ssh):
            color = STATE_COLOR.get(ch.state, YELLOW)
            t.append(f"{ch.name} ", style=TURQ)
            t.append("■ ", style=color)
            t.append(f"{ch.state:<7}", style=f"bold {color}")
            t.append(f"{ch.last_ms if ch.last_ms is not None and ch.state == 'UP' else '-':>5} MS", style=WHITE)
            t.append("  │  ", style=DIM)
        try:
            s = zosconf.load()
            t.append(f"{s.user}@{self.sysname()}", style=WHITE)
        except zosconf.NotConfigured:
            t.append("NOT LOGGED ON", style=YELLOW)
        t.append("  │  ", style=DIM)
        rid = runner.active_run_id()
        if rid:
            r = db.query("SELECT action, source, started_at FROM runs WHERE id=?", (rid,))[0]
            t.append(f"RUN #{rid} {r['action'].upper()} ({r['source'] or 'API'}) EXECUTING", style=f"bold {YELLOW}")
        else:
            t.append("NO ACTIVE RUN", style=GREEN)
        t.append("  │  ", style=DIM)
        t.append(time.strftime("%Y.%j %H:%M:%S"), style=WHITE)
        try:
            self.screen.query_one("#statusline").update(t)
        except Exception:
            pass

    # ------------------------------------------------------------ heartbeats (worker threads)
    @work(thread=True, exclusive=True, group="hb-zosmf")
    def beat_zosmf(self) -> None:
        if not zosconf.is_configured():
            self.monitor.zosmf.record_state("NOLOGON", "Not logged on")
            return
        try:
            ms, info = zos.ping()
        except Exception as e:
            self.monitor.zosmf.record_fail(str(e))
            return
        self.monitor.zosmf_info = info
        self.monitor.zosmf.record_ok(ms)

    @work(thread=True, exclusive=True, group="hb-ssh")
    def beat_ssh(self) -> None:
        if not zosconf.is_configured():
            self.monitor.ssh.record_state("NOLOGON", "Not logged on")
            return
        if not zosconf.KNOWN_HOSTS.exists():
            self.monitor.ssh.record_state("NOKEY", "SSH host key not trusted yet (SSHKEY on the connection panel)")
            return
        try:
            ms = uss.ping()
        except Exception as e:
            self.monitor.ssh.record_fail(str(e))
            return
        self.monitor.ssh.record_ok(ms)

    @work(thread=True, exclusive=True, group="agent")
    def refresh_agent(self) -> None:
        if not zosconf.is_configured() or not zosconf.KNOWN_HOSTS.exists():
            return
        try:
            info = uss.agent("info")
        except Exception as e:
            self.monitor.agent_error = str(e)
            return
        if info.get("error"):
            self.monitor.agent_error = info["error"]
            return
        self.monitor.agent_info, self.monitor.agent_at, self.monitor.agent_error = info, time.time(), None


def main() -> None:
    EwsConsole().run()


if __name__ == "__main__":
    main()
