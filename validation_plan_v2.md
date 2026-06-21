# Validation Plan v2

**Status:** Plan only — product validation after Phase 2  
**Scope:** Who should use Continuator today, how to validate, what success looks like  
**Out of scope:** New features, extensions, V10 changes, V11 training

---

## Purpose

Phase 2 shipped the state engine: v2 checkpoints, incremental update, cached resume, local serve, benchmark parity harness. The extraction engine (V10) is unchanged.

**The open question is no longer "can we build it?"** It is:

> Does Continuator produce checkpoints that real users trust enough to resume work without the original transcript?

This plan defines **who to validate with first**, **what to measure**, and **what evidence is required before any further engineering investment.

---

## Core product hypothesis

Continuator is valuable when a conversation has **durable project state**:

- an ongoing goal
- completed milestones
- open blockers
- a concrete next step

It is **not** valuable when the conversation is episodic Q&A, medical lookup, or casual chat — fields populate but semantics fail (see `checkpoint_archetype_analysis.md`, `checkpoints/my-project.yaml`).

**Today's product:** checkpoint + resume for long **coding, tutorial, project, and research** threads.  
**Not today's product:** universal "Git for all AI conversations."

---

## Who should use Continuator today?

### Candidate groups (ranked by expected value)

| Rank | Group | Expected value | Why | Validation priority |
|:----:|-------|:--------------:|-----|:-----------------:|
| **1** | **Cursor users** | **Highest** | Long multi-file coding sessions; natural fit for checkpoint-before-switch-model; `.continuator/checkpoint.yaml` in repo; resume without re-pasting transcript; aligns with primary product wedge (agentic coding). | **P0** |
| **2** | **Claude Code users** | **High** | Same session shape as Cursor (terminal agent, long threads, implementation arcs). Phase 2 `serve` is the future integration surface; validation can run via CLI today. | **P0** |
| **3** | **ChatGPT power users** | **High** | Large user base doing coding + tutoring + project planning in browser. Continuator is paste-export → checkpoint → resume briefing. Friction is higher (no native integration yet) but archetype fit is strong when they use ChatGPT as a dev tutor. | **P1** |
| **4** | **Researchers** | **Medium–high** | Multi-step inquiry threads (hypothesis, evidence, open questions) map well to schema when thread is inquiry-driven. Weaker when research = single-shot literature lookup. | **P1** |
| **5** | **Learners** | **Medium** | Tutorial / confused-learner threads are a V10 training strength (Aman, Kafka benchmarks). High checkpoint usefulness when session is a **course or skill thread**; low when learner asks one-off homework questions. Subset of ChatGPT/Cursor users. | **P1** |
| **6** | **Codex users** | **Medium** | Similar coding value to Cursor/Claude Code but smaller surface area and less session persistence pain today. Validate after P0 groups confirm resume utility. | **P2** |

### Ranking rationale (summary)

```
Cursor / Claude Code  →  longest sessions, highest resume pain, repo-local checkpoint path
ChatGPT power users   →  largest reachable audience, same archetypes, higher paste friction
Researchers           →  good schema fit for inquiry threads, narrower wedge
Learners              →  strong when tutorial-shaped, redundant label for ranks 1–3
Codex                 →  coding fit yes, product-integration fit later
```

### Who should **not** be primary targets today

| Group | Reason |
|-------|--------|
| Medical / health Q&A users | Populated checkpoints mislead; questions become `next_action` |
| Informational lookup users | No resumable work unit; checkpoint ≈ summary |
| Casual chat / community threads | Observer voice, duplication, no project arc |
| Single-turn prompt users | No session long enough to justify checkpoint overhead |

Do not market to these groups until validation identifies a distinct failure pattern that V11 could address.

---

## Intended user profiles (concrete)

### Profile A — Cursor developer (P0)

- 45–120 minute coding session across multiple files
- Switches model or starts fresh chat mid-implementation
- Needs: "where was I, what's broken, what do I do next"
- Success: resumes in new chat without re-uploading full transcript

### Profile B — Tutorial learner (P1)

- Multi-lesson thread (e.g. web dev course, API module)
- Returns days later to same project
- Needs: objective + completed modules + next exercise
- Success: tutor AI continues from correct lesson position

### Profile C — Project / RFC author (P1)

- Planning + implementation thread (PM blockers, architecture decisions)
- Needs: constraints, active problems, decision log in `completed_work`
- Success: new collaborator AI picks up without re-reading 50k tokens

### Profile D — Research thread (P1)

- Hypothesis exploration over multiple turns
- Needs: open questions in `active_problems`, evidence in `completed_work`
- Success: fresh LLM continues inquiry without losing thread

---

## Validation goals

| # | Question | Pass signal |
|---|----------|-------------|
| 1 | Is checkpoint quality good enough in target archetypes? | Median field score ≥ 4/5 on `checkpoint_quality_score.md` |
| 2 | Does resume work without transcript? | ≥ 80% of corpus passes `resume_validation_runner.md` continuity test |
| 3 | Is incremental update trusted? | Quality parity ≥ 95% vs full re-extract (Phase 2 benchmark gate) |
| 4 | Do users prefer checkpoint over raw paste? | ≥ 60% subjective preference in moderated sessions |
| 5 | Where does V10 fail systematically? | Failure patterns documented with rates — input to `v11_decision_gate_v2.md` |

---

## Validation phases

### Phase V1 — Internal corpus (week 1–2)

- Run `real_world_validation_corpus.md` design on 25–50 sessions
- Score with `checkpoint_quality_score.md`
- Run `resume_validation_runner.md` on all HIGH archetype samples
- No user recruitment yet

**Gate:** ≥ 70% of coding/tutorial/project samples pass resume continuity before external users.

### Phase V2 — Guided user sessions (week 3–4)

- 5–10 participants per P0/P1 group (Cursor, Claude Code, ChatGPT power users)
- Task: complete a real session, checkpoint, return next day, resume in fresh LLM
- Collect: quality scores, time saved, failure quotes

**Gate:** ≥ 60% would use again unprompted.

### Phase V3 — Longitudinal (week 5–8)

- Same users run 3+ checkpoints on same project with `--update`
- Measure incremental trust and drift

**Gate:** Incremental quality parity holds on real append-only growth.

---

## What we are **not** validating in this cycle

| Item | Defer reason |
|------|--------------|
| Cursor / VS Code extensions | Phase 3 — validate CLI checkpoint first |
| Browser extension | Phase 5 |
| MCP / Claude Code native integration | Phase 4 |
| Universal Q&A checkpointing | Out of product scope until V11 gate |
| V11 retraining | Only if `v11_decision_gate_v2.md` conditions met |

---

## Success criteria (product validation complete)

Validation is **complete** when all of the following hold:

1. **Corpus:** 25–50 real sessions scored across 6 categories (`real_world_validation_corpus.md`)
2. **Quality:** Median checkpoint quality ≥ 3.5/5 overall; ≥ 4.0/5 for coding + tutorial categories
3. **Resume:** ≥ 80% pass resume continuity test on HIGH-value archetypes
4. **Users:** ≥ 8 moderated sessions across P0/P1 groups with ≥ 60% repeat intent
5. **V11:** Decision documented — either "stay on V10" with known limitations or "train V11" with specific failure pattern and prevalence

---

## Deliverables from this validation cycle

| Document | Role |
|----------|------|
| `real_world_validation_corpus.md` | Session selection and category criteria |
| `checkpoint_quality_score.md` | Human + LLM-as-judge rubric |
| `resume_validation_runner.md` | Transcript-deleted resume protocol |
| `v11_decision_gate_v2.md` | Retrain decision framework |
| `validation_results_v2.md` | *(future)* scored corpus + user notes |

---

## Messaging for today's users

| Audience | Message |
|----------|---------|
| **Use today** | "Checkpoint long coding, tutoring, and project threads. Resume in a fresh AI without the full transcript." |
| **Caution** | "Not designed for medical Q&A, lookups, or casual chat." |
| **Workflow** | `continuator checkpoint session.txt` → `.continuator/checkpoint.yaml` → `continuator resume` or paste briefing |

---

## Related documents

- `checkpoint_archetype_analysis.md` — genre fit evidence (85 conversations)
- `phase2_implementation_spec.md` — shipped state engine
- `checkpoint_format_v2.md` — checkpoint schema
- `integration_roadmap.md` — extensions deferred to Phase 3+
