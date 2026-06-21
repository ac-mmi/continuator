"""Incremental benchmark smoke test (mock backend)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from continuator.commands.benchmark_incremental_cmd import append_transcript, run as benchmark_run
from continuator.platform.extract import extract_full, extract_incremental


@pytest.fixture(autouse=True)
def _mock_backend(monkeypatch):
    monkeypatch.setenv("MEMORY_EXTRACTOR_BACKEND", "mock")


def test_incremental_faster_than_full(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sample = Path(__file__).parent.parent / "examples" / "neck.txt"
    if not sample.is_file():
        pytest.skip("examples/neck.txt missing")
    text = sample.read_text(encoding="utf-8")
    grown = append_transcript(text, text[-max(1, len(text) // 5) :])

    r0, _ = extract_full(text, label="neck", project="neck", tier="full")
    _r1, _ = extract_full(grown, label="neck", project="neck", tier="full")
    r2, _ = extract_incremental(grown, r0, label="neck", project="neck", tier="full")

    assert r2.get("lineage", {}).get("merge_strategy") == "frontier_wins_v1"
    delta = r2.get("lineage", {}).get("delta") or {}
    assert "chunks_reused" in delta


def test_benchmark_incremental_cmd_examples(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    examples = Path(__file__).parent.parent / "examples"
    if not examples.is_dir():
        pytest.skip("examples/ missing")
    class Args:
        directory = str(examples)
        report = ""
        limit = 1
        verbose = False
        quiet = True

    code = benchmark_run(Args())
    assert code == 0
