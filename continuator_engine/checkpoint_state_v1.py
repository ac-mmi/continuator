"""CheckpointState — structured continuation fields shared by briefing and YAML export."""
from __future__ import annotations

from typing import Any, TypedDict

from continuation_export_v1 import (
    _aggregate_list_field,
    _format_list_section,
    _project_title,
    _terminal_chunk,
    _terminal_position,
)
from continuation_export_v2_frontier import (
    _conversation_frontier_hints,
    _derive_frontier_next_action,
    _frontier_objective,
    _normalize_states,
    _split_history_frontier,
    _total_chunk_count,
    continuation_closure_detected,
    filter_superseded_actives,
)
from handoff_generator_v2 import _clean_voice_preserve_lines
from continuation_export_v2_frontier import _sentence_overlap


class CheckpointState(TypedDict):
    project: str
    project_title: str
    objective: list[str]
    objective_display: str
    current_state: str
    completed_work: list[str]
    active_problems: list[str]
    constraints: list[str]
    next_action: str


def objective_text_to_list(text: str) -> list[str]:
    """Split frontier objective prose/bullets into a YAML-friendly list."""
    items: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
        elif not items:
            items.append(stripped)
        else:
            items.append(stripped)
    if not items and (text or "").strip():
        items = [(text or "").strip()]
    return items


def build_checkpoint_state(
    chunk_outputs: list[dict[str, Any]],
    *,
    conversation: str = "",
    archetype: str = "mixed",
    label: str = "",
    project: str = "",
    total_chunks: int | None = None,
) -> CheckpointState:
    """Aggregate V10 chunk outputs into structured checkpoint fields."""
    states = _normalize_states(chunk_outputs)
    if not states:
        return CheckpointState(
            project=project or label or "",
            project_title=label or "Conversation",
            objective=[],
            objective_display="",
            current_state="",
            completed_work=[],
            active_problems=[],
            constraints=[],
            next_action="",
        )

    n_total = total_chunks if total_chunks is not None else _total_chunk_count(states)
    history, frontier, _cutoff = _split_history_frontier(states, total_chunks=n_total)
    terminal = _terminal_chunk(frontier)
    hints = _conversation_frontier_hints(conversation)
    closed = continuation_closure_detected(terminal, conversation)

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

    current_state = position or "Conversation stopped mid-thread; use completed work and next action below."

    return CheckpointState(
        project=project or label or "",
        project_title=title,
        objective=objective_text_to_list(objective_text),
        objective_display=objective_text,
        current_state=current_state,
        completed_work=completed,
        active_problems=frontier_actives,
        constraints=constraints,
        next_action=next_action,
    )


def render_briefing_from_checkpoint_state(state: CheckpointState) -> str:
    """Render continuation briefing markdown from structured checkpoint state."""
    objective_display = state["objective_display"]
    if not objective_display and state["objective"]:
        objective_display = (
            state["objective"][0]
            if len(state["objective"]) == 1
            else _format_list_section(state["objective"])
        )

    lines = [
        "## PROJECT",
        "",
        state["project_title"],
        "",
        "Objective:",
        objective_display,
        "",
        "Current Position:",
        state["current_state"],
        "",
        "Completed Work:",
        _format_list_section(state["completed_work"]),
        "",
        "Active Problems:",
        _format_list_section(state["active_problems"]),
        "",
        "Constraints:",
        _format_list_section(state["constraints"]),
        "",
        "Next Action:",
        state["next_action"],
    ]

    text = "\n".join(lines).strip()
    for forbidden in ("The slice", "The discussion is focused", "The participant"):
        if forbidden.lower() in text.lower():
            text = _clean_voice_preserve_lines(text)
            break
    return text


__all__ = [
    "CheckpointState",
    "build_checkpoint_state",
    "objective_text_to_list",
    "render_briefing_from_checkpoint_state",
]
