"""Terminal presentation — re-exports ContinuatorConsole for commands."""
from __future__ import annotations

from continuator.console import FOOTER, ContinuatorConsole, render_briefing_panel, sanitize_error

__all__ = [
    "FOOTER",
    "ContinuatorConsole",
    "render_briefing_panel",
    "sanitize_error",
]
