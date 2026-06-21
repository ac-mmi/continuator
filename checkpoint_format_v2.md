# Checkpoint Format v2

**Status:** Design only  
**Replaces:** Validation experiment minimal yaml (7 fields, no metadata)  
**Goal:** One portable `checkpoint.yaml` that works across terminal, Cursor, VS Code, Claude Code, browser, and platform exports.

---

## Design principles

1. **State is authoritative** — `state` block is the source of truth; exports are cached renderings.
2. **Self-contained resume** — a checkpoint alone must be enough to resume (with optional source refresh).
3. **Forward compatible** — `format_version: 2`; readers reject unknown major versions.
4. **Human-readable** — YAML default; JSON supported for SDK/API.
5. **Privacy-aware** — no embedded full transcript by default; hash + optional external reference.

---

## File identity

| Property | Value |
|----------|-------|
| Filename | `checkpoint.yaml` (default) or `<project>-<id>.yaml` |
| MIME | `application/x-yaml` or `text/yaml` |
| Extension | `.yaml` / `.yml` / `.json` |

### Standard locations

| Context | Path |
|---------|------|
| Workspace (recommended) | `<repo>/.continuator/checkpoint.yaml` |
| Terminal (legacy validation) | `./checkpoints/<project>.yaml` |
| Global fallback | `~/.continuator/projects/<slug>/checkpoint.yaml` |
| Browser extension | Download + `chrome.storage.local` copy |

---

## Top-level schema

```yaml
checkpoint:
  format_version: 2
  id: a3f2c891
  project: neck-refactor
  label: "Neck Refactor"
  message: ""                    # optional user note
  created_at: "2026-06-21T14:30:00+00:00"
  updated_at: "2026-06-21T16:45:00+00:00"

  source:
    kind: file                   # file | stdin | cursor | vscode | browser | claude_code
    path: /path/to/chat.txt      # optional
    platform: chatgpt            # optional: chatgpt | claude | gemini | grok | cursor | unknown
    conversation_id: ""          # optional host-specific ID
    sha256: "abc123..."
    char_count: 47291
    message_count: 142           # optional — for incremental merge

  engine:
    baseline: v10-050+repair+continuation_export_v2_frontier
    memory_model: v10
    archetype: mixed             # tutorial | coding | project | ...

  state:
  pipeline:                      # optional — for refresh/debug
  cached_exports:                # optional — skip re-render on resume
  lineage:                       # optional — Phase 2 incremental
  stats:                         # optional
```

---

## `checkpoint.state` (required)

The six user-facing fields plus internal display helper. Maps 1:1 to `CheckpointState` in code.

```yaml
state:
  project_title: "Neck Refactor"
  objective:
    - "Complete Fetch API module"
    - "Finish error handling exercises"
  current_state: "Implementing fetch wrapper; last example uses .catch()."
  completed_work:
    - "Completed modules 1-2"
    - "Set up local dev environment"
  active_problems:
    - "CORS errors on local dev server"
  constraints:
    - "TypeScript strict mode"
  next_action: "Fix CORS configuration in vite.config.ts"
  closure_detected: false        # optional bool
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `project_title` | string | yes | Display title |
| `objective` | list[string] | yes | May be empty list |
| `current_state` | string | yes | Frontier position |
| `completed_work` | list[string] | yes | Chronological dedupe |
| `active_problems` | list[string] | yes | Frontier-filtered |
| `constraints` | list[string] | yes | May be empty |
| `next_action` | string | yes | Must be non-empty for valid checkpoint |
| `closure_detected` | bool | no | Thread resolved signal |

**Not in portable yaml:** `objective_display` (internal briefing helper) — reconstructed on read if needed.

### Validation rules

- `next_action` non-empty
- `current_state` non-empty OR `completed_work` non-empty
- `objective` non-empty for `tier: standard` checkpoints (warn only for minimal)

---

## `checkpoint.source` (required)

```yaml
source:
  kind: browser
  path: ""
  platform: claude
  conversation_id: "6a339d31-3014-83e8-9db8-30cafa82abb8"
  sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  char_count: 47291
  message_count: 87
```

| `kind` | Set by |
|--------|--------|
| `file` | CLI `continuator checkpoint file.txt` |
| `stdin` | CLI pipe |
| `cursor` | Cursor extension |
| `vscode` | VS Code extension |
| `browser` | Browser extension |
| `claude_code` | Claude Code MCP |

**Incremental merge (Phase 2):** `message_count` and `sha256` detect whether source grew since last checkpoint.

---

## `checkpoint.engine` (required)

```yaml
engine:
  baseline: v10-050+repair+continuation_export_v2_frontier+explain_v1
  memory_model: v10
  archetype: tutorial
  extractor_backend: mlx       # mlx | transformers | mock
```

Enables resume compatibility checks: warn if checkpoint was built with different baseline.

---

## `checkpoint.pipeline` (optional)

Included when full refresh is possible. Omitted in minimal/browser checkpoints to reduce size.

```yaml
pipeline:
  chunking:
    strategy: paragraph_chunk_overlap
    chunk_count: 14
  ranker:
    strategy: approach_b_v1
    selected_indices: [0, 3, 7, 11, 13]
  frontier:
    cutoff_index: 12
    indices: [12, 13]
  chunk_extractions:           # only if --include-chunks
    - chunk_index: 0
      parse_ok: true
      output: { ... }          # V10 per-chunk JSON
```

**Default for extensions:** omit `chunk_extractions` — state + source hash is enough for resume.

---

## `checkpoint.cached_exports` (optional, recommended)

Pre-rendered views. Enables instant resume without re-running renderers.

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
    # Conversation handoff
    ...
  gemini: |
    You are picking up...
  markdown: |
    # AI Handoff
  minimal: |                   # Phase 2 compression tier
    Objective: ...
    Next Action: ...
```

| Key | Consumer |
|-----|----------|
| `briefing` | Continue, Resume default |
| `explain` | Explain view |
| `claude` | Claude paste / Cursor inject |
| `chatgpt` | ChatGPT new chat |
| `gemini` | Gemini new chat |
| `markdown` | Generic |
| `minimal` | Tight context windows |

**Rule:** If `cached_exports.briefing` present, resume uses cache unless `--refresh`.

---

## `checkpoint.lineage` (optional, Phase 2)

Incremental checkpointing metadata.

```yaml
lineage:
  parent_id: b7c1d045           # previous checkpoint id
  merge_strategy: frontier_wins_v1
  delta:
    messages_added: 12
    chars_added: 3400
    chunks_extracted: [13, 14]
  history:
    - id: a3f2c891
      created_at: "2026-06-21T14:30:00+00:00"
      message: "initial"
```

---

## `checkpoint.stats` (optional)

```yaml
stats:
  briefing_words: 142
  explain_words: 118
  compression_ratio: 38.2       # char_count / briefing_chars
  extraction_parse_rate: 1.0
  archetype_confidence: 0.85    # heuristic
  usefulness_tier: high         # high | medium | low — from archetype analysis
  runtime_seconds: 12.4
```

---

## Format tiers

Not every surface needs the full schema:

| Tier | Includes | Use case |
|------|----------|----------|
| **minimal** | `format_version`, `project`, `state.*` | Validation experiment (v1) |
| **standard** | + `source`, `engine`, `created_at` | Extensions, resume |
| **full** | + `pipeline`, `cached_exports`, `lineage`, `stats` | Terminal, debugging, offline resume |

**Migration:** Validation experiment yaml (7 fields) = **minimal tier**. Reader upgrades to standard on next save.

---

## v1 → v2 migration

Validation experiment format (today):

```yaml
project: neck
objective: [...]
current_state: ...
# ...
```

v2 wrapper:

```yaml
checkpoint:
  format_version: 2
  id: <generated>
  project: neck
  created_at: <now>
  updated_at: <now>
  source: { kind: file, sha256: ..., char_count: ... }
  engine: { baseline: ..., memory_model: v10, archetype: mixed }
  state:
    project_title: neck
    objective: [...]
    # ... all v1 fields
```

**Reader logic:**

```python
def load_checkpoint(path):
    data = yaml.safe_load(path)
    if "checkpoint" in data:
        return parse_v2(data["checkpoint"])
    # flat v1 validation format
    return wrap_v1_as_v2(data)
```

---

## Cross-surface portability matrix

| Surface | Read | Write | Resume from cache | Incremental merge |
|---------|:----:|:-----:|:-----------------:|:-----------------:|
| Terminal CLI | ✅ | ✅ | Phase 2 | Phase 2 |
| TUI | ✅ | ✅ | Phase 2 | Phase 2 |
| Cursor ext | ✅ | ✅ | ✅ | Phase 3 |
| VS Code ext | ✅ | ✅ | ✅ | Phase 3 |
| Claude Code MCP | ✅ | ✅ | ✅ | Phase 4 |
| Browser ext | ✅ | ✅ | ✅ | Phase 5 |
| ChatGPT paste | — | — | via `cached_exports.chatgpt` | — |
| Claude paste | — | — | via `cached_exports.claude` | — |
| Gemini paste | — | — | via `cached_exports.gemini` | — |

---

## JSON representation

API and MCP use identical schema as JSON:

```json
{
  "checkpoint": {
    "format_version": 2,
    "id": "a3f2c891",
    "state": { "objective": ["..."], "next_action": "..." }
  }
}
```

`continuator checkpoint --json` emits standard tier.

---

## Security & privacy

| Field | Sensitivity |
|-------|-------------|
| `state.*` | May contain conversation content |
| `cached_exports.*` | Same |
| `pipeline.chunk_extractions` | Same |
| `source.sha256` | Low |
| `source.conversation_id` | Medium — host metadata |

**Recommendations:**
- Store under `.continuator/` (add to `.gitignore` template)
- File mode `0600`
- Never commit checkpoints with secrets — document in extension onboarding

---

## Example: standard tier

```yaml
checkpoint:
  format_version: 2
  id: f4e8b012
  project: continuator-release
  label: continuator-release
  message: "after checkpoint validation"
  created_at: "2026-06-21T18:00:00+00:00"
  updated_at: "2026-06-21T18:00:00+00:00"

  source:
    kind: cursor
    platform: cursor
    path: ""
    sha256: "abc123def456"
    char_count: 52000
    message_count: 64

  engine:
    baseline: v10-050+repair+continuation_export_v2_frontier+explain_v1
    memory_model: v10
    archetype: coding
    extractor_backend: mlx

  state:
    project_title: continuator-release
    objective:
      - "Ship checkpoint platform architecture"
    current_state: "Validation experiment complete; designing multi-surface platform."
    completed_work:
      - "Implemented continuator checkpoint command"
      - "Completed archetype analysis"
    active_problems:
      - "Incremental merge not yet built"
    constraints:
      - "No V10 retrain"
    next_action: "Implement checkpoint format v2 reader/writer"

  cached_exports:
    briefing: |
      ## PROJECT
      ...
    claude: |
      Continue this conversation (continuator-release)...
```

---

## Code mapping (existing → v2)

| v2 field | Source today |
|----------|--------------|
| `state.*` | `checkpoint_state_v1.build_checkpoint_state()` |
| `cached_exports.briefing` | `render_briefing_from_checkpoint_state()` |
| `cached_exports.explain` | `generate_conversation_explanation()` |
| `cached_exports.claude/chatgpt/gemini` | `handoff_export_v1.build_platform_exports()` |
| `pipeline.ranker` | `rank_chunks()` return |
| `pipeline.chunking` | `all_transcript_chunks()` meta |
| `engine.baseline` | `product_baseline` in session result |

---

## Related documents

- [`checkpoint_schema_v1.md`](checkpoint_schema_v1.md) — Phase 2 full schema (superseded by v2 for platform)
- [`platform_architecture.md`](platform_architecture.md) — state engine
- [`integration_roadmap.md`](integration_roadmap.md) — when v2 ships
