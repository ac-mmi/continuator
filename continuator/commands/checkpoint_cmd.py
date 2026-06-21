"""continuator checkpoint — v2 structured checkpoint save/update."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from checkpoint_record_v2 import serialize_checkpoint
from checkpoint_store_v2 import find_checkpoint_for_update, resolve_checkpoint_path

from continuator.checkpoint_yaml import slugify_project
from continuator.console import ContinuatorConsole, sanitize_error
from continuator.platform.extract import extract_full, extract_incremental
from continuator.runtime import ensure_runtime, label_from_path, read_transcript


def register(subparsers: argparse._SubParsersAction, *, parent: argparse.ArgumentParser) -> None:
    parser = subparsers.add_parser(
        "checkpoint",
        parents=[parent],
        help="Save structured checkpoint to .continuator/checkpoint.yaml",
        description=(
            "Run the continuation pipeline and write a v2 checkpoint with cached exports. "
            "Use --update for append-only incremental updates."
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
        help="Project name (default: filename stem)",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Incremental update when transcript grew append-only since last checkpoint",
    )
    parser.add_argument(
        "--message",
        metavar="MSG",
        default="",
        help="Optional checkpoint message",
    )
    parser.add_argument(
        "--minimal",
        action="store_true",
        help="State + project only (no cached_exports)",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help="Output checkpoint path (default: .continuator/checkpoint.yaml)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print v2 checkpoint JSON envelope to stdout",
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
    project = slugify_project(label or "conversation")
    tier = "minimal" if args.minimal else "full"
    out_path = Path(args.output).expanduser() if args.output else resolve_checkpoint_path(project)

    if not args.quiet and not args.json:
        console.show_header()

    ensure_runtime()

    try:
        src_path = str(Path(args.conversation).resolve()) if args.conversation not in ("-", "stdin") else args.conversation
        if args.update:
            prior = find_checkpoint_for_update(project)
            if prior:
                if args.minimal:
                    console.step_fail("--minimal is incompatible with --update")
                    return 2
                record, _session = extract_incremental(
                    transcript,
                    prior,
                    label=label,
                    project=project,
                    path=src_path,
                    message=args.message,
                    tier=tier,
                )
                saved = out_path
                from checkpoint_store_v2 import save_checkpoint

                saved = save_checkpoint(record, path=out_path)
            else:
                record, _session = extract_full(
                    transcript,
                    label=label,
                    project=project,
                    path=src_path,
                    message=args.message,
                    tier=tier,
                )
                from checkpoint_store_v2 import save_checkpoint

                saved = save_checkpoint(record, path=out_path)
        else:
            record, _session = extract_full(
                transcript,
                label=label,
                project=project,
                path=src_path,
                message=args.message,
                tier=tier,
            )
            from checkpoint_store_v2 import save_checkpoint

            saved = save_checkpoint(record, path=out_path)
    except ValueError as exc:
        console.step_fail(str(exc))
        return 2
    except Exception as exc:
        msg = sanitize_error(str(exc)) if not args.verbose else f"{type(exc).__name__}: {exc}"
        console.step_fail(msg)
        return 1

    if args.json:
        payload = serialize_checkpoint(record, fmt="json")
        if args.output:
            Path(args.output).write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0

    resolved = saved.resolve()
    if args.quiet:
        print(resolved)
    else:
        stats = dict(record.get("stats") or {})
        console.print_plain_success("Checkpoint saved")
        console.print_plain_success(f"  project: {project}")
        console.print_plain_success(f"  path:    {resolved}")
        console.print_plain_success(f"  id:      {record.get('id', '')}")
        if stats:
            console.print_plain_success(
                f"  briefing: {stats.get('briefing_words', 0)} words, "
                f"{stats.get('runtime_seconds', 0)}s"
            )

    return 0
