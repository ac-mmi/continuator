"""Continuation-state → AI handoff briefing (V3).

Optimizes for another LLM continuing the conversation — not human recap.
Uses archetype-based role framing, mandatory next action, field de-duplication,
and minimum briefing richness (120–180 words).
"""
from __future__ import annotations

import re
from typing import Any

from handoff_generator_v2 import (
    CONTINUATION_KEYS,
    _clean_voice,
    _clean_voice_preserve_lines,
    _listify,
    continuation_state_from_output,
)

ARCHETYPE_ROLES: dict[str, str] = {
    "tutorial": "Tutor",
    "debugging": "Engineer",
    "project_management": "Project Lead",
    "journal": "Coach",
    "research": "Research Assistant",
    "github": "Engineer",
    "reddit": "Facilitator",
    "mixed": "Assistant",
}

_NEXT_PREFIXES = (
    "the next step would be to ",
    "the next actionable step is to ",
    "the next step is to ",
    "next step: ",
    "next: ",
    "continue by ",
    "should ",
    "need to ",
)

_ARCHETYPE_NEXT_FALLBACK: dict[str, str] = {
    "tutorial": (
        "Resume teaching from the current lesson point: explain the next concept, "
        "check understanding with one question, then assign a short exercise."
    ),
    "debugging": (
        "Continue diagnosing from the last known symptom: propose the next check, "
        "interpret results, and narrow the root cause."
    ),
    "project_management": (
        "Pick up the open project thread: summarize blockers, propose the next decision, "
        "and ask what resource or approval is needed."
    ),
    "journal": (
        "Continue the reflection with one focused question about what they want to "
        "change, accept, or explore next — then listen."
    ),
    "research": (
        "Continue synthesizing: state the open hypothesis, propose the next source or "
        "experiment, and list what evidence would resolve uncertainty."
    ),
    "github": (
        "Continue the technical thread: address the open issue or question directly "
        "and propose a concrete fix, workaround, or next diagnostic step."
    ),
    "reddit": (
        "Continue the community thread: respond to the latest question, offer one "
        "practical next step, and ask what constraint matters most."
    ),
    "mixed": (
        "Continue from the current stopping point: restate what is unfinished and "
        "take the next concrete step in the conversation."
    ),
}

_MIN_WORDS = 120
_MAX_WORDS = 180

_SUMMARY_LEAD_FIXES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^[Tt]he slice (discusses|explains|covers|is about|outlines)\s+"), r"The session \1 "),
    (re.compile(r"^[Tt]his section (discusses|explains|covers|is about|outlines)\s+"), r"The session \1 "),
    (re.compile(r"^[Tt]his section\s+"), "The session covers "),
    (re.compile(r"^[Tt]he slice\s+"), "The session covers "),
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _word_count(text: str) -> int:
    return len((text or "").split())


def _clean_summary(text: str) -> str:
    out = _clean_voice(text)
    for pattern, replacement in _SUMMARY_LEAD_FIXES:
        out = pattern.sub(replacement, out)
    return out.strip()


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _sentence_overlap(a: str, b: str) -> bool:
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(shorter) >= 40 and shorter in longer:
        return True
    return na[:80] == nb[:80]


def _dedupe_sentences(sentences: list[str]) -> list[str]:
    kept: list[str] = []
    for sent in sentences:
        cleaned = _clean_voice(sent)
        if not cleaned or len(cleaned) < 12:
            continue
        if any(_sentence_overlap(cleaned, prev) for prev in kept):
            continue
        kept.append(cleaned)
    return kept


def _merge_position(current: str, continuation: str, summary: str) -> str:
    """Combine current_state + continuation_context without duplication."""
    parts = _dedupe_sentences(
        _split_sentences(current) + _split_sentences(continuation)
    )
    if parts:
        return " ".join(parts)
    if summary:
        return _clean_summary(summary)
    return ""


def _extract_next_from_text(text: str) -> str:
    lower = text.lower()
    for prefix in _NEXT_PREFIXES:
        if prefix in lower:
            idx = lower.index(prefix)
            tail = text[idx + len(prefix) :].strip().rstrip(".")
            if tail:
                return tail[0].upper() + tail[1:] if tail else tail
    return ""


def _infer_role(archetype: str | None, state: dict[str, Any]) -> str:
    key = (archetype or "mixed").strip().lower()
    base = ARCHETYPE_ROLES.get(key, ARCHETYPE_ROLES["mixed"])
    topic = str(state.get("topic") or "").strip()
    if topic and len(topic) < 80:
        return f"{base} — continue on: {topic}"
    return f"{base} — continue the prior conversation from the exact stopping point"


def _derive_next_action(
    state: dict[str, Any],
    *,
    position: str,
    archetype: str | None,
) -> str:
    continuation = _clean_voice(str(state.get("continuation_context") or ""))
    current = _clean_voice(str(state.get("current_state") or ""))
    summary = _clean_summary(str(state.get("summary") or ""))

    candidates: list[str] = []

    for source in (continuation, current, summary):
        extracted = _extract_next_from_text(source)
        if extracted:
            candidates.append(extracted)

    for obj in _listify(state.get("objective")):
        cleaned = _clean_voice(obj)
        if cleaned:
            candidates.append(cleaned)

    for problem in _listify(state.get("active_problems")):
        cleaned = _clean_voice(problem)
        if cleaned:
            if not cleaned.lower().startswith(("resolve", "address", "fix", "answer")):
                candidates.append(f"Address: {cleaned}")
            else:
                candidates.append(cleaned)

    for step in _listify(state.get("next_steps")):
        cleaned = _clean_voice(step)
        if cleaned:
            candidates.append(cleaned)

    for question in _listify(state.get("open_questions")):
        cleaned = _clean_voice(question)
        if cleaned:
            candidates.append(f"Answer: {cleaned}")

    # Continuation tail often holds the actionable delta beyond current_state.
    if continuation and current:
        ctx_norm, cur_norm = _normalize(continuation), _normalize(current)
        if len(ctx_norm) > len(cur_norm) + 25 and not ctx_norm.startswith(cur_norm[: min(len(cur_norm), 80)]):
            tail = continuation
            if cur_norm and cur_norm in ctx_norm:
                tail = continuation[continuation.lower().find(cur_norm[:40]) + len(cur_norm) :].strip(" ,.")
            if tail and len(tail) > 20:
                candidates.append(tail[0].upper() + tail[1:] if tail else tail)

    key = (archetype or "mixed").strip().lower()
    candidates.append(_ARCHETYPE_NEXT_FALLBACK.get(key, _ARCHETYPE_NEXT_FALLBACK["mixed"]))

    for candidate in candidates:
        cleaned = _clean_voice(candidate).strip()
        if not cleaned or len(cleaned) < 10:
            continue
        if position and _sentence_overlap(cleaned, position):
            continue
        if any(_sentence_overlap(cleaned, s) for s in _split_sentences(position)):
            continue
        return cleaned.rstrip(".")

    return _ARCHETYPE_NEXT_FALLBACK.get(key, _ARCHETYPE_NEXT_FALLBACK["mixed"])


def _fallback_position_from_summary(state: dict[str, Any]) -> str:
    topic = _clean_voice(str(state.get("topic") or ""))
    summary = _clean_summary(str(state.get("summary") or ""))
    goals = [_clean_voice(g) for g in _listify(state.get("goals"))]
    goals = [g for g in goals if g]

    parts: list[str] = []
    if topic:
        parts.append(f"The session covers {topic.rstrip('.')}.")
    if summary:
        parts.extend(_split_sentences(summary)[:3])
    if goals:
        parts.append(f"Active goals include: {goals[0]}.")
    return " ".join(_dedupe_sentences(parts))


def _trim_to_word_budget(text: str, budget: int) -> str:
    words = (text or "").split()
    if len(words) <= budget:
        return text.strip()
    return " ".join(words[:budget]).rstrip(".,;") + "…"


def _expand_to_min_words(
    sections: dict[str, str | list[str]],
    *,
    state: dict[str, Any],
    min_words: int,
) -> dict[str, str | list[str]]:
    """Pad briefing with non-duplicative detail until minimum word count."""
    def total() -> int:
        n = _word_count(str(sections.get("position") or ""))
        n += _word_count(str(sections.get("next_action") or ""))
        for key in ("completed", "open_problems", "constraints", "resolved"):
            for item in sections.get(key) or []:
                n += _word_count(str(item))
        return n

    if total() >= min_words:
        return sections

    summary_sents = _dedupe_sentences(_split_sentences(_clean_summary(str(state.get("summary") or ""))))
    pos = str(sections.get("position") or "")
    for sent in summary_sents:
        if total() >= min_words:
            break
        if not _sentence_overlap(sent, pos):
            sections["position"] = f"{pos} {sent}".strip() if pos else sent
            pos = str(sections["position"])

    completed = list(sections.get("completed") or [])
    for item in _listify(state.get("completed_work")):
        if total() >= min_words:
            break
        cleaned = _clean_voice(item)
        if cleaned and not any(_sentence_overlap(cleaned, x) for x in completed + [pos]):
            completed.append(cleaned)
    sections["completed"] = completed

    for item in _listify(state.get("important_facts")):
        if total() >= min_words:
            break
        cleaned = _clean_voice(str(item))
        if cleaned and not any(_sentence_overlap(cleaned, x) for x in completed + [pos]):
            completed.append(cleaned)
    sections["completed"] = completed

    constraints = list(sections.get("constraints") or [])
    for item in _listify(state.get("constraints")):
        if total() >= min_words:
            break
        cleaned = _clean_voice(item)
        if cleaned and cleaned not in constraints:
            constraints.append(cleaned)
    sections["constraints"] = constraints

    return sections


def generate_handoff_briefing(
    state: dict[str, Any],
    *,
    archetype: str | None = None,
) -> str:
    """Build a continuation-first handoff briefing from V10 (or mixed) fields."""
    current = _clean_voice(str(state.get("current_state") or ""))
    continuation = _clean_voice(str(state.get("continuation_context") or ""))
    summary = _clean_summary(str(state.get("summary") or ""))
    topic = _clean_voice(str(state.get("topic") or ""))

    has_continuation = any(
        [
            current,
            continuation,
            _listify(state.get("objective")),
            _listify(state.get("completed_work")),
            _listify(state.get("active_problems")),
        ]
    )
    has_fallback = bool(topic or summary or _listify(state.get("next_steps")) or _listify(state.get("open_questions")))
    if not has_continuation and not has_fallback:
        return ""

    role = _infer_role(archetype, state)
    position = _merge_position(current, continuation, summary)
    if not position:
        position = _fallback_position_from_summary(state)

    completed = _dedupe_sentences(
        [_clean_voice(x) for x in _listify(state.get("completed_work"))]
    )
    open_problems = _dedupe_sentences(
        [_clean_voice(x) for x in _listify(state.get("active_problems"))]
    )
    resolved = _dedupe_sentences(
        [_clean_voice(x) for x in _listify(state.get("resolved_problems"))]
    )
    constraints = _dedupe_sentences(
        [_clean_voice(x) for x in _listify(state.get("constraints"))]
    )

    next_action = _derive_next_action(state, position=position, archetype=archetype)

    sections: dict[str, str | list[str]] = {
        "position": position,
        "next_action": next_action,
        "completed": completed[:8],
        "open_problems": open_problems[:8],
        "resolved": resolved[:6],
        "constraints": constraints[:6],
    }
    sections = _expand_to_min_words(sections, state=state, min_words=_MIN_WORDS)

    position = str(sections["position"])
    next_action = str(sections["next_action"])
    completed = list(sections.get("completed") or [])
    open_problems = list(sections.get("open_problems") or [])
    resolved = list(sections.get("resolved") or [])
    constraints = list(sections.get("constraints") or [])

    lines = [
        "# AI Handoff Briefing",
        "",
        "You are picking up an in-progress conversation. Continue naturally — do not recap for a human audience.",
        "",
        "## Role",
        role,
        "",
        "## Current position",
        _trim_to_word_budget(position or "Session stopped mid-thread; infer context from completed work and next action.", 90),
    ]

    if completed:
        lines.extend(["", "## Completed work"])
        lines.extend(f"- {_trim_to_word_budget(item, 35)}" for item in completed[:8])

    if open_problems:
        lines.extend(["", "## Open problems"])
        lines.extend(f"- {_trim_to_word_budget(item, 35)}" for item in open_problems[:8])

    if resolved:
        lines.extend(["", "## Recently resolved"])
        lines.extend(f"- {_trim_to_word_budget(item, 30)}" for item in resolved[:6])

    if constraints:
        lines.extend(["", "## Constraints"])
        lines.extend(f"- {_trim_to_word_budget(item, 30)}" for item in constraints[:6])

    lines.extend(["", "## Next action", next_action])

    text = "\n".join(lines).strip()

    if _word_count(text) > _MAX_WORDS:
        overflow = _word_count(text) - _MAX_WORDS
        pos_words = (sections.get("position") or "").split()
        if len(pos_words) > 40:
            trimmed = " ".join(pos_words[: max(30, len(pos_words) - overflow)])
            text = text.replace(str(sections["position"]), trimmed.rstrip(".,;") + "…", 1)

    for forbidden in ("The slice", "The discussion is focused", "The participant"):
        if forbidden.lower() in text.lower():
            text = _clean_voice_preserve_lines(text)
            break

    return text


__all__ = [
    "ARCHETYPE_ROLES",
    "CONTINUATION_KEYS",
    "continuation_state_from_output",
    "generate_handoff_briefing",
]
