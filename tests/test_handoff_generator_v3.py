"""Tests for handoff_generator_v3."""
from __future__ import annotations

from handoff_generator_v3 import generate_handoff_briefing


def test_v3_archetype_role_tutorial():
    briefing = generate_handoff_briefing(
        {
            "current_state": "Explaining Bootstrap grid layout.",
            "continuation_context": "Learner stuck on 25/75 sidebar layout.",
            "completed_work": ["Covered grid basics"],
            "active_problems": ["Sidebar width example unfinished"],
        },
        archetype="tutorial",
    )
    assert "## Role" in briefing
    assert "Tutor" in briefing
    assert "## Next action" in briefing
    assert "The participant" not in briefing


def test_v3_summary_fallback_when_continuation_empty():
    briefing = generate_handoff_briefing(
        {
            "topic": "System design trade-offs",
            "summary": (
                "The session discusses latency vs consistency trade-offs and asks the learner "
                "to write a trade-off chain before converging on the right abstraction layer."
            ),
            "current_state": "",
            "continuation_context": "",
            "objective": [],
            "completed_work": [],
            "active_problems": [],
        },
        archetype="tutorial",
    )
    assert briefing
    assert "Tutor" in briefing
    assert "## Next action" in briefing
    assert len(briefing.split()) >= 80


def test_v3_dedupes_current_and_continuation():
    dup = "Currently explaining Kafka as a distributed event log for multiple consumers."
    briefing = generate_handoff_briefing(
        {
            "current_state": dup,
            "continuation_context": dup,
            "completed_work": ["Defined event log"],
            "active_problems": [],
            "objective": ["Explain Kafka with a food delivery example"],
        },
        archetype="tutorial",
    )
    assert briefing.count("distributed event log") <= 2
    assert "food delivery" in briefing.lower() or "Resume teaching" in briefing


def test_v3_journal_coach_role():
    briefing = generate_handoff_briefing(
        {
            "current_state": "Reflecting on career stagnation and fear of change.",
            "continuation_context": "Needs help identifying one small next step.",
            "active_problems": ["Unclear what to try next"],
        },
        archetype="journal",
    )
    assert "Coach" in briefing
    assert "## Next action" in briefing
