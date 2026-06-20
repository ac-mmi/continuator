"""Rich markup rendering for continuation briefings in the TUI."""
from __future__ import annotations

from continuator.console import _SECTION_ORDER, _parse_briefing

_CRITICAL_SECTIONS = frozenset({"Current Position", "Active Problems", "Next Action"})


def briefing_sections(
    text: str,
    *,
    fallback_title: str = "",
) -> tuple[str, dict[str, str]]:
    project, _, sections = _parse_briefing(text, fallback_title=fallback_title)
    return project, sections


def section_markup(key: str, body: str) -> str:
    if not body or body.lower() in {"none identified.", "none identified"}:
        body = "[dim italic]None[/]"

    if key in _CRITICAL_SECTIONS:
        return f"[bold #fbbf24]{key.upper()}[/]\n[#fde68a]{body}[/]"
    return f"[bold #67e8f9]{key.upper()}[/]\n[#f1f5f9]{body}[/]"


def briefing_markup(
    text: str,
    *,
    fallback_title: str = "",
    include_sections: set[str] | None = None,
) -> str:
    """Build Rich markup for briefing display with visual hierarchy."""
    project, sections = briefing_sections(text, fallback_title=fallback_title)
    lines: list[str] = [
        "[bold #e0f2fe]PROJECT[/]",
        f"[bold white]{project or fallback_title or 'Conversation'}[/]",
    ]

    for key in _SECTION_ORDER:
        if key not in sections:
            continue
        if include_sections is not None and key not in include_sections:
            continue
        lines.append("")
        lines.append(section_markup(key, sections[key]))

    if len(lines) <= 2 and text.strip():
        lines.append("")
        lines.append(f"[#f1f5f9]{text.strip()}[/]")

    return "\n".join(lines)


def ordered_section_keys(text: str, *, fallback_title: str = "") -> list[str]:
    _, sections = briefing_sections(text, fallback_title=fallback_title)
    return [key for key in _SECTION_ORDER if key in sections]
