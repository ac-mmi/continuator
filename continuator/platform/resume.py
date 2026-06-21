"""Resume from checkpoint without V10 (cached exports)."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from checkpoint_record_v2 import render_from_record
from checkpoint_store_v2 import load_checkpoint, resolve_read_path, save_checkpoint

FORMAT_ALIASES = {
    "briefing": "briefing",
    "explain": "explain",
    "claude": "claude",
    "chatgpt": "chatgpt",
    "gemini": "gemini",
    "markdown": "markdown",
    "state": "state",
}


def resolve_target(target: str | None, *, project: str | None = None, cwd: Path | None = None) -> Path:
    path = resolve_read_path(target, project=project, cwd=cwd)
    if path is None:
        raise FileNotFoundError("No checkpoint found; run continuator checkpoint first")
    return path


def resume_cached(
    record: dict[str, Any],
    *,
    fmt: str = "briefing",
) -> str:
    """Render export from checkpoint record without invoking V10."""
    key = FORMAT_ALIASES.get(fmt, fmt)
    return render_from_record(record, key)


def resume_with_refresh(
    record: dict[str, Any],
    transcript: str,
    *,
    label: str = "",
    project: str = "",
    path: str = "",
    output: Path | None = None,
) -> tuple[str, dict[str, Any]]:
    """Re-run full extract and overwrite checkpoint."""
    from continuator.platform.extract import extract_full

    proj = project or str(record.get("project") or label or "conversation")
    new_record, session = extract_full(
        transcript,
        label=label or str(record.get("label") or proj),
        project=proj,
        path=path or str(record.get("source", {}).get("path") or ""),
        tier="full",
    )
    save_checkpoint(new_record, path=output)
    text = resume_cached(new_record, fmt="briefing")
    return text, session


def load_and_resume(
    *,
    target: str | None = None,
    project: str | None = None,
    fmt: str = "briefing",
    refresh: bool = False,
    transcript: str | None = None,
    label: str = "",
    output: Path | None = None,
    cwd: Path | None = None,
) -> tuple[str, dict[str, Any], float]:
    """Load checkpoint and return (text, record, elapsed_ms)."""
    started = time.perf_counter()
    ckpt_path = resolve_target(target, project=project, cwd=cwd)
    record = load_checkpoint(ckpt_path)

    if record is None:
        raise FileNotFoundError(f"Could not load checkpoint: {ckpt_path}")

    if refresh:
        if not transcript:
            src = dict(record.get("source") or {})
            p = str(src.get("path") or "").strip()
            if p and p not in ("-", "stdin") and Path(p).expanduser().is_file():
                transcript = Path(p).expanduser().read_text(encoding="utf-8", errors="replace")
            elif str(src.get("transcript_snapshot") or "").strip():
                transcript = str(src["transcript_snapshot"])
            else:
                raise ValueError("No transcript for --refresh; pass source file or use checkpoint on a file path")
        text, _session = resume_with_refresh(
            record,
            transcript,
            label=label,
            project=str(record.get("project") or ""),
            path=str(record.get("source", {}).get("path") or ""),
            output=output or ckpt_path,
        )
        record = load_checkpoint(output or ckpt_path) or record
    else:
        text = resume_cached(record, fmt=fmt)

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return text, record, elapsed_ms
