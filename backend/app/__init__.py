"""Wind-power forecast monitoring application backend."""

from pathlib import Path
import sys
import types

# Ensure 'backend' package alias exists if imported directly as 'app'
_app_dir = Path(__file__).resolve().parent
_backend_dir = _app_dir.parent

for _p in (_backend_dir, _backend_dir.parent):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

if "backend" not in sys.modules:
    _backend_pkg = types.ModuleType("backend")
    _backend_pkg.__path__ = [str(_backend_dir)]
    sys.modules["backend"] = _backend_pkg

if "backend.app" not in sys.modules:
    _curr = sys.modules.get(__name__)
    if _curr:
        _backend_pkg = sys.modules["backend"]
        _backend_pkg.app = _curr
        sys.modules["backend.app"] = _curr
