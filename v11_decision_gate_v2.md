# V11 Decision Gate v2

**Status:** Plan only — retrain decision framework  
**Principle:** Do not retrain because we can. Retrain only when validation identifies a **specific, prevalent, addressable failure pattern**.  
**Out of scope:** V11 training plan, dataset design, implementation

---

## Purpose

V10 is the conversation state extractor. Phase 2 added checkpoint I/O, merge, and resume — **no LoRA changes**.

Before any V11 work, this gate defines:

1. What evidence validation must collect
2. What failure rates justify retraining
3. What failures do **not** justify retraining
4. What must be true to approve a V11 training cycle

---

## Default decision

```
┌────────────────────────────────────────────┐
│  DEFAULT: STAY ON V10                      │
│  Ship product validation + positioning     │
│  No retrain until gate conditions met      │
└────────────────────────────────────────────┘
```

Retraining is the **exception**, not the milestone after Phase 2.

---

## Inputs required before any V11 discussion

| Input | Source | Minimum |
|-------|--------|---------|
| Scored corpus | `real_world_validation_corpus.md` | 25 sessions, 15 gold/silver |
| Quality scores | `checkpoint_quality_score.md` | 100% gold scored |
| Resume results | `resume_validation_runner.md` | 100% HIGH archetype tested |
| Failure tags | Resume + quality worksheets | Per-session `F-*` codes |
| User sessions | `validation_plan_v2.md` Phase V2 | ≥ 8 moderated |

**No V11 review** until inputs complete — engineering capacity does not lower the bar.

---

## Gate metrics and thresholds

### Tier 1 — Automatic STAY ON V10 (no review needed)

If **any** of these hold after full corpus validation:

| Condition | Threshold | Rationale |
|-----------|-----------|-----------|
| Overall median quality | ≥ 3.5 / 5 | Product viable on V10 |
| Coding + tutorial median | ≥ 4.0 / 5 | Core wedge healthy |
| Resume pass rate (HIGH archetype) | ≥ 80% | Core promise holds |
| Negative controls score low | median ≤ 2.5 | Genre gating works — not extractor bug |
| No failure pattern | < 15% prevalence for any single `F-*` code | Failures are scattered noise |

**Action:** Document known limitations; improve product/positioning/UX — not LoRA.

---

### Tier 2 — V11 REVIEW (investigate, do not train yet)

Trigger **formal V11 review meeting** if **any**:

| Metric | Threshold | Implies |
|--------|-----------|---------|
| `next_action` failure rate (`F-NA`) | **> 25%** of gold/silver corpus | Systematic next-action extraction weakness |
| Objective accuracy median (M1) | **< 3.5** in coding+tutorial | Goal extraction misaligned |
| Current state accuracy median (M2) | **< 3.5** in coding+tutorial | Frontier position unreliable |
| Resume pass rate (HIGH archetype) | **< 70%** | State not portable — core promise at risk |
| Resume usefulness median (M6) | **< 3.5** | Checkpoint artifact insufficient |
| Duplication prevalence (`F-DUP`) | **> 30%** of sessions | Aggregation/schema tension |
| Stale terminal prevalence (`F-STALE`) | **> 20%** of tutorial corpus | Chunk frontier anchoring bug |
| Incremental parity | quality_ratio **< 95%** on real corpus | Merge policy or reuse bug — **fix merge first**, not LoRA |

**Action:** Root-cause analysis. Split failures into:
- **Engine bugs** (merge, render, validation) → fix without retrain
- **Genre mismatch** (Q&A in corpus) → positioning, not retrain
- **Extractor pattern** (consistent V10 wrong field) → candidate for V11

---

### Tier 3 — V11 TRAIN (approved exception)

Retrain **only if all** of the following:

| # | Condition |
|---|-----------|
| 1 | Tier 2 triggered AND root-cause attributes failure to **V10 extraction**, not merge/render/genre |
| 2 | One **primary failure pattern** documented with prevalence **≥ 25%** in target archetypes |
| 3 | Pattern is **addressable by training data** (not pure post-processing — e.g. duplication may be aggregation fix) |
| 4 | Proposed V11 scope is **narrow** — one pattern per training cycle |
| 5 | Success metric for V11 defined **before** training — same rubric, +X improvement on target pattern |
| 6 | V10 regression suite passes — no benchmark degradation on Aman, Kafka, pm |
| 7 | Product validation blocked on this pattern — users cite it unprompted |

**If any condition fails → STAY ON V10 or fix engine.**

---

## Failure pattern → train / don't train

| Pattern | Code | Train V11? | Alternative |
|---------|------|:----------:|-------------|
| Question as next_action | `F-NA` | **Maybe** — if > 25% in coding/tutorial | Frontier export rules; archetype warnings |
| Observer voice in fields | `F-OBS` | **Maybe** — if > 25% | Post-process voice cleaner (existing) |
| completed ≡ active duplication | `F-DUP` | **No** — aggregation | `filter_superseded_actives`, merge policy |
| Stale quiz / old terminal | `F-STALE` | **Maybe** — if > 20% tutorials | Ranker terminal lock; frontier band tuning |
| Medical/Q&A wrong semantics | `F-GENRE` | **No** | Do not market; optional genre detector |
| Missing blocker | `F-MISS` | **Maybe** — if > 20% debugging | Chunk selection; ranker |
| Resume asks for transcript | `F-ASK` | **No** — product/cache | Ensure cached_exports; user education |
| Hallucination on resume | `F-HALL` | **No** — LLM behavior | Briefing format; not extractor |
| Incremental quality drop | — | **No** — merge | `build_checkpoint_state` rebuild path |

---

## Example gate scenarios

### Scenario A — Stay on V10 ✅

```
Corpus: 30 sessions
Coding+tutorial median quality: 4.1
Resume pass rate: 85%
F-NA prevalence: 12%
F-GENRE on negatives: 100% fail as expected
```

**Decision:** STAY ON V10. Ship positioning for Cursor/coding users. Defer V11 indefinitely.

---

### Scenario B — Review, fix engine first ⚠️

```
Resume pass rate: 65%
Incremental quality_ratio: 88% on real appends
F-DUP prevalence: 35%
```

**Decision:** Fix merge/aggregation (`checkpoint_merge_v1`, `build_checkpoint_state`). Re-run validation. **Do not train V11** until merge fixed and resume still < 70%.

---

### Scenario C — Approve V11 training 🚨

```
Corpus: 35 gold/silver
F-NA prevalence: 32% in coding+tutorial (questions as next_action)
F-OBS: 8%
Resume pass: 72% (borderline)
Root cause: V10 tail-anchors last user message across 80% of F-NA cases
Merge fixes: attempted, no change
User sessions: 4/8 cite "next step was wrong"
```

**Decision:** Approve **narrow V11** — training objective: imperative next_action in coding/tutorial genres. Target: F-NA < 15%, resume pass ≥ 80%. Single pattern only.

---

## Metrics mapped to user-facing failures

| User complaint | Gate metric | Train threshold |
|----------------|-------------|-----------------|
| "Next step was wrong" | M5, `F-NA` | M5 median < 3.5 OR F-NA > 25% |
| "It doesn't know where I left off" | M2, continuity | M2 < 3.5 OR continuity fail > 30% |
| "It repeated stuff I already did" | M3, `F-DUP`, continuity | F-DUP > 30% (fix aggregation first) |
| "Wrong goal" | M1 | M1 < 3.5 in target genres |
| "Couldn't continue without chat" | M6, `F-ASK` | M6 < 3.5 OR pass < 70% (cache/product first) |
| "Worked great for coding, bad for health questions" | negative controls | **No train** — positioning |

---

## What V11 is **not** for

| Request | Response |
|---------|----------|
| "Make checkpoints universal for all chat" | No — genre gating is product strategy |
| "Beat GPT-4 summarization" | No — different product |
| "Add Cursor integration" | No — Phase 3 engineering |
| "Improve benchmark mock scores" | No — measure real corpus |
| "We have GPU time" | No — not a gate condition |
| "Competitor shipped fine-tune" | No — evidence-based only |

---

## V11 approval checklist (when Tier 3 reached)

- [ ] Validation corpus complete (25–50 sessions)
- [ ] Failure pattern named and prevalence documented
- [ ] Engine/merge ruled out as root cause
- [ ] Narrow training objective written (one pattern)
- [ ] V11 success metric: specific rubric improvement (+Δ on M5 or F-NA rate)
- [ ] V10 regression baseline frozen (benchmark cache JSONL)
- [ ] Dataset plan addresses pattern only — not full rehash
- [ ] Rollback plan: ship V10 if V11 regresses
- [ ] Product owner sign-off — not engineering-only decision

---

## Timeline interaction

```
Phase 2 complete (engine)
        ↓
Product validation (this gate's inputs)
        ↓
   ┌────┴────┐
   │         │
STAY V10   V11 review
   │         │
   │    Engine fix?
   │         │
   │    V11 train (exception)
   ↓
Phase 3 extensions (only after validation pass on V10)
```

**Extensions do not proceed on V11 hopes.** Validate V10 product first.

---

## Reporting template

```markdown
## V11 Gate Report — <date>

### Corpus
- Sessions: N gold/silver
- Categories: ...

### Scores
- Overall median: X / 5
- Coding+tutorial median: X / 5
- Resume pass rate: X%

### Failure prevalence
| Code | Rate | Train candidate? |
|------|------|------------------|
| F-NA | X% | yes/no |

### Decision
[ ] STAY ON V10
[ ] REVIEW (Tier 2)
[ ] APPROVE V11 (Tier 3) — pattern: ___

### Rationale
...
```

---

## Related documents

- `validation_plan_v2.md` — validation phasing
- `checkpoint_quality_score.md` — M1–M6 definitions
- `resume_validation_runner.md` — F-* failure tags
- `checkpoint_archetype_analysis.md` — prior evidence V10 is genre-gated
- `platform_architecture.md` — V10 unchanged in platform plan
- `phase2_implementation_spec.md` — explicit non-goal: V10 changes
