"""Experimental cluster-based chunk selector (head/tail representatives + budget ranking)."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np

_SELECTION_STRATEGY = "cluster_head_tail"
_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _load_embedder() -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer("all-MiniLM-L6-v2")


def _embed_chunks(chunks: list[str]) -> np.ndarray:
    model = _load_embedder()
    vecs = model.encode(chunks, show_progress_bar=False, normalize_embeddings=True)
    return np.asarray(vecs, dtype=np.float64)


def _cluster_labels(embeddings: np.ndarray, k: int) -> np.ndarray:
    from sklearn.cluster import KMeans

    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    return km.fit_predict(embeddings)


def _centroid_index(members: list[int], embeddings: np.ndarray) -> int:
    arr = np.array(members, dtype=int)
    center = embeddings[arr].mean(axis=0)
    dists = np.linalg.norm(embeddings[arr] - center, axis=1)
    return int(arr[int(np.argmin(dists))])


def _cluster_members(labels: np.ndarray, cluster_count: int) -> list[list[int]]:
    return [sorted(int(i) for i in np.where(labels == cid)[0]) for cid in range(cluster_count)]


def _representative_indices(members: list[int]) -> list[int]:
    if not members:
        return []
    if len(members) == 1:
        return [members[0]]
    if len(members) == 2:
        return [max(members)]
    return [min(members), max(members)]


def _rank_candidates(
    candidates: dict[int, dict[str, Any]],
    *,
    max_chunks: int,
) -> list[int]:
    ranked = sorted(
        candidates.items(),
        key=lambda item: (item[1]["score"], item[0]),
        reverse=True,
    )
    return sorted(idx for idx, _ in ranked[:max_chunks])


def select_chunks_cluster_head_tail(
    chunks: list[str],
    *,
    max_chunks: int = 8,
) -> dict[str, Any]:
    """
    Select up to ``max_chunks`` chunk indices using semantic clustering.

    Returns diagnostics including ``selected_indices`` (source chunk indices).
    """
    n = len(chunks)
    if n == 0:
        return {
            "selected_indices": [],
            "cluster_count": 0,
            "cluster_sizes": [],
            "selection_strategy": _SELECTION_STRATEGY,
            "clusters": [],
            "candidate_scores": {},
        }

    if n <= max_chunks:
        return {
            "selected_indices": list(range(n)),
            "cluster_count": n,
            "cluster_sizes": [1] * n,
            "selection_strategy": "full",
            "clusters": [{"cluster_id": i, "members": [i], "representatives": [i]} for i in range(n)],
            "candidate_scores": {i: {"score": 1.0} for i in range(n)},
        }

    k = min(max_chunks, n)
    embeddings = _embed_chunks(chunks)
    labels = _cluster_labels(embeddings, k)
    memberships = _cluster_members(labels, k)
    sizes = [len(m) for m in memberships]
    max_size = max(sizes) if sizes else 1
    denom = max(n - 1, 1)

    clusters_meta: list[dict[str, Any]] = []
    candidates: dict[int, dict[str, Any]] = {}

    for cid, members in enumerate(memberships):
        if not members:
            continue
        earliest = min(members)
        latest = max(members)
        centroid = _centroid_index(members, embeddings)
        reps = _representative_indices(members)
        importance = len(members) / max_size

        clusters_meta.append(
            {
                "cluster_id": cid,
                "members": members,
                "size": len(members),
                "earliest": earliest,
                "latest": latest,
                "centroid": centroid,
                "representatives": reps,
            }
        )

        for idx in reps:
            recency = float(idx) / float(denom)
            score = 0.6 * recency + 0.4 * importance
            prev = candidates.get(idx)
            if prev is None or score > float(prev["score"]):
                candidates[idx] = {
                    "score": round(score, 6),
                    "recency_score": round(recency, 6),
                    "cluster_importance_score": round(importance, 6),
                    "cluster_id": cid,
                    "cluster_size": len(members),
                }

    selected = _rank_candidates(candidates, max_chunks=max_chunks)

    return {
        "selected_indices": selected,
        "cluster_count": k,
        "cluster_sizes": sizes,
        "selection_strategy": _SELECTION_STRATEGY,
        "clusters": clusters_meta,
        "candidate_scores": candidates,
        "max_chunks": max_chunks,
        "total_chunks": n,
    }


def select_cluster_chunks(
    chunks: list[str],
    *,
    max_chunks: int = 8,
) -> tuple[list[str], dict[str, Any]]:
    """Return (selected_chunk_texts, audit dict) for drop-in experiments."""
    audit = select_chunks_cluster_head_tail(chunks, max_chunks=max_chunks)
    indices = list(audit.get("selected_indices") or [])
    selected = [chunks[i] for i in indices]
    audit = {
        **audit,
        "selected_chunks_count": len(selected),
    }
    return selected, audit
