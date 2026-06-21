"""Runtime diagnostics for extraction backend and dependencies."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from continuator.runtime import ensure_runtime


@dataclass
class ExtractionStatus:
    env_backend: str
    effective_backend: str
    platform_default: str
    transformers_ok: bool
    torch_ok: bool
    mlx_ok: bool
    adapter_ready: bool
    issues: list[str] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)

    @property
    def ready_for_real_extraction(self) -> bool:
        if self.effective_backend == "mock":
            return False
        if self.effective_backend == "transformers":
            return self.transformers_ok and self.torch_ok
        if self.effective_backend == "mlx":
            return self.mlx_ok
        return False


def collect_extraction_status() -> ExtractionStatus:
    ensure_runtime()
    from platform_defaults import default_extractor_backend

    env_backend = str(os.environ.get("MEMORY_EXTRACTOR_BACKEND", "")).strip()
    platform_default = default_extractor_backend()
    effective = env_backend.lower() if env_backend else platform_default

    transformers_ok = _can_import("transformers") and _can_import("peft")
    torch_ok = _can_import("torch")
    mlx_ok = _can_import("mlx_lm")

    adapter_ready = False
    if effective != "mock":
        try:
            from extraction_bootstrap_v1 import adapter_needs_download

            adapter_ready = not adapter_needs_download()
        except Exception:
            adapter_ready = False

    issues: list[str] = []
    fixes: list[str] = []

    if effective == "mock":
        issues.append("MEMORY_EXTRACTOR_BACKEND is set to mock — output is synthetic test data.")
        fixes.append("Windows: Remove-Item Env:MEMORY_EXTRACTOR_BACKEND")
        fixes.append("macOS/Linux: unset MEMORY_EXTRACTOR_BACKEND")
    elif effective == "transformers":
        if not torch_ok:
            issues.append("PyTorch is not installed.")
            fixes.append('pip install -e ".[transformers]"')
        if not transformers_ok:
            issues.append("transformers/peft are not installed.")
            fixes.append('pip install -e ".[transformers]"')
    elif effective == "mlx":
        if not mlx_ok:
            issues.append("mlx-lm is not installed.")
            fixes.append('pip install -e ".[mlx]"')

    return ExtractionStatus(
        env_backend=env_backend,
        effective_backend=effective,
        platform_default=platform_default,
        transformers_ok=transformers_ok,
        torch_ok=torch_ok,
        mlx_ok=mlx_ok,
        adapter_ready=adapter_ready,
        issues=issues,
        fixes=fixes,
    )


def find_stale_mock_checkpoints(cwd: Path | None = None) -> list[Path]:
    base = cwd or Path.cwd()
    found: list[Path] = []
    for candidate in (
        base / ".continuator" / "checkpoint.yaml",
        base / "checkpoints",
    ):
        if candidate.is_file():
            if _path_looks_mock_checkpoint(candidate):
                found.append(candidate)
            continue
        if candidate.is_dir():
            for path in sorted(candidate.glob("*.yaml")):
                if _path_looks_mock_checkpoint(path):
                    found.append(path)
    return found


def _path_looks_mock_checkpoint(path: Path) -> bool:
    try:
        from checkpoint_record_v2 import parse_checkpoint_file

        record = parse_checkpoint_file(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        text = path.read_text(encoding="utf-8", errors="replace")
        from continuator.checkpoint_mock import briefing_looks_mock

        return briefing_looks_mock(text)
    from continuator.checkpoint_mock import record_looks_mock

    return record_looks_mock(record)


def _can_import(module: str) -> bool:
    try:
        __import__(module)
        return True
    except Exception:
        return False


def format_status_report(status: ExtractionStatus, *, cwd: Path | None = None) -> str:
    lines = [
        "Continuator extraction diagnostics",
        "",
        f"  MEMORY_EXTRACTOR_BACKEND (env): {status.env_backend or '(not set)'}",
        f"  Platform default:               {status.platform_default}",
        f"  Effective backend:              {status.effective_backend}",
        "",
        "Dependencies:",
        f"  torch:          {'ok' if status.torch_ok else 'missing'}",
        f"  transformers:   {'ok' if status.transformers_ok else 'missing'}",
        f"  mlx-lm:         {'ok' if status.mlx_ok else 'missing'}",
        f"  V10 adapter:    {'cached' if status.adapter_ready else 'not downloaded yet'}",
    ]

    mock_ckpts = find_stale_mock_checkpoints(cwd)
    if mock_ckpts:
        lines.append("")
        lines.append("Stale mock checkpoints in this repo (will show fake briefings on resume):")
        for path in mock_ckpts:
            lines.append(f"  - {path}")

    if status.issues:
        lines.append("")
        lines.append("Issues:")
        for issue in status.issues:
            lines.append(f"  ! {issue}")

    if status.fixes:
        lines.append("")
        lines.append("Try:")
        for fix in status.fixes:
            lines.append(f"  {fix}")

    if mock_ckpts:
        lines.append("  Delete mock checkpoints, then run: continuator continue FILE -v")
        lines.append("  Or refresh: continuator resume --refresh examples/neck.txt")

    lines.append("")
    if status.ready_for_real_extraction:
        lines.append("Ready for real extraction. First run: continuator continue examples/neck.txt -v")
    elif status.effective_backend != "mock" and not status.issues:
        lines.append("Backend looks configured. Run: continuator continue examples/neck.txt -v")
    else:
        lines.append("Not ready for real extraction until the issues above are fixed.")

    return "\n".join(lines) + "\n"
