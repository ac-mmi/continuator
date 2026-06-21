# Continuator Platform Architecture

**Status:** Design only  
**Core engine:** V10 LoRA — Conversation State Extractor (unchanged)  
**North star:** One extraction engine, many product surfaces, one state model.

---

## Positioning shift

| Before | After |
|--------|-------|
| "Continuation briefing generator" | "Conversation state platform" |
| LoRA = handoff prompt writer | LoRA = **structured state extractor** |
| CLI output = markdown briefing | CLI output = **view** over `CheckpointState` |

The V10 LoRA extracts durable conversation state:

```
objective · current_state · completed_work · active_problems · constraints · next_action
```

Everything else — Continue, Explain, Checkpoint, Resume, Export, Handoff — is a **renderer** or **transport** over that state.

---

## System diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PRODUCT SURFACES                                   │
├──────────┬──────────┬──────────┬──────────┬──────────┬────────────────┤
│ Terminal │   CLI    │  Cursor  │ VS Code  │  Claude  │ Browser Ext.   │
│   TUI    │          │   Ext.   │   Ext.   │   Code   │ ChatGPT/Claude │
└────┬─────┴────┬─────┴────┬─────┴────┬─────┴────┬─────┴───────┬────────┘
     │          │          │          │          │             │
     └──────────┴──────────┴────┬─────┴──────────┴─────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Platform SDK        │  (future: TypeScript + Python)
                    │   - extract()         │
                    │   - merge()           │
                    │   - render()          │
                    │   - export()          │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │   State Engine        │
                    │   CheckpointState     │  ← single source of truth
                    │   + merge policy      │
                    │   + render registry   │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Extraction Pipeline │  (existing continuator_engine)
                    │   chunk → rank → V10  │
                    │   → aggregate → state   │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │   V10 LoRA            │  Qwen2.5-1.5B + adapter
                    │   (Conversation State │  NO retrain in platform plan
                    │    Extractor)         │
                    └───────────────────────┘
```

---

## Layer definitions

### L0 — V10 Extraction Pipeline (exists today)

**Package:** `continuator_engine/`

| Stage | Module | Output |
|-------|--------|--------|
| Chunk | `memory_extractor_v1._chunk_transcript_for_extraction` | `list[str]` chunks |
| Rank | `continuator_chunk_ranker_v1.rank_chunks` | selected indices |
| Extract | V10 LoRA per chunk | per-chunk JSON |
| Aggregate | `checkpoint_state_v1.build_checkpoint_state` | `CheckpointState` |
| Render | `render_*` functions | briefing, explain, YAML, platform exports |

**Invariant:** No surface bypasses this pipeline. Extensions call the same engine, not a parallel summarizer.

### L1 — State Engine (to build)

**Responsibility:** Own `CheckpointState` lifecycle.

| Capability | Status | Notes |
|------------|--------|-------|
| `build_state(transcript)` | ✅ exists | `run_continuator()` → `checkpoint_state` |
| `render(state, view)` | ✅ partial | briefing, explain, yaml |
| `merge(base, delta)` | ❌ Phase 2 | incremental update |
| `validate(state)` | ✅ partial | `checkpoint_yaml.validate_checkpoint_state` |
| `persist(state)` | ❌ Phase 2+ | read/write `checkpoint.yaml` |

**State engine does not run LoRA directly** — it orchestrates the pipeline and owns merge/persistence policy.

### L2 — Platform SDK (to build)

Thin API for all surfaces. Two bindings:

| Binding | Consumers |
|---------|-----------|
| **Python** (`continuator` package) | CLI, TUI, Claude Code subprocess, MCP server |
| **TypeScript** (`@continuator/sdk`) | Cursor ext, VS Code ext, browser ext |

SDK surface (language-agnostic):

```typescript
interface ContinuatorSDK {
  extract(input: ExtractInput): Promise<CheckpointRecord>;
  merge(base: CheckpointRecord, delta: ExtractInput): Promise<CheckpointRecord>;
  render(record: CheckpointRecord, view: RenderView): string;
  export(record: CheckpointRecord, target: ExportTarget): string;
}
```

**Phase 1–2:** Python-only; extensions shell out to `continuator` CLI.  
**Phase 3+:** Native TS SDK wrapping local HTTP or IPC to Python engine.

### L3 — Product Surfaces

Each surface is a **client** of L2. None embed extraction logic.

| Surface | Phase | Integration pattern |
|---------|-------|---------------------|
| Terminal TUI | 1 ✅ | In-process Python |
| CLI | 1 ✅ | `continuator {command}` |
| Cursor extension | 3 | TS → CLI or local service |
| VS Code extension | 3 | TS → CLI or local service |
| Claude Code | 4 | MCP or slash command → CLI |
| Browser extension | 5 | TS → cloud or local service |
| Platform exports | 1 ✅ | `render(state, claude\|chatgpt\|gemini)` |

---

## CheckpointState as single source of truth

### Canonical state (runtime)

Already implemented in `continuator_engine/checkpoint_state_v1.py`:

```python
CheckpointState = {
    project: str
    project_title: str
    objective: list[str]
    objective_display: str      # internal — briefing fidelity
    current_state: str
    completed_work: list[str]
    active_problems: list[str]
    constraints: list[str]
    next_action: str
}
```

### Derived artifacts (never authoritative)

| Artifact | Renderer | Source field |
|----------|----------|--------------|
| Continuation briefing | `render_briefing_from_checkpoint_state` | full state |
| Explain summary | `generate_conversation_explanation` | chunk outputs (today); state-only (future) |
| `checkpoint.yaml` | `render_checkpoint_yaml` | state subset |
| Claude paste block | `format_for_claude` | briefing |
| ChatGPT paste block | `format_for_chatgpt` | briefing |
| Gemini paste block | `format_for_gemini` | briefing |

**Rule:** Surfaces read and write `CheckpointRecord` (state + metadata). They never parse briefing markdown back into state.

---

## Product catalog

All products are views or workflows over the same state:

```
                    CheckpointState
                          │
     ┌────────────────────┼────────────────────┐
     │         │          │         │        │
  Continue  Explain  Checkpoint  Resume  Export
     │         │          │         │        │
  briefing  retrospective  .yaml   inject  platform
  markdown   summary      file    context  paste
```

| Product | User intent | Input | Output |
|---------|-------------|-------|--------|
| **Continue** | Hand off to fresh AI chat | transcript or checkpoint | briefing markdown |
| **Explain** | Understand what happened | transcript or checkpoint | retrospective summary |
| **Checkpoint** | Save durable state | transcript | `checkpoint.yaml` |
| **Resume** | Continue without re-extracting | checkpoint | briefing / injected context |
| **Export** | Platform-specific paste | transcript or checkpoint | claude/chatgpt/gemini block |
| **Handoff** | Alias for Continue + Export | same | combined workflow |

---

## Data flow (target)

### Full extraction (today)

```
Conversation text
  → chunk + rank
  → V10 extract (selected chunks)
  → build_checkpoint_state()
  → CheckpointState
  → render(view)
```

### Incremental extraction (Phase 2)

```
Existing CheckpointRecord + new messages (delta)
  → rank delta tail only
  → V10 extract (new chunks)
  → merge_state(base, delta_extractions)
  → updated CheckpointState
  → persist checkpoint.yaml
```

### Resume (Phase 2–3)

```
checkpoint.yaml
  → load CheckpointRecord
  → render(resume, target=cursor|claude|...)
  → inject into editor / new chat
  (no LoRA unless --refresh)
```

---

## Deployment models

Extensions can reach the engine three ways:

| Model | Pros | Cons | Phase |
|-------|------|------|-------|
| **CLI subprocess** | Zero new infra; works today | Latency; no streaming | 1–3 |
| **Local HTTP service** | Fast; streamable; one model load | Ops complexity | 3–4 |
| **MCP server** | Native Claude Code fit | Claude-specific | 4 |

**Recommendation:** CLI subprocess for Phase 3 MVP; local HTTP service (`continuator serve`) for Phase 4+ when extensions need sub-second resume.

```
┌─────────────┐     spawn      ┌──────────────────┐
│ Cursor ext  │ ──────────────►│ continuator      │
│ VS Code ext │                │ checkpoint/resume│
└─────────────┘                └────────┬─────────┘
                                        │
┌─────────────┐     HTTP :8741          │
│ Browser ext │ ───────────────────────►│ continuator serve │
└─────────────┘                         │ (model loaded once) │
                                        └──────────────────┘
```

---

## Local vs cloud boundary

| Component | Default | Rationale |
|-----------|---------|-----------|
| V10 LoRA inference | **Local** | Privacy; offline; matches v0.1 |
| Checkpoint storage | **Local** | `~/.continuator/` or workspace `.continuator/` |
| Browser extension extract | **Local service preferred** | Transcript never leaves machine |
| Optional cloud sync | Out of scope | Not in platform plan |

---

## Archetype-aware platform behavior

Per `checkpoint_archetype_analysis.md`, not all conversations benefit from checkpointing.

Platform policy (no V10 change):

| Archetype | Checkpoint default | Surfaces |
|-----------|-------------------|----------|
| tutorial, coding, project, research | **Encouraged** | All |
| journal, customer_discovery | Optional | Explain > Checkpoint |
| medical, informational_QA, casual_chat | **Discouraged** | Continue/Explain only; soft warning on checkpoint |

Surfaces share archetype heuristics via SDK — not per-extension logic.

---

## Package structure (target)

```
continuator/                    # Python product (CLI, TUI)
  commands/
  checkpoint_yaml.py
  platform/                       # NEW — SDK facade
    sdk.py                        # extract, merge, render, export
    views.py                      # RenderView registry

continuator_engine/               # Extraction engine (unchanged API)
  checkpoint_state_v1.py          # State builder
  continuator_chunk_ranker_v1.py
  memory_extractor_v1.py
  ...

packages/
  continuator-sdk/                # NEW — TypeScript SDK
    src/
      client.ts                   # CLI bridge → HTTP later
      types.ts                    # CheckpointRecord, RenderView
      formats.ts                  # checkpoint.yaml parser

integrations/                     # NEW — extension hosts
  cursor/
  vscode/
  browser/
  claude-code/
```

---

## Non-goals (platform plan)

- V11 or retraining
- Cloud checkpoint sync
- Multi-user collaboration
- Replacing IDE-native memory (Cursor @codebase, etc.)
- Universal "checkpoint every chat" positioning

---

## Success criteria

| Milestone | Signal |
|-----------|--------|
| Phase 1 | `CheckpointState` powers continue + checkpoint from same extraction |
| Phase 2 | Incremental merge without full re-extract; resume from yaml |
| Phase 3 | Cursor ext checkpoints after session; resume injects context |
| Phase 4 | Claude Code `continuator resume` in workflow |
| Phase 5 | Browser ext exports briefing to new ChatGPT tab |
| Phase 6 | Same `checkpoint.yaml` opens in terminal, Cursor, and browser |

---

## Related documents

- [`extension_strategy.md`](extension_strategy.md) — per-surface integration design
- [`checkpoint_format_v2.md`](checkpoint_format_v2.md) — portable checkpoint format
- [`integration_roadmap.md`](integration_roadmap.md) — phased delivery plan
- [`checkpoint_archetype_analysis.md`](checkpoint_archetype_analysis.md) — genre fit
