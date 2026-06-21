# Checkpoint Quality Score

**Status:** Plan only — human + LLM-as-judge rubric  
**Scale:** 1–5 per metric  
**Out of scope:** Automated scorer implementation, model changes

---

## Purpose

Provide a **repeatable rubric** to score checkpoint quality during product validation. Used on every session in `real_world_validation_corpus.md`.

**A checkpoint is "good enough" for product validation when:**

- Median overall score ≥ **3.5 / 5** across corpus
- Median ≥ **4.0 / 5** for coding and tutorial categories
- No metric median below **3.0 / 5** in HIGH-value categories

---

## Scoring model

### Six metrics (each 1–5)

| # | Metric | What it measures |
|---|--------|------------------|
| 1 | **Objective accuracy** | Does `state.objective` reflect the real goal of the conversation? |
| 2 | **Current state accuracy** | Does `current_state` describe where the work actually stopped? |
| 3 | **Completed work accuracy** | Are `completed_work` items real milestones (not observer summaries or duplicates)? |
| 4 | **Active problem accuracy** | Are `active_problems` genuine blockers/open issues (not questions or paraphrases of completed work)? |
| 5 | **Next action usefulness** | Would a competent human follow `next_action` to make progress? |
| 6 | **Resume usefulness** | Could someone continue the thread in a fresh LLM using only the checkpoint (no transcript)? |

### Overall score

```
overall = mean(metric_1 .. metric_6)
```

Optional weights for product gate (coding/tutorial focus):

```
weighted = 0.15×M1 + 0.15×M2 + 0.15×M3 + 0.15×M4 + 0.20×M5 + 0.20×M6
```

Use **unweighted mean** for reporting unless category-specific weights are defined.

---

## Scale anchors (all metrics)

| Score | Label | Meaning |
|:-----:|-------|---------|
| **5** | Excellent | Accurate, complete, actionable; no material errors |
| **4** | Good | Minor omissions or phrasing issues; still trustworthy |
| **3** | Acceptable | Usable with mild reviewer correction; some noise |
| **2** | Poor | Misleading or incomplete; reviewer would heavily edit before use |
| **1** | Fail | Wrong, empty, or harmful; would not use for resume |

---

## Metric rubrics

### 1. Objective accuracy

| Score | Criteria |
|:-----:|----------|
| 5 | Captures primary goal and major sub-goals; matches transcript intent |
| 4 | Primary goal correct; minor sub-goals missing |
| 3 | Goal directionally right but vague or partially wrong |
| 2 | Generic observer summary ("discussing X") not a goal |
| 1 | Wrong goal, empty, or unrelated |

**Automatic downgrade flags:**
- Objective is a question
- Objective duplicates `current_state` verbatim

---

### 2. Current state accuracy

| Score | Criteria |
|:-----:|----------|
| 5 | Precise stopping point — what was being done when session ended |
| 4 | Correct area; missing one specific detail |
| 3 | High-level correct but could apply to multiple points in thread |
| 2 | Session summary / "they discussed…" observer voice |
| 1 | Wrong position or empty |

**Automatic downgrade flags:**
- Phrases: "The discussion is focused", "The participant", "The slice"

---

### 3. Completed work accuracy

| Score | Criteria |
|:-----:|----------|
| 5 | Real milestones in sensible order; no filler |
| 4 | Mostly correct; 1 minor item questionable |
| 3 | Mix of milestones and vague summaries |
| 2 | Mostly observer narration of what was said |
| 1 | Wrong, empty when work exists, or largely duplicated in active_problems |

**Duplication check:** If any `completed_work` × `active_problems` pair has ≥ 45% token overlap, cap metric 3 at **2** unless reviewer overrides with note.

---

### 4. Active problem accuracy

| Score | Criteria |
|:-----:|----------|
| 5 | Real blockers / open issues a practitioner would recognize |
| 4 | Mostly blockers; one item is weak |
| 3 | Mix of blockers and narrative |
| 2 | Questions or tail-anchored user queries listed as problems |
| 1 | Empty when blockers exist, or duplicates completed_work |

**Automatic downgrade flags:**
- Item is a user question ("speaker is asking about…")
- Item is medical/legal informational query with no project arc

---

### 5. Next action usefulness

| Score | Criteria |
|:-----:|----------|
| 5 | Specific imperative next step; advances work; not already done |
| 4 | Clear direction; slightly vague on implementation |
| 3 | Reasonable but generic ("continue implementation") |
| 2 | Question, confirmation prompt, or repeats current_state |
| 1 | Wrong, empty, or unrelated tail sentence |

**Reference:** Gold-standard failures — GitHub thread open question as next action (2/5); medical Q&A general advice (2/5); pm roadblocks imperative (5/5).

---

### 6. Resume usefulness (holistic)

| Score | Criteria |
|:-----:|----------|
| 5 | Fresh LLM would continue productively with no transcript |
| 4 | Minor context gap; one clarifying question acceptable |
| 3 | Partial continuity; reviewer would paste one extra paragraph |
| 2 | Misleading resume; wrong priority or missing critical blocker |
| 1 | Worse than no checkpoint; active harm |

**This metric is validated twice:**
1. Human reviewer scores from checkpoint YAML + optional cached briefing
2. `resume_validation_runner.md` blind LLM continuation test (must correlate)

If human ≥ 4 but LLM runner fails → flag for investigation (format vs content).

---

## Scoring worksheet (per session)

```yaml
session_id: G04-aman
reviewer: <name>
reviewed_at: 2026-06-21T12:00:00Z
transcript_available: true  # reviewer may read; resume test does not

scores:
  objective_accuracy: 4
  current_state_accuracy: 4
  completed_work_accuracy: 5
  active_problem_accuracy: 3
  next_action_usefulness: 3
  resume_usefulness: 4

overall: 3.83  # mean

flags:
  - stale_terminal_quiz_risk
  - duplication_rate: 0.05

notes: >
  Next action anchors on quiz from chunk 2; v2 frontier improved vs v1
  but still not ideal for handoff.

verdict: pass | marginal | fail
```

### Verdict rules

| Verdict | Condition |
|---------|-----------|
| **pass** | overall ≥ 3.5 AND no metric ≤ 2 |
| **marginal** | overall ≥ 3.0 OR exactly one metric at 2 |
| **fail** | overall < 3.0 OR any metric = 1 OR two+ metrics at 2 |

---

## LLM-as-judge protocol (optional, consistent)

When human reviewers are scarce, a **second opinion** LLM may score using this rubric. Rules:

1. Provide **transcript excerpt** (frontier band + last 20% only) — not full checkpoint pipeline internals
2. Provide **checkpoint `state` block only** — not cached briefing (tests state accuracy)
3. LLM outputs JSON with six scores + one-sentence justification per metric
4. Human adjudicates when LLM-human delta ≥ 2 on any metric

**Do not** use LLM-as-judge as sole scorer for product gate — human must review ≥ 50% of gold/silver corpus.

---

## Category-specific expectations

| Category | Highest-weight metrics | Common failure modes |
|----------|------------------------|----------------------|
| Coding | M4, M5, M6 | Generic next action; missing error signature |
| Tutorials | M1, M2, M5 | Stale quiz; wrong lesson position |
| Research | M1, M3, M4 | Open questions in wrong field |
| Project planning | M3, M4 | completed/active duplication |
| Debugging | M4, M5 | Re-suggesting ruled-out fixes in resume |
| Architecture | M3, M4 | Re-opening settled decisions |
| Negative (Q&A) | M5, M6 | Should score LOW — confirms rubric |

---

## Aggregation for validation gate

Report per category:

```
median(metric_i), p25, p75
pass_rate (verdict == pass)
fail_pattern_counts (from flags)
```

**Product validation pass** when coding + tutorials each have:

- `median(overall) ≥ 4.0`
- `pass_rate ≥ 70%`
- `median(resume_usefulness) ≥ 4.0`

---

## Relationship to automated rubrics

| Existing | Role in validation |
|----------|-------------------|
| `briefing_quality()` in `pipeline.py` | CI smoke — section presence, word count |
| `checkpoint_archetype_analysis` usefulness 0–10 | Historical proxy — map to this rubric for comparison |
| Phase 2 benchmark quality_ratio | Incremental parity only — not substitute for human rubric |

---

## Related documents

- `real_world_validation_corpus.md` — what to score
- `resume_validation_runner.md` — independent resume test
- `v11_decision_gate_v2.md` — when failures trigger retrain review
- `checkpoint_archetype_analysis.md` — prior metric definitions
