"""Rich markup rendering for Explain-mode output in the TUI."""
from __future__ import annotations

import re

_EXPLAIN_SECTIONS = (
    "OVERVIEW",
    "MAIN TOPICS",
    "LEARNINGS / DECISIONS",
    "CURRENT STATUS",
    "OPEN QUESTIONS",
    "KEY TAKEAWAYS",
)

_HIGHLIGHT_SECTIONS = frozenset({"CURRENT STATUS", "OPEN QUESTIONS", "KEY TAKEAWAYS"})


def explain_markup(text: str) -> str:
    """Convert plain explain export text into highlighted Rich markup."""
    if not (text or "").strip():
        return "[dim italic]No explanation available yet.[/]"

    lines = text.strip().splitlines()
    out: list[str] = []
    current_section = ""
    body: list[str] = []

    def flush() -> None:
        nonlocal body
        if not current_section:
            return
        if current_section in _HIGHLIGHT_SECTIONS:
            out.append(f"[bold #fbbf24]{current_section}[/]")
        else:
            out.append(f"[bold #67e8f9]{current_section}[/]")
        if body:
            content = "\n".join(body).strip()
            if current_section in _HIGHLIGHT_SECTIONS:
                out.append(f"[#fde68a]{content}[/]")
            else:
                out.append(f"[#f1f5f9]{content}[/]")
        out.append("")
        body = []

    for raw in lines:
        line = raw.strip()
        if line in _EXPLAIN_SECTIONS:
            flush()
            current_section = line
            continue
        if not line:
            continue
        body.append(line)

    flush()
    return "\n".join(out).strip() if out else f"[#f1f5f9]{text.strip()}[/]"


def explain_sections(text: str) -> list[str]:
    found: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in _EXPLAIN_SECTIONS:
            found.append(stripped)
    return found
