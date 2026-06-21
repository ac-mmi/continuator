"""continuator benchmark-incremental — full vs update parity harness."""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from continuator.checkpoint_yaml import slugify_project
from continuator.console import ContinuatorConsole, sanitize_error
from continuator.pipeline import briefing_quality
from continuator.platform.extract import extract_full, extract_incremental
from continuator.platform.resume import resume_cached
from continuator.runtime import ensure_runtime, label_from_path, read_transcript


def append_transcript(base: str, suffix: str) -> str:
    return base.rstrip() + "\n\n" + suffix.strip()


def _growth_suffix(text: str, ratio: float = 0.2) -> str:
    t = (text or "").strip()
    if not t:
        return "Additional follow-up messages appended for incremental benchmark."
    n = max(1, int(len(t) * ratio))
    return t[-n:]


def state_parity(base: dict, inc: dict) -> dict[str, float]:
    from checkpoint_merge_v1 import state_field_jaccard

    return state_field_jaccard(dict(base.get("state") or {}), dict(inc.get("state") or {}))


def _next_action_match(a: str, b: str) -> bool:
    aa = (a or "").strip().lower()
    bb = (b or "").strip().lower()
    if not aa or not bb:
        return aa == bb
    if aa == bb:
        return True
    words_a = set(aa.split())
    words_b = set(bb.split())
    overlap = len(words_a & words_b) / max(len(words_a | words_b), 1)
    return overlap >= 0.95


def register(subparsers: argparse._SubParsersAction, *, parent: argparse.ArgumentParser) -> None:
    parser = subparsers.add_parser(
        "benchmark-incremental",
        parents=[parent],
        help="Compare full vs incremental checkpoint speed and quality",
        description="Run full/incremental checkpoint parity benchmark on conversation files.",
    )
    parser.add_argument(
        "directory",
        help="Folder containing conversation files",
    )
    parser.add_argument(
        "--report",
        metavar="FILE",
        help="Write JSON report to FILE",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Process at most N files (0 = all)",
    )
    parser.set_defaults(handler=run)


def _collect_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in ("*.txt", "*.json"):
        files.extend(sorted(root.rglob(pattern)))
    return list(dict.fromkeys(files))


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
        console.say(f"[bold]Incremental benchmark[/bold] — {len(files)} sample(s)")

    samples: list[dict] = []
    for i, path in enumerate(files, 1):
        rel = path.name
        if not args.quiet:
            console.step_work(f"[{i}/{len(files)}] {rel}")
        try:
            base_text = read_transcript(str(path))
            grown = append_transcript(base_text, _growth_suffix(base_text))
            label = label_from_path(str(path))
            project = slugify_project(label)

            t0 = time.perf_counter()
            r0, _ = extract_full(base_text, label=label, project=project, path=str(path), tier="full")
            t0_elapsed = time.perf_counter() - t0

            t1 = time.perf_counter()
            r1_full, _ = extract_full(grown, label=label, project=project, path=str(path), tier="full")
            t1_elapsed = time.perf_counter() - t1

            t2 = time.perf_counter()
            r2_inc, _ = extract_incremental(grown, r0, label=label, project=project, path=str(path), tier="full")
            t2_elapsed = time.perf_counter() - t2

            q_full = briefing_quality(str(r1_full.get("cached_exports", {}).get("briefing") or ""))
            q_inc = briefing_quality(str(r2_inc.get("cached_exports", {}).get("briefing") or ""))
            quality_ratio = (q_inc["score"] / max(q_full["score"], 1)) if q_full["score"] else 1.0

            parity = state_parity(r1_full, r2_inc)
            na_match = _next_action_match(
                str(r1_full.get("state", {}).get("next_action") or ""),
                str(r2_inc.get("state", {}).get("next_action") or ""),
            )

            resume_start = time.perf_counter()
            resume_cached(r2_inc, fmt="briefing")
            resume_ms = (time.perf_counter() - resume_start) * 1000.0

            delta = dict(r2_inc.get("lineage", {}).get("delta") or {})
            lora_inc = len(delta.get("chunks_extracted") or [])
            lora_full = len(r1_full.get("pipeline", {}).get("chunk_extractions") or [])

            speedup = t1_elapsed / max(t2_elapsed, 0.001)
            verdict = "pass"
            if speedup < 3.0 and t1_elapsed > 0.5:
                verdict = "fail"
            if quality_ratio < 0.95:
                verdict = "fail"
            if resume_ms >= 500:
                verdict = "fail"

            samples.append(
                {
                    "name": rel,
                    "baseline_seconds": round(t0_elapsed, 3),
                    "full_seconds": round(t1_elapsed, 3),
                    "incremental_seconds": round(t2_elapsed, 3),
                    "speedup": round(speedup, 2),
                    "lora_calls_full": lora_full,
                    "lora_calls_incremental": lora_inc,
                    "quality_ratio": round(quality_ratio, 3),
                    "state_parity": parity,
                    "next_action_match": na_match,
                    "resume_ms": round(resume_ms, 1),
                    "verdict": verdict,
                }
            )
            if not args.quiet:
                console.step_ok(f"{rel}: speedup={speedup:.1f}x quality={quality_ratio:.0%} {verdict}")
        except Exception as exc:
            msg = sanitize_error(str(exc)) if not args.verbose else f"{type(exc).__name__}: {exc}"
            console.step_fail(f"{rel}: {msg}")
            samples.append({"name": rel, "verdict": "error", "error": msg})

    pass_count = sum(1 for s in samples if s.get("verdict") == "pass")
    speedups = [s["speedup"] for s in samples if "speedup" in s]
    qualities = [s["quality_ratio"] for s in samples if "quality_ratio" in s]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "samples": samples,
        "summary": {
            "pass_count": pass_count,
            "total": len(samples),
            "avg_speedup": round(sum(speedups) / len(speedups), 2) if speedups else 0.0,
            "avg_quality_ratio": round(sum(qualities) / len(qualities), 3) if qualities else 0.0,
        },
    }

    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if not args.quiet:
        console.say(
            f"[bold]Summary[/bold]: {pass_count}/{len(samples)} passed "
            f"(avg speedup {report['summary']['avg_speedup']}x, "
            f"quality {report['summary']['avg_quality_ratio']:.0%})"
        )

    return 0 if pass_count == len(samples) and samples else 1
