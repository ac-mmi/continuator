"""Shared extract orchestration for CLI, serve, and benchmark."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal

from checkpoint_merge_v1 import (
    MERGE_STRATEGY,
    detect_transcript_delta,
    is_append_only,
    prior_transcript_from_record,
)
from checkpoint_record_v2 import build_record_from_session, hash_transcript
from checkpoint_store_v2 import save_checkpoint

Tier = Literal["minimal", "standard", "full"]


def _source_meta(
    transcript: str,
    *,
    path: str = "",
    message: str = "",
    kind: str = "file",
) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": path,
        "platform": "unknown",
        "conversation_id": "",
        "sha256": hash_transcript(transcript),
        "char_count": len(transcript),
        "message_count": 0,
        "transcript_snapshot": transcript,
        "transcript": transcript,
        "message": message,
    }


def extract_full(
    transcript: str,
    *,
    label: str = "",
    project: str = "",
    path: str = "",
    message: str = "",
    tier: Tier = "full",
    use_chunk_ranker: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Full V10 extract → v2 CheckpointRecord."""
    from continuator.model_prep import prepare_extraction
    from handoff_evaluation_v1 import run_continuator

    prepare_extraction()
    started = time.perf_counter()
    session = run_continuator(
        transcript,
        label=label,
        archetype="mixed",
        use_chunk_ranker=use_chunk_ranker,
    )
    session["_runtime_seconds"] = round(time.perf_counter() - started, 2)
    proj = project or label or "conversation"
    record = build_record_from_session(
        session,
        source_meta=_source_meta(transcript, path=path, message=message),
        project=proj,
        label=label,
        tier=tier,
    )
    return record, session


def extract_incremental(
    transcript: str,
    prior: dict[str, Any],
    *,
    label: str = "",
    project: str = "",
    path: str = "",
    message: str = "",
    tier: Tier = "full",
    use_chunk_ranker: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Append-only incremental extract → merged v2 record."""
    prior_text = prior_transcript_from_record(prior)
    if not is_append_only(prior_text, transcript):
        raise ValueError(
            "Transcript changed non-append-only; run full checkpoint or resume --refresh"
        )

    from continuator.model_prep import prepare_extraction
    from handoff_evaluation_v1 import run_continuator_incremental

    prepare_extraction()
    started = time.perf_counter()
    pipeline = dict(prior.get("pipeline") or {})
    session, merge_stats = run_continuator_incremental(
        transcript,
        pipeline,
        label=label or str(prior.get("label") or ""),
        use_chunk_ranker=use_chunk_ranker,
    )
    session["_runtime_seconds"] = round(time.perf_counter() - started, 2)
    delta_text = detect_transcript_delta(prior_text, transcript)
    proj = project or str(prior.get("project") or label or "conversation")
    parent_created = str(prior.get("created_at") or "")
    record = build_record_from_session(
        session,
        source_meta=_source_meta(transcript, path=path or str(prior.get("source", {}).get("path") or ""), message=message),
        project=proj,
        label=label or str(prior.get("label") or proj),
        tier=tier,
        parent_created_at=parent_created or None,
        lineage={
            "parent_id": str(prior.get("id") or ""),
            "merge_strategy": MERGE_STRATEGY,
            "delta": {
                "chars_added": len(delta_text),
                "chunks_extracted": list(merge_stats.get("chunks_extracted") or []),
                "chunks_reused": list(merge_stats.get("chunks_reused") or []),
            },
        },
    )
    return record, session


def run_incremental_update(
    transcript: str,
    prior: dict[str, Any],
    *,
    label: str = "",
    project: str = "",
    path: str = "",
    message: str = "",
    tier: Tier = "full",
    output: Path | None = None,
) -> Path:
    record, _session = extract_incremental(
        transcript,
        prior,
        label=label,
        project=project,
        path=path,
        message=message,
        tier=tier,
    )
    return save_checkpoint(record, path=output)


def run_full_checkpoint(
    transcript: str,
    *,
    label: str = "",
    project: str = "",
    path: str = "",
    message: str = "",
    tier: Tier = "full",
    output: Path | None = None,
) -> Path:
    record, _session = extract_full(
        transcript,
        label=label,
        project=project,
        path=path,
        message=message,
        tier=tier,
    )
    return save_checkpoint(record, path=output)
