"""ISPF-style panel frame shared by every screen, and the pop-up dialogs.

Every panel looks like a 3270 ISPF panel:

    EWSDSL ------------------- DATA SET LIST ------------------- S0W1
    COMMAND ===> ________________________________ SCROLL ===> CSR
    <message line>
    <body>
    F1=HELP  F3=END  F5=REFRESH ...
    <status line: channels, user, active run, clock>
"""
from __future__ import annotations

from datetime import datetime, timezone

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Input, Static

GREEN, TURQ, WHITE, YELLOW, RED, BLUE, PINK, DIM = (
    "#3ce65a", "#40e0d0", "#f2f2f2", "#ffff55", "#ff5555", "#6f8fff", "#ff79c6", "#2a6b3a")

STATE_COLOR = {"UP": GREEN, "DOWN": RED, "UNKNOWN": YELLOW, "NOKEY": YELLOW, "NOLOGON": YELLOW,
               "ok": GREEN, "running": YELLOW, "failed": RED, "pending": DIM, "skipped": DIM}


def local_time(iso: str | None) -> datetime | None:
    if not iso:
        return None
    t = datetime.fromisoformat(iso)
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone()


def julian(iso: str | None) -> str:
    """z/OS SYSLOG style timestamp: 2026301 12:04:36."""
    t = local_time(iso)
    return t.strftime("%Y%j %H:%M:%S") if t else "-------  --:--:--"


def hhmmss(iso: str | None) -> str:
    t = local_time(iso)
    return t.strftime("%H:%M:%S") if t else "--:--:--"


def elapsed(a: str | None, b: str | None = None) -> str:
    if not a:
        return ""
    end = local_time(b) if b else datetime.now().astimezone()
    s = max(0, int((end - local_time(a)).total_seconds()))
    return f"{s // 3600}h{s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m{s % 60:02d}s" if s >= 60 else f"{s}s"


def rc_color(step: dict) -> str:
    if step.get("status") == "abended":
        return RED
    if step.get("status") == "not executed":
        return DIM
    rc = step.get("rc") or 0
    return GREEN if rc == 0 else YELLOW if rc <= 4 else RED


def rc_text(step: dict) -> str:
    if step.get("status") == "abended":
        return step.get("abend", "ABEND")
    if step.get("status") == "not executed":
        return "FLUSH"
    return f"{step.get('rc', 0):04d}"


class Panel(Screen):
    """Base class: title line, command line, message line, body, PF-key line, status line."""

    PANEL_ID = "EWS"
    PANEL_TITLE = ""
    PFKEYS = "F1=HELP  F3=END  F5=REFRESH"
    HELP = ""
    BINDINGS = [
        Binding("f3", "end", show=False),
        Binding("escape", "end", show=False),
        Binding("f1", "help", show=False),
        Binding("f5", "refresh_panel", show=False),
        Binding("colon", "focus_cmd", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Static(id="title")
        with Horizontal(id="cmdrow"):
            yield Static("COMMAND ===>", classes="label")
            yield Input(id="cmd")
            yield Static(" SCROLL ===> CSR ", id="scroll")
        yield Static(id="msgline")
        with Container(id="body"):
            yield from self.body()
        yield Static(id="pfkeys")
        yield Static(id="statusline")

    def body(self) -> ComposeResult:
        return iter(())

    def on_mount(self) -> None:
        self.query_one("#pfkeys", Static).update(f"{self.PFKEYS}  :=COMMAND")
        self.draw_title()
        self.app.refresh_status()

    def on_resize(self) -> None:
        self.draw_title()

    def draw_title(self) -> None:
        width = max(self.size.width, 60)
        left, right = self.PANEL_ID, self.app.sysname()
        mid = f" {self.PANEL_TITLE} "
        dashes = max(2, width - len(left) - len(right) - len(mid) - 2)
        line = Text()
        line.append(left, style=f"bold {WHITE}")
        line.append(" " + "-" * (dashes // 2), style=BLUE)
        line.append(mid, style=f"bold {WHITE}")
        line.append("-" * (dashes - dashes // 2) + " ", style=BLUE)
        line.append(right, style=f"bold {TURQ}")
        self.query_one("#title", Static).update(line)

    def say(self, text: str, level: str = "I") -> None:
        """ISPF message line. level I = info, W = warning, E = error."""
        color = {"I": WHITE, "W": YELLOW, "E": RED}.get(level, WHITE)
        self.query_one("#msgline", Static).update(Text(text, style=f"bold {color}" if level == "E" else color))

    def say_from_thread(self, text: str, level: str = "I") -> None:
        self.app.call_from_thread(self.say, text, level)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "cmd":
            return
        text = event.value.strip()
        event.input.value = ""
        if not text:
            self.action_refresh_panel()
            return
        self.app.run_command(text, self)

    def command(self, text: str) -> bool:
        """Panel-specific primary commands. Return True if handled."""
        return False

    def action_end(self) -> None:
        self.app.end_panel()

    def action_help(self) -> None:
        self.app.push_screen(TextDialog(f"HELP - {self.PANEL_TITLE}", self.HELP or "No help for this panel."))

    def action_refresh_panel(self) -> None:
        pass

    def action_focus_cmd(self) -> None:
        self.query_one("#cmd", Input).focus()


# ------------------------------------------------------------------ dialogs
class _Dialog(ModalScreen):
    BINDINGS = [Binding("f3", "cancel", show=False), Binding("escape", "cancel", show=False),
                Binding("f12", "cancel", show=False)]

    def __init__(self, title: str):
        super().__init__()
        self.dialog_title = title

    def on_mount(self) -> None:
        self.query_one("#dialog").border_title = self.dialog_title

    def action_cancel(self) -> None:
        self.dismiss(None)


class TextDialog(_Dialog):
    BINDINGS = [Binding("enter", "cancel", show=False)]

    def __init__(self, title: str, text: str | Text):
        super().__init__(title)
        self.text = text

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self.text)
            yield Static("ENTER/F3=CLOSE", classes="hint")


class ConfirmDialog(_Dialog):
    """Enter confirms. With `require`, the operator must type that word first."""

    BINDINGS = [Binding("enter", "confirm", show=False)]

    def __init__(self, title: str, message: str | Text, require: str | None = None):
        super().__init__(title)
        self.message, self.require = message, require

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self.message)
            if self.require:
                with Horizontal(classes="field"):
                    yield Static(f"TYPE {self.require} ===>", classes="label")
                    yield Input(id="require")
            yield Static("ENTER=CONFIRM  F3=CANCEL", classes="hint")

    def on_mount(self) -> None:
        super().on_mount()
        if self.require:
            self.query_one("#require", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_confirm()

    def action_confirm(self) -> None:
        if self.require and self.query_one("#require", Input).value.strip().upper() != self.require:
            self.query_one(".hint", Static).update(Text(f"TYPE {self.require} TO CONFIRM, F3 TO CANCEL", style=YELLOW))
            return
        self.dismiss(True)


class FormDialog(_Dialog):
    """A few labelled input fields; Enter returns {key: value}."""

    def __init__(self, title: str, fields: list[tuple[str, str, str]], note: str | Text = ""):
        super().__init__(title)
        self.fields, self.note = fields, note

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            if self.note:
                yield Static(self.note)
            for key, label, default in self.fields:
                with Horizontal(classes="field"):
                    yield Static(f"{label} ===>", classes="label")
                    yield Input(value=str(default), id=f"f-{key}")
            yield Static("ENTER=CONFIRM  F3=CANCEL", classes="hint")

    def on_mount(self) -> None:
        super().on_mount()
        self.query(Input).first().focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss({key: self.query_one(f"#f-{key}", Input).value.strip() for key, _, _ in self.fields})
