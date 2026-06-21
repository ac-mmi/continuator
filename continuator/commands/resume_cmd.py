"""continuator resume — render cached checkpoint exports without V10."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from continuator.console import ContinuatorConsole, sanitize_error
from continuator.platform.resume import load_and_resume
from continuator.runtime import label_from_path, read_transcript


def register(subparsers: argparse._SubParsersAction, *, parent: argparse.ArgumentParser) -> None:
    parser = subparsers.add_parser(
        "resume",
        parents=[parent],
        help="Resume from a saved checkpoint (cached briefing, no model load)",
        description=(
            "Load a checkpoint and print a cached export (default: continuation briefing). "
            "Does not load the V10 model unless --refresh is used."
        ),
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="",
        help="Checkpoint file, source transcript path, or omit for .continuator/checkpoint.yaml",
    )
    parser.add_argument(
        "--format",
        dest="export_format",
        choices=("briefing", "explain", "state", "claude", "chatgpt", "gemini", "markdown"),
        default="briefing",
        help="Which cached export to print (default: briefing)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-run full V10 extraction from source transcript and update checkpoint",
    )
    parser.add_argument(
        "--name",
        metavar="NAME",
        default="",
        help="Project name for legacy checkpoint lookup",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="Write output to FILE instead of stdout",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    console = ContinuatorConsole(verbose=args.verbose, quiet=args.quiet)

    transcript: str | None = None
    target = (args.target or "").strip()
    project = ""
    if target and not args.refresh:
        p = Path(target).expanduser()
        if p.is_file() and p.suffix.lower() in (".txt", ".json"):
            try:
                transcript = read_transcript(target)
            except (FileNotFoundError, ValueError):
                pass
    if args.name:
        from continuator.checkpoint_yaml import slugify_project

        project = slugify_project(args.name)
    elif target:
        p = Path(target).expanduser()
        if p.is_file() and p.suffix.lower() in (".txt", ".json"):
            project = label_from_path(target, args.name)

    if args.refresh and target:
        try:
            transcript = read_transcript(target)
        except (FileNotFoundError, ValueError) as exc:
            console.step_fail(str(exc))
            return 2

    ckpt_target = target if target and Path(target).expanduser().suffix.lower() in (".yaml", ".yml", ".json") else None
    if not ckpt_target and target and not transcript:
        ckpt_target = target

    resume_label = label_from_path(target, args.name) if target and transcript else ""

    try:
        text, record, elapsed_ms = load_and_resume(
            target=ckpt_target,
            project=project or None,
            fmt=args.export_format,
            refresh=args.refresh,
            transcript=transcript,
            label=resume_label,
            output=Path(args.output) if args.output and args.refresh else None,
        )
    except (FileNotFoundError, ValueError) as exc:
        console.step_fail(sanitize_error(str(exc)) if not args.verbose else str(exc))
        return 2
    except Exception as exc:
        msg = sanitize_error(str(exc)) if not args.verbose else f"{type(exc).__name__}: {exc}"
        console.step_fail(msg)
        return 1

    if args.output and not args.refresh:
        Path(args.output).write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
        if args.quiet:
            print(Path(args.output).resolve())
        elif not args.quiet:
            console.print_plain_success(f"Saved to {Path(args.output).name}")
        return 0

    if args.quiet:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
    else:
        if args.verbose:
            console.say(f"[dim]resume: {elapsed_ms:.0f}ms (cached)[/dim]")
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")

    return 0
