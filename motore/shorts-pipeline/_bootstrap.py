"""Load the shared portable runtime when pipeline scripts run directly."""
from pathlib import Path
import sys

_MOTORE = str(Path(__file__).resolve().parent.parent)
if _MOTORE not in sys.path:
    sys.path.insert(0, _MOTORE)
from runtime import ensure_env

ensure_env()
