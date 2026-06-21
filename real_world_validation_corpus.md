# Real-World Validation Corpus

**Status:** Plan only — corpus design for product validation  
**Target size:** 25–50 real sessions  
**Out of scope:** Building collection tooling, extensions, V10/V11 changes

---

## Purpose

Phase 2 proved the **engine** works. This document designs the **corpus** needed to prove the **product** works on real conversations.

A session is in-corpus if:

1. It is a **real** conversation (not synthetic mock), or a **recorded benchmark** from the V10 eval cache with known ground truth
2. It is **labeled** by category and archetype
3. It is **scored** with `checkpoint_quality_score.md`
4. It is **resume-tested** per `resume_validation_runner.md` when archetype is HIGH or MEDIUM

---

## Corpus size and mix

| Tier | Count | Source |
|------|------:|--------|
| **Gold (V10-measured)** | 6–10 | `continuator_benchmark_v1_cache.jsonl`, `examples/`, prior eval artifacts |
| **Silver (real, newly collected)** | 15–25 | User exports, redacted team sessions, open-source dev threads |
| **Bronze (proxy / structural)** | 4–15 | `memory_brain/benchmarks/`, training-data samples — directional only |
| **Total** | **25–50** | |

**Minimum for validation gate:** 25 sessions with at least 15 **gold/silver** and ≥ 3 per HIGH-value category.

---

## Categories

### 1. Coding

**Description:** Implementation, debugging, PR review, library integration, test fixing.

**Example sources:**
- `examples/gitissue.txt`, `examples/jquery.txt`
- GitHub issue threads (jQuery, CI failures)
- Cursor/Claude Code exports (redacted)
- `v8_github/project_issues/`, `troubleshooting/` benchmarks

**Archetype fit:** HIGH

| Criterion | Definition |
|-----------|------------|
| **Success criteria** | Fresh LLM continues implementation without re-asking solved questions; proposes a sensible next code change |
| **Checkpoint usefulness** | `objective` reflects feature/bug; `completed_work` lists real progress; `active_problems` are blockers not summaries; `next_action` is imperative (fix, add test, run command) |
| **Resume usefulness** | Cached briefing alone sufficient to continue; reviewer rates continuity ≥ 4/5; no critical missing context from deleted transcript |

**Target n:** 8–12 sessions

---

### 2. Tutorials

**Description:** Learner + tutor threads; course modules; step-by-step skill building.

**Example sources:**
- `examples/neck.txt`
- Aman, Kafka benchmark samples
- `tutorial/confused_learner`, `practical_mentor` training folders

**Archetype fit:** HIGH

| Criterion | Definition |
|-----------|------------|
| **Success criteria** | Fresh LLM resumes at correct lesson position; does not repeat completed modules |
| **Checkpoint usefulness** | `objective` = learning goal; `current_state` = lesson position; `next_action` = next exercise or concept (not stale quiz from history) |
| **Resume usefulness** | Learner could hand briefing to new tutor and continue; stale-terminal risk flagged but acceptable if ≤ 20% of corpus |

**Target n:** 6–10 sessions

---

### 3. Research

**Description:** Multi-turn inquiry — hypothesis, evidence, comparisons, open questions.

**Example sources:**
- `archive/training-data/research/` (hypothesis_debate, architecture_exploration)
- Technical comparison threads (framework eval, paper discussion)
- Architecture option exploration (not yet committed to build)

**Archetype fit:** MEDIUM–HIGH

| Criterion | Definition |
|-----------|------------|
| **Success criteria** | Fresh LLM continues inquiry without resetting to "what are we researching?"; references prior conclusions |
| **Checkpoint usefulness** | `completed_work` = findings/decisions; `active_problems` = open questions (not rhetorical); `next_action` = next experiment or literature step |
| **Resume usefulness** | Briefing carries enough thread context; `constraints` capture methodology limits if present |

**Target n:** 4–6 sessions

---

### 4. Project planning

**Description:** Roadmaps, PM blockers, RFCs, sprint planning, cross-functional alignment.

**Example sources:**
- PM roadblocks benchmark (`pm`)
- `planning/` benchmark folders
- `customer_discovery/` threads (interview synthesis)

**Archetype fit:** HIGH (implementation arc) / MEDIUM (pure discovery)

| Criterion | Definition |
|-----------|------------|
| **Success criteria** | Fresh LLM understands project status and proposes aligned next step |
| **Checkpoint usefulness** | Low duplication between `completed_work` and `active_problems`; `constraints` capture scope/deadlines; `next_action` is actionable for team |
| **Resume usefulness** | New team member AI could onboard from checkpoint; duplication rate < 30% |

**Target n:** 4–6 sessions

---

### 5. Debugging

**Description:** Symptom → hypothesis → repro → fix loops; logs, stack traces, bisection.

**Example sources:**
- `troubleshooting/` benchmarks
- CI/CD failure threads (`github` sample — include as negative/edge case)
- Real stderr/log paste sessions (redacted)

**Archetype fit:** HIGH

| Criterion | Definition |
|-----------|------------|
| **Success criteria** | Fresh LLM does not re-suggest already-ruled-out fixes; next diagnostic step is logical |
| **Checkpoint usefulness** | `active_problems` = current hypothesis/blocker; `completed_work` = ruled-out causes and tried fixes; `next_action` = specific diagnostic command |
| **Resume usefulness** | Resume briefing preserves error signature and last known state |

**Target n:** 4–6 sessions

**Include edge cases:** At least 1 session known to produce duplication (e.g. GitHub forum-meta thread) to measure failure mode prevalence.

---

### 6. Architecture discussions

**Description:** System design, tradeoffs, ADR-style decisions without full implementation.

**Example sources:**
- `research/architecture_exploration` training samples
- API design threads
- "Should we use X or Y?" multi-turn debates

**Archetype fit:** MEDIUM–HIGH

| Criterion | Definition |
|-----------|------------|
| **Success criteria** | Fresh LLM recalls decided tradeoffs; does not re-open settled decisions without reason |
| **Checkpoint usefulness** | `completed_work` = decisions and rationale; `active_problems` = unresolved design questions; `constraints` = non-negotiables |
| **Resume usefulness** | Briefing sufficient to continue design review; `next_action` = review step, spike, or doc update |

**Target n:** 3–5 sessions

---

## Negative corpus (required controls)

Include **3–5 sessions** that should **fail** validation — to calibrate rubric and avoid false confidence.

| Category | Example | Expected outcome |
|----------|---------|------------------|
| Medical Q&A | `examples/chat.txt`, `checkpoints/my-project.yaml` | Low checkpoint + resume scores |
| Informational lookup | Law/definition single-topic thread | Fields populate, resume fails |
| Casual community | Reddit-style discussion | Observer voice, useless `next_action` |

Negative samples are **passing the validation** when they score LOW — confirms genre gating.

---

## Per-session metadata (required)

```yaml
session_id: <uuid>
source: file | export | benchmark_cache
path: <redacted path or benchmark id>
category: coding | tutorials | research | project_planning | debugging | architecture
archetype: tutorial | coding | project | research | journal | medical | informational_QA | other
transcript_chars: <int>
chunk_count: <int>
tier: gold | silver | bronze | negative
collector: internal | user_<anon_id>
collected_at: <iso8601>
checkpoint_id: <from v2 record>
incremental_tested: true | false
resume_tested: true | false
```

---

## Collection protocol

### Internal (gold/silver)

1. Select session from category quota table
2. `continuator checkpoint <file> --full` → `.continuator/checkpoint.yaml`
3. Score checkpoint with `checkpoint_quality_score.md` (human reviewer)
4. Run `resume_validation_runner.md` protocol
5. Optional: `continuator checkpoint <grown> --update` for append-only samples
6. Record scores in `validation_results_v2.md` (future)

### User-contributed (silver)

1. Participant exports chat (txt/json) from Cursor, Claude, or ChatGPT
2. Redact PII and secrets before submission
3. Same scoring pipeline as internal
4. Collect subjective repeat-intent survey (1–5)

### Privacy

- No raw transcripts in public repo without redaction
- Store full artifacts in private validation bucket
- Commit only: metadata, scores, redacted excerpts

---

## Category success thresholds (corpus-level)

| Category | Min sessions | Min median quality | Min resume pass rate |
|----------|:------------:|:------------------:|:--------------------:|
| Coding | 8 | 4.0 / 5 | 80% |
| Tutorials | 6 | 4.0 / 5 | 80% |
| Research | 4 | 3.5 / 5 | 70% |
| Project planning | 4 | 3.5 / 5 | 75% |
| Debugging | 4 | 4.0 / 5 | 80% |
| Architecture | 3 | 3.5 / 5 | 70% |
| **Negative controls** | 3 | **≤ 2.5 / 5** | **≤ 40%** |

---

## Suggested starter corpus (15 gold, expandable to 50)

| ID | Source | Category | Notes |
|----|--------|----------|-------|
| G01 | neck.txt | tutorials | Short smoke |
| G02 | gitissue.txt | coding | jQuery bug |
| G03 | jquery.txt | coding | Same genre |
| G04 | aman (cache) | tutorials | Stale quiz stress |
| G05 | kafka (cache) | tutorials | Medium N |
| G06 | superlong (cache) | coding | Large N |
| G07 | pm (cache) | project_planning | Best gold-standard |
| G08 | github (cache) | debugging | Duplication edge case |
| G09 | journal (cache) | research | Question-as-next-action |
| G10 | chat.txt | negative | Medical Q&A |
| G11 | my-project.yaml source | negative | User validation fail |
| G12–G15 | research/ training | architecture | Hypothesis threads |
| S01–S10 | User exports | mixed | Real silver collection |
| S11–S20 | Team redacted | coding | Cursor sessions |
| B01–B10 | memory_brain benchmarks | mixed | Bronze proxy only |

---

## What this corpus does **not** need

- Perfect balance across all LLM platforms (CLI validation first)
- Sessions > 200k chars in v1 (note but don't block)
- Non-English sessions until English gate passes
- Synthetic-only corpus (mock backend is for CI, not product proof)

---

## Related documents

- `validation_plan_v2.md` — audience and phasing
- `checkpoint_quality_score.md` — scoring rubric
- `resume_validation_runner.md` — resume protocol
- `checkpoint_archetype_analysis.md` — prior 85-conversation analysis
