"""MEMORY_MODEL feature flag — V9 vs V10 adapter selection and output serialization."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

_ROOT = Path(__file__).resolve().parent

CONTINUATION_FIELDS = (
    "objective",
    "current_state",
    "completed_work",
    "active_problems",
    "resolved_problems",
    "constraints",
    "continuation_context",
)


def get_memory_model() -> str:
    model = str(os.getenv("MEMORY_MODEL", "v9")).strip().lower()
    return model if model in {"v9", "v10"} else "v9"


def default_adapter_for_model(model: str | None = None) -> Path:
    from adapter_loader import ensure_adapter

    m = (model or get_memory_model()).lower()
    return ensure_adapter(m)


def default_profile_for_model(model: str | None = None) -> str:
    m = (model or get_memory_model()).lower()
    if m == "v10":
        return "fast"
    return (
        os.getenv("MEMORY_EXTRACTOR_PROFILE", "").strip()
        or os.getenv("MEMORY_EXTRACTOR_RECALL_PROFILE", "").strip()
        or "v8_production"
    )


def _listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    s = str(value).strip()
    return [s] if s else []


def record_to_extraction_output(record: Any) -> dict[str, Any]:
    """Unified extraction JSON for API responses (V9 + V10 fields)."""
    raw = dict(getattr(record, "raw", None) or {})
    goals = _listify(getattr(record, "current_goals", None) or raw.get("current_goals"))
    return {
        "topic": str(getattr(record, "topic", "") or raw.get("topic") or "").strip(),
        "summary": str(getattr(record, "summary", "") or raw.get("summary") or "").strip(),
        "important_facts": _listify(getattr(record, "important_facts", None) or raw.get("important_facts")),
        "goals": goals,
        "decisions": _listify(getattr(record, "decisions", None) or raw.get("decisions")),
        "next_steps": _listify(getattr(record, "next_steps", None) or raw.get("next_steps")),
        "open_questions": _listify(getattr(record, "open_questions", None) or raw.get("open_questions")),
        "objective": _listify(getattr(record, "objective", None) or raw.get("objective")),
        "current_state": str(getattr(record, "current_state", "") or raw.get("current_state") or "").strip(),
        "completed_work": _listify(getattr(record, "completed_work", None) or raw.get("completed_work")),
        "active_problems": _listify(getattr(record, "active_problems", None) or raw.get("active_problems")),
        "resolved_problems": _listify(getattr(record, "resolved_problems", None) or raw.get("resolved_problems")),
        "constraints": _listify(getattr(record, "constraints", None) or raw.get("constraints")),
        "continuation_context": str(
            getattr(record, "continuation_context", "") or raw.get("continuation_context") or ""
        ).strip(),
        "model_id": str(getattr(record, "model_id", "") or ""),
        "memory_model": str(raw.get("_memory_model") or get_memory_model()),
        "parse_ok": bool(getattr(record, "parse_ok", True)),
    }


def empty_extraction_output(*, memory_model: str = "v9") -> dict[str, Any]:
    return {
        "topic": "",
        "summary": "",
        "important_facts": [],
        "goals": [],
        "decisions": [],
        "next_steps": [],
        "open_questions": [],
        "objective": [],
        "current_state": "",
        "completed_work": [],
        "active_problems": [],
        "resolved_problems": [],
        "constraints": [],
        "continuation_context": "",
        "model_id": "",
        "memory_model": memory_model,
        "parse_ok": False,
    }


def build_ai_handoff(
    output: dict[str, Any],
    *,
    version: str = "auto",
    archetype: str | None = None,
) -> str:
    """Portable handoff block for a fresh LLM session."""
    if version == "v1":
        pass
    elif version == "v2":
        from handoff_generator_v2 import generate_handoff_briefing

        briefing = generate_handoff_briefing(output)
        if briefing:
            return briefing
    elif version in ("v3", "auto"):
        from handoff_generator_v3 import generate_handoff_briefing

        bucket = archetype or output.get("archetype") or output.get("bucket") or "mixed"
        briefing = generate_handoff_briefing(output, archetype=str(bucket))
        if briefing:
            return briefing

    lines = ["# AI Handoff Context", ""]
    if output.get("topic"):
        lines.extend([f"**Topic:** {output['topic']}", ""])
    if output.get("summary"):
        lines.extend([f"**Summary:** {output['summary']}", ""])
    if output.get("objective"):
        lines.append("**Objectives:**")
        lines.extend(f"- {item}" for item in output["objective"])
        lines.append("")
    if output.get("current_state"):
        lines.extend([f"**Current state:** {output['current_state']}", ""])
    for label, key in (
        ("Completed work", "completed_work"),
        ("Active problems", "active_problems"),
        ("Resolved problems", "resolved_problems"),
        ("Constraints", "constraints"),
    ):
        if output.get(key):
            lines.append(f"**{label}:**")
            lines.extend(f"- {item}" for item in output[key])
            lines.append("")
    if output.get("continuation_context"):
        lines.extend([f"**Continuation context:** {output['continuation_context']}", ""])
    if output.get("important_facts"):
        lines.append("**Important facts:**")
        lines.extend(f"- {item}" for item in output["important_facts"][:12])
        lines.append("")
    if output.get("goals"):
        lines.append("**Goals:**")
        lines.extend(f"- {item}" for item in output["goals"])
        lines.append("")
    if output.get("open_questions"):
        lines.append("**Open questions:**")
        lines.extend(f"- {item}" for item in output["open_questions"])
        lines.append("")
    if output.get("decisions"):
        lines.append("**Decisions:**")
        lines.extend(f"- {item}" for item in output["decisions"])
        lines.append("")
    if output.get("next_steps"):
        lines.append("**Next steps:**")
        lines.extend(f"- {item}" for item in output["next_steps"])
        lines.append("")
    return "\n".join(lines).strip()


def _restore_env(key: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value


@contextmanager
def memory_model_context(model: str) -> Iterator[None]:
    """Temporarily run extraction under a specific MEMORY_MODEL (clears MLX cache)."""
    from memory_extractor_v1 import (
        clear_mlx_model_cache,
        get_memory_extractor_profile,
        restore_memory_extractor_profile,
        set_memory_extractor_profile,
    )

    prev = {
        "MEMORY_MODEL": os.environ.get("MEMORY_MODEL"),
        "MEMORY_EXTRACTOR_ADAPTER_PATH": os.environ.get("MEMORY_EXTRACTOR_ADAPTER_PATH"),
        "MEMORY_EXTRACTOR_PROFILE": os.environ.get("MEMORY_EXTRACTOR_PROFILE"),
        "MEMORY_EXTRACTOR_MAX_NEW_TOKENS": os.environ.get("MEMORY_EXTRACTOR_MAX_NEW_TOKENS"),
    }
    prev_profile = get_memory_extractor_profile()
    profile = default_profile_for_model(model)
    try:
        os.environ["MEMORY_MODEL"] = model
        os.environ["MEMORY_EXTRACTOR_ADAPTER_PATH"] = str(default_adapter_for_model(model))
        os.environ["MEMORY_EXTRACTOR_PROFILE"] = profile
        if model == "v10":
            os.environ["MEMORY_EXTRACTOR_MAX_NEW_TOKENS"] = "1536"
        set_memory_extractor_profile(profile)
        clear_mlx_model_cache()
        yield
    finally:
        restore_memory_extractor_profile(prev_profile)
        for key, value in prev.items():
            _restore_env(key, value)
        clear_mlx_model_cache()


def extract_for_model(cluster_text: str, model: str) -> dict[str, Any]:
    from memory_extractor_v1 import MemoryExtractorError, _extract_single_chunk

    with memory_model_context(model):
        return _extract_chunk_in_current_context(cluster_text, model, chunk_index=1, chunk_total=1)


def _extract_chunk_in_current_context(
    cluster_text: str,
    model: str,
    *,
    chunk_index: int,
    chunk_total: int,
) -> dict[str, Any]:
    from memory_extractor_v1 import MemoryExtractorError, _extract_single_chunk

    try:
        record = _extract_single_chunk(
            cluster_text,
            chunk_index=chunk_index,
            chunk_total=chunk_total,
        )
        record.raw = {**dict(record.raw or {}), "_memory_model": model}
        return record_to_extraction_output(record)
    except MemoryExtractorError as exc:
        out = empty_extraction_output(memory_model=model)
        out["error"] = str(exc)
        return out


def all_transcript_chunks(transcript: str) -> tuple[list[str], dict[str, Any]]:
    from memory_extractor_v1 import _chunk_transcript_for_extraction

    text = (transcript or "").strip()
    chunks, audit = _chunk_transcript_for_extraction(text)
    if not chunks:
        return ([text[:6000]] if text else []), {
            "strategy": "fallback",
            "chunk_count": 1 if text else 0,
            "chunk_audit": audit,
        }
    return chunks, {
        "strategy": audit.get("strategy", "paragraph_chunk_overlap"),
        "chunk_count": len(chunks),
        "chunk_audit": audit,
    }


def extract_all_chunks(
    chunks: list[str],
    model: str,
    *,
    on_chunk_complete: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    indices = list(range(len(chunks)))
    return extract_chunks_at_indices(
        chunks,
        indices,
        model,
        on_chunk_complete=on_chunk_complete,
    )


def extract_chunks_at_indices(
    chunks: list[str],
    indices: list[int],
    model: str,
    *,
    on_chunk_complete: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """Extract V10/V9 only for the given source chunk indices (sorted ascending)."""
    total = len(chunks)
    picked = sorted({int(i) for i in indices if 0 <= int(i) < total})
    rows: list[dict[str, Any]] = []
    with memory_model_context(model):
        for pos, i in enumerate(picked):
            chunk_text = chunks[i]
            output = _extract_chunk_in_current_context(
                chunk_text,
                model,
                chunk_index=i + 1,
                chunk_total=total,
            )
            row = {
                "chunk_index": i,
                "input_chars": len(chunk_text),
                "output": output,
            }
            rows.append(row)
            if on_chunk_complete is not None:
                on_chunk_complete(pos + 1, len(picked), output)
    return rows


def format_copy_paste_outputs(chunk_rows: list[dict[str, Any]]) -> str:
    if not chunk_rows:
        return ""
    total = len(chunk_rows)
    parts: list[str] = []
    for row in chunk_rows:
        idx = int(row["chunk_index"]) + 1
        chars = int(row["input_chars"])
        parts.append(f"=== CHUNK {idx}/{total} ({chars} chars) ===")
        parts.append(json.dumps(row["output"], ensure_ascii=False, indent=2))
        parts.append("")
    return "\n".join(parts).strip()


def format_copy_paste_handoffs(chunk_rows: list[dict[str, Any]]) -> str:
    if not chunk_rows:
        return ""
    total = len(chunk_rows)
    parts: list[str] = []
    for row in chunk_rows:
        idx = int(row["chunk_index"]) + 1
        handoff = build_ai_handoff(row["output"])
        if not handoff:
            continue
        parts.append(f"=== CHUNK {idx}/{total} — AI HANDOFF ===")
        parts.append(handoff)
        parts.append("")
    return "\n".join(parts).strip()


def primary_cluster_slice(transcript: str) -> tuple[str, dict[str, Any]]:
    from memory_extractor_v1 import _chunk_transcript_for_extraction

    text = (transcript or "").strip()
    chunks, audit = _chunk_transcript_for_extraction(text)
    if not chunks:
        return text[:6000], {"strategy": "fallback", "input_chars": min(len(text), 6000)}
    best = max(chunks, key=len)
    return best, {
        "strategy": "largest_chunk",
        "cluster_count": len(chunks),
        "input_chars": len(best),
        "chunk_audit": audit,
    }


def compare_v9_v10(transcript: str) -> dict[str, Any]:
    chunks, chunk_meta = all_transcript_chunks(transcript)
    v9_chunks = extract_all_chunks(chunks, "v9")
    v10_chunks = extract_all_chunks(chunks, "v10")
    return {
        "v9": {
            "chunks": v9_chunks,
            "copy_paste": format_copy_paste_outputs(v9_chunks),
        },
        "v10": {
            "chunks": v10_chunks,
            "copy_paste": format_copy_paste_outputs(v10_chunks),
        },
        "ai_handoff": {
            "v9": format_copy_paste_handoffs(v9_chunks),
            "v10": format_copy_paste_handoffs(v10_chunks),
        },
        "meta": {
            "memory_model_default": get_memory_model(),
            "transcript_chars": len(transcript or ""),
            "chunk_count": len(chunks),
            "chunking": chunk_meta,
        },
    }
