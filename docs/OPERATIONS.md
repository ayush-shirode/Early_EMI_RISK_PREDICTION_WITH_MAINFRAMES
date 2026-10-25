# Operations: install, run, test, demo, troubleshoot

## 1. Prerequisites

| Need | Check |
|---|---|
| Node.js 18+ and npm | `node -v` |
| Python 3.11+ | `python3 --version` |
| Zowe CLI v3 | `zowe --version` (install: `npm install -g @zowe/cli`) |
| A Zowe profile that reaches z/OSMF | `zowe zosmf check status` → "user … successfully connected" |

To create the profile on a new machine: `zowe config init --global-config`, set `host` and `port` (Z Xplore: `204.90.115.200`, `10443`, `rejectUnauthorized: false`), then `zowe config secure` to store user and password.

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

## 4. Demo script (about 10 minutes)

1. **Mainframe → Overview**: connected to z/OS, checklist complete, explain the 5 steps.
2. **Data sets**: open `Z72230.EWS.CUSTMAST` (fixed-width records as stored on z/OS), then `Z72230.EWS.JCL` → `EWSBATCH`.
3. **Batch runs → Run batch & score**: follow the timeline; point at the JCL step chips (DFSORT → COBOL validate → COBOL match → DFSORT CSV → REXX), RC 4 on the validation steps because bad records were rejected.
4. Click **Job output** → `STEP070 SYSOUT` (EWSMATCH counts), `STEP090 SYSTSPRT` (REXX reconciliation), `JESYSMSG` (the return codes).
5. **Reports → Rejected records** (reason codes) and **Reconciliation** (all checks OK).
6. **Customers** → filter High → open one → **SHAP analysis**: why this customer is high risk.
7. **Dashboard → What-if**: lower the EMI, re-score, risk drops.
8. **Reports → Intervention report**: the list printed by COBOL on the mainframe from the scores written back.
9. **Model**: AUC, tiers vs actual outcomes, confusion matrix, feature importance.

## 5. Tests

```bash
make test        # = .venv/bin/python -m pytest -q tests
```

| File | What it proves |
|---|---|
| `test_layouts.py` | Python layouts = copybooks (every field length, every LRECL); FEAT2CSV member = generated from the layouts; all mainframe sources are ASCII and fit their fixed columns |
| `test_generator_and_rules.py` | records have exact lengths; generator is deterministic; every injected defect is rejected with the expected reason code; TRAIN/SCORE label behaviour; **no data after the as-of date affects features** |
| `test_pipeline.py` | JESYSMSG step-RC parsing (normal, proc step, skipped, abend); RUNCTL/REJREC parsing; API rejects unknown actions, bad parameters, bad job IDs and non-project data set names |
| `test_mainframe_golden.py` | **the CSV produced by COBOL on z/OS equals the Python reference rules for every customer and every field** (runs on the latest downloaded batch output; skipped if none) |

Current result: 31 passed.

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Header shows `BACKEND OFFLINE` | backend not running: `make dev` or `make api` |
| `MAINFRAME OFFLINE` / "not connected" | z/OSMF unreachable or password expired. Run `zowe zosmf check status` in a terminal; reset with `zowe config secure`. Z Xplore can also be down for maintenance. Already-scored results stay visible. |
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

* Mainframe credentials stay in the Zowe secure store (OS keyring); they are never in the repo, `.env`, the database or the browser.
* The backend binds to 127.0.0.1. The API exposes eight fixed actions with validated parameters; data set names are built server-side; previews are limited to `HLQ.EWS.*`; job IDs are pattern-checked.
* Only synthetic data is uploaded to Z Xplore, a shared IBM education system.
* `data/` (local database, downloaded files) and `ml/artifacts/` are git-ignored.

## 8. Clean up

* Local: `make clean` (removes run folders, the SQLite file and the Next.js build).
* Mainframe: **Reset data** in the Control Center deletes all `EWS.*` data sets except the source libraries. To remove everything, also delete `Z72230.EWS.JCL/CPY/CNTL/REXX` and the `EWS*` members of `Z72230.CBL` and `Z72230.LOAD` (e.g. in Zowe Explorer).
