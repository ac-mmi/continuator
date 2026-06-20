"""Pipeline progress callbacks for the Textual TUI (no extraction logic)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from continuator.silence import shield_libraries

if TYPE_CHECKING:
    from continuator.tui.app import ContinuatorApp


class ProgressHost(Protocol):
    verbose: bool

    def call_from_thread(self, callback, /, *args, **kwargs) -> None: ...

    def post_step(self, message: str, *, progress: float | None = None) -> None: ...

    def post_status(self, message: str) -> None: ...

    def post_activity_done(self, message: str) -> None: ...

    def post_activity_active(self, message: str) -> None: ...

    def post_rank_detail(
        self,
        *,
        selected: list[int],
        total: int,
        strategy: str,
    ) -> None: ...

    def post_file_stats(self, *, chars: int, chunks: int) -> None: ...


class TuiConsole:
    """Mirrors ContinuatorConsole pipeline hooks for the Textual app."""

    quiet = False

    def __init__(self, host: ProgressHost) -> None:
        self._host = host
        self.verbose = host.verbose
        self._progress_total = 1
        self._rank_logged = False

    def library_shield(self):
        return shield_libraries(verbose=self.verbose)

    def _call(self, method: str, *args, **kwargs) -> None:
        target = getattr(self._host, method)
        if callable(getattr(self._host, "call_from_thread", None)):
            self._host.call_from_thread(target, *args, **kwargs)
        else:
            target(*args, **kwargs)

    def _step(self, message: str, *, progress: float | None = None) -> None:
        self._call("post_step", message, progress=progress)

    def _status(self, message: str) -> None:
        self._call("post_status", message)

    def _done(self, message: str) -> None:
        self._call("post_activity_done", message)

    def _active(self, message: str) -> None:
        self._call("post_activity_active", message)

    def on_reading(self) -> None:
        self._active("Reading conversation")
        self._status("Reading conversation…")
        self._step("Reading conversation…", progress=0.02)

    def on_parsed(self, sections: int, chars: int) -> None:
        noun = "section" if sections == 1 else "sections"
        self._done(f"Parsed conversation ({sections} {noun})")
        self._active("Ranking chunks")
        self._status(f"Parsed {sections} {noun} · {chars:,} characters")
        self._call("post_file_stats", chars=chars, chunks=sections)
        self._step("Ranking conversation sections…", progress=0.08)

    def on_ranked(self, *, selected: list[int], total: int, strategy: str) -> None:
        self._progress_total = max(len(selected), 1)
        if not self._rank_logged:
            self._rank_logged = True
            nums = ", ".join(str(i + 1) for i in selected) or "all"
            self._done(f"Selected frontier chunks: {nums}")
            self._active("Extracting continuation state")
            self._call("post_rank_detail", selected=selected, total=total, strategy=strategy)
            detail = f"Strategy: {strategy} · focus {len(selected)} of {total}"
            self._status(detail)
            self._step("Extracting continuation state…", progress=0.12)

    def on_analyze_progress(self, done: int, total: int) -> None:
        extract_total = max(total, 1)
        self._progress_total = extract_total
        fraction = 0.12 + (0.78 * min(done, extract_total) / extract_total)
        self._status(f"Analyzing chunk {done}/{extract_total}")
        self._step(f"Extracting state — chunk {done}/{extract_total}", progress=fraction)

    def on_building(self) -> None:
        self._done("Extracted continuation state")
        self._active("Generating continuation briefing")
        self._status("Generating continuation briefing")
        self._step("Generating continuation briefing…", progress=0.94)

    def on_analysis_complete(self, *, seconds: float | None = None) -> None:
        self._done("Generated continuation briefing")
        message = "Ready for AI handoff"
        if self.verbose and seconds is not None:
            message = f"{message} · {seconds:.1f}s"
        self._status(message)
        self._step("Briefing complete", progress=1.0)
