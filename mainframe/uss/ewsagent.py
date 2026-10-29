"""EWS agent: runs on z/OS UNIX (USS) and answers the operator console in JSON.

Installed by the backend into ~/ews/ewsagent.py over SFTP and called over SSH:

    python3 ~/ews/ewsagent.py info                 system, IPL, clock, user, disk, versions
    python3 ~/ews/ewsagent.py jobs [OWNER] [PREFIX] JES jobs (ZOAU jls)
    python3 ~/ews/ewsagent.py datasets PATTERN     catalog entries (ZOAU dls -l)
    python3 ~/ews/ewsagent.py count DSN            number of records in a sequential data set
    python3 ~/ews/ewsagent.py version

One call gathers everything the monitor needs, so the connection screen costs one
SSH round trip. Standard library only (z/OS Python 3.9) plus the ZOAU commands.
"""
import json
import os
import re
import subprocess
import sys
import time

VERSION = "1.0"


def sh(cmd, timeout=60):
    p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def oper(cmd):
    """Operator command through ZOAU; returns the message lines without the console prefix."""
    rc, out, _ = sh("opercmd " + json.dumps(cmd))
    lines = []
    for line in out.splitlines():
        if "ISF031I" in line or line.strip().endswith(cmd):
            continue
        lines.append(re.sub(r"^\S+\s+\d{7}\s+[\d:.]+\s", "", line).strip() if re.match(r"^\S+\s+\d{7}\s", line)
                     else line.strip())
    return rc, [l for l in lines if l]


def info():
    t0 = time.time()
    out = {"agent": VERSION, "pid": os.getpid()}
    _, sysname, _ = sh("sysvar SYSNAME")
    _, uname, _ = sh("uname -a")
    out["sysname"] = sysname.strip()
    out["uname"] = uname.strip()
    rc, ipl = oper("D IPLINFO")
    text = " ".join(ipl)
    m = re.search(r"SYSTEM IPLED AT (\S+) ON (\S+)", text)
    out["ipl"] = {"time": m.group(1), "date": m.group(2)} if m else None
    m = re.search(r"RELEASE (z/OS \S+)", text)
    out["release"] = m.group(1) if m else None
    m = re.search(r"VOLUME\((\w+)\)", text)
    out["ipl_volume"] = m.group(1) if m else None
    rc, clock = oper("D T")
    m = re.search(r"LOCAL: TIME=(\S+) DATE=(\S+)", " ".join(clock))
    out["clock"] = {"time": m.group(1), "date": m.group(2)} if m else None
    out["console_ok"] = rc == 0 and bool(ipl)
    _, ident, _ = sh("id -un")
    out["user"] = ident.strip()
    out["home"] = os.path.expanduser("~")
    _, df, _ = sh("df -k " + out["home"] + " | tail -1")
    m = re.search(r"\((\S+)\)\s+(\d+)/(\d+)", df)
    out["home_fs"] = {"name": m.group(1), "free_kb": int(m.group(2)), "total_kb": int(m.group(3))} if m else None
    _, zoa, _ = sh("zoaversion")
    m = re.search(r"v(\d+\.\d+\.\d+\.\d+)", zoa)
    out["zoau"] = m.group(1) if m else None
    out["python"] = sys.version.split()[0]
    out["elapsed_ms"] = int((time.time() - t0) * 1000)
    return out


def jobs(owner=None, prefix=None):
    mask = "/" + (owner or "*").upper() + "/" + (prefix or "*").upper()
    rc, out, err = sh("jls " + json.dumps(mask))
    rows = []
    for line in out.splitlines():
        p = line.split()
        if len(p) >= 4:
            rows.append({"owner": p[0], "jobname": p[1], "jobid": p[2], "retcode": " ".join(p[3:])})
    return {"rc": rc, "jobs": rows, "error": err.strip() or None}


def datasets(pattern):
    rc, out, err = sh("dls -l " + json.dumps(pattern.upper()))
    rows = []
    for line in out.splitlines():
        p = line.split()
        if len(p) >= 5:
            rows.append({"dsname": p[0], "dsorg": p[1], "recfm": p[2], "lrecl": p[3], "volume": p[4]})
    return {"rc": rc, "datasets": rows, "error": err.strip() or None}


def count(dsn):
    rc, out, err = sh("dcat " + json.dumps(dsn.upper()) + " | wc -l", timeout=300)
    return {"dsname": dsn.upper(), "records": int(out.strip() or 0) if rc == 0 else None,
            "error": err.strip() or None}


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "version"
    if cmd == "version":
        print("ewsagent " + VERSION + " python " + sys.version.split()[0])
        return 0
    handlers = {"info": info, "jobs": jobs, "datasets": datasets, "count": count}
    if cmd not in handlers:
        print(json.dumps({"error": "unknown command " + cmd}))
        return 2
    try:
        print(json.dumps(handlers[cmd](*argv[2:])))
    except Exception as e:  # the caller always gets JSON
        print(json.dumps({"error": type(e).__name__ + ": " + str(e)}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
