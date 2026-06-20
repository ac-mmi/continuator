"""continuator benchmark — batch evaluation over a folder."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from continuator.console import ContinuatorConsole, sanitize_error
from continuator.pipeline import briefing_quality, pick_export, run_continuation
from continuator.runtime import ensure_runtime, read_transcript


def _collect_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in ("*.txt", "*.json"):
        files.extend(sorted(root.rglob(pattern)))
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in files:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def register(subparsers: argparse._SubParsersAction, *, parent: argparse.ArgumentParser) -> None:
    parser = subparsers.add_parser(
        "benchmark",
        parents=[parent],
        help="Run continuation on every conversation in a folder",
        description="Batch-evaluate .txt and .json conversations and summarize quality.",
    )
    parser.add_argument(
        "directory",
        help="Folder containing conversation files",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Process at most N files (0 = all)",
    )
    parser.add_argument(
        "--report",
        metavar="FILE",
        help="Write JSON report to FILE",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    console = ContinuatorConsole(verbose=args.verbose, quiet=args.quiet)
    root = Path(args.directory).expanduser()
    if not root.is_dir():
        console.step_fail(f"Not a directory: {root.name}")
        return 2

    files = _collect_files(root)
    if args.limit and args.limit > 0:
        files = files[: args.limit]
    if not files:
        console.step_fail(f"No conversations found in {root.name}")
        return 2

    ensure_runtime()
    if not args.quiet:
        console.show_header()
        console.say(f"[bold]Benchmark[/bold] — {len(files)} conversation(s)")

    rows: list[list[str]] = []
    report_rows: list[dict] = []
    failures = 0

    for i, path in enumerate(files, 1):
        rel = path.name
        if not args.quiet:
            console.step_work(f"[{i}/{len(files)}] {rel}")
        try:
            transcript = read_transcript(str(path))
            result = run_continuation(
                transcript,
                label=path.stem,
                console=None,
                verbose=args.verbose,
            )
            briefing = pick_export(result, "briefing")
            quality = briefing_quality(briefing)
            runtime = float(result.get("_runtime_seconds") or 0)
            selection = result.get("chunk_selection") or {}
            rows.append(
                [
                    rel,
                    str(selection.get("total_chunks") or "?"),
                    str(quality["words"]),
                    quality["verdict"],
                    f"{runtime:.1f}s",
                ]
            )
            report_rows.append(
                {
                    "file": str(path),
                    "name": rel,
                    "chunk_count": selection.get("total_chunks"),
                    "selected_k": selection.get("k"),
                    "briefing_words": quality["words"],
                    "verdict": quality["verdict"],
                    "runtime_seconds": runtime,
                    "issues": quality["issues"],
                }
            )
            if not args.quiet:
                console.step_ok(f"{rel} — {quality['verdict']} ({quality['words']} words)")
        except Exception as exc:
            failures += 1
            rows.append([rel, "—", "—", "error", "—"])
            report_rows.append({"file": str(path), "name": rel, "error": str(exc)})
            if not args.quiet:
                msg = sanitize_error(str(exc)) if not args.verbose else str(exc)
                console.step_fail(f"{rel} — {msg}")

    if not args.quiet:
        console.print_table("Summary", ["File", "Sections", "Words", "Quality", "Time"], rows)

    if args.report:
        Path(args.report).write_text(json.dumps(report_rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if not args.quiet:
            console.verbose_line(f"Report saved to {args.report}")

    return 1 if failures else 0
