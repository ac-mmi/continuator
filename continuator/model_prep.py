"""User-visible model download + mock-backend warnings before extraction."""
from __future__ import annotations

import os

from continuator.runtime import ensure_runtime
from continuator.silence import real_stderr


def prepare_extraction(
    console: object | None = None,
    *,
    quiet: bool = False,
    verbose: bool = False,
) -> str:
    """Ensure runtime, warn on mock, download models on first run (outside silence shield)."""
    ensure_runtime()
    backend = str(os.environ.get("MEMORY_EXTRACTOR_BACKEND", "")).strip().lower()

    if backend == "mock":
        _warn_mock(console=console, quiet=quiet)
        return "mock"

    if not quiet:
        _say(
            console,
            f"Extraction backend: {backend or 'auto'}",
            quiet=False,
            warn=False,
        )
    from adapter_loader import hf_repo_for_model
    from extraction_bootstrap_v1 import adapter_needs_download, ensure_extraction_assets

    if adapter_needs_download():
        repo = hf_repo_for_model("v10")
        msg = f"First run: downloading V10 model from Hugging Face ({repo})…"
        if console is not None and hasattr(console, "on_model_download"):
            console.on_model_download(msg)
        else:
            _say(console, msg, quiet=quiet, warn=True)
        if verbose and not quiet:
            _say(
                console,
                "This is one-time (~1–2 GB). Progress may appear below.",
                quiet=False,
                warn=False,
            )
        _run_download_with_progress(ensure_extraction_assets)
        _say(console, "Model download complete.", quiet=quiet, warn=False)
    else:
        ensure_extraction_assets()

    return backend


def _warn_mock(*, console: object | None, quiet: bool) -> None:
    if quiet:
        return
    msg = (
        "MEMORY_EXTRACTOR_BACKEND=mock — output is synthetic test data, not real extraction.\n"
        "  Fix: unset the variable and install a real backend:\n"
        "    macOS/Linux: unset MEMORY_EXTRACTOR_BACKEND\n"
        "    Windows:     Remove-Item Env:MEMORY_EXTRACTOR_BACKEND\n"
        "  Then: pip install -e \".[transformers]\" (Windows/Linux) or pip install -e \".[mlx]\" (Apple Silicon)"
    )
    if console is not None and hasattr(console, "step_warn"):
        console.step_warn("MEMORY_EXTRACTOR_BACKEND=mock — synthetic test output only")
        if hasattr(console, "verbose_line") and getattr(console, "verbose", False):
            console.verbose_line(msg.replace("\n", " "))
    else:
        print(msg, file=real_stderr(), flush=True)


def _say(console: object | None, message: str, *, quiet: bool, warn: bool) -> None:
    if quiet:
        return
    if console is not None:
        if warn and hasattr(console, "step_warn"):
            console.step_warn(message)
        elif hasattr(console, "say"):
            console.say(message)
        elif hasattr(console, "on_model_download"):
            console.on_model_download(message)
        return
    print(message, file=real_stderr(), flush=True)


def _run_download_with_progress(fn) -> None:
    """Run download with HF/tqdm progress visible on stderr."""
    prev = {
        "HF_HUB_DISABLE_PROGRESS_BARS": os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS"),
        "TQDM_DISABLE": os.environ.get("TQDM_DISABLE"),
    }
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "0"
    os.environ.pop("TQDM_DISABLE", None)
    try:
        fn()
    finally:
        for key, value in prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
