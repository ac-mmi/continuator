"""Platform-specific handoff export formatters for product validation."""
from __future__ import annotations

from typing import Literal

ExportFormat = Literal["claude", "chatgpt", "gemini", "markdown"]


def format_for_claude(handoff: str, *, label: str = "") -> str:
    title = f" ({label})" if label else ""
    return (
        f"Continue this conversation{title}. Treat the briefing below as your only prior context.\n"
        f"Do not summarize for the user — continue naturally from the stopping point.\n\n"
        f"{handoff.strip()}"
    )


def format_for_chatgpt(handoff: str, *, label: str = "") -> str:
    header = f"# Conversation handoff — {label}\n\n" if label else "# Conversation handoff\n\n"
    return (
        f"{header}"
        "Paste into a new ChatGPT thread. Continue from where the prior conversation stopped.\n\n"
        f"{handoff.strip()}\n\n"
        "---\n"
        "Please continue the conversation from the current position."
    )


def format_for_gemini(handoff: str, *, label: str = "") -> str:
    title = f" for: {label}" if label else ""
    return (
        f"You are picking up an in-progress conversation{title}.\n"
        "Use this briefing as your context and continue without recapping for a human audience.\n\n"
        f"{handoff.strip()}"
    )


def format_generic_markdown(handoff: str, *, label: str = "") -> str:
    if label:
        return f"# AI Handoff — {label}\n\n{handoff.strip()}"
    return handoff.strip()


def build_platform_exports(handoff: str, *, label: str = "") -> dict[str, str]:
    text = (handoff or "").strip()
    if not text:
        return {"claude": "", "chatgpt": "", "gemini": "", "markdown": ""}
    return {
        "claude": format_for_claude(text, label=label),
        "chatgpt": format_for_chatgpt(text, label=label),
        "gemini": format_for_gemini(text, label=label),
        "markdown": format_generic_markdown(text, label=label),
    }


def format_handoff(handoff: str, fmt: ExportFormat, *, label: str = "") -> str:
    formatters = {
        "claude": format_for_claude,
        "chatgpt": format_for_chatgpt,
        "gemini": format_for_gemini,
        "markdown": format_generic_markdown,
    }
    return formatters[fmt](handoff, label=label)
