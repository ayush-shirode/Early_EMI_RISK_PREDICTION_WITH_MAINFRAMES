"""Names and locations shared by the backend. Override with environment variables."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAINFRAME_SRC = ROOT / "mainframe"
DATA_DIR = ROOT / "data"                 # SQLite DB, generated input files, run folders
RUNS_DIR = DATA_DIR / "runs"
INPUT_DIR = DATA_DIR / "input"
ARTIFACTS_DIR = ROOT / "ml" / "artifacts"
DB_PATH = Path(os.environ.get("EWS_DB", DATA_DIR / "ews.sqlite"))

# High-level qualifier = the z/OS user ID. Detected from the Zowe profile when not set.
HLQ_ENV = os.environ.get("EWS_HLQ", "").upper()

# Score with this as-of date; train on the quarter-ends before it whose 90-day
# outcome window is complete in the data.
SCORE_ASOF = int(os.environ.get("EWS_SCORE_ASOF", "20260930"))
TRAIN_ASOFS = [20250930, 20251231, 20260331, 20260630]

# Tier thresholds on the predicted probability.
TIER_MEDIUM = 0.30
TIER_HIGH = 0.60


class Names:
    """All z/OS data set names used by the project, for one HLQ."""

    def __init__(self, hlq: str):
        self.hlq = hlq
        e = f"{hlq}.EWS"
        # libraries
        self.CBL = f"{hlq}.CBL"         # site IGYWCL proc reads &SYSUID..CBL(&SRC)
        self.LOAD = f"{hlq}.LOAD"       # ... and links into &SYSUID..LOAD(&SRC)
        self.JCL = f"{e}.JCL"
        self.CPY = f"{e}.CPY"
        self.CNTL = f"{e}.CNTL"
        self.REXX = f"{e}.REXX"
        # inputs
        self.CUSTMAST = f"{e}.CUSTMAST"
        self.LOANMAST = f"{e}.LOANMAST"
        self.REPAYHST = f"{e}.REPAYHST"
        self.TXNSUMM = f"{e}.TXNSUMM"
        # outputs of EWSBATCH
        self.CUST_VALID = f"{e}.CUST.VALID"
        self.LOAN_VALID = f"{e}.LOAN.VALID"
        self.TXN_SRT = f"{e}.TXN.SRT"
        self.REJECTS = f"{e}.REJECTS"
        self.EXCEPT = f"{e}.EXCEPT"
        self.FEATURES = f"{e}.FEATURES"
        self.FEATCSV = f"{e}.FEATCSV"
        self.RUNCTL = f"{e}.RUNCTL"
        # write-back
        self.SCORES = f"{e}.SCORES"
        self.RISKRPT = f"{e}.RISKRPT"
        # VSAM KSDS, key = customer ID: rebuilt by EWSBATCH / updated in place by EWSSUPD
        self.CUSTKSDS = f"{e}.CUSTKSDS"
        self.SCORKSDS = f"{e}.SCORKSDS"

    def libraries(self) -> list[dict]:
        """PDS-E libraries that setup allocates when missing."""
        return [
            {"name": self.CBL, "recfm": "FB", "lrecl": 80, "source": "cobol", "ext": ".cbl"},
            {"name": self.LOAD, "recfm": "U", "lrecl": 0, "source": None},
            {"name": self.CPY, "recfm": "FB", "lrecl": 80, "source": "copybooks", "ext": ".cpy"},
            {"name": self.CNTL, "recfm": "FB", "lrecl": 80, "source": "sortcntl", "ext": ""},
            {"name": self.REXX, "recfm": "FB", "lrecl": 80, "source": "rexx", "ext": ".rexx"},
            {"name": self.JCL, "recfm": "FB", "lrecl": 80, "source": "jcl", "ext": ".jcl"},
        ]

    def inputs(self) -> list[dict]:
        """Input sequential data sets and the local file uploaded into each."""
        return [
            {"name": self.CUSTMAST, "lrecl": 100, "file": "custmast.txt", "size": "15TRK"},
            {"name": self.LOANMAST, "lrecl": 80, "file": "loanmast.txt", "size": "15TRK"},
            {"name": self.REPAYHST, "lrecl": 80, "file": "repayhst.txt", "size": "150TRK"},
            {"name": self.TXNSUMM, "lrecl": 80, "file": "txnsumm.txt", "size": "150TRK"},
        ]

    def is_project_dataset(self, dsn: str) -> bool:
        """The UI may only browse project data sets."""
        return dsn.upper().startswith(f"{self.hlq}.EWS.")
