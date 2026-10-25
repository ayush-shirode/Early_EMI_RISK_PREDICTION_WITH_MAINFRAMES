# Implementation Plan — Early Warning Credit Risk & EMI Stress Prediction (Mainframe + ML)

**Project folder:** `/home/ayush/mainframes/CP`
**Based on:** `/home/ayush/College/EDI_SEM_4_Final` ("Vigilance AI", no mainframe)
**Mainframe:** IBM Z Xplore — z/OS 3.1 (z/OSMF 29), host `204.90.115.200:10443`, user `Z72230`
**Rules for this project:**
1. **The whole system is operated from the web dashboard.** Setting up the mainframe, generating and uploading data, compiling COBOL, running batch jobs, reading job output, training the model and viewing reports are all buttons and pages in the frontend. The user never has to open Zowe Explorer, a terminal or a 3270 screen.
2. **Every mainframe operation goes through Zowe.** The backend calls **Zowe CLI** (z/OSMF REST underneath) for each action the user clicks. Zowe Explorer stays useful only as an optional developer/debugging tool.

> **Status (2026-10-25): implemented and verified on IBM Z Xplore.** This file is the original plan. The implementation is documented in [README.md](README.md) and the documents it links. Where the code differs from this plan:
>
> | Plan | Implemented |
> |---|---|
> | DFSORT `SUM FIELDS=NONE,XSUM` for duplicate customer IDs | ICETOOL `SELECT ... FIRST DISCARD(DUPS)`: XSUM is not supported by DFSORT on this system (`ICE172A`) |
> | IDCAMS `DELETE` to clean up | IEFBR14 with `DISP=(MOD,DELETE,DELETE)`, which needs no in-stream symbols |
> | Allocations in cylinders | Tracks only: SMS on Z Xplore rejects CYL allocations |
> | `RUNCTL` as one FB 200 record | One `KEY=VALUE` per line in FB 80 (easier to read and parse) |
> | Backend in `ml/api.py`; `run_pipeline.py`, `setup_mainframe.py` | `api/main.py`; `pipeline/actions.py` + `pipeline/runner.py` (the UI actions), `pipeline/cli.py` for debugging |
> | Validation ROC-AUC ≥ 0.80 target | 0.825 (XGBoost), 0.823 (logistic-regression baseline); see [ML_MODEL.md](ML_MODEL.md) |
> | Calibrated with `CalibratedClassifierCV` | Not needed: the regularised XGBoost has a Brier score of 0.068 on the held-out snapshot |
> | Dashboard page `/mainframe/setup`, `/mainframe/data` | Merged into the `/mainframe` overview checklist; the data set browser is `/mainframe/datasets` |
> | Default 2,000 customers | 1,500 (≈ 77k records), adjustable 200–3,000 in the UI |

---

## 1. Goal

Predict, **before** a missed payment, how likely a borrower is to hit EMI repayment stress in the next 90 days. Then tier the customer as Low, Medium or High, explain the score with SHAP, and suggest an action.

| Customer | Risk score | Tier | Suggested action |
|---|---|---|---|
| CUST0001 | 12% | Low | Continue regular monitoring |
| CUST0002 | 56% | Medium | Review repayment patterns, send a pre-due reminder |
| CUST0003 | 89% | High | Prioritize early intervention (call, restructuring offer) |

*(Illustrative values only.)*

The mainframe is the **system of record**. Customer, loan, repayment and account data live in z/OS data sets. All cleansing, validation, matching and feature aggregation runs as a **z/OS batch job** (JCL + DFSORT + COBOL + REXX). Python only consumes the batch output, trains and scores the model, and serves the dashboard.

---

## 2. What we reuse from the old project and what we replace

| Old component (`EDI_SEM_4_Final`) | Decision | Reason |
|---|---|---|
| `services/dashboard` (Next.js 14, Tailwind, Recharts) | **Reused**, copied to `CP/dashboard` | The UI is complete: risk gauge, SHAP waterfall, customer list, comparison, EMI forecast. Only its data source changes. |
| `dashboard/src/components/*` | Reused as is | `RiskGauge`, `ShapWaterfallChart`, `FeatureDetailTable`, `SpendTrendChart`, `AlertTimeline`, `SuggestionCards`, `ModelMetaCard` all keep working once fed real data. |
| `dashboard/src/lib/customers.ts` (5 hard-coded customers) | **Replaced** by API data | Customers now come from mainframe output that the model has scored. |
| `dashboard/src/lib/shap.ts` (hand-written fake SHAP) | **Replaced** by real SHAP values from the model | Keep the `ShapFeature` / `ShapResult` types so the components don't change. |
| `dashboard/src/lib/mongodb.ts` + `/api/risk`, `/api/alerts`, `/api/trends` | **Rewritten** as thin proxies to the Python API | Same routes, so `useRiskPolling` keeps working. |
| `services/ai-engine` (Ollama LLM "prediction") | **Dropped** | An LLM guess isn't a trained, measurable classifier. It's replaced by XGBoost + Logistic Regression with real metrics (ROC-AUC, PR-AUC, recall). |
| `services/plaid-ingestion`, Kafka, Logstash, Elasticsearch, Kibana | **Dropped** | Ingestion is now mainframe batch data sets, not a US banking API stream. |
| MongoDB + `packages/db` | **Dropped**, replaced by SQLite | One file, no container. Enough for one batch run per day. |
| `services/scheduler` (cron, email alerts) | Logic moves to `pipeline/` | The "Run batch" action (`pipeline/actions.py`) replaces the nightly rescore. The mock-email pattern from `scheduler/src/notify/email.ts` can be ported later for High-tier alerts (optional). |

Effect: 11 Docker containers using ~11.5 GB of RAM become **two local processes** (FastAPI + Next.js) using under 1 GB, plus the remote mainframe.

---

## 3. Target architecture

```
                         ┌──────────────────── IBM Z Xplore (z/OS 3.1) ─────────────────────┐
 Local machine           │                                                                  │
 ─────────────           │  Z72230.EWS.CUSTMAST ┐                                           │
 ml/generate_data.py ──► │  Z72230.EWS.LOANMAST ├─► JCL EWSBATCH                            │
   (synthetic data)      │  Z72230.EWS.REPAYHST │     STEP010-040  DFSORT  sort, dedupe,    │
        │  Zowe CLI      │  Z72230.EWS.TXNSUMM  ┘                          numeric checks   │
        └─ upload ─────► │                            STEP050-060  COBOL   validate masters │
                         │                            STEP070      COBOL   EWSMATCH: match  │
                         │                                         + aggregate features     │
                         │                            STEP080      DFSORT  features → CSV   │
                         │                            STEP090      REXX    reconcile counts │
                         │                                    │                             │
                         │  Z72230.EWS.FEATCSV  ◄──────────────┤                             │
                         │  Z72230.EWS.RUNCTL   ◄──────────────┘                             │
                         │                                                                  │
                         │  Z72230.EWS.SCORES ─► JCL EWSRPTJ (DFSORT + COBOL EWSRPT)        │
                         │                        → High-risk intervention report (SYSOUT)  │
                         └──────────────────────────────────────────────────────────────────┘
                                         ▲
                                         │ z/OSMF REST (HTTPS :10443)
                                         │
                                ┌────────┴────────┐
                                │    Zowe CLI     │  allocate · upload · compile · submit
                                │ (secure creds)  │  job status · spool · download · list
                                └────────▲────────┘
                                         │ subprocess, whitelisted actions only
 ┌─────────────────────────── Backend: FastAPI (:8000, localhost) ──────────────────────────┐
 │  pipeline/actions.py   setup · generate+upload data · compile · run batch · write-back   │
 │  pipeline/runner.py    one action at a time, steps + logs saved to SQLite (live status)  │
 │  ml/train.py, ml/score.py   model training / scoring / SHAP                             │
 │  SQLite: customers, predictions, shap, runs, run_steps                                  │
 └──────────────────────────────────────────▲───────────────────────────────────────────────┘
                                            │ REST (polled every 2 s while a run is active)
 ┌──────────────────────────── Frontend: Next.js dashboard (:3000) ─────────────────────────┐
 │  Mainframe Control Center:  Connection · Setup · Data · Batch runs · Job output ·        │
 │                             Model training · Mainframe report                            │
 │  Risk views (reused):       Overview · Customers · Customer detail · SHAP · Comparison   │
 └──────────────────────────────────────────────────────────────────────────────────────────┘
```

The user's only interaction is the browser. Every arrow above the backend is automated.

---

## 4. Environment status (checked 2026-10-25)

| Item | Status |
|---|---|
| Zowe CLI | ✅ v8.36.0 (Zowe v3.6.0) at `~/.nvm/.../bin/zowe` |
| Zowe Explorer + IBM Z Open Editor (VS Code) | ✅ installed |
| Zowe team config `~/.zowe/zowe.config.json` | ✅ `zosmf` profile, port 10443, credentials in the secure store |
| z/OSMF connectivity | ✅ `zowe zosmf check status` → "user Z72230 successfully connected to S0W1" |
| Enterprise COBOL | ✅ `IGY650.SIGYPROC` (v6.5). The site `IGYWCL` proc is used as `EXEC IGYWCL,SRC=<member>` (see existing `Z72230.JCL(COBOL1J)`) and links into `Z72230.LOAD` |
| DFSORT | ✅ `SYS1.SICE*` present |
| Existing user data sets | `Z72230.CBL`, `.JCL`, `.LOAD`, `.SEQIN`, `.VSAM.KSDS`, … (none conflict with the new `Z72230.EWS.*` names) |
| Node.js / Python / Docker | ✅ node v22, python3 (pyenv), docker |
| `~/mainframes/mvs-tk5` (MVS 3.8j / Hercules) | ❌ **Not used.** TK5 has no z/OSMF, so Zowe can't talk to it, and its compilers are decades old. Z Xplore is the target. |

> **Data policy:** Z Xplore is a shared IBM education system. Only **synthetic** data is uploaded. No real customer data, ever.

---

## 5. Repository layout

```
CP/
├── docs/IMPLEMENTATION_PLAN.md      ← this file
├── mainframe/                       ← source of truth for everything uploaded to z/OS
│   ├── copybooks/   CUSTREC.cpy LOANREC.cpy REPAYREC.cpy TXNREC.cpy FEATREC.cpy SCOREREC.cpy REJREC.cpy
│   ├── cobol/       EWSVCUST.cbl EWSVLOAN.cbl EWSMATCH.cbl EWSRPT.cbl
│   ├── sortcntl/    SRTCUST SRTLOAN SRTREPAY SRTTXN FEAT2CSV SRTSCORE
│   ├── rexx/        EWSRECON.rexx  EWSSTAT.rexx
│   ├── jcl/         EWSCOMP.jcl EWSBATCH.jcl EWSRPTJ.jcl EWSCLEAN.jcl
│   └── data/        generated fixed-width files (git-ignored, except a tiny sample)
├── ml/
│   ├── layouts.py          record layouts mirroring the copybooks (one source for Python)
│   ├── generate_data.py    synthetic, seeded data generator → fixed-width files
│   ├── train.py            training + evaluation + SHAP explainer
│   ├── score.py            scoring, tiering, SHAP top factors, SQLite + SCORES file
│   ├── api.py              FastAPI for the dashboard
│   ├── requirements.txt
│   └── tests/
├── pipeline/
│   ├── zowe.py             wrapper around Zowe CLI (--rfj JSON parsing, timeouts, errors)
│   ├── actions.py          each UI button = one action made of named steps (see §7.2)
│   ├── runner.py           background executor: one action at a time, step status + logs → SQLite
│   ├── config.py           HLQ, data set names, as-of dates (env-overridable)
│   └── cli.py              same actions from a terminal (for debugging only, never required)
├── dashboard/              reused Next.js app (data layer rewired + Mainframe Control Center)
└── Makefile                `make dev` starts FastAPI + Next.js, the only command ever needed
```

---

## 6. Mainframe data design

### 6.1 Data sets (HLQ `Z72230.EWS`; JCL uses `&SYSUID..EWS` so it runs under any user)

| Data set | Org | RECFM/LRECL | Purpose |
|---|---|---|---|
| `EWS.JCL` | PDS-E | FB 80 | JCL members |
| `EWS.CPY` | PDS-E | FB 80 | COBOL copybooks |
| `EWS.CNTL` | PDS-E | FB 80 | DFSORT control statements |
| `EWS.REXX` | PDS-E | FB 80 | REXX execs (`SYSEXEC`) |
| `Z72230.CBL` (existing) | PDS-E | FB 80 | COBOL sources (needed by the site `IGYWCL` `SRC=` convention) |
| `Z72230.LOAD` (existing) | PDS-E | U | Load modules |
| `EWS.CUSTMAST` | PS | FB 100 | Customer master (input) |
| `EWS.LOANMAST` | PS | FB 80 | Loan master (input) |
| `EWS.REPAYHST` | PS | FB 80 | EMI installment history (input) |
| `EWS.TXNSUMM` | PS | FB 80 | Monthly account summary (input) |
| `EWS.CUST.SRT` / `.LOAN.SRT` / `.REPAY.SRT` / `.TXN.SRT` | PS | same as input | Sorted, deduplicated work files |
| `EWS.CUST.VALID` / `.LOAN.VALID` | PS | same as input | Records that passed COBOL validation |
| `EWS.REJECTS` | PS | FB 120 | Rejected records + reason code |
| `EWS.EXCEPT` | PS | FB 120 | Matching exceptions (orphan loan, repayment without loan, …) |
| `EWS.FEATURES` | PS | FB 200 | One fixed-width feature record per customer |
| `EWS.FEATCSV` | PS | VB 300 | Same features as CSV with a header (download target) |
| `EWS.CTLTOT` | PS | FB 80 | Control totals written by each step |
| `EWS.RUNCTL` | PS | FB 200 | One-line run summary from REXX (`key=value` pairs) |
| `EWS.SCORES` | PS | FB 80 | Model scores written back from Python |
| `EWS.RISKRPT` | PS | FBA 133 | Printed intervention report |

**Sizing:** dev runs use 500 customers (~3 MB in total). The demo uses 2,000 customers × 24 months (~60k repayment and 48k txn records, ~10 MB of inputs, ~25 MB with work files). Allocate in tracks/cylinders with secondary extents. Delete work files at the start of each run (`EWSCLEAN` / IDCAMS `DELETE … SET MAXCC=0`) to stay inside the Z Xplore quota.

**Encoding:** Zowe text-mode upload and download converts ASCII ⇄ EBCDIC (IBM-1047). So every file that crosses the boundary uses **display (zoned) numerics with no signs, and no COMP/COMP-3**. COMP-3 is fine inside COBOL `WORKING-STORAGE`.

### 6.2 Record layouts (copybooks)

**CUSTREC (FB 100)**

| Pos | Len | Field | PIC | Notes |
|---|---|---|---|---|
| 1 | 8 | CUST-ID | X(8) | `CUST0001` |
| 9 | 30 | CUST-NAME | X(30) | |
| 39 | 20 | CITY | X(20) | |
| 59 | 1 | EMP-TYPE | X | S=salaried, E=self-employed, B=business |
| 60 | 3 | AGE | 9(3) | 21–70 valid |
| 63 | 9 | MONTHLY-INCOME | 9(7)V99 | |
| 72 | 3 | CREDIT-SCORE | 9(3) | 300–900 |
| 75 | 8 | OPEN-DATE | 9(8) | YYYYMMDD |
| 83 | 1 | CUST-STATUS | X | A=active, C=closed |
| 84 | 17 | FILLER | | |

**LOANREC (FB 80)**: LOAN-ID X(10), CUST-ID X(8), LOAN-TYPE X (H/C/P/E), PRINCIPAL 9(9)V99, INT-RATE 9(2)V99, TENURE-MONTHS 9(3), START-DATE 9(8), EMI-AMOUNT 9(7)V99, EMI-DUE-DAY 9(2), OUTSTANDING 9(9)V99, LOAN-STATUS X (A/C/D), FILLER.

**REPAYREC (FB 80)**, one per installment: LOAN-ID, CUST-ID, INSTALLMENT-NO 9(3), DUE-DATE 9(8), PAID-DATE 9(8) (zeros = unpaid), EMI-DUE-AMT 9(7)V99, PAID-AMT 9(7)V99, DAYS-PAST-DUE 9(3), PAY-STATUS X (P=on time, L=late, R=partial, M=missed, B=bounced), FILLER.

**TXNREC (FB 80)**, one per customer per month: CUST-ID, YYYYMM 9(6), TOTAL-CREDITS 9(7)V99, TOTAL-DEBITS 9(7)V99, SALARY-CREDIT 9(7)V99, MIN-BALANCE 9(7)V99, AVG-BALANCE 9(7)V99, BOUNCE-COUNT 9(2), CC-UTIL-PCT 9(3)V99, FILLER.

**FEATREC (FB 200)**, produced by EWSMATCH, one per eligible customer:

| Feature | Meaning (all windows end at the as-of date) |
|---|---|
| `cust_id`, `as_of_date` | keys |
| `emp_type`, `age`, `monthly_income`, `credit_score` | profile |
| `active_loans`, `total_emi`, `total_outstanding` | exposure |
| `emi_to_income` | total EMI ÷ income |
| `tenure_remaining_max` | months left on the longest active loan |
| `late_cnt_3m`, `late_cnt_12m` | installments paid late |
| `missed_cnt_12m`, `partial_cnt_12m`, `emi_bounce_cnt_6m` | serious delinquency signals |
| `max_dpd_12m`, `avg_dpd_6m`, `dpd_trend` | days past due, and the change (avg of last 3 minus prior 3) |
| `avg_balance_3m`, `min_balance_3m`, `balance_trend_pct` | liquidity |
| `savings_to_emi` | avg balance 3m ÷ total EMI |
| `salary_missing_6m` | months with no salary credit (income shock) |
| `debit_credit_ratio_3m`, `spend_trend_pct` | spending pressure |
| `cc_util_avg_3m` | credit-card utilization |
| `label_stress_90d` | **TRAIN mode only** (see 6.4) |

These map directly onto the dashboard's existing SHAP features (`savings_gap`, `spend_trend_3m`, `income_utilisation`, `emi_income_ratio`, `credit_score`, `avg_balance`, `tenure_remaining`) and add the repayment-behavior features the old project never had.

### 6.3 Batch job `EWSBATCH`

Symbols are passed from Zowe: `--jcl-symbols "ASOFDT=20260930,MODE=SCORE"`.

| Step | Program | What it does | RC policy |
|---|---|---|---|
| STEP005 | IDCAMS | Delete previous work/output data sets (`SET MAXCC=0`) | always 0 |
| STEP010 | DFSORT `SRTCUST` | Sort customers by CUST-ID. `SUM FIELDS=NONE,XSUM` drops duplicate IDs (dups → SORTXSUM). `OUTFIL` counts records into CTLTOT | 0 |
| STEP020 | DFSORT `SRTLOAN` | Sort loans by CUST-ID + LOAN-ID | 0 |
| STEP030 | DFSORT `SRTREPAY` | Sort by CUST-ID + LOAN-ID + DUE-DATE. `INCLUDE COND=(22,8,ZD,EQ,NUM,AND,…)` keeps only numeric dates/amounts. `OUTFIL SAVE` sends bad records to REJECTS | 0 / 4 if rejects |
| STEP040 | DFSORT `SRTTXN` | Sort by CUST-ID + YYYYMM, with the same numeric checks | 0 / 4 |
| STEP050 | COBOL `EWSVCUST` | Validate customers: numeric fields, age/score ranges, valid dates (`FUNCTION TEST-DATE-YYYYMMDD`), status. Writes VALID + REJECTS with reason codes | 0 / 4 rejects / 8 if reject % > threshold / 16 I/O error |
| STEP060 | COBOL `EWSVLOAN` | Validate loans: EMI > 0, tenure 1–360, start date ≤ as-of, status in A/C/D | same |
| STEP070 | COBOL `EWSMATCH` | **Balanced-line match** of 4 sorted files on CUST-ID (and LOAN-ID). Aggregates the windows above using `FUNCTION INTEGER-OF-DATE` for date math and `COMPUTE … ROUNDED … ON SIZE ERROR` for ratios. Orphans → EXCEPT. Excludes customers already in default (status D or DPD ≥ 90 at as-of): they aren't "early warning" any more. PARM `'&ASOFDT&MODE'` | 0 / 4 exceptions |
| STEP080 | DFSORT `FEAT2CSV` | `OUTFIL FTOV,VLTRIM=C' ',HEADER1=(…),BUILD=(…,ZD,EDIT=(…))` turns fixed-width features into a readable CSV | 0 |
| STEP090 | REXX `EWSRECON` (IKJEFT01, `SYSEXEC`) | Reads CTLTOT with `EXECIO`. Checks `input = valid + rejected` for each file and `features = eligible customers`. Writes one `RUNCTL` record: `asof=… mode=… cust_in=… cust_valid=… rejects=… features=… status=OK` | 0 / 8 if out of balance |

Steps after 010 use `// IF (RC <= 4) THEN` so a failed step stops the job before bad features are produced. The Python side refuses to score unless `RUNCTL status=OK`.

**`EWSCOMP`** compiles all four programs with `EXEC IGYWCL,SRC=EWSxxxx`, adding `//COBOL.SYSLIB DD DSN=&SYSUID..EWS.CPY,DISP=SHR` for copybooks. *(Check in Phase 2 that the site proc's step is named `COBOL`. Look at the expanded JCL in the `COBOL1J` spool.)*

**`EWSRPTJ`** (write-back): DFSORT sorts `EWS.SCORES` by probability descending, then COBOL `EWSRPT` prints a paginated "Early Intervention List" (High tier first, with totals per tier) to `SYSOUT` and `EWS.RISKRPT`. This closes the loop: the model's output goes back into the system of record, and operations teams can see it on the mainframe.

### 6.4 Labels without leakage (TRAIN vs SCORE mode)

The same batch job creates the training data, so features and labels both come from the mainframe:

- **SCORE mode** (`ASOFDT=20260930`): features use only records with dates ≤ as-of. No label.
- **TRAIN mode** (`ASOFDT=20250930 … 20260630`, quarterly): same features, plus `label_stress_90d = 1` if, in the **90 days after** as-of, any installment is Missed or Bounced, or reaches DPD ≥ 30.

Running TRAIN at 4 quarterly as-of dates gives about 4 × 2,000 = 8,000 labeled rows. **Time-based split:** train on as-of ≤ 2026-03-31 and validate on 2026-06-30. Never use a random split, because the same customer appears in several snapshots.

---

## 7. How the software uses the mainframe (Zowe, driven from the frontend)

### 7.1 Flow of one button click

```
User clicks "Run batch (as-of 2026-09-30)"
  → Next.js  POST /api/mainframe/actions {action:"run_batch", asof:"20260930"}
  → FastAPI  creates run #42 in SQLite, starts it in the background, returns {runId:42}
  → runner   executes the steps one by one, each step = one or more Zowe CLI calls
  → UI       polls GET /runs/42 every 2 s and draws the step timeline live
             (✓ upload  ✓ submit JOB01234  ⟳ STEP070 EWSMATCH running …)
  → on finish the UI shows step RCs, RUNCTL counts, rejects, and links to the spool viewer
```

### 7.2 Actions available in the UI

| UI button | Steps the backend runs | Zowe CLI used |
|---|---|---|
| **Test connection** | check z/OSMF, show user/system/version | `zowe zosmf check status` |
| **Set up mainframe** (first time) | allocate `EWS.*` libraries + input data sets → upload JCL/COBOL/copybooks/DFSORT/REXX sources → submit `EWSCOMP` → verify load modules | `create pds/ps`, `upload dir-to-pds`, `submit data-set --wfo`, `list all-members Z72230.LOAD` |
| **Recompile programs** | upload changed sources → `EWSCOMP` → show compile listing on errors | `upload dir-to-pds`, `submit`, `view spool-file-by-id` |
| **Generate & upload data** (customer count, seed) | run `generate_data.py` → upload the 4 input files | `upload file-to-data-set` |
| **Run batch (SCORE)** for an as-of date | submit `EWSBATCH` MODE=SCORE → wait → collect step RCs → download `FEATCSV` + `RUNCTL` → check `status=OK` → score + SHAP → write scores back → submit `EWSRPTJ` | `submit --js … --wfo`, `list spool-files-by-jobid`, `download data-set`, `upload file-to-data-set` |
| **Train model** | 4× `EWSBATCH` MODE=TRAIN (quarterly as-of dates) → download each → `train.py` → metrics | same as above |
| **View job output** | list spool files for a job, open one (SYSOUT, SYSPRINT, SYSTSPRT, JESMSGLG) | `list spool-files-by-jobid`, `view spool-file-by-id` |
| **Browse data sets** | list `Z72230.EWS.*` with size/date; preview the first 50 records of a data set | `list data-set -a`, `view data-set` |
| **View reports** | REJECTS, EXCEPT, RISKRPT rendered as tables | `download data-set` |
| **Reset mainframe data** (confirmation dialog) | delete `EWS.*` work + output data sets | `delete data-set` |

### 7.3 Backend rules for Zowe calls
- **Whitelisted actions only.** The API accepts an action name + validated parameters (date `YYYYMMDD`, customer count 100–5000). It never runs an arbitrary command or data set name sent from the browser. Data set names are always built from `config.py` (`HLQ.EWS.*`).
- **Localhost only.** FastAPI binds to `127.0.0.1`, because it acts with your mainframe credentials.
- **Credentials** come from the Zowe secure store (already set up). They're never in the repo, `.env` or browser. The **Connection** panel only shows status; if credentials are missing, it shows the one-time `zowe config secure` instruction.
- **One action at a time** (lock), so two runs can't overwrite the same data sets. Buttons are disabled while a run is active.
- **Timeouts and clear errors:** each step has a timeout. A failure shows the job ID, failing step, RC and the last lines of its spool directly in the UI.
- The backend runs **locally (not in Docker)** so Zowe CLI can read the OS keyring.

### 7.4 Zowe CLI commands behind the actions

```bash
# Set up mainframe
zowe zos-files create pds Z72230.EWS.JCL  --rf FB --rl 80 --dst LIBRARY
zowe zos-files create ps  Z72230.EWS.CUSTMAST --rf FB --rl 100 --bs 27900 --size 15TRK

# sources → PDS (one member per file)
zowe zos-files upload dir-to-pds mainframe/jcl      Z72230.EWS.JCL
zowe zos-files upload dir-to-pds mainframe/cobol    Z72230.CBL
zowe zos-files upload dir-to-pds mainframe/copybooks Z72230.EWS.CPY

# data → PS
zowe zos-files upload file-to-data-set mainframe/data/custmast.txt Z72230.EWS.CUSTMAST

# compile, then run the batch and wait for it
zowe zos-jobs submit data-set "Z72230.EWS.JCL(EWSCOMP)" --wfo --rfj
zowe zos-jobs submit data-set "Z72230.EWS.JCL(EWSBATCH)" --js "ASOFDT=20260930,MODE=SCORE" --wfo --rfj

# results
zowe zos-files download data-set Z72230.EWS.FEATCSV -f pipeline/runs/<run>/features.csv
zowe zos-files download data-set Z72230.EWS.RUNCTL  -f pipeline/runs/<run>/runctl.txt
zowe zos-jobs list spool-files-by-jobid <JOBID> --rfj     # per-step RCs for the dashboard
```

`pipeline/zowe.py` calls these with `subprocess`, always adds `--rfj`, parses the JSON, and raises a clear error that includes the job ID and the failing step. Every run saves its job ID, step RCs, RUNCTL counts and downloaded files under `pipeline/runs/<run-id>/` and in SQLite, so the UI can show any past run.

### 7.5 Zowe Explorer (optional)
Not needed to use the software. It's still handy while *developing* COBOL/JCL (syntax checking with Z Open Editor, ad-hoc spool browsing). Everything it shows is also available in the Control Center.

---

## 8. Machine-learning component

| Item | Choice |
|---|---|
| Baseline | Logistic Regression (scaled features, `class_weight="balanced"`), easy to explain in a viva |
| Main model | XGBoost (`scale_pos_weight` for imbalance); fallback to sklearn `HistGradientBoostingClassifier` if XGBoost is a problem |
| Calibration | `CalibratedClassifierCV` (isotonic) so "56%" really means ~56% |
| Metrics | ROC-AUC, PR-AUC, recall and precision of the High tier, Brier score, confusion matrix → `ml/artifacts/metrics.json` (shown in `ModelMetaCard`) |
| Explainability | `shap.TreeExplainer`: per-customer top contributing features, and global mean \|SHAP\| importance |
| Tiers | Low < 30%, Medium 30–60%, High ≥ 60% (defaults; adjust on validation so High tier precision ≥ ~60%) |
| Actions | Low → monitor; Medium → review patterns + pre-due reminder; High → early intervention call / restructuring / payment-holiday review |
| Reasoning text | Template built from the top 3 SHAP factors, e.g. *"High risk mainly because 2 EMIs bounced in the last 6 months and balance fell 38% over 3 months."* This replaces the old LLM text, so it's deterministic and traceable. |

**Synthetic data generator (`ml/generate_data.py`)**: seeded and reproducible. Each customer has a hidden "stress" process (income shock, spending rising, balance draining) that starts **months before** misses occur, so real early-warning signals exist for the model to learn. It also injects about 1–2% bad records (non-numeric amounts, invalid dates, duplicate IDs, orphan loans) so that DFSORT/COBOL validation has something to catch and the reject report isn't empty. A unit test checks that the generated widths match every copybook LRECL.

*Optional extension:* map a public dataset (e.g. Kaggle "Give Me Some Credit") onto `CUSTREC`/`TXNREC` to show the pipeline on non-synthetic distributions.

---

## 9. Serving layer (`ml/api.py`, FastAPI on :8000, SQLite)

| Endpoint | Used by dashboard |
|---|---|
| `GET /customers?tier=&sort=` | `/customers`, `/comparison`, `/emi-forecast` (replaces `CUSTOMERS`) |
| `GET /customers/{id}` | `/customer/[id]` profile, gauge, spend trend (from TXNSUMM months) |
| `GET /customers/{id}/explanation` | `/prediction` SHAP waterfall + `FeatureDetailTable` (same `ShapResult` shape) |
| `GET /customers/{id}/history` | `AlertTimeline` (one prediction per pipeline run) |
| `POST /predict` (what-if) | Home-page EMI simulator: re-score a customer with a changed EMI amount |
| `GET /portfolio/summary` | Tier counts and average risk for the header |
| `GET /mainframe/status` | Connection panel: z/OSMF reachable, user, z/OS version; setup state (libraries allocated? load modules present? data uploaded?) |
| `POST /mainframe/actions` `{action, params}` | Every Control Center button (§7.2). Returns `{runId}` immediately; `409` if a run is already active |
| `GET /runs`, `GET /runs/{id}` | Run history and live status: steps (pending/running/ok/failed), job IDs, step RCs, RUNCTL counts, error text |
| `GET /jobs/{jobId}/spool`, `GET /jobs/{jobId}/spool/{fileId}` | Job output viewer |
| `GET /datasets`, `GET /datasets/{name}/preview` | Data set browser (names restricted to `HLQ.EWS.*`) |
| `GET /reports/{rejects\|exceptions\|riskrpt}?runId=` | Parsed reports as table rows |
| `GET /model` | Current model version, metrics, training as-of dates |

---

## 10. Dashboard changes (`CP/dashboard`)

1. **Remove** the `mongodb` and `@elastic/elasticsearch` dependencies and their `serverComponentsExternalPackages` entry in `next.config.js`.
2. **Add** `src/lib/api.ts` (typed fetch helpers, `API_URL` env). Rewrite `/api/risk`, `/api/risk/trigger`, `/api/alerts`, `/api/trends` as proxies to FastAPI so `useRiskPolling` keeps working.
3. **`CustomerContext`** loads the customer list from the API instead of the `CUSTOMERS` constant. Keep the `Customer` interface and map the API fields onto it.
4. **`/prediction`** uses `/customers/{id}/explanation` instead of `computeShap()`. Delete `lib/shap.ts`'s heuristics but keep its types.
5. **Severity:** go from 4 levels (`low/medium/high/critical`) to the 3 tiers in the spec. Update `getSeverityColor` / `SEVERITY_COLORS` and the badge helpers in `app/page.tsx`.
6. **`AiReasoningCard`** is relabeled "Why this score" and shows the SHAP template text.
7. **New section "Mainframe Control Center" (`/mainframe/*`)**, added to `Nav`:
   - `/mainframe`: **Overview & Connection**. Connection status, setup checklist (libraries ✓, programs compiled ✓, data uploaded ✓, model trained ✓) with the button for the next missing step, and the last run summary.
   - `/mainframe/setup`: **Set up / Recompile**, with the program list and compile RCs; the compile listing opens on errors.
   - `/mainframe/data`: **Generate & upload data** (customer count, seed) and a data set browser with record previews.
   - `/mainframe/runs`: **Batch runs**. As-of date picker + "Run batch" button, live step timeline (upload → EWSBATCH STEP010…STEP090 with RC chips → download → score → write-back), RUNCTL counts, run history.
   - `/mainframe/jobs/[jobId]`: **Job output** spool viewer (monospace, per DD).
   - `/mainframe/model`: **Train model** button, training progress, metrics (AUC, PR-AUC, confusion matrix, feature importance).
   - `/mainframe/reports`: REJECTS / EXCEPT by reason code and the RISKRPT intervention list fetched from the mainframe.
   - Reuses the old `useRiskPolling` pattern as `useRunPolling(runId)` (2 s while active, stops when finished).
8. **First-run experience:** if nothing is set up, the Overview page shows a guided "Get started" wizard (Test connection → Set up mainframe → Generate data → Train model → Run batch). After that, the risk pages fill with data.
9. `ModelMetaCard` shows the real metrics (model version, AUC, training rows, as-of date).

---

## 11. Phased implementation

Each phase ends with something that can be run and checked.

| # | Phase | Deliverables | Done when |
|---|---|---|---|
| 0 | Setup | `CP/` skeleton ✅, dashboard copied ✅, `ml/requirements.txt`, Python venv, `npm install` in dashboard | Dashboard runs on :3000 with its old mock data |
| 1 | Data contract | 7 copybooks, `ml/layouts.py`, `generate_data.py`, width tests | 500-customer files generated; every line has its exact LRECL |
| 2 | Backend core + Zowe actions | `pipeline/zowe.py`, `config.py`, `runner.py`, `actions.py` (Test connection, Set up mainframe, Generate & upload data), FastAPI `/mainframe/*`, `/runs/*` | `curl POST /mainframe/actions setup` allocates the libraries, uploads the sources and compiles: run shows all steps ✓ and 4 load modules in `Z72230.LOAD` |
| 3 | Mainframe batch programs | DFSORT cntl members, `EWSVCUST`, `EWSVLOAN`, `EWSMATCH`, `EWSRECON`, `EWSBATCH` + "Run batch" action | "Run batch" action on 500 customers: all steps RC ≤ 4, RUNCTL `status=OK`, injected bad records show up in REJECTS/EXCEPT, features downloaded |
| 4 | Control Center UI | `/mainframe` pages (§10.7), `useRunPolling`, get-started wizard | From a fresh `Z72230.EWS.*` state, the whole setup → data → run sequence is done **only by clicking in the browser** |
| 5 | Model | "Train model" action: 4 TRAIN runs at 2,000 customers, `train.py`, metrics, SHAP | Started from the UI; validation ROC-AUC ≥ 0.80, LR baseline beaten; metrics on `/mainframe/model` |
| 6 | Scoring + risk API | `score.py` inside "Run batch", SQLite schema, `/customers*`, `/predict` | `GET /customers` returns 2,000 scored customers with tiers, actions and top factors |
| 7 | Risk pages integration | Changes in §10.1–6 | Every page shows API data; no mock imports remain (`grep CUSTOMERS` is empty) |
| 8 | Write-back | `SCOREREC`, `EWSRPT`, `EWSRPTJ` as the last steps of "Run batch" | `/mainframe/reports` shows the RISKRPT fetched from the mainframe, High-tier customers sorted by risk |
| 9 | Hardening + demo | README, `make dev`, offline mode (UI banner + last successful run's data if Z Xplore is down), tests, screenshots | A clean clone: `make dev` → browser → wizard → full demo in under 10 minutes, no terminal steps |

**Critical path:** 1 → 2 → 3 → 5. The UI (4) and risk pages (7) can be built in parallel against a locally generated `features.csv` and fake run data.

---

## 12. Testing

| Level | What |
|---|---|
| Unit (Python) | Layout widths = LRECL; generator determinism; feature CSV parsing; tier/action mapping; SHAP output shape |
| Mainframe | Golden test: a tiny hand-written 10-customer input with known expected features. Compare the downloaded `FEATCSV` to `expected_features.csv` (exact match on counts, ±0.01 on ratios) |
| Validation logic | One injected bad record per reason code → each appears exactly once in REJECTS |
| Reconciliation | Delete a record mid-run (simulate) → `EWSRECON` returns RC 8, and the run stops before scoring and the UI shows the out-of-balance counts |
| ML | No leakage (all feature dates ≤ as-of; label window > as-of); time-based split; calibration plot |
| API | FastAPI `TestClient` for each endpoint |
| End-to-end | Browser-driven: wizard from an empty `EWS.*` state at 500 customers, then each page loads with data |

---

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Z Xplore storage quota / account limits | Small data sets, work files deleted each run, 500-customer dev mode |
| Z Xplore unavailable during the demo | Offline mode: UI banner + data from the last successful run; keep spool screenshots |
| ASCII/EBCDIC or numeric format surprises | Display numerics only across the boundary; golden-file test; text mode, never `--binary` |
| Site `IGYWCL` proc differs from the standard (step names, SYSLIB) | Check the expanded JCL in the `COBOL1J` spool in Phase 2; fall back to explicit compile/link steps against `IGY.V6R5M0.SIGYCOMP` |
| JCL symbols not reaching the PARM | `// SET ASOFDT=…` defaults in the JCL; verify by echoing `&ASOFDT` in a step's SYSOUT |
| Label leakage, so the model looks too good | As-of windows enforced in COBOL; time split; golden test asserts dates |
| Class imbalance (~10–15% stressed) | PR-AUC as the main metric, `scale_pos_weight`, threshold tuning |
| Credentials leaking | Only the Zowe secure store; `.env` git-ignored; no passwords in scripts or the browser |
| The web API can act on the mainframe | Localhost-only binding, whitelisted actions with validated parameters, data set names built server-side, confirmation dialog for deletes |
| Long batch runs vs. browser | Runs execute in the backend, not the request; closing the tab doesn't stop a run, and reopening shows its live state |

---

## 14. Demo flow (for review/viva)

Everything happens in the browser:

1. `/mainframe`: connection is green (z/OS 3.1, user Z72230), setup checklist complete.
2. `/mainframe/data`: browse `Z72230.EWS.*`, preview a few CUSTMAST and REPAYHST records (fixed-width, as stored on z/OS).
3. `/mainframe/runs`: pick as-of 2026-09-30 → **Run batch**. Watch the timeline: upload → JOB submitted → DFSORT → COBOL validate → COBOL match → DFSORT CSV → REXX reconcile → download → score → write-back.
4. Click a step → spool output (e.g. EWSMATCH counts, REXX RUNCTL line). Open `/mainframe/reports` → rejected records with reason codes.
5. `/customers` sorted by risk → a High-tier customer → `/prediction` SHAP waterfall ("why").
6. `/mainframe/reports` → **RISKRPT**, the intervention list written back to and produced on the mainframe.

---

## 15. Next step

Start with **Phase 1 (data contract)**, then **Phase 2 (backend + Zowe actions)**. The copybooks fix every downstream format (COBOL, DFSORT positions, the generator, CSV parsing), and the action runner is what lets every later piece be triggered from the UI.

**Only one-time manual prerequisite** (already done on this machine): Zowe CLI installed and the `zosmf` profile with credentials in the secure store. After that, `make dev` and the browser are all that's needed.
