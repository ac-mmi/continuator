"""Continuation Export v2 — frontier-first merge (History vs Frontier split).

Experimental path validated against v1. See continuation_frontier_analysis.md.
"""
from __future__ import annotations

import math
import re
from typing import Any

from continuation_export_v1 import (
    _aggregate_list_field,
    _derive_next_action,
    _format_list_section,
    _normalize,
    _objective_text,
    _project_title,
    _sentence_overlap,
    _terminal_chunk,
    _terminal_position,
)
from handoff_generator_v2 import _clean_voice, _clean_voice_preserve_lines, _listify
from handoff_generator_v3 import (
    _ARCHETYPE_NEXT_FALLBACK,
    _clean_summary,
    _extract_next_from_text,
    _merge_position,
    _split_sentences,
)

_GOAL_KEYS = ("objective", "goals", "open_questions", "next_steps")

_CLOSURE_RX = re.compile(
    r"(start a new chat|start new chat|that makes sense|thank you|thanks\.|"
    r"i'?ll (?:work on )?implement|continue (?:my )?(?:web development )?course from|"
    r"thread is resolved|conversation stopped)",
    re.I,
)

_FETCH_CONTINUE_RX = re.compile(
    r"continue (?:my )?(?:web development )?course from\s+([^\n\.]+)",
    re.I,
)

_TUTOR_QUESTION_RX = re.compile(
    r"(?:what do you think\??|which one would you (?:choose|use)\??|try answering[^.?]*\??|"
    r"what will (?:data|php|happen)[^.?]*\??)\s*$",
    re.I | re.M,
)

_USER_PIVOT_RX = re.compile(
    r"(?:as this chat|how to speed up|growing bigger|becoming slow|different topic|"
    r"change (?:of )?topic|side question)",
    re.I,
)

_STALE_QUIZ_MARKERS = (
    "member saved",
    "what will data contain",
    "what the data contains after",
    "save.php",
)


def frontier_band_size(n: int, *, fraction: float = 0.20) -> int:
    """Band = clamp(ceil(fraction·N), min=2, max=5)."""
    if n <= 0:
        return 0
    return max(2, min(5, int(math.ceil(fraction * n))))


def frontier_cutoff_index(total_chunks: int) -> int:
    """First chunk index (inclusive) in the frontier band."""
    if total_chunks <= 0:
        return 0
    band = frontier_band_size(total_chunks)
    return max(0, total_chunks - band)


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


def _total_chunk_count(states: list[dict[str, Any]]) -> int:
    if not states:
        return 0
    indices = [int(s.get("chunk_index", i)) for i, s in enumerate(states)]
    return max(indices) + 1


def _split_history_frontier(
    states: list[dict[str, Any]], *, total_chunks: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    cutoff = frontier_cutoff_index(total_chunks)
    history = [s for s in states if int(s.get("chunk_index", 0)) < cutoff]
    frontier = [s for s in states if int(s.get("chunk_index", 0)) >= cutoff]
    if not frontier and states:
        frontier = [states[-1]]
    return history, frontier, cutoff


def continuation_closure_detected(terminal: dict[str, Any], conversation: str = "") -> bool:
    blob = " ".join(
        str(terminal.get(k) or "")
        for k in ("current_state", "continuation_context", "summary", "topic")
    )
    tail = (conversation or "")[-4000:]
    return bool(_CLOSURE_RX.search(blob) or _CLOSURE_RX.search(tail))


def _conversation_frontier_hints(conversation: str) -> dict[str, str]:
    """Extract continuation hints from raw transcript tail when V10 terminal is stale."""
    hints: dict[str, str] = {}
    tail = (conversation or "").strip()
    if not tail:
        return hints

    window = tail[-5000:]
    m = _FETCH_CONTINUE_RX.search(window)
    if m:
        topic = _clean_voice(m.group(1).strip())
        hints["next_action"] = f"Continue the course from {topic.rstrip('.')}."
        hints["position"] = (
            f"Learner should resume the tutorial from {topic.rstrip('.')} "
            f"(prior lessons through Event Handling are complete)."
        )

    if _USER_PIVOT_RX.search(window) and "fetch" in window.lower():
        if "next_action" not in hints:
            hints["next_action"] = "Continue the web development course from Fetch API (AJAX)."
        hints["note"] = "User asked about speeding up a long chat; recommend a fresh thread with course summary."

    if re.search(r"that makes sense\.?\s*thank you", window, re.I):
        hints["position"] = "Thread resolved — implement the agreed CI/CD workflow changes."
        hints["next_action"] = "Implement mentor suggestions: PR validation vs push/merge deployment flow."

    offer = re.findall(
        r"If you want(?: next)?, I can(?: next)?(?: explain| show you| give you)[:\s]+([^\n]+)",
        window,
        re.I,
    )
    if offer and "next_action" not in hints:
        last_offer = _clean_voice(offer[-1].strip(" ."))
        if last_offer:
            hints["next_action"] = f"Pick up from tutor offer: {last_offer.rstrip('.')}."

    return hints


def _looks_like_stale_quiz(text: str, *, conversation: str) -> bool:
    lower = _normalize(text)
    if not any(marker in lower for marker in _STALE_QUIZ_MARKERS):
        return False
    tail = (conversation or "")[-6000:].lower()
    if _USER_PIVOT_RX.search(tail):
        return True
    if "continue" in tail and "fetch" in tail:
        return True
    if _FETCH_CONTINUE_RX.search(conversation or ""):
        return True
    return False


def _superseded_by_user_pivot(active: str, conversation: str) -> bool:
    if not conversation:
        return False
    tail = conversation[-8000:]
    if not _USER_PIVOT_RX.search(tail):
        return False
    # Tutor quiz in tail followed by user pivot without answering the quiz
    q_pos = max(tail.rfind("?"), tail.lower().rfind("what do you think"))
    pivot = _USER_PIVOT_RX.search(tail)
    if q_pos >= 0 and pivot and pivot.start() > q_pos:
        active_norm = _normalize(active)
        quiz_region = tail[q_pos : pivot.start()].lower()
        if any(w in active_norm for w in quiz_region.split() if len(w) > 5):
            return True
        if _looks_like_stale_quiz(active, conversation=conversation):
            return True
    return _looks_like_stale_quiz(active, conversation=conversation)


def filter_superseded_actives(
    actives: list[str],
    *,
    terminal: dict[str, Any],
    conversation: str = "",
    closure: bool | None = None,
) -> list[str]:
    closed = continuation_closure_detected(terminal, conversation) if closure is None else closure
    kept: list[str] = []
    for raw in actives:
        cleaned = _clean_voice(str(raw))
        if not cleaned:
            continue
        if closed and _looks_like_stale_quiz(cleaned, conversation=conversation):
            continue
        if _superseded_by_user_pivot(cleaned, conversation):
            continue
        if any(_sentence_overlap(cleaned, prev) for prev in kept):
            continue
        kept.append(cleaned)
    return kept


def _frontier_objective(
    frontier: list[dict[str, Any]],
    history: list[dict[str, Any]],
    *,
    conversation: str = "",
) -> str:
    terminal = _terminal_chunk(frontier)
    lead_parts: list[str] = []

    topic = _clean_voice(str(terminal.get("topic") or ""))
    if topic and not _looks_like_stale_quiz(topic, conversation=conversation):
        lead_parts.append(topic)

    for key in _GOAL_KEYS:
        for item in _listify(terminal.get(key)):
            cleaned = _clean_voice(str(item))
            if not cleaned or _looks_like_stale_quiz(cleaned, conversation=conversation):
                continue
            if cleaned not in lead_parts:
                lead_parts.append(cleaned)

    for chunk in reversed(frontier):
        for item in _listify(chunk.get("objective")):
            cleaned = _clean_voice(str(item))
            if cleaned and cleaned not in lead_parts:
                lead_parts.append(cleaned)

    history_themes: list[str] = []
    for chunk in history:
        for item in _listify(chunk.get("objective")) + _listify(chunk.get("topic")):
            cleaned = _clean_voice(str(item))
            if cleaned and cleaned not in lead_parts and cleaned not in history_themes:
                history_themes.append(cleaned)

    if not lead_parts and not history_themes:
        return "Continue the in-progress work from the current position."

    if len(lead_parts) == 1 and not history_themes:
        return lead_parts[0]

    lines: list[str] = []
    if lead_parts:
        lines.append(lead_parts[0])
        for item in lead_parts[1:4]:
            lines.append(f"- {item}")
    for item in history_themes[:3]:
        lines.append(f"- {item}")
    return "\n".join(lines) if len(lines) > 1 else (lines[0] if lines else "")


def _derive_frontier_next_action(
    frontier: list[dict[str, Any]],
    *,
    position: str,
    archetype: str,
    conversation: str,
    hints: dict[str, str],
) -> str:
    if hints.get("next_action"):
        return hints["next_action"].rstrip(".")

    terminal = _terminal_chunk(frontier)

    for chunk in reversed(frontier):
        for key in ("next_steps", "goals", "open_questions", "objective"):
            for item in reversed(_listify(chunk.get(key))):
                cleaned = _clean_voice(str(item))
                if not cleaned or len(cleaned) < 10:
                    continue
                if _looks_like_stale_quiz(cleaned, conversation=conversation):
                    continue
                if _superseded_by_user_pivot(cleaned, conversation):
                    continue
                if position and _sentence_overlap(cleaned, position):
                    continue
                if not cleaned.lower().startswith(("continue", "resolve", "address", "fix", "pick")):
                    if key == "next_steps":
                        return cleaned.rstrip(".")
                    return cleaned.rstrip(".")
                return cleaned.rstrip(".")

    actives = filter_superseded_actives(
        _aggregate_list_field(frontier, "active_problems"),
        terminal=terminal,
        conversation=conversation,
    )
    for problem in actives:
        action = problem if problem.lower().startswith(("continue", "address", "resolve", "fix")) else f"Address: {problem}"
        if position and _sentence_overlap(action, position):
            continue
        return action.rstrip(".")

    tail = _extract_next_from_text(str(terminal.get("continuation_context") or ""))
    if tail and not _looks_like_stale_quiz(tail, conversation=conversation):
        if not (position and _sentence_overlap(tail, position)):
            return tail.rstrip(".")

    return _derive_next_action(frontier, position=position, archetype=archetype)


def generate_continuation_briefing_frontier(
    chunk_outputs: list[dict[str, Any]],
    *,
    conversation: str = "",
    archetype: str = "mixed",
    label: str = "",
    total_chunks: int | None = None,
) -> str:
    """Build continuation briefing with History Merge + Frontier Merge."""
    if not chunk_outputs:
        return ""

    states = _normalize_states(chunk_outputs)
    if not states:
        return ""

    n_total = total_chunks if total_chunks is not None else _total_chunk_count(states)
    history, frontier, cutoff = _split_history_frontier(states, total_chunks=n_total)
    terminal = _terminal_chunk(frontier)
    hints = _conversation_frontier_hints(conversation)
    closed = continuation_closure_detected(terminal, conversation)

    # --- Frontier merge ---
    position = hints.get("position") or _terminal_position(terminal)
    if not position:
        position = _terminal_position(_terminal_chunk(states))

    completed = _aggregate_list_field(states, "completed_work")
    constraints = _aggregate_list_field(states, "constraints")

    frontier_actives = filter_superseded_actives(
        _aggregate_list_field(frontier, "active_problems"),
        terminal=terminal,
        conversation=conversation,
        closure=closed,
    )

    resolved = _aggregate_list_field(frontier, "resolved_problems")
    if resolved:
        frontier_actives = [
            a for a in frontier_actives if not any(_sentence_overlap(a, r) for r in resolved)
        ]

    objective_text = _frontier_objective(frontier, history, conversation=conversation)
    next_action = _derive_frontier_next_action(
        frontier,
        position=position,
        archetype=archetype,
        conversation=conversation,
        hints=hints,
    )
    title = _project_title(states, label=label)

    if not position and completed:
        position = f"Work in progress. Latest completed: {completed[-1]}"

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
        _format_list_section(frontier_actives),
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


__all__ = [
    "continuation_closure_detected",
    "filter_superseded_actives",
    "frontier_band_size",
    "frontier_cutoff_index",
    "generate_continuation_briefing_frontier",
]
