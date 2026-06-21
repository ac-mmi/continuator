"""Product-facing continuation pipeline wrapper (unchanged extraction logic)."""
from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from continuator.runtime import ensure_runtime
from continuator.model_prep import prepare_extraction
from continuator.silence import shield_libraries

if TYPE_CHECKING:
    from continuator.console import ContinuatorConsole


def run_continuation(
    transcript: str,
    *,
    label: str = "",
    use_chunk_ranker: bool = True,
    console: ContinuatorConsole | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run the continuator pipeline with human-readable progress."""
    ensure_runtime()
    prepare_extraction(console, quiet=bool(console and console.quiet), verbose=verbose)
    from handoff_evaluation_v1 import iter_continuator_stream

    started = time.perf_counter()
    result: dict[str, Any] | None = None
    chunk_count = 0
    rank_logged = False

    if console and not console.quiet:
        console.on_reading()

    shield = console.library_shield() if console else shield_libraries(verbose=verbose)

    with shield:
        for line in iter_continuator_stream(
            transcript,
            label=label,
            archetype="mixed",
            use_chunk_ranker=use_chunk_ranker,
        ):
            event = json.loads(line)
            et = event.get("type", "")

            if et == "started":
                chunk_count = int(event.get("chunk_count") or 0)
                chars = int(event.get("transcript_chars") or len(transcript))
                if console:
                    console.on_parsed(chunk_count, chars)
            elif et == "ranked" and console and not rank_logged:
                rank_logged = True
                selected = [int(i) for i in event.get("selected_indices") or []]
                console.on_ranked(
                    selected=selected,
                    total=chunk_count,
                    strategy=str(event.get("selection_strategy") or "default"),
                )
            elif et == "progress":
                done = int(event.get("completed") or 0)
                total = int(event.get("total") or 0)
                if console:
                    console.on_analyze_progress(done, total)
            elif et == "building":
                if console:
                    console.on_building()
            elif et == "complete":
                result = dict(event.get("result") or {})
            elif et == "error":
                raise RuntimeError(str(event.get("message") or "continuation failed"))

    if result is None:
        raise RuntimeError("continuation ended without a result")

    elapsed = time.perf_counter() - started
    result["_runtime_seconds"] = round(elapsed, 2)
    if console:
        console.on_analysis_complete(seconds=elapsed)
    return result


def inspect_conversation(
    transcript: str,
    *,
    use_chunk_ranker: bool = True,
    verbose: bool = False,
) -> dict[str, Any]:
    """Chunk + rank audit without running extraction."""
    ensure_runtime()
    from continuation_export_v2_frontier import frontier_band_size, frontier_cutoff_index
    from memory_model_v1 import all_transcript_chunks

    started = time.perf_counter()
    with shield_libraries(verbose=verbose):
        chunks, chunk_meta = all_transcript_chunks(transcript)
        n = len(chunks)

        rank_audit: dict[str, Any] = {
            "selected_indices": list(range(n)),
            "k": n,
            "total_chunks": n,
            "selection_strategy": "full",
            "locked_indices": list(range(n)) if n else [],
        }
        if use_chunk_ranker and n > 0:
            from continuator_chunk_ranker_v1 import rank_chunks

            rank_audit = rank_chunks(chunks)

    cutoff = frontier_cutoff_index(n) if n else 0
    frontier_indices = list(range(cutoff, n)) if n else []
    selected = [int(i) for i in rank_audit.get("selected_indices") or []]
    frontier_selected = [i for i in selected if i >= cutoff]

    elapsed = time.perf_counter() - started
    return {
        "transcript_chars": len(transcript),
        "chunk_count": n,
        "chunking": chunk_meta,
        "rank_audit": rank_audit,
        "selected_indices": selected,
        "frontier_cutoff": cutoff,
        "frontier_band_size": frontier_band_size(n) if n else 0,
        "frontier_indices": frontier_indices,
        "frontier_selected": frontier_selected,
        "runtime_seconds": round(elapsed, 3),
    }


def pick_export(result: dict[str, Any], target: str) -> str:
    exports = dict(result.get("exports") or {})
    if target == "briefing":
        return str(result.get("continuation_briefing") or exports.get("continuation_briefing") or "").strip()
    if target == "explain":
        return str(result.get("conversation_explanation") or exports.get("explain") or "").strip()
    return str(exports.get(target) or "").strip()


def explain_quality(text: str) -> dict[str, Any]:
    """Lightweight rubric for explain-mode benchmark summaries."""
    t = (text or "").strip()
    lower = t.lower()
    score = 0
    issues: list[str] = []

    if not t:
        return {"verdict": "fail", "score": 0, "words": 0, "issues": ["empty"]}

    required = (
        "overview",
        "main topics",
        "current status",
        "key takeaways",
    )
    for section in required:
        if section in lower:
            score += 1
        else:
            issues.append(f"missing {section}")

    if "next action" in lower and "continue fetch" in lower:
        issues.append("continuation handoff bleed")
        score -= 1

    words = len(t.split())
    if words >= 80:
        score += 1
    elif words < 50:
        issues.append("short")

    bullet_lines = sum(1 for line in t.splitlines() if line.strip().startswith("- "))
    if bullet_lines >= 3:
        score += 1
    else:
        issues.append("sparse topics/learnings")

    if score >= 5 and "continuation handoff bleed" not in issues:
        verdict = "pass"
    elif score >= 3:
        verdict = "partial"
    else:
        verdict = "fail"

    return {"verdict": verdict, "score": score, "words": words, "issues": issues}


def briefing_quality(text: str) -> dict[str, Any]:
    """Lightweight rubric for benchmark summaries."""
    t = (text or "").strip()
    lower = t.lower()
    score = 0
    issues: list[str] = []

    if not t:
        return {"verdict": "fail", "score": 0, "words": 0, "issues": ["empty"]}

    if "next action" in lower:
        score += 2
    else:
        issues.append("missing next action")

    if "current position" in lower:
        score += 2
    else:
        issues.append("missing position")

    if "completed work" in lower:
        score += 1
    if "active problems" in lower:
        score += 1

    words = len(t.split())
    if words >= 80:
        score += 1
    elif words < 60:
        issues.append("short")

    if score >= 6 and "missing next action" not in issues:
        verdict = "pass"
    elif score >= 4:
        verdict = "partial"
    else:
        verdict = "fail"

    return {"verdict": verdict, "score": score, "words": words, "issues": issues}
