# How the software connects to the mainframe

## 1. The chain

```
FastAPI backend ──subprocess──► Zowe CLI ──HTTPS (TLS)──► z/OSMF REST API ──► z/OS services
 pipeline/zowe.py               `zowe ... --rfj`          204.90.115.200:10443   JES2, catalog, SMS, data set I/O
```

* **z/OS** is the operating system (here z/OS 3.1 on the IBM Z Xplore system `S0W1.DAL-EBIS.IHOST.COM`).
* **z/OSMF** (z/OS Management Facility, version 29) is IBM's web server on z/OS. It exposes REST APIs; this project uses two of them:
  * **z/OS data set and file REST interface** (`/zosmf/restfiles/...`): list, create, read, write and delete data sets and members.
  * **z/OS jobs REST interface** (`/zosmf/restjobs/...`): submit JCL, get job status, list and read spool files.
* **Zowe CLI** (v8.36, part of Zowe v3.6, an Open Mainframe Project) is a command-line client for those APIs. Zowe Explorer in VS Code uses the same Zowe SDK and the same profiles.
* **`pipeline/zowe.py`** is the only Python module that touches the mainframe. Every function in it runs exactly one Zowe CLI command.

There is no database driver, no FTP and no 3270 terminal emulation anywhere in the project.

## 2. Authentication and configuration

Zowe CLI reads its **team configuration** from `~/.zowe/zowe.config.json`:

```json
"zosmf":       { "type": "zosmf", "properties": { "port": 10443 } },
"global_base": { "type": "base",  "properties": { "host": "204.90.115.200", "rejectUnauthorized": false },
                 "secure": ["user", "password"] }
```

* `host` and `port` identify z/OSMF; `rejectUnauthorized: false` accepts the Z Xplore self-signed certificate.
* `user` and `password` are listed under `secure`: they are **not** in the file. Zowe stores them in the operating system's credential store (the "secure store", via the keyring). They are set once with `zowe config secure` (or by Zowe Explorer's login prompt).
* Every request is HTTPS with HTTP basic authentication (`Auth type used: basic`).

Consequences for this project:

* The backend never sees or stores the password; it only invokes `zowe`, which reads the secure store itself.
* The backend must run as your local user on the desktop (not inside Docker), so it can reach the keyring.
* The z/OS user ID (`Z72230`) is read from `zowe zosmf check status` and becomes the **high-level qualifier** of every data set (`Z72230.EWS.*`). Set `EWS_HLQ` to override.

## 3. How a call is made (`pipeline/zowe.py`)

```python
def run(*args, timeout=180, retries=3):
    cmd = ["zowe", *args, "--rfj"]          # --rfj = response format JSON
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    resp = json.loads(p.stdout)             # {"success": bool, "data": ..., "message": ...}
    if resp["success"]: return resp["data"]
    # network hiccups ("Failed to send an HTTP request", ECONNRESET, ...) are retried 3x
    raise ZoweError(message + the command)
```

* `--rfj` makes every command print a JSON envelope, so results are parsed, never screen-scraped.
* Each step in the UI shows the error text of a failed call verbatim, including which command failed.
* Calls have timeouts (3 min by default, 10 min for uploads/downloads, 15 min for a job submit that waits for output).

## 4. Every Zowe call the project makes

| Purpose | Zowe CLI command | z/OSMF API underneath | Used by |
|---|---|---|---|
| Connection test, user ID | `zowe zosmf check status` | `GET /zosmf/info` | Test connection, status panel |
| List data sets | `zowe zos-files list data-set "Z72230.EWS.**" -a` | `GET /zosmf/restfiles/ds?dslevel=` | Setup, status, Data sets page |
| List members | `zowe zos-files list all-members Z72230.LOAD` | `GET /zosmf/restfiles/ds/{pds}/member` | Verify load modules, PDS browsing |
| Create PDS-E library | `zowe zos-files create data-set-partitioned DSN --dst LIBRARY --rf FB --rl 80 --size 5TRK --db 20` | `POST /zosmf/restfiles/ds/{dsn}` | Setup |
| Create load library | `zowe zos-files create data-set-binary DSN --dst LIBRARY --size 15TRK` | same | Setup (only if `Z72230.LOAD` is missing) |
| Create sequential data set | `zowe zos-files create data-set-sequential DSN --rf FB --rl 100 --bs 27900 --size 15TRK` | same | Generate data, write-back |
| Upload a member / data set | `zowe zos-files upload file-to-data-set local.txt "DSN(MEMBER)"` | `PUT /zosmf/restfiles/ds/{dsn}` (text, ASCII→EBCDIC) | Setup, generate data, write-back |
| Download a data set | `zowe zos-files download data-set DSN -f local.txt --overwrite` | `GET /zosmf/restfiles/ds/{dsn}` (text, EBCDIC→ASCII) | After every batch |
| View records | `zowe zos-files view data-set DSN --range 0,50` | `GET` with `X-IBM-Record-Range` | Data set preview |
| Delete | `zowe zos-files delete data-set DSN -f` | `DELETE /zosmf/restfiles/ds/{dsn}` | Re-allocation, reset |
| Submit JCL and wait | `zowe zos-jobs submit data-set "Z72230.EWS.JCL(EWSBATCH)" --js "ASOFDT=20260930 MODE=SCORE" --wfo` | `PUT /zosmf/restjobs/jobs` + polling | Every batch, compile, report |
| Job status | `zowe zos-jobs view job-status-by-jobid JOB04556` | `GET /zosmf/restjobs/jobs/{name}/{id}` | Job output page |
| Spool file list | `zowe zos-jobs list spool-files-by-jobid JOB04556` | `GET .../files` | Step RCs, job output page |
| Spool content | `zowe zos-jobs view spool-file-by-id JOB04556 4` | `GET .../files/{id}/records` | Step RCs, job output page |

### Passing parameters to JCL

`--js` (`--jcl-symbols`) sends JCL symbols with the submit request; z/OSMF substitutes them in the JCL before conversion. Two details were verified on the real system:

1. Several symbols must be **space-separated** (`"ASOFDT=20260930 MODE=SCORE"`). A comma is taken as part of the value.
2. A `// SET` statement inside the JCL **overrides** the submitted value, so `EWSBATCH` deliberately has no `SET` for these symbols.

In the JCL the symbols are used as `PARM='&ASOFDT.&MODE'` (COBOL receives `20260930SCORE`) and `PARM='%EWSRECON &ASOFDT &MODE'` (the REXX exec receives two words).

### Getting per-step return codes

`--wfo` returns only the job's highest return code (e.g. `CC 0004`). To show the code of every step, the backend reads the job's `JESYSMSG` spool file and parses the standard system messages:

| Message | Meaning | Parsed to |
|---|---|---|
| `IEF142I EWSBATCH STEP050 - STEP WAS EXECUTED - COND CODE 0004` | step ended normally | `{"step": "STEP050", "rc": 4}` |
| `IEF142I EWSCOMP CVCUST COBOL - STEP WAS EXECUTED - COND CODE 0000` | step of a procedure | `{"step": "CVCUST", "procstep": "COBOL", "rc": 0}` |
| `IEF272I EWSBATCH STEP080 - STEP WAS NOT EXECUTED.` | skipped by an `IF` | `status: not executed` |
| `IEF472I EWSBATCH STEP070 - COMPLETION CODE - SYSTEM=0C7 ...` | abend | `status: abended, abend: S0C7` |

An action fails if any step exceeds its allowed RC (4 for EWSBATCH/EWSCOMP, 0 for EWSRPTJ), abended, or was skipped.

## 5. Character encoding

z/OS stores text in **EBCDIC** (code page IBM-1047). Zowe uploads and downloads in **text mode**, so z/OSMF converts each byte between ASCII and EBCDIC and splits/joins records at line ends:

* upload: each line of the local file becomes one fixed-length record (padded with blanks to the LRECL);
* download: each record becomes one line (trailing blanks of FB records are kept; VB records have none).

This only works if every byte is a character. Hence all numeric fields in files that cross the boundary are **zoned decimal** (digits as characters), with no signs and no packed or binary fields. `tests/test_layouts.py` checks that all mainframe sources are pure ASCII and fit their columns.

## 6. Behaviour of the Z Xplore system that the code works around

| Observed | Handling |
|---|---|
| Occasional `Failed to send an HTTP request` (connection reset) | `zowe.run` retries up to 3 times with back-off |
| One COBOL source was always cut off during upload: the network filter in front of z/OSMF flags content that looks like SQL injection (`SELECT ...` together with literals such as `' HIGH=' ... ' LOW='`) | The `DISPLAY` text in `EWSRPT` was reworded; the upload error message explains this case if it ever happens again |
| SMS rejects allocations in cylinders (`--size 2CYL` → "SMS or ACS services returned an error"), tracks work | All allocations, in the backend and in JCL `SPACE=`, use tracks |
| The site `IGYWCL` compile procedure reads `&SYSUID..CBL(&SRC)` and links into `&SYSUID..LOAD(&SRC)`; its COBOL step has no `SYSLIB` | COBOL sources go to `Z72230.CBL`; `EWSCOMP` adds `//COBOL.SYSLIB DD DSN=&SYSUID..EWS.CPY` for the copybooks |
| DFSORT on this system does not support `SUM FIELDS=NONE,XSUM` (`ICE172A`) | Duplicate removal uses ICETOOL `SELECT ... FIRST DISCARD(DUPS)` |

## 7. Zowe Explorer

Not needed to use the system. It shares the same `zosmf` profile, so everything the backend creates is visible there: add a filter `Z72230.EWS.*` in the Data Sets tree and `Owner Z72230, Prefix EWS*` in the Jobs tree. It is useful for editing COBOL with IBM Z Open Editor syntax checks.
