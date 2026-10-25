"""FastAPI backend for the dashboard.

Two groups of endpoints:
  * Mainframe Control Center: start whitelisted actions, follow runs, read job output,
    browse project data sets and reports. All mainframe access goes through Zowe CLI.
  * Risk views: scored customers, SHAP explanations, history and what-if re-scoring,
    served from the local SQLite copy of the last batch run.

Run:  uvicorn api.main:app --host 127.0.0.1 --port 8000
It binds to localhost only, because it acts with the user's mainframe credentials.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from ml import features_meta as meta
from ml import score
from pipeline import actions, db, runner, zowe
from pipeline.config import RUNS_DIR, TIER_HIGH, TIER_MEDIUM



@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    yield


app = FastAPI(title="EWS backend", version="1.0", lifespan=lifespan)

LOAN_TYPES = {"H": "home", "C": "car", "P": "personal", "E": "education"}
EMP_TYPES = {"S": "salaried", "E": "self-employed", "B": "business"}
JOBID = re.compile(r"^(JOB|J|STC|TSU)\d{1,7}$")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "active_run": runner.active_run_id()}


# ============================================================ Control Center
_status_cache: dict = {"at": 0.0, "value": None}


@app.get("/mainframe/status")
def mainframe_status(refresh: bool = False) -> dict:
    """Connection + setup checklist. Mainframe part is cached for 60 s (several Zowe calls)."""
    if refresh or _status_cache["value"] is None or time.time() - _status_cache["at"] > 60:
        try:
            live = {"ok": True, **actions.mainframe_status()}
        except Exception as e:  # unreachable system, expired password, ...
            live = {"ok": False, "error": str(e)}
        _status_cache.update(at=time.time(), value=live)
    m = score.metrics()
    last_run = db.kv_get("last_score_run")
    return {
        "mainframe": _status_cache["value"],
        "checked_at": _status_cache["at"],
        "data": db.kv_get("data"),
        "model": None if not m else {k: m[k] for k in ("model_version", "trained_at", "rows")}
        | {"roc_auc": m["validation"]["xgboost"]["roc_auc"]},
        "last_score_run": runner.get_run(last_run) if last_run else None,
        "active_run": runner.active_run_id(),
    }


@app.get("/actions")
def list_actions() -> list[dict]:
    return [{"name": k, "label": v["label"]} for k, v in actions.ACTIONS.items()]


def _validate(name: str, params: dict) -> dict:
    """Whitelist and coerce parameters per action; anything else is rejected."""
    allowed = {"generate_data": {"customers", "seed"}, "run_batch": {"asof"}, "reset_data": {"confirm"}}
    extra = set(params) - allowed.get(name, set())
    if extra:
        raise HTTPException(400, f"Unexpected parameters: {', '.join(sorted(extra))}")
    out = dict(params)
    try:
        if name == "generate_data":
            out["customers"] = int(params.get("customers", 1500))
            out["seed"] = int(params.get("seed", 42))
            if not 200 <= out["customers"] <= 3000 or not 1 <= out["seed"] <= 999999:
                raise ValueError
        if name == "run_batch" and "asof" in params:
            out["asof"] = actions.validate_asof(params["asof"])
        if name == "reset_data" and params.get("confirm") is not True:
            raise HTTPException(400, "Reset needs confirm: true")
    except (ValueError, TypeError, runner.ActionError) as e:
        raise HTTPException(400, str(e) or "Invalid parameters")
    return out


@app.post("/actions/{name}")
def start_action(name: str, params: dict = Body(default={})) -> dict:
    if name not in actions.ACTIONS:
        raise HTTPException(404, f"Unknown action {name}")
    clean = _validate(name, params or {})
    try:
        run_id = runner.start(name, actions.ACTIONS[name]["fn"], clean)
    except runner.Busy as e:
        raise HTTPException(409, str(e))
    _status_cache["at"] = 0  # refresh the checklist after the run
    return {"runId": run_id}


@app.get("/runs")
def runs(limit: int = 30, action: str | None = None) -> list[dict]:
    return runner.list_runs(min(limit, 200), action)


@app.get("/runs/{run_id}")
def run(run_id: int) -> dict:
    r = runner.get_run(run_id)
    if not r:
        raise HTTPException(404, "No such run")
    return r


@app.get("/jobs/{jobid}/spool")
def job_spool(jobid: str) -> dict:
    if not JOBID.match(jobid):
        raise HTTPException(400, "Invalid job ID")
    try:
        files = zowe.spool_files(jobid)
        status = zowe.job_status(jobid)
    except zowe.ZoweError as e:
        raise HTTPException(502, str(e))
    return {
        "job": {k: status.get(k) for k in ("jobname", "jobid", "owner", "status", "retcode", "class")},
        "files": [{k: f.get(k) for k in ("id", "ddname", "stepname", "procstep", "record-count")} for f in files],
    }


@app.get("/jobs/{jobid}/spool/{file_id}", response_class=PlainTextResponse)
def job_spool_file(jobid: str, file_id: int) -> str:
    if not JOBID.match(jobid):
        raise HTTPException(400, "Invalid job ID")
    try:
        return zowe.spool_content(jobid, file_id)
    except zowe.ZoweError as e:
        raise HTTPException(502, str(e))


@app.get("/datasets")
def datasets() -> list[dict]:
    try:
        n = actions.names()
        items = zowe.list_datasets(f"{n.hlq}.EWS.**")
    except zowe.ZoweError as e:
        raise HTTPException(502, str(e))
    keys = ("dsname", "dsorg", "recfm", "lrecl", "blksz", "used", "sizex", "spacu", "cdate", "rdate", "vol")
    return [{k: d.get(k) for k in keys} for d in items]


@app.get("/datasets/{dsn}/preview")
def dataset_preview(dsn: str, records: int = 50) -> dict:
    n = actions.names()
    dsn = dsn.upper()
    member = re.fullmatch(r"([A-Z0-9#@$.]+)\(([A-Z0-9#@$]{1,8})\)", dsn)
    base = member.group(1) if member else dsn
    if not re.fullmatch(r"[A-Z0-9#@$.]+", base) or not n.is_project_dataset(base):
        raise HTTPException(403, "Only the project's EWS data sets can be browsed")
    try:
        if not member and next((d for d in zowe.list_datasets(dsn) if d["dsname"] == dsn), {}).get("dsorg", "").startswith("PO"):
            return {"dsname": dsn, "members": zowe.list_members(dsn)}
        text = zowe.view(dsn, max_records=min(max(records, 1), 500))
    except zowe.ZoweError as e:
        raise HTTPException(502, str(e))
    return {"dsname": dsn, "lines": text.splitlines()}


def _run_dir(run_id: int | None) -> tuple[int, Path]:
    rid = run_id or db.kv_get("last_score_run")
    if not rid:
        raise HTTPException(404, "No batch run yet")
    return rid, RUNS_DIR / str(rid)


@app.get("/reports/{kind}")
def report(kind: str, runId: int | None = None) -> dict:
    rid, d = _run_dir(runId)
    if kind in ("rejects", "exceptions"):
        p = next(d.glob(f"*/{'rejects' if kind == 'rejects' else 'exceptions'}.txt"), None)
        rows = actions.parse_rejects(p.read_text()) if p else []
        counts: dict = {}
        for r in rows:
            key = (r["reason_code"], r["reason_text"], r["source"])
            counts[key] = counts.get(key, 0) + 1
        summary = [{"code": c, "text": t, "source": s, "count": n} for (c, t, s), n in sorted(counts.items())]
        return {"runId": rid, "total": len(rows), "summary": summary, "rows": rows[:500]}
    if kind == "runctl":
        p = next(d.glob("*/runctl.txt"), None)
        return {"runId": rid, "values": actions.parse_runctl(p.read_text()) if p else {}}
    if kind == "riskrpt":
        p = d / "riskrpt.txt"
        if not p.exists():
            raise HTTPException(404, "No report in this run")
        lines = p.read_text().splitlines()
        rows = []
        for ln in lines:
            m = re.match(r"^ \s*(\d+)\s+(\S{8})\s+([\d.]+)\s+(HIGH|MEDIUM|LOW)\s+(\S+)\s+([\d,.]+)\s+(.*)$", ln)
            if m:
                rows.append({"rank": int(m.group(1)), "cust_id": m.group(2), "risk_pct": float(m.group(3)),
                             "tier": m.group(4), "action": m.group(5),
                             "total_emi": float(m.group(6).replace(",", "")), "top_factor": m.group(7).strip()})
        return {"runId": rid, "lines": lines, "rows": rows}
    raise HTTPException(404, "Unknown report")


@app.get("/model")
def model() -> dict:
    m = score.metrics()
    if not m:
        raise HTTPException(404, "No trained model yet")
    return m


# ============================================================ risk views
def _latest_run() -> int | None:
    rid = db.kv_get("last_score_run")
    if rid:
        return rid
    rows = db.query("SELECT MAX(run_id) AS r FROM predictions")
    return rows[0]["r"] if rows else None


def _ym_label(ym: int) -> str:
    return date(ym // 100, ym % 100, 1).strftime("%b %y")


def _suggestions(shap_detail: dict, action: str) -> list[str]:
    out = [action]
    for f in shap_detail["features"]:
        if f["shap"] > 0.005 and f["key"] in meta.SUGGESTIONS and meta.SUGGESTIONS[f["key"]] not in out:
            out.append(meta.SUGGESTIONS[f["key"]])
        if len(out) == 3:
            break
    return out


def _customer_rows(cust_ids: list[str] | None = None) -> list[dict]:
    rid = _latest_run()
    if not rid:
        return []
    sql = ("SELECT p.*, c.name, c.city, c.emp_type, c.age, c.monthly_income, c.credit_score "
           "FROM predictions p JOIN customers c ON c.cust_id = p.cust_id WHERE p.run_id = ?")
    args: list = [rid]
    if cust_ids:
        sql += f" AND p.cust_id IN ({','.join('?' * len(cust_ids))})"
        args += cust_ids
    preds = db.query(sql, tuple(args))
    if not preds:
        return []
    ids = [p["cust_id"] for p in preds]
    asof = preds[0]["as_of"]
    asof_ym = asof // 100
    marks = ",".join("?" * len(ids))
    loans: dict[str, list] = {}
    for l in db.query(f"SELECT * FROM loans WHERE cust_id IN ({marks})", tuple(ids)):
        loans.setdefault(l["cust_id"], []).append(l)
    months: dict[str, list] = {}
    for m in db.query(f"SELECT cust_id, yyyymm, debits FROM monthly WHERE cust_id IN ({marks}) AND yyyymm <= ? "
                      "ORDER BY yyyymm", (*ids, asof_ym)):
        months.setdefault(m["cust_id"], []).append(m)

    out = []
    for p in preds:
        f = json.loads(p["features"])
        sh = json.loads(p["shap"])
        active = []
        for l in loans.get(p["cust_id"], []):
            sd = l["start_date"]
            elapsed = (asof // 10000 - sd // 10000) * 12 + (asof // 100 % 100 - sd // 100 % 100)
            if sd <= asof and elapsed < l["tenure"]:
                active.append({**l, "remaining": l["tenure"] - elapsed})
        primary = max(active, key=lambda l: l["emi_amt"]) if active else None
        trend = [{"month": _ym_label(m["yyyymm"]), "amount": round(m["debits"])}
                 for m in months.get(p["cust_id"], [])[-6:]]
        prob = p["probability"]
        sd = str(primary["start_date"]) if primary else ""
        out.append({
            "id": p["cust_id"], "name": p["name"], "city": p["city"],
            "accountType": EMP_TYPES.get(p["emp_type"], p["emp_type"]), "age": p["age"],
            "monthlyIncome": p["monthly_income"], "creditScore": p["credit_score"],
            "emiAmount": round(float(f["total_emi"]), 2),
            "emiDueDate": str(primary["due_day"]) if primary else "1",
            "loanType": LOAN_TYPES.get(primary["loan_type"], "personal") if primary else "personal",
            "loanTenureMonths": primary["tenure"] if primary else 0,
            "loanStartDate": f"{sd[:4]}-{sd[4:6]}-{sd[6:]}" if sd else "",
            "monthsRemaining": primary["remaining"] if primary else 0,
            "activeLoans": len(active),
            "riskScore": round(prob * 100), "missProbability": round(prob, 4),
            "severity": p["tier"].lower(), "tier": p["tier"],
            "assessedSavings": round(float(f["avg_balance_3m"])),
            "spendTrend": trend,
            "suggestions": _suggestions(sh, p["action"]),
            "reasoning": p["reasoning"], "topFactor": p["top_factor"], "action": p["action"],
            "asOf": asof, "lastPredictionAt": p["created_at"], "modelVersion": p["model_version"],
            "runId": p["run_id"],
        })
    out.sort(key=lambda c: -c["missProbability"])
    return out


@app.get("/customers")
def customers() -> list[dict]:
    return _customer_rows()


@app.get("/portfolio")
def portfolio() -> dict:
    rows = _customer_rows()
    if not rows:
        return {"customers": 0}
    tiers = {t: [r for r in rows if r["tier"] == t] for t in ("High", "Medium", "Low")}
    return {
        "customers": len(rows), "asOf": rows[0]["asOf"], "runId": rows[0]["runId"],
        "avgRisk": round(sum(r["riskScore"] for r in rows) / len(rows), 1),
        "tiers": {t: {"count": len(v), "emiAtRisk": round(sum(r["emiAmount"] for r in v))} for t, v in tiers.items()},
        "thresholds": {"medium": TIER_MEDIUM, "high": TIER_HIGH},
    }


def _one(cust_id: str) -> dict:
    rows = _customer_rows([cust_id.upper()])
    if not rows:
        raise HTTPException(404, "Customer not scored in the latest run")
    return rows[0]


@app.get("/customers/{cust_id}")
def customer(cust_id: str) -> dict:
    c = _one(cust_id)
    c["loans"] = db.query("SELECT * FROM loans WHERE cust_id=? ORDER BY start_date", (c["id"],))
    c["monthly"] = db.query("SELECT * FROM monthly WHERE cust_id=? ORDER BY yyyymm", (c["id"],))
    return c


@app.get("/customers/{cust_id}/explanation")
def explanation(cust_id: str, top: int = 10) -> dict:
    rid = _latest_run()
    rows = db.query("SELECT * FROM predictions WHERE run_id=? AND cust_id=?", (rid, cust_id.upper()))
    if not rows:
        raise HTTPException(404, "Customer not scored in the latest run")
    p = rows[0]
    sh = json.loads(p["shap"])
    feats = sh["features"][:top]
    rest = sum(f["shap"] for f in sh["features"][top:])
    return {
        "custId": p["cust_id"], "asOf": p["as_of"], "probability": p["probability"], "tier": p["tier"],
        "base": sh["base"], "features": feats, "otherFeaturesShap": rest,
        "featureCount": len(sh["features"]), "reasoning": p["reasoning"], "action": p["action"],
        "modelVersion": p["model_version"], "computedAt": p["created_at"],
        "features_raw": json.loads(p["features"]),
    }


@app.get("/customers/{cust_id}/history")
def history(cust_id: str) -> list[dict]:
    rows = db.query("SELECT p.id, p.run_id, p.as_of, p.probability, p.tier, p.reasoning, p.model_version, "
                    "p.created_at, p.features FROM predictions p WHERE p.cust_id=? ORDER BY p.id DESC LIMIT 20",
                    (cust_id.upper(),))
    for r in rows:
        f = json.loads(r.pop("features"))
        r["total_emi"] = float(f["total_emi"])
    return rows


@app.post("/customers/{cust_id}/what-if")
def what_if(cust_id: str, body: dict = Body(...)) -> dict:
    try:
        emi = float(body.get("emiAmount"))
    except (TypeError, ValueError):
        raise HTTPException(400, "emiAmount must be a number")
    if not 0 < emi <= 500000:
        raise HTTPException(400, "emiAmount must be between 1 and 5,00,000")
    rid = _latest_run()
    rows = db.query("SELECT features FROM predictions WHERE run_id=? AND cust_id=?", (rid, cust_id.upper()))
    if not rows:
        raise HTTPException(404, "Customer not scored in the latest run")
    r = score.what_if(json.loads(rows[0]["features"]), {"total_emi": emi})
    return {**r, "emiAmount": emi, "riskScore": round(r["probability"] * 100)}
