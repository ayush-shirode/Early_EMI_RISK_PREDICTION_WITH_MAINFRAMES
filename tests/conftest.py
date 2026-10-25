import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Tests never touch the real database.
os.environ.setdefault("EWS_DB", str(Path(tempfile.mkdtemp()) / "test.sqlite"))
