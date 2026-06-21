"""Tests for validation_runner_v1.py."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "scripts" / "validation_runner_v1.py"


def test_validation_runner_smoke(tmp_path: Path):
    out = tmp_path / "validation_runs"
    env = {**dict(__import__("os").environ), "MEMORY_EXTRACTOR_BACKEND": "mock"}
    proc = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            str(ROOT / "examples" / "neck.txt"),
            "-o",
            str(out),
            "--mock",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    session = out / "neck"
    assert (session / "checkpoint.yaml").is_file()
    assert (session / "resume.txt").is_file()
    assert (session / "claude_prompt.txt").is_file()
    assert (session / "chatgpt_prompt.txt").is_file()
    assert (session / "gemini_prompt.txt").is_file()
    meta = json.loads((session / "metadata.json").read_text(encoding="utf-8"))
    assert meta["session_name"] == "neck"
    assert meta["resume_ms"] < 500
    assert "You are continuing an interrupted work session" in (session / "claude_prompt.txt").read_text()
