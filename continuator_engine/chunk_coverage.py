"""Operational chunk coverage — adaptive saliency + head/tail preservation (deterministic)."""
from __future__ import annotations

import math
import os
import re
from typing import Any

from chunk_saliency import (
    compute_chunk_cognitive_scores,
    operational_transition_signal,
    score_chunk_operational_saliency,
)

_COVERAGE_VERSION = "operational_chunk_coverage_v2"
_CHUNKING_PROFILE_VERSION = "adaptive_sparse_chunk_preservation_v1"
_SALIENCY_MIN_GAP = 2
_ISSUE_THREAD_RX = re.compile(
    r"\b(github|issue|disabled|jquery|reproduc|expected|actual|steps to|bug\b|focus event)\b",
    re.I,
)
_SALIENCY_ADJACENT_REDUNDANCY = 0.72
_SALIENCY_ADJACENT_SCORE_RATIO = 1.08


def operational_chunk_coverage_enabled() -> bool:
    return str(os.getenv("ENABLE_OPERATIONAL_CHUNK_COVERAGE", "1")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def operational_chunk_strategy() -> str:
    return str(os.getenv("OPERATIONAL_CHUNK_STRATEGY", "adaptive_saliency_sampling")).strip().lower()


def _read_float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return float(default)


def _read_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return int(default)


def sparse_chunk_preservation_enabled() -> bool:
    return str(os.getenv("ENABLE_SPARSE_CHUNK_PRESERVATION", "1")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _saliency_scores_for_chunks(all_chunks: list[str]) -> list[float]:
    scores: list[float] = []
    retained: list[str] = []
    for i, ch in enumerate(all_chunks):
        score, _ = score_chunk_operational_saliency(ch, all_chunks, i, retained_texts=retained)
        scores.append(float(score))
        if score >= 0.42:
            retained.append(ch)
    return scores


def _saliency_variance(scores: list[float]) -> float:
    if len(scores) < 2:
        return 0.0
    mean = sum(scores) / len(scores)
    var = sum((s - mean) ** 2 for s in scores) / len(scores)
    return round(math.sqrt(var), 4)


def _corpus_operational_evolution_likelihood(all_chunks: list[str]) -> float:
    """0–1 prior: high when thread looks like dense debugging / pivot-rich (stay normal chunking)."""
    if not all_chunks:
        return 0.0
    per_chunk: list[float] = []
    fail_scores: list[float] = []
    for ch in all_chunks:
        cs = compute_chunk_cognitive_scores(ch)
        trans = operational_transition_signal(ch)
        fail = float(cs.get("failure") or 0.0)
        fail_scores.append(fail)
        # Transition regex alone (e.g. 'regression' on issue trackers) must not force dense mode.
        dense_score = max(
            fail * 1.15,
            float(cs.get("reasoning_shift") or 0.0) * 0.9,
            float(cs.get("operational") or 0.0) * 0.85,
            trans * 0.45,
        )
        if trans > 0.35 and fail < 0.12:
            dense_score = max(fail * 1.1, float(cs.get("operational") or 0.0) * 0.5, 0.22)
        per_chunk.append(dense_score)
    per_chunk.sort(reverse=True)
    top_n = per_chunk[: max(2, len(per_chunk) // 2)]
    blended = sum(top_n) / len(top_n)
    if len(fail_scores) >= 2 and sum(1 for f in fail_scores if f >= 0.2) < 2:
        blended = min(blended, 0.36)
    return round(min(1.0, blended), 4)


def assess_sparse_preservation_candidate(
    text: str,
    all_chunks: list[str],
) -> tuple[bool, dict[str, Any]]:
    """
    Lightweight heuristics — no embeddings / LLM.
    True when paragraph chunking likely over-fragmented a low-density issue thread.
    """
    reasons: list[str] = []
    reject: list[str] = []
    raw = (text or "").strip()
    chunks = [c for c in (all_chunks or []) if str(c or "").strip()]
    original_count = len(chunks)
    total_chars = len(raw)

    max_chars = _read_int_env("SPARSE_PRESERVE_MAX_CHARS", 5500)
    max_original = _read_int_env("SPARSE_PRESERVE_MAX_ORIGINAL_CHUNKS", 6)
    max_variance = _read_float_env("SPARSE_PRESERVE_MAX_SALIENCY_STDEV", 0.20)
    max_evo = _read_float_env("SPARSE_PRESERVE_MAX_EVOLUTION_LIKELIHOOD", 0.42)

    signals: dict[str, Any] = {
        "total_chars": total_chars,
        "original_chunk_count": original_count,
        "max_chars_threshold": max_chars,
        "max_original_chunks_threshold": max_original,
    }

    if not sparse_chunk_preservation_enabled():
        reject.append("preservation_disabled")
        return False, {**signals, "accept": False, "rejection_reasons": reject, "accept_reasons": reasons}

    if original_count <= 1:
        reject.append("already_single_chunk")
        return False, {**signals, "accept": False, "rejection_reasons": reject, "accept_reasons": reasons}

    if total_chars > max_chars:
        reject.append(f"total_chars_gt_{max_chars}")
    else:
        reasons.append(f"total_chars_lte_{max_chars}")

    if original_count > max_original:
        reject.append(f"original_chunks_gt_{max_original}")
    else:
        reasons.append(f"original_chunks_lte_{max_original}")

    sal_scores = _saliency_scores_for_chunks(chunks)
    sal_var = _saliency_variance(sal_scores)
    evo = _corpus_operational_evolution_likelihood(chunks)
    issue_hits = sum(1 for ch in chunks if _ISSUE_THREAD_RX.search(ch))
    issue_ratio = issue_hits / max(len(chunks), 1)
    signals["issue_thread_ratio"] = round(issue_ratio, 4)
    if issue_ratio >= 0.5 and original_count <= max_original:
        evo = min(evo, 0.34)
        reasons.append(f"issue_thread_evo_cap_{evo}")
    signals["saliency_scores"] = [round(s, 4) for s in sal_scores]
    signals["saliency_variance_stdev"] = sal_var
    signals["operational_evolution_likelihood"] = evo

    if sal_var > max_variance:
        reject.append(f"saliency_variance_gt_{max_variance}")
    else:
        reasons.append(f"low_saliency_variance_{sal_var}")

    if evo >= max_evo:
        reject.append(f"evolution_likelihood_gte_{max_evo}")
    else:
        reasons.append(f"low_evolution_likelihood_{evo}")

    # Dense debugging guard: sustained failure / transition signal across many chunks
    fail_rich = sum(1 for ch in chunks if float(compute_chunk_cognitive_scores(ch).get("failure") or 0) >= 0.22)
    if fail_rich >= 3 and original_count >= 4:
        reject.append("multi_chunk_failure_density")
    if evo >= 0.55 and original_count >= 3 and total_chars >= 2800:
        reject.append("high_operational_evolution_likelihood")

    accept = not reject and len(reasons) >= 3
    return accept, {
        **signals,
        "accept": accept,
        "rejection_reasons": reject,
        "accept_reasons": reasons if accept else reasons,
    }


def merge_chunks_for_sparse_preservation(
    all_chunks: list[str],
    *,
    max_output_chunks: int = 1,
) -> list[str]:
    """Merge paragraph chunks into at most max_output_chunks coherent units."""
    chunks = [c for c in (all_chunks or []) if str(c or "").strip()]
    if not chunks:
        return []
    max_output_chunks = max(1, min(2, int(max_output_chunks)))
    if len(chunks) <= max_output_chunks:
        return chunks
    if max_output_chunks == 1:
        return ["\n\n".join(chunks)]
    mid = len(chunks) // 2
    return ["\n\n".join(chunks[:mid]), "\n\n".join(chunks[mid:])]


def adaptive_sparse_chunk_preservation(
    text: str,
    all_chunks: list[str],
    *,
    target_chars: int = 2200,
) -> tuple[list[str], dict[str, Any]]:
    """
    Optionally collapse over-fragmented sparse transcripts before MAP / transitions.
    Returns (chunks_for_pipeline, chunking_profile).
    """
    original_count = len([c for c in (all_chunks or []) if str(c or "").strip()])
    profile: dict[str, Any] = {
        "version": _CHUNKING_PROFILE_VERSION,
        "mode": "normal",
        "original_chunk_count": original_count,
        "final_chunk_count": original_count,
        "preservation_reason": [],
        "target_chars": int(target_chars),
    }
    if not all_chunks:
        return [], profile

    accept, assessment = assess_sparse_preservation_candidate(text, all_chunks)
    profile["assessment"] = assessment
    if not accept:
        profile["preservation_reason"] = assessment.get("rejection_reasons") or ["normal_chunking"]
        return list(all_chunks), profile

    total_chars = len((text or "").strip())
    max_out = 1
    if original_count > 4 or total_chars > _read_int_env("SPARSE_PRESERVE_TWO_CHUNK_MAX_CHARS", 4000):
        max_out = 2
    merged = merge_chunks_for_sparse_preservation(all_chunks, max_output_chunks=max_out)
    profile.update(
        {
            "mode": "sparse_preserved",
            "final_chunk_count": len(merged),
            "preservation_reason": assessment.get("accept_reasons") or [],
            "max_output_chunks": max_out,
        }
    )
    return merged, profile


def build_paragraph_chunks(text: str, *, target_chars: int = 2200) -> list[str]:
    """
    Paragraph/line chunking (same rules as legacy _chunk_for_hierarchical_summary, without max cap).
    """
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", raw) if p.strip()]
    if not paragraphs:
        return [raw]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        candidate = p if not buf else f"{buf}\n\n{p}"
        if len(candidate) <= target_chars:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
            buf = ""
        if len(p) <= target_chars:
            buf = p
            continue
        lines = [x.strip() for x in p.split("\n") if x.strip()]
        line_buf = ""
        for ln in lines:
            c2 = ln if not line_buf else f"{line_buf}\n{ln}"
            if len(c2) <= target_chars:
                line_buf = c2
            else:
                if line_buf:
                    chunks.append(line_buf)
                line_buf = ln[:target_chars]
        if line_buf:
            chunks.append(line_buf)
    if buf:
        chunks.append(buf)
    return chunks


def _index_ranges_dropped(selected_indices: list[int], all_count: int) -> list[list[int]]:
    if all_count <= 0 or not selected_indices:
        return []
    selected_set = set(selected_indices)
    ranges: list[list[int]] = []
    start: int | None = None
    for i in range(all_count):
        if i in selected_set:
            if start is not None:
                ranges.append([start, i - 1])
                start = None
            continue
        if start is None:
            start = i
    if start is not None:
        ranges.append([start, all_count - 1])
    return ranges


def _jaccard_text(a: str, b: str) -> float:
    from chunk_saliency import _safe_token_set, _jaccard

    return _jaccard(_safe_token_set(a), _safe_token_set(b))


def _resolve_slot_budgets(max_chunks: int) -> tuple[int, int, int]:
    """Return (head_n, middle_n, tail_n) summing to max_chunks."""
    head_n = max(1, min(max_chunks - 2, _read_int_env("OPERATIONAL_CHUNK_HEAD_SLOTS", 3)))
    tail_n = max(1, min(max_chunks - head_n - 1, _read_int_env("OPERATIONAL_CHUNK_TAIL_SLOTS", 2)))
    if head_n + tail_n >= max_chunks:
        head_n = max(1, max_chunks // 3)
        tail_n = max(1, max_chunks // 4)
    middle_n = max(0, max_chunks - head_n - tail_n)
    return head_n, middle_n, tail_n


def _continuity_coverage_estimate(selected_indices: list[int], all_count: int) -> float:
    if all_count <= 0 or not selected_indices:
        return 0.0
    span = selected_indices[-1] - selected_indices[0] + 1
    return round(span / all_count, 4)


def _skipped_low_signal_regions(
    selected_indices: list[int],
    all_count: int,
    *,
    min_gap: int = 8,
) -> list[list[int]]:
    """Largest dropped index ranges (at least min_gap wide)."""
    dropped = _index_ranges_dropped(selected_indices, all_count)
    return [r for r in dropped if (r[1] - r[0] + 1) >= min_gap]


def select_operational_chunks_head_tail(
    all_chunks: list[str],
    *,
    max_chunks: int = 12,
    head_ratio: float | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Legacy head+tail fixed-ratio selection."""
    all_chunks = [c for c in (all_chunks or []) if str(c or "").strip()]
    max_chunks = max(1, int(max_chunks))
    ratio = _read_float_env("OPERATIONAL_CHUNK_HEAD_RATIO", head_ratio if head_ratio is not None else 0.67)
    ratio = max(0.1, min(0.9, float(ratio)))

    all_count = len(all_chunks)
    chars_all = sum(len(c) for c in all_chunks)

    if all_count == 0:
        return [], {
            "version": _COVERAGE_VERSION,
            "enabled": operational_chunk_coverage_enabled(),
            "strategy": "empty",
            "all_chunks_count": 0,
            "selected_chunks_count": 0,
            "max_chunks": max_chunks,
            "selected_indices": [],
            "dropped_index_ranges": [],
            "head_count": 0,
            "tail_count": 0,
            "chars_all": 0,
            "chars_selected": 0,
            "coverage_ratio": 0.0,
        }

    if all_count <= max_chunks:
        indices = list(range(all_count))
        selected = [all_chunks[i] for i in indices]
        chars_selected = sum(len(c) for c in selected)
        return selected, {
            "version": _COVERAGE_VERSION,
            "enabled": operational_chunk_coverage_enabled(),
            "strategy": "full",
            "all_chunks_count": all_count,
            "selected_chunks_count": len(selected),
            "max_chunks": max_chunks,
            "selected_indices": indices,
            "dropped_index_ranges": [],
            "head_count": all_count,
            "tail_count": 0,
            "chars_all": chars_all,
            "chars_selected": chars_selected,
            "coverage_ratio": round(chars_selected / max(chars_all, 1), 4),
            "incomplete": False,
        }

    head_n = max(1, int(round(max_chunks * ratio)))
    tail_n = max(1, max_chunks - head_n)
    if head_n + tail_n > max_chunks:
        tail_n = max_chunks - head_n

    head_indices = list(range(min(head_n, all_count)))
    tail_start = max(0, all_count - tail_n)
    tail_indices = list(range(tail_start, all_count))

    selected_indices: list[int] = []
    seen: set[int] = set()
    for idx in head_indices + tail_indices:
        if idx not in seen:
            seen.add(idx)
            selected_indices.append(idx)
    selected_indices.sort()

    if len(selected_indices) > max_chunks:
        tail_keep = [i for i in selected_indices if i >= tail_start]
        head_keep = [i for i in selected_indices if i < tail_start]
        need = max_chunks - len(tail_keep)
        selected_indices = (head_keep[: max(need, 0)] + tail_keep)[:max_chunks]
        selected_indices.sort()

    selected = [all_chunks[i] for i in selected_indices]
    chars_selected = sum(len(c) for c in selected)
    dropped_ranges = _index_ranges_dropped(selected_indices, all_count)
    actual_head = sum(1 for i in selected_indices if i < head_n)
    actual_tail = sum(1 for i in selected_indices if i >= tail_start)

    return selected, {
        "version": _COVERAGE_VERSION,
        "enabled": True,
        "strategy": "head_tail",
        "all_chunks_count": all_count,
        "selected_chunks_count": len(selected),
        "max_chunks": max_chunks,
        "head_count": actual_head,
        "tail_count": actual_tail,
        "dynamic_middle_count": 0,
        "head_ratio_config": round(ratio, 4),
        "selected_indices": selected_indices,
        "dropped_index_ranges": dropped_ranges,
        "tail_index_start": tail_start,
        "chars_all": chars_all,
        "chars_selected": chars_selected,
        "coverage_ratio": round(chars_selected / max(chars_all, 1), 4),
        "continuity_coverage_estimate": _continuity_coverage_estimate(selected_indices, all_count),
        "incomplete": True,
    }


def adaptive_saliency_sampling(
    all_chunks: list[str],
    *,
    max_chunks: int = 12,
) -> tuple[list[str], dict[str, Any]]:
    """
    Head + tail anchors with saliency-ranked middle slots (deterministic).
    """
    all_chunks = [c for c in (all_chunks or []) if str(c or "").strip()]
    max_chunks = max(1, int(max_chunks))
    all_count = len(all_chunks)
    chars_all = sum(len(c) for c in all_chunks)

    empty_meta: dict[str, Any] = {
        "version": _COVERAGE_VERSION,
        "enabled": operational_chunk_coverage_enabled(),
        "strategy": "empty",
        "all_chunks_count": 0,
        "selected_chunks_count": 0,
        "max_chunks": max_chunks,
        "selected_indices": [],
        "saliency_selected_indices": [],
        "saliency_scores": {},
        "dynamic_middle_count": 0,
        "skipped_low_signal_regions": [],
        "continuity_coverage_estimate": 0.0,
    }
    if all_count == 0:
        return [], empty_meta

    if all_count <= max_chunks:
        indices = list(range(all_count))
        selected = [all_chunks[i] for i in indices]
        chars_selected = sum(len(c) for c in selected)
        return selected, {
            **empty_meta,
            "strategy": "full",
            "all_chunks_count": all_count,
            "selected_chunks_count": len(selected),
            "selected_indices": indices,
            "saliency_selected_indices": indices,
            "head_count": all_count,
            "tail_count": 0,
            "chars_all": chars_all,
            "chars_selected": chars_selected,
            "coverage_ratio": round(chars_selected / max(chars_all, 1), 4),
            "continuity_coverage_estimate": 1.0,
            "incomplete": False,
        }

    head_n, middle_n, tail_n = _resolve_slot_budgets(max_chunks)
    head_indices = list(range(min(head_n, all_count)))
    tail_start = max(0, all_count - tail_n)
    tail_indices = list(range(tail_start, all_count))
    reserved = set(head_indices) | set(tail_indices)

    middle_start = head_indices[-1] + 1 if head_indices else 0
    middle_end = tail_start - 1
    middle_candidates = [i for i in range(middle_start, middle_end + 1) if i not in reserved]

    saliency_scores: dict[str, dict[str, float]] = {}
    ranked: list[tuple[int, float, dict[str, float]]] = []
    for i in middle_candidates:
        score, breakdown = score_chunk_operational_saliency(all_chunks[i], all_chunks, i)
        saliency_scores[str(i)] = breakdown
        ranked.append((i, score, breakdown))
    ranked.sort(key=lambda x: (-x[1], x[0]))

    selected_middle: list[int] = []
    selected_middle_scores: list[float] = []
    retained_texts: list[str] = [all_chunks[i] for i in head_indices]

    def _try_add(idx: int, score: float, *, strict: bool) -> bool:
        if idx in selected_middle:
            return False
        if strict and selected_middle:
            last = selected_middle[-1]
            if abs(idx - last) < _SALIENCY_MIN_GAP and score < selected_middle_scores[-1] * _SALIENCY_ADJACENT_SCORE_RATIO:
                return False
            for j in selected_middle:
                if _jaccard_text(all_chunks[idx], all_chunks[j]) >= _SALIENCY_ADJACENT_REDUNDANCY:
                    if score < 0.52:
                        return False
        selected_middle.append(idx)
        selected_middle_scores.append(score)
        retained_texts.append(all_chunks[idx])
        return True

    for idx, score, _ in ranked:
        if len(selected_middle) >= middle_n:
            break
        _try_add(idx, score, strict=True)

    if len(selected_middle) < middle_n:
        for idx, score, _ in ranked:
            if len(selected_middle) >= middle_n:
                break
            if idx not in selected_middle:
                _try_add(idx, score, strict=False)

    selected_indices = sorted(set(head_indices) | set(selected_middle) | set(tail_indices))
    if len(selected_indices) > max_chunks:
        tail_keep = [i for i in selected_indices if i >= tail_start]
        head_keep = [i for i in selected_indices if i < tail_start]
        need = max_chunks - len(tail_keep)
        selected_indices = sorted((head_keep[: max(need, 0)] + tail_keep)[:max_chunks])

    selected = [all_chunks[i] for i in selected_indices]
    chars_selected = sum(len(c) for c in selected)
    dropped_ranges = _index_ranges_dropped(selected_indices, all_count)
    saliency_middle = [i for i in selected_middle if i in selected_indices]

    return selected, {
        "version": _COVERAGE_VERSION,
        "enabled": True,
        "strategy": "adaptive_saliency_sampling",
        "all_chunks_count": all_count,
        "selected_chunks_count": len(selected),
        "max_chunks": max_chunks,
        "head_count": sum(1 for i in selected_indices if i in head_indices),
        "tail_count": sum(1 for i in selected_indices if i >= tail_start),
        "dynamic_middle_count": sum(1 for i in selected_indices if middle_start <= i <= middle_end),
        "head_slots_config": head_n,
        "tail_slots_config": tail_n,
        "middle_slots_config": middle_n,
        "selected_indices": selected_indices,
        "saliency_selected_indices": sorted(saliency_middle),
        "saliency_scores": {k: v for k, v in saliency_scores.items() if int(k) in saliency_middle},
        "saliency_top_middle_candidates": [
            {"index": i, "score": round(s, 4)} for i, s, _ in ranked[: min(8, len(ranked))]
        ],
        "dropped_index_ranges": dropped_ranges,
        "skipped_low_signal_regions": _skipped_low_signal_regions(selected_indices, all_count),
        "tail_index_start": tail_start,
        "middle_index_range": [middle_start, middle_end] if middle_candidates else [],
        "chars_all": chars_all,
        "chars_selected": chars_selected,
        "coverage_ratio": round(chars_selected / max(chars_all, 1), 4),
        "continuity_coverage_estimate": _continuity_coverage_estimate(selected_indices, all_count),
        "incomplete": True,
    }


def select_operational_chunks(
    all_chunks: list[str],
    *,
    max_chunks: int = 12,
    head_ratio: float | None = None,
    chunking_profile: dict[str, Any] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """
    Select up to max_chunks with operational continuity preservation.
    Default: adaptive_saliency_sampling; rollback via OPERATIONAL_CHUNK_STRATEGY=head_tail.
    """
    all_chunks = [c for c in (all_chunks or []) if str(c or "").strip()]
    max_chunks = max(1, int(max_chunks))
    profile = chunking_profile if isinstance(chunking_profile, dict) else {}
    original_all_count = int(profile.get("original_chunk_count") or len(all_chunks))

    # Tiny conversations: never drop middle via saliency sampling.
    force_full = len(all_chunks) <= 3 or original_all_count <= 3
    if force_full and all_chunks:
        indices = list(range(len(all_chunks)))
        chars_all = sum(len(c) for c in all_chunks)
        chars_selected = sum(len(c) for c in all_chunks)
        cov: dict[str, Any] = {
            "version": _COVERAGE_VERSION,
            "enabled": operational_chunk_coverage_enabled(),
            "strategy": "full",
            "strategy_override": "tiny_conversation_full",
            "all_chunks_count": len(all_chunks),
            "selected_chunks_count": len(all_chunks),
            "max_chunks": max_chunks,
            "selected_indices": indices,
            "dropped_index_ranges": [],
            "chars_all": chars_all,
            "chars_selected": chars_selected,
            "coverage_ratio": 1.0,
            "continuity_coverage_estimate": 1.0,
            "incomplete": False,
        }
        if profile:
            cov["chunking_profile"] = profile
            if profile.get("mode") == "sparse_preserved":
                cov["sparse_preserved"] = True
        return list(all_chunks), cov

    if not operational_chunk_coverage_enabled():
        all_count = len(all_chunks)
        selected = all_chunks[:max_chunks]
        indices = list(range(len(selected)))
        chars_all = sum(len(c) for c in all_chunks)
        chars_selected = sum(len(c) for c in selected)
        return selected, {
            "version": _COVERAGE_VERSION,
            "enabled": False,
            "strategy": "legacy_head_only",
            "all_chunks_count": all_count,
            "selected_chunks_count": len(selected),
            "max_chunks": max_chunks,
            "selected_indices": indices,
            "dropped_index_ranges": [[len(selected), max(all_count - 1, len(selected))]]
            if all_count > len(selected)
            else [],
            "chars_all": chars_all,
            "chars_selected": chars_selected,
            "coverage_ratio": round(chars_selected / max(chars_all, 1), 4),
            "incomplete": all_count > len(selected),
        }

    strategy = operational_chunk_strategy()
    if strategy in {"head_tail", "legacy_head_tail"}:
        selected, cov = select_operational_chunks_head_tail(all_chunks, max_chunks=max_chunks, head_ratio=head_ratio)
    else:
        selected, cov = adaptive_saliency_sampling(all_chunks, max_chunks=max_chunks)
    if profile:
        cov["chunking_profile"] = profile
        if profile.get("mode") == "sparse_preserved":
            cov["sparse_preserved"] = True
    return selected, cov
