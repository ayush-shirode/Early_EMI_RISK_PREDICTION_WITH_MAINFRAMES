# Backend and local database

Code: `api/main.py` (FastAPI), `pipeline/` (runner, actions, z/OSMF client, SSH channel, SQLite), `ml/` (scoring).

Start with `make dev` or `make api`. It listens on **127.0.0.1:8000 only**, because it acts with your mainframe credentials. Interactive API docs: http://127.0.0.1:8000/docs.

## 1. Modules

| Module | Responsibility |
|---|---|
| `pipeline/config.py` | paths, HLQ, as-of dates, tier thresholds; `Names` builds every data set name from the HLQ |
| `pipeline/zosconf.py` | host, ports, user ID (`~/.config/ews/zos.json`) and password (OS keyring); `python -m pipeline.zosconf login` |
| `pipeline/zos.py` | our z/OSMF REST client: one function per data set or job operation; retries, error messages, step-RC parsing ([MAINFRAME_CONNECTION.md](MAINFRAME_CONNECTION.md)) |
| `pipeline/uss.py` | SSH channel to z/OS UNIX: commands, host-key pinning, installing and calling the EWS agent |
| `pipeline/oplog.py` | operator log: every mainframe call, job, run step and connection change, with message IDs |
| `pipeline/actions.py` | the eight actions behind the Control Center buttons, each a list of named steps |
| `pipeline/runner.py` | runs one action at a time in a background thread and records every step in SQLite |
| `pipeline/db.py` | SQLite schema and helpers |
| `pipeline/cli.py` | the same actions from a terminal, for debugging (`python -m pipeline.cli run_batch asof=20260930`) |
| `api/main.py` | REST endpoints for the dashboard |

## 2. Actions

| Name (POST `/actions/{name}`) | Parameters | Steps | Time (1,500 customers) |
|---|---|---|---|
| `test_connection` | — | Connect to z/OSMF | seconds |
| `setup` | — | connect · allocate libraries (only missing ones) · upload copybooks · COBOL · DFSORT · REXX · JCL · submit EWSCOMP · verify load modules | 1.5 min |
| `compile` | — | upload copybooks + COBOL · EWSCOMP · verify | < 1 min |
| `upload_sources` | — | upload DFSORT, REXX, JCL | < 1 min |
| `generate_data` | `customers` 200–3000, `seed` | generate locally · delete+allocate the 4 input data sets · upload each | 40–60 s |
| `train_model` | — | EWSBATCH TRAIN ×4 (each: submit, step RCs, download, check RUNCTL) · train | 2.5 min |
| `run_batch` | `asof` YYYYMMDD (2025-03-31…2026-09-30) | EWSBATCH SCORE · load master data · score + SHAP · write SCORES · EWSRPTJ · download report | 70 s |
| `reset_data` | `confirm: true` | delete all `EWS.*` data sets except the 4 source libraries | < 1 min |

Rules enforced by the API (`_validate` in `api/main.py`):
* unknown action → 404; unexpected parameter names → 400; values outside their range → 400;
* a second action while one is running → **409** "Run #N is still active";
* the browser can never send a data set name or a command for these actions.

## 3. The runner

```
POST /actions/run_batch {"asof": 20260930}
  → runner.start(): INSERT INTO runs (status='running') → returns {runId} immediately
  → background thread: actions.run_batch(ctx, asof)
       ctx.plan([...6 step names...])          → run_steps rows with status 'pending'
       with ctx.step("Submit EWSBATCH ..."):    → status 'running', started_at
           step.detail("..."), step.data(jobid=..., steps=[...RCs...], runctl={...})
       (exception)                              → step 'failed' + message, run 'failed'
  → finally: pending steps → 'skipped', run → 'ok' | 'failed', summary saved
GET /runs/{id}  (the UI polls every 2 s while status='running')
```

Each run also gets a folder `data/runs/<id>/` with every downloaded file (features, RUNCTL, rejects, exceptions, master data, scores, report) and `error.txt` with the Python traceback if it failed. Only one run is active at a time across the backend, the operator console and the CLI: `runner.start` checks for a `running` run and inserts the new one inside one `BEGIN IMMEDIATE` transaction. A run whose process (`runs.pid`) has died is marked failed then, and also when the backend starts.

## 4. Local database (SQLite)

File: `CP/data/ews.sqlite` (path overridable with `EWS_DB`). WAL mode; all writes go through one lock. It is a **cache of what the mainframe produced** plus run history; deleting it loses only history (run a batch again to repopulate).

```sql
runs(id PK, action, params JSON, status running|ok|failed, started_at, finished_at, error, summary JSON,
     pid, source API|TUI|CLI)                                    -- pid = process running it
run_steps(run_id, seq, name, status pending|running|ok|failed|skipped,
          started_at, finished_at, detail, data JSON)            -- PK (run_id, seq)
customers(cust_id PK, name, city, emp_type, age, monthly_income, credit_score, open_date, status)
loans(loan_id PK, cust_id, loan_type, principal, int_rate, tenure, start_date, emi_amt, due_day,
      outstanding, status)                                       -- index on cust_id
monthly(cust_id, yyyymm, credits, debits, salary, min_bal, avg_bal, bounces, cc_util)
                                                                 -- PK (cust_id, yyyymm)
predictions(id PK, run_id, cust_id, as_of, probability, tier, action, top_factor, reasoning,
            features JSON, shap JSON, model_version, created_at) -- indexes (cust_id,id), (run_id)
kv(key PK, value JSON)    -- last_score_run, data (generator settings), setup_done, compiled
oplog(id PK, ts, pid, channel ZOSMF|SSH|RUN|CONN, level I|W|E, msgid, text, ms)
                                                                 -- operator log, last 20,000 rows
```

| Table | Filled from | When |
|---|---|---|
| runs, run_steps | the runner | every action |
| customers, loans, monthly | `EWS.CUST.VALID`, `EWS.LOAN.VALID`, `EWS.TXN.SRT` downloaded from z/OS | every `run_batch` (replaced) |
| predictions | model output for `EWS.FEATCSV` | every `run_batch` (appended, one row per customer per run → history) |
| kv | actions | setup, generate, run |

`predictions.features` keeps the exact mainframe feature values used, and `predictions.shap` keeps the full explanation, so any past score can be explained later without re-running anything.

## 5. API reference

All paths are relative to `http://127.0.0.1:8000` (the dashboard calls them as `/api/backend/...`).

### Control Center

| Method & path | Returns |
|---|---|
| `GET /health` | `{ok, active_run}` |
| `GET /mainframe/status?refresh=` | connection (user, system, z/OSMF version), HLQ, which libraries/programs/input data sets exist, data/model/last-run summary, active run. The mainframe part is cached 60 s. |
| `GET /actions` | the action names and labels |
| `POST /actions/{name}` | `{runId}`; 400/404/409 as above |
| `GET /runs?limit=&action=` | run history |
| `GET /runs/{id}` | run with all steps, job IDs, step RCs, RUNCTL values, errors |
| `GET /jobs/{jobid}/spool` | job status and spool file list (job ID validated against `^(JOB\|J\|STC\|TSU)\d+$`) |
| `GET /jobs/{jobid}/spool/{fileId}` | spool file text |
| `GET /datasets` | the `EWS.*` data sets with organisation, RECFM, LRECL, usage |
| `GET /datasets/{dsn}/preview?records=` | first N records, or the member list for a PDS. **Only `HLQ.EWS.*` names are allowed** (403 otherwise). |
| `GET /reports/{riskrpt\|rejects\|exceptions\|runctl}?runId=` | parsed reports of a run (default: last scoring run) |
| `GET /model` | `metrics.json` |

### Risk views

| Method & path | Returns |
|---|---|
| `GET /customers` | every customer scored in the last run, sorted by probability, in the dashboard's `Customer` shape |
| `GET /customers/{id}` | the same plus all loans and the 24-month account history |
| `GET /customers/{id}/explanation?top=` | SHAP values (top N + "other"), baseline, reasoning, action, model version |
| `GET /customers/{id}/history` | the customer's predictions across runs |
| `POST /customers/{id}/what-if` `{emiAmount}` | re-scored probability, tier, reasoning for a different EMI |
| `GET /portfolio` | counts and EMI at risk per tier |

Example:

```bash
curl -s -X POST localhost:8000/actions/run_batch -H 'content-type: application/json' -d '{"asof":20260930}'
# {"runId":14}
curl -s localhost:8000/runs/14 | jq '.steps[] | {name, status, detail}'
curl -s localhost:8000/customers/CUST0166/explanation?top=3 | jq '.features[] | {label, display, shap}'
```
