# Early Warning Credit Risk & EMI Stress Prediction — IBM z/OS + Machine Learning

Predicts which borrowers are likely to run into EMI repayment stress in the next 90 days, **before** a payment is missed, and explains why.

* **Mainframe (IBM z/OS via z/OSMF and SSH):** the data lives in z/OS data sets. A JCL batch job sorts and checks it with DFSORT/ICETOOL, validates it with COBOL, matches all files and computes the early-warning features with COBOL, converts them to CSV with DFSORT, and reconciles every record count with REXX. Scores are written back and a COBOL job prints the early intervention list.
* **ML (Python):** XGBoost classifier, time-based evaluation, SHAP explanation for every customer.
* **Dashboard (Next.js):** for bank staff. Every mainframe step (setup, upload, compile, batch, job output, reports, training) is a button; the risk pages show the scored customers.
* **Operator console (terminal):** for the mainframe operator. ISPF/SDSF-style panels to monitor both connections, browse/upload/download data sets, follow jobs and the batch pipeline, read the operator log and run USS, TSO and console commands.

```
make install     # once
make login       # once: z/OS host, user ID, password (password -> OS keyring)
make login-ssh   # once: trust the SSH host key, install the EWS agent on USS
make dev         # then open http://localhost:3000/mainframe
make tui         # operator console in the terminal
```

| Folder | Content |
|---|---|
| `mainframe/` | COBOL programs, copybooks, JCL, DFSORT/ICETOOL statements, REXX: everything that runs on z/OS |
| `pipeline/` | our z/OSMF REST client and SSH channel, the Control Center actions, background runner, SQLite |
| `tui/` | the operator console: a 3270-style terminal UI for the mainframe side |
| `ml/` | record layouts, data generator, reference rules, training, scoring |
| `api/` | FastAPI backend |
| `dashboard/` | Next.js frontend |
| `tests/` | layout, rules, API and mainframe golden tests |
| `docs/` | **full documentation, start at [docs/README.md](docs/README.md)** |
