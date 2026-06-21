"""Cross-platform runtime defaults for Continuator."""
from __future__ import annotations

import platform
import sys


def default_extractor_backend() -> str:
    """MLX on Apple Silicon macOS; transformers elsewhere (Windows, Linux, Intel Mac)."""
    if sys.platform == "darwin" and platform.machine().lower() in {"arm64", "aarch64"}:
        return "mlx"
    return "transformers"
