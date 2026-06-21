"""Minimal checkpoint YAML writer for validation experiment."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_CHECKPOINT_FIELDS = (
    "project",
    "objective",
    "current_state",
    "completed_work",
    "active_problems",
    "constraints",
    "next_action",
)


def slugify_project(name: str) -> str:
    slug = re.sub(r"[^\w\-]+", "-", (name or "").strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:64] or "conversation"


def validate_checkpoint_state(state: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not str(state.get("next_action") or "").strip():
        issues.append("missing next_action")
    if not str(state.get("current_state") or "").strip() and not state.get("completed_work"):
        issues.append("missing current_state and completed_work")
    if not state.get("objective"):
        issues.append("missing objective")
    return issues


def _yaml_quote(value: str) -> str:
    if not value:
        return '""'
    if "\n" in value or ":" in value or value.startswith(("-", "#", "|", ">")):
        escaped = value.replace("\n", "\n")
        return "|\n" + "".join(f"  {line}\n" for line in escaped.splitlines())
    if re.search(r'[\[\]{},&*#?|\-<>=!%@`]', value) or value != value.strip():
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def render_checkpoint_yaml(state: dict[str, Any]) -> str:
    """Render minimal checkpoint YAML from structured state."""
    lines: list[str] = []
    project = str(state.get("project") or "")
    lines.append(f"project: {_yaml_quote(project)}")

    for field in _CHECKPOINT_FIELDS:
        if field == "project":
            continue
        value = state.get(field)
        if isinstance(value, list):
            if value:
                lines.append(f"{field}:")
                for item in value:
                    lines.append(f"  - {_yaml_quote(str(item))}")
            else:
                lines.append(f"{field}: []")
        else:
            lines.append(f"{field}: {_yaml_quote(str(value or ''))}")

    return "\n".join(lines).rstrip() + "\n"


def write_checkpoint_yaml(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_checkpoint_yaml(state), encoding="utf-8")
