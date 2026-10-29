# Architecture

## 1. Components

```
 Browser ──HTTP──► Next.js dashboard (:3000)
                     │  /api/backend/*  (rewrite proxy, same origin)
                     ▼
                   FastAPI backend (127.0.0.1:8000)                       local machine
                     ├─ api/main.py          REST endpoints
                     ├─ pipeline/runner.py   background executor, one action at a time
                     ├─ pipeline/actions.py  the Control Center actions (named steps)
                     ├─ pipeline/zos.py      our z/OSMF REST client: every data set and job call
                     ├─ ml/*                 generator, training, scoring, SHAP
                     └─ data/ews.sqlite      local copy of results (runs, customers, predictions)
                     │
                     │ HTTPS, basic auth then LTPA cookie (credentials: pipeline/zosconf.py + OS keyring)
                     ▼
                   z/OSMF REST API  https://204.90.115.200:10443   (TLS, basic auth)
                     ├─ /zosmf/restfiles/ds   data sets: list, create, upload, download, delete
                     └─ /zosmf/restjobs/jobs  jobs: submit, status, spool
                     ▼
                   IBM z/OS 3.1 (IBM Z Xplore, system S0W1)                 mainframe
                     ├─ JES2 runs EWSCOMP / EWSBATCH / EWSRPTJ
                     ├─ DFSORT + ICETOOL, Enterprise COBOL 6.5, TSO/E REXX
                     └─ Z72230.EWS.* data sets (PS + PDS-E, SMS-managed)
```

| Layer | Technology | Code |
|---|---|---|
| UI | Next.js 14.2 (App Router), React 18, Tailwind, Recharts | `dashboard/` |
| API | FastAPI + Uvicorn (Python 3.11) | `api/main.py` |
| Orchestration | Python threads, SQLite | `pipeline/runner.py`, `pipeline/actions.py`, `pipeline/db.py` |
| Mainframe access | own z/OSMF REST client (`requests`); SSH channel (`paramiko`) + agent on USS | `pipeline/zos.py`, `pipeline/uss.py`, `mainframe/uss/ewsagent.py` |
| Operator console | Textual (terminal UI) | `tui/` |
| Mainframe processing | JCL, DFSORT/ICETOOL, Enterprise COBOL 6.5, REXX | `mainframe/` |
| ML | pandas, scikit-learn, XGBoost, SHAP | `ml/` |

## 2. The two stores

| Store | What lives there | Role |
|---|---|---|
| **z/OS data sets** (`Z72230.EWS.*`) | Input master files, intermediate sorted/validated files, features, rejects, control totals, scores, report | **System of record**. All data preparation happens here. See [MAINFRAME_DATASETS.md](MAINFRAME_DATASETS.md). |
| **SQLite** (`CP/data/ews.sqlite`) | Run history and step status, a copy of the customer/loan/monthly master data downloaded from z/OS, predictions with SHAP values | **Serving cache** for the dashboard, so pages load instantly and still work if the mainframe is offline. See [BACKEND_AND_DATABASE.md](BACKEND_AND_DATABASE.md). |

On z/OS the batch data is QSAM sequential files and the code is in PDS-E libraries; two **VSAM KSDS** clusters keyed by customer ID (`CUSTKSDS`, `SCORKSDS`) give keyed access to one customer. No DB2. See [MAINFRAME_DATASETS.md](MAINFRAME_DATASETS.md#35-vsam-clusters-ksds-key--customer-id).

## 3. End-to-end data flow of one scoring run

```
User clicks "Run batch & score" (as-of 2026-09-30)
│
├─1  PUT /zosmf/restjobs/jobs {"file":"//'Z72230.EWS.JCL(EWSBATCH)'"}  X-IBM-JCL-Symbol-ASOFDT/MODE, poll to OUTPUT
│     JES2 runs EWSBATCH on z/OS:
│       STEP005/006 IEFBR14   clean up, allocate REJECTS + CTLTOT
│       STEP010 ICETOOL       CUSTMAST → CUST.SRT (sorted, duplicates → CUST.DUPS)
│       STEP020 DFSORT        LOANMAST → LOAN.SRT
│       STEP030 DFSORT        REPAYHST → REPAY.SRT, non-numeric → REJECTS (S01)
│       STEP040 DFSORT        TXNSUMM  → TXN.SRT,   non-numeric → REJECTS (S02)
│       STEP050 COBOL EWSVCUST  CUST.SRT → CUST.VALID, bad → REJECTS (C01-C08)
│       STEP055 IDCAMS        CUST.VALID → VSAM KSDS CUSTKSDS (DEFINE CLUSTER + REPRO)
│       STEP060 COBOL EWSVLOAN  LOAN.SRT → LOAN.VALID, bad → REJECTS (L01-L09)
│       STEP070 COBOL EWSMATCH  4-file match → FEATURES (+ EXCEPT M01-M05)
│       STEP080 DFSORT        FEATURES → FEATCSV (CSV, variable length)
│       STEP090 REXX EWSRECON reconcile all counts → RUNCTL (STATUS=OK|OUT_OF_BALANCE)
├─2  backend reads step return codes from the JESYSMSG spool (IEF142I lines)
├─3  download: FEATCSV, RUNCTL, REJECTS, EXCEPT; refuses to continue unless STATUS=OK
├─4  download: CUST.VALID, LOAN.VALID, TXN.SRT → SQLite (names, loans, history for the UI)
├─5  Python: XGBoost probability + SHAP for every customer → SQLite predictions
├─6  Python writes SCOREREC records → create + upload → Z72230.EWS.SCORES
├─7  submit EWSRPTJ: COBOL EWSSUPD updates the VSAM KSDS SCORKSDS by key, DFSORT sorts scores by risk,
│     COBOL EWSRPT prints RISKRPT with names read by key from the KSDS CUSTKSDS; then LISTCAT checks both
└─8  download RISKRPT → shown in the dashboard's Reports page
```

Every arrow that touches z/OS is one z/OSMF REST call made by `pipeline/zos.py`; see [MAINFRAME_CONNECTION.md](MAINFRAME_CONNECTION.md) for the exact requests.

## 4. Training flow

"Train model" runs the same EWSBATCH job four times with `MODE=TRAIN` and as-of dates 2025-09-30, 2025-12-31, 2026-03-31 and 2026-06-30. In TRAIN mode, EWSMATCH also writes the **label**: whether the customer had a missed or bounced EMI, or one 30+ days late, in the 90 days *after* the as-of date. The four CSVs are concatenated and the model is trained with a time-based split (see [ML_MODEL.md](ML_MODEL.md)). The labels are therefore produced by the same COBOL logic, from the same system of record, as the features.

## 5. Design decisions

| Decision | Why |
|---|---|
| Mainframe does all data preparation | That is the point of the project: the batch is the system of record and the ML only consumes its output. It also mirrors how banks actually run nightly batch. |
| Own z/OSMF client in the backend, not in the browser | The browser never holds mainframe credentials; the backend reads them from the OS keyring. Calling z/OSMF directly removes the Zowe CLI dependency (Node.js, one subprocess per call) and lets every call be logged with its timing. |
| A second channel over SSH | z/OSMF cannot run commands. SSH to USS gives the operator console a shell, TSO and console commands, and a place for our own agent; it also gives an independent check of whether the system is up. |
| Sequential files for the batch, VSAM KSDS for single customers | The batch reads every record once: sequential access is fastest and needs no index. Looking up or updating one customer (latest score, previous score) is what a KSDS index is for, so the score history is updated in place by key instead of rewriting a file. |
| Run lock in SQLite, not in memory | The backend, the operator console and the CLI can all start actions; a check-and-insert inside `BEGIN IMMEDIATE` and the owning process ID keep it to one run at a time, and a run whose process died stops blocking. |
| Whitelisted actions instead of a generic "run command" API | The web API acts with your z/OS identity. It can only start eight named actions with validated parameters, and data set names are always built server-side. |
| One action at a time | All runs share the same `EWS.*` data sets; a second run would overwrite the first. |
| Display (zoned) numerics in every file that crosses the boundary | z/OSMF text-mode transfer converts ASCII ⇄ EBCDIC byte by byte. Packed decimal (COMP-3) would be corrupted, so COMP-3 is used only inside COBOL working storage. |
| COBOL writes numeric-edited features, DFSORT builds the CSV | No numeric conversion is needed in DFSORT, and the fixed record stays human-readable on the mainframe. |
| A Python reference implementation of the COBOL rules (`ml/features_ref.py`) | Lets the mainframe output be verified field by field (golden test) and the ML be developed offline. |
| XGBoost + SHAP, not an LLM | The old project asked an LLM for a probability. A trained classifier has measurable accuracy and SHAP gives exact, additive explanations. |
| SQLite instead of MongoDB/Elasticsearch/Kafka | One scoring batch per run does not need a cluster. The previous 11 containers (~11.5 GB RAM) became 2 processes (<1 GB). |

## 6. What was reused from `EDI_SEM_4_Final`

| Reused | Changed |
|---|---|
| Dashboard look and feel, `RiskGauge`, `SpendTrendChart`, `ShapWaterfallChart`, `FeatureDetailTable`, `SuggestionCards`, `AlertTimeline`, the prediction page CSS | All data now comes from the backend; the 5 hard-coded customers, fake SHAP formulas, MongoDB and Elasticsearch routes were removed; 4 severity levels became the 3 tiers of the spec; the "Ollama" what-if became model re-scoring |
| — | New: the whole Mainframe Control Center (7 pages), mainframe status in the header, customer search/filter/paging for 1,000+ customers |

Dropped: Plaid ingestion, Kafka, Logstash, Elasticsearch, Kibana, Ollama, MongoDB, the scheduler container.
