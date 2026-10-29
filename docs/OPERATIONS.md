# Operations: install, run, test, demo, troubleshoot

## 1. Prerequisites

| Need | Check |
|---|---|
| Node.js 18+ and npm | `node -v` |
| Python 3.11+ | `python3 --version` |
| An OS keyring (GNOME Keyring / KWallet on Linux, Keychain on macOS) | `python -c "import keyring; print(keyring.get_keyring())"` |
| A z/OS user ID with z/OSMF and SSH access | `make login` → "Logged on: …" |

On a new machine: `make login` (Z Xplore: host `204.90.115.200`, z/OSMF port `10443`, SSH port `22`, verify TLS `n`), then `make login-ssh` to pin the SSH host key and install the agent. Both can also be done in `make tui` (LOGON panel, then `SSHKEY` and `INSTALL` on the connection panel).

## 2. Install and start

```bash
cd ~/mainframes/CP
make install    # .venv with ml/requirements.txt + dashboard/node_modules
make dev        # backend 127.0.0.1:8000 + dashboard http://localhost:3000  (Ctrl-C stops both)
```

## 3. First use (all in the browser, http://localhost:3000/mainframe)

1. **Test connection**: green card with your user ID.
2. **Set up mainframe**: allocates `Z72230.EWS.{JCL,CPY,CNTL,REXX}`, uploads all sources, compiles. Watch the steps live.
3. **Generate & upload**: 1,500 customers (200–3,000), seed 42.
4. **Train model**: four TRAIN batches and training (~2.5 min).
5. **Run batch & score** for as-of 2026-09-30 (~70 s).

Then use Dashboard, Customers, AI Analysis, and Mainframe → Reports.

## 4. Demo

See [DEMO.md](DEMO.md) for the full click-by-click demo script, expected results and likely questions.

## 5. Tests

```bash
make test        # = .venv/bin/python -m pytest -q tests
```

| File | What it proves |
|---|---|
| `test_layouts.py` | Python layouts = copybooks (every field length, every LRECL); FEAT2CSV member = generated from the layouts; all mainframe sources are ASCII and fit their fixed columns |
| `test_generator_and_rules.py` | records have exact lengths; generator is deterministic; every injected defect is rejected with the expected reason code; TRAIN/SCORE label behaviour; **no data after the as-of date affects features** |
| `test_vsam.py` | IDCAMS output parsing on real z/OS output (`PRINT … HEX` decoded from EBCDIC, `LISTCAT` statistics); key not found is an empty result; both KSDS records parsed for a lookup; EWSSUPD counters read from SYSOUT; report lines carry the VSAM name; every data set qualifier fits 8 characters |
| `test_zos.py` | the z/OSMF client builds the right requests (JCL symbols as headers, quoted upper-case data set paths, half-track block sizes) and reports z/OSMF errors; a run in another live process blocks a new one, and a dead process's run is cleaned up |
| `test_pipeline.py` | JESYSMSG step-RC parsing (normal, proc step, skipped, abend); RUNCTL/REJREC parsing; API rejects unknown actions, bad parameters, bad job IDs and non-project data set names |
| `test_mainframe_golden.py` | **the CSV produced by COBOL on z/OS equals the Python reference rules for every customer and every field** (runs on the latest downloaded batch output; skipped if none) |

Current result: 45 passed (the golden test included).

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Header shows `BACKEND OFFLINE` | backend not running: `make dev` or `make api` |
| `MAINFRAME OFFLINE` / "not connected" | z/OSMF unreachable or password expired. Check with `make tui` (connection panel shows the last error) or `python -m pipeline.zosconf show`; log on again with `make login`. Z Xplore can also be down for maintenance. Already-scored results stay visible. |
| `z/OSMF rejected the user ID or password (HTTP 401)` | password changed or expired: `make login` |
| SSH channel `NOKEY` in the console | the SSH host key is not trusted yet: `make login-ssh`, or `SSHKEY` on the connection panel |
| `The EWS agent is not installed on USS yet` | `make login-ssh`, or `INSTALL` on the connection panel |
| `409 Run #N is still active (started from the TUI)` | the operator console is running an action; wait for it (the console's PIPELINE panel shows it live) |
| `409 Run #N is still active` | one action at a time; open the run from the banner and wait |
| A step failed with `Job EWSBATCH (JOB…) failed: step STEP050 RC=8` | more than 10% of customer records were rejected; open the job output and Reports → Rejected records |
| `... abended S0C7` | a COBOL program read non-numeric data in a numeric field; check the generator/layout change you made and `make test` |
| `EWSRECON reports the batch is out of balance (CHK_...)` | record counts do not add up; open the run's RUNCTL panel to see which check failed |
| `Upload of X was cut off by the server` | the Z Xplore network filter rejected the file's content (looks like SQL injection); reword literal text such as `SELECT ...` next to `' NAME='` strings |
| `Dynamic allocation Error - SMS or ACS services returned an error` | allocation too large or in cylinders; sizes in `pipeline/config.py` and the JCL are in tracks |
| `No trained model yet` | run **Train model** first |
| Dashboard shows old numbers | click Refresh, or the run did not finish (check Batch runs) |

Logs: the run page shows each step's error; the full Python traceback is in `data/runs/<id>/error.txt`; every downloaded file is in the same folder.

## 7. Security notes

* The mainframe password stays in the OS keyring (service `ews-zos`); it is never in the repo, `.env`, the database, a log or the browser. `~/.config/ews/zos.json` holds only host, ports and user ID.
* The z/OS SSH host key is pinned in `~/.config/ews/known_hosts`; a changed key refuses the connection.
* The operator console acts with the user's full z/OS authority (its command shell is a real shell). It runs locally, in the user's own terminal.
* The backend binds to 127.0.0.1. The API exposes eight fixed actions with validated parameters; data set names are built server-side; previews are limited to `HLQ.EWS.*`; job IDs are pattern-checked.
* Only synthetic data is uploaded to Z Xplore, a shared IBM education system.
* `data/` (local database, downloaded files) and `ml/artifacts/` are git-ignored.

## 8. Clean up

* Local: `make clean` (removes run folders, the SQLite file and the Next.js build).
* Mainframe: **Reset data** in the Control Center deletes all `EWS.*` data sets except the source libraries. To remove everything, also delete `Z72230.EWS.JCL/CPY/CNTL/REXX`, the `EWS*` members of `Z72230.CBL` and `Z72230.LOAD`, and `~/ews` on USS.
