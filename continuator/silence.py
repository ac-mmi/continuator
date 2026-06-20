"""Suppress third-party library noise during product CLI runs."""
from __future__ import annotations

import logging
import os
import sys
import warnings
from contextlib import contextmanager
from typing import Iterator, TextIO

_CONFIGURED = False
_REAL_STDOUT: TextIO | None = None
_REAL_STDERR: TextIO | None = None


def real_stdout() -> TextIO:
    return _REAL_STDOUT or sys.stdout


def real_stderr() -> TextIO:
    return _REAL_STDERR or sys.stderr


def _apply_warning_filters() -> None:
    """Silence numpy/sklearn/sentence-transformers numerical and import warnings."""
    for category in (DeprecationWarning, FutureWarning, UserWarning, RuntimeWarning, PendingDeprecationWarning):
        warnings.filterwarnings("ignore", category=category)

    # sklearn KMeans on chunk embeddings can emit matmul RuntimeWarnings (harmless).
    for pattern in (
        ".*matmul.*",
        ".*sklearn.*",
        ".*divide by zero.*",
        ".*overflow encountered.*",
        ".*invalid value encountered.*",
        ".*SentenceTransformer.*",
        ".*tokenizer.*",
    ):
        warnings.filterwarnings("ignore", message=pattern)

    try:
        import numpy as np

        warnings.filterwarnings("ignore", category=np.VisibleDeprecationWarning)  # type: ignore[attr-defined]
    except Exception:
        pass


def configure_silence(*, verbose: bool = False) -> None:
    """Apply process-wide log/env settings (safe to call multiple times)."""
    global _CONFIGURED, _REAL_STDOUT, _REAL_STDERR
    if _REAL_STDOUT is None:
        _REAL_STDOUT = sys.stdout
    if _REAL_STDERR is None:
        _REAL_STDERR = sys.stderr

    if verbose:
        return

    os.environ.setdefault("CONTINUATOR_SUPPRESS_LOGS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("TQDM_DISABLE", "1")
    os.environ.setdefault("PYTHONWARNINGS", "ignore::RuntimeWarning,ignore::UserWarning")

    _apply_warning_filters()

    if _CONFIGURED:
        return
    _CONFIGURED = True

    for name in (
        "transformers",
        "sentence_transformers",
        "huggingface_hub",
        "urllib3",
        "filelock",
        "mlx",
        "mlx_lm",
        "httpx",
        "datasets",
        "sklearn",
    ):
        logging.getLogger(name).setLevel(logging.ERROR)


@contextmanager
def shield_libraries(*, verbose: bool = False) -> Iterator[None]:
    """Redirect stdout/stderr and suppress warnings during model/ranker work."""
    configure_silence(verbose=verbose)
    if verbose:
        yield
        return

    sink = open(os.devnull, "w", encoding="utf-8")
    saved_out, saved_err = sys.stdout, sys.stderr
    sys.stdout = sink
    sys.stderr = sink
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            yield
        finally:
            sys.stdout = saved_out
            sys.stderr = saved_err
            sink.close()
