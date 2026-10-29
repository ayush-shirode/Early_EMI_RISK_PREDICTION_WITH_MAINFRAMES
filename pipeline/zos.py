"""Our own z/OSMF REST client. Every data set and job operation of the project goes through here.

It speaks HTTPS directly to the two z/OSMF REST services:
  /zosmf/restfiles/ds    data sets: list, create, read, write, delete
  /zosmf/restjobs/jobs   JES: submit, status, spool files
with HTTP basic authentication (z/OSMF then returns an LTPA cookie that the session
reuses). Host, user and password come from pipeline/zosconf.py. Every request is
written to the operator log (pipeline/oplog.py) with its HTTP status and duration.
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from urllib.parse import quote

import requests
import urllib3

from pipeline import oplog, zosconf


class ZosError(RuntimeError):
    """A z/OSMF call failed; the message is meant for the user."""


class ZosConnectionError(ZosError):
    """The request never got an HTTP answer (network, TLS, reset by a filter)."""


_lock = threading.Lock()
_shared: dict = {"key": None}   # one session for all threads: it keeps the LTPA cookie and the TLS pool
_jobnames: dict[str, str] = {}   # jobid -> jobname, z/OSMF job URLs need both


def _short(e: Exception) -> str:
    text = str(e)
    m = re.search(r"\(Caused by (\w+)\(", text) or re.search(r"(Connection reset by peer|timed out|Name or service not known)", text)
    return m.group(1) if m else text[:200]


def _session() -> tuple[requests.Session, str]:
    try:
        s = zosconf.load()
    except zosconf.NotConfigured as e:
        raise ZosError(str(e)) from e
    key = (s.host, s.port, s.user, s.verify, zosconf.generation())
    with _lock:
        if _shared["key"] == key:
            return _shared["session"], _shared["base"]
        pw = zosconf.password(s)
        if not pw:
            raise ZosError(f"No password stored for {s.user}. Log on first: make login (or LOGON in the TUI).")
        if not s.verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        sess = requests.Session()
        sess.auth = (s.user, pw)
        sess.verify = s.verify
        # z/OSMF refuses state-changing requests without this header (CSRF protection).
        sess.headers.update({"X-CSRF-ZOSMF-HEADER": "true", "User-Agent": "ews-zos/1.0"})
        _shared.update(session=sess, key=key, base=s.base_url)
        return sess, s.base_url


def _error_text(r: requests.Response) -> str:
    try:
        j = r.json()
    except ValueError:
        return re.sub(r"<[^>]+>", " ", r.text).strip()[:500] or r.reason
    if isinstance(j, dict):
        parts = [j.get("message")] + list(j.get("details") or [])
        return " ".join(str(p) for p in parts if p)[:1000] or str(j)[:500]
    return str(j)[:500]


def request(method: str, path: str, *, params: dict | None = None, headers: dict | None = None,
            body: bytes | None = None, json_body: object = None, timeout: int = 180, retries: int = 3,
            log: bool = True) -> requests.Response:
    """One z/OSMF call. Connection failures are retried for idempotent calls (retries > 1)."""
    sess, base = _session()
    for attempt in range(1, retries + 1):
        t0 = time.monotonic()
        try:
            r = sess.request(method, base + path, params=params, headers=headers, data=body, json=json_body,
                             timeout=(15, timeout))
        except (requests.ConnectionError, requests.Timeout) as e:
            ms = int((time.monotonic() - t0) * 1000)
            if attempt < retries:
                oplog.write("EWS102W", f"{method} {path} {_short(e)} - RETRY {attempt}", ms)
                time.sleep(2 * attempt)
                continue
            oplog.write("EWS101E", f"{method} {path} {_short(e)}", ms)
            raise ZosConnectionError(f"z/OSMF at {base} did not answer ({_short(e)})") from e
        ms = int((time.monotonic() - t0) * 1000)
        if r.status_code >= 400:
            msg = _error_text(r)
            # z/OSMF sometimes times out talking to its own back end (HTTP 500 "__msgrcv_timed ... timed out")
            if r.status_code >= 500 and "timed out" in msg and attempt < retries:
                oplog.write("EWS102W", f"{method} {path} HTTP {r.status_code} SERVER TIMEOUT - RETRY {attempt}", ms)
                time.sleep(3 * attempt)
                continue
            oplog.write("EWS101E", f"{method} {path} HTTP {r.status_code} {msg}", ms)
            if r.status_code == 401:
                raise ZosError("z/OSMF rejected the user ID or password (HTTP 401). Log on again: make login")
            raise ZosError(f"{msg} (HTTP {r.status_code} on {method} {path})")
        if log:
            oplog.write("EWS100I", f"{method} {path} {r.status_code}", ms)
        return r
    raise AssertionError("unreachable")


def _ds(dsn: str) -> str:
    """URL path of a data set or member: /zosmf/restfiles/ds/HLQ.X.Y(MEMBER)."""
    return "/zosmf/restfiles/ds/" + quote(dsn.upper(), safe="().$@")


def _text(r: requests.Response) -> str:
    return r.content.decode(r.encoding or "iso-8859-1", errors="replace")


# ---------------------------------------------------------------- connection
def ping(timeout: int = 10) -> tuple[int, dict]:
    """Heartbeat: (milliseconds, /zosmf/info). Not logged, the caller logs state changes."""
    t0 = time.monotonic()
    info = request("GET", "/zosmf/info", timeout=timeout, retries=1, log=False).json()
    return int((time.monotonic() - t0) * 1000), info


def check_status() -> dict:
    """z/OSMF reachability, a credential check, and system info."""
    s = zosconf.load()
    info = request("GET", "/zosmf/info").json()
    # Some z/OSMF setups answer /zosmf/info without credentials; make sure they are accepted.
    request("GET", "/zosmf/restjobs/jobs", params={"owner": s.user, "max-jobs": 1})
    return {
        "user": s.user,
        "system": info.get("zosmf_hostname"),
        "zos_version": info.get("zos_version"),
        "zosmf_version": info.get("zosmf_full_version"),
        "port": str(s.port),
    }


# ---------------------------------------------------------------- data sets
def list_datasets(pattern: str) -> list[dict]:
    r = request("GET", "/zosmf/restfiles/ds", params={"dslevel": pattern.upper()},
                headers={"X-IBM-Attributes": "base", "X-IBM-Max-Items": "0"})
    return r.json().get("items", [])


def list_members(pds: str) -> list[str]:
    r = request("GET", _ds(pds) + "/member", headers={"X-IBM-Max-Items": "0"})
    return [i["member"] for i in r.json().get("items", [])]


def exists(dsn: str) -> bool:
    return any(d["dsname"] == dsn.upper() for d in list_datasets(dsn))


def _space(size: str) -> tuple[str, int]:
    m = re.fullmatch(r"(\d+)(TRK|CYL)", size.upper())
    if not m:
        raise ValueError(f"size must look like 15TRK, got {size}")
    return m.group(2), int(m.group(1))


def _blksize(recfm: str, lrecl: int) -> int:
    """Half-track blocking for 3390 disks: the largest multiple of LRECL up to 27998."""
    return 27998 // lrecl * lrecl if recfm.startswith("F") and lrecl else 27998


def _create(dsn: str, attrs: dict) -> None:
    request("POST", _ds(dsn), json_body=attrs, retries=1)


def create_library(dsn: str, recfm: str, lrecl: int) -> None:
    if recfm == "U":
        _create(dsn, {"dsorg": "PO", "dsntype": "LIBRARY", "alcunit": "TRK", "primary": 15, "secondary": 15,
                      "dirblk": 25, "recfm": "U", "blksize": 27998, "lrecl": 27998})
    else:
        _create(dsn, {"dsorg": "PO", "dsntype": "LIBRARY", "alcunit": "TRK", "primary": 5, "secondary": 5,
                      "dirblk": 20, "recfm": recfm, "blksize": _blksize(recfm, lrecl), "lrecl": lrecl})


def create_sequential(dsn: str, recfm: str, lrecl: int, size: str) -> None:
    unit, primary = _space(size)
    _create(dsn, {"dsorg": "PS", "alcunit": unit, "primary": primary, "secondary": max(1, primary // 2),
                  "recfm": recfm, "blksize": _blksize(recfm, lrecl), "lrecl": lrecl})


def delete(dsn: str) -> None:
    request("DELETE", _ds(dsn))


def upload_text(text: str, target: str) -> None:
    """Text-mode write (z/OSMF converts ASCII -> EBCDIC, one line per record). `target` is DSN or PDS(MEMBER)."""
    data = text.replace("\r\n", "\n").encode("iso-8859-1")
    t0 = time.monotonic()
    try:
        request("PUT", _ds(target), body=data, timeout=600, log=False,
                headers={"Content-Type": "text/plain", "X-IBM-Data-Type": "text"})
    except ZosConnectionError as e:
        raise ZosError(
            f"Upload to {target} was cut off before z/OSMF answered. If it keeps failing for this content, the "
            "Z Xplore network filter is rejecting it (it flags text that looks like SQL injection, e.g. SELECT "
            "together with ' NAME=' literals); reword that text."
        ) from e
    oplog.write("EWS120I", f"UPLOAD {target.upper()} {text.count(chr(10))} RECORDS {len(data)} BYTES",
                int((time.monotonic() - t0) * 1000))


def upload_file(local: Path, target: str) -> None:
    upload_text(Path(local).read_text(encoding="iso-8859-1"), target)


def download_text(dsn: str) -> str:
    t0 = time.monotonic()
    r = request("GET", _ds(dsn), headers={"X-IBM-Data-Type": "text"}, timeout=600, log=False)
    text = _text(r)
    oplog.write("EWS121I", f"DOWNLOAD {dsn.upper()} {text.count(chr(10))} RECORDS {len(r.content)} BYTES",
                int((time.monotonic() - t0) * 1000))
    return text


def download(dsn: str, local: Path) -> Path:
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(download_text(dsn))
    return local


def view(dsn: str, max_records: int | None = None) -> str:
    """First records of a data set as text. Use download() for large ones."""
    headers = {"X-IBM-Data-Type": "text"}
    if max_records:
        headers["X-IBM-Record-Range"] = f"0,{max_records}"
    return _text(request("GET", _ds(dsn), headers=headers, timeout=120))


# ---------------------------------------------------------------- VSAM (IDCAMS)
def idcams(*commands: str, check: bool = True) -> dict:
    """Run IDCAMS commands through z/OSMF (PUT /zosmf/restfiles/ams): {"rc", "output": [lines]}."""
    r = request("PUT", "/zosmf/restfiles/ams", json_body={"input": list(commands), "JSONversion": 1},
                retries=1, timeout=120).json()
    if check and r.get("rc", 0) > 4:
        msgs = [l.strip() for l in r.get("output", []) if re.search(r"IDC\d{4}[IE]", l) and "IDC0001I" not in l]
        raise ZosError(f"IDCAMS RC {r.get('rc')}: {' '.join(msgs)[:500] or commands[0]}")
    return r


_LISTCAT_FIELDS = ("REC-TOTAL", "REC-INSERTED", "REC-UPDATED", "REC-DELETED", "REC-RETRIEVED", "SPLITS-CI",
                   "SPLITS-CA", "FREESPACE-%CI", "FREESPACE-%CA", "CISIZE", "KEYLEN", "RKP", "MAXLRECL",
                   "HI-U-RBA", "HI-A-RBA", "EXTENTS", "VOLSER", "STORAGECLASS", "DATACLASS")


def parse_listcat(lines: list[str]) -> dict:
    """LISTCAT ALL of one cluster -> {"cluster": {...}, "data": {...}, "index": {...}}."""
    out: dict = {}
    part = None
    for line in lines:
        m = re.match(r"\s*(CLUSTER|DATA|INDEX)\s+-{3,}\s+(\S+)", line)
        if m:
            part = m.group(1).lower()
            out[part] = {"name": m.group(2)}
            continue
        if part is None:
            continue
        # FIELD-NAME------value: name parts are joined by single dashes, the padding is 2+ dashes
        for k, v in re.findall(r"\b([A-Z][A-Z%/]*(?:-[A-Z%/]+)*)-{2,}(\S+)", line):
            if k in _LISTCAT_FIELDS and k.lower() not in out[part]:
                out[part][k.lower()] = int(v) if v.isdigit() else v
        m = re.search(r"CREATION-{2,}(\S+)", line)
        if m:
            out[part].setdefault("created", m.group(1))
    return out


def listcat(dsn: str) -> dict:
    return parse_listcat(idcams(f"LISTCAT ENTRIES({dsn.upper()}) ALL")["output"])


def parse_print_hex(lines: list[str]) -> list[bytes]:
    """Records from IDCAMS PRINT ... HEX: 'KEY OF RECORD - <hex>' then the record in hex."""
    recs: list[bytes] = []
    cur: list[str] | None = None
    for line in lines:
        s = line.strip()
        if s.startswith("KEY OF RECORD"):
            if cur is not None:
                recs.append(bytes.fromhex("".join(cur)))
            cur = []
        elif cur is not None and re.fullmatch(r"[0-9A-F]+", s):
            cur.append(s)
        elif cur is not None and s:
            recs.append(bytes.fromhex("".join(cur)))
            cur = None
    if cur:
        recs.append(bytes.fromhex("".join(cur)))
    return recs


def ebcdic(b: bytes) -> str:
    """IBM-1047 to text. CPython has no cp1047; cp037 differs only in a few symbols, not letters or digits."""
    try:
        return b.decode("cp1047")
    except LookupError:
        return b.decode("cp037")


def vsam_read(dsn: str, key: str, to_key: str | None = None) -> list[str]:
    """Records of a KSDS by key (or key range) through IDCAMS PRINT, decoded from EBCDIC."""
    for k in (key, to_key or key):
        if not re.fullmatch(r"[A-Z0-9#@$]{1,44}", k.upper()):
            raise ZosError(f"Invalid key {k}")
    try:
        r = idcams(f"PRINT INDATASET({dsn.upper()}) FROMKEY({key.upper()}) TOKEY({(to_key or key).upper()}) HEX",
                   check=False)
    except ZosError as e:
        # z/OSMF answers HTTP 500 when PRINT finds no record in the key range (IDCAMS RC 12)
        if "NUMBER OF RECORDS PROCESSED WAS 0" in str(e):
            return []
        raise
    return [ebcdic(b) for b in parse_print_hex(r.get("output", []))]


def vsam_records(dsn: str, count: int = 200) -> list[str]:
    """The first `count` records of a VSAM cluster in key order (IDCAMS PRINT COUNT)."""
    r = idcams(f"PRINT INDATASET({dsn.upper()}) COUNT({int(count)}) HEX", check=False)
    return [ebcdic(b) for b in parse_print_hex(r.get("output", []))]


def delete_vsam(dsn: str) -> None:
    idcams(f"DELETE {dsn.upper()} CLUSTER")


# ---------------------------------------------------------------- jobs
def _job_path(jobid: str) -> str:
    name = _jobnames.get(jobid)
    if not name:
        jobs = request("GET", "/zosmf/restjobs/jobs", params={"owner": "*", "jobid": jobid}).json()
        if not jobs:
            raise ZosError(f"Job {jobid} not found")
        name = _jobnames[jobid] = jobs[0]["jobname"]
    return f"/zosmf/restjobs/jobs/{name}/{jobid}"


def submit(member_dsn: str, symbols: dict | None = None, wait: bool = True, timeout: int = 900) -> dict:
    """Submit JCL from a data set member. JCL symbols are passed as X-IBM-JCL-Symbol-* headers."""
    headers = {f"X-IBM-JCL-Symbol-{k}": str(v) for k, v in (symbols or {}).items()}
    # retries=1: re-sending a submit after a lost answer could run the job twice
    job = request("PUT", "/zosmf/restjobs/jobs", headers=headers, retries=1,
                  json_body={"file": f"//'{member_dsn.upper()}'"}).json()
    _jobnames[job["jobid"]] = job["jobname"]
    sym = " ".join(f"{k}={v}" for k, v in (symbols or {}).items())
    oplog.write("EWS110I", f"JOB {job['jobname']}({job['jobid']}) SUBMITTED FROM {member_dsn.upper()} {sym}".rstrip())
    return wait_for_output(job["jobid"], timeout) if wait else job


def wait_for_output(jobid: str, timeout: int = 900) -> dict:
    """Poll JES until the job is on the output queue and has a return code."""
    path, t0, extra = _job_path(jobid), time.monotonic(), 0
    while True:
        job = request("GET", path, log=False).json()
        if job.get("status") == "OUTPUT" and (job.get("retcode") or extra >= 5):
            break
        if job.get("status") == "OUTPUT":
            extra += 1
        if time.monotonic() - t0 > timeout:
            raise ZosError(f"Job {jobid} still {job.get('status')} after {timeout}s")
        time.sleep(2)
    rc = job.get("retcode") or "?"
    bad = not str(rc).startswith("CC ")
    oplog.write("EWS112E" if bad else "EWS111I", f"JOB {job['jobname']}({jobid}) ENDED {rc}",
                int((time.monotonic() - t0) * 1000))
    return job


def job_status(jobid: str) -> dict:
    return request("GET", _job_path(jobid)).json()


def list_jobs(owner: str | None = None, prefix: str = "*", max_jobs: int = 100) -> list[dict]:
    owner = owner or zosconf.load().user
    jobs = request("GET", "/zosmf/restjobs/jobs",
                   params={"owner": owner.upper(), "prefix": prefix.upper(), "max-jobs": max_jobs}).json()
    for j in jobs:
        _jobnames[j["jobid"]] = j["jobname"]
    return jobs


def spool_files(jobid: str) -> list[dict]:
    return request("GET", _job_path(jobid) + "/files").json() or []


def spool_content(jobid: str, file_id: int) -> str:
    return _text(request("GET", f"{_job_path(jobid)}/files/{int(file_id)}/records", timeout=120))


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
    request("DELETE", _job_path(jobid))
