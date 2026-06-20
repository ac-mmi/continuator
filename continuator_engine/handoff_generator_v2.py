"""Continuation-state → concise AI handoff briefing (V2).

Transforms V10 continuation fields into a paste-ready briefing for a fresh LLM.
Strips observer voice ("The slice...", "The participant...") in favor of direct,
action-oriented language.
"""
from __future__ import annotations

import re
from typing import Any

CONTINUATION_KEYS = (
    "objective",
    "current_state",
    "completed_work",
    "active_problems",
    "resolved_problems",
    "constraints",
    "continuation_context",
)

_OBSERVER_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b[Tt]he participant(s)? is being asked\b"), "You are being asked"),
    (re.compile(r"\b[Tt]he participant(s)? was asked\b"), "You were asked"),
    (re.compile(r"\b[Tt]he participant(s)? is now ready\b"), "You are now ready"),
    (re.compile(r"\b[Tt]he participant(s)? has not\b"), "You have not"),
    (re.compile(r"\b[Tt]he participant(s)? have not\b"), "You have not"),
    (re.compile(r"\b[Tt]he participant(s)? is\b"), "You are"),
    (re.compile(r"\b[Tt]he participant(s)? are\b"), "You are"),
    (re.compile(r"\b[Tt]he participant(s)? was\b"), "You were"),
    (re.compile(r"\b[Tt]he participant(s)? were\b"), "You were"),
    (re.compile(r"\b[Tt]he participant(s)? has\b"), "You have"),
    (re.compile(r"\b[Tt]he participant(s)? have\b"), "You have"),
    (re.compile(r"\b[Tt]he slice (is|was) explaining\b"), "Currently explaining"),
    (re.compile(r"\b[Tt]he slice (is|was) (explaining|discussing|covering)\b"), "Currently"),
    (re.compile(r"\b[Tt]he slice (is|was|explains|discusses|covers|contains)\b"), "This section"),
    (re.compile(r"\b[Tt]he discussion (is|was) (centered on|focused on|about)\b"), "The conversation is about"),
    (re.compile(r"\b[Tt]he discussion (is|was) at\b"), "The conversation is at"),
    (re.compile(r"\b[Tt]he discussion (explores|covers|addresses|is focused on)\b"), "The conversation"),
    (re.compile(r"\b[Pp]articipants (are|were) (debating|sharing|discussing)\b"), r"People \1 \2"),
    (re.compile(r"\b[Pp]articipants (are|were|have|debate|discuss)\b"), r"People \1"),
    (re.compile(r"\b[Tt]he conversation (discusses|covers|explores|spans)\b"), "The thread"),
    (re.compile(r"\b[Tt]he tutor (is|was|has|explains)\b"), "The tutor"),
    (re.compile(r"\b[Tt]he learner (is|was|has)\b"), "The learner"),
    (re.compile(r"\b[Nn]o one has yet\b"), "Nothing has yet"),
    (re.compile(r"\b[Tt]he cluster\b"), "This section"),
    (re.compile(r"\b[Tt]his slice\b"), "This section"),
    (re.compile(r"\bPeople (\w+ing)\b"), r"People are \1"),
]

_ROLE_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\btutor|teaching|lesson|course|explains?\b", re.I), "Tutor continuing a learning session"),
    (re.compile(r"\bburnout|journal|personal|regret|stagnation\b", re.I), "Coach continuing a personal reflection"),
    (re.compile(r"\bproject manager|roadmap|scope creep|retrospective|sprint\b", re.I), "Advisor continuing a project thread"),
    (re.compile(r"\bgithub|issue|pull request|kubernetes|CVE\b", re.I), "Engineer continuing a technical discussion"),
    (re.compile(r"\breddit|post|commenter|thread\b", re.I), "Facilitator continuing a community thread"),
]


def _listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    s = str(value).strip()
    return [s] if s else []


def _clean_voice(text: str) -> str:
    out = (text or "").strip()
    if not out:
        return ""
    for pattern, replacement in _OBSERVER_PATTERNS:
        out = pattern.sub(replacement, out)
    out = re.sub(r"\s+", " ", out).strip()
    if out.endswith("."):
        return out
    return out


def _clean_voice_preserve_lines(text: str) -> str:
    """Like _clean_voice but keeps line breaks for markdown section layouts."""
    lines = (text or "").splitlines()
    return "\n".join(_clean_voice(line) if line.strip() else "" for line in lines).strip()


def _infer_role(state: dict[str, Any]) -> str:
    blob = " ".join(
        [
            str(state.get("current_state") or ""),
            str(state.get("continuation_context") or ""),
            " ".join(_listify(state.get("objective"))),
        ]
    )
    for pattern, role in _ROLE_HINTS:
        if pattern.search(blob):
            return role
    if _listify(state.get("objective")):
        return "Assistant continuing an active task"
    return "Assistant continuing the prior conversation"


def _extract_next_action(state: dict[str, Any], *, current: str, continuation: str) -> str:
    ctx = _clean_voice(continuation)
    cur = _clean_voice(current)
    if ctx and cur and ctx != cur:
        for prefix in (
            "The next step would be to ",
            "The next actionable step is to ",
            "The next step is to ",
            "Next: ",
        ):
            if prefix.lower() in ctx.lower():
                idx = ctx.lower().index(prefix.lower())
                tail = ctx[idx + len(prefix) :].strip().rstrip(".")
                if tail:
                    return tail[0].upper() + tail[1:] if tail else tail
        if len(ctx) > len(cur) + 20:
            return ctx
    objectives = _listify(state.get("objective"))
    if objectives:
        return objectives[0]
    problems = _listify(state.get("active_problems"))
    if problems:
        return f"Address: {problems[0]}"
    return ""


def generate_handoff_briefing(state: dict[str, Any]) -> str:
    """Build a concise handoff briefing from V10 continuation fields."""
    current = _clean_voice(str(state.get("current_state") or ""))
    continuation = _clean_voice(str(state.get("continuation_context") or ""))
    if not any(
        [
            current,
            continuation,
            _listify(state.get("objective")),
            _listify(state.get("completed_work")),
            _listify(state.get("active_problems")),
        ]
    ):
        return ""

    role = _infer_role(state)
    completed = [_clean_voice(x) for x in _listify(state.get("completed_work"))]
    completed = [x for x in completed if x]
    open_problems = [_clean_voice(x) for x in _listify(state.get("active_problems"))]
    open_problems = [x for x in open_problems if x]
    resolved = [_clean_voice(x) for x in _listify(state.get("resolved_problems"))]
    resolved = [x for x in resolved if x]
    constraints = [_clean_voice(x) for x in _listify(state.get("constraints"))]
    constraints = [x for x in constraints if x]
    next_action = _extract_next_action(state, current=current, continuation=continuation)

    position = current or continuation
    if current and continuation:
        cur_norm = current.lower()[:100]
        ctx_norm = continuation.lower()[:100]
        if cur_norm == ctx_norm:
            position = current
        elif continuation.startswith(current[: min(len(current), 120)]):
            position = continuation
        elif current.startswith(continuation[: min(len(continuation), 120)]):
            position = current
        elif current not in continuation and continuation not in current:
            position = f"{current} {continuation}".strip()

    lines = [
        "# AI Handoff Briefing",
        "",
        "Continue the conversation from where it stopped. Use only the context below.",
        "",
        f"## Role",
        role,
        "",
        f"## Current position",
        position or "No explicit position captured.",
    ]

    if completed:
        lines.extend(["", "## Completed work"])
        lines.extend(f"- {item}" for item in completed[:8])

    if open_problems:
        lines.extend(["", "## Open problems"])
        lines.extend(f"- {item}" for item in open_problems[:8])

    if resolved:
        lines.extend(["", "## Recently resolved"])
        lines.extend(f"- {item}" for item in resolved[:6])

    if constraints:
        lines.extend(["", "## Constraints"])
        lines.extend(f"- {item}" for item in constraints[:6])

    lines.extend(["", "## Next action"])
    lines.append(next_action or "Pick up from the current position and ask what to do next.")

    text = "\n".join(lines).strip()
    for forbidden in ("The slice", "The discussion is focused", "The participant"):
        if forbidden.lower() in text.lower():
            text = _clean_voice_preserve_lines(text)
            break
    return text


def continuation_state_from_output(output: dict[str, Any]) -> dict[str, Any]:
    """Extract continuation-only dict from a full extraction output."""
    return {key: output.get(key) for key in CONTINUATION_KEYS}
