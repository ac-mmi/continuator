# Checkpoint Storage Design (Phase 2)

**Status:** Design only  
**Scope:** `checkpoint create`, `checkpoint list`, `checkpoint show` — local filesystem, no cloud sync.

---

## Storage root

```
~/.continuator/
├── config.yaml                 # optional: defaults (future)
└── checkpoints/
    └── <project>/              # one directory per project slug
        ├── index.yaml          # lightweight manifest for fast list
        ├── a3f2c891.yaml       # checkpoint record
        └── b7c1d045.yaml
```

**Default root:** `~/.continuator/checkpoints/`

**Override:** environment variable `CONTINUATOR_CHECKPOINT_DIR` (absolute path replaces `checkpoints/` subtree root entirely).

**Permissions:** create directories with `0700`; checkpoint files with `0600` (user-only read/write).

---

## Project slug rules

Project name comes from CLI `--name` or transcript filename stem (same as `label_from_path()` today).

Slugification (`slugify_project(name) -> str`):

1. Lowercase
2. Replace spaces and underscores with `-`
3. Strip characters outside `[a-z0-9-]`
4. Collapse repeated `-`
5. Trim leading/trailing `-`
6. Truncate to 64 chars
7. Fallback to `"default"` if empty

Examples:

| Input | Slug |
|-------|------|
| `neck.txt` | `neck` |
| `Neck Refactor` | `neck-refactor` |
| `auth_module_v2` | `auth-module-v2` |

---

## Checkpoint file naming

```
~/.continuator/checkpoints/<project>/<id>.yaml
```

- `<id>` = 8-char hex from schema (`checkpoint.id`)
- Collision within project: regenerate id with nonce suffix (extremely unlikely; handle anyway)

**No subdirectories per checkpoint** — flat files under project directory keeps list/show simple.

---

## Index manifest (`index.yaml`)

Optional but recommended for fast `checkpoint list` without parsing every checkpoint file.

```yaml
index:
  format_version: 1
  project: neck-refactor
  updated_at: "2026-06-21T14:30:00+00:00"
  checkpoints:
    - id: a3f2c891
      created_at: "2026-06-21T14:30:00+00:00"
      message: "after auth module"
      source_path: /Users/me/chat.txt
      source_sha256: "abc123..."
      char_count: 47291
      briefing_words: 142
    - id: b7c1d045
      created_at: "2026-06-21T16:00:00+00:00"
      message: ""
      source_path: /Users/me/chat.txt
      source_sha256: "def456..."
      char_count: 51002
      briefing_words: 156
```

**Update policy:** rewrite `index.yaml` atomically on every successful checkpoint create (write temp file → rename).

**Fallback:** if `index.yaml` missing or corrupt, `checkpoint list` scans `*.yaml` files (excluding `index.yaml`) and reads only top-level metadata fields.

---

## Command: `continuator checkpoint` (create)

### Synopsis

```bash
continuator checkpoint FILE [OPTIONS]
```

Alias considered but not required: `continuator checkpoint create FILE`.

### Arguments

| Arg | Description |
|-----|-------------|
| `FILE` | Transcript path (`.txt`, `.json`) or `-` for stdin |

### Options

| Flag | Description |
|------|-------------|
| `--name PROJECT` | Project slug override (default: filename stem) |
| `--message MSG` | Stored in `checkpoint.message` |
| `-o PATH` | Write checkpoint to explicit path (skip default storage layout) |
| `--json` | Write JSON instead of YAML |
| `-q / -v` | Quiet / verbose (shared parent flags) |

### Behavior

```
1. read_transcript(FILE)
2. run_continuator(transcript, label=label)     # existing pipeline — no behavior change
3. build_checkpoint_record(result, source_meta)
4. validate_checkpoint_record(record)
5. resolve storage path:
     default → ~/.continuator/checkpoints/<project>/<id>.yaml
     -o      → user path
6. write_checkpoint(record, path)
7. update index.yaml (unless -o outside checkpoint root)
8. print success summary
```

### Success output (default)

```
✓ Checkpoint saved
  id:      a3f2c891
  project: neck-refactor
  path:    ~/.continuator/checkpoints/neck-refactor/a3f2c891.yaml
  source:  47,291 chars → 142 word briefing (38:1)
```

### Quiet output

```
~/.continuator/checkpoints/neck-refactor/a3f2c891.yaml
```

(single line path — same pattern as `export --quiet`)

### Exit codes

| Code | Condition |
|------|-----------|
| 0 | Success |
| 1 | Pipeline / validation failure |
| 2 | Input file not found |

### Stdin handling

When `FILE` is `-`:

- `source.path` = `"stdin"`
- `source.format` = `"stdin"`
- No automatic re-extract path — user must re-supply stdin for refresh (Phase 3 concern; document in show output)

---

## Command: `continuator checkpoint list`

### Synopsis

```bash
continuator checkpoint list [OPTIONS]
```

### Options

| Flag | Description |
|------|-------------|
| `--project NAME` | Filter to one project slug |
| `--limit N` | Max entries (default: 20, most recent first) |
| `--json` | Machine-readable output |
| `-q` | IDs only, one per line |

### Behavior

```
1. resolve checkpoint root (~/.continuator/checkpoints/)
2. if --project: scan single project dir
   else: scan all project subdirs
3. load index.yaml per project (or fallback scan)
4. sort by created_at descending
5. apply --limit
6. render table or JSON
```

### Default output

```
Checkpoints (3)

  PROJECT          ID        CREATED                 SOURCE              SIZE
  neck-refactor    b7c1d045  2026-06-21 16:00 UTC   chat.txt (51k)      156w
  neck-refactor    a3f2c891  2026-06-21 14:30 UTC   chat.txt (47k)      142w
  auth-module      d4e8f012  2026-06-20 09:15 UTC   auth.txt (12k)       98w
```

### Empty state

```
No checkpoints found.
Create one with: continuator checkpoint chat.txt
```

### Resolution rules

| User input | Resolved path |
|------------|---------------|
| (none) | all projects under root |
| `--project neck` | `~/.continuator/checkpoints/neck/` |
| `--project neck-refactor` | same |

---

## Command: `continuator checkpoint show`

### Synopsis

```bash
continuator checkpoint show TARGET [OPTIONS]
```

### Arguments

`TARGET` is resolved in order:

1. **Existing file path** — if `Path(TARGET).is_file()`, read directly
2. **`<project>/<id>`** — e.g. `neck-refactor/a3f2c891`
3. **`<id>` alone** — search all projects for matching id prefix
4. **`latest`** or **`latest:<project>`** — most recent checkpoint (global or per-project)

### Options

| Flag | Description |
|------|-------------|
| `--format {summary,state,briefing,explain,full}` | Output view (default: `summary`) |
| `--json` | Raw checkpoint record as JSON |
| `-o FILE` | Write output to file |

### `--format` views

| Format | Output |
|--------|--------|
| `summary` | id, project, created_at, source, stats, state.next_action (human table) |
| `state` | `checkpoint.state` as YAML/JSON |
| `briefing` | `cached_exports.briefing` verbatim |
| `explain` | `cached_exports.explain` verbatim |
| `full` | entire checkpoint record |

### Default summary output

```
Checkpoint a3f2c891
  Project:    neck-refactor
  Created:    2026-06-21 14:30 UTC
  Message:    after auth module
  Source:     /Users/me/chat.txt (47,291 chars)
  Pipeline:   v10-050+repair+continuation_export_v2_frontier+explain_v1
  Chunks:     5/14 selected (approach_b_v1)
  Briefing:   142 words (38:1 compression)

  Next action:
    Fix CORS configuration in vite.config.ts
```

### Exit codes

| Code | Condition |
|------|-----------|
| 0 | Success |
| 1 | Checkpoint not found / invalid file |
| 2 | Invalid `--format` |

---

## Command: `continuator checkpoint diff` (Phase 2D — design only)

Included here for storage context; implementation is Phase 2D.

```bash
continuator checkpoint diff TARGET_A TARGET_B [OPTIONS]
```

`TARGET_A` and `TARGET_B` use same resolution rules as `show`.

Default output: field-level diff on `state` (objective, completed_work, active_problems, current_state, next_action) plus source hash change indicator.

---

## Atomic write protocol

Prevent partial checkpoint files on crash:

```python
def write_checkpoint(record, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(serialize(record), encoding="utf-8")
    tmp.replace(path)          # atomic on POSIX
    chmod(path, 0o600)
```

Same pattern for `index.yaml` updates.

---

## Config file (optional, Phase 2 stub)

`~/.continuator/config.yaml` — not required for MVP:

```yaml
checkpoints_dir: ~/.continuator/checkpoints   # override default root
default_project: ""                            # future
```

If absent, use defaults. `CONTINUATOR_CHECKPOINT_DIR` env var takes precedence over config.

---

## Storage size estimates

| Component | Typical size |
|-----------|-------------|
| Checkpoint YAML (briefing + explain + 5 chunk JSON outputs) | 15–40 KB |
| Index entry | ~200 bytes |
| 100 checkpoints / project | ~2–4 MB |

No pruning in Phase 2. Future: `checkpoint prune --keep N`.

---

## Security considerations

- Checkpoints may contain conversation content in `cached_exports` and `pipeline.chunk_extractions` — treat as sensitive.
- Default `0600` permissions.
- No network transmission in Phase 2.
- `source.path` stores absolute path — may leak username; acceptable for local tool; `--name` does not affect path storage.

---

## Relationship to existing `-o` flags

| Command | `-o` behavior today | Phase 2 behavior |
|---------|--------------------|--------------------|
| `continue -o out.md` | writes briefing markdown | unchanged |
| `continue --json -o out.json` | writes session JSON | unchanged |
| `checkpoint -o path.yaml` | (new) writes checkpoint record | new |
| `checkpoint show -o out.md` | (new) writes selected format view | new |

Session JSON from `continue --json` is **not** identical to CheckpointRecord — checkpoint is a stable, validated subset plus `format_version`.

---

## Directory bootstrap

First `continuator checkpoint` run:

```
mkdir -p ~/.continuator/checkpoints/<project>  # mode 0700
```

No global install step required.

---

## Test fixtures (for implementation)

```
tests/fixtures/checkpoints/
  neck/
    a3f2c891.yaml          # minimal valid fixture
    index.yaml
  invalid/
    bad_version.yaml       # format_version: 99
    missing_briefing.yaml
```

Used by unit tests for list/show/validate without running LoRA.
