"""Hero title and welcome-screen copy for Continuator."""
from __future__ import annotations

from rich.console import RenderableType
from rich.markup import render

CYAN_BRIGHT = "#67e8f9"
CYAN_GLOW = "#22d3ee"

TITLE_PLAIN_SIGNATURE = "██████╗"

# Solid block letters (Unicode box drawing).
_AI_LINES = (
    " █████╗ ██╗",
    "██╔══██╗██║",
    "███████║██║",
    "██╔══██║██║",
    "██║  ██║██║",
)

_CONTINUATOR_LINES = (
    " ██████╗ ██████╗ ███╗   ██╗████████╗██╗███╗   ██╗██╗   ██╗ █████╗ ████████╗ ██████╗ ██████╗",
    "██╔════╝██╔═══██╗████╗  ██║╚══██╔══╝██║████╗  ██║██║   ██║██╔══██╗╚══██╔══╝██╔═══██╗██╔══██╗",
    "██║     ██║   ██║██╔██╗ ██║   ██║   ██║██╔██╗ ██║██║   ██║███████║   ██║   ██║   ██║██████╔╝",
    "██║     ██║   ██║██║╚██╗██║   ██║   ██║██║╚██╗██║██║   ██║██╔══██║   ██║   ██║   ██║██╔══██╗",
    "╚██████╗╚██████╔╝██║ ╚████║   ██║   ██║██║ ╚████║╚██████╔╝██║  ██║   ██║   ╚██████╔╝██║  ██║",
    " ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝",
)

HERO_TAGLINE = "[#94a3b8]Turn conversations into AI continuation briefings.[/]"
HERO_ACTIONS = (
    "[#64748b]Continue[/][#1e3a4a]  ·  [/]"
    "[#64748b]Explain[/][#1e3a4a]  ·  [/]"
    "[#64748b]Export[/]"
)
HERO_HINT = (
    "[#475569]Press [/][bold #22d3ee]O[/][#475569] to open  ·  "
    "[bold #22d3ee]Q[/][#475569] to quit[/]"
)


def _centered_block_lines() -> list[str]:
    width = max(
        max(len(line) for line in _AI_LINES),
        max(len(line) for line in _CONTINUATOR_LINES),
    )
    lines = [line.center(width) for line in _AI_LINES]
    lines.append("")
    lines.extend(line.center(width) for line in _CONTINUATOR_LINES)
    return lines


def render_logo_markup() -> str:
    """Solid block-letter AI + CONTINUATOR logo."""
    styled = [f"[bold {CYAN_BRIGHT}]{line}[/]" if line.strip() else "" for line in _centered_block_lines()]
    return "\n".join(styled)


def logo_renderable() -> RenderableType:
    return render(render_logo_markup())


def hero_card_markup() -> str:
    return "\n\n".join([render_logo_markup(), HERO_TAGLINE, HERO_ACTIONS])


def hero_card_renderable() -> RenderableType:
    return render(hero_card_markup())


def title_markup() -> str:
    return render_logo_markup()


def title_renderable() -> RenderableType:
    return logo_renderable()


def welcome_title_markup() -> str:
    return f"{render_logo_markup()}\n"


def logo_lines() -> list[str]:
    return [line for line in _centered_block_lines() if line.strip()]


def title_lines() -> list[str]:
    return logo_lines()
