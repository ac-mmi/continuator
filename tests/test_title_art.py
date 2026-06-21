"""Tests for the hero title and welcome screen."""
from __future__ import annotations

from continuator.title_art import (
    TITLE_PLAIN_SIGNATURE,
    hero_card_markup,
    logo_lines,
    render_logo_markup,
)


def test_block_logo_renders_solid_letters() -> None:
    lines = logo_lines()
    assert len(lines) == 11
    assert TITLE_PLAIN_SIGNATURE in lines[5]
    assert "██╗" in lines[0]
    markup = render_logo_markup()
    assert "#67e8f9" in markup
    assert "bold" in markup
    assert "Turn conversations into AI continuation briefings." in hero_card_markup()
