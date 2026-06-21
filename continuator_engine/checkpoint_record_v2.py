"""CheckpointRecord v2 — parse, validate, serialize, build from session."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml

from checkpoint_state_v1 import CheckpointState, build_checkpoint_state, render_briefing_from_checkpoint_state
from continuation_export_v2_frontier import frontier_cutoff_index, frontier_band_size

FORMAT_VERSION = 2
PRODUCT_BASELINE = "v10-050+repair+continuation_export_v2_frontier+explain_v1"

Tier = Literal["minimal", "standard", "full"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_transcript(text: str) -> str:
    return (text or "").strip()


def hash_transcript(text: str) -> str:
    return hashlib.sha256(normalize_transcript(text).encode("utf-8")).hexdigest()


def generate_checkpoint_id(*, project: str, created_at: str, sha256: str) -> str:
    payload = f"{project}:{created_at}:{sha256}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:8]


def _listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    s = str(value).strip()
    return [s] if s else []


def state_to_checkpoint_state(state: dict[str, Any]) -> CheckpointState:
    return CheckpointState(
        project=str(state.get("project") or ""),
        project_title=str(state.get("project_title") or state.get("project") or "Conversation"),
        objective=_listify(state.get("objective")),
        objective_display=str(state.get("objective_display") or ""),
        current_state=str(state.get("current_state") or ""),
        completed_work=_listify(state.get("completed_work")),
        active_problems=_listify(state.get("active_problems")),
        constraints=_listify(state.get("constraints")),
        next_action=str(state.get("next_action") or ""),
    )


def record_state_to_v2(state: dict[str, Any]) -> dict[str, Any]:
    """Map CheckpointState dict to v2 state block."""
    return {
        "project_title": str(state.get("project_title") or state.get("project") or ""),
        "objective": _listify(state.get("objective")),
        "current_state": str(state.get("current_state") or ""),
        "completed_work": _listify(state.get("completed_work")),
        "active_problems": _listify(state.get("active_problems")),
        "constraints": _listify(state.get("constraints")),
        "next_action": str(state.get("next_action") or ""),
        "closure_detected": bool(state.get("closure_detected", False)),
    }


def build_cached_exports(session: dict[str, Any]) -> dict[str, str]:
    exports = dict(session.get("exports") or {})
    briefing = str(session.get("continuation_briefing") or exports.get("continuation_briefing") or "").strip()
    explain = str(session.get("conversation_explanation") or exports.get("explain") or "").strip()
    return {
        "briefing": briefing,
        "explain": explain,
        "claude": str(exports.get("claude") or "").strip(),
        "chatgpt": str(exports.get("chatgpt") or "").strip(),
        "gemini": str(exports.get("gemini") or "").strip(),
        "markdown": str(exports.get("markdown") or "").strip(),
    }


def build_pipeline_section(
    session: dict[str, Any],
    *,
    v10_rows: list[dict[str, Any]] | None = None,
    rank_audit: dict[str, Any] | None = None,
    include_extractions: bool = True,
) -> dict[str, Any]:
    from checkpoint_merge_v1 import chunk_content_hash

    chunking = dict(session.get("chunking") or {})
    selection = dict(session.get("chunk_selection") or {})
    n = int(selection.get("total_chunks") or chunking.get("chunk_count") or 0)
    cutoff = frontier_cutoff_index(n) if n else 0
    selected = [int(i) for i in selection.get("selected_indices") or []]

    pipeline: dict[str, Any] = {
        "chunking": {
            "strategy": chunking.get("strategy", "paragraph_chunk_overlap"),
            "chunk_count": n,
        },
        "ranker": {
            "strategy": selection.get("strategy") or rank_audit.get("selection_strategy") if rank_audit else "full",
            "k": int(selection.get("k") or 0),
            "total_chunks": n,
            "selected_indices": selected,
            "locked_indices": list(rank_audit.get("locked_indices") or []) if rank_audit else [],
        },
        "frontier": {
            "cutoff_index": cutoff,
            "band_size": frontier_band_size(n) if n else 0,
            "indices": list(range(cutoff, n)) if n else [],
            "selected_in_frontier": [i for i in selected if i >= cutoff],
        },
    }

    if include_extractions:
        rows = v10_rows if v10_rows is not None else list(session.get("v10_rows") or [])
        extractions: list[dict[str, Any]] = []
        chunks_text = list(session.get("_chunks_text") or [])
        for row in rows:
            idx = int(row.get("chunk_index", 0))
            chunk_text = chunks_text[idx] if idx < len(chunks_text) else ""
            extractions.append(
                {
                    "chunk_index": idx,
                    "input_chars": int(row.get("input_chars") or len(chunk_text)),
                    "content_hash": chunk_content_hash(chunk_text),
                    "parse_ok": bool(dict(row.get("output") or {}).get("parse_ok", True)),
                    "output": dict(row.get("output") or {}),
                }
            )
        pipeline["chunk_extractions"] = extractions

    return pipeline


def build_stats(session: dict[str, Any], *, transcript_chars: int, cached_exports: dict[str, str]) -> dict[str, Any]:
    briefing = cached_exports.get("briefing") or ""
    ratio = round(transcript_chars / max(len(briefing), 1), 1) if briefing else 0.0
    metrics = dict(session.get("metrics") or {}).get("v10") or {}
    return {
        "briefing_words": int(session.get("briefing_words") or len(briefing.split())),
        "explain_words": int(session.get("explain_words") or 0),
        "compression_ratio": ratio,
        "extraction_parse_rate": float(metrics.get("parse_rate") or 0.0),
        "runtime_seconds": float(session.get("_runtime_seconds") or 0.0),
    }


def build_record_from_session(
    session: dict[str, Any],
    *,
    source_meta: dict[str, Any],
    project: str,
    label: str = "",
    tier: Tier = "full",
    lineage: dict[str, Any] | None = None,
    created_at: str | None = None,
    parent_created_at: str | None = None,
) -> dict[str, Any]:
    """Build v2 CheckpointRecord from run_continuator session dict."""
    now = created_at or str(session.get("created_at") or _utc_now())
    sha = str(source_meta.get("sha256") or hash_transcript(str(source_meta.get("transcript") or "")))
    proj = project or label or "conversation"
    checkpoint_id = generate_checkpoint_id(project=proj, created_at=now, sha256=sha)

    cp_state = dict(session.get("checkpoint_state") or {})
    state_block = record_state_to_v2(cp_state)
    cached = build_cached_exports(session)

    record: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "id": checkpoint_id,
        "project": proj,
        "label": label or str(session.get("label") or proj),
        "message": str(source_meta.get("message") or ""),
        "created_at": parent_created_at or now,
        "updated_at": now,
        "source": {
            "kind": str(source_meta.get("kind") or "file"),
            "path": str(source_meta.get("path") or ""),
            "platform": str(source_meta.get("platform") or "unknown"),
            "conversation_id": str(source_meta.get("conversation_id") or ""),
            "sha256": sha,
            "char_count": int(source_meta.get("char_count") or session.get("transcript_chars") or 0),
            "message_count": int(source_meta.get("message_count") or 0),
            "transcript_snapshot": str(source_meta.get("transcript_snapshot") or source_meta.get("transcript") or ""),
        },
        "engine": {
            "baseline": str(session.get("product_baseline") or PRODUCT_BASELINE),
            "memory_model": "v10",
            "archetype": str(session.get("archetype") or "mixed"),
            "extractor_backend": str(
                os.getenv("MEMORY_EXTRACTOR_BACKEND") or source_meta.get("extractor_backend") or "auto"
            ),
        },
        "state": state_block,
    }

    if tier in ("standard", "full"):
        record["cached_exports"] = cached
        record["stats"] = build_stats(
            session,
            transcript_chars=int(record["source"]["char_count"]),
            cached_exports=cached,
        )

    if tier == "full":
        record["pipeline"] = build_pipeline_section(session)

    if lineage:
        record["lineage"] = lineage

    issues = validate_record(record)
    if issues:
        raise ValueError("invalid checkpoint record: " + ", ".join(issues))
    return record


def validate_record(record: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if int(record.get("format_version") or 0) != FORMAT_VERSION:
        issues.append("unsupported format_version")
    state = dict(record.get("state") or {})
    if not str(state.get("next_action") or "").strip():
        issues.append("missing next_action")
    if not str(state.get("current_state") or "").strip() and not state.get("completed_work"):
        issues.append("missing current_state and completed_work")
    if not state.get("objective"):
        issues.append("missing objective")
    return issues


def migrate_v1_flat(data: dict[str, Any]) -> dict[str, Any]:
    """Wrap validation experiment flat yaml as v2."""
    now = _utc_now()
    project = str(data.get("project") or "conversation")
    state = record_state_to_v2(
        {
            "project": project,
            "project_title": project,
            "objective": data.get("objective"),
            "current_state": data.get("current_state"),
            "completed_work": data.get("completed_work"),
            "active_problems": data.get("active_problems"),
            "constraints": data.get("constraints"),
            "next_action": data.get("next_action"),
        }
    )
    sha = hash_transcript("")
    record = {
        "format_version": FORMAT_VERSION,
        "id": generate_checkpoint_id(project=project, created_at=now, sha256=sha),
        "project": project,
        "label": project,
        "message": "",
        "created_at": now,
        "updated_at": now,
        "source": {
            "kind": "file",
            "path": "",
            "platform": "unknown",
            "conversation_id": "",
            "sha256": sha,
            "char_count": 0,
            "message_count": 0,
            "transcript_snapshot": "",
        },
        "engine": {
            "baseline": PRODUCT_BASELINE,
            "memory_model": "v10",
            "archetype": "mixed",
            "extractor_backend": "unknown",
        },
        "state": state,
        "cached_exports": {},
        "_migrated_from_v1": True,
    }
    return record


def parse_checkpoint_raw(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("checkpoint file must be a mapping")
    if "checkpoint" in raw:
        record = dict(raw["checkpoint"])
    elif "project" in raw and "objective" in raw:
        record = migrate_v1_flat(raw)
    else:
        raise ValueError("unrecognized checkpoint format")
    if int(record.get("format_version") or 0) != FORMAT_VERSION:
        raise ValueError(f"unsupported format_version: {record.get('format_version')}")
    return record


def parse_checkpoint_file(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        raw = json.loads(text)
    else:
        raw = yaml.safe_load(text)
    record = parse_checkpoint_raw(raw)
    issues = validate_record(record)
    if issues and not record.get("_migrated_from_v1"):
        raise ValueError("invalid checkpoint: " + ", ".join(issues))
    return record


def serialize_checkpoint(record: dict[str, Any], *, fmt: Literal["yaml", "json"] = "yaml") -> str:
    payload = {"checkpoint": record}
    if fmt == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    return yaml.safe_dump(payload, default_flow_style=False, allow_unicode=True, sort_keys=False)


def render_from_record(
    record: dict[str, Any],
    fmt: str,
) -> str:
    """Render export view from record without V10."""
    cached = dict(record.get("cached_exports") or {})
    key = fmt if fmt != "briefing" else "briefing"
    if key in cached and str(cached[key]).strip():
        return str(cached[key]).strip()

    if fmt == "state":
        return yaml.safe_dump({"state": record.get("state")}, default_flow_style=False)

    if fmt == "briefing":
        state = state_to_checkpoint_state(
            {
                **dict(record.get("state") or {}),
                "project": record.get("project"),
                "objective_display": "",
            }
        )
        if state.get("objective") or state.get("next_action"):
            return render_briefing_from_checkpoint_state(state)

    raise ValueError(f"missing cached export for format '{fmt}'; run checkpoint again or use --refresh")


__all__ = [
    "FORMAT_VERSION",
    "PRODUCT_BASELINE",
    "build_cached_exports",
    "build_pipeline_section",
    "build_record_from_session",
    "build_stats",
    "generate_checkpoint_id",
    "hash_transcript",
    "migrate_v1_flat",
    "normalize_transcript",
    "parse_checkpoint_file",
    "parse_checkpoint_raw",
    "record_state_to_v2",
    "render_from_record",
    "serialize_checkpoint",
    "state_to_checkpoint_state",
    "validate_record",
]
