# Validation Results v2

**Status:** Template — fill in as sessions are reviewed  
**Scoring:** 1–5 per `checkpoint_quality_score.md`  
**Fresh LLM:** pass | partial | fail

---

## Summary

| Metric | Value |
|--------|-------|
| Sessions tested | |
| PASS | |
| PARTIAL | |
| FAIL | |
| PASS rate (coding + tutorials + debugging) | |
| Median checkpoint quality | |
| Median resume quality | |
| Validation complete? | |

---

## Results

| Session | Category | Checkpoint Quality | Resume Quality | Fresh LLM Continuation | Notes |
|---------|----------|:------------------:|:--------------:|:--------------------:|-------|
| neck | tutorials | | | | |
| gitissue | coding | | | | |
| jquery | coding | | | | |
| aman | tutorials | | | | |
| kafka | tutorials | | | | |
| superlong | coding | | | | |
| pm | project_planning | | | | |
| github | debugging | | | | |
| kubernetes | tutorials | | | | |
| journal | research | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |

---

## Failure tags (if applicable)

| Session | Code | Description |
|---------|------|-------------|
| | F-NA | Bad next_action |
| | F-DUP | completed ≡ active duplication |
| | F-STALE | Stale terminal / old quiz |
| | F-OBS | Observer voice |
| | F-MISS | Missing critical blocker |
| | F-ASK | LLM asked for transcript |
| | F-HALL | Hallucination |
| | F-GENRE | Wrong archetype (Q&A) |

---

## Reviewer notes

### What worked

-

### What failed systematically

-

### V11 gate recommendation

- [ ] STAY ON V10
- [ ] REVIEW (see `v11_decision_gate_v2.md`)
- [ ] APPROVE V11 — pattern:

---

## Artifact locations

| Session | Path |
|---------|------|
| All runs | `validation_runs/<session_name>/` |
| Run summary | `validation_runs/run_summary.json` |

---

## Related documents

- `validation_dashboard.md` — status tracker
- `checkpoint_quality_score.md` — rubric definitions
- `v11_decision_gate_v2.md` — retrain decision framework
