"""Reusable Textual widgets for the Continuator TUI."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, RichLog, Static


WELCOME_BODY = """\
[bold #e0f2fe]AI CONTINUATOR[/]

[#94a3b8]Turn long conversations into AI continuation briefings.[/]

[bold #67e8f9]Capabilities[/]
[green]✓[/] Continue projects
[green]✓[/] Resume tutorials
[green]✓[/] Continue research
[green]✓[/] Continue journals

[#64748b]Press [/][bold cyan]O[/][#64748b] to open · [/][bold cyan]E[/][#64748b] explain · [/][bold cyan]C[/][#64748b] copy · [/][bold cyan]Q[/][#64748b] quit[/]
"""


class WelcomePanel(Vertical):
    """Landing screen shown before a conversation is loaded."""

    DEFAULT_CSS = """
    WelcomePanel {
        height: 1fr;
        width: 100%;
        align: center middle;
        padding: 2 4;
        background: #0d1117;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(WELCOME_BODY, id="welcome-body", markup=True)


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
