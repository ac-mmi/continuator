#!/usr/bin/env python3
"""Offline checkpoint archetype analysis — no extraction changes."""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "continuator_engine"
sys.path.insert(0, str(ENGINE))

from checkpoint_state_v1 import build_checkpoint_state  # noqa: E402

MEMORY = Path("/Users/acmmi/projects/memory")
CACHE = MEMORY / "training_pipeline/evaluation/continuator_benchmark_v1_cache.jsonl"
BENCHMARKS = MEMORY / "memory_brain/benchmarks"
TRAINING = MEMORY / "archive/training-data"
EXAMPLES = ROOT / "examples"

ARCHETYPES = (
    "tutorial",
    "coding",
    "project",
    "research",
    "journal",
    "customer_discovery",
    "medical",
    "casual_chat",
    "informational_QA",
    "other",
)

# Manual labels for cache + examples (grounded in eval docs)
LABELED: dict[str, str] = {
    "aman": "tutorial",
    "kafka": "tutorial",
    "kubernetes": "tutorial",
    "github": "project",
    "journal": "journal",
    "pm": "project",
    "superlong": "coding",
    "neck": "tutorial",
    "gitissue": "coding",
    "jquery": "coding",
    "chat": "medical",
    "my-project": "medical",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{4,}", _norm(s))}


def _overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def duplication_rate(state: dict[str, Any]) -> float:
    completed = state.get("completed_work") or []
    actives = state.get("active_problems") or []
    if not completed or not actives:
        return 0.0
    pairs = 0
    hits = 0
    for c in completed:
        for a in actives:
            pairs += 1
            if _overlap(str(c), str(a)) >= 0.45:
                hits += 1
    return hits / pairs if pairs else 0.0


def score_next_action(state: dict[str, Any]) -> tuple[int, list[str]]:
    na = str(state.get("next_action") or "").strip()
    issues: list[str] = []
    score = 0
    if not na:
        return 0, ["empty"]
    lower = na.lower()
    if na.endswith("?"):
        issues.append("question_not_action")
        score += 1
    else:
        score += 2
    action_verbs = ("continue", "implement", "fix", "address", "resolve", "pick up", "resume", "build", "add", "create")
    if any(v in lower for v in action_verbs):
        score += 2
    else:
        issues.append("weak_action_verb")
    if len(na.split()) < 6:
        issues.append("short")
    elif len(na.split()) <= 30:
        score += 1
    if "the slice" in lower or "the session covers" in lower or "the participant" in lower:
        issues.append("observer_voice")
        score -= 1
    if _overlap(na, str(state.get("current_state") or "")) > 0.7:
        issues.append("duplicates_position")
        score -= 1
    return max(0, min(5, score)), issues


def score_active_problems(state: dict[str, Any]) -> tuple[int, list[str]]:
    actives = state.get("active_problems") or []
    issues: list[str] = []
    if not actives:
        return 2, ["empty_ok_for_closed_threads"]
    score = 2
    for a in actives:
        al = str(a).lower()
        if al.startswith("the learner is") or al.startswith("the speaker is"):
            issues.append("observer_framing")
            score -= 1
        if "?" in al:
            issues.append("question_as_problem")
            score -= 1
    if len(actives) > 5:
        issues.append("noisy_list")
        score -= 1
    return max(0, min(5, score)), issues


def score_usefulness(state: dict[str, Any], *, na_s: int, ap_s: int, dup: float) -> tuple[int, str]:
    score = 0
    if state.get("objective"):
        score += 2
    if str(state.get("current_state") or "").strip():
        score += 2
    if state.get("completed_work"):
        score += 1
    if state.get("constraints"):
        score += 1
    score += min(2, na_s // 2)
    score += min(1, ap_s // 3)
    score -= int(dup * 3)
    if score >= 7:
        tier = "high"
    elif score >= 4:
        tier = "medium"
    else:
        tier = "low"
    return max(0, score), tier


def classify_path(path: Path) -> str:
    p = str(path).lower()
    name = path.stem.lower()
    if name in LABELED:
        return LABELED[name]
    if "/tutorial/" in p or "tutorial" in name:
        return "tutorial"
    if "/journal/" in p:
        return "journal"
    if "/research/" in p:
        return "research"
    if "/customer_discovery/" in p:
        return "customer_discovery"
    if "/troubleshooting/" in p or "debugging" in p or "troubleshoot" in name:
        return "coding"
    if "/planning/" in p or "startup" in name or "mvp" in name:
        return "project"
    if "/productivity/" in p or "career" in name or "interview" in name:
        return "journal"
    if "project_issues" in p or "github" in p or "discussion_" in name:
        return "coding"
    if "community_discussions" in p or "reddit" in p:
        return "casual_chat"
    if "replacements" in p or "rfc" in name or "enhancements" in name:
        return "project"
    if any(x in name for x in ("vitiligo", "hiv", "medical", "rash", "patient")):
        return "medical"
    if "neck" in name or "posture" in name:
        return "tutorial"
    return "other"


def classify_content(text: str) -> str | None:
    t = text[:8000].lower()
    if re.search(r"\b(learner|tutorial|lesson|module|exercise|chapter)\b", t):
        return "tutorial"
    if re.search(r"\b(github|issue|pr |pull request|bug|stack trace|docker|kubernetes|react flow|api)\b", t):
        return "coding"
    if re.search(r"\b(hypothesis|research|evidence|literature)\b", t):
        return "research"
    if re.search(r"\b(symptom|patient|diagnos|treatment|medicine|disease|hiv|rash)\b", t):
        return "medical"
    if re.search(r"\b(startup|roadmap|milestone|stakeholder|project manager)\b", t):
        return "project"
    return None


def final_archetype(path: Path, text: str = "") -> str:
    by_path = classify_path(path)
    by_content = classify_content(text) if text else None
    if by_path != "other":
        return by_path
    return by_content or "other"


def state_from_cache(entry: dict[str, Any]) -> dict[str, Any]:
    rows = entry.get("rows") or []
    v10_outputs = []
    for row in rows:
        out = dict(row.get("output") or {})
        out["chunk_index"] = int(row.get("chunk_index", 0))
        v10_outputs.append(out)
    label = str(entry.get("id") or "")
    archetype_map = {
        "kafka": "tutorial",
        "aman": "tutorial",
        "github": "github",
        "journal": "journal",
        "pm": "project_management",
        "superlong": "mixed",
    }
    return dict(
        build_checkpoint_state(
            v10_outputs,
            archetype=archetype_map.get(label, "mixed"),
            label=label,
            project=label,
            total_chunks=int(entry.get("chunk_count") or len(v10_outputs)),
        )
    )


def collect_training_files() -> list[Path]:
    out: list[Path] = []
    for sub in ("tutorial", "journal", "research", "customer_discovery", "workplace_collaboration", "mixed"):
        d = TRAINING / sub
        if d.is_dir():
            out.extend(sorted(d.rglob("*.txt")))
    return [p for p in out if "urls" not in p.name]


def collect_benchmark_files() -> list[Path]:
    if not BENCHMARKS.is_dir():
        return []
    files: list[Path] = []
    for p in sorted(BENCHMARKS.rglob("*.txt")):
        if p.name == "urls.txt":
            continue
        files.append(p)
    return files


def analyze_state(name: str, archetype: str, state: dict[str, Any]) -> dict[str, Any]:
    dup = duplication_rate(state)
    na_s, na_issues = score_next_action(state)
    ap_s, ap_issues = score_active_problems(state)
    use_s, use_tier = score_usefulness(state, na_s=na_s, ap_s=ap_s, dup=dup)
    return {
        "name": name,
        "archetype": archetype,
        "usefulness_score": use_s,
        "usefulness_tier": use_tier,
        "next_action_score": na_s,
        "next_action_issues": na_issues,
        "active_problems_score": ap_s,
        "active_problems_issues": ap_issues,
        "duplication_rate": round(dup, 3),
        "next_action": str(state.get("next_action") or "")[:120],
        "active_problems_count": len(state.get("active_problems") or []),
        "completed_work_count": len(state.get("completed_work") or []),
    }


def proxy_analyze_file(path: Path, text: str) -> dict[str, Any]:
    """Transcript-only proxy when V10 checkpoint not run (schema fit heuristic)."""
    archetype = final_archetype(path, text)
    t = text.lower()
    has_progression = bool(re.search(r"\b(done|completed|finished|next step|blocker|todo|implement)\b", t))
    is_qa = bool(re.search(r"\?\s*$", text[:3000], re.M)) or t.count("?") > 8
    is_multi_topic_qa = is_qa and not has_progression
    dup_proxy = 0.35 if is_multi_topic_qa else 0.1
    na_proxy = 2 if has_progression else (1 if is_qa else 2)
    ap_proxy = 3 if has_progression else 2
    use_s, use_tier = score_usefulness(
        {
            "objective": ["x"] if has_progression else (["x"] if not is_multi_topic_qa else []),
            "current_state": "x" if len(text) > 500 else "",
            "completed_work": ["x"] if has_progression else [],
            "constraints": [],
            "active_problems": ["x"] if has_progression else [],
            "next_action": "continue implementation" if has_progression else ("?" if is_qa else "continue"),
        },
        na_s=na_proxy,
        ap_s=ap_proxy,
        dup=dup_proxy,
    )
    if is_multi_topic_qa and archetype in ("medical", "informational_QA", "casual_chat"):
        use_tier = "low"
        use_s = min(use_s, 3)
    return {
        "name": path.stem,
        "archetype": archetype,
        "usefulness_score": use_s,
        "usefulness_tier": use_tier,
        "next_action_score": na_proxy,
        "next_action_issues": ["proxy"] if is_multi_topic_qa else [],
        "active_problems_score": ap_proxy,
        "active_problems_issues": ["proxy"] if is_multi_topic_qa else [],
        "duplication_rate": dup_proxy,
        "next_action": "(proxy)",
        "active_problems_count": -1,
        "completed_work_count": -1,
        "source": "proxy",
    }


def main() -> None:
    rows: list[dict[str, Any]] = []

    # Full V10 checkpoint from cache (6 conversations)
    if CACHE.is_file():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            label = str(entry.get("id") or "")
            arch = LABELED.get(label, "other")
            state = state_from_cache(entry)
            r = analyze_state(label, arch, state)
            r["source"] = "v10_cache"
            rows.append(r)

    # User validation artifact
    my_proj = ROOT / "checkpoints/my-project.yaml"
    if my_proj.is_file():
        data: dict[str, Any] = {"project": "my-project"}
        current_key = ""
        for line in my_proj.read_text(encoding="utf-8").splitlines():
            if line.startswith("project:"):
                data["project"] = line.split(":", 1)[1].strip().strip('"')
            elif line.endswith(":") and not line.startswith(" "):
                current_key = line[:-1].strip()
                data[current_key] = []
            elif line.strip().startswith("- ") and current_key:
                data.setdefault(current_key, []).append(line.strip()[2:].strip().strip('"'))
            elif ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1)
                data[k.strip()] = v.strip().strip('"')
        r = analyze_state("my-project", "medical", data)
        r["source"] = "user_checkpoint"
        rows.append(r)

    # Examples with proxy if no cache
    cached_names = {r["name"] for r in rows}
    for path in sorted(EXAMPLES.glob("*.txt")):
        if path.stem in cached_names:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        arch = final_archetype(path, text)
        if path.stem == "chat":
            # parse from user yaml already; skip duplicate proxy
            continue
        rows.append(proxy_analyze_file(path, text))
        rows[-1]["archetype"] = arch

    # Benchmark corpus — proxy classification + fit (39 files)
    for path in collect_benchmark_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        arch = final_archetype(path, text)
        r = proxy_analyze_file(path, text)
        r["name"] = path.name
        r["archetype"] = arch
        rows.append(r)

    # Training corpus — folder-ground-truth archetype (35 files), proxy metrics
    folder_map = {
        "tutorial": "tutorial",
        "journal": "journal",
        "research": "research",
        "customer_discovery": "customer_discovery",
        "workplace_collaboration": "project",
        "mixed": "other",
    }
    for path in collect_training_files():
        parts = path.parts
        folder = next((folder_map[k] for k in folder_map if k in parts), "other")
        text = path.read_text(encoding="utf-8", errors="replace")[:12000]
        r = proxy_analyze_file(path, text)
        r["name"] = path.name
        r["archetype"] = folder
        rows.append(r)

    # Dedupe by name keeping v10_cache
    seen: dict[str, dict] = {}
    for r in rows:
        key = r["name"]
        if key not in seen or r.get("source") == "v10_cache":
            seen[key] = r
    rows = list(seen.values())

    by_arch: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_arch[r["archetype"]].append(r)

    report = {
        "total": len(rows),
        "v10_measured": sum(1 for r in rows if r.get("source") == "v10_cache"),
        "by_archetype": {},
    }
    for arch in ARCHETYPES:
        items = by_arch.get(arch, [])
        if not items:
            continue
        report["by_archetype"][arch] = {
            "count": len(items),
            "avg_usefulness": round(sum(i["usefulness_score"] for i in items) / len(items), 2),
            "avg_next_action": round(sum(i["next_action_score"] for i in items) / len(items), 2),
            "avg_active_problems": round(sum(i["active_problems_score"] for i in items) / len(items), 2),
            "avg_duplication": round(sum(i["duplication_rate"] for i in items) / len(items), 3),
            "high_pct": round(100 * sum(1 for i in items if i["usefulness_tier"] == "high") / len(items), 1),
            "low_pct": round(100 * sum(1 for i in items if i["usefulness_tier"] == "low") / len(items), 1),
        }

    out = ROOT / "scripts/checkpoint_archetype_report.json"
    out.write_text(json.dumps({"summary": report, "rows": rows}, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {out} ({len(rows)} conversations)")


if __name__ == "__main__":
    main()
