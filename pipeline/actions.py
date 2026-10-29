"""The actions behind the Mainframe Control Center buttons.

Every action is a list of named steps; every mainframe operation in a step is a call
to our z/OSMF REST client (pipeline/zos.py). The browser can only start these actions, with validated
parameters; it can never send a command or a data set name of its own.
"""
from __future__ import annotations

import csv
import io
import json
import re
import time
from datetime import date
from pathlib import Path

from ml.layouts import CUSTREC, LOANREC, REJREC, SCOREREC, SCOREVS, TXNREC
from pipeline import db, zos, zosconf
from pipeline.config import HLQ_ENV, INPUT_DIR, MAINFRAME_SRC, SCORE_ASOF, TRAIN_ASOFS, Names
from pipeline.runner import ActionError, RunContext

PROGRAMS = ["EWSVCUST", "EWSVLOAN", "EWSMATCH", "EWSRPT", "EWSSUPD"]


def hlq() -> str:
    if HLQ_ENV:
        return HLQ_ENV
    try:
        return zosconf.load().user
    except zosconf.NotConfigured as e:
        raise ActionError(str(e)) from e


def names() -> Names:
    return Names(hlq())


# ===================================================================== helpers
def submit_job(step, member: str, symbols: dict | None = None, max_rc: int = 4) -> dict:
    """Submit JCL member from EWS.JCL, wait, collect per-step RCs, fail on a bad step."""
    n = names()
    step.detail(f"Submitting {n.JCL}({member})" + (f" with {symbols}" if symbols else ""))
    job = zos.submit(f"{n.JCL}({member})", symbols)
    jobid = job["jobid"]
    step.data(jobid=jobid, jobname=job.get("jobname"), retcode=job.get("retcode"))
    steps = zos.step_results(jobid)
    step.data(steps=steps)
    bad = [s for s in steps if s["status"] == "abended" or (s["rc"] is not None and s["rc"] > max_rc)]
    skipped = [s for s in steps if s["status"] == "not executed"]
    retcode = job.get("retcode") or ""
    if bad or skipped or "JCL ERROR" in retcode or "ABEND" in retcode:
        where = bad[0] if bad else (skipped[0] if skipped else None)
        what = (f"step {where['step']} {where.get('procstep') or ''} "
                f"{'abended ' + where['abend'] if where and where.get('abend') else 'RC=' + str(where['rc'])}"
                if where and where["status"] != "not executed" else
                f"step {where['step']} was not executed" if where else retcode)
        raise ActionError(f"Job {member} ({jobid}) failed: {what}. Open the job output for details.")
    step.detail(f"{member} {jobid} ended {retcode}")
    return {"jobid": jobid, "retcode": retcode, "steps": steps}


def parse_runctl(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            v = v.strip()
            out[k.strip()] = int(v) if v.isdigit() else v
    return out


def parse_rejects(text: str) -> list[dict]:
    return [REJREC.parse(l) for l in text.splitlines() if l.strip()]


_RPT_LINE = re.compile(r"^ \s*(\d+)\s+(\S{8})\s+([\d.]+)\s+(HIGH|MEDIUM|LOW)\s+(\S+)\s+([\d,.]+)\s+(.*)$")


def parse_riskrpt(lines: list[str]) -> list[dict]:
    """Detail lines of the EWSRPT intervention list (RISKRPT).

    The risk factor and the customer name (read by EWSRPT from the VSAM KSDS CUSTKSDS) are
    fixed columns: DT-FACTOR at 60-89 and DT-NAME at 92-121 (1-based, ASA byte included).
    """
    rows = []
    for ln in lines:
        m = _RPT_LINE.match(ln)
        if m:
            rows.append({"rank": int(m.group(1)), "cust_id": m.group(2), "risk_pct": float(m.group(3)),
                         "tier": m.group(4), "action": m.group(5),
                         "total_emi": float(m.group(6).replace(",", "")),
                         "top_factor": ln[59:89].strip(), "name": ln[91:121].strip()})
    return rows


def load_master_data(cust_text: str, loan_text: str, txn_text: str) -> dict:
    custs = [CUSTREC.parse(l) for l in cust_text.splitlines() if l.strip()]
    loans = [LOANREC.parse(l) for l in loan_text.splitlines() if l.strip()]
    txns = [TXNREC.parse(l) for l in txn_text.splitlines() if l.strip()]
    with db.tx() as con:
        con.execute("DELETE FROM customers")
        con.execute("DELETE FROM loans")
        con.execute("DELETE FROM monthly")
        con.executemany("INSERT INTO customers VALUES(?,?,?,?,?,?,?,?,?)", [
            (c["cust_id"], c["cust_name"], c["city"], c["emp_type"], c["age"], c["monthly_income"],
             c["credit_score"], c["open_date"], c["status"]) for c in custs])
        con.executemany("INSERT OR REPLACE INTO loans VALUES(?,?,?,?,?,?,?,?,?,?,?)", [
            (l["loan_id"], l["cust_id"], l["loan_type"], l["principal"], l["int_rate"], l["tenure"],
             l["start_date"], l["emi_amt"], l["due_day"], l["outstanding"], l["status"]) for l in loans])
        con.executemany("INSERT OR REPLACE INTO monthly VALUES(?,?,?,?,?,?,?,?,?)", [
            (t["cust_id"], t["yyyymm"], t["credits"], t["debits"], t["salary"], t["min_bal"],
             t["avg_bal"], t["bounces"], t["cc_util"]) for t in txns])
    return {"customers": len(custs), "loans": len(loans), "monthly": len(txns)}


def run_ewsbatch(ctx: RunContext, step, asof: int, mode: str, tag: str) -> dict:
    """Submit EWSBATCH and download its results into the run folder."""
    n = names()
    job = submit_job(step, "EWSBATCH", {"ASOFDT": asof, "MODE": mode})
    step.detail(f"EWSBATCH {job['jobid']} ended {job['retcode']}. Downloading results...")
    out = ctx.dir / tag
    zos.download(n.RUNCTL, out / "runctl.txt")
    zos.download(n.FEATCSV, out / "features.csv")
    zos.download(n.REJECTS, out / "rejects.txt")
    zos.download(n.EXCEPT, out / "exceptions.txt")
    runctl = parse_runctl((out / "runctl.txt").read_text())
    step.data(runctl=runctl)
    if runctl.get("STATUS") != "OK":
        failed = [k for k, v in runctl.items() if k.startswith("CHK_") and v != "OK"]
        raise ActionError(f"EWSRECON reports the batch is out of balance ({', '.join(failed)})")
    step.detail(f"{job['jobid']} {job['retcode']}: {runctl.get('FEATURES')} feature records, "
                f"{runctl.get('CUST_REJECTED', 0) + runctl.get('LOAN_REJECTED', 0) + runctl.get('REPAY_REJECTED', 0) + runctl.get('TXN_REJECTED', 0)} rejected, "
                f"{runctl.get('MATCH_EXCEPTIONS')} exceptions, reconciliation OK")
    return {"job": job, "runctl": runctl, "dir": out}


def job_displays(jobid: str, stepname: str, program: str) -> dict:
    """Counters a COBOL program DISPLAYed to SYSOUT, e.g. 'EWSSUPD ADDED        000000012'."""
    f = next((f for f in zos.spool_files(jobid) if f.get("stepname") == stepname and f.get("ddname") == "SYSOUT"), None)
    if not f:
        return {}
    text = zos.spool_content(jobid, f["id"])
    return {re.sub(r"[ -]+", "_", k.strip().lower()): int(v)
            for k, v in re.findall(rf"{program} ([A-Z][A-Z -]*?)\s+(\d{{7,9}})\s*$", text, re.M)}


def check_vsam(step, scored: int) -> dict:
    """Catalog check of both KSDS after a scoring run: record counts from LISTCAT."""
    n = names()
    cust = zos.listcat(n.CUSTKSDS).get("data", {})
    score = zos.listcat(n.SCORKSDS).get("data", {})
    out = {"custksds_records": cust.get("rec-total"), "scoreksds_records": score.get("rec-total"),
           "scoreksds_updated": score.get("rec-updated"), "scoreksds_inserted": score.get("rec-inserted"),
           "volume": cust.get("volser")}
    step.data(vsam=out)
    if not out["scoreksds_records"] or out["scoreksds_records"] < scored:
        raise ActionError(f"{n.SCORKSDS} holds {out['scoreksds_records']} records, fewer than the {scored} scored")
    return out


def validate_asof(asof) -> int:
    try:
        s = str(int(asof))
        d = date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except (ValueError, TypeError):
        raise ActionError("As-of date must be YYYYMMDD")
    if not date(2025, 3, 31) <= d <= date(2026, 9, 30):
        raise ActionError("As-of date must be between 2025-03-31 and 2026-09-30 (the data history window)")
    return int(s)


# ===================================================================== actions
def test_connection(ctx: RunContext) -> None:
    ctx.plan(["Connect to z/OSMF"])
    with ctx.step("Connect to z/OSMF") as s:
        info = zos.check_status()
        s.data(**info)
        s.detail(f"Connected as {info['user']} to {info['system']} (z/OSMF {info['zosmf_version']})")
        ctx.summary = info


SOURCE_STEPS = {
    "copybooks": "Upload copybooks",
    "cobol": "Upload COBOL programs",
    "sortcntl": "Upload DFSORT control statements",
    "rexx": "Upload REXX execs",
    "jcl": "Upload JCL",
}


def _upload_sources(ctx: RunContext, kinds: list[str]) -> None:
    for lib in names().libraries():
        if lib["source"] not in kinds:
            continue
        with ctx.step(SOURCE_STEPS[lib["source"]]) as s:
            files = sorted(p for p in (MAINFRAME_SRC / lib["source"]).iterdir()
                           if p.is_file() and not p.name.startswith("."))
            for i, f in enumerate(files, 1):
                member = f.name.split(".")[0].upper()
                s.detail(f"{i}/{len(files)}  {f.name} -> {lib['name']}({member})")
                zos.upload_file(f, f"{lib['name']}({member})")
            s.data(members=[f.name.split(".")[0].upper() for f in files], library=lib["name"])
            s.detail(f"{len(files)} members uploaded to {lib['name']}")


def _compile(ctx: RunContext) -> None:
    n = names()
    with ctx.step("Compile and link (EWSCOMP)") as s:
        submit_job(s, "EWSCOMP", max_rc=4)
    with ctx.step("Verify load modules") as s:
        members = set(zos.list_members(n.LOAD))
        missing = [p for p in PROGRAMS if p not in members]
        if missing:
            raise ActionError(f"Load modules missing in {n.LOAD}: {', '.join(missing)}")
        s.detail(f"{', '.join(PROGRAMS)} present in {n.LOAD}")
    db.kv_set("compiled", True)


def setup(ctx: RunContext) -> None:
    ctx.plan(["Connect to z/OSMF", "Allocate libraries", *SOURCE_STEPS.values(),
              "Compile and link (EWSCOMP)", "Verify load modules"])
    with ctx.step("Connect to z/OSMF") as s:
        info = zos.check_status()
        s.detail(f"Connected as {info['user']} to {info['system']}")
    n = names()
    with ctx.step("Allocate libraries") as s:
        created, existing = [], []
        for lib in n.libraries():
            if zos.exists(lib["name"]):
                existing.append(lib["name"])
            else:
                s.detail(f"Allocating {lib['name']}")
                zos.create_library(lib["name"], lib["recfm"], lib["lrecl"])
                created.append(lib["name"])
        s.data(created=created, existing=existing)
        s.detail(f"{len(created)} allocated, {len(existing)} already existed")
    _upload_sources(ctx, list(SOURCE_STEPS))
    _compile(ctx)
    db.kv_set("setup_done", True)


def compile_programs(ctx: RunContext) -> None:
    ctx.plan(["Upload copybooks", "Upload COBOL programs", "Compile and link (EWSCOMP)", "Verify load modules"])
    _upload_sources(ctx, ["copybooks", "cobol"])
    _compile(ctx)


def upload_sources(ctx: RunContext) -> None:
    ctx.plan([SOURCE_STEPS[k] for k in ("sortcntl", "rexx", "jcl")])
    _upload_sources(ctx, ["sortcntl", "rexx", "jcl"])


def generate_data(ctx: RunContext, customers: int = 1500, seed: int = 42) -> None:
    from ml.generate_data import generate

    customers, seed = int(customers), int(seed)
    if not 200 <= customers <= 3000:
        raise ActionError("Customers must be between 200 and 3000")
    n = names()
    inputs = n.inputs()
    ctx.plan(["Generate synthetic data", "Allocate input data sets",
              *[f"Upload {i['name']}" for i in inputs]])
    with ctx.step("Generate synthetic data") as s:
        manifest = generate(customers, seed, INPUT_DIR)
        s.data(records=manifest["records"], defects=len(manifest["defects"]))
        s.detail(f"{customers} customers, {sum(manifest['records'].values())} records, "
                 f"{len(manifest['defects'])} deliberately bad records")
    with ctx.step("Allocate input data sets") as s:
        for i in inputs:
            if zos.exists(i["name"]):
                zos.delete(i["name"])
            zos.create_sequential(i["name"], "FB", i["lrecl"], i["size"])
        s.detail(", ".join(f"{i['name']} FB {i['lrecl']}" for i in inputs))
    for i in inputs:
        with ctx.step(f"Upload {i['name']}") as s:
            zos.upload_file(INPUT_DIR / i["file"], i["name"])
            s.detail(f"{manifest['records'][i['file']]} records uploaded")
    db.kv_set("data", {"customers": customers, "seed": seed, "records": manifest["records"],
                       "defects": len(manifest["defects"]), "generated_at": db.now()})
    ctx.summary = {"customers": customers, "records": manifest["records"]}


def train_model(ctx: RunContext) -> None:
    from ml import train

    labels = [f"EWSBATCH TRAIN as-of {a}" for a in TRAIN_ASOFS]
    ctx.plan([*labels, "Train and evaluate model"])
    paths = []
    for asof, label in zip(TRAIN_ASOFS, labels):
        with ctx.step(label) as s:
            res = run_ewsbatch(ctx, s, asof, "TRAIN", f"train_{asof}")
            paths.append(res["dir"] / "features.csv")
            s.data(positives=res["runctl"].get("LABEL_POSITIVE"))
    with ctx.step("Train and evaluate model") as s:
        metrics = train.train(paths)
        s.data(**{k: metrics[k] for k in ("model_version", "rows", "positive_rate")},
               validation=metrics["validation"]["xgboost"])
        s.detail(f"XGBoost ROC-AUC {metrics['validation']['xgboost']['roc_auc']:.3f}, "
                 f"PR-AUC {metrics['validation']['xgboost']['pr_auc']:.3f} "
                 f"(baseline LR {metrics['validation']['logistic_regression']['roc_auc']:.3f})")
    ctx.summary = {"model_version": metrics["model_version"], "validation": metrics["validation"]}


def run_batch(ctx: RunContext, asof: int = SCORE_ASOF) -> None:
    from ml import score

    asof = validate_asof(asof)
    if not score.model_exists():
        raise ActionError("No trained model yet. Run 'Train model' first.")
    n = names()
    ctx.plan(["Submit EWSBATCH (DFSORT, COBOL, REXX)", "Load master data from the mainframe",
              "Score customers (model + SHAP)", "Write scores back (EWS.SCORES)",
              "Submit EWSRPTJ (VSAM update + intervention report)", "Check VSAM clusters (LISTCAT)",
              "Download report (EWS.RISKRPT)"])
    with ctx.step("Submit EWSBATCH (DFSORT, COBOL, REXX)") as s:
        res = run_ewsbatch(ctx, s, asof, "SCORE", "score")
    with ctx.step("Load master data from the mainframe") as s:
        s.detail(f"Downloading {n.CUST_VALID}, {n.LOAN_VALID}, {n.TXN_SRT}")
        texts = [zos.download(dsn, ctx.dir / "master" / f"{dsn.split('.', 2)[2].lower()}.txt").read_text()
                 for dsn in (n.CUST_VALID, n.LOAN_VALID, n.TXN_SRT)]
        counts = load_master_data(*texts)
        s.data(**counts)
        s.detail(f"{counts['customers']} customers, {counts['loans']} loans, {counts['monthly']} monthly summaries")
    with ctx.step("Score customers (model + SHAP)") as s:
        result = score.score_run(ctx.run_id, res["dir"] / "features.csv")
        s.data(**result["tiers"], model_version=result["model_version"])
        s.detail(f"{result['scored']} customers scored: {result['tiers']['High']} high, "
                 f"{result['tiers']['Medium']} medium, {result['tiers']['Low']} low")
    with ctx.step("Write scores back (EWS.SCORES)") as s:
        local = ctx.dir / "scores.txt"
        local.write_text("\n".join(result["score_records"]) + "\n")
        if zos.exists(n.SCORES):
            zos.delete(n.SCORES)
        zos.create_sequential(n.SCORES, "FB", 80, "15TRK")
        zos.upload_file(local, n.SCORES)
        s.detail(f"{len(result['score_records'])} SCOREREC records uploaded to {n.SCORES}")
    with ctx.step("Submit EWSRPTJ (VSAM update + intervention report)") as s:
        rpt = submit_job(s, "EWSRPTJ", max_rc=0)
        supd = job_displays(rpt["jobid"], "STEP008", "EWSSUPD")
        rpt_counts = job_displays(rpt["jobid"], "STEP020", "EWSRPT")
        s.data(vsam_update=supd, report=rpt_counts)
        s.detail(f"EWSRPTJ {rpt['jobid']} {rpt['retcode']}: {n.SCORKSDS} {supd.get('added', 0)} added, "
                 f"{supd.get('updated', 0)} updated in place ({supd.get('tier_changed', 0)} changed tier); "
                 f"{rpt_counts.get('names_from_vsam', 0)} names read by key from {n.CUSTKSDS}")
    with ctx.step("Check VSAM clusters (LISTCAT)") as s:
        vsam = check_vsam(s, result["scored"])
        s.detail(f"{n.CUSTKSDS} {vsam['custksds_records']} records, {n.SCORKSDS} {vsam['scoreksds_records']} "
                 f"records ({vsam['scoreksds_updated']} updates so far) on {vsam['volume']}")
    with ctx.step("Download report (EWS.RISKRPT)") as s:
        zos.download(n.RISKRPT, ctx.dir / "riskrpt.txt")
        s.detail(f"Report downloaded ({len((ctx.dir / 'riskrpt.txt').read_text().splitlines())} lines)")
    ctx.summary = {"asof": asof, "batch_job": res["job"]["jobid"], "report_job": rpt["jobid"],
                   "runctl": res["runctl"], "tiers": result["tiers"], "scored": result["scored"],
                   "vsam": {**vsam, **supd}}
    db.kv_set("last_score_run", ctx.run_id)


def reset_data(ctx: RunContext, confirm: bool = False) -> None:
    if confirm is not True:
        raise ActionError("Reset needs confirmation")
    n = names()
    ctx.plan(["Delete EWS data sets"])
    with ctx.step("Delete EWS data sets") as s:
        keep = {n.JCL, n.CPY, n.CNTL, n.REXX}
        removed = []
        for d in zos.list_datasets(f"{n.hlq}.EWS.**"):
            name = d["dsname"]
            if name in keep:
                continue
            if d.get("dsorg") == "VS":
                if name.endswith((".DATA", ".INDEX")):
                    continue  # components go with their cluster
                zos.delete_vsam(name)
            else:
                zos.delete(name)
            removed.append(name)
        s.data(deleted=removed)
        s.detail(f"Deleted {len(removed)} data sets (libraries kept)")
    db.kv_set("data", None)


ACTIONS = {
    "test_connection": {"fn": test_connection, "label": "Test connection"},
    "setup": {"fn": setup, "label": "Set up mainframe"},
    "compile": {"fn": compile_programs, "label": "Recompile COBOL programs"},
    "upload_sources": {"fn": upload_sources, "label": "Upload JCL, DFSORT and REXX"},
    "generate_data": {"fn": generate_data, "label": "Generate & upload data"},
    "train_model": {"fn": train_model, "label": "Train model"},
    "run_batch": {"fn": run_batch, "label": "Run batch & score"},
    "reset_data": {"fn": reset_data, "label": "Reset mainframe data"},
}


# ============================================================ read-only helpers for the API
def read_features_csv(path: Path) -> list[dict]:
    return list(csv.DictReader(io.StringIO(path.read_text())))


def mainframe_status() -> dict:
    """Live setup checklist (several Zowe calls; the API caches it)."""
    info = zos.check_status()
    n = names()
    dsns = {d["dsname"]: d for d in zos.list_datasets(f"{n.hlq}.EWS.**")}
    libs = [l["name"] for l in n.libraries() if l["name"] not in (n.CBL, n.LOAD)]
    load = set(zos.list_members(n.LOAD)) if zos.exists(n.LOAD) else set()
    return {
        "connection": info,
        "hlq": n.hlq,
        "libraries": {l: l in dsns for l in libs},
        "programs": {p: p in load for p in PROGRAMS},
        "inputs": {i["name"]: i["name"] in dsns for i in n.inputs()},
        "vsam": {v: v in dsns for v in (n.CUSTKSDS, n.SCORKSDS)},
        "datasets": sorted(dsns),
    }


def vsam_customer(cust_id: str) -> dict:
    """One customer straight from the two VSAM KSDS on z/OS, read by key (IDCAMS PRINT via z/OSMF)."""
    cust_id = cust_id.upper()
    if not re.fullmatch(r"[A-Z0-9]{8}", cust_id):
        raise ActionError("Customer IDs are 8 letters or digits, e.g. CUST0166")
    n = names()
    t0 = time.monotonic()
    cust = zos.vsam_read(n.CUSTKSDS, cust_id)
    score = zos.vsam_read(n.SCORKSDS, cust_id)
    ms = int((time.monotonic() - t0) * 1000)
    c = CUSTREC.parse(cust[0]) if cust else None
    sc = SCOREVS.parse(score[0]) if score else None
    for rec in (c, sc):
        if rec:
            rec.pop("filler", None)
    return {"cust_id": cust_id, "customer": c, "score": sc, "ms": ms,
            "source": {"customer": n.CUSTKSDS, "score": n.SCORKSDS},
            "raw": {"customer": cust[0] if cust else None, "score": score[0] if score else None}}


def vsam_clusters() -> list[dict]:
    """LISTCAT statistics of the project's KSDS clusters (missing ones are reported as such)."""
    out = []
    for dsn, role in ((names().CUSTKSDS, "customer master, rebuilt by EWSBATCH STEP055"),
                      (names().SCORKSDS, "latest score per customer, updated in place by EWSSUPD")):
        try:
            lc = zos.listcat(dsn)
        except zos.ZosError as e:
            out.append({"dsname": dsn, "role": role, "exists": False, "error": str(e)[:300]})
            continue
        out.append({"dsname": dsn, "role": role, "exists": "data" in lc, **lc})
    return out


def dataset_info(dsn: str) -> dict:
    items = zos.list_datasets(dsn)
    return next((d for d in items if d["dsname"] == dsn), {})


__all__ = ["ACTIONS", "names", "hlq", "parse_runctl", "parse_rejects", "mainframe_status", "json"]
