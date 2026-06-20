"""Textual TUI shell for Continuator."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Footer, Input, Label, ProgressBar, Static

from continuator.console import sanitize_error
from continuator.keyboard import copy_to_clipboard
from continuator.pipeline import pick_export, run_continuation
from continuator.runtime import default_export_path, label_from_path, read_transcript
from continuator.tui.briefing_render import briefing_markup, ordered_section_keys
from continuator.tui.console_adapter import TuiConsole
from continuator.tui.explain_render import explain_markup, explain_sections
from continuator.tui.widgets import ActivityFeed, InfoBar, MetadataPanel, WelcomePanel


def _default_browse_root() -> Path:
    cwd = Path.cwd()
    for candidate in (
        cwd / "examples",
        cwd / "fixtures",
        cwd,
        Path.home(),
    ):
        if candidate.is_dir():
            return candidate.resolve()
    return cwd.resolve()


def _format_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.1f} MB"


def _estimate_seconds(chunks: int, selected: int) -> str:
    base = max(selected, 1) * 12
    return f"~{max(base, 8)}s"


class OpenFileScreen(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    DEFAULT_CSS = """
    OpenFileScreen { align: center middle; }
    #open-dialog {
        width: 80; height: auto; max-height: 85%;
        padding: 1 2; background: #111827; border: solid #0891b2;
    }
    #open-hint { color: #94a3b8; margin-bottom: 1; }
    #open-dialog Input { margin: 1 0; }
    #open-dialog Button { margin-right: 1; }
    DirectoryTree { height: 18; margin: 1 0; border: solid #1e3a4a; }
    """

    def compose(self) -> ComposeResult:
        root = _default_browse_root()
        with Vertical(id="open-dialog"):
            yield Label("Open conversation file", id="open-title")
            yield Static(
                "Pick a .txt or .json file, or paste a path and press Enter.",
                id="open-hint",
            )
            yield Input(placeholder=str(root / "conversation.txt"), id="path-input")
            yield DirectoryTree(str(root), id="file-tree")
            with Horizontal():
                yield Button("Open", variant="primary", id="open-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#path-input", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(DirectoryTree.FileSelected)
    def on_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self.query_one("#path-input", Input).value = str(event.path)

    @on(Input.Submitted, "#path-input")
    def on_path_submitted(self) -> None:
        self.confirm_open()

    @on(Button.Pressed, "#open-btn")
    def confirm_open(self) -> None:
        path = self.query_one("#path-input", Input).value.strip()
        if not path:
            self.app.notify("Enter a file path or select a file in the tree", severity="warning")
            return
        candidate = Path(path).expanduser()
        if not candidate.is_file():
            self.app.notify(f"File not found: {candidate}", severity="error")
            return
        self.dismiss(str(candidate.resolve()))

    @on(Button.Pressed, "#cancel-btn")
    def cancel(self) -> None:
        self.dismiss(None)


class SaveFileScreen(ModalScreen[str | None]):
    DEFAULT_CSS = """
    SaveFileScreen { align: center middle; }
    #save-dialog {
        width: 70; height: auto; padding: 1 2;
        background: #111827; border: solid #0891b2;
    }
    #save-dialog Input { margin: 1 0; }
    #save-dialog Button { margin-right: 1; }
    """

    def __init__(self, default_path: str) -> None:
        super().__init__()
        self._default_path = default_path

    def compose(self) -> ComposeResult:
        with Vertical(id="save-dialog"):
            yield Label("Save briefing", id="save-title")
            yield Input(value=self._default_path, id="save-path")
            with Horizontal():
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#save-path", Input).focus()

    @on(Button.Pressed, "#save-btn")
    def confirm_save(self) -> None:
        path = self.query_one("#save-path", Input).value.strip()
        if path:
            self.dismiss(path)

    @on(Button.Pressed, "#cancel-btn")
    def cancel(self) -> None:
        self.dismiss(None)


class ContinuatorApp(App[None]):
    """Continuator product TUI — conversation intelligence layout."""

    CSS_PATH = Path(__file__).with_name("styles.tcss")
    TITLE = "Continuator"

    BINDINGS = [
        Binding("e", "toggle_explain", "Explain", priority=True),
        Binding("c", "copy_briefing", "Copy", priority=True),
        Binding("l", "copy_claude", "Claude", priority=True),
        Binding("g", "copy_chatgpt", "ChatGPT", priority=True),
        Binding("s", "save_briefing", "Save", priority=True),
        Binding("o", "open_file", "Open", priority=True),
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(
        self,
        *,
        conversation: str | None = None,
        name: str = "",
        verbose: bool = False,
    ) -> None:
        super().__init__()
        self.verbose = verbose
        self._explicit_name = name.strip()
        self._conversation_path = conversation
        self._conversation_label = ""
        self._briefing = ""
        self._explain = ""
        self._view_mode = "continue"
        self._result: dict[str, Any] | None = None
        self._active_worker = None
        self._file_bytes = 0
        self._chunk_total = 0
        self._selected_chunks: list[int] = []
        self._stream_handle = None

    def compose(self) -> ComposeResult:
        yield Static(" Ready — open a conversation to begin", id="status-bar")

        with Vertical(id="main-body"):
            yield WelcomePanel(id="welcome-view")

            with Vertical(id="workspace-view", classes="hidden"):
                yield InfoBar(id="info-bar")
                with Horizontal(id="workspace-split"):
                    with Vertical(id="side-panel"):
                        yield Label("ACTIVITY", classes="panel-heading")
                        yield ActivityFeed(id="activity-feed", markup=True)
                        yield MetadataPanel(id="metadata-panel", classes="hidden")

                    with Vertical(id="content-panel"):
                        yield Label("ANALYSIS", classes="panel-heading")
                        with Vertical(id="analysis-panel"):
                            yield Static("Waiting to start…", id="stage-label")
                            yield ProgressBar(total=100, show_eta=False, id="progress-bar")
                            yield Static("", id="rank-detail")

                        yield Label("CONTINUATION BRIEFING", id="content-heading", classes="panel-heading")
                        with VerticalScroll(id="briefing-scroll"):
                            yield Static(
                                "Briefing sections will stream in when ready…",
                                id="briefing-placeholder",
                            )
                            yield Static("", id="briefing-content", markup=True)

        with Horizontal(id="action-footer"):
            with Horizontal(id="export-group"):
                yield Button("Copy", id="btn-copy", disabled=True)
                yield Button("Explain", id="btn-explain", disabled=True)
                yield Button("Claude", id="btn-claude", disabled=True)
                yield Button("ChatGPT", id="btn-chatgpt", disabled=True)
                yield Button("Save", id="btn-save", disabled=True)
            yield Static("│", classes="footer-sep")
            with Horizontal(id="nav-group"):
                yield Button("Open", id="btn-open", variant="primary")
                yield Button("Quit", id="btn-quit")

        yield Footer()

    def on_mount(self) -> None:
        if self._conversation_path:
            self._start_pipeline(self._conversation_path)

    # ── View switching ────────────────────────────────────────────────────

    def _show_welcome(self) -> None:
        self.query_one("#welcome-view").remove_class("hidden")
        self.query_one("#workspace-view").add_class("hidden")
        self.set_status("Ready — open a conversation to begin")

    def _show_workspace(self) -> None:
        self.query_one("#welcome-view").add_class("hidden")
        self.query_one("#workspace-view").remove_class("hidden")

    def set_status(self, message: str) -> None:
        self.query_one("#status-bar", Static).update(f" {message}")

    # ── ProgressHost callbacks (main thread) ──────────────────────────────

    def post_step(self, message: str, *, progress: float | None = None) -> None:
        self.query_one("#stage-label", Static).update(message)
        if progress is not None:
            self.query_one("#progress-bar", ProgressBar).update(
                progress=int(max(0.0, min(1.0, progress)) * 100)
            )

    def post_status(self, message: str) -> None:
        self.set_status(message)

    def post_activity_done(self, message: str) -> None:
        self.query_one("#activity-feed", ActivityFeed).mark_done(message)

    def post_activity_active(self, message: str) -> None:
        self.query_one("#activity-feed", ActivityFeed).mark_active(message)

    def post_rank_detail(self, *, selected: list[int], total: int, strategy: str) -> None:
        self._selected_chunks = list(selected)
        nums = ", ".join(str(i + 1) for i in selected) or "all"
        detail = f"Selected: {nums} · {strategy} · {len(selected)} of {total} sections"
        self.query_one("#rank-detail", Static).update(detail)
        est = _estimate_seconds(total, len(selected))
        self.query_one("#info-bar", InfoBar).update_stats(estimate=est)

    def post_file_stats(self, *, chars: int, chunks: int) -> None:
        self._file_bytes = chars
        self._chunk_total = chunks
        path = Path(self._conversation_path or "")
        self.query_one("#info-bar", InfoBar).update_stats(
            filename=path.name or "—",
            size_label=_format_size(chars),
            chunks=str(chunks),
            estimate=_estimate_seconds(chunks, max(len(self._selected_chunks), 1)),
        )

    # ── Pipeline ──────────────────────────────────────────────────────────

    def _is_analysis_active(self) -> bool:
        worker = self._active_worker
        return worker is not None and not worker.is_finished

    def _release_worker(self) -> None:
        if self._active_worker is not None and self._active_worker.is_finished:
            self._active_worker = None

    def _reset_workspace(self, path: str, label: str) -> None:
        self._show_workspace()
        self._briefing = ""
        self._explain = ""
        self._view_mode = "continue"
        self._result = None
        self._selected_chunks = []
        feed = self.query_one("#activity-feed", ActivityFeed)
        feed.clear()
        feed.mark_pending("Parse conversation")
        feed.mark_pending("Rank chunks")
        feed.mark_pending("Extract continuation state")
        feed.mark_pending("Generate briefing")

        self.query_one("#metadata-panel").add_class("hidden")
        self.query_one("#rank-detail", Static).update("")
        self.query_one("#info-bar", InfoBar).update_stats(
            filename=Path(path).name,
            size_label="…",
            chunks="…",
            estimate="…",
        )
        self.query_one("#briefing-placeholder", Static).display = True
        self.query_one("#briefing-content", Static).update("")
        self.query_one("#briefing-content", Static).display = False
        self.post_step("Starting analysis…", progress=0.0)
        self.set_status(f"Loading {label or Path(path).stem}…")

    def _start_pipeline(self, path: str) -> None:
        self._release_worker()
        if self._is_analysis_active():
            self.notify("Analysis already in progress", severity="warning")
            return

        try:
            transcript = read_transcript(path)
        except (FileNotFoundError, ValueError) as exc:
            self.notify(str(exc), severity="error")
            return

        label = label_from_path(path, self._explicit_name)
        self._conversation_path = path
        self._conversation_label = label or Path(path).stem
        self._file_bytes = len(transcript.encode("utf-8"))
        self._reset_workspace(path, self._conversation_label)
        self._set_actions_enabled(False)
        self._active_worker = self._pipeline_worker(transcript, label, path)

    @work(thread=True, exclusive=True)
    def _pipeline_worker(self, transcript: str, label: str, path: str) -> None:
        try:
            console = TuiConsole(self)
            result = run_continuation(
                transcript,
                label=label,
                console=console,
                verbose=self.verbose,
            )
            briefing = pick_export(result, "briefing")
            if not briefing:
                raise RuntimeError("Could not generate a continuation briefing.")
            self.call_from_thread(self._on_pipeline_success, briefing, result, path)
        except Exception as exc:
            msg = sanitize_error(str(exc)) if not self.verbose else f"{type(exc).__name__}: {exc}"
            self.call_from_thread(self._on_pipeline_error, msg)
        finally:
            self.call_from_thread(self._release_worker)

    def _on_pipeline_success(self, briefing: str, result: dict[str, Any], path: str) -> None:
        self._briefing = briefing
        self._explain = pick_export(result, "explain")
        self._result = result
        self._conversation_path = path
        self._view_mode = "continue"
        self._update_metadata(result)
        self._stream_briefing(briefing)
        self._set_actions_enabled(True)
        self.set_status("Ready — Continue view · press E for Explain")
        self.notify("Briefing ready · press E to view explanation", timeout=4)

    def _on_pipeline_error(self, message: str) -> None:
        self.post_step(f"Error: {message}", progress=0.0)
        self.set_status(f"Error: {message}")
        self._set_actions_enabled(bool(self._briefing))
        self.notify(message, severity="error", timeout=8)

    def _update_metadata(self, result: dict[str, Any]) -> None:
        selection = dict(result.get("chunk_selection") or {})
        selected = selection.get("selected_indices") or []
        runtime = result.get("_runtime_seconds")
        words = result.get("briefing_words") or len(self._briefing.split())
        explain_words = result.get("explain_words") or len(self._explain.split())
        chunking = dict(result.get("chunking") or {})
        strategy = str(selection.get("selection_strategy") or chunking.get("strategy") or "default")

        lines = [
            f"Project: {self._conversation_label}",
            f"File: {Path(self._conversation_path or '').name}",
            f"Size: {_format_size(self._file_bytes)}",
            f"Sections: {result.get('chunk_count', self._chunk_total)}",
            f"Focus: {', '.join(str(i + 1) for i in selected) or 'all'}",
            f"Strategy: {strategy}",
            f"Briefing: {words} words",
            f"Explain: {explain_words} words",
        ]
        if runtime is not None:
            lines.append(f"Runtime: {runtime}s")

        panel = self.query_one("#metadata-panel", MetadataPanel)
        panel.remove_class("hidden")
        panel.update_metadata(lines)

    def _stream_briefing(self, briefing: str) -> None:
        if self._stream_handle is not None:
            self._stream_handle.stop()

        keys = ordered_section_keys(briefing, fallback_title=self._conversation_label)
        placeholder = self.query_one("#briefing-placeholder", Static)
        content = self.query_one("#briefing-content", Static)
        placeholder.display = True
        content.display = True
        content.update("")

        if not keys:
            content.update(briefing_markup(briefing, fallback_title=self._conversation_label))
            placeholder.display = False
            return

        revealed: set[str] = set()

        def reveal_next(index: int = 0) -> None:
            if index >= len(keys):
                placeholder.display = False
                self._stream_handle = None
                return
            revealed.add(keys[index])
            content.update(
                briefing_markup(
                    briefing,
                    fallback_title=self._conversation_label,
                    include_sections=set(revealed),
                )
            )
            self.query_one("#briefing-scroll", VerticalScroll).scroll_end(animate=False)
            self._stream_handle = self.set_timer(0.18, lambda: reveal_next(index + 1))

        reveal_next(0)

    def _active_payload(self) -> str:
        if self._view_mode == "explain":
            return self._explain
        return self._briefing

    def _render_content_view(self) -> None:
        heading = self.query_one("#content-heading", Label)
        placeholder = self.query_one("#briefing-placeholder", Static)
        content = self.query_one("#briefing-content", Static)

        if self._view_mode == "explain":
            heading.update("CONVERSATION EXPLANATION")
            placeholder.display = False
            content.display = True
            if self._explain:
                content.update(explain_markup(self._explain))
            else:
                content.update("[dim italic]Explanation not available.[/]")
            return

        heading.update("CONTINUATION BRIEFING")
        if self._briefing:
            placeholder.display = False
            content.update(briefing_markup(self._briefing, fallback_title=self._conversation_label))
        else:
            placeholder.display = True
            content.update("")

    def _stream_explain(self) -> None:
        if self._stream_handle is not None:
            self._stream_handle.stop()
        if not self._explain:
            self._render_content_view()
            return

        sections = explain_sections(self._explain)
        placeholder = self.query_one("#briefing-placeholder", Static)
        content = self.query_one("#briefing-content", Static)
        placeholder.display = True
        content.display = True
        content.update("")

        if not sections:
            content.update(explain_markup(self._explain))
            placeholder.display = False
            return

        revealed: list[str] = []

        def reveal_next(index: int = 0) -> None:
            if index >= len(sections):
                placeholder.display = False
                self._stream_handle = None
                return
            revealed.append(sections[index])
            partial_lines: list[str] = []
            for name in revealed:
                block = self._extract_explain_block(name)
                if block:
                    partial_lines.extend([name, "", block, ""])
            content.update(explain_markup("\n".join(partial_lines).strip()))
            self.query_one("#briefing-scroll", VerticalScroll).scroll_end(animate=False)
            self._stream_handle = self.set_timer(0.16, lambda: reveal_next(index + 1))

        reveal_next(0)

    def _extract_explain_block(self, section: str) -> str:
        lines = self._explain.splitlines()
        body: list[str] = []
        capture = False
        for raw in lines:
            stripped = raw.strip()
            if stripped == section:
                capture = True
                continue
            if capture and stripped in explain_sections(self._explain):
                break
            if capture and stripped:
                body.append(stripped)
        return "\n".join(body)

    def action_toggle_explain(self) -> None:
        if not self._explain and not self._briefing:
            self.notify("Load a conversation first", severity="warning")
            return
        if not self._explain:
            self.notify("Explanation not available for this session", severity="warning")
            return
        if self._view_mode == "continue":
            self._view_mode = "explain"
            self._stream_explain()
            self.set_status("Explain view — what happened in this conversation")
            self.query_one("#btn-explain", Button).add_class("-primary")
        else:
            self._view_mode = "continue"
            self._render_content_view()
            self.set_status("Continue view — handoff briefing for another AI")
            btn = self.query_one("#btn-explain", Button)
            btn.remove_class("-primary")

    def _set_actions_enabled(self, enabled: bool) -> None:
        for widget_id in ("btn-copy", "btn-explain", "btn-claude", "btn-chatgpt", "btn-save"):
            self.query_one(f"#{widget_id}", Button).disabled = not enabled

    # ── Clipboard / export ────────────────────────────────────────────────

    def _copy_payload(self, target: str) -> None:
        if not self._result:
            self.notify("No briefing to copy yet", severity="warning")
            return
        payload = pick_export(self._result, target)
        if not payload:
            self.notify(f"No {target} export available", severity="error")
            return
        if copy_to_clipboard(payload):
            labels = {"briefing": "Briefing", "claude": "Claude", "chatgpt": "ChatGPT"}
            self.notify(f"{labels.get(target, target)} copied", timeout=3)
        else:
            self.notify("Clipboard unavailable — use Save", severity="warning")

    def _save_payload(self, path: Path, payload: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload.rstrip() + "\n", encoding="utf-8")
        self.notify(f"Saved → {path.name}", timeout=4)

    def action_open_file(self) -> None:
        self._release_worker()
        if isinstance(self.screen, OpenFileScreen):
            self.screen.query_one("#path-input", Input).focus()
            return
        if self._is_analysis_active():
            self.notify("Analysis in progress — wait for it to finish", severity="warning")
            return

        def on_path(path: str | None) -> None:
            if path:
                self._start_pipeline(path)

        self.push_screen(OpenFileScreen(), on_path)

    def action_copy_briefing(self) -> None:
        payload = self._active_payload()
        if payload and copy_to_clipboard(payload):
            label = "Explanation copied" if self._view_mode == "explain" else "Briefing copied"
            self.notify(label, timeout=3)
        elif payload:
            self.notify("Clipboard unavailable", severity="warning")
        else:
            self._copy_payload("briefing")

    def action_copy_claude(self) -> None:
        self._copy_payload("claude")

    def action_copy_chatgpt(self) -> None:
        self._copy_payload("chatgpt")

    def action_save_briefing(self) -> None:
        payload = self._active_payload()
        if not payload:
            self.notify("Nothing to save yet", severity="warning")
            return
        suffix = "explain" if self._view_mode == "explain" else "markdown"
        default = str(default_export_path(self._conversation_path or "-", suffix)).replace(
            "_markdown.md", "_explain.md"
        )
        if self._view_mode == "explain" and not default.endswith("_explain.md"):
            default = default.replace(".md", "_explain.md")

        def on_path(path: str | None) -> None:
            if path:
                self._save_payload(Path(path).expanduser(), payload)

        self.push_screen(SaveFileScreen(default), on_path)

    @on(Button.Pressed, "#btn-open")
    def on_open_button(self) -> None:
        self.action_open_file()

    @on(Button.Pressed, "#btn-explain")
    def on_explain_button(self) -> None:
        self.action_toggle_explain()

    @on(Button.Pressed, "#btn-copy")
    def on_copy_button(self) -> None:
        self.action_copy_briefing()

    @on(Button.Pressed, "#btn-claude")
    def on_claude_button(self) -> None:
        self.action_copy_claude()

    @on(Button.Pressed, "#btn-chatgpt")
    def on_chatgpt_button(self) -> None:
        self.action_copy_chatgpt()

    @on(Button.Pressed, "#btn-save")
    def on_save_button(self) -> None:
        self.action_save_briefing()

    @on(Button.Pressed, "#btn-quit")
    def on_quit_button(self) -> None:
        self.exit()


def run_tui(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="continuator",
        description="Continuator TUI — turn a conversation into an AI handoff briefing.",
    )
    parser.add_argument("conversation", nargs="?", default=None)
    parser.add_argument("--name", metavar="NAME", default="")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    try:
        ContinuatorApp(
            conversation=args.conversation,
            name=args.name,
            verbose=args.verbose,
        ).run()
    except KeyboardInterrupt:
        return 130
    return 0
