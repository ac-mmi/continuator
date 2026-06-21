# CheckpointRecord v1 Schema

**Status:** Design only (Phase 2)  
**Format version:** `1`  
**Scope:** Minimum viable checkpoint export — no resume, compression tiers, or editor integrations.

---

## Purpose

CheckpointRecord is the durable artifact produced by `continuator checkpoint`. It wraps everything the pipeline already computes during `continuator continue`, serialized as a versioned YAML file.

Design goals:

1. **Stable format** — `format_version` enables future migrations without breaking readers.
2. **Self-describing** — a checkpoint file alone explains what was extracted, from what source, and how.
3. **Render-ready** — `cached_exports` holds paste-ready outputs so `checkpoint show` and future `resume` avoid re-running LoRA.
4. **Faithful to pipeline** — fields map directly to existing `run_continuator()` / `_finalize_continuator()` outputs.

---

## Top-level structure

```yaml
checkpoint:
  format_version: 1
  id: a3f2c891
  project: neck-refactor
  message: ""
  created_at: "2026-06-21T14:30:00.123456+00:00"
  label: neck
  source: { ... }
  pipeline: { ... }
  state: { ... }
  cached_exports: { ... }
  stats: { ... }
```

All keys under `checkpoint` are required unless marked *optional*.

---

## Field reference

### `checkpoint.format_version`

| Type | Value |
|------|-------|
| `integer` | `1` |

Increment when making breaking schema changes. Readers must reject unknown versions with a clear error.

---

### `checkpoint.id`

| Type | Description |
|------|-------------|
| `string` | Short unique identifier for this checkpoint file |

**Generation:** first 8 hex chars of SHA-256 over `(project + created_at + source.sha256)`.

Used in filenames: `<id>.yaml`. Not guaranteed globally unique across machines; unique within a project directory.

---

### `checkpoint.project`

| Type | Description |
|------|-------------|
| `string` | Namespace for grouping checkpoints |

Derived from `--name` flag, or `label_from_path()` stem when omitted. Slugified: lowercase, `[a-z0-9-]` only, max 64 chars.

Maps to storage directory: `~/.continuator/checkpoints/<project>/`.

---

### `checkpoint.message` *(optional)*

| Type | Description |
|------|-------------|
| `string` | User-supplied note (`--message` flag) |

Empty string when omitted. Analogous to a git commit message — human context only, not used by pipeline.

---

### `checkpoint.created_at`

| Type | Description |
|------|-------------|
| `string` | ISO 8601 UTC timestamp |

**Source:** `_utc_now()` in `handoff_evaluation_v1.py` (same as session `created_at` today).

---

### `checkpoint.label` *(optional)*

| Type | Description |
|------|-------------|
| `string` | Display label passed to export formatters |

**Source:** `run_continuator(label=...)` / `_finalize_continuator(label=...)`. Used in platform export wrappers and briefing title.

---

### `checkpoint.source`

Provenance of the input transcript.

```yaml
source:
  path: /Users/me/chat.txt          # absolute path at checkpoint time
  path_relative: chat.txt            # optional: relative to cwd if resolvable
  sha256: "abc123..."                # SHA-256 hex of normalized transcript bytes
  char_count: 47291
  format: txt                        # txt | json | stdin
```

| Field | Source function | Notes |
|-------|----------------|-------|
| `path` | CLI argument | `"-"` for stdin → store `"stdin"` |
| `sha256` | **new:** `hash_transcript(text)` | Normalize: strip trailing whitespace, UTF-8 encode |
| `char_count` | `len(transcript)` | Same as `transcript_chars` in session result |
| `format` | `Path.suffix` or `"stdin"` | |

**Non-goal for v1:** embedding full transcript in checkpoint. Store hash + path only. Re-extraction requires source file still present at `path`.

---

### `checkpoint.pipeline`

Metadata describing how extraction ran. Maps directly to `run_continuator()` result fields `chunking`, `chunk_selection`, and ranker audit.

```yaml
pipeline:
  baseline: v10-050+repair+continuation_export_v2_frontier+explain_v1
  memory_model: v10
  archetype: mixed
  ranker:
    strategy: approach_b_v1          # or "full" when all chunks selected
    k: 5
    total_chunks: 14
    selected_indices: [0, 3, 7, 11, 13]
    locked_indices: [12, 13]
    changepoints_pelt: [4, 9]        # optional audit subset
  chunking:
    strategy: paragraph_chunk_overlap
    chunk_count: 14
    chunk_audit:                     # passthrough from _chunk_transcript_for_extraction
      target_chars: 6000
      overlap_chars: 500
  frontier:
    cutoff_index: 12
    band_size: 2
    indices: [12, 13]
    selected_in_frontier: [11, 13]   # intersection of selected_indices and frontier.indices
  chunk_extractions:                 # per-chunk V10 outputs (selected indices only)
    - chunk_index: 0
      input_chars: 5842
      parse_ok: true
      output: { ... }                # record_to_extraction_output() dict
    - chunk_index: 3
      input_chars: 6011
      parse_ok: true
      output: { ... }
```

| Field | Source function / result key |
|-------|----------------------------|
| `baseline` | `result["product_baseline"]` |
| `memory_model` | always `"v10"` for product |
| `archetype` | `result["archetype"]` |
| `ranker.*` | `rank_chunks()` return + `result["chunk_selection"]` |
| `chunking.*` | `all_transcript_chunks()` → `chunk_meta` |
| `frontier.*` | `frontier_cutoff_index()`, `frontier_band_size()`, `inspect_conversation()` pattern |
| `chunk_extractions` | `v10_rows` from `extract_chunks_at_indices()` — each `output` via `record_to_extraction_output()` |

**Ranker audit verbosity:** v1 stores `changepoints_pelt` and `locked_indices` by default. Full displacement/curvature arrays available with `--verbose` checkpoint save (stored under `ranker.audit_full`).

---

### `checkpoint.state`

Aggregated structured V10 state — the semantic core of the checkpoint. This is the **merged** view (History + Frontier), not per-chunk raw output.

```yaml
state:
  project_title: "Neck Refactor"
  objective:                         # list[str] — frontier-first objective bullets
    - "Complete Fetch API module"
  current_state: "Implementing error handling in fetch wrapper."
  completed_work:                    # list[str] — aggregated across all chunks
    - "Set up project structure"
  active_problems:                   # list[str] — frontier band only, filtered
    - "CORS errors on local dev server"
  resolved_problems:                 # list[str]
    - "Module import path confusion"
  constraints:                       # list[str] — aggregated across all chunks
    - "Use TypeScript strict mode"
  continuation_context: ""           # str — frontier terminal delta (may be empty when folded into current_state)
  next_action: "Fix CORS configuration in vite.config.ts"
  closure_detected: false
```

| Field | Derivation (reuse existing functions) |
|-------|--------------------------------------|
| `project_title` | `_project_title(states, label=label)` from `continuation_export_v2_frontier` |
| `objective` | `_listify` + split of `_frontier_objective(frontier, history, ...)` output |
| `current_state` | `_terminal_position(terminal)` + `_conversation_frontier_hints()` overrides |
| `completed_work` | `_aggregate_list_field(states, "completed_work")` |
| `active_problems` | `filter_superseded_actives(_aggregate_list_field(frontier, "active_problems"), ...)` |
| `resolved_problems` | `_aggregate_list_field(frontier, "resolved_problems")` |
| `constraints` | `_aggregate_list_field(states, "constraints")` |
| `continuation_context` | terminal chunk `continuation_context` field |
| `next_action` | `_derive_frontier_next_action(...)` |
| `closure_detected` | `continuation_closure_detected(terminal, conversation)` |

**New module required:** `checkpoint_state_v1.py` with `aggregate_checkpoint_state(chunk_outputs, *, conversation, label, total_chunks) -> dict` — thin wrapper calling the private helpers above. No new model logic.

**V9 recall fields** (`topic`, `summary`, `important_facts`, etc.) are stored inside each `pipeline.chunk_extractions[].output` but omitted from top-level `state` in v1. Add `state.recall` in v2 if needed.

---

### `checkpoint.cached_exports`

Pre-rendered text outputs. Avoids re-running LoRA or export formatters on read.

```yaml
cached_exports:
  briefing: |
    ## PROJECT
    ...
  explain: |
    OVERVIEW
    ...
  claude: |
    Continue this conversation...
  chatgpt: |
    # Conversation handoff...
  gemini: |
    You are picking up...
  markdown: |
    # AI Handoff — neck
  v10_copy_paste: |
    === CHUNK 1/5 (5842 chars) ===
    { ... json ... }
```

| Key | Source function | Session result key |
|-----|----------------|-------------------|
| `briefing` | `generate_continuation_briefing_frontier()` | `continuation_briefing` |
| `explain` | `generate_conversation_explanation()` | `conversation_explanation` |
| `claude` | `format_for_claude()` | `exports.claude` |
| `chatgpt` | `format_for_chatgpt()` | `exports.chatgpt` |
| `gemini` | `format_for_gemini()` | `exports.gemini` |
| `markdown` | `format_generic_markdown()` | `exports.markdown` |
| `v10_copy_paste` | `format_copy_paste_outputs()` | `exports.v10_copy_paste` |

All values are UTF-8 strings. Use YAML literal block scalars (`|`) for multiline text.

---

### `checkpoint.stats` *(optional but recommended)*

Derived metrics for list/show UX and compression ratio display.

```yaml
stats:
  briefing_words: 142
  explain_words: 118
  extraction_parse_rate: 1.0          # fraction of chunk_extractions with parse_ok
  compression_ratio: 38.2             # source.char_count / len(briefing)
  runtime_seconds: 12.4               # wall time for full pipeline
```

| Field | Source |
|-------|--------|
| `briefing_words` | `_word_count()` in `handoff_evaluation_v1` |
| `explain_words` | same |
| `extraction_parse_rate` | `aggregate_metrics()` |
| `compression_ratio` | `char_count / len(cached_exports.briefing)` |
| `runtime_seconds` | `result["_runtime_seconds"]` from `run_continuation()` |

---

## JSON equivalent

`continuator checkpoint FILE --json -o neck.json` writes the same structure as JSON (no YAML block scalars). `format_version` remains integer `1`.

---

## Validation rules

On write:

1. `format_version` must be `1`.
2. `source.sha256` must match hash of input transcript.
3. `pipeline.chunk_extractions` must have one entry per `ranker.selected_indices` entry.
4. `cached_exports.briefing` must be non-empty (checkpoint save fails if extraction produced empty briefing — same as `continue` today).
5. `state.next_action` must be non-empty string (same rubric as `briefing_quality()`).

On read:

1. Reject files with unknown `format_version`.
2. Warn (don't fail) if `source.path` missing but hash matches nothing locally.

---

## Minimal example

```yaml
checkpoint:
  format_version: 1
  id: a3f2c891
  project: neck
  message: ""
  created_at: "2026-06-21T14:30:00+00:00"
  label: neck
  source:
    path: /Users/me/examples/neck.txt
    sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    char_count: 12400
    format: txt
  pipeline:
    baseline: v10-050+repair+continuation_export_v2_frontier+explain_v1
    memory_model: v10
    archetype: mixed
    ranker:
      strategy: approach_b_v1
      k: 3
      total_chunks: 6
      selected_indices: [0, 3, 5]
      locked_indices: [5]
    chunking:
      strategy: paragraph_chunk_overlap
      chunk_count: 6
    frontier:
      cutoff_index: 4
      band_size: 2
      indices: [4, 5]
      selected_in_frontier: [3, 5]
    chunk_extractions:
      - chunk_index: 0
        input_chars: 5800
        parse_ok: true
        output:
          objective: ["Learn Fetch API"]
          current_state: "Starting module 3."
          completed_work: ["Modules 1-2"]
          active_problems: []
          resolved_problems: []
          constraints: []
          continuation_context: ""
          parse_ok: true
          memory_model: v10
  state:
    project_title: neck
    objective: ["Learn Fetch API"]
    current_state: "Working through Fetch API exercises."
    completed_work: ["Modules 1-2"]
    active_problems: ["Unclear error handling pattern"]
    resolved_problems: []
    constraints: []
    continuation_context: ""
    next_action: "Continue Fetch API module from error handling section."
    closure_detected: false
  cached_exports:
    briefing: |
      ## PROJECT
      ...
    explain: |
      OVERVIEW
      ...
    claude: |
      Continue this conversation...
    chatgpt: ""
    gemini: ""
    markdown: ""
    v10_copy_paste: ""
  stats:
    briefing_words: 98
    explain_words: 85
    extraction_parse_rate: 1.0
    compression_ratio: 28.5
    runtime_seconds: 8.1
```

---

## Explicit non-goals (v1)

- Parent checkpoint / lineage links (Phase 3)
- Embedded source transcript
- Incremental merge metadata
- Compression tiers
- Platform-specific resume wrappers beyond cached exports

---

## Reader / writer API (planned)

| Function | Module | Purpose |
|----------|--------|---------|
| `build_checkpoint_record(session_result, *, source_meta) -> dict` | `checkpoint_record_v1.py` | Map `run_continuator()` output → schema |
| `validate_checkpoint_record(record) -> list[str]` | `checkpoint_record_v1.py` | Return validation errors |
| `write_checkpoint(record, path)` | `checkpoint_store_v1.py` | YAML serialize |
| `read_checkpoint(path) -> dict` | `checkpoint_store_v1.py` | YAML deserialize + validate |
| `aggregate_checkpoint_state(...)` | `checkpoint_state_v1.py` | Build `state` section from chunk outputs |
