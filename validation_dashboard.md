# Validation Dashboard

**Purpose:** Track resume validation progress across 10–20 real sessions.  
**Updated by:** Human reviewer after each fresh-LLM test.  
**Generated artifacts:** `scripts/validation_runner_v1.py` → `validation_runs/`

---

## North-star question

> **Can a fresh Claude / ChatGPT / Gemini continue the work from the checkpoint alone?**

---

## Status definitions

| Status | Checkpoint quality | Resume quality | Fresh LLM | Meaning |
|--------|:------------------:|:--------------:|:---------:|---------|
| **PASS** | ≥ 4 | ≥ 4 | Continues productively; no transcript requested | Ship confidence for this archetype |
| **PARTIAL** | ≥ 3 | ≥ 3 | Mostly continues; minor gaps or one clarifying question | Known limitation; document |
| **FAIL** | ≤ 2 | ≤ 2 | Asks for transcript, hallucinates, or restarts | Blocker or out-of-scope genre |
| **PENDING** | — | — | Not yet tested | Awaiting reviewer |

**Fresh LLM continuation** is the gate — checkpoint/resume scores support root-cause tagging.

---

## Master tracker

Copy this table to your working copy or use `validation_results_v2.md`.

| Session | Category | Checkpoint | Resume | Fresh LLM | Status | Reviewer | Date |
|---------|----------|:----------:|:------:|:---------:|:------:|----------|------|
| neck | tutorials | — | — | — | PENDING | | |
| gitissue | coding | — | — | — | PENDING | | |
| jquery | coding | — | — | — | PENDING | | |
| aman | tutorials | — | — | — | PENDING | | |
| kafka | tutorials | — | — | — | PENDING | | |
| superlong | coding | — | — | — | PENDING | | |
| pm | project_planning | — | — | — | PENDING | | |
| github | debugging | — | — | — | PENDING | | |
| kubernetes | tutorials | — | — | — | PENDING | | |
| journal | research | — | — | — | PENDING | | |

*Scores are 1–5 per `checkpoint_quality_score.md`. Fresh LLM: pass / partial / fail.*

---

## Per-session checklist

For each row in `validation_runs/<session>/`:

- [ ] `checkpoint.yaml` generated
- [ ] `resume.txt` non-empty
- [ ] `resume_ms` < 500 in `metadata.json`
- [ ] Pasted `claude_prompt.txt` into fresh Claude chat
- [ ] Pasted `chatgpt_prompt.txt` into fresh ChatGPT chat (optional)
- [ ] Pasted `gemini_prompt.txt` into fresh Gemini chat (optional)
- [ ] LLM did **not** ask for original conversation
- [ ] Scores recorded in `metadata.json` + master tracker
- [ ] Failure code tagged if FAIL (`F-NA`, `F-DUP`, `F-ASK`, … — see `resume_validation_runner.md`)

---

## Aggregate gates

Update after ≥ 10 sessions reviewed:

| Metric | Target | Current |
|--------|--------|---------|
| PASS rate (coding + tutorials + debugging) | ≥ 80% | — |
| Median checkpoint quality | ≥ 4.0 | — |
| Median resume quality | ≥ 4.0 | — |
| Fresh LLM asks for transcript | 0% | — |
| Negative control fail (if tested) | chat/medical ≤ 40% pass | — |

**Product validation pass:** coding + tutorials + debugging PASS rate ≥ 80% **and** zero transcript requests on PASS cohort.

---

## Run summary (auto-generated)

After each runner invocation:

```bash
cat validation_runs/run_summary.json
```

Fields per session: `checkpoint_seconds`, `resume_ms`, `auto_briefing_quality` (automated smoke — not human score).

---

## Workflow diagram

```
validation_runner_v1.py
        │
        ▼
validation_runs/<session>/
  checkpoint.yaml
  resume.txt
  *_prompt.txt
  metadata.json
        │
        ▼
Fresh LLM paste test (human)
        │
        ▼
validation_dashboard.md  ← update Status
validation_results_v2.md ← record scores + notes
        │
        ▼
v11_decision_gate_v2.md  ← only if systematic failures
```

---

## Commands reference

```bash
# Examples only (3 sessions, in-repo)
python scripts/validation_runner_v1.py examples/ -o validation_runs

# Top 10 with manifest
python scripts/validation_runner_v1.py \
  --from-cache aman kafka superlong pm github kubernetes journal \
  --manifest validation_manifest.json \
  -o validation_runs

# Smoke without LoRA
python scripts/validation_runner_v1.py examples/ --mock -o validation_runs
```

---

## Related documents

- `resume_test_pack.md` — prompt files and paste procedure
- `top_10_validation_sessions.md` — session priority list
- `validation_results_v2.md` — detailed results template
- `validation_plan_v2.md` — overall validation phasing
