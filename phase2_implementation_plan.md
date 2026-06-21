# Phase 2 Implementation Plan

**Scope:** Checkpoint export only (Phase 2A–2D). No resume, compression, editor integrations, or cloud sync.

**Companion docs:**

- [`checkpoint_schema_v1.md`](checkpoint_schema_v1.md) — CheckpointRecord schema
- [`checkpoint_storage_design.md`](checkpoint_storage_design.md) — storage layout and CLI UX

---

## Task 1: Codebase Audit — Structure Mapping

### 1.1 V10 extraction output structures

**Canonical per-chunk output** — `record_to_extraction_output(record)` in `continuator_engine/memory_model_v1.py`:

```python
{
    "topic": str,
    "summary": str,
    "important_facts": list[str],
    "goals": list[str],
    "decisions": list[str],
    "next_steps": list[str],
    "open_questions": list[str],
    "objective": list[str],
    "current_state": str,
    "completed_work": list[str],
    "active_problems": list[str],
    "resolved_problems": list[str],
    "constraints": list[str],
    "continuation_context": str,
    "model_id": str,
    "memory_model": str,
    "parse_ok": bool,
}
```

**Produced by:**

| Function | File | Returns |
|----------|------|---------|
| `_extract_chunk_in_current_context()` | `memory_model_v1.py` | single output dict |
| `extract_chunks_at_indices()` | `memory_model_v1.py` | `[{chunk_index, input_chars, output}]` |
| `extract_all_chunks()` | `memory_model_v1.py` | all indices (eval path) |

**Pipeline integration** — `handoff_evaluation_v1.py`:

- `iter_continuator_stream()` builds `v10_rows` with `{chunk_index, input_chars, output}`
- Converts to `v10_outputs` by adding `chunk_index` into each output dict
- Calls `_finalize_continuator(text, chunks, chunk_meta, v10_rows, ...)`

**Maps to CheckpointRecord:**

| CheckpointRecord field | Source |
|------------------------|--------|
| `pipeline.chunk_extractions[].chunk_index` | `row["chunk_index"]` |
| `pipeline.chunk_extractions[].input_chars` | `row["input_chars"]` |
| `pipeline.chunk_extractions[].parse_ok` | `row["output"]["parse_ok"]` |
| `pipeline.chunk_extractions[].output` | `row["output"]` (full dict) |

---

### 1.2 Continuation export structures

**Primary product export** — `generate_continuation_briefing_frontier()` in `continuation_export_v2_frontier.py`:

```python
generate_continuation_briefing_frontier(
    chunk_outputs: list[dict],   # v10_outputs with chunk_index
    *,
    conversation: str,
    archetype: str = "mixed",
    label: str = "",
    total_chunks: int | None = None,
) -> str                        # markdown briefing text
```

**Platform wrappers** — `build_platform_exports()` in `handoff_export_v1.py`:

```python
build_platform_exports(handoff: str, *, label: str = "") -> {
    "claude": str,
    "chatgpt": str,
    "gemini": str,
    "markdown": str,
}
```

**Session result keys** (from `_finalize_continuator()`):

| Session key | CheckpointRecord field |
|-------------|------------------------|
| `continuation_briefing` | `cached_exports.briefing` |
| `exports.claude` | `cached_exports.claude` |
| `exports.chatgpt` | `cached_exports.chatgpt` |
| `exports.gemini` | `cached_exports.gemini` |
| `exports.markdown` | `cached_exports.markdown` |
| `exports.v10_copy_paste` | `cached_exports.v10_copy_paste` |
| `product_baseline` | `pipeline.baseline` |
| `archetype` | `pipeline.archetype` |
| `briefing_words` | `stats.briefing_words` |

**Aggregated structured state** (not exported as JSON today — **new helper required**):

Reuse from `continuation_export_v2_frontier.py`:

| State field | Existing function |
|-------------|-------------------|
| `project_title` | `_project_title(states, label)` |
| `objective` | `_frontier_objective(frontier, history, conversation)` |
| `current_state` | `_terminal_position()` + `_conversation_frontier_hints()` |
| `completed_work` | `_aggregate_list_field(states, "completed_work")` from `continuation_export_v1.py` |
| `active_problems` | `filter_superseded_actives(_aggregate_list_field(frontier, "active_problems"), ...)` |
| `resolved_problems` | `_aggregate_list_field(frontier, "resolved_problems")` |
| `constraints` | `_aggregate_list_field(states, "constraints")` |
| `next_action` | `_derive_frontier_next_action(...)` |
| `closure_detected` | `continuation_closure_detected(terminal, conversation)` |

→ New module: `checkpoint_state_v1.py` with public `aggregate_checkpoint_state()`.

---

### 1.3 Explain export structures

**Function** — `generate_conversation_explanation()` in `conversation_explainer_v1.py`:

```python
generate_conversation_explanation(
    chunk_outputs: list[dict],
    *,
    conversation: str = "",
    label: str = "",
    archetype: str = "mixed",
    total_chunks: int | None = None,
) -> str
```

**Output sections:** OVERVIEW, MAIN TOPICS, LEARNINGS / DECISIONS, CURRENT STATUS, OPEN QUESTIONS, KEY TAKEAWAYS.

**Session mapping:**

| Session key | CheckpointRecord field |
|-------------|------------------------|
| `conversation_explanation` | `cached_exports.explain` |
| `exports.explain` | same |
| `explain_words` | `stats.explain_words` |

Already computed in `_finalize_continuator()` — no additional extraction needed for checkpoint save.

---

### 1.4 Ranker metadata available today

**Function** — `rank_chunks(chunks)` in `continuator_chunk_ranker_v1.py`:

```python
{
    "selected_indices": list[int],
    "k": int,
    "total_chunks": int,
    "selection_strategy": str,       # "approach_b_v1" | "full"
    "locked_indices": list[int],     # when strategy != "full"
    # audit fields (approach_b_v1 only):
    "displacement": list[float],
    "curvature": list[float],
    "changepoints_pelt": list[int],
    "peak_displacement": list[int],
    "peak_curvature": list[int],
    "cluster_boundaries": list[int],
    "boundary_candidates": list[int],
    "candidate_scores": dict[int, float],
    "cluster_audit": dict,
}
```

**Also in session result** — `chunk_selection` (added in `run_continuator()` / stream complete):

```python
{
    "strategy": str,
    "selected_indices": list[int],
    "k": int,
    "total_chunks": int,
}
```

**Chunking metadata** — `all_transcript_chunks()` in `memory_model_v1.py`:

```python
chunks, {
    "strategy": str,           # "paragraph_chunk_overlap"
    "chunk_count": int,
    "chunk_audit": dict,       # from _chunk_transcript_for_extraction
}
```

**Frontier metadata** — computed in `pipeline.inspect_conversation()` (reusable pattern):

| Function | File |
|----------|------|
| `frontier_cutoff_index(n)` | `continuation_export_v2_frontier.py` |
| `frontier_band_size(n)` | same |
| frontier indices | `range(cutoff, n)` |
| frontier_selected | intersection with selected_indices |

**Maps to CheckpointRecord `pipeline`:**

| CheckpointRecord field | Source |
|------------------------|--------|
| `pipeline.ranker.strategy` | `chunk_selection.strategy` |
| `pipeline.ranker.k` | `chunk_selection.k` |
| `pipeline.ranker.total_chunks` | `chunk_selection.total_chunks` |
| `pipeline.ranker.selected_indices` | `chunk_selection.selected_indices` |
| `pipeline.ranker.locked_indices` | `rank_audit["locked_indices"]` |
| `pipeline.ranker.changepoints_pelt` | `rank_audit["changepoints_pelt"]` |
| `pipeline.ranker.audit_full` | full `rank_audit` when `--verbose` |
| `pipeline.chunking` | `result["chunking"]` |
| `pipeline.frontier.cutoff_index` | `frontier_cutoff_index(total_chunks)` |
| `pipeline.frontier.band_size` | `frontier_band_size(total_chunks)` |
| `pipeline.frontier.indices` | `list(range(cutoff, n))` |
| `pipeline.frontier.selected_in_frontier` | filter selected_indices ≥ cutoff |

---

### 1.5 Full session result → CheckpointRecord map

`run_continuator()` / `iter_continuator_stream()` complete event already returns nearly everything:

```python
{
    "session_id": str,              # → NOT stored (ephemeral); use checkpoint.id instead
    "label": str,                   # → checkpoint.label
    "source": str,                  # → NOT used ("continuator"); use CLI source meta
    "archetype": str,               # → pipeline.archetype
    "product_baseline": str,        # → pipeline.baseline
    "created_at": str,              # → checkpoint.created_at
    "transcript_chars": int,        # → source.char_count
    "chunk_count": int,             # → pipeline.chunking.chunk_count
    "chunking": dict,               # → pipeline.chunking
    "chunk_selection": dict,        # → pipeline.ranker (partial)
    "continuation_briefing": str,   # → cached_exports.briefing
    "conversation_explanation": str,# → cached_exports.explain
    "briefing_words": int,          # → stats.briefing_words
    "explain_words": int,           # → stats.explain_words
    "exports": dict,                # → cached_exports (platform keys)
    "metrics": dict,                # → stats.extraction_parse_rate
    "_runtime_seconds": float,      # → stats.runtime_seconds (from pipeline.py wrapper)
}
```

**Gap:** rank_audit full dict and v10_rows are not in session result today. Options:

1. **Extend `_finalize_continuator()`** to accept optional `rank_audit` and include `chunk_extractions` in result — preferred, minimal duplication.
2. Re-derive rank_audit on checkpoint save — wasteful, wrong if ranker is non-deterministic.

**Recommended:** add optional keys to session result (internal only, not breaking CLI `--json` consumers):

```python
"v10_rows": [...],       # internal
"rank_audit": {...},     # internal
```

---

### 1.6 Reusable functions summary

| Purpose | Function | Module | Reuse |
|---------|----------|--------|-------|
| Run full pipeline | `run_continuator()` | `handoff_evaluation_v1.py` | ✅ direct |
| Stream pipeline | `iter_continuator_stream()` | same | ✅ for TUI later |
| Chunk transcript | `all_transcript_chunks()` | `memory_model_v1.py` | ✅ direct |
| Rank chunks | `rank_chunks()` | `continuator_chunk_ranker_v1.py` | ✅ direct |
| Extract selected | `extract_chunks_at_indices()` | `memory_model_v1.py` | ✅ direct |
| Finalize exports | `_finalize_continuator()` | `handoff_evaluation_v1.py` | ✅ extend |
| Continuation briefing | `generate_continuation_briefing_frontier()` | `continuation_export_v2_frontier.py` | ✅ already called in finalize |
| Explain text | `generate_conversation_explanation()` | `conversation_explainer_v1.py` | ✅ already called in finalize |
| Platform exports | `build_platform_exports()` | `handoff_export_v1.py` | ✅ already called in finalize |
| Copy-paste JSON | `format_copy_paste_outputs()` | `memory_model_v1.py` | ✅ already called in finalize |
| Frontier cutoff | `frontier_cutoff_index()`, `frontier_band_size()` | `continuation_export_v2_frontier.py` | ✅ direct |
| Read transcript | `read_transcript()` | `continuator/runtime.py` | ✅ direct |
| Label from path | `label_from_path()` | `continuator/runtime.py` | ✅ direct |
| Pick export view | `pick_export()` | `continuator/pipeline.py` | ✅ for show --format |
| Quality rubric | `briefing_quality()` | `continuator/pipeline.py` | ✅ validate on save |
| **Aggregated state** | `aggregate_checkpoint_state()` | **new** `checkpoint_state_v1.py` | 🔨 thin wrapper |
| **Build record** | `build_checkpoint_record()` | **new** `checkpoint_record_v1.py` | 🔨 mapper |
| **Write/read YAML** | `write_checkpoint()`, `read_checkpoint()` | **new** `checkpoint_store_v1.py` | 🔨 new |
| **Hash transcript** | `hash_transcript()` | **new** `checkpoint_record_v1.py` | 🔨 new |

---

## Task 4: Phased Implementation Plan

### Phase 2A — Save checkpoint

**Goal:** `continuator checkpoint FILE` runs pipeline and writes valid CheckpointRecord YAML.

#### New modules

| Module | LOC est. | Purpose |
|--------|----------|---------|
| `continuator_engine/checkpoint_state_v1.py` | ~80 | `aggregate_checkpoint_state()` |
| `continuator_engine/checkpoint_record_v1.py` | ~180 | build, validate, hash, id generation |
| `continuator_engine/checkpoint_store_v1.py` | ~120 | YAML I/O, atomic write, paths |
| `continuator/commands/checkpoint_cmd.py` | ~150 | argparse + create handler |

#### Files to modify

| File | Change | LOC est. |
|------|--------|----------|
| `continuator_engine/handoff_evaluation_v1.py` | Include `v10_rows`, `rank_audit` in `_finalize_continuator` result | +15 |
| `continuator/cli.py` | Register `checkpoint` subcommand | +5 |
| `continuator/commands/__init__.py` | Import checkpoint_cmd (if package init exists) | +2 |
| `pyproject.toml` | No change expected | 0 |

#### Tests (new)

| File | LOC est. |
|------|----------|
| `tests/test_checkpoint_record_v1.py` | ~120 |
| `tests/test_checkpoint_store_v1.py` | ~80 |
| `tests/fixtures/checkpoints/...` | fixture YAML |

#### Risks

| Risk | Mitigation |
|------|------------|
| `_finalize_continuator` signature change breaks `--json` consumers | New keys are additive; document as stable subset vs full session JSON |
| Private helper imports from `continuation_export_v2_frontier` | Accept for Phase 2; extract shared `frontier_merge_v1.py` later if needed |
| PyYAML dependency | Add `pyyaml` to `pyproject.toml` optional or core dep |
| Empty briefing fails save | Same as `continue` — reuse `briefing_quality()` gate |

**Total LOC estimate Phase 2A:** ~750 (including tests)

---

### Phase 2B — List checkpoints

**Goal:** `continuator checkpoint list [--project NAME]`

#### New / modified

| File | Change | LOC est. |
|------|--------|----------|
| `continuator_engine/checkpoint_store_v1.py` | `list_checkpoints()`, index read/write, scan fallback | +100 |
| `continuator/commands/checkpoint_cmd.py` | `list` subparser + table renderer | +80 |
| `continuator/console.py` | Optional: table styling helper | +20 |

#### Tests

| File | LOC est. |
|------|----------|
| `tests/test_checkpoint_store_v1.py` | +60 (list, index, empty) |

#### Risks

| Risk | Mitigation |
|------|------------|
| Stale index after manual file delete | Fallback directory scan; rebuild index on mismatch |
| Slow scan with many checkpoints | Index manifest (see storage design) |

**Total LOC estimate Phase 2B:** ~260

---

### Phase 2C — Show checkpoint

**Goal:** `continuator checkpoint show TARGET [--format ...]`

#### New / modified

| File | Change | LOC est. |
|------|--------|----------|
| `continuator_engine/checkpoint_store_v1.py` | `resolve_checkpoint_target()`, `read_checkpoint()` | +60 |
| `continuator/commands/checkpoint_cmd.py` | `show` subparser + format dispatch | +100 |
| `continuator/pipeline.py` | Optional: reuse `pick_export` pattern for format names | +10 |

#### Tests

| File | LOC est. |
|------|----------|
| `tests/test_checkpoint_cmd_show.py` | ~80 |

#### Risks

| Risk | Mitigation |
|------|------------|
| Ambiguous id across projects | Search all projects; error if multiple matches |
| Corrupt YAML | Validate on read; clear error message |

**Total LOC estimate Phase 2C:** ~250

---

### Phase 2D — Diff checkpoints

**Goal:** `continuator checkpoint diff TARGET_A TARGET_B`

#### New modules

| Module | LOC est. | Purpose |
|--------|----------|---------|
| `continuator_engine/checkpoint_diff_v1.py` | ~150 | Field-level diff on `state` + metadata |

#### Modified

| File | Change | LOC est. |
|------|--------|----------|
| `continuator/commands/checkpoint_cmd.py` | `diff` subparser | +60 |
| `continuator/console.py` | Diff color output (optional) | +30 |

#### Diff scope (v1)

Compare:

- `source.sha256`, `source.char_count`
- `state.objective`, `completed_work`, `active_problems`, `resolved_problems`, `constraints`
- `state.current_state`, `state.next_action`
- `pipeline.ranker.selected_indices`

List fields: added / removed / unchanged (set diff on normalized strings).

Scalar fields: show before → after.

#### Tests

| File | LOC est. |
|------|----------|
| `tests/test_checkpoint_diff_v1.py` | ~100 |

#### Risks

| Risk | Mitigation |
|------|------------|
| Noisy diffs from reordering | Normalize list order before compare (same dedupe as export) |
| Large output | Default to state fields only; `--full` for exports diff |

**Total LOC estimate Phase 2D:** ~340

---

### Phase 2 total estimate

| Phase | LOC (incl. tests) |
|-------|-------------------|
| 2A Save | ~750 |
| 2B List | ~260 |
| 2C Show | ~250 |
| 2D Diff | ~340 |
| **Total** | **~1,600** |

Recommended ship order: 2A → 2B → 2C → 2D (each independently useful).

---

## Task 5: `continue` Internal Refactor — Extract → Checkpoint → Render

### Current call chain

```
continue_cmd.run()
  └─ run_continuation()                    # continuator/pipeline.py
       └─ iter_continuator_stream()         # handoff_evaluation_v1.py
            ├─ all_transcript_chunks()
            ├─ rank_chunks()
            ├─ extract (v10_rows)
            └─ _finalize_continuator()      # → session result dict
       └─ console streaming / timing
  └─ pick_export(result, "briefing")
  └─ console.stream_briefing() / -o write
```

Checkpoint is implicit: session result dict exists in memory but is not persisted.

### Target internal architecture

```
                    ┌─────────────────────────────────┐
                    │         extract_session()        │
                    │  (wraps run_continuator today)   │
                    └───────────────┬─────────────────┘
                                    │
                    ┌───────────────▼─────────────────┐
                    │      build_checkpoint_record()     │
                    │  (pure mapper — no side effects)   │
                    └───────────────┬─────────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
    ┌─────────▼─────────┐  ┌───────▼────────┐  ┌────────▼────────┐
    │  save_checkpoint   │  │ render_briefing │  │ render_explain  │
    │  (checkpoint cmd)  │  │ (continue cmd)  │  │ (explain cmd)   │
    └───────────────────┘  └─────────────────┘  └─────────────────┘
```

### Can this happen without changing user-facing behavior?

**Yes.** Constraints:

1. `continuator continue FILE` output (briefing text, TUI, shortcuts, exit codes) must remain identical.
2. `continuator continue --json` may gain new keys (`v10_rows`, `rank_audit`) — additive only.
3. Performance must not regress — `build_checkpoint_record()` is pure dict mapping (~1ms).

### Migration path

#### Step 1 — Add mapper (no CLI change)

Create `build_checkpoint_record(session, *, source_meta) -> dict` in `checkpoint_record_v1.py`.

Unit test: session fixture → valid CheckpointRecord.

#### Step 2 — Extend session result (internal)

Modify `_finalize_continuator()` to attach:

```python
"v10_rows": v10_rows,
"rank_audit": rank_audit,   # pass through from run_continuator
```

`run_continuator()` already has `rank_audit` in scope — thread it into `_finalize_continuator`.

#### Step 3 — Introduce `extract_session()` wrapper

In `continuator/pipeline.py`:

```python
def extract_session(transcript, *, label="", use_chunk_ranker=True, console=None, verbose=False) -> dict:
    """Run pipeline; return session result. Same as run_continuation without render side effects."""
    return run_continuation(...)  # rename / alias
```

`run_continuation()` keeps console progress behavior — it *is* the extract step today.

#### Step 4 — Add `render_briefing(session) -> str`

```python
def render_briefing(session: dict) -> str:
    return pick_export(session, "briefing")
```

No change to `continue_cmd` logic — optional refactor to call through named functions.

#### Step 5 — Ship `checkpoint` command

```python
# checkpoint_cmd.run()
session = run_continuation(transcript, label=label, ...)
record = build_checkpoint_record(session, source_meta={...})
write_checkpoint(record, path)
```

`continue` unchanged.

#### Step 6 — Optional internal dedup in `continue_cmd`

```python
session = extract_session(...)
briefing = render_briefing(session)
# no save
```

Behavior identical; clearer separation for future `resume` (Phase 3).

### What NOT to refactor in Phase 2

| Change | Defer reason |
|--------|--------------|
| Make `continue` write checkpoint by default | User-facing behavior change |
| Replace `--json` output with CheckpointRecord | Breaking change for power users |
| Split `iter_continuator_stream` | High risk; streaming TUI depends on it |
| Lazy explain generation | Explain already computed in finalize; optimize in Phase 4 |

### Refactor feasibility verdict

| Question | Answer |
|----------|--------|
| Can `continue` decompose into extract → checkpoint → render? | **Yes**, with `build_checkpoint_record()` as optional middle step |
| Must `continue` persist checkpoints? | **No** — save only in `checkpoint` command |
| Breaking changes required? | **None** if session JSON extensions are additive |
| Recommended Phase 2 scope | Add mapper + checkpoint command; refactor `continue_cmd` to named helpers only if it clarifies — not required for ship |

---

## Dependency additions

| Package | Purpose | Notes |
|---------|---------|-------|
| `pyyaml` | YAML serialize/deserialize | Likely new core dependency |
| (none else) | | Reuse existing stack |

---

## Documentation updates (Phase 2 ship)

| File | Update |
|------|--------|
| `README.md` | Add `checkpoint` command section; soften hero toward checkpointing |
| `docs/cli-ux-examples.md` | Checkpoint create/list/show examples |
| `checkpointing_roadmap.md` | Mark Phase 2 complete when shipped |

---

## Out of scope (explicit)

- Phase 3: `resume`, incremental update, lineage
- Phase 4: `compress`, tiers
- Phase 5: editor integrations
- Cloud sync, API server, new model training
- TUI checkpoint browser (nice-to-have; not required for Phase 2 MVP)
