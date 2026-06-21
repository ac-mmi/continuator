#!/usr/bin/env python3
"""Export hero logo previews as SVG screenshots for design review."""
from __future__ import annotations

import asyncio
from pathlib import Path

from rich.align import Align
from rich.console import Group
from rich.markup import render
from rich.panel import Panel

from continuator.title_art import (
    HERO_ACTIONS,
    HERO_TAGLINE,
    SELECTED_LOGO,
    hero_card_markup,
    list_logo_variants,
    render_logo_markup,
)
from continuator.tui.app import ContinuatorApp

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "hero-previews"


def _panel(body: RenderableType, title: str) -> Panel:
    return Panel(
        body,
        title=title,
        border_style="#0891b2",
        style="on #0d1117",
        padding=(1, 2),
    )


async def export_tui_screenshots() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    app = ContinuatorApp(conversation=None)
    async with app.run_test(size=(120, 45)) as pilot:
        await pilot.pause()
        svg = app.export_screenshot(title="hero-final")
        (OUTPUT_DIR / "11-final-hero-tui.svg").write_text(svg, encoding="utf-8")

        for spec in list_logo_variants():
            logo = app.query_one("#hero-logo")
            logo.update(render(render_logo_markup(spec.key)))
            await pilot.pause()
            shot = app.export_screenshot(title=f"logo-{spec.key}")
            (OUTPUT_DIR / f"{spec.key}-{spec.label.lower().replace(' ', '-')}.svg").write_text(
                shot,
                encoding="utf-8",
            )

        logo = app.query_one("#hero-logo")
        logo.update(render(render_logo_markup(SELECTED_LOGO)))
        await pilot.pause()


def export_logo_cards() -> None:
    from rich.console import Console

    console = Console(record=True, width=88)
    for spec in list_logo_variants():
        card = Group(
            Align.center(render(render_logo_markup(spec.key))),
            "",
            Align.center(render(HERO_TAGLINE)),
            Align.center(render(HERO_ACTIONS)),
        )
        console.print(_panel(card, f"[bold #67e8f9]{spec.key} · {spec.label}[/]"))
        console.print()

    console.save_svg(str(OUTPUT_DIR / "00-all-logo-cards.svg"), title="Continuator hero logos")

    console = Console(record=True, width=88)
    console.print(
        _panel(
            render(hero_card_markup(SELECTED_LOGO)),
            "[bold #67e8f9]Recommended · 02 Stacked Claude-style[/]",
        )
    )
    console.save_svg(str(OUTPUT_DIR / "12-recommended-hero-card.svg"), title="Recommended hero")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    export_logo_cards()
    asyncio.run(export_tui_screenshots())
    print(f"Wrote previews to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
