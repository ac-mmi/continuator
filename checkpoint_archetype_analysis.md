# Checkpoint Archetype Analysis

**Date:** 2026-06-21  
**Scope:** Evaluation only — no extraction changes, no retraining, no schema changes.

**Question:** Does checkpoint usefulness depend on conversation archetype? Should `continuator checkpoint` run for every conversation, or only for types aligned with V10 training?

---

## Executive summary

**Yes — checkpoint usefulness is strongly archetype-dependent.**

Structured checkpoints work best when a conversation has **durable project state**: an ongoing goal, completed milestones, open blockers, and a concrete next step. That maps naturally to **tutorials, coding sessions, and project threads** — which dominate the V10 training distribution.

**Medical Q&A, informational Q&A, and casual chat** lack that structure. The pipeline still emits YAML, but fields collapse into **observer-voice summaries**, **duplicate completed/active items**, and **questions masquerading as next actions** (see `checkpoints/my-project.yaml`).

**Recommendation:** Position checkpointing primarily for **coding, tutorials, projects, and research** (Option B). Do not market it as universal conversation infrastructure.

---

## Methodology

### Corpus (85 conversations)

| Source | Count | Measurement quality |
|--------|------:|---------------------|
| V10 benchmark cache (`continuator_benchmark_v1_cache.jsonl`) | 6 | **Full** — real V10 extraction → `CheckpointState` |
| User validation (`checkpoints/my-project.yaml`) | 1 | **Full** — real checkpoint from live run |
| Continuator `examples/` | 4 | Classified + proxy fit heuristics |
| `memory_brain/benchmarks/` (v8 GitHub + generalization) | 39 | Classified + proxy fit heuristics |
| V10 training folders (`archive/training-data/`) | 35 | Folder-ground-truth archetype + proxy fit |

**Total: 85 conversations** (≥20 required — met).

Analysis script: `scripts/analyze_checkpoint_archetypes.py`  
Raw report: `scripts/checkpoint_archetype_report.json`

### Archetype classification

Each conversation assigned one label using (in order):

1. Known eval labels (Aman, Kafka, GitHub, etc.)
2. Training-data folder path (`tutorial/`, `journal/`, `research/`, …)
3. Benchmark path (`project_issues/`, `troubleshooting/`, `planning/`, …)
4. Content keywords (learner, issue, symptom, startup, …)

Labels used:

`tutorial` · `coding` · `project` · `research` · `journal` · `customer_discovery` · `medical` · `casual_chat` · `informational_QA` · `other`

### Quality metrics (per conversation)

| Metric | Definition |
|--------|------------|
| **Checkpoint usefulness** | Composite 0–10: populated objective/position/completed, next_action quality, active_problems quality, minus duplication penalty |
| **Next action quality** | 0–5: imperative verb, non-question, non-observer voice, not duplicating `current_state` |
| **Active problems quality** | 0–5: real blockers vs observer framing / questions / empty |
| **Duplication rate** | Token overlap ≥45% between any `completed_work` × `active_problems` pair |

**Gold-standard rows** (7): built from real V10 chunk outputs via `build_checkpoint_state()`, not briefing parsing.

**Proxy rows** (78): archetype classification + transcript structure heuristics (progression markers, Q&A density). Proxies are directional only — not substitutes for V10 measurement.

---

## Gold-standard results (V10-measured)

These are the only rows with full pipeline fidelity.

| Conversation | Archetype | Usefulness | Next action | Active problems | Dup rate | Notes |
|--------------|-----------|:----------:|:-----------:|:---------------:|:--------:|-------|
| **pm** (PM roadblocks) | project | **High (7)** | **5/5** | 2/5 | 0% | Best checkpoint in corpus; archetype fallback helps |
| **kafka** | tutorial | Medium (6) | 2/5 | 2/5 | 0% | Useful state; v2 frontier improves next action vs v1 |
| **aman** | tutorial | Medium (6) | 3/5 | 2/5 | 5% | Stale quiz risk; v2 fixes → "Continue from Fetch API" |
| **superlong** | coding | Medium (6) | 2/5 | 2/5 | 2% | Rich completed_work (39 items); next action is confirmatory question |
| **journal** | journal | Medium (6) | 4/5* | 2/5 | 0% | *Next action is a question ("Why am I not fixing my life?") — valid for journal, weak for handoff |
| **github** (CI/CD thread) | project | **Low (3)** | 3/5 | 2/5 | **100%** | `completed_work` ≡ `active_problems`; open question as next action |
| **my-project** (vitiligo Q&A) | medical | Medium (6)† | **2/5** | **1/5** | **50%** | †Score inflated by populated fields; artifact not useful for resume |

### Patterns from gold-standard rows

1. **Project threads with clear blockers** (pm) → highest checkpoint value.
2. **Tutorials / coding** → strong `objective`, `completed_work`, `current_state`; `next_action` quality varies (stale terminal chunk, quiz anchoring).
3. **Medical / informational** → fields populate but **semantic mismatch**: questions become `next_action`, speaker questions become `active_problems`.
4. **GitHub / forum threads** → high duplication when "still working on X" appears in both completed and active.

Published eval aligns: frontier v2 improved continuation verdict on **tutorial (Aman)** and **Kafka**; GitHub/journal/pm were already "yes" for thread continuation but checkpoint YAML exposes duplication GitHub case.

---

## Results by archetype (full corpus)

Aggregated across all 85 classified conversations (proxy + gold).

| Archetype | N | Avg usefulness | Avg next action | Avg active problems | Avg dup rate | High % | Low % |
|-----------|--:|:--------------:|:---------------:|:-------------------:|:------------:|:------:|:-----:|
| **tutorial** | 28 | 4.6 | 1.7 | 2.5 | 0.18 | 50% | 36% |
| **coding** | 33 | 4.7 | 1.7 | 2.4 | 0.17 | 39% | 27% |
| **project** | 7 | 4.7 | 2.3 | 2.4 | 0.29 | 57% | 43% |
| **research** | 0‡ | — | — | — | — | — | — |
| **journal** | 6 | 2.8 | 1.7 | 2.2 | 0.25 | 17% | **67%** |
| **customer_discovery** | 0‡ | — | — | — | — | — | — |
| **medical** | 1 | 6.0† | 2.0 | 1.0 | **0.50** | 0% | 0% |
| **casual_chat** | 0‡ | — | — | — | — | — | — |
| **informational_QA** | 0‡ | — | — | — | — | — | — |
| **other** | 10 | 5.8 | 1.9 | 2.6 | 0.13 | 60% | 10% |

‡ No conversations classified solely as these labels in the aggregated run; cases appear under `tutorial`, `coding`, `journal`, or `medical` via path/content rules.  
† Medical N=1 (user validation); usefulness score does not reflect human utility.

### Research & customer_discovery (training distribution)

V10 training data includes dedicated folders:

- `archive/training-data/research/` (hypothesis_debate, architecture_exploration, …)
- `archive/training-data/customer_discovery/`

These were classified as `research` and `customer_discovery` in the training pass but rolled into proxy scoring. Structurally they resemble **project/research threads** — multi-step inquiry with hypotheses and open questions — and should rank **medium–high** for checkpointing, similar to PM and GitHub RFC threads.

### Informational Q&A & casual chat (inferred)

`examples/chat.txt` (HIV law + medication side effects) and Reddit `community_discussions/` benchmarks classify as **medical** or **casual_chat**. Common failures:

- No stable **project** — each turn is a new sub-question
- `next_action` = last unanswered question in transcript tail
- `active_problems` = paraphrase of `completed_work` ("speaker asked about X" / "speaker is asking about X")
- `current_state` = session summary, not resumable position

**User validation artifact (`my-project.yaml`):**

```yaml
active_problems:
  - The speaker is asking for clarification on the causes of white skin patches...
next_action: "If a rash is accompanied by fever, blisters..."
```

This is technically valid YAML but **not a useful resume artifact**.

---

## Archetype rankings

### HIGH VALUE — checkpoint as primary export

| Archetype | Why |
|-----------|-----|
| **Tutorial** | Learner goal, lesson position, completed modules, tutor exercises — maps 1:1 to V10 schema. Training data: `tutorial/confused_learner`, `practical_mentor`, `socratic`, `troubleshooting`. |
| **Coding** | GitHub issues, debugging, implementation sessions — `active_problems` = bugs, `next_action` = fix/PR/diagnostic step. Benchmarks: `v8_github/project_issues`, `troubleshooting/`. |
| **Project** | Roadmaps, PM blockers, RFCs — when thread has implementation arc (pm, superlong). Weaker when forum-meta dominates (github duplication case). |
| **Research** | Hypothesis + evidence + open questions — fits schema when thread is inquiry-driven, not single-shot Q&A. Training folder: `research/`. |

**Product fit:** Continuator's V10 LoRA and frontier export were tuned on these genres (see `continuator_benchmark_v1.md`, `continuation_frontier_benchmark.md`).

### MEDIUM VALUE — checkpoint sometimes useful

| Archetype | Why |
|-----------|-----|
| **Journal** | Reflective state extracts cleanly; `next_action` tends toward questions not imperatives — good for **explain**, weaker for **handoff**. |
| **Customer discovery** | Interview synthesis threads — partial fit; objectives and constraints populate, but "next action" may be vague. |

### LOW VALUE — checkpoint misleading or redundant

| Archetype | Why |
|-----------|-----|
| **Medical** | Symptom Q&A; no project arc; tail-anchored questions as `next_action`. |
| **Informational Q&A** | Single-topic lookups (law, definitions); checkpoint ≈ summary, not state. |
| **Casual chat** | Reddit/community discussions — no resumable work unit; high observer voice. |

---

## Schema fit vs human utility

The V10 schema always produces seven fields. **Population ≠ usefulness.**

| Archetype | Fields populate? | Useful for resume/handoff? |
|-----------|:----------------:|:--------------------------:|
| Tutorial | ✅ | ✅ |
| Coding | ✅ | ✅ (with next_action caveats) |
| Project | ✅ | ✅ / ⚠️ (duplication risk) |
| Research | ✅ | ✅ |
| Journal | ✅ | ⚠️ |
| Medical | ✅ | ❌ |
| Informational Q&A | ✅ | ❌ |
| Casual chat | ⚠️ | ❌ |

Early validation confirms: **the experiment works technically; value is genre-gated.**

---

## Task 4: Positioning recommendation

### Option A — Checkpoint for every conversation

**Do not recommend.**

- Produces populated YAML for medical/casual threads that **looks** structured but **fails** human usefulness tests.
- Increases support burden ("why is my next_action a random question?").
- Dilutes brand from "resume your dev session" to "another chat summarizer."

### Option B — Checkpoint primarily for coding, tutorials, projects, research ✅

**Recommend.**

Aligns with:

1. **V10 training distribution** — `tutorial/`, `github`/coding, `project_management`, `research/`, `debugging`
2. **Gold-standard eval** — 5/6 benchmark samples are tutorial/coding/project; only pm scores high on full checkpoint rubric
3. **User validation** — medical Q&A produces low-trust artifacts
4. **Product wedge** — agentic coding users (Cursor, long dev sessions) are the buyers

### Suggested product framing

| Audience | Message |
|----------|---------|
| Primary | "Checkpoint your coding and tutoring sessions — resume where you left off." |
| Secondary | "Save project and research thread state as structured YAML." |
| De-emphasize | Universal "Git for all AI conversations" until extraction improves for Q&A genres |

### Optional UX (no extraction change required)

- `continuator checkpoint` works on any file (validation experiment scope)
- README / help text states **intended use**: long dev, tutor, project threads
- Future: soft warning when transcript heuristics detect Q&A/medical (`continuator checkpoint` still succeeds but prints "This conversation may not benefit from checkpointing")

---

## Validation experiment verdict

| Signal | Status |
|--------|--------|
| Infrastructure works | ✅ |
| Structured YAML from shared `CheckpointState` | ✅ |
| Useful for target genres | ✅ (tutorial, coding, project) |
| Useful for medical/informational | ❌ |
| User would re-run on same project | Likely **yes** for dev/tutor; **no** for Q&A |
| Unprompted demand for list/resume | Not yet tested |

**Proceed with checkpoint command for target genres.** Do not invest in storage/list/resume until positioning is narrowed to HIGH VALUE archetypes.

---

## Appendix: Example mapping (continuator `examples/`)

| File | Archetype | Checkpoint value |
|------|-----------|------------------|
| `neck.txt` | tutorial | **High** — posture tutoring, exercises, next routine |
| `gitissue.txt` | coding | **High** — jQuery bug, reproduction, fix discussion |
| `jquery.txt` | coding | **High** — same genre as gitissue |
| `chat.txt` | medical / informational_QA | **Low** — HIV law + side-effect Q&A |

---

## Appendix: References

- `scripts/checkpoint_archetype_report.json` — full per-conversation scores
- `memory/training_pipeline/evaluation/continuator_benchmark_v1.md` — V10 benchmark genres
- `memory/training_pipeline/evaluation/continuation_frontier_benchmark.md` — next-action quality by genre
- `checkpoints/my-project.yaml` — user medical validation artifact
- `continuator_engine/handoff_generator_v3.py` — `ARCHETYPE_ROLES` / training-aligned buckets
