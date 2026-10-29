# How the software connects to the mainframe

The project has its own clients for two independent channels to z/OS. No third-party mainframe client (Zowe CLI or similar) is needed.

## 1. The two channels

```
                         ┌─ channel 1: HTTPS ─────────────────────────────────────────────┐
 web backend   ─┐        │ pipeline/zos.py ──► z/OSMF REST API  204.90.115.200:10443       │
 operator TUI  ─┼─ pipeline ─►                    /zosmf/restfiles  data sets             │──► z/OS 3.1 (S0W1)
 CLI           ─┘        │                        /zosmf/restjobs   JES2 jobs, spool       │    JES2, catalog, SMS
                         ├─ channel 2: SSH ───────────────────────────────────────────────┤    USS, TSO, console
                         │ pipeline/uss.py ──► sshd on z/OS UNIX   204.90.115.200:22      │
                         │                       shell, TSO (tsocmd), console (opercmd),   │
                         │                       our agent ~/ews/ewsagent.py               │
                         └─────────────────────────────────────────────────────────────────┘
```

| Channel | Module | Carries | Used by |
|---|---|---|---|
| **z/OSMF REST** (HTTPS) | `pipeline/zos.py` | everything in the batch pipeline: allocate, upload, submit, wait, step RCs, download, delete | web backend, TUI, CLI |
| **SSH to USS** | `pipeline/uss.py` | operator work: shell, TSO and console commands, the EWS agent, record counts | TUI |

* **z/OSMF** (z/OS Management Facility, version 29) is IBM's web server on z/OS. Its REST services give programmatic access to data sets and JES. `pipeline/zos.py` calls them directly with `requests`.
* **USS** (z/OS UNIX System Services) is the POSIX side of z/OS. Its OpenSSH server (OpenSSH 8.4) accepts the same user ID and password. From there the IBM tools are available: `tsocmd` for TSO/E, ZOAU 1.3.6 (`jls`, `dls`, `dcat`, `opercmd`) and Python 3.9. `pipeline/uss.py` uses `paramiko`.

## 2. Credentials and configuration (`pipeline/zosconf.py`)

| What | Where |
|---|---|
| host, z/OSMF port, SSH port, user ID, verify-TLS flag | `~/.config/ews/zos.json` (not secret) |
| password | the OS keyring (Secret Service on Linux, Keychain on macOS), service `ews-zos`, account = user ID |
| trusted SSH host key | `~/.config/ews/known_hosts` |
| overrides (CI, containers) | `EWS_ZOS_HOST`, `EWS_ZOS_PORT`, `EWS_ZOS_USER`, `EWS_ZOS_PASSWORD`, `EWS_SSH_PORT`, `EWS_ZOS_VERIFY` |

Set it up once:

```bash
make login         # prompts for host, ports, user ID, password; tests the logon against z/OSMF
make login-ssh     # fetches and pins the SSH host key, installs the EWS agent on USS
```

The TUI's LOGON panel (option 0) does the same as `make login`; its connection panel has `SSHKEY` and `INSTALL` for the SSH part, and shows the host-key fingerprint before trusting it. To migrate an existing Zowe setup once, use `python -m pipeline.zosconf login --from-zowe`: it reads host and ports from `~/.zowe/zowe.config.json` and the user ID and password from Zowe's keyring entry. Nothing reads Zowe after that.

* The z/OS user ID is also the **high-level qualifier** of every data set (`Z72230.EWS.*`). Set `EWS_HLQ` to override.
* Z Xplore uses a self-signed certificate, so `verify` is `false` there. Leave it `true` on any system with a proper certificate.
* The SSH host key was checked against the one Zowe had already pinned for this host (`ssh-rsa 4c:3f:9e:4f:92:e9:e2:97:5f:1c:bc:bc:d2:01:a7:33`). If the key ever changes, connections are refused (`EWS301E ... HOST KEY ... CHANGED`).

## 3. Channel 1: the z/OSMF REST client (`pipeline/zos.py`)

```python
def request(method, path, *, params=None, headers=None, body=None, json_body=None, timeout=180, retries=3):
    sess, base = _session()               # one shared requests.Session: basic auth, then the LTPA cookie
    r = sess.request(method, base + path, ...)  # connection errors retried (not for submit)
    if r.status_code >= 400:
        raise ZosError(z/OSMF "message" + "details", status, method, path)   # 401 -> "log on again"
    oplog.write("EWS100I", f"{method} {path} {r.status_code}", ms)           # every call is logged
```

* Every state-changing request sends `X-CSRF-ZOSMF-HEADER: true`, which z/OSMF requires.
* A single shared session keeps the TLS connection pool and the LTPA token cookie that z/OSMF returns after the first basic-auth request, so later calls skip the password check.
* A job submit is never retried: if the answer is lost, resending it could run the job twice.

### Every call the project makes

| Purpose | Function | z/OSMF request |
|---|---|---|
| Heartbeat, system info | `ping()` | `GET /zosmf/info` (on this system it requires authentication) |
| Logon check | `check_status()` | `GET /zosmf/info` + `GET /zosmf/restjobs/jobs?owner=USER&max-jobs=1` |
| List data sets | `list_datasets("Z72230.EWS.**")` | `GET /zosmf/restfiles/ds?dslevel=...` with `X-IBM-Attributes: base` |
| List members | `list_members(pds)` | `GET /zosmf/restfiles/ds/{pds}/member` |
| Create PDS-E library | `create_library(dsn, "FB", 80)` | `POST /zosmf/restfiles/ds/{dsn}` `{"dsorg":"PO","dsntype":"LIBRARY","alcunit":"TRK",...}` |
| Create sequential data set | `create_sequential(dsn, "FB", 100, "15TRK")` | same, `{"dsorg":"PS",...,"blksize":27900}` (half-track blocking) |
| Upload text | `upload_file(local, "DSN(MEMBER)")` | `PUT /zosmf/restfiles/ds/{dsn}` with `X-IBM-Data-Type: text` (ASCII→EBCDIC) |
| Download text | `download(dsn, local)` | `GET /zosmf/restfiles/ds/{dsn}` with `X-IBM-Data-Type: text` (EBCDIC→ASCII) |
| View first records | `view(dsn, 50)` | same, with `X-IBM-Record-Range: 0,50` |
| Delete | `delete(dsn)` | `DELETE /zosmf/restfiles/ds/{dsn}` |
| Submit JCL | `submit("Z72230.EWS.JCL(EWSBATCH)", {"ASOFDT": 20260930, "MODE": "SCORE"})` | `PUT /zosmf/restjobs/jobs` `{"file": "//'Z72230.EWS.JCL(EWSBATCH)'"}` + one `X-IBM-JCL-Symbol-<name>` header per symbol |
| Wait for the job | `wait_for_output(jobid)` | `GET /zosmf/restjobs/jobs/{name}/{id}` every 2 s until `status=OUTPUT` and a `retcode` |
| Find a job by ID | (internal) | `GET /zosmf/restjobs/jobs?owner=*&jobid=JOB05387` |
| Job list (TUI SDSF panel) | `list_jobs(owner, prefix)` | `GET /zosmf/restjobs/jobs?owner=&prefix=&max-jobs=` |
| Spool files / content | `spool_files(jobid)`, `spool_content(jobid, id)` | `GET .../files`, `GET .../files/{id}/records` |
| Purge job (TUI) | `delete_job(jobid)` | `DELETE /zosmf/restjobs/jobs/{name}/{id}` |
| Run IDCAMS commands | `idcams("LISTCAT ...")` | `PUT /zosmf/restfiles/ams` `{"input": [...], "JSONversion": 1}` |
| VSAM statistics | `listcat(dsn)` | IDCAMS `LISTCAT ENTRIES(dsn) ALL`, parsed (`REC-TOTAL`, `REC-UPDATED`, splits, CI size, volume) |
| Read a VSAM record by key | `vsam_read(dsn, "CUST0166")` | IDCAMS `PRINT INDATASET(dsn) FROMKEY(k) TOKEY(k) HEX`; the hex is converted from EBCDIC locally. No record: z/OSMF answers HTTP 500 with `NUMBER OF RECORDS PROCESSED WAS 0`, returned as "not found" |
| Browse a VSAM cluster | `vsam_records(dsn, 500)` | IDCAMS `PRINT INDATASET(dsn) COUNT(500) HEX` |
| Delete a VSAM cluster | `delete_vsam(dsn)` | IDCAMS `DELETE dsn CLUSTER` |

Verified on the real system (2026-10-28): the RISKRPT download is byte-identical to the file Zowe CLI had downloaded, a 300-record round trip with special characters (`#@$ {}[]|!^~`) comes back unchanged, and `compile` (upload 12 members, submit EWSCOMP, step RCs, verify load modules) runs end to end.

### Passing parameters to JCL

JCL symbols travel as request headers (`X-IBM-JCL-Symbol-ASOFDT: 20260930`). z/OSMF substitutes them before conversion. A `// SET` statement inside the JCL would **override** the submitted value, so `EWSBATCH` deliberately has none for these symbols. In the JCL they are used as `PARM='&ASOFDT.&MODE'` (COBOL receives `20260930SCORE`) and `PARM='%EWSRECON &ASOFDT &MODE'` (the REXX exec receives two words).

### Per-step return codes

The job status only has the highest return code (e.g. `CC 0004`). For every step's code, `step_results(jobid)` reads the job's `JESYSMSG` spool file and parses the standard messages:

| Message | Meaning | Parsed to |
|---|---|---|
| `IEF142I EWSBATCH STEP050 - STEP WAS EXECUTED - COND CODE 0004` | step ended normally | `{"step": "STEP050", "rc": 4}` |
| `IEF142I EWSCOMP CVCUST COBOL - STEP WAS EXECUTED - COND CODE 0000` | step of a procedure | `{"step": "CVCUST", "procstep": "COBOL", "rc": 0}` |
| `IEF272I EWSBATCH STEP080 - STEP WAS NOT EXECUTED.` | skipped by an `IF` | `status: not executed` |
| `IEF472I EWSBATCH STEP070 - COMPLETION CODE - SYSTEM=0C7 ...` | abend | `status: abended, abend: S0C7` |

An action fails if any step exceeds its allowed RC (4 for EWSBATCH/EWSCOMP, 0 for EWSRPTJ), abended, or was skipped.

## 4. Channel 2: SSH and the EWS agent (`pipeline/uss.py`, `mainframe/uss/ewsagent.py`)

* One SSH connection per process, kept open with keepalives. Only connecting is serialized; each command runs on its own channel, so a long command in the TUI shell does not block the heartbeat.
* Non-interactive SSH sessions do not read the login profile, so every command is prefixed with the environment ZOAU and Python need (`PATH`, `LIBPATH`, `_BPXK_AUTOCVT=ON`, `_CEE_RUNOPTS=FILETAG(AUTOCVT,AUTOTAG)`).
* Authentication: an SSH key if the server accepts one, otherwise the keyring password.

The **EWS agent** is our own program on the z/OS side: a Python 3.9 script (standard library plus the ZOAU commands), copied by SFTP to `~/ews/ewsagent.py` and tagged as ASCII text (`chtag -tc ISO8859-1`) so z/OS Python reads it. It answers in JSON:

| Call | Answers with | How it gets it on z/OS |
|---|---|---|
| `ewsagent.py info` | system name, z/OS release, IPL date and volume, console clock, user, home file system, ZOAU/Python versions | `sysvar`, `uname`, `opercmd 'D IPLINFO'`, `opercmd 'D T'`, `df`, `zoaversion` |
| `ewsagent.py jobs OWNER PREFIX` | JES jobs | `jls /OWNER/PREFIX` |
| `ewsagent.py datasets PATTERN` | catalog entries | `dls -l` |
| `ewsagent.py count DSN` | number of records (z/OSMF cannot count) | `dcat DSN \| wc -l` |

One `info` call costs one SSH round trip (about 2 s, mostly z/OS process start-up).

## 5. Character encoding

z/OS stores text in **EBCDIC** (code page IBM-1047). Both upload and download use z/OSMF **text mode**, so z/OSMF converts each byte between ASCII and EBCDIC and splits or joins records at line ends:

* upload: each line of the local file becomes one fixed-length record, padded with blanks to the LRECL;
* download: each record becomes one line (trailing blanks of FB records are kept; VB records have none).

This only works if every byte is a character. Hence all numeric fields in files that cross the boundary are **zoned decimal** (digits as characters), with no signs and no packed or binary fields. `tests/test_layouts.py` checks that all mainframe sources are pure ASCII and fit their columns. Sending an explicit `charset=ISO-8859-1` on uploads makes z/OSMF's iconv fail (`EDC5121I`), so the client sends plain `text/plain` and relies on the server's default conversion.

## 6. The operator log

Every z/OSMF request, upload, download, job, SSH command, run step and channel change is written to the `oplog` table in SQLite, with a z/OS-style message ID (`EWS100I`, `EWS101E`, …), the channel and the duration. The web backend, the TUI and the CLI all write to it, and the TUI's SYSLOG panel shows it live. See [TUI.md](TUI.md#message-ids).

## 7. Behaviour of the Z Xplore system that the code works around

| Observed | Handling |
|---|---|
| Occasional connection resets | `zos.request` retries idempotent calls up to 3 times with back-off (`EWS102W`) |
| One COBOL source was always cut off during upload: the network filter in front of z/OSMF flags content that looks like SQL injection (`SELECT ...` together with literals such as `' HIGH=' ... ' LOW='`) | The `DISPLAY` text in `EWSRPT` was reworded; the upload error message explains this case if it ever happens again |
| `/zosmf/info` needs authentication here (it is often public) | `ping()` uses the logged-on session |
| z/OSMF restfiles cannot read or write VSAM records | VSAM goes through the AMS (IDCAMS) endpoint; `PRINT ... CHARACTER` shows lowercase letters as dots, so records are printed in `HEX` and decoded locally |
| Occasional HTTP 500 `__msgrcv_timed error timed out` from z/OSMF's back end | retried like a connection error (`EWS102W`), never for a submit |
| SMS rejects allocations in cylinders, tracks work | All allocations, in the backend and in JCL `SPACE=`, use tracks |
| The site `IGYWCL` compile procedure reads `&SYSUID..CBL(&SRC)` and links into `&SYSUID..LOAD(&SRC)`; its COBOL step has no `SYSLIB` | COBOL sources go to `Z72230.CBL`; `EWSCOMP` adds `//COBOL.SYSLIB DD DSN=&SYSUID..EWS.CPY` |
| DFSORT on this system does not support `SUM FIELDS=NONE,XSUM` (`ICE172A`) | Duplicate removal uses ICETOOL `SELECT ... FIRST DISCARD(DUPS)` |
| `jls -o` means "output fields", not owner | The agent passes the owner in the mask: `jls /Z72230/*` |
