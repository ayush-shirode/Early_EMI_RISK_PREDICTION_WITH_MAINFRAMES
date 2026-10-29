"""The operator console panels (ISPF/SDSF style)."""
from __future__ import annotations

import json
import shlex
import time
from datetime import datetime
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import DataTable, Input, RichLog, Sparkline, Static

from ml import score
from pipeline import actions, db, oplog, runner, uss, zos, zosconf
from pipeline.config import DATA_DIR, INPUT_DIR, RUNS_DIR, SCORE_ASOF
from tui.panels import (BLUE, DIM, GREEN, PINK, RED, STATE_COLOR, TURQ, WHITE, YELLOW, ConfirmDialog, FormDialog,
                        Panel, elapsed, hhmmss, julian, rc_color, rc_text)

DOWNLOAD_DIR = DATA_DIR / "downloads"


def table(id: str | None = None, **kw) -> DataTable:
    t = DataTable(id=id, cursor_type="row", zebra_stripes=False, **kw)
    return t


def keep_cursor(t: DataTable, fill) -> None:
    """Refill a table without losing the operator's place."""
    row = t.cursor_row
    t.clear()
    fill()
    if t.row_count:
        t.move_cursor(row=min(row, t.row_count - 1))


def row_key(t: DataTable) -> str | None:
    if not t.row_count:
        return None
    return t.coordinate_to_cell_key(t.cursor_coordinate).row_key.value


# ===================================================================== 0 LOGON
class LogonScreen(Panel):
    PANEL_ID = "EWSLOGON"
    PANEL_TITLE = "TSO/E LOGON - EWS OPERATOR CONSOLE"
    PFKEYS = "ENTER=LOGON  F3=END"
    HELP = ("Enter the z/OS user ID and password. They are checked against z/OSMF and the\n"
            "password is kept in the operating system keyring (service ews-zos), never in a file.\n\n"
            "HOST / PORTS  where z/OSMF (HTTPS) and the SSH server (USS) listen.\n"
            "VERIFY TLS    N for systems with a self-signed certificate (IBM Z Xplore).")

    def body(self) -> ComposeResult:
        try:
            s = zosconf.load()
        except zosconf.NotConfigured:
            s = zosconf.Settings(host="", verify=False)
        with Vertical(id="logon"):
            yield Static(Text("Enter LOGON parameters below:", style=WHITE))
            yield Static("")
            for key, label, value, pw in (("user", "Userid", s.user, False), ("password", "Password", "", True),
                                          ("host", "Host", s.host, False), ("port", "z/OSMF port", s.port, False),
                                          ("ssh_port", "SSH port", s.ssh_port, False),
                                          ("verify", "Verify TLS", "Y" if s.verify else "N", False)):
                with Horizontal(classes="field"):
                    yield Static(f"{label:<11} ===>", classes="label")
                    yield Input(value=str(value), id=f"l-{key}", password=pw)
            yield Static(Text("The password goes to the OS keyring; nothing secret is written to disk.", style=DIM))

    def on_mount(self) -> None:
        super().on_mount()
        first_empty = next((i for i in self.query(".field Input") if not i.value), None)
        (first_empty or self.query_one("#l-user", Input)).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "cmd":
            return super().on_input_submitted(event)
        v = {k: self.query_one(f"#l-{k}", Input).value.strip()
             for k in ("user", "password", "host", "port", "ssh_port", "verify")}
        if not (v["user"] and v["host"]):
            self.say("IKJ56700A ENTER USERID AND HOST", "E")
            return
        try:
            s = zosconf.Settings(host=v["host"], port=int(v["port"] or 10443), user=v["user"].upper(),
                                 ssh_port=int(v["ssh_port"] or 22), verify=v["verify"].upper().startswith("Y"))
        except ValueError:
            self.say("IKJ56701A PORTS MUST BE NUMERIC", "E")
            return
        if not v["password"]:
            try:
                if zosconf.password(s):
                    v["password"] = None  # keep the stored one
                else:
                    raise ValueError
            except ValueError:
                self.say("IKJ56702A ENTER PASSWORD", "E")
                return
        self.say(f"LOGON IN PROGRESS AT {s.host}:{s.port} ...")
        self.logon(s, v["password"])

    @work(thread=True, exclusive=True)
    def logon(self, s: zosconf.Settings, pw: str | None) -> None:
        try:
            zosconf.save(s, pw)
            info = zos.check_status()
        except Exception as e:
            self.say_from_thread(f"IKJ56421I LOGON REJECTED - {e}", "E")
            return
        oplog.write("EWS500I", f"LOGON {info['user']} AT {info['system']} (Z/OS {info['zos_version']})", channel="CONN")
        self.app.call_from_thread(self.app.logged_on)


# ===================================================================== primary menu
OPTIONS = [
    ("0", "LOGON", "Logon panel - user ID, password, host and ports"),
    ("1", "CONNECT", "Connection monitor - z/OSMF and SSH channels, z/OS system"),
    ("2", "DSLIST", "Data set list - browse, upload, download, count records"),
    ("3", "SDSF", "Job queue - status, step return codes, spool output"),
    ("4", "PIPELINE", "Batch pipeline - setup, compile, generate, train, run batch"),
    ("5", "SYSLOG", "Operator log - every mainframe call, run event and error"),
    ("6", "COMMAND", "USS shell, TSO and operator console commands over SSH"),
    ("7", "REPORTS", "Reconciliation, rejected records, intervention list"),
    ("X", "EXIT", "Leave the EWS operator console"),
]

BANNER = r"""
 EEEEEEE WW    WW  SSSSS    E A R L Y   W A R N I N G   S Y S T E M
 EE      WW    WW SS        EMI stress prediction - IBM z/OS batch + ML
 EEEEE   WW WW WW  SSSSS    JES2 - COBOL - DFSORT - REXX - z/OSMF - SSH
 EE      WWWW WWW      SS
 EEEEEEE WW    WW  SSSSS    OPERATOR CONSOLE""".strip("\n")


class MainMenu(Panel):
    PANEL_ID = "EWSPRIM"
    PANEL_TITLE = "EWS PRIMARY OPTION MENU"
    PFKEYS = "F1=HELP  F3=EXIT  ENTER=SELECT  0-7=OPTION"
    HELP = ("Type an option number (or its name) on the command line, or move to a line\n"
            "and press ENTER. From any panel, =N jumps straight to option N and =X exits.\n"
            "TSO <command> and /<console command> work from every panel.")
    BINDINGS = [Binding(k.lower(), f"open('{k}')", show=False) for k, _, _ in OPTIONS]

    def body(self) -> ComposeResult:
        yield Static(Text(BANNER, style=TURQ), id="banner")
        with Horizontal(id="menu-wrap"):
            yield table("menu", show_header=False)
            yield Static(id="sysinfo", classes="box")

    def on_mount(self) -> None:
        super().on_mount()
        t = self.query_one("#menu", DataTable)
        t.add_columns("opt", "name", "desc")
        for k, name, desc in OPTIONS:
            t.add_row(Text(f" {k} ", style=f"bold {WHITE}"), Text(f"{name:<9}", style=TURQ), Text(desc), key=k)
        t.focus()
        self.draw_info()
        self.set_interval(2, self.draw_info)

    def action_open(self, key: str) -> None:
        self.app.open_option(key)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.app.open_option(event.row_key.value)

    def draw_info(self) -> None:
        m, a = self.app.monitor, self.app.monitor.agent_info
        try:
            s = zosconf.load()
            user, host = s.user, s.host
        except zosconf.NotConfigured:
            user = host = "-"
        met = score.metrics()
        last = db.kv_get("last_score_run")
        lr = runner.get_run(last) if last else None
        rows = [
            ("USERID", user), ("TIME", datetime.now().strftime("%H:%M:%S")),
            ("DATE", datetime.now().strftime("%Y.%j")), ("TERMINAL", "3278-2  EWS/TUI"),
            ("SYSTEM", a.get("sysname") or self.app.sysname()), ("Z/OS", a.get("release") or m.zosmf_info.get("zos_version", "-")),
            ("Z/OSMF", m.zosmf_info.get("zosmf_full_version", "-")), ("HOST", host),
            ("HLQ", f"{user}.EWS"),
            ("MODEL", met["model_version"] if met else "NOT TRAINED"),
            ("LAST RUN", f"#{lr['id']} {lr['status'].upper()} AS-OF {lr['summary'].get('asof', '-')}" if lr else "NONE"),
        ]
        text = Text()
        for k, v in rows:
            text.append(f"{k:<9}. : ", style=TURQ)
            text.append(f"{v}\n", style=WHITE)
        for ch in (m.zosmf, m.ssh):
            text.append(f"{ch.name:<9}. : ", style=TURQ)
            text.append(f"{ch.state}", style=STATE_COLOR.get(ch.state, YELLOW))
            text.append(f" {ch.last_ms} MS\n" if ch.last_ms is not None and ch.state == "UP" else "\n")
        self.query_one("#sysinfo", Static).update(text)


# ===================================================================== 1 CONNECT
class ConnScreen(Panel):
    PANEL_ID = "EWSCONN"
    PANEL_TITLE = "CONNECTION MONITOR"
    PFKEYS = "F1=HELP  F3=END  F5=TEST NOW   TEST  SSHKEY  INSTALL  RECONNECT  LOGOFF"
    HELP = ("Two independent channels to z/OS are checked in the background:\n"
            "  ZOSMF  HTTPS to the z/OSMF REST API (data sets and JES), every 15 s\n"
            "  SSH    SSH to z/OS UNIX (commands, the EWS agent), every 30 s\n\n"
            "Commands:\n"
            "  TEST       check both channels now and refresh the z/OS system data\n"
            "  SSHKEY     fetch the SSH host key, show its fingerprint, trust it\n"
            "  INSTALL    copy the EWS agent (mainframe/uss/ewsagent.py) to ~/ews on USS\n"
            "  RECONNECT  drop the SSH connection and open a new one\n"
            "  LOGOFF     remove the stored password and return to the logon panel")

    def body(self) -> ComposeResult:
        with Horizontal(id="conn-top"):
            with Vertical(classes="channel box", id="zbox"):
                yield Static(id="zstat")
                yield Sparkline([0], id="zspark")
            with Vertical(classes="channel box", id="sbox"):
                yield Static(id="sstat")
                yield Sparkline([0], id="sspark")
        yield Static(id="agent", classes="box")
        yield Static("CONNECTION EVENTS", classes="section")
        yield RichLog(id="events", markup=False, wrap=False, max_lines=500)

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#zbox").border_title = "CHANNEL 1 - Z/OSMF REST (HTTPS)"
        self.query_one("#sbox").border_title = "CHANNEL 2 - SSH TO Z/OS UNIX"
        self.query_one("#agent").border_title = "Z/OS SYSTEM - EWS AGENT ON USS"
        self.last_event = max(0, (db.query("SELECT MAX(id) AS m FROM oplog")[0]["m"] or 0) - 60)
        self.draw()
        self.set_interval(1, self.draw)
        self.query_one("#cmd", Input).focus()

    def _channel(self, ch, endpoint: str, extra: list[tuple[str, str]]) -> Text:
        t = Text()
        hist = [h for h in ch.history if h]
        rows = [
            ("ENDPOINT", endpoint),
            ("STATE", None),
            ("LATENCY", f"{ch.last_ms} MS  (AVG {sum(hist) // len(hist)}  MAX {max(hist)})" if hist else "-"),
            ("CHECKS", f"{ch.ok} OK  {ch.fail} FAILED" + (f"  AVAIL {ch.availability:.1f}%" if ch.availability is not None else "")),
            ("LAST CHECK", time.strftime("%H:%M:%S", time.localtime(ch.checked_at)) if ch.checked_at else "-"),
            *extra,
            ("LAST ERROR", ch.last_error or "-"),
        ]
        for k, v in rows:
            t.append(f"{k:<11}", style=TURQ)
            if v is None:
                t.append("■ ", style=STATE_COLOR.get(ch.state, YELLOW))
                t.append(ch.state, style=f"bold {STATE_COLOR.get(ch.state, YELLOW)}")
                t.append(f"   SINCE {time.strftime('%H:%M:%S', time.localtime(ch.since))}\n", style=WHITE)
            else:
                style = RED if k == "LAST ERROR" and v != "-" else WHITE
                t.append(f"{v}\n", style=style)
        return t

    def draw(self) -> None:
        m = self.app.monitor
        try:
            s = zosconf.load()
            zend, send = f"https://{s.host}:{s.port}", f"{s.user}@{s.host}:{s.ssh_port}"
        except zosconf.NotConfigured:
            zend = send = "NOT CONFIGURED"
        zi = m.zosmf_info
        self.query_one("#zstat", Static).update(self._channel(m.zosmf, zend, [
            ("Z/OSMF", f"{zi.get('zosmf_full_version', '-')}  Z/OS {zi.get('zos_version', '-')}"),
            ("HOSTNAME", zi.get("zosmf_hostname", "-"))]))
        trusted = zosconf.KNOWN_HOSTS.exists()
        self.query_one("#sstat", Static).update(self._channel(m.ssh, send, [
            ("HOST KEY", "TRUSTED (PINNED)" if trusted else "NOT TRUSTED - USE SSHKEY"),
            ("AUTH", "KEY OR KEYRING PASSWORD")]))
        self.query_one("#zspark", Sparkline).data = list(m.zosmf.history) or [0]
        self.query_one("#sspark", Sparkline).data = list(m.ssh.history) or [0]

        a = m.agent_info
        t = Text()
        if a:
            fs = a.get("home_fs") or {}
            ipl, clock = a.get("ipl") or {}, a.get("clock") or {}
            for k, v in (
                ("SYSNAME", f"{a.get('sysname')}   {a.get('uname')}"),
                ("RELEASE", f"{a.get('release')}   IPL {ipl.get('date', '-')} {ipl.get('time', '-')}  VOLUME {a.get('ipl_volume')}"),
                ("CLOCK", f"{clock.get('date', '-')} {clock.get('time', '-')}  (FROM D T ON THE CONSOLE)"),
                ("USER", f"{a.get('user')}   HOME {a.get('home')}  {fs.get('name', '')} "
                         + (f"{fs['free_kb'] // 1024} MB FREE OF {fs['total_kb'] // 1024}" if fs else "")),
                ("SOFTWARE", f"ZOAU {a.get('zoau')}   PYTHON {a.get('python')}   EWS AGENT {a.get('agent')}"),
                ("UPDATED", f"{time.strftime('%H:%M:%S', time.localtime(m.agent_at))}  (ANSWERED IN {a.get('elapsed_ms')} MS)"),
            ):
                t.append(f"{k:<10}", style=TURQ)
                t.append(f"{v}\n", style=WHITE)
        else:
            t.append(m.agent_error or "Waiting for the agent (SSH channel)...", style=YELLOW if m.agent_error else DIM)
        self.query_one("#agent", Static).update(t)

        log = self.query_one("#events", RichLog)
        for r in oplog.read(after_id=self.last_event, limit=200):
            self.last_event = r["id"]
            if r["channel"] in ("CONN", "SSH") or r["msgid"] in ("EWS101E", "EWS102W"):
                log.write(syslog_line(r))

    def action_refresh_panel(self) -> None:
        self.say("CHECKING BOTH CHANNELS ...")
        self.app.beat_zosmf()
        self.app.beat_ssh()
        self.app.refresh_agent()

    def command(self, text: str) -> bool:
        verb = text.split()[0].upper()
        if verb == "TEST":
            self.action_refresh_panel()
        elif verb == "SSHKEY":
            self.fetch_key()
        elif verb == "INSTALL":
            self.say("INSTALLING THE EWS AGENT ON USS ...")
            self.install()
        elif verb == "RECONNECT":
            uss.close()
            self.app.beat_ssh()
            self.say("SSH CONNECTION DROPPED - RECONNECTING")
        elif verb == "LOGOFF":
            self.app.push_screen(ConfirmDialog("LOGOFF", "Remove the stored password from the keyring?"),
                                 lambda ok: ok and self.app.logoff())
        else:
            return False
        return True

    @work(thread=True)
    def fetch_key(self) -> None:
        try:
            key, fp = uss.fetch_host_key()
        except Exception as e:
            self.say_from_thread(f"EWS301E CANNOT READ THE HOST KEY: {e}", "E")
            return
        msg = Text()
        msg.append("The SSH server presents this host key:\n\n", style=WHITE)
        msg.append(f"   {fp}\n\n", style=f"bold {YELLOW}")
        msg.append("Trust it for all later connections? Compare it with the key your system\n"
                   "administrator published (or the one Zowe Explorer showed) before you confirm.", style=WHITE)

        def done(ok):
            if ok:
                uss.trust_host_key(key)
                self.say(f"EWS500I HOST KEY TRUSTED {fp}")
                self.app.beat_ssh()
        self.app.call_from_thread(self.app.push_screen, ConfirmDialog("TRUST SSH HOST KEY", msg), done)

    @work(thread=True, exclusive=True)
    def install(self) -> None:
        try:
            version = uss.install_agent()
        except Exception as e:
            self.say_from_thread(f"EWS301E AGENT INSTALL FAILED: {e}", "E")
            return
        self.say_from_thread(f"EWS500I AGENT INSTALLED IN ~/{uss.AGENT}: {version}")
        self.app.refresh_agent()


# ===================================================================== 2 DSLIST
class DslistScreen(Panel):
    PANEL_ID = "EWSDSL"
    PANEL_TITLE = "DATA SET LIST UTILITY"
    PFKEYS = "B=BROWSE  D=DOWNLOAD  U=UPLOAD  C=COUNT(SSH)  F3=END  F5=REFRESH"
    HELP = ("Line commands (move to a data set and press the key):\n"
            "  B or ENTER  browse records (PDS: member list)\n"
            "  D           download to data/downloads/<DSN>.txt\n"
            "  U           upload a local text file into the data set (or a member)\n"
            "  C           count records on z/OS through the SSH agent\n\n"
            "Primary commands:\n"
            "  L <pattern>  list other data sets, e.g. L Z72230.EWS.**  or  L Z72230.*")
    BINDINGS = [Binding("b", "browse", show=False), Binding("s", "browse", show=False),
                Binding("d", "download", show=False), Binding("u", "upload", show=False),
                Binding("c", "count", show=False)]

    def __init__(self):
        super().__init__()
        self.items: dict[str, dict] = {}
        try:
            self.pattern = f"{actions.hlq()}.EWS.**"
        except Exception:
            self.pattern = "*.EWS.**"

    def body(self) -> ComposeResult:
        yield Static(id="dshead")
        yield table("dslist")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#dslist", DataTable).add_columns(
            "DATA SET NAME", "DSORG", "RECFM", "LRECL", "BLKSZ", "USED%", "SIZE", "VOLUME", "CREATED", "REFERENCED")
        self.query_one("#dslist", DataTable).focus()
        self.action_refresh_panel()

    def action_refresh_panel(self) -> None:
        self.query_one("#dshead", Static).update(Text(f"DSLIST - DATA SETS MATCHING {self.pattern}   LOADING ...", style=WHITE))
        self.load()

    @work(thread=True, exclusive=True)
    def load(self) -> None:
        try:
            items = zos.list_datasets(self.pattern)
        except Exception as e:
            self.say_from_thread(f"EWS101E {e}", "E")
            return
        self.app.call_from_thread(self.fill, items)

    def fill(self, items: list[dict]) -> None:
        self.items = {d["dsname"]: d for d in items}
        t = self.query_one("#dslist", DataTable)

        def rows():
            for d in items:
                org = d.get("dsorg") or "?"
                style = TURQ if org.startswith("PO") else GREEN
                t.add_row(Text(d["dsname"], style=f"bold {style}"), org, d.get("recfm") or "", d.get("lrecl") or "",
                          d.get("blksz") or "", d.get("used") or "", d.get("sizex") or "", d.get("vol") or "",
                          d.get("cdate") or "", d.get("rdate") or "", key=d["dsname"])
        keep_cursor(t, rows)
        self.query_one("#dshead", Static).update(Text(
            f"DSLIST - DATA SETS MATCHING {self.pattern}   ROW 1 OF {len(items)}", style=WHITE))

    def command(self, text: str) -> bool:
        p = text.split()
        if p[0].upper() == "L" and len(p) == 2:
            self.pattern = p[1].upper()
            self.action_refresh_panel()
            return True
        return False

    def _selected(self) -> dict | None:
        k = row_key(self.query_one("#dslist", DataTable))
        return self.items.get(k) if k else None

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_browse()

    def action_browse(self) -> None:
        d = self._selected()
        if not d:
            return
        if (d.get("dsorg") or "").startswith("PO"):
            self.app.push_screen(MemberScreen(d))
        elif d.get("dsorg") == "VS":
            self.say("VSAM CLUSTERS ARE NOT BROWSABLE OVER Z/OSMF - USE COMMAND (OPTION 6)", "W")
        else:
            self.app.push_screen(BrowseScreen(d["dsname"], lambda dsn=d["dsname"]: zos.view(dsn, 2000),
                                              note="FIRST 2000 RECORDS"))

    def action_download(self) -> None:
        d = self._selected()
        if d and (d.get("dsorg") or "").startswith("PO"):
            self.say("SELECT A MEMBER (B) TO DOWNLOAD FROM A LIBRARY", "W")
        elif d:
            self.say(f"DOWNLOADING {d['dsname']} ...")
            download(self, d["dsname"])

    def action_upload(self) -> None:
        d = self._selected()
        if d:
            upload_dialog(self, d)

    def action_count(self) -> None:
        d = self._selected()
        if d and not (d.get("dsorg") or "").startswith("PO"):
            self.say(f"COUNTING RECORDS OF {d['dsname']} ON Z/OS (SSH AGENT) ...")
            self.count(d["dsname"])

    @work(thread=True)
    def count(self, dsn: str) -> None:
        try:
            r = uss.agent("count", dsn, timeout=300)
        except Exception as e:
            self.say_from_thread(f"EWS301E {e}", "E")
            return
        if r.get("records") is None:
            self.say_from_thread(f"EWS301E COUNT FAILED: {r.get('error')}", "E")
        else:
            self.say_from_thread(f"EWS300I {dsn} HAS {r['records']:,} RECORDS")


@work(thread=True)
def download(panel: Panel, dsn: str) -> None:
    try:
        text = zos.download_text(dsn)
    except Exception as e:
        panel.say_from_thread(f"EWS101E DOWNLOAD FAILED: {e}", "E")
        return
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = DOWNLOAD_DIR / f"{dsn}.txt"
    path.write_text(text)
    panel.say_from_thread(f"EWS121I {text.count(chr(10)):,} RECORDS DOWNLOADED TO {path}")


def upload_dialog(panel: Panel, d: dict) -> None:
    dsn, lrecl, recfm = d["dsname"], int(d.get("lrecl") or 0), d.get("recfm") or "FB"
    pds = (d.get("dsorg") or "").startswith("PO")
    default = ""
    for i in actions.names().inputs():
        if i["name"] == dsn:
            default = str(INPUT_DIR / i["file"])
    if not default and (DOWNLOAD_DIR / f"{dsn}.txt").exists():
        default = str(DOWNLOAD_DIR / f"{dsn}.txt")
    note = Text()
    note.append(f"Upload a local text file into {dsn}", style=WHITE)
    note.append(f"  ({recfm} {lrecl})\n", style=TURQ)
    note.append("The current content of the target is REPLACED. Lines become records (ASCII -> EBCDIC).",
                style=YELLOW)

    def go(v):
        if not v:
            return
        path, target = Path(v["local"]).expanduser(), v["target"].upper()
        if not path.is_file():
            panel.say(f"EWS120E LOCAL FILE NOT FOUND: {path}", "E")
            return
        lines = path.read_text(encoding="iso-8859-1").splitlines()
        limit = lrecl - 4 if recfm.startswith("V") else lrecl
        long = [n for n, l in enumerate(lines, 1) if limit and len(l) > limit]
        if long:
            panel.say(f"EWS120E LINE {long[0]} IS LONGER THAN LRECL {limit} ({len(long)} LINES TOO LONG)", "E")
            return
        panel.say(f"UPLOADING {len(lines):,} RECORDS TO {target} ...")
        _upload(panel, path, target)

    panel.app.push_screen(FormDialog("UPLOAD", [("local", "LOCAL FILE", default),
                                                 ("target", "TARGET", f"{dsn}(MEMBER)" if pds else dsn)], note), go)


@work(thread=True)
def _upload(panel: Panel, path: Path, target: str) -> None:
    try:
        zos.upload_file(path, target)
    except Exception as e:
        panel.say_from_thread(f"EWS120E UPLOAD FAILED: {e}", "E")
        return
    panel.say_from_thread(f"EWS120I {path.name} UPLOADED TO {target}")


class MemberScreen(Panel):
    PANEL_ID = "EWSMEM"
    PANEL_TITLE = "MEMBER LIST"
    PFKEYS = "B=BROWSE  D=DOWNLOAD  U=UPLOAD  F3=END  F5=REFRESH"
    BINDINGS = [Binding("b", "browse", show=False), Binding("s", "browse", show=False),
                Binding("d", "download", show=False), Binding("u", "upload", show=False)]

    def __init__(self, ds: dict):
        super().__init__()
        self.ds = ds
        self.PANEL_TITLE = f"MEMBER LIST - {ds['dsname']}"

    def body(self) -> ComposeResult:
        yield table("members")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#members", DataTable).add_columns("NAME", "LIBRARY")
        self.query_one("#members", DataTable).focus()
        self.action_refresh_panel()

    @work(thread=True, exclusive=True)
    def action_refresh_panel(self) -> None:
        try:
            members = zos.list_members(self.ds["dsname"])
        except Exception as e:
            self.say_from_thread(f"EWS101E {e}", "E")
            return

        def fill():
            t = self.query_one("#members", DataTable)
            keep_cursor(t, lambda: [t.add_row(Text(m, style=f"bold {TURQ}"), self.ds["dsname"], key=m) for m in members])
            self.say(f"{len(members)} MEMBERS" + ("  (LOAD MODULES CANNOT BE BROWSED)" if self.ds.get("recfm") == "U" else ""))
        self.app.call_from_thread(fill)

    def _member(self) -> str | None:
        m = row_key(self.query_one("#members", DataTable))
        return f"{self.ds['dsname']}({m})" if m else None

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_browse()

    def action_browse(self) -> None:
        m = self._member()
        if m and self.ds.get("recfm") != "U":
            self.app.push_screen(BrowseScreen(m, lambda: zos.view(m)))

    def action_download(self) -> None:
        m = self._member()
        if m and self.ds.get("recfm") != "U":
            download(self, m)

    def action_upload(self) -> None:
        upload_dialog(self, self.ds)


# ===================================================================== browse
RULER = "----+----1----+----2----+----3----+----4----+----5----+----6----+----7----+----8" \
        "----+----9----+----0----+----1----+----2----+----3---"


class BrowseScreen(Panel):
    PANEL_ID = "EWSBRW"
    PFKEYS = "F3=END  F7=UP  F8=DOWN  F10=LEFT  F11=RIGHT   FIND text  TOP  BOT"
    HELP = "FIND <text> finds the next line containing the text (case-insensitive). TOP / BOT jump."
    BINDINGS = [Binding("f7", "page(-1)", show=False), Binding("f8", "page(1)", show=False),
                Binding("f10", "side(-40)", show=False), Binding("f11", "side(40)", show=False)]

    def __init__(self, name: str, loader, note: str = ""):
        super().__init__()
        self.name_, self.loader, self.note = name, loader, note
        self.PANEL_TITLE = f"BROWSE  {name}"
        self.lines: list[str] = []
        self.found = -1

    def body(self) -> ComposeResult:
        yield Static(id="brhead")
        with ScrollableContainer(id="browse"):
            yield Static(id="browse-text")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#brhead", Static).update(Text(f"LOADING {self.name_} ...", style=WHITE))
        self.query_one("#browse").focus()
        self.load()

    @work(thread=True)
    def load(self) -> None:
        try:
            text = self.loader()
        except Exception as e:
            self.say_from_thread(f"EWS101E {e}", "E")
            return
        self.app.call_from_thread(self.show, text.splitlines())

    def show(self, lines: list[str]) -> None:
        self.lines = lines
        width = max([len(l) for l in lines] + [72])
        out = Text(no_wrap=True)
        out.append("=COLS> ", style=TURQ)
        out.append(RULER[:width] + "\n", style=TURQ)
        out.append("****** " + " Top of Data ".center(width, "*") + "\n", style=f"bold {WHITE}")
        for n, l in enumerate(lines, 1):
            out.append(f"{n:06d} ", style=TURQ)
            style = f"bold {YELLOW}" if n - 1 == self.found else GREEN
            out.append(l + "\n", style=style)
        out.append("****** " + " Bottom of Data ".center(width, "*"), style=f"bold {WHITE}")
        self.query_one("#browse-text", Static).update(out)
        self.query_one("#brhead", Static).update(Text(
            f"{self.name_:<44} LINE {len(lines):08d} RECORDS   COL 001 {width:03d}  {self.note}", style=WHITE))

    def action_page(self, d: int) -> None:
        c = self.query_one("#browse")
        c.scroll_to(y=max(0, c.scroll_y + d * (c.size.height - 1)), animate=False)

    def action_side(self, d: int) -> None:
        c = self.query_one("#browse")
        c.scroll_to(x=max(0, c.scroll_x + d), animate=False)

    def command(self, text: str) -> bool:
        p = text.split(None, 1)
        verb = p[0].upper()
        c = self.query_one("#browse")
        if verb in ("TOP", "M") or text.upper() == "M F7":
            c.scroll_home(animate=False)
        elif verb in ("BOT", "BOTTOM"):
            c.scroll_end(animate=False)
        elif verb in ("F", "FIND") and len(p) == 2:
            needle = p[1].strip("'\"").upper()
            start = self.found + 1
            hits = [i for i in list(range(start, len(self.lines))) + list(range(0, start))
                    if needle in self.lines[i].upper()]
            if not hits:
                self.say(f"*** {needle} NOT FOUND ***", "W")
                return True
            self.found = hits[0]
            self.show(self.lines)
            c.scroll_to(y=max(0, self.found + 2 - 3), animate=False)
            self.say(f"CHARS '{needle}' FOUND ON LINE {self.found + 1}")
        else:
            return False
        return True


# ===================================================================== 3 SDSF
class SdsfScreen(Panel):
    PANEL_ID = "EWSSDSF"
    PANEL_TITLE = "SDSF STATUS DISPLAY ALL CLASSES"
    PFKEYS = "S=SELECT  P=PURGE  F3=END  F5=REFRESH   PRE mask  OWNER id"
    HELP = ("S or ENTER shows the job's step return codes and spool data sets.\n"
            "P purges the job output (asks first).\n"
            "PRE EWS*  limits the list to job names starting with EWS; PRE * shows all.\n"
            "OWNER *   shows every owner's jobs; OWNER <userid> one owner's.")
    BINDINGS = [Binding("s", "select", show=False), Binding("p", "purge", show=False)]

    def __init__(self):
        super().__init__()
        self.prefix = "*"
        try:
            self.owner = zosconf.load().user
        except zosconf.NotConfigured:
            self.owner = "*"
        self.jobs: dict[str, dict] = {}

    def body(self) -> ComposeResult:
        yield Static(id="sdhead")
        yield table("jobs")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#jobs", DataTable).add_columns(
            "NP", "JOBNAME", "JOBID", "OWNER", "TYPE", "CLASS", "STATUS", "PHASE", "RETCODE")
        self.query_one("#jobs", DataTable).focus()
        self.action_refresh_panel()
        self.set_interval(20, self.action_refresh_panel)

    def action_refresh_panel(self) -> None:
        self.load()

    @work(thread=True, exclusive=True)
    def load(self) -> None:
        try:
            jobs = zos.list_jobs(owner=self.owner, prefix=self.prefix, max_jobs=200)
        except Exception as e:
            self.say_from_thread(f"EWS101E {e}", "E")
            return
        self.app.call_from_thread(self.fill, jobs)

    def fill(self, jobs: list[dict]) -> None:
        jobs.sort(key=lambda j: j["jobid"][3:] if j["jobid"][:3] in ("JOB", "STC", "TSU") else j["jobid"], reverse=True)
        self.jobs = {j["jobid"]: j for j in jobs}
        t = self.query_one("#jobs", DataTable)

        def rows():
            for j in jobs:
                rc = j.get("retcode") or ""
                color = GREEN if rc in ("CC 0000",) else YELLOW if rc.startswith("CC 000") else \
                    WHITE if not rc else RED
                t.add_row("", Text(j["jobname"], style=f"bold {TURQ}"), j["jobid"], j.get("owner", ""),
                          j.get("type", ""), j.get("class", ""), j.get("status", ""), j.get("phase-name", ""),
                          Text(rc or "-", style=color), key=j["jobid"])
        keep_cursor(t, rows)
        self.query_one("#sdhead", Static).update(Text(
            f"PREFIX={self.prefix}  DEST=(ALL)  OWNER={self.owner}  SORT=JOBID/D   LINE 1-{len(jobs)} ({len(jobs)})",
            style=WHITE))

    def command(self, text: str) -> bool:
        p = text.split()
        verb = p[0].upper()
        if verb in ("PRE", "PREFIX"):
            self.prefix = (p[1] if len(p) > 1 else "*").upper()
        elif verb == "OWNER":
            self.owner = (p[1] if len(p) > 1 else "*").upper()
        else:
            return False
        self.action_refresh_panel()
        return True

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_select()

    def action_select(self) -> None:
        jid = row_key(self.query_one("#jobs", DataTable))
        if jid:
            self.app.push_screen(JobScreen(self.jobs[jid]))

    def action_purge(self) -> None:
        jid = row_key(self.query_one("#jobs", DataTable))
        if not jid:
            return
        j = self.jobs[jid]

        def go(ok):
            if ok:
                self.purge(jid)
        self.app.push_screen(ConfirmDialog("PURGE JOB", f"Purge {j['jobname']}({jid}) and its spool output?"), go)

    @work(thread=True)
    def purge(self, jid: str) -> None:
        try:
            zos.delete_job(jid)
        except Exception as e:
            self.say_from_thread(f"EWS101E {e}", "E")
            return
        oplog.write("EWS110I", f"JOB {jid} PURGED FROM THE TUI")
        self.say_from_thread(f"$HASP250 {jid} PURGED")
        self.load()


class JobScreen(Panel):
    PANEL_ID = "EWSJDS"
    PFKEYS = "S=BROWSE  F3=END  F5=REFRESH"
    BINDINGS = [Binding("s", "select", show=False)]

    def __init__(self, job: dict):
        super().__init__()
        self.job = job
        self.PANEL_TITLE = f"SDSF JOB DATA SET DISPLAY - {job['jobname']} {job['jobid']}"

    def body(self) -> ComposeResult:
        yield Static(id="jobinfo", classes="box")
        yield table("dds")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#jobinfo").border_title = "JOB STEPS"
        self.query_one("#dds", DataTable).add_columns("DDNAME", "STEPNAME", "PROCSTEP", "DSID", "C", "REC-CNT")
        self.query_one("#dds", DataTable).focus()
        self.action_refresh_panel()

    @work(thread=True, exclusive=True)
    def action_refresh_panel(self) -> None:
        jid = self.job["jobid"]
        try:
            files = zos.spool_files(jid)
            steps = zos.step_results(jid) if any(f.get("ddname") == "JESYSMSG" for f in files) else []
            job = zos.job_status(jid)
        except Exception as e:
            self.say_from_thread(f"EWS101E {e}", "E")
            return
        self.app.call_from_thread(self.fill, job, files, steps)

    def fill(self, job: dict, files: list[dict], steps: list[dict]) -> None:
        self.files = {str(f["id"]): f for f in files}
        info = Text()
        info.append(f"{job.get('jobname')} {job.get('jobid')}  OWNER {job.get('owner')}  CLASS {job.get('class')}  "
                    f"STATUS {job.get('status')}  RETCODE ", style=WHITE)
        info.append(f"{job.get('retcode') or '-'}\n", style=f"bold {YELLOW}")
        info.append_text(step_chips(steps) if steps else Text("no step messages (job not run yet or JCL error)", style=DIM))
        self.query_one("#jobinfo", Static).update(info)
        t = self.query_one("#dds", DataTable)
        keep_cursor(t, lambda: [t.add_row(Text(f["ddname"], style=f"bold {TURQ}"), f.get("stepname") or "",
                                          f.get("procstep") or "", str(f["id"]), f.get("class") or "",
                                          str(f.get("record-count") or ""), key=str(f["id"])) for f in files])

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_select()

    def action_select(self) -> None:
        fid = row_key(self.query_one("#dds", DataTable))
        if fid:
            f, jid = self.files[fid], self.job["jobid"]
            self.app.push_screen(BrowseScreen(f"{self.job['jobname']} {jid} {f['ddname']}",
                                              lambda: zos.spool_content(jid, int(fid))))


def step_chips(steps: list[dict], per_line: int = 4) -> Text:
    """JCL steps as a flow: STEP010 0000 -> STEP020 0004 -> ..."""
    t = Text()
    for i, s in enumerate(steps):
        if i and i % per_line == 0:
            t.append("\n")
        elif i:
            t.append(" -> ", style=DIM)
        name = s["step"] + (f".{s['procstep']}" if s.get("procstep") else "")
        t.append(f"{name:<14}", style=WHITE)
        t.append(f"{rc_text(s):>5}", style=f"bold {rc_color(s)}")
    return t


# ===================================================================== 4 PIPELINE
PIPE_ACTIONS = [
    ("1", "test_connection", "Check the z/OSMF logon"),
    ("2", "setup", "Libraries, all sources, compile"),
    ("3", "compile", "Copybooks + COBOL, compile, link"),
    ("4", "upload_sources", "JCL, DFSORT and REXX members"),
    ("5", "generate_data", "New synthetic data, 4 uploads"),
    ("6", "train_model", "EWSBATCH TRAIN x4 + XGBoost"),
    ("7", "run_batch", "EWSBATCH SCORE, score, report"),
    ("8", "reset_data", "Delete EWS data, keep libraries"),
]
PIPE_VERBS = {"TEST": "test_connection", "SETUP": "setup", "COMPILE": "compile", "SOURCES": "upload_sources",
              "GEN": "generate_data", "GENERATE": "generate_data", "TRAIN": "train_model", "RUN": "run_batch",
              "RESET": "reset_data"}


class PipelineScreen(Panel):
    PANEL_ID = "EWSPIPE"
    PANEL_TITLE = "BATCH PIPELINE CONTROL"
    PFKEYS = "1-8=START ACTION  ENTER=SELECT  TAB=NEXT PANE  F3=END   RUN yyyymmdd  TRAIN  GEN n seed"
    HELP = ("Start an action: press its number, or select it and press ENTER, or type it:\n"
            "  TEST  SETUP  COMPILE  SOURCES  GEN [customers] [seed]  TRAIN  RUN [yyyymmdd]  RESET\n\n"
            "Only one action runs at a time across the web backend, this console and the CLI.\n"
            "A run started here runs inside this console: leaving the console aborts it.\n\n"
            "The run history and step timeline refresh by themselves. Select a run to see its\n"
            "steps, the JCL step return codes and the REXX reconciliation checks.")
    BINDINGS = [Binding(k, f"start('{name}')", show=False) for k, name, _ in PIPE_ACTIONS]

    def __init__(self):
        super().__init__()
        self.selected: int | None = None

    def body(self) -> ComposeResult:
        with Horizontal(id="pipe-top"):
            with Vertical(id="actions-box", classes="box"):
                yield table("pactions", show_header=False)
            with Vertical(id="runs-box", classes="box"):
                yield table("runs")
        with Vertical(id="steps-box", classes="box"):
            yield Static(id="flow")
            yield table("steps")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#actions-box").border_title = "ACTIONS"
        self.query_one("#runs-box").border_title = "RUN HISTORY"
        a = self.query_one("#pactions", DataTable)
        a.add_columns("k", "action", "desc")
        for k, name, desc in PIPE_ACTIONS:
            a.add_row(Text(f" {k} ", style=f"bold {WHITE}"), Text(f"{name.upper():<16}", style=TURQ), desc, key=name)
        self.query_one("#runs", DataTable).add_columns("RUN", "ACTION", "FROM", "STATUS", "STARTED", "ELAPSED", "MESSAGE")
        self.query_one("#steps", DataTable).add_columns("#", "STEP", "STATUS", "START", "TIME", "DETAIL")
        self.selected = runner.active_run_id()
        a.focus()
        self.reload()
        self.set_interval(1.5, self.reload)

    def reload(self) -> None:
        runs = runner.list_runs(limit=40)
        t = self.query_one("#runs", DataTable)

        def rows():
            for r in runs:
                st = r["status"]
                t.add_row(f"#{r['id']}", r["action"].upper(), r.get("source") or "-",
                          Text(st.upper(), style=f"bold {STATE_COLOR.get(st, WHITE)}"),
                          hhmmss(r["started_at"]), elapsed(r["started_at"], r["finished_at"]),
                          Text((r.get("error") or "")[:40], style=RED), key=str(r["id"]))
        if self.focused is not t:   # do not move the list under the operator's cursor
            keep_cursor(t, rows)
        if self.selected is None and runs:
            self.selected = runs[0]["id"]
        self.draw_run()

    def draw_run(self) -> None:
        box = self.query_one("#steps-box")
        run = runner.get_run(self.selected) if self.selected else None
        steps_t = self.query_one("#steps", DataTable)
        if not run:
            box.border_title = "RUN STEPS"
            steps_t.clear()
            return
        box.border_title = (f"RUN #{run['id']} {run['action'].upper()} - {run['status'].upper()} - "
                            f"{elapsed(run['started_at'], run['finished_at'])}"
                            + (f" - {json.dumps(run['params'])}" if run["params"] else ""))

        def rows():
            for s in run["steps"]:
                st = s["status"]
                mark = {"ok": "✓", "failed": "✗", "running": "►", "skipped": "-", "pending": "·"}.get(st, " ")
                steps_t.add_row(f"{s['seq'] + 1:>2}", Text(f"{mark} {s['name']}", style=WHITE if st != "pending" else DIM),
                                Text(st.upper(), style=f"bold {STATE_COLOR.get(st, WHITE)}"),
                                hhmmss(s["started_at"]) if s["started_at"] else "",
                                elapsed(s["started_at"], s["finished_at"]) if s["started_at"] else "",
                                Text((s["detail"] or "")[:110], style=RED if st == "failed" else GREEN))
        keep_cursor(steps_t, rows)

        flow = Text()
        for s in run["steps"]:
            d = s["data"] or {}
            if d.get("steps"):
                flow.append(f"{d.get('jobname', 'JOB')} {d.get('jobid', '')}  ", style=f"bold {TURQ}")
                flow.append(f"{d.get('retcode') or ''}\n", style=f"bold {YELLOW}")
                flow.append_text(step_chips(d["steps"], per_line=5))
                flow.append("\n")
            rc = d.get("runctl")
            if rc:
                flow.append("RECON  ", style=f"bold {TURQ}")
                for k, v in rc.items():
                    if k.startswith("CHK_") or k == "STATUS":
                        flow.append(f"{k.replace('CHK_', '')}=", style=WHITE)
                        flow.append(f"{v} ", style=GREEN if v == "OK" else RED)
                flow.append(f" FEATURES={rc.get('FEATURES')}\n", style=WHITE)
        self.query_one("#flow", Static).update(flow)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "runs" and event.row_key is not None:
            self.selected = int(event.row_key.value)
            self.draw_run()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "pactions":
            self.action_start(event.row_key.value)

    def command(self, text: str) -> bool:
        p = text.split()
        name = PIPE_VERBS.get(p[0].upper())
        if not name:
            return False
        self.action_start(name, p[1:])
        return True

    def action_start(self, name: str, args: list[str] | None = None) -> None:
        args = args or []
        busy = runner.active_run_id()
        if busy:
            self.say(f"EWS200E RUN #{busy} IS STILL ACTIVE - ONE ACTION AT A TIME", "E")
            return
        label = name.upper()
        if name == "run_batch":
            asof = args[0] if args else str(SCORE_ASOF)
            fields = [("asof", "AS-OF DATE", asof)]
            note = "EWSBATCH (SCORE) -> load master data -> score + SHAP -> write EWS.SCORES -> EWSRPTJ"
            self.app.push_screen(FormDialog(label, fields, note), lambda v: v and self._start(name, v))
        elif name == "generate_data":
            fields = [("customers", "CUSTOMERS", args[0] if args else "1500"), ("seed", "SEED", args[1] if len(args) > 1 else "42")]
            note = Text("Replaces the 4 input data sets on the mainframe with new synthetic data.", style=YELLOW)
            self.app.push_screen(FormDialog(label, fields, note), lambda v: v and self._start(name, v))
        elif name == "reset_data":
            self.app.push_screen(ConfirmDialog(label, Text(
                "Deletes every EWS data set on the mainframe except the JCL, copybook,\n"
                "DFSORT and REXX libraries.", style=YELLOW), require="RESET"),
                lambda ok: ok and self._start(name, {"confirm": True}))
        elif name == "test_connection":
            self._start(name, {})
        else:
            desc = next(d for _, n, d in PIPE_ACTIONS if n == name)
            self.app.push_screen(ConfirmDialog(label, f"{desc}.\n\nStart {label} on the mainframe?"),
                                 lambda ok: ok and self._start(name, {}))

    def _start(self, name: str, params: dict) -> None:
        try:
            if name == "run_batch":
                params = {"asof": actions.validate_asof(params["asof"])}
            elif name == "generate_data":
                params = {"customers": int(params["customers"]), "seed": int(params["seed"])}
                if not 200 <= params["customers"] <= 3000:
                    raise ValueError("CUSTOMERS MUST BE 200-3000")
            run_id = runner.start(name, actions.ACTIONS[name]["fn"], params, source="TUI")
        except (ValueError, runner.ActionError, runner.Busy) as e:
            self.say(f"EWS200E {str(e).upper() or 'INVALID PARAMETERS'}", "E")
            return
        self.app.started_runs.add(run_id)
        self.selected = run_id
        self.say(f"EWS200I RUN #{run_id} {name.upper()} STARTED")
        self.reload()


# ===================================================================== 5 SYSLOG
def syslog_line(r: dict) -> Text:
    color = {"E": RED, "W": YELLOW}.get(r["level"], GREEN)
    t = Text(no_wrap=True)
    t.append(f"{julian(r['ts'])} ", style=TURQ)
    t.append(f"{r['msgid']:<8}", style=f"bold {color if r['level'] != 'I' else WHITE}")
    t.append(f"{(r['channel'] or ''):<6}", style=BLUE)
    t.append(r["text"] or "", style=color)
    if r.get("ms") is not None:
        t.append(f"  ({r['ms']} MS)", style=DIM)
    return t


class SyslogScreen(Panel):
    PANEL_ID = "EWSLOG"
    PANEL_TITLE = "SYSTEM LOG"
    PFKEYS = "F3=END   ERR=ERRORS ONLY  ALL  CLEAR   FROM web backend, console and CLI"
    HELP = ("Every z/OSMF request, SSH command, job, run step and connection change, from every\n"
            "process (web backend, this console, CLI). Errors red, warnings yellow.\n\n"
            "Message IDs:  EWS1xx z/OSMF   EWS2xx runs   EWS3xx SSH   EWS4xx channels   EWS5xx logon\n"
            "ERR shows only warnings and errors, ALL shows everything, CLEAR empties the display.")

    def __init__(self):
        super().__init__()
        self.errors_only = False
        self.last = 0

    def body(self) -> ComposeResult:
        yield Static(id="loghead")
        yield RichLog(id="syslog", markup=False, wrap=False, max_lines=5000)

    def on_mount(self) -> None:
        super().on_mount()
        self.reload()
        self.set_interval(1, self.poll)
        self.query_one("#syslog").focus()

    def reload(self) -> None:
        log = self.query_one("#syslog", RichLog)
        log.clear()
        rows = oplog.read(limit=1000, errors_only=self.errors_only)
        for r in rows:
            log.write(syslog_line(r))
        self.last = rows[-1]["id"] if rows else (db.query("SELECT MAX(id) AS m FROM oplog")[0]["m"] or 0)
        self.head()

    def head(self) -> None:
        c = db.query("SELECT level, COUNT(*) AS n FROM oplog GROUP BY level")
        n = {r["level"]: r["n"] for r in c}
        t = Text()
        t.append(f"SYSLOG  SYSTEM {self.app.sysname()}  FILTER={'ERRORS' if self.errors_only else 'ALL'}   ", style=WHITE)
        t.append(f"INFO {n.get('I', 0)}  ", style=GREEN)
        t.append(f"WARN {n.get('W', 0)}  ", style=YELLOW)
        t.append(f"ERROR {n.get('E', 0)}", style=RED)
        self.query_one("#loghead", Static).update(t)

    def poll(self) -> None:
        rows = oplog.read(after_id=self.last, limit=500, errors_only=self.errors_only)
        if rows:
            log = self.query_one("#syslog", RichLog)
            for r in rows:
                log.write(syslog_line(r))
            self.last = rows[-1]["id"]
            self.head()

    def command(self, text: str) -> bool:
        verb = text.split()[0].upper()
        if verb in ("ERR", "ERRORS"):
            self.errors_only = True
        elif verb == "ALL":
            self.errors_only = False
        elif verb == "CLEAR":
            self.query_one("#syslog", RichLog).clear()
            return True
        else:
            return False
        self.reload()
        return True

    def action_refresh_panel(self) -> None:
        self.reload()


# ===================================================================== 6 COMMAND
class ShellScreen(Panel):
    PANEL_ID = "EWSCMD"
    PANEL_TITLE = "COMMAND SHELL - USS / TSO / CONSOLE"
    PFKEYS = "F3=END  UP/DOWN=HISTORY  =N=JUMP TO OPTION N   TSO cmd   /console cmd   CLEAR"
    HELP = ("Everything typed on the command line runs on z/OS over the SSH channel:\n"
            "  <text>          z/OS UNIX shell command (zsh; ZOAU on PATH)  e.g. dls 'Z72230.EWS.*'\n"
            "  TSO <command>   TSO/E command through tsocmd                 e.g. TSO LISTCAT LEVEL(Z72230.EWS)\n"
            "  /<command>      operator console command through opercmd    e.g. /D IPLINFO   /D T   /D A,L\n"
            "  CLEAR           clear the output\n"
            "Use =N to jump to another option (the bare option names run as shell commands here).")
    BINDINGS = [Binding("up", "history(-1)", show=False), Binding("down", "history(1)", show=False)]

    def __init__(self, first: str | None = None):
        super().__init__()
        self.first = first
        self.hist: list[str] = []
        self.hpos = 0

    def body(self) -> ComposeResult:
        yield RichLog(id="out", markup=False, wrap=False, max_lines=5000)

    def on_mount(self) -> None:
        super().on_mount()
        out = self.query_one("#out", RichLog)
        for line in ("Commands run on z/OS over SSH. Examples:",
                     "   dls 'Z72230.EWS.*'          ZOAU data set list",
                     "   jls                          ZOAU job list",
                     "   TSO LISTCAT LEVEL(Z72230.EWS) TSO/E command",
                     "   /D IPLINFO                   operator console command", ""):
            out.write(Text(line, style=TURQ))
        self.query_one("#cmd", Input).focus()
        if self.first:
            self.command(self.first)

    def command(self, text: str) -> bool:
        if text.upper() == "CLEAR":
            self.query_one("#out", RichLog).clear()
            return True
        self.hist.append(text)
        self.hpos = len(self.hist)
        if text.upper().startswith("TSO "):
            shell, kind = f"tsocmd {shlex.quote(text[4:].strip())} 2>&1", "TSO"
        elif text.startswith("/"):
            shell, kind = f"opercmd {shlex.quote(text[1:].strip())} 2>&1", "CONSOLE"
        else:
            shell, kind = text, "USS"
        try:
            user = zosconf.load().user
        except zosconf.NotConfigured:
            user = "?"
        self.query_one("#out", RichLog).write(Text(f"{user} {kind}> {text}", style=f"bold {WHITE}"))
        self.say(f"RUNNING ON Z/OS ({kind}) ...")
        self.execute(shell)
        return True

    @work(thread=True)
    def execute(self, shell: str) -> None:
        out = self.query_one("#out", RichLog)
        try:
            r = uss.run(shell, timeout=180)
        except Exception as e:
            self.app.call_from_thread(out.write, Text(str(e), style=RED))
            self.say_from_thread(f"EWS301E {e}", "E")
            return

        def show():
            for line in r["out"].splitlines():
                out.write(Text(line, style=GREEN))
            for line in r["err"].splitlines():
                out.write(Text(line, style=RED))
            out.write(Text(f"RC={r['rc']}  {r['ms']} MS", style=YELLOW if r["rc"] else DIM))
            out.write(Text(""))
            self.say(f"EWS300I COMMAND ENDED RC={r['rc']} IN {r['ms']} MS", "I" if r["rc"] == 0 else "W")
        self.app.call_from_thread(show)

    def action_history(self, d: int) -> None:
        if not self.hist:
            return
        self.hpos = max(0, min(len(self.hist), self.hpos + d))
        cmd = self.query_one("#cmd", Input)
        cmd.value = self.hist[self.hpos] if self.hpos < len(self.hist) else ""
        cmd.cursor_position = len(cmd.value)


# ===================================================================== 7 REPORTS
class ReportsScreen(Panel):
    PANEL_ID = "EWSRPT"
    PANEL_TITLE = "BATCH REPORTS"
    PFKEYS = "F3=END  F5=REFRESH   RUN n  RPT=FULL REPORT  REJ=REJECTS  EXC=EXCEPTIONS"
    HELP = ("Reports of a scoring run, from the files the run downloaded from z/OS:\n"
            "  RECONCILIATION   EWS.RUNCTL written by the REXX exec EWSRECON\n"
            "  REJECTS          EWS.REJECTS + EWS.EXCEPT grouped by reason code\n"
            "  INTERVENTION     EWS.RISKRPT printed by the COBOL program EWSRPT\n"
            "RUN n picks another run; RPT, REJ and EXC open the full text.")

    def __init__(self):
        super().__init__()
        self.run_id = db.kv_get("last_score_run")

    def body(self) -> ComposeResult:
        yield Static(id="rpthead")
        with Horizontal(id="rpt-top"):
            with Vertical(classes="box", id="recon-box"):
                yield table("recon")
            with Vertical(classes="box", id="rej-box"):
                yield table("rej")
        with Vertical(classes="box", id="list-box"):
            yield table("ilist")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#recon-box").border_title = "RECONCILIATION - EWS.RUNCTL (REXX EWSRECON)"
        self.query_one("#rej-box").border_title = "REJECTS AND EXCEPTIONS"
        self.query_one("#list-box").border_title = "EARLY INTERVENTION LIST - EWS.RISKRPT (COBOL EWSRPT)"
        self.query_one("#recon", DataTable).add_columns("KEY", "VALUE")
        self.query_one("#rej", DataTable).add_columns("CODE", "SOURCE", "REASON", "COUNT")
        self.query_one("#ilist", DataTable).add_columns("RANK", "CUSTOMER", "RISK %", "TIER", "ACTN", "TOTAL EMI", "TOP RISK FACTOR")
        self.query_one("#ilist", DataTable).focus()
        self.action_refresh_panel()

    def _file(self, pattern: str) -> Path | None:
        return next((RUNS_DIR / str(self.run_id)).glob(pattern), None) if self.run_id else None

    def action_refresh_panel(self) -> None:
        if not self.run_id:
            self.query_one("#rpthead", Static).update(Text("NO SCORING RUN YET - START RUN ON THE PIPELINE PANEL (=4)", style=YELLOW))
            return
        run = runner.get_run(self.run_id)
        head = Text()
        head.append(f"RUN #{self.run_id} {run['action'].upper() if run else '?'}  ", style=f"bold {WHITE}")
        if run:
            sm = run["summary"] or {}
            head.append(f"STATUS {run['status'].upper()}  AS-OF {sm.get('asof', '-')}  BATCH JOB {sm.get('batch_job', '-')}  "
                        f"REPORT JOB {sm.get('report_job', '-')}  SCORED {sm.get('scored', '-')}", style=WHITE)
        self.query_one("#rpthead", Static).update(head)

        rc = self._file("*/runctl.txt")
        values = actions.parse_runctl(rc.read_text()) if rc else {}
        t = self.query_one("#recon", DataTable)
        t.clear()
        for k, v in values.items():
            style = (GREEN if v == "OK" else RED) if k.startswith("CHK_") or k == "STATUS" else WHITE
            t.add_row(Text(k, style=TURQ), Text(str(v), style=style))

        counts: dict = {}
        for kind in ("rejects", "exceptions"):
            p = self._file(f"*/{kind}.txt")
            for r in actions.parse_rejects(p.read_text()) if p else []:
                key = (r["reason_code"], r["source"], r["reason_text"])
                counts[key] = counts.get(key, 0) + 1
        t = self.query_one("#rej", DataTable)
        t.clear()
        for (code, src, text), n in sorted(counts.items()):
            t.add_row(Text(code, style=f"bold {YELLOW}"), src, text, f"{n:>6}")

        rp = RUNS_DIR / str(self.run_id) / "riskrpt.txt"
        rows = actions.parse_riskrpt(rp.read_text().splitlines()) if rp.exists() else []
        t = self.query_one("#ilist", DataTable)
        t.clear()
        tier_color = {"HIGH": PINK, "MEDIUM": YELLOW, "LOW": GREEN}
        for r in rows:
            t.add_row(f"{r['rank']:>5}", Text(r["cust_id"], style=f"bold {TURQ}"), f"{r['risk_pct']:6.2f}",
                      Text(r["tier"], style=f"bold {tier_color[r['tier']]}"), r["action"],
                      f"{r['total_emi']:>12,.2f}", r["top_factor"])
        if not rows:
            self.say("NO INTERVENTION REPORT IN THIS RUN", "W")

    def command(self, text: str) -> bool:
        p = text.split()
        verb = p[0].upper()
        if verb == "RUN" and len(p) == 2 and p[1].lstrip("#").isdigit():
            self.run_id = int(p[1].lstrip("#"))
            self.action_refresh_panel()
        elif verb in ("RPT", "REJ", "EXC"):
            f = {"RPT": "riskrpt.txt", "REJ": "*/rejects.txt", "EXC": "*/exceptions.txt"}[verb]
            path = self._file(f)
            if not path or not path.exists():
                self.say("NOT IN THIS RUN", "W")
            else:
                self.app.push_screen(BrowseScreen(f"RUN #{self.run_id} {path.name}", path.read_text, note="LOCAL COPY"))
        else:
            return False
        return True
