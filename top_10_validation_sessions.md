# Top 10 Validation Sessions

**Purpose:** Highest-value sessions to run first for product confidence.  
**Goal:** Answer whether a fresh LLM can continue from checkpoint alone.  
**Avoid:** medical, casual chat, informational lookup

---

## Priority list

Run in order. First 3 are in-repo — no setup required.

| # | Session | Category | Source | Why first |
|---|---------|----------|--------|-----------|
| **1** | **gitissue** | coding / debugging | `examples/gitissue.txt` | Medium GitHub issue thread; jQuery bug — core wedge |
| **2** | **neck** | tutorials | `examples/neck.txt` | Short smoke; posture tutoring; fast iteration |
| **3** | **jquery** | coding | `examples/jquery.txt` | Learner + library session; V10 training alignment |
| **4** | **aman** | tutorials | benchmark cache | Confused learner; stale-quiz stress case |
| **5** | **kafka** | tutorials | benchmark cache | Multi-chunk tutorial; published eval sample |
| **6** | **pm** | project planning | benchmark cache | Best gold-standard checkpoint in archetype analysis |
| **7** | **superlong** | coding | benchmark cache | Large N; rich `completed_work`; speed stress |
| **8** | **github** | debugging | benchmark cache | CI/CD thread; duplication edge case — expect PARTIAL |
| **9** | **kubernetes** | tutorials | benchmark cache | Additional tutorial coverage |
| **10** | **journal** | research | benchmark cache | Reflective thread; medium expected value |

---

## Excluded (negative controls — run later, not in top 10)

| Session | Category | Source | Why excluded from top 10 |
|---------|----------|--------|--------------------------|
| chat | medical / informational | `examples/chat.txt` | Expected FAIL — confirms genre gating |
| my-project | medical | `checkpoints/my-project.yaml` source | User validation artifact; low resume utility |

---

## One-command batch

### In-repo only (sessions 1–3)

```bash
python scripts/validation_runner_v1.py examples/ -o validation_runs
```

### Full top 10

Requires benchmark cache at  
`/Users/acmmi/projects/memory/training_pipeline/evaluation/continuator_benchmark_v1_cache.jsonl`  
(or set `--cache-path`).

```bash
python scripts/validation_runner_v1.py \
  --from-cache aman kafka superlong pm github kubernetes journal \
  --manifest validation_manifest.json \
  -o validation_runs
```

This exports cache transcripts to `validation_runs/corpus/` then processes all manifest entries (examples + corpus).

### Real V10 (required for product gate)

Do **not** use `--mock` for scoring. Mock is wiring smoke only.

---

## Expected outcomes (hypothesis)

Based on `checkpoint_archetype_analysis.md` gold-standard rows:

| Session | Expected checkpoint | Expected resume | Risk |
|---------|:-------------------:|:---------------:|------|
| pm | High | PASS | — |
| neck | High | PASS | — |
| gitissue | High | PASS | — |
| jquery | High | PASS | — |
| aman | Medium | PASS / PARTIAL | Stale quiz → `F-STALE` |
| kafka | Medium | PASS / PARTIAL | Next action quality |
| superlong | Medium | PARTIAL | Confirmatory next action |
| github | Low–Medium | PARTIAL / FAIL | `F-DUP` duplication |
| kubernetes | Medium | PASS | — |
| journal | Medium | PARTIAL | Question-as-next-action |

**Gate:** ≥ 8/10 PASS or PARTIAL on sessions 1–7; sessions 8–10 document known limits.

---

## Per-session paste files

After runner completes:

| Session | Paste into fresh LLM |
|---------|---------------------|
| gitissue | `validation_runs/gitissue/claude_prompt.txt` |
| neck | `validation_runs/neck/claude_prompt.txt` |
| … | `validation_runs/<name>/claude_prompt.txt` |

Use `chatgpt_prompt.txt` / `gemini_prompt.txt` for cross-model check on subset (≥ 3 sessions).

---

## Category coverage

| Category | Sessions in top 10 | Count |
|----------|-------------------|------:|
| coding | gitissue, jquery, superlong | 3 |
| tutorials | neck, aman, kafka, kubernetes | 4 |
| debugging | gitissue, github | 2 |
| project planning | pm | 1 |
| research | journal | 1 |

---

## After top 10

Expand to 25–50 per `real_world_validation_corpus.md`:

- User-exported Cursor sessions (redacted)
- Additional `memory_brain/benchmarks/` troubleshooting threads
- Team project planning exports

Do not expand until top 10 gate is scored.

---

## Related documents

- `resume_test_pack.md` — paste procedure
- `validation_manifest.json` — machine-readable session list
- `validation_dashboard.md` — track PASS / PARTIAL / FAIL
- `validation_results_v2.md` — record scores
