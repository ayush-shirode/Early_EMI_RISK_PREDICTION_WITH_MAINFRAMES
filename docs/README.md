# Documentation: Early Warning Credit Risk & EMI Stress Prediction (z/OS + ML)

This folder documents what was built in `CP/`, how its parts connect, and how to run and extend it.

| Document | What it answers |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | What the components are, how data flows end to end, and why it is built this way |
| [MAINFRAME_CONNECTION.md](MAINFRAME_CONNECTION.md) | **How the software connects to the mainframe**: Zowe CLI, z/OSMF, authentication, every call that is made |
| [MAINFRAME_DATASETS.md](MAINFRAME_DATASETS.md) | **What kind of "database" is used on z/OS**: data set organisations, every data set, record layouts byte by byte, encoding |
| [BATCH_JOBS.md](BATCH_JOBS.md) | The JCL jobs and every step: DFSORT/ICETOOL, the four COBOL programs, the REXX exec, return codes, reason codes |
| [ML_MODEL.md](ML_MODEL.md) | Features, labels, training, evaluation, SHAP explanations and scoring |
| [BACKEND_AND_DATABASE.md](BACKEND_AND_DATABASE.md) | The FastAPI backend, the action runner, the local SQLite database and the full API reference |
| [FRONTEND.md](FRONTEND.md) | The Next.js dashboard: pages, what each shows, which API it calls |
| [DEMO.md](DEMO.md) | **Step-by-step demo**: preparation, a timed click-by-click script with talking points, expected results, fallback plan, likely questions |
| [OPERATIONS.md](OPERATIONS.md) | Install, run, test, troubleshooting, security |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | The original plan, with notes on where the implementation differs |

## In one paragraph

Customer, loan, repayment and account data live on **IBM z/OS** (IBM Z Xplore) as **sequential data sets** in fixed-width EBCDIC records described by **COBOL copybooks**. A **JCL batch job** sorts and checks them with **DFSORT/ICETOOL**, validates them with **COBOL**, matches all four files and computes 26 early-warning features with a **COBOL balanced-line match**, converts the result to CSV with **DFSORT**, and reconciles every record count with **REXX**. A **Python** backend drives all of this through **Zowe CLI** (which calls the **z/OSMF REST API**), downloads the features, scores every customer with an **XGBoost** model, explains each score with **SHAP**, writes the scores **back to the mainframe**, and runs a second COBOL job that prints the **early intervention list** on z/OS. A **Next.js** dashboard is the only user interface: every mainframe step is a button there.

## Quick start

```bash
cd ~/mainframes/CP
make install      # once: Python venv + dashboard packages
make dev          # backend on 127.0.0.1:8000, dashboard on http://localhost:3000
```

Open http://localhost:3000/mainframe and follow the five-step checklist (connect, set up, generate data, train, run batch). The only prerequisite outside the browser is a working Zowe CLI profile with credentials in the secure store (already true on this machine).

## Verified results (2026-10-25, user Z72230 on IBM Z Xplore, z/OS 3.1)

| Check | Result |
|---|---|
| Compile of all 4 COBOL programs (Enterprise COBOL 6.5) | CC 0000 |
| EWSBATCH on 1,500 customers / 77,243 records | CC 0004 (expected: deliberately bad records rejected), all 7 REXX balancing checks OK |
| Mainframe features vs Python reference rules | identical on all 28 fields for every customer (`tests/test_mainframe_golden.py`) |
| Model on held-out snapshot (2026-06-30) | ROC-AUC 0.825, PR-AUC 0.537, High-tier precision 74% (base rate 10.6%) |
| Full scoring run from the browser | ~70 s: batch, download, score 1,023 customers, write back, COBOL report |
| Automated tests | 31 passed |
