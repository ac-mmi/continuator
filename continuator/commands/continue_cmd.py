"""continuator continue — default product experience."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from continuator.console import ContinuatorConsole, sanitize_error
from continuator.pipeline import pick_export, run_continuation
from continuator.runtime import label_from_path, read_transcript


def register(subparsers: argparse._SubParsersAction, *, parent: argparse.ArgumentParser) -> None:
    parser = subparsers.add_parser(
        "continue",
        parents=[parent],
        help="Generate a continuation briefing from a conversation",
        description="Turn a long conversation into a structured briefing another AI can continue from.",
    )
    parser.add_argument(
        "conversation",
        help="Path to a conversation file (.txt, .json), or '-' for stdin",
    )
    parser.add_argument(
        "--name",
        metavar="NAME",
        default="",
        help="Optional project name (defaults to the file name)",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="Write briefing to FILE instead of stdout",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full session JSON (power users)",
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

    if not args.quiet and not args.json:
        console.show_header()

    try:
        result = run_continuation(
            transcript,
            label=label,
            console=None if args.quiet or args.json else console,
            verbose=args.verbose,
        )
    except Exception as exc:
        msg = sanitize_error(str(exc)) if not args.verbose else f"{type(exc).__name__}: {exc}"
        console.step_fail(msg)
        return 1

    if args.json:
        payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            Path(args.output).write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0

    briefing = pick_export(result, "briefing")
    if not briefing:
        console.step_fail("Could not generate a continuation briefing.")
        return 1

    if args.output:
        Path(args.output).write_text(briefing + "\n", encoding="utf-8")
        if not args.quiet:
            console.print_plain_success(f"Saved briefing to {Path(args.output).name}")
    else:
        display = label or str(result.get("label") or "")
        console.stream_briefing(briefing, display_label=display)
        console.prompt_handoff_actions(
            briefing=briefing,
            result=result,
            conversation_path=args.conversation,
        )

    return 0
