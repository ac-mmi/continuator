"""Reusable Textual widgets for the Continuator TUI."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, RichLog, Static
from rich.align import Align
from rich.markup import render

from continuator.title_art import HERO_ACTIONS, HERO_HINT, HERO_TAGLINE, logo_renderable


class WelcomePanel(Vertical):
    """Landing screen shown before a conversation is loaded."""

    DEFAULT_CSS = """
    WelcomePanel {
        height: 1fr;
        width: 100%;
        align: center middle;
        background: #0d1117;
    }

    #hero-stack {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #hero-logo {
        width: 100%;
        height: auto;
        color: #67e8f9;
        text-style: bold;
        text-align: center;
        content-align: center middle;
        margin-bottom: 1;
    }

    #hero-tagline {
        width: 100%;
        height: auto;
        text-align: center;
        content-align: center middle;
    }

    #hero-actions {
        width: 100%;
        height: auto;
        text-align: center;
        content-align: center middle;
        margin-top: 1;
    }

    #hero-hint {
        width: 100%;
        height: auto;
        text-align: center;
        content-align: center middle;
        margin-top: 2;
        color: #475569;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="hero-stack"):
            yield Static(Align.center(logo_renderable()), id="hero-logo")
            yield Static(Align.center(render(HERO_TAGLINE)), id="hero-tagline")
            yield Static(Align.center(render(HERO_ACTIONS)), id="hero-actions")
            yield Static(Align.center(render(HERO_HINT)), id="hero-hint")


class ActivityFeed(RichLog):
    """Timestamped pipeline activity log."""

    DEFAULT_CSS = """
    ActivityFeed {
        height: 1fr;
        border: solid #1e3a4a;
        background: #0a1018;
        padding: 0 1;
    }
    """

    def mark_done(self, message: str) -> None:
        self.write(f"[green]✓[/] {message}")

    def mark_active(self, message: str) -> None:
        self.write(f"[bold cyan]›[/] {message}")

    def mark_pending(self, message: str) -> None:
        self.write(f"[dim]○[/] {message}")

    def mark_info(self, message: str) -> None:
        self.write(f"[#94a3b8]{message}[/]")


class InfoBar(Horizontal):
    """Conversation metadata strip."""

    DEFAULT_CSS = """
    InfoBar {
        height: 3;
        padding: 0 2;
        background: #111827;
        border: solid #1e3a4a;
    }
    InfoBar .info-label {
        color: #64748b;
        width: auto;
        margin-right: 1;
    }
    InfoBar .info-value {
        color: #22d3ee;
        text-style: bold;
        margin-right: 3;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("FILE", classes="info-label")
        yield Static("—", id="info-file", classes="info-value")
        yield Label("SIZE", classes="info-label")
        yield Static("—", id="info-size", classes="info-value")
        yield Label("CHUNKS", classes="info-label")
        yield Static("—", id="info-chunks", classes="info-value")
        yield Label("EST", classes="info-label")
        yield Static("—", id="info-estimate", classes="info-value")

    def update_stats(
        self,
        *,
        filename: str = "",
        size_label: str = "",
        chunks: str = "",
        estimate: str = "",
    ) -> None:
        self.query_one("#info-file", Static).update(filename or "—")
        self.query_one("#info-size", Static).update(size_label or "—")
        self.query_one("#info-chunks", Static).update(chunks or "—")
        self.query_one("#info-estimate", Static).update(estimate or "—")


class MetadataPanel(Vertical):
    """Post-analysis conversation summary (left column)."""

    DEFAULT_CSS = """
    MetadataPanel {
        height: auto;
        max-height: 14;
        padding: 1;
        border: solid #1e3a4a;
        background: #0a1018;
    }
    MetadataPanel .meta-title {
        text-style: bold;
        color: #67e8f9;
        margin-bottom: 1;
    }
    MetadataPanel .meta-line {
        color: #cbd5e1;
        margin-bottom: 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Conversation", classes="meta-title")
        yield Static("", id="meta-body", classes="meta-line")

    def update_metadata(self, lines: list[str]) -> None:
        self.query_one("#meta-body", Static).update("\n".join(lines))
