"""Continuator product CLI."""
from __future__ import annotations

import argparse
import sys

from continuator import __version__
from continuator.commands import (
    benchmark_cmd,
    benchmark_incremental_cmd,
    checkpoint_cmd,
    continue_cmd,
    explain_cmd,
    export_cmd,
    inspect_cmd,
    resume_cmd,
    serve_cmd,
)
from continuator.silence import configure_silence

_SUBCOMMANDS = frozenset(
    {"continue", "explain", "export", "inspect", "benchmark", "benchmark-incremental", "checkpoint", "resume", "serve"}
)


def _shared_parent() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show technical details (models, timings, section selection)",
    )
    parent.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Minimal output (briefing or file path only)",
    )
    return parent


def build_parser() -> argparse.ArgumentParser:
    parent = _shared_parent()
    parser = argparse.ArgumentParser(
        prog="continuator",
        description=(
            "Turn a long conversation into a continuation briefing for another AI.\n\n"
            "Paste the briefing into Claude, ChatGPT, or Gemini to pick up where you left off."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  continuator continue chat.txt\n"
            "  continuator checkpoint chat.txt\n"
            "  continuator explain chat.txt\n"
            "  continuator export chat.txt --for claude\n"
            "  continuator inspect chat.txt --verbose\n"
            "  continuator benchmark samples/\n"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"continuator {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    continue_cmd.register(subparsers, parent=parent)
    checkpoint_cmd.register(subparsers, parent=parent)
    explain_cmd.register(subparsers, parent=parent)
    export_cmd.register(subparsers, parent=parent)
    inspect_cmd.register(subparsers, parent=parent)
    benchmark_cmd.register(subparsers, parent=parent)
    benchmark_incremental_cmd.register(subparsers, parent=parent)
    resume_cmd.register(subparsers, parent=parent)
    serve_cmd.register(subparsers, parent=parent)
    return parser


def main(argv: list[str] | None = None) -> int:
    raw = list(argv if argv is not None else sys.argv[1:])
    configure_silence(verbose=any(x in raw for x in ("--verbose", "-v")))

    # Default: Textual TUI when no subcommand is given.
    if not raw or raw[0] not in _SUBCOMMANDS:
        from continuator.tui import run_tui

        return int(run_tui(raw))

    parser = build_parser()
    args = parser.parse_args(raw)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return int(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
