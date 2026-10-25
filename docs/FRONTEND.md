# Frontend (Next.js dashboard)

Code: `dashboard/`. Next.js 14.2 (App Router), React 18, Tailwind CSS, Recharts, lucide-react icons.

## 1. How it reaches the backend

`next.config.js` rewrites `/api/backend/:path*` to `http://127.0.0.1:8000/:path*` (override with `BACKEND_URL`). The browser therefore only ever talks to the Next.js origin; there is no CORS setup and the backend is never exposed beyond localhost.

* `src/lib/api.ts`: typed `api.get/post`, `startAction()`, formatting helpers, the as-of date options.
* `src/lib/types.ts`: the shapes returned by the backend (`Customer`, `Run`, `Explanation`, `MainframeStatus`, `ModelMetrics`, …).
* `src/context/CustomerContext.tsx`: loads `GET /customers` once and shares the list and the selected customer with every page; `reload()` is called after a scoring run.
* `src/hooks/useRun.ts`: polls `GET /runs/{id}` every 2 s until the run finishes.
* `src/hooks/useRiskPolling.ts`: a customer's prediction history and the what-if call.

### Layout and consistency

* Every page is wrapped in `components/PageShell.tsx`: the global header, a centred `max-w-7xl` content column with the same padding, and a standard title / subtitle / actions row. `Loading` gives the same loading line everywhere.
* The header has two rows: brand on the left with the customer profile selector and the mainframe status on the right, then the navigation, which scrolls sideways on narrow screens instead of wrapping.
* Panels use the shared `glass-panel` style (also on the SHAP page, whose CSS module now uses the same colours as the rest of the app). Panels size to their content; none use `h-full`, which made the prediction-history and suggestion panels overflow their column.
* Wide tables sit in `overflow-x-auto` containers with `whitespace-nowrap`, so they scroll instead of squeezing on tablets.
* Money is formatted with `inr()` (₹, Indian grouping, no decimals), risk as a percentage, due days with `ordinal()` (1st, 2nd, 3rd…).
* Colours: High orange, Medium yellow, Low green; in SHAP views red raises risk and green lowers it.

## 2. Pages

### Mainframe Control Center (new)

| Route | Shows | Calls |
|---|---|---|
| `/mainframe` | connection card (user, system, z/OSMF, HLQ); the **5-step setup checklist**, each with its button and live state (libraries and load modules present, data uploaded, model trained, last run); reset | `/mainframe/status`, `POST /actions/*` |
| `/mainframe/runs` | "Run batch & score" with an as-of picker, "Train model", run history (auto-refresh) | `/runs`, `POST /actions/run_batch` |
| `/mainframe/runs/[id]` | live step timeline: per-step status, duration, detail, **JCL step return-code chips** (green 0, yellow 4, red ≥ 8, grey skipped), link to job output; REXX reconciliation checks; scoring or training summary | `/runs/{id}` |
| `/mainframe/jobs/[jobid]` | JES spool viewer: job card, spool files by step/DD (JESMSGLG, JESJCL, JESYSMSG, SYSOUT, TOOLMSG, SYSTSPRT …), file content | `/jobs/{id}/spool[/{file}]` |
| `/mainframe/datasets` | all `Z72230.EWS.*` data sets with organisation, RECFM, LRECL, usage and purpose; click to preview records or PDS members | `/datasets`, `/datasets/{dsn}/preview` |
| `/mainframe/reports` | tabs: the COBOL **intervention report** (RISKRPT), **rejected records** by reason code, **matching exceptions**, **reconciliation** (RUNCTL) | `/reports/*` |
| `/mainframe/model` | model version, data window, ROC-AUC / PR-AUC / precision / recall cards, tier table, confusion matrix, LR baseline comparison, global SHAP importance; Retrain | `/model` |

Every button goes through `ActionButton`, which posts the action and navigates to its live run page; buttons are disabled while another run is active. The header shows the mainframe connection (`z/OS Z72230`), an active run, or `MAINFRAME OFFLINE`, refreshed every 30 s.

### Risk views (reused from the earlier project, now on real data)

| Route | Shows |
|---|---|
| `/` | selected customer: risk gauge, **what-if EMI re-scoring**, "why this score", balance/tier/EMI cards, 6-month spend vs EMI chart, prediction history |
| `/customers` | all scored customers: search, tier filter, sorting, paging (50 per page), portfolio summary cards |
| `/customer/[id]` | profile (from CUSTMAST), every loan (LOANMAST), credit ring, risk, balance vs EMI, suggestions, **24-month account history chart** (TXNSUMM), printable report |
| `/prediction?customerId=` | SHAP waterfall (red = raises risk, green = lowers), feature table, model metadata incl. validation AUC, reasoning card, change vs previous run, history; print to PDF |
| `/comparison` | up to 6 customers (default: 3 riskiest, the selected one, 2 safest): spend trajectories, spend/EMI table, risk ranking |
| `/emi-forecast` | Medium/High customers with their next EMI dates, stress probability and balance vs EMI |

When no batch has been scored yet, these pages show a prompt that links to the Control Center.

## 3. Changes from the copied dashboard

* Removed: hard-coded `CUSTOMERS`, the heuristic `computeShap()`, MongoDB/Elasticsearch API routes and packages, the Dockerfile (the app runs locally next to the backend).
* Severity is the spec's 3 tiers (`low/medium/high`); "critical" is gone.
* Email/phone are not part of the customer master on the mainframe, so the profile shows customer ID, age and employment instead.
* Next.js upgraded from 14.1.0 to 14.2.35 (security fix).

## 4. Commands

```bash
cd dashboard
npm install
npx next dev -p 3000          # development (or `make dev` from CP/ for backend + frontend)
npx tsc --noEmit              # type check
npx next build && npx next start -p 3000   # production build
```
