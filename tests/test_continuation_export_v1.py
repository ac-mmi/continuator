"""Tests for continuation_export_v1."""
from __future__ import annotations

from continuation_export_v1 import generate_continuation_briefing


def test_single_briefing_not_multi_chunk():
    chunks = [
        {
            "chunk_index": 0,
            "objective": ["Learn Bootstrap grid"],
            "current_state": "Explaining 12-column grid.",
            "completed_work": ["Introduced row/col classes"],
            "active_problems": ["Sidebar layout example unfinished"],
            "continuation_context": "Next step: build 25/75 sidebar layout example.",
        },
        {
            "chunk_index": 1,
            "objective": ["Learn Bootstrap grid"],
            "current_state": "Learner stuck on 25% sidebar / 75% content layout.",
            "completed_work": ["Covered basic grid", "Reviewed col-md-* classes"],
            "active_problems": ["Needs working sidebar layout code"],
            "continuation_context": "The next step is to show col-md-3 and col-md-9 example.",
        },
    ]
    briefing = generate_continuation_briefing(chunks, archetype="tutorial", label="Aman")
    assert briefing
    assert "=== CHUNK" not in briefing
    assert "## PROJECT" in briefing
    assert "Next Action:" in briefing
    assert "Current Position:" in briefing
    assert "col-md" in briefing.lower() or "sidebar" in briefing.lower()
    assert "Introduced row" in briefing or "Covered basic grid" in briefing


def test_aggregates_completed_work():
    chunks = [
        {"chunk_index": 0, "completed_work": ["Step A done"], "current_state": "Mid session."},
        {"chunk_index": 1, "completed_work": ["Step A done", "Step B done"], "current_state": "Near end."},
    ]
    briefing = generate_continuation_briefing(chunks, archetype="mixed")
    assert "Step A" in briefing
    assert "Step B" in briefing
    assert briefing.count("Step A") == 1


def test_next_action_from_final_active_problem():
    chunks = [
        {"chunk_index": 0, "active_problems": ["Old blocker"], "current_state": "Early."},
        {
            "chunk_index": 1,
            "active_problems": ["Deploy to staging blocked on CI config"],
            "current_state": "Finalizing deployment.",
            "continuation_context": "Discussion about CI pipeline.",
        },
    ]
    briefing = generate_continuation_briefing(chunks, archetype="github")
    action = briefing.split("Next Action:")[-1].strip()
    assert "CI" in action or "staging" in action.lower() or "Address" in action
