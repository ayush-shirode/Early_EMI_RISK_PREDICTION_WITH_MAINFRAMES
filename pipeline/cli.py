"""Run a Control Center action from a terminal (debugging only; the UI never needs this).

    python -m pipeline.cli setup
    python -m pipeline.cli generate_data customers=1000 seed=42
    python -m pipeline.cli run_batch asof=20260930
"""
from __future__ import annotations

import json
import sys

from pipeline import db, runner
from pipeline.actions import ACTIONS


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ACTIONS:
        print("actions:", ", ".join(ACTIONS))
        sys.exit(2)
    params = {}
    for arg in sys.argv[2:]:
        k, v = arg.split("=", 1)
        params[k] = True if v == "true" else int(v) if v.isdigit() else v
    db.init()
    run_id = runner.run_inline(sys.argv[1], ACTIONS[sys.argv[1]]["fn"], params)
    run = runner.get_run(run_id)
    for s in run["steps"]:
        print(f"[{s['status']:>7}] {s['name']}: {s['detail'] or ''}")
    print(f"run #{run_id} {run['status']}", run["error"] or "")
    if run["summary"]:
        print(json.dumps(run["summary"], indent=2, default=str)[:3000])
    sys.exit(0 if run["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
