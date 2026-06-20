"""Conversation transcript → structured memory extraction (LoRA Qwen2.5-1.5B)."""
from __future__ import annotations

import json
import os
import re
import time
from contextlib import nullcontext
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

_VERSION = "memory_extractor_v1"
_ROOT = Path(__file__).resolve().parent

_FENCE_RX = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.S | re.I)
_TRAILING_COMMA_RX = re.compile(r",\s*([}\]])")

_recall_profile_ctx: ContextVar[str | None] = ContextVar("memory_recall_profile", default=None)

_DEFAULT_CHUNK_CHARS = 6000
_DEFAULT_CHUNK_OVERLAP_CHARS = 500
_PROFILE_FAST = "fast"
_PROFILE_DEEP = "deep"
_PROFILE_COMPACT = "compact"
_PROFILE_V8_LIST_CAP = "v8_list_cap"
_PROFILE_V8_PRODUCTION = "v8_production"
# LoRA weights: Hugging Face Hub (see adapter_loader) or MEMORY_EXTRACTOR_ADAPTER_PATH.
_DEFAULT_MAX_NEW_TOKENS_FAST = 640
_DEFAULT_MAX_NEW_TOKENS_DEEP = 1024
_DEFAULT_MAX_CHUNKS_FAST = 8
_DEFAULT_MAX_CHUNKS_DEEP = 32
_DEFAULT_SHORT_CIRCUIT_CHARS = 4500

_PROFILE_ALIASES: dict[str, str] = {
    "fast": _PROFILE_FAST,
    "interactive": _PROFILE_FAST,
    "deep": _PROFILE_DEEP,
    "compact": _PROFILE_COMPACT,
    "v8_list_cap": _PROFILE_V8_LIST_CAP,
    "v8_production": _PROFILE_V8_PRODUCTION,
}

_STRICT_FACTUAL_EXTRACTION_RULES = """FACTUAL EXTRACTION RULES

Extract only information explicitly stated in the conversation.

Do NOT:
* infer missing information
* explain concepts
* add background knowledge
* add best practices unless directly stated
* rewrite statements into stronger claims
* merge multiple facts into a new conclusion

Every memory item must be traceable to a specific part of the conversation.

If unsure whether something was stated explicitly:
omit it.

Prefer omission over hallucination.

The goal is factual memory extraction, not summarization.

Do not generate educational content.

Do not generate recommendations.

Do not generate conclusions.

Only preserve information present in the source text.

Before finalizing each list item, self-check:
1. Was this explicitly stated?
2. Can this be traced to a sentence in the source?
3. Does this introduce outside knowledge?
If the answer to #3 is yes, remove the item.

"""

_COMPACT_EXTRACTION_INSTRUCTION = """Extract structured memory from this conversation transcript as JSON with these fields and limits:
- topic: 1 short sentence
- summary: maximum 50 words
- important_facts: maximum 5 items
- decisions: maximum 3 items
- current_goals: maximum 2 items
- open_questions: maximum 3 items
- next_steps: maximum 3 items

Be concise. Prefer short phrases over explanations. Do not repeat information across fields. Only include the highest-signal items. Output valid JSON only.

Transcript:
"""

_V8_LIST_CAP_EXTRACTION_INSTRUCTION = """Extract structured memory from this conversation transcript as JSON with these fields and limits:
- topic: 1 short sentence
- summary: maximum 50 words
- important_facts: maximum 12 items
- decisions: maximum 3 items
- current_goals: maximum 2 items
- open_questions: maximum 3 items
- next_steps: maximum 3 items

After reaching the limit for any list field, close that array with ] and continue to the next field. Do not repeat items. Output valid complete JSON only.

Transcript:
"""


_TOPIC_COVERAGE_EXTRACTION_RULES = """TOPIC COVERAGE RULES

Before generating memories:

1. Identify the major topics discussed in the chunk.
2. Rank topics by importance.
3. Distribute the memory budget across topics.

Do not spend all memory items on a single topic when multiple major topics exist.

If 5 facts are available, prefer:
Topic A: 2 facts
Topic B: 2 facts
Topic C: 1 fact

instead of:
Topic A: 5 facts

First identify the major topics discussed.

Ensure extracted memories cover as many major topics as possible.

Prefer breadth before depth.

When memory budget is limited, represent each major topic with at least one memory item before adding additional details.

"""

def _strict_factual_extraction_enabled() -> bool:
    return str(os.getenv("MEMORY_EXTRACTOR_STRICT_FACTUAL", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _topic_coverage_mode_enabled() -> bool:
    return str(os.getenv("MEMORY_EXTRACTOR_TOPIC_COVERAGE_MODE", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _prompt_rule_prefix() -> str:
    parts: list[str] = []
    if _topic_coverage_mode_enabled():
        parts.append(_TOPIC_COVERAGE_EXTRACTION_RULES)
    if _strict_factual_extraction_enabled():
        parts.append(_STRICT_FACTUAL_EXTRACTION_RULES)
    return "".join(parts)

_mlx_run_audit_ctx: ContextVar[dict[str, Any] | None] = ContextVar("mlx_run_audit", default=None)
_mlx_last_generation_audit: ContextVar[dict[str, Any] | None] = ContextVar(
    "mlx_last_generation_audit", default=None
)


def _mlx_measure_enabled() -> bool:
    return str(os.getenv("MEMORY_EXTRACTOR_MLX_MEASURE", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _repetition_stop_enabled() -> bool:
    return str(os.getenv("MEMORY_EXTRACTOR_ENABLE_REPETITION_STOP", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _repstop_min_facts() -> int:
    return max(1, _read_int_env("MEMORY_EXTRACTOR_REPSTOP_MIN_FACTS", 8))


def _repstop_min_tokens() -> int:
    return max(1, _read_int_env("MEMORY_EXTRACTOR_REPSTOP_MIN_TOKENS", 256))


def clear_mlx_model_cache() -> None:
    """Clear the cached MLX model bundle (measurement / cold-start runs)."""
    _load_mlx_impl.cache_clear()


def _mlx_run_audit() -> dict[str, Any]:
    audit = _mlx_run_audit_ctx.get()
    if isinstance(audit, dict):
        return audit
    return {"loads": [], "chunks": [], "stage_ms": {}}


def _mlx_run_audit_begin() -> object:
    return _mlx_run_audit_ctx.set({"loads": [], "chunks": [], "stage_ms": {}})


def _mlx_run_audit_reset(token: object) -> None:
    _mlx_run_audit_ctx.reset(token)


def pop_mlx_generation_audit() -> dict[str, Any] | None:
    audit = _mlx_last_generation_audit.get()
    _mlx_last_generation_audit.set(None)
    return audit if isinstance(audit, dict) else None


def _record_mlx_load(
    *,
    cache_state: str,
    load_start_ts: float,
    load_end_ts: float,
    load_latency_ms: float,
) -> None:
    entry = {
        "cache_state": cache_state,
        "load_start_ts": load_start_ts,
        "load_end_ts": load_end_ts,
        "load_latency_ms": round(load_latency_ms, 2),
    }
    _mlx_run_audit().setdefault("loads", []).append(entry)


class MemoryExtractorError(RuntimeError):
    pass


@dataclass
class ConversationMemoryRecord:
    topic: str = ""
    important_facts: list[str] = field(default_factory=list)
    current_goals: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    summary: str = ""
    objective: list[str] = field(default_factory=list)
    current_state: str = ""
    completed_work: list[str] = field(default_factory=list)
    active_problems: list[str] = field(default_factory=list)
    resolved_problems: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    continuation_context: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    parse_ok: bool = True
    model_id: str = ""
    latency_ms: float = 0.0
    condense_audit: dict[str, Any] = field(default_factory=dict)
    thread_chars_in: int = 0


def memory_extractor_enabled() -> bool:
    return str(os.getenv("MEMORY_EXTRACTOR_ENABLED", "1")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _read_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def normalize_memory_profile(value: str | None = None) -> str:
    """Normalize API/env profile names (incl. ``v8_production``)."""
    raw = str(
        value
        or os.getenv("MEMORY_EXTRACTOR_PROFILE", "")
        or os.getenv("MEMORY_EXTRACTOR_RECALL_PROFILE", "")
        or _PROFILE_FAST
    ).strip().lower()
    return _PROFILE_ALIASES.get(raw, _PROFILE_FAST)


def get_memory_extractor_profile() -> str | None:
    """Current request-scoped profile, or ``None`` if unset."""
    return _recall_profile_ctx.get()


def restore_memory_extractor_profile(profile: str | None) -> None:
    """Set profile in the current context (safe across streaming/task boundaries)."""
    if profile is None:
        _recall_profile_ctx.set(None)
    else:
        _recall_profile_ctx.set(profile)


def set_memory_extractor_profile(profile: str | None):
    """Request-scoped memory profile. Returns reset token."""
    if profile is None:
        return _recall_profile_ctx.set(None)
    return _recall_profile_ctx.set(normalize_memory_profile(profile))


def reset_memory_extractor_profile(token: object) -> None:
    try:
        _recall_profile_ctx.reset(token)
    except ValueError:
        # Token was created in a different Context (e.g. NDJSON stream resume).
        pass


def set_memory_recall_profile(profile: str | None):
    """Backward-compatible alias for :func:`set_memory_extractor_profile`."""
    return set_memory_extractor_profile(profile)


def reset_memory_recall_profile(token: object) -> None:
    reset_memory_extractor_profile(token)


def _memory_profile() -> str:
    ctx = _recall_profile_ctx.get()
    if ctx in {
        _PROFILE_FAST,
        _PROFILE_DEEP,
        _PROFILE_COMPACT,
        _PROFILE_V8_LIST_CAP,
        _PROFILE_V8_PRODUCTION,
    }:
        return ctx
    return normalize_memory_profile(None)


def _is_v10_adapter() -> bool:
    """True when the active LoRA is a V10 continuation-state adapter."""
    try:
        from memory_model_v1 import get_memory_model

        if get_memory_model() == "v10":
            return True
    except ImportError:
        pass
    return "v10" in _adapter_path().name.lower()


def _uses_json_repair_postprocess() -> bool:
    """V9 production and V10 both use parse + truncation repair + dedupe."""
    return _memory_profile() == _PROFILE_V8_PRODUCTION or _is_v10_adapter()


def _format_extraction_prompt(chunk_text: str) -> str:
    """Wrap chunk text for LoRA input; compact/v8 profiles add explicit field limits."""
    text = (chunk_text or "").strip()
    rule_prefix = _prompt_rule_prefix()
    if _memory_profile() in {_PROFILE_V8_LIST_CAP, _PROFILE_V8_PRODUCTION}:
        return f"{rule_prefix}{_V8_LIST_CAP_EXTRACTION_INSTRUCTION}{text}"
    if _memory_profile() == _PROFILE_COMPACT:
        return f"{rule_prefix}{_COMPACT_EXTRACTION_INSTRUCTION}{text}"
    if rule_prefix:
        return f"{rule_prefix}Transcript:\n{text}"
    return text


def _recall_profile() -> str:
    """Backward-compatible alias."""
    return _memory_profile()


def _max_chunks_for_transcript(char_count: int) -> int:
    explicit = str(os.getenv("MEMORY_EXTRACTOR_MAX_CHUNKS", "")).strip()
    if explicit:
        default = (
            _DEFAULT_MAX_CHUNKS_DEEP
            if _memory_profile() == _PROFILE_DEEP
            else _DEFAULT_MAX_CHUNKS_FAST
        )
        return max(1, _read_int_env("MEMORY_EXTRACTOR_MAX_CHUNKS", default))
    if _memory_profile() == _PROFILE_DEEP:
        return _DEFAULT_MAX_CHUNKS_DEEP
    return _DEFAULT_MAX_CHUNKS_FAST


def _chunk_chars() -> int:
    return max(500, _read_int_env("MEMORY_EXTRACTOR_CHUNK_CHARS", _DEFAULT_CHUNK_CHARS))


def _chunk_overlap_chars() -> int:
    return max(0, _read_int_env("MEMORY_EXTRACTOR_CHUNK_OVERLAP_CHARS", _DEFAULT_CHUNK_OVERLAP_CHARS))


def _max_new_tokens() -> int:
    explicit = str(os.getenv("MEMORY_EXTRACTOR_MAX_NEW_TOKENS", "")).strip()
    if explicit:
        try:
            return int(explicit)
        except ValueError:
            pass
    if _memory_profile() == _PROFILE_DEEP:
        return _DEFAULT_MAX_NEW_TOKENS_DEEP
    return _DEFAULT_MAX_NEW_TOKENS_FAST


def _short_circuit_chars() -> int:
    return max(500, _read_int_env("MEMORY_EXTRACTOR_SHORT_CIRCUIT_CHARS", _DEFAULT_SHORT_CIRCUIT_CHARS))


def _backend() -> str:
    raw = str(os.getenv("MEMORY_EXTRACTOR_BACKEND", "")).strip().lower()
    if raw in {"mock", "mlx", "transformers"}:
        return raw
    if raw:
        return raw
    import sys

    return "mlx" if sys.platform == "darwin" else "transformers"


def _adapter_path() -> Path:
    if _backend() == "mock":
        mock_dir = _ROOT / ".mock_adapter"
        mock_dir.mkdir(exist_ok=True)
        config = mock_dir / "adapter_config.json"
        if not config.is_file():
            config.write_text('{"model": "mock"}', encoding="utf-8")
        weights = mock_dir / "adapters.safetensors"
        if not weights.is_file():
            weights.write_bytes(b"")
        return mock_dir

    from adapter_loader import ensure_adapter

    try:
        from memory_model_v1 import default_adapter_for_model, get_memory_model

        return default_adapter_for_model(get_memory_model())
    except ImportError:
        return ensure_adapter("v10")


def extractor_model_id() -> str:
    return f"{_base_model()}+lora:{_adapter_path().name}"


def get_memory_extractor_info() -> dict[str, Any]:
    adapter = _adapter_path()
    config_path = adapter / "adapter_config.json"
    config: dict[str, Any] = {}
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            config = {}
    adapter_files = list(adapter.glob("*.safetensors")) if adapter.is_dir() else []
    total_bytes = sum(f.stat().st_size for f in adapter_files)
    return {
        "adapter_path": str(adapter),
        "adapter_exists": adapter.is_dir(),
        "model_id": extractor_model_id(),
        "base_model": _base_model(),
        "backend": _backend(),
        "profile": _memory_profile(),
        "memory_model": _memory_model_label(),
        "adapter_config": config,
        "adapter_file_count": len(adapter_files),
        "adapter_total_bytes": total_bytes,
    }


def _memory_model_label() -> str:
    try:
        from memory_model_v1 import get_memory_model

        return get_memory_model()
    except ImportError:
        return "v9"


_EXTRACTOR_INIT_LOGGED = False


def _log_extractor_init_once() -> None:
    global _EXTRACTOR_INIT_LOGGED
    if _EXTRACTOR_INIT_LOGGED:
        return
    _EXTRACTOR_INIT_LOGGED = True
    if str(os.getenv("CONTINUATOR_SUPPRESS_LOGS", "")).strip().lower() in {"1", "true", "yes"}:
        return
    info = get_memory_extractor_info()
    print(f"Memory Extractor Adapter: {info['adapter_path']}", flush=True)
    print(f"Model ID: {info['model_id']}", flush=True)


def _base_model() -> str:
    return (
        os.getenv("MEMORY_EXTRACTOR_BASE_MODEL", "").strip()
        or "Qwen/Qwen2.5-1.5B-Instruct"
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    m = _FENCE_RX.search(raw)
    if m:
        raw = m.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    raw = _TRAILING_COMMA_RX.sub(r"\1", raw)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _extract_complete_array_items(text: str, field: str) -> list[str]:
    m = re.search(rf'"{field}"\s*:\s*\[', text)
    if not m:
        return []
    i = m.end()
    n = len(text)
    items: list[str] = []
    while i < n:
        while i < n and text[i] in " \t\n\r,":
            i += 1
        if i >= n or text[i] == "]":
            break
        if text[i] != '"':
            break
        i += 1
        buf: list[str] = []
        while i < n:
            c = text[i]
            if c == "\\" and i + 1 < n:
                buf.append(text[i : i + 2])
                i += 2
                continue
            if c == '"':
                i += 1
                break
            buf.append(c)
            i += 1
        raw = "".join(buf)
        items.append(raw.replace('\\"', '"').replace("\\n", "\n"))
    return items


def _first_exact_repeat_index(items: list[str]) -> int | None:
    seen: set[str] = set()
    for i, item in enumerate(items):
        key = re.sub(r"\s+", " ", str(item or "").strip().lower())
        if not key:
            continue
        if key in seen:
            return i
        seen.add(key)
    return None


def _listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    s = str(value).strip()
    return [s] if s else []


def _normalize_record(data: dict[str, Any]) -> ConversationMemoryRecord:
    """Map canonical + known drift variants into ConversationMemoryRecord."""
    topic = str(data.get("topic") or "").strip()
    important_facts = _listify(data.get("important_facts"))
    current_goals = _listify(data.get("current_goals"))
    decisions = _listify(data.get("decisions"))
    open_questions = _listify(data.get("open_questions"))
    next_steps = _listify(data.get("next_steps"))
    summary = str(data.get("summary") or "").strip()

    if not important_facts and data.get("important_facts_discussed") is not None:
        important_facts = _listify(data.get("important_facts_discussed"))

    if not topic and data.get("active_issue"):
        topic = str(data.get("active_issue") or "").strip()
    if not current_goals and data.get("current_goal"):
        current_goals = _listify(data.get("current_goal"))
    if not open_questions and data.get("current_blocker"):
        open_questions = _listify(data.get("current_blocker"))
    if not important_facts and data.get("key_entities"):
        important_facts = _listify(data.get("key_entities"))
    if not decisions and data.get("attempted_solutions"):
        decisions = _listify(data.get("attempted_solutions"))

    return ConversationMemoryRecord(
        topic=topic,
        important_facts=important_facts,
        current_goals=current_goals,
        decisions=decisions,
        open_questions=open_questions,
        next_steps=next_steps,
        summary=summary,
        objective=_listify(data.get("objective")),
        current_state=str(data.get("current_state") or "").strip(),
        completed_work=_listify(data.get("completed_work")),
        active_problems=_listify(data.get("active_problems")),
        resolved_problems=_listify(data.get("resolved_problems")),
        constraints=_listify(data.get("constraints")),
        continuation_context=str(data.get("continuation_context") or "").strip(),
        raw=dict(data),
        parse_ok=True,
    )


def _record_has_signal(record: ConversationMemoryRecord) -> bool:
    return bool(record.topic.strip() or record.summary.strip())


def _apply_v8_production_postprocess(
    raw_text: str,
    *,
    chunk_index: int,
    chunk_total: int,
) -> ConversationMemoryRecord:
    """List-cap generation → truncation repair → dedupe (V8 production stack)."""
    from pipeline_profiler_v1 import profile_stage
    from v8_dedupe import dedupe_memory_fields
    from v8_truncation_repair import repair_truncated_json

    timing: dict[str, float] = {}
    repair_used = False
    with profile_stage("parse_json"):
        t0 = time.perf_counter()
        data = _parse_json_object(raw_text)
        timing["parse_ms"] = round((time.perf_counter() - t0) * 1000.0, 3)
    if not data:
        with profile_stage("truncation_repair"):
            t0 = time.perf_counter()
            repaired, _repair_audit = repair_truncated_json(raw_text)
            timing["repair_ms"] = round((time.perf_counter() - t0) * 1000.0, 3)
        if repaired:
            repair_used = True
            with profile_stage("parse_json"):
                data = _parse_json_object(repaired)
    else:
        timing["repair_ms"] = 0.0
    if not data:
        raise MemoryExtractorError(
            f"memory extractor returned unparseable JSON on chunk {chunk_index}"
        )

    record = _normalize_record(data)
    with profile_stage("dedupe"):
        t0 = time.perf_counter()
        deduped, dedupe_audit = dedupe_memory_fields(
            important_facts=record.important_facts,
            open_questions=record.open_questions,
            current_goals=record.current_goals,
            decisions=record.decisions,
            next_steps=record.next_steps,
        )
        timing["dedupe_ms"] = round((time.perf_counter() - t0) * 1000.0, 3)
    record.important_facts = deduped["important_facts"]
    record.open_questions = deduped["open_questions"]
    record.current_goals = deduped["current_goals"]
    record.decisions = deduped["decisions"]
    record.next_steps = deduped["next_steps"]

    if _is_v10_adapter():
        from v8_dedupe import dedupe_exact_preserve_order

        v10_audit: dict[str, Any] = {}
        for field in ("objective", "completed_work", "active_problems", "resolved_problems", "constraints"):
            before = _listify(getattr(record, field))
            after, removed = dedupe_exact_preserve_order(before)
            setattr(record, field, after)
            v10_audit[f"{field}_before"] = len(before)
            v10_audit[f"{field}_after"] = len(after)
            v10_audit[f"{field}_removed"] = removed
        dedupe_audit = {**dedupe_audit, **v10_audit}

    with profile_stage("validation"):
        t0 = time.perf_counter()
        if not _record_has_signal(record):
            raise MemoryExtractorError(
                f"memory extractor returned JSON without topic or summary on chunk {chunk_index}"
            )
        timing["validation_ms"] = round((time.perf_counter() - t0) * 1000.0, 3)

    record.raw = {
        **dict(record.raw),
        "_chunk_index": chunk_index,
        "_chunk_total": chunk_total,
        "_profile_timing": timing,
        "_v8_production": {
            "repair_used": repair_used,
            **dedupe_audit,
        },
    }
    record.model_id = f"{_base_model()}+lora:{_adapter_path().name}"
    return record


def _apply_overlap_to_chunks(base_chunks: list[str], overlap_chars: int) -> list[str]:
    if overlap_chars <= 0 or len(base_chunks) <= 1:
        return list(base_chunks)
    out: list[str] = [base_chunks[0]]
    for chunk in base_chunks[1:]:
        prev = out[-1]
        tail = prev[-overlap_chars:].lstrip() if len(prev) > overlap_chars else prev
        if tail and not chunk.startswith(tail):
            merged = f"{tail}\n\n{chunk}" if tail.strip() else chunk
            out.append(merged)
        else:
            out.append(chunk)
    return out


def _chunk_transcript_for_extraction(thread_text: str) -> tuple[list[str], dict[str, Any]]:
    from chunk_coverage import build_paragraph_chunks

    raw = (thread_text or "").strip()
    target = _chunk_chars()
    overlap = _chunk_overlap_chars()
    audit: dict[str, Any] = {
        "version": "memory_chunker_v1",
        "original_chars": len(raw),
        "chunk_chars": target,
        "overlap_chars": overlap,
        "strategy": "single_chunk",
        "all_chunks_count": 0,
    }
    if not raw:
        return [], audit

    if len(raw) <= _short_circuit_chars():
        audit["all_chunks_count"] = 1
        audit["strategy"] = "short_circuit"
        return [raw], audit

    base = build_paragraph_chunks(raw, target_chars=target)
    if not base:
        audit["all_chunks_count"] = 1
        audit["strategy"] = "short_circuit"
        return [raw], audit

    chunks = _apply_overlap_to_chunks(base, overlap)
    audit["all_chunks_count"] = len(chunks)
    audit["strategy"] = "paragraph_chunk_overlap"
    return chunks, audit


def _select_chunks_if_over_budget(
    chunks: list[str],
    *,
    max_chunks: int,
) -> tuple[list[str], dict[str, Any]]:
    if len(chunks) <= max_chunks:
        return list(chunks), {
            "selection_strategy": "full",
            "selected_chunks_count": len(chunks),
            "selected_indices": list(range(len(chunks))),
        }
    from chunk_coverage import adaptive_saliency_sampling

    selected, coverage = adaptive_saliency_sampling(chunks, max_chunks=max_chunks)
    return selected, {
        "selection_strategy": "adaptive_saliency_sampling",
        "selected_chunks_count": len(selected),
        **coverage,
    }


def _mock_extract_single_chunk(
    chunk_text: str,
    *,
    chunk_index: int,
    chunk_total: int,
) -> ConversationMemoryRecord:
    idx = chunk_index + 1
    return ConversationMemoryRecord(
        topic=f"mock conversation topic (chunk {idx}/{chunk_total})",
        important_facts=[f"mock fact from chunk {idx}"],
        current_goals=[f"mock goal chunk {idx}"],
        decisions=[f"mock decision chunk {idx}"],
        open_questions=[f"mock question chunk {idx}"],
        next_steps=[f"mock next step chunk {idx}"],
        summary=f"mock summary for chunk {idx} of {chunk_total}.",
        raw={"mock": True, "_chunk_index": chunk_index, "_chunk_total": chunk_total},
        parse_ok=True,
        model_id="mock",
        thread_chars_in=len(chunk_text),
    )


@dataclass
class _MlxBundle:
    model: Any
    tokenizer: Any


@lru_cache(maxsize=4)
def _load_mlx_impl(adapter_key: str) -> _MlxBundle:
    adapter = Path(adapter_key)
    if not adapter.is_dir():
        raise MemoryExtractorError(f"adapter path not found: {adapter}")
    try:
        from mlx_lm import load
    except ImportError as exc:
        raise MemoryExtractorError(
            "mlx_lm is required for MEMORY_EXTRACTOR_BACKEND=mlx"
        ) from exc
    model, tokenizer = load(_base_model(), adapter_path=str(adapter))
    _log_extractor_init_once()
    return _MlxBundle(model=model, tokenizer=tokenizer)


def _load_mlx() -> _MlxBundle:
    adapter_key = str(_adapter_path())
    info_before = _load_mlx_impl.cache_info()
    load_start_ts = time.time()
    t0 = time.perf_counter()
    bundle = _load_mlx_impl(adapter_key)
    load_latency_ms = (time.perf_counter() - t0) * 1000.0
    load_end_ts = time.time()
    info_after = _load_mlx_impl.cache_info()
    if info_after.hits > info_before.hits:
        cache_state = "warm_cache_hit"
    elif info_after.misses > info_before.misses:
        cache_state = "cold_cache_miss"
    else:
        cache_state = "unknown"
    if _mlx_measure_enabled():
        _record_mlx_load(
            cache_state=cache_state,
            load_start_ts=load_start_ts,
            load_end_ts=load_end_ts,
            load_latency_ms=load_latency_ms,
        )
    return bundle


def _generate_mlx(thread_text: str) -> str:
    bundle = _load_mlx()
    user_content = _format_extraction_prompt(thread_text)
    messages = [{"role": "user", "content": user_content}]
    if hasattr(bundle.tokenizer, "apply_chat_template"):
        prompt = bundle.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    else:
        prompt = user_content

    enable_repstop = _repetition_stop_enabled()
    if _mlx_measure_enabled() or enable_repstop:
        generation_start_ts = time.time()
        t0 = time.perf_counter()
        from mlx_lm import stream_generate

        text = ""
        last = None
        stop_reason = "max_tokens_or_eos"
        stop_fact_repeat_index: int | None = None
        stop_fact_count = 0
        min_facts = _repstop_min_facts()
        min_tokens = _repstop_min_tokens()
        for response in stream_generate(
            bundle.model,
            bundle.tokenizer,
            prompt=prompt,
            max_tokens=_max_new_tokens(),
        ):
            text += response.text
            last = response
            if enable_repstop:
                generated_tokens = int(getattr(response, "generation_tokens", 0) or 0)
                facts = _extract_complete_array_items(text, "important_facts")
                rep_idx = _first_exact_repeat_index(facts)
                if (
                    rep_idx is not None
                    and len(facts) >= min_facts
                    and generated_tokens >= min_tokens
                ):
                    stop_reason = "exact_fact_repetition"
                    stop_fact_repeat_index = rep_idx
                    stop_fact_count = len(facts)
                    break
        generation_latency_ms = (time.perf_counter() - t0) * 1000.0
        generation_end_ts = time.time()
        audit: dict[str, Any] = {
            "generation_start_ts": generation_start_ts,
            "generation_end_ts": generation_end_ts,
            "generation_latency_ms": round(generation_latency_ms, 2),
            "repetition_stop_enabled": bool(enable_repstop),
            "stop_reason": stop_reason,
        }
        if last is not None:
            prompt_tps = float(last.prompt_tps or 0.0)
            generation_tps = float(last.generation_tps or 0.0)
            prompt_tokens = int(last.prompt_tokens or 0)
            generation_tokens = int(last.generation_tokens or 0)
            prefill_ms = round(1000.0 * prompt_tokens / max(prompt_tps, 1e-9), 2)
            decode_ms = round(1000.0 * generation_tokens / max(generation_tps, 1e-9), 2)
            audit.update(
                {
                    "prompt_tokens": prompt_tokens,
                    "generation_tokens": generation_tokens,
                    "input_tokens": prompt_tokens,
                    "output_tokens": generation_tokens,
                    "prompt_tps": round(prompt_tps, 3),
                    "generation_tps": round(generation_tps, 3),
                    "prefill_ms": prefill_ms,
                    "decode_ms": decode_ms,
                }
            )
        if enable_repstop:
            facts_final = _extract_complete_array_items(text, "important_facts")
            audit.update(
                {
                    "repetition_stop_triggered": stop_reason == "exact_fact_repetition",
                    "repstop_min_facts": min_facts,
                    "repstop_min_tokens": min_tokens,
                    "repstop_fact_repeat_index": stop_fact_repeat_index,
                    "repstop_fact_count_at_stop": stop_fact_count or len(facts_final),
                    "repstop_unique_facts_at_stop": len(
                        {
                            re.sub(r"\s+", " ", str(x or "").strip().lower())
                            for x in facts_final
                            if str(x).strip()
                        }
                    ),
                }
            )
        _mlx_last_generation_audit.set(dict(audit))
        return text

    from mlx_lm import generate

    return generate(
        bundle.model,
        bundle.tokenizer,
        prompt=prompt,
        max_tokens=_max_new_tokens(),
        verbose=False,
    )


@lru_cache(maxsize=4)
def _load_transformers(adapter_key: str):
    adapter = Path(adapter_key)
    if not adapter.is_dir():
        raise MemoryExtractorError(f"adapter path not found: {adapter}")
    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise MemoryExtractorError(
            "transformers and peft are required for MEMORY_EXTRACTOR_BACKEND=transformers"
        ) from exc

    base = _base_model()
    tokenizer = AutoTokenizer.from_pretrained(base, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        base,
        trust_remote_code=True,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    )
    model = PeftModel.from_pretrained(model, str(adapter))
    model.eval()
    _log_extractor_init_once()
    return model, tokenizer


def _generate_transformers(thread_text: str) -> str:
    model, tokenizer = _load_transformers(str(_adapter_path()))
    import torch

    user_content = _format_extraction_prompt(thread_text)
    messages = [{"role": "user", "content": user_content}]
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(prompt, return_tensors="pt")
    if hasattr(model, "device"):
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=_max_new_tokens(),
            do_sample=False,
        )
    gen = out[0][inputs["input_ids"].shape[-1] :]
    return tokenizer.decode(gen, skip_special_tokens=True)


def _generate_raw(thread_text: str) -> str:
    backend = _backend()
    if backend == "mock":
        return json.dumps(
            {
                "topic": "mock conversation topic",
                "important_facts": ["mock fact"],
                "current_goals": ["mock current goal"],
                "decisions": ["mock decision"],
                "open_questions": ["mock open question"],
                "next_steps": ["mock next step"],
                "summary": "mock summary",
            }
        )
    if backend == "mlx":
        return _generate_mlx(thread_text)
    if backend == "transformers":
        return _generate_transformers(thread_text)
    raise MemoryExtractorError(f"unsupported MEMORY_EXTRACTOR_BACKEND: {backend}")


def _extract_single_chunk(
    chunk_text: str,
    *,
    chunk_index: int,
    chunk_total: int,
) -> ConversationMemoryRecord:
    """Run one LoRA extraction on a single chunk (no condenser)."""
    started = time.time()
    text = (chunk_text or "").strip()
    if not text:
        raise MemoryExtractorError(f"empty chunk at index {chunk_index}")

    if _backend() == "mock":
        record = _mock_extract_single_chunk(
            text, chunk_index=chunk_index, chunk_total=chunk_total
        )
    else:
        try:
            from pipeline_profiler_v1 import profile_stage

            profile_timing: dict[str, Any] = {}
            with profile_stage("lora_generation"):
                t_gen = time.perf_counter()
                raw_text = _generate_raw(text)
                profile_timing["lora_generation_ms"] = round(
                    (time.perf_counter() - t_gen) * 1000.0, 3
                )
        except MemoryExtractorError:
            raise
        except Exception as exc:
            raise MemoryExtractorError(
                f"memory extraction generation failed on chunk {chunk_index}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        gen_audit = _mlx_last_generation_audit.get()
        _mlx_last_generation_audit.set(None)
        if isinstance(gen_audit, dict):
            profile_timing["prompt_tokens"] = int(gen_audit.get("prompt_tokens") or 0)
            profile_timing["output_tokens"] = int(gen_audit.get("output_tokens") or 0)
            load_ms = 0.0
            mlx_audit = _mlx_run_audit()
            if isinstance(mlx_audit, dict):
                loads = mlx_audit.get("loads") or []
                if loads:
                    load_ms = float(loads[-1].get("load_latency_ms") or 0.0)
            if load_ms > 0:
                from pipeline_profiler_v1 import get_pipeline_profile, pipeline_profile_enabled

                if pipeline_profile_enabled():
                    get_pipeline_profile().add_stage("model_load", load_ms)
        if _mlx_measure_enabled():
            chunk_metrics: dict[str, Any] = {
                "chunk_index": chunk_index,
                "chunk_chars": len(text),
            }
            if isinstance(gen_audit, dict):
                chunk_metrics.update(gen_audit)
            _mlx_run_audit().setdefault("chunks", []).append(dict(chunk_metrics))

        try:
            if _uses_json_repair_postprocess():
                record = _apply_v8_production_postprocess(
                    raw_text, chunk_index=chunk_index, chunk_total=chunk_total
                )
                post_timing = dict((record.raw or {}).get("_profile_timing") or {})
                profile_timing.update(post_timing)
            else:
                data = _parse_json_object(raw_text)
                if not data:
                    raise MemoryExtractorError(
                        f"memory extractor returned unparseable JSON on chunk {chunk_index}"
                    )
                record = _normalize_record(data)
                if not _record_has_signal(record):
                    raise MemoryExtractorError(
                        f"memory extractor returned JSON without topic or summary on chunk {chunk_index}"
                    )
                record.model_id = f"{_base_model()}+lora:{_adapter_path().name}"
                record.raw = {
                    **dict(record.raw),
                    "_chunk_index": chunk_index,
                    "_chunk_total": chunk_total,
                }
            if profile_timing:
                record.raw = {**dict(record.raw), "_profile_timing": profile_timing}
        except MemoryExtractorError:
            if _mlx_measure_enabled():
                chunks_audit = _mlx_run_audit().get("chunks")
                if isinstance(chunks_audit, list) and chunks_audit:
                    chunks_audit[-1]["parse_ok"] = False
                    chunks_audit[-1]["latency_ms"] = round((time.time() - started) * 1000, 2)
            raise

    record.latency_ms = round((time.time() - started) * 1000, 2)
    if not record.model_id:
        record.model_id = f"{_base_model()}+lora:{_adapter_path().name}"
    if _mlx_measure_enabled():
        chunks_audit = _mlx_run_audit().get("chunks")
        if isinstance(chunks_audit, list) and chunks_audit:
            chunks_audit[-1]["latency_ms"] = record.latency_ms
            chunks_audit[-1]["parse_ok"] = True
    record.thread_chars_in = len(text)
    return record


def _profiler_stage(profiler: Any | None, name: str):
    if profiler is not None:
        return profiler.stage(name)
    return nullcontext()


def _extract_conversation_memory_chunked(
    thread_text: str,
    *,
    profiler: Any | None = None,
) -> ConversationMemoryRecord:
    """Chunk transcript → N LoRA calls → merge into one record."""
    from memory_record_merger_v1 import merge_conversation_memory_records

    raw = (thread_text or "").strip()
    started = time.time()
    mlx_audit_token = _mlx_run_audit_begin() if _mlx_measure_enabled() else None

    try:
        with _profiler_stage(profiler, "memory.extract.chunk"):
            t_chunk = time.perf_counter()
            chunks, chunk_audit = _chunk_transcript_for_extraction(raw)
            if _mlx_measure_enabled():
                _mlx_run_audit()["stage_ms"]["chunking_ms"] = round(
                    (time.perf_counter() - t_chunk) * 1000, 2
                )

        if not chunks:
            raise MemoryExtractorError("no chunks produced from transcript")

        max_c = _max_chunks_for_transcript(len(raw))
        selection_audit: dict[str, Any] = {}
        if len(chunks) > max_c:
            with _profiler_stage(profiler, "memory.extract.select"):
                t_sel = time.perf_counter()
                chunks, selection_audit = _select_chunks_if_over_budget(chunks, max_chunks=max_c)
                if _mlx_measure_enabled():
                    _mlx_run_audit()["stage_ms"]["selection_ms"] = round(
                        (time.perf_counter() - t_sel) * 1000, 2
                    )

        chunk_audit = {
            **chunk_audit,
            **selection_audit,
            "lora_budget": max_c,
            "memory_profile": _memory_profile(),
            "recall_profile": _memory_profile(),
            "max_new_tokens": _max_new_tokens(),
            "chunks_created": int(chunk_audit.get("all_chunks_count") or len(chunks)),
        }

        records: list[ConversationMemoryRecord] = []
        failed_indices: list[int] = []
        total = len(chunks)

        with _profiler_stage(profiler, "memory.extract.lora"):
            t_lora = time.perf_counter()
            for i, chunk in enumerate(chunks):
                try:
                    records.append(
                        _extract_single_chunk(chunk, chunk_index=i, chunk_total=total)
                    )
                except MemoryExtractorError as exc:
                    failed_indices.append(i)
                    if total == 1:
                        raise
                    chunk_audit.setdefault("chunk_errors", []).append(
                        {"chunk_index": i, "error": str(exc)}
                    )
            if _mlx_measure_enabled():
                _mlx_run_audit()["stage_ms"]["lora_loop_ms"] = round(
                    (time.perf_counter() - t_lora) * 1000, 2
                )

        chunk_audit["chunks_selected"] = total
        chunk_audit["successful_lora_calls"] = len(records)

        if not records:
            errors = chunk_audit.get("chunk_errors") or []
            detail = "; ".join(
                f"chunk {e.get('chunk_index')}: {e.get('error')}" for e in errors[:4]
            )
            hint = (
                " (likely truncated JSON — raise MEMORY_EXTRACTOR_MAX_NEW_TOKENS to 1024 "
                "or use profile=deep)"
                if any("unparseable JSON" in str(e.get("error", "")) for e in errors)
                else ""
            )
            msg = "all chunk extractions failed"
            if detail:
                msg = f"{msg}: {detail}{hint}"
            raise MemoryExtractorError(msg)

        if _mlx_measure_enabled():
            mlx_audit = _mlx_run_audit()
            chunk_audit["mlx_measurement"] = {
                "loads": list(mlx_audit.get("loads") or []),
                "per_chunk": list(mlx_audit.get("chunks") or []),
                "stage_ms": dict(mlx_audit.get("stage_ms") or {}),
            }

        with _profiler_stage(profiler, "memory.extract.merge"):
            t_merge = time.perf_counter()
            merged = merge_conversation_memory_records(
                records,
                original_chars=len(raw),
                chunk_audit=chunk_audit,
                failed_chunk_indices=failed_indices,
            )
            if _mlx_measure_enabled():
                _mlx_run_audit()["stage_ms"]["merge_total_ms"] = round(
                    (time.perf_counter() - t_merge) * 1000, 2
                )
                timing = chunk_audit.get("stage_timing_ms")
                if isinstance(timing, dict):
                    merged.condense_audit.setdefault("stage_timing_ms", {}).update(timing)

        wall_ms = round((time.time() - started) * 1000, 2)
        if wall_ms > merged.latency_ms:
            merged.latency_ms = wall_ms
        if _mlx_measure_enabled():
            merged.condense_audit["extract_wall_ms"] = wall_ms
            merged.condense_audit["mlx_measurement"] = chunk_audit.get("mlx_measurement")
        return merged
    finally:
        if mlx_audit_token is not None:
            _mlx_run_audit_reset(mlx_audit_token)


def memory_extraction_runtime_audit(record: ConversationMemoryRecord) -> dict[str, Any]:
    """Flatten chunk/extraction counters for API runtime audit."""
    condense = record.condense_audit if isinstance(record.condense_audit, dict) else {}
    chunk = condense.get("chunk_audit") if isinstance(condense.get("chunk_audit"), dict) else {}
    return {
        "memory_profile": chunk.get("memory_profile") or condense.get("memory_profile") or _memory_profile(),
        "chunks_created": int(chunk.get("chunks_created") or chunk.get("all_chunks_count") or 0),
        "chunks_selected": int(
            chunk.get("chunks_selected") or chunk.get("selected_chunks_count") or 0
        ),
        "successful_lora_calls": int(
            chunk.get("successful_lora_calls") or condense.get("lora_call_count") or 0
        ),
    }


def extract_conversation_memory(
    thread_text: str,
    *,
    profiler: Any | None = None,
) -> ConversationMemoryRecord:
    """Extract operational memory from a conversation transcript (recall-first chunked LoRA)."""
    if not memory_extractor_enabled():
        raise MemoryExtractorError("MEMORY_EXTRACTOR_ENABLED=0")
    return _extract_conversation_memory_chunked(thread_text, profiler=profiler)
