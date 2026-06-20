"""Explain Conversation export v1 — retrospective summary from V10 chunk outputs.

No retraining. Aggregates existing V10 extraction fields into a human-readable
explanation of what happened in a conversation (vs continuation handoff).
"""
from __future__ import annotations

import re
from typing import Any

from continuation_export_v1 import (
    _aggregate_list_field,
    _format_list_section,
    _terminal_chunk,
    _terminal_position,
)
from handoff_generator_v2 import _clean_voice, _listify
from handoff_generator_v3 import _clean_summary, _sentence_overlap

_ARCHETYPE_OVERVIEW: dict[str, str] = {
    "tutorial": "This conversation followed a structured learning or tutorial session.",
    "debugging": "This conversation focused on diagnosing and resolving a technical problem.",
    "project_management": "This conversation tracked project progress, decisions, and blockers.",
    "journal": "This conversation was a reflective or personal journal-style discussion.",
    "research": "This conversation explored research questions and synthesized findings.",
    "github": "This conversation centered on a technical issue, code review, or open-source thread.",
    "reddit": "This conversation was a community discussion with multiple perspectives.",
    "mixed": "This conversation covered several related topics over time.",
}

_OBSERVER_RX = re.compile(
    r"^(the (?:slice|discussion|participant|session|conversation)|"
    r"this (?:slice|discussion|session)|the user is|they have been)",
    re.I,
)


def _normalize_states(chunk_outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(chunk_outputs, key=lambda c: int(c.get("chunk_index", 0)))
    states: list[dict[str, Any]] = []
    for row in ordered:
        if "v10_output" in row and isinstance(row["v10_output"], dict):
            state = dict(row["v10_output"])
        elif "output" in row and isinstance(row["output"], dict):
            state = dict(row["output"])
        else:
            state = dict(row)
        if "chunk_index" not in state:
            state["chunk_index"] = int(row.get("chunk_index", len(states)))
        states.append(state)
    return states


def _is_observer_voice(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return True
    return bool(_OBSERVER_RX.match(cleaned))


def _topic_label(text: str) -> str:
    cleaned = _clean_voice(text)
    if not cleaned:
        return ""
    cleaned = re.sub(r"^(topic|objective|goal)\s*:\s*", "", cleaned, flags=re.I)
    if len(cleaned) > 90:
        cleaned = cleaned[:87].rstrip(" ,;") + "…"
    return cleaned


def _collect_topics(states: list[dict[str, Any]]) -> list[str]:
    kept: list[str] = []
    for chunk in states:
        for key in ("topic", "objective"):
            for raw in _listify(chunk.get(key)):
                label = _topic_label(str(raw))
                if not label or _is_observer_voice(label):
                    continue
                if any(_sentence_overlap(label, prev) for prev in kept):
                    continue
                kept.append(label)
    return kept[:14]


def _collect_summaries(states: list[dict[str, Any]]) -> list[str]:
    kept: list[str] = []
    for chunk in states:
        summary = _clean_summary(str(chunk.get("summary") or ""))
        if not summary or _is_observer_voice(summary) or len(summary) < 20:
            continue
        if any(_sentence_overlap(summary, prev) for prev in kept):
            continue
        kept.append(summary)
    return kept


def _build_overview(
    states: list[dict[str, Any]],
    *,
    archetype: str,
    label: str,
) -> str:
    terminal = _terminal_chunk(states)
    summaries = _collect_summaries(states)
    topics = _collect_topics(states)

    terminal_summary = _clean_summary(str(terminal.get("summary") or ""))
    if terminal_summary and len(terminal_summary) > 40 and not _is_observer_voice(terminal_summary):
        lead = terminal_summary
    elif summaries:
        lead = summaries[0]
    elif topics:
        if len(topics) == 1:
            lead = f"This conversation focused on {topics[0].rstrip('.')}."
        else:
            lead = f"This conversation covered {', '.join(topics[:4]).rstrip('.')}."
    else:
        lead = _ARCHETYPE_OVERVIEW.get(archetype, _ARCHETYPE_OVERVIEW["mixed"])

    if label and label.lower() not in lead.lower():
        lead = f"{lead.rstrip('.')} ({label})."
    return lead.rstrip(".") + "."


def _build_learnings(states: list[dict[str, Any]]) -> list[str]:
    items: list[str] = []
    for field in ("completed_work", "decisions", "resolved_problems", "goals"):
        for raw in _aggregate_list_field(states, field):
            cleaned = _clean_voice(str(raw))
            if not cleaned or _is_observer_voice(cleaned):
                continue
            if cleaned.lower().startswith("learned "):
                cleaned = cleaned[8:]
            if any(_sentence_overlap(cleaned, prev) for prev in items):
                continue
            items.append(cleaned)
    return items[:12]


def _build_open_questions(states: list[dict[str, Any]]) -> list[str]:
    items: list[str] = []
    for field in ("open_questions", "active_problems", "goals"):
        for raw in _aggregate_list_field(states, field):
            cleaned = _clean_voice(str(raw))
            if not cleaned or _is_observer_voice(cleaned):
                continue
            if not cleaned.endswith("?"):
                if field == "active_problems":
                    cleaned = f"Unresolved: {cleaned.rstrip('.')}"
            if any(_sentence_overlap(cleaned, prev) for prev in items):
                continue
            items.append(cleaned)
    return items[:10]


def _build_current_status(states: list[dict[str, Any]]) -> str:
    terminal = _terminal_chunk(states)
    position = _terminal_position(terminal)
    if position and not _is_observer_voice(position):
        return position.rstrip(".") + "."

    continuation = _clean_voice(str(terminal.get("continuation_context") or ""))
    if continuation and len(continuation) > 30 and not _is_observer_voice(continuation):
        return continuation.rstrip(".") + "."

    actives = _aggregate_list_field(states, "active_problems")
    if actives:
        return f"The conversation ended with open threads including {actives[-1].rstrip('.')}."

    completed = _aggregate_list_field(states, "completed_work")
    if completed:
        return f"Progress was made on {completed[-1].rstrip('.')}."

    topics = _collect_topics(states)
    if topics:
        return f"The latest focus was {topics[-1].rstrip('.')}."

    return "The conversation reached a natural pause point without a sharp unresolved blocker."


def _build_takeaways(
    states: list[dict[str, Any]],
    *,
    learnings: list[str],
    topics: list[str],
) -> list[str]:
    items: list[str] = []
    for field in ("important_facts", "completed_work", "constraints", "resolved_problems"):
        for raw in _aggregate_list_field(states, field):
            cleaned = _clean_voice(str(raw))
            if not cleaned or _is_observer_voice(cleaned) or len(cleaned) < 12:
                continue
            if any(_sentence_overlap(cleaned, prev) for prev in items):
                continue
            items.append(cleaned)

    for topic in topics[:4]:
        bullet = f"Major thread: {topic.rstrip('.')}"
        if not any(_sentence_overlap(bullet, x) for x in items):
            items.append(bullet)

    for item in learnings[:3]:
        if not any(_sentence_overlap(item, x) for x in items):
            items.append(item)

    return items[:8]


def generate_conversation_explanation(
    chunk_outputs: list[dict[str, Any]],
    *,
    conversation: str = "",
    label: str = "",
    archetype: str = "mixed",
    total_chunks: int | None = None,
) -> str:
    """Build Explain-mode export from aggregated V10 chunk outputs."""
    states = _normalize_states(chunk_outputs)
    if not states:
        return ""

    overview = _build_overview(states, archetype=archetype, label=label)
    topics = _collect_topics(states)
    learnings = _build_learnings(states)
    status = _build_current_status(states)
    open_questions = _build_open_questions(states)
    takeaways = _build_takeaways(states, learnings=learnings, topics=topics)

    lines = [
        "OVERVIEW",
        "",
        overview,
        "",
        "MAIN TOPICS",
        "",
        _format_list_section(topics) if topics else "None identified.",
        "",
        "LEARNINGS / DECISIONS",
        "",
        _format_list_section(learnings) if learnings else "None identified.",
        "",
        "CURRENT STATUS",
        "",
        status,
        "",
        "OPEN QUESTIONS",
        "",
        _format_list_section(open_questions) if open_questions else "None identified.",
        "",
        "KEY TAKEAWAYS",
        "",
        _format_list_section(takeaways) if takeaways else "None identified.",
    ]

    text = "\n".join(lines).strip()
    if conversation and total_chunks and total_chunks > 1 and "sections" not in text.lower():
        # Light session scale hint for long transcripts.
        text = text.replace(
            overview,
            f"{overview.rstrip('.')} The source spans {total_chunks} sections.",
            1,
        )
    return text


__all__ = ["generate_conversation_explanation"]
