"""Checkpoint v2 filesystem store."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from checkpoint_record_v2 import parse_checkpoint_file, serialize_checkpoint

CHECKPOINT_FILENAME = "checkpoint.yaml"


def default_checkpoint_root(cwd: Path | None = None) -> Path:
    return (cwd or Path.cwd()) / ".continuator"


def legacy_checkpoint_path(project: str, cwd: Path | None = None) -> Path:
    return (cwd or Path.cwd()) / "checkpoints" / f"{project}.yaml"


def global_checkpoint_path(project: str) -> Path:
    override = (os.getenv("CONTINUATOR_CHECKPOINT_DIR") or "").strip()
    root = Path(override).expanduser() if override else Path.home() / ".continuator" / "projects"
    return root / project / CHECKPOINT_FILENAME


def resolve_checkpoint_path(
    project: str,
    *,
    cwd: Path | None = None,
    explicit: Path | str | None = None,
) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    return default_checkpoint_root(cwd) / CHECKPOINT_FILENAME


def resolve_read_path(
    target: str | None = None,
    *,
    project: str | None = None,
    cwd: Path | None = None,
) -> Path | None:
    """Resolve checkpoint file for read/resume."""
    base = cwd or Path.cwd()
    if target:
        p = Path(target).expanduser()
        if p.is_file():
            return p
        if project:
            legacy = legacy_checkpoint_path(project, base)
            if legacy.is_file():
                return legacy
        default_p = default_checkpoint_root(base) / CHECKPOINT_FILENAME
        if default_p.is_file():
            return default_p
        return None

    default_p = default_checkpoint_root(base) / CHECKPOINT_FILENAME
    if default_p.is_file():
        return default_p

    if project:
        legacy = legacy_checkpoint_path(project, base)
        if legacy.is_file():
            return legacy
        global_p = global_checkpoint_path(project)
        if global_p.is_file():
            return global_p
    else:
        legacy_dir = base / "checkpoints"
        if legacy_dir.is_dir():
            yamls = sorted(legacy_dir.glob("*.yaml"), key=lambda p: p.stat().st_mtime, reverse=True)
            if yamls:
                return yamls[0]
    return None


def load_checkpoint(path: Path | str | None = None, *, project: str | None = None, cwd: Path | None = None) -> dict[str, Any] | None:
    if path is None:
        resolved = resolve_read_path(project=project, cwd=cwd)
        if resolved is None:
            return None
        path = resolved
    return parse_checkpoint_file(path)


def save_checkpoint(record: dict[str, Any], path: Path | str | None = None, *, cwd: Path | None = None) -> Path:
    out = Path(path) if path else resolve_checkpoint_path(str(record.get("project") or "conversation"), cwd=cwd)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(serialize_checkpoint(record), encoding="utf-8")
    tmp.replace(out)
    try:
        out.chmod(0o600)
    except OSError:
        pass
    return out


def find_checkpoint_for_update(project: str, *, cwd: Path | None = None) -> dict[str, Any] | None:
    base = cwd or Path.cwd()
    for candidate in (
        default_checkpoint_root(base) / CHECKPOINT_FILENAME,
        legacy_checkpoint_path(project, base),
        global_checkpoint_path(project),
    ):
        if candidate.is_file():
            try:
                return parse_checkpoint_file(candidate)
            except (ValueError, OSError):
                continue
    return None


__all__ = [
    "CHECKPOINT_FILENAME",
    "default_checkpoint_root",
    "find_checkpoint_for_update",
    "global_checkpoint_path",
    "legacy_checkpoint_path",
    "load_checkpoint",
    "resolve_checkpoint_path",
    "resolve_read_path",
    "save_checkpoint",
]
