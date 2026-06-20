"""Approach B chunk ranker — MiniLM embeddings, displacement, changepoints, MMR, terminal lock.

Zero LLM in Stage 1. Selects K chunk indices for V10 extraction before continuation export.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from chunk_selector_v2_cluster import (
    _cluster_labels,
    _cluster_members,
    _embed_chunks,
    _representative_indices,
    select_chunks_cluster_head_tail,
)

_STRATEGY = "approach_b_v1"
_MMR_LAMBDA = 0.7
_PEAK_Z_THRESHOLD = 1.0
_PELT_PENALTY_SCALE = 0.5


def default_k(n: int) -> int:
    """K = clamp(ceil(N / 5), min=3, max=8)."""
    if n <= 0:
        return 0
    return max(3, min(8, int(math.ceil(n / 5))))


def _robust_zscore(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return arr
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    scale = 1.4826 * mad if mad > 1e-12 else 1.0
    return (arr - med) / scale


def _displacement_series(embeddings: np.ndarray) -> np.ndarray:
    n = len(embeddings)
    delta = np.zeros(n, dtype=np.float64)
    if n < 2:
        return delta
    for i in range(1, n):
        delta[i] = 1.0 - float(np.dot(embeddings[i], embeddings[i - 1]))
    return delta


def _curvature_series(delta: np.ndarray) -> np.ndarray:
    n = len(delta)
    kappa = np.zeros(n, dtype=np.float64)
    if n < 3:
        return kappa
    for i in range(2, n):
        kappa[i] = float(delta[i] - delta[i - 1])
    return kappa


def _local_maxima_indices(values: np.ndarray, *, z: np.ndarray, threshold: float) -> list[int]:
    n = len(values)
    if n < 3:
        return []
    peaks: list[int] = []
    for i in range(1, n - 1):
        if values[i] >= values[i - 1] and values[i] > values[i + 1] and z[i] >= threshold:
            peaks.append(i)
    return peaks


def _segment_cost(signal: np.ndarray, start: int, end: int) -> float:
    if end <= start:
        return 0.0
    seg = signal[start:end]
    mu = float(seg.mean())
    return float(((seg - mu) ** 2).sum())


def _pelt_changepoints(signal: np.ndarray, *, penalty: float) -> list[int]:
    """Hand-rolled PELT on 1D displacement (N ≤ ~100). Returns interior split indices."""
    n = len(signal)
    if n < 4:
        return []

    # Precompute segment costs O(n^2); fine for product chunk counts.
    cost = np.zeros((n + 1, n + 1), dtype=np.float64)
    for i in range(n):
        for j in range(i + 1, n + 1):
            cost[i, j] = _segment_cost(signal, i, j)

    f = np.full(n + 1, np.inf, dtype=np.float64)
    prev = np.full(n + 1, -1, dtype=np.int32)
    f[0] = 0.0

    for t in range(1, n + 1):
        for s in range(0, t):
            cand = f[s] + cost[s, t] + penalty
            if cand < f[t]:
                f[t] = cand
                prev[t] = s

    breaks: list[int] = []
    t = n
    while prev[t] > 0:
        breaks.append(int(prev[t]))
        t = int(prev[t])
    breaks.reverse()
    return breaks


def _changepoint_boundary_indices(changepoints: list[int], n: int) -> list[int]:
    """Causal: chunk at or immediately after each changepoint."""
    out: set[int] = set()
    for cp in changepoints:
        if 0 <= cp < n:
            out.add(cp)
        if 0 <= cp + 1 < n:
            out.add(cp + 1)
    return sorted(out)


def _cluster_boundary_indices(labels: np.ndarray) -> list[int]:
    out: list[int] = []
    for i in range(1, len(labels)):
        if labels[i] != labels[i - 1]:
            out.append(i)
    return out


def _recency(n: int) -> np.ndarray:
    if n <= 1:
        return np.ones(n, dtype=np.float64)
    return (np.arange(n, dtype=np.float64) + 1.0) / float(n)


def _cluster_mass(labels: np.ndarray, cluster_count: int) -> np.ndarray:
    n = len(labels)
    mass = np.zeros(n, dtype=np.float64)
    if cluster_count <= 0:
        return mass
    memberships = _cluster_members(labels, cluster_count)
    sizes = [len(m) for m in memberships]
    max_size = max(sizes) if sizes else 1
    for cid, members in enumerate(memberships):
        imp = len(members) / max(max_size, 1)
        for idx in members:
            mass[idx] = imp
    return mass


def _boundary_bonus(i: int, boundary_set: set[int]) -> float:
    return 1.0 if i in boundary_set else 0.0


def _base_scores(
    n: int,
    *,
    delta: np.ndarray,
    mass: np.ndarray,
    boundary_set: set[int],
) -> np.ndarray:
    rho = _recency(n)
    z_delta = _robust_zscore(delta)
    scores = np.zeros(n, dtype=np.float64)
    for i in range(n):
        scores[i] = (
            0.30 * float(z_delta[i])
            + 0.30 * float(rho[i])
            + 0.20 * float(mass[i])
            + 0.20 * _boundary_bonus(i, boundary_set)
        )
    return scores


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def _mmr_select(
    candidates: list[int],
    scores: np.ndarray,
    embeddings: np.ndarray,
    *,
    k: int,
    locked: set[int],
    mmr_lambda: float = _MMR_LAMBDA,
) -> list[int]:
    picked = sorted(locked)
    pool = [i for i in candidates if i not in locked]
    pool.sort(key=lambda i: (scores[i], i), reverse=True)

    while len(picked) < k and pool:
        best_idx = -1
        best_mmr = -1e18
        for i in pool:
            if picked:
                max_sim = max(_cosine_sim(embeddings[i], embeddings[j]) for j in picked)
            else:
                max_sim = 0.0
            mmr = mmr_lambda * scores[i] - (1.0 - mmr_lambda) * max_sim
            if mmr > best_mmr or (mmr == best_mmr and (best_idx < 0 or i < best_idx)):
                best_mmr = mmr
                best_idx = i
        if best_idx < 0:
            break
        picked.append(best_idx)
        pool.remove(best_idx)

    if len(picked) < k:
        remaining = [i for i in range(len(scores)) if i not in picked]
        remaining.sort(key=lambda i: (scores[i], i), reverse=True)
        for i in remaining:
            if len(picked) >= k:
                break
            picked.append(i)

    return sorted(set(picked))


def _terminal_lock(n: int) -> set[int]:
    locked: set[int] = set()
    if n <= 0:
        return locked
    locked.add(n - 1)
    if n > 15:
        locked.add(n - 2)
    return locked


def rank_chunks(
    chunks: list[str],
    *,
    k: int | None = None,
    mmr_lambda: float = _MMR_LAMBDA,
) -> dict[str, Any]:
    """Rank and select chunk indices for Approach B continuator."""
    n = len(chunks)
    if n == 0:
        return {
            "selected_indices": [],
            "k": 0,
            "total_chunks": 0,
            "selection_strategy": _STRATEGY,
        }

    budget = k if k is not None else default_k(n)
    budget = min(budget, n)

    if n <= budget:
        return {
            "selected_indices": list(range(n)),
            "k": n,
            "total_chunks": n,
            "selection_strategy": "full",
            "locked_indices": list(range(n)),
        }

    embeddings = _embed_chunks(chunks)
    delta = _displacement_series(embeddings)
    kappa = _curvature_series(delta)
    z_delta = _robust_zscore(delta)
    z_kappa = _robust_zscore(kappa)

    cluster_k = min(budget, n)
    labels = _cluster_labels(embeddings, cluster_k)
    cluster_audit = select_chunks_cluster_head_tail(chunks, max_chunks=budget)

    penalty = _PELT_PENALTY_SCALE * float(np.log(max(n, 2)))
    pelt_cps = _pelt_changepoints(delta, penalty=penalty)
    peak_delta = _local_maxima_indices(delta, z=z_delta, threshold=_PEAK_Z_THRESHOLD)
    peak_kappa = _local_maxima_indices(kappa, z=z_kappa, threshold=_PEAK_Z_THRESHOLD)
    cp_boundaries = _changepoint_boundary_indices(pelt_cps, n)
    cluster_bounds = _cluster_boundary_indices(labels)

    boundary_set = set(cp_boundaries) | set(peak_delta) | set(peak_kappa) | set(cluster_bounds)

    # Cluster representatives as additional candidates.
    for cluster in cluster_audit.get("clusters") or []:
        for idx in cluster.get("representatives") or []:
            boundary_set.add(int(idx))

    locked = _terminal_lock(n)
    candidate_set = set(boundary_set) | locked
    candidate_set = {i for i in candidate_set if 0 <= i < n}

    mass = _cluster_mass(labels, cluster_k)
    scores = _base_scores(n, delta=delta, mass=mass, boundary_set=boundary_set)

    candidates = sorted(candidate_set)
    if not candidates:
        candidates = list(range(n))

    selected = _mmr_select(
        candidates, scores, embeddings, k=budget, locked=locked, mmr_lambda=mmr_lambda
    )

    return {
        "selected_indices": selected,
        "k": budget,
        "total_chunks": n,
        "selection_strategy": _STRATEGY,
        "locked_indices": sorted(locked),
        "displacement": [round(float(x), 6) for x in delta],
        "curvature": [round(float(x), 6) for x in kappa],
        "changepoints_pelt": pelt_cps,
        "peak_displacement": peak_delta,
        "peak_curvature": peak_kappa,
        "cluster_boundaries": cluster_bounds,
        "boundary_candidates": sorted(boundary_set),
        "candidate_scores": {int(i): round(float(scores[i]), 6) for i in candidates},
        "cluster_audit": {
            "cluster_count": cluster_audit.get("cluster_count"),
            "cluster_sizes": cluster_audit.get("cluster_sizes"),
        },
    }


__all__ = ["default_k", "rank_chunks"]
