"""continuator explain — retrospective conversation summary from V10."""
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
        "explain",
        parents=[parent],
        help="Explain what happened in a conversation (retrospective summary)",
        description=(
            "Generate a retrospective explanation of a conversation using existing V10 "
            "extraction — no retraining. Answers: what happened throughout this conversation?"
        ),
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
        help="Write explanation to FILE instead of stdout",
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

    explanation = pick_export(result, "explain")
    if not explanation:
        console.step_fail("Could not generate a conversation explanation.")
        return 1

    if args.output:
        Path(args.output).write_text(explanation + "\n", encoding="utf-8")
        if not args.quiet:
            console.print_plain_success(f"Saved explanation to {Path(args.output).name}")
    else:
        if args.quiet:
            sys.stdout.write(explanation.rstrip() + "\n")
        else:
            console.say("[bold]Conversation explanation[/bold]")
            console.console.print()
            console.console.print(explanation.rstrip())
            console.console.print()

    return 0
