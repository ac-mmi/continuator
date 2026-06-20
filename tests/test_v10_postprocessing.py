"""Tests for V10 post-processing: truncation repair + handoff v2."""
from __future__ import annotations

import json

from handoff_generator_v2 import generate_handoff_briefing
from v8_truncation_repair import repair_truncated_json


def test_repair_truncated_v10_json():
    raw = (
        '{"topic": "Kafka basics", "summary": "Explaining event logs.", '
        '"important_facts": ["Kafka stores events"], '
        '"objective": ["Explain Kafka"], '
        '"current_state": "Mid-explanation of event logs.", '
        '"completed_work": ["Defined event log"], '
        '"active_problems": [], '
        '"continuation_context": "Next use a food delivery ex'
    )
    repaired, audit = repair_truncated_json(raw)
    assert repaired is not None
    assert audit["can_repair"]
    data = json.loads(repaired)
    assert data["topic"] == "Kafka basics"
    assert data["current_state"] == "Mid-explanation of event logs."
    assert "continuation_context" not in data


def test_handoff_v2_strips_observer_voice():
    briefing = generate_handoff_briefing(
        {
            "current_state": "The participant is being asked to choose the correct Bootstrap button color.",
            "continuation_context": "The discussion is focused on JavaScript DOM access.",
            "completed_work": ["Reviewed Bootstrap colors"],
            "active_problems": ["Unanswered quiz question"],
            "objective": [],
        }
    )
    assert briefing
    assert "The participant" not in briefing
    assert "The slice" not in briefing
    assert "## Role" in briefing
    assert "## Current position" in briefing
    assert "## Next action" in briefing


def test_handoff_v2_extracts_next_action_from_continuation():
    briefing = generate_handoff_briefing(
        {
            "current_state": "The slice is explaining Kafka as a distributed event log.",
            "continuation_context": (
                "The slice is explaining Kafka. The next step would be to explain Kafka "
                "using a food delivery app example."
            ),
            "completed_work": [],
            "active_problems": [],
        }
    )
    assert "food delivery" in briefing.lower()
