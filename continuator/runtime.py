"""Bootstrap continuator_engine and shared runtime defaults."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_EXPORT_TARGETS = frozenset({"claude", "chatgpt", "gemini", "markdown"})


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def engine_root() -> Path:
    override = (
        os.environ.get("CONTINUATOR_ENGINE_ROOT")
        or os.environ.get("MEMORY_BRAIN_ROOT")
        or ""
    ).strip()
    if override:
        root = Path(override).expanduser().resolve()
        if root.is_dir():
            return root

    candidates = [
        repo_root() / "continuator_engine",
        Path(__file__).resolve().parent / "continuator_engine",
    ]
    for root in candidates:
        if (root / "handoff_evaluation_v1.py").is_file():
            return root
    raise RuntimeError(
        "continuator_engine not found. Install from the repo root (pip install -e .) "
        "or set CONTINUATOR_ENGINE_ROOT to the engine directory."
    )


def memory_brain_root() -> Path:
    """Backward-compatible alias for engine_root()."""
    return engine_root()


def ensure_runtime() -> Path:
    """Add continuator_engine to sys.path and apply product defaults."""
    root = engine_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    os.environ.setdefault("MEMORY_BRAIN_API_MODE", "1")
    os.environ.setdefault("MEMORY_EXTRACTOR_BACKEND", "mlx")
    os.environ.setdefault("PIPELINE_MODE", "minimal")
    os.environ.setdefault("MEMORY_MODEL", "v10")
    os.environ.setdefault("MEMORY_EXTRACTOR_PROFILE", "fast")
    os.environ.setdefault("MEMORY_EXTRACTOR_MAX_NEW_TOKENS", "1536")
    return root


def read_transcript(path: str) -> str:
    if path == "-":
        data = sys.stdin.read()
    else:
        p = Path(path).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"conversation file not found: {p}")
        if p.suffix.lower() == ".json":
            import json

            payload = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            if isinstance(payload, dict):
                data = (
                    payload.get("conversation")
                    or payload.get("body")
                    or payload.get("full_text")
                    or ""
                )
            else:
                data = str(payload)
        else:
            data = p.read_text(encoding="utf-8", errors="replace")
    text = (data or "").strip()
    if not text:
        raise ValueError("conversation is empty")
    return text


def label_from_path(path: str, explicit: str = "") -> str:
    if explicit.strip():
        return explicit.strip()
    if path == "-":
        return ""
    return Path(path).expanduser().stem


def default_export_path(source: str, target: str) -> Path:
    if source == "-":
        stem = "conversation"
    else:
        stem = Path(source).expanduser().stem
    safe = target if target in _EXPORT_TARGETS else "markdown"
    return Path(f"{stem}_{safe}.md")
