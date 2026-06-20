"""AI Continuator — single continuation briefing from full conversation + all V10 chunks.

Produces ONE export for another LLM. Does not emit per-chunk handoffs.
Frozen inputs: V10-050 extraction fields only (no retraining, no relabeling).
"""
from __future__ import annotations

import re
from typing import Any

from handoff_generator_v2 import _clean_voice, _clean_voice_preserve_lines, _listify
from handoff_generator_v3 import (
    ARCHETYPE_ROLES,
    _ARCHETYPE_NEXT_FALLBACK,
    _clean_summary,
    _dedupe_sentences,
    _extract_next_from_text,
    _merge_position,
    _sentence_overlap,
    _split_sentences,
)

_AGGREGATE_LIST_KEYS = (
    "objective",
    "completed_work",
    "active_problems",
    "resolved_problems",
    "constraints",
)

_GOAL_KEYS = ("objective", "goals", "open_questions", "next_steps")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _aggregate_list_field(chunks: list[dict[str, Any]], field: str) -> list[str]:
    """Collect unique items across chunks in order; dedupe near-duplicates."""
    kept: list[str] = []
    for chunk in chunks:
        for raw in _listify(chunk.get(field)):
            cleaned = _clean_voice(str(raw))
            if not cleaned or len(cleaned) < 8:
                continue
            if any(_sentence_overlap(cleaned, prev) for prev in kept):
                continue
            kept.append(cleaned)
    return kept


def _terminal_chunk(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    if not chunks:
        return {}
    return chunks[-1]


def _terminal_position(final: dict[str, Any]) -> str:
    current = _clean_voice(str(final.get("current_state") or ""))
    continuation = _clean_voice(str(final.get("continuation_context") or ""))
    summary = _clean_summary(str(final.get("summary") or ""))
    position = _merge_position(current, continuation, summary)
    if position:
        return position
    topic = _clean_voice(str(final.get("topic") or ""))
    if topic:
        return f"The session covers {topic.rstrip('.')}."
    return ""


def _objective_text(chunks: list[dict[str, Any]], aggregated: list[str]) -> str:
    if aggregated:
        if len(aggregated) == 1:
            return aggregated[0]
        return "\n".join(f"- {item}" for item in aggregated[:12])
    final = _terminal_chunk(chunks)
    topic = _clean_voice(str(final.get("topic") or ""))
    if topic:
        return topic
    return "Continue the in-progress work from the current position."


def _continuation_tail(final: dict[str, Any]) -> str:
    continuation = _clean_voice(str(final.get("continuation_context") or ""))
    current = _clean_voice(str(final.get("current_state") or ""))
    if not continuation:
        return ""
    extracted = _extract_next_from_text(continuation)
    if extracted:
        return extracted
    if current:
        cur_norm = _normalize(current)
        ctx_norm = _normalize(continuation)
        if len(ctx_norm) > len(cur_norm) + 20 and cur_norm in ctx_norm:
            idx = continuation.lower().find(current.lower()[: min(len(current), 40)])
            if idx >= 0:
                tail = continuation[idx + len(current) :].strip(" ,.")
                if len(tail) > 15:
                    return tail[0].upper() + tail[1:] if tail else tail
    if len(continuation) > 30:
        sents = _split_sentences(continuation)
        if sents:
            return sents[-1]
    return continuation


def _derive_next_action(
    chunks: list[dict[str, Any]],
    *,
    position: str,
    archetype: str,
) -> str:
    """Priority: final-chunk active_problems → unresolved goals → continuation tail → fallback."""
    # 1. active_problems from final chunks (newest first)
    for chunk in reversed(chunks):
        for problem in reversed(_listify(chunk.get("active_problems"))):
            cleaned = _clean_voice(str(problem))
            if not cleaned:
                continue
            action = cleaned
            if not cleaned.lower().startswith(("resolve", "address", "fix", "answer")):
                action = f"Address: {cleaned}"
            if position and _sentence_overlap(action, position):
                continue
            return action.rstrip(".")

    # 2. unresolved goals from final chunks
    for chunk in reversed(chunks):
        for key in _GOAL_KEYS:
            for item in reversed(_listify(chunk.get(key))):
                cleaned = _clean_voice(str(item))
                if not cleaned or len(cleaned) < 10:
                    continue
                if position and _sentence_overlap(cleaned, position):
                    continue
                return cleaned.rstrip(".")

    # 3. continuation_context tail from final chunk
    final = _terminal_chunk(chunks)
    tail = _continuation_tail(final)
    if tail and not (position and _sentence_overlap(tail, position)):
        return tail.rstrip(".")

    # 4. archetype fallback
    key = (archetype or "mixed").strip().lower()
    return _ARCHETYPE_NEXT_FALLBACK.get(key, _ARCHETYPE_NEXT_FALLBACK["mixed"])


def _project_title(chunks: list[dict[str, Any]], *, label: str = "") -> str:
    if label:
        return label.strip()
    final = _terminal_chunk(chunks)
    topic = _clean_voice(str(final.get("topic") or ""))
    if topic:
        return topic
    role = ARCHETYPE_ROLES.get("mixed", "Project")
    return f"{role} continuation"


def _format_list_section(items: list[str], *, empty: str = "None identified.") -> str:
    if not items:
        return empty
    return "\n".join(f"- {item}" for item in items)


def generate_continuation_briefing(
    chunk_outputs: list[dict[str, Any]],
    *,
    conversation: str = "",
    archetype: str = "mixed",
    label: str = "",
) -> str:
    """Build ONE continuation briefing from all chunk V10 outputs.

    Args:
        chunk_outputs: V10 extraction dicts, each may include ``chunk_index``.
        conversation: Full transcript (optional; reserved for future use).
        archetype: Bucket hint for next-action fallback.
        label: Optional human label for project title.
    """
    _ = conversation  # reserved; terminal state comes from chunk outputs

    if not chunk_outputs:
        return ""

    ordered = sorted(
        chunk_outputs,
        key=lambda c: int(c.get("chunk_index", 0)),
    )
    # Strip chunk_index wrapper if outputs are nested
    states = []
    for row in ordered:
        if "v10_output" in row and isinstance(row["v10_output"], dict):
            states.append(row["v10_output"])
        elif "output" in row and isinstance(row["output"], dict):
            states.append(row["output"])
        else:
            states.append(row)

    if not states:
        return ""

    final = states[-1]
    objectives = _aggregate_list_field(states, "objective")
    completed = _aggregate_list_field(states, "completed_work")
    active = _aggregate_list_field(states, "active_problems")
    constraints = _aggregate_list_field(states, "constraints")

    # Drop active problems that appear resolved in aggregated resolved list
    resolved = _aggregate_list_field(states, "resolved_problems")
    if resolved:
        active = [
            a
            for a in active
            if not any(_sentence_overlap(a, r) for r in resolved)
        ]

    position = _terminal_position(final)
    if not position and completed:
        position = f"Work in progress. Latest completed: {completed[-1]}"

    next_action = _derive_next_action(states, position=position, archetype=archetype)
    objective_text = _objective_text(states, objectives)
    title = _project_title(states, label=label)

    lines = [
        "## PROJECT",
        "",
        title,
        "",
        "Objective:",
        objective_text,
        "",
        "Current Position:",
        position or "Conversation stopped mid-thread; use completed work and next action below.",
        "",
        "Completed Work:",
        _format_list_section(completed),
        "",
        "Active Problems:",
        _format_list_section(active),
        "",
        "Constraints:",
        _format_list_section(constraints),
        "",
        "Next Action:",
        next_action,
    ]

    text = "\n".join(lines).strip()
    for forbidden in ("The slice", "The discussion is focused", "The participant"):
        if forbidden.lower() in text.lower():
            text = _clean_voice_preserve_lines(text)
            break
    return text


__all__ = ["generate_continuation_briefing"]
