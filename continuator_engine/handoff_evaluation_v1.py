"""Handoff evaluation pipeline — V9 vs V10 + handoff v3 (product baseline)."""
from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from checkpoint_state_v1 import build_checkpoint_state, render_briefing_from_checkpoint_state
from continuation_export_v1 import generate_continuation_briefing
from conversation_explainer_v1 import generate_conversation_explanation
from handoff_export_v1 import build_platform_exports
from handoff_generator_v3 import generate_handoff_briefing
from memory_model_v1 import all_transcript_chunks, compare_v9_v10, extract_all_chunks, format_copy_paste_outputs


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    s = str(value or "").strip()
    return [s] if s else []


def _populated(output: dict[str, Any], field: str) -> bool:
    value = output.get(field)
    if isinstance(value, list):
        return bool(value)
    return bool(str(value or "").strip())


def _word_count(text: str) -> int:
    return len((text or "").split())


def chunk_handoff_metrics(output: dict[str, Any], handoff: str) -> dict[str, Any]:
    parse_ok = bool(output.get("parse_ok", True)) and not output.get("error")
    return {
        "parse_ok": parse_ok,
        "handoff_words": _word_count(handoff),
        "objective_populated": _populated(output, "objective"),
        "active_problems_populated": _populated(output, "active_problems"),
        "continuation_context_populated": _populated(output, "continuation_context"),
        "current_state_populated": _populated(output, "current_state"),
        "completed_work_populated": _populated(output, "completed_work"),
    }


def aggregate_metrics(
    chunk_rows: list[dict[str, Any]],
    *,
    prefix: str,
) -> dict[str, Any]:
    n = len(chunk_rows) or 1
    parse_ok = sum(1 for r in chunk_rows if r.get(f"{prefix}_metrics", {}).get("parse_ok"))
    return {
        "chunk_count": len(chunk_rows),
        "parse_rate": round(parse_ok / n, 4),
        "parse_ok_count": parse_ok,
        "avg_handoff_words": round(
            sum(r.get(f"{prefix}_handoff_words", 0) for r in chunk_rows) / n, 1
        ),
        "objective_population_rate": round(
            sum(1 for r in chunk_rows if r.get(f"{prefix}_metrics", {}).get("objective_populated")) / n, 4
        ),
        "active_problems_population_rate": round(
            sum(1 for r in chunk_rows if r.get(f"{prefix}_metrics", {}).get("active_problems_populated")) / n, 4
        ),
        "continuation_context_population_rate": round(
            sum(
                1
                for r in chunk_rows
                if r.get(f"{prefix}_metrics", {}).get("continuation_context_populated")
            )
            / n,
            4,
        ),
    }


def _finalize_continuator(
    text: str,
    chunks: list[str],
    chunk_meta: dict[str, Any],
    v10_rows: list[dict[str, Any]],
    *,
    label: str,
    source: str,
    archetype: str,
) -> dict[str, Any]:
    chunk_results: list[dict[str, Any]] = []
    for row in v10_rows:
        v10_out = dict(row.get("output") or {})
        v10_out["memory_model"] = "v10"
        chunk_results.append(
            {
                "chunk_index": int(row["chunk_index"]),
                "input_chars": int(row["input_chars"]),
                "v10_output": v10_out,
                "v10_metrics": chunk_handoff_metrics(v10_out, ""),
                "v10_handoff_words": 0,
            }
        )

    v10_outputs: list[dict[str, Any]] = []
    for c in chunk_results:
        out = dict(c["v10_output"])
        out["chunk_index"] = int(c["chunk_index"])
        v10_outputs.append(out)

    checkpoint_state = build_checkpoint_state(
        v10_outputs,
        conversation=text,
        archetype=archetype,
        label=label,
        project=label,
        total_chunks=len(chunks),
    )
    continuation_briefing = render_briefing_from_checkpoint_state(checkpoint_state)
    conversation_explanation = generate_conversation_explanation(
        v10_outputs,
        conversation=text,
        label=label,
        archetype=archetype,
        total_chunks=len(chunks),
    )
    platform_exports = build_platform_exports(continuation_briefing, label=label)
    briefing_words = _word_count(continuation_briefing)
    explain_words = _word_count(conversation_explanation)

    return {
        "session_id": str(uuid.uuid4()),
        "label": label or f"continuator-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "source": source,
        "archetype": archetype,
        "product_baseline": "v10-050+repair+continuation_export_v2_frontier+explain_v1",
        "created_at": _utc_now(),
        "transcript_chars": len(text),
        "chunk_count": len(chunks),
        "chunking": chunk_meta,
        "checkpoint_state": dict(checkpoint_state),
        "continuation_briefing": continuation_briefing,
        "conversation_explanation": conversation_explanation,
        "briefing_words": briefing_words,
        "explain_words": explain_words,
        "exports": {
            "continuation_briefing": continuation_briefing,
            "explain": conversation_explanation,
            "v10_copy_paste": format_copy_paste_outputs(v10_rows),
            **platform_exports,
        },
        "metrics": {
            "v10": aggregate_metrics(chunk_results, prefix="v10"),
        },
        "v10_rows": v10_rows,
        "_chunks_text": chunks,
    }


def run_continuator_incremental(
    transcript: str,
    prior_pipeline: dict[str, Any],
    *,
    label: str = "",
    archetype: str = "mixed",
    use_chunk_ranker: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Re-chunk full transcript; reuse cached V10 outputs where chunk hash matches."""
    from checkpoint_merge_v1 import finalize_session_from_rows, incremental_extract_rows
    from memory_model_v1 import extract_chunks_at_indices

    text = (transcript or "").strip()
    chunks, chunk_meta = all_transcript_chunks(text)
    selected_indices = list(range(len(chunks)))
    rank_audit: dict[str, Any] = {}
    if use_chunk_ranker and chunks:
        from continuator_chunk_ranker_v1 import rank_chunks

        rank_audit = rank_chunks(chunks)
        selected_indices = list(rank_audit.get("selected_indices") or selected_indices)

    def extract_one(chunk_text: str, index: int, total: int) -> dict[str, Any]:
        rows = extract_chunks_at_indices(chunks, [index], "v10")
        return dict(rows[0].get("output") or {}) if rows else {}

    v10_rows, merge_stats = incremental_extract_rows(
        chunks,
        selected_indices,
        prior_pipeline,
        extract_fn=extract_one,
    )
    chunk_selection = {
        "strategy": rank_audit.get("selection_strategy", "full"),
        "selected_indices": selected_indices,
        "k": len(selected_indices),
        "total_chunks": len(chunks),
    }
    session = finalize_session_from_rows(
        text,
        chunks,
        chunk_meta,
        v10_rows,
        label=label,
        archetype=archetype,
        rank_audit=rank_audit,
        chunk_selection=chunk_selection,
    )
    session["rank_audit"] = rank_audit
    return session, merge_stats


def _stream_line(event_type: str, **payload: Any) -> str:
    return json.dumps({"type": event_type, **payload}, ensure_ascii=False) + "\n"


def iter_continuator_stream(
    transcript: str,
    *,
    label: str = "",
    archetype: str = "mixed",
    use_chunk_ranker: bool = True,
) -> Iterator[str]:
    """Yield NDJSON progress lines, ending with type=complete."""
    text = (transcript or "").strip()
    chunks, chunk_meta = all_transcript_chunks(text)
    total = len(chunks)
    yield _stream_line(
        "started",
        chunk_count=total,
        transcript_chars=len(text),
        chunking=chunk_meta,
    )

    selected_indices = list(range(total))
    rank_audit: dict[str, Any] = {}
    if use_chunk_ranker and total > 0:
        from continuator_chunk_ranker_v1 import default_k, rank_chunks

        rank_audit = rank_chunks(chunks)
        selected_indices = list(rank_audit.get("selected_indices") or selected_indices)
        yield _stream_line(
            "ranked",
            selected_indices=selected_indices,
            k=len(selected_indices),
            default_k=default_k(total),
            selection_strategy=rank_audit.get("selection_strategy"),
            rank_audit={
                "changepoints_pelt": rank_audit.get("changepoints_pelt"),
                "locked_indices": rank_audit.get("locked_indices"),
            },
        )

    v10_rows: list[dict[str, Any]] = []
    extract_total = len(selected_indices)

    from memory_extractor_v1 import set_memory_extractor_profile

    from memory_model_v1 import (
        _extract_chunk_in_current_context,
        default_profile_for_model,
        memory_model_context,
    )

    v10_profile = default_profile_for_model("v10")

    with memory_model_context("v10"):
        for pos, i in enumerate(selected_indices):
            # Re-apply profile each iteration — streaming resumes in a new ContextVar context.
            set_memory_extractor_profile(v10_profile)
            chunk_text = chunks[i]
            output = _extract_chunk_in_current_context(
                chunk_text,
                "v10",
                chunk_index=i + 1,
                chunk_total=total,
            )
            row = {
                "chunk_index": i,
                "input_chars": len(chunk_text),
                "output": output,
            }
            v10_rows.append(row)
            parse_ok = bool(output.get("parse_ok", True)) and not output.get("error")
            yield _stream_line(
                "progress",
                completed=pos + 1,
                total=extract_total,
                chunk_count=total,
                chunk_index=i,
                selected_indices=selected_indices,
                parse_ok=parse_ok,
            )

    yield _stream_line("building", message="Assembling continuation briefing…", chunk_count=total)

    result = _finalize_continuator(
        text,
        chunks,
        chunk_meta,
        v10_rows,
        label=label,
        source="continuator",
        archetype=archetype,
    )
    result["chunk_selection"] = {
        "strategy": rank_audit.get("selection_strategy", "full"),
        "selected_indices": selected_indices,
        "k": len(selected_indices),
        "total_chunks": total,
    }
    result["v10_rows"] = v10_rows
    result["rank_audit"] = rank_audit
    result["_chunks_text"] = chunks
    yield _stream_line("complete", result=result)


def run_continuator(
    transcript: str,
    *,
    label: str = "",
    source: str = "continuator",
    archetype: str = "mixed",
    use_chunk_ranker: bool = True,
) -> dict[str, Any]:
    """V10-only pipeline → single continuation briefing (AI Continuator product)."""
    text = (transcript or "").strip()
    chunks, chunk_meta = all_transcript_chunks(text)
    selected_indices = list(range(len(chunks)))
    rank_audit: dict[str, Any] = {}
    if use_chunk_ranker and chunks:
        from continuator_chunk_ranker_v1 import rank_chunks

        rank_audit = rank_chunks(chunks)
        selected_indices = list(rank_audit.get("selected_indices") or selected_indices)

    from memory_model_v1 import extract_chunks_at_indices

    v10_rows = extract_chunks_at_indices(chunks, selected_indices, "v10")
    result = _finalize_continuator(
        text,
        chunks,
        chunk_meta,
        v10_rows,
        label=label,
        source=source,
        archetype=archetype,
    )
    result["chunk_selection"] = {
        "strategy": rank_audit.get("selection_strategy", "full"),
        "selected_indices": selected_indices,
        "k": len(selected_indices),
        "total_chunks": len(chunks),
    }
    result["v10_rows"] = v10_rows
    result["rank_audit"] = rank_audit
    result["_chunks_text"] = chunks
    return result


def run_handoff_evaluation(
    transcript: str,
    *,
    label: str = "",
    source: str = "paste",
    archetype: str = "mixed",
) -> dict[str, Any]:
    """Run full V9 + V10 + handoff v3 pipeline on all chunks."""
    text = (transcript or "").strip()
    chunks, chunk_meta = all_transcript_chunks(text)
    compare = compare_v9_v10(text)

    v9_by_idx = {int(r["chunk_index"]): r for r in compare["v9"]["chunks"]}
    v10_by_idx = {int(r["chunk_index"]): r for r in compare["v10"]["chunks"]}

    chunk_results: list[dict[str, Any]] = []
    for i, chunk_text in enumerate(chunks):
        v9_row = v9_by_idx.get(i, {})
        v10_row = v10_by_idx.get(i, {})
        v9_out = dict(v9_row.get("output") or {})
        v10_out = dict(v10_row.get("output") or {})
        v10_out["memory_model"] = "v10"

        handoff_v3 = generate_handoff_briefing(v10_out, archetype=archetype) if v10_out else ""
        v9_handoff = ""
        if v9_out:
            from memory_model_v1 import build_ai_handoff

            v9_handoff = build_ai_handoff(v9_out, version="v1")

        v9_metrics = chunk_handoff_metrics(v9_out, v9_handoff)
        v10_metrics = chunk_handoff_metrics(v10_out, handoff_v3)

        excerpt = chunk_text[:400] + ("…" if len(chunk_text) > 400 else "")
        chunk_results.append(
            {
                "chunk_index": i,
                "input_chars": len(chunk_text),
                "raw_excerpt": excerpt,
                "v9_output": v9_out,
                "v10_output": v10_out,
                "v9_handoff": v9_handoff,
                "handoff_v3": handoff_v3,
                "handoff_v2": handoff_v3,  # backward compat for older clients
                "v9_metrics": v9_metrics,
                "v10_metrics": v10_metrics,
                "v9_handoff_words": v9_metrics["handoff_words"],
                "v10_handoff_words": v10_metrics["handoff_words"],
            }
        )

    handoff_all = _format_handoffs(chunk_results, key="handoff_v3")
    v10_outputs = [c["v10_output"] for c in chunk_results]
    continuation_briefing = generate_continuation_briefing(
        v10_outputs,
        conversation=text,
        archetype=archetype,
        label=label,
    )
    platform_exports = build_platform_exports(
        continuation_briefing or handoff_all,
        label=label,
    )

    return {
        "session_id": str(uuid.uuid4()),
        "label": label or f"eval-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "source": source,
        "archetype": archetype,
        "product_baseline": "v10-050+repair+handoff_v3",
        "created_at": _utc_now(),
        "transcript_chars": len(text),
        "chunk_count": len(chunks),
        "chunking": chunk_meta,
        "chunks": chunk_results,
        "exports": {
            "v9_copy_paste": compare["v9"]["copy_paste"],
            "v10_copy_paste": compare["v10"]["copy_paste"],
            "v10_handoff_all": handoff_all,
            "continuation_briefing": continuation_briefing,
            "v9_handoff_all": _format_handoffs(chunk_results, key="v9_handoff"),
            **platform_exports,
        },
        "metrics": {
            "v9": aggregate_metrics(chunk_results, prefix="v9"),
            "v10": aggregate_metrics(chunk_results, prefix="v10"),
        },
        "human_eval": {
            "usefulness": None,
            "could_continue": None,
            "notes": "",
            "reviewed_at": None,
        },
    }


def _format_handoffs(chunks: list[dict[str, Any]], *, key: str) -> str:
    if not chunks:
        return ""
    total = len(chunks)
    parts: list[str] = []
    for row in chunks:
        handoff = str(row.get(key) or row.get("handoff_v3") or "").strip()
        if not handoff:
            continue
        idx = int(row["chunk_index"]) + 1
        parts.append(f"=== CHUNK {idx}/{total} — HANDOFF ===")
        parts.append(handoff)
        parts.append("")
    return "\n".join(parts).strip()


def export_session_markdown(session: dict[str, Any]) -> str:
    """Markdown export for copy/paste into Claude/GPT."""
    lines = [
        f"# Handoff Evaluation — {session.get('label', 'session')}",
        "",
        f"- Created: {session.get('created_at', '')}",
        f"- Baseline: {session.get('product_baseline', 'v10-050+repair+handoff_v3')}",
        f"- Chunks: {session.get('chunk_count', 0)}",
        f"- V10 parse rate: {session.get('metrics', {}).get('v10', {}).get('parse_rate', 0):.0%}",
        "",
        "## V10 AI Handoff v3 (all chunks)",
        "",
        session.get("exports", {}).get("v10_handoff_all") or "(empty)",
        "",
        "## V10 Raw JSON (all chunks)",
        "",
        "```json",
        session.get("exports", {}).get("v10_copy_paste") or "",
        "```",
    ]
    return "\n".join(lines)
