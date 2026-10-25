# Early Warning Credit Risk & EMI Stress Prediction — IBM z/OS + Machine Learning

Predicts which borrowers are likely to run into EMI repayment stress in the next 90 days, **before** a payment is missed, and explains why.

* **Mainframe (IBM z/OS via Zowe):** the data lives in z/OS data sets. A JCL batch job sorts and checks it with DFSORT/ICETOOL, validates it with COBOL, matches all files and computes the early-warning features with COBOL, converts them to CSV with DFSORT, and reconciles every record count with REXX. Scores are written back and a COBOL job prints the early intervention list.
* **ML (Python):** XGBoost classifier, time-based evaluation, SHAP explanation for every customer.
* **Dashboard (Next.js):** the only interface. Every mainframe step (setup, upload, compile, batch, job output, reports, training) is a button; the risk pages show the scored customers.

```
make install     # once
make dev         # then open http://localhost:3000/mainframe
```

| Folder | Content |
|---|---|
| `mainframe/` | COBOL programs, copybooks, JCL, DFSORT/ICETOOL statements, REXX: everything that runs on z/OS |
| `pipeline/` | Zowe CLI wrapper, the Control Center actions, background runner, SQLite |
| `ml/` | record layouts, data generator, reference rules, training, scoring |
| `api/` | FastAPI backend |
| `dashboard/` | Next.js frontend |
| `tests/` | layout, rules, API and mainframe golden tests |
| `docs/` | **full documentation, start at [docs/README.md](docs/README.md)** |
