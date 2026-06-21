"""Tests for CheckpointState build/render and checkpoint YAML."""
from __future__ import annotations

from pathlib import Path

from checkpoint_state_v1 import (
    build_checkpoint_state,
    objective_text_to_list,
    render_briefing_from_checkpoint_state,
)
from continuation_export_v2_frontier import generate_continuation_briefing_frontier

from continuator.checkpoint_yaml import (
    render_checkpoint_yaml,
    slugify_project,
    validate_checkpoint_state,
    write_checkpoint_yaml,
)


_CHUNKS = [
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


def test_build_state_matches_frontier_briefing():
    direct = generate_continuation_briefing_frontier(
        _CHUNKS, archetype="tutorial", label="Aman", total_chunks=2
    )
    state = build_checkpoint_state(
        _CHUNKS, archetype="tutorial", label="Aman", project="aman", total_chunks=2
    )
    rendered = render_briefing_from_checkpoint_state(state)
    assert rendered == direct


def test_objective_text_to_list_bullets():
    text = "Lead goal\n- secondary\n- tertiary"
    assert objective_text_to_list(text) == ["Lead goal", "secondary", "tertiary"]


def test_validate_checkpoint_state_requires_core_fields():
    ok = {
        "project": "neck",
        "objective": ["Do the thing"],
        "current_state": "In progress.",
        "completed_work": [],
        "active_problems": [],
        "constraints": [],
        "next_action": "Continue implementation.",
    }
    assert validate_checkpoint_state(ok) == []

    bad = dict(ok)
    bad["next_action"] = ""
    assert "missing next_action" in validate_checkpoint_state(bad)


def test_render_checkpoint_yaml_fields(tmp_path: Path):
    state = {
        "project": "neck",
        "objective": ["Finish module 3"],
        "current_state": "Working on fetch wrapper.",
        "completed_work": ["Module 1"],
        "active_problems": ["CORS errors"],
        "constraints": ["TypeScript strict"],
        "next_action": "Fix vite.config.ts",
    }
    yaml_text = render_checkpoint_yaml(state)
    assert "project: neck" in yaml_text
    assert "next_action:" in yaml_text
    assert "- Finish module 3" in yaml_text

    out = tmp_path / "neck.yaml"
    write_checkpoint_yaml(out, state)
    assert out.is_file()
    assert "project: neck" in out.read_text(encoding="utf-8")


def test_slugify_project():
    assert slugify_project("Neck Refactor") == "neck-refactor"
    assert slugify_project("") == "conversation"
