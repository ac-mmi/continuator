"""Incremental checkpoint merge — frontier_wins_v1 via build_checkpoint_state."""
from __future__ import annotations

import hashlib
from typing import Any

from checkpoint_record_v2 import normalize_transcript
from checkpoint_state_v1 import build_checkpoint_state, render_briefing_from_checkpoint_state
from conversation_explainer_v1 import generate_conversation_explanation
from handoff_export_v1 import build_platform_exports

MERGE_STRATEGY = "frontier_wins_v1"


def chunk_content_hash(chunk_text: str) -> str:
    return hashlib.sha256((chunk_text or "").encode("utf-8")).hexdigest()[:16]


def is_append_only(prior_text: str, new_text: str) -> bool:
    p = normalize_transcript(prior_text)
    n = normalize_transcript(new_text)
    if not p:
        return bool(n)
    return n.startswith(p) and len(n) > len(p)


def detect_transcript_delta(prior_text: str, new_text: str) -> str:
    p = normalize_transcript(prior_text)
    n = normalize_transcript(new_text)
    if n.startswith(p):
        return n[len(p) :].lstrip()
    return n


def prior_transcript_from_record(prior: dict[str, Any]) -> str:
    source = dict(prior.get("source") or {})
    snap = str(source.get("transcript_snapshot") or "").strip()
    if snap:
        return snap
    path = str(source.get("path") or "").strip()
    if path and path not in ("-", "stdin") and path != "":
        from pathlib import Path

        p = Path(path).expanduser()
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    return ""


def cached_extractions_by_index(pipeline: dict[str, Any]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for row in pipeline.get("chunk_extractions") or []:
        idx = int(row.get("chunk_index", 0))
        out[idx] = dict(row)
    return out


def merge_v10_outputs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_idx: dict[int, dict[str, Any]] = {}
    for row in rows:
        idx = int(row.get("chunk_index", 0))
        by_idx[idx] = {
            "chunk_index": idx,
            "input_chars": int(row.get("input_chars") or 0),
            "output": dict(row.get("output") or {}),
        }
    return [by_idx[i] for i in sorted(by_idx)]


def incremental_extract_rows(
    chunks: list[str],
    selected_indices: list[int],
    prior_pipeline: dict[str, Any] | None,
    *,
    extract_fn,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Extract only chunks with new/changed content. extract_fn(chunk_text, index, total) -> output dict."""
    cached = cached_extractions_by_index(prior_pipeline or {})
    rows: list[dict[str, Any]] = []
    stats = {"chunks_reused": [], "chunks_extracted": []}
    total = len(chunks)

    for i in sorted({int(x) for x in selected_indices if 0 <= int(x) < total}):
        chunk_text = chunks[i]
        h = chunk_content_hash(chunk_text)
        prior_row = cached.get(i)
        if prior_row and str(prior_row.get("content_hash") or "") == h:
            output = dict(prior_row.get("output") or {})
            stats["chunks_reused"].append(i)
        else:
            output = extract_fn(chunk_text, i, total)
            stats["chunks_extracted"].append(i)
        rows.append(
            {
                "chunk_index": i,
                "input_chars": len(chunk_text),
                "output": output,
            }
        )
    return rows, stats


def finalize_session_from_rows(
    transcript: str,
    chunks: list[str],
    chunk_meta: dict[str, Any],
    v10_rows: list[dict[str, Any]],
    *,
    label: str,
    archetype: str,
    rank_audit: dict[str, Any],
    chunk_selection: dict[str, Any],
    runtime_seconds: float = 0.0,
) -> dict[str, Any]:
    """Build session dict matching run_continuator output using merged rows."""
    v10_outputs: list[dict[str, Any]] = []
    for row in v10_rows:
        out = dict(row.get("output") or {})
        out["chunk_index"] = int(row["chunk_index"])
        v10_outputs.append(out)

    checkpoint_state = build_checkpoint_state(
        v10_outputs,
        conversation=transcript,
        archetype=archetype,
        label=label,
        project=label,
        total_chunks=len(chunks),
    )
    continuation_briefing = render_briefing_from_checkpoint_state(checkpoint_state)
    conversation_explanation = generate_conversation_explanation(
        v10_outputs,
        conversation=transcript,
        label=label,
        archetype=archetype,
        total_chunks=len(chunks),
    )
    platform_exports = build_platform_exports(continuation_briefing, label=label)

    from handoff_evaluation_v1 import _utc_now, aggregate_metrics, chunk_handoff_metrics

    chunk_results = []
    for row in v10_rows:
        v10_out = dict(row.get("output") or {})
        chunk_results.append(
            {
                "chunk_index": int(row["chunk_index"]),
                "v10_metrics": chunk_handoff_metrics(v10_out, ""),
            }
        )

    return {
        "label": label,
        "archetype": archetype,
        "product_baseline": "v10-050+repair+continuation_export_v2_frontier+explain_v1",
        "created_at": _utc_now(),
        "transcript_chars": len(transcript),
        "chunk_count": len(chunks),
        "chunking": chunk_meta,
        "chunk_selection": chunk_selection,
        "rank_audit": rank_audit,
        "v10_rows": v10_rows,
        "_chunks_text": chunks,
        "checkpoint_state": dict(checkpoint_state),
        "continuation_briefing": continuation_briefing,
        "conversation_explanation": conversation_explanation,
        "briefing_words": len(continuation_briefing.split()),
        "explain_words": len(conversation_explanation.split()),
        "exports": {
            "continuation_briefing": continuation_briefing,
            "explain": conversation_explanation,
            **platform_exports,
        },
        "metrics": {"v10": aggregate_metrics(
            [{"v10_metrics": chunk_handoff_metrics(dict(r.get("output") or {}), "")} for r in v10_rows],
            prefix="v10",
        )},
        "_runtime_seconds": runtime_seconds,
    }


def state_field_jaccard(base_state: dict[str, Any], inc_state: dict[str, Any]) -> dict[str, float]:
    def jaccard_lists(a: list, b: list) -> float:
        sa = {str(x).strip().lower() for x in a if str(x).strip()}
        sb = {str(x).strip().lower() for x in b if str(x).strip()}
        if not sa and not sb:
            return 1.0
        return len(sa & sb) / max(len(sa | sb), 1)

    return {
        "completed_work": jaccard_lists(base_state.get("completed_work") or [], inc_state.get("completed_work") or []),
        "active_problems": jaccard_lists(
            base_state.get("active_problems") or [], inc_state.get("active_problems") or []
        ),
        "constraints": jaccard_lists(base_state.get("constraints") or [], inc_state.get("constraints") or []),
    }


__all__ = [
    "MERGE_STRATEGY",
    "cached_extractions_by_index",
    "chunk_content_hash",
    "detect_transcript_delta",
    "finalize_session_from_rows",
    "incremental_extract_rows",
    "is_append_only",
    "merge_v10_outputs",
    "prior_transcript_from_record",
    "state_field_jaccard",
]
