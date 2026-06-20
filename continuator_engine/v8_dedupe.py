"""Exact-list dedupe for V8 production memory records."""
from __future__ import annotations

from typing import Any, TypeVar

T = TypeVar("T")


def dedupe_exact_preserve_order(items: list[str]) -> tuple[list[str], int]:
    """Remove exact duplicate strings; preserve first occurrence order."""
    seen: set[str] = set()
    out: list[str] = []
    removed = 0
    for item in items:
        key = item if isinstance(item, str) else str(item)
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        out.append(key)
    return out, removed


def dedupe_memory_fields(
    *,
    important_facts: list[str],
    open_questions: list[str],
    current_goals: list[str] | None = None,
    decisions: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    """
    Dedupe list fields on a memory record. Does not merge or invent content.

    Returns (deduped_fields, audit) where audit includes before/after counts.
    """
    goals = list(current_goals or [])
    decs = list(decisions or [])
    steps = list(next_steps or [])

    facts_deduped, facts_removed = dedupe_exact_preserve_order(list(important_facts or []))
    questions_deduped, questions_removed = dedupe_exact_preserve_order(list(open_questions or []))
    goals_deduped, goals_removed = dedupe_exact_preserve_order(goals)
    decs_deduped, decs_removed = dedupe_exact_preserve_order(decs)
    steps_deduped, steps_removed = dedupe_exact_preserve_order(steps)

    fields = {
        "important_facts": facts_deduped,
        "open_questions": questions_deduped,
        "current_goals": goals_deduped,
        "decisions": decs_deduped,
        "next_steps": steps_deduped,
    }
    audit = {
        "facts_before": len(important_facts or []),
        "facts_after": len(facts_deduped),
        "facts_removed": facts_removed,
        "questions_before": len(open_questions or []),
        "questions_after": len(questions_deduped),
        "questions_removed": questions_removed,
        "goals_before": len(goals),
        "goals_after": len(goals_deduped),
        "decisions_before": len(decs),
        "decisions_after": len(decs_deduped),
        "next_steps_before": len(steps),
        "next_steps_after": len(steps_deduped),
    }
    return fields, audit
