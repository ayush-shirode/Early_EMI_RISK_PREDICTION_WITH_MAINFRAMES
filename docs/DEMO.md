# Demo guide

A step-by-step script for presenting the project (about 12 minutes, plus questions). Each step says **what to click**, **what to point at**, and **what to say**. Everything happens in the browser.

## 1. Before the demo

### The day before
1. Check that Z Xplore accepts your login: `zowe zosmf check status` → "user Z72230 successfully connected". If the password expired, renew it on the Z Xplore site and run `zowe config secure`.
2. Start the app: `cd ~/mainframes/CP && make dev`.
3. Open http://localhost:3000/mainframe and make sure all five checklist steps are green. If not, run the missing ones (setup ≈ 1.5 min, data ≈ 1 min, training ≈ 2.5 min).
4. Run **Run batch & score** once, so there is a fresh run with a complete history and report.
5. Run `make test` and expect `31 passed`.

### 15 minutes before
1. `make dev` (if not already running), then open these tabs in this order:
   * http://localhost:3000/mainframe
   * http://localhost:3000/mainframe/runs
   * http://localhost:3000/customers
2. Zoom the browser to 110–125% so the audience can read the tables.
3. Click **Re-check** on the Overview page: the card must say *Connected to S0W1…*.
4. Optional: open VS Code with Zowe Explorer, filter `Z72230.EWS.*`. It shows the same data sets as the app and is a good answer to "is this really on the mainframe?".

### If the mainframe is unreachable during the demo
The risk pages (Dashboard, Customers, AI Analysis, Comparison, EMI Forecast, Reports of the last run, Model) work from the local copy of the last batch run. Show those, and show a finished run's page (Batch runs → latest run) with its job steps and return codes, which are stored locally. Say clearly that the live mainframe is down and you are showing the last run's results.

## 2. Demo script

| # | Time | Where | Do | Say |
|---|---|---|---|---|
| 1 | 0:00 | — | — | "Banks usually notice EMI trouble after a payment is missed. This system predicts stress 90 days ahead, from data that lives on an IBM mainframe, and explains every prediction." |
| 2 | 0:45 | **Mainframe → Overview** | Point at the connection card | "This is a real IBM z/OS 3.1 system (IBM Z Xplore). The app connects through Zowe: the backend calls Zowe CLI, which calls the z/OSMF REST API. The browser never sees my mainframe password; it stays in the Zowe secure store." |
| 3 | 1:30 | Overview checklist | Walk down steps 1–5 | "Everything is a button: allocate the libraries and compile the COBOL, upload the data, train, run the batch. No terminal, no 3270 screen." |
| 4 | 2:15 | **Data sets** | Click `Z72230.EWS.CUSTMAST` | "The data is stored the mainframe way: sequential data sets with fixed-length 100-byte EBCDIC records, described by a COBOL copybook. No SQL database." Then click `Z72230.EWS.JCL` → `EWSBATCH`: "This is the batch job." |
| 5 | 3:00 | **Batch runs** | Pick as-of `2026-09-30`, click **Run batch & score** | "This submits the job to JES on z/OS. Watch the steps come in." |
| 6 | 3:15 | Live run page | Wait for step 1 (~35 s); point at the RC chips | "DFSORT and ICETOOL sort the four files and reject records with bad numbers; COBOL validates customers and loans, and RC 4 means it rejected some bad records, which is expected because I injected them on purpose; EWSMATCH matches all four files in one pass and computes 26 features; DFSORT turns them into CSV; REXX reconciles every record count." |
| 7 | 4:00 | Run page, right column | Point at **REXX reconciliation** | "Seven balancing checks: every input record is either used, rejected with a reason, or a known duplicate. If one fails, the backend refuses to score. That is the audit control a bank would require." |
| 8 | 4:30 | Run page | Let the remaining steps finish (~35 s) | "Now Python downloads the features, scores every customer, and writes the scores back to the mainframe, where a second COBOL job prints the intervention list." |
| 9 | 5:15 | Click **Job output EWSBATCH** | Open `STEP070 SYSOUT`, then `STEP090 SYSTSPRT` | "This is the real JES spool output: EWSMATCH's counts, and the REXX reconciliation report." |
| 10 | 6:00 | **Reports → Rejected records** | Point at the reason-code summary | "Every rejected record has a reason code: C02 age not numeric, L04 EMI zero, S01 non-numeric repayment…" |
| 11 | 6:30 | **Customers** | Click **HIGH** filter | "1,023 customers scored; 44 are high risk. This list comes from the batch we just ran." |
| 12 | 7:00 | Open the top customer → **SHAP analysis** | Point at the waterfall | "Why is this customer at 88%? SHAP splits the prediction into contributions: spending 2.6× their income adds 37 points, credit cards 70% used adds 19, spending rising adds 10. The text and the suggested action are generated from these numbers, not by an LLM, so they are exact and traceable." |
| 13 | 8:30 | **Dashboard** | In *What-if*, lower the EMI (e.g. 13312 → 6000), click **Re-score with model** | "If the bank restructured this loan to a lower EMI, the model re-scores the customer with all other mainframe features unchanged. For this customer it barely moves (88% → 86% with an EMI of ₹6,000), because the real problem is spending, not the EMI size: restructuring alone would not help, which is exactly the kind of insight the explanation is for." |
| 14 | 9:30 | **Mainframe → Reports → Intervention report** | Scroll the report | "This report was printed by COBOL on z/OS from the scores we wrote back, so operations teams can work from the mainframe as usual." |
| 15 | 10:15 | **Model** | Point at the cards and the tier table | "Trained on four quarter-end snapshots, validated on a later one, never on a random split. ROC-AUC 0.825; of the customers marked High, 74% really ran into EMI stress, against a 10.6% base rate. The top drivers are early signals (spending and liquidity), not past defaults." |
| 16 | 11:15 | — | — | "To sum up: the mainframe is the system of record and does all data preparation and auditing; Python adds prediction and explanation; Zowe connects them; and one web app operates everything." |

### Short version (5 minutes)
Steps 2 → 5/6 → 7 → 11 → 12 → 15.

## 3. Expected results

| Where | You should see |
|---|---|
| EWSBATCH steps | STEP005–040 RC 0, STEP050/060/070 RC 4, STEP080/090 RC 0, job `CC 0004` |
| RUNCTL | all `CHK_*` = OK, `STATUS=OK`, `FEATURES=1023` (with the default data) |
| Scoring | about 44 High, 40 Medium, 939 Low |
| EWSRPTJ | `CC 0000`, report with page headings and tier totals |
| Whole run | about 70 seconds |

Numbers change if you regenerate the data with another seed or customer count.

## 4. Questions you are likely to get

| Question | Answer |
|---|---|
| Why use a mainframe at all? | Most core banking data still lives on z/OS, and nightly batch (sort, validate, match, reconcile) is how it is processed. The project shows ML added on top of that, without moving the data preparation off the mainframe. |
| What database is used? | On z/OS, sequential data sets (QSAM) with COBOL copybook layouts; no VSAM or DB2. Locally, SQLite only caches results for the web pages. See [MAINFRAME_DATASETS.md](MAINFRAME_DATASETS.md). |
| How does the app talk to the mainframe? | Zowe CLI → z/OSMF REST API over HTTPS with the user's credentials from the Zowe secure store. See [MAINFRAME_CONNECTION.md](MAINFRAME_CONNECTION.md). |
| How do you know the COBOL is correct? | The same rules are implemented in Python; a test compares the mainframe's output with them for every customer and every field. They match exactly. |
| Is the data real? | No, it is synthetic, because Z Xplore is a shared IBM education system. The generator builds in realistic early-warning patterns (spending rises and balances fall before payments fail) and about 1% bad records. |
| Why not a random train/test split? | Each customer appears in several quarterly snapshots; a random split would leak information. Validation uses the latest snapshot only. |
| Why XGBoost and not an LLM? | It is trained and measured (AUC, precision), gives calibrated probabilities, and SHAP explains it exactly. |
| What happens with bad input data? | DFSORT and COBOL reject it with reason codes; more than 10% rejects (RC 8) stops the job; REXX blocks scoring if any count does not balance. |
| What is "as-of date"? | The date the prediction is made. The COBOL program only uses data up to that date; the label (training only) looks at the 90 days after it. |
| Could this run every night? | Yes: the same action can be triggered on a schedule; on a real system EWSBATCH would be scheduled by the bank's job scheduler. |

## 5. Screens worth capturing for the report

1. Mainframe → Overview with all five steps green.
2. A finished run page with the JCL step chips and the REXX checks.
3. Job output of `STEP090 SYSTSPRT` (REXX reconciliation on z/OS).
4. Data sets list.
5. Customers filtered to High.
6. SHAP analysis of a high-risk customer.
7. Intervention report.
8. Model page.

Use the browser's full-page screenshot, or **Download PDF** on the SHAP analysis page.
