"""Conservative truncated JSON repair for V8 cluster memory outputs."""
from __future__ import annotations

import json
import re
from typing import Any

V8_LIST_FIELDS = (
    "important_facts",
    "current_goals",
    "decisions",
    "open_questions",
    "next_steps",
)

V10_LIST_FIELDS = (
    "objective",
    "completed_work",
    "active_problems",
    "resolved_problems",
    "constraints",
)

V10_SCALAR_FIELDS = (
    "current_state",
    "continuation_context",
)

_SCALAR_FIELDS = ("topic", "summary")

# Field order in typical model output (V9 + V10 merged schema).
ALL_LIST_FIELDS = V8_LIST_FIELDS + V10_LIST_FIELDS
ALL_SCALAR_FIELDS = _SCALAR_FIELDS + V10_SCALAR_FIELDS


def _unescape(s: str) -> str:
    return s.replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t")


def _complete_string_at(text: str, start: int) -> tuple[str | None, int]:
    """Parse a complete JSON string starting at opening quote index. Returns (value, end_index)."""
    if start >= len(text) or text[start] != '"':
        return None, start
    i = start + 1
    buf: list[str] = []
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            buf.append(text[i : i + 2])
            i += 2
            continue
        if c == '"':
            return _unescape("".join(buf)), i + 1
        buf.append(c)
        i += 1
    return None, i


def _extract_scalar(text: str, field: str) -> str | None:
    m = re.search(rf'"{field}"\s*:\s*"', text)
    if not m:
        return None
    value, end = _complete_string_at(text, m.end() - 1)
    return value


def _extract_complete_array_items(text: str, field: str) -> list[str]:
    """Return only fully closed string items from a JSON array field."""
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
        value, i = _complete_string_at(text, i)
        if value is None:
            break
        items.append(value)
    return items


def analyze_truncation(raw: str) -> dict[str, Any]:
    """Determine last complete field/item and whether safe repair is possible."""
    text = (raw or "").strip()
    topic = _extract_scalar(text, "topic")
    summary = _extract_scalar(text, "summary")
    arrays = {f: _extract_complete_array_items(text, f) for f in ALL_LIST_FIELDS}
    scalars = {f: _extract_scalar(text, f) for f in V10_SCALAR_FIELDS}

    last_complete_field = None
    last_complete_item = None
    if topic is not None:
        last_complete_field = "topic"
    if summary is not None:
        last_complete_field = "summary"
    for field in ALL_LIST_FIELDS:
        if arrays[field]:
            last_complete_field = field
            last_complete_item = arrays[field][-1][:120]
        elif re.search(rf'"{field}"\s*:\s*\[', text):
            last_complete_field = field
            break
    for field in V10_SCALAR_FIELDS:
        if scalars[field] is not None:
            last_complete_field = field

    active_array = None
    if not text.rstrip().endswith("}"):
        for field in reversed(ALL_LIST_FIELDS):
            m = re.search(rf'"{field}"\s*:\s*\[', text)
            if m:
                active_array = field
                break

    can_repair = bool(topic and summary)
    return {
        "has_topic": topic is not None,
        "has_summary": summary is not None,
        "last_complete_field": last_complete_field,
        "last_complete_item_preview": last_complete_item,
        "active_array_at_truncation": active_array,
        "can_repair": can_repair,
        "complete_item_counts": {f: len(arrays[f]) for f in ALL_LIST_FIELDS},
        "scalar_fields_present": {f: scalars[f] is not None for f in V10_SCALAR_FIELDS},
        "topic_preview": (topic or "")[:80],
        "summary_preview": (summary or "")[:80],
    }


def repair_truncated_json(raw: str) -> tuple[str | None, dict[str, Any]]:
    """
    Conservative repair: keep only complete scalars/array items, rebuild valid JSON.
    Does not invent fields or items.
    """
    audit = analyze_truncation(raw)
    if not audit["can_repair"]:
        return None, audit

    topic = _extract_scalar(raw, "topic")
    summary = _extract_scalar(raw, "summary")
    assert topic is not None and summary is not None

    obj: dict[str, Any] = {
        "topic": topic,
        "summary": summary,
    }
    for field in ALL_LIST_FIELDS:
        obj[field] = _extract_complete_array_items(raw, field)
    for field in V10_SCALAR_FIELDS:
        value = _extract_scalar(raw, field)
        if value is not None:
            obj[field] = value

    repaired = json.dumps(obj, ensure_ascii=False)
    audit["repaired_chars"] = len(repaired)
    audit["removed_incomplete_trailing"] = True
    return repaired, audit
