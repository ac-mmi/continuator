"""Smoke tests for the Continuator Textual TUI shell (no extraction)."""
from __future__ import annotations

import asyncio

from continuator.tui.app import ContinuatorApp, OpenFileScreen
from continuator.tui.briefing_render import briefing_markup
from continuator.title_art import TITLE_PLAIN_SIGNATURE


def test_briefing_markup_highlights_critical_sections() -> None:
    text = (
        "## PROJECT\n\nneck\n\nObjective:\nFix posture\n\n"
        "Current Position:\nUser has neck hump\n\n"
        "Next Action:\nDaily routine\n"
    )
    markup = briefing_markup(text, fallback_title="neck")
    assert "CURRENT POSITION" in markup
    assert "#fbbf24" in markup
    assert "NEXT ACTION" in markup


def test_tui_welcome_and_briefing_display() -> None:
    async def run() -> None:
        app = ContinuatorApp(conversation=None)
        async with app.run_test(size=(120, 45)) as pilot:
            assert TITLE_PLAIN_SIGNATURE in str(pilot.app.query_one("#hero-logo").render())
            tagline = pilot.app.query_one("#hero-tagline").render()
            assert "Turn conversations into AI continuation briefings." in str(tagline)
            assert pilot.app.query_one("#workspace-view").has_class("hidden")
            assert "Ready" in pilot.app.query_one("#status-bar").render().plain
            assert pilot.app.query_one("#btn-copy").disabled is True

            pilot.app.push_screen(OpenFileScreen())
            await pilot.pause()
            assert type(pilot.app.screen).__name__ == "OpenFileScreen"

            app._show_workspace()
            app._briefing = "## PROJECT\n\ndemo\n\nObjective:\nContinue work"
            app._result = {
                "continuation_briefing": app._briefing,
                "exports": {"claude": "claude payload", "chatgpt": "chatgpt payload"},
            }
            app._stream_briefing(app._briefing)
            app._set_actions_enabled(True)
            await pilot.pause()
            assert pilot.app.query_one("#btn-copy").disabled is False
            assert pilot.app.query_one("#briefing-content").display is True

    asyncio.run(run())


def test_cli_routes_to_tui_without_subcommand() -> None:
    from continuator.cli import _SUBCOMMANDS

    assert "continue" in _SUBCOMMANDS
    assert "export" in _SUBCOMMANDS
