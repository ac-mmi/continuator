"""Download extraction assets before the library silence shield runs."""
from __future__ import annotations

import os


def active_backend() -> str:
    raw = str(os.getenv("MEMORY_EXTRACTOR_BACKEND", "")).strip().lower()
    if raw:
        return raw
    from platform_defaults import default_extractor_backend

    return default_extractor_backend()


def adapter_needs_download() -> bool:
    if active_backend() == "mock":
        return False
    from adapter_loader import _adapter_ready, cache_root

    return not _adapter_ready(cache_root() / "v10")


def ensure_extraction_assets() -> None:
    """Download LoRA adapter and chunk embedder if missing (no-op for mock)."""
    if active_backend() == "mock":
        return

    from adapter_loader import ensure_adapter

    ensure_adapter("v10")

    try:
        from chunk_selector_v2_cluster import _load_embedder

        _load_embedder()
    except Exception:
        pass
