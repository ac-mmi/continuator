"""Tests for checkpoint_record_v2."""
from __future__ import annotations

from pathlib import Path

import yaml

from checkpoint_record_v2 import (
    FORMAT_VERSION,
    build_record_from_session,
    hash_transcript,
    migrate_v1_flat,
    parse_checkpoint_file,
    serialize_checkpoint,
    validate_record,
)
from checkpoint_state_v1 import build_checkpoint_state


def test_hash_transcript_normalizes():
    assert hash_transcript("  hello\n") == hash_transcript("hello")


def test_migrate_v1_flat():
    flat = {
        "project": "neck",
        "objective": ["Do thing"],
        "current_state": "Working.",
        "completed_work": ["Step 1"],
        "active_problems": [],
        "constraints": [],
        "next_action": "Continue.",
    }
    record = migrate_v1_flat(flat)
    assert record["format_version"] == FORMAT_VERSION
    assert record["state"]["next_action"] == "Continue."
    assert record.get("_migrated_from_v1") is True


def test_round_trip_fixture(tmp_path: Path):
    fixture = Path(__file__).parent / "fixtures" / "checkpoints" / "v2" / "standard.yaml"
    record = parse_checkpoint_file(fixture)
    assert record["project"] == "neck-refactor"
    out = serialize_checkpoint(record)
    reparsed = yaml.safe_load(out)["checkpoint"]
    assert reparsed["id"] == record["id"]
    assert reparsed["state"]["next_action"] == record["state"]["next_action"]


def test_validate_record_requires_next_action():
    bad = {"format_version": 2, "state": {"objective": ["x"], "current_state": "y", "next_action": ""}}
    assert "missing next_action" in validate_record(bad)


def test_build_record_from_session_minimal_fields():
    chunks = [
        {
            "chunk_index": 0,
            "objective": ["Goal"],
            "current_state": "In progress.",
            "completed_work": ["Done"],
            "active_problems": ["Issue"],
            "constraints": [],
            "continuation_context": "Next: fix bug.",
        }
    ]
    state = build_checkpoint_state(chunks, label="demo", project="demo", total_chunks=1)
    session = {
        "checkpoint_state": dict(state),
        "continuation_briefing": "briefing text",
        "conversation_explanation": "explain text",
        "exports": {"claude": "c", "chatgpt": "g", "gemini": "m", "markdown": "md"},
        "product_baseline": "test",
        "archetype": "mixed",
        "transcript_chars": 100,
        "chunking": {"strategy": "paragraph_chunk_overlap", "chunk_count": 1},
        "chunk_selection": {"selected_indices": [0], "k": 1, "total_chunks": 1},
        "v10_rows": [{"chunk_index": 0, "input_chars": 10, "output": chunks[0]}],
        "_chunks_text": ["chunk"],
        "_runtime_seconds": 0.5,
    }
    record = build_record_from_session(
        session,
        source_meta={"kind": "file", "path": "t.txt", "sha256": hash_transcript("t"), "char_count": 1, "transcript": "t"},
        project="demo",
        tier="full",
    )
    assert record["cached_exports"]["briefing"] == "briefing text"
    assert record["pipeline"]["chunk_extractions"]
