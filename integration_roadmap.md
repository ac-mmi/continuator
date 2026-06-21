# Integration Roadmap

**Status:** Design only  
**Horizon:** Platform evolution from terminal app → multi-surface conversation state product  
**Engine:** V10 LoRA unchanged throughout

---

## Roadmap overview

```
Phase 1          Phase 2              Phase 3           Phase 4          Phase 5         Phase 6
(Current)        State Engine         Editor Exts       Agent CLIs       Browser         Unified Format
────────         ────────────         ───────────       ─────────        ────────        ──────────────
TUI + CLI        Incremental          Cursor            Claude Code      ChatGPT         checkpoint.yaml
continue         merge + resume       VS Code           MCP / Codex      Claude.ai       portable everywhere
explain          continuator serve    observe + CP      slash cmds       Gemini/Grok
checkpoint       format v2 reader     local .continuator/
```

---

## Phase 1 — Current (shipped / shipping)

**Theme:** Terminal app + CLI; prove shared `CheckpointState`.

### Delivered

| Component | Status |
|-----------|--------|
| V10 extraction pipeline | ✅ |
| `continuator continue` | ✅ |
| `continuator explain` | ✅ |
| `continuator export` | ✅ |
| `continuator inspect` | ✅ |
| `continuator benchmark` | ✅ |
| Textual TUI | ✅ |
| `CheckpointState` + render split | ✅ |
| `continuator checkpoint` (validation) | ✅ minimal yaml |

### Phase 1 completion criteria

- [x] `build_checkpoint_state()` powers briefing and checkpoint from same extraction
- [x] Archetype analysis validates genre positioning
- [ ] README reflects "conversation state" positioning (copy only)
- [ ] Validation experiment user feedback collected

### No work in Phase 1

- Extensions, browser, MCP, incremental merge, format v2

---

## Phase 2 — Background State Engine

**Theme:** Incremental extraction, resume, portable checkpoint format.  
**Duration estimate:** 4–6 weeks

### Goals

1. Avoid reprocessing entire conversations on update.
2. Resume from checkpoint without LoRA (cached exports).
3. Ship `checkpoint_format_v2` standard tier.

### 2.1 Incremental extraction

```
Existing CheckpointRecord
  + new messages since last source.message_count
    → chunk tail only
    → rank (terminal lock on latest)
    → V10 extract new chunks
    → merge_state(base, delta)
    → updated CheckpointRecord
```

### Merge strategy design

**Policy name:** `frontier_wins_v1` (extends existing frontier aggregation semantics)

| Field | Merge rule |
|-------|------------|
| `objective` | Union dedupe; frontier objectives prepended |
| `current_state` | **Replace** with delta frontier position |
| `completed_work` | Union dedupe chronological (existing `_aggregate_list_field`) |
| `active_problems` | **Replace** with delta frontier actives; filter superseded |
| `resolved_problems` | Union from delta |
| `constraints` | Union dedupe |
| `next_action` | **Replace** from delta `_derive_frontier_next_action` |
| `closure_detected` | Delta wins |

**Chunk-level cache:** Store `pipeline.chunk_extractions` in full-tier checkpoint. On merge, append new chunk outputs; skip re-extract if `chunk_index` already in cache and source hash unchanged for that span.

**Conflict detection:** If `source.sha256` changes but not append-only (user edited mid-transcript), warn and require `--full-refresh`.

### 2.2 New commands

```bash
continuator checkpoint FILE [--update]     # incremental if prior exists
continuator resume [CHECKPOINT]            # render from cache
continuator resume --refresh               # re-extract from source
continuator serve [--port 8741]            # local HTTP for extensions (prep)
```

### 2.3 Modules to build

| Module | LOC est. | Purpose |
|--------|----------|---------|
| `checkpoint_record_v2.py` | ~200 | v2 read/write/validate/migrate v1 |
| `checkpoint_merge_v1.py` | ~150 | `merge_state(base, delta, strategy)` |
| `checkpoint_store_v2.py` | ~120 | `.continuator/` layout |
| `continuator/commands/resume_cmd.py` | ~100 | Resume UX |
| `continuator/platform/sdk.py` | ~150 | Python SDK facade |

### 2.4 Phase 2 exit criteria

- [ ] Incremental update ≥3× faster than full re-extract on 2× grown transcript (benchmark gate)
- [ ] `continuator resume` < 500ms from cached_exports
- [ ] v2 checkpoint round-trips through reader/writer
- [ ] Merge parity ≥95% vs full re-extract on benchmark corpus

### Risks

| Risk | Mitigation |
|------|------------|
| Merge quality regression | Benchmark gate; `frontier_wins_v1` reuses production helpers |
| Source file moved | Store relative path + hash; `--refresh` fallback |

---

## Phase 3 — Cursor / VS Code Extensions

**Theme:** Checkpoint in the editor where agentic sessions happen.  
**Duration estimate:** 6–8 weeks  
**Depends on:** Phase 2 (`resume`, v2 format, optional `continuator serve`)

### Deliverables

| Item | Description |
|------|-------------|
| `@continuator/sdk` | TypeScript SDK (CLI bridge) |
| `integrations/cursor` | Cursor extension package |
| `integrations/vscode` | VS Code extension (shared core) |
| `.continuator/` workspace template | gitignore snippet |

### Commands (both extensions)

- `Continuator: Checkpoint Conversation`
- `Continuator: Resume from Checkpoint`
- `Continuator: Export for Claude/ChatGPT`
- `Continuator: Show State` (webview)

### Storage

```
<workspace>/.continuator/checkpoint.yaml
```

### Update frequency

- **MVP:** Manual command only
- **Optional:** Auto-checkpoint on window blur (setting, off by default)
- **Prompt:** When context > 80% (if host exposes token estimate)

### APIs required

| API | Cursor | VS Code |
|-----|:------:|:-------:|
| Command palette | ✅ | ✅ |
| Clipboard | ✅ | ✅ |
| Webview | ✅ | ✅ |
| Chat history read | ⚠️ | ⚠️ |
| Subprocess spawn | ✅ | ✅ |

**Blocker:** Chat history API — validate in week 1 spike. Fallback: export file picker.

### Phase 3 exit criteria

- [ ] Checkpoint from Cursor in ≤3 clicks
- [ ] Resume injects briefing into composer/chat
- [ ] Same `checkpoint.yaml` readable by terminal `continuator resume`
- [ ] Published to Cursor marketplace (or sideload docs)

---

## Phase 4 — Claude Code / Codex

**Theme:** Agent CLI integrations via MCP.  
**Duration estimate:** 3–4 weeks  
**Depends on:** Phase 2 SDK; Phase 3 storage convention

### Deliverables

| Item | Description |
|------|-------------|
| `continuator-mcp` | Python MCP server |
| `integrations/claude-code/` | CLAUDE.md template, install docs |
| MCP tools | extract, checkpoint, resume, merge |

### MCP tools

```
continuator_extract(transcript, project) → CheckpointRecord
continuator_checkpoint(project) → path
continuator_resume(project, format) → briefing text
continuator_merge(project, delta) → CheckpointRecord
```

### Claude Code slash commands (fallback)

```
/continuator:checkpoint
/continuator:resume
```

Shell out to CLI — works without MCP.

### Codex feasibility

| Approach | Verdict |
|----------|---------|
| Same MCP server | **Feasible** if Codex adds MCP client |
| CLI hook | **Monitor** — use if hook API ships |
| Custom action | **Defer** — privacy |

### Phase 4 exit criteria

- [ ] Claude Code user can checkpoint + resume within session
- [ ] MCP tools documented in Continuator README
- [ ] Codex path documented (even if "not yet supported")

---

## Phase 5 — Browser Extension

**Theme:** Checkpoint web UI conversations (ChatGPT, Claude, Gemini, Grok).  
**Duration estimate:** 8–10 weeks  
**Depends on:** Phase 2 `continuator serve`; v2 format

### Deliverables

| Item | Description |
|------|-------------|
| `integrations/browser/` | Manifest V3 extension |
| Platform adapters | ChatGPT, Claude, Gemini |
| Local service installer | Bundled `continuator serve` helper |

### Flows

1. **Checkpoint this chat** → scrape DOM → local extract → save/download yaml
2. **Continue in new chat** → render export → paste/open new tab
3. **Load checkpoint file** → resume in new chat

### Requirements met

| Requirement | Design |
|-------------|--------|
| Read conversation DOM | Per-platform content script adapter |
| Extract text | Adapter → transcript string |
| Generate checkpoint | HTTP → `continuator serve /extract` |
| Export briefing | `cached_exports.chatgpt` etc. |
| Start new chat with checkpoint | Paste injection + platform-specific new-chat URL |

### Phase 5 exit criteria

- [ ] ChatGPT + Claude adapters pass fixture DOM tests
- [ ] Checkpoint never sent to remote server (local only)
- [ ] Export opens new chat with briefing in clipboard/input

### Risks

| Risk | Mitigation |
|------|------------|
| DOM breakage | Adapter versioning; community quick-fix releases |
| User doesn't run local service | Installer + clear onboarding |
| Low archetype value for casual chats | Warning banner (archetype analysis) |

---

## Phase 6 — Unified Checkpoint Format

**Theme:** Formalize v2 as cross-surface contract.  
**Duration estimate:** 2–3 weeks (parallel with Phase 3–5)  
**Can start:** After Phase 2 reader/writer exists

### Deliverables

| Item | Description |
|------|-------------|
| `checkpoint_format_v2.md` | ✅ this document set |
| JSON Schema | `schemas/checkpoint-v2.schema.json` |
| Conformance tests | Round-trip fixtures per surface |
| Migration tool | `continuator checkpoint migrate v1→v2` |

### Portability proof

One `checkpoint.yaml` must:

1. Be written by Cursor extension
2. Be read by `continuator resume` in terminal
3. Be loaded by browser extension for new-chat export
4. Be served by Claude Code MCP `continuator_resume`
5. Produce identical `cached_exports.briefing` on all surfaces (given same engine version)

### Phase 6 exit criteria

- [ ] Schema published in repo
- [ ] All surfaces use `format_version: 2` standard tier minimum
- [ ] Conformance test CI gate
- [ ] v1 validation yaml migrates cleanly

---

## Timeline (indicative)

```
2026 Q2   Phase 1 complete (validation + archetype analysis)
2026 Q3   Phase 2 — state engine, resume, v2 format
2026 Q3   Phase 3 — Cursor extension MVP
2026 Q4   Phase 4 — Claude Code MCP
2026 Q4   Phase 6 — format conformance
2027 Q1   Phase 5 — browser extension
2027 Q1   Phase 3b — VS Code marketplace
```

Phases 3, 4, 5 can overlap once Phase 2 SDK is stable.

---

## Team focus by phase

| Phase | Primary work | Secondary |
|-------|--------------|-----------|
| 1 | Terminal polish, validation feedback | Docs |
| 2 | Merge engine, v2 format, `serve` | Resume UX |
| 3 | Cursor ext + TS SDK | VS Code shared core |
| 4 | MCP server | Codex monitoring |
| 5 | Browser adapters | Local service UX |
| 6 | Schema + conformance | Migration |

---

## What we are not building

- V11 / retraining
- Cloud sync or multi-user checkpoints
- Replacement for IDE-native memory
- Checkpoint for all conversation types (see archetype analysis)
- In-browser LoRA (WASM) — local Python service only

---

## Metrics per phase

| Phase | Success metric |
|-------|----------------|
| 1 | Validation experiment: ≥3 users find yaml useful for dev/tutor threads |
| 2 | Incremental checkpoint < 30s on typical delta; resume < 500ms |
| 3 | ≥50 Cursor extension installs; repeat checkpoint usage |
| 4 | Claude Code MCP in official docs / community adoption |
| 5 | Browser ext: checkpoint + new-chat flow completion rate |
| 6 | Zero format drift across surfaces in conformance CI |

---

## Document index

| Document | Contents |
|----------|----------|
| [`platform_architecture.md`](platform_architecture.md) | Layers, SDK, data flow |
| [`extension_strategy.md`](extension_strategy.md) | Per-surface integration detail |
| [`checkpoint_format_v2.md`](checkpoint_format_v2.md) | Portable checkpoint schema |
| [`checkpoint_archetype_analysis.md`](checkpoint_archetype_analysis.md) | Genre positioning |
| [`product_repositioning_analysis.md`](product_repositioning_analysis.md) | Strategic framing |

---

## Immediate next steps (when implementation resumes)

1. **Phase 2a** — `checkpoint_record_v2` reader/writer + migrate v1 validation yaml
2. **Phase 2b** — `continuator resume` from cached_exports
3. **Phase 2c** — `checkpoint_merge_v1` + `--update` flag
4. **Phase 2d** — `continuator serve` HTTP skeleton for extension prep
5. **Phase 3 spike** — Cursor chat history API feasibility (1 week)

No V10 changes required for any of the above.
