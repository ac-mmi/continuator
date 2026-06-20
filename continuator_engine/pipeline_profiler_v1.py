"""Optional stage timing for the production Conversation Intelligence pipeline."""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


def pipeline_profile_enabled() -> bool:
    return str(os.getenv("MEMORY_PIPELINE_PROFILE", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@dataclass
class ClusterProfile:
    cluster_id: int
    cluster_size: int
    representative_chars: int
    representative_tokens: int = 0
    representative_strategy: str = ""
    representative_ms: float = 0.0
    extraction_total_ms: float = 0.0
    lora_generation_ms: float = 0.0
    parse_ms: float = 0.0
    repair_ms: float = 0.0
    dedupe_ms: float = 0.0
    validation_ms: float = 0.0
    output_facts: int = 0
    facts_before_dedupe: int = 0
    facts_removed_dedupe: int = 0
    output_questions: int = 0
    output_goals: int = 0
    output_decisions: int = 0
    output_tokens: int = 0
    prompt_tokens: int = 0
    repair_used: bool = False
    extract_error: str = ""


@dataclass
class PipelineProfileRun:
    run_started_at: float = 0.0
    stages_ms: dict[str, float] = field(default_factory=dict)
    clusters: list[ClusterProfile] = field(default_factory=list)
    _active_cluster: ClusterProfile | None = field(default=None, repr=False)

    def begin(self) -> None:
        self.run_started_at = time.perf_counter()
        self.stages_ms = {}
        self.clusters = []
        self._active_cluster = None

    def add_stage(self, name: str, duration_ms: float) -> None:
        self.stages_ms[name] = round(self.stages_ms.get(name, 0.0) + duration_ms, 3)

    def begin_cluster(self, cluster: ClusterProfile) -> None:
        self._active_cluster = cluster
        self.clusters.append(cluster)

    def active_cluster(self) -> ClusterProfile | None:
        return self._active_cluster

    def total_ms(self) -> float:
        return round(sum(self.stages_ms.values()), 3)

    def to_dict(self) -> dict[str, Any]:
        total = self.total_ms()
        pct = {
            k: round(100.0 * v / total, 2) if total > 0 else 0.0
            for k, v in sorted(self.stages_ms.items(), key=lambda kv: -kv[1])
        }
        return {
            "total_ms": total,
            "total_sec": round(total / 1000.0, 3),
            "stages_ms": dict(self.stages_ms),
            "stages_pct": pct,
            "clusters": [
                {
                    "cluster_id": c.cluster_id,
                    "cluster_size": c.cluster_size,
                    "representative_chars": c.representative_chars,
                    "representative_tokens": c.representative_tokens,
                    "representative_strategy": c.representative_strategy,
                    "representative_ms": c.representative_ms,
                    "extraction_total_ms": c.extraction_total_ms,
                    "lora_generation_ms": c.lora_generation_ms,
                    "parse_ms": c.parse_ms,
                    "repair_ms": c.repair_ms,
                    "dedupe_ms": c.dedupe_ms,
                    "validation_ms": c.validation_ms,
                    "output_facts": c.output_facts,
                    "facts_before_dedupe": c.facts_before_dedupe,
                    "facts_removed_dedupe": c.facts_removed_dedupe,
                    "output_questions": c.output_questions,
                    "output_goals": c.output_goals,
                    "output_decisions": c.output_decisions,
                    "output_tokens": c.output_tokens,
                    "prompt_tokens": c.prompt_tokens,
                    "repair_used": c.repair_used,
                    "extract_error": c.extract_error,
                }
                for c in self.clusters
            ],
        }


_RUN = PipelineProfileRun()


def reset_pipeline_profile() -> None:
    _RUN.begin()


def get_pipeline_profile() -> PipelineProfileRun:
    return _RUN


@contextmanager
def profile_stage(name: str) -> Iterator[None]:
    if not pipeline_profile_enabled():
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _RUN.add_stage(name, (time.perf_counter() - t0) * 1000.0)
