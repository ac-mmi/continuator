"""Tests for checkpoint_store_v2."""
from __future__ import annotations

from pathlib import Path

from checkpoint_record_v2 import migrate_v1_flat, serialize_checkpoint
from checkpoint_store_v2 import (
    default_checkpoint_root,
    load_checkpoint,
    resolve_checkpoint_path,
    save_checkpoint,
)


def test_atomic_save_load(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    record = migrate_v1_flat(
        {
            "project": "demo",
            "objective": ["Goal"],
            "current_state": "Working.",
            "completed_work": [],
            "active_problems": [],
            "constraints": [],
            "next_action": "Continue.",
        }
    )
    record["cached_exports"] = {"briefing": "hello"}
    path = save_checkpoint(record)
    assert path == default_checkpoint_root() / "checkpoint.yaml"
    loaded = load_checkpoint(path)
    assert loaded is not None
    assert loaded["project"] == "demo"


def test_resolve_explicit_output():
    p = resolve_checkpoint_path("demo", explicit="/tmp/out.yaml")
    assert str(p) == "/tmp/out.yaml"
