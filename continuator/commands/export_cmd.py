"""continuator export — platform-specific handoff files."""
from __future__ import annotations

import argparse
from pathlib import Path

from continuator.console import ContinuatorConsole, sanitize_error
from continuator.pipeline import pick_export, run_continuation
from continuator.runtime import default_export_path, label_from_path, read_transcript

_TARGETS = ("claude", "chatgpt", "gemini", "markdown")


def register(subparsers: argparse._SubParsersAction, *, parent: argparse.ArgumentParser) -> None:
    parser = subparsers.add_parser(
        "export",
        parents=[parent],
        help="Export a conversation briefing formatted for another AI",
        description="Create a ready-to-paste handoff file for Claude, ChatGPT, Gemini, or Markdown.",
    )
    parser.add_argument(
        "conversation",
        help="Path to a conversation file (.txt, .json), or '-' for stdin",
    )
    parser.add_argument(
        "--for",
        dest="target",
        required=True,
        choices=_TARGETS,
        help="Export target platform",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="Output path (default: <name>_<target>.md)",
    )
    parser.add_argument(
        "--name",
        metavar="NAME",
        default="",
        help="Optional project name (defaults to the file name)",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    console = ContinuatorConsole(verbose=args.verbose, quiet=args.quiet)

    try:
        transcript = read_transcript(args.conversation)
    except (FileNotFoundError, ValueError) as exc:
        console.step_fail(str(exc))
        return 2

    label = label_from_path(args.conversation, args.name)
    out_path = Path(args.output) if args.output else default_export_path(args.conversation, args.target)

    if not args.quiet:
        console.show_header()

    try:
        result = run_continuation(
            transcript,
            label=label,
            console=None if args.quiet else console,
            verbose=args.verbose,
        )
    except Exception as exc:
        msg = sanitize_error(str(exc)) if not args.verbose else f"{type(exc).__name__}: {exc}"
        console.step_fail(msg)
        return 1

    payload = pick_export(result, args.target)
    if not payload:
        console.step_fail("Could not generate an export.")
        return 1

    out_path.write_text(payload.rstrip() + "\n", encoding="utf-8")
    if args.quiet:
        print(str(out_path))
    else:
        console.print_plain_success(f"Exported for {args.target} → {out_path.name}")
    return 0
