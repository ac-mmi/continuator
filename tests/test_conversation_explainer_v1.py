"""Unit tests for conversation explainer export v1."""
from __future__ import annotations

from conversation_explainer_v1 import generate_conversation_explanation


def _chunk(
    idx: int,
    *,
    topic: str = "",
    summary: str = "",
    objective: list[str] | None = None,
    completed_work: list[str] | None = None,
    active_problems: list[str] | None = None,
    open_questions: list[str] | None = None,
    current_state: str = "",
    continuation_context: str = "",
) -> dict:
    return {
        "chunk_index": idx,
        "output": {
            "topic": topic,
            "summary": summary,
            "objective": objective or [],
            "completed_work": completed_work or [],
            "active_problems": active_problems or [],
            "open_questions": open_questions or [],
            "current_state": current_state,
            "continuation_context": continuation_context,
            "decisions": [],
            "goals": [],
            "resolved_problems": [],
            "constraints": [],
            "important_facts": [],
            "parse_ok": True,
        },
    }


def test_explain_includes_required_sections():
    rows = [
        _chunk(
            0,
            topic="HTML forms",
            summary="The learner studied HTML forms and validation.",
            completed_work=["Learned form validation", "Learned Bootstrap layouts"],
            objective=["CSS selectors"],
        ),
        _chunk(
            1,
            topic="Fetch API",
            summary="The session moved to Fetch API and AJAX basics.",
            current_state="Beginning Fetch API and AJAX.",
            open_questions=["Understanding fetch responses"],
            active_problems=["Understanding returned data"],
        ),
    ]
    text = generate_conversation_explanation(
        rows,
        label="web dev course",
        archetype="tutorial",
        total_chunks=2,
    )
    for section in (
        "OVERVIEW",
        "MAIN TOPICS",
        "LEARNINGS / DECISIONS",
        "CURRENT STATUS",
        "OPEN QUESTIONS",
        "KEY TAKEAWAYS",
    ):
        assert section in text
    assert "Fetch API" in text
    assert "Learned form validation" in text


def test_explain_not_continuation_voice():
    rows = [
        _chunk(
            0,
            topic="Kafka tutorial",
            current_state="Resume Fetch API",
            continuation_context="Continue Fetch API",
        )
    ]
    text = generate_conversation_explanation(rows, archetype="tutorial")
    assert "Next Action" not in text
    assert "CURRENT STATUS" in text
