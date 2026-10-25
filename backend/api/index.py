"""Vercel serverless function entrypoint for FastAPI backend."""

import os
import sys
import types
from pathlib import Path

# Resolve current directory and backend root
current_file = Path(__file__).resolve()
backend_root = current_file.parent.parent  # backend/ directory

# Ensure paths are added to sys.path
for path_entry in (backend_root, backend_root.parent):
    str_path = str(path_entry)
    if str_path not in sys.path:
        sys.path.insert(0, str_path)

# Configure default DATA_DIR pointing to backend/data if not explicitly set
if not os.getenv("DATA_DIR"):
    data_dir = backend_root / "data"
    if data_dir.exists():
        os.environ["DATA_DIR"] = str(data_dir)

# Handle module alias when deployed with Root Directory = backend
try:
    import backend.app  # noqa: F401
except ImportError:
    import app as app_pkg

    backend_pkg = types.ModuleType("backend")
    backend_pkg.__path__ = [str(backend_root)]
    backend_pkg.app = app_pkg
    sys.modules["backend"] = backend_pkg
    sys.modules["backend.app"] = app_pkg

from backend.app.data_loader import data_loader  # noqa: E402
from backend.app.main import app  # noqa: E402

# Ensure data snapshots are loaded on cold start
try:
    if not data_loader.is_loaded:
        data_loader.load_data()
except Exception as exc:
    import logging

    logging.getLogger("api.index").error("Cold start data loading error: %s", exc)

# Explicitly expose app for Vercel Python runtime
__all__ = ["app"]
