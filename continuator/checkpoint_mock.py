"""Detect mock / smoke-test checkpoints and briefing text."""
from __future__ import annotations

from typing import Any

_MOCK_MARKERS = (
    "mock conversation topic",
    "mock goal chunk",
    "mock summary for chunk",
)


def briefing_looks_mock(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _MOCK_MARKERS)


def record_looks_mock(record: dict[str, Any]) -> bool:
    engine = dict(record.get("engine") or {})
    if str(engine.get("extractor_backend") or "").strip().lower() == "mock":
        return True
    cached = dict(record.get("cached_exports") or {})
    briefing = str(cached.get("briefing") or "")
    return briefing_looks_mock(briefing)
