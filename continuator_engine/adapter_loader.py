"""Resolve LoRA adapter weights from Hugging Face Hub or a local path."""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HF_REPOS: dict[str, str] = {
    "v10": "ac-mmi/continuator-v10-lora",
    "v9": "continuator-ai/continuator-v9-lora",
}


def cache_root() -> Path:
    raw = os.getenv("CONTINUATOR_MODEL_CACHE", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.home() / ".cache" / "continuator" / "models"


def hf_repo_for_model(model: str) -> str:
    model = model.lower()
    override = os.getenv(f"MEMORY_EXTRACTOR_HF_REPO_{model.upper()}", "").strip()
    if override:
        return override
    generic = os.getenv("MEMORY_EXTRACTOR_HF_REPO", "").strip()
    if generic:
        return generic
    return DEFAULT_HF_REPOS.get(model, DEFAULT_HF_REPOS["v10"])


def _adapter_ready(path: Path) -> bool:
    if not path.is_dir():
        return False
    if not (path / "adapter_config.json").is_file():
        return False
    return bool(list(path.glob("*.safetensors")))


def _mock_adapter_dir() -> Path:
    root = Path(__file__).resolve().parent / ".mock_adapter"
    root.mkdir(exist_ok=True)
    config = root / "adapter_config.json"
    if not config.is_file():
        config.write_text('{"model": "mock"}', encoding="utf-8")
    weights = root / "adapters.safetensors"
    if not weights.is_file():
        weights.write_bytes(b"")
    return root


def ensure_adapter(model: str) -> Path:
    """Return a directory containing adapter_config.json and *.safetensors."""
    backend = os.getenv("MEMORY_EXTRACTOR_BACKEND", "").strip().lower()
    if backend == "mock":
        return _mock_adapter_dir()

    explicit = os.getenv("MEMORY_EXTRACTOR_ADAPTER_PATH", "").strip()
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if _adapter_ready(path):
            return path
        raise FileNotFoundError(
            f"MEMORY_EXTRACTOR_ADAPTER_PATH is set but adapter files are missing: {path}"
        )

    cache_dir = cache_root() / model
    if _adapter_ready(cache_dir):
        return cache_dir

    repo_id = hf_repo_for_model(model)
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "huggingface_hub is required to download the LoRA adapter. "
            "Install with: pip install huggingface_hub"
        ) from exc

    token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(cache_dir),
        local_dir_use_symlinks=False,
        token=token or None,
    )
    if not _adapter_ready(cache_dir):
        raise FileNotFoundError(
            f"Download from Hugging Face repo {repo_id!r} did not produce adapter files "
            f"under {cache_dir}. Set MEMORY_EXTRACTOR_ADAPTER_PATH to a local adapter directory, "
            f"or publish the model and set MEMORY_EXTRACTOR_HF_REPO."
        )
    return cache_dir
