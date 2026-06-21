"""Tests for checkpoint_merge_v1."""
from __future__ import annotations

import pytest

from checkpoint_merge_v1 import (
    chunk_content_hash,
    detect_transcript_delta,
    incremental_extract_rows,
    is_append_only,
    state_field_jaccard,
)


def test_is_append_only():
    assert is_append_only("hello", "hello world")
    assert not is_append_only("hello", "world hello")


def test_detect_delta():
    assert detect_transcript_delta("ab", "abcd") == "cd"


def test_chunk_hash_stable():
    h1 = chunk_content_hash("same text")
    h2 = chunk_content_hash("same text")
    assert h1 == h2


def test_incremental_reuse():
    chunks = ["chunk one", "chunk two"]
    prior = {
        "chunk_extractions": [
            {"chunk_index": 0, "content_hash": chunk_content_hash("chunk one"), "output": {"objective": ["a"]}},
        ]
    }
    calls: list[int] = []

    def extract_fn(_text, index, _total):
        calls.append(index)
        return {"objective": ["new"]}

    rows, stats = incremental_extract_rows(chunks, [0, 1], prior, extract_fn=extract_fn)
    assert 0 in stats["chunks_reused"]
    assert 1 in stats["chunks_extracted"]
    assert len(calls) == 1


def test_state_field_jaccard():
    base = {"completed_work": ["a", "b"], "active_problems": ["x"], "constraints": []}
    inc = {"completed_work": ["a", "c"], "active_problems": ["x"], "constraints": []}
    scores = state_field_jaccard(base, inc)
    assert scores["completed_work"] == pytest.approx(1 / 3)
    assert scores["active_problems"] == 1.0


def test_append_transcript_helper():
    from continuator.commands.benchmark_incremental_cmd import append_transcript

    assert append_transcript("base", "suffix") == "base\n\nsuffix"
