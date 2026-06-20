"""Merge per-chunk ConversationMemoryRecords into one record for the adapter."""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

from memory_extractor_v1 import ConversationMemoryRecord

_VERSION = "memory_record_merger_v1"
_SUMMARY_SYNTHESIS_VERSION = "chapter_v1"
_SUMMARY_MAX_WORDS = 600
_SUMMARY_MAX_CHARS = 4200
_PART_LABEL_RE = re.compile(r"\[Part\s+\d+/\d+\]", re.I)
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_logger = logging.getLogger(__name__)


def _norm_key(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _dedupe_preserve_order(items: list[str], *, limit: int | None = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        val = str(raw or "").strip()
        if not val:
            continue
        key = _norm_key(val)
        if key in seen:
            continue
        seen.add(key)
        out.append(val)
        if limit is not None and len(out) >= limit:
            break
    return out


def _record_snapshot(record: ConversationMemoryRecord) -> dict[str, Any]:
    return {
        "topic": record.topic,
        "important_facts": list(record.important_facts),
        "current_goals": list(record.current_goals),
        "decisions": list(record.decisions),
        "open_questions": list(record.open_questions),
        "next_steps": list(record.next_steps),
        "summary": record.summary,
        "chunk_index": (record.raw or {}).get("_chunk_index"),
    }


def _merge_topic(records: list[ConversationMemoryRecord]) -> str:
    for record in reversed(records):
        topic = str(record.topic or "").strip()
        if topic:
            return topic
    return ""


def _merge_list_chronological(
    records: list[ConversationMemoryRecord],
    field: str,
    *,
    limit: int,
) -> list[str]:
    items: list[str] = []
    for record in records:
        val = getattr(record, field, None)
        if isinstance(val, list):
            items.extend(str(x).strip() for x in val if str(x).strip())
    return _dedupe_preserve_order(items, limit=limit)


def _merge_current_goals(records: list[ConversationMemoryRecord]) -> list[str]:
    if not records:
        return []
    tail = [str(g).strip() for g in (records[-1].current_goals or []) if str(g).strip()]
    tail_keys = {_norm_key(g) for g in tail}
    earlier: list[str] = []
    for record in records[:-1]:
        for goal in record.current_goals or []:
            g = str(goal or "").strip()
            if not g or _norm_key(g) in tail_keys:
                continue
            earlier.append(g)
    return _dedupe_preserve_order(tail + earlier, limit=12)


def _merge_next_steps(records: list[ConversationMemoryRecord]) -> list[str]:
    if not records:
        return []
    tail_steps = [str(x).strip() for x in (records[-1].next_steps or []) if str(x).strip()]
    tail_keys = {_norm_key(x) for x in tail_steps}
    earlier: list[str] = []
    for record in records[:-1]:
        for step in record.next_steps or []:
            s = str(step or "").strip()
            if not s or _norm_key(s) in tail_keys:
                continue
            earlier.append(s)
    return _dedupe_preserve_order(tail_steps + earlier, limit=12)


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def _strip_part_labels(text: str) -> str:
    cleaned = _PART_LABEL_RE.sub("", str(text or ""))
    return _collapse_ws(cleaned)


def _clip_phrase(text: str, max_chars: int) -> str:
    phrase = _collapse_ws(text)
    if not phrase or max_chars <= 0:
        return ""
    if len(phrase) <= max_chars:
        return phrase
    if max_chars <= 1:
        return "…"
    cut = phrase[: max_chars - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    cut = cut.rstrip(".,;:- ")
    return (cut + "…") if cut else "…"


def _word_count(text: str) -> int:
    return len(_TOKEN_RE.findall(_norm_key(text)))


def _clip_words(text: str, max_words: int) -> str:
    if max_words <= 0:
        return ""
    words = re.findall(r"\S+", str(text or "").strip())
    if len(words) <= max_words:
        return " ".join(words)
    clipped = " ".join(words[:max_words]).rstrip(".,;:- ")
    return clipped + "…"


def _first_sentence(text: str, *, max_chars: int = 280) -> str:
    cleaned = _strip_part_labels(text)
    if not cleaned:
        return ""
    match = re.search(r"[.!?](?:\s+|$)", cleaned)
    if match and match.end() <= max_chars:
        return cleaned[: match.end()].strip()
    return _clip_phrase(cleaned, max_chars)


def _content_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(_norm_key(text)) if len(t) > 2}


def _is_near_duplicate(a: str, b: str, *, threshold: float = 0.55) -> bool:
    ta, tb = _content_tokens(a), _content_tokens(b)
    if not ta or not tb:
        return _norm_key(a) == _norm_key(b)
    overlap = len(ta & tb)
    union = len(ta | tb)
    return overlap / union >= threshold if union else False


def _diverse_items(items: list[str], *, limit: int) -> list[str]:
    out: list[str] = []
    for raw in items:
        val = _collapse_ws(raw)
        if not val:
            continue
        if any(_is_near_duplicate(val, kept) for kept in out):
            continue
        out.append(val)
        if len(out) >= limit:
            break
    return out


def _soften_clause(text: str) -> str:
    phrase = _collapse_ws(text).rstrip(".!?")
    if not phrase:
        return ""
    phrase = re.sub(r"^(the|a|an)\s+", "", phrase, flags=re.I)
    phrase = re.sub(
        r"^(segment|part|discussion|chunk)\s+\d+\s+(explored|focused on|addressed|covered)\s+",
        "",
        phrase,
        flags=re.I,
    )
    phrase = re.sub(
        r"^the conversation (focused on|explored|addressed|centered on)\s+",
        "",
        phrase,
        flags=re.I,
    )
    if phrase and phrase[0].isupper() and not phrase[:2].isupper():
        phrase = phrase[0].lower() + phrase[1:]
    return phrase


def _summary_gist(text: str, *, max_chars: int = 220) -> str:
    sentence = _first_sentence(text, max_chars=max_chars)
    gist = _soften_clause(sentence)
    return gist or _soften_clause(_clip_phrase(text, max_chars))


def _join_prose_clauses(items: list[str], *, limit: int, lead: str) -> str:
    picked = _diverse_items(items, limit=limit)
    if not picked:
        return ""
    if len(picked) == 1:
        return f"{lead} {_soften_clause(picked[0])}."
    bridges = ["Building on that", "The thread also established", "Another line of thought emphasized", "Later discussion reinforced"]
    parts = [f"{lead} {_soften_clause(picked[0])}."]
    for i, item in enumerate(picked[1:], start=1):
        bridge = bridges[min(i - 1, len(bridges) - 1)]
        parts.append(f"{bridge}, {_soften_clause(item)}.")
    return " ".join(parts)


def _section_about(
    *,
    topic: str,
    opening_summary: str,
    important_facts: list[str],
    current_goals: list[str],
) -> str:
    topic_text = _collapse_ws(topic)
    opening = _summary_gist(opening_summary)
    themes = _diverse_items(important_facts, limit=2)
    goal = _soften_clause(_collapse_ws(current_goals[0])) if current_goals else ""

    if topic_text:
        lead = (
            f"This discussion revisited {topic_text}. "
            "If you have not looked at this thread in months, the through-line was how the pieces fit together, not a loose collection of notes."
        )
    elif goal:
        lead = f"This discussion centered on {goal}."
    elif opening:
        lead = f"This discussion opened around {_summary_gist(opening)}."
    else:
        lead = "This discussion explored a technical problem from first principles."

    if opening and topic_text and _norm_key(opening) != _norm_key(topic_text):
        lead += f" Early framing highlighted {_summary_gist(opening)}."
    if themes:
        lead += (
            f" The conversation kept returning to the idea that {_soften_clause(themes[0])}"
            + (f" and {_soften_clause(themes[1])}" if len(themes) > 1 else "")
            + ", which tied the later work together."
        )
    elif goal and topic_text and _norm_key(goal) != _norm_key(topic_text):
        lead += f" The practical anchor throughout was {goal}."
    return lead


def _section_evolution(
    *,
    topic: str,
    opening_summary: str,
    tail_summary: str,
    chunk_count: int,
    current_goals: list[str],
) -> str:
    opening = _summary_gist(opening_summary)
    tail = _summary_gist(tail_summary)
    goal = _soften_clause(_collapse_ws(current_goals[0])) if current_goals else ""

    if chunk_count <= 1:
        if opening:
            return f"The exchange stayed focused on {_soften_clause(opening)}"
        if goal:
            return f"Work stayed oriented toward {goal}."
        return "The exchange moved in a single continuous arc without major topic shifts."

    parts: list[str] = []
    if opening:
        parts.append(f"The conversation began by examining {_soften_clause(opening)}")
    else:
        parts.append("The conversation began with foundational definitions and constraints")

    if chunk_count > 1:
        parts.append(f" and unfolded across {chunk_count} segments rather than one sitting")

    if tail and _norm_key(tail) != _norm_key(opening):
        parts.append(f", gradually tightening toward {_soften_clause(tail)}")
    elif goal:
        parts.append(f", gradually tightening toward {goal}")
    elif topic:
        parts.append(f", gradually tightening around {_soften_clause(topic)}")

    parts.append(
        ". Along the way, earlier exploratory ideas were tested against later constraints, "
        "so the thread reads as refinement rather than repetition."
    )
    return "".join(parts)


def _section_insights(*, important_facts: list[str]) -> str:
    body = _join_prose_clauses(
        important_facts,
        limit=4,
        lead="Several insights emerged, including",
    )
    if not body:
        return "No single breakthrough dominated; understanding accumulated through linked observations."
    return body + " Taken together, these insights explain why later choices felt necessary rather than arbitrary."


def _section_decisions(*, decisions: list[str]) -> str:
    picked = _diverse_items(decisions, limit=4)
    if not picked:
        return "No firm decisions were recorded, though the direction of travel became clearer as constraints surfaced."
    if len(picked) == 1:
        return f"The group committed to {_soften_clause(picked[0])}."
    lead = f"The group committed to {_soften_clause(picked[0])}."
    bridges = ["They also chose", "Another decision was", "The thread further settled on"]
    parts = [lead]
    for i, item in enumerate(picked[1:], start=1):
        bridge = bridges[min(i - 1, len(bridges) - 1)]
        parts.append(f"{bridge} {_soften_clause(item)}")
    return ". ".join(parts) + ". These choices narrowed the design space for what followed."


def _section_open_questions(*, open_questions: list[str]) -> str:
    recent = _diverse_items(open_questions[-8:], limit=4)
    if not recent:
        return "No major open questions were left on the table at the end of the thread."
    if len(recent) == 1:
        return f"One question still needs resolution: {_soften_clause(recent[0])}."
    joined = "; ".join(_soften_clause(q).rstrip(".") for q in recent[:-1])
    return (
        f"Important questions remain, including {joined}; "
        f"and {_soften_clause(recent[-1])}. "
        "Answering these will determine how complete the eventual solution can be."
    )


def _section_current_direction(
    *,
    current_goals: list[str],
    next_steps: list[str],
    tail_summary: str,
) -> str:
    goal = _soften_clause(_collapse_ws(current_goals[0])) if current_goals else ""
    steps = _diverse_items(next_steps, limit=2)
    tail = _summary_gist(tail_summary)

    parts: list[str] = []
    if goal:
        parts.append(f"Current work is focused on {goal}.")
    elif tail:
        parts.append(f"Current work is focused on {_soften_clause(tail)}.")

    if steps:
        if len(steps) == 1:
            parts.append(f"The immediate next move is to {_soften_clause(steps[0])}.")
        else:
            parts.append(
                f"The immediate next moves are to {_soften_clause(steps[0])} "
                f"and then {_soften_clause(steps[1])}."
            )
    elif tail and not goal:
        parts.append(f"The thread ended pointed toward {_soften_clause(tail)}.")

    if not parts:
        return "The thread ended with exploratory momentum but no single named next action."
    return " ".join(parts) + " That is the handoff point if you are picking this work back up."


_CHAPTER_SECTIONS: tuple[tuple[str, str], ...] = (
    ("What the discussion was about", "about"),
    ("How the discussion evolved over time", "evolution"),
    ("Key insights discovered", "insights"),
    ("Decisions that were made", "decisions"),
    ("Remaining open questions", "open_questions"),
    ("Current direction of work", "current_direction"),
)


def _render_chapter_section(title: str, body: str) -> str:
    body = _collapse_ws(body)
    if not body:
        return ""
    return f"## {title}\n\n{body}"


def _fit_chapter_recap(section_blocks: list[str], *, max_words: int, max_chars: int) -> str:
    blocks = [b for b in section_blocks if b.strip()]
    if not blocks:
        return ""

    def _joined(parts: list[str]) -> str:
        return "\n\n".join(parts)

    joined = _joined(blocks)
    if _word_count(joined) <= max_words and len(joined) <= max_chars:
        return joined

    # Preserve the final sections (open questions + current direction), trim earlier bodies.
    protected_tail = 2
    for trim_round in range(12):
        new_blocks: list[str] = []
        for idx, block in enumerate(blocks):
            header, _, body = block.partition("\n\n")
            if idx < len(blocks) - protected_tail and body:
                words = _word_count(body)
                if words > 28:
                    body = _clip_words(body, max(20, words - 8))
            new_blocks.append(f"{header}\n\n{body}" if body else header)
        blocks = new_blocks
        joined = _joined(blocks)
        if _word_count(joined) <= max_words and len(joined) <= max_chars:
            return joined

    return _clip_phrase(joined, max_chars)


def _synthesize_summary(
    *,
    topic: str,
    opening_summary: str,
    tail_summary: str,
    important_facts: list[str],
    decisions: list[str],
    current_goals: list[str],
    open_questions: list[str],
    next_steps: list[str],
    chunk_count: int,
) -> str:
    """Build a chapter-style recap from merged fields (deterministic, no LLM)."""
    opening = _strip_part_labels(opening_summary)
    tail = _strip_part_labels(tail_summary)

    if chunk_count <= 1:
        single = tail or opening
        if single:
            return _clip_phrase(single, _SUMMARY_MAX_CHARS)

    section_bodies = [
        _section_about(
            topic=topic,
            opening_summary=opening,
            important_facts=important_facts,
            current_goals=current_goals,
        ),
        _section_evolution(
            topic=topic,
            opening_summary=opening,
            tail_summary=tail,
            chunk_count=chunk_count,
            current_goals=current_goals,
        ),
        _section_insights(important_facts=important_facts),
        _section_decisions(decisions=decisions),
        _section_open_questions(open_questions=open_questions),
        _section_current_direction(
            current_goals=current_goals,
            next_steps=next_steps,
            tail_summary=tail,
        ),
    ]

    blocks: list[str] = []
    for (title, _), body in zip(_CHAPTER_SECTIONS, section_bodies, strict=True):
        rendered = _render_chapter_section(title, body)
        if rendered:
            blocks.append(rendered)

    summary = _fit_chapter_recap(
        blocks,
        max_words=_SUMMARY_MAX_WORDS,
        max_chars=_SUMMARY_MAX_CHARS,
    )
    if _PART_LABEL_RE.search(summary):
        summary = _strip_part_labels(summary)
    return summary


def merge_conversation_memory_records(
    records: list[ConversationMemoryRecord],
    *,
    original_chars: int,
    chunk_audit: dict[str, Any] | None = None,
    failed_chunk_indices: list[int] | None = None,
) -> ConversationMemoryRecord:
    """Merge N chunk-level records into one adapter-ready record."""
    if not records:
        raise ValueError("merge_conversation_memory_records requires at least one record")

    measure = str(os.getenv("MEMORY_EXTRACTOR_MLX_MEASURE", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    t_merge_lists = time.perf_counter() if measure else 0.0

    topic = _merge_topic(records)
    important_facts = _merge_list_chronological(records, "important_facts", limit=24)
    current_goals = _merge_current_goals(records)
    decisions = _merge_list_chronological(records, "decisions", limit=20)
    open_questions = _merge_list_chronological(records, "open_questions", limit=16)
    next_steps = _merge_next_steps(records)

    merge_lists_ms = round((time.perf_counter() - t_merge_lists) * 1000, 2) if measure else 0.0
    t_recap = time.perf_counter() if measure else 0.0

    summary = _synthesize_summary(
        topic=topic,
        opening_summary=str(records[0].summary or ""),
        tail_summary=str(records[-1].summary or ""),
        important_facts=important_facts,
        decisions=decisions,
        current_goals=current_goals,
        open_questions=open_questions,
        next_steps=next_steps,
        chunk_count=len(records),
    )

    recap_synthesis_ms = round((time.perf_counter() - t_recap) * 1000, 2) if measure else 0.0
    audit_dict = dict(chunk_audit or {})
    if measure:
        audit_dict["stage_timing_ms"] = {
            "merge_lists_ms": merge_lists_ms,
            "recap_synthesis_ms": recap_synthesis_ms,
            "merge_total_ms": round(merge_lists_ms + recap_synthesis_ms, 2),
        }

    merged = ConversationMemoryRecord(
        topic=topic,
        important_facts=important_facts,
        current_goals=current_goals,
        decisions=decisions,
        open_questions=open_questions,
        next_steps=next_steps,
        summary=summary,
        raw={
            "merged": True,
            "merge_version": _VERSION,
            "summary_synthesis": _SUMMARY_SYNTHESIS_VERSION,
            "source_chunk_count": len(records),
            "chunk_snapshots": [_record_snapshot(r) for r in records],
        },
        parse_ok=all(r.parse_ok for r in records),
        model_id=next(
            (r.model_id for r in reversed(records) if r.model_id),
            records[0].model_id,
        ),
        latency_ms=round(sum(float(r.latency_ms or 0.0) for r in records), 2),
        thread_chars_in=original_chars,
        condense_audit={
            "version": "memory_extraction_audit_v1",
            "strategy": "recall_chunked",
            "original_chars": original_chars,
            "lora_call_count": len(records),
            "chunk_audit": audit_dict,
            "failed_chunk_indices": list(failed_chunk_indices or []),
            "merge_version": _VERSION,
        },
    )
    _logger.info("[recap_len_debug] after_merge chars=%s", len(summary))
    return merged
