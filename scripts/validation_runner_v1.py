#!/usr/bin/env python3
"""Batch checkpoint + resume validation for product confidence testing.

Runs each transcript through full checkpoint extraction and cached resume,
writing per-session artifacts under validation_runs/<session_name>/.

Usage:
  python scripts/validation_runner_v1.py examples/
  python scripts/validation_runner_v1.py examples/ --output validation_runs --mock
  python scripts/validation_runner_v1.py --manifest validation_manifest.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "continuator_engine"

# Category labels for validation dashboard (see top_10_validation_sessions.md)
SESSION_CATEGORIES: dict[str, str] = {
    "neck": "tutorials",
    "gitissue": "coding",
    "jquery": "coding",
    "aman": "tutorials",
    "kafka": "tutorials",
    "kubernetes": "tutorials",
    "superlong": "coding",
    "pm": "project_planning",
    "github": "debugging",
    "journal": "research",
    "chat": "medical",
    "my-project": "medical",
}

CONTINUE_BY_CATEGORY: dict[str, str] = {
    "coding": "Continue the implementation. Propose the specific next code change and explain why.",
    "tutorials": "Continue as my tutor. What is the next lesson step and exercise?",
    "research": "Continue the research thread. What is the next question or experiment?",
    "project_planning": "Continue as PM. What is the next action for the team?",
    "debugging": "Continue debugging. What is the next diagnostic step?",
    "architecture": "Continue the design discussion. What decision or spike is next?",
}

PROMPT_PREAMBLE = """You are continuing an interrupted work session.

You have NO prior context except this checkpoint briefing.

{briefing}

Continue the work.
Do not ask for the original conversation.
"""

DEFAULT_CACHE = Path("/Users/acmmi/projects/memory/training_pipeline/evaluation/continuator_benchmark_v1_cache.jsonl")


def _setup_paths() -> None:
    for p in (str(ENGINE), str(ROOT)):
        if p not in sys.path:
            sys.path.insert(0, p)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(name: str) -> str:
    slug = re.sub(r"[^\w\-]+", "-", (name or "").strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:64] or "session"


def collect_transcript_files(directory: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in ("*.txt", "*.json"):
        files.extend(sorted(directory.rglob(pattern)))
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in files:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def load_manifest(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    sessions = raw.get("sessions") if isinstance(raw, dict) else raw
    if not isinstance(sessions, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for name, meta in sessions.items():
        if isinstance(meta, dict):
            out[str(name)] = {str(k): str(v) for k, v in meta.items()}
        elif isinstance(meta, str):
            out[str(name)] = {"path": meta}
    return out


def category_for(session_name: str, manifest: dict[str, dict[str, str]]) -> str:
    if session_name in manifest and manifest[session_name].get("category"):
        return manifest[session_name]["category"]
    return SESSION_CATEGORIES.get(session_name, "coding")


def continue_prompt_for(category: str) -> str:
    return CONTINUE_BY_CATEGORY.get(
        category,
        "Continue the work from where this briefing left off. Be specific and actionable.",
    )


def build_llm_prompt(briefing: str, category: str) -> str:
    body = PROMPT_PREAMBLE.format(briefing=briefing.strip())
    extra = continue_prompt_for(category)
    return f"{body}\n{extra}\n"


def read_transcript_path(path: Path) -> str:
    from continuator.runtime import read_transcript

    return read_transcript(str(path))


def export_cache_sessions(
    cache_path: Path,
    session_ids: list[str],
    output_dir: Path,
) -> list[Path]:
    """Write transcripts from benchmark cache jsonl for sessions not on disk."""
    if not cache_path.is_file():
        raise FileNotFoundError(f"benchmark cache not found: {cache_path}")
    wanted = {s.lower() for s in session_ids}
    found: dict[str, Path] = {}
    for line in cache_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        sid = str(entry.get("id") or "").lower()
        if sid not in wanted:
            continue
        text = (
            entry.get("transcript")
            or entry.get("full_text")
            or entry.get("conversation")
            or entry.get("text")
            or ""
        )
        if not str(text).strip():
            continue
        out = output_dir / f"{sid}.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(str(text).strip() + "\n", encoding="utf-8")
        found[sid] = out
    missing = wanted - set(found)
    if missing:
        print(f"warning: cache missing transcript for: {', '.join(sorted(missing))}", file=sys.stderr)
    return list(found.values())


def run_session(
    source_path: Path,
    *,
    output_root: Path,
    session_name: str,
    category: str,
    mock: bool,
) -> dict[str, Any]:
    from checkpoint_record_v2 import serialize_checkpoint
    from continuator.pipeline import briefing_quality
    from continuator.platform.extract import extract_full
    from continuator.platform.resume import resume_cached
    from continuator.runtime import ensure_runtime

    if mock:
        import os

        os.environ["MEMORY_EXTRACTOR_BACKEND"] = "mock"

    ensure_runtime()
    transcript = read_transcript_path(source_path)
    label = session_name

    ckpt_started = time.perf_counter()
    record, session = extract_full(
        transcript,
        label=label,
        project=slugify(session_name),
        path=str(source_path.resolve()),
        tier="full",
    )
    checkpoint_seconds = round(time.perf_counter() - ckpt_started, 3)

    resume_started = time.perf_counter()
    briefing = resume_cached(record, fmt="briefing")
    resume_ms = round((time.perf_counter() - resume_started) * 1000.0, 1)

    session_dir = output_root / slugify(session_name)
    session_dir.mkdir(parents=True, exist_ok=True)

    (session_dir / "checkpoint.yaml").write_text(
        serialize_checkpoint(record, fmt="yaml"),
        encoding="utf-8",
    )
    (session_dir / "resume.txt").write_text(briefing.rstrip() + "\n", encoding="utf-8")

    prompt = build_llm_prompt(briefing, category)
    for name in ("claude_prompt.txt", "chatgpt_prompt.txt", "gemini_prompt.txt"):
        (session_dir / name).write_text(prompt, encoding="utf-8")

    auto_quality = briefing_quality(briefing)
    state = dict(record.get("state") or {})
    metadata: dict[str, Any] = {
        "session_name": session_name,
        "source_path": str(source_path.resolve()),
        "category": category,
        "generated_at": _utc_now(),
        "checkpoint_id": record.get("id"),
        "checkpoint_seconds": checkpoint_seconds,
        "resume_ms": resume_ms,
        "transcript_chars": len(transcript),
        "chunk_count": session.get("chunk_count"),
        "briefing_words": len(briefing.split()),
        "auto_briefing_quality": auto_quality,
        "state_snapshot": {
            "next_action": state.get("next_action"),
            "objective_count": len(state.get("objective") or []),
            "completed_work_count": len(state.get("completed_work") or []),
            "active_problems_count": len(state.get("active_problems") or []),
        },
        "artifacts": {
            "checkpoint": "checkpoint.yaml",
            "resume": "resume.txt",
            "claude_prompt": "claude_prompt.txt",
            "chatgpt_prompt": "chatgpt_prompt.txt",
            "gemini_prompt": "gemini_prompt.txt",
        },
        "review_status": "pending",
        "checkpoint_quality": None,
        "resume_quality": None,
        "fresh_llm_continuation": None,
        "notes": "",
    }
    (session_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return metadata


def write_run_summary(output_root: Path, results: list[dict[str, Any]]) -> None:
    summary = {
        "generated_at": _utc_now(),
        "session_count": len(results),
        "sessions": [
            {
                "session_name": r["session_name"],
                "category": r["category"],
                "checkpoint_seconds": r["checkpoint_seconds"],
                "resume_ms": r["resume_ms"],
                "auto_briefing_quality": r.get("auto_briefing_quality", {}).get("verdict"),
                "output_dir": slugify(r["session_name"]),
            }
            for r in results
        ],
    }
    (output_root / "run_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def resolve_jobs(
    *,
    directory: Path | None,
    single_file: Path | None,
    manifest: dict[str, dict[str, str]],
    limit: int,
) -> list[tuple[Path, str, str]]:
    """Return list of (source_path, session_name, category)."""
    jobs: list[tuple[Path, str, str]] = []

    if single_file is not None:
        name = single_file.stem
        jobs.append((single_file, name, category_for(name, manifest)))

    if manifest:
        for name, meta in manifest.items():
            rel = meta.get("path", "")
            if not rel:
                continue
            source = Path(rel)
            if not source.is_absolute():
                source = (ROOT / source).resolve()
            if not source.is_file():
                print(f"warning: skipping missing manifest path: {rel}", file=sys.stderr)
                continue
            if any(j[0].resolve() == source.resolve() for j in jobs):
                continue
            jobs.append((source, name, category_for(name, manifest)))

    if directory is not None:
        for path in collect_transcript_files(directory):
            name = path.stem
            if any(j[0].resolve() == path.resolve() for j in jobs):
                continue
            jobs.append((path, name, category_for(name, manifest)))

    if limit > 0:
        jobs = jobs[:limit]
    return jobs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run checkpoint + resume validation on transcript files.",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default="",
        help="Transcript file or directory of .txt/.json files",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="validation_runs",
        help="Output root (default: validation_runs/)",
    )
    parser.add_argument(
        "--manifest",
        metavar="FILE",
        default="",
        help="JSON manifest of sessions (validation_manifest.json)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N sessions (0 = all)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use MEMORY_EXTRACTOR_BACKEND=mock (CI / wiring smoke)",
    )
    parser.add_argument(
        "--from-cache",
        nargs="*",
        metavar="ID",
        help="Export session IDs from benchmark cache into --output/corpus/ before run",
    )
    parser.add_argument(
        "--cache-path",
        default=str(DEFAULT_CACHE),
        help="Path to continuator_benchmark_v1_cache.jsonl",
    )
    args = parser.parse_args(argv)

    _setup_paths()
    output_root = Path(args.output)
    if not output_root.is_absolute():
        output_root = (ROOT / output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(ROOT / args.manifest) if args.manifest else load_manifest(ROOT / "validation_manifest.json")

    directory: Path | None = None
    single_file: Path | None = None
    if args.directory:
        target = Path(args.directory).expanduser()
        if not target.is_absolute():
            target = (ROOT / target).resolve()
        if target.is_file():
            single_file = target
        elif target.is_dir():
            directory = target
        else:
            print(f"error: not a file or directory: {target}", file=sys.stderr)
            return 2

    if args.from_cache:
        corpus_dir = output_root / "corpus"
        try:
            export_cache_sessions(Path(args.cache_path), list(args.from_cache), corpus_dir)
        except FileNotFoundError as exc:
            print(f"warning: {exc}", file=sys.stderr)
        if directory is None and corpus_dir.is_dir():
            directory = corpus_dir

    jobs = resolve_jobs(
        directory=directory,
        single_file=single_file,
        manifest=manifest,
        limit=args.limit,
    )
    if not jobs:
        print("error: no transcript files found", file=sys.stderr)
        return 2

    results: list[dict[str, Any]] = []
    failures = 0
    for source_path, session_name, category in jobs:
        print(f"→ {session_name} ({category}) …", file=sys.stderr)
        try:
            meta = run_session(
                source_path,
                output_root=output_root,
                session_name=session_name,
                category=category,
                mock=args.mock,
            )
            results.append(meta)
            q = meta.get("auto_briefing_quality", {}).get("verdict", "?")
            print(
                f"  ok  checkpoint={meta['checkpoint_seconds']}s resume={meta['resume_ms']}ms quality={q}",
                file=sys.stderr,
            )
        except Exception as exc:
            failures += 1
            print(f"  fail {session_name}: {exc}", file=sys.stderr)

    if results:
        write_run_summary(output_root, results)

    print(f"\nWrote {len(results)} session(s) to {output_root}", file=sys.stderr)
    return 1 if failures and not results else (1 if failures else 0)


if __name__ == "__main__":
    raise SystemExit(main())
