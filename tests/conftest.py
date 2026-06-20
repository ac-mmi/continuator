"""Pytest path setup for continuator_engine flat imports."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "continuator_engine"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))
