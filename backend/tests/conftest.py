import os
import tempfile
from pathlib import Path

# Point the app at a throwaway database before any app module is imported.
_tmp = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.as_posix()}"
os.environ.setdefault("JWT_SECRET", "test-secret")
