"""Second, independent channel to the mainframe: SSH into z/OS UNIX System Services (USS).

z/OSMF (pipeline/zos.py) carries the batch pipeline. This channel is for the operator:
running USS shell, TSO and ZOAU commands, and calling our own agent on z/OS
(mainframe/uss/ewsagent.py, installed into ~/ews on USS), which answers in JSON.

Authentication: an SSH key if the server accepts one, otherwise the same password as
z/OSMF from the keyring. The z/OS host key is pinned in ~/.config/ews/known_hosts the
first time (see install_host_key) and checked on every later connection.
"""
from __future__ import annotations

import json
import shlex
import threading
import time
from pathlib import Path

import paramiko

from pipeline import oplog, zosconf

AGENT_SRC = Path(__file__).resolve().parents[1] / "mainframe" / "uss" / "ewsagent.py"
AGENT_DIR = "ews"                      # relative to the USS home directory
AGENT = f"{AGENT_DIR}/ewsagent.py"

# Non-interactive SSH sessions do not read the login profile: set what ZOAU and Python need.
ENV = ("export PATH=/usr/lpp/IBM/zoautil/bin:/z/bin:/bin:/usr/sbin:$PATH "
       "LIBPATH=/usr/lpp/IBM/zoautil/lib:$LIBPATH ZOAU_HOME=/usr/lpp/IBM/zoautil "
       "_BPXK_AUTOCVT=ON _CEE_RUNOPTS='FILETAG(AUTOCVT,AUTOTAG) POSIX(ON)' "
       "_TAG_REDIR_IN=txt _TAG_REDIR_OUT=txt _TAG_REDIR_ERR=txt; ")


class UssError(RuntimeError):
    pass


_lock = threading.Lock()
_client: dict = {"ssh": None, "key": None}


def _connect() -> paramiko.SSHClient:
    s = zosconf.load()
    key = (s.host, s.ssh_port, s.user, zosconf.generation())
    c = _client["ssh"]
    if c is not None and _client["key"] == key and c.get_transport() and c.get_transport().is_active():
        return c
    if c is not None:
        c.close()
    if not zosconf.KNOWN_HOSTS.exists():
        raise UssError("The z/OS SSH host key is not trusted yet. Run: make login-ssh (or SSHKEY in the TUI).")
    ssh = paramiko.SSHClient()
    ssh.load_host_keys(str(zosconf.KNOWN_HOSTS))
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    t0 = time.monotonic()
    try:
        ssh.connect(s.host, port=s.ssh_port, username=s.user, password=zosconf.password(s),
                    timeout=20, banner_timeout=30, auth_timeout=30, look_for_keys=True, allow_agent=True)
    except paramiko.BadHostKeyException as e:
        oplog.write("EWS301E", f"SSH HOST KEY OF {s.host} CHANGED - CONNECTION REFUSED", channel="SSH")
        raise UssError(f"The SSH host key of {s.host} changed. If that is expected, run make login-ssh again.") from e
    except (paramiko.SSHException, OSError) as e:
        oplog.write("EWS301E", f"SSH CONNECT {s.user}@{s.host}:{s.ssh_port} FAILED: {e}", channel="SSH")
        raise UssError(f"SSH to {s.host}:{s.ssh_port} failed: {e}") from e
    t = ssh.get_transport()
    t.set_keepalive(30)
    oplog.write("EWS302I", f"SSH CONNECTED {s.user}@{s.host}:{s.ssh_port} {t.remote_version}",
                int((time.monotonic() - t0) * 1000), channel="SSH")
    _client.update(ssh=ssh, key=key)
    return ssh


def fetch_host_key() -> tuple[paramiko.PKey, str]:
    """The server's host key and its fingerprint, without trusting it yet."""
    s = zosconf.load()
    t = paramiko.Transport((s.host, s.ssh_port))
    try:
        t.start_client(timeout=20)
        k = t.get_remote_server_key()
    finally:
        t.close()
    return k, f"{k.get_name()} " + ":".join(f"{b:02x}" for b in k.get_fingerprint())


def trust_host_key(k: paramiko.PKey) -> None:
    s = zosconf.load()
    hk = paramiko.HostKeys()
    if zosconf.KNOWN_HOSTS.exists():
        hk.load(str(zosconf.KNOWN_HOSTS))
    name = s.host if s.ssh_port == 22 else f"[{s.host}]:{s.ssh_port}"
    hk.add(name, k.get_name(), k)
    zosconf.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    hk.save(str(zosconf.KNOWN_HOSTS))
    close()
    fp = ":".join(f"{b:02x}" for b in k.get_fingerprint())
    oplog.write("EWS500I", f"SSH HOST KEY OF {s.host} TRUSTED {k.get_name()} {fp}", channel="SSH")


def install_host_key() -> str:
    """Trust-on-first-use from the command line: fetch, store, return the fingerprint."""
    k, fp = fetch_host_key()
    trust_host_key(k)
    return fp


def close() -> None:
    with _lock:
        if _client["ssh"] is not None:
            _client["ssh"].close()
        _client.update(ssh=None, key=None)


def run(command: str, timeout: int = 60, log: bool = True) -> dict:
    """Run one command in the USS shell: {"rc", "out", "err", "ms"}."""
    with _lock:  # only connecting is serialized; commands run on their own channels in parallel
        ssh = _connect()
    t0 = time.monotonic()  # after connecting: the connect time is logged separately (EWS302I)
    try:
        _, out, err = ssh.exec_command(ENV + command, timeout=timeout)
        o = out.read().decode("utf-8", errors="replace")
        e = err.read().decode("utf-8", errors="replace")
        rc = out.channel.recv_exit_status()
    except (paramiko.SSHException, OSError, TimeoutError) as ex:
        with _lock:
            if _client["ssh"] is ssh:
                ssh.close()
                _client["ssh"] = None
        oplog.write("EWS301E", f"SSH {command[:80]} FAILED: {ex}", channel="SSH")
        raise UssError(f"SSH command failed: {ex}") from ex
    ms = int((time.monotonic() - t0) * 1000)
    if log:
        oplog.write("EWS300I" if rc == 0 else "EWS301E", f"SSH {command[:120]} RC={rc}", ms, channel="SSH")
    return {"rc": rc, "out": o, "err": e, "ms": ms}


def ping() -> int:
    """Heartbeat over SSH (reuses the open connection): milliseconds."""
    r = run("echo EWSPING", timeout=20, log=False)
    if "EWSPING" not in r["out"]:
        raise UssError(f"unexpected answer: {(r['out'] + r['err'])[:200]}")
    return r["ms"]


# ---------------------------------------------------------------- the agent on z/OS
def install_agent() -> str:
    """Copy ewsagent.py to ~/ews on USS (SFTP), tag it as ASCII text so z/OS Python reads it."""
    with _lock:
        ssh = _connect()
    sftp = ssh.open_sftp()
    try:
        try:
            sftp.mkdir(AGENT_DIR)
        except OSError:
            pass  # already there
        sftp.put(str(AGENT_SRC), AGENT)
    finally:
        sftp.close()
    r = run(f"chtag -tc ISO8859-1 {AGENT} && chmod 755 {AGENT} && python3 {AGENT} version")
    if r["rc"] != 0:
        raise UssError(f"Agent installed but does not start: {(r['err'] or r['out'])[:500]}")
    oplog.write("EWS500I", f"AGENT INSTALLED IN ~/{AGENT}", channel="SSH")
    return r["out"].strip()


def agent(*args: str, timeout: int = 60) -> dict:
    """Call the z/OS agent and return its JSON answer."""
    r = run(f"python3 {AGENT} " + " ".join(shlex.quote(a) for a in args), timeout=timeout)
    if r["rc"] == 127 or "can't open file" in r["err"] or "No such file" in r["err"]:
        raise UssError("The EWS agent is not installed on USS yet. Use INSTALL on the connection screen.")
    try:
        return json.loads(r["out"])
    except json.JSONDecodeError as e:
        raise UssError(f"Agent answer is not JSON (rc {r['rc']}): {(r['err'] or r['out'])[:500]}") from e


def _cli() -> None:
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "trust":
        print("Trusted host key:", install_host_key())
    elif cmd == "install":
        print(install_agent())
    elif cmd == "run":
        r = run(" ".join(sys.argv[2:]))
        print(r["out"], r["err"], f"rc={r['rc']} {r['ms']}ms", sep="")
    else:
        print("usage: python -m pipeline.uss trust | install | run <command>")


if __name__ == "__main__":
    _cli()
