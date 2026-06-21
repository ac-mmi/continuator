# Extension Strategy

**Status:** Design only  
**Scope:** Cursor, VS Code, Claude Code, Codex, Browser extension  
**Principle:** Extensions are thin clients over the V10 State Engine — no embedded extraction.

---

## Shared extension architecture

All extensions follow the same pattern:

```
┌─────────────────────────────────────────────────────────┐
│  Host (Cursor / VS Code / Browser / Claude Code)        │
│                                                         │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────┐ │
│  │ Conversation│   │ Continuator  │   │ Checkpoint  │ │
│  │  Observer   │──►│   Client     │──►│   Store     │ │
│  └─────────────┘   └──────┬───────┘   └─────────────┘ │
│                           │                             │
└───────────────────────────┼─────────────────────────────┘
                            │
              ┌─────────────▼─────────────┐
              │  continuator CLI / serve  │
              │  V10 State Extractor      │
              └───────────────────────────┘
```

### Shared components (build once)

| Component | Language | Responsibility |
|-----------|----------|----------------|
| `@continuator/sdk` | TypeScript | Types, checkpoint I/O, CLI bridge |
| `CheckpointStore` | TS | Read/write `checkpoint.yaml` per workspace |
| `ConversationAdapter` | TS per host | Host-specific transcript extraction |
| `RenderView` | shared enum | briefing, explain, resume, export targets |

---

## Phase 3 — Cursor Extension

### User stories

1. After a long agent session, run **"Continuator: Checkpoint conversation"** → saves `checkpoint.yaml`.
2. When context is large, run **"Continuator: Resume from checkpoint"** → injects compressed state.
3. Status bar shows last checkpoint age and project name.

### Conversation observation

| Approach | Feasibility | Notes |
|----------|-------------|-------|
| Read Cursor chat export | ✅ MVP | User exports or extension reads chat history API if exposed |
| Cursor extension API for chat | ⚠️ Unknown | Depends on Cursor extension surface; may not expose full thread |
| File watcher on Cursor DB | ❌ Fragile | Internal format churn |

**MVP path:** Command palette → user selects exported `.txt` / extension reads from clipboard / future Cursor chat API when available.

**Stretch:** Hook into Cursor's agent transcript if extension host exposes it (monitor Cursor changelog).

### Extension APIs required

| API | Purpose |
|-----|---------|
| `vscode.commands.registerCommand` | Checkpoint, Resume, Export commands |
| `vscode.workspace.workspaceFolders` | Project slug from repo root |
| `vscode.window.showInformationMessage` | Success / archetype warning |
| `vscode.env.clipboard` | Copy briefing to clipboard |
| Cursor-specific: AI chat panel access | **Blocker to validate** — prototype in week 1 |

### Local storage strategy

```
<workspace>/.continuator/
  checkpoint.yaml              # latest state for this project
  checkpoints/
    2026-06-21T143000.yaml     # optional history (Phase 2+)
  meta.json                    # last_extracted_hash, message_count
```

**Why workspace-local:** Checkpoints belong to the project, not global user dir. Aligns with git repo boundaries.

Fallback: `~/.continuator/projects/<slug>/` when no workspace open.

### State update frequency

| Trigger | Action |
|---------|--------|
| Manual command | Full or incremental extract |
| Session end (window blur / tab close) | Optional auto-checkpoint (off by default) |
| Every N messages | **Not recommended** — LoRA cost; use incremental in Phase 2 |
| Context > 80% window | Prompt: "Checkpoint recommended" |

**Default:** Manual only for MVP. Auto-checkpoint behind setting `continuator.autoCheckpointOnSave`.

### Cursor extension commands

| Command | SDK call |
|---------|----------|
| `continuator.checkpoint` | `extract(transcript)` → write yaml |
| `continuator.resume` | `render(checkpoint, briefing)` → insert at cursor / new composer |
| `continuator.exportForClaude` | `export(checkpoint, claude)` → clipboard |
| `continuator.showState` | Webview with structured fields |

### Implementation stack

- TypeScript, VS Code extension API (Cursor-compatible)
- Spawns: `continuator checkpoint -q --stdin` or `continuator serve` HTTP
- Shares `@continuator/sdk` with VS Code extension (~80% code reuse)

---

## Phase 3 — VS Code Extension

Nearly identical to Cursor with different distribution:

| Dimension | Cursor | VS Code |
|-----------|--------|---------|
| Chat source | Cursor Composer / Agent | Copilot Chat (if API allows) |
| Marketplace | Cursor marketplace | VS Code Marketplace |
| Priority | **First** extension target | Second — shared codebase |

### VS Code-specific

| Feature | API |
|---------|-----|
| Checkpoint panel | `WebviewPanel` showing `CheckpointState` fields |
| Task integration | `.vscode/tasks.json` contrib for `continuator checkpoint` |
| Copilot context | `vscode.chat.registerChatContextProvider` (when stable) |

**Feasibility note:** Copilot Chat API for reading full thread history is evolving. MVP uses file/clipboard like Cursor.

---

## Phase 4 — Claude Code Integration

### Option A: Slash commands (recommended MVP)

Claude Code supports project-level commands via `CLAUDE.md` and plugin hooks.

```bash
# User runs in Claude Code session
/continuator checkpoint
/continuator resume
```

**Implementation:** Shell out to `continuator` CLI; write/read `.continuator/checkpoint.yaml` in repo root.

| Pros | Cons |
|------|------|
| Zero Claude API dependency | Manual trigger |
| Same binary as terminal | No inline UI |
| Works today | |

### Option B: MCP server (recommended production)

```
Claude Code ──MCP──► continuator-mcp-server
                         │
                         ├─ tool: extract_conversation
                         ├─ tool: get_checkpoint
                         ├─ tool: resume_briefing
                         └─ resource: checkpoint://project/state
```

| MCP Tool | Input | Output |
|----------|-------|--------|
| `continuator_extract` | `{ transcript, project }` | `CheckpointRecord` JSON |
| `continuator_checkpoint` | `{ project }` | writes yaml, returns path |
| `continuator_resume` | `{ project, format }` | briefing text for injection |
| `continuator_merge` | `{ project, delta }` | updated state (Phase 2) |

**Feasibility:** High. Claude Code MCP is designed for this pattern. Python MCP server wraps existing `run_continuator()`.

### Option C: Codex / OpenAI integration

| Path | Feasibility |
|------|-------------|
| Codex CLI hook | Medium — depends on hook API stability |
| Custom GPT action | Low — privacy concern for full transcripts |
| MCP (if Codex supports) | Watch — same server as Claude |

**Recommendation:** Ship Claude Code MCP first; Codex follows same server with adapter.

### Claude Code storage

```
<repo>/.continuator/checkpoint.yaml     # same as Cursor/VS Code
CLAUDE.md                               # document workflow
```

Resume workflow in `CLAUDE.md`:

```markdown
## Continuator
When context is long, run MCP `continuator_resume` and treat the briefing as prior context.
```

---

## Phase 5 — Browser Extension

### Targets

| Platform | DOM stability | Priority |
|----------|---------------|----------|
| ChatGPT | Medium — class churn | P1 |
| Claude.ai | Medium | P1 |
| Gemini | Medium | P2 |
| Grok | Low — newer UI | P3 |

### Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Browser Extension (Manifest V3)                          │
│                                                          │
│  Content Script          Background Worker               │
│  ┌──────────────┐       ┌─────────────────────┐         │
│  │ DOM scraper  │──────►│ ContinuatorClient   │         │
│  │ (per platform)│       │                     │         │
│  └──────────────┘       │  Option A: Native    │         │
│                         │   Messaging → local  │         │
│  Popup UI               │   continuator serve  │         │
│  ┌──────────────┐       │  Option B: WASM      │         │
│  │ Checkpoint   │       │   (future, heavy)    │         │
│  │ Export       │       └──────────┬──────────┘         │
│  │ New chat     │                  │                     │
│  └──────────────┘                  ▼                     │
└────────────────────────────────────┼─────────────────────┘
                                     │
                          localhost:8741 (continuator serve)
                          V10 runs locally — transcript stays on machine
```

**Privacy default:** Browser sends transcript to **local service only**, never to Continuator cloud (no cloud in plan).

### Content script responsibilities

| Platform | Extraction strategy |
|----------|---------------------|
| ChatGPT | Query message list containers; join role + content |
| Claude | Similar; handle artifact blocks |
| Gemini | Turn-based div scan |
| Grok | TBD — adapter pattern |

**Adapter interface:**

```typescript
interface PlatformAdapter {
  platform: 'chatgpt' | 'claude' | 'gemini' | 'grok';
  scrapeConversation(): string;
  injectIntoNewChat(briefing: string): void;
  detectConversationId(): string;
}
```

### User flows

**Flow 1 — Checkpoint**
1. User clicks extension icon → "Checkpoint this chat"
2. Content script scrapes DOM → transcript
3. Background calls local `continuator serve /extract`
4. Saves `checkpoint.yaml` to extension storage + download option
5. Shows: objective, next_action, compression ratio

**Flow 2 — Export to new chat**
1. User clicks "Continue in new chat"
2. Render briefing via `export(claude|chatgpt|gemini)`
3. Open new chat tab; paste into input (or clipboard + prompt)
4. Platform-specific: ChatGPT "new chat" URL; Claude project chat

**Flow 3 — Resume from file**
1. User loads existing `checkpoint.yaml`
2. Extension renders briefing → new chat

### Browser storage

| Store | Contents |
|-------|----------|
| `chrome.storage.local` | Last N checkpoints (metadata + yaml text) |
| Download | User-saveable `checkpoint.yaml` |
| No sync | Local only |

### Blockers

| Blocker | Mitigation |
|---------|------------|
| DOM selectors break on UI update | Adapter per platform; fixture tests; version pinning in manifest |
| Cannot open new chat programmatically | Clipboard + user instruction fallback |
| Local service not running | Extension installer bundles "start continuator serve" helper |
| LoRA too heavy for in-browser | Must use local Python service — no WASM in Phase 5 |

---

## Cross-extension checkpoint portability

All extensions read/write the same file per [`checkpoint_format_v2.md`](checkpoint_format_v2.md):

```
<project>/.continuator/checkpoint.yaml
```

A checkpoint created in Cursor opens in browser extension, terminal, and Claude Code.

---

## Extension MVP priority

| Order | Extension | Rationale |
|-------|-----------|-----------|
| 1 | **Cursor** | Target user (agentic coding); highest checkpoint value |
| 2 | **Claude Code MCP** | CLI-native audience; low UI cost |
| 3 | **VS Code** | Shared codebase with Cursor |
| 4 | **Browser** | Broad reach; DOM fragility; requires `continuator serve` |

---

## `@continuator/sdk` (TypeScript) — shared library

```typescript
// types.ts
export interface CheckpointRecord { /* see checkpoint_format_v2 */ }
export type RenderView = 'briefing' | 'explain' | 'state' | 'resume';
export type ExportTarget = 'claude' | 'chatgpt' | 'gemini' | 'markdown';

// client.ts — Phase 3
export class CliClient {
  async extract(transcript: string, project: string): Promise<CheckpointRecord>;
  async render(record: CheckpointRecord, view: RenderView): Promise<string>;
  async export(record: CheckpointRecord, target: ExportTarget): Promise<string>;
}

// store.ts
export class CheckpointStore {
  constructor(private root: string) {}  // .continuator/
  async load(): Promise<CheckpointRecord | null>;
  async save(record: CheckpointRecord): Promise<void>;
}
```

---

## Risk matrix

| Risk | Impact | Mitigation |
|------|--------|------------|
| Host doesn't expose chat API | Extensions blocked | File/clipboard MVP; engage platform partners |
| LoRA latency (10–120s) | Poor UX | `continuator serve` keeps model warm; incremental extract |
| DOM scraping breaks | Browser ext outage | Adapter versioning; graceful degradation |
| Checkpoint not useful for Q&A chats | User trust loss | Archetype warning (see archetype analysis) |
| Multiple extensions diverge | Format fragmentation | Single `checkpoint_format_v2`; shared SDK |

---

## Related documents

- [`platform_architecture.md`](platform_architecture.md) — platform layers
- [`checkpoint_format_v2.md`](checkpoint_format_v2.md) — portable format
- [`integration_roadmap.md`](integration_roadmap.md) — delivery phases
