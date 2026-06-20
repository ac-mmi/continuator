"""continuator inspect — conversation structure and selection audit."""
from __future__ import annotations

import argparse
import json
import sys

from continuator.console import ContinuatorConsole, sanitize_error
from continuator.pipeline import inspect_conversation, pick_export, run_continuation
from continuator.runtime import read_transcript


def register(subparsers: argparse._SubParsersAction, *, parent: argparse.ArgumentParser) -> None:
    parser = subparsers.add_parser(
        "inspect",
        parents=[parent],
        help="Inspect how a conversation will be processed",
        description="Show section count, focus areas, and optional full-run timing.",
    )
    parser.add_argument(
        "conversation",
        help="Path to a conversation file (.txt, .json), or '-' for stdin",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Also run full continuation (includes end-to-end runtime)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    console = ContinuatorConsole(verbose=args.verbose, quiet=args.quiet)

    try:
        transcript = read_transcript(args.conversation)
    except (FileNotFoundError, ValueError) as exc:
        console.step_fail(str(exc))
        return 2

    audit = inspect_conversation(transcript, verbose=args.verbose)
    full_result = None
    if args.full:
        try:
            full_result = run_continuation(
                transcript,
                console=None if args.quiet or args.json else console,
                verbose=args.verbose,
            )
            if full_result:
                full_result["continuation_briefing"] = pick_export(full_result, "briefing")
        except Exception as exc:
            msg = sanitize_error(str(exc)) if not args.verbose else f"{type(exc).__name__}: {exc}"
            console.step_fail(msg)
            return 1

    if args.json:
        payload = dict(audit)
        if full_result:
            payload["continuation"] = {
                "briefing_words": full_result.get("briefing_words"),
                "runtime_seconds": full_result.get("_runtime_seconds"),
            }
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return 0

    console.print_inspect(audit, full_result=full_result)
    return 0
