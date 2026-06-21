# Phase 2 Implementation Specification

**Status:** Plan only — no extension work, no V10 changes, no training data changes  
**Source of truth:** [`checkpoint_format_v2.md`](checkpoint_format_v2.md)  
**Scope:** State engine — record I/O, store, merge, resume, incremental checkpoint, local HTTP serve, benchmark gate

---

## Goals

| # | Deliverable | Success criterion |
|---|-------------|-------------------|
| 1 | `checkpoint_record_v2.py` | v2 read/write/validate; v1 migration |
| 2 | `checkpoint_store_v2.py` | Resolve, load, save `.continuator/checkpoint.yaml` |
| 3 | `continuator resume` | **No V10** when `cached_exports.briefing` present |
| 4 | `checkpoint --update` | Append-only delta; skip unchanged chunks |
| 5 | `checkpoint_merge_v1.py` | `frontier_wins_v1` merge policy |
| 6 | `continuator serve` | Local HTTP; model warm for future extensions |
| 7 | Incremental benchmark | Full vs update: speed + quality parity |

---

## Implementation plan (ordered workstreams)

### Workstream A — Record format (week 1)

Build the v2 data contract before commands depend on it.

1. Add `pyyaml` to `pyproject.toml` dependencies (v2 canonical serialization).
2. Implement `checkpoint_record_v2.py` — models, validate, migrate, build from session.
3. Unit tests: round-trip fixtures, v1→v2 migration, validation failures.
4. Keep `continuator/checkpoint_yaml.py` as thin re-export or deprecate writer in favor of v2.

**Gate:** Fixture yaml from `checkpoint_format_v2.md` parses and re-serializes identically (modulo timestamps).

### Workstream B — Store layer (week 1)

1. Implement `checkpoint_store_v2.py` — path resolution, atomic write, load.
2. Default layout: `.continuator/checkpoint.yaml` (cwd), legacy fallback `./checkpoints/<project>.yaml`.
3. Wire `checkpoint_store` into record module tests.

**Gate:** Save/load round-trip under `tests/fixtures/checkpoints/v2/`.

### Workstream C — Full checkpoint v2 (week 2)

Upgrade `continuator checkpoint` without incremental yet.

1. Add `build_record_from_session(result, *, source_meta) -> CheckpointRecord` in `checkpoint_record_v2.py`.
2. Populate **standard tier** minimum: `source`, `engine`, `state`, `cached_exports`, `stats`.
3. Populate **full tier** when `--full` (default for terminal): `pipeline.chunk_extractions`, ranker audit.
4. Change default output path to `.continuator/checkpoint.yaml` (keep `--output` override).
5. `--json` emits v2 JSON envelope.

**Gate:** `continuator checkpoint examples/neck.txt` writes valid v2 file; `continue` behavior unchanged.

### Workstream D — Resume (week 2)

1. Implement `continuator/commands/resume_cmd.py`.
2. Implement `continuator/platform/resume.py` — load record, pick export, no LoRA path.
3. `--refresh` delegates to existing `run_continuation()` + overwrite store.

**Gate:** `continuator resume` < 500ms on fixture with `cached_exports.briefing`; zero calls to `memory_extractor` in default path (mock/spy test).

### Workstream E — Merge engine (week 3)

1. Implement `checkpoint_merge_v1.py`.
2. Implement append-only detection + chunk content-hash cache reuse.
3. Implement `run_incremental_update()` orchestrator in `continuator/platform/extract.py`.
4. Add `checkpoint --update` flag.

**Gate:** Benchmark corpus incremental ≥3× faster; quality parity ≥95% (see Benchmark Design).

### Workstream F — Serve (week 3–4)

1. Implement `continuator/commands/serve_cmd.py` + `continuator/platform/http_server.py`.
2. Endpoints mirror CLI: extract, checkpoint, resume, health.
3. Single process loads MLX/transformers once at startup.

**Gate:** Second `/extract` request faster than cold CLI spawn; health returns baseline version.

### Workstream G — Benchmark & docs (week 4)

1. `continuator benchmark-incremental` or extend `benchmark` with `--incremental` mode.
2. Report JSON + markdown summary.
3. Update README Phase 2 section.

---

## Architecture (Phase 2)

```
┌─────────────────────────────────────────────────────────────────┐
│  CLI: checkpoint | resume | serve                               │
└────────────┬───────────────────────┬────────────────────────────┘
             │                       │
┌────────────▼──────────┐  ┌─────────▼──────────┐
│ continuator/platform/ │  │ checkpoint_store_v2 │
│  extract.py           │  │  resolve/load/save  │
│  resume.py            │  └─────────┬──────────┘
│  http_server.py       │            │
└────────────┬──────────┘  ┌─────────▼──────────┐
             │             │ checkpoint_record_v2│
             │             │  build/parse/validate│
             └────────────►└─────────┬──────────┘
                                       │
                          ┌────────────▼────────────┐
                          │ checkpoint_merge_v1     │
                          │  frontier_wins_v1       │
                          └────────────┬────────────┘
                                       │
                          ┌────────────▼────────────┐
                          │ continuator_engine/     │  (unchanged)
                          │  run_continuator()      │
                          │  build_checkpoint_state │
                          └─────────────────────────┘
```

**Invariant:** V10 LoRA is only invoked from `extract.py` full/incremental paths — never from `resume.py`.

---

## Module breakdown

### 1. `continuator_engine/checkpoint_record_v2.py` (~280 LOC)

**Responsibility:** Canonical v2 `CheckpointRecord` type; parse/serialize; build from pipeline session; migrate v1.

| Function / type | Purpose |
|-----------------|---------|
| `CheckpointRecord` | TypedDict or Pydantic model matching `checkpoint_format_v2.md` |
| `FORMAT_VERSION = 2` | Constant |
| `hash_transcript(text) -> str` | SHA-256 hex, normalized strip |
| `generate_checkpoint_id(project, created_at, sha256) -> str` | 8-char hex id |
| `build_record_from_session(session, *, source_meta, tier) -> CheckpointRecord` | Map `run_continuator()` result → v2 |
| `build_cached_exports(session, state) -> dict` | briefing, explain, claude, chatgpt, gemini, markdown |
| `build_pipeline_section(session, v10_rows) -> dict` | chunking, ranker, frontier, chunk_extractions |
| `parse_checkpoint_file(path) -> CheckpointRecord` | YAML/JSON load + validate |
| `serialize_checkpoint(record, fmt="yaml") -> str` | Dump |
| `validate_record(record) -> list[str]` | Structural + state rules from v2 spec |
| `migrate_v1_flat(data: dict) -> CheckpointRecord` | Validation experiment 7-field yaml |
| `state_to_checkpoint_state(state: dict) -> CheckpointState` | Bridge to existing renderers |

**`build_record_from_session` mapping:**

| v2 field | Session key |
|----------|-------------|
| `state.*` | `checkpoint_state` |
| `cached_exports.briefing` | `continuation_briefing` |
| `cached_exports.explain` | `conversation_explanation` |
| `cached_exports.claude/...` | `exports.*` |
| `engine.baseline` | `product_baseline` |
| `pipeline` | `chunking`, `chunk_selection`, `v10_rows` (new: attach in `_finalize_continuator`) |
| `stats.runtime_seconds` | `_runtime_seconds` |

**Minimal `_finalize_continuator` extension (not V10):** Add `v10_rows` and `rank_audit` to session result dict for incremental cache — ~10 LOC, additive only.

### 2. `continuator_engine/checkpoint_store_v2.py` (~160 LOC)

**Responsibility:** Filesystem layout; atomic I/O; checkpoint discovery.

| Function | Purpose |
|----------|---------|
| `default_checkpoint_root(cwd) -> Path` | `.continuator/` |
| `resolve_checkpoint_path(project, *, cwd, explicit) -> Path` | `.continuator/checkpoint.yaml` or legacy |
| `legacy_checkpoint_path(project) -> Path` | `./checkpoints/<project>.yaml` |
| `load_checkpoint(path=None, project=None) -> CheckpointRecord \| None` | Load + migrate |
| `save_checkpoint(record, path=None) -> Path` | Atomic write tmp→rename, mode 0600 |
| `find_checkpoint_for_update(project, cwd) -> CheckpointRecord \| None` | For `--update` |

**Path precedence:**

```
1. --output PATH (explicit)
2. .continuator/checkpoint.yaml (cwd)
3. ./checkpoints/<project>.yaml (legacy, read-only fallback for --update)
4. ~/.continuator/projects/<project>/checkpoint.yaml (optional env override)
```

### 3. `continuator_engine/checkpoint_merge_v1.py` (~220 LOC)

**Responsibility:** Incremental merge at chunk-output and state level.

| Function | Purpose |
|----------|---------|
| `MERGE_STRATEGY = "frontier_wins_v1"` | Constant |
| `is_append_only(prior_text, new_text) -> bool` | `normalize(new).startswith(normalize(prior))` |
| `detect_transcript_delta(prior, new) -> str` | Return suffix only |
| `chunk_content_hash(chunk_text) -> str` | Cache key per chunk |
| `merge_chunk_extractions(base, delta, *, new_chunks) -> list` | By index + content hash reuse |
| `merge_v10_outputs(cached_rows, new_rows) -> list` | Sorted by chunk_index, dedupe by index |
| `merge_checkpoint_records(base, delta_record) -> CheckpointRecord` | Lineage + state merge |
| `merge_state_frontier_wins(base_state, delta_state, *, merged_outputs, conversation) -> dict` | Field rules below |

**`frontier_wins_v1` state merge** (re-invoke existing helpers where possible):

| Field | Implementation |
|-------|----------------|
| `objective` | `_union_dedupe(delta.objective + base.objective)` |
| `current_state` | `delta.current_state` if non-empty else `base` |
| `completed_work` | `_aggregate_list_field(merged_outputs, "completed_work")` |
| `active_problems` | Re-run `filter_superseded_actives` on delta frontier only |
| `constraints` | `_aggregate_list_field(merged_outputs, "constraints")` |
| `next_action` | Re-run `_derive_frontier_next_action` on delta frontier outputs + full `conversation` |
| `closure_detected` | delta wins |
| `project_title` | delta wins |

**Preferred path:** After merging `v10_outputs`, call `build_checkpoint_state(merged_outputs, conversation=full_new_text, ...)` — same as full extract. This reuses production aggregation without duplicating field logic. `merge_state_frontier_wins` becomes a thin wrapper or is replaced by rebuild-from-outputs.

**Chunk skip rule (only process new content):**

```python
for i, chunk_text in enumerate(chunks):
    h = chunk_content_hash(chunk_text)
    if i in cached_by_index and cached_by_index[i].content_hash == h:
        reuse cached v10 output
    else:
        extract with V10
```

Only changed/new chunks hit LoRA.

### 4. `continuator/commands/resume_cmd.py` (~120 LOC)

```bash
continuator resume [TARGET] [OPTIONS]

TARGET resolution:
  1. explicit file path
  2. .continuator/checkpoint.yaml
  3. ./checkpoints/<project>.yaml
  4. latest in cwd

Options:
  --format briefing|explain|state|claude|chatgpt|gemini|markdown  (default: briefing)
  --refresh              # re-run V10 from source.path; rewrite checkpoint
  -o FILE
  -q / -v
```

**Default path (no V10):**

```python
record = load_checkpoint(target)
text = record["cached_exports"][format_key]  # briefing default
if not text:
    if format == "briefing" and record.get("state"):
        text = render_briefing_from_checkpoint_state(state_to_checkpoint_state(record["state"]))
    else:
        fail("missing cached export; run with --refresh")
```

**`--refresh` path:** `read_transcript(source.path)` → `run_continuation()` → `save_checkpoint(build_record_from_session(...))` → render.

### 5. `continuator/commands/checkpoint_cmd.py` (modify ~80 LOC delta)

New flags:

```bash
continuator checkpoint FILE [--update] [--message MSG] [--full|--minimal]
                           [-o PATH] [--json] [--name PROJECT]
```

| Mode | Behavior |
|------|----------|
| Default | Full extract → v2 standard/full tier → save |
| `--update` | Load existing → append check → incremental extract → merge → save |
| `--minimal` | State + project only (validation compat) |
| `--full` | Include `pipeline.chunk_extractions` (default for terminal) |

**`--update` algorithm:**

```
1. transcript = read(FILE)
2. prior = find_checkpoint_for_update(project)
3. if not prior: fall through to full checkpoint (same as today)
4. if not is_append_only(prior.source snapshot, transcript):
     error "Transcript changed non-append-only; use --refresh or full checkpoint"
5. merged_rows = incremental_extract(transcript, prior.pipeline.chunk_extractions)
6. session = finalize_from_merged_rows(...)  # or run_continuator incremental API
7. record = build_record_from_session(session, lineage={parent_id, merge_strategy, delta})
8. save_checkpoint(record)
```

**Snapshot for append check:** Store `source.char_count` + optional `source.prefix_sha256` or re-read `source.path` if still exists.

### 6. `continuator serve` (~200 LOC)

**Files:**

- `continuator/commands/serve_cmd.py`
- `continuator/platform/http_server.py`

```bash
continuator serve [--port 8741] [--host 127.0.0.1]
```

| Endpoint | Method | Body | Response |
|----------|--------|------|----------|
| `/health` | GET | — | `{status, baseline, model_loaded}` |
| `/v1/extract` | POST | `{transcript, project, label?}` | `CheckpointRecord` JSON |
| `/v1/checkpoint` | POST | `{transcript, project, update?: bool}` | `{path, record}` |
| `/v1/resume` | POST | `{project?, path?, format?}` | `{text}` — **cached only, no V10** |
| `/v1/resume/refresh` | POST | `{project, ...}` | runs V10 |

**Implementation:** `http.server.ThreadingHTTPServer` or `stdlib` only for Phase 2 (no FastAPI dep). Model loaded in `ensure_runtime()` at server start.

**Security:** Bind `127.0.0.1` only; document in help.

### 7. `continuator/platform/extract.py` (~180 LOC)

Orchestration shared by CLI, serve, and benchmark:

| Function | Purpose |
|----------|---------|
| `extract_full(transcript, **opts) -> CheckpointRecord` | `run_continuation` → `build_record_from_session` |
| `extract_incremental(transcript, prior, **opts) -> CheckpointRecord` | merge path |
| `incremental_extract_rows(transcript, prior_pipeline) -> list` | chunk hash skip logic |

### 8. Tests (est. ~400 LOC)

| File | Coverage |
|------|----------|
| `tests/test_checkpoint_record_v2.py` | parse, serialize, migrate, validate |
| `tests/test_checkpoint_store_v2.py` | atomic write, path resolve |
| `tests/test_checkpoint_merge_v1.py` | append detection, chunk reuse, merge |
| `tests/test_resume_cmd.py` | cached resume no V10 (mock patch) |
| `tests/test_incremental_benchmark.py` | parity rubric on fixtures |

---

## Migration strategy

### v1 validation yaml → v2

**Reader (`parse_checkpoint_file`):**

```python
raw = yaml.safe_load(path)
if isinstance(raw, dict) and "checkpoint" in raw:
    return validate_v2(raw["checkpoint"])
if isinstance(raw, dict) and "project" in raw and "objective" in raw:
    return migrate_v1_flat(raw)  # flat 7-field experiment format
raise ValueError("unrecognized checkpoint format")
```

**`migrate_v1_flat`:**

- Set `format_version: 2`, generate `id`, `created_at` = now
- `source.kind` = `"file"`, `sha256` = empty (unknown), `char_count` = 0
- `engine` = current product defaults
- `state` = map flat fields; `project_title` = `project`
- `cached_exports` = **empty** — resume requires `--refresh` once for migrated files
- Log warning: "Migrated v1 checkpoint; run checkpoint --refresh to populate cached_exports"

### CLI output path migration

| Version | Default write path |
|---------|-------------------|
| v0.1 validation | `./checkpoints/<project>.yaml` |
| Phase 2 | `.continuator/checkpoint.yaml` |

**Compatibility:**

- `resume` reads both locations (store resolver).
- `checkpoint` writes v2 to `.continuator/` by default.
- `--output` preserves explicit path.
- No auto-delete of legacy `./checkpoints/` files.

### Session JSON (`continue --json`)

Additive fields only: `checkpoint_record` (v2 envelope). Existing keys unchanged.

### Dependency migration

Add to `pyproject.toml`:

```toml
dependencies = [
  ...
  "pyyaml>=6.0",
]
```

Retire hand-written YAML emitter in `checkpoint_yaml.py` for v2 writes; keep `validate_checkpoint_state` moved to `checkpoint_record_v2` or re-export.

---

## `continuator resume` — no V10 guarantee

| Path | V10 invoked? | Source |
|------|:------------:|--------|
| `resume` default | **No** | `cached_exports.briefing` |
| `resume --format explain` | **No** | `cached_exports.explain` |
| `resume --format claude` | **No** | `cached_exports.claude` |
| `resume --format state` | **No** | serialize `record.state` |
| `resume --refresh` | Yes | full `run_continuation` |
| Migrated v1 without cache | Yes (or fail with message) | `--refresh` required |

**Test:** Patch `memory_extractor_v1._extract_single_chunk` to raise if called; `continuator resume` must pass.

**Performance target:** p99 < 500ms for load + print briefing (exclude terminal render).

---

## `checkpoint --update` — only new content

### Append-only detection

```python
def is_append_only(prior_text: str, new_text: str) -> bool:
    p = normalize(prior_text)
    n = normalize(new_text)
    return n.startswith(p) and len(n) > len(p)
```

If user edits middle of file: **reject** with message to run full checkpoint or `resume --refresh`.

**Optional:** Store full prior transcript hash; on update re-read `source.path` and compare prefix hash of first `prior.char_count` chars.

### Chunk-level skip (no V10 for unchanged chunks)

1. Re-chunk **full** new transcript (chunk boundaries may shift — content hash handles this).
2. For each chunk index `i`, hash chunk text.
3. If `(i, hash)` matches entry in `prior.pipeline.chunk_extractions` → reuse `output`.
4. Else → queue for V10 extraction.
5. Merge all outputs → `build_checkpoint_state` on full conversation text.

**Expected savings:** On 2× grown transcript, ~50% of chunks unchanged at prefix → ~50% fewer LoRA calls; ranker+embed still run (cheap vs LoRA).

### Lineage metadata written

```yaml
lineage:
  parent_id: <prior.id>
  merge_strategy: frontier_wins_v1
  delta:
    chars_added: <int>
    chunks_extracted: [<indices>]
    chunks_reused: [<indices>]
```

---

## Benchmark design

### Command

```bash
continuator benchmark-incremental DIR [--report FILE] [--mock]
# or
continuator benchmark DIR --compare-incremental
```

### Corpus

| Sample | Source | Why |
|--------|--------|-----|
| Aman/tutorial | training cache / examples | Multi-chunk; stale quiz stress |
| Kafka | benchmark cache | Medium N |
| Superlong | benchmark cache | Large N — speedup signal |
| neck.txt | examples | Short smoke |
| Synthetic append | generated | Controlled 1× → 2× growth |

**Synthetic append fixture builder** (test helper):

```python
def append_transcript(base: str, suffix: str) -> str:
    return base.rstrip() + "\n\n" + suffix.strip()
```

Use recorded suffix from benchmark transcripts (last 20% chars) to simulate realistic growth.

### Metrics per sample

| Metric | Full | Incremental | Pass threshold |
|--------|------|-------------|----------------|
| `wall_seconds` | T_full | T_update | T_update ≤ T_full / 3 |
| `lora_calls` | N_chunks | N_extracted | N_extracted < N_chunks |
| `briefing_quality` | rubric score | rubric score | ≥ 95% of full |
| `state_field_overlap` | — | Jaccard on completed_work, active_problems | ≥ 0.90 |
| `next_action_match` | — | exact or semantic overlap | ≥ 0.95 |
| `resume_ms` | — | cached resume latency | < 500ms |

### Procedure

```
For each sample S with append suffix S':
  1. T0 = full checkpoint(S)           → record R0
  2. T1 = full checkpoint(S + S')      → record R1_full (quality baseline)
  3. T2 = checkpoint(S + S', --update)  → record R2_inc (after R0)
  4. Compare quality(R2_inc, R1_full)
  5. Compare wall time T2 vs T1
  6. Resume(R2_inc) — verify no V10, measure latency
```

### Report format (`benchmark_incremental_report.json`)

```json
{
  "generated_at": "...",
  "samples": [
    {
      "name": "kafka",
      "full_seconds": 64.2,
      "incremental_seconds": 18.1,
      "speedup": 3.55,
      "lora_calls_full": 5,
      "lora_calls_incremental": 2,
      "quality_ratio": 0.98,
      "next_action_match": true,
      "resume_ms": 12,
      "verdict": "pass"
    }
  ],
  "summary": {
    "pass_count": 4,
    "total": 5,
    "avg_speedup": 3.2,
    "avg_quality_ratio": 0.96
  }
}
```

### CI strategy

- **PR gate:** `MEMORY_EXTRACTOR_BACKEND=mock` — test merge logic + resume path only (~5s).
- **Nightly / manual:** real V10 on cache corpus — full benchmark report.

### Quality rubric (reuse)

- `briefing_quality()` from `continuator/pipeline.py`
- Add `state_parity(base_state, inc_state)` — field-level comparison helper in `checkpoint_merge_v1.py`

---

## Files to create / modify

### New files

| Path | LOC est. |
|------|----------|
| `continuator_engine/checkpoint_record_v2.py` | 280 |
| `continuator_engine/checkpoint_store_v2.py` | 160 |
| `continuator_engine/checkpoint_merge_v1.py` | 220 |
| `continuator/platform/extract.py` | 180 |
| `continuator/platform/resume.py` | 80 |
| `continuator/platform/http_server.py` | 150 |
| `continuator/commands/resume_cmd.py` | 120 |
| `continuator/commands/serve_cmd.py` | 60 |
| `continuator/commands/benchmark_incremental_cmd.py` | 150 |
| `tests/test_checkpoint_record_v2.py` | 150 |
| `tests/test_checkpoint_store_v2.py` | 80 |
| `tests/test_checkpoint_merge_v1.py` | 120 |
| `tests/test_resume_no_v10.py` | 60 |
| `tests/fixtures/checkpoints/v2/standard.yaml` | fixture |

### Modified files

| Path | Change | LOC est. |
|------|--------|----------|
| `continuator/commands/checkpoint_cmd.py` | v2 save, `--update`, path | +80 |
| `continuator/cli.py` | register resume, serve, benchmark-incremental | +15 |
| `continuator_engine/handoff_evaluation_v1.py` | expose `v10_rows`, `rank_audit` in session | +15 |
| `pyproject.toml` | add `pyyaml` | +1 |
| `continuator/checkpoint_yaml.py` | deprecate writer; re-export validate | -40 net |
| `README.md` | Phase 2 commands | +30 |

**Total estimate:** ~1,650 LOC (incl. tests)

---

## Explicit non-goals (Phase 2)

- Cursor / VS Code / browser extensions
- MCP server (Phase 4)
- Cloud sync
- V10 / training changes
- `checkpoint list` / `diff` (defer)
- Compression `minimal` tier generation (optional stub in `cached_exports` only if trivial)

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Chunk boundary shift breaks hash reuse | Medium | Less speedup | Content-hash match still skips unchanged text blocks |
| Merge quality < 95% | Medium | Bad updates | Rebuild state via `build_checkpoint_state(merged_outputs)` not manual field merge |
| Migrated v1 can't resume without refresh | High | UX | Clear warning on migrate |
| `serve` model memory pressure | Low | OOM on small machines | Document RAM; lazy load option |
| PyYAML new dep | Low | install friction | stdlib-only read fallback optional |

---

## Acceptance checklist

- [ ] `checkpoint_record_v2` round-trips `checkpoint_format_v2.md` example
- [ ] v1 flat yaml migrates and re-saves as v2
- [ ] `continuator resume` prints briefing without loading LoRA
- [ ] `continuator resume --refresh` re-runs pipeline
- [ ] `continuator checkpoint --update` on append-only transcript skips cached chunks
- [ ] `continuator serve` `/v1/resume` returns cached briefing
- [ ] Benchmark report: ≥3× speedup and ≥95% quality on ≥4/5 samples
- [ ] `continuator continue` output unchanged (regression test)

---

## Related documents

- [`checkpoint_format_v2.md`](checkpoint_format_v2.md) — schema
- [`integration_roadmap.md`](integration_roadmap.md) — Phase 2 context
- [`platform_architecture.md`](platform_architecture.md) — state engine layer
- [`phase2_implementation_plan.md`](phase2_implementation_plan.md) — superseded Phase 2 full platform plan (reference only)
