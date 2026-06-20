"""Rich terminal UI for the Continuator product CLI."""
from __future__ import annotations

import re
from typing import Any

from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.rule import Rule
from rich.status import Status
from rich.table import Table
from rich.text import Text

from continuator import theme as T
from continuator.keyboard import copy_to_clipboard, read_key
from continuator.runtime import default_export_path
from continuator.silence import configure_silence, real_stderr, real_stdout, shield_libraries

FOOTER = "Ready for AI handoff."

_SECTION_ORDER = (
    "Objective",
    "Current Position",
    "Completed Work",
    "Active Problems",
    "Constraints",
    "Next Action",
)
_SECTION_HEADER_LINES = frozenset(f"{name}:" for name in _SECTION_ORDER)


def _match_section_header(line: str) -> str | None:
    """True section header only when the whole line is e.g. ``Objective:``."""
    if line in _SECTION_HEADER_LINES:
        return line[:-1]
    return None


def _resolve_display_title(project: str, fallback: str) -> str:
    title = (project or "").strip()
    if title:
        return title
    fb = (fallback or "").strip()
    if fb.startswith("continuator-"):
        return "Conversation"
    return fb or "Conversation"


def _parse_briefing(
    text: str,
    *,
    fallback_title: str = "",
) -> tuple[str, str, dict[str, str]]:
    """Parse briefing markdown into project title, optional project body, and sections."""
    lines = (text or "").strip().splitlines()
    project_lines: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for raw in lines:
        line = raw.strip()
        if line.startswith("## PROJECT"):
            current = "__project__"
            continue

        header = _match_section_header(line)
        if header is not None:
            current = header
            sections.setdefault(current, [])
            continue

        if current == "__project__":
            if line:
                project_lines.append(line)
            continue

        if current and line:
            sections.setdefault(current, []).append(line)

    project_title = project_lines[0] if project_lines else ""
    project_body = "\n".join(project_lines[1:]).strip() if len(project_lines) > 1 else ""

    if not project_title.strip():
        project_title = _resolve_display_title("", fallback_title)

    rendered: dict[str, str] = {}
    for key, body_lines in sections.items():
        rendered[key] = "\n".join(body_lines).strip()
    return project_title, project_body, rendered


def _section_body(key: str, body: str) -> RenderableType:
    if not body or body.lower() in {"none identified.", "none identified"}:
        return Text("None", style=f"{T.MUTED} italic")

    if key in {"Completed Work", "Active Problems", "Constraints"}:
        items: list[RenderableType] = []
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            bullet = stripped[2:] if stripped.startswith("- ") else stripped.lstrip("•").strip()
            items.append(Text(f"• {bullet}"))
        return Group(*items) if items else Text(body)

    return Text(body, style="white")


def _briefing_section_blocks(text: str, *, fallback_title: str = "") -> list[list[RenderableType]]:
    project, project_body, sections = _parse_briefing(text, fallback_title=fallback_title)
    groups: list[list[RenderableType]] = []

    if project or project_body or "## PROJECT" in text or sections:
        project_group: list[RenderableType] = [
            Text("PROJECT", style=T.HEADING),
            Text(project, style=T.ACCENT),
        ]
        if project_body:
            project_group.append(Text(project_body))
        project_group.append(Text(""))
        groups.append(project_group)

    for key in _SECTION_ORDER:
        if key not in sections:
            continue
        body = sections.get(key, "")
        groups.append(
            [
                Text(key.upper(), style=T.HEADING),
                _section_body(key, body),
                Text(""),
            ]
        )

    if not groups:
        groups.append([Text(text)])

    return groups


def render_briefing_panel(text: str, *, fallback_title: str = "") -> Panel:
    blocks: list[RenderableType] = []
    for group in _briefing_section_blocks(text, fallback_title=fallback_title):
        blocks.extend(group)
    return _panel_from_blocks(blocks)


def _full_width_panel(content: RenderableType, *, padding: tuple[int, int] = (1, 2)) -> Panel:
    return Panel(
        content,
        border_style=T.PANEL_BORDER,
        padding=padding,
        expand=True,
    )


def _panel_from_blocks(blocks: list[RenderableType]) -> Panel:
    return _full_width_panel(Group(*blocks))


def render_branded_header() -> Panel:
    body = Group(
        Align.center(Text("AI CONTINUATOR", style=T.HEADER_TITLE)),
        Align.center(Text("Turn conversations into AI handoffs", style=T.HEADER_TAGLINE)),
    )
    return _full_width_panel(body, padding=(1, 2))


def render_action_footer() -> Panel:
    line = Text()
    line.append("[c]", style=T.ACTION_KEY)
    line.append(" Copy   ", style=T.ACTION_LABEL)
    line.append("[e]", style=T.ACTION_KEY)
    line.append(" Export   ", style=T.ACTION_LABEL)
    line.append("[q]", style=T.ACTION_KEY)
    line.append(" Quit", style=T.ACTION_LABEL)
    return _full_width_panel(Align.center(line), padding=(0, 2))


class ContinuatorConsole:
    """Product terminal session — unified full-width layout on interactive TTY."""

    def __init__(self, *, verbose: bool = False, quiet: bool = False) -> None:
        self.verbose = verbose
        self.quiet = quiet
        configure_silence(verbose=verbose)
        # Interactive UI uses one console so header, progress, briefing, and footer align.
        self.console = Console(file=real_stderr(), stderr=False, highlight=False)
        self._plain = Console(file=real_stdout(), stderr=False, highlight=False)
        self._progress: Progress | None = None
        self._task_id: int | None = None
        self._status: Status | None = None
        self._analyze_total = 0

    def _ui(self) -> Console:
        """Console for product UI (always aligned)."""
        return self.console if self._interactive() else self._plain

    def _interactive(self) -> bool:
        return not self.quiet and self.console.is_terminal

    def show_header(self) -> None:
        if self.quiet:
            return
        self.console.print()
        self.console.print(render_branded_header())
        self.console.print()

    def say(self, message: str, *, style: str = "") -> None:
        if self.quiet:
            return
        self.console.print(message, style=style or T.SUBHEADING)

    def step_ok(self, message: str) -> None:
        if self.quiet:
            return
        self.console.print(f"[{T.SUCCESS}]✓[/] {message}")

    def step_warn(self, message: str) -> None:
        if self.quiet:
            return
        self.console.print(f"[{T.WARN}]![/] {message}")

    def step_fail(self, message: str) -> None:
        self.console.print(f"[{T.ERROR}]✗[/] {message}")

    def verbose_line(self, message: str) -> None:
        if self.verbose and not self.quiet:
            self.console.print(f"[{T.MUTED}]{message}[/]")

    def _start_status(self, message: str) -> None:
        self._stop_status()
        if self.quiet:
            return
        self._status = self.console.status(
            f"[{T.STATUS_SPINNER}]{message}[/]",
            spinner="dots",
            spinner_style=T.STATUS_SPINNER,
        )
        self._status.start()

    def _stop_status(self) -> None:
        if self._status is not None:
            self._status.stop()
            self._status = None

    def on_reading(self) -> None:
        self._start_status("Reading conversation…")

    def on_parsed(self, sections: int, chars: int) -> None:
        self._stop_status()
        self.step_ok(f"{sections} section{'s' if sections != 1 else ''} detected")
        if self.verbose:
            self.verbose_line(f"{chars:,} characters")

    def on_ranked(self, *, selected: list[int], total: int, strategy: str) -> None:
        self._analyze_total = max(len(selected), 1)
        if not self.verbose:
            return
        nums = ", ".join(str(i + 1) for i in selected)
        self.verbose_line(f"Selection strategy: {strategy}")
        self.verbose_line(f"Focused sections: {nums} ({len(selected)} of {total})")

    def _ensure_progress(self, total: int) -> None:
        if self.quiet or self._progress is not None:
            return
        self._stop_status()
        self._analyze_total = max(total, 1)
        self._progress = Progress(
            TextColumn(f"[{T.STATUS_SPINNER}]{{task.description}}[/]"),
            BarColumn(
                bar_width=None,
                complete_style=T.PROGRESS_BAR_COMPLETE,
                finished_style=T.PROGRESS_BAR_COMPLETE,
                pulse_style=T.PROGRESS_BAR_PENDING,
            ),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=self.console,
            expand=True,
            transient=False,
        )
        self._progress.start()
        self._task_id = self._progress.add_task(
            "Building continuation state…",
            total=self._analyze_total,
        )

    def on_analyze_progress(self, done: int, total: int) -> None:
        if self.quiet:
            return
        extract_total = max(total, 1)
        self._ensure_progress(extract_total)
        if self._progress is not None and self._task_id is not None:
            self._progress.update(
                self._task_id,
                completed=min(done, extract_total),
                description="Building continuation state…",
            )

    def on_building(self) -> None:
        if self.quiet:
            return
        if self._progress is not None and self._task_id is not None:
            self._progress.update(
                self._task_id,
                completed=self._analyze_total,
                description="Generating continuation briefing…",
            )
        else:
            self._ensure_progress(1)
            if self._progress is not None and self._task_id is not None:
                self._progress.update(
                    self._task_id,
                    completed=1,
                    description="Generating continuation briefing…",
                )

    def on_analysis_complete(self, *, seconds: float | None = None) -> None:
        self._stop_status()
        if self._progress is not None and self._task_id is not None:
            self._progress.update(
                self._task_id,
                completed=self._analyze_total,
                description="Building continuation state…",
            )
        self._stop_progress()
        if self.verbose and seconds is not None and not self.quiet:
            self.verbose_line(f"Analysis finished in {seconds:.1f}s")

    def _stop_progress(self) -> None:
        if self._progress is not None:
            self._progress.stop()
            self._progress = None
            self._task_id = None

    def _print_handoff_footer(self, out: Console) -> None:
        out.print()
        out.print(Rule(title=FOOTER, style=T.FOOTER_READY, characters="─"))
        out.print()

    def stream_briefing(self, briefing: str, *, display_label: str = "") -> None:
        if self.quiet:
            self._plain.print(briefing.rstrip())
            return

        if not self._interactive():
            self._print_briefing_instant(briefing, out=self._plain, display_label=display_label)
            return

        out = self.console
        out.print()
        out.print(render_briefing_panel(briefing, fallback_title=display_label))
        self._print_handoff_footer(out)

    def prompt_handoff_actions(
        self,
        *,
        briefing: str,
        result: dict[str, Any],
        conversation_path: str,
    ) -> None:
        if not self._interactive():
            return

        from continuator.pipeline import pick_export

        out = self.console
        out.print()
        out.print(render_action_footer())

        while True:
            key = read_key()
            if key is None:
                break
            if key == "c":
                if copy_to_clipboard(briefing):
                    self.step_ok("Copied briefing to clipboard")
                else:
                    self.step_warn("Clipboard unavailable — use [e] Export instead")
            elif key == "e":
                path = default_export_path(conversation_path, "claude")
                payload = pick_export(result, "claude")
                path.write_text(payload.rstrip() + "\n", encoding="utf-8")
                self.step_ok(f"Exported for Claude → {path.name}")
            elif key in {"q", "\x1b"}:
                break
            else:
                self.step_warn(f"Unknown key '{key}' — try c, e, or q")
                continue

            out.print()
            out.print(render_action_footer())

    def print_briefing(self, briefing: str, *, to_stdout: bool = True, display_label: str = "") -> None:
        if self._interactive():
            self.stream_briefing(briefing, display_label=display_label)
            return
        self._print_briefing_instant(briefing, out=self._plain if to_stdout else self.console, display_label=display_label)

    def _print_briefing_instant(self, briefing: str, *, out: Console, display_label: str = "") -> None:
        if self.quiet:
            out.print(briefing.rstrip())
            return
        out.print()
        out.print(render_briefing_panel(briefing, fallback_title=display_label))
        out.print()
        self._print_handoff_footer(out)

    def print_plain_success(self, message: str) -> None:
        if self.quiet:
            return
        self.console.print()
        self.step_ok(message)
        self.console.print(Rule(title=FOOTER, style=T.FOOTER_READY, characters="─"))

    def print_table(self, title: str, headers: list[str], rows: list[list[str]]) -> None:
        if self.quiet:
            return
        table = Table(
            title=title,
            show_header=True,
            header_style=T.HEADING,
            border_style=T.BORDER,
            expand=True,
        )
        for h in headers:
            table.add_column(h)
        for row in rows:
            table.add_row(*row)
        self.console.print(table)

    def print_inspect(self, audit: dict[str, Any], *, full_result: dict[str, Any] | None = None) -> None:
        if self.quiet:
            return
        self.show_header()
        self.say("[bold]Conversation overview[/bold]")
        self.console.print()
        overview = Table(show_header=False, box=None, padding=(0, 2), expand=True)
        overview.add_row(Text("Characters", style=T.SUBHEADING), f"{audit['transcript_chars']:,}")
        overview.add_row(Text("Sections", style=T.SUBHEADING), str(audit["chunk_count"]))
        overview.add_row(Text("Inspect time", style=T.SUBHEADING), f"{audit['runtime_seconds']:.2f}s")
        self.console.print(overview)
        self.console.print()

        def fmt(indices: list[int]) -> str:
            return ", ".join(str(i + 1) for i in indices) if indices else "—"

        sel = audit["selected_indices"]
        self.say("[bold]Focus[/bold]")
        focus = Table(show_header=False, box=None, padding=(0, 2), expand=True)
        focus.add_row(Text("Selected", style=T.SUBHEADING), f"{fmt(sel)} ({len(sel)} total)")
        focus.add_row(Text("Recent", style=T.SUBHEADING), fmt(audit["frontier_indices"]))
        focus.add_row(Text("Recent focus", style=T.SUBHEADING), fmt(audit["frontier_selected"]))
        self.console.print(focus)

        if self.verbose:
            rank = audit.get("rank_audit") or {}
            scores = rank.get("candidate_scores") or {}
            if scores:
                self.console.print()
                self.say("[bold]Section scores[/bold]")
                rows = [
                    [str(int(k) + 1), f"{float(v):.3f}"]
                    for k, v in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:8]
                ]
                self.print_table("", ["Section", "Score"], rows)

        if full_result:
            words = full_result.get("briefing_words") or len(
                str(full_result.get("continuation_briefing") or "").split()
            )
            self.console.print()
            self.say("[bold]Full run[/bold]")
            run = Table(show_header=False, box=None, padding=(0, 2), expand=True)
            run.add_row(Text("Runtime", style=T.SUBHEADING), f"{full_result.get('_runtime_seconds', 0):.1f}s")
            run.add_row(Text("Briefing words", style=T.SUBHEADING), str(words))
            self.console.print(run)

        self.console.print()
        self.console.print(Rule(style=T.BORDER))

    def library_shield(self):
        return shield_libraries(verbose=self.verbose)


def sanitize_error(message: str) -> str:
    text = message
    text = re.sub(r"/[^\s:]+\.(safetensors|json|txt)", "[model]", text)
    text = re.sub(r"/Users/[^\s]+", "[path]", text)
    text = re.sub(r"(?i)(adapter|checkpoint|lora|mlx|transformers|huggingface)[^\s]*", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text or "Something went wrong. Try again with --verbose for details."
