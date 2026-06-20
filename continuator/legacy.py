"""Legacy argparse compatibility for scripts/run_continuator.py."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from continuator.console import ContinuatorConsole, sanitize_error
from continuator.pipeline import pick_export, run_continuation
from continuator.runtime import label_from_path, read_transcript


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Legacy continuator script (use `continuator continue` instead)")
    parser.add_argument("transcript")
    parser.add_argument("--label", default="")
    parser.add_argument("--archetype", default="mixed")
    parser.add_argument("--format", "-f", dest="export_format", default="briefing")
    parser.add_argument("-o", "--output")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--json-out")
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--quiet", "-q", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--no-ranker", action="store_true")
    return parser


def dispatch(argv: list[str] | None = None) -> int:
    print(
        "Note: scripts/run_continuator.py is legacy. Prefer: continuator continue FILE\n",
        file=sys.stderr,
    )
    args = _build_parser().parse_args(argv)
    console = ContinuatorConsole(verbose=args.verbose, quiet=args.quiet)

    try:
        transcript = read_transcript(args.transcript)
    except (FileNotFoundError, ValueError) as exc:
        console.step_fail(str(exc))
        return 2

    label = label_from_path(args.transcript, args.label)

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

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.json:
        payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            Path(args.output).write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0

    fmt = args.export_format if args.export_format != "briefing" else "briefing"
    payload = pick_export(result, fmt)
    if not payload:
        console.step_fail("Could not generate output.")
        return 1

    if args.output:
        Path(args.output).write_text(payload.rstrip() + "\n", encoding="utf-8")
        if not args.quiet:
            console.print_plain_success(f"Saved to {Path(args.output).name}")
    elif fmt == "briefing" and not args.quiet:
        display = (args.label or "").strip() or Path(args.transcript).stem if args.transcript != "-" else ""
        console.stream_briefing(payload, display_label=display)
        console.prompt_handoff_actions(
            briefing=payload,
            result=result,
            conversation_path=args.transcript,
        )
    else:
        sys.stdout.write(payload.rstrip() + "\n")
    return 0
