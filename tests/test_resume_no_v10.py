"""Resume must not invoke V10 on cached path."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from checkpoint_record_v2 import build_record_from_session, hash_transcript
from checkpoint_state_v1 import build_checkpoint_state
from checkpoint_store_v2 import save_checkpoint
from continuator.platform.resume import load_and_resume, resume_cached


def _sample_record(tmp_path: Path) -> Path:
    chunks = [
      {
          "chunk_index": 0,
          "objective": ["Goal"],
          "current_state": "Working.",
          "completed_work": ["Done"],
          "active_problems": [],
          "constraints": [],
          "continuation_context": "Next step.",
      }
    ]
    state = build_checkpoint_state(chunks, label="demo", project="demo", total_chunks=1)
    session = {
      "checkpoint_state": dict(state),
      "continuation_briefing": "CACHED BRIEFING",
      "conversation_explanation": "explain",
      "exports": {},
      "archetype": "mixed",
      "transcript_chars": 10,
      "chunking": {"chunk_count": 1},
      "chunk_selection": {"selected_indices": [0], "k": 1, "total_chunks": 1},
      "v10_rows": [{"chunk_index": 0, "input_chars": 5, "output": chunks[0]}],
      "_chunks_text": ["hello"],
    }
    record = build_record_from_session(
        session,
        source_meta={"kind": "file", "path": "t.txt", "transcript": "hello", "sha256": hash_transcript("hello"), "char_count": 5},
        project="demo",
        tier="full",
    )
    return save_checkpoint(record, path=tmp_path / "checkpoint.yaml")


def test_resume_cached_no_v10(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = _sample_record(tmp_path)
    with patch("memory_model_v1.extract_chunks_at_indices") as mock_extract:
        text, record, elapsed = load_and_resume(target=str(path), fmt="briefing")
        mock_extract.assert_not_called()
    assert "CACHED BRIEFING" in text
    assert elapsed < 500


def test_resume_cached_direct():
    record = {
        "state": {"objective": ["g"], "current_state": "s", "next_action": "n", "completed_work": [], "active_problems": [], "constraints": []},
        "cached_exports": {"briefing": "direct cache"},
    }
    assert resume_cached(record) == "direct cache"
