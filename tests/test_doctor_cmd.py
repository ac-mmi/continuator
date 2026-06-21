"""Doctor command and mock checkpoint detection."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from continuator.checkpoint_mock import briefing_looks_mock, record_looks_mock
from continuator.extraction_status import collect_extraction_status, find_stale_mock_checkpoints


def test_briefing_looks_mock():
    assert briefing_looks_mock("mock conversation topic (chunk 1/1)")
    assert not briefing_looks_mock("Fix neck posture with daily exercises")


def test_record_looks_mock_engine_field():
    record = {"engine": {"extractor_backend": "mock"}, "cached_exports": {"briefing": "ok"}}
    assert record_looks_mock(record)


def test_collect_extraction_status_mock(monkeypatch):
    monkeypatch.setenv("MEMORY_EXTRACTOR_BACKEND", "mock")
    status = collect_extraction_status()
    assert status.effective_backend == "mock"
    assert not status.ready_for_real_extraction
    assert status.issues


def test_find_stale_mock_checkpoint(tmp_path: Path):
    ckpt = tmp_path / ".continuator" / "checkpoint.yaml"
    ckpt.parent.mkdir(parents=True)
    ckpt.write_text(
        "engine:\n  extractor_backend: mock\ncached_exports:\n  briefing: mock conversation topic\n",
        encoding="utf-8",
    )
    found = find_stale_mock_checkpoints(tmp_path)
    assert ckpt in found


def test_doctor_cli_json(monkeypatch):
    monkeypatch.setenv("MEMORY_EXTRACTOR_BACKEND", "mock")
    from continuator.cli import main

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(["doctor", "--json"])
    payload = json.loads(buf.getvalue())
    assert payload["effective_backend"] == "mock"
    assert code == 1
