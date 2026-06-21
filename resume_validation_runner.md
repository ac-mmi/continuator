# Resume Validation Runner

**Status:** Plan only — protocol design  
**Tests:** Resume usefulness without transcript (the core product promise)  
**Out of scope:** New CLI commands, automation scripts, extensions

---

## Purpose

Phase 2 shipped `continuator resume` — cached exports, no V10 on default path. Product validation must answer:

> If the user loses the original transcript, can they still continue productively from the checkpoint alone?

This document defines a **manual workflow** (runnable today with existing CLI) and what to measure.

---

## Core protocol (5 steps)

```
┌─────────────────────────────────────────────────────────────────┐
│  1. CHECKPOINT          continuator checkpoint session.txt       │
│  2. DELETE TRANSCRIPT   remove / isolate source file             │
│  3. RESUME (CLI)        continuator resume  → cached briefing      │
│  4. FRESH LLM           paste checkpoint/briefing only           │
│  5. CONTINUE PROMPT     ask LLM to continue the work             │
└─────────────────────────────────────────────────────────────────┘
```

The reviewer **never** gives the fresh LLM the original transcript.

---

## Step-by-step workflow

### Step 1 — Create checkpoint

```bash
continuator checkpoint session.txt --full -o .continuator/checkpoint.yaml
```

Record:

- `checkpoint.id`
- `source.sha256`, `source.char_count`
- `stats.runtime_seconds`
- Full `state` block (for scoring)

**Optional append test (incremental):**

```bash
# Grow session append-only, then:
continuator checkpoint session_grown.txt --update
```

Use grown session for Steps 2–5 separately to validate incremental record.

---

### Step 2 — Delete transcript

**Goal:** Simulate user who only has the checkpoint artifact.

Actions:

1. Move `session.txt` out of workspace (or rename to `.bak` inaccessible to reviewer)
2. Clear editor history / clipboard of transcript content
3. Confirm `source.path` in checkpoint points to missing file (realistic failure mode)

**Reviewer may retain a sealed copy** for grading only — not shared with Step 4 LLM.

---

### Step 3 — Resume from checkpoint only

```bash
continuator resume -q > briefing.txt
# or
continuator resume --format state -q > state.yaml
```

Verify:

- Resume latency < 500ms (cached path)
- No V10 load (optional: `MEMORY_EXTRACTOR_BACKEND=mock` should still return same briefing if `cached_exports` populated)

**Failure before Step 4:** If resume errors or briefing empty → score **resume usefulness = 1**, skip to notes.

---

### Step 4 — Give checkpoint to a fresh LLM

**Fresh LLM** = new chat session, different model acceptable, no system context about prior conversation.

**Input options (test both when possible):**

| Variant | Input to LLM | Tests |
|---------|--------------|-------|
| **A — Briefing** | Full `continuator resume` output (cached briefing) | Primary user path |
| **B — State only** | YAML `state` block serialized | State-as-SSOT path |
| **C — v2 JSON** | `checkpoint` envelope minus pipeline | SDK/future path |

**Recommended default:** Variant A (briefing) for product gate.

**Paste template:**

```markdown
You are continuing an interrupted work session. You have NO prior context except this checkpoint briefing.

<paste briefing.txt>

Do not ask me to provide the original conversation. Continue from where this left off.
```

---

### Step 5 — Continue prompt

Use a **fixed prompt** per category for comparability:

| Category | Continue prompt |
|----------|-----------------|
| Coding | "Continue the implementation. Propose the specific next code change and explain why." |
| Tutorials | "Continue as my tutor. What is the next lesson step and exercise?" |
| Research | "Continue the research thread. What is the next question or experiment?" |
| Project planning | "Continue as PM. What is the next action for the team?" |
| Debugging | "Continue debugging. What is the next diagnostic step?" |
| Architecture | "Continue the design discussion. What decision or spike is next?" |

**Do not** customize prompt per session except category.

---

## What to measure

### Primary dimensions (1–5 each)

| Dimension | Definition |
|-----------|------------|
| **Correctness** | Is the LLM's understanding factually aligned with sealed transcript ground truth? |
| **Continuity** | Does it pick up from the stopping point without restarting or repeating completed work? |
| **Usefulness** | Would a real user make progress with this response? |

### Secondary signals (boolean / counts)

| Signal | Pass condition |
|--------|----------------|
| Asks for original transcript | **Fail** — product promise broken |
| Repeats completed milestone as new work | **Fail** continuity |
| Proposes sensible next_action | **Pass** if matches or improves checkpoint `next_action` |
| Identifies same active blocker | **Pass** correctness |
| Hallucinates major context | **Fail** correctness |

### Resume usefulness mapping

Map to `checkpoint_quality_score.md` metric 6:

| Correctness | Continuity | Usefulness | Resume usefulness |
|:-----------:|:----------:|:----------:|:-----------------:|
| ≥ 4 | ≥ 4 | ≥ 4 | 5 |
| ≥ 3 | ≥ 3 | ≥ 3 | 3–4 |
| any ≤ 2 | any ≤ 2 | any ≤ 2 | 1–2 |

---

## Grading procedure

### Reviewer roles

| Role | Access | Task |
|------|--------|------|
| **Operator** | Runs CLI, pastes to LLM | Steps 1–5 |
| **Grader** | Sealed transcript | Scores correctness/continuity |
| **Subject** (optional) | Real user | Subjective usefulness only |

Grader and Operator should be different people when possible.

### Grading worksheet

```yaml
session_id: G07-pm
variant: briefing  # briefing | state | json
llm_model: claude-sonnet-4-20250514
run_at: 2026-06-21T15:00:00Z

scores:
  correctness: 5
  continuity: 4
  usefulness: 5
  resume_usefulness: 5

signals:
  asked_for_transcript: false
  repeated_completed_work: false
  matched_next_action: true
  hallucination: false

llm_response_excerpt: |
  <first 500 chars>

grader_notes: >
  Correctly identified blocker chain; proposed same next step as checkpoint.

verdict: pass | marginal | fail
```

### Pass / fail (per session)

| Verdict | Rule |
|---------|------|
| **pass** | correctness ≥ 4 AND continuity ≥ 4 AND usefulness ≥ 4 AND NOT asked_for_transcript |
| **marginal** | all ≥ 3, no critical hallucination |
| **fail** | any primary ≤ 2 OR asked_for_transcript OR critical hallucination |

---

## Corpus-level gates

| Gate | Threshold |
|------|-----------|
| HIGH archetype pass rate | ≥ **80%** (coding, tutorials, project) |
| MEDIUM archetype pass rate | ≥ **70%** (research, architecture) |
| Negative control fail rate | ≥ **60%** fail (medical, Q&A) |
| Variant A vs B delta | Briefing not worse than state-only by > 0.5 median |

---

## Incremental resume variant

For sessions with append-only growth:

1. Checkpoint base transcript → `R0`
2. Append growth → `continuator checkpoint grown.txt --update` → `R1`
3. Delete both transcripts
4. Resume from `R1` only
5. Fresh LLM continue

**Additional measure:** Does continuation reflect **new** content from append, not just base state?

---

## Model matrix (recommended)

Run **primary gate** on one strong model; spot-check on second.

| Priority | Model | Role |
|:--------:|-------|------|
| P0 | User's actual target (Claude/GPT) | Primary |
| P1 | Second family | Generalization check |
| P2 | Smaller/cheaper model | Robustness |

Do not block validation on model matrix completeness — minimum is **one** fresh LLM per gold session.

---

## Failure taxonomy (tag every fail)

| Code | Pattern | Example |
|------|---------|---------|
| `F-NA` | Bad next_action | Question as action |
| `F-DUP` | Duplication | completed ≡ active |
| `F-STALE` | Stale terminal | Old quiz as next step |
| `F-OBS` | Observer voice | "The speaker discussed…" |
| `F-MISS` | Missing blocker | Critical bug not in active_problems |
| `F-HALL` | Hallucination | LLM invents files/commits |
| `F-ASK` | Asks for transcript | Resume insufficient |
| `F-GENRE` | Wrong archetype | Medical Q&A in corpus |

Tag failures for `v11_decision_gate_v2.md` aggregation.

---

## Runnable today (no new tooling)

| Step | Command / action |
|------|------------------|
| Checkpoint | `continuator checkpoint FILE` |
| Resume | `continuator resume` |
| State export | `continuator resume --format state` |
| Refresh (control) | `continuator resume --refresh FILE` — **not** used in this protocol |
| Benchmark proxy | `continuator benchmark-incremental DIR` — speed/parity only |

Record results in spreadsheet or future `validation_results_v2.md`.

---

## Success definition

**Resume validation passes** when:

1. ≥ 80% of coding + tutorial corpus passes per-session verdict
2. Median resume usefulness ≥ 4.0 from `checkpoint_quality_score.md`
3. Negative controls fail at expected rate (genre gating confirmed)
4. Zero sessions where fresh LLM **requires** transcript after Variant A briefing

---

## Related documents

- `validation_plan_v2.md` — who and when
- `real_world_validation_corpus.md` — session selection
- `checkpoint_quality_score.md` — metric 6 alignment
- `v11_decision_gate_v2.md` — failure → retrain decision
- `phase2_implementation_spec.md` — resume < 500ms, no V10 on cached path
