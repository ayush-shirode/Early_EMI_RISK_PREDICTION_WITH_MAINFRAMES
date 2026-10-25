"""Thin wrapper around Zowe CLI. Every mainframe operation in the project goes through here.

Each call runs `zowe ... --rfj` (response format JSON) and returns the parsed `data`.
Credentials come from the Zowe team configuration and its secure store; nothing
secret is passed on the command line or stored by this project.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path


class ZoweError(RuntimeError):
    pass


ZOWE = shutil.which("zowe") or "zowe"


TRANSIENT = ("Failed to send an HTTP request", "ECONNRESET", "ETIMEDOUT", "socket hang up", "EAI_AGAIN")


def run(*args: str, timeout: int = 180, retries: int = 3) -> object:
    """Run one Zowe CLI command. Network hiccups to the remote system are retried."""
    cmd = [ZOWE, *args, "--rfj"]
    for attempt in range(1, retries + 1):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise ZoweError(f"zowe {' '.join(args[:3])} timed out after {timeout}s") from e
        except FileNotFoundError as e:
            raise ZoweError("Zowe CLI not found on PATH. Install it with: npm i -g @zowe/cli") from e
        try:
            resp = json.loads(p.stdout)
        except json.JSONDecodeError as e:
            raise ZoweError((p.stderr or p.stdout or "no output").strip()[:2000]) from e
        if resp.get("success", False):
            return resp.get("data")
        msg = re.sub(r"\x1b\[[0-9;]*m", "", str(resp.get("message") or resp.get("stderr") or "Zowe command failed"))
        if attempt < retries and any(t in msg for t in TRANSIENT):
            time.sleep(2 * attempt)
            continue
        raise ZoweError(f"{msg.strip()[:2000]} (zowe {' '.join(args[:4])})")


# ---------------------------------------------------------------- connection
def check_status() -> dict:
    """z/OSMF reachability, user ID and system info."""
    cmd = [ZOWE, "zosmf", "check", "status", "--rfj"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    resp = json.loads(p.stdout or "{}")
    if not resp.get("success"):
        raise ZoweError(re.sub(r"\x1b\[[0-9;]*m", "", resp.get("message", p.stderr)).strip()[:1000])
    m = re.search(r"user (\S+) successfully connected to z/OSMF on '([^']+)'", resp.get("stdout", ""))
    data = resp.get("data") or {}
    return {
        "user": m.group(1).upper() if m else None,
        "system": m.group(2) if m else data.get("zosmf_hostname"),
        "zos_version": data.get("zos_version"),
        "zosmf_version": data.get("zosmf_full_version"),
        "port": data.get("zosmf_port"),
    }


# ---------------------------------------------------------------- data sets
def list_datasets(pattern: str) -> list[dict]:
    data = run("zos-files", "list", "data-set", pattern, "-a")
    return (data or {}).get("apiResponse", {}).get("items", [])


def list_members(pds: str) -> list[str]:
    data = run("zos-files", "list", "all-members", pds)
    return [i["member"] for i in (data or {}).get("apiResponse", {}).get("items", [])]


def exists(dsn: str) -> bool:
    return any(d["dsname"] == dsn.upper() for d in list_datasets(dsn))


def create_library(dsn: str, recfm: str, lrecl: int) -> None:
    if recfm == "U":
        run("zos-files", "create", "data-set-binary", dsn, "--dst", "LIBRARY", "--size", "15TRK")
    else:
        run("zos-files", "create", "data-set-partitioned", dsn, "--dst", "LIBRARY",
            "--rf", recfm, "--rl", str(lrecl), "--size", "5TRK", "--db", "20")


def create_sequential(dsn: str, recfm: str, lrecl: int, size: str) -> None:
    run("zos-files", "create", "data-set-sequential", dsn, "--rf", recfm, "--rl", str(lrecl),
        "--bs", str(27920 if lrecl == 80 else 27900 if lrecl == 100 else 0), "--size", size)


def delete(dsn: str) -> None:
    run("zos-files", "delete", "data-set", dsn, "-f")


def upload_file(local: Path, target: str) -> None:
    """Text-mode upload (ASCII -> EBCDIC). `target` is DSN or PDS(MEMBER)."""
    try:
        run("zos-files", "upload", "file-to-data-set", str(local), target, timeout=600)
    except ZoweError as e:
        if "Failed to send an HTTP request" in str(e):
            raise ZoweError(
                f"Upload of {local.name} to {target} was cut off by the server. If it keeps failing for this "
                "file, the Z Xplore network filter is rejecting its content (it flags text that looks like SQL "
                "injection, e.g. SELECT together with ' NAME=' literals); reword that text."
            ) from e
        raise


def download(dsn: str, local: Path) -> Path:
    local.parent.mkdir(parents=True, exist_ok=True)
    run("zos-files", "download", "data-set", dsn, "-f", str(local), "--overwrite", timeout=600)
    return local


def view(dsn: str, max_records: int | None = None) -> str:
    """Content of a (small) data set as text. Use download() for large ones."""
    args = ["zos-files", "view", "data-set", dsn]
    if max_records:
        args += ["--range", f"0,{max_records}"]
    data = run(*args, timeout=120) or {}
    return data.get("commandResponse", "") if isinstance(data, dict) else str(data)


# ---------------------------------------------------------------- jobs
def submit(member_dsn: str, symbols: dict | None = None, wait: bool = True, timeout: int = 900) -> dict:
    args = ["zos-jobs", "submit", "data-set", member_dsn]
    if symbols:
        # Zowe passes JCL symbols as one space-separated string: "A=1 B=2"
        args += ["--js", " ".join(f"{k}={v}" for k, v in symbols.items())]
    if wait:
        args.append("--wfo")
    return run(*args, timeout=timeout)


def job_status(jobid: str) -> dict:
    return run("zos-jobs", "view", "job-status-by-jobid", jobid)


def spool_files(jobid: str) -> list[dict]:
    return run("zos-jobs", "list", "spool-files-by-jobid", jobid) or []


def spool_content(jobid: str, file_id: int) -> str:
    return run("zos-jobs", "view", "spool-file-by-id", jobid, str(file_id), timeout=120) or ""


_STEP_RE = re.compile(
    r"IEF142I (\S+) (\S+)(?: (\S+))? - STEP WAS EXECUTED - COND CODE (\d{4})"
    r"|IEF272I (\S+) (\S+)(?: (\S+))? - STEP WAS NOT EXECUTED"
    r"|IEF472I (\S+) (\S+)(?: (\S+))? - COMPLETION CODE - SYSTEM=(\w+) USER=(\w+)"
)


def step_results(jobid: str) -> list[dict]:
    """Per-step outcome parsed from the JESYSMSG spool file (IEF142I/IEF272I/IEF472I)."""
    msg = next((f for f in spool_files(jobid) if f.get("ddname") == "JESYSMSG"), None)
    if not msg:
        return []
    text = spool_content(jobid, msg["id"])
    steps: list[dict] = []
    for m in _STEP_RE.finditer(text):
        if m.group(1):
            steps.append({"step": m.group(2), "procstep": m.group(3), "rc": int(m.group(4)), "status": "executed"})
        elif m.group(5):
            steps.append({"step": m.group(6), "procstep": m.group(7), "rc": None, "status": "not executed"})
        else:
            sys_code, user_code = m.group(11), m.group(12)
            abend = f"S{sys_code}" if sys_code != "000" else f"U{user_code}"
            steps.append({"step": m.group(9), "procstep": m.group(10), "rc": None,
                          "status": "abended", "abend": abend})
    return steps


def delete_job(jobid: str) -> None:
    run("zos-jobs", "delete", "job", jobid)
