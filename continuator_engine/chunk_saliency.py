"""Pre-MAP chunk saliency scoring — mirrors v5_pipeline cognitive / retention signals (deterministic)."""
from __future__ import annotations

import re
from typing import Any

# --- Multi-signal retention (from v5_pipeline._multi_signal_chunk_score) ---

def _safe_token_set(text: str) -> set[str]:
    return {
        t.lower()
        for t in re.findall(r"[a-zA-Z][a-zA-Z0-9_+-]+", text or "")
        if len(t) >= 3
    }


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / max(union, 1)


def multi_signal_chunk_score(
    chunk_text: str,
    recent_chunk_texts: list[str],
    recent_retained_texts: list[str],
) -> dict[str, float]:
    text = chunk_text or ""
    low = text.lower()
    tok = _safe_token_set(text)
    recent_join = "\n".join(recent_chunk_texts[-3:]) if recent_chunk_texts else ""
    retained_join = "\n".join(recent_retained_texts[-4:]) if recent_retained_texts else ""
    recent_tok = _safe_token_set(recent_join)
    retained_tok = _safe_token_set(retained_join)

    def _ratio(hit_count: int, denom: int) -> float:
        return max(0.0, min(1.0, float(hit_count) / max(denom, 1)))

    user_initiative_hits = len(
        re.findall(
            r"\b(need|want|let's|lets|please|change|instead|focus|priority|next step|rewrite|fix|should we|do this)\b",
            low,
        )
    )
    assistant_elab_hits = len(
        re.findall(r"\b(you can|here's|here is|for example|in summary|overall)\b", low)
    )
    user_initiative = max(
        0.0,
        min(1.0, 0.6 * _ratio(user_initiative_hits, 4) + 0.4 * (1.0 - _ratio(assistant_elab_hits, 5))),
    )

    unresolved_hits = len(
        re.findall(
            r"\b(todo|pending|unresolved|still|failing|error|bug|verify|test|next step|follow up|later|retry)\b",
            low,
        )
    )
    unresolved_pressure = _ratio(unresolved_hits, 5)

    constraint_hits = len(
        re.findall(
            r"\b(local|offline|latency|deadline|budget|hardware|memory|cpu|gpu|no cloud|open source|on-device|compatibility)\b",
            low,
        )
    )
    constraint_binding = _ratio(constraint_hits, 4)

    overlap_recent = _jaccard(tok, recent_tok) if recent_tok else 0.0
    overlap_retained = _jaccard(tok, retained_tok) if retained_tok else 0.0
    novelty = max(0.0, min(1.0, 1.0 - max(overlap_recent, overlap_retained)))
    redundancy = max(0.0, min(1.0, max(overlap_recent, overlap_retained)))
    trajectory_delta = max(0.0, min(1.0, 1.0 - overlap_recent))

    final_score = (
        0.18 * user_initiative
        + 0.24 * unresolved_pressure
        + 0.16 * trajectory_delta
        + 0.12 * constraint_binding
        + 0.20 * novelty
        - 0.10 * redundancy
    )
    final_score = max(0.0, min(1.0, final_score))

    return {
        "user_initiative": round(user_initiative, 4),
        "trajectory_delta": round(trajectory_delta, 4),
        "unresolved_pressure": round(unresolved_pressure, 4),
        "constraint_binding": round(constraint_binding, 4),
        "redundancy": round(redundancy, 4),
        "novelty": round(novelty, 4),
        "final_score": round(final_score, 4),
    }


# --- Cognitive mode scores (Phase 1 lexical; text-only path) ---

_COGNITIVE_OPERATIONAL_RX = re.compile(
    r"\b("
    r"implement(?:ing|ed|ation)?|building|build|fix(?:ing|ed)?|debug(?:ging)?|deploy(?:ing|ed)?|"
    r"blocked?\b|blockers?\b|stuck\b|todo\b|next step|working on|need to|have to|"
    r"ship(?:ping)?|merg(?:e|ing)|pull request|\bpr\b|sprint|milestone|deadline|"
    r"action items?|follow[- ]up|rollout|release|patch|hotfix|wip\b|in progress"
    r")\b",
    re.I,
)
_COGNITIVE_REASONING_SHIFT_RX = re.compile(
    r"\b("
    r"we realized|i realized|turns out|the real issue|the issue was|the problem was|"
    r"instead of|worked better|caused by|root cause|not .* but|"
    r"shift(?:ed)? (?:to|from)|changed (?:our|my) (?:mind|understanding)|"
    r"clarified that|we (?:now|finally) (?:see|understand)|mental model|"
    r"re[- ]frame|aha\b|eureka"
    r")\b",
    re.I,
)
_COGNITIVE_ARCHITECTURE_RX = re.compile(
    r"\b("
    r"must remain|should remain|design principle|methodology|philosophy|long[- ]lived|long[- ]term|"
    r"system[- ]wide|invariant|non[- ]negotiable|idempotent|non[- ]destruct|"
    r"tie[- ]break(?:ers?)?|constraint|architectural|stable (?:contract|behavior)|"
    r"future[- ]proof|read[- ]only policy|policy:?"
    r")\b",
    re.I,
)
_COGNITIVE_FAILURE_RX = re.compile(
    r"\b("
    r"fail(?:ed|ure|ing)?|regression|broke|broken|exception|stack trace|panic|crash|"
    r"wrong assumption|didn'?t work|dead end|anti[- ]pattern|mistake|bug\b|"
    r"error:|null pointer|timeout|503|500\b|rolled back"
    r")\b",
    re.I,
)
_COGNITIVE_TRADEOFF_RX = re.compile(
    r"\b("
    r"trade[- ]off|tradeoff|versus\b|\bvs\.|cost benefit|cost/benefit|"
    r"balance between|weighing|compromise|sacrifice|robustness|"
    r"flexibility|latency|throughput|safety|performance|"
    r"speed vs|fast vs|cheap vs|better vs|rather than .{0,40} (?:we|i) (?:chose|pick)"
    r")\b",
    re.I,
)
_TRANSITION_PIVOT_RX = re.compile(
    r"\b(?:caused|causing|causes|led to|lead to|leading to|regression|regressions|broke|broken|"
    r"failed|failing|pivot(?:ed|s|ing)?|shifted|shift|moved|changed focus|instead of|rather than|"
    r"previously|now\b|introduced|uncovered|revealed|masked|temporary|rolled back|reversed|"
    r"after operational|because of|due to|triggered|worsened|weakened|"
    r"after edits|followed by|persisted|resurfaced|coincided|stabilize|unstable|"
    r"repeated(?:ly)?|re-?run|still failing)\b",
    re.I,
)
_COG_STRUCT_TRANSITION = re.compile(
    r"\b(?:pivot(?:ed|ing)?|shifted (?:to|from|focus)|changed (?:approach|strategy|direction)|"
    r"moved (?:to|from)|instead (?:we|i)|rather than (?:we|i)|transition(?:ed)? to)\b",
    re.I,
)
_GRAV_METHODOLOGY_SHIFT = re.compile(
    r"\b(?:instead\s+of|we\s+moved\s+to|(?:the\s+)?better\s+approach|"
    r"relying\s+on\b[^.\n]{0,52}\brather\s+than\b|operational\s+philosophy|"
    r"methodology\s+shift|new\s+approach\s+is|changed\s+(?:our\s+)?approach)\b",
    re.I,
)


def _clamp01(x: float) -> float:
    return round(max(0.0, min(1.0, x)), 4)


def compute_chunk_cognitive_scores(chunk_text: str) -> dict[str, float]:
    """Text-only cognitive scores (same formulas as v5_pipeline Phase 1)."""
    t = (chunk_text or "").strip().lower()
    if not t:
        return {
            "operational": 0.0,
            "reasoning_shift": 0.0,
            "architecture": 0.0,
            "failure": 0.0,
            "tradeoff": 0.0,
            "exploratory": 0.0,
        }

    def hits(rx: re.Pattern) -> int:
        return len(rx.findall(t))

    length_norm = max(0.45, min(1.0, (len(t) ** 0.5) / 22.0))
    op_h = min(hits(_COGNITIVE_OPERATIONAL_RX), 10)
    rs_h = min(hits(_COGNITIVE_REASONING_SHIFT_RX), 10)
    ar_h = min(hits(_COGNITIVE_ARCHITECTURE_RX), 10)
    fl_h = min(hits(_COGNITIVE_FAILURE_RX), 10)
    tr_h = min(hits(_COGNITIVE_TRADEOFF_RX), 10)

    return {
        "operational": _clamp01((0.085 * op_h + 0.02) * length_norm),
        "reasoning_shift": _clamp01((0.10 * rs_h + 0.02) * length_norm),
        "architecture": _clamp01((0.09 * ar_h + 0.02) * length_norm),
        "failure": _clamp01((0.09 * fl_h + 0.02) * length_norm),
        "tradeoff": _clamp01((0.095 * tr_h + 0.02) * length_norm),
        "exploratory": 0.0,
    }


def estimate_conceptual_gravity_text_only(chunk_text: str, cognitive_scores: dict[str, float]) -> float:
    """Lightweight text-only gravity prior (Phase 3A.1 subset)."""
    t = (chunk_text or "").strip().lower()
    if not t:
        return 0.0
    n_ms = min(5, len(_GRAV_METHODOLOGY_SHIFT.findall(t)))
    n_tr = min(6, len(_COG_STRUCT_TRANSITION.findall(t)))
    n_pivot = min(6, len(_TRANSITION_PIVOT_RX.findall(t)))
    cs = cognitive_scores if isinstance(cognitive_scores, dict) else {}
    cognitive_prior = min(
        0.22,
        0.08 * float(cs.get("architecture") or 0.0)
        + 0.07 * float(cs.get("failure") or 0.0)
        + 0.06 * float(cs.get("reasoning_shift") or 0.0)
        + 0.05 * float(cs.get("tradeoff") or 0.0),
    )
    raw = 0.052 * min(4, n_ms) + 0.04 * min(4, n_tr) + 0.035 * min(4, n_pivot) + cognitive_prior
    return _clamp01(raw * 2.8)


def operational_transition_signal(chunk_text: str) -> float:
    t = chunk_text or ""
    if not t.strip():
        return 0.0
    hits = len(_TRANSITION_PIVOT_RX.findall(t)) + len(_COG_STRUCT_TRANSITION.findall(t))
    return _clamp01(hits / 5.0)


def score_chunk_operational_saliency(
    chunk_text: str,
    all_chunks: list[str],
    chunk_index: int,
    *,
    retained_texts: list[str] | None = None,
) -> tuple[float, dict[str, float]]:
    """
    Combined saliency for middle-chunk ranking (deterministic).
    Reuses trajectory_delta, reasoning_shift, gravity, unresolved_pressure, transitions.
    """
    recent = all_chunks[max(0, chunk_index - 3) : chunk_index]
    retained = retained_texts if retained_texts is not None else []
    ms = multi_signal_chunk_score(chunk_text, recent, retained)
    cs = compute_chunk_cognitive_scores(chunk_text)
    grav = estimate_conceptual_gravity_text_only(chunk_text, cs)
    trans = operational_transition_signal(chunk_text)

    saliency = (
        0.18 * float(ms.get("trajectory_delta") or 0.0)
        + 0.16 * float(ms.get("unresolved_pressure") or 0.0)
        + 0.10 * float(ms.get("novelty") or 0.0)
        - 0.08 * float(ms.get("redundancy") or 0.0)
        + 0.14 * float(cs.get("reasoning_shift") or 0.0)
        + 0.12 * float(cs.get("architecture") or 0.0)
        + 0.08 * float(cs.get("failure") or 0.0)
        + 0.08 * float(cs.get("operational") or 0.0)
        + 0.10 * grav
        + 0.10 * trans
        + 0.06 * float(ms.get("constraint_binding") or 0.0)
    )
    saliency = _clamp01(saliency)
    breakdown = {
        **{f"ms_{k}": v for k, v in ms.items()},
        **{f"cs_{k}": v for k, v in cs.items()},
        "conceptual_gravity": grav,
        "operational_transition": trans,
        "saliency": saliency,
    }
    return saliency, breakdown
