# Checkpoint Validation Experiment

**Goal:** Test whether users find structured checkpoint artifacts valuable.  
**Scope:** One command. One file. No infrastructure.

**Ship:** `continuator checkpoint FILE` only.

---

## What this is / is not

| In scope | Out of scope |
|----------|--------------|
| Run existing pipeline end-to-end | `checkpoint list` / `show` / `diff` |
| Write minimal YAML to `./checkpoints/<project>.yaml` | `~/.continuator/`, index, config |
| 7 structured fields + project name | `format_version`, lineage, cached exports |
| Overwrite same project file on re-run | Update/merge workflow |
| ~250 LOC total | Storage manager, resume, compression |

---

## Design principle

**Do not build a checkpoint platform. Build a structured export of what `continue` already produces.**

The pipeline already computes a continuation briefing with fixed sections. The experiment parses that briefing into YAML fields — zero changes to V10 LoRA, ranker, or frontier export logic.

```
FILE → run_continuation() → continuation_briefing (markdown)
                                    ↓
                          parse_briefing_sections()
                                    ↓
                          write ./checkpoints/<project>.yaml
```

If users value the YAML artifact, invest in Phase 2 proper (schema, storage, resume). If not, delete ~250 LOC and keep `continue`.

---

## Minimal YAML schema

Single file, flat structure, no wrapper key:

```yaml
project: neck
objective:
  - Continue the Fetch API module from error handling.
  - Finish exercises in section 3.
current_state: Implementing error handling in the fetch wrapper; last working example uses .catch().
completed_work:
  - Completed modules 1-2
  - Set up local dev environment
active_problems:
  - CORS errors on local dev server
constraints:
  - Use TypeScript strict mode
  - No external state management library
next_action: Fix CORS configuration in vite.config.ts
```

### Field mapping (from continuation briefing)

| YAML field | Briefing section header |
|------------|-------------------------|
| `project` | CLI `--name` or filename stem (not parsed from briefing) |
| `objective` | `Objective:` |
| `current_state` | `Current Position:` |
| `completed_work` | `Completed Work:` |
| `active_problems` | `Active Problems:` |
| `constraints` | `Constraints:` |
| `next_action` | `Next Action:` |

### Parsing rules

- Section headers match `continuation_export_v2_frontier` output exactly (case-sensitive labels after `Objective:`, etc.).
- List sections: lines starting with `- ` → list items; strip leading `- `.
- `None identified.` → empty list `[]`.
- Single-line sections without bullets → string field (`current_state`, `next_action`).
- `objective` may be prose or bullets — if bullets, list; if single paragraph, one-element list or string (prefer **list** for consistency).
- Strip `## PROJECT` block and title lines before parsing; start at `Objective:`.

---

## Exact CLI UX

### Command

```bash
continuator checkpoint FILE [--name PROJECT] [-q|--quiet] [-v|--verbose]
```

No subcommands. `checkpoint` is the command; `FILE` is required.

### Examples

```bash
# Default: project = filename stem
continuator checkpoint examples/neck.txt
```

```
┌─ Continuator ─────────────────────────────────────────────┐
│  (same progress UI as `continue`: reading → ranking →     │
│   extracting → building)                                  │
└───────────────────────────────────────────────────────────┘

✓ Checkpoint saved
  project: neck
  path:    checkpoints/neck.yaml
  fields:  7/7 populated
```

```bash
continuator checkpoint chat.txt --name auth-refactor
# → checkpoints/auth-refactor.yaml
```

```bash
continuator checkpoint chat.txt -q
# → checkpoints/neck.yaml   (path only, one line)
```

```bash
continuator checkpoint - < chat.txt
# → checkpoints/conversation.yaml   (stdin default stem)
```

### Flags

| Flag | Behavior |
|------|----------|
| `--name PROJECT` | Override project slug (same as `continue --name`) |
| `-q / --quiet` | Print output path only |
| `-v / --verbose` | Show parse debug (section boundaries) on stderr |
| *(no `--json`)* | Not needed for validation |
| *(no `-o`)* | Always `./checkpoints/<project>.yaml` |

### Exit codes

| Code | Condition |
|------|-----------|
| 0 | Checkpoint written |
| 1 | Pipeline or parse failure |
| 2 | Input file not found / empty conversation |

### Failure messages

```
Could not generate a continuation briefing.
→ same as continue (pipeline failure)

Could not parse checkpoint fields from briefing.
→ parse found < 4/7 required fields (objective, current_state, next_action minimum)

Could not write checkpoints/neck.yaml: Permission denied
```

### Required fields for success

Validation gate (same spirit as `briefing_quality()`):

- `next_action` non-empty
- `current_state` non-empty **or** `completed_work` non-empty
- `objective` non-empty

Optional: `active_problems`, `constraints` may be empty lists.

### Overwrite behavior

Each run **overwrites** `./checkpoints/<project>.yaml`. No warning. No backup. Intentional for validation simplicity.

### Directory creation

```python
Path("checkpoints").mkdir(exist_ok=True)
```

Relative to **current working directory**, not repo root. Document in help text.

---

## Implementation plan

### Step 1 — Briefing section parser (~70 LOC)

**New file:** `continuator/checkpoint_parse.py`

```python
def parse_briefing_to_checkpoint(briefing: str, *, project: str) -> dict:
    """Parse continuation briefing markdown → minimal checkpoint dict."""
```

- Regex or line-scan split on section headers
- Unit tests with fixture string copied from real `generate_continuation_briefing_frontier` output (no LoRA in tests)

### Step 2 — Minimal YAML writer (~45 LOC)

**Same file or** `continuator/checkpoint_yaml.py`

```python
def write_checkpoint_yaml(path: Path, data: dict) -> None:
```

- **No PyYAML dependency** — hand-write YAML for `str` + `list[str]` only
- Escape strings containing `:` or newlines (quote or `|` block for `current_state`)
- Keeps dependency footprint unchanged

### Step 3 — Command handler (~100 LOC)

**New file:** `continuator/commands/checkpoint_cmd.py`

```python
def run(args):
    transcript = read_transcript(args.conversation)
    project = slugify(label_from_path(args.conversation, args.name) or "conversation")
    result = run_continuation(transcript, label=project, console=...)
    briefing = pick_export(result, "briefing")
    data = parse_briefing_to_checkpoint(briefing, project=project)
    validate_minimal_checkpoint(data)  # ~15 LOC inline
    path = Path("checkpoints") / f"{project}.yaml"
    path.parent.mkdir(exist_ok=True)
    write_checkpoint_yaml(path, data)
    # success output
```

Reuses verbatim:

- `read_transcript()` — `continuator/runtime.py`
- `label_from_path()` — same
- `run_continuation()` — `continuator/pipeline.py`
- `pick_export()` — same
- `ContinuatorConsole` — same progress UX as `continue`

### Step 4 — CLI registration (~10 LOC)

**Modify:** `continuator/cli.py`

- Add `"checkpoint"` to `_SUBCOMMANDS`
- `checkpoint_cmd.register(subparsers, parent=parent)`
- Epilog example: `continuator checkpoint chat.txt`

### Step 5 — Tests (~60 LOC)

**New file:** `tests/test_checkpoint_parse.py`

- Parse fixture briefing → assert all 7 fields
- Empty section → `[]`
- `None identified.` → `[]`
- Round-trip YAML write/read via parser on golden file

No integration test requiring LoRA (use `MEMORY_EXTRACTOR_BACKEND=mock` optional smoke in CI).

---

## Files to modify

| File | Action | LOC |
|------|--------|-----|
| `continuator/checkpoint_parse.py` | **new** — parser + yaml writer + slugify | ~115 |
| `continuator/commands/checkpoint_cmd.py` | **new** — command handler | ~100 |
| `continuator/cli.py` | register subcommand | ~10 |
| `tests/test_checkpoint_parse.py` | **new** — parser/writer tests | ~60 |
| `tests/fixtures/briefing_neck.txt` | **new** — golden briefing snippet | ~30 (data) |

**Engine changes:** none.  
**Pipeline changes:** none.  
**New dependencies:** none.

---

## Estimated LOC

| Component | LOC |
|-----------|-----|
| `checkpoint_parse.py` | 115 |
| `checkpoint_cmd.py` | 100 |
| `cli.py` | 10 |
| `test_checkpoint_parse.py` | 60 |
| **Total** | **~285** |

Under 300 LOC budget.

---

## Risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Briefing format changes | Parser breaks | Test fixture from real export; parser keyed to exact section labels |
| `## PROJECT` title confuses parser | Wrong fields | Skip lines before `Objective:` |
| Project slug collisions | Overwrites | Document; acceptable for validation |
| `./checkpoints/` cwd-relative | User confusion | Print full resolved path in success message |
| Multiline `current_state` | YAML formatting | Use `\|` block scalar in hand writer |

---

## Validation success criteria

After shipping, measure manually (no analytics infra needed):

1. **Do users run `checkpoint` more than once** on the same project (overwrite = re-validation)?
2. **Do users open/edit the YAML** or paste fields elsewhere?
3. **Does anyone ask for `resume` or `list`** unprompted? → signals Phase 2 demand
4. **Does anyone say the YAML is redundant with the briefing?** → signals experiment failed

If 2–3 positive signals within beta feedback → proceed to Phase 2 schema. Otherwise keep `continue` only.

---

## Slugify helper (~10 LOC)

```python
def slugify_project(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", name.strip().lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:64] or "conversation"
```

Prevents path traversal (`../evil` → `evil`). Filename = `{slug}.yaml` only.

---

## Help text (exact)

```
usage: continuator checkpoint [-h] [-q] [-v] [--name NAME] conversation

Extract structured checkpoint fields from a conversation and save to
./checkpoints/<project>.yaml

positional arguments:
  conversation          Path to a conversation file (.txt, .json), or '-' for stdin

options:
  --name NAME           Project name for output file (default: filename stem)
  -q, --quiet           Print output path only
  -v, --verbose         Show parsing details

Examples:
  continuator checkpoint chat.txt
  continuator checkpoint chat.txt --name my-project
  continuator checkpoint chat.txt -q
```

---

## Delete path

If validation fails, remove:

- `continuator/checkpoint_parse.py`
- `continuator/commands/checkpoint_cmd.py`
- `tests/test_checkpoint_parse.py`
- `tests/fixtures/briefing_neck.txt`
- 10 lines from `cli.py`

No engine rollback required.
